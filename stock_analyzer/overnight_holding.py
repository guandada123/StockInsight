"""
一夜持股法 — 尾盘选股 + 隔夜卖出模块

六步筛选法：
  Step 1: 涨幅 3%-5%（当日强势但不追高）
  Step 2: 量比 > 1（活跃度过滤）
  Step 3: 换手率 5%-15%（关注度适中，排除出货嫌疑）
  Step 4: 流通市值 50-200亿（盘子适中，可被短线资金拉动）
  Step 5: 涨停基因（20日内有涨停板）
  Step 6: K线多头排列 + 均线发散

卖出铁律：
  - 第二天早盘10点前必须清仓
  - 高开1-5%: 冲高拐头/放量滞涨→止盈
  - 平开/低开: 反弹至成本线附近→分批离场
  - 低开低走 -2%~-3%: 无条件止损
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from .analysis import calc_ma
from .cache import cached_kline
from .fetcher import _get_em_session, sina_real_time

# ── 数据获取层 ──────────────────────────────────────


def _get_mainboard_codes():
    """获取所有主板股票代码列表（60/00开头）"""
    from .fetcher import _load_stock_name_map

    name_map = _load_stock_name_map()
    return sorted([c for c in name_map if c.startswith(("60", "00"))])


def _batch_sina_quotes(codes, batch_size=300):
    """批量拉取新浪实时行情（涨幅、成交量、成交额）"""
    results = {}
    for i in range(0, len(codes), batch_size):
        batch = codes[i : i + batch_size]
        try:
            rt = sina_real_time(batch)
            results.update(rt)
        except Exception:
            pass
        # 小延迟避免被限流（>10只才有速率限制）
        if len(batch) > 10 and i + batch_size < len(codes):
            time.sleep(0.15)
    return results


def _em_quote_batch(codes, max_workers=15):
    """并行拉取东方财富个股实时行情（量比/换手率/流通市值）

    使用 push2 stock/get 接口，trust_env=False 直连。
    字段映射：f50=量比, f167=换手率, f116=流通市值, f170=涨跌幅,
              f43=最新价, f44=最高, f45=最低, f48=成交额, f47=成交量
    """
    session = _get_em_session()
    fields = "f43,f44,f45,f47,f48,f50,f57,f58,f116,f167,f168,f170"

    def fetch_one(code):
        prefix = "1." if code.startswith("6") else "0."
        try:
            r = session.get(
                "http://push2.eastmoney.com/api/qt/stock/get",
                params={
                    "secid": prefix + code,
                    "fields": fields,
                    "fltt": 2,
                },
                timeout=5,
            )
            if r.status_code == 200:
                d = r.json().get("data")
                if d:
                    return code, {
                        "量比": d.get("f50", 0) or 0,
                        "换手率": d.get("f167", 0) or 0,
                        "流通市值": d.get("f116", 0) or 0,
                        "涨跌幅": d.get("f170", 0) or 0,
                        "最新价": d.get("f43", 0) or 0,
                        "最高": d.get("f44", 0) or 0,
                        "最低": d.get("f45", 0) or 0,
                        "成交额": d.get("f48", 0) or 0,
                        "成交量": d.get("f47", 0) or 0,
                        "振幅": d.get("f168", 0) or 0,
                        "名称": d.get("f58", ""),
                    }
        except Exception:
            pass
        return code, None

    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(fetch_one, c): c for c in codes}
        for f in as_completed(futures):
            code, data = f.result()
            if data:
                results[code] = data
    return results


# ── 降级方案：K线推算量比/换手率/市值（EM不可用时） ──


def _calc_amplitude(data):
    """计算日内振幅：(最高-最低)/昨收*100"""
    high = data.get("最高", 0)
    low = data.get("最低", 0)
    yclose = data.get("昨收", 0)
    if high and low and yclose and high > low:
        return round((high - low) / yclose * 100, 1)
    return data.get("振幅", 0)


def _kline_fallback_batch(codes, sina_data):
    """用K线数据批量推算量比、换手率、流通市值

    量比 = today_volume / avg_5d_volume
    换手率 = today_volume / floatShare (floatShare from baostock)
    流通市值 = price * floatShare
    """
    results = {}
    # 用于缓存floatShare避免重复baostock查询
    _float_share_cache: dict[str, float] = {}

    for code in codes:
        try:
            sina = sina_data.get(code, {})
            today_vol = sina.get("成交量", 0)
            price = sina.get("最新价", 0)
            if not today_vol or not price:
                continue

            df = cached_kline(code, days=30)
            if df is None or len(df) < 10:
                continue

            # 量比: today / avg_5d (skip today's K-line which is yesterday)
            avg_5d_vol = df["成交量"].tail(6).head(5).mean()
            vol_ratio = today_vol / avg_5d_vol if avg_5d_vol > 0 else 1.0

            # 换手率 + 流通市值: from floatShare
            turnover = 0
            market_cap = 0
            float_share = _get_float_share(code, df, _float_share_cache)
            if float_share > 0:
                turnover = today_vol / float_share * 100
                market_cap = price * float_share

            results[code] = {
                "量比": round(vol_ratio, 2),
                "换手率": round(turnover, 1),
                "流通市值": market_cap,
                "涨跌幅": sina.get("涨跌幅", 0),
                "最新价": price,
                "最高": sina.get("最高", 0),
                "最低": sina.get("最低", 0),
                "成交额": sina.get("成交额", 0),
                "成交量": today_vol,
                "振幅": _calc_amplitude(sina),
                "名称": sina.get("名称", ""),
            }
        except Exception:
            continue

    return results


def _get_float_share(code, df, cache_dict):
    """获取流通股本：先从K线反推，失败则用baostock"""
    if code in cache_dict:
        return cache_dict[code]

    # 方法1: 从K线振幅+成交额反推
    float_share = _estimate_float_share_from_kline(df)

    # 方法2: baostock
    if float_share <= 0:
        float_share = _get_float_share_from_baostock(code)

    cache_dict[code] = float_share
    return float_share


def _estimate_float_share_from_kline(df):
    """从K线粗略估算流通股本 — 用日成交额/价格/换手率关系"""
    try:
        # 最近20天平均成交额 / 平均价格 / 平均预期换手率
        avg_amount = df["成交额"].tail(20).mean()
        avg_price = df["收盘"].tail(20).mean()
        if avg_amount > 0 and avg_price > 0:
            # 假设日均换手2% → floatShare = avg_amount/avg_price / 0.02
            return avg_amount / avg_price / 0.02
    except Exception:
        pass
    return 0


def _get_float_share_from_baostock(code):
    """从baostock查询最新日期的turn+volume反推floatShare"""
    try:
        import baostock as bs

        symbol = "sh." + code if code.startswith("6") else "sz." + code
        # 使用全局单例baostock连接
        if not hasattr(_get_float_share_from_baostock, "_logged_in"):
            bs.login()
            _get_float_share_from_baostock._logged_in = True  # type: ignore[attr-defined]

        from datetime import datetime

        end_date = datetime.now().strftime("%Y-%m-%d")
        rs = bs.query_history_k_data_plus(
            symbol,
            "date,turn,volume",
            start_date="2026-01-01",
            end_date=end_date,
            frequency="d",
            adjustflag="1",
        )
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        if rows:
            last = rows[-1]
            vol = float(last[2])
            turn = float(last[1])
            if turn > 0:
                return vol / (turn / 100)
    except Exception:
        pass
    return 0


# ── 六步筛选 ────────────────────────────────────────


def _step1_gain_filter(stocks):
    """Step 1: 涨幅 3%-5%"""
    return {c: d for c, d in stocks.items() if 3 <= d.get("涨跌幅", 0) <= 5}


def _step2_volume_ratio(stocks, min_vr=1.0):
    """Step 2: 量比 > min_vr"""
    return {c: d for c, d in stocks.items() if d.get("量比", 0) > min_vr}


def _step3_turnover(stocks, t_min=5, t_max=15):
    """Step 3: 换手率 5%-15%"""
    return {c: d for c, d in stocks.items() if t_min <= d.get("换手率", 0) <= t_max}


def _step4_market_cap(stocks, cap_min=50, cap_max=200):
    """Step 4: 流通市值 50-200亿"""
    return {
        c: d for c, d in stocks.items() if cap_min * 1e8 <= d.get("流通市值", 0) <= cap_max * 1e8
    }


def _has_limit_up_in_days(code, days=20):
    """检测过去N日是否有涨停板（>=9.8%且收在最高价附近）"""
    try:
        df = cached_kline(code, days=days)
        if df is None or len(df) < 5:
            return False
        gains = df["涨跌幅"].tail(days).values
        return any(g >= 9.8 for g in gains)
    except Exception:
        return False


def _step5_limit_up_gene(candidates):
    """Step 5: 涨停基因 — 20日内有涨停"""
    results = {}
    for code in candidates:
        if _has_limit_up_in_days(code, 20):
            results[code] = candidates[code]
    return results


def _check_bullish_alignment(code):
    """检查均线多头排列：MA5 > MA10 > MA20"""
    try:
        df = cached_kline(code, days=120)
        if df is None or len(df) < 60:
            return False, None

        df = calc_ma(df, [5, 10, 20])
        last = df.iloc[-1]
        ma5, ma10, ma20 = last.get("MA5", 0), last.get("MA10", 0), last.get("MA20", 0)

        if not (ma5 and ma10 and ma20):
            return False, None

        aligned = float(ma5) > float(ma10) > float(ma20)

        # 成交量温和放大：近5日均量 > 近20日均量
        vol_5d = df["成交量"].tail(5).mean()
        vol_20d = df["成交量"].tail(20).mean()
        vol_expanding = vol_5d > vol_20d * 1.1 if vol_20d > 0 else False

        return aligned and vol_expanding, {
            "ma5": round(float(ma5), 2),
            "ma10": round(float(ma10), 2),
            "ma20": round(float(ma20), 2),
            "vol_ratio": round(float(vol_5d / vol_20d), 2) if vol_20d > 0 else 0,
        }
    except Exception:
        return False, None


def _price_filter(stocks, min_price=10, max_price=80):
    """价格过滤：主板10-80元"""
    return {c: d for c, d in stocks.items() if min_price <= d.get("最新价", 0) <= max_price}


def _step6_kline_pattern(candidates):
    """Step 6: K线形态 — 均线多头排列 + 成交量温和放大"""
    results = {}
    for code, data in candidates.items():
        ok, ma_info = _check_bullish_alignment(code)
        if ok:
            data["均线"] = ma_info
            results[code] = data
    return results


# ── 纪律验证层 ──────────────────────────────────────


def _check_20d_gain(code, rt_price=None):
    """检查近20日涨幅 — 用实时价+历史K线，不用缓存价

    Args:
        code: 股票代码
        rt_price: 实时价格（来自Sina），None则用K线最新收盘价
    """
    try:
        df = cached_kline(code, days=30)
        if df is None or len(df) < 21:
            return None
        close_now = rt_price if rt_price and rt_price > 0 else df.iloc[-1]["收盘"]
        close_20d = df.iloc[-21]["收盘"]
        close_5d = df.iloc[-6]["收盘"]
        gain = (close_now - close_20d) / close_20d * 100
        gain_5d = (close_now - close_5d) / close_5d * 100
        return {"20日涨幅": round(gain, 1), "近5日涨幅": round(gain_5d, 1)}
    except Exception:
        return None


def _validate_discipline(code, data, verbose=False):
    """对单只候选执行纪律验证

    Returns:
        dict: {'通过': bool, '淘汰原因': str, '组合信号': {}, '短线评分': {}, '20日涨幅': x, '主力': {}}
    """
    result = {
        "通过": True,
        "淘汰原因": "",
        "组合信号": {},
        "短线评分": 0,
        "20日涨幅": 0,
        "近5日涨幅": 0,
        "主力": {},
    }

    # 1. 20日涨幅红线检查（>=30%淘汰）— 用实时价
    rt_price = data.get("最新价", 0)
    gain_info = _check_20d_gain(code, rt_price=rt_price)
    if gain_info:
        result["20日涨幅"] = gain_info["20日涨幅"]
        result["近5日涨幅"] = gain_info["近5日涨幅"]
        if gain_info["20日涨幅"] >= 30:
            result["通过"] = False
            result["淘汰原因"] = f"20日涨幅{gain_info['20日涨幅']:.1f}%超过30%红线"
            return result

    # 2. 振幅确认（<3%淘汰）
    amp = data.get("振幅", 0)
    if amp < 3:
        result["通过"] = False
        result["淘汰原因"] = f"振幅{amp:.1f}%不足3%"
        return result

    # 3. 组合信号检查
    try:
        from .short_term import calc_combo_signals, short_term_score

        kline = cached_kline(code, days=120)
        if kline is not None and len(kline) >= 60:
            combo = calc_combo_signals(kline, code)
            result["组合信号"] = combo
            ss = short_term_score(kline, code)
            result["短线评分"] = ss.get("短线评分", 0)

            # 组合信号强度<-2淘汰
            strength = combo.get("强度", 0)
            if strength <= -2:
                result["通过"] = False
                result["淘汰原因"] = f"组合信号强度{strength}偏空"
                return result
    except Exception:
        pass

    # 4. 主力资金标记（不淘汰）
    try:
        from .short_term import calc_fund_flow_summary

        ff = calc_fund_flow_summary(code, days=5)  # type: ignore[call-arg]
        result["主力"] = ff
    except Exception:
        pass

    return result


def _batch_validate_discipline(candidates, verbose=False):
    """批量纪律验证 — 淘汰红线违规+标记警告"""
    passed = {}
    eliminated = []

    for code, data in candidates.items():
        check = _validate_discipline(code, data, verbose)
        if check["通过"]:
            data["纪律"] = check
            passed[code] = data
        else:
            eliminated.append((code, data.get("名称", ""), check["淘汰原因"]))

    if verbose and eliminated:
        print(f"\n  🚫 纪律淘汰 ({len(eliminated)}只):")
        for code, name, reason in eliminated:
            print(f"     {code} {name}: {reason}")

    return passed


def _compute_overnight_score_v2(data):
    """一夜持股综合评分 v2 — 含纪律因子

    权重：
    - 一夜基础(55%): 量比+换手率+振幅+涨幅位置+均线
    - 组合信号(20%): 信号强度映射(-4~+4 → 0~20)
    - 短线评分(15%): short_term_score 归一化
    - 追高惩罚(-20~0): 20日>25%→-5, >28%→-10; 近5日>15%→-5
    """
    score = 0

    # 一夜基础分(55分)
    vr = data.get("量比", 0)
    score += min(18, vr / 3 * 18)  # 量比 18%

    turnover = data.get("换手率", 0)
    if 8 <= turnover <= 12:
        score += 12
    elif 5 <= turnover <= 15:
        score += max(6, 12 - min(abs(turnover - 8), abs(turnover - 12)) * 3)

    amp = data.get("振幅", 0)
    score += min(10, amp / 8 * 10)  # 振幅 10%

    gain = data.get("涨跌幅", 0)
    if 3 <= gain <= 3.5:
        score += 10
    elif 3.5 < gain <= 5:
        score += max(3, 10 - (gain - 3.5) * 5)

    ma = data.get("均线", {})
    if ma and ma.get("ma5", 0) > ma.get("ma10", 0) > ma.get("ma20", 0):
        score += 8
        if ma.get("vol_ratio", 0) > 1.2:
            score += 3

    # 组合信号加分(20分) — 强度-4~+4映射到0~20
    discipline = data.get("纪律", {})
    combo = discipline.get("组合信号", {})
    signal_strength = combo.get("强度", 0)
    score += max(0, (signal_strength + 4) * 2.5)  # 强度-4→0, 0→10, +4→20

    # 短线评分加分(15分)
    ss = discipline.get("短线评分", 0)
    score += min(15, ss / 100 * 15)

    # 追高惩罚
    gain_20d = discipline.get("20日涨幅", 0)
    if gain_20d > 28:
        score -= 10
    elif gain_20d > 25:
        score -= 5

    gain_5d = discipline.get("近5日涨幅", 0)
    if gain_5d > 15:
        score -= 5

    return max(0, round(min(100, score)))


# ── 主力入口 ────────────────────────────────────────


def run_overnight_scan(top_n=20, min_price=10, max_price=80, verbose=True):
    """一夜持股法六步筛选主函数

    Args:
        top_n: 返回前N只
        min_price: 最低价格（默认10）
        max_price: 最高价格（默认80）

    Returns:
        list[dict]: 候选股票列表，按综合评分降序排列
    """
    t_start = time.time()

    # ── Phase 1: 获取所有主板股票 ──
    if verbose:
        print("【一夜持股法】尾盘选股扫描")
        print(f"  启动时间: {datetime.now().strftime('%H:%M:%S')}\n")

    all_codes = _get_mainboard_codes()
    if verbose:
        print(f"  📡 主板股票池: {len(all_codes)} 只")

    # ── Phase 2: 新浪批量拉涨幅 ──
    t1 = time.time()
    sina_data = _batch_sina_quotes(all_codes)
    n_sina = len(sina_data)
    if verbose:
        print(f"  ✓ 新浪行情拉取: {n_sina} 只 ({time.time() - t1:.1f}s)")

    # ── Phase 3: Step 1 — 涨幅 3-5% ──
    candidates = _step1_gain_filter(sina_data)
    if verbose:
        print(f"  📊 Step1 涨幅3%-5%: {len(candidates)} 只通过")

    if not candidates:
        if verbose:
            print("\n  ⚠️ 无股票通过Step1，今日不适合一夜持股。")
        return []

    # ── 价格过滤 ──
    candidates = _price_filter(candidates, min_price, max_price)
    if verbose:
        print(f"  📊 价格{min_price}-{max_price}元: {len(candidates)} 只通过")

    if not candidates:
        if verbose:
            print("\n  ⚠️ 无股票通过价格过滤。")
        return []

    # ── Phase 4: EM拉量比/换手率/市值，失败则K线降级 ──
    t2 = time.time()
    candidate_codes = list(candidates.keys())
    em_data = _em_quote_batch(candidate_codes)

    # 合并EM数据
    em_hit = 0
    for code, edata in em_data.items():
        if code in candidates:
            candidates[code].update(edata)
            em_hit += 1

    # 降级：EM覆盖率<50%时，K线推算缺失数据
    coverage = em_hit / len(candidate_codes) * 100 if candidate_codes else 0
    if coverage < 50:
        if verbose:
            print(f"  ⚠️ EM覆盖率仅{coverage:.0f}%，启动K线推算降级...")
        fallback = _kline_fallback_batch(candidate_codes, sina_data)
        fb_hit = 0
        for code, fdata in fallback.items():
            if code in candidates and candidates[code].get("量比", 0) == 0:
                candidates[code].update(fdata)
                fb_hit += 1
        if verbose:
            print(f"  ✓ K线推算补充: {fb_hit} 只 (量比/换手/市值)")
    elif verbose:
        print(f"  ✓ 东方财富详情拉取: {em_hit} 只 ({time.time() - t2:.1f}s)")

    # 修正振幅：EM或K线未提供时，从最高/最低/昨收计算
    for code, data in candidates.items():
        if data.get("振幅", 0) == 0:
            data["振幅"] = _calc_amplitude(data)
        # 确保昨收有值（从sina补）
        if data.get("昨收", 0) == 0 and code in sina_data:
            data["昨收"] = sina_data[code].get("昨收", 0)

    # ── Phase 5: Steps 2-4 过滤 ──
    n_before = len(candidates)
    candidates = _step2_volume_ratio(candidates, min_vr=1.0)
    if verbose:
        print(f"  📊 Step2 量比>1: {len(candidates)} 只 (淘汰{n_before - len(candidates)})")

    n_before = len(candidates)
    candidates = _step3_turnover(candidates)
    if verbose:
        print(f"  📊 Step3 换手率5-15%: {len(candidates)} 只 (淘汰{n_before - len(candidates)})")

    n_before = len(candidates)
    candidates = _step4_market_cap(candidates)
    if verbose:
        print(
            f"  📊 Step4 流通市值50-200亿: {len(candidates)} 只 (淘汰{n_before - len(candidates)})"
        )

    if not candidates:
        if verbose:
            print("\n  ⚠️ 无股票通过Step4，今日不适合一夜持股。")
        return []

    # ── Phase 6: Steps 5-6 K线分析 ──
    t3 = time.time()
    n_before = len(candidates)
    candidates = _step5_limit_up_gene(candidates)
    if verbose:
        print(f"  📊 Step5 涨停基因: {len(candidates)} 只 (淘汰{n_before - len(candidates)})")

    n_before = len(candidates)
    candidates = _step6_kline_pattern(candidates)
    if verbose:
        print(f"  📊 Step6 K线多头+放量: {len(candidates)} 只 (淘汰{n_before - len(candidates)})")

    # ── Phase 7: 纪律验证 ──
    candidates = _batch_validate_discipline(candidates, verbose=True)
    if verbose:
        print(f"  📋 纪律验证: {len(candidates)} 只通过")

    if not candidates:
        if verbose:
            print("\n  ⚠️ 全部被纪律规则淘汰，今日不适合一夜持股。")
        return []

    # ── Phase 8: 综合评分排序 v2 ──
    results = []
    for code, data in candidates.items():
        score = _compute_overnight_score_v2(data)
        disc = data.get("纪律", {})
        combo = disc.get("组合信号", {})
        results.append(
            {
                "代码": code,
                "名称": data.get("名称", ""),
                "最新价": data.get("最新价", 0),
                "涨跌幅": data.get("涨跌幅", 0),
                "振幅": data.get("振幅", 0),
                "量比": data.get("量比", 0),
                "换手率": data.get("换手率", 0),
                "流通市值": data.get("流通市值", 0),
                "成交额": data.get("成交额", 0),
                "一夜评分": score,
                "20日涨幅": disc.get("20日涨幅", 0),
                "近5日涨幅": disc.get("近5日涨幅", 0),
                "组合信号": combo.get("信号", "?"),
                "信号强度": combo.get("强度", 0),
                "短线评分": disc.get("短线评分", 0),
                "均线": data.get("均线", {}),
            }
        )

    results.sort(key=lambda x: x["一夜评分"], reverse=True)

    total_time = time.time() - t_start
    if verbose:
        print(f"\n  ⏱ 总耗时: {total_time:.1f}s")
        print(f"  🎯 最终候选: {len(results)} 只\n")

        if results:
            _print_results(results[:top_n])
            _print_sell_rules()

    return results[:top_n]


def _compute_overnight_score(data):
    """一夜持股综合评分 (0-100)

    权重分配：
    - 量比(25%): 越高越好, 1-3映射到60-100分
    - 换手率(20%): 适中最优, 8-12%给满分
    - 振幅(15%): 越大越好, 3-8%映射
    - 涨跌幅(15%): 接近3%最优(还有上涨空间)
    - 均线(25%): MA5/MA10/MA20多头排列加分
    """
    score = 0

    # 量比 (1→60, 3+→100)
    vr = data.get("量比", 0)
    score += min(25, vr / 3 * 25)

    # 换手率 (8-12%满分, 5-15%线性)
    turnover = data.get("换手率", 0)
    if 8 <= turnover <= 12:
        score += 20
    elif 5 <= turnover <= 15:
        dist = min(abs(turnover - 8), abs(turnover - 12))
        score += max(10, 20 - dist * 3)

    # 振幅 (3%→60, 8%+→100)
    amp = data.get("振幅", 0)
    score += min(15, amp / 8 * 15)

    # 涨跌幅 (接近3%最优, 说明还有冲高空间)
    gain = data.get("涨跌幅", 0)
    if 3 <= gain <= 3.5:
        score += 15
    elif 3.5 < gain <= 5:
        score += max(5, 15 - (gain - 3.5) * 5)

    # 均线排列
    ma = data.get("均线", {})
    if ma:
        if ma.get("ma5", 0) > ma.get("ma10", 0) > ma.get("ma20", 0):
            score += 20
        vol_ratio = ma.get("vol_ratio", 0)
        if vol_ratio > 1.2:
            score += 5
        elif vol_ratio > 1.0:
            score += 3

    return round(min(100, score))


def _print_results(results):
    """格式化输出候选列表（含纪律列）"""
    # 宽版表格
    print("┌" + "─" * 104 + "┐")
    header = f"│ {'排名':^3} │ {'代码':^8} │ {'名称':^8} │ {'现价':^6} │ {'涨幅':^5} │ {'量比':^4} │ {'换手':^4} │ {'市值':^5} │ {'20日涨':^6} │ {'信号':^4} │ {'短线':^4} │ {'评分':^4} │"
    print(header)
    print("├" + "─" * 104 + "┤")
    for i, r in enumerate(results, 1):
        mc = r["流通市值"] / 1e8 if r["流通市值"] else 0
        sig = r.get("组合信号", "?")
        sig_str = r.get("信号强度", 0)
        signal_display = f"{sig}{sig_str:+d}"
        print(
            f"│ {i:^3} │ {r['代码']:^8} │ {r['名称']:^8} │ {r['最新价']:>6.2f} │ {r['涨跌幅']:>+4.1f}% │ {r['量比']:>4.2f} │ {r['换手率']:>3.1f}% │ {mc:>5.0f}亿 │ {r.get('20日涨幅', 0):>+5.1f}% │ {signal_display:>6} │ {r.get('短线评分', 0):>4} │ {r['一夜评分']:>4} │"
        )
    print("└" + "─" * 104 + "┘")


def _print_sell_rules():
    """打印卖出规则"""
    print("""
