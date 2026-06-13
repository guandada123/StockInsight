import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest

import numpy as np
import pandas as pd

from stock_analyzer import analysis, quant


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


class TestQuant(unittest.TestCase):
    def test_risk_metrics(self):
        """夏普/最大回撤/VaR 不为 None"""
        df = _make_df(200)
        df = analysis.full_technical_analysis(df)
        metrics = quant.calc_risk_metrics(df)
        self.assertIsNotNone(metrics["sharpe_ratio"])
        self.assertIsNotNone(metrics["max_drawdown_pct"])
        self.assertIsNotNone(metrics["VaR_95_pct"])

    def test_risk_metrics_empty(self):
        """空 DataFrame 不报错，返回 None"""
        empty = pd.DataFrame(columns=["日期", "开盘", "收盘", "最高", "最低", "成交量"])
        metrics = quant.calc_risk_metrics(empty)
        for k, v in metrics.items():
            self.assertIsNone(v, f"{k} should be None for empty df")

    def test_composite_score(self):
        """评分在 0-100，评级是有效值"""
        df = _make_df(200)
        df = analysis.full_technical_analysis(df)
        result = quant.composite_quant_score(df)
        score = result["composite_score"]
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)
        self.assertIn(
            result["rating"],
            ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"],
        )

    def test_composite_score_with_funda(self):
        """传入基本面评分不报错"""
        df = _make_df(200)
        df = analysis.full_technical_analysis(df)
        funda = {
            "ROE": 18,
            "营收增长": 0.25,
            "净利润增长": 0.15,
            "毛利率": 0.45,
        }
        result = quant.composite_quant_score(df, fundamentals=funda)
        score = result["composite_score"]
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_signals(self):
        """信号汇总 bias 是有效值"""
        df = _make_df(200)
        df = analysis.full_technical_analysis(df)
        sig = quant.generate_all_signals(df)
        cons = quant.consolidate_signals(sig)
        self.assertIn(
            cons["bias"],
            ["strong_bullish", "bullish", "neutral", "bearish", "strong_bearish"],
        )

    def test_backtest(self):
        """回测有交易记录"""
        from stock_analyzer.backtest import run_backtest, strategy_ma_cross

        df = _make_df(200)
        result = run_backtest(df, strategy_ma_cross, {"fast": 5, "slow": 20})
        self.assertGreater(len(result["trades"]), 0)

    def test_backtest_edge(self):
        """数据太少时回测为 0 笔交易"""
        from stock_analyzer.backtest import run_backtest, strategy_ma_cross

        df = _make_df(5)
        result = run_backtest(df, strategy_ma_cross, {"fast": 5, "slow": 20})
        self.assertEqual(len(result["trades"]), 0)


if __name__ == "__main__":
    unittest.main()
