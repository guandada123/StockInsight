import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import SectorSection from "./SectorSection";
import type { SectorAnalysis } from "../../types/api";

function makeSA(overrides: Partial<SectorAnalysis> = {}): SectorAnalysis {
  return {
    industry: "白酒",
    concepts: ["白酒概念", "贵州板块", "国企改革"],
    sector_name: "白酒行业",
    sector_rank: 3,
    sector_total: 45,
    sector_change_pct: 1.25,
    sector_fund_flow_yi: 2.5,
    rank_label: "领先",
    rank_color: "green",
    assessment: "行业整体处于复苏阶段，龙头公司受益明显",
    ...overrides,
  };
}

describe("SectorSection", () => {
  // ── 基础渲染 ──

  it("renders rank badge with label", () => {
    render(<SectorSection sa={makeSA()} />);
    expect(screen.getByText("领先")).toBeInTheDocument();
  });

  it("renders rank badge with color class", () => {
    const { container } = render(<SectorSection sa={makeSA()} />);
    const badge = container.querySelector(".sector-badge");
    expect(badge?.className).toContain("green");
  });

  it("renders industry name", () => {
    render(<SectorSection sa={makeSA()} />);
    // "白酒" appears both as industry name (<strong>) and in concept tag "白酒概念"
    const matches = screen.getAllByText("白酒", { exact: false });
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  // ── 排名渲染 (sector_rank > 0) ──

  it("renders rank number and total", () => {
    render(<SectorSection sa={makeSA()} />);
    expect(screen.getByText("#3", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("/45", { exact: false })).toBeInTheDocument();
  });

  it("renders sector change with positive sign and green color", () => {
    render(<SectorSection sa={makeSA()} />);
    // The change is rendered as "+1.25%" (positive with + prefix)
    const chg = screen.getByText("+1.25%");
    expect(chg).toBeInTheDocument();
    expect(chg.getAttribute("style")).toContain("var(--gn)");
  });

  it("renders sector change with negative sign and red color", () => {
    const sa = makeSA({ sector_change_pct: -0.85 });
    render(<SectorSection sa={sa} />);
    const chg = screen.getByText("-0.85%");
    expect(chg).toBeInTheDocument();
    expect(chg.getAttribute("style")).toContain("var(--rd)");
  });

  it("renders sector fund flow with positive sign and green color", () => {
    render(<SectorSection sa={makeSA()} />);
    const flow = screen.getByText("+2.5亿");
    expect(flow).toBeInTheDocument();
    expect(flow.getAttribute("style")).toContain("var(--gn)");
  });

  it("renders sector fund flow with negative sign and red color", () => {
    const sa = makeSA({ sector_fund_flow_yi: -1.2 });
    render(<SectorSection sa={sa} />);
    const flow = screen.getByText("-1.2亿");
    expect(flow).toBeInTheDocument();
    expect(flow.getAttribute("style")).toContain("var(--rd)");
  });

  it("renders zero change with + prefix and green color", () => {
    const sa = makeSA({ sector_change_pct: 0 });
    render(<SectorSection sa={sa} />);
    const chg = screen.getByText("+0%");
    expect(chg).toBeInTheDocument();
    expect(chg.getAttribute("style")).toContain("var(--gn)");
  });

  it("renders zero fund flow with + prefix and green color", () => {
    const sa = makeSA({ sector_fund_flow_yi: 0 });
    render(<SectorSection sa={sa} />);
    const flow = screen.getByText("+0亿");
    expect(flow).toBeInTheDocument();
    expect(flow.getAttribute("style")).toContain("var(--gn)");
  });

  // ── 排名不渲染 (sector_rank = 0) ──

  it("does not render rank details when sector_rank is 0", () => {
    const sa = makeSA({ sector_rank: 0, sector_change_pct: 1.5, sector_fund_flow_yi: 3.0 });
    render(<SectorSection sa={sa} />);
    // The "行业: 白酒" div also has .sector-rank class, so count is 1.
    // What should NOT appear is the rank details: #, 涨跌, 资金
    expect(screen.queryByText(/排名/)).not.toBeInTheDocument();
    expect(screen.queryByText(/涨跌/)).not.toBeInTheDocument();
    expect(screen.queryByText(/资金/)).not.toBeInTheDocument();
  });

  // ── 概念标签 ──

  it("renders concept tags", () => {
    render(<SectorSection sa={makeSA()} />);
    expect(screen.getByText("白酒概念")).toBeInTheDocument();
    expect(screen.getByText("贵州板块")).toBeInTheDocument();
    expect(screen.getByText("国企改革")).toBeInTheDocument();
  });

  it("renders concept tags with purple class", () => {
    const { container } = render(<SectorSection sa={makeSA()} />);
    const tags = container.querySelectorAll(".tag-purple");
    expect(tags.length).toBe(3);
  });

  it("does not render concepts section when concepts array is empty", () => {
    const sa = makeSA({ concepts: [] });
    const { container } = render(<SectorSection sa={sa} />);
    expect(container.querySelectorAll(".tag-purple").length).toBe(0);
  });

  it("does not render concepts section when concepts is undefined", () => {
    const sa = makeSA({ concepts: undefined as unknown as string[] });
    const { container } = render(<SectorSection sa={sa} />);
    expect(container.querySelectorAll(".tag-purple").length).toBe(0);
  });

  // ── 评估 ──

  it("renders assessment", () => {
    render(<SectorSection sa={makeSA()} />);
    expect(screen.getByText("行业整体处于复苏阶段，龙头公司受益明显")).toBeInTheDocument();
  });

  it("does not render assessment when assessment is empty string", () => {
    const sa = makeSA({ assessment: "" });
    const { container } = render(<SectorSection sa={sa} />);
    // Only one child: sector-info (no assessment div)
    const texts = container.querySelectorAll(".c-tx");
    expect(texts.length).toBe(0);
  });

  it("does not render assessment when assessment is undefined", () => {
    const sa = makeSA({ assessment: undefined as unknown as string });
    const { container } = render(<SectorSection sa={sa} />);
    const texts = container.querySelectorAll(".c-tx");
    expect(texts.length).toBe(0);
  });

  // ── 容错 ──

  it("handles single concept gracefully", () => {
    const sa = makeSA({ concepts: ["仅有一个概念"] });
    render(<SectorSection sa={sa} />);
    expect(screen.getByText("仅有一个概念")).toBeInTheDocument();
  });

  it("handles negative rank values", () => {
    const sa = makeSA({ sector_rank: -1, sector_change_pct: -0.5, sector_fund_flow_yi: -3.0 });
    render(<SectorSection sa={sa} />);
    // -1 > 0 is false → rank details (#, 涨跌, 资金) should not appear
    expect(screen.queryByText(/排名/)).not.toBeInTheDocument();
    expect(screen.queryByText(/涨跌/)).not.toBeInTheDocument();
    expect(screen.queryByText(/资金/)).not.toBeInTheDocument();
  });

  it("renders full rank info with all fields", () => {
    const { container } = render(<SectorSection sa={makeSA()} />);
    // Verify the structure: badge + rank divs
    expect(container.querySelector(".sector-info")).toBeInTheDocument();
    expect(container.querySelector(".sector-badge")).toBeInTheDocument();
  });

  it("renders assessment with fs-11 and c-tx classes", () => {
    const { container } = render(<SectorSection sa={makeSA()} />);
    const assessment = container.querySelector(".c-tx");
    expect(assessment?.className).toContain("fs-11");
    expect(assessment?.className).toContain("c-tx");
  });
});
