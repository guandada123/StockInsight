"""测试 config.py — 配置常量有效性验证"""

import os
import sys
import unittest

from stock_analyzer import config


class TestConfigPaths(unittest.TestCase):
    """路径常量测试"""

    def test_root_dir_exists(self):
        """项目根目录存在"""
        self.assertTrue(os.path.isdir(config.ROOT_DIR))

    def test_db_path_in_root(self):
        """数据库路径在项目根下"""
        self.assertTrue(config.DB_PATH.startswith(config.ROOT_DIR))

    def test_report_dir_exists(self):
        """reports 目录已创建"""
        self.assertTrue(os.path.isdir(config.REPORT_DIR))

    def test_log_dir_exists(self):
        """logs 目录已创建"""
        self.assertTrue(os.path.isdir(config.LOG_DIR))

    def test_all_paths_are_strings(self):
        """所有路径常量是字符串"""
        for attr in [
            "DB_PATH",
            "REPORT_DIR",
            "CHART_DIR",
            "PORTFOLIO_DIR",
            "LOG_DIR",
            "ARCHIVE_DIR",
            "ALERTS_PATH",
            "ALERTS_LOG_PATH",
            "STOCK_LIST_CACHE",
            "CHECKPOINT_FILE",
        ]:
            self.assertIsInstance(getattr(config, attr), str, f"{attr} should be str")


class TestConfigAPI(unittest.TestCase):
    """API 请求配置测试"""

    def test_headers_is_dict(self):
        """HEADERS 是字典"""
        self.assertIsInstance(config.HEADERS, dict)
        self.assertIn("User-Agent", config.HEADERS)

    def test_api_hosts_not_empty(self):
        """API_HOSTS 非空"""
        self.assertGreater(len(config.API_HOSTS), 0)

    def test_kline_periods(self):
        """KLINE_PERIODS 包含 daily/weekly/monthly"""
        self.assertIn("daily", config.KLINE_PERIODS)
        self.assertIn("weekly", config.KLINE_PERIODS)
        self.assertIn("monthly", config.KLINE_PERIODS)

    def test_adjust_types(self):
        """ADJUST 包含 qfq/hfq/none"""
        self.assertIn("qfq", config.ADJUST)
        self.assertIn("hfq", config.ADJUST)
        self.assertIn("none", config.ADJUST)


class TestConfigAnalysis(unittest.TestCase):
    """技术分析参数测试"""

    def test_ma_windows(self):
        """均线窗口包含常用周期"""
        self.assertIn(5, config.MA_WINDOWS)
        self.assertIn(20, config.MA_WINDOWS)
        self.assertIn(60, config.MA_WINDOWS)

    def test_macd_params_positive(self):
        """MACD 参数为正"""
        self.assertGreater(config.MACD_FAST, 0)
        self.assertGreater(config.MACD_SLOW, config.MACD_FAST)
        self.assertGreater(config.MACD_SIGNAL, 0)

    def test_rsi_period_positive(self):
        """RSI 周期为正"""
        self.assertGreater(config.RSI_PERIOD, 0)

    def test_bb_params(self):
        """布林带参数合理"""
        self.assertGreater(config.BB_PERIOD, 0)
        self.assertGreater(config.BB_STD_DEV, 0)


class TestConfigQuant(unittest.TestCase):
    """量化参数测试"""

    def test_risk_free_rate_range(self):
        """无风险利率在合理范围内"""
        self.assertGreater(config.RISK_FREE_RATE, 0)
        self.assertLess(config.RISK_FREE_RATE, 0.2)

    def test_var_confidence_range(self):
        """VaR 置信度在 0-1 之间"""
        self.assertGreater(config.VAR_CONFIDENCE, 0)
        self.assertLess(config.VAR_CONFIDENCE, 1)

    def test_factor_weights_sum_near_one(self):
        """因子权重之和约等于 1"""
        total = sum(config.QUANT_FACTOR_WEIGHTS.values())
        self.assertAlmostEqual(total, 1.0, delta=0.02)

    def test_factor_weight_keys(self):
        """因子权重包含必备因子"""
        expected = ["momentum", "technical", "fundamental", "volume", "risk"]
        for key in expected:
            self.assertIn(key, config.QUANT_FACTOR_WEIGHTS)

    def test_individual_weights_positive(self):
        """每个因子权重为正"""
        for w in config.QUANT_FACTOR_WEIGHTS.values():
            self.assertGreater(w, 0)


class TestConfigDefaults(unittest.TestCase):
    """默认参数测试"""

    def test_default_top_n(self):
        """默认选取 30 只"""
        self.assertEqual(config.DEFAULT_TOP_N, 30)

    def test_default_min_score(self):
        """默认最低评分 60"""
        self.assertEqual(config.DEFAULT_MIN_SCORE, 60)

    def test_cache_ttls_positive(self):
        """所有缓存 TTL 为正"""
        self.assertGreater(config.KLINE_CACHE_TTL, 0)
        self.assertGreater(config.FUNDAMENTALS_CACHE_TTL, 0)
        self.assertGreater(config.NT_HOLDINGS_CACHE_TTL, 0)

    def test_scan_workers_positive(self):
        """扫描线程数为正"""
        self.assertGreater(config.SCAN_WORKERS, 0)

    def test_mem_cache_max_reasonable(self):
        """内存缓存上限合理"""
        self.assertGreater(config.MEM_CACHE_MAX, 100)

    def test_env_vars_exist(self):
        """环境变量配置是字符串（可能为空）"""
        self.assertIsInstance(config.TUSHARE_TOKEN, str)
        self.assertIsInstance(config.FEISHU_WEBHOOK, str)
        self.assertIsInstance(config.FEISHU_CHAT_ID, str)
        self.assertIsInstance(config.DEEPSEEK_API_KEY, str)


if __name__ == "__main__":
    unittest.main()
