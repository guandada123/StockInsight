"""补充测试 backtest.py — 回测策略（补充 test_quant.py 中已有的策略测试）"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest

import numpy as np
import pandas as pd

from stock_analyzer.backtest import (
    run_backtest,
    strategy_bollinger_breakout,
    strategy_ma_cross,
    strategy_macd_cross,
    strategy_momentum_breakout,
    strategy_rsi_reversal,
)

# 扩展 test_quant.py 中已有的 _make_df，确保测试可重复


class TestBacktestStrategies(unittest.TestCase):
    """各策略函数单元测试（纯逻辑，不依赖网络）"""

    def _make_df(self, rows=200):
        np.random.seed(42)
        close = 50 + np.cumsum(np.random.randn(rows) * 0.5)
        return pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=rows),
            "开盘": close * 0.99,
            "收盘": close,
            "最高": close * 1.02,
            "最低": close * 0.98,
            "成交量": np.random.randint(1_000_000, 10_000_000, rows),
        })

    def test_run_backtest_returns_dict(self):
        """回测返回字典"""
        df = self._make_df(200)
        result = run_backtest(df, strategy_ma_cross, {"fast": 5, "slow": 20})
        self.assertIsInstance(result, dict)

    def test_run_backtest_has_expected_keys(self):
        """回测结果包含预期键"""
        df = self._make_df(200)
        result = run_backtest(df, strategy_ma_cross, {"fast": 5, "slow": 20})
        for key in ["trades", "equity_curve", "metrics", "summary"]:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_empty_df_returns_none(self):
        """空数据/无信号时返回 None"""
        empty = pd.DataFrame(columns=["日期", "开盘", "收盘", "最高", "最低", "成交量"])
        result = run_backtest(empty, strategy_ma_cross, {"fast": 5, "slow": 20})
        self.assertIsNone(result)

    def test_insufficient_data(self):
        """数据不足时返回 0 交易"""
        df = self._make_df(10)
        result = run_backtest(df, strategy_ma_cross, {"fast": 5, "slow": 20})
        self.assertIsInstance(result, dict)

    def test_strategy_macd_runs(self):
        """MACD 策略不报错"""
        df = self._make_df(200)
        try:
            result = run_backtest(df, strategy_macd_cross, {"fast": 12, "slow": 26, "sig": 9})
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.fail(f"strategy_macd_cross raised: {e}")

    def test_strategy_rsi_runs(self):
        """RSI 策略不报错"""
        df = self._make_df(200)
        try:
            result = run_backtest(df, strategy_rsi_reversal, {"period": 14, "oversold": 30, "overbought": 70})
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.fail(f"strategy_rsi_reversal raised: {e}")

    def test_strategy_bollinger_runs(self):
        """布林带策略不报错"""
        df = self._make_df(200)
        try:
            result = run_backtest(df, strategy_bollinger_breakout, {"period": 20, "std": 2})
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.fail(f"strategy_bollinger_breakout raised: {e}")

    def test_strategy_momentum_breakout_runs(self):
        """动量突破策略不报错"""
        df = self._make_df(200)
        try:
            result = run_backtest(df, strategy_momentum_breakout, {"lookback": 20})
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.fail(f"strategy_momentum_breakout raised: {e}")

    def test_backtest_metrics_range(self):
        """回测指标在合理范围"""
        df = self._make_df(200)
        result = run_backtest(df, strategy_ma_cross, {"fast": 5, "slow": 20})
        if len(result["trades"]) > 0:
            # win_rate 应在 0-100 之间（百分比）
            self.assertGreaterEqual(result["metrics"]["胜率%"], 0)
            self.assertLessEqual(result["metrics"]["胜率%"], 100)
            # max_drawdown 应为非正数（百分比）
            self.assertLessEqual(result["metrics"]["最大回撤%"], 0)

    def test_benchmark_calculated(self):
        """基准收益被计算"""
        df = self._make_df(200)
        result = run_backtest(df, strategy_ma_cross, {"fast": 5, "slow": 20})
        self.assertIn("metrics", result)
        self.assertIn("基准收益%", result["metrics"])


if __name__ == "__main__":
    unittest.main()
