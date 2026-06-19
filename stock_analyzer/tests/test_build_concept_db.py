"""测试 build_concept_db.py — 概念板块数据库构建"""

import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from stock_analyzer import build_concept_db


class TestBuild(unittest.TestCase):
    """build() 构建概念板块数据库"""

    def setUp(self):
        self.db = tempfile.mktemp(suffix=".db")
        self.akshare_mock = MagicMock()
        self.modules_patcher = patch.dict("sys.modules", {"akshare": self.akshare_mock})
        self.modules_patcher.start()

    def tearDown(self):
        self.modules_patcher.stop()
        if os.path.exists(self.db):
            os.unlink(self.db)

    def test_build_creates_tables(self):
        """正常构建创建表并插入数据"""
        build_concept_db.DB_PATH = self.db

        # mock akshare 返回概念列表
        self.akshare_mock.stock_board_concept_name_em.return_value = pd.DataFrame(
            {
                "板块名称": ["AI概念", "新能源", "半导体"],
            }
        )

        # mock 成分股查询
        def mock_cons_em(symbol):
            data = {
                "AI概念": pd.DataFrame({"代码": ["000001", "000002"]}),
                "新能源": pd.DataFrame({"代码": ["000003"]}),
                "半导体": pd.DataFrame({"代码": ["000004", "000005", "000006"]}),
            }
            return data.get(symbol, pd.DataFrame())

        self.akshare_mock.stock_board_concept_cons_em.side_effect = mock_cons_em

        result = build_concept_db.build()
        self.assertEqual(result, 3)  # 3 个概念板块

        # 验证数据写入
        conn = sqlite3.connect(self.db)
        rows = conn.execute("SELECT COUNT(*) FROM stock_concept").fetchone()[0]
        self.assertEqual(rows, 6)  # 2+1+3 = 6 条映射
        conn.close()

    def test_build_with_progress_cb(self):
        """progress_cb 被调用"""
        build_concept_db.DB_PATH = self.db
        self.akshare_mock.stock_board_concept_name_em.return_value = pd.DataFrame(
            {
                "板块名称": ["A", "B", "C", "D", "E"],
            }
        )
        self.akshare_mock.stock_board_concept_cons_em.return_value = pd.DataFrame(
            {
                "代码": ["000001", "000002"],
            }
        )

        calls = []

        def progress(i, total, name):
            calls.append((i, total, name))

        build_concept_db.build(progress_cb=progress)
        self.assertGreater(len(calls), 0)

    def test_empty_concept_list(self):
        """空概念列表 → 返回 0"""
        build_concept_db.DB_PATH = tempfile.mktemp(suffix=".db")
        self.akshare_mock.stock_board_concept_name_em.return_value = pd.DataFrame({"板块名称": []})
        result = build_concept_db.build()
        self.assertEqual(result, 0)


class TestGetConcepts(unittest.TestCase):
    """get_concepts() 查询"""

    def setUp(self):
        self.db = tempfile.mktemp(suffix=".db")

    def tearDown(self):
        if os.path.exists(self.db):
            os.unlink(self.db)

    def _seed(self):
        build_concept_db.DB_PATH = self.db
        conn = sqlite3.connect(self.db)
        conn.execute("""CREATE TABLE IF NOT EXISTS stock_concept (
            code TEXT, concept TEXT, source TEXT DEFAULT 'eastmoney',
            PRIMARY KEY (code, concept))""")
        conn.execute("INSERT INTO stock_concept VALUES ('000001', 'AI概念', 'eastmoney')")
        conn.execute("INSERT INTO stock_concept VALUES ('000001', '半导体', 'eastmoney')")
        conn.execute("INSERT INTO stock_concept VALUES ('000002', '新能源', 'eastmoney')")
        conn.commit()
        conn.close()

    def test_get_existing_concepts(self):
        """已有记录 → 返回概念列表"""
        self._seed()
        concepts = build_concept_db.get_concepts("000001")
        self.assertEqual(len(concepts), 2)
        self.assertIn("AI概念", concepts)
        self.assertIn("半导体", concepts)

    def test_get_nonexistent(self):
        """不存在 → 空列表"""
        self._seed()
        concepts = build_concept_db.get_concepts("999999")
        self.assertEqual(concepts, [])

    def test_db_error_returns_empty(self):
        """数据库异常 → 空列表"""
        build_concept_db.DB_PATH = "/nonexistent/path/db.sqlite"
        self.assertEqual(build_concept_db.get_concepts("000001"), [])


class TestGetSectorAll(unittest.TestCase):
    """get_sector_all() 全量板块信息"""

    def setUp(self):
        self.db = tempfile.mktemp(suffix=".db")

    def tearDown(self):
        if os.path.exists(self.db):
            os.unlink(self.db)

    def _seed(self):
        build_concept_db.DB_PATH = self.db
        conn = sqlite3.connect(self.db)
        conn.execute("""CREATE TABLE IF NOT EXISTS stock_concept (
            code TEXT, concept TEXT, source TEXT, PRIMARY KEY (code, concept))""")
        conn.execute("""CREATE TABLE IF NOT EXISTS stock_sector_v2 (
            code TEXT, sector TEXT, sub_sector TEXT, type TEXT,
            PRIMARY KEY (code, type))""")
        conn.execute(
            "INSERT INTO stock_sector_v2 VALUES ('000001', '银行', '股份制银行', 'industry')"
        )
        conn.execute("INSERT INTO stock_concept VALUES ('000001', '破净股', 'eastmoney')")
        conn.commit()
        conn.close()

    def test_returns_industry_and_concepts(self):
        """返回行业 + 概念"""
        self._seed()
        info = build_concept_db.get_sector_all("000001")
        self.assertIn("industry", info)
        self.assertIn("concepts", info)
        self.assertEqual(info["industry"], "银行 > 股份制银行")
        self.assertIn("破净股", info["concepts"])

    def test_unknown_returns_defaults(self):
        """不存在 → 返回默认值"""
        self._seed()
        info = build_concept_db.get_sector_all("999999")
        self.assertEqual(info["industry"], "未知")
        self.assertEqual(info["concepts"], [])


if __name__ == "__main__":
    unittest.main()
