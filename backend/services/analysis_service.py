"""个股分析服务层 — L0-L7 七层全出 + Builder 函数

职责:
    - 执行分析流水线 (_run_analysis)
    - TTL 缓存管理 (_cached_analysis)
    - 所有 _build_* 函数（从 router 中提取）
    - 统一 numpy → Python 原生类型转换 (_safe)
"""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# 核心分析流水线
# ═══════════════════════════════════════════


# Analysis result cache (in-memory, 5-minute TTL)
_ANALYSIS_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_TTL = 300  # seconds


def cached_analysis(code: str, full: bool = True) -> dict[str, Any]:
    """Cache-aware analysis wrapper"""
    key = f"{code}:{'full' if full else 'std'}"
    now = time.time()
    if key in _ANALYSIS_CACHE:
        entry = _ANALYSIS_CACHE[key]
        if now - entry["time"] < _CACHE_TTL:
            return entry["result"]  # type: ignore[no-any-return]
    result = _run_analysis(code, full=full)
    _ANALYSIS_CACHE[key] = {"result": result, "time": now}
    return result


def _run_analysis(code: str, full: bool = True) -> dict:
    """执行完整分析流水线，返回结构化 dict"""
    from stock_analyzer.analysis import calc_support_resistance, get_technical_summary
    from stock_analyzer.analyzer import deep_analyze
    from stock_analyzer.fetcher import sina_real_time

    r = deep_analyze(code, days=365)
    if r is None:
        raise ValueError(f"股票 {code} 数据不足（K线<20天）")

    kline = r["_kline"]
    tech_sum = get_technical_summary(kline)
    sr = calc_support_resistance(kline)

    rt = sina_real_time([code])
    info = rt.get(code, {})
    name = info.get("名称", code)
    price = float(info.get("最新价", 0) or r.get("price", 0))

    result = {
        "code": code,
        "name": name,
        "time": time.strftime("%H:%M:%S"),
        "quote": _build_quote(code, name, info, price, r),
        "technical": _build_technical(r, tech_sum, sr),
        "quant": _build_quant(r),
        "risk": _build_risk(r),
        "financial": _build_financial(r),
        "fund_flow": _build_fund_flow(code, r),
        "signal": _build_signal(r),
        "near_5d": r.get("near_5d", 0),
        "near_20d": r.get("near_20d", 0),
        "short_score": r.get("short_score", 0),
        "long_score": r.get("long_score", 0),
        "style": r.get("style", ""),
    }

    if full:
        result["debate"] = _build_debate(code, r)
        result["ml"] = _build_ml(r)

        # 11段分析新增
        result["sector_analysis"] = _build_sector_analysis(code, r)
        result["pattern_analysis"] = _build_pattern_analysis(kline, info)
        result["manipulator_intention"] = _build_manipulator_intention(code, r)
        result["retail_psychology"] = _build_retail_psychology(r)
        result["prediction"] = _build_prediction(r)
        result["operation_advice"] = _build_operation_advice(r)
        result["combined_summary"] = _build_combined_summary(
            result["pattern_analysis"], result["manipulator_intention"]
        )
        result["risk_warnings"] = _build_risk_warnings(r, result.get("sector_analysis"))
        result["data_sources"] = _build_data_sources(r)
        try:
            from stock_analyzer.business_quality import full_business_quality

            result["chip_concentration"] = _build_chip_concentration(code, kline)
            result["business_quality"] = full_business_quality(code)
        except Exception:
            result["business_quality"] = None

    return result


