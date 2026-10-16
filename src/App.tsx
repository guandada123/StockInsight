import { Routes, Route, useNavigate } from "react-router-dom";
import { lazy, Suspense, useState, useEffect } from "react";
import Dashboard from "./pages/Dashboard";
import ErrorBoundary from "./components/ErrorBoundary";
import { API_BASE } from "./types/api";

// P2-8：按路由做代码分割，把 ECharts（仅个股页使用）等重量依赖移出首屏主包；
//   Dashboard 作为首屏保留同步加载，避免首屏白屏。
const StockAnalysis = lazy(() => import("./pages/StockAnalysis"));
const Portfolio = lazy(() => import("./pages/Portfolio"));
const Settings = lazy(() => import("./pages/Settings"));

interface WatchlistItem {
  code: string;
  name: string;
  tag: string;
}

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
  const [apiFailed, setApiFailed] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  // P1-4：原实现 setTimeout 链无清理/无卸载保护，30 次重试耗尽后永久停在"正在启动"
  //   且无错误态与重试入口。现加 cancelled 标志 + clearTimeout + 单次健康检查超时
  //   （AbortController），耗尽后切错误态并提供「重试」。
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController | undefined;
    let retries = 0;

    const check = async () => {
      controller = new AbortController();
      const timeout = setTimeout(() => controller?.abort(), 4000);
      try {
        const res = await fetch(`${API_BASE}/api/health`, { signal: controller.signal });
        if (!cancelled && res.ok) {
          setApiReady(true);
          return;
        }
      } catch (err) {
        if (!cancelled) console.warn("[App] API health check failed, retrying...", err);
      } finally {
        clearTimeout(timeout);
      }
      if (cancelled) return;
      if (retries++ < 30) {
        timer = setTimeout(check, 1000);
      } else {
        setApiFailed(true);
      }
    };

    check();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      controller?.abort();
    };
  }, [retryKey]);

  // 重试耗尽 → 错误态（提供重试入口）
  if (apiFailed && !apiReady) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "100vh",
          background: "#060b14",
          color: "#bac8dc",
          flexDirection: "column",
          gap: 16,
        }}
      >
        <div className="fs-24 fw-800 c-white">
          Stock<span style={{ color: "#3b82f6" }}>Insight</span> Pro
        </div>
        <div className="c-dm" style={{ maxWidth: 380, textAlign: "center", padding: "0 16px" }}>
          无法连接 Python 分析引擎，请确认后端已启动（同源 /api 或 127.0.0.1:8765）。
        </div>
        <button
          className="nav-btn primary"
          onClick={() => {
            setApiFailed(false);
            setRetryKey((k) => k + 1);
          }}
        >
          重试
        </button>
      </div>
    );
  }

  if (!apiReady) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "100vh",
          background: "#060b14",
          color: "#bac8dc",
          flexDirection: "column",
          gap: 16,
        }}
      >
        <div className="fs-24 fw-800 c-white">
          Stock<span style={{ color: "#3b82f6" }}>Insight</span> Pro
        </div>
        <div className="c-dm">正在启动 Python 分析引擎...</div>
        <div
          style={{
            width: 200,
            height: 3,
            background: "#1a2740",
            borderRadius: 2,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: "40%",
              height: "100%",
              background: "#3b82f6",
              borderRadius: 2,
              animation: "pulse 1.5s infinite",
            }}
          />
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
          <button className="nav-tab active" onClick={() => navigate("/")}>
            仪表盘
          </button>
          <button className="nav-tab" onClick={() => navigate("/portfolio")}>
            持仓
          </button>
          <button className="nav-tab" onClick={() => navigate("/settings")}>
            设置
          </button>
        </div>
        <input
          className="nav-search"
          placeholder="输入股票代码 如 600519"
          value={searchCode}
          onChange={(e) => setSearchCode(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
        />
        <button className="nav-btn primary" onClick={handleSearch}>
          分析
        </button>
        <div className="nav-spacer" />
        <span className="fs-10 c-dm">v1.0 MVP</span>
      </nav>

      {/* 主体内容 */}
      <div className="main-body">
        <ErrorBoundary>
          <div className="content">
            <Suspense fallback={<div className="loading">加载中...</div>}>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/stock/:code" element={<StockAnalysis />} />
                <Route path="/portfolio" element={<Portfolio />} />
                <Route path="/settings" element={<Settings />} />
              </Routes>
            </Suspense>
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
    } catch {
      console.warn("[Sidebar] 读取自选股缓存失败，使用默认值");
    }
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
    const next = watchlist.filter((s: WatchlistItem) => s.code !== code);
    setWatchlist(next);
    localStorage.setItem("watchlist", JSON.stringify(next));
  };

  return (
    <div className="sidebar">
      <div className="card">
        <div className="card-header">自选股</div>
        <div className="card-body p-8">
          {watchlist.map((s: WatchlistItem) => (
            <div key={s.code} className="wl-item" onClick={() => navigate("/stock/" + s.code)}>
              <div className="flex-1">
                <div className="wl-name">{s.name}</div>
                <div className="wl-code">
                  {s.code} &middot; {s.tag}
                </div>
              </div>
              <button className="wl-remove" onClick={(e) => removeStock(s.code, e)} title="删除">
                &times;
              </button>
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
