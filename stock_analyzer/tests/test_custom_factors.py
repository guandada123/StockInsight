"""测试 custom_factors.py — FactorExpressionEngine 表达式安全求值"""

import os
import sys
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
        self.df = pd.DataFrame(
            {
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
            }
        )

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
        np.testing.assert_array_almost_equal(
            result["factor_value"].values, expected.values.astype(float)
        )

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


# ═══════════════════════════════════════════
# 错误路径全覆盖
# ═══════════════════════════════════════════


class TestErrorPaths(unittest.TestCase):
    """覆盖所有 raise ValueError 分支"""

    def setUp(self):
        self.engine = FactorExpressionEngine()
        self.df = pd.DataFrame(
            {
                "open": [10.0, 11.0],
                "close": [10.5, 11.5],
                "vol": [1000000, 2000000],
            }
        )

    # ── evaluate 层: 非Series结果 ──
    def test_rolling_without_terminal_method(self):
        """rolling() 返回 Rolling 对象而非 Series → 报错"""
        with self.assertRaises(ValueError) as ctx:
            self.engine.evaluate("close.rolling(5)", self.df)
        self.assertIn("Series", str(ctx.exception))

    # ── _eval_node: 不支持的运算符 ──
    def test_unsupported_binary_op(self):
        """| 运算符不在白名单 (line 99)"""
        with self.assertRaises(ValueError) as ctx:
            self.engine.evaluate("close | close", self.df)
        self.assertIn("不支持的运算符", str(ctx.exception))

    def test_unsupported_unary_op(self):
        """~ 运算符不在白名单 (line 104)"""
        with self.assertRaises(ValueError) as ctx:
            self.engine.evaluate("~close", self.df)
        self.assertIn("不支持的一元运算符", str(ctx.exception))

    def test_double_underscore_name_blocked(self):
        """双下划线变量名被拦截 (line 108)"""
        with self.assertRaises(ValueError) as ctx:
            self.engine.evaluate("__xxx__", self.df)
        self.assertIn("不安全", str(ctx.exception))

    def test_column_in_whitelist_but_not_in_df(self):
        """白名单列但 DataFrame 中不存在 (line 112)"""
        with self.assertRaises(ValueError) as ctx:
            self.engine.evaluate("amount", self.df)  # amount 在白名单但 df 没有
        self.assertIn("列不存在", str(ctx.exception))

    def test_non_numeric_constant(self):
        """字符串常量被拦截 (line 117)"""
        with self.assertRaises(ValueError) as ctx:
            self.engine.evaluate('"hello"', self.df)
        self.assertIn("数值常量", str(ctx.exception))

    def test_boolean_constant_accepted(self):
        """布尔常量在 Python 中是 int 子类，引擎接受但值视为 1/0"""
        # True/False 在 Python 中是 int 的子类，会通过数值检查
        result = self.engine.evaluate("True", self.df)
        self.assertIn("factor_value", result.columns)

    def test_unsupported_node_type(self):
        """不支持的 AST 节点 (line 120)"""
        import ast

        with self.assertRaises(ValueError) as ctx:
            self.engine._eval_node(ast.List(elts=[], ctx=ast.Load()), self.df)
        self.assertIn("不支持的节点类型", str(ctx.exception))

    # ── _eval_call: 调用方式 ──
    def test_unsupported_call_style(self):
        """Call(func=Subscript) 既非 Name 也非 Attribute → 不支持的调用方式"""
        import ast

        # func = close[0] (Subscript), params not needed
        sub_node = ast.Subscript(
            value=ast.Name(id="close", ctx=ast.Load()),
            slice=ast.Constant(value=0),
            ctx=ast.Load(),
        )
        call_node = ast.Call(func=sub_node, args=[], keywords=[])
        with self.assertRaises(ValueError) as ctx:
            self.engine._eval_call(call_node, self.df)
        self.assertIn("不支持的调用方式", str(ctx.exception))

    def test_double_underscore_method_caught(self):
        """close.__class__ 在 _eval_node 层被拦截为不支持节点类型"""
        with self.assertRaises(ValueError) as ctx:
            self.engine.evaluate("close.__class__", self.df)
        self.assertIn("不支持的节点", str(ctx.exception))

    def test_rolling_on_non_series(self):
        """rolling() 作用于标量报错 (line 142)"""
        with self.assertRaises(ValueError) as ctx:
            self.engine.evaluate("(close - close).rolling(5)", self.df)
        self.assertIn("Series", str(ctx.exception))

    def test_rolling_window_zero(self):
        """rolling 窗口为 0 报错 (line 145)"""
        with self.assertRaises(ValueError) as ctx:
            self.engine.evaluate("close.rolling(0)", self.df)
        self.assertIn("窗口", str(ctx.exception))

    def test_rolling_window_negative(self):
        """rolling 窗口为负数报错 (line 145)"""
        with self.assertRaises(ValueError) as ctx:
            self.engine.evaluate("close.rolling(-3)", self.df)
        self.assertIn("窗口", str(ctx.exception))

    def test_unsupported_series_method(self):
        """不支持的 Series 方法 (line 150)"""
        with self.assertRaises(ValueError) as ctx:
            self.engine.evaluate("close.cumsum()", self.df)
        self.assertIn("Series 方法不允许", str(ctx.exception))

    def test_unsupported_window_method(self):
        """不支持的窗口方法 (line 156)"""
        with self.assertRaises(ValueError) as ctx:
            self.engine.evaluate("close.rolling(3).median()", self.df)
        self.assertIn("窗口方法不允许", str(ctx.exception))

    def test_unsupported_method_on_non_series_non_window(self):
        """未知方法 (line 160)"""
        with self.assertRaises(ValueError) as ctx:
            self.engine.evaluate("close.rolling(3).unknown()", self.df)
        self.assertIn("不支持的方法", str(ctx.exception))

    # ── _as_scalar: 类型校验 ──
    def test_as_scalar_rejects_series(self):
        """_as_scalar 拒绝 Series (line 165-167)"""
        with self.assertRaises(ValueError) as ctx:
            self.engine._as_scalar(pd.Series([1, 2, 3]), "test")
        self.assertIn("数值标量", str(ctx.exception))

    def test_as_scalar_rejects_string(self):
        """_as_scalar 拒绝字符串 (line 165-167)"""
        with self.assertRaises(ValueError) as ctx:
            self.engine._as_scalar("abc", "test")
        self.assertIn("数值标量", str(ctx.exception))

    def test_as_scalar_accepts_int(self):
        """_as_scalar 接受整数"""
        result = self.engine._as_scalar(42, "test")
        self.assertEqual(result, 42)
        self.assertIsInstance(result, int)

    def test_as_scalar_accepts_float(self):
        """_as_scalar 接受浮点数"""
        result = self.engine._as_scalar(3.14, "test")
        self.assertEqual(result, 3.14)
        self.assertIsInstance(result, float)

    def test_as_scalar_accepts_numpy_int(self):
        """_as_scalar 接受 numpy 整数"""
        result = self.engine._as_scalar(np.int64(10), "test")
        self.assertEqual(result, 10)

    def test_as_scalar_accepts_numpy_float(self):
        """_as_scalar 接受 numpy 浮点"""
        result = self.engine._as_scalar(np.float64(2.5), "test")
        self.assertEqual(result, 2.5)

    # ── 安全：禁止列名 ──
    def test_forbidden_function_call(self):
        """不在白名单的函数报错"""
        with self.assertRaises(ValueError) as ctx:
            self.engine.evaluate("len(close)", self.df)
        self.assertIn("函数不允许", str(ctx.exception))