def run_fast_analysis(code: str) -> dict[str, Any]:
    """快速分析 — 纯本地 L0-L2，200ms 级别"""
    from stock_analyzer.analysis import (
        calc_stop_levels,
        calc_support_resistance,
        full_technical_analysis,
        get_technical_summary,
    )
    from stock_analyzer.cache import cached_fundamentals, cached_kline
    from stock_analyzer.fetcher import sina_real_time
    from stock_analyzer.quant import composite_quant_score

    kline = cached_kline(code, days=120)
    if kline is None or kline.empty or len(kline) < 20:
        raise ValueError(f"股票 {code} 数据不足")

    kline = full_technical_analysis(kline)
    tech = get_technical_summary(kline)
    sr = calc_support_resistance(kline)
    price = float(kline["收盘"].iloc[-1])
    atr = (
        float(kline.iloc[-1].get("ATR", price * 0.03))
        if "ATR" in kline.columns
        else price * 0.03
    )
    stop = calc_stop_levels(
        price,
        atr,
        float(sr.get("支撑位", [price * 0.9])[0]),
        float(sr.get("压力位", [price * 1.1])[0]),
    )
    funds = cached_fundamentals(code)
    quant = composite_quant_score(kline, funds)

    n5 = (
        round(float((kline["收盘"].iloc[-1] / kline["收盘"].iloc[-6] - 1) * 100), 2)
        if len(kline) > 5
        else 0
    )
    n20 = (
        round(float((kline["收盘"].iloc[-1] / kline["收盘"].iloc[-21] - 1) * 100), 2)
        if len(kline) > 20
        else 0
    )

    rt = sina_real_time([code])
    info = rt.get(code, {})
    name = info.get("名称", code)
    price_rt = float(info.get("最新价", 0) or price)

    result = {
        "code": code,
        "name": name,
        "time": time.strftime("%H:%M:%S"),
        "quote": _build_quote(code, name, info, price_rt, None),
        "technical": {
            "ma_status": tech.get("均线", ""),
            "macd_signal": tech.get("macd_signal", ""),
            "kdj_signal": tech.get("kdj_signal", ""),
            "rsi_value": tech.get("rsi_value", 50),
            "atr": round(atr, 2),
            "support": [round(float(x), 2) for x in sr.get("支撑位", [price * 0.9])[:2]],
            "resistance": [round(float(x), 2) for x in sr.get("压力位", [price * 1.1])[:2]],
            "stop_loss": round(stop.get("止损参考价", price * 0.93), 2),
            "stop_profit": round(stop.get("止盈参考价", price * 1.07), 2),
        },
        "quant": {
            "composite": round(float(quant.get("composite_score", 50)), 1),
            "rating": str(quant.get("rating", "")),
            "factor_scores": {
                k: round(float(v.get("score", 0)), 1) if isinstance(v, dict) else 0
                for k, v in quant.get("factor_scores", {}).items()
            },
        },
        "risk": {
            "sharpe_ratio": 0,
            "max_drawdown_pct": 0,
            "annual_volatility_pct": 0,
            "var_95_pct": 0,
        },
        "financial": {
            "roe": round(funds.get("ROE", 0), 2) if isinstance(funds, dict) else None
        },
        "near_5d": n5,
        "near_20d": n20,
    }
    return result


def build_kline_data(code: str, ktype: str = "day", days: int = 120) -> dict[str, Any]:
    """获取K线JSON数据（供前端 ECharts 渲染）"""
    import pandas as pd

    from stock_analyzer.analysis import full_technical_analysis
    from stock_analyzer.cache import cached_kline

    df = cached_kline(code, days=days)
    if df is None or df.empty:
        raise ValueError("K线数据不可用")

    df = full_technical_analysis(df)
    df["日期"] = pd.to_datetime(df["日期"])

    if ktype == "week":
        df = (
            df.set_index("日期")
            .resample("W")
            .agg({"开盘": "first", "最高": "max", "最低": "min", "收盘": "last", "成交量": "sum"})
            .dropna()
            .reset_index()
            .tail(52)
        )
    elif ktype == "month":
        df = (
            df.set_index("日期")
            .resample("ME")
            .agg({"开盘": "first", "最高": "max", "最低": "min", "收盘": "last", "成交量": "sum"})
            .dropna()
            .reset_index()
            .tail(24)
        )

    tail = df.tail(120)
    closes = tail["收盘"].values.tolist()

    def safe_ma(series, window):
        return [
            round(float(x), 2) if pd.notna(x) else None
            for x in series.rolling(window).mean().values.tolist()
        ]

    return {
        "dates": [str(d)[:10] for d in tail["日期"].values],
        "opens": [round(float(x), 2) for x in tail["开盘"].values],
        "highs": [round(float(x), 2) for x in tail["最高"].values],
        "lows": [round(float(x), 2) for x in tail["最低"].values],
        "closes": [round(float(x), 2) for x in closes],
        "volumes": [int(x) for x in tail["成交量"].values],
        "ma5": safe_ma(tail["收盘"], 5),
        "ma10": safe_ma(tail["收盘"], 10),
        "ma20": safe_ma(tail["收盘"], 20),
        "ma60": safe_ma(tail["收盘"], 60),
    }


