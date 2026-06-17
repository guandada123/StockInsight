"""个股分析 API 路由 — L0-L7 七层全出

所有业务逻辑已下沉至 backend/services/analysis_service.py。
本文件仅保留路由定义和参数校验。
"""

import logging
import time

from fastapi import APIRouter, Query

from backend.common import _err, _ok
from backend.services.analysis_service import (
    build_fund_flow_data,
    build_indicator_data,
    build_kline_data,
    cached_analysis,
    run_fast_analysis,
)

logger = logging.getLogger(__name__)

_SAFE_ERROR_MSG = "服务暂不可用，请稍后重试"

router = APIRouter(prefix="/api/analysis", tags=["个股分析"])


# ── 核心分析 ────────────────────────────────────────


@router.get("/{code}")
async def analyze_stock(code: str):
    """个股标准分析（L0-L5 基础层）"""
    t0 = time.time()
    try:
        result = cached_analysis(code, full=False)
        return _ok(result, timing=(time.time() - t0) * 1000)
    except Exception:
        logger.exception("analyze_stock_failed: code=%s", code)
        return _err(_SAFE_ERROR_MSG)


@router.get("/{code}/full")
async def analyze_stock_full(code: str):
    """个股全维度分析（L0-L7 + 多空辩论 + ML 预测）"""
    t0 = time.time()
    try:
        result = cached_analysis(code, full=True)
        return _ok(result, timing=(time.time() - t0) * 1000)
    except Exception:
        logger.exception("analyze_stock_failed: code=%s", code)
        return _err(_SAFE_ERROR_MSG)


@router.get("/{code}/quality")
async def analyze_quality(code: str):
    """公司质地七问"""
    t0 = time.time()
    try:
        from stock_analyzer.business_quality import full_business_quality

        result = full_business_quality(code)
        return _ok(result, timing=(time.time() - t0) * 1000)
    except Exception:
        logger.exception("analyze_stock_failed: code=%s", code)
        return _err(_SAFE_ERROR_MSG)


@router.get("/{code}/fast")
async def analyze_stock_fast(code: str):
    """快速分析 — 纯本地 L0-L2，200ms 级别"""
    t0 = time.time()
    try:
        result = run_fast_analysis(code)
        return _ok(result, freshness="fresh", timing=(time.time() - t0) * 1000)
    except Exception:
        logger.exception("analyze_stock_fast_failed: code=%s", code)
        return _err(_SAFE_ERROR_MSG)


@router.get("/owned")
async def analyze_owned():
    """批量持仓分析"""
    t0 = time.time()
    try:
        import glob
        import json

        files = sorted(glob.glob("mainboard_owned_*.json"), reverse=True)
        if not files:
            return _err("未找到持仓文件")
        with open(files[0], encoding="utf-8") as f:
            owned = json.load(f)
        if not owned:
            return _err("持仓文件为空")

        from stock_analyzer.fetcher import sina_real_time

        codes = list(owned.keys())
        rt = sina_real_time(codes)

        results = []
        for code, pos in owned.items():
            info = rt.get(code, {})
            p = float(info.get("最新价", 0) or 0)
            cost = pos.get("cost", 0)
            shares = pos.get("shares", 0)
            mv = p * shares
            profit = (p - cost) * shares if cost else 0
            profit_pct = round((p - cost) / cost * 100, 2) if cost else 0
            results.append(
                {
                    "code": code,
                    "name": info.get("名称", code),
                    "shares": shares,
                    "cost": cost,
                    "current_price": p,
                    "market_value": round(mv, 2),
                    "profit_amount": round(profit, 2),
                    "profit_pct": profit_pct,
                }
            )

        total_value = sum(r["market_value"] for r in results)
        total_profit = sum(r["profit_amount"] for r in results)
        total_cost = sum(r["cost"] * r["shares"] for r in results)

        return _ok(
            {
                "holdings": results,
                "total_value": round(total_value, 2),
                "total_profit": round(total_profit, 2),
                "total_profit_pct": round(total_profit / total_cost * 100, 2) if total_cost else 0,
                "count": len(results),
                "update_time": time.strftime("%H:%M:%S"),
            },
            timing=(time.time() - t0) * 1000,
        )
    except Exception:
        logger.exception("analyze_owned_failed")
        return _err(_SAFE_ERROR_MSG)


@router.get("/{code}/kline")
async def get_kline_data(
    code: str,
    ktype: str = Query("day", description="K线类型: day|week|month"),
    days: int = Query(120, description="获取天数"),
):
    """获取K线JSON数据（供前端 ECharts 渲染）"""
    t0 = time.time()
    try:
        result = build_kline_data(code, ktype=ktype, days=days)
        return _ok(result, freshness="cached", timing=(time.time() - t0) * 1000)
    except ValueError as ve:
        return _err(str(ve))
    except Exception:
        logger.exception("api_error")
        return _err(_SAFE_ERROR_MSG)


@router.get("/{code}/indicators")
async def get_indicator_data(
    code: str,
    indicator: str = Query("macd", description="指标类型: macd|rsi|kdj"),
):
    """获取技术指标JSON数据（供前端 ECharts 渲染）"""
    t0 = time.time()
    try:
        result = build_indicator_data(code, indicator=indicator)
        return _ok(result, freshness="cached", timing=(time.time() - t0) * 1000)
    except ValueError as ve:
        return _err(str(ve))
    except Exception:
        logger.exception("api_error")
        return _err(_SAFE_ERROR_MSG)


@router.get("/{code}/fund-flow")
async def get_fund_flow_data(code: str, days: int = Query(20)):
    """获取资金流向数据"""
    t0 = time.time()
    try:
        result = build_fund_flow_data(code, days=days)
        return _ok(result, freshness="cached", timing=(time.time() - t0) * 1000)
    except ValueError as ve:
        return _err(str(ve))
    except Exception:
        logger.exception("get_fund_flow_failed: code=%s", code)
        return _err(_SAFE_ERROR_MSG)
