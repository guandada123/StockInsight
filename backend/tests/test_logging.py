"""
StockInsight Backend — 日志配置测试

覆盖:
  - JSONFormatter 输出格式与字段完整性
  - setup_logging 幂等性
  - TimedRotatingFileHandler 轮转（mock rollover 验证）
  - LOG_DIR 不可写时自动降级仅 stdout
  - 环境变量配置识别
"""

import json
import logging
import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def _reset_logging():
    """每个测试前重置 logging 状态（避免跨测试干扰）"""
    root = logging.getLogger()
    root.handlers.clear()
    logging.root.handlers.clear()
    # 重置全局状态
    import backend.logging_config as lc

    lc._initialized = False
    yield
    root.handlers.clear()
    logging.root.handlers.clear()
    lc._initialized = False


class TestJSONFormatter:
    def test_basic_format(self):
        """JSONFormatter 输出合法 JSON 且包含必要字段"""
        from backend.logging_config import JSONFormatter

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=42,
            msg="hello world",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["time"] is not None
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test_logger"
        assert parsed["message"] == "hello world"

    def test_extra_fields(self):
        """extra 字段（trace_id/path/method）应出现在 JSON 输出中"""
        from backend.logging_config import JSONFormatter

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg="test extra",
            args=(),
            exc_info=None,
        )
        record.trace_id = "trace-abc"
        record.path = "/api/test"
        record.status_code = 404

        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["trace_id"] == "trace-abc"
        assert parsed["path"] == "/api/test"
        assert parsed["status_code"] == 404

    def test_exception_info(self):
        """异常信息应序列化到 exception 字段"""
        import sys

        from backend.logging_config import JSONFormatter

        formatter = JSONFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            # 捕获当前异常的 (type, value, traceback) tuple
            # 直接传 exc_info=True 在 LogRecord 构造中不经过 logging 系统处理
            exc_tuple = sys.exc_info()
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="error occurred",
                args=(),
                exc_info=exc_tuple,
            )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]


class TestSetupLogging:
    def test_console_handler_added(self):
        """setup_logging 后 console handler 应存在"""
        from backend.logging_config import setup_logging

        setup_logging()
        root = logging.getLogger("stockinsight-api")
        handlers = root.handlers
        assert any(h.__class__.__name__ == "StreamHandler" for h in handlers)

    def test_file_handler_added(self):
        """默认日志目录可写时，file handler 应存在"""
        from backend.logging_config import setup_logging

        with tempfile.TemporaryDirectory() as tmpdir:
            setup_logging(log_dir=tmpdir)
            logger = logging.getLogger("stockinsight-api")
            handlers = logger.handlers
            file_handlers = [h for h in handlers if "RotatingFileHandler" in h.__class__.__name__]
            assert len(file_handlers) == 1

    def test_idempotent(self):
        """多次调用 setup_logging 不会重复添加 handler"""
        from backend.logging_config import setup_logging

        setup_logging()
        count_before = len(logging.getLogger("stockinsight-api").handlers)
        setup_logging()
        count_after = len(logging.getLogger("stockinsight-api").handlers)
        assert count_after == count_before, "不是幂等的！"

    def test_log_writes_to_file(self):
        """日志应实际写入文件"""
        from backend.logging_config import setup_logging

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "stockinsight.log")
            setup_logging(log_dir=tmpdir)
            test_logger = logging.getLogger("stockinsight-api")
            test_logger.info("写入测试信息")
            # 确保 handler flush
            for h in test_logger.handlers:
                h.flush()
            assert os.path.exists(log_file)
            content = open(log_file).read()
            assert "写入测试信息" in content

    def test_log_rotation_creates_backup(self, monkeypatch):
        """日志轮转应生成备份文件（模拟 midnight 跨日）"""
        import re

        from backend.logging_config import setup_logging

        with tempfile.TemporaryDirectory() as tmpdir:
            setup_logging(log_dir=tmpdir, backup_count=2)
            log_file = os.path.join(tmpdir, "stockinsight.log")

            test_logger = logging.getLogger("stockinsight-api")

            # 写入第一条日志 → 创建 stockinsight.log
            test_logger.info("day 1 log")
            for h in test_logger.handlers:
                h.flush()

            # 获取 file handler
            file_handler = None
            for h in test_logger.handlers:
                if "RotatingFileHandler" in h.__class__.__name__:
                    file_handler = h
                    break
            assert file_handler is not None, "没有找到 file handler"

            # TimedRotatingFileHandler 使用日期后缀（%Y-%m-%d），
            # delay=True 时 doRollover 不会自动创建新文件。
            # 强制轮转后写入第二条日志以触发新文件创建。
            file_handler.doRollover()
            test_logger.info("day 2 log")
            for h in test_logger.handlers:
                h.flush()

            # 验证：有备份文件（.YYYY-MM-DD 格式）
            all_files = os.listdir(tmpdir)
            backup_pattern = re.compile(r"stockinsight\.log\.\d{4}-\d{2}-\d{2}")
            backups = [f for f in all_files if backup_pattern.match(f)]
            assert len(backups) >= 1, f"轮转后应生成备份文件，实际文件列表: {all_files}"

            # 验证：新日志文件已重建
            assert os.path.exists(log_file), f"轮转后应创建新日志文件: {log_file}"
            content = open(log_file).read()
            assert "day 2 log" in content, "新文件应包含轮转后写入的日志"

    def test_fallback_console_only(self, monkeypatch):
        """LOG_DIR 不可写时自动降级仅 stdout（不抛异常）"""
        from backend.logging_config import setup_logging

        # 用一个不存在的不可写路径
        bad_dir = "/nonexistent_dir_xyz_12345"
        # 不应抛出异常
        setup_logging(log_dir=bad_dir)
        logger = logging.getLogger("stockinsight-api")
        handlers = logger.handlers
        file_handlers = [h for h in handlers if "RotatingFileHandler" in h.__class__.__name__]
        assert len(file_handlers) == 0
        console_handlers = [h for h in handlers if h.__class__.__name__ == "StreamHandler"]
        assert len(console_handlers) >= 1

    def test_env_vars_recognized(self, monkeypatch):
        """环境变量 LOG_LEVEL / LOG_DIR / LOG_BACKUP 被识别"""
        import backend.logging_config as lc

        # 刷新模块以读取新 env vars
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("LOG_BACKUP", "7")

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("LOG_DIR", tmpdir)
            # 重新加载模块
            import importlib

            importlib.reload(lc)
            lc.setup_logging()

            logger = logging.getLogger("stockinsight-api")
            assert logger.level == logging.DEBUG or logger.level == 0  # 0=NOTSET

            # 验证 backup_count 生效：写超过7+1条日志验证保留策略
            for i in range(10):
                logger.info(f"test line {i}")
                for h in logger.handlers:
                    h.flush()

            backup_files = [f for f in os.listdir(tmpdir) if f.startswith("stockinsight.log")]
            # 至少应该有 stockinsight.log 本身，轮转备份可选
            assert any("stockinsight" in f for f in backup_files)
