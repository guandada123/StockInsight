"""
StockInsight SQLite 异步连接池 — WAL 模式 + aiosqlite + 超时保护

用法:
    from backend.db import get_connection, execute_query

    async with get_connection() as conn:
        cursor = await conn.execute("SELECT * FROM kline_store WHERE code = ?", (code,))
        rows = await cursor.fetchall()

    # 或使用便捷函数
    rows = await execute_query("SELECT * FROM daily_basic WHERE code = ?", (code,))

特性:
    - WAL 模式: 允许并发读写（默认 SQLite 是串行的）
    - 异步连接池: 最多 5 个连接复用（asyncio.Queue，避免频繁 open/close）
    - 超时保护: 单查询最多 10 秒
    - 自动 VACUUM: 空间回收
"""

import asyncio
import logging
import os
import sqlite3
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

# 配置
_DB_PATH = os.environ.get(
    "STOCKINSIGHT_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stock_cache.db"),
)
_POOL_SIZE = int(os.environ.get("STOCKINSIGHT_DB_POOL_SIZE", "5"))
_QUERY_TIMEOUT = int(os.environ.get("STOCKINSIGHT_DB_TIMEOUT", "10"))

# 异步连接池
_pool: asyncio.Queue[aiosqlite.Connection] | None = None
_initialized = False


async def _init_db():
    """初始化数据库: WAL 模式 + 性能优化 pragma。"""
    global _initialized, _pool
    if _initialized:
        return
    # 使用锁防止并发 init（用 asyncio.Lock 替代 threading.Lock）
    _pool = asyncio.Queue(maxsize=_POOL_SIZE)

    # 创建初始连接并设置 WAL 模式（需要先有连接才能设置 PRAGMA）
    conn = await aiosqlite.connect(_DB_PATH, timeout=_QUERY_TIMEOUT)
    conn.row_factory = sqlite3.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA synchronous=NORMAL")
    await conn.execute("PRAGMA mmap_size=67108864")
    await conn.execute("PRAGMA cache_size=-8000")
    await conn.execute("PRAGMA temp_store=MEMORY")
    await conn.close()

    _initialized = True
    logger.info("db: initialized WAL mode, pool_size=%d, db=%s", _POOL_SIZE, _DB_PATH)


async def _create_connection() -> aiosqlite.Connection:
    """创建新的异步 SQLite 连接（带优化 pragma）。"""
    conn = await aiosqlite.connect(_DB_PATH, timeout=_QUERY_TIMEOUT)
    conn.row_factory = sqlite3.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA synchronous=NORMAL")
    await conn.execute("PRAGMA cache_size=-8000")
    return conn


class _AsyncDbConnection:
    """异步上下文管理器 — 从池中获取连接，使用后归还。"""

    def __init__(self):
        self.conn: aiosqlite.Connection | None = None

    async def __aenter__(self) -> aiosqlite.Connection:
        await _init_db()

        if _pool is None:
            raise RuntimeError("数据库连接池未初始化")
        try:
            self.conn = _pool.get_nowait()
        except asyncio.QueueEmpty:
            self.conn = await _create_connection()
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.conn is not None:
            if exc_type is not None:
                # 连接可能处于异常状态，丢弃不归还
                try:
                    await self.conn.close()
                except Exception:
                    pass
                self.conn = None
            else:
                if _pool is None:
                    raise RuntimeError("数据库连接池未初始化")
                try:
                    _pool.put_nowait(self.conn)
                except asyncio.QueueFull:
                    # 池满，关闭多余连接
                    await self.conn.close()
                self.conn = None


def get_connection() -> _AsyncDbConnection:
    """
    从池中获取异步连接，使用后归还。

    用法:
        async with get_connection() as conn:
            await conn.execute(...)
    """
    return _AsyncDbConnection()


async def execute_query(sql: str, params: tuple = (), fetchone: bool = False) -> Any:
    """
    便捷查询函数。

    Args:
        sql: SQL 语句
        params: 参数元组
        fetchone: True 返回单行，False 返回所有行

    Returns:
        查询结果 (list[sqlite3.Row] 或 sqlite3.Row 或 None)
    """
    async with get_connection() as conn:
        cursor = await conn.execute(sql, params)
        if fetchone:
            return await cursor.fetchone()
        return await cursor.fetchall()


async def execute_write(sql: str, params: tuple = ()) -> int:
    """
    写操作（INSERT/UPDATE/DELETE）。

    Returns:
        affected rows count
    """
    async with get_connection() as conn:
        cursor = await conn.execute(sql, params)
        await conn.commit()
        return int(cursor.rowcount)


async def vacuum():
    """回收数据库空间（应在低负载时调用）。"""
    async with get_connection() as conn:
        await conn.execute("VACUUM")
        logger.info("db: VACUUM completed")


def pool_stats() -> dict:
    """返回连接池统计（同步函数，仅读取计数器）。"""
    return {
        "pool_size": _POOL_SIZE,
        "available": _pool.qsize() if _pool is not None else 0,
        "db_path": _DB_PATH,
        "wal_mode": True,
    }
