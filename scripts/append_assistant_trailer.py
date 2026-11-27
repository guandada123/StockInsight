#!/usr/bin/env python3
"""给「助手写的提交」追加 `Assistant-Change` trailer（2026-11-27，用户拍板方案①）。

## 为什么需要

三仓 git 作者全是同一人（`guandada123`），**事后无法区分「助手写的」与「中台轮次写的」提交**。
2026-11-27 那次审计里「20 个提交」全靠回忆，不可独立复核 —— 审计链天生不闭合。

## 为什么是「按环境变量」而不是「无条件追加」

若对所有提交都加，中台轮次的提交也会被标成助手写的 —— 那是**错标**，比漏标更坏
（与「给助手单独 git identity」同类的失真，只是换了个位置）。

所以只在 `ASSISTANT_COMMIT=1` 时追加：

    ASSISTANT_COMMIT=1 git commit -m "..."

出错方向是**少标**（我忘了带 env），而不是**错标**。少标可以事后补查，错标会污染整条审计链。

## 幂等

已含 `Assistant-Change:` 的提交信息直接跳过，重复跑不会加两行。

## fail-safe

任何异常都 `exit 0` —— 这个 hook 只做标注，**没有资格阻断提交**。
写在 `commit-msg` stage 是为了一次性拿到最终信息（含 `-m` 与编辑器两种输入路径）。
"""

from __future__ import annotations

import datetime
import os
import re
import subprocess
import sys

MARKER = "Assistant-Change:"
ENV_FLAG = "ASSISTANT_COMMIT"


def _today_seq(repo_dir: str, today: str) -> int:
    """当天已有多少条 Assistant-Change → 下一条的序号。取不到就当 1。"""
    try:
        r = subprocess.run(
            ["git", "log", "--format=%B"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        # 第一版用 `git log --grep=^Assistant-Change: <date>- --fixed-strings` 数，
        # 结果 20 次提交的序号全是 `-1` —— `--fixed-strings` 会把 `^` 当字面量，匹配不到任何行。
        # 改为取全部 body 自己按前缀数，行为可预测。
        prefix = f"{MARKER} {today}-"
        n = sum(1 for ln in (r.stdout or "").splitlines() if ln.startswith(prefix))
        return n + 1
    except Exception:  # noqa: BLE001
        return 1


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        return 0
    msg_path = argv[1]

    # ① 只在显式声明「这是助手提交」时动手
    if os.environ.get(ENV_FLAG, "").strip() not in {"1", "true", "yes"}:
        return 0

    try:
        with open(msg_path, encoding="utf-8") as f:
            msg = f.read()
    except Exception:  # noqa: BLE001
        return 0

    # ② 幂等：已有 marker 就不重复加
    if re.search(rf"^{re.escape(MARKER)}", msg, re.MULTILINE):
        return 0

    # ③ 空提交信息（编辑器直接退出）不动
    if not msg.strip():
        return 0

    repo_dir = os.environ.get("GIT_DIR") or "."
    # GIT_DIR 可能是 .git 路径，取父目录作为仓根
    if repo_dir.endswith("/.git") or repo_dir == ".git":
        repo_dir = os.path.dirname(os.path.abspath(repo_dir))

    today = datetime.datetime.now().strftime("%Y-%m-%d")
    seq = _today_seq(repo_dir, today)
    trailer = f"{MARKER} {today}-{seq}"

    # ④ 保证 marker 前有一个空行（trailer 段约定）
    body = msg.rstrip("\n")
    new = f"{body}\n\n{trailer}\n"
    try:
        with open(msg_path, "w", encoding="utf-8") as f:
            f.write(new)
    except Exception:  # noqa: BLE001
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
