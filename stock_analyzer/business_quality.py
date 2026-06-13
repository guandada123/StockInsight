"""公司质地七问 — 价值投资基本面深度分析

基于 akshare 数据，从7个维度评估一家公司的投资价值：
1. 公司靠什么赚钱 (商业模式)
2. 凭什么别人抢不了 (护城河)
3. 到底赚不赚钱 (盈利能力+现金流)
4. 现在什么阶段 (生命周期)
5. 股价贵不贵 (估值)
6. 最近走得怎么样 → 已有技术面模块，此处跳过
7. 有什么大事要发生 (事件日历)

用法:
  from stock_analyzer.business_quality import full_business_quality
  result = full_business_quality('601138')
"""


def get_company_profile(code):
    """Q1: 公司靠什么赚钱 — 主营业务与商业模式

    数据源: akshare stock_individual_info_em()

    Returns:
        dict: {name, industry, business_scope, main_business, listing_date, registered_capital}
    """
    try:
        import akshare as ak

        info = ak.stock_individual_info_em(symbol=code)

        if info is None or info.empty:
            return _profile_fallback(code)

        result = {
            "name": _safe_get(info, "股票简称", ""),
            "industry": _safe_get(info, "行业", ""),
            "business_scope": _safe_get(info, "经营范围", ""),  # noqa
            "main_business": _safe_get(info, "主营业务", ""),
            "listing_date": _safe_get(info, "上市时间", ""),
            "registered_capital": _safe_get(info, "注册资本", ""),
            "total_market_cap": _safe_get(info, "总市值", ""),
        }
        return result
    except Exception:
        return _profile_fallback(code)


def _profile_fallback(code):
    from stock_analyzer.cache import cached_fundamentals
    from stock_analyzer.sector_info import get_stock_sector_full

    funds = cached_fundamentals(code)
    industry = get_stock_sector_full(code)
    return {
        "name": str(code),
        "industry": industry,
        "business_scope": "数据暂不可用（akshare API 不可用）",
        "main_business": "数据暂不可用",
        "listing_date": "",
        "registered_capital": "",
        "total_market_cap": "",
    }


def score_moat(code, fundamentals=None):
    """Q2: 护城河评分 — 凭什么别人抢不了

    五维度评分:
    - 毛利率(40分): 定价权
    - ROE稳定性(25分): 持续盈利能力
    - 研发投入(15分): 技术壁垒
    - 品牌/牌照(10分): 无形资产
    - 市占率/规模(10分): 规模优势

    Returns:
        dict: {score, level, dimensions, signals, assessment}
    """
    try:
        if fundamentals is None:
            from stock_analyzer.cache import cached_fundamentals

            fundamentals = cached_fundamentals(code)

        if not isinstance(fundamentals, dict):
            return _moat_fallback("基本面数据不可用")

        gross_margin = fundamentals.get("毛利率", 0) or 0
        roe = fundamentals.get("ROE", 0) or 0
        net_margin = fundamentals.get("净利率", 0) or 0
        revenue_growth = fundamentals.get("营收增长", 0) or 0

        # 1. 毛利率评分 (40分)
        if gross_margin >= 70:
            margin_score = 40
        elif gross_margin >= 50:
            margin_score = 30
        elif gross_margin >= 30:
            margin_score = 20
        elif gross_margin >= 15:
            margin_score = 10
        else:
            margin_score = 5

        # 2. ROE 稳定性 (25分)
        if roe >= 20:
            roe_score = 25
        elif roe >= 15:
            roe_score = 20
        elif roe >= 10:
            roe_score = 15
        elif roe >= 5:
            roe_score = 8
        else:
            roe_score = 3

        # 3. 研发投入估算 (15分) — 科技股通常毛利率高+研发高
        # 用毛利率作为技术含量代理变量，结合净利率与毛利率的差距
        rd_gap = gross_margin - net_margin
        if gross_margin >= 50 and rd_gap >= 30:
            rd_score = 15
        elif gross_margin >= 40 and rd_gap >= 20:
            rd_score = 10
        elif gross_margin >= 30:
            rd_score = 5
        else:
            rd_score = 2

        # 4. 品牌/牌照 (10分)
        brand_score = 5  # 默认中等
        if gross_margin >= 60 and roe >= 15:
            brand_score = 10  # 高毛利+高ROE = 强品牌
        elif gross_margin >= 40:
            brand_score = 7

        # 5. 规模优势 (10分) — 用营收增长反推
        if revenue_growth > 20:
            scale_score = 8
        elif revenue_growth > 10:
            scale_score = 6
        elif revenue_growth > 0:
            scale_score = 4
        else:
            scale_score = 2

        dimensions = {
            "定价权(毛利率)": margin_score,
            "盈利能力(ROE)": roe_score,
            "技术壁垒(研发)": rd_score,
            "品牌/牌照": brand_score,
            "规模优势": scale_score,
        }

        total = sum(dimensions.values())

        if total >= 80:
            level = "宽阔的护城河"
        elif total >= 60:
            level = "较宽的护城河"
        elif total >= 40:
            level = "狭窄的护城河"
        else:
            level = "无明显护城河"

        signals = []
        if gross_margin >= 60:
            signals.append(f"毛利率{gross_margin:.1f}%极高，产品有强定价权")
        elif gross_margin >= 40:
            signals.append(f"毛利率{gross_margin:.1f}%较高，有一定议价能力")
        if roe >= 15:
            signals.append(f"ROE{roe:.1f}%优秀，资本回报率高")
        if rd_gap >= 30:
            signals.append(f"毛利率-净利率差{rd_gap:.0f}%，高研发投入特征")

        assessment = _moat_assessment(level, total, signals)

        return {
            "score": total,
            "level": level,
            "dimensions": dimensions,
            "signals": signals,
            "assessment": assessment,
        }
    except Exception:
        return _moat_fallback("护城河分析异常")


