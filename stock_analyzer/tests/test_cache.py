"""测试 cache.py — 模板缓存 + 永久存储 + K线缓存"""
import os
import sys
import unittest
import pickle
import sqlite3
import time
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np

from stock_analyzer import cache

# ── 原有的 DB_PATH 替换（保持兼容）──
_ORIG_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "stock_cache.db")

def _setup_test_cache():
    """重置内存缓存和 DB 路径"""
    cache._MEM_CACHE.clear()
    cache._DB_CONN = None  # type: ignore[attr-defined]
    # 用 :memory: 替代真实 DB
    return

def _make_kline_df(rows=60, code="000001"):
    """构造模拟K线 DataFrame"""
    np.random.seed(42)
    close = 50 + np.cumsum(np.random.randn(rows) * 0.3)
    dates = pd.date_range("2025-01-01", periods=rows)
    df = pd.DataFrame({
        "日期": dates,
        "开盘": close * 0.99,
        "收盘": close,
        "最高": close * 1.02,
        "最低": close * 0.98,
        "成交量": np.random.randint(1_000_000, 10_000_000, rows),
        "涨跌幅": np.append([0], np.diff(close) / close[:-1] * 100),
        "涨跌额": np.append([0], np.diff(close)),
        "代码": [code] * rows,
    })
    return df

# ═══════════════════════════════════════════
# 核心 KV 缓存
# ═══════════════════════════════════════════

class TestCacheBasic(unittest.TestCase):
    """基础 KV 缓存操作"""

    def setUp(self):
        cache._MEM_CACHE.clear()

    def test_cache_set_get(self):
        cache.cache_set("test_key", {"val": 42})
        result = cache.cache_get("test_key")
        self.assertIsNotNone(result)
        self.assertEqual(result["val"], 42)

    def test_cache_get_miss(self):
        result = cache.cache_get("nonexistent_key_12345")
        self.assertIsNone(result)

    def test_cache_ttl_expiry(self):
        """TTL 过期后缓存返回 None"""
        cache.cache_set("expire_key", "value", ttl=0)  # immediate expiry
        # Sleep to ensure expiry
        import time
        time.sleep(0.01)
        result = cache.cache_get("expire_key")
        self.assertIsNone(result)

    def test_cache_overwrite(self):
        cache.cache_set("overwrite_key", "old")
        cache.cache_set("overwrite_key", "new")
        result = cache.cache_get("overwrite_key")
        self.assertEqual(result, "new")

    def test_cache_clear(self):
        cache.cache_set("clear_test", "val")
        cache.cache_clear("clear_test")
        self.assertIsNone(cache.cache_get("clear_test"))

    def test_cache_clear_all(self):
        cache.cache_set("k1", "v1")
        cache.cache_set("k2", "v2")
        cache.cache_clear_all()
        self.assertEqual(len(cache._MEM_CACHE), 0)

# ═══════════════════════════════════════════
# 异常路径
# ═══════════════════════════════════════════

class TestCacheErrorPaths(unittest.TestCase):
    """cache 函数的异常降级路径"""

    def setUp(self):
        cache._MEM_CACHE.clear()

    def test_cache_get_exception_returns_none(self):
        """cache_get 异常时返回 None"""
        with patch('stock_analyzer.cache.sqlite3.connect', side_effect=Exception("DB down")):
            result = cache.cache_get("any_key")
            self.assertIsNone(result)

    def test_cache_set_exception_no_raise(self):
        """cache_set 异常时不抛异常"""
        cache.cache_set("pre_set", "ok_value")  # 先正常存一个
        with patch('stock_analyzer.cache.sqlite3.connect', side_effect=Exception("DB down")):
            # Should not raise
            cache.cache_set("should_not_crash", "value")

    def test_cache_clear_exception_no_raise(self):
        """cache_clear 异常时不抛异常"""
        with patch('stock_analyzer.cache.sqlite3.connect', side_effect=Exception("DB down")):
            cache.cache_clear("any_key")

    def test_cache_clear_all_exception_no_raise(self):
        """cache_clear_all 异常时不抛异常"""
        with patch('stock_analyzer.cache.sqlite3.connect', side_effect=Exception("DB down")):
            cache.cache_clear_all()

# ═══════════════════════════════════════════
# 永久存储 _perm_load / _perm_save
# ═══════════════════════════════════════════

