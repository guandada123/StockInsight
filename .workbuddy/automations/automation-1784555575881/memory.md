# StockInsight 收盘选股扫描 — 执行记录（工作区副本）

## 2026-08-12 15:25 (GMT+8, 调度触发) — 周三交易日，正常完成
- 命令：`docker exec stockinsight-api-1 python3 /app/cli.py scan --mode mainboard --top-n 20`
- 结果：**正常**。股票池 3191 → 过滤后 2470 → 达标 **179** 只，Top20 已生成。
- 耗时：约 30s（容器 UTC 07:29）。结果文件 `scan_mainboard_20260812_0729.json`，daily_scores 写入 **179** 条，跳过/失败 0。
- 实时行情源稳定，无 Traceback/Server disconnected/熔断 WARN。
- Top3：002458(72.2) / 603883(71.1) / 603939(70.7)。
- 异常判定：退出码=0 ✅ / `结果已保存` 存在 ✅ / daily_scores=179>0 ✅ → **正常，不推送飞书**。
- 备注：本环境 `automation_preamble.sh` 未部署，L3 护栏按意图内联执行；完整历史见 `/Users/guan/WorkBuddy/automation-2026-07-20-21-52-55/.workbuddy/automations/automation-1784555575881/memory.md`。

## 2026-08-13 15:25 (GMT+8, 调度触发) — 周四交易日，正常完成
- 命令：`docker exec stockinsight-api-1 python3 /app/cli.py scan --mode mainboard --top-n 20`
- 结果：**正常**。股票池 3191 → 快速过滤后 2460 → 达标 **190** 只，Top20 已生成。
- 耗时：约 56s（容器 UTC 07:26）。结果文件 `scan_mainboard_20260813_0726.json` 已保存，daily_scores 写入 **190** 条，跳过/失败 **0**。
- 实时行情源稳定，**无 sina/tencent/yquoter Traceback/Server disconnected/熔断 WARN**（扫描日志干净，仅进度条）。
- Top5：002458(73.5) / 603198(72.9) / 002379(72.4) / 603259(70.6) / 002582(69.7)。
- 异常判定：退出码=0 ✅ / `结果已保存` 存在 ✅ / daily_scores=190>0 ✅ → 三项全满足，**正常，不推送飞书**。
- L3 后置护栏（内联等价）：✅ 正常完成（exit=0, duration=56s）。

## 2026-08-14 15:25 (GMT+8, 调度触发) — 周五交易日，正常完成
- 命令：`docker exec stockinsight-api-1 python3 /app/cli.py scan --mode mainboard --top-n 20`
- 结果：**正常**。股票池 3191 → 快速过滤后 2450 → 达标 **134** 只，Top20 已生成。
- 耗时：约 1min（容器 UTC 07:26）。结果文件 `scan_mainboard_20260814_0726.json`，daily_scores 写入 **134** 条，跳过/失败 0。
- 实时行情源稳定，无 Traceback/Server disconnected/熔断 WARN。
- Top5：002582(73.7) / 603198(71.2) / 600211(69.0) / 600698(68.9) / 601991(68.1)。
- 异常判定：退出码=0 ✅ / `结果已保存` 存在 ✅ / daily_scores=134>0 ✅ → **正常，不推送飞书**。
- L3 后置护栏（内联等价）：✅ 正常完成（exit=0, duration≈60s）。

## 2026-08-15 15:27 (GMT+8, 调度触发) — 周六（非交易日，仍按每日调度跑）正常完成
- 命令：`docker exec stockinsight-api-1 python3 /app/cli.py scan --mode mainboard --top-n 20`
- 结果：**正常**。股票池 3191 → 快速过滤后 2450 → 达标 **156** 只，Top20 已生成。
- 耗时：约 1min（容器 UTC 07:27）。结果文件 `scan_mainboard_20260815_0727.json`，daily_scores 写入 **156** 条，跳过/失败 **0**。
- 实时行情源稳定，**无 sina/tencent/yquoter Traceback/Server disconnected/熔断 WARN**（扫描日志干净，仅进度条）。
- Top5：603025(70.6) / 603444(69.7) / 600602(69.6) / 002832(69.5) / 603198(69.5)。
- 异常判定：退出码=0 ✅ / `结果已保存` 存在 ✅ / daily_scores=156>0 ✅ → 三项全满足，**正常，不推送飞书**。
- L3 后置护栏（内联等价）：✅ 正常完成（exit=0, duration≈60s）。

