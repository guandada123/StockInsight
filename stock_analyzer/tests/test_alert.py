"""测试 alert.py — 预警系统 (CRUD + 检查逻辑 + 飞书推送)"""

import json
import os
import sys
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

        alert_id = add_alert(
            {"type": "price", "code": "000001", "direction": "above", "target": 15}
        )
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
        triggered, msg = _check_price_alert(
            {"code": "000001", "direction": "above", "target": 15.0}
        )
        self.assertTrue(triggered)
        self.assertIn("000001", msg)
        self.assertIn("15.5", msg)

    @patch("stock_analyzer.alert._get_current_price")
    def test_above_not_triggered(self, mock_price):
        """价格未突破不触发"""
        from stock_analyzer.alert import _check_price_alert

        mock_price.return_value = 14.0
        triggered, msg = _check_price_alert(
            {"code": "000001", "direction": "above", "target": 15.0}
        )
        self.assertFalse(triggered)

    @patch("stock_analyzer.alert._get_current_price")
    def test_below_triggered(self, mock_price):
        """价格跌破目标触发"""
        from stock_analyzer.alert import _check_price_alert

        mock_price.return_value = 9.5
        triggered, msg = _check_price_alert(
            {"code": "600000", "direction": "below", "target": 10.0}
        )
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
        triggered, msg = _check_fundamental_alert(
            {"code": "000001", "metric": "ROE", "condition": "<10"}
        )
        self.assertTrue(triggered)
        self.assertIn("ROE", msg)

    @patch("stock_analyzer.alert.cached_fundamentals")
    def test_roe_above_no_trigger(self, mock_funda):
        """ROE 高于阈值不触发"""
        from stock_analyzer.alert import _check_fundamental_alert

        mock_funda.return_value = {"ROE": 18.0}
        triggered, msg = _check_fundamental_alert(
            {"code": "000001", "metric": "ROE", "condition": "<10"}
        )
        self.assertFalse(triggered)

    @patch("stock_analyzer.alert.cached_fundamentals")
    def test_metric_missing(self, mock_funda):
        """指标不存在返回 None"""
        from stock_analyzer.alert import _check_fundamental_alert

        mock_funda.return_value = {"ROE": 15}
        result, msg = _check_fundamental_alert(
            {"code": "000001", "metric": "市盈率", "condition": "<10"}
        )
        self.assertIsNone(result)

    @patch("stock_analyzer.alert.cached_fundamentals")
    def test_invalid_condition(self, mock_funda):
        """非法条件表达式返回 None"""
        from stock_analyzer.alert import _check_fundamental_alert

        mock_funda.return_value = {"ROE": 15}
        result, msg = _check_fundamental_alert(
            {"code": "000001", "metric": "ROE", "condition": "abc"}
        )
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

    @patch("urllib.request.urlopen")
    def test_http_success(self, mock_urlopen):
        """飞书推送成功"""
        os.environ["FEISHU_WEBHOOK_URL"] = "https://example.com/hook"
        os.environ["FEISHU_ALERTS_ENABLED"] = "1"

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"code": 0}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        from stock_analyzer.alert import _notify_via_feishu

        result = _notify_via_feishu([{"type": "price", "message": "test"}])
        self.assertTrue(result)

    @patch("urllib.request.urlopen")
    def test_http_fail_code(self, mock_urlopen):
        """飞书返回错误码"""
        os.environ["FEISHU_WEBHOOK_URL"] = "https://example.com/hook"
        os.environ["FEISHU_ALERTS_ENABLED"] = "1"

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"code": 10001}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        from stock_analyzer.alert import _notify_via_feishu

        result = _notify_via_feishu([{"type": "price", "message": "test"}])
        self.assertFalse(result)

    @patch("urllib.request.urlopen")
    def test_http_exception(self, mock_urlopen):
        """飞书请求异常不崩溃"""
        os.environ["FEISHU_WEBHOOK_URL"] = "https://example.com/hook"
        os.environ["FEISHU_ALERTS_ENABLED"] = "1"

        mock_urlopen.side_effect = RuntimeError("timeout")

        from stock_analyzer.alert import _notify_via_feishu

        result = _notify_via_feishu([{"type": "price", "message": "test"}])
        self.assertFalse(result)


