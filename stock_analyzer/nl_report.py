"""自然语言分析报告 — LLM风格多空辩论 + 综合结论

借鉴 TradingAgents / daily_stock_analysis，将量化数据转化为可读的自然语言分析。
不依赖外部 API，基于规则模板生成。
"""


def generate_bull_bear_debate(analysis_data):
    """多空辩论：多头视角 vs 空头视角 vs 综合判断

    Args:
        analysis_data: dict，包含 quant_score, technical, fund_flow, ai_pred, sector 等

    Returns:
        dict with bull, bear, verdict sections
    """
    score = analysis_data.get("quant_score", 50)
    tech = analysis_data.get("technical", {})
    fund = analysis_data.get("fund_flow", {})
    ai = analysis_data.get("ai_prediction", {})
    sector = analysis_data.get("sector", {})

    # ── 多头观点 ──
    bull_points = []
    bull_score = 0

    macd = tech.get("macd_signal", "")
    if "金叉" in str(macd):
        bull_points.append("MACD刚刚金叉，短期动能转向多头，历史上金叉后5日胜率约62%")
        bull_score += 2
    elif "多头" in str(macd):
        bull_points.append("MACD维持多头排列，趋势未破，DIF线仍在DEA上方运行")
        bull_score += 1

    rsi = tech.get("rsi", 50)
    if 40 < rsi < 65:
        bull_points.append(f"RSI={rsi}处于健康区间(40-65)，既未超买也未超卖，有继续上行空间")
        bull_score += 1
    elif rsi < 30:
        bull_points.append(f"RSI={rsi}进入超卖区，历史数据显示超卖后反弹概率>70%")
        bull_score += 1

    kdj = tech.get("kdj_signal", "")
    if "金叉" in str(kdj):
        bull_points.append("KDJ金叉，短线资金开始介入，与MACD形成共振")
        bull_score += 2

    near5 = tech.get("near5d", 0)
    near20 = tech.get("near20d", 0)
    if 0 < near5 < 10:
        bull_points.append(f"近5日仅涨{near5:.1f}%，涨幅温和，无追高风险")
        bull_score += 1
    if near20 < 0 and near5 > 0:
        bull_points.append(f"近20日跌{near20:.1f}%但近5日转涨{near5:.1f}%，底部反转信号")
        bull_score += 2

    fund_dir = fund.get("direction", "")
    if "流入" in str(fund_dir):
        bull_points.append("主力资金近5日净流入，大资金在低位吸筹")
        bull_score += 2

    ai_dir = ai.get("direction", "")
    ai_conf = ai.get("confidence", 0)
    if "看涨" in str(ai_dir) and ai_conf > 60:
        bull_points.append(f"AI模型看涨，置信度{ai_conf:.0f}%，机器学习从历史模式中识别到上涨信号")
        bull_score += 1

    pe = tech.get("pe", 0)
    if 0 < pe < 30:
        bull_points.append(f"PE={pe:.0f}，估值合理，不属于泡沫区间")
        bull_score += 1

    # ── 空头观点 ──
    bear_points = []
    bear_score = 0

    if "死叉" in str(macd):
        bear_points.append("MACD死叉，短期动能转为空头，注意回调风险")
        bear_score += 2
    elif "空头" in str(macd):
        bear_points.append("MACD处于空头区域，DIF线在DEA下方，趋势偏弱")
        bear_score += 1

    if rsi > 75:
        bear_points.append(f"RSI={rsi}进入超买区，短期获利盘压力大，回调风险上升")
        bear_score += 2
    elif rsi < 35:
        bear_points.append(f"RSI={rsi}偏弱，市场情绪低迷，可能继续下探")
        bear_score += 1

    if "死叉" in str(kdj):
        bear_points.append("KDJ死叉，短线资金在撤离，不宜追高")
        bear_score += 2

    if near5 > 15:
        bear_points.append(f"近5日涨{near5:.1f}%，短线获利盘积累严重，随时可能回调")
        bear_score += 2
    if near20 > 40:
        bear_points.append(f"近20日涨{near20:.1f}%，处于加速赶顶阶段，追高风险极大")
        bear_score += 3

    if "流出" in str(fund_dir):
        bear_points.append("主力资金近5日净流出，大资金在悄悄撤退")
        bear_score += 2

    if "看跌" in str(ai_dir) and ai_conf > 60:
        bear_points.append(f"AI模型看跌，置信度{ai_conf:.0f}%，机器学习识别到下跌风险")
        bear_score += 1

    # 均线
    ma_status = tech.get("ma_status", "")
    if "空头" in str(ma_status):
        bear_points.append("均线空头排列，短期均线在长期均线下方，趋势性偏弱")
        bear_score += 2
    elif "多头" in str(ma_status):
        bull_points.append("均线多头排列，短期均线全部在长期均线上方，趋势健康")
        bull_score += 1

    # 距离压力位
    resist = tech.get("resistance", [])
    price = tech.get("price", 0)
    if resist and price > 0:
        near_resist = min(resist, key=lambda x: abs(x - price))
        dist = (near_resist - price) / price * 100
        if 0 < dist < 3:
            bear_points.append(f"距压力位{near_resist:.1f}仅{dist:.1f}%，上方空间有限")
            bear_score += 1

    # ── 综合判断 ──
    net = bull_score - bear_score
    if net >= 4:
        verdict = "多头占据明显优势，多个指标共振看多"
        action = "可以买入"
        confidence = "高"
    elif net >= 2:
        verdict = "多头略占上风，但仍有分歧"
        action = "轻仓试探"
        confidence = "中"
    elif net >= -1:
        verdict = "多空力量均衡，方向不明"
        action = "观望等待"
        confidence = "低"
    elif net >= -3:
        verdict = "空头略占上风，风险大于机会"
        action = "减仓或观望"
        confidence = "中"
    else:
        verdict = "空头占据明显优势，多个指标共振看空"
        action = "不建议买入"
        confidence = "高"

    return {
        "bull": {"score": bull_score, "points": bull_points},
        "bear": {"score": bear_score, "points": bear_points},
        "verdict": verdict,
        "action": action,
        "confidence": confidence,
        "net_score": net,
    }


