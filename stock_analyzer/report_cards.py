"""HTML 报告生成 — 个股详情卡片

从 report_html.py 拆分而来，包含个股详情卡片的 HTML 生成函数。
"""

from .report_html_utils import (
    _change_color,
    _change_sign,
    _color_for_value,
    _escape_html,
    _fmt_num,
    _rating_bg_color,
    _rating_color,
    _tip,
)
from .report_narratives import (
    _build_news_section,
    _build_operation_advice,
    _build_stock_narrative,
)


def _stock_detail_card(code: str, detail: dict, index: int = 1) -> str:
    """生成单只股票的分析详情卡片 HTML"""
    name = detail.get("name", code)
    score = detail.get("score", "")
    rating = detail.get("rating", "")
    price = _fmt_num(detail.get("price", ""))
    change = detail.get("change", "")

    sr = detail.get("support_resistance", {})
    stop = detail.get("stop_levels", {})
    tech = detail.get("technical_summary", {})
    risk = detail.get("risk_metrics", {})
    signals = detail.get("signals", {})

    # 短线/长线风格 & 板块
    sector = detail.get("sector", "")
    trading_style = detail.get("trading_style", {})

    supports = sr.get("支撑位", [])
    resistances = sr.get("压力位", [])
    ma_support = sr.get("均线支撑", {})

    stop_loss = stop.get("止损参考价", "")
    stop_pct = stop.get("止损幅度%", "")
    take_profit = stop.get("止盈参考价", "")
    tp_pct = stop.get("止盈幅度%", "")

    ma_status = tech.get("ma_status", {})
    macd = tech.get("macd_signal", "")
    rsi = tech.get("rsi_signal", "")
    rsi_val = tech.get("rsi_value", "")
    kdj = tech.get("kdj_signal", "")

    sharpe = risk.get("sharpe_ratio", "")
    max_dd = risk.get("max_drawdown_pct", "")
    var_val = risk.get("VaR_95_pct", "")

    bias = signals.get("bias", "")

    # 构建均线文字
    ma_text_parts = []
    for w in [5, 10, 20, 60]:
        info = ma_status.get(f"MA{w}", {})
        if info:
            pos = info.get("股价位置", "")
            ma_text_parts.append(f"MA{w}({pos})")
    ma_text = " / ".join(ma_text_parts) if ma_text_parts else "-"

    # 技术面评语
    tech_commentary = []
    if macd in ("多头", "金叉"):
        tech_commentary.append("MACD处于多头区域")
    elif macd in ("空头", "死叉"):
        tech_commentary.append("MACD处于空头区域")

    if rsi == "超买":
        tech_commentary.append("RSI超买，注意回调风险")
    elif rsi == "超卖":
        tech_commentary.append("RSI超卖，可能存在反弹机会")

    if kdj in ("金叉",):
        tech_commentary.append("KDJ金叉信号")
    elif kdj in ("死叉",):
        tech_commentary.append("KDJ死叉信号")

    # 止损止盈评语
    sl_commentary = []
    if stop_loss and isinstance(stop_loss, int | float):
        sl_commentary.append(f"建议止损价 {stop_loss}，回撤幅度约{stop_pct}%")
    if take_profit and isinstance(take_profit, int | float):
        sl_commentary.append(f"建议止盈价 {take_profit}，预期涨幅约{tp_pct}%")

    # 短线/长线风格信息
    ts_short_score = trading_style.get("short_term_score", 0)
    ts_long_score = trading_style.get("long_term_score", 0)
    ts_style = trading_style.get("style", "")
    ts_confidence = trading_style.get("style_confidence", "")
    ts_short_basis = trading_style.get("short_term_basis", "")
    ts_long_basis = trading_style.get("long_term_basis", "")

    # 量化因子评分
    quant_score = detail.get("quant_score", {})
    qs_composite = quant_score.get("composite_score", score)
    qs_rating = quant_score.get("rating", rating)
    # 如果外部未传score，回退到量化综合评分
    if (score == "" or score is None) and qs_composite:
        score = qs_composite
    qs_factors = quant_score.get("factor_scores", {})
    qs_mom = qs_factors.get("momentum", {}).get("score", 0)
    qs_tech = qs_factors.get("technical", {}).get("score", 0)
    qs_fund = qs_factors.get("fundamental", {}).get("score", 0)
    qs_vol = qs_factors.get("volume", {}).get("score", 0)
    qs_risk_factor = qs_factors.get("risk", {}).get("score", 0)
    qs_sentiment = qs_factors.get("sentiment", {}).get("score", 50)

    # 资金流向（fund_flow 在 stock_details 中传入）
    fund_flow = detail.get("fund_flow", {}) or {}
    if isinstance(fund_flow, dict):
        ff_main_ratio = fund_flow.get("主力净流入-净占比", "")
        ff_main_amount = fund_flow.get("主力净流入-净额", "")
        ff_super_ratio = fund_flow.get("超大单净流入-净占比", "")
        ff_date = fund_flow.get("日期", "")
    else:
        ff_main_ratio = ff_main_amount = ff_super_ratio = ff_date = ""
    # 格式化主力金额（元→亿）
    ff_amount_str = ""
    if ff_main_amount and isinstance(ff_main_amount, int | float) and abs(ff_main_amount) > 0:
        ff_amount_str = f"{ff_main_amount / 1e8:.2f}亿"

    # 新闻舆情
    news_headlines = detail.get("news_headlines", [])
    news_times = detail.get("news_times", [])
    news_sources = detail.get("news_sources", [])

    # 国家队持股
    national_team = detail.get("national_team", {}) or {}
    nt_badge = ""
    if national_team.get("has_national_team"):
        holders = national_team.get("holders", [])
        nt_badge = '<span class="nt-badge">🏛️ 国家队</span>'
        if holders:
            # 显示前两个持有者简称
            short_names = []
            for h in holders:
                if "证金" in h or "汇金" in h:
                    short_names.append("证金/汇金")
                elif "社保" in h:
                    short_names.append("社保")
                elif "养老" in h:
                    short_names.append("养老金")
            if short_names:
                nt_badge = (
                    '<span class="nt-badge" title="十大流通股东中包含：'
                    + "; ".join(holders[:3])
                    + '">🏛️ 国家队('
                    + "/".join(set(short_names))
                    + ")</span>"
                )
    style_colors = {"短线": "#e65100", "长线": "#1565c0", "短线+长线": "#6a1b9a", "观望": "#757575"}

    r_color = _rating_color(rating)
    r_bg = _rating_bg_color(rating)
    ch_color = _change_color(change)
    sc_color = style_colors.get(ts_style, "#666")

    return f"""
    <div class="stock-detail-card">
      <div class="sd-header">
        <span class="sd-code">{code}</span>
        <span class="sd-name">{name}</span>
        {'<span class="sd-sector">' + sector + "</span>" if sector else ""}
        <span class="sd-price" style="color:{ch_color}">{price}</span>
        <span class="sd-change" style="color:{ch_color}">{_change_sign(change)}%</span>
        <span class="rating-badge" style="color:{r_color};background:{r_bg}">{rating}</span>
        <span class="sd-score" style="color:{_color_for_value(score)}">{score}/100</span>
        {f'<span class="sd-style-badge" style="background:{sc_color}">{ts_style}</span>' if ts_style else ""}
        {nt_badge}
      </div>
      <div class="sd-body">
        {_build_stock_narrative(detail)}
        <div class="sd-section">
          <div class="sd-section-title">技术面</div>
          <div class="sd-info-grid">
            <div class="sd-info-item"><span class="sd-label">{_tip("MACD")}</span><span class="sd-value {"sd-bullish" if macd in ("多头", "金叉") else "sd-bearish" if macd in ("空头", "死叉") else ""}">{macd}</span></div>
            <div class="sd-info-item"><span class="sd-label">{_tip("RSI")}</span><span class="sd-value {"sd-warning" if rsi == "超买" else "sd-oversold" if rsi == "超卖" else ""}">{rsi_val} - {rsi}</span></div>
            <div class="sd-info-item"><span class="sd-label">{_tip("KDJ")}</span><span class="sd-value">{kdj}</span></div>
            <div class="sd-info-item"><span class="sd-label">{_tip("均线")}</span><span class="sd-value sd-ma">{ma_text}</span></div>
          </div>
          <div class="sd-tech-comment">{"；".join(tech_commentary) if tech_commentary else "技术指标中性"}</div>
        </div>

        <div class="sd-section">
          <div class="sd-section-title">支撑 · 压力 · 止损 · 止盈</div>
          <div class="sd-levels-grid">
            <div class="sd-level-item"><span class="sd-level-label">{_tip("支撑位")}</span><span class="sd-level-value">{" / ".join(str(s) for s in supports[:2]) if supports else "-"}</span></div>
            <div class="sd-level-item"><span class="sd-level-label">{_tip("压力位")}</span><span class="sd-level-value">{" / ".join(str(r) for r in resistances[:2]) if resistances else "-"}</span></div>
            <div class="sd-level-item"><span class="sd-level-label">均线支撑</span><span class="sd-level-value">{", ".join(f"{k}={v}" for k, v in ma_support.items()) if ma_support else "-"}</span></div>
            <div class="sd-level-item"><span class="sd-level-label">止损参考</span><span class="sd-level-value" style="color:#2e7d32">{stop_loss}</span></div>
            <div class="sd-level-item"><span class="sd-level-label">止盈参考</span><span class="sd-level-value" style="color:#d32f2f">{take_profit}</span></div>
            <div class="sd-level-item"><span class="sd-level-label">{_tip("ATR")}</span><span class="sd-level-value">{stop.get("ATR", "-")} ({stop.get("ATR占比%", "-")}%)</span></div>
          </div>
          {'<div class="sd-sl-comment">' + "；".join(sl_commentary) + "</div>" if sl_commentary else ""}
        </div>

        <div class="sd-section">
          <div class="sd-section-title">资金流向</div>
          <div class="sd-levels-grid">
            <div class="sd-level-item"><span class="sd-level-label">主力净占比</span><span class="sd-level-value" style="color:{"#d32f2f" if ff_main_ratio != "" and ff_main_ratio is not None and float(str(ff_main_ratio).replace("%", "")) > 0 else "#2e7d32" if ff_main_ratio != "" and ff_main_ratio is not None and float(str(ff_main_ratio).replace("%", "")) < 0 else "#333"}">{ff_main_ratio}{"%" if ff_main_ratio != "" and "%" not in str(ff_main_ratio) else ""}</span></div>
            <div class="sd-level-item"><span class="sd-level-label">主力净额</span><span class="sd-level-value">{ff_amount_str if ff_amount_str else ("-" if not ff_main_amount else f"{ff_main_amount:.0f}")}</span></div>
            <div class="sd-level-item"><span class="sd-level-label">超大单净占比</span><span class="sd-level-value">{ff_super_ratio}{"%" if ff_super_ratio != "" and "%" not in str(ff_super_ratio) else ""}</span></div>
            <div class="sd-level-item"><span class="sd-level-label">数据日期</span><span class="sd-level-value">{ff_date if ff_date else "-"}</span></div>
          </div>
          <div class="sd-sl-comment" style="font-size:11px;color:#666;margin-top:4px;">
            <span class="term-t">主力资金<span class="term-t-popup">超大单(≥100万元)和大单(20~100万元)合计，反映机构和大资金动向。正值=净流入(看涨信号)，负值=净流出(看跌信号)。</span></span>
            ｜
            <span class="term-t">国家队<span class="term-t-popup">证金公司、汇金公司、社保基金、养老金的合计持股。出现在十大流通股东中代表有国家资金背书。</span></span>
          </div>
        </div>
        </div>

        <div class="sd-section">
          <div class="sd-section-title">风险指标</div>
          <div class="sd-info-grid">
            <div class="sd-info-item"><span class="sd-label">{_tip("夏普比率")}</span><span class="sd-value">{sharpe}</span></div>
            <div class="sd-info-item"><span class="sd-label">{_tip("最大回撤")}</span><span class="sd-value" style="color:{"#2e7d32" if max_dd and float(max_dd) > -10 else "#d32f2f"}">{max_dd}%</span></div>
            <div class="sd-info-item"><span class="sd-label">{_tip("VaR", "VaR")}(95%)</span><span class="sd-value">{var_val}%</span></div>
            <div class="sd-info-item"><span class="sd-label">信号</span><span class="sd-value {"sd-bullish" if bias == "bullish" else "sd-bearish" if bias == "bearish" else ""}">{bias}</span></div>
          </div>
        </div>

        <div class="sd-section">
          <div class="sd-section-title">量化因子评分 <span style="font-size:11px;color:#999;font-weight:400;">（参考：≥80优秀 / 60-79良好 / 40-59一般 / 20-39较差 / <20很差）</span></div>
          <div class="sd-info-grid">
            <div class="sd-info-item"><span class="sd-label">综合评分</span><span class="sd-value" style="color:{_color_for_value(qs_composite)}">{qs_composite} → {qs_rating}</span></div>
            <div class="sd-info-item"><span class="sd-label">{_tip("动量分")}</span><span class="sd-value" style="color:{_color_for_value(qs_mom)}">{qs_mom:.0f}</span></div>
            <div class="sd-info-item"><span class="sd-label">{_tip("技术分")}</span><span class="sd-value" style="color:{_color_for_value(qs_tech)}">{qs_tech:.0f}</span></div>
            <div class="sd-info-item"><span class="sd-label">{_tip("基本面分")}</span><span class="sd-value" style="color:{_color_for_value(qs_fund)}">{qs_fund:.0f}</span></div>
            <div class="sd-info-item"><span class="sd-label">{_tip("量能分")}</span><span class="sd-value" style="color:{_color_for_value(qs_vol)}">{qs_vol:.0f}</span></div>
            <div class="sd-info-item"><span class="sd-label">{_tip("风险分")}</span><span class="sd-value" style="color:{_color_for_value(qs_risk_factor, invert=True)}">{qs_risk_factor:.0f}</span></div>
            <div class="sd-info-item"><span class="sd-label">{_tip("舆情分")}</span><span class="sd-value" style="color:{_color_for_value(qs_sentiment)}">{qs_sentiment:.0f}</span></div>
          </div>
        </div>

        {_build_news_section(detail) if detail.get("news_headlines") else ""}

        <div class="sd-section">
          <div class="sd-section-title">短线 / 长线 适宜度分析</div>
          <div class="sd-ts-grid">
            <div class="sd-ts-item">
              <div class="sd-ts-label">
                <span>短线评分</span>
                <span class="sd-ts-score" style="color:{_color_for_value(ts_short_score)}">{ts_short_score:.0f}</span>
              </div>
              <div class="sd-ts-bar"><div class="sd-ts-bar-fill" style="width:{ts_short_score}%;background:{_color_for_value(ts_short_score)}"></div></div>
            </div>
            <div class="sd-ts-item">
              <div class="sd-ts-label">
                <span>长线评分</span>
                <span class="sd-ts-score" style="color:{_color_for_value(ts_long_score)}">{ts_long_score:.0f}</span>
              </div>
              <div class="sd-ts-bar"><div class="sd-ts-bar-fill" style="width:{ts_long_score}%;background:{_color_for_value(ts_long_score)}"></div></div>
            </div>
          </div>
          {'<div class="sd-ts-confidence">判断置信度：' + ts_confidence + "</div>" if ts_confidence else ""}
          {'<div class="sd-ts-basis"><strong>短线依据：</strong>' + ts_short_basis + "</div>" if ts_short_basis else ""}
          {'<div class="sd-ts-basis"><strong>长线依据：</strong>' + ts_long_basis + "</div>" if ts_long_basis else ""}
        </div>

        {_build_operation_advice(detail)}

      </div>
    </div>"""
