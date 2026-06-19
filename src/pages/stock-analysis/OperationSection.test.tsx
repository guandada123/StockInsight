import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import OperationSection from "./OperationSection";
import type { OperationAdvice } from "../../types/api";

function makeOp(overrides: Partial<OperationAdvice> = {}): OperationAdvice {
  return {
    direction: "买入",
    direction_color: "up",
    confidence: "较高",
    entry_range: { low: 14.5, high: 15.8 },
    stop_loss: 13.2,
    take_profit: [17.0, 19.5],
    position_pct: 60,
    holding_days: "1~3个月",
    key_points: ["分批建仓", "跌破止损价坚决离场", "关注成交量配合"],
    ...overrides,
  };
}

describe("OperationSection", () => {
  // ── 基础渲染 ──

  it("renders direction with color class", () => {
    render(<OperationSection op={makeOp()} />);
    const el = screen.getByText("买入");
    expect(el).toBeInTheDocument();
    expect(el.className).toContain("up");
  });

  it("renders confidence tag", () => {
    render(<OperationSection op={makeOp()} />);
    expect(screen.getByText("置信度: 较高")).toBeInTheDocument();
  });

  // ── 表格内容 ──

  it("renders entry range", () => {
    render(<OperationSection op={makeOp()} />);
    expect(screen.getByText("买入区间")).toBeInTheDocument();
    expect(screen.getByText("14.5 ~ 15.8")).toBeInTheDocument();
  });

  it("renders stop loss", () => {
    render(<OperationSection op={makeOp()} />);
    expect(screen.getByText("止损价")).toBeInTheDocument();
    expect(screen.getByText("13.2")).toBeInTheDocument();
  });

  it("renders take profit targets", () => {
    render(<OperationSection op={makeOp()} />);
    expect(screen.getByText("止盈目标1")).toBeInTheDocument();
    expect(screen.getByText("17")).toBeInTheDocument();
    expect(screen.getByText("止盈目标2")).toBeInTheDocument();
    expect(screen.getByText("19.5")).toBeInTheDocument();
  });

  it("does not render take profit when array is empty", () => {
    render(<OperationSection op={makeOp({ take_profit: [] })} />);
    expect(screen.queryByText("止盈目标1")).not.toBeInTheDocument();
  });

  it("renders position percentage", () => {
    render(<OperationSection op={makeOp()} />);
    expect(screen.getByText("建议仓位")).toBeInTheDocument();
    expect(screen.getByText("60%")).toBeInTheDocument();
  });

  it("renders holding period", () => {
    render(<OperationSection op={makeOp()} />);
    expect(screen.getByText("持有周期")).toBeInTheDocument();
    expect(screen.getByText("1~3个月")).toBeInTheDocument();
  });

  // ── 关键要点 ──

  it("renders key points", () => {
    render(<OperationSection op={makeOp()} />);
    expect(screen.getByText("分批建仓", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("跌破止损价坚决离场", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("关注成交量配合", { exact: false })).toBeInTheDocument();
  });

  it("does not render key points when array is empty", () => {
    const { container } = render(<OperationSection op={makeOp({ key_points: [] })} />);
    expect(container.querySelector(".operation-points")).not.toBeInTheDocument();
  });

  // ── 仓位颜色边界 ──

  it("colors position green when >= 50", () => {
    render(<OperationSection op={makeOp({ position_pct: 50 })} />);
    const el = screen.getByText("50%");
    expect(el.getAttribute("style")).toContain("var(--gn)");
  });

  it("colors position yellow when < 50", () => {
    render(<OperationSection op={makeOp({ position_pct: 30 })} />);
    const el = screen.getByText("30%");
    expect(el.getAttribute("style")).toContain("var(--gd)");
  });

  // ── 边距情况 ──

  it("handles single take profit target", () => {
    render(<OperationSection op={makeOp({ take_profit: [18.0] })} />);
    expect(screen.getByText("止盈目标1")).toBeInTheDocument();
    expect(screen.getByText("18")).toBeInTheDocument();
    expect(screen.queryByText("止盈目标2")).not.toBeInTheDocument();
  });

  it("renders multiple take profit targets", () => {
    render(<OperationSection op={makeOp({ take_profit: [16.0, 18.5, 21.0] })} />);
    expect(screen.getByText("止盈目标1")).toBeInTheDocument();
    expect(screen.getByText("止盈目标2")).toBeInTheDocument();
    expect(screen.getByText("止盈目标3")).toBeInTheDocument();
    expect(screen.getByText("16")).toBeInTheDocument();
    expect(screen.getByText("18.5")).toBeInTheDocument();
    expect(screen.getByText("21")).toBeInTheDocument();
  });
});
