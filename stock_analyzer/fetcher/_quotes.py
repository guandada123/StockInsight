"""fetcher _quotes 子模块 —— 原样搬移自 __init__.py（2026-10-17 拆分，逻辑零改动）。"""

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
    _circuit_report,
    _correct_stock_name,
    _get_sina_session,
    _retry_request,
    _sina_check_rate,
)

logger = get_logger("fetcher")


def sina_real_time(codes):
    """获取新浪实时行情（加重试+速率限制）

    少量股票(<10只)跳过快率限制，适合盘中快速查询。
    """
    if not codes:
        return {}
    symbols = ",".join(f"{'sh' if c.startswith('6') else 'sz'}{c}" for c in codes)
    if len(codes) > 10:
        _sina_check_rate()  # 大批量才需要限流
    session = _get_sina_session()
    r = _retry_request(
        "GET",
        f"http://hq.sinajs.cn/list={symbols}",
        max_retries=1,
        base_delay=0.3,
        timeout=3,
        session=session,
    )
    success = r is not None and r.status_code == 200
    _circuit_report("sina_real_time", success)
    if not success:
        return {}
    results = {}
    for line in r.text.strip().split("\n"):
        m = re.search(r'hq_str_(\w+)="(.*)"', line)
        if not m:
            continue
        parts = m.group(2).split(",")
        if len(parts) < 32:
            continue
        code = m.group(1)[2:]
        price = float(parts[3]) if parts[3] else 0
        yclose = float(parts[2]) if parts[2] else 0
        results[code] = {
            "代码": code,
            "名称": _correct_stock_name(code, parts[0]),
            "最新价": price,
            "涨跌幅": round((price - yclose) / yclose * 100, 2) if yclose else 0,
            "涨跌额": round(price - yclose, 2),
            "今开": float(parts[1]) if parts[1] else 0,
            "昨收": yclose,
            "最高": float(parts[4]) if parts[4] else 0,
            "最低": float(parts[5]) if parts[5] else 0,
            "成交量": float(parts[8]) if parts[8] else 0,
            "成交额": float(parts[9]) if parts[9] else 0,
        }
    return results


def tencent_real_time(codes):
    """获取腾讯实时行情（2026-11-22 新增，作为新浪的优先源）

    腾讯 qt.gtimg.cn 目前比新浪稳：新浪对 Referer 敏感且有频率限制，
    腾讯无此约束，返回同样字段。实测 sh600519 返回 88 个 ~ 分隔字段。

    字段索引（0 起）：1 名称 / 2 代码 / 3 最新价 / 4 昨收 / 5 今开 /
    32 涨跌幅 / 33 最高 / 34 最低 / 37 成交额(万元)
    """
    if not codes:
        return {}
    symbols = ",".join(f"{'sh' if c.startswith('6') else 'sz'}{c}" for c in codes)
    r = _retry_request(
        "GET",
        f"https://qt.gtimg.cn/q={symbols}",
        max_retries=1,
        base_delay=0.3,
        timeout=8,
    )
    success = r is not None and r.status_code == 200
    _circuit_report("tencent_real_time", success)
    if not success:
        return {}

    r.encoding = "gbk"
    results = {}
    for line in r.text.strip().split("\n"):
        m = re.search(r'v_(\w+)="(.*)"', line)
        if not m:
            continue
        parts = m.group(2).split("~")
        if len(parts) < 38:
            continue
        code = parts[2]
        try:
            price = float(parts[3] or 0)
            yclose = float(parts[4] or 0)
        except ValueError:
            continue
        if price <= 0:
            continue
        results[code] = {
            "代码": code,
            "名称": _correct_stock_name(code, parts[1]),
            "最新价": price,
            "涨跌幅": round((price - yclose) / yclose * 100, 2) if yclose else 0,
            "涨跌额": round(price - yclose, 2),
            "今开": float(parts[5] or 0),
            "昨收": yclose,
            "最高": float(parts[33] or 0),
            "最低": float(parts[34] or 0),
            "成交量": float(parts[6] or 0),
            "成交额": float(parts[37] or 0) * 10000,  # 万元 → 元，对齐新浪口径
        }
    return results


def get_real_time(codes):
    """实时行情统一入口：腾讯优先，新浪兜底（2026-11-22 新增）

    东财已不可用，行情主链路改为「腾讯 → 新浪」双源降级。
    返回结构与原 sina_real_time 一致，调用方无需感知切换。
    """
    rt = tencent_real_time(codes)
    if len(rt) >= max(1, len(codes) // 2):
        return rt
    logger.warning("get_real_time: 腾讯源返回不足（%d/%d），降级到新浪", len(rt), len(codes))
    return sina_real_time(codes)


def get_market_overview():
    """获取大盘指数行情（加重试）

    用新浪实时行情获取主要指数：
    上证综指(000001)、深证成指(399001)、创业板指(399006)、科创50(000688)
    返回 dict：指数代码 → {名称, 最新价, 涨跌幅, 涨跌额, 成交额}
    """
    index_symbols = {
        "sh000001": "000001",
        "sz399001": "399001",
        "sz399006": "399006",
        "sh000688": "000688",
    }
    _sina_check_rate()
    session = _get_sina_session()
    url = "http://hq.sinajs.cn/list=" + ",".join(index_symbols.keys())
    r = _retry_request("GET", url, max_retries=2, base_delay=1.0, timeout=10, session=session)
    if r is None or r.status_code != 200:
        return {}
    results = {}
    for line in r.text.strip().split("\n"):
        m = re.search(r'hq_str_(\w+)="(.*)"', line)
        if not m:
            continue
        parts = m.group(2).split(",")
        if len(parts) < 32:
            continue
        raw_code = m.group(1)
        code = index_symbols.get(raw_code, raw_code[2:])
        price = float(parts[3]) if parts[3] else 0
        yclose = float(parts[2]) if parts[2] else 0
        results[code] = {
            "代码": code,
            "名称": parts[0],
            "最新价": price,
            "涨跌幅": round((price - yclose) / yclose * 100, 2) if yclose else 0,
            "涨跌额": round(price - yclose, 2),
            "今开": float(parts[1]) if parts[1] else 0,
            "昨收": yclose,
            "最高": float(parts[4]) if parts[4] else 0,
            "最低": float(parts[5]) if parts[5] else 0,
        }
    return results
