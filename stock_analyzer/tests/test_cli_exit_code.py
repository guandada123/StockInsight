"""退出码契约回归测试（2026-10-17）

背景（见仓库外 `代码审查修复报告_20261017.md` P0-1）：
    `cli.main()` 曾写成 `dispatch[args.command](args)`，**丢弃返回值**，
    进程恒以 0 退出。后果：
      · 调用方依赖的「退出码非 0 = 异常」判定永久失效
        （StockInsight 收盘选股扫描自动化 automation-1784555575881 的异常条件之一）；
      · `cmd_audit` 的 `1 if report.has_issues() else 0` 从未生效。
    修复后为 `sys.exit(dispatch[args.command](args))`。

本测试把该契约固化为门禁：
    **main() 的进程退出码必须等于对应 cmd_* 的返回值**（None 视为 0）。

注意：
    - 全部 cmd_* 处于 mock 状态，不发任何网络请求；
    - argv 必须能通过 argparse（`config` 需要 action 位置参数）。
"""

import sys
from unittest import mock

import pytest

import cli
import cli_commands


@pytest.mark.parametrize(
    "argv,returned",
    [
        # cmd_audit 的真实契约：有/无问题 → 1 / 0
        (["cli.py", "audit"], 1),
        (["cli.py", "audit"], 0),
        # cmd_scan 非交易日路径返回 0
        (["cli.py", "scan"], 0),
        # 返回 None 的命令：sys.exit(None) → 退出码 0（与修复前行为一致，防回归）
        (["cli.py", "config", "show"], None),
        (["cli.py", "check"], None),
    ],
)
def test_main_propagates_dispatch_return_value(argv, returned):
    """main() 的退出码必须等于对应 cmd_* 的返回值（None → 0）。"""
    with (
        mock.patch.object(sys, "argv", argv),
        mock.patch.object(
            cli, f"cmd_{argv[1]}", return_value=returned
        ),  # build_parser 解析期自 cli 命名空间绑定
    ):
        with pytest.raises(SystemExit) as excinfo:
            cli.main()

    code = excinfo.value.code
    assert (0 if code is None else code) == (returned or 0), (
        f"{argv} 期望退出码 {returned or 0}，实得 {code!r}"
    )


def test_main_without_command_exits_zero():
    """无子命令 → 仅打印 help 后正常返回（不抛 SystemExit），进程退 0。"""
    with mock.patch.object(sys, "argv", ["cli.py"]):
        # main() 在 command is None 分支直接 return，不应抛 SystemExit
        cli.main()


def test_audit_exit_code_contract_matches_implementation():
    """cmd_audit 的返回值语义必须仍是 0/1（问题存在→1）。

    若未来 cmd_audit 改为返回 None，本测试会提醒同步更新
    automation 侧对退出码的解读。
    """
    src_has_return = False
    try:
        import inspect

        src = inspect.getsource(cli.cmd_audit)
        src_has_return = "return 1 if" in src or "return 0" in src
    except (OSError, TypeError):
        pytest.skip("无法读取 cmd_audit 源码")
    assert src_has_return, "cmd_audit 不再返回 0/1 退出码，请同步更新退出码契约文档"


# ══════════════════════════════════════════════════════════════
# 失败率护栏（2026-10-17，_fail_on_skip_ratio）
# ══════════════════════════════════════════════════════════════


def test_fail_on_skip_ratio_thresholds():
    """≥阈值比例未完成 → 判失败；阈值可用 SCAN_FAIL_RATIO 覆盖，>1 显式禁用。"""
    import os

    cases = [
        # (环境值, skipped, total, 期望)
        ("0.9", 4100, 4466, True),  # 91.8% → 失败
        ("0.9", 100, 4466, False),  # 2.2% → 正常
        ("0.9", 4466, 4466, True),  # 100% → 失败
        ("0.9", 0, 0, False),  # 空池 → 不判失败（bool(total) 守卫）
        ("0.9", 4020, 4466, True),  # 恰好 90%（>=）
        ("0.9", 4019, 4466, False),  # 差 1 只未到阈值
        ("1.5", 4466, 4466, False),  # >1 → 显式禁用
        ("abc", 4100, 4466, True),  # 非数字 → 回退默认 0.9
    ]
    for env_val, skipped, total, expected in cases:
        with mock.patch.dict(os.environ, {"SCAN_FAIL_RATIO": env_val}):
            got = cli._fail_on_skip_ratio(skipped, total)
        assert got is expected, (
            f"SCAN_FAIL_RATIO={env_val}, {skipped}/{total}: 期望 {expected}，实得 {got}"
        )


def test_fail_on_skip_ratio_default_when_env_missing():
    """未设置环境变量 → 默认阈值 0.9。"""
    import os

    env = {k: v for k, v in os.environ.items() if k != "SCAN_FAIL_RATIO"}
    with mock.patch.dict(os.environ, env, clear=True):
        assert cli._fail_on_skip_ratio(4100, 4466) is True
        assert cli._fail_on_skip_ratio(100, 4466) is False


def test_cmd_scan_returns_1_when_all_codes_fail():
    """集成：全部标的分析失败 → main() 以退出码 1 结束（「退出码非 0」判据可用）。

    全程 mock，零网络请求；不落盘（--no-save + mock checkpoint）。
    """
    import os

    import stock_analyzer.screener as screener_mod
    import stock_analyzer.trade_day as trade_day_mod

    argv = [
        "cli.py",
        "scan",
        "--mode",
        "mainboard",
        "--top-n",
        "1",
        "--min-score",
        "0",
        "--no-save",
    ]
    with (
        mock.patch.object(sys, "argv", argv),
        mock.patch.dict(os.environ, {"SCAN_FAIL_RATIO": "0.9"}),
        mock.patch.object(trade_day_mod, "is_trading_day", return_value=True),
        mock.patch.object(
            screener_mod, "load_all_a_shares", return_value=["600000", "000001", "300001"]
        ),
        mock.patch.object(screener_mod, "quick_filter", side_effect=lambda c: c),
        mock.patch.object(cli_commands, "deep_analyze", side_effect=RuntimeError("模拟取数全挂")),
        mock.patch.object(cli_commands, "_save_checkpoint_single"),
        mock.patch.object(cli_commands, "_clear_checkpoint"),
        mock.patch.object(cli_commands, "_cleanup_old_logs", return_value=[]),
        mock.patch.object(
            cli.sys, "exit", side_effect=SystemExit
        ) as m_exit,  # sys.exit 由 cli.main 统一调用
    ):
        with pytest.raises(SystemExit):
            cli.main()

    m_exit.assert_called_once_with(1)