def build_indicator_data(code: str, indicator: str = "macd") -> dict[str, Any]:
    """获取技术指标JSON数据（供前端 ECharts 渲染）"""
    from stock_analyzer.analysis import full_technical_analysis
    from stock_analyzer.cache import cached_kline

    df = full_technical_analysis(cached_kline(code, days=120))
    if df is None or df.empty:
        raise ValueError("数据不可用")

    tail = df.tail(60)
    dates = [str(d)[:10] for d in tail["日期"].values]

    result = {"type": indicator, "dates": dates, "values": {}}
    if indicator == "macd" and "DIF" in tail.columns:
        result["values"] = {
            "dif": [round(float(x), 4) for x in tail["DIF"].values],
            "dea": [round(float(x), 4) for x in tail["DEA"].values],
            "bar": [round(float(x), 4) for x in tail.get("MACD", [0] * len(tail)).values],
        }
    elif indicator == "rsi" and "RSI" in tail.columns:
        result["values"] = {"rsi": [round(float(x), 2) for x in tail["RSI"].values]}
    elif indicator == "kdj" and "K" in tail.columns:
        result["values"] = {
            "k": [round(float(x), 2) for x in tail["K"].values],
            "d": [round(float(x), 2) for x in tail["D"].values],
            "j": [round(float(x), 2) for x in tail.get("J", [0] * len(tail)).values],
        }
    return result


def build_fund_flow_data(code: str, days: int = 20) -> dict[str, Any]:
    """获取资金流向数据"""
    from stock_analyzer.fetcher import get_fund_flow

    ff = get_fund_flow(code, days=days)
    if ff is None or ff.empty:
        raise ValueError("资金流向数据不可用")

    flows: list[dict[str, Any]] = []
    for _, row in ff.iterrows():
        flows.append(
            {
                "date": str(row.get("日期", ""))[:10],
                "main_net": round(float(row.get("主力净流入-净额", 0)) / 1e8, 4),
                "main_pct": round(float(row.get("主力净流入-净占比", 0)), 2),
                "super_large_net": round(float(row.get("超大单净流入-净额", 0)) / 1e8, 4),
                "large_net": round(float(row.get("大单净流入-净额", 0)) / 1e8, 4),
            }
        )

    total = sum(f["main_net"] for f in flows)
    return {
        "direction": "流入" if total > 0 else "流出",
        "total_yi": round(total, 2),
        "daily": flows,
    }


# ═══════════════════════════════════════════
# Builder 函数
# ═══════════════════════════════════════════


def _build_quote(code, name, info, price, r):
    return {
        "code": code,
        "name": name,
        "price": price,
        "open": float(info.get("今开", 0) or 0),
        "high": float(info.get("最高", 0) or 0),
        "low": float(info.get("最低", 0) or 0),
        "prev_close": float(info.get("昨收", 0) or 0),
        "change": round(price - float(info.get("昨收", 0) or price), 2),
        "change_pct": round(
            (price - float(info.get("昨收", 0) or price))
            / max(float(info.get("昨收", 0) or price), 0.01)
            * 100,
            2,
        ),
        "amplitude": round(float(info.get("振幅", 0) or 0), 2),
        "volume": int(float(info.get("成交量", 0) or 0)),
        "turnover": round(float(info.get("换手率", 0) or 0), 2),
    }


def _build_technical(r, tech_sum=None, sr=None):
    stop_d = r.get("stop_levels", {})
    return {
        "ma_status": (tech_sum or {}).get("均线", ""),
        "macd_signal": r.get("macd_signal", ""),
        "kdj_signal": r.get("kdj_signal", ""),
        "rsi_value": r.get("rsi", 50),
        "macd_dif": r.get("_kline", None).iloc[-1].get("DIF")
        if r.get("_kline") is not None
        else None,
        "macd_dea": r.get("_kline", None).iloc[-1].get("DEA")
        if r.get("_kline") is not None
        else None,
        "adx": r.get("_kline", None).iloc[-1].get("ADX") if r.get("_kline") is not None else None,
        "atr": r.get("atr", 0),
        "support": r.get("support", [])[:2],
        "resistance": r.get("resistance", [])[:2],
        "stop_loss": r.get("stop_loss", 0),
        "stop_profit": r.get("stop_profit", 0),
    }