def generate_stock_report(code, name, analysis_data):
    """生成完整的自然语言个股分析报告

    返回格式化的文本报告，可直接展示给用户。
    """
    debate = generate_bull_bear_debate(analysis_data)
    price = analysis_data.get("technical", {}).get("price", 0)
    chg = analysis_data.get("technical", {}).get("near5d", 0)

    lines = []
    lines.append(f"╔{'═' * 58}╗")
    lines.append(f"║  {name}({code}) 多空辩论分析报告{'':<30}║")
    lines.append(f"╠{'═' * 58}╣")

    # 多头
    lines.append(f"║ 🐂 多头观点 (得分: {debate['bull']['score']}){'':<38}║")
    for pt in debate["bull"]["points"]:
        # 中文分行处理
        text = f"║   ✓ {pt}"
        padding = 62 - len(text) - (len(pt) - len(pt.encode("gbk", errors="replace")))
        lines.append(f"{text:<60}║")
    if not debate["bull"]["points"]:
        lines.append(f"║   (无明显看多信号){'':<41}║")

    lines.append(f"╟{'─' * 58}╢")

    # 空头
    lines.append(f"║ 🐻 空头观点 (得分: {debate['bear']['score']}){'':<38}║")
    for pt in debate["bear"]["points"]:
        text = f"║   ✗ {pt}"
        lines.append(f"{text:<60}║")
    if not debate["bear"]["points"]:
        lines.append(f"║   (无明显看空信号){'':<41}║")

    lines.append(f"╠{'═' * 58}╣")
    lines.append(f"║ 📊 综合判断: {debate['verdict']}{'':<32}║")
    lines.append(f"║ 🎯 操作建议: {debate['action']}  置信度: {debate['confidence']}{'':<22}║")
    lines.append(f"╚{'═' * 58}╝")

    return "\n".join(lines)


def generate_market_summary(market_data, holdings_analysis):
    """生成大盘+持仓综合自然语言摘要"""
    parts = []

    # 大盘
    sh = market_data.get("000001", {})
    sz = market_data.get("399001", {})
    if sh:
        parts.append(f"上证{sh.get('最新价', '?')}（{sh.get('涨跌幅', '?')}%）")
    if sz:
        parts.append(f"深证{sz.get('最新价', '?')}（{sz.get('涨跌幅', '?')}%）")

    market_str = "，".join(parts) if parts else "大盘数据缺失"

    # 持仓总结
    if holdings_analysis:
        bullish = sum(1 for h in holdings_analysis if h.get("net_score", 0) > 0)
        bearish = sum(1 for h in holdings_analysis if h.get("net_score", 0) < 0)
        neutral = len(holdings_analysis) - bullish - bearish
        summary = f"持仓中{bullish}只偏多，{neutral}只中性，{bearish}只偏空"
    else:
        summary = "无持仓数据"

    return f"【大盘】{market_str}\n【持仓】{summary}"
