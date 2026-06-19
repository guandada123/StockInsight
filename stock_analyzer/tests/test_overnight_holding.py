"""测试 overnight_holding.py — 一夜持股法尾盘选股模块（六步筛选 + 纪律验证 + 评分）"""

import unittest
from unittest import mock

import numpy as np
import pandas as pd

from stock_analyzer import overnight_holding as oh

# ── 测试辅助工具 ────────────────────────────────────


def _make_kline(rows=100, seed=42):
    """生成模拟K线数据"""
    np.random.seed(seed)
    close = 50 + np.cumsum(np.random.randn(rows) * 0.5)
    changes = np.random.randn(rows) * 2  # 涨跌幅%
    df = pd.DataFrame(
        {
            "日期": pd.date_range("2025-01-01", periods=rows),
            "开盘": close * 0.99,
            "收盘": close,
            "最高": close * 1.02,
            "最低": close * 0.98,
            "成交量": np.random.randint(1_000_000, 10_000_000, rows),
            "成交额": np.random.randint(50_000_000, 500_000_000, rows),
            "涨跌幅": changes,
            "换手率": np.random.uniform(1, 8, rows),
        }
    )
    return df


def _make_stock(**overrides):
    """生成模拟股票数据结构"""
    stock = {
        "涨跌幅": 4.0,
        "量比": 2.5,
        "换手率": 8.0,
        "流通市值": 100 * 1e8,
        "最新价": 25.0,
        "最高": 26.0,
        "最低": 24.5,
        "成交额": 5e8,
        "成交量": 20_000_000,
        "振幅": 6.0,
        "名称": "测试股票",
        "昨收": 24.0,
    }
    stock.update(overrides)
    return stock


# ════════════════════════════════════════════
# 数据层测试
# ════════════════════════════════════════════


class TestCalcAmplitude(unittest.TestCase):
    """振幅计算"""

    def test_normal_case(self):
        """正常计算：最高-最低/昨收*100"""
        data = {"最高": 26.0, "最低": 24.0, "昨收": 25.0, "振幅": 0}
        result = oh._calc_amplitude(data)
        self.assertAlmostEqual(result, 8.0, places=1)

    def test_returns_amplitude_field_when_no_hl(self):
        """当最高/最低/昨收缺失时，返回已有振幅字段"""
        data = {"振幅": 5.5}
        result = oh._calc_amplitude(data)
        self.assertEqual(result, 5.5)

    def test_handles_high_equal_low(self):
        """最高=最低时返回已有振幅"""
        data = {"最高": 25.0, "最低": 25.0, "昨收": 25.0, "振幅": 3.0}
        result = oh._calc_amplitude(data)
        self.assertEqual(result, 3.0)

    def test_missing_yclose(self):
        """缺昨收时返回已有振幅"""
        data = {"最高": 26.0, "最低": 24.0, "振幅": 4.0}
        result = oh._calc_amplitude(data)
        self.assertEqual(result, 4.0)


class TestGetFloatShare(unittest.TestCase):
    """流通股本获取"""

    def test_uses_cache(self):
        """缓存命中直接返回"""
        df = _make_kline(30)
        cache = {"600001": 1e8}
        result = oh._get_float_share("600001", df, cache)
        self.assertEqual(result, 1e8)

    def test_estimate_from_kline(self):
        """K线估算成功"""
        df = _make_kline(30)
        cache = {}
        result = oh._get_float_share("600001", df, cache)
        # 结果应大于0
        self.assertGreater(result, 0)

    @mock.patch("stock_analyzer.overnight_holding._get_float_share_from_baostock")
    def test_fallback_to_baostock(self, mock_baostock):
        """K线估算失败时回退到baostock"""
        mock_baostock.return_value = 5e8
        # 给一个空成交额的df，让K线估算失败
        df = _make_kline(10)
        df["成交额"] = 0
        cache = {}
        result = oh._get_float_share("600001", df, cache)
        self.assertEqual(result, 5e8)
        mock_baostock.assert_called_once_with("600001")


class TestEstimateFloatShareFromKline(unittest.TestCase):
    """K线估算流通股本"""

    def test_normal_estimate(self):
        """正常估算"""
        df = _make_kline(30)
        result = oh._estimate_float_share_from_kline(df)
        self.assertGreater(result, 0)

    def test_empty_df(self):
        """空df返回0"""
        result = oh._estimate_float_share_from_kline(pd.DataFrame())
        self.assertEqual(result, 0)

    def test_zero_amount(self):
        """成交额为0返回0"""
        df = _make_kline(30)
        df["成交额"] = 0
        result = oh._estimate_float_share_from_kline(df)
        self.assertEqual(result, 0)

    def test_few_rows(self):
        """行数少仍可估算"""
        df = _make_kline(5)
        result = oh._estimate_float_share_from_kline(df)
        # 行数少但仍有数据
        self.assertGreaterEqual(result, 0)


