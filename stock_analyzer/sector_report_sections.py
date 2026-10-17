"""板块分析报告的章节构建函数（2026-10-18 从 sector_report.py 拆出）

生成 HTML 片段供 `sector_report.generate_sector_report` 编排器拼接。
拆分原则：本模块**只做纯拼装**，不含外部 IO 调用（run_screener /
get_sector_for_code / cached_market_overview 的调用留在 sector_report.py
—— 测试 patch 的是该模块属性，迁走会失效）。
唯一例外：板块资金流保持在函数体内惰性 `from .cache import ...`，
这是 21 个用例 patch `stock_analyzer.cache.*` 的前提。
"""

from typing import Any

import numpy as np

_FACTOR_KEYS = ["动量分", "技术分", "基本面分", "量能分", "风险分"]

_FACTOR_DISPLAY_CN = {
    "动量分": "动量",
    "技术分": "技术",
    "基本面分": "基本面",
    "量能分": "量能",
    "风险分": "风险",
}

_FACTOR_COLORS = {
    "动量分": "#1a73e8",
    "技术分": "#e65100",
    "基本面分": "#2e7d32",
    "量能分": "#6a1b9a",
    "风险分": "#f9a825",
}


def _sector_stat_rows(sector_data: dict[str, dict]) -> list[tuple]:
    """板块聚合统计行：(名称, 数量, 均分, 中位, 标准差, 优质数, 偏低数, 因子均值)"""
    rows = []
    for s_name, s_info in sector_data.items():
        avg_score = np.mean(s_info["scores"]) if s_info["scores"] else 0
        med_score = np.median(s_info["scores"]) if s_info["scores"] else 0
        std_score = np.std(s_info["scores"]) if len(s_info["scores"]) > 1 else 0
        high_cnt = sum(1 for s in s_info["scores"] if s >= 60)
        low_cnt = sum(1 for s in s_info["scores"] if s < 40)
        avg_factors = {}
        for fc in _FACTOR_KEYS:
            fa = s_info["factors"][fc]
            avg_factors[fc] = np.mean(fa) if fa else 0
        rows.append(
            (
                s_name,
                s_info["count"],
                avg_score,
                med_score,
                std_score,
                high_cnt,
                low_cnt,
                avg_factors,
            )
        )
    return rows


def _count_ratings(df: Any) -> tuple[Any, dict[str, int]]:
    """评级分布：返回 (评级序列, 五档计数)"""
    ratings = df["评级"] if "评级" in df.columns else []
    rating_counts = {"Strong Buy": 0, "Buy": 0, "Hold": 0, "Sell": 0, "Strong Sell": 0}
    for r in ratings:
        r = str(r).strip()
        if r in rating_counts:
            rating_counts[r] += 1
    return ratings, rating_counts


def _build_title_block(total: int, sector_count: int, gen_time: str) -> str:
    """报告标题块"""
    return f"""  <div class="header">
    <h1>全市场板块分析报告</h1>
    <div class="meta">全市场 {total} 只成功评分，覆盖 {sector_count} 个板块 | 生成时间：{gen_time}</div>
  </div>"""


