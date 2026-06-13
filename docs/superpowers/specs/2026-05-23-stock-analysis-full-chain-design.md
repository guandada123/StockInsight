# 全链路股票分析系统 - 设计文档

## 概述

在现有 `stock_analyzer` 项目基础上，新增 6 个功能模块，构建从数据获取→缓存→选股→分析→组合→预警→报告的完整闭环。

## 架构图

```
           ┌─────────────┐
           │  外部数据源   │
           │ 新浪/东方财富 │
           │  /akshare    │
           └──────┬──────┘
                  │ 原始数据
           ┌──────▼──────┐
           │  cache.py   │ ◄── SQLite 缓存层，避免重复拉取
           │  数据缓存层  │
           └──────┬──────┘
                  │ 缓存数据
     ┌────────────┼────────────┐
     │            │            │
┌────▼───┐  ┌────▼───┐  ┌────▼───┐
│screener │  │ 现有分析 │  │portfolio│
│ 选股池  │  │ 模块复用 │  │ 组合管理 │
└────┬───┘  └────┬───┘  └────┬───┘
     │            │            │
     └────────────┼────────────┘
                  │
            ┌─────▼─────┐
            │  alert.py  │── 条件检查 → 输出预警
            │  预警模块   │
            └─────┬─────┘
                  │
            ┌─────▼──────┐
            │report_html  │── Chart.js 交互式报告
            │ HTML报告    │
            └────────────┘
```

所有修改为新增独立文件，不修改现有 `analysis.py` / `quant.py` / `main.py` 等已有代码。

## 1. 数据缓存层 `cache.py`

**用途：** 所有数据获取先查本地 SQLite 缓存，命中且未过期则直接返回，否则拉取后写入缓存。

**表结构（SQLite）：**
```sql
CREATE TABLE cache (
    key TEXT PRIMARY KEY,       -- 如 "kline:300408"
    value BLOB,                 -- pickle 序列化
    created_at REAL,            -- time.time()
    ttl_seconds INTEGER         -- 过期时间
);
```

**TTL 策略：**
| 数据类型 | 缓存有效期 |
|----------|-----------|
| K线数据（日线） | 4 小时 |
| 基本面数据 | 24 小时 |
| 板块列表 | 2 小时 |
| 实时行情 | 30 分钟 |

**接口：**
- `cache_get(key)`: 读取缓存，过期返回 None
- `cache_set(key, value, ttl)`: 写入缓存
- `cache_clear(key)`: 清除单条
- `cache_clear_all()`: 清空全部
- `cached_kline(code, days=120)`: 包装 get_kline，自动走缓存
- `cached_fundamentals(code)`: 包装 get_fundamentals
- `cached_sectors()`: 包装 get_sectors

**边界处理：**
- SQLite 文件不存在时自动创建
- pickle 反序列化失败时删除损坏缓存并重新拉取
- 并发写使用 `INSERT OR REPLACE`
- 缓存穿透：同时请求同一只股票时不会重复拉取

**文件路径：** `D:\CC\5.23\stock_analyzer\cache.py`，数据库文件放 `D:\CC\5.23\stock_cache.db`

## 2. 每日选股池 `screener.py`

**用途：** 基于缓存数据，批量筛选全市场股票，按多因子排名输出精选池。

**工作流程：**
1. 加载股票池（默认：沪深300 + 中证500 成分股，或自定义列表）
2. 从缓存批量拉取 K 线 + 基本面数据（缓存未命中则逐个拉取）
3. 对每只股票调用 `composite_quant_score()` 计算多因子评分
4. 按综合评分降序排列
5. 应用过滤条件（排除 ST、排除成交量过低）
6. 输出 Top N 精选结果

**接口：**
- `run_screener(pool=None, top_n=30)`: 执行扫描，返回评分 DataFrame
- `filter_by_conditions(df, min_price=5, max_pe=200, min_volume_ratio=0.1)`: 条件过滤
- `save_screener_result(df, path)`: 保存结果到 JSON
- `load_stock_pool(source="hs300_zz500")`: 加载股票池

**输出字段：**
代码 | 名称 | 综合评分 | 评级 | 动量分 | 技术分 | 基本面分 | 量能分 | 风险分 | 最新价 | 涨跌幅 | 所属板块

**与现有 main.py 的区别：**
- `main.py` 从 TOP3 板块选股，范围窄
- `screener.py` 全市场扫描，评分更系统，过滤更灵活

## 3. 投资组合管理 `portfolio.py`

**用途：** 管理一组自选股，整体看风险收益，生成组合级分析报告。

