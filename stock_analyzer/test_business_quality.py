import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest

import pandas as pd

from stock_analyzer import business_quality as bq


# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════


class TestSafeGet(unittest.TestCase):
    """_safe_get 安全取值"""

    def test_existing_column(self):
        df = pd.DataFrame({"股票简称": ["测试股票"]})
        result = bq._safe_get(df, "股票简称")
        self.assertEqual(result, "测试股票")

    def test_missing_column(self):
        df = pd.DataFrame({"A": [1]})
        result = bq._safe_get(df, "不存在")
        self.assertEqual(result, "")

    def test_custom_default(self):
        df = pd.DataFrame({"A": [1]})
        result = bq._safe_get(df, "不存在", default="N/A")
        self.assertEqual(result, "N/A")

    def test_none_value(self):
        df = pd.DataFrame({"A": [None]})
        result = bq._safe_get(df, "A", default="空")
        self.assertEqual(result, "空")

    def test_empty_df(self):
        df = pd.DataFrame()
        result = bq._safe_get(df, "A")
        self.assertEqual(result, "")


class TestSafeFloat(unittest.TestCase):
    """_safe_float 安全取浮点数"""

    def test_numeric_value(self):
        row = pd.Series({"净利润": 1.5e8})
        result = bq._safe_float(row, "净利润")
        self.assertAlmostEqual(result, 150000000)

    def test_missing_key(self):
        row = pd.Series({"A": 1})
        result = bq._safe_float(row, "不存在")
        self.assertEqual(result, 0.0)

    def test_custom_default(self):
        row = pd.Series({"A": 1})
        result = bq._safe_float(row, "不存在", default=-1.0)
        self.assertEqual(result, -1.0)

    def test_string_value(self):
        row = pd.Series({"A": "not a number"})
        result = bq._safe_float(row, "A")
        self.assertEqual(result, 0.0)

    def test_none_value(self):
        row = pd.Series({"A": None})
        result = bq._safe_float(row, "A")
        self.assertEqual(result, 0.0)

    def test_zero_value(self):
        row = pd.Series({"A": 0})
        result = bq._safe_float(row, "A")
        self.assertEqual(result, 0.0)


# ═══════════════════════════════════════════
# Fallback 函数
# ═══════════════════════════════════════════


class TestFallbacks(unittest.TestCase):
    """各类 fallback 返回函数"""

    def test_moat_fallback(self):
        result = bq._moat_fallback("数据不可用")
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["level"], "无法评估")
        self.assertIn("数据不可用", result["signals"][0])

    def test_cf_fallback(self):
        result = bq._cf_fallback()
        self.assertEqual(result["quality"], "数据不可用")
        self.assertEqual(result["operating_cf_yi"], 0)

    def test_lifecycle_fallback(self):
        result = bq._lifecycle_fallback()
        self.assertEqual(result["stage"], "unknown")
        self.assertEqual(result["confidence"], 0)
        self.assertIn("数据不足", result["signals"])


# ═══════════════════════════════════════════
# 护城河评估
# ═══════════════════════════════════════════


class TestMoatAssessment(unittest.TestCase):
    """_moat_assessment 文本生成"""

    def test_broad_moat(self):
        text = bq._moat_assessment("宽阔的护城河", 85, ["毛利率极高", "ROE优秀"])
        self.assertIn("宽阔的护城河", text)
        self.assertIn("85分", text)

    def test_moderate_moat(self):
        text = bq._moat_assessment("较宽的护城河", 65, ["毛利率较高"])
        self.assertIn("较宽的护城河", text)

    def test_narrow_moat(self):
        text = bq._moat_assessment("狭窄的护城河", 45, [])
        self.assertIn("狭窄的护城河", text)

    def test_no_moat(self):
        text = bq._moat_assessment("无明显护城河", 25, [])
        self.assertIn("无明显护城河", text)
        self.assertIn("竞争激烈", text)


# ═══════════════════════════════════════════
# 生命周期分类
# ═══════════════════════════════════════════


class TestClassifyLifecycle(unittest.TestCase):
    """生命周期阶段判断"""

    def test_high_growth(self):
        financials = {"营收增长": 35, "净利润增长": 40, "ROE": 18}
        result = bq.classify_lifecycle("000001", financials=financials)
        self.assertEqual(result["stage"], "growth")
        self.assertIn("高速成长", result["stage_cn"])
        self.assertGreater(result["confidence"], 0)

    def test_growth_stage(self):
        financials = {"营收增长": 20, "净利润增长": 15, "ROE": 12}
        result = bq.classify_lifecycle("000001", financials=financials)
        self.assertEqual(result["stage"], "growth")
        self.assertEqual(result["stage_cn"], "成长期")

    def test_mature_stage(self):
        financials = {"营收增长": 8, "净利润增长": 5, "ROE": 12}
        result = bq.classify_lifecycle("000001", financials=financials)
        self.assertEqual(result["stage"], "mature")
        self.assertIn("成熟期", result["stage_cn"])

    def test_slow_growth(self):
        financials = {"营收增长": 2, "净利润增长": 1, "ROE": 6}
        result = bq.classify_lifecycle("000001", financials=financials)
        self.assertEqual(result["stage"], "mature")
        self.assertIn("放缓", result["stage_cn"])

    def test_decline(self):
        financials = {"营收增长": -10, "净利润增长": -15, "ROE": 3}
        result = bq.classify_lifecycle("000001", financials=financials)
        self.assertEqual(result["stage"], "decline")
        self.assertEqual(result["stage_cn"], "衰退期")

    def test_transition(self):
        financials = {"营收增长": -3, "净利润增长": 5, "ROE": 10}
        result = bq.classify_lifecycle("000001", financials=financials)
        self.assertEqual(result["stage"], "transition")

    def test_not_dict_financials(self):
        result = bq.classify_lifecycle("000001", financials="not a dict")
        self.assertEqual(result["stage"], "unknown")

    def test_none_values(self):
        financials = {"营收增长": None, "净利润增长": None, "ROE": None}
        result = bq.classify_lifecycle("000001", financials=financials)
        self.assertIn(result["stage"], ["mature", "transition"])

    def test_zero_values(self):
        financials = {"营收增长": 0, "净利润增长": 0, "ROE": 0}
        result = bq.classify_lifecycle("000001", financials=financials)
        self.assertEqual(result["stage"], "mature")  # >= 0 path


