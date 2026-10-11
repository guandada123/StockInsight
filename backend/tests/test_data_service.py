"""测试 backend/services/data_service.py — DB 统计 / 缓存 / VACUUM / 数据源健康 / 导入导出

隔离要点：
    - 数据库路径来自 backend.common._get_db_path（默认指向仓库 stock_cache.db）。
      所有用例通过 monkeypatch 把它指向 tmp_path，避免触碰真实库。注意 data_service
      是 `from backend.common import _get_db_path`，因此 patch 目标是 data_service 自身的名字。
    - 连接通过 `from backend.db import get_connection` 在函数内导入，patch 目标为
      backend.db.get_connection。替身实现 async 上下文管理器协议（__aenter__/__aexit__），
      这是最容易踩坑的地方 —— 直接给 MagicMock 会在 `async with` 处炸。
    - 导出/数据源健康依赖 stock_analyzer 的外部调用，统一 patch 到模块属性。
"""

import json
from unittest.mock import patch

import pandas as pd
import pytest

from backend.services import data_service as dsvc

# ════════════════════════════════════════════════════
# 连接替身（支持 async with / await execute / await commit）
# ════════════════════════════════════════════════════


class _FakeCursor:
    def __init__(self, rows):
        self._rows = list(rows)

    async def fetchone(self):
        return self._rows.pop(0) if self._rows else None


class _FakeConn:
    """最小 aiosqlite 连接替身，按 SQL 内容返回构造好的行。

    注意 aiosqlite 的 Connection 同时支持 `await cursor.fetchone()` 与
    直接 `await conn.fetchone()` 两种写法 —— common.async_safe_table_count
    用的就是后者（把 conn 当 cursor 用），因此替身两者都要提供。
    """

    def __init__(self, *, counts=None, last_update=None, score_dates=0, fail_tables=()):
        self._counts = counts or {}
        self._last_update = last_update
        self._score_dates = score_dates
        self._fail_tables = set(fail_tables)
        self._pending = []
        self.executed = []

    def _row_for(self, sql: str):
        if "COUNT(*)" in sql and "FROM" in sql:
            table = sql.split("FROM", 1)[1].strip().split()[0]
            return (self._counts.get(table, 0),)
        if "MAX(updated_at)" in sql:
            return (self._last_update,)
        if "COUNT(DISTINCT date)" in sql:
            return (self._score_dates,)
        return (0,)

    async def execute(self, sql, params=()):
        self.executed.append(sql)
        table = sql.split("FROM", 1)[1].strip().split()[0] if "FROM" in sql else ""
        if table in self._fail_tables:
            raise RuntimeError(f"simulated failure on {table}")
        row = self._row_for(sql)
        self._pending = [row]
        return _FakeCursor([row])

    async def fetchone(self):
        """兼容 `await conn.fetchone()` 写法（conn 被当 cursor 使用）"""
        return self._pending.pop(0) if self._pending else None

    async def commit(self):
        return None


class _FakeConnCM:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


def _install_connection(monkeypatch, conn):
    monkeypatch.setattr("backend.db.get_connection", lambda: _FakeConnCM(conn))


# ════════════════════════════════════════════════════
# 夹具
# ════════════════════════════════════════════════════


@pytest.fixture
def db_file(tmp_path, monkeypatch):
    """真实存在的空 db 文件，并让 data_service 指向它"""
    p = tmp_path / "stock_cache.db"
    p.write_bytes(b"")
    monkeypatch.setattr(dsvc, "_get_db_path", lambda: str(p))
    return p


@pytest.fixture
def missing_db(tmp_path, monkeypatch):
    """指向一个不存在的路径"""
    monkeypatch.setattr(dsvc, "_get_db_path", lambda: str(tmp_path / "nope.db"))


