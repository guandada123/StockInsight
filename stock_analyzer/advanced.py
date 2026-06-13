#!/usr/bin/env python
"""高级分析模块

7 大功能：
  1. 龙虎榜 — 追踪游资/机构上榜动向
  2. 北向资金 — 外资沪深股通流入流出
  3. 融资融券 — 杠杆资金情绪
  4. 高管增减持 — 内部人交易信号
  5. 机构调研 — 机构关注度变化
  6. 财报深度拆解 — 利润质量/现金流分析
  7. 宏观指标 — CPI/PMI/利率与板块关联
"""

import time
from datetime import datetime, timedelta

import pandas as pd

from .cache import _MEM_CACHE, _perm_load, _perm_save


def _cached_perm(table, key, fetch_fn, ttl_seconds):
    """通用永久存储 + 内存缓存包装"""
    mem_key = f"{table}:{key}"
    mem_entry = _MEM_CACHE.get(mem_key)
    if mem_entry is not None and time.time() - mem_entry[0] < min(ttl_seconds, 3600):
        return mem_entry[1]

    stored = _perm_load(table, "key", key)
    if stored is not None:
        conn = __import__("threading").local()
        # Check staleness
        from .cache import _get_conn

        c = _get_conn()
        cur = c.execute(f"SELECT updated_at FROM {table} WHERE key=?", (key,))
        row = cur.fetchone()
        if row and time.time() - row[0] < ttl_seconds:
            _MEM_CACHE[mem_key] = (time.time(), stored)
            return stored

    try:
        data = fetch_fn()
        if data is not None:
            _perm_save(table, "key", key, data)
            _MEM_CACHE[mem_key] = (time.time(), data)
        return data
    except Exception:
        if stored is not None:
            return stored
        return None


# ═══════════════════════════════════════════
# 1. 龙虎榜分析
# ═══════════════════════════════════════════


def get_lhb_detail(date=None):
    """获取指定日期龙虎榜明细"""
    if date is None:
        date = datetime.now().strftime("%Y%m%d")
    try:
        import akshare as ak

        df = ak.stock_lhb_detail_em(date=date)
        if df is not None and not df.empty:
            return df
    except Exception:
        pass
    return pd.DataFrame()


def get_lhb_stock_detail(code, date=None):
    """获取个股龙虎榜上榜记录"""
    if date is None:
        date = datetime.now().strftime("%Y%m%d")
    try:
        import akshare as ak

        df = ak.stock_lhb_stock_detail_date_em(date=date, symbol=code)
        return df
    except Exception:
        return pd.DataFrame()


def analyze_lhb_today():
    """分析当日龙虎榜：净买入TOP10、机构净买TOP10、知名游资动向"""
    df = get_lhb_detail()
    if df.empty:
        return {"error": "龙虎榜数据获取失败"}

    result = {"上榜数量": len(df), "分析时间": datetime.now().isoformat()}

    # 净买入TOP10
    if "净买额" in df.columns:
        top_buy = df.nlargest(10, "净买额")[["代码", "名称", "净买额", "涨幅", "上榜原因"]]
        result["净买入TOP10"] = top_buy.to_dict("records")

    # 净卖出TOP10
    if "净买额" in df.columns:
        top_sell = df.nsmallest(10, "净买额")[["代码", "名称", "净买额", "涨幅", "上榜原因"]]
        result["净卖出TOP10"] = top_sell.to_dict("records")

    return result


# ═══════════════════════════════════════════
# 2. 北向资金
# ═══════════════════════════════════════════


def get_north_flow_summary():
    """北向资金当日流向汇总"""
    try:
        import akshare as ak

        df = ak.stock_hsgt_fund_flow_summary_em()
        return df
    except Exception:
        return pd.DataFrame()


