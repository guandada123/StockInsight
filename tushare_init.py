#!/usr/bin/env python
"""Tushare data initializer - moneyflow, concepts, daily_basic"""
import os, time, sqlite3, sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run(moneyflow=False, concepts=False):
    for line in open('.env', encoding='utf-8'):
        if line.startswith('TUSHARE_TOKEN='):
            val = line.split('=', 1)[1].strip().strip(chr(34)).strip(chr(39))
            os.environ['TUSHARE_TOKEN'] = val
            break
    from stock_analyzer.tushare_loader import get_tushare_pro
    pro = get_tushare_pro()
    if moneyflow:
        _fetch_moneyflow(pro)
    if concepts:
        _fetch_concepts()


def _fetch_moneyflow(pro):
    print('--- Money Flow ---')
    conn = sqlite3.connect('stock_cache.db')
    existing = set()
    for r in conn.execute('SELECT DISTINCT trade_date FROM stock_moneyflow'):
        existing.add(r[0])
    trade_dates = []
    d = datetime.now()
    while len(trade_dates) < 5:
        ds = d.strftime('%Y%m%d')
        if d.weekday() < 5:
            trade_dates.append(ds)
        d -= timedelta(days=1)
    total = 0
    for td in trade_dates:
        if td in existing:
            continue
        df = pro.moneyflow(trade_date=td)
        if df is None or df.empty:
            continue
        rows = []
        for _, r in df.iterrows():
            code = r['ts_code'].split('.')[0]
            bt = sum(float(r.get(c, 0) or 0) for c in ['buy_sm_amount', 'buy_md_amount', 'buy_lg_amount', 'buy_elg_amount'])
            st = sum(float(r.get(c, 0) or 0) for c in ['sell_sm_amount', 'sell_md_amount', 'sell_lg_amount', 'sell_elg_amount'])
            rows.append((code, td,
                float(r.get('net_mf_amount', 0) or 0),
                float(r.get('buy_elg_amount', 0) or 0), float(r.get('sell_elg_amount', 0) or 0),
                float(r.get('buy_lg_amount', 0) or 0), float(r.get('sell_lg_amount', 0) or 0),
                float(r.get('buy_md_amount', 0) or 0), float(r.get('sell_md_amount', 0) or 0),
                float(r.get('buy_sm_amount', 0) or 0), float(r.get('sell_sm_amount', 0) or 0),
                bt, st))
        conn.executemany('INSERT OR REPLACE INTO stock_moneyflow VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', rows)
        conn.commit()
        total += len(rows)
        print(f'  {td}: {len(rows)} stocks')
        time.sleep(0.6)
    conn.close()
    print(f'  Total: {total} rows')


def _fetch_concepts():
    print('--- Concepts ---')
    from stock_analyzer.build_concept_db import build
    build()


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description='Tushare data init')
    p.add_argument('--moneyflow', action='store_true')
    p.add_argument('--concepts', action='store_true')
    p.add_argument('--all', action='store_true')
    a = p.parse_args()
    run(a.moneyflow or a.all, a.concepts or a.all)
