"""数据缓存层模块

使用 sqlite3 实现通用 KV 缓存，线程内连接复用。
包装 fetcher 中的核心函数，提供带 TTL 的缓存版本。
支持 K线/基本面/板块/新闻/舆情/研报/大盘指数 缓存。
"""

import pickle
import sqlite3
import threading
import time
from typing import Any

from .config import (
    DB_PATH,
    FUNDAMENTALS_CACHE_TTL,
    MEM_CACHE_MAX,
    NT_HOLDINGS_CACHE_TTL,
)
from .fetcher import get_fundamentals, get_kline, get_sectors

_MEM_CACHE_MAX = MEM_CACHE_MAX  # 5000

# 线程内连接复用
_local = threading.local()

# 进程内内存缓存（避免重复 pickle 反序列化同一 DataFrame）
_MEM_CACHE: dict[str, Any] = {}


def _mem_cache_set(key, value):
    """写入进程内内存缓存，超过上限时淘汰最旧的条目"""
    if len(_MEM_CACHE) >= _MEM_CACHE_MAX:
        oldest = min(_MEM_CACHE, key=lambda k: _MEM_CACHE[k][0])
        del _MEM_CACHE[oldest]
    _MEM_CACHE[key] = (time.time(), value)


def _get_conn():
    """获取当前线程的数据库连接（懒创建），开启 WAL 模式提升写入性能"""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.execute(
            "CREATE TABLE IF NOT EXISTS cache "
            "(key TEXT PRIMARY KEY, value BLOB, created_at REAL, ttl_seconds INTEGER)"
        )
        # 永久存储表（不复用 cache 表的 TTL 机制，数据永不过期）
        _local.conn.execute(
            "CREATE TABLE IF NOT EXISTS kline_store "
            "(code TEXT PRIMARY KEY, data BLOB, updated_at REAL)"
        )
        _local.conn.execute(
            "CREATE TABLE IF NOT EXISTS fund_store "
            "(code TEXT PRIMARY KEY, data BLOB, updated_at REAL)"
        )
        _local.conn.execute(
            "CREATE TABLE IF NOT EXISTS sector_store "
            "(name TEXT PRIMARY KEY, data BLOB, updated_at REAL)"
        )
        _local.conn.execute(
            "CREATE TABLE IF NOT EXISTS nt_store "
            "(code TEXT PRIMARY KEY, data BLOB, updated_at REAL)"
        )
        # 高级分析永久存储表
        _local.conn.execute(
            "CREATE TABLE IF NOT EXISTS perm_store "
            "(key TEXT PRIMARY KEY, data BLOB, updated_at REAL)"
        )
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn.commit()
    return _local.conn


# ── 核心缓存操作 ──────────────────────────────


def cache_get(key, max_age=None):
    """读取缓存，过期则删除并返回 None。
    max_age: 覆盖 TTL（秒），用于获取过期缓存作为兜底
    """
    try:
        conn = _get_conn()
        cur = conn.execute("SELECT value, created_at, ttl_seconds FROM cache WHERE key=?", (key,))
        row = cur.fetchone()
        if row is None:
            return None

        value_blob, created_at, ttl = row
        age = time.time() - created_at
        limit = max_age if max_age is not None else ttl
        if age > limit:
            if max_age is None:  # 默认行为：删除过期条目
                conn.execute("DELETE FROM cache WHERE key=?", (key,))
                conn.commit()
            return None

        return pickle.loads(value_blob)
    except Exception:
        return None


def cache_set(key, value, ttl=3600):
    """写入缓存，使用 pickle 序列化"""
    try:
        conn = _get_conn()
        blob = pickle.dumps(value)
        conn.execute(
            "INSERT OR REPLACE INTO cache (key, value, created_at, ttl_seconds) VALUES (?, ?, ?, ?)",
            (key, blob, time.time(), ttl),
        )
        conn.commit()
        return True
    except Exception:
        return False


def cache_clear(key):
    """删除单条缓存"""
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM cache WHERE key=?", (key,))
        conn.commit()
        return True
    except Exception:
        return False


def cache_clear_all():
    """清空全部缓存"""
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM cache")
        conn.commit()
        return True
    except Exception:
        return False


# ── 通用永久存储操作 ──────────────────────────


def _perm_load(table, key_col, key_val):
    """从永久存储表加载数据"""
    try:
        conn = _get_conn()
        cur = conn.execute(f"SELECT data FROM {table} WHERE {key_col}=?", (key_val,))
        row = cur.fetchone()
        if row:
            return pickle.loads(row[0])
    except Exception:
        pass
    return None


