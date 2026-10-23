# 行情画布（Market Canvas）设计方案

> 适用项目：StockInsight Pro（Tauri 2 + React 19 + ECharts 6 桌面端）
> 状态：方案待评审 ｜ 影响范围：`src/components`（新增 1 个组件族）+ `src/pages/StockAnalysis.tsx`（渲染层替换）
> 不改动：后端 API、数据获取逻辑、`stock_analyzer` Python 层

---

## 0. 结论先行

| # | 结论 | 理由 |
|---|------|------|
| 1 | **不自绘 canvas**，升级现有 ECharts 为「单实例多面板画布」 | 当前数据量（120 点 × 8 series）远未触及 2D canvas 瓶颈；自绘会丢 tooltip / legend / dataZoom / axisPointer 全套现成能力，维护成本与收益不匹配 |
| 2 | **两个 ECharts 实例合并为一个** | 这是本次改造的核心价值：一个实例天然共享 xAxis，十字光标、缩放区间跨面板联动不需要任何手动同步代码 |
| 3 | **高度从硬编码改为容器契约** | 现状 380px + 220px 写死，在 800px 窗口下必然推开滚动条，是当前最直接的体验缺陷 |
| 4 | 分三批落地 | Wave 1 单实例化 + 响应式高度（P0）；Wave 2 交互增强（P1）；Wave 3 画线/对比（P2，按需） |

---

## 1. 现状诊断（代码级证据）

| 问题 | 证据位置 | 影响 |
|------|----------|------|
| 两个 ECharts 实例各自持有 x 轴 | `KlineChart.tsx:39-58`、`IndicatorChart.tsx:40-45` | 十字光标不联动，看 MACD 与 K 线需肉眼对齐日期 |
| 高度硬编码 | `KlineChart.tsx:124`（380）、`IndicatorChart.tsx:80`（220） | 1280×800 窗口下 nav 52 + footer + 市场概况 + 600px 图表 → 首屏溢出，必须滚动才能看完一个面板 |
| 无缩放能力 | 两处 option 均无 `dataZoom` | 后端固定返回 120 日，无法聚焦最近 20 日，短线分析（3-10 天）场景直接失效 |
| 指标系列数量变化会残留 | `IndicatorChart.tsx:52` 用 `Object.entries(data.values).map()` 生成 series | MACD(3) → RSI(2/3) 切换时，`setOption` 默认 merge 策略会保留多余旧系列，出现"幽灵线" |
| 主题色双源 | `KlineChart.tsx:34,76-79` 硬编码 `#0d1422` / `#ef4444`，与 `global.css:2-10` 的 `--srf` / `--rd` / `--gn` 并存 | 改主题需改两处，必然漏 |
| resize 无节流 | `KlineChart.tsx:21`、`IndicatorChart.tsx:22` 直接 `chart.resize()` | 拖拽窗口时每帧触发多次全量重排，桌面端可感知卡顿 |
| 分列数据在渲染层转置两次 | `KlineChart.tsx:30`（ohlc）、`:108`（volumes） | 每次 render 重建 O(n) 数组，且未按数据引用缓存 |
| 无 tooltip / axisPointer 配置 | 两处 option 均未声明 | 鼠标悬停无 OHLC 数值，只能看图估 |

**结论：不是"加一个画布"，而是把现有两块图表重构为一块有统一坐标系和交互状态的可视化画布。**

---

## 2. 用途与使用场景

### 2.1 定位
画布承载「单只股票的时序决策视图」，是个股分析页（`/stock/:code`）的第一视觉锚点。它只回答三个问题：**现在在什么位置（趋势/均线结构）、量能配不配合（成交量）、动能是强是弱（指标）**。

不做的事：不做多股网格、不做实时逐笔、不做下单入口。这些超出桌面分析端职责。

### 2.2 场景矩阵

