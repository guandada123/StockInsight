import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import PatternSection from "./PatternSection";
import type { PatternAnalysis, PatternItem } from "../../types/api";

function makePI(overrides: Partial<PatternItem> = {}): PatternItem {
  return {
    name: "头肩底",
    date: "2026-06-15",
    type: "bullish",
    description: "底部形成头肩底形态，右肩放量突破颈线",
    reliability: "高",
    ...overrides,
  };
}

function makePA(overrides: Partial<PatternAnalysis> = {}): PatternAnalysis {
  return {
    recent_patterns: [
      makePI({ date: "2026-06-15" }),
      makePI({ name: "上升三法", date: "2026-06-14", type: "bullish", description: "三法形态，中继看涨", reliability: "中" }),
      makePI({ name: "黄昏之星", date: "2026-06-13", type: "bearish", description: "高位出现黄昏之星", reliability: "低" }),
    ],
    summary: "近期看涨形态占优，中期看多",
    trend_phase: "上升趋势",
    key_observation: "需关注成交量能否持续配合",
    ...overrides,
  };
}

describe("PatternSection", () => {
  // ── 基础渲染 ──

  it("renders trend phase", () => {
    render(<PatternSection pa={makePA()} />);
    expect(screen.getByText("上升趋势")).toBeInTheDocument();
    expect(screen.getByText(/趋势阶段/)).toBeInTheDocument();
  });

  it("renders summary", () => {
    render(<PatternSection pa={makePA()} />);
    expect(screen.getByText("近期看涨形态占优，中期看多")).toBeInTheDocument();
  });

  // ── K线形态列表 ──

  it("renders pattern names", () => {
    render(<PatternSection pa={makePA()} />);
    expect(screen.getByText("头肩底")).toBeInTheDocument();
    expect(screen.getByText("上升三法")).toBeInTheDocument();
    expect(screen.getByText("黄昏之星")).toBeInTheDocument();
  });

  it("renders pattern dates", () => {
    render(<PatternSection pa={makePA()} />);
    expect(screen.getByText("2026-06-15")).toBeInTheDocument();
  });

  it("renders pattern descriptions", () => {
    render(<PatternSection pa={makePA()} />);
    expect(screen.getByText(/底部形成头肩底形态/)).toBeInTheDocument();
    expect(screen.getByText(/高位出现黄昏之星/)).toBeInTheDocument();
  });

  it("renders reliability values", () => {
    render(<PatternSection pa={makePA()} />);
    expect(screen.getByText("可靠性: 高")).toBeInTheDocument();
    expect(screen.getByText("可靠性: 中")).toBeInTheDocument();
    expect(screen.getByText("可靠性: 低")).toBeInTheDocument();
  });

  // ── 形态图标 ──

  it("renders ▲ icon for bullish patterns", () => {
    const { container } = render(<PatternSection pa={makePA()} />);
    const icons = container.querySelectorAll(".pattern-icon");
    // First two patterns are bullish → ▲
    expect(icons[0].textContent).toContain("▲");
    expect(icons[1].textContent).toContain("▲");
  });

  it("renders ▼ icon for bearish patterns", () => {
    const { container } = render(<PatternSection pa={makePA()} />);
    const icons = container.querySelectorAll(".pattern-icon");
    // Third pattern is bearish → ▼
    expect(icons[2].textContent).toContain("▼");
  });

  it("renders — icon for neutral patterns", () => {
    const pa = makePA();
    pa.recent_patterns = [makePI({ type: "neutral", name: "十字星" })];
    const { container } = render(<PatternSection pa={pa} />);
    const icon = container.querySelector(".pattern-icon");
    expect(icon?.textContent).toContain("—");
  });

  // ── 形态样式 ──

  it("applies type class to pattern items", () => {
    const { container } = render(<PatternSection pa={makePA()} />);
    const items = container.querySelectorAll(".pattern-item");
    expect(items[0].className).toContain("bullish");
    expect(items[1].className).toContain("bullish");
    expect(items[2].className).toContain("bearish");
  });

  // ── 空状态 ──

  it("shows empty state message when no patterns", () => {
    const pa = makePA({ recent_patterns: [] });
    render(<PatternSection pa={pa} />);
    expect(screen.getByText("近期没有检测到明显K线形态")).toBeInTheDocument();
  });

  it("shows empty state message when patterns is undefined", () => {
    const pa = makePA({ recent_patterns: undefined as unknown as PatternItem[] });
    render(<PatternSection pa={pa} />);
    expect(screen.getByText("近期没有检测到明显K线形态")).toBeInTheDocument();
  });

  // ── 关键观察 ──

  it("renders key observation", () => {
    render(<PatternSection pa={makePA()} />);
    expect(screen.getByText("需关注成交量能否持续配合")).toBeInTheDocument();
  });

  it("does not render key observation when empty", () => {
    const pa = makePA({ key_observation: "" });
    render(<PatternSection pa={pa} />);
    expect(screen.queryByText("需关注成交量")).not.toBeInTheDocument();
  });

  it("does not render key observation when undefined", () => {
    const pa = makePA({ key_observation: undefined as unknown as string });
    render(<PatternSection pa={pa} />);
    expect(screen.queryByText("需关注成交量")).not.toBeInTheDocument();
  });

  // ── 容错 ──

  it("handles single pattern", () => {
    const pa = makePA({ recent_patterns: [makePI({ name: "单根长阳" })] });
    render(<PatternSection pa={pa} />);
    expect(screen.getByText("单根长阳")).toBeInTheDocument();
  });

  it("renders pattern-item with correct structure", () => {
    const { container } = render(<PatternSection pa={makePA()} />);
    // Each pattern item has: icon, body (name+date, desc, meta)
    const items = container.querySelectorAll(".pattern-item");
    expect(items.length).toBe(3);

    const firstItem = items[0];
    expect(firstItem.querySelector(".pattern-icon")).toBeInTheDocument();
    expect(firstItem.querySelector(".pattern-body")).toBeInTheDocument();
    expect(firstItem.querySelector(".pattern-name")).toBeInTheDocument();
    expect(firstItem.querySelector(".pattern-desc")).toBeInTheDocument();
    expect(firstItem.querySelector(".pattern-meta")).toBeInTheDocument();
  });

  it("renders verdict-box with summary", () => {
    const { container } = render(<PatternSection pa={makePA()} />);
    expect(container.querySelector(".verdict-box")).toBeInTheDocument();
    expect(container.querySelector(".va-reason")).toBeInTheDocument();
  });
});
