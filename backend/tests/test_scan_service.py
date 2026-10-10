"""测试 backend/services/scan_service.py — 批量扫描后台任务

覆盖重点：
    - _is_kline_valid 的边界（None / 非 DataFrame / 空 / 行数阈值 20）
    - run_batch_scan 的完整生命周期：进度推送、结果组装、单只失败隔离、全失败仍完成

隔离要点：
    scan_service 使用模块级 `tracker`（backend.scan_progress 的全局单例）。
    直接复用会跨用例累积状态，因此所有用例都用 isolated_tracker 夹具替换为本实例。
    stock_analyzer 的行情/K线/量化打分全部 mock，保证离线可重复。
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from backend.scan_progress import ProgressTracker
from backend.services import scan_service as svc

# ════════════════════════════════════════════════════
# 夹具与辅助
# ════════════════════════════════════════════════════


@pytest.fixture
def isolated_tracker(monkeypatch):
    """替换模块级 tracker 单例，避免测试间状态串扰"""
    tracker = ProgressTracker()
    monkeypatch.setattr(svc, "tracker", tracker)
    return tracker


def _kline_df(rows: int = 30) -> pd.DataFrame:
    """构造一份行数可控的 K 线 DataFrame"""
    return pd.DataFrame(
        {
            "日期": [f"2026-01-{i:02d}" for i in range(1, rows + 1)],
            "开盘": [10.0] * rows,
            "最高": [11.0] * rows,
            "最低": [9.0] * rows,
            "收盘": [10.5] * rows,
            "成交量": [1000] * rows,
        }
    )


def _patch_analyzer_ok(kline=None, quote=None, tech=None, sr=None, qscore=None, funda=None):
    """返回一组“全部成功”的 patch 上下文（可用参数覆盖个别返回值）"""
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(
        patch(
            "stock_analyzer.fetcher.sina_real_time",
            return_value=quote if quote is not None else {"name": "测试股", "最新价": "10"},
        )
    )
    stack.enter_context(
        patch(
            "stock_analyzer.cache.cached_kline",
            return_value=kline if kline is not None else _kline_df(30),
        )
    )
    stack.enter_context(
        patch(
            "stock_analyzer.cache.cached_fundamentals",
            return_value=funda if funda is not None else {},
        )
    )
    stack.enter_context(
        patch("stock_analyzer.analysis.full_technical_analysis", side_effect=lambda df: df)
    )
    stack.enter_context(
        patch(
            "stock_analyzer.analysis.get_technical_summary",
            return_value=tech if tech is not None else {"整体趋势": "上涨"},
        )
    )
    stack.enter_context(
        patch(
            "stock_analyzer.analysis.calc_support_resistance",
            return_value=sr if sr is not None else {"support": 9.0, "resistance": 11.0},
        )
    )
    stack.enter_context(
        patch(
            "stock_analyzer.quant.composite_quant_score",
            return_value=qscore if qscore is not None else {"总分": 88},
        )
    )
    return stack


# ════════════════════════════════════════════════════
# _is_kline_valid
# ════════════════════════════════════════════════════


class TestIsKlineValid:
    def test_none_is_invalid(self):
        assert svc._is_kline_valid(None) is False

    def test_non_dataframe_is_invalid(self):
        assert svc._is_kline_valid([1, 2, 3]) is False

    def test_empty_dataframe_is_invalid(self):
        assert svc._is_kline_valid(pd.DataFrame()) is False

    def test_19_rows_is_invalid(self):
        """边界：19 行不足 20 行"""
        assert svc._is_kline_valid(_kline_df(19)) is False

    def test_20_rows_is_valid(self):
        """边界：恰好 20 行算有效"""
        assert svc._is_kline_valid(_kline_df(20)) is True

    def test_many_rows_is_valid(self):
        assert svc._is_kline_valid(_kline_df(60)) is True


# ════════════════════════════════════════════════════
# run_batch_scan
# ════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestRunBatchScan:
    async def test_happy_path_completes_with_results(self, isolated_tracker):
        task_id = await isolated_tracker.create("批量扫描", total_items=2)

        with _patch_analyzer_ok(funda={"PE_TTM": 12.5}):
            await svc.run_batch_scan(task_id, ["600519", "000001"])

        task = await isolated_tracker.get(task_id)
        assert task.event.status == "completed"
        assert task.event.progress == 100
        assert task.completed_items == 2

        result = task.event.result
        assert result["codes"] == ["600519", "000001"]
        first = result["results"][0]
        assert first["code"] == "600519"
        assert first["name"] == "测试股"
        assert first["pe"] == 12.5
        assert first["trend"] == "上涨"
        assert first["support"] == "9.0"
        assert first["resistance"] == "11.0"
        assert first["score"] == 88
        assert first["error"] is None

    async def test_invalid_kline_marks_insufficient_data(self, isolated_tracker):
        """K 线不足 20 行时，趋势标记为“数据不足”、支撑压力为破折号"""
        task_id = await isolated_tracker.create("t", total_items=1)

        with _patch_analyzer_ok(kline=_kline_df(5)):
            await svc.run_batch_scan(task_id, ["600519"])

        row = (await isolated_tracker.get(task_id)).event.result["results"][0]
        assert row["trend"] == "数据不足"
        assert row["support"] == "—"
        assert row["resistance"] == "—"
        assert row["score"] == "—"
        assert row["error"] is None

    async def test_single_failure_is_isolated(self, isolated_tracker):
        """一只股票行情异常时只记录该条 error，不影响其余股票"""
        kline = _kline_df(30)

        def quote_side(code):
            if code == "600519":
                raise RuntimeError("行情源超时")
            return {"name": "正常股", "最新价": "10"}

        task_id = await isolated_tracker.create("t", total_items=2)
        with (
            _patch_analyzer_ok(kline=kline),
            patch("stock_analyzer.fetcher.sina_real_time", side_effect=quote_side),
        ):
            await svc.run_batch_scan(task_id, ["600519", "000001"])

        results = (await isolated_tracker.get(task_id)).event.result["results"]
        assert results[0]["code"] == "600519"
        assert results[0]["error"] is not None
        assert results[1]["code"] == "000001"
        assert results[1]["error"] is None

    async def test_all_failures_still_mark_completed(self, isolated_tracker):
        """全部失败时任务仍正常收尾（不能让前端 SSE 一直挂起）"""
        task_id = await isolated_tracker.create("t", total_items=2)
        with patch("stock_analyzer.fetcher.sina_real_time", side_effect=RuntimeError("down")):
            await svc.run_batch_scan(task_id, ["600519", "000001"])

        task = await isolated_tracker.get(task_id)
        assert task.event.status == "completed"
        assert all(row["error"] for row in task.event.result["results"])

    async def test_empty_code_list_completes(self, isolated_tracker):
        task_id = await isolated_tracker.create("t", total_items=0)

        await svc.run_batch_scan(task_id, [])

        task = await isolated_tracker.get(task_id)
        assert task.event.status == "completed"
        assert task.event.result["codes"] == []

    async def test_progress_events_pushed_per_code(self, isolated_tracker):
        """推送序列：初始 0% + 每只一次 + 完成 + 终止哨兵"""
        task_id = await isolated_tracker.create("t", total_items=3)

        with _patch_analyzer_ok():
            await svc.run_batch_scan(task_id, ["1", "2", "3"])

        task = await isolated_tracker.get(task_id)
        events = []
        while not task.queue.empty():
            events.append(task.queue.get_nowait())

        assert events[-1] is None  # 终止哨兵
        assert events[0].progress == 0
        assert events[-2].progress == 100
        # 非 None 事件数 = 初始 1 + 3 只 + 完成 1
        assert len([e for e in events if e is not None]) == 5

    async def test_positional_fallback_when_quote_missing_name(self, isolated_tracker):
        """行情返回空字典时用代码兜底作名称"""
        task_id = await isolated_tracker.create("t", total_items=1)

        with _patch_analyzer_ok(quote={}):
            await svc.run_batch_scan(task_id, ["600519"])

        row = (await isolated_tracker.get(task_id)).event.result["results"][0]
        assert row["name"] == "600519"

    async def test_support_resistance_none_falls_back(self, isolated_tracker):
        """calc_support_resistance 返回空时支撑压力回落为破折号"""
        task_id = await isolated_tracker.create("t", total_items=1)

        with (
            _patch_analyzer_ok(),
            patch("stock_analyzer.analysis.calc_support_resistance", return_value=None),
        ):
            await svc.run_batch_scan(task_id, ["600519"])

        row = (await isolated_tracker.get(task_id)).event.result["results"][0]
        assert row["support"] == "—"
        assert row["resistance"] == "—"

    async def test_fundamentals_non_dict_falls_back_to_dash(self, isolated_tracker):
        """基本面返回非 dict 时 PE 回落为破折号"""
        task_id = await isolated_tracker.create("t", total_items=1)

        with (
            _patch_analyzer_ok(),
            patch("stock_analyzer.cache.cached_fundamentals", return_value=MagicMock()),
        ):
            await svc.run_batch_scan(task_id, ["600519"])

        row = (await isolated_tracker.get(task_id)).event.result["results"][0]
        assert row["pe"] == "—"
