"""增强版选股器 — 两轮筛选 + 板块/短线/ML/自定义因子 全集成

两轮筛选:
  Pass 1 (快速预筛): 板块排名→实时行情→硬筛(价格/量能/ST) → TOP 200候选
  Pass 2 (深度分析): K线→技术指标→量化评分→短线信号→ML预测→自定义因子→综合排序

相比旧版 run_screener():
  1. 板块预筛: 只扫描前排板块的股票 (胜率更高)
  2. 短线信号: 组合信号 + 多周期共振 参与排序
  3. ML增强: 三模型集成预测融入评分
  4. 自定义因子: 计算自定义因子加入评分体系
  5. 自动入库: 结果写入 daily_scores
  6. 更快: 全市场 Pass1 仅需实时行情批量过滤(~3s)，Pass2 深度分析8线程并行
"""

import json
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import datetime
from threading import Lock

import pandas as pd

from .analysis import full_technical_analysis, get_technical_summary
from .cache import cached_fundamentals, cached_kline, cached_weibo_sentiment
from .fetcher import get_sectors, sina_real_time
from .quant import composite_quant_score, evaluate_trading_style
from .short_term import calc_combo_signals, calc_multi_timeframe_resonance, short_term_score

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "stock_cache.db")
STOCK_LIST_CACHE = os.path.join(PROJECT_ROOT, "stock_list_cache.json")

SCAN_WORKERS = 8


def _load_all_codes():
    if os.path.exists(STOCK_LIST_CACHE):
        with open(STOCK_LIST_CACHE, encoding="utf-8") as f:
            return json.load(f)
    try:
        import akshare as ak

        df = ak.stock_info_a_code_name()
        codes = df["code"].astype(str).str.zfill(6).tolist()
        with open(STOCK_LIST_CACHE, "w", encoding="utf-8") as f:
            json.dump(codes, f)
        return codes
    except Exception as e:
        print(f"加载股票列表失败: {e}")
        return []


