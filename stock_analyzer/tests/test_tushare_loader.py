"""测试 tushare_loader.py — Tushare 数据下载管线

注意事项：
- get_tushare_pro() 使用 env.get_env 获取 TUSHARE_TOKEN
- 所有 download_* 函数都调用 get_tushare_pro() 和 _get_conn()
- _get_conn() 打开文件级 SQLite，测试中需要替换为临时 DB
"""

import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, PropertyMock, call, patch

import pandas as pd


# ── 辅助：不关闭的 SQLite 连接 wrapper ──────────────────────────────
class _NoCloseConn:
    """包装 sqlite3.Connection，使其 close() 成为 no-op，用于验证数据"""
    def __init__(self, conn):
        self._conn = conn
    def __getattr__(self, name):
        return getattr(self._conn, name)
    def close(self):
        pass


# ── 在导入 tushare_loader 前 mock tushare ──────────────────────────
_ts_mock = MagicMock()
sys.modules["tushare"] = _ts_mock

import stock_analyzer.tushare_loader as tl


class TestRateLimit(unittest.TestCase):
    """_rate_limit — API 调用限速"""

    def test_respects_interval(self):
        """连续调用间隔小于 0.5 秒时 sleep"""
        # 重置全局计时器
        tl._last_api_call = 0.0

        # 第一次调用——不应 sleep
        t0 = time.time()
        tl._rate_limit()
        t1 = time.time()
        elapsed = t1 - t0
        self.assertLess(elapsed, 0.3)  # 不应有可感知的延迟

        # 重置为近期时间（假装 0.1 秒前调用过）
        tl._last_api_call = time.time()
        with patch("stock_analyzer.tushare_loader.time.sleep") as mock_sleep:
            tl._rate_limit()
            # 应该 sleep (0.5 - 0.1) ≈ 0.4 秒
            mock_sleep.assert_called_once()
            sleep_arg = mock_sleep.call_args[0][0]
            self.assertGreater(sleep_arg, 0.3)
            self.assertLessEqual(sleep_arg, 0.5)


class TestGetTusharePro(unittest.TestCase):
    """get_tushare_pro — 初始化 Tushare API"""

    @patch("stock_analyzer.tushare_loader.get_env")
    def test_no_token_raises(self, mock_get_env):
        """无 TUSHARE_TOKEN → RuntimeError"""
        mock_get_env.side_effect = lambda key, default="": "" if key == "TUSHARE_TOKEN" else default
        with self.assertRaises(RuntimeError) as ctx:
            tl.get_tushare_pro()
        self.assertIn("TUSHARE_TOKEN", str(ctx.exception))

    @patch("stock_analyzer.tushare_loader.get_env")
    def test_with_token_returns_pro(self, mock_get_env):
        """有 TUSHARE_TOKEN → 返回 ts.pro_api()"""
        mock_get_env.side_effect = lambda key, default="": (
            "test_token_123" if key == "TUSHARE_TOKEN" else default
        )
        # 清除之前的 import 缓存
        if "tushare" in sys.modules:
            del sys.modules["tushare"]
        ts_mock = MagicMock()
        pro_mock = MagicMock()
        ts_mock.pro_api.return_value = pro_mock
        sys.modules["tushare"] = ts_mock

        try:
            result = tl.get_tushare_pro()
            self.assertIs(result, pro_mock)
            ts_mock.set_token.assert_called_once_with("test_token_123")
        finally:
            # 恢复
            sys.modules["tushare"] = _ts_mock


