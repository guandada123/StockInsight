"""大盘/行情/板块 API 路由

所有业务逻辑已下沉至 backend/services/market_service.py。
本文件仅保留路由定义和参数校验。
"""

import logging
import time

from fastapi import APIRouter, Depends, Query

from backend.common import _err, _ok
from backend.schemas.requests import BatchCodesParam
from backend.services.market_service import (
    build_batch_quotes,
    build_hot_sectors,
    build_indices_detail,
    build_limit_up_down,
    build_market_overview,
    build_sector_rotation,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market", tags=["市场行情"])

_SAFE_ERROR_MSG = "服务暂不可用，请稍后重试"


@router.get("/overview")
async def market_overview():
    """大盘总览 — 四大指数 + 涨跌停统计"""
    t0 = time.time()
    try:
        result = build_market_overview()
        return _ok(result, timing=(time.time() - t0) * 1000)
    except Exception:
        logger.exception("market_overview_failed")
        return _err(_SAFE_ERROR_MSG)


@router.get("/indices")
async def indices_detail():
    """四大指数详细数据"""
    t0 = time.time()
    try:
        result = build_indices_detail()
        return _ok({"indices": result}, timing=(time.time() - t0) * 1000)
    except Exception:
        logger.exception("indices_detail_failed")
        return _err(_SAFE_ERROR_MSG)


@router.get("/quotes")
async def batch_quotes(params: BatchCodesParam = Depends()):
    """批量实时行情"""
    t0 = time.time()
    try:
        result = build_batch_quotes(params.code_list)
        return _ok(result, timing=(time.time() - t0) * 1000)
    except ValueError as ve:
        return _err(str(ve))
    except Exception:
        logger.exception("batch_quotes_failed")
        return _err(_SAFE_ERROR_MSG)


@router.get("/limit-up-down")
async def limit_up_down():
    """涨跌停统计"""
    t0 = time.time()
    try:
        result = build_limit_up_down()
        return _ok(result, freshness="cached", timing=(time.time() - t0) * 1000)
    except Exception:
        logger.exception("limit_up_down_failed")
        return _err(_SAFE_ERROR_MSG)


@router.get("/sector-rotation")
async def sector_rotation():
    """板块轮动排名"""
    t0 = time.time()
    try:
        result = build_sector_rotation(top_n=30)
        return _ok(result, freshness="cached", timing=(time.time() - t0) * 1000)
    except Exception:
        logger.exception("sector_rotation_failed")
        return _err(_SAFE_ERROR_MSG)


@router.get("/hot-sectors")
async def hot_sectors(top_n: int = Query(10, description="返回前N个板块")):
    """热门板块（涨跌幅 + 资金流向综合排名）"""
    t0 = time.time()
    try:
        result = build_hot_sectors(top_n=top_n)
        return _ok(result, freshness="cached", timing=(time.time() - t0) * 1000)
    except Exception:
        logger.exception("hot_sectors_failed")
        return _err(_SAFE_ERROR_MSG)
