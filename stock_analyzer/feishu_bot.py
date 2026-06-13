"""飞书群机器人 — 消息发送与格式化

飞书自定义机器人 Webhook 推送，不依赖飞书 SDK，纯 HTTP POST。
支持文本消息、富文本消息、大盘简报、选股推荐。

Webhook URL 配置：环境变量 FEISHU_WEBHOOK_URL
"""

import json
import os
import urllib.error
import urllib.request
from datetime import datetime


def _webhook_url():
    """获取 Webhook URL，优先环境变量"""
    url = os.environ.get("FEISHU_WEBHOOK_URL", "")
    if not url:
        # 尝试从 .env 文件读取
        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        if os.path.exists(env_file):
            with open(env_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("FEISHU_WEBHOOK_URL="):
                        url = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
    return url


def send_text(content, webhook_url=None):
    """发送纯文本消息"""
    url = webhook_url or _webhook_url()
    if not url:
        return {"ok": False, "error": "未配置 FEISHU_WEBHOOK_URL"}
    payload = {"msg_type": "text", "content": {"text": content}}
    return _post(url, payload)


def send_post(title, paragraphs, webhook_url=None):
    """发送富文本消息

    Args:
        title: 消息标题
        paragraphs: 段落列表，每个段落是 [[tag_obj, ...], ...]
                    tag_obj 格式: {"tag": "text", "text": "..."}
                    或: {"tag": "a", "text": "...", "href": "..."}
    """
    url = webhook_url or _webhook_url()
    if not url:
        return {"ok": False, "error": "未配置 FEISHU_WEBHOOK_URL"}
    payload = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": title,
                    "content": paragraphs,
                }
            }
        },
    }
    return _post(url, payload)


def send_market_brief(webhook_url=None):
    """发送大盘简报 — 四大指数 + 涨跌停统计"""
    try:
        from stock_analyzer.fetcher import get_market_overview

        market = get_market_overview()

        idx_map = {"000001": "上证", "399001": "深证", "399006": "创业板", "000688": "科创50"}
        lines = []
        for code, name in idx_map.items():
            info = market.get(code, {})
            price = float(info.get("最新价", 0) or 0)
            prev = float(info.get("昨收", 0) or 0)
            chg_pct = round((price - prev) / prev * 100, 2) if prev else 0
            direction = "+" if chg_pct >= 0 else ""
            lines.append(f"{name} {price:.2f} {direction}{chg_pct:.2f}%")

        # 涨跌停
        try:
            import akshare as ak

            df = ak.stock_zt_pool_em(date=None)
            limit_up = len(df[df.get("涨跌幅", 0) >= 9.8]) if not df.empty else 0
            limit_down = len(df[df.get("涨跌幅", -100) <= -9.8]) if not df.empty else 0
            lines.append(f"涨停 {limit_up} 只 | 跌停 {limit_down} 只")
        except Exception:
            pass

        now = datetime.now().strftime("%H:%M")
        title = f"大盘简报 {now}"
        content = [[{"tag": "text", "text": "\n".join(lines)}]]
        return send_post(title, content, webhook_url)
    except Exception as e:
        return {"ok": False, "error": str(e)}


