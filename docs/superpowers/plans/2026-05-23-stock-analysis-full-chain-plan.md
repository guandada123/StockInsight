# 全链路股票分析系统 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 6 个新增模块构建完整分析闭环：数据缓存 → 选股池 → 组合管理 → 价格预警 → HTML报告 → 单元测试

**Architecture:** 所有模块为独立文件，不修改现有代码。cache.py 作为底层依赖，screener/portfolio/alert 复用现有 analysis.py/quant.py，report_html.py 完全独立。

**Tech Stack:** Python 3, sqlite3(built-in), unittest(built-in), json, pandas, Chart.js(CDN)

---

### Task 1: 数据缓存层 `stock_analyzer/cache.py`

**Files:**
- Create: `D:\CC\5.23\stock_analyzer\cache.py`

SQLite 缓存，通用 KV 存储，自动过期。

```sql
CREATE TABLE cache (
    key TEXT PRIMARY KEY,
    value BLOB,
    created_at REAL,
    ttl_seconds INTEGER
);
```

TTL: K线4h, 基本面24h, 板块2h, 实时行情30min。

- [ ] **Step 1: 创建 cache.py，实现核心函数**

写入 `D:\CC\5.23\stock_analyzer\cache.py`：

```python
"""数据缓存层 — SQLite 通用 KV 缓存"""
import sqlite3
import pickle
import time
import os
import threading

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "stock_cache.db")
_TTL = {"kline": 14400, "fundamentals": 86400, "sectors": 7200, "realtime": 1800}
_local = threading.local()


def _get_conn():
    """线程内复用连接"""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH)
        _local.conn.execute(
            "CREATE TABLE IF NOT EXISTS cache ("
            "key TEXT PRIMARY KEY, value BLOB, created_at REAL, ttl_seconds INTEGER)"
        )
    return _local.conn


def cache_get(key):
    try:
        cur = _get_conn().execute("SELECT value, created_at, ttl_seconds FROM cache WHERE key=?", (key,))
        row = cur.fetchone()
        if row is None:
            return None
        val, created, ttl = row
        if time.time() - created > ttl:
            _get_conn().execute("DELETE FROM cache WHERE key=?", (key,))
            return None
        return pickle.loads(val)
    except Exception:
        return None


def cache_set(key, value, ttl=3600):
    try:
        _get_conn().execute(
            "INSERT OR REPLACE INTO cache (key, value, created_at, ttl_seconds) VALUES (?,?,?,?)",
            (key, pickle.dumps(value), time.time(), ttl),
        )
        _get_conn().commit()
    except Exception:
        pass


def cache_clear(key):
    try:
        _get_conn().execute("DELETE FROM cache WHERE key=?", (key,))
        _get_conn().commit()
    except Exception:
        pass


def cache_clear_all():
    try:
        _get_conn().execute("DELETE FROM cache")
        _get_conn().commit()
    except Exception:
        pass


def _ttl_for(data_type):
    return _TTL.get(data_type, 3600)


def cached_kline(code, days=120):
    """包装 get_kline，自动走缓存"""
    from .fetcher import get_kline
    key = f"kline:{code}:{days}"
    cached = cache_get(key)
    if cached is not None:
        return cached
    df = get_kline(code, days)
    if not df.empty:
        cache_set(key, df, _ttl_for("kline"))
    return df


def cached_fundamentals(code):
    """包装 get_fundamentals，自动走缓存"""
    from .fetcher import get_fundamentals
    key = f"fundamentals:{code}"
    cached = cache_get(key)
    if cached is not None:
        return cached
    data = get_fundamentals(code)
    cache_set(key, data, _ttl_for("fundamentals"))
    return data


def cached_sectors():
    """包装 get_sectors，自动走缓存"""
    from .fetcher import get_sectors
    key = "sectors"
    cached = cache_get(key)
    if cached is not None:
        return cached
    df = get_sectors()
    if not df.empty:
        cache_set(key, df, _ttl_for("sectors"))
    return df
```

- [ ] **Step 2: 验证缓存正常工作**

```bash
cd D:\CC\5.23 && python -c "
import sys, io; sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from stock_analyzer.cache import cache_set, cache_get, cache_clear

cache_clear_all()
cache_set('test_key', {'a': 1, 'b': [1,2,3]}, ttl=60)
result = cache_get('test_key')
print('写入和读取:', 'OK' if result and result['a'] == 1 else 'FAIL')

import time
cache_set('expire_key', 'expire', ttl=1)
time.sleep(1.5)
result2 = cache_get('expire_key')
print('过期处理:', 'OK' if result2 is None else 'FAIL')

from stock_analyzer.cache import cached_kline
kline = cached_kline('300408', 30)
print(f'K线缓存: {len(kline)} 行' if not kline.empty else 'K线获取失败')
"
```


