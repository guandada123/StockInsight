"""测试 quant.py — 纯计算函数 + 因子评分 + 信号检测分支覆盖"""
import os
import sys
import unittest
from typing import Any
from unittest.mock import patch
import pandas as pd
import numpy as np

from stock_analyzer import quant

def _make_df(rows=100):
    """构造带收盘价和成交量的标准 K 线 DataFrame"""
    np.random.seed(42)
    close = 50 + np.cumsum(np.random.randn(rows) * 0.5)
    df = pd.DataFrame({
        "日期": pd.date_range("2025-01-01", periods=rows),
        "开盘": close * 0.99,
        "收盘": close,
        "最高": close * 1.02,
        "最低": close * 0.98,
        "成交量": np.random.randint(1_000_000, 10_000_000, rows),
    })
    return df

def _add_ma(df):
    """添加均线列"""
    df = df.copy()
    df["MA5"] = df["收盘"].rolling(5).mean()
    df["MA10"] = df["收盘"].rolling(10).mean()
    df["MA20"] = df["收盘"].rolling(20).mean()
    df["MA60"] = df["收盘"].rolling(60).mean()
    return df

def _add_indicators(df):
    """添加技术指标列"""
    df = df.copy()
    close = df["收盘"]
    # MACD
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    df["DIF"] = ema12 - ema26
    df["DEA"] = df["DIF"].ewm(span=9).mean()
    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(span=14).mean()
    avg_loss = loss.ewm(span=14).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    df["RSI"] = 100 - (100 / (1 + rs))
    # KDJ
    low_min = close.rolling(9).min()
    high_max = close.rolling(9).max()
    rsv = (close - low_min) / (high_max - low_min + 1e-9) * 100
    df["K"] = rsv.ewm(com=2).mean()
    df["D"] = df["K"].ewm(com=2).mean()
    # ATR
    high = df["最高"]
    low = df["最低"]
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    df["ATR"] = tr.ewm(span=14).mean()
    # Bollinger
    df["BB_MIDDLE"] = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    df["BB_UPPER"] = df["BB_MIDDLE"] + 2 * bb_std
    df["BB_LOWER"] = df["BB_MIDDLE"] - 2 * bb_std
    # ADX
    df["DI_PLUS"] = np.abs(high.diff()).ewm(span=14).mean() / tr.ewm(span=14).mean() * 100
    df["DI_MINUS"] = np.abs(low.diff()).ewm(span=14).mean() / tr.ewm(span=14).mean() * 100
    dx = np.abs(df["DI_PLUS"] - df["DI_MINUS"]) / (df["DI_PLUS"] + df["DI_MINUS"] + 1e-9) * 100
    df["ADX"] = dx.ewm(span=14).mean()
    return df

# ═══════════════════════════════════════════
# 纯计算函数
# ═══════════════════════════════════════════

class TestNormalizeScore(unittest.TestCase):
    """_normalize_score 归一化"""

    def test_normal(self):
        self.assertAlmostEqual(quant._normalize_score(50, 0, 100), 50)

    def test_below_low(self):
        self.assertEqual(quant._normalize_score(-10, 0, 100), 0)

    def test_equal_low(self):
        self.assertEqual(quant._normalize_score(0, 0, 100), 0)

    def test_above_high(self):
        self.assertEqual(quant._normalize_score(200, 0, 100), 100)

    def test_equal_high(self):
        self.assertEqual(quant._normalize_score(100, 0, 100), 100)

    def test_inverted(self):
        """invert=True 反向归一化"""
        self.assertAlmostEqual(quant._normalize_score(20, 0, 100, invert=True), 80)

class TestDailyReturns(unittest.TestCase):
    """_daily_returns 日收益率"""

    def test_normal(self):
        df = pd.DataFrame({"收盘": [10.0, 10.5, 10.0, 11.0]})
        rets = quant._daily_returns(df)
        self.assertEqual(len(rets), 3)  # first is NaN

    def test_too_few_rows(self):
        df = pd.DataFrame({"收盘": [10.0]})
        rets = quant._daily_returns(df)
        self.assertEqual(len(rets), 0)

class TestCalcMaxDrawdown(unittest.TestCase):
    """calc_max_drawdown 最大回撤"""

    def setUp(self):
        self.returns = pd.Series([0.01, 0.02, -0.05, -0.03, 0.01, -0.02], name="returns")

    def test_normal(self):
        result = quant.calc_max_drawdown(self.returns)
        self.assertIn("max_drawdown_pct", result)
        self.assertIn("max_drawdown_duration_days", result)
        self.assertIn("current_drawdown_pct", result)

    def test_no_drawdown(self):
        """全是上涨——无回撤"""
        prices = pd.Series([100.0, 101.0, 102.5, 103.0, 104.0])
        result = quant.calc_max_drawdown(prices)
        self.assertEqual(result["max_drawdown_pct"], 0)

    def test_deep_drawdown(self):
        """深回撤"""
        rets = pd.Series([0.01, -0.10, -0.05, -0.03, 0.01])
        result = quant.calc_max_drawdown(rets)
        self.assertLess(result["max_drawdown_pct"], -10)

    def test_peak_then_crash(self):
        """冲高后暴跌"""
        rets = pd.Series([0.02, 0.03, -0.08, -0.07, 0.01])
        result = quant.calc_max_drawdown(rets)
        self.assertLess(result["max_drawdown_pct"], -10)

    def test_empty_series(self):
        result = quant.calc_max_drawdown(pd.Series([], dtype=float))
        self.assertEqual(result["max_drawdown_pct"], 0)

    def test_single_value(self):
        result = quant.calc_max_drawdown(pd.Series([0.01]))
        self.assertEqual(result["max_drawdown_pct"], 0)

class TestCalcSharpeSortino(unittest.TestCase):
    """Sharpe 和 Sortino 比率"""

    def test_sharpe_normal(self):
        rets = pd.Series([0.01, 0.02, -0.01, 0.01, 0.005])
        ratio = quant.calc_sharpe_ratio(rets)
        self.assertIsInstance(ratio, float)
        self.assertGreater(ratio, 0)

    def test_sharpe_zero_vol(self):
        """零波动率"""
        rets = pd.Series([0.01, 0.01, 0.01, 0.01])
        ratio = quant.calc_sharpe_ratio(rets)
        self.assertIsNone(ratio)

    def test_sortino_normal(self):
        rets = pd.Series([0.02, -0.01, -0.015, 0.01, 0.005, -0.02, 0.01, -0.005])
        ratio = quant.calc_sortino_ratio(rets)
        self.assertIsInstance(ratio, float)

    def test_sortino_no_downside(self):
        """全是正收益无下行风险"""
        rets = pd.Series([0.01, 0.02, 0.005, 0.01])
        ratio = quant.calc_sortino_ratio(rets)
        self.assertIsInstance(ratio, (float, type(None)))

class TestCalcVar(unittest.TestCase):
    """VaR 风险值"""

    def test_var_normal(self):
        rets = pd.Series([0.01, 0.02, -0.03, -0.01, 0.01, -0.02, 0.01, 0.005] * 10)
        result = quant.calc_var(rets)
        self.assertIn("VaR_95_pct", result)
        self.assertIn("CVaR_95_pct", result)

    def test_var_too_few(self):
        rets = pd.Series([0.01, -0.01])
        result = quant.calc_var(rets)
        self.assertIsNotNone(result)

class TestCalcCalmar(unittest.TestCase):
    """Calmar 比率"""

    def test_calmar_normal(self):
        daily_rets = pd.Series([0.01, 0.02, -0.01, 0.01, 0.005])
        close = pd.Series([100, 102, 100, 101, 101.5])
        ratio = quant.calc_calmar_ratio(daily_rets, close)
        self.assertIsNotNone(ratio)

    def test_calmar_zero_mdd(self):
        daily_rets = pd.Series([0.01, 0.01])
        close = pd.Series([100, 101])
        ratio = quant.calc_calmar_ratio(daily_rets, close)
        self.assertIsNone(ratio)

# ═══════════════════════════════════════════
# 因子评分函数
# ═══════════════════════════════════════════

