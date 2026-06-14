"""Tests for screener.py — 每日选股池模块"""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch, PropertyMock

import pandas as pd
import pytest

from stock_analyzer.screener import (
    DEFAULT_POOL,
    filter_by_conditions,
    get_stock_name,
    load_all_a_shares,
    load_stock_pool,
    quick_filter,
    run_screener,
    save_screener_result,
    three_layer_funnel,
)


# ==============================================================================
# Tests: load_all_a_shares
# ==============================================================================

class TestLoadAllAShares:
    def test_cache_hit(self):
        """缓存文件存在且合法时直接返回缓存内容"""
        fake_codes = ["000001", "000002", "600000"]
        with patch("stock_analyzer.screener.os.path.exists", return_value=True):
            with patch("builtins.open") as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(
                    fake_codes
                )
                result = load_all_a_shares()
        assert result == fake_codes

    def test_cache_corrupted_falls_through_to_akshare(self):
        """缓存文件损坏时回退到 akshare"""
        with patch("stock_analyzer.screener.os.path.exists", return_value=True):
            with patch("builtins.open") as mock_open:
                mock_open.return_value.__enter__.return_value.read.side_effect = Exception(
                    "corrupt"
                )
                mock_ak = MagicMock()
                mock_df = MagicMock()
                mock_df.__getitem__.return_value.astype.return_value.str.zfill.return_value.tolist.return_value = [
                    "000001"
                ]
                mock_ak.stock_info_a_code_name.return_value = mock_df
                with patch.dict("sys.modules", {"akshare": mock_ak}):
                    result = load_all_a_shares(force_refresh=False)
        assert result == ["000001"]

    def test_force_refresh_skips_cache(self):
        """force_refresh=True 时跳过缓存直接获取 akshare"""
        mock_ak = MagicMock()
        mock_df = MagicMock()
        mock_df.__getitem__.return_value.astype.return_value.str.zfill.return_value.tolist.return_value = [
            "600519"
        ]
        mock_ak.stock_info_a_code_name.return_value = mock_df
        with patch.dict("sys.modules", {"akshare": mock_ak}):
            with patch("stock_analyzer.screener.os.makedirs"):
                with patch("builtins.open"):
                    result = load_all_a_shares(force_refresh=True)
        assert result == ["600519"]

    def test_akshare_failure_fallback_default_pool(self):
        """akshare 异常时回退到 DEFAULT_POOL"""
        with patch("stock_analyzer.screener.os.path.exists", return_value=False):
            mock_ak = MagicMock()
            mock_ak.stock_info_a_code_name.side_effect = Exception("network error")
            with patch.dict("sys.modules", {"akshare": mock_ak}):
                result = load_all_a_shares()
        assert result == list(DEFAULT_POOL)


# ==============================================================================
# Tests: quick_filter
# ==============================================================================

