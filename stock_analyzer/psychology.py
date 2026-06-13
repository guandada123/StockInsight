"""庄家意图 & 散户心态分析

基于K线数据+资金流向+筹码分布，识别庄家操盘阶段和散户情绪状态。
规则引擎，无ML依赖，纯numpy/pandas计算。
"""

import numpy as np

# ═══════════════════════════════════════════
# 庄家意图分析 — 四阶段识别
# ═══════════════════════════════════════════


def analyze_manipulator_intention(df, fund_flow_direction="", chip_score=50):
    """分析当前庄家操盘阶段

    Args:
        df: 含'开盘','收盘','最高','最低','成交量','ATR'列的DataFrame
        fund_flow_direction: 资金方向 "流入"/"流出"
        chip_score: 筹码集中度评分 (0-100)

    Returns:
        dict: {phase, phase_confidence, signals, volume_analysis, chip_analysis, assessment, risk_note}
    """
    if df is None or len(df) < 30:
        return _fallback_result("数据不足（需至少30个交易日）")

    closes = df["收盘"].values.astype(float)
    volumes = df["成交量"].values.astype(float)
    n = len(df)

    # 计算各阶段得分
    acc_score, acc_signals = _detect_accumulation(df, closes, volumes, n)
    wash_score, wash_signals = _detect_washout(df, closes, volumes, n)
    up_score, up_signals = _detect_uptrend(df, closes, volumes, n)
    dist_score, dist_signals = _detect_distribution(df, closes, volumes, n, fund_flow_direction)

    scores = {
        "建仓": (acc_score, acc_signals),
        "洗盘": (wash_score, wash_signals),
        "拉升": (up_score, up_signals),
        "出货": (dist_score, dist_signals),
    }

    best_phase = max(scores, key=lambda k: scores[k][0])
    best_score, best_signals = scores[best_phase]

    # 如果最高分也低于30，判断为不明
    if best_score < 30:
        return _fallback_result("信号不明确，无法判断庄家阶段")

    vol_analysis = _volume_profile(df, volumes, n)
    chip_analysis = _chip_assessment(chip_score)
    assessment = _phase_assessment(best_phase, best_score, df, closes, n, fund_flow_direction)
    risk_note = _phase_risk(best_phase, df, closes, n)

    return {
        "phase": best_phase,
        "phase_confidence": min(round(best_score), 95),
        "signals": best_signals,
        "volume_analysis": vol_analysis,
        "chip_analysis": chip_analysis,
        "assessment": assessment,
        "risk_note": risk_note,
    }


def _detect_accumulation(df, closes, volumes, n):
    """检测建仓阶段：低位+缩量+温和上涨"""
    score = 0
    signals = []

    n20_chg = (closes[-1] / closes[-min(20, n)] - 1) * 100
    n60_chg = (closes[-1] / closes[-min(60, n)] - 1) * 100 if n >= 60 else n20_chg

    # 位置判断：低位（60日涨幅<15%且未大跌）
    if n60_chg < 15 and n60_chg > -15 and n20_chg > -3:
        score += 25
        signals.append(f"近60日涨幅{n60_chg:.1f}%，处于相对低位区间，具备建仓空间")
    elif n20_chg < 20 and n60_chg < 25:
        score += 10
        signals.append(f"近20日涨幅{n20_chg:.1f}%，位置不算高位")

    # 量能：温和放量（近5日均量/近20日均量在1.0-1.5之间）
    vol5 = np.mean(volumes[-5:]) if n >= 5 else volumes[-1]
    vol20 = np.mean(volumes[-min(20, n) :])
    vol_ratio = vol5 / vol20 if vol20 > 0 else 1
    if 1.0 <= vol_ratio <= 1.8:
        score += 20
        signals.append(f"量比{vol_ratio:.1f}，温和放量，符合建仓量能特征")
    elif vol_ratio < 1.0:
        score += 5
    elif vol_ratio > 2.5:
        signals.append(f"量比{vol_ratio:.1f}偏高，可能不是建仓而是出货")

    # 阳线占比
    bullish_count = sum(
        1 for i in range(max(0, n - 15), n) if closes[i] > float(df["开盘"].values[i])
    )
    bull_ratio = bullish_count / min(15, n)
    if 0.5 <= bull_ratio <= 0.7:
        score += 15
        signals.append(f"近15日阳线占比{bull_ratio:.0%}，缓步吸筹节奏")
    elif bull_ratio > 0.7:
        score += 10
        signals.append(f"阳线占比{bull_ratio:.0%}偏高，可能已进入拉升阶段")

    # 波动率：低波动
    if "ATR" in df.columns:
        atr_pct = float(df["ATR"].iloc[-1]) / closes[-1] * 100
        if atr_pct < 2.5:
            score += 15
            signals.append(f"ATR占比{atr_pct:.1f}%，低波动符合建仓期特征")
    else:
        rets = np.diff(np.log(closes[-20:]))
        vol = np.std(rets) * np.sqrt(252) * 100
        if vol < 30:
            score += 10
            signals.append(f"年化波动率{vol:.0f}%，波动较低")

    # 均线：开始走平
    if n >= 20:
        ma5 = np.mean(closes[-5:])
        ma10 = np.mean(closes[-10:])
        ma20 = np.mean(closes[-20:])
        if abs(ma5 - ma10) / ma10 < 0.02 and abs(ma10 - ma20) / ma20 < 0.03:
            score += 10
            signals.append("均线走平粘合，盘整蓄势特征")

    return min(score, 100), signals