class TestVolumeAlert(unittest.TestCase):
    """放量预警测试"""

    @patch("stock_analyzer.alert.cached_kline")
    def test_triggered(self, mock_kline):
        """成交量超过 multiplier 倍 20日均量"""
        from stock_analyzer.alert import _check_volume_alert

        df = _make_kline_df({"成交量": [100] * 20 + [300]})
        mock_kline.return_value = df
        triggered, msg = _check_volume_alert({"code": "600000", "multiplier": 2.0})
        self.assertTrue(triggered)
        self.assertIn("600000", msg)
        self.assertIn("放量", msg)

    @patch("stock_analyzer.alert.cached_kline")
    def test_not_triggered(self, mock_kline):
        """成交量未超过倍数"""
        from stock_analyzer.alert import _check_volume_alert

        df = _make_kline_df({"成交量": [100] * 20 + [150]})
        mock_kline.return_value = df
        triggered, msg = _check_volume_alert({"code": "600000", "multiplier": 2.0})
        self.assertFalse(triggered)

    @patch("stock_analyzer.alert.cached_kline")
    def test_empty_df(self, mock_kline):
        """空 DataFrame"""
        import pandas as pd

        from stock_analyzer.alert import _check_volume_alert

        mock_kline.return_value = pd.DataFrame()
        result, msg = _check_volume_alert({"code": "600000", "multiplier": 2.0})
        self.assertIsNone(result)

    @patch("stock_analyzer.alert.cached_kline")
    def test_too_short(self, mock_kline):
        """K线不足 21 天"""
        from stock_analyzer.alert import _check_volume_alert

        df = _make_kline_df({"成交量": [100] * 10})
        mock_kline.return_value = df
        result, msg = _check_volume_alert({"code": "600000", "multiplier": 2.0})
        self.assertIsNone(result)

    @patch("stock_analyzer.alert.cached_kline")
    def test_avg_volume_zero(self, mock_kline):
        """均量为零"""
        from stock_analyzer.alert import _check_volume_alert

        df = _make_kline_df({"成交量": [0] * 21})
        mock_kline.return_value = df
        result, msg = _check_volume_alert({"code": "600000", "multiplier": 2.0})
        self.assertIsNone(result)
        self.assertIn("均量为零", msg)