def _build_market_overview_section(
    total: int,
    sector_count: int,
    all_scores: Any,
    ratings: Any,
    rating_counts: dict[str, int],
) -> list[str]:
    """一、市场概览：关键数字 + 市场判断 + 评级分布饼图"""
    html: list[str] = []
    html.append("""  <div class="card">
    <div class="card-title">一、市场概览</div>""")

    # 关键数字
    avg_all = np.mean(all_scores) if len(all_scores) else 0
    pct_high = (
        sum(1 for s in all_scores if s >= 60) / len(all_scores) * 100 if len(all_scores) else 0
    )
    pct_low = sum(1 for s in all_scores if s < 40) / len(all_scores) * 100 if len(all_scores) else 0
    html.append(f"""    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin-bottom:12px;">
      <div style="background:#f0f7ff;border-radius:8px;padding:12px;text-align:center;"><div style="font-size:24px;font-weight:700;color:#1a73e8;">{total}</div><div style="font-size:11px;color:#666;">评分股票</div></div>
      <div style="background:#f0f7ff;border-radius:8px;padding:12px;text-align:center;"><div style="font-size:24px;font-weight:700;color:#1a73e8;">{sector_count}</div><div style="font-size:11px;color:#666;">覆盖板块</div></div>
      <div style="background:#f0f7ff;border-radius:8px;padding:12px;text-align:center;"><div style="font-size:24px;font-weight:700;color:#1a73e8;">{avg_all:.1f}</div><div style="font-size:11px;color:#666;">市场均分</div></div>
      <div style="background:#e8f5e9;border-radius:8px;padding:12px;text-align:center;"><div style="font-size:24px;font-weight:700;color:#2e7d32;">{pct_high:.0f}%</div><div style="font-size:11px;color:#666;">优质(≥60分)</div></div>
      <div style="background:#ffebee;border-radius:8px;padding:12px;text-align:center;"><div style="font-size:24px;font-weight:700;color:#c62828;">{pct_low:.0f}%</div><div style="font-size:11px;color:#666;">偏低(<40分)</div></div>
    </div>""")

    # 市场判断
    if avg_all >= 50:
        sentiment = "市场整体评分偏中性，优质标的存在结构性机会"
    elif avg_all >= 45:
        sentiment = "市场整体评分偏低，需精选个股"
    else:
        sentiment = "市场整体偏弱，建议控制仓位，等待机会"
    buy_pct = (
        (rating_counts["Buy"] + rating_counts["Strong Buy"]) / len(ratings) * 100
        if len(ratings)
        else 0
    )
    sell_pct = (
        (rating_counts["Sell"] + rating_counts["Strong Sell"]) / len(ratings) * 100
        if len(ratings)
        else 0
    )
    html.append(f"""    <p style="font-size:13px;color:#555;line-height:1.8;">
      市场平均综合评分 <strong>{avg_all:.1f}</strong> 分，{pct_high:.0f}% 评分≥60（优质），
      {pct_low:.0f}% 评分<40（偏低）。买入/强买入占比 {buy_pct:.0f}%，卖出/强卖出占比 {sell_pct:.0f}%。
      （注：全市场扫描先排除ST/退市/次新股，仅对具有足够K线数据的股票完成评分。）
      {sentiment}
    </p>""")

    # 评级分布饼图
    rc = rating_counts
    has_ratings = any(rc.values())
    if has_ratings:
        html.append(f"""    <div class="sec-title">评级分布</div>
    <div class="chart-box"><canvas id="ratingChart"></canvas></div>
    <script>
    new Chart(document.getElementById('ratingChart'), {{
      type: 'doughnut',
      data: {{
        labels: ['Strong Buy', 'Buy', 'Hold', 'Sell', 'Strong Sell'],
        datasets: [{{ data: [{rc["Strong Buy"]},{rc["Buy"]},{rc["Hold"]},{rc["Sell"]},{rc["Strong Sell"]}],
          backgroundColor: ['#2e7d32','#66bb6a','#f9a825','#ef6c00','#c62828'] }}]
      }},
      options: {{ responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ position: 'right', labels: {{ font: {{ size: 12 }} }} }} }} }}
    }});
    </script>""")
    html.append("  </div>")
    return html


