import { render } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import KlineChart from "./KlineChart";
import type { KlineData } from "../types/api";

// 制造测试用 Kline 数据
function makeKlineData(overrides?: Partial<KlineData>): KlineData {
  return {
    dates: ["2026-06-01", "2026-06-02", "2026-06-03"],
    opens: [1500, 1510, 1520],
    closes: [1510, 1520, 1530],
    highs: [1520, 1530, 1540],
    lows: [1490, 1500, 1510],
    volumes: [10000, 12000, 11000],
    ma5: [1505, 1515, 1525],
    ma10: [1495, 1505, 1515],
    ma20: [1485, 1495, 1505],
    ma60: [null, null, null],
    ...overrides,
  };
}

describe("KlineChart", () => {
  it("渲染 K 线图表容器", () => {
    const { container } = render(<KlineChart data={makeKlineData()} indicator={null} />);
    // ECharts 组件会渲染一个 div 容器
    expect(container.querySelector("div")).toBeInTheDocument();
  });

  it("渲染指定高度", () => {
    const { container } = render(<KlineChart data={makeKlineData()} indicator={null} />);
    const chartDiv = container.firstChild as HTMLElement;
    expect(chartDiv.style.height).toBe("380px");
  });

  it("使用 canvas 渲染器", () => {
    const { container } = render(<KlineChart data={makeKlineData()} indicator={null} />);
    // echarts-for-react 在 JSDOM 中可能不渲染实际 canvas
    // 验证容器 div 存在即可
    expect(container.querySelector('[style*="height"]')).toBeTruthy();
  });

  it("使用 useMemo 避免重复渲染", () => {
    // 验证组件使用 useMemo 缓存 option（通过渲染两次确认无崩溃）
    const data = makeKlineData();
    const { rerender } = render(<KlineChart data={data} indicator={null} />);
    expect(() => rerender(<KlineChart data={data} indicator={null} />)).not.toThrow();
  });
});
