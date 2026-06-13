"""构建板块数据库 — Baostock 全量行业分类 + 静态精准板块映射

数据源:
  1. Baostock query_stock_industry() → 5527只A股证监会行业分类
  2. sectors_fallback 静态映射 → 更精准的交易板块名(半导体/白酒/光伏等)

优先级: 静态映射 > Baostock行业 (静态更贴近实际交易板块)
"""

import os
import sqlite3

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stock_cache.db"
)


def build():
    from .sectors_fallback import SECTOR_STOCKS_FALLBACK

    print("构建板块数据库...")

    # 1. Baostock 全量行业分类
    print("  1/2 从 Baostock 获取行业分类...")
    import baostock as bs

    bs.login()
    rs = bs.query_stock_industry()
    baostock_map = {}  # code → industry_name
    while rs.next():
        r = rs.get_row_data()
        code = r[1].replace("sh.", "").replace("sz.", "")
        industry = r[3]  # 行业代码+名称: "J66货币金融服务"
        if code and industry:
            # 清理：去掉字母数字前缀和开头的符号
            clean = industry.lstrip(
                "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz、 "
            )
            baostock_map[code] = clean
    bs.logout()
    print(f"     Baostock: {len(baostock_map)} 只")

    # 2. 静态精准映射
    print("  2/2 叠加静态精准板块映射...")
    static_count = 0
    for sector_name, info in SECTOR_STOCKS_FALLBACK.items():
        for code in info.get("成分股", []):
            if code in baostock_map:
                baostock_map[code] = sector_name
                static_count += 1
    print(f"     静态覆盖: {static_count} 只")

    # 3. 存入 SQLite
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_sector (
            code TEXT PRIMARY KEY,
            sector TEXT NOT NULL,
            source TEXT DEFAULT 'baostock'
        )
    """)
    conn.execute("DELETE FROM stock_sector")
    rows = [
        (
            code,
            sector,
            "static"
            if any(code in info.get("成分股", []) for info in SECTOR_STOCKS_FALLBACK.values())
            else "baostock",
        )
        for code, sector in baostock_map.items()
    ]
    conn.executemany("INSERT INTO stock_sector VALUES (?, ?, ?)", rows)
    conn.commit()

    cur = conn.execute("SELECT COUNT(*), source FROM stock_sector GROUP BY source")
    for cnt, src in cur.fetchall():
        print(f"     {src}: {cnt} 只")
    conn.close()

    print(f"  完成: {len(baostock_map)} 只股票板块已入库")
    return len(baostock_map)


def get_sector_from_db(code: str) -> str:
    """从数据库查询板块（毫秒级）"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.execute("SELECT sector FROM stock_sector WHERE code=?", (code,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else "其他"
    except Exception:
        return "其他"


if __name__ == "__main__":
    build()
