"""HTML 报告生成 — 工具函数与术语常量

从 report_html.py 拆分而来，包含所有辅助工具函数和 TERM_DEFS 术语表。
"""

import os
from datetime import datetime

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


# ── 术语解释 ──────────────────────────────────────

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


def _tip(label: str, term_key: str | None = None) -> str:
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
