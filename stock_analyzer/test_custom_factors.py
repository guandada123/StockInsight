"""测试 custom_factors.py — FactorExpressionEngine 表达式安全求值"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest

import numpy as np
import pandas as pd

from stock_analyzer.custom_factors import FactorExpressionEngine


class TestFactorExpressionEngine(unittest.TestCase):
    """因子表达式引擎测试"""

    def setUp(self):
        np.random.seed(42)
        self.engine = FactorExpressionEngine()
        # 构造标准K线 DataFrame
        closes = 50 + np.cumsum(np.random.randn(30) * 0.5)
        self.df = pd.DataFrame({
            "日期": pd.date_range("2025-06-01", periods=30),
            "open": closes * 0.99,
            "high": closes * 1.02,
            "low": closes * 0.98,
            "close": closes,
            "pre_close": np.roll(closes, 1),
            "change_c": closes - np.roll(closes, 1),
            "pct_chg": np.append([0], np.diff(closes) / closes[:-1] * 100),
            "vol": np.random.randint(1_000_000, 10_000_000, 30),
            "amount": np.random.randint(10_000_000, 100_000_000, 30),
        })

    # ── __init__ 测试 ──

    def test_default_init(self):
        """默认初始化白名单包含标准列"""
        engine = FactorExpressionEngine()
        self.assertIn("close", engine.allowed_columns)
        self.assertIn("vol", engine.allowed_columns)

    def test_custom_columns(self):
        """自定义白名单"""
        engine = FactorExpressionEngine(allowed_columns={"my_col", "other_col"})
        self.assertNotIn("close", engine.allowed_columns)
        self.assertIn("my_col", engine.allowed_columns)

    # ── evaluate 基础功能 ──

    def test_evaluate_returns_dataframe(self):
        """返回含 factor_value 列的 DataFrame"""
        result = self.engine.evaluate("close", self.df)
        self.assertIsInstance(result, pd.DataFrame)
        self.assertIn("factor_value", result.columns)

    def test_evaluate_close_column(self):
        """直接引用 close 列"""
        result = self.engine.evaluate("close", self.df)
        np.testing.assert_array_almost_equal(
            result["factor_value"].values[:10],
            self.df["close"].values[:10],
        )

    def test_evaluate_vol_column(self):
        """引用 vol 列"""
        result = self.engine.evaluate("vol", self.df)
        np.testing.assert_array_almost_equal(
            result["factor_value"].values[:5],
            self.df["vol"].values[:5].astype(float),
        )

    def test_evaluate_empty_df(self):
        """空 DataFrame 返回含 factor_value 列的空 DataFrame"""
        empty = pd.DataFrame()
        result = self.engine.evaluate("close", empty)
        self.assertIsInstance(result, pd.DataFrame)
        self.assertIn("factor_value", result.columns)
        self.assertTrue(result.empty)

    def test_evaluate_none_df(self):
        """None DataFrame 不报错"""
        result = self.engine.evaluate("close", None)
        self.assertIsInstance(result, pd.DataFrame)

    def test_evaluate_empty_expression_raises(self):
        """空表达式抛出 ValueError"""
        with self.assertRaises(ValueError):
            self.engine.evaluate("", self.df)

    def test_evaluate_whitespace_expression_raises(self):
        """纯空白表达式抛出 ValueError"""
        with self.assertRaises(ValueError):
            self.engine.evaluate("   ", self.df)

    # ── 运算符测试 ──

    def test_addition(self):
        """加法运算"""
        result = self.engine.evaluate("close + 1", self.df)
        expected = self.df["close"] + 1
        np.testing.assert_array_almost_equal(result["factor_value"].values, expected.values)

    def test_subtraction(self):
        """减法运算"""
        result = self.engine.evaluate("close - open", self.df)
        expected = self.df["close"] - self.df["open"]
        np.testing.assert_array_almost_equal(result["factor_value"].values, expected.values)

    def test_multiplication(self):
        """乘法运算"""
        result = self.engine.evaluate("close * 2", self.df)
        expected = self.df["close"] * 2
        np.testing.assert_array_almost_equal(result["factor_value"].values, expected.values)

    def test_division(self):
        """除法运算"""
        result = self.engine.evaluate("close / 2", self.df)
        expected = self.df["close"] / 2
        np.testing.assert_array_almost_equal(result["factor_value"].values, expected.values)

    def test_power(self):
        """幂运算"""
        result = self.engine.evaluate("close ** 0", self.df)
        expected = np.ones(len(self.df))
        np.testing.assert_array_almost_equal(result["factor_value"].values, expected)

    def test_modulo(self):
        """取模运算"""
        result = self.engine.evaluate("vol % 100", self.df)
        expected = self.df["vol"] % 100
        np.testing.assert_array_almost_equal(result["factor_value"].values, expected.values.astype(float))

    def test_unary_neg(self):
        """一元负号"""
        result = self.engine.evaluate("-close", self.df)
        expected = -self.df["close"]
        np.testing.assert_array_almost_equal(result["factor_value"].values, expected.values)

    def test_unary_pos(self):
        """一元正号"""
        result = self.engine.evaluate("+close", self.df)
        np.testing.assert_array_almost_equal(
            result["factor_value"].values,
            self.df["close"].values,
        )

    def test_abs_function(self):
        """abs() 函数——仅支持标量"""
        result = self.engine.evaluate("abs(-5)", self.df)
        expected = np.full(len(self.df), 5.0)
        np.testing.assert_array_almost_equal(result["factor_value"].values, expected)

    # ── Series 方法测试 ──

    def test_pct_change(self):
        """pct_change 方法"""
        result = self.engine.evaluate("close.pct_change(5)", self.df)
        self.assertAlmostEqual(
            result["factor_value"].iloc[-1],
            self.df["close"].pct_change(5).iloc[-1],
        )

    def test_shift(self):
        """shift 方法"""
        result = self.engine.evaluate("close.shift(1)", self.df)
        expected = self.df["close"].shift(1)
        np.testing.assert_array_almost_equal(
            result["factor_value"].values[1:],
            expected.values[1:],
        )

    def test_diff(self):
        """diff 方法"""
        result = self.engine.evaluate("close.diff(1)", self.df)
        expected = self.df["close"].diff(1)
        np.testing.assert_array_almost_equal(
            result["factor_value"].values[1:],
            expected.values[1:],
        )

    def test_rank(self):
        """rank 方法"""
        result = self.engine.evaluate("close.rank()", self.df)
        expected = self.df["close"].rank()
        np.testing.assert_array_almost_equal(result["factor_value"].values, expected.values)

    # ── rolling 窗口方法 ──

    def test_rolling_mean(self):
        """rolling().mean()"""
        result = self.engine.evaluate("close.rolling(5).mean()", self.df)
        expected = self.df["close"].rolling(5).mean()
        np.testing.assert_array_almost_equal(
            result["factor_value"].values[4:],
            expected.values[4:],
        )

    def test_rolling_std(self):
        """rolling().std()"""
        result = self.engine.evaluate("close.rolling(10).std()", self.df)
        expected = self.df["close"].rolling(10).std()
        np.testing.assert_array_almost_equal(
            result["factor_value"].values[9:],
            expected.values[9:],
        )

    def test_rolling_max(self):
        """rolling().max()"""
        result = self.engine.evaluate("close.rolling(20).max()", self.df)
        expected = self.df["close"].rolling(20).max()
        np.testing.assert_array_almost_equal(
            result["factor_value"].values[19:],
            expected.values[19:],
        )

    def test_rolling_min(self):
        """rolling().min()"""
        result = self.engine.evaluate("close.rolling(10).min()", self.df)
        expected = self.df["close"].rolling(10).min()
        np.testing.assert_array_almost_equal(
            result["factor_value"].values[9:],
            expected.values[9:],
        )

    def test_rolling_sum(self):
        """rolling().sum()"""
        result = self.engine.evaluate("vol.rolling(5).sum()", self.df)
        expected = self.df["vol"].rolling(5).sum()
        np.testing.assert_array_almost_equal(
            result["factor_value"].values[4:],
            expected.values[4:],
        )

    # ── 安全测试 ──

    def test_forbidden_column_raises(self):
        """未在白名单的列名应报错"""
        with self.assertRaises(ValueError):
            self.engine.evaluate("nonexistent_column", self.df)

    def test_double_underscore_blocked(self):
        """双下划线方法被拦截"""
        with self.assertRaises(ValueError):
            self.engine.evaluate("close.__class__", self.df)

    def test_import_blocked(self):
        """无法通过表达式导入模块"""
        invalid_exprs = [
            "__import__('os')",
            "eval('1+1')",
            "exec('x=1')",
        ]
        for expr in invalid_exprs:
            with self.assertRaises((ValueError, SyntaxError, TypeError)):
                self.engine.evaluate(expr, self.df)

    # ── 标量广播 ──

    def test_scalar_broadcast(self):
        """标量结果广播到整个 Series"""
        result = self.engine.evaluate("1 + 1", self.df)
        np.testing.assert_array_almost_equal(
            result["factor_value"].values,
            np.full(len(self.df), 2.0),
        )

    # ── 复杂表达式 ──

    def test_complex_expression_momentum(self):
        """动量因子: close.pct_change(20) ——返回比率（非百分比）"""
        result = self.engine.evaluate("close.pct_change(20)", self.df)
        expected_ratio = self.df["close"].iloc[-1] / self.df["close"].iloc[-21] - 1
        # pct_change 返回比率（-0.1 表示下跌10%），而非百分比
        self.assertAlmostEqual(result["factor_value"].iloc[-1], expected_ratio)

    def test_complex_expression_ma_cross(self):
        """均线交叉: close.rolling(5).mean() - close.rolling(20).mean()"""
        result = self.engine.evaluate(
            "close.rolling(5).mean() - close.rolling(20).mean()",
            self.df,
        )
        ma5 = self.df["close"].rolling(5).mean()
        ma20 = self.df["close"].rolling(20).mean()
        expected = ma5 - ma20
        np.testing.assert_array_almost_equal(
            result["factor_value"].values[19:],
            expected.values[19:],
        )


if __name__ == "__main__":
    unittest.main()