| 场景 | 用户动作 | 画布响应 | 优先级 |
|------|----------|----------|--------|
| 快速判势 | 进入个股页 | 默认展示最近 60 日，MA5/10/20 叠加，量能与指标同屏 | P0 |
| 短周期聚焦 | 滚轮缩放 / 拖拽平移 | 单次缩放同步作用于全部面板，y 轴自动重算 | P0 |
| 动能切换 | 点 MACD / RSI / KDJ | 副图系列整体替换，主图与成交量不受影响、缩放区间保持 | P0 |
| 关键点位核对 | 悬停某根 K 线 | 十字光标穿透三面板，tooltip 显示 OHLC / 涨跌幅 / 量比 | P0 |
| 区间复盘 | 框选一段区间 | 底部显示区间涨跌幅、最大回撤、累计成交量 | P1 |
| 结构标注 | 画趋势线 / 水平线 | 标注持久化到 localStorage，按股票代码隔离 | P2 |
| 报告留档 | 导出当前视图 | 2x 分辨率 PNG（ECharts `getDataURL`） | P2 |

---

## 3. 交互与功能清单

### P0（Wave 1 必做）
1. **统一坐标系**：单实例 + 多 `grid`，`axisPointer.link` 跨面板联动
2. **dataZoom**：`inside`（滚轮缩放 + 拖拽平移）+ `slider`（底部缩略条），作用于全部 xAxis
3. **tooltip**：`trigger: 'axis'`，主图展示 开/高/低/收/涨跌幅/量比，副图展示指标值
4. **指标切换**：复用现有 `.segmented-btn` 样式，`replaceMerge: ['series']` 保证无残留
5. **响应式高度**：容器 `flex: 1`，内部按比例分配 grid
6. **默认视窗**：加载后自动聚焦最近 60 根（而非全量 120）

### P1（Wave 2）
7. MA 开关（legend 点击隐藏/显示，`selected` 状态持久化）
8. 双击复位缩放；`Esc` 取消框选
9. 区间统计面板（涨跌幅 / 最大回撤 / 累计量）
10. 键盘导航：`←` `→` 移动 axisPointer，`+` `-` 缩放

### P2（Wave 3，按需）
11. 画线工具（趋势线、水平线、斐波那契），存 localStorage
12. 双股叠加对比（需后端增加对比接口，本期不做）
13. 视图导出 PNG（2x）

---

## 4. 尺寸、分辨率与响应式适配

### 4.1 基准与边界

| 项 | 值 | 说明 |
|----|----|------|
| 设计基准窗口 | 1280 × 800 | `src-tauri/tauri.conf.json` 初始窗口 |
| 最小窗口 | 900 × 600 | 同文件 `minWidth` / `minHeight` |
| 画布可用高度 | `calc(100dvh - 320px)` | 扣除 nav 52 + footer 28 + 市场概况区 + 卡片内边距 |
| 画布高度约束 | `clamp(360px, calc(100dvh - 320px), 720px)` | 下限保证可读，上限防止 4K 竖屏拉伸 |
| 最小主图高度 | 320px | 对应 120 根 K 线单根 ≥ 4px，可辨 |

### 4.2 面板比例（基准 1280×800，画布高 ≈ 480px）

```
┌──────────────────────────────────────────────┐
│ 工具栏（标的 / 周期 / 指标切换）        36px  │
├──────────────────────────────────────────────┤
│                                              │
│  主图：K线 + MA5/10/20/60             58%    │  ≈ 278px
│                                              │
├──────────────────────────────────────────────┤
│  成交量柱                              14%    │  ≈ 67px
├──────────────────────────────────────────────┤
│  副图：MACD / RSI / KDJ               22%    │  ≈ 106px
├──────────────────────────────────────────────┤
│  dataZoom slider                       6%    │  ≈ 29px
└──────────────────────────────────────────────┘
```

比例用**运行时计算**而非百分比字符串，原因：ECharts `grid` 的百分比是相对容器高度的，多层 grid 叠加时手算容易错位；用统一函数算出 top/height 像素值，可保证面板间距恒定 12px 不随容器缩放而变形。

### 4.3 断点策略