def get_north_hold_stock():
    """北向资金持仓个股（沪股通+深股通重仓）"""
    try:
        import akshare as ak

        # 沪股通
        sh = ak.stock_hsgt_hold_stock_em(symbol="沪股通")
        # 深股通
        sz = ak.stock_hsgt_hold_stock_em(symbol="深股通")
        if sh is not None and sz is not None:
            return pd.concat([sh, sz], ignore_index=True)
        return sh if sh is not None else sz
    except Exception:
        return pd.DataFrame()


def get_north_flow_trend(days=30):
    """北向资金历史流向趋势"""
    try:
        import akshare as ak

        df = ak.stock_hsgt_hist_em(symbol="沪股通")
        if df is not None and not df.empty:
            df = df.tail(days)
        return df
    except Exception:
        return pd.DataFrame()


def north_flow_signal():
    """北向资金信号：连续流入/流出天数、单日净买额"""
    df = get_north_flow_summary()
    if df.empty:
        return {"error": "北向资金数据获取失败"}

    result = {}
    for _, row in df.iterrows():
        name = row.get("名称", "")
        net = row.get("净买额", 0)
        result[name] = {"净买额(亿)": round(float(net) / 1e8, 2) if net else 0}
    return result


# ═══════════════════════════════════════════
# 3. 融资融券
# ═══════════════════════════════════════════


def get_margin_stock_detail(code, days=30):
    """个股融资融券明细"""
    try:
        import akshare as ak

        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        end_date = datetime.now().strftime("%Y%m%d")
        df = ak.stock_margin_detail_sse(date=end_date)
        if df is not None and not df.empty:
            stock = df[df["标的代码"].astype(str).str.zfill(6) == str(code).zfill(6)]
            return stock
    except Exception:
        pass
    return pd.DataFrame()


def get_margin_summary():
    """全市场融资融券汇总（沪深两市）"""
    try:
        import akshare as ak

        sh = ak.macro_china_market_margin_sh()
        sz = ak.macro_china_market_margin_sz()
        if sh is not None and sz is not None:
            result = {
                "沪市": {
                    "融资余额(亿)": float(sh.iloc[-1, 1]) if len(sh) > 0 else 0,
                    "融券余额(亿)": float(sh.iloc[-1, 2]) if len(sh) > 0 and sh.shape[1] > 2 else 0,
                },
                "深市": {
                    "融资余额(亿)": float(sz.iloc[-1, 1]) if len(sz) > 0 else 0,
                    "融券余额(亿)": float(sz.iloc[-1, 2]) if len(sz) > 0 and sz.shape[1] > 2 else 0,
                },
            }
            return result
    except Exception:
        pass
    return {}


# ═══════════════════════════════════════════
# 4. 高管增减持
# ═══════════════════════════════════════════


def get_insider_trades(code=None):
    """高管增减持记录"""
    try:
        import akshare as ak

        if code:
            df = ak.stock_hold_management_detail_em(symbol=code)
        else:
            # 全市场（最近一个月）
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            df = ak.stock_hold_management_detail_em()
            if df is not None and not df.empty and "变动日期" in df.columns:
                df = df[df["变动日期"] >= start_date]
        return df
    except Exception:
        return pd.DataFrame()


def insider_signal(code):
    """个股高管增减持信号：净增持为正、净减持为负"""
    df = get_insider_trades(code)
    if df.empty:
        return {"signal": "无数据", "net_shares": 0}

    signal = "无数据"
    try:
        if "变动数量" in df.columns:
            total = df["变动数量"].sum()
            if total > 0:
                signal = "净增持"
            elif total < 0:
                signal = "净减持"
            return {"signal": signal, "net_shares": int(total), "records": len(df)}
    except Exception:
        pass
    return {"signal": signal, "net_shares": 0}


# ═══════════════════════════════════════════
# 5. 机构调研
# ═══════════════════════════════════════════


def get_institution_visits(code=None, days=30):
    """机构调研记录"""
    try:
        import akshare as ak

        if code:
            df = ak.stock_jgdy_detail_em(symbol=code)
        else:
            df = ak.stock_jgdy_tj_em()
        if df is not None and not df.empty:
            if "调研日期" in df.columns:
                cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
                df = df[df["调研日期"] >= cutoff]
        return df
    except Exception:
        return pd.DataFrame()


