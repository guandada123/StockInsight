"""测试 backend/services/analysis_service.py

策略：
  - 纯 builder 函数：构造 mock r dict 直接测
  - 外部依赖（_run_analysis / run_fast_analysis / build_*_data）：mock stock_analyzer 函数
  - cached_analysis：mock _run_analysis，测缓存命中/过期
"""

from unittest import mock

import pytest

from backend.services import analysis_service as svc

# ════════════════════════════════════════════
# 测试辅助：构建模拟分析结果 dict
# ════════════════════════════════════════════


def _make_kline():
    """构建模拟 K 线 DataFrame"""
    import numpy as np
    import pandas as pd

    dates = pd.date_range(end="2026-06-19", periods=100, freq="D")
    np.random.seed(42)
    return pd.DataFrame(
        {
            "日期": dates,
            "开盘": np.random.uniform(10, 12, 100),
            "最高": np.random.uniform(11, 13, 100),
            "最低": np.random.uniform(9, 11, 100),
            "收盘": np.random.uniform(10, 12, 100),
            "成交量": np.random.randint(1e6, 1e8, 100),
            "DIF": np.random.uniform(-0.5, 0.5, 100),
            "DEA": np.random.uniform(-0.3, 0.3, 100),
            "MACD": np.random.uniform(-0.2, 0.2, 100),
            "RSI": np.random.uniform(30, 70, 100),
            "K": np.random.uniform(20, 80, 100),
            "D": np.random.uniform(20, 80, 100),
            "J": np.random.uniform(20, 80, 100),
            "ADX": np.random.uniform(15, 40, 100),
            "ATR": np.full(100, 0.5),
        }
    )


def _make_analysis_result(code="000001", name="测试股票", price=11.5, full=True):
    """构建一个完整的模拟分析结果 dict（模拟 deep_analyze 的输出）"""
    kline = _make_kline()
    return {
        "_kline": kline,
        "price": price,
        "atr": 0.5,
        "macd_signal": "MACD金叉",
        "kdj_signal": "KDJ金叉",
        "rsi": 55,
        "qs_composite": 62,
        "qs_rating": "谨慎看多",
        "mom_s": 60,
        "tech_s": 65,
        "fund_s": 50,
        "vol_s": 55,
        "risk_s": 45,
        "sharpe": 1.2,
        "max_dd": -15.5,
        "volatility": 22.3,
        "var95": -3.2,
        "fundamentals": {
            "ROE": 12.5,
            "市盈率": 15.0,
            "市净率": 2.1,
            "每股收益": 0.85,
            "毛利率": 35.0,
            "净利率": 12.0,
            "营收增长": 8.5,
            "净利润增长": 10.2,
        },
        "fund_flow_total": 5e6,
        "signals": {
            "bias": "bullish",
            "score": 3,
            "combo_strength": 3,
            "details": ["MACD金叉", "量价配合"],
        },
        "stop_levels": {"止损参考价": 10.5, "止盈参考价": 12.5},
        "support": [10.8, 10.5],
        "resistance": [12.2, 12.8],
        "stop_loss": 10.5,
        "stop_profit": 12.5,
        "near_5d": 3.5,
        "near_20d": 8.2,
        "short_score": 30,
        "long_score": 60,
        "style": "成长",
        "nt_holders": ["证金", "汇金"],
        "signal_bias": "bullish",
    }


def _make_info(price=11.5):
    """模拟新浪实时行情 dict"""
    return {
        "名称": "测试股票",
        "最新价": str(price),
        "今开": "11.2",
        "最高": "11.8",
        "最低": "11.0",
        "昨收": "11.3",
        "振幅": "3.5",
        "成交量": "50000000",
        "换手率": "0.85",
    }


# ════════════════════════════════════════════
# Pure Builder 函数
# ════════════════════════════════════════════


class TestBuildQuote:
    """_build_quote — 行情快照 builder"""

    def test_basic(self):
        """基本信息拼接"""
        r = _make_analysis_result()
        info = _make_info(price=11.5)
        result = svc._build_quote("000001", "测试股票", info, 11.5, r)

        assert result["code"] == "000001"
        assert result["name"] == "测试股票"
        assert result["price"] == 11.5
        assert result["open"] == 11.2

    def test_change_calculation(self):
        """涨跌额/涨跌幅计算正确"""
        info = _make_info(price=12.0)
        info["昨收"] = "10.0"
        result = svc._build_quote("000001", "测试", info, 12.0, None)

        assert result["change"] == 2.0
        assert result["change_pct"] == 20.0

    def test_prev_close_zero_protection(self):
        """昨收缺失时避免除零"""
        info = _make_info(price=10.0)
        info["昨收"] = ""  # 空字符串触发 or price 回退
        result = svc._build_quote("000001", "测试", info, 10.0, None)

        assert result["change_pct"] == 0.0

    def test_missing_fields_default_to_zero(self):
        """缺失字段默认 0"""
        result = svc._build_quote("000001", "测试", {}, 0, None)
        assert result["price"] == 0
        assert result["change_pct"] == 0.0