class TestQuickFilter:
    @patch("stock_analyzer.screener.sina_real_time")
    def test_basic_filter(self, mock_sina):
        """基础过滤：价格范围、排除ST、排除北交所、成交量下限"""
        mock_sina.return_value = {
            "000001": {"名称": "平安银行", "最新价": 15.0, "成交量": 5_000_000},
            "002415": {"名称": "海康威视", "最新价": 40.0, "成交量": 3_000_000},
            "600519": {"名称": "贵州茅台", "最新价": 1800.0, "成交量": 2_000_000},
            "300750": {"名称": "宁德时代", "最新价": 200.0, "成交量": 8_000_000},
            "000999": {"名称": "ST华塑", "最新价": 5.0, "成交量": 1_500_000},
            "888888": {"名称": "北交所票", "最新价": 10.0, "成交量": 2_000_000},
        }
        codes = ["000001", "002415", "600519", "300750", "000999", "888888"]
        result = quick_filter(
            codes, min_price=6, max_price=500, exclude_st=True, exclude_bj=True, min_volume=2_000_000
        )
        # 平安银行15元通过，海康40元通过，茅台1800超过max_price被排除
        # 宁德时代200通过，ST华硕被排除，北交所被排除
        # 茅台1800 > 500 max_price → 不通过
        assert "000001" in result
        assert "002415" in result
        assert "600519" not in result  # 1800 > 500
        assert "300750" in result
        assert "000999" not in result  # ST
        assert "888888" not in result  # 北交所

    @patch("stock_analyzer.screener.sina_real_time")
    def test_empty_rt_data_returns_all(self, mock_sina):
        """实时行情为空时直接返回原始列表"""
        mock_sina.return_value = {}
        codes = ["000001", "000002"]
        result = quick_filter(codes)
        assert result == codes

    @patch("stock_analyzer.screener.sina_real_time")
    def test_missing_price_or_volume(self, mock_sina):
        """缺失最新价或成交量为 None/0 时排除"""
        mock_sina.return_value = {
            "000001": {"名称": "平安银行", "最新价": None, "成交量": 5_000_000},
            "000002": {"名称": "万科A", "最新价": 0, "成交量": 3_000_000},
            "000003": {"名称": "正常股", "最新价": 20.0, "成交量": None},
        }
        codes = ["000001", "000002", "000003"]
        result = quick_filter(codes, min_price=0, max_price=0, min_volume=0)
        assert "000001" not in result  # price is None
        assert "000002" not in result  # price == 0
        assert "000003" in result  # volume is None but min_volume=0

    @patch("stock_analyzer.screener.sina_real_time")
    def test_exclude_st_disabled(self, mock_sina):
        """排除ST关闭时ST股保留"""
        mock_sina.return_value = {
            "000001": {"名称": "ST华塑", "最新价": 5.0, "成交量": 1_000_000},
        }
        codes = ["000001"]
        result = quick_filter(codes, exclude_st=False, min_volume=0, min_price=0, max_price=0)
        assert "000001" in result


# ==============================================================================
# Tests: load_stock_pool
# ==============================================================================

