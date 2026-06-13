"""K线形态识别 — 日本蜡烛图形态检测 + 中文解读

提供两种接口：
1. detect_patterns(df) -> list[dict]   # 最近出现的形态列表
2. generate_kline_interpretation(df) -> dict   # 完整的K线形态解读
"""

import pandas as pd

# ═══════════════════════════════════════════
# 单根K线形态
# ═══════════════════════════════════════════


def _body(row):
    """实体大小"""
    return abs(float(row["收盘"]) - float(row["开盘"]))


def _upper_shadow(row):
    """上影线长度"""
    return float(row["最高"]) - max(float(row["收盘"]), float(row["开盘"]))


def _lower_shadow(row):
    """下影线长度"""
    return min(float(row["收盘"]), float(row["开盘"])) - float(row["最低"])


def _body_ratio(row):
    """实体占比 (实体/总波幅)"""
    total = float(row["最高"]) - float(row["最低"])
    if total <= 0:
        return 0
    return _body(row) / total


def is_big_bullish(row, threshold=0.03):
    """大阳线：实体占比>60%且涨幅>threshold"""
    price = float(row["收盘"])
    open_p = float(row["开盘"])
    if open_p <= 0:
        return False
    chg = (price - open_p) / open_p
    return chg > threshold and _body_ratio(row) > 0.6


def is_big_bearish(row, threshold=0.03):
    """大阴线：实体占比>60%且跌幅>threshold"""
    price = float(row["收盘"])
    open_p = float(row["开盘"])
    if open_p <= 0:
        return False
    chg = (price - open_p) / open_p
    return chg < -threshold and _body_ratio(row) > 0.6


def is_doji(row, threshold=0.001):
    """十字星：实体极小，上下影线明显"""
    body = _body(row)
    total = float(row["最高"]) - float(row["最低"])
    if total <= 0:
        return False
    ratio = body / total
    upper = _upper_shadow(row)
    lower = _lower_shadow(row)
    return ratio < 0.15 and upper > body * 2 and lower > body * 2


def is_hammer(row, trend="down"):
    """锤子线：下跌趋势末端的下影线极长小实体"""
    body = _body(row)
    lower = _lower_shadow(row)
    upper = _upper_shadow(row)
    total = float(row["最高"]) - float(row["最低"])
    if total <= 0 or body <= 0:
        return False
    if trend != "down":
        return False
    return lower >= body * 2 and upper <= body * 0.5 and _body_ratio(row) < 0.4


def is_inverted_hammer(row, trend="down"):
    """倒锤子：下跌趋势末端的上影线极长小实体"""
    body = _body(row)
    lower = _lower_shadow(row)
    upper = _upper_shadow(row)
    total = float(row["最高"]) - float(row["最低"])
    if total <= 0 or body <= 0:
        return False
    if trend != "down":
        return False
    return upper >= body * 2 and lower <= body * 0.5 and _body_ratio(row) < 0.4


def is_shooting_star(row, trend="up"):
    """射击之星：上升趋势末端上影线极长小实体，看跌"""
    if trend != "up":
        return False
    return is_inverted_hammer(row, trend="down")  # same shape, different context


def is_hanging_man(row, trend="up"):
    """吊颈线：上升趋势末端下影线极长小实体，看跌"""
    if trend != "up":
        return False
    return is_hammer(row, trend="down")  # same shape, different context


# ═══════════════════════════════════════════
# 两根K线形态
# ═══════════════════════════════════════════


def is_bullish_engulfing(prev, curr):
    """看涨吞没：前阴后阳，阳线实体完全覆盖阴线实体"""
    p_open, p_close = float(prev["开盘"]), float(prev["收盘"])
    c_open, c_close = float(curr["开盘"]), float(curr["收盘"])
    if p_close >= p_open:  # prev must be bearish
        return False
    if c_close <= c_open:  # curr must be bullish
        return False
    return c_open <= p_close and c_close >= p_open


