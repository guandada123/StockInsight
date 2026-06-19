"""测试 backend/scan_progress.py — SSE 进度跟踪系统"""

import asyncio
import time

import pytest
import pytest_asyncio

from backend.scan_progress import ProgressEvent, ProgressTask, ProgressTracker

# ── 测试辅助 ────────────────────────────────────


@pytest_asyncio.fixture
async def tracker():
    """每个测试一个全新的 tracker"""
    t = ProgressTracker()
    yield t


# ════════════════════════════════════════════
# 数据类创建
# ════════════════════════════════════════════


class TestProgressEvent:
    """ProgressEvent dataclass"""

    def test_default_values(self):
        """默认值正确"""
        event = ProgressEvent(progress=0, message="start")
        assert event.progress == 0
        assert event.message == "start"
        assert event.status == "running"
        assert event.result is None
        assert isinstance(event.timestamp, float)
        assert event.timestamp > 0

    def test_with_result(self):
        """带 result 的构造"""
        event = ProgressEvent(50, "half", status="completed", result={"count": 10})
        assert event.progress == 50
        assert event.status == "completed"
        assert event.result == {"count": 10}


class TestProgressTask:
    """ProgressTask dataclass"""

    def test_default_values(self):
        """默认值正确"""
        task = ProgressTask(id="abc", name="test")
        assert task.id == "abc"
        assert task.name == "test"
        assert task.total_items == 0
        assert task.completed_items == 0
        assert task.event.status == "pending"
        assert task.event.progress == 0
        assert isinstance(task.created_at, float)
        assert isinstance(task.updated_at, float)


# ════════════════════════════════════════════
# ProgressTracker 生命周期
# ════════════════════════════════════════════


@pytest.mark.asyncio
class TestTrackerCreate:
    """创建任务"""

    async def test_create_returns_id(self, tracker):
        """create 返回非空 task_id"""
        task_id = await tracker.create("批量扫描")
        assert task_id is not None
        assert len(task_id) == 12  # uuid hex[:12]

    async def test_create_with_total_items(self, tracker):
        """创建时指定 total_items"""
        task_id = await tracker.create("数据采集", total_items=100)
        task = await tracker.get(task_id)
        assert task is not None
        assert task.total_items == 100
        assert task.name == "数据采集"
        assert task.event.status == "pending"

    async def test_create_multiple_tasks(self, tracker):
        """多次创建产生不同 id"""
        id1 = await tracker.create("任务A")
        id2 = await tracker.create("任务B")
        assert id1 != id2

        task1 = await tracker.get(id1)
        task2 = await tracker.get(id2)
        assert task1.name == "任务A"
        assert task2.name == "任务B"


@pytest.mark.asyncio
class TestTrackerUpdate:
    """更新任务进度"""

    async def test_update_progress(self, tracker):
        """更新进度数值"""
        task_id = await tracker.create("测试")
        await tracker.update(task_id, progress=50, message="进行中")

        task = await tracker.get(task_id)
        assert task is not None
        assert task.event.progress == 50.0
        assert task.event.message == "进行中"
        assert task.event.status == "pending"  # update 不会自动改 status，需显式传入

    async def test_update_nonexistent_task(self, tracker):
        """更新不存在的任务不报错"""
        await tracker.update("nonexistent", progress=100)  # should not raise

    async def test_update_status_to_completed(self, tracker):
        """标记为 completed"""
        task_id = await tracker.create("测试")
        await tracker.update(task_id, progress=100, status="completed")
        task = await tracker.get(task_id)
        assert task is not None
        assert task.event.status == "completed"
        assert task.event.progress == 100.0

    async def test_update_status_to_failed(self, tracker):
        """标记为 failed"""
        task_id = await tracker.create("测试")
        await tracker.update(task_id, progress=50, status="failed", message="网络超时")
        task = await tracker.get(task_id)
        assert task is not None
        assert task.event.status == "failed"
        assert "网络超时" in task.event.message

    async def test_update_with_result(self, tracker):
        """更新 result"""
        task_id = await tracker.create("测试")
        await tracker.update(task_id, result={"symbols": ["600001"]})
        task = await tracker.get(task_id)
        assert task is not None
        assert task.event.result == {"symbols": ["600001"]}

    async def test_update_completed_items(self, tracker):
        """更新 completed_items"""
        task_id = await tracker.create("测试", total_items=10)
        await tracker.update(task_id, completed_items=5)
        task = await tracker.get(task_id)
        assert task is not None
        assert task.completed_items == 5

    async def test_update_updated_at(self, tracker):
        """每次更新 updated_at 递增"""
        task_id = await tracker.create("测试")
        task = await tracker.get(task_id)
        initial = task.updated_at

        time.sleep(0.01)
        await tracker.update(task_id, progress=10)
        task = await tracker.get(task_id)
        assert task.updated_at > initial


