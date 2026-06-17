"""量化投资分析模块
风险指标 / 多因子评分 / 量化交易信号 / 策略回测
依赖: numpy, pandas, analysis.py
"""

import numpy as np
import pandas as pd

from typing import Any

from .analysis import score_fundamental
from .config import (
    QUANT_FACTOR_WEIGHTS,
    RISK_FREE_RATE,
    TRADING_DAYS_PER_YEAR,
    VAR_CONFIDENCE,
)

# ═══════════════════════════════════════════════════════════════
# 1. 风险指标
# ═══════════════════════════════════════════════════════════════


def _daily_returns(df):
    """内部：计算每日收益率序列（小数，非百分比）"""
    if df.empty or "收盘" not in df.columns:
        return pd.Series(dtype=float)
    ret = df["收盘"].pct_change().dropna()
    return ret


def calc_annualized_return(daily_returns, trading_days=TRADING_DAYS_PER_YEAR):
    if daily_returns.empty or len(daily_returns) < 5:
        return None
    return float(daily_returns.mean() * trading_days * 100)  # 转为百分比


def calc_annualized_volatility(daily_returns, trading_days=TRADING_DAYS_PER_YEAR):
    if daily_returns.empty or len(daily_returns) < 5:
        return None
    return float(daily_returns.std() * np.sqrt(trading_days) * 100)


def calc_sharpe_ratio(
    daily_returns, risk_free_rate=RISK_FREE_RATE, trading_days=TRADING_DAYS_PER_YEAR
):
    ann_ret = calc_annualized_return(daily_returns, trading_days)
    ann_vol = calc_annualized_volatility(daily_returns, trading_days)
    if ann_ret is None or ann_vol is None or ann_vol == 0:
        return None
    return round((ann_ret - risk_free_rate * 100) / ann_vol, 3)


def calc_sortino_ratio(
    daily_returns, risk_free_rate=RISK_FREE_RATE, trading_days=TRADING_DAYS_PER_YEAR
):
    if daily_returns.empty or len(daily_returns) < 5:
        return None
    ann_ret = calc_annualized_return(daily_returns, trading_days)
    downside = daily_returns[daily_returns < 0]
    if len(downside) < 2:
        return None
    downside_vol = float(downside.std() * np.sqrt(trading_days) * 100)
    if downside_vol == 0:
        return None
    return round((ann_ret - risk_free_rate * 100) / downside_vol, 3)


def calc_max_drawdown(close_series):
    """计算最大回撤及相关指标 — 向量化版本"""
    if close_series.empty or len(close_series) < 2:
        return {"max_drawdown_pct": 0, "max_drawdown_duration_days": 0, "current_drawdown_pct": 0}

    wealth = close_series / close_series.iloc[0]
    running_max = wealth.cummax()
    drawdown = (wealth / running_max - 1) * 100

    max_dd = float(drawdown.min())
    current_dd = float(drawdown.iloc[-1])

    # 最大回撤持续期 — 向量化：找所有峰值点，计算最大间隔
    wv = wealth.values
    rv = running_max.values
    peak_mask = wv >= rv  # 创新高或持平的位置
    peak_indices = np.where(peak_mask)[0]
    if len(peak_indices) > 0:
        gaps = np.diff(peak_indices)  # 相邻峰值之间的间隔
        max_dur = int(gaps.max()) if len(gaps) > 0 else 0
        # 最后一个峰值到序列末尾的间隔
        last_gap = len(wealth) - 1 - peak_indices[-1]
        max_dur = max(max_dur, last_gap)
    else:
        max_dur = len(wealth)

    return {
        "max_drawdown_pct": round(max_dd, 2),
        "max_drawdown_duration_days": max_dur,
        "current_drawdown_pct": round(current_dd, 2),
    }


def calc_calmar_ratio(daily_returns, close_series, trading_days=TRADING_DAYS_PER_YEAR):
    ann_ret = calc_annualized_return(daily_returns, trading_days)
    dd = calc_max_drawdown(close_series)
    mdd = abs(dd["max_drawdown_pct"])
    if ann_ret is None or mdd == 0:
        return None
    return round(ann_ret / mdd, 3)


def calc_var(daily_returns, confidence=VAR_CONFIDENCE):
    if daily_returns.empty or len(daily_returns) < 10:
        return {"VaR": None, "CVaR": None}
    threshold = np.percentile(daily_returns, (1 - confidence) * 100)
    var_val = float(threshold * 100)
    cvar_val = float(daily_returns[daily_returns <= threshold].mean() * 100)
    return {"VaR_95_pct": round(var_val, 2), "CVaR_95_pct": round(cvar_val, 2)}


