#!/usr/bin/env python
"""主板精选 — 不追高+全面优质，长线短线各选5只
复用 cli.deep_analyze，不再重复实现分析逻辑。
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import pandas as pd

from stock_analyzer.analyzer import deep_analyze
from stock_analyzer.sectors_fallback import get_sector_for_code

ALREADY_OWN = set()


def run(owned=None, top_n=10):
    """执行主板精选

    参数:
        owned: 已持仓代码集合
        top_n: 返回前N只
    """
    global ALREADY_OWN
    ALREADY_OWN = owned or set()

    # 读取数据，仅主板
    df_all = pd.read_csv("full_scan_results.csv")
    df_all["代码_str"] = df_all["代码"].astype(str).str.zfill(6)

    df_ok = df_all[
        (df_all["代码_str"].str.startswith("60") | df_all["代码_str"].str.startswith("00"))
        & (~df_all["代码_str"].isin(ALREADY_OWN))
    ].copy()
    print(f"主板可筛选: {len(df_ok)} 只")

    # 初筛
    candidates = (
        df_ok[
            (df_ok["综合评分"] >= 60)
            & (df_ok["基本面分"] >= 55)
            & (df_ok["技术分"] >= 55)
            & (df_ok["动量分"] < 92)
            & (df_ok["风险分"] >= 50)
        ]
        .copy()
        .sort_values("综合评分", ascending=False)
    )
    print(f"初筛候选: {len(candidates)} 只\n")

    # 深度分析 TOP40
    all_results = _analyze_batch(candidates.head(40))
    return _select_top(all_results, top_n)


def _analyze_batch(candidates):
    """批量深度分析"""
    all_results = []
    seen = set(ALREADY_OWN)

    for i, (_, row) in enumerate(candidates.iterrows()):
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

        # 长线综合
        nt_bonus = 10 if r["has_nt"] else 0
        sharpe_norm = min(r["sharpe"], 4) / 4 * 100
        r["long_composite"] = (
            r["long_score"] * 0.35
            + r["fund_s"] * 0.25
            + r["risk_s"] * 0.20
            + sharpe_norm * 0.10
            + nt_bonus * 0.10
        )

        # 长线惩罚
        lpen, lr = _calc_long_penalty(r)
        r["long_penalty"] = lpen
        r["long_final"] = r["long_composite"] - lpen
        r["penalty_reasons"] = lr

        # 短线分析(120天)
        try:
            if "_kline" in r and len(r["_kline"]) >= 120:
                kline_s = r["_kline"].tail(120)
            else:
                from stock_analyzer.analysis import full_technical_analysis
                from stock_analyzer.cache import cached_kline
                from stock_analyzer.quant import (
                    consolidate_signals,
                    evaluate_trading_style,
                    generate_all_signals,
                )

                kline_s = cached_kline(code, days=120)
                kline_s = full_technical_analysis(kline_s)
            sigs_s = consolidate_signals(generate_all_signals(kline_s))
            trading_s = evaluate_trading_style(kline_s, None, None)
            ts_s = trading_s if isinstance(trading_s, dict) else {}
            sigs_sd = sigs_s if isinstance(sigs_s, dict) else {}
            r["short_score_120"] = ts_s.get("short_term_score", r["short_score"])
            r["short_signal"] = sigs_sd.get("bias", r["signal_bias"])
        except Exception:
            r["short_score_120"] = r["short_score"]
            r["short_signal"] = r["signal_bias"]

        # 短线综合
        r["short_composite"] = (
            r["short_score_120"] * 0.35 + r["mom_s"] * 0.25 + r["tech_s"] * 0.20 + r["vol_s"] * 0.20
        )

        spen, sr_list = _calc_short_penalty(r)
        r["short_penalty"] = spen
        r["short_final"] = r["short_composite"] - spen - lpen * 0.5
        r["final_score"] = r["long_final"] * 0.6 + r["short_final"] * 0.4

        all_results.append(r)
        print(
            f"  [{len(all_results):2d}] {code} {name:<8s} {r['sector'][:6]:<6s} "
            f"价格:{r['price']:<8.2f} 长线:{r['long_final']:.1f} 短线:{r['short_final']:.1f} 综合:{r['final_score']:.1f} "
            f"近20日:{r['near_20d']:+.1f}% RSI:{r['rsi']:.0f} "
            f"基本面:{r['fund_s']:.0f} 夏普:{r['sharpe']:.2f} ROE:{r['roe']:.1f}% "
            f"{'🏛️' if r['has_nt'] else ''}"
            + (f" ⚠️{','.join(r['penalty_reasons'])}" if r["penalty_reasons"] else " ✅")
        )

    return all_results


def _calc_long_penalty(r):
    pen, reasons = 0, []
    if r["near_20d"] > 35:
        pen += 12
        reasons.append(f"近20日涨{r['near_20d']:.0f}%")
    elif r["near_20d"] > 30:
        pen += 8
        reasons.append(f"近20日涨{r['near_20d']:.0f}%")
    elif r["near_20d"] > 25:
        pen += 4
        reasons.append(f"近20日涨{r['near_20d']:.0f}%")
    if r["rsi"] > 78:
        pen += 10
        reasons.append(f"RSI={r['rsi']:.0f}过热")
    elif r["rsi"] > 75:
        pen += 6
        reasons.append(f"RSI={r['rsi']:.0f}过热")
    elif r["rsi"] > 72:
        pen += 3
        reasons.append(f"RSI={r['rsi']:.0f}偏高")
    if r["max_dd"] < -45:
        pen += 8
        reasons.append(f"回撤{r['max_dd']:.0f}%深")
    elif r["max_dd"] < -35:
        pen += 4
        reasons.append(f"回撤{r['max_dd']:.0f}%")
    if r["roe"] < 0:
        pen += 12
        reasons.append("ROE为负")
    elif r["roe"] < 1:
        pen += 5
        reasons.append(f"ROE仅{r['roe']:.1f}%")
    if r["macd_signal"] in ("死叉", "空头"):
        pen += 3
        reasons.append(f"MACD{r['macd_signal']}")
    return pen, reasons


def _calc_short_penalty(r):
    pen, reasons = 0, []
    if r["near_5d"] > 18:
        pen += 10
        reasons.append(f"近5日涨{r['near_5d']:.0f}%")
    elif r["near_5d"] > 15:
        pen += 5
        reasons.append(f"近5日涨{r['near_5d']:.0f}%")
    if r.get("short_signal") in ("bearish", "strong_bearish"):
        pen += 6
        reasons.append(f"信号{r['short_signal']}")
    return pen, reasons


def _select_top(all_results, top_n=10):
    all_results.sort(key=lambda x: x["final_score"], reverse=True)
    picked = []
    used_sectors = set()
    for r in all_results:
        sec = r["sector"]
        if len(picked) >= top_n:
            break
        if sec not in used_sectors or r["final_score"] > 60:
            picked.append(r)
            used_sectors.add(sec)
    return picked


# ── 直接运行 ──
if __name__ == "__main__":
    print("=" * 70)
    print("主板精选 (综合得分 = 长线×0.6 + 短线×0.4)")
    print("=" * 70)
    picked = run(top_n=10)

    print(
        f"\n{'排名':<5} {'代码':<8} {'名称':<10} {'板块':<8} {'价格':<8} {'综合':<8} {'长线':<8} {'短线':<8} {'近20日':<8} {'RSI':<6} {'基本面':<6} {'夏普':<6} {'ROE':<8} {'国家队'}"
    )
    print("-" * 115)
    for i, r in enumerate(picked):
        print(
            f"{i + 1:<5} {r['code']:<8} {r['name']:<10} {r['sector'][:6]:<8} "
            f"{r['price']:<8.2f} {r['final_score']:<8.1f} {r['long_final']:<8.1f} {r['short_final']:<8.1f} "
            f"{r['near_20d']:<+8.1f} {r['rsi']:<6.0f} {r['fund_s']:<6.0f} {r['sharpe']:<6.2f} "
            f"{r['roe']:<8.1f}% {'🏛️' if r['has_nt'] else '—'}"
        )

    # TOP5 详情
    print(f"\n{'=' * 70}")
    print("TOP5 详细分析")
    print("=" * 70)
    for i, r in enumerate(picked[:5]):
        print(f"\n{'─' * 60}")
        print(f"  #{i + 1} {r['code']} {r['name']} ({r['sector']})")
        print(f"{'─' * 60}")
        print(f"  价格: {r['price']:.2f}  |  综合得分: {r['final_score']:.1f}")
        print(f"  长线最终: {r['long_final']:.1f}  |  短线最终: {r['short_final']:.1f}")
        print(
            f"  近5日: {r['near_5d']:+.1f}%  |  近20日: {r['near_20d']:+.1f}%  |  RSI: {r['rsi']:.0f}"
        )
        print(f"  MACD: {r['macd_signal']}  |  KDJ: {r['kdj_signal']}")
        print(
            f"  动量{r['mom_s']:.0f} 技术{r['tech_s']:.0f} 基本面{r['fund_s']:.0f} 量能{r['vol_s']:.0f} 风险{r['risk_s']:.0f}"
        )
        print(f"  夏普: {r['sharpe']:.2f}  |  回撤: {r['max_dd']:.1f}%")
        print(f"  基本面评分: {r['fund_score']:.0f}  |  ROE: {r['roe']:.1f}%")
        print(
            f"  支撑: {[f'{x:.2f}' for x in r['support']]}  压力: {[f'{x:.2f}' for x in r['resistance']]}"
        )
        print(f"  止损: {r['stop_loss']:.2f}  止盈: {r['stop_profit']:.2f}")
        nt = f"🏛️ {', '.join(r['nt_holders'][:2])}" if r["has_nt"] else "—"
        print(f"  国家队: {nt}")
        if r.get("penalty_reasons"):
            print(f"  扣分: {' | '.join(r['penalty_reasons'])}")
        print(
            f"  风格: {r['style']}  |  短线{r.get('short_score_120', r['short_score']):.0f}分  |  长线{r['long_score']:.0f}分"
        )

    print(f"\n{'=' * 70}")
    print("DONE!")