def is_bearish_engulfing(prev, curr):
    """看跌吞没：前阳后阴，阴线实体完全覆盖阳线实体"""
    p_open, p_close = float(prev["开盘"]), float(prev["收盘"])
    c_open, c_close = float(curr["开盘"]), float(curr["收盘"])
    if p_close <= p_open:  # prev must be bullish
        return False
    if c_close >= c_open:  # curr must be bearish
        return False
    return c_open >= p_close and c_close <= p_open


def is_bullish_harami(prev, curr):
    """看涨孕线：前大阴线后小阳线，阳线在阴线实体内"""
    p_open, p_close = float(prev["开盘"]), float(prev["收盘"])
    c_open, c_close = float(curr["开盘"]), float(curr["收盘"])
    if p_close >= p_open:  # prev must be bearish
        return False
    if c_close <= c_open:  # curr must be bullish
        return False
    p_body = abs(p_close - p_open)
    c_body = abs(c_close - c_open)
    return p_body > c_body * 1.5 and c_open >= p_close and c_close <= p_open


def is_bearish_harami(prev, curr):
    """看跌孕线：前大阳线后小阴线，阴线在阳线实体内"""
    p_open, p_close = float(prev["开盘"]), float(prev["收盘"])
    c_open, c_close = float(curr["开盘"]), float(curr["收盘"])
    if p_close <= p_open:  # prev must be bullish
        return False
    if c_close >= c_open:  # curr must be bearish
        return False
    p_body = abs(p_close - p_open)
    c_body = abs(c_close - c_open)
    return p_body > c_body * 1.5 and c_open <= p_close and c_close >= p_open


def is_dark_cloud_cover(prev, curr):
    """乌云盖顶：前大阳线后阴线高开低走，收盘在前阳线中点以下"""
    p_open, p_close = float(prev["开盘"]), float(prev["收盘"])
    c_open, c_close = float(curr["开盘"]), float(curr["收盘"])
    if p_close <= p_open:
        return False
    if c_close >= c_open:
        return False
    p_body = p_close - p_open
    p_mid = p_open + p_body / 2
    return c_open > p_close and c_close < p_mid and c_close > p_open


def is_piercing_pattern(prev, curr):
    """刺透形态：前大阴线后阳线低开高走，收盘在前阴线中点以上"""
    p_open, p_close = float(prev["开盘"]), float(prev["收盘"])
    c_open, c_close = float(curr["开盘"]), float(curr["收盘"])
    if p_close >= p_open:
        return False
    if c_close <= c_open:
        return False
    p_body = p_open - p_close
    p_mid = p_close + p_body / 2
    return c_open < p_close and c_close > p_mid and c_close < p_open


# ═══════════════════════════════════════════
# 三根K线形态
# ═══════════════════════════════════════════


def is_morning_star(r1, r2, r3):
    """启明星（早晨之星）：阴线->小实体(跳空)->阳线回补，底部反转"""
    p1_close, p1_open = float(r1["收盘"]), float(r1["开盘"])
    p2_body = _body(r2)
    p2_total = float(r2["最高"]) - float(r2["最低"])
    p3_close, p3_open = float(r3["收盘"]), float(r3["开盘"])
    if p1_close >= p1_open:
        return False  # day1 must be bearish
    if p2_total <= 0 or p2_body / p2_total > 0.3:
        return False  # day2 small body
    if p3_close <= p3_open:
        return False  # day3 must be bullish
    return p3_close > (p1_open + p1_close) / 2 and float(r2["最高"]) < min(
        float(r1["收盘"]), float(r3["开盘"])
    )


def is_evening_star(r1, r2, r3):
    """黄昏之星：阳线->小实体(跳空)->阴线回落，顶部反转"""
    p1_close, p1_open = float(r1["收盘"]), float(r1["开盘"])
    p2_body = _body(r2)
    p2_total = float(r2["最高"]) - float(r2["最低"])
    p3_close, p3_open = float(r3["收盘"]), float(r3["开盘"])
    if p1_close <= p1_open:
        return False
    if p2_total <= 0 or p2_body / p2_total > 0.3:
        return False
    if p3_close >= p3_open:
        return False
    return p3_close < (p1_open + p1_close) / 2 and float(r2["最低"]) > max(
        float(r1["收盘"]), float(r3["开盘"])
    )