class TestLoadStockPool:
    def test_default_pool(self):
        """无参数时返回 DEFAULT_POOL"""
        result = load_stock_pool()
        assert result == set(DEFAULT_POOL)

    def test_from_json_list(self):
        """从 JSON 文件加载 list"""
        codes = ["000001", "000002"]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(codes, f)
            f.flush()
            result = load_stock_pool(source=f.name)
        os.unlink(f.name)
        assert result == set(codes)

    def test_from_json_dict_with_codes(self):
        """从 JSON 文件加载 dict[codes]"""
        data = {"codes": ["600000", "600001"]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            result = load_stock_pool(source=f.name)
        os.unlink(f.name)
        assert result == {"600000", "600001"}

    def test_from_json_unrecognized_format(self):
        """无法识别的 JSON 格式时使用默认池"""
        data = {"foo": "bar"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            result = load_stock_pool(source=f.name)
        os.unlink(f.name)
        assert result == set(DEFAULT_POOL)

    def test_file_not_found(self):
        """文件不存在时使用默认池"""
        result = load_stock_pool(source="/nonexistent/path.json")
        assert result == set(DEFAULT_POOL)

    @patch("stock_analyzer.screener.load_all_a_shares")
    @patch("stock_analyzer.screener.quick_filter")
    def test_use_all_a_shares(self, mock_qf, mock_load):
        """use_all_a_shares=True 时调用全市场加载+快速过滤"""
        mock_load.return_value = ["000001", "000002", "000003"]
        mock_qf.return_value = ["000001", "000002"]
        result = load_stock_pool(use_all_a_shares=True)
        mock_load.assert_called_once()
        mock_qf.assert_called_once()
        assert result == ["000001", "000002"]

    @patch("stock_analyzer.screener.load_all_a_shares")
    @patch("stock_analyzer.screener.quick_filter")
    def test_use_all_a_shares_with_custom_args(self, mock_qf, mock_load):
        """use_all_a_shares 时传入自定义 quick_filter_args"""
        mock_load.return_value = ["000001"]
        mock_qf.return_value = []
        result = load_stock_pool(
            use_all_a_shares=True, quick_filter_args={"min_price": 10, "exclude_st": False}
        )
        # 默认参数应被自定义参数覆盖
        call_kwargs = mock_qf.call_args[1]
        assert call_kwargs["min_price"] == 10
        assert call_kwargs["exclude_st"] is False
        assert call_kwargs["max_price"] == 500  # 默认保留


# ==============================================================================
# Tests: get_stock_name
# ==============================================================================

class TestGetStockName:
    def test_from_cache(self):
        """优先从 rt_cache 获取名称"""
        rt_cache = {"000001": {"名称": "平安银行"}}
        result = get_stock_name("000001", rt_cache=rt_cache)
        assert result == "平安银行"

    @patch("stock_analyzer.screener.sina_real_time")
    def test_fallback_to_sina(self, mock_sina):
        """缓存不存在时从新浪 API 获取"""
        mock_sina.return_value = {"000001": {"名称": "平安银行"}}
        result = get_stock_name("000001")
        assert result == "平安银行"

    @patch("stock_analyzer.screener.sina_real_time")
    def test_no_name_found(self, mock_sina):
        """代码不存在时返回空字符串"""
        mock_sina.return_value = {}
        result = get_stock_name("999999")
        assert result == ""


# ==============================================================================
# Tests: three_layer_funnel
# ==============================================================================

class TestThreeLayerFunnel:
    def _make_candidate(self, code, price=15, score=70, **kw):
        c = {"code": code, "price": price, "score": score}
        c.update(kw)
        return c

    def test_all_fail_l1(self):
        """所有候选在 L1 硬筛阶段被过滤"""
        candidates = [
            self._make_candidate("000001", price=3, score=70),
            self._make_candidate("000002", price=15, score=40),
        ]
        result = three_layer_funnel(candidates, top_n=5)
        assert result["L1_硬筛通过"] == 0
        assert result["最终推荐"] == []

    def test_l1_passes_l2_without_kline(self):
        """L1通过，但 cached_kline 返回空时使用 fallback 评分"""
        # 预置 combo_strength/resonance 以便通过 L3 过滤（测试焦点在 fallback 评分）
        candidates = [
            self._make_candidate("000001", price=15, score=70, combo_strength=3, resonance=20),
        ]
        with patch("stock_analyzer.cache.cached_kline", return_value=pd.DataFrame()):
            with patch("stock_analyzer.short_term.calc_combo_signals"):
                with patch("stock_analyzer.short_term.calc_multi_timeframe_resonance"):
                    result = three_layer_funnel(candidates, top_n=5)
        assert result["L1_硬筛通过"] == 1
        assert result["L2_多因子排序"] == 1
        # fallback score = score = 70
        assert result["最终推荐"][0].get("funnel_score") == 70

    def test_l2_full_scoring(self):
        """L2 完整评分：combo + resonance + funnel_score 计算"""
        candidates = [self._make_candidate("000001", price=15, score=70)]
        mock_kline = pd.DataFrame({"收盘": [10.0, 11.0]})
        with patch("stock_analyzer.cache.cached_kline", return_value=mock_kline):
            with patch(
                "stock_analyzer.short_term.calc_combo_signals",
                return_value={"信号": "买入", "强度": 3},
            ):
                with patch(
                    "stock_analyzer.short_term.calc_multi_timeframe_resonance",
                    return_value={"共振强度": 20, "状态": "共振"},
                ):
                    result = three_layer_funnel(candidates, top_n=5)
        c = result["最终推荐"][0]
        assert c["combo_signal"] == "买入"
        assert c["combo_strength"] == 3
        assert c["resonance"] == 20
        assert c["resonance_status"] == "共振"
        # funnel_score = 70*0.4 + (3+4)/8*100*0.35 + (20+60)/120*100*0.25
        expected = 70 * 0.4 + (3 + 4) / 8 * 100 * 0.35 + (20 + 60) / 120 * 100 * 0.25
        assert abs(c["funnel_score"] - expected) < 0.001

    def test_l3_filter(self):
        """L3 NL终审：combo_strength >= 2 且 resonance > -20 才通过"""
        candidates = [
            self._make_candidate("000001", price=15, score=70),
            self._make_candidate("000002", price=16, score=68),
            self._make_candidate("000003", price=17, score=65),
        ]
        mock_kline = pd.DataFrame({"收盘": [10.0, 11.0]})

        def mock_combo(kline, code):
            strengths = {"000001": 3, "000002": 1, "000003": 2}
            return {"信号": "买入", "强度": strengths.get(code, 0)}

        def mock_resonance(code):
            vals = {"000001": 20, "000002": 10, "000003": -30}
            return {"共振强度": vals.get(code, 0), "状态": "?"}

        with patch("stock_analyzer.cache.cached_kline", return_value=mock_kline):
            with patch(
                "stock_analyzer.short_term.calc_combo_signals", side_effect=mock_combo
            ):
                with patch(
                    "stock_analyzer.short_term.calc_multi_timeframe_resonance",
                    side_effect=mock_resonance,
                ):
                    result = three_layer_funnel(candidates, top_n=2)
        picks = result["最终推荐"]
        codes = [c["code"] for c in picks]
        assert "000001" in codes  # combo=3 >=2, reso=20 > -20 ✓
        assert "000002" not in codes  # combo=1 < 2 ✗
        assert "000003" not in codes  # combo=2 >=2 但 reso=-30 <= -20 ✗
        assert len(picks) <= 2

    def test_kline_exception_uses_fallback(self):
        """cached_kline 抛异常时使用 fallback score"""
        candidates = [
            self._make_candidate("000001", price=15, score=60, combo_strength=3, resonance=20)
        ]
        with patch("stock_analyzer.cache.cached_kline", side_effect=Exception("boom")):
            with patch("stock_analyzer.short_term.calc_combo_signals"):
                with patch("stock_analyzer.short_term.calc_multi_timeframe_resonance"):
                    result = three_layer_funnel(candidates, top_n=5)
        assert result["最终推荐"][0]["funnel_score"] == 60


# ==============================================================================
# Tests: run_screener (核心—但简单验证)
# ==============================================================================

class TestRunScreener:
    NOW = pd.Timestamp.now()

    @patch("stock_analyzer.screener.cached_weibo_sentiment")
    @patch("stock_analyzer.screener.cached_fundamentals")
    @patch("stock_analyzer.screener.composite_quant_score")
    @patch("stock_analyzer.screener.full_technical_analysis")
    @patch("stock_analyzer.screener.cached_kline")
    @patch("stock_analyzer.screener.sina_real_time")
    def test_screener_basic_flow(
        self,
        mock_sina,
        mock_kline,
        mock_fta,
        mock_quant,
        mock_fund,
        mock_sentiment,
    ):
        """基本流程：一个股票通过全链路返回 DataFrame"""
        # 实时行情
        mock_sina.return_value = {
            "000001": {
                "名称": "平安银行",
                "最新价": 15.0,
                "涨跌幅": 2.5,
            }
        }
        # K 线（至少20行才能通过 kline 检查）
        mock_kline.return_value = pd.DataFrame(
            {"收盘": [14.0] * 22 + [15.0], "涨跌幅": [1.0] * 22 + [2.5]},
            index=pd.date_range(end=self.NOW, periods=23),
        )
        # 技术分析返回同样的数据（已含涨跌幅列）
        kline_after = pd.DataFrame(
            {"收盘": [14.0] * 22 + [15.0], "涨跌幅": [1.0] * 22 + [2.5]},
            index=pd.date_range(end=self.NOW, periods=23),
        )
        mock_fta.return_value = kline_after
        # 基本面
        mock_fund.return_value = {"pe": 10, "pb": 1.5}
        # 综合评分
        mock_quant.return_value = {
            "composite_score": 75,
            "rating": "推荐",
            "factor_scores": {
                "momentum": {"score": 70},
                "technical": {"score": 80},
                "fundamental": {"score": 65},
                "volume": {"score": 60},
                "risk": {"score": 85},
                "sentiment": {"score": 55},
            },
        }
        # 舆情
        mock_sentiment.return_value = None

        df = run_screener(pool=["000001"], top_n=5, use_sentiment=False)

        assert not df.empty
        assert df.iloc[0]["代码"] == "000001"
        assert df.iloc[0]["综合评分"] == 75
        assert df.iloc[0]["评级"] == "推荐"
        assert "序号" in df.columns

    @patch("stock_analyzer.screener.cached_weibo_sentiment")
    @patch("stock_analyzer.screener.cached_fundamentals")
    @patch("stock_analyzer.screener.composite_quant_score")
    @patch("stock_analyzer.screener.full_technical_analysis")
    @patch("stock_analyzer.screener.cached_kline")
    @patch("stock_analyzer.screener.sina_real_time")
    def test_screener_kline_too_short(
        self,
        mock_sina,
        mock_kline,
        mock_fta,
        mock_quant,
        mock_fund,
        mock_sentiment,
    ):
        """K 线数据不足 20 行时跳过该股票"""
        mock_sina.return_value = {
            "000001": {"名称": "平安银行", "最新价": 15.0, "涨跌幅": 0},
        }
        mock_kline.return_value = pd.DataFrame(
            {"收盘": [15.0]},  # 只有 1 行，不足 20
            index=pd.date_range(end=self.NOW, periods=1),
        )
        mock_sentiment.return_value = None
        df = run_screener(pool=["000001"], top_n=5, use_sentiment=False)
        assert df.empty

    @patch("stock_analyzer.screener.cached_weibo_sentiment")
    @patch("stock_analyzer.screener.cached_fundamentals")
    @patch("stock_analyzer.screener.composite_quant_score")
    @patch("stock_analyzer.screener.full_technical_analysis")
    @patch("stock_analyzer.screener.cached_kline")
    @patch("stock_analyzer.screener.sina_real_time")
    def test_screener_st_filter(
        self,
        mock_sina,
        mock_kline,
        mock_fta,
        mock_quant,
        mock_fund,
        mock_sentiment,
    ):
        """ST 股票被过滤"""
        mock_sina.return_value = {
            "000001": {"名称": "ST华塑", "最新价": 5.0, "涨跌幅": -1.0},
        }
        mock_sentiment.return_value = None
        df = run_screener(pool=["000001"], top_n=5, use_sentiment=False)
        assert df.empty

    @patch("stock_analyzer.screener.cached_weibo_sentiment")
    @patch("stock_analyzer.screener.cached_fundamentals")
    @patch("stock_analyzer.screener.composite_quant_score")
    @patch("stock_analyzer.screener.full_technical_analysis")
    @patch("stock_analyzer.screener.cached_kline")
    @patch("stock_analyzer.screener.sina_real_time")
    def test_screener_with_use_sentiment(
        self,
        mock_sina,
        mock_kline,
        mock_fta,
        mock_quant,
        mock_fund,
        mock_sentiment,
    ):
        """use_sentiment=True 时舆情数据应该被获取"""
        mock_sina.return_value = {
            "000001": {"名称": "平安银行", "最新价": 15.0, "涨跌幅": 0},
        }
        mock_kline.return_value = pd.DataFrame(
            {"收盘": [14.0] * 25, "涨跌幅": [1.0] * 25},
            index=pd.date_range(end=self.NOW, periods=25),
        )
        mock_fta.return_value = mock_kline.return_value
        mock_fund.return_value = {"pe": 10}
        mock_quant.return_value = {
            "composite_score": 60,
            "rating": "关注",
            "factor_scores": {
                "momentum": {"score": 50},
                "technical": {"score": 50},
                "fundamental": {"score": 50},
                "volume": {"score": 50},
                "risk": {"score": 50},
                "sentiment": {"score": 50},
            },
        }
        mock_sentiment.return_value = pd.DataFrame({"name": [], "rate": []})
        df = run_screener(pool=["000001"], top_n=5, use_sentiment=True)
        mock_sentiment.assert_called_once()
        assert not df.empty

    @patch("stock_analyzer.screener.cached_weibo_sentiment")
    @patch("stock_analyzer.screener.cached_fundamentals")
    @patch("stock_analyzer.screener.composite_quant_score")
    @patch("stock_analyzer.screener.full_technical_analysis")
    @patch("stock_analyzer.screener.cached_kline")
    @patch("stock_analyzer.screener.sina_real_time")
    def test_screener_mode_full(
        self,
        mock_sina,
        mock_kline,
        mock_fta,
        mock_quant,
        mock_fund,
        mock_sentiment,
    ):
        """mode='full' 时使用全市场加载"""
        mock_sina.return_value = {
            "000001": {"名称": "平安银行", "最新价": 15.0, "涨跌幅": 0},
        }
        mock_kline.return_value = pd.DataFrame(
            {"收盘": [14.0] * 25, "涨跌幅": [1.0] * 25},
            index=pd.date_range(end=self.NOW, periods=25),
        )
        mock_fta.return_value = mock_kline.return_value
        mock_fund.return_value = {"pe": 10}
        mock_quant.return_value = {
            "composite_score": 60,
            "rating": "关注",
            "factor_scores": {
                "momentum": {"score": 50},
                "technical": {"score": 50},
                "fundamental": {"score": 50},
                "volume": {"score": 50},
                "risk": {"score": 50},
                "sentiment": {"score": 50},
            },
        }
        mock_sentiment.return_value = None
        with patch("stock_analyzer.screener.load_stock_pool", return_value=["000001"]):
            df = run_screener(pool=None, mode="full", top_n=5, use_sentiment=False)
        assert not df.empty

    @patch("stock_analyzer.screener.cached_weibo_sentiment")
    @patch("stock_analyzer.screener.cached_fundamentals")
    @patch("stock_analyzer.screener.composite_quant_score")
    @patch("stock_analyzer.screener.full_technical_analysis")
    @patch("stock_analyzer.screener.cached_kline")
    @patch("stock_analyzer.screener.sina_real_time")
    def test_screener_full_string_mode(
        self,
        mock_sina,
        mock_kline,
        mock_fta,
        mock_quant,
        mock_fund,
        mock_sentiment,
    ):
        """pool='all' 字符串触发的全市场扫描"""
        mock_sina.return_value = {
            "000001": {"名称": "平安银行", "最新价": 15.0, "涨跌幅": 0},
        }
        mock_kline.return_value = pd.DataFrame(
            {"收盘": [14.0] * 25, "涨跌幅": [1.0] * 25},
            index=pd.date_range(end=self.NOW, periods=25),
        )
        mock_fta.return_value = mock_kline.return_value
        mock_fund.return_value = {"pe": 10}
        mock_quant.return_value = {
            "composite_score": 60,
            "rating": "关注",
            "factor_scores": {
                "momentum": {"score": 50},
                "technical": {"score": 50},
                "fundamental": {"score": 50},
                "volume": {"score": 50},
                "risk": {"score": 50},
                "sentiment": {"score": 50},
            },
        }
        mock_sentiment.return_value = None
        with patch("stock_analyzer.screener.load_stock_pool", return_value=["000001"]):
            df = run_screener(pool="all", top_n=5, use_sentiment=False)
        assert not df.empty

    @patch("stock_analyzer.screener.cached_weibo_sentiment")
    @patch("stock_analyzer.screener.cached_fundamentals")
    @patch("stock_analyzer.screener.composite_quant_score")
    @patch("stock_analyzer.screener.full_technical_analysis")
    @patch("stock_analyzer.screener.cached_kline")
    @patch("stock_analyzer.screener.sina_real_time")
    def test_screener_price_fallback(
        self,
        mock_sina,
        mock_kline,
        mock_fta,
        mock_quant,
        mock_fund,
        mock_sentiment,
    ):
        """实时行情最新价为 None 时从 K 线最后收盘价获取"""
        mock_sina.return_value = {
            "000001": {"名称": "平安银行", "最新价": None, "涨跌幅": None},
        }
        mock_kline.return_value = pd.DataFrame(
            {"收盘": [14.0] * 25 + [15.5], "涨跌幅": [1.0] * 26},
            index=pd.date_range(end=self.NOW, periods=26),
        )
        mock_fta.return_value = mock_kline.return_value
        mock_fund.return_value = {"pe": 10}
        mock_quant.return_value = {
            "composite_score": 65,
            "rating": "关注",
            "factor_scores": {
                "momentum": {"score": 50},
                "technical": {"score": 50},
                "fundamental": {"score": 50},
                "volume": {"score": 50},
                "risk": {"score": 50},
            },
        }
        mock_sentiment.return_value = None
        df = run_screener(pool=["000001"], top_n=5, use_sentiment=False)
        assert not df.empty
        assert df.iloc[0]["最新价"] == 15.5  # 从 kline 最后收盘价
        # 涨跌幅为 0（因为从 kline 取不到涨跌幅列）
        assert df.iloc[0]["涨跌幅"] == 1.0  # 从 kline 涨跌幅最后值


# ==============================================================================
# Tests: filter_by_conditions
# ==============================================================================

class TestFilterByConditions:
    def test_empty_df(self):
        """空 DataFrame 返回空"""
        df = pd.DataFrame()
        result = filter_by_conditions(df, min_price=5)
        assert result.empty

    def test_filter_by_price_and_score(self):
        """按价格和评分过滤"""
        df = pd.DataFrame({
            "最新价": [10.0, 3.0, 20.0],
            "综合评分": [70, 80, 50],
        })
        result = filter_by_conditions(df, min_price=5, min_score=60)
        assert len(result) == 1
        assert result.iloc[0]["最新价"] == 10.0
        assert result.iloc[0]["综合评分"] == 70

    def test_no_filter_conditions(self):
        """全部条件 <= 0 时返回全部"""
        df = pd.DataFrame({"最新价": [10.0], "综合评分": [70]})
        result = filter_by_conditions(df, min_price=0, min_score=0)
        assert len(result) == 1

    def test_removes_existing_seq_column(self):
        """已有序号列时先移除再插入新序号"""
        df = pd.DataFrame({"序号": [1, 2], "最新价": [10.0, 20.0], "综合评分": [70, 80]})
        result = filter_by_conditions(df, min_price=5, min_score=60)
        assert "序号" in result.columns
        assert result.iloc[0]["序号"] == 1

    def test_price_only_filter(self):
        """仅按价格过滤"""
        df = pd.DataFrame({"最新价": [10.0, 3.0], "综合评分": [70, 80]})
        result = filter_by_conditions(df, min_price=5, min_score=0)
        assert len(result) == 1
        assert result.iloc[0]["最新价"] == 10.0


# ==============================================================================
# Tests: save_screener_result
# ==============================================================================

class TestSaveScreenerResult:
    def test_save_to_specified_path(self):
        """保存到指定路径"""
        df = pd.DataFrame({
            "代码": ["000001"],
            "名称": ["平安银行"],
            "综合评分": [75],
        })
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            saved = save_screener_result(df, path=path)
            assert saved == path
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            assert "生成时间" in data
            assert data["股票数量"] == 1
            assert data["股票列表"][0]["代码"] == "000001"
        finally:
            os.unlink(path)

    def test_save_auto_path(self):
        """不指定路径时自动生成 reports/ 下的路径"""
        df = pd.DataFrame({"代码": ["000001"]})
        with patch("stock_analyzer.screener.os.path.dirname") as mock_dir:
            mock_dir.return_value = "/fake"
            with patch("stock_analyzer.screener.os.makedirs"):
                with patch("builtins.open") as mock_open:
                    saved = save_screener_result(df)
        assert saved is not None
        # 路径应包含日期
        assert "screener_2026" in saved
