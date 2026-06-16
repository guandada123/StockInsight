"""StockInsight Pro — FastAPI 后端入口

启动方式:
    uvicorn backend.main:app --host 127.0.0.1 --port 8765 --reload
    python -m backend.main

Tauri 集成:
    1. Rust sidecar 启动 Python 子进程运行此文件
    2. 轮询 GET /api/health 直到就绪
    3. 关闭时发送 POST /api/shutdown
"""

import logging
import os
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# 确保项目根目录在 sys.path 中（sidecar 启动时可能需要）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("stockinsight-api")

START_TIME = time.time()


# --- Sliding-window rate limiter with file persistence ---
import json as _json

_RATE_LIMITS: dict[str, list[float]] = {}  # ip -> list of request timestamps
_RATE_MAX = 60  # max requests
_RATE_WINDOW = 60.0  # per window (seconds)
_RATE_DUMP_INTERVAL = 10.0  # flush to disk every N seconds
_RATE_DUMP_PATH = os.path.join(os.path.dirname(__file__), ".rate_limits.json")
_last_rate_dump = 0.0


def _load_rate_limits() -> dict[str, list[float]]:
    """启动时从磁盘恢复限流状态，防止重启后限流失效"""
    try:
        if os.path.exists(_RATE_DUMP_PATH):
            with open(_RATE_DUMP_PATH) as f:
                data = _json.load(f) if _json else {}
            now = time.time()
            return {ip: [t for t in ts if now - t < _RATE_WINDOW] for ip, ts in data.items()}
    except Exception:
        pass
    return {}


def _dump_rate_limits():
    """定期将限流状态写入磁盘，用于重启恢复"""
    global _last_rate_dump
    _last_rate_dump = time.time()
    try:
        with open(_RATE_DUMP_PATH, "w") as f:
            _json.dump(_RATE_LIMITS, f)
    except Exception:
        pass


# 启动时恢复限流状态
_RATE_LIMITS = _load_rate_limits()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("StockInsight API server starting on port 8765...")
    yield
    logger.info("StockInsight API server shutting down...")


# 生产环境关闭文档路由（安全加固）
_IS_PRODUCTION = os.environ.get("PYWORKSPACE_ENV", "").lower() in ("production", "prod")
_docs_kwargs = (
    {"docs_url": None, "redoc_url": None, "openapi_url": None}
    if _IS_PRODUCTION
    else {"docs_url": "/docs", "redoc_url": "/redoc"}
)

app = FastAPI(
    title="StockInsight Pro API",
    description=(
        "A股量化分析平台 — 提供市场总览、个股七层全维度分析、持仓管理、"
        "K线数据、资金流向、板块轮动等 API。\n\n"
        "**数据来源**: 新浪财经 / 东方财富 / AkShare\n"
        "**免责声明**: 以上分析仅供学习研究，不构成投资建议。"
    ),
    version="1.0.0",
    lifespan=lifespan,
    **_docs_kwargs,
    openapi_tags=[
        {"name": "市场行情", "description": "大盘指数、涨跌停、板块轮动"},
        {"name": "个股分析", "description": "七层全维度分析、K线、技术指标、资金流向"},
        {"name": "持仓管理", "description": "组合创建/编辑/分析、调仓建议"},
        {"name": "因子管理", "description": "自定义因子CRUD"},
        {"name": "数据管理", "description": "缓存/数据源状态/导入导出"},
        {"name": "数据下载", "description": "Tushare 数据管线任务"},
        {"name": "健康检查", "description": "服务状态探针"},
    ],
)

# CORS: 仅允许白名单来源和方法
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:1420",  # Vite dev server
        "http://127.0.0.1:1420",
        "tauri://localhost",  # Tauri production
        "https://tauri.localhost",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    elapsed = (time.time() - t0) * 1000
    response.headers["X-Response-Time-Ms"] = f"{elapsed:.0f}"
    return response


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """添加安全响应头：CSP、X-Content-Type-Options、X-Frame-Options"""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
    return response


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Simple sliding-window rate limiter: 60 req/min per IP."""
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    if ip not in _RATE_LIMITS:
        _RATE_LIMITS[ip] = []
    timestamps = _RATE_LIMITS[ip]
    # Purge old entries
    timestamps[:] = [t for t in timestamps if now - t < _RATE_WINDOW]
    if len(timestamps) >= _RATE_MAX:
        return JSONResponse(
            status_code=429, content={"detail": "Too many requests. Try again later."}
        )
    timestamps.append(now)
    # Prevent unbounded growth — evict stale IPs
    if len(_RATE_LIMITS) > 10000:
        stale = [ip for ip, ts in _RATE_LIMITS.items() if not ts or now - ts[-1] > _RATE_WINDOW]
        for ip in stale:
            del _RATE_LIMITS[ip]
    # Periodically persist to disk for restart recovery
    global _last_rate_dump
    if now - _last_rate_dump > _RATE_DUMP_INTERVAL:
        _dump_rate_limits()
    return await call_next(request)


# ── 注册路由 ────────────────────────────────────────


@app.get("/api/health")
async def health():
    """健康检查（Tauri 轮询此端点等待就绪）"""
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "version": "1.0.0",
    }


@app.post("/api/shutdown")
async def shutdown():
    """优雅关闭（Tauri 退出时调用）"""
    logger.info("Shutdown requested")
    import asyncio

    asyncio.create_task(_delayed_shutdown())
    return {"status": "shutting_down"}


async def _delayed_shutdown():
    await asyncio.sleep(0.5)
    logger.info("Shutdown complete")
    # 使用 SIGTERM 优雅关闭，确保 SQLite WAL 和 buffer 被正确 flush
    os.kill(os.getpid(), signal.SIGTERM)


# ── 注册子路由 ──────────────────────────────────────

from backend.routers import analysis, data_jobs, data_management, factors, market, portfolio

app.include_router(market.router)
app.include_router(analysis.router)
app.include_router(portfolio.router)
app.include_router(data_management.router)
app.include_router(data_jobs.router)
app.include_router(factors.router)

import asyncio  # noqa: E402


@app.get("/api")
async def api_root():
    """API 根 — 列出所有端点"""
    routes = []
    for route in app.routes:
        if hasattr(route, "path") and route.path.startswith("/api"):
            routes.append(f"{route.methods if hasattr(route, 'methods') else 'GET'} {route.path}")
    return {"endpoints": sorted(routes), "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8765, reload=False)