class TestBuildTechnical:
    """_build_technical — 技术指标 builder"""

    def test_with_kline(self):
        """有 K 线时读取最新指标值"""
        r = _make_analysis_result()

        tech_sum = {"均线": "多头排列"}
        sr = {"支撑位": [10.5, 10.2], "压力位": [12.5, 13.0]}
        result = svc._build_technical(r, tech_sum, sr)

        assert result["ma_status"] == "多头排列"
        assert result["macd_signal"] == "MACD金叉"
        assert result["kdj_signal"] == "KDJ金叉"
        assert result["rsi_value"] == 55
        assert result["atr"] == 0.5

    def test_without_kline(self):
        """无 K 线时返回 None 指标"""
        r = {"macd_signal": "", "kdj_signal": "", "rsi": 50, "atr": 0, "_kline": None}
        result = svc._build_technical(r, None, None)

        assert result["macd_dif"] is None
        assert result["macd_dea"] is None
        assert result["adx"] is None


class TestBuildQuant:
    """_build_quant — 量化评分 builder"""

    def test_scores(self):
        """因子评分映射正确"""
        r = _make_analysis_result()
        result = svc._build_quant(r)

        assert result["composite"] == 62
        assert result["rating"] == "谨慎看多"
        assert result["factor_scores"]["momentum"] == 60
        assert result["factor_scores"]["technical"] == 65
        assert result["factor_scores"]["fundamental"] == 50


class TestBuildRisk:
    """_build_risk — 风险指标 builder"""

    def test_risk_metrics(self):
        """风险指标映射"""
        r = _make_analysis_result()
        result = svc._build_risk(r)

        assert result["sharpe_ratio"] == 1.2
        assert result["max_drawdown_pct"] == -15.5
        assert result["annual_volatility_pct"] == 22.3
        assert result["var_95_pct"] == -3.2

    def test_zeros(self):
        """无数据时默认 0"""
        result = svc._build_risk({})
        assert result["sharpe_ratio"] == 0


class TestBuildFinancial:
    """_build_financial — 基本面 builder"""

    def test_with_funds(self):
        """有基本面数据"""
        r = _make_analysis_result()
        result = svc._build_financial(r)

        assert result["roe"] == 12.5
        assert result["pe"] == 15.0

    def test_funds_not_dict(self):
        """fundamentals 不是 dict 时安全处理"""
        r = {"fundamentals": None}
        result = svc._build_financial(r)
        assert result["roe"] is None

    def test_missing_roe(self):
        """ROE 缺失时返回 None"""
        r = {"fundamentals": {"pe": 15}}
        result = svc._build_financial(r)
        assert result["roe"] is None


class TestBuildSignal:
    """_build_signal — 信号 builder"""

    def test_signals(self):
        """信号映射"""
        r = _make_analysis_result()
        result = svc._build_signal(r)

        assert result["bias"] == "bullish"
        assert result["score"] == 3
        assert result["combo_strength"] == 3
        assert len(result["details"]) == 2

    def test_no_signals(self):
        """无信号时返回中性"""
        result = svc._build_signal({})
        assert result["bias"] == "neutral"
        assert result["score"] == 0


class TestSafeConvert:
    """safe_convert — numpy→Python 递归转换"""

    def test_numpy_int(self):
        """numpy int 转 Python int"""
        import numpy as np

        assert svc.safe_convert(np.int32(42)) == 42
        assert isinstance(svc.safe_convert(np.int32(42)), int)

    def test_numpy_float(self):
        """numpy float 转 Python float"""
        import numpy as np

        assert svc.safe_convert(np.float64(3.14)) == 3.14
        assert isinstance(svc.safe_convert(np.float64(3.14)), float)

    def test_numpy_array(self):
        """numpy array 转 list"""
        import numpy as np

        result = svc.safe_convert(np.array([1, 2, 3]))
        assert result == [1, 2, 3]

    def test_dict_recursive(self):
        """嵌套 dict 递归转换"""
        import numpy as np

        data = {"a": np.int32(1), "b": {"c": np.float64(2.5)}}
        result = svc.safe_convert(data)
        assert result == {"a": 1, "b": {"c": 2.5}}

    def test_list_recursive(self):
        """嵌套 list 递归转换"""
        import numpy as np

        result = svc.safe_convert([np.int32(1), np.float64(2.5)])
        assert result == [1, 2.5]

    def test_python_types_passthrough(self):
        """原生 Python 类型不变"""
        assert svc.safe_convert("hello") == "hello"
        assert svc.safe_convert(42) == 42
        assert svc.safe_convert(3.14) == 3.14
        assert svc.safe_convert(None) is None