@pytest.mark.asyncio
class TestTrackerGet:
    """获取任务状态"""

    async def test_get_existing(self, tracker):
        """获取存在的任务"""
        task_id = await tracker.create("存在")
        task = await tracker.get(task_id)
        assert task is not None
        assert isinstance(task, ProgressTask)

    async def test_get_nonexistent(self, tracker):
        """获取不存在的任务返回 None"""
        task = await tracker.get("does_not_exist")
        assert task is None


@pytest.mark.asyncio
class TestTrackerListActive:
    """列出活跃任务"""

    async def test_list_active_empty(self, tracker):
        """无活跃任务时返回空列表"""
        active = await tracker.list_active()
        assert active == []

    async def test_list_active_includes_running(self, tracker):
        """running 状态的任务在活跃列表中"""
        task_id = await tracker.create("活跃任务")
        await tracker.update(task_id, progress=30)
        active = await tracker.list_active()
        assert len(active) >= 1
        ids = [t["id"] for t in active]
        assert task_id in ids

    async def test_list_active_excludes_completed(self, tracker):
        """completed 状态不在活跃列表中"""
        task_id = await tracker.create("已完成")
        await tracker.update(task_id, progress=100, status="completed")
        active = await tracker.list_active()
        ids = [t["id"] for t in active]
        assert task_id not in ids

    async def test_list_active_excludes_failed(self, tracker):
        """failed 状态不在活跃列表中"""
        task_id = await tracker.create("失败")
        await tracker.update(task_id, status="failed")
        active = await tracker.list_active()
        ids = [t["id"] for t in active]
        assert task_id not in ids

    async def test_list_active_format(self, tracker):
        """活跃条目包含必要字段"""
        task_id = await tracker.create("格式检查", total_items=20)
        await tracker.update(task_id, progress=25, message="进行中", completed_items=5)
        active = await tracker.list_active()
        entry = next(t for t in active if t["id"] == task_id)
        assert "name" in entry
        assert "status" in entry
        assert "progress" in entry
        assert "message" in entry
        assert "total_items" in entry
        assert "completed_items" in entry
        assert "elapsed_seconds" in entry
        assert entry["name"] == "格式检查"
        assert entry["progress"] == 25.0
        assert entry["status"] == "pending"  # 未显式改 status


