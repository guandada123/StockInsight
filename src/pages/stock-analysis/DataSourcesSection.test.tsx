import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import DataSourcesSection from "./DataSourcesSection";
import type { DataSourceInfo } from "../../types/api";

function makeDS(overrides: Partial<DataSourceInfo> = {}): DataSourceInfo {
  return {
    quote_source: "腾讯财经 (实时)",
    kline_source: "东方财富 (日K)",
    sector_source: "同花顺 (行业)",
    fundamental_source: "Tushare (财报)",
    update_time: "2026-06-18 10:30:00",
    disclaimer: "以上数据仅供参考，不构成投资建议",
    ...overrides,
  };
}

describe("DataSourcesSection", () => {
  // ── 数据源渲染 ──

  it("renders quote source", () => {
    render(<DataSourcesSection ds={makeDS()} />);
    expect(screen.getByText("腾讯财经 (实时)")).toBeInTheDocument();
  });

  it("renders kline source", () => {
    render(<DataSourcesSection ds={makeDS()} />);
    expect(screen.getByText("东方财富 (日K)")).toBeInTheDocument();
  });

  it("renders sector source", () => {
    render(<DataSourcesSection ds={makeDS()} />);
    expect(screen.getByText("同花顺 (行业)")).toBeInTheDocument();
  });

  it("renders fundamental source", () => {
    render(<DataSourcesSection ds={makeDS()} />);
    expect(screen.getByText("Tushare (财报)")).toBeInTheDocument();
  });

  it("renders all four source items", () => {
    const { container } = render(<DataSourcesSection ds={makeDS()} />);
    const items = container.querySelectorAll(".source-item");
    expect(items.length).toBe(4);
  });

  // ── 数据源点样式 ──

  it("renders source-dot ok class for each source", () => {
    const { container } = render(<DataSourcesSection ds={makeDS()} />);
    const dots = container.querySelectorAll(".source-dot.ok");
    expect(dots.length).toBe(4);
  });

  // ── 更新时间 ──

  it("renders update time", () => {
    render(<DataSourcesSection ds={makeDS()} />);
    expect(screen.getByText("2026-06-18 10:30:00", { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/数据更新/)).toBeInTheDocument();
  });

  // ── 免责声明 ──

  it("renders disclaimer text", () => {
    render(<DataSourcesSection ds={makeDS()} />);
    expect(screen.getByText("以上数据仅供参考，不构成投资建议")).toBeInTheDocument();
  });

  // ── 布局结构 ──

  it("renders correct component structure", () => {
    const { container } = render(<DataSourcesSection ds={makeDS()} />);
    expect(container.querySelector(".source-grid")).toBeInTheDocument();
    expect(container.querySelector(".disclaimer-text")).toBeInTheDocument();
  });

  it("renders source items in correct order", () => {
    const { container } = render(<DataSourcesSection ds={makeDS()} />);
    const items = container.querySelectorAll(".source-item");
    expect(items[0].textContent).toContain("腾讯财经");
    expect(items[1].textContent).toContain("东方财富");
    expect(items[2].textContent).toContain("同花顺");
    expect(items[3].textContent).toContain("Tushare");
  });
});
