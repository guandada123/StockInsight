#!/usr/bin/env python
"""机器学习预测模块

功能：
  1. 特征工程 — 从K线+基本面+宏观构建50+特征
  2. 方向预测 — XGBoost/LightGBM预测N日后涨跌方向
  3. 涨跌幅预测 — 回归模型预测N日后涨跌幅
  4. 特征重要性 — 哪些因子对股价影响最大
  5. 模型评估 — 准确率/精确率/召回率/AUC
"""

import hashlib
import warnings
from typing import Any

import numpy as np

warnings.filterwarnings("ignore")


# ═══════════════════════════════════════════
# 特征工程
# ═══════════════════════════════════════════


def build_features(df, fundamentals=None, lookback_days=20):
    """从K线数据构建ML特征矩阵

    返回: (X, y, y_pct, feature_names, fundamentals_features)
      X: 特征矩阵  y: 涨跌方向  y_pct: 涨跌幅  feature_names: 特征名列表
    """
    if df is None or len(df) < 60:
        return None, None, None, [], None

    df = df.copy()

    # ── 价格特征 ──
    df["returns_1d"] = df["收盘"].pct_change(1)
    df["returns_5d"] = df["收盘"].pct_change(5)
    df["returns_10d"] = df["收盘"].pct_change(10)
    df["returns_20d"] = df["收盘"].pct_change(20)

    # ── 均线特征 ──
    for w in [5, 10, 20, 60]:
        df[f"ma_{w}"] = df["收盘"].rolling(w).mean()
        df[f"ma_{w}_dist"] = (df["收盘"] - df[f"ma_{w}"]) / df[f"ma_{w}"] * 100

    # ── 波动率 ──
    df["volatility_5d"] = df["returns_1d"].rolling(5).std()
    df["volatility_10d"] = df["returns_1d"].rolling(10).std()
    df["volatility_20d"] = df["returns_1d"].rolling(20).std()

    # ── 量能 ──
    if "成交量" in df.columns:
        df["volume_ma5"] = df["成交量"].rolling(5).mean()
        df["volume_ma20"] = df["成交量"].rolling(20).mean()
        df["volume_ratio"] = df["成交量"] / df["volume_ma20"].replace(0, np.nan)
        df["volume_trend"] = df["volume_ma5"] / df["volume_ma20"].replace(0, np.nan)

    # ── RSI ──
    delta = df["收盘"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    df["rsi"] = 100 - (100 / (1 + rs))

    # ── MACD ──
    ema12 = df["收盘"].ewm(span=12).mean()
    ema26 = df["收盘"].ewm(span=26).mean()
    df["macd_dif"] = ema12 - ema26
    df["macd_dea"] = df["macd_dif"].ewm(span=9).mean()
    df["macd_bar"] = 2 * (df["macd_dif"] - df["macd_dea"])

    # ── 布林带 ──
    ma20 = df["收盘"].rolling(20).mean()
    std20 = df["收盘"].rolling(20).std()
    df["bb_width"] = (std20 * 4) / ma20 * 100
    df["bb_position"] = (df["收盘"] - (ma20 - 2 * std20)) / (4 * std20).replace(0, np.nan)

    # ── KDJ ──
    low_n = df["最低"].rolling(9).min()
    high_n = df["最高"].rolling(9).max()
    rsv = (df["收盘"] - low_n) / (high_n - low_n).replace(0, 1e-10) * 100
    df["kdj_k"] = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    df["kdj_d"] = df["kdj_k"].ewm(alpha=1 / 3, adjust=False).mean()

    # ── 趋势强度 ──
    df["adx_plus"] = (df["最高"] - df["最高"].shift(1)).clip(lower=0)
    df["adx_minus"] = (df["最低"].shift(1) - df["最低"]).clip(lower=0)
    df["trend_strength"] = abs(df["收盘"] - df["收盘"].shift(20)) / df["收盘"].shift(20)

    # ── 标签: 下一日涨跌方向 ──
    df["target"] = (df["returns_1d"].shift(-1) > 0).astype(int)
    # 涨跌幅标签
    df["target_pct"] = df["returns_1d"].shift(-1)

    # 移除NaN
    df = df.dropna()

    # 特征列
    feature_cols = [
        c
        for c in df.columns
        if c
        not in [
            "日期",
            "开盘",
            "收盘",
            "最高",
            "最低",
            "成交量",
            "成交额",
            "涨跌幅",
            "涨跌额",
            "昨收",
            "振幅",
            "target",
            "target_pct",
            "ATR",
            "ADX",
        ]
    ]

    X = df[feature_cols].values
    y = df["target"].values
    y_pct = df["target_pct"].values

    return X, y, y_pct, feature_cols, df.index


# ═══════════════════════════════════════════
# 方向预测
# ═══════════════════════════════════════════


def predict_direction(df, fundamentals=None, model_type="xgb", lookahead=1):
    """预测下一日涨跌方向

    参数:
        df: K线DataFrame
        fundamentals: 基本面数据dict（可选）
        model_type: 'xgb' / 'rf' (Random Forest)
        lookahead: 预测未来第N天

    返回:
        dict: {probability, direction, confidence, features_importance, accuracy}
    """
    X, y, y_pct, feature_names, _ = build_features(df, fundamentals)
    if X is None or len(y) < 30:
        return {"error": "数据不足（至少需要60天K线）"}

    try:
        from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
        from sklearn.model_selection import train_test_split

        # 按时间切分（前80%训练，后20%验证）
        split = int(len(X) * 0.8)
        X_train, X_test = X[:split], X[split:]
        y_train, y_test = y[:split], y[split:]

        if len(np.unique(y_train)) < 2:
            return {"error": "训练数据标签单一，无法训练"}

        # 模型选择
        if model_type == "xgb":
            try:
                from xgboost import XGBClassifier

                model = XGBClassifier(
                    n_estimators=100,
                    max_depth=4,
                    learning_rate=0.05,
                    subsample=0.8,
                    random_state=42,
                    verbosity=0,
                )
            except ImportError:
                from sklearn.ensemble import RandomForestClassifier

                model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
        else:
            from sklearn.ensemble import RandomForestClassifier

            model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)

        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        y_proba = model.predict_proba(X_test)[:, 1]

        # 最新预测
        latest_features = X[-1:].reshape(1, -1)
        latest_proba = model.predict_proba(latest_features)[0]

        # 特征重要性
        if hasattr(model, "feature_importances_"):
            importances = sorted(
                zip(feature_names, model.feature_importances_), key=lambda x: x[1], reverse=True
            )[:10]
        else:
            importances = []

        return {
            "上涨概率": round(float(latest_proba[1]) * 100, 1),
            "下跌概率": round(float(latest_proba[0]) * 100, 1),
            "预测方向": "看涨" if latest_proba[1] > 0.5 else "看跌",
            "置信度": round(max(latest_proba) * 100, 1),
            "准确率%": round(accuracy_score(y_test, y_pred) * 100, 1),
            "精确率%": round(precision_score(y_test, y_pred) * 100, 1),
            "召回率%": round(recall_score(y_test, y_pred) * 100, 1),
            "AUC": round(roc_auc_score(y_test, y_proba), 3) if len(np.unique(y_test)) > 1 else 0,
            "训练样本": len(X_train),
            "测试样本": len(X_test),
            "重要特征": [{"特征": name, "重要性": round(imp, 4)} for name, imp in importances[:5]],
        }
    except ImportError as e:
        return {"error": f"缺少依赖: {e}。pip install scikit-learn xgboost"}
    except Exception as e:
        return {"error": str(e)}


