# 系统架构概述

## 进程架构

```
┌─────────────────────────────────────────────────┐
│  Tauri Desktop (Rust sidecar)                    │
│  ┌──────────────┐  ┌──────────────┐             │
│  │  主进程 (Rust) │  │  WebView     │             │
│  │  托盘/通知    │  │  (React SPA) │             │
│  │  子进程管理   │  └──────┬───────┘             │
│  └──────┬───────┘         │ HTTP                 │
│         │ sidecar         │                      │
│         ▼                 ▼                      │
│  ┌─────────────────────────────────┐            │
│  │  Python 子进程 (FastAPI, :8765)  │            │
│  │  ┌───────┐ ┌──────┐ ┌────────┐  │            │
│  │  │ 路由层  │ │ 服务层 │ │ 分析引擎 │  │            │
│  │  └───────┘ └──────┘ └────────┘  │            │
│  └─────────────────────────────────┘            │
└─────────────────────────────────────────────────┘
```

## 后端层 (FastAPI)

```
backend/
├── main.py              # 入口：中间件注册、路由挂载、生命周期
├── exceptions.py        # 统一异常处理 + trace_id 注入
├── logging_config.py    # 结构化日志（JSON）+ 每日轮转
├── routers/             # 路由模块（7 个）
│   ├── market.py        # 市场行情
│   ├── analysis.py      # 个股分析
│   ├── portfolio.py     # 持仓管理
│   ├── data_management.py
│   ├── data_jobs.py     # 数据下载任务
│   ├── factors.py       # 自定义因子
│   └── scan.py          # 扫描
└── tests/
    ├── test_exceptions.py
    ├── test_logging.py
    └── test_api_integration.py
```

## 分析引擎层 (stock_analyzer)

核心模块（~65 文件），按分析层级组织：

| 层级 | 模块 | 职责 |
|------|------|------|
| L0 | `fetcher/` | 7 源 K 线获取 + 实时行情 |
| L1 | `analysis.py` | 技术指标 (MA/MACD/RSI/KDJ) + 27 种 K 线形态 |
| L2 | `business_quality.py` | 基本面 + 公司质地七问 |
| L3 | `quant.py` | 多因子评分 / 风险指标 / 信号 |
| L4 | `advanced.py` | 实时行情 / 国家队 / 北向 / 龙虎榜 |
| L5 | `short_term.py` | 资金流向 / 换手率 / 短线评分 |
| L6 | `ml_predict.py` | XGBoost + RF + LightGBM 三模型 |
| L7 | `backtest.py` | 7 策略回测 |

## 数据流

```
7 源数据 → fetcher/ → SQLite 缓存 (三级) → 分析引擎 → API → React 前端
                                  ↕
                           CLI 工具直接调用
```

## 中间件执行顺序（backend 请求生命周期）

```
请求 →
① trace_id_middleware (注入 X-Request-ID)
② CORSMiddleware (跨域)
③ add_timing_header (X-Response-Time-Ms)
④ add_security_headers (CSP/HSTS)
⑤ rate_limit_middleware (60 req/min)
⑥ 路由处理器
⑦ trace_id 自动回写响应头
```

## 数据源容灾（K 线）

7 源按优先级降级：
1. 新浪财经 → 2. 腾讯财经 → 3. Baostock → 4. AData → 5. TuShare → 6. yquoter → 7. TickFlow