### Task 2: 每日选股池 `stock_analyzer/screener.py`

**Files:**
- Create: `D:\CC\5.23\stock_analyzer\screener.py`

基于缓存调用 `composite_quant_score` 批量评分，支持过滤和排序。

- [ ] **Step 1: 创建 screener.py**

```python
"""每日选股池：全市场批量评分 + 条件过滤"""
import json
import os
import pandas as pd
import time
from .cache import cached_kline, cached_fundamentals
from .analysis import full_technical_analysis
from .quant import composite_quant_score


# 常用股票池（沪深300 + 中证500 的部分代表）
DEFAULT_POOL = {
    "300408", "603005", "600519", "000858", "000333", "002415", "300750",
    "601318", "600036", "000651", "002594", "300059", "600887", "600585",
    "000725", "002475", "300124", "600309", "601166", "600900",
    "000568", "002304", "600809", "000858", "603259", "300015",
    "002230", "300782", "688981", "688036",
}


def _is_st(name):
    return name and ("ST" in name or "退" in name)


def load_stock_pool(source=None):
    """加载股票池，返回代码列表"""
    if source and os.path.exists(source):
        with open(source) as f:
            return json.load(f)
    return list(DEFAULT_POOL)


def run_screener(pool=None, top_n=30):
    """执行全市场扫描，返回评分 DataFrame"""
    if pool is None:
        pool = DEFAULT_POOL
    results = []
    for code in pool:
        try:
            kline = cached_kline(code, days=120)
            if kline.empty or len(kline) < 30:
                continue
            kline = full_technical_analysis(kline)
            funda = cached_fundamentals(code)
            score = composite_quant_score(kline, funda)
            last_close = kline["收盘"].iloc[-1]
            chg = kline["涨跌幅"].iloc[-1]
            results.append({
                "代码": code,
                "综合评分": score["composite_score"],
                "评级": score["rating"],
                "动量分": score["factor_scores"]["momentum"]["score"],
                "技术分": score["factor_scores"]["technical"]["score"],
                "基本面分": score["factor_scores"]["fundamental"]["score"],
                "量能分": score["factor_scores"]["volume"]["score"],
                "风险分": score["factor_scores"]["risk"]["score"],
                "最新价": round(last_close, 2),
                "涨跌幅": round(chg, 2),
            })
        except Exception:
            pass
        time.sleep(0.1)

    df = pd.DataFrame(results)
    if df.empty:
        return df
    df = df.sort_values("综合评分", ascending=False).reset_index(drop=True)
    return df.head(top_n)


def filter_by_conditions(df, min_price=5, max_pe=None, min_score=0):
    """条件过滤"""
    mask = pd.Series([True] * len(df))
    if min_price:
        mask &= (df.get("最新价", 100) >= min_price)
    if min_score:
        mask &= (df.get("综合评分", 0) >= min_score)
    return df[mask].reset_index(drop=True)


def save_screener_result(df, path=None):
    """保存结果到 JSON"""
    if path is None:
        from datetime import datetime
        os.makedirs("D:/CC/5.23/reports", exist_ok=True)
        path = f"D:/CC/5.23/reports/screener_{datetime.now().strftime('%Y%m%d')}.json"
    df.to_json(path, orient="records", force_ascii=False)
    return path
```

- [ ] **Step 2: 验证选股池运行**

```bash
cd D:\CC\5.23 && python -c "
import sys, io; sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from stock_analyzer.screener import run_screener, filter_by_conditions

df = run_screener(top_n=5)
if not df.empty:
    print('选股结果：')
    for _, r in df.iterrows():
        print(f'  {r[\"代码\"]}  评分:{r[\"综合评分\"]}/100  {r[\"评级\"]}  '
              f'动量:{r[\"动量分\"]} 技术:{r[\"技术分\"]} 基本:{r[\"基本面分\"]}  '
              f'量能:{r[\"量能分\"]} 风险:{r[\"风险分\"]}  '
              f'价:{r[\"最新价\"]} 涨幅:{r[\"涨跌幅\"]:+.2f}%')
else:
    print('无数据')
"
```


### Task 3: 投资组合管理 `stock_analyzer/portfolio.py`

