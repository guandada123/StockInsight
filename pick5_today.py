#!/usr/bin/env python
"""今日精选5只推荐 — 主板/低价/不追高/板块分散
复用 cli.deep_analyze，不再重复实现分析逻辑。
"""

import io
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from stock_analyzer.analyzer import deep_analyze
from stock_analyzer.sectors_fallback import get_sector_for_code

OWNED = {"601677", "002119", "600176", "603203"}
SEEN_SECTORS = {"铝材", "电子", "玻纤", "自动化"}

# 1. 从全市场扫描加载候选
df = pd.read_csv("full_scan_results.csv")
df["code_str"] = df["代码"].astype(str).str.zfill(6)

candidates = (
    df[
        (df["code_str"].str.startswith("60") | df["code_str"].str.startswith("00"))
        & (~df["code_str"].isin(OWNED))
        & (df["综合评分"] >= 65)
        & (df["基本面分"] >= 60)
        & (df["技术分"] >= 55)
        & (df["动量分"] < 90)
        & (df["风险分"] >= 50)
        & (df["最新价"] > 5)
        & (df["最新价"] < 100)
    ]
    .copy()
    .sort_values("综合评分", ascending=False)
)

print(f"初筛候选: {len(candidates)} 只 (主板/评分≥65/基本面≥60/价格5-100)")
print()

# 2. 深度分析 TOP30
print("深度分析 TOP30...")
results = []
seen = set(OWNED)

for i, (_, row) in enumerate(candidates.head(30).iterrows()):
    code = str(row["代码"]).zfill(6)
    if code in seen:
        continue
    seen.add(code)
    name = row["名称"]
    r = deep_analyze(code, days=365, skip_nt=False)
    if r is None:
        continue
    r["name"] = name
    r["sector"] = get_sector_for_code(code)
    r["scan_score"] = row["综合评分"]

    # 追高惩罚
    pen = 0
    if r["near_20d"] > 30:
        pen += 10
    elif r["near_20d"] > 25:
        pen += 5
    elif r["near_20d"] > 20:
        pen += 2
    if r["rsi"] > 75:
        pen += 8
    elif r["rsi"] > 72:
        pen += 4
    if r["macd_signal"] in ("死叉", "空头"):
        pen += 5
    if r["max_dd"] < -40:
        pen += 3
    r["penalty"] = pen
    r["final_score"] = r["qs_composite"] - pen
    results.append(r)
    print(
        f"  [{len(results)}] {code} {name}: 原始{r['qs_composite']:.0f} → 最终{r['final_score']:.1f} (扣{pen})"
    )

# 3. 板块分散选择（"其他"不算同一板块，已知板块最多2只）
results.sort(key=lambda x: x["final_score"], reverse=True)
picked = []
sector_count = {}
for r in results:
    if len(picked) >= 5:
        break
    sec = r["sector"]
    if sec != "其他":
        if sector_count.get(sec, 0) >= 2:
            continue
        if sec in SEEN_SECTORS and r["final_score"] < 65:
            continue
    picked.append(r)
    sector_count[sec] = sector_count.get(sec, 0) + 1

# 4. 输出
print(f"\n{'=' * 85}")
print("精选5只推荐 (股价<100 / 不追高 / 板块分散)")
print(f"{'=' * 85}")
print(
    f"{'#':<3} {'代码':<8} {'名称':<10} {'板块':<8} {'价格':<8} {'评分':<7} {'近20日':<8} {'RSI':<5} {'MACD':<6} {'夏普':<6} {'ROE':<7} {'国家队'}"
)
print("-" * 90)
for i, r in enumerate(picked):
    nt = "🏛️" if r["has_nt"] else ""
    print(
        f"{i + 1:<3} {r['code']:<8} {r['name']:<10} {r['sector'][:6]:<8} "
        f"{r['price']:<8.2f} {r['final_score']:<7.1f} {r['near_20d']:<+8.1f} "
        f"{r['rsi']:<5.0f} {r['macd_signal']:<6} {r['sharpe']:<6.2f} "
        f"{r['roe']:<7.1f}% {nt}"
    )

# 5. 每只详细
print(f"\n{'=' * 85}")
print("个股详解")
print(f"{'=' * 85}")
for i, r in enumerate(picked):
    print(f"\n{'--' * 35}")
    print(f"  #{i + 1} {r['code']} {r['name']} ({r['sector']})")
    print(f"{'--' * 35}")
    print(
        f"  价格: {r['price']:.2f} | 综合评分: {r['qs_composite']:.0f} → 最终: {r['final_score']:.1f}(追高扣{r['penalty']})"
    )
    print(f"  近5日: {r['near_5d']:+.1f}% | 近20日: {r['near_20d']:+.1f}% | RSI: {r['rsi']:.0f}")
    print(f"  MACD: {r['macd_signal']} | 夏普: {r['sharpe']:.2f} | 回撤: {r['max_dd']:.1f}%")
    print(
        f"  因子: 动量{r['mom_s']:.0f} 技术{r['tech_s']:.0f} 基本面{r['fund_s']:.0f} 量能{r['vol_s']:.0f} 风险{r['risk_s']:.0f}"
    )
    print(f"  风格: {r['style']} | 短线{r['short_score']:.0f}分 长线{r['long_score']:.0f}分")
    print(f"  ROE: {r['roe']:.1f}% | 基本面评分: {r['fund_score']:.0f}分")
    nt = f"🏛️ {', '.join(r['nt_holders'][:3])}" if r["has_nt"] else "无"
    print(f"  国家队: {nt}")
    print(f"  止损: {r['stop_loss']:.2f} | 止盈: {r['stop_profit']:.2f}")
    print(f"  支撑: {r['support']} | 压力: {r['resistance']}")

print(f"\n{'=' * 85}")
sectors_set = set(r["sector"] for r in picked)
print(f"板块分布: {len(picked)} 只 | 覆盖板块: {len(sectors_set)} 个")
print("⚠️ 以上分析基于历史数据，不构成投资建议。")