# ════════════════════════════════════════════════════
# get_data_stats
# ════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestGetDataStats:
    async def test_missing_db_raises_file_not_found(self, missing_db):
        with pytest.raises(FileNotFoundError):
            await dsvc.get_data_stats()

    async def test_returns_counts_for_all_tables(self, db_file, monkeypatch):
        conn = _FakeConn(
            counts={
                "kline_store": 11,
                "fund_store": 22,
                "nt_store": 33,
                "sector_store": 44,
                "cache": 55,
                "daily_scores": 66,
            }
        )
        _install_connection(monkeypatch, conn)

        result = await dsvc.get_data_stats()

        assert result["kline_count"] == 11
        assert result["fundamental_count"] == 22
        assert result["national_team_count"] == 33
        assert result["sector_count"] == 44
        assert result["ttl_entries"] == 55
        assert result["total_stocks"] == 11

    async def test_last_update_formatted_when_present(self, db_file, monkeypatch):
        conn = _FakeConn(counts={"kline_store": 1}, last_update=1700000000.0)
        _install_connection(monkeypatch, conn)

        result = await dsvc.get_data_stats()

        assert result["last_kline_update"] != "未知"
        assert len(result["last_kline_update"]) == 19  # YYYY-MM-DD HH:MM:SS

    async def test_last_update_unknown_when_null(self, db_file, monkeypatch):
        conn = _FakeConn(counts={"kline_store": 1}, last_update=None)
        _install_connection(monkeypatch, conn)

        result = await dsvc.get_data_stats()

        assert result["last_kline_update"] == "未知"

    async def test_score_dates_counted(self, db_file, monkeypatch):
        conn = _FakeConn(counts={"kline_store": 1}, score_dates=7)
        _install_connection(monkeypatch, conn)

        result = await dsvc.get_data_stats()

        assert result["score_dates"] == 7

    async def test_single_table_failure_does_not_abort(self, db_file, monkeypatch):
        """单表统计失败应被吞掉并记 warning，整体仍返回"""
        conn = _FakeConn(counts={"kline_store": 5}, fail_tables={"fund_store"})
        _install_connection(monkeypatch, conn)

        result = await dsvc.get_data_stats()

        assert result["kline_count"] == 5
        assert result["fundamental_count"] == 0  # 失败表回落到默认 0

    async def test_db_size_reported_in_mb(self, db_file, monkeypatch):
        _install_connection(monkeypatch, _FakeConn(counts={}))

        result = await dsvc.get_data_stats()

        assert result["db_size_mb"] >= 0


# ════════════════════════════════════════════════════
# clear_cache
# ════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestClearCache:
    async def test_missing_db_raises(self, missing_db):
        with pytest.raises(FileNotFoundError):
            await dsvc.clear_cache()

    async def test_returns_remaining_entries(self, db_file, monkeypatch):
        conn = _FakeConn(counts={"cache": 0})
        _install_connection(monkeypatch, conn)

        result = await dsvc.clear_cache()

        assert result["message"] == "TTL 缓存已清除"
        assert result["remaining_entries"] == 0
        assert any("DELETE FROM cache" in sql for sql in conn.executed)


# ════════════════════════════════════════════════════
# vacuum_db
# ════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestVacuumDb:
    async def test_reports_sizes(self, db_file, monkeypatch):
        _install_connection(monkeypatch, _FakeConn())

        result = await dsvc.vacuum_db()

        assert "size_before_mb" in result
        assert "size_after_mb" in result
        assert "saved_mb" in result
        assert result["saved_mb"] == round(result["size_before_mb"] - result["size_after_mb"], 1)


# ════════════════════════════════════════════════════
# get_source_status
# ════════════════════════════════════════════════════


class TestGetSourceStatus:
    def _health(self, **overrides):
        base = {
            "sina_kline": {"available": True, "latency": 0.1},
            "tencent_kline": {"available": False, "latency": 0.5, "error": "timeout"},
            "baostock_kline": {"available": True, "latency": 0.2},
            "eastmoney_kline": {"available": False, "latency": 0.3},
            "sina_realtime": {"available": True, "latency": 0.05},
            "akshare": {"available": False, "latency": 0.4},
            "mode": "normal",
        }
        base.update(overrides)
        return base

    def test_returns_all_sources(self):
        with patch("stock_analyzer.network_health.check_all", return_value=self._health()):
            result = dsvc.get_source_status()

        # 4 个 K 线源 + 1 实时 + 1 聚合 = 6
        assert len(result["sources"]) == 6
        assert result["mode"] == "normal"

    def test_status_mapping(self):
        with patch("stock_analyzer.network_health.check_all", return_value=self._health()):
            result = dsvc.get_source_status()

        by_name = {s["name"]: s for s in result["sources"]}
        assert by_name["新浪财经-K线"]["status"] == "ok"
        assert by_name["腾讯证券-K线"]["status"] == "slow"
        assert by_name["腾讯证券-K线"]["message"] == "timeout"
        assert by_name["akshare-数据聚合"]["status"] == "disabled"

    def test_latency_converted_to_ms(self):
        with patch("stock_analyzer.network_health.check_all", return_value=self._health()):
            result = dsvc.get_source_status()

        by_name = {s["name"]: s for s in result["sources"]}
        assert by_name["新浪财经-K线"]["latency_ms"] == 100.0
        assert by_name["新浪财经-实时行情"]["latency_ms"] == 50.0

    def test_missing_source_treated_as_slow(self):
        """health 里缺少某源时按不可用处理，不抛异常"""
        with patch("stock_analyzer.network_health.check_all", return_value={"mode": "degraded"}):
            result = dsvc.get_source_status()

        assert all(s["status"] in ("slow", "disabled") for s in result["sources"])
        assert result["mode"] == "degraded"


