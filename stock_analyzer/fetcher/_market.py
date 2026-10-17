"""fetcher _market 子模块 —— 原样搬移自 __init__.py（2026-10-17 拆分，逻辑零改动）。"""

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

logger = get_logger("fetcher")


def get_limit_up_down(date=None):
    """获取当日涨跌停股票列表

    Returns:
        dict: {up: [{code, name, price, change}], down: [...]}
    """
    try:
        import akshare as ak

        df = ak.stock_zt_pool_em(date=date or datetime.now().strftime("%Y%m%d"))
        if df is None or df.empty:
            return {"up": [], "down": [], "up_count": 0, "down_count": 0}

        up_list, down_list = [], []
        for _, r in df.iterrows():
            code = (
                str(r.get("代码", r.get("code", ""))).zfill(6)
                if "代码" in df.columns or "code" in df.columns
                else ""
            )
            name = r.get("名称", r.get("name", ""))
            change = float(r.get("涨跌幅", r.get("pct_chg", 0)) or 0)
            price = float(r.get("最新价", r.get("close", 0)) or 0)
            if change > 0:
                up_list.append({"code": code, "name": name, "price": price, "change": change})
            elif change < 0:
                down_list.append({"code": code, "name": name, "price": price, "change": change})

        return {
            "up": up_list,
            "down": down_list,
            "up_count": len(up_list),
            "down_count": len(down_list),
        }
    except Exception:
        return {"up": [], "down": [], "up_count": 0, "down_count": 0}


def get_dragon_tiger_board():
    """获取龙虎榜数据（当日上榜个股+买卖席位）

    Returns:
        DataFrame: 上榜股票+净买入额+买入/卖出前五席位
    """
    try:
        import akshare as ak

        df = ak.stock_lhb_detail_em(date=datetime.now().strftime("%Y%m%d"))
        if df is not None and not df.empty:
            return df
    except Exception as e:
        logger.warning("get_dragon_tiger_board: 龙虎榜数据获取失败 (%s: %s)", type(e).__name__, e)
    return pd.DataFrame()
