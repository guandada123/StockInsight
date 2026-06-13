"""Tushare 数据下载管线 — 适配 SQLite 缓存架构

数据下载脚本，支持交易日历/股票列表/日线历史/基本面/资金流向。
从 henrylin99/quantitative_analysis 借鉴，改为 SQLite 存储。
"""

import logging
import os
import sqlite3
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta

import pandas as pd

logger = logging.getLogger("tushare_loader")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "stock_cache.db")

# ── 限速控制（强制间隔，防止触发API限流）──
_API_CALL_INTERVAL = 0.5  # 每次API请求间隔秒数
_last_api_call = 0.0
_api_lock = threading.Lock()


def _rate_limit():
    """强制限速：每次API调用至少间隔 0.5 秒"""
    global _last_api_call
    with _api_lock:
        elapsed = time.time() - _last_api_call
        if elapsed < _API_CALL_INTERVAL:
            time.sleep(_API_CALL_INTERVAL - elapsed)
        _last_api_call = time.time()


# 作业状态追踪
_jobs: dict = {}
_jobs_lock = threading.Lock()


def get_tushare_pro():
    """初始化 Tushare API（支持代理）"""
    token = ""
    api_url = ""
    # 1. 从 .env 文件读取
    try:
        env_file = os.path.join(PROJECT_ROOT, ".env")
        if os.path.exists(env_file):
            with open(env_file, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("TUSHARE_TOKEN="):
                        token = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                    elif line.startswith("TUSHARE_API_URL="):
                        api_url = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    # 2. 环境变量
    if not token:
        token = os.environ.get("TUSHARE_TOKEN", "")
    # 3. config.py
    if not token:
        try:
            from stock_analyzer.config import TUSHARE_TOKEN

            token = TUSHARE_TOKEN
        except ImportError:
            pass
    if not token:
        raise RuntimeError("未配置 TUSHARE_TOKEN，请在 .env 文件、环境变量或 config.py 中设置")
    import tushare as ts

    ts.set_token(token)
    pro = ts.pro_api()
    if api_url:
        pro._DataApi__http_url = api_url
    return pro


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


# ═══════════════════════════════════════════
# 交易日历
# ═══════════════════════════════════════════


def download_trade_calendar(progress_cb: Callable | None = None):
    """下载交易日历到 SQLite"""
    pro = get_tushare_pro()
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_trade_calendar (
                exchange TEXT,
                cal_date TEXT PRIMARY KEY,
                is_open INTEGER,
                pretrade_date TEXT
            )
        """)
        data = pro.trade_cal(exchange="", start_date="20240101", end_date="20261231")
        conn.execute("DELETE FROM stock_trade_calendar")
        rows = [tuple(r) for _, r in data.iterrows()]
        conn.executemany("INSERT INTO stock_trade_calendar VALUES (?,?,?,?)", rows)
        conn.commit()
        if progress_cb:
            progress_cb(len(rows), len(rows), "交易日历下载完成")
        logger.info(f"交易日历: {len(rows)} 条")
        return len(rows)
    finally:
        conn.close()


# ═══════════════════════════════════════════
# 股票列表
# ═══════════════════════════════════════════


def download_stock_basic(progress_cb: Callable | None = None):
    """下载全量股票基础信息到 SQLite"""
    pro = get_tushare_pro()
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_basic_info (
                ts_code TEXT PRIMARY KEY,
                symbol TEXT,
                name TEXT,
                area TEXT,
                industry TEXT,
                list_date TEXT
            )
        """)
        data = pro.stock_basic(
            exchange="", list_status="L", fields="ts_code,symbol,name,area,industry,list_date"
        )
        conn.execute("DELETE FROM stock_basic_info")
        rows = [tuple(r) for _, r in data.iterrows()]
        conn.executemany("INSERT INTO stock_basic_info VALUES (?,?,?,?,?,?)", rows)
        conn.commit()
        if progress_cb:
            progress_cb(len(rows), len(rows), "股票列表下载完成")
        logger.info(f"股票列表: {len(rows)} 只")
        return len(rows)
    finally:
        conn.close()


