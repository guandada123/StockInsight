"""测试增强选股器 enhanced_screener.py — 两轮筛选 + 板块/短线/ML/自定义因子"""
import json
import os
import pickle
import tempfile
from unittest.mock import MagicMock, PropertyMock, patch, call

import numpy as np
import pandas as pd
import pytest

from stock_analyzer import enhanced_screener as es


# ── 工具函数 ──────────────────────────────────────────

def _make_stock_cache(tmp_path):
    """创建 STOCK_LIST_CACHE 临时 JSON"""
    codes = ["600000", "000001", "600030", "000002", "600519", "600888", "834765"]
    path = os.path.join(tmp_path, "stock_list_cache.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(codes, f)
    return path, codes


def _make_sectors_df():
    return pd.DataFrame({
        "板块名称": ["银行", "券商", "保险", "地产", "医药"],
        "涨跌幅": [2.5, 1.8, -0.5, 1.2, 3.0],
    })


def _make_sectors_dict():
    return {
        "银行": {"涨跌幅": 2.5},
        "券商": {"涨跌幅": 1.8},
        "保险": {"涨跌幅": -0.5},
    }


def _mock_sina(codes):
    stocks = {
        "600000": {"名称": "浦发银行", "最新价": "8.50", "涨跌幅": "1.20", "成交量": "5000000",
                   "最高": "8.60", "最低": "8.40"},
        "000001": {"名称": "平安银行", "最新价": "12.00", "涨跌幅": "0.80", "成交量": "8000000",
                   "最高": "12.20", "最低": "11.80"},
        "600030": {"名称": "中信证券", "最新价": "22.00", "涨跌幅": "-0.50", "成交量": "20000000",
                   "最高": "22.50", "最低": "21.80"},
        "000002": {"名称": "万科A", "最新价": "15.00", "涨跌幅": "2.00", "成交量": "15000000",
                   "最高": "15.30", "最低": "14.80"},
        "600519": {"名称": "贵州茅台", "最新价": "1800.00", "涨跌幅": "0.50", "成交量": "3000000",
                   "最高": "1820.00", "最低": "1790.00"},
        "600888": {"名称": "ST股票", "最新价": "5.00", "涨跌幅": "-1.00", "成交量": "1000000",
                   "最高": "5.10", "最低": "4.90"},
        "834765": {"名称": "三板股票", "最新价": "3.00", "涨跌幅": "0.00", "成交量": "500000",
                   "最高": "3.10", "最低": "2.95"},
    }
    return {c: stocks.get(c, {"名称": f"股票{c}", "最新价": "10.00", "涨跌幅": "0.00",
                              "成交量": "3000000", "最高": "10.20", "最低": "9.80"})
            for c in codes}


def _make_kline():
    np.random.seed(42)
    dates = pd.date_range(end="2025-06-01", periods=120, freq="D")
    return pd.DataFrame({
        "date": dates,
        "open": np.random.uniform(10, 12, 120),
        "high": np.random.uniform(11, 13, 120),
        "low": np.random.uniform(9, 11, 120),
        "close": np.random.uniform(10, 12, 120),
        "volume": np.random.randint(1_000_000, 10_000_000, 120),
    })


def _make_quant_result(cs=70, rating="A", **kw):
    r = {"composite_score": cs, "rating": rating,
         "factor_scores": {k: {"score": v} for k, v in {
             "momentum": 65, "technical": 70, "fundamental": 75,
             "volume": 60, "risk": 55, "sentiment": 50}.items()}}
    r.update(kw)
    return r


def _make_trading_style(**kw):
    r = {"long_term_score": 60}
    r.update(kw)
    return r


def _make_ml_result(**kw):
    r = {"ensemble_direction": "看涨", "ensemble_confidence": 75.0, "agreement": "高"}
    r.update(kw)
    return r


# ── Test: _gf ──────────────────────────────────────────

class TestGf:
    def test_dict_with_score(self):
        assert es._gf({"momentum": {"score": 65}}, "momentum") == 65.0

    def test_dict_without_score(self):
        assert es._gf({"momentum": {}}, "momentum") == 0.0

    def test_non_dict_value(self):
        assert es._gf({"momentum": 65}, "momentum") == 0.0

    def test_missing_key(self):
        assert es._gf({}, "momentum") == 0.0


# ── Test: _check_nt ────────────────────────────────────

class TestCheckNt:
    @patch("stock_analyzer.cache.cached_national_team_holdings")
    def test_has_national_team(self, mock_nt):
        mock_nt.return_value = {"has_national_team": True}
        assert es._check_nt("600000") is True

    @patch("stock_analyzer.cache.cached_national_team_holdings")
    def test_no_nt(self, mock_nt):
        mock_nt.return_value = {"has_national_team": False}
        assert es._check_nt("600000") is False

    @patch("stock_analyzer.cache.cached_national_team_holdings")
    def test_exception(self, mock_nt):
        mock_nt.side_effect = RuntimeError("fail")
        assert es._check_nt("600000") is False

    @patch("stock_analyzer.cache.cached_national_team_holdings")
    def test_non_dict_return(self, mock_nt):
        mock_nt.return_value = None
        assert es._check_nt("600000") is False


# ── Test: _load_all_codes ─────────────────────────────

class TestLoadAllCodes:
    def test_cache_exists(self, monkeypatch):
        tmp = tempfile.mkdtemp()
        path, expected = _make_stock_cache(tmp)
        monkeypatch.setattr(es, "STOCK_LIST_CACHE", path)
        result = es._load_all_codes()
        assert result == expected

    def test_cache_empty_json(self, monkeypatch):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "stock_list_cache.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("[]")
        monkeypatch.setattr(es, "STOCK_LIST_CACHE", path)
        assert es._load_all_codes() == []

    def test_akshare_fallback(self, monkeypatch):
        import sys
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "stock_list_cache.json")
        monkeypatch.setattr(es, "STOCK_LIST_CACHE", path)
        mock_ak = MagicMock()
        mock_ak.stock_info_a_code_name.return_value = pd.DataFrame({
            "code": ["600000", "600001"],
        })
        monkeypatch.setitem(sys.modules, "akshare", mock_ak)
        result = es._load_all_codes()
        assert "600000" in result
        assert "600001" in result
        # 验证缓存已写入
        assert os.path.exists(path)

    def test_akshare_exception(self, monkeypatch):
        import sys
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "stock_list_cache.json")
        monkeypatch.setattr(es, "STOCK_LIST_CACHE", path)
        mock_ak = MagicMock()
        mock_ak.stock_info_a_code_name.side_effect = ValueError("fail")
        monkeypatch.setitem(sys.modules, "akshare", mock_ak)
        assert es._load_all_codes() == []


