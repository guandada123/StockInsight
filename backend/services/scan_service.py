"""批量扫描服务层 — SSE 进度跟踪 + 批量分析

职责:
    - 后台执行批量扫描（带进度推送）
    - 扫描逻辑与路由解耦
"""

import asyncio
import logging
from typing import Any

import pandas as pd

from backend.scan_progress import tracker

logger = logging.getLogger(__name__)


def _is_kline_valid(kline) -> bool:
    """判断 K 线数据是否有效（防御性检查）"""
    if kline is None:
        return False
    if isinstance(kline, pd.DataFrame):
        return not kline.empty and len(kline) >= 20
    return False


async def run_batch_scan(task_id: str, codes: list[str]):
    """后台执行批量扫描并推送进度"""
    # 提前导入（在 asyncio 上下文外加载模块，避免线程池上下文问题）
    from stock_analyzer.analysis import (
        calc_support_resistance,
        full_technical_analysis,
        get_technical_summary,
    )
    from stock_analyzer.cache import cached_fundamentals, cached_kline
    from stock_analyzer.fetcher import sina_real_time
    from stock_analyzer.quant import composite_quant_score

    total = len(codes)
    await tracker.update(
        task_id,
        progress=0,
        message=f"准备扫描 {total} 只股票...",
        status="running",
        completed_items=0,
    )

    results: list[dict[str, Any]] = []
    for i, code in enumerate(codes, 1):
        try:
            quote = await asyncio.to_thread(sina_real_time, code)
            name = quote.get("name", code) if isinstance(quote, dict) and quote else code

            kline = await asyncio.to_thread(cached_kline, code, 120)

            if _is_kline_valid(kline):
                kline = full_technical_analysis(kline)
                tech = get_technical_summary(kline)
                sr = calc_support_resistance(kline)
                support = str(sr.get("support", "—")) if sr else "—"
                resistance = str(sr.get("resistance", "—")) if sr else "—"
            else:
                tech = {"整体趋势": "数据不足"}
                support = resistance = "—"

            funda = await asyncio.to_thread(cached_fundamentals, code)
            pe = funda.get("PE_TTM", "—") if isinstance(funda, dict) and funda else "—"

            qscore = (
                await asyncio.to_thread(composite_quant_score, kline)
                if _is_kline_valid(kline)
                else {}
            )
            score = qscore.get("总分", "—") if isinstance(qscore, dict) and qscore else "—"

            results.append(
                {
                    "code": code,
                    "name": name,
                    "pe": pe,
                    "trend": tech.get("整体趋势", "—"),
                    "support": support,
                    "resistance": resistance,
                    "score": score,
                    "error": None,
                }
            )
        except Exception as e:
            logger.exception("batch_scan_failed: code=%s", code)
            results.append({"code": code, "name": code, "error": str(e)})

        pct = round(i / total * 100, 1)
        await tracker.update(
            task_id,
            progress=pct,
            message=f"[{i}/{total}] {code} {'✅' if results[-1].get('error') is None else '⚠️'}",
            completed_items=i,
        )

    await tracker.update(
        task_id,
        progress=100,
        message=f"扫描完成：{total} 只股票",
        status="completed",
        result={"codes": [r["code"] for r in results], "results": results},
    )