class TestBuildOperationAdvice:
    """_build_operation_advice — 操作建议"""

    def test_buy_signal(self):
        """高 quant + bullish → 买入"""
        r = _make_analysis_result()
        r["qs_composite"] = 70
        r["signal_bias"] = "bullish"
        r["near_20d"] = 10

        result = svc._build_operation_advice(r)
        assert result["direction"] == "买入"
        assert result["direction_color"] == "green"
        assert result["position_pct"] == 60
        assert result["holding_days"] == "1-2天"

    def test_watch_signal(self):
        """中等 quant → 观望"""
        r = _make_analysis_result()
        r["qs_composite"] = 55
        result = svc._build_operation_advice(r)
        assert result["direction"] == "观望"

    def test_reduce_signal(self):
        """低 quant → 减仓"""
        r = _make_analysis_result()
        r["qs_composite"] = 35
        result = svc._build_operation_advice(r)
        assert result["direction"] == "减仓"
        assert result["direction_color"] == "red"

    def test_overbought_risk(self):
        """RSI 超买时提示追高风险"""
        r = _make_analysis_result()
        r["rsi"] = 75
        r["qs_composite"] = 60
        result = svc._build_operation_advice(r)
        assert any("超买" in p for p in result["key_points"])

    def test_oversold_risk(self):
        """RSI 超卖时提示左侧风险"""
        r = _make_analysis_result()
        r["rsi"] = 25
        r["qs_composite"] = 60
        result = svc._build_operation_advice(r)
        assert any("超卖" in p for p in result["key_points"])

    def test_high_n5_warning(self):
        """近 5 日涨幅过大提示追高风险"""
        r = _make_analysis_result()
        r["near_5d"] = 10
        r["qs_composite"] = 60
        result = svc._build_operation_advice(r)
        assert any("短期涨幅较大" in p for p in result["key_points"])

    def test_oversold_short_term(self):
        """近 5 日超跌提示反弹关注"""
        r = _make_analysis_result()
        r["near_5d"] = -8
        r["qs_composite"] = 60
        result = svc._build_operation_advice(r)
        assert any("短期超跌" in p for p in result["key_points"])

    def test_exception_safety(self):
        """异常时返回安全默认值"""
        result = svc._build_operation_advice({})
        assert result["direction"] == "观望"
        assert result["direction_color"] == "yellow"


class TestBuildRiskWarnings:
    """_build_risk_warnings — 风险提示列表"""

    def test_high_n5(self):
        """近 5 日 >12% 触发高风险"""
        r = {"near_5d": 15, "near_20d": 5, "rsi": 50}
        risks = svc._build_risk_warnings(r)
        assert any(r["level"] == "high" for r in risks)

    def test_medium_n5(self):
        """近 5 日 8-12% 触发中风险"""
        r = {"near_5d": 10, "near_20d": 5, "rsi": 50}
        risks = svc._build_risk_warnings(r)
        assert any(r["level"] == "medium" for r in risks)

    def test_overbought(self):
        """RSI 超买"""
        r = {"near_5d": 3, "near_20d": 5, "rsi": 78}
        risks = svc._build_risk_warnings(r)
        assert any("超买" in r["message"] for r in risks)

    def test_oversold(self):
        """RSI 超卖"""
        r = {"near_5d": 3, "near_20d": 5, "rsi": 20}
        risks = svc._build_risk_warnings(r)
        assert any("超卖" in r["message"] for r in risks)

    def test_sector_red_risk(self):
        """板块弱势增加板块风险提示"""
        r = {"near_5d": 3, "near_20d": 5, "rsi": 50}
        sector = {"rank_color": "red", "sector_rank": 48}
        risks = svc._build_risk_warnings(r, sector)
        assert any("板块弱势" in r["message"] for r in risks)

    def test_sector_missing(self):
        """板块排名为 0 时提示数据缺失"""
        r = {"near_5d": 3, "near_20d": 5, "rsi": 50}
        sector = {"rank_color": "gray", "sector_rank": 0}
        risks = svc._build_risk_warnings(r, sector)
        assert any("板块排名数据缺失" in r["message"] for r in risks)

    @mock.patch("stock_analyzer.fetcher.get_fund_flow")
    def test_no_risks_returns_low(self, mock_ff):
        """无极端风险时返回 low 级别常规提示"""
        import pandas as pd

        mock_ff.return_value = pd.DataFrame({"日期": ["2026-06-19"]})
        r = {"near_5d": 3, "near_20d": 5, "rsi": 50}
        risks = svc._build_risk_warnings(r)
        assert any(r["level"] == "low" for r in risks)

    def test_always_has_disclaimer(self):
        """始终包含免责声明"""
        r = {"near_5d": 3, "near_20d": 5, "rsi": 50}
        risks = svc._build_risk_warnings(r)
        assert any("不构成投资建议" in r["message"] for r in risks)

    def test_safe_empty_result(self):
        """空 dict 不崩溃"""
        risks = svc._build_risk_warnings({})
        assert len(risks) >= 1
        assert risks[-1]["level"] == "info"