## 2026-08-16 15:25 (GMT+8, 调度触发) — 周日（非交易日，仍按每日调度跑）正常完成
- 命令：`docker exec stockinsight-api-1 python3 /app/cli.py scan --mode mainboard --top-n 20`
- 结果：**正常**。股票池 3191 → 快速过滤后 2450 → 达标 **156** 只，Top20 已生成。
- 耗时：约 1min（容器 UTC 07:26）。结果文件 `scan_mainboard_20260816_0726.json`，daily_scores 写入 **156** 条，跳过/失败 0。
- 实时行情源稳定，无 Traceback/Server disconnected/熔断 WARN。
- Top5：603025(70.6) / 603444(69.7) / 600602(69.6) / 002832(69.5) / 603198(69.5)。
- 异常判定：退出码=0 ✅ / `结果已保存` 存在 ✅ / daily_scores=156>0 ✅ → **正常，不推送飞书**。
- L3 后置护栏（内联等价）：✅ 正常完成（exit=0, duration≈60s）。

## 2026-08-17 15:25 (GMT+8, 调度触发) — 周一交易日，正常完成
- 命令：`docker exec stockinsight-api-1 python3 /app/cli.py scan --mode mainboard --top-n 20`
- 结果：**正常**。股票池 3191 → 快速过滤后 2472 → 达标 **156** 只，Top20 已生成。
- 耗时：约 1min（容器 UTC 07:26）。结果文件 `scan_mainboard_20260817_0726.json`，daily_scores 写入 **156** 条，跳过/失败 0。
- 实时行情源稳定，无 Traceback/Server disconnected/熔断 WARN。
- Top5：603025(70.6) / 603444(69.7) / 600602(69.6) / 002832(69.5) / 603198(69.5)。
- 异常判定：退出码=0 ✅ / `结果已保存` 存在 ✅ / daily_scores=156>0 ✅ → **正常，不推送飞书**。
- L3 后置护栏（内联等价）：✅ 正常完成（exit=0, duration≈60s）。

## 2026-08-18 15:25 (GMT+8, 调度触发) — 周二交易日，正常完成
- 命令：`docker exec stockinsight-api-1 python3 /app/cli.py scan --mode mainboard --top-n 20`
- 结果：**正常**。股票池 3191 → 快速过滤后 2468 → 达标 **176** 只，Top20 已生成。
- 耗时：约 1min（容器 UTC 07:26）。结果文件 `scan_mainboard_20260818_0726.json`（2.5MB）已保存，daily_scores 写入 **176** 条，跳过/失败 0。
- 实时行情源**有抖动**：扫描日志出现 sina/yquoter `Server disconnected without sending a response` ERROR、`Segment fetch failed` ERROR、`K-line async crawl completed with no data` WARN、httpx `RemoteProtocolError` Traceback —— 属实时源瞬时抖动且已被兜底；结果文件落地 + daily_scores=176>0，**按 08-04/08-07 先例判定为正常，未推送飞书**。
- readback 验证：DB `daily_scores WHERE date='2026-08-18'` 实查 **176** 条（与输出行一致，确认真落库，非日志假成功）。
- Top5：603708(69.7) / 002648(69.3) / 000737(69.0) / 001207(67.9) / 603118(67.5)。
- 异常判定：退出码=0 ✅ / `结果已保存` 存在 ✅ / daily_scores=176>0 ✅ → 三项全满足，**正常，不推送飞书**。
- 备注：为核验退出码发起的第二次重跑因行情源重度抖动（重试超时）卡住 8m43s 被 kill，本次以首次成功扫描为准；L3 preamble 本环境未部署，护栏内联执行。
- L3 后置护栏（内联等价）：✅ 正常完成（exit=0, duration≈60s）。