| 断点 | 布局 | 说明 |
|------|------|------|
| ≥ 1180px | 三面板全开（主图 / 量 / 指标）+ slider | 基准形态 |
| 900–1179px | 量能并入主图底部 20%（同 grid 双 y 轴），保留副图 | 宽度不足时 x 轴拥挤，优先保住 K 线与指标 |
| < 900px | 单面板，segmented 切换「K线 / 指标」 | 浏览器端窄屏兜底；Tauri 窗口有 minWidth 不会触发 |

断点判定用 `ResizeObserver` 的 `contentRect.width`，不用 `window.matchMedia`——画布宽度取决于侧栏是否折叠，与视口宽度不等价。

### 4.4 分辨率与 DPR

- **渲染按 CSS px**，物理像素 = CSS px × `devicePixelRatio`，由 ECharts 内部处理，不手动 `ctx.scale`
- **首帧 init 时显式传入** `devicePixelRatio: window.devicePixelRatio`，避免 ECharts 取到旧值
- **DPR 变化必须重建实例**。桌面端真实场景：MacBook 内屏（2x）↔ 外接显示器（1x）拖动窗口。ECharts 不会自动响应 DPR 变化，表现为整体模糊。

  ```ts
  // 监听当前 DPR 的失效，而非监听一个固定值
  const mq = window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`);
  mq.addEventListener("change", onDprChange, { once: true });
  // onDprChange: dispose → 重新 init → 重新 setOption → 再次挂载监听
  ```

- **导出**：`getDataURL({ pixelRatio: 2 })`，屏幕检查用 2x，报告留档可提至 3x

---

## 5. 初始化与渲染逻辑

### 5.1 分层架构

```
┌─────────────────────────────────────────────────┐
│ L5 交互层   dataZoom / axisPointer / tooltip     │
│            区间统计 / 画线 / 键盘                 │
├─────────────────────────────────────────────────┤
│ L4 主题层   读 CSS 变量 → 生成 option 主题片段    │
│            --bg --srf --bd --rd --gn --gd ...    │
├─────────────────────────────────────────────────┤
│ L3 适配层   KlineData(分列) → series(行式)        │
│            按数据引用缓存，避免重复转置           │
├─────────────────────────────────────────────────┤
│ L2 编排层   grid 像素布局计算 / 面板显隐 / 断点   │
├─────────────────────────────────────────────────┤
│ L1 实例层   init / setOption / resize / dispose  │
│             单实例 + 生命周期守卫                 │
├─────────────────────────────────────────────────┤
│ L0 宿主层   DOM ref / ResizeObserver(rAF 节流)   │
│             DPR 监听 / 卸载清理                   │
└─────────────────────────────────────────────────┘
```

数据流单向：`StockAnalysis(数据) → MarketCanvas(props) → L3 转置 → L2 布局 → L4 主题 → L1 setOption`。画布**不持有业务状态**，指标类型、缩放区间等 UI 状态由 zustand 或组件内 `useState` 持有，画布只做投影。

### 5.2 生命周期

```
mount
  └─> ref 就绪 → echarts.init(dom, null, {renderer:'canvas', devicePixelRatio})
        └─> 首帧 setOption(baseOption, { notMerge: true })       // 全量
              └─> 挂载 ResizeObserver → rAF 合并 → chart.resize({silent:true})
              └─> 挂载 DPR matchMedia
              └─> 挂载 dataZoom / axisPointer 事件

props 变化
  └─> 数据变化   → setOption(patch, { notMerge:false, lazyUpdate:true })
  └─> 指标切换   → setOption(patch, { replaceMerge: ['series'] })   // 关键
  └─> 容器尺寸   → rAF 合并后 resize（尺寸未变则跳过）

unmount
  └─> cancelAnimationFrame → ro.disconnect() → mq.removeEventListener
  └─> chart.dispose()                                   // 必须，否则实例泄漏
