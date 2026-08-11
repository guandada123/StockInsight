# Learnings (StockInsight)

Corrections, insights, and knowledge gaps captured during development.

**Categories**: correction | insight | best_practice | knowledge_gap

---
### 2026-08-11 收盘扫描告警源误判（insight → ★升级候选）
- **类型**: insight
- **现象**: 告警 automation-1784555575881 称"容器内4个K线源(Sina/Tencent/AData/Tushare)全部熔断+出网持续中断"，建议待恢复重跑。
- **根因**(实测): 告警夸大影响面。查 `network_health.best_kline_source` 候选仅 [sina, tencent, baostock]，**AData/Tushare 不在 scan 主链路**（是 tushare_loader/enhanced-scan 辅助源）；eastmoney 超时也不影响 K 线扫描。当时(15:26)确属时段性容器出网中断，但 16:20 官方自检已恢复(sina✅61ms/tencent✅203ms/baostock✅, all_ok=True)。
- **处置**: 背景重跑 `scan --mode mainboard --top-n 20` → 速率12.6只/s、失败0、落盘 daily_scores 195条。今日结果补齐。
- **防复犯**: 告警解读先查源码确认主链路源依赖；nc 探测 HTTPS 不准，用 curl 实测；容器 healthy 状态只探内部端口不代表出网正常。
- **去重**: 首次
