"""SSE 进度跟踪系统 — 内存级任务状态管理器

用法:
    tracker = ProgressTracker()
    task_id = tracker.create("批量扫描")
    tracker.update(task_id, progress=50, message="正在分析第 5/10 只股票...")
    # 其他协程通过 asyncio.Queue 消费进度事件
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProgressEvent:
    """单个进度事件"""
    progress: float  # 0-100
    message: str
    status: str = "running"  # running | completed | failed
    result: Any = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class ProgressTask:
    """进度任务"""
    id: str
    name: str
    total_items: int = 0
    completed_items: int = 0
    event: ProgressEvent = field(default_factory=lambda: ProgressEvent(0, "等待开始", "pending"))
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class ProgressTracker:
    """SSE 进度跟踪器（线程安全，内存级）"""

    def __init__(self):
        self._tasks: dict[str, ProgressTask] = {}
        self._lock = asyncio.Lock()
        # 自动清理过期任务（默认 30 分钟）
        self._cleanup_interval = 1800

    async def create(self, name: str, total_items: int = 0) -> str:
        """创建新任务，返回 task_id"""
        task_id = uuid.uuid4().hex[:12]
        async with self._lock:
            self._tasks[task_id] = ProgressTask(
                id=task_id,
                name=name,
                total_items=total_items,
            )
        return task_id

    async def update(
        self,
        task_id: str,
        progress: float | None = None,
        message: str | None = None,
        status: str | None = None,
        completed_items: int | None = None,
        result: Any = None,
    ):
        """更新任务进度并推送到 SSE 队列"""
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return

            if progress is not None:
                task.event.progress = round(progress, 1)
            if message is not None:
                task.event.message = message
            if status is not None:
                task.event.status = status
            if completed_items is not None:
                task.completed_items = completed_items
            if result is not None:
                task.event.result = result

            task.updated_at = time.time()
            # 推送到队列供 SSE 消费者读取
            await task.queue.put(ProgressEvent(
                progress=task.event.progress,
                message=task.event.message,
                status=task.event.status,
                result=task.event.result,
            ))

            # 终端状态清理队列
            if task.event.status in ("completed", "failed"):
                # 标记队列结束
                await task.queue.put(None)

    async def get(self, task_id: str) -> ProgressTask | None:
        """获取任务状态"""
        async with self._lock:
            return self._tasks.get(task_id)

    async def list_active(self) -> list[dict]:
        """列出活跃任务"""
        async with self._lock:
            now = time.time()
            active = []
            for tid, task in self._tasks.items():
                if task.event.status in ("running", "pending"):
                    active.append({
                        "id": tid,
                        "name": task.name,
                        "status": task.event.status,
                        "progress": task.event.progress,
                        "message": task.event.message,
                        "total_items": task.total_items,
                        "completed_items": task.completed_items,
                        "elapsed_seconds": round(now - task.created_at, 1),
                    })
            return active

    async def cleanup(self):
        """清理过期任务"""
        async with self._lock:
            now = time.time()
            stale = [
                tid for tid, task in self._tasks.items()
                if task.event.status in ("completed", "failed")
                and now - task.updated_at > self._cleanup_interval
            ]
            for tid in stale:
                del self._tasks[tid]

    async def remove(self, task_id: str):
        """手动移除任务"""
        async with self._lock:
            self._tasks.pop(task_id, None)


# 全局单例
tracker = ProgressTracker()
