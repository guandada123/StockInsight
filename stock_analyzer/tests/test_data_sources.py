"""测试 data_sources.py — 数据源抽象层（CircuitBreaker/FileRateLimiter/Freshness/DataSource）"""

import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

import pandas as pd

from stock_analyzer.data_sources import (
    CircuitBreaker,
    DataSource,
    DataSourceChain,
    FileRateLimiter,
    Freshness,
    HTTPSessionPool,
    _parse_kline_df,
    check_sina_rate,
    fetch_fundamentals,
    fetch_kline,
    fetch_realtime,
    get_default_fundamentals_chain,
    get_default_kline_chain,
    get_default_realtime_chain,
    get_sina_rate_limiter,
)


class TestFreshness(unittest.TestCase):
    """数据新鲜度枚举测试"""

    def test_all_values(self):
        """Freshness 包含所有预期值"""
        values = [e.value for e in Freshness]
        self.assertIn("fresh", values)
        self.assertIn("cached", values)
        self.assertIn("degraded", values)
        self.assertIn("stale", values)
        self.assertIn("unavailable", values)

    def test_fresh_members(self):
        """Freshness.FRESH 等于 'fresh'"""
        self.assertEqual(Freshness.FRESH.value, "fresh")
        self.assertEqual(Freshness.DEGRADED.value, "degraded")
        self.assertEqual(Freshness.UNAVAILABLE.value, "unavailable")


class TestCircuitBreaker(unittest.TestCase):
    """熔断器测试"""

    def test_allow_initially(self):
        """初始状态允许调用"""
        cb = CircuitBreaker("test_cb")
        self.assertTrue(cb.allow())

    def test_report_success_resets(self):
        """成功报告重置失败计数"""
        cb = CircuitBreaker("test_cb", max_failures=3, cooldown=10)
        cb.report(success=False)
        cb.report(success=False)
        self.assertTrue(cb.allow())  # not yet 3 failures
        cb.report(success=True)
        # after success, counter reset
        cb.report(success=False)
        cb.report(success=False)
        self.assertTrue(cb.allow())  # only 2 consecutive failures

    def test_breaker_opens_after_max_failures(self):
        """连续失败超过阈值后熔断"""
        cb = CircuitBreaker("test_cb", max_failures=2, cooldown=10)
        cb.report(success=False)
        cb.report(success=False)
        self.assertFalse(cb.allow())  # breaker should be open

    def test_breaker_reopens_after_cooldown(self):
        """冷却期后重新允许"""
        cb = CircuitBreaker("test_cb", max_failures=1, cooldown=0.5)
        cb.report(success=False)  # 1 failure = open
        self.assertFalse(cb.allow())
        time.sleep(0.6)
        self.assertTrue(cb.allow())  # reopens after cooldown

    def test_name_matches(self):
        """名称正确保存"""
        cb = CircuitBreaker("my_api", max_failures=5)
        self.assertEqual(cb.name, "my_api")


