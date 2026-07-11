import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import KlineChart from "../components/KlineChart";
import { useApi } from "../hooks/useApi";
import SectorSection from "./stock-analysis/SectorSection";
import PatternSection from "./stock-analysis/PatternSection";
import ManipulatorSection from "./stock-analysis/ManipulatorSection";
import PsychologySection from "./stock-analysis/PsychologySection";
import PredictionSection from "./stock-analysis/PredictionSection";
import OperationSection from "./stock-analysis/OperationSection";
import CombinedSection from "./stock-analysis/CombinedSection";
import RiskSection from "./stock-analysis/RiskSection";
import DataSourcesSection from "./stock-analysis/DataSourcesSection";
import ScoreCircle from "./stock-analysis/ScoreCircle";
import BusinessQualitySection from "./stock-analysis/BusinessQualitySection";
import MarketIndicesSection from "./stock-analysis/MarketIndicesSection";
import CoreDataSection from "./stock-analysis/CoreDataSection";
import type { StockAnalysisResult, KlineData, IndicatorData, MarketIndex } from "../types/api";

export default function StockAnalysis() {
  const { code } = useParams<{ code: string }>();
  const [result, setResult] = useState<StockAnalysisResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [kline, setKline] = useState<KlineData | null>(null);
  const [indicator, setIndicator] = useState<IndicatorData | null>(null);
  const [indType, setIndType] = useState("macd");
  const [marketIndices, setMarketIndices] = useState<Record<string, MarketIndex>>({});
  const [klineError, setKlineError] = useState<string | null>(null);
  const [indicatorError, setIndicatorError] = useState<string | null>(null);
  const [marketError, setMarketError] = useState<string | null>(null);

  const analysisApi = useApi<StockAnalysisResult>();
  const klineApi = useApi<KlineData>();
  const indicatorApi = useApi<IndicatorData>();
  const marketApi = useApi<{ indices: Record<string, MarketIndex> }>();

  useEffect(() => {
    if (!code) return;
    loadAnalysis(code);
    loadKline(code);
    loadIndicatorData(code, "macd");
    loadMarketOverview();
  }, [code]);

  async function loadAnalysis(c: string) {
    setLoading(true);
    const res = await analysisApi.fetchApi(`/api/analysis/${c}/full`);
    if (res.success) setResult(res.data);
    else setError(res.error || "分析失败");
    setLoading(false);
  }

  async function loadKline(c: string) {
    setKlineError(null);
    const res = await klineApi.fetchApi(`/api/analysis/${c}/kline?days=120`);
    if (res.success) setKline(res.data);
    else setKlineError(res.error || "K线数据加载失败");
  }

  async function loadIndicatorData(c: string, type: string) {
    setIndType(type);
    setIndicatorError(null);
    const res = await indicatorApi.fetchApi(`/api/analysis/${c}/indicators?indicator=${type}`);
    if (res.success) setIndicator(res.data);
    else setIndicatorError(res.error || "指标数据加载失败");
  }

  async function loadMarketOverview() {
    setMarketError(null);
    const res = await marketApi.fetchApi("/api/market/overview");
    if (res.success && res.data) setMarketIndices(res.data.indices || {});
    else setMarketError(res.error || "市场概况加载失败");
  }

  // ── Loading / Error / Empty states ──
  if (loading) return <div className="loading">正在分析 {code}...</div>;
  if (error)
    return (
      <div className="loading" style={{ color: "var(--rd)" }}>
        分析失败: {error}
      </div>
    );
  if (!result) return <div className="loading">无数据</div>;

  const { technical, quant, financial, fund_flow, debate, ml, signal, business_quality } = result;

  return (
    <div>
      <MarketIndicesSection indices={marketIndices} />
      {marketError && (
        <div className="card mt-10">
          <div className="card-body text-center p-12">
            <span className="c-dm fs-12">市场概况加载失败: {marketError}</span>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════
          二、板块分析
          ══════════════════════════════════════ */}
      {result.sector_analysis && (
        <div className="card mt-10">
          <div className="card-header">
            <div className="section-header">
              <div className="section-num">2</div>
              <span className="fs-14 fw-700 c-white">板块分析</span>
              <span className="fs-10 c-dm">板块定胜率，个股定赔率</span>
            </div>
          </div>
          <div className="card-body">
            <SectorSection sa={result.sector_analysis} />
          </div>
        </div>
      )}

      <CoreDataSection result={result} code={code} />

      {/* K线图 + 量化评分 */}
      <div className="grid23 mt-10">
        <div className="card">
          <div className="card-header">
            <span>K线图 — {result.name}</span>
            <div className="flex gap-4">
              {["macd", "rsi", "kdj"].map((t) => (
                <button
                  key={t}
                  className={`nav-tab ${indType === t ? "active" : ""}`}
                  onClick={() => loadIndicatorData(code!, t)}
                >
                  {t.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
          <div className="card-body">
            {klineError ? (
              <div className="text-center p-20 c-dm fs-12">K线数据加载失败: {klineError}</div>
            ) : kline ? (
              <KlineChart data={kline} indicator={indicator} />
            ) : null}
            {indicatorError && !klineError && (
              <div className="text-center p-8 c-dm fs-11">指标数据加载失败: {indicatorError}</div>
            )}
          </div>
        </div>

        {/* 量化评分 + 交易信号 + 资金 & 财务 */}
        <div>
          <div className="card">
            <div className="card-header">量化评分</div>
            <div className="card-body text-center">
              <ScoreCircle score={quant.composite} />
              <div className="mt-8">
                {Object.entries(quant.factor_scores).map(([k, v]) => (
                  <div key={k} className="bar-row">
                    <div className="br-lbl">
                      {k === "momentum"
                        ? "动量"
                        : k === "technical"
                          ? "技术"
                          : k === "fundamental"
                            ? "基本面"
                            : k === "volume"
                              ? "量能"
                              : "风险"}
                    </div>
                    <div className="br-bar">
                      <div
                        className="br-fill"
                        style={{
                          width: `${Math.min(Number(v), 100)}%`,
                          background:
                            Number(v) >= 60
                              ? "var(--gn)"
                              : Number(v) >= 45
                                ? "var(--gd)"
                                : "var(--rd)",
                        }}
                      />
                    </div>
                    <div className="br-val">{typeof v === "number" ? v : 0}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-header">交易信号</div>
            <div className="card-body text-center">
              <div className="verdict-box">
                <div className="va-action">
                  {signal.bias === "bullish" ? "偏多" : signal.bias === "bearish" ? "偏空" : "中性"}
                </div>
                <div className="va-reason">组合信号强度: {signal.combo_strength}</div>
              </div>
              <div className="kpi-row mt-8">
                <div className="kpi">
                  <div className="kpi-lbl">止损</div>
                  <div className="kpi-val c-rd">{technical.stop_loss}</div>
                </div>
                <div className="kpi">
                  <div className="kpi-lbl">止盈</div>
                  <div className="kpi-val c-gn">{technical.stop_profit}</div>
                </div>
                <div className="kpi">
                  <div className="kpi-lbl">支撑</div>
                  <div className="kpi-val">{technical.support[0] ?? "--"}</div>
                </div>
                <div className="kpi">
                  <div className="kpi-lbl">压力</div>
                  <div className="kpi-val">{technical.resistance[0] ?? "--"}</div>
                </div>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-header">资金 & 基本面</div>
            <div className="card-body">
              <div className="kpi-row">
                <div className="kpi">
                  <div className="kpi-lbl">主力5日</div>
                  <div
                    className={`kpi-val ${fund_flow.direction === "流入" ? "positive" : ""}`}
                    style={{
                      color: fund_flow.direction === "流入" ? "var(--gn)" : "var(--rd)",
                      fontSize: 13,
                    }}
                  >
                    {fund_flow.total_5d}亿
                  </div>
                </div>
                <div className="kpi">
                  <div className="kpi-lbl">筹码</div>
                  <div className="kpi-val fs-13">{fund_flow.chip_score}</div>
                </div>
                <div className="kpi">
                  <div className="kpi-lbl">国家队</div>
                  <div className="kpi-val fs-11">{fund_flow.national_team}</div>
                </div>
                <div className="kpi">
                  <div className="kpi-lbl">PB</div>
                  <div className="kpi-val fs-13">{financial.pb ?? "--"}</div>
                </div>
              </div>
              {ml && (
                <div className="verdict-box mt-8">
                  <div className="va-action fs-14">AI预测: {ml.direction}</div>
                  <div className="va-reason">
                    置信度 {ml.confidence}% · {ml.votes}
                  </div>
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
        <div className="card mt-10">
          <div className="card-header">
            <div className="section-header">
              <div className="section-num">4</div>
              <span className="fs-14 fw-700 c-white">K线形态解读</span>
              <span className="fs-10 c-dm">图形会说话</span>
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
        <div className="card mt-10">
          <div className="card-header">
            <div className="section-header">
              <div className="section-num">5</div>
              <span className="fs-14 fw-700 c-white">庄家意图分析</span>
              <span className="fs-10 c-dm">跟庄不跟散</span>
            </div>
          </div>
          <div className="card-body">
            <ManipulatorSection mi={result.manipulator_intention} />
          </div>
        </div>
      )}

      {/* 六、散户心态画像 + 七、明日预测 并排 */}
      <div className="grid2 mt-10">
        {result.retail_psychology && (
          <div className="card">
            <div className="card-header">
              <div className="section-header">
                <div className="section-num">6</div>
                <span className="fs-14 fw-700 c-white">散户心态画像</span>
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
                <span className="fs-14 fw-700 c-white">明日预测</span>
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
        <div className="card mt-10">
          <div className="card-header">
            <div className="section-header">
              <div
                className={`section-num ${result.operation_advice.direction_color === "red" ? "danger" : result.operation_advice.direction_color === "yellow" ? "warn" : ""}`}
              >
                8
              </div>
              <span className="fs-14 fw-700 c-white">操作建议</span>
              <span className="fs-10 c-dm">结论必须明确</span>
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
        <div className="card mt-10">
          <div className="card-header">
            <div className="section-header">
              <div className="section-num">9</div>
              <span className="fs-14 fw-700 c-white">K线+庄家联动总结</span>
            </div>
          </div>
          <div className="card-body">
            <CombinedSection cs={result.combined_summary} />
          </div>
        </div>
      )}

      {/* 多空辩论 */}
      {debate && (
        <div className="card mt-10">
          <div className="card-header">多空辩论</div>
          <div className="card-body">
            <div className="debate-cols">
              <div>
                <div className="dc-ttl c-gn">多头 ({debate.bull_score}分)</div>
                {debate.bull_points.map((p, i) => (
                  <div key={i} className="dc-pt">
                    {p}
                  </div>
                ))}
              </div>
              <div>
                <div className="dc-ttl c-rd">空头 ({debate.bear_score}分)</div>
                {debate.bear_points.map((p, i) => (
                  <div key={i} className="dc-pt">
                    {p}
                  </div>
                ))}
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
        <div className="card mt-10">
          <div className="card-header">
            <div className="section-header">
              <div className="section-num danger">10</div>
              <span className="fs-14 fw-700 c-white">风险提示</span>
              <span className="fs-10 c-dm">每一条都可能是亏损的来源</span>
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
        <div className="card mt-10">
          <div className="card-header">
            <div className="section-header">
              <div className="section-num">11</div>
              <span className="fs-14 fw-700 c-white">数据来源 & 时效性</span>
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
        <div className="card mt-10">
          <div className="card-header">
            <div className="section-header">
              <div className="section-num">12</div>
              <span className="fs-14 fw-700 c-white">公司质地七问</span>
              <span className="fs-10 c-dm">价值投资基本面</span>
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

// Section Sub-components have been extracted to stock-analysis/ directory.
// All 11 components (SectorSection, PatternSection, ManipulatorSection,
// PsychologySection, PredictionSection, OperationSection, CombinedSection,
// RiskSection, DataSourcesSection, ScoreCircle, BusinessQualitySection)
// are imported from ./stock-analysis/ at the top of this file.
