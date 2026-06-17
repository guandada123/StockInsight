import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import Portfolio from "./Portfolio";

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

// ── Mock data ──
const mockPortfolioList = {
  success: true,
  data: {
    portfolios: [{ name: "测试组合", count: 2, total_value: 188000 }],
  },
};

const mockPortfolioDetail = {
  success: true,
  data: {
    name: "测试组合",
    holdings: [
      {
        code: "600519",
        name: "贵州茅台",
        shares: 100,
        cost: 1450,
        current_price: 1500,
        market_value: 150000,
        profit_amount: 5000,
        profit_pct: 3.45,
        weight_pct: 50,
      },
      {
        code: "300750",
        name: "宁德时代",
        shares: 200,
        cost: 180,
        current_price: 190,
        market_value: 38000,
        profit_amount: -1000,
        profit_pct: -2.78,
        weight_pct: 50,
      },
    ],
    total_value: 188000,
    total_cost: 181000,
    total_profit: 4000,
    total_profit_pct: 2.21,
    count: 2,
    update_time: "2026-06-18 15:00",
  },
};

const mockOwnedData = {
  success: true,
  data: {
    holdings: [
      { code: "000001", name: "平安银行", shares: 500, cost: 12, current_price: 13, market_value: 6500, profit_amount: 500, profit_pct: 4.17, weight_pct: 100 },
    ],
    total_value: 6500,
    total_cost: 6000,
    total_profit: 500,
    total_profit_pct: 8.33,
    count: 1,
    update_time: "2026-06-18 14:00",
  },
};

function renderPortfolio() {
  return render(
    <MemoryRouter>
      <Portfolio />
    </MemoryRouter>
  );
}

