"""技术分析 & 基本面评分模块"""

import numpy as np
import pandas as pd

from .config import MA_WINDOWS, MACD_FAST, MACD_SIGNAL, MACD_SLOW, RSI_PERIOD

# ── 技术指标计算 ──────────────────────────────────


def calc_ma(df, windows=None):
    """计算移动均线"""
    if windows is None:
        windows = MA_WINDOWS
    for w in windows:
        df[f"MA{w}"] = df["收盘"].rolling(w).mean()
    return df


def calc_macd(df, fast=None, slow=None, signal=None):
    """计算 MACD"""
    fast = fast or MACD_FAST
    slow = slow or MACD_SLOW
    signal = signal or MACD_SIGNAL

    exp1 = df["收盘"].ewm(span=fast, adjust=False).mean()
    exp2 = df["收盘"].ewm(span=slow, adjust=False).mean()
    df["DIF"] = exp1 - exp2
    df["DEA"] = df["DIF"].ewm(span=signal, adjust=False).mean()
    df["MACD"] = 2 * (df["DIF"] - df["DEA"])
    return df


def calc_rsi(df, period=None):
    """计算 RSI"""
    period = period or RSI_PERIOD
    delta = df["收盘"].diff()
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))
    return df


def calc_kdj(df, n=9):
    """计算 KDJ — 向量化版本

    K_i = 2/3*K_{i-1} + 1/3*RSV_i 本质是 EMA(alpha=1/3)
    D_i = 2/3*D_{i-1} + 1/3*K_i 同上
    用 pandas ewm 替代逐行 for 循环，5000 只股票从 ~30s 降到 <1s
    """
    low_n = df["最低"].rolling(n).min()
    high_n = df["最高"].rolling(n).max()
    rsv = (df["收盘"] - low_n) / (high_n - low_n).replace(0, np.nan) * 100

    df["K"] = 50.0
    df["D"] = 50.0

    if len(df) > n:
        # n-1 位置插入种子值 50，使 ewm 结果与原递推公式完全一致
        rsv_from_seed = rsv.iloc[n - 1 :].copy()
        rsv_from_seed.iloc[0] = 50.0
        k_ema = rsv_from_seed.ewm(alpha=1 / 3, adjust=False).mean()
        d_ema = k_ema.ewm(alpha=1 / 3, adjust=False).mean()
        df.loc[df.index[n - 1 :], "K"] = k_ema.values
        df.loc[df.index[n - 1 :], "D"] = d_ema.values

    df["J"] = 3 * df["K"] - 2 * df["D"]
    return df


def calc_atr(df, period=14):
    """计算平均真实波幅 ATR"""
    high, low, close = df["最高"], df["最低"], df["收盘"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["ATR"] = tr.rolling(period).mean()
    return df


def calc_bollinger(df, period=20, std_dev=2):
    """计算布林带"""
    if df.empty or len(df) < period:
        return df
    middle = df["收盘"].rolling(period).mean()
    std = df["收盘"].rolling(period).std()
    df["BB_MIDDLE"] = middle
    df["BB_UPPER"] = middle + std_dev * std
    df["BB_LOWER"] = middle - std_dev * std
    return df


def calc_adx(df, period=14):
    """计算 ADX 趋势强度指标"""
    if df.empty or len(df) < period + 1:
        return df
    high, low, close = df["最高"], df["最低"], df["收盘"]
    prev_close = close.shift(1)

    # 真实波幅 TR
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    # 方向移动
    up_move = high.diff()
    down_move = low.diff()

    dm_plus = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0), index=df.index)
    dm_minus = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0), index=df.index
    )

    # Wilder 平滑 (EMA with alpha=1/period)
    alpha = 1 / period
    tr_smooth = tr.ewm(alpha=alpha, adjust=False).mean()
    dm_plus_smooth = dm_plus.ewm(alpha=alpha, adjust=False).mean()
    dm_minus_smooth = dm_minus.ewm(alpha=alpha, adjust=False).mean()

    di_plus = 100 * dm_plus_smooth / tr_smooth.replace(0, np.nan)
    di_minus = 100 * dm_minus_smooth / tr_smooth.replace(0, np.nan)

    dx = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, np.nan)
    adx = dx.ewm(alpha=alpha, adjust=False).mean()

    df["ADX"] = adx
    df["DI_PLUS"] = di_plus
    df["DI_MINUS"] = di_minus
    return df