class TestScoreMomentumFactor(unittest.TestCase):
    """score_momentum_factor 动量因子"""

    def test_normal(self):
        df = _make_df(120)
        result = quant.score_momentum_factor(df)
        self.assertIsInstance(result, dict)
        self.assertIn("score", result)
        self.assertIn("return_5d_pct", result["details"])

    def test_insufficient_data(self):
        """数据不足 60 天返回默认值"""
        df = _make_df(30)
        result = quant.score_momentum_factor(df)
        self.assertIn("score", result)

    def test_strong_momentum(self):
        """强动量"""
        close = np.concatenate([np.linspace(40, 50, 100), np.linspace(50, 70, 20)])
        df = pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=120),
            "收盘": close,
            "成交量": np.random.randint(1_000_000, 10_000_000, 120),
        })
        result = quant.score_momentum_factor(df)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

class TestScoreVolumeFactor(unittest.TestCase):
    """score_volume_factor 量能因子"""

    def test_normal(self):
        df = _make_df(120)
        result = quant.score_volume_factor(df)
        self.assertIsInstance(result, dict)
        self.assertIn("volume_ratio_score", result["details"])

    def test_high_volume_surge(self):
        """成交量突增"""
        vol = np.ones(120) * 5_000_000
        vol[-5:] = 20_000_000  # 最后5天放量
        close = 50 + np.cumsum(np.random.randn(120) * 0.3)
        df = pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=120),
            "收盘": close,
            "成交量": vol,
        })
        result = quant.score_volume_factor(df)
        self.assertIsInstance(result, dict)

    def test_includes_price_volume_relation(self):
        """量价配合关系"""
        df = _make_df(120)
        result = quant.score_volume_factor(df)
        self.assertIn("volume_ratio_score", result["details"])

class TestScoreRiskFactor(unittest.TestCase):
    """score_risk_factor 风险因子"""

    def test_normal(self):
        df = _add_indicators(_make_df(120))
        result = quant.score_risk_factor(df)
        self.assertIsInstance(result, dict)
        self.assertIn("atr_ratio_score", result["details"])

    def test_no_atr_column(self):
        """无 ATR 列"""
        df = _make_df(60)
        result = quant.score_risk_factor(df)
        self.assertIsInstance(result, dict)

    def test_high_volatility(self):
        """高波动"""
        close = 50 + np.cumsum(np.random.randn(120) * 2.0)  # high volatility
        df = pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=120),
            "收盘": close,
            "最高": close * 1.03,
            "最低": close * 0.97,
            "成交量": np.random.randint(1_000_000, 10_000_000, 120),
        })
        df = _add_indicators(df)
        result = quant.score_risk_factor(df)
        self.assertIn("atr_ratio_score", result["details"])

class TestScoreFundFlowFactor(unittest.TestCase):
    """score_fund_flow_factor 资金流因子"""

    def test_no_fund_flow_column(self):
        """无 fund_flow 列返回默认"""
        df = _make_df(60)
        result = quant.score_fund_flow_factor(df)
        self.assertIn("score", result)

    def test_empty_fund_flow(self):
        """空资金流"""
        df = _make_df(60)
        df["fund_flow"] = [{}] * 60
        result = quant.score_fund_flow_factor(df)
        self.assertIsInstance(result, dict)

    def test_with_fund_flow_data(self):
        """有资金流数据"""
        df = _make_df(60)
        flows = [
            {"main_net_inflow": 100_000_000, "super_large_net_inflow": 50_000_000}
            if i > 40
            else {"main_net_inflow": 10_000_000, "super_large_net_inflow": 5_000_000}
            for i in range(60)
        ]
        df["fund_flow"] = flows
        result = quant.score_fund_flow_factor(df)
        self.assertIn("score", result)
        self.assertIsInstance(result["score"], (int, float))

# ═══════════════════════════════════════════
# 信号检测 — 分支覆盖
# ═══════════════════════════════════════════

class TestDetectMACrossover(unittest.TestCase):
    """均线金叉/死叉检测"""

    def test_golden_cross(self):
        """MA5 上穿 MA10"""
        df = pd.DataFrame({
            "收盘": [10.0] * 20,
            "MA5": [9.5] * 9 + [10.5] * 11,
            "MA10": [10.0] * 20,
        })
        df.loc[10, "MA5"] = 10.2  # crossover at index 10
        result = quant.detect_ma_crossover(df)
        self.assertIsInstance(result, list)

    def test_death_cross(self):
        """MA5 下穿 MA10"""
        df = pd.DataFrame({
            "收盘": [10.0] * 20,
            "MA5": [10.5] * 9 + [9.5] * 11,
            "MA10": [10.0] * 20,
        })
        result = quant.detect_ma_crossover(df)
        self.assertIsInstance(result, list)

    def test_no_cross(self):
        """无交叉"""
        df = pd.DataFrame({
            "收盘": [10.0] * 20,
            "MA5": [11.0] * 20,
            "MA10": [10.0] * 20,
        })
        result = quant.detect_ma_crossover(df)
        self.assertEqual(len(result), 0)

class TestDetectMACDCrossover(unittest.TestCase):
    """MACD 金叉/死叉"""

    def test_golden_cross(self):
        df = pd.DataFrame({
            "收盘": [10.0] * 30,
            "DIF": [-0.1] * 14 + [0.05] * 16,
            "DEA": [0.0] * 30,
        })
        result = quant.detect_macd_crossover(df)
        self.assertIsInstance(result, list)

    def test_death_cross(self):
        df = pd.DataFrame({
            "收盘": [10.0] * 30,
            "DIF": [0.1] * 14 + [-0.05] * 16,
            "DEA": [0.0] * 30,
        })
        result = quant.detect_macd_crossover(df)
        self.assertIsInstance(result, list)

class TestDetectADXTrend(unittest.TestCase):
    """ADX 趋势检测"""

    def test_bullish_trend(self):
        df = pd.DataFrame({
            "收盘": list(range(10, 40)),
            "ADX": [30] * 30,
            "DI_PLUS": [35] * 30,
            "DI_MINUS": [15] * 30,
        })
        result = quant.detect_adx_trend(df)
        self.assertIsInstance(result, list)

    def test_bearish_trend(self):
        df = pd.DataFrame({
            "收盘": list(range(40, 10, -1)),
            "ADX": [30] * 30,
            "DI_PLUS": [15] * 30,
            "DI_MINUS": [35] * 30,
        })
        result = quant.detect_adx_trend(df)
        self.assertIsInstance(result, list)

    def test_ranging(self):
        """ADX<20 震荡——应返回 adx_ranging 信号"""
        df = pd.DataFrame({
            "收盘": [10.0] * 30,
            "ADX": [15] * 30,
            "DI_PLUS": [20] * 30,
            "DI_MINUS": [20] * 30,
        })
        result = quant.detect_adx_trend(df)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "adx_ranging")

class TestDetectChannelBreakout(unittest.TestCase):
    """通道突破检测"""

    def test_up_breakout(self):
        """向上突破——需要至少 lookback+1=21 行数据"""
        n = 27
        df = pd.DataFrame({
            "收盘": list(range(10, 10 + n)),
            "最高": list(range(11, 11 + n)),
            "最低": list(range(9, 9 + n)),
            "成交量": [1_000_000] * (n - 2) + [10_000_000, 15_000_000],
        })
        result = quant.detect_channel_breakout(df)
        self.assertIsInstance(result, list)

    def test_down_breakout(self):
        """向下突破"""
        df = pd.DataFrame({
            "收盘": list(range(40, 15, -1)) + [12, 10],
            "最高": list(range(41, 16, -1)) + [13, 11],
            "最低": list(range(39, 14, -1)) + [11, 9],
            "成交量": [1_000_000] * 25 + [10_000_000, 15_000_000],
        })
        result = quant.detect_channel_breakout(df)
        self.assertIsInstance(result, list)

    def test_no_breakout(self):
        df = pd.DataFrame({
            "收盘": [10.0] * 30,
            "最高": [11.0] * 30,
            "最低": [9.0] * 30,
            "成交量": [1_000_000] * 30,
        })
        result = quant.detect_channel_breakout(df)
        self.assertEqual(len(result), 0)

