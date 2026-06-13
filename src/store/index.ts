import { create } from "zustand";
import type { MarketIndex, StockAnalysisResult, PortfolioData, DataStats } from "../types/api";

// 市场状态
interface MarketState {
  indices: Record<string, MarketIndex>;
  updateTime: string;
  setIndices: (data: Record<string, MarketIndex>) => void;
}

export const useMarketStore = create<MarketState>((set) => ({
  indices: {},
  updateTime: "",
  setIndices: (data) => set({ indices: data, updateTime: new Date().toLocaleTimeString("zh-CN") }),
}));

// 分析状态
interface AnalysisState {
  currentCode: string;
  result: StockAnalysisResult | null;
  loading: boolean;
  setCode: (code: string) => void;
  setResult: (r: StockAnalysisResult | null) => void;
  setLoading: (v: boolean) => void;
}

export const useAnalysisStore = create<AnalysisState>((set) => ({
  currentCode: "",
  result: null,
  loading: false,
  setCode: (code) => set({ currentCode: code }),
  setResult: (r) => set({ result: r }),
  setLoading: (v) => set({ loading: v }),
}));

// 持仓状态
interface PortfolioState {
  data: PortfolioData | null;
  loading: boolean;
  setData: (d: PortfolioData | null) => void;
  setLoading: (v: boolean) => void;
}

export const usePortfolioStore = create<PortfolioState>((set) => ({
  data: null,
  loading: false,
  setData: (d) => set({ data: d }),
  setLoading: (v) => set({ loading: v }),
}));

// 数据状态
interface DataState {
  stats: DataStats | null;
  setStats: (s: DataStats | null) => void;
}

export const useDataStore = create<DataState>((set) => ({
  stats: null,
  setStats: (s) => set({ stats: s }),
}));