class TestBuildDataSources:
    """_build_data_sources — 数据来源"""

    def test_structure(self):
        """包含所有来源字段"""
        result = svc._build_data_sources({})
        assert "quote_source" in result
        assert "kline_source" in result
        assert "update_time" in result
        assert "disclaimer" in result

    def test_disclaimer(self):
        """包含免责声明"""
        result = svc._build_data_sources({})
        assert "不构成投资建议" in result["disclaimer"]


# ════════════════════════════════════════════
# _build_prediction
# ════════════════════════════════════════════


class TestBuildPrediction:
    """_build_prediction — 明日预测"""

    def test_bullish_prediction(self):
        """金叉 + 健康 RSI → 偏多预测"""
        r = _make_analysis_result()
        r["macd_signal"] = "MACD金叉"
        r["rsi"] = 55
        r["signals"] = {"combo_strength": 3, "bias": "bullish", "score": 2, "details": []}
        r["atr"] = 0.5

        with mock.patch(
            "stock_analyzer.ml_predict._cached_predict_ensemble",
            return_value={
                "ensemble_direction": "看涨",
                "ensemble_confidence": 75,
            },
        ):
            result = svc._build_prediction(r)

        assert result["direction"] == "看涨"
        assert result["confidence"] == 75
        assert result["price_range"]["low"] < result["price_range"]["high"]
        assert len(result["rationale"]) > 0

    def test_exception_safety(self):
        """异常时返回安全默认值"""
        with mock.patch(
            "stock_analyzer.ml_predict._cached_predict_ensemble",
            side_effect=ValueError("API error"),
        ):
            result = svc._build_prediction(_make_analysis_result())

        assert result["direction"] == "震荡"
        assert result["confidence"] == 0


# ════════════════════════════════════════════
# _build_debate / _build_ml / _build_sector_analysis
# ════════════════════════════════════════════


class TestBuildDebate:
    """_build_debate — 多空辩论"""

    @mock.patch("stock_analyzer.analysis.calc_support_resistance")
    @mock.patch("stock_analyzer.analysis.get_technical_summary")
    @mock.patch("stock_analyzer.ml_predict._cached_predict_ensemble")
    @mock.patch("stock_analyzer.nl_report.generate_bull_bear_debate")
    def test_basic_debate(
        self,
        mock_gen,
        mock_ml,
        mock_tech,
        mock_sr,
    ):
        """调用 generate_bull_bear_debate 返回结构化结果"""
        mock_tech.return_value = {"均线": "多头排列"}
        mock_sr.return_value = {"压力": [12.5], "支撑": [10.5]}
        mock_ml.return_value = {"ensemble_direction": "看涨", "ensemble_confidence": 70}
        mock_gen.return_value = {
            "bull": {"points": ["量价配合好"], "score": 7},
            "bear": {"points": ["RSI偏高"], "score": 3},
            "verdict": "偏多",
            "action": "轻仓参与",
        }

        r = _make_analysis_result()
        r["price"] = 11.5
        r["fund_flow_total"] = 5e6
        result = svc._build_debate("000001", r)

        assert result["bull_score"] == 7
        assert result["bear_score"] == 3
        assert result["verdict"] == "偏多"
        assert result["action"] == "轻仓参与"

    def test_exception_safety(self):
        """异常时返回空辩论"""
        result = svc._build_debate("000001", _make_analysis_result())
        # 没有 mock 的情况下会真实调用（或 import 出错）
        # 这里只验证异常时返回默认值
        assert isinstance(result, dict)