class TestDetectRSIReversal(unittest.TestCase):
    """RSI 反转信号"""

    def test_oversold_bounce(self):
        """超卖反弹 RSI < 25 且上升"""
        rsi = [30] * 15 + [20, 22, 24, 25, 26]
        df = pd.DataFrame({
            "收盘": list(range(20, 40)),
            "RSI": rsi,
        })
        result = quant.detect_rsi_reversal(df)
        self.assertIsInstance(result, list)

    def test_deep_oversold(self):
        """深度超卖 RSI < 20"""
        df = pd.DataFrame({
            "收盘": [10.0] * 30,
            "RSI": [15] * 30,
        })
        result = quant.detect_rsi_reversal(df)
        self.assertIsInstance(result, list)

    def test_overbought_drop(self):
        """超买回落 RSI > 75 且下降"""
        rsi = [60] * 15 + [80, 78, 76, 74, 72]
        df = pd.DataFrame({
            "收盘": list(range(40, 20, -1)),
            "RSI": rsi,
        })
        result = quant.detect_rsi_reversal(df)
        self.assertIsInstance(result, list)

    def test_deep_overbought(self):
        """深度超买 RSI > 80"""
        df = pd.DataFrame({
            "收盘": [10.0] * 30,
            "RSI": [85] * 30,
        })
        result = quant.detect_rsi_reversal(df)
        self.assertIsInstance(result, list)

    def test_normal_range(self):
        """正常区间无信号"""
        df = pd.DataFrame({
            "收盘": [10.0] * 30,
            "RSI": [50] * 30,
        })
        result = quant.detect_rsi_reversal(df)
        self.assertEqual(len(result), 0)

class TestDetectBollingerReversion(unittest.TestCase):
    """布林带回归信号"""

    def test_touch_upper(self):
        """触及上轨"""
        df = pd.DataFrame({
            "收盘": [12.0, 11.5, 11.0, 10.8, 10.5],
            "BB_UPPER": [11.0] * 5,
            "BB_LOWER": [9.0] * 5,
            "BB_MIDDLE": [10.0] * 5,
            "RSI": [50] * 5,
        })
        result = quant.detect_bollinger_reversion(df)
        self.assertIsInstance(result, list)

    def test_touch_lower(self):
        """触及下轨"""
        df = pd.DataFrame({
            "收盘": [9.0, 9.2, 9.5, 9.8, 10.0],
            "BB_UPPER": [11.0] * 5,
            "BB_LOWER": [10.0] * 5,
            "BB_MIDDLE": [10.5] * 5,
            "RSI": [50] * 5,
        })
        result = quant.detect_bollinger_reversion(df)
        self.assertIsInstance(result, list)

    def test_touch_upper_rsi_confirm(self):
        """触及上轨 + RSI>70 加强信号"""
        df = pd.DataFrame({
            "收盘": [12.5, 12.0, 11.8, 11.5, 11.2],
            "BB_UPPER": [11.0] * 5,
            "BB_LOWER": [9.0] * 5,
            "BB_MIDDLE": [10.0] * 5,
            "RSI": [75] * 5,
        })
        result = quant.detect_bollinger_reversion(df)
        self.assertIsInstance(result, list)

    def test_normal_range(self):
        """在带内无信号"""
        df = pd.DataFrame({
            "收盘": [10.0] * 10,
            "BB_UPPER": [11.0] * 10,
            "BB_LOWER": [9.0] * 10,
            "BB_MIDDLE": [10.0] * 10,
            "RSI": [50] * 10,
        })
        result = quant.detect_bollinger_reversion(df)
        self.assertEqual(len(result), 0)

# ═══════════════════════════════════════════
# 综合信号生成
# ═══════════════════════════════════════════

class TestGenerateAllSignals(unittest.TestCase):
    """generate_all_signals 综合信号"""

    def test_generates_all_signal_types(self):
        df = _add_indicators(_add_ma(_make_df(120)))
        result = quant.generate_all_signals(df)
        self.assertIsInstance(result, dict)
        self.assertIn("signals", result)
        self.assertIn("total_bullish", result)
        self.assertIn("total_bearish", result)
        self.assertIsInstance(result["signals"], list)

    def test_with_empty_df(self):
        result = quant.generate_all_signals(pd.DataFrame())
        self.assertIn("signals", result)
        self.assertEqual(len(result["signals"]), 0)
        self.assertEqual(result["total_bullish"], 0)
        self.assertEqual(result["total_bearish"], 0)

class TestConsolidateSignals(unittest.TestCase):
    """consolidate_signals 信号整合"""

    def test_normal(self):
        signals = {
            "signals": [
                {"type": "ma_golden_cross", "direction": "bullish", "strength": 3, "name": "MA金叉", "price": 10.0, "value": {}},
                {"type": "bollinger_lower_touch", "direction": "bullish", "strength": 2, "name": "布林下轨", "price": 10.0, "value": {}},
            ],
            "total_bullish": 2,
            "total_bearish": 0,
            "strongest_bullish_strength": 3,
            "strongest_bearish_strength": 0,
        }
        result = quant.consolidate_signals(signals)
        self.assertIn("bias", result)
        self.assertIn("bias_score", result)

    def test_all_empty(self):
        signals = {
            "signals": [],
            "total_bullish": 0,
            "total_bearish": 0,
            "strongest_bullish_strength": 0,
            "strongest_bearish_strength": 0,
        }
        result = quant.consolidate_signals(signals)
        self.assertEqual(result["bias"], "neutral")

# ═══════════════════════════════════════════
# 综合量化评分
# ═══════════════════════════════════════════

class TestCompositeQuantScore(unittest.TestCase):
    """composite_quant_score 综合评分"""

    def test_basic(self):
        df = _add_indicators(_add_ma(_make_df(120)))
        result = quant.composite_quant_score(df)
        self.assertIn("composite_score", result)
        self.assertIn("rating", result)
        self.assertIn("factor_scores", result)

    def test_with_fundamentals(self):
        df = _add_indicators(_add_ma(_make_df(120)))
        fundamentals = {"ROE": 15, "PE": 20, "name": "测试"}
        result = quant.composite_quant_score(df, fundamentals=fundamentals)
        self.assertIn("composite_score", result)

    def test_with_empty_df(self):
        result = quant.composite_quant_score(pd.DataFrame())
        self.assertIn("composite_score", result)

class TestRiskMetrics(unittest.TestCase):
    """calc_risk_metrics 综合风险指标 (保留原有)"""

    def test_normal(self):
        df = _make_df(120)
        result = quant.calc_risk_metrics(df)
        self.assertIsInstance(result, dict)
        for k in ("annualized_return_pct", "annualized_volatility_pct", "sharpe_ratio",
                   "sortino_ratio", "max_drawdown_pct", "calmar_ratio", "VaR_95_pct"):
            self.assertIn(k, result)

    def test_empty(self):
        result = quant.calc_risk_metrics(pd.DataFrame())
        self.assertIsInstance(result, dict)

class TestMakeSignal(unittest.TestCase):
    """_make_signal 辅助函数"""

    def test_basic(self):
        """_make_signal(type, name, direction, strength, description, price)"""
        s = quant._make_signal("golden_cross", "MA金叉", "bullish", 0.8, "MA5上穿MA10", 100.0)
        self.assertEqual(s["type"], "golden_cross")
        self.assertEqual(s["direction"], "bullish")
        self.assertEqual(s["strength"], 0.8)

# ═══════════════════════════════════════════
# 技术因子 (score_technical_factor 分支扩展)
# ═══════════════════════════════════════════

