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
        mock.patch.object(cli, f"cmd_{argv[1]}", return_value=returned),
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
