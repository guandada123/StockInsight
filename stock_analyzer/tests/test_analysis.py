import os
import sys
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


class TestCalcSupportResistance(unittest.TestCase):
    """支撑位与压力位计算"""

    def test_returns_expected_keys(self):
        df = _make_df(100)
        df = analysis.calc_ma(df)
        result = analysis.calc_support_resistance(df)
        self.assertIn("支撑位", result)
        self.assertIn("压力位", result)
        self.assertIn("均线支撑", result)

    def test_supports_below_price(self):
        df = _make_df(100)
        df = analysis.calc_ma(df)
        current = df["收盘"].iloc[-1]
        result = analysis.calc_support_resistance(df)
        for s in result["支撑位"]:
            self.assertLess(s, current)

    def test_resistances_above_price(self):
        df = _make_df(100)
        df = analysis.calc_ma(df)
        current = df["收盘"].iloc[-1]
        result = analysis.calc_support_resistance(df)
        for r in result["压力位"]:
            self.assertGreater(r, current)

    def test_short_df_still_works(self):
        df = _make_df(20)
        df = analysis.calc_ma(df)
        result = analysis.calc_support_resistance(df, lookback=20)
        self.assertIsInstance(result, dict)


class TestCalcStopLevels(unittest.TestCase):
    """止损止盈位计算"""

    def test_with_atr_and_levels(self):
        result = analysis.calc_stop_levels(current_price=50, atr=2, support=46, resistance=55)
        self.assertEqual(result["ATR"], 2)
        self.assertLess(result["止损参考价"], 50)
        self.assertGreater(result["止盈参考价"], 50)

    def test_without_support(self):
        result = analysis.calc_stop_levels(current_price=50, atr=2, support=None, resistance=None)
        self.assertAlmostEqual(
            result["止损参考价"], 47.5, delta=1
        )  # 50 - 2*2 = 46 vs 50*0.95 = 47.5
        self.assertAlmostEqual(result["止盈参考价"], 57.5, delta=1)  # 50*1.15 = 57.5

    def test_nan_atr_defaults(self):
        result = analysis.calc_stop_levels(
            current_price=100, atr=float("nan"), support=90, resistance=110
        )
        self.assertLess(result["止损参考价"], 100)
        self.assertGreater(result["止盈参考价"], 100)

    def test_zero_atr_defaults(self):
        result = analysis.calc_stop_levels(current_price=100, atr=0, support=None, resistance=None)
        self.assertLess(result["止损参考价"], 100)
        self.assertGreater(result["止盈参考价"], 100)

    def test_percentage_fields(self):
        result = analysis.calc_stop_levels(current_price=50, atr=2, support=46, resistance=55)
        self.assertIn("止损幅度%", result)
        self.assertIn("止盈幅度%", result)
        self.assertIn("ATR占比%", result)


class TestGetTechnicalSummary(unittest.TestCase):
    """技术分析结论提取"""

    def _make_full_df(self, rows=100):
        df = _make_df(rows)
        return analysis.full_technical_analysis(df)

    def test_returns_dict_with_expected_keys(self):
        df = self._make_full_df()
        result = analysis.get_technical_summary(df)
        self.assertIsInstance(result, dict)
        for key in ["最新收盘", "涨跌幅", "均线", "MACD", "RSI", "KDJ", "支撑压力", "止损止盈参考"]:
            self.assertIn(key, result)

    def test_total_empty_df(self):
        result = analysis.get_technical_summary(pd.DataFrame())
        self.assertEqual(result, {})

    def test_macd_signal_exists(self):
        df = self._make_full_df(200)
        result = analysis.get_technical_summary(df)
        self.assertIn(result["MACD"]["信号"], ["金叉", "死叉", "多头", "空头"])

    def test_rsi_signal_exists(self):
        df = self._make_full_df(200)
        result = analysis.get_technical_summary(df)
        self.assertIn(result["RSI"]["信号"], ["超买", "超卖", "中性", "未知"])

    def test_kdj_signal_exists(self):
        df = self._make_full_df(200)
        result = analysis.get_technical_summary(df)
        self.assertIn(result["KDJ"]["信号"], ["金叉", "死叉", "超买", "超卖", "中性", "未知"])

    def test_ma_status_keys(self):
        df = self._make_full_df(200)
        result = analysis.get_technical_summary(df)
        for w in [5, 10, 20, 60]:
            if f"MA{w}" in result["均线"]:
                self.assertIn("值", result["均线"][f"MA{w}"])
                self.assertIn("股价位置", result["均线"][f"MA{w}"])

    def test_near_term_change(self):
        df = self._make_full_df(50)
        result = analysis.get_technical_summary(df)
        self.assertIsNotNone(result["近5日涨跌幅"])

    def test_short_df_no_20d_change(self):
        df = self._make_full_df(15)
        result = analysis.get_technical_summary(df)
        self.assertIsNone(result["近20日涨跌幅"])


class TestScoreFundamental(unittest.TestCase):
    """基本面评分"""

    def test_high_roe_high_growth(self):
        funds = {"ROE": 25, "营收增长": 0.35, "净利润增长": 0.40, "毛利率": 0.65}
        score, details = analysis.score_fundamental(funds)
        self.assertGreater(score, 60)
        self.assertLessEqual(score, 100)

    def test_negative_all(self):
        funds = {"ROE": 2, "营收增长": -0.1, "净利润增长": -0.2, "毛利率": 0.1}
        score, details = analysis.score_fundamental(funds)
        self.assertLess(score, 60)

    def test_empty_fundamentals(self):
        score, details = analysis.score_fundamental({})
        self.assertEqual(score, 50)  # baseline

    def test_missing_keys(self):
        score, details = analysis.score_fundamental({"ROE": 15})
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_score_capped_at_100(self):
        funds = {"ROE": 50, "营收增长": 1.0, "净利润增长": 1.0, "毛利率": 0.9}
        score, details = analysis.score_fundamental(funds)
        self.assertLessEqual(score, 100)

    def test_score_floor_at_0(self):
        funds = {"ROE": -10, "营收增长": -0.5, "净利润增长": -0.5, "毛利率": 0.0}
        score, details = analysis.score_fundamental(funds)
        self.assertGreaterEqual(score, 0)

    def test_returns_details(self):
        funds = {"ROE": 18, "营收增长": 0.15}
        score, details = analysis.score_fundamental(funds)
        self.assertIn("ROE", details)
        self.assertIn("营收增长", details)


class TestScoreStocksInSector(unittest.TestCase):
    """板块内个股评分"""

    def test_scores_added(self):
        df = pd.DataFrame(
            {
                "名称": ["A", "B", "C"],
                "涨跌幅": [5.0, -2.0, 3.0],
                "量比": [1.5, 0.8, 2.0],
                "振幅": [3.0, 2.0, 5.0],
            }
        )
        result = analysis.score_stocks_in_sector(df)
        self.assertIn("个股评分", result.columns)

    def test_sorted_descending(self):
        df = pd.DataFrame(
            {
                "名称": ["A", "B", "C"],
                "涨跌幅": [5.0, -2.0, 3.0],
                "量比": [1.5, 0.8, 2.0],
                "振幅": [3.0, 2.0, 5.0],
            }
        )
        result = analysis.score_stocks_in_sector(df)
        scores = result["个股评分"].values
        self.assertTrue(all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1)))

    def test_single_stock(self):
        df = pd.DataFrame(
            {
                "名称": ["A"],
                "涨跌幅": [5.0],
                "量比": [1.5],
                "振幅": [3.0],
            }
        )
        result = analysis.score_stocks_in_sector(df)
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
