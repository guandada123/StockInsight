"""
StockInsight Backend — 异常处理模块单元测试

覆盖:
  - _error_response 结构完整性
  - 各异常处理器正确返回 JSONResponse
  - trace_id_middleware 的回写与自动生成
  - register_exception_handlers 注册后生效
"""

import sys
from unittest.mock import MagicMock

# ── 模块级: mock stock_analyzer before importing app ──
_ORIG_SA = sys.modules.get("stock_analyzer")
_mock_sa = MagicMock()
sys.modules["stock_analyzer"] = _mock_sa

# 不触发 setup_logging 文件写入（测试不需要持久化日志）
# 手动清空 root logger handlers 避免干扰
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

# 由于 test_exceptions.py 在 test_api_integration.py 之前被 collection，
# 此处直接 import app 不会与 conftest 冲突
from backend.exceptions import (
    _error_response,
    register_exception_handlers,
    trace_id_middleware,
)

for h in logging.root.handlers[:]:
    logging.root.removeHandler(h)

# 创建一个干净的测试 app
_test_app = FastAPI()
register_exception_handlers(_test_app)
_test_app.middleware("http")(trace_id_middleware)


@_test_app.get("/test/unhandled")
async def _crash():
    raise RuntimeError("simulated crash")


_client = TestClient(_test_app)


# 恢复 stock_analyzer
if _ORIG_SA is not None:
    sys.modules["stock_analyzer"] = _ORIG_SA
else:
    sys.modules.pop("stock_analyzer", None)


class TestErrorResponseStructure:
    def test_basic_fields(self):
        """_error_response 返回带 code/message/detail/trace_id 的 JSONResponse"""
        resp = _error_response(400, "bad request", trace_id="abc")
        assert resp.status_code == 400
        body = resp.body.decode()
        import json

        parsed = json.loads(body)
        assert parsed["code"] == 400
        assert parsed["message"] == "bad request"
        assert parsed["detail"] is None
        assert parsed["trace_id"] == "abc"

    def test_with_detail(self):
        """detail 字段支持任意类型"""
        resp = _error_response(
            422, "validation failed", detail=[{"field": "name", "msg": "required"}]
        )
        assert resp.status_code == 422
        import json

        parsed = json.loads(resp.body.decode())
        assert parsed["detail"] == [{"field": "name", "msg": "required"}]


class TestExceptionHandlers:
    def test_404_from_handler(self):
        """未定义路由返回统一格式 404"""
        resp = _client.get("/nonexistent")
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == 404
        assert "trace_id" in body

    def test_500_from_handler(self):
        """未捕获异常返回统一格式 500"""
        resp = _client.get("/test/unhandled")
        assert resp.status_code == 500
        body = resp.json()
        assert body["code"] == 500
        assert "trace_id" in body

    def test_trace_id_roundtrip(self):
        """X-Request-ID 从请求头传递至响应头"""
        resp = _client.get("/test/unhandled", headers={"X-Request-ID": "echo-123"})
        assert resp.headers.get("X-Request-ID") == "echo-123"

    def test_trace_id_auto_generate(self):
        """不传 X-Request-ID 时自动生成"""
        resp = _client.get("/test/unhandled")
        trace = resp.headers.get("X-Request-ID")
        assert trace is not None
        assert len(trace) > 0

    def test_handler_registration(self):
        """register_exception_handlers 注册后异常被捕获而不是返回纯文本"""
        app = FastAPI()
        register_exception_handlers(app)
        # 测试注册后 404 返回 JSON
        from starlette.testclient import TestClient as TC

        with TC(app) as c:
            resp = c.get("/nonexistent")
            assert resp.status_code == 404
            assert resp.headers.get("content-type", "").startswith("application/json")
