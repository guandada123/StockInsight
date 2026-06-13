"""投资组合管理模块

支持组合的创建/保存/读取/增删股票、组合整体分析（收益率/波动率/夏普/贡献度）、调仓建议。
依赖: cache.cached_kline
"""

import json
import os
from datetime import date

import numpy as np
import pandas as pd

from .cache import cached_kline
from .config import PORTFOLIO_DIR

# ── 内部工具 ─────────────────────────────────────


def _ensure_dir():
    """确保组合存储目录存在"""
    os.makedirs(PORTFOLIO_DIR, exist_ok=True)


def _portfolio_path(name):
    """获取组合 JSON 文件的完整路径"""
    return os.path.join(PORTFOLIO_DIR, f"{name}.json")


def _get_current_price(code):
    """获取某只股票最新收盘价"""
    df = cached_kline(code, days=30)
    if df.empty:
        return None
    return float(df["收盘"].iloc[-1])


def _get_daily_returns_series(code, days=252):
    """获取某只股票每日收益率序列（以日期为索引）"""
    df = cached_kline(code, days=days)
    if df.empty or len(df) < 2:
        return pd.Series(dtype=float)
    df = df.sort_values("日期")
    s = df.set_index("日期")["收盘"].pct_change().dropna()
    return s


# ── 基本操作 ─────────────────────────────────────


def create_portfolio(name, stocks=None):
    """新建组合并保存

    Parameters
    ----------
    name : str
        组合名称，同时用作文件名
    stocks : list[dict] or None
        每项包含 code / weight / cost，如::

            [{"code": "300408", "weight": 0.4, "cost": 100.0}]

    Returns
    -------
    dict : 组合数据
    """
    portfolio = {
        "name": name,
        "created_at": date.today().isoformat(),
        "stocks": stocks or [],
    }
    save_portfolio(portfolio)
    return portfolio