def calc_support_resistance(df, lookback=60):
    """计算近期支撑位与压力位（基于波段转折点 + 均线）"""
    from scipy.signal import argrelextrema

    recent = df.tail(lookback)
    current_price = recent["收盘"].iloc[-1]

    lows = recent["最低"].values
    highs = recent["最高"].values
    # 用 scipy 向量化找局部极值，替代 Python for 循环
    swing_low_idx = argrelextrema(lows, np.less, order=1)[0]
    swing_high_idx = argrelextrema(highs, np.greater, order=1)[0]
    swing_lows = lows[swing_low_idx].tolist()
    swing_highs = highs[swing_high_idx].tolist()

    # 支撑位：当前价下方的波段低点，取最近的两个（按与当前价的接近程度）
    supports = sorted(set(round(s, 2) for s in swing_lows if s < current_price), reverse=True)[:2]

    # 压力位：当前价上方的波段高点，取最近的两个
    resistances = sorted(set(round(r, 2) for r in swing_highs if r > current_price))[:2]

    # 均线支撑
    ma_levels = {}
    for w in [20, 60]:
        col = f"MA{w}"
        if col in df.columns:
            val = df.iloc[-1].get(col)
            if val and not np.isnan(val):
                ma_levels[f"MA{w}"] = round(val, 2)

    return {
        "支撑位": supports or [round(current_price * 0.95, 2)],
        "压力位": resistances or [round(current_price * 1.05, 2)],
        "均线支撑": ma_levels,
    }


def calc_stop_levels(current_price, atr, support, resistance):
    """根据 ATR 和支撑/压力位给出止损止盈参考"""
    if not atr or np.isnan(atr):
        atr = current_price * 0.03  # 无 ATR 时按 3% 估算

    stop_loss = (
        round(max(current_price - 2 * atr, support * 0.98), 2)
        if support
        else round(current_price * 0.95, 2)
    )
    take_profit = (
        round(min(current_price + 3 * atr, resistance * 1.02), 2)
        if resistance
        else round(current_price * 1.15, 2)
    )

    return {
        "止损参考价": stop_loss,
        "止损幅度%": round((stop_loss / current_price - 1) * 100, 2),
        "止盈参考价": take_profit,
        "止盈幅度%": round((take_profit / current_price - 1) * 100, 2),
        "ATR": round(atr, 3),
        "ATR占比%": round(atr / current_price * 100, 2),
    }


def full_technical_analysis(df):
    """完整技术分析：MA + MACD + RSI + KDJ + ATR + Bollinger + ADX

    注意：直接修改并返回传入的 DataFrame（不再 copy），节省内存。
    """
    df = df.sort_values("日期")
    df = calc_ma(df)
    df = calc_macd(df)
    df = calc_rsi(df)
    df = calc_kdj(df)
    df = calc_atr(df)
    df = calc_bollinger(df)
    df = calc_adx(df)
    return df