def predict_return(df, fundamentals=None):
    """预测次日涨跌幅（回归模型）

    返回:
        dict: {predicted_return, confidence_interval, feature_importance}
    """
    X, y, y_pct, feature_names, _ = build_features(df, fundamentals)
    if X is None or len(y) < 30:
        return {"error": "数据不足"}

    try:
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.metrics import mean_absolute_error, r2_score

        split = int(len(X) * 0.8)
        X_train, X_test = X[:split], X[split:]
        y_train, y_test = y_pct[:split], y_pct[split:]

        model = RandomForestRegressor(n_estimators=100, max_depth=5, random_state=42)
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        latest = model.predict(X[-1:].reshape(1, -1))[0]

        return {
            "预测涨跌幅%": round(float(latest) * 100, 2),
            "方向": "上涨" if latest > 0 else "下跌",
            "MAE": round(mean_absolute_error(y_test, y_pred), 4),
            "R2": round(r2_score(y_test, y_pred), 3),
        }
    except Exception as e:
        return {"error": str(e)}


def ml_enhanced_score(df, fundamentals=None):
    """ML增强评分：传统量化评分 + ML预测融合

    返回: dict — 含传统评分和ML增强项
    """
    result = {"ml_available": False}

    # 尝试ML预测
    direction = predict_direction(df, fundamentals)
    if "error" not in direction:
        result["ml_available"] = True
        result["ml_方向"] = direction["预测方向"]
        result["ml_上涨概率"] = direction["上涨概率"]
        result["ml_准确率"] = direction["准确率%"]
        result["ml_AUC"] = direction.get("AUC", 0)

    # 尝试回归预测
    reg = predict_return(df, fundamentals)
    if "error" not in reg:
        result["ml_预测涨跌幅"] = reg["预测涨跌幅%"]

    return result


