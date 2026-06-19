#!/usr/bin/env python3
"""
Conventional Commits 格式验证器

格式: <type>[(scope)]: <description>
示例:
  feat(strategy): 添加布林带策略
  fix(execution): 修复止损价计算错误
  docs: 更新 API 文档
  test: 增加回测引擎单元测试
  ci: 添加安全扫描流水线

用法（作为 commit-msg hook）:
  ./scripts/check-commit-msg.py .git/COMMIT_MSG
  或通过 pre-commit: 配置 commit-msg stage
"""

import re
import sys

VALID_TYPES = [
    "feat",  # 新功能
    "fix",  # Bug 修复
    "docs",  # 文档
    "test",  # 测试
    "refactor",  # 重构
    "perf",  # 性能优化
    "ci",  # CI/CD
    "chore",  # 杂务
    "deps",  # 依赖更新
    "style",  # 代码格式
    "build",  # 构建系统
    "revert",  # 回滚
]

PATTERN = re.compile(
    r"^(" + "|".join(VALID_TYPES) + r")"
    r"(\([a-z0-9\-]+\))?"  # 可选 scope
    r"!?"  # 可选 breaking change 标记
    r": .{3,100}$"  # 冒号 + 空格 + 描述(3-100字符)
)

MERGE_PATTERN = re.compile(r"^Merge (branch|pull request|remote)")
REVERT_PATTERN = re.compile(r'^Revert "')


def validate(msg: str) -> tuple[bool, str]:
    """验证提交信息格式，返回 (是否通过, 错误信息)。"""
    # 取第一行
    first_line = msg.strip().split("\n")[0].strip()

    if not first_line:
        return False, "提交信息不能为空"

    # 跳过 merge/revert 自动生成的消息
    if MERGE_PATTERN.match(first_line) or REVERT_PATTERN.match(first_line):
        return True, ""

    if PATTERN.match(first_line):
        return True, ""

    # 构造帮助信息
    types_str = ", ".join(VALID_TYPES)
    return False, (
        f"❌ 提交信息不符合 Conventional Commits 规范\n"
        f"\n"
        f"  当前: {first_line}\n"
        f"  格式: <type>[(scope)]: <description>\n"
        f"\n"
        f"  可用 type: {types_str}\n"
        f"\n"
        f"  示例:\n"
        f"    feat(strategy): 添加布林带策略\n"
        f"    fix(backtest): 修复夏普比率计算\n"
        f"    docs: 更新部署文档\n"
    )


def main():
    if len(sys.argv) < 2:
        print("Usage: check-commit-msg.py <commit-msg-file>")
        sys.exit(1)

    msg_file = sys.argv[1]
    with open(msg_file, encoding="utf-8") as f:
        msg = f.read()

    ok, error = validate(msg)
    if not ok:
        print(error, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
