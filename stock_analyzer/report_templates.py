"""HTML 报告生成 — HTML 页面模板

从 report_generators.py 拆分而来，包含页面骨架模板常量。
"""

# ── HTML 模板骨架 ────────────────────────────────────

_PAGE_HEADER = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                 "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
    background: #f0f2f5; color: #333; padding: 20px;
  }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  .header {{
    background: linear-gradient(135deg, #1a73e8, #1557b0);
    color: #fff; padding: 28px 32px; border-radius: 12px;
    margin-bottom: 24px; box-shadow: 0 4px 20px rgba(26,115,232,0.25);
  }}
  .header h1 {{ font-size: 24px; font-weight: 600; }}
  .header .meta {{ font-size: 13px; opacity: 0.85; margin-top: 6px; }}

  .card {{
    background: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    padding: 20px 24px; margin-bottom: 20px; overflow: hidden;
  }}
  .card-title {{
    font-size: 16px; font-weight: 600; color: #1a73e8;
    margin-bottom: 16px; padding-bottom: 10px;
    border-bottom: 2px solid #e8edf3;
  }}
  .card-subtitle {{
    font-size: 13px; color: #888; margin-top: -10px; margin-bottom: 16px; line-height: 1.6;
  }}

  /* 概览卡片网格 */
  .stat-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 16px; margin-bottom: 20px;
  }}
  .stat-card {{
    background: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    padding: 18px 16px; text-align: center;
  }}
  .stat-card .label {{ font-size: 12px; color: #888; margin-bottom: 4px; }}
  .stat-card .value {{ font-size: 22px; font-weight: 700; color: #1a73e8; }}
  .stat-card .value.green {{ color: #2e7d32; }}
  .stat-card .value.red {{ color: #d32f2f; }}

  /* 表格 */
  .table-wrap {{
    overflow-x: auto; margin: 0 -4px;
  }}
  table {{
    width: 100%; border-collapse: collapse; font-size: 13px;
    min-width: 680px;
  }}
  thead th {{
    background: #1a73e8; color: #fff; padding: 10px 8px;
    text-align: center; font-weight: 600; white-space: nowrap;
    position: sticky; top: 0; z-index: 1;
  }}
  tbody td {{
    padding: 9px 8px; text-align: center; border-bottom: 1px solid #eee;
    white-space: nowrap;
  }}
  tbody tr:hover {{ background: #f5f8ff; }}
  .rating-badge {{
    display: inline-block; padding: 2px 10px; border-radius: 12px;
    font-size: 12px; font-weight: 600;
  }}

  /* 图表容器 */
  .chart-row {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
    gap: 20px; margin-bottom: 20px;
  }}
  .chart-box {{
    background: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    padding: 16px; position: relative;
  }}
  .chart-box .chart-title {{
    font-size: 14px; font-weight: 600; color: #333;
    margin-bottom: 10px; text-align: center;
  }}
  .chart-box canvas {{ width: 100% !important; height: auto !important; max-height: 360px; }}

  /* 个股详情卡片 */
  .stock-detail-card {{
    border: 1px solid #e8edf3;
    border-radius: 10px; margin-bottom: 16px; overflow: hidden;
  }}
  .sd-header {{
    display: flex; align-items: center; gap: 12px;
    padding: 12px 16px; background: #f8faff;
    border-bottom: 1px solid #e8edf3;
    flex-wrap: wrap;
  }}
  .sd-code {{ font-size: 15px; font-weight: 700; color: #1a73e8; }}
  .sd-name {{ font-size: 14px; color: #555; }}
  .sd-price {{ font-size: 16px; font-weight: 700; margin-left: auto; }}
  .sd-change {{ font-size: 13px; font-weight: 600; }}
  .sd-score {{ font-size: 14px; font-weight: 700; }}
  .sd-body {{ padding: 14px 16px; }}
  .sd-section {{ margin-bottom: 12px; }}
  .sd-section:last-child {{ margin-bottom: 0; }}
  .sd-section-title {{
    font-size: 12px; font-weight: 600; color: #1a73e8;
    margin-bottom: 8px; padding-bottom: 4px;
    border-bottom: 1px dashed #e8edf3;
  }}
  .sd-info-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 6px;
  }}
  .sd-info-item {{
    padding: 4px 8px; background: #f8faff; border-radius: 6px;
    display: flex; flex-direction: column;
  }}
  .sd-label {{ font-size: 11px; color: #888; }}
  .sd-value {{ font-size: 13px; font-weight: 600; color: #333; }}
  .sd-value.sd-bullish {{ color: #d32f2f; }}
  .sd-value.sd-bearish {{ color: #2e7d32; }}
  .sd-value.sd-warning {{ color: #d32f2f; }}
  .sd-value.sd-oversold {{ color: #2e7d32; }}
  .sd-tech-comment, .sd-sl-comment {{
    font-size: 12px; color: #666; margin-top: 6px;
    padding: 6px 10px; background: #fafafa; border-radius: 6px;
    line-height: 1.6;
  }}
  .sd-levels-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 6px;
  }}
  .sd-sector {{
    font-size: 11px; color: #fff; background: #1a73e8; padding: 2px 8px;
    border-radius: 10px; font-weight: 500;
  }}
  .sd-style-badge {{
    font-size: 11px; color: #fff; padding: 2px 10px; border-radius: 10px;
    font-weight: 600;
  }}
  .nt-badge {{
    font-size: 11px; color: #b8860b; background: #fff8e1; padding: 2px 10px; border-radius: 10px;
    font-weight: 600; border: 1px solid #f0d060; cursor: help;
  }}
  .sd-news-list {{
    display: flex; flex-direction: column; gap: 8px; margin-top: 4px;
  }}
  .news-item {{
    padding: 8px 10px; background: #f8f9ff; border-radius: 6px;
    border-left: 3px solid #1a73e8;
  }}
  .news-title {{ font-size: 13px; color: #333; line-height: 1.5; }}
  .news-meta {{ font-size: 11px; color: #999; margin-top: 3px; }}
  .sd-ts-grid {{
    display: grid; gap: 10px; margin-bottom: 8px;
  }}
  .sd-ts-item {{
    display: flex; flex-direction: column; gap: 4px;
  }}
  .sd-ts-label {{
    display: flex; justify-content: space-between; font-size: 13px;
  }}
  .sd-ts-score {{ font-weight: 700; font-size: 15px; }}
  .sd-ts-bar {{
    height: 8px; background: #eee; border-radius: 4px; overflow: hidden;
  }}
  .sd-ts-bar-fill {{
    height: 100%; border-radius: 4px; transition: width 0.3s ease;
  }}
  .sd-ts-confidence {{
    font-size: 12px; color: #666; margin-bottom: 6px;
  }}
  .sd-ts-basis {{
    font-size: 12px; color: #444; line-height: 1.7; margin-bottom: 4px;
    padding: 6px 10px; background: #f8faff; border-radius: 6px;
  }}

  /* 操作建议 */
  .sd-advice-grid {{
    display: flex; gap: 12px; flex-wrap: wrap; margin-top: 6px;
  }}
  .sd-advice-item {{
    flex: 1; min-width: 220px; border: 1px solid #e8e8e8;
    border-radius: 8px; overflow: hidden; background: #fff;
  }}
  .sd-advice-header {{
    display: flex; align-items: center; gap: 6px;
    padding: 8px 10px; font-size: 13px; font-weight: 600;
  }}
  .sd-advice-icon {{ font-size: 15px; }}
  .sd-advice-score {{
    margin-left: auto; font-size: 11px; font-weight: 400;
    background: #f5f5f5; padding: 1px 8px; border-radius: 10px;
  }}
  .sd-advice-body {{
    padding: 8px 10px 10px;
  }}
  .sd-advice-conclusion {{
    font-size: 13px; line-height: 1.7; color: #333;
  }}
  .sd-advice-note {{
    font-size: 12px; line-height: 1.6; color: #666;
    margin-top: 6px; padding: 6px 8px; background: #fafafa;
    border-radius: 4px; border-left: 2px solid #ddd;
  }}
  .sd-level-item {{
    padding: 6px 8px; background: #f8faff; border-radius: 6px;
    text-align: center;
  }}
  .sd-level-label {{ font-size: 11px; color: #888; display: block; }}
  .sd-level-value {{ font-size: 13px; font-weight: 600; color: #333; }}

  /* 术语悬停提示 */
  .term-t {{
    cursor: help; border-bottom: 1px dashed #1a73e8; position: relative;
    display: inline-block;
  }}
  .term-t-popup {{
    visibility: hidden; opacity: 0; transition: opacity 0.2s, visibility 0.2s;
    position: absolute; bottom: calc(100% + 6px); left: 50%; transform: translateX(-50%);
    background: #333; color: #fff; font-size: 12px; line-height: 1.5;
    padding: 8px 12px; border-radius: 8px; width: 240px; z-index: 100;
    text-align: left; font-weight: 400; box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    pointer-events: none;
  }}
  .term-t-popup::after {{
    content: ''; position: absolute; top: 100%; left: 50%; transform: translateX(-50%);
    border: 6px solid transparent; border-top-color: #333;
  }}
  .term-t:hover .term-t-popup {{
    visibility: visible; opacity: 1;
  }}
  .sd-info-item:hover {{ box-shadow: 0 1px 4px rgba(26,115,232,0.15); transition: box-shadow 0.15s; }}

  /* 空状态 */
  .empty-state {{
    text-align: center; padding: 48px 24px; color: #999;
  }}
  .empty-state .icon {{ font-size: 48px; margin-bottom: 12px; }}

  /* 免责声明 */
  .disclaimer {{
    background: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    padding: 18px 24px; margin-top: 20px;
  }}
  .disclaimer p {{
    font-size: 12px; color: #999; line-height: 1.8; margin: 0;
  }}

  /* 市场概述 */
  .market-overview {{
    background: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    padding: 18px 24px; margin-bottom: 20px; line-height: 1.8;
  }}
  .market-overview h3 {{ font-size: 15px; color: #1a73e8; margin-bottom: 8px; }}
  .market-overview p {{ font-size: 13px; color: #555; }}

  /* 术语表 */
  .glossary-grid {{
    display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 10px; margin-top: 8px;
  }}
  .glossary-item {{
    padding: 10px 12px; background: #f8faff; border-radius: 8px;
    border-left: 3px solid #1a73e8; transition: background 0.15s;
  }}
  .glossary-item:hover {{ background: #eef3fc; }}
  .glossary-term {{
    font-size: 13px; font-weight: 700; color: #1a73e8;
    display: block; margin-bottom: 3px;
  }}
  .glossary-def {{
    font-size: 12px; color: #555; line-height: 1.6; display: block;
  }}

  /* 叙述文字 */
  .sd-narrative {{
    padding: 14px 16px; background: #fafcff; border-radius: 8px;
    margin-bottom: 14px; border: 1px solid #e8edf3;
  }}
  .narrative-block p {{
    font-size: 13px; line-height: 1.9; color: #444; margin-bottom: 8px;
  }}
  .narrative-block p:last-child {{ margin-bottom: 0; }}
  .n-subtitle {{
    font-size: 13px; font-weight: 700; color: #1a73e8;
    margin-bottom: 4px; margin-top: 10px;
  }}
  .n-subtitle:first-child {{ margin-top: 0; }}

  /* 核心观点高亮 */
  .key-finding {{
    padding: 12px 16px; border-radius: 8px; margin: 10px 0;
    font-size: 13px; line-height: 1.8;
  }}
  .key-finding.positive {{ background: #e8f5e9; border-left: 4px solid #2e7d32; color: #1b5e20; }}
  .key-finding.negative {{ background: #ffebee; border-left: 4px solid #c62828; color: #b71c1c; }}
  .key-finding.neutral {{ background: #fff8e1; border-left: 4px solid #f9a825; color: #795548; }}
  .kf-label {{ font-weight: 700; display: block; margin-bottom: 2px; font-size: 12px; }}

  /* 速览统计 */
  .glance-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
    gap: 10px; margin-bottom: 16px;
  }}
  .glance-item {{
    background: #fff; border-radius: 8px; padding: 12px 10px;
    text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  }}
  .glance-value {{ font-size: 20px; font-weight: 700; color: #1a73e8; }}
  .glance-value.green {{ color: #2e7d32; }}
  .glance-value.red {{ color: #d32f2f; }}
  .glance-label {{ font-size: 11px; color: #888; margin-top: 2px; }}

  /* 评分模型展示 */
  .model-factor-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 10px; margin: 12px 0;
  }}
  .model-factor {{
    padding: 10px 12px; background: #f8faff; border-radius: 8px;
    border-top: 3px solid #1a73e8;
  }}
  .model-factor .mf-header {{
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;
  }}
  .model-factor .mf-name {{ font-size: 13px; font-weight: 700; color: #333; }}
  .model-factor .mf-weight {{ font-size: 11px; color: #1a73e8; font-weight: 600; }}
  .model-factor .mf-desc {{ font-size: 12px; color: #666; line-height: 1.6; }}
  .mf-bar {{ height: 4px; background: #e8edf3; border-radius: 2px; margin-top: 6px; overflow: hidden; }}
  .mf-bar-fill {{ height: 100%; border-radius: 2px; }}

  @media (max-width: 640px) {{
    body {{ padding: 12px; }}
    .header {{ padding: 18px 16px; }}
    .card {{ padding: 14px 16px; }}
    .stat-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .chart-row {{ grid-template-columns: 1fr; }}
    .sd-header {{ gap: 6px; }}
  }}
</style>
</head>
<body>
<div class="container">
"""

_PAGE_FOOTER = r"""
  <div class="disclaimer">
    <p><strong>免责声明：</strong>
    本报告由 AI 自动生成，数据来源于公开市场信息，仅供参考，不构成任何投资建议或投资承诺。
    投资有风险，入市需谨慎。过往表现不代表未来收益。<br>
    报告生成时间：{gen_time} &nbsp;|&nbsp; AI 工具：Claude Code</p>
  </div>
</div>
</body>
</html>"""
