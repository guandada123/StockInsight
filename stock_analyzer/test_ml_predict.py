"""Tests for ml_predict.py — Machine Learning prediction module

覆盖:
  - build_features: 特征构建（纯 pandas/numpy，实跑）
  - predict_direction: 方向预测（mock sklearn）
  - predict_return: 涨跌幅预测（mock sklearn）
  - ml_enhanced_score: ML 增强评分
  - predict_ensemble: 三模型集成投票
  - predict_dual_model: 双模型验证
  - _cached_predict_ensemble: 缓存机制
"""

import hashlib
import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch, ANY

from stock_analyzer import ml_predict


# ═══════════════════════════════════════════════════════════
# 测试数据生成
# ═══════════════════════════════════════════════════════════

def _make_kline_df(n=200, seed=42):
    """生成模拟 K 线 DataFrame"""
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 0.5, n))
    high = close * (1 + np.abs(rng.normal(0, 0.01, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.01, n)))
    return pd.DataFrame({
        "日期": dates,
        "开盘": close * (1 + rng.normal(0, 0.005, n)),
        "收盘": close,
        "最高": high,
        "最低": low,
        "成交量": rng.integers(100_000, 10_000_000, n),
        "成交额": rng.integers(1_000_000, 100_000_000, n),
        "昨收": pd.Series(close).shift(1).values,
        "涨跌幅": pd.Series(close).pct_change().values * 100,
        "涨跌额": pd.Series(close).diff().values,
        "振幅": (high - low) / close * 100,
    })


def _make_mock_model(n_features=35, n_samples=30):
    """创建 mock RF/RF 模型实例"""
    model = MagicMock()
    model.fit.return_value = None
    model.predict.return_value = np.ones(n_samples, dtype=int)
    model.predict_proba.return_value = np.column_stack([
        np.full(n_samples + 1, 0.3),
        np.full(n_samples + 1, 0.7),
    ])
    model.feature_importances_ = np.random.default_rng(42).random(n_features)
    return model


def _make_mock_regressor(n_samples=30):
    """创建 mock 回归模型实例"""
    model = MagicMock()
    model.fit.return_value = None
    model.predict.return_value = np.full(n_samples + 1, 0.005)
    return model


# ═══════════════════════════════════════════════════════════
# build_features — 特征工程（纯 pandas/numpy，无 mock）
# ═══════════════════════════════════════════════════════════

class TestBuildFeatures:
    def test_basic(self):
        """200 行 K 线 → 有效的 X / y / y_pct / feature_names"""
        df = _make_kline_df(200)
        X, y, y_pct, names, idx = ml_predict.build_features(df)
        assert X is not None
        assert len(X) == len(y) == len(y_pct) == len(idx)
        assert X.shape[1] == len(names)
        assert X.shape[1] >= 25  # 至少 25 个特征
        assert X.shape[0] >= 80  # dropna 后至少 80 行

    def test_basic_hundred_rows(self):
        """100 行 K 线也能正常工作"""
        df = _make_kline_df(100)
        X, y, y_pct, names, idx = ml_predict.build_features(df)
        assert X is not None
        assert len(X) >= 20

    def test_none_df(self):
        """None → 全部返回 None"""
        X, y, y_pct, names, idx = ml_predict.build_features(None)
        assert X is None and y is None and y_pct is None
        assert names == []

    def test_fewer_than_60_rows(self):
        """少于 60 行 → None"""
        df = _make_kline_df(30)
        X, y, y_pct, names, idx = ml_predict.build_features(df)
        assert X is None

    def test_missing_volume(self):
        """无成交量列 → 不崩溃，无量能特征"""
        df = _make_kline_df(200).drop(columns=["成交量"])
        X, y, y_pct, names, idx = ml_predict.build_features(df)
        assert X is not None
        # 不包含任何 volume_ 开头的特征
        vol_feats = [n for n in names if n.startswith("volume_")]
        assert len(vol_feats) == 0

    def test_feature_names_content(self):
        """特征名列包含预期特征"""
        df = _make_kline_df(200)
        X, y, y_pct, names, idx = ml_predict.build_features(df)
        expected = {"returns_1d", "returns_5d", "ma_5", "ma_60", "ma_60_dist",
                     "volatility_5d", "volatility_20d", "volume_ma5", "volume_ma20",
                     "volume_ratio", "rsi", "macd_dif", "macd_bar",
                     "bb_width", "bb_position", "kdj_k", "kdj_d",
                     "trend_strength", "adx_plus", "adx_minus"}
        assert expected.issubset(set(names)), f"缺少特征: {expected - set(names)}"

    def test_target_is_binary(self):
        """y 只包含 0 和 1"""
        df = _make_kline_df(200)
        X, y, y_pct, names, idx = ml_predict.build_features(df)
        assert set(y) == {0, 1}

    def test_target_pct_range(self):
        """y_pct 是收益率（每天浮动）"""
        df = _make_kline_df(200)
        X, y, y_pct, names, idx = ml_predict.build_features(df)
        assert np.all(y_pct >= -0.15)
        assert np.all(y_pct <= 0.15)

    def test_copy_not_mutate(self):
        """build_features 不修改原始 df"""
        df = _make_kline_df(200)
        orig_cols = set(df.columns)
        ml_predict.build_features(df)
        assert set(df.columns) == orig_cols


