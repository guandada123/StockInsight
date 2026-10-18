"""AST 巡检门禁：同文件/同类内 test_ 函数重名检测。

背景（2026-10-18 测试去重取证）：Python 模块与类体都是"后名覆盖前名"的字典
语义——同一文件或同一类内定义两个同名 ``test_*``，pytest 只收集后者，前者
**静默不执行**（覆盖缩水且无任何告警）。跨文件同名不受影响（模块隔离），
属自然命名，不在本门禁范围。

判据：同文件顶层或同一类体内出现重复 ``test_`` 前缀函数 → 失败。
"""

from __future__ import annotations

import ast
import glob
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_TEST_GLOBS = ["stock_analyzer/tests/test_*.py", "backend/tests/test_*.py"]


def _iter_test_files() -> list[Path]:
    files: list[Path] = []
    for pattern in _TEST_GLOBS:
        files.extend(Path(p) for p in sorted(glob.glob(str(_PROJECT_ROOT / pattern))))
    return files


def _collect_dups(funcs: list[tuple[str, int]]) -> list[tuple[str, int, int]]:
    """返回 [(name, first_lineno, shadowed_lineno), ...]；funcs 保持源码顺序。"""
    seen: dict[str, int] = {}
    dups: list[tuple[str, int, int]] = []
    for name, lineno in funcs:
        if name in seen:
            dups.append((name, seen[name], lineno))
        else:
            seen[name] = lineno
    return dups


def test_no_shadowed_tests() -> None:
    """同文件顶层与同类体内不得出现重复 test_ 函数（防止静默覆盖缩水）。"""
    problems: list[str] = []
    for path in _iter_test_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rel = path.relative_to(_PROJECT_ROOT)

        top_level = [
            (n.name, n.lineno)
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")
        ]
        for name, first, shadowed in _collect_dups(top_level):
            problems.append(f"{rel}: 顶层 {name} L{first} 被 L{shadowed} 遮蔽")

        for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            methods = [
                (n.name, n.lineno)
                for n in cls.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name.startswith("test_")
            ]
            for name, first, shadowed in _collect_dups(methods):
                problems.append(f"{rel}::{cls.name}: {name} L{first} 被 L{shadowed} 遮蔽")

    assert not problems, (
        "发现同文件/同类内重名 test_ 函数（后者覆盖前者，前者静默不执行），"
        "请重命名以保留全部断言：\n" + "\n".join(problems)
    )
