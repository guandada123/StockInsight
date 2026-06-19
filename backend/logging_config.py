"""StockInsight Backend — 结构化日志配置

特性：
  - JSON 格式输出（便于容器采集）
  - 控制台（stdout）+ 文件双通道
  - 按日轮转（TimedRotatingFileHandler），保留 backup_count 天
  - 环境变量控制：LOG_LEVEL / LOG_DIR / LOG_BACKUP
  - Docker 兼容：LOG_DIR 不可写时自动降级仅 stdout

使用方式（在 main.py 中）：
    from backend.logging_config import setup_logging
    setup_logging()
"""

import json
import logging
import logging.config
import logging.handlers
import os
import sys
from datetime import UTC, datetime

# ── 默认常量 ──────────────────────────────────────────

_DEFAULT_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")

_LOG_DIR = os.environ.get("LOG_DIR", _DEFAULT_LOG_DIR)
_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
_LOG_BACKUP = int(os.environ.get("LOG_BACKUP", "14"))


class JSONFormatter(logging.Formatter):
    """结构化日志格式器 → JSON 行输出"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "time": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # 注入 extra 字段（由异常处理器/业务代码传入）
        for key in ("trace_id", "path", "method", "status_code", "error_type", "errors"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        # exc_info 可能是 bool True（直接构造 LogRecord 传参），
        # 也可能是 (type, value, traceback) tuple（logging 系统自动转换后）。
        # 仅当是 tuple 且有异常类型时才调用 formatException。
        if isinstance(record.exc_info, tuple) and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


def _build_dict_config(log_level: str, log_dir: str, backup_count: int) -> dict:
    """构建 logging dictConfig（可根据环境自定义）"""

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": JSONFormatter,
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "json",
                "stream": "ext://sys.stdout",
            },
            "file": {
                "class": "logging.handlers.TimedRotatingFileHandler",
                "level": log_level,
                "formatter": "json",
                "filename": os.path.join(log_dir, "stockinsight.log"),
                "when": "midnight",
                "interval": 1,
                "backupCount": backup_count,
                "encoding": "utf-8",
                "delay": True,
            },
        },
        "loggers": {
            "stockinsight-api": {
                "level": log_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "backend": {
                "level": log_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
        },
        "root": {
            "level": "WARNING",
            "handlers": ["console"],
        },
    }


_initialized = False


def setup_logging(
    log_level: str | None = None,
    log_dir: str | None = None,
    backup_count: int | None = None,
) -> None:
    """初始化结构化日志（幂等，仅首次生效）

    Args:
        log_level: 日志级别（默认 $LOG_LEVEL 或 INFO）
        log_dir:   日志目录（默认 $LOG_DIR 或项目根 logs/）
        backup_count: 文件保留天数（默认 $LOG_BACKUP 或 14）
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    level = (log_level or _LOG_LEVEL).upper()
    bdir = log_dir or _LOG_DIR
    bkp = backup_count or _LOG_BACKUP

    # 尝试创建日志目录（失败则降级仅 stdout）
    file_available = True
    try:
        os.makedirs(bdir, exist_ok=True)
    except (OSError, PermissionError):
        file_available = False
        # 打印一次到 stderr 告知降级（此时 dictConfig 尚未加载）
        sys.stderr.write(
            f"[logging_config] WARNING log_dir={bdir} not writable, "
            f"falling back to console-only output\n"
        )

    config = _build_dict_config(level, bdir, bkp)

    if not file_available:
        # 移除 file handler
        del config["handlers"]["file"]
        for log_name in config["loggers"]:
            config["loggers"][log_name]["handlers"] = ["console"]

    logging.config.dictConfig(config)
    logging.getLogger("stockinsight-api").info(
        "logging_initialized",
        extra={
            "log_level": level,
            "log_dir": bdir if file_available else "(console-only)",
            "backup_count": bkp if file_available else 0,
        },
    )
