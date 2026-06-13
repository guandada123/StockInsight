# Changelog

## [2026-06-13] Phase 13: Python 3.12 统一

### Docker
- Dockerfile: python:3.11-slim → python:3.12-slim

## [2026-06-13] Phase 12: Docker HEALTHCHECK

### Docker
- Dockerfile: 添加 HEALTHCHECK (curl /api/health, 30s间隔)

## [2026-06-13] Phase 11: CI 加固 + 类型安全

### CI 加固
- 移除 backend-test `|| true` → 测试真正门禁 CI
- 添加 `--cov-fail-under=40` 覆盖率硬性阈值
- 添加 backend-type-check (mypy) 类型检查步骤
- 测试范围扩展: stock_analyzer/test_*.py + backend/tests/

### 开发体验
- Makefile: 添加 test-be-cov/type-check 目标
- README: 添加 CI badge

## [2026-06-13] 全维度代码质量优化

### 安全修复
- API 异常信息泄露 31处 → 全部脱敏 (logger.exception + 通用错误信息)
- Dashboard.tsx 空catch → console.error + 错误状态
- DOM直接操作 → React受控组件 (useRef + useState)

### 韧性
- ErrorBoundary 全局错误兜底 (防白屏 + 一键恢复)
- stock_analyzer/resilience.py: @retry + @circuit_breaker + @resilient 组合装饰器
- backend/db.py: SQLite WAL模式 + 连接池(5) + PRAGMA优化 + 查询超时

### 质量基础设施
- ruff + ESLint + Prettier 全栈 lint/format
- pre-commit hooks (ruff + mypy + prettier + conventional commits)
- GitHub Actions CI (frontend-lint → backend-lint → backend-test → security)
- Dependabot 依赖自动更新

### API 文档
- OpenAPI spec 自动生成 (38 endpoints, 7 tags)
- Swagger UI (/docs) + ReDoc (/redoc) 双入口
- scripts/generate_api_docs.py (含 --check CI模式)

### 测试
- backend/tests/test_api_integration.py: 8个API集成测试
- 健康检查/错误脱敏/参数验证/404/敏感信息过滤

### 性能
- backend/cache.py: TTL内存缓存装饰器
- schemas/requests.py: Pydantic v2 输入验证
- scripts/load_test.js: k6压测 (6场景/5-15VU/p95<500ms)
- data_management.py: UploadFile → bytes Body (消除编译依赖)

### 开发体验
- Makefile: make setup/lint/test/ci/dev/api/docs/load-test
- Python 3.12 标准化
