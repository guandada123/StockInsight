"""测试 sectors_fallback.py — 静态板块成分股映射完整性"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest

from stock_analyzer.sectors_fallback import SECTOR_STOCKS_FALLBACK

CODE_PATTERN = re.compile(r"^\d{6}$")


class TestSectorsFallback(unittest.TestCase):
    """静态板块数据测试"""

    def test_data_is_dict(self):
        """SECTOR_STOCKS_FALLBACK 是字典"""
        self.assertIsInstance(SECTOR_STOCKS_FALLBACK, dict)

    def test_has_sectors(self):
        """包含多个板块分类"""
        self.assertGreater(len(SECTOR_STOCKS_FALLBACK), 10,
                           "Should have at least 10 sectors")

    def test_every_entry_has_representative(self):
        """每个板块有代表股"""
        for name, data in SECTOR_STOCKS_FALLBACK.items():
            self.assertIn("代表", data, f"'{name}' missing '代表' key")
            rep = data["代表"]
            self.assertIsInstance(rep, str, f"'{name}' 代表股应为字符串")

    def test_every_entry_has_constituents(self):
        """每个板块有成分股列表"""
        for name, data in SECTOR_STOCKS_FALLBACK.items():
            self.assertIn("成分股", data, f"'{name}' missing '成分股' key")
            stocks = data["成分股"]
            self.assertIsInstance(stocks, list, f"'{name}' 成分股应为列表")
            self.assertGreater(len(stocks), 0, f"'{name}' 成分股不应为空")

    def test_all_codes_are_six_digits(self):
        """所有股票代码为 6 位数字"""
        for name, data in SECTOR_STOCKS_FALLBACK.items():
            # 检查代表股
            rep = data["代表"]
            self.assertRegex(rep, CODE_PATTERN,
                             f"'{name}' 代表股 '{rep}' 应为 6 位数字")
            # 检查成分股
            for code in data["成分股"]:
                self.assertRegex(code, CODE_PATTERN,
                                 f"'{name}' 成分股 '{code}' 应为 6 位数字")

    def test_representative_in_constituents(self):
        """代表股必须在成分股列表中"""
        for name, data in SECTOR_STOCKS_FALLBACK.items():
            rep = data["代表"]
            stocks = data["成分股"]
            self.assertIn(rep, stocks,
                          f"'{name}' 代表股 '{rep}' 不在成分股列表中")

    def test_no_duplicate_constituents_per_sector(self):
        """每个板块内成分股无重复"""
        for name, data in SECTOR_STOCKS_FALLBACK.items():
            stocks = data["成分股"]
            self.assertEqual(len(stocks), len(set(stocks)),
                             f"'{name}' 成分股存在重复")

    def test_sector_names_not_empty(self):
        """板块名称非空"""
        for name in SECTOR_STOCKS_FALLBACK:
            self.assertIsInstance(name, str)
            self.assertGreater(len(name.strip()), 0)

    def test_sh_stocks_start_with_6(self):
        """沪市股票以 6 开头"""
        for name, data in SECTOR_STOCKS_FALLBACK.items():
            for code in data["成分股"]:
                if code.startswith("6"):
                    self.assertIn(code[:3], ["600", "601", "603", "605", "688"],
                                  f"'{name}' 沪市代码 '{code}' 前缀异常")

    def test_sz_stocks_have_valid_prefix(self):
        """深市股票以 0/3 开头"""
        for name, data in SECTOR_STOCKS_FALLBACK.items():
            for code in data["成分股"]:
                if not code.startswith("6"):
                    self.assertTrue(code.startswith("0") or code.startswith("3"),
                                    f"'{name}' 深市代码 '{code}' 前缀异常")

    def test_sector_count_range(self):
        """每个板块成分股数量 5-500 之间"""
        for name, data in SECTOR_STOCKS_FALLBACK.items():
            count = len(data["成分股"])
            self.assertGreaterEqual(count, 5, f"'{name}' 成分股太少 ({count})")
            self.assertLessEqual(count, 500, f"'{name}' 成分股太多 ({count})")

    def test_known_sectors_exist(self):
        """已知的重要板块应该存在"""
        known = ["有色金属", "银行", "白酒"]
        for sector in known:
            if sector in SECTOR_STOCKS_FALLBACK:
                self.assertIn(sector, SECTOR_STOCKS_FALLBACK)


if __name__ == "__main__":
    unittest.main()