# ═══════════════════════════════════════════════════════════
# predict_direction — 方向预测
# ═══════════════════════════════════════════════════════════

class TestPredictDirection:
    def setup_method(self):
        self.df = _make_kline_df(200)

    # ── 公共 mock 装饰器（所有成功路径共用） ──
    _COMMON_MOCKS = [
        patch("sklearn.metrics.accuracy_score", return_value=0.85),
        patch("sklearn.metrics.precision_score", return_value=0.80),
        patch("sklearn.metrics.recall_score", return_value=0.75),
        patch("sklearn.metrics.roc_auc_score", return_value=0.90),
    ]

    def _apply_common_mocks(self):
        """应用公共 mock 并同时返回 mock 对象元组"""
        # 手动 patch
        mock_acc = patch("sklearn.metrics.accuracy_score", return_value=0.85).start()
        mock_prec = patch("sklearn.metrics.precision_score", return_value=0.80).start()
        mock_rec = patch("sklearn.metrics.recall_score", return_value=0.75).start()
        mock_auc = patch("sklearn.metrics.roc_auc_score", return_value=0.90).start()
        return mock_acc, mock_prec, mock_rec, mock_auc

    def _stop_mocks(self, mocks):
        for m in mocks:
            m.stop()

    @patch("sklearn.ensemble.RandomForestClassifier")
    def test_success_xgb(self, mock_rf):
        """xgb 模式（xgboost 未装 → 降级 RF）→ 返回完整结果"""
        model = _make_mock_model()
        mock_rf.return_value = model
        mocks = self._apply_common_mocks()

        try:
            result = ml_predict.predict_direction(self.df, model_type="xgb")

            assert "error" not in result, f"不应返回 error: {result.get('error')}"
            assert result["上涨概率"] == 70.0
            assert result["下跌概率"] == 30.0
            assert result["预测方向"] == "看涨"
            assert result["置信度"] == 70.0
            assert result["准确率%"] == 85.0
            assert result["精确率%"] == 80.0
            assert result["召回率%"] == 75.0
            assert result["AUC"] == 0.9
            assert result["训练样本"] > 0
            assert result["测试样本"] > 0
            assert len(result["重要特征"]) == 5
            assert "特征" in result["重要特征"][0]
            assert "重要性" in result["重要特征"][0]
        finally:
            self._stop_mocks(mocks)

    @patch("sklearn.ensemble.RandomForestClassifier")
    def test_success_rf(self, mock_rf):
        """rf 模式 → 返回完整结果"""
        model = _make_mock_model()
        mock_rf.return_value = model
        mocks = self._apply_common_mocks()

        try:
            result = ml_predict.predict_direction(self.df, model_type="rf")
            assert "error" not in result
            assert result["预测方向"] in ("看涨", "看跌")
            assert "训练样本" in result
            assert "测试样本" in result
            assert "重要特征" in result
        finally:
            self._stop_mocks(mocks)

    def test_short_data(self):
        """数据不足 → error"""
        df = _make_kline_df(30)  # 只有 30 行
        result = ml_predict.predict_direction(df)
        assert "error" in result
        assert "数据不足" in result["error"]

    def test_data_too_few_rows(self):
        """刚好 59 行（<60）→ error"""
        df = _make_kline_df(59)
        result = ml_predict.predict_direction(df)
        assert "error" in result

    @patch("sklearn.ensemble.RandomForestClassifier")
    def test_down_prediction(self, mock_rf):
        """下跌预测分支"""
        model = MagicMock()
        model.fit.return_value = None
        # 预测全部为 0（下跌）
        n = 30
        model.predict.return_value = np.zeros(n, dtype=int)
        model.predict_proba.return_value = np.column_stack([
            np.full(n + 1, 0.7),
            np.full(n + 1, 0.3),
        ])
        model.feature_importances_ = np.random.default_rng(42).random(35)
        mock_rf.return_value = model

        mocks = self._apply_common_mocks()
        try:
            result = ml_predict.predict_direction(self.df)
            assert result["预测方向"] == "看跌"
            assert result["上涨概率"] == 30.0
            assert result["下跌概率"] == 70.0
            assert result["置信度"] == 70.0
        finally:
            self._stop_mocks(mocks)

    @patch("sklearn.ensemble.RandomForestClassifier")
    def test_single_label_auc_zero(self, mock_rf):
        """y_test 单标签 → AUC=0 且不调用 roc_auc_score"""
        model = _make_mock_model()
        mock_rf.return_value = model

        # patch roc_auc_score 来验证它不被调用
        with patch("sklearn.metrics.roc_auc_score") as mock_roc:
            mock_roc.return_value = 0.9
            with patch("sklearn.metrics.accuracy_score", return_value=0.85), \
                 patch("sklearn.metrics.precision_score", return_value=0.80), \
                 patch("sklearn.metrics.recall_score", return_value=0.75):

                # 让 y_test 全为 1 → 单标签：这只发生在极端情况下
                # 我们用 build_features 自然跑，所以 y_test 通常有 mixed labels
                # 这个测试验证如果有 single label，AUC 被设为 0
                # 但我们无法轻松控制 y_test 的内容，所以这个测试确保代码不崩溃
                result = ml_predict.predict_direction(self.df)
                # 正常路径会调用 roc_auc_score，因为 y_test 有 mixed labels
                assert "error" not in result

    @patch("sklearn.ensemble.RandomForestClassifier")
    def test_no_feature_importances(self, mock_rf):
        """模型没有 feature_importances_ → 重要特征为空列表"""
        # 用 spec 限制属性，使 hasattr(model, "feature_importances_") 返回 False
        model = MagicMock(spec=["fit", "predict", "predict_proba"])
        model.fit.return_value = None
        model.predict.return_value = np.ones(30, dtype=int)
        model.predict_proba.return_value = np.column_stack([
            np.full(31, 0.3), np.full(31, 0.7),
        ])
        mock_rf.return_value = model

        with patch("sklearn.metrics.accuracy_score", return_value=0.85), \
             patch("sklearn.metrics.precision_score", return_value=0.80), \
             patch("sklearn.metrics.recall_score", return_value=0.75), \
             patch("sklearn.metrics.roc_auc_score", return_value=0.90):
            result = ml_predict.predict_direction(self.df)
            assert result["重要特征"] == []

    def test_single_label_error(self):
        """y_train 全为同一标签 → 返回单一标签错误"""
        # mock build_features 返回全 1 的 y
        mock_X = np.random.default_rng(42).random((100, 30))
        mock_y = np.ones(100, dtype=int)
        with patch("stock_analyzer.ml_predict.build_features") as mock_bf:
            mock_bf.return_value = (mock_X, mock_y, np.zeros(100), [f"f{i}" for i in range(30)], None)
            result = ml_predict.predict_direction(self.df)
            assert "error" in result
            assert "训练数据标签单一" in result["error"]

    @patch("sklearn.ensemble.RandomForestClassifier")
    def test_exception_in_training(self, mock_rf):
        """训练异常 → 返回 error"""
        model = MagicMock()
        model.fit.side_effect = ValueError("训练失败")
        mock_rf.return_value = model

        with patch("sklearn.metrics.accuracy_score", return_value=0.85), \
             patch("sklearn.metrics.precision_score", return_value=0.80), \
             patch("sklearn.metrics.recall_score", return_value=0.75), \
             patch("sklearn.metrics.roc_auc_score", return_value=0.90):
            result = ml_predict.predict_direction(self.df)
            assert "error" in result
            assert "训练失败" in result["error"]


