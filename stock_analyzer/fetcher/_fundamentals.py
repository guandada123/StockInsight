"""fetcher _fundamentals 子模块 —— 原样搬移自 __init__.py（2026-10-17 拆分，逻辑零改动）。"""

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
from ._infra import _retry_on_failure
from ._quotes import sina_real_time

logger = get_logger("fetcher")


def get_fundamentals(code):
    """获取基本面指标（akshare stock_financial_abstract_ths）

    v5/30: 旧版 stock_a_lg_indicator 已从 akshare 移除。
           改用 financial_abstract_ths，数据更全(含每股净资产可用算PB)。
    """
    result = {
        "市盈率": None,
        "市净率": None,
        "ROE": None,
        "营收增长": None,
        "净利润增长": None,
        "毛利率": None,
        "净利率": None,
        "每股收益": None,
        "每股净资产": None,
    }

    @_retry_on_failure(max_retries=1, base_delay=0.5, label=f"fund_{code}", default=None)
    def _fetch_financial():
        import akshare as ak

        return ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")

    try:
        fin = _fetch_financial()
        if fin is not None and not fin.empty:
            row = fin.tail(1)
            for col in fin.columns:
                val = row[col].values[0]
                if isinstance(val, str):
                    val = val.replace("%", "").replace(",", "")
                try:
                    val = float(val)
                except (ValueError, TypeError):
                    continue
                if "净资产收益率" in col and "摊薄" not in col:
                    result["ROE"] = round(val, 2)
                elif "营业总收入同比增长" in col:
                    result["营收增长"] = round(val, 2)
                elif "净利润同比增长" in col and "扣非" not in col:
                    result["净利润增长"] = round(val, 2)
                elif col == "销售毛利率":
                    result["毛利率"] = round(val, 2)
                elif col == "销售净利率":
                    result["净利率"] = round(val, 2)
                elif col == "基本每股收益":
                    result["每股收益"] = round(val, 4)
                elif col == "每股净资产":
                    result["每股净资产"] = round(val, 4)

        # 用实时价算 PE/PB
        if result["每股收益"] and result["每股收益"] > 0:
            try:
                rt = sina_real_time([code])
                info = rt.get(code, {})
                price = float(info.get("最新价", 0) or 0)
                if price > 0:
                    result["市盈率"] = round(price / result["每股收益"], 2)
                    if result["每股净资产"] and result["每股净资产"] > 0:
                        result["市净率"] = round(price / result["每股净资产"], 2)
            except Exception as e:
                logger.debug("get_fundamentals: 指标派生计算失败 (%s: %s)", type(e).__name__, e)
    except Exception as e:
        logger.warning("get_fundamentals: 全部来源失败 code=%s (%s: %s)", code, type(e).__name__, e)

    return result


def get_national_team_holdings(code):
    """检测国家队持股情况（十大流通股东，带重试）

    扫描十大流通股东名称，识别：证金公司、汇金公司、社保基金、养老金、中金等。
    返回 dict：{"has_national_team": bool, "holders": [名称列表]}
    """
    result = {"has_national_team": False, "holders": []}
    team_keywords = ["中国证券金融", "中央汇金", "全国社保基金", "基本养老保险", "中金", "证金"]

    @_retry_on_failure(max_retries=3, base_delay=2.0, label=f"nt_{code}", default=None)
    def _fetch_holders():
        import akshare as ak

        return ak.stock_circulate_stock_holder(symbol=code)

    try:
        df = _fetch_holders()
        if df is not None and not df.empty:
            name_col = None
            for col in df.columns:
                if "股东名称" in col or "名称" in col or "股东" in col:
                    name_col = col
                    break
            if name_col:
                for name in df[name_col].tolist():
                    for kw in team_keywords:
                        if kw in str(name):
                            result["has_national_team"] = True
                            if name not in result["holders"]:
                                result["holders"].append(name)
                            break
    except Exception as e:
        logger.warning(
            "get_national_team_holdings: 全部来源失败 code=%s (%s: %s)", code, type(e).__name__, e
        )
    return result
