import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
import unittest

from stock_analyzer import cache

# 测试用独立数据库路径（避免影响线上缓存）
TEST_DB = os.path.join(os.path.dirname(__file__), "test_cache.db")


class TestCache(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db_path = cache.DB_PATH
        cache.DB_PATH = TEST_DB
        # 重置连接，使下一次 _get_conn 使用新的 DB_PATH
        if hasattr(cache._local, "conn"):
            cache._local.conn = None

    @classmethod
    def tearDownClass(cls):
        cache.DB_PATH = cls._orig_db_path
        if hasattr(cache._local, "conn"):
            cache._local.conn = None
        try:
            os.remove(TEST_DB)
        except OSError:
            pass

    def setUp(self):
        cache.cache_clear_all()

    # ── 测试用例 ──────────────────────────────────

    def test_set_get(self):
        """写入后读取"""
        cache.cache_set("k1", "hello")
        self.assertEqual(cache.cache_get("k1"), "hello")

    def test_get_nonexistent(self):
        """不存在返回 None"""
        self.assertIsNone(cache.cache_get("i_dont_exist"))

    def test_expiry(self):
        """TTL 过期后返回 None"""
        cache.cache_set("exp", "val", ttl=1)
        self.assertEqual(cache.cache_get("exp"), "val")
        time.sleep(1.5)
        self.assertIsNone(cache.cache_get("exp"))

    def test_clear(self):
        """删除单条"""
        cache.cache_set("del_me", "data")
        self.assertIsNotNone(cache.cache_get("del_me"))
        cache.cache_clear("del_me")
        self.assertIsNone(cache.cache_get("del_me"))

    def test_clear_all(self):
        """清空全部"""
        cache.cache_set("a", 1)
        cache.cache_set("b", 2)
        cache.cache_clear_all()
        self.assertIsNone(cache.cache_get("a"))
        self.assertIsNone(cache.cache_get("b"))

    def test_overwrite(self):
        """覆盖写入"""
        cache.cache_set("ow", "old_value")
        cache.cache_set("ow", "new_value")
        self.assertEqual(cache.cache_get("ow"), "new_value")


if __name__ == "__main__":
    unittest.main()
