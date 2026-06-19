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
        <span className="fs-11 c-dm" style={{ float: "right" }}>
          {result.time}
        </span>
      </div>
      <div className="card-body">
        <div className="flex gap-24 flex-wrap">
          <div>
            <div className="fs-28 fw-700" style={{ color }}>
              {q.price.toFixed(2)}
            </div>
            <div className="fs-13" style={{ color }}>
              {isUp ? "+" : ""}
              {q.change.toFixed(2)} ({isUp ? "+" : ""}
              {changePct.toFixed(2)}%)
            </div>
          </div>
          <div className="fs-12 c-dm" style={{ lineHeight: 1.8 }}>
            今开 {q.open.toFixed(2)} · 最高 {q.high.toFixed(2)} · 最低 {q.low.toFixed(2)} · 昨收{" "}
            {q.prev_close.toFixed(2)} · 振幅 {q.amplitude.toFixed(2)}%
          </div>
        </div>
      </div>
    </div>
  );
}
