import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import RiskSection from "./RiskSection";
import type { RiskWarning } from "../../types/api";

function makeRisk(overrides: Partial<RiskWarning> = {}): RiskWarning {
  return {
    level: "high",
    message: "股价处于历史高位，注意回调风险",
    ...overrides,
  };
}

describe("RiskSection", () => {
  // ── 基础渲染 ──

  it("renders risk message", () => {
    render(<RiskSection risks={[makeRisk()]} />);
    expect(screen.getByText("股价处于历史高位，注意回调风险")).toBeInTheDocument();
  });

  it("renders risk icon 🔴 for high level", () => {
    render(<RiskSection risks={[makeRisk()]} />);
    expect(screen.getByText("🔴")).toBeInTheDocument();
  });

  it("renders risk icon 🟡 for medium level", () => {
    render(<RiskSection risks={[makeRisk({ level: "medium" })]} />);
    expect(screen.getByText("🟡")).toBeInTheDocument();
  });

  it("renders risk icon 🟢 for low level", () => {
    render(<RiskSection risks={[makeRisk({ level: "low" })]} />);
    expect(screen.getByText("🟢")).toBeInTheDocument();
  });

  it("renders risk icon 🔵 for info level", () => {
    render(<RiskSection risks={[makeRisk({ level: "info" })]} />);
    expect(screen.getByText("🔵")).toBeInTheDocument();
  });

  it("renders risk icon 🔵 for unknown level", () => {
    render(<RiskSection risks={[makeRisk({ level: "critical" as RiskWarning["level"] })]} />);
    expect(screen.getByText("🔵")).toBeInTheDocument();
  });

  // ── 风险等级样式 ──

  it("applies level class to risk item", () => {
    const { container } = render(<RiskSection risks={[makeRisk()]} />);
    const item = container.querySelector(".risk-item");
    expect(item?.className).toContain("high");
  });

  it("applies medium class for medium risk", () => {
    const { container } = render(<RiskSection risks={[makeRisk({ level: "medium" })]} />);
    const item = container.querySelector(".risk-item");
    expect(item?.className).toContain("medium");
  });

  it("applies low class for low risk", () => {
    const { container } = render(<RiskSection risks={[makeRisk({ level: "low" })]} />);
    const item = container.querySelector(".risk-item");
    expect(item?.className).toContain("low");
  });

  // ── 多风险项 ──

  it("renders multiple risk items", () => {
    const risks = [
      makeRisk({ level: "high", message: "风险A" }),
      makeRisk({ level: "medium", message: "风险B" }),
      makeRisk({ level: "low", message: "风险C" }),
    ];
    const { container } = render(<RiskSection risks={risks} />);
    const items = container.querySelectorAll(".risk-item");
    expect(items.length).toBe(3);
    expect(screen.getByText("风险A")).toBeInTheDocument();
    expect(screen.getByText("风险B")).toBeInTheDocument();
    expect(screen.getByText("风险C")).toBeInTheDocument();
  });

  // ── 空数组 ──

  it("renders nothing when risks array is empty", () => {
    const { container } = render(<RiskSection risks={[]} />);
    expect(container.querySelector(".risk-list")).toBeInTheDocument();
    expect(container.querySelectorAll(".risk-item").length).toBe(0);
  });

  // ── 布局结构 ──

  it("renders with risk-list container", () => {
    const { container } = render(<RiskSection risks={[makeRisk()]} />);
    expect(container.querySelector(".risk-list")).toBeInTheDocument();
  });

  it("renders risk-icon in each item", () => {
    const { container } = render(<RiskSection risks={[makeRisk()]} />);
    const icon = container.querySelector(".risk-icon");
    expect(icon).toBeInTheDocument();
    expect(icon?.textContent).toBe("🔴");
  });
});