def calc_risk_metrics(df, trading_days=TRADING_DAYS_PER_YEAR, risk_free_rate=RISK_FREE_RATE):
    """汇总：计算全部风险指标"""
    if df.empty or len(df) < 10:
        return dict.fromkeys(
            [
                "annualized_return_pct",
                "annualized_volatility_pct",
                "sharpe_ratio",
                "sortino_ratio",
                "max_drawdown_pct",
                "max_drawdown_duration_days",
                "calmar_ratio",
                "VaR_95_pct",
                "CVaR_95_pct",
            ]
        )

    ret = _daily_returns(df)
    close = df["收盘"]
    ann_ret = calc_annualized_return(ret, trading_days)
    ann_vol = calc_annualized_volatility(ret, trading_days)
    sharpe = calc_sharpe_ratio(ret, risk_free_rate, trading_days)
    sortino = calc_sortino_ratio(ret, risk_free_rate, trading_days)
    dd = calc_max_drawdown(close)
    calmar = calc_calmar_ratio(ret, close, trading_days)
    var_ = calc_var(ret)

    return {
        "annualized_return_pct": ann_ret,
        "annualized_volatility_pct": ann_vol,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown_pct": dd["max_drawdown_pct"],
        "max_drawdown_duration_days": dd["max_drawdown_duration_days"],
        "current_drawdown_pct": dd["current_drawdown_pct"],
        "calmar_ratio": calmar,
        "VaR_95_pct": var_["VaR_95_pct"],
        "CVaR_95_pct": var_["CVaR_95_pct"],
    }


# ═══════════════════════════════════════════════════════════════
# 2. 多因子评分模型
# ═══════════════════════════════════════════════════════════════


def _normalize_score(value, low=-20, high=20, invert=False):
    """将数值线性映射到 0-100 分，超过范围则截断"""
    if value <= low:
        raw = 0
    elif value >= high:
        raw = 100
    else:
        raw = (value - low) / (high - low) * 100
    return 100 - raw if invert else raw


def score_momentum_factor(df):
    """动量因子评分"""
    if df.empty or len(df) < 60:
        return {"score": 50, "details": {}}

    close = df["收盘"].iloc[-1]
    ret_5d = (close / df["收盘"].iloc[-6] - 1) * 100 if len(df) >= 6 else 0
    ret_20d = (close / df["收盘"].iloc[-21] - 1) * 100 if len(df) >= 21 else 0
    ret_60d = (close / df["收盘"].iloc[-61] - 1) * 100 if len(df) >= 61 else ret_20d

    s5 = _normalize_score(ret_5d, -10, 20)
    s20 = _normalize_score(ret_20d, -20, 30)
    s60 = _normalize_score(ret_60d, -30, 40)

    score = s5 * 0.3 + s20 * 0.4 + s60 * 0.3
    return {
        "score": round(score, 1),
        "details": {
            "return_5d_pct": round(ret_5d, 2),
            "return_20d_pct": round(ret_20d, 2),
            "return_60d_pct": round(ret_60d, 2),
            "score_5d": round(s5, 1),
            "score_20d": round(s20, 1),
            "score_60d": round(s60, 1),
        },
    }


def score_technical_factor(df):
    """技术面因子评分"""
    if df.empty or len(df) < 30:
        return {"score": 50, "details": {}}

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # MACD
    macd_score = 50
    macd_detail = "中性"
    if "DIF" in last and "DEA" in last:
        if last["DIF"] > last["DEA"] and prev["DIF"] <= prev["DEA"]:
            macd_score, macd_detail = 90, "金叉"
        elif last["DIF"] < last["DEA"] and prev["DIF"] >= prev["DEA"]:
            macd_score, macd_detail = 10, "死叉"
        elif last["DIF"] > last["DEA"]:
            macd_score, macd_detail = 65, "多头"
        else:
            macd_score, macd_detail = 35, "空头"

    # RSI
    rsi_score = 50
    rsi_val = last.get("RSI")
    if rsi_val is not None and not np.isnan(rsi_val):
        if 30 <= rsi_val <= 70:
            rsi_score = 70
        elif rsi_val < 20:
            rsi_score = 30
        elif rsi_val < 30:
            rsi_score = 55
        elif rsi_val > 80:
            rsi_score = 15
        else:
            rsi_score = 35

    # KDJ
    kdj_score = 50
    k, d = last.get("K"), last.get("D")
    if k is not None and d is not None and not np.isnan(k) and not np.isnan(d):
        pk, pd_ = prev.get("K"), prev.get("D")
        if k > d and (pk is not None and pd_ is not None and pk <= pd_):
            kdj_score = 85
        elif k < d and (pk is not None and pd_ is not None and pk >= pd_):
            kdj_score = 15
        elif k > 80 and d > 80:
            kdj_score = 20
        elif k < 20 and d < 20:
            kdj_score = 70
        elif k > d:
            kdj_score = 65
        else:
            kdj_score = 35

    # 均线排列
    ma_score = 50
    ma_cols = ["MA5", "MA10", "MA20", "MA60"]
    vals = [
        last.get(c)
        for c in ma_cols
        if last.get(c) is not None and not np.isnan(last.get(c, np.nan))
    ]
    if len(vals) >= 3:
        is_bull = all(vals[i] > vals[i + 1] for i in range(len(vals) - 1))
        is_bear = all(vals[i] < vals[i + 1] for i in range(len(vals) - 1))
        if is_bull:
            ma_score = 90
        elif is_bear:
            ma_score = 10
        else:
            ma_score = 50

    score = macd_score * 0.3 + rsi_score * 0.2 + kdj_score * 0.2 + ma_score * 0.3
    return {
        "score": round(score, 1),
        "details": {
            "macd_score": macd_score,
            "macd_detail": macd_detail,
            "rsi_score": rsi_score,
            "kdj_score": kdj_score,
            "ma_alignment_score": ma_score,
        },
    }