class TestScoreTechnicalFactor(unittest.TestCase):
    """技术因子 — 覆盖MACD/RSI/KDJ/均线排列多种状态"""

    def test_macd_bullish(self):
        """MACD 多头排列 (DIF>0, DIF>DEA)"""
        df = pd.DataFrame({
            "收盘": [10.0] * 60,
            "DIF": [0.5] * 60,
            "DEA": [0.3] * 60,
            "MA5": [10.0] * 60,
            "MA10": [10.0] * 60,
            "MA20": [10.0] * 60,
            "MA60": [10.0] * 60,
        })
        result = quant.score_technical_factor(df)
        self.assertIn("macd_score", result["details"])

    def test_macd_bearish(self):
        """MACD 空头 (DIF<0, DIF<DEA)"""
        df = pd.DataFrame({
            "收盘": [10.0] * 60,
            "DIF": [-0.5] * 60,
            "DEA": [-0.3] * 60,
            "MA5": [10.0] * 60,
            "MA10": [10.0] * 60,
            "MA20": [10.0] * 60,
            "MA60": [10.0] * 60,
        })
        result = quant.score_technical_factor(df)
        self.assertIn("macd_score", result["details"])

    def test_rsi_overbought(self):
        """RSI > 80"""
        df = pd.DataFrame({
            "收盘": [10.0] * 60,
            "RSI": [85] * 60,
            "DIF": [0.1] * 60,
            "DEA": [0.05] * 60,
            "K": [50] * 60,
            "D": [50] * 60,
            "MA5": [10.0] * 60,
            "MA10": [10.0] * 60,
            "MA20": [10.0] * 60,
            "MA60": [10.0] * 60,
        })
        result = quant.score_technical_factor(df)
        self.assertIn("rsi_score", result["details"])

    def test_rsi_oversold(self):
        """RSI < 25"""
        df = pd.DataFrame({
            "收盘": [10.0] * 60,
            "RSI": [20] * 60,
            "DIF": [-0.1] * 60,
            "DEA": [-0.05] * 60,
            "K": [50] * 60,
            "D": [50] * 60,
            "MA5": [10.0] * 60,
            "MA10": [10.0] * 60,
            "MA20": [10.0] * 60,
            "MA60": [10.0] * 60,
        })
        result = quant.score_technical_factor(df)
        self.assertIn("rsi_score", result["details"])

    def test_kdj_golden_cross(self):
        """K 上穿 D"""
        k = [40] * 10 + [60] * 50
        d = [45] * 60
        df = pd.DataFrame({
            "收盘": [10.0] * 60,
            "K": k,
            "D": d,
            "RSI": [50] * 60,
            "DIF": [0.1] * 60,
            "DEA": [0.05] * 60,
            "MA5": [10.0] * 60,
            "MA10": [10.0] * 60,
            "MA20": [10.0] * 60,
            "MA60": [10.0] * 60,
        })
        result = quant.score_technical_factor(df)
        self.assertIn("kdj_score", result["details"])

    def test_ma_bullish_alignment(self):
        """均线多头排列 (MA5>MA10>MA20>MA60)"""
        df = pd.DataFrame({
            "收盘": [10.0] * 60,
            "MA5": [10.4] * 60,
            "MA10": [10.3] * 60,
            "MA20": [10.2] * 60,
            "MA60": [10.1] * 60,
            "DIF": [0.1] * 60,
            "DEA": [0.05] * 60,
            "RSI": [50] * 60,
            "K": [50] * 60,
            "D": [50] * 60,
        })
        result = quant.score_technical_factor(df)
        self.assertIsInstance(result, dict)

# ═══════════════════════════════════════════
# 文本情感因子（完全未覆盖）
# ═══════════════════════════════════════════

class TestScoreSentimentFactor(unittest.TestCase):
    """score_sentiment_factor 舆情/情感因子"""

    def test_no_news_no_sentiment(self):
        """无新闻无微博数据 → None"""
        result = quant.score_sentiment_factor("000001", None, None)
        self.assertIsNone(result)

    def test_no_news_empty_sentiment(self):
        """无新闻 + 空微博 → None"""
        result = quant.score_sentiment_factor("000001", None, pd.DataFrame())
        self.assertIsNone(result)

    def test_empty_news_no_sentiment(self):
        """空新闻 + 空微博 → None"""
        result = quant.score_sentiment_factor("000001", pd.DataFrame(), None)
        self.assertIsNone(result)

    def test_news_without_title_column(self):
        """新闻无标题列 → 走默认中性"""
        df_news = pd.DataFrame({"content": ["公司发布利好公告"]})
        result = quant.score_sentiment_factor("000001", df_news, None)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 50.0)

    def test_news_positive_keywords(self):
        """含正面关键词 → 偏正分数"""
        df_news = pd.DataFrame({"标题": ["公司发布利好公告，业绩超预期，中标大合同", "股价突破创新高"]})
        result = quant.score_sentiment_factor("000001", df_news, None)
        self.assertIsNotNone(result)
        self.assertGreater(result, 50)

    def test_news_negative_keywords(self):
        """含负面关键词 → 偏负分数"""
        df_news = pd.DataFrame({"标题": ["公司遭遇利空，股价下跌，业绩亏损预警"]})
        result = quant.score_sentiment_factor("000001", df_news, None)
        self.assertIsNotNone(result)
        self.assertLess(result, 50)

    def test_news_mixed_no_clear_trend(self):
        """有新闻但无明显倾向 → news_score=55 → composite=52"""
        df_news = pd.DataFrame({"标题": ["今日公司发布公告"]})
        result = quant.score_sentiment_factor("000001", df_news, None)
        # news_score=55 (no clear sentiment), weibo=50 → 55*0.4+50*0.6=52
        self.assertAlmostEqual(result, 52.0)

    @patch("stock_analyzer.screener.get_stock_name")
    def test_with_sentiment_matched(self, mock_get_name):
        """微博舆情匹配 → 调整分数"""
        mock_get_name.return_value = "测试公司"
        df_news = pd.DataFrame({"标题": ["利好"]})
        df_sentiment = pd.DataFrame({
            "name": ["测试公司"],
            "rate": [0.5],
        })
        result = quant.score_sentiment_factor("000001", df_news, df_sentiment)
        self.assertIsNotNone(result)
        # news=50+1/1*40=90, weibo=50+0.5*40=70, composite=90*0.4+70*0.6=78
        self.assertAlmostEqual(result, 78.0)

    @patch("stock_analyzer.screener.get_stock_name")
    def test_with_sentiment_no_match(self, mock_get_name):
        """微博舆情无匹配 → 只用新闻"""
        mock_get_name.return_value = "测试公司"
        df_news = pd.DataFrame({"标题": ["利好"]})
        df_sentiment = pd.DataFrame({
            "name": ["其他公司"],
            "rate": [0.5],
        })
        result = quant.score_sentiment_factor("000001", df_news, df_sentiment)
        self.assertIsNotNone(result)
        # weibo stays 50 (no match)
        self.assertAlmostEqual(result, 90 * 0.4 + 50 * 0.6)  # = 66

    @patch("stock_analyzer.screener.get_stock_name")
    def test_sentiment_negative_rate(self, mock_get_name):
        """微博负面情绪"""
        mock_get_name.return_value = "测试公司"
        df_news = pd.DataFrame({"标题": ["公告"]})
        df_sentiment = pd.DataFrame({
            "name": ["测试公司"],
            "rate": [-0.8],
        })
        result = quant.score_sentiment_factor("000001", df_news, df_sentiment)
        self.assertIsNotNone(result)
        # news=55 (no clear sentiment), weibo=50+(-0.8)*40=18
        # composite = 55*0.4+18*0.6 = 22+10.8 = 32.8
        # news_score=55 (无关键词), weibo=50+(-0.8)*40=18 → 55*0.4+18*0.6=32.8
        self.assertAlmostEqual(result, 32.8)

    @patch("stock_analyzer.screener.get_stock_name")
    def test_sentiment_without_rate_column(self, mock_get_name):
        """微博无rate列"""
        mock_get_name.return_value = "测试公司"
        df_news = pd.DataFrame({"标题": []})
        df_sentiment = pd.DataFrame({"name": ["测试公司"]})
        result = quant.score_sentiment_factor("000001", df_news, df_sentiment)
        # news headlines is empty (list), so headlines = []
        # if headlines: is false, news_score stays 50
        # sentiment_df has no "rate" column, so weibo stays 50
        self.assertAlmostEqual(result, 50.0)

# ═══════════════════════════════════════════
# 边缘分支覆盖 — 风险指标
# ═══════════════════════════════════════════