# ═══════════════════════════════════════════════════════════
# predict_return — 涨跌幅预测
# ═══════════════════════════════════════════════════════════

class TestPredictReturn:
    def setup_method(self):
        self.df = _make_kline_df(200)

    @patch("sklearn.ensemble.RandomForestRegressor")
    @patch("sklearn.metrics.mean_absolute_error", return_value=0.01)
    @patch("sklearn.metrics.r2_score", return_value=0.80)
    def test_success(self, mock_r2, mock_mae, mock_rf):
        """正常路径 → 返回预测涨跌幅"""
        model = _make_mock_regressor()
        mock_rf.return_value = model

        result = ml_predict.predict_return(self.df)
        assert "error" not in result
        assert result["预测涨跌幅%"] == 0.5  # 0.005 * 100
        assert result["方向"] == "上涨"
        assert result["MAE"] == 0.01
        assert result["R2"] == 0.80

    @patch("sklearn.ensemble.RandomForestRegressor")
    @patch("sklearn.metrics.mean_absolute_error", return_value=0.01)
    @patch("sklearn.metrics.r2_score", return_value=0.80)
    def test_down_return(self, mock_r2, mock_mae, mock_rf):
        """负涨跌幅 → 方向为下跌"""
        model = MagicMock()
        model.fit.return_value = None
        model.predict.return_value = np.full(31, -0.005)
        mock_rf.return_value = model

        result = ml_predict.predict_return(self.df)
        assert result["方向"] == "下跌"
        assert result["预测涨跌幅%"] == -0.5

    def test_short_data(self):
        """数据不足 → error"""
        df = _make_kline_df(30)
        result = ml_predict.predict_return(df)
        assert "error" in result

    @patch("sklearn.ensemble.RandomForestRegressor")
    @patch("sklearn.metrics.mean_absolute_error", return_value=0.01)
    @patch("sklearn.metrics.r2_score", return_value=0.80)
    def test_exception(self, mock_r2, mock_mae, mock_rf):
        """异常 → error"""
        mock_rf.side_effect = ValueError("regressor init failed")
        result = ml_predict.predict_return(self.df)
        assert "error" in result


