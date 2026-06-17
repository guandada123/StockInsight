"""HTML 报告生成 — 报告生成入口函数

从 report_html.py 拆分而来，经过多轮优化后仅保留 3 个 generate_* 入口函数：
- generate_screener_report()  — 选股结果报告
- generate_portfolio_report() — 投资组合报告
- generate_full_chain_report() — 全链路一键报告

各子模块：
- report_templates.py    — HTML 页面模板（_PAGE_HEADER / _PAGE_FOOTER）
- report_sections.py     — 报告章节构建（_build_market_overview / _build_selection_rationale）
- report_html_utils.py   — 工具函数 + 术语表
- report_cards.py        — 个股详情卡片
- report_narratives.py   — 叙述文字生成
"""

import json
import os
from datetime import datetime

import pandas as pd

from .report_cards import _stock_detail_card
from .report_html_utils import (
    REPORT_DIR,
    TERM_DEFS,
    _change_color,
    _change_sign,
    _color_for_value,
    _default_path,
    _escape_html,
    _fmt_num,
    _rating_bg_color,
    _rating_color,
    _tip,
)
from .report_sections import _build_market_overview, _build_selection_rationale
from .report_templates import _PAGE_FOOTER, _PAGE_HEADER

# ══════════════════════════════════════════════════════
# 1. 选股结果报告（增强版）
# ══════════════════════════════════════════════════════


