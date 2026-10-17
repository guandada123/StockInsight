"""全市场板块分析报告生成器"""

import os
from datetime import datetime
from typing import Any

import numpy as np

from stock_analyzer.cache import cached_market_overview
from stock_analyzer.screener import run_screener
from stock_analyzer.sectors_fallback import get_sector_for_code

from .sector_report_sections import (
    _FACTOR_KEYS,
    _build_factor_leaders,
    _build_fund_flow_section,
    _build_market_overview_section,
    _build_radar_chart,
    _build_ranking_table,
    _build_score_bar_chart,
    _build_sector_detail_table,
    _build_title_block,
    _count_ratings,
    _sector_stat_rows,
)

_PAGE_HEADER = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdn.bootcdn.net/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; background: #f5f7fa; color: #333; padding: 20px; }}
.container {{ max-width: 1100px; margin: 0 auto; }}
.header {{ text-align: center; padding: 24px 0 16px; }}
.header h1 {{ font-size: 22px; color: #1a73e8; }}
.header .meta {{ font-size: 12px; color: #888; margin-top: 4px; }}
.card {{ background: #fff; border-radius: 10px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 6px rgba(0,0,0,0.06); }}
.card-title {{ font-size: 16px; font-weight: 700; color: #1a73e8; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 2px solid #1a73e8; }}
.sec-title {{ font-size: 14px; font-weight: 600; color: #333; margin: 14px 0 8px; }}
.sec-title:first-child {{ margin-top: 0; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ background: #f0f4f8; padding: 8px 6px; text-align: center; font-weight: 600; color: #555; border-bottom: 2px solid #ddd; }}
td {{ padding: 7px 6px; text-align: center; border-bottom: 1px solid #eee; }}
tr:hover td {{ background: #f5f8ff; }}
.s-bar {{ display: inline-block; height: 16px; border-radius: 4px; min-width: 4px; vertical-align: middle; }}
.s-bar-wrapper {{ display: flex; align-items: center; gap: 6px; }}
.s-bar-val {{ font-size: 11px; color: #666; min-width: 28px; }}
.rank-badge {{ display: inline-block; width: 20px; height: 20px; line-height: 20px; border-radius: 50%; text-align: center; font-size: 11px; font-weight: 700; color: #fff; }}
.r1 {{ background: #c62828; }} .r2 {{ background: #ef6c00; }} .r3 {{ background: #f9a825; }}
.chart-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
@media(max-width:700px) {{ .chart-row {{ grid-template-columns: 1fr; }} }}
.chart-box {{ position: relative; height: 300px; }}
.chart-box-full {{ position: relative; height: 380px; }}
.sun-item {{ display: inline-flex; align-items: center; margin: 3px 6px; }}
.sun-dot {{ width: 10px; height: 10px; border-radius: 50%; margin-right: 4px; }}
.footer {{ text-align: center; font-size: 11px; color: #aaa; padding: 20px 0; }}
</style>
</head>
<body>
<div class="container">
"""

_PAGE_FOOTER = """</div>
<div class="footer">报告由量化分析系统自动生成，不构成投资建议 | {gen_time}</div>
</body>
</html>"""


def _collect_sector_data(df: Any) -> dict[str, dict]:
    """板块映射：股票 → 板块（多板块按顿号拆分），累计评分与五因子"""
    sector_data: dict[str, dict] = {}
    for _, row in df.iterrows():
        code = str(row.get("代码", ""))
        score = row.get("综合评分", 0)
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = 0
        s = get_sector_for_code(code)
        if s == "其他" or not s:
            s = "其他"
        for sec_name in s.split("、"):
            if sec_name not in sector_data:
                sector_data[sec_name] = {
                    "count": 0,
                    "scores": [],
                    "factors": {c: [] for c in _FACTOR_KEYS},
                }
            sector_data[sec_name]["count"] += 1
            sector_data[sec_name]["scores"].append(score)
            for fc in _FACTOR_KEYS:
                v = row.get(fc, 0)
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    v = 0
                sector_data[sec_name]["factors"][fc].append(v)
    return sector_data


def _build_market_quote_section() -> list[str]:
    """大盘行情卡片（cached_market_overview 调用与拼装同在 try 内，保持原覆盖范围）"""
    html: list[str] = []
    html.append("""  <div class="card">
    <div class="card-title">大盘行情</div>
    <p style="font-size:13px;color:#555;line-height:1.8;margin-bottom:10px;">
      主要指数实时行情：
    </p>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;">
""")
    try:
        mkt = cached_market_overview()
        if mkt:
            for code in ["000001", "399001", "399006", "000688"]:
                info = mkt.get(code)
                if info:
                    price = info.get("最新价", "-")
                    change = info.get("涨跌幅", 0)
                    name = info.get("名称", code)
                    if isinstance(change, int | float):
                        change_str = f"{change:+.2f}%"
                        color = "#c62828" if change > 0 else "#2e7d32" if change < 0 else "#333"
                    else:
                        change_str = str(change)
                        color = "#333"
                    html.append(f"""      <div style="background:#f8f9fa;border-radius:8px;padding:12px;text-align:center;">
          <div style="font-size:12px;color:#666;margin-bottom:4px;">{name}</div>
          <div style="font-size:20px;font-weight:700;">{price}</div>
          <div style="font-size:13px;font-weight:600;color:{color};">{change_str}</div>
        </div>""")
        else:
            html.append(
                """      <div style="padding:12px;text-align:center;color:#888;">大盘行情数据暂不可用</div>"""
            )
    except Exception:
        html.append(
            """      <div style="padding:12px;text-align:center;color:#888;">大盘行情数据暂不可用</div>"""
        )
    html.append("""    </div>
  </div>""")
    return html


def generate_sector_report(output_path: str | None = None) -> str:
    """全市场板块分析报告（编排器；各章节实现见 sector_report_sections.py，2026-10-18 拆分）"""
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        output_path = f"reports/sector_{ts}.html"

    print("正在扫描全市场股票...")
    df = run_screener(top_n=0, mode="full")
    total = len(df)
    print(f"  有效股票: {total} 只")

    # ── 板块映射 ──
    print("  正在计算板块分布...")
    sector_data = _collect_sector_data(df)
    sorted_rows = sorted(_sector_stat_rows(sector_data), key=lambda x: -x[2])  # by avg_score desc

    all_scores = df["综合评分"].dropna().values if "综合评分" in df.columns else []
    ratings, rating_counts = _count_ratings(df)

    # ── 开始构建HTML ──
    gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = [_PAGE_HEADER.format(title="全市场板块分析报告")]

    # 标题
    html.append(_build_title_block(total, len(sorted_rows), gen_time))

    # ── 大盘行情 ──
    html.extend(_build_market_quote_section())

    # ── 1. 市场概览 ──
    html.extend(
        _build_market_overview_section(total, len(sorted_rows), all_scores, ratings, rating_counts)
    )

    # ── 2. 板块排名 ──
    html.extend(_build_ranking_table(sorted_rows))

    # ── 3. 板块评分柱状图 ──
    html.append(_build_score_bar_chart(sorted_rows))

    # ── 4. 五因子分析 ──
    html.append(_build_radar_chart(sorted_rows))

    # ── 5.因子领先板块 ──
    html.extend(_build_factor_leaders(sorted_rows))

    # ── 5b.板块资金流向排名 ──
    html.extend(_build_fund_flow_section())

    # ── 七、板块详情总览 ──
    html.extend(_build_sector_detail_table(sorted_rows))

    # ── Footer ──
    html.append(_PAGE_FOOTER.format(gen_time=gen_time))

    # ── 写出文件 ──
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html))

    print(f"板块分析报告已生成: {output_path}")
    return output_path


if __name__ == "__main__":
    generate_sector_report()