def is_three_white_soldiers(r1, r2, r3):
    """红三兵：连续三根阳线，每根收盘>前一根收盘，实体递增"""
    for r in [r1, r2, r3]:
        if float(r["收盘"]) <= float(r["开盘"]):
            return False
    c1, c2, c3 = float(r1["收盘"]), float(r2["收盘"]), float(r3["收盘"])
    b1, b2, b3 = _body(r1), _body(r2), _body(r3)
    return c1 < c2 < c3 and b1 < b2 < b3


def is_three_black_crows(r1, r2, r3):
    """三只乌鸦：连续三根阴线，每根收盘<前一根收盘，实体递增"""
    for r in [r1, r2, r3]:
        if float(r["收盘"]) >= float(r["开盘"]):
            return False
    c1, c2, c3 = float(r1["收盘"]), float(r2["收盘"]), float(r3["收盘"])
    b1, b2, b3 = _body(r1), _body(r2), _body(r3)
    return c1 > c2 > c3 and b1 < b2 < b3


# ═══════════════════════════════════════════
# 趋势判断
# ═══════════════════════════════════════════


def detect_trend_phase(df):
    """判断当前处于上升/下降/横盘趋势"""
    if df is None or len(df) < 20:
        return "数据不足"
    closes = df["收盘"].values
    ma5 = pd.Series(closes).rolling(5).mean().values
    ma10 = pd.Series(closes).rolling(10).mean().values
    ma20 = pd.Series(closes).rolling(20).mean().values

    last_close = closes[-1]
    last_ma5 = ma5[-1]
    last_ma10 = ma10[-1]
    last_ma20 = ma20[-1]

    n20_chg = (closes[-1] / closes[-20] - 1) * 100 if len(closes) >= 20 else 0
    n10_slope = (ma5[-1] / ma5[-10] - 1) * 100 if len(ma5) >= 10 and ma5[-10] > 0 else 0

    if (
        last_ma5 > last_ma10 > last_ma20
        and last_close > last_ma5
        and n20_chg > 3
        and n10_slope > 0.5
    ):
        return "上升趋势"
    elif (
        last_ma5 < last_ma10 < last_ma20
        and last_close < last_ma5
        and n20_chg < -3
        and n10_slope < -0.5
    ):
        return "下降趋势"
    else:
        return "横盘整理"


def _local_trend(closes, i, window=5):
    """判断第i根K线附近的局部趋势（用于形态上下文判断）"""
    if i < window:
        return "neutral"
    start = max(0, i - window)
    mid_price = closes[start:i]
    if len(mid_price) < 2:
        return "neutral"
    chg = mid_price[-1] / mid_price[0] - 1
    if chg > 0.03:
        return "up"
    elif chg < -0.03:
        return "down"
    return "neutral"


# ═══════════════════════════════════════════
# 形态名称 -> 描述映射
# ═══════════════════════════════════════════