def _detect_washout(df, closes, volumes, n):
    """检测洗盘阶段：拉升后缩量回调，不破关键支撑"""
    score = 0
    signals = []

    n10_chg = (closes[-1] / closes[-min(10, n)] - 1) * 100
    n5_high = np.max(closes[-5:])
    current = closes[-1]

    # 近期有回调（从高点回撤5-15%）
    n20_high = np.max(closes[-min(20, n) :])
    pullback = (current - n20_high) / n20_high * 100
    if -15 <= pullback <= -3:
        score += 25
        signals.append(f"从近20日高点回撤{abs(pullback):.1f}%，回调幅度符合洗盘特征")
    elif pullback < -15:
        signals.append(f"回撤{abs(pullback):.1f}%过大，已跌破正常洗盘范围，有可能是出货")

    # 缩量下跌（近5日均量<近20日均量）
    vol5 = np.mean(volumes[-5:])
    vol20 = np.mean(volumes[-min(20, n) :])
    vol_ratio = vol5 / vol20 if vol20 > 0 else 1
    if pullback < 0 and vol_ratio < 0.85:
        score += 25
        signals.append(f"回调时缩量（量比{vol_ratio:.1f}），卖盘枯竭，符合洗盘特征")
    elif pullback < 0 and vol_ratio < 0.6:
        score += 15

    # 之前有拉升（前20日涨幅>5%）
    n20_early_chg = (closes[-min(10, n)] / closes[-min(20, n)] - 1) * 100
    if n20_early_chg > 5:
        score += 15
        signals.append(f"洗盘前有{n20_early_chg:.1f}%的拉升，符合「拉升-洗盘-再拉升」节奏")

    # RSI 回调到中低位
    if "RSI" in df.columns:
        rsi = float(df["RSI"].iloc[-1])
        if 35 <= rsi <= 50:
            score += 15
            signals.append(f"RSI回调至{rsi:.0f}，洗盘清洗了超买情绪")
    else:
        delta = np.diff(closes[-14:])
        gain = np.mean(delta[delta > 0]) if any(delta > 0) else 0
        loss = abs(np.mean(delta[delta < 0])) if any(delta < 0) else 1e-9
        rs = gain / loss if loss > 0 else 100
        rsi = 100 - 100 / (1 + rs)
        if 30 <= rsi <= 55:
            score += 10

    # 未破关键支撑（20日均线）
    if n >= 20:
        ma20 = np.mean(closes[-20:])
        if current > ma20 * 0.95:
            score += 10
            if current > ma20:
                signals.append("股价仍在20日均线上方，未破关键支撑")
            else:
                signals.append("股价略低于20日均线但未远离，支撑尚在")

    return min(score, 100), signals


