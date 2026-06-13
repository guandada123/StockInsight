import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { PortfolioData, PortfolioHolding } from "../types/api";

import { API_BASE } from "../types/api";

export default function Portfolio() {
  const navigate = useNavigate();
  const [data, setData] = useState<PortfolioData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [portfolioName, setPortfolioName] = useState("");

  useEffect(() => {
    loadPortfolios();
  }, []);

  async function loadPortfolios() {
    try {
      // 先列出所有组合
      const listRes = await fetch(`${API_BASE}/api/portfolio/list`);
      const listJson = await listRes.json();
      if (!listJson.success || !listJson.data.portfolios.length) {
        setError("暂无持仓组合");
        setLoading(false);
        return;
      }
      const name = listJson.data.portfolios[0].name;
      setPortfolioName(name);

      // 加载第一个组合
      const res = await fetch(`${API_BASE}/api/portfolio/${name}`);
      const json = await res.json();
      if (json.success) setData(json.data);
      else setError(json.error);
    } catch (e: unknown) { const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  // 尝试从 mainboard_owned 加载实时数据
  async function loadFromOwned() {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/analysis/owned`);
      const json = await res.json();
      if (json.success && json.data.holdings) {
        setData({
          name: "当前持仓",
          holdings: json.data.holdings,
          total_value: json.data.total_value,
          total_cost: json.data.total_cost || 0,
          total_profit: json.data.total_profit,
          total_profit_pct: json.data.total_profit_pct,
          count: json.data.count,
          update_time: json.data.update_time,
        });
        setError(null);
      } else {
        setError(json.error || "无法加载持仓");
      }
    } catch (e: unknown) { const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  if (loading) return <div className="loading">加载持仓数据...</div>;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: "#fff" }}>
            {data?.name || "持仓管理"}
          </h2>
          {data?.update_time && <span style={{ fontSize: 11, color: "var(--dm)" }}>更新时间: {data.update_time}</span>}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="nav-btn" onClick={loadFromOwned}>从持仓文件加载</button>
          <button className="nav-btn" onClick={loadPortfolios}>刷新</button>
        </div>
      </div>

      {error && !data && (
        <div className="card">
          <div className="card-body" style={{ textAlign: "center", padding: 40 }}>
            <div style={{ fontSize: 16, color: "var(--dm)", marginBottom: 8 }}>{error}</div>
            <button className="nav-btn primary" onClick={loadFromOwned}>从持仓文件加载</button>
          </div>
        </div>
      )}

      {data && (
        <>
          {/* 总览 */}
          <div className="grid2" style={{ marginBottom: 10 }}>
            <div className="card">
              <div className="card-body">
                <div className="kpi-row">
                  <div className="kpi"><div className="kpi-lbl">总市值</div><div className="kpi-val">{data.total_value.toLocaleString()}</div></div>
                  <div className="kpi"><div className="kpi-lbl">总成本</div><div className="kpi-val">{data.total_cost.toLocaleString()}</div></div>
                  <div className="kpi"><div className="kpi-lbl">持仓盈亏</div><div className={`kpi-val ${data.total_profit >= 0 ? "positive" : "text-red"}`}>{data.total_profit >= 0 ? "+" : ""}{data.total_profit.toLocaleString()}</div></div>
                  <div className="kpi"><div className="kpi-lbl">收益率</div><div className={`kpi-val ${data.total_profit_pct >= 0 ? "positive" : "text-red"}`}>{data.total_profit_pct >= 0 ? "+" : ""}{data.total_profit_pct.toFixed(2)}%</div></div>
                  <div className="kpi"><div className="kpi-lbl">持仓数</div><div className="kpi-val">{data.count}</div></div>
                </div>
              </div>
            </div>

            {data.suggestion && (
              <div className="card">
                <div className="card-header">调仓建议</div>
                <div className="card-body">
                  <div className="verdict-box">
                    <div className="va-reason" style={{ fontSize: 13 }}>{data.suggestion}</div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* 持仓明细 */}
          <div className="card">
            <div className="card-header">持仓明细</div>
            <div className="card-body" style={{ padding: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>代码</th><th>名称</th><th>持股</th><th>成本</th>
                    <th>现价</th><th>市值</th><th>占比</th><th>盈亏</th><th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {data.holdings.map((h: PortfolioHolding) => (
                    <tr key={h.code}>
                      <td style={{ color: "var(--dm)", fontSize: 11 }}>{h.code}</td>
                      <td style={{ fontWeight: 600, color: "#fff", cursor: "pointer" }} onClick={() => navigate(`/stock/${h.code}`)}>{h.name}</td>
                      <td>{h.shares}股</td>
                      <td>{h.cost.toFixed(2)}</td>
                      <td style={{ fontWeight: 600 }}>{h.current_price.toFixed(2)}</td>
                      <td>{h.market_value.toLocaleString()}</td>
                      <td>{h.weight_pct.toFixed(1)}%</td>
                      <td className={h.profit_pct >= 0 ? "positive" : "text-red"}>
                        {h.profit_pct >= 0 ? "+" : ""}{h.profit_pct.toFixed(2)}%
                        <div style={{ fontSize: 10, color: "var(--dm)" }}>{h.profit_amount >= 0 ? "+" : ""}{h.profit_amount.toFixed(0)}</div>
                      </td>
                      <td>
                        <button className="nav-btn" style={{ fontSize: 10, padding: "2px 8px" }} onClick={() => navigate(`/stock/${h.code}`)}>分析</button>
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