class TestGetFloatShareFromBaostock(unittest.TestCase):
    """baostock查询流通股本"""

    @mock.patch(
        "stock_analyzer.overnight_holding._get_float_share_from_baostock._logged_in",
        new_callable=mock.PropertyMock,
        create=True,
    )
    @mock.patch("builtins.hasattr")
    @mock.patch("baostock.query_history_k_data_plus")
    @mock.patch("baostock.login")
    def test_success(self, mock_login, mock_query, mock_hasattr, mock_logged_in):
        """成功查询"""
        # 模拟已登录
        mock_hasattr.return_value = True
        # 模拟查询结果
        mock_rs = mock.MagicMock()
        mock_rs.next.side_effect = [True, True, False]
        mock_rs.get_row_data.side_effect = [
            ["2026-06-01", "2.5", "10000000"],
            ["2026-06-02", "3.0", "12000000"],
        ]
        mock_query.return_value = mock_rs
        result = oh._get_float_share_from_baostock("600001")
        # vol=12000000, turn=3.0 → 12000000 / (3.0/100) = 400000000
        self.assertAlmostEqual(result, 400_000_000)
        mock_login.assert_not_called()  # hasattr返回True表示已登录

    @mock.patch(
        "stock_analyzer.overnight_holding._get_float_share_from_baostock._logged_in",
        new_callable=mock.PropertyMock,
        create=True,
    )
    @mock.patch("baostock.login")
    @mock.patch("baostock.query_history_k_data_plus")
    def test_login_if_needed(self, mock_query, mock_login, mock_logged_in):
        """未登录时自动登录"""
        # 没有_logged_in属性 → 需要登录
        mock_query.side_effect = Exception("no data")
        result = oh._get_float_share_from_baostock("000001")
        self.assertEqual(result, 0)

    @mock.patch(
        "stock_analyzer.overnight_holding._get_float_share_from_baostock._logged_in",
        new_callable=mock.PropertyMock,
        create=True,
    )
    @mock.patch("baostock.login")
    @mock.patch("baostock.query_history_k_data_plus")
    def test_empty_result(self, mock_query, mock_login, mock_logged_in):
        """无数据返回0"""
        mock_rs = mock.MagicMock()
        mock_rs.next.return_value = False
        mock_query.return_value = mock_rs
        result = oh._get_float_share_from_baostock("000001")
        self.assertEqual(result, 0)

    @mock.patch(
        "stock_analyzer.overnight_holding._get_float_share_from_baostock._logged_in",
        new_callable=mock.PropertyMock,
        create=True,
    )
    @mock.patch("baostock.login")
    @mock.patch("baostock.query_history_k_data_plus")
    def test_zero_turnover(self, mock_query, mock_login, mock_logged_in):
        """换手率为0返回0"""
        mock_rs = mock.MagicMock()
        mock_rs.next.side_effect = [True, False]
        mock_rs.get_row_data.return_value = ["2026-06-01", "0", "10000000"]
        mock_query.return_value = mock_rs
        result = oh._get_float_share_from_baostock("000001")
        self.assertEqual(result, 0)

    @mock.patch(
        "stock_analyzer.overnight_holding._get_float_share_from_baostock._logged_in",
        new_callable=mock.PropertyMock,
        create=True,
    )
    @mock.patch("baostock.login")
    @mock.patch("baostock.query_history_k_data_plus")
    def test_sh_symbol(self, mock_query, mock_login, mock_logged_in):
        """沪市股票 prefix sh."""
        mock_rs = mock.MagicMock()
        mock_rs.next.side_effect = [True, False]
        mock_rs.get_row_data.return_value = ["2026-06-01", "5.0", "20000000"]
        mock_query.return_value = mock_rs
        result = oh._get_float_share_from_baostock("600001")
        self.assertGreater(result, 0)
        # 验证传入了sh.600001
        call_args = mock_query.call_args
        self.assertEqual(call_args[0][0], "sh.600001")


# ════════════════════════════════════════════
# 六步筛选 — 纯函数测试
# ════════════════════════════════════════════


class TestStep1GainFilter(unittest.TestCase):
    """Step 1: 涨幅 3%-5%"""

    def test_passes_3_to_5(self):
        """涨幅3%-5%通过"""
        stocks = {"600001": _make_stock(涨跌幅=4.0)}
        result = oh._step1_gain_filter(stocks)
        self.assertIn("600001", result)

    def test_filters_below_3(self):
        """涨幅<3%淘汰"""
        stocks = {"600001": _make_stock(涨跌幅=2.9)}
        result = oh._step1_gain_filter(stocks)
        self.assertNotIn("600001", result)

    def test_filters_above_5(self):
        """涨幅>5%淘汰"""
        stocks = {"600001": _make_stock(涨跌幅=5.1)}
        result = oh._step1_gain_filter(stocks)
        self.assertNotIn("600001", result)

    def test_boundary_3(self):
        """涨幅恰好3%通过"""
        stocks = {"600001": _make_stock(涨跌幅=3.0)}
        result = oh._step1_gain_filter(stocks)
        self.assertIn("600001", result)

    def test_boundary_5(self):
        """涨幅恰好5%通过"""
        stocks = {"600001": _make_stock(涨跌幅=5.0)}
        result = oh._step1_gain_filter(stocks)
        self.assertIn("600001", result)

    def test_mixed_stocks(self):
        """混合情况只保留符合条件的"""
        stocks = {
            "600001": _make_stock(涨跌幅=4.0),
            "600002": _make_stock(涨跌幅=2.0),
            "600003": _make_stock(涨跌幅=6.0),
            "600004": _make_stock(涨跌幅=3.5),
        }
        result = oh._step1_gain_filter(stocks)
        self.assertEqual(set(result.keys()), {"600001", "600004"})

    def test_negative_gain(self):
        """负涨幅淘汰"""
        stocks = {"600001": _make_stock(涨跌幅=-1.0)}
        result = oh._step1_gain_filter(stocks)
        self.assertNotIn("600001", result)

    def test_empty_input(self):
        """空输入返回空字典"""
        self.assertEqual(oh._step1_gain_filter({}), {})


class TestStep2VolumeRatio(unittest.TestCase):
    """Step 2: 量比 > min_vr"""

    def test_passes_above_1(self):
        """量比>1通过"""
        stocks = {"600001": _make_stock(量比=2.0)}
        result = oh._step2_volume_ratio(stocks)
        self.assertIn("600001", result)

    def test_filters_below_1(self):
        """量比≤1淘汰"""
        stocks = {"600001": _make_stock(量比=0.8)}
        result = oh._step2_volume_ratio(stocks)
        self.assertNotIn("600001", result)

    def test_boundary_1(self):
        """量比恰好1淘汰（需要>1）"""
        stocks = {"600001": _make_stock(量比=1.0)}
        result = oh._step2_volume_ratio(stocks)
        self.assertNotIn("600001", result)

    def test_custom_min_vr(self):
        """自定义min_vr参数"""
        stocks = {"600001": _make_stock(量比=1.5)}
        result = oh._step2_volume_ratio(stocks, min_vr=2.0)
        self.assertNotIn("600001", result)

    def test_missing_volume_ratio(self):
        """缺量比字段时按0处理"""
        stocks = {"600001": _make_stock()}
        del stocks["600001"]["量比"]
        result = oh._step2_volume_ratio(stocks)
        self.assertNotIn("600001", result)


class TestStep3Turnover(unittest.TestCase):
    """Step 3: 换手率 5%-15%"""

    def test_passes_5_to_15(self):
        """换手率5-15%通过"""
        stocks = {"600001": _make_stock(换手率=10.0)}
        result = oh._step3_turnover(stocks)
        self.assertIn("600001", result)

    def test_filters_below_5(self):
        """换手率<5%淘汰"""
        stocks = {"600001": _make_stock(换手率=4.9)}
        result = oh._step3_turnover(stocks)
        self.assertNotIn("600001", result)

    def test_filters_above_15(self):
        """换手率>15%淘汰"""
        stocks = {"600001": _make_stock(换手率=15.1)}
        result = oh._step3_turnover(stocks)
        self.assertNotIn("600001", result)

    def test_boundary_5(self):
        """换手率恰好5%通过"""
        stocks = {"600001": _make_stock(换手率=5.0)}
        result = oh._step3_turnover(stocks)
        self.assertIn("600001", result)

    def test_boundary_15(self):
        """换手率恰好15%通过"""
        stocks = {"600001": _make_stock(换手率=15.0)}
        result = oh._step3_turnover(stocks)
        self.assertIn("600001", result)

    def test_custom_range(self):
        """自定义t_min/t_max"""
        stocks = {"600001": _make_stock(换手率=20.0)}
        result = oh._step3_turnover(stocks, t_min=10, t_max=25)
        self.assertIn("600001", result)


