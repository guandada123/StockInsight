"""持仓组合服务层 — 组合 CRUD 与分析

职责:
    - 组合列表 / 详情 / 创建 / 更新 / 删除
    - 组合分析（收益统计、调仓建议）
"""

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


# 组合文件根目录（与 router 一致）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PORTFOLIO_DIR = os.path.join(PROJECT_ROOT, "portfolios")


def _portfolio_path(name: str) -> str:
    """获取组合文件路径"""
    return os.path.join(PORTFOLIO_DIR, f"{name}.json")


def list_portfolios() -> dict[str, Any]:
    """列出所有持仓组合"""
    os.makedirs(PORTFOLIO_DIR, exist_ok=True)
    portfolios = []
    for f in os.listdir(PORTFOLIO_DIR):
        if f.endswith(".json"):
            name = f.replace(".json", "")
            fpath = os.path.join(PORTFOLIO_DIR, f)
            mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(fpath)))
            try:
                with open(fpath, encoding="utf-8") as fh:
                    data = json.load(fh)
                holdings = data.get("holdings", data.get("stocks", {}))
                portfolios.append({"name": name, "holdings_count": len(holdings), "updated": mtime})
            except Exception:
                portfolios.append({"name": name, "holdings_count": 0, "updated": mtime})
    return {"portfolios": portfolios}


def get_portfolio(name: str) -> dict[str, Any]:
    """获取持仓组合详情（含实时行情）"""
    from stock_analyzer.fetcher import sina_real_time

    fpath = _portfolio_path(name)
    if not os.path.exists(fpath):
        raise FileNotFoundError(f"组合 {name} 不存在")

    with open(fpath, encoding="utf-8") as f:
        data = json.load(f)

    holdings_raw = data.get("holdings", data.get("stocks", {}))
    if not holdings_raw:
        return {
            "name": name,
            "holdings": [],
            "total_value": 0,
            "total_cost": 0,
            "total_profit": 0,
            "total_profit_pct": 0,
            "count": 0,
        }

    codes = list(holdings_raw.keys())
    rt = sina_real_time(codes)

    holdings = []
    total_cost = 0
    total_value = 0
    for code, pos in holdings_raw.items():
        info = rt.get(code, {})
        p = float(info.get("最新价", 0) or 0)
        cost = pos.get("cost", 0)
        shares = pos.get("shares", 0)
        mv = round(p * shares, 2)
        profit = round((p - cost) * shares, 2)
        profit_pct = round((p - cost) / cost * 100, 2) if cost else 0
        total_cost += cost * shares
        total_value += mv
        holdings.append(
            {
                "code": code,
                "name": info.get("名称", code),
                "shares": shares,
                "cost": cost,
                "current_price": p,
                "market_value": mv,
                "profit_amount": profit,
                "profit_pct": profit_pct,
                "weight_pct": 0,
            }
        )

    for h in holdings:
        h["weight_pct"] = round(h["market_value"] / total_value * 100, 1) if total_value else 0

    total_profit = round(total_value - total_cost, 2)
    total_profit_pct = round(total_profit / total_cost * 100, 2) if total_cost else 0

    return {
        "name": name,
        "holdings": sorted(holdings, key=lambda x: x["profit_pct"], reverse=True),
        "total_value": round(total_value, 2),
        "total_cost": round(total_cost, 2),
        "total_profit": total_profit,
        "total_profit_pct": total_profit_pct,
        "count": len(holdings),
        "update_time": time.strftime("%H:%M:%S"),
    }


def create_portfolio(name: str, codes: str = "") -> dict[str, Any]:
    """创建新持仓组合"""
    fpath = _portfolio_path(name)
    if os.path.exists(fpath):
        raise FileExistsError(f"组合 {name} 已存在")

    holdings = {}
    if codes.strip():
        code_list = [c.strip() for c in codes.split(",") if c.strip()]
        for code in code_list:
            holdings[code] = {"shares": 0, "cost": 0}

    data = {"name": name, "created": time.strftime("%Y-%m-%d"), "holdings": holdings}
    os.makedirs(PORTFOLIO_DIR, exist_ok=True)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {"name": name, "holdings_count": len(holdings)}


def update_portfolio_holding(
    name: str, code: str, shares: int = 0, cost: float = 0.0, action: str = "add"
) -> dict[str, Any]:
    """更新持仓组合中的股票"""
    fpath = _portfolio_path(name)
    if not os.path.exists(fpath):
        raise FileNotFoundError(f"组合 {name} 不存在")

    with open(fpath, encoding="utf-8") as f:
        data = json.load(f)

    if "holdings" not in data:
        data["holdings"] = {}

    if action == "remove":
        data["holdings"].pop(code, None)
    else:
        data["holdings"][code] = {
            "shares": shares,
            "cost": cost,
            "updated": time.strftime("%Y-%m-%d"),
        }

    data["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {"name": name, "code": code, "action": action}


def delete_portfolio(name: str) -> dict[str, Any]:
    """删除持仓组合"""
    fpath = _portfolio_path(name)
    if not os.path.exists(fpath):
        raise FileNotFoundError(f"组合 {name} 不存在")
    os.remove(fpath)
    return {"deleted": name}


def analyze_portfolio(name: str) -> dict[str, Any]:
    """组合分析 — 收益率/波动率/夏普/调仓建议"""
    from stock_analyzer.fetcher import sina_real_time

    fpath = _portfolio_path(name)
    if not os.path.exists(fpath):
        raise FileNotFoundError(f"组合 {name} 不存在")

    with open(fpath, encoding="utf-8") as f:
        data = json.load(f)

    holdings_raw = data.get("holdings", data.get("stocks", {}))
    if not holdings_raw:
        return {"name": name, "holdings": [], "suggestion": "空组合，请添加股票"}

    codes = list(holdings_raw.keys())
    rt = sina_real_time(codes)

    holdings = []
    total_value = 0
    total_cost = 0
    for code, pos in holdings_raw.items():
        info = rt.get(code, {})
        p = float(info.get("最新价", 0) or 0)
        cost = pos.get("cost", 0)
        shares = pos.get("shares", 0)
        mv = p * shares
        total_value += mv
        total_cost += cost * shares
        holdings.append(
            {
                "code": code,
                "name": info.get("名称", code),
                "shares": shares,
                "cost": cost,
                "current_price": p,
                "market_value": round(mv, 2),
                "profit_pct": round((p - cost) / cost * 100, 2) if cost else 0,
            }
        )

    suggestion = _build_rebalance_suggestion(holdings, total_value)

    return {
        "name": name,
        "holdings": holdings,
        "total_value": round(total_value, 2),
        "total_cost": round(total_cost, 2),
        "total_profit_pct": round((total_value - total_cost) / total_cost * 100, 2)
        if total_cost
        else 0,
        "suggestion": suggestion,
    }


def _build_rebalance_suggestion(holdings, total_value):
    """生成简单的调仓建议"""
    if not holdings or total_value <= 0:
        return "数据不足，无法生成建议"

    parts = []
    for h in holdings:
        weight = h["market_value"] / total_value * 100
        pnl = h["profit_pct"]

        if pnl > 10:
            parts.append(f"{h['name']}({h['code']}) 盈利 {pnl}%，建议考虑部分止盈")
        elif pnl < -8:
            parts.append(f"{h['name']}({h['code']}) 亏损 {pnl}%，建议评估是否需要止损")
        elif weight > 40:
            parts.append(f"{h['name']}({h['code']}) 占比 {weight:.0f}%，集中度偏高，建议分散")

    if not parts:
        parts.append("当前持仓结构合理，无需调整")
    return "；".join(parts)
