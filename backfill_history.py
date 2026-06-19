"""历史评分回算 —— 用K线永久存储回算过去日期的评分，补全daily_scores"""

import logging
import os
import pickle
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd

from stock_analyzer.analysis import full_technical_analysis
from stock_analyzer.config import DB_PATH, SCAN_WORKERS
from stock_analyzer.quant import composite_quant_score


def score_on_date(code, kline_df, date_str):
    """计算某只股票在指定日期的评分"""
    # 统一日期格式
    kline_df = kline_df.copy()
    kline_df["日期"] = pd.to_datetime(kline_df["日期"])
    target_date = pd.Timestamp(date_str)
    hist = kline_df[kline_df["日期"] <= target_date].copy()
    if len(hist) < 20:
        return None

    try:
        hist = full_technical_analysis(hist)
        quant = composite_quant_score(hist, None)
        fs = quant.get("factor_scores", {})

        def gf(k):
            v = fs.get(k, {})
            return round(float(v.get("score", 0)), 1) if isinstance(v, dict) else 0

        price = float(hist["收盘"].iloc[-1])
        return {
            "code": code,
            "name": "",
            "composite_score": round(float(quant.get("composite_score", 0)), 1),
            "rating": str(quant.get("rating", "")),
            "momentum_score": gf("momentum"),
            "technical_score": gf("technical"),
            "fundamental_score": gf("fundamental"),
            "volume_score": gf("volume"),
            "risk_score": gf("risk"),
            "price": price,
        }
    except Exception:
        return None


def main():
    # 加载所有K线数据
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT code, data FROM kline_store")
    all_stocks = []
    for row in cur:
        try:
            df = pickle.loads(row[1])
            if len(df) >= 20:
                all_stocks.append((row[0], df))
        except Exception as e:
            logger.debug("加载K线数据异常: %s", e)
    conn.close()
    print(f"加载 {len(all_stocks)} 只股票K线")

    # 确定目标日期（最近60个交易日）
    sample_dates = sorted(set(str(d)[:10] for d in all_stocks[0][1]["日期"].unique()))
    target_dates = sample_dates[-60:]

    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT DISTINCT date FROM daily_scores")
    existing = {row[0] for row in cur}
    conn.close()
    need_dates = [d for d in target_dates if d not in existing]
    print(f"目标日期: {target_dates[0]}~{target_dates[-1]}, 需回算: {len(need_dates)}天")

    for date_str in need_dates:
        t0 = time.time()
        results = []
        done = 0

        def work(stock_tuple):
            code, kline = stock_tuple
            return score_on_date(code, kline, date_str)

        with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as ex:
            futures = {ex.submit(work, s): s[0] for s in all_stocks}
            for f in as_completed(futures):
                r = f.result()
                if r:
                    results.append(r)
                done += 1
                if done % 1000 == 0:
                    elapsed = time.time() - t0
                    rate = done / elapsed if elapsed > 0 else 0
                    eta = (len(all_stocks) - done) / rate if rate > 0 else 0
                    print(
                        f"  [{date_str}] {done}/{len(all_stocks)} rate={rate:.0f}/s ETA={eta / 60:.0f}min results={len(results)}"
                    )

        # 写入daily_scores
        if results:
            conn = sqlite3.connect(DB_PATH)
            for r in results:
                conn.execute(
                    "INSERT OR REPLACE INTO daily_scores (date, code, name, composite_score, rating, "
                    "momentum_score, technical_score, fundamental_score, volume_score, risk_score, price) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        date_str,
                        r["code"],
                        r["name"],
                        r["composite_score"],
                        r["rating"],
                        r["momentum_score"],
                        r["technical_score"],
                        r["fundamental_score"],
                        r["volume_score"],
                        r["risk_score"],
                        r["price"],
                    ),
                )
            conn.commit()
            conn.close()
            elapsed = time.time() - t0
            print(f"  [{date_str}] 完成: {len(results)}条, 耗时{elapsed / 60:.1f}min")

    # 验证
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT date, COUNT(*) FROM daily_scores GROUP BY date ORDER BY date")
    print("\n评分历史:")
    for row in cur:
        print(f"  {row[0]}: {row[1]}条")
    conn.close()


if __name__ == "__main__":
    main()
