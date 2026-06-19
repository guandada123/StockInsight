"""测试 backend/db.py — 异步 SQLite 连接池全生命周期"""

import asyncio
import importlib
import os
import sys
from unittest import mock

import pytest

# ── 在导入 db 前 mock aiosqlite（模块级别依赖，未安装）──
_mock_aiosqlite = mock.MagicMock()
sys.modules["aiosqlite"] = _mock_aiosqlite

from backend import db

pytestmark = pytest.mark.asyncio


# ── 测试辅助 ────────────────────────────────────


def _make_mock_conn(name="conn"):
    """创建一个模拟的 aiosqlite.Connection"""
    conn = mock.AsyncMock(name=name)
    conn.row_factory = None
    cursor = mock.AsyncMock(name=f"{name}_cursor")
    cursor.fetchone = mock.AsyncMock(return_value={"code": "000001"})
    cursor.fetchall = mock.AsyncMock(return_value=[{"code": "000001"}, {"code": "600519"}])
    cursor.rowcount = 2
    conn.execute = mock.AsyncMock(return_value=cursor)
    conn.close = mock.AsyncMock()
    conn.commit = mock.AsyncMock()
    return conn


def _reset_db_module():
    """重置 db 模块的全局状态"""
    db._pool = None
    db._initialized = False


@pytest.fixture(autouse=True)
def reset_and_mock():
    """每个测试前重置全局状态 + 配置 mock connect"""
    _reset_db_module()
    # 重新配置 mock aiosqlite.connect
    conn = _make_mock_conn()
    db.aiosqlite.connect = mock.AsyncMock(return_value=conn)
    yield
    db.aiosqlite.connect.reset_mock()


@pytest.fixture
def mock_conn():
    """返回当前 mock connection（测试内可进一步定制）"""
    return db.aiosqlite.connect.return_value


# ════════════════════════════════════════════
# __init_db
# ════════════════════════════════════════════


class TestInitDb:
    """_init_db 初始化流程"""

    async def test_init_creates_pool_and_configures_db(self, mock_conn):
        """第一次 init 创建连接池并设置 WAL pragma"""
        await db._init_db()

        assert db._initialized is True
        assert db._pool is not None
        assert db._pool.maxsize == 5
        db.aiosqlite.connect.assert_called_once()
        mock_conn.execute.assert_any_call("PRAGMA journal_mode=WAL")
        mock_conn.execute.assert_any_call("PRAGMA synchronous=NORMAL")
        mock_conn.close.assert_called_once()

    async def test_init_idempotent(self, mock_conn):
        """多次 init 是幂等的，只执行一次"""
        await db._init_db()
        await db._init_db()
        await db._init_db()

        assert db.aiosqlite.connect.call_count == 1

    async def test_init_custom_pool_size(self):
        """环境变量控制池大小"""
        orig_env = os.environ.get("STOCKINSIGHT_DB_POOL_SIZE")
        try:
            os.environ["STOCKINSIGHT_DB_POOL_SIZE"] = "3"
            importlib.reload(db)
            _reset_db_module()
            conn = _make_mock_conn()
            db.aiosqlite.connect = mock.AsyncMock(return_value=conn)
            await db._init_db()
            assert db._pool is not None
            assert db._pool.maxsize == 3
        finally:
            if orig_env:
                os.environ["STOCKINSIGHT_DB_POOL_SIZE"] = orig_env
            else:
                os.environ.pop("STOCKINSIGHT_DB_POOL_SIZE", None)
            importlib.reload(db)
            _reset_db_module()
            db.aiosqlite.connect = mock.AsyncMock(return_value=_make_mock_conn())


# ════════════════════════════════════════════
# _create_connection
# ════════════════════════════════════════════


class TestCreateConnection:
    """_create_connection 创建新连接"""

    async def test_create_connection_applies_pragma(self, mock_conn):
        """新建连接执行优化 pragma"""
        result = await db._create_connection()

        assert result is mock_conn
        db.aiosqlite.connect.assert_called_once()
        mock_conn.execute.assert_any_call("PRAGMA journal_mode=WAL")
        mock_conn.execute.assert_any_call("PRAGMA synchronous=NORMAL")
        mock_conn.execute.assert_any_call("PRAGMA cache_size=-8000")

    async def test_create_connection_sets_row_factory(self, mock_conn):
        """新建连接设置 row_factory = sqlite3.Row"""
        import sqlite3

        await db._create_connection()

        assert mock_conn.row_factory is sqlite3.Row


# ════════════════════════════════════════════
# AsyncDbConnection 上下文管理器
# ════════════════════════════════════════════


