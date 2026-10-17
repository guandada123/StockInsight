"""SQLite 连接公共工具 —— 统一 WAL/同步策略

2026-10-17 全面审计：tushare_loader / history_db / custom_factors 各自实现了
几乎相同的 `_get_conn`（connect + PRAGMA journal_mode=WAL [+ synchronous=NORMAL]），
合并为本工具，避免"改一处漏三处"。

注意：cache.py 的 `_get_conn` 是线程局部连接复用 + 建表引导，语义不同，不在此列。
"""

import sqlite3


def open_wal_conn(db_path: str, *, synchronous_normal: bool = True) -> sqlite3.Connection:
    """打开启用了 WAL 的 SQLite 连接。

    WAL 模式提升并发写入性能；synchronous=NORMAL 是 WAL 的推荐搭配
    （custom_factors 历史上未开启，本次统一，仅影响 fsync 频率，属行为改进）。

    Args:
        db_path: 数据库文件路径。
        synchronous_normal: 是否设置 PRAGMA synchronous=NORMAL。
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    if synchronous_normal:
        conn.execute("PRAGMA synchronous=NORMAL")
    return conn
