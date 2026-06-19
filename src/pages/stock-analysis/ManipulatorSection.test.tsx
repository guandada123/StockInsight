import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import ManipulatorSection from "./ManipulatorSection";
import type { ManipulatorIntention } from "../../types/api";

function makeMI(overrides: Partial<ManipulatorIntention> = {}): ManipulatorIntention {
  return {
    phase: "建仓",
    phase_confidence: 75,
    signals: ["底部放量异动", "大单持续流入", "筹码集中度提升"],
    volume_analysis: "近期成交量明显放大，有资金建仓迹象",
    chip_analysis: "低位筹码集中，上方套牢盘较少",
    assessment: "综合判断当前处于主力建仓阶段，可逢低布局",
    risk_note: "需关注大盘系统性风险",
    ...overrides,
  };
}

describe("ManipulatorSection", () => {
  // ── 阶段渲染 ──

  it("renders phase label", () => {
    render(<ManipulatorSection mi={makeMI()} />);
    expect(screen.getByText("建仓")).toBeInTheDocument();
  });

  it("renders phase confidence", () => {
    render(<ManipulatorSection mi={makeMI()} />);
    expect(screen.getByText("判断置信度: 75%")).toBeInTheDocument();
  });

  it("uses accumulation class for 建仓", () => {
    const { container } = render(<ManipulatorSection mi={makeMI()} />);
    const label = container.querySelector(".phase-label");
    expect(label?.className).toContain("accumulation");
  });

  it("uses washout class for 洗盘", () => {
    const { container } = render(<ManipulatorSection mi={makeMI({ phase: "洗盘" })} />);
    const label = container.querySelector(".phase-label");
    expect(label?.className).toContain("washout");
  });

  it("uses uptrend class for 拉升", () => {
    const { container } = render(<ManipulatorSection mi={makeMI({ phase: "拉升" })} />);
    const label = container.querySelector(".phase-label");
    expect(label?.className).toContain("uptrend");
  });

  it("uses distribution class for 出货", () => {
    const { container } = render(<ManipulatorSection mi={makeMI({ phase: "出货" })} />);
    const label = container.querySelector(".phase-label");
    expect(label?.className).toContain("distribution");
  });

  it("uses unknown class for unexpected phase", () => {
    const { container } = render(<ManipulatorSection mi={makeMI({ phase: "震荡" })} />);
    const label = container.querySelector(".phase-label");
    expect(label?.className).toContain("unknown");
  });

  // ── 信号列表 ──

  it("renders signal items", () => {
    render(<ManipulatorSection mi={makeMI()} />);
    expect(screen.getByText("底部放量异动", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("大单持续流入", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("筹码集中度提升", { exact: false })).toBeInTheDocument();
  });

  it("does not render signals when signals array is empty", () => {
    const { container } = render(<ManipulatorSection mi={makeMI({ signals: [] })} />);
    expect(container.querySelector(".phase-signals")).not.toBeInTheDocument();
  });

  it("does not render signals when signals is undefined", () => {
    const { container } = render(
      <ManipulatorSection mi={makeMI({ signals: undefined as unknown as string[] })} />
    );
    expect(container.querySelector(".phase-signals")).not.toBeInTheDocument();
  });

  // ── 量价/筹码分析 ──

  it("renders volume analysis", () => {
    render(<ManipulatorSection mi={makeMI()} />);
    expect(screen.getByText("近期成交量明显放大，有资金建仓迹象")).toBeInTheDocument();
  });

  it("does not render volume analysis when empty", () => {
    render(<ManipulatorSection mi={makeMI({ volume_analysis: "" })} />);
    expect(screen.queryByText("近期成交量明显放大")).not.toBeInTheDocument();
  });

  it("renders chip analysis", () => {
    render(<ManipulatorSection mi={makeMI()} />);
    expect(screen.getByText("低位筹码集中，上方套牢盘较少")).toBeInTheDocument();
  });

  it("does not render chip analysis when empty", () => {
    render(<ManipulatorSection mi={makeMI({ chip_analysis: "" })} />);
    expect(screen.queryByText("低位筹码集中")).not.toBeInTheDocument();
  });

  // ── 评估 ──

  it("renders assessment", () => {
    render(<ManipulatorSection mi={makeMI()} />);
    expect(screen.getByText("综合判断当前处于主力建仓阶段，可逢低布局")).toBeInTheDocument();
  });

  // ── 风险提示 ──

  it("renders risk note", () => {
    render(<ManipulatorSection mi={makeMI()} />);
    expect(screen.getByText("需关注大盘系统性风险", { exact: false })).toBeInTheDocument();
  });

  it("does not render risk note when empty", () => {
    const { container } = render(<ManipulatorSection mi={makeMI({ risk_note: "" })} />);
    expect(container.querySelector(".c-gd")).not.toBeInTheDocument();
  });

  it("does not render risk note when undefined", () => {
    const { container } = render(
      <ManipulatorSection mi={makeMI({ risk_note: undefined as unknown as string })} />
    );
    expect(container.querySelector(".c-gd")).not.toBeInTheDocument();
  });
});