class TestBuildML:
    """_build_ml — ML 预测"""

    @mock.patch("stock_analyzer.ml_predict._cached_predict_ensemble")
    def test_basic(self, mock_ml):
        """ML 预测映射"""
        mock_ml.return_value = {
            "ensemble_direction": "看涨",
            "ensemble_confidence": 80,
            "votes": "3/5",
            "models": {"xgboost": {"direction": "看涨", "confidence": 85}},
        }
        r = _make_analysis_result()
        result = svc._build_ml(r)

        assert result["direction"] == "看涨"
        assert result["confidence"] == 80

    @mock.patch(
        "stock_analyzer.ml_predict._cached_predict_ensemble", side_effect=ValueError("fail")
    )
    def test_exception_safety(self, mock_ml):
        """异常时返回安全默认值"""
        result = svc._build_ml(_make_analysis_result())
        assert result["direction"] == "?"


class TestBuildSectorAnalysis:
    """_build_sector_analysis — 板块分析"""

    @mock.patch("stock_analyzer.fetcher.get_sectors")
    @mock.patch("stock_analyzer.sector_info.get_stock_concepts")
    @mock.patch("stock_analyzer.sector_info.get_stock_sector_full")
    def test_basic(
        self,
        mock_sector_full,
        mock_concepts,
        mock_sectors,
    ):
        """板块排名与评估"""
        mock_sector_full.return_value = "金融 > 银行"
        mock_concepts.return_value = ["MSCI", "证金持股"]
        mock_sectors.return_value = {
            "银行": {"涨跌幅": "2.5", "资金净流入": "500000000"},
            "白酒": {"涨跌幅": "1.2", "资金净流入": "200000000"},
            "券商": {"涨跌幅": "-0.5", "资金净流入": "-100000000"},
        }

        result = svc._build_sector_analysis("000001", _make_analysis_result())

        assert result["industry"] == "金融 > 银行"
        assert result["sector_name"] == "银行"
        assert result["sector_rank"] == 1  # 涨幅最高
        assert result["rank_color"] == "green"

    def test_exception_safety(self):
        """异常时返回安全默认值"""
        result = svc._build_sector_analysis("000001", _make_analysis_result())
        assert result["industry"] in ("未知", "金融 > 银行")


# ════════════════════════════════════════════
# cached_analysis
# ════════════════════════════════════════════


class TestCachedAnalysis:
    """cached_analysis — 缓存 + 重算"""

    def setup_method(self):
        """每次测试前清空缓存"""
        with svc._ANALYSIS_CACHE_LOCK:
            svc._ANALYSIS_CACHE.clear()

    @mock.patch.object(svc, "_run_analysis")
    def test_miss_then_hit(self, mock_run):
        """首次未命中，再次命中缓存"""
        mock_run.return_value = {"code": "000001", "name": "测试"}
        # mock 时间戳：让 TTL 不失效
        svc._CACHE_TTL = 300

        r1 = svc.cached_analysis("000001")
        r2 = svc.cached_analysis("000001")

        assert r1 == r2
        assert mock_run.call_count == 1

    @mock.patch.object(svc, "_run_analysis")
    def test_full_vs_std_cache_keys(self, mock_run):
        """full 和 std 使用不同缓存 key"""
        mock_run.side_effect = [
            {"code": "000001", "full": True},
            {"code": "000001", "full": False},
        ]

        full = svc.cached_analysis("000001", full=True)
        std = svc.cached_analysis("000001", full=False)

        assert full["full"] is True
        assert std["full"] is False
        assert mock_run.call_count == 2

    @mock.patch.object(svc, "_run_analysis")
    def test_different_codes_separate_cache(self, mock_run):
        """不同股票代码独立缓存"""
        mock_run.side_effect = [
            {"code": "000001", "name": "股票A"},
            {"code": "600519", "name": "股票B"},
        ]

        a = svc.cached_analysis("000001")
        b = svc.cached_analysis("600519")

        assert a["name"] == "股票A"
        assert b["name"] == "股票B"
        assert mock_run.call_count == 2

    @mock.patch.object(svc, "_run_analysis")
    def test_reanalysis_after_cache_clear(self, mock_run):
        """清空缓存后重新计算"""
        mock_run.return_value = {"code": "000001"}

        svc.cached_analysis("000001")
        svc._ANALYSIS_CACHE.clear()
        svc.cached_analysis("000001")

        assert mock_run.call_count == 2

    @mock.patch.object(svc, "_run_analysis")
    def test_expired_after_ttl(self, mock_run):
        """TTL 过期后重新调用"""
        import time

        mock_run.return_value = {"code": "000001", "ts": 1}
        svc._CACHE_TTL = 0.01  # 10ms TTL

        svc.cached_analysis("000001")
        time.sleep(0.02)
        mock_run.return_value = {"code": "000001", "ts": 2}
        r2 = svc.cached_analysis("000001")

        assert r2["ts"] == 2
        assert mock_run.call_count == 2

    @mock.patch.object(svc, "_run_analysis")
    def test_returns_dict(self, mock_run):
        """返回非空 dict"""
        mock_run.return_value = {"code": "000001"}
        result = svc.cached_analysis("000001")
        assert isinstance(result, dict)
        assert result["code"] == "000001"


