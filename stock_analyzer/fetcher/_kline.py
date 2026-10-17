"""fetcher _kline 子模块 —— 原样搬移自 __init__.py（2026-10-17 拆分，逻辑零改动）。"""

import functools
import json
import os
import random
import re
import time
from datetime import datetime, timedelta
from enum import Enum

import numpy as np
import pandas as pd
import requests

from ..config import HEADERS
from ..env import get_env
from ..logging_config import get_logger
from ..sectors_fallback import SECTOR_STOCKS_FALLBACK
from ._infra import (
    _get_sina_session,
    _get_tushare_api_url,
    _get_tushare_token,
    _parse_kline_df,
    _retry_request,
    _sina_check_rate,
)

logger = get_logger("fetcher")


def _sina_kline(code, days):
    """新浪财经日K线（加重试）"""
    symbol = f"sh{code}" if code.startswith("6") else f"sz{code}"
    url = (
        "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        f"CN_MarketData.getKLineData?symbol={symbol}&scale=240&datalen={days}"
    )
    _sina_check_rate()
    session = _get_sina_session()
    r = _retry_request("GET", url, max_retries=1, base_delay=0.5, timeout=8, session=session)
    if r is not None and r.status_code == 200 and r.text and r.text != "null":
        try:
            items = json.loads(r.text)
            if items and len(items) > 1:
                rows = [
                    {
                        "日期": it["day"],
                        "开盘": float(it["open"]),
                        "收盘": float(it["close"]),
                        "最高": float(it["high"]),
                        "最低": float(it["low"]),
                        "成交量": float(it.get("volume", 0)),
                        "成交额": float(it.get("amount", 0)) if "amount" in it else 0,
                    }
                    for it in items
                ]
                return _parse_kline_df(rows, days)
        except Exception as e:
            logger.debug("get_kline: sina 源失败 (%s: %s)", type(e).__name__, e)
    return pd.DataFrame()


def _tencent_kline(code, days):
    """腾讯证券日K线（备选，加重试）"""
    symbol = f"sh{code}" if code.startswith("6") else f"sz{code}"
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,120,qfq"
    session = _get_sina_session()  # 复用同一个session
    r = _retry_request("GET", url, max_retries=1, base_delay=0.5, timeout=8, session=session)
    if r is not None and r.status_code == 200:
        try:
            data = r.json()
            klines = data.get("data", {}).get(symbol, {}).get("qfqday", [])
            if klines and len(klines) > 1:
                rows = [
                    {
                        "日期": it[0],
                        "开盘": float(it[1]),
                        "收盘": float(it[2]),
                        "最高": float(it[3]),
                        "最低": float(it[4]),
                        "成交量": float(it[5]),
                    }
                    for it in klines
                ]
                return _parse_kline_df(rows, days)
        except Exception as e:
            logger.debug("get_kline: tencent 源失败 (%s: %s)", type(e).__name__, e)
    return pd.DataFrame()


def _baostock_kline(code, days):
    """Baostock 日K线（第三备选，完全免费+无限流+有复权）

    Baostock 数据延迟约收盘后1-2小时，适合盘后补数据。
    提供前复权数据，质量优于新浪/腾讯的未复权数据。
    """
    try:
        import baostock as bs

        bs.login()

        symbol = f"sh.{code}" if code.startswith("6") else f"sz.{code}"
        end_date = time.strftime("%Y-%m-%d")
        # 多取一些天数以防非交易日
        start_date = (pd.Timestamp.now() - pd.Timedelta(days=days + 60)).strftime("%Y-%m-%d")

        rs = bs.query_history_k_data_plus(
            symbol,
            "date,open,close,high,low,volume,amount",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="2",
        )  # 前复权

        if rs.error_code != "0":
            bs.logout()
            return pd.DataFrame()

        rows = []
        while rs.next():
            row = rs.get_row_data()
            rows.append(
                {
                    "日期": row[0],
                    "开盘": float(row[1]),
                    "收盘": float(row[2]),
                    "最高": float(row[3]),
                    "最低": float(row[4]),
                    "成交量": float(row[5]),
                    "成交额": float(row[6]) if row[6] else 0,
                }
            )
        bs.logout()

        if len(rows) < 20:
            return pd.DataFrame()

        return _parse_kline_df(rows, days)
    except Exception:
        return pd.DataFrame()