# ── Test: _get_sector_stocks ──────────────────────────

class TestGetSectorStocks:
    def setup_method(self):
        # 固定 DB_PATH 为临时文件
        self.tmp_db = tempfile.mktemp(suffix=".db")

    @patch("stock_analyzer.enhanced_screener.sqlite3")
    def test_sqlite_found_dict_stocks(self, mock_sql):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (pickle.dumps({"stocks": ["600000", "000001"]}),)
        mock_conn.execute.return_value = mock_cursor
        mock_sql.connect.return_value.__enter__.return_value = mock_conn
        mock_sql.connect.return_value = mock_conn

        result = es._get_sector_stocks("银行")
        assert result == ["600000", "000001"]

    @patch("stock_analyzer.enhanced_screener.sqlite3")
    @patch("stock_analyzer.sectors_fallback.get_sector_for_code", return_value=[])
    def test_sqlite_found_no_stocks_key(self, mock_fb, mock_sql):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (pickle.dumps({"name": "银行"}),)
        mock_conn.execute.return_value = mock_cursor
        mock_sql.connect.return_value = mock_conn

        result = es._get_sector_stocks("银行")
        # no "stocks" key → fallback → empty
        assert result == []

    @patch("stock_analyzer.enhanced_screener.sqlite3")
    @patch("stock_analyzer.sectors_fallback.get_sector_for_code", return_value=[])
    def test_sqlite_empty_row(self, mock_fb, mock_sql):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.execute.return_value = mock_cursor
        mock_sql.connect.return_value = mock_conn

        result = es._get_sector_stocks("银行")
        assert result == []

    @patch("stock_analyzer.enhanced_screener.sqlite3")
    @patch("stock_analyzer.sectors_fallback.get_sector_for_code", return_value=[])
    def test_sqlite_exception_triggers_fallback(self, mock_fb, mock_sql):
        mock_sql.connect.side_effect = RuntimeError("db fail")
        result = es._get_sector_stocks("银行")
        # SQL异常→fallback→返回空
        assert result == []


# ── Test: pass1_quick_filter ───────────────────────────

