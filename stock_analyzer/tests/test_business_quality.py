import os
import sys
import unittest
from typing import Any

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


class TestScoreMoat(unittest.TestCase):
    """Q4: 护城河五维度评分"""

    # ── 毛利率维度 ──
    def test_gross_margin_excellent(self):
        """毛利率 >= 70 → 40分"""
        r = bq.score_moat("000001", {"毛利率": 75, "ROE": 20, "净利率": 25, "营收增长": 15})
        self.assertEqual(r["dimensions"]["定价权(毛利率)"], 40)
        self.assertGreaterEqual(r["score"], 80)

    def test_gross_margin_high(self):
        """毛利率 50-70 → 30分"""
        r = bq.score_moat("000001", {"毛利率": 55, "ROE": 18, "净利率": 10, "营收增长": 12})
        self.assertEqual(r["dimensions"]["定价权(毛利率)"], 30)

    def test_gross_margin_moderate(self):
        """毛利率 30-50 → 20分"""
        r = bq.score_moat("000001", {"毛利率": 35, "ROE": 12, "净利率": 5, "营收增长": 8})
        self.assertEqual(r["dimensions"]["定价权(毛利率)"], 20)

    def test_gross_margin_low(self):
        """毛利率 15-30 → 10分"""
        r = bq.score_moat("000001", {"毛利率": 20, "ROE": 8, "净利率": 3, "营收增长": 5})
        self.assertEqual(r["dimensions"]["定价权(毛利率)"], 10)

    def test_gross_margin_very_low(self):
        """毛利率 < 15 → 5分"""
        r = bq.score_moat("000001", {"毛利率": 8, "ROE": 3, "净利率": 1, "营收增长": 2})
        self.assertEqual(r["dimensions"]["定价权(毛利率)"], 5)

    # ── ROE 维度 ──
    def test_roe_superb(self):
        """ROE >= 20 → 25分"""
        r = bq.score_moat("000001", {"毛利率": 40, "ROE": 25, "净利率": 10, "营收增长": 10})
        self.assertEqual(r["dimensions"]["盈利能力(ROE)"], 25)

    def test_roe_strong(self):
        """ROE 15-20 → 20分"""
        r = bq.score_moat("000001", {"毛利率": 40, "ROE": 17, "净利率": 10, "营收增长": 10})
        self.assertEqual(r["dimensions"]["盈利能力(ROE)"], 20)

    def test_roe_good(self):
        """ROE 10-15 → 15分"""
        r = bq.score_moat("000001", {"毛利率": 40, "ROE": 12, "净利率": 10, "营收增长": 10})
        self.assertEqual(r["dimensions"]["盈利能力(ROE)"], 15)

    def test_roe_fair(self):
        """ROE 5-10 → 8分"""
        r = bq.score_moat("000001", {"毛利率": 30, "ROE": 7, "净利率": 5, "营收增长": 5})
        self.assertEqual(r["dimensions"]["盈利能力(ROE)"], 8)

    def test_roe_poor(self):
        """ROE < 5 → 3分"""
        r = bq.score_moat("000001", {"毛利率": 10, "ROE": 2, "净利率": 1, "营收增长": 1})
        self.assertEqual(r["dimensions"]["盈利能力(ROE)"], 3)

    # ── 研发/技术壁垒维度 ──
    def test_rd_strong_tech(self):
        """毛利率>=50且差>=30 → 15分"""
        r = bq.score_moat("000001", {"毛利率": 65, "ROE": 15, "净利率": 10, "营收增长": 15})
        self.assertEqual(r["dimensions"]["技术壁垒(研发)"], 15)

    def test_rd_moderate_tech(self):
        """毛利率>=40且差>=20 → 10分"""
        r = bq.score_moat("000001", {"毛利率": 45, "ROE": 12, "净利率": 15, "营收增长": 10})
        self.assertEqual(r["dimensions"]["技术壁垒(研发)"], 10)

    def test_rd_some_tech(self):
        """毛利率>=30 → 5分"""
        r = bq.score_moat("000001", {"毛利率": 35, "ROE": 10, "净利率": 10, "营收增长": 8})
        self.assertEqual(r["dimensions"]["技术壁垒(研发)"], 5)

    def test_rd_low_tech(self):
        """毛利率<30 → 2分"""
        r = bq.score_moat("000001", {"毛利率": 15, "ROE": 5, "净利率": 5, "营收增长": 3})
        self.assertEqual(r["dimensions"]["技术壁垒(研发)"], 2)

    # ── 品牌/牌照维度 ──
    def test_brand_strong(self):
        """毛利率>=60且ROE>=15 → 10分"""
        r = bq.score_moat("000001", {"毛利率": 65, "ROE": 18, "净利率": 25, "营收增长": 15})
        self.assertEqual(r["dimensions"]["品牌/牌照"], 10)

    def test_brand_moderate(self):
        """毛利率>=40 → 7分"""
        r = bq.score_moat("000001", {"毛利率": 45, "ROE": 8, "净利率": 10, "营收增长": 8})
        self.assertEqual(r["dimensions"]["品牌/牌照"], 7)

    def test_brand_default(self):
        """低毛利率 → 默认5分"""
        r = bq.score_moat("000001", {"毛利率": 20, "ROE": 5, "净利率": 3, "营收增长": 3})
        self.assertEqual(r["dimensions"]["品牌/牌照"], 5)

    # ── 规模优势维度 ──
    def test_scale_high_growth(self):
        """营收增长>20 → 8分"""
        r = bq.score_moat("000001", {"毛利率": 30, "ROE": 10, "净利率": 5, "营收增长": 35})
        self.assertEqual(r["dimensions"]["规模优势"], 8)

    def test_scale_moderate_growth(self):
        """营收增长 10-20 → 6分"""
        r = bq.score_moat("000001", {"毛利率": 30, "ROE": 10, "净利率": 5, "营收增长": 15})
        self.assertEqual(r["dimensions"]["规模优势"], 6)

    def test_scale_slow_growth(self):
        """营收增长 0-10 → 4分"""
        r = bq.score_moat("000001", {"毛利率": 30, "ROE": 10, "净利率": 5, "营收增长": 5})
        self.assertEqual(r["dimensions"]["规模优势"], 4)

    def test_scale_negative_growth(self):
        """营收增长 <= 0 → 2分"""
        r = bq.score_moat("000001", {"毛利率": 20, "ROE": 5, "净利率": 3, "营收增长": -5})
        self.assertEqual(r["dimensions"]["规模优势"], 2)

    # ── 护城河等级 ──
    def test_moat_level_broad(self):
        """总分 >= 80 → 宽阔的护城河"""
        r = bq.score_moat("000001", {"毛利率": 75, "ROE": 25, "净利率": 30, "营收增长": 30})
        self.assertEqual(r["level"], "宽阔的护城河")
        self.assertGreaterEqual(r["score"], 80)

    def test_moat_level_wide(self):
        """总分 60-80 → 较宽的护城河"""
        r = bq.score_moat("000001", {"毛利率": 55, "ROE": 18, "净利率": 15, "营收增长": 20})
        self.assertEqual(r["level"], "较宽的护城河")
        self.assertGreaterEqual(r["score"], 60)
        self.assertLess(r["score"], 80)

    def test_moat_level_narrow(self):
        """总分 40-60 → 狭窄的护城河"""
        r = bq.score_moat("000001", {"毛利率": 35, "ROE": 10, "净利率": 8, "营收增长": 10})
        self.assertEqual(r["level"], "狭窄的护城河")
        self.assertGreaterEqual(r["score"], 40)
        self.assertLess(r["score"], 60)

    def test_moat_level_none(self):
        """总分 < 40 → 无明显护城河"""
        r = bq.score_moat("000001", {"毛利率": 10, "ROE": 3, "净利率": 2, "营收增长": 0})
        self.assertEqual(r["level"], "无明显护城河")
        self.assertLess(r["score"], 40)

    # ── 信号生成 ──
    def test_signals_high_gross_margin(self):
        """毛利率>=60 生成定价权信号"""
        r = bq.score_moat("000001", {"毛利率": 65, "ROE": 15, "净利率": 20, "营收增长": 10})
        signals_str = " ".join(r["signals"])
        self.assertIn("定价权", signals_str)

    def test_signals_moderate_gross_margin(self):
        """毛利率 40-60 生成议价能力信号"""
        r = bq.score_moat("000001", {"毛利率": 45, "ROE": 5, "净利率": 10, "营收增长": 5})
        signals_str = " ".join(r["signals"])
        self.assertIn("议价", signals_str)

    def test_signals_roe_excellent(self):
        """ROE>=15 生成ROE优秀信号"""
        r = bq.score_moat("000001", {"毛利率": 30, "ROE": 18, "净利率": 5, "营收增长": 5})
        signals_str = " ".join(r["signals"])
        self.assertIn("ROE", signals_str)

    def test_signals_rd_high(self):
        """毛利率-净利率差>=30 生成研发信号"""
        r = bq.score_moat("000001", {"毛利率": 65, "ROE": 12, "净利率": 15, "营收增长": 10})
        signals_str = " ".join(r["signals"])
        self.assertIn("研发", signals_str)

    # ── 边界/异常情况 ──
    def test_defaults_financials_none(self):
        """financials=None 走懒加载分支"""
        # 会触发 import cache，在无 DB 环境下会降级到 fallback
        r = bq.score_moat("999999")  # 不存在的代码，fundamentals 为 None
        self.assertIn("level", r)
        self.assertIn("score", r)

    def test_not_dict_financials(self):
        """financials 不是 dict — 返回 fallback"""
        r = bq.score_moat("000001", "not a dict")
        self.assertEqual(r["level"], "无法评估")
        self.assertEqual(r["score"], 0)

    def test_missing_fields_default_zero(self):
        """缺失字段默认为0"""
        r = bq.score_moat("000001", {})
        self.assertIsInstance(r["score"], int)
        self.assertIn("level", r)

    def test_none_values(self):
        """None 值被转为 0"""
        r = bq.score_moat(
            "000001",
            {"毛利率": None, "ROE": None, "净利率": None, "营收增长": None},
        )
        self.assertIsInstance(r["score"], int)

    def test_returns_all_keys(self):
        """返回完整字段"""
        r = bq.score_moat("000001", {"毛利率": 50, "ROE": 15, "净利率": 10, "营收增长": 12})
        for key in ("score", "level", "dimensions", "signals", "assessment"):
            self.assertIn(key, r)
        self.assertEqual(len(r["dimensions"]), 5)


