"""测试 backend/cache.py — TTL 内存缓存装饰器 + 统计管理"""

import time
from unittest import mock

import pytest

from backend import cache

# ── 测试辅助 ────────────────────────────────────


def _make_sync_fn(return_value="result"):
    """返回一个同步模拟函数"""
    fn = mock.MagicMock(return_value=return_value)
    fn.__name__ = "sync_fn"
    fn.__module__ = "test_cache"
    return fn


def _make_async_fn(return_value="result"):
    """返回一个异步模拟函数"""

    async def fn(*args, **kwargs):
        return return_value

    fn.__name__ = "async_fn"
    fn.__module__ = "test_cache"
    # 标记为协程函数
    mock_coro = mock.AsyncMock(return_value=return_value)
    # 保留函数名属性
    return mock_coro


# ════════════════════════════════════════════
# 通用辅助
# ════════════════════════════════════════════


class TestCacheHelpers:
    """cache_stats / cache_clear / cache_evict_expired"""

    def setup_method(self):
        cache.cache_clear()

    def test_stats_initial_state(self):
        """初始状态：命中=0，未命中=0，hit_rate=0"""
        stats = cache.cache_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["total"] == 0
        assert stats["hit_rate_pct"] == 0
        assert stats["entries"] == 0

    def test_cache_clear_resets_all(self):
        """clear 后 stats 和 entries 全部归零"""
        # 先制造一些缓存
        fn = _make_sync_fn("hello")
        decorated = cache.ttl_cache(ttl=60)(fn)
        decorated()
        decorated()
        assert cache.cache_stats()["hits"] > 0 or cache.cache_stats()["total"] > 0

        cache.cache_clear()
        stats = cache.cache_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["entries"] == 0

    def test_evict_expired_removes_stale(self):
        """evict_expired 只移除过期条目，保留未过期"""
        # 手动往缓存写两个条目
        now = time.time()
        cache._cache["key_a"] = (now - 10, "expired_a")  # 已过期
        cache._cache["key_b"] = (now + 3600, "fresh_b")  # 未过期

        cache.cache_evict_expired()

        assert "key_a" not in cache._cache
        assert "key_b" in cache._cache
        assert cache._cache["key_b"][1] == "fresh_b"

    def test_evict_expired_no_stale(self):
        """没有过期条目时，缓存不变"""
        now = time.time()
        cache._cache["key"] = (now + 3600, "fresh")
        cache.cache_evict_expired()
        assert "key" in cache._cache

    def test_evict_expired_empty(self):
        """空缓存调用不崩溃"""
        cache.cache_clear()
        cache.cache_evict_expired()  # should not raise


# ════════════════════════════════════════════
# 同步 TTLCache
# ════════════════════════════════════════════