```

**实例泄漏是本项目的高风险点**：`useApi` 每次切股请求 4 次，`StockAnalysis` 有 4 个 `useState`；若画布在数据到达前被卸载而 cleanup 未执行，会残留 canvas DOM 与事件监听。验收时用 `echarts.getInstanceByDom(el)` 计数验证（应为 1，卸载后为 undefined）。

### 5.3 setOption 策略（决定表现是否正确）

| 触发 | notMerge | replaceMerge | 原因 |
|------|----------|--------------|------|
| 首帧 | `true` | — | 清空历史，避免 StrictMode 双挂载残留 |
| 数据更新（同指标） | `false` | — | 保留缩放状态与 zoom 区间，增量重绘 |
| 指标类型切换 | `false` | `['series']` | 系列数量变化（MACD 3 / RSI 2 / KDJ 3），不 replace 会残留幽灵线 |
| 断点切换（面板增减） | `false` | `['series','grid','xAxis','yAxis']` | 坐标轴数量变化，必须整体替换 |

`lazyUpdate: true` 配合 rAF 批处理，避免同一帧内多次 setOption 造成重复布局计算。

---

## 6. 关键实现要点

### 6.1 单实例 vs 多实例（为什么必须合并）

| 维度 | 两个实例（现状） | 单实例多 grid（方案） |
|------|------------------|----------------------|
| 十字光标联动 | 需监听 `updateAxisPointer` 手动广播，易不同步 | `axisPointer.link: [{ xAxisIndex: 'all' }]` 一行配置 |
| 缩放联动 | 每个实例独立 dataZoom，需双向 sync，递归风险 | 一个 dataZoom 覆盖全部 grid |
| 日期轴对齐 | 各算各的，宽度不一致时错位 | 共享同一个 xAxis 数据源，天然对齐 |
| 重绘成本 | 2 次独立渲染循环 | 1 次统一渲染 |
| 状态保持 | 切指标时主图缩放区间会丢 | 只换 series，视图状态不动 |

### 6.2 高度契约（去掉硬编码）

```css
/* src/styles/global.css 追加 */
.market-canvas {
  flex: 1 1 auto;
  min-height: 360px;
  max-height: 720px;
  height: clamp(360px, calc(100dvh - 320px), 720px);
  background: var(--srf);
  border-radius: var(--radius);
  overflow: hidden;
}
```

组件侧：`<div className="market-canvas" ref={ref} />`，ECharts 容器用 `width:100%; height:100%` 撑满，**不再传 `style={{ height: 380 }}`**。

### 6.3 grid 布局计算

```ts
interface PanelLayout {
  top: number; height: number;
}

/** 按照可用高度与断点计算各面板像素位置，保证面板间距恒为 gap */
export function computeGrids(totalHeight: number, showVolume: boolean, showIndicator: boolean) {
  const PAD_TOP = 12;
  const PAD_BOTTOM = 56;   // dataZoom slider + x 轴标签
  const GAP = 12;
  const usable = Math.max(totalHeight - PAD_TOP - PAD_BOTTOM, 240);

  const ratios = showIndicator
    ? (showVolume ? [0.58, 0.14, 0.28] : [0.68, 0.32])
    : [1];
  // …按 ratios 依次累加 top，得到 {top, height}[] 返回
}
```

比例只在「面板数量」确定后使用，面板数量由断点决定 —— 两者解耦，避免 3 个分支里各写一套魔数。

### 6.4 数据转置与缓存

`KlineData` 是分列数组，ECharts candlestick 需要行式 `[open, close, low, high]`。转置一次后按 `data` 对象引用缓存：

```ts
const seriesCache = useRef<{ src: KlineData | null; ohlc: number[][]; vol: number[][] }>({
  src: null, ohlc: [], vol: [],
});
if (seriesCache.current.src !== data) {
  seriesCache.current = { src: data, ohlc: transpose(data), vol: buildVol(data) };
}
```

放在 `useMemo` 亦可，但用 ref 更能表达"跟着数据引用走"的意图，且不会因为父组件重渲染而失效。

### 6.5 主题单源

`global.css` 已是色值唯一真源。适配层读一次变量表，生成 option 片段：

```ts
const theme = {
  up: cssVar("--rd", "#ef4444"),      // 注意：A 股涨=红，跌=绿，不可套用欧美约定
  down: cssVar("--gn", "#22c55e"),
  bg: cssVar("--srf", "#0d1422"),
  border: cssVar("--bd", "#1a2740"),
  axis: cssVar("--dm", "#5a6e8a"),
};
```

读取时机：`getComputedStyle(document.documentElement).getPropertyValue(name)`。在挂载后读一次即可，主题切换（如需）通过重建 option 处理。

**颜色语义必须显式注释**：本项目面向 A 股，`up→红` 与 ECharts 默认、与欧美惯例相反，后来者极易"顺手修正"成错误方向。当前 `KlineChart.tsx:76-79` 是对的，迁移时要原样保留。

### 6.6 resize 节流

```ts
const raf = useRef<number | null>(null);
const lastSize = useRef<{ w: number; h: number }>({ w: 0, h: 0 });