class TestStep4MarketCap(unittest.TestCase):
    """Step 4: 流通市值 50-200亿"""

    def test_passes_50_to_200(self):
        """流通市值50-200亿通过"""
        stocks = {"600001": _make_stock(流通市值=100 * 1e8)}
        result = oh._step4_market_cap(stocks)
        self.assertIn("600001", result)

    def test_filters_below_50(self):
        """流通市值<50亿淘汰"""
        stocks = {"600001": _make_stock(流通市值=30 * 1e8)}
        result = oh._step4_market_cap(stocks)
        self.assertNotIn("600001", result)

    def test_filters_above_200(self):
        """流通市值>200亿淘汰"""
        stocks = {"600001": _make_stock(流通市值=300 * 1e8)}
        result = oh._step4_market_cap(stocks)
        self.assertNotIn("600001", result)

    def test_boundary_50(self):
        """流通市值恰好50亿通过"""
        stocks = {"600001": _make_stock(流通市值=50 * 1e8)}
        result = oh._step4_market_cap(stocks)
        self.assertIn("600001", result)

    def test_boundary_200(self):
        """流通市值恰好200亿通过"""
        stocks = {"600001": _make_stock(流通市值=200 * 1e8)}
        result = oh._step4_market_cap(stocks)
        self.assertIn("600001", result)


class TestPriceFilter(unittest.TestCase):
    """价格过滤"""

    def test_passes_10_to_80(self):
        """价格10-80元通过"""
        stocks = {"600001": _make_stock(最新价=25.0)}
        result = oh._price_filter(stocks)
        self.assertIn("600001", result)

    def test_filters_below_10(self):
        """价格<10元淘汰"""
        stocks = {"600001": _make_stock(最新价=9.0)}
        result = oh._price_filter(stocks)
        self.assertNotIn("600001", result)

    def test_filters_above_80(self):
        """价格>80元淘汰"""
        stocks = {"600001": _make_stock(最新价=100.0)}
        result = oh._price_filter(stocks)
        self.assertNotIn("600001", result)

    def test_custom_range(self):
        """自定义价格区间"""
        stocks = {
            "600001": _make_stock(最新价=5.0),
            "600002": _make_stock(最新价=15.0),
        }
        result = oh._price_filter(stocks, min_price=10, max_price=50)
        self.assertNotIn("600001", result)
        self.assertIn("600002", result)


# ════════════════════════════════════════════
# K线分析 — mock cached_kline
# ════════════════════════════════════════════


class TestHasLimitUpInDays(unittest.TestCase):
    """检测20日内是否有涨停"""

    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    def test_has_limit_up(self, mock_ck):
        """有涨停板"""
        df = _make_kline(30)
        df["涨跌幅"] = 0.5
        df.iloc[-5, df.columns.get_loc("涨跌幅")] = 9.9
        mock_ck.return_value = df
        self.assertTrue(oh._has_limit_up_in_days("600001"))

    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    def test_no_limit_up(self, mock_ck):
        """无涨停板"""
        df = _make_kline(30)
        df["涨跌幅"] = 5.0  # 都小于9.8
        mock_ck.return_value = df
        self.assertFalse(oh._has_limit_up_in_days("600001"))

    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    def test_not_enough_data(self, mock_ck):
        """数据不足"""
        df = _make_kline(3)
        mock_ck.return_value = df
        self.assertFalse(oh._has_limit_up_in_days("600001"))

    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    def test_none_data(self, mock_ck):
        """cached_kline返回None"""
        mock_ck.return_value = None
        self.assertFalse(oh._has_limit_up_in_days("600001"))

    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    def test_exception_handled(self, mock_ck):
        """异常被捕获返回False"""
        mock_ck.side_effect = Exception("error")
        self.assertFalse(oh._has_limit_up_in_days("600001"))

    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    def test_custom_days(self, mock_ck):
        """自定义天数"""
        df = _make_kline(50)
        df["涨跌幅"] = 0.5
        mock_ck.return_value = df
        oh._has_limit_up_in_days("600001", days=30)
        # 验证传入的是30天
        self.assertEqual(mock_ck.call_args[1].get("days"), 30)


class TestCheckBullishAlignment(unittest.TestCase):
    """均线多头排列检查"""

    @mock.patch("stock_analyzer.overnight_holding.calc_ma")
    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    def test_aligned_with_expansion(self, mock_ck, mock_ma):
        """多头排列+成交放量"""
        df = _make_kline(80)
        df["MA5"] = 55.0
        df["MA10"] = 53.0
        df["MA20"] = 51.0

        # 成交量处理：近5日均量 > 近20日均量*1.1
        df["成交量"] = 5_000_000
        df.iloc[-5:, df.columns.get_loc("成交量")] = 10_000_000

        mock_ck.return_value = df
        # calc_ma应该返回带MA列的df
        mock_ma.side_effect = lambda df_, _: df_

        ok, info = oh._check_bullish_alignment("600001")
        self.assertTrue(ok)
        self.assertIn("ma5", info)
        self.assertIn("ma10", info)
        self.assertIn("ma20", info)
        self.assertIn("vol_ratio", info)

    @mock.patch("stock_analyzer.overnight_holding.calc_ma")
    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    def test_not_aligned(self, mock_ck, mock_ma):
        """非多头排列"""
        df = _make_kline(80)
        df["MA5"] = 51.0
        df["MA10"] = 53.0
        df["MA20"] = 55.0
        df["成交量"] = 5_000_000
        mock_ck.return_value = df
        mock_ma.side_effect = lambda df_, _: df_

        ok, info = oh._check_bullish_alignment("600001")
        self.assertFalse(ok)

    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    def test_not_enough_data(self, mock_ck):
        """数据不足60行"""
        df = _make_kline(30)
        mock_ck.return_value = df
        ok, info = oh._check_bullish_alignment("600001")
        self.assertFalse(ok)
        self.assertIsNone(info)

    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    def test_none_data(self, mock_ck):
        """cached_kline返回None"""
        mock_ck.return_value = None
        ok, info = oh._check_bullish_alignment("600001")
        self.assertFalse(ok)
        self.assertIsNone(info)

    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    def test_zero_ma_values(self, mock_ck):
        """MA值为0视为False"""
        df = _make_kline(80)
        df["涨跌幅"] = 0.5
        mock_ck.return_value = df
        ok, _ = oh._check_bullish_alignment("600001")
        self.assertFalse(ok)

    @mock.patch("stock_analyzer.overnight_holding.calc_ma")
    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    def test_vol_not_expanding(self, mock_ck, mock_ma):
        """均线多头但成交量不足"""
        df = _make_kline(80)
        df["MA5"] = 55.0
        df["MA10"] = 53.0
        df["MA20"] = 51.0
        # 成交量均匀，近5日没有明显放大
        df["成交量"] = 5_000_000
        mock_ck.return_value = df
        mock_ma.side_effect = lambda df_, _: df_

        ok, _ = oh._check_bullish_alignment("600001")
        self.assertFalse(ok)


