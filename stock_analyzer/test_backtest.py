"""补充测试 backtest.py — 回测策略（补充 test_quant.py 中已有的策略测试）"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest

import numpy as np
import pandas as pd

from stock_analyzer.backtest import (
    STRATEGIES,
    compare_strategies,
    export_backtest_json,
    optimize_strategy,
    run_backtest,
    strategy_bollinger_breakout,
    strategy_grid,
    strategy_ma_cross,
    strategy_macd_cross,
    strategy_ma_trend,
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


# ── 网格交易 ──────────────────────────────────────────────


class TestStrategyGrid(unittest.TestCase):
    """strategy_grid 网格交易策略测试"""

    def _make_price_series(self, prices):
        return pd.DataFrame({"收盘": prices, "日期": pd.date_range("2025-01-01", periods=len(prices))})

    def test_grid_basic(self):
        """正常网格：5% 网格触发买卖"""
        # 模拟先跌后涨
        prices = [100, 94, 94, 94, 106, 106, 106]
        df = self._make_price_series(prices)
        result = strategy_grid(df, grid_pct=0.05)
        # 第二根K线 94 <= 100*0.95 → buy(1)
        self.assertEqual(result["signal"].iloc[1], 1)
        # 第四根K线 106 >= 94*1.05 → sell(-1)
        self.assertEqual(result["signal"].iloc[4], -1)

    def test_grid_base_zero(self):
        """base 价格为 0 → 跳过（不崩）"""
        df = self._make_price_series([0, 10, 9])
        result = strategy_grid(df, grid_pct=0.05)
        self.assertIn("signal", result.columns)

    def test_grid_base_zero_after_reset(self):
        """base 被重置为0 → 跳过"""
        df = self._make_price_series([100, 0, 95, 95])
        result = strategy_grid(df, grid_pct=0.05)
        self.assertIn("signal", result.columns)


# ── 均线趋势 ────────────────────────────────────────────


class TestStrategyMaTrend(unittest.TestCase):
    """strategy_ma_trend 均线多头排列测试"""

    def _make_trend_df(self, rows=60):
        np.random.seed(7)
        close = 50 + np.cumsum(np.random.randn(rows) * 0.8)
        return pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=rows),
            "收盘": close,
            "最高": close * 1.02,
            "最低": close * 0.98,
        })

    def test_trend_returns_signals(self):
        """均线趋势返回 DataFrame 含 signal"""
        df = self._make_trend_df(120)
        result = strategy_ma_trend(df)
        self.assertIsInstance(result, pd.DataFrame)
        self.assertIn("signal", result.columns)

    def test_trend_has_ma_columns(self):
        """输出包含 MA 辅助列"""
        df = self._make_trend_df(120)
        result = strategy_ma_trend(df, short=5, mid=20, long=60)
        for col in ["MA_S", "MA_M", "MA_L"]:
            self.assertIn(col, result.columns)

    def test_trend_short_data(self):
        """数据不足时不报错"""
        df = self._make_trend_df(10)
        result = strategy_ma_trend(df)
        self.assertIsInstance(result, pd.DataFrame)


# ── 布林带列路径 ─────────────────────────────────────


class TestStrategyBollingerColumns(unittest.TestCase):
    """strategy_bollinger_breakout 不同列名路径测试"""

    def test_with_bb_columns(self):
        """df 已有 BB_UPPER/BB_LOWER/BB_MIDDLE 列"""
        df = pd.DataFrame({
            "收盘": [50, 51, 52, 53, 54],
            "BB_UPPER": [55, 56, 57, 58, 59],
            "BB_LOWER": [45, 44, 43, 42, 41],
            "BB_MIDDLE": [50, 50, 50, 50, 50],
        })
        result = strategy_bollinger_breakout(df)
        self.assertIn("signal", result.columns)

    def test_with_lowercase_columns(self):
        """df 有小写 upper/lower/middle 列"""
        df = pd.DataFrame({
            "收盘": [50, 51, 52, 53, 54],
            "upper": [55, 56, 57, 58, 59],
            "lower": [45, 44, 43, 42, 41],
            "middle": [50, 50, 50, 50, 50],
        })
        result = strategy_bollinger_breakout(df)
        self.assertIn("signal", result.columns)

    def test_without_extra_columns(self):
        """只有收盘价列（走 rolling 计算）"""
        df = pd.DataFrame({
            "收盘": [50 + i for i in range(30)],
        })
        result = strategy_bollinger_breakout(df)
        self.assertIn("signal", result.columns)


# ── MACD 列路径 ────────────────────────────────────────


class TestStrategyMacdCrossColumns(unittest.TestCase):
    """strategy_macd_cross 已有 DIF/DEA 列"""

    def test_with_dif_dea_columns(self):
        """df 已有 DIF/DEA 列"""
        df = pd.DataFrame({
            "收盘": [50, 51, 52, 53, 54],
            "DIF": [0.5, 1.0, 1.5, 2.0, 2.5],
            "DEA": [0.3, 0.8, 1.2, 1.8, 2.2],
        })
        result = strategy_macd_cross(df)
        self.assertIn("signal", result.columns)


# ── 回测引擎边缘分支 ─────────────────────────────────


class TestBacktestEdgeCases(unittest.TestCase):
    """run_backtest 边缘分支测试"""

    def _make_kline(self, rows=200):
        np.random.seed(42)
        close = 50 + np.cumsum(np.random.randn(rows) * 0.5)
        return pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=rows),
            "收盘": close,
            "最高": close * 1.02,
            "最低": close * 0.98,
            "成交量": np.random.randint(1_000_000, 10_000_000, rows),
        })

    def test_missing_close_column(self):
        """缺少 '收盘' 列 → ValueError"""
        df = pd.DataFrame({"开盘": [50, 51]})
        with self.assertRaises(ValueError):
            run_backtest(df, strategy_ma_cross)

    def test_signals_all_zero(self):
        """信号全零 → 0 交易"""
        def _noop_strategy(df):
            return pd.DataFrame({"signal": [0] * len(df)}, index=df.index)
        df = self._make_kline(100)
        result = run_backtest(df, _noop_strategy)
        self.assertIsNotNone(result)
        self.assertEqual(result["metrics"]["交易次数"], 0)

    def test_no_date_column(self):
        """无日期列时仍正常运行"""
        df = self._make_kline(100).drop(columns=["日期"])
        result = run_backtest(df, strategy_ma_cross, {"fast": 5, "slow": 20})
        self.assertIsInstance(result, dict)

    def test_strategy_params_none(self):
        """strategy_params=None → 使用空字典"""
        df = self._make_kline(100)
        result = run_backtest(df, strategy_ma_cross, None)
        self.assertIsInstance(result, dict)


# ── 止盈止损风控 ──────────────────────────────────


class TestBacktestRiskControl(unittest.TestCase):
    """run_backtest 止盈止损移动止损测试"""

    def _trend_df(self):
        """单边下跌后反弹的 K 线"""
        prices = [100, 99, 98, 97, 96, 95, 94, 93, 92, 91,
                  90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100]
        return pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=len(prices)),
            "收盘": prices,
            "最高": [p * 1.01 for p in prices],
            "最低": [p * 0.99 for p in prices],
        })

    def _buy_hold_strategy(self, df):
        """始终买入持有直至卖出信号"""
        sig = pd.Series(0, index=df.index)
        sig.iloc[1] = 1     # 第2天买入
        sig.iloc[-2] = -1   # 倒数第2天卖出
        return pd.DataFrame({"signal": sig})

    def test_stop_loss_triggers(self):
        """固定止损触发 → 在止损价卖出"""
        df = self._trend_df()
        result = run_backtest(df, self._buy_hold_strategy, stop_loss=0.05)
        sells = [t for t in result["trades"] if t["action"] == "SELL"]
        self.assertGreater(len(sells), 0)
        # 至少有一个卖出原因是"止损"
        reasons = [t.get("exit_reason", "") for t in sells]
        self.assertIn("止损", reasons)

    def test_take_profit_triggers(self):
        """固定止盈触发 → 在止盈价卖出"""
        # 价格从100跌到90再涨到120 → 止盈路径
        prices = [100, 99, 98, 97, 96, 95, 94, 93, 92, 91,
                  90, 95, 100, 105, 110, 115, 120, 125]
        df = pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=len(prices)),
            "收盘": prices,
            "最高": [p * 1.01 for p in prices],
            "最低": [p * 0.99 for p in prices],
        })
        result = run_backtest(df, self._buy_hold_strategy, take_profit=0.15)
        sells = [t for t in result["trades"] if t["action"] == "SELL"]
        reasons = [t.get("exit_reason", "") for t in sells]
        has_tp = any("止盈" in r for r in reasons)
        self.assertTrue(has_tp, f"Expected 止盈 in reasons: {reasons}")

    def test_trailing_stop_triggers(self):
        """移动止损触发"""
        # 先涨后跌 → 从高点回撤触发
        prices = [100, 102, 105, 108, 110, 112, 115, 113, 110, 107,
                  104, 101, 98, 95, 92, 90]
        df = pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=len(prices)),
            "收盘": prices,
            "最高": [p * 1.01 for p in prices],
            "最低": [p * 0.99 for p in prices],
        })
        result = run_backtest(df, self._buy_hold_strategy, trailing_stop=0.08)
        sells = [t for t in result["trades"] if t["action"] == "SELL"]
        reasons = [t.get("exit_reason", "") for t in sells]
        has_ts = any("移动止损" in r for r in reasons)
        self.assertTrue(has_ts, f"Expected 移动止损 in reasons: {reasons}")


# ── 多策略对比 ──────────────────────────────────


class TestCompareStrategies(unittest.TestCase):
    """compare_strategies 多策略对比测试"""

    def _make_kline(self, rows=200):
        np.random.seed(42)
        close = 50 + np.cumsum(np.random.randn(rows) * 0.5)
        return pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=rows),
            "收盘": close,
            "最高": close * 1.02,
            "最低": close * 0.98,
        })

    def test_default_strategies(self):
        """默认策略列表全部运行"""
        df = self._make_kline(200)
        results = compare_strategies(df, verbose=False)
        self.assertGreater(len(results), 0)

    def test_single_strategy(self):
        """指定单个策略"""
        df = self._make_kline(200)
        results = compare_strategies(df, strategies=["ma_cross"], verbose=False)
        self.assertIn("ma_cross", results)

    def test_unknown_strategy_skipped(self):
        """未知策略被跳过"""
        df = self._make_kline(200)
        results = compare_strategies(df, strategies=["nonexistent"], verbose=False)
        self.assertEqual(len(results), 0)

    def test_verbose_output(self):
        """verbose=True 时打印跳过信息（仅测不报错）"""
        df = self._make_kline(200)
        import io, sys
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            results = compare_strategies(df, strategies=["nonexistent"], verbose=True)
        finally:
            sys.stdout = old_stdout
        self.assertEqual(len(results), 0)
        output = captured.getvalue()
        self.assertIn("跳过", output)

    def test_skipped_strategy_verbose_false(self):
        """verbose=False 时不打印跳过信息"""
        df = self._make_kline(200)
        results = compare_strategies(df, strategies=["nonexistent"], verbose=False)
        self.assertEqual(len(results), 0)


# ── 参数优化 ──────────────────────────────────


class TestOptimizeStrategy(unittest.TestCase):
    """optimize_strategy 参数网格优化测试"""

    def _make_kline(self, rows=200):
        np.random.seed(42)
        close = 50 + np.cumsum(np.random.randn(rows) * 0.5)
        return pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=rows),
            "收盘": close,
            "最高": close * 1.02,
            "最低": close * 0.98,
        })

    def test_unknown_strategy(self):
        """未知策略返回 None"""
        result = optimize_strategy(None, "nonexistent")
        self.assertIsNone(result)

    def test_with_known_strategy(self):
        """已知策略返回最佳参数"""
        df = self._make_kline(200)
        result = optimize_strategy(df, "ma_cross")
        self.assertIsNotNone(result)
        self.assertIn("params", result)
        self.assertIn("metrics", result)

    def test_with_custom_param_grid(self):
        """自定义参数网格"""
        df = self._make_kline(200)
        result = optimize_strategy(df, "ma_cross", param_grid={"fast": [5], "slow": [20]})
        self.assertIsNotNone(result)
        self.assertEqual(result["params"], {"fast": 5, "slow": 20})

    def test_with_test_set(self):
        """含样本外验证"""
        df = self._make_kline(300)
        result = optimize_strategy(df, "ma_cross", test_pct=0.3)
        self.assertIsNotNone(result)
        self.assertIn("test_metrics", result)

    def test_large_param_grid(self):
        """超过10组参数 → 触发进度输出"""
        df = self._make_kline(200)
        grid = {"fast": [3, 5, 8, 10], "slow": [15, 20, 30]}  # 3*4=12 combos
        import io, sys
        captured = io.StringIO()
        old_stderr = sys.stderr
        sys.stderr = captured
        try:
            result = optimize_strategy(df, "ma_cross", param_grid=grid)
        finally:
            sys.stderr = old_stderr
        self.assertIsNotNone(result)
        output = captured.getvalue()
        self.assertIn("优化进度", output)
        self.assertIn("优化完成", output)



# ── JSON 导出 ──────────────────────────────────


class TestExportBacktestJson(unittest.TestCase):
    """export_backtest_json 测试"""

    def test_export_to_tempfile(self):
        """导出到临时文件并验证内容"""
        import tempfile
        result = {
            "metrics": {"总收益率%": 12.5},
            "trades": [{"action": "BUY", "price": 50.0}],
            "equity_curve": [100000, 100500],
            "summary": "收益率12.5%",
        }
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            export_backtest_json(result, path)
            import json
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["metrics"]["总收益率%"], 12.5)
            self.assertEqual(len(data["trades"]), 1)
        finally:
            os.unlink(path)