def score_volume_factor(df):
    """量能因子评分"""
    if df.empty or len(df) < 20:
        return {"score": 50, "details": {}}
    last_vol = df["成交量"].iloc[-1]
    avg_vol = df["成交量"].tail(20).mean()
    vol_ratio = last_vol / avg_vol if avg_vol > 0 else 0

    if vol_ratio > 2.0:
        vr_score = 90
    elif vol_ratio > 1.5:
        vr_score = 75
    elif vol_ratio > 1.2:
        vr_score = 60
    elif vol_ratio > 0.8:
        vr_score = 50
    elif vol_ratio > 0.5:
        vr_score = 35
    else:
        vr_score = 20

    # 量价配合：最近5日量价方向一致性
    vp_score = 50
    if len(df) >= 5:
        vol_dir = df["成交量"].diff().tail(5).sum()
        price_dir = df["收盘"].diff().tail(5).sum()
        if vol_dir > 0 and price_dir > 0:
            vp_score = 80
        elif vol_dir < 0 and price_dir < 0:
            vp_score = 30
        elif vol_dir > 0 > price_dir:
            vp_score = 25
        else:
            vp_score = 60

    score = vr_score * 0.5 + vp_score * 0.5
    return {
        "score": round(score, 1),
        "details": {
            "volume_ratio": round(vol_ratio, 2),
            "volume_ratio_score": vr_score,
            "volume_price_alignment": "aligned" if vp_score >= 60 else "diverging",
            "volume_price_score": vp_score,
        },
    }


def score_fund_flow_factor(df):
    """资金流向因子评分（主力净流入+超大单）

    依赖 df 中包含 fund_flow 字段（含主力净流入-净占比等）。
    如果 fund_flow 数据不存在，返回中性 50 分。
    """
    if df.empty or "fund_flow" not in df.columns:
        return {"score": 50, "details": {"available": False}}
    f = df["fund_flow"].iloc[-1] if isinstance(df["fund_flow"].iloc[-1], dict) else {}
    if not f:
        return {"score": 50, "details": {"available": False}}

    main_ratio = f.get("主力净流入-净占比", 0) or 0
    super_ratio = f.get("超大单净流入-净占比", 0) or 0

    # 主力净占比评分
    if main_ratio > 3:
        main_score = 90
    elif main_ratio > 1:
        main_score = 75
    elif main_ratio > 0:
        main_score = 60
    elif main_ratio > -1:
        main_score = 45
    elif main_ratio > -3:
        main_score = 30
    else:
        main_score = 15

    # 超大单净占比评分（权重低一些）
    if super_ratio > 2:
        super_score = 80
    elif super_ratio > 0:
        super_score = 60
    elif super_ratio > -2:
        super_score = 40
    else:
        super_score = 20

    score = main_score * 0.7 + super_score * 0.3
    return {
        "score": round(score, 1),
        "details": {
            "available": True,
            "main_net_ratio_pct": round(main_ratio, 2),
            "main_net_amount": f.get("主力净流入-净额", 0),
            "super_large_ratio_pct": round(super_ratio, 2),
            "main_score": main_score,
        },
    }


def score_risk_factor(df):
    """风险因子评分（风险越低分越高）"""
    if df.empty or len(df) < 10:
        return {"score": 50, "details": {}}

    last = df.iloc[-1]
    close = last["收盘"]

    # ATR占比
    atr = last.get("ATR", np.nan)
    if atr is not None and not np.isnan(atr) and close > 0:
        atr_ratio = atr / close * 100
        if atr_ratio < 2:
            atr_score = 80
        elif atr_ratio < 4:
            atr_score = 60
        elif atr_ratio < 6:
            atr_score = 40
        else:
            atr_score = 20
    else:
        atr_ratio = 0
        atr_score = 50

    # 20日回撤
    if len(df) >= 20:
        dd20 = (close / df["收盘"].tail(20).max() - 1) * 100
        if dd20 > -2:
            dd_score = 80
        elif dd20 > -5:
            dd_score = 60
        elif dd20 > -10:
            dd_score = 40
        else:
            dd_score = 20
    else:
        dd20 = 0
        dd_score = 50

    score = atr_score * 0.4 + dd_score * 0.6
    return {
        "score": round(score, 1),
        "details": {
            "atr_ratio_pct": round(atr_ratio, 2),
            "atr_ratio_score": atr_score,
            "drawdown_20d_pct": round(dd20, 2),
            "drawdown_20d_score": dd_score,
        },
    }


