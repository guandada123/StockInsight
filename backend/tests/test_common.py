"""测试 backend/common.py — 公共工具函数"""

from unittest import mock

import pytest

from backend import common

# ════════════════════════════════════════════
# 统一响应格式
# ════════════════════════════════════════════


class TestOk:
    """_ok 响应格式"""

    def test_basic_ok(self):
        """基本成功响应"""
        resp = common._ok({"price": 10.5})
        assert resp["success"] is True
        assert resp["data"] == {"price": 10.5}
        assert resp["error"] is None
        assert resp["freshness"] == "fresh"
        assert isinstance(resp["timing_ms"], (int, float))

    def test_ok_with_freshness(self):
        """自定义 freshness"""
        resp = common._ok([1, 2, 3], freshness="cached")
        assert resp["freshness"] == "cached"

    def test_ok_with_timing(self):
        """自定义 timing"""
        resp = common._ok(None, timing=123.456)
        assert resp["timing_ms"] == 123.5

    def test_ok_with_zero_data(self):
        """data 为 0 / False 不应被当作空"""
        resp_zero = common._ok(0)
        assert resp_zero["data"] == 0

        resp_none = common._ok(None)
        assert resp_none["data"] is None


class TestErr:
    """_err 响应格式"""

    def test_basic_err(self):
        """基本错误响应"""
        resp = common._err("出错了")
        assert resp["success"] is False
        assert resp["data"] is None
        assert resp["error"] == "出错了"
        assert resp["freshness"] == "stale"
        assert resp["timing_ms"] == 0

    def test_err_with_exception(self):
        """用 Exception 对象作为错误消息"""
        exc = ValueError("非法参数")
        resp = common._err(exc)
        assert "非法参数" in resp["error"]

    def test_err_with_number(self):
        """数字作为错误消息"""
        resp = common._err(404)
        assert resp["error"] == "404"

    def test_err_empty_string(self):
        """空字符串错误"""
        resp = common._err("")
        assert resp["error"] == ""


# ════════════════════════════════════════════
# 组合名称校验
# ════════════════════════════════════════════


class TestValidatePortfolioName:
    """validate_portfolio_name"""

    def test_valid_names(self):
        """合法名称通过"""
        assert common.validate_portfolio_name("test") == "test"
        assert common.validate_portfolio_name("my_portfolio") == "my_portfolio"
        assert common.validate_portfolio_name("Portfolio-123") == "Portfolio-123"
        assert common.validate_portfolio_name("A") == "A"

    def test_invalid_names_raise(self):
        """非法名称抛出 ValueError"""
        with pytest.raises(ValueError, match="非法的组合名称"):
            common.validate_portfolio_name("../etc/passwd")
        with pytest.raises(ValueError, match="非法的组合名称"):
            common.validate_portfolio_name("my portfolio!@#")
        with pytest.raises(ValueError, match="非法的组合名称"):
            common.validate_portfolio_name("")
        with pytest.raises(ValueError, match="非法的组合名称"):
            common.validate_portfolio_name("a/b")
        with pytest.raises(ValueError, match="非法的组合名称"):
            common.validate_portfolio_name("a.b")

    # 注意：Python 3 的 \w 匹配 Unicode 字符，所以中文名通过校验


# ════════════════════════════════════════════
# 安全 COUNT 查询（同步）
# ════════════════════════════════════════════


class TestSafeTableCount:
    """safe_table_count"""

    def test_allowed_table(self, monkeypatch):
        """白名单表名正常查询"""
        mock_cursor = mock.MagicMock()
        mock_cursor.fetchone.return_value = (42,)
        result = common.safe_table_count(mock_cursor, "kline_store")
        assert result == 42
        mock_cursor.execute.assert_called_once_with("SELECT COUNT(*) FROM kline_store")

    def test_forbidden_table(self, monkeypatch):
        """禁止表名返回 0"""
        mock_cursor = mock.MagicMock()
        result = common.safe_table_count(mock_cursor, "user_secrets")
        assert result == 0
        mock_cursor.execute.assert_not_called()

    def test_sql_injection_attempt(self, monkeypatch):
        """SQL 注入尝试被阻止"""
        mock_cursor = mock.MagicMock()
        result = common.safe_table_count(mock_cursor, "kline_store; DROP TABLE users")
        assert result == 0
        mock_cursor.execute.assert_not_called()

    def test_empty_table_name(self):
        """空表名返回 0"""
        mock_cursor = mock.MagicMock()
        result = common.safe_table_count(mock_cursor, "")
        assert result == 0

    def test_all_allowed_tables(self):
        """所有白名单表名均可正常查询"""
        allowed = ["kline_store", "fund_store", "nt_store", "sector_store", "cache", "daily_scores"]
        for table in allowed:
            mock_cursor = mock.MagicMock()
            mock_cursor.fetchone.return_value = (5,)
            result = common.safe_table_count(mock_cursor, table)
            assert result == 5


# ════════════════════════════════════════════
# 安全 COUNT 查询（异步）
# ════════════════════════════════════════════


@pytest.mark.asyncio
class TestAsyncSafeTableCount:
    """async_safe_table_count"""

    async def test_allowed_table(self):
        """白名单表名正常查询"""
        mock_cursor = mock.AsyncMock()
        mock_cursor.fetchone.return_value = (99,)
        result = await common.async_safe_table_count(mock_cursor, "cache")
        assert result == 99
        mock_cursor.execute.assert_called_once_with("SELECT COUNT(*) FROM cache")

    async def test_forbidden_table(self):
        """禁止表名返回 0"""
        mock_cursor = mock.AsyncMock()
        result = await common.async_safe_table_count(mock_cursor, "hacky_table")
        assert result == 0
        mock_cursor.execute.assert_not_called()

    async def test_sql_injection_attempt(self):
        """SQL 注入尝试"""
        mock_cursor = mock.AsyncMock()
        result = await common.async_safe_table_count(mock_cursor, "cache; DELETE FROM kline_store")
        assert result == 0

    async def test_fetchone_returns_none(self):
        """fetchone 返回 None 时返回 0"""
        mock_cursor = mock.AsyncMock()
        mock_cursor.fetchone.return_value = None
        result = await common.async_safe_table_count(mock_cursor, "fund_store")
        assert result == 0
