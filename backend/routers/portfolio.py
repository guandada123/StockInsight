"""持仓管理 API 路由

所有业务逻辑已下沉至 backend/services/portfolio_service.py。
本文件仅保留路由定义和参数校验。
"""

import logging
import time

from fastapi import APIRouter, Depends, Query

from backend.common import _err, _ok, validate_portfolio_name
from backend.schemas.requests import PortfolioCreateParams, PortfolioUpdateParams
from backend.services.portfolio_service import (
    analyze_portfolio,
    create_portfolio,
    delete_portfolio,
    get_portfolio,
    list_portfolios,
    update_portfolio_holding,
)

logger = logging.getLogger(__name__)
_SAFE_ERROR_MSG = "服务暂不可用，请稍后重试"

router = APIRouter(prefix="/api/portfolio", tags=["持仓管理"])


@router.get("/list")
async def list_portfolios_route():
    """列出所有持仓组合"""
    t0 = time.time()
    try:
        result = list_portfolios()
        return _ok(result, timing=(time.time() - t0) * 1000)
    except Exception:
        logger.exception("list_portfolios_failed")
        return _err(_SAFE_ERROR_MSG)


@router.get("/{name}")
async def get_portfolio_route(name: str):
    """获取持仓组合详情"""
    t0 = time.time()
    try:
        validate_portfolio_name(name)
        result = get_portfolio(name)
        return _ok(result, timing=(time.time() - t0) * 1000)
    except FileNotFoundError as e:
        return _err(str(e))
    except Exception:
        logger.exception("get_portfolio_failed: name=%s", name)
        return _err(_SAFE_ERROR_MSG)


@router.post("/create")
async def create_portfolio_route(
    params: PortfolioCreateParams = Depends(),
):
    """创建新持仓组合"""
    t0 = time.time()
    try:
        result = create_portfolio(params.name, codes=params.codes)
        return _ok(result, timing=(time.time() - t0) * 1000)
    except FileExistsError as e:
        return _err(str(e))
    except Exception:
        logger.exception("create_portfolio_failed: name=%s", params.name)
        return _err(_SAFE_ERROR_MSG)


@router.put("/{name}")
async def update_portfolio_holding_route(
    name: str,
    params: PortfolioUpdateParams = Depends(),
):
    """更新持仓组合中的股票"""
    t0 = time.time()
    try:
        result = update_portfolio_holding(
            name, params.code, params.shares, params.cost, params.action
        )
        return _ok(result, timing=(time.time() - t0) * 1000)
    except FileNotFoundError as e:
        return _err(str(e))
    except Exception:
        logger.exception("update_portfolio_failed: name=%s code=%s", name, params.code)
        return _err(_SAFE_ERROR_MSG)


@router.delete("/{name}")
async def delete_portfolio_route(name: str):
    """删除持仓组合"""
    t0 = time.time()
    try:
        validate_portfolio_name(name)
        result = delete_portfolio(name)
        return _ok(result, timing=(time.time() - t0) * 1000)
    except FileNotFoundError as e:
        return _err(str(e))
    except Exception:
        logger.exception("delete_portfolio_failed: name=%s", name)
        return _err(_SAFE_ERROR_MSG)


@router.get("/{name}/analysis")
async def analyze_portfolio_route(name: str):
    """组合分析 — 收益率/波动率/夏普/调仓建议"""
    t0 = time.time()
    try:
        validate_portfolio_name(name)
        result = analyze_portfolio(name)
        return _ok(result, timing=(time.time() - t0) * 1000)
    except FileNotFoundError as e:
        return _err(str(e))
    except Exception:
        logger.exception("get_portfolio_failed: name=%s", name)
        return _err(_SAFE_ERROR_MSG)
