# =============================================================================
# StockInsight Pro — 多阶段 Docker 构建
# 策略：前端构建 → Python 依赖 → 精简运行镜像
# 优化目标：移除运行时不需要的 Node.js、npm、apt 缓存、构建工具链
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: 前端构建阶段 (node:20-slim — 轻量 Node.js 镜像)
# ---------------------------------------------------------------------------
FROM node:20-slim AS frontend-builder

WORKDIR /build

# 先复制 manifest 文件，利用 Docker 层缓存
COPY package.json package-lock.json* ./
RUN npm ci --only=production && npm cache clean --force

# 复制前端源码与构建配置
COPY vite.config.ts tsconfig.json tsconfig.node.json index.html ./
COPY src/ src/

# 生产构建（不生成 sourcemap，esbuild 压缩）
RUN npx vite build --minify esbuild

# 清理：移除 node_modules（构建后不再需要）
RUN rm -rf node_modules

# ---------------------------------------------------------------------------
# Stage 2: Python 依赖安装阶段
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS python-deps

WORKDIR /install

# 安装系统依赖（仅在安装阶段需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 创建虚拟环境，隔离 Python 依赖
RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip cache purge

# ---------------------------------------------------------------------------
# Stage 3: 最终运行镜像 (纯 Python slim，不携带任何构建工具)
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# 避免交互式提示
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/venv/bin:$PATH"

WORKDIR /app

# 仅安装运行时系统依赖（curl 用于 HEALTHCHECK）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制 Python 依赖（从 Stage 2）
COPY --from=python-deps /venv /venv

# 复制前端构建产物（从 Stage 1）
COPY --from=frontend-builder /build/dist/ dist/

# 复制后端代码
COPY backend/ backend/
COPY stock_analyzer/ stock_analyzer/
COPY cli.py .

# 创建非 root 用户运行
RUN groupadd -r appuser && useradd -r -g appuser appuser && \
    chown -R appuser:appuser /app

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8765/api/health || exit 1

USER appuser

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8765"]
