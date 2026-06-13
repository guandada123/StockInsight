"""Pydantic 统一响应模型"""

from typing import Any

from pydantic import BaseModel


class ApiResponse(BaseModel):
    success: bool
    data: Any = None
    error: str | None = None
    freshness: str = "fresh"  # fresh | cached | degraded | stale
    timing_ms: float = 0


class MarketIndex(BaseModel):
    name: str
    code: str
    price: float
    change: float
    change_pct: float
    volume: float | None = None  # 亿


class SectorInfo(BaseModel):
    name: str
    code: str
    change_pct: float
    fund_flow: float | None = None  # 亿
    ranking: int
    leading_stock: str | None = None


class StockQuote(BaseModel):
    code: str
    name: str
    price: float
    open: float
    high: float
    low: float
    prev_close: float
    change: float
    change_pct: float
    amplitude: float
    volume: float | None = None
    turnover: float | None = None


class KlineData(BaseModel):
    dates: list[str]
    opens: list[float]
    highs: list[float]
    lows: list[float]
    closes: list[float]
    volumes: list[float]
    ma5: list[float | None]
    ma10: list[float | None]
    ma20: list[float | None]
    ma60: list[float | None]


class IndicatorData(BaseModel):
    type: str  # macd | rsi | kdj
    dates: list[str]
    values: dict[str, list[float]]


class FactorScores(BaseModel):
    momentum: float = 0
    technical: float = 0
    fundamental: float = 0
    volume: float = 0
    risk: float = 0
    sentiment: float | None = None
    fund_flow: float | None = None


class QuantScore(BaseModel):
    composite: float = 0
    rating: str = ""
    factor_scores: FactorScores = FactorScores()


class RiskMetrics(BaseModel):
    sharpe_ratio: float = 0
    sortino_ratio: float | None = None
    max_drawdown_pct: float = 0
    max_drawdown_days: int | None = None
    annual_return_pct: float = 0
    annual_volatility_pct: float = 0
    calmar_ratio: float | None = None
    var_95_pct: float = 0
    cvar_95_pct: float | None = None


class TechnicalSummary(BaseModel):
    ma_status: str = ""
    macd_signal: str = ""
    kdj_signal: str = ""
    rsi_value: float = 50
    macd_dif: float | None = None
    macd_dea: float | None = None
    macd_bar: float | None = None
    kdj_k: float | None = None
    kdj_d: float | None = None
    kdj_j: float | None = None
    adx: float | None = None
    atr: float | None = None
    support: list[float] = []
    resistance: list[float] = []
    stop_loss: float = 0
    stop_profit: float = 0


class FinancialData(BaseModel):
    roe: float | None = None
    pe: float | None = None
    pb: float | None = None
    eps: float | None = None
    gross_margin: float | None = None
    net_margin: float | None = None
    revenue_growth: float | None = None
    profit_growth: float | None = None
    asset_liability_ratio: float | None = None
    operating_cashflow: float | None = None


class FundFlowData(BaseModel):
    direction: str = ""  # 流入/流出
    total_5d: float = 0
    total_20d: float | None = None
    daily_flows: list[dict] | None = None
    chip_score: float = 50
    national_team: str = "无"


class DebateData(BaseModel):
    bull_points: list[str] = []
    bear_points: list[str] = []
    bull_score: int = 0
    bear_score: int = 0
    verdict: str = ""
    action: str = ""


class MlPrediction(BaseModel):
    direction: str = ""
    confidence: float = 0
    votes: str = ""
    models: dict = {}


class SignalData(BaseModel):
    bias: str = "neutral"
    score: int = 0
    combo_strength: int = 0
    details: list[str] = []


class StockAnalysisResult(BaseModel):
    code: str
    name: str
    time: str
    quote: StockQuote
    kline: KlineData | None = None
    technical: TechnicalSummary
    quant: QuantScore
    risk: RiskMetrics
    financial: FinancialData
    fund_flow: FundFlowData
    debate: DebateData
    ml: MlPrediction | None = None
    signal: SignalData
    short_score: float = 0
    long_score: float = 0
    style: str = ""
    near_5d: float = 0
    near_20d: float = 0


class PortfolioHolding(BaseModel):
    code: str
    name: str
    shares: int
    cost: float
    current_price: float
    market_value: float
    profit_pct: float
    profit_amount: float
    weight_pct: float
    signal: str | None = None


class PortfolioSummary(BaseModel):
    name: str
    total_value: float
    total_cost: float
    total_profit: float
    total_profit_pct: float
    holdings_count: int
    volatility: float | None = None
    sharpe: float | None = None
    max_drawdown: float | None = None
    rebalance_suggestion: str = ""


class DataStats(BaseModel):
    db_size_mb: float
    kline_count: int
    fundamental_count: int
    national_team_count: int
    sector_count: int
    score_dates: int
    last_kline_update: str
    ttl_entries: int
    total_stocks: int


class DataSourceStatus(BaseModel):
    name: str
    status: str  # ok | slow | error | disabled
    latency_ms: float
    message: str = ""


class CacheStats(BaseModel):
    hit_rate_pct: float = 0
    mem_cache_size: int = 0
    db_size_mb: float = 0
