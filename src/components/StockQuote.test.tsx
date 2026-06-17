import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import StockQuote from "./StockQuote";
import type { StockAnalysisResult } from "../types/api";

function makeResult(changePct: number, industry?: string): StockAnalysisResult {
  return {
    code: "600519",
    name: "贵州茅台",
    time: "2026-06-17 15:00",
    quote: {
      code: "600519",
      name: "贵州茅台",
      price: 1500 + changePct,
      open: 1498,
      high: 1510,
      low: 1490,
      prev_close: 1500,
      change: changePct,
      change_pct: changePct,
      amplitude: 1.5,
    },
    technical: {
      ma_status: "多头排列",
      macd_signal: "金叉",
      kdj_signal: "金叉",
      rsi_value: 55,
      atr: 12,
      support: [1480],
      resistance: [1520],
      stop_loss: 1480,
      stop_profit: 1520,
    },
    quant: {
      composite: 70,
      rating: "推荐",
      factor_scores: { momentum: 60, technical: 70, fundamental: 80, volume: 65, risk: 75 },
    },
    risk: { sharpe_ratio: 1.2, max_drawdown_pct: 15, annual_volatility_pct: 25, var_95_pct: 3.5 },
    financial: { roe: 15, pe: 25, pb: 5 },
    fund_flow: { direction: "流入", total_5d: 50000000, chip_score: 65, national_team: "持有" },
    signal: { bias: "偏多", score: 2, combo_strength: 1 },
    near_5d: 2.5,
    near_20d: 5.0,
    short_score: 60,
    long_score: 70,
    style: "价值成长",
    sector_analysis: industry
      ? {
          industry,
          concepts: ["白酒", "消费"],
          sector_name: "食品饮料",
          sector_rank: 5,
          sector_total: 100,
          sector_change_pct: 1.2,
          sector_fund_flow_yi: 3.5,
          rank_label: "领先",
          rank_color: "green",
          assessment: "行业领先",
        }
      : undefined,
  };
}

describe("StockQuote", () => {
  it("渲染股票名称和代码", () => {
    const result = makeResult(1.5);
    render(<StockQuote result={result} code="600519" />);
    expect(screen.getByText(/贵州茅台/)).toBeInTheDocument();
  });

  it("上涨时价格显示红色（A股惯例）", () => {
    const result = makeResult(1.5);
    render(<StockQuote result={result} code="600519" />);
    const priceEl = screen.getByText("1501.50");
    expect(priceEl).toBeInTheDocument();
    expect(priceEl.getAttribute("style")).toContain("rgb(239, 68, 68)");
  });

  it("下跌时价格显示绿色（A股惯例）", () => {
    const result = makeResult(-1.5);
    render(<StockQuote result={result} code="600519" />);
    const priceEl = screen.getByText("1498.50");
    expect(priceEl.getAttribute("style")).toContain("rgb(34, 197, 94)");
  });

  it("有行业信息时显示行业", () => {
    const result = makeResult(0, "白酒");
    render(<StockQuote result={result} code="600519" />);
    expect(screen.getByText(/白酒/)).toBeInTheDocument();
  });

  it("无行业信息时回退到 ma_status", () => {
    const result = makeResult(0);
    render(<StockQuote result={result} code="600519" />);
    // 没有 industry 时 card-header 应显示 ma_status
    expect(screen.getByText(/多头排列/)).toBeInTheDocument();
  });
});
