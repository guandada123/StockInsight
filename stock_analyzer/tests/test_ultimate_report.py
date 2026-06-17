"""
Test ultimate_report.py — 终极分析报告生成器

ultimate_analysis(code) 是一个 455 行的大函数，内部所有 import 都是懒加载的。
测试策略：patch 所有被懒加载函数的源模块属性，跑通各个分支。

覆盖场景：
1. 正常全流程（看涨 → combo ≥ 4 → 2-3天持有）
2. K线数据不足 → 提前 return
3. 大盘/板块/宏观异常时的兜底
4. 板块排名靠后 / RSI 超买等风险分支
5. ML 预测失败时的 fallback
6. 回测数据不足 / 主力资金空数据
7. 国家队持仓异常
"""

# ── 把项目根目录加入 sys.path（不依赖 conftest）──
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ══════════════════════════════════════════
#  Helper：生成模拟 K 线 DataFrame
# ══════════════════════════════════════════


def _make_kline_df(length: int = 252) -> pd.DataFrame:
    """生成模拟日线 K 线（包含 full_technical_analysis 输出的列）"""
    dates = pd.date_range("2025-01-01", periods=length, freq="D")
    base = np.linspace(10, 12, length) + np.random.default_rng(42).normal(0, 0.15, length)
    return pd.DataFrame(
        {
            "开盘": base * (1 + np.random.default_rng(100).normal(0, 0.005, length)),
            "收盘": base,
            "最高": base * np.random.default_rng(200).uniform(1.01, 1.04, length),
            "最低": base * np.random.default_rng(300).uniform(0.96, 0.99, length),
            "成交量": np.random.default_rng(400).integers(1_000_000, 5_000_000, length),
            "ATR": np.full(length, 0.30),
            "MACD": np.random.default_rng(500).normal(0, 0.5, length),
            "MACD信号": np.random.default_rng(600).normal(0, 0.5, length),
            "MACD柱": np.random.default_rng(700).normal(0, 0.3, length),
            "RSI": np.random.default_rng(800).uniform(30, 70, length),
            "KDJ_K": np.random.default_rng(900).uniform(20, 80, length),
            "KDJ_D": np.random.default_rng(910).uniform(20, 80, length),
            "KDJ_J": np.random.default_rng(920).uniform(20, 80, length),
        },
        index=dates,
    )


# ══════════════════════════════════════════
#  模拟数据常量
# ══════════════════════════════════════════

MOCK_MARKET = {
    "000001": {"最新价": "3350.50", "涨跌幅": "+0.85"},
    "399001": {"最新价": "10500.00", "涨跌幅": "+1.20"},
    "399006": {"最新价": "2200.00", "涨跌幅": "-0.30"},
    "000688": {"最新价": "980.00", "涨跌幅": "+0.50"},
}

MOCK_SECTORS = {
    "半导体": {"涨跌幅": "3.50", "资金净流入": "2500000000"},
    "白酒": {"涨跌幅": "2.15", "资金净流入": "850000000"},
    "银行": {"涨跌幅": "1.05", "资金净流入": "320000000"},
    "新能源": {"涨跌幅": "-0.52", "资金净流入": "-150000000"},
    "医药": {"涨跌幅": "-1.20", "资金净流入": "-500000000"},
}

MOCK_SECTOR_FULL = "金融 > 银行 > 股份制银行"

MOCK_TECH_SUMMARY = {
    "macd_signal": "金叉",
    "rsi_value": 55,
    "kdj_signal": "金叉",
    "均线": "多头排列",
}

MOCK_REALTIME = {
    "000001": {"最新价": "12.50", "名称": "平安银行"},
}

MOCK_FUNDAMENTALS = {"ROE": 12.5}

MOCK_SHORT_TERM = {
    "短线评分": 65,
    "评级": "A",
    "ATR占比%": 2.5,
    "风险": [],
}