def generate_screener_report(
    screener_result: pd.DataFrame,
    output_path: str | None = None,
    stock_details: dict | None = None,
) -> str:
    """生成选股结果 HTML 报告（含个股详情 + 选股逻辑 + 图表）"""
    if output_path is None:
        output_path = _default_path("screener")

    df = screener_result.copy()
    now = datetime.now()
    gen_time = now.strftime("%Y-%m-%d %H:%M:%S")
    stock_count = len(df)

    # ── 构建 HTML ──────────────────────────────────
    parts = [_PAGE_HEADER.format(title="每日选股池报告")]

    # 标题
    parts.append(f"""  <div class="header">
    <h1>每日选股池报告</h1>
    <div class="meta">生成时间：{gen_time} &nbsp;|&nbsp; 扫描股票：{stock_count} 只 &nbsp;|&nbsp; 数据源：新浪财经/东方财富</div>
  </div>""")

    # 市场概述（文字分析）
    parts.append(_build_market_overview(df, stock_details))

    # ── 选股逻辑说明（板块分析 + 个股选择依据）───
    if stock_details:
        rationale = _build_selection_rationale(
            df, stock_details, total_scanned=stock_count, top_n=min(10, stock_count)
        )
        if rationale:
            parts.append(rationale)

    # ── 数据表格 ──────────────────────────────────
    parts.append("""  <div class="card">
    <div class="card-title">选股结果明细</div>
    <div class="card-subtitle">按综合评分降序排列，综合评分 = 动量(25%) + 技术(25%) + 基本面(20%) + 量能(15%) + 风险(15%)</div>
    <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>序号</th>
          <th>代码</th>
          <th>综合评分</th>
          <th>评级</th>
          <th>动量分</th>
          <th>技术分</th>
          <th>基本面分</th>
          <th>量能分</th>
          <th>风险分</th>
          <th>最新价</th>
          <th>涨跌幅</th>
        </tr>
      </thead>
      <tbody>""")

    has_seq = "序号" in df.columns

    for idx, (_, row) in enumerate(df.iterrows()):
        seq = row.get("序号", idx + 1)
        code = _escape_html(row.get("代码", ""))
        name = _escape_html(row.get("名称", ""))
        score = _escape_html(row.get("综合评分", ""))
        rating = str(row.get("评级", ""))
        mom = _escape_html(row.get("动量分", ""))
        tech = _escape_html(row.get("技术分", ""))
        fund = _escape_html(row.get("基本面分", ""))
        vol = _escape_html(row.get("量能分", ""))
        risk = _escape_html(row.get("风险分", ""))
        price = _escape_html(row.get("最新价", ""))
        change_val = row.get("涨跌幅", 0)

        r_color = _rating_color(rating)
        r_bg = _rating_bg_color(rating)
        ch_color = _change_color(change_val)
        ch_str = _change_sign(change_val)

        parts.append(f"""        <tr>
          <td>{seq}</td>
          <td><strong>{code}</strong><br><span style="font-size:11px;color:#888">{name}</span></td>
          <td style="font-weight:600;color:{_color_for_value(score)}">{score}</td>
          <td><span class="rating-badge" style="color:{r_color};background:{r_bg}">{rating}</span></td>
          <td style="color:{_color_for_value(mom)}">{mom}</td>
          <td style="color:{_color_for_value(tech)}">{tech}</td>
          <td style="color:{_color_for_value(fund)}">{fund}</td>
          <td style="color:{_color_for_value(vol)}">{vol}</td>
          <td style="color:{_color_for_value(risk, invert=True)}">{risk}</td>
          <td>{price}</td>
          <td style="color:{ch_color};font-weight:600">{ch_str}%</td>
        </tr>""")

    parts.append("""      </tbody>
    </table>
    </div>
  </div>""")

    # ── 个股分析详情（仅显示有完整数据的股票）───────
    if stock_details:
        detail_codes = [
            code
            for code in df["代码"].astype(str).str.zfill(6).tolist()
            if code in stock_details and stock_details[code].get("quant_score")
        ]
        if detail_codes:
            parts.append("""  <div class="card">
    <div class="card-title">个股深度分析</div>
    <div class="card-subtitle">仅显示有完整分析数据的股票，含支撑位/压力位、止损止盈参考、技术面状态和风险指标</div>""")
            for idx, code in enumerate(detail_codes):
                row = df[df["代码"].astype(str).str.zfill(6) == code].iloc[0]
                detail = stock_details.get(code, {}).copy()
                detail["score"] = row.get("综合评分", "")
                detail["rating"] = str(row.get("评级", ""))
                detail["price"] = row.get("最新价", "")
                detail["change"] = row.get("涨跌幅", 0)
                name = row.get("名称", code)
                detail.setdefault("name", name)
                parts.append(_stock_detail_card(code, detail, idx + 1))
            parts.append("  </div>")

    # ── 雷达图：五维评分，最多前5只 ────────────────
    if stock_count > 0:
        top5 = df.head(5)
        labels_json = json.dumps(
            ["动量分", "技术分", "基本面分", "量能分", "风险分"], ensure_ascii=False
        )

        datasets = []
        for _, row in top5.iterrows():
            code = str(row.get("代码", ""))
            mom = float(row.get("动量分", 0) or 0)
            tech = float(row.get("技术分", 0) or 0)
            fund = float(row.get("基本面分", 0) or 0)
            vol = float(row.get("量能分", 0) or 0)
            risk = float(row.get("风险分", 0) or 0)
            datasets.append(
                {
                    "label": code,
                    "data": [mom, tech, fund, vol, risk],
                    "fill": True,
                }
            )

        datasets_json = json.dumps(datasets, ensure_ascii=False)

        parts.append(f"""  <div class="card">
    <div class="card-title">五维评分雷达图（前 {len(top5)} 只）</div>
    <div class="card-subtitle">动量(25%) · 技术(25%) · 基本面(20%) · 量能(15%) · 风险(15%)</div>
    <div class="chart-box">
      <canvas id="radarChart"></canvas>
    </div>
  </div>""")

        palette = [
            {"bg": "rgba(26,115,232,0.15)", "border": "rgba(26,115,232,0.9)"},
            {"bg": "rgba(219,68,55,0.15)", "border": "rgba(219,68,55,0.9)"},
            {"bg": "rgba(15,157,88,0.15)", "border": "rgba(15,157,88,0.9)"},
            {"bg": "rgba(255,193,7,0.15)", "border": "rgba(255,193,7,0.9)"},
            {"bg": "rgba(156,39,176,0.15)", "border": "rgba(156,39,176,0.9)"},
        ]

        parts.append(
            """<script>
  (function() {
    var ctx = document.getElementById('radarChart').getContext('2d');
    var labels = """
            + labels_json
            + """;
    var rawDatasets = """
            + datasets_json
            + """;
    var palette = """
            + json.dumps(palette, ensure_ascii=False)
            + """;
    var datasets = rawDatasets.map(function(ds, i) {
      var p = palette[i % palette.length];
      return {
        label: ds.label,
        data: ds.data,
        backgroundColor: p.bg,
        borderColor: p.border,
        borderWidth: 2,
        pointBackgroundColor: p.border,
        pointRadius: 3,
      };
    });
    new Chart(ctx, {
      type: 'radar',
      data: { labels: labels, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: { position: 'bottom', labels: { font: { size: 12 }, padding: 16 } },
        },
        scales: {
          r: {
            beginAtZero: true, max: 100,
            ticks: { stepSize: 20, font: { size: 10 }, backdropColor: 'transparent' },
            pointLabels: { font: { size: 12, weight: 'bold' }, color: '#333' },
            grid: { color: 'rgba(0,0,0,0.08)' },
            angleLines: { color: 'rgba(0,0,0,0.08)' },
          }
        }
      }
    });
  })();
</script>"""
        )

    else:
        parts.append("""  <div class="card">
    <div class="empty-state">
      <div class="icon">&#128200;</div>
      <p>暂无选股结果数据</p>
    </div>
  </div>""")

    # ── 评级分布饼图 + 因子对比柱状图 ─────────────
    if stock_count > 0 and stock_details:
        rating_order = ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]
        rating_counts = dict.fromkeys(rating_order, 0)
        for _, srow in df.iterrows():
            r = str(srow.get("评级", "")).strip()
            if r in rating_counts:
                rating_counts[r] += 1
            elif "Buy" in r:
                rating_counts["Buy"] += 1
            elif "Sell" in r:
                rating_counts["Sell"] += 1
        rating_labels_json = json.dumps(rating_order, ensure_ascii=False)
        rating_data_json = json.dumps([rating_counts[r] for r in rating_order], ensure_ascii=False)

        factor_labels = json.dumps(
            ["动量分", "技术分", "基本面分", "量能分", "风险分"], ensure_ascii=False
        )
        stock_ds_list = []
        top_n_chart = min(10, len(df))
        for _, srow in df.head(top_n_chart).iterrows():
            code = str(srow.get("代码", ""))
            sd = (stock_details or {}).get(code, {})
            qs = sd.get("quant_score", {})
            fs = qs.get("factor_scores", {})
            vals = [
                fs.get(k, {}).get("score", 0)
                for k in ["momentum", "technical", "fundamental", "volume", "risk"]
            ]
            if not any(v > 0 for v in vals):
                vals = [
                    float(srow.get("动量分", 0) or 0),
                    float(srow.get("技术分", 0) or 0),
                    float(srow.get("基本面分", 0) or 0),
                    float(srow.get("量能分", 0) or 0),
                    float(srow.get("风险分", 0) or 0),
                ]
            stock_ds_list.append({"label": code, "data": vals})
        stock_datasets_json = json.dumps(stock_ds_list, ensure_ascii=False)
        has_charts = json.dumps(len(stock_ds_list) > 0)

        parts.append(f"""
  <div class="chart-row">
    <div class="chart-box">
      <div class="chart-title">评级分布</div>
      <canvas id="ratingChart"></canvas>
    </div>
    <div class="chart-box">
      <div class="chart-title">因子评分对比（前 {top_n_chart} 只）</div>
      <canvas id="factorChart"></canvas>
    </div>
  </div>
<script>
(function() {{
  new Chart(document.getElementById('ratingChart'), {{
    type: 'doughnut',
    data: {{
      labels: {rating_labels_json},
      datasets: [{{
        data: {rating_data_json},
        backgroundColor: ['#2e7d32','#66bb6a','#f9a825','#ef6c00','#c62828'],
        borderWidth: 1,
      }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: true,
      plugins: {{ legend: {{ position: 'bottom', labels: {{ font: {{ size: 12 }}, padding: 16 }} }} }},
    }}
  }});
  var fctx = document.getElementById('factorChart');
  if (fctx && {has_charts}) {{
    var colors = ['#1a73e8','#db4437','#0f9d58','#f9a825','#9c27b0',
                  '#e91e63','#00bcd4','#ff5722','#607d8b','#795548'];
    new Chart(fctx, {{
      type: 'bar',
      data: {{
        labels: {factor_labels},
        datasets: {stock_datasets_json}.map(function(ds, i) {{
          return {{
            label: ds.label, data: ds.data,
            backgroundColor: colors[i % colors.length] + '33',
            borderColor: colors[i % colors.length],
            borderWidth: 2, borderRadius: 4,
          }};
        }}),
      }},
      options: {{
        responsive: true, maintainAspectRatio: true,
        plugins: {{ legend: {{ position: 'bottom', labels: {{ font: {{ size: 11 }}, padding: 12 }} }} }},
        scales: {{ y: {{ beginAtZero: true, max: 100, ticks: {{ stepSize: 20 }} }} }},
      }}
    }});
  }}
}})();
</script>""")

    # ── 术语表 ──────────────────────────────────────
    parts.append("""  <div class="card">
    <div class="card-title">专业术语说明</div>
    <div class="card-subtitle">报告中使用的专业术语解释</div>
    <div class="glossary-grid">""")
    for term, defn in TERM_DEFS.items():
        esc_defn = defn.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        parts.append(f"""      <div class="glossary-item">
        <span class="glossary-term">{term}</span>
        <span class="glossary-def">{esc_defn}</span>
      </div>""")
    parts.append("""    </div>
  </div>""")

    # ── 页脚 ──────────────────────────────────────
    parts.append(_PAGE_FOOTER.format(gen_time=gen_time))

    # ── 写出文件 ──────────────────────────────────
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))

    print(f"选股报告已生成: {output_path}")
    return output_path


