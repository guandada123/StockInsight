"""测试 daily_history_by_date.py — 股票日线行情按交易日导入"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# db_utils 和 job_env 不是独立安装的模块，导入前 mock
sys.modules["db_utils"] = MagicMock()
sys.modules["job_env"] = MagicMock()


class TestEnsureTable(unittest.TestCase):
    """ensure_table 表创建"""

    def test_create_table_sql(self):
        """执行建表 SQL 包含关键字段"""
        from stock_analyzer.daily_history_by_date import ensure_table

        cursor = MagicMock()
        ensure_table(cursor)
        cursor.execute.assert_called_once()
        sql = cursor.execute.call_args[0][0]
        self.assertIn("CREATE TABLE IF NOT EXISTS `stock_daily_history`", sql)
        self.assertIn("PRIMARY KEY (`ts_code`,`trade_date`)", sql)
        self.assertIn("close", sql)
        self.assertIn("amount", sql)


class TestUpsertTradeDate(unittest.TestCase):
    """upsert_trade_date 数据写入"""

    def setUp(self):
        self.cursor = MagicMock()

    def test_none_df_returns_zero(self):
        """df 为 None → 返回 0"""
        from stock_analyzer.daily_history_by_date import upsert_trade_date

        n = upsert_trade_date(self.cursor, None)
        self.assertEqual(n, 0)
        self.cursor.executemany.assert_not_called()

    def test_empty_df_returns_zero(self):
        """空 DataFrame → 返回 0"""
        import pandas as pd

        from stock_analyzer.daily_history_by_date import upsert_trade_date

        n = upsert_trade_date(self.cursor, pd.DataFrame())
        self.assertEqual(n, 0)
        self.cursor.executemany.assert_not_called()

    def test_normal_df_calls_executemany(self):
        """正常数据 → 调用 executemany"""
        import pandas as pd

        from stock_analyzer.daily_history_by_date import upsert_trade_date

        df = pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "2025-06-01",
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.5,
                    "close": 10.5,
                    "pre_close": 10.0,
                    "change": 0.5,
                    "pct_chg": 5.0,
                    "vol": 1000000,
                    "amount": 10500000.0,
                }
            ]
        )
        n = upsert_trade_date(self.cursor, df)
        self.assertEqual(n, 1)
        self.cursor.executemany.assert_called_once()

    def test_sql_contains_insert_with_duplicate_key(self):
        """SQL 包含 INSERT ... ON DUPLICATE KEY UPDATE"""
        import pandas as pd

        from stock_analyzer.daily_history_by_date import upsert_trade_date

        df = pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "2025-06-01",
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.5,
                    "close": 10.5,
                    "pre_close": 10.0,
                    "change": 0.5,
                    "pct_chg": 5.0,
                    "vol": 1000000,
                    "amount": 10500000.0,
                }
            ]
        )
        upsert_trade_date(self.cursor, df)
        sql = self.cursor.executemany.call_args[0][0]
        self.assertIn("INSERT INTO stock_daily_history", sql)
        self.assertIn("ON DUPLICATE KEY UPDATE", sql)

    def test_na_values_replaced(self):
        """NaN/None 被替换为 None，不崩溃"""
        import numpy as np
        import pandas as pd

        from stock_analyzer.daily_history_by_date import upsert_trade_date

        df = pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "2025-06-01",
                    "open": None,
                    "high": float("nan"),
                    "low": None,
                    "close": 10.5,
                    "pre_close": None,
                    "change": None,
                    "pct_chg": None,
                    "vol": None,
                    "amount": None,
                }
            ]
        )
        n = upsert_trade_date(self.cursor, df)
        self.assertEqual(n, 1)


class TestMain(unittest.TestCase):
    """main() 主流程"""

    def setUp(self):
        # 清理模块级导入缓存，使每次测试重新导入时能拿到新的 mock
        if "stock_analyzer.daily_history_by_date" in sys.modules:
            del sys.modules["stock_analyzer.daily_history_by_date"]

    @patch("stock_analyzer.daily_history_by_date.fetch_open_trade_dates")
    @patch("stock_analyzer.daily_history_by_date.resolve_date_window")
    @patch("stock_analyzer.daily_history_by_date.DatabaseUtils")
    def test_no_trade_dates_early_return(self, mock_db, mock_resolve, mock_fetch):
        """无交易日 → 提前返回"""
        mock_db.init_tushare_api.return_value = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.connect_to_mysql.return_value = (mock_conn, mock_cursor)
        mock_resolve.return_value = ("2025-06-01", "2025-06-10", False)
        mock_fetch.return_value = []

        from stock_analyzer.daily_history_by_date import main

        main()

        # 没有调用 pro.daily()
        pro = mock_db.init_tushare_api.return_value
        pro.daily.assert_not_called()
        mock_conn.commit.assert_not_called()
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch("stock_analyzer.daily_history_by_date.upsert_trade_date")
    @patch("stock_analyzer.daily_history_by_date.fetch_open_trade_dates")
    @patch("stock_analyzer.daily_history_by_date.resolve_date_window")
    @patch("stock_analyzer.daily_history_by_date.DatabaseUtils")
    def test_normal_flow(self, mock_db, mock_resolve, mock_fetch, mock_upsert):
        """正常流程：拉取数据 → upsert → commit"""
        mock_pro = MagicMock()
        mock_db.init_tushare_api.return_value = mock_pro
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.connect_to_mysql.return_value = (mock_conn, mock_cursor)

        mock_resolve.return_value = ("2025-06-01", "2025-06-10", False)
        mock_fetch.return_value = ["2025-06-01", "2025-06-02"]
        mock_upsert.return_value = 3

        import pandas as pd

        df = pd.DataFrame([{"ts_code": "000001.SZ", "trade_date": "2025-06-01"}])
        mock_pro.daily.return_value = df

        from stock_analyzer.daily_history_by_date import main

        main()

        # 每个交易日都调用 pro.daily()
        self.assertEqual(mock_pro.daily.call_count, 2)
        mock_pro.daily.assert_any_call(trade_date="2025-06-01")
        mock_pro.daily.assert_any_call(trade_date="2025-06-02")
        # upsert 被调用了两次
        self.assertEqual(mock_upsert.call_count, 2)
        # commit 每次 upsert 后都调用
        self.assertEqual(mock_conn.commit.call_count, 2)
        # 清理
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch("stock_analyzer.daily_history_by_date.delete_trade_date_range")
    @patch("stock_analyzer.daily_history_by_date.upsert_trade_date")
    @patch("stock_analyzer.daily_history_by_date.fetch_open_trade_dates")
    @patch("stock_analyzer.daily_history_by_date.resolve_date_window")
    @patch("stock_analyzer.daily_history_by_date.DatabaseUtils")
    def test_full_refresh_deletes_first(
        self, mock_db, mock_resolve, mock_fetch, mock_upsert, mock_delete
    ):
        """full_refresh=True → 先删除再拉取"""
        mock_pro = MagicMock()
        mock_db.init_tushare_api.return_value = mock_pro
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.connect_to_mysql.return_value = (mock_conn, mock_cursor)

        mock_resolve.return_value = ("2025-06-01", "2025-06-10", True)  # full_refresh=True
        mock_fetch.return_value = ["2025-06-01"]
        mock_upsert.return_value = 5

        import pandas as pd

        mock_pro.daily.return_value = pd.DataFrame([{"ts_code": "000001.SZ"}])

        from stock_analyzer.daily_history_by_date import main

        main()

        # 先调用 delete_trade_date_range 删除
        mock_delete.assert_called_once_with(
            mock_cursor, "stock_daily_history", "2025-06-01", "2025-06-01"
        )
        # 然后 commit
        mock_conn.commit.assert_called()  # commit after delete + commit after upsert
        # 再拉数据
        mock_pro.daily.assert_called_once_with(trade_date="2025-06-01")


if __name__ == "__main__":
    unittest.main()