class TestSyncTTLCache:
    """ttl_cache 在同步函数上的表现"""

    def setup_method(self):
        cache.cache_clear()

    def test_miss_then_hit(self):
        """首次未命中，再次命中"""
        fn = _make_sync_fn(42)
        decorated = cache.ttl_cache(ttl=60)(fn)

        # 首次：未命中
        result1 = decorated()
        assert result1 == 42
        assert fn.call_count == 1

        # 再次：命中
        result2 = decorated()
        assert result2 == 42
        assert fn.call_count == 1  # 原函数只调用一次

    def test_expired_after_ttl(self):
        """TTL 过期后重新调用原函数"""
        fn = _make_sync_fn("first")
        decorated = cache.ttl_cache(ttl=1)(fn)

        decorated()  # 缓存 "first"
        # 等 TTL 过期
        time.sleep(1.1)

        fn.return_value = "second"
        result = decorated()
        assert result == "second"
        # 原函数被调用了两次（第一次未命中 + 过期重算）
        assert fn.call_count == 2

    def test_different_args_produce_different_cache(self):
        """不同参数产生不同缓存 key"""
        fn = _make_sync_fn()
        fn.__name__ = "args_fn"
        decorated = cache.ttl_cache(ttl=60)(fn)

        r1 = decorated(1, x=2)
        r2 = decorated(3, x=4)
        assert fn.call_count == 2  # 两个不同的 key

    def test_same_args_return_cached(self):
        """相同参数命中缓存"""
        fn = _make_sync_fn("cached_val")
        fn.__name__ = "same_args"
        decorated = cache.ttl_cache(ttl=60)(fn)

        r1 = decorated("hello", key="world")
        assert fn.call_count == 1

        r2 = decorated("hello", key="world")
        assert fn.call_count == 1
        assert r1 == r2 == "cached_val"

    def test_zero_ttl(self):
        """ttl=0 时每次都不缓存"""
        fn = _make_sync_fn("no_cache")
        decorated = cache.ttl_cache(ttl=0)(fn)

        decorated()
        decorated()
        assert fn.call_count == 2

    def test_stats_tracking_sync(self):
        """命中/未命中统计正确"""
        fn = _make_sync_fn(1)
        decorated = cache.ttl_cache(ttl=60)(fn)

        # 第一次：未命中
        decorated()
        stats = cache.cache_stats()
        assert stats["misses"] >= 1

        # 第二次：命中
        decorated()
        stats = cache.cache_stats()
        assert stats["hits"] >= 1
        assert stats["total"] >= 2
        assert stats["hit_rate_pct"] > 0


# ════════════════════════════════════════════
# 异步 TTLCache
# ════════════════════════════════════════════


@pytest.mark.asyncio
class TestAsyncTTLCache:
    """ttl_cache 在异步函数上的表现"""

    def setup_method(self):
        cache.cache_clear()

    async def test_async_miss_then_hit(self):
        """异步函数：首次未命中，再次命中"""
        fn = mock.AsyncMock(return_value="async_val")
        fn.__name__ = "async_test_fn"
        fn.__module__ = "test_cache"

        decorated = cache.ttl_cache(ttl=60)(fn)

        r1 = await decorated()
        assert r1 == "async_val"
        assert fn.await_count == 1

        r2 = await decorated()
        assert r2 == "async_val"
        assert fn.await_count == 1  # 命中缓存

    async def test_async_expired(self):
        """异步函数：TTL 过期后重算"""
        fn = mock.AsyncMock(return_value="old")
        fn.__name__ = "async_expire"
        fn.__module__ = "test_cache"

        decorated = cache.ttl_cache(ttl=1)(fn)
        await decorated()  # 缓存 "old"

        time.sleep(1.1)

        fn.return_value = "new"
        result = await decorated()
        assert result == "new"
        assert fn.await_count == 2

    async def test_async_different_args(self):
        """异步函数：不同参数不同缓存"""
        fn = mock.AsyncMock(side_effect=lambda code, **kw: f"data_{code}")
        fn.__name__ = "async_args"
        fn.__module__ = "test_cache"

        decorated = cache.ttl_cache(ttl=60)(fn)

        r1 = await decorated("600001")
        r2 = await decorated("600002")
        assert r1 == "data_600001"
        assert r2 == "data_600002"
        assert fn.await_count == 2

    async def test_async_zero_ttl(self):
        """异步函数：ttl=0 不缓存"""
        fn = mock.AsyncMock(return_value="x")
        fn.__name__ = "async_no_cache"
        fn.__module__ = "test_cache"

        decorated = cache.ttl_cache(ttl=0)(fn)
        await decorated()
        await decorated()
        assert fn.await_count == 2

    async def test_async_stats(self):
        """异步函数：统计正确"""
        fn = mock.AsyncMock(return_value=99)
        fn.__name__ = "async_stats"
        fn.__module__ = "test_cache"

        decorated = cache.ttl_cache(ttl=60)(fn)

        cache.cache_clear()
        await decorated()  # miss
        await decorated()  # hit

        stats = cache.cache_stats()
        assert stats["misses"] >= 1
        assert stats["hits"] >= 1
