import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest

import numpy as np
import pandas as pd

from stock_analyzer import analysis


def _make_df(rows=100):
    """生成模拟 K 线数据，固定 seed 确保可重复"""
    np.random.seed(42)
    close = 50 + np.cumsum(np.random.randn(rows) * 0.5)
    df = pd.DataFrame(
        {
            "日期": pd.date_range("2025-01-01", periods=rows),
            "开盘": close * 0.99,
            "收盘": close,
            "最高": close * 1.02,
            "最低": close * 0.98,
            "成交量": np.random.randint(1_000_000, 10_000_000, rows),
        }
    )
    return df


class TestAnalysis(unittest.TestCase):
    def test_empty_df(self):
        """空 DataFrame 调用 calc_ma 等不报错"""
        empty = pd.DataFrame(columns=["日期", "开盘", "收盘", "最高", "最低", "成交量"])
        try:
            analysis.full_technical_analysis(empty)
        except Exception as e:
            self.fail(f"full_technical_analysis on empty DataFrame raised: {e}")

    def test_ma_calculation(self):
        """full_technical_analysis 后存在 MA5/MA20"""
        df = _make_df()
        result = analysis.full_technical_analysis(df)
        self.assertIn("MA5", result.columns)
        self.assertIn("MA20", result.columns)

    def test_macd_columns(self):
        """存在 DIF/DEA/MACD"""
        df = _make_df()
        result = analysis.full_technical_analysis(df)
        self.assertIn("DIF", result.columns)
        self.assertIn("DEA", result.columns)
        self.assertIn("MACD", result.columns)

    def test_rsi_range(self):
        """RSI 在 0-100 之间"""
        df = _make_df()
        result = analysis.full_technical_analysis(df)
        valid = result["RSI"].dropna()
        self.assertGreater(len(valid), 0)
        self.assertTrue(all((valid >= 0) & (valid <= 100)))

    def test_bollinger(self):
        """BB_UPPER >= BB_LOWER"""
        df = _make_df()
        result = analysis.full_technical_analysis(df)
        valid = result.dropna(subset=["BB_UPPER", "BB_LOWER"])
        self.assertGreater(len(valid), 0)
        self.assertTrue((valid["BB_UPPER"] >= valid["BB_LOWER"]).all())

    def test_adx(self):
        """存在 ADX/DI_PLUS/DI_MINUS"""
        df = _make_df()
        result = analysis.full_technical_analysis(df)
        self.assertIn("ADX", result.columns)
        self.assertIn("DI_PLUS", result.columns)
        self.assertIn("DI_MINUS", result.columns)

    def test_kdj(self):
        """存在 K/D/J"""
        df = _make_df()
        result = analysis.full_technical_analysis(df)
        self.assertIn("K", result.columns)
        self.assertIn("D", result.columns)
        self.assertIn("J", result.columns)

    def test_atr(self):
        """ATR > 0"""
        df = _make_df()
        result = analysis.full_technical_analysis(df)
        valid = result["ATR"].dropna()
        self.assertGreater(len(valid), 0)
        self.assertTrue((valid > 0).all())


if __name__ == "__main__":
    unittest.main()
