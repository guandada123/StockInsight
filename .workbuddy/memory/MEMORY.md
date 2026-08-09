# 项目记忆 — StockInsight

## 项目定位
- **名称**：StockInsight Pro（A股全链路量化投资分析平台）
- **用途**：65 个 Python 文件 / 23k+ 行 / 7 大分析层级（L0 K线→L7 宏观回测）+ ML 三模型集成（XGBoost/RF/LightGBM）+ 庄家博弈识别 + K线27形态 + 飞书推送
- **真实路径**：`/Volumes/ZHITAI/WorkBuddy/StockInsight`（与 `/Users/guan/WorkBuddy/StockInsight` 同 inode 别名，非双副本）
- **Git**：`https://github.com/guandada123/StockInsight.git` (main)

## 技术栈
- 核心：Python 3.12 + NumPy/pandas/scikit-learn/XGBoost/LightGBM
- 后端 API：FastAPI（端口 **8765**，35+ 端点，`/api/health` 健康检查）
- 前端：React + TypeScript + ECharts；桌面端 Tauri（Rust 壳）
- 缓存：SQLite 三级缓存（内存→SQLite→API）；DB `stock_cache.db`
- 数据源：7 源容灾（新浪/腾讯/Baostock/AData/Tushare/yquoter/TickFlow）
- 推送：飞书 Webhook（`feishu_push.py` / `stock_analyzer/feishu_bot.py`）

## 部署（docker-compose）
- 服务 `api`：端口 `127.0.0.1:8766:8765`，`restart: unless-stopped`
- 健康检查：`curl -f http://localhost:8765/api/health`
- 容器名：**`stockinsight-api-1`**（当前 Up 3 days healthy）
- 已在助手 self_heal 白名单（1 容器）

## CI 状态
- workflows：`stockinsight-ci.yml` + `security-scan.yml` + `build.yml`（pre-commit✓）
- 当前：**green**（08-04 验证）；测试 后端45+ 覆盖率79.9% / 前端45
- ⚠️ 写操作：助手仅事件驱动修红；**不静默改分析逻辑/选股参数/ML 模型**

## 每日工作流（已自调度，不重复建）
- 9:00 开盘前自检 `cli.py check --premarket`
- 14:30 尾盘选股 `overnight-scan`
- 15:00 收盘复盘 `check --owned`
- **16:00 `run_daily.py` 自动全市场扫描 + 自审计**（`self_audit.py` 6 大审计项）
- `feishu_push.py` 每日推送选股结果到飞书
- 助手接管层**不重复**建这些，改为：① 每日 CI 红扫描 ② 容器存活快照（已含 `stockinsight-api-1` 白名单）

## 已知坑（来自 2026-07-21 日志）
- `sector_info.py` 函数重命名 `get_stock_sector → get_stock_sector_full` 时，`cli.py:685/687` 漏改（全项目其他 10+ 处已用 `_full`）；修复 commit `d21a81e`。改 sector_info 公共函数名时务必全局 grep 同步。

## 助手接管边界（2026-08-05 授权）
- ✅ 接管：每日 CI 红扫描 + 容器存活快照（docker `stockinsight-*`）+ 自愈白名单 `stockinsight-api-1`
- ❌ 不接管：分析逻辑/选股参数/ML 模型/实盘下单；非 Claw 仓日常 commit 节奏（仅事件驱动修红）
- 飞书推送：经 StockInsight 自带 `feishu_push.py`（非 Claw push_feishu.sh）；告警经 Claw 主群 `oc_9ee5303497f5e0e71666b610d6b610d6bdc346`
