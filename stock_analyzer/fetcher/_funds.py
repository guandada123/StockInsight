"""fetcher _funds 子模块 —— 原样搬移自 __init__.py（2026-10-17 拆分，逻辑零改动）。"""

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
from ._infra import _circuit_breaker, _circuit_report, _get_em_session, _retry_request

logger = get_logger("fetcher")


def get_fund_flow(code, days=20):
    """获取个股资金流向（push2his 主源 + Tushare 备源 + 快速失败）

    返回 DataFrame：日期/主力净流入-净额/主力净流入-净占比/超大单/大单/中单/小单
    失败返回空 DataFrame。

    v2.3: 新增 Tushare moneyflow 备源（东方财富挂时自动降级）
    v2.2: 减少重试(fail-fast)、加push2当日数据fallback
    v2.0: 改用 push2his fflow/daykline 接口（个股专用）
    """
    import pandas as pd

    # 主源：push2his 历史资金流（5日明细）
    if not _circuit_breaker("fund_flow"):  # 2026-10-17 修复反转：True=可尝试，False 才跳过
        return pd.DataFrame()  # 熔断中，让缓存层兜底
    try:
        market = "1" if code.startswith("6") else "0"
        secid = f"{market}.{code}"
        url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
        params = {
            "lmt": min(days, 250),
            "klt": 101,
            "secid": secid,
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        }
        session = _get_em_session()
        r = _retry_request(
            "GET", url, params=params, max_retries=2, base_delay=0.5, timeout=8, session=session
        )
        _circuit_report("fund_flow", r is not None and r.status_code == 200)
        if r is not None and r.status_code == 200:
            data = r.json()
            if data.get("data") and data["data"].get("klines"):
                records = []
                for line in data["data"]["klines"]:
                    parts = line.split(",")
                    if len(parts) < 7:
                        continue
                    main_net = float(parts[1]) if parts[1] != "-" else 0.0
                    main_pct = float(parts[6]) if len(parts) > 6 and parts[6] != "-" else 0.0
                    super_large = float(parts[5]) if parts[5] != "-" else 0.0
                    large = float(parts[4]) if parts[4] != "-" else 0.0
                    medium = float(parts[3]) if parts[3] != "-" else 0.0
                    small = float(parts[2]) if parts[2] != "-" else 0.0
                    super_large_pct = (
                        float(parts[10]) if len(parts) > 10 and parts[10] != "-" else 0.0
                    )
                    large_pct = float(parts[9]) if len(parts) > 9 and parts[9] != "-" else 0.0
                    medium_pct = float(parts[8]) if len(parts) > 8 and parts[8] != "-" else 0.0
                    small_pct = float(parts[7]) if len(parts) > 7 and parts[7] != "-" else 0.0
                    records.append(
                        {
                            "日期": parts[0],
                            "主力净流入-净额": main_net,
                            "主力净流入-净占比": main_pct,
                            "超大单净流入-净额": super_large,
                            "超大单净流入-净占比": super_large_pct,
                            "大单净流入-净额": large,
                            "大单净流入-净占比": large_pct,
                            "中单净流入-净额": medium,
                            "中单净流入-净占比": medium_pct,
                            "小单净流入-净额": small,
                            "小单净流入-净占比": small_pct,
                        }
                    )
                if records:
                    return pd.DataFrame(records)
    except Exception as e:
        logger.debug("get_fund_flow: 数据源失败 (%s: %s)", type(e).__name__, e)

    # 备源：Tushare moneyflow（东方财富挂时自动降级）
    try:
        from stock_analyzer.tushare_loader import get_moneyflow_cache

        df = get_moneyflow_cache(code, days)
        if df is not None and not df.empty:
            # 格式适配：Tushare net_mf_amount 单位是万元，转为元以与东财一致
            records = []
            for _, row in df.iterrows():
                net_amount = float(row["主力净流入"]) * 10000  # 万元→元
                records.append(
                    {
                        "日期": str(row["日期"]),
                        "主力净流入-净额": net_amount,
                        "主力净流入-净占比": 0,  # Tushare 无占比数据
                        "超大单净流入-净额": float(row["超大单买入"]) - float(row["超大单卖出"]),
                        "大单净流入-净额": float(row["大单买入"]) - float(row["大单卖出"]),
                        "中单净流入-净额": 0,
                        "小单净流入-净额": 0,
                    }
                )
            return pd.DataFrame(records)
    except Exception as e:
        logger.warning("get_fund_flow: 全部来源失败 code=%s (%s: %s)", code, type(e).__name__, e)

    return pd.DataFrame()


def get_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流"):
    """获取板块资金流向排名（东方财富，带重试）

    Parameters
    ----------
    indicator : str — "今日" / "5日" / "10日"
    sector_type : str — "行业资金流" / "概念资金流" / "地域资金流"
    """
    import akshare as ak

    df = ak.stock_sector_fund_flow_rank(indicator=indicator, sector_type=sector_type)
    return df if df is not None and not df.empty else pd.DataFrame()