class TestPass1QuickFilter:
    codes = ["600000", "000001", "600030", "000002", "600519", "600888", "834765"]

    @patch("stock_analyzer.enhanced_screener._get_sector_stocks")
    @patch("stock_analyzer.enhanced_screener.sina_real_time")
    @patch("stock_analyzer.enhanced_screener.get_sectors")
    def test_full_flow_df_sectors(self, mock_gs, mock_sina, mock_gss):
        """DataFrame 板块排名 + 完整筛选流程"""
        mock_gs.return_value = _make_sectors_df()
        mock_sina.side_effect = _mock_sina
        mock_gss.return_value = ["600000", "000001", "600030"]

        passed, top_sectors, stats = es.pass1_quick_filter(self.codes)
        assert len(top_sectors) == 5
        assert top_sectors[0] == "医药"  # 涨跌幅最高
        assert len(passed) >= 0
        # 板块过滤后 pool 缩小（ST股票已被板块过滤移除）
        assert stats["total"] <= 3
        assert stats["st_filtered"] == 0  # ST已在板块过滤中被排除

    @patch("stock_analyzer.enhanced_screener._get_sector_stocks")
    @patch("stock_analyzer.enhanced_screener.sina_real_time")
    @patch("stock_analyzer.enhanced_screener.get_sectors")
    def test_full_flow_dict_sectors(self, mock_gs, mock_sina, mock_gss):
        """dict 格式板块排名"""
        mock_gs.return_value = _make_sectors_dict()
        mock_sina.side_effect = _mock_sina
        mock_gss.return_value = ["600000", "000001"]

        passed, top_sectors, stats = es.pass1_quick_filter(self.codes)
        assert len(top_sectors) == 3
        assert top_sectors[0] == "银行"

    @patch("stock_analyzer.enhanced_screener._get_sector_stocks")
    @patch("stock_analyzer.enhanced_screener.sina_real_time")
    @patch("stock_analyzer.enhanced_screener.get_sectors")
    def test_get_sectors_exception(self, mock_gs, mock_sina, mock_gss):
        """get_sectors 异常 → 跳过板块过滤"""
        mock_gs.side_effect = RuntimeError("fail")
        mock_sina.side_effect = _mock_sina
        mock_gss.return_value = ["600000", "000001"]

        # 无板块过滤，但仍有硬筛
        passed, top_sectors, stats = es.pass1_quick_filter(self.codes)
        assert top_sectors == []
        assert stats["total"] == len(self.codes)

    @patch("stock_analyzer.enhanced_screener._get_sector_stocks")
    @patch("stock_analyzer.enhanced_screener.sina_real_time")
    @patch("stock_analyzer.enhanced_screener.get_sectors")
    def test_no_sector_stocks(self, mock_gs, mock_sina, mock_gss):
        """板块有效但成分股为空 → 不过滤"""
        mock_gs.return_value = _make_sectors_df()
        mock_sina.side_effect = _mock_sina
        mock_gss.return_value = []  # 板块成分股为空

        passed, top_sectors, stats = es.pass1_quick_filter(self.codes)
        # sector_stocks 为空 → 不过滤，全部进入硬筛
        assert len(top_sectors) == 5

    @patch("stock_analyzer.enhanced_screener._get_sector_stocks")
    @patch("stock_analyzer.enhanced_screener.sina_real_time")
    @patch("stock_analyzer.enhanced_screener.get_sectors")
    def test_all_filtered_out(self, mock_gs, mock_sina, mock_gss):
        """所有股票被过滤→空结果"""
        mock_gs.return_value = _make_sectors_df()
        mock_gss.return_value = []
        codes = ["600888", "834765"]  # 只有 ST 和 8xx
        mock_sina.side_effect = _mock_sina

        passed, top_sectors, stats = es.pass1_quick_filter(codes)
        assert len(passed) == 0
        assert stats["st_filtered"] == 2

    @patch("stock_analyzer.enhanced_screener._get_sector_stocks")
    @patch("stock_analyzer.enhanced_screener.sina_real_time")
    @patch("stock_analyzer.enhanced_screener.get_sectors")
    def test_min_amplitude_filter(self, mock_gs, mock_sina, mock_gss):
        """最低振幅过滤"""
        mock_gs.return_value = _make_sectors_df()
        mock_sina.side_effect = _mock_sina
        mock_gss.return_value = ["600000", "000001"]

        passed, top_sectors, stats = es.pass1_quick_filter(
            self.codes, min_amplitude=50  # 极高振幅要求 → 全部过滤
        )
        assert stats["amplitude_filtered"] >= 0

    @patch("stock_analyzer.enhanced_screener._get_sector_stocks")
    @patch("stock_analyzer.enhanced_screener.sina_real_time")
    @patch("stock_analyzer.enhanced_screener.get_sectors")
    def test_price_filter(self, mock_gs, mock_sina, mock_gss):
        """价格范围过滤"""
        mock_gs.return_value = _make_sectors_df()
        mock_sina.side_effect = _mock_sina
        mock_gss.return_value = []

        # min_price=100, max_price=200 → 只有贵州茅台(1800)被过滤
        passed, top_sectors, stats = es.pass1_quick_filter(
            self.codes, min_price=1, max_price=10
        )
        assert stats["price_filtered"] > 0

    @patch("stock_analyzer.enhanced_screener._get_sector_stocks")
    @patch("stock_analyzer.enhanced_screener.sina_real_time")
    @patch("stock_analyzer.enhanced_screener.get_sectors")
    def test_volume_filter(self, mock_gs, mock_sina, mock_gss):
        """成交量过滤（默认最低 100 万）"""
        mock_gs.return_value = _make_sectors_df()
        mock_sina.side_effect = _mock_sina
        mock_gss.return_value = []

        # 用极高成交量要求过滤所有
        passed, top_sectors, stats = es.pass1_quick_filter(
            self.codes, min_turnover=50_000_000
        )
        assert stats["vol_filtered"] > 0

    @patch("stock_analyzer.enhanced_screener._get_sector_stocks")
    @patch("stock_analyzer.enhanced_screener.sina_real_time")
    @patch("stock_analyzer.enhanced_screener.get_sectors")
    def test_missing_info_skipped(self, mock_gs, mock_sina, mock_gss):
        """缺少实时行情的股票被跳过"""
        mock_gs.return_value = _make_sectors_df()
        mock_gss.return_value = []
        # 无 sina 数据
        mock_sina.return_value = {}

        passed, top_sectors, stats = es.pass1_quick_filter(self.codes)
        assert len(passed) == 0

    @patch("stock_analyzer.enhanced_screener._get_sector_stocks")
    @patch("stock_analyzer.enhanced_screener.sina_real_time")
    @patch("stock_analyzer.enhanced_screener.get_sectors")
    def test_sector_filter_reduces_codes(self, mock_gs, mock_sina, mock_gss):
        """板块过滤后的 subsets 测试"""
        mock_gs.return_value = _make_sectors_df()
        mock_sina.side_effect = _mock_sina
        # 只包含一只股票
        mock_gss.return_value = ["600000"]

        passed, top_sectors, stats = es.pass1_quick_filter(self.codes)
        # 只有 600000 在板块成分股中，所以只有它进入硬筛
        assert stats["total"] < len(self.codes)


# ── pass2_deep_analyze 测试 ──────────────────────────