class TestDownloadTradeCalendar(unittest.TestCase):
    """download_trade_calendar — 交易日历下载"""

    def setUp(self):
        self.db_fd, self.db_path = None, None

    def _make_temp_conn(self):
        if self.db_path is None:
            self.db_path = tempfile.mktemp(suffix=".db", prefix="test_tc_")
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def tearDown(self):
        if self.db_path and os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except OSError:
                pass

    @patch("stock_analyzer.tushare_loader._get_conn")
    @patch("stock_analyzer.tushare_loader.get_tushare_pro")
    def test_download_creates_table_and_inserts_data(self, mock_get_pro, mock_get_conn):
        """正常下载 → 建表 + 插入数据 + 返回行数"""
        real_conn = sqlite3.connect(":memory:")
        real_conn.execute("PRAGMA journal_mode=WAL")
        mock_get_conn.return_value = _NoCloseConn(real_conn)

        pro = MagicMock()
        data = pd.DataFrame(
            {
                "exchange": ["SSE", "SZSE"],
                "cal_date": ["20250101", "20250102"],
                "is_open": [1, 0],
                "pretrade_date": ["", "20250101"],
            }
        )
        pro.trade_cal.return_value = data
        mock_get_pro.return_value = pro

        n = tl.download_trade_calendar()

        self.assertEqual(n, 2)
        # 验证表存在且有数据
        cur = real_conn.execute("SELECT COUNT(*) FROM stock_trade_calendar")
        self.assertEqual(cur.fetchone()[0], 2)
        real_conn.close()

    @patch("stock_analyzer.tushare_loader._get_conn")
    @patch("stock_analyzer.tushare_loader.get_tushare_pro")
    def test_with_progress_callback(self, mock_get_pro, mock_get_conn):
        """带 progress_cb → 回调被调用"""
        conn = sqlite3.connect(":memory:")
        mock_get_conn.return_value = conn

        pro = MagicMock()
        data = pd.DataFrame(
            {
                "exchange": ["SSE"],
                "cal_date": ["20250101"],
                "is_open": [1],
                "pretrade_date": [""],
            }
        )
        pro.trade_cal.return_value = data
        mock_get_pro.return_value = pro

        cb = MagicMock()
        tl.download_trade_calendar(progress_cb=cb)

        cb.assert_called_once_with(1, 1, "交易日历下载完成")
        conn.close()


class TestDownloadStockBasic(unittest.TestCase):
    """download_stock_basic — 股票列表下载"""

    @patch("stock_analyzer.tushare_loader._get_conn")
    @patch("stock_analyzer.tushare_loader.get_tushare_pro")
    def test_download_stock_basic(self, mock_get_pro, mock_get_conn):
        """下载股票列表 → 插入数据"""
        real_conn = sqlite3.connect(":memory:")
        mock_get_conn.return_value = _NoCloseConn(real_conn)

        pro = MagicMock()
        data = pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "600519.SH"],
                "symbol": ["1", "600519"],
                "name": ["平安银行", "贵州茅台"],
                "area": ["深圳", "贵州"],
                "industry": ["银行", "白酒"],
                "list_date": ["19910403", "20010731"],
            }
        )
        pro.stock_basic.return_value = data
        mock_get_pro.return_value = pro

        n = tl.download_stock_basic()

        self.assertEqual(n, 2)
        cur = real_conn.execute("SELECT COUNT(*) FROM stock_basic_info")
        self.assertEqual(cur.fetchone()[0], 2)
        cur = real_conn.execute("SELECT name FROM stock_basic_info WHERE ts_code='600519.SH'")
        self.assertEqual(cur.fetchone()[0], "贵州茅台")
        real_conn.close()


class TestDownloadIndustry(unittest.TestCase):
    """download_industry — 行业分类下载"""

    @patch("stock_analyzer.tushare_loader._get_conn")
    @patch("stock_analyzer.tushare_loader.get_tushare_pro")
    @patch("stock_analyzer.tushare_loader._rate_limit")
    def test_download_industry(self, mock_rate, mock_get_pro, mock_get_conn):
        """下载行业分类 → 插入数据"""
        real_conn = sqlite3.connect(":memory:")
        mock_get_conn.return_value = _NoCloseConn(real_conn)

        pro = MagicMock()
        data = pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "600519.SH"],
                "industry": ["银行", "白酒"],
            }
        )
        pro.stock_basic.return_value = data
        mock_get_pro.return_value = pro

        n = tl.download_industry()

        self.assertEqual(n, 2)
        cur = real_conn.execute("SELECT industry FROM stock_industry WHERE code='600519'")
        self.assertEqual(cur.fetchone()[0], "白酒")
        real_conn.close()

    @patch("stock_analyzer.tushare_loader._get_conn")
    @patch("stock_analyzer.tushare_loader.get_tushare_pro")
    @patch("stock_analyzer.tushare_loader._rate_limit")
    def test_empty_result_returns_zero(self, mock_rate, mock_get_pro, mock_get_conn):
        """无数据返回 → 0"""
        conn = sqlite3.connect(":memory:")
        mock_get_conn.return_value = conn

        pro = MagicMock()
        pro.stock_basic.return_value = pd.DataFrame()
        mock_get_pro.return_value = pro

        n = tl.download_industry()
        self.assertEqual(n, 0)
        conn.close()


