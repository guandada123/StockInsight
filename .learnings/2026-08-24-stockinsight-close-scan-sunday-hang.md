# ★升级候选 StockInsight 收盘选股周日硬 hang 根因与修复

**日期**: 2026-08-24
**项目**: StockInsight (收盘选股扫描自动化 automation-1784555575881)
**严重度**: P1（误报告警 + 资源浪费，非数据错误，次日自愈）

## 现象
- 2026-08-23 15:30（周日非交易日）自动化触发，收盘选股命令连续 3 次 hard hang / 超时 600s。
- 5 个 K 线源（Sina/Tencent/Baostock/AData/Tushare）全部熔断，日志 382 行 `K线[X] 全部数据源失败`。
- 退出码 124（timeout 杀掉），无 `结果已保存`，`daily_scores=0`。
- L3 护栏判定真异常 → 推送飞书告警。

## 根因（已读日志+代码实锤，非脑补）
1. **非交易日源离线**：周日收盘后 Sina/Tencent 等 K 线接口普遍不可用（已在 08-24/08-18 等多日日志复现，属已知周末抖动）。
2. **`fetch_kline` 无单源硬超时**：`stock_analyzer/data_sources.py:DataSourceChain.fetch_kline` 仅依赖各源自身 socket 超时 + 300s 熔断器冷却，单只 `analyze_one` 在源全挂时阻塞时长远超 `cli.py:638 future.result(timeout=45)` 的 45s 等待窗——`future.result` 只放弃"等待线程返回"，线程本身仍在源重试循环里占池。
3. **外层 600s `timeout` < 最坏聚合时间**：数百只 × 8 线程全卡源重试 → 墙钟超 600s → 被外层 `timeout` 杀（exit 124）。
4. **非死锁**：告警"提示3"怀疑的 `future` 未 resolve 死锁不成立——`as_completed` + `future.result(timeout=45)` 结构正确，无 future 泄漏。真因是"全源失败 × 无单源硬超时 × 外层 timeout 过小"的超时放大。

## 修复（已落地 cli.py）
- `cli.py cmd_scan` 顶部新增**非交易日短路**（08-24 提交）：
  ```python
  _now = datetime.now()
  if _now.weekday() >= 5:  # 5=Sat, 6=Sun
      print("⏸️ 非交易日跳过扫描...下一交易日自动恢复")
      return 0
  ```
- 效果：周末直接 exit 0，不触发网络抓取、不产生 600s hang、不误报告警。交易日路径零改动。
- 验证：ast 语法 OK；weekday 分支逻辑独立复现 Sun/Sat→skip、Mon→proceed 正确。

## 根治项落地状态
- ✅ **单源硬超时（已做，08-24 18:59）**：`data_sources.py` 加 `PER_SOURCE_TIMEOUT=8s` + 进程级 `_SRC_TIMEOUT_POOL(max_workers=8)`，包裹 `DataSourceChain.fetch_kline` 每源调用。
  - 验证：success path 0.00s（无回归）；单源 hang → 8.0s 超时后跳下一源；5 源全 hang 最坏 24.0s（熔断跳过 2 源后 3×8s），**< 45s 外层窗**，彻底消除"无单源超时 → 300s 熔断 → 600s 被杀"的放大链。
  - 关键坑：初版 `max_workers=1` 导致超时源后台线程占满单 worker 串行化后续源（实测 20s），改 `max_workers=8` 解决。
- ✅ **交易日历精确化（已做，08-24 19:01）**：接 `tushare_loader` 交易日表，彻底静默周末+法定节假日。
  - 新增 `stock_analyzer/trade_day.py`：`is_trading_day(dt)` 优先查 `stock_cache.db` 的 `stock_trade_calendar` 表（tushare_loader schema），表缺失/越界 fallback 内置 2026 休市 + weekday<5（**保守设计：宁可少跳不误跳，避免交易日被静默漏扫**）。
  - `cli.py cmd_scan` 顶部短路升级为 `if not is_trading_day(_now.date()): return 0` —— 周末/法定节假日均 exit 0 不抓源。
  - 内置 2026 休市区间依**上交所 2025-12-22 官方公告**核实（元旦1/1-1/3、春节2/15-2/23、清明4/4-4/6、劳动5/1-5/5、端午6/19-6/21、中秋9/25-9/27、国庆10/1-10/7）。
  - **部署关键（复盘必读）**：容器跑旧镜像，本地改动须 `docker cp` 进 stockinsight-api-1（或重建镜像）才生效；`stock_cache.db` 是 bind mount 实时同步。已 `docker cp` cli.py/data_sources.py/trade_day.py 进容器验证。
  - **表数据落地**：容器无 Tushare token 无法跑 `download_trade_calendar`，故本地直接生成 2026 全年交易日历（365行/242交易日，含官方休市）写入 `stock_cache.db.stock_trade_calendar`，容器经 mount 读到 → 表优先路径生效。越界(>2026-12-31)自动 fallback 内置表。
  - 验证：容器内 `is_trading_day` 表优先确认（2026-08-24→交易日、2026-10-01→非交易日、2027-01-01→None fallback）。

## 升级候选理由
- 同类"非交易日/节假日源离线 → 扫描硬 hang → 误报告警"是**可复发类**，且根因（无单源硬超时 + 外层 timeout 过小）在交易日全源故障场景同样成立。
- 当前周日短路是"止血"，**单源硬超时**才是根治。建议周度 auto-promote 后写入 StockInsight 铁律 + 补单源超时回归测试。
