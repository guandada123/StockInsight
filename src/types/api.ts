// API 响应类型定义

// 开发模式走 Vite 代理 (相对路径)，生产模式直连
export const API_BASE = window.location.hostname === "localhost" ? "" : "http://127.0.0.1:8765";

export interface ApiResponse<T = unknown> {
  success: boolean;
  data: T;
  error: string | null;
  freshness: "fresh" | "cached" | "degraded" | "stale";
  timing_ms: number;
}

export interface MarketIndex {
  name: string;
  code: string;
  price: number;
  change: number;
  change_pct: number;
  volume?: number;
}

export interface SectorInfo {
  name: string;
  code: string;
  change_pct: number;
  fund_flow_yi: number;
  ranking: number;
  leading_stock?: string;
}

export interface StockQuote {
  code: string;
  name: string;
  price: number;
  open: number;
  high: number;
  low: number;
  prev_close: number;
  change: number;
  change_pct: number;
  amplitude: number;
  volume?: number;
  turnover?: number;
}

export interface KlineData {
  dates: string[];
  opens: number[];
  highs: number[];
  lows: number[];
  closes: number[];
  volumes: number[];
  ma5: (number | null)[];
  ma10: (number | null)[];
  ma20: (number | null)[];
  ma60: (number | null)[];
}

export interface IndicatorData {
  type: string;
  dates: string[];
  values: Record<string, number[]>;
}

export interface FactorScores {
  momentum: number;
  technical: number;
  fundamental: number;
  volume: number;
  risk: number;
  sentiment?: number;
  fund_flow?: number;
}

export interface QuantScore {
  composite: number;
  rating: string;
  factor_scores: FactorScores;
}

export interface RiskMetrics {
  sharpe_ratio: number;
  max_drawdown_pct: number;
  annual_volatility_pct: number;
  var_95_pct: number;
}

export interface TechnicalSummary {
  ma_status: string;
  macd_signal: string;
  kdj_signal: string;
  rsi_value: number;
  macd_dif?: number;
  macd_dea?: number;
  adx?: number;
  atr: number;
  support: number[];
  resistance: number[];
  stop_loss: number;
  stop_profit: number;
}

export interface FinancialData {
  roe?: number;
  pe?: number;
  pb?: number;
  eps?: number;
  gross_margin?: number;
  net_margin?: number;
  revenue_growth?: number;
  profit_growth?: number;
}

export interface FundFlowData {
  direction: string;
  total_5d: number;
  chip_score: number;
  national_team: string;
  daily?: Array<{
    date: string;
    main_net: number;
    main_pct: number;
  }>;
}

export interface DebateData {
  bull_points: string[];
  bear_points: string[];
  bull_score: number;
  bear_score: number;
  verdict: string;
  action: string;
}

export interface MlPrediction {
  direction: string;
  confidence: number;
  votes: string;
  models: Record<string, unknown>;
}

export interface SignalData {
  bias: string;
  score: number;
  combo_strength: number;
  details?: string[];
}

export interface StockAnalysisResult {
  code: string;
  name: string;
  time: string;
  quote: StockQuote;
  kline?: KlineData;
  technical: TechnicalSummary;
  quant: QuantScore;
  risk: RiskMetrics;
  financial: FinancialData;
  fund_flow: FundFlowData;
  debate?: DebateData;
  ml?: MlPrediction;
  signal: SignalData;
  near_5d: number;
  near_20d: number;
  short_score: number;
  long_score: number;
  style: string;
  // 11段分析新增
  sector_analysis?: SectorAnalysis;
  pattern_analysis?: PatternAnalysis;
  manipulator_intention?: ManipulatorIntention;
  retail_psychology?: RetailPsychology;
  prediction?: PredictionData;
  operation_advice?: OperationAdvice;
  combined_summary?: CombinedSummary;
  risk_warnings?: RiskWarning[];
  data_sources?: DataSourceInfo;
  business_quality?: BusinessQuality;
  chip_concentration?: ChipConcentration;
}

export interface ChipConcentration {
  pct90: number;
  pct70: number;
  avg_cost: number;
  current_price: number;
  level: string;
  risk_warning: string;
  cost_range_90: [number, number];
  cost_range_70: [number, number];
  lookback_days: number;
}