def _build_quant(r):
    return {
        "composite": r.get("qs_composite", 50),
        "rating": r.get("qs_rating", ""),
        "factor_scores": {
            "momentum": r.get("mom_s", 0),
            "technical": r.get("tech_s", 0),
            "fundamental": r.get("fund_s", 0),
            "volume": r.get("vol_s", 0),
            "risk": r.get("risk_s", 0),
        },
    }


def _build_risk(r):
    return {
        "sharpe_ratio": r.get("sharpe", 0),
        "max_drawdown_pct": r.get("max_dd", 0),
        "annual_volatility_pct": r.get("volatility", 0),
        "var_95_pct": r.get("var95", 0),
    }


def _build_financial(r):
    funds = r.get("fundamentals", {})
    if not isinstance(funds, dict):
        funds = {}
    return {
        "roe": round(funds.get("ROE", 0), 2) if funds.get("ROE") else None,
        "pe": funds.get("市盈率"),
        "pb": funds.get("市净率"),
        "eps": funds.get("每股收益"),
        "gross_margin": funds.get("毛利率"),
        "net_margin": funds.get("净利率"),
        "revenue_growth": funds.get("营收增长"),
        "profit_growth": funds.get("净利润增长"),
    }


def _build_fund_flow(code, r):
    try:
        from stock_analyzer.cache import cached_fund_flow, cached_kline
        from stock_analyzer.chip_factors import composite_chip_score

        kline = r.get("_kline")
        if kline is None:
            kline = cached_kline(code)
        ff = cached_fund_flow(code, days=5)
        total = 0.0
        if ff is not None and not ff.empty:
            total = round(float(ff["主力净流入-净额"].sum()) / 1e8, 2)
        chip = composite_chip_score(code, kline) if kline is not None else 50
        nt_holders = r.get("nt_holders", [])
        return {
            "direction": "流入" if total > 0 else "流出",
            "total_5d": total,
            "chip_score": chip,
            "national_team": f"{len(nt_holders)}家" if nt_holders else "无",
        }
    except Exception:
        return {"direction": "", "total_5d": 0, "chip_score": 50, "national_team": "无"}


def _build_signal(r):
    sigs_d = r.get("signals", {})
    return {
        "bias": sigs_d.get("bias", "neutral"),
        "score": sigs_d.get("score", 0),
        "combo_strength": sigs_d.get("combo_strength", 0),
        "details": sigs_d.get("details", []),
    }


# ═══════════════════════════════════════════
# 11段分析 builder 函数
# ═══════════════════════════════════════════


def _build_debate(code, r):
    try:
        from stock_analyzer.analysis import calc_support_resistance, get_technical_summary
        from stock_analyzer.ml_predict import _cached_predict_ensemble
        from stock_analyzer.nl_report import generate_bull_bear_debate

        kline = r["_kline"]
        tech_sum = get_technical_summary(kline)
        sr = calc_support_resistance(kline)
        ai = _cached_predict_ensemble(kline, {})
        price = r.get("price", 0)

        debate = generate_bull_bear_debate(
            {
                "quant_score": r.get("qs_composite", 50),
                "technical": {
                    "macd_signal": r.get("macd_signal", ""),
                    "kdj_signal": r.get("kdj_signal", ""),
                    "rsi": r.get("rsi", 50),
                    "near5d": r.get("near_5d", 0),
                    "near20d": r.get("near_20d", 0),
                    "ma_status": tech_sum.get("均线", ""),
                    "resistance": sr.get("压力", []),
                    "price": price,
                    "pe": r.get("fundamentals", {}).get("市盈率")
                    if isinstance(r.get("fundamentals"), dict)
                    else None,
                },
                "fund_flow": {"direction": "流入" if r.get("fund_flow_total", 0) > 0 else "流出"},
                "ai_prediction": {
                    "direction": ai.get("ensemble_direction", "看涨"),
                    "confidence": ai.get("ensemble_confidence", 50),
                },
            }
        )
        return {
            "bull_points": debate["bull"]["points"],
            "bear_points": debate["bear"]["points"],
            "bull_score": debate["bull"]["score"],
            "bear_score": debate["bear"]["score"],
            "verdict": debate["verdict"],
            "action": debate["action"],
        }
    except Exception:
        return {
            "bull_points": [],
            "bear_points": [],
            "bull_score": 0,
            "bear_score": 0,
            "verdict": "",
            "action": "",
        }


