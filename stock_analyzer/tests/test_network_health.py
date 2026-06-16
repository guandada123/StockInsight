"""测试 network_health.py — 网络数据源健康监测"""
import os
import sys
import time
import unittest
from unittest.mock import patch, MagicMock
from stock_analyzer.network_health import (
    SourceStatus,
    NetworkHealth,
    _quick_get,
    check_all,
    get_health,
    print_health,
)

class TestSourceStatus(unittest.TestCase):
    """SourceStatus dataclass 基础行为"""

    def test_default_values(self):
        """默认值正确"""
        s = SourceStatus("sina")
        self.assertEqual(s.name, "sina")
        self.assertFalse(s.available)
        self.assertEqual(s.latency_ms, 9999)
        self.assertEqual(s.error, "")

    def test_custom_values(self):
        """自定义值"""
        s = SourceStatus("tencent", True, 123, "ok")
        self.assertTrue(s.available)
        self.assertEqual(s.latency_ms, 123)

class TestNetworkHealth(unittest.TestCase):
    """NetworkHealth dataclass 属性"""

    def setUp(self):
        self.h = NetworkHealth()
        self.h.sina = SourceStatus("sina", True, 200)
        self.h.tencent = SourceStatus("tencent", True, 300)
        self.h.baostock = SourceStatus("baostock", True, 500)

    def test_best_kline_source_picks_fastest(self):
        """best_kline_source 返回延迟最低的可用源"""
        self.assertEqual(self.h.best_kline_source, "sina")

    def test_best_kline_source_fallback(self):
        """没有可用源时兜底 baostock"""
        for s in [self.h.sina, self.h.tencent, self.h.baostock]:
            s.available = False
        self.assertEqual(self.h.best_kline_source, "baostock")

    def test_all_ok_true(self):
        """sina 或 tencent 任一可用"""
        self.assertTrue(self.h.all_ok)

    def test_all_ok_false(self):
        """全部不可用"""
        self.h.sina.available = False
        self.h.tencent.available = False
        self.assertFalse(self.h.all_ok)

    def test_mode_fast(self):
        """sina 可用且延迟<500 → fast"""
        self.assertEqual(self.h.mode, "fast")

    def test_mode_normal(self):
        """sina 延迟高但 tencent 可用 → normal"""
        self.h.sina.latency_ms = 600
        self.assertEqual(self.h.mode, "normal")

    def test_mode_offline(self):
        """全部不可用 → offline"""
        self.h.sina.available = False
        self.h.tencent.available = False
        self.assertEqual(self.h.mode, "offline")

    def test_checked_at_stamp(self):
        """checked_at 为 timestamp"""
        t = time.time()
        self.h.checked_at = t
        self.assertAlmostEqual(self.h.checked_at, t, delta=1)

class TestQuickGet(unittest.TestCase):
    """_quick_get 网络请求"""

    @patch("stock_analyzer.network_health.requests.Session")
    def test_successful_get(self, mock_session):
        """正常响应 → 返回(延迟ms, True)"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "x" * 200
        mock_session.return_value.get.return_value = mock_resp

        ms, ok = _quick_get("http://example.com")
        self.assertTrue(ok)
        self.assertGreater(ms, 0)

    @patch("stock_analyzer.network_health.requests.Session")
    def test_http_error(self, mock_session):
        """HTTP 异常 → 返回(9999, False)"""
        mock_session.return_value.get.side_effect = Exception("timeout")

        ms, ok = _quick_get("http://example.com")
        self.assertFalse(ok)
        self.assertEqual(ms, 9999)

    @patch("stock_analyzer.network_health.requests.Session")
    def test_short_response_is_failure(self, mock_session):
        """响应正文不足 100 字符 → 失败"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "OK"
        mock_session.return_value.get.return_value = mock_resp

        ms, ok = _quick_get("http://example.com")
        self.assertFalse(ok)

class TestCheckAll(unittest.TestCase):
    """check_all 集成检查"""

    @patch("stock_analyzer.network_health._quick_get")
    def test_all_sources_checked(self, mock_get):
        """三个数据源都被检测"""
        mock_get.side_effect = [(150, True), (200, True), (300, True)]

        h = check_all()
        self.assertEqual(h.sina.latency_ms, 150)
        self.assertTrue(h.sina.available)
        self.assertEqual(h.tencent.latency_ms, 200)
        self.assertTrue(h.tencent.available)
        self.assertEqual(h.eastmoney.latency_ms, 300)
        self.assertTrue(h.eastmoney.available)

    @patch("stock_analyzer.network_health._quick_get")
    def test_partial_failure(self, mock_get):
        """部分源失败"""
        mock_get.side_effect = [(150, True), (9999, False), (300, True)]

        h = check_all()
        self.assertTrue(h.sina.available)
        self.assertFalse(h.tencent.available)
        self.assertEqual(h.tencent.error, "超时或不可达")
        self.assertTrue(h.eastmoney.available)

    @patch("stock_analyzer.network_health._quick_get")
    def test_checked_at_is_set(self, mock_get):
        """checked_at 被设置"""
        mock_get.return_value = (200, True)
        h = check_all()
        self.assertGreater(h.checked_at, 0)

class TestGetHealth(unittest.TestCase):
    """get_health 缓存行为"""

    def setUp(self):
        import stock_analyzer.network_health as nh
        nh._health_cache = None
        nh._health_cache_time = 0
        self.patcher = patch("stock_analyzer.network_health.check_all")
        self.mock_check = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_first_call_invokes_check(self):
        """首次调用触发 check_all"""
        self.mock_check.return_value = NetworkHealth()
        get_health()
        self.mock_check.assert_called_once()

    def test_cache_used_within_ttl(self):
        """10 分钟内走缓存，不重复调用"""
        self.mock_check.return_value = NetworkHealth()
        get_health()
        get_health()
        self.mock_check.assert_called_once()

    def test_force_refresh(self):
        """force=True 强制重新检测"""
        self.mock_check.return_value = NetworkHealth()
        get_health(force=True)
        self.assertEqual(self.mock_check.call_count, 1)

class TestPrintHealth(unittest.TestCase):
    """print_health 输出"""

    @patch("stock_analyzer.network_health.get_health")
    def test_print_does_not_crash(self, mock_get):
        """正常输出"""
        h = NetworkHealth()
        h.sina = SourceStatus("sina", True, 150)
        h.tencent = SourceStatus("tencent", False, 9999, "超时")
        h.eastmoney = SourceStatus("eastmoney", True, 300)
        mock_get.return_value = h

        # 确保不会抛出异常
        result = print_health()
        self.assertIs(result, h)

if __name__ == "__main__":
    unittest.main()