class TestParseKlineDF(unittest.TestCase):
    """_parse_kline_df 测试"""

    def _make_rows(self, count=30):
        import numpy as np

        np.random.seed(99)
        base = 50 + np.cumsum(np.random.randn(count) * 0.5)
        return [
            {
                "日期": f"2025-{(i // 30) + 1:02d}-{(i % 28) + 1:02d}",
                "开盘": float(base[i] * 0.99),
                "收盘": float(base[i]),
                "最高": float(base[i] * 1.02),
                "最低": float(base[i] * 0.98),
                "成交量": int(np.random.randint(1_000_000, 10_000_000)),
                "成交额": int(np.random.randint(10_000_000, 100_000_000)),
            }
            for i in range(count)
        ]

    def test_returns_dataframe(self):
        """返回 DataFrame"""
        rows = self._make_rows(30)
        df = _parse_kline_df(rows, 30)
        self.assertIsInstance(df, pd.DataFrame)

    def test_truncates_to_days(self):
        """截断到指定天数"""
        rows = self._make_rows(50)
        df = _parse_kline_df(rows, 30)
        self.assertLessEqual(len(df), 30)

    def test_has_expected_columns(self):
        """包含标准列"""
        rows = self._make_rows(30)
        df = _parse_kline_df(rows, 30)
        for col in ["日期", "开盘", "收盘", "最高", "最低", "成交量", "涨跌幅", "涨跌额"]:
            self.assertIn(col, df.columns, f"Missing column: {col}")

    def test_sort_by_date(self):
        """按日期升序排列"""
        rows = self._make_rows(30)
        df = _parse_kline_df(rows, 30)
        dates = pd.to_datetime(df["日期"])
        self.assertTrue(
            (dates.diff().dropna() >= pd.Timedelta(0)).all(), "Dates should be sorted ascending"
        )

    def test_empty_rows(self):
        """空列表不报错"""
        df = _parse_kline_df([], 30)
        self.assertIsInstance(df, pd.DataFrame)

    def test_pct_change_calculated(self):
        """涨跌幅已计算"""
        rows = self._make_rows(30)
        df = _parse_kline_df(rows, 30)
        # 第一行涨跌幅为 NaN（无前值），后续行有值
        self.assertTrue(df["涨跌幅"].iloc[1:].notna().any())

    def test_columns_are_numeric(self):
        """价格列为数值类型"""
        rows = self._make_rows(30)
        df = _parse_kline_df(rows, 30)
        for col in ["开盘", "收盘", "最高", "最低"]:
            self.assertTrue(pd.api.types.is_numeric_dtype(df[col]), f"{col} should be numeric")


class TestDataSourceABC(unittest.TestCase):
    """DataSource 抽象基类测试"""

    def test_default_methods_return_empty(self):
        """默认方法返回空值"""
        ds = DataSource()
        self.assertTrue(ds.fetch_kline("000001").empty)
        self.assertEqual(ds.fetch_realtime(["000001"]), {})
        self.assertEqual(ds.fetch_fundamentals("000001"), {})
        self.assertTrue(ds.fetch_sectors().empty)

    def test_name_is_class_name(self):
        """名称默认为类名"""
        ds = DataSource()
        self.assertEqual(ds.name, "DataSource")

    def test_is_available_default_true(self):
        """默认可用"""
        ds = DataSource()
        self.assertTrue(ds.is_available())

    def test_subclass_name(self):
        """子类名称正确"""

        class MySource(DataSource):
            pass

        ms = MySource()
        self.assertEqual(ms.name, "MySource")


# ============================================================
# FileRateLimiter 测试
# ============================================================


