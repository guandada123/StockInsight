# 运行与测试指南

## 后端启动

```bash
# 开发模式（热重载）
cd /Users/guan/WorkBuddy/StockInsight
uvicorn backend.main:app --host 127.0.0.1 --port 8765 --reload

# 或直接运行
python -m backend.main
```

## Docker 构建

```bash
docker build -t stockinsight-pro:latest .
docker compose up -d
```

## 后端测试

```bash
# 全量测试
cd /Users/guan/WorkBuddy/StockInsight
python -m pytest backend/tests/ -v

# 带覆盖率
python -m pytest backend/tests/ --cov=backend --cov-report=term-missing

# 运行指定测试文件
python -m pytest backend/tests/test_exceptions.py -v --tb=short

# stock_analyzer 测试（230+ 测试）
python -m pytest stock_analyzer/tests/ -q --tb=short --disable-warnings
```

## 前端测试

```bash
cd /Users/guan/WorkBuddy/StockInsight
npx vitest run                    # 全量
npx vitest run --reporter=verbose  # 详细
```

## CLI 工具

```bash
# 开盘前自检
python cli.py check --premarket

# 查看大盘
python cli.py check --market

# 个股快速分析
python cli.py analyze 601677 --fast

# 尾盘选股
python cli.py overnight-scan --top-n 20

# 全市场扫描
python cli.py scan --mode mainboard --top-n 30
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `LOG_DIR` | `./logs` | 日志文件目录 |
| `LOG_BACKUP` | `14` | 日志保留天数 |
| `PYWORKSPACE_ENV` | — | 设为 `production` 禁用 API 文档路由 |

## 常见问题

- **日志目录不可写** → 服务自动降级仅 stdout，不阻塞启动
- **数据源超时** → 7 源自动容灾切换，无需手动干预
- **Docker 端口冲突** → 修改 `docker-compose.yml` 中映射端口
