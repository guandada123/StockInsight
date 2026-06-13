"""统一日志配置 — 替换全项目 print() 调用

用法:
    from stock_analyzer.logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("...")
    logger.warning("...")
    logger.error("...")
"""

import logging
import os
import sys
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_initialized = False


def init_logging(level=logging.INFO, log_dir=None):
    """初始化全局日志系统（幂等，仅首次调用生效）"""
    global _initialized
    if _initialized:
        return
    _initialized = True

    if log_dir is None:
        log_dir = os.path.join(_ROOT, "logs")
    os.makedirs(log_dir, exist_ok=True)

    root_logger = logging.getLogger("stock_analyzer")
    root_logger.setLevel(level)

    # 格式
    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-5s %(name)s | %(message)s", datefmt="%m-%d %H:%M:%S"
    )

    # 文件输出（按日轮转）
    today = datetime.now().strftime("%Y%m%d")
    fh = logging.FileHandler(os.path.join(log_dir, f"stock_{today}.log"), encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(fmt)
    root_logger.addHandler(fh)

    # 错误日志单独记
    eh = logging.FileHandler(os.path.join(log_dir, f"error_{today}.log"), encoding="utf-8")
    eh.setLevel(logging.WARNING)
    eh.setFormatter(fmt)
    root_logger.addHandler(eh)

    # 控制台输出（仅 WARNING 以上，避免刷屏）
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.WARNING)
    ch.setFormatter(fmt)
    root_logger.addHandler(ch)


def get_logger(name):
    """获取模块级 logger（首次调用自动初始化）"""
    if not _initialized:
        init_logging()
    return logging.getLogger(f"stock_analyzer.{name}")


# 项目启动时自动初始化（导入即生效）
init_logging()
