"""板块归属查询 — 行业板块 + 概念板块"""

import os
import sqlite3
from typing import Any

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stock_cache.db"
)
_CACHE: dict[str, tuple | None] = {}


def _query(code: str) -> tuple[Any, ...] | None:
    if code in _CACHE:
        return _CACHE[code]
    try:
        conn = sqlite3.connect(_DB_PATH)
        cur = conn.execute(
            "SELECT sector, sub_sector FROM stock_sector_v2 WHERE code=? AND type='industry'",
            (code,),
        )
        row = cur.fetchone()
        conn.close()
        if row:
            _CACHE[code] = (row[0], row[1])
            return _CACHE[code]
    except Exception:
        pass
    _CACHE[code] = None
    return None


def get_stock_sector_full(code: str) -> str:
    """行业板块完整: '制造业 > 半导体'"""
    r = _query(code)
    return f"{r[0]} > {r[1]}" if r else "未知"


def get_stock_concepts(code: str) -> list:
    """概念板块列表 (需先运行 build_concept_db.build())"""
    try:
        conn = sqlite3.connect(_DB_PATH)
        cur = conn.execute("SELECT concept FROM stock_concept WHERE code=?", (code,))
        concepts = [r[0] for r in cur.fetchall()]
        conn.close()
        return concepts
    except Exception:
        return []


def get_stock_all_sectors(code: str) -> dict:
    """行业 + 概念，完整板块信息"""
    industry = get_stock_sector_full(code)
    concepts = get_stock_concepts(code)
    return {"industry": industry, "concepts": concepts}
