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


# --- Simple in-memory rate limiter (token bucket) ---
_RATE_LIMITS: dict[str, list[float]] = {}  # ip -> list of request timestamps
_RATE_MAX = 60  # max requests
_RATE_WINDOW = 60.0  # per window (seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("StockInsight API server starting on port 8765...")
    yield
    logger.info("StockInsight API server shutting down...")


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
    docs_url="/docs",
    redoc_url="/redoc",
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

# CORS: 允许 Tauri WebView (tauri://localhost) 和 Vite dev server (localhost:1420)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:1420",  # Vite dev server
        "http://127.0.0.1:1420",
        "tauri://localhost",  # Tauri production
        "https://tauri.localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    elapsed = (time.time() - t0) * 1000
    response.headers["X-Response-Time-Ms"] = f"{elapsed:.0f}"
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
    try:
        import signal

        signal.raise_signal(signal.SIGTERM)
    except Exception:
        os._exit(0)


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