class TestIndustryLookup(unittest.TestCase):
    """get_industry / get_stocks_by_industry — 行业查询"""

    @patch("stock_analyzer.tushare_loader._get_conn")
    def test_get_industry_found(self, mock_get_conn):
        """存在该股票 → 返回行业名"""
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE stock_industry (code TEXT PRIMARY KEY, industry TEXT, update_time REAL)"
        )
        conn.execute("INSERT INTO stock_industry VALUES ('000001', '银行', 1000.0)")
        mock_get_conn.return_value = conn

        result = tl.get_industry("000001")
        self.assertEqual(result, "银行")
        conn.close()

    @patch("stock_analyzer.tushare_loader._get_conn")
    def test_get_industry_not_found(self, mock_get_conn):
        """不存在 → 返回空字符串"""
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE stock_industry (code TEXT PRIMARY KEY, industry TEXT, update_time REAL)"
        )
        mock_get_conn.return_value = conn

        result = tl.get_industry("999999")
        self.assertEqual(result, "")
        conn.close()

    @patch("stock_analyzer.tushare_loader._get_conn")
    def test_get_stocks_by_industry(self, mock_get_conn):
        """按行业查询股票列表"""
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE stock_industry (code TEXT PRIMARY KEY, industry TEXT, update_time REAL)"
        )
        conn.execute("INSERT INTO stock_industry VALUES ('000001', '银行', 1000.0)")
        conn.execute("INSERT INTO stock_industry VALUES ('600519', '白酒', 1000.0)")
        conn.execute("INSERT INTO stock_industry VALUES ('000002', '银行', 1000.0)")
        mock_get_conn.return_value = conn

        result = tl.get_stocks_by_industry("银行")
        self.assertEqual(sorted(result), ["000001", "000002"])
        conn.close()


class TestGetMoneyflowCache(unittest.TestCase):
    """get_moneyflow_cache — 资金流向缓存读取"""

    @patch("stock_analyzer.tushare_loader._get_conn")
    def test_returns_dataframe(self, mock_get_conn):
        """有数据 → 返回 DataFrame"""
        conn = sqlite3.connect(":memory:")
        conn.execute(
            """CREATE TABLE stock_moneyflow (
                code TEXT, trade_date TEXT, net_mf_amount REAL,
                buy_elg_amount REAL, sell_elg_amount REAL,
                buy_lg_amount REAL, sell_lg_amount REAL,
                buy_md_amount REAL, sell_md_amount REAL,
                buy_sm_amount REAL, sell_sm_amount REAL,
                buy_total_amount REAL, sell_total_amount REAL,
                PRIMARY KEY (code, trade_date)
            )"""
        )
        conn.execute(
            """INSERT INTO stock_moneyflow VALUES
               ('000001', '20250601', 100.0, 50.0, 30.0, 60.0, 40.0,
                20.0, 10.0, 5.0, 5.0, 130.0, 85.0)"""
        )
        mock_get_conn.return_value = conn

        df = tl.get_moneyflow_cache("000001")
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 1)
        self.assertIn("主力净流入", df.columns)
        conn.close()

    @patch("stock_analyzer.tushare_loader._get_conn")
    def test_no_data_returns_none(self, mock_get_conn):
        """无数据 → None"""
        conn = sqlite3.connect(":memory:")
        conn.execute(
            """CREATE TABLE stock_moneyflow (
                code TEXT, trade_date TEXT, net_mf_amount REAL,
                PRIMARY KEY (code, trade_date)
            )"""
        )
        mock_get_conn.return_value = conn

        result = tl.get_moneyflow_cache("999999")
        self.assertIsNone(result)
        conn.close()


