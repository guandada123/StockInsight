"""大盘/行情/板块 API 路由"""

import logging
import time

from fastapi import APIRouter, Query

from backend.common import _err, _ok

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market", tags=["市场行情"])

# 对外展示的安全错误信息（不泄露内部细节）
_SAFE_ERROR_MSG = "服务暂不可用，请稍后重试"


@router.get("/overview")
async def market_overview():
    """大盘总览 — 四大指数 + 涨跌停统计"""
    t0 = time.time()
    try:
        from stock_analyzer.fetcher import get_market_overview

        market = get_market_overview()
        indices = {}
        idx_map = {
            "000001": "上证指数",
            "399001": "深证成指",
            "399006": "创业板指",
            "000688": "科创50",
        }
        for code, cn_name in idx_map.items():
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
        return _ok(
            {"indices": indices, "update_time": time.strftime("%H:%M:%S")},
            timing=(time.time() - t0) * 1000,
        )
    except Exception:
        logger.exception("market_overview_failed")
        return _err(_SAFE_ERROR_MSG)


@router.get("/indices")
async def indices_detail():
    """四大指数详细数据"""
    t0 = time.time()
    try:
        from stock_analyzer.fetcher import get_market_overview

        market = get_market_overview()
        result = []
        idx_map = {
            "000001": "上证指数",
            "399001": "深证成指",
            "399006": "创业板指",
            "000688": "科创50",
        }
        for code, cn_name in idx_map.items():
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
        return _ok({"indices": result}, timing=(time.time() - t0) * 1000)
    except Exception:
        logger.exception("indices_detail_failed")
        return _err(_SAFE_ERROR_MSG)


@router.get("/quotes")
async def batch_quotes(codes: str = Query(..., description="逗号分隔的股票代码")):
    """批量实时行情"""
    t0 = time.time()
    try:
        from stock_analyzer.fetcher import sina_real_time

        code_list = [c.strip() for c in codes.split(",") if c.strip()]
        if not code_list:
            return _err("请提供股票代码")
        rt = sina_real_time(code_list)
        result = {}
        for code in code_list:
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
        return _ok(result, timing=(time.time() - t0) * 1000)
    except Exception:
        logger.exception("batch_quotes_failed")
        return _err(_SAFE_ERROR_MSG)


@router.get("/limit-up-down")
async def limit_up_down():
    """涨跌停统计"""
    t0 = time.time()
    try:
        import akshare as ak

        df = ak.stock_zt_pool_em(date=None)
        limit_up = len(df[df.get("涨跌幅", 0) >= 9.8]) if not df.empty else 0
        limit_down = len(df[df.get("涨跌幅", -100) <= -9.8]) if not df.empty else 0
        return _ok(
            {
                "limit_up_count": limit_up,
                "limit_down_count": limit_down,
                "ratio": round(limit_up / max(limit_down, 1), 1),
            },
            freshness="cached",
            timing=(time.time() - t0) * 1000,
        )
    except Exception:
        logger.exception("limit_up_down_failed")
        return _err(_SAFE_ERROR_MSG)


@router.get("/sector-rotation")
async def sector_rotation():
    """板块轮动排名"""
    t0 = time.time()
    try:
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
            return _ok(
                {"sectors": result[:30], "total_sectors": len(result)},
                freshness="cached",
                timing=(time.time() - t0) * 1000,
            )
        return _ok({"sectors": [], "total_sectors": 0}, freshness="degraded")
    except Exception:
        logger.exception("sector_rotation_failed")
        return _err(_SAFE_ERROR_MSG)


@router.get("/hot-sectors")
async def hot_sectors(top_n: int = Query(10, description="返回前N个板块")):
    """热门板块（涨跌幅 + 资金流向综合排名）"""
    t0 = time.time()
    try:
        from stock_analyzer.fetcher import get_sector_fund_flow_rank, get_sectors

        sectors = get_sectors()
        fund_rank = get_sector_fund_flow_rank()
        result = []
        ranking = 1
        sector_list = list(sectors.items()) if isinstance(sectors, dict) else []
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
        return _ok(
            {"sectors": result[:top_n]}, freshness="cached", timing=(time.time() - t0) * 1000
        )
    except Exception:
        logger.exception("hot_sectors_failed")
        return _err(_SAFE_ERROR_MSG)
