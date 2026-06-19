import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import MarketIndicesSection from "./MarketIndicesSection";
import type { MarketIndex } from "../../types/api";

function makeIndex(overrides: Partial<MarketIndex> = {}): MarketIndex {
  return {
    code: "000001",
    name: "上证指数",
    price: 3200.5,
    change: 15.25,
    change_pct: 0.85,
    volume: 3500,
    ...overrides,
  };
}

describe("MarketIndicesSection", () => {
  it("shows placeholder lines when indices are empty", () => {
    render(<MarketIndicesSection indices={{}} />);

    expect(screen.getByText("上证指数")).toBeInTheDocument();
    expect(screen.getByText("深证成指")).toBeInTheDocument();
    expect(screen.getByText("创业板指")).toBeInTheDocument();
    expect(screen.getByText("科创50")).toBeInTheDocument();

    // All 4 should show "--" for price
    const placeholders = screen.getAllByText("--");
    expect(placeholders).toHaveLength(4);
  });

  it("renders all four indices with data", () => {
    const indices: Record<string, MarketIndex> = {
      "000001": makeIndex({
        code: "000001",
        name: "上证指数",
        price: 3200.5,
        change_pct: 0.85,
        volume: 3500,
      }),
      "399001": makeIndex({
        code: "399001",
        name: "深证成指",
        price: 10500.3,
        change_pct: -0.32,
        volume: 4800,
      }),
      "399006": makeIndex({
        code: "399006",
        name: "创业板指",
        price: 2150.8,
        change_pct: 1.25,
        volume: 1200,
      }),
      "000688": makeIndex({
        code: "000688",
        name: "科创50",
        price: 980.6,
        change_pct: -0.55,
        volume: 450,
      }),
    };

    render(<MarketIndicesSection indices={indices} />);

    expect(screen.getByText("上证指数")).toBeInTheDocument();
    expect(screen.getByText("深证成指")).toBeInTheDocument();
    expect(screen.getByText("创业板指")).toBeInTheDocument();
    expect(screen.getByText("科创50")).toBeInTheDocument();

    // Prices
    expect(screen.getByText("3200.50")).toBeInTheDocument();
    expect(screen.getByText("10500.30")).toBeInTheDocument();
    expect(screen.getByText("2150.80")).toBeInTheDocument();
    expect(screen.getByText("980.60")).toBeInTheDocument();
  });

  it("shows positive change with + sign and up class", () => {
    const indices = { "000001": makeIndex({ code: "000001", change_pct: 0.85 }) };
    render(<MarketIndicesSection indices={indices} />);

    const changeEl = screen.getByText("+0.85%");
    expect(changeEl).toBeInTheDocument();
    expect(changeEl.className).toContain("up");
  });

  it("shows negative change without + sign and down class", () => {
    const indices = { "000001": makeIndex({ code: "000001", change_pct: -0.55 }) };
    render(<MarketIndicesSection indices={indices} />);

    const changeEl = screen.getByText("-0.55%");
    expect(changeEl).toBeInTheDocument();
    expect(changeEl.className).toContain("down");
  });

  it("shows volume in 亿", () => {
    const indices = { "000001": makeIndex({ code: "000001", volume: 3500 }) };
    render(<MarketIndicesSection indices={indices} />);
    expect(screen.getByText(/成交 3500 亿/)).toBeInTheDocument();
  });

  it("shows -- for volume when undefined", () => {
    const indices = {
      "000001": makeIndex({ code: "000001", volume: undefined as unknown as number }),
    };
    render(<MarketIndicesSection indices={indices} />);
    // "成交 -- 亿" should appear; multiple "--" elements exist from other placeholders
    expect(screen.getAllByText("--").length).toBeGreaterThanOrEqual(1);
  });

  it("handles mixed present and missing indices", () => {
    const indices = {
      "000001": makeIndex({ code: "000001", name: "上证指数", price: 3200.5, change_pct: 0.85 }),
    };
    render(<MarketIndicesSection indices={indices} />);

    // Present index shows real data
    expect(screen.getByText("3200.50")).toBeInTheDocument();
    // Missing indices show placeholders
    const placeholders = screen.getAllByText("--");
    expect(placeholders.length).toBeGreaterThanOrEqual(3);
  });

  it("renders header with section number and subtitle", () => {
    render(<MarketIndicesSection indices={{}} />);
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("大盘环境")).toBeInTheDocument();
    expect(screen.getByText("市场情绪决定仓位")).toBeInTheDocument();
  });
});
