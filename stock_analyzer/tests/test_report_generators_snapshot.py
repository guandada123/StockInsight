"""行为快照测试：report_generators 两个报告函数（**当前零测试**）。

背景：2026-10-18 全面审计后续——generate_screener_report(338 行) 与
generate_portfolio_report(277 行) 即将拆分。二者**没有任何测试**
（实测：tests/ 下零命中；"经 generate_full_chain_report 链路测试"的说法
复核为假——该函数无任何调用方）。故本测试从零建立安全网，照 C4 的
黄金文件模式，拆分前后输出必须逐字节一致。

额外断言（快照抓不到的部分）：
· print 文案（capsys）："选股报告已生成: " / "组合报告已生成: "
· stat-grid marker：位置与出现次数——generate_full_chain_report 靠
  `content.find('<div class="stat-grid">')` 注入选股逻辑，找不到时
  **静默跳过不报错**，必须钉死。

有意变更输出时：删除对应 golden 重跑本测试重新固化，并在 commit 说明原因。
"""

from datetime import datetime
from unittest.mock import patch

import pandas as pd
import pytest

from stock_analyzer import report_generators
from stock_analyzer.report_generators import (
    generate_portfolio_report,
    generate_screener_report,
)

FIXED_NOW = datetime(2026, 10, 18, 12, 0, 0)
STAT_GRID_MARKER = '<div class="stat-grid">'


class _FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):  # noqa: ARG003
        return FIXED_NOW


def _screener_df() -> pd.DataFrame:
    rows = [
        # 代码 / 名称 / 综合评分 / 评级（含带空白的"  Buy  "以覆盖 strip 与兜底分支）
        ("600000", "浦发银行", 82.5, "  Buy  ", 80, 85, 90, 70, 25, 10.5, 1.2),
        ("000001", "平安银行", 78.0, "Buy", 75, 80, 85, 65, 30, 11.8, -0.6),
        ("300750", "宁德时代", 74.0, "Hold", 70, 75, 88, 60, 35, 210.0, 2.3),
        ("601138", "工业富联", 55.0, "Sell", 50, 55, 60, 45, 55, 18.2, -1.1),
    ]
    cols = [
        "代码",
        "名称",
        "综合评分",
        "评级",
        "动量分",
        "技术分",
        "基本面分",
        "量能分",
        "风险分",
        "最新价",
        "涨跌幅",
    ]
    return pd.DataFrame(rows, columns=cols)


def _stock_details() -> dict:
    def detail(sector: str) -> dict:
        return {
            "sector": sector,
            "quant_score": {
                "factor_scores": {
                    "momentum": {"score": 80},
                    "technical": {"score": 85},
                    "fundamental": {"score": 78},
                    "volume": {"score": 62},
                    "risk": {"score": 40},
                }
            },
            "trading_style": {"style": "稳健", "style_confidence": "高"},
        }

    return {
        "600000": detail("银行、金融"),
        "000001": detail("银行"),
        "300750": detail("电池、新能源"),
    }


def _portfolio_analysis() -> dict:
    return {
        "name": "测试组合",
        "total_value": 108000.0,
        "total_cost": 100000.0,
        "total_return_pct": 8.0,
        "portfolio_volatility_pct": 12.5,
        "portfolio_sharpe": 1.35,
        "stock_count": 3,
        "rebalance_suggestions": ["银行仓位偏高，建议减配 5%"],
        "stocks": [
            {
                "代码": "600000",
                "名称": "浦发银行",
                "仓位%": 40.0,
                "成本价": 10.0,
                "现价": 10.5,
                "收益率%": 5.0,
                "贡献度%": 2.0,
                "评分": 82.5,
                "评级": "Buy",
            },
            {
                "代码": "000001",
                "名称": "平安银行",
                "仓位%": 35.0,
                "成本价": 12.0,
                "现价": 11.8,
                "收益率%": -1.7,
                "贡献度%": -0.6,
                "评分": 78.0,
                "评级": "Buy",
            },
            {
                "代码": "300750",
                "名称": "宁德时代",
                "仓位%": 25.0,
                "成本价": 200.0,
                "现价": 210.0,
                "收益率%": 5.0,
                "贡献度%": 1.2,
                "评分": 74.0,
                "评级": "Hold",
            },
        ],
    }


def _golden(name: str):
    from pathlib import Path

    return Path(__file__).resolve().parent / name


def _compare(content: str, name: str) -> None:
    golden = _golden(name)
    if not golden.exists():
        golden.write_text(content + "\n", encoding="utf-8")
        pytest.skip(f"首次运行：已固化黄金快照 {golden.name}（{len(content)} 字符）")
    expected = golden.read_text(encoding="utf-8")
    if content + "\n" != expected:
        diff_at = next(
            (i for i, (a, b) in enumerate(zip(expected, content)) if a != b),
            min(len(expected), len(content)),
        )
        pytest.fail(
            f"快照不一致 @字符 {diff_at}\n"
            f"  期望: ...{expected[max(0, diff_at - 40) : diff_at + 60]!r}\n"
            f"  实得: ...{content[max(0, diff_at - 40) : diff_at + 60]!r}\n"
            f"  （有意变更输出：删除 {golden.name} 重新固化）"
        )


def test_screener_report_snapshot(tmp_path, capsys):
    """选股报告：HTML 逐字节 + print 文案"""
    output_path = str(tmp_path / "screener.html")
    with patch("stock_analyzer.report_generators.datetime", _FixedDatetime):
        result = generate_screener_report(
            _screener_df(), output_path=output_path, stock_details=_stock_details()
        )
    assert result == output_path
    content = (tmp_path / "screener.html").read_text(encoding="utf-8")
    assert "每日选股池报告" in content
    # print 文案（不进 HTML，快照抓不到）
    assert "选股报告已生成: " in capsys.readouterr().out
    _compare(content, "golden_screener_report.html")


def test_portfolio_report_snapshot(tmp_path, capsys):
    """组合报告：HTML 逐字节 + print 文案 + stat-grid marker 钉死"""
    output_path = str(tmp_path / "portfolio.html")
    with patch("stock_analyzer.report_generators.datetime", _FixedDatetime):
        result = generate_portfolio_report(
            _portfolio_analysis(), output_path=output_path, stock_details=_stock_details()
        )
    assert result == output_path
    content = (tmp_path / "portfolio.html").read_text(encoding="utf-8")
    assert "投资组合分析报告" in content or "组合" in content
    # stat-grid 是 generate_full_chain_report 的注入锚点：首次出现位置与唯一性必须钉死
    assert content.count(STAT_GRID_MARKER) == 1, "stat-grid 必须恰好出现一次（注入锚点）"
    assert content.find(STAT_GRID_MARKER) > 0
    # print 文案
    assert "组合报告已生成: " in capsys.readouterr().out
    _compare(content, "golden_portfolio_report.html")


def test_module_exports_stable():
    """report_html.py 依赖这些再导出，拆分后不得改名"""
    for name in (
        "generate_screener_report",
        "generate_portfolio_report",
        "generate_full_chain_report",
    ):
        assert hasattr(report_generators, name), f"缺失导出: {name}"