# ═══════════════════════════════════════════
# 估值评分 (扩展：覆盖所有PE/PEG/PB区间)
# ═══════════════════════════════════════════


class TestScoreValuationExtended(unittest.TestCase):
    """估值评分 — 覆盖剩余未测区间"""

    def test_pe_25_to_50(self):
        """PE 25-50 → pe_score=15"""
        r = bq.score_valuation(
            "000001", price=50, financials={"市盈率": 35, "市净率": 2, "营收增长": 20}
        )
        self.assertIn("偏高", r["assessment"])

    def test_pe_50_to_100(self):
        """PE 50-100 → pe_score=8"""
        r = bq.score_valuation(
            "000001", price=50, financials={"市盈率": 70, "市净率": 5, "营收增长": 5}
        )
        self.assertIn(r["level"], ["高估", "泡沫"])

    def test_pe_over_100(self):
        """PE > 100 → pe_score=3"""
        r = bq.score_valuation(
            "000001", price=50, financials={"市盈率": 150, "市净率": 8, "营收增长": 2}
        )
        self.assertIn(">100倍", r["assessment"])

    def test_peg_1_to_2(self):
        """PEG 1-2 → peg_score=15"""
        r = bq.score_valuation("000001", price=50, financials={"市盈率": 25, "营收增长": 18})
        self.assertIsNotNone(r["peg"])
        self.assertGreaterEqual(r["peg"], 1)
        self.assertLess(r["peg"], 2)

    def test_peg_2_to_3(self):
        """PEG 2-3 → peg_score=8"""
        r = bq.score_valuation("000001", price=50, financials={"市盈率": 50, "营收增长": 20})
        self.assertIsNotNone(r["peg"])
        self.assertGreaterEqual(r["peg"], 2)
        self.assertLess(r["peg"], 3)

    def test_pb_very_high(self):
        """PB >= 10 → pb_score=2"""
        r = bq.score_valuation(
            "000001", price=50, financials={"市盈率": 15, "市净率": 12, "营收增长": 5}
        )
        self.assertIn("极高", r["assessment"])

    def test_pb_high_range(self):
        """PB 6-10 → pb_score=5"""
        r = bq.score_valuation(
            "000001", price=50, financials={"市盈率": 20, "市净率": 8, "营收增长": 10}
        )
        self.assertIn("高", r["assessment"])

    def test_level_overvalued(self):
        """总分 20-35 → level='高估'"""
        r = bq.score_valuation(
            "000001", price=50, financials={"市盈率": 45, "市净率": 4, "营收增长": 10}
        )
        self.assertEqual(r["level"], "高估")

    def test_level_bubble(self):
        """总分 < 20 → level='泡沫'"""
        r = bq.score_valuation(
            "000001", price=50, financials={"市盈率": 200, "市净率": 15, "营收增长": 1}
        )
        self.assertEqual(r["level"], "泡沫")

    def test_level_reasonable_high(self):
        """总分 35-50 → '合理偏高'"""
        r = bq.score_valuation(
            "000001", price=50, financials={"市盈率": 25, "市净率": 2.5, "营收增长": 15}
        )
        self.assertEqual(r["level"], "合理偏高")

    def test_level_reasonable_low(self):
        """总分 50-65 → '合理偏低'"""
        r = bq.score_valuation(
            "000001", price=50, financials={"市盈率": 18, "市净率": 2.5, "营收增长": 15}
        )
        self.assertEqual(r["level"], "合理偏低")

    def test_level_undervalued(self):
        """总分 >= 65 → '低估'"""
        r = bq.score_valuation(
            "000001", price=50, financials={"市盈率": 8, "市净率": 0.8, "营收增长": 30}
        )
        self.assertEqual(r["level"], "低估")

    def test_no_revenue_growth_default_peg(self):
        """营收增长<=0 时 PEG 走默认 12 分"""
        r = bq.score_valuation(
            "000001", price=50, financials={"市盈率": 20, "市净率": 2, "营收增长": 0}
        )
        self.assertIsNone(r["peg"])
        self.assertIsInstance(r["score"], int)


