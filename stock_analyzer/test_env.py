"""测试 env.py — 环境变量加载和解析"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest

from stock_analyzer.env import get_env, get_env_int, get_env_float, get_env_bool, load_env


class TestGetEnv(unittest.TestCase):
    """get_env 基础功能测试"""

    def test_get_env_exists(self):
        """获取已存在的环境变量"""
        os.environ["_TEST_VAR"] = "hello"
        self.assertEqual(get_env("_TEST_VAR"), "hello")
        del os.environ["_TEST_VAR"]

    def test_get_env_default(self):
        """不存在的变量返回默认值"""
        self.assertEqual(get_env("_NONEXIST_TEST_VAR", "fallback"), "fallback")

    def test_get_env_default_empty(self):
        """默认值为空字符串"""
        self.assertEqual(get_env("_NONEXIST_TEST_VAR2"), "")


class TestGetEnvInt(unittest.TestCase):
    """get_env_int 解析测试"""

    def test_get_env_int_valid(self):
        """正常整数解析"""
        os.environ["_TEST_INT"] = "42"
        self.assertEqual(get_env_int("_TEST_INT"), 42)
        del os.environ["_TEST_INT"]

    def test_get_env_int_default(self):
        """不存在的变量返回默认整数"""
        self.assertEqual(get_env_int("_NONEXIST_INT", 100), 100)

    def test_get_env_int_invalid(self):
        """非法整数返回默认值"""
        os.environ["_TEST_INT_BAD"] = "not_a_number"
        self.assertEqual(get_env_int("_TEST_INT_BAD", 99), 99)
        del os.environ["_TEST_INT_BAD"]

    def test_get_env_int_negative(self):
        """负整数解析"""
        os.environ["_TEST_INT_NEG"] = "-7"
        self.assertEqual(get_env_int("_TEST_INT_NEG"), -7)
        del os.environ["_TEST_INT_NEG"]


class TestGetEnvFloat(unittest.TestCase):
    """get_env_float 解析测试"""

    def test_get_env_float_valid(self):
        """正常浮点数解析"""
        os.environ["_TEST_FLOAT"] = "3.14"
        self.assertAlmostEqual(get_env_float("_TEST_FLOAT"), 3.14)
        del os.environ["_TEST_FLOAT"]

    def test_get_env_float_default(self):
        """不存在的变量返回默认浮点数"""
        self.assertEqual(get_env_float("_NONEXIST_FLOAT", 2.5), 2.5)

    def test_get_env_float_invalid(self):
        """非法浮点数返回默认值"""
        os.environ["_TEST_FLOAT_BAD"] = "pi"
        self.assertEqual(get_env_float("_TEST_FLOAT_BAD", 1.0), 1.0)
        del os.environ["_TEST_FLOAT_BAD"]

    def test_get_env_float_integer_string(self):
        """整数字符串解析为浮点数"""
        os.environ["_TEST_FLOAT_INT"] = "5"
        self.assertEqual(get_env_float("_TEST_FLOAT_INT"), 5.0)
        del os.environ["_TEST_FLOAT_INT"]


class TestGetEnvBool(unittest.TestCase):
    """get_env_bool 解析测试"""

    def test_get_env_bool_true_variants(self):
        """多种 true 表示法"""
        for val in ("true", "True", "TRUE", "1", "yes", "YES", "on", "ON"):
            os.environ["_TEST_BOOL"] = val
            self.assertTrue(get_env_bool("_TEST_BOOL"), f"'{val}' should be True")
            del os.environ["_TEST_BOOL"]

    def test_get_env_bool_false_variants(self):
        """其他值为 False"""
        for val in ("false", "False", "0", "no", "off", "", "anything_else"):
            os.environ["_TEST_BOOL"] = val
            self.assertFalse(get_env_bool("_TEST_BOOL"), f"'{val}' should be False")
            del os.environ["_TEST_BOOL"]

    def test_get_env_bool_default(self):
        """默认值测试"""
        self.assertFalse(get_env_bool("_NONEXIST_BOOL"))
        self.assertTrue(get_env_bool("_NONEXIST_BOOL", True))


class TestLoadEnv(unittest.TestCase):
    """load_env 测试"""

    def test_load_env_returns_bool(self):
        """返回 bool 类型"""
        result = load_env()
        self.assertIsInstance(result, bool)

    def test_load_env_does_not_crash(self):
        """多次调用不报错"""
        try:
            load_env()
            load_env()
            load_env()
        except Exception as e:
            self.fail(f"load_env raised: {e}")

    def test_load_env_idempotent(self):
        """幂等且不改变已有环境变量覆盖行为"""
        os.environ["_IDEMPOTENT_TEST"] = "original"
        load_env()
        # dotenv 使用 override=False，不会覆盖已有环境变量
        self.assertEqual(os.environ["_IDEMPOTENT_TEST"], "original")
        del os.environ["_IDEMPOTENT_TEST"]


if __name__ == "__main__":
    unittest.main()
