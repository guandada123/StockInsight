"""行为快照测试：generate_sector_report 拆分前后输出必须逐字节一致。

背景：2026-10-18 全面审计后续——该函数 479 行，计划拆为 11 个子函数。
本测试在拆分**前**固化当前输出（黄金文件），拆分后必须不变。
（现有 test_sector_report.py 的 29 个用例均为弱子串断言，抓不到段落顺序
错乱/漏段/换行丢失等字节级漂移，故必须补快照。）

确定性保证：patch 冻结 datetime/扫描/板块映射/大盘行情/资金流五个外部依赖；
显式传 output_path 绕开默认路径；真实写 tmp_path 后读回比对。

有意变更输出时：删除对应 golden 文件重跑本测试重新固化，并在 commit 说明原因。
"""

from datetime import datetime
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from stock_analyzer import sector_report

FIXED_NOW = datetime(2026, 10, 18, 12, 0, 0)


class _FixedDatetime(datetime):
    """冻结 datetime.now()，使文件名与页脚时间戳稳定"""

    @classmethod
    def now(cls, tz=None):  # noqa: ARG003
        return FIXED_NOW


def _screener_df() -> pd.DataFrame:
    """固定扫描结果（含多板块顿号、低分边界、NaN 评分）"""
    rows = [
        ("000001", 65, "Buy", 60, 70, 55, 50, 40),
        ("000002", 45, "Hold", 50, 40, 60, 45, 55),
        ("000003", 30, "Sell", 20, 30, 35, 25, 45),
        ("600001", 80, "Strong Buy", 85, 75, 90, 80, 70),
        ("600002", 55, "Hold", 60, 50, 55, 60, 50),
        ("002001", 70, "Buy", 65, 75, 80, 70, 60),
        ("300001", 20, "Strong Sell", 15, 25, 30, 20, 35),
        ("999999", 10, "Hold", 0, 0, 0, 0, 0),
        ("888888", np.nan, "Hold", 10, 10, 10, 10, 10),  # NaN 评分分支
    ]
    cols = ["代码", "综合评分", "评级", "动量分", "技术分", "基本面分", "量能分", "风险分"]
    return pd.DataFrame(rows, columns=cols)


def _mock_sector(code: str) -> str:
    mapping = {
        "000001": "银行、金融",  # 顿号多板块分支
        "000002": "地产",
        "000003": "综合",
        "600001": "科技",
        "600002": "制造",
        "002001": "医药",
        "300001": "其他",
        "999999": "其他",
        "888888": "其他",
    }
    return mapping.get(code, "其他")


def _fund_flow_df() -> pd.DataFrame:
    """固定资金流排名数据（字段名与东财返回一致）"""
    rows = [
        (1, "银行", 1.2e8, 3.5, 1.1, "招商银行"),
        (2, "科技", -5.0e7, -1.8, -0.6, "中芯国际"),
        (3, "医药", 8.0e7, 2.2, 0.9, "恒瑞医药"),
    ]
    cols = [
        "序号",
        "名称",
        "今日主力净流入-净额",
        "今日主力净流入-净占比",
        "今日涨跌幅",
        "今日主力净流入最大股",
    ]
    return pd.DataFrame(rows, columns=cols)


def _run(output_path: str, df: pd.DataFrame, mkt, ff) -> str:
    with (
        patch("stock_analyzer.sector_report.datetime", _FixedDatetime),
        patch("stock_analyzer.sector_report.run_screener", return_value=df),
        patch("stock_analyzer.sector_report.get_sector_for_code", side_effect=_mock_sector),
        patch("stock_analyzer.sector_report.cached_market_overview", return_value=mkt),
        patch("stock_analyzer.cache.cached_sector_fund_flow_rank", ff),
    ):
        return sector_report.generate_sector_report(output_path)


def _snapshot(tmp_path, name: str, df: pd.DataFrame, mkt, ff) -> None:
    output_path = str(tmp_path / "s.html")
    _run(output_path, df, mkt, ff)
    content = (tmp_path / "s.html").read_text(encoding="utf-8")
    assert "全市场板块分析报告" in content, "输出缺少报告标题"
    golden = path_golden(name)
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


def path_golden(name: str):
    from pathlib import Path

    return Path(__file__).resolve().parent / name


def test_snapshot_full(tmp_path):
    """全特性：大盘行情有值 + 资金流有值"""
    mkt = {
        "000001": {"最新价": 3200.5, "涨跌幅": 1.2, "名称": "上证指数"},
        "399001": {"最新价": 12000.0, "涨跌幅": -0.5, "名称": "深证成指"},
    }
    _snapshot(tmp_path, "golden_sector_report_full.html", _screener_df(), mkt, _fund_flow_df())


def test_snapshot_no_rating(tmp_path):
    """无评级列分支（ratings 为空、无 doughnut 图）"""
    df = _screener_df().drop(columns=["评级"])
    _snapshot(tmp_path, "golden_sector_report_no_rating.html", df, None, _fund_flow_df())


def test_snapshot_fund_flow_fail(tmp_path):
    """资金流异常分支（走 except 文案）"""
    from unittest.mock import Mock

    ff = Mock(side_effect=ValueError("数据解析失败"))
    _snapshot(tmp_path, "golden_sector_report_ff_fail.html", _screener_df(), None, ff)