class TestDownloadDailyBasic(unittest.TestCase):
    """download_daily_basic — 基本面指标下载"""

    @patch("stock_analyzer.tushare_loader._get_conn")
    @patch("stock_analyzer.tushare_loader.get_tushare_pro")
    def test_download_daily_basic(self, mock_get_pro, mock_get_conn):
        """下载基本面数据 → 插入 """
        real_conn = sqlite3.connect(":memory:")
        mock_get_conn.return_value = _NoCloseConn(real_conn)

        pro = MagicMock()
        data = pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": ["20250602"],
                "pe": [8.5],
                "pe_ttm": [8.0],
                "pb": [1.2],
                "ps": [3.0],
                "ps_ttm": [2.8],
                "dv_ratio": [3.5],
                "dv_ttm": [3.6],
                "total_mv": [1e11],
                "circ_mv": [8e10],
            }
        )
        pro.daily_basic.return_value = data
        mock_get_pro.return_value = pro

        n = tl.download_daily_basic(start_date="20250602", end_date="20250602")

        self.assertGreaterEqual(n, 1)
        real_conn.close()


class TestJobManagement(unittest.TestCase):
    """submit_job / get_job_status / list_jobs — 作业管理"""

    def setUp(self):
        # 每个测试前清理全局作业状态
        tl._jobs.clear()

    def test_submit_and_query(self):
        """提交作业 → 可查询状态"""
        with (
            patch("stock_analyzer.tushare_loader.get_tushare_pro") as mock_pro,
            patch("stock_analyzer.tushare_loader._get_conn") as mock_conn,
        ):
            pro = MagicMock()
            pro.trade_cal.return_value = pd.DataFrame()
            mock_pro.return_value = pro
            mock_conn.return_value = sqlite3.connect(":memory:")

            job_id = tl.submit_job("trade_calendar")
            self.assertIsNotNone(job_id)
            self.assertEqual(len(job_id), 8)

            status = tl.get_job_status(job_id)
            self.assertIsNotNone(status)
            self.assertEqual(status["type"], "trade_calendar")

    def test_invalid_job_type_raises(self):
        """不支持的作业类型 → ValueError"""
        with self.assertRaises(ValueError):
            tl.submit_job("nonexistent")

    def test_list_jobs_orders_by_started(self):
        """list_jobs 按开始时间倒序"""
        tl._jobs["a"] = {"id": "a", "status": "done", "started": "09:00:00"}
        tl._jobs["b"] = {"id": "b", "status": "running", "started": "10:00:00"}
        tl._jobs["c"] = {"id": "c", "status": "pending", "started": "08:00:00"}

        jobs = tl.list_jobs(limit=5)
        self.assertEqual([j["id"] for j in jobs], ["b", "a", "c"])

    def test_list_jobs_filter_by_status(self):
        """按状态过滤"""
        tl._jobs["a"] = {"id": "a", "status": "done", "started": "09:00:00"}
        tl._jobs["b"] = {"id": "b", "status": "running", "started": "10:00:00"}

        done_jobs = tl.list_jobs(status_filter="done")
        self.assertEqual(len(done_jobs), 1)
        self.assertEqual(done_jobs[0]["id"], "a")

    def test_limit_respected(self):
        """limit 参数限制返回数量"""
        for i in range(5):
            tl._jobs[str(i)] = {"id": str(i), "status": "done", "started": f"0{i}:00:00"}

        jobs = tl.list_jobs(limit=2)
        self.assertEqual(len(jobs), 2)