class TestCalcRiskMetricsEdge(unittest.TestCase):
    """calc_annualized_return/volatility/sortino/max_drawdown 边缘"""

    def test_annualized_return_too_few(self):
        rets = pd.Series([0.01])
        self.assertIsNone(quant.calc_annualized_return(rets))

    def test_annualized_return_empty(self):
        self.assertIsNone(quant.calc_annualized_return(pd.Series(dtype=float)))

    def test_annualized_vol_too_few(self):
        rets = pd.Series([0.01])
        self.assertIsNone(quant.calc_annualized_volatility(rets))

    def test_annualized_vol_empty(self):
        self.assertIsNone(quant.calc_annualized_volatility(pd.Series(dtype=float)))

    def test_sortino_insufficient_downside(self):
        """下行数据不足2个 → None"""
        rets = pd.Series([0.01, 0.02, 0.03, 0.04, -0.01, 0.02])
        self.assertIsNone(quant.calc_sortino_ratio(rets))

    def test_sharpe_zero_returns(self):
        """零收益率时 Sharpe → None"""
        rets = pd.Series([0.01, -0.01, 0.02, -0.02, 0.01])
        # This should produce valid return
        ratio = quant.calc_sharpe_ratio(rets)
        self.assertIsInstance(ratio, float)

    def test_calmar_none_return(self):
        """ann_ret为None时 Calmar → None"""
        rets = pd.Series([0.01])
        close = pd.Series([100, 101])
        self.assertIsNone(quant.calc_calmar_ratio(rets, close))

    def test_max_drawdown_empty_indices(self):
        """无峰值 → 全区间为回撤"""
        prices = pd.Series([100.0, 99.0, 98.0, 97.0, 96.0])
        result = quant.calc_max_drawdown(prices)
        self.assertLess(result["max_drawdown_pct"], 0)
        self.assertGreater(result["max_drawdown_duration_days"], 0)

    def test_max_drawdown_single_peak(self):
        """只有一个峰值"""
        prices = pd.Series([100.0, 110.0, 105.0, 103.0, 102.0])
        result = quant.calc_max_drawdown(prices)
        self.assertLess(result["max_drawdown_pct"], 0)

    def test_var_empty(self):
        """空 returns → {VaR: None, CVaR: None}"""
        result = quant.calc_var(pd.Series(dtype=float))
        self.assertIsNone(result["VaR"])
        self.assertIsNone(result["CVaR"])

    def test_var_too_few(self):
        """不足10个 → {VaR: None, CVaR: None}"""
        rets = pd.Series([0.01, -0.01, 0.02, -0.02, 0.01])
        result = quant.calc_var(rets)
        self.assertIsNone(result["VaR"])
        self.assertIsNone(result["CVaR"])

    def test_daily_returns_no_close(self):
        """无收盘列 → 空Series"""
        df = pd.DataFrame({"开盘": [10.0, 11.0]})
        rets = quant._daily_returns(df)
        self.assertEqual(len(rets), 0)

    def test_risk_metrics_empty_df(self):
        """空DataFrame → 全None"""
        result = quant.calc_risk_metrics(pd.DataFrame())
        for v in result.values():
            self.assertIsNone(v)

    def test_risk_metrics_too_few(self):
        """不足10行 → 全None"""
        df = _make_df(5)
        result = quant.calc_risk_metrics(df)
        for v in result.values():
            self.assertIsNone(v)

# ═══════════════════════════════════════════
# 分支覆盖 — 量能因子
# ═══════════════════════════════════════════

class TestScoreVolumeFactorBranches(unittest.TestCase):
    """score_volume_factor 各分支"""

    def test_vol_ratio_gt_2(self):
        vol = [1_000_000] * 19 + [5_000_000]
        df = pd.DataFrame({"收盘": range(50, 70), "成交量": vol})
        result = quant.score_volume_factor(df)
        self.assertGreater(result["details"]["volume_ratio_score"], 80)

    def test_vol_ratio_gt_1_5(self):
        vol = [1_000_000] * 19 + [1_800_000]
        df = pd.DataFrame({"收盘": range(50, 70), "成交量": vol})
        result = quant.score_volume_factor(df)
        self.assertGreaterEqual(result["details"]["volume_ratio_score"], 70)

    def test_vol_ratio_gt_1_2(self):
        vol = [1_000_000] * 19 + [1_300_000]
        df = pd.DataFrame({"收盘": range(50, 70), "成交量": vol})
        result = quant.score_volume_factor(df)
        self.assertGreaterEqual(result["details"]["volume_ratio_score"], 55)

    def test_vol_ratio_gt_0_8(self):
        vol = [1_000_000] * 19 + [900_000]
        df = pd.DataFrame({"收盘": range(50, 70), "成交量": vol})
        result = quant.score_volume_factor(df)
        self.assertEqual(result["details"]["volume_ratio_score"], 50)

    def test_vol_ratio_gt_0_5(self):
        vol = [1_000_000] * 19 + [600_000]
        df = pd.DataFrame({"收盘": range(50, 70), "成交量": vol})
        result = quant.score_volume_factor(df)
        self.assertGreaterEqual(result["details"]["volume_ratio_score"], 30)

    def test_vol_ratio_low(self):
        vol = [1_000_000] * 19 + [100_000]
        df = pd.DataFrame({"收盘": range(50, 70), "成交量": vol})
        result = quant.score_volume_factor(df)
        self.assertLessEqual(result["details"]["volume_ratio_score"], 25)

    def test_vp_aligned_up(self):
        """量价同向上"""
        np.random.seed(99)
        close = list(range(50, 70))
        vol = [1_000_000 + i * 1000 for i in range(20)]
        df = pd.DataFrame({"收盘": close, "成交量": vol})
        result = quant.score_volume_factor(df)
        self.assertIn("volume_price_score", result["details"])

    def test_vp_diverging(self):
        """量价背离: 量增价跌"""
        close = list(range(70, 50, -1))
        vol = [1_000_000 + i * 1000 for i in range(20)]
        df = pd.DataFrame({"收盘": close, "成交量": vol})
        result = quant.score_volume_factor(df)
        self.assertIn("volume_price_score", result["details"])

    def test_vp_both_down(self):
        """量价同向下"""
        close = list(range(70, 50, -1))
        vol = [1_020_000 - i * 1000 for i in range(20)]
        df = pd.DataFrame({"收盘": close, "成交量": vol})
        result = quant.score_volume_factor(df)
        self.assertIn("volume_price_score", result["details"])

    def test_insufficient_data(self):
        df = _make_df(10)
        result = quant.score_volume_factor(df)
        self.assertEqual(result["score"], 50)

# ═══════════════════════════════════════════
# 分支覆盖 — 资金流因子
# ═══════════════════════════════════════════

class TestScoreFundFlowFactorBranches(unittest.TestCase):
    """score_fund_flow_factor 各金额/比例分支"""

    def _make_ff_df(self, main_ratio, super_ratio):
        df = _make_df(30)
        flows: list[dict[str, Any]] = [{}] * 29 + [{
            "主力净流入-净占比": main_ratio,
            "超大单净流入-净占比": super_ratio,
            "主力净流入-净额": 100_000_000,
        }]
        df["fund_flow"] = flows
        return df

    def test_main_ratio_gt_3(self):
        result = quant.score_fund_flow_factor(self._make_ff_df(5.0, 1.0))
        self.assertEqual(result["details"]["main_score"], 90)

    def test_main_ratio_gt_1(self):
        result = quant.score_fund_flow_factor(self._make_ff_df(2.0, 1.0))
        self.assertEqual(result["details"]["main_score"], 75)

    def test_main_ratio_gt_0(self):
        result = quant.score_fund_flow_factor(self._make_ff_df(0.5, 0))
        self.assertEqual(result["details"]["main_score"], 60)

    def test_main_ratio_gt_neg1(self):
        result = quant.score_fund_flow_factor(self._make_ff_df(-0.5, 0))
        self.assertEqual(result["details"]["main_score"], 45)

    def test_main_ratio_gt_neg3(self):
        result = quant.score_fund_flow_factor(self._make_ff_df(-2.0, 0))
        self.assertEqual(result["details"]["main_score"], 30)

    def test_main_ratio_neg3_or_below(self):
        result = quant.score_fund_flow_factor(self._make_ff_df(-5.0, 0))
        self.assertEqual(result["details"]["main_score"], 15)

    def test_super_ratio_gt_2(self):
        result = quant.score_fund_flow_factor(self._make_ff_df(1.0, 3.0))
        self.assertIsInstance(result, dict)

    def test_super_ratio_gt_0(self):
        result = quant.score_fund_flow_factor(self._make_ff_df(1.0, 1.0))
        self.assertIsInstance(result, dict)

    def test_super_ratio_gt_neg2(self):
        result = quant.score_fund_flow_factor(self._make_ff_df(1.0, -1.0))
        self.assertIsInstance(result, dict)

    def test_super_ratio_low(self):
        result = quant.score_fund_flow_factor(self._make_ff_df(1.0, -5.0))
        self.assertIsInstance(result, dict)

    def test_fund_flow_not_dict(self):
        """fund_flow 末行不是 dict"""
        df = _make_df(30)
        df["fund_flow"] = [42] * 30  # 整数而非 dict
        result = quant.score_fund_flow_factor(df)
        self.assertEqual(result["score"], 50)

