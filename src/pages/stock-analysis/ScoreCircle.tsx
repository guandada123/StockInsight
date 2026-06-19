export default function ScoreCircle({ score }: { score: number }) {
  const color = score >= 65 ? "#22c55e" : score >= 45 ? "#f59e0b" : "#ef4444";
  return (
    <div className="score-circle" style={{ borderColor: color }}>
      <div className="sc-num">{score}</div>
      <div className="sc-sub">/100</div>
    </div>
  );
}
