import type { CombinedSummary } from "../../types/api";

export default function CombinedSection({ cs }: { cs: CombinedSummary }) {
  return (
    <div className="combined-block">
      {cs.kline_summary && (
        <div className="combined-row">
          <div className="combined-label">K线语言</div>
          <div className="combined-text">{cs.kline_summary}</div>
        </div>
      )}
      {cs.manipulator_summary && (
        <div className="combined-row">
          <div className="combined-label">庄家语言</div>
          <div className="combined-text">{cs.manipulator_summary}</div>
        </div>
      )}
      {cs.synergy_assessment && (
        <div className="combined-row">
          <div className="combined-label">联动判断</div>
          <div className="combined-text">{cs.synergy_assessment}</div>
        </div>
      )}
      {cs.overall_conclusion && <div className="combined-conclusion">{cs.overall_conclusion}</div>}
    </div>
  );
}