# ═══════════════════════════════════════════
# 分支覆盖 — 风险因子
# ═══════════════════════════════════════════

class TestScoreRiskFactorBranches(unittest.TestCase):
    """score_risk_factor 各 ATR/回撤分支"""

    def test_atr_ratio_lt_2(self):
        """ATR占比 < 2%"""
        df = pd.DataFrame({
            "收盘": [100.0] * 30,
            "ATR": [1.5] * 30,  # 1.5/100 = 1.5%
        })
        result = quant.score_risk_factor(df)
        self.assertEqual(result["details"]["atr_ratio_score"], 80)

    def test_atr_ratio_gt_6(self):
        """ATR占比 > 6%"""
        df = pd.DataFrame({
            "收盘": [100.0] * 30,
            "ATR": [7.0] * 30,  # 7/100 = 7%
        })
        result = quant.score_risk_factor(df)
        self.assertEqual(result["details"]["atr_ratio_score"], 20)

    def test_atr_ratio_4_to_6(self):
        """ATR占比 4-6%"""
        df = pd.DataFrame({
            "收盘": [100.0] * 30,
            "ATR": [5.0] * 30,  # 5/100 = 5%
        })
        result = quant.score_risk_factor(df)
        self.assertEqual(result["details"]["atr_ratio_score"], 40)

    def test_dd20_gt_neg2(self):
        """20日回撤 > -2%"""
        # tail(20).max() = 100, last close = 99, dd20 = (99/100-1)*100 = -1 > -2
        close = [100] * 19 + [99]
        df = pd.DataFrame({"收盘": close, "ATR": [2.0] * 20})
        result = quant.score_risk_factor(df)
        self.assertEqual(result["details"]["drawdown_20d_score"], 80)

    def test_dd20_gt_neg5(self):
        """20日回撤 -5% ~ -2%"""
        # tail(20).max() = 100, last close = 96, dd20 = (96/100-1)*100 = -4
        close = [100] * 19 + [96]
        df = pd.DataFrame({"收盘": close, "ATR": [2.0] * 20})
        result = quant.score_risk_factor(df)
        self.assertEqual(result["details"]["drawdown_20d_score"], 60)

    def test_dd20_gt_neg10(self):
        """20日回撤 -10% ~ -5%"""
        # tail(20).max() = 100, last close = 93, dd20 = (93/100-1)*100 = -7
        close = [100] * 19 + [93]
        df = pd.DataFrame({"收盘": close, "ATR": [2.0] * 20})
        result = quant.score_risk_factor(df)
        self.assertEqual(result["details"]["drawdown_20d_score"], 40)

    def test_dd20_below_neg10(self):
        """20日回撤 < -10%"""
        # tail(20).max() = 100, last close = 85, dd20 = (85/100-1)*100 = -15
        close = [100] * 19 + [85]
        df = pd.DataFrame({"收盘": close, "ATR": [2.0] * 20})
        result = quant.score_risk_factor(df)
        self.assertEqual(result["details"]["drawdown_20d_score"], 20)

    def test_less_than_20_rows(self):
        """不足20行 → 回撤默认50"""
        df = pd.DataFrame({"收盘": [100.0] * 15, "ATR": [2.0] * 15})
        result = quant.score_risk_factor(df)
        self.assertEqual(result["details"]["drawdown_20d_score"], 50)

# ═══════════════════════════════════════════
# 分支覆盖 — 综合评分 (chase_penalty + rating)
# ═══════════════════════════════════════════

class TestCompositeQuantScoreBranches(unittest.TestCase):
    """composite_quant_score 追高惩罚 + 评级分支"""

    def test_chase_penalty_extreme(self):
        """近20日涨>40% → 扣15分"""
        close = list(range(50, 180))
        df = pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=130),
            "收盘": close,
            "最高": [c * 1.02 for c in close],
            "最低": [c * 0.98 for c in close],
            "成交量": [1_000_000] * 130,
        })
        df = _add_indicators(_add_ma(df))
        result = quant.composite_quant_score(df)
        self.assertIn("composite_score", result)

    def test_chase_penalty_high(self):
        """近20日涨30-40% → 扣10分"""
        close = list(range(50, 120))
        df = pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=70),
            "收盘": close,
            "最高": [c * 1.02 for c in close],
            "最低": [c * 0.98 for c in close],
            "成交量": [1_000_000] * 70,
        })
        df = _add_indicators(_add_ma(df))
        result = quant.composite_quant_score(df)
        self.assertIn("composite_score", result)

    def test_chase_penalty_light(self):
        """近20日涨25-30% → 扣5分"""
        close = list(range(50, 100))
        df = pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=50),
            "收盘": close,
            "最高": [c * 1.02 for c in close],
            "最低": [c * 0.98 for c in close],
            "成交量": [1_000_000] * 50,
        })
        df = _add_indicators(_add_ma(df))
        result = quant.composite_quant_score(df)
        self.assertIn("composite_score", result)

    def test_chase_penalty_5d(self):
        """近5日涨>15% → 扣3分（但20日不足25%）"""
        close_flat = [50] * 10 + list(range(50, 70))
        df = pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=len(close_flat)),
            "收盘": close_flat,
            "最高": [c * 1.02 for c in close_flat],
            "最低": [c * 0.98 for c in close_flat],
            "成交量": [1_000_000] * len(close_flat),
        })
        df = _add_indicators(_add_ma(df))
        result = quant.composite_quant_score(df)
        self.assertIn("composite_score", result)

    def test_rating_sell(self):
        """综合分20-40 → Sell"""
        # 下跌趋势使动量因子得分低
        close = list(range(100, 30, -1))
        df = pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=70),
            "收盘": close,
            "最高": [c * 1.01 for c in close],
            "最低": [c * 0.99 for c in close],
            "成交量": [1_000_000] * 70,
        })
        df = _add_indicators(_add_ma(df))
        result = quant.composite_quant_score(df)
        self.assertIn(result["rating"], ["Sell", "Strong Sell", "Hold"])

    def test_rating_strong_sell(self):
        """综合分<20 → Strong Sell 或 Sell"""
        close = list(range(100, 20, -1))
        df = pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=80),
            "收盘": close,
            "最高": [c * 1.01 for c in close],
            "最低": [c * 0.99 for c in close],
            "成交量": [1_000_000] * 80,
        })
        df = _add_indicators(_add_ma(df))
        result = quant.composite_quant_score(df)
        self.assertIn(result["rating"], ["Sell", "Strong Sell"])

    def test_fund_flow_unavailable_deleted(self):
        """fund_flow可用但权重重新分配"""
        df = _add_indicators(_add_ma(_make_df(120)))
        result = quant.composite_quant_score(df, fundamentals={"ROE": 15})
        # fundamentals available, weight redistribution
        self.assertIn("fundamental", result["factor_scores"])

# ═══════════════════════════════════════════
# 分支覆盖 — 信号检测
# ═══════════════════════════════════════════

