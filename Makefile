# StockInsight Pro — 开发工具链
# 用法: make setup / make lint / make test / make ci / make dev

PYTHON := python3
PIP_INSTALL := $(PYTHON) -m pip install
PYTEST := $(PYTHON) -m pytest
MIRROR := -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

.PHONY: setup lint format test test-be test-be-cov test-fe ci dev api docs load-test type-check help

help: ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: ## 初始化开发环境 (Python + Node)
	$(PIP_INSTALL) pre-commit ruff mypy pytest fastapi uvicorn python-multipart $(MIRROR)
	npm install
	pre-commit install --hook-type pre-commit --hook-type commit-msg
	@echo "✅ StockInsight 开发环境就绪 (Python 3.12)"

lint: ## 运行 lint (ruff + eslint)
	ruff check backend/ stock_analyzer/ --fix --config ruff.toml
	npx eslint src/

format: ## 格式化代码 (ruff + prettier)
	ruff format backend/ stock_analyzer/ --config ruff.toml
	npx prettier --write "src/**/*.{ts,tsx,css}"

test: test-be test-fe ## 运行所有测试

test-be: ## 后端测试
	$(PYTEST) stock_analyzer/test_*.py backend/tests/ -v --tb=short

test-be-cov: ## 后端测试 + 覆盖率
	$(PYTEST) stock_analyzer/test_*.py backend/tests/ -v --tb=short \
		--cov=stock_analyzer --cov=backend \
		--cov-report=term-missing --cov-fail-under=40

test-fe: ## 前端测试
	npx vitest run

type-check: ## 运行 mypy 类型检查
	mypy stock_analyzer/ backend/ \
		--ignore-missing-imports --check-untyped-defs \
		--warn-return-any --warn-redundant-casts

ci: ## 模拟完整 CI 流水线
	$(MAKE) lint
	$(MAKE) test
	$(MAKE) type-check
	@echo "✅ CI 通过"

dev: ## 启动开发服务器 (API + Vite)
	npx concurrently "$(PYTHON) -m backend.main" "npx vite"

api: ## 仅启动 API 后端
	$(PYTHON) -m backend.main

docs: ## 生成 API 文档
	$(PYTHON) scripts/generate_api_docs.py
	@echo "📄 Swagger: http://127.0.0.1:8765/docs"
	@echo "📄 ReDoc:   http://127.0.0.1:8765/redoc"

load-test: ## 运行 k6 压测 (需先启动 API)
	k6 run scripts/load_test.js
