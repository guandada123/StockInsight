import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import BusinessQualitySection from "./BusinessQualitySection";
import type { BusinessQuality } from "../../types/api";

function makeBQ(overrides: Partial<BusinessQuality> = {}): BusinessQuality {
  return {
    code: "600519",
    name: "贵州茅台",
    price: 1500,
    overall_score: 75,
    overall_level: "优秀",
    assessment_summary: "公司质地优秀，具备长期竞争优势",
    company_profile: {
      name: "贵州茅台",
      industry: "白酒",
      business_scope: "白酒生产销售",
      main_business: "茅台酒及系列酒",
      listing_date: "2001-08-27",
      registered_capital: "12.56亿",
      total_market_cap: "1.8万亿",
    },
    moat: {
      score: 75,
      level: "宽护城河",
      dimensions: {
        "定价权(毛利率)": 18,
        "盈利能力(ROE)": 15,
        "品牌/牌照": 12,
        "技术壁垒(研发)": 8,
        规模优势: 5,
      },
      signals: ["品牌溢价显著", "毛利率持续>90%"],
      assessment: "品牌护城河极深",
    },
    cash_flow: {
      operating_cf_yi: 12.5,
      investing_cf_yi: -3.2,
      financing_cf_yi: -5.1,
      free_cf_yi: 9.3,
      quality: "优秀",
      assessment: "现金流健康",
    },
    lifecycle: {
      stage: "mature",
      stage_cn: "成熟期",
      confidence: 85,
      signals: ["稳定分红", "增长放缓"],
      suggestion: "关注分红率",
    },
    valuation: {
      score: 80,
      level: "合理偏低",
      pe: 25.5,
      pb: 8.3,
      peg: 1.2,
      signals: ["历史分位偏低"],
      assessment: "估值合理偏低",
    },
    events: {
      events: [
        { type: "财报发布", date: "2026-04-28", title: "2026年一季报净利润同比增长12%" },
        { type: "分红", date: "2026-06-15", title: "每10股派发现金红利200元" },
        { type: "公告", date: "2026-06-01", title: "股东大会决议公告" },
      ],
      assessment: "近期无重大利空",
    },
    ...overrides,
  };
}

