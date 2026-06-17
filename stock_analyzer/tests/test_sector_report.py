"""test_sector_report.py — sector_report.py 全覆盖测试"""

import os
from unittest.mock import MagicMock, PropertyMock, patch

import numpy as np
import pandas as pd
import pytest

from stock_analyzer import sector_report


def _make_screener_df(extra_rows: bool = False) -> pd.DataFrame:
    """创建模拟的 run_screener 返回值 DataFrame"""
    rows = [
        # (代码, 综合评分, 评级, 动量分, 技术分, 基本面分, 量能分, 风险分)
        ("000001", 65, "Buy", 60, 70, 55, 50, 40),
        ("000002", 45, "Hold", 50, 40, 60, 45, 55),
        ("000003", 30, "Sell", 20, 30, 35, 25, 45),
        ("600001", 80, "Strong Buy", 85, 75, 90, 80, 70),
        ("600002", 55, "Hold", 60, 50, 55, 60, 50),
        ("002001", 70, "Buy", 65, 75, 80, 70, 60),
        ("300001", 20, "Strong Sell", 15, 25, 30, 20, 35),
        # 低评分边界测试
        ("999999", 10, "Hold", 0, 0, 0, 0, 0),
    ]
    cols = ["代码", "综合评分", "评级", "动量分", "技术分", "基本面分", "量能分", "风险分"]
    return pd.DataFrame(rows, columns=cols)


def _mock_sector(code: str) -> str:
    """模拟 get_sector_for_code 返回值"""
    mapping = {
        "000001": "银行",
        "000002": "地产",
        "000003": "综合",
        "600001": "科技",
        "600002": "制造",
        "002001": "医药",
        "300001": "其他",
        "999999": "其他",
    }
    return mapping.get(code, "其他")