# ══════════════════════════════════════════════════════
# 2. 投资组合报告（增强版）
# ══════════════════════════════════════════════════════


def generate_portfolio_report(
    portfolio_analysis: dict,
    output_path: str | None = None,
    stock_details: dict | None = None,
) -> str:
    """生成投资组合 HTML 报告（含个股详情）"""
    if output_path is None:
        output_path = _default_path("portfolio")

    now = datetime.now()
    gen_time = now.strftime("%Y-%m-%d %H:%M:%S")

    analysis = portfolio_analysis
    stocks = analysis.get("stocks", []) or []

    name = analysis.get("name", analysis.get("组合名称", "未命名组合"))
    total_val = analysis.get("total_value", 0)
    total_cost = analysis.get("total_cost", 0)
    total_ret = analysis.get("total_return_pct", 0)
    vol = analysis.get("portfolio_volatility_pct", 0)
    sharpe_val = analysis.get("portfolio_sharpe", None)
    stock_count = analysis.get("stock_count", len(stocks))

    # ── 构建 HTML ──────────────────────────────────
    parts = [_PAGE_HEADER.format(title=f"组合报告 - {name}")]

    # 标题
    parts.append(f"""  <div class="header">
    <h1>{name} - 投资组合报告</h1>
    <div class="meta">生成时间：{gen_time} &nbsp;|&nbsp; 持股数量：{stock_count} 只</div>
  </div>""")

    # ── 概览卡片 ──────────────────────────────────
    ret_color = "green" if total_ret >= 0 else "red"
    ret_sign = "+" if total_ret >= 0 else ""
    sharpe_str = f"{sharpe_val:.2f}" if sharpe_val is not None else "-"

    # 组合评价文字
    portfolio_commentary = []
    if sharpe_val is not None:
        if sharpe_val >= 1:
            portfolio_commentary.append("夏普比率大于1，风险调整后收益表现优秀")
        elif sharpe_val >= 0.5:
            portfolio_commentary.append("夏普比率适中，风险收益平衡")
        elif sharpe_val > 0:
            portfolio_commentary.append("夏普比率为正，组合具备一定的风险调整收益")
        else:
            portfolio_commentary.append("夏普比率为负，组合收益未能覆盖风险")

    if vol > 30:
        portfolio_commentary.append(f"组合波动率较高({vol:.1f}%)，建议关注仓位控制")
    elif vol > 20:
        portfolio_commentary.append(f"组合波动率中等({vol:.1f}%)，风险可控")
    else:
        portfolio_commentary.append(f"组合波动率较低({vol:.1f}%)，风格偏稳健")

    if total_ret > 10:
        portfolio_commentary.append(f"组合累计收益{total_ret:.1f}%，表现良好")
    elif total_ret < 0:
        portfolio_commentary.append(f"组合累计亏损{abs(total_ret):.1f}%，需审视持仓")

    parts.append(f"""  <div class="stat-grid">
    <div class="stat-card">
      <div class="label">总市值</div>
      <div class="value">{_fmt_num(total_val)}</div>
    </div>
    <div class="stat-card">
      <div class="label">总收益</div>
      <div class="value {ret_color}">{ret_sign}{_fmt_num(total_ret, suffix="%")}</div>
    </div>
    <div class="stat-card">
      <div class="label">组合波动率</div>
      <div class="value">{_fmt_num(vol, suffix="%")}</div>
    </div>
    <div class="stat-card">
      <div class="label">夏普比率</div>
      <div class="value">{sharpe_str}</div>
    </div>
    <div class="stat-card">
      <div class="label">持股数</div>
      <div class="value">{stock_count}</div>
    </div>
  </div>""")

    # 组合评价卡片
    parts.append("""  <div class="card">
    <div class="card-title">组合评估</div>""")
    if portfolio_commentary:
        for line in portfolio_commentary:
            parts.append(f'    <p style="font-size:13px;color:#555;line-height:1.8;">• {line}</p>')
    # 调仓建议
    rebal = analysis.get("rebalance_suggestions")
    if rebal:
        parts.append(
            '    <div style="margin-top:12px;padding:10px 14px;background:#fff8e1;border-radius:8px;">'
        )
        parts.append('      <p style="font-size:13px;font-weight:600;color:#f57f17;">调仓建议</p>')
        for s in rebal:
            parts.append(f'      <p style="font-size:12px;color:#555;line-height:1.6;">• {s}</p>')
        parts.append("    </div>")
    parts.append("  </div>")

    # ── 图表区域：评级分布 + 因子对比 ──────────────────────────
    if stocks:
        rating_order = ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]
        rating_counts = dict.fromkeys(rating_order, 0)
        for s in stocks:
            r = str(s.get("评级", ""))
            if r in rating_counts:
                rating_counts[r] += 1

        factor_labels = json.dumps(
            ["动量分", "技术分", "基本面分", "量能分", "风险分"], ensure_ascii=False
        )
        stock_ds_list = []
        for s in stocks[:5]:
            code = str(s.get("代码", ""))
            sd = (stock_details or {}).get(code, {})
            qs = sd.get("quant_score", {})
            fs = qs.get("factor_scores", {})
            vals = [
                fs.get(k, {}).get("score", 0)
                for k in ["momentum", "technical", "fundamental", "volume", "risk"]
            ]
            if any(v > 0 for v in vals):
                stock_ds_list.append({"label": code, "data": vals})
        stock_datasets_json = json.dumps(stock_ds_list, ensure_ascii=False)

        rating_labels_json = json.dumps(rating_order, ensure_ascii=False)
        rating_data_json = json.dumps([rating_counts[r] for r in rating_order], ensure_ascii=False)

        parts.append(f"""
  <div class=\"chart-row\">
    <div class=\"chart-box\">
      <div class=\"chart-title\">评级分布</div>
      <canvas id=\"ratingChart\"></canvas>
    </div>
    <div class=\"chart-box\">
      <div class=\"chart-title\">因子评分对比</div>
      <canvas id=\"factorChart\"></canvas>
    </div>
  </div>
<script>
(function() {{
  new Chart(document.getElementById('ratingChart'), {{
    type: 'doughnut',
    data: {{
      labels: {rating_labels_json},
      datasets: [{{
        data: {rating_data_json},
        backgroundColor: ['#2e7d32','#66bb6a','#f9a825','#ef6c00','#c62828'],
        borderWidth: 1,
      }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: true,
      plugins: {{ legend: {{ position: 'bottom', labels: {{ font: {{ size: 11 }}, padding: 12 }} }} }}
    }}
  }});
  var fctx = document.getElementById('factorChart');
  if (fctx && {stock_datasets_json}.length > 0) {{
    var colors = ['rgba(26,115,232,0.8)','rgba(219,68,55,0.8)','rgba(15,157,88,0.8)','rgba(255,193,7,0.8)','rgba(156,39,176,0.8)'];
    new Chart(fctx, {{
      type: 'bar',
      data: {{
        labels: {factor_labels},
        datasets: {stock_datasets_json}.map(function(ds, i) {{
          return {{ label: ds.label, data: ds.data, backgroundColor: colors[i % colors.length], borderRadius: 4 }};
        }})
      }},
      options: {{
        responsive: true, maintainAspectRatio: true,
        plugins: {{ legend: {{ position: 'bottom', labels: {{ font: {{ size: 11 }}, padding: 12 }} }} }},
        scales: {{ y: {{ beginAtZero: true, max: 100, ticks: {{ stepSize: 20 }} }} }}
      }}
    }});
  }}
}})();
</script>""")

    # ── 持仓明细表
    parts.append("""  <div class="card">
    <div class="card-title">持仓明细</div>
    <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>代码</th>
          <th>名称</th>
          <th>仓位(%)</th>
          <th>成本价</th>
          <th>现价</th>
          <th>收益率(%)</th>
          <th>贡献度(%)</th>
          <th>评分</th>
          <th>评级</th>
        </tr>
      </thead>
      <tbody>""")

    if stocks:
        for s in stocks:
            code = _escape_html(s.get("代码", ""))
            sname = _escape_html(s.get("名称", s.get("name", "")))
            weight = s.get("仓位%", s.get("仓位", ""))
            cost = s.get("成本价", s.get("成本", ""))
            price = s.get("现价", "")
            ret_s = s.get("收益率%", s.get("收益率", 0))
            contrib = s.get("贡献度%", s.get("贡献度", ""))
            score = s.get("评分", "")
            rating = str(s.get("评级", ""))

            ret_color_s = "#d32f2f" if (float(ret_s) if ret_s else 0) >= 0 else "#2e7d32"
            contrib_color = "#d32f2f" if (float(contrib) if contrib else 0) >= 0 else "#2e7d32"
            r_color = _rating_color(rating)
            r_bg = _rating_bg_color(rating)

            parts.append(f"""        <tr>
          <td><strong>{code}</strong></td>
          <td style="font-size:12px;color:#888">{sname}</td>
          <td>{_fmt_num(weight)}</td>
          <td>{_fmt_num(cost)}</td>
          <td>{_fmt_num(price)}</td>
          <td style="color:{ret_color_s};font-weight:600">{_change_sign(ret_s)}%</td>
          <td style="color:{contrib_color}">{_fmt_num(contrib)}</td>
          <td style="color:{_color_for_value(score)}">{_fmt_num(score, suffix="")}</td>
          <td><span class="rating-badge" style="color:{r_color};background:{r_bg}">{rating}</span></td>
        </tr>""")
    else:
        parts.append("""        <tr>
          <td colspan="9" style="color:#999;padding:32px;text-align:center;">暂无持仓数据</td>
        </tr>""")

    parts.append("""      </tbody>
    </table>
    </div>
  </div>""")

    # ── 个股分析详情 ──────────────────────────────
    if stock_details and stocks:
        parts.append("""  <div class="card">
    <div class="card-title">持仓个股深度分析</div>
    <div class="card-subtitle">每只股票的支撑位/压力位、止损止盈参考、技术面状态和风险指标</div>""")
        for s in stocks:
            code = str(s.get("代码", ""))
            detail = stock_details.get(code, {})
            detail.setdefault("name", s.get("名称", s.get("name", code)))
            detail["score"] = s.get("评分", "")
            detail["rating"] = str(s.get("评级", ""))
            detail["price"] = s.get("现价", "")
            parts.append(_stock_detail_card(code, detail))
        parts.append("  </div>")

    # ── 术语表 ──────────────────────────────────────
    parts.append("""  <div class="card">
    <div class="card-title">专业术语说明</div>
    <div class="card-subtitle">报告中使用的专业术语解释</div>
    <div class="glossary-grid">""")
    for term, defn in TERM_DEFS.items():
        esc_defn = defn.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        parts.append(f"""      <div class="glossary-item">
        <span class="glossary-term">{term}</span>
        <span class="glossary-def">{esc_defn}</span>
      </div>""")
    parts.append("""    </div>
  </div>""")

    # ── 页脚 ──────────────────────────────────────
    parts.append(_PAGE_FOOTER.format(gen_time=gen_time))

    # ── 写出文件 ──────────────────────────────────
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))

    print(f"组合报告已生成: {output_path}")
    return output_path