def _detect_uptrend(df, closes, volumes, n):
    """检测拉升阶段：均线多头排列+放量阳多阴少"""
    score = 0
    signals = []

    # 均线多头排列
    if n >= 20:
        ma5 = np.mean(closes[-5:])
        ma10 = np.mean(closes[-10:])
        ma20 = np.mean(closes[-20:])
        if ma5 > ma10 > ma20:
            score += 25
            signals.append("均线多头排列（MA5>MA10>MA20），典型拉升结构")
        elif ma5 > ma10:
            score += 10

    # 股价沿5日线上行
    n5_chg = (closes[-1] / closes[-min(5, n)] - 1) * 100
    if 1 < n5_chg < 10:
        score += 20
        signals.append(f"近5日涨{n5_chg:.1f}%，沿5日线稳步攀升")
    elif n5_chg >= 10:
        score += 5
        signals.append(f"近5日涨{n5_chg:.1f}%，涨幅偏大，可能是加速赶顶")

    # 阳多阴少
    bullish_count = sum(
        1 for i in range(max(0, n - 10), n) if closes[i] > float(df["开盘"].values[i])
    )
    if bullish_count >= 7:
        score += 15
        signals.append(f"近10日{bullish_count}阳，多方完全控盘")

    # MACD 零轴上方
    if "DIF" in df.columns and "DEA" in df.columns:
        dif = float(df["DIF"].iloc[-1])
        dea = float(df["DEA"].iloc[-1])
        if dif > dea and dif > 0:
            score += 15
            signals.append("MACD在零轴上方金叉运行，多头动能充足")

    # 量能配合（放量阳线+缩量阴线）
    bull_vol_avg = (
        np.mean(
            [
                volumes[i]
                for i in range(max(0, n - 10), n)
                if closes[i] > float(df["开盘"].values[i])
            ]
        )
        if bullish_count > 0
        else 0
    )
    bear_vol_avg = (
        np.mean(
            [
                volumes[i]
                for i in range(max(0, n - 10), n)
                if closes[i] <= float(df["开盘"].values[i])
            ]
        )
        if 10 - bullish_count > 0
        else 0
    )
    if bull_vol_avg > bear_vol_avg * 1.1 and bull_vol_avg > 0:
        score += 10
        signals.append("阳线放量阴线缩量，量价配合良好")

    return min(score, 100), signals


def _detect_distribution(df, closes, volumes, n, fund_flow_direction):
    """检测出货阶段：高位放量滞涨或下跌+主力流出"""
    score = 0
    signals = []

    n20_chg = (closes[-1] / closes[-min(20, n)] - 1) * 100
    n60_chg = (closes[-1] / closes[-min(60, n)] - 1) * 100 if n >= 60 else n20_chg

    # 高位（涨幅>30%或60日涨>40%）
    is_high = n20_chg > 25 or n60_chg > 35
    if is_high:
        score += 20
        signals.append(
            f"近20日涨{n20_chg:.1f}%、近60日涨{n60_chg:.1f}%，处于高位区间，出货风险上升"
        )

    # 放量滞涨或放量下跌
    vol5 = np.mean(volumes[-5:])
    vol20 = np.mean(volumes[-min(20, n) :])
    vol_ratio = vol5 / vol20 if vol20 > 0 else 1
    n5_chg = (closes[-1] / closes[-min(5, n)] - 1) * 100

    if vol_ratio > 1.5 and abs(n5_chg) < 2:
        score += 25
        signals.append(
            f"近5日放量{vol_ratio:.1f}倍但股价几乎不动（涨{n5_chg:.1f}%），典型的放量滞涨出货"
        )
    elif vol_ratio > 1.3 and n5_chg < -3:
        score += 20
        signals.append(f"放量{vol_ratio:.1f}倍下跌{n5_chg:.1f}%，放量砸盘出货")

    # K线特征：高位的长上影、阴包阳
    for i in range(max(0, n - 5), n):
        row = df.iloc[i]
        body = abs(float(row["收盘"]) - float(row["开盘"]))
        upper_s = float(row["最高"]) - max(float(row["收盘"]), float(row["开盘"]))
        total = float(row["最高"]) - float(row["最低"])
        if total > 0 and upper_s > body and upper_s / total > 0.5:
            score += 15
            signals.append("近期出现长上影线，高位抛压明显")
            break

    # 主力资金流出
    if fund_flow_direction == "流出":
        score += 15
        signals.append("主力资金近期呈净流出状态，与出货判断一致")
    elif fund_flow_direction == "流入":
        score -= 10

    # RSI 超买
    if "RSI" in df.columns:
        rsi = float(df["RSI"].iloc[-1])
        if rsi > 70:
            score += 10
            signals.append(f"RSI={rsi:.0f}超买，技术上需要回调")

    # 如果不在高位，出货得分打折扣
    if not is_high and score < 40:
        score = max(0, score - 15)

    return min(score, 100), signals