def get_technical_summary(df):
    """提取技术分析结论"""
    if df.empty:
        return {}
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    # 均线判断
    ma_status = {}
    for w in [5, 10, 20, 60]:
        if f"MA{w}" in last and not np.isnan(last[f"MA{w}"]):
            ma_status[f"MA{w}"] = {
                "值": round(last[f"MA{w}"], 2),
                "股价位置": "上方" if last["收盘"] > last[f"MA{w}"] else "下方",
            }

    # MACD 判断
    macd_signal = (
        "金叉"
        if (last["DIF"] > last["DEA"] and prev["DIF"] <= prev["DEA"])
        else "死叉"
        if (last["DIF"] < last["DEA"] and prev["DIF"] >= prev["DEA"])
        else "多头"
        if last["DIF"] > last["DEA"]
        else "空头"
    )

    # RSI 判断
    rsi_val = last.get("RSI", 50)
    if pd.isna(rsi_val):
        rsi_signal = "未知"
    elif rsi_val > 80:
        rsi_signal = "超买"
    elif rsi_val < 20:
        rsi_signal = "超卖"
    else:
        rsi_signal = "中性"

    # KDJ 判断
    k_val = last.get("K", 50)
    d_val = last.get("D", 50)
    j_val = last.get("J", 50)
    if pd.isna(k_val):
        kdj_signal = "未知"
    elif k_val > d_val and prev.get("K", 0) <= prev.get("D", 0):
        kdj_signal = "金叉"
    elif k_val < d_val and prev.get("K", 0) >= prev.get("D", 0):
        kdj_signal = "死叉"
    elif k_val > 80 and d_val > 80:
        kdj_signal = "超买"
    elif k_val < 20 and d_val < 20:
        kdj_signal = "超卖"
    else:
        kdj_signal = "中性"

    # 支撑/压力 & 止损止盈
    sr = calc_support_resistance(df, lookback=60)
    current_price = round(last["收盘"], 2)
    atr_val = last.get("ATR", np.nan)
    sup = sr["支撑位"][0] if sr["支撑位"] else None
    res = sr["压力位"][0] if sr["压力位"] else None
    stop_ref = calc_stop_levels(current_price, atr_val, sup, res)

    return {
        "最新收盘": current_price,
        "涨跌幅": round(last.get("涨跌幅", 0), 2),
        "均线": ma_status,
        "ma_status": ma_status,
        "MACD": {
            "DIF": round(last.get("DIF", 0), 3),
            "DEA": round(last.get("DEA", 0), 3),
            "信号": macd_signal,
        },
        "macd_signal": macd_signal,
        "RSI": {"值": round(rsi_val, 1) if not pd.isna(rsi_val) else None, "信号": rsi_signal},
        "rsi_value": round(rsi_val, 1) if not pd.isna(rsi_val) else None,
        "rsi_signal": rsi_signal,
        "KDJ": {
            "K": round(k_val, 1),
            "D": round(d_val, 1),
            "J": round(j_val, 1),
            "信号": kdj_signal,
        },
        "kdj_signal": kdj_signal,
        "近5日涨跌幅": round((last["收盘"] / df.iloc[-6]["收盘"] - 1) * 100, 2)
        if len(df) >= 6
        else None,
        "近20日涨跌幅": round((last["收盘"] / df.iloc[-21]["收盘"] - 1) * 100, 2)
        if len(df) >= 21
        else None,
        "支撑压力": sr,
        "止损止盈参考": stop_ref,
    }


def score_stocks_in_sector(stocks_df):
    """板块内个股综合评分"""
    df = stocks_df.copy()
    df["个股评分"] = (
        df["涨跌幅"].rank(pct=True) * 0.4
        + df["量比"].rank(pct=True) * 0.3
        + df["振幅"].rank(pct=True) * 0.3
    )
    return df.sort_values("个股评分", ascending=False)


def score_fundamental(fundamentals):
    """基本面评分 (0-100)"""
    score = 50  # 基准分
    details = {}

    if fundamentals.get("ROE") is not None:
        roe = fundamentals["ROE"]
        details["ROE"] = roe
        if roe > 20:
            score += 20
        elif roe > 15:
            score += 15
        elif roe > 10:
            score += 10
        elif roe > 5:
            score += 5
        else:
            score -= 10

    if fundamentals.get("营收增长") is not None:
        rev_g = fundamentals["营收增长"]
        details["营收增长"] = rev_g
        if rev_g > 0.3:
            score += 15
        elif rev_g > 0.2:
            score += 10
        elif rev_g > 0.1:
            score += 5
        elif rev_g < 0:
            score -= 15

    if fundamentals.get("净利润增长") is not None:
        np_g = fundamentals["净利润增长"]
        details["净利润增长"] = np_g
        if np_g > 0.3:
            score += 15
        elif np_g > 0.2:
            score += 10
        elif np_g > 0.1:
            score += 5
        elif np_g < 0:
            score -= 15

    if fundamentals.get("毛利率") is not None:
        gm = fundamentals["毛利率"]
        details["毛利率"] = gm
        if gm > 0.6:
            score += 10
        elif gm > 0.4:
            score += 5
        elif gm < 0.2:
            score -= 5

    score = max(0, min(100, score))
    return score, details
