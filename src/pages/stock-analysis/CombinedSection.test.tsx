import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import CombinedSection from "./CombinedSection";
import type { CombinedSummary } from "../../types/api";

function makeCS(overrides: Partial<CombinedSummary> = {}): CombinedSummary {
  return {
    kline_summary: "K线呈现多头排列，量价配合良好",
    manipulator_summary: "主力资金持续流入，筹码集中度提升",
    synergy_assessment: "K线与资金面共振，做多信号明显",
    overall_conclusion: "综合判断：中期看多，可逢低布局",
    ...overrides,
  };
}

describe("CombinedSection", () => {
  // ── 基础渲染 ──

  it("renders kline summary", () => {
    render(<CombinedSection cs={makeCS()} />);
    expect(screen.getByText("K线语言")).toBeInTheDocument();
    expect(screen.getByText("K线呈现多头排列，量价配合良好")).toBeInTheDocument();
  });

  it("renders manipulator summary", () => {
    render(<CombinedSection cs={makeCS()} />);
    expect(screen.getByText("庄家语言")).toBeInTheDocument();
    expect(screen.getByText("主力资金持续流入，筹码集中度提升")).toBeInTheDocument();
  });

  it("renders synergy assessment", () => {
    render(<CombinedSection cs={makeCS()} />);
    expect(screen.getByText("联动判断")).toBeInTheDocument();
    expect(screen.getByText("K线与资金面共振，做多信号明显")).toBeInTheDocument();
  });

  it("renders overall conclusion", () => {
    render(<CombinedSection cs={makeCS()} />);
    expect(screen.getByText("综合判断：中期看多，可逢低布局")).toBeInTheDocument();
  });

  // ── 条件渲染 ──

  it("does not render kline_summary when empty", () => {
    const cs = makeCS({ kline_summary: "" });
    render(<CombinedSection cs={cs} />);
    expect(screen.queryByText("K线语言")).not.toBeInTheDocument();
  });

  it("does not render manipulator_summary when empty", () => {
    const cs = makeCS({ manipulator_summary: "" });
    render(<CombinedSection cs={cs} />);
    expect(screen.queryByText("庄家语言")).not.toBeInTheDocument();
  });

  it("does not render synergy_assessment when empty", () => {
    const cs = makeCS({ synergy_assessment: "" });
    render(<CombinedSection cs={cs} />);
    expect(screen.queryByText("联动判断")).not.toBeInTheDocument();
  });

  it("does not render overall_conclusion when empty", () => {
    const cs = makeCS({ overall_conclusion: "" });
    render(<CombinedSection cs={cs} />);
    expect(screen.queryByText("综合判断")).not.toBeInTheDocument();
  });

  it("does not render kline_summary when undefined", () => {
    const cs = makeCS({ kline_summary: undefined as unknown as string });
    render(<CombinedSection cs={cs} />);
    expect(screen.queryByText("K线语言")).not.toBeInTheDocument();
  });

  it("does not render manipulator_summary when undefined", () => {
    const cs = makeCS({ manipulator_summary: undefined as unknown as string });
    render(<CombinedSection cs={cs} />);
    expect(screen.queryByText("庄家语言")).not.toBeInTheDocument();
  });

  it("does not render synergy_assessment when undefined", () => {
    const cs = makeCS({ synergy_assessment: undefined as unknown as string });
    render(<CombinedSection cs={cs} />);
    expect(screen.queryByText("联动判断")).not.toBeInTheDocument();
  });

  it("does not render overall_conclusion when undefined", () => {
    const cs = makeCS({ overall_conclusion: undefined as unknown as string });
    render(<CombinedSection cs={cs} />);
    expect(screen.queryByText("综合判断")).not.toBeInTheDocument();
  });

  // ── 组合容错 ──

  it("renders nothing when all fields are empty", () => {
    const cs = makeCS({
      kline_summary: "",
      manipulator_summary: "",
      synergy_assessment: "",
      overall_conclusion: "",
    });
    const { container } = render(<CombinedSection cs={cs} />);
    expect(container.querySelectorAll(".combined-row").length).toBe(0);
    expect(container.querySelectorAll(".combined-conclusion").length).toBe(0);
  });

  it("renders partial rows when some fields are provided", () => {
    const cs = makeCS({
      kline_summary: "仅K线有数据",
      manipulator_summary: "",
      synergy_assessment: "",
      overall_conclusion: "",
    });
    render(<CombinedSection cs={cs} />);
    expect(screen.getByText("K线语言")).toBeInTheDocument();
    expect(screen.getByText("仅K线有数据")).toBeInTheDocument();
    expect(screen.queryByText("庄家语言")).not.toBeInTheDocument();
    expect(screen.queryByText("联动判断")).not.toBeInTheDocument();
    expect(screen.queryByText("综合判断")).not.toBeInTheDocument();
  });

  // ── 布局结构 ──

  it("renders combined-block container", () => {
    const { container } = render(<CombinedSection cs={makeCS()} />);
    expect(container.querySelector(".combined-block")).toBeInTheDocument();
  });

  it("renders all four combined-rows", () => {
    const { container } = render(<CombinedSection cs={makeCS()} />);
    const rows = container.querySelectorAll(".combined-row");
    expect(rows.length).toBe(3); // overall_conclusion has its own class
  });

  it("renders overall_conclusion in combined-conclusion", () => {
    const { container } = render(<CombinedSection cs={makeCS()} />);
    expect(container.querySelector(".combined-conclusion")).toBeInTheDocument();
  });

  it("renders all labels correctly", () => {
    render(<CombinedSection cs={makeCS()} />);
    expect(screen.getByText("K线语言")).toBeInTheDocument();
    expect(screen.getByText("庄家语言")).toBeInTheDocument();
    expect(screen.getByText("联动判断")).toBeInTheDocument();
  });
});