def _volume_profile(df, volumes, n):
    """生成量能分析描述"""
    vol5 = np.mean(volumes[-5:]) if n >= 5 else volumes[-1]
    vol20 = np.mean(volumes[-min(20, n) :])
    ratio = vol5 / vol20 if vol20 > 0 else 1

    if ratio > 2.0:
        return f"近5日均量是20日均量的{ratio:.1f}倍，放量明显。若股价同步上涨则为健康放量，若股价不涨反跌则为对倒出货的嫌疑。"
    elif ratio > 1.3:
        return f"近5日均量是20日均量的{ratio:.1f}倍，温和放量。量能逐步放大是趋势延续的信号，关键看能否持续。"
    elif ratio > 0.7:
        return (
            f"近5日均量是20日均量的{ratio:.1f}倍，量能平稳。没有异常放量或缩量，市场参与度常态化。"
        )
    else:
        return f"近5日均量是20日均量的{ratio:.1f}倍，明显缩量。缩量可能意味着筹码锁定良好（上涨中）= 还能涨，也可能意味着资金离场冷淡（下跌中）= 无人接盘。"


def _chip_assessment(chip_score):
    """生成筹码评估描述"""
    if chip_score >= 70:
        return f"筹码评分{chip_score}，筹码集中度较高，主力控盘程度较好。筹码集中的股票拉升阻力小，但出货时也要找对手盘。"
    elif chip_score >= 50:
        return f"筹码评分{chip_score}，筹码相对集中但不极端。主力有一定控盘能力但散户仍有较多筹码，拉升时需要更多资金推动。"
    else:
        return f"筹码评分{chip_score}，筹码分散，散户持仓为主。筹码分散的股票主力控盘弱，拉升难度大，更多随大盘波动。"


def _phase_assessment(phase, score, df, closes, n, fund_flow_direction):
    """生成阶段综合评估"""
    price = closes[-1]

    assessments = {
        "建仓": (
            f"综合判断庄家目前大概率处于建仓吸筹阶段（置信度{score}%）。"
            f"数据上看，股价在相对低位区域运行，成交量温和放大，阳线为主但涨幅控制得当。"
            f"庄家的目的是在低位悄悄收集筹码，不愿引起市场关注——这个阶段特征是'闷声发大财'。"
            f"对散户来说，建仓期是最佳介入时机，但需要耐心——庄家可能还会震荡洗盘，不会立刻拉升。"
        ),
        "洗盘": (
            f"综合判断庄家目前大概率处于洗盘震仓阶段（置信度{score}%）。"
            f"关键证据是回调时成交量明显缩小，说明卖盘在枯竭而非主力在出货。"
            f"庄家的目的是把不坚定的散户甩下车，减轻后续拉升的抛压。这个阶段的下跌是'假摔'而非'真跑'。"
            f"如果你已经持有，不要被洗出去——缩量跌是洗盘的特征；如果你还没买，洗盘结束、放量回升时是最佳买点。"
        ),
        "拉升": (
            f"综合判断庄家目前大概率处于主升浪拉升阶段（置信度{score}%）。"
            f"均线多头排列、MACD零轴上方运行、阳线放量阴线缩量——这是最健康的上涨结构。"
            f"庄家正在用真金白银往上推，目的是把股价拉到目标位。这个阶段'顺势而为'是最优策略——拿住别急着卖。"
            f"{'但需注意，主力资金近期有流出迹象，可能是边拉边出，保持警惕。' if fund_flow_direction == '流出' else ''}"
        ),
        "出货": (
            f"综合判断庄家目前大概率处于出货派发阶段（置信度{score}%）。"
            f"股价处于高位，成交量异常放大但价格不涨或微跌——这是庄家对倒出货的典型特征。"
            f"庄家的目的是在价格还好看的时候把筹码倒给追进来的散户。'利好出尽是利空'——好消息配合出货是常见手法。"
            f"⚠ 如果你还持有，建议设定跟紧的止盈位，跌破果断离场。如果你没买，远离出货阶段的股票——当接盘侠是散户亏钱最快的路径。"
        ),
    }

    return assessments.get(phase, "庄家意图不明确，建议继续观察等待更多信号。")