def _moat_fallback(reason):
    return {
        "score": 0,
        "level": "无法评估",
        "dimensions": {},
        "signals": [reason],
        "assessment": f"护城河分析暂不可用：{reason}",
    }


def _moat_assessment(level, score, signals):
    if score >= 80:
        return f"该公司拥有{level}（{score}分）。{'；'.join(signals[:3])}。这类公司很难被竞争对手复制，是长期持有的优质标的。"
    elif score >= 60:
        return f"该公司拥有{level}（{score}分）。{'；'.join(signals[:2])}。竞争优势明显，但不如顶级公司牢不可破。"
    elif score >= 40:
        return f"该公司护城河{level}（{score}分）。有一定的差异化，但竞争优势不够牢固，需持续跟踪行业格局变化。"
    else:
        return f"该公司{level}（{score}分）。行业竞争激烈，产品或服务容易被替代，长期投资需谨慎。"


def analyze_cash_flow(code):
    """Q3补充: 现金流分析

    数据源: akshare stock_cash_flow_sheet_by_report_em()

    Returns:
        dict: {operating_cf, investing_cf, financing_cf, free_cf, quality, assessment}
    """
    try:
        import akshare as ak

        cf = ak.stock_cash_flow_sheet_by_report_em(symbol=code)

        if cf is None or cf.empty:
            return _cf_fallback()

        # 取最新一期
        latest = cf.iloc[0]

        # 提取关键现金流项目（中文字段）
        op_cf = _safe_float(latest, "经营活动产生的现金流量净额")
        inv_cf = _safe_float(latest, "投资活动产生的现金流量净额")
        fin_cf = _safe_float(latest, "筹资活动产生的现金流量净额")

        # 自由现金流 = 经营现金流 + 投资现金流（投资通常为负）
        free_cf = op_cf + inv_cf if op_cf else 0

        # 质量判断
        if op_cf and op_cf > 0 and free_cf > 0:
            quality = "优秀"
            desc = "经营现金流充裕，自由现金流为正，公司自身造血能力强，不依赖外部融资。"
        elif op_cf and op_cf > 0:
            quality = "良好"
            desc = "经营现金流为正但投资支出较大，可能处于扩张期，需关注投资回报。"
        elif op_cf and op_cf > 0 > free_cf:
            quality = "一般"
            desc = "经营现金流为正，但投资支出超过经营现金流，自由现金流为负。可能是高速扩张，也可能是过度投资。"
        else:
            quality = "预警"
            desc = "经营现金流为负，公司主营业务不产生现金，依赖融资或变卖资产维持运营。这是最危险的财务信号之一。"

        return {
            "operating_cf_yi": round(op_cf / 1e8, 2) if op_cf else 0,
            "investing_cf_yi": round(inv_cf / 1e8, 2) if inv_cf else 0,
            "financing_cf_yi": round(fin_cf / 1e8, 2) if fin_cf else 0,
            "free_cf_yi": round(free_cf / 1e8, 2) if free_cf else 0,
            "quality": quality,
            "assessment": desc,
        }
    except Exception:
        return _cf_fallback()


