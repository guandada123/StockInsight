"""
StockInsight SQLite 连接池 — WAL 模式 + 连接复用 + 超时保护

用法:
    from backend.db import get_connection, execute_query

    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM kline_store WHERE code = ?", (code,)).fetchall()

    # 或使用便捷函数
    rows = execute_query("SELECT * FROM daily_basic WHERE code = ?", (code,))

特性:
    - WAL 模式: 允许并发读写（默认 SQLite 是串行的）
    - 连接池: 最多 5 个连接复用（避免频繁 open/close）
    - 超时保护: 单查询最多 10 秒
    - 自动 VACUUM: 空间回收
"""

import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from queue import Empty, Queue
from typing import Any

logger = logging.getLogger(__name__)

# 配置
_DB_PATH = os.environ.get(
    "STOCKINSIGHT_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stock_cache.db"),
)
_POOL_SIZE = int(os.environ.get("STOCKINSIGHT_DB_POOL_SIZE", "5"))
_QUERY_TIMEOUT = int(os.environ.get("STOCKINSIGHT_DB_TIMEOUT", "10"))

# 连接池
_pool: Queue = Queue(maxsize=_POOL_SIZE)
_pool_lock = threading.Lock()
_initialized = False


def _init_db():
    """初始化数据库: WAL 模式 + 性能优化 pragma。"""
    global _initialized
    if _initialized:
        return
    with _pool_lock:
        if _initialized:
            return
        conn = sqlite3.connect(_DB_PATH, timeout=_QUERY_TIMEOUT)
        # WAL 模式: 允许并发读 + 单写
        conn.execute("PRAGMA journal_mode=WAL")
        # 同步模式: NORMAL (比 FULL 快, 比 OFF 安全)
        conn.execute("PRAGMA synchronous=NORMAL")
        # 内存映射: 64MB (大表查询加速)
        conn.execute("PRAGMA mmap_size=67108864")
        # 缓存大小: 8000 pages (~32MB)
        conn.execute("PRAGMA cache_size=-8000")
        # 临时表存内存
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.close()
        _initialized = True
        logger.info("db: initialized WAL mode, pool_size=%d, db=%s", _POOL_SIZE, _DB_PATH)


def _create_connection() -> sqlite3.Connection:
    """创建新的 SQLite 连接（带优化 pragma）。"""
    conn = sqlite3.connect(_DB_PATH, timeout=_QUERY_TIMEOUT)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-8000")
    return conn


@contextmanager
def get_connection():
    """
    从池中获取连接，使用后归还。

    用法:
        with get_connection() as conn:
            conn.execute(...)
    """
    _init_db()

    conn = None
    try:
        conn = _pool.get_nowait()
    except Empty:
        conn = _create_connection()

    try:
        yield conn
    except Exception:
        # 连接可能处于异常状态，丢弃不归还
        try:
            conn.close()
        except Exception:
            pass
        conn = None
        raise
    finally:
        if conn is not None:
            try:
                _pool.put_nowait(conn)
            except Exception:
                # 池满，关闭多余连接
                conn.close()


def execute_query(sql: str, params: tuple = (), fetchone: bool = False) -> Any:
    """
    便捷查询函数。

    Args:
        sql: SQL 语句
        params: 参数元组
        fetchone: True 返回单行，False 返回所有行

    Returns:
        查询结果 (list[Row] 或 Row 或 None)
    """
    with get_connection() as conn:
        cursor = conn.execute(sql, params)
        if fetchone:
            return cursor.fetchone()
        return cursor.fetchall()


def execute_write(sql: str, params: tuple = ()) -> int:
    """
    写操作（INSERT/UPDATE/DELETE）。

    Returns:
        affected rows count
    """
    with get_connection() as conn:
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.rowcount


def vacuum():
    """回收数据库空间（应在低负载时调用）。"""
    with get_connection() as conn:
        conn.execute("VACUUM")
        logger.info("db: VACUUM completed")


def pool_stats() -> dict:
    """返回连接池统计。"""
    return {
        "pool_size": _POOL_SIZE,
        "available": _pool.qsize(),
        "db_path": _DB_PATH,
        "wal_mode": True,
    }