class TestPermStorage(unittest.TestCase):
    """_perm_load 和 _perm_save 永久存储"""

    def setUp(self):
        cache._MEM_CACHE.clear()
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE IF NOT EXISTS test_t (key_col TEXT PRIMARY KEY, data BLOB, updated_at REAL)")

    def tearDown(self):
        self.conn.close()

    @patch('stock_analyzer.cache._get_conn')
    def test_perm_save_and_load(self, mock_conn):
        """保存后再加载"""
        mock_conn.return_value = self.conn
        data = {"fundamentals": {"ROE": 15, "PE": 20}}
        cache._perm_save("test_t", "key_col", "mykey", data)
        result = cache._perm_load("test_t", "key_col", "mykey")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["fundamentals"]["ROE"], 15)

    @patch('stock_analyzer.cache._get_conn')
    def test_perm_load_nonexistent(self, mock_conn):
        """加载不存在的 key 返回 None"""
        mock_conn.return_value = self.conn
        result = cache._perm_load("test_t", "key_col", "nonexistent")
        self.assertIsNone(result)

    @patch('stock_analyzer.cache._get_conn')
    def test_perm_load_corrupted_data(self, mock_conn):
        """损坏的 blob 数据返回 None"""
        mock_conn.return_value = self.conn
        self.conn.execute(
            "INSERT OR REPLACE INTO test_t VALUES (?, ?, ?)",
            ("bad_key", b"not_valid_pickle", time.time()),
        )
        self.conn.commit()
        result = cache._perm_load("test_t", "key_col", "bad_key")
        self.assertIsNone(result)

    @patch('stock_analyzer.cache._get_conn')
    def test_perm_save_overwrite(self, mock_conn):
        """覆盖保存"""
        mock_conn.return_value = self.conn
        cache._perm_save("test_t", "key_col", "overwrite_key", {"v": 1})
        cache._perm_save("test_t", "key_col", "overwrite_key", {"v": 2})
        result = cache._perm_load("test_t", "key_col", "overwrite_key")
        self.assertEqual(result["v"], 2)

# ═══════════════════════════════════════════
# 模板化 cached_* 函数
# ═══════════════════════════════════════════