_PATTERN_DESCRIPTIONS = {
    "大阳线": {
        "type": "bullish",
        "desc": "涨幅超3%的光头光脚或大实体阳线，买方力量极强。若在低位出现，常为主力建仓信号；若在高位出现，需警惕加速赶顶。",
        "reliability": "中",
    },
    "大阴线": {
        "type": "bearish",
        "desc": "跌幅超3%的大实体阴线，卖方完全主导。低位大阴线可能是最后恐慌一跌（洗盘），高位大阴线则是出货确认信号。",
        "reliability": "中",
    },
    "十字星": {
        "type": "neutral",
        "desc": "开盘价与收盘价几乎相同，上下影线明显，多空力量均衡。出现在趋势末端往往是变盘信号——上涨途中的十字星暗示涨势衰竭，下跌途中的十字星暗示跌势放缓。",
        "reliability": "中",
    },
    "锤子线": {
        "type": "bullish",
        "desc": "下影线极长（≥实体2倍）、上影线极短的小实体K线，出现在下跌趋势末端。长长的下影线说明价格在盘中一度大幅下跌后被强劲买盘推回，是底部反转的经典信号。",
        "reliability": "高",
    },
    "倒锤子": {
        "type": "bullish",
        "desc": "上影线极长、下影线极短的小实体K线，出现在下跌趋势末端。盘中冲高回落说明买方开始试探，虽被卖方压制但多头力量已显现，次日若高开确认则反转概率大增。",
        "reliability": "中",
    },
    "射击之星": {
        "type": "bearish",
        "desc": "上影线极长的小实体K线，出现在上升趋势中。盘中一度大涨但被空头猛烈打压回来，说明上方抛压沉重，是见顶信号。",
        "reliability": "高",
    },
    "吊颈线": {
        "type": "bearish",
        "desc": "与锤子线形态相同但出现在上升趋势中。长长的下影线看似下方有支撑，实则可能是主力在拉升过程中悄悄出货留下的痕迹，次日若低开大概率见顶。",
        "reliability": "中",
    },
    "看涨吞没": {
        "type": "bullish",
        "desc": "前一根阴线后紧跟一根大阳线，阳线实体完全包裹阴线实体。买方力量突然逆转，从被卖方压制转为完全主导，是明确的底部反转信号。",
        "reliability": "高",
    },
    "看跌吞没": {
        "type": "bearish",
        "desc": "前一根阳线后紧跟一根大阴线，阴线实体完全包裹阳线实体。卖方突然发力扭转局势，高位出现此形态往往意味着主力开始派发，应及时离场。",
        "reliability": "高",
    },
    "看涨孕线": {
        "type": "bullish",
        "desc": "前大阴线后小阳线，小阳线实体完全在大阴线实体范围内，像婴儿躲在母体里。下跌动能衰减，多头开始萌芽，是止跌企稳信号。",
        "reliability": "中",
    },
    "看跌孕线": {
        "type": "bearish",
        "desc": "前大阳线后小阴线，小阴线在大阳线实体内。上涨动能减弱，空头开始反扑，高位出现警惕变盘。",
        "reliability": "中",
    },
    "乌云盖顶": {
        "type": "bearish",
        "desc": "前大阳线后阴线高开低走，收盘跌破阳线中点。早盘冲高时散户追进去，尾盘却被庄家狠狠砸下来——典型的诱多出货形态，高位出现时尤其危险。",
        "reliability": "高",
    },
    "刺透形态": {
        "type": "bullish",
        "desc": "前大阴线后阳线低开高走，收盘突破阴线中点。早盘恐慌杀跌时庄家在低位接货，尾盘拉回，是典型的洗盘后拉升前兆。",
        "reliability": "高",
    },
    "启明星": {
        "type": "bullish",
        "desc": "三根K线组成的底部反转形态：第一天阴线（恐慌延续）->第二天小实体（跌势衰竭）->第三天阳线（多头确认）。三天的剧本是「绝望->犹豫->希望」，是最经典的底部反转信号之一。",
        "reliability": "高",
    },
    "黄昏之星": {
        "type": "bearish",
        "desc": "三根K线组成的顶部反转形态：第一天阳线（涨势延续）->第二天小实体（涨势停滞）->第三天阴线（空头确认）。高位出现此形态，就像是黄昏的最后一抹余晖，之后将是黑夜。",
        "reliability": "高",
    },
    "红三兵": {
        "type": "bullish",
        "desc": "连续三根阳线，每根收盘都高于前一根，实体逐步放大。这是最健康的多头推进形态，三根阳线步步为营，多方完全控盘。出现在上涨初期时信号最强。",
        "reliability": "高",
    },
    "三只乌鸦": {
        "type": "bearish",
        "desc": "连续三根阴线，每根收盘都低于前一根，实体逐步放大。这是最典型的空头碾压形态，三根阴线一根比一根狠。高位出现意味着主力不计成本地出货，应立即离场。",
        "reliability": "高",
    },
}


# ═══════════════════════════════════════════
# 公共接口
# ═══════════════════════════════════════════