# ═══════════════════════════════════════════
# 综合摘要 (扩展：覆盖剩余分支)
# ═══════════════════════════════════════════


class TestGenerateSummaryExtended(unittest.TestCase):
    """_generate_summary — 覆盖 transition 和 growth 非优质分支"""

    def test_growth_weak_moat(self):
        """成长期但护城河不够宽 → 关注护城河和现金流"""
        profile = {"main_business": "软件开发"}
        moat = {"score": 35, "level": "狭窄的护城河"}
        cf = {"quality": "一般"}
        lifecycle = {"stage": "growth", "stage_cn": "成长期"}
        valuation = {"score": 45, "level": "合理偏高"}

        result = bq._generate_summary("000001", "测试", profile, moat, cf, lifecycle, valuation)
        self.assertIn("关注护城河", result)

    def test_growth_poor_cashflow(self):
        """成长期护城河够宽但现金流不佳 → 关注护城河和现金流"""
        profile = {"main_business": ""}
        moat = {"score": 65, "level": "较宽的护城河"}
        cf = {"quality": "预警"}
        lifecycle = {"stage": "growth", "stage_cn": "成长期"}
        valuation = {"score": 50, "level": "合理偏低"}

        result = bq._generate_summary("000001", "测试", profile, moat, cf, lifecycle, valuation)
        self.assertIn("关注护城河", result)

    def test_transition_else_branch(self):
        """transition 阶段 → 走 else 分支品质中等"""
        profile = {"main_business": "传统制造"}
        moat = {"score": 40, "level": "狭窄的护城河"}
        cf = {"quality": "良好"}
        lifecycle = {"stage": "transition", "stage_cn": "转型期"}
        valuation = {"score": 40, "level": "合理偏高"}

        result = bq._generate_summary("000001", "测试", profile, moat, cf, lifecycle, valuation)
        self.assertIn("质地中等", result)

    def test_mature_not_undervalued(self):
        """成熟期但估值不低 → 走 else 分支"""
        profile: dict[str, Any] = {}
        moat = {"score": 50, "level": "狭窄的护城河"}
        cf = {"quality": "良好"}
        lifecycle = {"stage": "mature", "stage_cn": "成熟期"}
        valuation = {"score": 40, "level": "合理偏高"}

        result = bq._generate_summary("000001", "测试", profile, moat, cf, lifecycle, valuation)
        self.assertIn("质地中等", result)

    def test_unknown_stage(self):
        """未知阶段 → 走 else 分支"""
        profile: dict[str, Any] = {}
        moat = {"score": 30, "level": "无明显护城河"}
        cf = {"quality": "一般"}
        lifecycle = {"stage": "unknown", "stage_cn": "无法判断"}
        valuation = {"score": 30, "level": "高估"}

        result = bq._generate_summary("000001", "测试", profile, moat, cf, lifecycle, valuation)
        self.assertIn("质地中等", result)


if __name__ == "__main__":
    unittest.main()