**Files:**
- Create: `D:\CC\5.23\stock_analyzer\portfolio.py`
- Create directory: `D:\CC\5.23\portfolios\`

组合 CRUD + 整体分析（收益率/波动率/夏普/贡献度）。

- [ ] **Step 1: 创建 portfolio.py**

```python
"""投资组合管理：创建、分析、调仓"""
import json
import os
import numpy as np
import pandas as pd
from datetime import datetime
from .cache import cached_kline
from .analysis import full_technical_analysis
from .quant import composite_quant_score, calc_risk_metrics, _daily_returns

PORTFOLIO_DIR = "D:/CC/5.23/portfolios"


def _path(name):
    os.makedirs(PORTFOLIO_DIR, exist_ok=True)
    return os.path.join(PORTFOLIO_DIR, f"{name}.json")


def create_portfolio(name, stocks=None):
    """新建组合"""
    portfolio = {
        "name": name,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "stocks": stocks or [],
    }
    save_portfolio(portfolio)
    return portfolio


def save_portfolio(portfolio):
    with open(_path(portfolio["name"]), "w", encoding="utf-8") as f:
        json.dump(portfolio, f, ensure_ascii=False, indent=2)


def load_portfolio(name):
    with open(_path(name), encoding="utf-8") as f:
        return json.load(f)


def list_portfolios():
    os.makedirs(PORTFOLIO_DIR, exist_ok=True)
    return [f.replace(".json", "") for f in os.listdir(PORTFOLIO_DIR) if f.endswith(".json")]


def add_stock(portfolio, code, weight, cost):
    portfolio["stocks"].append({"code": code, "weight": weight, "cost": cost})
    save_portfolio(portfolio)
    return portfolio


def remove_stock(portfolio, code):
    portfolio["stocks"] = [s for s in portfolio["stocks"] if s["code"] != code]
    save_portfolio(portfolio)
    return portfolio


def analyze_portfolio(portfolio):
    """组合整体分析"""
    stocks = portfolio["stocks"]
    if not stocks:
        return {"error": "组合为空", "total_value": 0, "total_return_pct": 0}

    details = []
    weights = []
    daily_rets = []

    for s in stocks:
        code = s["code"]
        kline = cached_kline(code, days=120)
        if kline.empty:
            continue
        kline = full_technical_analysis(kline)
        last_price = kline["收盘"].iloc[-1]
        ret = (last_price / s["cost"] - 1) * 100
        ret_decimal = last_price / s["cost"] - 1
        market_value = last_price * s["weight"]
        original_value = s["cost"] * s["weight"]
        details.append({
            "代码": code,
            "仓位%": round(s["weight"] * 100, 1),
            "成本价": s["cost"],
            "现价": round(last_price, 2),
            "收益率%": round(ret, 2),
            "市值": round(market_value, 2),
        })
        weights.append(s["weight"])
        daily_rets.append(_daily_returns(kline))

    total_value = sum(d["市值"] for d in details)
    total_cost = sum(s["weight"] * s["cost"] for s in stocks)
    total_return = (total_value / total_cost - 1) * 100 if total_cost > 0 else 0

    # 组合波动率（加权协方差）
    if len(daily_rets) > 1 and all(len(r) > 0 for r in daily_rets):
        min_len = min(len(r) for r in daily_rets)
        aligned = np.array([r.tail(min_len).values for r in daily_rets])
        cov = np.cov(aligned)
        w = np.array(weights)
        port_vol = np.sqrt(w @ cov @ w.T) * np.sqrt(252) * 100
        port_sharpe = (total_return / 100 - 0.03) / (port_vol / 100) if port_vol > 0 else 0
    else:
        port_vol = None
        port_sharpe = None

    # 贡献度
    total_ret_decimal = total_value / total_cost - 1
    for d, s in zip(details, stocks):
        d["贡献度%"] = round(((s["weight"] * (d["现价"] / s["cost"] - 1)) / total_ret_decimal) * 100, 1) if total_ret_decimal != 0 else 0

    return {
        "name": portfolio["name"],
        "total_value": round(total_value, 2),
        "total_cost": round(total_cost, 2),
        "total_return_pct": round(total_return, 2),
        "portfolio_volatility_pct": round(port_vol, 2) if port_vol else None,
        "portfolio_sharpe": round(port_sharpe, 3) if port_sharpe else None,
        "stock_count": len(stocks),
        "stocks": details,
    }


def rebalance(portfolio, target_weights):
    """调仓建议：target_weights = {code: weight}"""
    current = analyze_portfolio(portfolio)
    suggestions = []
    for s in current["stocks"]:
        code = s["代码"]
        current_w = s["仓位%"]
        target_w = target_weights.get(code, 0) * 100
        diff = target_w - current_w
        if abs(diff) > 5:
            suggestions.append({
                "代码": code,
                "当前仓位%": current_w,
                "目标仓位%": target_w,
                "调整": f"{'加仓' if diff > 0 else '减仓'} {abs(diff):.0f}%",
            })
    return suggestions
