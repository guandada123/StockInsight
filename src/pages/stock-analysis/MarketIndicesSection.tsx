import type { MarketIndex } from "../../types/api";

const IDX_NAMES: Record<string, string> = {
  "000001": "上证指数",
  "399001": "深证成指",
  "399006": "创业板指",
  "000688": "科创50",
};

export default function MarketIndicesSection({
  indices,
}: {
  indices: Record<string, MarketIndex>;
}) {
  return (
    <div className="card">
      <div className="card-header">
        <div className="section-header">
          <div className="section-num">1</div>
          <span className="fs-14 fw-700 c-white">大盘环境</span>
          <span className="fs-10 c-dm">市场情绪决定仓位</span>
        </div>
      </div>
      <div className="card-body">
        <div className="idx-row">
          {["000001", "399001", "399006", "000688"].map((idxCode) => {
            const idx = indices[idxCode];
            if (!idx)
              return (
                <div
                  key={idxCode}
                  className="market-card"
                  style={{ flex: 1, minWidth: 180, opacity: 0.4 }}
                >
                  <div className="mc-name">{IDX_NAMES[idxCode]}</div>
                  <div className="mc-price">--</div>
                </div>
              );
            const isUp = idx.change_pct >= 0;
            return (
              <div key={idxCode} className="market-card" style={{ flex: 1, minWidth: 180 }}>
                <div className="mc-name">{idx.name}</div>
                <div className="mc-price">{idx.price.toFixed(2)}</div>
                <div className={`mc-chg ${isUp ? "up" : "down"}`}>
                  {isUp ? "+" : ""}
                  {idx.change_pct.toFixed(2)}%
                </div>
                <div className="mc-vol fs-10 c-dm mt-4">
                  成交 {idx.volume?.toFixed(0) ?? "--"} 亿
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