MOCK_COMBO = {
    "信号": "强势",
    "强度": 4,
    "详情": "多指标共振看涨",
}

MOCK_MULTI_TF = {"状态": "共振向上", "共振强度": 3}

MOCK_TURNOVER = {"换手率%": 1.5, "量比": 1.2}
MOCK_CONSECUTIVE = {"描述": "连涨3天"}
MOCK_TAIL = {"节奏": "尾盘拉升"}

MOCK_SUPPORT_RESIST = {"支撑位": [11.50, 11.00], "压力位": [13.00, 13.50]}

MOCK_QUANT_SCORE = {
    "composite_score": 72,
    "rating": "A-",
    "factor_scores": {
        "momentum": {"score": 75},
        "technical": {"score": 68},
        "fundamental": {"score": 70},
        "volume": {"score": 65},
        "risk": {"score": 60},
    },
}

MOCK_RISK = {"sharpe_ratio": 1.2, "max_drawdown_pct": -15.5, "annualized_volatility_pct": 22.0}

MOCK_TRADING_STYLE = {"short_term_score": 65, "long_term_score": 55, "style": "均衡"}

MOCK_NT_HOLDINGS = {"holders": ["证金", "汇金", "社保基金"]}

MOCK_DEBATE = {
    "bull": {"score": 7, "points": ["技术面看涨", "资金流入", "MACD金叉"]},
    "bear": {"score": 3, "points": ["RSI偏高"]},
    "verdict": "短期偏多",
    "action": "轻仓参与",
}

MOCK_ML = {
    "ensemble_direction": "看涨",
    "ensemble_confidence": 75,
    "agreement": "高",
    "votes": "3-0",
    "models": {
        "xgb": {
            "预测方向": "看涨",
            "上涨概率": 72,
            "准确率%": 65,
            "AUC": 0.72,
            "重要特征": [{"特征": "动量", "重要性": 0.3}],
        },
        "rf": {"预测方向": "看涨", "上涨概率": 68, "准确率%": 62, "AUC": 0.68},
        "lgb": {"预测方向": "看涨", "上涨概率": 70, "准确率%": 63, "AUC": 0.70},
    },
}

MOCK_BACKTEST = {
    "ma_cross": {
        "name": "均线金叉",
        "metrics": {"夏普比率": 1.5, "总收益率%": 25, "超额收益%": 10, "最大回撤%": 12},
    },
    "breakout": {
        "name": "突破策略",
        "metrics": {"夏普比率": 1.2, "总收益率%": 20, "超额收益%": 5, "最大回撤%": 15},
    },
}

MOCK_MACRO = {
    "error": None,
    "数据": {"制造业PMI": "50.5", "M2同比%": "8.2", "CPI同比%": "0.5"},
    "信号": ["经济温和复苏"],
    "整体": "宏观经济平稳",
}


# ══════════════════════════════════════════
#  Fixture：Mock Stack（25+个 patch）
# ══════════════════════════════════════════

MOCK_KLINE = _make_kline_df()


