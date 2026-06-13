import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import Dashboard from "./Dashboard";

const mockFetch = vi.fn();
global.fetch = mockFetch;

const mockSetIndices = vi.fn();

vi.mock("../store", () => ({
  useMarketStore: () => ({
    indices: {},
    setIndices: mockSetIndices,
  }),
}));

function renderDashboard() {
  return render(
    <MemoryRouter>
      <Dashboard onSearch={() => {}} />
    </MemoryRouter>
  );
}

describe("Dashboard", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockSetIndices.mockReset();
    mockFetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          success: true,
          data: { indices: {}, sectors: [] },
        }),
    });
  });

  it("renders market overview section", () => {
    renderDashboard();
    expect(screen.getByText("市场总览")).toBeInTheDocument();
  });

  it("renders hot sectors section", () => {
    renderDashboard();
    expect(screen.getByText("板块热点 TOP12")).toBeInTheDocument();
  });

  it("renders quick analysis input", () => {
    renderDashboard();
    expect(screen.getByPlaceholderText(/600519/)).toBeInTheDocument();
  });

  it("renders start analysis button", () => {
    renderDashboard();
    expect(screen.getByRole("button", { name: "开始分析" })).toBeInTheDocument();
  });

  it("shows loading state initially", () => {
    renderDashboard();
    expect(screen.getByText("市场总览")).toBeInTheDocument();
  });

  it("calls fetch on mount", async () => {
    renderDashboard();
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });

  it("shows error message on fetch failure", async () => {
    mockFetch.mockRejectedValue(new Error("Network error"));
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText(/加载失败/)).toBeInTheDocument();
    }, { timeout: 5000 });
  });
});