def _adata_kline(code, days):
    """AData 日K线（第四备选，整合同花顺+东方财富+百度，免费无需注册）

    AData 内部聚合多个数据源自动切换，稳定性优于单一源。
    """
    try:
        import adata.stock.market as adata_market

        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=days + 60)).strftime("%Y-%m-%d")
        df = adata_market.get_market(stock_code=code, k_type=1, start_date=start, end_date=end)
        if df is None or df.empty or len(df) < 20:
            return pd.DataFrame()

        # AData列名映射到标准列名
        col_map = {
            "trade_date": "日期",
            "open": "开盘",
            "close": "收盘",
            "high": "最高",
            "low": "最低",
            "volume": "成交量",
            "amount": "成交额",
        }
        rows = []
        for _, row in df.iterrows():
            date_val = row.get("trade_date") or row.get("trade_time")
            if date_val is None:
                continue
            rows.append(
                {
                    "日期": str(date_val)[:10],
                    "开盘": float(row.get("open", 0) or 0),
                    "收盘": float(row.get("close", 0) or 0),
                    "最高": float(row.get("high", 0) or 0),
                    "最低": float(row.get("low", 0) or 0),
                    "成交量": float(row.get("volume", 0) or 0),
                    "成交额": float(row.get("amount", 0) or 0),
                }
            )
        if len(rows) < 20:
            return pd.DataFrame()
        return _parse_kline_df(rows, days)
    except Exception:
        return pd.DataFrame()


def _tushare_kline(code, days):
    """TuShare 日K线（第五备选，需注册获取token，支持代理API）

    配置方式：在 .env 文件中设置 TUSHARE_TOKEN 和 TUSHARE_API_URL（代理地址，可选）
    """
    token = _get_tushare_token()
    if not token:
        return pd.DataFrame()

    try:
        import tushare as ts

        ts.set_token(token)
        pro = ts.pro_api()
        api_url = _get_tushare_api_url()
        if api_url:
            pro._DataApi__http_url = api_url

        symbol = f"{code}.{'SH' if code.startswith('6') else 'SZ'}"
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days + 60)).strftime("%Y%m%d")
        df = ts.pro_bar(ts_code=symbol, api=pro, start_date=start, end_date=end)
        if df is None or df.empty or len(df) < 20:
            return pd.DataFrame()
        df = df.sort_values("trade_date")
        rows = [
            {
                "日期": row["trade_date"],
                "开盘": float(row["open"]),
                "收盘": float(row["close"]),
                "最高": float(row["high"]),
                "最低": float(row["low"]),
                "成交量": float(row["vol"]),
                "成交额": float(row.get("amount", 0) or 0),
            }
            for _, row in df.iterrows()
        ]
        return _parse_kline_df(rows, days)
    except Exception:
        return pd.DataFrame()


def _yquoter_kline(code, days):
    """yquoter 日K线（第六备选，统一接口支持A股/港股/美股）

    开源免费，无需注册，Apache 2.0 协议。
    """
    try:
        from yquoter import Stock

        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=days + 60)).strftime("%Y-%m-%d")
        s = Stock("cn", code)
        df = s.get_history(start_date=start, end_date=end)
        if df is None or df.empty or len(df) < 20:
            return pd.DataFrame()
        rows = [
            {
                "日期": str(row["date"])[:10]
                if "date" in row
                else str(row.get("trade_date", ""))[:10],
                "开盘": float(row.get("open", 0) or 0),
                "收盘": float(row.get("close", 0) or 0),
                "最高": float(row.get("high", 0) or 0),
                "最低": float(row.get("low", 0) or 0),
                "成交量": float(row.get("vol", row.get("volume", 0)) or 0),
                "成交额": float(row.get("amount", 0) or 0),
            }
            for _, row in df.iterrows()
        ]
        if len(rows) < 20:
            return pd.DataFrame()
        return _parse_kline_df(rows, days)
    except Exception:
        return pd.DataFrame()