def _phase_risk(phase, df, closes, n):
    """生成阶段风险提示"""
    risks = {
        "建仓": "建仓阶段最大的风险是'抄底抄在半山腰'——你以为是底部但庄家还在打压吸筹。建议分批次介入，不要一次性满仓。",
        "洗盘": "洗盘阶段最怕心态崩溃——看着账户浮亏就割肉，恰恰割在地板上。只要成交量是缩的、支撑位没破，就相信自己的判断。",
        "拉升": "拉升阶段最怕贪婪——涨了还想涨，止盈位一改再改。记住'会买的是徒弟，会卖的是师傅'，设定移动止盈保住利润。",
        "出货": "出货阶段最怕侥幸——看到跌了觉得'还能弹回来'，结果越套越深。庄家一旦出货完毕，股价大概率会深跌，不抱幻想。",
    }
    return risks.get(phase, "")


def _fallback_result(reason):
    return {
        "phase": "不明",
        "phase_confidence": 0,
        "signals": [reason],
        "volume_analysis": "",
        "chip_analysis": "",
        "assessment": f"数据不足以判断庄家意图：{reason}",
        "risk_note": "",
    }


# ═══════════════════════════════════════════
# 散户心态画像
# ═══════════════════════════════════════════


def analyze_retail_psychology(df, rsi=50, near_5d=0.0):
    """分析散户当前的心理状态

    Args:
        df: K线DataFrame
        rsi: RSI值
        near_5d: 近5日涨跌幅(%)

    Returns:
        dict: {emotion, emotion_score, behavior_pattern, sentiment_indicators, advice}
    """
    if df is None or len(df) < 10:
        return {
            "emotion": "未知",
            "emotion_score": 0,
            "behavior_pattern": "数据不足",
            "sentiment_indicators": [],
            "advice": "请获取更多交易数据后再进行分析",
        }

    closes = df["收盘"].values.astype(float)
    volumes = df["成交量"].values.astype(float)
    n = len(df)

    # 计算各情绪得分
    greed_score, greed_indicators = _calc_greed(df, rsi, near_5d, closes, volumes, n)
    fear_score, fear_indicators = _calc_fear(df, rsi, near_5d, closes, volumes, n)
    hesitation_score, hesitation_indicators = _calc_hesitation(df, rsi, near_5d, closes, volumes, n)
    chasing_score, chasing_indicators = _calc_chasing(df, rsi, near_5d, closes, volumes, n)
    panic_score, panic_indicators = _calc_panic(df, rsi, near_5d, closes, volumes, n)

    emotions = {
        "贪婪": (greed_score, greed_indicators),
        "恐惧": (fear_score, fear_indicators),
        "犹豫观望": (hesitation_score, hesitation_indicators),
        "追涨": (chasing_score, chasing_indicators),
        "恐慌抛售": (panic_score, panic_indicators),
    }

    best = max(emotions, key=lambda k: emotions[k][0])
    best_score, best_indicators = emotions[best]

    behavior = _describe_behavior(best, near_5d, rsi, n)
    advice = _psychology_advice(best, near_5d, rsi)

    return {
        "emotion": best,
        "emotion_score": min(round(best_score), 100),
        "behavior_pattern": behavior,
        "sentiment_indicators": best_indicators if best_indicators else ["无明显极端情绪指标"],
        "advice": advice,
    }


def _calc_greed(df, rsi, near_5d, closes, volumes, n):
    """计算贪婪情绪得分"""
    score = 0
    indicators = []

    if rsi > 70:
        score += 25
        indicators.append(f"RSI={rsi:.0f}超买，市场情绪过热")
    if near_5d > 10:
        score += 20
        indicators.append(f"近5日涨{near_5d:.1f}%，短期涨幅较大催生贪婪")
    elif near_5d > 5:
        score += 10

    # 连续大阳线
    big_bull_count = sum(
        1
        for i in range(max(0, n - 10), n)
        if closes[i] > float(df["开盘"].values[i])
        and (closes[i] / float(df["开盘"].values[i]) - 1) > 0.02
    )
    if big_bull_count >= 5:
        score += 15
        indicators.append(f"近10日{big_bull_count}根明显阳线，连涨催生「还能涨」的幻想")

    n20_chg = (closes[-1] / closes[-min(20, n)] - 1) * 100
    if n20_chg > 20:
        score += 15
        indicators.append(f"近20日涨{n20_chg:.1f}%，大幅获利后容易过度自信")
    if n20_chg > 30:
        score += 10

    return min(score, 100), indicators