class TestSignalDetectionEdge(unittest.TestCase):
    """信号检测边缘分支"""

    def test_ma_crossover_nan_col(self):
        """MA列含NaN → 跳过"""
        df = pd.DataFrame({
            "收盘": [10.0] * 5,
            "MA5": [np.nan] * 5,
            "MA10": [10.0] * 5,
        })
        result = quant.detect_ma_crossover(df)
        self.assertEqual(len(result), 0)

    def test_ma_crossover_golden(self):
        """MA5/MA10 金叉 — 最后一根K线MA5上穿MA10"""
        # prev (idx -2): MA5=9.5, MA10=10.0, last (idx -1): MA5=10.5, MA10=10.0
        df = pd.DataFrame({
            "收盘": [10.0] * 10,
            "MA5": [9.5, 9.5, 9.5, 9.5, 9.5, 9.5, 9.5, 9.5, 9.5, 10.5],
            "MA10": [10.0] * 10,
            "MA20": [10.0] * 10,
        })
        result = quant.detect_ma_crossover(df)
        self.assertGreater(len(result), 0)

    def test_ma_crossover_death(self):
        """MA5/MA10 死叉 — 最后一根K线MA5下穿MA10"""
        # prev (idx -2): MA5=10.5, MA10=10.0, last (idx -1): MA5=9.5, MA10=10.0
        df = pd.DataFrame({
            "收盘": [10.0] * 10,
            "MA5": [10.5, 10.5, 10.5, 10.5, 10.5, 10.5, 10.5, 10.5, 10.5, 9.5],
            "MA10": [10.0] * 10,
            "MA20": [10.0] * 10,
        })
        result = quant.detect_ma_crossover(df)
        self.assertGreater(len(result), 0)

    def test_ma_crossover_insufficient(self):
        """数据不足3行"""
        result = quant.detect_ma_crossover(pd.DataFrame({"收盘": [10.0]}))
        self.assertEqual(len(result), 0)

    def test_macd_missing_cols(self):
        """缺少DIF/DEA列"""
        df = pd.DataFrame({"收盘": [10.0] * 5})
        result = quant.detect_macd_crossover(df)
        self.assertEqual(len(result), 0)

    def test_adx_nan_values(self):
        """ADX值为NaN"""
        df = pd.DataFrame({
            "收盘": [10.0] * 25,
            "ADX": [np.nan] * 25,
            "DI_PLUS": [20] * 25,
            "DI_MINUS": [20] * 25,
        })
        result = quant.detect_adx_trend(df)
        self.assertEqual(len(result), 0)

    def test_bollinger_missing_cols(self):
        """缺少布林带列"""
        df = pd.DataFrame({"收盘": [10.0] * 25})
        result = quant.detect_bollinger_reversion(df)
        self.assertEqual(len(result), 0)

    def test_rsi_reversal_oversold_bounce(self):
        """RSI < 25 且上升 → 超卖反弹"""
        df = pd.DataFrame({
            "收盘": [10.0] * 10 + [10.5],
            "RSI": [20, 20, 20, 20, 20, 20, 20, 20, 20, 22, 24],
        })
        result = quant.detect_rsi_reversal(df)
        self.assertGreater(len(result), 0)

    def test_rsi_reversal_overbought_drop(self):
        """RSI > 75 且下降 → 超买回落"""
        df = pd.DataFrame({
            "收盘": [10.0] * 10 + [9.5],
            "RSI": [80, 80, 80, 80, 80, 80, 80, 80, 80, 78, 76],
        })
        result = quant.detect_rsi_reversal(df)
        self.assertGreater(len(result), 0)

    def test_rsi_no_signal_neutral(self):
        """RSI中性 → 无信号"""
        df = pd.DataFrame({
            "收盘": [10.0] * 10,
            "RSI": [50.0] * 10,
        })
        result = quant.detect_rsi_reversal(df)
        self.assertEqual(len(result), 0)

    def test_consolidate_strong_bullish(self):
        signals = {
            "signals": [
                {"direction": "bullish", "strength": 4},
                {"direction": "bullish", "strength": 4},
                {"direction": "bullish", "strength": 3},
            ],
            "total_bullish": 3,
            "total_bearish": 0,
            "strongest_bullish_strength": 4,
            "strongest_bearish_strength": 0,
        }
        result = quant.consolidate_signals(signals)
        self.assertEqual(result["bias"], "strong_bullish")

    def test_consolidate_strong_bearish(self):
        signals = {
            "signals": [
                {"direction": "bearish", "strength": 4},
                {"direction": "bearish", "strength": 4},
                {"direction": "bearish", "strength": 3},
            ],
            "total_bullish": 0,
            "total_bearish": 3,
            "strongest_bullish_strength": 0,
            "strongest_bearish_strength": 4,
        }
        result = quant.consolidate_signals(signals)
        self.assertEqual(result["bias"], "strong_bearish")

    def test_consolidate_bearish(self):
        signals = {
            "signals": [
                {"direction": "bearish", "strength": 3},
                {"direction": "bearish", "strength": 2},
                {"direction": "bullish", "strength": 1},
            ],
            "total_bullish": 1,
            "total_bearish": 2,
            "strongest_bullish_strength": 1,
            "strongest_bearish_strength": 3,
        }
        result = quant.consolidate_signals(signals)
        self.assertEqual(result["bias"], "bearish")

# ═══════════════════════════════════════════
# 短线/长线风格评估（完全未覆盖）
# ═══════════════════════════════════════════

def _rich_kline(rows=100, trend_up=True):
    """构建适合 evaluate_trading_style 的丰富 K 线"""
    np.random.seed(42)
    if trend_up:
        close = 50 + np.cumsum(np.random.randn(rows) * 0.3) + np.linspace(0, 15, rows)
    else:
        close = 50 + np.cumsum(np.random.randn(rows) * 0.3) - np.linspace(0, 15, rows)
    df = pd.DataFrame({
        "日期": pd.date_range("2025-01-01", periods=rows),
        "开盘": close * 0.99,
        "收盘": close,
        "最高": close * 1.02,
        "最低": close * 0.98,
        "成交量": np.random.randint(1_000_000, 10_000_000, rows),
    })
    df["MA5"] = df["收盘"].rolling(5).mean()
    df["MA10"] = df["收盘"].rolling(10).mean()
    df["MA20"] = df["收盘"].rolling(20).mean()
    df["MA60"] = df["收盘"].rolling(60).mean()
    ema12 = df["收盘"].ewm(span=12).mean()
    ema26 = df["收盘"].ewm(span=26).mean()
    df["DIF"] = ema12 - ema26
    df["DEA"] = df["DIF"].ewm(span=9).mean()
    delta = df["收盘"].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(span=14).mean()
    avg_loss = loss.ewm(span=14).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    df["RSI"] = 100 - (100 / (1 + rs))
    low_min = df["收盘"].rolling(9).min()
    high_max = df["收盘"].rolling(9).max()
    rsv = (df["收盘"] - low_min) / (high_max - low_min + 1e-9) * 100
    df["K"] = rsv.ewm(com=2).mean()
    df["D"] = df["K"].ewm(com=2).mean()
    high = df["最高"]
    low = df["最低"]
    prev_close = df["收盘"].shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    df["ATR"] = tr.ewm(span=14).mean()
    df["BB_MIDDLE"] = df["收盘"].rolling(20).mean()
    bb_std = df["收盘"].rolling(20).std()
    df["BB_UPPER"] = df["BB_MIDDLE"] + 2 * bb_std
    df["BB_LOWER"] = df["BB_MIDDLE"] - 2 * bb_std
    df["channel_high_20"] = df["最高"].rolling(20).max()
    df["DI_PLUS"] = np.abs(high.diff()).ewm(span=14).mean() / tr.ewm(span=14).mean() * 100
    df["DI_MINUS"] = np.abs(low.diff()).ewm(span=14).mean() / tr.ewm(span=14).mean() * 100
    dx = np.abs(df["DI_PLUS"] - df["DI_MINUS"]) / (df["DI_PLUS"] + df["DI_MINUS"] + 1e-9) * 100
    df["ADX"] = dx.ewm(span=14).mean()
    df["volume_ratio"] = df["成交量"] / df["成交量"].rolling(20).mean()
    return df.dropna()

