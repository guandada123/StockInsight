import ReactECharts from "echarts-for-react";
import type { IndicatorData } from "../types/api";

export default function IndicatorChart({
  data,
  type,
  onTypeChange,
}: {
  data: IndicatorData;
  type: string;
  onTypeChange: (t: string) => void;
}) {
  const types = [
    { key: "macd", label: "MACD" },
    { key: "rsi", label: "RSI" },
    { key: "kdj", label: "KDJ" },
  ];

  const option = {
    backgroundColor: "#0d1422",
    grid: { left: "8%", right: "3%", top: "10%", bottom: "10%" },
    xAxis: {
      type: "category",
      data: data.dates,
      axisLine: { lineStyle: { color: "#1a2740" } },
      axisLabel: { color: "#5a6e8a", fontSize: 10 },
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLabel: { color: "#5a6e8a", fontSize: 10 },
      splitLine: { lineStyle: { color: "#1a2740", type: "dashed" } },
    },
    series: Object.entries(data.values).map(([name, vals]) => ({
      name,
      type: "line",
      data: vals,
      symbol: "none",
      lineStyle: { width: 1 },
    })),
    legend: { textStyle: { color: "#bac8dc" } },
  };

  return (
    <div className="card">
      <div className="card-header" style={{ display: "flex", gap: 8 }}>
        {types.map((t) => (
          <button
            key={t.key}
            className={`segmented-btn ${type === t.key ? "active" : ""}`}
            onClick={() => onTypeChange(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        <ReactECharts
          option={option}
          style={{ height: 220 }}
          opts={{ renderer: "canvas" }}
        />
      </div>
    </div>
  );
}
