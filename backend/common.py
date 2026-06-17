"""StockInsight Backend — 公共工具模块

集中管理：
  - 统一响应格式 (_ok / _err)
  - 安全辅助函数
"""

import logging
import os
import re

logger = logging.getLogger(__name__)


# ── 统一 API 响应 ──────────────────────────────────


def _ok(data, freshness="fresh", timing=0):
    return {
        "success": True,
        "data": data,
        "error": None,
        "freshness": freshness,
        "timing_ms": round(timing, 1),
    }


def _err(msg):
    return {"success": False, "data": None, "error": str(msg), "freshness": "stale", "timing_ms": 0}


# ── 安全校验 ──────────────────────────────────────

_PORTFOLIO_NAME_RE = re.compile(r"^[\w\-]+$")


def validate_portfolio_name(name: str) -> str:
    """验证组合名称只含合法字符，防止路径穿越"""
    if not _PORTFOLIO_NAME_RE.match(name):
        raise ValueError(f"非法的组合名称: {name!r}，仅允许字母、数字、下划线和连字符")
    return name


# 项目根目录
PROJECT_ROOT: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_db_path() -> str:
    """获取 SQLite 数据库路径（兼容 stock_analyzer/ 子目录路径）"""
    db_path = os.path.join(PROJECT_ROOT, "stock_cache.db")
    if not os.path.exists(db_path):
        db_path = os.path.join(PROJECT_ROOT, "stock_analyzer", "stock_cache.db")
    return db_path


# SQLite 白名单表名
_ALLOWED_TABLES: frozenset[str] = frozenset(
    {
        "kline_store",
        "fund_store",
        "nt_store",
        "sector_store",
        "cache",
        "daily_scores",
    }
)


def safe_table_count(cur, table: str) -> int:
    """带白名单校验的 COUNT 查询（同步版），防止 SQL 注入"""
    if table not in _ALLOWED_TABLES:
        logger.warning("attempted COUNT on forbidden table: %s", table)
        return 0
    cur.execute(f"SELECT COUNT(*) FROM {table}")  # nosec — table 已通过白名单校验
    return int(cur.fetchone()[0])


async def async_safe_table_count(cur, table: str) -> int:
    """带白名单校验的 COUNT 查询（异步版，适用于 aiosqlite cursor）"""
    if table not in _ALLOWED_TABLES:
        logger.warning("attempted COUNT on forbidden table: %s", table)
        return 0
    await cur.execute(f"SELECT COUNT(*) FROM {table}")  # nosec — table 已通过白名单校验
    row = await cur.fetchone()
    return int(row[0]) if row else 0