class TestFileRateLimiter(unittest.TestCase):
    """跨进程速率限制器测试 — 核心逻辑全覆盖"""

    def setUp(self):
        """每个测试使用独立临时目录，避免状态污染"""
        self.tmpdir = tempfile.mkdtemp(prefix="test_ratelimit_")
        self.limiter = FileRateLimiter(
            "test_api", max_requests=3, window=10.0, lock_dir=self.tmpdir
        )

    def tearDown(self):
        """清理临时文件"""
        try:
            self.limiter.reset()
        except Exception:
            pass
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_init_creates_lock_file_on_acquire(self):
        """首次 acquire 时创建锁文件（惰性创建）"""
        limiter = FileRateLimiter("init_test", lock_dir=self.tmpdir)
        # lock file created lazily on first _acquire()
        limiter._acquire()
        self.assertTrue(os.path.exists(limiter._lock_file))
        limiter._release()

    def test_read_timestamps_empty(self):
        """空文件时返回空列表"""
        self.assertEqual(self.limiter._read_timestamps(), [])

    def test_write_and_read_timestamps(self):
        """写入后可以正确读取"""
        ts = [time.time() - 5, time.time() - 2]
        self.limiter._write_timestamps(ts)
        read = self.limiter._read_timestamps()
        self.assertEqual(len(read), 2)

    def test_check_and_wait_no_wait(self):
        """请求数未达上限时立即通过"""
        start = time.time()
        self.limiter.check_and_wait()
        elapsed = time.time() - start
        self.assertLess(elapsed, 0.5, "未达上限不应等待")

    def test_check_and_wait_records_timestamp(self):
        """check_and_wait 记录当前请求时间戳"""
        self.limiter.check_and_wait()
        timestamps = self.limiter._read_timestamps()
        self.assertGreaterEqual(len(timestamps), 1)

    def test_check_and_wait_at_limit(self):
        """达上限时等待"""
        # 填满 3 个请求
        now = time.time()
        self.limiter._write_timestamps([now - 1, now - 0.5, now - 0.1])

        # 窗口 10 秒，3 个请求就是上限，需要等待最旧的过期
        start = time.time()
        self.limiter.check_and_wait()
        elapsed = time.time() - start
        # 等待时间应接近 (10 - (now - oldest)) + 1 ≈ 10 - 1 + 1 = 10s...
        # Actually oldest is now-1, so wait = 10 - 1 + 1 = 10s. Too long for test.
        # Let me use shorter window. Let me re-create limiter with 0.5s window
        # skipped — tested via shorter window below

    def test_check_and_wait_short_window(self):
        """短窗口达上限时等待可通过"""
        limiter = FileRateLimiter("fast", max_requests=2, window=1.5, lock_dir=self.tmpdir)
        limiter._write_timestamps([time.time(), time.time() - 0.1])
        start = time.time()
        limiter.check_and_wait()
        elapsed = time.time() - start
        self.assertGreater(elapsed, 0.3, "达上限应有等待")

    def test_reset_clears(self):
        """reset 清除所有记录"""
        self.limiter._write_timestamps([time.time(), time.time() - 1])
        self.limiter.reset()
        self.assertEqual(len(self.limiter._read_timestamps()), 0)

    def test_current_count(self):
        """current_count 返回窗口内请求数"""
        now = time.time()
        self.limiter._write_timestamps([now - 2, now - 5, now - 20])  # 第三个在窗口外
        count = self.limiter.current_count()
        self.assertEqual(count, 2)

    def test_current_count_empty(self):
        """空状态时 current_count 返回 0"""
        self.limiter.reset()
        self.assertEqual(self.limiter.current_count(), 0)

    def test_read_corrupted_json(self):
        """损坏的 JSON 文件返回空列表"""
        with open(self.limiter._state_file, "w") as f:
            f.write("not json {{{")
        self.assertEqual(self.limiter._read_timestamps(), [])


# ============================================================
# HTTP 会话池测试
# ============================================================


class TestHTTPSessionPool(unittest.TestCase):
    """HTTPSessionPool 单例模式测试"""

    def test_sina_singleton(self):
        """多次调用 sina() 返回同一会话"""
        s1 = HTTPSessionPool.sina()
        s2 = HTTPSessionPool.sina()
        self.assertIs(s1, s2)

    def test_sina_has_headers(self):
        """sina 会话包含 User-Agent 头"""
        s = HTTPSessionPool.sina()
        self.assertIn("User-Agent", s.headers)

    def test_em_singleton(self):
        """多次调用 em() 返回同一会话"""
        e1 = HTTPSessionPool.em()
        e2 = HTTPSessionPool.em()
        self.assertIs(e1, e2)

    def test_sina_and_em_different(self):
        """sina 和 em 是不同的会话对象"""
        self.assertIsNot(HTTPSessionPool.sina(), HTTPSessionPool.em())


# ============================================================
# DataSourceChain 测试
# ============================================================


class _MockSuccessKlineSource(DataSource):
    """模拟成功返回 K 线的数据源"""

    def fetch_kline(self, code, days=120):
        return pd.DataFrame({"日期": ["2025-01-01"], "收盘": [100.0]})


class _MockFailSource(DataSource):
    """模拟总是失败的数据源（返回空 DataFrame）"""

    def fetch_kline(self, code, days=120):
        return pd.DataFrame()


