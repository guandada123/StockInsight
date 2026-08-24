"""交易日判断 — 接 tushare_loader 交易日表，fallback 内置 2026 休市表。

判断优先级：
1. stock_cache.db 的 stock_trade_calendar 表（tushare_loader.download_trade_calendar 落库，
   范围 2024-01-01~2026-12-31，is_open=1 为交易日）。表存在且日期在范围内 → 精确判断。
2. 表缺失 / 日期越界 → fallback：内置 2026 A股休市集合 + weekday<5（周六日）。
   fallback 保守：宁可少跳（误跑）也不误跳（漏扫），避免交易日被静默跳过丢数据。

2026 休市区间依据上交所 2025-12-22 公告《关于上海证券交易所2026年部分节假日休市安排的通知》。
"""
from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "stock_cache.db")

# ── 2026 A股休市日（内置 fallback，依据上交所官方公告展开）──
# 区间：元旦 1/1-1/3｜春节 2/15-2/23｜清明 4/4-4/6｜劳动节 5/1-5/5｜
#       端午 6/19-6/21｜中秋 9/25-9/27｜国庆 10/1-10/7
_HOLIDAY_RANGES_2026 = [
    ("2026-01-01", "2026-01-03"),
    ("2026-02-15", "2026-02-23"),
    ("2026-04-04", "2026-04-06"),
    ("2026-05-01", "2026-05-05"),
    ("2026-06-19", "2026-06-21"),
    ("2026-09-25", "2026-09-27"),
    ("2026-10-01", "2026-10-07"),
]


def _build_holiday_set() -> set[str]:
    s: set[str] = set()
    for start, end in _HOLIDAY_RANGES_2026:
        d0 = datetime.strptime(start, "%Y-%m-%d").date()
        d1 = datetime.strptime(end, "%Y-%m-%d").date()
        cur = d0
        while cur <= d1:
            s.add(cur.strftime("%Y-%m-%d"))
            cur = cur.fromordinal(cur.toordinal() + 1)
    return s


_HOLIDAYS_2026 = _build_holiday_set()


def _query_calendar_table(d: str) -> bool | None:
    """查 stock_trade_calendar 表。返回 True/False（交易日/非交易日），表缺失或日期越界返回 None。"""
    if not os.path.exists(DB_PATH):
        return None
    try:
        conn = sqlite3.connect(DB_PATH)
        try:
            cur = conn.execute(
                "SELECT is_open FROM stock_trade_calendar WHERE cal_date=?", (d,)
            ).fetchone()
        finally:
            conn.close()
        if cur is None:
            return None  # 越界（表范围外）→ 交由 fallback
        return cur[0] == 1
    except sqlite3.Error:
        return None


def is_trading_day(dt: date | None = None) -> bool:
    """给定日期是否为 A股交易日。默认今天。

    接 tushare_loader 交易日表优先；表不可用则 fallback 内置 2026 休市 + 周末。
    """
    if dt is None:
        dt = date.today()
    d = dt.strftime("%Y-%m-%d")
    cal = _query_calendar_table(d)
    if cal is not None:
        return cal
    # fallback：周末 + 内置休市
    if dt.weekday() >= 5:
        return False
    if d in _HOLIDAYS_2026:
        return False
    return True


if __name__ == "__main__":
    for t in ["2026-08-22", "2026-08-23", "2026-08-24", "2026-08-25",
              "2026-10-01", "2026-10-08", "2026-01-01", "2026-01-04", "2026-02-24"]:
        dd = datetime.strptime(t, "%Y-%m-%d").date()
        print(f"{t} -> {'交易日' if is_trading_day(dd) else '非交易日'}")
