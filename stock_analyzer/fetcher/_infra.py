"""fetcher _infra 子模块 —— 原样搬移自 __init__.py（2026-10-17 拆分，逻辑零改动）。"""

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


class Freshness(Enum):
    FRESH = "fresh"  # 实时获取
    CACHED = "cached"  # 缓存命中
    DEGRADED = "degraded"  # 主源失败，备源降级
    STALE = "stale"  # 过期缓存兜底
    UNAVAILABLE = "unavailable"  # 完全不可用


_CIRCUIT_STATE: dict[
    str, dict[str, float | int]
] = {}  # {api_name: {"failures": N, "last_fail": timestamp, "open_until": timestamp}}


def _circuit_breaker(api_name, max_failures=3, cooldown=300):
    """熔断器检查：返回 True 表示可以尝试，False 表示跳过"""
    state = _CIRCUIT_STATE.get(api_name, {})
    now = time.time()
    if state.get("open_until", 0) > now:
        return False  # 熔断中，跳过
    return True


def _circuit_report(api_name, success):
    """报告API调用结果，更新熔断状态"""
    state = _CIRCUIT_STATE.get(api_name, {"failures": 0, "last_fail": 0, "open_until": 0})
    if success:
        state["failures"] = 0  # 成功后重置计数
    else:
        state["failures"] += 1
        state["last_fail"] = time.time()
        if state["failures"] >= 3:
            state["open_until"] = time.time() + 300  # 5分钟熔断
            logger.warning(f"熔断器: {api_name} 连续失败{state['failures']}次，熔断5分钟")
    _CIRCUIT_STATE[api_name] = state


_SESSION_SINA = None


_SESSION_EM = None


def _get_sina_session():
    """新浪财经专用 Session（连接池复用，直连不代理）"""
    global _SESSION_SINA
    if _SESSION_SINA is None:
        _SESSION_SINA = requests.Session()
        _SESSION_SINA.trust_env = False  # 绕过系统代理直连
        _SESSION_SINA.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36",
                "Referer": "http://finance.sina.com.cn",
            }
        )
        adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=30, max_retries=0)
        _SESSION_SINA.mount("http://", adapter)
        _SESSION_SINA.mount("https://", adapter)
    return _SESSION_SINA


def _get_em_session():
    """东方财富专用 Session（直连，不走系统代理）"""
    global _SESSION_EM
    if _SESSION_EM is None:
        _SESSION_EM = requests.Session()
        _SESSION_EM.trust_env = False  # 国内站点直连，不走系统代理
        _SESSION_EM.headers.update(HEADERS)
        adapter = requests.adapters.HTTPAdapter(pool_connections=5, pool_maxsize=15, max_retries=0)
        _SESSION_EM.mount("http://", adapter)
        _SESSION_EM.mount("https://", adapter)
    return _SESSION_EM


RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _is_retryable(exc_or_status):
    """判断是否应该重试：5xx/429/超时/连接错误 → 重试；4xx → 不重试"""
    if isinstance(exc_or_status, int):
        return exc_or_status in RETRYABLE_STATUS or exc_or_status >= 500
    if isinstance(exc_or_status, requests.Timeout):
        return True
    if isinstance(exc_or_status, requests.ConnectionError):
        return True
    return False


def _retry_request(method, url, max_retries=1, base_delay=0.5, timeout=5, session=None, **kwargs):
    """带指数退避+随机抖动的统一重试请求

    退避序列：1s → 2s → 4s → 8s（上限30s）
    随机抖动 ±25% 防止惊群效应
    可重试：5xx / 429 / 超时 / 连接错误
    不可重试：4xx（包括 403/404 等，不重试）

    Returns:
        requests.Response 或 None（全部失败时）
    """
    sess = session or _get_em_session()
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            r = sess.request(method, url, timeout=timeout, **kwargs)
            if r.status_code == 200:
                return r
            if r.status_code == 429:
                # 速率限制：等待更长时间
                retry_after = int(r.headers.get("Retry-After", 30))
                time.sleep(retry_after)
            if not _is_retryable(r.status_code):
                return r  # 4xx 不重试，直接返回
            last_error = f"HTTP {r.status_code}"
        except requests.Timeout as e:
            last_error = f"超时: {e}"
        except requests.ConnectionError as e:
            last_error = f"连接错误: {e}"
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"

        if attempt < max_retries:
            delay = min(base_delay * (2**attempt), 30)
            jitter = delay * 0.25 * (2 * random.random() - 1)  # ±25%
            actual_delay = delay + jitter
            if last_error:
                logger.warning(
                    f"[{method}] {url[:80]} — {last_error}，{actual_delay:.1f}s后重试({attempt + 1}/{max_retries})"
                )
            time.sleep(actual_delay)

    if last_error:
        logger.error(f"[{method}] {url[:80]} — 最终失败: {last_error}")
    return None


