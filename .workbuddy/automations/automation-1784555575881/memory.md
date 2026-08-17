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
