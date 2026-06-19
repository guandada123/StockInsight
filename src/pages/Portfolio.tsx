import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import type { PortfolioData, PortfolioHolding } from "../types/api";

/** 组合列表响应中单个条目 */
interface PortfolioListItem {
  name: string;
  count: number;
  total_value: number;
}

export default function Portfolio() {
  const navigate = useNavigate();
  const [data, setData] = useState<PortfolioData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const listApi = useApi<{ portfolios: PortfolioListItem[] }>();
  const detailApi = useApi<PortfolioData>();
  const ownedApi = useApi<{
    holdings: PortfolioHolding[];
    total_value: number;
    total_cost: number;
    total_profit: number;
    total_profit_pct: number;
    count: number;
    update_time: string;
  }>();

  useEffect(() => {
    loadPortfolios();
  }, []);

  async function loadPortfolios() {
    setLoading(true);
    setError(null);
    // 先列出所有组合
    const listRes = await listApi.fetchApi("/api/portfolio/list");
    if (!listRes.success || !listRes.data.portfolios.length) {
      setError("暂无持仓组合");
      setLoading(false);
      return;
    }
    const name = listRes.data.portfolios[0].name;

    // 加载第一个组合
    const res = await detailApi.fetchApi(`/api/portfolio/${name}`);
    if (res.success) setData(res.data);
    else setError(res.error);
    setLoading(false);
  }

  // 尝试从 mainboard_owned 加载实时数据
  async function loadFromOwned() {
    setLoading(true);
    setError(null);
    const res = await ownedApi.fetchApi("/api/analysis/owned");
    if (res.success && res.data.holdings) {
      setData({
        name: "当前持仓",
        holdings: res.data.holdings,
        total_value: res.data.total_value,
        total_cost: res.data.total_cost || 0,
        total_profit: res.data.total_profit,
        total_profit_pct: res.data.total_profit_pct,
        count: res.data.count,
        update_time: res.data.update_time,
      });
      setError(null);
    } else {
      setError(res.error || "无法加载持仓");
    }
    setLoading(false);
  }

  if (loading) return <div className="loading">加载持仓数据...</div>;

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 14,
        }}
      >
        <div>
          <h2 className="fs-18 fw-700 c-white">{data?.name || "持仓管理"}</h2>
          {data?.update_time && <span className="fs-11 c-dm">更新时间: {data.update_time}</span>}
        </div>
        <div className="flex gap-8">
          <button className="nav-btn" onClick={loadFromOwned} disabled={ownedApi.loading}>
            {ownedApi.loading ? "加载中..." : "从持仓文件加载"}
          </button>
          <button className="nav-btn" onClick={loadPortfolios} disabled={listApi.loading}>
            {listApi.loading ? "加载中..." : "刷新"}
          </button>
        </div>
      </div>

      {error && !data && (
        <div className="card">
          <div className="card-body text-center p-40">
            <div className="fs-16 c-dm mb-8">{error}</div>
            <button className="nav-btn primary" onClick={loadFromOwned}>
              从持仓文件加载
            </button>
          </div>
        </div>
      )}

      {data && (
        <>
          {/* 总览 */}
          <div className="grid2 mb-10">
            <div className="card">
              <div className="card-body">
                <div className="kpi-row">
                  <div className="kpi">
                    <div className="kpi-lbl">总市值</div>
                    <div className="kpi-val">{data.total_value.toLocaleString()}</div>
                  </div>
                  <div className="kpi">
                    <div className="kpi-lbl">总成本</div>
                    <div className="kpi-val">{data.total_cost.toLocaleString()}</div>
                  </div>
                  <div className="kpi">
                    <div className="kpi-lbl">持仓盈亏</div>
                    <div className={`kpi-val ${data.total_profit >= 0 ? "positive" : "text-red"}`}>
                      {data.total_profit >= 0 ? "+" : ""}
                      {data.total_profit.toLocaleString()}
                    </div>
                  </div>
                  <div className="kpi">
                    <div className="kpi-lbl">收益率</div>
                    <div
                      className={`kpi-val ${data.total_profit_pct >= 0 ? "positive" : "text-red"}`}
                    >
                      {data.total_profit_pct >= 0 ? "+" : ""}
                      {data.total_profit_pct.toFixed(2)}%
                    </div>
                  </div>
                  <div className="kpi">
                    <div className="kpi-lbl">持仓数</div>
                    <div className="kpi-val">{data.count}</div>
                  </div>
                </div>
              </div>
            </div>

            {data.suggestion && (
              <div className="card">
                <div className="card-header">调仓建议</div>
                <div className="card-body">
                  <div className="verdict-box">
                    <div className="va-reason fs-13">{data.suggestion}</div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* 持仓明细 */}
          <div className="card">
            <div className="card-header">持仓明细</div>
            <div className="card-body p-0">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>代码</th>
                    <th>名称</th>
                    <th>持股</th>
                    <th>成本</th>
                    <th>现价</th>
                    <th>市值</th>
                    <th>占比</th>
                    <th>盈亏</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {data.holdings.map((h: PortfolioHolding) => (
                    <tr key={h.code}>
                      <td className="c-dm fs-11">{h.code}</td>
                      <td
                        className="fw-600 c-white"
                        style={{ cursor: "pointer" }}
                        onClick={() => navigate(`/stock/${h.code}`)}
                      >
                        {h.name}
                      </td>
                      <td>{h.shares}股</td>
                      <td>{h.cost.toFixed(2)}</td>
                      <td className="fw-600">{h.current_price.toFixed(2)}</td>
                      <td>{h.market_value.toLocaleString()}</td>
                      <td>{h.weight_pct.toFixed(1)}%</td>
                      <td className={h.profit_pct >= 0 ? "positive" : "text-red"}>
                        {h.profit_pct >= 0 ? "+" : ""}
                        {h.profit_pct.toFixed(2)}%
                        <div className="fs-10 c-dm">
                          {h.profit_amount >= 0 ? "+" : ""}
                          {h.profit_amount.toFixed(0)}
                        </div>
                      </td>
                      <td>
                        <button
                          className="nav-btn fs-10"
                          style={{ padding: "2px 8px" }}
                          onClick={() => navigate(`/stock/${h.code}`)}
                        >
                          分析
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