def safe_convert(v):
    """递归转换 numpy 类型为 Python 原生类型，避免 JSON 序列化崩溃"""
    import numpy as np

    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, dict):
        return {k: safe_convert(vv) for k, vv in v.items()}
    if isinstance(v, (list, tuple)):
        return [safe_convert(x) for x in v]
    return v


def _build_ml(r):
    try:
        from stock_analyzer.ml_predict import _cached_predict_ensemble

        ai = _cached_predict_ensemble(r["_kline"], {})
        return safe_convert(
            {
                "direction": ai.get("ensemble_direction", "?"),
                "confidence": ai.get("ensemble_confidence", 0),
                "votes": ai.get("votes", ""),
                "models": ai.get("models", {}),
            }
        )
    except Exception:
        return {"direction": "?", "confidence": 0, "votes": "", "models": {}}


def _build_sector_analysis(code, r):
    """板块分析：所属板块 + 排名 + 资金流向"""
    try:
        from stock_analyzer.fetcher import get_sectors
        from stock_analyzer.sector_info import get_stock_concepts, get_stock_sector_full

        industry = get_stock_sector_full(code)
        concepts = (get_stock_concepts(code) or [])[:5]

        # 提取板块简称用于匹配
        sname = industry.split(" > ")[-1] if " > " in industry else industry

        sectors = get_sectors()
        rank, total_sectors, change_pct, flow_yi = 0, 0, 0.0, 0.0
        if isinstance(sectors, dict) and sectors:
            ranked = sorted(
                sectors.items(), key=lambda x: float(x[1].get("涨跌幅", 0) or 0), reverse=True
            )
            total_sectors = len(ranked)
            for i, (nm, info) in enumerate(ranked):
                chg = float(info.get("涨跌幅", 0) or 0)
                ff = float(info.get("资金净流入", 0) or 0) / 1e8
                # 模糊匹配板块名称
                if nm == sname or sname in nm or (nm and nm in sname):
                    rank = i + 1
                    change_pct = round(chg, 2)
                    flow_yi = round(ff, 1)
                    break

        # 计算排位百分比
        rpct = (total_sectors - rank) / total_sectors * 100 if rank and total_sectors else 50
        if rpct > 66:
            label, color = "强势前排", "green"
        elif rpct > 33:
            label, color = "中游", "yellow"
        else:
            label, color = "弱势后排", "red"

        assessment = ""
        if rank:
            assessment = f"板块今日排名 #{rank}/{total_sectors}，处于{label}位置"
            if rpct < 35:
                assessment += "。板块整体弱势，个股逆势上涨难度较大，注意板块拖累风险"
        else:
            assessment = "板块排名数据暂未匹配到，建议人工确认板块归属"

        return {
            "industry": industry,
            "concepts": concepts,
            "sector_name": sname,
            "sector_rank": rank,
            "sector_total": total_sectors,
            "sector_change_pct": change_pct,
            "sector_fund_flow_yi": flow_yi,
            "rank_label": label,
            "rank_color": color,
            "assessment": assessment,
        }
    except Exception:
        return {
            "industry": "未知",
            "concepts": [],
            "sector_name": "",
            "sector_rank": 0,
            "sector_total": 0,
            "sector_change_pct": 0,
            "sector_fund_flow_yi": 0,
            "rank_label": "未知",
            "rank_color": "gray",
            "assessment": "板块数据暂不可用",
        }


def _build_pattern_analysis(kline, rt_info=None):
    """K线形态解读（含当日盘中数据）"""
    try:
        from stock_analyzer.patterns import generate_kline_interpretation_with_today

        if rt_info and rt_info.get("今开") and rt_info.get("最新价"):
            return generate_kline_interpretation_with_today(
                kline,
                today_open=float(rt_info.get("今开", 0) or 0),
                today_high=float(rt_info.get("最高", 0) or 0),
                today_low=float(rt_info.get("最低", 0) or 0),
                today_close=float(rt_info.get("最新价", 0) or 0),
                today_volume=int(float(rt_info.get("成交量", 0) or 0)),
            )
        return generate_kline_interpretation_with_today(kline)
    except Exception:
        return {
            "recent_patterns": [],
            "summary": "K线形态分析暂不可用",
            "trend_phase": "未知",
            "key_observation": "",
        }


