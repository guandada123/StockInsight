"""价格预警模块

支持四种预警类型：
- price: 价格突破/跌破目标价
- volume: 放量预警（成交量超过 N 倍 20日均量）
- technical: 技术指标预警（RSI超买超卖、MACD金叉死叉）
- fundamental: 基本面预警（ROE等指标阈值）

存储路径：
- 规则: {os.path.join(os.path.dirname(os.path.dirname(__file__)), "alerts.json")}
- 日志: {os.path.join(os.path.dirname(os.path.dirname(__file__)), "alerts_log.txt")}

飞书集成：
- 触发预警时自动推送到飞书群（需配置 FEISHU_WEBHOOK_URL 环境变量）
- 设置 FEISHU_ALERTS_ENABLED=0 可禁用飞书推送
"""

import json
import os
import re
import time
import uuid

import numpy as np

from .analysis import full_technical_analysis
from .cache import cached_fundamentals, cached_kline
from .config import ALERTS_LOG_PATH, ALERTS_PATH
from .fetcher import sina_real_time

LOG_PATH = ALERTS_LOG_PATH


# ── 持久化操作 ─────────────────────────────────────


def load_alerts():
    """从 alerts.json 加载所有预警规则"""
    if not os.path.exists(ALERTS_PATH):
        return []
    try:
        with open(ALERTS_PATH, encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return []
            return json.loads(content)
    except (json.JSONDecodeError, Exception):
        return []


def _save_alerts(alerts):
    """保存预警列表到 alerts.json"""
    with open(ALERTS_PATH, "w", encoding="utf-8") as f:
        json.dump(alerts, f, ensure_ascii=False, indent=2)


def add_alert(config):
    """添加一条预警规则，自动分配 id 并持久化

    参数
    ----
    config : dict
        预警配置，格式见模块文档

    返回
    ----
    str : 分配的预警 id
    """
    alerts = load_alerts()
    alert_id = str(uuid.uuid4())[:8]
    config["id"] = alert_id
    config.setdefault("enabled", True)
    alerts.append(config)
    _save_alerts(alerts)
    print(f"  预警已添加 [{alert_id}]: {config}")
    return alert_id


def remove_alert(alert_id):
    """根据 id 删除预警规则"""
    alerts = load_alerts()
    new_alerts = [a for a in alerts if a.get("id") != alert_id]
    if len(new_alerts) == len(alerts):
        print(f"  未找到预警: {alert_id}")
        return False
    _save_alerts(new_alerts)
    print(f"  预警已删除: {alert_id}")
    return True


# ── 核心检查逻辑 ───────────────────────────────────


def _get_current_price(code):
    """获取某只股票的实时价格"""
    rt = sina_real_time([code])
    if code in rt:
        return rt[code].get("最新价")
    return None


def _check_price_alert(config):
    """检查价格预警

    格式: {"type": "price", "code": "...", "direction": "above"/"below", "target": float}
    """
    code = config["code"]
    direction = config["direction"]
    target = float(config["target"])

    price = _get_current_price(code)
    if price is None:
        return None, f"{code}: 无法获取实时价格"

    triggered = False
    if direction == "above" and price > target or direction == "below" and price < target:
        triggered = True

    if triggered:
        symbol = ">" if direction == "above" else "<"
        msg = f"价格预警 {code}: 当前价 {price:.2f} {symbol} 目标 {target:.2f}"
        return True, msg
    return False, None


def _check_volume_alert(config):
    """检查放量预警

    格式: {"type": "volume", "code": "...", "multiplier": 2.0}
    """
    code = config["code"]
    multiplier = float(config["multiplier"])

    df = cached_kline(code, days=30)
    if df.empty or len(df) < 21:
        return None, f"{code}: K线数据不足"

    latest = df.iloc[-1]
    current_volume = latest.get("成交量", 0)
    avg_volume = df["成交量"].tail(20).mean()

    if avg_volume == 0 or np.isnan(avg_volume):
        return None, f"{code}: 均量为零"

    ratio = current_volume / avg_volume
    if ratio > multiplier:
        msg = (
            f"放量预警 {code}: 当前量 {current_volume:.0f}, "
            f"20日均量 {avg_volume:.0f}, 倍数 {ratio:.2f}x "
            f"(阈值 {multiplier}x)"
        )
        return True, msg
    return False, None


def _check_technical_alert(config):
    """检查技术指标预警

    格式: {"type": "technical", "code": "...", "indicator": "RSI"/"MACD", "condition": ">80"/"<20"/"金叉"/"死叉"}
    """
    code = config["code"]
    indicator = config["indicator"]
    condition = config["condition"]

    df = cached_kline(code, days=120)
    if df.empty:
        return None, f"{code}: K线数据为空"

    df = full_technical_analysis(df)
    if df.empty:
        return None, f"{code}: 技术分析失败"

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    if indicator.upper() == "RSI":
        rsi_val = last.get("RSI")
        if rsi_val is None or np.isnan(rsi_val):
            return None, f"{code}: RSI 值无效"

        if condition == ">80":
            if rsi_val > 80:
                return True, f"RSI预警 {code}: RSI={rsi_val:.1f} > 80 (超买)"
        elif condition == "<20":
            if rsi_val < 20:
                return True, f"RSI预警 {code}: RSI={rsi_val:.1f} < 20 (超卖)"
        elif condition.startswith(">"):
            threshold = float(condition[1:])
            if rsi_val > threshold:
                return True, f"RSI预警 {code}: RSI={rsi_val:.1f} > {threshold}"
        elif condition.startswith("<"):
            threshold = float(condition[1:])
            if rsi_val < threshold:
                return True, f"RSI预警 {code}: RSI={rsi_val:.1f} < {threshold}"
        return False, None

    elif indicator.upper() == "MACD":
        dif_now = last.get("DIF")
        dea_now = last.get("DEA")
        dif_prev = prev.get("DIF")
        dea_prev = prev.get("DEA")

        if any(x is None or np.isnan(x) for x in [dif_now, dea_now, dif_prev, dea_prev]):
            return None, f"{code}: MACD 值无效"

        if condition == "金叉":
            if dif_now > dea_now and dif_prev <= dea_prev:
                return True, f"MACD金叉 {code}: DIF={dif_now:.3f} 上穿 DEA={dea_now:.3f}"
        elif condition == "死叉":
            if dif_now < dea_now and dif_prev >= dea_prev:
                return True, f"MACD死叉 {code}: DIF={dif_now:.3f} 下穿 DEA={dea_now:.3f}"
        else:
            # 支持自定义阈值 "DIF>DEA" 等
            m = re.match(r"(DIF|DEA)\s*(>|<|>=|<=)\s*([-+]?\d+\.?\d*)", condition)
            if m:
                col, op, val_str = m.group(1), m.group(2), m.group(3)
                val = float(val_str)
                actual = last.get(col)
                if actual is None or np.isnan(actual):
                    return None, f"{code}: {col} 值无效"
                if op == ">" and actual > val:
                    return True, f"MACD预警 {code}: {col}={actual:.3f} > {val}"
                elif op == "<" and actual < val:
                    return True, f"MACD预警 {code}: {col}={actual:.3f} < {val}"
                elif op == ">=" and actual >= val:
                    return True, f"MACD预警 {code}: {col}={actual:.3f} >= {val}"
                elif op == "<=" and actual <= val:
                    return True, f"MACD预警 {code}: {col}={actual:.3f} <= {val}"
        return False, None

    else:
        return None, f"{code}: 不支持的技术指标 {indicator}"


def _check_fundamental_alert(config):
    """检查基本面预警

    格式: {"type": "fundamental", "code": "...", "metric": "ROE", "condition": "<10"}
    """
    code = config["code"]
    metric = config["metric"]
    condition = config["condition"]

    fundamentals = cached_fundamentals(code)
    actual = fundamentals.get(metric)
    if actual is None:
        return None, f"{code}: 无 {metric} 数据"

    # 解析条件
    m = re.match(r"(>|<|>=|<=)\s*([-+]?\d+\.?\d*)", str(condition))
    if not m:
        return None, f"{code}: 无法解析条件 {condition}"

    op, val_str = m.group(1), m.group(2)
    threshold = float(val_str)

    triggered = False
    if (
        op == ">"
        and actual > threshold
        or op == "<"
        and actual < threshold
        or op == ">="
        and actual >= threshold
        or op == "<="
        and actual <= threshold
    ):
        triggered = True

    if triggered:
        unit = "%" if metric in ("ROE", "营收增长", "净利润增长", "毛利率", "净利率") else ""
        msg = f"基本面预警 {code}: {metric}={actual:.2f}{unit} {op} {threshold}{unit}"
        return True, msg
    return False, None


# ── 批量检查 ───────────────────────────────────────


def check_alerts(alert_list):
    """检查一组预警规则，返回触发列表

    参数
    ----
    alert_list : list[dict]
        预警配置列表

    返回
    ----
    list[dict] : 触发的预警，每项含 id、类型、消息等
    """
    triggered = []
    for config in alert_list:
        if not config.get("enabled", True):
            continue

        alert_type = config.get("type")
        code = config.get("code", "?")

        try:
            if alert_type == "price":
                result, msg = _check_price_alert(config)
            elif alert_type == "volume":
                result, msg = _check_volume_alert(config)
            elif alert_type == "technical":
                result, msg = _check_technical_alert(config)
            elif alert_type == "fundamental":
                result, msg = _check_fundamental_alert(config)
            else:
                result, msg = None, f"{code}: 未知预警类型 {alert_type}"

            if result is True:
                triggered.append(
                    {
                        "id": config.get("id"),
                        "type": alert_type,
                        "code": code,
                        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "message": msg,
                        "config": config,
                    }
                )
            elif result is None:
                # 检查出错，打印警告但不中断
                print(f"  [警告] {msg}")

        except Exception as e:
            print(f"  [错误] 检查预警 {config.get('id', '?')} 时异常: {e}")

    return triggered


# ── 运行全部预警 ───────────────────────────────────


def _notify_via_feishu(triggered: list) -> bool:
    """将触发的预警推送到飞书群"""
    webhook_url = os.environ.get("FEISHU_WEBHOOK_URL", os.environ.get("FEISHU_WEBHOOK", ""))
    if not webhook_url:
        return False

    if os.environ.get("FEISHU_ALERTS_ENABLED", "1") != "1":
        return False

    try:
        lines = ["【StockInsight 预警触发】"]
        for t in triggered:
            emoji = "🔴" if t.get("type") in ("price", "fundamental") else "🟡"
            lines.append(f"{emoji} [{t['type']}] {t['message']}")

        content = "\n".join(lines)
        payload = {"msg_type": "text", "content": {"text": content}}

        import urllib.request
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("code") == 0:
                print(f"  ✅ 已推送 {len(triggered)} 条预警到飞书")
                return True
            else:
                print(f"  ⚠️ 飞书返回异常: {result}")
                return False
    except Exception as e:
        print(f"  ⚠️ 飞书推送失败: {e}")
        return False


def run_all_alerts():
    """加载并检查所有预警，触发时打印到终端、写入日志文件、飞书推送"""
    alerts = load_alerts()
    if not alerts:
        print("  无待检查的预警规则")
        return []

    print(f"  共 {len(alerts)} 条预警规则，开始检查...")
    triggered = check_alerts(alerts)

    if not triggered:
        print("  本次无预警触发")
        return []

    # 终端输出
    print("\n  ╔══════════════════════════════════════════╗")
    print(f"  ║       触发预警汇总 ({len(triggered)} 条)          ║")
    print("  ╚══════════════════════════════════════════╝")
    for t in triggered:
        print(f"  [{t['time']}] [{t['type']}] {t['message']}")

    # 写入日志
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        for t in triggered:
            f.write(f"[{t['time']}] [{t['type']}] [{t['code']}] {t['message']}\n")
        f.write(f"-- 检查完成于 {timestamp}, 触发 {len(triggered)} 条 --\n")

    print(f"  日志已写入: {LOG_PATH}")

    # 飞书推送
    _notify_via_feishu(triggered)

    return triggered