def _calc_fear(df, rsi, near_5d, closes, volumes, n):
    """计算恐惧情绪得分"""
    score = 0
    indicators = []

    if rsi < 30:
        score += 25
        indicators.append(f"RSI={rsi:.0f}超卖，市场情绪极度悲观")
    if near_5d < -8:
        score += 20
        indicators.append(f"近5日跌{abs(near_5d):.1f}%，短期急跌引发恐惧")
    elif near_5d < -3:
        score += 10

    # 连续阴线
    bear_count = sum(
        1 for i in range(max(0, n - 10), n) if closes[i] <= float(df["开盘"].values[i])
    )
    if bear_count >= 7:
        score += 15
        indicators.append(f"近10日{bear_count}阴，持续下跌消耗信心")

    n20_chg = (closes[-1] / closes[-min(20, n)] - 1) * 100
    if n20_chg < -15:
        score += 15
        indicators.append(f"近20日跌{abs(n20_chg):.1f}%，深度被套后恐慌情绪蔓延")

    return min(score, 100), indicators


def _calc_hesitation(df, rsi, near_5d, closes, volumes, n):
    """计算犹豫观望情绪得分"""
    score = 0
    indicators = []

    if 40 <= rsi <= 60:
        score += 20
        indicators.append(f"RSI={rsi:.0f}在中性区间，方向不明确")

    if abs(near_5d) < 2:
        score += 20
        indicators.append("近5日几乎不涨不跌，观望情绪浓厚")

    # 振幅收窄
    n10_highs = [float(df["最高"].values[i]) for i in range(max(0, n - 10), n)]
    n10_lows = [float(df["最低"].values[i]) for i in range(max(0, n - 10), n)]
    avg_amp = np.mean([(h - l) / l * 100 for h, l in zip(n10_highs, n10_lows) if l > 0])
    if avg_amp < 2.5:
        score += 20
        indicators.append(f"近10日均振幅{avg_amp:.1f}%，窄幅横盘")

    # 缩量
    vol5 = np.mean(volumes[-5:]) if n >= 5 else volumes[-1]
    vol20 = np.mean(volumes[-min(20, n) :])
    ratio = vol5 / vol20 if vol20 > 0 else 1
    if ratio < 0.7:
        score += 15
        indicators.append(f"近期缩量（量比{ratio:.1f}），资金参与度低，都在观望")

    return min(score, 100), indicators


def _calc_chasing(df, rsi, near_5d, closes, volumes, n):
    """计算追涨情绪得分"""
    score = 0
    indicators = []

    # 突破近期新高
    n20_high = np.max(closes[-min(20, n) : -1])
    current = closes[-1]
    if current > n20_high * 1.01:
        score += 20
        indicators.append("股价突破近20日新高，散户FOMO（怕踏空）情绪上升")

    if near_5d > 5:
        score += 15
        indicators.append(f"近5日涨{near_5d:.1f}%，追涨资金涌入")

    # 放量上涨
    vol5 = np.mean(volumes[-5:]) if n >= 5 else volumes[-1]
    vol20 = np.mean(volumes[-min(20, n) :])
    ratio = vol5 / vol20 if vol20 > 0 else 1
    if ratio > 1.5 and near_5d > 0:
        score += 20
        indicators.append(f"放量{ratio:.1f}倍上涨，场外资金追入")

    if rsi > 65:
        score += 10
        indicators.append("RSI偏高但仍在加速，追涨心理强化")

    return min(score, 100), indicators