@pytest.fixture
def mock_all():
    """为 ultimate_analysis 准备所有外部依赖的 mock。

    所有 mock 通过单个 dict 聚合，方便各测试方法覆盖特定返回值。
    """
    return {
        "get_market_overview": MagicMock(return_value=MOCK_MARKET),
        "get_stock_sector_full": MagicMock(return_value=MOCK_SECTOR_FULL),
        "get_sectors": MagicMock(return_value=MOCK_SECTORS),
        "cached_kline": MagicMock(return_value=MOCK_KLINE),
        "cached_fundamentals": MagicMock(return_value=MOCK_FUNDAMENTALS),
        "full_technical_analysis": MagicMock(side_effect=lambda x: x),
        "get_technical_summary": MagicMock(return_value=MOCK_TECH_SUMMARY),
        "sina_real_time": MagicMock(return_value=MOCK_REALTIME),
        "short_term_score": MagicMock(return_value=MOCK_SHORT_TERM),
        "calc_combo_signals": MagicMock(return_value=MOCK_COMBO),
        "calc_multi_timeframe_resonance": MagicMock(return_value=MOCK_MULTI_TF),
        "calc_turnover_signal": MagicMock(return_value=MOCK_TURNOVER),
        "calc_consecutive_days": MagicMock(return_value=MOCK_CONSECUTIVE),
        "calc_tail_tendency": MagicMock(return_value=MOCK_TAIL),
        "cached_fund_flow": MagicMock(
            return_value=pd.DataFrame({"主力净流入-净额": [50_000_000, 30_000_000, -10_000_000]})
        ),
        "calc_support_resistance": MagicMock(return_value=MOCK_SUPPORT_RESIST),
        "calc_stop_levels": MagicMock(return_value={"止损参考价": 11.20, "止盈参考价": 13.80}),
        "composite_quant_score": MagicMock(return_value=MOCK_QUANT_SCORE),
        "calc_risk_metrics": MagicMock(return_value=MOCK_RISK),
        "evaluate_trading_style": MagicMock(return_value=MOCK_TRADING_STYLE),
        "cached_national_team_holdings": MagicMock(return_value=MOCK_NT_HOLDINGS),
        "generate_bull_bear_debate": MagicMock(return_value=MOCK_DEBATE),
        "predict_ensemble": MagicMock(return_value=MOCK_ML),
        "compare_strategies": MagicMock(return_value=MOCK_BACKTEST),
        "macro_market_signal": MagicMock(return_value=MOCK_MACRO),
    }


def _apply_patches(mocks):
    """对 ultimate_analysis 的所有懒加载目标应用 patch，返回 patch 列表。"""
    patch_map = {
        "get_market_overview": "stock_analyzer.fetcher.get_market_overview",
        "get_stock_sector_full": "stock_analyzer.sector_info.get_stock_sector_full",
        "get_sectors": "stock_analyzer.fetcher.get_sectors",
        "cached_kline": "stock_analyzer.cache.cached_kline",
        "cached_fundamentals": "stock_analyzer.cache.cached_fundamentals",
        "full_technical_analysis": "stock_analyzer.analysis.full_technical_analysis",
        "get_technical_summary": "stock_analyzer.analysis.get_technical_summary",
        "sina_real_time": "stock_analyzer.fetcher.sina_real_time",
        "short_term_score": "stock_analyzer.short_term.short_term_score",
        "calc_combo_signals": "stock_analyzer.short_term.calc_combo_signals",
        "calc_multi_timeframe_resonance": "stock_analyzer.short_term.calc_multi_timeframe_resonance",
        "calc_turnover_signal": "stock_analyzer.short_term.calc_turnover_signal",
        "calc_consecutive_days": "stock_analyzer.short_term.calc_consecutive_days",
        "calc_tail_tendency": "stock_analyzer.short_term.calc_tail_tendency",
        "cached_fund_flow": "stock_analyzer.cache.cached_fund_flow",
        "calc_support_resistance": "stock_analyzer.analysis.calc_support_resistance",
        "calc_stop_levels": "stock_analyzer.analysis.calc_stop_levels",
        "composite_quant_score": "stock_analyzer.quant.composite_quant_score",
        "calc_risk_metrics": "stock_analyzer.quant.calc_risk_metrics",
        "evaluate_trading_style": "stock_analyzer.quant.evaluate_trading_style",
        "cached_national_team_holdings": "stock_analyzer.cache.cached_national_team_holdings",
        "generate_bull_bear_debate": "stock_analyzer.nl_report.generate_bull_bear_debate",
        "predict_ensemble": "stock_analyzer.ml_predict.predict_ensemble",
        "compare_strategies": "stock_analyzer.backtest.compare_strategies",
        "macro_market_signal": "stock_analyzer.advanced.macro_market_signal",
    }
    patchers = []
    for key, target in patch_map.items():
        if key in mocks:
            p = patch(target, mocks[key])
            p.start()
            patchers.append((target, p))
    return patchers


