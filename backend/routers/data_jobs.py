"""数据下载作业 API — Tushare 数据管线"""

import logging
import time

from fastapi import APIRouter, Query

from backend.common import _err, _ok

logger = logging.getLogger(__name__)
_SAFE_ERROR_MSG = "服务暂不可用，请稍后重试"

router = APIRouter(prefix="/api/data-jobs", tags=["数据下载"])


@router.post("/submit")
async def submit_job(
    job_type: str = Query(
        ..., description="任务类型: trade_calendar|stock_basic|daily_history|daily_basic"
    ),
    start_date: str | None = Query(None, description="起始日期 20250101"),
    end_date: str | None = Query(None, description="结束日期 20251231"),
):
    """提交数据下载任务"""
    t0 = time.time()
    try:
        from stock_analyzer.tushare_loader import submit_job as _submit

        params = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        job_id = _submit(job_type, params)
        return _ok({"job_id": job_id}, timing=(time.time() - t0) * 1000)
    except Exception:
        logger.exception("submit_job_failed: job_type=%s", job_type)
        return _err(_SAFE_ERROR_MSG)


@router.get("/status/{job_id}")
async def job_status(job_id: str):
    """查询任务状态"""
    t0 = time.time()
    try:
        from stock_analyzer.tushare_loader import get_job_status

        s = get_job_status(job_id)
        if s is None:
            return _err(f"任务不存在: {job_id}")
        return _ok(s, timing=(time.time() - t0) * 1000)
    except Exception:
        logger.exception("job_status_failed: job_id=%s", job_id)
        return _err(_SAFE_ERROR_MSG)


@router.get("/list")
async def list_jobs(
    limit: int = Query(20),
    status: str | None = Query(None),
):
    """列出最近的任务"""
    t0 = time.time()
    try:
        from stock_analyzer.tushare_loader import list_jobs as _list

        jobs = _list(limit, status)
        return _ok({"jobs": jobs, "total": len(jobs)}, timing=(time.time() - t0) * 1000)
    except Exception:
        logger.exception("list_jobs_failed")
        return _err(_SAFE_ERROR_MSG)


@router.get("/job-types")
async def job_types():
    """列出可用的任务类型"""
    return _ok(
        {
            "types": [
                {"id": "trade_calendar", "name": "交易日历", "desc": "下载交易所交易日历数据"},
                {"id": "stock_basic", "name": "股票列表", "desc": "下载全量A股基础信息"},
                {
                    "id": "daily_history",
                    "name": "日线历史",
                    "desc": "按交易日逐日下载日K线 (需先下载交易日历)",
                },
                {
                    "id": "daily_basic",
                    "name": "基本面数据",
                    "desc": "下载每日PE/PB/市值等基本面指标",
                },
                {
                    "id": "moneyflow",
                    "name": "资金流向",
                    "desc": "下载个股每日资金流向(主力/超大单/大单/中单/小单)",
                },
                {"id": "industry", "name": "行业分类", "desc": "下载全量A股行业分类(110个行业)"},
            ]
        }
    )