def _calc_panic(df, rsi, near_5d, closes, volumes, n):
    """计算恐慌抛售情绪得分"""
    score = 0
    indicators = []

    # 跌破支撑
    n20_low = np.min(closes[-min(20, n) : -1])
    current = closes[-1]
    if current < n20_low * 0.99:
        score += 25
        indicators.append("股价跌破近20日新低，恐慌性抛售")

    if near_5d < -5:
        score += 15
        indicators.append(f"近5日跌{abs(near_5d):.1f}%，恐慌盘涌出")

    # 放量暴跌
    vol5 = np.mean(volumes[-5:]) if n >= 5 else volumes[-1]
    vol20 = np.mean(volumes[-min(20, n) :])
    ratio = vol5 / vol20 if vol20 > 0 else 1
    if ratio > 1.3 and near_5d < -3:
        score += 20
        indicators.append(f"放量{ratio:.1f}倍下跌，恐慌性抛售特征明显")

    # 连续长阴
    big_bear_count = sum(
        1
        for i in range(max(0, n - 10), n)
        if closes[i] <= float(df["开盘"].values[i])
        and (closes[i] / float(df["开盘"].values[i]) - 1) < -0.02
    )
    if big_bear_count >= 4:
        score += 15
        indicators.append(f"近10日{big_bear_count}根明显阴线，恐慌加速蔓延")

    return min(score, 100), indicators


def _describe_behavior(emotion, near_5d, rsi, n):
    """描述散户行为模式"""
    descriptions = {
        "贪婪": f"持有者心态：'还能涨，再拿拿'——止盈位一改再改。想买者心态：'再不买就来不及了'——怕踏空急于追入。当前RSI={rsi:.0f}，近5日涨{near_5d:+.1f}%，贪婪情绪正在蔓延。",
        "恐惧": f"持有者心态：'还要跌，赶紧卖'——想止损离场或已经割肉。想买者心态：'太危险了，再等等'——不敢买入错失机会。当前RSI={rsi:.0f}，近5日跌{near_5d:.1f}%，恐惧情绪支配决策。",
        "犹豫观望": "持有者和想买者心态一致：'看不清方向，先不动'。大家都在等别人先动手，市场陷入'你不买我不买'的僵局。参与度低、成交量萎缩是犹豫期的典型特征。",
        "追涨": "持有者心态：'我就说会涨，加仓！'——浮盈让人过度自信。想买者心态：'再不买就买不到了，管它什么价'——FOMO驱动的非理性追入。这种心态下最容易买在最高点。",
        "恐慌抛售": "持有者心态：'完了完了，再不卖就跌没了'——情绪化抛售不管价格。想买者心态：'谁买谁傻'——虽然价格很便宜但没人敢接。恐慌抛售常造成超跌，为冷静的逆向投资者创造机会。",
    }
    return descriptions.get(emotion, "散户情绪状态不明确。")


def _psychology_advice(emotion, near_5d, rsi):
    """给出心理层面的建议——反着散户心态来"""
    advice_map = {
        "贪婪": "当所有人都在喊'还能涨'的时候，恰恰是最危险的时候。纪律至上——到了止盈位就减仓，不要把浮盈当确定收益。巴菲特的智慧：'别人贪婪时我恐惧。'",
        "恐惧": f"RSI={rsi:.0f}，近5日跌{abs(near_5d):.1f}%，市场弥漫恐慌。但请注意：缩量下跌=洗盘，放量下跌才=出货。如果成交量是缩的，很可能是主力在故意制造恐慌。别人恐惧时你要冷静分析。",
        "犹豫观望": "观望本身不是错——没有把握就不要出手。但要注意：窄幅震荡后必有大方向选择。如果放量突破整理区间上沿，第一时间跟进；如果跌破下沿，果断止损。",
        "追涨": "追涨是散户亏钱最快的姿势。如果你是追进去的，设定一个紧止损——亏5-8%必须走。记住：宁可错过也不要做错。等回调到支撑位再买，成本至少低3-5%。",
        "恐慌抛售": "在恐慌中卖出的决策，事后看往往是错的。如果你还没卖：想清楚是真的基本面变坏，还是只是市场情绪波动。如果你已经卖了：不要立刻想着'扳回来'——冷静下来等下一次机会。",
    }
    return advice_map.get(emotion, "保持冷静，按纪律执行操作。")


# ═══════════════════════════════════════════
# K线+庄家联动总结
# ═══════════════════════════════════════════


