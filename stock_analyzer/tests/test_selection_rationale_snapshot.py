"""行为快照测试：_build_selection_rationale 拆分前后输出必须逐字节一致。

背景：2026-10-17 全面审计后续——该函数 387 行，计划拆为 6 个 _rationale_*
子函数。本测试在拆分**前**固化当前输出（黄金文件），拆分后必须不变。
确定性保证：函数无时钟/随机依赖（探索实证）；固定 df + stock_details。

有意变更输出时：删除 golden 文件重跑本测试重新固化，并在 commit message 说明。
"""

from pathlib import Path

import pandas as pd

from stock_analyzer.report_sections import _build_selection_rationale

GOLDEN = Path(__file__).resolve().parent / "golden_selection_rationale.html"


def _fixed_df() -> pd.DataFrame:
    rows = [
        {
            "代码": "600000",
            "名称": "浦发银行",
            "综合评分": 82.5,
            "评级": "强烈推荐",
            "动量分": 80,
            "技术分": 85,
            "基本面分": 90,
            "量能分": 70,
            "风险分": 25,
        },
        {
            "代码": "000001",
            "名称": "平安银行",
            "综合评分": 78.0,
            "评级": "推荐",
            "动量分": 75,
            "技术分": 80,
            "基本面分": 85,
            "量能分": 65,
            "风险分": 30,
        },
        {
            "代码": "300750",
            "名称": "宁德时代",
            "综合评分": 74.0,
            "评级": "推荐",
            "动量分": 70,
            "技术分": 75,
            "基本面分": 88,
            "量能分": 60,
            "风险分": 35,
        },
        {
            "代码": "601138",
            "名称": "工业富联",
            "综合评分": 55.0,
            "评级": "观望",
            "动量分": 50,
            "技术分": 55,
            "基本面分": 60,
            "量能分": 45,
            "风险分": 55,
        },
    ]
    return pd.DataFrame(rows)


def _fixed_details() -> dict:
    return {
        "600000": {
            "sector": "银行、金融",
            "quant_score": {
                "factor_scores": {"momentum": {"score": 80}, "technical": {"score": 85}}
            },
            "trading_style": {"style": "稳健", "style_confidence": 0.8},
        },
        "000001": {
            "sector": "银行",
            "quant_score": {
                "factor_scores": {"momentum": {"score": 75}, "technical": {"score": 80}}
            },
            "trading_style": {"style": "均衡", "style_confidence": 0.7},
        },
        "300750": {
            "sector": "电池、新能源",
            "quant_score": {
                "factor_scores": {"momentum": {"score": 70}, "technical": {"score": 75}}
            },
            "trading_style": {"style": "成长", "style_confidence": 0.9},
        },
    }


def test_selection_rationale_snapshot():
    output = _build_selection_rationale(_fixed_df(), _fixed_details(), total_scanned=100, top_n=3)
    assert output, "输出为空——函数行为异常"
    # 结构性锚点（拆分时最容易丢的部分）
    for marker in ("选股逻辑说明", "板块分布", "评分模型", "宁德时代"):
        assert marker in output, f"快照缺少关键标记: {marker}"
    # 黄金文件逐字节比对
    if not GOLDEN.exists():
        GOLDEN.write_text(output + "\n", encoding="utf-8")
        print(f"\n首次运行：已固化黄金快照 {GOLDEN.name}（{len(output)} 字符）")
        return
    expected = GOLDEN.read_text(encoding="utf-8")
    if output + "\n" != expected:
        # 给出首个差异位置帮助定位
        diff_at = next(
            (i for i, (a, b) in enumerate(zip(expected, output)) if a != b),
            min(len(expected), len(output)),
        )
        pytest_fail(
            f"快照不一致 @字符 {diff_at}\n"
            f"  期望: ...{expected[max(0, diff_at - 30) : diff_at + 50]!r}\n"
            f"  实得: ...{output[max(0, diff_at - 30) : diff_at + 50]!r}\n"
            f"  （有意变更输出：删除 {GOLDEN.name} 重新固化）"
        )


def pytest_fail(msg: str):
    import pytest

    pytest.fail(msg)