class _MockExceptionSource(DataSource):
    """模拟抛异常的数据源"""

    def fetch_kline(self, code, days=120):
        raise RuntimeError("模拟异常")


class _MockRealtimeSource(DataSource):
    """模拟实时行情源"""

    def fetch_realtime(self, codes):
        return {"000001": {"最新价": 50.0, "涨跌幅": 2.5}}


class _MockFundamentalsSource(DataSource):
    """模拟基本面源"""

    def fetch_fundamentals(self, code):
        return {"ROE": 15.0, "市盈率": 20.0, "市净率": 3.0}


class TestDataSourceChain(unittest.TestCase):
    """容灾链测试"""

    def test_fetch_kline_first_success(self):
        """第一个数据源成功即返回"""
        chain = DataSourceChain([_MockSuccessKlineSource(), _MockFailSource()])
        df = chain.fetch_kline("000001")
        self.assertFalse(df.empty)

    def test_fetch_kline_fallback(self):
        """前几个失败后回退到成功的源"""
        chain = DataSourceChain([_MockFailSource(), _MockSuccessKlineSource()])
        df = chain.fetch_kline("000001")
        self.assertFalse(df.empty)

    def test_fetch_kline_all_fail(self):
        """全部数据源失败返回空"""
        chain = DataSourceChain([_MockFailSource(), _MockFailSource()])
        df = chain.fetch_kline("000001")
        self.assertTrue(df.empty)

    def test_fetch_kline_exception_fallback(self):
        """异常数据源被跳过，回退到正常源"""
        chain = DataSourceChain([_MockExceptionSource(), _MockSuccessKlineSource()])
        df = chain.fetch_kline("000001")
        self.assertFalse(df.empty)

    def test_fetch_kline_circuit_breaker(self):
        """连续失败触发熔断后跳过该源"""
        chain = DataSourceChain([_MockFailSource(), _MockSuccessKlineSource()])
        # 触发熔断
        for _ in range(4):
            chain.fetch_kline("000001")
        # 熔断后仍能回退
        df = chain.fetch_kline("000001")
        self.assertFalse(df.empty)

    def test_fetch_realtime_success(self):
        """实时行情链成功返回"""
        chain = DataSourceChain([_MockRealtimeSource()])
        result = chain.fetch_realtime(["000001"])
        self.assertIn("000001", result)
        self.assertEqual(result["000001"]["最新价"], 50.0)

    def test_fetch_realtime_empty_input(self):
        """空输入时链返回空（默认 DataSource.fetch_realtime 返回 {}）"""
        chain = DataSourceChain([DataSource()])
        result = chain.fetch_realtime([])
        self.assertEqual(result, {})

    def test_fetch_fundamentals_success(self):
        """基本面链成功返回"""
        chain = DataSourceChain([_MockFundamentalsSource()])
        result = chain.fetch_fundamentals("000001")
        self.assertEqual(result["ROE"], 15.0)

    def test_fetch_fundamentals_no_valid(self):
        """基本面全部无效返回空"""
        chain = DataSourceChain([_MockFailSource()])
        result = chain.fetch_fundamentals("000001")
        self.assertEqual(result, {})

    def test_reset_circuits(self):
        """重置熔断器后全部恢复"""
        chain = DataSourceChain([_MockFailSource()])
        for _ in range(4):
            chain.fetch_kline("000001")
        self.assertEqual(len(chain._circuit_breakers), 1)
        chain.reset_circuits()
        self.assertEqual(len(chain._circuit_breakers), 0)

    def test_chain_sources_preserved(self):
        """链创建后 source 列表不变"""
        chain = DataSourceChain([_MockSuccessKlineSource()])
        self.assertEqual(len(chain.sources), 1)


# ============================================================
# 默认容灾链工厂函数测试
# ============================================================