# ════════════════════════════════════════════
# _build_pattern_analysis 等（需要 mock stock_analyzer.patterns）
# ════════════════════════════════════════════


class TestBuildPatternAnalysis:
    """_build_pattern_analysis — K 线形态解读"""

    @mock.patch("stock_analyzer.patterns.generate_kline_interpretation_with_today")
    def test_with_rt_info(self, mock_gen):
        """有实时行情时传 today 参数"""
        mock_gen.return_value = {
            "recent_patterns": ["三连阳"],
            "summary": "短期偏多",
            "trend_phase": "上升",
            "key_observation": "连续放量",
        }
        kline = _make_kline()
        info = _make_info(price=11.5)

        result = svc._build_pattern_analysis(kline, info)

        assert result["summary"] == "短期偏多"
        mock_gen.assert_called_once()
        args, _ = mock_gen.call_args
        assert args[0] is kline
        assert "today_close" in mock_gen.call_args[1]

    @mock.patch(
        "stock_analyzer.patterns.generate_kline_interpretation_with_today",
        side_effect=ValueError("fail"),
    )
    def test_exception_safety(self, mock_gen):
        """异常时返回安全默认值"""
        import pandas as pd

        result = svc._build_pattern_analysis(pd.DataFrame({"日期": ["2026-01-01"]}))
        assert "K线形态分析" in result["summary"]


class TestBuildManipulatorIntention:
    """_build_manipulator_intention — 庄家意图"""

    @mock.patch("stock_analyzer.chip_factors.composite_chip_score")
    @mock.patch("stock_analyzer.psychology.analyze_manipulator_intention")
    def test_basic(self, mock_analyze, mock_chip):
        """调用意图分析"""
        mock_chip.return_value = 65
        mock_analyze.return_value = {
            "phase": "吸筹",
            "phase_confidence": 70,
            "signals": ["大单净流入"],
            "volume_analysis": "量价配合",
            "chip_analysis": "筹码集中",
            "assessment": "主力吸筹迹象",
            "risk_note": "",
        }
        r = _make_analysis_result()
        r["fund_flow_total"] = 5e6

        result = svc._build_manipulator_intention("000001", r)

        assert result["phase"] == "吸筹"
        assert result["phase_confidence"] == 70

    def test_exception_safety(self):
        """异常时返回安全默认值"""
        result = svc._build_manipulator_intention("000001", _make_analysis_result())
        assert isinstance(result, dict)


class TestBuildRetailPsychology:
    """_build_retail_psychology — 散户心态"""

    @mock.patch("stock_analyzer.psychology.analyze_retail_psychology")
    def test_basic(self, mock_psych):
        """调用散户心态分析"""
        mock_psych.return_value = {
            "emotion": "贪婪",
            "emotion_score": 70,
            "behavior_pattern": "追涨",
            "sentiment_indicators": ["换手率高"],
            "advice": "保持冷静",
        }
        r = _make_analysis_result()
        result = svc._build_retail_psychology(r)

        assert result["emotion"] == "贪婪"
        assert result["advice"] == "保持冷静"

    def test_exception_safety(self):
        """异常时返回安全默认值"""
        result = svc._build_retail_psychology(_make_analysis_result())
        assert isinstance(result, dict)


class TestBuildCombinedSummary:
    """_build_combined_summary — K 线+庄家联动总结"""

    @mock.patch("stock_analyzer.psychology.generate_combined_summary")
    def test_basic(self, mock_gen):
        """调用联动总结"""
        mock_gen.return_value = {
            "kline_summary": "多头排列",
            "manipulator_summary": "吸筹期",
            "synergy_assessment": "配合良好",
            "overall_conclusion": "偏多",
        }
        result = svc._build_combined_summary({"trend": "up"}, {"phase": "吸筹"})

        assert result["overall_conclusion"] == "偏多"

    @mock.patch(
        "stock_analyzer.psychology.generate_combined_summary",
        side_effect=ValueError("fail"),
    )
    def test_exception_safety(self, mock_gen):
        """异常时返回安全默认值"""
        result = svc._build_combined_summary({}, {})
        assert result["overall_conclusion"] == "数据不足"