def _predict_lgb(df, fundamentals=None):
    """LightGBM 预测（降级到RF如果未安装）"""
    try:
        from lightgbm import LGBMClassifier

        X, y, y_pct, feature_names, _ = build_features(df, fundamentals)
        if X is None or len(y) < 30:
            return {"error": "数据不足"}
        from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
        from sklearn.model_selection import train_test_split

        split = int(len(X) * 0.8)
        X_train, X_test = X[:split], X[split:]
        y_train, y_test = y[:split], y[split:]
        if len(np.unique(y_train)) < 2:
            return predict_direction(df, fundamentals, model_type="rf")
        model = LGBMClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.05,
            random_state=42,
            verbose=-1,
            importance_type="gain",
        )
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        y_proba = model.predict_proba(X_test)[:, 1]

        latest = X[-1:].reshape(1, -1)
        proba = model.predict_proba(latest)[0]
        importances = sorted(
            zip(feature_names, model.feature_importances_), key=lambda x: x[1], reverse=True
        )[:10]
        return {
            "上涨概率": round(float(proba[1]) * 100, 1),
            "下跌概率": round(float(proba[0]) * 100, 1),
            "预测方向": "看涨" if proba[1] > 0.5 else "看跌",
            "置信度": round(max(proba) * 100, 1),
            "准确率%": round(accuracy_score(y_test, y_pred) * 100, 1),
            "精确率%": round(precision_score(y_test, y_pred) * 100, 1),
            "召回率%": round(recall_score(y_test, y_pred) * 100, 1),
            "AUC": round(roc_auc_score(y_test, y_proba), 3) if len(np.unique(y_test)) > 1 else 0,
            "训练样本": len(X_train),
            "测试样本": len(X_test),
            "重要特征": [{"特征": name, "重要性": round(imp, 4)} for name, imp in importances[:5]],
        }
    except ImportError:
        return predict_direction(df, fundamentals, model_type="rf")


# In-memory result cache (per process)
_RESULT_CACHE: dict[str, dict[str, Any]] = {}


def _cached_predict_ensemble(df, fundamentals=None):
    # Use shape + last 20 closing prices as cache key
    key = hashlib.md5(
        str(df.shape).encode()
        + str(df.iloc[-20:, 1].sum()).encode()
        + str(df.iloc[-1, 1]).encode(),
        usedforsecurity=False,
    ).hexdigest()
    if key in _RESULT_CACHE:
        return _RESULT_CACHE[key]
    result = predict_ensemble(df, fundamentals)
    _RESULT_CACHE[key] = result
    return result


def predict_ensemble(df, fundamentals=None):
    """三模型集成投票：XGBoost + RandomForest + LightGBM

    返回 dict:
        votes: 三个模型的预测方向
        ensemble_direction: 投票结果
        ensemble_confidence: 平均置信度
        agreement: 3/3一致=高, 2/3=中, 1/3=低
    """
    xgb = predict_direction(df, fundamentals, model_type="xgb")
    rf = predict_direction(df, fundamentals, model_type="rf")
    lgb = _predict_lgb(df, fundamentals)

    models = {"xgb": xgb, "rf": rf, "lgb": lgb}
    votes_up = 0
    total_prob = 0
    valid = 0

    for name, result in models.items():
        if "error" in result:
            continue
        valid += 1
        if result.get("预测方向") == "看涨":
            votes_up += 1
        prob = result.get("上涨概率", 50)
        # 转换为方向性置信度
        if result.get("预测方向") == "看跌":
            prob = 100 - prob
        total_prob += prob

    if valid < 2:
        return {"agreement": "数据不足", "ensemble_direction": "未知", "models": models}

    direction = "看涨" if votes_up >= valid / 2 else "看跌"
    avg_conf = total_prob / valid if valid > 0 else 50
    agreement = "高" if votes_up in (0, valid) else ("中" if valid >= 3 else "低")

    return {
        "agreement": agreement,
        "ensemble_direction": direction,
        "ensemble_confidence": round(avg_conf, 1),
        "models": models,
        "votes": f"{votes_up}/{valid}看涨",
    }


def predict_dual_model(df, fundamentals=None):
    """双模型验证：调用集成投票"""
    return predict_ensemble(df, fundamentals)