# ═══════════════════════════════════════════
# SQLite 因子管理
# ═══════════════════════════════════════════


class TestFactorCRUD(unittest.TestCase):
    """因子 SQLite 存储 CRUD 操作"""

    @classmethod
    def setUpClass(cls):
        from stock_analyzer.custom_factors import init_factor_table

        init_factor_table()

    def test_init_table_idempotent(self):
        """重复建表不报错"""
        from stock_analyzer.custom_factors import init_factor_table

        init_factor_table()  # 第二次调用
        init_factor_table()  # 第三次调用

    def test_create_and_list_factors(self):
        """创建因子后能从列表查询"""
        from stock_analyzer.custom_factors import create_factor, list_factors

        create_factor("test_momentum", "动量因子", "close.pct_change(10)", description="10日动量")
        factors = list_factors()
        ids = [f["id"] for f in factors]
        self.assertIn("test_momentum", ids)

    def test_create_duplicate_updates(self):
        """重复创建同名因子更新定义"""
        from stock_analyzer.custom_factors import create_factor, list_factors

        create_factor("test_dup", "dup_v1", "close.pct_change(5)", description="v1")
        create_factor("test_dup", "dup_v2", "close.pct_change(10)", description="v2")
        factors = {f["id"]: f for f in list_factors()}
        self.assertIn("v2", factors["test_dup"]["description"])

    def test_create_invalid_syntax_raises(self):
        """创建语法错误的因子报错"""
        from stock_analyzer.custom_factors import create_factor

        with self.assertRaises((ValueError, SyntaxError)):
            create_factor("bad_factor", "broken", "close + ")

    def test_delete_factor(self):
        """删除因子后不再出现在列表中"""
        from stock_analyzer.custom_factors import create_factor, delete_factor, list_factors

        create_factor("to_delete", "temp_del", "close.pct_change(3)", description="temp")
        delete_factor("to_delete")
        factors = list_factors()
        ids = [f["id"] for f in factors]
        self.assertNotIn("to_delete", ids)

    def test_delete_nonexistent_no_error(self):
        """删除不存在的因子不报错"""
        from stock_analyzer.custom_factors import delete_factor

        delete_factor("does_not_exist_xyz")

    def test_factor_stores_metadata(self):
        """因子存储元数据"""
        from stock_analyzer.custom_factors import create_factor, list_factors

        create_factor("meta_test", "量比因子", "vol.pct_change(20)", description="成交量动量")
        factors = {f["id"]: f for f in list_factors()}
        f = factors["meta_test"]
        self.assertEqual(f["expression"], "vol.pct_change(20)")
        self.assertIn("created", f)

    def test_create_factor_ast_validation(self):
        """create_factor AST 语法校验——安全表达式不报错"""
        from stock_analyzer.custom_factors import create_factor

        create_factor(
            "safe_expr",
            "布林带",
            "(close - close.rolling(20).mean()) / close.rolling(20).std()",
            description="布林带位置",
        )


if __name__ == "__main__":
    unittest.main()
