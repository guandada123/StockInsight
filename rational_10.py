#!/usr/bin/env python
"""理性重选 — 长线5只 + 短线5只（不追高，不盲目）
复用 cli.deep_analyze，不再重复实现分析逻辑。
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import numpy as np
import pandas as pd

from stock_analyzer.analyzer import deep_analyze
from stock_analyzer.report_html import generate_screener_report
from stock_analyzer.sectors_fallback import get_sector_for_code

# ============================================================
# 读取全市场数据
# ============================================================
CSV_PATH = "full_scan_results.csv"

if not os.path.exists(CSV_PATH):
    print(f"❌ 找不到全市场扫描结果文件: {CSV_PATH}")
    print("   请先运行: python run_full_scan.py")
    print(f"   扫描完成后会在当前目录生成 {CSV_PATH}")
    sys.exit(1)

try:
    df_all = pd.read_csv(CSV_PATH, encoding="utf-8-sig")
except Exception as e:
    print(f"❌ 读取 {CSV_PATH} 失败: {e}")
    print("   文件可能已损坏，请重新运行: python run_full_scan.py")
    sys.exit(1)

if len(df_all) == 0:
    print(f"⚠️ {CSV_PATH} 为空，无股票数据可分析。请先运行: python run_full_scan.py")
    sys.exit(0)

required_cols = ["综合评分", "代码", "名称"]
missing = [c for c in required_cols if c not in df_all.columns]
if missing:
    print(f"❌ {CSV_PATH} 缺少必要列: {missing}")
    print(f"   现有列: {list(df_all.columns)}")
    sys.exit(1)

print(f"全市场评分: {len(df_all)} 只\n")

# ============================================================
# PART A: 长线选股
# ============================================================
print("=" * 70)
print("PART A: 长线5只 — 重基本面+低波动+不追高")
print("=" * 70)

long_c = (
    df_all[
        (df_all["综合评分"] >= 60)
        & (df_all["基本面分"] >= 65)
        & (df_all["风险分"] >= 55)
        & (df_all["动量分"] < 95)
        & (df_all["技术分"] >= 50)
    ]
    .copy()
    .sort_values("综合评分", ascending=False)
)

print(f"长线候选: {len(long_c)} 只 (综合≥60,基本面≥65,风险≥55,动量<95)")

print("深度分析TOP25...")
long_results = []
for i, (_, row) in enumerate(long_c.head(25).iterrows()):
    code = str(row["代码"]).zfill(6)
    name = row["名称"]
    r = deep_analyze(code, days=365, skip_nt=False)
    if r is None:
        continue
    r["name"] = name
    r["sector"] = get_sector_for_code(code)
    r["scan_score"] = row["综合评分"]

    # 长线综合 = 长线×0.35 + 基本面×0.25 + 风险×0.2 + 夏普归一化×0.1 + 国家队×0.1
    nt_bonus = 10 if r["has_nt"] else 0
    sharpe_norm = min(r["sharpe"], 4) / 4 * 100
    r["long_composite"] = (
        r["long_score"] * 0.35
        + r["fund_s"] * 0.25
        + r["risk_s"] * 0.20
        + sharpe_norm * 0.10
        + nt_bonus * 0.10
    )

    # 追高/过热惩罚
    penalty, reasons = 0, []
    if r["near_20d"] > 30:
        penalty += 10
        reasons.append(f"近20日涨{r['near_20d']:.0f}%")
    elif r["near_20d"] > 25:
        penalty += 5
        reasons.append(f"近20日涨{r['near_20d']:.0f}%")
    if r["rsi"] > 75:
        penalty += 8
        reasons.append(f"RSI={r['rsi']:.0f}过热")
    elif r["rsi"] > 72:
        penalty += 4
        reasons.append(f"RSI={r['rsi']:.0f}偏高")
    if r["max_dd"] < -35:
        penalty += 5
        reasons.append(f"回撤{r['max_dd']:.0f}%过大")
    if r["roe"] < 0:
        penalty += 10
        reasons.append("ROE为负")
    r["penalty"] = penalty
    r["penalty_reasons"] = reasons
    r["long_final"] = r["long_composite"] - penalty

    long_results.append(r)
    print(
        f"  [{len(long_results):2d}] {code} {name:<8s} 长线综合:{r['long_composite']:.1f} "
        f"惩罚:{penalty} 最终:{r['long_final']:.1f} "
        f"长线分:{r['long_score']:.0f} 基本面:{r['fund_s']:.0f} "
        f"近20日:{r['near_20d']:+.1f}% RSI:{r['rsi']:.0f} ROE:{r['roe']:.1f}%"
        + (f" {'🏛️' if r['has_nt'] else ''} {'⚠️' + ','.join(reasons) if reasons else '✅'}")
    )

long_results.sort(key=lambda x: x["long_final"], reverse=True)
long_top5 = long_results[:5]

print(f"\n{'=' * 50}")
print("长线精选5只:")
print(
    f"{'排名':<5} {'代码':<8} {'名称':<10} {'长线最终':<10} {'长线分':<8} {'基本面':<8} {'夏普':<8} {'回撤':<8} {'近20日':<10} {'RSI':<6}"
)
print("-" * 90)
for i, r in enumerate(long_top5):
    print(
        f"{i + 1:<5} {r['code']:<8} {r['name']:<10} {r['long_final']:<10.1f} "
        f"{r['long_score']:<8.0f} {r['fund_s']:<8.0f} {r['sharpe']:<8.2f} "
        f"{r['max_dd']:<8.1f}% {r['near_20d']:<+10.1f}% {r['rsi']:<6.0f} "
        f"{'🏛️' if r['has_nt'] else ''}"
    )

# ============================================================
# PART B: 短线选股
# ============================================================
print("\n\n" + "=" * 70)
print("PART B: 短线5只 — 动量+技术+量能，但不追高不接盘")
print("=" * 70)

short_c = (
    df_all[
        (df_all["综合评分"] >= 60)
        & (df_all["动量分"] >= 70)
        & (df_all["动量分"] < 95)
        & (df_all["技术分"] >= 65)
        & (df_all["量能分"] >= 60)
        & (df_all["风险分"] >= 50)
    ]
    .copy()
    .sort_values("综合评分", ascending=False)
)

print(f"短线候选: {len(short_c)} 只 (综合≥60,动量70-94,技术≥65,量能≥60)")

print("深度分析TOP25...")
short_results = []
for i, (_, row) in enumerate(short_c.head(25).iterrows()):
    code = str(row["代码"]).zfill(6)
    name = row["名称"]
    r = deep_analyze(code, days=120, skip_nt=False)
    if r is None:
        continue
    r["name"] = name
    r["sector"] = get_sector_for_code(code)
    r["scan_score"] = row["综合评分"]

    # 短线综合 = 短线×0.35 + 动量×0.25 + 技术×0.2 + 量能×0.2
    r["short_composite"] = (
        r["short_score"] * 0.35 + r["mom_s"] * 0.25 + r["tech_s"] * 0.20 + r["vol_s"] * 0.20
    )

    penalty, reasons = 0, []
    if r["near_5d"] > 15:
        penalty += 8
        reasons.append(f"近5日涨{r['near_5d']:.0f}%")
    elif r["near_5d"] > 12:
        penalty += 3
        reasons.append(f"近5日涨{r['near_5d']:.0f}%")
    if r["near_20d"] > 30:
        penalty += 10
        reasons.append(f"近20日涨{r['near_20d']:.0f}%")
    elif r["near_20d"] > 25:
        penalty += 6
        reasons.append(f"近20日涨{r['near_20d']:.0f}%")
    elif r["near_20d"] > 20:
        penalty += 2
    if r["rsi"] > 75:
        penalty += 10
        reasons.append(f"RSI={r['rsi']:.0f}过热")
    elif r["rsi"] > 72:
        penalty += 5
        reasons.append(f"RSI={r['rsi']:.0f}偏高")
    if r["signal_bias"] in ("bearish", "strong_bearish"):
        penalty += 8
        reasons.append(f"信号{r['signal_bias']}")
    r["penalty"] = penalty
    r["penalty_reasons"] = reasons
    r["short_final"] = r["short_composite"] - penalty

    short_results.append(r)
    print(
        f"  [{len(short_results):2d}] {code} {name:<8s} 短线综合:{r['short_composite']:.1f} "
        f"惩罚:{penalty} 最终:{r['short_final']:.1f} "
        f"短线分:{r['short_score']:.0f} 动量:{r['mom_s']:.0f} 技术:{r['tech_s']:.0f} 量能:{r['vol_s']:.0f} "
        f"近5日:{r['near_5d']:+.1f}% 近20日:{r['near_20d']:+.1f}% RSI:{r['rsi']:.0f}"
        + (f" {'⚠️' + ','.join(reasons) if reasons else '✅'}")
    )

short_results.sort(key=lambda x: x["short_final"], reverse=True)
short_top5 = short_results[:5]

print(f"\n{'=' * 50}")
print("短线精选5只:")
print(
    f"{'排名':<5} {'代码':<8} {'名称':<10} {'短线最终':<10} {'短线分':<8} {'动量':<6} {'技术':<6} {'量能':<6} {'近5日':<8} {'近20日':<10} {'RSI':<6}"
)
print("-" * 90)
for i, r in enumerate(short_top5):
    print(
        f"{i + 1:<5} {r['code']:<8} {r['name']:<10} {r['short_final']:<10.1f} "
        f"{r['short_score']:<8.0f} {r['mom_s']:<6.0f} {r['tech_s']:<6.0f} {r['vol_s']:<6.0f} "
        f"{r['near_5d']:<+8.1f}% {r['near_20d']:<+10.1f}% {r['rsi']:<6.0f}"
    )


# ============================================================
# 生成两份HTML报告
# ============================================================
def gen_report(picks, output_path, label):
    rows = []
    details = {}
    for r in picks:
        rows.append(
            {
                "代码": r["code"],
                "名称": r["name"],
                "综合评分": r["qs_composite"],
                "评级": r["qs_rating"],
                "动量分": r["mom_s"],
                "技术分": r["tech_s"],
                "基本面分": r["fund_s"],
                "量能分": r["vol_s"],
                "风险分": r["risk_s"],
                "最新价": r["price"],
                "涨跌幅": r["near_5d"],
            }
        )
        details[r["code"]] = {
            "name": r["name"],
            "sector": r["sector"],
            "quant_score": r["quant_score"],
            "support_resistance": r["support_resistance"],
            "stop_levels": r["stop_levels"],
            "technical_summary": r["technical_summary"],
            "risk_metrics": r["risk_metrics"],
            "signals": r["signals"],
            "trading_style": r["trading_style"],
            "fundamental_score": r["fund_score"],
            "fundamentals": r["fundamentals"],
            "fund_flow": {},
            "national_team": {"has_national_team": r["has_nt"], "holders": r["nt_holders"]},
            "near_5d_pct": r["near_5d"],
            "near_20d_pct": r["near_20d"],
        }
    df = pd.DataFrame(rows)
    for c in ["综合评分", "动量分", "技术分", "基本面分", "量能分", "风险分", "最新价", "涨跌幅"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    path = generate_screener_report(df, output_path=output_path, stock_details=details)
    print(f"  {label}报告: {path}")
    return path


print(f"\n{'=' * 70}")
print("生成HTML报告...")
gen_report(long_top5, "reports/rational_long_5_20260525.html", "长线5只")
gen_report(short_top5, "reports/rational_short_5_20260525.html", "短线5只")


# 保存JSON
def convert(obj):
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd.Timestamp):
        return str(obj)
    return obj


for name, data in [("long", long_top5), ("short", short_top5)]:
    clean = []
    for r in data:
        c = {}
        for k, v in r.items():
            if k in (
                "quant_score",
                "technical_summary",
                "support_resistance",
                "stop_levels",
                "risk_metrics",
                "signals",
                "trading_style",
                "fundamentals",
                "_kline",
            ):
                continue
            try:
                c[k] = convert(v)
            except Exception:
                c[k] = str(v)
        clean.append(c)
    with open(f"rational_{name}_5.json", "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)

print("\nDONE! 长线5只 + 短线5只 全部完成")
