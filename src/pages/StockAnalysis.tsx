import { useEffect, useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import KlineChart from "../components/KlineChart";
import StockQuote from "../components/StockQuote";
import IndicatorChart from "../components/IndicatorChart";
import type {
  StockAnalysisResult, KlineData, IndicatorData, MarketIndex,
  SectorAnalysis, PatternAnalysis, ManipulatorIntention,
  RetailPsychology, PredictionData, OperationAdvice,
  CombinedSummary, RiskWarning, DataSourceInfo, BusinessQuality,
} from "../types/api";
import { API_BASE } from "../types/api";

const IDX_NAMES: Record<string, string> = {
  "000001": "上证指数", "399001": "深证成指",
  "399006": "创业板指", "000688": "科创50",
};

export default function StockAnalysis() {
  const { code } = useParams<{ code: string }>();
  const [result, setResult] = useState<StockAnalysisResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [kline, setKline] = useState<KlineData | null>(null);
  const [indicator, setIndicator] = useState<IndicatorData | null>(null);
  const [indType, setIndType] = useState("macd");
  const [marketIndices, setMarketIndices] = useState<Record<string, MarketIndex>>({});

  useEffect(() => {
    if (!code) return;
    setLoading(true);
    setError(null);
    loadAnalysis(code);
    loadKline(code);
    loadIndicatorData(code, "macd");
    loadMarketOverview();
  }, [code]);

  async function loadAnalysis(c: string) {
    try {
      const res = await fetch(`${API_BASE}/api/analysis/${c}/full`);
      const json = await res.json();
      if (json.success) setResult(json.data);
      else setError(json.error || "分析失败");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function loadKline(c: string) {
    try {
      const res = await fetch(`${API_BASE}/api/analysis/${c}/kline?days=120`);
      const json = await res.json();
      if (json.success) setKline(json.data);
    } catch { /* ignore */ }
  }

  async function loadIndicatorData(c: string, type: string) {
    setIndType(type);
    try {
      const res = await fetch(`${API_BASE}/api/analysis/${c}/indicators?indicator=${type}`);
      const json = await res.json();
      if (json.success) setIndicator(json.data);
    } catch { /* ignore */ }
  }

  async function loadMarketOverview() {
    try {
      const res = await fetch(`${API_BASE}/api/market/overview`);
      const json = await res.json();
      if (json.success) setMarketIndices(json.data.indices || {});
    } catch { /* ignore */ }
  }

  // ── Loading / Error / Empty states ──
  if (loading) return <div className="loading">正在分析 {code}...</div>;
  if (error) return <div className="loading" style={{ color: "var(--rd)" }}>分析失败: {error}</div>;
  if (!result) return <div className="loading">无数据</div>;

  const { quote, technical, quant, risk, financial, fund_flow, debate, ml, signal, near_5d, near_20d, short_score, long_score, style, business_quality } = result;

  return (
    <div>
      {/* ══════════════════════════════════════
          一、大盘环境
          ══════════════════════════════════════ */}
      <div className="card">
        <div className="card-header">
          <div className="section-header">
            <div className="section-num">1</div>
            <span style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>大盘环境</span>
            <span style={{ fontSize: 10, color: "var(--dm)" }}>市场情绪决定仓位</span>
          </div>
        </div>
        <div className="card-body">
          <div className="idx-row">
            {["000001", "399001", "399006", "000688"].map(idxCode => {
              const idx = marketIndices[idxCode];
              if (!idx) return <div key={idxCode} className="market-card" style={{ flex: 1, minWidth: 180, opacity: 0.4 }}><div className="mc-name">{IDX_NAMES[idxCode]}</div><div className="mc-price">--</div></div>;
              const isUp = idx.change_pct >= 0;
              return (
                <div key={idxCode} className="market-card" style={{ flex: 1, minWidth: 180 }}>
                  <div className="mc-name">{idx.name}</div>
                  <div className="mc-price">{idx.price.toFixed(2)}</div>
                  <div className={`mc-chg ${isUp ? "up" : "down"}`}>
                    {isUp ? "+" : ""}{idx.change_pct.toFixed(2)}%
                  </div>
                  <div className="mc-vol" style={{ fontSize: 10, color: "var(--dm)", marginTop: 4 }}>
                    成交 {idx.volume?.toFixed(0) ?? "--"} 亿
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* ══════════════════════════════════════
          二、板块分析
          ══════════════════════════════════════ */}
      {result.sector_analysis && (
        <div className="card" style={{ marginTop: 10 }}>
          <div className="card-header">
            <div className="section-header">
              <div className="section-num">2</div>
              <span style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>板块分析</span>
              <span style={{ fontSize: 10, color: "var(--dm)" }}>板块定胜率，个股定赔率</span>
            </div>
          </div>
          <div className="card-body">
            <SectorSection sa={result.sector_analysis} />
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════
          三、个股核心数据
          ══════════════════════════════════════ */}
      <div className="card" style={{ marginTop: 10 }}>
        <div className="card-header">
          <div className="section-header">
            <div className="section-num">3</div>
            <span style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>个股核心数据</span>
            <span style={{ fontSize: 10, color: "var(--dm)" }}>{result.name} · {result.time}</span>
          </div>
        </div>
        <div className="card-body">
          {/* Quote header */}
          <div className="quote-header">
            <div>
              <div className="qh-name">{result.name} <span className="qh-code">{code}</span></div>
            </div>
            <div className="qh-price">{quote.price.toFixed(2)}</div>
            <div className={`qh-chg ${quote.change_pct >= 0 ? "up" : "down"}`}>
              {quote.change_pct >= 0 ? "+" : ""}{quote.change_pct.toFixed(2)}%
            </div>
            <span className={`tag ${quant.composite >= 65 ? "tag-buy" : quant.composite >= 45 ? "tag-warn" : "tag-sell"}`}>
              {quant.rating} {quant.composite}分
            </span>
          </div>
          {/* KPI row */}
          <div className="kpi-row" style={{ marginTop: 12 }}>
            <div className="kpi"><div className="kpi-lbl">今开</div><div className="kpi-val">{quote.open.toFixed(2)}</div></div>
            <div className="kpi"><div className="kpi-lbl">最高</div><div className="kpi-val">{quote.high.toFixed(2)}</div></div>
            <div className="kpi"><div className="kpi-lbl">最低</div><div className="kpi-val">{quote.low.toFixed(2)}</div></div>
            <div className="kpi"><div className="kpi-lbl">振幅</div><div className="kpi-val">{quote.amplitude.toFixed(1)}%</div></div>
            <div className="kpi"><div className="kpi-lbl">5日</div><div className={`kpi-val ${near_5d >= 0 ? "up" : "down"}`}>{near_5d >= 0 ? "+" : ""}{near_5d}%</div></div>
            <div className="kpi"><div className="kpi-lbl">20日</div><div className={`kpi-val ${near_20d >= 0 ? "up" : "down"}`}>{near_20d >= 0 ? "+" : ""}{near_20d}%</div></div>
            <div className="kpi"><div className="kpi-lbl">短线</div><div className="kpi-val" style={{ color: short_score >= 60 ? "var(--gn)" : "var(--gd)" }}>{short_score}</div></div>
            <div className="kpi"><div className="kpi-lbl">长线</div><div className="kpi-val" style={{ color: long_score >= 60 ? "var(--gn)" : "var(--gd)" }}>{long_score}</div></div>
          </div>
          {/* Key indicators row */}
          <div className="kpi-row" style={{ marginTop: 8 }}>
            <div className="kpi">
              <div className="kpi-lbl">MACD</div>
              <div className="kpi-val" style={{ fontSize: 12, color: technical.macd_signal.includes("金叉") || technical.macd_signal.includes("多头") ? "var(--gn)" : technical.macd_signal.includes("死叉") || technical.macd_signal.includes("空头") ? "var(--rd)" : "var(--gd)" }}>{technical.macd_signal}</div>
            </div>
            <div className="kpi">
              <div className="kpi-lbl">KDJ</div>
              <div className="kpi-val" style={{ fontSize: 12, color: technical.kdj_signal.includes("金叉") || technical.kdj_signal.includes("多头") ? "var(--gn)" : technical.kdj_signal.includes("死叉") || technical.kdj_signal.includes("空头") ? "var(--rd)" : "var(--gd)" }}>{technical.kdj_signal}</div>
            </div>
            <div className="kpi">
              <div className="kpi-lbl">RSI</div>
              <div className="kpi-val" style={{ fontSize: 12, color: technical.rsi_value > 70 ? "var(--rd)" : technical.rsi_value < 30 ? "var(--gn)" : "#fff" }}>{technical.rsi_value.toFixed(0)}</div>
            </div>
            <div className="kpi">
              <div className="kpi-lbl">均线</div>
              <div className="kpi-val" style={{ fontSize: 11, color: technical.ma_status.includes("多头") ? "var(--gn)" : technical.ma_status.includes("空头") ? "var(--rd)" : "var(--gd)" }}>{technical.ma_status}</div>
            </div>
            <div className="kpi">
              <div className="kpi-lbl">PE</div>
              <div className="kpi-val" style={{ fontSize: 12 }}>{financial.pe ?? "--"}</div>
            </div>
            <div className="kpi">
              <div className="kpi-lbl">ROE</div>
              <div className="kpi-val" style={{ fontSize: 12 }}>{financial.roe !== undefined ? `${financial.roe}%` : "--"}</div>
            </div>
            <div className="kpi">
              <div className="kpi-lbl">风格</div>
              <div className="kpi-val" style={{ fontSize: 11 }}>{style}</div>
            </div>
          </div>
        </div>
      </div>

      {/* K线图 + 量化评分 */}
      <div className="grid23" style={{ marginTop: 10 }}>
        <div className="card">
          <div className="card-header">
            <span>K线图 — {result.name}</span>
            <div style={{ display: "flex", gap: 4 }}>
              {["macd", "rsi", "kdj"].map((t) => (
                <button key={t} className={`nav-tab ${indType === t ? "active" : ""}`} onClick={() => loadIndicatorData(code!, t)}>{t.toUpperCase()}</button>
              ))}
            </div>
          </div>
          <div className="card-body">
            {kline && <KlineChart data={kline} indicator={indicator} />}
          </div>
        </div>

        {/* 量化评分 + 交易信号 + 资金 & 财务 */}
        <div>
          <div className="card">
            <div className="card-header">量化评分</div>
            <div className="card-body" style={{ textAlign: "center" }}>
              <ScoreCircle score={quant.composite} />
              <div style={{ marginTop: 8 }}>
                {Object.entries(quant.factor_scores).map(([k, v]: [string, any]) => (
                  <div key={k} className="bar-row">
                    <div className="br-lbl">{k === "momentum" ? "动量" : k === "technical" ? "技术" : k === "fundamental" ? "基本面" : k === "volume" ? "量能" : "风险"}</div>
                    <div className="br-bar"><div className="br-fill" style={{ width: `${Math.min(Number(v), 100)}%`, background: Number(v) >= 60 ? "var(--gn)" : Number(v) >= 45 ? "var(--gd)" : "var(--rd)" }} /></div>
                    <div className="br-val">{typeof v === "number" ? v : 0}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-header">交易信号</div>
            <div className="card-body" style={{ textAlign: "center" }}>
              <div className="verdict-box">
                <div className="va-action">{signal.bias === "bullish" ? "偏多" : signal.bias === "bearish" ? "偏空" : "中性"}</div>
                <div className="va-reason">组合信号强度: {signal.combo_strength}</div>
              </div>
              <div className="kpi-row" style={{ marginTop: 8 }}>
                <div className="kpi"><div className="kpi-lbl">止损</div><div className="kpi-val" style={{ color: "var(--rd)" }}>{technical.stop_loss}</div></div>
                <div className="kpi"><div className="kpi-lbl">止盈</div><div className="kpi-val" style={{ color: "var(--gn)" }}>{technical.stop_profit}</div></div>
                <div className="kpi"><div className="kpi-lbl">支撑</div><div className="kpi-val">{technical.support[0] ?? "--"}</div></div>
                <div className="kpi"><div className="kpi-lbl">压力</div><div className="kpi-val">{technical.resistance[0] ?? "--"}</div></div>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-header">资金 & 基本面</div>
            <div className="card-body">
              <div className="kpi-row">
                <div className="kpi"><div className="kpi-lbl">主力5日</div><div className={`kpi-val ${fund_flow.direction === "流入" ? "positive" : ""}`} style={{ color: fund_flow.direction === "流入" ? "var(--gn)" : "var(--rd)", fontSize: 13 }}>{fund_flow.total_5d}亿</div></div>
                <div className="kpi"><div className="kpi-lbl">筹码</div><div className="kpi-val" style={{ fontSize: 13 }}>{fund_flow.chip_score}</div></div>
                <div className="kpi"><div className="kpi-lbl">国家队</div><div className="kpi-val" style={{ fontSize: 11 }}>{fund_flow.national_team}</div></div>
                <div className="kpi"><div className="kpi-lbl">PB</div><div className="kpi-val" style={{ fontSize: 13 }}>{financial.pb ?? "--"}</div></div>
              </div>
              {ml && (
                <div className="verdict-box" style={{ marginTop: 8 }}>
                  <div className="va-action" style={{ fontSize: 14 }}>AI预测: {ml.direction}</div>
                  <div className="va-reason">置信度 {ml.confidence}% · {ml.votes}</div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ══════════════════════════════════════
          四、K线形态解读
          ══════════════════════════════════════ */}
      {result.pattern_analysis && (
        <div className="card" style={{ marginTop: 10 }}>
          <div className="card-header">
            <div className="section-header">
              <div className="section-num">4</div>
              <span style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>K线形态解读</span>
              <span style={{ fontSize: 10, color: "var(--dm)" }}>图形会说话</span>
            </div>
          </div>
          <div className="card-body">
            <PatternSection pa={result.pattern_analysis} />
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════
          五、庄家意图分析
          ══════════════════════════════════════ */}
      {result.manipulator_intention && (
        <div className="card" style={{ marginTop: 10 }}>
          <div className="card-header">
            <div className="section-header">
              <div className="section-num">5</div>
              <span style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>庄家意图分析</span>
              <span style={{ fontSize: 10, color: "var(--dm)" }}>跟庄不跟散</span>
            </div>
          </div>
          <div className="card-body">
            <ManipulatorSection mi={result.manipulator_intention} />
          </div>
        </div>
      )}

      {/* 六、散户心态画像 + 七、明日预测 并排 */}
      <div className="grid2" style={{ marginTop: 10 }}>
        {result.retail_psychology && (
          <div className="card">
            <div className="card-header">
              <div className="section-header">
                <div className="section-num">6</div>
                <span style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>散户心态画像</span>
              </div>
            </div>
            <div className="card-body">
              <PsychologySection rp={result.retail_psychology} />
            </div>
          </div>
        )}

        {result.prediction && (
          <div className="card">
            <div className="card-header">
              <div className="section-header">
                <div className="section-num">7</div>
                <span style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>明日预测</span>
              </div>
            </div>
            <div className="card-body">
              <PredictionSection pred={result.prediction} />
            </div>
          </div>
        )}
      </div>

      {/* ══════════════════════════════════════
          八、操作建议
          ══════════════════════════════════════ */}
      {result.operation_advice && (
        <div className="card" style={{ marginTop: 10 }}>
          <div className="card-header">
            <div className="section-header">
              <div className={`section-num ${result.operation_advice.direction_color === "red" ? "danger" : result.operation_advice.direction_color === "yellow" ? "warn" : ""}`}>8</div>
              <span style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>操作建议</span>
              <span style={{ fontSize: 10, color: "var(--dm)" }}>结论必须明确</span>
            </div>
          </div>
          <div className="card-body">
            <OperationSection op={result.operation_advice} />
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════
          九、K线+庄家联动总结
          ══════════════════════════════════════ */}
      {result.combined_summary && (
        <div className="card" style={{ marginTop: 10 }}>
          <div className="card-header">
            <div className="section-header">
              <div className="section-num">9</div>
              <span style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>K线+庄家联动总结</span>
            </div>
          </div>
          <div className="card-body">
            <CombinedSection cs={result.combined_summary} />
          </div>
        </div>
      )}

      {/* 多空辩论 */}
      {debate && (
        <div className="card" style={{ marginTop: 10 }}>
          <div className="card-header">多空辩论</div>
          <div className="card-body">
            <div className="debate-cols">
              <div>
                <div className="dc-ttl" style={{ color: "var(--gn)" }}>多头 ({debate.bull_score}分)</div>
                {debate.bull_points.map((p, i) => <div key={i} className="dc-pt">{p}</div>)}
              </div>
              <div>
                <div className="dc-ttl" style={{ color: "var(--rd)" }}>空头 ({debate.bear_score}分)</div>
                {debate.bear_points.map((p, i) => <div key={i} className="dc-pt">{p}</div>)}
              </div>
            </div>
            <div className="verdict-box">
              <div className="va-action">{debate.action}</div>
              <div className="va-reason">{debate.verdict}</div>
            </div>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════
          十、风险提示
          ══════════════════════════════════════ */}
      {result.risk_warnings && result.risk_warnings.length > 0 && (
        <div className="card" style={{ marginTop: 10 }}>
          <div className="card-header">
            <div className="section-header">
              <div className="section-num danger">10</div>
              <span style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>风险提示</span>
              <span style={{ fontSize: 10, color: "var(--dm)" }}>每一条都可能是亏损的来源</span>
            </div>
          </div>
          <div className="card-body">
            <RiskSection risks={result.risk_warnings} />
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════
          十一、数据来源 & 时效性
          ══════════════════════════════════════ */}
      {result.data_sources && (
        <div className="card" style={{ marginTop: 10 }}>
          <div className="card-header">
            <div className="section-header">
              <div className="section-num">11</div>
              <span style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>数据来源 & 时效性</span>
            </div>
          </div>
          <div className="card-body">
            <DataSourcesSection ds={result.data_sources} />
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════
          十二、公司质地七问
          ══════════════════════════════════════ */}
      {business_quality && (
        <div className="card" style={{ marginTop: 10 }}>
          <div className="card-header">
            <div className="section-header">
              <div className="section-num">12</div>
              <span style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>公司质地七问</span>
              <span style={{ fontSize: 10, color: "var(--dm)" }}>价值投资基本面</span>
            </div>
          </div>
          <div className="card-body">
            <BusinessQualitySection bq={business_quality} />
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════
// Section Sub-components
// ═══════════════════════════════════════

function SectorSection({ sa }: { sa: SectorAnalysis }) {
  return (
    <div>
      <div className="sector-info">
        <span className={`sector-badge ${sa.rank_color}`}>{sa.rank_label}</span>
        <div className="sector-rank">
          行业: <strong>{sa.industry}</strong>
        </div>
        {sa.sector_rank > 0 && (
          <div className="sector-rank">
            排名: <strong>#{sa.sector_rank}</strong>/{sa.sector_total}
            {" "}涨跌: <span style={{ color: sa.sector_change_pct >= 0 ? "var(--gn)" : "var(--rd)" }}>
              {sa.sector_change_pct >= 0 ? "+" : ""}{sa.sector_change_pct}%
            </span>
            {" "}资金: <span style={{ color: sa.sector_fund_flow_yi >= 0 ? "var(--gn)" : "var(--rd)" }}>
              {sa.sector_fund_flow_yi >= 0 ? "+" : ""}{sa.sector_fund_flow_yi}亿
            </span>
          </div>
        )}
      </div>
      {sa.concepts && sa.concepts.length > 0 && (
        <div style={{ marginTop: 8 }}>
          {sa.concepts.map((c: string, i: number) => <span key={i} className="tag tag-purple" style={{ marginRight: 4 }}>{c}</span>)}
        </div>
      )}
      {sa.assessment && <div style={{ marginTop: 8, fontSize: 11, color: "var(--tx)", lineHeight: 1.5 }}>{sa.assessment}</div>}
    </div>
  );
}

function PatternSection({ pa }: { pa: PatternAnalysis }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: "var(--dm)", marginBottom: 8 }}>
        趋势阶段: <span style={{ color: "#fff", fontWeight: 600 }}>{pa.trend_phase}</span>
      </div>
      {pa.recent_patterns && pa.recent_patterns.length > 0 ? (
        <div className="pattern-list">
          {pa.recent_patterns.map((p, i) => (
            <div key={i} className={`pattern-item ${p.type}`}>
              <div className="pattern-icon">{p.type === "bullish" ? "▲" : p.type === "bearish" ? "▼" : "—"}</div>
              <div className="pattern-body">
                <div className="pattern-name">{p.name} <span style={{ fontSize: 10, color: "var(--dm)", fontWeight: 400 }}>{p.date}</span></div>
                <div className="pattern-desc">{p.description}</div>
                <div className="pattern-meta">可靠性: {p.reliability}</div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ fontSize: 12, color: "var(--dm)", textAlign: "center", padding: 16 }}>近期没有检测到明显K线形态</div>
      )}
      <div className="verdict-box" style={{ marginTop: 10 }}>
        <div className="va-reason" style={{ color: "var(--tx)", fontSize: 12 }}>{pa.summary}</div>
      </div>
      {pa.key_observation && <div style={{ fontSize: 12, color: "var(--tx)", marginTop: 8, lineHeight: 1.5 }}>{pa.key_observation}</div>}
    </div>
  );
}

function ManipulatorSection({ mi }: { mi: ManipulatorIntention }) {
  const phaseClass = mi.phase === "建仓" ? "accumulation" : mi.phase === "洗盘" ? "washout" : mi.phase === "拉升" ? "uptrend" : mi.phase === "出货" ? "distribution" : "unknown";

  return (
    <div>
      <div className="phase-card">
        <div className={`phase-label ${phaseClass}`}>{mi.phase}</div>
        <div className="phase-confidence">判断置信度: {mi.phase_confidence}%</div>
      </div>

      {mi.signals && mi.signals.length > 0 && (
        <div className="phase-signals">
          {mi.signals.map((s, i) => <div key={i} className="phase-signal">• {s}</div>)}
        </div>
      )}

      {mi.volume_analysis && <div style={{ fontSize: 11, color: "var(--tx)", marginTop: 8, lineHeight: 1.5 }}>{mi.volume_analysis}</div>}
      {mi.chip_analysis && <div style={{ fontSize: 11, color: "var(--tx)", marginTop: 4, lineHeight: 1.5 }}>{mi.chip_analysis}</div>}

      <div style={{ fontSize: 12, color: "var(--tx)", marginTop: 10, lineHeight: 1.7, background: "#070d18", padding: 12, borderRadius: 6 }}>
        {mi.assessment}
      </div>

      {mi.risk_note && <div style={{ fontSize: 11, color: "var(--gd)", marginTop: 8, lineHeight: 1.5 }}>⚠ {mi.risk_note}</div>}
    </div>
  );
}

function PsychologySection({ rp }: { rp: RetailPsychology }) {
  const emotionClass = rp.emotion === "贪婪" || rp.emotion === "追涨" ? "greed"
    : rp.emotion === "恐惧" || rp.emotion === "恐慌抛售" ? "fear"
    : rp.emotion === "犹豫观望" ? "hesitation"
    : rp.emotion.includes("恐慌") ? "panic" : "unknown";

  return (
    <div>
      <div className="emotion-display">
        <div className={`emotion-label ${emotionClass}`}>{rp.emotion}</div>
        <div style={{ fontSize: 10, color: "var(--dm)", marginTop: 4 }}>情绪强度: {rp.emotion_score}/100</div>
        <div className="emotion-desc">{rp.behavior_pattern}</div>
      </div>
      {rp.sentiment_indicators && rp.sentiment_indicators.length > 0 && (
        <div style={{ marginTop: 8 }}>
          {rp.sentiment_indicators.map((s, i) => (
            <div key={i} style={{ fontSize: 11, color: "var(--tx)", padding: "3px 0", borderBottom: "1px solid #121a2a" }}>• {s}</div>
          ))}
        </div>
      )}
      {rp.advice && <div className="emotion-advice">{rp.advice}</div>}
    </div>
  );
}

function PredictionSection({ pred }: { pred: PredictionData }) {
  const dirClass = pred.direction.includes("涨") ? "up" : pred.direction.includes("跌") ? "down" : "sideways";

  return (
    <div className="prediction-card">
      <div className={`pred-direction ${dirClass}`}>{pred.direction}</div>
      <div style={{ fontSize: 10, color: "var(--dm)", marginTop: 4 }}>置信度 {pred.confidence}%</div>
      {pred.price_range && (
        <div className="pred-range">
          预测区间: {pred.price_range.low} ~ {pred.price_range.high}
        </div>
      )}
      {pred.rationale && <div className="pred-reason">{pred.rationale}</div>}
    </div>
  );
}

function OperationSection({ op }: { op: OperationAdvice }) {
  return (
    <div className="operation-card">
      <div className="operation-header">
        <div className={`operation-action ${op.direction_color}`}>{op.direction}</div>
        <span className="tag tag-info">置信度: {op.confidence}</span>
      </div>
      <table className="operation-table">
        <tbody>
          <tr><td>买入区间</td><td style={{ color: "var(--gn)" }}>{op.entry_range?.low} ~ {op.entry_range?.high}</td></tr>
          <tr><td>止损价</td><td style={{ color: "var(--rd)" }}>{op.stop_loss}</td></tr>
          {op.take_profit?.map((tp, i) => (
            <tr key={i}><td>止盈目标{i + 1}</td><td style={{ color: "var(--gn)" }}>{tp}</td></tr>
          ))}
          <tr><td>建议仓位</td><td style={{ color: op.position_pct >= 50 ? "var(--gn)" : "var(--gd)" }}>{op.position_pct}%</td></tr>
          <tr><td>持有周期</td><td>{op.holding_days}</td></tr>
        </tbody>
      </table>
      {op.key_points && op.key_points.length > 0 && (
        <div className="operation-points">
          {op.key_points.map((p, i) => <div key={i} className="operation-point">• {p}</div>)}
        </div>
      )}
    </div>
  );
}

function CombinedSection({ cs }: { cs: CombinedSummary }) {
  return (
    <div className="combined-block">
      {cs.kline_summary && (
        <div className="combined-row">
          <div className="combined-label">K线语言</div>
          <div className="combined-text">{cs.kline_summary}</div>
        </div>
      )}
      {cs.manipulator_summary && (
        <div className="combined-row">
          <div className="combined-label">庄家语言</div>
          <div className="combined-text">{cs.manipulator_summary}</div>
        </div>
      )}
      {cs.synergy_assessment && (
        <div className="combined-row">
          <div className="combined-label">联动判断</div>
          <div className="combined-text">{cs.synergy_assessment}</div>
        </div>
      )}
      {cs.overall_conclusion && (
        <div className="combined-conclusion">{cs.overall_conclusion}</div>
      )}
    </div>
  );
}

function RiskSection({ risks }: { risks: RiskWarning[] }) {
  return (
    <div className="risk-list">
      {risks.map((r, i) => (
        <div key={i} className={`risk-item ${r.level}`}>
          <div className="risk-icon">{r.level === "high" ? "🔴" : r.level === "medium" ? "🟡" : r.level === "low" ? "🟢" : "🔵"}</div>
          <div>{r.message}</div>
        </div>
      ))}
    </div>
  );
}

function DataSourcesSection({ ds }: { ds: DataSourceInfo }) {
  return (
    <div>
      <div className="source-grid">
        <div className="source-item"><div className="source-dot ok" />{ds.quote_source}</div>
        <div className="source-item"><div className="source-dot ok" />{ds.kline_source}</div>
        <div className="source-item"><div className="source-dot ok" />{ds.sector_source}</div>
        <div className="source-item"><div className="source-dot ok" />{ds.fundamental_source}</div>
      </div>
      <div style={{ fontSize: 10, color: "var(--dm)", marginTop: 6 }}>数据更新: {ds.update_time}</div>
      <div className="disclaimer-text">{ds.disclaimer}</div>
    </div>
  );
}

// ═══════════════════════════════════════
// Shared Components
// ═══════════════════════════════════════

function ScoreCircle({ score }: { score: number }) {
  const color = score >= 65 ? "#22c55e" : score >= 45 ? "#f59e0b" : "#ef4444";
  return (
    <div className="score-circle" style={{ borderColor: color }}>
      <div className="sc-num">{score}</div>
      <div className="sc-sub">/100</div>
    </div>
  );
}

function BusinessQualitySection({ bq }: { bq: BusinessQuality }) {
  const dims = bq.moat?.dimensions || {};
  const dimLabels: Record<string, string> = {
    "定价权(毛利率)": "定价权", "盈利能力(ROE)": "ROE", "技术壁垒(研发)": "研发",
    "品牌/牌照": "品牌", "规模优势": "规模",
  };

  return (
    <div>
      {/* Overall */}
      <div className="verdict-box" style={{ marginBottom: 12 }}>
        <div className="va-action" style={{ color: bq.overall_score >= 55 ? "var(--gn)" : bq.overall_score >= 40 ? "var(--gd)" : "var(--rd)" }}>
          {bq.overall_score}分 → {bq.overall_level}
        </div>
        <div className="va-reason">{bq.assessment_summary}</div>
      </div>

      {/* Details grid */}
      <div className="grid2">
        {/* Q1+Q4 */}
        <div>
          <div style={{ fontSize: 11, color: "var(--dm)", marginBottom: 4 }}>Q1 靠什么赚钱 · Q4 什么阶段</div>
          <div style={{ fontSize: 12, color: "var(--tx)", lineHeight: 1.6 }}>
            {bq.company_profile?.main_business || "数据暂不可用"}
          </div>
          <div style={{ fontSize: 11, color: "var(--tx)", marginTop: 4 }}>
            行业: {bq.company_profile?.industry} | {bq.lifecycle?.stage_cn} (置信{bq.lifecycle?.confidence}%)
          </div>
        </div>

        {/* Q2 护城河 */}
        <div>
          <div style={{ fontSize: 11, color: "var(--dm)", marginBottom: 4 }}>
            Q2 护城河 <span style={{ color: bq.moat?.score >= 60 ? "var(--gn)" : bq.moat?.score >= 40 ? "var(--gd)" : "var(--rd)" }}>{bq.moat?.score}分 {bq.moat?.level}</span>
          </div>
          {Object.entries(dims).map(([k, v]) => (
            <div key={k} className="bar-row" style={{ marginBottom: 3 }}>
              <div className="br-lbl" style={{ width: 50 }}>{dimLabels[k] || k}</div>
              <div className="br-bar"><div className="br-fill" style={{ width: `${v}%`, background: v >= 15 ? "var(--gn)" : v >= 8 ? "var(--gd)" : "var(--rd)" }} /></div>
              <div className="br-val">{v}</div>
            </div>
          ))}
        </div>

        {/* Q3 现金流 */}
        <div>
          <div style={{ fontSize: 11, color: "var(--dm)", marginBottom: 4 }}>
            Q3 现金流 <span style={{ color: bq.cash_flow?.quality === "优秀" ? "var(--gn)" : bq.cash_flow?.quality === "良好" ? "var(--cy)" : bq.cash_flow?.quality === "一般" ? "var(--gd)" : "var(--rd)" }}>{bq.cash_flow?.quality}</span>
          </div>
          <div className="kpi-row">
            <div className="kpi"><div className="kpi-lbl">经营CF</div><div className="kpi-val" style={{ fontSize: 12 }}>{bq.cash_flow?.operating_cf_yi || "--"}亿</div></div>
            <div className="kpi"><div className="kpi-lbl">自由CF</div><div className="kpi-val" style={{ fontSize: 12, color: (bq.cash_flow?.free_cf_yi || 0) >= 0 ? "var(--gn)" : "var(--rd)" }}>{bq.cash_flow?.free_cf_yi || "--"}亿</div></div>
          </div>
        </div>

        {/* Q5 估值 */}
        <div>
          <div style={{ fontSize: 11, color: "var(--dm)", marginBottom: 4 }}>
            Q5 估值 <span style={{ color: bq.valuation?.level === "低估" || bq.valuation?.level === "合理偏低" ? "var(--gn)" : bq.valuation?.level === "合理偏高" ? "var(--gd)" : "var(--rd)" }}>{bq.valuation?.score}分 {bq.valuation?.level}</span>
          </div>
          <div className="kpi-row">
            <div className="kpi"><div className="kpi-lbl">PE</div><div className="kpi-val" style={{ fontSize: 12 }}>{bq.valuation?.pe || "--"}</div></div>
            <div className="kpi"><div className="kpi-lbl">PB</div><div className="kpi-val" style={{ fontSize: 12 }}>{bq.valuation?.pb || "--"}</div></div>
            <div className="kpi"><div className="kpi-lbl">PEG</div><div className="kpi-val" style={{ fontSize: 12 }}>{bq.valuation?.peg || "--"}</div></div>
          </div>
        </div>
      </div>

      {/* Q7 事件 */}
      {bq.events?.events && bq.events.events.length > 0 && (
        <div style={{ marginTop: 10, fontSize: 11, color: "var(--tx)" }}>
          <span style={{ color: "var(--dm)" }}>Q7 近期大事: </span>
          {bq.events.events.slice(0, 3).map((e, i) => (
            <span key={i} className="tag tag-purple" style={{ marginRight: 4 }}>[{e.type}] {e.date} {e.title?.slice(0, 20)}</span>
          ))}
        </div>
      )}
    </div>
  );
}

