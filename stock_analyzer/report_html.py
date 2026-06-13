"""HTML 报告生成模块

通过 Chart.js CDN 生成交互式 HTML 报告，无其他依赖。
三个核心函数:
    generate_screener_report()   — 选股结果报告（含个股分析详情）
    generate_portfolio_report()  — 投资组合报告（含个股分析详情）
    generate_full_chain_report() — 全链路一键报告
"""

import json
import os
from datetime import datetime
from typing import Any

import pandas as pd

# ── 输出目录 ─────────────────────────────────────────
from .config import REPORT_DIR as _CFG_REPORT_DIR

REPORT_DIR = _CFG_REPORT_DIR


def _ensure_report_dir() -> None:
    os.makedirs(REPORT_DIR, exist_ok=True)


def _default_path(prefix: str) -> str:
    """生成默认输出路径: reports/{prefix}_YYYYMMDD_HHMM.html"""
    _ensure_report_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    return os.path.join(REPORT_DIR, f"{prefix}_{ts}.html")


def _escape_html(val) -> str:
    if val is None:
        return ""
    return str(val)


def _rating_color(rating: str) -> str:
    mapping = {
        "Strong Buy": "#2e7d32",
        "强买入": "#2e7d32",
        "Buy": "#66bb6a",
        "买入": "#66bb6a",
        "Hold": "#f9a825",
        "持有": "#f9a825",
        "Sell": "#ef6c00",
        "卖出": "#ef6c00",
        "Strong Sell": "#c62828",
        "强卖出": "#c62828",
    }
    return mapping.get(str(rating).strip(), "#666666")


def _rating_bg_color(rating: str) -> str:
    mapping = {
        "Strong Buy": "#e8f5e9",
        "强买入": "#e8f5e9",
        "Buy": "#f1f8e9",
        "买入": "#f1f8e9",
        "Hold": "#fff8e1",
        "持有": "#fff8e1",
        "Sell": "#fff3e0",
        "卖出": "#fff3e0",
        "Strong Sell": "#ffebee",
        "强卖出": "#ffebee",
    }
    return mapping.get(str(rating).strip(), "#f5f5f5")


def _change_color(val) -> str:
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "#666666"
    if v > 0:
        return "#d32f2f"
    if v < 0:
        return "#2e7d32"
    return "#666666"


def _change_sign(val) -> str:
    try:
        v = float(val)
    except (TypeError, ValueError):
        return str(val)
    if v > 0:
        return f"+{v}"
    return str(v)


def _color_for_value(val: float, invert: bool = False) -> str:
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "#666666"
    if v >= 80:
        return "#2e7d32" if not invert else "#c62828"
    if v >= 60:
        return "#66bb6a" if not invert else "#ef6c00"
    if v >= 40:
        return "#f9a825"
    if v >= 20:
        return "#ef6c00" if not invert else "#66bb6a"
    return "#c62828" if not invert else "#2e7d32"


def _fmt_num(v, prefix="", suffix=""):
    try:
        return f"{prefix}{float(v):,.2f}{suffix}"
    except (TypeError, ValueError):
        return "-"


# ── 术语解释与提示 ──────────────────────────────

TERM_DEFS = {
    "MACD": "异同移动平均线，趋势跟踪指标。DIF上穿DEA为金叉(看涨)，下穿为死叉(看跌)。柱状图反映多空力量对比。",
    "RSI": "相对强弱指标，0-100。>70超买区域，可能回调；<30超卖区域，可能反弹。50为强弱分界线。",
    "KDJ": "随机指标，K线为快速确认线，D线为慢速主干线。K上穿D为金叉，下穿为死叉。",
    "均线": "移动平均线，反映一定周期内的平均持仓成本。常用MA5/MA10/MA20/MA60，多头排列指短期均线在长期之上。",
    "夏普比率": "衡量风险调整后收益。(收益率-无风险利率)/波动率。>1良好，>2优秀，<0表示收益未能覆盖风险。",
    "最大回撤": "历史最高点到最低点的最大跌幅，衡量策略的抗风险能力。回撤越小说明风控越好。",
    "VaR": "在险价值(Value at Risk)，95%置信度下最大可能损失。如VaR=-2%表示有95%的把握单日损失不超过2%。",
    "ATR": "平均真实波幅(Average True Range)，衡量股价波动幅度。ATR越大说明波动越剧烈，风险越高。",
    "支撑位": "股价下跌时可能获得买盘支撑的价格位，是技术分析中的重要参考价位。",
    "压力位": "股价上涨时可能遭遇卖盘压制的价格位，突破压力位通常被视为强势信号。",
    "动量分": "基于短期(5日/20日/60日)涨跌幅计算的动量强度评分，得分越高说明近期上涨势头越强。",
    "技术分": "综合MACD、RSI、KDJ、均线排列等技术指标的计算得分，反映技术面整体状态。",
    "基本面分": "基于ROE、营收增长、净利润增长、毛利率等财务指标的综合评分。",
    "量能分": "基于成交量变化、量价配合度计算的评分，反映资金参与活跃程度。",
    "风险分": "基于ATR占比、回撤幅度计算的评分，得分越高说明风险控制越好、波动越温和。",
    "舆情分": "基于个股新闻和微博舆情数据计算的市场情绪评分。>60正面舆情，<40负面舆情，50为中性。反映市场对个股的关注度和情绪倾向。",
    "金叉": "快线向上穿越慢线的技术形态，通常视为买入或看涨信号。如MACD金叉、KDJ金叉等。",
    "死叉": "快线向下穿越慢线的技术形态，通常视为卖出或看跌信号。如MACD死叉、KDJ死叉等。",
    "多头排列": "短期均线>中期均线>长期均线，且股价在所有均线之上，是典型的上升趋势特征。",
    "空头排列": "短期均线<中期均线<长期均线，且股价在所有均线之下，是典型的下降趋势特征。",
    "量价配合": "成交量和价格变化的协同关系。量升价涨为健康上涨，量缩价涨或量升价跌为背离信号。",
    "止损": "预先设定的卖出价位，当股价跌破该价位时卖出以控制亏损幅度，是风险管理的基本手段。",
    "止盈": "预先设定的卖出价位，当股价涨到该价位时卖出以锁定利润。",
    "年化收益率": "将投资收益换算为一年的收益率，便于不同期限的投资业绩比较。基于252个交易日计算。",
    "布林带": "由中轨(20日均线)、上轨(中轨+2倍标准差)和下轨(中轨-2倍标准差)组成，股价触及上下轨时可能出现反转。",
    "ADX": "平均趋向指数(Average Directional Index)，衡量趋势强度。ADX>25表示趋势确立，<20表示震荡市场。",
    "仓位管理": "根据风险承受能力和市场情况，合理分配每只股票的资金占比，是控制整体投资风险的重要手段。",
    "CVaR": "条件在险价值(Conditional VaR)，衡量超过VaR的极端损失的平均值，比VaR更全面地反映尾部风险。",
    "Calmar比率": "年化收益率与最大回撤的比值，衡量策略在极端情况下的表现。比率越高说明回撤控制越好。",
    "索提诺比率": "夏普比率的改进版，仅用下行波动率计算，更准确地衡量下行风险调整后收益。",
}