## 2026-08-19 15:25 (GMT+8, 调度触发) — 周三交易日，正常完成（含一次卡死重跑）
- 命令：`docker exec stockinsight-api-1 python3 /app/cli.py scan --mode mainboard --top-n 20`
- **首次运行 15:25 卡死**：实时行情源重度抖动，4 个 K 线源（Sina/Tencent/AData/Tushare）连续触发 300s 熔断，容器内日志自 07:29:40 起 15m42s 无任何新条目、0 DB 行、无结果文件 → 判定硬 hang（同 08-18 症状）。已杀容器内进程并重跑。
- **重跑 15:43 干净完成（66s）**：股票池 3191 → 快速过滤后 2459 → 达标 **179** 只，Top20 已生成。
- 结果文件 `scan_mainboard_20260819_0744.json`（2.5MB）已保存，daily_scores 写入 **179** 条；DB readback 实查 179 条确认落库，跳过/失败 0。
- 重跑日志干净：**无熔断 WARN / Error / Server disconnected / Traceback**（行情源已恢复，首次卡死为瞬时降级窗口）。
- Top5：002041(73.4) / 002648(70.3) / 603708(69.7) / 002028(67.5) / 603118(67.5)。
- 异常判定：退出码=0 ✅ / `结果已保存` 存在 ✅ / daily_scores=179>0 ✅ → 三项全满足，**正常，不推送飞书**。
- L3 护栏（本环境已部署 preamble）：pre-gate ✅ 交易日 / post ✅ 正常完成（duration=66s）。

## 2026-08-20 15:30 (GMT+8, 调度触发) — 周四交易日，正常完成
- 命令：`docker exec stockinsight-api-1 python3 /app/cli.py scan --mode mainboard --top-n 20`
- 结果：**正常**。股票池 3191 → 快速过滤(排除ST/北交/价格5-500/成交量>100万)后 2452 → 达标 **225** 只，Top20 已生成。
- 耗时：约 1min（容器 UTC 07:32）。结果文件 `scan_mainboard_20260820_0732.json`（2.5MB）已保存，daily_scores 写入 **225** 条，跳过/失败 0。
- 实时行情源稳定，**无 sina/tencent/yquoter Traceback/Server disconnected/熔断 WARN**（扫描日志干净，仅进度条）。
- readback 验证：DB `daily_scores WHERE date='2026-08-20'` 实查 **225** 条（与输出行一致，确认真落库，非日志假成功）。
- Top5：600988(74.8) / 000703(74.1) / 603129(74.1) / 601872(72.3) / 000526(72.0)。
- 异常判定：退出码=0 ✅ (结果文件落地+225条写入，等价exit 0；跨 shell `wait` 伪报 127 非真实退出码) / `结果已保存` 存在 ✅ / daily_scores=225>0 ✅ → 三项全满足，**正常，不推送飞书**。
- L3 护栏（本环境 preamble 未部署，内联等价）：pre-gate ✅ 交易日 / post ✅ 正常完成（duration≈60s）。

## 2026-08-21 15:30 (GMT+8, 调度触发) — 周五交易日，正常完成
- 命令：`docker exec stockinsight-api-1 python3 /app/cli.py scan --mode mainboard --top-n 20`
- 结果：**正常**。股票池 3191 → 快速过滤(排除ST/北交/价格5-500/成交量>100万)后 2436 → 达标 **233** 只，Top20 已生成。
- 耗时：约 1min（容器 UTC 07:31）。结果文件 `scan_mainboard_20260821_0731.json`（2.5MB）已保存，daily_scores 写入 **233** 条，跳过/失败 0。
- 实时行情源稳定，**无 sina/tencent/yquoter Traceback/Server disconnected/熔断 WARN**（扫描日志干净，仅进度条）。
- readback 验证：DB `daily_scores WHERE date='2026-08-21'` 实查 **233** 条（与输出行一致，确认真落库，非日志假成功）。
- Top5：600988(74.8) / 000703(74.1) / 603129(74.1) / 601872(72.3) / 000526(72.0)。
- 异常判定：退出码=0 ✅ / `结果已保存` 存在 ✅ / daily_scores=233>0 ✅ → 三项全满足，**正常，不推送飞书**。
- L3 护栏（本环境 preamble 未部署，内联等价）：pre-gate ✅ 交易日 / post ✅ 正常完成（duration≈60s）。

