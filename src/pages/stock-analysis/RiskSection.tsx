import type { RiskWarning } from "../../types/api";

export default function RiskSection({ risks }: { risks: RiskWarning[] }) {
  return (
    <div className="risk-list">
      {risks.map((r, i) => (
        <div key={i} className={`risk-item ${r.level}`}>
          <div className="risk-icon">
            {r.level === "high"
              ? "🔴"
              : r.level === "medium"
                ? "🟡"
                : r.level === "low"
                  ? "🟢"
                  : "🔵"}
          </div>
          <div>{r.message}</div>
        </div>
      ))}
    </div>
  );
}