┌─────────────────────────────────────────────────────────────┐
│                     📈 卖出铁律（第二天执行）                    │
├─────────────────────────────────────────────────────────────┤
│  ⏰ 时间: 无论盈亏，第二天早盘10:00前必须清仓                    │
│  🟢 高开1-5%: 冲高出现拐头或放量滞涨 → 立即止盈                │
│  🟡 平开/低开: 反弹至成本线附近 → 分批离场                     │
│  🔴 低开低走-2%~-3%: 无条件止损！不补仓、不扛单                │
│  💰 仓位: 单只≤20%总资金, 总隔夜≤50%                          │
└─────────────────────────────────────────────────────────────┘
""")


def overnight_sell_check(positions):
    """第二天早盘持仓检查 — 根据开盘情况给出卖出建议

    Args:
        positions: list of dict, 每只包含 {'代码', '成本', '股数'}
    """
    if not positions:
        print("当前无隔夜持仓。")
        return

    codes = [p["代码"] for p in positions]
    em_data = _em_quote_batch(codes)

    print("\n【隔夜持仓 · 早盘卖出建议】")
    print(f"  检查时间: {datetime.now().strftime('%H:%M:%S')}")
    print(f"  持仓数量: {len(positions)} 只\n")

    for pos in positions:
        code = pos["代码"]
        cost = pos["成本"]
        shares = pos.get("股数", 0)
        data = em_data.get(code, {})

        price = data.get("最新价", 0)
        gain = data.get("涨跌幅", 0)
        vr = data.get("量比", 0)

        if not price:
            print(f"  {code}: 数据获取失败")
            continue

        pnl = (price - cost) / cost * 100

        # 决定建议
        if pnl >= 5:
            advice = "🔴 急卖! 已赚+5%，落袋为安"
        elif pnl >= 2:
            advice = "🟠 分批止盈，先卖一半"
        elif pnl >= 1:
            advice = "🟡 冲高止盈，设+2%卖点"
        elif pnl >= -1:
            advice = "⚪ 成本附近出，别亏手续费"
        elif pnl >= -2:
            advice = "🟠 小亏出掉，别等扩大"
        else:
            advice = "🔴 无条件止损！-2%铁律触发"

        print(
            f"  {code} {data.get('名称', '')} | 成本:{cost:.2f} 现价:{price:.2f} | "
            f"浮盈:{pnl:+.2f}% | 量比:{vr:.2f} | {advice}"
        )

    print("\n  ⏰ 提醒: 无论盈亏，10:00前全部清仓！")

    return em_data
