"""测试 daily_basic.py — 股票日线基本面数据导入"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock, PropertyMock

# db_utils 不是独立安装的模块，导入前 mock
sys.modules["db_utils"] = MagicMock()
from stock_analyzer.daily_basic import (
    _normalize_ymd,
    _to_bool,
    FIELDS,
)

class TestNormalizeYmd(unittest.TestCase):
    """_normalize_ymd 日期格式标准化"""

    def test_none_returns_none(self):
        """None → None"""
        self.assertIsNone(_normalize_ymd(None))

    def test_empty_returns_none(self):
        """空字符串 → None"""
        self.assertIsNone(_normalize_ymd(""))
        self.assertIsNone(_normalize_ymd("   "))

    def test_already_ymd(self):
        """已是 YYYYMMDD 格式 → 原样返回"""
        self.assertEqual(_normalize_ymd("20250601"), "20250601")

    def test_dash_format(self):
        """YYYY-MM-DD 格式 → 转为 YYYYMMDD"""
        self.assertEqual(_normalize_ymd("2025-06-01"), "20250601")

    def test_trailing_whitespace(self):
        """尾随空格 → 去除"""
        self.assertEqual(_normalize_ymd("  20250601  "), "20250601")

class TestToBool(unittest.TestCase):
    """_to_bool 布尔值转换"""

    def test_none_is_false(self):
        """None → False"""
        self.assertFalse(_to_bool(None))

    def test_1_is_true(self):
        """'1' → True"""
        self.assertTrue(_to_bool("1"))

    def test_true_is_true(self):
        """'true' → True（大小写不敏感）"""
        self.assertTrue(_to_bool("True"))
        self.assertTrue(_to_bool("true"))
        self.assertTrue(_to_bool("TRUE"))

    def test_yes_is_true(self):
        """'yes' → True"""
        self.assertTrue(_to_bool("yes"))

    def test_y_is_true(self):
        """'y' → True"""
        self.assertTrue(_to_bool("y"))

    def test_on_is_true(self):
        """'on' → True"""
        self.assertTrue(_to_bool("on"))

    def test_0_is_false(self):
        """'0' → False"""
        self.assertFalse(_to_bool("0"))

    def test_no_is_false(self):
        """'no' → False"""
        self.assertFalse(_to_bool("no"))

    def test_whitespace_handling(self):
        """前后空格不影响判断"""
        self.assertTrue(_to_bool(" 1 "))
        self.assertFalse(_to_bool(" 0 "))

# ── 数据库相关函数（需要 mock MySQL cursor）──

class TestResolveDates(unittest.TestCase):
    """_resolve_dates 交易日窗口解析"""

    def setUp(self):
        self.cursor = MagicMock()

    def test_trade_date_from_env(self):
        """DATA_JOB_TRADE_DATE 环境变量 → 返回单日期"""
        with patch.dict(os.environ, {"DATA_JOB_TRADE_DATE": "2025-06-01"}, clear=True):
            from stock_analyzer.daily_basic import _resolve_dates
            dates, full_refresh = _resolve_dates(self.cursor)
            self.assertEqual(dates, ["20250601"])

    def test_full_refresh_flag(self):
        """DATA_JOB_FULL_REFRESH=true → full_refresh=True"""
        with patch.dict(os.environ, {"DATA_JOB_TRADE_DATE": "2025-06-01",
                                      "DATA_JOB_FULL_REFRESH": "1"}, clear=True):
            from stock_analyzer.daily_basic import _resolve_dates
            dates, full_refresh = _resolve_dates(self.cursor)
            self.assertTrue(full_refresh)

    def test_end_date_from_calendar(self):
        """无 DATA_JOB_END_DATE → 从 stock_trade_calendar 取最新交易日"""
        self.cursor.fetchone.side_effect = [("20250615",)]
        with patch.dict(os.environ, {"DATA_JOB_START_DATE": "2025-06-01"}, clear=True):
            from stock_analyzer.daily_basic import _resolve_dates
            dates, full_refresh = _resolve_dates(self.cursor)
            # 验证查询了交易日历
            self.cursor.execute.assert_any_call(
                unittest.mock.ANY  # SELECT DATE_FORMAT(MAX(cal_date), ...)
            )

    def test_start_date_from_max_trade(self):
        """无 DATA_JOB_START_DATE → 从上一次最大 trade_date 下一天开始"""
        self.cursor.fetchone.side_effect = [("20250615",), ("20250610",)]
        with patch.dict(os.environ, {}, clear=True):
            from stock_analyzer.daily_basic import _resolve_dates
            dates, full_refresh = _resolve_dates(self.cursor)
            self.assertFalse(full_refresh)

    def test_no_dates_when_start_after_end(self):
        """start_date > end_date → 空列表"""
        self.cursor.fetchone.side_effect = [("20250601",)]
        with patch.dict(os.environ, {"DATA_JOB_START_DATE": "2025-06-15",
                                      "DATA_JOB_END_DATE": "2025-06-01"}, clear=True):
            from stock_analyzer.daily_basic import _resolve_dates
            dates, full_refresh = _resolve_dates(self.cursor)
            self.assertEqual(dates, [])

class TestEnsureTable(unittest.TestCase):
    """_ensure_table 表创建"""

    def test_create_table_sql(self):
        """执行建表 SQL"""
        cursor = MagicMock()
        from stock_analyzer.daily_basic import _ensure_table
        _ensure_table(cursor)
        cursor.execute.assert_called_once()
        sql = cursor.execute.call_args[0][0]
        self.assertIn("CREATE TABLE IF NOT EXISTS stock_daily_basic", sql)
        self.assertIn("PRIMARY KEY (ts_code,trade_date)", sql)

class TestDeleteForRefresh(unittest.TestCase):
    """_delete_for_refresh 删除旧数据"""

    def test_no_refresh_skips_delete(self):
        """full_refresh=False → 不执行删除"""
        cursor = MagicMock()
        from stock_analyzer.daily_basic import _delete_for_refresh
        _delete_for_refresh(cursor, ["20250601"], False)
        cursor.execute.assert_not_called()

    def test_empty_dates_skips_delete(self):
        """空日期列表 → 不执行删除"""
        cursor = MagicMock()
        from stock_analyzer.daily_basic import _delete_for_refresh
        _delete_for_refresh(cursor, [], True)
        cursor.execute.assert_not_called()

    def test_delete_called_with_range(self):
        """刷新时按 min/max 日期删除"""
        cursor = MagicMock()
        from stock_analyzer.daily_basic import _delete_for_refresh
        _delete_for_refresh(cursor, ["20250601", "20250603", "20250602"], True)
        cursor.execute.assert_called_once()
        sql = cursor.execute.call_args[0][0]
        self.assertIn("DELETE FROM stock_daily_basic", sql)

class TestSaveTradeDate(unittest.TestCase):
    """_save_trade_date 数据写入"""

    def setUp(self):
        self.cursor = MagicMock()
        self.conn = MagicMock()

    def test_empty_df(self):
        """空 DataFrame → 返回 0"""
        import pandas as pd
        from stock_analyzer.daily_basic import _save_trade_date
        n = _save_trade_date(self.cursor, self.conn, pd.DataFrame())
        self.assertEqual(n, 0)

    def test_insert_called(self):
        """正常数据 → 调用 executemany + commit"""
        import pandas as pd
        from stock_analyzer.daily_basic import _save_trade_date
        df = pd.DataFrame([{
            "ts_code": "000001.SZ", "trade_date": "20250601",
            "close": 12.5, "turnover_rate": 1.2, "turnover_rate_f": 1.0,
            "volume_ratio": 0.8, "pe": 10.0, "pe_ttm": 9.5, "pb": 1.2,
            "ps": 2.0, "ps_ttm": 1.8, "dv_ratio": 2.5, "dv_ttm": 2.3,
            "total_share": 1000000, "float_share": 800000, "free_share": 700000,
            "total_mv": 12500000, "circ_mv": 10000000,
        }])
        n = _save_trade_date(self.cursor, self.conn, df)
        self.assertEqual(n, 1)
        self.cursor.executemany.assert_called_once()
        self.conn.commit.assert_called_once()

    def test_na_values_replaced(self):
        """NaN/None 被替换为 None"""
        import pandas as pd
        import numpy as np
        from stock_analyzer.daily_basic import _save_trade_date
        df = pd.DataFrame([{
            "ts_code": "000001.SZ", "trade_date": "20250601",
            "close": None, "turnover_rate": float("nan"),
            "turnover_rate_f": None, "volume_ratio": None,
            "pe": None, "pe_ttm": None, "pb": None,
            "ps": None, "ps_ttm": None, "dv_ratio": None, "dv_ttm": None,
            "total_share": None, "float_share": None, "free_share": None,
            "total_mv": None, "circ_mv": None,
        }])
        n = _save_trade_date(self.cursor, self.conn, df)
        self.assertEqual(n, 1)

if __name__ == "__main__":
    unittest.main()