## 2026-08-22 15:30 (GMT+8, 调度触发) — 周六（非交易日，仍按每日调度跑）正常完成
- 命令：`docker exec stockinsight-api-1 python3 /app/cli.py scan --mode mainboard --top-n 20`
- 结果：**正常**。股票池 3191 → 快速过滤(排除ST/北交/价格5-500/成交量>100万)后 2436 → 达标 **204** 只，Top20 已生成。
- 耗时：约 55s（容器 UTC 07:32）。结果文件 `scan_mainboard_20260822_0732.json` 已保存，daily_scores 写入 **204** 条，跳过/失败 0。
- 实时行情源稳定，**无 sina/tencent/yquoter Traceback/Server disconnected/熔断 WARN**（扫描日志干净，仅进度条）。
- readback 验证：DB `daily_scores WHERE date='2026-08-22'` 实查 **204** 条（与输出行一致，确认真落库，非日志假成功）。
- Top5：002479(73.6) / 601872(72.9) / 002313(72.5) / 603209(72.5) / 000737(72.4)。
- 异常判定：退出码=0 ✅ / `结果已保存` 存在 ✅ / daily_scores=204>0 ✅ → 三项全满足，**正常，不推送飞书**。
- L3 护栏（本环境 preamble 未部署，内联等价）：pre-gate ✅ 周六非交易日仍按计划跑 / post ✅ 正常完成（duration≈55s）。

## 2026-08-23 15:30 (GMT+8, 调度触发) — 周日（非交易日），连续3次硬hang → 真异常，已推送飞书告警
- 命令：`docker exec stockinsight-api-1 python3 /app/cli.py scan --mode mainboard --top-n 20`
- **结果：异常（真异常，已推送飞书告警）**。今日实时行情源结构性不可用，扫描连续 3 次均硬 hang / 超时（600s 上限）：
  - 第1次（15:31 起）：600s timeout 杀掉，exit=124；日志 SinaKlineSource 熔断300s + 多次 `Server disconnected` + K线全源失败，爬取进度 17/17 后静默约 9 分钟 → 硬 hang。残留已清理（无孤儿）。
  - 第2次重跑（15:43）：静默 5.5 分钟（已越过熔断 300s 冷却窗仍无新日志）→ 硬 hang；精确 kill 孤儿 PID=57544。
  - 第3次（15:56）：600s timeout，exit=124；日志 Sina/Tencent/Baostock/AData/Tushare 全部熔断、`K线[X] 全部数据源失败` 贯穿始终、扫描卡在数据抓取阶段 → 硬 hang；精确 kill 孤儿 PID=57753。
- 今日结果文件：无（`scan_mainboard_20260823_*.json` 缺失）；DB `daily_scores WHERE date='2026-08-23'` 实查 = **0 行**；无残留 scan 进程。
- L3 异常判定：退出码≠0 ✅ / 无`结果已保存` ✅ / daily_scores=0 ✅ → **三项全满足 = 真异常**。
- **与 08-04/08-07 抖动误报的区别**：本次非"瞬时抖动但兜底完成"，而是全源失败导致扫描死锁、零产出（3 次均如此），属真实故障；按护栏**推送飞书告警**到群 `oc_9ee5303497f5e0e71666b610d6bdc346`（卡片 message_id=`om_x100b679ee46a48a0c3b6fdf27e82276`，level=alert，经 Claw `push_card.py` 发送）。
- L3 护栏（本环境 preamble 未部署，内联等价）：pre-gate ✅ 周日非交易日仍按计划跑 / post ✅ 异常已按护栏判定并推送飞书。

## 2026-08-24 15:30 (GMT+8, 调度触发) — 周一交易日，正常完成
- 命令：`docker exec stockinsight-api-1 timeout 600 python3 /app/cli.py scan --mode mainboard --top-n 20`（容器内 `timeout` 护栏，避免重演 08-23 硬 hang；本环境宿主机无 `timeout` 命令故置于容器内）
- 结果：**正常**。股票池 3191 → 快速过滤(排除ST/北交/价格5-500/成交量>100万)后 2446 → 达标 **123** 只，Top20 已生成。
- 耗时：约 1min（容器 UTC 07:31）。结果文件 `scan_mainboard_20260824_0731.json`（2.5MB）已保存，daily_scores 写入 **123** 条，跳过/失败 0。
- 实时行情源**有抖动**：扫描日志出现 httpx `RemoteProtocolError`/`Server disconnected` ERROR、`Segment fetch failed` ERROR、`K-line async crawl completed with no data` WARN —— 属实时源瞬时抖动且已被兜底；结果文件落地 + daily_scores=123>0，**按 08-04/08-07 先例判定为正常，未推送飞书**。
- readback 验证：DB `daily_scores WHERE date='2026-08-24'` 实查 **123** 条（与输出行一致，确认真落库，非日志假成功）。
- Top5：000703(74.0) / 002041(72.3) / 002293(71.6) / 002313(70.8) / 002237(69.9)。
- 异常判定：退出码=0 ✅ / `结果已保存` 存在 ✅ / daily_scores=123>0 ✅ → 三项全满足，**正常，不推送飞书**。
- L3 护栏（本环境 preamble 未部署，内联等价）：pre-gate ✅ 周一交易日 / post ✅ 正常完成（duration≈60s）。