# ═══════════════════════════════════════════
# 估值评分
# ═══════════════════════════════════════════


class TestScoreValuation(unittest.TestCase):
    """估值评分"""

    def test_low_pe_undervalued(self):
        financials = {"市盈率": 10, "市净率": 1.5, "营收增长": 20}
        result = bq.score_valuation("000001", price=50, financials=financials)
        self.assertIn(result["level"], ["低估", "合理偏低"])

    def test_high_pe_overvalued(self):
        financials = {"市盈率": 80, "市净率": 8, "营收增长": 5}
        result = bq.score_valuation("000001", price=50, financials=financials)
        self.assertIn(result["level"], ["高估", "泡沫"])

    def test_negative_pe(self):
        financials = {"市盈率": -5, "市净率": 2, "营收增长": 0}
        result = bq.score_valuation("000001", price=50, financials=financials)
        self.assertIsInstance(result["score"], int)

    def test_no_pe(self):
        financials = {"市净率": 2, "营收增长": 15}
        result = bq.score_valuation("000001", price=50, financials=financials)
        self.assertIsInstance(result["score"], int)

    def test_not_dict_graceful_degradation(self):
        """非 dict 输入优雅降级（所有指标取 None/默认值），不抛异常"""
        result = bq.score_valuation("000001", price=50, financials="bad")
        self.assertIsInstance(result["score"], int)
        self.assertIsNone(result["pe"])
        self.assertIsNone(result["pb"])

    def test_returns_pe_pb_peg(self):
        financials = {"市盈率": 20, "市净率": 3, "营收增长": 25}
        result = bq.score_valuation("000001", price=50, financials=financials)
        self.assertIn("pe", result)
        self.assertIn("pb", result)
        self.assertIn("peg", result)

    def test_peg_below_one(self):
        financials = {"市盈率": 15, "营收增长": 30}
        result = bq.score_valuation("000001", price=50, financials=financials)
        self.assertIsNotNone(result["peg"])
        self.assertLess(result["peg"], 1)

    def test_peg_above_three(self):
        financials = {"市盈率": 100, "营收增长": 10}
        result = bq.score_valuation("000001", price=50, financials=financials)
        self.assertGreater(result["peg"], 3)

    def test_pb_breakup(self):
        financials = {"市盈率": 15, "市净率": 0.5}
        result = bq.score_valuation("000001", price=50, financials=financials)
        self.assertIsNotNone(result["pb"])


# ═══════════════════════════════════════════
# 综合摘要
# ═══════════════════════════════════════════


class TestGenerateSummary(unittest.TestCase):
    """_generate_summary 文本生成"""

    def test_growth_good_moat(self):
        profile = {"main_business": "消费电子制造"}
        moat = {"score": 70, "level": "较宽的护城河"}
        cf = {"quality": "优秀"}
        lifecycle = {"stage": "growth", "stage_cn": "高速成长期"}
        valuation = {"score": 60, "level": "合理偏低"}

        result = bq._generate_summary("000001", "测试公司", profile, moat, cf, lifecycle, valuation)
        self.assertIsInstance(result, str)
        self.assertIn("测试公司", result)
        self.assertIn("优质", result)

    def test_decline_warning(self):
        profile = {"main_business": ""}
        moat = {"score": 25, "level": "无明显护城河"}
        cf = {"quality": "预警"}
        lifecycle = {"stage": "decline", "stage_cn": "衰退期"}
        valuation = {"score": 20, "level": "高估"}

        result = bq._generate_summary("000001", "测试", profile, moat, cf, lifecycle, valuation)
        self.assertIn("不建议介入", result)

    def test_mature_undervalued(self):
        profile = {}
        moat = {"score": 50, "level": "狭窄的护城河"}
        cf = {"quality": "良好"}
        lifecycle = {"stage": "mature", "stage_cn": "成熟期"}
        valuation = {"score": 70, "level": "低估"}

        result = bq._generate_summary("000001", "测试", profile, moat, cf, lifecycle, valuation)
        self.assertIn("价值投资者", result)


if __name__ == "__main__":
    unittest.main()
