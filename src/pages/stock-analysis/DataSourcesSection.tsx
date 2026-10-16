import type { DataSourceInfo, Freshness } from "../../types/api";

// P2-5：原来四个数据源状态点硬编码 "ok"，忽略后端 freshness。改为按 freshness 驱动 class：
//   fresh → ok、cached/degraded → warn、stale → error，并展示时效文案。
const FRESHNESS_META: Record<Freshness, { dot: string; label: string }> = {
  fresh: { dot: "ok", label: "新鲜" },
  cached: { dot: "warn", label: "缓存" },
  degraded: { dot: "warn", label: "降级" },
  stale: { dot: "error", label: "已过期" },
};

export default function DataSourcesSection({
  ds,
  freshness = "fresh",
}: {
  ds: DataSourceInfo;
  freshness?: Freshness;
}) {
  const meta = FRESHNESS_META[freshness] ?? FRESHNESS_META.fresh;
  return (
    <div>
      <div className="source-grid">
        <div className="source-item">
          <div className={`source-dot ${meta.dot}`} />
          {ds.quote_source}
        </div>
        <div className="source-item">
          <div className={`source-dot ${meta.dot}`} />
          {ds.kline_source}
        </div>
        <div className="source-item">
          <div className={`source-dot ${meta.dot}`} />
          {ds.sector_source}
        </div>
        <div className="source-item">
          <div className={`source-dot ${meta.dot}`} />
          {ds.fundamental_source}
        </div>
      </div>
      <div className="fs-10 c-dm mt-6">数据更新: {ds.update_time}</div>
      <div className="fs-10 c-dm mt-4">数据时效: {meta.label}</div>
      <div className="disclaimer-text">{ds.disclaimer}</div>
    </div>
  );
}