class TestAsyncDbConnection:
    """_AsyncDbConnection 上下文管理器 — 池获取/归还/异常分支"""

    async def test_acquire_creates_new_conn_on_empty_pool(self, mock_conn):
        """池空时自动创建新连接"""
        async with db.get_connection() as acq:
            assert acq is mock_conn

        # 正常退出应归还池
        assert db._pool is not None
        assert db._pool.qsize() == 1

    async def test_acquire_reuses_pooled_connection(self, mock_conn):
        """池中有连接时直接复用，不创建新连接"""
        async with db.get_connection() as acq1:
            pass
        async with db.get_connection() as acq2:
            pass

        # _init_db 调了一次 connect + 首次 get_connection 又调了一次 _create_connection
        # 第二次 get_connection 从池中复用，不再调用 connect
        assert db.aiosqlite.connect.call_count == 2  # init + _create_connection

    async def test_exception_discards_connection(self, mock_conn):
        """异常退出时丢弃连接（不归还池）"""
        try:
            async with db.get_connection() as acq:
                raise ValueError("test error")
        except ValueError:
            pass

        # close 被调用过（init 关了一次 + 异常处理又关一次）
        assert mock_conn.close.call_count >= 1
        # 连接不归还池
        assert db._pool is not None
        assert db._pool.qsize() == 0
        assert db._initialized is True

    async def test_pool_full_closes_extra_connection(self):
        """池满时 __aexit__ 关闭额外连接（put_nowait 触发 QueueFull）"""
        db._pool = asyncio.Queue(maxsize=2)
        db._initialized = True
        await db._pool.put(_make_mock_conn("pooled_1"))
        await db._pool.put(_make_mock_conn("pooled_2"))

        # 模拟池满时归还一个"额外"连接（比如并发中创建的）
        extra = _make_mock_conn("extra")
        cm = db._AsyncDbConnection()
        cm.conn = extra

        await cm.__aexit__(None, None, None)

        extra.close.assert_called_once()
        assert db._pool.qsize() == 2  # 池状态不变

    async def test_double_use_works(self, mock_conn):
        """同一 _AsyncDbConnection 可以复用"""
        async with db.get_connection() as acq1:
            pass
        async with db.get_connection() as acq2:
            pass

        # init 一次 + 第一次创建连接，第二次复用池
        assert db.aiosqlite.connect.call_count == 2


# ════════════════════════════════════════════
# execute_query / execute_write / vacuum
# ════════════════════════════════════════════


class TestExecuteQuery:
    """execute_query 便捷查询函数"""

    async def test_execute_query_fetchall(self, mock_conn):
        """execute_query 返回所有行"""
        result = await db.execute_query("SELECT * FROM test")

        assert len(result) == 2
        mock_conn.execute.assert_called_with("SELECT * FROM test", ())
        mock_conn.execute.return_value.fetchall.assert_called_once()

    async def test_execute_query_fetchone(self, mock_conn):
        """execute_query(fetchone=True) 返回单行"""
        result = await db.execute_query(
            "SELECT * FROM test WHERE code=?", ("000001",), fetchone=True
        )

        mock_conn.execute.assert_called_with("SELECT * FROM test WHERE code=?", ("000001",))
        mock_conn.execute.return_value.fetchone.assert_called_once()

    async def test_execute_query_empty_result(self, mock_conn):
        """空结果不崩溃"""
        mock_conn.execute.return_value.fetchall = mock.AsyncMock(return_value=[])
        result = await db.execute_query("SELECT * FROM test WHERE 1=0")

        assert result == []


class TestExecuteWrite:
    """execute_write 写操作函数"""

    async def test_execute_write_commits(self, mock_conn):
        """写操作执行 INSERT 并 commit"""
        result = await db.execute_write("INSERT INTO test VALUES (?)", ("val",))

        mock_conn.execute.assert_called_with("INSERT INTO test VALUES (?)", ("val",))
        mock_conn.commit.assert_called_once()
        assert result == 2  # rowcount mock

    async def test_execute_write_update(self, mock_conn):
        """UPDATE 返回影响行数"""
        result = await db.execute_write("UPDATE test SET x=1 WHERE id=?", (1,))

        mock_conn.execute.assert_called_with("UPDATE test SET x=1 WHERE id=?", (1,))
        mock_conn.commit.assert_called_once()
        assert isinstance(result, int)


class TestVacuum:
    """vacuum 空间回收"""

    async def test_vacuum_executes(self, mock_conn):
        """vacuum 调用 VACUUM"""
        await db.vacuum()

        mock_conn.execute.assert_called_with("VACUUM")


# ════════════════════════════════════════════
# pool_stats
# ════════════════════════════════════════════


class TestPoolStats:
    """pool_stats 统计信息"""

    async def test_pool_stats_before_init(self):
        """未初始化时返回 0"""
        stats = db.pool_stats()
        assert stats["available"] == 0
        assert stats["wal_mode"] is True

    async def test_pool_stats_after_init(self, mock_conn):
        """初始化后 reflect pool size"""
        await db._init_db()
        stats = db.pool_stats()

        assert stats["pool_size"] == 5
        assert stats["available"] == 0  # 空闲连接数（刚初始化的池是空的）
        assert stats["wal_mode"] is True
        assert "db_path" in stats

    async def test_pool_stats_with_connections(self, mock_conn):
        """有归还连接后 available 增加"""
        async with db.get_connection():
            pass

        stats = db.pool_stats()
        assert stats["available"] == 1
