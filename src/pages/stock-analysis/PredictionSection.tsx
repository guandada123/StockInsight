import type { PredictionData } from "../../types/api";

export default function PredictionSection({ pred }: { pred: PredictionData }) {
  const dirClass = pred.direction.includes("涨")
    ? "up"
    : pred.direction.includes("跌")
      ? "down"
      : "sideways";

  return (
    <div className="prediction-card">
      <div className={`pred-direction ${dirClass}`}>{pred.direction}</div>
      <div className="fs-10 c-dm mt-4">置信度 {pred.confidence}%</div>
      {pred.price_range && (
        <div className="pred-range">
          预测区间: {pred.price_range.low} ~ {pred.price_range.high}
        </div>
      )}
      {pred.rationale && <div className="pred-reason">{pred.rationale}</div>}
    </div>
  );
}
