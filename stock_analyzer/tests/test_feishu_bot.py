"""测试 feishu_bot.py — 飞书群机器人消息发送"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from stock_analyzer.feishu_bot import (
    _post,
    _webhook_url,
    send_alert,
    send_post,
    send_text,
)


class TestWebhookURL(unittest.TestCase):
    """_webhook_url 获取 Webhook URL（env.py 统一加载 .env 文件）"""

    @patch.dict(os.environ, {"FEISHU_WEBHOOK_URL": "https://open.feishu.cn/hook/test"}, clear=True)
    def test_from_env_var(self):
        """优先从环境变量读取"""
        self.assertEqual(_webhook_url(), "https://open.feishu.cn/hook/test")

    @patch.dict(os.environ, {}, clear=True)
    def test_no_url_configured(self):
        """没有任何配置时返回空字符串"""
        self.assertEqual(_webhook_url(), "")

    @patch.dict(os.environ, {"FEISHU_WEBHOOK_URL": ""}, clear=True)
    def test_empty_env_var(self):
        """环境变量为空字符串"""
        self.assertEqual(_webhook_url(), "")


class TestPost(unittest.TestCase):
    """_post 底层 HTTP 请求"""

    @patch("stock_analyzer.feishu_bot.urllib.request.urlopen")
    def test_successful_post(self, mock_urlopen):
        """正常返回 → 解析成功"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"code": 0}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = _post("https://example.com", {"msg_type": "text"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["response"]["code"], 0)

    @patch("stock_analyzer.feishu_bot.urllib.request.urlopen")
    def test_success_with_statuscode(self, mock_urlopen):
        """StatusCode=0 也视为成功"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"StatusCode": 0}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = _post("https://example.com", {})
        self.assertTrue(result["ok"])

    @patch("stock_analyzer.feishu_bot.urllib.request.urlopen")
    def test_failed_post(self, mock_urlopen):
        """非零 code → 失败"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"code": 10001, "msg": "invalid"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = _post("https://example.com", {})
        self.assertFalse(result["ok"])

    @patch("stock_analyzer.feishu_bot.urllib.request.urlopen")
    def test_http_error(self, mock_urlopen):
        """HTTPError 处理"""
        import urllib.error

        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://example.com",
            403,
            "Forbidden",
            {},
            None,  # type: ignore[arg-type]
        )
        result = _post("https://example.com", {})
        self.assertFalse(result["ok"])
        self.assertIn("HTTP 403", result["error"])

    @patch("stock_analyzer.feishu_bot.urllib.request.urlopen")
    def test_generic_exception(self, mock_urlopen):
        """其他异常"""
        mock_urlopen.side_effect = ConnectionError("network unavailable")
        result = _post("https://example.com", {})
        self.assertFalse(result["ok"])
        self.assertIn("network unavailable", result["error"])


class TestSendText(unittest.TestCase):
    """send_text 纯文本消息"""

    def test_no_webhook_returns_error(self):
        """未配置 Webhook → 返回错误"""
        with patch("stock_analyzer.feishu_bot._webhook_url", return_value=""):
            result = send_text("测试消息")
            self.assertFalse(result["ok"])
            self.assertIn("未配置", result["error"])

    @patch("stock_analyzer.feishu_bot._post")
    @patch("stock_analyzer.feishu_bot._webhook_url", return_value="https://hook.test")
    def test_send_text_content(self, mock_url, mock_post):
        """正确构造 payload"""
        mock_post.return_value = {"ok": True}
        result = send_text("hello world")
        self.assertTrue(result["ok"])
        # 验证 payload 结构
        call_args = mock_post.call_args[0]
        self.assertEqual(call_args[0], "https://hook.test")
        self.assertEqual(call_args[1]["msg_type"], "text")
        self.assertEqual(call_args[1]["content"]["text"], "hello world")


class TestSendPost(unittest.TestCase):
    """send_post 富文本消息"""

    def test_no_webhook_returns_error(self):
        """未配置 Webhook → 返回错误"""
        with patch("stock_analyzer.feishu_bot._webhook_url", return_value=""):
            result = send_post("标题", [[{"tag": "text", "text": "内容"}]])
            self.assertFalse(result["ok"])

    @patch("stock_analyzer.feishu_bot._post")
    @patch("stock_analyzer.feishu_bot._webhook_url", return_value="https://hook.test")
    def test_send_post_content(self, mock_url, mock_post):
        """正确构造富文本 payload"""
        mock_post.return_value = {"ok": True}
        paragraphs = [
            [{"tag": "text", "text": "第一行"}],
            [{"tag": "a", "text": "链接", "href": "https://example.com"}],
        ]
        result = send_post("测试标题", paragraphs)
        self.assertTrue(result["ok"])
        call_payload = mock_post.call_args[0][1]
        self.assertEqual(call_payload["msg_type"], "post")
        zh_cn = call_payload["content"]["post"]["zh_cn"]
        self.assertEqual(zh_cn["title"], "测试标题")
        self.assertEqual(zh_cn["content"], paragraphs)


class TestSendAlert(unittest.TestCase):
    """send_alert 预警消息"""

    @patch("stock_analyzer.feishu_bot._post")
    @patch("stock_analyzer.feishu_bot._webhook_url", return_value="https://hook.test")
    def test_alert_format(self, mock_url, mock_post):
        """正确构造预警文本格式"""
        mock_post.return_value = {"ok": True}
        result = send_alert("止损提醒", "000001 触及止损价 12.50")
        self.assertTrue(result["ok"])
        text = mock_post.call_args[0][1]["content"]["text"]
        self.assertIn("止损提醒", text)
        self.assertIn("000001", text)

    @patch("stock_analyzer.feishu_bot._webhook_url", return_value="https://hook.test")
    @patch("stock_analyzer.feishu_bot._post")
    def test_alert_passes_webhook(self, mock_post, mock_url):
        """自定义 webhook_url 被传递"""
        mock_post.return_value = {"ok": True}
        send_alert("测试", "内容", webhook_url="https://custom.hook/test")
        self.assertEqual(mock_post.call_args[0][0], "https://custom.hook/test")


if __name__ == "__main__":
    unittest.main()
