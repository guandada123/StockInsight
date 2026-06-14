"""测试 alert.py — 预警系统 (CRUD + 检查逻辑 + 飞书推送)"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tempfile
import unittest
from unittest.mock import MagicMock, patch

# 使用临时文件避免影响线上 alert 文件
TMP_ALERTS = os.path.join(tempfile.gettempdir(), "test_alerts.json")
TMP_ALERTS_LOG = os.path.join(tempfile.gettempdir(), "test_alerts_log.txt")

os.environ["FEISHU_ALERTS_ENABLED"] = "0"  # 禁用飞书推送


class TestAlertCRUD(unittest.TestCase):
    """预警 CRUD 操作测试"""

    @classmethod
    def setUpClass(cls):
        # 清理临时文件
        for f in [TMP_ALERTS, TMP_ALERTS_LOG]:
            try:
                os.remove(f)
            except OSError:
                pass

    def setUp(self):
        # mock 配置路径
        self._patchers = [
            patch("stock_analyzer.alert.ALERTS_PATH", TMP_ALERTS),
            patch("stock_analyzer.alert.ALERTS_LOG_PATH", TMP_ALERTS_LOG),
        ]
        for p in self._patchers:
            p.start()
        # 清空文件
        for f in [TMP_ALERTS, TMP_ALERTS_LOG]:
            try:
                os.remove(f)
            except OSError:
                pass

    def tearDown(self):
        for p in self._patchers:
            p.stop()

    def test_load_alerts_empty(self):
        """文件不存在时返回空列表"""
        from stock_analyzer.alert import load_alerts
        self.assertEqual(load_alerts(), [])

    def test_load_alerts_empty_file(self):
        """空文件返回空列表"""
        with open(TMP_ALERTS, "w") as f:
            f.write("")
        from stock_analyzer.alert import load_alerts
        self.assertEqual(load_alerts(), [])

    def test_add_and_load(self):
        """添加后能加载"""
        from stock_analyzer.alert import add_alert, load_alerts

        alert_id = add_alert({"type": "price", "code": "000001", "direction": "above", "target": 15})
        self.assertIsInstance(alert_id, str)
        self.assertEqual(len(alert_id), 8)

        alerts = load_alerts()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["type"], "price")
        self.assertEqual(alerts[0]["code"], "000001")
        self.assertIn("enabled", alerts[0])

    def test_remove_alert(self):
        """删除已存在的预警"""
        from stock_analyzer.alert import add_alert, load_alerts, remove_alert

        alert_id = add_alert({"type": "volume", "code": "600000", "multiplier": 2.0})
        self.assertEqual(len(load_alerts()), 1)
        self.assertTrue(remove_alert(alert_id))
        self.assertEqual(len(load_alerts()), 0)

    def test_remove_nonexistent(self):
        """删除不存在的 ID"""
        from stock_analyzer.alert import remove_alert
        self.assertFalse(remove_alert("nonexistent"))

    def test_multiple_alerts(self):
        """多条预警同时存在"""
        from stock_analyzer.alert import add_alert, load_alerts

        add_alert({"type": "price", "code": "000001", "direction": "above", "target": 15})
        add_alert({"type": "volume", "code": "600000", "multiplier": 3.0})
        add_alert({"type": "technical", "code": "300750", "indicator": "RSI", "condition": "<20"})
        self.assertEqual(len(load_alerts()), 3)

    def test_add_without_enabled(self):
        """不传 enabled 默认 True"""
        from stock_analyzer.alert import add_alert, load_alerts

        alert_id = add_alert({"type": "price", "code": "000001", "direction": "below", "target": 5})
        alert = next(a for a in load_alerts() if a["id"] == alert_id)
        self.assertTrue(alert["enabled"])


class TestCheckAlerts(unittest.TestCase):
    """check_alerts 分发逻辑测试"""

    def setUp(self):
        self._patcher = patch("stock_analyzer.alert.ALERTS_PATH", TMP_ALERTS)
        self._patcher.start()
        try:
            os.remove(TMP_ALERTS)
        except OSError:
            pass

    def tearDown(self):
        self._patcher.stop()

    def test_check_alerts_unknown_type(self):
        """未知类型不报错"""
        from stock_analyzer.alert import check_alerts

        result = check_alerts([{"type": "unknown_type", "code": "000001", "enabled": True}])
        self.assertEqual(result, [])

    def test_check_alerts_disabled(self):
        """禁用的预警跳过"""
        from stock_analyzer.alert import check_alerts

        result = check_alerts([{"type": "price", "code": "000001", "enabled": False}])
        self.assertEqual(result, [])


class TestRunAllAlerts(unittest.TestCase):
    """run_all_alerts 集成测试"""

    def setUp(self):
        self._patcher = patch("stock_analyzer.alert.ALERTS_PATH", TMP_ALERTS)
        self._patcher.start()
        try:
            os.remove(TMP_ALERTS)
        except OSError:
            pass

    def tearDown(self):
        self._patcher.stop()

    def test_run_no_alerts(self):
        """无预警时返回空列表"""
        from stock_analyzer.alert import run_all_alerts
        result = run_all_alerts()
        self.assertEqual(result, [])

    def test_run_with_alerts_no_trigger(self):
        """有预警但未触发"""
        from stock_analyzer.alert import add_alert, run_all_alerts

        add_alert({"type": "price", "code": "000001", "direction": "above", "target": 999999})
        with patch("stock_analyzer.alert._get_current_price", return_value=10.0):
            result = run_all_alerts()
            self.assertEqual(result, [])


class TestPriceAlert(unittest.TestCase):
    """价格预警检查测试（纯逻辑，无需数据库）"""

    @patch("stock_analyzer.alert._get_current_price")
    def test_above_triggered(self, mock_price):
        """价格突破目标触发"""
        from stock_analyzer.alert import _check_price_alert

        mock_price.return_value = 15.5
        triggered, msg = _check_price_alert({"code": "000001", "direction": "above", "target": 15.0})
        self.assertTrue(triggered)
        self.assertIn("000001", msg)
        self.assertIn("15.5", msg)

    @patch("stock_analyzer.alert._get_current_price")
    def test_above_not_triggered(self, mock_price):
        """价格未突破不触发"""
        from stock_analyzer.alert import _check_price_alert

        mock_price.return_value = 14.0
        triggered, msg = _check_price_alert({"code": "000001", "direction": "above", "target": 15.0})
        self.assertFalse(triggered)

    @patch("stock_analyzer.alert._get_current_price")
    def test_below_triggered(self, mock_price):
        """价格跌破目标触发"""
        from stock_analyzer.alert import _check_price_alert

        mock_price.return_value = 9.5
        triggered, msg = _check_price_alert({"code": "600000", "direction": "below", "target": 10.0})
        self.assertTrue(triggered)
        self.assertIn("600000", msg)

    @patch("stock_analyzer.alert._get_current_price")
    def test_price_none(self, mock_price):
        """无法获取价格时返回 None"""
        from stock_analyzer.alert import _check_price_alert

        mock_price.return_value = None
        result, msg = _check_price_alert({"code": "000001", "direction": "above", "target": 15.0})
        self.assertIsNone(result)


class TestFundamentalAlert(unittest.TestCase):
    """基本面预警测试"""

    @patch("stock_analyzer.alert.cached_fundamentals")
    def test_roe_below_trigger(self, mock_funda):
        """ROE 低于阈值触发"""
        from stock_analyzer.alert import _check_fundamental_alert

        mock_funda.return_value = {"ROE": 8.5}
        triggered, msg = _check_fundamental_alert({
            "code": "000001", "metric": "ROE", "condition": "<10"
        })
        self.assertTrue(triggered)
        self.assertIn("ROE", msg)

    @patch("stock_analyzer.alert.cached_fundamentals")
    def test_roe_above_no_trigger(self, mock_funda):
        """ROE 高于阈值不触发"""
        from stock_analyzer.alert import _check_fundamental_alert

        mock_funda.return_value = {"ROE": 18.0}
        triggered, msg = _check_fundamental_alert({
            "code": "000001", "metric": "ROE", "condition": "<10"
        })
        self.assertFalse(triggered)

    @patch("stock_analyzer.alert.cached_fundamentals")
    def test_metric_missing(self, mock_funda):
        """指标不存在返回 None"""
        from stock_analyzer.alert import _check_fundamental_alert

        mock_funda.return_value = {"ROE": 15}
        result, msg = _check_fundamental_alert({
            "code": "000001", "metric": "市盈率", "condition": "<10"
        })
        self.assertIsNone(result)

    @patch("stock_analyzer.alert.cached_fundamentals")
    def test_invalid_condition(self, mock_funda):
        """非法条件表达式返回 None"""
        from stock_analyzer.alert import _check_fundamental_alert

        mock_funda.return_value = {"ROE": 15}
        result, msg = _check_fundamental_alert({
            "code": "000001", "metric": "ROE", "condition": "abc"
        })
        self.assertIsNone(result)


class TestNotifyFeishu(unittest.TestCase):
    """飞书推送测试"""

    def setUp(self):
        self._orig_webhook = os.environ.get("FEISHU_WEBHOOK_URL", "")

    def tearDown(self):
        if self._orig_webhook:
            os.environ["FEISHU_WEBHOOK_URL"] = self._orig_webhook
        else:
            os.environ.pop("FEISHU_WEBHOOK_URL", None)
        os.environ.pop("FEISHU_ALERTS_ENABLED", None)

    def test_no_webhook_returns_false(self):
        """无 webhook 时返回 False"""
        os.environ.pop("FEISHU_WEBHOOK_URL", None)
        os.environ.pop("FEISHU_WEBHOOK", None)
        os.environ["FEISHU_ALERTS_ENABLED"] = "1"

        from stock_analyzer.alert import _notify_via_feishu
        result = _notify_via_feishu([{"type": "price", "message": "test"}])
        self.assertFalse(result)

    def test_disabled_returns_false(self):
        """FEISHU_ALERTS_ENABLED=0 时跳过"""
        os.environ.pop("FEISHU_WEBHOOK_URL", None)
        os.environ["FEISHU_WEBHOOK"] = "https://example.com/hook"
        os.environ["FEISHU_ALERTS_ENABLED"] = "0"

        from stock_analyzer.alert import _notify_via_feishu
        result = _notify_via_feishu([{"type": "price", "message": "test"}])
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