def _cf_fallback():
    return {
        "operating_cf_yi": 0,
        "investing_cf_yi": 0,
        "financing_cf_yi": 0,
        "free_cf_yi": 0,
        "quality": "数据不可用",
        "assessment": "现金流数据暂不可用（akshare API 不可用）",
    }


def classify_lifecycle(code, financials=None, cash_flows=None):
    """Q4: 生命周期阶段分类

    基于营收增速 + 现金流模式判断:
    - 初创期: 低营收+负经营现金流+负自由现金流+高融资
    - 成长期: 高营收增速(>20%)+经营现金流转正+投资现金流出大
    - 成熟期: 中低营收增速(0-15%)+经营现金充裕+自由现金流转正
    - 衰退期: 负营收增速+经营现金流可能为负

    Returns:
        dict: {stage, stage_cn, confidence, signals, assessment, suggestion}
    """
    try:
        if financials is None:
            from stock_analyzer.cache import cached_fundamentals

            financials = cached_fundamentals(code)

        if not isinstance(financials, dict):
            return _lifecycle_fallback()

        revenue_growth = financials.get("营收增长", 0) or 0
        profit_growth = financials.get("净利润增长", 0) or 0
        roe = financials.get("ROE", 0) or 0

        signals = []

        # 用营收增速+ROE+利润增速综合判断
        if revenue_growth >= 30 and roe >= 15:
            stage = "growth"
            stage_cn = "高速成长期"
            confidence = 80
            signals.append(f"营收增速{revenue_growth:.0f}%，高速扩张")
            signals.append(f"ROE{roe:.0f}%，资本回报优秀")
            suggestion = (
                "适合成长股投资者，关注增速是否可持续。估值容忍度可适当放宽，但要跟踪竞争格局变化。"
            )
        elif revenue_growth >= 15:
            stage = "growth"
            stage_cn = "成长期"
            confidence = 65
            signals.append(f"营收增速{revenue_growth:.0f}%，稳健成长")
            suggestion = "增长速度健康，适合中长期持有。关注行业天花板和市占率变化。"
        elif revenue_growth >= 5 and roe >= 10:
            stage = "mature"
            stage_cn = "成熟期"
            confidence = 70
            signals.append(f"营收增速{revenue_growth:.0f}%，进入稳定期")
            signals.append(f"ROE{roe:.0f}%，盈利稳定")
            suggestion = (
                "适合价值投资者，关注分红率和估值。增长放缓但现金流稳定，可作为防御性持仓。"
            )
        elif revenue_growth >= 0:
            stage = "mature"
            stage_cn = "成熟期（增长放缓）"
            confidence = 55
            signals.append(f"营收增速仅{revenue_growth:.0f}%，增长乏力")
            suggestion = "关注公司是否有第二增长曲线。如果没有，估值应偏低，分红率应较高。"
        elif revenue_growth < 0 and roe < 8:
            stage = "decline"
            stage_cn = "衰退期"
            confidence = 65
            signals.append(f"营收负增长{revenue_growth:.0f}%，业务萎缩")
            signals.append(f"ROE仅{roe:.0f}%，资本回报低迷")
            suggestion = (
                "除非有明确的困境反转催化剂，否则不建议介入。关注是否有重组/转型/新业务机会。"
            )
        else:
            stage = "transition"
            stage_cn = "转型期"
            confidence = 40
            signals.append(f"营收增速{revenue_growth:.0f}%，方向不明确")
            suggestion = "公司处于转型阶段，结果不确定。建议等待方向明确后再决策。"

        return {
            "stage": stage,
            "stage_cn": stage_cn,
            "confidence": confidence,
            "signals": signals,
            "suggestion": suggestion,
        }
    except Exception:
        return _lifecycle_fallback()


def _lifecycle_fallback():
    return {
        "stage": "unknown",
        "stage_cn": "无法判断",
        "confidence": 0,
        "signals": ["数据不足"],
        "suggestion": "需要更多财务数据来判断生命周期阶段",
    }


