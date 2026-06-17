import type { ManipulatorIntention } from "../../types/api";

export default function ManipulatorSection({ mi }: { mi: ManipulatorIntention }) {
  const phaseClass =
    mi.phase === "建仓"
      ? "accumulation"
      : mi.phase === "洗盘"
        ? "washout"
        : mi.phase === "拉升"
          ? "uptrend"
          : mi.phase === "出货"
            ? "distribution"
            : "unknown";

  return (
    <div>
      <div className="phase-card">
        <div className={`phase-label ${phaseClass}`}>{mi.phase}</div>
        <div className="phase-confidence">判断置信度: {mi.phase_confidence}%</div>
      </div>

      {mi.signals && mi.signals.length > 0 && (
        <div className="phase-signals">
          {mi.signals.map((s, i) => (
            <div key={i} className="phase-signal">
              • {s}
            </div>
          ))}
        </div>
      )}

      {mi.volume_analysis && (
        <div className="fs-11 c-tx mt-8" style={{ lineHeight: 1.5 }}>
          {mi.volume_analysis}
        </div>
      )}
      {mi.chip_analysis && (
        <div className="fs-11 c-tx mt-4" style={{ lineHeight: 1.5 }}>
          {mi.chip_analysis}
        </div>
      )}

      <div
        style={{
          fontSize: 12,
          color: "var(--tx)",
          marginTop: 10,
          lineHeight: 1.7,
          background: "#070d18",
          padding: 12,
          borderRadius: 6,
        }}
      >
        {mi.assessment}
      </div>

      {mi.risk_note && (
        <div className="fs-11 c-gd mt-8" style={{ lineHeight: 1.5 }}>
          ⚠ {mi.risk_note}
        </div>
      )}
    </div>
  );
}
