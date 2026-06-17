"""数据源抽象层 — 统一接口 + 容灾链

v1.0: 将散落在 fetcher/__init__.py 中的 7 个 K 线源、
     4 个基本面源、3 个实时行情源统一封装为 DataSource 子类。

设计原则：
- 每个 DataSource 子类封装单一数据提供商
- DataSourceChain 实现优先级容灾链（逐个尝试，成功即返回）
- 保持与现有 fetcher 模块 100% 向后兼容
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd
import requests

from .env import get_env
from .logging_config import get_logger

logger = get_logger("datasource")


# ============================================
# 数据新鲜度标记
# ============================================


class Freshness(Enum):
    """数据新鲜度等级 — 与 fetcher.Freshness 保持一致"""

    FRESH = "fresh"
    CACHED = "cached"
    DEGRADED = "degraded"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


# ============================================
# 熔断器（提取自 fetcher，独立可用）
# ============================================


class CircuitBreaker:
    """熔断器：连续失败 N 次后，M 秒内跳过该 API。

    用法:
        cb = CircuitBreaker("sina_api", max_failures=3, cooldown=300)
        if not cb.allow():
            return fallback()
        try:
            result = api_call()
            cb.report(success=True)
        except Exception:
            cb.report(success=False)
    """

    def __init__(self, name: str, max_failures: int = 3, cooldown: float = 300):
        self.name = name
        self.max_failures = max_failures
        self.cooldown = cooldown
        self._failures = 0
        self._last_fail = 0.0
        self._open_until = 0.0

    def allow(self) -> bool:
        """检查是否允许调用（未熔断）"""
        if self._open_until > time.time():
            logger.debug(f"熔断器[{self.name}] 激活中，剩余 {self._open_until - time.time():.0f}s")
            return False
        return True

    def report(self, success: bool) -> None:
        """报告调用结果"""
        if success:
            self._failures = 0
        else:
            self._failures += 1
            self._last_fail = time.time()
            if self._failures >= self.max_failures:
                self._open_until = time.time() + self.cooldown
                logger.warning(
                    f"熔断器[{self.name}] {self._failures}次连续失败，熔断{self.cooldown}s"
                )


# ============================================
# HTTP 会话池（连接复用）
# ============================================


class HTTPSessionPool:
    """HTTP 会话连接池 — 避免每次请求新建 TCP 连接"""

    _sina: requests.Session | None = None
    _em: requests.Session | None = None

    @classmethod
    def sina(cls) -> requests.Session:
        if cls._sina is None:
            cls._sina = requests.Session()
            cls._sina.trust_env = False
            cls._sina.headers.update(
                {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Referer": "http://finance.sina.com.cn",
                }
            )
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=10, pool_maxsize=30, max_retries=0
            )
            cls._sina.mount("http://", adapter)
            cls._sina.mount("https://", adapter)
        return cls._sina

    @classmethod
    def em(cls) -> requests.Session:
        if cls._em is None:
            cls._em = requests.Session()
            cls._em.trust_env = False
            cls._em.headers.update(
                {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Referer": "https://www.eastmoney.com",
                }
            )
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=5, pool_maxsize=15, max_retries=0
            )
            cls._em.mount("http://", adapter)
            cls._em.mount("https://", adapter)
        return cls._em


# ============================================
# 跨进程速率限制器（文件锁 → 取代内存列表）
# ============================================


class FileRateLimiter:
    """跨进程速率限制器 — fcntl 文件锁 + JSON 持久化

    解决原 `_SINA_REQUEST_TIMES` 内存列表在多进程环境下无法协调的问题。
    使用 fcntl.flock() 实现进程间互斥，JSON 文件持久化请求时间戳。

    用法:
        limiter = FileRateLimiter("sina", max_requests=130, window=120)
        limiter.check_and_wait()
        # ... 调用 API ...
    """

    def __init__(
        self,
        name: str,
        max_requests: int = 130,
        window: float = 120.0,
        lock_dir: str | None = None,
    ):
        self.name = name
        self.max_requests = max_requests
        self.window = window

        # 文件路径：状态文件 + 锁文件（独立文件避免状态读写影响锁）
        base = lock_dir or os.path.join(tempfile.gettempdir(), "stockinsight")
        os.makedirs(base, exist_ok=True)
        self._state_file = os.path.join(base, f"ratelimit_{name}.json")
        self._lock_file = os.path.join(base, f"ratelimit_{name}.lock")

        # 进程内线程安全锁（减少 fcntl 竞争）
        self._thread_lock = threading.Lock()
        self._lock_fd: int | None = None

    def _acquire(self):
        """获取排他文件锁（阻塞直到成功）"""
        if self._lock_fd is None:
            self._lock_fd = os.open(self._lock_file, os.O_CREAT | os.O_RDWR, 0o644)
        fcntl.flock(self._lock_fd, fcntl.LOCK_EX)

    def _release(self):
        """释放文件锁"""
        if self._lock_fd is not None:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)

    def _read_timestamps(self) -> list[float]:
        """从 JSON 文件读取请求时间戳列表"""
        try:
            if os.path.exists(self._state_file) and os.path.getsize(self._state_file) > 0:
                with open(self._state_file, encoding="utf-8") as f:
                    return json.load(f)  # type: ignore[no-any-return]
        except (json.JSONDecodeError, OSError):
            pass
        return []

    def _write_timestamps(self, timestamps: list[float]):
        """写入请求时间戳到 JSON 文件"""
        try:
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(timestamps, f)
        except OSError:
            pass

    def check_and_wait(self) -> None:
        """检查速率限制，必要时阻塞等待。

        此方法是线程安全 + 进程安全的：
        - 进程内用 threading.Lock 防止线程竞争
        - 进程间用 fcntl.flock 防止多进程同时读写状态文件
        """
        with self._thread_lock:
            self._acquire()
            try:
                timestamps = self._read_timestamps()
                now = time.time()

                # 清理过期记录
                timestamps = [t for t in timestamps if now - t < self.window]

                # 达到阈值 → 等待最早记录过期
                if len(timestamps) >= self.max_requests:
                    oldest = min(timestamps)
                    wait = self.window - (now - oldest) + 1  # +1s 缓冲
                    if wait > 0:
                        logger.info(
                            f"RateLimiter[{self.name}]: "
                            f"{len(timestamps)}次/{self.window:.0f}s，等待{wait:.1f}s"
                        )
                        time.sleep(wait)
                        timestamps = []  # 等待期间旧记录已过期

                # 记录本次请求
                timestamps.append(time.time())
                self._write_timestamps(timestamps)
            finally:
                self._release()

    def reset(self):
        """重置速率限制状态（手动清除所有记录）"""
        with self._thread_lock:
            self._acquire()
            try:
                self._write_timestamps([])
                logger.info(f"RateLimiter[{self.name}]: 已重置")
            finally:
                self._release()

    def current_count(self) -> int:
        """查询当前窗口内请求数（用于监控）"""
        with self._thread_lock:
            self._acquire()
            try:
                timestamps = self._read_timestamps()
                now = time.time()
                return sum(1 for t in timestamps if now - t < self.window)
            finally:
                self._release()


# ============================================
# 抽象基类
# ============================================


class DataSource(ABC):
    """数据源抽象基类

    所有外部数据源（新浪/腾讯/Baostock/Tushare 等）必须实现此接口。
    子类只需实现自己支持的方法，不支持的返回空即可。
    """

    def fetch_kline(self, code: str, days: int = 120) -> pd.DataFrame:
        """获取日K线数据 → 返回标准 DataFrame（日期/开盘/收盘/最高/最低/成交量/成交额）"""
        return pd.DataFrame()

    def fetch_realtime(self, codes: list[str]) -> dict:
        """获取实时行情 → 返回 {code: {最新价, 涨跌幅, ...}}"""
        return {}

    def fetch_fundamentals(self, code: str) -> dict:
        """获取基本面数据 → 返回 {ROE, 市盈率, 市净率, ...}"""
        return {}

    def fetch_sectors(self) -> pd.DataFrame:
        """获取板块列表 → 返回 DataFrame"""
        return pd.DataFrame()

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def is_available(self) -> bool:
        """检查数据源是否可用（子类可重写做健康检查）"""
        return True


# ============================================
# K 线数据源具体实现
# ============================================


def _parse_kline_df(rows: list[dict], days: int) -> pd.DataFrame:
    """将 K 线 dict 列表转为标准 DataFrame（含技术指标列）"""
    if not rows:
        return pd.DataFrame(columns=["日期", "开盘", "收盘", "最高", "最低", "成交量", "涨跌幅", "涨跌额"])
    df = pd.DataFrame(rows)
    df["日期"] = pd.to_datetime(df["日期"])
    df = df.sort_values("日期").reset_index(drop=True)
    df["涨跌幅"] = df["收盘"].pct_change() * 100
    df["涨跌额"] = df["收盘"].diff()
    df["昨收"] = df["收盘"].shift(1)
    df["振幅"] = (df["最高"] - df["最低"]) / df["昨收"].shift(1) * 100
    return df.tail(days).reset_index(drop=True)


class SinaKlineSource(DataSource):
    """新浪财经日K线（主源，免费，约150次/120s 限流）"""

    def fetch_kline(self, code: str, days: int = 120) -> pd.DataFrame:
        symbol = f"sh{code}" if code.startswith("6") else f"sz{code}"
        url = (
            "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            f"CN_MarketData.getKLineData?symbol={symbol}&scale=240&datalen={days}"
        )
        try:
            session = HTTPSessionPool.sina()
            r = session.get(url, timeout=8)
            if r.status_code == 200 and r.text and r.text != "null":
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
            logger.debug(f"新浪K线[{code}] 失败: {e}")
        return pd.DataFrame()


class TencentKlineSource(DataSource):
    """腾讯证券日K线（备选 1，不限流）"""

    def fetch_kline(self, code: str, days: int = 120) -> pd.DataFrame:
        symbol = f"sh{code}" if code.startswith("6") else f"sz{code}"
        url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,120,qfq"
        try:
            session = HTTPSessionPool.sina()
            r = session.get(url, timeout=8)
            if r.status_code == 200:
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
                            "成交额": 0,
                        }
                        for it in klines
                    ]
                    return _parse_kline_df(rows, days)
        except Exception as e:
            logger.debug(f"腾讯K线[{code}] 失败: {e}")
        return pd.DataFrame()


class BaostockKlineSource(DataSource):
    """Baostock 日K线（备选 2，完全免费 + 无限流 + 前复权）"""

    def fetch_kline(self, code: str, days: int = 120) -> pd.DataFrame:
        try:
            import baostock as bs

            bs.login()
            symbol = f"sh.{code}" if code.startswith("6") else f"sz.{code}"
            end_date = time.strftime("%Y-%m-%d")
            start_date = (pd.Timestamp.now() - pd.Timedelta(days=days + 60)).strftime("%Y-%m-%d")

            rs = bs.query_history_k_data_plus(
                symbol,
                "date,open,close,high,low,volume,amount",
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag="2",  # 前复权
            )
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
        except Exception as e:
            logger.debug(f"Baostock K线[{code}] 失败: {e}")
        return pd.DataFrame()


class ADataKlineSource(DataSource):
    """AData 日K线（备选 3，聚合多源自动切换）"""

    def fetch_kline(self, code: str, days: int = 120) -> pd.DataFrame:
        try:
            import adata.stock.market as adata_market

            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=days + 60)).strftime("%Y-%m-%d")
            df = adata_market.get_market(stock_code=code, k_type=1, start_date=start, end_date=end)
            if df is None or df.empty or len(df) < 20:
                return pd.DataFrame()

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
        except Exception as e:
            logger.debug(f"AData K线[{code}] 失败: {e}")
        return pd.DataFrame()


class TushareKlineSource(DataSource):
    """TuShare 日K线（备选 4，需注册 token）"""

    def fetch_kline(self, code: str, days: int = 120) -> pd.DataFrame:
        token = self._get_token()
        if not token:
            return pd.DataFrame()
        try:
            import tushare as ts

            ts.set_token(token)
            pro = ts.pro_api()

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
        except Exception as e:
            logger.debug(f"Tushare K线[{code}] 失败: {e}")
        return pd.DataFrame()

    @staticmethod
    def _get_token() -> str:
        """获取 Tushare token（使用统一 env 模块）"""
        return get_env("TUSHARE_TOKEN", "")

# ============================================
# 实时行情数据源
# ============================================


class SinaRealtimeSource(DataSource):
    """新浪财经实时行情（主源，约150次/120s 限流）"""

    def fetch_realtime(self, codes: list[str]) -> dict:
        if not codes:
            return {}

        symbols = ",".join(f"{'sh' if c.startswith('6') else 'sz'}{c}" for c in codes)
        try:
            session = HTTPSessionPool.sina()
            r = session.get(f"http://hq.sinajs.cn/list={symbols}", timeout=3)
            if r.status_code != 200:
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
                    "名称": parts[0],
                    "最新价": price,
                    "涨跌幅": round((price - yclose) / yclose * 100, 2) if yclose else 0,
                    "涨跌额": round(price - yclose, 2),
                    "今开": float(parts[1]) if parts[1] else 0,
                    "昨收": yclose,
                    "最高": float(parts[4]) if parts[4] else 0,
                    "最低": float(parts[5]) if parts[5] else 0,
                    "成交量": float(parts[8]) if parts[8] else 0,
                    "成交额": float(parts[9]) if parts[9] else 0,
                    "open": float(parts[1]) if parts[1] else 0,  # analyzer.py 兼容字段
                    "high": float(parts[4]) if parts[4] else 0,
                    "low": float(parts[5]) if parts[5] else 0,
                    "price": price,
                    "volume": float(parts[8]) if parts[8] else 0,
                }
            return results
        except Exception as e:
            logger.debug(f"新浪实时行情失败: {e}")
        return {}


# ============================================
# 基本面数据源
# ============================================


class AKShareFundamentalsSource(DataSource):
    """AKShare 同花顺财务摘要（主源）"""

    def fetch_fundamentals(self, code: str) -> dict:
        result: dict[str, float | None] = {
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
        try:
            import akshare as ak

            fin = ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")
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
        except Exception as e:
            logger.debug(f"基本面[{code}] 失败: {e}")

        return result


# ============================================
# 容灾链 — 核心编排器
# ============================================


class DataSourceChain:
    """数据源容灾链：按优先级依次尝试，成功即返回。

    用法:
        chain = get_default_kline_chain()
        df = chain.fetch_kline("600519", days=120)
    """

    def __init__(self, sources: list[DataSource]):
        self.sources = sources
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

    def _allow_source(self, src: DataSource) -> bool:
        """检查数据源是否允许调用（未熔断）"""
        cb = self._circuit_breakers.get(src.name)
        if cb is None:
            cb = CircuitBreaker(src.name, max_failures=3, cooldown=300)
            self._circuit_breakers[src.name] = cb
        return cb.allow()

    def _report_source(self, src: DataSource, success: bool):
        cb = self._circuit_breakers.get(src.name)
        if cb is None:
            cb = CircuitBreaker(src.name, max_failures=3, cooldown=300)
            self._circuit_breakers[src.name] = cb
        cb.report(success)

    def fetch_kline(self, code: str, days: int = 120) -> pd.DataFrame:
        """按优先级依次尝试 K 线数据源，返回第一个非空 DataFrame"""
        for src in self.sources:
            if not self._allow_source(src):
                logger.debug(f"K线[{code}] 熔断跳过: {src.name}")
                continue
            try:
                df = src.fetch_kline(code, days)
                if not df.empty:
                    self._report_source(src, True)
                    logger.debug(f"K线[{code}] 命中: {src.name} ({len(df)}行)")
                    return df
                self._report_source(src, False)
            except Exception:
                self._report_source(src, False)
                logger.debug(f"K线[{code}] 异常: {src.name}")
        logger.warning(f"K线[{code}] 全部数据源失败")
        return pd.DataFrame()

    def fetch_realtime(self, codes: list[str]) -> dict:
        """按优先级依次尝试实时行情源"""
        for src in self.sources:
            if not self._allow_source(src):
                continue
            try:
                result = src.fetch_realtime(codes)
                if result:
                    self._report_source(src, True)
                    return result
                self._report_source(src, False)
            except Exception:
                self._report_source(src, False)
        return {}

    def fetch_fundamentals(self, code: str) -> dict:
        """按优先级依次尝试基本面数据源"""
        for src in self.sources:
            if not self._allow_source(src):
                continue
            try:
                result = src.fetch_fundamentals(code)
                has_valid = any(result.get(k) is not None for k in ["ROE", "市盈率", "市净率"])
                if has_valid:
                    self._report_source(src, True)
                    return result
                self._report_source(src, False)
            except Exception:
                self._report_source(src, False)
        return {}

    def reset_circuits(self):
        """重置所有熔断器（用于手动恢复）"""
        self._circuit_breakers.clear()
        logger.info("所有熔断器已重置")


# ============================================
# 预配置的默认容灾链
# ============================================

# 模块级单例 — 每个进程只创建一次
_DEFAULT_KLINE_CHAIN: DataSourceChain | None = None
_DEFAULT_REALTIME_CHAIN: DataSourceChain | None = None
_DEFAULT_FUNDAMENTALS_CHAIN: DataSourceChain | None = None


def get_default_kline_chain() -> DataSourceChain:
    """获取默认 K 线容灾链：新浪→腾讯→Baostock→AData→Tushare"""
    global _DEFAULT_KLINE_CHAIN
    if _DEFAULT_KLINE_CHAIN is None:
        _DEFAULT_KLINE_CHAIN = DataSourceChain(
            [
                SinaKlineSource(),  # 主源：新浪
                TencentKlineSource(),  # 备1：腾讯
                BaostockKlineSource(),  # 备2：Baostock（免费+复权）
                ADataKlineSource(),  # 备3：AData 聚合
                TushareKlineSource(),  # 备4：Tushare
            ]
        )
    return _DEFAULT_KLINE_CHAIN


def get_default_realtime_chain() -> DataSourceChain:
    """获取默认实时行情容灾链"""
    global _DEFAULT_REALTIME_CHAIN
    if _DEFAULT_REALTIME_CHAIN is None:
        _DEFAULT_REALTIME_CHAIN = DataSourceChain(
            [
                SinaRealtimeSource(),
            ]
        )
    return _DEFAULT_REALTIME_CHAIN


def get_default_fundamentals_chain() -> DataSourceChain:
    """获取默认基本面数据容灾链"""
    global _DEFAULT_FUNDAMENTALS_CHAIN
    if _DEFAULT_FUNDAMENTALS_CHAIN is None:
        _DEFAULT_FUNDAMENTALS_CHAIN = DataSourceChain(
            [
                AKShareFundamentalsSource(),
            ]
        )
    return _DEFAULT_FUNDAMENTALS_CHAIN


# ============================================
# 便捷顶层 API（与旧 fetcher 接口兼容）
# ============================================


def fetch_kline(code: str, days: int = 120) -> pd.DataFrame:
    """便捷方法：从默认容灾链获取 K 线"""
    return get_default_kline_chain().fetch_kline(code, days)


def fetch_realtime(codes: list[str]) -> dict:
    """便捷方法：从默认容灾链获取实时行情"""
    return get_default_realtime_chain().fetch_realtime(codes)


def fetch_fundamentals(code: str) -> dict:
    """便捷方法：从默认容灾链获取基本面数据"""
    return get_default_fundamentals_chain().fetch_fundamentals(code)


# ============================================
# 速率限制器便捷 API
# ============================================

_SINA_RATE_LIMITER: FileRateLimiter | None = None


def get_sina_rate_limiter() -> FileRateLimiter:
    """获取新浪 API 速率限制器（单例）"""
    global _SINA_RATE_LIMITER
    if _SINA_RATE_LIMITER is None:
        _SINA_RATE_LIMITER = FileRateLimiter("sina", max_requests=130, window=120)
    return _SINA_RATE_LIMITER


def check_sina_rate() -> None:
    """检查新浪 API 速率限制（跨进程安全版本）

    替代 fetcher._sina_check_rate() 的内存列表方案。
    """
    get_sina_rate_limiter().check_and_wait()
