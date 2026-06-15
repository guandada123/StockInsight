"""测试 analyzer.py — 深度分析引擎（check_national_team / merge_realtime_kline）"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from stock_analyzer.analyzer import _check_national_team, _merge_realtime_kline, deep_analyze


class TestCheckNationalTeam(unittest.TestCase):
    """国家队持仓查询测试"""

    @patch("stock_analyzer.cache.cached_national_team_holdings")
    def test_has_national_team(self, mock_cache):
        """有国家队持仓时返回 True 和名单"""
        mock_cache.return_value = {
            "has_national_team": True,
            "holders": ["社保基金", "养老金"]
        }
        has_nt, holders = _check_national_team("000001")
        self.assertTrue(has_nt)
        self.assertIn("社保基金", holders)

    @patch("stock_analyzer.cache.cached_national_team_holdings")
    def test_no_national_team(self, mock_cache):
        """无国家队持仓时返回 False 和空列表"""
        mock_cache.return_value = {"has_national_team": False, "holders": []}
        has_nt, holders = _check_national_team("000001")
        self.assertFalse(has_nt)
        self.assertEqual(holders, [])

    @patch("stock_analyzer.cache.cached_national_team_holdings")
    def test_cache_none(self, mock_cache):
        """缓存返回 None 时不报错"""
        mock_cache.return_value = None
        has_nt, holders = _check_national_team("000001")
        self.assertFalse(has_nt)
        self.assertEqual(holders, [])

    @patch("stock_analyzer.cache.cached_national_team_holdings")
    def test_cache_empty_dict(self, mock_cache):
        """缓存返回空字典时不报错"""
        mock_cache.return_value = {}
        has_nt, holders = _check_national_team("000001")
        self.assertFalse(has_nt)
        self.assertEqual(holders, [])

    @patch("stock_analyzer.cache.cached_national_team_holdings")
    def test_cache_exception(self, mock_cache):
        """缓存抛异常时静默处理"""
        mock_cache.side_effect = RuntimeError("DB error")
        has_nt, holders = _check_national_team("000001")
        self.assertFalse(has_nt)
        self.assertEqual(holders, [])

    @patch("stock_analyzer.cache.cached_national_team_holdings")
    def test_cache_not_dict(self, mock_cache):
        """缓存返回非 dict 时不报错"""
        mock_cache.return_value = "not_a_dict"
        has_nt, holders = _check_national_team("000001")
        self.assertFalse(has_nt)


class TestMergeRealtimeKline(unittest.TestCase):
    """实时行情合并到K线测试"""

    def _make_kline(self, rows=30):
        """生成模拟K线数据"""
        np.random.seed(42)
        close = 50 + np.cumsum(np.random.randn(rows) * 0.5)
        return pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=rows),
            "开盘": close * 0.99,
            "收盘": close,
            "最高": close * 1.02,
            "最低": close * 0.98,
            "成交量": np.random.randint(1_000_000, 10_000_000, rows),
            "成交额": np.random.randint(10_000_000, 100_000_000, rows),
        })

    def test_no_realtime_data(self):
        """无实时行情时返回原数据"""
        kline = self._make_kline(30)
        with patch("stock_analyzer.fetcher.sina_real_time", return_value={}):
            result = _merge_realtime_kline(kline, "000001")
            self.assertEqual(len(result), len(kline))

    def test_realtime_adds_new_day(self):
        """新交易日添加新行"""
        kline = self._make_kline(30)
        fake_rt = {
            "000001": {
                "open": "51.0", "high": "52.0", "low": "50.5",
                "price": "51.5", "volume": "5000000"
            }
        }
        with patch("stock_analyzer.fetcher.sina_real_time", return_value=fake_rt):
            result = _merge_realtime_kline(kline, "000001")
            # 如果今天日期 > 最后日期，会新增一行
            last_date = str(kline["日期"].iloc[-1])[:10]
            today = pd.Timestamp.now().strftime("%Y-%m-%d")
            if today > last_date:
                self.assertEqual(len(result), len(kline) + 1)
                self.assertEqual(float(result.iloc[-1]["收盘"]), 51.5)

    def test_realtime_code_not_in_data(self):
        """代码不在实时数据中返回原数据"""
        kline = self._make_kline(30)
        fake_rt = {"600000": {"open": "10", "high": "11", "low": "9.5", "price": "10.5", "volume": "1000"}}
        with patch("stock_analyzer.fetcher.sina_real_time", return_value=fake_rt):
            result = _merge_realtime_kline(kline, "000001")
            self.assertEqual(len(result), len(kline))

    def test_realtime_zero_price(self):
        """实时价格为0时不合并"""
        kline = self._make_kline(30)
        fake_rt = {"000001": {"open": "0", "high": "0", "low": "0", "price": "0", "volume": "0"}}
        with patch("stock_analyzer.fetcher.sina_real_time", return_value=fake_rt):
            result = _merge_realtime_kline(kline, "000001")
            self.assertEqual(len(result), len(kline))

    def test_realtime_exception(self):
        """sina_real_time 抛异常时静默处理"""
        kline = self._make_kline(30)
        with patch("stock_analyzer.fetcher.sina_real_time", side_effect=ConnectionError("timeout")):
            result = _merge_realtime_kline(kline, "000001")
            self.assertEqual(len(result), len(kline))

    def test_result_preserves_columns(self):
        """合并后保留原有列"""
        kline = self._make_kline(30)
        fake_rt = {
            "000001": {
                "open": "51.0", "high": "52.0", "low": "50.5",
                "price": "51.5", "volume": "5000000"
            }
        }
        with patch("stock_analyzer.fetcher.sina_real_time", return_value=fake_rt):
            result = _merge_realtime_kline(kline, "000001")
            for col in ["日期", "开盘", "收盘", "最高", "最低", "成交量"]:
                self.assertIn(col, result.columns)


# ──────────────────────────────────────────────
# TestDeepAnalyze — deep_analyze 完整流程
# ──────────────────────────────────────────────

class TestDeepAnalyze(unittest.TestCase):
    """deep_analyze 完整逻辑测试"""

    def _make_kline(self, rows=60):
        """生成含技术指标的K线"""
        np.random.seed(42)
        close = 50 + np.cumsum(np.random.randn(rows) * 0.5)
        dates = pd.date_range("2025-01-01", periods=rows)
        df = pd.DataFrame({
            "日期": dates,
            "开盘": close * 0.99,
            "收盘": close,
            "最高": close * 1.02,
            "最低": close * 0.98,
            "成交量": np.random.randint(1_000_000, 10_000_000, rows),
            "成交额": np.random.randint(10_000_000, 100_000_000, rows),
        })
        df["ATR"] = df["收盘"] * 0.02
        return df

    # ── 辅助：patch deep_analyze 所有内部依赖 ──
    def _patch_deps(self, **overrides):
        """Patch deep_analyze 的函数内 import 依赖。
        所有 import 发生在函数体内，运行时 patching 有效。
        返回 mock 名字典供断言使用。
        """
        defaults = {
            "sina": ("stock_analyzer.fetcher.sina_real_time",
                     {"000001": {"open": "49.0", "high": "50.0", "low": "48.0",
                                 "price": "49.5", "volume": "3000000"}}),
            "kline": ("stock_analyzer.cache.cached_kline", self._make_kline(120)),
            "funds": ("stock_analyzer.cache.cached_fundamentals",
                      {"ROE": 15.0, "PE": 20.0}),
            "techan": ("stock_analyzer.analysis.full_technical_analysis", None),  # identity
            "summary": ("stock_analyzer.analysis.get_technical_summary",
                        {"rsi_value": 55, "macd_signal": "bullish",
                         "kdj_signal": "golden_cross"}),
            "sr": ("stock_analyzer.analysis.calc_support_resistance",
                   {"支撑位": [48.0], "压力位": [52.0]}),
            "stop": ("stock_analyzer.analysis.calc_stop_levels",
                     {"止损参考价": 48.5, "止盈参考价": 52.5}),
            "risk": ("stock_analyzer.quant.calc_risk_metrics",
                     {"sharpe_ratio": 1.2, "max_drawdown_pct": -0.05,
                      "VaR_95_pct": -0.02, "annualized_volatility_pct": 0.15}),
            "signals": ("stock_analyzer.quant.generate_all_signals",
                        {"signals": [{"type": "ma_bullish"}],
                         "total_bullish": 1, "total_bearish": 0}),
            "consolidate": ("stock_analyzer.quant.consolidate_signals",
                            {"bias": "bullish", "score": 0.7}),
            "score_fund": ("stock_analyzer.analysis.score_fundamental", (8.5, {})),
            "quant": ("stock_analyzer.quant.composite_quant_score",
                      {"composite_score": 75.0, "rating": "B+",
                       "factor_scores": {
                           "momentum": {"score": 7.0},
                           "technical": {"score": 6.5},
                           "fundamental": {"score": 8.0},
                           "volume": {"score": 5.5},
                           "risk": {"score": 6.0},
                       }}),
            "trading": ("stock_analyzer.quant.evaluate_trading_style",
                        {"short_term_score": 7.5, "long_term_score": 6.0,
                         "style": "mixed", "style_confidence": "medium",
                         "short_term_basis": "momentum",
                         "long_term_basis": "value"}),
            "nt": ("stock_analyzer.cache.cached_national_team_holdings",
                   {"has_national_team": True,
                    "holders": ["社保基金", "养老金"]}),
        }
        defaults.update(overrides)

        mocks = {}
        for key, (target, ret) in defaults.items():
            p = patch(target)
            m = p.start()
            if key == "techan" and ret is None:
                # full_technical_analysis —— identity function
                m.side_effect = lambda df, _techan_self=m: df
            else:
                m.return_value = ret
            self.addCleanup(p.stop)
            mocks[key] = m
        return mocks

    # ── 测试用例 ──

    @patch("stock_analyzer.cache.cached_kline")
    def test_insufficient_kline(self, mock_kline):
        """少于20行K线 → 返回None"""
        mock_kline.return_value = self._make_kline(15)
        result = deep_analyze("000001")
        self.assertIsNone(result)

    def test_basic_deep_analyze(self):
        """完整分析路径 → 返回所有预期字段"""
        self._patch_deps()
        result = deep_analyze("000001")

        self.assertIsNotNone(result)
        self.assertEqual(result["code"], "000001")
        # 核心字段
        self.assertIn("qs_composite", result)
        self.assertEqual(result["qs_rating"], "B+")
        self.assertEqual(result["signal_bias"], "bullish")
        self.assertEqual(result["signal_score"], 0.7)
        # 收益率
        self.assertIsInstance(result["near_5d"], float)
        self.assertIsInstance(result["near_20d"], float)
        # 风险
        self.assertIn("sharpe", result)
        self.assertIn("max_dd", result)
        self.assertIn("var95", result)
        # 国家队
        self.assertTrue(result["has_nt"])
        self.assertIn("社保基金", result["nt_holders"])
        # 支撑压力
        self.assertTrue(len(result["support"]) > 0)
        self.assertTrue(len(result["resistance"]) > 0)
        # 原始数据
        self.assertIn("_kline", result)
        self.assertIn("fundamentals", result)
        self.assertIn("quant_score", result)

    def test_atr_nan_fallback(self):
        """ATR为NaN → 使用价格*3%作为ATR"""
        kline = self._make_kline(120)
        kline["ATR"] = np.nan
        self._patch_deps(kline=("stock_analyzer.cache.cached_kline", kline))
        result = deep_analyze("000001")
        self.assertIsNotNone(result)
        # 进入 NaN 分支后 atr = price * 0.03 > 0
        self.assertGreater(result["atr"], 0)

    def test_sr_not_dict(self):
        """calc_support_resistance 返回非dict → 使用价格*0.9/1.1作为默认值"""
        self._patch_deps(sr=("stock_analyzer.analysis.calc_support_resistance", None))
        result = deep_analyze("000001")
        self.assertIsNotNone(result)
        self.assertTrue(len(result["support"]) > 0)
        self.assertTrue(len(result["resistance"]) > 0)

    def test_skip_nt(self):
        """skip_nt=True → 不查国家队"""
        mocks = self._patch_deps()
        result = deep_analyze("000001", skip_nt=True)
        # nt patcher 没有被调用
        self.assertFalse(result["has_nt"])
        self.assertEqual(result["nt_holders"], [])

    def test_no_fundamentals(self):
        """cached_fundamentals 返回None → fund_score=0, roe=0"""
        self._patch_deps(
            funds=("stock_analyzer.cache.cached_fundamentals", None)
        )
        result = deep_analyze("000001")
        self.assertEqual(result["fund_score"], 0)
        self.assertEqual(result["roe"], 0)

    def test_exact_20_rows_sets_n20_zero(self):
        """K线刚好20行 → n5已计算, n20=0（len>20 为False）"""
        kline = self._make_kline(20)
        self._patch_deps(
            kline=("stock_analyzer.cache.cached_kline", kline),
            sina=("stock_analyzer.fetcher.sina_real_time", {}),
        )
        result = deep_analyze("000001")
        self.assertIsNotNone(result)
        # 20行，不触发 n5 或 n20 的 len 检查？
        # 实际上 n5: len>5 → True (20>5)
        # n20: len>20 → False (20是 False)
        self.assertNotEqual(result["near_5d"], 0)   # 有足够行计算
        self.assertEqual(result["near_20d"], 0)      # 行数不够21→0

    def test_non_dict_fallbacks(self):
        """quant/sigs/trading/stop 返回非dict时用空dict兜底"""
        self._patch_deps(
            quant=("stock_analyzer.quant.composite_quant_score", "not_a_dict"),
            consolidate=("stock_analyzer.quant.consolidate_signals", None),
            trading=("stock_analyzer.quant.evaluate_trading_style", [1, 2, 3]),
            stop=("stock_analyzer.analysis.calc_stop_levels", 12345),
        )
        result = deep_analyze("000001")
        self.assertIsNotNone(result)
        self.assertEqual(result["qs_composite"], 0)
        self.assertEqual(result["signal_bias"], "neutral")
        self.assertEqual(result["short_score"], 0)
        self.assertEqual(result["stop_loss"], 0)

    def test_tech_not_dict_fallback(self):
        """get_technical_summary 返回非dict → 默认值"""
        self._patch_deps(
            summary=("stock_analyzer.analysis.get_technical_summary", "bad_data")
        )
        result = deep_analyze("000001")
        self.assertEqual(result["rsi"], 50)
        self.assertEqual(result["macd_signal"], "")
        self.assertEqual(result["kdj_signal"], "")

    def test_factor_scores_not_dict(self):
        """factor_scores 中的子项不是dict时返回0"""
        self._patch_deps(
            quant=("stock_analyzer.quant.composite_quant_score",
                   {"composite_score": 50, "rating": "C",
                    "factor_scores": {
                        "momentum": "not_a_dict",
                        "technical": None,
                    }}),
        )
        result = deep_analyze("000001")
        self.assertEqual(result["mom_s"], 0)
        self.assertEqual(result["tech_s"], 0)


if __name__ == "__main__":
    unittest.main()