# ══════════════════════════════════════════════════════
# 3. 全链路一键报告
# ══════════════════════════════════════════════════════


def generate_full_chain_report(
    top_n: int = 5,
    output_path: str | None = None,
    mode: str = "quick",
) -> str:
    """一键生成全链路报告：选股 → 分析 → 组合 → 报告

    自动运行选股池、对每只股票进行完整技术分析和量化评分，
    构建等权重组合，生成包含所有详细分析的综合 HTML 报告。
    """
    if output_path is None:
        output_path = _default_path("fullchain")

    import numpy as np

    from stock_analyzer.analysis import (
        calc_stop_levels,
        calc_support_resistance,
        full_technical_analysis,
        get_technical_summary,
    )
    from stock_analyzer.cache import cached_fundamentals, cached_kline, cached_stock_news
    from stock_analyzer.portfolio import analyze_portfolio, create_portfolio
    from stock_analyzer.quant import (
        calc_risk_metrics,
        composite_quant_score,
        consolidate_signals,
        evaluate_trading_style,
        generate_all_signals,
    )
    from stock_analyzer.screener import run_screener
    from stock_analyzer.sectors_fallback import get_sector_for_code

    now = datetime.now()
    gen_time = now.strftime("%Y-%m-%d %H:%M:%S")

    # 1. 选股
    pool = run_screener(top_n=0, mode=mode)

    if pool.empty:
        parts = [_PAGE_HEADER.format(title="全链路报告")]
        parts.append(f"""  <div class="header">
    <h1>全链路分析报告</h1>
    <div class="meta">生成时间：{gen_time}</div>
  </div>""")
        parts.append("""  <div class="card">
    <div class="empty-state"><div class="icon">&#9888;</div><p>选股池为空，无法生成报告</p></div>
  </div>""")
        parts.append(_PAGE_FOOTER.format(gen_time=gen_time))
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(parts))
        return output_path

    # 2. 对每只股票做完整分析
    stock_details = {}
    portfolio_stocks = []

    for _, row in pool.head(top_n).iterrows():
        code = str(row.get("代码", ""))
        name = str(row.get("名称", code))
        price = float(row.get("最新价", 0))

        try:
            kline = cached_kline(code, days=120)
            kline = full_technical_analysis(kline)

            tech_summary = get_technical_summary(kline)
            sr = calc_support_resistance(kline)
            atr_val = kline.iloc[-1].get("ATR", np.nan) if "ATR" in kline.columns else np.nan
            stop = calc_stop_levels(
                price,
                atr_val,
                sr["支撑位"][0] if sr["支撑位"] else None,
                sr["压力位"][0] if sr["压力位"] else None,
            )
            risk = calc_risk_metrics(kline)
            signals = consolidate_signals(generate_all_signals(kline))

            # 基本面 & 量化评分 & 短线/长线评估
            fundamentals = cached_fundamentals(code)
            quant_score = composite_quant_score(kline, fundamentals)
            trading_style = evaluate_trading_style(kline, fundamentals, risk)
            sector = get_sector_for_code(code)

            # 获取新闻和舆情
            news = cached_stock_news(code)
            news_headlines = news["标题"].head(3).tolist() if "标题" in news.columns else []
            news_summaries = news["摘要"].head(3).tolist() if "摘要" in news.columns else []
            news_times = news["时间"].head(3).tolist() if "时间" in news.columns else []
            news_sources = news["来源"].head(3).tolist() if "来源" in news.columns else []

            stock_details[code] = {
                "name": name,
                "sector": sector,
                "quant_score": quant_score,
                "trading_style": trading_style,
                "support_resistance": sr,
                "stop_levels": stop,
                "technical_summary": tech_summary,
                "risk_metrics": risk,
                "signals": signals,
                "fundamentals": fundamentals,
                "news_headlines": news_headlines,
                "news_summaries": news_summaries,
                "news_times": news_times,
                "news_sources": news_sources,
            }
        except Exception:
            stock_details[code] = {
                "name": name,
                "sector": get_sector_for_code(code),
            }

        portfolio_stocks.append({"code": code, "weight": 1.0 / top_n, "cost": price})

    # 3. 创建组合
    p = create_portfolio("全链路精选组合", portfolio_stocks)
    pr = analyze_portfolio(p)

    # 4. 生成组合报告
    generate_portfolio_report(pr, output_path, stock_details)

    # 5. 注入选股逻辑说明（板块分析 + 个股选择依据）
    total_scanned = 4405 if mode == "full" else 29
    rationale_html = _build_selection_rationale(
        pool, stock_details, total_scanned=total_scanned, top_n=top_n
    )
    if rationale_html:
        with open(output_path, encoding="utf-8") as f:
            content = f.read()
        marker = '<div class="stat-grid">'
        inject_pos = content.find(marker)
        if inject_pos >= 0:
            content = content[:inject_pos] + rationale_html + "\n\n" + content[inject_pos:]
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)

    print(f"全链路报告已生成: {output_path}")
    return output_path
