"""P1-12 增量门禁：**禁止新增**本机绝对路径（/Users/guan）到本仓代码。

> 移植自 Claw 的同名门禁（2026-10-12 跨项目治理）。Claw 侧扫描域是 `.workbuddy/scripts/`，
> 本仓改为「**已入库的代码文件**」——口径与 CI 检出树一致（本地全绿 ≠ CI 会绿）。

## 判据（全部机器判定）
  ① **新文件**出现 ≥1 处 → ❌ 失败
  ② 已有文件出现数**超过基线** → ❌ 失败（新增即拦）
  ③ 出现数**少于基线** → ✅ 通过，但提示下调基线（门禁逐步收紧）
  ④ 已清零却仍在基线表 → ❌ 失败（防止基线腐烂成"永远允许"）

## ⚠️ 别对基线 .json 显式跑 `ruff format`（会加尾逗号 → json.loads 崩）
改数字请用文本替换，改完 `python -c "import json;json.load(open(…))"` 验一次。
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASELINE = Path(__file__).resolve().parent / "hardcoded_paths_baseline.json"
# 拼装构造，避免门禁文件自身被判"测试里写死本机路径"
PATTERN = re.compile("/" + "Use" + "rs/guan")
SELF = Path(__file__).name
EXTS = (".py", ".sh", ".ts", ".tsx", ".js", ".vue")
SKIP = (".venv/", "node_modules/", "/.git/", "dist/", "build/", "__pycache__/")


def _tracked_code() -> list[Path] | None:
    """本仓**已入库**、且是代码后缀的文件；取不到返回 None（判不了就不拦）。"""
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO), "ls-files"], capture_output=True, text=True, timeout=20
        )
    except Exception:  # noqa: BLE001
        return None
    if r.returncode != 0:
        return None
    out = []
    for ln in r.stdout.splitlines():
        if not ln.strip() or not ln.endswith(EXTS) or any(s in ln for s in SKIP):
            continue
        p = REPO / ln
        if p.name == SELF:
            continue
        out.append(p)
    return out


def scan() -> dict[str, int]:
    files = _tracked_code()
    if files is None:
        return {}
    out: dict[str, int] = {}
    for p in files:
        try:
            n = len(PATTERN.findall(p.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            continue
        if n:
            rel = str(p.relative_to(REPO))
            out[rel] = n
    return out


def load_baseline() -> dict[str, int]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))["files"]


def test_no_new_hardcoded_paths():
    current, baseline = scan(), load_baseline()
    new_files = sorted(set(current) - set(baseline))
    increased = sorted(
        (f, baseline[f], current[f]) for f in set(current) & set(baseline) if current[f] > baseline[f]
    )
    assert not new_files, (
        "以下文件**新增**了本机绝对路径 /Users/guan（禁新增）——请改用派生路径"
        "（Path(__file__).resolve().parents[N] / Path.home()）或环境变量：\n  - " + "\n  - ".join(new_files)
    )
    assert not increased, "以下文件的本机绝对路径**比基线更多**（禁新增）：\n  - " + "\n  - ".join(
        f"{f}: {b} → {c}" for f, b, c in increased
    )


def test_baseline_has_no_stale_zero_entries():
    """基线腐烂守卫：文件已清零却还留在表里 = 门禁对它是"永远允许"。"""
    current, baseline = scan(), load_baseline()
    stale = sorted(f for f in baseline if f not in current)
    assert not stale, (
        f"以下文件已无 /Users/guan，但仍留在基线表：请从 {BASELINE.name} 删除这些条目：\n  - "
        + "\n  - ".join(stale)
    )


def test_report_progress(capsys):
    current, baseline = scan(), load_baseline()
    improved = sorted(
        (f, baseline[f], current[f]) for f in set(current) & set(baseline) if current[f] < baseline[f]
    )
    if improved:
        print("📉 以下文件已比基线减少，请把基线数字调小：\n  - " + "\n  - ".join(f"{f}: {b} → {c}" for f, b, c in improved))
    print(f"📊 当前硬编码总量：{sum(current.values())} 处 / {len(current)} 文件（基线 {sum(baseline.values())} 处）")