def _perm_save(table, key_col, key_val, data):
    """保存数据到永久存储表"""
    try:
        conn = _get_conn()
        blob = pickle.dumps(data)
        conn.execute(
            f"INSERT OR REPLACE INTO {table} ({key_col}, data, updated_at) VALUES (?, ?, ?)",
            (key_val, blob, time.time()),
        )
        conn.commit()
    except Exception:
        pass


# ── 业务缓存包装 ──────────────────────────────


def _load_kline_store(code):
    """从永久存储加载 K 线数据 (SQLite pickle)"""
    return _perm_load("kline_store", "code", code)


def _save_kline_store(code, df):
    """保存 K 线数据 (SQLite pickle)"""
    _perm_save("kline_store", "code", code, df)


def cached_kline(code, days=120):
    """获取 K 线数据——永久本地存储 + 增量拉取。

    首次拉取全量历史数据存入本地，后续只拉取新增交易日（通常 0-1 天）。
    彻底消除因 TTL 过期导致的全量重拉。
    """
    from datetime import datetime

    import pandas as pd

    # 1. 进程内内存缓存（按 code+days 区分，快速路径）
    mem_key = f"kline:{code}:{days}"
    mem_entry = _MEM_CACHE.get(mem_key)
    if mem_entry is not None:
        cached_ts, cached_df = mem_entry  # _mem_cache_set 存的是 (timestamp, value)
        if time.time() - cached_ts < 1800:
            return cached_df

    # 2. 加载永久存储的历史数据
    stored = _load_kline_store(code)

    if stored is not None and not stored.empty:
        last_date = pd.Timestamp(stored["日期"].iloc[-1])
        today = datetime.now()
        days_passed = (today - last_date.to_pydatetime()).days

        # 数据够新鲜(昨天或今天) → 直接返回，不拉API
        if days_passed <= 1 and len(stored) >= days:
            result = stored.tail(days).reset_index(drop=True)
            _mem_cache_set(mem_key, result)
            return result

        # 如果存储数据不够请求天数（如存了120天但要365天），全量重拉
        if len(stored) < days:
            try:
                data = get_kline(code, days=max(days, 365))
                if not data.empty:
                    data["日期"] = pd.to_datetime(data["日期"])
                    data = data.sort_values("日期").reset_index(drop=True)
                    # 合并去重（保留旧数据中可能被新API缺失的日期）
                    combined = pd.concat([stored, data], ignore_index=True)
                    combined = combined.drop_duplicates(subset=["日期"], keep="last")
                    combined = combined.sort_values("日期").reset_index(drop=True)
                    _save_kline_store(code, combined)
                    result = combined.tail(days).reset_index(drop=True)
                    _mem_cache_set(mem_key, result)
                    return result
            except Exception:
                pass
            # 重拉失败，用已有数据兜底
            if len(stored) >= 20:
                result = stored.tail(days).reset_index(drop=True)
                _mem_cache_set(mem_key, result)
                return result

        # 增量拉取：仅交易日(排除周末) + 盘后或数据落后，避免无效API调用
        is_weekend = today.weekday() >= 5
        # Allow update on weekends if data is stale (missed Friday)
        if (not is_weekend or days_passed >= 2) and (days_passed >= 2 or today.hour >= 15):
            try:
                missing_days = max(days_passed + 2, 5)
                new_data = get_kline(code, days=missing_days)
                if not new_data.empty:
                    combined = pd.concat([stored, new_data], ignore_index=True)
                    combined["日期"] = pd.to_datetime(combined["日期"])
                    combined = combined.drop_duplicates(subset=["日期"], keep="last")
                    combined = combined.sort_values("日期").reset_index(drop=True)
                    _save_kline_store(code, combined)
                    result = combined.tail(days).reset_index(drop=True)
                    _mem_cache_set(mem_key, result)
                    return result
            except Exception:
                pass

        # 增量跳过/失败，用已有数据兜底
        if len(stored) >= 20:
            result = stored.tail(days).reset_index(drop=True)
            _mem_cache_set(mem_key, result)
            return result

    # 3. 首次拉取（无历史数据）
    try:
        data = get_kline(code, days=max(days, 365))  # 首次拉 1 年全量
        if not data.empty:
            data["日期"] = pd.to_datetime(data["日期"])
            data = data.sort_values("日期").reset_index(drop=True)
            _save_kline_store(code, data)
            result = data.tail(days).reset_index(drop=True)
            _mem_cache_set(mem_key, result)
            return result
    except Exception:
        pass

    return pd.DataFrame()


