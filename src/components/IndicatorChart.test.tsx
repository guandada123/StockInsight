import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import IndicatorChart from "./IndicatorChart";
import type { IndicatorData } from "../types/api";

// ── Mock ECharts ──
vi.mock("echarts-for-react", () => ({
  default: ({ option }: { option: Record<string, unknown> }) => (
    <div data-testid="echart" data-option={JSON.stringify(option)} />
  ),
}));

const mockData: IndicatorData = {
  dates: ["2026-06-01", "2026-06-02", "2026-06-03"],
  values: {
    dif: [0.5, 0.6, 0.7],
    dea: [0.4, 0.5, 0.55],
    macd_bar: [0.1, 0.1, 0.15],
  },
};

const onTypeChange = vi.fn();

function renderChart(type = "macd") {
  return render(
    <IndicatorChart data={mockData} type={type} onTypeChange={onTypeChange} />
  );
}

describe("IndicatorChart", () => {
  beforeEach(() => {
    onTypeChange.mockReset();
  });

  // ── Renders type selector buttons ──
  it("renders MACD, RSI, KDJ buttons", () => {
    renderChart();
    expect(screen.getByText("MACD")).toBeInTheDocument();
    expect(screen.getByText("RSI")).toBeInTheDocument();
    expect(screen.getByText("KDJ")).toBeInTheDocument();
  });

  // ── Highlights active type button ──
  it("highlights the active type button", () => {
    renderChart("rsi");
    const rsiBtn = screen.getByText("RSI");
    expect(rsiBtn.className).toContain("active");
    const macdBtn = screen.getByText("MACD");
    expect(macdBtn.className).not.toContain("active");
  });

  // ── Calls onTypeChange on button click ──
  it("calls onTypeChange when clicking RSI button", () => {
    renderChart();
    fireEvent.click(screen.getByText("RSI"));
    expect(onTypeChange).toHaveBeenCalledWith("rsi");
  });

  it("calls onTypeChange when clicking KDJ button", () => {
    renderChart();
    fireEvent.click(screen.getByText("KDJ"));
    expect(onTypeChange).toHaveBeenCalledWith("kdj");
  });

  it("calls onTypeChange when clicking MACD button (even if already active)", () => {
    renderChart("macd");
    fireEvent.click(screen.getByText("MACD"));
    expect(onTypeChange).toHaveBeenCalledWith("macd");
  });

  // ── Renders ECharts component ──
  it("renders the ECharts chart component", () => {
    renderChart();
    expect(screen.getByTestId("echart")).toBeInTheDocument();
  });

  // ── Chart option has correct data ──
  it("passes correct data to ECharts option", () => {
    renderChart();
    const echart = screen.getByTestId("echart");
    const option = JSON.parse(echart.getAttribute("data-option") || "{}");

    expect(option.xAxis.data).toEqual(mockData.dates);
    expect(option.series.length).toBe(3);
    expect(option.series[0].name).toBe("dif");
    expect(option.series[1].name).toBe("dea");
    expect(option.series[2].name).toBe("macd_bar");
  });

  // ── Chart option: dark background ──
  it("uses dark theme background color", () => {
    renderChart();
    const echart = screen.getByTestId("echart");
    const option = JSON.parse(echart.getAttribute("data-option") || "{}");

    expect(option.backgroundColor).toBe("#0d1422");
  });

  // ── Chart option: line series with no symbols ──
  it("renders line series with no symbols", () => {
    renderChart();
    const echart = screen.getByTestId("echart");
    const option = JSON.parse(echart.getAttribute("data-option") || "{}");

    option.series.forEach((s: Record<string, unknown>) => {
      expect(s.type).toBe("line");
      expect(s.symbol).toBe("none");
    });
  });
});
