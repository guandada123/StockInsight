import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

// ── Mock useApi ──
const mockFetchApi = vi.fn();
const mockRequest = vi.fn();

vi.mock("../hooks/useApi", () => ({
  useApi: () => ({
    fetchApi: mockFetchApi,
    request: mockRequest,
    loading: false,
    data: null,
    error: null,
  }),
}));

// ── Import AFTER mock ──
import Settings from "./Settings";

const JOB_LIST_URL = "/api/data-jobs/list?limit=20";
const FACTOR_LIST_URL = "/api/factors/list";

const EMPTY_JOBS = { success: true, data: { jobs: [] }, error: null };
const EMPTY_FACTORS = { success: true, data: { factors: [] }, error: null };

function makeDefaultMock() {
  return vi.fn((url: string) => {
    if (url === JOB_LIST_URL) return Promise.resolve(EMPTY_JOBS);
    if (url === FACTOR_LIST_URL) return Promise.resolve(EMPTY_FACTORS);
    return Promise.resolve({ success: true, data: null, error: null });
  });
}

describe("Settings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: both API calls return empty lists
    mockFetchApi.mockImplementation(makeDefaultMock());
    mockRequest.mockResolvedValue({ success: true, data: null, error: null });
  });

  // ══════════════════════════════════
  // General
  // ══════════════════════════════════
  it("renders the page title", () => {
    render(<Settings />);
    expect(screen.getByText("系统设置")).toBeInTheDocument();
  });

  it("shows all three tab buttons", () => {
    render(<Settings />);
    expect(screen.getByText("数据管理")).toBeInTheDocument();
    expect(screen.getByText("因子管理")).toBeInTheDocument();
    expect(screen.getByText("关于")).toBeInTheDocument();
  });

  it("defaults to data management tab", () => {
    render(<Settings />);
    const dataTab = screen.getByText("数据管理");
    expect(dataTab.className).toContain("active");
  });

  it("switches to factor management tab on click", () => {
    render(<Settings />);
    fireEvent.click(screen.getByText("因子管理"));
    expect(screen.getByText("因子管理").className).toContain("active");
    expect(screen.getByText("数据管理").className).not.toContain("active");
  });

  it("switches to about tab on click", () => {
    render(<Settings />);
    fireEvent.click(screen.getByText("关于"));
    expect(screen.getByText("关于").className).toContain("active");
  });

  // ══════════════════════════════════
  // DataManagement tab
  // ══════════════════════════════════
  it("shows job type buttons in data tab", () => {
    render(<Settings />);
    expect(screen.getByText("交易日历")).toBeInTheDocument();
    expect(screen.getByText("股票列表")).toBeInTheDocument();
    expect(screen.getByText("日线历史")).toBeInTheDocument();
    expect(screen.getByText("基本面数据")).toBeInTheDocument();
  });

  it("shows download buttons for each job type", () => {
    render(<Settings />);
    const downloadButtons = screen.getAllByText("下载");
    expect(downloadButtons).toHaveLength(4);
  });

  it("shows empty job list placeholder", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByText("暂无任务")).toBeInTheDocument();
    });
  });

  it("renders job items from API", async () => {
    mockFetchApi.mockImplementation((url: string) => {
      if (url === JOB_LIST_URL) {
        return Promise.resolve({
          success: true,
          data: {
            jobs: [
              {
                id: "1",
                name: "trade_calendar",
                status: "done",
                progress: 100,
                total: 100,
                started: "2026-06-18 08:00",
                done: "2026-06-18 08:05",
              },
              {
                id: "2",
                name: "stock_basic",
                status: "running",
                progress: 50,
                total: 100,
                started: "2026-06-18 08:10",
                done: null,
              },
              {
                id: "3",
                name: "daily_history",
                status: "failed",
                progress: 30,
                total: 100,
                started: "2026-06-18 07:00",
                done: null,
              },
              {
                id: "4",
                name: "daily_basic",
                status: "pending",
                progress: 0,
                total: 0,
                started: "",
                done: null,
              },
            ],
          },
          error: null,
        });
      }
      if (url === FACTOR_LIST_URL) return Promise.resolve(EMPTY_FACTORS);
      return Promise.resolve({ success: true, data: null });
    });
    render(<Settings />);
    await waitFor(() => {
      // "完成" appears both in table header and job status tag
      expect(screen.getAllByText("完成").length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("运行中")).toBeInTheDocument();
      expect(screen.getByText("失败")).toBeInTheDocument();
      expect(screen.getByText("等待")).toBeInTheDocument();
    });
  });

  it("shows refresh button", () => {
    render(<Settings />);
    expect(screen.getByText("刷新")).toBeInTheDocument();
  });

  it("shows data source configuration hint", () => {
    render(<Settings />);
    expect(screen.getByText(/TUSHARE_TOKEN/)).toBeInTheDocument();
  });

  // ══════════════════════════════════
  // FactorManagement tab
  // ══════════════════════════════════
  it("shows empty factor placeholder", async () => {
    render(<Settings />);
    fireEvent.click(screen.getByText("因子管理"));
    await waitFor(() => {
      expect(screen.getByText("暂无自定义因子")).toBeInTheDocument();
    });
  });

  it("renders factor items from API", async () => {
    mockFetchApi.mockImplementation((url: string) => {
      if (url === JOB_LIST_URL) return Promise.resolve(EMPTY_JOBS);
      if (url === FACTOR_LIST_URL) {
        return Promise.resolve({
          success: true,
          data: {
            factors: [
              {
                id: "ma_cross",
                name: "均线金叉",
                expression: "ma5 > ma20",
                type: "technical",
                created: "2026-06-01",
              },
              {
                id: "volume_ratio",
                name: "量比",
                expression: "vol / avg_vol_20",
                type: "volume",
                created: "2026-06-10",
              },
            ],
          },
          error: null,
        });
      }
      return Promise.resolve({ success: true, data: null });
    });
    render(<Settings />);
    fireEvent.click(screen.getByText("因子管理"));
    await waitFor(() => {
      expect(screen.getByText("均线金叉")).toBeInTheDocument();
      expect(screen.getByText("量比")).toBeInTheDocument();
    });
  });

  it("shows create form on clicking + 新建", () => {
    render(<Settings />);
    fireEvent.click(screen.getByText("因子管理"));
    fireEvent.click(screen.getByText("+ 新建"));
    expect(screen.getByText("创建因子")).toBeInTheDocument();
  });

  it("shows expression examples", () => {
    render(<Settings />);
    fireEvent.click(screen.getByText("因子管理"));
    expect(screen.getByText("表达式示例:")).toBeInTheDocument();
  });

  it("shows delete buttons for each factor", async () => {
    mockFetchApi.mockImplementation((url: string) => {
      if (url === JOB_LIST_URL) return Promise.resolve(EMPTY_JOBS);
      if (url === FACTOR_LIST_URL) {
        return Promise.resolve({
          success: true,
          data: {
            factors: [
              {
                id: "ma_cross",
                name: "均线金叉",
                expression: "ma5 > ma20",
                type: "technical",
                created: "2026-06-01",
              },
              {
                id: "volume_ratio",
                name: "量比",
                expression: "vol / avg_vol_20",
                type: "volume",
                created: "2026-06-10",
              },
            ],
          },
          error: null,
        });
      }
      return Promise.resolve({ success: true, data: null });
    });
    render(<Settings />);
    fireEvent.click(screen.getByText("因子管理"));
    await waitFor(() => {
      const deleteBtns = screen.getAllByText("删除");
      expect(deleteBtns).toHaveLength(2);
    });
  });

  it("calls window.confirm on delete click", async () => {
    mockFetchApi.mockImplementation((url: string) => {
      if (url === JOB_LIST_URL) return Promise.resolve(EMPTY_JOBS);
      if (url === FACTOR_LIST_URL) {
        return Promise.resolve({
          success: true,
          data: {
            factors: [
              {
                id: "ma_cross",
                name: "均线金叉",
                expression: "ma5 > ma20",
                type: "technical",
                created: "2026-06-01",
              },
            ],
          },
          error: null,
        });
      }
      return Promise.resolve({ success: true, data: null });
    });
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<Settings />);
    fireEvent.click(screen.getByText("因子管理"));
    await waitFor(() => {
      const deleteBtns = screen.getAllByText("删除");
      fireEvent.click(deleteBtns[0]);
    });
    expect(confirmSpy).toHaveBeenCalledWith("确定要永久删除此因子吗？此操作不可撤销。");
    confirmSpy.mockRestore();
  });

  // ══════════════════════════════════
  // About tab
  // ══════════════════════════════════
  it("renders about tab with version info", () => {
    render(<Settings />);
    fireEvent.click(screen.getByText("关于"));
    expect(screen.getByText("关于 StockInsight Pro")).toBeInTheDocument();
    expect(screen.getByText("1.0.0")).toBeInTheDocument();
    expect(screen.getByText("Tauri + React + FastAPI")).toBeInTheDocument();
    expect(screen.getByText(/新浪\/东方财富\/akshare\/Tushare/)).toBeInTheDocument();
    expect(screen.getByText("SQLite 152MB")).toBeInTheDocument();
  });

  it("renders disclaimer in about tab", () => {
    render(<Settings />);
    fireEvent.click(screen.getByText("关于"));
    expect(screen.getByText(/本系统仅供学习研究/)).toBeInTheDocument();
  });
});