def _build_ranking_table(sorted_rows: list[tuple]) -> list[str]:
    """二、板块综合排名表"""
    html: list[str] = []
    html.append("""  <div class="card">
    <div class="card-title">二、板块综合排名</div>
    <p style="font-size:13px;color:#555;line-height:1.8;margin-bottom:10px;">
      以下按平均综合评分降序排列，展示各板块的数量分布和评分特征。
      评分越高代表板块整体质地越好，标准差反映板块内部分化程度。
    </p>
    <table>
      <thead><tr>
        <th>排名</th><th style="text-align:left;">板块</th><th>个股数量</th><th>平均分</th><th>中位数</th>
        <th>标准差</th><th>优质(≥60)</th><th style="font-size:11px;">偏低(<40)</th>
      </tr></thead><tbody>""")

    # 移除死代码(2026-10-16)：原 `bar_max = max(...)` + `score_pct = avg / bar_max * 100`
    # 计算后从未被引用，却在板块均分为 0 时触发除零 RuntimeWarning（NaN 污染）。直接删除。
    for i, (name, cnt, avg, med, std, hi, lo, _) in enumerate(sorted_rows):
        rank = i + 1
        rclass = f"r{rank}" if rank <= 3 else ""
        hi_pct = hi / cnt * 100 if cnt else 0
        lo_pct = lo / cnt * 100 if cnt else 0
        html.append(f"""      <tr>
        <td>{'<span class="rank-badge ' + rclass + '">' + str(rank) + "</span>" if rank <= 3 else rank}</td>
        <td style="text-align:left;font-weight:{"600" if rank <= 3 else "400"};color:{"#1a73e8" if rank <= 3 else "#333"};">{name}</td>
        <td>{cnt}</td>
        <td style="font-weight:600;color:{"#2e7d32" if avg >= 60 else "#ef6c00" if avg < 45 else "#333"};">{avg:.1f}</td>
        <td>{med:.1f}</td>
        <td style="color:#888;font-size:11px;">{std:.1f}</td>
        <td><div class="s-bar-wrapper"><div class="s-bar" style="width:{hi_pct:.0f}%;background:#66bb6a;"></div><span class="s-bar-val">{hi}</span></div></td>
        <td><div class="s-bar-wrapper"><div class="s-bar" style="width:{lo_pct:.0f}%;background:#ef9a9a;"></div><span class="s-bar-val">{lo}</span></div></td>
      </tr>""")

    html.append("    </tbody></table>")
    html.append("  </div>")
    return html


def _build_score_bar_chart(sorted_rows: list[tuple]) -> str:
    """三、板块评分对比（Top 12）柱状图卡片"""
    top12 = sorted_rows[:12]
    return (
        """  <div class="card">
    <div class="card-title">三、板块评分对比（Top 12）</div>
    <div class="chart-box-full"><canvas id="sectorBarChart"></canvas></div>
    <script>
    new Chart(document.getElementById('sectorBarChart'), {
      type: 'bar',
      data: {
        labels: """
        + str([r[0] for r in top12]).replace("'", '"')
        + """,
        datasets: [{
          label: '平均评分',
          data: """
        + str([float(round(r[2], 1)) for r in top12])
        + """,
          backgroundColor: """
        + str(
            ["#2e7d32" if r[2] >= 60 else "#ef6c00" if r[2] < 45 else "#f9a825" for r in top12]
        ).replace("'", '"')
        + """,
          borderRadius: 4
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        indexAxis: 'y',
        scales: { x: { min: 0, max: 100, title: { display: true, text: '评分' } } },
        plugins: { legend: { display: false } }
      }
    });
    </script>
  </div>"""
    )


def _build_radar_chart(sorted_rows: list[tuple]) -> str:
    """四、板块五因子对比（Top 8）雷达图卡片"""
    top8 = sorted_rows[:8]
    return (
        """  <div class="card">
    <div class="card-title">四、板块五因子对比（Top 8）</div>
    <p style="font-size:13px;color:#555;line-height:1.8;margin-bottom:10px;">
      五个维度：动量（股价涨跌力度）、技术（MACD/RSI/KDJ）、基本面（ROE/增长/毛利率）、
      量能（成交量变化）、风险（波动率/回撤）。每条线代表一个板块。
    </p>
    <div class="chart-box-full"><canvas id="radarChart"></canvas></div>
    <script>
    new Chart(document.getElementById('radarChart'), {
      type: 'radar',
      data: {
        labels: ['动量', '技术', '基本面', '量能', '风险'],
        datasets: ["""
        + ",".join(
            '{label:"'
            + r[0]
            + '",data:['
            + ",".join(f"{r[7][fc]:.1f}" for fc in _FACTOR_KEYS)
            + "],fill:true,"
            + 'backgroundColor:"rgba('
            + str(50 + i * 20)
            + ","
            + str(100 + i * 15)
            + ","
            + str(200 - i * 15)
            + ',0.1)",'
            + 'borderColor:"rgba('
            + str(50 + i * 20)
            + ","
            + str(100 + i * 15)
            + ","
            + str(200 - i * 15)
            + ',0.8)",'
            + 'pointBackgroundColor:"rgba('
            + str(50 + i * 20)
            + ","
            + str(100 + i * 15)
            + ","
            + str(200 - i * 15)
            + ',1)"'
            + "}"
            for i, r in enumerate(top8)
        )
        + """]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        scales: { r: { min: 0, max: 100, ticks: { stepSize: 20 } } },
        plugins: { legend: { position: 'right', labels: { font: { size: 11 } } } }
      }
    });
    </script>
  </div>"""
    )