**数据格式（JSON）：**
```json
{
    "name": "我的组合",
    "created_at": "2026-05-23",
    "stocks": [
        {"code": "300408", "weight": 0.4, "cost": 100.0},
        {"code": "603005", "weight": 0.3, "cost": 35.0},
        {"code": "600519", "weight": 0.3, "cost": 1500.0}
    ]
}
```

**接口：**
- `create_portfolio(name, stocks)`: 新建组合
- `load_portfolio(name)`: 加载组合（从 JSON 文件）
- `save_portfolio(portfolio)`: 保存组合
- `analyze_portfolio(portfolio)`: 整体分析
  - 每只股票调用现有分析模块
  - 汇总计算组合总市值、总收益、组合夏普比率、组合波动率
  - 输出各股贡献度
- `list_portfolios()`: 列出所有组合
- `add_stock(portfolio, code, weight, cost)`: 加仓
- `remove_stock(portfolio, code)`: 减仓
- `rebalance(portfolio, target_weights)`: 调仓建议

**存储路径：** `D:\CC\5.23\portfolios\` 目录下每个组合一个 JSON

**组合指标计算：**
- 组合收益率 = Σ(个股收益率 × 权重)
- 组合波动率 = sqrt(ΣΣ(wi × wj × cov(i,j)))
- 组合夏普 = (组合收益率 - 无风险利率) / 组合波动率
- 个股贡献度 = 个股收益率 × 权重 / 组合收益率

## 4. 价格预警 `alert.py`

**用途：** 对关注的股票设置条件，满足时触发通知。

**预警类型：**
```python
# 价格预警
{"type": "price", "code": "300408", "direction": "above", "target": 120.0}
{"type": "price", "code": "300408", "direction": "below", "target": 100.0}

# 放量预警
{"type": "volume", "code": "603005", "multiplier": 2.0}  # 成交量 > 2倍均值

# 技术指标预警
{"type": "technical", "code": "300408", "indicator": "RSI", "condition": ">80"}
{"type": "technical", "code": "300408", "indicator": "MACD", "condition": "金叉"}
{"type": "technical", "code": "300408", "indicator": "支撑位", "condition": "跌破"}

# 基本面预警
{"type": "fundamental", "code": "600519", "metric": "ROE", "condition": "<10"}
```

**接口：**
- `add_alert(config)`: 添加预警规则
- `remove_alert(alert_id)`: 删除预警
- `check_alerts(watchlist)`: 对所有关注的股票检查预警
- `run_all_alerts()`: 加载所有预警规则并执行检查
- `load_alerts()` / `save_alerts()`: 持久化

**存储：** `D:\CC\5.23\alerts.json`

**触发输出：** 终端打印 + 可选写入 `alerts_log.txt`（带时间戳）

## 5. HTML 报告 `report_html.py`

**用途：** 替代 DOCX，生成交互式 HTML 报告（Chart.js + 自适应布局）。

**报告结构：**
1. 顶部：组合概览卡片（总收益/夏普/最大回撤/股票数）
2. 组合详情表：每只股票一行（代码/名称/仓位/现价/收益/评分/评级）
3. 评分雷达图：每只股票的五维因子对比
4. K线走势图：核心 K 线 + MA + 布林带（用 Chart.js 画）
5. 风险仪表盘：组合整体风险指标

**接口：**
- `generate_html_report(portfolio_data, stock_details, output_path)`: 生成完整报告
- `generate_screener_report(screener_result, output_path)`: 生成选股结果报告

**依赖：** Chart.js（CDN 加载，无需安装），无其他外部依赖

## 6. 单元测试

**框架：** pytest（或 unittest）

**测试文件：**
| 文件 | 测试内容 | 关键测试点 |
|------|---------|-----------|
| `test_cache.py` | cache.py | 读写/过期/损坏数据处理/并发 |
| `test_analysis.py` | analysis.py | 各指标计算/空数据/不足周期 |
| `test_quant.py` | quant.py | 评分边界/信号检测/回测逻辑 |
| `test_screener.py` | screener.py | 过滤逻辑/评分排序 |
| `test_portfolio.py` | portfolio.py | 收益计算/权重/调仓 |
| `test_fetcher.py` | fetcher.py | mock API 响应测试 |

**运行方式：**
```bash
cd D:\CC\5.23 && python -m pytest stock_analyzer/test_*.py -v
```

## 实施顺序

1. `cache.py` — 基础，后续所有模块受益
2. 各模块的单元测试（随模块一起写）
3. `screener.py` — 依赖缓存
4. `portfolio.py` — 依赖缓存和分析模块
5. `alert.py` — 依赖缓存
6. `report_html.py` — 独立，可最后做
