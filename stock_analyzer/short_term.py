#!/usr/bin/env python
"""短线专项分析模块

从日线K线数据提取短线交易关键指标：
  1. 换手率 & 量能异常检测
  2. 连涨/连跌天数
  3. 尾盘倾向（最后30分钟资金方向）
  4. 主力资金流向摘要
  5. 前日走势节奏
  6. 个股消息催化检测
  7. 短线综合评分
"""


def calc_turnover_signal(kline):
    """换手率信号

    返回: dict — 最新换手率、5日均换手、异常检测
    """
    if kline is None or kline.empty:
        return {"换手率%": 0, "均换手%": 0, "信号": "无数据"}

    # 尝试找换手率列
    turnover_col = None
    for c in kline.columns:
        if "换手" in c or "turnover" in c:
            turnover_col = c
            break

    if turnover_col is None:
        # 用成交量/流通盘估算（粗略）
        if "成交量" in kline.columns:
            latest_vol = float(kline["成交量"].iloc[-1])
            avg_vol = float(kline["成交量"].tail(20).mean())
            ratio = latest_vol / avg_vol if avg_vol > 0 else 1
            return {
                "换手率%": 0,
                "量比": round(ratio, 2),
                "信号": "放量" if ratio > 1.5 else ("缩量" if ratio < 0.5 else "正常"),
            }
        return {"换手率%": 0, "信号": "无数据"}

    latest = float(kline[turnover_col].iloc[-1])
    avg_5 = float(kline[turnover_col].tail(5).mean())
    avg_20 = float(kline[turnover_col].tail(20).mean())

    signal = "正常"
    if latest > avg_20 * 2:
        signal = "异常放量⚠️"
    elif latest > avg_20 * 1.5:
        signal = "放量"
    elif latest < avg_20 * 0.5:
        signal = "缩量"
    elif latest > avg_5 * 1.3:
        signal = "近期放量"

    return {
        "换手率%": round(latest, 2),
        "5日均换手%": round(avg_5, 2),
        "20日均换手%": round(avg_20, 2),
        "信号": signal,
    }


def calc_consecutive_days(kline):
    """连涨/连跌天数

    返回: dict — 当前连涨/连跌天数、方向、统计
    """
    if kline is None or len(kline) < 5:
        return {"方向": "无数据", "天数": 0}

    changes = kline["收盘"].pct_change().dropna()
    if len(changes) < 2:
        return {"方向": "无数据", "天数": 0}

    # 从最近开始往回数
    consecutive = 0
    direction = "涨" if changes.iloc[-1] >= 0 else "跌"

    for i in range(len(changes) - 1, -1, -1):
        if (direction == "涨" and changes.iloc[i] >= 0) or (
            direction == "跌" and changes.iloc[i] < 0
        ):
            consecutive += 1
        else:
            break

    # 历史统计：最近60天最大连涨/连跌
    max_up, max_down = 0, 0
    cur_up, cur_down = 0, 0
    for c in changes.tail(60):
        if c >= 0:
            cur_up += 1
            cur_down = 0
            max_up = max(max_up, cur_up)
        else:
            cur_down += 1
            cur_up = 0
            max_down = max(max_down, cur_down)

    signal = "正常"
    if consecutive >= 5 and direction == "涨":
        signal = "连涨过多⚠️"
    elif consecutive >= 4 and direction == "跌":
        signal = "超跌反弹机会💡"
    elif consecutive >= 3 and direction == "跌":
        signal = "连跌中"

    return {
        "方向": direction,
        "天数": consecutive,
        "信号": signal,
        "近60日最大连涨": max_up,
        "近60日最大连跌": max_down,
    }


def calc_tail_tendency(kline, days=10):
    """尾盘倾向：最近N天尾盘涨跌统计

    用最后1/5的K线涨幅近似模拟尾盘倾向（日线数据局限）
    """
    if kline is None or len(kline) < days:
        return {"尾盘倾向": "无数据"}

    recent = kline.tail(days)
    up_days = (
        len(recent[recent["涨跌幅"] > 0])
        if "涨跌幅" in recent.columns
        else len(recent[recent["收盘"] > recent["开盘"]])
    )

    ratio = up_days / days * 100

    if ratio >= 70:
        tendency = "近期偏强💪"
    elif ratio <= 30:
        tendency = "近期偏弱📉"
    else:
        tendency = "震荡中性"

    return {
        "尾盘倾向": tendency,
        f"近{days}日阳线占比%": round(ratio, 0),
        "近5日涨跌节奏": _calc_rhythm(recent.tail(5)),
    }