def detect_patterns(df):
    """检测最近10个交易日内出现的K线形态

    Args:
        df: 含'开盘','收盘','最高','最低'列的DataFrame，按日期升序

    Returns:
        list[dict]: [{name, date, type, description, reliability}, ...]
    """
    if df is None or len(df) < 3:
        return []

    patterns = []
    closes = df["收盘"].values
    n = len(df)

    for i in range(n):
        row = df.iloc[i]
        date_str = str(df.iloc[i].get("日期", ""))[:10]
        trend = _local_trend(closes, i, 5)

        # 单根形态
        if is_big_bullish(row):
            patterns.append(_make_pattern("大阳线", date_str))
        if is_big_bearish(row):
            patterns.append(_make_pattern("大阴线", date_str))
        if is_doji(row):
            patterns.append(_make_pattern("十字星", date_str))
        if is_hammer(row, trend):
            patterns.append(_make_pattern("锤子线", date_str))
        if is_inverted_hammer(row, trend):
            patterns.append(_make_pattern("倒锤子", date_str))
        if is_shooting_star(row, trend):
            patterns.append(_make_pattern("射击之星", date_str))
        if is_hanging_man(row, trend):
            patterns.append(_make_pattern("吊颈线", date_str))

        # 两根形态
        if i >= 1:
            prev = df.iloc[i - 1]
            if is_bullish_engulfing(prev, row):
                patterns.append(_make_pattern("看涨吞没", date_str))
            if is_bearish_engulfing(prev, row):
                patterns.append(_make_pattern("看跌吞没", date_str))
            if is_bullish_harami(prev, row):
                patterns.append(_make_pattern("看涨孕线", date_str))
            if is_bearish_harami(prev, row):
                patterns.append(_make_pattern("看跌孕线", date_str))
            if is_dark_cloud_cover(prev, row):
                patterns.append(_make_pattern("乌云盖顶", date_str))
            if is_piercing_pattern(prev, row):
                patterns.append(_make_pattern("刺透形态", date_str))

        # 三根形态
        if i >= 2:
            r1, r2, r3 = df.iloc[i - 2], df.iloc[i - 1], df.iloc[i]
            if is_morning_star(r1, r2, r3):
                patterns.append(_make_pattern("启明星", date_str))
            if is_evening_star(r1, r2, r3):
                patterns.append(_make_pattern("黄昏之星", date_str))
            if is_three_white_soldiers(r1, r2, r3):
                patterns.append(_make_pattern("红三兵", date_str))
            if is_three_black_crows(r1, r2, r3):
                patterns.append(_make_pattern("三只乌鸦", date_str))

    # 只返回最近10日且有形态
    seen = set()
    recent = []
    for p in reversed(patterns):
        if p["name"] not in seen:
            seen.add(p["name"])
            recent.append(p)
        if len(recent) >= 10:
            break
    recent.reverse()
    return recent


def _make_pattern(name, date_str):
    info = _PATTERN_DESCRIPTIONS.get(name, {"type": "neutral", "desc": "", "reliability": "低"})
    return {
        "name": name,
        "date": date_str,
        "type": info["type"],
        "description": info["desc"],
        "reliability": info["reliability"],
    }


def generate_kline_interpretation(df):
    """生成完整的K线形态解读

    Args:
        df: 含'开盘','收盘','最高','最低'列的DataFrame

    Returns:
        dict: {recent_patterns, summary, trend_phase, key_observation}
    """
    if df is None or len(df) < 5:
        return {
            "recent_patterns": [],
            "summary": "K线数据不足，无法进行形态解读",
            "trend_phase": "数据不足",
            "key_observation": "",
        }

    patterns = detect_patterns(df)
    trend = detect_trend_phase(df)

    # 生成总结
    summary = _generate_summary(patterns, trend, df)
    key_obs = _generate_key_observation(patterns, trend, df)

    return {
        "recent_patterns": patterns,
        "summary": summary,
        "trend_phase": trend,
        "key_observation": key_obs,
    }


