import type { StockAnalysisResult } from "../types/api";

export default function StockQuote({
  result,
  code,
}: {
  result: StockAnalysisResult;
  code: string;
}) {
  const q = result.quote;
  const changePct = q.change_pct;
  const isUp = changePct >= 0;
  const color = isUp ? "#ef4444" : "#22c55e";

  return (
    <div className="card">
      <div className="card-header">
        {result.name} ({code}) · {result.sector_analysis?.industry || result.technical?.ma_status}
        <span style={{ float: "right", fontSize: 11, color: "var(--dm)" }}>
          {result.time}
        </span>
      </div>
      <div className="card-body">
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 28, fontWeight: 700, color }}>
              {q.price.toFixed(2)}
            </div>
            <div style={{ color, fontSize: 13 }}>
              {isUp ? "+" : ""}
              {q.change.toFixed(2)} ({isUp ? "+" : ""}
              {changePct.toFixed(2)}%)
            </div>
          </div>
          <div style={{ fontSize: 12, color: "var(--dm)", lineHeight: 1.8 }}>
            今开 {q.open.toFixed(2)} · 最高 {q.high.toFixed(2)} · 最低{" "}
            {q.low.toFixed(2)} · 昨收 {q.prev_close.toFixed(2)} · 振幅{" "}
            {q.amplitude.toFixed(2)}%
          </div>
        </div>
      </div>
    </div>
  );
}