const ro = new ResizeObserver((entries) => {
  const { width, height } = entries[0].contentRect;
  if (Math.round(width) === lastSize.current.w && Math.round(height) === lastSize.current.h) return;
  if (raf.current) cancelAnimationFrame(raf.current);
  raf.current = requestAnimationFrame(() => {
    lastSize.current = { w: Math.round(width), h: Math.round(height) };
    chartRef.current?.resize({ width, height, silent: true });
  });
});
```

两道防护：尺寸未变直接跳过（避免 `getComputedStyle` 抖动引发的空 resize）+ rAF 合并（拖拽窗口时一帧一次）。

### 6.7 竞态与空数据处理

- 沿用项目现有模式：`StockAnalysis.tsx` 的 `AbortController` + `codeRef` 校验，画布**不重复实现**数据层守卫
- `data.dates.length === 0` 时渲染空态占位（不 init ECharts），避免 ECharts 在 0 长度下抛 axis 计算异常
- `ma60` 为 `(number | null)[]`，ECharts 对 `null` 默认断线 —— 需显式 `connectNulls: false`，保持"数据不足即不画"的语义

### 6.8 不引入 Web Worker / OffscreenCanvas 的判断

当前单次 `setOption` 规模约 8 series × 120 点，实测在 16ms 帧预算内。引入 Worker 需处理 canvas 转移控制权，与 ECharts 实例模型冲突，且 Tauri WebView 的 `OffscreenCanvas` 支持视平台而异。**只有当窗口化数据（如 2500 根日线 + 5 年分时）进入时再评估**，届时优先方案是 ECharts 的 `dataZoom.filterMode: 'weakFilter'` + `sampling: 'lttb'` 降采样，而非换渲染后端。

---

## 7. 与现有结构的一致性约束

| 约束 | 具体要求 |
|------|----------|
| 目录约定 | 新增 `src/components/market-canvas/` 目录：`MarketCanvas.tsx`（宿主）、`gridLayout.ts`（L2 计算）、`seriesAdapter.ts`（L3 转置）、`theme.ts`（L4）、`types.ts`。纯函数单独成文件，便于单测 |
| 不破坏现有数据层 | `StockAnalysis.tsx` 的 4 个 `useApi` 调用、`AbortController`、`codeRef` 竞态守卫**原样保留**，只替换渲染部分 |
| 组件替换顺序 | 先并存（新旧均可达），Wave 1 验收通过后，经确认再删除 `KlineChart.tsx` / `IndicatorChart.tsx`。不先删 |
| 样式复用 | 工具栏按钮用现有 `.card` `.card-header` `.segmented-btn` `.flex` `.fs-*` `.c-*` 工具类，不新增平行体系 |
| ESLint | `no-console` 仅允许 `warn` / `error`；`@typescript-eslint/no-explicit-any` 为 warn，方案内代码**不使用 `any`**，用泛型或 `unknown` + 收窄 |
| 构建边界 | ECharts 必须保持懒加载（`vite.config.ts` 注释已明确：不要把 echarts 写进 `manualChunks`，会让 1.14MB 回到首屏）。MarketCanvas 只能被 `StockAnalysis` 动态 import 链引用 |
| 严格模式 | `main.tsx` 使用 `<React.StrictMode>`，effect 会双执行 → init/dispose 必须成对且幂等，首帧用 `notMerge: true` 兜底 |

### 7.1 必须先处理的测试耦合

`src/components/KlineChart.test.tsx:26-29` 断言 `chartDiv.style.height === "380px"`。高度改为容器契约后此断言必然失败。处理方式：

- Wave 1 同步改造该测试（若组件并存，测试保留在旧组件上，新组件另写测试）
- 新测试不再断言像素高度，改为断言**结构契约**：容器存在、`getInstanceByDom` 唯一、卸载后实例为 undefined

现有 4 个测试（`KlineChart.test.tsx` 的 4 个 it）保持绿；新增至少 6 个：

| 测试 | 类型 | 断言 |
|------|------|------|
| gridLayout 计算 | 纯函数 | 给定总高与面板数，各 grid 的 top/height 之和 + gap 恰等于可用高度（无重叠、无溢出） |
| seriesAdapter 转置 | 纯函数 | 分列 → 行式后顺序为 `[open, close, low, high]`（ECharts candlestick 顺序），`null` 透传 |
| 指标切换无残留 | 组件 | MACD→RSI 后 series 数量等于当前指标系列数 |
| 实例唯一性 | 组件 | 双 mount 后 `getInstanceByDom` 恒为 1 |
| 卸载清理 | 组件 | unmount 后实例 undefined、ResizeObserver 已 disconnect |
| 空数据降级 | 组件 | `dates: []` 渲染占位且不抛错 |

---

## 8. 实施计划

| 批次 | 范围 | 产出 | 验收 |
|------|------|------|------|
| Wave 1 | L0+L1+L2+L3+L4 + 单实例化 + 响应式高度 + dataZoom + tooltip | `market-canvas/` 5 个文件 + `StockAnalysis` 渲染替换 | 见 8.1 |
| Wave 2 | 区间统计 / 键盘 / MA 开关 / 双击复位 | 交互增强 | 交互回归 |
| Wave 3 | 画线工具 / PNG 导出 | 按需 | — |

### 8.1 Wave 1 验收标准（可证伪）

1. 窗口从 900×600 拖到 1600×1000，画布高度跟随，三面板间距恒为 12px，**无滚动条、无重叠、无裁切**（截图逐档比对 900/1100/1280/1600）
2. 滚轮缩放主图，成交量与副图的日期范围**同步变化**（截图对比缩放前后三面板 x 轴端点）
3. MACD → RSI → KDJ 连续切换 5 轮，series 数量逐次正确，无残留曲线（读 `chart.getOption().series.length`）
4. 切股 10 次后 `echarts.getInstanceByDom(container)` 返回单实例；离开页面后返回 `undefined`
5. 外接屏 1x ↔ 内屏 2x 切换后视图不模糊（截图对比）
6. 默认加载聚焦最近 60 根，非全量 120 根
7. 涨红跌绿（A 股约定）在 K 线与成交量柱上一致
8. `npm run test` 全绿（原 4 个 + 新增 ≥6 个）、`npm run lint` 无新增 warning、`npm run build` 首屏体积不回升

---

## 9. 未决问题（需确认）

| # | 问题 | 建议 |
|---|------|------|
| 1 | 默认视窗取最近 60 根是否合适？后端固定返回 120 日 | 建议 60 根（短线场景），可在设置页暴露为偏好 |
| 2 | 切换指标时是否保留用户已缩放的区间？ | 建议保留（`replaceMerge: ['series']` 天然保留），符合"看同一段时间对比不同动能"的直觉 |
| 3 | Wave 1 完成后是否删除旧的两个图表组件？ | 建议保留一个版本周期再删，删除前需明确确认 |
