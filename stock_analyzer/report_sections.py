"""HTML 报告生成 — 报告章节构建函数

从 report_generators.py 拆分而来，包含市场概述和选股逻辑说明的 HTML 生成函数。
"""

import pandas as pd

from .report_html_utils import (
    _color_for_value,
    _fmt_num,
)

# ══════════════════════════════════════════════════════
# 辅助：生成市场概述文字
# ══════════════════════════════════════════════════════


def _build_market_overview(df: pd.DataFrame, stock_details: dict = None) -> str:
    """根据选股结果和个股详情生成市场概述文字"""
    total = len(df)
    if not total:
        return '<div class="market-overview"><p>暂无数据</p></div>'

    buy_count = sum(
        1
        for _, r in df.iterrows()
        if str(r.get("评级", "")).startswith("Buy") or str(r.get("评级", "")) == "强买入"
    )
    sell_count = sum(
        1
        for _, r in df.iterrows()
        if str(r.get("评级", "")).startswith("Sell") or str(r.get("评级", "")) == "强卖出"
    )
    hold_count = total - buy_count - sell_count

    buy_ratio = buy_count / total * 100
    sell_ratio = sell_count / total * 100

    avg_score = df["综合评分"].mean() if "综合评分" in df.columns else 0
    avg_mom = df["动量分"].mean() if "动量分" in df.columns else 0
    avg_tech = df["技术分"].mean() if "技术分" in df.columns else 0
    avg_fund = df["基本面分"].mean() if "基本面分" in df.columns else 0
    avg_vol = df["量能分"].mean() if "量能分" in df.columns else 0
    avg_risk_score = df["风险分"].mean() if "风险分" in df.columns else 0

    # 市场情绪判断
    if buy_ratio >= 50:
        market_sentiment = "整体市场情绪偏乐观"
        sentiment_detail = f"买入/强买入评级占比 {buy_ratio:.0f}%，市场呈现积极信号"
    elif sell_ratio >= 40:
        market_sentiment = "整体市场情绪偏谨慎"
        sentiment_detail = f"卖出/强卖出评级占比 {sell_ratio:.0f}%，市场存在一定风险"
    else:
        market_sentiment = "市场情绪中性偏分化"
        sentiment_detail = f"买入 {buy_ratio:.0f}% / 持有 {hold_count / total * 100:.0f}% / 卖出 {sell_ratio:.0f}%，建议精选个股"

    # 因子强弱分析
    factor_parts = []
    if avg_mom >= 60:
        factor_parts.append("动量因子表现较强，近期趋势向上")
    elif avg_mom <= 30:
        factor_parts.append("动量因子偏弱，近期整体承压")
    else:
        factor_parts.append("动量因子处于中性区间")

    if avg_fund >= 60:
        factor_parts.append("基本面整体优秀，盈利能力良好")
    elif avg_fund <= 30:
        factor_parts.append("基本面偏弱，需关注盈利能力")

    if avg_risk_score >= 60:
        factor_parts.append("风险控制较好，波动率在可接受范围内")
    elif avg_risk_score <= 30:
        factor_parts.append("风险指标偏高，建议控制仓位")

    factor_text = "；".join(factor_parts)

    # 评分分布
    high_cnt = int((df["综合评分"] >= 60).sum()) if "综合评分" in df.columns else 0
    mid_cnt = (
        int(((df["综合评分"] >= 40) & (df["综合评分"] < 60)).sum())
        if "综合评分" in df.columns
        else 0
    )
    low_cnt = int((df["综合评分"] < 40).sum()) if "综合评分" in df.columns else 0

    # 核心观点
    if buy_ratio >= 50:
        key_class = "positive"
        key_msg = "整体偏乐观"
        key_detail = f"买入/强买入占比{buy_ratio:.0f}%，选股池整体质量较高，市场信心较强。"
    elif sell_ratio >= 40:
        key_class = "negative"
        key_msg = "整体偏谨慎"
        key_detail = f"卖出/强卖出占比{sell_ratio:.0f}%，需注意市场风险，建议控制仓位。"
    else:
        key_class = "neutral"
        key_msg = "中性偏分化"
        key_detail = "建议精选个股，关注评分前列的优质标的。"

    # 最佳/最差因子
    factor_map = [
        ("动量", avg_mom),
        ("技术", avg_tech),
        ("基本面", avg_fund),
        ("量能", avg_vol),
        ("风险", avg_risk_score),
    ]
    best_factor_name = max(factor_map, key=lambda x: x[1])
    worst_factor_name = min(factor_map, key=lambda x: x[1])

    return f"""  <div class="card">
    <div class="card-title">核心观点</div>
    <div class="key-finding {key_class}">
      <span class="kf-label">📊 市场判断：{key_msg}</span>
      {key_detail} 本次扫描{total}只股票，平均综合评分{avg_score:.1f}分。
      入选股票中评分≥60分的优质标的{high_cnt}只，中等{mid_cnt}只，偏低{low_cnt}只。
      五因子中<b>{best_factor_name[0]}</b>表现最强（{best_factor_name[1]:.0f}分），
      <b>{worst_factor_name[0]}</b>相对偏弱（{worst_factor_name[1]:.0f}分）。
    </div>
  </div>
  <div class="market-overview">
    <h3>市场概览</h3>
    <p>本次共扫描 <strong>{total}</strong> 只股票，平均综合评分 <strong>{avg_score:.1f}</strong> 分。
    {market_sentiment}（{sentiment_detail}）。<br>
    五因子均值：动量 {avg_mom:.0f} 分 / 技术 {avg_tech:.0f} 分 / 基本面 {avg_fund:.0f} 分 / 量能 {avg_vol:.0f} 分 / 风险 {avg_risk_score:.0f} 分。<br>
    {factor_text}。</p>
    <div class="glance-grid">
      <div class="glance-item"><div class="glance-value green">{high_cnt}</div><div class="glance-label">优质(≥60分)</div></div>
      <div class="glance-item"><div class="glance-value" style="color:#f9a825">{mid_cnt}</div><div class="glance-label">中等(40-60分)</div></div>
      <div class="glance-item"><div class="glance-value red">{low_cnt}</div><div class="glance-label">偏低(&lt;40分)</div></div>
      <div class="glance-item"><div class="glance-value">{avg_score:.0f}</div><div class="glance-label">平均分</div></div>
      <div class="glance-item"><div class="glance-value green">{buy_count}</div><div class="glance-label">买入/强买入</div></div>
      <div class="glance-item"><div class="glance-value red">{sell_count}</div><div class="glance-label">卖出/强卖出</div></div>
    </div>
  </div>"""