def download_industry(progress_cb: Callable | None = None):
    """下载全量股票行业分类到 SQLite（用于选股时按行业过滤）"""
    pro = get_tushare_pro()
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_industry (
                code TEXT PRIMARY KEY,
                industry TEXT,
                update_time REAL
            )
        """)
        _rate_limit()
        df = pro.stock_basic(list_status="L", fields="ts_code,industry")
        if df is None or df.empty:
            return 0
        now = time.time()
        rows = [(r["ts_code"].split(".")[0], r["industry"], now) for _, r in df.iterrows()]
        conn.executemany("INSERT OR REPLACE INTO stock_industry VALUES (?,?,?)", rows)
        conn.commit()
        n = len(rows)
        if progress_cb:
            progress_cb(n, n, f"行业分类 {n} 只")
        logger.info(f"行业分类: {n} 只")
        return n
    finally:
        conn.close()


def get_industry(code: str) -> str:
    """快速查询个股行业（先从SQLite读，无数据返回空）"""
    conn = _get_conn()
    try:
        cur = conn.execute("SELECT industry FROM stock_industry WHERE code=?", (code,))
        row = cur.fetchone()
        return row[0] if row else ""
    except Exception:
        return ""
    finally:
        conn.close()


def get_stocks_by_industry(industry: str) -> list:
    """获取某行业的所有股票代码"""
    conn = _get_conn()
    try:
        cur = conn.execute("SELECT code FROM stock_industry WHERE industry=?", (industry,))
        return [r[0] for r in cur.fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


# ═══════════════════════════════════════════
# 日线历史
# ═══════════════════════════════════════════


def download_daily_history(
    start_date: str = "2025-01-01", end_date: str | None = None, progress_cb: Callable | None = None
):
    """按交易日逐日下载日线数据，存入 kline_store"""
    pro = get_tushare_pro()
    conn = _get_conn()
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")

    try:
        # 获取交易日列表
        cur = conn.execute(
            "SELECT cal_date FROM stock_trade_calendar WHERE is_open=1 "
            "AND cal_date>=? AND cal_date<=? ORDER BY cal_date",
            (start_date, end_date),
        )
        trade_dates = [r[0] for r in cur.fetchall()]
        if not trade_dates:
            # 未下载交易日历，直接用日期范围
            from datetime import datetime as dt

            d0 = dt.strptime(start_date, "%Y%m%d")
            d1 = dt.strptime(end_date, "%Y%m%d")
            trade_dates = []
            while d0 <= d1:
                if d0.weekday() < 5:
                    trade_dates.append(d0.strftime("%Y%m%d"))
                d0 += timedelta(days=1)

        import pickle

        total = 0
        for i, td in enumerate(trade_dates):
            try:
                _rate_limit()  # 强制0.5秒间隔，防止触发限流
                df = pro.daily(trade_date=td)
                if df is None or df.empty:
                    continue
                # 转换为我们的 K 线格式
                for _, row in df.iterrows():
                    code = row["ts_code"].split(".")[0]  # "000001.SZ" -> "000001"
                    existing = None
                    cur2 = conn.execute("SELECT data FROM kline_store WHERE code=?", (code,))
                    old = cur2.fetchone()
                    if old:
                        existing = pickle.loads(old[0])
                    new_row = pd.DataFrame(
                        [
                            {
                                "日期": row["trade_date"],
                                "开盘": float(row["open"]),
                                "最高": float(row["high"]),
                                "最低": float(row["low"]),
                                "收盘": float(row["close"]),
                                "成交量": int(row["vol"]),
                                "成交额": float(row["amount"]) if row["amount"] else 0,
                            }
                        ]
                    )
                    if existing is not None and not existing.empty:
                        combined = pd.concat([existing, new_row], ignore_index=True)
                        combined = combined.drop_duplicates(subset=["日期"], keep="last")
                    else:
                        combined = new_row
                    conn.execute(
                        "INSERT OR REPLACE INTO kline_store VALUES (?,?,?)",
                        (code, pickle.dumps(combined), time.time()),
                    )
                    total += 1
                if progress_cb and i % 10 == 0:
                    progress_cb(i, len(trade_dates), f"日线 {td}")
            except Exception as e:
                logger.warning(f"日线下载失败 {td}: {e}")
                continue
        conn.commit()
        logger.info(f"日线下载完成: {total} 条更新")
        return total
    finally:
        conn.close()


# ═══════════════════════════════════════════
# 基本面数据
# ═══════════════════════════════════════════


def download_daily_basic(
    start_date: str = "2025-01-01", end_date: str | None = None, progress_cb: Callable | None = None
):
    """下载每日基本面指标"""
    pro = get_tushare_pro()
    conn = _get_conn()
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")

    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_daily_basic (
                ts_code TEXT, trade_date TEXT,
                pe REAL, pe_ttm REAL, pb REAL,
                ps REAL, ps_ttm REAL, dv_ratio REAL, dv_ttm REAL,
                total_mv REAL, circ_mv REAL,
                PRIMARY KEY (ts_code, trade_date)
            )
        """)
        trade_dates = []
        d0 = datetime.strptime(start_date, "%Y%m%d")
        d1 = datetime.strptime(end_date, "%Y%m%d")
        while d0 <= d1:
            if d0.weekday() < 5:
                trade_dates.append(d0.strftime("%Y%m%d"))
            d0 += timedelta(days=1)

        total = 0
        for i, td in enumerate(trade_dates):
            try:
                df = pro.daily_basic(trade_date=td)
                if df is None or df.empty:
                    continue
                rows = []
                for _, r in df.iterrows():
                    rows.append(
                        (
                            r["ts_code"],
                            r["trade_date"],
                            float(r.get("pe", 0) or 0),
                            float(r.get("pe_ttm", 0) or 0),
                            float(r.get("pb", 0) or 0),
                            float(r.get("ps", 0) or 0),
                            float(r.get("ps_ttm", 0) or 0),
                            float(r.get("dv_ratio", 0) or 0),
                            float(r.get("dv_ttm", 0) or 0),
                            float(r.get("total_mv", 0) or 0),
                            float(r.get("circ_mv", 0) or 0),
                        )
                    )
                conn.executemany(
                    "INSERT OR REPLACE INTO stock_daily_basic VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows
                )
                total += len(rows)
                if progress_cb and i % 5 == 0:
                    progress_cb(i, len(trade_dates), f"基本面 {td}")
            except Exception as e:
                logger.warning(f"基本面下载失败 {td}: {e}")
                continue
        conn.commit()
        logger.info(f"基本面下载完成: {total} 条")
        return total
    finally:
        conn.close()