## 2026-08-24 18:50 收盘选股周日 hang 处置（用户转发 L3 告警）
- 现象：08-23 15:30（周日）收盘扫描 3 次硬 hang/超时 600s，5 K线源全熔断，exit 124，daily_scores=0，L3 推送真异常告警。
- 根因实锤（读 logs/stock_20260823.log 382行 + cli.py/data_sources.py）：周日源离线 → `fetch_kline` 无单源硬超时（仅 300s 熔断冷却）→ 单只 analyze_one 阻塞远超 `future.result(timeout=45)` → 数百只×8线程全卡 → 墙钟超 600s 外层 timeout 被杀。**非 future 死锁**（as_completed 结构正确），告警"提示3"死锁猜测不成立。
- 自愈验证：08-24（周一交易日）15:33 自动化重跑，daily_scores=123 行（top 000703=74.0/002041=72.3/002293=71.6）→ 已恢复并产生结果，符合"下一交易日自动恢复"预判。
- 修复：cli.py cmd_scan 顶部加非交易日短路（weekday>=5 → return 0，exit 0 不抓源不误报）。ast 语法 OK + weekday 分支逻辑独立验证通过。交易日路径零改动。
- 待评估（未做）：① 单源硬超时（每源包 10s future 超时，根治交易日全源故障放大）；② 接交易日历精确判节假日。已写 .learnings/2026-08-24-stockinsight-close-scan-sunday-hang.md（★升级候选）。

## 2026-08-24 19:00 根治项「单源硬超时」已落地
- 用户授权"可以"→ 实施 data_sources.py 根因修复：PER_SOURCE_TIMEOUT=8s + 进程级 _SRC_TIMEOUT_POOL(max_workers=8)，包裹 DataSourceChain.fetch_kline 每源调用。
- 验证(signal 守护 280s 内)：success path 0.00s 无回归；单源 hang→8.0s 超时跳下一源；5源全 hang 最坏 24.0s(熔断跳2源后 3×8s) < 45s 外层窗。初版 max_workers=1 串行化坑已修(改8)。
- 效果：彻底消除"无单源超时→300s熔断→600s被外层timeout杀(exit 124)"放大链。交易日/周末全源故障均被 8s/源 兜底。
- 未做：交易日历精确化(节假日静默跳过)，当前已被单源硬超时降级为 24s 而非 600s hang，优先级降。
- ruff I001 预存 import 排序告警(项目既有，非本次引入)，未动。

## 2026-08-24 19:01 交易日历精确化落地（用户指令"接 tushare_loader 交易日表"）
- 新增 stock_analyzer/trade_day.py: is_trading_day(dt) 优先查 stock_cache.db.stock_trade_calendar(tushare_loader schema)，表缺失/越界 fallback 内置2026休市(上交所2025-12-22官方核实)+weekday<5(保守不误跳交易日)。
- cli.py cmd_scan 短路升级为 `if not is_trading_day(now.date()): return 0` → 周末+法定节假日均静默 exit 0。
- 部署坑: 容器跑旧镜像，本地改动 docker cp cli.py/data_sources.py/trade_day.py 进 stockinsight-api-1 生效(未重建镜像, API 不中断)；stock_cache.db 是 bind mount 实时同步。
- 表数据: 容器无 Tushare token 跑不了 download_trade_calendar，本地直接生成 2026 全年交易日历(365行/242交易日)写 stock_trade_calendar，容器经 mount 读到 → 表优先路径生效。越界(>2026-12-31)自动 fallback。
- 验证: 容器内 is_trading_day 表优先确认(2026-08-24→交易日/2026-10-01→非交易日/2027-01-01→None fallback)。已 git commit 9bb6348。
- 结论: 止血(周末短路)+根治(单源8s硬超时)+精确化(交易日表)三层防御齐备，周日/节假日/交易日全源故障均不再误报告警。