def _build_manipulator_intention(code, r):
    """庄家意图分析"""
    try:
        from stock_analyzer.chip_factors import composite_chip_score
        from stock_analyzer.psychology import analyze_manipulator_intention

        kline = r["_kline"]
        flow_dir = "流入" if r.get("fund_flow_total", 0) > 0 else "流出"
        chip = composite_chip_score(code, kline) if kline is not None else 50
        return analyze_manipulator_intention(kline, flow_dir, chip)
    except Exception:
        return {
            "phase": "不明",
            "phase_confidence": 0,
            "signals": [],
            "volume_analysis": "",
            "chip_analysis": "",
            "assessment": "庄家意图分析暂不可用",
            "risk_note": "",
        }


def _build_retail_psychology(r):
    """散户心态画像"""
    try:
        from stock_analyzer.psychology import analyze_retail_psychology

        return analyze_retail_psychology(r["_kline"], r.get("rsi", 50), r.get("near_5d", 0))
    except Exception:
        return {
            "emotion": "未知",
            "emotion_score": 0,
            "behavior_pattern": "",
            "sentiment_indicators": [],
            "advice": "",
        }


def _build_prediction(r):
    """明日预测"""
    try:
        from stock_analyzer.ml_predict import _cached_predict_ensemble

        ai = _cached_predict_ensemble(r["_kline"], {})
        price = r.get("price", 0)
        atr = r.get("atr", price * 0.03)

        direction = ai.get("ensemble_direction", "震荡")
        confidence = ai.get("ensemble_confidence", 50)

        range_low = round(price - atr * 0.8, 2)
        range_high = round(price + atr * 0.8, 2)

        macd = r.get("macd_signal", "")
        rsi = r.get("rsi", 50)
        combo = r.get("signals", {}).get("combo_strength", 0)

        reasons = []
        if "金叉" in str(macd):
            reasons.append("MACD金叉，短期动能向上")
        if 40 < rsi < 65:
            reasons.append(f"RSI={rsi:.0f}处于健康区间")
        if combo >= 3:
            reasons.append("多信号共振，方向明确")
        if not reasons:
            reasons.append("多空信号分歧，大概率震荡为主")

        return {
            "direction": direction,
            "confidence": min(round(confidence), 95),
            "price_range": {"low": range_low, "high": range_high},
            "key_level": round(price, 2),
            "rationale": "；".join(reasons),
        }
    except Exception:
        return {
            "direction": "震荡",
            "confidence": 0,
            "price_range": {"low": 0, "high": 0},
            "key_level": 0,
            "rationale": "",
        }


def _build_operation_advice(r):
    """操作建议"""
    try:
        price = r.get("price", 0)
        atr = r.get("atr", price * 0.03)
        quant = r.get("qs_composite", 50)
        n5 = r.get("near_5d", 0)
        n20 = r.get("near_20d", 0)
        rsi = r.get("rsi", 50)
        signal_bias = r.get("signal_bias", "neutral")

        # 方向判断
        if quant >= 65 and signal_bias == "bullish" and n20 < 30:
            direction, dir_color = "买入", "green"
            position = 60
        elif quant >= 55:
            direction, dir_color = "观望", "yellow"
            position = 30
        elif quant >= 40:
            direction, dir_color = "观望", "yellow"
            position = 0
        else:
            direction, dir_color = "减仓", "red"
            position = 0

        entry_low = round(price - atr * 0.5, 2)
        entry_high = round(price + atr * 0.3, 2)
        sl = round(max(price - 1.5 * atr, price * 0.93), 2)
        tp1 = round(price + 2 * atr, 2)
        tp2 = round(price + 3 * atr, 2)

        holding = "1-2天" if quant >= 60 else "观望"

        points = []
        if quant >= 60:
            points.append("量化评分较高，可轻仓参与")
        if n5 > 8:
            points.append("短期涨幅较大，注意追高风险")
        elif n5 < -5:
            points.append("短期超跌，可关注反弹机会但需确认止跌信号")
        if rsi > 70:
            points.append("RSI超买，等待回调至健康区间再介入更安全")
        elif rsi < 30:
            points.append("RSI超卖，左侧买入风险较大，等右侧信号")
        if n20 > 25:
            points.append(f"近20日涨{n20:.0f}%，追高惩罚生效，综合评分已被拉低")

        return {
            "direction": direction,
            "direction_color": dir_color,
            "confidence": "高" if quant >= 65 else "中",
            "entry_range": {"low": entry_low, "high": entry_high},
            "stop_loss": sl,
            "take_profit": [tp1, tp2],
            "position_pct": position,
            "holding_days": holding,
            "key_points": points if points else ["按量化信号操作，注意止损纪律"],
        }
    except Exception:
        return {
            "direction": "观望",
            "direction_color": "yellow",
            "confidence": "低",
            "entry_range": {"low": 0, "high": 0},
            "stop_loss": 0,
            "take_profit": [],
            "position_pct": 0,
            "holding_days": "",
            "key_points": [],
        }


