"""数据管理 API 路由 — DB统计/缓存/导入导出/数据源健康

所有业务逻辑已下沉至 backend/services/data_service.py。
本文件仅保留路由定义和参数校验。
"""

import logging
import time

from fastapi import APIRouter, Body, Query

from backend.common import _err, _ok
from backend.services.data_service import (
    clear_cache,
    export_data,
    get_data_stats,
    get_source_status,
    import_data,
    vacuum_db,
)

logger = logging.getLogger(__name__)
_SAFE_ERROR_MSG = "服务暂不可用，请稍后重试"

router = APIRouter(prefix="/api/data", tags=["数据管理"])


@router.get("/stats")
async def data_stats():
    """数据库统计 — 大小、表行数、更新时间"""
    t0 = time.time()
    try:
        result = await get_data_stats()
        return _ok(result, timing=(time.time() - t0) * 1000)
    except FileNotFoundError as e:
        return _err(str(e))
    except Exception:
        logger.exception("data_error")
        return _err(_SAFE_ERROR_MSG)


@router.post("/clear-cache")
async def clear_cache_route():
    """清除 TTL 缓存（不删除永久存储的 K线/基本面/国家队数据）"""
    t0 = time.time()
    try:
        result = await clear_cache()
        return _ok(result, timing=(time.time() - t0) * 1000)
    except FileNotFoundError as e:
        return _err(str(e))
    except Exception:
        logger.exception("data_error")
        return _err(_SAFE_ERROR_MSG)


@router.post("/vacuum")
async def vacuum_db_route():
    """回收数据库空间"""
    t0 = time.time()
    try:
        result = await vacuum_db()
        return _ok(result, timing=(time.time() - t0) * 1000)
    except Exception:
        logger.exception("data_error")
        return _err(_SAFE_ERROR_MSG)


@router.get("/source-status")
async def source_status_route():
    """数据源健康检查 — 测试所有 K 线源和实时行情源"""
    t0 = time.time()
    try:
        result = get_source_status()
        return _ok(result, timing=(time.time() - t0) * 1000)
    except Exception:
        logger.exception("data_error")
        return _err(_SAFE_ERROR_MSG)


@router.post("/import")
async def import_data_route(
    file: bytes = Body(
        ..., media_type="application/octet-stream", description="CSV 或 JSON 文件内容"
    ),
    data_type: str = Query("kline", description="导入类型: kline|portfolio"),
    filename: str = Query("data.csv", description="上传文件名（用于解析股票代码）"),
):
    """导入数据 — 支持 CSV/JSON K 线数据或持仓 JSON"""
    t0 = time.time()
    try:
        result = await import_data(file, data_type, filename)
        return _ok(result, timing=(time.time() - t0) * 1000)
    except ValueError as ve:
        return _err(str(ve))
    except Exception:
        logger.exception("data_error")
        return _err(_SAFE_ERROR_MSG)


@router.get("/export/{code}")
async def export_data_route(
    code: str, format: str = Query("json", description="导出格式: json|csv")
):
    """导出个股数据"""
    t0 = time.time()
    try:
        result = export_data(code, fmt=format)
        if format == "csv" and "data" in result:
            return {
                "success": True,
                "data": result["data"],
                "error": None,
                "freshness": "cached",
                "timing_ms": round((time.time() - t0) * 1000),
            }
        return _ok(result, freshness="cached", timing=(time.time() - t0) * 1000)
    except Exception:
        logger.exception("data_error")
        return _err(_SAFE_ERROR_MSG)
