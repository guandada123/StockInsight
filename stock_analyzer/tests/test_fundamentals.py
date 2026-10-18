"""fetcher/_fundamentals.py 测试（2026-10-18：覆盖率 33.33% -> 目标 90%+）

覆盖两个抓数函数的全部分支：
- get_fundamentals：指标映射（含"摊薄"/"扣非"排除）、字符串清洗（% 与千分位）、
  非数字跳过、EPS<=0 不算 PE、实时价异常降级、外层异常兜底
- get_national_team_holdings：关键词命中与去重、三种列名探测、无名称列、空数据、
  异常兜底

重试装饰器的等待通过 patch time.sleep 跳过（否则异常路径要等 6s+）。
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from stock_analyzer.fetcher import _fundamentals as fund


def _fin(**cols) -> pd.DataFrame:
    """构造一行基本面 DataFrame（列名即指标名）"""
    return pd.DataFrame([cols])


# ══════════════════════════════════════════
#  get_fundamentals
# ══════════════════════════════════════════


class TestGetFundamentals:
    def test_full_metrics_with_pe_pb(self):
        fin = _fin(
            净资产收益率=15.5,
            营业总收入同比增长=20.1,
            净利润同比增长=18.3,
            销售毛利率=30.2,
            销售净利率=12.8,
            基本每股收益=2.0,
            每股净资产=10.0,
        )
        with (
            patch("akshare.stock_financial_abstract_ths", return_value=fin),
            patch.object(fund, "sina_real_time", return_value={"600036": {"最新价": 42.0}}),
        ):
            r = fund.get_fundamentals("600036")
        assert r["ROE"] == 15.5
        assert r["营收增长"] == 20.1
        assert r["净利润增长"] == 18.3
        assert r["毛利率"] == 30.2
        assert r["净利率"] == 12.8
        assert r["每股收益"] == 2.0
        assert r["每股净资产"] == 10.0
        assert r["市盈率"] == 21.0  # 42 / 2
        assert r["市净率"] == 4.2  # 42 / 10

    def test_diluted_roe_excluded(self):
        """『净资产收益率-摊薄』不得计入 ROE（仅非摊薄列生效）"""
        fin = _fin(**{"净资产收益率": 12.0, "净资产收益率-摊薄": 99.0})
        with (
            patch("akshare.stock_financial_abstract_ths", return_value=fin),
            patch.object(fund, "sina_real_time", return_value={}),
        ):
            r = fund.get_fundamentals("600036")
        assert r["ROE"] == 12.0

    def test_diluted_only_yields_none(self):
        fin = _fin(**{"净资产收益率-摊薄": 99.0})
        with (
            patch("akshare.stock_financial_abstract_ths", return_value=fin),
            patch.object(fund, "sina_real_time", return_value={}),
        ):
            r = fund.get_fundamentals("600036")
        assert r["ROE"] is None

    def test_deducted_profit_growth_excluded(self):
        """『净利润同比增长-扣非』不得计入净利润增长"""
        fin = _fin(**{"净利润同比增长": 8.0, "净利润同比增长-扣非": 88.0})
        with (
            patch("akshare.stock_financial_abstract_ths", return_value=fin),
            patch.object(fund, "sina_real_time", return_value={}),
        ):
            r = fund.get_fundamentals("600036")
        assert r["净利润增长"] == 8.0

    def test_string_values_cleaned(self):
        """百分号与千分位逗号需清洗后转 float"""
        fin = _fin(净资产收益率="15.5%", 基本每股收益="1,234.5")
        with (
            patch("akshare.stock_financial_abstract_ths", return_value=fin),
            patch.object(fund, "sina_real_time", return_value={}),
        ):
            r = fund.get_fundamentals("600036")
        assert r["ROE"] == 15.5
        assert r["每股收益"] == 1234.5

    def test_non_numeric_skipped(self):
        fin = _fin(净资产收益率="—", 销售毛利率=30.0)
        with (
            patch("akshare.stock_financial_abstract_ths", return_value=fin),
            patch.object(fund, "sina_real_time", return_value={}),
        ):
            r = fund.get_fundamentals("600036")
        assert r["ROE"] is None  # "—" 无法转 float，跳过
        assert r["毛利率"] == 30.0

    def test_fin_none_returns_all_none(self):
        with patch("akshare.stock_financial_abstract_ths", return_value=None):
            r = fund.get_fundamentals("600036")
        assert all(v is None for v in r.values())

    def test_fin_empty_returns_all_none(self):
        with patch("akshare.stock_financial_abstract_ths", return_value=pd.DataFrame()):
            r = fund.get_fundamentals("600036")
        assert all(v is None for v in r.values())

    def test_eps_zero_skips_pe(self):
        fin = _fin(基本每股收益=0.0, 每股净资产=10.0)
        with (
            patch("akshare.stock_financial_abstract_ths", return_value=fin),
            patch.object(fund, "sina_real_time") as rt,
        ):
            r = fund.get_fundamentals("600036")
        rt.assert_not_called()
        assert r["市盈率"] is None

    def test_eps_negative_skips_pe(self):
        fin = _fin(基本每股收益=-1.0)
        with (
            patch("akshare.stock_financial_abstract_ths", return_value=fin),
            patch.object(fund, "sina_real_time") as rt,
        ):
            fund.get_fundamentals("600036")
        rt.assert_not_called()

    def test_realtime_exception_degrades_to_none(self):
        """实时价取数失败 → PE/PB 保持 None，不冒泡"""
        fin = _fin(基本每股收益=2.0, 每股净资产=10.0)
        with (
            patch("akshare.stock_financial_abstract_ths", return_value=fin),
            patch.object(fund, "sina_real_time", side_effect=RuntimeError("net down")),
        ):
            r = fund.get_fundamentals("600036")
        assert r["每股收益"] == 2.0
        assert r["市盈率"] is None

    def test_realtime_zero_price_no_pe(self):
        fin = _fin(基本每股收益=2.0)
        with (
            patch("akshare.stock_financial_abstract_ths", return_value=fin),
            patch.object(fund, "sina_real_time", return_value={"600036": {"最新价": 0}}),
        ):
            r = fund.get_fundamentals("600036")
        assert r["市盈率"] is None

    def test_akshare_exception_returns_defaults(self):
        with (
            patch("akshare.stock_financial_abstract_ths", side_effect=RuntimeError("boom")),
            patch("time.sleep"),
        ):
            r = fund.get_fundamentals("600036")
        assert all(v is None for v in r.values())

    def test_outer_exception_logged_and_partial(self):
        """解析阶段抛异常（列值结构异常）→ 外层 except 兜底，返回已算出的部分"""
        bad = MagicMock()
        bad.empty = False
        bad.columns = ["基本每股收益"]
        bad.tail.return_value.__getitem__.side_effect = IndexError("shape mismatch")
        with (
            patch("akshare.stock_financial_abstract_ths", return_value=bad),
            patch.object(fund, "sina_real_time", return_value={}),
        ):
            r = fund.get_fundamentals("600036")
        # 解析失败但函数未抛异常，返回初始 None 结构
        assert r["每股收益"] is None
        assert set(r) == {
            "市盈率",
            "市净率",
            "ROE",
            "营收增长",
            "净利润增长",
            "毛利率",
            "净利率",
            "每股收益",
            "每股净资产",
        }


# ══════════════════════════════════════════
#  get_national_team_holdings
# ══════════════════════════════════════════


class TestNationalTeamHoldings:
    def test_hits_and_dedup(self):
        df = pd.DataFrame(
            {
                "股东名称": [
                    "中国证券金融股份有限公司",
                    "中央汇金资产管理有限责任公司",
                    "中国证券金融股份有限公司",  # 重复 → 去重
                    "某某私募基金",
                    "全国社保基金一零一组合",
                ]
            }
        )
        with patch("akshare.stock_circulate_stock_holder", return_value=df):
            r = fund.get_national_team_holdings("600036")
        assert r["has_national_team"] is True
        assert len(r["holders"]) == 3
        assert r["holders"].count("中国证券金融股份有限公司") == 1

    def test_no_hit(self):
        df = pd.DataFrame({"股东名称": ["张三", "李四基金"]})
        with patch("akshare.stock_circulate_stock_holder", return_value=df):
            r = fund.get_national_team_holdings("600036")
        assert r == {"has_national_team": False, "holders": []}

    @pytest.mark.parametrize("col", ["股东名称", "十大流通股东名称", "名称", "股东"])
    def test_column_detection_variants(self, col):
        df = pd.DataFrame({col: ["中央汇金投资有限责任公司"]})
        with patch("akshare.stock_circulate_stock_holder", return_value=df):
            r = fund.get_national_team_holdings("600036")
        assert r["has_national_team"] is True

    def test_no_name_column(self):
        df = pd.DataFrame({"持股数": [1000], "占比": [1.5]})
        with patch("akshare.stock_circulate_stock_holder", return_value=df):
            r = fund.get_national_team_holdings("600036")
        assert r["has_national_team"] is False

    def test_none_df(self):
        with patch("akshare.stock_circulate_stock_holder", return_value=None):
            r = fund.get_national_team_holdings("600036")
        assert r == {"has_national_team": False, "holders": []}

    def test_empty_df(self):
        with patch("akshare.stock_circulate_stock_holder", return_value=pd.DataFrame()):
            r = fund.get_national_team_holdings("600036")
        assert r["has_national_team"] is False

    def test_exception_returns_empty(self):
        with (
            patch("akshare.stock_circulate_stock_holder", side_effect=RuntimeError("boom")),
            patch("time.sleep"),
        ):
            r = fund.get_national_team_holdings("600036")
        assert r == {"has_national_team": False, "holders": []}

    def test_multiple_keywords_in_one_name(self):
        """单个股东名同时含多个关键词只记一次（break 生效）"""
        df = pd.DataFrame({"股东名称": ["中央汇金全国社保基金组合"]})
        with patch("akshare.stock_circulate_stock_holder", return_value=df):
            r = fund.get_national_team_holdings("600036")
        assert len(r["holders"]) == 1