class TestBuildChipConcentration:
    """_build_chip_concentration — 筹码集中度"""

    @mock.patch("stock_analyzer.chip_concentration.calc_chip_concentration")
    def test_basic(self, mock_chip):
        """调用筹码分析"""
        mock_chip.return_value = {"pct90": 25.5, "pct70": 15.3, "level": "集中", "risk_warning": ""}
        result = svc._build_chip_concentration("000001", _make_kline())

        assert result["level"] == "集中"

    def test_exception_safety(self):
        """异常时返回安全默认值"""
        result = svc._build_chip_concentration("000001", None)
        assert result["level"] == "无法评估"


# ════════════════════════════════════════════
# run_fast_analysis（mock stock_analyzer.cache）
# ════════════════════════════════════════════


class TestRunFastAnalysis:
    """run_fast_analysis — 快速分析"""

    def _mock_deps(self):
        """批量 mock 所有依赖"""
        patchers = [
            mock.patch("stock_analyzer.cache.cached_kline"),
            mock.patch("stock_analyzer.cache.cached_fundamentals"),
            mock.patch("stock_analyzer.analysis.full_technical_analysis"),
            mock.patch("stock_analyzer.analysis.get_technical_summary"),
            mock.patch("stock_analyzer.analysis.calc_support_resistance"),
            mock.patch("stock_analyzer.analysis.calc_stop_levels"),
            mock.patch("stock_analyzer.quant.composite_quant_score"),
            mock.patch("stock_analyzer.fetcher.sina_real_time"),
        ]
        mocks = {}
        for p in patchers:
            m = p.start()
            name = p.attribute.split(".")[-1] if "." in p.attribute else p.attribute
            mocks[name] = m
        return patchers, mocks

    def test_success(self):
        """正常路径返回结构化结果"""
        patchers, m = self._mock_deps()
        try:
            import pandas as pd

            kline = pd.DataFrame(
                {
                    "收盘": [10.0 + i * 0.1 for i in range(120)],
                    "最高": [10.5 + i * 0.1 for i in range(120)],
                    "最低": [9.5 + i * 0.1 for i in range(120)],
                    "开盘": [10.0 + i * 0.1 for i in range(120)],
                    "成交量": [1000000] * 120,
                    "ATR": [0.3] * 120,
                }
            )
            m["cached_kline"].return_value = kline
            m["full_technical_analysis"].return_value = kline
            m["get_technical_summary"].return_value = {
                "均线": "多头排列",
                "macd_signal": "金叉",
                "kdj_signal": "金叉",
                "rsi_value": 55,
            }
            m["calc_support_resistance"].return_value = {
                "支撑位": [10.5, 10.2],
                "压力位": [12.5, 13.0],
            }
            m["calc_stop_levels"].return_value = {
                "止损参考价": 10.0,
                "止盈参考价": 12.0,
            }
            m["cached_fundamentals"].return_value = {"ROE": 12.5}
            m["composite_quant_score"].return_value = {
                "composite_score": 60,
                "rating": "谨慎看多",
                "factor_scores": {
                    "momentum": {"score": 55},
                    "technical": {"score": 60},
                },
            }
            m["sina_real_time"].return_value = {"000001": {"名称": "平安银行", "最新价": "11.5"}}

            result = svc.run_fast_analysis("000001")

            assert result["code"] == "000001"
            assert result["name"] == "平安银行"
            assert result["near_5d"] != 0
            assert result["technical"]["ma_status"] == "多头排列"
            assert result["quant"]["rating"] == "谨慎看多"
            assert result["financial"]["roe"] == 12.5
        finally:
            for p in patchers:
                p.stop()

    def test_insufficient_data(self):
        """数据不足时抛出 ValueError"""
        patchers, m = self._mock_deps()
        try:
            import pandas as pd

            # 少于 20 行的空 K 线
            m["cached_kline"].return_value = pd.DataFrame()
            with pytest.raises(ValueError, match="数据不足"):
                svc.run_fast_analysis("000001")
        finally:
            for p in patchers:
                p.stop()

    def test_insufficient_data_none(self):
        """K 线为 None 时抛出 ValueError"""
        patchers, m = self._mock_deps()
        try:
            m["cached_kline"].return_value = None
            with pytest.raises(ValueError, match="数据不足"):
                svc.run_fast_analysis("000001")
        finally:
            for p in patchers:
                p.stop()


# ════════════════════════════════════════════
# build_kline_data / build_indicator_data / build_fund_flow_data
# ════════════════════════════════════════════