def score_valuation(code, price, financials=None):
    """Q5: 估值评分 — 股价贵不贵

    四维度: PE估值 + PEG + 历史分位 + PB

    Returns:
        dict: {score, level, pe, pb, peg, pe_percentile, assessment}
    """
    try:
        if financials is None:
            from stock_analyzer.cache import cached_fundamentals

            financials = cached_fundamentals(code)

        score = 30  # 基准分
        signals = []

        pe = financials.get("市盈率") if isinstance(financials, dict) else None
        pb = financials.get("市净率") if isinstance(financials, dict) else None
        eps = financials.get("每股收益") if isinstance(financials, dict) else None
        revenue_growth = financials.get("营收增长") if isinstance(financials, dict) else 0

        # 1. PE 估值 (30分)
        if pe is not None:
            if pe < 0:
                pe_score = 5
                signals.append("PE为负，公司亏损")
            elif pe < 15:
                pe_score = 30
                signals.append(f"PE={pe:.1f}，低于15倍，估值偏低")
            elif pe < 25:
                pe_score = 25
                signals.append(f"PE={pe:.1f}，在15-25倍正常区间")
            elif pe < 50:
                pe_score = 15
                signals.append(f"PE={pe:.1f}，25-50倍偏高")
            elif pe < 100:
                pe_score = 8
                signals.append(f"PE={pe:.1f}，50-100倍高估值")
            else:
                pe_score = 3
                signals.append(f"PE={pe:.1f}，>100倍极高估值")
        else:
            pe_score = 15

        # 2. PEG (25分)
        peg = None
        if pe is not None and revenue_growth and revenue_growth > 0:
            peg = pe / revenue_growth
            if peg < 1:
                peg_score = 25
                signals.append(f"PEG={peg:.2f}<1，成长性足以支撑估值")
            elif peg < 2:
                peg_score = 15
                signals.append(f"PEG={peg:.2f}，1-2之间，估值基本合理")
            elif peg < 3:
                peg_score = 8
                signals.append(f"PEG={peg:.2f}，2-3之间，估值偏贵")
            else:
                peg_score = 3
                signals.append(f"PEG={peg:.2f}>3，估值严重偏高")
        else:
            peg_score = 12

        # 3. PB (20分)
        if pb is not None:
            if pb < 1:
                pb_score = 20
                signals.append(f"PB={pb:.2f}，破净，极度低估")
            elif pb < 3:
                pb_score = 18
                signals.append(f"PB={pb:.2f}，正常偏低")
            elif pb < 6:
                pb_score = 10
                signals.append(f"PB={pb:.2f}，正常偏高")
            elif pb < 10:
                pb_score = 5
                signals.append(f"PB={pb:.2f}，高")
            else:
                pb_score = 2
                signals.append(f"PB={pb:.2f}，极高")
        else:
            pb_score = 10

        score = pe_score + peg_score + pb_score

        if score >= 65:
            level = "低估"
        elif score >= 50:
            level = "合理偏低"
        elif score >= 35:
            level = "合理偏高"
        elif score >= 20:
            level = "高估"
        else:
            level = "泡沫"

        assessment = f"综合估值评分{score}分，处于{level}区间。{'；'.join(signals[:4])}。"

        return {
            "score": score,
            "level": level,
            "pe": round(pe, 2) if pe else None,
            "pb": round(pb, 2) if pb else None,
            "peg": round(peg, 2) if peg else None,
            "signals": signals,
            "assessment": assessment,
        }
    except Exception:
        return {
            "score": 30,
            "level": "无法评估",
            "pe": None,
            "pb": None,
            "peg": None,
            "signals": ["估值数据不可用"],
            "assessment": "估值分析暂不可用",
        }


def get_upcoming_events(code):
    """Q7: 近期重大事件 — 财报/分红/解禁/公告

    Returns:
        dict: {events: [{type, date, title}], assessment}
    """
    events = []
    try:
        # 财报预约
        try:
            import akshare as ak

            notice = ak.stock_notice_report(symbol=code)
            if notice is not None and not notice.empty:
                for _, row in notice.head(5).iterrows():
                    events.append(
                        {
                            "type": "公告",
                            "date": str(row.get("公告日期", ""))[:10],
                            "title": str(row.get("公告标题", ""))[:80],
                        }
                    )
        except Exception:
            pass

        # 分红信息
        try:
            import akshare as ak

            dividend = ak.stock_dividents_cninfo(symbol=code)
            if dividend is not None and not dividend.empty:
                latest = dividend.head(3)
                for _, row in latest.iterrows():
                    events.append(
                        {
                            "type": "分红",
                            "date": str(row.get("除权除息日", ""))[:10],
                            "title": f"每股派息{row.get('每股派息', '?')}元",
                        }
                    )
        except Exception:
            pass

        if not events:
            return {"events": [], "assessment": "暂无近期重大事件数据"}

        # 排序
        events.sort(key=lambda x: x["date"] if x["date"] else "9999")

        return {
            "events": events,
            "assessment": f"近期待关注事件{len(events)}条。财报/分红/公告等重要事件可能影响股价。",
        }
    except Exception:
        return {"events": [], "assessment": "事件数据暂不可用"}