def _calc_rhythm(kline_5):
    """最近5天涨跌节奏：如涨-跌-跌-涨-涨"""
    if len(kline_5) < 5:
        return ""
    changes = []
    for i in range(len(kline_5)):
        if "涨跌幅" in kline_5.columns:
            chg = float(kline_5["涨跌幅"].iloc[i])
        else:
            chg = (
                float(kline_5["收盘"].iloc[i])
                / float(kline_5["前收" if "前收" in kline_5.columns else "开盘"].iloc[i])
                - 1
            ) * 100
        changes.append("↑" if chg >= 0 else "↓")
    return "→".join(changes)


def calc_fund_flow_summary(code):
    """主力资金流向摘要（通过缓存层，避免重复网络请求）"""
    try:
        from .cache import cached_fund_flow

        df = cached_fund_flow(code, days=5)
        if df is None or df.empty:
            return {"主力动向": "无数据", "近5日累计(亿)": 0, "今日方向": "无数据"}

        # 精确匹配：'主力净流入-净额'，避免误匹配'主力净流入-净占比'
        main_col = "主力净流入-净额"
        if main_col not in df.columns:
            return {"主力动向": "无数据", "近5日累计(亿)": 0, "今日方向": "无数据"}

        total_5d = df[main_col].sum()
        latest = df[main_col].iloc[-1] if len(df) > 0 else 0

        # 判断主力动向
        if total_5d > 1e8 and latest > 0:
            signal = "主力流入✅"
        elif total_5d < -1e8 and latest < 0:
            signal = "主力流出⚠️"
        elif total_5d > 0:
            signal = "主力小幅流入"
        elif total_5d < 0:
            signal = "主力小幅流出"
        else:
            signal = "主力分歧"

        return {
            "主力动向": signal,
            "近5日累计(亿)": round(total_5d / 1e8, 2),
            "今日方向": "流入" if latest > 0 else "流出",
        }
    except Exception:
        return {"主力动向": "获取失败", "近5日累计(亿)": 0, "今日方向": "无数据"}


def calc_news_catalyst(code):
    """个股消息催化检测"""
    try:
        from .cache import cached_stock_news

        news = cached_stock_news(code)
        if news is None or news.empty:
            return {"消息催化": "无近期消息"}

        # 简单关键词检测
        keywords = [
            "业绩",
            "合同",
            "中标",
            "重组",
            "回购",
            "增持",
            "减持",
            "分红",
            "减持",
            "预增",
            "预减",
            "涨停",
            "跌停",
            "突破",
            "合作",
            "订单",
        ]
        found = []
        for _, row in news.head(20).iterrows():
            title = str(row.get("标题", row.get("title", "")))
            content = str(row.get("内容", row.get("content", "")))
            text = title + content
            for kw in keywords:
                if kw in text and kw not in found:
                    found.append(kw)

        if found:
            return {"消息催化": f"关注: {', '.join(found[:5])}", "近期消息数": len(news)}
        return {"消息催化": "无明显催化", "近期消息数": len(news)}
    except Exception:
        return {"消息催化": "获取失败"}