class TestTechnicalAlert(unittest.TestCase):
    """技术指标预警测试"""

    def _make_tech_df(self, rsi_val=50, dif=None, dea=None):
        """构造含技术指标数据的 DataFrame（已通过 full_technical_analysis）"""
        import pandas as pd

        df = pd.DataFrame(
            {
                "close": [10.0] * 5,
                "high": [11.0] * 5,
                "low": [9.0] * 5,
                "volume": [100] * 5,
                "RSI": [float(rsi_val)] * 5,
            }
        )
        if dif is not None:
            df["DIF"] = [float(dif)] * 5
        if dea is not None:
            df["DEA"] = [float(dea)] * 5
        return df

    @patch("stock_analyzer.alert.full_technical_analysis")
    @patch("stock_analyzer.alert.cached_kline")
    def test_rsi_overbought(self, mock_kline, mock_ta):
        """RSI > 80 超买触发"""
        from stock_analyzer.alert import _check_technical_alert

        df = self._make_tech_df(rsi_val=85)
        mock_kline.return_value = df
        mock_ta.return_value = df
        triggered, msg = _check_technical_alert(
            {"code": "000001", "indicator": "RSI", "condition": ">80"}
        )
        self.assertTrue(triggered)
        self.assertIn("超买", msg)

    @patch("stock_analyzer.alert.full_technical_analysis")
    @patch("stock_analyzer.alert.cached_kline")
    def test_rsi_oversold(self, mock_kline, mock_ta):
        """RSI < 20 超卖触发"""
        from stock_analyzer.alert import _check_technical_alert

        df = self._make_tech_df(rsi_val=15)
        mock_kline.return_value = df
        mock_ta.return_value = df
        triggered, msg = _check_technical_alert(
            {"code": "000001", "indicator": "RSI", "condition": "<20"}
        )
        self.assertTrue(triggered)
        self.assertIn("超卖", msg)

    @patch("stock_analyzer.alert.full_technical_analysis")
    @patch("stock_analyzer.alert.cached_kline")
    def test_rsi_custom_threshold_above(self, mock_kline, mock_ta):
        """RSI 自定义 >75"""
        from stock_analyzer.alert import _check_technical_alert

        df = self._make_tech_df(rsi_val=80)
        mock_kline.return_value = df
        mock_ta.return_value = df
        triggered, msg = _check_technical_alert(
            {"code": "000001", "indicator": "RSI", "condition": ">75"}
        )
        self.assertTrue(triggered)
        self.assertIn("80", msg)

    @patch("stock_analyzer.alert.full_technical_analysis")
    @patch("stock_analyzer.alert.cached_kline")
    def test_rsi_custom_threshold_below(self, mock_kline, mock_ta):
        """RSI 自定义 <25"""
        from stock_analyzer.alert import _check_technical_alert

        df = self._make_tech_df(rsi_val=20)
        mock_kline.return_value = df
        mock_ta.return_value = df
        triggered, msg = _check_technical_alert(
            {"code": "000001", "indicator": "RSI", "condition": "<25"}
        )
        self.assertTrue(triggered)
        self.assertIn("20", msg)

    @patch("stock_analyzer.alert.full_technical_analysis")
    @patch("stock_analyzer.alert.cached_kline")
    def test_rsi_not_triggered(self, mock_kline, mock_ta):
        """RSI 在中间区间不触发"""
        from stock_analyzer.alert import _check_technical_alert

        df = self._make_tech_df(rsi_val=50)
        mock_kline.return_value = df
        mock_ta.return_value = df
        triggered, msg = _check_technical_alert(
            {"code": "000001", "indicator": "RSI", "condition": ">80"}
        )
        self.assertFalse(triggered)

    @patch("stock_analyzer.alert.full_technical_analysis")
    @patch("stock_analyzer.alert.cached_kline")
    def test_macd_golden_cross(self, mock_kline, mock_ta):
        """MACD 金叉触发"""
        from stock_analyzer.alert import _check_technical_alert

        # prev: DIF=-0.1 < DEA=0.0, now: DIF=0.1 > DEA=0.0
        df = _make_macd_df(prev_dif=-0.1, prev_dea=0.0, now_dif=0.1, now_dea=0.0)
        mock_kline.return_value = df
        mock_ta.return_value = df
        triggered, msg = _check_technical_alert(
            {"code": "000001", "indicator": "MACD", "condition": "金叉"}
        )
        self.assertTrue(triggered)
        self.assertIn("金叉", msg)

    @patch("stock_analyzer.alert.full_technical_analysis")
    @patch("stock_analyzer.alert.cached_kline")
    def test_macd_death_cross(self, mock_kline, mock_ta):
        """MACD 死叉触发"""
        from stock_analyzer.alert import _check_technical_alert

        # prev: DIF=0.1 > DEA=0.0, now: DIF=-0.1 < DEA=0.0
        df = _make_macd_df(prev_dif=0.1, prev_dea=0.0, now_dif=-0.1, now_dea=0.0)
        mock_kline.return_value = df
        mock_ta.return_value = df
        triggered, msg = _check_technical_alert(
            {"code": "000001", "indicator": "MACD", "condition": "死叉"}
        )
        self.assertTrue(triggered)
        self.assertIn("死叉", msg)

    @patch("stock_analyzer.alert.full_technical_analysis")
    @patch("stock_analyzer.alert.cached_kline")
    def test_macd_custom_condition(self, mock_kline, mock_ta):
        """MACD 自定义 DIF>0.5"""
        from stock_analyzer.alert import _check_technical_alert

        df = _make_macd_df(prev_dif=0.3, prev_dea=0.2, now_dif=0.6, now_dea=0.3)
        mock_kline.return_value = df
        mock_ta.return_value = df
        triggered, msg = _check_technical_alert(
            {"code": "000001", "indicator": "MACD", "condition": "DIF>0.5"}
        )
        self.assertTrue(triggered)
        self.assertIn("0.6", msg)

    @patch("stock_analyzer.alert.full_technical_analysis")
    @patch("stock_analyzer.alert.cached_kline")
    def test_unknown_indicator(self, mock_kline, mock_ta):
        """不支持的技术指标"""
        from stock_analyzer.alert import _check_technical_alert

        df = _make_kline_df({"close": [10.0] * 5})
        mock_kline.return_value = df
        mock_ta.return_value = df
        result, msg = _check_technical_alert(
            {"code": "000001", "indicator": "BOLL", "condition": ">80"}
        )
        self.assertIsNone(result)

    @patch("stock_analyzer.alert.cached_kline")
    def test_empty_df(self, mock_kline):
        """空 DataFrame（在 full_technical_analysis 调用前就返回）"""
        import pandas as pd

        from stock_analyzer.alert import _check_technical_alert

        mock_kline.return_value = pd.DataFrame()
        result, msg = _check_technical_alert(
            {"code": "000001", "indicator": "RSI", "condition": ">80"}
        )
        self.assertIsNone(result)

    @patch("stock_analyzer.alert.full_technical_analysis")
    @patch("stock_analyzer.alert.cached_kline")
    def test_rsi_nan(self, mock_kline, mock_ta):
        """RSI 值为 NaN"""
        from stock_analyzer.alert import _check_technical_alert

        df = _make_kline_df({"close": [10.0] * 5})
        df["RSI"] = float("nan")
        mock_kline.return_value = df
        mock_ta.return_value = df
        result, msg = _check_technical_alert(
            {"code": "000001", "indicator": "RSI", "condition": ">80"}
        )
        self.assertIsNone(result)

    @patch("stock_analyzer.alert.full_technical_analysis")
    @patch("stock_analyzer.alert.cached_kline")
    def test_macd_nan(self, mock_kline, mock_ta):
        """MACD 值为 NaN"""
        from stock_analyzer.alert import _check_technical_alert

        df = _make_kline_df({"close": [10.0] * 5})
        df["DIF"] = float("nan")
        df["DEA"] = float("nan")
        mock_kline.return_value = df
        mock_ta.return_value = df
        result, msg = _check_technical_alert(
            {"code": "000001", "indicator": "MACD", "condition": "金叉"}
        )
        self.assertIsNone(result)


