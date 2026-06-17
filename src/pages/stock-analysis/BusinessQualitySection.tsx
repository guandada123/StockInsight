import type { BusinessQuality } from "../../types/api";

const DIM_LABELS: Record<string, string> = {
  "定价权(毛利率)": "定价权",
  "盈利能力(ROE)": "ROE",
  "技术壁垒(研发)": "研发",
  "品牌/牌照": "品牌",
  规模优势: "规模",
};

export default function BusinessQualitySection({ bq }: { bq: BusinessQuality }) {
  const dims = bq.moat?.dimensions || {};

  return (
    <div>
      {/* Overall */}
      <div className="verdict-box mb-12">
        <div
          className="va-action"
          style={{
            color:
              bq.overall_score >= 55
                ? "var(--gn)"
                : bq.overall_score >= 40
                  ? "var(--gd)"
                  : "var(--rd)",
          }}
        >
          {bq.overall_score}分 → {bq.overall_level}
        </div>
        <div className="va-reason">{bq.assessment_summary}</div>
      </div>

      {/* Details grid */}
      <div className="grid2">
        {/* Q1+Q4 */}
        <div>
          <div className="fs-11 c-dm mb-4">Q1 靠什么赚钱 · Q4 什么阶段</div>
          <div className="fs-12 c-tx" style={{ lineHeight: 1.6 }}>
            {bq.company_profile?.main_business || "数据暂不可用"}
          </div>
          <div className="fs-11 c-tx mt-4">
            行业: {bq.company_profile?.industry} | {bq.lifecycle?.stage_cn} (置信
            {bq.lifecycle?.confidence}%)
          </div>
        </div>

        {/* Q2 护城河 */}
        <div>
          <div className="fs-11 c-dm mb-4">
            Q2 护城河{" "}
            <span
              style={{
                color:
                  bq.moat?.score >= 60
                    ? "var(--gn)"
                    : bq.moat?.score >= 40
                      ? "var(--gd)"
                      : "var(--rd)",
              }}
            >
              {bq.moat?.score}分 {bq.moat?.level}
            </span>
          </div>
          {Object.entries(dims).map(([k, v]) => (
            <div key={k} className="bar-row mb-3">
              <div className="br-lbl" style={{ width: 50 }}>
                {DIM_LABELS[k] || k}
              </div>
              <div className="br-bar">
                <div
                  className="br-fill"
                  style={{
                    width: `${v}%`,
                    background: v >= 15 ? "var(--gn)" : v >= 8 ? "var(--gd)" : "var(--rd)",
                  }}
                />
              </div>
              <div className="br-val">{v}</div>
            </div>
          ))}
        </div>

        {/* Q3 现金流 */}
        <div>
          <div className="fs-11 c-dm mb-4">
            Q3 现金流{" "}
            <span
              style={{
                color:
                  bq.cash_flow?.quality === "优秀"
                    ? "var(--gn)"
                    : bq.cash_flow?.quality === "良好"
                      ? "var(--cy)"
                      : bq.cash_flow?.quality === "一般"
                        ? "var(--gd)"
                        : "var(--rd)",
              }}
            >
              {bq.cash_flow?.quality}
            </span>
          </div>
          <div className="kpi-row">
            <div className="kpi">
              <div className="kpi-lbl">经营CF</div>
              <div className="kpi-val fs-12">{bq.cash_flow?.operating_cf_yi || "--"}亿</div>
            </div>
            <div className="kpi">
              <div className="kpi-lbl">自由CF</div>
              <div
                className="kpi-val"
                style={{
                  fontSize: 12,
                  color: (bq.cash_flow?.free_cf_yi || 0) >= 0 ? "var(--gn)" : "var(--rd)",
                }}
              >
                {bq.cash_flow?.free_cf_yi || "--"}亿
              </div>
            </div>
          </div>
        </div>

        {/* Q5 估值 */}
        <div>
          <div className="fs-11 c-dm mb-4">
            Q5 估值{" "}
            <span
              style={{
                color:
                  bq.valuation?.level === "低估" || bq.valuation?.level === "合理偏低"
                    ? "var(--gn)"
                    : bq.valuation?.level === "合理偏高"
                      ? "var(--gd)"
                      : "var(--rd)",
              }}
            >
              {bq.valuation?.score}分 {bq.valuation?.level}
            </span>
          </div>
          <div className="kpi-row">
            <div className="kpi">
              <div className="kpi-lbl">PE</div>
              <div className="kpi-val fs-12">{bq.valuation?.pe || "--"}</div>
            </div>
            <div className="kpi">
              <div className="kpi-lbl">PB</div>
              <div className="kpi-val fs-12">{bq.valuation?.pb || "--"}</div>
            </div>
            <div className="kpi">
              <div className="kpi-lbl">PEG</div>
              <div className="kpi-val fs-12">{bq.valuation?.peg || "--"}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Q7 事件 */}
      {bq.events?.events && bq.events.events.length > 0 && (
        <div className="mt-10 fs-11 c-tx">
          <span className="c-dm">Q7 近期大事: </span>
          {bq.events.events.slice(0, 3).map((e, i) => (
            <span key={i} className="tag tag-purple mr-4">
              [{e.type}] {e.date} {e.title?.slice(0, 20)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
