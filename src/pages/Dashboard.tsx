import { useEffect, useState, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useMarketStore } from "../store";
import { useApi } from "../hooks/useApi";
import type { MarketIndex, SectorInfo } from "../types/api";

export default function Dashboard({ onSearch: _onSearch }: { onSearch: () => void }) {
  const navigate = useNavigate();
  const { indices, setIndices } = useMarketStore();
  const [sectors, setSectors] = useState<SectorInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [quickCode, setQuickCode] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const marketApi = useApi<{ indices: Record<string, MarketIndex> }>();
  const sectorsApi = useApi<{ sectors: SectorInfo[] }>();

  const loadMarket = useCallback(async () => {
    const res = await marketApi.fetchApi("/api/market/overview");
    if (res.success) setIndices(res.data.indices);
    else setError(res.error || "获取市场数据失败");
  }, [setIndices, marketApi]);

  const loadSectors = useCallback(async () => {
    const res = await sectorsApi.fetchApi("/api/market/hot-sectors?top_n=12");
    if (res.success) setSectors(res.data.sectors || []);
  }, [sectorsApi]);

  useEffect(() => {
    loadMarket();
    loadSectors();
    const timer = setInterval(loadMarket, 60000); // 每分钟刷新
    return () => clearInterval(timer);
  }, [loadMarket, loadSectors]);

  function handleQuickAnalysis() {
    const code = quickCode.trim();
    if (code && /^\d{6}$/.test(code)) navigate(`/stock/${code}`);
  }

  const idxMap: Record<string, string> = {
    "000001": "上证指数",
    "399001": "深证成指",
    "399006": "创业板指",
    "000688": "科创50",
  };

  return (
    <div>
      {/* 大盘指数 */}
      <div className="card">
        <div className="card-header">
          <span>市场总览</span>
          <button className="nav-btn" onClick={loadMarket} disabled={marketApi.loading}>
            {marketApi.loading ? "加载中..." : "刷新"}
          </button>
        </div>
        <div className="card-body">
          <div className="market-grid">
            {Object.entries(indices).length === 0 ? (
              <div className="text-center p-20 c-dm" style={{ gridColumn: "1/-1" }}>
                {error ? error : marketApi.loading ? "加载中..." : "暂无数据"}
              </div>
            ) : (
              Object.entries(indices).map(([code, idx]: [string, MarketIndex]) => (
                <div key={code} className="market-card">
                  <div className="mc-name">{idxMap[code] || idx.name}</div>
                  <div className="mc-price">{idx.price.toFixed(2)}</div>
                  <div className={`mc-chg ${idx.change_pct >= 0 ? "up" : "down"}`}>
                    {idx.change_pct >= 0 ? "+" : ""}
                    {idx.change_pct.toFixed(2)}%
                  </div>
                  <div className="mc-vol">成交 {idx.volume?.toFixed(0) ?? "--"} 亿</div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="grid2">
        {/* 板块热点 */}
        <div className="card">
          <div className="card-header">板块热点 TOP12</div>
          <div className="card-body p-8">
            {sectors.length === 0 ? (
              <div className="text-center p-20 c-dm">
                {sectorsApi.loading ? "加载中..." : "暂无数据"}
              </div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>排名</th>
                    <th>板块</th>
                    <th>涨跌幅</th>
                    <th>资金净流入</th>
                  </tr>
                </thead>
                <tbody>
                  {sectors.map((s) => (
                    <tr key={s.code}>
                      <td className="c-dm" style={{ width: 40 }}>
                        {s.ranking}
                      </td>
                      <td>{s.name}</td>
                      <td className={s.change_pct >= 0 ? "up" : "down"}>
                        {s.change_pct >= 0 ? "+" : ""}
                        {s.change_pct.toFixed(2)}%
                      </td>
                      <td className={s.fund_flow_yi >= 0 ? "positive" : "text-red"}>
                        {s.fund_flow_yi.toFixed(1)}亿
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* 快速分析入口 */}
        <div>
          <div className="card">
            <div className="card-header">快速分析</div>
            <div className="card-body text-center p-24">
              <div className="fs-14 c-dm mb-12">输入六位股票代码，获取七层全维度分析</div>
              <input
                ref={inputRef}
                className="nav-search w-full mb-10"
                placeholder="例如 600519 贵州茅台"
                value={quickCode}
                onChange={(e) => setQuickCode(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleQuickAnalysis();
                }}
              />
              <button className="nav-btn primary w-full" onClick={handleQuickAnalysis}>
                开始分析
              </button>
            </div>
          </div>

          {/* 常用入口 */}
          <div className="card">
            <div className="card-header">常用功能</div>
            <div className="card-body">
              <div className="flex-col gap-6">
                {[
                  { label: "持仓管理", path: "/portfolio" },
                  { label: "自选股", codes: "600519,300750,002594,600036,300308" },
                ].map((item) => (
                  <div
                    key={item.path}
                    style={{
                      padding: "8px 10px",
                      borderRadius: 6,
                      cursor: "pointer",
                      background: "#070d18",
                      fontSize: 12,
                    }}
                    onClick={() => item.path && navigate(item.path)}
                  >
                    {item.label}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