# ════════════════════════════════════════════════════
# import_data
# ════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestImportData:
    async def test_unsupported_type_raises(self, monkeypatch):
        with pytest.raises(ValueError, match="不支持的导入类型"):
            await dsvc.import_data(b"{}", "unknown", "x.json")

    async def test_kline_csv_missing_column_raises(self, monkeypatch):
        csv_bytes = b"date,open\n2026-01-01,1\n"

        with pytest.raises(ValueError, match="缺少必要列"):
            await dsvc.import_data(csv_bytes, "kline", "600519_2026.csv")

    async def test_kline_csv_import_success(self, monkeypatch):
        csv_bytes = "日期,开盘,最高,最低,收盘,成交量\n2026-01-01,1,2,0.5,1.5,100\n".encode()
        conn = _FakeConn()
        _install_connection(monkeypatch, conn)

        result = await dsvc.import_data(csv_bytes, "kline", "600519_2026.csv")

        assert result["imported"] == "600519"
        assert result["rows"] == 1
        assert any("INSERT OR REPLACE INTO kline_store" in sql for sql in conn.executed)

    async def test_kline_json_fallback_when_not_csv(self, monkeypatch):
        """CSV 解析抛异常时回退到 JSON 解析

        注意：pandas.read_csv 对 `[{...}]` 这类内容并不会抛异常（会解析成
        单列），所以必须显式让 read_csv 失败，才能真正走到 JSON 分支。
        """
        payload = json.dumps(
            [
                {
                    "日期": "2026-01-01",
                    "开盘": 1,
                    "最高": 2,
                    "最低": 0.5,
                    "收盘": 1.5,
                    "成交量": 100,
                }
            ]
        ).encode()
        conn = _FakeConn()
        _install_connection(monkeypatch, conn)

        with patch("pandas.read_csv", side_effect=Exception("not a csv")):
            result = await dsvc.import_data(payload, "kline", "000001_hist.json")

        assert result["imported"] == "000001"
        assert result["rows"] == 1

    async def test_kline_code_extracted_from_filename(self, monkeypatch):
        csv_bytes = "日期,开盘,最高,最低,收盘,成交量\n2026-01-01,1,2,0.5,1.5,100\n".encode()
        _install_connection(monkeypatch, _FakeConn())

        result = await dsvc.import_data(csv_bytes, "kline", "600036_2026_Q1.csv")

        assert result["imported"] == "600036"

    async def test_portfolio_import_writes_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("backend.common.PROJECT_ROOT", str(tmp_path))
        payload = json.dumps({"name": "我的组合", "holdings": {"600519": {}}}).encode()

        result = await dsvc.import_data(payload, "portfolio", "fallback.json")

        assert result == {"imported": "我的组合", "type": "portfolio"}
        saved = tmp_path / "portfolios" / "我的组合.json"
        assert saved.exists()
        assert json.loads(saved.read_text(encoding="utf-8"))["name"] == "我的组合"

    async def test_portfolio_import_uses_filename_when_name_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("backend.common.PROJECT_ROOT", str(tmp_path))
        payload = json.dumps({"holdings": {}}).encode()

        result = await dsvc.import_data(payload, "portfolio", "myfile.json")

        assert result["imported"] == "myfile"

    # ── 路径穿越防护（2026-10-11 审计修复） ──────────────

    @pytest.mark.parametrize(
        "evil_name",
        [
            "../../evil",
            "../outside",
            "a/b",
            "a\\b",
            "..",
            ".",
            " ",
            "x" * 65,  # 超长（>64）
            "组合/../x",
        ],
    )
    async def test_portfolio_import_rejects_traversal_names(self, tmp_path, monkeypatch, evil_name):
        """恶意/非法 name 必须被拒绝，且不得产生任何越目录写入。"""
        monkeypatch.setattr("backend.common.PROJECT_ROOT", str(tmp_path))
        payload = json.dumps({"name": evil_name, "holdings": {}}).encode()

        with pytest.raises(ValueError):
            await dsvc.import_data(payload, "portfolio", "fallback.json")

        # portfolios 目录之外不得出现任何被写入的文件
        stray = [p for p in tmp_path.rglob("*") if p.is_file()]
        assert stray == [], f"存在越目录写入: {stray}"

    async def test_portfolio_import_empty_name_falls_back_to_filename(self, tmp_path, monkeypatch):
        """空 name 不视为攻击：回退用 filename（filename 仍会过白名单校验）。"""
        monkeypatch.setattr("backend.common.PROJECT_ROOT", str(tmp_path))
        payload = json.dumps({"name": "", "holdings": {}}).encode()

        result = await dsvc.import_data(payload, "portfolio", "fallback.json")

        assert result["imported"] == "fallback"

    async def test_portfolio_import_rejects_traversal_via_filename(self, tmp_path, monkeypatch):
        """name 缺失时回退用 filename，同样必须过滤（原实现的另一条入口）。"""
        monkeypatch.setattr("backend.common.PROJECT_ROOT", str(tmp_path))
        payload = json.dumps({"holdings": {}}).encode()

        with pytest.raises(ValueError):
            await dsvc.import_data(payload, "portfolio", "../../evil.json")

    async def test_portfolio_import_keeps_safe_names_working(self, tmp_path, monkeypatch):
        """回归：合法中文/英文/数字/连字符名称不受影响（不能修出误伤）。"""
        monkeypatch.setattr("backend.common.PROJECT_ROOT", str(tmp_path))
        for good in ("我的组合", "my_pool-2026", "600519"):
            payload = json.dumps({"name": good, "holdings": {}}).encode()
            result = await dsvc.import_data(payload, "portfolio", "f.json")
            assert result["imported"] == good
            assert (tmp_path / "portfolios" / f"{good}.json").exists()


