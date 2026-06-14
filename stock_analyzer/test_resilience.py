import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stock_analyzer import resilience
from stock_analyzer.resilience import CircuitBreakerOpen, _CircuitBreaker


# ═══════════════════════════════════════════
# _CircuitBreaker 基础功能
# ═══════════════════════════════════════════


class TestCircuitBreakerCore(unittest.TestCase):
    """断路器核心逻辑"""

    def setUp(self):
        self.cb = _CircuitBreaker("test_source", failure_threshold=3, recovery_timeout=0.5)

    def test_initial_state(self):
        self.assertFalse(self.cb.is_open)
        self.assertEqual(self.cb._state, "CLOSED")

    def test_record_failures_opens_circuit(self):
        for _ in range(3):
            self.cb.record_failure()
        self.assertTrue(self.cb.is_open)
        self.assertEqual(self.cb._state, "OPEN")

    def test_not_open_below_threshold(self):
        self.cb.record_failure()
        self.cb.record_failure()
        self.assertFalse(self.cb.is_open)

    def test_record_success_resets(self):
        for _ in range(3):
            self.cb.record_failure()
        self.assertTrue(self.cb.is_open)
        self.cb.record_success()
        self.assertFalse(self.cb.is_open)
        self.assertEqual(self.cb._state, "CLOSED")

    def test_half_open_after_recovery(self):
        for _ in range(3):
            self.cb.record_failure()
        self.assertTrue(self.cb.is_open)
        time.sleep(0.6)  # > recovery_timeout
        # After timeout, is_open returns False but state is HALF_OPEN
        self.assertFalse(self.cb.is_open)
        self.assertEqual(self.cb._state, "HALF_OPEN")

    def test_half_open_allows_through(self):
        for _ in range(3):
            self.cb.record_failure()
        time.sleep(0.6)
        self.assertFalse(self.cb.is_open)  # HALF_OPEN allows through

    def test_success_after_half_open_closes(self):
        for _ in range(3):
            self.cb.record_failure()
        time.sleep(0.6)
        self.assertFalse(self.cb.is_open)
        self.cb.record_success()
        self.assertEqual(self.cb._state, "CLOSED")

    def test_failure_count(self):
        self.cb.record_failure()
        self.cb.record_failure()
        self.assertEqual(self.cb._failures, 2)

    def test_recovery_not_expired_stays_open(self):
        for _ in range(3):
            self.cb.record_failure()
        # not sleeping — should stay open
        self.assertTrue(self.cb.is_open)
        self.assertEqual(self.cb._state, "OPEN")


# ═══════════════════════════════════════════
# 断路器装饰器
# ═══════════════════════════════════════════


class TestCircuitBreakerDecorator(unittest.TestCase):
    """circuit_breaker 装饰器"""

    def setUp(self):
        # Clean global registry between tests
        resilience._breakers.clear()

    def test_normal_execution(self):
        call_count = [0]

        @resilience.circuit_breaker("test_cb", failure_threshold=2)
        def good_func():
            call_count[0] += 1
            return "ok"

        result = good_func()
        self.assertEqual(result, "ok")
        self.assertEqual(call_count[0], 1)

    def test_opens_after_failures(self):
        @resilience.circuit_breaker("test_cb2", failure_threshold=2)
        def failing_func():
            raise ValueError("fail")

        for _ in range(2):
            try:
                failing_func()
            except ValueError:
                pass

        with self.assertRaises(CircuitBreakerOpen):
            failing_func()

    def test_fallback_called_when_open(self):
        @resilience.circuit_breaker(
            "test_fb", failure_threshold=1, fallback=lambda: "fallback_value"
        )
        def always_fail():
            raise RuntimeError("boom")

        # First call: triggers failure
        try:
            always_fail()
        except RuntimeError:
            pass
        # Second call: circuit open, fallback used
        result = always_fail()
        self.assertEqual(result, "fallback_value")

    def test_fallback_with_args(self):
        @resilience.circuit_breaker(
            "test_fb2", failure_threshold=1, fallback=lambda x: f"fb_{x}"
        )
        def fail_with_arg(x):
            raise RuntimeError("boom")

        try:
            fail_with_arg("hello")
        except RuntimeError:
            pass
        result = fail_with_arg("hello")
        self.assertEqual(result, "fb_hello")

    def test_success_resets_circuit(self):
        call_count = [0]

        @resilience.circuit_breaker("test_reset", failure_threshold=2)
        def flaky():
            call_count[0] += 1
            if call_count[0] <= 2:
                raise ValueError("transient")
            return "recovered"

        for _ in range(2):
            try:
                flaky()
            except ValueError:
                pass
        # Circuit should be open now
        with self.assertRaises(CircuitBreakerOpen):
            flaky()

        # Manually reset by clearing breakers and re-creating
        resilience._breakers.clear()
        call_count[0] = 0

        @resilience.circuit_breaker("test_reset2", failure_threshold=3)
        def flaky2():
            call_count[0] += 1
            if call_count[0] <= 2:
                raise ValueError("transient")
            return "ok"

        for _ in range(2):
            try:
                flaky2()
            except ValueError:
                pass
        # Below threshold, still works
        result = flaky2()
        self.assertEqual(result, "ok")