```

- [ ] **Step 2: 验证组合创建与分析**

```bash
cd D:\CC\5.23 && python -c "
import sys, io; sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from stock_analyzer.portfolio import create_portfolio, analyze_portfolio, list_portfolios

p = create_portfolio('测试组合', [
    {'code': '300408', 'weight': 0.4, 'cost': 100.0},
    {'code': '603005', 'weight': 0.3, 'cost': 35.0},
    {'code': '600519', 'weight': 0.3, 'cost': 1500.0},
])
print(f'组合已创建: {p[\"name\"]}')

r = analyze_portfolio(p)
print(f'总市值: {r[\"total_value\"]}  总收益: {r[\"total_return_pct\"]}%')
print(f'组合波动: {r[\"portfolio_volatility_pct\"]}%  夏普: {r[\"portfolio_sharpe\"]}')
for s in r['stocks']:
    print(f'  {s[\"代码\"]} 仓位:{s[\"仓位%\"]}% 收益:{s[\"收益率%\"]}% 贡献:{s[\"贡献度%\"]}%')
"
```


### Task 4: 价格预警 `stock_analyzer/alert.py`

**Files:**
- Create: `D:\CC\5.23\stock_analyzer\alert.py`

四种预警类型：价格、放量、技术指标、基本面。

- [ ] **Step 1: 创建 alert.py**

```python
"""价格预警系统：条件检查 + 触发通知"""
import json
import os
from datetime import datetime
from .cache import cached_kline, cached_fundamentals
from .analysis import full_technical_analysis, get_technical_summary

ALERTS_FILE = "D:/CC/5.23/alerts.json"
LOG_FILE = "D:/CC/5.23/alerts_log.txt"


