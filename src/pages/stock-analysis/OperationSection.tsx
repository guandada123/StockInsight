import type { OperationAdvice } from "../../types/api";

export default function OperationSection({ op }: { op: OperationAdvice }) {
  return (
    <div className="operation-card">
      <div className="operation-header">
        <div className={`operation-action ${op.direction_color}`}>{op.direction}</div>
        <span className="tag tag-info">置信度: {op.confidence}</span>
      </div>
      <table className="operation-table">
        <tbody>
          <tr>
            <td>买入区间</td>
            <td style={{ color: "var(--gn)" }}>
              {op.entry_range?.low} ~ {op.entry_range?.high}
            </td>
          </tr>
          <tr>
            <td>止损价</td>
            <td style={{ color: "var(--rd)" }}>{op.stop_loss}</td>
          </tr>
          {op.take_profit?.map((tp, i) => (
            <tr key={i}>
              <td>止盈目标{i + 1}</td>
              <td style={{ color: "var(--gn)" }}>{tp}</td>
            </tr>
          ))}
          <tr>
            <td>建议仓位</td>
            <td style={{ color: op.position_pct >= 50 ? "var(--gn)" : "var(--gd)" }}>
              {op.position_pct}%
            </td>
          </tr>
          <tr>
            <td>持有周期</td>
            <td>{op.holding_days}</td>
          </tr>
        </tbody>
      </table>
      {op.key_points && op.key_points.length > 0 && (
        <div className="operation-points">
          {op.key_points.map((p, i) => (
            <div key={i} className="operation-point">
              • {p}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
