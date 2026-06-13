"""筹码集中度分析 — 基于K线+成交量计算90%/70%成本集中区间

核心规则（用户实战经验）：
- 90%筹码集中度 > 20% → 上涨空间有限，只能快进快出（下跌到位买入，上涨就抛）
- 90%筹码>35% 且 70%筹码>20% → 绝对不能碰，套你没商量
- 90%筹码<10% → 筹码高度集中，主力控盘，拉升潜力大

计算方法：
  基于近60个交易日K线数据，通过累计成交量分布推算筹码成本分布。
  将每日成交量按当日价格区间分配，模拟筹码堆积，计算覆盖90%/70%成交量
  所需的价格区间占当前价格的比例。
"""


def calc_chip_concentration(kline, lookback=60):
    """计算筹码集中度 — 90%和70%筹码覆盖的价格区间

    算法：
    1. 取近N日K线，以每日(最高+最低)/2为当日平均成本
    2. 按成交量加权，构建成本分布直方图
    3. 从分布中心向两侧扩展，直到覆盖90%/70%的总成交量
    4. 计算覆盖区间的宽度占当前价格的比例 = 集中度

    Args:
        kline: 含'最高','最低','成交量','收盘'的DataFrame
        lookback: 回溯天数（默认60）

    Returns:
        dict: {
            pct90: 90%筹码集中度(%),
            pct70: 70%筹码集中度(%),
            avg_cost: 加权平均成本,
            current_price: 当前价,
            level: 安全/谨慎/危险/极度危险,
            risk_warning: 风险提示,
            cost_range_90: [最低成本, 最高成本],
            cost_range_70: [最低成本, 最高成本],
        }
    """
    if kline is None or len(kline) < 20:
        return _fallback("K线数据不足")

    df = kline.tail(lookback).copy()
    if len(df) < 20:
        return _fallback("数据不足20日")

    # 日均成本 = (最高+最低) / 2
    df["avg_price"] = (df["最高"] + df["最低"]) / 2
    df = df[df["成交量"] > 0].copy()

    if df.empty:
        return _fallback("无有效成交量数据")

    total_vol = df["成交量"].sum()
    current_price = float(df["收盘"].iloc[-1])

    # 按成本排序
    sorted_df = df.sort_values("avg_price")
    cum_vol = sorted_df["成交量"].cumsum()

    # 90%筹码集中度
    pct90_low, pct90_high = _find_cost_range(sorted_df, cum_vol, total_vol, 0.90)
    pct90 = round((pct90_high - pct90_low) / current_price * 100, 1)

    # 70%筹码集中度
    pct70_low, pct70_high = _find_cost_range(sorted_df, cum_vol, total_vol, 0.70)
    pct70 = round((pct70_high - pct70_low) / current_price * 100, 1)

    # 加权平均成本
    avg_cost = round((df["avg_price"] * df["成交量"]).sum() / total_vol, 2)

    # ── 用户规则判断 ──
    level, warning = _assess_risk(pct90, pct70, current_price, avg_cost)

    return {
        "pct90": pct90,
        "pct70": pct70,
        "avg_cost": avg_cost,
        "current_price": current_price,
        "level": level,
        "risk_warning": warning,
        "cost_range_90": [round(pct90_low, 2), round(pct90_high, 2)],
        "cost_range_70": [round(pct70_low, 2), round(pct70_high, 2)],
        "lookback_days": len(df),
    }


def _find_cost_range(sorted_df, cum_vol, total_vol, target_pct):
    """找到覆盖target_pct成交量所需的价格区间"""
    target_vol = total_vol * target_pct
    margin_vol = total_vol * (1 - target_pct) / 2  # 每侧剔除的成交量

    low_idx = (cum_vol >= margin_vol).idxmax() if len(cum_vol[cum_vol >= margin_vol]) > 0 else 0
    high_idx = (
        (cum_vol >= total_vol - margin_vol).idxmax()
        if len(cum_vol[cum_vol >= total_vol - margin_vol]) > 0
        else len(sorted_df) - 1
    )

    low_price = (
        float(sorted_df.loc[low_idx, "avg_price"])
        if low_idx < len(sorted_df)
        else float(sorted_df["avg_price"].iloc[0])
    )
    high_price = (
        float(sorted_df.loc[high_idx, "avg_price"])
        if high_idx < len(sorted_df)
        else float(sorted_df["avg_price"].iloc[-1])
    )

    return low_price, high_price


def _assess_risk(pct90, pct70, current_price, avg_cost):
    """根据用户规则评估风险等级"""
    profit_pct = round((current_price - avg_cost) / avg_cost * 100, 1)

    if pct90 >= 35 and pct70 >= 20:
        level = "极度危险"
        warning = (
            f"90%筹码集中度{pct90}%（>35%）且70%筹码集中度{pct70}%（>20%）。"
            f"筹码极度分散，套牢盘遍布各个价位，主力已无法控盘。"
            f"⚠ 绝对不能碰！这类股票每一波上涨都会面临密集套牢盘的抛压，"
            f"套你没商量。远离！"
        )
    elif pct90 >= 25:
        level = "危险"
        warning = (
            f"90%筹码集中度{pct90}%（>25%），筹码分散。"
            f"当前价{current_price:.2f}，平均成本{avg_cost:.2f}。"
            f"上涨空间大幅受限——每涨3-5%就会有套牢盘涌出。"
            f"如果实在想买，必须等跌到密集成本区下沿再考虑，快进快出。"
        )
    elif pct90 >= 20:
        level = "谨慎"
        warning = (
            f"90%筹码集中度{pct90}%（>20%），筹码偏分散。"
            f"当前已处于筹码密集区上方{profit_pct:.1f}%。"
            f"上涨空间有限，只适合下跌到位时买入、上涨就抛的快进快出策略。"
        )
    elif pct90 >= 10:
        level = "正常"
        warning = (
            f"90%筹码集中度{pct90}%，筹码集中度正常。"
            f"当前价{current_price:.2f}，成本{avg_cost:.2f}（{'盈利' if profit_pct > 0 else '亏损'}{abs(profit_pct):.1f}%）。"
            f"主力有一定控盘能力，可正常操作。"
        )
    else:
        level = "安全"
        warning = (
            f"90%筹码集中度仅{pct90}%（<10%），筹码高度集中！"
            f"主力高度控盘，抛压轻，拉升潜力大。"
            f"当前价{current_price:.2f}，平均成本{avg_cost:.2f}。"
            f"如果配合K线和技术信号，是理想的介入时机。"
        )

    return level, warning


def _fallback(reason):
    return {
        "pct90": 0,
        "pct70": 0,
        "avg_cost": 0,
        "current_price": 0,
        "level": "无法评估",
        "risk_warning": f"筹码分析暂不可用：{reason}",
        "cost_range_90": [0, 0],
        "cost_range_70": [0, 0],
        "lookback_days": 0,
    }


def quick_chip_check(code):
    """快捷筹码检查：拉K线→算集中度→返回结论"""
    from stock_analyzer.cache import cached_kline

    kline = cached_kline(code, days=120)
    return calc_chip_concentration(kline, lookback=60)