def most_visited_stocks(days=30):
    """近期机构调研最多、最密集的股票"""
    df = get_institution_visits(days=days)
    if df.empty or "证券代码" not in df.columns:
        return pd.DataFrame()

    # 按调研次数排名
    code_col = "证券代码"
    name_col = "证券简称" if "证券简称" in df.columns else None
    visit_count = df.groupby(code_col).size().reset_index(name="调研次数")
    visit_count = visit_count.sort_values("调研次数", ascending=False)
    return visit_count.head(20)


# ═══════════════════════════════════════════
# 6. 财报深度拆解
# ═══════════════════════════════════════════


def get_financial_deep(code):
    """财报深度拆解：资产负债表+利润表+现金流"""
    try:
        import akshare as ak

        result = {}

        # 资产负债表
        try:
            bs = ak.stock_balance_sheet_by_report_em(symbol=code)
            if bs is not None and not bs.empty:
                result["资产负债表"] = bs.head(4)  # 最近4个报告期
        except Exception:
            pass

        # 利润表
        try:
            income = ak.stock_profit_sheet_by_report_em(symbol=code)
            if income is not None and not income.empty:
                result["利润表"] = income.head(4)
        except Exception:
            pass

        # 财务摘要
        try:
            abstract = ak.stock_financial_abstract(symbol=code)
            if abstract is not None and not abstract.empty:
                result["财务摘要"] = abstract.head(4)
        except Exception:
            pass

        return result
    except Exception:
        return {}


def analyze_profit_quality(code):
    """利润质量分析"""
    deep = get_financial_deep(code)
    if not deep:
        return {"error": "财报数据获取失败"}

    analysis = {"代码": code}

    # 从财务摘要提取关键指标
    abstract = deep.get("财务摘要")
    if abstract is not None and not abstract.empty:
        latest = abstract.iloc[0]
        analysis["营收(亿)"] = _safe_float(latest.get("营业总收入", 0)) / 1e8
        analysis["净利润(亿)"] = _safe_float(latest.get("归母净利润", 0)) / 1e8
        analysis["净利率%"] = (
            round(analysis["净利润(亿)"] / analysis["营收(亿)"] * 100, 1)
            if analysis["营收(亿)"]
            else 0
        )
        analysis["ROE%"] = _safe_float(latest.get("净资产收益率", 0))
        analysis["毛利率%"] = _safe_float(latest.get("销售毛利率", 0))

    # 利润表趋势
    income = deep.get("利润表")
    if income is not None and not income.empty and len(income) >= 2:
        try:
            latest_rev = _safe_float(income.iloc[0].get("营业总收入", 0))
            prev_rev = _safe_float(income.iloc[-1].get("营业总收入", 0))
            if prev_rev > 0:
                analysis["营收增长%"] = round((latest_rev / prev_rev - 1) * 100, 1)
        except Exception:
            pass

    # 现金流质量
    bs = deep.get("资产负债表")
    if bs is not None and not bs.empty:
        try:
            analysis["资产负债率%"] = _safe_float(bs.iloc[0].get("资产负债率", 0))
        except Exception:
            pass

    analysis["评价"] = _profit_quality_rating(analysis)
    return analysis


def _safe_float(val):
    try:
        return float(val) if val else 0
    except (ValueError, TypeError):
        return 0