def cached_fundamentals(code):
    """获取基本面数据——永久本地存储 + 按需刷新。

    财务数据基于季报，7 天内不重复拉取。永久存储确保隔夜不失效。
    """
    FUND_STALE = FUNDAMENTALS_CACHE_TTL  # 使用统一配置值(24h)

    # 1. 内存缓存
    mem_key = f"fundamentals:{code}"
    mem_entry = _MEM_CACHE.get(mem_key)
    if mem_entry is not None and time.time() - mem_entry[0] < 1800:
        return mem_entry[1]

    # 2. 永久存储
    stored = _perm_load("fund_store", "code", code)
    if stored is not None:
        # 检查是否过时（超过 7 天重新拉取）
        conn = _get_conn()
        cur = conn.execute("SELECT updated_at FROM fund_store WHERE code=?", (code,))
        row = cur.fetchone()
        if row and time.time() - row[0] < FUND_STALE:
            _mem_cache_set(mem_key, stored)
            return stored

    # 3. 拉取并永久存储
    # 有旧数据且不到7天 → 直接用，不重拉
    if stored is not None and row and time.time() - row[0] < FUND_STALE * 7:
        _mem_cache_set(mem_key, stored)
        return stored

    try:
        data = get_fundamentals(code)
        has_valid = any(data.get(k) is not None for k in ["ROE", "市盈率", "市净率"])
        if has_valid:
            _perm_save("fund_store", "code", code, data)
            _mem_cache_set(mem_key, data)
            return data
        else:
            # API 返回了空数据 → 有旧用旧
            if stored is not None:
                _mem_cache_set(mem_key, stored)
                return stored
            raise ValueError("API返回空")
    except Exception:
        # 拉取失败 → 有旧数据用旧数据，不缓存空结果
        if stored is not None:
            _mem_cache_set(mem_key, stored)
            return stored
        empty = {
            "市盈率": None,
            "市净率": None,
            "ROE": None,
            "营收增长": None,
            "净利润增长": None,
            "毛利率": None,
            "净利率": None,
            "每股收益": None,
        }
        return empty


def cached_market_news():
    """包装 get_market_news，TTL 30 分钟（市场要闻变化快）"""
    from .fetcher import get_market_news

    key = "market_news"
    cached = cache_get(key)
    if cached is not None:
        return cached
    try:
        data = get_market_news()
        if not data.empty:
            cache_set(key, data, ttl=1800)  # 30 分钟
        return data
    except Exception:
        import pandas as pd

        return pd.DataFrame()


def cached_sectors():
    """获取板块列表——永久本地存储 + 按需刷新（板块分类极少变动）"""
    SECTOR_STALE = 86400  # 1 天

    # 内存缓存
    mem_key = "sectors"
    mem_entry = _MEM_CACHE.get(mem_key)
    if mem_entry is not None and time.time() - mem_entry[0] < 3600:
        return mem_entry[1]

    # 永久存储
    stored = _perm_load("sector_store", "name", "all_sectors")
    if stored is not None:
        conn = _get_conn()
        cur = conn.execute("SELECT updated_at FROM sector_store WHERE name=?", ("all_sectors",))
        row = cur.fetchone()
        if row and time.time() - row[0] < SECTOR_STALE:
            _mem_cache_set(mem_key, stored)
            return stored

    # 拉取并永久存储
    try:
        data = get_sectors()
        if not data.empty:
            _perm_save("sector_store", "name", "all_sectors", data)
        _mem_cache_set(mem_key, data)
        return data
    except Exception:
        if stored is not None:
            return stored  # 兜底：返回旧数据
        import pandas as pd

        return pd.DataFrame()


# ── 新闻消息缓存包装 ────────────────────────────


def cached_stock_news(code):
    """包装 get_stock_news，TTL 2 小时"""
    from .fetcher import get_stock_news

    key = f"news:{code}"
    cached = cache_get(key)
    if cached is not None:
        return cached
    try:
        data = get_stock_news(code)
        if not data.empty:
            cache_set(key, data, ttl=7200)
        return data
    except Exception:
        import pandas as pd

        return pd.DataFrame()


