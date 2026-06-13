"""每日选股池模块

流程：加载股票池 -> 过滤 ST/退市 -> K线/技术分析 -> 基本面 -> 综合评分 -> 排序输出

支持两种模式：
    1. 快速模式（默认）：使用预设 29 只成分股，1-2 分钟完成
    2. 全市场模式：扫描全部 A 股，先批量实时行情过滤，再对候选股深度分析
"""

import json
import os
import time
from datetime import datetime

import pandas as pd

from .analysis import full_technical_analysis
from .cache import cached_fundamentals, cached_kline, cached_weibo_sentiment
from .fetcher import sina_real_time
from .quant import composite_quant_score

# ── 默认股票池（沪深300 + 中证500 代表）─────────────
DEFAULT_POOL = {
    "300408",
    "603005",
    "600519",
    "000858",
    "000333",
    "002415",
    "300750",
    "601318",
    "600036",
    "000651",
    "002594",
    "300059",
    "600887",
    "600585",
    "000725",
    "002475",
    "300124",
    "600309",
    "601166",
    "600900",
    "000568",
    "002304",
    "600809",
    "603259",
    "300015",
    "002230",
    "300782",
    "688981",
    "688036",
}

# ── 全A股列表缓存路径 ─────────────────────────────────
_STOCK_LIST_CACHE = os.path.join(os.path.dirname(__file__), "..", "stock_list_cache.json")


