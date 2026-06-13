"""历史评分数据库

每天扫描完成后自动追加当日结果，支持追踪：
  - 单只股票评分变化趋势
  - 选股推荐的历史表现回测
  - 全市场评分分布变化
"""

import sqlite3
from datetime import datetime

import pandas as pd

from .config import DB_PATH


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_history_db():
    """初始化历史表（幂等）"""
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_scores (
            date TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            composite_score REAL,
            rating TEXT,
            momentum_score REAL,
            technical_score REAL,
            fundamental_score REAL,
            volume_score REAL,
            risk_score REAL,
            price REAL,
            change_pct REAL,
            PRIMARY KEY (date, code)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_scores(date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_code ON daily_scores(code)")
    conn.commit()
    conn.close()


def append_daily_results(df, scan_date=None):
    """追加当日扫描结果到历史表

    Args:
        df: DataFrame，包含 代码/名称/综合评分/评级/动量分/技术分/基本面分/量能分/风险分/最新价/涨跌幅
        scan_date: 扫描日期，默认今天
    Returns:
        int: 写入行数
    """
    if df is None or df.empty:
        return 0

    if scan_date is None:
        scan_date = datetime.now().strftime("%Y-%m-%d")

    init_history_db()

    rows = []
    for _, r in df.iterrows():
        rows.append(
            (
                scan_date,
                str(r.get("代码", "")).zfill(6),
                str(r.get("名称", "")),
                float(r.get("综合评分", 0) or 0),
                str(r.get("评级", "")),
                float(r.get("动量分", 0) or 0),
                float(r.get("技术分", 0) or 0),
                float(r.get("基本面分", 0) or 0),
                float(r.get("量能分", 0) or 0),
                float(r.get("风险分", 0) or 0),
                float(r.get("最新价", 0) or 0),
                float(r.get("涨跌幅", 0) or 0),
            )
        )

    conn = _get_conn()
    conn.executemany(
        "INSERT OR REPLACE INTO daily_scores "
        "(date, code, name, composite_score, rating, momentum_score, "
        "technical_score, fundamental_score, volume_score, risk_score, price, change_pct) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM daily_scores WHERE date=?", (scan_date,)).fetchone()[0]
    conn.close()
    return n


def get_stock_history(code, days=30):
    """查询某只股票的历史评分趋势

    Returns:
        DataFrame: date, composite_score, momentum_score, ..., price, change_pct
    """
    conn = _get_conn()
    df = pd.read_sql_query(
        "SELECT * FROM daily_scores WHERE code=? ORDER BY date DESC LIMIT ?",
        conn,
        params=(str(code).zfill(6), days),
    )
    conn.close()
    return df


def get_top_stocks(date=None, top_n=20, min_score=60):
    """查询某日评分最高的股票

    Args:
        date: 日期字符串，默认最新日期
    """
    conn = _get_conn()
    if date is None:
        date = conn.execute("SELECT MAX(date) FROM daily_scores").fetchone()[0]
        if date is None:
            conn.close()
            return pd.DataFrame()

    df = pd.read_sql_query(
        "SELECT * FROM daily_scores WHERE date=? AND composite_score>=? "
        "ORDER BY composite_score DESC LIMIT ?",
        conn,
        params=(date, min_score, top_n),
    )
    conn.close()
    return df


def get_market_summary(date=None):
    """查询某日全市场评分分布统计

    Returns:
        dict: {total, avg_score, excellent(>=80), good(60-79), medium(40-59), low(<40)}
    """
    conn = _get_conn()
    if date is None:
        date = conn.execute("SELECT MAX(date) FROM daily_scores").fetchone()[0]
        if date is None:
            conn.close()
            return {}

    row = conn.execute(
        "SELECT COUNT(*), AVG(composite_score), "
        "SUM(CASE WHEN composite_score>=80 THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN composite_score>=60 AND composite_score<80 THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN composite_score>=40 AND composite_score<60 THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN composite_score<40 THEN 1 ELSE 0 END) "
        "FROM daily_scores WHERE date=?",
        (date,),
    ).fetchone()
    conn.close()

    return {
        "date": date,
        "total": int(row[0] or 0),
        "avg_score": round(row[1], 1) if row[1] else 0,
        "excellent": int(row[2] or 0),
        "good": int(row[3] or 0),
        "medium": int(row[4] or 0),
        "low": int(row[5] or 0),
    }


def get_available_dates(limit=30):
    """查询历史库中有哪些日期的数据"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT DISTINCT date FROM daily_scores ORDER BY date DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]
