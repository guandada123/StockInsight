"""测试 self_audit.py — 自审计模块

AuditReport 是纯逻辑类，可以在不 mock 任何依赖的情况下完整测试。
_clear_cache_pattern 和 _preload_name_map 需要 mock 内部依赖。
run_audit 通过 patch 各个审计函数来验证编排逻辑。
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
class TestAuditReport(unittest.TestCase):
    """AuditReport 数据收集与摘要"""

    def setUp(self):
        from stock_analyzer.self_audit import AuditReport
        self.report = AuditReport()

    def test_initial_state(self):
        """初始状态全空"""
        self.assertEqual(self.report.issues, [])
        self.assertEqual(self.report.fixes, [])
        self.assertEqual(self.report.warnings, [])
        self.assertEqual(self.report.passed, [])
        self.assertFalse(self.report.has_issues())

    def test_fail_adds_issue(self):
        """fail() → 增加问题记录"""
        self.report.fail("测试", "出错了", "修复方法")
        self.assertTrue(self.report.has_issues())
        self.assertEqual(len(self.report.issues), 1)
        self.assertEqual(self.report.issues[0]["category"], "测试")
        self.assertEqual(self.report.issues[0]["detail"], "出错了")
        self.assertEqual(self.report.issues[0]["fix"], "修复方法")

    def test_fail_without_fix(self):
        """fail() 可不带 fix 参数"""
        self.report.fail("测试", "出错了")
        self.assertIsNone(self.report.issues[0].get("fix"))

    def test_warn_adds_warning(self):
        """warn() → 增加警告记录"""
        self.report.warn("性能", "响应慢")
        self.assertEqual(len(self.report.warnings), 1)
        self.assertEqual(self.report.warnings[0]["category"], "性能")

    def test_ok_adds_passed(self):
        """ok() → 增加通过记录"""
        self.report.ok("行情", "正常")
        self.assertEqual(len(self.report.passed), 1)

    def test_fixed_adds_fix(self):
        """fixed() → 增加修复记录"""
        self.report.fixed("缓存", "已清理")
        self.assertEqual(len(self.report.fixes), 1)

    def test_has_issues_true(self):
        """有 issues 时 has_issues 返回 True"""
        self.report.fail("测试", "问题")
        self.assertTrue(self.report.has_issues())

    def test_summary_includes_counts(self):
        """summary() 包含各项计数"""
        self.report.ok("A", "通过")
        self.report.fail("B", "失败")
        self.report.warn("C", "警告")
        self.report.fixed("D", "修复")
        s = self.report.summary()
        self.assertIn("1个问题", s)
        self.assertIn("1个已修复", s)
        self.assertIn("1个警告", s)
        self.assertIn("1个通过", s)

    def test_summary_with_issues_includes_fix_suggestion(self):
        """有问题且有 fix → 摘要中显示建议修复"""
        self.report.fail("键名一致性", "缺少键", "检查 quant.py")
        s = self.report.summary()
        self.assertIn("建议修复", s)
        self.assertIn("检查 quant.py", s)

    def test_summary_no_issues_omits_section(self):
        """无问题时摘要不显示问题区块"""
        s = self.report.summary()
        self.assertNotIn("需处理", s)

    def test_multiple_issues_formatted(self):
        """多个问题正确格式化"""
        self.report.fail("A", "问题1")
        self.report.fail("B", "问题2")
        s = self.report.summary()
        self.assertIn("[A] 问题1", s)
        self.assertIn("[B] 问题2", s)

class TestClearCachePattern(unittest.TestCase):
    """_clear_cache_pattern 缓存清理"""

    def test_successful_clear(self):
        """正常清除 → 返回 True"""
        from stock_analyzer.self_audit import _clear_cache_pattern

        mock_conn = MagicMock()
        with patch("stock_analyzer.cache._get_conn", return_value=mock_conn):
            result = _clear_cache_pattern("fundflow:%")
            self.assertTrue(result)
            mock_conn.execute.assert_called_once_with(
                "DELETE FROM cache WHERE key LIKE ?", ("fundflow:%",)
            )
            mock_conn.commit.assert_called_once()

    def test_exception_returns_false(self):
        """异常 → 返回 False"""
        from stock_analyzer.self_audit import _clear_cache_pattern

        with patch("stock_analyzer.cache._get_conn", side_effect=Exception("DB locked")):
            result = _clear_cache_pattern("test:%")
            self.assertFalse(result)

class TestPreloadNameMap(unittest.TestCase):
    """_preload_name_map 名称映射预加载"""

    def test_successful_preload(self):
        """正常加载 → 返回 True"""
        from stock_analyzer.self_audit import _preload_name_map

        with patch("stock_analyzer.fetcher._load_stock_name_map") as mock_load:
            result = _preload_name_map()
            self.assertTrue(result)
            mock_load.assert_called_once()

    def test_exception_returns_false(self):
        """异常 → 返回 False"""
        from stock_analyzer.self_audit import _preload_name_map

        with patch("stock_analyzer.fetcher._load_stock_name_map",
                   side_effect=Exception("Network error")):
            result = _preload_name_map()
            self.assertFalse(result)

class TestRunAudit(unittest.TestCase):
    """run_audit 主入口编排"""

    def test_run_without_auto_fix(self):
        """auto_fix=False 跳过自动修复"""
        from stock_analyzer.self_audit import run_audit

        # 把 AUTO_FIX_LIST 清空 + 用 sentinel 检查跳过
        with patch("stock_analyzer.self_audit.AUTO_FIX_LIST", []):
            # mock 所有审计函数，避免真正执行
            with patch("stock_analyzer.self_audit.audit_api_data_consistency") as mock_a1:
                with patch("stock_analyzer.self_audit.audit_internal_key_consistency") as mock_a2:
                    with patch("stock_analyzer.self_audit.audit_cross_source_validation") as mock_a3:
                        with patch("stock_analyzer.self_audit.audit_score_validity") as mock_a4:
                            with patch("stock_analyzer.self_audit.audit_performance") as mock_a5:
                                with patch("stock_analyzer.self_audit.audit_fund_flow_sign") as mock_a6:
                                    with patch("stock_analyzer.self_audit.audit_api_health") as mock_a7:
                                        with patch("stock_analyzer.self_audit.audit_storage_benchmark") as mock_a8:
                                            report = run_audit(auto_fix=False, verbose=False)

        # 所有审计函数都被调用
        mock_a1.assert_called_once()
        mock_a2.assert_called_once()
        mock_a3.assert_called_once()
        mock_a4.assert_called_once()
        mock_a5.assert_called_once()
        mock_a6.assert_called_once()
        mock_a7.assert_called_once()
        mock_a8.assert_called_once()

        # 返回的是 AuditReport 实例
        from stock_analyzer.self_audit import AuditReport
        self.assertIsInstance(report, AuditReport)

    def test_audit_function_error_caught(self):
        """审计函数抛出异常 → 被捕获并记录为问题"""
        from stock_analyzer.self_audit import run_audit

        with patch("stock_analyzer.self_audit.AUTO_FIX_LIST", []):
            with patch("stock_analyzer.self_audit.audit_api_data_consistency",
                       side_effect=ValueError("模拟错误")):
                with patch("stock_analyzer.self_audit.audit_internal_key_consistency"):
                    with patch("stock_analyzer.self_audit.audit_cross_source_validation"):
                        with patch("stock_analyzer.self_audit.audit_score_validity"):
                            with patch("stock_analyzer.self_audit.audit_performance"):
                                with patch("stock_analyzer.self_audit.audit_fund_flow_sign"):
                                    with patch("stock_analyzer.self_audit.audit_api_health"):
                                        with patch("stock_analyzer.self_audit.audit_storage_benchmark"):
                                            report = run_audit(auto_fix=False, verbose=False)

        # 应有一个问题记录（异常的哪个审计步骤）
        self.assertTrue(report.has_issues())
        issue_categories = [i["category"] for i in report.issues]
        self.assertIn("数据一致性", issue_categories)

    def test_auto_fix_runs_before_audit(self):
        """auto_fix=True → 先执行 AUTO_FIX_LIST 再跑审计"""
        from stock_analyzer.self_audit import run_audit

        mock_action = MagicMock(return_value=True)
        fake_auto_fix = [
            {"id": "test_fix", "desc": "测试自动修复", "action": mock_action},
        ]

        with patch("stock_analyzer.self_audit.AUTO_FIX_LIST", fake_auto_fix):
            with patch("stock_analyzer.self_audit.audit_api_data_consistency"):
                with patch("stock_analyzer.self_audit.audit_internal_key_consistency"):
                    with patch("stock_analyzer.self_audit.audit_cross_source_validation"):
                        with patch("stock_analyzer.self_audit.audit_score_validity"):
                            with patch("stock_analyzer.self_audit.audit_performance"):
                                with patch("stock_analyzer.self_audit.audit_fund_flow_sign"):
                                    with patch("stock_analyzer.self_audit.audit_api_health"):
                                        with patch("stock_analyzer.self_audit.audit_storage_benchmark"):
                                            report = run_audit(auto_fix=True, verbose=False)

        mock_action.assert_called_once()

if __name__ == "__main__":
    unittest.main()
