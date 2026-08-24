# Learnings (StockInsight)

Corrections, insights, and knowledge gaps captured during development.

**Categories**: correction | insight | best_practice | knowledge_gap

---
### 2026-08-11 收盘扫描告警源误判（insight → ✅已升级(2026-08-16)）
- **类型**: insight
- **现象**: 告警 automation-1784555575881 称"容器内4个K线源(Sina/Tencent/AData/Tushare)全部熔断+出网持续中断"，建议待恢复重跑。
- **根因**(实测): 告警夸大影响面。查 `network_health.best_kline_source` 候选仅 [sina, tencent, baostock]，**AData/Tushare 不在 scan 主链路**（是 tushare_loader/enhanced-scan 辅助源）；eastmoney 超时也不影响 K 线扫描。当时(15:26)确属时段性容器出网中断，但 16:20 官方自检已恢复(sina✅61ms/tencent✅203ms/baostock✅, all_ok=True)。
- **处置**: 背景重跑 `scan --mode mainboard --top-n 20` → 速率12.6只/s、失败0、落盘 daily_scores 195条。今日结果补齐。
- **防复犯**: 告警解读先查源码确认主链路源依赖；nc 探测 HTTPS 不准，用 curl 实测；容器 healthy 状态只探内部端口不代表出网正常。
- **✅已升级(2026-08-16)**: 本例"单点日志/告警误判、须查源码全链路"并入🔴铁律「单链路日志≠全链路, 禁脑补归因」(incident-triage 反模式已含 nc/curl、告警源误判条目)。
- **去重**: 首次

### 2026-08-23 收盘扫描全源失败死锁（knowledge_gap + insight → ★升级候选）
- **类型**: knowledge_gap（代码健壮性缺陷）+ insight（运维处置）
- **现象（证据，非脑补）**: 自动化 automation-1784555575881 触发 `scan --mode mainboard --top-n 20`，连续 3 次均硬 hang / 600s 超时（exit=124）：
  - 日志实锤：`K线[X] 全部数据源失败` 贯穿多只股票；熔断器[SinaKlineSource]/[TencentKlineSource]/[BaostockKlineSource] 均触发（另有 aux 源 AData/Tushare 熔断）；
  - 爬取阶段后进程静默 5+ 分钟（已越过 300s 熔断冷却窗仍无新日志）→ 死锁，非等待；
  - 结果文件缺失 + DB `daily_scores WHERE date='2026-08-23'` 实查 = **0 行**（readback 验证，确认真零产出）。
- **根因（假设，待复现确认）**: scan 主链路 K 线源 = sina/tencent/baostock（见 `network_health.best_kline_source` 候选）；当三者同时失败时，异步 K 线抓取底层 future/task 未设硬超时、兜底路径阻塞，主线程死锁 → 整轮零产出。属**代码健壮性缺陷，非单纯上游抖动**。
  ⚠️ **范围澄清（承接 08-11 教训）**: AData/Tushare 是 tushare_loader/enhanced-scan 辅助源，**不在 scan 主链路**；告警/记录须仅把 sina/tencent/baostock 列为 scan 阻断源，勿夸大影响面。
- **与 08-11 区别**: 08-11 是**误报**（源已恢复、重跑成功 195 条，告警却称"4 源全断"）；本次是**真故障**（3 次均 hang、零产出、readback 确认 0 行）。两者都须先查源码确认主链路源依赖，再下结论。
- **处置（已做）**: 每次 hang 后精确 kill 容器内孤儿 scan 进程（读 /proc 按精确 cmdline，未用 pkill -f 防误杀 sidecar）；重跑 3 次均失败 → 按 L3 护栏三项真异常条件（退出码≠0 / 无`结果已保存` / daily_scores=0）判定真异常 → 经 Claw `push_card.py` 推送卡片告警到 `oc_9ee5303497f5e0e71666b610d6bdc346`（message_id=`om_x100b679ee46a48a0c3b6fdf27e82276`，level=alert）。
- **防复犯 / 修复方向（待用户授权改代码）**: ① 给每股票 K 线抓取加 `asyncio.wait_for` 硬超时；② 全源失败时跳过该股票 / 回退缓存而非阻塞整轮；③ 扫描级 watchdog：N 秒无进度则干净中止并写"源不可用"错误 + 部分落盘，杜绝静默死锁。验证：指向黑洞源复现，确认能干净超时而非 hang。
- **✅已升级(2026-08-23)**：是 — 扫描死锁属生产级健壮性缺陷；建议升为 runbook「scan 超时即查孤儿进程 + 重跑 + 真异常告警」+ 代码层硬性超时。(已升🔴铁律"长耗时扫描/批处理/异步任务须硬性超时+孤儿进程检测+重跑")
- **去重**: 首次（同类：上游源全断致扫描 hang）