# ════════════════════════════════════════════
# 纪律验证
# ════════════════════════════════════════════


class TestCheck20dGain(unittest.TestCase):
    """20日涨幅检查"""

    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    def test_normal(self, mock_ck):
        """正常计算"""
        df = _make_kline(30)
        # 设20日前收盘价为 50，最新收盘为 60
        df.iloc[-1, df.columns.get_loc("收盘")] = 60.0
        df.iloc[-21, df.columns.get_loc("收盘")] = 50.0
        df.iloc[-6, df.columns.get_loc("收盘")] = 55.0
        mock_ck.return_value = df

        result = oh._check_20d_gain("600001")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["20日涨幅"], 20.0, places=0)
        self.assertAlmostEqual(result["近5日涨幅"], 9.1, places=0)

    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    def test_with_rt_price(self, mock_ck):
        """使用实时价计算"""
        df = _make_kline(30)
        df.iloc[-21, df.columns.get_loc("收盘")] = 50.0
        df.iloc[-6, df.columns.get_loc("收盘")] = 55.0
        mock_ck.return_value = df

        result = oh._check_20d_gain("600001", rt_price=65.0)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["20日涨幅"], 30.0, places=0)

    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    def test_not_enough_data(self, mock_ck):
        """数据不足"""
        df = _make_kline(10)
        mock_ck.return_value = df
        result = oh._check_20d_gain("600001")
        self.assertIsNone(result)

    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    def test_none_data(self, mock_ck):
        """cached_kline返回None"""
        mock_ck.return_value = None
        result = oh._check_20d_gain("600001")
        self.assertIsNone(result)


class TestValidateDiscipline(unittest.TestCase):
    """单只纪律验证"""

    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    @mock.patch("stock_analyzer.short_term.calc_combo_signals")
    @mock.patch("stock_analyzer.short_term.short_term_score")
    @mock.patch("stock_analyzer.short_term.calc_fund_flow_summary")
    def test_pass_all(self, mock_ff, mock_score, mock_combo, mock_ck):
        """全部通过"""
        df = _make_kline(80)
        mock_ck.return_value = df
        mock_combo.return_value = {"强度": 1, "信号": "看涨"}
        mock_score.return_value = {"短线评分": 65}
        mock_ff.return_value = {"主力净流入": 1e7}

        stock = _make_stock(振幅=6.0, 最新价=25.0)
        result = oh._validate_discipline("600001", stock)

        self.assertTrue(result["通过"])
        self.assertEqual(result["淘汰原因"], "")
        self.assertGreater(result["短线评分"], 0)

    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    def test_fail_by_amplitude(self, mock_ck):
        """振幅不足3%淘汰"""
        df = _make_kline(30)
        # 20日涨幅<30%
        df.iloc[-1, df.columns.get_loc("收盘")] = 55.0
        df.iloc[-21, df.columns.get_loc("收盘")] = 50.0
        mock_ck.return_value = df

        stock = _make_stock(振幅=2.0, 最新价=25.0)
        result = oh._validate_discipline("600001", stock)

        self.assertFalse(result["通过"])
        self.assertIn("振幅", result["淘汰原因"])

    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    def test_fail_by_20d_gain(self, mock_ck):
        """20日涨幅超30%淘汰"""
        df = _make_kline(30)
        df.iloc[-1, df.columns.get_loc("收盘")] = 65.0
        df.iloc[-21, df.columns.get_loc("收盘")] = 45.0
        mock_ck.return_value = df

        stock = _make_stock(振幅=6.0, 最新价=65.0)
        result = oh._validate_discipline("600001", stock)
        self.assertFalse(result["通过"])
        self.assertIn("20日涨幅", result["淘汰原因"])

    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    @mock.patch("stock_analyzer.short_term.calc_combo_signals")
    @mock.patch("stock_analyzer.short_term.short_term_score")
    def test_fail_by_combo_strength(self, mock_score, mock_combo, mock_ck):
        """组合信号强度≤-2淘汰"""
        df = _make_kline(80)
        mock_ck.return_value = df
        mock_combo.return_value = {"强度": -3, "信号": "看跌"}
        mock_score.return_value = {"短线评分": 30}

        stock = _make_stock(振幅=6.0, 最新价=25.0)
        result = oh._validate_discipline("600001", stock)
        self.assertFalse(result["通过"])
        self.assertIn("强度", result["淘汰原因"])

    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    def test_missing_amplitude(self, mock_ck):
        """缺振幅字段按0处理淘汰"""
        df = _make_kline(30)
        df.iloc[-1, df.columns.get_loc("收盘")] = 55.0
        df.iloc[-21, df.columns.get_loc("收盘")] = 50.0
        mock_ck.return_value = df

        stock = _make_stock()
        del stock["振幅"]
        result = oh._validate_discipline("600001", stock)
        self.assertFalse(result["通过"])
        self.assertIn("振幅", result["淘汰原因"])

    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    @mock.patch("stock_analyzer.short_term.calc_combo_signals")
    @mock.patch("stock_analyzer.short_term.short_term_score")
    def test_combo_signal_exception(self, mock_score, mock_combo, mock_ck):
        """组合信号异常时继续执行不中断"""
        df = _make_kline(80)
        mock_ck.return_value = df
        mock_combo.side_effect = Exception("API error")
        mock_score.side_effect = Exception("score error")

        stock = _make_stock(振幅=6.0, 最新价=25.0)
        result = oh._validate_discipline("600001", stock)
        # 异常被捕获，仍然通过（但短线评分=0）
        self.assertTrue(result["通过"])


