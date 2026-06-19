import { describe, it, expect, beforeEach } from "vitest";
import { useMarketStore, useAnalysisStore, usePortfolioStore, useDataStore } from "./index";
import type { MarketIndex, StockAnalysisResult, PortfolioData, DataStats } from "../types/api";

beforeEach(() => {
  // 重置所有 store 到初始状态
  useMarketStore.setState({ indices: {}, updateTime: "" });
  useAnalysisStore.setState({ currentCode: "", result: null, loading: false });
  usePortfolioStore.setState({ data: null, loading: false });
  useDataStore.setState({ stats: null });
});

// ===== useMarketStore =====
describe("useMarketStore", () => {
  it("初始状态：indices 为空对象，updateTime 为空字符串", () => {
    const state = useMarketStore.getState();
    expect(state.indices).toEqual({});
    expect(state.updateTime).toBe("");
  });

  it("setIndices 更新 indices 并设置 updateTime", () => {
    const mockIndices: Record<string, MarketIndex> = {
      "000001": { name: "上证指数", code: "000001", price: 3200, change: 15, change_pct: 0.47 },
      "399001": { name: "深证成指", code: "399001", price: 10500, change: -30, change_pct: -0.28 },
    };

    useMarketStore.getState().setIndices(mockIndices);
    const state = useMarketStore.getState();

    expect(state.indices).toEqual(mockIndices);
    expect(state.indices["000001"].name).toBe("上证指数");
    expect(state.indices["399001"].change_pct).toBe(-0.28);
    expect(state.updateTime).not.toBe("");
  });

  it("多次调用 setIndices 会覆盖之前的数据", () => {
    useMarketStore.getState().setIndices({
      "000001": { name: "旧数据", code: "000001", price: 3000, change: 0, change_pct: 0 },
    });
    useMarketStore.getState().setIndices({
      "399006": { name: "创业板指", code: "399006", price: 2500, change: 10, change_pct: 0.4 },
    });

    const state = useMarketStore.getState();
    // 新数据覆盖后，旧的不应存在
    expect(state.indices["000001"]).toBeUndefined();
    expect(state.indices["399006"].name).toBe("创业板指");
  });

  it("setIndices 接收空对象时，indices 被清空", () => {
    useMarketStore.getState().setIndices({
      "000001": { name: "上证", code: "000001", price: 3200, change: 0, change_pct: 0 },
    });
    useMarketStore.getState().setIndices({});

    expect(useMarketStore.getState().indices).toEqual({});
  });
});

// ===== useAnalysisStore =====
describe("useAnalysisStore", () => {
  it("初始状态：currentCode 为空，result 为 null，loading 为 false", () => {
    const state = useAnalysisStore.getState();
    expect(state.currentCode).toBe("");
    expect(state.result).toBeNull();
    expect(state.loading).toBe(false);
  });

  it("setCode 更新 currentCode", () => {
    useAnalysisStore.getState().setCode("600519");
    expect(useAnalysisStore.getState().currentCode).toBe("600519");
  });

  it("setResult 设置分析结果", () => {
    const mockResult: StockAnalysisResult = {
      code: "600519",
      name: "贵州茅台",
      time: "2026-06-17 15:00",
      quote: {
        code: "600519",
        name: "贵州茅台",
        price: 1500,
        open: 1498,
        high: 1510,
        low: 1490,
        prev_close: 1500,
        change: 0,
        change_pct: 0,
        amplitude: 1.5,
      },
      technical: {
        ma_status: "多头排列",
        macd_signal: "金叉",
        kdj_signal: "向上",
        rsi_value: 55,
        atr: 20,
        support: [1480],
        resistance: [1520],
        stop_loss: 1480,
        stop_profit: 1520,
      },
      quant: {
        composite: 75,
        rating: "A",
        factor_scores: { momentum: 80, technical: 70, fundamental: 85, volume: 65, risk: 75 },
      },
      risk: { sharpe_ratio: 1.5, max_drawdown_pct: 15, annual_volatility_pct: 20, var_95_pct: 3 },
      financial: { roe: 25, pe: 30, pb: 8 },
      fund_flow: { direction: "净流入", total_5d: 5000, chip_score: 70, national_team: "增持" },
      signal: { bias: "看涨", score: 75, combo_strength: 0.8 },
      near_5d: 3.5,
      near_20d: 8.2,
      short_score: 70,
      long_score: 80,
      style: "价值成长",
    };

    useAnalysisStore.getState().setResult(mockResult);
    expect(useAnalysisStore.getState().result).toEqual(mockResult);
    expect(useAnalysisStore.getState().result!.name).toBe("贵州茅台");
  });

  it("setLoading 更新 loading 状态", () => {
    expect(useAnalysisStore.getState().loading).toBe(false);
    useAnalysisStore.getState().setLoading(true);
    expect(useAnalysisStore.getState().loading).toBe(true);
    useAnalysisStore.getState().setLoading(false);
    expect(useAnalysisStore.getState().loading).toBe(false);
  });

  it("setResult(null) 可以清除结果", () => {
    const mockResult: StockAnalysisResult = {
      code: "600519",
      name: "测试",
      time: "",
      quote: {
        code: "",
        name: "",
        price: 0,
        open: 0,
        high: 0,
        low: 0,
        prev_close: 0,
        change: 0,
        change_pct: 0,
        amplitude: 0,
      },
      technical: {
        ma_status: "",
        macd_signal: "",
        kdj_signal: "",
        rsi_value: 0,
        atr: 0,
        support: [],
        resistance: [],
        stop_loss: 0,
        stop_profit: 0,
      },
      quant: {
        composite: 0,
        rating: "",
        factor_scores: { momentum: 0, technical: 0, fundamental: 0, volume: 0, risk: 0 },
      },
      risk: { sharpe_ratio: 0, max_drawdown_pct: 0, annual_volatility_pct: 0, var_95_pct: 0 },
      financial: {},
      fund_flow: { direction: "", total_5d: 0, chip_score: 0, national_team: "" },
      signal: { bias: "", score: 0, combo_strength: 0 },
      near_5d: 0,
      near_20d: 0,
      short_score: 0,
      long_score: 0,
      style: "",
    };
    useAnalysisStore.getState().setResult(mockResult);
    expect(useAnalysisStore.getState().result).not.toBeNull();
    useAnalysisStore.getState().setResult(null);
    expect(useAnalysisStore.getState().result).toBeNull();
  });
});