def score_sentiment_factor(code, news_df, sentiment_df):
    """舆情因子评分

    基于个股新闻关键词情感 + 微博舆情评分。
    返回 0-100 分，舆情正面时高分，负面时低分。
    无数据时返回 None（权重会被重新分配）。
    """
    if news_df is None or news_df.empty:
        if sentiment_df is None or sentiment_df.empty:
            return None  # 完全无数据，重新分配权重

    news_score: float = 50  # 中性基准

    # 1. 新闻关键词情感分析
    if news_df is not None and not news_df.empty:
        positive_keywords = [
            "利好",
            "上涨",
            "突破",
            "增长",
            "盈利",
            "分红",
            "回购",
            "创新高",
            "买入",
            "增持",
            "涨停",
            "反弹",
            "扩张",
            "中标",
            "合同",
            "签署",
            "合作",
            "获批",
            "扭亏",
            "超预期",
        ]
        negative_keywords = [
            "利空",
            "下跌",
            "亏损",
            "减持",
            "风险",
            "预警",
            "处罚",
            "诉讼",
            "退市",
            "下调",
            "跌停",
            "违约",
            "调查",
            "降级",
            "破产",
            "st",
            "警示",
            "冻结",
            "问责",
        ]

        headlines = news_df["标题"].head(5).tolist() if "标题" in news_df.columns else []
        if headlines:
            pos_count = sum(1 for kw in positive_keywords for t in headlines if kw in t)
            neg_count = sum(1 for kw in negative_keywords for t in headlines if kw in t)
            total = pos_count + neg_count
            if total > 0:
                net_ratio = (pos_count - neg_count) / total
                news_score = 50 + net_ratio * 40  # 范围 10-90
            else:
                news_score = 55  # 有新闻但无明显倾向，略偏中性偏正

    # 2. 微博舆情分（-1到+1）
    weibo_score: float = 50
    if sentiment_df is not None and not sentiment_df.empty and "rate" in sentiment_df.columns:
        # 通过股票名称匹配
        from .screener import get_stock_name

        name = get_stock_name(code)
        if name:
            match = sentiment_df[sentiment_df["name"] == name]
            if not match.empty:
                rate = float(match["rate"].iloc[0])
                weibo_score = 50 + rate * 40  # -1→10, 0→50, 1→90

    # 综合评分（新闻40% + 微博60%）
    composite = news_score * 0.4 + weibo_score * 0.6
    return round(max(0, min(100, composite)), 1)


def composite_quant_score(df, fundamentals=None, weights=None, sentiment_score=None):
    """多因子综合评分"""
    if weights is None:
        weights = QUANT_FACTOR_WEIGHTS

    momentum = score_momentum_factor(df)
    technical = score_technical_factor(df)
    volume = score_volume_factor(df)
    risk = score_risk_factor(df)
    fund_flow = score_fund_flow_factor(df)

    # 基本面
    if fundamentals:
        raw_score, _ = score_fundamental(fundamentals)
        fundamental = {"score": raw_score, "details": {"raw_score": raw_score}}
    else:
        fundamental = {"score": 50, "details": {}}

    # 舆情
    if sentiment_score is not None:
        sentiment = {"score": sentiment_score, "details": {}}
    else:
        sentiment = {"score": 50, "details": {}}

    factors = {
        "momentum": momentum,
        "technical": technical,
        "fundamental": fundamental,
        "volume": volume,
        "risk": risk,
        "sentiment": sentiment,
        "fund_flow": fund_flow,
    }

    # 如果某因子不可用，权重重新分配
    active_weights = dict(weights)
    if not fundamentals:
        del active_weights["fundamental"]
    if sentiment_score is None:
        del active_weights["sentiment"]
    if len(active_weights) < len(weights):
        remaining = sum(active_weights.values())
        if remaining > 0:
            active_weights = {k: v / remaining for k, v in active_weights.items()}

    composite = sum(factors[k]["score"] * active_weights[k] for k in active_weights)

    # 追高惩罚：近20日涨幅>25%或近5日>15%时打折，防止推荐山顶票
    ret_20d = factors["momentum"].get("details", {}).get("return_20d_pct", 0)
    ret_5d = factors["momentum"].get("details", {}).get("return_5d_pct", 0)
    chase_penalty = 0
    if ret_20d > 40:
        chase_penalty = 15  # 极度追高，扣15分
    elif ret_20d > 30:
        chase_penalty = 10
    elif ret_20d > 25:
        chase_penalty = 5
    elif ret_5d > 15:
        chase_penalty = 3  # 近5日涨太多也轻罚
    composite -= chase_penalty

    # 评级
    if composite >= 80:
        rating = "Strong Buy"
    elif composite >= 60:
        rating = "Buy"
    elif composite >= 40:
        rating = "Hold"
    elif composite >= 20:
        rating = "Sell"
    else:
        rating = "Strong Sell"

    return {
        "composite_score": round(composite, 1),
        "rating": rating,
        "factor_scores": {
            k: {"score": v["score"], "details": v["details"]} for k, v in factors.items()
        },
    }


# ═══════════════════════════════════════════════════════════════
# 3. 量化交易信号
# ═══════════════════════════════════════════════════════════════


def _make_signal(signal_type, name, direction, strength, description, price=None, value=None):
    return {
        "type": signal_type,
        "name": name,
        "direction": direction,
        "strength": strength,
        "description": description,
        "price": price,
        "value": value or {},
    }


def detect_ma_crossover(df):
    """MA金叉/死叉信号"""
    signals: list[dict[str, Any]] = []
    if df.empty or len(df) < 3:
        return signals

    last, prev = df.iloc[-1], df.iloc[-2]
    price = round(last.get("收盘", 0), 2)

    for fast, slow, name in [("MA5", "MA10", "MA5/MA10"), ("MA10", "MA20", "MA10/MA20")]:
        if fast not in last or slow not in last:
            continue
        fv, sv = last.get(fast), last.get(slow)
        fp, sp = prev.get(fast), prev.get(slow)
        if any(x is None or np.isnan(x) for x in [fv, sv, fp, sp]):
            continue

        if fv > sv and fp <= sp:
            signals.append(
                _make_signal(
                    f"ma_golden_cross_{name}",
                    f"{name}金叉",
                    "bullish",
                    4,
                    f"{fast}上穿{slow}，短期趋势转多",
                    price,
                )
            )
        elif fv < sv and fp >= sp:
            signals.append(
                _make_signal(
                    f"ma_death_cross_{name}",
                    f"{name}死叉",
                    "bearish",
                    4,
                    f"{fast}下穿{slow}，短期趋势转空",
                    price,
                )
            )
    return signals