@pytest.mark.asyncio
class TestTrackerQueue:
    """SSE 队列推送"""

    async def test_update_pushes_to_queue(self, tracker):
        """update 将事件推送到 queue"""
        task_id = await tracker.create("推送测试")
        task = await tracker.get(task_id)

        await tracker.update(task_id, progress=50, message="处理中")
        event = await asyncio.wait_for(task.queue.get(), timeout=1)
        assert event.progress == 50.0
        assert event.message == "处理中"
        assert event.status == "pending"  # 未显式传 status

    async def test_completed_sends_none_sentinel(self, tracker):
        """completed 状态推送 None 哨兵"""
        task_id = await tracker.create("完成测试")
        task = await tracker.get(task_id)

        await tracker.update(task_id, progress=100, status="completed")

        # 应收到正常事件
        event = await asyncio.wait_for(task.queue.get(), timeout=1)
        assert event.status == "completed"

        # 然后收到 None 哨兵
        sentinel = await asyncio.wait_for(task.queue.get(), timeout=1)
        assert sentinel is None

    async def test_failed_sends_none_sentinel(self, tracker):
        """failed 状态推送 None 哨兵"""
        task_id = await tracker.create("失败测试")
        task = await tracker.get(task_id)

        await tracker.update(task_id, status="failed")
        event = await asyncio.wait_for(task.queue.get(), timeout=1)
        assert event.status == "failed"

        sentinel = await asyncio.wait_for(task.queue.get(), timeout=1)
        assert sentinel is None

    async def test_multiple_updates_queued(self, tracker):
        """多次更新依次入队"""
        task_id = await tracker.create("多次推送")
        task = await tracker.get(task_id)

        await tracker.update(task_id, progress=25)
        await tracker.update(task_id, progress=50)
        await tracker.update(task_id, progress=75)

        e1 = await asyncio.wait_for(task.queue.get(), timeout=1)
        e2 = await asyncio.wait_for(task.queue.get(), timeout=1)
        e3 = await asyncio.wait_for(task.queue.get(), timeout=1)

        assert e1.progress == 25.0
        assert e2.progress == 50.0
        assert e3.progress == 75.0


@pytest.mark.asyncio
class TestTrackerCleanup:
    """清理过期任务"""

    async def test_cleanup_removes_stale_completed(self, tracker):
        """cleanup 移除过期的已完成任务"""
        task_id = await tracker.create("过期任务")
        await tracker.update(task_id, status="completed")

        # 手动把 updated_at 改到很旧
        async with tracker._lock:
            task = tracker._tasks[task_id]
            task.updated_at = time.time() - 3600  # 1小时前

        await tracker.cleanup()

        task = await tracker.get(task_id)
        assert task is None

    async def test_cleanup_preserves_fresh_completed(self, tracker):
        """cleanup 保留未过期的已完成任务"""
        task_id = await tracker.create("新鲜任务")
        await tracker.update(task_id, status="completed")

        # 刚刚更新，没过期
        await tracker.cleanup()

        task = await tracker.get(task_id)
        assert task is not None

    async def test_cleanup_preserves_running(self, tracker):
        """cleanup 不移除 running 任务"""
        task_id = await tracker.create("正在运行")
        await tracker.update(task_id, progress=50)

        # 即使 updated_at 很老，running 任务也不移除
        async with tracker._lock:
            task = tracker._tasks[task_id]
            task.updated_at = time.time() - 3600

        await tracker.cleanup()

        task = await tracker.get(task_id)
        assert task is not None

    async def test_cleanup_empty(self, tracker):
        """空 tracker 调用 cleanup 不报错"""
        await tracker.cleanup()  # should not raise


@pytest.mark.asyncio
class TestTrackerRemove:
    """手动移除任务"""

    async def test_remove_existing(self, tracker):
        """移除存在的任务"""
        task_id = await tracker.create("待移除")
        await tracker.remove(task_id)
        task = await tracker.get(task_id)
        assert task is None

    async def test_remove_nonexistent(self, tracker):
        """移除不存在的任务不报错"""
        await tracker.remove("nonexistent")  # should not raise

    async def test_remove_one_keeps_others(self, tracker):
        """移除一个不影响其他"""
        id1 = await tracker.create("保留")
        id2 = await tracker.create("移除")
        await tracker.remove(id2)

        task1 = await tracker.get(id1)
        assert task1 is not None
        assert task1.name == "保留"

        task2 = await tracker.get(id2)
        assert task2 is None


# ════════════════════════════════════════════
# 全局单例
# ════════════════════════════════════════════


class TestGlobalSingleton:
    """scan_progress 模块级单例"""

    def test_tracker_is_progress_tracker(self):
        """tracker 是 ProgressTracker 实例"""
        from backend.scan_progress import tracker as global_tracker

        assert isinstance(global_tracker, ProgressTracker)
