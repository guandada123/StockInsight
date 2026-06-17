"""扫描进度 API — SSE 实时推送 + 批量扫描

端点:
    GET  /api/scan/progress/{task_id}  — SSE 实时进度流
    POST /api/scan/batch              — 批量扫描股票（带进度推送）
    GET  /api/scan/tasks              — 活跃任务列表

批量扫描业务逻辑已下沉至 backend/services/scan_service.py。
"""

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.common import _err, _ok
from backend.scan_progress import tracker
from backend.services.scan_service import run_batch_scan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scan", tags=["扫描进度"])

_SAFE_ERROR_MSG = "服务暂不可用，请稍后重试"


# ── SSE 进度流 ──────────────────────────────────────


async def _sse_generator(task_id: str):
    """SSE 事件生成器 — 从任务队列读取事件并推送"""
    task = await tracker.get(task_id)
    if task is None:
        yield f"event: error\ndata: {json.dumps({'error': '任务不存在', 'task_id': task_id})}\n\n"
        return

    # 先推送当前状态
    initial = {
        "task_id": task_id,
        "name": task.name,
        "progress": task.event.progress,
        "message": task.event.message,
        "status": task.event.status,
        "total_items": task.total_items,
        "completed_items": task.completed_items,
    }
    yield f"event: progress\ndata: {json.dumps(initial)}\n\n"

    # 持续读取队列
    try:
        while True:
            event = await asyncio.wait_for(task.queue.get(), timeout=300)
            if event is None:
                break
            data = {
                "task_id": task_id,
                "progress": event.progress,
                "message": event.message,
                "status": event.status,
                "result": event.result,
            }
            yield f"event: progress\ndata: {json.dumps(data)}\n\n"

            if event.status in ("completed", "failed"):
                yield f"event: done\ndata: {json.dumps({'task_id': task_id, 'status': event.status})}\n\n"
                break
    except asyncio.TimeoutError:
        yield f"event: timeout\ndata: {json.dumps({'task_id': task_id, 'message': '连接超时'})}\n\n"
    except Exception as e:
        logger.exception("SSE generator error: task=%s", task_id)
        yield f"event: error\ndata: {json.dumps({'task_id': task_id, 'error': str(e)})}\n\n"


@router.get("/progress/{task_id}")
async def sse_progress(task_id: str):
    """SSE 实时进度流 — 前端通过 EventSource 连接"""
    task = await tracker.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    return StreamingResponse(
        _sse_generator(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 批量扫描 ─────────────────────────────────────────


@router.post("/batch")
async def batch_scan(
    codes: str = Query(..., description="股票代码列表，逗号分隔，最多 50 只"),
):
    """批量扫描 — 创建 SSE 进度任务并后台执行

    前端调用流程:
    1. POST /api/scan/batch?codes=000001,000002,000003
    2. 返回 task_id
    3. new EventSource('/api/scan/progress/{task_id}') 连接 SSE 流
    4. 监听 progress 事件更新 UI 进度条
    """
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        return _err("请提供至少一个有效的股票代码")
    if len(code_list) > 50:
        return _err("单次批量扫描最多 50 只股票")

    task_id = await tracker.create(f"批量扫描 {len(code_list)} 只股票", total_items=len(code_list))
    await tracker.update(task_id, progress=0, message=f"任务已创建，共 {len(code_list)} 只股票")

    # 后台执行（委托给 service 层）
    asyncio.create_task(run_batch_scan(task_id, code_list))

    return _ok(
        {
            "task_id": task_id,
            "total": len(code_list),
            "sse_url": f"/api/scan/progress/{task_id}",
        }
    )


# ── 活跃任务 ─────────────────────────────────────────


@router.get("/tasks")
async def list_tasks():
    """列出当前活跃的扫描任务"""
    await tracker.cleanup()
    tasks = await tracker.list_active()
    return _ok({"tasks": tasks, "count": len(tasks)})