class TestCachedWrappers(unittest.TestCase):
    """模板缓存包装函数（mock fetcher）"""

    def setUp(self):
        cache._MEM_CACHE.clear()

    def tearDown(self):
        cache._MEM_CACHE.clear()

    # ── cached_market_news ──

    @patch('stock_analyzer.fetcher.get_market_news')
    def test_cached_market_news_hit(self, mock_fetch):
        """缓存命中直接返回"""
        mock_df = pd.DataFrame({"title": ["新闻1"]})
        cache.cache_set("market_news", mock_df, ttl=1800)
        result = cache.cached_market_news()
        mock_fetch.assert_not_called()
        self.assertEqual(len(result), 1)

    @patch('stock_analyzer.cache.cache_get', return_value=None)
    @patch('stock_analyzer.fetcher.get_market_news')
    def test_cached_market_news_miss(self, mock_fetch, mock_cache_get):
        """缓存未命中，调用 fetcher"""
        mock_df = pd.DataFrame({"title": ["新闻A", "新闻B"]})
        mock_fetch.return_value = mock_df
        result = cache.cached_market_news()
        mock_fetch.assert_called_once()
        self.assertEqual(len(result), 2)

    @patch('stock_analyzer.fetcher.get_market_news')
    def test_cached_market_news_fetch_error(self, mock_fetch):
        """fetcher 异常返回空 DataFrame"""
        mock_fetch.side_effect = Exception("Network error")
        result = cache.cached_market_news()
        self.assertIsInstance(result, pd.DataFrame)
        self.assertTrue(result.empty)

    # ── cached_stock_news ──

    @patch('stock_analyzer.fetcher.get_stock_news')
    def test_cached_stock_news_hit(self, mock_fetch):
        mock_df = pd.DataFrame({"title": ["股票新闻"]})
        cache.cache_set("news:000001", mock_df)
        result = cache.cached_stock_news("000001")
        mock_fetch.assert_not_called()

    @patch('stock_analyzer.cache.cache_get', return_value=None)
    @patch('stock_analyzer.fetcher.get_stock_news')
    def test_cached_stock_news_miss(self, mock_fetch, mock_cache_get):
        mock_fetch.return_value = pd.DataFrame({"title": ["新闻X"]})
        result = cache.cached_stock_news("000001")
        mock_fetch.assert_called_once_with("000001")

    @patch('stock_analyzer.fetcher.get_stock_news')
    def test_cached_stock_news_error(self, mock_fetch):
        mock_fetch.side_effect = Exception("fail")
        result = cache.cached_stock_news("000001")
        self.assertIsInstance(result, pd.DataFrame)

    # ── cached_weibo_sentiment ──

    @patch('stock_analyzer.fetcher.get_weibo_sentiment')
    def test_cached_weibo_sentiment_miss(self, mock_fetch):
        mock_fetch.return_value = pd.DataFrame({"sentiment": ["positive"]})
        result = cache.cached_weibo_sentiment()
        mock_fetch.assert_called_once()
        self.assertEqual(len(result), 1)

    @patch('stock_analyzer.fetcher.get_weibo_sentiment')
    def test_cached_weibo_sentiment_error(self, mock_fetch):
        mock_fetch.side_effect = Exception("fail")
        result = cache.cached_weibo_sentiment()
        self.assertTrue(result.empty)

    # ── cached_stock_research ──

    @patch('stock_analyzer.fetcher.get_stock_research')
    def test_cached_stock_research_miss(self, mock_fetch):
        mock_fetch.return_value = pd.DataFrame({"report": ["研报1"]})
        result = cache.cached_stock_research("000001")
        mock_fetch.assert_called_once_with("000001")

    @patch('stock_analyzer.fetcher.get_stock_research')
    def test_cached_stock_research_error(self, mock_fetch):
        mock_fetch.side_effect = Exception("fail")
        result = cache.cached_stock_research("000001")
        self.assertTrue(result.empty)

    # ── cached_market_overview ──

    @patch('stock_analyzer.fetcher.get_market_overview')
    def test_cached_market_overview_hit(self, mock_fetch):
        """缓存命中（dict 类型）"""
        cache.cache_set("market_overview", {"index": 3500}, ttl=120)
        result = cache.cached_market_overview()
        mock_fetch.assert_not_called()
        self.assertIn("index", result)

    @patch('stock_analyzer.cache.cache_get', return_value=None)
    @patch('stock_analyzer.fetcher.get_market_overview')
    def test_cached_market_overview_miss(self, mock_fetch, mock_cache_get):
        mock_fetch.return_value = {"index": 3600, "volume": "1.2万亿"}
        result = cache.cached_market_overview()
        self.assertEqual(result["index"], 3600)

    @patch('stock_analyzer.fetcher.get_market_overview')
    def test_cached_market_overview_error(self, mock_fetch):
        mock_fetch.side_effect = Exception("fail")
        result = cache.cached_market_overview()
        self.assertEqual(result, {})

    # ── cached_sector_fund_flow_rank ──

    @patch('stock_analyzer.fetcher.get_sector_fund_flow_rank')
    def test_cached_sector_fund_flow_rank_miss(self, mock_fetch):
        mock_fetch.return_value = pd.DataFrame({"sector": ["半导体"], "flow": [100]})
        result = cache.cached_sector_fund_flow_rank()
        mock_fetch.assert_called_once()

    @patch('stock_analyzer.fetcher.get_sector_fund_flow_rank')
    def test_cached_sector_fund_flow_rank_error(self, mock_fetch):
        mock_fetch.side_effect = Exception("fail")
        result = cache.cached_sector_fund_flow_rank()
        self.assertTrue(result.empty)

# ═══════════════════════════════════════════
# cached_fundamentals — 三层缓存
# ═══════════════════════════════════════════