def load_all_a_shares(force_refresh=False):
    """获取全部 A 股代码列表（akshare），结果缓存到 JSON

    参数:
        force_refresh: True 则强制重新从 akshare 拉取
    返回:
        list[str]: 全 A 股代码列表
    """
    # 读缓存
    if not force_refresh and os.path.exists(_STOCK_LIST_CACHE):
        try:
            with open(_STOCK_LIST_CACHE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # 从 akshare 拉取
    try:
        import akshare as ak

        print("  正在从 akshare 获取全 A 股列表...")
        df = ak.stock_info_a_code_name()
        codes = df["code"].astype(str).str.zfill(6).tolist()
        # 缓存到文件
        os.makedirs(os.path.dirname(_STOCK_LIST_CACHE) or ".", exist_ok=True)
        with open(_STOCK_LIST_CACHE, "w", encoding="utf-8") as f:
            json.dump(codes, f)
        print(f"  获取完成，共 {len(codes)} 只股票")
        return codes
    except Exception as e:
        print(f"  获取全 A 股失败: {e}，回退使用默认池")
        return list(DEFAULT_POOL)


def quick_filter(
    codes,
    min_price=5,
    max_price=500,
    exclude_st=True,
    exclude_bj=True,
    min_volume=1_000_000,
    batch_size=500,
):
    """快速批量过滤：仅使用实时行情（无需下载 K 线）

    通过 sina_real_time 分批查询所有股票的实时行情
    （每批 500 只），按价格/成交量/板块/ST 等条件过滤。

    参数:
        codes: 股票代码列表
        min_price: 最低价格，默认 5
        max_price: 最高价格
        exclude_st: 是否排除 ST/退市
        exclude_bj: 是否排除北交所（8 开头）
        min_volume: 最低成交量（股），默认 100 万股
        batch_size: 每批查询数量，默认 500
    返回:
        list[str]: 过滤后的股票代码列表
    """
    print(f"  快速过滤 {len(codes)} 只股票（实时行情分批查询）...")

    rt_all = {}
    for i in range(0, len(codes), batch_size):
        batch = codes[i : i + batch_size]
        rt_all.update(sina_real_time(batch))
        if (i // batch_size) % 5 == 0:
            print(f"    已查询 {min(i + batch_size, len(codes))}/{len(codes)}...")

    if not rt_all:
        print("  实时行情获取失败，跳过过滤")
        return codes

    valid = []
    for code in codes:
        info = rt_all.get(code)
        if not info:
            continue
        name = info.get("名称", "")
        if exclude_bj and code.startswith("8"):
            continue
        if exclude_st and ("ST" in name or "退" in name):
            continue
        price = info.get("最新价")
        if price is None or price == 0:
            continue
        if min_price > 0 and price < min_price:
            continue
        if max_price > 0 and price > max_price:
            continue
        if min_volume > 0:
            volume = info.get("成交量", 0)
            if volume < min_volume:
                continue
        valid.append(code)

    conds = []
    if exclude_st:
        conds.append("排除ST")
    if exclude_bj:
        conds.append("排除北交所")
    conds.append(f"价格{min_price}-{max_price}")
    if min_volume > 0:
        conds.append(f"成交量>{min_volume / 10000:.0f}万")
    print(f"  过滤后剩余 {len(valid)} 只（{'/'.join(conds)}）")
    return valid


def load_stock_pool(source=None, use_all_a_shares=False, quick_filter_args=None):
    """加载股票池

    参数:
        source: None 返回默认池；str 路径则从 JSON 文件加载
        use_all_a_shares: True 则返回全 A 股列表（会先做快速过滤）
        quick_filter_args: dict，传给 quick_filter 的参数
                          {min_price, max_price, exclude_st, exclude_bj}
                          仅在 use_all_a_shares=True 时生效
    返回:
        list[str]
    """
    if use_all_a_shares:
        all_codes = load_all_a_shares()
        qf_args = {"min_price": 5, "max_price": 500, "exclude_st": True, "exclude_bj": True}
        if quick_filter_args:
            qf_args.update(quick_filter_args)
        return quick_filter(all_codes, **qf_args)

    if source is not None:
        try:
            with open(source, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                codes = set(data)
            elif isinstance(data, dict) and "codes" in data:
                codes = set(data["codes"])
            else:
                print("  无法识别的 JSON 格式（期待 list 或 dict[codes]），使用默认池")
                codes = set(DEFAULT_POOL)
            print(f"  从文件加载股票池: {len(codes)} 只")
            return codes
        except FileNotFoundError:
            print(f"  文件不存在 {source}，使用默认池")
        except Exception as e:
            print(f"  加载股票池失败 {source}: {e}，使用默认池")
    return set(DEFAULT_POOL)


def get_stock_name(code, rt_cache=None):
    """获取股票名称，优先从实时行情缓存中查找"""
    if rt_cache and code in rt_cache:
        return rt_cache[code].get("名称", "")
    # 兜底：通过新浪实时行情 API 查询
    rt = sina_real_time([code])
    if code in rt:
        return rt[code].get("名称", "")
    return ""


def three_layer_funnel(candidates, top_n=10):
    """三层漏斗选股：借鉴 alphasift 架构

    L1 硬筛：价格/量能/板块 → 过滤不合格
    L2 多因子：量化评分 + 组合信号 + 共振 → 排序
    L3 NL终审：多空辩论确认 → 最终推荐

    Args:
        candidates: list of dict, 每个包含 code/name/score/signal/resonance
        top_n: 最终输出数量

    Returns:
        dict with L1/L2/L3 counts and final picks
    """
    from .cache import cached_kline
    from .short_term import calc_combo_signals, calc_multi_timeframe_resonance

    l1_passed = []
    l2_scored = []
    final_picks = []

    for c in candidates:
        code = c.get("code", "")
        # L1: 硬筛
        price = c.get("price", 0)
        score = c.get("score", 0)
        if price < 5 or score < 45:
            continue
        l1_passed.append(c)

    # L2: 多因子排序
    for c in l1_passed:
        try:
            kline = cached_kline(c.get("code", ""))
            if kline is not None and not kline.empty:
                combo = calc_combo_signals(kline, c.get("code"))
                mr = calc_multi_timeframe_resonance(c.get("code", ""))
                c["combo_signal"] = combo.get("信号", "?")
                c["combo_strength"] = combo.get("强度", 0)
                c["resonance"] = mr.get("共振强度", 0)
                c["resonance_status"] = mr.get("状态", "?")
                # 综合排序分
                c["funnel_score"] = (
                    c.get("score", 50) * 0.4
                    + max(combo.get("强度", 0) + 4, 0) / 8 * 100 * 0.35
                    + max(mr.get("共振强度", 0) + 60, 0) / 120 * 100 * 0.25
                )
            else:
                c["funnel_score"] = c.get("score", 50)
        except Exception:
            c["funnel_score"] = c.get("score", 50)
        l2_scored.append(c)

    # 按 funnel_score 排序
    l2_scored.sort(key=lambda x: x.get("funnel_score", 0), reverse=True)

    # L3: NL终审 — 取Top N，多空辩论不通过的降级
    for c in l2_scored[: top_n * 2]:
        combo_str = c.get("combo_strength", 0)
        reso = c.get("resonance", 0)
        if combo_str >= 2 and reso > -20:
            final_picks.append(c)
        if len(final_picks) >= top_n:
            break

    return {
        "L1_硬筛通过": len(l1_passed),
        "L2_多因子排序": len(l2_scored),
        "L3_NL终审": len(final_picks),
        "最终推荐": final_picks,
    }


def run_screener(pool=None, top_n=30, mode="quick", use_sentiment=True):
    """执行每日选股扫描

    对每只股票依次调用:
        cached_kline() → full_technical_analysis() → cached_fundamentals() → composite_quant_score()

    参数:
        pool: 股票池 iterable，默认使用 DEFAULT_POOL
              传入 "all" 或 "full" 使用全市场扫描模式
        top_n: 返回前 N 名（按综合评分降序），0 或 None 返回全部
        mode: "quick"（默认，使用预设池）或 "full"（全市场扫描，会先快速过滤）
        use_sentiment: True（默认）纳入舆情因子；False 跳过舆情，权重重新归一化到五因子

    返回:
        pd.DataFrame，字段: 序号/代码/名称/综合评分/评级/动量分/技术分/基本面分/
                            量能分/风险分/舆情分/最新价/涨跌幅
    """
    # ── 确定股票池 ──────────────────────────────────
    if pool is None:
        if mode == "full":
            pool = load_stock_pool(use_all_a_shares=True)
        else:
            pool = DEFAULT_POOL
    elif isinstance(pool, str) and pool.lower() in ("all", "full"):
        pool = load_stock_pool(use_all_a_shares=True)

    pool = list(pool)
    print(f"股票池共 {len(pool)} 只，正在获取实时行情以过滤 ST/退市...")
    if len(pool) > 100:
        print(
            f"  （全市场模式：先快速过滤再逐只深度分析，预计 {len(pool) * 0.1 / 60:.0f}-{len(pool) * 1.5 / 60:.0f} 分钟）"
        )

    # ── 第一步：批量获取实时行情，过滤 ST / 退市 ──
    # 股票数量多时分批查询，防止 URL 超长
    rt_all = {}
    if len(pool) > 500:
        for i in range(0, len(pool), 500):
            batch = pool[i : i + 500]
            rt_all.update(sina_real_time(batch))
            if (i // 500) % 5 == 0:
                print(f"    已查询实时行情 {min(i + 500, len(pool))}/{len(pool)}...")
    else:
        rt_all = sina_real_time(pool)

    valid_codes = []
    for code in pool:
        info = rt_all.get(code)
        if not info:
            continue
        name = info.get("名称", "")
        if "ST" in name or "退" in name:
            continue
        valid_codes.append(code)

    print(f"  有效股票: {len(valid_codes)} 只\n")

    # ── 第二步：预取舆情数据（仅一次，全市场通用） ──
    sentiment_map = {}  # name→rate 的 dict，O(1) 查找替代 DataFrame 扫描
    if use_sentiment:
        print("  获取微博舆情数据...")
        sentiment_df = cached_weibo_sentiment()
        has_sentiment = sentiment_df is not None and not sentiment_df.empty
        if has_sentiment:
            print(f"  微博舆情数据获取完成，覆盖 {len(sentiment_df)} 只股票")
            if "name" in sentiment_df.columns and "rate" in sentiment_df.columns:
                sentiment_map = dict(zip(sentiment_df["name"], sentiment_df["rate"]))
        else:
            print("  微博舆情数据不可用，跳过")
    else:
        sentiment_df = None
        has_sentiment = False
        print("  跳过舆情因子")

    # ── 第三步：逐只分析 ──
    results = []
    total = len(valid_codes)
    t_start = time.time()

    for idx, code in enumerate(valid_codes):
        print(f"  [{idx + 1}/{total}] {code}...", end=" ")
        try:
            # 1. K 线数据
            kline = cached_kline(code, days=120)
            if kline.empty or len(kline) < 20:
                print("K 线数据不足，跳过")
                time.sleep(0.05)
                continue

            # 2. 技术指标计算
            kline = full_technical_analysis(kline)

            # 3. 基本面
            fundamentals = cached_fundamentals(code)

            # 4. 舆情评分（O(1) dict 查找替代 O(n) DataFrame 扫描）
            sentiment_score = None
            if sentiment_map and code in rt_all:
                name = rt_all[code].get("名称", "")
                if name and name in sentiment_map:
                    rate = float(sentiment_map[name])
                    sentiment_score = round(50 + rate * 40, 1)

            # 5. 综合评分
            quant = composite_quant_score(kline, fundamentals, sentiment_score=sentiment_score)

            # 6. 实时行情信息（最新价 / 涨跌幅）
            rt = rt_all.get(code, {})
            price = rt.get("最新价")
            if price is None:
                price = round(float(kline["收盘"].iloc[-1]), 2)
            change = rt.get("涨跌幅")
            if change is None:
                change = (
                    round(float(kline["涨跌幅"].iloc[-1]), 2) if "涨跌幅" in kline.columns else 0.0
                )

            # 提取各因子分
            fs = quant.get("factor_scores", {})

            results.append(
                {
                    "代码": code,
                    "名称": rt.get("名称", ""),
                    "综合评分": quant["composite_score"],
                    "评级": quant["rating"],
                    "动量分": fs.get("momentum", {}).get("score", 0),
                    "技术分": fs.get("technical", {}).get("score", 0),
                    "基本面分": fs.get("fundamental", {}).get("score", 0),
                    "量能分": fs.get("volume", {}).get("score", 0),
                    "风险分": fs.get("risk", {}).get("score", 0),
                    "舆情分": fs.get("sentiment", {}).get("score", 50),
                    "最新价": price,
                    "涨跌幅": change,
                }
            )
            print(f"评分 {quant['composite_score']:.0f}/100  {quant['rating']}")

        except Exception as e:
            print(f"失败: {e}")

    elapsed = time.time() - t_start
    print()

    if not results:
        print("无有效分析结果")
        return pd.DataFrame()

    df = pd.DataFrame(results)
    df = df.sort_values("综合评分", ascending=False).reset_index(drop=True)
    df.insert(0, "序号", range(1, len(df) + 1))

    if top_n and 0 < top_n < len(df):
        df = df.head(top_n)

    print(f"选股完成，返回 {len(df)} 只结果（耗时 {elapsed:.0f} 秒）")
    return df


def filter_by_conditions(df, min_price=5, min_score=0):
    """按价格和评分过滤

    参数:
        df: run_screener 返回的 DataFrame
        min_price: 最低价格过滤（<=0 时不限）
        min_score: 最低综合评分（<=0 时不限）
    返回:
        pd.DataFrame
    """
    if df.empty:
        return df

    # 移除已有序号列，避免重复插入
    df = df.drop(columns=["序号"], errors="ignore")

    mask = pd.Series(True, index=df.index)
    if min_price > 0:
        mask &= df["最新价"] >= min_price
    if min_score > 0:
        mask &= df["综合评分"] >= min_score

    result = df[mask].copy()
    if not result.empty:
        result.insert(0, "序号", range(1, len(result) + 1))
    return result


def save_screener_result(df, path=None):
    """将选股结果保存为 JSON

    参数:
        df: run_screener 返回的 DataFrame
        path: 输出路径，默认 reports/screener_YYYYMMDD.json
    返回:
        str: 实际保存路径
    """
    if path is None:
        today = datetime.now().strftime("%Y%m%d")
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "reports", f"screener_{today}.json"
        )

    os.makedirs(os.path.dirname(path), exist_ok=True)

    data = {
        "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "股票数量": len(df),
        "股票列表": df.to_dict(orient="records"),
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"选股结果已保存至: {path}")
    return path