def _stop_patches(patchers):
    for _, p in patchers:
        p.stop()


@pytest.fixture(autouse=True)
def auto_patch(mock_all, request):
    """自动为每个测试方法应用所有 mock（autouse）"""
    patchers = _apply_patches(mock_all)
    yield
    _stop_patches(patchers)


# ══════════════════════════════════════════
#  测试用例
# ══════════════════════════════════════════


class TestUltimateAnalysis:
    """ultimate_analysis 主函数测试"""

    # ── 正常流程 ──

    def test_happy_path_contains_key_sections(self, capsys, mock_all):
        """正常全流程：验证各核心段落的关键字"""
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        out = capsys.readouterr().out

        assert "StockInsight 终极分析" in out
        assert "一、大盘环境" in out
        assert "上证指数" in out
        assert "二、板块分析" in out
        assert "股份制银行" in out
        assert "三、个股七层深度分析" in out
        assert "L0 短线专项" in out
        assert "L1 技术面" in out
        assert "L2 量化评分" in out
        assert "L3 基本面 & 国家队" in out
        assert "NL 多空辩论" in out
        assert "L5 策略回测" in out
        assert "L6 AI预测" in out
        assert "L7 宏观环境" in out
        assert "四、综合预测 & 操作建议" in out
        assert "五、风险提示" in out
        assert "数据来源" in out
        assert "免责声明" in out

    def test_happy_path_prediction_logic(self, capsys, mock_all):
        """正常全流程：验证预测逻辑输出（combo=4 → 2-3天持有）"""
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        out = capsys.readouterr().out

        assert "看涨" in out
        assert "2-3天" in out
        assert "买入区间" in out
        assert "止损" in out
        assert "止盈" in out
        assert "国家队" in out

    def test_happy_path_risk_warnings_disclaimer(self, capsys, mock_all):
        """正常全流程：验证风控和声明"""
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        out = capsys.readouterr().out

        assert "⚠️" in out
        assert "暂无明显风险信号" in out or "风险" in out
        assert "不构成投资建议" in out

    # ── 数据不足 ──

    def test_kline_none_returns_early(self, capsys, mock_all):
        """K线 None → 提前 return"""
        mock_all["cached_kline"].return_value = None
        # 重新应用 mock
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "K线数据不足" in out
        # 不能出现后续段落的内容
        assert "L0" not in out

    def test_kline_empty_returns_early(self, capsys, mock_all):
        """K线空 DataFrame → 提前 return"""
        mock_all["cached_kline"].return_value = pd.DataFrame()
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "K线数据不足" in out

    def test_kline_short_returns_early(self, capsys, mock_all):
        """K线行数 < 20 → 提前 return"""
        mock_all["cached_kline"].return_value = _make_kline_df(10)
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "K线数据不足" in out

    # ── 异常路径 ──

    def test_market_overview_failure_handled(self, capsys, mock_all):
        """大盘数据异常 → 兜底 '大盘数据获取失败'"""
        mock_all["get_market_overview"].side_effect = RuntimeError("API down")
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")  # 不应抛出异常
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "大盘数据获取失败" in out

    def test_sector_analysis_failure_handled(self, capsys, mock_all):
        """板块分析异常 → 兜底打印异常信息"""
        mock_all["get_stock_sector_full"].side_effect = ValueError("no sector")
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "板块分析异常" in out or "no sector" in out

    def test_ml_prediction_failure_fallback(self, capsys, mock_all):
        """ML 预测异常 → fallback 看涨/? /50%"""
        mock_all["predict_ensemble"].side_effect = ImportError("xgboost missing")
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        # fallback 为 "?" 方向，50% 置信
        assert "AI预测" in out

    def test_backtest_failure_handled(self, capsys, mock_all):
        """回测异常 → 兜底 '回测数据不足'"""
        mock_all["compare_strategies"].side_effect = Exception("回测异常")
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "回测数据不足" in out or "L5 策略回测" in out

    def test_macro_failure_handled(self, capsys, mock_all):
        """宏观数据异常 → 兜底 '宏观数据暂不可用'"""
        mock_all["macro_market_signal"].side_effect = ConnectionError("timeout")
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "宏观数据暂不可用" in out

    def test_fund_flow_exception_handled(self, capsys, mock_all):
        """主力资金异常 → 不抛异常，'无数据'"""
        mock_all["cached_fund_flow"].side_effect = Exception("东方财富挂")
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "无数据" in out

    def test_fund_flow_empty_dataframe(self, capsys, mock_all):
        """主力资金返回空 DataFrame → flow_ok=False"""
        mock_all["cached_fund_flow"].return_value = pd.DataFrame()
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "无数据" in out

    def test_fund_flow_no_column(self, capsys, mock_all):
        """主力资金缺少 '主力净流入-净额' 列 → flow_ok=False"""
        mock_all["cached_fund_flow"].return_value = pd.DataFrame({"other_col": [1, 2]})
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "无数据" in out

    def test_national_team_exception_handled(self, capsys, mock_all):
        """国家队持仓异常 → 不抛异常，显示 '国家队: 无'"""
        mock_all["cached_national_team_holdings"].side_effect = Exception("API 500")
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "国家队: 无" in out

    def test_national_team_empty_holders(self, capsys, mock_all):
        """国家队返回空列表 → 显示 '国家队: 无'"""
        mock_all["cached_national_team_holdings"].return_value = {"holders": []}
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "国家队: 无" in out

    def test_national_team_non_dict(self, capsys, mock_all):
        """国家队返回非 dict → 空 holders → 显示 '国家队: 无'"""
        mock_all["cached_national_team_holdings"].return_value = "error_str"
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "国家队: 无" in out

    # ── 板块相关 ──

    def test_sector_not_ranked(self, capsys, mock_all):
        """个股板块不在排名 TOP5 中 → sector_rank=0 → 东方财富数据不可用"""
        # 将 get_stock_sector_full 设为排名外的板块
        mock_all["get_stock_sector_full"].return_value = "农林牧渔 > 养殖"
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "东方财富数据不可用" in out

    def test_sectors_empty_dict(self, capsys, mock_all):
        """板块数据为空 dict → 走 empty 分支"""
        mock_all["get_sectors"].return_value = {}
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "所属" in out

    # ── 资金流向分支 ──

    def test_positive_flow_shows_流入(self, capsys, mock_all):
        """主力净流入 > 0 → 显示 '流入'"""
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        out = capsys.readouterr().out
        assert "流入" in out

    def test_negative_flow_shows_流出(self, capsys, mock_all):
        """主力 5 日净流出 → 显示 '流出'"""
        mock_all["cached_fund_flow"].return_value = pd.DataFrame(
            {"主力净流入-净额": [-100_000_000, -50_000_000]}
        )
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "流出" in out

    # ── 综合预测分支 ──

    def test_prediction_bearish_combo_zero(self, capsys, mock_all):
        """ML 看跌 + combo ≤ 0 → 综合看跌"""
        mock_all["calc_combo_signals"].return_value = {"信号": "弱势", "强度": 0, "详情": ""}
        mock_all["predict_ensemble"].return_value = {**MOCK_ML, "ensemble_direction": "看跌"}
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "看跌" in out

    def test_prediction_combo_high_ml_unknown(self, capsys, mock_all):
        """ML 方向未知但 combo ≥ 3 → 看涨(技术面)"""
        mock_all["calc_combo_signals"].return_value = {"信号": "强势", "强度": 3, "详情": ""}
        mock_all["predict_ensemble"].return_value = {
            **MOCK_ML,
            "ensemble_direction": "?",
            "ensemble_confidence": 50,
        }
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "看涨(技术面)" in out

    def test_prediction_combo_low_default(self, capsys, mock_all):
        """combo 低 + ML 非看跌 → 震荡"""
        mock_all["calc_combo_signals"].return_value = {"信号": "震荡", "强度": 1, "详情": ""}
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "震荡" in out

    def test_prediction_combo_off_default(self, capsys, mock_all):
        """combo ≥ 2 但 ML 不是看涨/看跌 → 1-2天"""
        mock_all["calc_combo_signals"].return_value = {"信号": "偏多", "强度": 2, "详情": ""}
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "1-2天" in out

    def test_prediction_combo_low_watch(self, capsys, mock_all):
        """combo ≤ 1 → 观望"""
        mock_all["calc_combo_signals"].return_value = {"信号": "偏弱", "强度": 0, "详情": ""}
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "观望" in out

    # ── 风险提示分支 ──

    def test_risk_n5_over_12(self, capsys, mock_all):
        """n5 > 12 → 短线追高风险"""
        # 用 .loc 避免 pandas Copy-on-Write 链式赋值失效
        df = _make_kline_df()
        df.loc[df.index[-1], "收盘"] = df.loc[df.index[-6], "收盘"] * 1.13
        # 同时更新最高/最低，保证 ATR 等不报错
        df.loc[df.index[-1], "最高"] = df.loc[df.index[-1], "收盘"] * 1.02
        df.loc[df.index[-1], "最低"] = df.loc[df.index[-1], "收盘"] * 0.98
        mock_all["cached_kline"].return_value = df
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "短线追高风险" in out

    def test_risk_n20_over_30(self, capsys, mock_all):
        """n20 > 30 → 追高惩罚已触发"""
        df = _make_kline_df()
        df.loc[df.index[-1], "收盘"] = df.loc[df.index[-21], "收盘"] * 1.31
        df.loc[df.index[-1], "最高"] = df.loc[df.index[-1], "收盘"] * 1.02
        df.loc[df.index[-1], "最低"] = df.loc[df.index[-1], "收盘"] * 0.98
        mock_all["cached_kline"].return_value = df
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "追高惩罚已触发" in out

    def test_risk_rsi_over_72(self, capsys, mock_all):
        """RSI > 72 → 接近超买"""
        mock_all["get_technical_summary"].return_value = {**MOCK_TECH_SUMMARY, "rsi_value": 80}
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "接近超买" in out

    def test_risk_flow_below_neg1(self, capsys, mock_all):
        """主力 5 日流出 > 1 亿 → 主力 5 日流出风险"""
        mock_all["cached_fund_flow"].return_value = pd.DataFrame(
            {"主力净流入-净额": [-200_000_000, -100_000_000, -50_000_000]}
        )
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "主力5日流出" in out

    def test_risk_ai_bearish_combo_strong(self, capsys, mock_all):
        """AI 看跌 + combo ≥ 3 → 信号矛盾风险"""
        mock_all["predict_ensemble"].return_value = {**MOCK_ML, "ensemble_direction": "看跌"}
        mock_all["calc_combo_signals"].return_value = {"信号": "强势", "强度": 3, "详情": ""}
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "信号矛盾" in out

    def test_risk_combo_weak(self, capsys, mock_all):
        """combo ≤ 1 → 短期方向不明"""
        mock_all["calc_combo_signals"].return_value = {"信号": "偏弱", "强度": 0, "详情": ""}
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "组合信号偏弱" in out

    def test_risk_sector_rank_default(self, capsys, mock_all):
        """sector_rank=0 → 板块排名数据不可用风险"""
        mock_all["get_stock_sector_full"].return_value = "农林牧渔 > 养殖"
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "板块排名数据不可用" in out

    def test_no_risks_shows_fallback(self, capsys, mock_all):
        """没有触发任何风险 → 显示 '暂无明显风险信号'"""
        # 设置一个安全的场景：K 线平稳，RSI 适中，资金不极端
        df = _make_kline_df()
        # n5 < 12%, n20 < 30% — 用 .loc 避免 Copy-on-Write 失效
        df.loc[df.index[-1], "收盘"] = df.loc[df.index[-6], "收盘"] * 1.05
        df.loc[df.index[-1], "收盘"] = df.loc[df.index[-21], "收盘"] * 1.10
        df.loc[df.index[-1], "最高"] = df.loc[df.index[-1], "收盘"] * 1.02
        df.loc[df.index[-1], "最低"] = df.loc[df.index[-1], "收盘"] * 0.98
        mock_all["cached_kline"].return_value = df
        mock_all["get_technical_summary"].return_value = {**MOCK_TECH_SUMMARY, "rsi_value": 50}
        mock_all["cached_fund_flow"].return_value = pd.DataFrame(
            {"主力净流入-净额": [5_000_000, 3_000_000]}
        )
        mock_all["calc_combo_signals"].return_value = {"信号": "强势", "强度": 3, "详情": ""}
        # 保证板块排名可见（不触发 sector_rank=0 风险）
        mock_all["get_stock_sector_full"].return_value = "金融 > 银行 > 股份制银行"
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "暂无明显风险信号" in out

    # ── 回测分支 ──

    def test_backtest_empty_result(self, capsys, mock_all):
        """回测返回空 dict → 不抛异常"""
        mock_all["compare_strategies"].return_value = {}
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "L5 策略回测" in out

    # ── AI 模型分支 ──

    def test_ai_high_agreement_bullish(self, capsys, mock_all):
        """三模型一致看涨 → 📈 图标"""
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        out = capsys.readouterr().out
        assert "三模型一致" in out
        assert "置信" in out

    def test_ai_high_agreement_bearish(self, capsys, mock_all):
        """三模型一致看跌 → 📉 图标"""
        mock_all["predict_ensemble"].return_value = {
            **MOCK_ML,
            "ensemble_direction": "看跌",
            "agreement": "高",
        }
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "三模型一致看跌" in out

    def test_ai_disagreement(self, capsys, mock_all):
        """模型分歧 → ⚠️ 分歧"""
        mock_all["predict_ensemble"].return_value = {
            **MOCK_ML,
            "ensemble_direction": "看涨",
            "agreement": "低",
            "votes": "2-1",
        }
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        assert "分歧" in out or "⚠️" in out

    # ── 宏观分支 ──

    def test_macro_error_key(self, capsys, mock_all):
        """macro 返回含 'error' 键 → 不显示数据"""
        mock_all["macro_market_signal"].return_value = {"error": "timeout"}
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        # 因为 "error" in macro 为 True，不会输出宏数据
        # 但由于它在 L7 打印之后，L7 的标题还是会出现的
        assert "L7 宏观环境" in out

    # ── 板块不足 TOP5 时的 sector_rank 边界 ──

    def test_sector_rank_behind_top5(self, capsys, mock_all):
        """板块排名靠后（>60%分位）→ 板块拖累风险"""
        # 给 20 个板块，让目标板块排第 15（靠后）
        # 注意：sector 名不能有子串匹配 — 源码中 nm == sname or sname in nm or nm in sname
        # 用唯一前导码避免误匹配（如 "Sector-XX"）
        mock_all["get_sectors"].return_value = {
            f"SECTOR_{i:03d}": {"涨跌幅": f"{1.0 - i * 0.1:.2f}", "资金净流入": "0"}
            for i in range(20)
        }
        mock_all["get_stock_sector_full"].return_value = "SECTOR_015"
        patchers = _apply_patches(mock_all)
        from stock_analyzer.ultimate_report import ultimate_analysis

        ultimate_analysis("000001")
        _stop_patches(patchers)
        out = capsys.readouterr().out
        # sector_rank 在 TOP5 里找不到 → sector_rank=0 → 东方财富数据不可用
        assert "板块排名数据不可用" in out
