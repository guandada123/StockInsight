"""
API 响应缓存层 — TTL 内存缓存
使用简单的字典 + 过期时间，无需 Redis。

Usage:
    from backend.cache import ttl_cache

    @ttl_cache(ttl=30)
    async def get_market_overview():
        ...
"""

import asyncio
import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)

# 全局缓存存储
_cache: dict[str, tuple[float, Any]] = {}

# 缓存统计
_stats = {"hits": 0, "misses": 0}


def ttl_cache(ttl: int = 30):
    """
    TTL 内存缓存装饰器。

    Args:
        ttl: 缓存存活时间（秒），默认 30 秒

    特性：
        - 命中时响应 < 1ms
        - 过期后自动刷新
        - 线程安全（GIL 保护字典操作）
        - 支持 async 和 sync 函数
    """

    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            key = f"{func.__module__}.{func.__name__}:{args}:{sorted(kwargs.items())}"
            now = time.time()

            # 检查缓存
            if key in _cache:
                expire_at, value = _cache[key]
                if now < expire_at:
                    _stats["hits"] += 1
                    return value

            # 缓存未命中 — 执行原函数
            _stats["misses"] += 1
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            _cache[key] = (now + ttl, result)
            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            key = f"{func.__module__}.{func.__name__}:{args}:{sorted(kwargs.items())}"
            now = time.time()

            if key in _cache:
                expire_at, value = _cache[key]
                if now < expire_at:
                    _stats["hits"] += 1
                    return value

            _stats["misses"] += 1
            result = func(*args, **kwargs)
            _cache[key] = (now + ttl, result)
            return result

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def cache_stats() -> dict:
    """返回缓存命中率统计。"""
    total = _stats["hits"] + _stats["misses"]
    hit_rate = round(_stats["hits"] / total * 100, 1) if total > 0 else 0
    return {
        "hits": _stats["hits"],
        "misses": _stats["misses"],
        "total": total,
        "hit_rate_pct": hit_rate,
        "entries": len(_cache),
    }


def cache_clear():
    """清空所有缓存。"""
    _cache.clear()
    _stats["hits"] = 0
    _stats["misses"] = 0
    logger.info("Cache cleared")


def cache_evict_expired():
    """清理过期条目（可定时调用）。"""
    now = time.time()
    expired = [k for k, (expire_at, _) in _cache.items() if now >= expire_at]
    for k in expired:
        del _cache[k]
    if expired:
        logger.debug("Evicted %d expired cache entries", len(expired))
