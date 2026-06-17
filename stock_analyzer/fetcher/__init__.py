"""数据获取模块
- 新浪财经：K线历史、实时行情（稳定，~150次/120s限流）
- 腾讯证券：K线备选（不限流）
- 东方财富：板块列表、成分股（HTTPS代理间歇性，多重重试+HTTP备线）
- Baostock：K线第三备选（完全免费、无需注册、不限流、有复权）
- akshare：基本面、资金流向

网络层优化（2026-05-26）：
  - 统一指数退避重试 + 随机抖动
  - requests.Session 连接池复用
  - 新浪速率限制主动跟踪
  - K线三源容灾（新浪→腾讯→Baostock）
"""

# ── API 容灾层：数据新鲜度标记 + 熔断器 ──
from enum import Enum


class Freshness(Enum):
    FRESH = "fresh"  # 实时获取
    CACHED = "cached"  # 缓存命中
    DEGRADED = "degraded"  # 主源失败，备源降级
    STALE = "stale"  # 过期缓存兜底
    UNAVAILABLE = "unavailable"  # 完全不可用


# 熔断器：连续失败 N 次后，M 秒内跳过该 API
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


def get_freshness_label(data, tag):
    """给数据打新鲜度标签"""
    if isinstance(data, dict):
        data["_freshness"] = tag.value if isinstance(tag, Freshness) else tag
    return data


# ── 延迟预热（首次调用 25s → 预热后 0.02s）──
_SESSION_WARMED = False


def _ensure_warmup():
    """预热 requests Session + 连接池，避免首次调用卡 25 秒"""
    global _SESSION_WARMED
    if _SESSION_WARMED:
        return
    try:
        _get_sina_session().get("http://hq.sinajs.cn/list=sz000001", timeout=3)
    except Exception:
        pass
    _SESSION_WARMED = True


import functools
import json
import os
import random
import re
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests

from ..logging_config import get_logger

logger = get_logger("fetcher")

from ..config import HEADERS
from ..env import get_env
from ..sectors_fallback import SECTOR_STOCKS_FALLBACK

# ═══════════════════════════════════════════════════════════════
# 网络层基础设施
# ═══════════════════════════════════════════════════════════════

# 连接池复用 — 避免每次请求新建 TCP 连接
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


# ── 统一重试机制 ──────────────────────────────────

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


# ── 新浪速率限制跟踪 ──────────────────────────────
#
# v2.0: 支持两种模式：
#   - 默认：跨进程 FileRateLimiter（fcntl 文件锁，多进程安全）
#   - 降级：内存列表（单进程可用，向后兼容）
#
# 通过环境变量 RATE_LIMITER_MODE 切换：
#   export RATE_LIMITER_MODE=file     # 文件锁（新，推荐）
#   export RATE_LIMITER_MODE=memory   # 内存列表（旧，兼容）

_SINA_REQUEST_TIMES: list[float] = []  # 降级模式：记录最近120秒内请求的时间戳
_SINA_RATE_LIMIT = 130  # 安全阈值（实际约150次/120s）
_SINA_COOLDOWN = 120  # 冷却时间（秒）

# 文件锁速率限制器（懒加载）
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


# ── 通用重试装饰器（给 akshare 调用用）────────────