class TestEvaluateTradingStyle(unittest.TestCase):
    """evaluate_trading_style 短线/长线风格评估"""

    def test_insufficient_data(self):
        """数据不足20行"""
        df = _make_df(10)
        result = quant.evaluate_trading_style(df)
        self.assertEqual(result["style"], "数据不足")

    def test_strong_bullish_full_metrics(self):
        """短线+长线，高置信度，含基本面和风险指标"""
        df = _rich_kline(120, trend_up=True)
        fundamentals = {"ROE": 18.0, "营收增长": 25.0, "PE": 15}
        risk_metrics = {
            "sharpe_ratio": 1.5,
            "max_drawdown_pct": -8.0,
            "annualized_volatility_pct": 20.0,
            "current_drawdown_pct": -2.0,
        }
        result = quant.evaluate_trading_style(df, fundamentals, risk_metrics)
        self.assertIn("short_term_score", result)
        self.assertIn("long_term_score", result)
        self.assertIn("style", result)
        self.assertIn("style_confidence", result)
        self.assertIn("factors", result)
        self.assertIn("short_term_basis", result)
        self.assertIn("long_term_basis", result)

    def test_short_term_style(self):
        """短线风格（短线高分，长线弱）"""
        df = _rich_kline(80, trend_up=True)
        risk_metrics = {
            "sharpe_ratio": 0.3,
            "max_drawdown_pct": -25.0,
            "annualized_volatility_pct": 35.0,
            "current_drawdown_pct": -15.0,
        }
        result = quant.evaluate_trading_style(df, None, risk_metrics)
        self.assertIn(result["style"], ["短线", "短线+长线", "长线"])

    def test_long_term_style(self):
        """长线风格（基本面好但短线弱）"""
        # 给一个震荡或下跌的k线
        close = 50 + np.cumsum(np.random.randn(120) * 0.3) - np.linspace(0, 5, 120)
        df = pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=120),
            "开盘": close * 0.99,
            "收盘": close,
            "最高": close * 1.02,
            "最低": close * 0.98,
            "成交量": np.random.randint(1_000_000, 10_000_000, 120),
        })
        df = _add_indicators(_add_ma(df))
        df["channel_high_20"] = df["最高"].rolling(20).max()
        df["volume_ratio"] = df["成交量"] / df["成交量"].rolling(20).mean()
        df = df.dropna()
        fundamentals = {"ROE": 20.0, "营收增长": 30.0}
        risk_metrics = {"sharpe_ratio": 0.8, "max_drawdown_pct": -12.0, "annualized_volatility_pct": 22.0, "current_drawdown_pct": -3.0}
        result = quant.evaluate_trading_style(df, fundamentals, risk_metrics)
        self.assertIn("style", result)

    def test_watch_style(self):
        """观望风格（双低）"""
        df = _rich_kline(60, trend_up=False)
        risk_metrics = {
            "sharpe_ratio": -0.5,
            "max_drawdown_pct": -40.0,
            "annualized_volatility_pct": 30.0,
            "current_drawdown_pct": -20.0,
        }
        result = quant.evaluate_trading_style(df, None, risk_metrics)
        self.assertIsInstance(result["short_term_score"], (int, float))
        self.assertIsInstance(result["long_term_score"], (int, float))

    def test_without_risk_metrics(self):
        """不传 risk_metrics"""
        df = _rich_kline(80, trend_up=True)
        result = quant.evaluate_trading_style(df, {"ROE": 12.0}, None)
        self.assertIn("style", result)

    def test_without_fundamentals_or_risk(self):
        """不传基本面也不传风险指标——应使用K线趋势分析作为长线依据"""
        df = _rich_kline(80, trend_up=True)
        result = quant.evaluate_trading_style(df, None, None)
        self.assertIn("style", result)
        # 无基本面时，走 K 线趋势分析（MA60），不再返回"数据不足"
        self.assertIn("MA60", result["long_term_basis"])
        self.assertIn("长期趋势向上", result["long_term_basis"])

    def test_macd_bearish_path(self):
        """MACD空头分支"""
        df = _rich_kline(80, trend_up=False)
        result = quant.evaluate_trading_style(df, None, None)
        self.assertIsInstance(result["short_term_score"], (int, float))

    def test_volume_ratio_low(self):
        """成交量萎缩分支"""
        df = _rich_kline(80, trend_up=True)
        df["volume_ratio"] = 0.4  # 强制缩量
        result = quant.evaluate_trading_style(df, None, None)
        self.assertIsInstance(result["short_term_score"], (int, float))

    def test_roe_good_profitability(self):
        """ROE≥15 → 盈利能力优秀"""
        df = _rich_kline(80, trend_up=True)
        fundamentals = {"ROE": 18.0}
        risk_metrics = {"sharpe_ratio": 0.6, "max_drawdown_pct": -5.0, "annualized_volatility_pct": 22.0, "current_drawdown_pct": -2.0}
        result = quant.evaluate_trading_style(df, fundamentals, risk_metrics)
        self.assertIn("ROE", result["long_term_basis"])

    def test_roe_good_but_not_excellent(self):
        """ROE 10-15 → 盈利能力良好"""
        df = _rich_kline(80, trend_up=True)
        fundamentals = {"ROE": 12.0}
        risk_metrics = {"sharpe_ratio": 0.6, "max_drawdown_pct": -5.0, "annualized_volatility_pct": 22.0, "current_drawdown_pct": -2.0}
        result = quant.evaluate_trading_style(df, fundamentals, risk_metrics)
        self.assertIn("ROE", result["long_term_basis"])

    def test_roe_below_10(self):
        """ROE < 10 → 盈利能力一般"""
        df = _rich_kline(80, trend_up=True)
        fundamentals = {"ROE": 5.0}
        risk_metrics = {"sharpe_ratio": 0.6, "max_drawdown_pct": -5.0, "annualized_volatility_pct": 22.0, "current_drawdown_pct": -2.0}
        result = quant.evaluate_trading_style(df, fundamentals, risk_metrics)
        self.assertIn("ROE", result["long_term_basis"])

    def test_sharpe_below_0_5(self):
        """夏普比率偏低"""
        df = _rich_kline(80, trend_up=True)
        risk_metrics = {"sharpe_ratio": 0.2, "max_drawdown_pct": -5.0, "annualized_volatility_pct": 22.0, "current_drawdown_pct": -2.0}
        result = quant.evaluate_trading_style(df, {"ROE": 10.0}, risk_metrics)
        self.assertIn("夏普", result["long_term_basis"])

    def test_adx_below_15(self):
        """ADX < 15 → 趋势弱"""
        df = _rich_kline(80, trend_up=True)
        df["ADX"] = 10.0
        result = quant.evaluate_trading_style(df, None, None)
        self.assertIsInstance(result["short_term_score"], (int, float))

    def test_high_volatility_atr(self):
        """ATR > 5% → 高波动"""
        df = _rich_kline(80, trend_up=True)
        # 确保last["收盘"] > 0
        df["ATR"] = df["收盘"] * 0.06  # 6% ATR
        result = quant.evaluate_trading_style(df, None, None)
        self.assertIn("波动率", result["long_term_basis"])

    def test_rsi_over_70(self):
        """RSI > 70 → 注意回调"""
        df = _rich_kline(80, trend_up=True)
        df["RSI"] = 75.0
        df["K"] = 70
        df["D"] = 65
        result = quant.evaluate_trading_style(df, None, None)
        self.assertIn("RSI", result["short_term_basis"])

    def test_rsi_below_30(self):
        """RSI < 30 → 超跌反弹"""
        df = _rich_kline(80, trend_up=True)
        df["RSI"] = 25.0
        result = quant.evaluate_trading_style(df, None, None)
        self.assertIn("RSI", result["short_term_basis"])

    def test_bb_pos_gt_0_95(self):
        """布林带位置>0.95 → 扣分"""
        df = _rich_kline(80, trend_up=True)
        df["BB_LOWER"] = df["收盘"] - 10
        df["BB_UPPER"] = df["收盘"] + 10
        # 让收盘接近上轨
        df["收盘"] = df["BB_UPPER"] * 0.99
        result = quant.evaluate_trading_style(df, None, None)
        self.assertIn("short_term_basis", result)

    def test_lt_trend_below_ma60(self):
        """股价在MA60下方 → 趋势承压"""
        df = _rich_kline(80, trend_up=False)
        risk_metrics = {"sharpe_ratio": 0.5, "max_drawdown_pct": -5.0, "annualized_volatility_pct": 22.0, "current_drawdown_pct": -2.0}
        result = quant.evaluate_trading_style(df, {"ROE": 10.0}, risk_metrics)
        self.assertIn("MA60", result.get("long_term_basis", ""))

    def test_ret_60d_below_neg15(self):
        """60日涨幅 < -15%"""
        close = list(range(100, 20, -1))  # 大跌
        df = pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=80),
            "收盘": close,
            "最高": [c * 1.02 for c in close],
            "最低": [c * 0.98 for c in close],
            "成交量": np.random.randint(1_000_000, 10_000_000, 80),
        })
        df = _add_indicators(_add_ma(df))
        df["channel_high_20"] = df["最高"].rolling(20).max()
        df["volume_ratio"] = df["成交量"] / df["成交量"].rolling(20).mean()
        df = df.dropna()
        result = quant.evaluate_trading_style(df, None, None)
        self.assertIsInstance(result["long_term_score"], (int, float))

if __name__ == "__main__":
    unittest.main()