def _build_factor_leaders(sorted_rows: list[tuple]) -> list[str]:
    """五、各因子领先板块表"""
    html: list[str] = []
    html.append("""  <div class="card">
    <div class="card-title">五、各因子领先板块</div>
    <p style="font-size:13px;color:#555;line-height:1.8;margin-bottom:10px;">
      每个维度上评分最高的板块及其得分：
    </p>
    <table><thead><tr><th>因子</th><th style="text-align:left;">领先板块</th><th>得分</th><th style="text-align:left;">说明</th></tr></thead><tbody>""")

    for fc in _FACTOR_KEYS:
        best = max(sorted_rows, key=lambda r: r[7][fc]) if sorted_rows else None
        if best:
            cn = _FACTOR_DISPLAY_CN[fc]
            descs = {
                "动量分": "反映股价近期涨跌力度，越高说明短期趋势越强",
                "技术分": "综合MACD/RSI/KDJ等指标，越高说明技术形态越好",
                "基本面分": "基于ROE/营收增长/毛利率，越高说明公司质地越优",
                "量能分": "衡量成交活跃度和量价配合，越高说明资金参与度越强",
                "风险分": "评估波动率和回撤，越高说明风险控制越好",
            }
            html.append(f"""      <tr>
        <td><span style="display:inline-block;width:12px;height:12px;border-radius:3px;background:{_FACTOR_COLORS[fc]};vertical-align:middle;margin-right:4px;"></span>{cn}</td>
        <td style="text-align:left;font-weight:600;">{best[0]}</td>
        <td style="font-weight:600;color:#1a73e8;">{best[7][fc]:.1f}</td>
        <td style="text-align:left;color:#888;font-size:12px;">{descs[fc]}</td>
      </tr>""")

    html.append("    </tbody></table>")
    html.append("  </div>")
    return html