def _tip(label: str, term_key: str = None) -> str:
    """生成带悬停解释的术语标签 HTML"""
    key = term_key or label
    defn = TERM_DEFS.get(key)
    if defn:
        esc_defn = (
            defn.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
        return f'<span class="term-t">{label}<span class="term-t-popup">{esc_defn}</span></span>'
    return label


def _score_rank(score, ranges=None):
    """将数值映射为优良中差等级及说明文字"""
    if ranges:
        for threshold, rank, desc in ranges:
            if score >= threshold:
                return rank, desc
        return "很差", "远低于参考标准"
    # 默认评分标准（因子评分/综合评分）
    if score >= 80:
        return "优秀", "≥80分，表现突出"
    if score >= 60:
        return "良好", "60-79分，处于中等偏上水平"
    if score >= 40:
        return "一般", "40-59分，处于中等水平，有提升空间"
    if score >= 20:
        return "较差", "20-39分，相对偏弱，需关注"
    return "很差", "<20分，表现不佳，需警惕"


# ── 叙述文字生成函数 ──────────────────────────────


def _build_fundamental_narrative(detail: dict) -> str:
    """根据基本面数据生成中文叙述文字"""
    qs = detail.get("quant_score", {})
    fs = qs.get("factor_scores", {})
    fund_factor = fs.get("fundamental", {})
    fund_score = fund_factor.get("score")
    fund_details = fund_factor.get("details", {})

    parts = ['<div class="narrative-block">']
    parts.append('<div class="n-subtitle">基本面分析</div>')

    funda = detail.get("fundamentals")
    has_funda = funda and isinstance(funda, dict) and funda.get("ROE") is not None

    if has_funda:
        roe = funda.get("ROE", 0)
        if isinstance(roe, (int, float)):
            rev_growth = funda.get("营收增长", 0)
            net_growth = funda.get("净利润增长", 0)
            gross_margin = funda.get("毛利率", 0)
            net_margin = funda.get("净利率", 0)

            # ROE解读
            if roe > 15:
                roe_text = "优秀"
                roe_comment = "属于盈利能力很强的企业"
            elif roe > 8:
                roe_text = "良好"
                roe_comment = "盈利能力处于中等偏上水平"
            elif roe > 5:
                roe_text = "一般"
                roe_comment = "盈利能力处于中等水平"
            else:
                roe_text = "偏低"
                roe_comment = "盈利能力有待提升"

            sentences = [
                f"该股ROE（净资产收益率）为{roe:.1f}%，处于{roe_text}水平，{roe_comment}。"
                f"（A股参考：ROE>15%优秀，8-15%良好，5-8%一般，<5%偏低）"
            ]

            if isinstance(rev_growth, (int, float)):
                rev_pct = rev_growth * 100 if rev_growth < 1 else rev_growth
                if rev_pct > 30:
                    sentences.append(
                        f"营收增长{rev_pct:.1f}%，增速非常快，公司处于高速扩张期。（A股参考：营收增长>20%为较快，5-20%为稳定增长，<5%为增长乏力）"
                    )
                elif rev_pct > 20:
                    sentences.append(f"营收增长{rev_pct:.1f}%，增速较快，公司处于快速扩张阶段。")
                elif rev_pct > 5:
                    sentences.append(f"营收增长{rev_pct:.1f}%，业务保持稳定增长。")
                elif rev_pct > 0:
                    sentences.append(f"营收微增{rev_pct:.1f}%，增长动力偏弱。")
                else:
                    sentences.append(f"营收同比下降{abs(rev_pct):.1f}%，需关注业务下滑风险。")

            if isinstance(gross_margin, (int, float)):
                gm_pct = gross_margin * 100 if gross_margin < 1 else gross_margin
                if gm_pct > 70:
                    sentences.append(
                        f"毛利率{gm_pct:.1f}%，处于极高水平，产品或服务具有很强定价权和护城河。"
                    )
                elif gm_pct > 60:
                    sentences.append(
                        f"毛利率{gm_pct:.1f}%，处于较高水平，产品或服务具有较强定价权。（A股参考：毛利率>60%优秀，30-60%中等，<30%偏低）"
                    )
                elif gm_pct > 30:
                    sentences.append(f"毛利率{gm_pct:.1f}%，处于中等水平，盈利能力尚可。")
                else:
                    sentences.append(f"毛利率{gm_pct:.1f}%，相对偏低，产品或服务竞争较为激烈。")

            if isinstance(net_margin, (int, float)):
                nm_pct = net_margin * 100 if net_margin < 1 else net_margin
                if nm_pct > 20:
                    sentences.append(f"净利率{nm_pct:.1f}%，盈利质量很高，成本控制能力优秀。")
                elif nm_pct > 15:
                    sentences.append(f"净利率{nm_pct:.1f}%，盈利质量较高。")
                elif nm_pct > 5:
                    sentences.append(f"净利率{nm_pct:.1f}%，盈利质量处于中等水平。")

            if isinstance(net_growth, (int, float)):
                ng_pct = net_growth * 100 if net_growth < 1 else net_growth
                if ng_pct > 50:
                    sentences.append(f"净利润增长{ng_pct:.1f}%，爆发式增长，盈利能力大幅提升。")
                elif ng_pct > 30:
                    sentences.append(f"净利润增长{ng_pct:.1f}%，增长势头强劲。")

            parts.extend(f"<p>{s}</p>" for s in sentences)
    elif fund_score is not None:
        if fund_score >= 60:
            parts.append(
                f"<p>该股基本面评分为{fund_score:.0f}分，整体质地较好，财务健康度较高。</p>"
            )
        elif fund_score >= 40:
            parts.append(
                f"<p>该股基本面评分为{fund_score:.0f}分，处于中等水平，部分财务指标表现一般。</p>"
            )
        else:
            parts.append(
                f"<p>该股基本面评分为{fund_score:.0f}分，相对偏低，需关注公司经营状况的变化。</p>"
            )
    else:
        parts.append("<p>基本面数据暂缺，无法进行详细分析。</p>")

    parts.append("</div>")
    return "\n".join(parts)


def _build_technical_narrative(detail: dict) -> str:
    """根据技术指标数据生成中文叙述文字"""
    tech = detail.get("technical_summary", {})
    changes = detail.get("changes", {})

    parts = ['<div class="narrative-block">']
    parts.append('<div class="n-subtitle">技术面分析</div>')

    has_tech = bool(tech and isinstance(tech, dict))

    if has_tech:
        # MACD
        macd = tech.get("macd_signal", "")
        if macd in ("多头", "金叉"):
            if macd == "金叉":
                parts.append(
                    "<p><strong>MACD指标</strong>刚刚形成金叉信号（DIF线上穿DEA线），是趋势由弱转强的技术标志，短期看涨信号较强。"
                )
            else:
                parts.append(
                    "<p><strong>MACD指标</strong>处于多头区域，DIF线位于DEA线上方，表明短期内上涨动能占优，多头力量较强。"
                )
        elif macd in ("空头", "死叉"):
            if macd == "死叉":
                parts.append(
                    "<p><strong>MACD指标</strong>出现死叉信号（DIF线下穿DEA线），是趋势转弱的技术信号，短期需警惕进一步下行风险。"
                )
            else:
                parts.append(
                    "<p><strong>MACD指标</strong>处于空头区域，DIF线位于DEA线下方，短期趋势偏弱，空方力量占优。"
                )
        else:
            parts.append(
                "<p><strong>MACD指标</strong>处于多空交界状态，趋势方向尚不明确，需等待进一步确认。"
            )

        # RSI
        rsi_val = tech.get("rsi_value")
        rsi_sig = tech.get("rsi_signal", "")
        if rsi_val is not None:
            try:
                rv = float(rsi_val)
                if rv >= 80:
                    parts.append(
                        f"<p><strong>RSI指标</strong>为{rv:.0f}，处于严重超买区域（>80），说明近期涨幅较大，短期存在技术性回调压力，不宜追高。"
                    )
                elif rv > 70:
                    parts.append(
                        f"<p><strong>RSI指标</strong>为{rv:.0f}，处于超买区域（>70），短期可能存在回调需求，建议关注高位风险。"
                    )
                elif rv <= 20:
                    parts.append(
                        f"<p><strong>RSI指标</strong>为{rv:.0f}，处于严重超卖区域（<20），说明近期跌幅较大，可能存在超跌反弹机会。"
                    )
                elif rv < 30:
                    parts.append(
                        f"<p><strong>RSI指标</strong>为{rv:.0f}，处于超卖区域（<30），短期可能存在技术性反弹机会，可逢低关注。"
                    )
                else:
                    parts.append(
                        f"<p><strong>RSI指标</strong>为{rv:.0f}，处于中性区间（30-70），多空力量相对均衡，价格走势平稳。"
                    )
            except (TypeError, ValueError):
                parts.append("<p><strong>RSI指标</strong>数据异常，无法判断当前状态。")

        # KDJ
        kdj = tech.get("kdj_signal", "")
        if kdj == "金叉":
            parts.append(
                "<p><strong>KDJ指标</strong>出现金叉信号（K线上穿D线），是短期技术性买入信号，表明短期动能正在积聚。"
            )
        elif kdj == "死叉":
            parts.append(
                "<p><strong>KDJ指标</strong>出现死叉信号（K线下穿D线），是短期技术性卖出信号，预示短期调整或将开始。"
            )
        elif kdj == "超买":
            parts.append(
                "<p><strong>KDJ指标</strong>处于超买区域，K值和D值均偏高，短期存在回调需求。"
            )
        elif kdj == "超卖":
            parts.append(
                "<p><strong>KDJ指标</strong>处于超卖区域，K值和D值均偏低，短期可能存在反弹机会。"
            )

        # 均线排列
        ma_status = tech.get("ma_status", {})
        if ma_status:
            above = sum(1 for v in ma_status.values() if v.get("股价位置") == "上方")
            total_ma = len(ma_status)
            ma_keys = sorted(ma_status.keys())
            if above == total_ma:
                parts.append(
                    f"<p><strong>均线系统</strong>呈多头排列，股价位于全部主要均线（{'/'.join(ma_keys)}）之上，属于强势上涨格局，中期趋势向好。"
                )
            elif above >= total_ma / 2:
                up_list = [k for k, v in ma_status.items() if v.get("股价位置") == "上方"]
                down_list = [k for k, v in ma_status.items() if v.get("股价位置") != "上方"]
                parts.append(
                    f"<p>股价位于{','.join(up_list)}之上，但受到{','.join(down_list)}的压制，短期走势尚可但中期压力仍在。"
                )
            elif above > 0:
                up_list = [k for k, v in ma_status.items() if v.get("股价位置") == "上方"]
                down_list = [k for k, v in ma_status.items() if v.get("股价位置") != "上方"]
                parts.append(
                    f"<p>仅{','.join(up_list)}在股价之下，而{'、'.join(down_list)}均构成压力，整体趋势偏弱，需等待均线系统修复。"
                )
            else:
                parts.append(
                    "<p>股价位于全部主要均线之下，均线系统呈空头排列，整体处于弱势格局，建议等待企稳信号。"
                )

        # 近期涨跌幅
        ret5 = tech.get("近5日涨跌幅")
        ret20 = tech.get("近20日涨跌幅")
        if ret5 is not None and ret20 is not None:
            try:
                r5, r20 = float(ret5), float(ret20)
                if r5 > 5 and r20 > 10:
                    parts.append(
                        f"<p>近期表现强势，近5日上涨{r5:.1f}%，近20日上涨{r20:.1f}%，短中期均呈现上涨趋势，动量充足。"
                    )
                elif r5 < -5 and r20 < -10:
                    parts.append(
                        f"<p>近期表现承压，近5日下跌{abs(r5):.1f}%，近20日下跌{abs(r20):.1f}%，短中期趋势偏弱。"
                    )
                elif r20 > 5:
                    parts.append(f"<p>近期走势温和向上，近20日上涨{r20:.1f}%，中期趋势逐步改善。")
                elif r20 < -5:
                    parts.append(f"<p>中期趋势偏弱，近20日下跌{abs(r20):.1f}%，建议等待走势企稳。")
                else:
                    parts.append(
                        f"<p>近5日涨跌{r5:.1f}%，近20日涨跌{r20:.1f}%，走势相对平稳，无明显趋势性信号。"
                    )
            except (TypeError, ValueError):
                pass
    else:
        parts.append("<p>技术数据暂缺，无法进行技术面分析。</p>")

    parts.append("</div>")
    return "\n".join(parts)


def _build_risk_narrative(detail: dict) -> str:
    """根据风险指标数据生成中文叙述文字"""
    risk = detail.get("risk_metrics", {})
    stop = detail.get("stop_levels", {})

    parts = ['<div class="narrative-block">']
    parts.append('<div class="n-subtitle">风险评估</div>')

    has_risk = bool(risk and isinstance(risk, dict) and risk.get("sharpe_ratio") is not None)

    if has_risk:
        # 夏普比率
        sharpe = risk.get("sharpe_ratio")
        if sharpe is not None:
            try:
                s = float(sharpe)
                if s > 1:
                    parts.append(
                        f"<p><strong>风险调整后收益</strong>表现优秀。夏普比率为{s:.2f}（>1），每承担一单位风险获得了较高的超额回报，风险收益性价比较好。（A股参考：夏普比率>1优秀，0.5-1良好，0-0.5一般，<0需谨慎）"
                    )
                elif s > 0.5:
                    parts.append(
                        f"<p><strong>风险调整后收益</strong>处于中等偏上水平。夏普比率为{s:.2f}，收益基本能够覆盖风险，性价比较好。"
                    )
                elif s > 0:
                    parts.append(
                        f"<p><strong>风险调整后收益</strong>一般。夏普比率为{s:.2f}（>0），虽为正数但偏低，承担的风险未能充分转化为回报。"
                    )
                else:
                    parts.append(
                        f"<p><strong>风险调整后收益</strong>为负。夏普比率为{s:.2f}（<0），收益未能覆盖所承担的风险，当前风险收益特征不太理想。"
                    )
            except (TypeError, ValueError):
                pass

        # 最大回撤
        max_dd = risk.get("max_drawdown_pct")
        if max_dd is not None:
            try:
                dd = abs(float(max_dd))
                if dd < 10:
                    parts.append(
                        f"<p><strong>下行风险</strong>控制较好。历史最大回撤仅{dd:.1f}%，即使在极端行情下跌幅也相对有限，风险可控。（A股参考：最大回撤<10%优秀，10-20%良好，20-30%中等，>30%较大）"
                    )
                elif dd < 20:
                    parts.append(
                        f"<p><strong>下行风险</strong>控制尚可。历史最大回撤{dd:.1f}%，属于A股中较好水平，整体风险可控。"
                    )
                elif dd < 25:
                    parts.append(
                        f"<p><strong>下行风险</strong>处于中等水平。历史最大回撤{dd:.1f}%，属于A股正常波动范围，投资者仍需关注仓位管理。"
                    )
                elif dd < 35:
                    parts.append(
                        f"<p><strong>下行风险</strong>偏高。历史最大回撤{dd:.1f}%，该股历史上曾经历过较大幅度下跌，需注意极端行情风险。"
                    )
                else:
                    parts.append(
                        f"<p><strong>下行风险</strong>较大。历史最大回撤{dd:.1f}%，属于高波动品种，更适合风险承受能力较强的投资者。"
                    )
            except (TypeError, ValueError):
                pass

        # VaR
        var_val = risk.get("VaR_95_pct")
        if var_val is not None:
            try:
                var_abs = abs(float(var_val))
                if var_abs < 1.5:
                    parts.append(
                        f"<p><strong>尾部风险</strong>较低。在95%置信水平下，单日最大可能亏损不超过{var_abs:.1f}%，极端风险可控。（A股参考：VaR<2%较低，2-4%适中，>4%较高）"
                    )
                elif var_abs < 2:
                    parts.append(
                        f"<p><strong>尾部风险</strong>较低。在95%置信水平下，单日最大可能亏损不超过{var_abs:.1f}%，极端风险可控。"
                    )
                elif var_abs < 4:
                    parts.append(
                        f"<p><strong>尾部风险</strong>适中。单日VaR约{var_abs:.1f}%，极端行情下的潜在损失在可接受范围内。"
                    )
                else:
                    parts.append(
                        f"<p><strong>尾部风险</strong>较高。单日VaR达到{var_abs:.1f}%，极端行情下波动剧烈，需严格控制仓位。"
                    )
            except (TypeError, ValueError):
                pass

        # 波动率
        vol = risk.get("annualized_volatility_pct")
        if vol is not None:
            try:
                v = float(vol)
                if v < 20:
                    parts.append(
                        f"<p><strong>波动特征</strong>偏稳健。年化波动率{v:.1f}%，股价波动幅度较小，走势相对平稳。"
                    )
                elif v < 35:
                    parts.append(
                        f"<p><strong>波动特征</strong>中等。年化波动率{v:.1f}%，股价呈现正常波动。"
                    )
                else:
                    parts.append(
                        f"<p><strong>波动特征</strong>偏剧烈。年化波动率{v:.1f}%，价格波动频繁，交易时需注意仓位管理。"
                    )
            except (TypeError, ValueError):
                pass

        # 止损止盈参考
        sl = stop.get("止损参考价") if stop else None
        tp = stop.get("止盈参考价") if stop else None
        if sl and tp and isinstance(sl, (int, float)):
            sl_pct = stop.get("止损幅度%", "")
            tp_pct = stop.get("止盈幅度%", "")
            parts.append(
                f"<p><strong>交易区间参考</strong>：建议在{sl}设置止损（约{sl_pct}%），止盈目标参考{tp}（约{tp_pct}%），这是基于ATR波动率和支撑压力位计算的风险管理参考。"
            )
    else:
        parts.append("<p>风险数据暂缺，无法提供详细风险评估。</p>")

    parts.append("</div>")
    return "\n".join(parts)


def _build_trading_suggestion(detail: dict) -> str:
    """根据交易风格和信号生成操作建议"""
    ts = detail.get("trading_style", {})
    signals = detail.get("signals", {})
    stop = detail.get("stop_levels", {})

    parts = ['<div class="narrative-block">']
    parts.append('<div class="n-subtitle">操作建议</div>')

    style = ts.get("style", "")
    confidence = ts.get("style_confidence", "")
    short_score = ts.get("short_term_score", 0)
    long_score = ts.get("long_term_score", 0)

    style_map = {
        "短线": (
            "短线交易为主",
            "该股短线信号较为明确，适合波段操作。建议密切关注量价变化，严格执行止损纪律。",
        ),
        "长线": (
            "长线持有为主",
            "该股基本面扎实，适合中长期持有。不必过于在意短期价格波动，建议以基本面变化作为持有依据。",
        ),
        "短线+长线": (
            "同时适合短线交易和长线持有",
            "这类标的是较为理想的操作对象，短线可博取波段收益，长线可享受价值增长，兼具进攻和防守特性。",
        ),
        "观望": (
            "暂时观望",
            "当前市场信号不够明朗，不确定性较高，建议等待更清晰的趋势信号后再做决策。",
        ),
    }

    if style in style_map:
        style_name, style_desc = style_map[style]
        conf_text = f"（置信度：{confidence}）" if confidence else ""
        parts.append(
            f"<p>根据量化模型评估，该股<strong>更适合{style_name}</strong>{conf_text}。{style_desc}"
        )

        # 显示评分
        parts.append(
            f"<p><strong>量化评分</strong>：短线适宜度{short_score:.0f}分 / 长线适宜度{long_score:.0f}分。"
        )
    else:
        parts.append("<p>数据不足，无法提供操作建议。</p>")

    # 多空信号
    sig_summary = signals.get("signal_summary", {})
    bull_cnt = sig_summary.get("bullish_count", 0)
    bear_cnt = sig_summary.get("bearish_count", 0)
    if bull_cnt or bear_cnt:
        if bull_cnt > bear_cnt:
            parts.append(
                f"<p><strong>信号汇总</strong>：当前持有<strong>{bull_cnt}个看多信号</strong>、{bear_cnt}个看空信号，整体偏乐观。"
            )
        elif bear_cnt > bull_cnt:
            parts.append(
                f"<p><strong>信号汇总</strong>：当前持有{bull_cnt}个看多信号、<strong>{bear_cnt}个看空信号</strong>，整体偏谨慎。"
            )
        else:
            parts.append(
                f"<p><strong>信号汇总</strong>：当前持有{bull_cnt}个看多信号、{bear_cnt}个看空信号，多空力量均衡。"
            )

    # 短线/长线依据（复用 evaluate_trading_style 已生成的文字）
    short_basis = ts.get("short_term_basis", "")
    long_basis = ts.get("long_term_basis", "")
    if style in ("短线", "短线+长线") and short_basis:
        parts.append(f"<p><strong>短线依据：</strong>{short_basis}</p>")
    if style in ("长线", "短线+长线") and long_basis:
        parts.append(f"<p><strong>长线依据：</strong>{long_basis}</p>")

    # 止损止盈操作建议
    sl = stop.get("止损参考价") if stop else None
    tp = stop.get("止盈参考价") if stop else None
    if sl and tp and isinstance(sl, (int, float)):
        sl_pct = stop.get("止损幅度%", "")
        tp_pct = stop.get("止盈幅度%", "")
        parts.append(
            f"<p><strong>操作参考</strong>：建议将止损设在{sl}（约{sl_pct}%），目标止盈参考{tp}（约{tp_pct}%），严格执行纪律以控制风险。</p>"
        )

    parts.append("</div>")
    return "\n".join(parts)


def _build_news_section(detail: dict) -> str:
    """生成新闻舆情 HTML 块"""
    headlines = detail.get("news_headlines", [])
    times = detail.get("news_times", [])
    sources = detail.get("news_sources", [])
    if not headlines:
        return ""

    items_html = []
    for i, title in enumerate(headlines[:3]):
        t = times[i] if i < len(times) else ""
        s = sources[i] if i < len(sources) else ""
        meta = f"{t} | {s}" if t and s else (t or s or "")
        items_html.append(
            f"""<div class="news-item"><div class="news-title">{title}</div><div class="news-meta">{meta}</div></div>"""
        )

    return f"""<div class="sd-section">
          <div class="sd-section-title">最新舆情</div>
          <div class="sd-news-list">{"".join(items_html)}</div>
        </div>"""


def _build_stock_narrative(detail: dict) -> str:
    """组合所有叙述文字为完整 HTML"""
    sections = [
        _build_fundamental_narrative(detail),
        _build_technical_narrative(detail),
        _build_risk_narrative(detail),
        _build_trading_suggestion(detail),
    ]
    return '<div class="sd-narrative">\n' + "\n".join(sections) + "\n</div>"


# ── 操作建议生成 ──────────────────────────────────


def _build_operation_advice(detail: dict) -> str:
    """根据多维度数据生成短线/长线操作建议"""
    ts = detail.get("trading_style", {})
    tech = detail.get("technical_summary", {})
    risk = detail.get("risk_metrics", {})
    quant_score = detail.get("quant_score", {})
    fund_flow = detail.get("fund_flow", {}) or {}
    nt = detail.get("national_team", {}) or {}
    signals = detail.get("signals", {})

    short_score = ts.get("short_term_score", 50)
    long_score = ts.get("long_term_score", 50)
    funda_score = detail.get("fundamental_score", 50)
    rsi_val = tech.get("rsi_value", 50)
    near_5d = detail.get("near_5d_pct", 0)
    near_20d = detail.get("near_20d_pct", 0)
    max_dd = risk.get("max_drawdown_pct", 0)
    bias = signals.get("bias", "neutral")
    main_ratio = fund_flow.get("主力净流入-净占比", 0)
    has_nt = nt.get("has_national_team", False)
    qs_total = quant_score.get("total", 50) if isinstance(quant_score, dict) else 50

    if isinstance(main_ratio, str):
        try:
            main_ratio = float(main_ratio.replace("%", ""))
        except (ValueError, TypeError):
            main_ratio = 0

    parts = []
    parts.append('<div class="sd-section">')
    parts.append('<div class="sd-section-title">操作建议</div>')

    try:
        rsi_val = float(rsi_val)
    except (TypeError, ValueError):
        rsi_val = 50
    try:
        near_20d = float(near_20d)
    except (TypeError, ValueError):
        near_20d = 0
    try:
        near_5d = float(near_5d)
    except (TypeError, ValueError):
        near_5d = 0
    try:
        short_score = float(short_score)
    except (TypeError, ValueError):
        short_score = 50
    try:
        long_score = float(long_score)
    except (TypeError, ValueError):
        long_score = 50
    try:
        funda_score = float(funda_score)
    except (TypeError, ValueError):
        funda_score = 50
    try:
        max_dd = float(max_dd) if max_dd else 0
    except (TypeError, ValueError):
        max_dd = 0
    try:
        main_ratio = float(main_ratio)
    except (TypeError, ValueError):
        main_ratio = 0

    # ─── 短线操作建议 ───
    short_notes = []
    is_overbought = rsi_val >= 72
    is_oversold = rsi_val <= 28
    is_risen_much = near_20d > 20
    is_dropped_much = near_20d < -15

    if is_overbought:
        short_notes.append(f"RSI({rsi_val:.0f})偏高，短期存在回调风险")
    if is_risen_much:
        short_notes.append(f"近20日涨幅{near_20d:.1f}%，短期追高风险较大")
    if main_ratio < -2:
        short_notes.append("主力资金净流出较大，短期资金面偏弱")
    if is_dropped_much and not is_overbought:
        short_notes.append(f"短期跌幅较大({near_20d:.1f}%)，存在超跌反弹需求")

    if short_score >= 70 and not is_overbought and bias == "bullish":
        short_conclusion = "短线技术面较强，适合已有持仓者继续持有"
    elif short_score >= 70 and is_overbought:
        short_conclusion = "短线评分较高但RSI已偏高，已有持仓者可持有，不适合空仓追入"
    elif short_score >= 70 and is_risen_much:
        short_conclusion = "短线评分较高但近期涨幅已大，追高需谨慎，可等回调再介入"
    elif short_score >= 50 and not is_overbought:
        short_conclusion = "短线信号中性偏正面，可逢低小仓位试探"
    elif short_score >= 50 and is_overbought:
        short_conclusion = "短线信号中性，但当前价位偏高，建议等待回调"
    elif short_score < 40:
        short_conclusion = "短线信号偏弱，建议观望，等待趋势明朗"
    else:
        short_conclusion = "短线方向不明，建议观望或轻仓操作"

    # ─── 长线操作建议 ───
    long_notes = []
    if has_nt:
        nt_names = nt.get("holders", [])
        nt_count = len(nt_names)
        long_notes.append(f"十大流通股东中发现{nt_count}家国家队机构持股，长线安全边际较高")
    if funda_score >= 80:
        long_notes.append("基本面评分优秀，适合作为长线核心配置")
    elif funda_score >= 65:
        long_notes.append("基本面评分良好，具备长线持有价值")
    elif funda_score < 40:
        long_notes.append("基本面评分偏低，长线持有需跟踪业绩变化")
    if abs(max_dd) >= 35:
        long_notes.append(f"历史最大回撤达{abs(max_dd):.1f}%，需承受较大波动，建议分批建仓或定投")
    elif abs(max_dd) >= 20:
        long_notes.append(f"历史最大回撤{abs(max_dd):.1f}%，属正常波动范围")
    if long_score >= 70 and funda_score >= 65 and has_nt:
        long_conclusion = "基本面良好+国家队背书，适合长线持有，建议分批建仓，耐心持有3个月以上"
    elif long_score >= 70 and funda_score >= 65:
        long_conclusion = "基本面良好，长线适宜度高，适合中长期持有"
    elif long_score >= 50 and has_nt:
        long_conclusion = "有国家队持股托底，长线风险相对可控，适合小额定投"
    elif long_score >= 50:
        long_conclusion = "长线适宜度中等，建议结合自身风险偏好决定持仓周期"
    elif long_score < 40:
        long_conclusion = "长线信号偏弱，不建议长期持有"
    else:
        long_conclusion = "长线方向不明确，建议等待更好入场时机"

    # 构建HTML
    parts.append('<div class="sd-advice-grid">')

    # 短线建议框
    short_extra = ""
    if short_notes:
        short_extra = '<div class="sd-advice-note">' + "；".join(short_notes) + "</div>"
    # 标签颜色根据建议性质
    if "不适合空仓追入" in short_conclusion or "追高需谨慎" in short_conclusion:
        sc_color = "#e65100"
    elif "持有" in short_conclusion and "追" not in short_conclusion:
        sc_color = "#2e7d32"
    elif "观望" in short_conclusion:
        sc_color = "#757575"
    else:
        sc_color = "#1565c0"

    parts.append(f"""<div class="sd-advice-item">
      <div class="sd-advice-header" style="color:{sc_color};border-left:3px solid {sc_color};">
        <span class="sd-advice-icon">📈</span> 短线操作
        <span class="sd-advice-score">评分 {short_score:.0f}</span>
      </div>
      <div class="sd-advice-body">
        <div class="sd-advice-conclusion"><strong>结论：</strong>{short_conclusion}</div>
        {short_extra}
      </div>
    </div>""")

    # 长线建议框
    long_extra = ""
    if long_notes:
        long_extra = '<div class="sd-advice-note">' + "；".join(long_notes) + "</div>"
    if "分批建仓" in long_conclusion or "定投" in long_conclusion:
        lc_color = "#2e7d32"
    elif "持有" in long_conclusion:
        lc_color = "#1565c0"
    elif "不适合" in long_conclusion or "不建议" in long_conclusion:
        lc_color = "#c62828"
    else:
        lc_color = "#6a1b9a"

    parts.append(f"""<div class="sd-advice-item">
      <div class="sd-advice-header" style="color:{lc_color};border-left:3px solid {lc_color};">
        <span class="sd-advice-icon">📊</span> 长线操作
        <span class="sd-advice-score">评分 {long_score:.0f}</span>
      </div>
      <div class="sd-advice-body">
        <div class="sd-advice-conclusion"><strong>结论：</strong>{long_conclusion}</div>
        {long_extra}
      </div>
    </div>""")

    parts.append("</div>")
    parts.append("</div>")
    return "\n".join(parts)


# ── 个股详情卡片 HTML 生成 ──────────────────────────


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
    if stop_loss and isinstance(stop_loss, (int, float)):
        sl_commentary.append(f"建议止损价 {stop_loss}，回撤幅度约{stop_pct}%")
    if take_profit and isinstance(take_profit, (int, float)):
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
    if ff_main_amount and isinstance(ff_main_amount, (int, float)) and abs(ff_main_amount) > 0:
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


# ── HTML 模板骨架 ────────────────────────────────────

_PAGE_HEADER = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                 "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
    background: #f0f2f5; color: #333; padding: 20px;
  }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  .header {{
    background: linear-gradient(135deg, #1a73e8, #1557b0);
    color: #fff; padding: 28px 32px; border-radius: 12px;
    margin-bottom: 24px; box-shadow: 0 4px 20px rgba(26,115,232,0.25);
  }}
  .header h1 {{ font-size: 24px; font-weight: 600; }}
  .header .meta {{ font-size: 13px; opacity: 0.85; margin-top: 6px; }}

  .card {{
    background: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    padding: 20px 24px; margin-bottom: 20px; overflow: hidden;
  }}
  .card-title {{
    font-size: 16px; font-weight: 600; color: #1a73e8;
    margin-bottom: 16px; padding-bottom: 10px;
    border-bottom: 2px solid #e8edf3;
  }}
  .card-subtitle {{
    font-size: 13px; color: #888; margin-top: -10px; margin-bottom: 16px; line-height: 1.6;
  }}

  /* 概览卡片网格 */
  .stat-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 16px; margin-bottom: 20px;
  }}
  .stat-card {{
    background: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    padding: 18px 16px; text-align: center;
  }}
  .stat-card .label {{ font-size: 12px; color: #888; margin-bottom: 4px; }}
  .stat-card .value {{ font-size: 22px; font-weight: 700; color: #1a73e8; }}
  .stat-card .value.green {{ color: #2e7d32; }}
  .stat-card .value.red {{ color: #d32f2f; }}

  /* 表格 */
  .table-wrap {{
    overflow-x: auto; margin: 0 -4px;
  }}
  table {{
    width: 100%; border-collapse: collapse; font-size: 13px;
    min-width: 680px;
  }}
  thead th {{
    background: #1a73e8; color: #fff; padding: 10px 8px;
    text-align: center; font-weight: 600; white-space: nowrap;
    position: sticky; top: 0; z-index: 1;
  }}
  tbody td {{
    padding: 9px 8px; text-align: center; border-bottom: 1px solid #eee;
    white-space: nowrap;
  }}
  tbody tr:hover {{ background: #f5f8ff; }}
  .rating-badge {{
    display: inline-block; padding: 2px 10px; border-radius: 12px;
    font-size: 12px; font-weight: 600;
  }}

  /* 图表容器 */
  .chart-row {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
    gap: 20px; margin-bottom: 20px;
  }}
  .chart-box {{
    background: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    padding: 16px; position: relative;
  }}
  .chart-box .chart-title {{
    font-size: 14px; font-weight: 600; color: #333;
    margin-bottom: 10px; text-align: center;
  }}
  .chart-box canvas {{ width: 100% !important; height: auto !important; max-height: 360px; }}

  /* 个股详情卡片 */
  .stock-detail-card {{
    border: 1px solid #e8edf3;
    border-radius: 10px; margin-bottom: 16px; overflow: hidden;
  }}
  .sd-header {{
    display: flex; align-items: center; gap: 12px;
    padding: 12px 16px; background: #f8faff;
    border-bottom: 1px solid #e8edf3;
    flex-wrap: wrap;
  }}
  .sd-code {{ font-size: 15px; font-weight: 700; color: #1a73e8; }}
  .sd-name {{ font-size: 14px; color: #555; }}
  .sd-price {{ font-size: 16px; font-weight: 700; margin-left: auto; }}
  .sd-change {{ font-size: 13px; font-weight: 600; }}
  .sd-score {{ font-size: 14px; font-weight: 700; }}
  .sd-body {{ padding: 14px 16px; }}
  .sd-section {{ margin-bottom: 12px; }}
  .sd-section:last-child {{ margin-bottom: 0; }}
  .sd-section-title {{
    font-size: 12px; font-weight: 600; color: #1a73e8;
    margin-bottom: 8px; padding-bottom: 4px;
    border-bottom: 1px dashed #e8edf3;
  }}
  .sd-info-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 6px;
  }}
  .sd-info-item {{
    padding: 4px 8px; background: #f8faff; border-radius: 6px;
    display: flex; flex-direction: column;
  }}
  .sd-label {{ font-size: 11px; color: #888; }}
  .sd-value {{ font-size: 13px; font-weight: 600; color: #333; }}
  .sd-value.sd-bullish {{ color: #d32f2f; }}
  .sd-value.sd-bearish {{ color: #2e7d32; }}
  .sd-value.sd-warning {{ color: #d32f2f; }}
  .sd-value.sd-oversold {{ color: #2e7d32; }}
  .sd-tech-comment, .sd-sl-comment {{
    font-size: 12px; color: #666; margin-top: 6px;
    padding: 6px 10px; background: #fafafa; border-radius: 6px;
    line-height: 1.6;
  }}
  .sd-levels-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 6px;
  }}
  .sd-sector {{
    font-size: 11px; color: #fff; background: #1a73e8; padding: 2px 8px;
    border-radius: 10px; font-weight: 500;
  }}
  .sd-style-badge {{
    font-size: 11px; color: #fff; padding: 2px 10px; border-radius: 10px;
    font-weight: 600;
  }}
  .nt-badge {{
    font-size: 11px; color: #b8860b; background: #fff8e1; padding: 2px 10px; border-radius: 10px;
    font-weight: 600; border: 1px solid #f0d060; cursor: help;
  }}
  .sd-news-list {{
    display: flex; flex-direction: column; gap: 8px; margin-top: 4px;
  }}
  .news-item {{
    padding: 8px 10px; background: #f8f9ff; border-radius: 6px;
    border-left: 3px solid #1a73e8;
  }}
  .news-title {{ font-size: 13px; color: #333; line-height: 1.5; }}
  .news-meta {{ font-size: 11px; color: #999; margin-top: 3px; }}
  .sd-ts-grid {{
    display: grid; gap: 10px; margin-bottom: 8px;
  }}
  .sd-ts-item {{
    display: flex; flex-direction: column; gap: 4px;
  }}
  .sd-ts-label {{
    display: flex; justify-content: space-between; font-size: 13px;
  }}
  .sd-ts-score {{ font-weight: 700; font-size: 15px; }}
  .sd-ts-bar {{
    height: 8px; background: #eee; border-radius: 4px; overflow: hidden;
  }}
  .sd-ts-bar-fill {{
    height: 100%; border-radius: 4px; transition: width 0.3s ease;
  }}
  .sd-ts-confidence {{
    font-size: 12px; color: #666; margin-bottom: 6px;
  }}
  .sd-ts-basis {{
    font-size: 12px; color: #444; line-height: 1.7; margin-bottom: 4px;
    padding: 6px 10px; background: #f8faff; border-radius: 6px;
  }}

  /* 操作建议 */
  .sd-advice-grid {{
    display: flex; gap: 12px; flex-wrap: wrap; margin-top: 6px;
  }}
  .sd-advice-item {{
    flex: 1; min-width: 220px; border: 1px solid #e8e8e8;
    border-radius: 8px; overflow: hidden; background: #fff;
  }}
  .sd-advice-header {{
    display: flex; align-items: center; gap: 6px;
    padding: 8px 10px; font-size: 13px; font-weight: 600;
  }}
  .sd-advice-icon {{ font-size: 15px; }}
  .sd-advice-score {{
    margin-left: auto; font-size: 11px; font-weight: 400;
    background: #f5f5f5; padding: 1px 8px; border-radius: 10px;
  }}
  .sd-advice-body {{
    padding: 8px 10px 10px;
  }}
  .sd-advice-conclusion {{
    font-size: 13px; line-height: 1.7; color: #333;
  }}
  .sd-advice-note {{
    font-size: 12px; line-height: 1.6; color: #666;
    margin-top: 6px; padding: 6px 8px; background: #fafafa;
    border-radius: 4px; border-left: 2px solid #ddd;
  }}
  .sd-level-item {{
    padding: 6px 8px; background: #f8faff; border-radius: 6px;
    text-align: center;
  }}
  .sd-level-label {{ font-size: 11px; color: #888; display: block; }}
  .sd-level-value {{ font-size: 13px; font-weight: 600; color: #333; }}

  /* 术语悬停提示 */
  .term-t {{
    cursor: help; border-bottom: 1px dashed #1a73e8; position: relative;
    display: inline-block;
  }}
  .term-t-popup {{
    visibility: hidden; opacity: 0; transition: opacity 0.2s, visibility 0.2s;
    position: absolute; bottom: calc(100% + 6px); left: 50%; transform: translateX(-50%);
    background: #333; color: #fff; font-size: 12px; line-height: 1.5;
    padding: 8px 12px; border-radius: 8px; width: 240px; z-index: 100;
    text-align: left; font-weight: 400; box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    pointer-events: none;
  }}
  .term-t-popup::after {{
    content: ''; position: absolute; top: 100%; left: 50%; transform: translateX(-50%);
    border: 6px solid transparent; border-top-color: #333;
  }}
  .term-t:hover .term-t-popup {{
    visibility: visible; opacity: 1;
  }}
  .sd-info-item:hover {{ box-shadow: 0 1px 4px rgba(26,115,232,0.15); transition: box-shadow 0.15s; }}

  /* 空状态 */
  .empty-state {{
    text-align: center; padding: 48px 24px; color: #999;
  }}
  .empty-state .icon {{ font-size: 48px; margin-bottom: 12px; }}

  /* 免责声明 */
  .disclaimer {{
    background: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    padding: 18px 24px; margin-top: 20px;
  }}
  .disclaimer p {{
    font-size: 12px; color: #999; line-height: 1.8; margin: 0;
  }}

  /* 市场概述 */
  .market-overview {{
    background: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    padding: 18px 24px; margin-bottom: 20px; line-height: 1.8;
  }}
  .market-overview h3 {{ font-size: 15px; color: #1a73e8; margin-bottom: 8px; }}
  .market-overview p {{ font-size: 13px; color: #555; }}

  /* 术语表 */
  .glossary-grid {{
    display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 10px; margin-top: 8px;
  }}
  .glossary-item {{
    padding: 10px 12px; background: #f8faff; border-radius: 8px;
    border-left: 3px solid #1a73e8; transition: background 0.15s;
  }}
  .glossary-item:hover {{ background: #eef3fc; }}
  .glossary-term {{
    font-size: 13px; font-weight: 700; color: #1a73e8;
    display: block; margin-bottom: 3px;
  }}
  .glossary-def {{
    font-size: 12px; color: #555; line-height: 1.6; display: block;
  }}

  /* 叙述文字 */
  .sd-narrative {{
    padding: 14px 16px; background: #fafcff; border-radius: 8px;
    margin-bottom: 14px; border: 1px solid #e8edf3;
  }}
  .narrative-block p {{
    font-size: 13px; line-height: 1.9; color: #444; margin-bottom: 8px;
  }}
  .narrative-block p:last-child {{ margin-bottom: 0; }}
  .n-subtitle {{
    font-size: 13px; font-weight: 700; color: #1a73e8;
    margin-bottom: 4px; margin-top: 10px;
  }}
  .n-subtitle:first-child {{ margin-top: 0; }}

  /* 核心观点高亮 */
  .key-finding {{
    padding: 12px 16px; border-radius: 8px; margin: 10px 0;
    font-size: 13px; line-height: 1.8;
  }}
  .key-finding.positive {{ background: #e8f5e9; border-left: 4px solid #2e7d32; color: #1b5e20; }}
  .key-finding.negative {{ background: #ffebee; border-left: 4px solid #c62828; color: #b71c1c; }}
  .key-finding.neutral {{ background: #fff8e1; border-left: 4px solid #f9a825; color: #795548; }}
  .kf-label {{ font-weight: 700; display: block; margin-bottom: 2px; font-size: 12px; }}

  /* 速览统计 */
  .glance-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
    gap: 10px; margin-bottom: 16px;
  }}
  .glance-item {{
    background: #fff; border-radius: 8px; padding: 12px 10px;
    text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  }}
  .glance-value {{ font-size: 20px; font-weight: 700; color: #1a73e8; }}
  .glance-value.green {{ color: #2e7d32; }}
  .glance-value.red {{ color: #d32f2f; }}
  .glance-label {{ font-size: 11px; color: #888; margin-top: 2px; }}

  /* 评分模型展示 */
  .model-factor-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 10px; margin: 12px 0;
  }}
  .model-factor {{
    padding: 10px 12px; background: #f8faff; border-radius: 8px;
    border-top: 3px solid #1a73e8;
  }}
  .model-factor .mf-header {{
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;
  }}
  .model-factor .mf-name {{ font-size: 13px; font-weight: 700; color: #333; }}
  .model-factor .mf-weight {{ font-size: 11px; color: #1a73e8; font-weight: 600; }}
  .model-factor .mf-desc {{ font-size: 12px; color: #666; line-height: 1.6; }}
  .mf-bar {{ height: 4px; background: #e8edf3; border-radius: 2px; margin-top: 6px; overflow: hidden; }}
  .mf-bar-fill {{ height: 100%; border-radius: 2px; }}

  @media (max-width: 640px) {{
    body {{ padding: 12px; }}
    .header {{ padding: 18px 16px; }}
    .card {{ padding: 14px 16px; }}
    .stat-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .chart-row {{ grid-template-columns: 1fr; }}
    .sd-header {{ gap: 6px; }}
  }}
</style>
</head>
<body>
<div class="container">
"""

_PAGE_FOOTER = r"""
  <div class="disclaimer">
    <p><strong>免责声明：</strong>
    本报告由 AI 自动生成，数据来源于公开市场信息，仅供参考，不构成任何投资建议或投资承诺。
    投资有风险，入市需谨慎。过往表现不代表未来收益。<br>
    报告生成时间：{gen_time} &nbsp;|&nbsp; AI 工具：Claude Code</p>
  </div>
</div>
</body>
</html>"""


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


# ══════════════════════════════════════════════════════
# 1. 选股结果报告（增强版）
# ══════════════════════════════════════════════════════


def generate_screener_report(
    screener_result: pd.DataFrame,
    output_path: str | None = None,
    stock_details: dict[str, Any] | None = None,
) -> str:
    """生成选股结果 HTML 报告（含个股详情 + 选股逻辑 + 图表）

    Parameters
    ----------
    screener_result : pd.DataFrame
        包含字段: 代码/名称/综合评分/评级/动量分/技术分/基本面分/量能分/风险分/最新价/涨跌幅
    output_path : str or None
        输出路径，默认 reports/screener_YYYYMMDD_HHMM.html
    stock_details : dict or None
        可选，每只股票的详细分析数据，格式: {code: {name, score, rating, price, change,
                      support_resistance, stop_levels, technical_summary,
                      risk_metrics, signals, quant_score, trading_style}}

        传入 stock_details 时会自动扩展生成：
        - 选股逻辑说明（全市场板块分布/评分模型/个股详细解析）
        - 评级分布饼图（doughnut chart）
        - 因子评分对比柱状图（Top10 分组柱状图）

    Returns
    -------
    str : 实际保存的文件路径
    """
    if output_path is None:
        output_path = _default_path("screener")

    df = screener_result.copy()
    now = datetime.now()
    gen_time = now.strftime("%Y-%m-%d %H:%M:%S")
    stock_count = len(df)

    # ── 构建 HTML ──────────────────────────────────
    parts = [_PAGE_HEADER.format(title="每日选股池报告")]

    # 标题
    parts.append(f"""  <div class="header">
    <h1>每日选股池报告</h1>
    <div class="meta">生成时间：{gen_time} &nbsp;|&nbsp; 扫描股票：{stock_count} 只 &nbsp;|&nbsp; 数据源：新浪财经/东方财富</div>
  </div>""")

    # 市场概述（文字分析）
    parts.append(_build_market_overview(df, stock_details))

    # ── 选股逻辑说明（板块分析 + 个股选择依据）───
    if stock_details:
        rationale = _build_selection_rationale(
            df, stock_details, total_scanned=stock_count, top_n=min(10, stock_count)
        )
        if rationale:
            parts.append(rationale)

    # ── 数据表格 ──────────────────────────────────
    parts.append("""  <div class="card">
    <div class="card-title">选股结果明细</div>
    <div class="card-subtitle">按综合评分降序排列，综合评分 = 动量(25%) + 技术(25%) + 基本面(20%) + 量能(15%) + 风险(15%)</div>
    <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>序号</th>
          <th>代码</th>
          <th>综合评分</th>
          <th>评级</th>
          <th>动量分</th>
          <th>技术分</th>
          <th>基本面分</th>
          <th>量能分</th>
          <th>风险分</th>
          <th>最新价</th>
          <th>涨跌幅</th>
        </tr>
      </thead>
      <tbody>""")

    has_seq = "序号" in df.columns

    for idx, (_, row) in enumerate(df.iterrows()):
        seq = row.get("序号", idx + 1)
        code = _escape_html(row.get("代码", ""))
        name = _escape_html(row.get("名称", ""))
        score = _escape_html(row.get("综合评分", ""))
        rating = str(row.get("评级", ""))
        mom = _escape_html(row.get("动量分", ""))
        tech = _escape_html(row.get("技术分", ""))
        fund = _escape_html(row.get("基本面分", ""))
        vol = _escape_html(row.get("量能分", ""))
        risk = _escape_html(row.get("风险分", ""))
        price = _escape_html(row.get("最新价", ""))
        change_val = row.get("涨跌幅", 0)

        r_color = _rating_color(rating)
        r_bg = _rating_bg_color(rating)
        ch_color = _change_color(change_val)
        ch_str = _change_sign(change_val)

        parts.append(f"""        <tr>
          <td>{seq}</td>
          <td><strong>{code}</strong><br><span style="font-size:11px;color:#888">{name}</span></td>
          <td style="font-weight:600;color:{_color_for_value(score)}">{score}</td>
          <td><span class="rating-badge" style="color:{r_color};background:{r_bg}">{rating}</span></td>
          <td style="color:{_color_for_value(mom)}">{mom}</td>
          <td style="color:{_color_for_value(tech)}">{tech}</td>
          <td style="color:{_color_for_value(fund)}">{fund}</td>
          <td style="color:{_color_for_value(vol)}">{vol}</td>
          <td style="color:{_color_for_value(risk, invert=True)}">{risk}</td>
          <td>{price}</td>
          <td style="color:{ch_color};font-weight:600">{ch_str}%</td>
        </tr>""")

    parts.append("""      </tbody>
    </table>
    </div>
  </div>""")

    # ── 个股分析详情（仅显示有完整数据的股票）───────
    if stock_details:
        detail_codes = [
            code
            for code in df["代码"].astype(str).str.zfill(6).tolist()
            if code in stock_details and stock_details[code].get("quant_score")
        ]
        if detail_codes:
            parts.append("""  <div class="card">
    <div class="card-title">个股深度分析</div>
    <div class="card-subtitle">仅显示有完整分析数据的股票，含支撑位/压力位、止损止盈参考、技术面状态和风险指标</div>""")
            for idx, code in enumerate(detail_codes):
                row = df[df["代码"].astype(str).str.zfill(6) == code].iloc[0]
                detail = stock_details.get(code, {}).copy()
                detail["score"] = row.get("综合评分", "")
                detail["rating"] = str(row.get("评级", ""))
                detail["price"] = row.get("最新价", "")
                detail["change"] = row.get("涨跌幅", 0)
                name = row.get("名称", code)
                detail.setdefault("name", name)
                parts.append(_stock_detail_card(code, detail, idx + 1))
            parts.append("  </div>")

    # ── 雷达图：五维评分，最多前5只 ────────────────
    if stock_count > 0:
        top5 = df.head(5)
        labels_json = json.dumps(
            ["动量分", "技术分", "基本面分", "量能分", "风险分"], ensure_ascii=False
        )

        datasets = []
        for _, row in top5.iterrows():
            code = str(row.get("代码", ""))
            mom = float(row.get("动量分", 0) or 0)
            tech = float(row.get("技术分", 0) or 0)
            fund = float(row.get("基本面分", 0) or 0)
            vol = float(row.get("量能分", 0) or 0)
            risk = float(row.get("风险分", 0) or 0)
            datasets.append(
                {
                    "label": code,
                    "data": [mom, tech, fund, vol, risk],
                    "fill": True,
                }
            )

        datasets_json = json.dumps(datasets, ensure_ascii=False)

        parts.append(f"""  <div class="card">
    <div class="card-title">五维评分雷达图（前 {len(top5)} 只）</div>
    <div class="card-subtitle">动量(25%) · 技术(25%) · 基本面(20%) · 量能(15%) · 风险(15%)</div>
    <div class="chart-box">
      <canvas id="radarChart"></canvas>
    </div>
  </div>""")

        palette = [
            {"bg": "rgba(26,115,232,0.15)", "border": "rgba(26,115,232,0.9)"},
            {"bg": "rgba(219,68,55,0.15)", "border": "rgba(219,68,55,0.9)"},
            {"bg": "rgba(15,157,88,0.15)", "border": "rgba(15,157,88,0.9)"},
            {"bg": "rgba(255,193,7,0.15)", "border": "rgba(255,193,7,0.9)"},
            {"bg": "rgba(156,39,176,0.15)", "border": "rgba(156,39,176,0.9)"},
        ]

        parts.append(
            """<script>
  (function() {
    var ctx = document.getElementById('radarChart').getContext('2d');
    var labels = """
            + labels_json
            + """;
    var rawDatasets = """
            + datasets_json
            + """;
    var palette = """
            + json.dumps(palette, ensure_ascii=False)
            + """;
    var datasets = rawDatasets.map(function(ds, i) {
      var p = palette[i % palette.length];
      return {
        label: ds.label,
        data: ds.data,
        backgroundColor: p.bg,
        borderColor: p.border,
        borderWidth: 2,
        pointBackgroundColor: p.border,
        pointRadius: 3,
      };
    });
    new Chart(ctx, {
      type: 'radar',
      data: { labels: labels, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: { position: 'bottom', labels: { font: { size: 12 }, padding: 16 } },
        },
        scales: {
          r: {
            beginAtZero: true, max: 100,
            ticks: { stepSize: 20, font: { size: 10 }, backdropColor: 'transparent' },
            pointLabels: { font: { size: 12, weight: 'bold' }, color: '#333' },
            grid: { color: 'rgba(0,0,0,0.08)' },
            angleLines: { color: 'rgba(0,0,0,0.08)' },
          }
        }
      }
    });
  })();
</script>"""
        )

    else:
        parts.append("""  <div class="card">
    <div class="empty-state">
      <div class="icon">&#128200;</div>
      <p>暂无选股结果数据</p>
    </div>
  </div>""")

    # ── 评级分布饼图 + 因子对比柱状图 ─────────────
    if stock_count > 0 and stock_details:
        rating_order = ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]
        rating_counts = dict.fromkeys(rating_order, 0)
        for _, srow in df.iterrows():
            r = str(srow.get("评级", "")).strip()
            if r in rating_counts:
                rating_counts[r] += 1
            elif "Buy" in r:
                rating_counts["Buy"] += 1
            elif "Sell" in r:
                rating_counts["Sell"] += 1
        rating_labels_json = json.dumps(rating_order, ensure_ascii=False)
        rating_data_json = json.dumps([rating_counts[r] for r in rating_order], ensure_ascii=False)

        factor_labels = json.dumps(
            ["动量分", "技术分", "基本面分", "量能分", "风险分"], ensure_ascii=False
        )
        stock_ds_list = []
        top_n_chart = min(10, len(df))
        for _, srow in df.head(top_n_chart).iterrows():
            code = str(srow.get("代码", ""))
            sd = (stock_details or {}).get(code, {})
            qs = sd.get("quant_score", {})
            fs = qs.get("factor_scores", {})
            vals = [
                fs.get(k, {}).get("score", 0)
                for k in ["momentum", "technical", "fundamental", "volume", "risk"]
            ]
            if not any(v > 0 for v in vals):
                vals = [
                    float(srow.get("动量分", 0) or 0),
                    float(srow.get("技术分", 0) or 0),
                    float(srow.get("基本面分", 0) or 0),
                    float(srow.get("量能分", 0) or 0),
                    float(srow.get("风险分", 0) or 0),
                ]
            stock_ds_list.append({"label": code, "data": vals})
        stock_datasets_json = json.dumps(stock_ds_list, ensure_ascii=False)
        has_charts = json.dumps(len(stock_ds_list) > 0)

        parts.append(f"""
  <div class="chart-row">
    <div class="chart-box">
      <div class="chart-title">评级分布</div>
      <canvas id="ratingChart"></canvas>
    </div>
    <div class="chart-box">
      <div class="chart-title">因子评分对比（前 {top_n_chart} 只）</div>
      <canvas id="factorChart"></canvas>
    </div>
  </div>
<script>
(function() {{
  new Chart(document.getElementById('ratingChart'), {{
    type: 'doughnut',
    data: {{
      labels: {rating_labels_json},
      datasets: [{{
        data: {rating_data_json},
        backgroundColor: ['#2e7d32','#66bb6a','#f9a825','#ef6c00','#c62828'],
        borderWidth: 1,
      }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: true,
      plugins: {{ legend: {{ position: 'bottom', labels: {{ font: {{ size: 12 }}, padding: 16 }} }} }},
    }}
  }});
  var fctx = document.getElementById('factorChart');
  if (fctx && {has_charts}) {{
    var colors = ['#1a73e8','#db4437','#0f9d58','#f9a825','#9c27b0',
                  '#e91e63','#00bcd4','#ff5722','#607d8b','#795548'];
    new Chart(fctx, {{
      type: 'bar',
      data: {{
        labels: {factor_labels},
        datasets: {stock_datasets_json}.map(function(ds, i) {{
          return {{
            label: ds.label, data: ds.data,
            backgroundColor: colors[i % colors.length] + '33',
            borderColor: colors[i % colors.length],
            borderWidth: 2, borderRadius: 4,
          }};
        }}),
      }},
      options: {{
        responsive: true, maintainAspectRatio: true,
        plugins: {{ legend: {{ position: 'bottom', labels: {{ font: {{ size: 11 }}, padding: 12 }} }} }},
        scales: {{ y: {{ beginAtZero: true, max: 100, ticks: {{ stepSize: 20 }} }} }},
      }}
    }});
  }}
}})();
</script>""")

    # ── 术语表 ──────────────────────────────────────
    parts.append("""  <div class="card">
    <div class="card-title">专业术语说明</div>
    <div class="card-subtitle">报告中使用的专业术语解释</div>
    <div class="glossary-grid">""")
    for term, defn in TERM_DEFS.items():
        esc_defn = defn.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        parts.append(f"""      <div class="glossary-item">
        <span class="glossary-term">{term}</span>
        <span class="glossary-def">{esc_defn}</span>
      </div>""")
    parts.append("""    </div>
  </div>""")

    # ── 页脚 ──────────────────────────────────────
    parts.append(_PAGE_FOOTER.format(gen_time=gen_time))

    # ── 写出文件 ──────────────────────────────────
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))

    print(f"选股报告已生成: {output_path}")
    return output_path


# ══════════════════════════════════════════════════════
# 2. 投资组合报告（增强版）
# ══════════════════════════════════════════════════════


def generate_portfolio_report(
    portfolio_analysis: dict,
    output_path: str | None = None,
    stock_details: dict[str, Any] | None = None,
) -> str:
    """生成投资组合 HTML 报告（含个股详情）

    Parameters
    ----------
    portfolio_analysis : dict
        包含字段: 组合名称, total_value, total_return_pct, portfolio_volatility_pct,
                  portfolio_sharpe, stocks
    output_path : str or None
        输出路径，默认 reports/portfolio_YYYYMMDD_HHMM.html
    stock_details : dict or None
        可选，每只股票的详细分析数据，格式同 generate_screener_report

    Returns
    -------
    str : 实际保存的文件路径
    """
    if output_path is None:
        output_path = _default_path("portfolio")

    now = datetime.now()
    gen_time = now.strftime("%Y-%m-%d %H:%M:%S")

    analysis = portfolio_analysis
    stocks = analysis.get("stocks", []) or []

    name = analysis.get("name", analysis.get("组合名称", "未命名组合"))
    total_val = analysis.get("total_value", 0)
    total_cost = analysis.get("total_cost", 0)
    total_ret = analysis.get("total_return_pct", 0)
    vol = analysis.get("portfolio_volatility_pct", 0)
    sharpe_val = analysis.get("portfolio_sharpe", None)
    stock_count = analysis.get("stock_count", len(stocks))

    # ── 构建 HTML ──────────────────────────────────
    parts = [_PAGE_HEADER.format(title=f"组合报告 - {name}")]

    # 标题
    parts.append(f"""  <div class="header">
    <h1>{name} - 投资组合报告</h1>
    <div class="meta">生成时间：{gen_time} &nbsp;|&nbsp; 持股数量：{stock_count} 只</div>
  </div>""")

    # ── 概览卡片 ──────────────────────────────────
    ret_color = "green" if total_ret >= 0 else "red"
    ret_sign = "+" if total_ret >= 0 else ""
    sharpe_str = f"{sharpe_val:.2f}" if sharpe_val is not None else "-"

    # 组合评价文字
    portfolio_commentary = []
    if sharpe_val is not None:
        if sharpe_val >= 1:
            portfolio_commentary.append("夏普比率大于1，风险调整后收益表现优秀")
        elif sharpe_val >= 0.5:
            portfolio_commentary.append("夏普比率适中，风险收益平衡")
        elif sharpe_val > 0:
            portfolio_commentary.append("夏普比率为正，组合具备一定的风险调整收益")
        else:
            portfolio_commentary.append("夏普比率为负，组合收益未能覆盖风险")

    if vol > 30:
        portfolio_commentary.append(f"组合波动率较高({vol:.1f}%)，建议关注仓位控制")
    elif vol > 20:
        portfolio_commentary.append(f"组合波动率中等({vol:.1f}%)，风险可控")
    else:
        portfolio_commentary.append(f"组合波动率较低({vol:.1f}%)，风格偏稳健")

    if total_ret > 10:
        portfolio_commentary.append(f"组合累计收益{total_ret:.1f}%，表现良好")
    elif total_ret < 0:
        portfolio_commentary.append(f"组合累计亏损{abs(total_ret):.1f}%，需审视持仓")

    parts.append(f"""  <div class="stat-grid">
    <div class="stat-card">
      <div class="label">总市值</div>
      <div class="value">{_fmt_num(total_val)}</div>
    </div>
    <div class="stat-card">
      <div class="label">总收益</div>
      <div class="value {ret_color}">{ret_sign}{_fmt_num(total_ret, suffix="%")}</div>
    </div>
    <div class="stat-card">
      <div class="label">组合波动率</div>
      <div class="value">{_fmt_num(vol, suffix="%")}</div>
    </div>
    <div class="stat-card">
      <div class="label">夏普比率</div>
      <div class="value">{sharpe_str}</div>
    </div>
    <div class="stat-card">
      <div class="label">持股数</div>
      <div class="value">{stock_count}</div>
    </div>
  </div>""")

    # 组合评价卡片
    parts.append("""  <div class="card">
    <div class="card-title">组合评估</div>""")
    if portfolio_commentary:
        for line in portfolio_commentary:
            parts.append(f'    <p style="font-size:13px;color:#555;line-height:1.8;">• {line}</p>')
    # 调仓建议
    rebal = analysis.get("rebalance_suggestions")
    if rebal:
        parts.append(
            '    <div style="margin-top:12px;padding:10px 14px;background:#fff8e1;border-radius:8px;">'
        )
        parts.append('      <p style="font-size:13px;font-weight:600;color:#f57f17;">调仓建议</p>')
        for s in rebal:
            parts.append(f'      <p style="font-size:12px;color:#555;line-height:1.6;">• {s}</p>')
        parts.append("    </div>")
    parts.append("  </div>")

    # ── 持仓明细表 ──────────────────────────────────

    # ── 图表区域：评级分布 + 因子对比 ──────────────────────────
    if stocks:
        rating_order = ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]
        rating_counts = dict.fromkeys(rating_order, 0)
        for s in stocks:
            r = str(s.get("评级", ""))
            if r in rating_counts:
                rating_counts[r] += 1

        factor_labels = json.dumps(
            ["动量分", "技术分", "基本面分", "量能分", "风险分"], ensure_ascii=False
        )
        stock_ds_list = []
        for s in stocks[:5]:
            code = str(s.get("代码", ""))
            sd = (stock_details or {}).get(code, {})
            qs = sd.get("quant_score", {})
            fs = qs.get("factor_scores", {})
            vals = [
                fs.get(k, {}).get("score", 0)
                for k in ["momentum", "technical", "fundamental", "volume", "risk"]
            ]
            if any(v > 0 for v in vals):
                stock_ds_list.append({"label": code, "data": vals})
        stock_datasets_json = json.dumps(stock_ds_list, ensure_ascii=False)

        rating_labels_json = json.dumps(rating_order, ensure_ascii=False)
        rating_data_json = json.dumps([rating_counts[r] for r in rating_order], ensure_ascii=False)

        parts.append(f"""
  <div class=\"chart-row\">
    <div class=\"chart-box\">
      <div class=\"chart-title\">评级分布</div>
      <canvas id=\"ratingChart\"></canvas>
    </div>
    <div class=\"chart-box\">
      <div class=\"chart-title\">因子评分对比</div>
      <canvas id=\"factorChart\"></canvas>
    </div>
  </div>
<script>
(function() {{
  new Chart(document.getElementById('ratingChart'), {{
    type: 'doughnut',
    data: {{
      labels: {rating_labels_json},
      datasets: [{{
        data: {rating_data_json},
        backgroundColor: ['#2e7d32','#66bb6a','#f9a825','#ef6c00','#c62828'],
        borderWidth: 1,
      }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: true,
      plugins: {{ legend: {{ position: 'bottom', labels: {{ font: {{ size: 11 }}, padding: 12 }} }} }}
    }}
  }});
  var fctx = document.getElementById('factorChart');
  if (fctx && {stock_datasets_json}.length > 0) {{
    var colors = ['rgba(26,115,232,0.8)','rgba(219,68,55,0.8)','rgba(15,157,88,0.8)','rgba(255,193,7,0.8)','rgba(156,39,176,0.8)'];
    new Chart(fctx, {{
      type: 'bar',
      data: {{
        labels: {factor_labels},
        datasets: {stock_datasets_json}.map(function(ds, i) {{
          return {{ label: ds.label, data: ds.data, backgroundColor: colors[i % colors.length], borderRadius: 4 }};
        }})
      }},
      options: {{
        responsive: true, maintainAspectRatio: true,
        plugins: {{ legend: {{ position: 'bottom', labels: {{ font: {{ size: 11 }}, padding: 12 }} }} }},
        scales: {{ y: {{ beginAtZero: true, max: 100, ticks: {{ stepSize: 20 }} }} }}
      }}
    }});
  }}
}})();
</script>""")

    # ── 持仓明细表
    parts.append("""  <div class="card">
    <div class="card-title">持仓明细</div>
    <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>代码</th>
          <th>名称</th>
          <th>仓位(%)</th>
          <th>成本价</th>
          <th>现价</th>
          <th>收益率(%)</th>
          <th>贡献度(%)</th>
          <th>评分</th>
          <th>评级</th>
        </tr>
      </thead>
      <tbody>""")

    if stocks:
        for s in stocks:
            code = _escape_html(s.get("代码", ""))
            sname = _escape_html(s.get("名称", s.get("name", "")))
            weight = s.get("仓位%", s.get("仓位", ""))
            cost = s.get("成本价", s.get("成本", ""))
            price = s.get("现价", "")
            ret_s = s.get("收益率%", s.get("收益率", 0))
            contrib = s.get("贡献度%", s.get("贡献度", ""))
            score = s.get("评分", "")
            rating = str(s.get("评级", ""))

            ret_color_s = "#d32f2f" if (float(ret_s) if ret_s else 0) >= 0 else "#2e7d32"
            contrib_color = "#d32f2f" if (float(contrib) if contrib else 0) >= 0 else "#2e7d32"
            r_color = _rating_color(rating)
            r_bg = _rating_bg_color(rating)

            parts.append(f"""        <tr>
          <td><strong>{code}</strong></td>
          <td style="font-size:12px;color:#888">{sname}</td>
          <td>{_fmt_num(weight)}</td>
          <td>{_fmt_num(cost)}</td>
          <td>{_fmt_num(price)}</td>
          <td style="color:{ret_color_s};font-weight:600">{_change_sign(ret_s)}%</td>
          <td style="color:{contrib_color}">{_fmt_num(contrib)}</td>
          <td style="color:{_color_for_value(score)}">{_fmt_num(score, suffix="")}</td>
          <td><span class="rating-badge" style="color:{r_color};background:{r_bg}">{rating}</span></td>
        </tr>""")
    else:
        parts.append("""        <tr>
          <td colspan="9" style="color:#999;padding:32px;text-align:center;">暂无持仓数据</td>
        </tr>""")

    parts.append("""      </tbody>
    </table>
    </div>
  </div>""")

    # ── 个股分析详情 ──────────────────────────────
    if stock_details and stocks:
        parts.append("""  <div class="card">
    <div class="card-title">持仓个股深度分析</div>
    <div class="card-subtitle">每只股票的支撑位/压力位、止损止盈参考、技术面状态和风险指标</div>""")
        for s in stocks:
            code = str(s.get("代码", ""))
            detail = stock_details.get(code, {})
            detail.setdefault("name", s.get("名称", s.get("name", code)))
            detail["score"] = s.get("评分", "")
            detail["rating"] = str(s.get("评级", ""))
            detail["price"] = s.get("现价", "")
            parts.append(_stock_detail_card(code, detail))
        parts.append("  </div>")

    # ── 术语表 ──────────────────────────────────────
    parts.append("""  <div class="card">
    <div class="card-title">专业术语说明</div>
    <div class="card-subtitle">报告中使用的专业术语解释</div>
    <div class="glossary-grid">""")
    for term, defn in TERM_DEFS.items():
        esc_defn = defn.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        parts.append(f"""      <div class="glossary-item">
        <span class="glossary-term">{term}</span>
        <span class="glossary-def">{esc_defn}</span>
      </div>""")
    parts.append("""    </div>
  </div>""")

    # ── 页脚 ──────────────────────────────────────
    parts.append(_PAGE_FOOTER.format(gen_time=gen_time))

    # ── 写出文件 ──────────────────────────────────
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))

    print(f"组合报告已生成: {output_path}")
    return output_path


# ══════════════════════════════════════════════════════
# 3. 全链路一键报告
# ══════════════════════════════════════════════════════


def generate_full_chain_report(
    top_n: int = 5,
    output_path: str | None = None,
    mode: str = "quick",
) -> str:
    """一键生成全链路报告：选股 → 分析 → 组合 → 报告

    自动运行选股池、对每只股票进行完整技术分析和量化评分，
    构建等权重组合，生成包含所有详细分析的综合 HTML 报告。

    Parameters
    ----------
    top_n : int
        选股数量，默认 5
    output_path : str or None
        输出路径，默认 reports/fullchain_YYYYMMDD_HHMM.html

    Returns
    -------
    str : 实际保存的文件路径
    """
    if output_path is None:
        output_path = _default_path("fullchain")

    import numpy as np

    from stock_analyzer.analysis import (
        calc_stop_levels,
        calc_support_resistance,
        full_technical_analysis,
        get_technical_summary,
    )
    from stock_analyzer.cache import cached_fundamentals, cached_kline, cached_stock_news
    from stock_analyzer.portfolio import analyze_portfolio, create_portfolio
    from stock_analyzer.quant import (
        calc_risk_metrics,
        composite_quant_score,
        consolidate_signals,
        evaluate_trading_style,
        generate_all_signals,
    )
    from stock_analyzer.screener import run_screener
    from stock_analyzer.sectors_fallback import get_sector_for_code

    now = datetime.now()
    gen_time = now.strftime("%Y-%m-%d %H:%M:%S")

    # 1. 选股
    pool = run_screener(top_n=0, mode=mode)

    if pool.empty:
        parts = [_PAGE_HEADER.format(title="全链路报告")]
        parts.append(f"""  <div class="header">
    <h1>全链路分析报告</h1>
    <div class="meta">生成时间：{gen_time}</div>
  </div>""")
        parts.append("""  <div class="card">
    <div class="empty-state"><div class="icon">&#9888;</div><p>选股池为空，无法生成报告</p></div>
  </div>""")
        parts.append(_PAGE_FOOTER.format(gen_time=gen_time))
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(parts))
        return output_path

    # 2. 对每只股票做完整分析
    stock_details = {}
    portfolio_stocks = []

    for _, row in pool.head(top_n).iterrows():
        code = str(row.get("代码", ""))
        name = str(row.get("名称", code))
        price = float(row.get("最新价", 0))

        try:
            kline = cached_kline(code, days=120)
            kline = full_technical_analysis(kline)

            tech_summary = get_technical_summary(kline)
            sr = calc_support_resistance(kline)
            atr_val = kline.iloc[-1].get("ATR", np.nan) if "ATR" in kline.columns else np.nan
            stop = calc_stop_levels(
                price,
                atr_val,
                sr["支撑位"][0] if sr["支撑位"] else None,
                sr["压力位"][0] if sr["压力位"] else None,
            )
            risk = calc_risk_metrics(kline)
            signals = consolidate_signals(generate_all_signals(kline))

            # 基本面 & 量化评分 & 短线/长线评估
            fundamentals = cached_fundamentals(code)
            quant_score = composite_quant_score(kline, fundamentals)
            trading_style = evaluate_trading_style(kline, fundamentals, risk)
            sector = get_sector_for_code(code)

            # 获取新闻和舆情
            news = cached_stock_news(code)
            news_headlines = news["标题"].head(3).tolist() if "标题" in news.columns else []
            news_summaries = news["摘要"].head(3).tolist() if "摘要" in news.columns else []
            news_times = news["时间"].head(3).tolist() if "时间" in news.columns else []
            news_sources = news["来源"].head(3).tolist() if "来源" in news.columns else []

            stock_details[code] = {
                "name": name,
                "sector": sector,
                "quant_score": quant_score,
                "trading_style": trading_style,
                "support_resistance": sr,
                "stop_levels": stop,
                "technical_summary": tech_summary,
                "risk_metrics": risk,
                "signals": signals,
                "fundamentals": fundamentals,
                "news_headlines": news_headlines,
                "news_summaries": news_summaries,
                "news_times": news_times,
                "news_sources": news_sources,
            }
        except Exception:
            stock_details[code] = {
                "name": name,
                "sector": get_sector_for_code(code),
            }

        portfolio_stocks.append({"code": code, "weight": 1.0 / top_n, "cost": price})

    # 3. 创建组合
    p = create_portfolio("全链路精选组合", portfolio_stocks)
    pr = analyze_portfolio(p)

    # 4. 生成组合报告
    generate_portfolio_report(pr, output_path, stock_details)

    # 5. 注入选股逻辑说明（板块分析 + 个股选择依据）
    total_scanned = 4405 if mode == "full" else 29
    rationale_html = _build_selection_rationale(
        pool, stock_details, total_scanned=total_scanned, top_n=top_n
    )
    if rationale_html:
        with open(output_path, encoding="utf-8") as f:
            content = f.read()
        marker = '<div class="stat-grid">'
        inject_pos = content.find(marker)
        if inject_pos >= 0:
            content = content[:inject_pos] + rationale_html + "\n\n" + content[inject_pos:]
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)

    print(f"全链路报告已生成: {output_path}")
    return output_path
