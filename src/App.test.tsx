import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import App from "./App";

// ── Mock child components ──
vi.mock("./pages/Dashboard", () => ({
  default: ({ onSearch }: { onSearch: () => void }) => (
    <div data-testid="dashboard">
      Dashboard <button onClick={onSearch}>分析</button>
    </div>
  ),
}));
vi.mock("./pages/StockAnalysis", () => ({
  default: () => <div data-testid="stock-analysis">StockAnalysis</div>,
}));
vi.mock("./pages/Portfolio", () => ({
  default: () => <div data-testid="portfolio">Portfolio</div>,
}));
vi.mock("./pages/Settings", () => ({
  default: () => <div data-testid="settings">Settings</div>,
}));
vi.mock("./components/ErrorBoundary", () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// ── Mock fetch for health check ──
const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

function renderApp(initialEntries = ["/"]) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <App />
    </MemoryRouter>
  );
}

describe("App", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    localStorage.clear();
  });

  // ── Loading state ──
  it("shows loading state while API health check is pending", () => {
    mockFetch.mockImplementation(() => new Promise(() => {})); // never resolves
    renderApp();
    expect(screen.getByText("正在启动 Python 分析引擎...")).toBeInTheDocument();
    // "StockInsight Pro" spans multiple DOM nodes — verify the loading screen container
    const loadingContainer = document.querySelector('[style*="height: 100vh"]');
    expect(loadingContainer).toBeInTheDocument();
    // The pulse animation bar indicates loading state
    expect(document.querySelector('[style*="animation: pulse"]')).toBeInTheDocument();
    // Should not show navigation or content yet
    expect(screen.queryByText("仪表盘")).not.toBeInTheDocument();
  });

  // ── Ready state: navigation renders ──
  it("renders navigation tabs after API is ready", async () => {
    mockFetch.mockResolvedValue({ ok: true });
    renderApp();
    await waitFor(() => {
      expect(screen.getByText("仪表盘")).toBeInTheDocument();
    });
    expect(screen.getByText("持仓")).toBeInTheDocument();
    expect(screen.getByText("设置")).toBeInTheDocument();
  });

  // ── Ready state: version label ──
  it("shows version label after API is ready", async () => {
    mockFetch.mockResolvedValue({ ok: true });
    renderApp();
    await waitFor(() => {
      expect(screen.getByText("v1.0 MVP")).toBeInTheDocument();
    });
  });

  // ── Search functionality ──
  it("navigates to stock page on valid search code", async () => {
    mockFetch.mockResolvedValue({ ok: true });
    renderApp();

    await waitFor(() => {
      expect(screen.getByPlaceholderText("输入股票代码 如 600519")).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText("输入股票代码 如 600519");
    // There are two "分析" buttons: nav search + Dashboard mock → pick the nav one
    const searchBtns = screen.getAllByText("分析");
    const searchBtn = searchBtns[0]; // first one is the nav search button

    // 输入无效代码（少于6位）
    fireEvent.change(input, { target: { value: "600" } });
    fireEvent.click(searchBtn);
    // 不应导航 — 仍在首页
    expect(screen.getByTestId("dashboard")).toBeInTheDocument();

    // 输入有效代码
    fireEvent.change(input, { target: { value: "600519" } });
    fireEvent.click(searchBtn);
    // 应导航到 /stock/600519
    await waitFor(() => {
      expect(screen.getByTestId("stock-analysis")).toBeInTheDocument();
    });
  });

  it("triggers search on Enter key", async () => {
    mockFetch.mockResolvedValue({ ok: true });
    renderApp();

    await waitFor(() => {
      expect(screen.getByPlaceholderText("输入股票代码 如 600519")).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText("输入股票代码 如 600519");
    fireEvent.change(input, { target: { value: "300750" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => {
      expect(screen.getByTestId("stock-analysis")).toBeInTheDocument();
    });
  });

  // ── Route: Dashboard (/) ──
  it("renders Dashboard at root route", async () => {
    mockFetch.mockResolvedValue({ ok: true });
    renderApp(["/"]);
    await waitFor(() => {
      expect(screen.getByTestId("dashboard")).toBeInTheDocument();
    });
  });

  // ── Route: Stock (/stock/:code) ──
  it("renders StockAnalysis at /stock/:code route", async () => {
    mockFetch.mockResolvedValue({ ok: true });
    renderApp(["/stock/600519"]);
    await waitFor(() => {
      expect(screen.getByTestId("stock-analysis")).toBeInTheDocument();
    });
  });

  // ── Route: Portfolio ──
  it("renders Portfolio at /portfolio route", async () => {
    mockFetch.mockResolvedValue({ ok: true });
    renderApp(["/portfolio"]);
    await waitFor(() => {
      expect(screen.getByTestId("portfolio")).toBeInTheDocument();
    });
  });

  // ── Route: Settings ──
  it("renders Settings at /settings route", async () => {
    mockFetch.mockResolvedValue({ ok: true });
    renderApp(["/settings"]);
    await waitFor(() => {
      expect(screen.getByTestId("settings")).toBeInTheDocument();
    });
  });

  // ── Sidebar: default watchlist ──
  it("renders default watchlist in Sidebar", async () => {
    mockFetch.mockResolvedValue({ ok: true });
    renderApp();
    await waitFor(() => {
      expect(screen.getByText("自选股")).toBeInTheDocument();
    });
    expect(screen.getByText("茅台")).toBeInTheDocument();
    expect(screen.getByText("宁德时代")).toBeInTheDocument();
    expect(screen.getByText("比亚迪")).toBeInTheDocument();
    expect(screen.getByText("招商银行")).toBeInTheDocument();
    expect(screen.getByText("中际旭创")).toBeInTheDocument();
  });

  // ── Sidebar: remove stock from watchlist ──
  it("removes a stock from watchlist on click ×", async () => {
    mockFetch.mockResolvedValue({ ok: true });
    renderApp();
    await waitFor(() => {
      expect(screen.getByText("茅台")).toBeInTheDocument();
    });

    // 每个 wl-item 都有一个 × 按钮
    const removeButtons = screen.getAllByTitle("删除");
    expect(removeButtons.length).toBe(5);

    // 移除第一个（茅台）
    fireEvent.click(removeButtons[0]);
    expect(screen.queryByText("茅台")).not.toBeInTheDocument();
    expect(screen.getByText("宁德时代")).toBeInTheDocument(); // 其余仍在
  });

  // ── Sidebar: empty watchlist message ──
  it("shows empty message when all stocks removed", async () => {
    mockFetch.mockResolvedValue({ ok: true });
    renderApp();
    await waitFor(() => {
      expect(screen.getByText("自选股")).toBeInTheDocument();
    });

    // 移除全部 5 个 — use getAllByTitle since there are multiple
    const removeButtons = screen.getAllByTitle("删除");
    expect(removeButtons.length).toBe(5);
    removeButtons.forEach((btn) => fireEvent.click(btn));

    await waitFor(() => {
      expect(screen.getByText("暂无自选股，在个股页点击右上角添加")).toBeInTheDocument();
    });
  });

  // ── Sidebar: click stock navigates ──
  it("navigates to stock page on clicking a watchlist item", async () => {
    mockFetch.mockResolvedValue({ ok: true });
    renderApp();
    await waitFor(() => {
      expect(screen.getByText("茅台")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("茅台"));
    await waitFor(() => {
      expect(screen.getByTestId("stock-analysis")).toBeInTheDocument();
    });
  });

  // ── Nav: click tabs navigate ──
  it("navigates to portfolio page when clicking 持仓 tab", async () => {
    mockFetch.mockResolvedValue({ ok: true });
    renderApp(["/"]);
    await waitFor(() => {
      expect(screen.getByTestId("dashboard")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("持仓"));
    await waitFor(() => {
      expect(screen.getByTestId("portfolio")).toBeInTheDocument();
    });
  });

  it("navigates to settings page when clicking 设置 tab", async () => {
    mockFetch.mockResolvedValue({ ok: true });
    renderApp(["/"]);
    await waitFor(() => {
      expect(screen.getByTestId("dashboard")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("设置"));
    await waitFor(() => {
      expect(screen.getByTestId("settings")).toBeInTheDocument();
    });
  });

  // ── Footer ──
  it("renders footer after API is ready", async () => {
    mockFetch.mockResolvedValue({ ok: true });
    renderApp();
    await waitFor(() => {
      expect(screen.getByText(/数据来源/)).toBeInTheDocument();
    });
    expect(screen.getByText(/免责声明/)).toBeInTheDocument();
  });

  // ── Logo click navigates home ──
  it("navigates to root when clicking logo", async () => {
    mockFetch.mockResolvedValue({ ok: true });
    const { container } = renderApp(["/portfolio"]);
    await waitFor(() => {
      expect(screen.getByTestId("portfolio")).toBeInTheDocument();
    });

    // nav-logo contains "Stock" and "Insight" in separate nodes — query by class
    const logo = container.querySelector(".nav-logo");
    expect(logo).toBeInTheDocument();
    fireEvent.click(logo!);
    await waitFor(() => {
      expect(screen.getByTestId("dashboard")).toBeInTheDocument();
    });
  });
});
