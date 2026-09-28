# ADR-001: 异常处理与日志策略

**状态**: ✅ 已实施
**日期**: 2026-06-19
**决策者**: Senior Developer

## 背景

StockInsight 后端缺乏统一的异常处理和结构化日志机制。具体问题：

1. **异常响应不一致** — 某些错误返回 HTML，某些返回 JSON，字段格式各异
2. **trace_id 缺失** — 无法串联请求链路，排查问题困难
3. **日志非结构化** — 纯文本格式不适合容器采集和日志分析平台
4. **日志无轮转** — 单文件持续增长，可能撑满磁盘

## 决策

### 异常处理：中间件模式而非 exception_handler

**方案**: 使用中间件（`trace_id_middleware`）的 `try/except` 兜底未捕获异常，配合 FastAPI `exception_handler` 处理已知异常类型。

**原因**: Starlette 的 `BaseHTTPMiddleware` 在 exception_handler 返回响应后仍会 re-raise 异常（starlette#486），导致 500 响应无法正常发送。中间件级别的 `try/except` 可以干净地捕获所有未处理异常。

**已知异常处理**:
- `StarletteHTTPException` → 标准 JSON（code=status_code, message=detail）
- `RequestValidationError` → 标准 JSON（code=422, detail=errors()）
- 其余未捕获异常 → 中间件 try/except 兜底返回 500

### 日志：JSON 结构化 + 双通道

**方案**: 自定义 `JSONFormatter`，控制台 + 文件双 handler，按天轮转保留 14 天。

**字段标准**:
```json
{
  "time": "2026-06-19T00:00:00.000Z",
  "level": "INFO",
  "logger": "stockinsight-api",
  "message": "logging_initialized",
  "trace_id": "abc123",
  "path": "/api/health",
  "method": "GET",
  "status_code": 200,
  "error_type": "ValueError",
  "exception": "Traceback..."
}
```

**轮转策略**: `TimedRotatingFileHandler` (`when="midnight"`, `backupCount=14`)

## 替代方案

| 方案 | 评估 | 结论 |
|------|------|------|
| 仅用 exception_handler | 修复 Starlette re-raise 需升级框架 | ❌ 不采用，控制力不足 |
| 第三方日志库 (structlog, python-json-logger) | 增加依赖，功能重叠 | ❌ 不采用，轻量优先 |
| RotatingFileHandler（按大小） | 不适合时政场景 | ❌ 不采用，按天更直观 |

## 影响

- **正面**:
  - 所有错误响应格式统一，前端可统一处理
  - trace_id 串联全链路，调试效率提升
  - 日志可直接接入 ELK / Grafana Loki
- **负面**:
  - 日志格式变更需同步下游采集配置
  - `delay=True` 首次写入才创建日志文件

## 回滚

移除 `main.py` 中的异常处理器注册和中间件即可回到无统一异常处理状态。
日志恢复：删除 `setup_logging()` 调用，改为 `logging.basicConfig(level=logging.INFO)`。

---

## 🔍 审计留痕（2026-09-28 · 由 Claw 巡检回写，可整段回退）

**背景**：跨项目扫描发现一类失效模式 —— **否决现成方案时，理由未经任何验证，且不设复查点**
（实例：2026-09-23 签到项目以「accessToken 泄露即被接管」否决两个开源实现，**从未读过其代码**，
承诺的安全审计至今未做，此后 4 天再没回看）。本 ADR 的「被否决方案」表中，
三条否决理由均为**印象型**，建议补成可验证表述：

| 被否方案 | 现有理由 | 缺什么 |
|---|---|---|
| 仅用 `exception_handler` | 「修复 Starlette re-raise 需升级框架」「控制力不足」 | 未记录：当前框架版本、升级到哪个版本可修、或一次验证该论点的最小实验 |
| 第三方日志库（structlog / python-json-logger） | 「增加依赖，功能重叠」 | 未记录：重叠了哪些字段、依赖体量（包大小/传递依赖数） |
| `RotatingFileHandler`（按大小） | 「不适合时政场景」「按天更直观」 | 未记录：单日日志量实测值、按大小切分会切出多少文件的估算 |

**建议（非强制）**：每条否决理由后面加一格「依据」（实测数据 / 代码引用 / 文档链接）。
理由不足时，宁可写「未验证，暂缓」，也比写成确定语气更好审计。

> 只标注不改写：**否定一个方案的依据必须可验证**；补实测是原作者的决定。
> 本段可整段删除，不影响 ADR 结论。