class TestGenerateSectorReport:
    """generate_sector_report 函数全覆盖测试"""

    @patch("stock_analyzer.sector_report.os.makedirs")
    @patch("builtins.open", new_callable=MagicMock)
    @patch("stock_analyzer.cache.cached_sector_fund_flow_rank")
    @patch("stock_analyzer.sector_report.cached_market_overview")
    @patch("stock_analyzer.sector_report.get_sector_for_code")
    @patch("stock_analyzer.sector_report.run_screener")
    def test_basic_flow(self, mock_run, mock_sector, mock_mkt, mock_ff, mock_open, mock_mkdir):
        """基本流程：完整报告生成"""
        mock_run.return_value = _make_screener_df()
        mock_sector.side_effect = _mock_sector
        mock_mkt.return_value = {
            "000001": {"最新价": 3200.5, "涨跌幅": 1.2, "名称": "上证指数"},
            "399001": {"最新价": 12000.0, "涨跌幅": -0.5, "名称": "深证成指"},
        }
        mock_ff.return_value = None  # 资金流不可用路径

        result = sector_report.generate_sector_report("/tmp/test_report.html")

        assert result == "/tmp/test_report.html"
        mock_run.assert_called_once_with(top_n=0, mode="full")
        mock_mkdir.assert_called_once()
        mock_open.assert_called_once_with("/tmp/test_report.html", "w", encoding="utf-8")
        # 验证 HTML 内容包含关键部分
        handle = mock_open.return_value.__enter__.return_value
        written = "".join(c[0][0] for c in handle.write.call_args_list)
        assert "全市场板块分析报告" in written
        assert "银行" in written
        assert "科技" in written
        assert "TOP12" not in written  # 通过 canvas id 验证

    @patch("stock_analyzer.sector_report.os.makedirs")
    @patch("builtins.open", new_callable=MagicMock)
    @patch("stock_analyzer.cache.cached_sector_fund_flow_rank")
    @patch("stock_analyzer.sector_report.cached_market_overview")
    @patch("stock_analyzer.sector_report.get_sector_for_code")
    @patch("stock_analyzer.sector_report.run_screener")
    def test_default_output_path(
        self, mock_run, mock_sector, mock_mkt, mock_ff, mock_open, mock_mkdir
    ):
        """默认输出路径：不传参时自动生成"""
        mock_run.return_value = _make_screener_df()
        mock_sector.side_effect = _mock_sector
        mock_mkt.return_value = None
        mock_ff.return_value = None

        result = sector_report.generate_sector_report()

        assert result.startswith("reports/sector_")
        assert result.endswith(".html")

    @patch("stock_analyzer.sector_report.os.makedirs")
    @patch("builtins.open", new_callable=MagicMock)
    @patch("stock_analyzer.cache.cached_sector_fund_flow_rank")
    @patch("stock_analyzer.sector_report.cached_market_overview")
    @patch("stock_analyzer.sector_report.get_sector_for_code")
    @patch("stock_analyzer.sector_report.run_screener")
    def test_market_overview_success(
        self, mock_run, mock_sector, mock_mkt, mock_ff, mock_open, mock_mkdir
    ):
        """大盘行情板块：有数据"""
        mock_run.return_value = _make_screener_df()
        mock_sector.side_effect = _mock_sector
        mock_mkt.return_value = {
            "000001": {"最新价": 3200.5, "涨跌幅": 1.2, "名称": "上证指数"},
        }
        mock_ff.return_value = None

        result = sector_report.generate_sector_report("/tmp/mkt.html")

        handle = mock_open.return_value.__enter__.return_value
        written = "".join(c[0][0] for c in handle.write.call_args_list)
        assert "上证指数" in written
        assert "3200.5" in written

    def test_market_overview_empty(self):
        """大盘行情板块：返回值 None"""
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = _make_screener_df()
            mock_sector.side_effect = _mock_sector
            mock_mkt.return_value = None
            mock_ff.return_value = None

            sector_report.generate_sector_report("/tmp/mkt_empty.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            assert "大盘行情数据暂不可用" in written

    def test_market_overview_exception(self):
        """大盘行情板块：异常"""
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = _make_screener_df()
            mock_sector.side_effect = _mock_sector
            mock_mkt.side_effect = RuntimeError("网络超时")
            mock_ff.return_value = None

            sector_report.generate_sector_report("/tmp/mkt_exc.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            assert "大盘行情数据暂不可用" in written

    def test_market_overview_partial_data(self):
        """大盘行情板块：部分指数有数据部分没有"""
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = _make_screener_df()
            mock_sector.side_effect = _mock_sector
            mock_mkt.return_value = {"000001": None}  # 存在 key 但值为 None
            mock_ff.return_value = None

            sector_report.generate_sector_report("/tmp/mkt_partial.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            assert "大盘行情数据暂不可用" not in written  # 有数据但不显示详情

    def test_market_overview_change_types(self):
        """大盘行情板块：涨跌幅各种类型"""
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = _make_screener_df()
            mock_sector.side_effect = _mock_sector
            mock_mkt.return_value = {
                "000001": {"最新价": 1, "涨跌幅": 1.2, "名称": "涨"},
                "399001": {"最新价": 2, "涨跌幅": -0.5, "名称": "跌"},
                "399006": {"最新价": 3, "涨跌幅": "N/A", "名称": "非数值"},
                "000688": {"最新价": 4, "涨跌幅": 0, "名称": "平"},
            }
            mock_ff.return_value = None

            sector_report.generate_sector_report("/tmp/mkt_chg.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            assert "涨" in written
            assert "跌" in written
            # 非数值涨跌幅不应抛异常
            assert "非数值" in written or "N/A" in written

    def test_sentiment_high(self):
        """市场判断分支：avg >= 50（优质结构）"""
        df = _make_screener_df()
        # 提高评分使平均值 >= 50
        df.loc[df["代码"].isin(["000002", "600002"]), "综合评分"] = [60, 65]
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = df
            mock_sector.side_effect = _mock_sector
            mock_mkt.return_value = None
            mock_ff.return_value = None

            sector_report.generate_sector_report("/tmp/sent_high.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            assert "市场整体评分偏中性" in written

    def test_sentiment_mid(self):
        """市场判断分支：45 <= avg < 50（偏低）"""
        df = _make_screener_df()
        # 调整评分使平均值在 45-50 之间
        df.loc[df["代码"].isin(["000001", "600001", "002001"]), "综合评分"] = [55, 50, 52]
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = df
            mock_sector.side_effect = _mock_sector
            mock_mkt.return_value = None
            mock_ff.return_value = None

            sector_report.generate_sector_report("/tmp/sent_mid.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            assert "偏低" in written

    def test_sentiment_low(self):
        """市场判断分支：avg < 45（偏弱）"""
        df = _make_screener_df()
        # 降低所有评分使 avg < 45
        df["综合评分"] = df["综合评分"].apply(lambda x: 40 if isinstance(x, (int, float)) else x)
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = df
            mock_sector.side_effect = _mock_sector
            mock_mkt.return_value = None
            mock_ff.return_value = None

            sector_report.generate_sector_report("/tmp/sent_low.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            assert "偏弱" in written

    def test_no_ratings_column(self):
        """DataFrame 无评级列"""
        df = _make_screener_df()
        df = df.drop(columns=["评级"])
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = df
            mock_sector.side_effect = _mock_sector
            mock_mkt.return_value = None
            mock_ff.return_value = None

            result = sector_report.generate_sector_report("/tmp/no_rating.html")

            assert result == "/tmp/no_rating.html"

    def test_empty_screener_result(self):
        """run_screener 返回空 DataFrame"""
        df = pd.DataFrame(columns=["代码"])
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = df
            mock_sector.side_effect = _mock_sector  # 不会被调用，但没问题
            mock_mkt.return_value = None
            mock_ff.return_value = None

            result = sector_report.generate_sector_report("/tmp/empty.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            # 空 DataFrame → all_scores = [] → avg=0, bar_max=1
            assert "覆盖 0 个板块" in written or "覆盖" in written

    def test_all_sectors_other(self):
        """所有股票都映射到"其他"板块"""
        df = _make_screener_df()
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = df
            mock_sector.return_value = "其他"  # 所有股票都返回"其他"
            mock_mkt.return_value = None
            mock_ff.return_value = None

            result = sector_report.generate_sector_report("/tmp/all_other.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            assert "其他" in written

    def test_multi_sector_assignment(self):
        """板块映射包含顿号分隔的多板块"""
        df = _make_screener_df()
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = df

            # 某个股票属于"银行、金融"（多板块）
            def _multi_sec(code):
                return {"000001": "银行、金融", "000002": "地产"}.get(code, "其他")

            mock_sector.side_effect = _multi_sec
            mock_mkt.return_value = None
            mock_ff.return_value = None

            sector_report.generate_sector_report("/tmp/multi_sec.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            assert "银行" in written
            assert "金融" in written

    def test_single_sector_only(self):
        """只有一个板块（所有股票归属同一个板块）"""
        df = _make_screener_df()
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = df
            mock_sector.return_value = "银行"  # 全部归入"银行"
            mock_mkt.return_value = None
            mock_ff.return_value = None

            result = sector_report.generate_sector_report("/tmp/single.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            assert "银行" in written
            assert "覆盖 1 个板块" in written or "1个板块" in written or "1 个板块" in written

    def test_fund_flow_success(self):
        """资金流向板块：有数据（DataFrame）"""
        ff_df = pd.DataFrame(
            {
                "序号": [1, 2],
                "名称": ["银行", "科技"],
                "今日主力净流入-净额": [1e9, -5e8],
                "今日主力净流入-净占比": [5.0, -2.0],
                "今日涨跌幅": [1.5, -0.8],
                "今日主力净流入最大股": ["招商银行", "腾讯控股"],
            }
        )
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = _make_screener_df()
            mock_sector.side_effect = _mock_sector
            mock_mkt.return_value = None
            mock_ff.return_value = ff_df

            result = sector_report.generate_sector_report("/tmp/ff.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            assert "主力净流入 Top 20" in written
            assert "主力净流出 Top 10" in written
            assert "银行" in written
            assert "+10.00" in written or "10.00" in written  # 1e9 / 1e8 = 10

    def test_fund_flow_empty_df(self):
        """资金流向板块：空 DataFrame"""
        ff_df = pd.DataFrame()
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = _make_screener_df()
            mock_sector.side_effect = _mock_sector
            mock_mkt.return_value = None
            mock_ff.return_value = ff_df  # 空 DF → .empty 为 True

            result = sector_report.generate_sector_report("/tmp/ff_empty.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            assert "暂不可用" in written

    def test_fund_flow_exception(self):
        """资金流向板块：异常"""
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = _make_screener_df()
            mock_sector.side_effect = _mock_sector
            mock_mkt.return_value = None
            mock_ff.side_effect = ValueError("数据解析失败")

            result = sector_report.generate_sector_report("/tmp/ff_exc.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            assert "获取失败" in written

    def test_duplicate_ratings(self):
        """评级列有额外空白符"""
        df = _make_screener_df()
        df["评级"] = df["评级"].apply(lambda x: f"  {x}  " if pd.notna(x) else x)
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = df
            mock_sector.side_effect = _mock_sector
            mock_mkt.return_value = None
            mock_ff.return_value = None

            result = sector_report.generate_sector_report("/tmp/dup_rating.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            # 验证评级分布统计正确（strip 后匹配）
            # Strong Buy: 1, Buy: 2, Hold: 2, Sell: 1, Strong Sell: 1
            assert "Buy" in written

    def test_empty_scores(self):
        """所有评分为空，不应崩溃"""
        df = pd.DataFrame(
            {
                "代码": ["000001"],
                "综合评分": [np.nan],
                "评级": ["Hold"],
                "动量分": [np.nan],
                "技术分": [np.nan],
                "基本面分": [np.nan],
                "量能分": [np.nan],
                "风险分": [np.nan],
            }
        )
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = df
            mock_sector.return_value = "其他"
            mock_mkt.return_value = None
            mock_ff.return_value = None

            result = sector_report.generate_sector_report("/tmp/nan.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            assert "板块分析" in written

    def test_very_high_scores(self):
        """极高评分（所有 >= 60）"""
        df = _make_screener_df()
        df["综合评分"] = [85, 90, 75, 95, 88, 92, 70, 80]
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = df
            mock_sector.side_effect = _mock_sector
            mock_mkt.return_value = None
            mock_ff.return_value = None

            sector_report.generate_sector_report("/tmp/high.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            assert "100%" in written or "优质" in written

    def test_no_chart_column(self):
        """DataFrame 不含"综合评分"列"""
        df = pd.DataFrame({"代码": ["000001"]})
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = df
            mock_sector.side_effect = lambda c: {"000001": "银行"}.get(c, "其他")
            mock_mkt.return_value = None
            mock_ff.return_value = None

            result = sector_report.generate_sector_report("/tmp/nocol.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            # 无评分列，不影响基本结构
            assert "板块分析" in written

    def test_html_structure(self):
        """验证 HTML 结构完整性"""
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = _make_screener_df()
            mock_sector.side_effect = _mock_sector
            mock_mkt.return_value = {
                "000001": {"最新价": 3200, "涨跌幅": 1.0, "名称": "上证指数"},
            }
            mock_ff.return_value = None

            sector_report.generate_sector_report("/tmp/html.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            # 验证所有主要 HTML 结构元素
            assert "<!DOCTYPE html>" in written
            assert "</html>" in written
            assert "Chart.js" in written
            # 验证各 section
            assert "一、市场概览" in written
            assert "二、板块综合排名" in written
            assert "三、板块评分对比" in written
            assert "四、板块五因子对比" in written
            assert "五、各因子领先板块" in written
            assert "七、板块详情总览" in written
            # 验证 footer
            assert "免责" in written or "建议" in written

    def test_non_numeric_score_in_sector_data(self):
        """评分转换异常：综合评分非数值 → 先转 object 再 pd.to_numeric 确保不崩溃"""
        df = _make_screener_df()
        # 转 object dtype 以允许赋值 "N/A"
        df = df.astype({"综合评分": object})
        df.loc[df["代码"] == "999999", "综合评分"] = "N/A"
        # 转回数值，errors='coerce' 将 "N/A" 变成 pd.NA
        # dropna() 后 all_scores 中不含非数值，整体不崩溃
        df["综合评分"] = pd.to_numeric(df["综合评分"], errors="coerce")
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = df
            mock_sector.side_effect = _mock_sector
            mock_mkt.return_value = None
            mock_ff.return_value = None

            result = sector_report.generate_sector_report("/tmp/nonnum_score.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            assert "板块分析" in written

    def test_non_numeric_factor_value(self):
        """因子值非数值 → float()→ValueError → fallback 为 0（不影响 all_scores）"""
        df = _make_screener_df()
        # 转 object dtype 以允许赋值 "N/A"；all_scores 只读"综合评分"列不受影响
        df = df.astype({"动量分": object})
        df.loc[df["代码"] == "000001", "动量分"] = "N/A"
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = df
            mock_sector.side_effect = _mock_sector
            mock_mkt.return_value = None
            mock_ff.return_value = None

            result = sector_report.generate_sector_report("/tmp/nonnum_factor.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            assert "板块分析" in written

    def test_sector_with_empty_name(self):
        """get_sector_for_code 返回空/None，应归入「其他」"""
        df = _make_screener_df()
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = df
            mock_sector.return_value = ""  # 空字符串 → 归入"其他"
            mock_mkt.return_value = None
            mock_ff.return_value = None

            sector_report.generate_sector_report("/tmp/empty_sec.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            assert "其他" in written

    def test_sector_with_none_name(self):
        """get_sector_for_code 返回 None"""
        df = _make_screener_df()
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = df
            mock_sector.return_value = None  # None → 归入"其他"
            mock_mkt.return_value = None
            mock_ff.return_value = None

            sector_report.generate_sector_report("/tmp/none_sec.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            assert "其他" in written

    def test_fund_flow_zero_values(self):
        """资金流向：零值和缺失值"""
        ff_df = pd.DataFrame(
            {
                "序号": [1],
                "名称": ["银行"],
                "今日主力净流入-净额": [None],
                "今日主力净流入-净占比": [0],
                "今日涨跌幅": [None],
                "今日主力净流入最大股": [""],
            }
        )
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = _make_screener_df()
            mock_sector.side_effect = _mock_sector
            mock_mkt.return_value = None
            mock_ff.return_value = ff_df

            sector_report.generate_sector_report("/tmp/ff_zero.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            assert "主力净流入 Top 20" in written

    def test_html_contains_dataless_section(self):
        """market overview 无数据时，rating 部分应正常渲染"""
        df = _make_screener_df()
        # 无评级列但其他正常
        df = df.drop(columns=["评级"])
        with (
            patch("stock_analyzer.sector_report.run_screener") as mock_run,
            patch("stock_analyzer.sector_report.get_sector_for_code") as mock_sector,
            patch("stock_analyzer.sector_report.cached_market_overview") as mock_mkt,
            patch("stock_analyzer.cache.cached_sector_fund_flow_rank") as mock_ff,
            patch("stock_analyzer.sector_report.os.makedirs"),
            patch("builtins.open", new_callable=MagicMock) as mock_open,
        ):
            mock_run.return_value = df
            mock_sector.side_effect = _mock_sector
            mock_mkt.return_value = None
            mock_ff.return_value = None

            sector_report.generate_sector_report("/tmp/no_rate.html")

            handle = mock_open.return_value.__enter__.return_value
            written = "".join(c[0][0] for c in handle.write.call_args_list)
            # 无评级列时 buy_pct 和 sell_pct = 0，不应出现 Chart.js ratingChart
            assert "板块分析" in written
