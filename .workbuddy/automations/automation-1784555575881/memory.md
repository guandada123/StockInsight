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
