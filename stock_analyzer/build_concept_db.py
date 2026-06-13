"""构建概念板块数据库 — 东方财富概念板块

概念板块 vs 行业板块:
  行业板块(industry): 证监会分类，每只股票一个行业 (已存入 stock_sector_v2)
  概念板块(concept):  主题投资概念，每只股票可属多个概念 (存入 stock_concept)

数据源: akshare stock_board_concept_name_em() → 概念列表
       akshare stock_board_concept_cons_em() → 概念成分股

用法: python -c "from stock_analyzer.build_concept_db import build; build()"
"""

import os
import sqlite3
import time

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stock_cache.db"
)


def build(progress_cb=None):
    """从东方财富拉取全量概念板块 → 成分股映射"""
    import akshare as ak

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS stock_concept (
        code TEXT, concept TEXT, source TEXT DEFAULT 'eastmoney',
        PRIMARY KEY (code, concept))""")
    conn.execute("DELETE FROM stock_concept")

    # 1. 获取概念列表
    print("获取概念板块列表...")
    concepts_df = ak.stock_board_concept_name_em()
    concept_names = concepts_df["板块名称"].tolist()
    print(f"  共 {len(concept_names)} 个概念板块")

    # 2. 逐概念获取成分股
    total = 0
    failed = 0
    for i, name in enumerate(concept_names):
        try:
            df = ak.stock_board_concept_cons_em(symbol=name)
            if df is not None and not df.empty and "代码" in df.columns:
                rows = [(c, name, "eastmoney") for c in df["代码"].tolist()]
                conn.executemany("INSERT OR IGNORE INTO stock_concept VALUES (?,?,?)", rows)
                total += len(rows)
        except Exception:
            failed += 1
        if progress_cb and i % 20 == 0:
            progress_cb(i, len(concept_names), name)
        time.sleep(0.3)  # 限速

    conn.commit()

    cur = conn.execute("SELECT COUNT(DISTINCT concept) FROM stock_concept")
    concept_cnt = cur.fetchone()[0]
    cur = conn.execute("SELECT COUNT(DISTINCT code) FROM stock_concept")
    stock_cnt = cur.fetchone()[0]

    print(f"  完成: {concept_cnt} 个概念, {stock_cnt} 只股票, {total} 条映射")
    print(f"  失败: {failed} 个概念")
    conn.close()
    return concept_cnt


def get_concepts(code: str) -> list:
    """获取某只股票的所有概念板块"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.execute("SELECT concept FROM stock_concept WHERE code=?", (code,))
        concepts = [r[0] for r in cur.fetchall()]
        conn.close()
        return concepts
    except Exception:
        return []


def get_sector_all(code: str) -> dict:
    """获取股票完整板块信息: 行业 + 概念"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.execute(
            "SELECT sector, sub_sector FROM stock_sector_v2 WHERE code=? AND type='industry'",
            (code,),
        )
        ind = cur.fetchone()
        cur = conn.execute("SELECT concept FROM stock_concept WHERE code=?", (code,))
        concepts = [r[0] for r in cur.fetchall()]
        conn.close()
        return {
            "industry": f"{ind[0]} > {ind[1]}" if ind else "未知",
            "concepts": concepts,
        }
    except Exception:
        return {"industry": "未知", "concepts": []}


if __name__ == "__main__":
    build()