def send_stock_picks(picks, sector_ranking, market_summary="", webhook_url=None):
    """发送尾盘选股推荐

    Args:
        picks: 推荐股票列表，每项 dict:
            {code, name, price, change_pct, score, rating, sector, sector_rank,
             signal, ai_direction, ai_confidence, entry_low, entry_high,
             stop_loss, take_profit, level}
        sector_ranking: 板块排名列表
        market_summary: 大盘简述
        webhook_url: Webhook URL
    """
    url = webhook_url or _webhook_url()
    if not url:
        return {"ok": False, "error": "未配置 FEISHU_WEBHOOK_URL"}

    now = datetime.now().strftime("%m-%d %H:%M")
    title = f"尾盘选股推荐 {now}"

    paragraphs = []

    # 大盘
    if market_summary:
        paragraphs.append([{"tag": "text", "text": f"【大盘】{market_summary}"}])

    # 板块
    if sector_ranking:
        sector_lines = ["【强势板块】"]
        for i, s in enumerate(sector_ranking[:5]):
            sector_lines.append(
                f"{i + 1}. {s['name']} {s['change_pct']:+.2f}% 资金{s['fund_flow_yi']:+.1f}亿"
            )
        paragraphs.append([{"tag": "text", "text": "\n".join(sector_lines)}])

    # 推荐个股
    level_labels = {"strong": "强推", "buy": "可买", "watch": "关注"}
    level_colors = {"strong": "🔴", "buy": "🟡", "watch": "⚪"}

    for i, pick in enumerate(picks[:8]):
        level = pick.get("level", "buy")
        label = level_labels.get(level, level)
        icon = level_colors.get(level, "")

        lines = []
        lines.append(
            f"{icon} #{i + 1} {pick['name']}({pick['code']}) | 评分{pick.get('score', 0):.0f} {pick.get('rating', '')}"
        )
        lines.append(
            f"    现价{pick.get('price', 0):.2f} | 5日{pick.get('near_5d', 0):+.1f}% | 20日{pick.get('near_20d', 0):+.1f}%"
        )
        lines.append(
            f"    板块#{pick.get('sector_rank', '?')} {pick.get('sector', '')} | AI{pick.get('ai_direction', '?')} {pick.get('ai_confidence', 0):.0f}%"
        )
        if pick.get("entry_low"):
            lines.append(
                f"    买入 {pick['entry_low']:.2f}~{pick['entry_high']:.2f} | 止损 {pick.get('stop_loss', 0):.2f} | 止盈 {pick.get('take_profit', 0):.2f}"
            )

        paragraphs.append([{"tag": "text", "text": "\n".join(lines)}])

    # 风险提示
    paragraphs.append(
        [
            {
                "tag": "text",
                "text": "⚠ 以上基于量化模型和历史数据，不构成投资建议。市场有风险，投资需谨慎。",
            }
        ]
    )

    return send_post(title, paragraphs, url)


def send_alert(alert_type, message, webhook_url=None):
    """发送预警消息"""
    now = datetime.now().strftime("%H:%M:%S")
    content = f"[{alert_type}] {now}\n{message}"
    return send_text(content, webhook_url)


