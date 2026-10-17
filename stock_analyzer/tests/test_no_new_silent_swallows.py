"""P1 门禁：静默吞异常（纯 except-pass）不得新增 —— 2026-10-17 全面审计后续。

背景：全面审计发现全仓 76 处 `except Exception: pass`，其中取数/缓存层 26 处
会让残缺数据静默流入分析和报告。治理采用"分级日志"（链中节点 debug、
兜底终点 warning），本门禁保证治理成果不回退：**只减不增**。

判据（全部机器判定，AST 解析，与 hardcoded_paths 门禁同构）：
  ① 已有文件出现数**超过基线** → ❌ 失败（新增即拦）
  ② 基线外**新文件**出现 ≥1 处 → ❌ 失败
  ③ 出现数**少于基线** → ✅ 通过，但打印提示下调基线（防基线腐烂）
  ④ 已清零却仍在基线表 → ❌ 失败

调整基线：直接编辑 silent_swallows_baseline.json（每项 = 该文件当前计数），
改完本测试即自校验。
"""

import ast
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]  # tests/ → stock_analyzer/ → 仓库根
BASELINE = Path(__file__).resolve().parent / "silent_swallows_baseline.json"
SCAN_ROOTS = [REPO / "backend", REPO / "stock_analyzer", REPO / "cli.py"]


def _count_pure_except_pass(path: Path) -> int:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return 0
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler)
        and len(node.body) == 1
        and isinstance(node.body[0], ast.Pass)
    )


def _scan_current() -> dict[str, int]:
    current: dict[str, int] = {}
    for root in SCAN_ROOTS:
        files = [root] if root.is_file() else list(root.rglob("*.py"))
        for f in files:
            s = str(f)
            if "test" in s or ".venv" in s:
                continue
            n = _count_pure_except_pass(f)
            if n:
                current[s] = n
    return {k.replace(str(REPO) + "/", ""): v for k, v in current.items()}


def test_no_new_silent_swallows() -> None:
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
            print("\n⚠️ 以下文件低于基线，建议下调 silent_swallows_baseline.json：")
            for f in stale:
                print(f"   {f}: {baseline[f]} → {current[f]}")
        return

    msg = ["发现静默吞异常超出基线（治理成果回退）："]
    for f, n, allowed in over:
        msg.append(f"  {f}: 基线 {allowed} → 当前 {n}")
    msg.append("处置：新代码应使用分级日志（链中节点 logger.debug / 兜底终点 logger.warning）；")
    msg.append("确认治理后可下调基线 JSON。")
    pytest.fail("\n".join(msg))