# ════════════════════════════════════════════════════
# export_data
# ════════════════════════════════════════════════════


class TestExportData:
    def _kline_df(self):
        return pd.DataFrame(
            {
                "日期": ["2026-01-01", "2026-01-02"],
                "开盘": [1.0, 2.0],
                "最高": [2.0, 3.0],
                "最低": [0.5, 1.5],
                "收盘": [1.5, 2.5],
                "成交量": [100, 200],
            }
        )

    def test_no_kline_returns_fundamentals_only(self):
        with (
            patch("stock_analyzer.cache.cached_kline", return_value=None),
            patch("stock_analyzer.cache.cached_fundamentals", return_value={"PE_TTM": 12.5}),
        ):
            result = dsvc.export_data("600519")

        assert result["code"] == "600519"
        assert result["fundamentals"] == {"PE_TTM": 12.5}
        assert "kline" not in result

    def test_empty_dataframe_treated_as_no_kline(self):
        with (
            patch("stock_analyzer.cache.cached_kline", return_value=pd.DataFrame()),
            patch("stock_analyzer.cache.cached_fundamentals", return_value={}),
        ):
            result = dsvc.export_data("600519")

        assert "kline" not in result

    def test_non_dict_fundamentals_becomes_empty(self):
        with (
            patch("stock_analyzer.cache.cached_kline", return_value=None),
            patch("stock_analyzer.cache.cached_fundamentals", return_value=None),
        ):
            result = dsvc.export_data("600519")

        assert result["fundamentals"] == {}

    def test_json_format_builds_records(self):
        with (
            patch("stock_analyzer.cache.cached_kline", return_value=self._kline_df()),
            patch("stock_analyzer.cache.cached_fundamentals", return_value={}),
        ):
            result = dsvc.export_data("600519", fmt="json")

        assert len(result["kline"]) == 2
        first = result["kline"][0]
        assert first["open"] == 1.0
        assert first["close"] == 1.5
        assert first["volume"] == 100

    def test_csv_format_returns_data_string(self):
        with (
            patch("stock_analyzer.cache.cached_kline", return_value=self._kline_df()),
            patch("stock_analyzer.cache.cached_fundamentals", return_value={}),
        ):
            result = dsvc.export_data("600519", fmt="csv")

        assert "data" in result
        assert "日期" in result["data"]
        assert "kline" not in result
