"""
统一环境变量加载模块 — 使用 python-dotenv 标准方式

优先级: 系统环境变量 > .env 文件 > 代码默认值

用法:
    from stock_analyzer.env import load_env
    load_env()  # 在应用启动时调用一次即可
"""

import os
from pathlib import Path

# 延迟导入 dotenv，避免未安装时启动失败
_dotenv_loaded = False


def _find_project_root() -> Path:
    """向上查找项目根目录（包含 .env 或 cli.py 的目录）"""
    current = Path(__file__).resolve().parent
    for _ in range(3):
        if (current / "cli.py").exists() or (current / ".env").exists():
            return current
        current = current.parent
    return Path(__file__).resolve().parent.parent  # fallback


def load_env(env_file: str | None = None) -> bool:
    """
    加载 .env 文件到环境变量。
    返回 True 表示成功加载，False 表示 dotenv 未安装或文件不存在。
    """
    global _dotenv_loaded
    if _dotenv_loaded:
        return True

    try:
        from dotenv import load_dotenv
    except ImportError:
        # python-dotenv 未安装，静默跳过（环境变量仍可通过系统设置）
        return False

    project_root = _find_project_root()
    env_path = env_file or str(project_root / ".env")

    if os.path.exists(env_path):
        load_dotenv(env_path, override=False)
        _dotenv_loaded = True
        return True

    # 尝试默认 .env
    default_env = str(project_root / ".env")
    if os.path.exists(default_env):
        load_dotenv(default_env, override=False)
        _dotenv_loaded = True
        return True

    return False


def get_env(key: str, default: str = "") -> str:
    """获取环境变量，带默认值（先尝试加载 .env）"""
    load_env()
    return os.environ.get(key, default)


def get_env_int(key: str, default: int = 0) -> int:
    """获取整数类型环境变量"""
    val = get_env(key, str(default))
    try:
        return int(val)
    except ValueError:
        return default


def get_env_float(key: str, default: float = 0.0) -> float:
    """获取浮点数类型环境变量"""
    val = get_env(key, str(default))
    try:
        return float(val)
    except ValueError:
        return default


def get_env_bool(key: str, default: bool = False) -> bool:
    """获取布尔类型环境变量（支持 true/1/yes 为 True）"""
    val = get_env(key, str(default)).lower()
    return val in ("true", "1", "yes", "on")
