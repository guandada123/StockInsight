import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import PredictionSection from "./PredictionSection";
import type { PredictionData } from "../../types/api";

function makePred(overrides: Partial<PredictionData> = {}): PredictionData {
  return {
    direction: "震荡上涨",
    confidence: 72,
    price_range: { low: 1480, high: 1580 },
    key_level: 1500,
    rationale: "均线多头排列，主力资金持续流入，预计震荡向上",
    ...overrides,
  };
}

describe("PredictionSection", () => {
  // ── 基础渲染 ──

  it("renders direction text", () => {
    render(<PredictionSection pred={makePred()} />);
    expect(screen.getByText("震荡上涨")).toBeInTheDocument();
  });

  it("renders confidence percentage", () => {
    render(<PredictionSection pred={makePred()} />);
    expect(screen.getByText("置信度 72%")).toBeInTheDocument();
  });

  it("renders price range", () => {
    render(<PredictionSection pred={makePred()} />);
    expect(screen.getByText(/1480/)).toBeInTheDocument();
    expect(screen.getByText(/1580/)).toBeInTheDocument();
    expect(screen.getByText(/预测区间/)).toBeInTheDocument();
  });

  it("renders rationale", () => {
    render(<PredictionSection pred={makePred()} />);
    expect(screen.getByText("均线多头排列，主力资金持续流入，预计震荡向上")).toBeInTheDocument();
  });

  // ── 方向样式 ──

  it("uses up class when direction includes 涨", () => {
    const { container } = render(<PredictionSection pred={makePred()} />);
    const dir = container.querySelector(".pred-direction");
    expect(dir?.className).toContain("up");
  });

  it("uses down class when direction includes 跌", () => {
    const { container } = render(<PredictionSection pred={makePred({ direction: "持续下跌" })} />);
    const dir = container.querySelector(".pred-direction");
    expect(dir?.className).toContain("down");
  });

  it("uses sideways class when direction is neutral", () => {
    const { container } = render(<PredictionSection pred={makePred({ direction: "横盘震荡" })} />);
    const dir = container.querySelector(".pred-direction");
    expect(dir?.className).toContain("sideways");
  });

  it("uses sideways class for empty direction", () => {
    const { container } = render(<PredictionSection pred={makePred({ direction: "" })} />);
    const dir = container.querySelector(".pred-direction");
    expect(dir?.className).toContain("sideways");
  });

  // ── 条件渲染 ──

  it("does not render price range when price_range is undefined", () => {
    const pred = makePred();
    (pred as any).price_range = undefined;
    render(<PredictionSection pred={pred} />);
    expect(screen.queryByText(/预测区间/)).not.toBeInTheDocument();
  });

  it("does not render rationale when empty", () => {
    const pred = makePred({ rationale: "" });
    render(<PredictionSection pred={pred} />);
    expect(screen.queryByText("均线多头排列")).not.toBeInTheDocument();
  });

  it("does not render rationale when undefined", () => {
    const pred = makePred({ rationale: undefined as unknown as string });
    render(<PredictionSection pred={pred} />);
    expect(screen.queryByText("均线多头排列")).not.toBeInTheDocument();
  });

  // ── 边界值 ──

  it("renders 0% confidence", () => {
    render(<PredictionSection pred={makePred({ confidence: 0 })} />);
    expect(screen.getByText("置信度 0%")).toBeInTheDocument();
  });

  it("renders 100% confidence", () => {
    render(<PredictionSection pred={makePred({ confidence: 100 })} />);
    expect(screen.getByText("置信度 100%")).toBeInTheDocument();
  });

  // ── 布局结构 ──

  it("renders prediction-card container", () => {
    const { container } = render(<PredictionSection pred={makePred()} />);
    expect(container.querySelector(".prediction-card")).toBeInTheDocument();
  });

  it("renders pred-direction, pred-range, and pred-reason", () => {
    const { container } = render(<PredictionSection pred={makePred()} />);
    expect(container.querySelector(".pred-direction")).toBeInTheDocument();
    expect(container.querySelector(".pred-range")).toBeInTheDocument();
    expect(container.querySelector(".pred-reason")).toBeInTheDocument();
  });
});
