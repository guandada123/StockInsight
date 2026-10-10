"""测试 backend/services/portfolio_service.py — 组合 CRUD 与调仓建议

隔离要点（必须遵守）：
    PORTFOLIO_DIR 是模块级常量，默认指向仓库 portfolios/ 目录。
    测试若不 patch 就会写真实组合目录 —— 历史上 test_update_tmp.json
    就是这样泄漏到运行目录的（只在 .gitignore 里被 portfolios/test_*.json 掩盖）。
    因此本文件所有涉及文件读写的用例统一用 portfolio_dir 夹具隔离到 tmp_path。

实时行情（stock_analyzer.fetcher.sina_real_time）依赖外部网络，
统一用 patch 替换，保证测试离线可重复。
"""

import json
from unittest.mock import patch

import pytest

from backend.services import portfolio_service as svc

# ════════════════════════════════════════════════════
# 夹具
# ════════════════════════════════════════════════════


@pytest.fixture
def portfolio_dir(tmp_path, monkeypatch):
    """把组合目录隔离到 tmp_path，避免污染真实 portfolios/"""
    d = tmp_path / "portfolios"
    d.mkdir()
    monkeypatch.setattr(svc, "PORTFOLIO_DIR", str(d))
    return d


def _write(d, name: str, data: dict) -> None:
    (d / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _read(d, name: str) -> dict:
    return json.loads((d / f"{name}.json").read_text(encoding="utf-8"))


# ════════════════════════════════════════════════════
# _build_rebalance_suggestion —— 纯函数，止盈/止损/集中度
# ════════════════════════════════════════════════════


class TestRebalanceSuggestion:
    """调仓建议生成（无副作用，纯逻辑）"""

    def test_empty_holdings_returns_insufficient(self):
        assert "数据不足" in svc._build_rebalance_suggestion([], 1000)

    def test_zero_total_value_returns_insufficient(self):
        holdings = [{"name": "A", "code": "600000", "market_value": 100, "profit_pct": 5.0}]
        assert "数据不足" in svc._build_rebalance_suggestion(holdings, 0)

    def test_negative_total_value_returns_insufficient(self):
        holdings = [{"name": "A", "code": "600000", "market_value": 100, "profit_pct": 5.0}]
        assert "数据不足" in svc._build_rebalance_suggestion(holdings, -1)

    def test_profit_over_10_suggests_take_profit(self):
        holdings = [
            {"name": "贵州茅台", "code": "600519", "market_value": 1000, "profit_pct": 15.0}
        ]
        suggestion = svc._build_rebalance_suggestion(holdings, 10000)

        assert "止盈" in suggestion
        assert "贵州茅台" in suggestion

    def test_loss_under_minus8_suggests_stop_loss(self):
        holdings = [
            {"name": "长电科技", "code": "600584", "market_value": 1000, "profit_pct": -12.0}
        ]
        suggestion = svc._build_rebalance_suggestion(holdings, 10000)

        assert "止损" in suggestion
        assert "长电科技" in suggestion

    def test_concentration_over_40_suggests_diversify(self):
        holdings = [{"name": "招商银行", "code": "600036", "market_value": 5000, "profit_pct": 1.0}]
        suggestion = svc._build_rebalance_suggestion(holdings, 10000)

        assert "集中度" in suggestion

    def test_boundary_exactly_plus10_not_triggered(self):
        """恰好 +10% 不触发止盈（源码为 pnl > 10）"""
        holdings = [{"name": "A", "code": "600000", "market_value": 100, "profit_pct": 10.0}]
        assert "止盈" not in svc._build_rebalance_suggestion(holdings, 10000)

    def test_boundary_exactly_minus8_not_triggered(self):
        """恰好 -8% 不触发止损（源码为 pnl < -8）"""
        holdings = [{"name": "A", "code": "600000", "market_value": 100, "profit_pct": -8.0}]
        assert "止损" not in svc._build_rebalance_suggestion(holdings, 10000)

    def test_boundary_exactly_40pct_not_triggered(self):
        """恰好占 40% 不触发集中度告警（源码为 weight > 40）"""
        holdings = [{"name": "A", "code": "600000", "market_value": 4000, "profit_pct": 0.0}]
        assert "集中度" not in svc._build_rebalance_suggestion(holdings, 10000)

    def test_take_profit_takes_priority_over_concentration(self):
        """盈亏与集中度同时命中时，按 elif 链只输出止盈"""
        holdings = [{"name": "A", "code": "600000", "market_value": 6000, "profit_pct": 20.0}]
        suggestion = svc._build_rebalance_suggestion(holdings, 10000)

        assert "止盈" in suggestion
        assert "集中度" not in suggestion

    def test_multiple_holdings_joined_by_separator(self):
        holdings = [
            {"name": "A", "code": "600000", "market_value": 1000, "profit_pct": 20.0},
            {"name": "B", "code": "600001", "market_value": 1000, "profit_pct": -20.0},
        ]
        suggestion = svc._build_rebalance_suggestion(holdings, 10000)

        assert "；" in suggestion
        assert "止盈" in suggestion
        assert "止损" in suggestion

    def test_all_balanced_returns_reasonable(self):
        holdings = [
            {"name": "A", "code": "600000", "market_value": 3000, "profit_pct": 2.0},
            {"name": "B", "code": "600001", "market_value": 3000, "profit_pct": -3.0},
        ]
        assert "合理" in svc._build_rebalance_suggestion(holdings, 10000)


# ════════════════════════════════════════════════════
# create_portfolio
# ════════════════════════════════════════════════════


class TestCreatePortfolio:
    def test_create_empty(self, portfolio_dir):
        result = svc.create_portfolio("我的组合")

        assert result == {"name": "我的组合", "holdings_count": 0}
        assert (portfolio_dir / "我的组合.json").exists()

    def test_create_with_codes_initializes_zero_positions(self, portfolio_dir):
        result = svc.create_portfolio("组合A", codes="600519,000001")

        assert result["holdings_count"] == 2
        data = _read(portfolio_dir, "组合A")
        assert data["holdings"]["600519"] == {"shares": 0, "cost": 0}
        assert set(data["holdings"]) == {"600519", "000001"}

    def test_create_strips_and_skips_blank_codes(self, portfolio_dir):
        result = svc.create_portfolio("b", codes=" 600519 , , 000001 ,")

        assert result["holdings_count"] == 2

    def test_create_blank_codes_only_yields_empty(self, portfolio_dir):
        result = svc.create_portfolio("b", codes="   ,  ")

        assert result["holdings_count"] == 0

    def test_create_duplicate_raises_file_exists(self, portfolio_dir):
        svc.create_portfolio("dup")

        with pytest.raises(FileExistsError):
            svc.create_portfolio("dup")

    def test_create_records_creation_date(self, portfolio_dir):
        svc.create_portfolio("dated")

        assert "created" in _read(portfolio_dir, "dated")


# ════════════════════════════════════════════════════
# update_portfolio_holding
# ════════════════════════════════════════════════════


class TestUpdatePortfolioHolding:
    def test_add_holding(self, portfolio_dir):
        svc.create_portfolio("p")

        result = svc.update_portfolio_holding("p", "600519", shares=100, cost=1580.0, action="add")

        assert result == {"name": "p", "code": "600519", "action": "add"}
        holding = _read(portfolio_dir, "p")["holdings"]["600519"]
        assert holding["shares"] == 100
        assert holding["cost"] == 1580.0
        assert "updated" in holding

    def test_update_records_portfolio_timestamp(self, portfolio_dir):
        svc.create_portfolio("p")
        svc.update_portfolio_holding("p", "600519", shares=100, cost=10.0)

        assert "updated" in _read(portfolio_dir, "p")

    def test_remove_holding(self, portfolio_dir):
        svc.create_portfolio("p", codes="600519")

        svc.update_portfolio_holding("p", "600519", action="remove")

        assert "600519" not in _read(portfolio_dir, "p")["holdings"]

    def test_remove_absent_code_is_noop(self, portfolio_dir):
        svc.create_portfolio("p")

        result = svc.update_portfolio_holding("p", "999999", action="remove")

        assert result["action"] == "remove"

    def test_backfills_missing_holdings_key(self, portfolio_dir):
        """历史组合文件可能没有 holdings 键，更新时应自动补建"""
        _write(portfolio_dir, "legacy", {"name": "legacy"})

        svc.update_portfolio_holding("legacy", "600519", shares=100, cost=10.0)

        assert _read(portfolio_dir, "legacy")["holdings"]["600519"]["shares"] == 100

    def test_missing_portfolio_raises(self, portfolio_dir):
        with pytest.raises(FileNotFoundError):
            svc.update_portfolio_holding("nope", "600519")


# ════════════════════════════════════════════════════
# delete_portfolio
# ════════════════════════════════════════════════════


class TestDeletePortfolio:
    def test_delete_removes_file(self, portfolio_dir):
        svc.create_portfolio("d")

        assert svc.delete_portfolio("d") == {"deleted": "d"}
        assert not (portfolio_dir / "d.json").exists()

    def test_delete_missing_raises(self, portfolio_dir):
        with pytest.raises(FileNotFoundError):
            svc.delete_portfolio("nope")


# ════════════════════════════════════════════════════
# list_portfolios
# ════════════════════════════════════════════════════


class TestListPortfolios:
    def test_empty_dir(self, portfolio_dir):
        assert svc.list_portfolios() == {"portfolios": []}

    def test_lists_holdings_count_from_holdings_key(self, portfolio_dir):
        _write(portfolio_dir, "a", {"name": "a", "holdings": {"600519": {}, "000001": {}}})

        result = svc.list_portfolios()

        assert result["portfolios"][0]["holdings_count"] == 2
        assert result["portfolios"][0]["name"] == "a"

    def test_supports_legacy_stocks_key(self, portfolio_dir):
        _write(portfolio_dir, "b", {"name": "b", "stocks": {"600036": {}}})

        assert svc.list_portfolios()["portfolios"][0]["holdings_count"] == 1

    def test_corrupt_json_counts_zero_without_raising(self, portfolio_dir):
        (portfolio_dir / "bad.json").write_text("{not-json", encoding="utf-8")

        result = svc.list_portfolios()

        assert result["portfolios"][0]["holdings_count"] == 0

    def test_ignores_non_json_files(self, portfolio_dir):
        (portfolio_dir / "note.txt").write_text("x", encoding="utf-8")

        assert svc.list_portfolios() == {"portfolios": []}

    def test_includes_updated_timestamp(self, portfolio_dir):
        _write(portfolio_dir, "a", {"name": "a", "holdings": {}})

        assert "updated" in svc.list_portfolios()["portfolios"][0]


# ════════════════════════════════════════════════════
# get_portfolio —— 含实时行情
# ════════════════════════════════════════════════════


class TestGetPortfolio:
    def test_missing_raises(self, portfolio_dir):
        with pytest.raises(FileNotFoundError):
            svc.get_portfolio("nope")

    def test_empty_holdings_returns_zeroed_summary(self, portfolio_dir):
        _write(portfolio_dir, "empty", {"name": "empty", "holdings": {}})

        result = svc.get_portfolio("empty")

        assert result["count"] == 0
        assert result["total_value"] == 0
        assert result["holdings"] == []

    def test_computes_market_value_cost_and_weight(self, portfolio_dir):
        _write(
            portfolio_dir,
            "p",
            {
                "name": "p",
                "holdings": {
                    "600519": {"shares": 100, "cost": 1500.0},
                    "000001": {"shares": 1000, "cost": 10.0},
                },
            },
        )
        quotes = {
            "600519": {"名称": "贵州茅台", "最新价": "1600"},
            "000001": {"名称": "平安银行", "最新价": "12"},
        }

        with patch("stock_analyzer.fetcher.sina_real_time", return_value=quotes):
            result = svc.get_portfolio("p")

        # 市值 160000 + 12000 = 172000；成本 150000 + 10000 = 160000
        assert result["total_value"] == 172000.0
        assert result["total_cost"] == 160000.0
        assert result["total_profit"] == 12000.0
        assert result["count"] == 2
        weight = {h["code"]: h["weight_pct"] for h in result["holdings"]}
        assert weight["600519"] == round(160000 / 172000 * 100, 1)

    def test_holdings_sorted_by_profit_pct_desc(self, portfolio_dir):
        _write(
            portfolio_dir,
            "p",
            {
                "name": "p",
                "holdings": {
                    "600519": {"shares": 100, "cost": 1000.0},
                    "000001": {"shares": 100, "cost": 100.0},
                },
            },
        )
        quotes = {
            "600519": {"名称": "A", "最新价": "900"},  # -10%
            "000001": {"名称": "B", "最新价": "200"},  # +100%
        }

        with patch("stock_analyzer.fetcher.sina_real_time", return_value=quotes):
            result = svc.get_portfolio("p")

        assert result["holdings"][0]["code"] == "000001"
        assert result["holdings"][-1]["code"] == "600519"

    def test_zero_cost_does_not_divide_by_zero(self, portfolio_dir):
        """cost=0 时 profit_pct 归零，而不是抛 ZeroDivisionError"""
        _write(
            portfolio_dir, "p", {"name": "p", "holdings": {"600519": {"shares": 100, "cost": 0}}}
        )
        quotes = {"600519": {"名称": "A", "最新价": "10"}}

        with patch("stock_analyzer.fetcher.sina_real_time", return_value=quotes):
            result = svc.get_portfolio("p")

        assert result["holdings"][0]["profit_pct"] == 0

    def test_missing_quote_falls_back_to_code_name(self, portfolio_dir):
        """行情源未返回该代码时，用代码兜底、价格按 0 计"""
        _write(
            portfolio_dir, "p", {"name": "p", "holdings": {"600519": {"shares": 100, "cost": 10.0}}}
        )

        with patch("stock_analyzer.fetcher.sina_real_time", return_value={}):
            result = svc.get_portfolio("p")

        assert result["holdings"][0]["name"] == "600519"
        assert result["total_value"] == 0

    def test_empty_price_string_is_treated_as_zero(self, portfolio_dir):
        """行情返回空字符串价格时按 0 处理（源码 `or 0`）"""
        _write(
            portfolio_dir, "p", {"name": "p", "holdings": {"600519": {"shares": 100, "cost": 10.0}}}
        )
        quotes = {"600519": {"名称": "A", "最新价": ""}}

        with patch("stock_analyzer.fetcher.sina_real_time", return_value=quotes):
            result = svc.get_portfolio("p")

        assert result["holdings"][0]["current_price"] == 0


# ════════════════════════════════════════════════════
# analyze_portfolio
# ════════════════════════════════════════════════════


class TestAnalyzePortfolio:
    def test_missing_raises(self, portfolio_dir):
        with pytest.raises(FileNotFoundError):
            svc.analyze_portfolio("nope")

    def test_empty_holdings(self, portfolio_dir):
        _write(portfolio_dir, "empty", {"name": "empty", "holdings": {}})

        result = svc.analyze_portfolio("empty")

        assert result["holdings"] == []
        assert "空组合" in result["suggestion"]

    def test_returns_suggestion_for_profitable_holding(self, portfolio_dir):
        _write(
            portfolio_dir,
            "p",
            {"name": "p", "holdings": {"600519": {"shares": 100, "cost": 100.0}}},
        )
        quotes = {"600519": {"名称": "茅台", "最新价": "150"}}

        with patch("stock_analyzer.fetcher.sina_real_time", return_value=quotes):
            result = svc.analyze_portfolio("p")

        assert result["name"] == "p"
        assert "止盈" in result["suggestion"]
        assert result["total_value"] == 15000.0

    def test_zero_cost_does_not_divide_by_zero(self, portfolio_dir):
        _write(
            portfolio_dir, "p", {"name": "p", "holdings": {"600519": {"shares": 100, "cost": 0}}}
        )
        quotes = {"600519": {"名称": "A", "最新价": "10"}}

        with patch("stock_analyzer.fetcher.sina_real_time", return_value=quotes):
            result = svc.analyze_portfolio("p")

        assert result["holdings"][0]["profit_pct"] == 0

    def test_supports_legacy_stocks_key(self, portfolio_dir):
        _write(
            portfolio_dir, "p", {"name": "p", "stocks": {"600519": {"shares": 100, "cost": 100.0}}}
        )
        quotes = {"600519": {"名称": "A", "最新价": "110"}}

        with patch("stock_analyzer.fetcher.sina_real_time", return_value=quotes):
            result = svc.analyze_portfolio("p")

        assert len(result["holdings"]) == 1