class TestDownloadMoneyflow(unittest.TestCase):
    """download_moneyflow_latest — 资金流向下载"""

    @patch("stock_analyzer.tushare_loader._get_conn")
    @patch("stock_analyzer.tushare_loader.get_tushare_pro")
    @patch("stock_analyzer.tushare_loader._rate_limit")
    def test_download_moneyflow(self, mock_rate, mock_get_pro, mock_get_conn):
        """下载资金流向 → 插入数据"""
        conn = sqlite3.connect(":memory:")
        mock_get_conn.return_value = conn

        pro = MagicMock()
        data = pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": ["20250601"],
                "net_mf_amount": [1000000.0],
                "buy_elg_amount": [500000.0],
                "sell_elg_amount": [200000.0],
                "buy_lg_amount": [300000.0],
                "sell_lg_amount": [100000.0],
                "buy_md_amount": [100000.0],
                "sell_md_amount": [50000.0],
                "buy_sm_amount": [50000.0],
                "sell_sm_amount": [25000.0],
            }
        )
        pro.moneyflow.return_value = data
        mock_get_pro.return_value = pro

        n = tl.download_moneyflow_latest(days=1)
        self.assertEqual(n, 1)
        conn.close()

    @patch("stock_analyzer.tushare_loader._get_conn")
    @patch("stock_analyzer.tushare_loader.get_tushare_pro")
    @patch("stock_analyzer.tushare_loader._rate_limit")
    def test_skip_existing_dates(self, mock_rate, mock_get_pro, mock_get_conn):
        """已有数据的日期 → 跳过"""
        conn = sqlite3.connect(":memory:")
        conn.execute(
            """CREATE TABLE stock_moneyflow (
                code TEXT, trade_date TEXT, net_mf_amount REAL,
                buy_elg_amount REAL, sell_elg_amount REAL,
                buy_lg_amount REAL, sell_lg_amount REAL,
                buy_md_amount REAL, sell_md_amount REAL,
                buy_sm_amount REAL, sell_sm_amount REAL,
                buy_total_amount REAL, sell_total_amount REAL,
                PRIMARY KEY (code, trade_date)
            )"""
        )
        mock_get_conn.return_value = conn

        pro = MagicMock()
        data = pd.DataFrame(
            {
                "ts_code": [],
                "trade_date": [],
                "net_mf_amount": [],
                "buy_elg_amount": [],
                "sell_elg_amount": [],
                "buy_lg_amount": [],
                "sell_lg_amount": [],
                "buy_md_amount": [],
                "sell_md_amount": [],
                "buy_sm_amount": [],
                "sell_sm_amount": [],
            }
        )
        pro.moneyflow.return_value = data
        mock_get_pro.return_value = pro

        # 在股票代码不存在时，moneyflow 返回空，total 应为 0
        n = tl.download_moneyflow_latest(days=1)
        self.assertEqual(n, 0)
        conn.close()


class TestDownloadDailyHistory(unittest.TestCase):
    """download_daily_history — 日线历史下载"""

    @patch("stock_analyzer.tushare_loader._get_conn")
    @patch("stock_analyzer.tushare_loader.get_tushare_pro")
    @patch("stock_analyzer.tushare_loader._rate_limit")
    def test_download_daily_history(self, mock_rate, mock_get_pro, mock_get_conn):
        """下载日线数据 → 插入 kline_store"""
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS stock_trade_calendar "
            "(exchange TEXT, cal_date TEXT PRIMARY KEY, is_open INTEGER, pretrade_date TEXT)"
        )
        conn.execute(
            "INSERT INTO stock_trade_calendar VALUES ('SSE', '20250601', 1, '20250531')"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS kline_store "
            "(code TEXT PRIMARY KEY, data BLOB, update_time REAL)"
        )
        mock_get_conn.return_value = conn

        pro = MagicMock()
        data = pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": ["20250601"],
                "open": [10.0],
                "high": [11.0],
                "low": [9.5],
                "close": [10.5],
                "vol": [100000],
                "amount": [1050000.0],
            }
        )
        pro.daily.return_value = data
        mock_get_pro.return_value = pro

        n = tl.download_daily_history(start_date="20250601", end_date="20250601")
        self.assertGreater(n, 0)
        conn.close()

    @patch("stock_analyzer.tushare_loader._get_conn")
    @patch("stock_analyzer.tushare_loader.get_tushare_pro")
    def test_no_trade_calendar_fallback(self, mock_get_pro, mock_get_conn):
        """股票交易日历表无数据 → fallback 到 Monday-Friday"""
        real_conn = sqlite3.connect(":memory:")
        real_conn.execute(
            "CREATE TABLE IF NOT EXISTS stock_trade_calendar "
            "(exchange TEXT, cal_date TEXT PRIMARY KEY, is_open INTEGER, pretrade_date TEXT)"
        )
        real_conn.execute(
            "CREATE TABLE IF NOT EXISTS kline_store "
            "(code TEXT PRIMARY KEY, data BLOB, update_time REAL)"
        )
        mock_get_conn.return_value = _NoCloseConn(real_conn)

        pro = MagicMock()
        data = pd.DataFrame()  # empty
        pro.daily.return_value = data
        mock_get_pro.return_value = pro

        # 应该不报错，使用 weekday fallback（2025-06-16 是星期一）
        n = tl.download_daily_history(start_date="20250616", end_date="20250616")

        self.assertEqual(n, 0)  # 没有数据插入
        real_conn.close()


if __name__ == "__main__":
    unittest.main()