class TestCheckAlertsDispatch(unittest.TestCase):
    """check_alerts 全部分发分支 + 异常处理"""

    def setUp(self):
        self._patcher = patch("stock_analyzer.alert.ALERTS_PATH", TMP_ALERTS)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    @patch("stock_analyzer.alert._check_volume_alert")
    def test_volume_dispatch_triggered(self, mock_check):
        """volume 类型分发且触发"""
        from stock_analyzer.alert import check_alerts

        mock_check.return_value = (True, "放量预警 test")
        result = check_alerts(
            [{"type": "volume", "code": "600000", "multiplier": 2.0, "enabled": True}]
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "volume")
        self.assertEqual(result[0]["code"], "600000")

    @patch("stock_analyzer.alert._check_technical_alert")
    def test_technical_dispatch_triggered(self, mock_check):
        """technical 类型分发且触发"""
        from stock_analyzer.alert import check_alerts

        mock_check.return_value = (True, "技术预警 test")
        result = check_alerts(
            [
                {
                    "type": "technical",
                    "code": "300750",
                    "indicator": "RSI",
                    "condition": ">80",
                    "enabled": True,
                }
            ]
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "technical")

    @patch("stock_analyzer.alert._check_fundamental_alert")
    def test_fundamental_dispatch_triggered(self, mock_check):
        """fundamental 类型分发且触发"""
        from stock_analyzer.alert import check_alerts

        mock_check.return_value = (True, "基本面预警 test")
        result = check_alerts(
            [
                {
                    "type": "fundamental",
                    "code": "000001",
                    "metric": "ROE",
                    "condition": "<10",
                    "enabled": True,
                }
            ]
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "fundamental")

    def test_exception_does_not_crash(self):
        """检查出现异常时跳过该条，不崩溃"""
        from stock_analyzer.alert import check_alerts

        result = check_alerts(
            [
                {
                    "type": "price",
                    "code": "000001",
                    "direction": "above",
                    "target": 15,
                    "enabled": True,
                }
            ]
        )
        # _get_current_price 没 mock，调用 sina_real_time 会抛异常
        # 但 check_alerts 应该捕获并继续
        self.assertEqual(result, [])