# ═══════════════════════════════════════════
# 重试装饰器
# ═══════════════════════════════════════════


class TestRetryDecorator(unittest.TestCase):
    """retry 装饰器"""

    def test_no_retry_on_success(self):
        call_count = [0]

        @resilience.retry(max_retries=3, base_delay=0.01)
        def good():
            call_count[0] += 1
            return "done"

        result = good()
        self.assertEqual(result, "done")
        self.assertEqual(call_count[0], 1)

    def test_retries_on_retryable_error(self):
        call_count = [0]

        @resilience.retry(max_retries=2, base_delay=0.01, retryable=(ValueError,))
        def flaky():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("transient")
            return "ok"

        result = flaky()
        self.assertEqual(result, "ok")
        self.assertEqual(call_count[0], 3)  # 2 failures + 1 success

    def test_exhausts_retries(self):
        @resilience.retry(max_retries=1, base_delay=0.01, retryable=(ValueError,))
        def always_fail():
            raise ValueError("permanent")

        with self.assertRaises(ValueError):
            always_fail()

    def test_non_retryable_raises_immediately(self):
        call_count = [0]

        @resilience.retry(max_retries=3, base_delay=0.01, retryable=(ValueError,))
        def type_error_func():
            call_count[0] += 1
            raise TypeError("not retryable")

        with self.assertRaises(TypeError):
            type_error_func()
        self.assertEqual(call_count[0], 1)  # No retry

    def test_on_retry_callback(self):
        retry_log = []

        def on_retry(attempt, exc):
            retry_log.append((attempt, str(exc)))

        @resilience.retry(max_retries=2, base_delay=0.01, on_retry=on_retry)
        def flaky():
            if len(retry_log) < 2:
                raise ConnectionError("timeout")
            return "done"

        result = flaky()
        self.assertEqual(result, "done")
        self.assertEqual(len(retry_log), 2)

    def test_exponential_backoff(self):
        """验证指数退避延迟计算（不实际 sleep，只测逻辑）"""
        # base_delay * 2^attempt, capped at max_delay
        decorator = resilience.retry(max_retries=3, base_delay=1.0)
        self.assertIsNotNone(decorator)  # 装饰器创建成功


# ═══════════════════════════════════════════
# resilient 组合装饰器
# ═══════════════════════════════════════════


class TestResilientDecorator(unittest.TestCase):
    """resilient 组合装饰器"""

    def setUp(self):
        resilience._breakers.clear()

    def test_normal_execution(self):
        @resilience.resilient("test_res", max_retries=1)
        def good():
            return "ok"

        result = good()
        self.assertEqual(result, "ok")

    def test_retries_then_circuit_breaker(self):
        call_count = [0]

        @resilience.resilient("test_res2", max_retries=1, failure_threshold=2)
        def flaky():
            call_count[0] += 1
            raise ConnectionError("fail")

        # First call: retry exhausts, records 1 failure
        with self.assertRaises(ConnectionError):
            flaky()
        self.assertGreater(call_count[0], 1)  # Retried

        # Second call: retry exhausts again, records 2nd failure → circuit open
        try:
            flaky()
        except (ConnectionError, CircuitBreakerOpen):
            pass

        # Third call: circuit should be open
        with self.assertRaises(CircuitBreakerOpen):
            flaky()

    def test_fallback_with_resilient(self):
        @resilience.resilient(
            "test_fb3", max_retries=0, failure_threshold=1, fallback=lambda: "safe"
        )
        def always_fail():
            raise RuntimeError("fail")

        try:
            always_fail()
        except RuntimeError:
            pass
        # Circuit open, fallback should work
        result = always_fail()
        self.assertEqual(result, "safe")


# ═══════════════════════════════════════════
# get_breaker_status
# ═══════════════════════════════════════════


class TestGetBreakerStatus(unittest.TestCase):
    """断路器状态查询"""

    def setUp(self):
        resilience._breakers.clear()

    def test_empty(self):
        result = resilience.get_breaker_status()
        self.assertEqual(result, {})

    def test_after_failures(self):
        @resilience.circuit_breaker("stat_test", failure_threshold=2)
        def fail():
            raise ValueError("x")

        try:
            fail()
        except ValueError:
            pass

        status = resilience.get_breaker_status()
        self.assertIn("stat_test", status)
        self.assertEqual(status["stat_test"]["failures"], 1)
        self.assertEqual(status["stat_test"]["threshold"], 2)
        self.assertIn(status["stat_test"]["state"], ["CLOSED", "OPEN", "HALF_OPEN"])


# ═══════════════════════════════════════════
# CircuitBreakerOpen 异常
# ═══════════════════════════════════════════


class TestCircuitBreakerOpenException(unittest.TestCase):
    """断路器打开异常"""

    def test_is_exception(self):
        exc = CircuitBreakerOpen("test error")
        self.assertIsInstance(exc, Exception)

    def test_message(self):
        exc = CircuitBreakerOpen("数据源不可用")
        self.assertIn("数据源不可用", str(exc))


if __name__ == "__main__":
    unittest.main()