def _generate_summary(patterns, trend, df):
    """根据形态和趋势生成白话总结"""
    if not patterns:
        if trend == "上升趋势":
            return "最近K线没有出现明显的转折形态，股价沿均线稳步上行，多方控盘良好。"
        elif trend == "下降趋势":
            return "最近K线没有出现明显的止跌信号，阴线多于阳线，空头仍占优势。"
        else:
            return "最近K线没有出现明显的转折形态，股价在区间内震荡整理，方向不明。"

    bullish_count = sum(1 for p in patterns if p["type"] == "bullish")
    bearish_count = sum(1 for p in patterns if p["type"] == "bearish")
    names = [p["name"] for p in patterns[:3]]

    parts = [f"最近{len(patterns)}个交易日内出现了{'、'.join(names)}等形态。"]

    if bullish_count > bearish_count:
        parts.append(f"整体偏多，{bullish_count}个看涨信号对{bearish_count}个看跌信号。")
        if trend == "下降趋势":
            parts.append("虽然趋势仍偏弱，但多个看涨形态同时出现值得关注，可能正在筑底。")
        elif trend == "上升趋势":
            parts.append("形态与趋势方向一致，上涨势头健康，回踩支撑是介入机会。")
    elif bearish_count > bullish_count:
        parts.append(f"整体偏空，{bearish_count}个看跌信号对{bullish_count}个看涨信号。")
        if trend == "上升趋势":
            parts.append("虽然趋势仍向上，但K线形态已出现多处警示，警惕高位变盘。")
        elif trend == "下降趋势":
            parts.append("形态与趋势方向一致，跌势未止，不宜急于抄底。")
    else:
        parts.append("看涨看跌信号基本均衡，多空力量在当前位置争夺激烈。")

    return "".join(parts)


def _generate_key_observation(patterns, trend, df):
    """生成最关键的观察点"""
    if not patterns:
        return "近期无明显形态信号，观望为主。"

    bullish = [p for p in patterns if p["type"] == "bullish"]
    bearish = [p for p in patterns if p["type"] == "bearish"]

    if trend == "上升趋势" and bearish and len(bearish) >= 2:
        return f"⚠ 上升趋势中出现{'、'.join([p['name'] for p in bearish[:2]])}等看跌形态，这是趋势可能转折的早期信号，不宜追高加仓。"
    elif trend == "下降趋势" and bullish and len(bullish) >= 2:
        return f"✅ 下跌趋势中出现{'、'.join([p['name'] for p in bullish[:2]])}等看涨形态，这是潜在的见底信号，可以开始关注但需等待确认。"
    elif bullish:
        return f"短期形态偏多（{'、'.join([p['name'] for p in bullish[:2]])}），可结合量能和板块判断是否介入。"
    elif bearish:
        return f"短期形态偏空（{'、'.join([p['name'] for p in bearish[:2]])}），建议减仓或观望。"

    return "形态信号中性，继续观察。"


def merge_today_data(df, today_open, today_high, today_low, today_close, today_volume):
    """将当日盘中实时数据追加到K线DataFrame末尾

    Args:
        df: 缓存K线DataFrame（至昨日）
        today_open/close/high/low/volume: 当日实时数据

    Returns:
        合并后的DataFrame（含今日盘中K线）
    """
    import datetime

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    new_row = pd.DataFrame(
        [
            {
                "日期": today_str,
                "开盘": today_open,
                "收盘": today_close,
                "最高": today_high,
                "最低": today_low,
                "成交量": today_volume,
            }
        ]
    )
    combined = pd.concat([df, new_row], ignore_index=True)
    return combined