def detect_macd_crossover(df):
    """MACD金叉/死叉信号"""
    signals: list[dict[str, Any]] = []
    if df.empty or len(df) < 3:
        return signals
    last, prev = df.iloc[-1], df.iloc[-2]
    price = round(last.get("收盘", 0), 2)

    for col in ["DIF", "DEA"]:
        if col not in last or col not in prev:
            return signals

    if last["DIF"] > last["DEA"] and prev["DIF"] <= prev["DEA"]:
        signals.append(
            _make_signal(
                "macd_golden_cross", "MACD金叉", "bullish", 4, "DIF上穿DEA，趋势转多", price
            )
        )
    elif last["DIF"] < last["DEA"] and prev["DIF"] >= prev["DEA"]:
        signals.append(
            _make_signal(
                "macd_death_cross", "MACD死叉", "bearish", 4, "DIF下穿DEA，趋势转空", price
            )
        )
    return signals


def detect_adx_trend(df):
    """ADX趋势强度信号"""
    signals: list[dict[str, Any]] = []
    if df.empty or len(df) < 20:
        return signals
    last = df.iloc[-1]
    adx = last.get("ADX")
    di_p = last.get("DI_PLUS")
    di_m = last.get("DI_MINUS")
    if any(x is None or np.isnan(x) for x in [adx, di_p, di_m]):
        return signals

    direction = "bullish" if di_p > di_m else "bearish"
    strength = min(5, int(adx / 10)) if adx > 25 else 1

    if adx > 25:
        signals.append(
            _make_signal(
                "adx_trend",
                "ADX趋势确立",
                direction,
                strength,
                f"ADX={adx:.1f}，DI+={di_p:.1f}，DI-={di_m:.1f}，{'多头' if direction == 'bullish' else '空头'}趋势",
                round(last.get("收盘", 0), 2),
                {"adx": round(adx, 1), "di_plus": round(di_p, 1), "di_minus": round(di_m, 1)},
            )
        )
    elif adx < 20:
        signals.append(
            _make_signal(
                "adx_ranging",
                "ADX震荡市场",
                "neutral",
                1,
                f"ADX={adx:.1f}<20，市场处于震荡盘整",
                round(last.get("收盘", 0), 2),
            )
        )
    return signals


def detect_channel_breakout(df, lookback=20):
    """通道突破信号"""
    signals: list[dict[str, Any]] = []
    if df.empty or len(df) < lookback + 1:
        return signals

    recent = df.tail(lookback + 1)
    current = recent.iloc[-1]
    prior = recent.iloc[:-1]

    high_high = prior["最高"].max()
    low_low = prior["最低"].min()
    price = round(current["收盘"], 2)

    avg_vol = prior["成交量"].mean()
    vol_ratio = current["成交量"] / avg_vol if avg_vol > 0 else 1

    # 向上突破
    if current["最高"] > high_high:
        strength = 4 if vol_ratio > 1.2 else 3
        signals.append(
            _make_signal(
                "channel_breakout_up",
                f"{lookback}日通道突破",
                "bullish",
                strength,
                f"突破{lookback}日高点{high_high:.2f}{'，量能确认' if vol_ratio > 1.2 else ''}",
                price,
                {"breakout_level": round(high_high, 2), "volume_ratio": round(vol_ratio, 2)},
            )
        )
    # 向下突破
    elif current["最低"] < low_low:
        strength = 4 if vol_ratio > 1.2 else 3
        signals.append(
            _make_signal(
                "channel_breakout_down",
                f"{lookback}日通道跌破",
                "bearish",
                strength,
                f"跌破{lookback}日低点{low_low:.2f}{'，量能确认' if vol_ratio > 1.2 else ''}",
                price,
                {"breakout_level": round(low_low, 2), "volume_ratio": round(vol_ratio, 2)},
            )
        )
    return signals


def detect_rsi_reversal(df):
    """RSI超买超卖反转信号"""
    signals: list[dict[str, Any]] = []
    if df.empty or len(df) < 3:
        return signals

    last, prev = df.iloc[-1], df.iloc[-2]
    rsi = last.get("RSI")
    rsi_prev = prev.get("RSI")
    if rsi is None or rsi_prev is None or np.isnan(rsi) or np.isnan(rsi_prev):
        return signals
    price = round(last.get("收盘", 0), 2)

    if rsi < 25 and rsi > rsi_prev:
        signals.append(
            _make_signal(
                "rsi_oversold_bounce",
                "RSI超卖反弹",
                "bullish",
                3,
                f"RSI={rsi:.1f}从超卖区回升，可能出现反弹",
                price,
                {"rsi": round(rsi, 1)},
            )
        )
    elif rsi < 20:
        signals.append(
            _make_signal(
                "rsi_deep_oversold",
                "RSI深度超卖",
                "bullish",
                3,
                f"RSI={rsi:.1f}深度超卖，反弹概率较大",
                price,
                {"rsi": round(rsi, 1)},
            )
        )
    if rsi > 75 and rsi < rsi_prev:
        signals.append(
            _make_signal(
                "rsi_overbought_drop",
                "RSI超买回落",
                "bearish",
                3,
                f"RSI={rsi:.1f}从超买区回落，可能出现回调",
                price,
                {"rsi": round(rsi, 1)},
            )
        )
    elif rsi > 80:
        signals.append(
            _make_signal(
                "rsi_deep_overbought",
                "RSI深度超买",
                "bearish",
                3,
                f"RSI={rsi:.1f}深度超买，回调风险较大",
                price,
                {"rsi": round(rsi, 1)},
            )
        )
    return signals


