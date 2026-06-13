# StockInsight Pro

[![StockInsight CI](https://github.com/nguyenchunghieu799-blip/stock-insight/actions/workflows/stockinsight-ci.yml/badge.svg)](https://github.com/nguyenchunghieu799-blip/stock-insight/actions/workflows/stockinsight-ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)]()

A股全链路量化投资分析平台 — 65个Python文件 · 23,000+行代码 · 7大分析层级 · 7路数据源容灾

## 功能总览

| 层级 | 内容 | 模块 |
|:--:|------|------|
| L0 | K线数据 + 实时行情 | 7源容灾（新浪/腾讯/Baostock/AData/Tushare/yquoter/TickFlow） |
| L1 | 技术指标 | MA/MACD/RSI/KDJ/ATR/布林带/ADX + 27种K线形态识别 |
| L2 | 基本面 | ROE/PE/PB/毛利率/净利率/营收增长 + 公司质地七问 |
| L3 | 量化多因子评分 | 7因子（动量/技术/基本面/量能/风险/舆情/资金流） |
| L4 | 实时行情 + 国家队 | 新浪批量行情 + 国家队/北向/龙虎榜 |
| L5 | 资金流向 + 短线 | 主力资金 + 换手率 + 短线评分 + 组合信号 |
| L6 | ML预测 | XGBoost + RandomForest + LightGBM 三模型集成投票 |
| L7 | 宏观 + 回测 | 宏观经济数据 + 7大策略回测对比 |

### 特色功能

- **庄家博弈四阶段识别** — 建仓/洗盘/拉升/出货，含置信度 + 量价分析
- **K线形态27种** — 三只乌鸦/黄昏之星/阳包阴/锤子线/射击之星等，含中文解读
- **筹码集中度** — 90%/70%成本分布 + 风控规则（>35%+>20%=极度危险）
- **投资心理学** — 10种亏钱心态 + 7种好心态 + 4阶段进化
- **多空辩论** — NL自然语言自动生成看涨vs看跌双方论点
- **三重过滤系统** — 大盘→板块→个股，板块排名定胜率
- **Tauri桌面端** — React + FastAPI + Rust 三进程架构

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 开盘前自检（推荐，5秒检测所有数据源）
python cli.py check --premarket

# 查看大盘
python cli.py check --market

# 板块排名
python cli.py check --rotation

# 个股快速分析（盘中秒出，纯本地）
python cli.py analyze 601677 --fast

# 个股完整分析（七层全出）
python cli.py analyze 601677 --full

# 终极分析（大盘+板块+L0-L7+预测+买卖点）
python cli.py analyze 601677 --ultimate

# 生成DOCX深度报告
python gen_docx_report.py 600066
```

## 选股流程

```bash
# 增强选股（板块过滤+短线+ML，两轮筛选）
python cli.py enhanced-scan --top-n 20

# 一夜持股法（尾盘2:30后，六步筛选）
python cli.py overnight-scan --top-n 20

# 全市场扫描
python cli.py scan --mode mainboard --top-n 30

# ML双层过滤选股
python ml_scan.py                    # 主板 top10
python ml_scan.py --mode full        # 全A股
```

## 分析模式对比

| 模式 | 速度 | 内容 | 网络 | 适用 |
|------|:--:|------|:--:|------|
| `--fast` | <1s | L0-L3（K线+技术+量化+基本面） | 零 | 盘中快速决策 |
| `--full` | ~35s | L0-L7（全部七层+多空辩论） | 5-6次 | 盘后深度研究 |
| `--ultimate` | ~40s | full + 板块分析 + 买卖点 | 6-8次 | 入金前精选 |

## 技术栈

| 层 | 技术 |
|------|------|
| 核心引擎 | Python 3.x, NumPy, pandas, scikit-learn, XGBoost, LightGBM |
| 后端API | FastAPI (端口8765, 35+端点) |
| 前端 | React + TypeScript + ECharts |
| 桌面端 | Tauri (Rust壳，进程管理/托盘/通知) |
| 数据库 | SQLite (stock_cache.db, 三级缓存架构) |
| 报告 | Chart.js HTML + DOCX (python-docx) |
| 推送 | 飞书Webhook机器人 |

## 项目结构

```
├── cli.py                    # 统一CLI入口（50+命令）
├── stock_analyzer/
│   ├── analysis.py           # 技术指标（MA/MACD/RSI/KDJ/ATR/布林带/ADX）
│   ├── quant.py              # 量化分析（风险指标/多因子评分/信号/回测）
│   ├── patterns.py           # K线形态识别（27种蜡烛图）
│   ├── chip_concentration.py # 筹码集中度（90%/70%成本分布）
│   ├── chip_factors.py       # 筹码面因子（集中度/量价/换手率）
│   ├── short_term.py         # 短线专项（换手率/主力/组合信号/多周期共振）
│   ├── backtest.py           # 7策略回测框架
│   ├── ml_predict.py         # ML三模型预测（XGBoost+RF+LightGBM）
│   ├── psychology.py         # 庄家意图+散户心态+联动总结
│   ├── business_quality.py   # 公司质地七问
│   ├── screener.py           # 全市场选股流水线
│   ├── enhanced_screener.py  # 增强选股器
│   ├── custom_factors.py     # 自定义因子表达式引擎（AST白名单）
│   ├── sector_info.py        # 板块查询（行业+概念）
│   ├── feishu_bot.py         # 飞书群机器人推送
│   ├── ultimate_report.py    # 终极分析（大盘+板块+L0-L7+预测+买卖点）
│   ├── portfolio.py          # 组合管理（夏普/方差/风险平价/等权）
│   ├── alert.py              # 价格预警
│   ├── advanced.py           # 龙虎榜/北向/两融/增减持/调研/财报
│   ├── report_html.py        # Chart.js交互式HTML报告
│   ├── cache.py              # 三级缓存（内存→SQLite→API）
│   ├── config.py             # 统一配置
│   ├── self_audit.py         # 自审计系统（6大审计项）
│   └── fetcher/              # 数据获取（7源K线+实时行情+资金流向）
├── backend/                  # FastAPI后端 (35+端点)
├── src/                      # React前端 (TypeScript + ECharts)
├── src-tauri/                # Tauri桌面端 (Rust壳)
├── run_daily.py              # 每日16:00自动扫描
├── run_full_scan.py          # 全市场扫描（8线程，~8min）
├── feishu_push.py            # 飞书每日推送
├── gen_docx_report.py        # DOCX深度报告生成
└── warmup_all_data.py        # K线数据预热
```

## 数据源

| 数据 | 来源 | 说明 |
|------|------|------|
| K线日线 | 新浪→腾讯→Baostock→AData→TuShare→yquoter→TickFlow | 七源容灾 |
| 实时行情 | 新浪 hq.sinajs.cn | 批量500只 |
| 基本面 | akshare（东方财富） | ROE/PE/PB/毛利率等 |
| 资金流向 | 东方财富push2 + Tushare代理 | 盘中+盘后T+1 |
| 行业分类 | Tushare代理 + Baostock | 110行业/5524只 |
| 板块排名 | 东方财富push2 | 概念板块资金排名 |
| 国家队/北向/龙虎榜 | akshare | 盘后更新 |
| 新闻/舆情 | akshare | 东方财富/微博 |

## 缓存架构

三级读取：L1进程内存(30min) → L2 SQLite永久存储(永不过期) → L3 API增量

| 表 | 内容 | 数据量 |
|------|------|------|
| kline_store | K线日线 | 5,220只×365天 |
| fund_store | 基本面 | 5,522只 |
| nt_store | 国家队持股 | 5,522只 |
| daily_scores | 历史评分 | 316,532条(61天) |
| cache | 临时缓存 | 名称表+新闻+板块+资金流向 |

## 性能优化

| 优化项 | 优化前 | 优化后 | 方案 |
|:-----:|:------:|:------:|------|
| 宏观数据API | 23.8s | 0.006s | SQLite缓存(7天TTL) |
| ML三模型训练 | 4.7s | 0.001s | 内存缓存 |
| ML跨进程复用 | 4.7s | 0.01s | 磁盘缓存 models/ |
| gen_docx报告 | 47s | 12.9s | 以上三项合计 |
| 实时行情首次调用 | 25s | 0.08s | 名称表SQLite缓存 |

## 每日工作流

```
9:00   python cli.py check --premarket     → 5秒自检所有数据源
9:30-14:30   python cli.py analyze <code> --fast  → 盘中快速分析
14:30  python cli.py overnight-scan --top-n 20     → 尾盘选股
15:00  python cli.py check --owned          → 收盘复盘
16:00  run_daily.py 自动触发全市场扫描 + 自审计
```

## 启动桌面端

```bash
npm install
npm run tauri dev
```

## 免责声明

本项目仅供学习研究使用，所有分析结论不构成投资建议。股市有风险，投资需谨慎。

## License

Private — for personal use only.
