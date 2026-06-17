# AGENTS.md — 双 AI 协作规范

本项目由 **Claude Code** 和 **Codex (OpenAI)** 共同维护。

## 能力矩阵

| 领域 | Claude Code | Codex | 结论 |
|------|:--:|:--:|------|
| **大项目重构** | ✅ 1M token，跨50+文件 | ❌ 上下文小，易丢 | Claude |
| **深度推理** | ✅ Plan模式+思考模式 | ⚠️ 一般 | Claude |
| **代码审查** | ⚠️ 能审但非独立 | ✅ 独立视角（不同模型） | Codex |
| **Agent编排** | ✅ 子Agent并行+状态追踪 | ❌ | Claude |
| **Git全流程** | ✅ commit/PR/worktree | ⚠️ | Claude |
| **生成图片** | ❌ 只能读不能画 | ✅ DALL-E / GPT Image | Codex |
| **视频理解/生成** | ❌ | ✅ 帧提取+生成 | Codex |
| **音频处理** | ❌ | ✅ Whisper转写 | Codex |
| **网页截图/视觉验证** | ⚠️ headless browser | ✅ 可视浏览器 | Codex |
| **沙箱执行** | ❌ 直接本地 | ✅ 隔离沙箱 | Codex |
| **简单脚本** | ⚠️ 牛刀杀鸡 | ✅ 轻快 | Codex |
| **定时任务** | ✅ Cron持久化 | ❌ | Claude |
| **跨会话记忆** | ✅ MEMORY.md | ❌ | Claude |
| **大文件处理** | ✅ PDF/图片/Word/Excel | ⚠️ | Claude |
| **系统级操作** | ✅ Bash/进程/DB | ⚠️ | Claude |

## 角色分工

| 角色 | Claude Code | Codex |
|------|:--:|:--:|
| 主力开发 | ✅ 复杂功能、架构、大文件重构 | 补位：简单脚本、批量替换 |
| 代码审查 | — | ✅ 独立审查（不同模型视角） |
| 股票分析 | ✅ 全链路量化分析 | — |
| 文档维护 | ✅ SKILL.md、DOCX | — |
| Bug 修复 | ✅ 根因分析 | ✅ 第二意见 |
| 图片/视频 | — | ✅ 报告配图、截图验证 |

## 成本对比

| | Claude Code | Codex |
|------|:--:|:--:|
| 费用 | **低（基准）** | **高（~5倍）** |
| 性价比 | 日常主力，量大便宜 | 按需调用，贵但补盲区 |

**原则：能用 Claude 的不用 Codex，只有 Claude 做不了的才派 Codex。**

## 触发规则

| 场景 | 谁来做 | 原因 |
|------|:--:|------|
| 改超过3个文件 | Claude Code | 便宜+擅长 |
| 需要架构设计/Plan | Claude Code | 便宜+擅长 |
| 需要"第二意见"审查 | Codex review | 独立视角，Claude做不了 |
| 需要生成图片/视频 | Codex | Claude做不了 |
| 需要深度推理排bug | Claude Code | 便宜+擅长 |
| 简单脚本/一次性任务 | Claude Code | 便宜，没必要用贵的 |
| 需要跨会话上下文 | Claude Code (MEMORY.md) | 便宜+独有能力 |

## 协作流程

```
Claude Code 写代码 → Codex review → 分歧人工判断
Codex 改代码 → Claude Code 最终检查 → 确认提交
Codex 生成图片/视频 → Claude Code 验证 → 合入报告
大改动前先 commit，两边在同一基准上干活
```

## 新增功能

### K线形态分析 (DOCX报告)
- 使用 generate_kline_interpretation_with_today() 聚焦近10个交易日形态识别
- 输出: trend_phase(趋势阶段)、recent_patterns(近期形态列表)、summary(综合判断)、key_observation(关键观察)
- 形态类型: bullish(看涨)/bearish(看跌)，含可靠性评级(高/中/低)
- 27种K线形态识别: 三只乌鸦、黄昏之星、早晨之星、阳包阴、阴包阳、锤子线、射击之星等

### 庄家意图分析 (DOCX报告)
- 使用 analyze_manipulator_intention() 识别庄家四阶段
- 四阶段: 建仓 → 洗盘 → 拉升 → 出货 (含置信度)
- 输出: phase(当前阶段)、signals(判断依据列表)、volume_analysis(成交量分析)、assessment(综合评估)、risk_note(风险提示)

### 双层过滤选股 (ml_scan.py)

```
python ml_scan.py                    # 主板 top10，双层过滤
python ml_scan.py --mode full        # 全A股
python ml_scan.py --top-n 20         # 主板 top20
```

| 层级 | PE | PB | 量比 | 换手率 | ML条件 | 标记 |
|:----:|:--:|:--:|:----:|:------:|:------:|:----:|
| Tier1 严格 | 5-60 | ≤8 | ≥0.7 | ≤25% | 三模型看涨 | Tier1 |
| Tier2 宽松 | 5-100 | ≤15 | ≥0.5 | ≤35% | 三模型看涨 | Tier2 [宽松] |

- Tier1 选不够 → 自动降级到 Tier2
- 每个候选标注所属层级，Tier2 会额外提示风险更高

## 速度优化记录

| 优化项 | 优化前 | 优化后 | 方案 |
|:-----:|:------:|:------:|------|
| 周末K线不更新 | 数据停在上周 | 周末也拉取 | cache.py 放宽 is_weekend 条件 |
| 宏观数据API | 23.8s | 0.006s | SQLite缓存(7天TTL) |
| ML三模型训练 | 4.7s | 0.001s | 内存缓存 _RESULT_CACHE |
| ML跨进程复用 | 4.7s | 0.01s | 磁盘缓存 models/ |
| gen_docx报告 | 47s | 12.9s | 以上三项合计 |
| 后端分析API | 每次重算 | 5分钟TTL | _ANALYSIS_CACHE (backend) |
| ML预测缓存 | 每次重训 | 0ms命中 | _cached_predict_ensemble |

## 工作规则

1. **大改动前先 commit**，两边在同一基准上干活，避免互相踩
2. **修改文件后必须更新 SKILL.md** 的相关内容（功能、模块列表、注意事项）
3. **项目结构变化**（新增/删除文件）立即同步到 SKILL.md 项目结构段
4. **发现的 bug/陷阱** 记录到 SKILL.md "注意事项 & 已知陷阱"段
5. **性能优化** 记录到 SKILL.md 性能优化记录表
6. **不要改对方的配置文件**（Claude: CLAUDE.md, Codex: 对应的配置）
7. **git commit 前双方确认** 没有语法错误和逻辑 bug

## 项目上下文

- 语言：Python 3.x + TypeScript (React) + Rust (Tauri)
- 数据源：新浪/腾讯/Baostock/东方财富/akshare/Tushare/TickFlow
- 数据库：SQLite (stock_cache.db ~152MB)
- 完整技能文档：`C:\Users\47535\.claude\skills\stock-quant-analysis\SKILL.md`
- 最近重构：fetcher.py → fetcher/ 包、前端组件化、ML缓存、analyzer.py 解耦

## 当前状态 (2026-06-18)

- 仓库已公开: https://github.com/nguyenchunghieu799-blip/stock-insight
- MIT LICENSE 开源
- README.md 已上线
- fetcher/__init__.py 1495行单体过大，后续可拆分子模块
