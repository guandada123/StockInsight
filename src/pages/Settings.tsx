import { useEffect, useState } from "react";
import { API_BASE } from "../types/api";

export default function Settings() {
  const [tab, setTab] = useState<"data" | "factors" | "about">("data");

  return (
    <div>
      <h2 style={{ fontSize: 18, fontWeight: 700, color: "#fff", marginBottom: 14 }}>系统设置</h2>
      <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
        {(["data", "factors", "about"] as const).map((t) => (
          <button key={t} className={`nav-tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>
            {t === "data" ? "数据管理" : t === "factors" ? "因子管理" : "关于"}
          </button>
        ))}
      </div>

      {tab === "data" && <DataManagement />}
      {tab === "factors" && <FactorManagement />}
      {tab === "about" && <AboutTab />}
    </div>
  );
}

function DataManagement() {
  const [jobs, setJobs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => { loadJobs(); }, []);

  async function loadJobs() {
    try {
      const res = await fetch(`${API_BASE}/api/data-jobs/list?limit=20`);
      const json = await res.json();
      if (json.success) setJobs(json.data.jobs);
    } catch {}
  }

  async function submitJob(type: string) {
    setLoading(true);
    try {
      await fetch(`${API_BASE}/api/data-jobs/submit?job_type=${type}`, { method: "POST" });
      setTimeout(() => loadJobs(), 1000);
      setTimeout(() => loadJobs(), 3000);
    } catch {} finally { setLoading(false); }
  }

  const jobTypes = [
    { id: "trade_calendar", name: "交易日历", icon: "📅" },
    { id: "stock_basic", name: "股票列表", icon: "📋" },
    { id: "daily_history", name: "日线历史", icon: "📈" },
    { id: "daily_basic", name: "基本面数据", icon: "💰" },
  ];

  return (
    <div>
      <div className="card">
        <div className="card-header">日频数据中心</div>
        <div className="card-body">
          <div className="grid2" style={{ marginBottom: 12 }}>
            {jobTypes.map((jt) => (
              <div key={jt.id} style={{ background: "#070d18", borderRadius: 8, padding: 16, textAlign: "center" }}>
                <div style={{ fontSize: 24, marginBottom: 8 }}>{jt.icon}</div>
                <div style={{ fontSize: 14, fontWeight: 600, color: "#fff", marginBottom: 4 }}>{jt.name}</div>
                <button className="nav-btn primary" disabled={loading} onClick={() => submitJob(jt.id)}>
                  下载
                </button>
              </div>
            ))}
          </div>
          <div style={{ fontSize: 11, color: "var(--dm)" }}>
            需要配置 TUSHARE_TOKEN 环境变量。数据存储在 stock_cache.db。
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <span>任务列表</span>
          <button className="nav-btn" onClick={loadJobs}>刷新</button>
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          <table className="data-table">
            <thead>
              <tr><th>ID</th><th>类型</th><th>状态</th><th>进度</th><th>开始</th><th>完成</th></tr>
            </thead>
            <tbody>
              {jobs.length === 0 ? (
                <tr><td colSpan={6} style={{ textAlign: "center", padding: 20, color: "var(--dm)" }}>暂无任务</td></tr>
              ) : jobs.map((j) => (
                <tr key={j.id}>
                  <td style={{ fontSize: 10, color: "var(--dm)" }}>{j.id}</td>
                  <td>{j.name}</td>
                  <td>
                    <span className={`tag ${j.status === "done" ? "tag-buy" : j.status === "failed" ? "tag-sell" : j.status === "running" ? "tag-info" : "tag-warn"}`}>
                      {j.status === "done" ? "完成" : j.status === "failed" ? "失败" : j.status === "running" ? "运行中" : "等待"}
                    </span>
                  </td>
                  <td>{j.total > 0 ? `${Math.round(j.progress / j.total * 100)}%` : "-"}</td>
                  <td style={{ fontSize: 10 }}>{j.started}</td>
                  <td style={{ fontSize: 10 }}>{j.done || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function FactorManagement() {
  const [factors, setFactors] = useState<any[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ id: "", name: "", expression: "", description: "" });
  const [validateMsg, setValidateMsg] = useState("");

  useEffect(() => { loadFactors(); }, []);

  async function loadFactors() {
    try {
      const res = await fetch(`${API_BASE}/api/factors/list`);
      const json = await res.json();
      if (json.success) setFactors(json.data.factors);
    } catch {}
  }

  async function createFactor() {
    const params = new URLSearchParams(form);
    const res = await fetch(`${API_BASE}/api/factors/create?${params}`, { method: "POST" });
    const json = await res.json();
    if (json.success) {
      setShowCreate(false);
      setForm({ id: "", name: "", expression: "", description: "" });
      loadFactors();
    } else {
      setValidateMsg(json.error || "创建失败");
    }
  }

  async function deleteFactor(id: string) {
    await fetch(`${API_BASE}/api/factors/${id}`, { method: "DELETE" });
    loadFactors();
  }

  async function validateExpr() {
    const res = await fetch(`${API_BASE}/api/factors/validate?expression=${encodeURIComponent(form.expression)}`, { method: "POST" });
    const json = await res.json();
    setValidateMsg(json.data.valid ? "表达式语法正确" : `语法错误: ${json.data.error}`);
  }

  const examples = [
    { expr: "close.pct_change(10)", desc: "10日动量" },
    { expr: "(close - close.rolling(20).mean()) / close.rolling(20).std()", desc: "布林带位置" },
    { expr: "vol / vol.rolling(20).mean()", desc: "量比" },
    { expr: "abs(close - open) / open", desc: "日内振幅" },
  ];

  return (
    <div>
      <div className="card">
        <div className="card-header">
          <span>自定义因子</span>
          <button className="nav-btn primary" onClick={() => setShowCreate(!showCreate)}>
            {showCreate ? "取消" : "+ 新建"}
          </button>
        </div>
        <div className="card-body">
          {showCreate && (
            <div style={{ background: "#070d18", borderRadius: 8, padding: 14, marginBottom: 12 }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <input className="nav-search" style={{ width: "100%" }} placeholder="因子ID (英文, 如 my_momentum_10)"
                  value={form.id} onChange={(e) => setForm({ ...form, id: e.target.value })} />
                <input className="nav-search" style={{ width: "100%" }} placeholder="因子名称 (如 10日动量)"
                  value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                <div style={{ display: "flex", gap: 8 }}>
                  <input className="nav-search" style={{ flex: 1 }} placeholder="表达式 (如 close.pct_change(10))"
                    value={form.expression} onChange={(e) => setForm({ ...form, expression: e.target.value })} />
                  <button className="nav-btn" onClick={validateExpr}>验证</button>
                </div>
                {validateMsg && (
                  <div style={{ fontSize: 11, color: validateMsg.includes("正确") ? "var(--gn)" : "var(--rd)" }}>
                    {validateMsg}
                  </div>
                )}
                <div style={{ fontSize: 10, color: "var(--dm)" }}>
                  可用列: open, high, low, close, vol, amount | 方法: pct_change, rolling, shift, diff
                </div>
                <button className="nav-btn primary" onClick={createFactor} style={{ width: "100%" }}>创建因子</button>
              </div>
            </div>
          )}

          <div style={{ fontSize: 11, color: "var(--dm)", marginBottom: 8 }}>表达式示例:</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
            {examples.map((e, i) => (
              <code key={i} style={{ background: "#070d18", padding: "4px 8px", borderRadius: 4, fontSize: 10, color: "var(--cy)" }}>
                {e.expr} <span style={{ color: "var(--dm)" }}>→ {e.desc}</span>
              </code>
            ))}
          </div>

          <table className="data-table">
            <thead>
              <tr><th>ID</th><th>名称</th><th>表达式</th><th>类型</th><th>创建</th><th>操作</th></tr>
            </thead>
            <tbody>
              {factors.length === 0 ? (
                <tr><td colSpan={6} style={{ textAlign: "center", padding: 20, color: "var(--dm)" }}>暂无自定义因子</td></tr>
              ) : factors.map((f) => (
                <tr key={f.id}>
                  <td style={{ fontSize: 10, color: "var(--cy)" }}>{f.id}</td>
                  <td style={{ fontWeight: 600 }}>{f.name}</td>
                  <td style={{ fontSize: 10, fontFamily: "monospace" }}>{f.expression}</td>
                  <td><span className="tag tag-purple">{f.type}</span></td>
                  <td style={{ fontSize: 10 }}>{f.created}</td>
                  <td><button className="nav-btn" style={{ fontSize: 10, color: "var(--rd)" }} onClick={() => deleteFactor(f.id)}>删除</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function AboutTab() {
  return (
    <div className="card">
      <div className="card-header">关于 StockInsight Pro</div>
      <div className="card-body">
        <div className="kpi-row">
          <div className="kpi"><div className="kpi-lbl">版本</div><div className="kpi-val">1.0.0</div></div>
          <div className="kpi"><div className="kpi-lbl">架构</div><div className="kpi-val">Tauri + React + FastAPI</div></div>
          <div className="kpi"><div className="kpi-lbl">数据源</div><div className="kpi-val" style={{ fontSize: 11 }}>新浪/东方财富/akshare/Tushare</div></div>
          <div className="kpi"><div className="kpi-lbl">数据库</div><div className="kpi-val">SQLite 152MB</div></div>
        </div>
        <div style={{ fontSize: 12, color: "var(--dm)", lineHeight: 1.8, marginTop: 8 }}>
          集成了 henrylin99/quantitative_analysis 项目的:
          <br />· 日频数据中心 — Tushare 数据下载管线
          <br />· 自定义因子表达式引擎 — AST 白名单安全校验
          <br />· Docker 容器化部署支持
          <br />· 组合优化 (均值方差/风险平价/因子中性/Black-Litterman)
        </div>
        <div style={{ fontSize: 10, color: "var(--dm)", marginTop: 12 }}>
          免责声明: 本系统仅供学习研究，不构成投资建议。
        </div>
      </div>
    </div>
  );
}