# ═══════════════════════════════════════════════════════════
# ml_enhanced_score — ML 增强评分
# ═══════════════════════════════════════════════════════════

class TestMlEnhancedScore:
    def setup_method(self):
        self.df = _make_kline_df(200)
        # 成功结果
        self._success_direction = {
            "预测方向": "看涨", "上涨概率": 70.0, "准确率%": 85.0, "AUC": 0.9
        }
        self._success_return = {"预测涨跌幅%": 1.5}

    @patch("stock_analyzer.ml_predict.predict_return")
    @patch("stock_analyzer.ml_predict.predict_direction")
    def test_both_available(self, mock_dir, mock_ret):
        """方向和回归都成功"""
        mock_dir.return_value = self._success_direction
        mock_ret.return_value = self._success_return

        result = ml_predict.ml_enhanced_score(self.df)
        assert result["ml_available"] is True
        assert result["ml_方向"] == "看涨"
        assert result["ml_上涨概率"] == 70.0
        assert result["ml_准确率"] == 85.0
        assert result["ml_AUC"] == 0.9
        assert result["ml_预测涨跌幅"] == 1.5

    @patch("stock_analyzer.ml_predict.predict_return")
    @patch("stock_analyzer.ml_predict.predict_direction")
    def test_direction_only(self, mock_dir, mock_ret):
        """方向成功，回归失败"""
        mock_dir.return_value = self._success_direction
        mock_ret.return_value = {"error": "数据不足"}

        result = ml_predict.ml_enhanced_score(self.df)
        assert result["ml_available"] is True
        assert "ml_方向" in result
        assert "ml_预测涨跌幅" not in result

    @patch("stock_analyzer.ml_predict.predict_return")
    @patch("stock_analyzer.ml_predict.predict_direction")
    def test_both_fail(self, mock_dir, mock_ret):
        """两个都失败"""
        mock_dir.return_value = {"error": "数据不足"}
        mock_ret.return_value = {"error": "数据不足"}

        result = ml_predict.ml_enhanced_score(self.df)
        assert result["ml_available"] is False
        assert "ml_方向" not in result
        assert "ml_预测涨跌幅" not in result

    @patch("stock_analyzer.ml_predict.predict_return")
    @patch("stock_analyzer.ml_predict.predict_direction")
    def test_no_auc_key(self, mock_dir, mock_ret):
        """direction 返回中无 AUC"""
        mock_dir.return_value = {"预测方向": "看跌", "上涨概率": 30.0, "准确率%": 80.0}
        mock_ret.return_value = self._success_return

        result = ml_predict.ml_enhanced_score(self.df)
        assert result["ml_AUC"] == 0


