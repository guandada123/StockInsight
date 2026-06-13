import { Routes, Route, useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import Dashboard from "./pages/Dashboard";
import StockAnalysis from "./pages/StockAnalysis";
import Portfolio from "./pages/Portfolio";
import Settings from "./pages/Settings";
import ErrorBoundary from "./components/ErrorBoundary";
import { API_BASE } from "./types/api";

export default function App() {
  const navigate = useNavigate();
  const [searchCode, setSearchCode] = useState("");

  const handleSearch = () => {
    const code = searchCode.trim();
    if (code && /^\d{6}$/.test(code)) {
      navigate(`/stock/${code}`);
    }
  };

  // 检查 API 后端是否就绪
  const [apiReady, setApiReady] = useState(false);
  useEffect(() => {
    let retries = 0;
    const check = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/health`);
        if (res.ok) { setApiReady(true); return; }
      } catch (err) {
        console.warn("[App] API health check failed, retrying...", err);
      }
      if (retries++ < 30) setTimeout(check, 1000);
    };
    check();
  }, []);

  if (!apiReady) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", background: "#060b14", color: "#bac8dc", flexDirection: "column", gap: 16 }}>
        <div style={{ fontSize: 24, fontWeight: 800, color: "#fff" }}>Stock<span style={{ color: "#3b82f6" }}>Insight</span> Pro</div>
        <div style={{ color: "#5a6e8a" }}>正在启动 Python 分析引擎...</div>
        <div style={{ width: 200, height: 3, background: "#1a2740", borderRadius: 2, overflow: "hidden" }}>
          <div style={{ width: "40%", height: "100%", background: "#3b82f6", borderRadius: 2, animation: "pulse 1.5s infinite" }} />
        </div>
        <style>{`@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }`}</style>
      </div>
    );
  }

  return (
    <div className="app-layout">
      {/* 顶部导航 */}
      <nav className="nav">
        <div className="nav-logo" onClick={() => navigate("/")}>
          Stock<span>Insight</span>
        </div>
        <div className="nav-tabs">
          <button className="nav-tab active" onClick={() => navigate("/")}>仪表盘</button>
          <button className="nav-tab" onClick={() => navigate("/portfolio")}>持仓</button>
        <button className="nav-tab" onClick={() => navigate("/settings")}>设置</button>
        </div>
        <input
          className="nav-search"
          placeholder="输入股票代码 如 600519"
          value={searchCode}
          onChange={(e) => setSearchCode(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
        />
        <button className="nav-btn primary" onClick={handleSearch}>分析</button>
        <div className="nav-spacer" />
        <span style={{ fontSize: 10, color: "var(--dm)" }}>v1.0 MVP</span>
      </nav>

      {/* 主体内容 */}
      <div className="main-body">
        <ErrorBoundary>
          <div className="content">
            <Routes>
              <Route path="/" element={<Dashboard onSearch={handleSearch} />} />
              <Route path="/stock/:code" element={<StockAnalysis />} />
              <Route path="/portfolio" element={<Portfolio />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </div>

          {/* 侧边栏 */}
          <Sidebar />
        </ErrorBoundary>
      </div>

      {/* 底部 */}
      <div className="footer">
        <span>数据来源: 新浪财经 / 东方财富 / akshare</span>
        <span>免责声明: 以上分析仅供学习研究，不构成投资建议</span>
      </div>
    </div>
  );
}

function Sidebar() {
  // Read watchlist from localStorage, fallback to defaults
  const [watchlist, setWatchlist] = useState(() => {
    try {
      const saved = localStorage.getItem("watchlist");
      if (saved) return JSON.parse(saved);
    } catch {}
    return [
      { code: "600519", name: "茅台", tag: "白酒" },
      { code: "300750", name: "宁德时代", tag: "电池" },
      { code: "002594", name: "比亚迪", tag: "新能源车" },
      { code: "600036", name: "招商银行", tag: "银行" },
      { code: "300308", name: "中际旭创", tag: "光模块" },
    ];
  });

  const navigate = useNavigate();

  const removeStock = (code: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const next = watchlist.filter((s: any) => s.code !== code);
    setWatchlist(next);
    localStorage.setItem("watchlist", JSON.stringify(next));
  };

  return (
    <div className="sidebar">
      <div className="card">
        <div className="card-header">自选股</div>
        <div className="card-body" style={{ padding: 8 }}>
          {watchlist.map((s: any) => (
            <div key={s.code} className="wl-item" onClick={() => navigate("/stock/" + s.code)}>
              <div style={{ flex: 1 }}>
                <div className="wl-name">{s.name}</div>
                <div className="wl-code">{s.code} &middot; {s.tag}</div>
              </div>
              <button
                className="wl-remove"
                onClick={(e) => removeStock(s.code, e)}
                title="删除"
              >&times;</button>
            </div>
          ))}
          {watchlist.length === 0 && (
            <div style={{ color: "var(--dm)", fontSize: 12, textAlign: "center", padding: 12 }}>
              暂无自选股，在个股页点击右上角添加
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
