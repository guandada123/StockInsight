"""P2 门禁：未用变量（ruff F841）不得新增 —— 2026-10-18 补齐 advanced.py 时发现。

背景：`F841`（unused-variable）在 ruff.toml 中被全局 ignore，导致死代码静默累积
——advanced.py 藏了 4 处（`threading.local()` 空赋值、构造后从未使用的
`start_date`/`end_date`/`name_col`），无任何 lint/测试发现。基线实测全仓 76 处
（含测试文件中 `with patch(...) as mock:` 未用 mock 的合理模式）。

本门禁保证**只减不增**（与 silent_swallows / oversized_functions 同构）：
  ① 已有文件出现数**超过基线** → ❌ 失败
  ② 基线外**新文件**出现 ≥1 个 → ❌ 失败
  ③ 出现数**少于基线** → ✅ 通过，但打印提示下调基线（防基线腐烂）
  ④ 已清零却仍在基线表 → ❌ 失败

实现：调用 ruff `--select F841 --output-format json`（作用域级的"赋值未使用"
分析 AST 自研成本极高且易误判，复用 ruff 已验证的实现；ruff 由
requirements-dev.txt 钉版 0.15.17 提供，CI 测试 job 必装）。

调整基线：`ruff check . --config ruff.toml --select F841 --output-format json`
逐文件计数后编辑 unused_vars_baseline.json。
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]  # tests/ → stock_analyzer/ → 仓库根
BASELINE = Path(__file__).resolve().parent / "unused_vars_baseline.json"


def _scan_current() -> dict[str, int]:
    """用 ruff 统计全仓每文件 F841 数量（口径与 CI `ruff check .` 一致）。"""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            str(REPO),
            "--config",
            str(REPO / "ruff.toml"),
            "--select",
            "F841",
            "--output-format",
            "json",
            "--no-cache",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    # ruff check 有诊断时 exit=1，无诊断 exit=0；其它退出码是工具本身故障
    assert proc.returncode in (0, 1), f"ruff 执行失败(rc={proc.returncode}): {proc.stderr[:300]}"
    diagnostics = json.loads(proc.stdout or "[]")
    counts: dict[str, int] = {}
    for d in diagnostics:
        try:
            rel = Path(d["filename"]).resolve().relative_to(REPO.resolve()).as_posix()
        except ValueError:  # 仓库外文件（理论上不会出现）
            continue
        counts[rel] = counts.get(rel, 0) + 1
    return counts


def _load_baseline() -> dict[str, int]:
    data: dict[str, int] = json.loads(BASELINE.read_text(encoding="utf-8"))
    return data


def test_no_new_unused_vars() -> None:
    """F841 只减不增：超过基线或新文件出现即失败。"""
    current = _scan_current()
    baseline = _load_baseline()

    over: list[str] = []
    new: list[str] = []
    for path, cnt in sorted(current.items()):
        base = baseline.get(path)
        if base is None:
            new.append(f"{path}: {cnt} 处")
        elif cnt > base:
            over.append(f"{path}: {cnt} > 基线 {base}")

    assert not over and not new, (
        "F841（未用变量）只减不增被打破——请赋值即使用，或 `_ = expr` 显式丢弃：\n"
        + "\n".join(["【超基线】"] + over + ["【基线外新文件】"] + new if over or new else [])
    )

    # ③ 低于基线：提示下调（不失败）
    shrunk = [
        (p, baseline[p], current.get(p, 0)) for p in baseline if current.get(p, 0) < baseline[p]
    ]
    if shrunk:
        print("\n⬇️ 以下文件 F841 已减少，请下调 unused_vars_baseline.json：")
        for p, old, now in shrunk:
            print(f"   {p}: {old} → {now}")

    # ④ 清零仍在基线表 → 失败（防基线腐烂，与 oversized 门禁同判据）
    stale = [p for p, v in baseline.items() if v > 0 and current.get(p, 0) == 0]
    assert not stale, "以下文件 F841 已清零，请从基线中删除键（清零必须删键）：\n" + "\n".join(
        stale
    )