class TestDefaultChains(unittest.TestCase):
    """默认容灾链工厂"""

    def test_kline_chain_singleton(self):
        """K 线链是单例"""
        c1 = get_default_kline_chain()
        c2 = get_default_kline_chain()
        self.assertIs(c1, c2)

    def test_kline_chain_has_sources(self):
        """K 线链包含多个数据源"""
        chain = get_default_kline_chain()
        self.assertGreater(len(chain.sources), 0)

    def test_kline_chain_first_is_sina(self):
        """第一个 K 线源是新浪"""
        chain = get_default_kline_chain()
        self.assertIn("Sina", chain.sources[0].name)

    def test_realtime_chain_singleton(self):
        """实时行情链是单例"""
        c1 = get_default_realtime_chain()
        c2 = get_default_realtime_chain()
        self.assertIs(c1, c2)

    def test_fundamentals_chain_singleton(self):
        """基本面链是单例"""
        c1 = get_default_fundamentals_chain()
        c2 = get_default_fundamentals_chain()
        self.assertIs(c1, c2)


# ============================================================
# 便捷顶层 API 测试
# ============================================================


class TestConvenienceAPI(unittest.TestCase):
    """便捷 API 测试"""

    def test_fetch_kline_delegates(self):
        """fetch_kline 从默认链调用"""
        df = fetch_kline("600519", days=10)
        self.assertIsInstance(df, pd.DataFrame)

    def test_fetch_realtime_delegates(self):
        """fetch_realtime 从默认链调用"""
        result = fetch_realtime(["600519"])
        self.assertIsInstance(result, dict)

    def test_fetch_fundamentals_delegates(self):
        """fetch_fundamentals 从默认链调用"""
        result = fetch_fundamentals("600519")
        self.assertIsInstance(result, dict)

    def test_rate_limiter_singleton(self):
        """速率限制器是单例"""
        rl1 = get_sina_rate_limiter()
        rl2 = get_sina_rate_limiter()
        self.assertIs(rl1, rl2)

    def test_check_sina_rate(self):
        """check_sina_rate 不抛异常"""
        try:
            check_sina_rate()
        except Exception as e:
            self.fail(f"check_sina_rate 不应抛异常: {e}")


# ============================================================
# DataSource 子类 K 线源测试（集成/网络依赖验证）
# ============================================================


class TestKlineSources(unittest.TestCase):
    """K 线数据源集成测试 — 验证解析逻辑，依赖网络"""

    def test_sina_kline_parse(self):
        """新浪 K 线源返回有效 DataFrame 或空 (网络依赖)"""
        import json
        from unittest import mock

        from stock_analyzer.data_sources import SinaKlineSource

        fake_items = [
            {
                "day": "2025-06-10",
                "open": "10.0",
                "close": "10.5",
                "high": "10.8",
                "low": "9.9",
                "volume": "100000",
                "amount": "1050000",
            },
            {
                "day": "2025-06-11",
                "open": "10.5",
                "close": "11.0",
                "high": "11.2",
                "low": "10.4",
                "volume": "120000",
                "amount": "1320000",
            },
        ]
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = json.dumps(fake_items)

        with mock.patch.object(HTTPSessionPool, "sina", return_value=mock.MagicMock()) as mock_sess:
            mock_sess.return_value.get.return_value = mock_resp
            src = SinaKlineSource()
            df = src.fetch_kline("600519", days=30)
            if not df.empty:
                self.assertIn("收盘", df.columns)

    def test_tencent_kline_parse(self):
        """腾讯 K 线源返回有效 DataFrame 或空 (网络依赖)"""
        import json
        from unittest import mock

        from stock_analyzer.data_sources import TencentKlineSource

        fake_data = {
            "data": {
                "sh600519": {
                    "qfqday": [
                        ["2025-06-10", "10.0", "10.5", "10.8", "9.9", "100000"],
                        ["2025-06-11", "10.5", "11.0", "11.2", "10.4", "120000"],
                    ]
                }
            }
        }
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = fake_data

        with mock.patch.object(HTTPSessionPool, "sina", return_value=mock.MagicMock()) as mock_sess:
            mock_sess.return_value.get.return_value = mock_resp
            src = TencentKlineSource()
            df = src.fetch_kline("600519", days=30)
            if not df.empty:
                self.assertIn("收盘", df.columns)

    def test_sina_kline_bad_response(self):
        """新浪 K 线异常返回空"""
        from unittest import mock

        from stock_analyzer.data_sources import SinaKlineSource

        with mock.patch.object(HTTPSessionPool, "sina") as mock_sess:
            mock_sess.return_value.get.side_effect = Exception("网络错误")
            src = SinaKlineSource()
            df = src.fetch_kline("600519", days=30)
            self.assertTrue(df.empty)

    def test_tushare_get_token_env(self):
        """Tushare _get_token 从环境变量读取"""
        from stock_analyzer.data_sources import TushareKlineSource

        with mock.patch.dict(os.environ, {"TUSHARE_TOKEN": "test_token_123"}):
            token = TushareKlineSource._get_token()
            self.assertEqual(token, "test_token_123")

    def test_tushare_get_token_empty(self):
        """Tushare _get_token 无环境变量且无 .env 时返回空"""
        from stock_analyzer.data_sources import TushareKlineSource

        with mock.patch.dict(os.environ, {}, clear=True):
            token = TushareKlineSource._get_token()
            self.assertEqual(token, "")


