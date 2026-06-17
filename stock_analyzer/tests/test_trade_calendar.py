"""测试 trade_calendar.py — 交易日历 ETL 脚本

注意事项：
- trade_calendar.py 包含模块级代码：初始化 Tushare API、连接 MySQL、建表、插入数据
- 必须在 import 前 mock db_utils（包括 DatabaseUtils.init_tushare_api 和 connect_to_mysql）
- tushare 也需要 mock，因为模块级代码调用 pro.trade_cal()
"""

import sys
import unittest
from unittest.mock import MagicMock, call, patch

# ── 模块级 mock ──────────────────────────────────────────────────────
# db_utils 必须在导入 trade_calendar 前 mock
_mock_db = MagicMock()
_mock_pro = MagicMock()
_mock_conn = MagicMock()
_mock_cursor = MagicMock()

_mock_db.DatabaseUtils.init_tushare_api.return_value = _mock_pro
_mock_db.DatabaseUtils.connect_to_mysql.return_value = (_mock_conn, _mock_cursor)
sys.modules["db_utils"] = _mock_db

# 模拟 tushare 返回值
_trade_cal_data = type(
    "MockDataFrame",
    (),
    {
        "iterrows": lambda self: iter(
            [
                (0, {"exchange": "SSE", "cal_date": "20250101", "is_open": 1, "pretrade_date": ""}),
                (
                    1,
                    {
                        "exchange": "SZSE",
                        "cal_date": "20250102",
                        "is_open": 0,
                        "pretrade_date": "20250101",
                    },
                ),
            ]
        )
    },
)()
_mock_pro.trade_cal.return_value = _trade_cal_data

# 现在导入 trade_calendar（模块级代码会自动执行，使用上方的 mock）
import stock_analyzer.trade_calendar as tc


class TestTradeCalendarETL(unittest.TestCase):
    """验证 trade_calendar.py 模块级 ETL 流程"""

    def test_tushare_api_initialized(self):
        """Tushare API 已通过 db_utils 初始化"""
        _mock_db.DatabaseUtils.init_tushare_api.assert_called_once()

    def test_mysql_connection_established(self):
        """MySQL 连接已建立"""
        _mock_db.DatabaseUtils.connect_to_mysql.assert_called_once()

    def test_trade_cal_api_called(self):
        """trade_cal API 被调用，参数正确"""
        _mock_pro.trade_cal.assert_called_once_with(
            exchange="",
            start_date="20240101",
            end_date="20261231",
            fields="exchange,cal_date,is_open,pretrade_date",
        )

    def test_table_created(self):
        """建表语句已执行"""
        create_call = [
            c for c in _mock_cursor.execute.call_args_list if "CREATE TABLE" in str(c)
        ]
        self.assertGreater(len(create_call), 0)

    def test_data_inserted(self):
        """数据已批量插入"""
        _mock_cursor.executemany.assert_called_once()
        args = _mock_cursor.executemany.call_args
        self.assertIn("REPLACE INTO", str(args))
        self.assertIn("stock_trade_calendar", str(args))

    def test_connection_closed(self):
        """连接已关闭"""
        _mock_cursor.close.assert_called_once()
        _mock_conn.close.assert_called_once()

    def test_truncate_executed(self):
        """先清空再插入"""
        truncate_call = [
            c for c in _mock_cursor.execute.call_args_list if "truncate" in str(c).lower()
        ]
        self.assertGreater(len(truncate_call), 0)


class TestTradeCalendarDataFlow(unittest.TestCase):
    """测试 trade_calendar.py 数据处理逻辑"""

    def setUp(self):
        # 用独立的 mock 重新模拟模块级行为
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()

        self.mock_db = MagicMock()
        self.mock_pro = MagicMock()
        self.mock_db.DatabaseUtils.init_tushare_api.return_value = self.mock_pro
        self.mock_db.DatabaseUtils.connect_to_mysql.return_value = (
            self.mock_conn,
            self.mock_cursor,
        )

    def test_dataframe_converted_to_tuples(self):
        """DataFrame 行正确转换为 tuple"""
        import pandas as pd

        data = pd.DataFrame(
            {
                "exchange": ["SSE", "SZSE"],
                "cal_date": ["20250101", "20250102"],
                "is_open": [1, 0],
                "pretrade_date": ["", "20250101"],
            }
        )

        # 手动模拟模块级的数据处理逻辑
        insert_data = [tuple(row) for index, row in data.iterrows()]
        self.assertEqual(len(insert_data), 2)
        self.assertEqual(insert_data[0], ("SSE", "20250101", 1, ""))
        self.assertEqual(insert_data[1], ("SZSE", "20250102", 0, "20250101"))

    def test_data_with_nan_handled(self):
        """NaN 值在 tuple 转换中不崩溃"""
        import pandas as pd

        data = pd.DataFrame(
            {
                "exchange": ["SSE"],
                "cal_date": ["20250101"],
                "is_open": [1],
                "pretrade_date": [None],  # NaN
            }
        )
        insert_data = [tuple(row) for index, row in data.iterrows()]
        self.assertEqual(len(insert_data), 1)
        # NaN 应被转换为 float('nan') 或 None
        self.assertTrue(pd.isna(insert_data[0][3]) or insert_data[0][3] is None)


if __name__ == "__main__":
    unittest.main()