def _build_selection_rationale(
    df: pd.DataFrame, stock_details: dict = None, total_scanned: int = 4405, top_n: int = 5
) -> str:
    """生成板块分析 + 个股选择依据的完整说明，含全市场板块分布、板块对比、落选分析、个股详解"""
    total = len(df)
    if not total:
        return ""

    from stock_analyzer.sectors_fallback import get_sector_for_code

    factor_cols = ["动量分", "技术分", "基本面分", "量能分", "风险分"]
    factor_display = {
        "动量分": "动量",
        "技术分": "技术",
        "基本面分": "基本面",
        "量能分": "量能",
        "风险分": "风险",
    }

    # ── 全市场板块分布（所有扫描的股票） ──
    all_sectors = {}
    for _, row in df.iterrows():
        code = str(row.get("代码", ""))
        score = row.get("综合评分", 0)
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = 0
        detail = stock_details.get(code, {}) if stock_details else {}
        s = detail.get("sector", "")
        if not s or s == "其他":
            s = get_sector_for_code(code)
        is_selected = code in stock_details if stock_details else False
        for sector_name in s.split("、"):
            if sector_name not in all_sectors:
                all_sectors[sector_name] = {"count": 0, "scores": [], "selected": 0}
            all_sectors[sector_name]["count"] += 1
            all_sectors[sector_name]["scores"].append(score)
            if is_selected:
                all_sectors[sector_name]["selected"] += 1

    sorted_sectors = sorted(all_sectors.items(), key=lambda x: -x[1]["count"])
    all_avg = df["综合评分"].mean() if "综合评分" in df.columns else 0

    # ── 全市场板块分布 HTML（水平条形图） ──
    sector_bars = []
    max_count = sorted_sectors[0][1]["count"] if sorted_sectors else 1
    for s_name, s_info in sorted_sectors[:15]:
        avg_s = sum(s_info["scores"]) / len(s_info["scores"]) if s_info["scores"] else 0
        pct = s_info["count"] / max_count * 100
        bar_color = "#1a73e8" if s_info["selected"] > 0 else "#ddd"
        text_color = "#1a73e8" if s_info["selected"] > 0 else "#999"
        sel_tag = (
            f' <span style="color:#2e7d32;font-weight:600;">★选{s_info["selected"]}</span>'
            if s_info["selected"] > 0
            else ""
        )
        sector_bars.append(
            f'<div style="display:flex;align-items:center;margin:3px 0;font-size:12px;">'
            f'<span style="width:100px;text-align:right;padding-right:8px;color:{text_color};">{s_name}</span>'
            f'<div style="flex:1;background:#f0f0f0;border-radius:8px;height:18px;overflow:hidden;">'
            f'<div style="width:{pct:.0f}%;background:{bar_color};height:18px;border-radius:8px;'
            f"display:flex;align-items:center;justify-content:flex-end;"
            f"padding-right:6px;box-sizing:border-box;color:{'#fff' if s_info['selected'] > 0 else '#666'};"
            f'font-size:11px;font-weight:500;">{s_info["count"]}</div></div>'
            f'<span style="width:60px;text-align:left;padding-left:8px;color:{text_color};">{avg_s:.0f}分</span>'
            f"{sel_tag}</div>"
        )
    sector_all_html = "".join(sector_bars)
    if len(sorted_sectors) > 15:
        sector_all_html += f'<div style="font-size:11px;color:#999;text-align:center;margin-top:4px;">...及其他 {len(sorted_sectors) - 15} 个板块</div>'

    # ── 选中股票的板块数据 ──
    selected_sector_data = {}
    for s_name, s_info in sorted_sectors:
        if s_info["selected"] > 0:
            avg_s = sum(s_info["scores"]) / len(s_info["scores"]) if s_info["scores"] else 0
            selected_sector_data[s_name] = {
                "count": s_info["count"],
                "selected": s_info["selected"],
                "avg_score": avg_s,
            }

    sector_ranks = []
    for s_name, s_info in selected_sector_data.items():
        sector_ranks.append((s_name, s_info["avg_score"], {}, s_info["count"]))
    sector_ranks.sort(key=lambda x: -x[1])

    # ── 选中板块标签 ──
    sector_tags = []
    for s_name, avg_s, _, cnt in sector_ranks:
        color = "#1a73e8" if avg_s >= all_avg else "#999"
        sector_tags.append(
            f'<span style="background:#e8edf3;padding:2px 10px;border-radius:12px;'
            f'font-size:12px;white-space:nowrap;display:inline-block;margin:2px 4px;color:{color};">'
            f"{s_name}（{cnt}只，均分{avg_s:.0f}）</span>"
        )
    sector_tags_html = " ".join(sector_tags)

    # ── 逐板块分析文字 ──
    sector_analysis_parts = []
    if sector_ranks:
        names_str = "、".join(
            f"{s}（全池{cnt}只，选中{selected_sector_data[s]['selected']}只）"
            for s, _, _, cnt in sector_ranks[:5]
        )
        sector_analysis_parts.append(
            f"入选的{total}只股票分布于{len(sector_ranks)}个板块：{names_str}。"
        )
        for s_name, avg_s, _, cnt in sector_ranks[:4]:
            sd = selected_sector_data[s_name]
            if avg_s - all_avg > 10:
                score_label = "显著高于"
            elif avg_s >= all_avg:
                score_label = "略高于"
            elif all_avg - avg_s < 10:
                score_label = "略低于"
            else:
                score_label = "显著低于"
            sector_analysis_parts.append(
                f"<strong>{s_name}</strong>板块扫描范围内共{sd['count']}只，"
                f"选中{sd['selected']}只，"
                f"均分{avg_s:.0f}分，{score_label}全部扫描均值（{all_avg:.1f}分）。"
            )
    else:
        sector_analysis_parts.append("入选股票分散于多个板块，未呈现明显板块集中特征。")
    sector_desc = "".join(sector_analysis_parts)

    # ── 板块对比 ──
    sector_comparison_parts = []
    if len(sector_ranks) >= 2:
        best_name = sector_ranks[0][0]
        best_score = sector_ranks[0][1]
        sector_comparison_parts.append(
            f"板块对比来看，<strong>{best_name}</strong>综合评分最高（{best_score:.0f}分）"
        )
        sector_comparison_parts.append("。")
    sector_comparison = "".join(sector_comparison_parts)

    # ── 落选板块分析 ──
    exclusion_parts = []
    if sorted_sectors and total_scanned > total:
        weak_sectors = []
        for s, info in sorted_sectors:
            if info["selected"] == 0 and info["scores"]:
                avg_s = sum(info["scores"]) / len(info["scores"])
                if avg_s < 50:
                    weak_sectors.append(s)
        if weak_sectors:
            exclusion_parts.append(
                f"在全部{len(sorted_sectors)}个板块中，部分板块无个股入选且均分偏低，如、".join(
                    weak_sectors[:3]
                )
                + "等，说明这些板块整体评分较低，"
                "暂未达到选股标准。"
            )
        high_cnt = sum(
            1
            for s, info in sorted_sectors
            if info["selected"] > 0
            and info["scores"]
            and (sum(info["scores"]) / len(info["scores"]) >= 65)
        )
        if high_cnt >= 2:
            exclusion_parts.append(
                f"整体来看，选股结果集中在评分较高的{high_cnt}个板块中，市场呈现结构性分化特征。"
            )
    exclusion_desc = "".join(exclusion_parts)

    # ── 评分模型 ──
    model_factors = [
        ("动量", "25%", "衡量股价近期上涨或下跌的力度", "#1a73e8"),
        ("技术", "25%", "综合MACD、RSI、KDJ等技术指标判断买卖信号", "#e65100"),
        ("基本面", "20%", "基于ROE、营收增长、毛利率等财务数据分析公司质地", "#2e7d32"),
        ("量能", "15%", "观察成交量变化和量价配合度，判断资金参与热情", "#6a1b9a"),
        ("风险", "15%", "评估波动率和回撤幅度，得分越高说明风险控制越好", "#f9a825"),
    ]
    model_html = '<div class="model-factor-grid">'
    for f_name, f_weight, f_desc, f_color in model_factors:
        model_html += f"""
        <div class="model-factor" style="border-top-color:{f_color}">
          <div class="mf-header">
            <span class="mf-name">{f_name}</span>
            <span class="mf-weight">{f_weight}</span>
          </div>
          <div class="mf-desc">{f_desc}</div>
          <div class="mf-bar"><div class="mf-bar-fill" style="width:{f_weight};background:{f_color}"></div></div>
        </div>"""
    model_html += "</div>"

    # ── 入选股票因子解读 ──
    top_scores = df["综合评分"].head(top_n) if "综合评分" in df.columns else pd.Series()
    top_avg = top_scores.mean() if len(top_scores) else 0
    avg_diff = top_avg - all_avg

    factor_strengths = []
    key_factor_config = [
        ("动量分", "短期动量", 60),
        ("技术分", "技术指标", 60),
        ("基本面分", "基本面", 60),
        ("量能分", "量能活跃度", 60),
        ("风险分", "风险控制", 60),
    ]
    for col, label, threshold in key_factor_config:
        if col in df.columns:
            top_val = df[col].head(top_n).mean()
            if top_val >= threshold:
                factor_strengths.append(f"{label}({top_val:.0f}分)")

    pool_avg_factors = {}
    for c in factor_cols:
        if c in df.columns:
            pool_avg_factors[c] = df[c].mean()

    # ── 个股详细解析 ──
    factor_names_cn = {
        "momentum": "动量",
        "technical": "技术",
        "fundamental": "基本面",
        "volume": "量能",
        "risk": "风险",
    }
    detail_sections = []
    stock_highlights = []
    for idx, (_, row) in enumerate(df.head(top_n).iterrows()):
        code = str(row.get("代码", ""))
        name = str(row.get("名称", code))
        score = row.get("综合评分", 0)
        rating = str(row.get("评级", ""))
        detail = stock_details.get(code, {}) if stock_details else {}
        sector = detail.get("sector", "")
        ts = detail.get("trading_style", {})
        style = ts.get("style", "")
        confidence = ts.get("style_confidence", "")

        sector_total_count = all_sectors.get(sector, {}).get("count", 0) if sector else 0
        sector_selected_count = all_sectors.get(sector, {}).get("selected", 0) if sector else 0

        qs = detail.get("quant_score", {})
        factor_scores = qs.get("factor_scores", {})
        factor_items = [(k, v.get("score", 0)) for k, v in factor_scores.items()]
        factor_items.sort(key=lambda x: -x[1])
        best_factor_k = factor_items[0][0] if factor_items else ""
        best_factor_v = factor_items[0][1] if factor_items else 0
        worst_factor_k = factor_items[-1][0] if factor_items else ""
        worst_factor_v = factor_items[-1][1] if factor_items else 0
        best_cn = factor_names_cn.get(best_factor_k, "")
        worst_cn = factor_names_cn.get(worst_factor_k, "")

        sector_avg = all_avg
        for s_name, info in selected_sector_data.items():
            if s_name in sector:
                sector_avg = info["avg_score"]
                break

        style_tag = f"，交易风格偏{style}" if style else ""
        sector_info = (
            f"该板块扫描范围内共{sector_total_count}只，此次选中{sector_selected_count}只"
            if sector_total_count > 0
            else ""
        )

        detail_html = (
            f'<div style="margin-bottom:10px;padding:10px;background:#f8f9fb;border-radius:8px;">'
            f'<div style="font-weight:600;font-size:14px;color:#333;">{idx + 1}. {name}（{sector}）</div>'
            f'<div style="font-size:12px;color:#555;line-height:1.9;margin-top:4px;">'
        )
        if sector_info:
            detail_html += f'<span style="color:#888;">{sector_info}。</span><br>'
        detail_html += (
            f"综合评分 <strong>{score}</strong> 分，"
            f"评级 <strong>{rating}</strong>"
            f"（{'高于' if score > all_avg else '低于'}"
            f"扫描均值{abs(score - all_avg):.1f}分"
            f"，{'高于' if score > sector_avg else '低于'}"
            f"所在板块均值{abs(score - sector_avg):.1f}分"
            f"{style_tag}）。"
            f"最强因子为<strong>{best_cn}</strong>（{best_factor_v:.0f}分）"
        )
        if worst_factor_k and worst_factor_v < 60:
            detail_html += f"，最弱因子为{worst_cn}（{worst_factor_v:.0f}分）"
        detail_html += "。"

        over_avg_parts = []
        fcol_map = {
            "momentum": "动量分",
            "technical": "技术分",
            "fundamental": "基本面分",
            "volume": "量能分",
            "risk": "风险分",
        }
        for k, v in factor_items:
            cn = factor_names_cn.get(k, "")
            pool_v = pool_avg_factors.get(fcol_map.get(k, ""), 0)
            if v >= pool_v + 10:
                over_avg_parts.append(f"{cn}{v:.0f}分（+{v - pool_v:.0f} vs 均值）")
            elif v >= pool_v:
                over_avg_parts.append(f"{cn}{v:.0f}分")
        if over_avg_parts:
            detail_html += "相对于扫描池，该股在、".join(over_avg_parts) + "方面具有优势。"

        tech = detail.get("technical_summary", {})
        funda = detail.get("fundamentals", {})
        ma_trend = tech.get("ma_trend", "")
        if ma_trend:
            trend_desc = {
                "bullish_all": "均线多头排列",
                "bullish": "短期均线偏多",
                "mixed": "均线方向不一",
                "bearish": "均线偏弱",
                "bearish_all": "均线全面空头",
            }
            detail_html += f"技术面{trend_desc.get(ma_trend, '')}。"
        roe = funda.get("roe", None)
        if roe is not None:
            try:
                roe_v = float(roe) * 100 if roe < 1 else float(roe)
                detail_html += f"基本面ROE为{roe_v:.1f}%。"
            except (TypeError, ValueError):
                pass
        detail_html += "</div></div>"
        detail_sections.append(detail_html)

        style_tag2 = f"，适合{style}" if style else ""
        conf_extra = f"，{confidence}置信度" if confidence else ""
        best_name = factor_names_cn.get(best_factor_k, "")
        best_extra = (
            f"，{best_name}因子最强（{best_factor_v:.0f}分）" if best_factor_v >= 60 else ""
        )
        stock_highlights.append(
            f"<strong>{name}（{sector}）</strong>：综合评分 {score} 分 → {rating}"
            f"{best_extra}{style_tag2}{conf_extra}"
        )

    # ── 组合成文 ──
    parts = [
        '  <div class="card">',
        '    <div class="card-title">选股逻辑说明</div>',
        '    <div class="card-subtitle">从板块分布到个股选择的完整逻辑</div>',
        # 一、全市场板块分布
        '    <div class="sd-section-title">一、全市场板块分布</div>',
        f'    <p style="font-size:13px;color:#555;line-height:1.8;margin-bottom:8px;">'
        f"本次共扫描 <strong>{total}</strong> 只股票，"
        f"覆盖 <strong>{len(sorted_sectors)}</strong> 个板块。"
        f"下表展示各个板块的数量分布和平均评分"
        f'（<span style="color:#1a73e8;font-weight:600;">蓝色</span>'
        f"标记为有个股入选的板块）：</p>",
        f'    <div style="margin:8px 0 12px 0;">{sector_all_html}</div>',
        # 二、板块选择分析
        '    <div class="sd-section-title" style="margin-top:14px;">二、板块选择分析</div>',
        f'    <p style="font-size:13px;color:#333;line-height:1.9;margin-bottom:6px;">{sector_desc}</p>',
        f'    <div style="margin:6px 0 10px 0;">{sector_tags_html}</div>',
        f'    <p style="font-size:13px;color:#555;line-height:1.8;margin-bottom:6px;">{sector_comparison}</p>',
        f'    <p style="font-size:13px;color:#888;line-height:1.8;margin-bottom:0;">{exclusion_desc}</p>',
        # 三、多因子评分模型
        '    <div class="sd-section-title" style="margin-top:14px;">三、多因子评分模型说明</div>',
        f'    <p style="font-size:13px;color:#555;line-height:1.8;margin-bottom:8px;">'
        f"本系统通过五个维度对每只股票进行综合评分，"
        f"最终选出评分最高的 <strong>{total}</strong> 只。"
        f"各维度的权重和含义如下："
        f"</p>",
        f"    {model_html}",
        f'    <p style="font-size:13px;color:#555;line-height:1.8;margin-top:8px;">'
        f"入选股票平均分 {top_avg:.1f}，"
        f"{'高于' if avg_diff >= 0 else '低于'}"
        f"全部扫描股票均值 {abs(avg_diff):.1f} 分。"
        f"{'在' + '、'.join(factor_strengths) + '方面表现尤其突出。' if factor_strengths else ''}"
        f"</p>",
        # 四、个股详细解析
        '    <div class="sd-section-title" style="margin-top:14px;">四、个股详细解析</div>',
        '    <p style="font-size:13px;color:#555;line-height:1.8;margin-bottom:8px;">'
        "以下逐一分析每只入选个股的评分结构、"
        "因子优势和综合特征：</p>",
    ]
    parts.extend(detail_sections)

    # 五、重点个股一览
    parts.append(
        '    <div class="sd-section-title" style="margin-top:14px;">五、重点个股一览</div>'
    )
    parts.append('    <div class="sd-ts-basis">' + "<br>".join(stock_highlights) + "</div>")
    parts.append("  </div>")

    return "\n".join(parts)