def _build_fund_flow_section() -> list[str]:
    """五-B、板块资金流向排名（惰性 import 保持函数体内，供 cache 层 patch）"""
    html: list[str] = []
    html.append("""  <div class="card">
    <div class="card-title">五-B、板块资金流向排名（今日主力净流入）</div>
    <p style="font-size:13px;color:#555;line-height:1.8;margin-bottom:10px;">
      主力资金为大单和超大单合计（单笔≥20万元），反映机构和大资金的日内流向。
      正值=净流入（资金买入），负值=净流出（资金卖出）。
    </p>
""")
    try:
        from .cache import cached_sector_fund_flow_rank

        ff_sectors = cached_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
        if ff_sectors is not None and not ff_sectors.empty:
            # 取前20名和后10名
            ff_top = ff_sectors.head(20)
            ff_bottom = ff_sectors.tail(10)
            html.append("""    <div class="sec-title">主力净流入 Top 20</div>
    <table><thead><tr>
      <th>排名</th><th style="text-align:left;">板块</th><th>主力净流入(亿)</th><th>主力净占比</th><th>涨跌幅</th><th>最大流入股</th>
    </tr></thead><tbody>""")
            for _, r in ff_top.iterrows():
                name = r.get("名称", "")
                amount = r.get("今日主力净流入-净额", 0) or 0
                ratio = r.get("今日主力净流入-净占比", 0) or 0
                chg = r.get("今日涨跌幅", 0) or 0
                top_stock = r.get("今日主力净流入最大股", "")
                amount_yi = amount / 1e8
                color = "#d32f2f" if amount_yi > 0 else "#2e7d32"
                html.append(f"""      <tr>
                <td style="width:40px;">{r.get("序号", "")}</td>
                <td style="text-align:left;font-weight:500;">{name}</td>
                <td style="font-weight:600;color:{color};">{amount_yi:+.2f}</td>
                <td>{ratio:+.2f}%</td>
                <td style="color:{"#d32f2f" if chg > 0 else "#2e7d32"}">{chg:+.2f}%</td>
                <td style="font-size:12px;color:#555;">{top_stock}</td>
              </tr>""")
            html.append("""    </tbody></table>""")

            html.append("""    <div class="sec-title" style="margin-top:20px;">主力净流出 Top 10</div>
    <table><thead><tr>
      <th>排名</th><th style="text-align:left;">板块</th><th>主力净流入(亿)</th><th>主力净占比</th><th>涨跌幅</th><th>最大流入股</th>
    </tr></thead><tbody>""")
            for _, r in ff_bottom.iterrows():
                name = r.get("名称", "")
                amount = r.get("今日主力净流入-净额", 0) or 0
                ratio = r.get("今日主力净流入-净占比", 0) or 0
                chg = r.get("今日涨跌幅", 0) or 0
                top_stock = r.get("今日主力净流入最大股", "")
                amount_yi = amount / 1e8
                color = "#d32f2f" if amount_yi > 0 else "#2e7d32"
                html.append(f"""      <tr>
                <td style="width:40px;">{r.get("序号", "")}</td>
                <td style="text-align:left;font-weight:500;">{name}</td>
                <td style="font-weight:600;color:{color};">{amount_yi:+.2f}</td>
                <td>{ratio:+.2f}%</td>
                <td style="color:{"#d32f2f" if chg > 0 else "#2e7d32"}">{chg:+.2f}%</td>
                <td style="font-size:12px;color:#555;">{top_stock}</td>
              </tr>""")
            html.append("""    </tbody></table>""")
            html.append(
                """    <p style="font-size:11px;color:#999;margin-top:8px;">数据来源：东方财富，交易日盘中/盘后实时数据。资金流向为今日统计，可能随行情更新而变化。</p>"""
            )
        else:
            html.append(
                """    <p style="font-size:13px;color:#888;text-align:center;padding:20px;">板块资金流向数据暂不可用（可能为非交易日或接口超时）</p>"""
            )
    except Exception as e:
        html.append(
            f"""    <p style="font-size:13px;color:#888;text-align:center;padding:20px;">板块资金流向获取失败（{e}）</p>"""
        )
    html.append("  </div>")
    return html


def _build_sector_detail_table(sorted_rows: list[tuple]) -> list[str]:
    """七、板块详情总览表"""
    html: list[str] = []
    html.append("""  <div class="card">
    <div class="card-title">七、板块详情总览</div>
    <p style="font-size:13px;color:#555;line-height:1.8;margin-bottom:10px;">
      每个板块的完整评分数据，包含五因子分解。
    </p>
    <table><thead><tr>
      <th>板块</th><th>数量</th><th>均分</th><th>动量</th><th>技术</th><th>基本面</th><th>量能</th><th>风险</th>
    </tr></thead><tbody>""")

    for name, cnt, avg, med, std, hi, lo, af in sorted_rows:
        color = "#2e7d32" if avg >= 60 else "#ef6c00" if avg < 45 else "#333"
        html.append(f"""      <tr>
        <td style="text-align:left;font-weight:500;">{name}</td>
        <td>{cnt}</td>
        <td style="font-weight:600;color:{color};">{avg:.1f}</td>
        <td>{af["动量分"]:.0f}</td>
        <td>{af["技术分"]:.0f}</td>
        <td>{af["基本面分"]:.0f}</td>
        <td>{af["量能分"]:.0f}</td>
        <td>{af["风险分"]:.0f}</td>
      </tr>""")

    html.append("    </tbody></table>")
    html.append("  </div>")
    return html