def _load():
    if not os.path.exists(ALERTS_FILE):
        return []
    with open(ALERTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save(alerts):
    with open(ALERTS_FILE, "w", encoding="utf-8") as f:
        json.dump(alerts, f, ensure_ascii=False, indent=2)


def _log(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {msg}\n")
    print(msg)


def add_alert(config):
    """添加预警规则"""
    alerts = _load()
    config["id"] = len(alerts) + 1
    config["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    alerts.append(config)
    _save(alerts)
    return config["id"]


def remove_alert(alert_id):
    alerts = [a for a in _load() if a["id"] != alert_id]
    _save(alerts)


def load_alerts():
    return _load()


def check_alerts(alert_list):
    """检查一组预警"""
    triggered = []
    for alert in alert_list:
        code = alert["code"]
        try:
            kline = cached_kline(code, days=60)
            if kline.empty:
                continue
            kline = full_technical_analysis(kline)
            last = kline.iloc[-1]
            close = last["收盘"]

            if alert["type"] == "price":
                target = alert["target"]
                if alert["direction"] == "above" and close > target:
                    triggered.append(f"{code} 价格 {close:.2f} 突破 {target:.2f} ↑")
                elif alert["direction"] == "below" and close < target:
                    triggered.append(f"{code} 价格 {close:.2f} 跌破 {target:.2f} ↓")

            elif alert["type"] == "volume":
                avg_vol = kline["成交量"].tail(20).mean()
                if avg_vol > 0 and last["成交量"] > avg_vol * alert["multiplier"]:
                    triggered.append(f"{code} 放量 {last['成交量']:.0f} > {alert['multiplier']}倍均值 {avg_vol:.0f}")

            elif alert["type"] == "technical":
                tech = get_technical_summary(kline)
                if alert["indicator"] == "RSI":
                    rsi = tech["RSI"]["值"]
                    if alert["condition"] == ">80" and rsi and rsi > 80:
                        triggered.append(f"{code} RSI={rsi:.1f} 超买")
                    elif alert["condition"] == "<20" and rsi and rsi < 20:
                        triggered.append(f"{code} RSI={rsi:.1f} 超卖")
                elif alert["indicator"] == "MACD" and alert["condition"] == "金叉":
                    if tech["MACD"]["信号"] == "金叉":
                        triggered.append(f"{code} MACD金叉")
                elif alert["indicator"] == "MACD" and alert["condition"] == "死叉":
                    if tech["MACD"]["信号"] == "死叉":
                        triggered.append(f"{code} MACD死叉")

            elif alert["type"] == "fundamental":
                funda = cached_fundamentals(code)
                val = funda.get(alert["metric"])
                if val is not None:
                    threshold = float(alert["condition"].replace("<", "").replace(">", ""))
                    if "<" in alert["condition"] and val < threshold:
                        triggered.append(f"{code} {alert['metric']}={val} 低于{threshold}")
                    elif ">" in alert["condition"] and val > threshold:
                        triggered.append(f"{code} {alert['metric']}={val} 高于{threshold}")
        except Exception:
            pass
    return triggered


def run_all_alerts():
    """检查所有预警规则"""
    alerts = _load()
    triggered = check_alerts(alerts)
    if triggered:
        _log(f"触发了 {len(triggered)} 条预警:")
        for t in triggered:
            _log(f"  ⚠ {t}")
    else:
        print(f"[{datetime.now().strftime('%H:%M')}] 无预警触发")
    return triggered
```

- [ ] **Step 2: 验证预警系统**

```bash
cd D:\CC\5.23 && python -c "
import sys, io; sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from stock_analyzer.alert import add_alert, run_all_alerts, load_alerts, remove_alert

# 添加几条测试预警
add_alert({'type':'technical', 'code':'300408', 'indicator':'RSI', 'condition':'>80'})
add_alert({'type':'price', 'code':'300408', 'direction':'below', 'target':100})
add_alert({'type':'technical', 'code':'603005', 'indicator':'MACD', 'condition':'金叉'})
print(f'已添加 3 条预警')

run_all_alerts()
"
```


### Task 5: HTML 报告 `stock_analyzer/report_html.py`

**Files:**
- Create: `D:\CC\5.23\stock_analyzer\report_html.py`

Chart.js CDN + 纯 HTML 模板，输出交互式报告。

- [ ] **Step 1: 创建 report_html.py**

```python
"""HTML 报告生成器 — Chart.js 交互式报告"""
import os
import json
from datetime import datetime

CHART_JS = "https://cdn.jsdelivr.net/npm/chart.js@4"


def _header(title):
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<script src="{CHART_JS}"></script>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; font-family:-apple-system,sans-serif; }}
  body {{ background:#f5f6fa; padding:20px; }}
  .container {{ max-width:1200px; margin:0 auto; }}
  .card {{ background:#fff; border-radius:12px; padding:20px; margin-bottom:20px; box-shadow:0 2px 8px rgba(0,0,0,.08); }}
  .card h2 {{ color:#2d3436; margin-bottom:16px; font-size:18px; border-left:4px solid #0984e3; padding-left:12px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; }}
  .stat {{ text-align:center; padding:16px; background:#f8f9fa; border-radius:8px; }}
  .stat .value {{ font-size:28px; font-weight:700; color:#2d3436; }}
  .stat .label {{ font-size:13px; color:#636e72; margin-top:4px; }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  th,td {{ padding:10px 12px; text-align:left; border-bottom:1px solid #eee; }}
  th {{ background:#f8f9fa; font-weight:600; color:#636e72; }}
  .buy {{ color:#00b894; font-weight:600; }} .sell {{ color:#d63031; font-weight:600; }}
  .hold {{ color:#fdcb6e; font-weight:600; }} .strong-buy {{ color:#00b894; }} .strong-sell {{ color:#d63031; }}
  .chart-container {{ position:relative; height:300px; }}
</style></head><body><div class="container">"""


def _footer():
    return f"""<div class="card" style="text-align:center;color:#636e72;font-size:12px;">
  <p>报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
  <p>⚠ 以上分析仅供参考，不构成投资建议</p>
</div></div></body></html>"""


def _radar_chart(canvas_id, stock_details):
    """生成五维评分雷达图 JS"""
    labels = ["动量", "技术", "基本面", "量能", "风险"]
    datasets = []
    colors = ["#0984e3", "#00b894", "#d63031", "#fdcb6e", "#6c5ce7"]
    for i, sd in enumerate(stock_details[:5]):
        datasets.append({
            "label": sd.get("代码", f"股票{i+1}"),
            "data": [sd.get("动量分", 50), sd.get("技术分", 50), sd.get("基本面分", 50),
                     sd.get("量能分", 50), sd.get("风险分", 50)],
            "borderColor": colors[i % len(colors)],
            "backgroundColor": colors[i % len(colors)].replace(")", ",0.1)"),
            "pointRadius": 3,
        })
    return f"""new Chart(document.getElementById('{canvas_id}'), {{
    type:'radar',
    data:{{labels:{json.dumps(labels,ensure_ascii=False)},datasets:{json.dumps(datasets,ensure_ascii=False)}}},
    options:{{scales:{{r:{{min:0,max:100,ticks:{{stepSize:20}}}}}}}}
  }});"""


def generate_screener_report(screener_result, output_path=None):
    """生成选股结果报告"""
    if output_path is None:
        os.makedirs("D:/CC/5.23/reports", exist_ok=True)
        output_path = f"D:/CC/5.23/reports/screener_{datetime.now().strftime('%Y%m%d_%H%M')}.html"

    stock_list = screener_result.to_dict("records") if hasattr(screener_result, "to_dict") else screener_result
    rows = ""
    for s in stock_list:
        rating = s.get("评级", "")
        cls = {"Strong Buy": "strong-buy", "Buy": "buy", "Hold": "hold", "Sell": "sell", "Strong Sell": "strong-sell"}.get(rating, "")
        score = s.get("综合评分", 0)
        chg = s.get("涨跌幅", 0)
        chg_cls = "buy" if chg >= 0 else "sell"
        rows += f"<tr><td>{s.get('代码','')}</td><td>{score}</td><td class='{cls}'>{rating}</td>" \
                f"<td>{s.get('动量分',0)}</td><td>{s.get('技术分',0)}</td><td>{s.get('基本面分',0)}</td>" \
                f"<td>{s.get('量能分',0)}</td><td>{s.get('风险分',0)}</td>" \
                f"<td>{s.get('最新价',0)}</td><td class='{chg_cls}'>{chg:+.2f}%</td></tr>"

    html = _header("每日选股池报告")
    html += f"""<div class="card"><h2>📊 选股结果 TOP {len(stock_list)}</h2>
    <table><thead><tr><th>代码</th><th>综合评分</th><th>评级</th><th>动量</th><th>技术</th><th>基本面</th><th>量能</th><th>风险</th><th>最新价</th><th>涨跌幅</th></tr></thead><tbody>{rows}</tbody></table></div>"""
    html += f"""<div class="card"><h2>🎯 五维评分雷达图</h2><div class="chart-container"><canvas id="radarChart"></canvas></div></div>"""
    html += _footer()
    html += f"<script>{_radar_chart('radarChart', stock_list)}</script>"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path


def generate_portfolio_report(portfolio_analysis, output_path=None):
    """生成组合报告"""
    if output_path is None:
        os.makedirs("D:/CC/5.23/reports", exist_ok=True)
        output_path = f"D:/CC/5.23/reports/portfolio_{datetime.now().strftime('%Y%m%d_%H%M')}.html"

    pa = portfolio_analysis
    stocks = pa.get("stocks", [])

    stat_html = f"""
    <div class="grid">
      <div class="stat"><div class="value">{pa.get('total_value',0):.0f}</div><div class="label">总市值</div></div>
      <div class="stat"><div class="value" style="color:{'#00b894' if pa.get('total_return_pct',0)>=0 else '#d63031'}">{pa.get('total_return_pct',0):+.1f}%</div><div class="label">总收益</div></div>
      <div class="stat"><div class="value">{pa.get('portfolio_volatility_pct','-')}</div><div class="label">组合波动率%</div></div>
      <div class="stat"><div class="value">{pa.get('portfolio_sharpe','-')}</div><div class="label">夏普比率</div></div>
      <div class="stat"><div class="value">{pa.get('stock_count',0)}</div><div class="label">持股数</div></div>
    </div>"""

    rows = ""
    for s in stocks:
        ret = s.get("收益率%", 0)
        contrib = s.get("贡献度%", 0)
        rows += f"<tr><td>{s.get('代码','')}</td><td>{s.get('仓位%',0):.1f}%</td><td>{s.get('成本价',0)}</td><td>{s.get('现价',0)}</td><td style='color:{'#00b894' if ret>=0 else '#d63031'}'>{ret:+.2f}%</td><td>{contrib:.1f}%</td></tr>"

    html = _header(f"组合报告 - {pa.get('name','')}")
    html += f"""<div class="card"><h2>📈 {pa.get('name','投资组合')}</h2>{stat_html}</div>"""
    html += f"""<div class="card"><h2>持仓明细</h2><table><thead><tr><th>代码</th><th>仓位</th><th>成本价</th><th>现价</th><th>收益率</th><th>贡献度</th></tr></thead><tbody>{rows}</tbody></table></div>"""
    html += _footer()

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path
```

- [ ] **Step 2: 验证 HTML 报告生成**

```bash
cd D:\CC\5.23 && python -c "
import sys, io; sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import pandas as pd
from stock_analyzer.report_html import generate_screener_report

# 模拟选股结果
data = pd.DataFrame([
    {'代码':'300408','综合评分':79,'评级':'Buy','动量分':100,'技术分':66.5,'基本面分':75,'量能分':85,'风险分':64,'最新价':115,'涨跌幅':16.79},
    {'代码':'603005','综合评分':72.3,'评级':'Buy','动量分':89.2,'技术分':66.5,'基本面分':55,'量能分':85,'风险分':64,'最新价':39.14,'涨跌幅':8.48},
])
path = generate_screener_report(data)
print(f'报告已生成: {path}')
"
```


### Task 6: 单元测试

**Files:**
- Create: `D:\CC\5.23\stock_analyzer\test_cache.py`
- Create: `D:\CC\5.23\stock_analyzer\test_analysis.py`
- Create: `D:\CC\5.23\stock_analyzer\test_quant.py`

- [ ] **Step 1: 创建 test_cache.py**

```python
"""测试数据缓存"""
import unittest
import tempfile
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stock_analyzer.cache import cache_set, cache_get, cache_clear, cache_clear_all
import time


class TestCache(unittest.TestCase):
    def setUp(self):
        cache_clear_all()

    def test_set_get(self):
        cache_set("a", {"key": "value"}, ttl=60)
        self.assertEqual(cache_get("a"), {"key": "value"})

    def test_get_nonexistent(self):
        self.assertIsNone(cache_get("nonexistent"))

    def test_expiry(self):
        cache_set("b", "data", ttl=1)
        self.assertEqual(cache_get("b"), "data")
        time.sleep(1.5)
        self.assertIsNone(cache_get("b"))

    def test_clear(self):
        cache_set("c", "data", ttl=60)
        cache_clear("c")
        self.assertIsNone(cache_get("c"))

    def test_clear_all(self):
        cache_set("d", 1, ttl=60)
        cache_set("e", 2, ttl=60)
        cache_clear_all()
        self.assertIsNone(cache_get("d"))
        self.assertIsNone(cache_get("e"))

    def test_overwrite(self):
        cache_set("f", "old", ttl=60)
        cache_set("f", "new", ttl=60)
        self.assertEqual(cache_get("f"), "new")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 创建 test_analysis.py**

```python
"""测试技术分析指标"""
import unittest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pandas as pd
import numpy as np
from stock_analyzer.analysis import (
    calc_ma, calc_macd, calc_rsi, calc_kdj,
    calc_atr, calc_bollinger, calc_adx,
    full_technical_analysis,
)


def _make_df(rows=100):
    np.random.seed(42)
    close = 50 + np.cumsum(np.random.randn(rows) * 0.5)
    df = pd.DataFrame({
        "日期": pd.date_range("2025-01-01", periods=rows),
        "开盘": close * 0.99,
        "收盘": close,
        "最高": close * 1.02,
        "最低": close * 0.98,
        "成交量": np.random.randint(1000000, 10000000, rows),
    })
    return df


class TestAnalysis(unittest.TestCase):
    def test_empty_df(self):
        empty = pd.DataFrame()
        self.assertTrue(calc_ma(empty).empty)
        self.assertTrue(calc_macd(empty).empty)

    def test_ma_calculation(self):
        df = full_technical_analysis(_make_df(30))
        self.assertIn("MA5", df.columns)
        self.assertIn("MA20", df.columns)
        self.assertFalse(df["MA5"].isna().all())

    def test_macd_columns(self):
        df = full_technical_analysis(_make_df(60))
        for col in ["DIF", "DEA", "MACD"]:
            self.assertIn(col, df.columns)

    def test_rsi_range(self):
        df = full_technical_analysis(_make_df(50))
        rsi = df["RSI"].dropna()
        self.assertTrue((rsi >= 0).all())
        self.assertTrue((rsi <= 100).all())

    def test_bollinger(self):
        df = full_technical_analysis(_make_df(50))
        self.assertIn("BB_UPPER", df.columns)
        self.assertIn("BB_LOWER", df.columns)
        last = df.iloc[-1]
        self.assertGreaterEqual(last["BB_UPPER"], last["BB_LOWER"])

    def test_adx(self):
        df = full_technical_analysis(_make_df(50))
        self.assertIn("ADX", df.columns)
        self.assertIn("DI_PLUS", df.columns)
        self.assertIn("DI_MINUS", df.columns)

    def test_kdj(self):
        df = full_technical_analysis(_make_df(50))
        for col in ["K", "D", "J"]:
            self.assertIn(col, df.columns)

    def test_atr(self):
        df = full_technical_analysis(_make_df(50))
        atr = df["ATR"].dropna()
        self.assertGreater(atr.iloc[-1], 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: 创建 test_quant.py**

```python
"""测试量化分析模块"""
import unittest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pandas as pd
import numpy as np
from stock_analyzer.analysis import full_technical_analysis
from stock_analyzer.quant import (
    calc_risk_metrics, composite_quant_score,
    generate_all_signals, consolidate_signals,
    backtest_ma_crossover,
)


def _make_df(rows=120):
    np.random.seed(42)
    close = 50 + np.cumsum(np.random.randn(rows) * 0.5)
    df = pd.DataFrame({
        "日期": pd.date_range("2025-01-01", periods=rows),
        "开盘": close * 0.99,
        "收盘": close,
        "最高": close * 1.02,
        "最低": close * 0.98,
        "成交量": np.random.randint(1000000, 10000000, rows),
    })
    df["涨跌幅"] = df["收盘"].pct_change() * 100
    return full_technical_analysis(df)


class TestQuant(unittest.TestCase):
    def setUp(self):
        self.df = _make_df()

    def test_risk_metrics(self):
        risk = calc_risk_metrics(self.df)
        self.assertIsNotNone(risk["sharpe_ratio"])
        self.assertIsNotNone(risk["max_drawdown_pct"])
        self.assertIn("VaR_95_pct", risk)

    def test_risk_metrics_empty(self):
        risk = calc_risk_metrics(pd.DataFrame())
        self.assertIsNone(risk["sharpe_ratio"])

    def test_composite_score(self):
        score = composite_quant_score(self.df)
        self.assertGreaterEqual(score["composite_score"], 0)
        self.assertLessEqual(score["composite_score"], 100)
        self.assertIn(score["rating"], ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"])

    def test_composite_score_with_funda(self):
        funda = {"ROE": 12.5, "营收增长": 0.25, "净利润增长": 0.3, "毛利率": 0.5}
        score = composite_quant_score(self.df, funda)
        self.assertGreaterEqual(score["composite_score"], 0)

    def test_signals(self):
        sigs = generate_all_signals(self.df)
        cons = consolidate_signals(sigs)
        self.assertIn(cons["bias"], ["strong_bullish", "bullish", "neutral", "bearish", "strong_bearish"])
        self.assertIsNotNone(cons["net_score"])

    def test_backtest(self):
        result = backtest_ma_crossover(self.df, initial_capital=10000)
        self.assertGreater(result["summary"]["total_trades"], 0)
        self.assertGreater(len(result["trades"]), 0)
        self.assertGreater(len(result["equity_curve"]), 0)

    def test_backtest_edge(self):
        result = backtest_ma_crossover(_make_df(5), initial_capital=10000)
        self.assertEqual(len(result["trades"]), 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: 运行全部测试**

```bash
cd D:\CC\5.23 && python -m unittest discover -s stock_analyzer -p "test_*.py" -v
```


### Task 7: 更新 SKILL.md

**Files:**
- Modify: `C:\Users\47535\.claude\skills\stock-quant-analysis\SKILL.md`

- [ ] **Step 1: 更新 description，新增缓存/选股池/组合/预警/报告描述**

```markdown
description: A股全链路量化投资分析平台。板块排名、K线技术指标(MA/MACD/RSI/KDJ/布林带/ADX/ATR)、基本面评分、量化多因子评分、风险指标(夏普/回撤/VaR)、量化交易信号(趋势/突破/均值回归)、策略回测(MA金叉死叉)、SQLite数据缓存、全市场每日选股池、投资组合管理(整体收益/波动率/夏普/贡献度)、价格预警(价格/放量/技术指标/基本面)、Chart.js交互式HTML报告。数据源：东方财富/新浪财经/akshare。
```

- [ ] **Step 2: 在使用方式中加入新模块的用法示例**

在 SKILL.md 的使用方式部分增加：
```python
from stock_analyzer.cache import cached_kline
from stock_analyzer.screener import run_screener
from stock_analyzer.portfolio import create_portfolio, analyze_portfolio
from stock_analyzer.alert import add_alert, run_all_alerts
from stock_analyzer.report_html import generate_screener_report, generate_portfolio_report

# 选股池
df = run_screener(top_n=20)

# 组合分析
p = create_portfolio("我的组合", [{"code":"300408","weight":0.5,"cost":100}])
r = analyze_portfolio(p)

# 预警
add_alert({"type":"price","code":"300408","direction":"above","target":120})
run_all_alerts()

# HTML报告
generate_screener_report(df)
```
