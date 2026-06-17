"""HTML 报告生成模块 — 再导出包装器

此文件是 report_html.py 4 模块拆分的兼容性包装器，
保持对 `from stock_analyzer.report_html import generate_screener_report` 等旧导入的兼容。

拆分后的 4 个模块：
  - report_html_utils.py  — 工具函数与术语常量
  - report_narratives.py  — 叙述文字生成函数
  - report_cards.py       — 个股详情卡片
  - report_generators.py  — 报告生成器函数和 HTML 模板
"""

from .report_generators import (
    generate_full_chain_report,
    generate_portfolio_report,
    generate_screener_report,
)
from .report_html_utils import REPORT_DIR, TERM_DEFS

__all__ = [
    "generate_screener_report",
    "generate_portfolio_report",
    "generate_full_chain_report",
    "REPORT_DIR",
    "TERM_DEFS",
]
