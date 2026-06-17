import type { DataSourceInfo } from "../../types/api";

export default function DataSourcesSection({ ds }: { ds: DataSourceInfo }) {
  return (
    <div>
      <div className="source-grid">
        <div className="source-item">
          <div className="source-dot ok" />
          {ds.quote_source}
        </div>
        <div className="source-item">
          <div className="source-dot ok" />
          {ds.kline_source}
        </div>
        <div className="source-item">
          <div className="source-dot ok" />
          {ds.sector_source}
        </div>
        <div className="source-item">
          <div className="source-dot ok" />
          {ds.fundamental_source}
        </div>
      </div>
      <div className="fs-10 c-dm mt-6">数据更新: {ds.update_time}</div>
      <div className="disclaimer-text">{ds.disclaimer}</div>
    </div>
  );
}