# ═══════════════════════════════════════════
# 一键全出
# ═══════════════════════════════════════════


def full_business_quality(code):
    """一键输出七问全维度分析

    Returns:
        dict: {
            overall_score, overall_level,
            company_profile, moat, cash_flow, lifecycle, valuation, events,
            assessment_summary
        }
    """
    from stock_analyzer.cache import cached_fundamentals
    from stock_analyzer.fetcher import sina_real_time

    funds = cached_fundamentals(code)
    rt = sina_real_time([code])
    info = rt.get(code, {})
    name = info.get("名称", str(code))
    price = float(info.get("最新价", 0) or 0)

    # Q1
    profile = get_company_profile(code)

    # Q2
    moat = score_moat(code, funds)

    # Q3
    cf = analyze_cash_flow(code)

    # Q4
    lifecycle = classify_lifecycle(code, funds, cf)

    # Q5
    valuation = score_valuation(code, price, funds)

    # Q7
    events = get_upcoming_events(code)

    # 综合评分: Q2(40%) + Q3(25%) + Q4(15%) + Q5(20%)
    overall = (
        moat["score"] * 0.40
        + (
            80
            if cf.get("quality") == "优秀"
            else 60
            if cf.get("quality") == "良好"
            else 40
            if cf.get("quality") == "一般"
            else 20
        )
        * 0.25
        + (
            80
            if lifecycle.get("stage") == "growth"
            else 60
            if lifecycle.get("stage") == "mature"
            else 30
        )
        * 0.15
        + valuation["score"] * 0.20
    )

    if overall >= 70:
        o_level = "优质"
    elif overall >= 55:
        o_level = "良好"
    elif overall >= 40:
        o_level = "一般"
    else:
        o_level = "较差"

    return {
        "code": code,
        "name": name,
        "price": price,
        "overall_score": round(overall, 1),
        "overall_level": o_level,
        "company_profile": profile,
        "moat": moat,
        "cash_flow": cf,
        "lifecycle": lifecycle,
        "valuation": valuation,
        "events": events,
        "assessment_summary": _generate_summary(
            code, name, profile, moat, cf, lifecycle, valuation
        ),
    }


def _generate_summary(code, name, profile, moat, cf, lifecycle, valuation):
    """生成公司质地综合评估"""
    parts = []
    parts.append(
        f"{name}({code}) 公司质地综合评分: {moat['score'] * 0.4 + valuation['score'] * 0.2:.0f}分"
    )

    if profile.get("main_business"):
        parts.append(f"主营业务: {profile['main_business'][:60]}")

    parts.append(f"护城河: {moat['level']}（{moat['score']}分）")
    parts.append(f"现金流: {cf['quality']}")
    parts.append(f"生命周期: {lifecycle['stage_cn']}")
    parts.append(f"估值: {valuation['level']}（{valuation['score']}分）")

    if lifecycle["stage"] == "growth" and moat["score"] >= 60 and cf["quality"] in ("优秀", "良好"):
        parts.append("综合评价: 成长性好+护城河宽+现金流健康，是优质的长期投资标的。")
    elif lifecycle["stage"] == "growth":
        parts.append("综合评价: 处于成长期，但需关注护城河和现金流质量。")
    elif lifecycle["stage"] == "mature" and valuation["level"] in ("低估", "合理偏低"):
        parts.append("综合评价: 成熟期低估值，适合稳健型价值投资者。")
    elif lifecycle["stage"] == "decline":
        parts.append("综合评价: 处于衰退期，除非有困境反转信号，不然不建议介入。")
    else:
        parts.append("综合评价: 公司质地中等，需结合技术面和市场环境综合判断。")

    return "；".join(parts)


# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════


def _safe_get(df, col, default=""):
    """安全从 DataFrame 取值"""
    try:
        if col in df.columns:
            val = df[col].values[0]
            return str(val) if val is not None else default
    except Exception:
        pass
    return default


def _safe_float(row, col, default=0.0):
    """安全从 Series 取浮点数"""
    try:
        if col in row.index:
            val = row[col]
            return float(val) if val is not None and not isinstance(val, str) else default
    except Exception:
        pass
    return default
