# StockInsight Pro — Docker 镜像
# 包含 Python FastAPI 后端 + React 静态前端
FROM python:3.12-slim

WORKDIR /app

# 安装 Node.js (用于构建前端)
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && apt-get clean

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 前端构建
COPY package.json package-lock.json* ./
RUN npm install
COPY src/ src/
COPY vite.config.ts tsconfig.json tsconfig.node.json index.html ./
RUN npx vite build

# 后端代码
COPY backend/ backend/
COPY stock_analyzer/ stock_analyzer/
COPY cli.py .

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8765/api/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8765"]
