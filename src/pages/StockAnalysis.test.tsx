import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

// ── Mock useApi ──
const mockFetchApi = vi.fn();
vi.mock("../hooks/useApi", () => ({
  useApi: () => ({
    fetchApi: mockFetchApi,
    loading: false,
    data: null,
    error: null,
  }),
}));

// ── Mock child sections ──
vi.mock("./stock-analysis/SectorSection", () => ({
  default: () => <div data-testid="sector-section">Sector</div>,
}));
vi.mock("./stock-analysis/PatternSection", () => ({
  default: () => <div data-testid="pattern-section">Pattern</div>,
}));
vi.mock("./stock-analysis/ManipulatorSection", () => ({
  default: () => <div data-testid="manipulator-section">Manipulator</div>,
}));
vi.mock("./stock-analysis/PsychologySection", () => ({
  default: () => <div data-testid="psychology-section">Psychology</div>,
}));
vi.mock("./stock-analysis/PredictionSection", () => ({
  default: () => <div data-testid="prediction-section">Prediction</div>,
}));
vi.mock("./stock-analysis/OperationSection", () => ({
  default: () => <div data-testid="operation-section">Operation</div>,
}));
vi.mock("./stock-analysis/CombinedSection", () => ({
  default: () => <div data-testid="combined-section">Combined</div>,
}));
vi.mock("./stock-analysis/RiskSection", () => ({
  default: () => <div data-testid="risk-section">Risk</div>,
}));
vi.mock("./stock-analysis/DataSourcesSection", () => ({
  default: () => <div data-testid="datasources-section">DataSources</div>,
}));
vi.mock("./stock-analysis/BusinessQualitySection", () => ({
  default: () => <div data-testid="bq-section">BQ</div>,
}));
vi.mock("./stock-analysis/MarketIndicesSection", () => ({
  default: () => <div data-testid="market-indices">Indices</div>,
}));
vi.mock("./stock-analysis/ScoreCircle", () => ({
  default: ({ score }: { score: number }) => <div data-testid="score-circle">{score}</div>,
}));

// ── Mock KlineChart ──
vi.mock("../components/KlineChart", () => ({
  default: () => <div data-testid="kline-chart">Kline</div>,
}));

// ── Mock data factory ──
function makeMockResult(overrides = {}) {
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
      factor_scores: {
        momentum: 80,
        technical: 70,
        fundamental: 85,
        volume: 65,
        risk: 75,
      },
    },
    risk: {
      sharpe_ratio: 1.2,
      max_drawdown_pct: -15,
      annual_volatility_pct: 25,
      var_95_pct: -3.5,
    },
    financial: { roe: 18, pe: 25, pb: 5, eps: 60 },
    fund_flow: { direction: "流入", total_5d: 3.5, chip_score: 72, national_team: "有" },
    debate: {
      bull_points: ["业绩增长确定", "估值合理"],
      bear_points: ["宏观不确定", "增速放缓"],
      bull_score: 70,
      bear_score: 30,
      verdict: "偏多",
      action: "持有",
    },
    ml: { direction: "看涨", confidence: 72, votes: "3/5模型一致", models: {} },
    signal: { bias: "bullish", score: 72, combo_strength: "中等偏强" },
    near_5d: 0.5,
    near_20d: 2.1,
    short_score: 65,
    long_score: 80,
    style: "价值成长",
    sector_analysis: {
      industry: "白酒",
      concepts: ["消费", "白马"],
      sector_name: "白酒",
      sector_rank: 3,
      sector_total: 20,
      sector_change_pct: 1.2,
      sector_fund_flow_yi: 5.2,
      rank_label: "前列",
      rank_color: "green",
      assessment: "板块表现强势",
    },
    pattern_analysis: {
      recent_patterns: [
        {
          name: "三连阳",
          date: "2026-06-17",
          type: "bullish",
          description: "连续3日收阳",
          reliability: "中",
        },
      ],
      summary: "近期偏多",
      trend_phase: "上升趋势",
      key_observation: "量价配合良好",
    },
    manipulator_intention: {
      phase: "吸筹末期",
      phase_confidence: 65,
      signals: ["缩量回调"],
      volume_analysis: "量能温和",
      chip_analysis: "筹码集中",
      assessment: "庄家控盘较高",
      risk_note: "注意高位派发",
    },
    retail_psychology: {
      emotion: "谨慎乐观",
      emotion_score: 60,
      behavior_pattern: "追涨意愿不强",
      sentiment_indicators: ["换手率低"],
      advice: "可逢低布局",
    },
    prediction: {
      direction: "看涨",
      confidence: 65,
      price_range: { low: 1490, high: 1520 },
      key_level: 1510,
      rationale: "技术面支撑",
    },
    operation_advice: {
      direction: "买入",
      direction_color: "red",
      confidence: "高",
      entry_range: { low: 1480, high: 1500 },
      stop_loss: 1460,
      take_profit: [1550, 1580],
      position_pct: 30,
      holding_days: "5-10天",
      key_points: ["放量突破确认"],
    },
    combined_summary: {
      kline_summary: "K线偏多",
      manipulator_summary: "庄家意向不明",
      synergy_assessment: "共振偏强",
      overall_conclusion: "可适度参与",
    },
    risk_warnings: [
      { level: "medium", message: "大盘回调风险" },
      { level: "low", message: "行业利空传闻" },
    ],
    data_sources: {
      quote_source: "新浪财经",
      kline_source: "东方财富",
      sector_source: "同花顺",
      fundamental_source: "Tushare",
      update_time: "2026-06-18 10:00",
      disclaimer: "仅供参考",
    },
    business_quality: {
      code: "600519",
      name: "贵州茅台",
      price: 1500,
      overall_score: 82,
      overall_level: "A",
      company_profile: {
        name: "贵州茅台",
        industry: "白酒",
        business_scope: "茅台酒系列",
        main_business: "白酒制造",
        listing_date: "2001-08-27",
        registered_capital: "12.56亿",
        total_market_cap: "1.88万亿",
      },
      moat: {
        score: 85,
        level: "宽护城河",
        dimensions: { brand: 95, pricing: 80, channel: 75 },
        signals: ["品牌溢价显著"],
        assessment: "护城河深厚",
      },
      cash_flow: {
        operating_cf_yi: 80,
        investing_cf_yi: -20,
        financing_cf_yi: -30,
        free_cf_yi: 60,
        quality: "优秀",
        assessment: "造血能力强",
      },
      lifecycle: {
        stage: "mature",
        stage_cn: "成熟期",
        confidence: 85,
        signals: ["稳定分红"],
        suggestion: "关注分红政策",
      },
      valuation: {
        score: 55,
        level: "合理偏高",
        pe: 25,
        pb: 5,
        peg: 1.5,
        signals: ["估值处于中位数"],
        assessment: "估值合理偏高",
      },
      events: {
        events: [{ type: "财报", date: "2026-08-30", title: "中报发布" }],
        assessment: "有潜在催化剂",
      },
      assessment_summary: "质地优秀",
    },
    ...overrides,
  };
}