describe("BusinessQualitySection", () => {
  // ── 基础渲染 ──

  it("renders overall score and level", () => {
    render(<BusinessQualitySection bq={makeBQ()} />);
    expect(screen.getByText("75分 → 优秀")).toBeInTheDocument();
  });

  it("renders assessment summary", () => {
    render(<BusinessQualitySection bq={makeBQ()} />);
    expect(screen.getByText("公司质地优秀，具备长期竞争优势")).toBeInTheDocument();
  });

  it("renders company profile main business", () => {
    render(<BusinessQualitySection bq={makeBQ()} />);
    expect(screen.getByText("茅台酒及系列酒")).toBeInTheDocument();
  });

  it("shows fallback text when main_business is empty", () => {
    const bq = makeBQ();
    bq.company_profile.main_business = "";
    render(<BusinessQualitySection bq={bq} />);
    expect(screen.getByText("数据暂不可用")).toBeInTheDocument();
  });

  it("renders industry and lifecycle info", () => {
    render(<BusinessQualitySection bq={makeBQ()} />);
    expect(screen.getByText("行业:", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("白酒", { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/成熟期/)).toBeInTheDocument();
    expect(screen.getByText("85", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("置信", { exact: false })).toBeInTheDocument();
  });

  it("renders section headers", () => {
    render(<BusinessQualitySection bq={makeBQ()} />);
    expect(screen.getByText("Q1 靠什么赚钱 · Q4 什么阶段")).toBeInTheDocument();
    expect(screen.getByText(/Q2 护城河/)).toBeInTheDocument();
    expect(screen.getByText(/Q3 现金流/)).toBeInTheDocument();
    expect(screen.getByText(/Q5 估值/)).toBeInTheDocument();
  });

  // ── 护城河渲染 ──

  it("renders moat score and level", () => {
    render(<BusinessQualitySection bq={makeBQ()} />);
    expect(screen.getByText("75分 宽护城河")).toBeInTheDocument();
  });

  it("renders moat dimensions with shortened labels", () => {
    render(<BusinessQualitySection bq={makeBQ()} />);
    expect(screen.getByText("定价权")).toBeInTheDocument();
    expect(screen.getByText("ROE")).toBeInTheDocument();
    expect(screen.getByText("品牌")).toBeInTheDocument();
    expect(screen.getByText("研发")).toBeInTheDocument();
    expect(screen.getByText("规模")).toBeInTheDocument();
  });

  it("renders moat dimension bar values", () => {
    render(<BusinessQualitySection bq={makeBQ()} />);
    expect(screen.getByText("18")).toBeInTheDocument();
    expect(screen.getByText("15")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  it("uses original dimension key when not in DIM_LABELS mapping", () => {
    const bq = makeBQ();
    bq.moat.dimensions = { 管理层能力: 10, 客户忠诚度: 7 };
    render(<BusinessQualitySection bq={bq} />);
    expect(screen.getByText("管理层能力")).toBeInTheDocument();
    expect(screen.getByText("客户忠诚度")).toBeInTheDocument();
  });

  it("renders no bar-row when dimensions are empty", () => {
    const bq = makeBQ();
    bq.moat.dimensions = {};
    const { container } = render(<BusinessQualitySection bq={bq} />);
    expect(container.querySelectorAll(".bar-row").length).toBe(0);
  });

  // ── 现金流渲染 ──

  it("renders operating CF value with 亿 suffix", () => {
    render(<BusinessQualitySection bq={makeBQ()} />);
    expect(screen.getByText("12.5亿")).toBeInTheDocument();
  });

  it("renders free CF value with 亿 suffix", () => {
    render(<BusinessQualitySection bq={makeBQ()} />);
    expect(screen.getByText("9.3亿")).toBeInTheDocument();
  });

  // ── 估值渲染 ──

  it("renders valuation score and level", () => {
    render(<BusinessQualitySection bq={makeBQ()} />);
    expect(screen.getByText("80分 合理偏低")).toBeInTheDocument();
  });

  it("renders PE, PB, PEG values", () => {
    render(<BusinessQualitySection bq={makeBQ()} />);
    expect(screen.getByText("25.5")).toBeInTheDocument();
    expect(screen.getByText("8.3")).toBeInTheDocument();
    expect(screen.getByText("1.2")).toBeInTheDocument();
  });

  it("shows -- for null PE/PB/PEG", () => {
    const bq = makeBQ();
    bq.valuation.pe = null;
    bq.valuation.pb = null;
    bq.valuation.peg = null;
    render(<BusinessQualitySection bq={bq} />);
    const dashes = screen.getAllByText("--");
    expect(dashes.length).toBeGreaterThanOrEqual(3);
  });

  // ── 事件渲染 ──

  it("renders event tags when events exist", () => {
    render(<BusinessQualitySection bq={makeBQ()} />);
    expect(screen.getByText(/Q7 近期大事/)).toBeInTheDocument();
    expect(screen.getByText(/2026年一季报净利润同比增长12%/)).toBeInTheDocument();
    expect(screen.getByText(/每10股派发现金红利200元/)).toBeInTheDocument();
  });

  it("limits events to first 3", () => {
    const bq = makeBQ();
    bq.events.events = [
      { type: "A", date: "01", title: "第一件事" },
      { type: "B", date: "02", title: "第二件事" },
      { type: "C", date: "03", title: "第三件事" },
      { type: "D", date: "04", title: "第四件事" },
    ];
    render(<BusinessQualitySection bq={bq} />);
    // titles are inside spans like "[A] 01 第一件事" — use inexact match
    expect(screen.getByText("第一件事", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("第二件事", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("第三件事", { exact: false })).toBeInTheDocument();
    expect(screen.queryByText("第四件事", { exact: false })).not.toBeInTheDocument();
  });

  it("does not render events section when events array is empty", () => {
    const bq = makeBQ();
    bq.events.events = [];
    render(<BusinessQualitySection bq={bq} />);
    expect(screen.queryByText(/Q7 近期大事/)).not.toBeInTheDocument();
  });

  // ── overall_score 颜色边界 ──

  it("uses green (var(--gn)) when overall_score >= 55", () => {
    render(<BusinessQualitySection bq={makeBQ({ overall_score: 75 })} />);
    const el = screen.getByText("75分 → 优秀");
    expect(el.getAttribute("style")).toContain("var(--gn)");
  });

  it("uses yellow (var(--gd)) when overall_score = 45 (< 55, >= 40)", () => {
    const bq = makeBQ({ overall_score: 45, overall_level: "一般" });
    render(<BusinessQualitySection bq={bq} />);
    const el = screen.getByText("45分 → 一般");
    expect(el.getAttribute("style")).toContain("var(--gd)");
  });

  it("uses yellow at boundary 40", () => {
    const bq = makeBQ({ overall_score: 40, overall_level: "一般" });
    render(<BusinessQualitySection bq={bq} />);
    const el = screen.getByText("40分 → 一般");
    expect(el.getAttribute("style")).toContain("var(--gd)");
  });

  it("uses red (var(--rd)) when overall_score < 40", () => {
    const bq = makeBQ({ overall_score: 35, overall_level: "较差" });
    render(<BusinessQualitySection bq={bq} />);
    const el = screen.getByText("35分 → 较差");
    expect(el.getAttribute("style")).toContain("var(--rd)");
  });

  // ── 现金流 quality 颜色 ──

  it("colors cash flow quality green for 优秀", () => {
    render(<BusinessQualitySection bq={makeBQ()} />);
    const all = screen.getAllByText("优秀");
    const styled = all.filter((el) => el.getAttribute("style")?.includes("var(--gn)"));
    expect(styled.length).toBeGreaterThanOrEqual(1);
  });

  it("colors cash flow quality cyan (var(--cy)) for 良好", () => {
    const bq = makeBQ();
    bq.cash_flow.quality = "良好";
    render(<BusinessQualitySection bq={bq} />);
    const el = screen.getByText("良好");
    expect(el.getAttribute("style")).toContain("var(--cy)");
  });

  it("colors cash flow quality yellow (var(--gd)) for 一般", () => {
    const bq = makeBQ({ overall_score: 45, overall_level: "一般" });
    bq.cash_flow.quality = "一般";
    render(<BusinessQualitySection bq={bq} />);
    const all = screen.getAllByText("一般");
    const styled = all.filter((el) => el.getAttribute("style")?.includes("var(--gd)"));
    expect(styled.length).toBeGreaterThanOrEqual(1);
  });

  it("colors cash flow quality red (var(--rd)) for other values", () => {
    const bq = makeBQ();
    bq.cash_flow.quality = "较差";
    render(<BusinessQualitySection bq={bq} />);
    const el = screen.getByText("较差");
    expect(el.getAttribute("style")).toContain("var(--rd)");
  });

  // ── 自由现金流颜色 ──

  it("colors free CF green when >= 0", () => {
    render(<BusinessQualitySection bq={makeBQ()} />);
    const el = screen.getByText("9.3亿");
    expect(el.getAttribute("style")).toContain("var(--gn)");
  });

  it("colors free CF red when negative", () => {
    const bq = makeBQ();
    bq.cash_flow.free_cf_yi = -2.5;
    render(<BusinessQualitySection bq={bq} />);
    const el = screen.getByText("-2.5亿");
    expect(el.getAttribute("style")).toContain("var(--rd)");
  });

  it("shows --亿 when free CF is 0 (falsy check)", () => {
    const bq = makeBQ();
    bq.cash_flow.free_cf_yi = 0;
    render(<BusinessQualitySection bq={bq} />);
    expect(screen.getByText("--亿")).toBeInTheDocument();
  });

  // ── 估值 level 颜色 ──

  it("colors valuation green for 低估", () => {
    const bq = makeBQ();
    bq.valuation.level = "低估";
    render(<BusinessQualitySection bq={bq} />);
    const el = screen.getByText("80分 低估");
    expect(el.getAttribute("style")).toContain("var(--gn)");
  });

  it("colors valuation green for 合理偏低", () => {
    render(<BusinessQualitySection bq={makeBQ()} />);
    const el = screen.getByText("80分 合理偏低");
    expect(el.getAttribute("style")).toContain("var(--gn)");
  });

  it("colors valuation yellow (var(--gd)) for 合理偏高", () => {
    const bq = makeBQ();
    bq.valuation.level = "合理偏高";
    render(<BusinessQualitySection bq={bq} />);
    const el = screen.getByText("80分 合理偏高");
    expect(el.getAttribute("style")).toContain("var(--gd)");
  });

  it("colors valuation red for 高估", () => {
    const bq = makeBQ();
    bq.valuation.level = "高估";
    bq.valuation.score = 30;
    render(<BusinessQualitySection bq={bq} />);
    const el = screen.getByText("30分 高估");
    expect(el.getAttribute("style")).toContain("var(--rd)");
  });

  // ── 护城河维度条形图颜色 ──

  it("uses green bar-fill for dimension >= 15", () => {
    const { container } = render(<BusinessQualitySection bq={makeBQ()} />);
    const fills = container.querySelectorAll(".br-fill");
    // First: 18 >= 15 → green
    expect((fills[0] as HTMLElement).style.background).toContain("var(--gn)");
    // Second: 15 >= 15 → green
    expect((fills[1] as HTMLElement).style.background).toContain("var(--gn)");
  });

  it("uses yellow bar-fill for dimension between 8 and 14", () => {
    const { container } = render(<BusinessQualitySection bq={makeBQ()} />);
    const fills = container.querySelectorAll(".br-fill");
    // Third: 12 >= 8, < 15 → yellow
    expect((fills[2] as HTMLElement).style.background).toContain("var(--gd)");
    // Fourth: 8 >= 8 → yellow (boundary)
    expect((fills[3] as HTMLElement).style.background).toContain("var(--gd)");
  });

  it("uses red bar-fill for dimension < 8", () => {
    const { container } = render(<BusinessQualitySection bq={makeBQ()} />);
    const fills = container.querySelectorAll(".br-fill");
    // Fifth: 5 < 8 → red
    expect((fills[4] as HTMLElement).style.background).toContain("var(--rd)");
  });

  // ── 护城河 score 颜色 ──

  it("colors moat score green when >= 60", () => {
    render(<BusinessQualitySection bq={makeBQ()} />);
    const el = screen.getByText("75分 宽护城河");
    expect(el.getAttribute("style")).toContain("var(--gn)");
  });

  it("colors moat score yellow when >= 40 and < 60", () => {
    const bq = makeBQ();
    bq.moat.score = 55;
    bq.moat.level = "窄护城河";
    render(<BusinessQualitySection bq={bq} />);
    const el = screen.getByText("55分 窄护城河");
    expect(el.getAttribute("style")).toContain("var(--gd)");
  });

  it("colors moat score red when < 40", () => {
    const bq = makeBQ();
    bq.moat.score = 35;
    bq.moat.level = "无护城河";
    render(<BusinessQualitySection bq={bq} />);
    const el = screen.getByText("35分 无护城河");
    expect(el.getAttribute("style")).toContain("var(--rd)");
  });

  // ── 容错 / 边缘情况 ──

  it("handles undefined main_business gracefully", () => {
    const bq = makeBQ();
    (bq.company_profile as any).main_business = undefined;
    render(<BusinessQualitySection bq={bq} />);
    expect(screen.getByText("数据暂不可用")).toBeInTheDocument();
  });

  it("handles undefined moat dimensions gracefully", () => {
    const bq = makeBQ();
    (bq.moat as any).dimensions = undefined;
    const { container } = render(<BusinessQualitySection bq={bq} />);
    expect(container.querySelectorAll(".bar-row").length).toBe(0);
  });

  it("handles undefined cash_flow gracefully", () => {
    const bq = makeBQ();
    (bq.cash_flow as any).free_cf_yi = undefined;
    (bq.cash_flow as any).operating_cf_yi = undefined;
    render(<BusinessQualitySection bq={bq} />);
    // Both should show "--亿" instead of undefined values
    const cfDash = screen.getAllByText("--亿");
    expect(cfDash.length).toBeGreaterThanOrEqual(2);
  });

  it("handles null valuation pe/pb/peg gracefully", () => {
    const bq = makeBQ();
    bq.valuation.pe = null;
    bq.valuation.pb = null;
    bq.valuation.peg = null;
    render(<BusinessQualitySection bq={bq} />);
    // Should not crash
    expect(screen.getByText(/Q5 估值/)).toBeInTheDocument();
  });

  it("truncates event title to 20 characters", () => {
    const bq = makeBQ();
    // 22 characters — slice(0, 20) will truncate 2 chars
    const longTitle = "这是一个超过二十个字符的非常长的事件标题呀";
    const truncated = longTitle.slice(0, 20); // "这是一个超过二十个字符的非常长的事件标"
    const remaining = longTitle.slice(20); // "题呀"
    bq.events.events = [{ type: "公告", date: "2026-06-01", title: longTitle }];
    render(<BusinessQualitySection bq={bq} />);
    expect(screen.getByText(truncated, { exact: false })).toBeInTheDocument();
    // The title is rendered inside "[公告] 2026-06-01 这是一个…", so remaining part should not appear
    expect(screen.queryByText(remaining, { exact: false })).not.toBeInTheDocument();
  });
});