# ═══════════════════════════════════════════
# 作业管理
# ═══════════════════════════════════════════


def submit_job(job_type: str, params: dict | None = None) -> str:
    """提交数据下载作业，返回 job_id"""
    import uuid

    job_id = str(uuid.uuid4())[:8]
    if job_type not in JOB_TYPES:
        raise ValueError(f"不支持的作业类型: {job_type}")

    name, func = JOB_TYPES[job_type]
    params = params or {}
    status = {
        "id": job_id,
        "type": job_type,
        "name": name,
        "status": "pending",
        "progress": 0,
        "total": 0,
        "message": "",
        "started": time.strftime("%H:%M:%S"),
        "done": None,
    }

    def _update(progress, total, msg):
        with _jobs_lock:
            s = _jobs.get(job_id, status)
            s["progress"] = progress
            s["total"] = total
            s["message"] = msg
            s["status"] = "running" if progress < total else "done"

    def _run():
        with _jobs_lock:
            _jobs[job_id]["status"] = "running"
        try:
            if job_type in ("daily_history", "daily_basic", "moneyflow"):
                func(
                    start_date=params.get("start_date", "2025-01-01"),
                    end_date=params.get("end_date"),
                    progress_cb=_update,
                )
            else:
                func(progress_cb=_update)
            with _jobs_lock:
                _jobs[job_id]["status"] = "done"
                _jobs[job_id]["done"] = time.strftime("%H:%M:%S")
                _jobs[job_id]["message"] = "完成"
        except Exception as e:
            with _jobs_lock:
                _jobs[job_id]["status"] = "failed"
                _jobs[job_id]["message"] = str(e)

    with _jobs_lock:
        _jobs[job_id] = status
    threading.Thread(target=_run, daemon=True).start()
    return job_id


# ═══════════════════════════════════════════
# 资金流向（Tushare moneyflow）
# ═══════════════════════════════════════════