function renderAtRoute(code = "600519") {
  return render(
    <MemoryRouter initialEntries={[`/stock/${code}`]}>
      <Routes>
        <Route path="/stock/:code" element={<StockAnalysis />} />
      </Routes>
    </MemoryRouter>
  );
}

// ── Import AFTER mocks ──
import StockAnalysis from "./StockAnalysis";

describe("StockAnalysis", () => {
  beforeEach(() => {
    mockFetchApi.mockReset();
  });

  // ═══════════════════════
  // Loading / Error / Empty
  // ═══════════════════════
  it("shows loading state while fetching", async () => {
    mockFetchApi.mockImplementation(() => new Promise(() => {}));
    renderAtRoute("600519");
    expect(screen.getByText("正在分析 600519...")).toBeInTheDocument();
  });

  it("shows error message on analysis failure", async () => {
    mockFetchApi.mockResolvedValue({
      success: false,
      data: null,
      error: "数据源不可用",
      freshness: "stale",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.getByText("分析失败: 数据源不可用")).toBeInTheDocument();
    });
  });

  it("shows no data placeholder when result is null", async () => {
    mockFetchApi.mockResolvedValue({
      success: true,
      data: null,
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.getByText("无数据")).toBeInTheDocument();
    });
  });

  // ═══════════════════════
  // Full analysis rendering
  // ═══════════════════════
  it("renders market indices section", async () => {
    mockFetchApi.mockResolvedValue({
      success: true,
      data: makeMockResult(),
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.getByTestId("market-indices")).toBeInTheDocument();
    });
  });

  it("renders sector analysis section", async () => {
    mockFetchApi.mockResolvedValue({
      success: true,
      data: makeMockResult(),
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.getByTestId("sector-section")).toBeInTheDocument();
    });
  });

  it("renders Kline chart", async () => {
    mockFetchApi.mockResolvedValue({
      success: true,
      data: makeMockResult(),
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.getByTestId("kline-chart")).toBeInTheDocument();
    });
  });

  it("renders score circle with composite score", async () => {
    mockFetchApi.mockResolvedValue({
      success: true,
      data: makeMockResult(),
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.getByTestId("score-circle")).toHaveTextContent("75");
    });
  });

  it("renders signal section with bias text", async () => {
    const result = makeMockResult({
      signal: { bias: "bullish", score: 72, combo_strength: "中等偏强" },
    });
    mockFetchApi.mockResolvedValue({
      success: true,
      data: result,
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      // "偏多" appears both in signal section (from bias) and debate section (from verdict)
      expect(screen.getAllByText("偏多").length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText(/组合信号强度/)).toBeInTheDocument();
    });
  });

  it("renders bearish signal correctly", async () => {
    const result = makeMockResult({
      signal: { bias: "bearish", score: 30, combo_strength: "偏弱" },
    });
    mockFetchApi.mockResolvedValue({
      success: true,
      data: result,
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.getByText("偏空")).toBeInTheDocument();
    });
  });

  it("renders neutral signal correctly", async () => {
    const result = makeMockResult({
      signal: { bias: "neutral", score: 50, combo_strength: "中性" },
    });
    mockFetchApi.mockResolvedValue({
      success: true,
      data: result,
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.getByText("中性")).toBeInTheDocument();
    });
  });

  it("renders fund flow and financial data", async () => {
    mockFetchApi.mockResolvedValue({
      success: true,
      data: makeMockResult(),
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.getByText(/3.5亿/)).toBeInTheDocument(); // total_5d
      // "72" appears both as chip_score and in confidence % — use getAllByText to avoid multi-match error
      expect(screen.getAllByText(/72/).length).toBeGreaterThanOrEqual(1);
    });
  });

  it("renders multi-argument debate section", async () => {
    mockFetchApi.mockResolvedValue({
      success: true,
      data: makeMockResult(),
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.getByText(/多头.*70分/)).toBeInTheDocument();
      expect(screen.getByText(/空头.*30分/)).toBeInTheDocument();
    });
  });

  it("renders ML prediction when present", async () => {
    const result = makeMockResult({
      ml: { direction: "看涨", confidence: 72, votes: "3/5模型一致", models: {} },
    });
    mockFetchApi.mockResolvedValue({
      success: true,
      data: result,
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.getByText(/AI预测.*看涨/)).toBeInTheDocument();
    });
  });

  it("hides ML prediction when absent", async () => {
    const result = makeMockResult({ ml: undefined });
    mockFetchApi.mockResolvedValue({
      success: true,
      data: result,
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.queryByText(/AI预测/)).not.toBeInTheDocument();
    });
  });

  it("renders pattern analysis section", async () => {
    mockFetchApi.mockResolvedValue({
      success: true,
      data: makeMockResult(),
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.getByTestId("pattern-section")).toBeInTheDocument();
    });
  });

  it("renders manipulator intention section", async () => {
    mockFetchApi.mockResolvedValue({
      success: true,
      data: makeMockResult(),
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.getByTestId("manipulator-section")).toBeInTheDocument();
    });
  });

  it("renders retail psychology and prediction sections", async () => {
    mockFetchApi.mockResolvedValue({
      success: true,
      data: makeMockResult(),
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.getByTestId("psychology-section")).toBeInTheDocument();
      expect(screen.getByTestId("prediction-section")).toBeInTheDocument();
    });
  });

  it("renders operation advice section", async () => {
    mockFetchApi.mockResolvedValue({
      success: true,
      data: makeMockResult(),
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.getByTestId("operation-section")).toBeInTheDocument();
    });
  });

  it("renders combined summary section", async () => {
    mockFetchApi.mockResolvedValue({
      success: true,
      data: makeMockResult(),
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.getByTestId("combined-section")).toBeInTheDocument();
    });
  });

  it("renders risk warnings section", async () => {
    mockFetchApi.mockResolvedValue({
      success: true,
      data: makeMockResult(),
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.getByTestId("risk-section")).toBeInTheDocument();
    });
  });

  it("renders data sources section", async () => {
    mockFetchApi.mockResolvedValue({
      success: true,
      data: makeMockResult(),
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.getByTestId("datasources-section")).toBeInTheDocument();
    });
  });

  it("renders business quality section", async () => {
    mockFetchApi.mockResolvedValue({
      success: true,
      data: makeMockResult(),
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.getByTestId("bq-section")).toBeInTheDocument();
    });
  });

  // ═══════════════════════
  // Optional sections hidden
  // ═══════════════════════
  it("hides section 2 (sector) when sector_analysis is absent", async () => {
    const result = makeMockResult({ sector_analysis: undefined });
    mockFetchApi.mockResolvedValue({
      success: true,
      data: result,
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.queryByTestId("sector-section")).not.toBeInTheDocument();
    });
  });

  it("hides debate section when debate is absent", async () => {
    const result = makeMockResult({ debate: undefined });
    mockFetchApi.mockResolvedValue({
      success: true,
      data: result,
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.queryByText(/多头/)).not.toBeInTheDocument();
    });
  });

  it("hides risk section when no risk_warnings", async () => {
    const result = makeMockResult({ risk_warnings: [] });
    mockFetchApi.mockResolvedValue({
      success: true,
      data: result,
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.queryByTestId("risk-section")).not.toBeInTheDocument();
    });
  });

  it("hides business quality when absent", async () => {
    const result = makeMockResult({ business_quality: undefined });
    mockFetchApi.mockResolvedValue({
      success: true,
      data: result,
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.queryByTestId("bq-section")).not.toBeInTheDocument();
    });
  });

  // ═══════════════════════
  // Factor score rendering
  // ═══════════════════════
  it("renders all factor scores in the quant section", async () => {
    mockFetchApi.mockResolvedValue({
      success: true,
      data: makeMockResult(),
      error: null,
      freshness: "fresh",
      timing_ms: 0,
    });
    renderAtRoute("600519");
    await waitFor(() => {
      expect(screen.getByText("动量")).toBeInTheDocument();
      expect(screen.getByText("技术")).toBeInTheDocument();
      expect(screen.getByText("基本面")).toBeInTheDocument();
      expect(screen.getByText("量能")).toBeInTheDocument();
      expect(screen.getByText("风险")).toBeInTheDocument();
    });
  });
});