class TestBatchValidateDiscipline(unittest.TestCase):
    """批量纪律验证"""

    @mock.patch("stock_analyzer.overnight_holding._validate_discipline")
    def test_mixed_results(self, mock_vd):
        """混合通过/淘汰"""

        def side_effect(code, data, verbose=False):
            if code == "600001":
                return {
                    "通过": True,
                    "淘汰原因": "",
                    "组合信号": {},
                    "短线评分": 60,
                    "20日涨幅": 10,
                    "近5日涨幅": 3,
                    "主力": {},
                }
            else:
                return {
                    "通过": False,
                    "淘汰原因": "振幅不足",
                    "组合信号": {},
                    "短线评分": 0,
                    "20日涨幅": 5,
                    "近5日涨幅": 2,
                    "主力": {},
                }

        mock_vd.side_effect = side_effect

        stocks = {
            "600001": _make_stock(名称="A股"),
            "600002": _make_stock(名称="B股"),
        }
        result = oh._batch_validate_discipline(stocks)
        self.assertIn("600001", result)
        self.assertNotIn("600002", result)
        # 通过的股票应包含纪律字段
        self.assertIn("纪律", result["600001"])

    @mock.patch("stock_analyzer.overnight_holding._validate_discipline")
    def test_all_passed(self, mock_vd):
        """全部通过"""
        mock_vd.return_value = {
            "通过": True,
            "淘汰原因": "",
            "组合信号": {},
            "短线评分": 50,
            "20日涨幅": 8,
            "近5日涨幅": 2,
            "主力": {},
        }
        stocks = {"600001": _make_stock(), "600002": _make_stock()}
        result = oh._batch_validate_discipline(stocks)
        self.assertEqual(len(result), 2)

    @mock.patch("stock_analyzer.overnight_holding._validate_discipline")
    def test_all_eliminated(self, mock_vd):
        """全部淘汰"""
        mock_vd.return_value = {
            "通过": False,
            "淘汰原因": "振幅不足",
            "组合信号": {},
            "短线评分": 0,
            "20日涨幅": 5,
            "近5日涨幅": 2,
            "主力": {},
        }
        stocks = {"600001": _make_stock(), "600002": _make_stock()}
        result = oh._batch_validate_discipline(stocks)
        self.assertEqual(len(result), 0)


# ════════════════════════════════════════════
# 评分系统
# ════════════════════════════════════════════


class TestComputeOvernightScoreV2(unittest.TestCase):
    """一夜持股综合评分 v2"""

    def test_high_score_scenario(self):
        """高评分场景"""
        data = {
            "量比": 3.0,
            "换手率": 10.0,
            "振幅": 8.0,
            "涨跌幅": 3.2,
            "均线": {"ma5": 55, "ma10": 53, "ma20": 51, "vol_ratio": 1.5},
            "纪律": {
                "组合信号": {"强度": 3},
                "短线评分": 80,
                "20日涨幅": 15,
                "近5日涨幅": 8,
            },
        }
        score = oh._compute_overnight_score_v2(data)
        # 量比18 + 换手12 + 振幅10 + 涨幅10 + 均线8+3 + 信号17.5 + 短线12 = ~90.5
        self.assertGreaterEqual(score, 60)
        self.assertLessEqual(score, 100)

    def test_low_score_scenario(self):
        """低评分场景"""
        data = {
            "量比": 1.0,
            "换手率": 5.0,
            "振幅": 3.0,
            "涨跌幅": 5.0,
            "均线": {},
            "纪律": {
                "组合信号": {"强度": -2},
                "短线评分": 20,
                "20日涨幅": 30,
                "近5日涨幅": 20,
            },
        }
        score = oh._compute_overnight_score_v2(data)
        # 追高惩罚-15，得分应较低
        self.assertLessEqual(score, 50)

    def test_missing_discipline(self):
        """缺纪律字段"""
        data = {
            "量比": 2.0,
            "换手率": 8.0,
            "振幅": 5.0,
            "涨跌幅": 3.5,
            "均线": {},
        }
        score = oh._compute_overnight_score_v2(data)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_missing_ma(self):
        """缺均线字段"""
        data = {
            "量比": 2.0,
            "换手率": 8.0,
            "振幅": 5.0,
            "涨跌幅": 3.5,
            "纪律": {"组合信号": {}, "短线评分": 0, "20日涨幅": 0, "近5日涨幅": 0},
        }
        score = oh._compute_overnight_score_v2(data)
        self.assertGreaterEqual(score, 0)

    def test_score_capped_at_100(self):
        """得分上限100"""
        data = {
            "量比": 10.0,
            "换手率": 10.0,
            "振幅": 20.0,
            "涨跌幅": 3.2,
            "均线": {"ma5": 100, "ma10": 90, "ma20": 80, "vol_ratio": 3.0},
            "纪律": {
                "组合信号": {"强度": 4},
                "短线评分": 100,
                "20日涨幅": 10,
                "近5日涨幅": 5,
            },
        }
        score = oh._compute_overnight_score_v2(data)
        self.assertLessEqual(score, 100)

    def test_score_min_0(self):
        """得分下限0"""
        data = {
            "量比": 0.1,
            "换手率": 1.0,
            "振幅": 0.5,
            "涨跌幅": 5.0,
            "均线": {},
            "纪律": {
                "组合信号": {"强度": -4},
                "短线评分": 0,
                "20日涨幅": 30,
                "近5日涨幅": 20,
            },
        }
        score = oh._compute_overnight_score_v2(data)
        self.assertGreaterEqual(score, 0)

    def test_gain_position_scoring(self):
        """涨幅位置得分"""
        # 3-3.5: 10分
        data = {
            "量比": 1.0,
            "换手率": 5.0,
            "振幅": 3.0,
            "涨跌幅": 3.2,
            "纪律": {"组合信号": {}, "短线评分": 0, "20日涨幅": 0, "近5日涨幅": 0},
        }
        score = oh._compute_overnight_score_v2(data)
        self.assertGreater(score, 0)

    def test_turnover_optimal_zone(self):
        """换手率8-12%得满分"""
        data_optimal = {
            "量比": 1.0,
            "换手率": 10.0,
            "振幅": 3.0,
            "涨跌幅": 3.2,
            "纪律": {"组合信号": {}, "短线评分": 0, "20日涨幅": 0, "近5日涨幅": 0},
        }
        data_edge = {
            "量比": 1.0,
            "换手率": 5.0,
            "振幅": 3.0,
            "涨跌幅": 3.2,
            "纪律": {"组合信号": {}, "短线评分": 0, "20日涨幅": 0, "近5日涨幅": 0},
        }
        score_opt = oh._compute_overnight_score_v2(data_optimal)
        score_edge = oh._compute_overnight_score_v2(data_edge)
        self.assertGreater(score_opt, score_edge)


