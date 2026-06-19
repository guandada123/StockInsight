"""StockInsight API — 统一异常处理模块

提供：
  1. trace_id 注入与传递
  2. 标准化 JSON 错误响应（code/message/detail/trace_id）
  3. 覆盖：HTTPException / RequestValidationError / 未捕获 Exception
  4. 结构化日志串联 trace_id 与请求上下文

使用方式（在 main.py 中）：
    from backend.exceptions import register_exception_handlers, trace_id_middleware
    register_exception_handlers(app)
    app.middleware("http")(trace_id_middleware)  # 必须最先注册（最外层）

注意：
  - HTTPException 和 RequestValidationError 通过 FastAPI 异常处理器处理
  - 通用 Exception 在 trace_id_middleware 中捕获，避免 Starlette
    BaseHTTPMiddleware 在异常处理器返回后仍 re-raise 的 bug (starlette#486)
"""

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("stockinsight-api")


# ── 统一错误响应结构 ──────────────────────────────────


def _error_response(
    code: int,
    message: str,
    detail: Any = None,
    trace_id: str = "",
) -> JSONResponse:
    """返回标准 JSON 错误响应"""
    return JSONResponse(
        status_code=code,
        content={
            "code": code,
            "message": message,
            "detail": detail,
            "trace_id": trace_id,
        },
    )


# ── 异常处理器 ──────────────────────────────────────────


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """处理 4xx HTTP 异常（404/400/405 等）"""
    trace_id = getattr(request.state, "trace_id", "")
    logger.warning(
        "http_exception",
        extra={
            "trace_id": trace_id,
            "path": request.url.path,
            "method": request.method,
            "status_code": exc.status_code,
            "detail": str(exc.detail),
        },
    )
    return _error_response(
        code=exc.status_code,
        message=str(exc.detail) if exc.status_code != 404 else "请求的资源不存在",
        detail=None,
        trace_id=trace_id,
    )


async def _validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """处理 422 参数校验失败"""
    trace_id = getattr(request.state, "trace_id", "")
    errors = exc.errors()
    logger.warning(
        "validation_error",
        extra={
            "trace_id": trace_id,
            "path": request.url.path,
            "method": request.method,
            "errors": errors,
        },
    )
    return _error_response(
        code=422,
        message="参数校验失败",
        detail=[
            {
                "loc": list(e.get("loc", [])),
                "msg": e.get("msg", ""),
                "type": e.get("type", ""),
            }
            for e in errors
        ],
        trace_id=trace_id,
    )


# ── 中间件：trace_id + 通用异常兜底 ──────────────────
# 两个职责合一，因为此中间件必须是最外层：
#   1. 最先读取 trace_id，确保后续所有代码能用 request.state.trace_id
#   2. 最外层 catch 所有从内层泄漏的异常，避免 Starlette
#      BaseHTTPMiddleware 在 exception_handler 返回后仍 re-raise
#
# 注意：如果在此中间件之前还有别的 HTTP middleware，
# 它们的异常将无法被兜底，所以必须最先注册。


async def trace_id_middleware(request: Request, call_next):
    """注入 & 透传 trace_id + 捕获未处理异常（最外层中间件）"""
    trace_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:16])
    request.state.trace_id = trace_id
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.exception(
            "unhandled_error",
            extra={
                "trace_id": trace_id,
                "path": request.url.path,
                "method": request.method,
                "error_type": type(exc).__name__,
            },
        )
        response = _error_response(
            code=500,
            message="服务内部错误",
            detail=type(exc).__name__,
            trace_id=trace_id,
        )
    response.headers["X-Request-ID"] = trace_id
    return response


# ── 注册入口 ────────────────────────────────────────


def register_exception_handlers(app: FastAPI) -> None:
    """在 FastAPI 应用上注册所有异常处理器

    注意：通用 Exception 不在此注册，由 trace_id_middleware 兜底。
    """
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    # Exception handler 故意不注册 — 由 trace_id_middleware 兜底避免 BaseHTTPMiddleware re-raise 问题