def generate_combined_summary(pattern_result, manipulator_result):
    """将K线形态分析和庄家意图分析结合起来

    Args:
        pattern_result: generate_kline_interpretation() 的返回值
        manipulator_result: analyze_manipulator_intention() 的返回值

    Returns:
        dict: {kline_summary, manipulator_summary, synergy_assessment, overall_conclusion}
    """
    kline_summary = pattern_result.get("summary", "") if isinstance(pattern_result, dict) else ""
    trend = pattern_result.get("trend_phase", "") if isinstance(pattern_result, dict) else ""
    patterns = pattern_result.get("recent_patterns", []) if isinstance(pattern_result, dict) else []

    phase = (
        manipulator_result.get("phase", "不明") if isinstance(manipulator_result, dict) else "不明"
    )
    confidence = (
        manipulator_result.get("phase_confidence", 0) if isinstance(manipulator_result, dict) else 0
    )
    assessment = (
        manipulator_result.get("assessment", "") if isinstance(manipulator_result, dict) else ""
    )

    manipulator_summary = f"庄家大概率处于{phase}阶段（置信度{confidence}%）。{assessment}"

    # 联动一致性判断
    synergy = _assess_synergy(patterns, phase, trend)

    overall = _overall_conclusion(patterns, phase, trend, synergy)

    return {
        "kline_summary": kline_summary,
        "manipulator_summary": manipulator_summary,
        "synergy_assessment": synergy,
        "overall_conclusion": overall,
    }


def _assess_synergy(patterns, phase, trend):
    """评估K线形态与庄家意图是否一致"""
    bullish_count = sum(1 for p in patterns if p.get("type") == "bullish") if patterns else 0
    bearish_count = sum(1 for p in patterns if p.get("type") == "bearish") if patterns else 0

    phase_bullish = phase in ["建仓", "拉升"]
    phase_bearish = phase in ["出货"]

    if phase == "不明":
        return "庄家意图不明确，无法与K线形态进行联动判断。建议继续观察等待。"

    if phase_bullish and bullish_count >= bearish_count:
        return (
            f"✅ K线形态（{bullish_count}个看涨信号）与庄家意图（{phase}阶段）方向一致。"
            f"K线语言和庄家语言都在说同一件事——看多。这种'双重确认'大大提高了判断的可靠性。"
        )
    elif phase_bearish and bearish_count >= bullish_count:
        return (
            f"⚠ K线形态（{bearish_count}个看跌信号）与庄家意图（{phase}阶段）方向一致。"
            f"K线和庄家行为都在指向下跌——这种共振信号值得高度重视，应果断减仓或离场。"
        )
    elif phase_bullish and bearish_count > bullish_count:
        return (
            f"⚠ 信号矛盾：庄家意图显示{phase}（偏多），但K线形态出现{bearish_count}个看跌信号。"
            f"这种矛盾需要警惕——可能是庄家在拉升前的最后洗盘，也可能是判断出错。建议等K线形态转多后再介入。"
        )
    elif phase_bearish and bullish_count > bearish_count:
        return (
            f"⚠ 信号矛盾：庄家意图显示{phase}（偏空），但K线形态出现{bullish_count}个看涨信号。"
            f"这种'形好看但庄家在跑'的组合非常危险——可能是庄家故意做出好看的技术图形来吸引散户接盘。"
        )
    else:
        return "K线形态信号和庄家意图信号均中性，无明确方向。"


def _overall_conclusion(patterns, phase, trend, synergy):
    """生成综合结论"""
    if phase == "拉升":
        return f"综合K线形态和庄家意图判断：当前处于{trend}，庄家大概率在拉升阶段。K线形态与庄家行为一致看多，顺势而为是最优策略。建议设好移动止盈，让利润奔跑，但不要在高位追高加仓。"
    elif phase == "建仓":
        return f"综合K线形态和庄家意图判断：当前处于{trend}，庄家大概率在建仓吸筹。这是中长期布局的好时机，但短期可能还会震荡甚至洗盘。建议分批次低吸，耐心持有等待拉升。"
    elif phase == "洗盘":
        return f"综合K线形态和庄家意图判断：当前处于{trend}的回调阶段，大概率是庄家在洗盘。只要成交量是缩的、支撑位没破，就不要被洗出去。洗盘结束后的放量回升是最佳加仓点。"
    elif phase == "出货":
        return f"综合K线形态和庄家意图判断：当前处于{trend}，庄家大概率在出货派发。这是最危险的时候——不要被K线上好看的反弹迷惑，那是庄家在给散户'最后的上车机会'。建议减仓或清仓离场。"
    else:
        return "当前K线信号和庄家意图均不明确，建议观望等待更多信号出现后再做决策。宁可错过机会，也不要在不确定时下注。"