def get_today_pattern(today_open, today_high, today_low, today_close, prev_row, trend):
    """单独判断当日K线形态

    Args:
        today_open/close/high/low: 当日盘中数据
        prev_row: 昨日K线Series
        trend: 当前趋势方向

    Returns:
        dict: {name, type, description, reliability} 或 None
    """
    # 构造当日行和前一日行
    import pandas as pd

    today = pd.Series(
        {
            "开盘": today_open,
            "收盘": today_close,
            "最高": today_high,
            "最低": today_low,
        }
    )

    # 检查单根形态
    if is_doji(today):
        return _make_pattern("十字星", "今日盘中")
    if is_big_bullish(today):
        return _make_pattern("大阳线", "今日盘中")
    if is_big_bearish(today):
        return _make_pattern("大阴线", "今日盘中")
    if is_hammer(today, trend):
        return _make_pattern("锤子线", "今日盘中")
    if is_inverted_hammer(today, trend):
        return _make_pattern("倒锤子", "今日盘中")
    if is_shooting_star(today, trend):
        return _make_pattern("射击之星", "今日盘中")

    # 两根形态（今日+昨日）
    prev = pd.Series(
        {
            "开盘": float(prev_row["开盘"]),
            "收盘": float(prev_row["收盘"]),
            "最高": float(prev_row["最高"]),
            "最低": float(prev_row["最低"]),
        }
    )
    if is_bullish_engulfing(prev, today):
        return _make_pattern("看涨吞没", "今日盘中")
    if is_bearish_engulfing(prev, today):
        return _make_pattern("看跌吞没", "今日盘中")
    if is_bullish_harami(prev, today):
        return _make_pattern("看涨孕线", "今日盘中")
    if is_bearish_harami(prev, today):
        return _make_pattern("看跌孕线", "今日盘中")
    if is_dark_cloud_cover(prev, today):
        return _make_pattern("乌云盖顶", "今日盘中")
    if is_piercing_pattern(prev, today):
        return _make_pattern("刺透形态", "今日盘中")

    # 基础分类（未命中特殊形态时）
    body = abs(today_close - today_open)
    total = today_high - today_low
    if total > 0:
        upper = today_high - max(today_close, today_open)
        lower = min(today_close, today_open) - today_low
        chg = round((today_close - today_open) / today_open * 100, 2)
        body_ratio = body / total * 100
        features = []
        if upper > body * 2:
            features.append("长上影")
        if lower > body * 2:
            features.append("长下影")

        if body_ratio > 60 and chg > 2:
            btype = "bullish"
            name = "大阳线"
            desc = f"今日大阳线涨{chg:.2f}%，买方力量极强。"
        elif body_ratio > 60 and chg < -2:
            btype = "bearish"
            name = "大阴线"
            desc = f"今日大阴线跌{abs(chg):.2f}%，卖方完全主导。"
        elif features:
            shape = "阳线" if today_close > today_open else "阴线"
            name = f"{shape}({'，'.join(features)})"
            btype = (
                "bearish"
                if "长上影" in features
                else "bullish"
                if "长下影" in features
                else "neutral"
            )
            desc = f"今日{'高开低走' if today_close < today_open else '低开高走'}，{'，'.join(features)}。{'上方抛压沉重' if '长上影' in features else '下方支撑明显' if '长下影' in features else ''}"
        elif chg > 0:
            btype = "bullish"
            name = "阳线"
            desc = f"今日阳线涨{chg:.2f}%，实体占比{body_ratio:.0f}%，温和上涨。"
        elif chg < -1:
            btype = "bearish"
            name = "阴线"
            desc = f"今日阴线跌{abs(chg):.2f}%，实体占比{body_ratio:.0f}%。"
        else:
            btype = "neutral"
            name = "小实体"
            desc = f"今日小实体({'阳' if chg > 0 else '阴'})，涨跌{chg:+.2f}%，方向不明确。"

        return {
            "name": name,
            "date": "今日盘中",
            "type": btype,
            "description": desc,
            "reliability": "中",
        }

    return None


def generate_kline_interpretation_with_today(
    df, today_open=None, today_high=None, today_low=None, today_close=None, today_volume=None
):
    """含当日数据的完整K线解读

    如果提供了当日数据，会先合并再分析。
    """
    if today_open is not None and today_close is not None:
        df = merge_today_data(df, today_open, today_high, today_low, today_close, today_volume or 0)

    result = generate_kline_interpretation(df)

    # 单独标注今日形态
    if today_open is not None and today_close is not None and len(df) >= 2:
        today = df.iloc[-1]
        prev = df.iloc[-2]
        trend = result.get("trend_phase", "横盘整理")
        today_pat = get_today_pattern(today_open, today_high, today_low, today_close, prev, trend)
        if today_pat:
            result["today_pattern"] = today_pat
            result["today_chg"] = round((today_close - today_open) / today_open * 100, 2)
            # 把今日形态也加到最近形态列表最前面
            result["recent_patterns"] = [today_pat] + result["recent_patterns"]

    return result