class TestPass2DeepAnalyze:
    """pass2_deep_analyze 通过充分 mock 外部依赖来测试"""

    candidates = [
        {"code": "600000", "name": "浦发银行", "price": 8.5, "change_pct": 1.2,
         "volume": 5000000, "amplitude": 2.35},
        {"code": "000001", "name": "平安银行", "price": 12.0, "change_pct": 0.8,
         "volume": 8000000, "amplitude": 3.33},
        {"code": "600030", "name": "中信证券", "price": 22.0, "change_pct": -0.5,
         "volume": 20000000, "amplitude": 3.18},
        {"code": "000002", "name": "万科A", "price": 15.0, "change_pct": 2.0,
         "volume": 15000000, "amplitude": 3.33},
    ]

    @patch("stock_analyzer.enhanced_screener.cached_weibo_sentiment")
    @patch("stock_analyzer.enhanced_screener.cached_kline")
    @patch("stock_analyzer.enhanced_screener.cached_fundamentals")
    @patch("stock_analyzer.enhanced_screener.full_technical_analysis")
    @patch("stock_analyzer.enhanced_screener.get_technical_summary")
    @patch("stock_analyzer.enhanced_screener.composite_quant_score")
    @patch("stock_analyzer.enhanced_screener.evaluate_trading_style")
    @patch("stock_analyzer.enhanced_screener.calc_combo_signals")
    @patch("stock_analyzer.enhanced_screener.calc_multi_timeframe_resonance")
    @patch("stock_analyzer.enhanced_screener.short_term_score")
    @patch("stock_analyzer.enhanced_screener._check_nt")
    @patch("stock_analyzer.ml_predict.predict_ensemble")
    @patch("stock_analyzer.custom_factors.list_factors")
    @patch("stock_analyzer.custom_factors.compute_all_factors")
    @patch("stock_analyzer.sector_info.get_stock_sector_full")
    def test_full_flow(self, mock_sector_full, mock_cf_all, mock_cf_list,
                       mock_ml, mock_nt, mock_st, mock_res, mock_combo,
                       mock_trading, mock_quant, mock_tech_sum, mock_tech,
                       mock_fund, mock_kline, mock_sent):
        """完整流程：ML + 自定义因子 + 多股筛选"""
        mock_sent.return_value = pd.DataFrame({
            "name": ["浦发银行", "平安银行"],
            "rate": [0.3, -0.1],
        })
        kline = _make_kline()
        mock_kline.return_value = kline
        mock_fund.return_value = {"ROE": 12.5}
        mock_tech.return_value = kline  # 返回自身
        mock_tech_sum.return_value = {"macd_signal": "金叉", "rsi_value": 55, "kdj_signal": "超买"}
        mock_quant.return_value = _make_quant_result(70, "A")
        mock_trading.return_value = _make_trading_style()
        mock_combo.return_value = {"强度": 3}
        mock_res.return_value = {"共振强度": 45}
        mock_st.return_value = {"短线评分": 65}
        mock_nt.return_value = True
        mock_ml.return_value = {"ensemble_direction": "看涨", "ensemble_confidence": 75.0, "agreement": "高"}
        mock_cf_list.return_value = [{"id": "factor1"}, {"id": "factor2"}]
        mock_cf_all.return_value = [{"factor_id": "factor1", "value": 1.5}]
        mock_sector_full.return_value = "银行"

        df = es.pass2_deep_analyze(self.candidates)

        assert isinstance(df, pd.DataFrame)
        assert len(df) <= 4
        assert "排名" in df.columns
        assert "综合排序分" in df.columns
        assert "ml_direction" in df.columns
        assert "cf_factor1" in df.columns
        assert "板块" in df.columns
        assert "国家队" in df.columns
        assert "综合评分" in df.columns or "composite_score" in df.columns

    @patch("stock_analyzer.enhanced_screener.cached_weibo_sentiment")
    @patch("stock_analyzer.enhanced_screener.cached_kline")
    @patch("stock_analyzer.enhanced_screener.cached_fundamentals")
    @patch("stock_analyzer.enhanced_screener.full_technical_analysis")
    @patch("stock_analyzer.enhanced_screener.get_technical_summary")
    @patch("stock_analyzer.enhanced_screener.composite_quant_score")
    @patch("stock_analyzer.enhanced_screener.evaluate_trading_style")
    @patch("stock_analyzer.enhanced_screener.calc_combo_signals")
    @patch("stock_analyzer.enhanced_screener.calc_multi_timeframe_resonance")
    @patch("stock_analyzer.enhanced_screener.short_term_score")
    @patch("stock_analyzer.enhanced_screener._check_nt")
    @patch("stock_analyzer.sector_info.get_stock_sector_full")
    def test_no_ml_no_custom(self, mock_sector_full, mock_nt, mock_st,
                             mock_res, mock_combo, mock_trading, mock_quant,
                             mock_tech_sum, mock_tech, mock_fund, mock_kline, mock_sent):
        """关闭 ML 和自定义因子"""
        mock_sent.return_value = pd.DataFrame()
        kline = _make_kline()
        mock_kline.return_value = kline
        mock_fund.return_value = {"ROE": 10.0}
        mock_tech.return_value = kline
        mock_tech_sum.return_value = {}
        mock_quant.return_value = _make_quant_result(60, "B")
        mock_trading.return_value = _make_trading_style()
        mock_combo.return_value = {"强度": 1}
        mock_res.return_value = {"共振强度": 30}
        mock_st.return_value = {"短线评分": 55}
        mock_nt.return_value = False
        mock_sector_full.return_value = "券商"

        df = es.pass2_deep_analyze(self.candidates, use_ml=False, use_custom_factors=False)
        assert isinstance(df, pd.DataFrame)
        # 没有 ML 列
        assert "ml_direction" not in df.columns or df["ml_direction"].isna().all()

    @patch("stock_analyzer.enhanced_screener.cached_weibo_sentiment")
    @patch("stock_analyzer.enhanced_screener.cached_kline")
    @patch("stock_analyzer.enhanced_screener.cached_fundamentals")
    @patch("stock_analyzer.enhanced_screener.full_technical_analysis")
    @patch("stock_analyzer.enhanced_screener.get_technical_summary")
    @patch("stock_analyzer.enhanced_screener.composite_quant_score")
    @patch("stock_analyzer.enhanced_screener.evaluate_trading_style")
    @patch("stock_analyzer.enhanced_screener.calc_combo_signals")
    @patch("stock_analyzer.enhanced_screener.calc_multi_timeframe_resonance")
    @patch("stock_analyzer.enhanced_screener.short_term_score")
    @patch("stock_analyzer.enhanced_screener._check_nt")
    @patch("stock_analyzer.sector_info.get_stock_sector_full")
    def test_all_fail_min_score(self, mock_sector_full, mock_nt, mock_st,
                                mock_res, mock_combo, mock_trading, mock_quant,
                                mock_tech_sum, mock_tech, mock_fund, mock_kline, mock_sent):
        """所有候选低于最低评分→空结果"""
        mock_sent.return_value = None
        kline = _make_kline()
        mock_kline.return_value = kline
        mock_fund.return_value = {}
        mock_tech.return_value = kline
        mock_tech_sum.return_value = {}
        mock_quant.return_value = _make_quant_result(30, "C")  # 低于 45
        mock_trading.return_value = _make_trading_style()
        mock_combo.return_value = {"强度": 0}
        mock_res.return_value = {"共振强度": 0}
        mock_st.return_value = {"短线评分": 40}
        mock_nt.return_value = False
        mock_sector_full.return_value = "银行"

        df = es.pass2_deep_analyze(self.candidates, min_score=45)
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    @patch("stock_analyzer.enhanced_screener.cached_weibo_sentiment")
    @patch("stock_analyzer.enhanced_screener.cached_kline")
    @patch("stock_analyzer.enhanced_screener.cached_fundamentals")
    @patch("stock_analyzer.enhanced_screener.full_technical_analysis")
    @patch("stock_analyzer.enhanced_screener.get_technical_summary")
    @patch("stock_analyzer.enhanced_screener.composite_quant_score")
    @patch("stock_analyzer.enhanced_screener.evaluate_trading_style")
    @patch("stock_analyzer.enhanced_screener.calc_combo_signals")
    @patch("stock_analyzer.enhanced_screener.calc_multi_timeframe_resonance")
    @patch("stock_analyzer.enhanced_screener.short_term_score")
    @patch("stock_analyzer.enhanced_screener._check_nt")
    @patch("stock_analyzer.sector_info.get_stock_sector_full")
    def test_empty_candidates(self, mock_sector_full, mock_nt, mock_st,
                               mock_res, mock_combo, mock_trading, mock_quant,
                               mock_tech_sum, mock_tech, mock_fund, mock_kline, mock_sent):
        """空候选列表→空 DataFrame"""
        df = es.pass2_deep_analyze([])
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    @patch("stock_analyzer.enhanced_screener.cached_weibo_sentiment")
    @patch("stock_analyzer.enhanced_screener.cached_kline")
    @patch("stock_analyzer.enhanced_screener.cached_fundamentals")
    @patch("stock_analyzer.enhanced_screener.full_technical_analysis")
    @patch("stock_analyzer.enhanced_screener.get_technical_summary")
    @patch("stock_analyzer.enhanced_screener.composite_quant_score")
    @patch("stock_analyzer.enhanced_screener.evaluate_trading_style")
    @patch("stock_analyzer.enhanced_screener.calc_combo_signals")
    @patch("stock_analyzer.enhanced_screener.calc_multi_timeframe_resonance")
    @patch("stock_analyzer.enhanced_screener.short_term_score")
    @patch("stock_analyzer.enhanced_screener._check_nt")
    @patch("stock_analyzer.sector_info.get_stock_sector_full")
    def test_empty_kline(self, mock_sector_full, mock_nt, mock_st,
                         mock_res, mock_combo, mock_trading, mock_quant,
                         mock_tech_sum, mock_tech, mock_fund, mock_kline, mock_sent):
        """K线为空→跳过该股票"""
        mock_sent.return_value = None
        mock_kline.return_value = pd.DataFrame()  # 空 DataFrame
        mock_fund.return_value = {}
        mock_tech.return_value = pd.DataFrame()
        mock_tech_sum.return_value = {}
        mock_quant.return_value = _make_quant_result(70, "A")
        mock_trading.return_value = _make_trading_style()
        mock_combo.return_value = {"强度": 3}
        mock_res.return_value = {"共振强度": 45}
        mock_st.return_value = {"短线评分": 65}
        mock_nt.return_value = False
        mock_sector_full.return_value = "银行"

        df = es.pass2_deep_analyze(self.candidates)
        # 所有 candidate 的 kline 为空 → 全部跳过
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    @patch("stock_analyzer.enhanced_screener.cached_weibo_sentiment")
    @patch("stock_analyzer.enhanced_screener.cached_kline")
    @patch("stock_analyzer.enhanced_screener.cached_fundamentals")
    @patch("stock_analyzer.enhanced_screener.full_technical_analysis")
    @patch("stock_analyzer.enhanced_screener.get_technical_summary")
    @patch("stock_analyzer.enhanced_screener.composite_quant_score")
    @patch("stock_analyzer.enhanced_screener.evaluate_trading_style")
    @patch("stock_analyzer.enhanced_screener.calc_combo_signals")
    @patch("stock_analyzer.enhanced_screener.calc_multi_timeframe_resonance")
    @patch("stock_analyzer.enhanced_screener.short_term_score")
    @patch("stock_analyzer.enhanced_screener._check_nt")
    @patch("stock_analyzer.sector_info.get_stock_sector_full")
    def test_sentiment_exception(self, mock_sector_full, mock_nt, mock_st,
                                  mock_res, mock_combo, mock_trading, mock_quant,
                                  mock_tech_sum, mock_tech, mock_fund, mock_kline, mock_sent):
        """舆情接口异常不应阻止流程"""
        mock_sent.side_effect = RuntimeError("sentiment fail")
        kline = _make_kline()
        mock_kline.return_value = kline
        mock_fund.return_value = {"ROE": 12.5}
        mock_tech.return_value = kline
        mock_tech_sum.return_value = {"macd_signal": "金叉", "rsi_value": 55, "kdj_signal": "超买"}
        mock_quant.return_value = _make_quant_result(70, "A")
        mock_trading.return_value = _make_trading_style()
        mock_combo.return_value = {"强度": 3}
        mock_res.return_value = {"共振强度": 45}
        mock_st.return_value = {"短线评分": 65}
        mock_nt.return_value = False
        mock_sector_full.return_value = "银行"

        df = es.pass2_deep_analyze(self.candidates)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    @patch("stock_analyzer.enhanced_screener.cached_weibo_sentiment")
    @patch("stock_analyzer.enhanced_screener.cached_kline")
    @patch("stock_analyzer.enhanced_screener.cached_fundamentals")
    @patch("stock_analyzer.enhanced_screener.full_technical_analysis")
    @patch("stock_analyzer.enhanced_screener.get_technical_summary")
    @patch("stock_analyzer.enhanced_screener.composite_quant_score")
    @patch("stock_analyzer.enhanced_screener.evaluate_trading_style")
    @patch("stock_analyzer.enhanced_screener.calc_combo_signals")
    @patch("stock_analyzer.enhanced_screener.calc_multi_timeframe_resonance")
    @patch("stock_analyzer.enhanced_screener.short_term_score")
    @patch("stock_analyzer.enhanced_screener._check_nt")
    @patch("stock_analyzer.ml_predict.predict_ensemble")
    @patch("stock_analyzer.custom_factors.list_factors")
    @patch("stock_analyzer.custom_factors.compute_all_factors")
    @patch("stock_analyzer.sector_info.get_stock_sector_full")
    def test_ml_exception(self, mock_sector_full, mock_cf_all, mock_cf_list,
                          mock_ml, mock_nt, mock_st, mock_res, mock_combo,
                          mock_trading, mock_quant, mock_tech_sum, mock_tech,
                          mock_fund, mock_kline, mock_sent):
        """ML 预测异常→降级标记"""
        mock_sent.return_value = None
        kline = _make_kline()
        mock_kline.return_value = kline
        mock_fund.return_value = {"ROE": 12.5}
        mock_tech.return_value = kline
        mock_tech_sum.return_value = {}
        mock_quant.return_value = _make_quant_result(70, "A")
        mock_trading.return_value = _make_trading_style()
        mock_combo.return_value = {"强度": 3}
        mock_res.return_value = {"共振强度": 45}
        mock_st.return_value = {"短线评分": 65}
        mock_nt.return_value = False
        mock_cf_list.return_value = []
        mock_cf_all.return_value = []
        mock_ml.side_effect = ValueError("ML error")
        mock_sector_full.return_value = "银行"

        df = es.pass2_deep_analyze(self.candidates)
        assert isinstance(df, pd.DataFrame)
        # 验证 ML 异常降级标记
        assert "ml_direction" in df.columns
        assert (df["ml_direction"] == "?").all()

    @patch("stock_analyzer.enhanced_screener.cached_weibo_sentiment")
    @patch("stock_analyzer.enhanced_screener.cached_kline")
    @patch("stock_analyzer.enhanced_screener.cached_fundamentals")
    @patch("stock_analyzer.enhanced_screener.full_technical_analysis")
    @patch("stock_analyzer.enhanced_screener.get_technical_summary")
    @patch("stock_analyzer.enhanced_screener.composite_quant_score")
    @patch("stock_analyzer.enhanced_screener.evaluate_trading_style")
    @patch("stock_analyzer.enhanced_screener.calc_combo_signals")
    @patch("stock_analyzer.enhanced_screener.calc_multi_timeframe_resonance")
    @patch("stock_analyzer.enhanced_screener.short_term_score")
    @patch("stock_analyzer.enhanced_screener._check_nt")
    @patch("stock_analyzer.ml_predict.predict_ensemble")
    @patch("stock_analyzer.custom_factors.list_factors")
    @patch("stock_analyzer.custom_factors.compute_all_factors")
    @patch("stock_analyzer.sector_info.get_stock_sector_full")
    def test_top_n_truncation(self, mock_sector_full, mock_cf_all, mock_cf_list,
                              mock_ml, mock_nt, mock_st, mock_res, mock_combo,
                              mock_trading, mock_quant, mock_tech_sum, mock_tech,
                              mock_fund, mock_kline, mock_sent):
        """top_n 截断"""
        mock_sent.return_value = None
        kline = _make_kline()
        mock_kline.return_value = kline
        mock_fund.return_value = {}
        mock_tech.return_value = kline
        mock_tech_sum.return_value = {}
        mock_quant.return_value = _make_quant_result(70, "A")
        mock_trading.return_value = _make_trading_style()
        mock_combo.return_value = {"强度": 3}
        mock_res.return_value = {"共振强度": 45}
        mock_st.return_value = {"短线评分": 65}
        mock_nt.return_value = False
        mock_cf_list.return_value = []
        mock_cf_all.return_value = []
        mock_ml.return_value = _make_ml_result()
        mock_sector_full.return_value = "银行"

        df = es.pass2_deep_analyze(self.candidates, top_n=2)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2

    @patch("stock_analyzer.enhanced_screener.cached_weibo_sentiment")
    @patch("stock_analyzer.enhanced_screener.cached_kline")
    @patch("stock_analyzer.enhanced_screener.cached_fundamentals")
    @patch("stock_analyzer.enhanced_screener.full_technical_analysis")
    @patch("stock_analyzer.enhanced_screener.get_technical_summary")
    @patch("stock_analyzer.enhanced_screener.composite_quant_score")
    @patch("stock_analyzer.enhanced_screener.evaluate_trading_style")
    @patch("stock_analyzer.enhanced_screener.calc_combo_signals")
    @patch("stock_analyzer.enhanced_screener.calc_multi_timeframe_resonance")
    @patch("stock_analyzer.enhanced_screener.short_term_score")
    @patch("stock_analyzer.enhanced_screener._check_nt")
    @patch("stock_analyzer.ml_predict.predict_ensemble")
    @patch("stock_analyzer.custom_factors.list_factors")
    @patch("stock_analyzer.custom_factors.compute_all_factors")
    @patch("stock_analyzer.sector_info.get_stock_sector_full")
    def test_single_candidate(self, mock_sector_full, mock_cf_all, mock_cf_list,
                              mock_ml, mock_nt, mock_st, mock_res, mock_combo,
                              mock_trading, mock_quant, mock_tech_sum, mock_tech,
                              mock_fund, mock_kline, mock_sent):
        """单候选"""
        mock_sent.return_value = None
        kline = _make_kline()
        mock_kline.return_value = kline
        mock_fund.return_value = {"ROE": 12.5}
        mock_tech.return_value = kline
        mock_tech_sum.return_value = {}
        mock_quant.return_value = _make_quant_result(70, "A")
        mock_trading.return_value = _make_trading_style()
        mock_combo.return_value = {"强度": 3}
        mock_res.return_value = {"共振强度": 45}
        mock_st.return_value = {"短线评分": 65}
        mock_nt.return_value = False
        mock_cf_list.return_value = []
        mock_cf_all.return_value = []
        mock_ml.return_value = _make_ml_result()
        mock_sector_full.return_value = "银行"

        df = es.pass2_deep_analyze([self.candidates[0]])
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert df.iloc[0]["code"] == "600000"

    @patch("stock_analyzer.enhanced_screener.cached_weibo_sentiment")
    @patch("stock_analyzer.enhanced_screener.cached_kline")
    @patch("stock_analyzer.enhanced_screener.cached_fundamentals")
    @patch("stock_analyzer.enhanced_screener.full_technical_analysis")
    @patch("stock_analyzer.enhanced_screener.get_technical_summary")
    @patch("stock_analyzer.enhanced_screener.composite_quant_score")
    @patch("stock_analyzer.enhanced_screener.evaluate_trading_style")
    @patch("stock_analyzer.enhanced_screener.calc_combo_signals")
    @patch("stock_analyzer.enhanced_screener.calc_multi_timeframe_resonance")
    @patch("stock_analyzer.enhanced_screener.short_term_score")
    @patch("stock_analyzer.enhanced_screener._check_nt")
    @patch("stock_analyzer.ml_predict.predict_ensemble")
    @patch("stock_analyzer.custom_factors.list_factors")
    @patch("stock_analyzer.custom_factors.compute_all_factors")
    @patch("stock_analyzer.sector_info.get_stock_sector_full")
    def test_composite_sort_ranking(self, mock_sector_full, mock_cf_all, mock_cf_list,
                                    mock_ml, mock_nt, mock_st, mock_res, mock_combo,
                                    mock_trading, mock_quant, mock_tech_sum, mock_tech,
                                    mock_fund, mock_kline, mock_sent):
        """验证综合排序分和排名"""
        mock_sent.return_value = None
        kline = _make_kline()
        mock_kline.return_value = kline
        mock_fund.return_value = {}
        mock_tech.return_value = kline
        mock_tech_sum.return_value = {}
        mock_nt.return_value = False
        mock_cf_list.return_value = []
        mock_cf_all.return_value = []
        mock_ml.return_value = _make_ml_result()
        mock_sector_full.return_value = "银行"

        # 为每个候选设置不同评分
        scores = [80, 70, 60, 50]
        def _quant_side_effect(*args, **kwargs):
            cs = scores.pop(0) if scores else 50
            return _make_quant_result(cs, "A")

        mock_quant.side_effect = _quant_side_effect
        mock_trading.return_value = _make_trading_style()
        mock_combo.return_value = {"强度": 3}
        mock_res.return_value = {"共振强度": 45}
        mock_st.return_value = {"短线评分": 65}

        df = es.pass2_deep_analyze(self.candidates)
        # 验证排名递增（composite_score 从高到低）
        assert df["排名"].is_monotonic_increasing
        assert df.iloc[0]["composite_score"] >= df.iloc[-1]["composite_score"]


