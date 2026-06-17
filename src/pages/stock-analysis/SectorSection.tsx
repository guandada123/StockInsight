import type { SectorAnalysis } from "../../types/api";

export default function SectorSection({ sa }: { sa: SectorAnalysis }) {
  return (
    <div>
      <div className="sector-info">
        <span className={`sector-badge ${sa.rank_color}`}>{sa.rank_label}</span>
        <div className="sector-rank">
          行业: <strong>{sa.industry}</strong>
        </div>
        {sa.sector_rank > 0 && (
          <div className="sector-rank">
            排名: <strong>#{sa.sector_rank}</strong>/{sa.sector_total} 涨跌:{" "}
            <span style={{ color: sa.sector_change_pct >= 0 ? "var(--gn)" : "var(--rd)" }}>
              {sa.sector_change_pct >= 0 ? "+" : ""}
              {sa.sector_change_pct}%
            </span>{" "}
            资金:{" "}
            <span style={{ color: sa.sector_fund_flow_yi >= 0 ? "var(--gn)" : "var(--rd)" }}>
              {sa.sector_fund_flow_yi >= 0 ? "+" : ""}
              {sa.sector_fund_flow_yi}亿
            </span>
          </div>
        )}
      </div>
      {sa.concepts && sa.concepts.length > 0 && (
        <div style={{ marginTop: 8 }}>
          {sa.concepts.map((c: string, i: number) => (
            <span key={i} className="tag tag-purple" style={{ marginRight: 4 }}>
              {c}
            </span>
          ))}
        </div>
      )}
      {sa.assessment && (
        <div style={{ marginTop: 8, fontSize: 11, color: "var(--tx)", lineHeight: 1.5 }}>
          {sa.assessment}
        </div>
      )}
    </div>
  );
}