def _profit_quality_rating(a):
    """综合利润质量评级"""
    score = 0
    reasons = []
    roe = a.get("ROE%", 0)
    growth = a.get("营收增长%", 0)
    margin = a.get("净利率%", 0)

    if roe > 15:
        score += 3
        reasons.append("ROE优秀")
    elif roe > 8:
        score += 1
        reasons.append("ROE良好")
    else:
        reasons.append("ROE偏低")

    if growth > 20:
        score += 3
        reasons.append("高增长")
    elif growth > 5:
        score += 1
        reasons.append("稳定增长")
    elif growth < 0:
        score -= 2
        reasons.append("营收下滑")

    if margin > 20:
        score += 2
        reasons.append("高利润率")
    elif margin > 10:
        score += 1
        reasons.append("利润率良好")

    if score >= 6:
        return "优秀"
    elif score >= 3:
        return "良好"
    elif score >= 0:
        return "一般"
    return "需关注"


# ═══════════════════════════════════════════
# 7. 宏观指标
# ═══════════════════════════════════════════


def get_macro_indicators():
    import json
    import sqlite3
    from datetime import datetime

    conn = sqlite3.connect("stock_cache.db")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS macro_cache (key TEXT PRIMARY KEY, value TEXT, ts TEXT)"
    )
    cur = conn.execute("SELECT value, ts FROM macro_cache WHERE key=?", ("macro_indicators",))
    row = cur.fetchone()
    if row:
        ts = datetime.fromisoformat(row[1])
        if (datetime.now() - ts).days < 7:
            conn.close()
            return json.loads(row[0])
    conn.close()
    result = _fetch_macro_indicators()
    conn = sqlite3.connect("stock_cache.db")
    conn.execute(
        "INSERT OR REPLACE INTO macro_cache VALUES (?,?,?)",
        ("macro_indicators", json.dumps(result), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return result


def _fetch_macro_indicators():
    """主要宏观指标汇总"""
    result = {}
    try:
        import akshare as ak

        # PMI
        try:
            pmi_mfg = ak.index_pmi_man_cx()
            if pmi_mfg is not None and not pmi_mfg.empty:
                latest = pmi_mfg.iloc[-1]
                result["制造业PMI"] = float(latest.iloc[1]) if len(latest) > 1 else 0
        except Exception:
            result["制造业PMI"] = None

        # CPI
        try:
            cpi = ak.macro_china_cpi_yearly()
            if cpi is not None and not cpi.empty:
                result["CPI同比%"] = float(cpi.iloc[-1, 1]) if cpi.shape[1] > 1 else 0
        except Exception:
            result["CPI同比%"] = None

        # 社会融资
        try:
            social_fin = ak.macro_china_new_financial_credit()
            if social_fin is not None and not social_fin.empty:
                result["社融增量(亿)"] = (
                    float(social_fin.iloc[-1, 1]) if social_fin.shape[1] > 1 else 0
                )
        except Exception:
            result["社融增量(亿)"] = None

        # M2
        try:
            m2 = ak.macro_china_money_supply()
            if m2 is not None and not m2.empty:
                result["M2同比%"] = float(m2.iloc[-1, 1]) if m2.shape[1] > 1 else 0
        except Exception:
            result["M2同比%"] = None

        result["更新时间"] = datetime.now().isoformat()
    except Exception:
        pass

    return result


def macro_market_signal():
    """宏观→市场信号灯"""
    ind = get_macro_indicators()
    if not ind:
        return {"error": "宏观数据获取失败"}

    signals = []
    pmi = ind.get("制造业PMI", 0) or 50
    cpi = ind.get("CPI同比%", 0) or 2
    m2 = ind.get("M2同比%", 0) or 8

    if pmi > 50:
        signals.append("PMI扩张→经济向好")
    elif pmi < 49:
        signals.append("PMI收缩→经济承压")

    if cpi > 3:
        signals.append("CPI高位→通胀压力")
    elif cpi < 0:
        signals.append("CPI为负→通缩风险")

    if m2 > 12:
        signals.append("M2高增→流动性充裕")
    elif m2 < 8:
        signals.append("M2偏低→流动性收紧")

    return {
        "数据": ind,
        "信号": signals,
        "整体": "偏多"
        if len([s for s in signals if "扩张" in s or "充裕" in s]) > len(signals) / 2
        else "偏空",
    }