def detect_bollinger_reversion(df):
    """布林带触边回归信号"""
    signals: list[dict[str, Any]] = []
    if df.empty or len(df) < 20:
        return signals

    last = df.iloc[-1]
    close = last["收盘"]
    price = round(close, 2)
    rsi = last.get("RSI")

    for col in ["BB_UPPER", "BB_LOWER", "BB_MIDDLE"]:
        if col not in last or np.isnan(last.get(col, np.nan)):
            return signals

    upper, lower = last["BB_UPPER"], last["BB_LOWER"]

    if close > upper:
        strength = 3 if (rsi is not None and not np.isnan(rsi) and rsi > 70) else 2
        signals.append(
            _make_signal(
                "bollinger_touch_upper",
                "布林触上轨",
                "bearish",
                strength,
                f"股价{close:.2f}触及布林上轨{upper:.2f}，超买",
                price,
                {"bb_upper": round(upper, 2), "bb_lower": round(lower, 2)},
            )
        )
    elif close < lower:
        strength = 3 if (rsi is not None and not np.isnan(rsi) and rsi < 30) else 2
        signals.append(
            _make_signal(
                "bollinger_touch_lower",
                "布林触下轨",
                "bullish",
                strength,
                f"股价{close:.2f}触及布林下轨{lower:.2f}，超卖",
                price,
                {"bb_upper": round(upper, 2), "bb_lower": round(lower, 2)},
            )
        )
    return signals


def generate_all_signals(df):
    """生成全部量化信号"""
    all_signals = []
    for detector in [
        detect_ma_crossover,
        detect_macd_crossover,
        detect_adx_trend,
        detect_channel_breakout,
        detect_rsi_reversal,
        detect_bollinger_reversion,
    ]:
        try:
            all_signals.extend(detector(df))
        except Exception:
            pass

    bullish = [s for s in all_signals if s["direction"] == "bullish"]
    bearish = [s for s in all_signals if s["direction"] == "bearish"]
    return {
        "signals": all_signals,
        "total_bullish": len(bullish),
        "total_bearish": len(bearish),
        "strongest_bullish_strength": max((s["strength"] for s in bullish), default=0),
        "strongest_bearish_strength": max((s["strength"] for s in bearish), default=0),
    }


def consolidate_signals(signals_dict):
    """汇总信号为整体偏多/空判断"""
    signals = signals_dict.get("signals", [])
    bull_strength = sum(s["strength"] for s in signals if s["direction"] == "bullish")
    bear_strength = sum(s["strength"] for s in signals if s["direction"] == "bearish")
    net = bull_strength - bear_strength

    if net >= 6:
        bias, bias_score = "strong_bullish", 2
    elif net >= 2:
        bias, bias_score = "bullish", 1
    elif net <= -6:
        bias, bias_score = "strong_bearish", -2
    elif net <= -2:
        bias, bias_score = "bearish", -1
    else:
        bias, bias_score = "neutral", 0

    return {
        "bias": bias,
        "bias_score": bias_score,
        "bullish_net_strength": bull_strength,
        "bearish_net_strength": bear_strength,
        "net_score": net,
        "signal_summary": {
            "bullish_count": signals_dict["total_bullish"],
            "bearish_count": signals_dict["total_bearish"],
            "strongest_bullish": signals_dict["strongest_bullish_strength"],
            "strongest_bearish": signals_dict["strongest_bearish_strength"],
        },
    }


# ═══════════════════════════════════════════════════════════════
# 5. 短线/长线风格评估
# ═══════════════════════════════════════════════════════════════