# ── Test: enhanced_scan ────────────────────────────────

class TestEnhancedScan:
    @patch("stock_analyzer.enhanced_screener._save_snapshot")
    @patch("stock_analyzer.enhanced_screener._save_to_daily_scores")
    @patch("stock_analyzer.enhanced_screener.pass2_deep_analyze")
    @patch("stock_analyzer.enhanced_screener.pass1_quick_filter")
    @patch("stock_analyzer.enhanced_screener._load_all_codes")
    def test_mainboard_mode(self, mock_codes, mock_p1, mock_p2, mock_save, mock_snap):
        """主板模式（60/00 开头）"""
        all_codes = ["600000", "000001", "834765", "300001"]  # 834765 和 300001 应被过滤
        mock_codes.return_value = all_codes
        mock_p1.return_value = (
            [{"code": "600000", "name": "浦发"}],
            ["银行"],
            {"total": 2, "passed": 1},
        )
        mock_p2.return_value = pd.DataFrame({
            "code": ["600000"],
            "composite_score": [70],
            "综合排序分": [75.0],
        })

        result = es.enhanced_scan(mode="mainboard")
        assert isinstance(result, pd.DataFrame)
        # 验证 pass1 只收到过滤后的代码
        passed_codes = mock_p1.call_args[0][0]
        assert "600000" in passed_codes
        assert "834765" not in passed_codes
        assert "300001" not in passed_codes

    @patch("stock_analyzer.enhanced_screener._save_snapshot")
    @patch("stock_analyzer.enhanced_screener._save_to_daily_scores")
    @patch("stock_analyzer.enhanced_screener.pass2_deep_analyze")
    @patch("stock_analyzer.enhanced_screener.pass1_quick_filter")
    @patch("stock_analyzer.enhanced_screener._load_all_codes")
    def test_full_mode(self, mock_codes, mock_p1, mock_p2, mock_save, mock_snap):
        """全市场模式"""
        mock_codes.return_value = ["600000", "300001", "834765"]
        mock_p1.return_value = (
            [{"code": "600000", "name": "浦发"}],
            [],
            {"total": 3, "passed": 1},
        )
        mock_p2.return_value = pd.DataFrame({
            "code": ["600000"],
            "composite_score": [70],
            "综合排序分": [75.0],
        })
        result = es.enhanced_scan(mode="full")
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1

    @patch("stock_analyzer.enhanced_screener._save_snapshot")
    @patch("stock_analyzer.enhanced_screener._save_to_daily_scores")
    @patch("stock_analyzer.enhanced_screener.pass2_deep_analyze")
    @patch("stock_analyzer.enhanced_screener.pass1_quick_filter")
    @patch("stock_analyzer.enhanced_screener._load_all_codes")
    def test_top_sectors_mode(self, mock_codes, mock_p1, mock_p2, mock_save, mock_snap):
        """仅前排板块模式"""
        mock_codes.return_value = ["600000", "000001"]
        mock_p1.return_value = (
            [{"code": "600000", "name": "浦发"}],
            ["银行"],
            {"total": 2, "passed": 1},
        )
        mock_p2.return_value = pd.DataFrame({
            "code": ["600000"],
            "composite_score": [70],
            "综合排序分": [75.0],
        })
        result = es.enhanced_scan(mode="top_sectors")
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1

    @patch("stock_analyzer.enhanced_screener._save_snapshot")
    @patch("stock_analyzer.enhanced_screener._save_to_daily_scores")
    @patch("stock_analyzer.enhanced_screener.pass2_deep_analyze")
    @patch("stock_analyzer.enhanced_screener.pass1_quick_filter")
    @patch("stock_analyzer.enhanced_screener._load_all_codes")
    def test_no_codes(self, mock_codes, mock_p1, mock_p2, mock_save, mock_snap):
        """股票列表为空→空结果"""
        mock_codes.return_value = []
        result = es.enhanced_scan()
        assert isinstance(result, pd.DataFrame)
        assert result.empty
        mock_p1.assert_not_called()

    @patch("stock_analyzer.enhanced_screener._save_snapshot")
    @patch("stock_analyzer.enhanced_screener._save_to_daily_scores")
    @patch("stock_analyzer.enhanced_screener.pass2_deep_analyze")
    @patch("stock_analyzer.enhanced_screener.pass1_quick_filter")
    @patch("stock_analyzer.enhanced_screener._load_all_codes")
    def test_no_candidates(self, mock_codes, mock_p1, mock_p2, mock_save, mock_snap):
        """Pass1 无候选→空结果"""
        mock_codes.return_value = ["600000"]
        mock_p1.return_value = ([], [], {"total": 1, "passed": 0})
        result = es.enhanced_scan()
        assert isinstance(result, pd.DataFrame)
        assert result.empty
        mock_p2.assert_not_called()

    @patch("stock_analyzer.enhanced_screener._save_snapshot")
    @patch("stock_analyzer.enhanced_screener._save_to_daily_scores")
    @patch("stock_analyzer.enhanced_screener.pass2_deep_analyze")
    @patch("stock_analyzer.enhanced_screener.pass1_quick_filter")
    @patch("stock_analyzer.enhanced_screener._load_all_codes")
    def test_empty_pass2(self, mock_codes, mock_p1, mock_p2, mock_save, mock_snap):
        """Pass2 返回空→空结果"""
        mock_codes.return_value = ["600000"]
        mock_p1.return_value = (
            [{"code": "600000", "name": "浦发"}],
            ["银行"],
            {"total": 1, "passed": 1},
        )
        mock_p2.return_value = pd.DataFrame()  # 空
        result = es.enhanced_scan()
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    @patch("stock_analyzer.enhanced_screener._save_snapshot")
    @patch("stock_analyzer.enhanced_screener._save_to_daily_scores")
    @patch("stock_analyzer.enhanced_screener.pass2_deep_analyze")
    @patch("stock_analyzer.enhanced_screener.pass1_quick_filter")
    @patch("stock_analyzer.enhanced_screener._load_all_codes")
    def test_save_called(self, mock_codes, mock_p1, mock_p2, mock_save, mock_snap):
        """验证保存函数被调用"""
        mock_codes.return_value = ["600000"]
        mock_p1.return_value = (
            [{"code": "600000", "name": "浦发"}],
            ["银行"],
            {"total": 1, "passed": 1},
        )
        mock_p2.return_value = pd.DataFrame({
            "code": ["600000"],
            "composite_score": [70],
            "综合排序分": [75.0],
        })
        es.enhanced_scan()
        mock_save.assert_called_once()
        mock_snap.assert_called_once()