def _build_combined_summary(pattern_result, manipulator_result):
    """K线+庄家联动总结"""
    try:
        from stock_analyzer.psychology import generate_combined_summary

        return generate_combined_summary(pattern_result, manipulator_result)
    except Exception:
        return {
            "kline_summary": "",
            "manipulator_summary": "",
            "synergy_assessment": "",
            "overall_conclusion": "数据不足",
        }


def _build_risk_warnings(r, sector_result=None):
    """风险提示列表"""
    risks = []
    n5 = r.get("near_5d", 0)
    n20 = r.get("near_20d", 0)
    rsi = r.get("rsi", 50)

    if n5 > 12:
        risks.append({"level": "high", "message": f"近5日涨{n5:.1f}%，短线追高风险极大，不建议追入"})
    elif n5 > 8:
        risks.append({"level": "medium", "message": f"近5日涨{n5:.1f}%，短线涨幅偏大，注意回调"})
    if n20 > 30:
        risks.append(
            {
                "level": "high",
                "message": f"近20日涨{n20:.1f}%，处于高位加速区，追高是短线亏钱第一大原因",
            }
        )
    elif n20 > 20:
        risks.append({"level": "medium", "message": f"近20日涨{n20:.1f}%，追高惩罚机制已触发"})

    if rsi > 72:
        risks.append({"level": "medium", "message": f"RSI={rsi:.0f}超买，技术上有回调需求"})
    if rsi < 25:
        risks.append({"level": "medium", "message": f"RSI={rsi:.0f}超卖，可能继续惯性下探"})

    if sector_result and isinstance(sector_result, dict):
        if sector_result.get("rank_color") == "red":
            risks.append(
                {
                    "level": "medium",
                    "message": f"所属板块排名靠后（#{sector_result.get('sector_rank', '?')}），板块弱势拖累个股",
                }
            )
        if sector_result.get("sector_rank") == 0:
            risks.append({"level": "low", "message": "板块排名数据缺失，无法评估板块联动风险"})

    from stock_analyzer.fetcher import get_fund_flow

    try:
        ff = get_fund_flow("000001", days=1)
        if ff is None or ff.empty:
            risks.append(
                {
                    "level": "info",
                    "message": "资金流向数据暂不可用（东财API可能盘中关闭），主力资金判断参考性降低",
                }
            )
    except Exception:
        risks.append(
            {"level": "info", "message": "部分外部数据源可能不稳定，盘中数据以实时行情为准"}
        )

    if not risks:
        risks.append({"level": "low", "message": "暂无明显极端风险信号，处于常规波动范围内"})

    risks.append(
        {
            "level": "info",
            "message": "以上分析基于历史数据和量化模型，不构成投资建议。市场有风险，投资需谨慎。",
        }
    )

    return risks


def _build_chip_concentration(code, kline):
    """筹码集中度分析"""
    try:
        from stock_analyzer.chip_concentration import calc_chip_concentration

        return calc_chip_concentration(kline)
    except Exception:
        return {"pct90": 0, "pct70": 0, "level": "无法评估", "risk_warning": ""}


def _build_data_sources(r):
    """数据来源 & 时效性"""
    import time as _time

    return {
        "quote_source": "新浪财经实时行情",
        "kline_source": "东方财富K线数据",
        "sector_source": "东方财富板块数据(BK)",
        "fundamental_source": "Baostock基本面数据",
        "update_time": _time.strftime("%H:%M:%S"),
        "disclaimer": "以上分析仅供学习研究，不构成投资建议。市场有风险，投资需谨慎。",
    }