_SINA_REQUEST_TIMES: list[float] = []  # 降级模式：记录最近120秒内请求的时间戳


_SINA_RATE_LIMIT = 130  # 安全阈值（实际约150次/120s）


_FILE_RATE_LIMITER = None


def _get_file_rate_limiter():
    """获取文件锁速率限制器（懒加载单例）"""
    global _FILE_RATE_LIMITER
    if _FILE_RATE_LIMITER is None:
        try:
            from stock_analyzer.data_sources import get_sina_rate_limiter

            _FILE_RATE_LIMITER = get_sina_rate_limiter()
        except ImportError:
            return None
    return _FILE_RATE_LIMITER


def _sina_check_rate():
    """检查新浪API速率限制，接近阈值时自动等待冷却

    v2.0: 默认使用跨进程 FileRateLimiter（多进程安全）。
          可通过 RATE_LIMITER_MODE=memory 回退到内存列表。
    """
    # 文件锁模式（默认，多进程安全）
    use_file_lock = get_env("RATE_LIMITER_MODE", "file") != "memory"
    if use_file_lock:
        rl = _get_file_rate_limiter()
        if rl is not None:
            rl.check_and_wait()
            return

    # 降级模式：内存列表（单进程兼容）
    global _SINA_REQUEST_TIMES
    now = time.time()
    _SINA_REQUEST_TIMES = [t for t in _SINA_REQUEST_TIMES if now - t < 120]

    if len(_SINA_REQUEST_TIMES) >= _SINA_RATE_LIMIT:
        oldest = min(_SINA_REQUEST_TIMES)
        wait = 120 - (now - oldest) + 5
        if wait > 0:
            logger.info(f"新浪API速率限制({len(_SINA_REQUEST_TIMES)}次/120s)，等待{wait:.0f}s...")
            time.sleep(wait)
            _SINA_REQUEST_TIMES.clear()

    _SINA_REQUEST_TIMES.append(now)


_NON_RETRYABLE_EXC = (ImportError, ModuleNotFoundError)