def download_moneyflow_latest(days: int = 1, progress_cb: Callable | None = None):
    """增量下载最近N个交易日资金流向（每日1次，限频安全）

    免费版 moneyflow 限频 1次/小时，每次调用返回全市场当日数据。
    策略：每天16:00后调用1次，拉取当日全市场资金流向。
    """
    pro = get_tushare_pro()
    conn = _get_conn()
    end_date = datetime.now().strftime("%Y%m%d")

    # 确保表存在
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_moneyflow (
            code TEXT, trade_date TEXT,
            net_mf_amount REAL,
            buy_elg_amount REAL, sell_elg_amount REAL,
            buy_lg_amount REAL, sell_lg_amount REAL,
            buy_md_amount REAL, sell_md_amount REAL,
            buy_sm_amount REAL, sell_sm_amount REAL,
            buy_total_amount REAL, sell_total_amount REAL,
            PRIMARY KEY (code, trade_date)
        )
    """)

    # 已有日期
    existing = set()
    for r in conn.execute("SELECT DISTINCT trade_date FROM stock_moneyflow"):
        existing.add(r[0])

    # 按日拉取（每天全市场1次API调用）
    from datetime import datetime as dt

    trade_dates = []
    d0 = dt.now()
    count = 0
    while count < abs(days):
        ds = d0.strftime("%Y%m%d")
        if d0.weekday() < 5:
            trade_dates.append(ds)
            count += 1
        d0 -= timedelta(days=1)

    total = 0
    for td in trade_dates:
        if td in existing:
            if progress_cb:
                progress_cb(1, 1, f"资金流向 {td} 已有数据，跳过")
            continue
        if progress_cb:
            progress_cb(0, 1, f"资金流向 {td} 拉取中...")
        try:
            _rate_limit()  # 强制0.5秒间隔
            df = pro.moneyflow(trade_date=td)
            if df is None or df.empty:
                continue
            rows = []
            for _, r in df.iterrows():
                code = r["ts_code"].split(".")[0]
                buy_total = (
                    float(r.get("buy_sm_amount", 0) or 0)
                    + float(r.get("buy_md_amount", 0) or 0)
                    + float(r.get("buy_lg_amount", 0) or 0)
                    + float(r.get("buy_elg_amount", 0) or 0)
                )
                sell_total = (
                    float(r.get("sell_sm_amount", 0) or 0)
                    + float(r.get("sell_md_amount", 0) or 0)
                    + float(r.get("sell_lg_amount", 0) or 0)
                    + float(r.get("sell_elg_amount", 0) or 0)
                )
                rows.append(
                    (
                        code,
                        td,
                        float(r.get("net_mf_amount", 0) or 0),
                        float(r.get("buy_elg_amount", 0) or 0),
                        float(r.get("sell_elg_amount", 0) or 0),
                        float(r.get("buy_lg_amount", 0) or 0),
                        float(r.get("sell_lg_amount", 0) or 0),
                        float(r.get("buy_md_amount", 0) or 0),
                        float(r.get("sell_md_amount", 0) or 0),
                        float(r.get("buy_sm_amount", 0) or 0),
                        float(r.get("sell_sm_amount", 0) or 0),
                        buy_total,
                        sell_total,
                    )
                )
            if rows:
                conn.executemany(
                    """INSERT OR REPLACE INTO stock_moneyflow VALUES
                       (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    rows,
                )
                total += len(rows)
                conn.commit()
            if progress_cb:
                progress_cb(1, 1, f"资金流向 {td}: {len(rows)} 只")
        except Exception as e:
            logger.warning(f"资金流向下载失败 {td}: {str(e)[:80]}")
            continue
        if len(trade_dates) > 1:
            time.sleep(65)  # 限频间隔

    logger.info(f"资金流向增量: {total} 条 ({len(trade_dates)}天)")
    return total


# 保留原函数用于大量回补（pro版或手动慢跑）
download_moneyflow = download_moneyflow_latest


def get_moneyflow_cache(code: str, days: int = 20) -> pd.DataFrame | None:
    """从 SQLite 缓存读取个股资金流向，返回与 fetcher 兼容的格式"""
    conn = _get_conn()
    try:
        df = pd.read_sql_query(
            """SELECT trade_date, net_mf_amount,
                      buy_elg_amount, sell_elg_amount,
                      buy_lg_amount, sell_lg_amount
               FROM stock_moneyflow
               WHERE code=? AND net_mf_amount IS NOT NULL
               ORDER BY trade_date DESC LIMIT ?""",
            conn,
            params=(code, days),
        )
        if df.empty:
            return None
        df.columns = ["日期", "主力净流入", "超大单买入", "超大单卖出", "大单买入", "大单卖出"]
        return df
    except Exception:
        return None
    finally:
        conn.close()


def get_job_status(job_id: str) -> dict | None:
    with _jobs_lock:
        return _jobs.get(job_id)


def list_jobs(limit: int = 20, status_filter: str | None = None) -> list:
    with _jobs_lock:
        jobs = list(_jobs.values())
    if status_filter:
        jobs = [j for j in jobs if j["status"] == status_filter]
    jobs.sort(key=lambda j: j["started"], reverse=True)
    return jobs[:limit]


# ═══════════════════════════════════════════
# 作业类型注册（所有函数定义之后）
# ═══════════════════════════════════════════

JOB_TYPES = {
    "trade_calendar": ("交易日历", download_trade_calendar),
    "stock_basic": ("股票列表", download_stock_basic),
    "industry": ("行业分类", download_industry),
    "daily_history": ("日线历史", download_daily_history),
    "daily_basic": ("基本面数据", download_daily_basic),
    "moneyflow": ("资金流向", download_moneyflow_latest),
}
