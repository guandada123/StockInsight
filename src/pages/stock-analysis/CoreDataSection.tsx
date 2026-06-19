import type { StockAnalysisResult } from "../../types/api";

export default function CoreDataSection({
  result,
  code,
}: {
  result: StockAnalysisResult;
  code?: string;
}) {
  const { quote, technical, quant, financial, near_5d, near_20d, short_score, long_score, style } =
    result;

  return (
    <div className="card mt-10">
      <div className="card-header">
        <div className="section-header">
          <div className="section-num">3</div>
          <span className="fs-14 fw-700 c-white">个股核心数据</span>
          <span className="fs-10 c-dm">
            {result.name} · {result.time}
          </span>
        </div>
      </div>
      <div className="card-body">
        {/* Quote header */}
        <div className="quote-header">
          <div>
            <div className="qh-name">
              {result.name} <span className="qh-code">{code}</span>
            </div>
          </div>
          <div className="qh-price">{quote.price.toFixed(2)}</div>
          <div className={`qh-chg ${quote.change_pct >= 0 ? "up" : "down"}`}>
            {quote.change_pct >= 0 ? "+" : ""}
            {quote.change_pct.toFixed(2)}%
          </div>
          <span
            className={`tag ${quant.composite >= 65 ? "tag-buy" : quant.composite >= 45 ? "tag-warn" : "tag-sell"}`}
          >
            {quant.rating} {quant.composite}分
          </span>
        </div>
        {/* KPI row */}
        <div className="kpi-row mt-12">
          <div className="kpi">
            <div className="kpi-lbl">今开</div>
            <div className="kpi-val">{quote.open.toFixed(2)}</div>
          </div>
          <div className="kpi">
            <div className="kpi-lbl">最高</div>
            <div className="kpi-val">{quote.high.toFixed(2)}</div>
          </div>
          <div className="kpi">
            <div className="kpi-lbl">最低</div>
            <div className="kpi-val">{quote.low.toFixed(2)}</div>
          </div>
          <div className="kpi">
            <div className="kpi-lbl">振幅</div>
            <div className="kpi-val">{quote.amplitude.toFixed(1)}%</div>
          </div>
          <div className="kpi">
            <div className="kpi-lbl">5日</div>
            <div className={`kpi-val ${near_5d >= 0 ? "up" : "down"}`}>
              {near_5d >= 0 ? "+" : ""}
              {near_5d}%
            </div>
          </div>
          <div className="kpi">
            <div className="kpi-lbl">20日</div>
            <div className={`kpi-val ${near_20d >= 0 ? "up" : "down"}`}>
              {near_20d >= 0 ? "+" : ""}
              {near_20d}%
            </div>
          </div>
          <div className="kpi">
            <div className="kpi-lbl">短线</div>
            <div
              className="kpi-val"
              style={{ color: short_score >= 60 ? "var(--gn)" : "var(--gd)" }}
            >
              {short_score}
            </div>
          </div>
          <div className="kpi">
            <div className="kpi-lbl">长线</div>
            <div
              className="kpi-val"
              style={{ color: long_score >= 60 ? "var(--gn)" : "var(--gd)" }}
            >
              {long_score}
            </div>
          </div>
        </div>
        {/* Key indicators row */}
        <div className="kpi-row mt-8">
          <div className="kpi">
            <div className="kpi-lbl">MACD</div>
            <div
              className="kpi-val"
              style={{
                fontSize: 12,
                color:
                  technical.macd_signal.includes("金叉") || technical.macd_signal.includes("多头")
                    ? "var(--gn)"
                    : technical.macd_signal.includes("死叉") ||
                        technical.macd_signal.includes("空头")
                      ? "var(--rd)"
                      : "var(--gd)",
              }}
            >
              {technical.macd_signal}
            </div>
          </div>
          <div className="kpi">
            <div className="kpi-lbl">KDJ</div>
            <div
              className="kpi-val"
              style={{
                fontSize: 12,
                color:
                  technical.kdj_signal.includes("金叉") || technical.kdj_signal.includes("多头")
                    ? "var(--gn)"
                    : technical.kdj_signal.includes("死叉") || technical.kdj_signal.includes("空头")
                      ? "var(--rd)"
                      : "var(--gd)",
              }}
            >
              {technical.kdj_signal}
            </div>
          </div>
          <div className="kpi">
            <div className="kpi-lbl">RSI</div>
            <div
              className="kpi-val"
              style={{
                fontSize: 12,
                color:
                  technical.rsi_value > 70
                    ? "var(--rd)"
                    : technical.rsi_value < 30
                      ? "var(--gn)"
                      : "#fff",
              }}
            >
              {technical.rsi_value.toFixed(0)}
            </div>
          </div>
          <div className="kpi">
            <div className="kpi-lbl">均线</div>
            <div
              className="kpi-val"
              style={{
                fontSize: 11,
                color: technical.ma_status.includes("多头")
                  ? "var(--gn)"
                  : technical.ma_status.includes("空头")
                    ? "var(--rd)"
                    : "var(--gd)",
              }}
            >
              {technical.ma_status}
            </div>
          </div>
          <div className="kpi">
            <div className="kpi-lbl">PE</div>
            <div className="kpi-val fs-12">{financial.pe ?? "--"}</div>
          </div>
          <div className="kpi">
            <div className="kpi-lbl">ROE</div>
            <div className="kpi-val fs-12">
              {financial.roe !== undefined ? `${financial.roe}%` : "--"}
            </div>
          </div>
          <div className="kpi">
            <div className="kpi-lbl">风格</div>
            <div className="kpi-val fs-11">{style}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
