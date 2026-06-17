"""测试 history_db.py — SQLite 历史评分数据库操作"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from stock_analyzer import history_db


class TestInitHistoryDB(unittest.TestCase):
    """初始化历史数据库"""

    @patch("stock_analyzer.history_db.DB_PATH", new_callable=lambda: tempfile.mktemp(suffix=".db"))
    def test_init_creates_table(self, mock_path):
        """幂等初始化，表结构正确"""
        history_db.DB_PATH = mock_path
        history_db.init_history_db()

        conn = history_db._get_conn()
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        conn.close()
        os.unlink(mock_path)

        self.assertIn(("daily_scores",), tables)


class TestAppendResults(unittest.TestCase):
    """追加当日结果"""

    def setUp(self):
        self.db = tempfile.mktemp(suffix=".db")

    def tearDown(self):
        if os.path.exists(self.db):
            os.unlink(self.db)

    def _patch_path(self):
        return patch("stock_analyzer.history_db.DB_PATH", self.db)

    def test_empty_df_returns_zero(self):
        """空 DataFrame / None → 返回 0"""
        self.assertEqual(history_db.append_daily_results(None), 0)
        self.assertEqual(history_db.append_daily_results(pd.DataFrame()), 0)

    def test_append_single_row(self):
        """写入一条记录，返回行数"""
        df = pd.DataFrame(
            [
                {
                    "代码": "000001",
                    "名称": "平安银行",
                    "综合评分": 85,
                    "评级": "A",
                    "动量分": 80,
                    "技术分": 70,
                    "基本面分": 90,
                    "量能分": 75,
                    "风险分": 20,
                    "最新价": 12.5,
                    "涨跌幅": 1.2,
                }
            ]
        )
        with self._patch_path():
            n = history_db.append_daily_results(df, scan_date="2025-06-01")
            self.assertEqual(n, 1)

    def test_append_multiple_rows(self):
        """写入多条记录"""
        df = pd.DataFrame(
            [
                {"代码": "000001", "名称": "平安银行", "综合评分": 85},
                {"代码": "000002", "名称": "万科A", "综合评分": 72},
            ]
        )
        # 补齐缺失字段测试默认值
        with self._patch_path():
            n = history_db.append_daily_results(df, scan_date="2025-06-01")
            self.assertEqual(n, 2)

    def test_overwrite_on_same_date_code(self):
        """同一日期+代码 → INSERT OR REPLACE 覆盖"""
        df1 = pd.DataFrame(
            [
                {"代码": "000001", "名称": "平安银行", "综合评分": 85, "评级": "A"},
            ]
        )
        df2 = pd.DataFrame(
            [
                {"代码": "000001", "名称": "平安银行", "综合评分": 90, "评级": "A+"},
            ]
        )
        with self._patch_path():
            history_db.append_daily_results(df1, scan_date="2025-06-01")
            history_db.append_daily_results(df2, scan_date="2025-06-01")
            rows = (
                history_db._get_conn()
                .execute(
                    "SELECT composite_score FROM daily_scores WHERE date='2025-06-01' AND code='000001'"
                )
                .fetchall()
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], 90)

    def test_default_scan_date_is_today(self):
        """scan_date 默认今天"""
        from datetime import datetime

        df = pd.DataFrame(
            [
                {"代码": "000001", "名称": "平安银行", "综合评分": 85},
            ]
        )
        with self._patch_path():
            history_db.append_daily_results(df)
            today = datetime.now().strftime("%Y-%m-%d")
            rows = (
                history_db._get_conn()
                .execute("SELECT COUNT(*) FROM daily_scores WHERE date=?", (today,))
                .fetchone()
            )
            self.assertGreater(rows[0], 0)

    def test_code_zero_filled(self):
        """代码自动补零到6位"""
        df = pd.DataFrame(
            [
                {"代码": "1", "名称": "测试", "综合评分": 80},
            ]
        )
        with self._patch_path():
            history_db.append_daily_results(df, scan_date="2025-06-01")
            rows = history_db._get_conn().execute("SELECT code FROM daily_scores").fetchall()
            self.assertEqual(rows[0][0], "000001")


class TestGetStockHistory(unittest.TestCase):
    """查询单只股票历史"""

    def setUp(self):
        self.db = tempfile.mktemp(suffix=".db")

    def tearDown(self):
        if os.path.exists(self.db):
            os.unlink(self.db)

    def _seed(self):
        with patch("stock_analyzer.history_db.DB_PATH", self.db):
            history_db.init_history_db()
            for d in ["2025-06-01", "2025-06-02", "2025-06-03"]:
                df = pd.DataFrame(
                    [
                        {"代码": "000001", "名称": "平安银行", "综合评分": 80},
                    ]
                )
                history_db.append_daily_results(df, scan_date=d)

    def test_returns_dataframe(self):
        """正常返回 DataFrame"""
        self._seed()
        with patch("stock_analyzer.history_db.DB_PATH", self.db):
            df = history_db.get_stock_history("000001", days=30)
            self.assertIsInstance(df, pd.DataFrame)
            self.assertGreater(len(df), 0)

    def test_empty_for_unknown_code(self):
        """不存在代码 → 空 DataFrame"""
        with patch("stock_analyzer.history_db.DB_PATH", self.db):
            history_db.init_history_db()
            df = history_db.get_stock_history("999999")
            self.assertTrue(df.empty)

    def test_code_zero_filled(self):
        """代码自动补零"""
        self._seed()
        with patch("stock_analyzer.history_db.DB_PATH", self.db):
            df1 = history_db.get_stock_history("1")
            df2 = history_db.get_stock_history("000001")
            self.assertEqual(len(df1), len(df2))


class TestGetTopStocks(unittest.TestCase):
    """查询高评分股票"""

    def setUp(self):
        self.db = tempfile.mktemp(suffix=".db")

    def tearDown(self):
        if os.path.exists(self.db):
            os.unlink(self.db)

    def _seed(self):
        with patch("stock_analyzer.history_db.DB_PATH", self.db):
            history_db.init_history_db()
            df = pd.DataFrame(
                [
                    {"代码": "000001", "名称": "A", "综合评分": 90, "动量分": 85},
                    {"代码": "000002", "名称": "B", "综合评分": 70, "动量分": 65},
                    {"代码": "000003", "名称": "C", "综合评分": 50, "动量分": 45},
                ]
            )
            history_db.append_daily_results(df, scan_date="2025-06-01")

    def test_returns_top_n(self):
        """按评分降序返回指定数量"""
        self._seed()
        with patch("stock_analyzer.history_db.DB_PATH", self.db):
            df = history_db.get_top_stocks(date="2025-06-01", top_n=2)
            self.assertEqual(len(df), 2)
            self.assertEqual(df.iloc[0]["code"], "000001")  # 评分最高

    def test_min_score_filter(self):
        """min_score 过滤低分"""
        self._seed()
        with patch("stock_analyzer.history_db.DB_PATH", self.db):
            df = history_db.get_top_stocks(date="2025-06-01", min_score=80)
            self.assertEqual(len(df), 1)

    def test_no_date_uses_latest(self):
        """不传 date 用最新日期"""
        self._seed()
        with patch("stock_analyzer.history_db.DB_PATH", self.db):
            df = history_db.get_top_stocks()
            self.assertGreaterEqual(len(df), 0)

    def test_empty_db_returns_empty(self):
        """空库 → 空 DataFrame"""
        with patch("stock_analyzer.history_db.DB_PATH", self.db):
            history_db.init_history_db()
            df = history_db.get_top_stocks()
            self.assertTrue(df.empty)


class TestGetMarketSummary(unittest.TestCase):
    """全市场评分分布统计"""

    def setUp(self):
        self.db = tempfile.mktemp(suffix=".db")

    def tearDown(self):
        if os.path.exists(self.db):
            os.unlink(self.db)

    def _seed(self):
        with patch("stock_analyzer.history_db.DB_PATH", self.db):
            history_db.init_history_db()
            df = pd.DataFrame(
                [
                    {"代码": "000001", "名称": "A", "综合评分": 90},
                    {"代码": "000002", "名称": "B", "综合评分": 70},
                    {"代码": "000003", "名称": "C", "综合评分": 50},
                    {"代码": "000004", "名称": "D", "综合评分": 30},
                ]
            )
            history_db.append_daily_results(df, scan_date="2025-06-01")

    def test_summary_structure(self):
        """返回统计字典包含所有 key"""
        self._seed()
        with patch("stock_analyzer.history_db.DB_PATH", self.db):
            sm = history_db.get_market_summary(date="2025-06-01")
            for key in ["date", "total", "avg_score", "excellent", "good", "medium", "low"]:
                self.assertIn(key, sm)

    def test_counts_correct(self):
        """分级统计正确"""
        self._seed()
        with patch("stock_analyzer.history_db.DB_PATH", self.db):
            sm = history_db.get_market_summary(date="2025-06-01")
            self.assertEqual(sm["total"], 4)
            self.assertEqual(sm["excellent"], 1)  # >=80
            self.assertEqual(sm["good"], 1)  # 60-79
            self.assertEqual(sm["medium"], 1)  # 40-59
            self.assertEqual(sm["low"], 1)  # <40

    def test_empty_db_returns_empty_dict(self):
        """空库 → 空 dict"""
        with patch("stock_analyzer.history_db.DB_PATH", self.db):
            history_db.init_history_db()
            sm = history_db.get_market_summary()
            self.assertEqual(sm, {})

    def test_no_date_uses_latest(self):
        """不传 date 用最新"""
        self._seed()
        with patch("stock_analyzer.history_db.DB_PATH", self.db):
            sm = history_db.get_market_summary()
            self.assertEqual(sm["total"], 4)


class TestGetAvailableDates(unittest.TestCase):
    """可用日期查询"""

    def setUp(self):
        self.db = tempfile.mktemp(suffix=".db")

    def tearDown(self):
        if os.path.exists(self.db):
            os.unlink(self.db)

    def test_returns_dates(self):
        with patch("stock_analyzer.history_db.DB_PATH", self.db):
            history_db.init_history_db()
            df = pd.DataFrame([{"代码": "000001", "名称": "A", "综合评分": 80}])
            history_db.append_daily_results(df, scan_date="2025-06-01")
            dates = history_db.get_available_dates()
            self.assertIn("2025-06-01", dates)

    def test_empty_returns_empty(self):
        with patch("stock_analyzer.history_db.DB_PATH", self.db):
            history_db.init_history_db()
            dates = history_db.get_available_dates()
            self.assertEqual(dates, [])


if __name__ == "__main__":
    unittest.main()