def evaluate_trading_style(kline, fundamentals=None, risk_metrics=None):
    """评估股票适合短线还是长线

    参数:
        kline: 经过 full_technical_analysis 处理后的 DataFrame
        fundamentals: dict，基本面数据（可选）
        risk_metrics: dict，风险指标（可选，若为 None 自动计算）

    返回:
        dict: {short_term_score, long_term_score, style, style_confidence,
               short_term_basis, long_term_basis, factors}
    """
    if kline.empty or len(kline) < 20:
        return {
            "style": "数据不足",
            "short_term_score": 0,
            "long_term_score": 0,
            "short_term_basis": "K线数据不足，无法分析",
            "long_term_basis": "",
        }

    last = kline.iloc[-1].to_dict()  # 转 dict 避免重复 Series.__getitem__
    prev = kline.iloc[-2].to_dict() if len(kline) > 1 else last

    # ── 短线因子计算 ────────────────────────────
    st_factors = {}

    # 1. 动量 (25%)
    ret_5d = float(kline["收盘"].pct_change(5).iloc[-1] * 100) if len(kline) >= 6 else 0
    ret_20d = float(kline["收盘"].pct_change(20).iloc[-1] * 100) if len(kline) >= 21 else 0
    mom_score = min(max((ret_5d * 2 + ret_20d + 30), 0), 100)
    st_factors["动量"] = round(mom_score, 1)

    # 2. 技术指标 (30%)
    tech_score = 50
    # RSI: 40-60 最佳短线区间
    rsi_val = float(last.get("RSI", 50))
    if 40 <= rsi_val <= 60:
        tech_score += 20
    elif rsi_val > 80 or rsi_val < 20:
        tech_score -= 10
    elif rsi_val > 70:
        tech_score -= 5
    # KDJ: K>D 偏多
    k_val, d_val = float(last.get("K", 50)), float(last.get("D", 50))
    if k_val > d_val:
        tech_score += 10
    # MACD: 多头加分
    if last.get("DIF", 0) > last.get("DEA", 0):
        tech_score += 10
    else:
        tech_score -= 5
    # 均线: 股价在MA5上方
    if "MA5" in last and last["收盘"] > last["MA5"]:
        tech_score += 10
    st_factors["技术指标"] = round(min(max(tech_score, 0), 100), 1)

    # 3. 量能 (20%)
    vol_score = 50
    vr = last.get("volume_ratio", 1)
    volume_ratio = (
        float(vr) if vr is not None and not (isinstance(vr, float) and np.isnan(vr)) else 1.0
    )
    if volume_ratio > 1.5:
        vol_score += 30
    elif volume_ratio > 1.2:
        vol_score += 15
    elif volume_ratio < 0.5:
        vol_score -= 15
    # 量价配合: 涨+放量 = 好
    last_change = float(kline["收盘"].pct_change().iloc[-1] * 100) if len(kline) >= 2 else 0
    if last_change > 0 and volume_ratio > 1:
        vol_score += 10
    elif last_change < 0 and volume_ratio > 1.5:
        vol_score -= 10
    st_factors["量能"] = round(min(max(vol_score, 0), 100), 1)

    # 4. 突破信号 (25%)
    break_score = 50
    # 通道突破
    if "channel_high_20" in kline.columns:
        near_high = last["收盘"] >= float(kline["channel_high_20"].iloc[-1]) * 0.98
        if near_high:
            break_score += 25
    # 布林带位置
    if "BB_UPPER" in kline.columns and "BB_LOWER" in kline.columns:
        bb_width = float(last["BB_UPPER"] - last["BB_LOWER"])
        bb_pos = (last["收盘"] - last["BB_LOWER"]) / bb_width if bb_width > 0 else 0.5
        if 0.3 <= bb_pos <= 0.7:
            break_score += 15
        elif bb_pos > 0.95:
            break_score -= 10
    # ADX趋势
    adx_val = float(last.get("ADX", 0))
    if adx_val > 25:
        break_score += 10
    st_factors["突破信号"] = round(min(max(break_score, 0), 100), 1)

    # 综合短线评分
    short_term_score = (
        st_factors["动量"] * 0.25
        + st_factors["技术指标"] * 0.30
        + st_factors["量能"] * 0.20
        + st_factors["突破信号"] * 0.25
    )

    # ── 长线因子计算 ────────────────────────────
    lt_factors = {}

    # 1. 基本面 (40%)
    funda_score = 50
    if fundamentals:
        _result = score_fundamental(fundamentals)
        if isinstance(_result, tuple):
            funda_score = _result[0]
        else:
            funda_score = _result
    lt_factors["基本面"] = round(funda_score, 1)

    # 2. 风险指标 (25%)
    risk_score = 50
    if risk_metrics:
        sharpe = risk_metrics.get("sharpe_ratio")
        if sharpe is not None and not np.isnan(sharpe):
            if sharpe > 1:
                risk_score += 30
            elif sharpe > 0.5:
                risk_score += 15
            elif sharpe < 0:
                risk_score -= 15
        dd = risk_metrics.get("max_drawdown_pct", 0)
        if dd is not None:
            if abs(dd) < 10:
                risk_score += 15
            elif abs(dd) > 30:
                risk_score -= 15
    # 年化波动率低 = 稳定
    vol_pct = risk_metrics.get("annualized_volatility_pct") if risk_metrics else None
    if vol_pct is not None and vol_pct < 25:
        risk_score += 10
    lt_factors["风险控制"] = round(min(max(risk_score, 0), 100), 1)

    # 3. 长期趋势 (20%)
    trend_score = 50
    # 股价在MA60上方
    if "MA60" in last and last["收盘"] > last["MA60"]:
        trend_score += 20
    else:
        trend_score -= 10
    # ADX > 25 趋势确立
    if adx_val > 25:
        trend_score += 10
    elif adx_val < 15:
        trend_score -= 10
    # 60日涨幅
    ret_60d = float(kline["收盘"].pct_change(60).iloc[-1] * 100) if len(kline) >= 61 else 0
    if ret_60d > 15:
        trend_score += 15
    elif ret_60d < -15:
        trend_score -= 15
    lt_factors["长期趋势"] = round(min(max(trend_score, 0), 100), 1)

    # 4. 稳定性 (15%)
    stable_score = 60
    # ATR占比
    atr_ratio = (
        float(last.get("ATR", 0)) / last["收盘"]
        if last["收盘"] > 0 and not pd.isna(last.get("ATR", np.nan))
        else 0.03
    )
    if atr_ratio < 0.02:  # 低波动=稳定
        stable_score += 20
    elif atr_ratio > 0.05:  # 高波动=不稳定
        stable_score -= 15
    # 回撤
    current_dd = risk_metrics.get("current_drawdown_pct") if risk_metrics else 0
    if current_dd is not None and abs(current_dd) < 5:
        stable_score += 10
    lt_factors["稳定性"] = round(min(max(stable_score, 0), 100), 1)

    # 综合长线评分
    long_term_score = (
        lt_factors["基本面"] * 0.40
        + lt_factors["风险控制"] * 0.25
        + lt_factors["长期趋势"] * 0.20
        + lt_factors["稳定性"] * 0.15
    )

    # ── 风格判断 ────────────────────────────────
    st, lt = short_term_score, long_term_score
    diff = st - lt

    if st >= 60 and lt >= 60:
        style = "短线+长线"
        confidence = "高" if max(st, lt) >= 75 else "中"
    elif st >= 60 and diff > 10:
        style = "短线"
        confidence = "高" if st >= 75 else "中"
    elif lt >= 60 and diff < -10:
        style = "长线"
        confidence = "高" if lt >= 75 else "中"
    elif st >= 50 or lt >= 50:
        style = "短线" if st > lt else "长线"
        confidence = "低"
    else:
        style = "观望"
        confidence = "中"

    # ── 分析依据文字 ────────────────────────────
    short_term_basis_parts = []
    # 动量
    if ret_5d > 5:
        short_term_basis_parts.append(f"近5日涨幅{ret_5d:.1f}%，短期动量较强")
    elif ret_5d < -5:
        short_term_basis_parts.append(f"近5日下跌{abs(ret_5d):.1f}%，短期承压")
    else:
        short_term_basis_parts.append(f"近5日涨幅{ret_5d:.1f}%，短期走势平稳")
    # RSI
    if rsi_val > 70:
        short_term_basis_parts.append(f"RSI({rsi_val:.0f})偏高，注意回调风险")
    elif rsi_val < 30:
        short_term_basis_parts.append(f"RSI({rsi_val:.0f})偏低，可能存在超跌反弹机会")
    else:
        short_term_basis_parts.append(f"RSI({rsi_val:.0f})处于中性区间")
    # 成交量
    if volume_ratio > 1.3:
        short_term_basis_parts.append(f"成交量放大至{volume_ratio:.1f}倍均值，资金关注度高")
    elif volume_ratio < 0.7:
        short_term_basis_parts.append(f"成交量萎缩({volume_ratio:.1f}倍均值)，交投不活跃")
    # MACD
    if last.get("DIF", 0) > last.get("DEA", 0):
        short_term_basis_parts.append("MACD处于多头区域")
    else:
        short_term_basis_parts.append("MACD处于空头区域")

    long_term_basis_parts = []
    # 基本面
    if fundamentals:
        roe = fundamentals.get("ROE")
        if roe is not None:
            if roe >= 15:
                long_term_basis_parts.append(f"ROE{roe:.1f}%，盈利能力优秀")
            elif roe >= 10:
                long_term_basis_parts.append(f"ROE{roe:.1f}%，盈利能力良好")
            else:
                long_term_basis_parts.append(f"ROE{roe:.1f}%，盈利能力一般")
        rev_g = fundamentals.get("营收增长")
        if rev_g is not None and rev_g > 10:
            long_term_basis_parts.append(f"营收增长{rev_g:.1f}%，成长性良好")
    # 风险
    if risk_metrics:
        sharpe = risk_metrics.get("sharpe_ratio")
        if sharpe is not None and not np.isnan(sharpe):
            if sharpe > 0.5:
                long_term_basis_parts.append(f"夏普比率{sharpe:.2f}，风险调整收益较好")
            else:
                long_term_basis_parts.append(f"夏普比率{sharpe:.2f}，风险收益偏低")
        dd = risk_metrics.get("max_drawdown_pct")
        if dd is not None:
            long_term_basis_parts.append(f"历史最大回撤{abs(dd):.1f}%")
    # 趋势
    if "MA60" in last:
        if last["收盘"] > last["MA60"]:
            long_term_basis_parts.append(f"股价在MA60({last['MA60']:.2f})上方，长期趋势向上")
        else:
            long_term_basis_parts.append(f"股价在MA60({last['MA60']:.2f})下方，长期趋势承压")
    # ATR
    if atr_ratio < 0.03:
        long_term_basis_parts.append(f"ATR占比{atr_ratio * 100:.1f}%，波动率较低，适合长持")
    elif atr_ratio > 0.05:
        long_term_basis_parts.append(f"ATR占比{atr_ratio * 100:.1f}%，波动率较高")

    return {
        "short_term_score": round(short_term_score, 1),
        "long_term_score": round(long_term_score, 1),
        "style": style,
        "style_confidence": confidence,
        "short_term_basis": "；".join(short_term_basis_parts),
        "long_term_basis": "；".join(long_term_basis_parts)
        if long_term_basis_parts
        else "基本面数据不足，无法评估长线价值",
        "factors": {
            "short_term": st_factors,
            "long_term": lt_factors,
        },
    }
