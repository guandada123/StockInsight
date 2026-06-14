"""测试 analyzer.py — 深度分析引擎（check_national_team / merge_realtime_kline）"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from stock_analyzer.analyzer import _check_national_team, _merge_realtime_kline


class TestCheckNationalTeam(unittest.TestCase):
    """国家队持仓查询测试"""

    @patch("stock_analyzer.cache.cached_national_team_holdings")
    def test_has_national_team(self, mock_cache):
        """有国家队持仓时返回 True 和名单"""
        mock_cache.return_value = {
            "has_national_team": True,
            "holders": ["社保基金", "养老金"]
        }
        has_nt, holders = _check_national_team("000001")
        self.assertTrue(has_nt)
        self.assertIn("社保基金", holders)

    @patch("stock_analyzer.cache.cached_national_team_holdings")
    def test_no_national_team(self, mock_cache):
        """无国家队持仓时返回 False 和空列表"""
        mock_cache.return_value = {"has_national_team": False, "holders": []}
        has_nt, holders = _check_national_team("000001")
        self.assertFalse(has_nt)
        self.assertEqual(holders, [])

    @patch("stock_analyzer.cache.cached_national_team_holdings")
    def test_cache_none(self, mock_cache):
        """缓存返回 None 时不报错"""
        mock_cache.return_value = None
        has_nt, holders = _check_national_team("000001")
        self.assertFalse(has_nt)
        self.assertEqual(holders, [])

    @patch("stock_analyzer.cache.cached_national_team_holdings")
    def test_cache_empty_dict(self, mock_cache):
        """缓存返回空字典时不报错"""
        mock_cache.return_value = {}
        has_nt, holders = _check_national_team("000001")
        self.assertFalse(has_nt)
        self.assertEqual(holders, [])

    @patch("stock_analyzer.cache.cached_national_team_holdings")
    def test_cache_exception(self, mock_cache):
        """缓存抛异常时静默处理"""
        mock_cache.side_effect = RuntimeError("DB error")
        has_nt, holders = _check_national_team("000001")
        self.assertFalse(has_nt)
        self.assertEqual(holders, [])

    @patch("stock_analyzer.cache.cached_national_team_holdings")
    def test_cache_not_dict(self, mock_cache):
        """缓存返回非 dict 时不报错"""
        mock_cache.return_value = "not_a_dict"
        has_nt, holders = _check_national_team("000001")
        self.assertFalse(has_nt)


class TestMergeRealtimeKline(unittest.TestCase):
    """实时行情合并到K线测试"""

    def _make_kline(self, rows=30):
        """生成模拟K线数据"""
        np.random.seed(42)
        close = 50 + np.cumsum(np.random.randn(rows) * 0.5)
        return pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=rows),
            "开盘": close * 0.99,
            "收盘": close,
            "最高": close * 1.02,
            "最低": close * 0.98,
            "成交量": np.random.randint(1_000_000, 10_000_000, rows),
            "成交额": np.random.randint(10_000_000, 100_000_000, rows),
        })

    def test_no_realtime_data(self):
        """无实时行情时返回原数据"""
        kline = self._make_kline(30)
        with patch("stock_analyzer.fetcher.sina_real_time", return_value={}):
            result = _merge_realtime_kline(kline, "000001")
            self.assertEqual(len(result), len(kline))

    def test_realtime_adds_new_day(self):
        """新交易日添加新行"""
        kline = self._make_kline(30)
        fake_rt = {
            "000001": {
                "open": "51.0", "high": "52.0", "low": "50.5",
                "price": "51.5", "volume": "5000000"
            }
        }
        with patch("stock_analyzer.fetcher.sina_real_time", return_value=fake_rt):
            result = _merge_realtime_kline(kline, "000001")
            # 如果今天日期 > 最后日期，会新增一行
            last_date = str(kline["日期"].iloc[-1])[:10]
            today = pd.Timestamp.now().strftime("%Y-%m-%d")
            if today > last_date:
                self.assertEqual(len(result), len(kline) + 1)
                self.assertEqual(float(result.iloc[-1]["收盘"]), 51.5)

    def test_realtime_code_not_in_data(self):
        """代码不在实时数据中返回原数据"""
        kline = self._make_kline(30)
        fake_rt = {"600000": {"open": "10", "high": "11", "low": "9.5", "price": "10.5", "volume": "1000"}}
        with patch("stock_analyzer.fetcher.sina_real_time", return_value=fake_rt):
            result = _merge_realtime_kline(kline, "000001")
            self.assertEqual(len(result), len(kline))

    def test_realtime_zero_price(self):
        """实时价格为0时不合并"""
        kline = self._make_kline(30)
        fake_rt = {"000001": {"open": "0", "high": "0", "low": "0", "price": "0", "volume": "0"}}
        with patch("stock_analyzer.fetcher.sina_real_time", return_value=fake_rt):
            result = _merge_realtime_kline(kline, "000001")
            self.assertEqual(len(result), len(kline))

    def test_realtime_exception(self):
        """sina_real_time 抛异常时静默处理"""
        kline = self._make_kline(30)
        with patch("stock_analyzer.fetcher.sina_real_time", side_effect=ConnectionError("timeout")):
            result = _merge_realtime_kline(kline, "000001")
            self.assertEqual(len(result), len(kline))

    def test_result_preserves_columns(self):
        """合并后保留原有列"""
        kline = self._make_kline(30)
        fake_rt = {
            "000001": {
                "open": "51.0", "high": "52.0", "low": "50.5",
                "price": "51.5", "volume": "5000000"
            }
        }
        with patch("stock_analyzer.fetcher.sina_real_time", return_value=fake_rt):
            result = _merge_realtime_kline(kline, "000001")
            for col in ["日期", "开盘", "收盘", "最高", "最低", "成交量"]:
                self.assertIn(col, result.columns)


if __name__ == "__main__":
    unittest.main()