def cached_weibo_sentiment():
    """包装 get_weibo_sentiment，TTL 1 小时"""
    from .fetcher import get_weibo_sentiment

    key = "weibo_sentiment"
    cached = cache_get(key)
    if cached is not None:
        return cached
    try:
        data = get_weibo_sentiment()
        if not data.empty:
            cache_set(key, data, ttl=3600)
        return data
    except Exception:
        import pandas as pd

        return pd.DataFrame()


def cached_stock_research(code):
    """包装 get_stock_research，TTL 24 小时"""
    from .fetcher import get_stock_research

    key = f"research:{code}"
    cached = cache_get(key)
    if cached is not None:
        return cached
    try:
        data = get_stock_research(code)
        if not data.empty:
            cache_set(key, data, ttl=86400)
        return data
    except Exception:
        import pandas as pd

        return pd.DataFrame()


def cached_market_overview():
    """包装 get_market_overview，TTL 2 分钟"""
    from .fetcher import get_market_overview

    key = "market_overview"
    cached = cache_get(key)
    if cached is not None:
        return cached
    try:
        data = get_market_overview()
        if data:
            cache_set(key, data, ttl=120)
        return data
    except Exception:
        return {}


def cached_fund_flow(code, days=20):
    """包装 get_fund_flow，TTL 24h，API失败时用过期缓存(48h)兜底

    资金流向 T+1 发布，盘中拉取的数据收盘后仍然有效。
    """
    import pandas as pd

    from .fetcher import get_fund_flow

    key = f"fundflow:{code}"

    # 先查新鲜缓存（24小时内）
    cached = cache_get(key)
    if cached is not None:
        if hasattr(cached, "attrs"):
            cached.attrs["freshness"] = "cached"
        return cached

    # 过期缓存兜底（48h）→ 先返回，不阻塞
    stale = cache_get(key, max_age=172800)
    if stale is not None:
        if hasattr(stale, "attrs"):
            stale.attrs["freshness"] = "degraded"
        # 后台异步刷新
        import threading

        def _bg_refresh():
            try:
                data = get_fund_flow(code, days=days)
                if not data.empty:
                    cache_set(key, data, ttl=86400)
            except Exception:
                pass

        threading.Thread(target=_bg_refresh, daemon=True).start()
        return stale

    # 完全无缓存 → 尝试一次
    try:
        data = get_fund_flow(code, days=days)
        if not data.empty:
            if hasattr(data, "attrs"):
                data.attrs["freshness"] = "fresh"
            cache_set(key, data, ttl=86400)
            return data
    except Exception:
        pass

    empty = pd.DataFrame()
    empty.attrs["freshness"] = "stale"
    return empty


def cached_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流"):
    """包装 get_sector_fund_flow_rank，TTL 2 小时"""
    from .fetcher import get_sector_fund_flow_rank

    key = f"sector_fundflow:{indicator}:{sector_type}"
    cached = cache_get(key)
    if cached is not None:
        return cached
    try:
        data = get_sector_fund_flow_rank(indicator=indicator, sector_type=sector_type)
        if not data.empty:
            cache_set(key, data, ttl=7200)
        return data
    except Exception:
        import pandas as pd

        return pd.DataFrame()


def cached_national_team_holdings(code):
    """获取国家队持股——永久本地存储 + 按需刷新（季报数据极少变动）"""
    from .fetcher import get_national_team_holdings

    # 内存缓存
    mem_key = f"nt:{code}"
    mem_entry = _MEM_CACHE.get(mem_key)
    if mem_entry is not None and time.time() - mem_entry[0] < NT_HOLDINGS_CACHE_TTL:
        return mem_entry[1]

    # 永久存储
    stored = _perm_load("nt_store", "code", code)
    if stored is not None:
        conn = _get_conn()
        cur = conn.execute("SELECT updated_at FROM nt_store WHERE code=?", (code,))
        row = cur.fetchone()
        if row and time.time() - row[0] < NT_HOLDINGS_CACHE_TTL:
            _mem_cache_set(mem_key, stored)
            return stored

    # 拉取并永久存储
    result = {"has_national_team": False, "holders": []}
    try:
        result = get_national_team_holdings(code)
        _perm_save("nt_store", "code", code, result)
    except Exception:
        if stored is not None:
            _mem_cache_set(mem_key, stored)
            return stored  # 兜底：返回旧数据
        _perm_save("nt_store", "code", code, result)  # 失败也存空结果防反复重试
    _mem_cache_set(mem_key, result)
    return result