def _post(url, payload, timeout=10):
    """发送 POST 请求到飞书 Webhook"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            ok = result.get("code") == 0 or result.get("StatusCode") == 0
            return {"ok": ok, "response": result}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"HTTP {e.code}: {body[:200]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── 便捷函数 ──


def push_daily_picks(webhook_url=None):
    """一键推送：拉数据 → 选股 → 分析 → 推送

    这是最常用的入口，封装了完整流程。
    """
    from stock_analyzer.fetcher import get_market_overview, get_sectors, sina_real_time
    from stock_analyzer.sector_info import get_stock_sector_full

    url = webhook_url or _webhook_url()
    if not url:
        print("错误: 未配置 FEISHU_WEBHOOK_URL")
        print("设置方式: set FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx")
        return {"ok": False, "error": "未配置 Webhook URL"}

    # 1. 大盘
    market = get_market_overview()
    idx_lines = []
    idx_map = {"000001": "上证", "399001": "深证", "399006": "创业板", "000688": "科创50"}
    for code, name in idx_map.items():
        info = market.get(code, {})
        price = float(info.get("最新价", 0) or 0)
        prev = float(info.get("昨收", 0) or 0)
        chg_pct = round((price - prev) / prev * 100, 2) if prev else 0
        idx_lines.append(f"{name} {price:.2f} {chg_pct:+.2f}%")
    market_summary = " | ".join(idx_lines)

    # 2. 板块排名
    sectors = get_sectors()
    sector_ranking = []
    if isinstance(sectors, dict) and sectors:
        ranked = sorted(
            sectors.items(), key=lambda x: float(x[1].get("涨跌幅", 0) or 0), reverse=True
        )
        for i, (nm, info) in enumerate(ranked[:5]):
            sector_ranking.append(
                {
                    "name": nm,
                    "change_pct": round(float(info.get("涨跌幅", 0) or 0), 2),
                    "fund_flow_yi": round(float(info.get("资金净流入", 0) or 0) / 1e8, 1),
                }
            )

    # 3. 增强选股
    print("正在执行增强选股...")
    codes = []
    try:
        from stock_analyzer.enhanced_screener import enhanced_scan

        result_df = enhanced_scan(top_n=15, min_score=45)
        if result_df is not None and len(result_df) > 0:
            codes = result_df["code"].tolist() if "code" in result_df.columns else []
            # 限制数量
            codes = [str(c).zfill(6) for c in codes[:8]]
            print(f"选股完成: {len(codes)} 只候选")
        else:
            print("增强选股未返回结果")
    except Exception as e:
        print(f"选股异常: {e}")
        import traceback

        traceback.print_exc()

    if not codes:
        print("未找到候选股票，推送板块信息")
        send_market_brief(url)
        return {"ok": True, "fallback": "仅推送大盘简报"}

    print(f"候选股票: {codes}")
    picks = []
    for code in codes:
        try:
            from stock_analyzer.analyzer import deep_analyze

            r = deep_analyze(code, days=120)
            if r is None:
                continue

            kline = r["_kline"]
            rt = sina_real_time([code])
            info = rt.get(code, {})
            name = info.get("名称", code)
            price = float(info.get("最新价", 0) or r.get("price", 0))
            prev = float(info.get("昨收", 0) or 0)
            change_pct = round((price - prev) / prev * 100, 2) if prev else 0

            score = r.get("qs_composite", 50)
            rating = r.get("qs_rating", "")
            if score >= 65:
                level = "strong"
            elif score >= 50:
                level = "buy"
            else:
                level = "watch"

            # AI 预测
            ai_dir = "?"
            ai_conf = 0
            try:
                from stock_analyzer.ml_predict import predict_ensemble

                ai = predict_ensemble(kline, {})
                ai_dir = ai.get("ensemble_direction", "?")
                ai_conf = ai.get("ensemble_confidence", 0)
            except Exception:
                pass

            # 板块
            sector = ""
            try:
                sector = get_stock_sector_full(code)
            except Exception:
                pass

            # 止损止盈
            entry_low = round(price * 0.97, 2)
            entry_high = round(price * 1.01, 2)
            stop_loss = round(price * 0.93, 2)
            take_profit = round(price * 1.08, 2)

            picks.append(
                {
                    "code": code,
                    "name": name,
                    "price": price,
                    "change_pct": change_pct,
                    "score": score,
                    "rating": rating,
                    "level": level,
                    "near_5d": r.get("near_5d", 0),
                    "near_20d": r.get("near_20d", 0),
                    "sector": sector.split(" > ")[-1] if " > " in sector else sector,
                    "sector_rank": "?",
                    "signal": r.get("macd_signal", ""),
                    "ai_direction": ai_dir,
                    "ai_confidence": ai_conf,
                    "entry_low": entry_low,
                    "entry_high": entry_high,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                }
            )
        except Exception as e:
            print(f"  {code} 分析异常: {e}")
            continue

    if not picks:
        send_market_brief(url)
        return {"ok": True, "fallback": "无有效候选"}

    # 按评分排序
    picks.sort(key=lambda x: x["score"], reverse=True)

    # 限制强推+可买不超过8只
    result_picks = [p for p in picks if p["level"] != "watch"][:8]

    print(f"推送 {len(result_picks)} 只推荐股")
    return send_stock_picks(result_picks, sector_ranking, market_summary, url)
