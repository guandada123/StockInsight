"""advanced.py 测试（2026-10-18 补齐：原覆盖率 7.94%，全项目最大测试空白）

覆盖策略：
- 纯逻辑函数（_safe_float/_profit_quality_rating）直接断言分支
- 上层信号函数（north_flow_signal/insider_signal/macro_market_signal 等）
  patch 同模块内的取数函数（`advanced.get_xxx`）→ 只测本模块逻辑
- 取数函数 patch `akshare.xxx` → 测正常路径 + 异常兜底路径
- 缓存 _cached_perm：patch _MEM_CACHE/_perm_load/_perm_save/_get_conn 四件套
  （磁盘缓存泄漏会让测试串味，必须一并隔离）
- get_macro_indicators 会写真实 stock_cache.db → patch sqlite3.connect 指向 tmp
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from stock_analyzer import advanced


@pytest.fixture(autouse=True)
def _isolate_cache():
    """隔离全局内存缓存与磁盘永久缓存（防测试互相串味 / 污染真库）"""
    advanced._MEM_CACHE.clear()
    with (
        patch.object(advanced, "_perm_load", return_value=None),
        patch.object(advanced, "_perm_save", return_value=None),
    ):
        yield
    advanced._MEM_CACHE.clear()


# ══════════════════════════════════════════
#  纯函数
# ══════════════════════════════════════════


class TestSafeFloat:
    def test_normal_values(self):
        assert advanced._safe_float(3.5) == 3.5
        assert advanced._safe_float("2.5") == 2.5
        assert advanced._safe_float(0) == 0

    def test_falsy_and_invalid(self):
        assert advanced._safe_float(None) == 0
        assert advanced._safe_float("") == 0
        assert advanced._safe_float("abc") == 0
        assert advanced._safe_float([1]) == 0


class TestProfitQualityRating:
    def test_excellent(self):
        r = advanced._profit_quality_rating({"ROE%": 20, "营收增长%": 25, "净利率%": 22})
        assert r == "优秀"

    def test_good(self):
        r = advanced._profit_quality_rating({"ROE%": 10, "营收增长%": 8, "净利率%": 12})
        assert r == "良好"

    def test_normal(self):
        r = advanced._profit_quality_rating({"ROE%": 5, "营收增长%": 0, "净利率%": 5})
        assert r == "一般"

    def test_needs_attention(self):
        r = advanced._profit_quality_rating({"ROE%": 2, "营收增长%": -10, "净利率%": 1})
        assert r == "需关注"

    def test_empty_dict_defaults(self):
        # 全缺省 → 0/0/0，score=0 → 一般
        assert advanced._profit_quality_rating({}) == "一般"


# ══════════════════════════════════════════
#  1. 龙虎榜
# ══════════════════════════════════════════


class TestLhb:
    def _df(self):
        return pd.DataFrame(
            {
                "代码": ["600001", "600002", "600003"],
                "名称": ["A", "B", "C"],
                "净买额": [3e8, -2e8, 1e8],
                "涨幅": [10.0, -5.0, 3.0],
                "上榜原因": ["涨停", "跌停", "异动"],
            }
        )

    def test_analyze_today_normal(self):
        with patch.object(advanced, "get_lhb_detail", return_value=self._df()):
            r = advanced.analyze_lhb_today()
        assert r["上榜数量"] == 3
        assert r["净买入TOP10"][0]["代码"] == "600001"
        assert r["净卖出TOP10"][0]["代码"] == "600002"
        assert "分析时间" in r

    def test_analyze_today_empty(self):
        with patch.object(advanced, "get_lhb_detail", return_value=pd.DataFrame()):
            r = advanced.analyze_lhb_today()
        assert r == {"error": "龙虎榜数据获取失败"}

    def test_analyze_today_without_net_column(self):
        df = pd.DataFrame({"代码": ["600001"], "名称": ["A"]})
        with patch.object(advanced, "get_lhb_detail", return_value=df):
            r = advanced.analyze_lhb_today()
        assert r["上榜数量"] == 1
        assert "净买入TOP10" not in r

    def test_get_lhb_detail_ok(self):
        fake = self._df()
        with patch("akshare.stock_lhb_detail_em", return_value=fake):
            out = advanced.get_lhb_detail("20261017")
        assert len(out) == 3

    def test_get_lhb_detail_exception_returns_empty(self):
        with patch("akshare.stock_lhb_detail_em", side_effect=RuntimeError("net")):
            out = advanced.get_lhb_detail("20261017")
        assert out.empty

    def test_get_lhb_stock_detail_exception_returns_empty(self):
        with patch("akshare.stock_lhb_stock_detail_date_em", side_effect=RuntimeError("x")):
            out = advanced.get_lhb_stock_detail("600001", "20261017")
        assert out.empty


# ══════════════════════════════════════════
#  2. 北向资金
# ══════════════════════════════════════════


class TestNorthFlow:
    def test_signal_normal(self):
        df = pd.DataFrame({"名称": ["沪股通", "深股通"], "净买额": [5e8, -3e8]})
        with patch.object(advanced, "get_north_flow_summary", return_value=df):
            r = advanced.north_flow_signal()
        assert r["沪股通"]["净买额(亿)"] == 5.0
        assert r["深股通"]["净买额(亿)"] == -3.0

    def test_signal_zero_net(self):
        df = pd.DataFrame({"名称": ["沪股通"], "净买额": [0]})
        with patch.object(advanced, "get_north_flow_summary", return_value=df):
            r = advanced.north_flow_signal()
        assert r["沪股通"]["净买额(亿)"] == 0

    def test_signal_empty(self):
        with patch.object(advanced, "get_north_flow_summary", return_value=pd.DataFrame()):
            r = advanced.north_flow_signal()
        assert r == {"error": "北向资金数据获取失败"}

    def test_summary_exception_returns_empty(self):
        with patch("akshare.stock_hsgt_fund_flow_summary_em", side_effect=RuntimeError("x")):
            assert advanced.get_north_flow_summary().empty

    def test_hold_stock_concats(self):
        sh = pd.DataFrame({"代码": ["600001"], "名称": ["A"]})
        sz = pd.DataFrame({"代码": ["000001"], "名称": ["B"]})
        with patch("akshare.stock_hsgt_hold_stock_em", side_effect=[sh, sz]):
            out = advanced.get_north_hold_stock()
        assert len(out) == 2

    def test_hold_stock_one_none(self):
        sh = pd.DataFrame({"代码": ["600001"]})
        with patch("akshare.stock_hsgt_hold_stock_em", side_effect=[sh, None]):
            out = advanced.get_north_hold_stock()
        assert len(out) == 1

    def test_hold_stock_exception_returns_empty(self):
        with patch("akshare.stock_hsgt_hold_stock_em", side_effect=RuntimeError("x")):
            assert advanced.get_north_hold_stock().empty

    def test_trend_tail(self):
        df = pd.DataFrame({"日期": list(range(100)), "净买额": list(range(100))})
        with patch("akshare.stock_hsgt_hist_em", return_value=df):
            out = advanced.get_north_flow_trend(days=5)
        assert len(out) == 5
        assert out.iloc[-1]["日期"] == 99

    def test_trend_exception_returns_empty(self):
        with patch("akshare.stock_hsgt_hist_em", side_effect=RuntimeError("x")):
            assert advanced.get_north_flow_trend().empty


# ══════════════════════════════════════════
#  3. 融资融券
# ══════════════════════════════════════════


class TestMargin:
    def test_stock_detail_filters_code(self):
        df = pd.DataFrame({"标的代码": ["600001", "600002"], "融资余额": [1, 2]})
        with patch("akshare.stock_margin_detail_sse", return_value=df):
            out = advanced.get_margin_stock_detail("600001")
        assert len(out) == 1
        assert out.iloc[0]["标的代码"] == "600001"

    def test_stock_detail_code_zfill(self):
        # 输入 '1' 应零填充为 '000001' 后匹配
        df = pd.DataFrame({"标的代码": ["000001"], "融资余额": [1]})
        with patch("akshare.stock_margin_detail_sse", return_value=df):
            out = advanced.get_margin_stock_detail("1")
        assert len(out) == 1

    def test_stock_detail_exception_returns_empty(self):
        with patch("akshare.stock_margin_detail_sse", side_effect=RuntimeError("x")):
            assert advanced.get_margin_stock_detail("600001").empty

    def test_summary_both_markets(self):
        sh = pd.DataFrame([[None, 100, 5]])
        sz = pd.DataFrame([[None, 200, 7]])
        with (
            patch("akshare.macro_china_market_margin_sh", return_value=sh),
            patch("akshare.macro_china_market_margin_sz", return_value=sz),
        ):
            r = advanced.get_margin_summary()
        assert r["沪市"]["融资余额(亿)"] == 100.0
        assert r["深市"]["融券余额(亿)"] == 7.0

    def test_summary_single_column(self):
        sh = pd.DataFrame([[None, 100]])
        sz = pd.DataFrame([[None, 200]])
        with (
            patch("akshare.macro_china_market_margin_sh", return_value=sh),
            patch("akshare.macro_china_market_margin_sz", return_value=sz),
        ):
            r = advanced.get_margin_summary()
        assert r["沪市"]["融券余额(亿)"] == 0

    def test_summary_exception_returns_empty_dict(self):
        with patch("akshare.macro_china_market_margin_sh", side_effect=RuntimeError("x")):
            assert advanced.get_margin_summary() == {}


# ══════════════════════════════════════════
#  4. 高管增减持
# ══════════════════════════════════════════


class TestInsider:
    def test_signal_net_buy(self):
        df = pd.DataFrame({"变动数量": [1000, 500]})
        with patch.object(advanced, "get_insider_trades", return_value=df):
            r = advanced.insider_signal("600001")
        assert r["signal"] == "净增持"
        assert r["net_shares"] == 1500
        assert r["records"] == 2

    def test_signal_net_sell(self):
        df = pd.DataFrame({"变动数量": [-1000, 200]})
        with patch.object(advanced, "get_insider_trades", return_value=df):
            r = advanced.insider_signal("600001")
        assert r["signal"] == "净减持"
        assert r["net_shares"] == -800

    def test_signal_zero_sum(self):
        df = pd.DataFrame({"变动数量": [100, -100]})
        with patch.object(advanced, "get_insider_trades", return_value=df):
            r = advanced.insider_signal("600001")
        assert r["signal"] == "无数据"

    def test_signal_empty(self):
        with patch.object(advanced, "get_insider_trades", return_value=pd.DataFrame()):
            r = advanced.insider_signal("600001")
        assert r == {"signal": "无数据", "net_shares": 0}

    def test_signal_no_quantity_column(self):
        df = pd.DataFrame({"姓名": ["张三"]})
        with patch.object(advanced, "get_insider_trades", return_value=df):
            r = advanced.insider_signal("600001")
        assert r["signal"] == "无数据"

    def test_trades_with_code(self):
        df = pd.DataFrame({"变动数量": [1]})
        with patch("akshare.stock_hold_management_detail_em", return_value=df) as m:
            out = advanced.get_insider_trades("600001")
        assert len(out) == 1
        m.assert_called_once_with(symbol="600001")

    def test_trades_market_wide_filters_date(self):
        df = pd.DataFrame({"变动日期": ["2099-01-01", "1999-01-01"], "变动数量": [1, 2]})
        with patch("akshare.stock_hold_management_detail_em", return_value=df):
            out = advanced.get_insider_trades()
        assert len(out) == 1

    def test_trades_exception_returns_empty(self):
        with patch("akshare.stock_hold_management_detail_em", side_effect=RuntimeError("x")):
            assert advanced.get_insider_trades().empty


# ══════════════════════════════════════════
#  5. 机构调研
# ══════════════════════════════════════════


class TestInstitution:
    def test_most_visited_ranks(self):
        df = pd.DataFrame(
            {
                "证券代码": ["600001", "600001", "600002", "600003", "600003", "600003"],
                "证券简称": ["A", "A", "B", "C", "C", "C"],
            }
        )
        with patch.object(advanced, "get_institution_visits", return_value=df):
            out = advanced.most_visited_stocks()
        assert out.iloc[0]["证券代码"] == "600003"
        assert out.iloc[0]["调研次数"] == 3

    def test_most_visited_empty(self):
        with patch.object(advanced, "get_institution_visits", return_value=pd.DataFrame()):
            assert advanced.most_visited_stocks().empty

    def test_most_visited_missing_code_column(self):
        df = pd.DataFrame({"其他列": [1]})
        with patch.object(advanced, "get_institution_visits", return_value=df):
            assert advanced.most_visited_stocks().empty

    def test_visits_filter_by_date(self):
        df = pd.DataFrame({"调研日期": ["2099-01-01", "1999-01-01"]})
        with patch("akshare.stock_jgdy_tj_em", return_value=df):
            out = advanced.get_institution_visits(days=30)
        assert len(out) == 1

    def test_visits_with_code(self):
        df = pd.DataFrame({"调研日期": ["2099-01-01"]})
        with patch("akshare.stock_jgdy_detail_em", return_value=df):
            out = advanced.get_institution_visits("600001")
        assert len(out) == 1

    def test_visits_exception_returns_empty(self):
        with patch("akshare.stock_jgdy_tj_em", side_effect=RuntimeError("x")):
            assert advanced.get_institution_visits().empty


# ══════════════════════════════════════════
#  6. 财报深度拆解
# ══════════════════════════════════════════


class TestFinancialDeep:
    def test_head_four_periods(self):
        long_df = pd.DataFrame({"v": list(range(10))})
        with (
            patch("akshare.stock_balance_sheet_by_report_em", return_value=long_df),
            patch("akshare.stock_profit_sheet_by_report_em", return_value=long_df),
            patch("akshare.stock_financial_abstract", return_value=long_df),
        ):
            r = advanced.get_financial_deep("600001")
        assert set(r) == {"资产负债表", "利润表", "财务摘要"}
        assert all(len(v) == 4 for v in r.values())

    def test_partial_failures_kept(self):
        long_df = pd.DataFrame({"v": [1, 2]})
        with (
            patch("akshare.stock_balance_sheet_by_report_em", side_effect=RuntimeError("x")),
            patch("akshare.stock_profit_sheet_by_report_em", return_value=long_df),
            patch("akshare.stock_financial_abstract", side_effect=RuntimeError("y")),
        ):
            r = advanced.get_financial_deep("600001")
        assert set(r) == {"利润表"}

    def test_all_fail_returns_empty_dict(self):
        with (
            patch("akshare.stock_balance_sheet_by_report_em", side_effect=RuntimeError("x")),
            patch("akshare.stock_profit_sheet_by_report_em", side_effect=RuntimeError("x")),
            patch("akshare.stock_financial_abstract", side_effect=RuntimeError("x")),
        ):
            assert advanced.get_financial_deep("600001") == {}


class TestProfitQuality:
    def test_normal_full_data(self):
        abstract = pd.DataFrame(
            [
                {
                    "营业总收入": 1e9,
                    "归母净利润": 2e8,
                    "净资产收益率": 18,
                    "销售毛利率": 30,
                }
            ]
        )
        income = pd.DataFrame([{"营业总收入": 1e9}, {"营业总收入": 0.8e9}])
        bs = pd.DataFrame([{"资产负债率": 45.5}])
        deep = {"财务摘要": abstract, "利润表": income, "资产负债表": bs}
        with patch.object(advanced, "get_financial_deep", return_value=deep):
            r = advanced.analyze_profit_quality("600001")
        assert r["营收(亿)"] == 10.0
        assert r["净利润(亿)"] == 2.0
        assert r["净利率%"] == 20.0
        assert r["ROE%"] == 18
        assert r["毛利率%"] == 30
        assert r["营收增长%"] == 25.0
        assert r["资产负债率%"] == 45.5
        assert r["评价"] in {"优秀", "良好", "一般", "需关注"}

    def test_empty_deep(self):
        with patch.object(advanced, "get_financial_deep", return_value={}):
            assert advanced.analyze_profit_quality("600001") == {"error": "财报数据获取失败"}

    def test_zero_revenue_no_div_by_zero(self):
        abstract = pd.DataFrame([{"营业总收入": 0, "归母净利润": 1e8}])
        with patch.object(advanced, "get_financial_deep", return_value={"财务摘要": abstract}):
            r = advanced.analyze_profit_quality("600001")
        assert r["净利率%"] == 0

    def test_single_period_no_growth(self):
        income = pd.DataFrame([{"营业总收入": 1e9}])
        abstract = pd.DataFrame([{"营业总收入": 1e9, "归母净利润": 1e8}])
        with patch.object(
            advanced, "get_financial_deep", return_value={"财务摘要": abstract, "利润表": income}
        ):
            r = advanced.analyze_profit_quality("600001")
        assert "营收增长%" not in r


# ══════════════════════════════════════════
#  7. 宏观
# ══════════════════════════════════════════


class TestMacro:
    def test_signal_expansion_and_liquidity(self):
        ind = {"制造业PMI": 52, "CPI同比%": 1.5, "M2同比%": 13}
        with patch.object(advanced, "get_macro_indicators", return_value=ind):
            r = advanced.macro_market_signal()
        assert "PMI扩张→经济向好" in r["信号"]
        assert "M2高增→流动性充裕" in r["信号"]
        assert r["整体"] == "偏多"
        assert r["数据"] is ind

    def test_signal_contraction_and_tight(self):
        ind = {"制造业PMI": 48, "CPI同比%": 4, "M2同比%": 7}
        with patch.object(advanced, "get_macro_indicators", return_value=ind):
            r = advanced.macro_market_signal()
        assert "PMI收缩→经济承压" in r["信号"]
        assert "CPI高位→通胀压力" in r["信号"]
        assert "M2偏低→流动性收紧" in r["信号"]

    def test_signal_deflation(self):
        ind = {"制造业PMI": 50, "CPI同比%": -1, "M2同比%": 10}
        with patch.object(advanced, "get_macro_indicators", return_value=ind):
            r = advanced.macro_market_signal()
        assert "CPI为负→通缩风险" in r["信号"]

    def test_signal_empty_data(self):
        with patch.object(advanced, "get_macro_indicators", return_value={}):
            assert advanced.macro_market_signal() == {"error": "宏观数据获取失败"}

    def test_signal_defaults_when_keys_missing(self):
        with patch.object(advanced, "get_macro_indicators", return_value={"更新时间": "x"}):
            r = advanced.macro_market_signal()
        # 默认 PMI=50/CPI=2/M2=8 → 8 不 > 12 也不算 < 8 → 无 M2 信号
        assert r["信号"] == []

    def test_fetch_indicators_all_sources(self):
        pmi = pd.DataFrame([[None, 51.2]])
        cpi = pd.DataFrame([[None, 1.8]])
        sf = pd.DataFrame([[None, 3000]])
        m2 = pd.DataFrame([[None, 9.5]])
        with (
            patch("akshare.index_pmi_man_cx", return_value=pmi),
            patch("akshare.macro_china_cpi_yearly", return_value=cpi),
            patch("akshare.macro_china_new_financial_credit", return_value=sf),
            patch("akshare.macro_china_money_supply", return_value=m2),
        ):
            r = advanced._fetch_macro_indicators()
        assert r["制造业PMI"] == 51.2
        assert r["CPI同比%"] == 1.8
        assert r["社融增量(亿)"] == 3000.0
        assert r["M2同比%"] == 9.5
        assert "更新时间" in r

    def test_fetch_indicators_each_source_fails(self):
        with (
            patch("akshare.index_pmi_man_cx", side_effect=RuntimeError("x")),
            patch("akshare.macro_china_cpi_yearly", side_effect=RuntimeError("x")),
            patch("akshare.macro_china_new_financial_credit", side_effect=RuntimeError("x")),
            patch("akshare.macro_china_money_supply", side_effect=RuntimeError("x")),
        ):
            r = advanced._fetch_macro_indicators()
        assert r["制造业PMI"] is None
        assert r["M2同比%"] is None

    def test_indicators_cache_hit_via_db(self, tmp_path, monkeypatch):
        """缓存命中：不调用 _fetch_macro_indicators"""
        import sqlite3
        from datetime import datetime

        db = tmp_path / "cache.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE macro_cache (key TEXT PRIMARY KEY, value TEXT, ts TEXT)")
        conn.execute(
            "INSERT INTO macro_cache VALUES (?,?,?)",
            ("macro_indicators", '{"制造业PMI": 51}', datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()

        real_connect = sqlite3.connect
        monkeypatch.setattr(
            "sqlite3.connect",
            lambda *a, **k: real_connect(db) if a[0] == "stock_cache.db" else real_connect(*a, **k),
        )
        with patch.object(advanced, "_fetch_macro_indicators") as m:
            r = advanced.get_macro_indicators()
        assert r["制造业PMI"] == 51
        m.assert_not_called()

    def test_indicators_cache_miss_fetches_and_writes(self, tmp_path, monkeypatch):
        """缓存未命中：调取数函数并落库"""
        import sqlite3

        db = tmp_path / "cache.db"
        real_connect = sqlite3.connect
        monkeypatch.setattr(
            "sqlite3.connect",
            lambda *a, **k: real_connect(db) if a[0] == "stock_cache.db" else real_connect(*a, **k),
        )
        with patch.object(
            advanced, "_fetch_macro_indicators", return_value={"制造业PMI": 50.5}
        ) as m:
            r = advanced.get_macro_indicators()
        assert r["制造业PMI"] == 50.5
        m.assert_called_once()
        # 验证确实写入了库
        conn = real_connect(db)
        row = conn.execute("SELECT value FROM macro_cache WHERE key='macro_indicators'").fetchone()
        conn.close()
        assert row is not None and "50.5" in row[0]


# ══════════════════════════════════════════
#  缓存包装 _cached_perm
# ══════════════════════════════════════════


class TestCachedPerm:
    def test_mem_cache_hit(self):
        advanced._MEM_CACHE["t:k"] = (__import__("time").time(), "cached-value")
        fetch = MagicMock(return_value="fresh")
        out = advanced._cached_perm("t", "k", fetch, ttl_seconds=3600)
        assert out == "cached-value"
        fetch.assert_not_called()

    def test_disk_cache_fresh_hit(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (__import__("time").time(),)
        with (
            patch.object(advanced, "_perm_load", return_value="disk-value"),
            patch("stock_analyzer.cache._get_conn", return_value=conn),
        ):
            fetch = MagicMock(return_value="fresh")
            out = advanced._cached_perm("t", "k", fetch, ttl_seconds=3600)
        assert out == "disk-value"
        fetch.assert_not_called()

    def test_disk_cache_stale_refetches(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (0.0,)  # 1970 → 必然过期
        with (
            patch.object(advanced, "_perm_load", return_value="stale-value"),
            patch.object(advanced, "_perm_save") as save,
            patch("stock_analyzer.cache._get_conn", return_value=conn),
        ):
            out = advanced._cached_perm("t", "k", lambda: "fresh", ttl_seconds=60)
        assert out == "fresh"
        save.assert_called_once()

    def test_fetch_failure_falls_back_to_stored(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (0.0,)
        with (
            patch.object(advanced, "_perm_load", return_value="stale-value"),
            patch("stock_analyzer.cache._get_conn", return_value=conn),
        ):
            out = advanced._cached_perm("t", "k", MagicMock(side_effect=RuntimeError("x")), 60)
        assert out == "stale-value"

    def test_fetch_failure_no_stored_returns_none(self):
        with patch.object(advanced, "_perm_load", return_value=None):
            out = advanced._cached_perm("t", "k", MagicMock(side_effect=RuntimeError("x")), 60)
        assert out is None
