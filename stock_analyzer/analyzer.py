"""个股深度分析引擎

将 CLI 层的 deep_analyze 移到这里供后端 API 复用，消除循环依赖。
"""

import numpy as np


def _merge_realtime_kline(kline, code):
    """将新浪实时行情合并到K线DataFrame末尾"""
    import pandas as pd

    from stock_analyzer.fetcher import sina_real_time

    try:
        rt = sina_real_time([code])
        if rt and code in rt:
            r = rt[code]
            today_open = float(r.get("open", 0) or 0)
            today_high = float(r.get("high", 0) or 0)
            today_low = float(r.get("low", 0) or 0)
            today_price = float(r.get("price", 0) or 0)
            today_vol = float(r.get("volume", 0) or 0)
            if today_open > 0 and today_price > 0:
                last_date = str(kline["日期"].iloc[-1])[:10]
                today_str = pd.Timestamp.now().strftime("%Y-%m-%d")
                if today_str > last_date:
                    new_row = pd.DataFrame(
                        [
                            {
                                "日期": pd.Timestamp(today_str),
                                "开盘": today_open,
                                "最高": today_high,
                                "最低": today_low,
                                "收盘": today_price,
                                "成交量": int(today_vol),
                                "成交额": 0,
                            }
                        ]
                    )
                    return pd.concat([kline, new_row], ignore_index=True)
    except Exception:
        pass
    return kline


def _check_national_team(code):
    """查询国家队持仓（社保/养老金/汇金）"""
    try:
        from stock_analyzer.cache import cached_national_team_holdings

        nt = cached_national_team_holdings(code)
        if nt and isinstance(nt, dict) and nt.get("has_national_team"):
            return True, nt.get("holders", [])
    except Exception:
        pass
    return False, []


def deep_analyze(code, days=365, skip_nt=False):
    """个股深度分析（单次调用，返回完整dict）"""
    import pandas as pd

    from stock_analyzer.analysis import (
        calc_stop_levels,
        calc_support_resistance,
        full_technical_analysis,
        get_technical_summary,
        score_fundamental,
    )
    from stock_analyzer.cache import cached_fundamentals, cached_kline
    from stock_analyzer.quant import (
        calc_risk_metrics,
        composite_quant_score,
        consolidate_signals,
        evaluate_trading_style,
        generate_all_signals,
    )

    kline = cached_kline(code, days=days)
    if len(kline) < 20:
        return None

    # Merge real-time data into K-line
    kline = _merge_realtime_kline(kline, code)

    kline = full_technical_analysis(kline)
    tech = get_technical_summary(kline)
    sr = calc_support_resistance(kline)

    price = float(kline.iloc[-1]["收盘"])
    atr = float(kline.iloc[-1].get("ATR", np.nan))
    if pd.isna(atr) or atr <= 0:
        atr = price * 0.03

    if not isinstance(sr, dict):
        sr = {"支撑位": [price * 0.9], "压力位": [price * 1.1]}
    sl = sr.get("支撑位", [price * 0.9])
    rl = sr.get("压力位", [price * 1.1])
    stop = calc_stop_levels(price, atr, float(sl[0]), float(rl[0]))

    risk = calc_risk_metrics(kline)
    sigs = consolidate_signals(generate_all_signals(kline))
    funds = cached_fundamentals(code)
    fsv, _ = score_fundamental(funds) if funds else (0, {})
    quant = composite_quant_score(kline, funds, sentiment_score=None)
    trading = evaluate_trading_style(kline, funds, risk)

    n5 = float((kline.iloc[-1]["收盘"] / kline.iloc[-6]["收盘"] - 1) * 100) if len(kline) > 5 else 0
    n20 = (
        float((kline.iloc[-1]["收盘"] / kline.iloc[-21]["收盘"] - 1) * 100)
        if len(kline) > 20
        else 0
    )

    rsi = tech.get("rsi_value", 50) if isinstance(tech, dict) else 50
    macd_sig = tech.get("macd_signal", "") if isinstance(tech, dict) else ""
    kdj_sig = tech.get("kdj_signal", "") if isinstance(tech, dict) else ""

    qs = quant if isinstance(quant, dict) else {}
    fs = qs.get("factor_scores", {})

    def gf(k):
        v = fs.get(k, {})
        return float(v.get("score", 0)) if isinstance(v, dict) else 0

    risk_d = risk if isinstance(risk, dict) else {}
    sigs_d = sigs if isinstance(sigs, dict) else {}
    ts_d = trading if isinstance(trading, dict) else {}
    stop_d = stop if isinstance(stop, dict) else {}

    if not skip_nt:
        has_nt, nt_holders = _check_national_team(code)
    else:
        has_nt = False
        nt_holders = []

    return {
        "code": code,
        "price": price,
        "atr": atr,
        "near_5d": round(n5, 2),
        "near_20d": round(n20, 2),
        "rsi": round(rsi, 1),
        "macd_signal": macd_sig,
        "kdj_signal": kdj_sig,
        "fund_score": round(fsv, 1),
        "roe": round(funds.get("ROE", 0), 2) if funds else 0,
        "sharpe": round(risk_d.get("sharpe_ratio", 0), 3),
        "max_dd": round(risk_d.get("max_drawdown_pct", 0), 2),
        "var95": round(risk_d.get("VaR_95_pct", 0), 2),
        "volatility": round(risk_d.get("annualized_volatility_pct", 0), 2),
        "signal_bias": sigs_d.get("bias", "neutral"),
        "signal_score": sigs_d.get("score", 0),
        "short_score": round(ts_d.get("short_term_score", 0), 1),
        "long_score": round(ts_d.get("long_term_score", 0), 1),
        "style": ts_d.get("style", ""),
        "confidence": ts_d.get("style_confidence", ""),
        "short_basis": ts_d.get("short_term_basis", ""),
        "long_basis": ts_d.get("long_term_basis", ""),
        "qs_composite": round(float(qs.get("composite_score", 0)), 1),
        "qs_rating": str(qs.get("rating", "")),
        "mom_s": round(gf("momentum"), 1),
        "tech_s": round(gf("technical"), 1),
        "fund_s": round(gf("fundamental"), 1),
        "vol_s": round(gf("volume"), 1),
        "risk_s": round(gf("risk"), 1),
        "has_nt": has_nt,
        "nt_holders": nt_holders,
        "support": [round(float(x), 2) for x in sl[:2]],
        "resistance": [round(float(x), 2) for x in rl[:2]],
        "stop_loss": round(stop_d.get("止损参考价", 0), 2),
        "stop_profit": round(stop_d.get("止盈参考价", 0), 2),
        "_kline": kline,
        "fundamentals": funds,
        "quant_score": quant,
        "technical_summary": tech,
        "support_resistance": sr,
        "stop_levels": stop,
        "risk_metrics": risk,
        "signals": sigs,
        "trading_style": trading,
    }
