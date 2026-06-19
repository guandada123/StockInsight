# API 端点概览

Base URL: `http://127.0.0.1:8765`

## 健康检查

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 服务探针，返回 status/uptime/version |
| POST | `/api/shutdown` | 优雅关闭 |
| GET | `/api` | 列出所有端点 |

## 市场行情

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/market/index` | 大盘指数 |
| GET | `/api/market/limit-up` | 涨停板 |
| GET | `/api/market/rotation` | 板块轮动 |

## 个股分析

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/analysis/stock/{code}` | 完整七层分析 |
| GET | `/api/analysis/stock/{code}/kline` | K 线数据 |

## 持仓管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/portfolio` | 组合列表 |
| POST | `/api/portfolio` | 创建组合 |

## 通用错误响应

所有错误返回统一 JSON 结构：

```json
{
  "code": 404,
  "message": "Not Found",
  "detail": null,
  "trace_id": "a1b2c3d4e5f67890"
}
```

响应头包含 `X-Request-ID` (即 trace_id)。

开发环境 Swagger 文档: `/docs`