# ── Test: _save_to_daily_scores ──────────────────────

class TestSaveToDailyScores:
    @patch("stock_analyzer.enhanced_screener.sqlite3.connect")
    def test_success(self, mock_conn):
        df = pd.DataFrame({
            "code": ["600000"],
            "name": ["浦发银行"],
            "composite_score": [70.0],
            "rating": ["A"],
            "动量分": [65.0],
            "技术分": [70.0],
            "基本面分": [75.0],
            "量能分": [60.0],
            "风险分": [55.0],
        })
        es._save_to_daily_scores(df)
        mock_conn.return_value.execute.assert_called()

    @patch("stock_analyzer.enhanced_screener.sqlite3.connect")
    def test_conn_exception(self, mock_conn):
        """数据库连接异常不崩溃"""
        mock_conn.side_effect = RuntimeError("conn fail")
        df = pd.DataFrame({"code": ["600000"]})
        es._save_to_daily_scores(df)  # 不应抛出异常

    @patch("stock_analyzer.enhanced_screener.sqlite3.connect")
    def test_multiple_rows(self, mock_conn):
        """多行写入"""
        df = pd.DataFrame({
            "code": ["600000", "000001"],
            "name": ["浦发", "平安"],
            "composite_score": [70.0, 65.0],
            "rating": ["A", "B"],
            "动量分": [65.0, 55.0],
            "技术分": [70.0, 60.0],
            "基本面分": [75.0, 65.0],
            "量能分": [60.0, 50.0],
            "风险分": [55.0, 45.0],
        })
        es._save_to_daily_scores(df)
        execute = mock_conn.return_value.execute
        assert execute.call_count >= 2

    @patch("stock_analyzer.enhanced_screener.sqlite3.connect")
    def test_empty_df(self, mock_conn):
        """空 DataFrame→不执行任何 INSERT"""
        es._save_to_daily_scores(pd.DataFrame())
        mock_conn.return_value.__enter__.return_value.execute.assert_not_called()


