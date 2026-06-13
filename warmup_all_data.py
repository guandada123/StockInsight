#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一次性全量预热：A股全部历史数据永久存储

预热内容：
  1. K线 — 每只股票 365 天日线 → kline_store 表
  2. 基本面 — ROE/PE/PB/营收增长等 → fund_store 表
  3. 国家队 — 十大流通股东检测 → nt_store 表
  4. 板块 — 全市场板块分类 → sector_store 表

预热后，每日只需增量拉取（K线 1-2 天，基本面按季刷新）。

用法：
  python warmup_all_data.py                    # 全新开始（全部4项）
  python warmup_all_data.py --resume           # 断点续跑
  python warmup_all_data.py --kline-only       # 仅预热 K 线
  python warmup_all_data.py --workers 6        # 自定义线程数
"""
import sys, os, io, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from stock_analyzer.cache import (
    cached_kline, cached_fundamentals, cached_national_team_holdings,
    _load_kline_store, _perm_load, _perm_save,
)
from stock_analyzer.screener import load_all_a_shares

CHECKPOINT_FILE = ".warmup_progress.json"
DEFAULT_WORKERS = 3  # 保守线程数（新浪限流 ~150次/120s）


def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r') as f:
            data = json.load(f)
            if isinstance(data, dict):
                data['kline'] = set(data.get('kline', []))
                data['fund'] = set(data.get('fund', []))
                data['nt'] = set(data.get('nt', []))
                return data
    return {'kline': set(), 'fund': set(), 'nt': set()}


def save_checkpoint(ck):
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump({
            'kline': sorted(ck['kline']),
            'fund': sorted(ck['fund']),
            'nt': sorted(ck['nt']),
        }, f)


def warmup_kline(code):
    """预热 K 线"""
    try:
        kline = cached_kline(code, days=365)
        if kline is not None and len(kline) >= 20:
            stored = _load_kline_store(code)
            return ('ok', code, len(stored) if stored is not None else 0)
        return ('skip', code, 0)
    except Exception as e:
        return ('err', code, str(e)[:50])


def warmup_fund(code):
    """预热基本面"""
    try:
        funds = cached_fundamentals(code)
        if funds and funds.get('ROE') is not None:
            return ('ok', code, 0)
        return ('skip', code, 0)
    except Exception as e:
        return ('err', code, str(e)[:50])


def warmup_nt(code):
    """预热国家队"""
    try:
        nt = cached_national_team_holdings(code)
        return ('ok', code, 0)
    except Exception as e:
        return ('err', code, str(e)[:50])


def warmup_sectors():
    """预热板块（只需一次）"""
    from stock_analyzer.cache import cached_sectors
    try:
        sectors = cached_sectors()
        if sectors is not None and not sectors.empty:
            return True
    except Exception:
        pass
    return False


def main():
    import argparse
    p = argparse.ArgumentParser(description='预热全A股全部历史数据')
    p.add_argument('--resume', action='store_true', help='断点续跑')
    p.add_argument('--workers', type=int, default=DEFAULT_WORKERS, help='并行线程数')
    p.add_argument('--no-resume', action='store_true', help='全新开始(清除断点)')
    p.add_argument('--kline-only', action='store_true', help='仅预热K线')
    p.add_argument('--fund-only', action='store_true', help='仅预热基本面')
    p.add_argument('--nt-only', action='store_true', help='仅预热国家队')
    args = p.parse_args()

    if args.no_resume and os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)

    # 确定要预热的项目
    if args.kline_only:
        tasks = ['kline']
    elif args.fund_only:
        tasks = ['fund']
    elif args.nt_only:
        tasks = ['nt']
    else:
        tasks = ['kline', 'fund', 'nt']

    # 加载全 A 股代码
    print('加载A股列表...')
    all_codes = load_all_a_shares()
    print(f'全A股: {len(all_codes)} 只')

    # 预热板块（优先用缓存，失败不阻塞）
    if 'nt' in tasks or 'fund' in tasks:
        print('预热板块分类...')
        try:
            from stock_analyzer.sectors_fallback import SECTOR_STOCKS_FALLBACK as SECTORS
            if SECTORS:
                import pandas as pd
                df = pd.DataFrame([{'板块代码':k, '板块名称':v} for k,v in SECTORS.items()])
                _perm_save("sector_store", "name", "all_sectors", df)
                print(f'  板块分类 OK ({len(SECTORS)} 个，使用本地兜底数据)')
            else:
                print('  板块分类 跳过（无本地数据）')
        except Exception:
            print('  板块分类 跳过（不影响继续）')

    # 断点续跑
    ck = load_checkpoint() if args.resume else {'kline': set(), 'fund': set(), 'nt': set()}

    lock = Lock()

    for task in tasks:
        done = ck.get(task, set())
        codes = [c for c in all_codes if c not in done]
        total = len(codes)
        if total == 0:
            print(f'\n[{task}] 全部已完成!')
            continue

        warmup_fn = {'kline': warmup_kline, 'fund': warmup_fund, 'nt': warmup_nt}[task]
        label = {'kline': 'K线(365天)', 'fund': '基本面', 'nt': '国家队'}[task]
        est = {'kline': 0.3, 'fund': 0.8, 'nt': 2.0}[task]  # 秒/只 估计值

        print(f'\n{"="*60}')
        print(f'[{task}] {label} — 待处理 {total} 只')
        print(f'  预估: {total * est / args.workers / 60:.0f} 分钟 ({args.workers}线程)')
        print(f'{"="*60}')

        ok = skip = err = 0
        t0 = time.time()
        done_batch = set()

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(warmup_fn, c): c for c in codes}

            for future in as_completed(futures):
                code = futures[future]
                try:
                    status, c, rows = future.result(timeout=90)
                except Exception:
                    status, c = 'err', code

                with lock:
                    if status == 'ok':
                        ok += 1
                    elif status == 'skip':
                        skip += 1
                    else:
                        err += 1

                    done_batch.add(c)
                    completed = ok + skip + err

                    if len(done_batch) >= 100:
                        done.update(done_batch)
                        ck[task] = done
                        save_checkpoint(ck)
                        done_batch.clear()

                    if completed % 100 == 0 or completed == total:
                        elapsed = time.time() - t0
                        rate = completed / elapsed if elapsed > 0 else 0
                        eta = (total - completed) / rate if rate > 0 else 0
                        pct = completed / total * 100
                        print(f'  [{completed}/{total}] {pct:.0f}%  '
                              f'OK={ok} skip={skip} err={err}  '
                              f'{rate:.1f}只/s  ETA {eta/60:.0f}min')

        # 存盘
        done.update(done_batch)
        ck[task] = done
        save_checkpoint(ck)

        elapsed = time.time() - t0
        print(f'  [{task}] 完成! OK={ok} skip={skip} err={err}  耗时 {elapsed/60:.1f}min')

    # 最终汇总
    print(f'\n{"="*60}')
    print('全部预热完成!')
    for task in tasks:
        d = ck.get(task, set())
        print(f'  {task}: {len(d)} 只已永久存储')
    print(f'{"="*60}')


if __name__ == '__main__':
    main()
