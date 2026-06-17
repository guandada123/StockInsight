import type { PatternAnalysis } from "../../types/api";

export default function PatternSection({ pa }: { pa: PatternAnalysis }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: "var(--dm)", marginBottom: 8 }}>
        趋势阶段: <span style={{ color: "#fff", fontWeight: 600 }}>{pa.trend_phase}</span>
      </div>
      {pa.recent_patterns && pa.recent_patterns.length > 0 ? (
        <div className="pattern-list">
          {pa.recent_patterns.map((p, i) => (
            <div key={i} className={`pattern-item ${p.type}`}>
              <div className="pattern-icon">
                {p.type === "bullish" ? "▲" : p.type === "bearish" ? "▼" : "—"}
              </div>
              <div className="pattern-body">
                <div className="pattern-name">
                  {p.name}{" "}
                  <span style={{ fontSize: 10, color: "var(--dm)", fontWeight: 400 }}>
                    {p.date}
                  </span>
                </div>
                <div className="pattern-desc">{p.description}</div>
                <div className="pattern-meta">可靠性: {p.reliability}</div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ fontSize: 12, color: "var(--dm)", textAlign: "center", padding: 16 }}>
          近期没有检测到明显K线形态
        </div>
      )}
      <div className="verdict-box" style={{ marginTop: 10 }}>
        <div className="va-reason" style={{ color: "var(--tx)", fontSize: 12 }}>
          {pa.summary}
        </div>
      </div>
      {pa.key_observation && (
        <div style={{ fontSize: 12, color: "var(--tx)", marginTop: 8, lineHeight: 1.5 }}>
          {pa.key_observation}
        </div>
      )}
    </div>
  );
}
