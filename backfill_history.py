"""历史评分回算 —— 用K线永久存储回算过去日期的评分，补全daily_scores

🔴 口径警告（2026-11-25 实测，勿混用）：
    本脚本用 `composite_quant_score(hist, None)` 回算（基本面/情绪入参为 None），
    而日扫描用 `composite_quant_score(kline, fundamentals, sentiment_score=...)`。
    同股相邻两日实测：回填 31.9 vs 日扫描 62.2（差 -30.3），**不是行情波动能解释的**。
    另外日扫描只写 composite_score >= 60 的股票，本脚本写全市场（min 约 18~21）。
    → 把本脚本结果混入由日扫描产出的 daily_scores 会让「全市场均分/评分分布/跨日窗口」
      不可比。真修复是统一评分入参（见 .autopilot/QUEUE 的对应条目），不是加大过滤阈值。
    故本脚本默认**拒绝写库**，需显式 --allow-mixed-scoring 才执行。
"""

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


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(description="历史评分回算（默认拒绝写库，见文件头口径警告）")
    ap.add_argument(
        "--allow-mixed-scoring",
        action="store_true",
        help="确认知情：允许把「无基本面回算」的数据写入日扫描产出的 daily_scores",
    )
    args = ap.parse_args(argv)
    if not args.allow_mixed_scoring:
        print(
            "[拒绝] 本脚本回算口径与日扫描不一致（基本面/情绪入参为 None，且写全市场而非 >=60）。"
            "2026-11-25 实测同股相邻两日评分差达 -30 分，混入会让跨日统计不可比。"
            "如确已知情并接受（例如只补历史、不与日扫描混用）：--allow-mixed-scoring"
        )
        return 2

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

    # 确定目标日期（最近 60 个交易日）
    # 🔴 2026-11-25 修：原取 all_stocks[0] 单只股票的日期序列，而那只股票 K 线止于
    # 2026-07-21 → 窗口整体错位成「04-23~07-21」，跑完补了 59 个 4~7 月历史缺口，
    # 却**没补当时真正缺的 10-27/11-17**。改为取全部股票日期并集，窗口才跟着市场走。
    all_dates: set[str] = set()
    for _, _df in all_stocks:
        all_dates.update(str(d)[:10] for d in _df["日期"].unique())
    target_dates = sorted(all_dates)[-60:]

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
    # 必须把返回值接到退出码：否则「拒绝写库」也会 rc=0，脚本化调用会误判成功
    sys.exit(main())
