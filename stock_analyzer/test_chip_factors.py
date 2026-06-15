"""测试 chip_factors.py — 量价配合 / 换手率分析（纯逻辑函数）"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Pre-populate sys.modules so @patch('akshare.stock_holder_number_em') resolves
# without needing akshare actually installed in the test environment.
from unittest.mock import MagicMock
sys.modules["akshare"] = MagicMock()

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from stock_analyzer.chip_factors import (
    calc_chip_concentration,
    calc_turnover_analysis,
    calc_volume_price_factors,
    composite_chip_score,
)


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

    def test_high_avg_turnover(self):
        """平均换手率 > 15 → 评分30"""
        kline = _make_kline_df(60)
        kline["换手率"] = np.full(60, 20.0)
        result = calc_turnover_analysis(kline)
        self.assertEqual(result["换手率评分"], 30)

    def test_low_avg_turnover(self):
        """平均换手率 < 0.5 → 评分40"""
        kline = _make_kline_df(60)
        kline["换手率"] = np.full(60, 0.3)
        result = calc_turnover_analysis(kline)
        self.assertEqual(result["换手率评分"], 40)

    def test_mid_avg_turnover(self):
        """平均换手率 8~15 之间 → 评分50"""
        kline = _make_kline_df(60)
        kline["换手率"] = np.full(60, 10.0)
        result = calc_turnover_analysis(kline)
        self.assertEqual(result["换手率评分"], 50)


class TestCalcChipConcentration(unittest.TestCase):
    """calc_chip_concentration 筹码集中度测试（mock akshare）"""

    @patch("akshare.stock_holder_number_em")
    def test_concentration_increasing(self, mock_ak):
        """股东人数大幅减少 → 筹码集中(主力吸筹)"""
        mock_ak.return_value = pd.DataFrame({
            "股东人数": [10000, 12000],  # 最新:10000, 上期:12000 → -16.7%
        })
        result = calc_chip_concentration("000001")
        self.assertTrue(result["数据可用"])
        self.assertEqual(result["股东人数趋势"], "集中(主力吸筹)")
        self.assertEqual(result["筹码集中度评分"], 80)
        self.assertLess(result["股东人数变化率"], -5)

    @patch("akshare.stock_holder_number_em")
    def test_concentration_slight(self, mock_ak):
        """股东人数小幅减少 → 小幅集中"""
        mock_ak.return_value = pd.DataFrame({
            "股东人数": [11700, 12000],  # -2.5% → change_pct < -2
        })
        result = calc_chip_concentration("000001")
        self.assertTrue(result["数据可用"])
        self.assertEqual(result["股东人数趋势"], "小幅集中")
        self.assertEqual(result["筹码集中度评分"], 65)

    @patch("akshare.stock_holder_number_em")
    def test_concentration_stable(self, mock_ak):
        """股东人数基本不变 → 稳定"""
        mock_ak.return_value = pd.DataFrame({
            "股东人数": [12000, 12100],  # -0.83%
        })
        result = calc_chip_concentration("000001")
        self.assertTrue(result["数据可用"])
        self.assertEqual(result["股东人数趋势"], "稳定")

    @patch("akshare.stock_holder_number_em")
    def test_concentration_slight_dispersing(self, mock_ak):
        """股东人数小幅增加 → 小幅分散"""
        mock_ak.return_value = pd.DataFrame({
            "股东人数": [12300, 12000],  # +2.5%
        })
        result = calc_chip_concentration("000001")
        self.assertTrue(result["数据可用"])
        self.assertEqual(result["股东人数趋势"], "小幅分散")

    @patch("akshare.stock_holder_number_em")
    def test_concentration_dispersing(self, mock_ak):
        """股东人数大幅增加 → 分散(主力出货)"""
        mock_ak.return_value = pd.DataFrame({
            "股东人数": [13000, 12000],  # +8.33%
        })
        result = calc_chip_concentration("000001")
        self.assertTrue(result["数据可用"])
        self.assertEqual(result["股东人数趋势"], "分散(主力出货)")
        self.assertEqual(result["筹码集中度评分"], 20)

    @patch("akshare.stock_holder_number_em")
    def test_too_few_rows(self, mock_ak):
        """数据不足2行 → 返回默认值"""
        mock_ak.return_value = pd.DataFrame({"股东人数": [10000]})
        result = calc_chip_concentration("000001")
        self.assertFalse(result["数据可用"])

    @patch("akshare.stock_holder_number_em")
    def test_empty_data(self, mock_ak):
        """空数据 → 返回默认值"""
        mock_ak.return_value = pd.DataFrame()
        result = calc_chip_concentration("000001")
        self.assertFalse(result["数据可用"])

    @patch("akshare.stock_holder_number_em")
    def test_prev_zero(self, mock_ak):
        """上期股东人数为0 → 返回默认值"""
        mock_ak.return_value = pd.DataFrame({
            "股东人数": [10000, 0],
        })
        result = calc_chip_concentration("000001")
        self.assertFalse(result["数据可用"])

    @patch("akshare.stock_holder_number_em")
    def test_akshare_exception(self, mock_ak):
        """akshare 抛异常 → 返回默认值"""
        mock_ak.side_effect = RuntimeError("API fail")
        result = calc_chip_concentration("000001")
        self.assertFalse(result["数据可用"])

    @patch("akshare.stock_holder_number_em")
    def test_with_total_shares(self, mock_ak):
        """有总股本 → 计算户均持股"""
        mock_ak.return_value = pd.DataFrame({
            "股东人数": [10000, 12000],
            "总股本": [100_000_000, 100_000_000],
        })
        result = calc_chip_concentration("000001")
        self.assertTrue(result["数据可用"])
        self.assertGreater(result["户均持股变化"], 0)


class TestVolumePriceFactorsNoVol(unittest.TestCase):
    """calc_volume_price_factors — 无成交量列分支"""

    def test_no_volume_column(self):
        """DataFrame无成交量列 → 返回默认评分50"""
        kline = pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=30),
            "收盘": [50.0] * 30,
        })
        result = calc_volume_price_factors(kline)
        self.assertEqual(result["量价配合度评分"], 50)


class TestCompositeChipScore(unittest.TestCase):
    """composite_chip_score 综合评分测试"""

    @patch("stock_analyzer.chip_factors.calc_chip_concentration")
    def test_with_kline_data_available(self, mock_chip):
        """有K线 + 筹码数据可用 → 综合评分"""
        mock_chip.return_value = {
            "数据可用": True,
            "筹码集中度评分": 80,
        }
        kline = _make_kline_df(60)
        result = composite_chip_score("000001", kline)
        self.assertIsInstance(result, float)
        self.assertGreater(result, 0)

    @patch("stock_analyzer.chip_factors.calc_chip_concentration")
    def test_without_kline(self, mock_chip):
        """无K线 → 仅用筹码集中度"""
        mock_chip.return_value = {
            "数据可用": True,
            "筹码集中度评分": 80,
        }
        result = composite_chip_score("000001")
        self.assertIsInstance(result, float)
        self.assertGreater(result, 0)

    @patch("stock_analyzer.chip_factors.calc_chip_concentration")
    def test_data_not_available(self, mock_chip):
        """筹码数据不可用 → 权重降低"""
        mock_chip.return_value = {
            "数据可用": False,
            "筹码集中度评分": 50,
        }
        kline = _make_kline_df(60)
        result = composite_chip_score("000001", kline)
        self.assertIsInstance(result, float)
