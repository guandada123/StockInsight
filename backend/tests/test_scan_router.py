"""backend/routers/scan.py 测试（2026-10-18 补齐：原覆盖率 32.79%）

覆盖：
- _spawn_background 强引用生命周期（2026-10-16 修复的 asyncio 弱引用 GC 问题）
- _sse_generator 六个分支：任务不存在 / 正常事件流 / completed 终止 /
  队列 None 终止 / TimeoutError / 其他异常
- sse_progress 404 与 StreamingResponse headers
- batch_scan 参数校验（空 / 超 50）+ 正常路径
- list_tasks cleanup + 返回结构
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.routers import scan
from backend.scan_progress import ProgressEvent, ProgressTask


def _make_task(task_id="t1", name="测试任务", total=3) -> ProgressTask:
    return ProgressTask(id=task_id, name=name, total_items=total)


def _parse_sse(chunk: str) -> tuple[str, dict]:
    """把 SSE 文本块解析为 (event, data)"""
    lines = chunk.strip().split("\n")
    event = lines[0].replace("event: ", "")
    data = json.loads(lines[1].replace("data: ", ""))
    return event, data


@pytest.fixture
def fake_tracker():
    t = MagicMock()
    t.get = AsyncMock(return_value=None)
    t.create = AsyncMock(return_value="task-123")
    t.update = AsyncMock()
    t.cleanup = AsyncMock()
    t.list_active = AsyncMock(return_value=[{"id": "a"}, {"id": "b"}])
    return t


# ══════════════════════════════════════════
#  后台任务强引用
# ══════════════════════════════════════════


class TestSpawnBackground:
    @pytest.mark.asyncio
    async def test_task_tracked_then_removed(self):
        scan._BACKGROUND_TASKS.clear()
        task = scan._spawn_background(asyncio.sleep(0))
        assert task in scan._BACKGROUND_TASKS
        await task
        await asyncio.sleep(0)  # 让 done_callback 执行
        assert task not in scan._BACKGROUND_TASKS

    @pytest.mark.asyncio
    async def test_returns_task_object(self):
        scan._BACKGROUND_TASKS.clear()
        task = scan._spawn_background(asyncio.sleep(0))
        assert isinstance(task, asyncio.Task)
        await task


# ══════════════════════════════════════════
#  SSE 生成器
# ══════════════════════════════════════════


class TestSseGenerator:
    @pytest.mark.asyncio
    async def test_task_not_found(self, fake_tracker):
        fake_tracker.get.return_value = None
        with patch.object(scan, "tracker", fake_tracker):
            chunks = [c async for c in scan._sse_generator("missing")]
        assert len(chunks) == 1
        event, data = _parse_sse(chunks[0])
        assert event == "error"
        assert data["task_id"] == "missing"

    @pytest.mark.asyncio
    async def test_initial_state_pushed(self, fake_tracker):
        task = _make_task()
        task.event = ProgressEvent(0, "等待开始", status="pending")
        fake_tracker.get.return_value = task
        with patch.object(scan, "tracker", fake_tracker):
            gen = scan._sse_generator("t1")
            first = await gen.__anext__()
            event, data = _parse_sse(first)
            assert event == "progress"
            assert data["task_id"] == "t1"
            assert data["name"] == "测试任务"
            assert data["total_items"] == 3
            await gen.aclose()

    @pytest.mark.asyncio
    async def test_normal_event_then_completed(self, fake_tracker):
        task = _make_task()
        await task.queue.put(ProgressEvent(50, "half"))
        await task.queue.put(ProgressEvent(100, "done", status="completed", result={"ok": 1}))
        fake_tracker.get.return_value = task
        with patch.object(scan, "tracker", fake_tracker):
            chunks = [c async for c in scan._sse_generator("t1")]
        events = [_parse_sse(c) for c in chunks]
        # 初始 + 2 progress + 1 done
        assert [e for e, _ in events] == ["progress", "progress", "progress", "done"]
        assert events[2][1]["status"] == "completed"
        assert events[3][1]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_failed_status_emits_done(self, fake_tracker):
        task = _make_task()
        await task.queue.put(ProgressEvent(30, "boom", status="failed"))
        fake_tracker.get.return_value = task
        with patch.object(scan, "tracker", fake_tracker):
            chunks = [c async for c in scan._sse_generator("t1")]
        assert _parse_sse(chunks[-1])[0] == "done"
        assert _parse_sse(chunks[-1])[1]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_queue_none_breaks_without_done(self, fake_tracker):
        task = _make_task()
        await task.queue.put(None)
        fake_tracker.get.return_value = task
        with patch.object(scan, "tracker", fake_tracker):
            chunks = [c async for c in scan._sse_generator("t1")]
        # 只有初始 progress，无 done
        assert len(chunks) == 1
        assert _parse_sse(chunks[0])[0] == "progress"

    @pytest.mark.asyncio
    async def test_timeout_emits_timeout_event(self, fake_tracker):
        task = _make_task()
        fake_tracker.get.return_value = task
        with (
            patch.object(scan, "tracker", fake_tracker),
            patch("asyncio.wait_for", side_effect=TimeoutError),
        ):
            chunks = [c async for c in scan._sse_generator("t1")]
        event, data = _parse_sse(chunks[-1])
        assert event == "timeout"
        assert data["message"] == "连接超时"

    @pytest.mark.asyncio
    async def test_generic_exception_emits_error(self, fake_tracker):
        task = _make_task()
        fake_tracker.get.return_value = task
        with (
            patch.object(scan, "tracker", fake_tracker),
            patch("asyncio.wait_for", side_effect=RuntimeError("boom")),
        ):
            chunks = [c async for c in scan._sse_generator("t1")]
        event, data = _parse_sse(chunks[-1])
        assert event == "error"
        assert "boom" in data["error"]


# ══════════════════════════════════════════
#  SSE 端点
# ══════════════════════════════════════════


class TestSseProgressEndpoint:
    @pytest.mark.asyncio
    async def test_404_when_task_missing(self, fake_tracker):
        fake_tracker.get.return_value = None
        with patch.object(scan, "tracker", fake_tracker):
            with pytest.raises(HTTPException) as ei:
                await scan.sse_progress("nope")
        assert ei.value.status_code == 404

    @pytest.mark.asyncio
    async def test_streaming_response_headers(self, fake_tracker):
        fake_tracker.get.return_value = _make_task()
        with patch.object(scan, "tracker", fake_tracker):
            resp = await scan.sse_progress("t1")
        assert resp.media_type == "text/event-stream"
        assert resp.headers["Cache-Control"] == "no-cache"
        assert resp.headers["X-Accel-Buffering"] == "no"


# ══════════════════════════════════════════
#  批量扫描
# ══════════════════════════════════════════


class TestBatchScan:
    @pytest.mark.asyncio
    async def test_empty_codes_rejected(self, fake_tracker):
        with patch.object(scan, "tracker", fake_tracker):
            r = await scan.batch_scan(codes=" , , ")
        assert r["success"] is False or "error" in r
        fake_tracker.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_too_many_codes_rejected(self, fake_tracker):
        codes = ",".join(f"{i:06d}" for i in range(51))
        with patch.object(scan, "tracker", fake_tracker):
            r = await scan.batch_scan(codes=codes)
        assert r["success"] is False or "error" in r
        fake_tracker.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_normal_path_creates_task(self, fake_tracker):
        scan._BACKGROUND_TASKS.clear()
        with (
            patch.object(scan, "tracker", fake_tracker),
            patch.object(scan, "run_batch_scan", AsyncMock()) as m,
        ):
            r = await scan.batch_scan(codes="000001, 000002,000003")
            await asyncio.sleep(0)  # 让真实 _spawn_background 的后台任务执行完
        assert r["success"] is True or "data" in r
        payload = r.get("data", r)
        assert payload["task_id"] == "task-123"
        assert payload["total"] == 3
        assert payload["sse_url"] == "/api/scan/progress/task-123"
        fake_tracker.create.assert_awaited_once()
        fake_tracker.update.assert_awaited_once()
        m.assert_awaited_once()


# ══════════════════════════════════════════
#  活跃任务列表
# ══════════════════════════════════════════


class TestListTasks:
    @pytest.mark.asyncio
    async def test_cleanup_then_list(self, fake_tracker):
        with patch.object(scan, "tracker", fake_tracker):
            r = await scan.list_tasks()
        fake_tracker.cleanup.assert_awaited_once()
        payload = r.get("data", r)
        assert payload["count"] == 2
        assert len(payload["tasks"]) == 2