// ===== usePortfolioStore =====
describe("usePortfolioStore", () => {
  it("初始状态：data 为 null，loading 为 false", () => {
    const state = usePortfolioStore.getState();
    expect(state.data).toBeNull();
    expect(state.loading).toBe(false);
  });

  it("setData 更新持仓数据", () => {
    const mockPortfolio: PortfolioData = {
      name: "我的组合",
      holdings: [
        {
          code: "600519",
          name: "贵州茅台",
          shares: 100,
          cost: 1450,
          current_price: 1500,
          market_value: 150000,
          profit_amount: 5000,
          profit_pct: 3.45,
          weight_pct: 50,
        },
        {
          code: "300750",
          name: "宁德时代",
          shares: 200,
          cost: 180,
          current_price: 190,
          market_value: 38000,
          profit_amount: 2000,
          profit_pct: 5.56,
          weight_pct: 50,
        },
      ],
      total_value: 188000,
      total_cost: 181000,
      total_profit: 7000,
      total_profit_pct: 3.87,
      count: 2,
      update_time: "2026-06-17 15:00",
    };

    usePortfolioStore.getState().setData(mockPortfolio);
    const state = usePortfolioStore.getState();
    expect(state.data).toEqual(mockPortfolio);
    expect(state.data!.count).toBe(2);
    expect(state.data!.holdings[0].name).toBe("贵州茅台");
  });

  it("setLoading 控制加载状态", () => {
    usePortfolioStore.getState().setLoading(true);
    expect(usePortfolioStore.getState().loading).toBe(true);
    usePortfolioStore.getState().setLoading(false);
    expect(usePortfolioStore.getState().loading).toBe(false);
  });

  it("setData(null) 可以清除持仓数据", () => {
    usePortfolioStore.getState().setData({} as PortfolioData);
    usePortfolioStore.getState().setData(null);
    expect(usePortfolioStore.getState().data).toBeNull();
  });
});

// ===== useDataStore =====
describe("useDataStore", () => {
  it("初始状态：stats 为 null", () => {
    expect(useDataStore.getState().stats).toBeNull();
  });

  it("setStats 更新数据统计", () => {
    const mockStats: DataStats = {
      db_size_mb: 152.3,
      kline_count: 5200,
      fundamental_count: 5500,
      national_team_count: 4800,
      sector_count: 110,
      score_dates: 61,
      last_kline_update: "2026-06-17",
      total_stocks: 5524,
    };

    useDataStore.getState().setStats(mockStats);
    const state = useDataStore.getState();
    expect(state.stats).toEqual(mockStats);
    expect(state.stats!.db_size_mb).toBe(152.3);
    expect(state.stats!.total_stocks).toBe(5524);
  });

  it("setStats(null) 可以清除统计", () => {
    useDataStore.getState().setStats({} as DataStats);
    useDataStore.getState().setStats(null);
    expect(useDataStore.getState().stats).toBeNull();
  });

  it("多次 setStats 覆盖之前的统计数据", () => {
    useDataStore.getState().setStats({ db_size_mb: 100 } as DataStats);
    useDataStore.getState().setStats({ db_size_mb: 200 } as DataStats);
    expect(useDataStore.getState().stats!.db_size_mb).toBe(200);
  });
});
