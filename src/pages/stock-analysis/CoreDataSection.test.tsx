import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import CoreDataSection from "./CoreDataSection";
import type { StockAnalysisResult } from "../../types/api";

function makeResult(overrides: Partial<StockAnalysisResult> = {}): StockAnalysisResult {
  return {
    code: "600519",
    name: "贵州茅台",
    time: "2026-06-18 10:00",
    quote: {
      code: "600519",
      name: "贵州茅台",
      price: 1500.0,
      open: 1498.0,
      high: 1510.0,
      low: 1495.0,
      prev_close: 1495.0,
      change: 5.0,
      change_pct: 0.33,
      amplitude: 1.0,
    },
    technical: {
      ma_status: "多头排列",
      macd_signal: "金叉",
      kdj_signal: "超买",
      rsi_value: 65,
      atr: 1.5,
      support: [1480, 1450],
      resistance: [1520, 1550],
      stop_loss: 1470,
      stop_profit: 1550,
    },
    quant: {
      composite: 75,
      rating: "A",
      factor_scores: { momentum: 80, technical: 70, fundamental: 85, volume: 65, risk: 75 },
    },
    financial: { roe: 18, pe: 25, pb: 5, eps: 60 },
    fund_flow: { direction: "流入", total_5d: 3.5, chip_score: 72, national_team: "有" },
    debate: {
      bull_points: [],
      bear_points: [],
      bull_score: 0,
      bear_score: 0,
      verdict: "中性",
      action: "持有",
    },
    ml: { direction: "看涨", confidence: 72, votes: "3/5模型一致", models: {} },
    signal: { bias: "bullish", score: 72, combo_strength: "中等偏强" },
    near_5d: 0.5,
    near_20d: 2.1,
    short_score: 65,
    long_score: 80,
    style: "价值成长",
    ...overrides,
  } as StockAnalysisResult;
}

describe("CoreDataSection", () => {
  it("renders stock name, code, and time", () => {
    render(<CoreDataSection result={makeResult()} code="600519" />);
    expect(screen.getByText("贵州茅台")).toBeInTheDocument();
    expect(screen.getByText("600519")).toBeInTheDocument();
    expect(screen.getByText(/2026-06-18/)).toBeInTheDocument();
  });

  it("renders current price", () => {
    render(<CoreDataSection result={makeResult()} />);
    expect(screen.getByText("1500.00")).toBeInTheDocument();
  });

  it("shows positive change with + sign and up class", () => {
    render(<CoreDataSection result={makeResult()} />);
    const chg = screen.getByText("+0.33%");
    expect(chg).toBeInTheDocument();
    expect(chg.className).toContain("up");
  });

  it("shows negative change with - sign and down class", () => {
    const r = makeResult();
    r.quote.change_pct = -1.5;
    render(<CoreDataSection result={r} />);
    const chg = screen.getByText("-1.50%");
    expect(chg).toBeInTheDocument();
    expect(chg.className).toContain("down");
  });

  it("renders quant rating and composite score", () => {
    render(<CoreDataSection result={makeResult()} />);
    expect(screen.getByText(/A 75分/)).toBeInTheDocument();
  });

  it("renders quote KPI row: 今开, 最高, 最低, 振幅", () => {
    render(<CoreDataSection result={makeResult()} />);
    expect(screen.getByText("1498.00")).toBeInTheDocument();
    expect(screen.getByText("1510.00")).toBeInTheDocument();
    expect(screen.getByText("1495.00")).toBeInTheDocument();
    expect(screen.getByText("1.0%")).toBeInTheDocument();
  });

  it("renders near_5d with + sign when positive", () => {
    render(<CoreDataSection result={makeResult()} />);
    expect(screen.getByText("+0.5%")).toBeInTheDocument();
  });

  it("renders near_5d with - sign when negative", () => {
    const r = makeResult({ near_5d: -1.2 });
    render(<CoreDataSection result={r} />);
    expect(screen.getByText("-1.2%")).toBeInTheDocument();
  });

  it("renders near_20d with + sign when positive", () => {
    render(<CoreDataSection result={makeResult()} />);
    expect(screen.getByText("+2.1%")).toBeInTheDocument();
  });

  it("renders near_20d with - sign when negative", () => {
    const r = makeResult({ near_20d: -3.5 });
    render(<CoreDataSection result={r} />);
    expect(screen.getByText("-3.5%")).toBeInTheDocument();
  });

  it("renders short_score and long_score", () => {
    render(<CoreDataSection result={makeResult()} />);
    // "65" appears as short_score and RSI value
    expect(screen.getAllByText("65").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("80").length).toBeGreaterThanOrEqual(1);
  });

  it("renders technical indicators: MACD, KDJ, RSI, 均线", () => {
    render(<CoreDataSection result={makeResult()} />);
    expect(screen.getByText("金叉")).toBeInTheDocument();
    expect(screen.getByText("超买")).toBeInTheDocument();
    // RSI value "65" also appears as short_score
    expect(screen.getAllByText("65").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("多头排列")).toBeInTheDocument();
  });

  it("renders financial PE and ROE", () => {
    render(<CoreDataSection result={makeResult()} />);
    expect(screen.getByText("25")).toBeInTheDocument(); // PE
    expect(screen.getByText("18%")).toBeInTheDocument(); // ROE
  });

  it("renders style label", () => {
    render(<CoreDataSection result={makeResult()} />);
    expect(screen.getByText("价值成长")).toBeInTheDocument();
  });

  it("renders section header with number and description", () => {
    render(<CoreDataSection result={makeResult()} />);
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("个股核心数据")).toBeInTheDocument();
  });
});