class TestBuildKlineData:
    """build_kline_data — K 线 JSON 数据"""

    @mock.patch("stock_analyzer.cache.cached_kline")
    @mock.patch("stock_analyzer.analysis.full_technical_analysis")
    def test_basic(self, mock_tech, mock_kline):
        """默认日 K 返回结构化 JSON"""
        kline = _make_kline()
        mock_kline.return_value = kline
        mock_tech.return_value = kline

        result = svc.build_kline_data("000001")

        assert "dates" in result
        assert "opens" in result
        assert "closes" in result
        assert "volumes" in result
        assert len(result["dates"]) <= 120
        assert len(result["dates"]) == len(result["closes"])
        assert len(result["ma5"]) == len(result["dates"])

    @mock.patch("stock_analyzer.cache.cached_kline")
    @mock.patch("stock_analyzer.analysis.full_technical_analysis")
    def test_weekly_ktype(self, mock_tech, mock_kline):
        """周 K 聚合"""
        kline = _make_kline()
        mock_kline.return_value = kline
        mock_tech.return_value = kline

        result = svc.build_kline_data("000001", ktype="week")

        assert "dates" in result
        assert len(result["dates"]) >= 1

    @mock.patch("stock_analyzer.cache.cached_kline")
    def test_missing_data(self, mock_kline):
        """K 线不可用时抛出 ValueError"""
        mock_kline.return_value = None
        with pytest.raises(ValueError, match="K线数据不可用"):
            svc.build_kline_data("000001")


class TestBuildIndicatorData:
    """build_indicator_data — 技术指标数据"""

    @mock.patch("stock_analyzer.cache.cached_kline")
    @mock.patch("stock_analyzer.analysis.full_technical_analysis")
    def test_macd(self, mock_tech, mock_kline):
        """MACD 指标输出"""
        kline = _make_kline()
        mock_kline.return_value = kline
        mock_tech.return_value = kline

        result = svc.build_indicator_data("000001", "macd")

        assert result["type"] == "macd"
        assert "dif" in result["values"]
        assert "dea" in result["values"]
        assert "bar" in result["values"]
        assert len(result["values"]["dif"]) == len(result["dates"])

    @mock.patch("stock_analyzer.cache.cached_kline")
    @mock.patch("stock_analyzer.analysis.full_technical_analysis")
    def test_rsi(self, mock_tech, mock_kline):
        """RSI 指标输出"""
        kline = _make_kline()
        mock_kline.return_value = kline
        mock_tech.return_value = kline

        result = svc.build_indicator_data("000001", "rsi")

        assert result["type"] == "rsi"
        assert "rsi" in result["values"]

    @mock.patch("stock_analyzer.cache.cached_kline")
    @mock.patch("stock_analyzer.analysis.full_technical_analysis")
    def test_kdj(self, mock_tech, mock_kline):
        """KDJ 指标输出"""
        kline = _make_kline()
        mock_kline.return_value = kline
        mock_tech.return_value = kline

        result = svc.build_indicator_data("000001", "kdj")

        assert result["type"] == "kdj"
        assert "k" in result["values"]
        assert "d" in result["values"]
        assert "j" in result["values"]


class TestBuildFundFlowData:
    """build_fund_flow_data — 资金流向数据"""

    @mock.patch("stock_analyzer.fetcher.get_fund_flow")
    def test_basic(self, mock_ff):
        """资金流向结构化输出"""
        import pandas as pd

        ff = pd.DataFrame(
            {
                "日期": ["2026-06-19", "2026-06-18"],
                "主力净流入-净额": [100000000.0, -50000000.0],
                "主力净流入-净占比": [2.5, -1.2],
                "超大单净流入-净额": [50000000.0, -20000000.0],
                "大单净流入-净额": [50000000.0, -30000000.0],
            }
        )
        mock_ff.return_value = ff

        result = svc.build_fund_flow_data("000001", days=20)

        assert result["direction"] == "流入"
        assert result["total_yi"] > 0
        assert len(result["daily"]) == 2

    @mock.patch("stock_analyzer.fetcher.get_fund_flow")
    def test_outflow(self, mock_ff):
        """净流出时方向正确"""
        import pandas as pd

        ff = pd.DataFrame(
            {
                "日期": ["2026-06-19"],
                "主力净流入-净额": [-100000000.0],
                "主力净流入-净占比": [-2.5],
                "超大单净流入-净额": [-50000000.0],
                "大单净流入-净额": [-50000000.0],
            }
        )
        mock_ff.return_value = ff

        result = svc.build_fund_flow_data("000001")

        assert result["direction"] == "流出"

    @mock.patch("stock_analyzer.fetcher.get_fund_flow")
    def test_no_data(self, mock_ff):
        """数据不可用时抛出 ValueError"""
        mock_ff.return_value = None
        with pytest.raises(ValueError, match="资金流向数据不可用"):
            svc.build_fund_flow_data("000001")
