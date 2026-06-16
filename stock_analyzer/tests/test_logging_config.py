"""测试 logging_config.py — 统一日志系统"""

import logging
import os
import sys
import unittest

from stock_analyzer.logging_config import get_logger, init_logging

class TestLoggingConfig(unittest.TestCase):
    """日志配置测试"""

    def test_get_logger_returns_logger(self):
        """get_logger 返回 Logger 实例"""
        logger = get_logger("test_module")
        self.assertIsInstance(logger, logging.Logger)

    def test_get_logger_has_stock_analyzer_prefix(self):
        """获取的 logger 名称有 stock_analyzer 前缀"""
        logger = get_logger("my_module")
        self.assertTrue(logger.name.startswith("stock_analyzer."))

    def test_get_logger_same_name_same_instance(self):
        """相同名称返回同一个 logger 实例"""
        l1 = get_logger("dup_test")
        l2 = get_logger("dup_test")
        self.assertIs(l1, l2)

    def test_root_logger_has_handlers(self):
        """stock_analyzer 根 logger 有 handler"""
        root = logging.getLogger("stock_analyzer")
        self.assertGreater(len(root.handlers), 0, "root logger should have handlers")

    def test_init_logging_idempotent(self):
        """init_logging 多次调用不报错"""
        try:
            init_logging()
            init_logging()
            init_logging()
        except Exception as e:
            self.fail(f"init_logging raised: {e}")

    def test_logger_info(self):
        """logger.info 不报错"""
        logger = get_logger("test_info")
        try:
            logger.info("test message")
            logger.debug("debug message")
            logger.warning("warning message")
        except Exception as e:
            self.fail(f"logger methods raised: {e}")

if __name__ == "__main__":
    unittest.main()