export interface PortfolioHolding {
  code: string;
  name: string;
  shares: number;
  cost: number;
  current_price: number;
  market_value: number;
  profit_amount: number;
  profit_pct: number;
  weight_pct: number;
  signal?: string;
}

export interface PortfolioData {
  name: string;
  holdings: PortfolioHolding[];
  total_value: number;
  total_cost: number;
  total_profit: number;
  total_profit_pct: number;
  count: number;
  update_time: string;
  suggestion?: string;
}

export interface DataStats {
  db_size_mb: number;
  kline_count: number;
  fundamental_count: number;
  national_team_count: number;
  sector_count: number;
  score_dates: number;
  last_kline_update: string;
  total_stocks: number;
}

export interface DataSourceStatus {
  name: string;
  type: string;
  status: "ok" | "slow" | "error" | "disabled";
  latency_ms: number;
  message: string;
}

// ── 11段分析新增类型 ──

export interface SectorAnalysis {
  industry: string;
  concepts: string[];
  sector_name: string;
  sector_rank: number;
  sector_total: number;
  sector_change_pct: number;
  sector_fund_flow_yi: number;
  rank_label: string;
  rank_color: string;
  assessment: string;
}

export interface PatternItem {
  name: string;
  date: string;
  type: "bullish" | "bearish" | "neutral";
  description: string;
  reliability: "高" | "中" | "低";
}

export interface PatternAnalysis {
  recent_patterns: PatternItem[];
  summary: string;
  trend_phase: string;
  key_observation: string;
}

export interface ManipulatorIntention {
  phase: string;
  phase_confidence: number;
  signals: string[];
  volume_analysis: string;
  chip_analysis: string;
  assessment: string;
  risk_note: string;
}

export interface RetailPsychology {
  emotion: string;
  emotion_score: number;
  behavior_pattern: string;
  sentiment_indicators: string[];
  advice: string;
}

export interface PredictionData {
  direction: string;
  confidence: number;
  price_range: { low: number; high: number };
  key_level: number;
  rationale: string;
}

export interface OperationAdvice {
  direction: string;
  direction_color: string;
  confidence: string;
  entry_range: { low: number; high: number };
  stop_loss: number;
  take_profit: number[];
  position_pct: number;
  holding_days: string;
  key_points: string[];
}

export interface CombinedSummary {
  kline_summary: string;
  manipulator_summary: string;
  synergy_assessment: string;
  overall_conclusion: string;
}

export interface RiskWarning {
  level: "high" | "medium" | "low" | "info";
  message: string;
}

export interface DataSourceInfo {
  quote_source: string;
  kline_source: string;
  sector_source: string;
  fundamental_source: string;
  update_time: string;
  disclaimer: string;
}

// ── 公司质地七问 ──

export interface CompanyProfile {
  name: string;
  industry: string;
  business_scope: string;
  main_business: string;
  listing_date: string;
  registered_capital: string;
  total_market_cap: string;
}

export interface MoatScore {
  score: number;
  level: string;
  dimensions: Record<string, number>;
  signals: string[];
  assessment: string;
}

export interface CashFlowAnalysis {
  operating_cf_yi: number;
  investing_cf_yi: number;
  financing_cf_yi: number;
  free_cf_yi: number;
  quality: string;
  assessment: string;
}

export interface LifecycleStage {
  stage: string;
  stage_cn: string;
  confidence: number;
  signals: string[];
  suggestion: string;
}

export interface ValuationScore {
  score: number;
  level: string;
  pe: number | null;
  pb: number | null;
  peg: number | null;
  signals: string[];
  assessment: string;
}

export interface UpcomingEvent {
  type: string;
  date: string;
  title: string;
}

export interface UpcomingEvents {
  events: UpcomingEvent[];
  assessment: string;
}

export interface BusinessQuality {
  code: string;
  name: string;
  price: number;
  overall_score: number;
  overall_level: string;
  company_profile: CompanyProfile;
  moat: MoatScore;
  cash_flow: CashFlowAnalysis;
  lifecycle: LifecycleStage;
  valuation: ValuationScore;
  events: UpcomingEvents;
  assessment_summary: string;
}
