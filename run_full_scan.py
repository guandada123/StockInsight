"""全市场扫描：仅排除ST/退市，不设价格和成交量下限

特性:
  - 复用 cli.py 的 deep_analyze + 8线程并行
  - 每只股票完成后立即存 checkpoint，崩溃后 --resume 续跑不重来
  - 单只股票 45 秒超时保护，卡住自动跳过
  - 扫描完成自动追加历史评分数据库
"""

import argparse
import fcntl
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from contextlib import contextmanager
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 复用 cli.py 的分析函数（含 skip_nt + 完整返回）
from stock_analyzer.analyzer import deep_analyze
from stock_analyzer.config import SCAN_WORKERS
from stock_analyzer.fetcher import sina_real_time
from stock_analyzer.screener import load_all_a_shares


def _get_checkpoint_file():
    from stock_analyzer.config import CHECKPOINT_FILE

    return CHECKPOINT_FILE


PER_STOCK_TIMEOUT = 45


@contextmanager
def _checkpoint_lock(mode="r"):
    """checkpoint 文件锁 — 防止多进程并发读写"""
    cp = _get_checkpoint_file()
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    fd = os.open(cp, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        if mode == "r":
            fcntl.flock(fd, fcntl.LOCK_SH)  # 共享锁（读）
        else:
            fcntl.flock(fd, fcntl.LOCK_EX)  # 排他锁（写/清空）
        yield fd
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def load_checkpoint():
    cp = _get_checkpoint_file()
    if not os.path.exists(cp):
        return set()
    with _checkpoint_lock("r") as fd:
        os.lseek(fd, 0, os.SEEK_SET)
        data = os.read(fd, os.fstat(fd).st_size).decode("utf-8")
    return {line.strip() for line in data.splitlines() if line.strip()}


def save_checkpoint(code):
    with _checkpoint_lock("w") as fd:
        os.lseek(fd, 0, os.SEEK_END)
        os.write(fd, (code + "\n").encode("utf-8"))
        os.fsync(fd)


def clear_checkpoint():
    cp = _get_checkpoint_file()
    if os.path.exists(cp):
        with _checkpoint_lock("w") as fd:
            os.ftruncate(fd, 0)
            os.fsync(fd)


def main():
    parser = argparse.ArgumentParser(description="全市场扫描")
    parser.add_argument("--resume", action="store_true", help="从 checkpoint 续跑")
    parser.add_argument("--no-resume", action="store_true", help="忽略 checkpoint，从头扫描")
    args = parser.parse_args()

    t0 = time.time()
    print(f"全市场扫描启动 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")

    # 1. 加载股票列表
    print("步骤1: 加载全A股列表...")
    all_codes = load_all_a_shares()
    print(f"  共 {len(all_codes)} 只")

    # 2. 实时行情批量获取（排除ST/退市/停牌）
    print("步骤2: 获取实时行情，排除ST/退市...")
    rt_all = {}
    for i in range(0, len(all_codes), 500):
        batch = all_codes[i : i + 500]
        rt_all.update(sina_real_time(batch))

    valid_codes = []
    for code in all_codes:
        info = rt_all.get(code)
        if not info:
            continue
        name = info.get("名称", "")
        if "ST" in name or "退" in name:
            continue
        price = info.get("最新价", 0) or 0
        if price <= 0:
            continue
        valid_codes.append(code)

    print(f"  过滤后剩余 {len(valid_codes)} 只")

    # 3. 断点续跑
    if not args.no_resume:
        done = load_checkpoint()
        todo = [c for c in valid_codes if c not in done]
        if done:
            if args.resume:
                print(f"  ✅ 续跑模式：已完成 {len(done)} 只，剩余 {len(todo)} 只")
            else:
                print(
                    f"  💡 发现 {len(done)} 只已完成。使用 --resume 跳过，或 --no-resume 重新扫描"
                )
    else:
        clear_checkpoint()
        done = set()
        todo = valid_codes

    # 4. 并行分析（8线程 + skip_nt，复用 cli.py 的 deep_analyze）
    print(
        f"步骤3: 并行深度分析（{len(todo)} 只，{SCAN_WORKERS}线程，超时{PER_STOCK_TIMEOUT}s/只）..."
    )

    results = []
    total = len(todo)
    skipped = 0
    completed = 0

    def analyze_one(code):
        try:
            r = deep_analyze(code, days=120, skip_nt=True)
            if r and r["qs_composite"] > 0:
                # 转为扫描结果格式
                return {
                    "代码": code,
                    "名称": rt_all.get(code, {}).get("名称", ""),
                    "综合评分": r["qs_composite"],
                    "评级": r["qs_rating"],
                    "动量分": r["mom_s"],
                    "技术分": r["tech_s"],
                    "基本面分": r["fund_s"],
                    "量能分": r["vol_s"],
                    "风险分": r["risk_s"],
                    "最新价": r["price"],
                    "近5日涨跌幅": r["near_5d"],
                }
            return None
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as executor:
        futures = {executor.submit(analyze_one, c): c for c in todo}

        for future in futures:
            code = futures[future]
            try:
                row = future.result(timeout=PER_STOCK_TIMEOUT)
            except FutureTimeout:
                skipped += 1
                completed += 1
                print(f"  ⏰ [{code}] 超时，跳过")
                save_checkpoint(code)
                continue
            except Exception:
                skipped += 1
                completed += 1
                save_checkpoint(code)
                continue

            completed += 1
            if row is not None:
                results.append(row)

            save_checkpoint(code)

            # 进度报告
            if completed % 100 == 0 or completed == total:
                elapsed = time.time() - t0
                rate = completed / elapsed if elapsed > 0 else 0
                eta = (total - completed) / rate if rate > 0 else 0
                pct = completed / total * 100
                print(
                    f"  [{completed}/{total}] {pct:.0f}%  速率 {rate:.1f}只/s  "
                    f"ETA {eta / 60:.0f}min  结果 {len(results)}  跳过 {skipped}"
                )

    # 5. 保存结果
    elapsed = time.time() - t0
    print("\n步骤4: 保存结果...")
    print(f"扫描完成: {len(results)} 只 | 跳过/失败: {skipped} 只 | 耗时 {elapsed / 60:.1f} 分钟")

    import pandas as pd

    df = pd.DataFrame(results)

    # 5a. 追加到历史数据库
    from stock_analyzer.history_db import append_daily_results

    try:
        today = datetime.now().strftime("%Y-%m-%d")
        n_hist = append_daily_results(df, today)
        print(f"历史库追加: {n_hist} 条 (日期: {today})")
    except Exception as e:
        print(f"历史库追加失败（不影响主流程）: {e}")

    df = df.sort_values("综合评分", ascending=False).reset_index(drop=True)
    df.insert(0, "序号", range(1, len(df) + 1))

    csv_path = "full_scan_results.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"CSV: {csv_path}")

    json_path = "full_scan_results.json"
    data = {
        "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "股票数量": len(df),
        "股票列表": df.to_dict(orient="records"),
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"JSON: {json_path}")

    # 评分分布
    print("\n评分分布:")
    for label, lo, hi in [
        ("优秀(≥80)", 80, 100),
        ("良好(60-79)", 60, 80),
        ("中等(40-59)", 40, 60),
        ("偏低(<40)", 0, 40),
    ]:
        n = len([r for r in results if lo <= r["综合评分"] < hi])
        print(f"  {label}: {n} 只")

    clear_checkpoint()
    print(f"\n完成！[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")


if __name__ == "__main__":
    main()
