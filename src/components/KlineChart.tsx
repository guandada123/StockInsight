import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import type { KlineData, IndicatorData } from "../types/api";

export default function KlineChart({
  data,
  indicator: _indicator,
}: {
  data: KlineData;
  indicator: IndicatorData | null;
}) {
  const dates = data.dates;
  const ohlc = dates.map((_d, i) => [data.opens[i], data.closes[i], data.lows[i], data.highs[i]]);

  const option = useMemo(() => ({
    backgroundColor: "#0d1422",
    grid: [
      { left: "8%", right: "3%", top: "5%", height: "55%" },
      { left: "8%", right: "3%", top: "68%", height: "20%" },
    ],
    xAxis: [
      {
        type: "category",
        data: dates,
        gridIndex: 0,
        axisLine: { lineStyle: { color: "#1a2740" } },
        axisLabel: {
          color: "#5a6e8a",
          fontSize: 10,
          formatter: (v: string) => v.slice(5),
        },
      },
      {
        type: "category",
        data: dates,
        gridIndex: 1,
        axisLine: { lineStyle: { color: "#1a2740" } },
        axisLabel: { show: false },
      },
    ],
    yAxis: [
      {
        type: "value",
        gridIndex: 0,
        scale: true,
        axisLabel: { color: "#5a6e8a", fontSize: 10 },
        splitLine: { lineStyle: { color: "#1a2740", type: "dashed" } },
      },
      { type: "value", gridIndex: 1, axisLabel: { color: "#5a6e8a", fontSize: 9 } },
    ],
    series: [
      {
        type: "candlestick",
        data: ohlc,
        xAxisIndex: 0,
        yAxisIndex: 0,
        itemStyle: {
          color: "#ef4444",
          color0: "#22c55e",
          borderColor: "#ef4444",
          borderColor0: "#22c55e",
        },
      },
      {
        type: "line",
        data: data.ma5,
        xAxisIndex: 0,
        yAxisIndex: 0,
        symbol: "none",
        lineStyle: { color: "#f59e0b", width: 1 },
      },
      {
        type: "line",
        data: data.ma10,
        xAxisIndex: 0,
        yAxisIndex: 0,
        symbol: "none",
        lineStyle: { color: "#06b6d4", width: 1 },
      },
      {
        type: "line",
        data: data.ma20,
        xAxisIndex: 0,
        yAxisIndex: 0,
        symbol: "none",
        lineStyle: { color: "#a855f7", width: 1 },
      },
      {
        type: "bar",
        data: data.volumes.map((v, i) => [i, v, data.closes[i] >= data.opens[i] ? 1 : -1]),
        xAxisIndex: 1,
        yAxisIndex: 1,
        itemStyle: {
          color: (params: { data: number[] | undefined }) =>
            (params.data ? params.data[2] : 0) > 0 ? "#ef4444" : "#22c55e",
        },
      },
    ],
  }), [data]);

  return <ReactECharts option={option} style={{ height: 380 }} opts={{ renderer: "canvas" }} />;
}
