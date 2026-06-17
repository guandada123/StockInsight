import type { PatternAnalysis } from "../../types/api";

export default function PatternSection({ pa }: { pa: PatternAnalysis }) {
  return (
    <div>
      <div className="fs-11 c-dm mb-8">
        趋势阶段: <span className="c-white fw-600">{pa.trend_phase}</span>
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
                  <span className="fs-10 c-dm" style={{ fontWeight: 400 }}>
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
        <div className="fs-12 c-dm text-center p-16">近期没有检测到明显K线形态</div>
      )}
      <div className="verdict-box mt-10">
        <div className="va-reason c-tx fs-12">{pa.summary}</div>
      </div>
      {pa.key_observation && (
        <div className="fs-12 c-tx mt-8" style={{ lineHeight: 1.5 }}>
          {pa.key_observation}
        </div>
      )}
    </div>
  );
}