def short_term_score(kline, code=None):
    """短线综合评分（0-100）v2.0

    评分因子：
      动量(20%) + 量能(15%) + 波动(15%) + 组合信号(25%) + 多周期共振(15%) + 位置(10%)
    """
    if kline is None or len(kline) < 20:
        return {"短线评分": 0, "评级": "数据不足"}

    # 动量：近5日涨幅
    n5 = float((kline["收盘"].iloc[-1] / kline["收盘"].iloc[-6] - 1) * 100) if len(kline) > 5 else 0
    mom_score = min(max(n5 * 3 + 50, 0), 100)

    # 量能：量比
    if "成交量" in kline.columns:
        vol_latest = float(kline["成交量"].iloc[-1])
        vol_avg = float(kline["成交量"].tail(20).mean())
        vol_ratio = vol_latest / vol_avg if vol_avg > 0 else 1
        vol_score = min(vol_ratio * 40 + 40, 100)
    else:
        vol_score = 50
        vol_ratio = 1

    # 波动：ATR/价格
    atr = float(kline.iloc[-1].get("ATR", 0))
    price = float(kline["收盘"].iloc[-1])
    atr_pct = atr / price * 100 if price > 0 else 0
    vola_score = min(atr_pct * 15, 100)

    # 组合信号分数（新）
    combo = calc_combo_signals(kline, code)
    combo_score = max((combo["强度"] + 4) / 8 * 100, 0)  # -4~+4 → 0~100

    # 多周期共振（新）
    resonance_score = 50
    if code:
        try:
            mr = calc_multi_timeframe_resonance(code)
            resonance_score = max((mr["共振强度"] + 60) / 120 * 100, 0)
        except Exception:
            pass

    # 位置：距20日均线
    ma20 = float(kline["收盘"].tail(20).mean())
    dist_pct = (price - ma20) / ma20 * 100
    pos_score = 60 if -3 < dist_pct < 5 else (40 if dist_pct < -5 else 50)

    total = (
        mom_score * 0.20
        + vol_score * 0.15
        + vola_score * 0.15
        + combo_score * 0.25
        + resonance_score * 0.15
        + pos_score * 0.10
    )

    rating = (
        "强力短线"
        if total >= 75
        else ("短线可做" if total >= 60 else ("观望" if total >= 45 else "不建议"))
    )

    # 风险提示
    risks = []
    if n5 > 15:
        risks.append("近5日涨幅过大")
    rsi = _calc_rsi(kline)
    if rsi > 75:
        risks.append("RSI过热")
    if rsi < 25:
        risks.append("RSI过冷")
    consecutive = calc_consecutive_days(kline)
    if consecutive["天数"] >= 4 and consecutive["方向"] == "涨":
        risks.append("连涨过多")

    return {
        "短线评分": round(total, 1),
        "评级": rating,
        "风险": risks if risks else ["无明显风险"],
        "动量分": round(mom_score, 1),
        "量能分": round(vol_score, 1),
        "波动分": round(vola_score, 1),
        "组合信号分": round(combo_score, 1),
        "共振分": round(resonance_score, 1),
        "ATR占比%": round(atr_pct, 2),
        "组合信号": combo,
    }


