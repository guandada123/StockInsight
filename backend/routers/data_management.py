"""数据管理 API 路由 — DB统计/缓存/导入导出/数据源健康"""

import logging
import os
import sqlite3
import time

from fastapi import APIRouter, Body, Query

logger = logging.getLogger(__name__)
_SAFE_ERROR_MSG = "服务暂不可用，请稍后重试"

router = APIRouter(prefix="/api/data", tags=["数据管理"])


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


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _get_db_path():
    """获取 SQLite 数据库路径"""
    db_path = os.path.join(PROJECT_ROOT, "stock_cache.db")
    if not os.path.exists(db_path):
        # 尝试 stock_analyzer 包内
        db_path = os.path.join(PROJECT_ROOT, "stock_analyzer", "stock_cache.db")
    return db_path


@router.get("/stats")
async def data_stats():
    """数据库统计 — 大小、表行数、更新时间"""
    t0 = time.time()
    try:
        db_path = _get_db_path()
        if not os.path.exists(db_path):
            return _err(f"数据库不存在: {db_path}")

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # DB 大小
        db_size = os.path.getsize(db_path) / (1024 * 1024)

        # 各表行数
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
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                tables[table] = cur.fetchone()[0]
            except Exception:
                pass

        # 最近 K 线更新时间
        last_update = "未知"
        try:
            cur.execute("SELECT MAX(updated_at) FROM kline_store")
            ts = cur.fetchone()[0]
            if ts:
                last_update = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
        except Exception:
            pass

        # 评分日期数
        score_dates = 0
        try:
            cur.execute("SELECT COUNT(DISTINCT date) FROM daily_scores")
            score_dates = cur.fetchone()[0]
        except Exception:
            pass

        # 全市场股票数
        total_stocks = tables["kline_store"]

        conn.close()

        return _ok(
            {
                "db_size_mb": round(db_size, 1),
                "db_path": db_path,
                "kline_count": tables["kline_store"],
                "fundamental_count": tables["fund_store"],
                "national_team_count": tables["nt_store"],
                "sector_count": tables["sector_store"],
                "ttl_entries": tables["cache"],
                "score_dates": score_dates,
                "last_kline_update": last_update,
                "total_stocks": total_stocks,
            },
            timing=(time.time() - t0) * 1000,
        )
    except Exception:
        logger.exception("data_error")
        return _err(_SAFE_ERROR_MSG)


@router.post("/clear-cache")
async def clear_cache():
    """清除 TTL 缓存（不删除永久存储的 K线/基本面/国家队数据）"""
    t0 = time.time()
    try:
        db_path = _get_db_path()
        if not os.path.exists(db_path):
            return _err("数据库不存在")

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("DELETE FROM cache")
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM cache")
        remaining = cur.fetchone()[0]
        conn.close()

        return _ok(
            {"message": "TTL 缓存已清除", "remaining_entries": remaining},
            timing=(time.time() - t0) * 1000,
        )
    except Exception:
        logger.exception("data_error")
        return _err(_SAFE_ERROR_MSG)


@router.post("/vacuum")
async def vacuum_db():
    """回收数据库空间"""
    t0 = time.time()
    try:
        db_path = _get_db_path()
        size_before = os.path.getsize(db_path) / (1024 * 1024)

        conn = sqlite3.connect(db_path)
        conn.execute("VACUUM")
        conn.close()

        size_after = os.path.getsize(db_path) / (1024 * 1024)
        saved = round(size_before - size_after, 1)

        return _ok(
            {
                "size_before_mb": round(size_before, 1),
                "size_after_mb": round(size_after, 1),
                "saved_mb": saved,
            },
            timing=(time.time() - t0) * 1000,
        )
    except Exception:
        logger.exception("data_error")
        return _err(_SAFE_ERROR_MSG)


@router.get("/source-status")
async def source_status():
    """数据源健康检查 — 测试所有 K 线源和实时行情源"""
    t0 = time.time()
    try:
        from stock_analyzer.network_health import check_network_health

        health = check_network_health()

        sources = []
        # K 线源
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

        # 实时行情源
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

        return _ok(
            {"sources": sources, "mode": health.get("mode", "normal")},
            timing=(time.time() - t0) * 1000,
        )
    except Exception:
        logger.exception("data_error")
        return _err(_SAFE_ERROR_MSG)


# ═══════════════════════════════════════
# 文件导入端点（使用 bytes 替代 UploadFile 以减少依赖）
# ═══════════════════════════════════════


@router.post("/import")
async def import_data(
    file: bytes = Body(
        ..., media_type="application/octet-stream", description="CSV 或 JSON 文件内容"
    ),
    data_type: str = Query("kline", description="导入类型: kline|portfolio"),
    filename: str = Query("data.csv", description="上传文件名（用于解析股票代码）"),
):
    """导入数据 — 支持 CSV/JSON K 线数据或持仓 JSON"""
    t0 = time.time()
    try:
        import pandas as pd

        content = file

        if data_type == "kline":
            try:
                df = pd.read_csv(pd.io.common.BytesIO(content))
            except Exception:
                import json as _json

                data = _json.loads(content.decode("utf-8"))
                df = pd.DataFrame(data)

            required_cols = ["日期", "开盘", "最高", "最低", "收盘", "成交量"]
            for col in required_cols:
                if col not in df.columns:
                    return _err(f"缺少必要列: {col}")

            db_path = _get_db_path()
            conn = sqlite3.connect(db_path)
            import pickle

            code = filename.rsplit(".", 1)[0].split("_", maxsplit=1)[0]
            blob = pickle.dumps(df)
            conn.execute(
                "INSERT OR REPLACE INTO kline_store (code, data, updated_at) VALUES (?, ?, ?)",
                (code, blob, time.time()),
            )
            conn.commit()
            conn.close()
            return _ok({"imported": code, "rows": len(df)}, timing=(time.time() - t0) * 1000)

        elif data_type == "portfolio":
            import json as _json

            data = _json.loads(content.decode("utf-8"))
            name = data.get("name", filename.rsplit(".", 1)[0])
            fpath = os.path.join(PROJECT_ROOT, "portfolios", f"{name}.json")
            os.makedirs(os.path.dirname(fpath), exist_ok=True)
            with open(fpath, "w", encoding="utf-8") as f:
                _json.dump(data, f, ensure_ascii=False, indent=2)
            return _ok({"imported": name, "type": "portfolio"}, timing=(time.time() - t0) * 1000)

        else:
            return _err(f"不支持的导入类型: {data_type}")
    except Exception:
        logger.exception("data_error")
        return _err(_SAFE_ERROR_MSG)


@router.get("/export/{code}")
async def export_data(code: str, format: str = Query("json", description="导出格式: json|csv")):
    """导出个股数据"""
    t0 = time.time()
    try:
        from stock_analyzer.cache import cached_fundamentals, cached_kline

        kline = cached_kline(code)
        funds = cached_fundamentals(code)

        export = {
            "code": code,
            "export_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "fundamentals": funds if isinstance(funds, dict) else {},
        }

        if kline is not None and not kline.empty:
            if format == "csv":
                csv_str = kline.tail(60).to_csv(index=False)
                return {
                    "success": True,
                    "data": csv_str,
                    "error": None,
                    "freshness": "cached",
                    "timing_ms": round((time.time() - t0) * 1000),
                }
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

        return _ok(export, freshness="cached", timing=(time.time() - t0) * 1000)
    except Exception:
        logger.exception("data_error")
        return _err(_SAFE_ERROR_MSG)