class TestCachedFundamentals(unittest.TestCase):
    """基本面缓存 — 内存→永久存储→API"""

    def setUp(self):
        cache._MEM_CACHE.clear()

    def tearDown(self):
        cache._MEM_CACHE.clear()

    # ── 内存缓存命中 ──

    def test_mem_hit(self):
        """内存缓存命中"""
        data = {"ROE": 18, "PE": 15, "name": "测试"}
        cache._MEM_CACHE["fundamentals:000001"] = (time.time(), data)
        with patch('stock_analyzer.fetcher.get_fundamentals') as mock_fetch:
            result = cache.cached_fundamentals("000001")
            mock_fetch.assert_not_called()
        self.assertEqual(result["ROE"], 18)

    # ── 永久存储命中 ──

    @patch('stock_analyzer.cache._get_conn')
    @patch('stock_analyzer.cache.get_fundamentals')
    def test_perm_hit_fresh(self, mock_fetch, mock_conn):
        """永久存储数据新鲜"""
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS fund_store (code TEXT PRIMARY KEY, data BLOB, updated_at REAL)"
        )
        data = {"ROE": 20, "PE": 12}
        conn.execute(
            "INSERT OR REPLACE INTO fund_store VALUES (?, ?, ?)",
            ("000001", pickle.dumps(data), time.time()),
        )
        conn.commit()
        mock_conn.return_value = conn
        result = cache.cached_fundamentals("000001")
        mock_fetch.assert_not_called()
        self.assertEqual(result["ROE"], 20)
        conn.close()

    @patch('stock_analyzer.cache._get_conn')
    @patch('stock_analyzer.cache.get_fundamentals')
    def test_perm_hit_stale_within_7d(self, mock_fetch, mock_conn):
        """永久存储过期但未超7天 — 返回旧数据"""
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS fund_store (code TEXT PRIMARY KEY, data BLOB, updated_at REAL)"
        )
        data = {"ROE": 15}
        stale_time = time.time() - 86400 * 2  # 2 days ago
        conn.execute(
            "INSERT OR REPLACE INTO fund_store VALUES (?, ?, ?)",
            ("000001", pickle.dumps(data), stale_time),
        )
        conn.commit()
        mock_conn.return_value = conn
        result = cache.cached_fundamentals("000001")
        # 2天前的数据不会重新拉取
        self.assertEqual(result["ROE"], 15)
        conn.close()

    # ── API 拉取 ──

    @patch('stock_analyzer.cache._get_conn')
    @patch('stock_analyzer.cache.get_fundamentals')
    def test_api_fetch_success(self, mock_fetch, mock_conn):
        """无缓存，API 拉取成功"""
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS fund_store (code TEXT PRIMARY KEY, data BLOB, updated_at REAL)"
        )
        mock_conn.return_value = conn
        mock_fetch.return_value = {"ROE": 25, "PE": 10, "name": "测试公司"}
        result = cache.cached_fundamentals("000001")
        self.assertEqual(result["ROE"], 25)
        mock_fetch.assert_called_once_with("000001")
        conn.close()

    @patch('stock_analyzer.cache._get_conn')
    @patch('stock_analyzer.cache.get_fundamentals')
    def test_api_empty_with_old_data(self, mock_fetch, mock_conn):
        """API 返回空但有旧数据 — 返回旧数据"""
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS fund_store (code TEXT PRIMARY KEY, data BLOB, updated_at REAL)"
        )
        old_data = {"ROE": 10}
        conn.execute(
            "INSERT OR REPLACE INTO fund_store VALUES (?, ?, ?)",
            ("000001", pickle.dumps(old_data), time.time() - 86400),
        )
        conn.commit()
        mock_conn.return_value = conn
        mock_fetch.return_value = {}  # empty
        result = cache.cached_fundamentals("000001")
        self.assertEqual(result["ROE"], 10)
        conn.close()

    @patch('stock_analyzer.cache._get_conn')
    @patch('stock_analyzer.cache.get_fundamentals')
    def test_api_error_with_old_data(self, mock_fetch, mock_conn):
        """API 异常但有旧数据 — 返回旧数据"""
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS fund_store (code TEXT PRIMARY KEY, data BLOB, updated_at REAL)"
        )
        old_data = {"ROE": 12}
        conn.execute(
            "INSERT OR REPLACE INTO fund_store VALUES (?, ?, ?)",
            ("000001", pickle.dumps(old_data), time.time() - 86400),
        )
        conn.commit()
        mock_conn.return_value = conn
        mock_fetch.side_effect = Exception("API error")
        result = cache.cached_fundamentals("000001")
        self.assertEqual(result["ROE"], 12)
        conn.close()

    @patch('stock_analyzer.cache._get_conn')
    @patch('stock_analyzer.cache.get_fundamentals')
    def test_api_error_no_data(self, mock_fetch, mock_conn):
        """API 异常且无旧数据 — 返回空 dict"""
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS fund_store (code TEXT PRIMARY KEY, data BLOB, updated_at REAL)"
        )
        mock_conn.return_value = conn
        mock_fetch.side_effect = Exception("API error")
        result = cache.cached_fundamentals("000001")
        self.assertIsInstance(result, dict)
        self.assertIsNone(result.get("ROE"))
        conn.close()

# ═══════════════════════════════════════════
# cached_kline — K线缓存
# ═══════════════════════════════════════════