describe("Portfolio", () => {
  beforeEach(() => {
    mockFetchApi.mockReset();
  });

  // ── Loading state ──
  it("shows loading message on initial render", () => {
    // Don't resolve the fetch
    mockFetchApi.mockImplementation(() => new Promise(() => {}));
    renderPortfolio();
    expect(screen.getByText("加载持仓数据...")).toBeInTheDocument();
  });

  // ── Error state: empty portfolio list ──
  it("shows error when portfolio list is empty", async () => {
    mockFetchApi.mockResolvedValue({
      success: true,
      data: { portfolios: [] },
    });
    renderPortfolio();
    await waitFor(() => {
      expect(screen.getByText("暂无持仓组合")).toBeInTheDocument();
    });
    // "从持仓文件加载" appears in both nav bar and error card — check the primary one
    const loadBtns = screen.getAllByText("从持仓文件加载");
    expect(loadBtns.length).toBe(2); // nav icon + error card primary button
  });

  // ── Error state: API returns error on list call ──
  it("shows error when list API call fails", async () => {
    mockFetchApi.mockResolvedValue({ success: false, error: "网络错误" });
    renderPortfolio();
    await waitFor(() => {
      expect(screen.getByText("暂无持仓组合")).toBeInTheDocument();
    });
  });

  // ── Error state: list succeeds but detail fails ──
  it("shows detail API error message when detail fails", async () => {
    mockFetchApi
      .mockResolvedValueOnce(mockPortfolioList)
      .mockResolvedValueOnce({ success: false, error: "API 不可用" });
    renderPortfolio();

    await waitFor(() => {
      // list has data, so detail is called; detail fails → shows error "API 不可用"
      // But the component shows "暂无持仓组合" header in the error card... let me check:
      // Actually, looking at the code: listRes.success=true, portfolios.length>0
      // so it calls detail. detail returns {success:false, error:"API不可用"}.
      // The error card shows: error "API 不可用" + "从持仓文件加载" button
      // BUT: data is null, so the outer card shows the error.
      // Actually the component shows: if error && !data → card with error message
      expect(screen.getByText("API 不可用")).toBeInTheDocument();
    });
    // The "从持仓文件加载" button should still appear
    expect(screen.getAllByText("从持仓文件加载").length).toBe(2);
  });

  // ── Data display: KPI row ──
  it("displays portfolio KPI values when data loaded", async () => {
    mockFetchApi
      .mockResolvedValueOnce(mockPortfolioList)
      .mockResolvedValueOnce(mockPortfolioDetail);
    renderPortfolio();

    await waitFor(() => {
      expect(screen.getByText("测试组合")).toBeInTheDocument();
    });

    expect(screen.getByText("188,000")).toBeInTheDocument(); // 总市值
    expect(screen.getByText("181,000")).toBeInTheDocument(); // 总成本
    expect(screen.getByText("+4,000")).toBeInTheDocument(); // 总盈亏
    expect(screen.getByText("+2.21%")).toBeInTheDocument(); // 收益率
    expect(screen.getByText("2")).toBeInTheDocument(); // 持仓数
    expect(screen.getByText("更新时间: 2026-06-18 15:00")).toBeInTheDocument();
  });

  // ── Data display: holdings table ──
  it("renders holdings table with correct data", async () => {
    mockFetchApi
      .mockResolvedValueOnce(mockPortfolioList)
      .mockResolvedValueOnce(mockPortfolioDetail);
    renderPortfolio();

    await waitFor(() => {
      expect(screen.getByText("贵州茅台")).toBeInTheDocument();
    });

    expect(screen.getByText("100股")).toBeInTheDocument();
    expect(screen.getByText("1500.00")).toBeInTheDocument();
    expect(screen.getByText("150,000")).toBeInTheDocument();
    expect(screen.getByText("宁德时代")).toBeInTheDocument();
    expect(screen.getByText("200股")).toBeInTheDocument();
  });

  // ── Profit color: positive vs negative ──
  it("shows positive profit with positive class and negative with text-red class", async () => {
    mockFetchApi
      .mockResolvedValueOnce(mockPortfolioList)
      .mockResolvedValueOnce(mockPortfolioDetail);
    renderPortfolio();

    await waitFor(() => {
      expect(screen.getByText("+3.45%")).toBeInTheDocument();
    });
    // 贵州茅台 +3.45%
    const positiveEl = screen.getByText("+3.45%");
    expect(positiveEl.className).toContain("positive");

    // 宁德时代 -2.78%
    const negativeEl = screen.getByText("-2.78%");
    const parent = negativeEl.closest("td");
    expect(parent?.className).toContain("text-red");
  });

  // ── "分析" button on each row ──
  it("renders 分析 button for each holding", async () => {
    mockFetchApi
      .mockResolvedValueOnce(mockPortfolioList)
      .mockResolvedValueOnce(mockPortfolioDetail);
    renderPortfolio();

    await waitFor(() => {
      const analysisBtns = screen.getAllByText("分析");
      // There may be multiple "分析" texts — filter for ones in the table
      expect(analysisBtns.length).toBeGreaterThanOrEqual(2);
    });
  });

  // ── Suggestion display ──
  it("displays portfolio suggestion when available", async () => {
    const dataWithSuggestion = {
      ...mockPortfolioDetail,
      data: {
        ...mockPortfolioDetail.data,
        suggestion: "建议分散持仓，降低集中度风险",
      },
    };
    mockFetchApi
      .mockResolvedValueOnce(mockPortfolioList)
      .mockResolvedValueOnce(dataWithSuggestion);
    renderPortfolio();

    await waitFor(() => {
      expect(screen.getByText("建议分散持仓，降低集中度风险")).toBeInTheDocument();
    });
  });

  // ── Interactive buttons exist ──
  it("has refresh and load buttons", async () => {
    mockFetchApi
      .mockResolvedValueOnce(mockPortfolioList)
      .mockResolvedValueOnce(mockPortfolioDetail);
    renderPortfolio();

    await waitFor(() => {
      expect(screen.getByText("刷新")).toBeInTheDocument();
    });
    expect(screen.getByText("从持仓文件加载")).toBeInTheDocument();
  });
});
