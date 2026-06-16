"""测试 chip_concentration.py — 筹码集中度计算"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np

from stock_analyzer import chip_concentration

def _kline(rows=60, seed=42):
    """构造带筹码分析所需字段的 K 线 DataFrame"""
    np.random.seed(seed)
    close = 50 + np.cumsum(np.random.randn(rows) * 0.5)
    vol = np.random.randint(500_000, 3_000_000, rows)
    # 让最后几天成交量放大以模拟主力建仓
    vol[-10:] = vol[-10:] * 2
    return pd.DataFrame({
        "日期": pd.date_range("2025-01-01", periods=rows),
        "开盘": close * 0.99,
        "收盘": close,
        "最高": close * 1.02,
        "最低": close * 0.98,
        "成交量": vol,
    })

class TestCalcChipConcentration(unittest.TestCase):
    """calc_chip_concentration 主函数测试"""

    def test_normal_concentration(self):
        """正常数据 → 返回完整结构"""
        result = chip_concentration.calc_chip_concentration(_kline(60))
        for key in ["pct90", "pct70", "avg_cost", "current_price", "level",
                     "risk_warning", "cost_range_90", "cost_range_70", "lookback_days"]:
            self.assertIn(key, result)
        self.assertGreater(result["lookback_days"], 0)

    def test_none_kline_fallback(self):
        """None → fallback"""
        result = chip_concentration.calc_chip_concentration(None)
        self.assertEqual(result["level"], "无法评估")

    def test_empty_kline_fallback(self):
        """空 DataFrame → fallback"""
        result = chip_concentration.calc_chip_concentration(pd.DataFrame())
        self.assertEqual(result["level"], "无法评估")

    def test_too_few_days_fallback(self):
        """不足 20 日 → fallback"""
        df = _kline(10)
        result = chip_concentration.calc_chip_concentration(df)
        self.assertEqual(result["level"], "无法评估")

    def test_lookback_param(self):
        """自定义 lookback 参数"""
        result = chip_concentration.calc_chip_concentration(_kline(100), lookback=30)
        self.assertEqual(result["lookback_days"], 30)

class TestRiskAssessment(unittest.TestCase):
    """_assess_risk 各风险等级"""

    def test_extreme_danger(self):
        """pct90>=35 且 pct70>=20 → 极度危险"""
        level, _ = chip_concentration._assess_risk(40, 25, 10, 9)
        self.assertEqual(level, "极度危险")

    def test_danger(self):
        """pct90>=25 → 危险"""
        level, _ = chip_concentration._assess_risk(28, 15, 10, 9)
        self.assertEqual(level, "危险")

    def test_caution(self):
        """pct90>=20 → 谨慎"""
        level, _ = chip_concentration._assess_risk(22, 12, 10, 9)
        self.assertEqual(level, "谨慎")

    def test_normal(self):
        """pct90>=10 → 正常"""
        level, _ = chip_concentration._assess_risk(15, 8, 10, 9)
        self.assertEqual(level, "正常")

    def test_safe(self):
        """pct90<10 → 安全"""
        level, _ = chip_concentration._assess_risk(5, 3, 10, 9)
        self.assertEqual(level, "安全")

    def test_profit_calculation(self):
        """盈利/亏损时 profit_pct 正确"""
        _, w = chip_concentration._assess_risk(12, 6, 11, 10)  # 盈利10%
        self.assertIn("盈利", w)
        _, w = chip_concentration._assess_risk(12, 6, 9, 10)  # 亏损10%
        self.assertIn("亏损", w)

class TestFindCostRange(unittest.TestCase):
    """_find_cost_range 边界条件"""

    def test_normal_range(self):
        """正常找到价格区间"""
        np.random.seed(42)
        prices = np.arange(10, 20, 0.5)
        vols = np.random.randint(100_000, 500_000, len(prices))
        df = pd.DataFrame({"avg_price": prices, "成交量": vols})
        cum_vol = df["成交量"].cumsum()
        total_vol = df["成交量"].sum()

        low, high = chip_concentration._find_cost_range(df, cum_vol, total_vol, 0.90)
        self.assertGreater(high, low)
        self.assertGreater(low, 0)

    def test_single_row(self):
        """单行数据 → 不会崩溃"""
        df = pd.DataFrame({"avg_price": [15.0], "成交量": [1000]})
        cum_vol = df["成交量"].cumsum()
        low, high = chip_concentration._find_cost_range(df, cum_vol, 1000, 0.90)
        self.assertEqual(low, 15.0)
        self.assertEqual(high, 15.0)

class TestFallback(unittest.TestCase):
    """_fallback 返回值结构"""

    def test_fallback_structure(self):
        result = chip_concentration._fallback("测试原因")
        self.assertEqual(result["level"], "无法评估")
        self.assertIn("测试原因", result["risk_warning"])
        self.assertEqual(result["pct90"], 0)
        self.assertEqual(result["cost_range_90"], [0, 0])

class TestQuickChipCheck(unittest.TestCase):
    """quick_chip_check 集成测试"""

    @patch("stock_analyzer.cache.cached_kline")
    def test_quick_chip_check(self, mock_kline):
        """调用 cached_kline 后走 calc_chip_concentration"""
        mock_kline.return_value = _kline(120)
        result = chip_concentration.quick_chip_check("000001")
        self.assertIn("level", result)
        mock_kline.assert_called_once_with("000001", days=120)

class TestEdgeCases(unittest.TestCase):
    """边界情况"""

    def test_no_volume_data(self):
        """成交量全为 0 → fallback"""
        df = _kline(60)
        df["成交量"] = 0
        result = chip_concentration.calc_chip_concentration(df)
        self.assertEqual(result["level"], "无法评估")

    def test_concentration_with_many_days(self):
        """大量数据也能正常计算"""
        result = chip_concentration.calc_chip_concentration(_kline(500))
        self.assertIn(result["level"], ["安全", "正常", "谨慎", "危险", "极度危险"])

    def test_pct90_greater_than_pct70(self):
        """90%集中度 > 70%集中度 的数学关系成立"""
        result = chip_concentration.calc_chip_concentration(_kline(60))
        self.assertGreaterEqual(result["pct90"], result["pct70"])

    def test_different_seed_consistent(self):
        """不同种子数据下仍然稳定"""
        for s in [1, 7, 42, 99, 100]:
            result = chip_concentration.calc_chip_concentration(_kline(60, seed=s))
            self.assertIn(result["level"], ["安全", "正常", "谨慎", "危险", "极度危险"])

if __name__ == "__main__":
    unittest.main()