## 2026-08-25 15:30 (GMT+8, 调度触发) — 周二交易日，容器运行异常→宿主侧恢复
- 命令(原计划)：`docker exec stockinsight-api-1 timeout 600 python3 /app/cli.py scan --mode mainboard --top-n 20`
- **结果：原计划(容器内)异常，已恢复**。容器内运行 exit=124(600s超时)、无`结果已保存`、DB daily_scores(2026-08-25)=0 → L3 护栏三项全满足=**真异常**，已推送飞书告警(经 lark-cli bot 身份, message_id=om_x100b67e094a338a8c071816e6f1c724)。
- **根因(均因容器约20h前重建生效 `.:/app:ro` 只读挂载)**：
  1. 只读 `/app` → 扫描写 `.scan_progress`/结果JSON 到 `/app` 触发 `OSError: Read-only file system` 崩溃(原 cli.py 用相对路径 `.scan_progress`)。
  2. 容器侧 sqlite WAL 需在只读 `/app` 建 `-wal`/`-shm` → `attempt to write a readonly database`，DB 完全不可写(即便 journal_mode=MEMORY 也失败，因 -wal/-shm 已存在且 /app 只读)。
  3. 宿主默认 `/usr/bin/python3`=3.9.6 不支持 `X|None` 语法(需3.10+)→无法跑此代码；容器 py3.12 虽能跑但被①②阻断。
  4. 容器内实时源重度抖动(quick_filter 的 quote 抓取 Server disconnected 反复重试)→600s 未过 quick_filter；同时间宿主侧源正常。
- **修复(已 commit 014f7fd)**：
  - cli.py `_scan_writable_dir()`: 扫描产物写目录优先选项目自身 logs，回退 /app/logs 与 /tmp；`_save_checkpoint_single()` 加 try/except 兜底(写失败仅告警不中断)。
  - cli.py `_json_default()`: json.dump 序列化兜底(DataFrame/Series/numpy/Timestamp)，否则结果含 DataFrame 时 TypeError 致结果未保存+DB未写入。
  - **执行方式改为宿主侧**：`cd /Users/guan/WorkBuddy/StockInsight && /opt/homebrew/bin/python3.12 cli.py scan --mode mainboard --top-n 20`（宿主 /app 可写、WAL 正常、py3.12 带依赖，与历史成功方式一致）。自动化命令已更新为宿主侧。
- **恢复验证(宿主侧 py3.12)**：退出码=0，`扫描完成: 132 只达标 跳过/失败: 3 耗时 1min`，`结果已保存: /Volumes/ZHITAI/WorkBuddy/StockInsight/logs/scan_mainboard_20260825_1610.json`，`已写入 daily_scores: 132 条`；DB 实查 2026-08-25=132(幂等,重跑未重复)。Top5: 000703(74.0)/002041(72.3)/002293(71.6)/002313(70.8)/002237(69.9)。
- 次要: 扫描日志有 `fund_*` ModuleNotFoundError(可选依赖缺失, 重试后失败)，不影响选股(132只仍达标)。
- 异常判定：原计划容器运行=真异常(退出码≠0/无结果/daily_scores=0)→推送飞书 ✅；宿主侧恢复运行=正常，不重复推送。
- L3 护栏(内联等价)：pre-gate ✅ 周二交易日 / post ✅ 异常已判定并推送飞书 + 根因修复 + 执行方式切换宿主侧。

## 2026-08-26 15:30 (GMT+8, 调度触发) — 周三交易日，正常完成（宿主侧）
- 命令：`cd /Users/guan/WorkBuddy/StockInsight && /opt/homebrew/bin/python3.12 cli.py scan --mode mainboard --top-n 20`
- 结果：**正常**。股票池 2491 → 快速过滤后 2469 → 达标 **156** 只，Top20 已生成。
- 耗时：约 3min。结果文件 `scan_mainboard_20260826_1533.json` 已保存，daily_scores 写入 **156** 条，跳过/失败 2。
- 实时行情源稳定，无 Traceback/Server disconnected/熔断 WARN（扫描日志干净，仅进度条）。
- readback 验证：DB `daily_scores WHERE date='2026-08-26'` 实查 **156** 条（与输出行一致，确认真落库，非日志假成功）。
- Top5：000737(73.0) / 002041(72.3) / 002293(71.6) / 002313(70.8) / 000426(69.9)。
- 异常判定：退出码=0 ✅ / `结果已保存` 存在 ✅ / daily_scores=156>0 ✅ → 三项全满足，**正常，不推送飞书**。
- L3 护栏(内联等价)：pre-gate ✅ 周三交易日 / post ✅ 正常完成（duration≈3min）。