class TestComputeOvernightScore(unittest.TestCase):
    """一夜持股综合评分 v1"""

    def test_normal_scoring(self):
        """正常评分"""
        data = {
            "量比": 2.0,
            "换手率": 10.0,
            "振幅": 5.0,
            "涨跌幅": 3.5,
            "均线": {"ma5": 55, "ma10": 53, "ma20": 51, "vol_ratio": 1.5},
        }
        score = oh._compute_overnight_score(data)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_missing_ma(self):
        """缺均线"""
        data = {
            "量比": 2.0,
            "换手率": 10.0,
            "振幅": 5.0,
            "涨跌幅": 3.5,
        }
        score = oh._compute_overnight_score(data)
        self.assertGreaterEqual(score, 0)

    def test_turnover_boundary(self):
        """换手率边界得分"""
        data_in = {
            "量比": 1.0,
            "换手率": 8.0,
            "振幅": 3.0,
            "涨跌幅": 3.2,
            "均线": {},
        }
        data_out = {
            "量比": 1.0,
            "换手率": 4.0,
            "振幅": 3.0,
            "涨跌幅": 3.2,
            "均线": {},
        }
        score_in = oh._compute_overnight_score(data_in)
        score_out = oh._compute_overnight_score(data_out)
        self.assertGreater(score_in, score_out)

    def test_gain_scoring(self):
        """涨跌幅3-3.5满分"""
        data_best = {
            "量比": 1.0,
            "换手率": 5.0,
            "振幅": 3.0,
            "涨跌幅": 3.2,
            "均线": {},
        }
        data_high = {
            "量比": 1.0,
            "换手率": 5.0,
            "振幅": 3.0,
            "涨跌幅": 4.5,
            "均线": {},
        }
        score_best = oh._compute_overnight_score(data_best)
        score_high = oh._compute_overnight_score(data_high)
        self.assertGreater(score_best, score_high)

    def test_vol_ratio_bonus(self):
        """量比>1.2额外加分"""
        data_high_vol = {
            "量比": 2.0,
            "换手率": 10.0,
            "振幅": 5.0,
            "涨跌幅": 3.2,
            "均线": {"ma5": 60, "ma10": 55, "ma20": 50, "vol_ratio": 1.5},
        }
        data_low_vol = {
            "量比": 2.0,
            "换手率": 10.0,
            "振幅": 5.0,
            "涨跌幅": 3.2,
            "均线": {"ma5": 60, "ma10": 55, "ma20": 50, "vol_ratio": 1.0},
        }
        score_high = oh._compute_overnight_score(data_high_vol)
        score_low = oh._compute_overnight_score(data_low_vol)
        self.assertGreater(score_high, score_low)

    def test_score_capped(self):
        """上限100"""
        data = {
            "量比": 5.0,
            "换手率": 10.0,
            "振幅": 15.0,
            "涨跌幅": 3.0,
            "均线": {"ma5": 100, "ma10": 90, "ma20": 80, "vol_ratio": 3.0},
        }
        score = oh._compute_overnight_score(data)
        self.assertLessEqual(score, 100)


# ════════════════════════════════════════════
# 输出函数
# ════════════════════════════════════════════


class TestPrintResults(unittest.TestCase):
    """格式化输出"""

    def test_print_results(self):
        """基本输出不崩溃"""
        results = [
            {
                "代码": "600001",
                "名称": "测试股票A",
                "最新价": 25.0,
                "涨跌幅": 4.0,
                "振幅": 6.0,
                "量比": 2.5,
                "换手率": 8.0,
                "流通市值": 100 * 1e8,
                "成交额": 5e8,
                "一夜评分": 85,
                "20日涨幅": 15.0,
                "近5日涨幅": 5.0,
                "组合信号": "看涨",
                "信号强度": 2,
                "短线评分": 70,
                "均线": {"ma5": 55, "ma10": 53, "ma20": 51},
            }
        ]
        try:
            oh._print_results(results)
        except Exception as e:
            self.fail(f"_print_results raised {e}")

    def test_print_results_empty(self):
        """空列表不崩溃"""
        try:
            oh._print_results([])
        except Exception as e:
            self.fail(f"_print_results([]) raised {e}")

    def test_print_results_zero_market_cap(self):
        """流通市值为0不崩溃"""
        results = [
            {
                "代码": "600001",
                "名称": "测试",
                "最新价": 25.0,
                "涨跌幅": 4.0,
                "振幅": 6.0,
                "量比": 2.5,
                "换手率": 8.0,
                "流通市值": 0,
                "成交额": 0,
                "一夜评分": 50,
                "20日涨幅": 0,
                "近5日涨幅": 0,
                "组合信号": "?",
                "信号强度": 0,
                "短线评分": 0,
                "均线": {},
            }
        ]
        try:
            oh._print_results(results)
        except Exception as e:
            self.fail(f"_print_results with zero market cap raised {e}")


class TestPrintSellRules(unittest.TestCase):
    """卖出规则输出"""

    def test_runs_without_error(self):
        """不崩溃"""
        try:
            oh._print_sell_rules()
        except Exception as e:
            self.fail(f"_print_sell_rules raised {e}")


# ════════════════════════════════════════════
# 主线扫描（集成级别，全mock外部依赖）
# ════════════════════════════════════════════


