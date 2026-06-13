"""
数据获取层韧性模块 — 重试 + 断路器 + 降级

为 stock_analyzer/fetcher 的所有网络调用提供容错保护。

用法:
    from stock_analyzer.resilience import retry, circuit_breaker

    @retry(max_retries=3, base_delay=1.0)
    def fetch_market_data(code: str) -> dict:
        ...

    @circuit_breaker("akshare", failure_threshold=5, recovery_timeout=60)
    def get_kline_from_akshare(code: str) -> pd.DataFrame:
        ...
"""

import logging
import threading
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


# ═══════════════════════════════════════
# 重试装饰器 — 指数退避
# ═══════════════════════════════════════


def retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable: tuple[type[BaseException], ...] = (
        ConnectionError,
        TimeoutError,
        OSError,
        IOError,
    ),
    on_retry: Callable[[int, Exception], None] | None = None,
):
    """
    指数退避重试装饰器。

    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟（秒）
        max_delay: 最大延迟上限
        retryable: 可重试的异常类型
        on_retry: 每次重试时的回调(attempt, exception)
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable as e:
                    last_exc = e
                    if attempt == max_retries:
                        logger.error(
                            "retry_exhausted: func=%s attempts=%d error=%s",
                            func.__name__,
                            attempt + 1,
                            str(e)[:200],
                        )
                        raise
                    delay = min(base_delay * (2**attempt), max_delay)
                    logger.warning(
                        "retry: func=%s attempt=%d/%d delay=%.1fs error=%s",
                        func.__name__,
                        attempt + 1,
                        max_retries,
                        delay,
                        str(e)[:100],
                    )
                    if on_retry:
                        on_retry(attempt + 1, e)
                    time.sleep(delay)
            raise last_exc  # type: ignore

        return wrapper  # type: ignore

    return decorator


# ═══════════════════════════════════════
# 断路器
# ═══════════════════════════════════════


class CircuitBreakerOpen(Exception):
    """断路器打开时抛出。"""


class _CircuitBreaker:
    """令牌桶式断路器 — 连续失败达阈值后短路。"""

    def __init__(self, name: str, failure_threshold: int, recovery_timeout: float):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failures = 0
        self._state = "CLOSED"  # CLOSED | OPEN | HALF_OPEN
        self._last_failure_time = 0.0
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        with self._lock:
            if self._state == "CLOSED":
                return False
            if self._state == "OPEN":
                if time.time() - self._last_failure_time > self.recovery_timeout:
                    self._state = "HALF_OPEN"
                    logger.info("circuit_breaker_half_open: name=%s", self.name)
                    return False
                return True
            return False  # HALF_OPEN allows through

    def record_success(self):
        with self._lock:
            if self._state != "CLOSED":
                logger.info("circuit_breaker_closed: name=%s", self.name)
            self._failures = 0
            self._state = "CLOSED"

    def record_failure(self):
        with self._lock:
            self._failures += 1
            self._last_failure_time = time.time()
            if self._failures >= self.failure_threshold:
                if self._state != "OPEN":
                    self._state = "OPEN"
                    logger.error(
                        "circuit_breaker_opened: name=%s failures=%d", self.name, self._failures
                    )


# 全局断路器注册表
_breakers: dict[str, _CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    fallback: Callable[..., Any] | None = None,
):
    """
    断路器装饰器。

    Args:
        name: 断路器名称（按数据源命名，如 "akshare", "eastmoney"）
        failure_threshold: 触发打开的连续失败次数
        recovery_timeout: 打开后多久尝试恢复（秒）
        fallback: 断路器打开时的降级函数（可选）
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            with _breakers_lock:
                if name not in _breakers:
                    _breakers[name] = _CircuitBreaker(name, failure_threshold, recovery_timeout)
            breaker = _breakers[name]

            if breaker.is_open:
                if fallback:
                    logger.warning("circuit_breaker_fallback: name=%s func=%s", name, func.__name__)
                    return fallback(*args, **kwargs)
                raise CircuitBreakerOpen(
                    f"数据源 '{name}' 暂时不可用(连续失败{breaker._failures}次)，"
                    f"将在{int(breaker.recovery_timeout)}秒后重试"
                )

            try:
                result = func(*args, **kwargs)
                breaker.record_success()
                return result
            except Exception:
                breaker.record_failure()
                raise

        return wrapper  # type: ignore

    return decorator


# ═══════════════════════════════════════
# 便捷组合：重试 + 断路器
# ═══════════════════════════════════════


def resilient(
    source_name: str,
    max_retries: int = 2,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    fallback: Callable[..., Any] | None = None,
):
    """
    组合装饰器：先重试，再断路器。

    用法:
        @resilient("eastmoney", max_retries=2, fallback=lambda code: pd.DataFrame())
        def fetch_kline(code: str) -> pd.DataFrame:
            ...
    """

    def decorator(func: F) -> F:
        # 先包装重试
        retried = retry(max_retries=max_retries, base_delay=0.5)(func)
        # 再包装断路器
        protected = circuit_breaker(
            source_name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            fallback=fallback,
        )(retried)
        return protected  # type: ignore

    return decorator


def get_breaker_status() -> dict[str, dict]:
    """获取所有断路器状态（用于 /health 端点）。"""
    result = {}
    for name, b in _breakers.items():
        result[name] = {
            "state": b._state,
            "failures": b._failures,
            "threshold": b.failure_threshold,
        }
    return result