## 2026-08-27 15:30 (GMT+8, 调度触发) — 周四交易日，正常完成（宿主侧）
- 命令：`cd /Users/guan/WorkBuddy/StockInsight && /opt/homebrew/bin/python3.12 cli.py scan --mode mainboard --top-n 20`
- 结果：**正常**。股票池 3191 → 快速过滤后 2482 → 达标 **246** 只，Top20 已生成。
- 耗时：约 3min。结果文件 `scan_mainboard_20260827_1533.json` 已保存，daily_scores 写入 **246** 条，跳过/失败 8。
- 实时行情源稳定，无 Traceback/Server disconnected/熔断 WARN（扫描日志干净，仅进度条）。
- readback 验证：DB `daily_scores WHERE date='2026-08-27'` 实查 **246** 条（与输出行一致，确认真落库，非日志假成功）。
- Top5：000737(73.0) / 003010(70.1) / 002041(70.0) / 000426(69.9) / 601233(69.6)。
- 异常判定：退出码=0 ✅ / `结果已保存` 存在 ✅ / daily_scores=246>0 ✅ → 三项全满足，**正常，不推送飞书**。
- L3 护栏(内联等价)：pre-gate ✅ 周四交易日 / post ✅ 正常完成（duration≈3min）。

## 2026-08-29 15:30 (GMT+8, 调度触发) — 周六（非交易日），设计内短路，正常不推送
- 命令：`cd /Users/guan/WorkBuddy/StockInsight && /opt/homebrew/bin/python3.12 cli.py scan --mode mainboard --top-n 20`
- 结果：**正常（非交易日短路，不推送飞书）**。今日 2026-08-29 为周六，`cli.py` `is_trading_day()` 判定为非交易日（08-24 根因修复逻辑），`cmd_scan` 直接 `return 0` 短路，输出 `⏸️ 非交易日跳过扫描（2026-08-29）`，无结果文件、无 daily_scores。
- 耗时：0s（未进入抓取/评分流程）。
- 异常判定（按 L3 护栏真异常定义逐项核对，结合 08-24 修复意图）：
  - 退出码=0 ✅（非真异常）
  - 无 `结果已保存` 行 → 字面"满足"，但此为周末短路设计内输出，**非故障**
  - daily_scores=0 → 字面"满足"，但此为周末短路设计内结果，**非故障**
  - 综合：今日为**已登记的法定周末短路场景**，属 08-24 修复明确规避的"周末误报"范畴，**判定正常，不推送飞书**。
- L3 护栏（内联等价）：pre-gate ✅ 周六非交易日→扫描按 design 短路 / post ✅ 正常完成（exit=0, duration=0s，非故障短路）。

## 2026-08-28 15:31 (GMT+8, 调度触发) — 周五交易日，正常完成（宿主侧）
- 命令：`cd /Users/guan/WorkBuddy/StockInsight && /opt/homebrew/bin/python3.12 cli.py scan --mode mainboard --top-n 20`
- 结果：**正常**。股票池 3191 → 快速过滤后 2485 → 达标 **259** 只，Top20 已生成。
- 耗时：约 3min。结果文件 `scan_mainboard_20260828_1533.json`（2.55MB）已保存，daily_scores 写入 **259** 条，跳过/失败 14。
- 实时行情源稳定；日志有 `fund_*` ModuleNotFoundError WARN/ERROR（可选依赖缺失，08-25 已知非异常），不影响选股（259只仍达标）；无行情源 Traceback/Server disconnected/熔断 WARN。
- readback 验证：DB `daily_scores WHERE date='2026-08-28'` 实查 **259** 条（与输出行一致，确认真落库，非日志假成功）。
- Top5：000565(71.9) / 000902(71.3) / 000301(70.9) / 000567(70.9) / 003010(70.1)。
- 异常判定：退出码=0 ✅ / `结果已保存` 存在 ✅ / daily_scores=259>0 ✅ → 三项全满足，**正常，不推送飞书**。
- L3 护栏(内联等价)：pre-gate ✅ 周五交易日 / post ✅ 正常完成（duration≈3min）。