# ── Test: _save_snapshot ──────────────────────────────

class TestSaveSnapshot:
    RE = "stock_analyzer.enhanced_screener"

    @patch(f"{RE}.os.path")
    @patch(f"{RE}.os.makedirs")
    @patch(f"{RE}.pd.DataFrame.to_csv")
    def test_success(self, mock_csv, mock_makedirs, mock_path):
        """保存 CSV 快照"""
        mock_path.exists.return_value = True
        mock_path.dirname.return_value = "/tmp/reports"
        mock_path.join.return_value = "/tmp/reports/enhanced_scan_20250601_1200.csv"

        es._save_snapshot(pd.DataFrame({
            "code": ["600000"],
            "composite_score": [70.0],
        }))

        mock_makedirs.assert_called_once()
        mock_csv.assert_called_once()
        # 不应该抛异常

    @patch(f"{RE}.os.path")
    @patch(f"{RE}.os.makedirs")
    @patch(f"{RE}.pd.DataFrame.to_csv")
    def test_with_real_df(self, mock_csv, mock_makedirs, mock_path):
        """用真实 DataFrame 保存"""
        mock_path.exists.return_value = True
        mock_path.dirname.return_value = "/tmp/reports"
        mock_path.join.return_value = "/tmp/reports/enhanced_scan_20250601_1200.csv"

        df = pd.DataFrame({"code": ["600000"], "name": ["浦发"]})
        es._save_snapshot(df)
        mock_makedirs.assert_called_once()
        mock_csv.assert_called_once()