class TestRunOvernightScan(unittest.TestCase):
    """run_overnight_scan 全流程"""

    @mock.patch("stock_analyzer.overnight_holding._get_mainboard_codes")
    @mock.patch("stock_analyzer.overnight_holding._batch_sina_quotes")
    @mock.patch("stock_analyzer.overnight_holding._em_quote_batch")
    @mock.patch("stock_analyzer.overnight_holding._has_limit_up_in_days")
    @mock.patch("stock_analyzer.overnight_holding._check_bullish_alignment")
    @mock.patch("stock_analyzer.overnight_holding._validate_discipline")
    def test_normal_flow(
        self, mock_vd, mock_alignment, mock_limitup, mock_em, mock_sina, mock_codes
    ):
        """正常流程能找到候选"""
        mock_codes.return_value = ["600001", "600002", "600003"]
        mock_sina.return_value = {
            "600001": {
                "涨跌幅": 4.0,
                "成交量": 2e7,
                "成交额": 5e8,
                "最新价": 25.0,
                "最高": 26.0,
                "最低": 24.5,
                "名称": "A",
                "昨收": 24.0,
            },
            "600002": {
                "涨跌幅": 3.5,
                "成交量": 1.5e7,
                "成交额": 3e8,
                "最新价": 30.0,
                "最高": 31.0,
                "最低": 29.5,
                "名称": "B",
                "昨收": 29.0,
            },
            "600003": {
                "涨跌幅": 3.2,
                "成交量": 1e7,
                "成交额": 2e8,
                "最新价": 20.0,
                "最高": 21.0,
                "最低": 19.5,
                "名称": "C",
                "昨收": 19.5,
            },
        }
        mock_em.return_value = {
            "600001": {
                "量比": 2.5,
                "换手率": 8.0,
                "流通市值": 100 * 1e8,
                "振幅": 6.0,
                "涨跌幅": 4.0,
                "最新价": 25.0,
                "最高": 26.0,
                "最低": 24.5,
                "成交额": 5e8,
                "成交量": 2e7,
                "名称": "A",
            },
            "600002": {
                "量比": 1.5,
                "换手率": 6.0,
                "流通市值": 80 * 1e8,
                "振幅": 5.0,
                "涨跌幅": 3.5,
                "最新价": 30.0,
                "最高": 31.0,
                "最低": 29.5,
                "成交额": 3e8,
                "成交量": 1.5e7,
                "名称": "B",
            },
            "600003": {
                "量比": 2.0,
                "换手率": 7.0,
                "流通市值": 60 * 1e8,
                "振幅": 4.5,
                "涨跌幅": 3.2,
                "最新价": 20.0,
                "最高": 21.0,
                "最低": 19.5,
                "成交额": 2e8,
                "成交量": 1e7,
                "名称": "C",
            },
        }
        # Step 5: 全部通过
        mock_limitup.return_value = True
        # Step 6: 全部通过
        mock_alignment.return_value = (True, {"ma5": 55, "ma10": 53, "ma20": 51, "vol_ratio": 1.3})
        # 纪律: 全部通过
        mock_vd.return_value = {
            "通过": True,
            "淘汰原因": "",
            "组合信号": {"强度": 1, "信号": "看涨"},
            "短线评分": 65,
            "20日涨幅": 10,
            "近5日涨幅": 3,
            "主力": {},
        }

        results = oh.run_overnight_scan(top_n=5, verbose=False)
        self.assertGreater(len(results), 0)
        # 结果按评分降序排列
        for i in range(len(results) - 1):
            self.assertGreaterEqual(results[i]["一夜评分"], results[i + 1]["一夜评分"])

    @mock.patch("stock_analyzer.overnight_holding._get_mainboard_codes")
    @mock.patch("stock_analyzer.overnight_holding._batch_sina_quotes")
    def test_no_step1_candidates(self, mock_sina, mock_codes):
        """Step1无候选返回空列表"""
        mock_codes.return_value = ["600001"]
        mock_sina.return_value = {
            "600001": {"涨跌幅": 2.0, "成交量": 0, "最新价": 25.0},
        }
        results = oh.run_overnight_scan(verbose=False)
        self.assertEqual(results, [])

    @mock.patch("stock_analyzer.overnight_holding._get_mainboard_codes")
    @mock.patch("stock_analyzer.overnight_holding._batch_sina_quotes")
    @mock.patch("stock_analyzer.overnight_holding._em_quote_batch")
    @mock.patch("stock_analyzer.overnight_holding._has_limit_up_in_days")
    @mock.patch("stock_analyzer.overnight_holding._check_bullish_alignment")
    @mock.patch("stock_analyzer.overnight_holding._validate_discipline")
    def test_all_eliminated_by_discipline(
        self, mock_vd, mock_alignment, mock_limitup, mock_em, mock_sina, mock_codes
    ):
        """纪律验证全部淘汰返回空列表"""
        mock_codes.return_value = ["600001"]
        mock_sina.return_value = {
            "600001": {
                "涨跌幅": 4.0,
                "成交量": 2e7,
                "成交额": 5e8,
                "最新价": 25.0,
                "最高": 26.0,
                "最低": 24.5,
                "名称": "A",
                "昨收": 24.0,
            },
        }
        mock_em.return_value = {
            "600001": {
                "量比": 2.5,
                "换手率": 8.0,
                "流通市值": 100 * 1e8,
                "振幅": 6.0,
                "涨跌幅": 4.0,
                "最新价": 25.0,
                "最高": 26.0,
                "最低": 24.5,
                "成交额": 5e8,
                "成交量": 2e7,
                "名称": "A",
            },
        }
        mock_limitup.return_value = True
        mock_alignment.return_value = (True, {"ma5": 55, "ma10": 53, "ma20": 51, "vol_ratio": 1.3})
        mock_vd.return_value = {
            "通过": False,
            "淘汰原因": "20日涨幅超过30%红线",
            "组合信号": {},
            "短线评分": 0,
            "20日涨幅": 35,
            "近5日涨幅": 10,
            "主力": {},
        }

        results = oh.run_overnight_scan(verbose=False)
        self.assertEqual(results, [])

    @mock.patch("stock_analyzer.overnight_holding._get_mainboard_codes")
    @mock.patch("stock_analyzer.overnight_holding._batch_sina_quotes")
    @mock.patch("stock_analyzer.overnight_holding._kline_fallback_batch")
    @mock.patch("stock_analyzer.overnight_holding._has_limit_up_in_days")
    @mock.patch("stock_analyzer.overnight_holding._check_bullish_alignment")
    @mock.patch("stock_analyzer.overnight_holding._validate_discipline")
    def test_em_coverage_low_triggers_fallback(
        self, mock_vd, mock_alignment, mock_limitup, mock_fallback, mock_sina, mock_codes
    ):
        """EM覆盖率<50%时触发K线降级"""
        mock_codes.return_value = ["600001", "600002", "600003"]
        mock_sina.return_value = {
            "600001": {
                "涨跌幅": 4.0,
                "成交量": 2e7,
                "最新价": 25.0,
                "最高": 26.0,
                "最低": 24.5,
                "名称": "A",
                "昨收": 24.0,
            },
            "600002": {
                "涨跌幅": 3.5,
                "成交量": 1.5e7,
                "最新价": 30.0,
                "最高": 31.0,
                "最低": 29.5,
                "名称": "B",
                "昨收": 29.0,
            },
            "600003": {
                "涨跌幅": 3.2,
                "成交量": 1e7,
                "最新价": 20.0,
                "最高": 21.0,
                "最低": 19.5,
                "名称": "C",
                "昨收": 19.5,
            },
        }
        # EM只返回1只 → 覆盖率33% < 50%
        mock_em = mock.MagicMock(
            return_value={
                "600001": {
                    "量比": 2.5,
                    "换手率": 8.0,
                    "流通市值": 100 * 1e8,
                    "振幅": 6.0,
                    "涨跌幅": 4.0,
                    "最新价": 25.0,
                    "最高": 26.0,
                    "最低": 24.5,
                    "成交额": 5e8,
                    "成交量": 2e7,
                    "名称": "A",
                },
            }
        )
        with mock.patch("stock_analyzer.overnight_holding._em_quote_batch", mock_em):
            mock_fallback.return_value = {
                "600002": {
                    "量比": 1.5,
                    "换手率": 6.0,
                    "流通市值": 80 * 1e8,
                    "振幅": 5.0,
                    "涨跌幅": 3.5,
                    "最新价": 30.0,
                    "名称": "B",
                },
            }
            mock_limitup.return_value = True
            mock_alignment.return_value = (
                True,
                {"ma5": 55, "ma10": 53, "ma20": 51, "vol_ratio": 1.3},
            )
            mock_vd.return_value = {
                "通过": True,
                "淘汰原因": "",
                "组合信号": {"强度": 1},
                "短线评分": 65,
                "20日涨幅": 10,
                "近5日涨幅": 3,
                "主力": {},
            }
            results = oh.run_overnight_scan(verbose=False)
            self.assertGreater(len(results), 0)
            mock_fallback.assert_called_once()


