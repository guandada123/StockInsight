"""测试 patterns.py — K 线形态识别（日本蜡烛图形态检测 + 趋势判断）"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest

import numpy as np
import pandas as pd

from stock_analyzer import patterns


def _make_df(rows=120):
    """生成模拟 K 线数据，固定 seed 确保可重复"""
    np.random.seed(42)
    close = 50 + np.cumsum(np.random.randn(rows) * 0.5)
    opens = close * (1 + np.random.randn(rows) * 0.01)
    highs = np.maximum(opens, close) + np.abs(np.random.randn(rows) * 0.3)
    lows = np.minimum(opens, close) - np.abs(np.random.randn(rows) * 0.3)
    volumes = np.random.randint(1_000_000, 10_000_000, rows)
    df = pd.DataFrame({
        "日期": pd.date_range("2025-01-01", periods=rows),
        "开盘": np.round(opens, 2),
        "收盘": np.round(close, 2),
        "最高": np.round(highs, 2),
        "最低": np.round(lows, 2),
        "成交量": volumes,
    })
    return df


def _make_row(open_p, close_p, high_p, low_p, volume=5000000):
    """创建单行 K 线数据 (Series)"""
    return pd.Series({
        "开盘": float(open_p),
        "收盘": float(close_p),
        "最高": float(high_p),
        "最低": float(low_p),
        "成交量": volume,
    })


class TestHelpers(unittest.TestCase):
    """K 线辅助函数测试"""

    def test_body_positive(self):
        """实体大小为正"""
        row = _make_row(10, 12, 13, 9)
        self.assertAlmostEqual(patterns._body(row), 2.0)

    def test_body_bearish(self):
        """阴线实体也为正"""
        row = _make_row(12, 10, 13, 9)
        self.assertAlmostEqual(patterns._body(row), 2.0)

    def test_body_zero(self):
        """十字星实体为 0"""
        row = _make_row(10, 10, 13, 9)
        self.assertEqual(patterns._body(row), 0.0)

    def test_upper_shadow(self):
        """上影线计算"""
        row = _make_row(10, 12, 14, 9)  # high=14, max(close,open)=12
        self.assertAlmostEqual(patterns._upper_shadow(row), 2.0)

    def test_lower_shadow(self):
        """下影线计算"""
        row = _make_row(12, 10, 13, 8)  # low=8, min(close,open)=10
        self.assertAlmostEqual(patterns._lower_shadow(row), 2.0)

    def test_body_ratio_between_zero_and_one(self):
        """实体占比在 0-1 之间"""
        row = _make_row(10, 12, 14, 9)
        ratio = patterns._body_ratio(row)
        self.assertGreaterEqual(ratio, 0)
        self.assertLessEqual(ratio, 1)

    def test_body_ratio_zero_total(self):
        """总波幅为 0 时返回 0"""
        row = _make_row(10, 10, 10, 10)
        self.assertEqual(patterns._body_ratio(row), 0)

    def test_upper_shadow_zero(self):
        """无上影线"""
        row = _make_row(10, 14, 14, 9)
        self.assertEqual(patterns._upper_shadow(row), 0.0)

    def test_lower_shadow_zero(self):
        """无下影线（最低价等于开盘/收盘较小者）"""
        row = _make_row(10, 12, 14, 10)
        self.assertEqual(patterns._lower_shadow(row), 0.0)


class TestSingleCandlePatterns(unittest.TestCase):
    """单根 K 线形态测试"""

    # ── 大阳线 ──
    def test_big_bullish_true(self):
        """标准大阳线（涨 5%+，实体占比>60%）"""
        row = _make_row(10, 10.8, 10.9, 9.9)  # 涨 8%, 实体 0.8, total 1.0, ratio 0.8
        self.assertTrue(patterns.is_big_bullish(row, threshold=0.03))

    def test_big_bullish_small_gain(self):
        """涨幅不够不是大阳线"""
        row = _make_row(10, 10.15, 10.2, 9.9)  # 涨 1.5%，但可能有其他问题
        # 实体 0.15, total 0.3, ratio 0.5 < 0.6
        self.assertFalse(patterns.is_big_bullish(row, threshold=0.03))

    def test_big_bullish_bearish(self):
        """阴线不是大阳线"""
        row = _make_row(10, 9, 11, 8)
        self.assertFalse(patterns.is_big_bullish(row))

    # ── 大阴线 ──
    def test_big_bearish_true(self):
        """标准大阴线"""
        row = _make_row(10, 9.2, 10.2, 9.1)  # 跌 8%, ratio > 0.6
        self.assertTrue(patterns.is_big_bearish(row, threshold=0.03))

    def test_big_bearish_bullish(self):
        """阳线不是大阴线"""
        row = _make_row(10, 11, 12, 9)
        self.assertFalse(patterns.is_big_bearish(row))

    # ── 十字星 ──
    def test_doji_false_normal_candle(self):
        """普通K线不是十字星"""
        row = _make_row(10, 12, 13, 9)
        self.assertFalse(patterns.is_doji(row))

    # ── 锤子线 ──
    def test_hammer_true(self):
        """下跌趋势中的标准锤子线：下影线>=实体*2, 上影线<=实体*0.5, 实体占比<40%"""
        # open=10.5,close=9.8 → body=0.7; high=10.6,low=8.0
        # lower=min(9.8,10.5)-8.0=1.8 >= 1.4 ✅; upper=10.6-10.5=0.1 <= 0.35 ✅; ratio=0.7/2.6=0.27 < 0.4 ✅
        row = _make_row(10.5, 9.8, 10.6, 8.0)
        self.assertTrue(patterns.is_hammer(row, trend="down"))

    def test_hammer_wrong_trend(self):
        """上升趋势不是锤子线"""
        row = _make_row(10.5, 9.8, 10.6, 8.0)
        self.assertFalse(patterns.is_hammer(row, trend="up"))

    def test_hammer_no_lower_shadow(self):
        """无下影线不是锤子线"""
        row = _make_row(10, 12, 14, 10)
        self.assertFalse(patterns.is_hammer(row, trend="down"))

    # ── 倒锤子 ──
    def test_inverted_hammer_true(self):
        """下跌趋势中的标准倒锤子：上影线>=实体*2, 下影线<=实体*0.5, 实体占比<40%"""
        # open=9.0,close=9.3 → body=0.3; high=10.5,low=8.8
        # upper=10.5-9.3=1.2 >= 0.6 ✅; lower=9.0-8.8=0.2 <= 0.15? No!
        # Need lower <= body*0.5 = 0.15. Let me try low=8.95: lower=9.0-8.95=0.05 <= 0.15 ✅
        row = _make_row(9.0, 9.3, 10.2, 8.95)
        self.assertTrue(patterns.is_inverted_hammer(row, trend="down"))

    # ── 射击之星 ──
    def test_shooting_star_true(self):
        """上升趋势中的射击之星（与倒锤子同形）"""
        row = _make_row(10.0, 10.3, 11.5, 9.95)
        self.assertTrue(patterns.is_shooting_star(row, trend="up"))

    def test_shooting_star_wrong_trend(self):
        """下跌趋势不是射击之星"""
        row = _make_row(10.0, 10.3, 11.5, 9.95)
        self.assertFalse(patterns.is_shooting_star(row, trend="down"))

    # ── 吊颈线 ──
    def test_hanging_man_true(self):
        """上升趋势中的吊颈线（与锤子线同形）"""
        row = _make_row(11.5, 10.8, 11.6, 9.0)
        self.assertTrue(patterns.is_hanging_man(row, trend="up"))

    def test_hanging_man_wrong_trend(self):
        """下跌趋势不是吊颈线"""
        row = _make_row(11.5, 10.8, 11.6, 9.0)
        self.assertFalse(patterns.is_hanging_man(row, trend="down"))


class TestTwoCandlePatterns(unittest.TestCase):
    """两根 K 线形态测试"""

    def test_bullish_engulfing_true(self):
        """看涨吞没：前阴后阳覆盖"""
        prev = _make_row(10.5, 10, 10.8, 9.8)
        curr = _make_row(9.9, 10.6, 10.9, 9.7)
        self.assertTrue(patterns.is_bullish_engulfing(prev, curr))

    def test_bullish_engulfing_prev_bullish(self):
        """前阳线不是看涨吞没"""
        prev = _make_row(10, 10.5, 11, 9.5)
        curr = _make_row(10.4, 11, 11.2, 10)
        self.assertFalse(patterns.is_bullish_engulfing(prev, curr))

    def test_bullish_engulfing_curr_bearish(self):
        """后阴线不是看涨吞没"""
        prev = _make_row(11, 10, 11.5, 9.5)
        curr = _make_row(10.5, 10, 11, 9.5)
        self.assertFalse(patterns.is_bullish_engulfing(prev, curr))

    def test_bearish_engulfing_true(self):
        """看跌吞没：前阳后阴覆盖"""
        prev = _make_row(10, 10.5, 11, 9.5)
        curr = _make_row(10.6, 9.9, 10.8, 9.6)
        self.assertTrue(patterns.is_bearish_engulfing(prev, curr))

    def test_bearish_engulfing_prev_bearish(self):
        """前阴线不是看跌吞没"""
        prev = _make_row(10.5, 10, 11, 9.5)
        curr = _make_row(10.1, 9.8, 10.3, 9.6)
        self.assertFalse(patterns.is_bearish_engulfing(prev, curr))

    def test_bullish_harami_true(self):
        """看涨孕线（前大阴后小阳）"""
        prev = _make_row(12, 10, 12.2, 9.8)  # 实体 2
        curr = _make_row(10.2, 11, 11.2, 10)  # 实体 0.8 < 2
        self.assertTrue(patterns.is_bullish_harami(prev, curr))

    def test_bullish_harami_body_too_big(self):
        """后实体太大不是孕线"""
        prev = _make_row(10.5, 10, 11, 9.5)  # 实体 0.5
        curr = _make_row(10, 12, 12.5, 9.5)  # 实体 2, 太大
        self.assertFalse(patterns.is_bullish_harami(prev, curr))

    def test_bearish_harami_true(self):
        """看跌孕线（前大阳后小阴）"""
        prev = _make_row(10, 12, 12.2, 9.8)  # 实体 2
        curr = _make_row(11.8, 11, 12, 10.8)  # 实体 0.8 < 2
        self.assertTrue(patterns.is_bearish_harami(prev, curr))

    def test_dark_cloud_cover_true(self):
        """乌云盖顶"""
        prev = _make_row(10, 11, 11.2, 9.8)
        curr = _make_row(11.2, 10.4, 11.5, 10.2)
        # 前阳: 10->11, 后高开低走: 11.2->10.4, 收盘在前阳中点 10.5 以下
        self.assertTrue(patterns.is_dark_cloud_cover(prev, curr))

    def test_dark_cloud_cover_not_high_open(self):
        """不高开不是乌云盖顶"""
        prev = _make_row(10, 11, 11.2, 9.8)
        curr = _make_row(10.8, 10.4, 11, 10.2)
        self.assertFalse(patterns.is_dark_cloud_cover(prev, curr))

    def test_piercing_pattern_true(self):
        """刺透形态"""
        prev = _make_row(11, 10, 11.2, 9.5)  # 阴线 11->10
        curr = _make_row(9.8, 10.6, 10.8, 9.5)  # 低开高走 9.8->10.6, 过中点 10.5
        self.assertTrue(patterns.is_piercing_pattern(prev, curr))

    def test_piercing_pattern_not_low_open(self):
        """不低开不是刺透"""
        prev = _make_row(11, 10, 11.2, 9.8)
        curr = _make_row(10.2, 10.6, 10.8, 10)
        self.assertFalse(patterns.is_piercing_pattern(prev, curr))


class TestThreeCandlePatterns(unittest.TestCase):
    """三根 K 线形态测试"""

    def test_morning_star_true(self):
        """启明星（早晨之星）：阴线→小实体跳空→阳线回补过半"""
        # day1 bearish: open=12,close=10.5,high=12.5,low=10.2
        r1 = _make_row(12, 10.5, 12.5, 10.2)
        # day2 small body (<30%), gapped below r1.close=10.5: open=10.2,close=10.3,high=10.4,low=9.8
        # body=0.1, total=0.6, ratio=0.167, high=10.4 < min(10.5, r3.open) ✅
        r2 = _make_row(10.2, 10.3, 10.4, 9.8)
        # day3 bullish, close > midpoint of day1: open=10.6,close=11.5,high=11.8,low=10.4
        # close=11.5 > (12+10.5)/2=11.25 ✅
        r3 = _make_row(10.6, 11.5, 11.8, 10.4)
        self.assertTrue(patterns.is_morning_star(r1, r2, r3))

    def test_morning_star_day1_bullish(self):
        """第1天阳线不是启明星"""
        r1 = _make_row(10, 11, 12, 9)
        r2 = _make_row(10.3, 10.5, 10.6, 10.2)
        r3 = _make_row(10.6, 11.5, 11.8, 10.4)
        self.assertFalse(patterns.is_morning_star(r1, r2, r3))

    def test_evening_star_true(self):
        """黄昏之星：阳线→小实体跳空→阴线回落过半"""
        # day1 bullish: open=10,close=11.5,high=12,low=9.5
        r1 = _make_row(10, 11.5, 12, 9.5)
        # day2 small body, gapped up: open=11.8,close=11.7,high=12.2,low=11.6
        # body=0.1, total=0.6, ratio=0.167, low=11.6 > max(11.5, r3.open) ✅
        r2 = _make_row(11.8, 11.7, 12.2, 11.6)
        # day3 bearish, close < midpoint: open=11.0,close=10.0,high=11.2,low=9.8
        # close=10.0 < (10+11.5)/2=10.75 ✅
        r3 = _make_row(11.0, 10.0, 11.2, 9.8)
        self.assertTrue(patterns.is_evening_star(r1, r2, r3))

    def test_evening_star_day3_bullish(self):
        """第3天阳线不是黄昏之星"""
        r1 = _make_row(10, 11.5, 12, 9.5)
        r2 = _make_row(11.7, 11.5, 11.9, 11.3)
        r3 = _make_row(11, 11.5, 12, 10.8)
        self.assertFalse(patterns.is_evening_star(r1, r2, r3))

    def test_three_white_soldiers_true(self):
        """红三兵"""
        r1 = _make_row(10, 10.3, 10.5, 9.8)
        r2 = _make_row(10.4, 10.8, 11, 10.3)
        r3 = _make_row(10.9, 11.4, 11.6, 10.8)
        self.assertTrue(patterns.is_three_white_soldiers(r1, r2, r3))

    def test_three_white_soldiers_not_sequential(self):
        """收盘价不递增不是红三兵"""
        r1 = _make_row(10, 10.8, 11, 9.8)
        r2 = _make_row(10.9, 10.5, 11, 10.3)
        r3 = _make_row(10.6, 11, 11.2, 10.4)
        self.assertFalse(patterns.is_three_white_soldiers(r1, r2, r3))

    def test_three_black_crows_true(self):
        """三只乌鸦"""
        r1 = _make_row(12, 11.5, 12.2, 11.3)
        r2 = _make_row(11.4, 10.8, 11.5, 10.6)
        r3 = _make_row(10.7, 10, 10.8, 9.8)
        self.assertTrue(patterns.is_three_black_crows(r1, r2, r3))

    def test_three_black_crows_bullish(self):
        """阳线不是三只乌鸦"""
        r1 = _make_row(10, 11, 11.2, 9.8)
        r2 = _make_row(11, 10, 11.2, 9.8)
        r3 = _make_row(10, 9, 10.2, 8.8)
        self.assertFalse(patterns.is_three_black_crows(r1, r2, r3))


class TestTrendDetection(unittest.TestCase):
    """趋势判断测试"""

    def test_detect_trend_insufficient_data(self):
        """数据不足返回提示"""
        df = _make_df(10)
        result = patterns.detect_trend_phase(df)
        self.assertEqual(result, "数据不足")

    def test_detect_trend_none(self):
        """None 输入返回数据不足"""
        result = patterns.detect_trend_phase(None)
        self.assertEqual(result, "数据不足")

    def test_detect_trend_returns_valid_states(self):
        """返回有效的趋势状态"""
        df = _make_df(120)
        result = patterns.detect_trend_phase(df)
        self.assertIn(result, ["上升趋势", "下降趋势", "横盘整理", "数据不足"])

    def test_detect_trend_uptrend(self):
        """纯上升模拟数据应检测为上升趋势"""
        np.random.seed(123)
        closes = 10 + np.arange(120) * 0.15 + np.random.randn(120) * 0.1
        df = pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=120),
            "开盘": closes * 0.99,
            "收盘": closes,
            "最高": closes * 1.02,
            "最低": closes * 0.98,
            "成交量": np.full(120, 5000000),
        })
        result = patterns.detect_trend_phase(df)
        self.assertEqual(result, "上升趋势")

    def test_detect_trend_downtrend(self):
        """纯下降模拟数据应检测为下降趋势"""
        np.random.seed(456)
        closes = 100 - np.arange(120) * 0.2 + np.random.randn(120) * 0.1
        df = pd.DataFrame({
            "日期": pd.date_range("2025-01-01", periods=120),
            "开盘": closes * 0.99,
            "收盘": closes,
            "最高": closes * 1.02,
            "最低": closes * 0.98,
            "成交量": np.full(120, 5000000),
        })
        result = patterns.detect_trend_phase(df)
        self.assertEqual(result, "下降趋势")


class TestPatternDetection(unittest.TestCase):
    """detect_patterns 和 generate_kline_interpretation 测试"""

    def test_detect_patterns_returns_list(self):
        """detect_patterns 返回列表"""
        df = _make_df(120)
        result = patterns.detect_patterns(df)
        self.assertIsInstance(result, list)

    def test_detect_patterns_empty_df(self):
        """空 DataFrame 不报错"""
        empty = pd.DataFrame(columns=["日期", "开盘", "收盘", "最高", "最低", "成交量"])
        result = patterns.detect_patterns(empty)
        self.assertEqual(result, [])

    def test_detect_patterns_small_df(self):
        """数据太少时不报错"""
        df = _make_df(5)
        result = patterns.detect_patterns(df)
        self.assertIsInstance(result, list)

    def test_detect_patterns_each_has_keys(self):
        """每个检测到的形态有 name/date 等字段"""
        df = _make_df(200)
        result = patterns.detect_patterns(df)
        for p in result:
            self.assertIsInstance(p, dict)
            self.assertIn("name", p)

    def test_generate_kline_interpretation_returns_dict(self):
        """generate_kline_interpretation 返回字典"""
        df = _make_df(120)
        result = patterns.generate_kline_interpretation(df)
        self.assertIsInstance(result, dict)

    def test_generate_kline_interpretation_empty(self):
        """空 DataFrame 不报错"""
        empty = pd.DataFrame(columns=["日期", "开盘", "收盘", "最高", "最低", "成交量"])
        result = patterns.generate_kline_interpretation(empty)
        self.assertIsInstance(result, dict)

    def test_generate_kline_interpretation_small(self):
        """数据不足时不报错"""
        df = _make_df(5)
        result = patterns.generate_kline_interpretation(df)
        self.assertIsInstance(result, dict)

    def test_get_today_pattern(self):
        """今天的K线形态检测返回 dict"""
        prev = _make_row(10, 10.5, 11, 9.5)
        result = patterns.get_today_pattern(10.8, 11.2, 10.5, 11, prev, "up")
        self.assertIsInstance(result, dict)
        self.assertIn("name", result)

    def test_merge_today_data(self):
        """合并今日数据不报错"""
        df = _make_df(120)
        try:
            result = patterns.merge_today_data(df, 60, 62, 58, 61, 8000000)
            self.assertIsInstance(result, pd.DataFrame)
            self.assertEqual(len(result), len(df) + 1)
        except Exception as e:
            self.fail(f"merge_today_data raised: {e}")


if __name__ == "__main__":
    unittest.main()
