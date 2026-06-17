"""测试 sector_info.py — 板块归属查询"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from stock_analyzer.sector_info import (
    _CACHE,
    _query,
    get_stock_all_sectors,
    get_stock_concepts,
    get_stock_sector_full,
)


class TestSectorInfoNoDB(unittest.TestCase):
    """无数据库时的行为测试"""

    def setUp(self):
        _CACHE.clear()

    def test_get_stock_sector_full_no_db(self):
        """数据库不可用时返回 '未知'"""
        with patch(
            "stock_analyzer.sector_info.sqlite3.connect", side_effect=OSError("DB not found")
        ):
            result = get_stock_sector_full("000001")
            self.assertEqual(result, "未知")

    def test_get_stock_concepts_no_db(self):
        """数据库不可用时返回空列表"""
        with patch(
            "stock_analyzer.sector_info.sqlite3.connect", side_effect=OSError("DB not found")
        ):
            result = get_stock_concepts("000001")
            self.assertEqual(result, [])

    def test_get_stock_all_sectors_no_db(self):
        """数据库不可用时返回默认结构"""
        with patch(
            "stock_analyzer.sector_info.sqlite3.connect", side_effect=OSError("DB not found")
        ):
            result = get_stock_all_sectors("000001")
            self.assertEqual(result["industry"], "未知")
            self.assertEqual(result["concepts"], [])


class TestSectorInfoCache(unittest.TestCase):
    """缓存行为测试"""

    def setUp(self):
        _CACHE.clear()

    def test_query_caches_result(self):
        """_query 结果被缓存"""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = ("信息技术", "半导体")

        with patch("stock_analyzer.sector_info.sqlite3.connect", return_value=mock_conn):
            result1 = _query("000001")
            self.assertEqual(result1, ("信息技术", "半导体"))
            self.assertIn("000001", _CACHE)

    def test_cached_query_no_db_call(self):
        """已缓存的查询不访问数据库"""
        _CACHE["000002"] = ("金融", "银行")
        with patch(
            "stock_analyzer.sector_info.sqlite3.connect",
            side_effect=Exception("should not be called"),
        ):
            result = _query("000002")
            self.assertEqual(result, ("金融", "银行"))

    def test_queue_none_result_cached(self):
        """查询失败的结果(None)也被缓存"""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None

        with patch("stock_analyzer.sector_info.sqlite3.connect", return_value=mock_conn):
            result = _query("999999")
            self.assertIsNone(result)
            self.assertIn("999999", _CACHE)
            self.assertIsNone(_CACHE["999999"])


class TestSectorInfoFull(unittest.TestCase):
    """完整数据流测试"""

    def setUp(self):
        _CACHE.clear()

    def test_get_stock_sector_full_formatted(self):
        """行业信息格式化正确"""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = ("制造业", "汽车零部件")

        with patch("stock_analyzer.sector_info.sqlite3.connect", return_value=mock_conn):
            result = get_stock_sector_full("600000")
            self.assertEqual(result, "制造业 > 汽车零部件")

    def test_get_stock_concepts_with_data(self):
        """概念板块正常返回"""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            ("新能源车",),
            ("锂电池",),
            ("特斯拉",),
        ]

        with patch("stock_analyzer.sector_info.sqlite3.connect", return_value=mock_conn):
            result = get_stock_concepts("300750")
            self.assertEqual(result, ["新能源车", "锂电池", "特斯拉"])

    def test_get_stock_concepts_empty(self):
        """无概念板块时返回空列表"""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("stock_analyzer.sector_info.sqlite3.connect", return_value=mock_conn):
            result = get_stock_concepts("000001")
            self.assertEqual(result, [])

    def test_get_stock_all_sectors_full(self):
        """完整板块信息结构正确"""

        def mock_connect(*args, **kwargs):
            conn = MagicMock()
            # 根据查询内容返回不同结果
            call_count = [0]

            def side_effect(query, params=None):
                call_count[0] += 1
                m = MagicMock()
                if "stock_sector_v2" in query:
                    m.fetchone.return_value = ("制造业", "汽车零部件")
                elif "stock_concept" in query:
                    m.fetchall.return_value = [("新能源车",), ("锂电池",)]
                return m

            conn.execute.side_effect = side_effect
            return conn

        with patch("stock_analyzer.sector_info.sqlite3.connect", side_effect=mock_connect):
            result = get_stock_all_sectors("600000")
            self.assertEqual(result["industry"], "制造业 > 汽车零部件")
            self.assertIn("新能源车", result["concepts"])
            self.assertIn("锂电池", result["concepts"])


if __name__ == "__main__":
    unittest.main()