def _calc_rsi(kline, period=14):
    delta = kline["收盘"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    return float(100 - (100 / (1 + rs.iloc[-1])))


def _calc_macd_signal(kline):
    """返回 MACD 状态：金叉/多头/死叉/空头"""
    close = kline["收盘"]
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    bar = 2 * (dif - dea)
    if bar.iloc[-1] > bar.iloc[-2] > 0 and dif.iloc[-1] > dea.iloc[-1]:
        return "金叉"
    elif dif.iloc[-1] > dea.iloc[-1]:
        return "多头"
    elif bar.iloc[-1] < bar.iloc[-2] < 0 and dif.iloc[-1] < dea.iloc[-1]:
        return "死叉"
    else:
        return "空头"


def _calc_kdj_signal(kline):
    """返回 KDJ 状态"""
    high9 = kline["最高"].rolling(9).max()
    low9 = kline["最低"].rolling(9).min()
    rsv = (kline["收盘"] - low9) / (high9 - low9 + 1e-10) * 100
    k = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    d = k.ewm(alpha=1 / 3, adjust=False).mean()
    if k.iloc[-1] > d.iloc[-1] and k.iloc[-2] <= d.iloc[-2]:
        return "金叉"
    elif k.iloc[-1] > d.iloc[-1]:
        return "多头"
    elif k.iloc[-1] < d.iloc[-1] and k.iloc[-2] >= d.iloc[-2]:
        return "死叉"
    else:
        return "空头"


def calc_combo_signals(kline, code=None):
    """组合买卖信号（MACD + KDJ + RSI + 量能 四维共振）

    返回 dict：信号(买入/关注/卖出/观望) + 各维度状态
    """
    if kline is None or len(kline) < 26:
        return {"信号": "数据不足", "强度": 0}

    macd = _calc_macd_signal(kline)
    kdj = _calc_kdj_signal(kline)
    rsi = _calc_rsi(kline)

    vol_latest = float(kline["成交量"].iloc[-1])
    vol_avg = float(kline["成交量"].tail(20).mean())
    vol_ratio = vol_latest / vol_avg if vol_avg > 0 else 1

    # 近5日涨跌幅
    p5 = float((kline["收盘"].iloc[-1] / kline["收盘"].iloc[-6] - 1) * 100) if len(kline) > 5 else 0

    # 信号强度计数（-4 ~ +4）
    score = 0
    details = []

    # MACD
    if macd == "金叉":
        score += 2
        details.append("MACD金叉✅")
    elif macd == "多头":
        score += 1
        details.append("MACD多头")
    elif macd == "死叉":
        score -= 2
        details.append("MACD死叉❌")
    else:
        score -= 1
        details.append("MACD空头")

    # KDJ
    if kdj == "金叉":
        score += 2
        details.append("KDJ金叉✅")
    elif kdj == "多头":
        score += 1
        details.append("KDJ多头")
    elif kdj == "死叉":
        score -= 2
        details.append("KDJ死叉❌")
    else:
        score -= 1
        details.append("KDJ空头")

    # RSI
    if 40 < rsi < 70:
        score += 1
        details.append(f"RSI{rsi:.0f}健康")
    elif rsi < 30:
        score -= 1
        details.append(f"RSI{rsi:.0f}超卖")
    elif rsi > 80:
        score -= 2
        details.append(f"RSI{rsi:.0f}超买⚠️")

    # 量能
    if vol_ratio > 1.5:
        score += 1
        details.append(f"放量{vol_ratio:.1f}倍")
    elif vol_ratio < 0.5:
        score -= 1
        details.append(f"缩量{vol_ratio:.1f}倍")

    # 综合判断
    if score >= 4:
        signal = "🟢 买入"
    elif score >= 2:
        signal = "🟡 关注"
    elif score <= -4:
        signal = "🔴 卖出"
    elif score <= -2:
        signal = "⚠️ 偏空"
    else:
        signal = "⚪ 观望"

    return {
        "信号": signal,
        "强度": score,
        "详情": details,
        "MACD": macd,
        "KDJ": kdj,
        "RSI": round(rsi, 1),
        "量比": round(vol_ratio, 2),
        "近5日%": round(p5, 1),
    }


def calc_multi_timeframe_resonance(code):
    """多周期共振分析：对比日线+60分钟线 MACD/KDJ 方向

    返回：共振强度(0-100) + 日线信号 + 60分钟信号
    """
    try:
        from .cache import cached_kline
        from .fetcher import get_intraday_kline

        daily = cached_kline(code)
        intraday = get_intraday_kline(code, scale=60, count=120)

        daily_signal = calc_combo_signals(daily, code) if not daily.empty else None
        intra_signal = calc_combo_signals(intraday, code) if not intraday.empty else None

        if daily_signal is None:
            return {"共振强度": 0, "状态": "日线数据不足"}

        resonance = 0

        # 日线+60分钟 MACD 同向 → +30
        if daily_signal.get("MACD") and intra_signal and intra_signal.get("MACD"):
            if daily_signal["MACD"] in ("金叉", "多头") and intra_signal["MACD"] in (
                "金叉",
                "多头",
            ):
                resonance += 30
            elif daily_signal["MACD"] in ("死叉", "空头") and intra_signal["MACD"] in (
                "死叉",
                "空头",
            ):
                resonance -= 30

        # 日线+60分钟 KDJ 同向 → +25
        if daily_signal.get("KDJ") and intra_signal and intra_signal.get("KDJ"):
            if daily_signal["KDJ"] in ("金叉", "多头") and intra_signal["KDJ"] in ("金叉", "多头"):
                resonance += 25
            elif daily_signal["KDJ"] in ("死叉", "空头") and intra_signal["KDJ"] in (
                "死叉",
                "空头",
            ):
                resonance -= 25

        # 日线信号强度（-4~+4→0~40）
        resonance += daily_signal["强度"] * 5

        # 60分钟线信号
        if intra_signal:
            resonance += intra_signal["强度"] * 3

        status = (
            "强共振看多"
            if resonance >= 60
            else (
                "偏多"
                if resonance >= 20
                else ("震荡" if resonance > -20 else ("偏空" if resonance > -60 else "强共振看空"))
            )
        )

        return {
            "共振强度": resonance,
            "状态": status,
            "日线信号": daily_signal,
            "60分钟信号": intra_signal,
        }
    except Exception:
        return {"共振强度": 0, "状态": "计算异常"}