class TestRunAllAlertsTriggered(unittest.TestCase):
    """run_all_alerts 触发态测试"""

    def setUp(self):
        self._patcher = patch("stock_analyzer.alert.ALERTS_PATH", TMP_ALERTS)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    @patch("stock_analyzer.alert._get_current_price", return_value=12.0)
    @patch("stock_analyzer.alert._notify_via_feishu")
    @patch("stock_analyzer.alert.LOG_PATH", TMP_ALERTS_LOG)
    @patch("stock_analyzer.alert.os.makedirs")
    def test_with_triggered_alerts(self, mock_makedirs, mock_notify, mock_price):
        """触发的预警写入日志并返回"""
        from stock_analyzer.alert import add_alert, run_all_alerts

        add_alert({"type": "price", "code": "000001", "direction": "above", "target": 10.0})
        result = run_all_alerts()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "price")

        # 验证日志写入
        self.assertTrue(os.path.exists(TMP_ALERTS_LOG))
        with open(TMP_ALERTS_LOG, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("000001", content)


class TestAlertEdgeCases(unittest.TestCase):
    """边缘情况测试"""

    def setUp(self):
        self._patcher = patch("stock_analyzer.alert.ALERTS_PATH", TMP_ALERTS)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_load_corrupt_json(self):
        """损坏的 JSON 返回空列表"""
        with open(TMP_ALERTS, "w", encoding="utf-8") as f:
            f.write("{corrupt json")
        from stock_analyzer.alert import load_alerts

        self.assertEqual(load_alerts(), [])

    @patch("stock_analyzer.alert.sina_real_time")
    def test_get_current_price_found(self, mock_sina):
        """获取实时价格成功"""
        from stock_analyzer.alert import _get_current_price

        mock_sina.return_value = {"000001": {"最新价": 15.5}}
        price = _get_current_price("000001")
        self.assertEqual(price, 15.5)

    @patch("stock_analyzer.alert.sina_real_time")
    def test_get_current_price_not_found(self, mock_sina):
        """股票不在返回中时返回 None"""
        from stock_analyzer.alert import _get_current_price

        mock_sina.return_value = {}
        price = _get_current_price("000001")
        self.assertIsNone(price)


class TestTechnicalAlertEdgeCases(unittest.TestCase):
    """技术指标预警边缘分支补齐"""

    @patch("stock_analyzer.alert.full_technical_analysis")
    @patch("stock_analyzer.alert.cached_kline")
    def test_ta_returns_empty_df(self, mock_kline, mock_ta):
        """full_technical_analysis 返回空 DF（line 171）"""
        import pandas as pd

        from stock_analyzer.alert import _check_technical_alert

        mock_kline.return_value = _make_kline_df({"close": [10.0] * 5})
        mock_ta.return_value = pd.DataFrame()
        result, msg = _check_technical_alert(
            {"code": "000001", "indicator": "RSI", "condition": ">80"}
        )
        self.assertIsNone(result)

    @patch("stock_analyzer.alert.full_technical_analysis")
    @patch("stock_analyzer.alert.cached_kline")
    def test_macd_ge_condition(self, mock_kline, mock_ta):
        """MACD 自定义 >= 条件"""
        from stock_analyzer.alert import _check_technical_alert

        df = _make_macd_df(prev_dif=0.1, prev_dea=0.05, now_dif=0.5, now_dea=0.3)
        mock_kline.return_value = df
        mock_ta.return_value = df
        triggered, msg = _check_technical_alert(
            {"code": "000001", "indicator": "MACD", "condition": "DIF>=0.5"}
        )
        self.assertTrue(triggered)

    @patch("stock_analyzer.alert.full_technical_analysis")
    @patch("stock_analyzer.alert.cached_kline")
    def test_macd_le_condition(self, mock_kline, mock_ta):
        """MACD 自定义 <= 条件"""
        from stock_analyzer.alert import _check_technical_alert

        df = _make_macd_df(prev_dif=0.5, prev_dea=0.3, now_dif=0.1, now_dea=0.2)
        mock_kline.return_value = df
        mock_ta.return_value = df
        triggered, msg = _check_technical_alert(
            {"code": "000001", "indicator": "MACD", "condition": "DEA<=0.2"}
        )
        self.assertTrue(triggered)

    @patch("stock_analyzer.alert.full_technical_analysis")
    @patch("stock_analyzer.alert.cached_kline")
    def test_macd_custom_col_none(self, mock_kline, mock_ta):
        """MACD 自定义条件的列值为 None"""
        from stock_analyzer.alert import _check_technical_alert

        df = _make_macd_df(prev_dif=0.1, prev_dea=0.05, now_dif=0.5, now_dea=0.3)
        del df["DIF"]  # 移除 DIF 列
        df["DIF"] = None  # 设为 None
        mock_kline.return_value = df
        mock_ta.return_value = df
        result, msg = _check_technical_alert(
            {"code": "000001", "indicator": "MACD", "condition": "DIF>0.5"}
        )
        self.assertIsNone(result)

    @patch("stock_analyzer.alert.full_technical_analysis")
    @patch("stock_analyzer.alert.cached_kline")
    def test_macd_custom_not_triggered(self, mock_kline, mock_ta):
        """MACD 自定义条件未触发"""
        from stock_analyzer.alert import _check_technical_alert

        df = _make_macd_df(prev_dif=0.1, prev_dea=0.05, now_dif=0.3, now_dea=0.2)
        mock_kline.return_value = df
        mock_ta.return_value = df
        triggered, msg = _check_technical_alert(
            {"code": "000001", "indicator": "MACD", "condition": "DIF>0.5"}
        )
        self.assertFalse(triggered)


class TestCheckAlertsException(unittest.TestCase):
    """check_alerts 异常处理（line 327-328）"""

    @patch("stock_analyzer.alert._check_price_alert")
    def test_exception_caught(self, mock_check):
        """检查函数抛出异常被捕获"""
        from stock_analyzer.alert import check_alerts

        mock_check.side_effect = ValueError("some error")
        result = check_alerts(
            [
                {
                    "type": "price",
                    "code": "000001",
                    "direction": "above",
                    "target": 15,
                    "enabled": True,
                    "id": "test-id",
                }
            ]
        )
        self.assertEqual(result, [])


def _make_kline_df(data):
    """构造测试用 DataFrame"""
    import pandas as pd

    return pd.DataFrame(data)


def _make_macd_df(prev_dif, prev_dea, now_dif, now_dea):
    """构造含两行 MACD 数据的 DataFrame"""
    df = _make_kline_df(
        {
            "close": [10.0, 10.0],
            "high": [11.0, 11.0],
            "low": [9.0, 9.0],
            "volume": [100, 100],
            "DIF": [prev_dif, now_dif],
            "DEA": [prev_dea, now_dea],
        }
    )
    return df


if __name__ == "__main__":
    unittest.main()
