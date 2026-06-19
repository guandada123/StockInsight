import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import PsychologySection from "./PsychologySection";
import type { RetailPsychology } from "../../types/api";

function makeRP(overrides: Partial<RetailPsychology> = {}): RetailPsychology {
  return {
    emotion: "贪婪",
    emotion_score: 82,
    behavior_pattern: "市场情绪高涨，散户追涨意愿强烈",
    sentiment_indicators: ["融资余额持续增加", "新开户数创近期新高", "散户仓位处于高位"],
    advice: "建议控制仓位，避免追高，可适当减仓锁定利润",
    ...overrides,
  };
}

describe("PsychologySection", () => {
  // ── 基础渲染 ──

  it("renders emotion label", () => {
    render(<PsychologySection rp={makeRP()} />);
    expect(screen.getByText("贪婪")).toBeInTheDocument();
  });

  it("renders emotion score", () => {
    render(<PsychologySection rp={makeRP()} />);
    expect(screen.getByText("情绪强度: 82/100")).toBeInTheDocument();
  });

  it("renders behavior pattern", () => {
    render(<PsychologySection rp={makeRP()} />);
    expect(screen.getByText("市场情绪高涨，散户追涨意愿强烈")).toBeInTheDocument();
  });

  // ── 情绪样式分类 ──

  it("uses greed class for 贪婪", () => {
    const { container } = render(<PsychologySection rp={makeRP()} />);
    const label = container.querySelector(".emotion-label");
    expect(label?.className).toContain("greed");
  });

  it("uses greed class for 追涨", () => {
    const { container } = render(<PsychologySection rp={makeRP({ emotion: "追涨" })} />);
    const label = container.querySelector(".emotion-label");
    expect(label?.className).toContain("greed");
  });

  it("uses fear class for 恐惧", () => {
    const { container } = render(<PsychologySection rp={makeRP({ emotion: "恐惧" })} />);
    const label = container.querySelector(".emotion-label");
    expect(label?.className).toContain("fear");
  });

  it("uses fear class for 恐慌抛售", () => {
    const { container } = render(<PsychologySection rp={makeRP({ emotion: "恐慌抛售" })} />);
    const label = container.querySelector(".emotion-label");
    expect(label?.className).toContain("fear");
  });

  it("uses hesitation class for 犹豫观望", () => {
    const { container } = render(<PsychologySection rp={makeRP({ emotion: "犹豫观望" })} />);
    const label = container.querySelector(".emotion-label");
    expect(label?.className).toContain("hesitation");
  });

  it("uses panic class for emotion containing 恐慌", () => {
    const { container } = render(<PsychologySection rp={makeRP({ emotion: "恐慌加剧" })} />);
    const label = container.querySelector(".emotion-label");
    expect(label?.className).toContain("panic");
  });

  it("uses unknown class for unexpected emotion", () => {
    const { container } = render(<PsychologySection rp={makeRP({ emotion: "淡定" })} />);
    const label = container.querySelector(".emotion-label");
    expect(label?.className).toContain("unknown");
  });

  // ── 情绪指示器 ──

  it("renders sentiment indicators", () => {
    render(<PsychologySection rp={makeRP()} />);
    expect(screen.getByText("• 融资余额持续增加", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("• 新开户数创近期新高", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("• 散户仓位处于高位", { exact: false })).toBeInTheDocument();
  });

  it("does not render sentiment indicators when array is empty", () => {
    const rp = makeRP({ sentiment_indicators: [] });
    render(<PsychologySection rp={rp} />);
    expect(screen.queryByText("融资余额")).not.toBeInTheDocument();
  });

  it("does not render sentiment indicators when undefined", () => {
    const rp = makeRP({ sentiment_indicators: undefined as unknown as string[] });
    render(<PsychologySection rp={rp} />);
    expect(screen.queryByText("融资余额")).not.toBeInTheDocument();
  });

  it("renders single sentiment indicator", () => {
    const rp = makeRP({ sentiment_indicators: ["仅有一个指标"] });
    render(<PsychologySection rp={rp} />);
    expect(screen.getByText("仅有一个指标", { exact: false })).toBeInTheDocument();
  });

  // ── 建议 ──

  it("renders advice", () => {
    render(<PsychologySection rp={makeRP()} />);
    expect(screen.getByText("建议控制仓位，避免追高，可适当减仓锁定利润")).toBeInTheDocument();
  });

  it("does not render advice when advice is empty string", () => {
    const { container } = render(<PsychologySection rp={makeRP({ advice: "" })} />);
    expect(container.querySelector(".emotion-advice")).not.toBeInTheDocument();
  });

  it("does not render advice when advice is undefined", () => {
    const { container } = render(
      <PsychologySection rp={makeRP({ advice: undefined as unknown as string })} />
    );
    expect(container.querySelector(".emotion-advice")).not.toBeInTheDocument();
  });

  // ── 容错 / 边缘情况 ──

  it("handles zero emotion score", () => {
    render(<PsychologySection rp={makeRP({ emotion_score: 0 })} />);
    expect(screen.getByText("情绪强度: 0/100")).toBeInTheDocument();
  });

  it("handles 100 emotion score", () => {
    render(<PsychologySection rp={makeRP({ emotion_score: 100 })} />);
    expect(screen.getByText("情绪强度: 100/100")).toBeInTheDocument();
  });

  it("renders all main sections in correct order", () => {
    const { container } = render(<PsychologySection rp={makeRP()} />);
    // emotion-display contains: emotion-label, emotion-score, emotion-desc
    expect(container.querySelector(".emotion-display")).toBeInTheDocument();
    expect(container.querySelector(".emotion-label")).toBeInTheDocument();
    expect(container.querySelector(".emotion-desc")).toBeInTheDocument();
    expect(container.querySelector(".emotion-advice")).toBeInTheDocument();
  });
});
