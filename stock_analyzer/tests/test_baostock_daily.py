"""测试 baostock_daily.py — 60分钟线数据加载

注意事项：
- baostock_daily.py 有模块级代码，导入时执行 DatabaseUtils.connect_to_mysql()
  和 cursor.execute("CREATE TABLE...")，因此必须在导入前预先 mock db_utils。
- import baostock as bs 也在模块级，同样需要预先 mock。
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock, call

# ── 导入前的准备：mock 模块级依赖 ──────────────────────────────────────
_pre_mock_db = MagicMock()
_pre_mock_db.DatabaseUtils.connect_to_mysql.return_value = (MagicMock(), MagicMock())
sys.modules["db_utils"] = _pre_mock_db

_pre_mock_bs = MagicMock()
sys.modules["baostock"] = _pre_mock_bs
# 模块级代码会在 import 时自动执行（使用上方的 mock），cc 先导入一次
import stock_analyzer.baostock_daily as bd

class TestGet60minStockDataBs(unittest.TestCase):
    """get_60min_stock_data_bs — baostock 60分钟线数据获取"""

    def setUp(self):
        # 重置 bs query_history_k_data_plus mock
        self.patcher = patch("stock_analyzer.baostock_daily.bs.query_history_k_data_plus")
        self.mock_query = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def _make_result_set(self, rows, fields=None):
        """构造模拟的 baostock 结果集对象"""
        if fields is None:
            fields = ["date", "time", "code", "open", "high", "low", "close",
                       "volume", "amount"]
        rs = MagicMock()
        rs.error_code = "0"
        rs.fields = fields
        # 逐个返回行：第一次 True（有数据），第二次 False（结束）
        row_iter = iter(rows)
        rs.next.side_effect = lambda: next(row_iter, False)
        rs.get_row_data.side_effect = lambda: rows[len(rows) - len(list(iter(rows)))]  # 简化
        # 更简单的实现：用一个 index 跟踪
        return rs

    def test_successful_query_returns_dataframe(self):
        """正常查询 → 返回 DataFrame"""
        rs = MagicMock()
        rs.error_code = "0"
        rs.fields = ["date", "time", "code", "open", "high", "low", "close",
                      "volume", "amount"]
        rs.next.side_effect = [True, True, False]
        rs.get_row_data.side_effect = [
            ["2025-06-01", "20250601140000", "sh.600519", "1500.0", "1510.0",
             "1490.0", "1505.0", "10000", "15000000.0"],
            ["2025-06-01", "20250601143000", "sh.600519", "1505.0", "1520.0",
             "1500.0", "1515.0", "12000", "18180000.0"],
        ]
        self.mock_query.return_value = rs

        df = bd.get_60min_stock_data_bs("sh.600519", "2025-06-01", "2025-06-01")

        self.assertIsNotNone(df)
        self.assertEqual(len(df), 2)
        self.assertIn("code", df.columns)
        self.assertIn("close", df.columns)

    def test_empty_result(self):
        """无数据 → 空 DataFrame"""
        rs = MagicMock()
        rs.error_code = "0"
        rs.fields = ["date", "time", "code", "open", "high", "low", "close",
                      "volume", "amount"]
        rs.next.return_value = False
        self.mock_query.return_value = rs

        df = bd.get_60min_stock_data_bs("sh.600519", "2099-01-01", "2099-01-01")

        self.assertIsNotNone(df)
        self.assertTrue(df.empty)

    def test_query_called_with_correct_params(self):
        """查询参数正确传递"""
        rs = MagicMock()
        rs.error_code = "0"
        rs.fields = ["date"]
        rs.next.return_value = False
        self.mock_query.return_value = rs

        bd.get_60min_stock_data_bs("sz.000001", "2025-01-01", "2025-01-31")

        self.mock_query.assert_called_once_with(
            "sz.000001",
            "date,time,code,open,high,low,close,volume,amount",
            start_date="2025-01-01",
            end_date="2025-01-31",
            frequency="d",
            adjustflag="2",
        )

class TestMain(unittest.TestCase):
    """main() 主流程"""

    def setUp(self):
        # 清理缓存，让每个测试独立重新导入模块
        if "stock_analyzer.baostock_daily" in sys.modules:
            del sys.modules["stock_analyzer.baostock_daily"]

        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()

        self.mock_db = MagicMock()
        self.mock_db.DatabaseUtils.connect_to_mysql.return_value = (
            self.mock_conn, self.mock_cursor
        )
        sys.modules["db_utils"] = self.mock_db

        # baostock 也需要重置
        self.mock_bs = MagicMock()
        sys.modules["baostock"] = self.mock_bs

    def _import_module(self):
        """重新导入 baostock_daily 并返回模块对象"""
        import importlib
        mod = importlib.import_module("stock_analyzer.baostock_daily")
        return mod

    def test_no_stocks_skips_baostock(self):
        """无股票列表 → bs.login 仍被调用（在循环外），但不获取数据"""
        self.mock_cursor.fetchall.return_value = []
        mod = self._import_module()
        mod.main()
        # login 在 for 循环外，即使无股票也被调用
        self.mock_bs.login.assert_called_once()
        # 没有数据 → 不 commit
        self.mock_conn.commit.assert_not_called()
        self.mock_cursor.close.assert_called_once()
        self.mock_conn.close.assert_called_once()
        self.mock_bs.logout.assert_called_once()

    @patch("stock_analyzer.baostock_daily.get_60min_stock_data_bs")
    def test_normal_flow_with_one_batch(self, mock_get_data):
        """单批次正常流程：获取数据 → 插入 → commit"""
        self.mock_cursor.fetchall.return_value = [
            ("000001.SZ",), ("600519.SH",),
        ]

        import pandas as pd
        test_df = pd.DataFrame([{
            "date": "2025-06-01", "time": "20250601140000",
            "code": "sz.000001", "open": "10.0", "high": "11.0",
            "low": "9.5", "close": "10.5", "volume": "100000",
            "amount": "1050000.0",
        }])
        mock_get_data.return_value = test_df

        mod = self._import_module()
        mod.main()

        # 对每只股票调用了 get_60min_stock_data_bs
        self.assertEqual(mock_get_data.call_count, 2)
        # cursor.execute 被调用（INSERT IGNORE）
        self.mock_cursor.execute.assert_called()
        # conn.commit 被调用
        self.mock_conn.commit.assert_called_once()
        # 清理
        self.mock_cursor.close.assert_called_once()
        self.mock_conn.close.assert_called_once()
        self.mock_bs.logout.assert_called_once()

    @patch("stock_analyzer.baostock_daily.get_60min_stock_data_bs")
    def test_error_row_does_not_crash(self, mock_get_data):
        """异常行不中断整个流程"""
        self.mock_cursor.fetchall.return_value = [
            ("000001.SZ",),
        ]

        import pandas as pd
        # 制造一行缺 time 字段的数据 → cursor.execute 抛异常
        bad_df = pd.DataFrame([{
            "date": "2025-06-01", "time": None,
            "code": "sz.000001", "open": "10.0", "high": "11.0",
            "low": "9.5", "close": "10.5", "volume": "100000",
            "amount": "1050000.0",
        }])
        mock_get_data.return_value = bad_df

        mod = self._import_module()
        # 不应该抛出异常（内部 try/except/continue 处理了）
        try:
            mod.main()
        except Exception:
            self.fail("main() raised an exception for bad row data")

        self.mock_bs.logout.assert_called_once()
        self.mock_cursor.close.assert_called_once()
        self.mock_conn.close.assert_called_once()

if __name__ == "__main__":
    unittest.main()
