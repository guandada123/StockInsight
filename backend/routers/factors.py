"""自定义因子管理 API"""

import logging
import time

from fastapi import APIRouter, Body, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)
_SAFE_ERROR_MSG = "服务暂不可用，请稍后重试"

router = APIRouter(prefix="/api/factors", tags=["因子管理"])


class FactorCreateRequest(BaseModel):
    factor_id: str
    name: str
    expression: str
    factor_type: str = "custom"
    description: str = ""


def _ok(data, timing=0):
    return {"success": True, "data": data, "error": None, "timing_ms": round(timing, 1)}


def _err(msg):
    return {"success": False, "data": None, "error": str(msg), "timing_ms": 0}


@router.get("/list")
async def list_factors():
    """列出所有自定义因子"""
    t0 = time.time()
    try:
        from stock_analyzer.custom_factors import list_factors as _list

        factors = _list()
        return _ok({"factors": factors, "total": len(factors)}, timing=(time.time() - t0) * 1000)
    except Exception:
        logger.exception("factors_error")
        return _err(_SAFE_ERROR_MSG)


@router.post("/create")
async def create_factor(
    factor_id: str = Body(...),
    name: str = Body(...),
    expression: str = Body(...),
    factor_type: str = Body("custom"),
    description: str = Body(""),
):
    """创建自定义因子 (JSON body)"""
    t0 = time.time()
    try:
        import pandas as pd

        from stock_analyzer.custom_factors import FactorExpressionEngine

        # 预验证表达式
        engine = FactorExpressionEngine()
        dummy = pd.DataFrame(
            {
                "close": [100, 101, 102],
                "vol": [1000, 1100, 1050],
                "open": [99, 100, 101],
                "high": [101, 102, 103],
                "low": [98, 99, 100],
            }
        )
        engine.evaluate(expression, dummy)  # 会抛异常如果不合法
        from stock_analyzer.custom_factors import create_factor as _create

        r = _create(factor_id, name, expression, factor_type, description)
        return _ok(r, timing=(time.time() - t0) * 1000)
    except ValueError as ve:
        return _err(f"表达式不合法: {ve}")
    except Exception:
        logger.exception("factors_error")
        return _err(_SAFE_ERROR_MSG)


@router.delete("/{factor_id}")
async def delete_factor(factor_id: str):
    """删除自定义因子"""
    t0 = time.time()
    try:
        from stock_analyzer.custom_factors import delete_factor as _del

        _del(factor_id)
        return _ok({"deleted": factor_id}, timing=(time.time() - t0) * 1000)
    except Exception:
        logger.exception("factors_error")
        return _err(_SAFE_ERROR_MSG)


@router.get("/compute/{code}")
async def compute_factors(code: str, factor_id: str | None = Query(None)):
    """计算股票的自定义因子值"""
    t0 = time.time()
    try:
        from stock_analyzer.custom_factors import compute_all_factors, compute_factor

        if factor_id:
            r = compute_factor(code, factor_id)
            return _ok(r, timing=(time.time() - t0) * 1000)
        else:
            results = compute_all_factors(code)
            return _ok({"code": code, "factors": results}, timing=(time.time() - t0) * 1000)
    except Exception:
        logger.exception("factors_error")
        return _err(_SAFE_ERROR_MSG)


@router.post("/validate")
async def validate_expression(expression: str = Query(...)):
    """验证因子表达式 (语法+安全白名单)"""
    t0 = time.time()
    try:
        import pandas as pd

        from stock_analyzer.custom_factors import FactorExpressionEngine

        engine = FactorExpressionEngine()
        dummy = pd.DataFrame(
            {
                "close": [100, 101, 102],
                "vol": [1000, 1100, 1050],
                "open": [99, 100, 101],
                "high": [101, 102, 103],
                "low": [98, 99, 100],
                "amount": [500, 550, 525],
                "pre_close": [100, 100, 101],
                "pct_chg": [0, 1, -0.5],
                "change_c": [0, 1, -0.5],
            }
        )
        engine.evaluate(expression, dummy)
        return _ok({"valid": True, "expression": expression}, timing=(time.time() - t0) * 1000)
    except (SyntaxError, ValueError) as e:
        return _ok({"valid": False, "error": str(e)}, timing=(time.time() - t0) * 1000)
    except Exception as e:
        return _ok({"valid": False, "error": str(e)}, timing=(time.time() - t0) * 1000)
