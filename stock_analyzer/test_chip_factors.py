"""测试 chip_factors.py — 量价配合 / 换手率分析（纯逻辑函数）"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest

import numpy as np
import pandas as pd

from stock_analyzer.chip_factors import calc_turnover_analysis, calc_volume_price_factors


def _make_kline_df(rows=60, seed=42):
    """生成标准K线DataFrame"""
    np.random.seed(seed)
    close = 50 + np.cumsum(np.random.randn(rows) * 0.5)
    return pd.DataFrame({
        "日期": pd.date_range("2025-01-01", periods=rows),
        "开盘": close * (1 - np.abs(np.random.randn(rows) * 0.005)),
        "收盘": close,
        "最高": close * (1 + np.abs(np.random.randn(rows) * 0.01)),
        "最低": close * (1 - np.abs(np.random.randn(rows) * 0.01)),
        "成交量": np.random.randint(500_000, 5_000_000, rows),
    })


class TestVolumePriceFactors(unittest.TestCase):
    """量价配合因子"""

    def test_returns_dict(self):
        kline = _make_kline_df(60)
        result = calc_volume_price_factors(kline)
        self.assertIsInstance(result, dict)

    def test_has_expected_keys(self):
        kline = _make_kline_df(60)
        result = calc_volume_price_factors(kline)
        for key in ["量价配合度评分", "放量上涨天数", "缩量下跌天数", "量价状态"]:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_score_range(self):
        kline = _make_kline_df(60)
        result = calc_volume_price_factors(kline)
        self.assertGreaterEqual(result["量价配合度评分"], 0)
        self.assertLessEqual(result["量价配合度评分"], 100)

    def test_insufficient_data(self):
        kline = _make_kline_df(10)
        result = calc_volume_price_factors(kline)
        self.assertEqual(result["量价配合度评分"], 50)

    def test_none_input(self):
        result = calc_volume_price_factors(None)
        self.assertEqual(result["量价配合度评分"], 50)

    def test_state_is_valid(self):
        kline = _make_kline_df(60)
        result = calc_volume_price_factors(kline)
        self.assertIn(result["量价状态"], ["健康", "一般", "背离"])

    def test_up_days_non_negative(self):
        kline = _make_kline_df(60)
        result = calc_volume_price_factors(kline)
        self.assertGreaterEqual(result["放量上涨天数"], 0)

    def test_down_days_non_negative(self):
        kline = _make_kline_df(60)
        result = calc_volume_price_factors(kline)
        self.assertGreaterEqual(result["缩量下跌天数"], 0)


class TestTurnoverAnalysis(unittest.TestCase):
    """换手率分析因子"""

    def test_returns_dict(self):
        kline = _make_kline_df(60)
        result = calc_turnover_analysis(kline)
        self.assertIsInstance(result, dict)

    def test_has_score_key(self):
        kline = _make_kline_df(60)
        result = calc_turnover_analysis(kline)
        self.assertIn("换手率评分", result)

    def test_score_range(self):
        kline = _make_kline_df(60)
        result = calc_turnover_analysis(kline)
        self.assertGreaterEqual(result["换手率评分"], 10)
        self.assertLessEqual(result["换手率评分"], 70)

    def test_insufficient_data(self):
        kline = _make_kline_df(10)
        result = calc_turnover_analysis(kline)
        self.assertEqual(result["换手率评分"], 50)

    def test_none_input(self):
        result = calc_turnover_analysis(None)
        self.assertEqual(result["换手率评分"], 50)

    def test_with_turnover_column(self):
        """有换手率列时返回近20日均换手率"""
        kline = _make_kline_df(60)
        kline["换手率"] = np.random.uniform(1, 10, 60)
        result = calc_turnover_analysis(kline)
        self.assertIn("近20日均换手率", result)

    def test_without_turnover_column(self):
        """无换手率列时返回近20日均成交量"""
        kline = _make_kline_df(60)
        result = calc_turnover_analysis(kline)
        self.assertIn("近20日均成交量", result)

    def test_abnormal_turnover_detected(self):
        """异常换手检测——有一日远超均值3倍"""
        kline = _make_kline_df(60)
        kline["换手率"] = np.full(60, 3.0)
        kline.loc[59, "换手率"] = 30.0  # 最后一天异常换手
        result = calc_turnover_analysis(kline)
        self.assertTrue(result.get("异常换手", False))


if __name__ == "__main__":
    unittest.main()