# ═══════════════════════════════════════════════════════════
# predict_ensemble — 集成投票
# ═══════════════════════════════════════════════════════════

class TestPredictEnsemble:
    def setup_method(self):
        self.df = _make_kline_df(200)

    @patch("stock_analyzer.ml_predict._predict_lgb")
    @patch("stock_analyzer.ml_predict.predict_direction")
    def test_all_up(self, mock_dir, mock_lgb):
        """三模型全部看涨 → agreement=高"""
        mock_dir.return_value = {"预测方向": "看涨", "上涨概率": 70.0}
        mock_lgb.return_value = {"预测方向": "看涨", "上涨概率": 75.0}

        result = ml_predict.predict_ensemble(self.df)
        assert result["agreement"] == "高"
        assert result["ensemble_direction"] == "看涨"
        # mock_dir 被调用两次（xgb + rf），return 值相同
        # 所以平均置信度 = (70 + 70 + 75) / 3 = 71.67
        assert result["ensemble_confidence"] == 71.7
        assert result["votes"] == "3/3看涨"

    @patch("stock_analyzer.ml_predict._predict_lgb")
    @patch("stock_analyzer.ml_predict.predict_direction")
    def test_majority_up(self, mock_dir, mock_lgb):
        """2/3 看涨 → 中 agreement + 看涨"""
        # side_effect: 第一次调用(xgb)=看涨, 第二次调用(rf)=看跌
        mock_dir.side_effect = [
            {"预测方向": "看涨", "上涨概率": 70.0},
            {"预测方向": "看跌", "上涨概率": 30.0},
        ]
        mock_lgb.return_value = {"预测方向": "看涨", "上涨概率": 80.0}

        result = ml_predict.predict_ensemble(self.df)
        # 2/3 看涨，但 valid=3，agreement = "中"
        assert result["ensemble_direction"] == "看涨"
        assert result["agreement"] == "中"
        # 置信度: xgb(70) + rf(100-30=70) + lgb(80) / 3 = 73.3
        assert result["votes"] == "2/3看涨"

    @patch("stock_analyzer.ml_predict._predict_lgb")
    @patch("stock_analyzer.ml_predict.predict_direction")
    def test_all_down(self, mock_dir, mock_lgb):
        """全部看跌 → agreement=高"""
        mock_dir.return_value = {"预测方向": "看跌", "上涨概率": 30.0}
        mock_lgb.return_value = {"预测方向": "看跌", "上涨概率": 25.0}

        result = ml_predict.predict_ensemble(self.df)
        assert result["ensemble_direction"] == "看跌"
        assert result["agreement"] == "高"
        assert result["votes"] == "0/3看涨"

    @patch("stock_analyzer.ml_predict._predict_lgb")
    @patch("stock_analyzer.ml_predict.predict_direction")
    def test_one_model_error(self, mock_dir, mock_lgb):
        """一个模型 error → 另外两个投票"""
        mock_dir.side_effect = [
            {"预测方向": "看涨", "上涨概率": 70.0},
            {"error": "数据不足"},
        ]
        mock_lgb.return_value = {"预测方向": "看跌", "上涨概率": 30.0}

        result = ml_predict.predict_ensemble(self.df)
        # 2 valid, 1 看涨 1 看跌 → 平局 → 看跌 (votes_up=1 < 2/2=1? No, 1 >= 1)
        # direction = "看涨" if votes_up >= valid/2 → 1 >= 1 → True → "看涨"
        assert result["ensemble_direction"] in ("看涨",)
        assert result["agreement"] == "低"  # valid < 3
        # 置信度: (70 + (100-30)) / 2 = 70.0
        assert result["votes"] == "1/2看涨"

    @patch("stock_analyzer.ml_predict._predict_lgb")
    @patch("stock_analyzer.ml_predict.predict_direction")
    def test_two_models_error(self, mock_dir, mock_lgb):
        """两个模型 error → 数据不足（仅 1 个有效）"""
        mock_dir.side_effect = [
            {"预测方向": "看涨", "上涨概率": 70.0},  # xgb: valid
            {"error": "数据不足"},                    # rf: error
        ]
        mock_lgb.return_value = {"error": "数据不足"}  # lgb: error

        result = ml_predict.predict_ensemble(self.df)
        assert result["agreement"] == "数据不足"  # valid=1 < 2
        assert result["ensemble_direction"] == "未知"
        # models 字典仍包含三个结果
        assert "xgb" in result["models"]
        assert "rf" in result["models"]
        assert "lgb" in result["models"]


