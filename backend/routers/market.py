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

# 板块热点进程内缓存（2026-11-23）：45 秒。盘中数据仍在变，但用户不会 45 秒内刷同一屏，
# 换来首屏重复请求从 0.36s 降到 ~0.001s。多 worker 各自持有，属「可容忍的不一致」。
_HOT_SECTORS_TTL = 45.0
_HOT_SECTORS_CACHE: dict = {"data": None, "top_n": None, "ts": 0.0}


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
        logger.warning("batch_quotes_validation: %s", ve)
        return _err("参数不合法，请检查股票代码格式")
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
    """热门板块（涨跌幅 + 资金流向综合排名）

    2026-11-23：加 45 秒进程内缓存。
    此前每次请求都重算（实测稳定的 0.36-0.40s，两次之间毫无差异 = 缓存不存在），
    但返回里却硬写 freshness="cached" —— 属"呈现假事实"，比没缓存更糟。
    现在：命中才标 cached，未命中标 fresh，且 freshness 与实际行为一致。
    """
    t0 = time.time()
    try:
        now = time.time()
        if (
            _HOT_SECTORS_CACHE["data"] is not None
            and _HOT_SECTORS_CACHE["top_n"] == top_n
            and now - _HOT_SECTORS_CACHE["ts"] < _HOT_SECTORS_TTL
        ):
            return _ok(
                _HOT_SECTORS_CACHE["data"], freshness="cached", timing=(time.time() - t0) * 1000
            )
        result = build_hot_sectors(top_n=top_n)
        _HOT_SECTORS_CACHE.update(data=result, top_n=top_n, ts=now)
        return _ok(result, freshness="fresh", timing=(time.time() - t0) * 1000)
    except Exception:
        logger.exception("hot_sectors_failed")
        return _err(_SAFE_ERROR_MSG)