class TestCachedKline(unittest.TestCase):
    """K线本地文件缓存"""

    def setUp(self):
        cache._MEM_CACHE.clear()

    def tearDown(self):
        cache._MEM_CACHE.clear()

    @patch('stock_analyzer.cache.get_kline')
    def test_mem_cache_hit(self, mock_fetch):
        """内存缓存命中"""
        df = _make_kline_df(60)
        cache._MEM_CACHE["kline:000001:60"] = (time.time(), df)
        result = cache.cached_kline("000001", days=60)
        mock_fetch.assert_not_called()
        self.assertEqual(len(result), 60)

    @patch('stock_analyzer.cache._load_kline_store')
    @patch('stock_analyzer.cache.get_kline')
    def test_store_fresh_sufficient(self, mock_fetch, mock_load):
        """存储数据新鲜且足够天数"""
        df = _make_kline_df(60)
        # 模拟日期截至昨天（新鲜数据）
        df["日期"] = pd.date_range(end=pd.Timestamp.now().normalize() - pd.Timedelta(days=1), periods=60)
        mock_load.return_value = df
        result = cache.cached_kline("000001", days=30)
        mock_fetch.assert_not_called()
        self.assertGreaterEqual(len(result), 30)

    @patch('stock_analyzer.cache._load_kline_store')
    @patch('stock_analyzer.cache._save_kline_store')
    @patch('stock_analyzer.cache.get_kline')
    def test_store_insufficient_full_refetch(self, mock_fetch, mock_save, mock_load):
        """存储不够天数，全量重拉"""
        store_df = _make_kline_df(10)  # only 10 in store
        mock_load.return_value = store_df
        full_df = _make_kline_df(60)
        mock_fetch.return_value = full_df
        result = cache.cached_kline("000001", days=60)
        mock_fetch.assert_called_once_with("000001", days=365)
        self.assertGreater(len(result), 10)

    @patch('stock_analyzer.cache._load_kline_store')
    @patch('stock_analyzer.cache._save_kline_store')
    @patch('stock_analyzer.cache.get_kline')
    def test_store_insufficient_refetch_fails(self, mock_fetch, mock_save, mock_load):
        """全量重拉失败，用已有数据兜底"""
        store_df = _make_kline_df(25)
        mock_load.return_value = store_df
        mock_fetch.side_effect = Exception("Network error")
        result = cache.cached_kline("000001", days=60)
        self.assertEqual(len(result), 25)

    @patch('stock_analyzer.cache._load_kline_store')
    @patch('stock_analyzer.cache._save_kline_store')
    @patch('stock_analyzer.cache.get_kline')
    def test_first_fetch_success(self, mock_fetch, mock_save, mock_load):
        """首次拉取成功（无历史数据）"""
        mock_load.return_value = None
        df = _make_kline_df(60)
        mock_fetch.return_value = df
        result = cache.cached_kline("000001", days=60)
        mock_fetch.assert_called()
        self.assertEqual(len(result), 60)

    @patch('stock_analyzer.cache._load_kline_store')
    @patch('stock_analyzer.cache._save_kline_store')
    @patch('stock_analyzer.cache.get_kline')
    def test_first_fetch_fails(self, mock_fetch, mock_save, mock_load):
        """首次拉取失败（无历史数据）— 返回空 DataFrame"""
        mock_load.return_value = None
        mock_fetch.side_effect = Exception("Network error")
        result = cache.cached_kline("000001", days=60)
        self.assertIsInstance(result, pd.DataFrame)
        self.assertTrue(result.empty)

# ═══════════════════════════════════════════
# cached_sectors / cached_national_team_holdings
# ═══════════════════════════════════════════

class TestCachedSectors(unittest.TestCase):
    """板块和机构持仓缓存"""

    def setUp(self):
        cache._MEM_CACHE.clear()

    def tearDown(self):
        cache._MEM_CACHE.clear()

    @patch('stock_analyzer.cache.get_sectors')
    def test_cached_sectors_mem_hit(self, mock_fetch):
        df = pd.DataFrame({"sector": ["半导体"], "code": ["000001"]})
        cache._MEM_CACHE["sectors"] = (time.time(), df)
        result = cache.cached_sectors()
        mock_fetch.assert_not_called()

    @patch('stock_analyzer.cache._get_conn')
    @patch('stock_analyzer.cache.get_sectors')
    def test_cached_sectors_perm_hit(self, mock_fetch, mock_conn):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sector_store (name TEXT PRIMARY KEY, data BLOB, updated_at REAL)"
        )
        df = pd.DataFrame({"sector": ["银行"], "code": ["000001"]})
        conn.execute(
            "INSERT OR REPLACE INTO sector_store VALUES (?, ?, ?)",
            ("all_sectors", pickle.dumps(df), time.time()),
        )
        conn.commit()
        mock_conn.return_value = conn
        result = cache.cached_sectors()
        mock_fetch.assert_not_called()
        self.assertGreater(len(result), 0)
        conn.close()

    @patch('stock_analyzer.cache._perm_load', return_value=None)
    @patch('stock_analyzer.cache.get_sectors')
    def test_cached_sectors_fetch_error(self, mock_fetch, mock_perm_load):
        mock_fetch.side_effect = Exception("fail")
        result = cache.cached_sectors()
        self.assertTrue(result.empty)

if __name__ == "__main__":
    unittest.main()