def _retry_on_failure(max_retries=1, base_delay=1.0, label="", default=None):
    """装饰器：给网络函数加指数退避重试

    参数:
        default: 全部失败时的默认返回值（None 或 pd.DataFrame() 等）
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            tag = f"[{label}]" if label else ""
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except _NON_RETRYABLE_EXC as e:
                    # 依赖缺失/环境未装：重试 0.5s 不可能变好，短路退出（省 sleep 与日志噪声）
                    logger.error(f"{tag}不可重试错误，放弃: {type(e).__name__}: {e}")
                    return default
                except Exception as e:
                    last_error = e
                    if attempt < max_retries:
                        delay = min(base_delay * (2**attempt), 20)
                        jitter = delay * 0.25 * (2 * random.random() - 1)
                        actual_delay = delay + jitter
                        logger.warning(
                            f"{tag}{type(e).__name__}: {e}，{actual_delay:.1f}s后重试"
                            f"({attempt + 1}/{max_retries})"
                        )
                        time.sleep(actual_delay)
            if last_error:
                # 修复(2026-10-16)：原仅记 type(...).__name__，丢失异常 message，
                # 导致 9.4k 次 AttributeError / 32k 次 ModuleNotFoundError 全部无法定位根因。
                logger.error(f"{tag}最终失败: {type(last_error).__name__}: {last_error}")
            return default

        return wrapper

    return decorator


def _em_request(path, params, max_attempts=5, delay=1.5):
    """东方财富API：多主机+指数退避重试

    优化后：最多3主机×5次=15次尝试（原12×3=36次）
    每次退避：1.5s→3s→6s→12s→24s（上限30s，含±25%抖动）
    """
    hosts = [
        "https://push2.eastmoney.com",
        "https://push2his.eastmoney.com",
        "http://80.push2.eastmoney.com",
    ]
    session = _get_em_session()
    for host in hosts:
        r = _retry_request(
            "GET",
            host + path,
            max_retries=max_attempts,
            base_delay=delay,
            timeout=15,
            session=session,
            params=params,
        )
        if r is not None and r.status_code == 200:
            try:
                return r.json()
            except Exception as e:
                logger.debug("_em_request: 响应 JSON 解析失败 (%s: %s)", type(e).__name__, e)
        time.sleep(0.5)  # 切换主机间隔
    return None


_STOCK_NAME_MAP = None  # 懒加载缓存


def _load_stock_name_map():
    """加载股票代码→名称映射（SQLite缓存30天，首次akshare拉取后永久本地读取）

    v2.0: 加入SQLite永久缓存，避免每次进程启动都调用akshare下载5000+股票列表(16s→0.01s)
    """
    global _STOCK_NAME_MAP
    if _STOCK_NAME_MAP is not None:
        return _STOCK_NAME_MAP

    # 先尝试从SQLite缓存加载
    try:
        from ..cache import cache_get, cache_set

        cached = cache_get("stock_name_map", max_age=2592000)  # 30天TTL
        if cached is not None:
            _STOCK_NAME_MAP = cached
            return _STOCK_NAME_MAP
    except Exception as e:
        logger.debug("_load_stock_name_map: 名称表缓存读取失败 (%s: %s)", type(e).__name__, e)

    # 缓存未命中 → akshare拉取
    _STOCK_NAME_MAP = {}
    try:
        import akshare as ak

        df = ak.stock_info_a_code_name()
        for _, row in df.iterrows():
            code = str(row["code"]).zfill(6)
            _STOCK_NAME_MAP[code] = str(row["name"])
        # 写入SQLite缓存
        try:
            from ..cache import cache_set

            cache_set("stock_name_map", _STOCK_NAME_MAP, ttl=2592000)
        except Exception as e:
            logger.debug("_load_stock_name_map: 名称表缓存写入失败 (%s: %s)", type(e).__name__, e)
    except Exception as e:
        logger.debug("_load_stock_name_map: 名称表构建失败 (%s: %s)", type(e).__name__, e)
    return _STOCK_NAME_MAP


def _correct_stock_name(code, sina_name):
    """纠正新浪API可能错误的股票名称（仅在名称明显异常时修正）"""
    # 跳过空名称和明显正常的名称，避免不必要的查表
    if not sina_name or len(sina_name) >= 4:
        return sina_name
    # 仅当名称异常短(<4字)时才查表修正
    name_map = _load_stock_name_map()
    if code in name_map:
        return name_map[code]
    return sina_name


def _parse_kline_df(rows, days):
    """将 K 线 dict 列表转为标准 DataFrame（含技术指标列）"""
    df = pd.DataFrame(rows)
    df["日期"] = pd.to_datetime(df["日期"])
    df = df.sort_values("日期").reset_index(drop=True)
    df["涨跌幅"] = df["收盘"].pct_change() * 100
    df["涨跌额"] = df["收盘"].diff()
    df["昨收"] = df["收盘"].shift(1)
    df["振幅"] = (df["最高"] - df["最低"]) / df["昨收"].shift(1) * 100
    return df.tail(days).reset_index(drop=True)


def _get_tushare_token():
    """获取 Tushare token（使用统一 env 模块，.env 由 config.py 自动加载）"""
    return get_env("TUSHARE_TOKEN", "")


def _get_tushare_api_url():
    """获取 Tushare API 地址，支持代理"""
    return get_env("TUSHARE_API_URL", "")
