"""数据管理服务层 — DB 统计 / 缓存 / 导入导出 / 数据源健康

职责:
    - SQLite 数据库统计与维护（异步，使用 aiosqlite）
    - TTL 缓存清除
    - VACUUM 空间回收
    - 数据源健康检查
    - 数据导入/导出
"""

import json as _json
import logging
import os
import time
from typing import Any

from backend.common import _get_db_path, async_safe_table_count

logger = logging.getLogger(__name__)


async def get_data_stats() -> dict[str, Any]:
    """数据库统计 — 大小、表行数、更新时间"""
    db_path = _get_db_path()
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"数据库不存在: {db_path}")

    from backend.db import get_connection

    db_size = os.path.getsize(db_path) / (1024 * 1024)

    async with get_connection() as conn:
        tables = {
            "kline_store": 0,
            "fund_store": 0,
            "nt_store": 0,
            "sector_store": 0,
            "cache": 0,
            "daily_scores": 0,
        }
        for table in tables:
            try:
                tables[table] = await async_safe_table_count(conn, table)
            except Exception:
                pass

        last_update = "未知"
        try:
            cursor = await conn.execute("SELECT MAX(updated_at) FROM kline_store")
            row = await cursor.fetchone()
            if row and row[0]:
                last_update = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(row[0]))
        except Exception:
            pass

        score_dates = 0
        try:
            cursor = await conn.execute("SELECT COUNT(DISTINCT date) FROM daily_scores")
            row = await cursor.fetchone()
            score_dates = int(row[0]) if row else 0
        except Exception:
            pass

        total_stocks = tables["kline_store"]

    return {
        "db_size_mb": round(db_size, 1),
        "kline_count": tables["kline_store"],
        "fundamental_count": tables["fund_store"],
        "national_team_count": tables["nt_store"],
        "sector_count": tables["sector_store"],
        "ttl_entries": tables["cache"],
        "score_dates": score_dates,
        "last_kline_update": last_update,
        "total_stocks": total_stocks,
    }


async def clear_cache() -> dict[str, Any]:
    """清除 TTL 缓存"""
    db_path = _get_db_path()
    if not os.path.exists(db_path):
        raise FileNotFoundError("数据库不存在")

    from backend.db import get_connection

    async with get_connection() as conn:
        await conn.execute("DELETE FROM cache")
        await conn.commit()
        cursor = await conn.execute("SELECT COUNT(*) FROM cache")
        row = await cursor.fetchone()
        remaining = int(row[0]) if row else 0

    return {"message": "TTL 缓存已清除", "remaining_entries": remaining}


async def vacuum_db() -> dict[str, Any]:
    """回收数据库空间"""
    db_path = _get_db_path()
    size_before = os.path.getsize(db_path) / (1024 * 1024)

    from backend.db import get_connection

    async with get_connection() as conn:
        await conn.execute("VACUUM")

    size_after = os.path.getsize(db_path) / (1024 * 1024)
    saved = round(size_before - size_after, 1)

    return {
        "size_before_mb": round(size_before, 1),
        "size_after_mb": round(size_after, 1),
        "saved_mb": saved,
    }


def get_source_status() -> dict[str, Any]:
    """数据源健康检查（同步，无 DB 调用）"""
    from stock_analyzer.network_health import check_all

    health = check_all()

    sources = []
    kline_sources = [
        ("sina_kline", "新浪财经-K线"),
        ("tencent_kline", "腾讯证券-K线"),
        ("baostock_kline", "Baostock-K线"),
        ("eastmoney_kline", "东方财富-K线"),
    ]
    for key, name in kline_sources:
        status = health.get(key, {})
        sources.append(
            {
                "name": name,
                "type": "kline",
                "status": "ok" if status.get("available") else "slow",
                "latency_ms": round(status.get("latency", 0) * 1000, 1),
                "message": status.get("error", ""),
            }
        )

    sources.append(
        {
            "name": "新浪财经-实时行情",
            "type": "realtime",
            "status": "ok" if health.get("sina_realtime", {}).get("available") else "slow",
            "latency_ms": round(health.get("sina_realtime", {}).get("latency", 0) * 1000, 1),
            "message": "",
        }
    )
    sources.append(
        {
            "name": "akshare-数据聚合",
            "type": "api",
            "status": "ok" if health.get("akshare", {}).get("available") else "disabled",
            "latency_ms": round(health.get("akshare", {}).get("latency", 0) * 1000, 1),
            "message": "",
        }
    )

    return {"sources": sources, "mode": health.get("mode", "normal")}


async def import_data(file: bytes, data_type: str, filename: str) -> dict[str, Any]:
    """导入数据 — 支持 CSV/JSON K 线数据或持仓 JSON"""
    import pandas as pd

    content = file

    if data_type == "kline":
        try:
            df = pd.read_csv(pd.io.common.BytesIO(content))
        except Exception:
            data = _json.loads(content.decode("utf-8"))
            df = pd.DataFrame(data)

        required_cols = ["日期", "开盘", "最高", "最低", "收盘", "成交量"]
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"缺少必要列: {col}")

        from backend.db import get_connection

        code = filename.rsplit(".", 1)[0].split("_", maxsplit=1)[0]
        df_json = df.to_json(orient="records", force_ascii=False)
        blob = df_json.encode("utf-8")

        async with get_connection() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO kline_store (code, data, updated_at) VALUES (?, ?, ?)",
                (code, blob, time.time()),
            )
            await conn.commit()

        return {"imported": code, "rows": len(df)}

    elif data_type == "portfolio":
        data = _json.loads(content.decode("utf-8"))
        name = data.get("name", filename.rsplit(".", 1)[0])

        from backend.common import PROJECT_ROOT

        fpath = os.path.join(PROJECT_ROOT, "portfolios", f"{name}.json")
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        with open(fpath, "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False, indent=2)
        return {"imported": name, "type": "portfolio"}

    else:
        raise ValueError(f"不支持的导入类型: {data_type}")


def export_data(code: str, fmt: str = "json") -> dict[str, Any]:
    """导出个股数据（同步，无 DB 调用 — 通过 stock_analyzer.cache 获取数据）"""
    from stock_analyzer.cache import cached_fundamentals, cached_kline

    kline = cached_kline(code)
    funds = cached_fundamentals(code)

    export = {
        "code": code,
        "export_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "fundamentals": funds if isinstance(funds, dict) else {},
    }

    if kline is not None and not kline.empty:
        if fmt == "csv":
            csv_str = kline.tail(60).to_csv(index=False)
            return {"data": csv_str}
        else:
            records = []
            for _, row in kline.tail(60).iterrows():
                records.append(
                    {
                        "date": str(row.get("日期", ""))[:10],
                        "open": float(row.get("开盘", 0)),
                        "high": float(row.get("最高", 0)),
                        "low": float(row.get("最低", 0)),
                        "close": float(row.get("收盘", 0)),
                        "volume": int(row.get("成交量", 0)),
                    }
                )
            export["kline"] = records

    return export
