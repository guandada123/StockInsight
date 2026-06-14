"""测试 psychology.py — 庄家意图/散户心态分析（纯逻辑函数，无外部依赖）"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest

import numpy as np
import pandas as pd

from stock_analyzer.psychology import (
    _assess_synergy,
    _calc_chasing,
    _calc_fear,
    _calc_greed,
    _calc_hesitation,
    _calc_panic,
    _chip_assessment,
    _describe_behavior,
    _detect_accumulation,
    _detect_distribution,
    _detect_uptrend,
    _detect_washout,
    _fallback_result,
    _overall_conclusion,
    _phase_assessment,
    _phase_risk,
    _psychology_advice,
    _volume_profile,
    analyze_manipulator_intention,
    analyze_retail_psychology,
    generate_combined_summary,
)


def _make_kline_df(rows=60, seed=42):
    """生成模拟K线DataFrame（含开盘/收盘/最高/最低/成交量/ATR）"""
    np.random.seed(seed)
    close = 50 + np.cumsum(np.random.randn(rows) * 0.5)
    return pd.DataFrame({
        "日期": pd.date_range("2025-01-01", periods=rows),
        "开盘": close * (1 - np.abs(np.random.randn(rows) * 0.005)),
        "收盘": close,
        "最高": close * (1 + np.abs(np.random.randn(rows) * 0.01)),
        "最低": close * (1 - np.abs(np.random.randn(rows) * 0.01)),
        "成交量": np.random.randint(500_000, 5_000_000, rows),
        "ATR": np.abs(np.random.randn(rows) * 1.5) + 0.5,
    })


class TestDetectAccumulation(unittest.TestCase):
    """建仓阶段检测"""

    def test_returns_tuple(self):
        df = _make_kline_df(60)
        closes = df["收盘"].values.astype(float)
        volumes = df["成交量"].values.astype(float)
        score, signals = _detect_accumulation(df, closes, volumes, 60)
        self.assertIsInstance(score, int)
        self.assertIsInstance(signals, list)

    def test_score_in_range(self):
        df = _make_kline_df(60)
        closes = df["收盘"].values.astype(float)
        volumes = df["成交量"].values.astype(float)
        score, signals = _detect_accumulation(df, closes, volumes, 60)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)


class TestDetectWashout(unittest.TestCase):
    """洗盘阶段检测"""

    def test_returns_tuple(self):
        df = _make_kline_df(60)
        closes = df["收盘"].values.astype(float)
        volumes = df["成交量"].values.astype(float)
        score, signals = _detect_washout(df, closes, volumes, 60)
        self.assertIsInstance(score, int)
        self.assertIsInstance(signals, list)

    def test_short_data(self):
        df = _make_kline_df(10)
        closes = df["收盘"].values.astype(float)
        volumes = df["成交量"].values.astype(float)
        score, signals = _detect_washout(df, closes, volumes, 10)
        self.assertIsInstance(score, int)


class TestDetectUptrend(unittest.TestCase):
    """拉升阶段检测"""

    def test_returns_tuple(self):
        df = _make_kline_df(60)
        closes = df["收盘"].values.astype(float)
        volumes = df["成交量"].values.astype(float)
        score, signals = _detect_uptrend(df, closes, volumes, 60)
        self.assertIsInstance(score, int)
        self.assertIsInstance(signals, list)

    def test_strong_uptrend(self):
        """强上升趋势应得分更高"""
        np.random.seed(99)
        closes = 50 + np.cumsum(np.random.randn(60) * 0.2 + 0.3)  # 明显上涨
        volumes = np.random.randint(500_000, 5_000_000, 60)
        df = pd.DataFrame({
            "开盘": closes * 0.99,
            "收盘": closes,
            "最高": closes * 1.01,
            "最低": closes * 0.98,
            "成交量": volumes,
        })
        score, _ = _detect_uptrend(df, closes, volumes, 60)
        self.assertGreater(score, 0)


class TestDetectDistribution(unittest.TestCase):
    """出货阶段检测"""

    def test_returns_tuple(self):
        df = _make_kline_df(60)
        closes = df["收盘"].values.astype(float)
        volumes = df["成交量"].values.astype(float)
        score, signals = _detect_distribution(df, closes, volumes, 60, "流出")
        self.assertIsInstance(score, int)
        self.assertIsInstance(signals, list)

    def test_with_inflow(self):
        df = _make_kline_df(60)
        closes = df["收盘"].values.astype(float)
        volumes = df["成交量"].values.astype(float)
        score, signals = _detect_distribution(df, closes, volumes, 60, "流入")
        self.assertIsInstance(score, int)


class TestVolumeProfile(unittest.TestCase):
    """量能分析"""

    def test_returns_string(self):
        df = _make_kline_df(60)
        volumes = df["成交量"].values.astype(float)
        result = _volume_profile(df, volumes, 60)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)


class TestChipAssessment(unittest.TestCase):
    """筹码评估"""

    def test_high_score(self):
        result = _chip_assessment(85)
        self.assertIsInstance(result, str)

    def test_low_score(self):
        result = _chip_assessment(20)
        self.assertIsInstance(result, str)


class TestPhaseAssessment(unittest.TestCase):
    """阶段综合评估"""

    def test_all_phases(self):
        df = _make_kline_df(60)
        closes = df["收盘"].values.astype(float)
        for phase in ["建仓", "洗盘", "拉升", "出货"]:
            result = _phase_assessment(phase, 60, df, closes, 60, "")
            self.assertIsInstance(result, str)


class TestPhaseRisk(unittest.TestCase):
    """阶段风险提示"""

    def test_all_phases(self):
        df = _make_kline_df(60)
        closes = df["收盘"].values.astype(float)
        for phase in ["建仓", "洗盘", "拉升", "出货"]:
            result = _phase_risk(phase, df, closes, 60)
            self.assertIsInstance(result, str)


class TestFallbackResult(unittest.TestCase):
    """回退结果"""

    def test_has_expected_keys(self):
        result = _fallback_result("测试原因")
        for key in ["phase", "phase_confidence", "signals", "volume_analysis",
                     "chip_analysis", "assessment", "risk_note"]:
            self.assertIn(key, result)

    def test_phase_is_unknown(self):
        result = _fallback_result("测试")
        self.assertEqual(result["phase"], "不明")


class TestManipulatorIntention(unittest.TestCase):
    """庄家意图主入口"""

    def test_returns_dict(self):
        df = _make_kline_df(60)
        result = analyze_manipulator_intention(df)
        self.assertIsInstance(result, dict)

    def test_has_all_keys(self):
        df = _make_kline_df(60)
        result = analyze_manipulator_intention(df)
        for key in ["phase", "phase_confidence", "signals", "volume_analysis",
                     "chip_analysis", "assessment", "risk_note"]:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_insufficient_data(self):
        df = _make_kline_df(15)
        result = analyze_manipulator_intention(df)
        self.assertEqual(result["phase"], "不明")

    def test_none_df(self):
        result = analyze_manipulator_intention(None)
        self.assertEqual(result["phase"], "不明")

    def test_with_fund_flow(self):
        df = _make_kline_df(60)
        result = analyze_manipulator_intention(df, fund_flow_direction="流入")
        self.assertIn(result["phase"], ["建仓", "洗盘", "拉升", "出货", "不明"])

    def test_phase_confidence_range(self):
        df = _make_kline_df(60)
        result = analyze_manipulator_intention(df)
        self.assertGreaterEqual(result["phase_confidence"], 0)
        self.assertLessEqual(result["phase_confidence"], 100)


class TestRetailPsychology(unittest.TestCase):
    """散户心态主入口"""

    def test_returns_dict(self):
        df = _make_kline_df(60)
        result = analyze_retail_psychology(df)
        self.assertIsInstance(result, dict)

    def test_has_all_keys(self):
        df = _make_kline_df(60)
        result = analyze_retail_psychology(df)
        for key in ["emotion", "emotion_score", "behavior_pattern",
                     "sentiment_indicators", "advice"]:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_insufficient_data(self):
        df = _make_kline_df(5)
        result = analyze_retail_psychology(df)
        self.assertEqual(result["emotion"], "未知")

    def test_none_df(self):
        result = analyze_retail_psychology(None)
        self.assertEqual(result["emotion"], "未知")

    def test_emotion_is_known(self):
        df = _make_kline_df(60)
        result = analyze_retail_psychology(df)
        valid = ["贪婪", "恐惧", "犹豫观望", "追涨", "恐慌抛售"]
        self.assertIn(result["emotion"], valid)

    def test_score_in_range(self):
        df = _make_kline_df(60)
        result = analyze_retail_psychology(df)
        self.assertGreaterEqual(result["emotion_score"], 0)
        self.assertLessEqual(result["emotion_score"], 100)


class TestEmotionCalculators(unittest.TestCase):
    """五个情绪计算函数"""

    def setUp(self):
        self.df = _make_kline_df(60)
        self.closes = self.df["收盘"].values.astype(float)
        self.volumes = self.df["成交量"].values.astype(float)
        self.n = 60
        self.rsi = 50
        self.near_5d = 2.0

    def test_calc_greed(self):
        score, indicators = _calc_greed(self.df, self.rsi, self.near_5d,
                                         self.closes, self.volumes, self.n)
        self.assertIsInstance(score, int)
        self.assertIsInstance(indicators, list)

    def test_calc_fear(self):
        score, indicators = _calc_fear(self.df, self.rsi, self.near_5d,
                                        self.closes, self.volumes, self.n)
        self.assertIsInstance(score, int)
        self.assertIsInstance(indicators, list)

    def test_calc_hesitation(self):
        score, indicators = _calc_hesitation(self.df, self.rsi, self.near_5d,
                                              self.closes, self.volumes, self.n)
        self.assertIsInstance(score, int)
        self.assertIsInstance(indicators, list)

    def test_calc_chasing(self):
        score, indicators = _calc_chasing(self.df, self.rsi, self.near_5d,
                                           self.closes, self.volumes, self.n)
        self.assertIsInstance(score, int)
        self.assertIsInstance(indicators, list)

    def test_calc_panic(self):
        score, indicators = _calc_panic(self.df, self.rsi, self.near_5d,
                                         self.closes, self.volumes, self.n)
        self.assertIsInstance(score, int)
        self.assertIsInstance(indicators, list)

    def test_all_scores_non_negative(self):
        for fn in [_calc_greed, _calc_fear, _calc_hesitation, _calc_chasing, _calc_panic]:
            score, _ = fn(self.df, self.rsi, self.near_5d,
                          self.closes, self.volumes, self.n)
            self.assertGreaterEqual(score, 0, f"{fn.__name__} returned negative")


class TestPsychologyHelpers(unittest.TestCase):
    """描述/建议文本生成"""

    def test_describe_behavior(self):
        for emotion in ["贪婪", "恐惧", "犹豫观望", "追涨", "恐慌抛售"]:
            result = _describe_behavior(emotion, 5.0, 70, 60)
            self.assertIsInstance(result, str)
            self.assertGreater(len(result), 0)

    def test_psychology_advice(self):
        for emotion in ["贪婪", "恐惧", "犹豫观望", "追涨", "恐慌抛售"]:
            result = _psychology_advice(emotion, -3.0, 30)
            self.assertIsInstance(result, str)
            self.assertGreater(len(result), 0)


class TestCombinedSummary(unittest.TestCase):
    """综合摘要"""

    def test_returns_dict(self):
        """generate_combined_summary 返回 dict"""
        pattern_result = {"primary": {"name": "启明星"}, "patterns": []}
        manipulator_result = {
            "phase": "拉升", "phase_confidence": 65,
            "signals": [], "volume_analysis": "", "chip_analysis": "",
            "assessment": "", "risk_note": "",
        }
        result = generate_combined_summary(pattern_result, manipulator_result)
        self.assertIsInstance(result, dict)

    def test_has_expected_keys(self):
        pattern_result = {"primary": {"name": "启明星"}, "patterns": []}
        manipulator_result = {
            "phase": "拉升", "phase_confidence": 65,
            "signals": [], "volume_analysis": "", "chip_analysis": "",
            "assessment": "", "risk_note": "",
        }
        result = generate_combined_summary(pattern_result, manipulator_result)
        for key in ["kline_summary", "manipulator_summary", "synergy_assessment", "overall_conclusion"]:
            self.assertIn(key, result)

    def test_none_inputs(self):
        result = generate_combined_summary(None, None)
        self.assertIsInstance(result, dict)


class TestSynergyAndConclusion(unittest.TestCase):
    """协同评估和总结"""

    def test_assess_synergy(self):
        patterns = [{"type": "bullish", "name": "启明星"}, {"type": "bullish", "name": "大阳线"}]
        result = _assess_synergy(patterns, "拉升", "上涨")
        self.assertIsInstance(result, str)

    def test_assess_synergy_empty(self):
        result = _assess_synergy([], "不明", "横盘")
        self.assertIsInstance(result, str)

    def test_overall_conclusion(self):
        result = _overall_conclusion(["启明星"], "拉升", "上涨", "强烈看涨")
        self.assertIsInstance(result, str)


if __name__ == "__main__":
    unittest.main()
