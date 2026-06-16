"""测试 build_sector_db.py — Baostock 行业板块数据库构建

关键陷阱：build() 内部所有 import 都是懒加载（函数体内），
包括 import baostock as bs 和 from .sectors_fallback import SECTOR_STOCKS_FALLBACK。
所以 patch 必须针对源模块路径生效，不能用 stock_analyzer.build_sector_db 属性路径。
"""
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import sqlite3

import baostock as bs  # noqa: F401 确保 baostock 在 sys.modules 里

from stock_analyzer import build_sector_db


class TestBuild(unittest.TestCase):
    """build() 板块数据库构建"""

    @patch("baostock.login")
    @patch("baostock.query_stock_industry")
    @patch("baostock.logout")
    def test_build_from_baostock(self, mock_logout, mock_query, mock_login):
        """正常构建: Baostock 全量"""
        build_sector_db.DB_PATH = tempfile.mktemp(suffix=".db")

        mock_rs = MagicMock()
        mock_rs.next.side_effect = [True, True, False]  # 两条记录
        mock_rs.get_row_data.side_effect = [
            ["1", "sh.000001", "000001.SH", "J66货币金融服务"],
            ["2", "sz.000002", "000002.SZ", "C27医药制造业"],
        ]
        mock_query.return_value = mock_rs

        result = build_sector_db.build()
        self.assertGreater(result, 0)
        mock_login.assert_called_once()
        mock_logout.assert_called_once()

        conn = sqlite3.connect(build_sector_db.DB_PATH)
        rows = conn.execute("SELECT COUNT(*) FROM stock_sector").fetchone()[0]
        self.assertEqual(rows, 2)
        conn.close()

    @patch("stock_analyzer.sectors_fallback.SECTOR_STOCKS_FALLBACK", {"半导体": {"成分股": ["000002"]}})
    @patch("baostock.login")
    @patch("baostock.query_stock_industry")
    @patch("baostock.logout")
    def test_build_with_static_override(self, mock_logout, mock_query, mock_login):
        """静态映射覆盖 Baostock 数据"""
        build_sector_db.DB_PATH = tempfile.mktemp(suffix=".db")

        mock_rs = MagicMock()
        mock_rs.next.side_effect = [True, False]
        mock_rs.get_row_data.return_value = ["1", "sz.000002", "000002.SZ", "C27医药制造业"]
        mock_query.return_value = mock_rs

        build_sector_db.build()

        conn = sqlite3.connect(build_sector_db.DB_PATH)
        sector = conn.execute(
            "SELECT sector FROM stock_sector WHERE code='000002'"
        ).fetchone()[0]
        source = conn.execute(
            "SELECT source FROM stock_sector WHERE code='000002'"
        ).fetchone()[0]
        conn.close()
        self.assertEqual(sector, "半导体")  # 被静态覆盖
        self.assertEqual(source, "static")  # 来源标记为 static

    @patch("stock_analyzer.sectors_fallback.SECTOR_STOCKS_FALLBACK", {})
    @patch("baostock.login")
    @patch("baostock.query_stock_industry")
    @patch("baostock.logout")
    def test_baostock_industry_clean(self, mock_logout, mock_query, mock_login):
        """行业名称清理: 去掉字母数字前缀"""
        build_sector_db.DB_PATH = tempfile.mktemp(suffix=".db")

        mock_rs = MagicMock()
        mock_rs.next.side_effect = [True, False]
        mock_rs.get_row_data.return_value = ["1", "sh.600519", "600519.SH", "J66货币金融服务"]
        mock_query.return_value = mock_rs

        build_sector_db.build()

        conn = sqlite3.connect(build_sector_db.DB_PATH)
        sector = conn.execute("SELECT sector FROM stock_sector").fetchone()[0]
        conn.close()
        self.assertEqual(sector, "货币金融服务")  # 前缀被清理


class TestGetSectorFromDB(unittest.TestCase):
    """get_sector_from_db() 查询"""

    def setUp(self):
        self.db = tempfile.mktemp(suffix=".db")

    def tearDown(self):
        if os.path.exists(self.db):
            os.unlink(self.db)

    def _seed(self):
        build_sector_db.DB_PATH = self.db
        conn = sqlite3.connect(self.db)
        conn.execute("""CREATE TABLE IF NOT EXISTS stock_sector (
            code TEXT PRIMARY KEY, sector TEXT NOT NULL, source TEXT DEFAULT 'baostock')""")
        conn.execute("INSERT INTO stock_sector VALUES ('000001', '银行', 'baostock')")
        conn.commit()
        conn.close()

    def test_get_existing(self):
        """已有 → 返回板块名"""
        self._seed()
        sector = build_sector_db.get_sector_from_db("000001")
        self.assertEqual(sector, "银行")

    def test_get_missing_returns_other(self):
        """无记录 → '其他'"""
        self._seed()
        sector = build_sector_db.get_sector_from_db("999999")
        self.assertEqual(sector, "其他")

    def test_db_error_returns_other(self):
        """数据库异常 → '其他'"""
        build_sector_db.DB_PATH = "/nonexistent/path/db.sqlite"
        self.assertEqual(build_sector_db.get_sector_from_db("000001"), "其他")


if __name__ == "__main__":
    unittest.main()