def _retry_on_failure(max_retries=1, base_delay=1.0, label="", default=None):
    """装饰器：给网络函数加指数退避重试

    参数:
        default: 全部失败时的默认返回值（None 或 pd.DataFrame() 等）
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries:
                        delay = min(base_delay * (2**attempt), 20)
                        jitter = delay * 0.25 * (2 * random.random() - 1)
                        actual_delay = delay + jitter
                        tag = f"[{label}]" if label else ""
                        logger.warning(
                            f"{tag}{type(e).__name__}，{actual_delay:.1f}s后重试({attempt + 1}/{max_retries})"
                        )
                        time.sleep(actual_delay)
            if last_error:
                tag = f"[{label}]" if label else ""
                logger.error(f"{tag}最终失败: {type(last_error).__name__}")
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
            except Exception:
                pass
        time.sleep(0.5)  # 切换主机间隔
    return None


# ── 新浪实时行情 ────────────────────────────────

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
        from .cache import cache_get, cache_set

        cached = cache_get("stock_name_map", max_age=2592000)  # 30天TTL
        if cached is not None:
            _STOCK_NAME_MAP = cached
            return _STOCK_NAME_MAP
    except Exception:
        pass

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
            from .cache import cache_set

            cache_set("stock_name_map", _STOCK_NAME_MAP, ttl=2592000)
        except Exception:
            pass
    except Exception:
        pass
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


# ── K线数据（新浪） ─────────────────────────────


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
        except Exception:
            pass
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
        except Exception:
            pass
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


def _get_tushare_token():
    """获取 Tushare token（使用统一 env 模块，.env 由 config.py 自动加载）"""
    return get_env("TUSHARE_TOKEN", "")


def _get_tushare_api_url():
    """获取 Tushare API 地址，支持代理"""
    return get_env("TUSHARE_API_URL", "")


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
        except Exception:
            pass
    return pd.DataFrame()


def _tickflow_kline(code, days):
    """TickFlow 日K线（第七备选，免费免注册，盘后数据）

    代码格式转换: 600519 → 600519.SH, 000001 → 000001.SZ
    """
    try:
        if code.startswith("6"):
            symbol = f"{code}.SH"
        elif code.startswith("0") or code.startswith("3"):
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
        from .network_health import get_health

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
    except Exception:
        pass  # 健康检测不可用，走默认容灾链

    # ── DataSourceChain 主容灾链（熔断器保护）──
    # 新浪→腾讯→Baostock→AData→Tushare
    try:
        from stock_analyzer.data_sources import get_default_kline_chain

        chain = get_default_kline_chain()
        df = chain.fetch_kline(code, days)
        if not df.empty:
            return df
    except Exception:
        pass  # Chain 不可用，走兜底

    # ── 兜底源：yquoter → TickFlow（无熔断，最后防线）──
    df = _yquoter_kline(code, days)
    if not df.empty:
        return df
    return _tickflow_kline(code, days)


# ── 板块数据（东方财富，多重重试+静态兜底）────


def get_sectors():
    """获取行业板块列表"""
    data = _em_request(
        "/api/qt/clist/get",
        {
            "pn": 1,
            "pz": 200,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "m:90+t:2",
            "fields": "f2,f3,f4,f12,f14,f20,f104,f105,f128",
        },
        max_attempts=3,
        delay=1.0,
    )
    if data and data.get("data"):
        rows = []
        for item in data["data"].get("diff", []):
            rows.append(
                {
                    "板块代码": item.get("f12"),
                    "板块名称": item.get("f14"),
                    "涨跌幅": item.get("f3") or 0,
                    "上涨家数": item.get("f104") or 0,
                    "下跌家数": item.get("f105") or 0,
                    "总成交额": item.get("f20") or 0,
                }
            )
        df = pd.DataFrame(rows)
        return df[df["板块名称"].notna()].reset_index(drop=True)

    # 兜底：用静态板块列表（从Sina实时行情计算涨跌幅）
    return get_sectors_fallback()


def get_sectors_fallback():
    """兜底：静态板块映射 + 新浪实时行情"""
    rows = []
    for sec_name, info in SECTOR_STOCKS_FALLBACK.items():
        stocks = info["成分股"]
        rt = sina_real_time(stocks)
        changes = [rt[c]["涨跌幅"] for c in stocks if c in rt and rt[c]["涨跌幅"] is not None]
        if not changes:
            continue
        up = sum(1 for c in changes if c > 0)
        down = sum(1 for c in changes if c < 0)
        rows.append(
            {
                "板块代码": f"BK{abs(hash(sec_name)) % 10000:04d}",
                "板块名称": sec_name,
                "涨跌幅": round(float(np.mean(changes)), 2),
                "上涨家数": up,
                "下跌家数": down,
                "总成交额": sum(rt[c]["成交额"] for c in stocks if c in rt),
            }
        )
    if rows:
        df = pd.DataFrame(rows)
        return df.sort_values("涨跌幅", ascending=False).reset_index(drop=True)
    return pd.DataFrame()


def get_sector_stocks(sector_code):
    """获取板块成分股"""
    # 先试东方财富
    data = _em_request(
        "/api/qt/clist/get",
        {
            "pn": 1,
            "pz": 200,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": f"b:{sector_code}",
            "fields": "f2,f3,f12,f14,f20",
        },
        max_attempts=3,
        delay=1.0,
    )
    if data and data.get("data"):
        rows = []
        for item in data["data"].get("diff", []):
            name = item.get("f14", "")
            if "ST" in name or "退市" in name:
                continue
            rows.append({"代码": item.get("f12", ""), "名称": name, "涨跌幅": item.get("f3") or 0})
        if rows:
            return pd.DataFrame(rows)

    # 兜底：从静态映射找
    for sec_name_internal, info in SECTOR_STOCKS_FALLBACK.items():
        target = f"BK{abs(hash(sec_name_internal)) % 10000:04d}"
        if target == sector_code:
            stocks = info["成分股"]
            rt = sina_real_time(stocks)
            rows = []
            for c in stocks:
                if c in rt:
                    rows.append({"代码": c, "名称": rt[c]["名称"], "涨跌幅": rt[c]["涨跌幅"]})
            return pd.DataFrame(rows)

    return pd.DataFrame()


# ── 基本面（akshare） ────────────────────────────


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
            except Exception:
                pass
    except Exception:
        pass

    return result


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
    if _circuit_breaker("fund_flow"):
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
    except Exception:
        pass

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
    except Exception:
        pass

    return pd.DataFrame()


@_retry_on_failure(max_retries=3, base_delay=2.0, label="sector_fund_flow", default=pd.DataFrame())
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
    except Exception:
        pass
    return result


# ── 精选逻辑 ─────────────────────────────────────


def get_top_sector_stocks(sectors_df, top_n=3):
    """从TOP板块中精选个股"""
    from .analysis import score_stocks_in_sector

    top3 = sectors_df.head(top_n)
    all_picks = []

    for _, sec_row in top3.iterrows():
        sec_code = sec_row["板块代码"]
        sec_name = sec_row["板块名称"]
        stocks = get_sector_stocks(sec_code)
        if stocks.empty:
            print(f"  {sec_name}: 无成分股数据")
            continue

        # 用新浪实时行情补充量比、振幅
        codes = stocks["代码"].tolist()
        rt = sina_real_time(codes)
        if rt:
            rt_df = pd.DataFrame.from_dict(rt, orient="index")
            stocks = stocks.merge(
                rt_df[["代码", "最新价", "成交额", "今开", "昨收", "最高", "最低"]],
                on="代码",
                how="left",
            )
        else:
            stocks["最新价"] = 0
            stocks["最高"] = 0
            stocks["最低"] = 0
            stocks["昨收"] = 0
            stocks["成交额"] = 0

        stocks = stocks[stocks["涨跌幅"].notna()].copy()
        if stocks.empty:
            continue

        stocks["振幅"] = (
            (stocks["最高"] - stocks["最低"]) / stocks["昨收"].replace(0, np.nan) * 100
        ).fillna(0)
        mean_amount = stocks["成交额"].mean()
        stocks["量比"] = (stocks["成交额"] / (mean_amount + 1)).fillna(1)

        scored = score_stocks_in_sector(stocks)
        for _, stk in scored.head(2).iterrows():
            all_picks.append(
                {
                    "代码": stk["代码"],
                    "名称": stk["名称"],
                    "板块": sec_name,
                    "最新价": stk.get("最新价", None),
                    "涨跌幅": stk["涨跌幅"],
                    "量比": stk.get("量比", 1),
                    "振幅": stk.get("振幅", 0),
                    "个股评分": stk["个股评分"],
                }
            )
        time.sleep(0.3)

    if all_picks:
        df = pd.DataFrame(all_picks)
        return df.drop_duplicates(subset=["代码"])
    return pd.DataFrame()


# ── 新闻与消息数据 ──────────────────────────────


@_retry_on_failure(max_retries=3, base_delay=2.0, label="stock_news", default=pd.DataFrame())
def get_stock_news(code):
    """获取个股新闻（东方财富，带重试）

    使用 akshare 获取最近 100 条个股新闻。
    返回 DataFrame，包含：标题、内容、时间、来源、关键词。
    失败时返回空 DataFrame。
    """
    import akshare as ak

    try:
        df = ak.stock_news_em(symbol=code)
    except Exception:
        return pd.DataFrame()
    if df is not None and not df.empty:
        # 新版akshare列名: 关键词/新闻标题/新闻内容/发布时间/文章来源
        col_map = {}
        if "新闻标题" in df.columns:
            col_map["新闻标题"] = "标题"
        if "新闻内容" in df.columns:
            col_map["新闻内容"] = "内容"
        elif "内容摘要" in df.columns:
            col_map["内容摘要"] = "内容"
        if "发布时间" in df.columns:
            col_map["发布时间"] = "时间"
        if "文章来源" in df.columns:
            col_map["文章来源"] = "来源"
        if "关键词" in df.columns:
            col_map["关键词"] = "关键词"
        df = df.rename(columns=col_map)
        keep_cols = [c for c in ["标题", "内容", "时间", "来源", "关键词"] if c in df.columns]
        return df[keep_cols]
    return pd.DataFrame()


@_retry_on_failure(max_retries=2, base_delay=2.0, label="market_news", default=pd.DataFrame())
def get_market_news():
    """获取全市场财经要闻（财新/东方财富，带重试）

    返回 DataFrame，包含：标签(市场动态/公司要闻等)、摘要、URL。
    可用于判断当日市场情绪和重大事件。
    """
    import akshare as ak

    df = ak.stock_news_main_cx()
    if df is not None and not df.empty:
        col_map = {}
        if "tag" in df.columns:
            col_map["tag"] = "标签"
        if "summary" in df.columns:
            col_map["summary"] = "摘要"
        if "url" in df.columns:
            col_map["url"] = "链接"
        return df.rename(columns=col_map)
    return pd.DataFrame()


def analyze_news_sentiment(news_df, stock_name=""):
    """分析新闻情感倾向

    基于关键词+情感词典，对新闻标题和内容进行情感评分。
    返回: {sentiment_score: 0-100, direction: 'positive'/'neutral'/'negative',
            key_events: [事件关键词列表], risk_alert: bool}
    """
    if news_df is None or news_df.empty:
        return {
            "sentiment_score": 50,
            "direction": "neutral",
            "key_events": [],
            "risk_alert": False,
        }

    title_col = (
        "标题"
        if "标题" in news_df.columns
        else ("新闻标题" if "新闻标题" in news_df.columns else None)
    )
    content_col = (
        "内容"
        if "内容" in news_df.columns
        else ("新闻内容" if "新闻内容" in news_df.columns else None)
    )

    # 情感词典
    positive_words = [
        "利好",
        "大涨",
        "突破",
        "增长",
        "盈利",
        "分红",
        "回购",
        "创新高",
        "买入",
        "增持",
        "涨停",
        "中标",
        "合同",
        "扭亏",
        "超预期",
        "扩产",
        "订单",
        "政策支持",
        "国产替代",
        "放量",
    ]
    negative_words = [
        "利空",
        "大跌",
        "亏损",
        "减持",
        "风险",
        "处罚",
        "诉讼",
        "退市",
        "下调",
        "跌停",
        "违约",
        "调查",
        "破产",
        "ST",
        "警示",
        "问责",
        "制裁",
        "关税",
        "限售",
        "暴雷",
    ]
    event_keywords = [
        "政策",
        "关税",
        "制裁",
        "重组",
        "并购",
        "定增",
        "业绩",
        "分红",
        "回购",
        "减持",
        "解禁",
        "立案",
        "停牌",
        "复牌",
        "涨停",
        "跌停",
        "龙虎榜",
        "大宗交易",
    ]

    all_text = ""
    if title_col:
        titles = news_df[title_col].head(20).tolist()
        all_text += " ".join(str(t) for t in titles)
    if content_col:
        contents = news_df[content_col].head(10).tolist()
        all_text += " " + " ".join(str(c)[:200] for c in contents)

    pos_count = sum(1 for w in positive_words if w in all_text)
    neg_count = sum(1 for w in negative_words if w in all_text)
    events_found = [w for w in event_keywords if w in all_text]

    if pos_count + neg_count == 0:
        score = 50
        direction = "neutral"
    else:
        ratio = pos_count / (pos_count + neg_count)
        score = 50 + (ratio - 0.5) * 80  # 10-90范围
        score = max(10, min(90, score))
        if ratio > 0.6:
            direction = "positive"
        elif ratio < 0.4:
            direction = "negative"
        else:
            direction = "neutral"

    return {
        "sentiment_score": round(score, 1),
        "direction": direction,
        "key_events": events_found[:5],
        "risk_alert": direction == "negative" and len(events_found) > 0,
        "positive_hits": pos_count,
        "negative_hits": neg_count,
    }


def get_market_news_digest():
    """获取当日市场消息摘要（板块级+市场级）

    返回: {summary: 一句话总结, hot_sectors: [热门板块],
            key_events: [重大事件], sentiment: '偏多'/'偏空'/'中性'}
    """
    news = get_market_news()
    if news.empty:
        return {"summary": "暂无市场要闻", "hot_sectors": [], "key_events": [], "sentiment": "中性"}

    # 按标签分类
    tags = news["标签"].value_counts().head(5).to_dict() if "标签" in news.columns else {}

    # 提取板块关键词
    sector_keywords = [
        "半导体",
        "新能源",
        "医药",
        "消费",
        "金融",
        "地产",
        "汽车",
        "AI",
        "算力",
        "光伏",
        "锂电",
        "军工",
        "有色",
        "化工",
        "电力",
        "基建",
        "通信",
        "传媒",
        "农业",
    ]
    all_summaries = " ".join(news["摘要"].head(30).tolist()) if "摘要" in news.columns else ""
    hot_sectors = [s for s in sector_keywords if s in all_summaries]

    # 情感判断
    pos_words_in_news = ["上涨", "大涨", "利好", "突破", "增长", "政策支持", "回暖"]
    neg_words_in_news = ["下跌", "大跌", "利空", "风险", "制裁", "关税", "调整"]
    pos = sum(1 for w in pos_words_in_news if w in all_summaries)
    neg = sum(1 for w in neg_words_in_news if w in all_summaries)

    if pos > neg * 1.5:
        sentiment = "偏多"
    elif neg > pos * 1.5:
        sentiment = "偏空"
    else:
        sentiment = "中性"

    # 生成一句话总结
    tag_str = "、".join(list(tags.keys())[:3])
    sector_str = "、".join(hot_sectors[:4]) if hot_sectors else "无突出板块"
    summary = f"今日要闻聚焦{tag_str}；热门板块：{sector_str}；市场情绪{sentiment}"

    return {
        "summary": summary,
        "hot_sectors": hot_sectors[:5],
        "key_tags": tags,
        "sentiment": sentiment,
        "news_count": len(news),
    }


@_retry_on_failure(max_retries=3, base_delay=2.0, label="weibo", default=pd.DataFrame())
def get_weibo_sentiment():
    """获取微博舆情评分（金十数据，带重试）

    返回 DataFrame：股票名称 → 情绪评分（-1 到 +1，正数正面）。
    """
    import akshare as ak

    df = ak.stock_js_weibo_report(time_period="CNHOUR24")
    return df if df is not None and not df.empty else pd.DataFrame()


@_retry_on_failure(max_retries=3, base_delay=2.0, label="research", default=pd.DataFrame())
def get_stock_research(code):
    """获取券商研报与盈利预测（东方财富，带重试）"""
    import akshare as ak

    df = ak.stock_research_report_em(symbol=code)
    if df is not None and not df.empty:
        cols = {"研究报告标题": "研报标题", "评级": "评级", "机构": "券商", "行业": "行业"}
        for c in df.columns:
            if "盈利预测" in c:
                cols[c] = c
        return df[[c for c in cols if c in df.columns]].rename(columns=cols)
    return pd.DataFrame()


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
    except Exception:
        pass
    return pd.DataFrame()


def calc_relative_strength(code, index_code="000001", days=60):
    """计算个股相对大盘的强弱（RS线）

    相对强弱 = (个股累计涨幅 - 大盘累计涨幅)，正值=跑赢大盘。

    Returns:
        dict: {rs_value: float, stock_return: float, index_return: float,
               trend: '跑赢大盘'/'跑输大盘'/'持平'}
    """
    try:
        # 延迟导入避免循环依赖（cache 会 import fetcher）
        from .cache import cached_kline as _ck

        stock_kline = _ck(code, days=days)
        if stock_kline.empty or len(stock_kline) < days * 0.8:
            return {"rs_value": 0, "stock_return": 0, "index_return": 0, "trend": "数据不足"}

        stock_ret = (stock_kline.iloc[-1]["收盘"] / stock_kline.iloc[0]["收盘"] - 1) * 100

        # 用指数K线计算真实区间回报（不再用单日涨跌×倍数估算）
        try:
            prefix = "sh" if index_code.startswith(("0", "6")) else "sz"
            idx_kline = (
                _ck(f"{prefix}{index_code}", days=days)
                if index_code != "000688"
                else _ck("sh000688", days=days)
            )
        except Exception:
            idx_kline = pd.DataFrame()
        if not idx_kline.empty and len(idx_kline) >= days * 0.8:
            idx_ret = (idx_kline.iloc[-1]["收盘"] / idx_kline.iloc[0]["收盘"] - 1) * 100
        else:
            # K线不可用时用当日涨跌幅兜底
            index_data = get_market_overview()
            idx_info = index_data.get(index_code, {})
            idx_ret = idx_info.get("涨跌幅", 0)

        rs = stock_ret - idx_ret
        if rs > 5:
            trend = "跑赢大盘"
        elif rs < -5:
            trend = "跑输大盘"
        else:
            trend = "持平"

        return {
            "rs_value": round(rs, 1),
            "stock_return": round(stock_ret, 1),
            "index_return": round(idx_ret, 1),
            "trend": trend,
        }
    except Exception:
        return {"rs_value": 0, "stock_return": 0, "index_return": 0, "trend": "计算失败"}


def get_sector_rotation(days=5):
    """分析板块轮动：对比近N天板块排名变化

    从历史评分库中提取板块均分变化，识别走强和走弱的板块。

    Returns:
        dict: {strengthening: [{name, score_change}],
               weakening: [{name, score_change}],
               top5_now: [{name, avg_score}]}
    """
    try:
        import pandas as pd

        from .history_db import get_market_summary
        from .sectors_fallback import get_sector_for_code

        # 从全市场扫描结果中统计板块均分
        if not os.path.exists("full_scan_results.csv"):
            return {
                "strengthening": [],
                "weakening": [],
                "top5_now": [],
                "message": "暂无全市场扫描数据",
            }

        df = pd.read_csv("full_scan_results.csv")
        df["code_str"] = df["代码"].astype(str).str.zfill(6)
        df["sector"] = df["code_str"].apply(get_sector_for_code)

        sector_scores = df.groupby("sector")["综合评分"].agg(["mean", "count"]).reset_index()
        sector_scores = sector_scores[sector_scores["count"] >= 3]  # 至少3只股票
        sector_scores = sector_scores.sort_values("mean", ascending=False)

        top5 = [
            {"name": r["sector"], "avg_score": round(r["mean"], 1)}
            for _, r in sector_scores.head(5).iterrows()
        ]

        return {
            "strengthening": [],  # 需要多天数据对比，初次运行只有一天
            "weakening": [],
            "top5_now": top5,
            "total_sectors": len(sector_scores),
            "message": f"共{len(sector_scores)}个板块，均分最高: {top5[0]['name'] if top5 else '无'}",
        }
    except Exception as e:
        return {
            "strengthening": [],
            "weakening": [],
            "top5_now": [],
            "message": f"板块分析失败: {e}",
        }


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