class TestOvernightSellCheck(unittest.TestCase):
    """早盘卖出检查"""

    @mock.patch("stock_analyzer.overnight_holding._em_quote_batch")
    def test_profit_above_5(self, mock_em):
        """盈利≥5% → 急卖"""
        mock_em.return_value = {
            "600001": {"最新价": 26.25, "涨跌幅": 5.0, "量比": 1.2, "名称": "测试A"},
        }
        positions = [{"代码": "600001", "成本": 25.0, "股数": 1000}]
        oh.overnight_sell_check(positions)

    @mock.patch("stock_analyzer.overnight_holding._em_quote_batch")
    def test_profit_2_to_5(self, mock_em):
        """盈利2-5% → 分批止盈"""
        mock_em.return_value = {
            "600001": {"最新价": 25.75, "涨跌幅": 3.0, "量比": 1.2, "名称": "测试A"},
        }
        positions = [{"代码": "600001", "成本": 25.0, "股数": 1000}]
        oh.overnight_sell_check(positions)

    @mock.patch("stock_analyzer.overnight_holding._em_quote_batch")
    def test_profit_1_to_2(self, mock_em):
        """盈利1-2% → 冲高止盈"""
        mock_em.return_value = {
            "600001": {"最新价": 25.5, "涨跌幅": 2.0, "量比": 1.2, "名称": "测试A"},
        }
        positions = [{"代码": "600001", "成本": 25.0, "股数": 1000}]
        oh.overnight_sell_check(positions)

    @mock.patch("stock_analyzer.overnight_holding._em_quote_batch")
    def test_small_loss(self, mock_em):
        """小亏1% → 成本附近出"""
        mock_em.return_value = {
            "600001": {"最新价": 24.75, "涨跌幅": -1.0, "量比": 1.2, "名称": "测试A"},
        }
        positions = [{"代码": "600001", "成本": 25.0, "股数": 1000}]
        oh.overnight_sell_check(positions)

    @mock.patch("stock_analyzer.overnight_holding._em_quote_batch")
    def test_loss_2pct(self, mock_em):
        """亏损2% → 小亏出掉"""
        mock_em.return_value = {
            "600001": {"最新价": 24.5, "涨跌幅": -2.0, "量比": 1.2, "名称": "测试A"},
        }
        positions = [{"代码": "600001", "成本": 25.0, "股数": 1000}]
        oh.overnight_sell_check(positions)

    @mock.patch("stock_analyzer.overnight_holding._em_quote_batch")
    def test_loss_below_minus_2(self, mock_em):
        """亏损< -2% → 无条件止损"""
        mock_em.return_value = {
            "600001": {"最新价": 24.0, "涨跌幅": -4.0, "量比": 1.5, "名称": "测试A"},
        }
        positions = [{"代码": "600001", "成本": 25.0, "股数": 1000}]
        oh.overnight_sell_check(positions)

    @mock.patch("stock_analyzer.overnight_holding._em_quote_batch")
    def test_data_fetch_failed(self, mock_em):
        """数据获取失败"""
        mock_em.return_value = {}
        positions = [{"代码": "600001", "成本": 25.0, "股数": 1000}]
        oh.overnight_sell_check(positions)

    @mock.patch("stock_analyzer.overnight_holding._em_quote_batch")
    def test_empty_positions(self, mock_em):
        """空持仓"""
        oh.overnight_sell_check([])
        mock_em.assert_not_called()


# ════════════════════════════════════════════
# K线降级方案
# ════════════════════════════════════════════


class TestKlineFallbackBatch(unittest.TestCase):
    """K线推算降级"""

    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    @mock.patch("stock_analyzer.overnight_holding._get_float_share")
    def test_normal_fallback(self, mock_float, mock_ck):
        """正常推算"""
        df = _make_kline(30)
        df["成交量"] = 5_000_000
        df["成交额"] = 250_000_000
        mock_ck.return_value = df
        mock_float.return_value = 1e8

        sina_data = {
            "600001": {
                "成交量": 8_000_000,
                "最新价": 25.0,
                "涨跌幅": 4.0,
                "最高": 26.0,
                "最低": 24.5,
                "成交额": 5e8,
                "名称": "测试",
                "昨收": 24.0,
            },
        }
        result = oh._kline_fallback_batch(["600001"], sina_data)
        self.assertIn("600001", result)
        self.assertIn("量比", result["600001"])
        self.assertIn("换手率", result["600001"])
        self.assertIn("流通市值", result["600001"])
        self.assertGreater(result["600001"]["量比"], 0)

    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    def test_missing_sina_data(self, mock_ck):
        """缺新浪数据时跳过"""
        df = _make_kline(30)
        mock_ck.return_value = df

        result = oh._kline_fallback_batch(["600001"], {})
        self.assertNotIn("600001", result)

    @mock.patch("stock_analyzer.overnight_holding.cached_kline")
    def test_not_enough_kline(self, mock_ck):
        """K线数据不足"""
        df = _make_kline(5)
        mock_ck.return_value = df

        sina_data = {
            "600001": {"成交量": 8_000_000, "最新价": 25.0, "名称": "测试"},
        }
        result = oh._kline_fallback_batch(["600001"], sina_data)
        self.assertNotIn("600001", result)


class TestGetMainboardCodes(unittest.TestCase):
    """获取主板股票代码"""

    @mock.patch("stock_analyzer.fetcher._load_stock_name_map")
    def test_returns_60_and_00(self, mock_map):
        """返回60/00开头代码"""
        mock_map.return_value = {
            "600001": "A",
            "600002": "B",
            "000001": "C",
            "000002": "D",
            "300001": "E",
            "688001": "F",
        }
        codes = oh._get_mainboard_codes()
        self.assertIn("600001", codes)
        self.assertIn("000001", codes)
        self.assertNotIn("300001", codes)
        self.assertNotIn("688001", codes)

    @mock.patch("stock_analyzer.fetcher._load_stock_name_map")
    def test_sorted_order(self, mock_map):
        """排序返回"""
        mock_map.return_value = {"600002": "B", "600001": "A"}
        codes = oh._get_mainboard_codes()
        self.assertEqual(codes, ["600001", "600002"])