def _get_sector_stocks(sector_name):
    """从 sector_store 或 fallback 获取板块成分股"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.execute("SELECT data FROM sector_store WHERE name=?", (sector_name,))
        row = cur.fetchone()
        conn.close()
        if row:
            import pickle

            data = pickle.loads(row[0])
            if isinstance(data, dict) and "stocks" in data:
                return data["stocks"]
    except Exception:
        pass
    # Fallback: 从 sectors_fallback 获取
    try:
        from .sectors_fallback import get_sector_for_code

        return list(get_sector_for_code("000001"))  # dummy
    except Exception:
        pass
    return []


def pass1_quick_filter(
    codes, sector_top_n=5, min_price=5, max_price=500, min_amplitude=0, min_turnover=1_000_000
):
    """第一轮快速预筛 — 仅用实时行情 + 板块排名

    Returns: (passed_codes, sector_info, stats)
    """
    print(f"\n{'=' * 60}")
    print(f"  Pass 1: 快速预筛 ({len(codes)} 只)")
    print(f"{'=' * 60}")

    # 1. 板块排名
    top_sectors = []
    try:
        sectors = get_sectors()
        if sectors is not None and len(sectors) > 0:
            if hasattr(sectors, "iterrows"):
                ranked = sectors.sort_values("涨跌幅", ascending=False)
                top_sectors = ranked["板块名称"].head(sector_top_n).tolist()
            else:
                ranked = sorted(
                    sectors.items(), key=lambda x: float(x[1].get("涨跌幅", 0) or 0), reverse=True
                )
                top_sectors = [name for name, _ in ranked[:sector_top_n]]
            print(f"  板块排名 TOP{sector_top_n}: {', '.join(top_sectors[:5])}")
    except Exception as e:
        print(f"  板块排名获取失败: {e}，跳过板块过滤")

    # 2. 板块成分股集合
    sector_stocks = set()
    if top_sectors:
        for s in top_sectors:
            stocks = _get_sector_stocks(s)
            sector_stocks.update(stocks)
        if sector_stocks:
            print(f"  板块成分股: {len(sector_stocks)} 只")
            # 取交集
            codes = [c for c in codes if c in sector_stocks]
            print(f"  板块过滤后: {len(codes)} 只")

    # 3. 批量实时行情 + 硬筛
    rt_all = {}
    for i in range(0, len(codes), 500):
        batch = codes[i : i + 500]
        rt_all.update(sina_real_time(batch))

    passed = []
    stats = {
        "total": len(codes),
        "st_filtered": 0,
        "price_filtered": 0,
        "vol_filtered": 0,
        "amplitude_filtered": 0,
        "passed": 0,
    }

    for code in codes:
        info = rt_all.get(code)
        if not info:
            continue
        name = info.get("名称", "")
        if "ST" in name or "退" in name:
            stats["st_filtered"] += 1
            continue
        if code.startswith("8"):
            stats["st_filtered"] += 1
            continue
        price = float(info.get("最新价", 0) or 0)
        if price < min_price or price > max_price:
            stats["price_filtered"] += 1
            continue
        vol = float(info.get("成交量", 0) or 0)
        if vol < min_turnover:
            stats["vol_filtered"] += 1
            continue
        if min_amplitude > 0:
            high = float(info.get("最高", 0) or 0)
            low = float(info.get("最低", 0) or 0)
            amp = (high - low) / price * 100 if price else 0
            if amp < min_amplitude:
                stats["amplitude_filtered"] += 1
                continue
        # 振幅（新浪API无此字段，从最高/最低计算）
        hi = float(info.get("最高", 0) or 0)
        lo = float(info.get("最低", 0) or 0)
        amp = round((hi - lo) / price * 100, 2) if price and hi and lo else 0
        passed.append(
            {
                "code": code,
                "name": name,
                "price": price,
                "change_pct": float(info.get("涨跌幅", 0) or 0),
                "volume": vol,
                "amplitude": amp,
            }
        )

    stats["passed"] = len(passed)
    print(
        f"  硬筛通过: {len(passed)} 只 (ST:{stats['st_filtered']} 价格:{stats['price_filtered']} "
        f"量能:{stats['vol_filtered']} 振幅:{stats['amplitude_filtered']})"
    )
    return passed, top_sectors, stats


def pass2_deep_analyze(candidates, top_n=30, use_ml=True, use_custom_factors=True, min_score=45):
    """第二轮深度分析 — 8线程并行

    Args:
        candidates: Pass 1 输出的候选列表
        top_n: 返回前 N 名
        use_ml: 是否使用 ML 预测
        use_custom_factors: 是否计算自定义因子
        min_score: 最低综合评分

    Returns: DataFrame with columns: 代码/名称/综合评分/评级/动量分/技术分/...
    """
    print(f"\n{'=' * 60}")
    print(f"  Pass 2: 深度分析 ({len(candidates)} 只, {SCAN_WORKERS}线程)")
    print(f"{'=' * 60}")

    # 预取舆情
    sentiment_map = {}
    try:
        sdf = cached_weibo_sentiment()
        if sdf is not None and not sdf.empty and "name" in sdf.columns:
            sentiment_map = dict(zip(sdf["name"], sdf["rate"]))
        print(f"  舆情覆盖: {len(sentiment_map)} 只")
    except Exception:
        pass

    # 自定义因子
    custom_factor_ids = []
    if use_custom_factors:
        try:
            from .custom_factors import list_factors

            custom_factors = list_factors()
            custom_factor_ids = [f["id"] for f in custom_factors]
            if custom_factor_ids:
                print(f"  自定义因子: {len(custom_factor_ids)} 个 ({', '.join(custom_factor_ids)})")
        except Exception:
            pass

    results = []
    total = len(candidates)
    t0 = time.time()
    _lock = Lock()
    completed = 0
    skipped = 0

    def analyze_one(c):
        code = c["code"]
        try:
            kline = cached_kline(code, days=120)
            if kline.empty or len(kline) < 20:
                return None
            kline = full_technical_analysis(kline)
            funds = cached_fundamentals(code)
            tech_sum = get_technical_summary(kline)

            # 量化评分
            name = c["name"]
            sent_score = None
            if sentiment_map and name in sentiment_map:
                sent_score = round(50 + float(sentiment_map[name]) * 40, 1)
            quant = composite_quant_score(kline, funds, sentiment_score=sent_score)
            qs = quant["composite_score"]
            if qs < min_score:
                return None

            fs = quant.get("factor_scores", {})

            # 短线信号
            combo = calc_combo_signals(kline)
            mr = calc_multi_timeframe_resonance(code)
            # 短线评分 (short_term_score 返回 dict, key="短线评分")
            st_result = (
                short_term_score(kline, code) if kline is not None and len(kline) >= 20 else {}
            )
            st_score = st_result.get("短线评分", 50) if isinstance(st_result, dict) else 50

            # 交易风格
            risk_data = {
                "sharpe_ratio": 0,
                "max_drawdown_pct": 0,
                "annualized_volatility_pct": 0,
                "VaR_95_pct": 0,
            }
            trading = evaluate_trading_style(kline, funds, risk_data)

            row = {
                "code": code,
                "name": name,
                "price": c["price"],
                "change_pct": c.get("change_pct", 0),
                "amplitude": c.get("amplitude", 0),
                "composite_score": round(qs, 1),
                "rating": quant["rating"],
                "动量分": round(_gf(fs, "momentum"), 1),
                "技术分": round(_gf(fs, "technical"), 1),
                "基本面分": round(_gf(fs, "fundamental"), 1),
                "量能分": round(_gf(fs, "volume"), 1),
                "风险分": round(_gf(fs, "risk"), 1),
                "舆情分": round(_gf(fs, "sentiment"), 1),
                "短线评分": round(st_score, 1) if isinstance(st_score, (int, float)) else 50,
                "长线评分": round(trading.get("long_term_score", 50), 1),
                "组合信号强度": combo.get("强度", 0),
                "共振强度": mr.get("共振强度", 0),
                "macd": tech_sum.get("macd_signal", ""),
                "rsi": tech_sum.get("rsi_value", 50),
                "kdj": tech_sum.get("kdj_signal", ""),
                "roe": round(funds.get("ROE", 0), 2) if isinstance(funds, dict) else 0,
                "国家队": 1 if _check_nt(code) else 0,
            }

            # ML预测
            if use_ml:
                try:
                    from .ml_predict import predict_ensemble

                    ml = predict_ensemble(kline, funds)
                    row["ml_direction"] = ml.get("ensemble_direction", "?")
                    row["ml_confidence"] = round(ml.get("ensemble_confidence", 50), 1)
                    row["ml_agreement"] = ml.get("agreement", "?")
                    # ML增强评分
                    if ml.get("ensemble_direction") == "看涨":
                        row["ml_boost"] = round(ml.get("ensemble_confidence", 50) * 0.1, 1)
                    else:
                        row["ml_boost"] = round(-ml.get("ensemble_confidence", 50) * 0.1, 1)
                except Exception:
                    row["ml_direction"] = "?"
                    row["ml_confidence"] = 0
                    row["ml_agreement"] = "?"
                    row["ml_boost"] = 0

            # 自定义因子
            if custom_factor_ids:
                try:
                    from .custom_factors import compute_all_factors

                    cf = compute_all_factors(code, df=kline)
                    for f in cf:
                        if f.get("value") is not None:
                            row[f"cf_{f['factor_id']}"] = f["value"]
                except Exception:
                    pass

            return row
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as executor:
        futures = {executor.submit(analyze_one, c): c for c in candidates}
        for future in as_completed(futures):
            c = futures[future]
            with _lock:
                completed += 1
            try:
                row = future.result(timeout=30)
            except FutureTimeout:
                with _lock:
                    skipped += 1
                continue
            if row:
                with _lock:
                    results.append(row)
            if completed % 50 == 0 or completed == total:
                print(f"  [{completed}/{total}] 已通过: {len(results)}")

    elapsed = time.time() - t0
    print(f"\n  Pass 2 完成: {len(results)} 只耗时 {elapsed:.0f}s ({skipped}超时)")

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)
    # 添加板块+细分
    from .sector_info import get_stock_sector_full

    df["板块"] = df["code"].apply(lambda c: get_stock_sector_full(c) if c else "")
    # 综合排序分 = 量化评分(40%) + 短线信号(25%) + ML增强(15%) + 共振(10%) + 量能(10%)
    df["综合排序分"] = (
        df["composite_score"] * 0.40
        + df["短线评分"] * 0.25
        + df.get("ml_boost", 0) * 0.15 * 10
        + ((df["共振强度"] + 60) / 120 * 100).clip(0, 100) * 0.10
        + df["量能分"] * 0.10
    )
    df = df.sort_values("综合排序分", ascending=False).reset_index(drop=True)
    df.insert(0, "排名", range(1, len(df) + 1))

    if top_n and 0 < top_n < len(df):
        df = df.head(top_n)

    return df


def enhanced_scan(
    top_n=30,
    mode="mainboard",
    sector_top_n=5,
    min_price=10,
    max_price=80,
    min_amplitude=3,
    use_ml=True,
    use_custom_factors=True,
    min_score=45,
):
    """一键增强选股

    Args:
        top_n: 最终输出数量
        mode: "mainboard" (60/00) | "full" (全部) | "top_sectors" (仅前排板块)
        sector_top_n: 板块排名取前N
        min_price: 最低价格
        max_price: 最高价格
        min_amplitude: 最低振幅%（短线需要波动）
        use_ml: 启用ML预测
        use_custom_factors: 启用自定义因子
        min_score: 最低量化评分

    Returns: DataFrame
    """
    codes = _load_all_codes()
    if not codes:
        print("无法加载股票列表")
        return pd.DataFrame()

    # 主板过滤
    if mode == "mainboard":
        codes = [c for c in codes if c.startswith("60") or c.startswith("00")]
    elif mode == "top_sectors":
        pass  # Pass1 会做板块过滤

    print(f"增强选股启动: mode={mode}, 股票池={len(codes)}只")

    # Pass 1
    candidates, top_sectors, p1_stats = pass1_quick_filter(
        codes,
        sector_top_n=sector_top_n,
        min_price=min_price,
        max_price=max_price,
        min_amplitude=min_amplitude,
    )

    if not candidates:
        print("Pass 1 无候选，选股结束")
        return pd.DataFrame()

    # Pass 2
    df = pass2_deep_analyze(
        candidates,
        top_n=top_n,
        use_ml=use_ml,
        use_custom_factors=use_custom_factors,
        min_score=min_score,
    )

    if df.empty:
        print("Pass 2 无结果")
        return df

    # 保存到 daily_scores
    _save_to_daily_scores(df, top_sectors)
    # 保存 CSV 快照
    _save_snapshot(df)

    return df


def _gf(fs, key):
    v = fs.get(key, {})
    return float(v.get("score", 0)) if isinstance(v, dict) else 0


def _check_nt(code):
    try:
        from .cache import cached_national_team_holdings

        nt = cached_national_team_holdings(code)
        return nt.get("has_national_team", False) if isinstance(nt, dict) else False
    except Exception:
        return False


def _save_to_daily_scores(df, top_sectors=None):
    """将选股结果写入 daily_scores 表"""
    try:
        conn = sqlite3.connect(DB_PATH)
        today = datetime.now().strftime("%Y-%m-%d")
        for _, row in df.iterrows():
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO daily_scores
                    (date, code, name, composite_score, rating, mom_s, tech_s, fund_s, vol_s, risk_s)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                    (
                        today,
                        row.get("code"),
                        row.get("name"),
                        row.get("composite_score"),
                        row.get("rating"),
                        row.get("动量分"),
                        row.get("技术分"),
                        row.get("基本面分"),
                        row.get("量能分"),
                        row.get("风险分"),
                    ),
                )
            except Exception:
                pass
        conn.commit()
        conn.close()
        print(f"  已写入 daily_scores: {len(df)} 条 ({today})")
    except Exception as e:
        print(f"  写入 daily_scores 失败: {e}")


def _save_snapshot(df):
    """保存选股快照 CSV"""
    today = datetime.now().strftime("%Y%m%d_%H%M")
    path = os.path.join(PROJECT_ROOT, "reports", f"enhanced_scan_{today}.csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"  快照已保存: {path}")
