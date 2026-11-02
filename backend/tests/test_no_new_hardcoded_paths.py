"""P1-12 增量门禁：**禁止新增**本机绝对路径（/Users/guan）到本仓代码。

> 移植自 Claw 的同名门禁（2026-10-12 跨项目治理）。Claw 侧扫描域是 `.workbuddy/scripts/`，
> 本仓改为「**已入库的代码文件**」——口径与 CI 检出树一致（本地全绿 ≠ CI 会绿）。

## 判据（五条，全部机器判定）
  ① **新文件**出现 ≥1 处 → ❌ 失败
  ② 已有文件出现数**超过基线** → ❌ 失败（新增即拦）
  ③ 出现数**少于基线** → ✅ 通过，但提示下调基线（门禁逐步收紧）
  ④ 已清零却仍在基线表 → ❌ 失败（防止基线腐烂成"永远允许"）
  ⑤ **code_only 基线比实测宽松**（留了余量）→ ❌ 失败

## 两层口径（2026-11-03 从 Claw 同步）
  - `files`：正则按出现次数统计，**含注释与文档串** → 硬天花板。
  - `code_only`：只数运行时会用到的字符串字面量（排除 COMMENT / docstring）→ 真实风险线。
  - 本仓目前两层的实测都是 0、基线都是空表，故两层判据**当前等价**；分层的价值在
    ①失败时能说清「是运行时依赖还是只写了句注释」②将来真要开例外时，风险面可单独度量。
  - ⚠️ Python 3.12+ 的 f-string 是 FSTRING_MIDDLE token，统计层已同时收 STRING 与 FSTRING_MIDDLE，
    改成只认 STRING 会静默漏掉全部 f-string 硬编码。

## ⚠️ 别对基线 .json 显式跑 `ruff format`（会加尾逗号 → json.loads 崩）
改数字请用文本替换，改完 `python -c "import json;json.load(open(…))"` 验一次。
"""

from __future__ import annotations

import io
import json
import re
import subprocess
import tokenize
from pathlib import Path
from typing import cast

REPO = Path(__file__).resolve().parent.parent
BASELINE = Path(__file__).resolve().parent / "hardcoded_paths_baseline.json"
# 拼装构造，避免门禁文件自身被判"测试里写死本机路径"
# 🔴 2026-10-31 修：原只匹配 /Users/guan。工程已迁 /Volumes/ZHITAI/WorkBuddy 且旧路径经软链
# 仍有效，导致新形态路径长期绕过门禁（两边都不报错）。现同时覆盖两个根。
PATTERN = re.compile("/" + "Use" + "rs/guan|/Volumes/Z" + "HITAI")
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
    return cast(dict[str, int], json.loads(BASELINE.read_text(encoding="utf-8"))["files"])


def _code_hits(path: Path) -> int:
    """只数**会进入运行时**的字符串字面量里的命中（排除注释与 docstring）。

    docstring 判定：模块/函数/类开头的第一条 STRING（用冒号/换行状态机近似）。
    解析失败时退回原口径（宁可多拦，不因解析失败而静默放过）。
    """
    src = path.read_text(encoding="utf-8", errors="ignore")
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return len(PATTERN.findall(src))

    doc_lines: set[int] = set()
    expect_doc = True
    for t in toks:
        if t.type == tokenize.STRING and expect_doc:
            doc_lines.update(range(t.start[0], t.end[0] + 1))
            expect_doc = False
        if t.type not in (
            tokenize.NEWLINE,
            tokenize.NL,
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.COMMENT,
            tokenize.ENCODING,
        ):
            expect_doc = t.type == tokenize.OP and t.string == ":"

    n = 0
    fstring_middle = getattr(tokenize, "FSTRING_MIDDLE", None)
    for t in toks:
        # Python 3.12+ 起 f-string 被拆成 FSTRING_START / FSTRING_MIDDLE / FSTRING_END，
        # 字面量部分不再是 STRING token；只认 STRING 会静默漏掉全部 f-string 硬编码。
        is_literal = t.type == tokenize.STRING or (
            fstring_middle is not None and t.type == fstring_middle
        )
        if not is_literal or PATTERN.search(t.string) is None:
            continue
        if t.type == tokenize.STRING and t.start[0] in doc_lines:
            continue
        n += len(PATTERN.findall(t.string))
    return n


