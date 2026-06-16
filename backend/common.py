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


# SQLite 白名单表名
_ALLOWED_TABLES: frozenset[str] = frozenset({
    "kline_store",
    "fund_store",
    "nt_store",
    "sector_store",
    "cache",
    "daily_scores",
})


def safe_table_count(cur, table: str) -> int:
    """带白名单校验的 COUNT 查询，防止 SQL 注入"""
    if table not in _ALLOWED_TABLES:
        logger.warning("attempted COUNT on forbidden table: %s", table)
        return 0
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    return cur.fetchone()[0]
