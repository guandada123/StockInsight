"""筹码面因子 — 股东人数变化/户均持股/筹码集中度

借鉴对方36因子体系中的筹码面因子，检测主力吸筹/出货行为。
数据源：akshare 十大流通股东 + 股东人数变化
"""


def calc_chip_concentration(code):
    """计算筹码集中度因子

    返回 dict: 股东人数趋势/户均持股变化/集中度评分
    """
    result = {
        "股东人数趋势": "未知",
        "户均持股变化": 0.0,
        "筹码集中度评分": 50,
        "股东人数变化率": 0.0,
        "数据可用": False,
    }

    try:
        import akshare as ak

        df = ak.stock_holder_number_em(symbol=code)
        if df is None or df.empty or len(df) < 2:
            return result

        # 最新两期股东人数
        latest = df.iloc[0]
        prev = df.iloc[1]
        holders_now = float(latest.get("股东人数", latest.iloc[1] if len(df.columns) > 1 else 0))
        holders_prev = float(prev.get("股东人数", prev.iloc[1] if len(df.columns) > 1 else 0))

        if holders_prev == 0:
            return result

        change_pct = (holders_now - holders_prev) / holders_prev * 100

        # 判断趋势
        if change_pct < -5:
            trend = "集中(主力吸筹)"
            score = 80
        elif change_pct < -2:
            trend = "小幅集中"
            score = 65
        elif change_pct < 2:
            trend = "稳定"
            score = 50
        elif change_pct < 5:
            trend = "小幅分散"
            score = 35
        else:
            trend = "分散(主力出货)"
            score = 20

        # 户均持股估算
        total_shares = float(latest.get("总股本", 0)) if "总股本" in latest.index else 0
        if total_shares > 0 and holders_now > 0:
            avg_hold = total_shares / holders_now
        else:
            avg_hold = 0

        result = {
            "股东人数趋势": trend,
            "股东人数变化率": round(change_pct, 2),
            "户均持股变化": round(avg_hold, 2),
            "筹码集中度评分": score,
            "数据可用": True,
        }
    except Exception:
        pass

    return result


def calc_volume_price_factors(kline):
    """量价配合因子

    返回 dict: 量价配合度/放量上涨天数/缩量下跌天数/资金流向推断
    """
    if kline is None or len(kline) < 20:
        return {"量价配合度评分": 50}

    close = kline["收盘"]
    vol = kline["成交量"] if "成交量" in kline.columns else None
    if vol is None:
        return {"量价配合度评分": 50}

    # 近20日量价配合分析
    up_days_vol = 0  # 放量上涨日
    down_days_shrink = 0  # 缩量下跌日
    vol_avg = vol.tail(20).mean()

    for i in range(-20, 0):
        price_chg = (close.iloc[i] / close.iloc[i - 1] - 1) if i > -len(close) else 0
        vol_chg = vol.iloc[i] / vol_avg - 1

        if price_chg > 0 and vol_chg > 0.2:
            up_days_vol += 1
        if price_chg < 0 and vol_chg < -0.2:
            down_days_shrink += 1

    # 配合度评分
    ratio = (up_days_vol + down_days_shrink) / 20
    score = min(ratio * 120, 100)

    return {
        "量价配合度评分": round(score, 1),
        "放量上涨天数": up_days_vol,
        "缩量下跌天数": down_days_shrink,
        "量价状态": "健康" if score > 60 else ("一般" if score > 40 else "背离"),
    }


def calc_turnover_analysis(kline):
    """换手率分析因子 — 检测异常换手"""
    if kline is None or len(kline) < 20:
        return {"换手率评分": 50}

    result = {"换手率评分": 50, "异常换手": False}

    # 如果有换手率列
    if "换手率" in kline.columns:
        turnover = kline["换手率"].tail(20)
        avg_turnover = turnover.mean()
        max_turnover = turnover.max()

        # 换手率评分
        if 2 < avg_turnover < 8:
            score = 70  # 活跃但不异常
        elif avg_turnover > 15:
            score = 30  # 过度活跃，可能是对倒
        elif avg_turnover < 0.5:
            score = 40  # 交易清淡
        else:
            score = 50

        # 异常换手检测
        if max_turnover > avg_turnover * 3:
            result["异常换手"] = True
            score -= 10

        result["换手率评分"] = max(score, 10)
        result["近20日均换手率"] = round(avg_turnover, 2)
    # 用成交量/总股本估算换手率
    elif "成交量" in kline.columns:
        vol = kline["成交量"].tail(20).mean()
        result["近20日均成交量"] = int(vol)

    return result


def composite_chip_score(code, kline=None):
    """筹码面综合评分（0-100）

    聚合：筹码集中度 + 量价配合 + 换手率分析
    """
    scores = []

    chip = calc_chip_concentration(code)
    if chip.get("数据可用"):
        scores.append(("筹码集中度", chip["筹码集中度评分"], 0.4))
    else:
        scores.append(("筹码集中度", 50, 0.2))

    if kline is not None:
        vp = calc_volume_price_factors(kline)
        scores.append(("量价配合", vp.get("量价配合度评分", 50), 0.35))

        to = calc_turnover_analysis(kline)
        scores.append(("换手率", to.get("换手率评分", 50), 0.25))
    else:
        scores.append(("量价配合", 50, 0.4))
        scores.append(("换手率", 50, 0.4))

    total = sum(s * w for _, s, w in scores)
    return round(total, 1)
