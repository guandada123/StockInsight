"""市场行情服务层 — 大盘指数、涨跌停、板块轮动

职责:
    - 大盘总览 / 指数详情
    - 批量实时行情
    - 涨跌停统计
    - 板块轮动 / 热门板块排名
"""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


# 四大指数映射
_INDEX_MAP = {
    "000001": "上证指数",
    "399001": "深证成指",
    "399006": "创业板指",
    "000688": "科创50",
}


def build_market_overview() -> dict[str, Any]:
    """大盘总览 — 四大指数 + 涨跌停统计"""
    from stock_analyzer.fetcher import get_market_overview

    market = get_market_overview()
    indices = {}
    for code, cn_name in _INDEX_MAP.items():
        info = market.get(code, {})
        price = float(info.get("最新价", 0) or 0)
        prev = float(info.get("昨收", 0) or 0)
        chg = round(price - prev, 2) if prev else 0
        chg_pct = round(chg / prev * 100, 2) if prev else 0
        indices[code] = {
            "name": cn_name,
            "code": code,
            "price": price,
            "change": chg,
            "change_pct": chg_pct,
            "volume": round(float(info.get("成交额", 0) or 0) / 1e8, 2),
        }
    return {"indices": indices, "update_time": time.strftime("%H:%M:%S")}


def build_indices_detail() -> list[dict[str, Any]]:
    """四大指数详细数据"""
    from stock_analyzer.fetcher import get_market_overview

    market = get_market_overview()
    result = []
    for code, cn_name in _INDEX_MAP.items():
        info = market.get(code, {})
        price = float(info.get("最新价", 0) or 0)
        prev = float(info.get("昨收", 0) or 0)
        chg_pct = round((price - prev) / prev * 100, 2) if prev else 0
        result.append(
            {
                "name": cn_name,
                "code": code,
                "price": price,
                "open": float(info.get("今开", 0) or 0),
                "high": float(info.get("最高", 0) or 0),
                "low": float(info.get("最低", 0) or 0),
                "change_pct": chg_pct,
                "volume_yi": round(float(info.get("成交额", 0) or 0) / 1e8, 2),
            }
        )
    return result


def build_batch_quotes(codes: list[str]) -> dict[str, Any]:
    """批量实时行情"""
    from stock_analyzer.fetcher import sina_real_time

    if not codes:
        raise ValueError("请提供股票代码")
    rt = sina_real_time(codes)
    result = {}
    for code in codes:
        info = rt.get(code, {})
        p = float(info.get("最新价", 0) or 0)
        prev = float(info.get("昨收", 0) or 0)
        result[code] = {
            "code": code,
            "name": info.get("名称", code),
            "price": p,
            "open": float(info.get("今开", 0) or 0),
            "high": float(info.get("最高", 0) or 0),
            "low": float(info.get("最低", 0) or 0),
            "prev_close": prev,
            "change": round(p - prev, 2) if prev else 0,
            "change_pct": round((p - prev) / prev * 100, 2) if prev else 0,
            "amplitude": round(float(info.get("振幅", 0) or 0), 2),
            "volume": round(float(info.get("成交量", 0) or 0), 0),
            "turnover": round(float(info.get("换手率", 0) or 0), 2),
        }
    return result


def build_limit_up_down() -> dict[str, Any]:
    """涨跌停统计"""
    import akshare as ak

    df = ak.stock_zt_pool_em(date=None)
    limit_up = len(df[df.get("涨跌幅", 0) >= 9.8]) if not df.empty else 0
    limit_down = len(df[df.get("涨跌幅", -100) <= -9.8]) if not df.empty else 0
    return {
        "limit_up_count": limit_up,
        "limit_down_count": limit_down,
        "ratio": round(limit_up / max(limit_down, 1), 1),
    }


def build_sector_rotation(top_n: int = 30) -> dict[str, Any]:
    """板块轮动排名（按涨跌幅排序）"""
    from stock_analyzer.fetcher import get_sectors

    sectors = get_sectors()
    if isinstance(sectors, dict):
        result = []
        ranking = 1
        for name, info in sorted(
            sectors.items(), key=lambda x: float(x[1].get("涨跌幅", 0) or 0), reverse=True
        ):
            result.append(
                {
                    "name": name,
                    "code": info.get("code", ""),
                    "change_pct": round(float(info.get("涨跌幅", 0) or 0), 2),
                    "fund_flow": round(float(info.get("资金净流入", 0) or 0) / 1e8, 2),
                    "ranking": ranking,
                    "leading_stock": info.get("领涨股", ""),
                }
            )
            ranking += 1
        return {"sectors": result[:top_n], "total_sectors": len(result)}
    return {"sectors": [], "total_sectors": 0}


def build_hot_sectors(top_n: int = 10) -> dict[str, Any]:
    """热门板块（涨跌幅 + 资金流向综合排名）"""
    from stock_analyzer.fetcher import get_sectors

    sectors = get_sectors()
    sector_list = list(sectors.items()) if isinstance(sectors, dict) else []
    result = []
    ranking = 1
    for name, info in sector_list[: top_n * 2]:
        chg = float(info.get("涨跌幅", 0) or 0)
        ff = float(info.get("资金净流入", 0) or 0)
        result.append(
            {
                "name": name,
                "code": info.get("code", ""),
                "change_pct": round(chg, 2),
                "fund_flow_yi": round(ff / 1e8, 2),
                "ranking": ranking,
            }
        )
        ranking += 1
    result.sort(key=lambda x: x["change_pct"], reverse=True)
    for i, r in enumerate(result):
        r["ranking"] = i + 1
    return {"sectors": result[:top_n]}