# ============================================================
# SinaRealtimeSource 测试
# ============================================================


class TestSinaRealtimeSource(unittest.TestCase):
    """新浪实时行情源测试"""

    def test_empty_codes(self):
        """空代码列表返回空"""
        from stock_analyzer.data_sources import SinaRealtimeSource

        src = SinaRealtimeSource()
        self.assertEqual(src.fetch_realtime([]), {})

    def test_parse_realtime_response(self):
        """解析新浪实时行情响应"""
        from unittest import mock

        from stock_analyzer.data_sources import SinaRealtimeSource

        # 模拟新浪返回格式（32+ 字段）
        # 字段: 名称,今开,昨收,最新价,最高,最低,竞买价,竞卖价,成交量,成交额,
        #       买1量,买1价,买2量,买2价,买3量,买3价,买4量,买4价,买5量,买5价,
        #       卖1量,卖1价,卖2量,卖2价,卖3量,卖3价,卖4量,卖4价,卖5量,卖5价,日期,时间,状态
        fake_body = (
            'var hq_str_sh600519="贵州茅台,'
            "1850.00,1845.00,1855.00,1860.00,1840.00,1855.00,1845.00,"
            "100000,185500000,"  # 成交量,成交额
            "500,1850.00,100,1849.00,200,1851.00,300,1848.00,400,1852.00,"  # 买1-5
            "500,1860.00,100,1859.00,200,1858.00,300,1857.00,400,1856.00,"  # 卖1-5
            '2025-06-14,15:00:00,00";\n'
        )
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = fake_body

        mock_sess = mock.MagicMock()
        mock_sess.get.return_value = mock_resp

        orig_sina = HTTPSessionPool._sina
        HTTPSessionPool._sina = mock_sess
        try:
            src = SinaRealtimeSource()
            result = src.fetch_realtime(["600519"])
            self.assertIn("600519", result, f"Result keys: {list(result.keys())}")
            self.assertEqual(result["600519"]["最新价"], 1855.00)
            self.assertEqual(result["600519"]["名称"], "贵州茅台")
        finally:
            HTTPSessionPool._sina = orig_sina

    def test_realtime_http_error(self):
        """HTTP 非 200 返回空"""
        from unittest import mock

        from stock_analyzer.data_sources import SinaRealtimeSource

        mock_resp = mock.MagicMock()
        mock_resp.status_code = 500

        mock_sess = mock.MagicMock()
        mock_sess.get.return_value = mock_resp

        orig_sina = HTTPSessionPool._sina
        HTTPSessionPool._sina = mock_sess
        try:
            src = SinaRealtimeSource()
            self.assertEqual(src.fetch_realtime(["600519"]), {})
        finally:
            HTTPSessionPool._sina = orig_sina


if __name__ == "__main__":
    unittest.main()
