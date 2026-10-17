"""P2 门禁：超长函数（>120 行）不得新增 —— 2026-10-17 全面审计后续。

背景：审计发现 26 个超 120 行的大函数（最大 478 行），单函数过长导致
测试难以覆盖分支、改动回归风险高。本门禁保证**只减不增**：
拆分既有大函数后下调基线，新代码不允许再出现超长函数。

判据（AST 解析，与 silent_swallows 门禁同构）：
  ① 已有文件出现数**超过基线** → ❌ 失败
  ② 基线外**新文件**出现 ≥1 个 → ❌ 失败
  ③ 出现数**少于基线** → ✅ 通过，但打印提示下调基线（防基线腐烂）
  ④ 已清零却仍在基线表 → ❌ 失败

阈值：120 行（与审计口径一致）。调整基线：编辑 oversized_functions_baseline.json。
"""

import ast
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]  # tests/ → stock_analyzer/ → 仓库根
BASELINE = Path(__file__).resolve().parent / "oversized_functions_baseline.json"
SCAN_ROOTS = [REPO / "backend", REPO / "stock_analyzer", REPO / "cli.py"]
THRESHOLD = 120


def _count_oversized(path: Path) -> int:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return 0
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.end_lineno - node.lineno > THRESHOLD
    )


def _scan_current() -> dict[str, int]:
    current: dict[str, int] = {}
    for root in SCAN_ROOTS:
        files = [root] if root.is_file() else list(root.rglob("*.py"))
        for f in files:
            s = str(f)
            if "test" in s or ".venv" in s:
                continue
            n = _count_oversized(f)
            if n:
                current[s.replace(str(REPO) + "/", "")] = n
    return current


def test_no_new_oversized_functions() -> None:
    baseline: dict[str, int] = json.loads(BASELINE.read_text(encoding="utf-8"))
    current = _scan_current()

    over: list[tuple[str, int, int]] = []
    for f, allowed in baseline.items():
        n = current.get(f, 0)
        if n == 0:
            over.append((f, n, allowed))  # ④ 已清零仍在基线
        elif n > allowed:
            over.append((f, n, allowed))  # ①/② 超基线
    for f, n in current.items():
        if f not in baseline:
            over.append((f, n, 0))  # ② 新文件

    if not over:
        stale = [f for f, n in current.items() if f in baseline and n < baseline[f]]
        if stale:
            print("\n⚠️ 以下文件低于基线，建议下调 oversized_functions_baseline.json：")
            for f in stale:
                print(f"   {f}: {baseline[f]} → {current[f]}")
        return

    msg = ["发现超长函数（>120 行）超出基线："]
    for f, n, allowed in over:
        msg.append(f"  {f}: 基线 {allowed} → 当前 {n}")
    msg.append("处置：拆分函数（数据准备/核心逻辑/拼装三段式），或经评审后下调基线 JSON。")
    pytest.fail("\n".join(msg))