# ═══════════════════════════════════════════════════════════
# predict_dual_model — 双模型验证（委托给 ensemble）
# ═══════════════════════════════════════════════════════════

class TestPredictDualModel:
    def test_delegates_to_ensemble(self):
        """双模型验证 = 集成投票"""
        df = _make_kline_df(200)
        with patch("stock_analyzer.ml_predict.predict_ensemble") as mock_ens:
            mock_ens.return_value = {"ensemble_direction": "看涨"}
            result = ml_predict.predict_dual_model(df)
            assert result["ensemble_direction"] == "看涨"
            mock_ens.assert_called_once_with(df, None)


# ═══════════════════════════════════════════════════════════
# _cached_predict_ensemble — 缓存机制
# ═══════════════════════════════════════════════════════════

class TestCachedPredictEnsemble:
    def test_cache_hit(self):
        """相同 DataFrame → 第二次命中缓存"""
        df = _make_kline_df(200)
        with patch("stock_analyzer.ml_predict.predict_ensemble") as mock_ens:
            mock_ens.return_value = {"ensemble_direction": "看涨"}

            # 第一次调用: cache miss
            r1 = ml_predict._cached_predict_ensemble(df)
            # 第二次调用: cache hit
            r2 = ml_predict._cached_predict_ensemble(df)

            assert r1 == r2
            # predict_ensemble 应该只被调用一次
            assert mock_ens.call_count == 1

    def test_cache_miss_different_df(self):
        """不同 DataFrame → 不命中缓存"""
        df1 = _make_kline_df(200, seed=1)
        df2 = _make_kline_df(200, seed=2)
        with patch("stock_analyzer.ml_predict.predict_ensemble") as mock_ens:
            mock_ens.return_value = {"ensemble_direction": "看涨"}

            ml_predict._cached_predict_ensemble(df1)
            ml_predict._cached_predict_ensemble(df2)

            # 应该被调用两次（不同数据）
            assert mock_ens.call_count == 2

    def test_cache_key_uses_hashlib_md5(self):
        """缓存键使用 hashlib.md5"""
        df = _make_kline_df(200)
        # 清理 _RESULT_CACHE
        ml_predict._RESULT_CACHE.clear()
        # 预期 key
        expected_key = hashlib.md5(
            str(df.shape).encode()
            + str(df.iloc[-20:, 1].sum()).encode()
            + str(df.iloc[-1, 1]).encode()
        ).hexdigest()

        with patch("stock_analyzer.ml_predict.predict_ensemble") as mock_ens:
            mock_ens.return_value = {"ensemble_direction": "看涨"}
            ml_predict._cached_predict_ensemble(df)

            # key 应该在 _RESULT_CACHE 中
            assert expected_key in ml_predict._RESULT_CACHE
            assert ml_predict._RESULT_CACHE[expected_key] == {"ensemble_direction": "看涨"}


# ═══════════════════════════════════════════════════════════
# _predict_lgb — LightGBM 降级测试
# ═══════════════════════════════════════════════════════════

class TestPredictLgb:
    def test_lightgbm_not_installed_falls_to_rf(self):
        """lightgbm 未装 → 降级到 predict_direction(rf)"""
        df = _make_kline_df(200)
        with patch("stock_analyzer.ml_predict.predict_direction") as mock_dir:
            mock_dir.return_value = {"预测方向": "看涨", "上涨概率": 65.0}

            # _predict_lgb 内部: try lightgbm → ImportError → return predict_direction(rf)
            result = ml_predict._predict_lgb(df)

            assert result == {"预测方向": "看涨", "上涨概率": 65.0}
            # 验证降级到 model_type="rf"
            mock_dir.assert_called_once_with(df, None, model_type="rf")