def scan_code_only() -> dict[str, int]:
    """口径同 scan()（只统计已入库代码），但排除注释/文档串。"""
    files = _tracked_code()
    if files is None:
        return {}
    out: dict[str, int] = {}
    for p in files:
        try:
            n = _code_hits(p)
        except OSError:
            continue
        if n:
            out[str(p.relative_to(REPO))] = n
    return out


def load_code_baseline() -> dict[str, int]:
    return cast(
        dict[str, int], json.loads(BASELINE.read_text(encoding="utf-8")).get("code_only", {})
    )


def test_no_new_hardcoded_paths():
    current, baseline = scan(), load_baseline()
    code = scan_code_only()

    def why(fname: str) -> str:
        """标注属性：是运行时依赖，还是只是注释/文档串。

        没有这一行时，注释里写一句路径也会红，读的人会以为新增了运行时依赖。
        """
        n = code.get(fname, 0)
        return f"（其中运行时代码 {n} 处）" if n else "（全部在注释/文档串里，不影响运行时）"

    new_files = sorted(set(current) - set(baseline))
    increased = sorted(
        (f, baseline[f], current[f])
        for f in set(current) & set(baseline)
        if current[f] > baseline[f]
    )
    assert not new_files, (
        "以下文件**新增**了本机绝对路径 /Users/guan（禁新增）——请改用派生路径"
        "（Path(__file__).resolve().parents[N] / Path.home()）或环境变量：\n  - "
        + "\n  - ".join(f"{f} {why(f)}" for f in new_files)
    )
    assert not increased, "以下文件的本机绝对路径**比基线更多**（禁新增）：\n  - " + "\n  - ".join(
        f"{f}: {b} → {n} {why(f)}" for f, b, n in increased
    )


def test_no_new_hardcoded_path_in_runtime_code():
    """真实风险线：只比 code_only 层（注释/文档串不算）。"""
    current, baseline = scan_code_only(), load_code_baseline()
    new_files = sorted(set(current) - set(baseline))
    increased = sorted(
        (f, baseline[f], current[f])
        for f in set(current) & set(baseline)
        if current[f] > baseline[f]
    )
    assert not new_files, "以下文件**新增**了运行时会用到的本机绝对路径：\n  - " + "\n  - ".join(
        new_files
    )
    assert not increased, "以下文件的运行时绝对路径**比基线更多**：\n  - " + "\n  - ".join(
        f"{f}: {b} → {c}" for f, b, c in increased
    )


def test_code_baseline_has_no_slack():
    """code_only 基线**不许留余量**：每个文件的基线必须等于实测值。

    动机：基线是入库的 JSON，谁都能把数字调大来让红灯变绿。单快照里无法从机制上阻止
    （改大就通过），但可以消灭"留余量"这种合法化借口——调大后必然出现 slack，本用例立刻红。
    """
    current, baseline = scan_code_only(), load_code_baseline()
    loose = sorted(
        (f, baseline[f], current.get(f, 0)) for f in baseline if baseline[f] > current.get(f, 0)
    )
    assert not loose, (
        "以下文件的 code_only 基线**比实测更宽松**（等于提前预留了新增额度）：\n  - "
        + "\n  - ".join(f"{f}: 基线 {b} → 实测 {c}" for f, b, c in loose)
        + "\n\n按实测收紧后应写成：\n"
        + json.dumps(current, ensure_ascii=False, indent=2)
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
        (f, baseline[f], current[f])
        for f in set(current) & set(baseline)
        if current[f] < baseline[f]
    )
    if improved:
        print(
            "📉 以下文件已比基线减少，请把基线数字调小：\n  - "
            + "\n  - ".join(f"{f}: {b} → {c}" for f, b, c in improved)
        )
    print(
        f"📊 当前硬编码总量：{sum(current.values())} 处 / {len(current)} 文件（基线 {sum(baseline.values())} 处）"
    )
