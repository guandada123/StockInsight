import type { RetailPsychology } from "../../types/api";

export default function PsychologySection({ rp }: { rp: RetailPsychology }) {
  const emotionClass =
    rp.emotion === "贪婪" || rp.emotion === "追涨"
      ? "greed"
      : rp.emotion === "恐惧" || rp.emotion === "恐慌抛售"
        ? "fear"
        : rp.emotion === "犹豫观望"
          ? "hesitation"
          : rp.emotion.includes("恐慌")
            ? "panic"
            : "unknown";

  return (
    <div>
      <div className="emotion-display">
        <div className={`emotion-label ${emotionClass}`}>{rp.emotion}</div>
        <div className="fs-10 c-dm mt-4">情绪强度: {rp.emotion_score}/100</div>
        <div className="emotion-desc">{rp.behavior_pattern}</div>
      </div>
      {rp.sentiment_indicators && rp.sentiment_indicators.length > 0 && (
        <div className="mt-8">
          {rp.sentiment_indicators.map((s, i) => (
            <div
              key={i}
              style={{
                fontSize: 11,
                color: "var(--tx)",
                padding: "3px 0",
                borderBottom: "1px solid #121a2a",
              }}
            >
              • {s}
            </div>
          ))}
        </div>
      )}
      {rp.advice && <div className="emotion-advice">{rp.advice}</div>}
    </div>
  );
}