def _tickflow_kline(code, days):
    """TickFlow 日K线（第七备选，免费免注册，盘后数据）

    代码格式转换: 600519 → 600519.SH, 000001 → 000001.SZ
    """
    try:
        if code.startswith("6"):
            symbol = f"{code}.SH"
        elif code.startswith(("0", "3")):
            symbol = f"{code}.SZ"
        else:
            return pd.DataFrame()

        from tickflow import TickFlow

        tf = TickFlow.free()
        df = tf.klines.get(symbol, period="1d", count=days, as_dataframe=True)
        if df is None or df.empty or len(df) < 20:
            return pd.DataFrame()

        # 统一字段名
        rows = []
        for _, row in df.iterrows():
            rows.append(
                {
                    "日期": str(row["trade_date"])[:10],
                    "开盘": round(float(row["open"]), 2),
                    "收盘": round(float(row["close"]), 2),
                    "最高": round(float(row["high"]), 2),
                    "最低": round(float(row["low"]), 2),
                    "成交量": int(row["volume"]),
                    "成交额": round(float(row["amount"]), 2),
                }
            )
        result = pd.DataFrame(rows)
        return result.tail(days) if len(result) > days else result
    except Exception:
        return pd.DataFrame()


def get_kline(code, days=120):
    """获取日K线（七源容灾：网络健康 → DataSourceChain含熔断 → 兜底源）

    优先使用当前最快源，失败或限流时自动切换。
    主链 5 源受熔断器保护（3次失败/5分钟冷却），兜底 2 源无熔断。
    返回 DataFrame，包含 日期/开盘/收盘/最高/最低/成交量/涨跌幅 等标准列。
    """
    # ── 网络健康状态：决定源优先级 ──
    try:
        from ..network_health import get_health

        h = get_health()
        # 离线模式：跳过所有网络源，直接尝试 Baostock
        if h.mode == "offline":
            df = _baostock_kline(code, days)
            return df if not df.empty else pd.DataFrame()
        # 快速模式：优先当前最快源
        if h.mode == "fast" and h.best_kline_source == "tencent":
            df = _tencent_kline(code, days)
            if not df.empty:
                return df
            df = _sina_kline(code, days)
            if not df.empty:
                return df
    except Exception as e:
        logger.debug("get_kline: 健康检测不可用，走默认容灾链 (%s: %s)", type(e).__name__, e)

    # ── DataSourceChain 主容灾链（熔断器保护）──
    # 新浪→腾讯→Baostock→AData→Tushare
    try:
        from stock_analyzer.data_sources import get_default_kline_chain

        chain = get_default_kline_chain()
        df = chain.fetch_kline(code, days)
        if not df.empty:
            return df
    except Exception as e:
        logger.warning(
            "get_kline: Chain 不可用且兜底失败 code=%s (%s: %s)", code, type(e).__name__, e
        )

    # ── 兜底源：yquoter → TickFlow（无熔断，最后防线）──
    df = _yquoter_kline(code, days)
    if not df.empty:
        return df
    return _tickflow_kline(code, days)


def get_intraday_kline(code, scale=60, count=120):
    """获取分钟K线（新浪，60分钟线用于多周期共振）

    scale: 5/15/30/60 (分钟)
    count: 返回条数
    返回 DataFrame（列：日期/开盘/收盘/最高/最低/成交量）或空
    """
    symbol = f"sh{code}" if code.startswith("6") else f"sz{code}"
    url = (
        "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        f"CN_MarketData.getKLineData?symbol={symbol}&scale={scale}&ma=no&datalen={count}"
    )
    session = _get_sina_session()
    r = _retry_request("GET", url, max_retries=1, base_delay=0.3, timeout=5, session=session)
    if r is not None and r.status_code == 200 and r.text and r.text != "null":
        try:
            items = json.loads(r.text)
            if items:
                rows = [
                    {
                        "日期": it["day"],
                        "开盘": float(it["open"]),
                        "收盘": float(it["close"]),
                        "最高": float(it["high"]),
                        "最低": float(it["low"]),
                        "成交量": float(it["volume"]),
                    }
                    for it in items
                ]
                df = pd.DataFrame(rows)
                df["日期"] = pd.to_datetime(df["日期"])
                return df.sort_values("日期").reset_index(drop=True)
        except Exception as e:
            logger.warning(
                "get_intraday_kline: 全部来源失败 code=%s (%s: %s)", code, type(e).__name__, e
            )
    return pd.DataFrame()


def wencai_screen(query, loop=True):
    """同花顺问财自然语言选股

    支持自然语言查询，例如：
      - "主板 市盈率<30 ROE>15% 近20日涨幅<20%"
      - "半导体板块 综合评分最高"
      - "社保基金持股 市值>100亿"

    返回 DataFrame，失败返回空。
    """
    try:
        import pywencai

        df = pywencai.get(query=query, loop=loop)
        return df if df is not None and not df.empty else pd.DataFrame()
    except Exception:
        return pd.DataFrame()