def save_portfolio(portfolio):
    """保存组合到 JSON 文件"""
    _ensure_dir()
    path = _portfolio_path(portfolio["name"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(portfolio, f, ensure_ascii=False, indent=2)
    return True


def load_portfolio(name):
    """读取组合 JSON 文件

    Parameters
    ----------
    name : str
        组合名称（不含 .json 后缀）

    Returns
    -------
    dict or None
    """
    path = _portfolio_path(name)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_portfolios():
    """列出所有组合名称

    Returns
    -------
    list[str]
    """
    _ensure_dir()
    files = [f for f in os.listdir(PORTFOLIO_DIR) if f.endswith(".json")]
    return sorted(os.path.splitext(f)[0] for f in files)


def add_stock(portfolio, code, weight, cost):
    """加仓：向组合中添加股票（若已存在则覆盖）

    Parameters
    ----------
    portfolio : dict
    code : str
    weight : float
    cost : float

    Returns
    -------
    dict : 更新后的组合（直接修改原对象）
    """
    stocks = portfolio.setdefault("stocks", [])
    for i, s in enumerate(stocks):
        if s["code"] == code:
            stocks[i] = {"code": code, "weight": weight, "cost": cost}
            return portfolio
    stocks.append({"code": code, "weight": weight, "cost": cost})
    return portfolio


def remove_stock(portfolio, code):
    """减仓：从组合中移除指定股票

    Returns
    -------
    dict : 更新后的组合（直接修改原对象）
    """
    portfolio["stocks"] = [s for s in portfolio.get("stocks", []) if s["code"] != code]
    return portfolio


# ── 组合分析 ─────────────────────────────────────


def analyze_portfolio(portfolio):
    """组合整体分析

    对每只股票调用 cached_kline 获取最新价和收益率序列，
    计算组合层面的总市值、总收益、加权波动率（协方差矩阵）、夏普比率和各股贡献度。

    Parameters
    ----------
    portfolio : dict
        包含 "name" 和 "stocks" 的组合字典

    Returns
    -------
    dict ::

        {
            "组合名称": str,
            "total_value": float,          # 总市值（相对值）
            "total_cost": float,           # 总成本（相对值）
            "total_return_pct": float,     # 总收益率 %
            "portfolio_volatility_pct": float,  # 组合年化波动率 %
            "portfolio_sharpe": float,     # 组合夏普比率
            "stocks": [
                {
                    "代码": str,
                    "现价": float or None,
                    "成本": float,
                    "仓位%": float,          # 当前市值占比 %
                    "市值": float,
                    "收益率%": float,        # 个股收益率 %
                    "贡献度%": float,        # 对组合收益率的贡献占比 %
                },
            ],
        }
    """
    stocks = portfolio.get("stocks", [])
    if not stocks:
        return _empty_result(portfolio.get("name", ""))

    # ── 1. 获取每只股票最新价和收益率序列 ──
    stock_info = []
    for s in stocks:
        code = s["code"]
        weight = s["weight"]
        cost = s["cost"]
        current_price = _get_current_price(code)
        daily_ret = (
            _get_daily_returns_series(code, days=252)
            if current_price is not None
            else pd.Series(dtype=float)
        )
        stock_info.append(
            {
                "code": code,
                "weight": weight,
                "cost": cost,
                "price": current_price,
                "daily_ret": daily_ret,
            }
        )

    # ── 2. 总市值 / 总成本 / 总收益率 ──
    total_cost = sum(s["weight"] for s in stock_info)
    total_value = sum(
        s["weight"] * (s["price"] / s["cost"]) for s in stock_info if s["price"] is not None
    )
    # 如果有股票无现价，总市值用原始权重替代
    any_none_price = any(s["price"] is None for s in stock_info)
    if any_none_price:
        total_value = sum(
            s["weight"] * (s["price"] / s["cost"] if s["price"] is not None else 1.0)
            for s in stock_info
        )

    portfolio_return = (total_value / total_cost - 1) if total_cost > 0 else 0.0

    # ── 3. 协方差矩阵 & 组合波动率 ──
    valid_ret = {s["code"]: s["daily_ret"] for s in stock_info if not s["daily_ret"].empty}

    if len(valid_ret) >= 2:
        ret_df = pd.DataFrame(valid_ret).dropna()
        if not ret_df.empty and ret_df.shape[1] >= 2:
            # 对齐后的权重（只保留有数据的股票）
            codes_aligned = list(ret_df.columns)
            aligned_weights = np.array(
                [s["weight"] for s in stock_info if s["code"] in codes_aligned]
            )
            aligned_weights = aligned_weights / aligned_weights.sum()

            cov_matrix = ret_df.cov()
            portfolio_var = float(aligned_weights.T @ cov_matrix @ aligned_weights)
            portfolio_vol = float(np.sqrt(portfolio_var) * np.sqrt(252) * 100)
        else:
            portfolio_vol = 0.0
    else:
        portfolio_vol = 0.0

    # ── 4. 组合夏普比率 ──
    portfolio_return_pct = portfolio_return * 100
    if portfolio_vol > 1e-10:
        portfolio_sharpe = (portfolio_return_pct / 100 - 0.03) / (portfolio_vol / 100)
    else:
        portfolio_sharpe = None

    # ── 5. 各股贡献度 ──
    contributions = []
    for s in stock_info:
        stock_ret = (s["price"] / s["cost"] - 1) if s["price"] is not None else 0.0
        if abs(portfolio_return) > 1e-10:
            contrib = s["weight"] * stock_ret / portfolio_return * 100
        else:
            contrib = 0.0
        contributions.append(contrib)

    # ── 6. 组装结果 ──
    stock_details = []
    for i, s in enumerate(stock_info):
        if s["price"] is not None:
            stock_value = s["weight"] * s["price"] / s["cost"]
            stock_ret_pct = (s["price"] / s["cost"] - 1) * 100
        else:
            stock_value = s["weight"]
            stock_ret_pct = 0.0
        weight_pct = (stock_value / total_value * 100) if total_value > 0 else s["weight"] * 100

        stock_details.append(
            {
                "代码": s["code"],
                "现价": s["price"],
                "成本": s["cost"],
                "仓位%": round(weight_pct, 2),
                "市值": round(stock_value, 4),
                "收益率%": round(stock_ret_pct, 2),
                "贡献度%": round(contributions[i], 2),
            }
        )

    return {
        "组合名称": portfolio.get("name", ""),
        "total_value": round(total_value, 4),
        "total_cost": round(total_cost, 4),
        "total_return_pct": round(portfolio_return_pct, 2),
        "portfolio_volatility_pct": round(portfolio_vol, 2),
        "portfolio_sharpe": round(portfolio_sharpe, 4) if portfolio_sharpe is not None else None,
        "stocks": stock_details,
    }


def _empty_result(name):
    """返回空组合的分析结果"""
    return {
        "组合名称": name,
        "total_value": 0,
        "total_cost": 0,
        "total_return_pct": 0,
        "portfolio_volatility_pct": 0,
        "portfolio_sharpe": None,
        "stocks": [],
    }


# ── 调仓建议 ─────────────────────────────────────


def rebalance(portfolio, target_weights):
    """调仓建议

    基于当前市值占比与目标权重的偏差，偏差绝对值超过 5% 给出调仓提示。

    Parameters
    ----------
    portfolio : dict
        组合数据，含 "stocks"
    target_weights : dict
        目标权重，格式 {code: weight, ...}

    Returns
    -------
    list[dict] ::

        [
            {
                "代码": str,
                "当前仓位%": float,
                "目标仓位%": float,
                "偏差%": float,
                "建议": str,   # "增持" / "减持" / "持有"
            },
        ]
    """
    stocks = portfolio.get("stocks", [])
    if not stocks:
        return []

    # 计算当前市值
    values = {}
    for s in stocks:
        code = s["code"]
        cost = s["cost"]
        weight = s["weight"]
        price = _get_current_price(code)
        if price is not None:
            values[code] = weight * price / cost
        else:
            values[code] = weight

    total_val = sum(values.values())
    current_weights = {k: v / total_val for k, v in values.items()} if total_val > 0 else {}

    # 对比目标权重
    all_codes = set(current_weights.keys()) | set(target_weights.keys())
    suggestions = []
    for code in sorted(all_codes):
        cw = current_weights.get(code, 0.0) * 100
        tw = target_weights.get(code, 0.0) * 100
        deviation = cw - tw

        if deviation > 5:
            action = "减持"
        elif deviation < -5:
            action = "增持"
        else:
            action = "持有"

        suggestions.append(
            {
                "代码": code,
                "当前仓位%": round(cw, 2),
                "目标仓位%": round(tw, 2),
                "偏差%": round(deviation, 2),
                "建议": action,
            }
        )

    return suggestions


def optimize_portfolio(holdings, method="max_sharpe"):
    """投资组合优化 — 借鉴对方均值方差/风险平价/最大夏普/最小方差

    Args:
        holdings: list of dict, [{code, name, cost, shares, price}, ...]
        method: 'max_sharpe' / 'min_variance' / 'risk_parity' / 'equal_weight'

    Returns:
        dict with optimized weights, expected return, volatility, sharpe
    """
    if len(holdings) < 2:
        return {"weights": [1.0], "method": "单一持仓"}

    try:
        codes = [h["code"] for h in holdings]
        prices = [h.get("price", h.get("cost", 0)) for h in holdings]

        # 取近60日K线计算收益和协方差
        returns_list = []
        valid_codes = []
        for code in codes:
            kline = cached_kline(code)
            if kline is not None and len(kline) >= 30:
                ret = kline["收盘"].pct_change().dropna().tail(60)
                returns_list.append(ret.values)
                valid_codes.append(code)

        if len(valid_codes) < 2:
            return {"weights": [1.0 / len(holdings)] * len(holdings), "method": "数据不足-等权"}

        returns_df = pd.DataFrame({c: r for c, r in zip(valid_codes, returns_list)})
        mu = returns_df.mean() * 252
        sigma = returns_df.cov() * 252
        n = len(valid_codes)

        if method == "min_variance":
            ones = np.ones(n)
            inv_sigma = np.linalg.inv(sigma.values)
            w = inv_sigma @ ones / (ones @ inv_sigma @ ones)
        elif method == "risk_parity":
            # 简化：每只股票风险贡献相等 → 权重反比波动率
            vols = np.sqrt(np.diag(sigma.values))
            w = (1.0 / vols) / np.sum(1.0 / vols)
        elif method == "max_sharpe":
            # 最大夏普比：w ∝ Σ⁻¹μ
            inv_sigma = np.linalg.inv(sigma.values)
            w = inv_sigma @ mu.values
            w = np.maximum(w, 0)  # 不允许做空
            w = w / np.sum(w) if np.sum(w) > 0 else np.ones(n) / n
        else:  # equal_weight
            w = np.ones(n) / n

        port_return = float(np.dot(w, mu.values) * 100)
        port_vol = float(np.sqrt(w @ sigma.values @ w) * 100)
        port_sharpe = float(port_return / port_vol) if port_vol > 0 else 0

        weights = {valid_codes[i]: round(w[i] * 100, 1) for i in range(n)}

        return {
            "method": method,
            "weights": weights,
            "expected_return_pct": round(port_return, 2),
            "expected_volatility_pct": round(port_vol, 2),
            "expected_sharpe": round(port_sharpe, 2),
        }
    except Exception:
        return {"weights": [1.0 / len(holdings)] * len(holdings), "method": "计算异常-等权"}
