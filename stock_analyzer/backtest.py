#!/usr/bin/env python
"""多策略回测框架

内置策略：MA金叉死叉 / MACD金叉死叉 / RSI超买超卖 / 布林带突破 /
        均线趋势 / 动量突破 / 双均线通道 / 网格交易

支持：参数网格优化、多策略对比、权益曲线、绩效指标
"""

import numpy as np
import pandas as pd

from stock_analyzer.config import TRADING_DAYS_PER_YEAR
from stock_analyzer.quant import calc_calmar_ratio, calc_sortino_ratio

# ═══════════════════════════════════════════
# 内置策略集
# ═══════════════════════════════════════════


def strategy_ma_cross(df, fast=5, slow=20):
    """MA 金叉死叉：快线上穿慢线买入，下穿卖出"""
    col_f, col_s = f"MA{fast}", f"MA{slow}"
    ma_fast = df[col_f] if col_f in df.columns else df["收盘"].rolling(fast).mean()
    ma_slow = df[col_s] if col_s in df.columns else df["收盘"].rolling(slow).mean()
    signals = pd.DataFrame({"signal": 0}, index=df.index)
    cross_up = (ma_fast > ma_slow) & (ma_fast.shift(1) <= ma_slow.shift(1))
    cross_down = (ma_fast < ma_slow) & (ma_fast.shift(1) >= ma_slow.shift(1))
    signals.loc[cross_up, "signal"] = 1
    signals.loc[cross_down, "signal"] = -1
    return signals


def strategy_macd_cross(df, fast=12, slow=26, sig=9):
    """MACD 金叉死叉：DIF上穿DEA买入，下穿卖出"""
    signals = pd.DataFrame({"signal": 0}, index=df.index)
    if "DIF" in df.columns and "DEA" in df.columns:
        dif, dea = df["DIF"], df["DEA"]
    else:
        ema_fast = df["收盘"].ewm(span=fast, adjust=False).mean()
        ema_slow = df["收盘"].ewm(span=slow, adjust=False).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=sig, adjust=False).mean()
    cross_up = (dif > dea) & (dif.shift(1) <= dea.shift(1))
    cross_down = (dif < dea) & (dif.shift(1) >= dea.shift(1))
    signals.loc[cross_up, "signal"] = 1
    signals.loc[cross_down, "signal"] = -1
    return signals


def strategy_rsi_reversal(df, period=14, oversold=30, overbought=70):
    """RSI 均值回归：超卖区域买入，回到中性或超买时卖出"""
    signals = pd.DataFrame(index=df.index)
    signals["signal"] = 0
    delta = df["收盘"].diff()
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    signals["RSI"] = rsi
    # 进入超卖区买入
    signals.loc[(rsi < oversold) & (rsi.shift(1) >= oversold), "signal"] = 1
    # 回到中性区(RSI>50)或超买区卖出
    signals.loc[((rsi > 50) & (rsi.shift(1) <= 50)) | (rsi > overbought), "signal"] = -1
    return signals


def strategy_bollinger_breakout(df, period=20, std=2):
    """布林带均值回归：跌破下轨买入，回到中轨或突破上轨卖出"""
    signals = pd.DataFrame({"signal": 0}, index=df.index)
    if "BB_UPPER" in df.columns and "BB_LOWER" in df.columns:
        upper, lower, middle = (
            df["BB_UPPER"],
            df["BB_LOWER"],
            df.get(
                "BB_MIDDLE",
                df["BB_MIDDLE"]
                if "BB_MIDDLE" in df.columns
                else (df["BB_UPPER"] + df["BB_LOWER"]) / 2,
            ),
        )
    elif "upper" in df.columns:
        upper, lower, middle = df["upper"], df["lower"], df["middle"]
    else:
        ma = df["收盘"].rolling(period).mean()
        sd = df["收盘"].rolling(period).std()
        upper, lower, middle = ma + std * sd, ma - std * sd, ma
    signals.loc[(df["收盘"] < lower) & (df["收盘"].shift(1) >= lower.shift(1)), "signal"] = 1
    signals.loc[(df["收盘"] > middle) | (df["收盘"] > upper), "signal"] = -1
    return signals


def strategy_ma_trend(df, short=5, mid=20, long=60):
    """均线多头排列趋势：三线多头持有，空头清仓"""
    signals = pd.DataFrame(index=df.index)
    signals["signal"] = 0
    ma_s = df["收盘"].rolling(short).mean()
    ma_m = df["收盘"].rolling(mid).mean()
    ma_l = df["收盘"].rolling(long).mean()
    signals["MA_S"] = ma_s
    signals["MA_M"] = ma_m
    signals["MA_L"] = ma_l
    # 多头排列第一天买入
    bull = (ma_s > ma_m) & (ma_m > ma_l)
    signals.loc[bull & ~bull.shift(1).fillna(False), "signal"] = 1
    # 空头排列第一天卖出
    bear = (ma_s < ma_m) & (ma_m < ma_l)
    signals.loc[bear & ~bear.shift(1).fillna(False), "signal"] = -1
    return signals


def strategy_momentum_breakout(df, lookback=20):
    """动量通道突破：突破N日最高买入，跌破N日最低卖出"""
    signals = pd.DataFrame(index=df.index)
    signals["signal"] = 0
    signals["high_n"] = df["最高"].rolling(lookback).max()
    signals["low_n"] = df["最低"].rolling(lookback).min()
    signals.loc[df["收盘"] > signals["high_n"].shift(1), "signal"] = 1
    signals.loc[df["收盘"] < signals["low_n"].shift(1), "signal"] = -1
    return signals


def strategy_grid(df, grid_pct=0.05):
    """网格交易：每跌grid_pct加仓，每涨grid_pct减仓"""
    prices = df["收盘"].values
    signals_arr = np.zeros(len(prices), dtype=int)
    base = prices[0]
    if base <= 0:
        return pd.DataFrame({"signal": signals_arr}, index=df.index)
    for i in range(1, len(prices)):
        if base <= 0:
            base = prices[i]
            continue
        change = (prices[i] - base) / base
        if change < -grid_pct:
            signals_arr[i] = 1
            base = prices[i]
        elif change > grid_pct:
            signals_arr[i] = -1
            base = prices[i]
    return pd.DataFrame({"signal": signals_arr}, index=df.index)


# ═══════════════════════════════════════════
# 策略注册表
# ═══════════════════════════════════════════

DEFAULT_COMPARE_STRATEGIES = [
    "ma_cross",
    "macd_cross",
    "rsi_reversal",
    "bollinger",
    "ma_trend",
    "momentum_breakout",
    "grid",
]


STRATEGIES = {
    "ma_cross": {
        "name": "MA金叉死叉",
        "fn": strategy_ma_cross,
        "params": {"fast": [5, 10, 20], "slow": [20, 30, 60]},
        "default": {"fast": 5, "slow": 20},
    },
    "macd_cross": {
        "name": "MACD金叉死叉",
        "fn": strategy_macd_cross,
        "params": {"fast": [12], "slow": [26], "sig": [9]},
        "default": {"fast": 12, "slow": 26, "sig": 9},
    },
    "rsi_reversal": {
        "name": "RSI超买超卖",
        "fn": strategy_rsi_reversal,
        "params": {"period": [14], "oversold": [25, 30, 35], "overbought": [65, 70, 75]},
        "default": {"period": 14, "oversold": 30, "overbought": 70},
    },
    "bollinger": {
        "name": "布林带均值回归",
        "fn": strategy_bollinger_breakout,
        "params": {"period": [20], "std": [2, 2.5]},
        "default": {"period": 20, "std": 2},
    },
    "ma_trend": {
        "name": "均线多头趋势",
        "fn": strategy_ma_trend,
        "params": {"short": [5], "mid": [10, 20], "long": [30, 60]},
        "default": {"short": 5, "mid": 20, "long": 60},
    },
    "momentum_breakout": {
        "name": "动量通道突破",
        "fn": strategy_momentum_breakout,
        "params": {"lookback": [10, 20, 30]},
        "default": {"lookback": 20},
    },
    "grid": {
        "name": "网格交易",
        "fn": strategy_grid,
        "params": {"grid_pct": [0.03, 0.05, 0.08]},
        "default": {"grid_pct": 0.05},
    },
}


# ═══════════════════════════════════════════
# 回测引擎
# ═══════════════════════════════════════════


def run_backtest(
    df,
    strategy_fn,
    strategy_params=None,
    initial_capital=100000,
    commission=0.0003,
    slippage=0.001,
    position_pct=1.0,
    stop_loss=None,
    take_profit=None,
    trailing_stop=None,
):
    """通用回测引擎

    参数:
        df: K线DataFrame（需含'收盘'列）
        strategy_fn: 策略函数，返回含'signal'列的DataFrame
        strategy_params: 策略参数字典
        initial_capital: 初始资金
        commission: 手续费率
        slippage: 滑点
        position_pct: 仓位比例
        stop_loss: 固定止损比例（如0.08=8%亏损止损）
        take_profit: 固定止盈比例（如0.15=15%盈利止盈）
        trailing_stop: 移动止损比例（如0.05=从最高点回撤5%止损）

    返回:
        dict: {trades, equity_curve, metrics, summary}
    """
    if strategy_params is None:
        strategy_params = {}

    # 列校验
    required = ["收盘"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"K线数据缺少必要列: {missing}，当前列: {list(df.columns)}")

    signals = strategy_fn(df, **strategy_params)
    if signals is None or signals.empty:
        return None

    # 消除前视偏差：信号后移一根K线，当日信号次日执行
    signals["signal"] = signals["signal"].shift(1).fillna(0).astype(int)

    # 模拟交易
    capital = initial_capital
    position = 0  # 持股数量
    entry_price = 0  # 开仓均价
    peak_since_entry = 0  # 持仓期间最高价（移动止损用）
    trades = []
    equity = [capital]

    def _close_position(exit_price, reason):
        """平仓辅助函数"""
        nonlocal capital, position, entry_price, peak_since_entry
        gross = position * exit_price * (1 - slippage)
        cfee = gross * commission
        capital += gross - cfee
        # PnL = 卖出收入 - 买入成本（均含手续费）
        entry_total = entry_price * position * (1 + slippage) * (1 + commission)
        pnl = (gross - cfee) - entry_total
        trades.append(
            {
                "date": str(df["日期"].iloc[i])[:10] if "日期" in df.columns else i,
                "action": "SELL",
                "price": round(exit_price, 2),
                "shares": 0,
                "capital": round(capital, 2),
                "pnl": round(pnl, 2),
                "exit_reason": reason,
            }
        )
        position = 0
        entry_price = 0
        peak_since_entry = 0

    for i in range(len(df)):
        price = float(df["收盘"].iloc[i])
        day_low = float(df["最低"].iloc[i]) if "最低" in df.columns else price
        day_high = float(df["最高"].iloc[i]) if "最高" in df.columns else price
        sig = int(signals["signal"].iloc[i])

        # ── 风控检查（持仓时逐日检测）──
        if position > 0:
            peak_since_entry = max(peak_since_entry, day_high)

            # 固定止损：日内最低价触及止损线
            if stop_loss is not None and entry_price > 0:
                sl_price = entry_price * (1 - stop_loss)
                if day_low <= sl_price:
                    _close_position(sl_price, "止损")

            # 固定止盈：日内最高价触及止盈线
            if position > 0 and take_profit is not None and entry_price > 0:
                tp_price = entry_price * (1 + take_profit)
                if day_high >= tp_price:
                    _close_position(tp_price, "止盈")

            # 移动止损：从持仓最高点回撤超过阈值
            if position > 0 and trailing_stop is not None and peak_since_entry > 0:
                ts_price = peak_since_entry * (1 - trailing_stop)
                if day_low <= ts_price:
                    _close_position(ts_price, "移动止损")

        # ── 策略信号 ──
        if sig == 1 and position == 0:  # 买入
            max_shares = int(capital * position_pct / (price * (1 + slippage)))
            if max_shares > 0:
                cost = max_shares * price * (1 + slippage)
                cfee = cost * commission
                capital -= cost + cfee
                position = max_shares
                entry_price = price
                peak_since_entry = price
                trades.append(
                    {
                        "date": str(df["日期"].iloc[i])[:10] if "日期" in df.columns else i,
                        "action": "BUY",
                        "price": round(price, 2),
                        "shares": position,
                        "capital": round(capital, 2),
                    }
                )

        elif sig == -1 and position > 0:  # 卖出（策略信号）
            gross = position * price * (1 - slippage)
            cfee = gross * commission
            capital += gross - cfee
            entry_total = entry_price * position * (1 + slippage) * (1 + commission)
            pnl = (gross - cfee) - entry_total
            trades.append(
                {
                    "date": str(df["日期"].iloc[i])[:10] if "日期" in df.columns else i,
                    "action": "SELL",
                    "price": round(price, 2),
                    "shares": 0,
                    "capital": round(capital, 2),
                    "pnl": round(pnl, 2),
                    "exit_reason": "策略",
                }
            )
            position = 0
            entry_price = 0
            peak_since_entry = 0

        # 权益曲线（含持仓市值）
        market_value = position * price
        equity.append(capital + market_value)

    # 清仓
    if position > 0:
        last_price = float(df["收盘"].iloc[-1])
        revenue = position * last_price * (1 - slippage)
        capital += revenue - revenue * commission
        trades.append(
            {
                "date": str(df["日期"].iloc[-1])[:10] if "日期" in df.columns else len(df) - 1,
                "action": "SELL",
                "price": round(last_price, 2),
                "shares": 0,
                "capital": round(capital, 2),
                "pnl": round(revenue - entry_price * position - revenue * commission, 2),
                "exit_reason": "到期清仓",
            }
        )
        position = 0

    # 绩效指标
    equity_series = pd.Series(equity)
    returns = equity_series.pct_change().dropna()

    total_return = (equity[-1] / initial_capital - 1) * 100
    benchmark_return = (float(df["收盘"].iloc[-1]) / float(df["收盘"].iloc[0]) - 1) * 100
    n_trades = len([t for t in trades if t["action"] == "SELL"])
    win_trades = len([t for t in trades if t["action"] == "SELL" and t.get("pnl", 0) >= 0])
    win_rate = (win_trades / n_trades * 100) if n_trades > 0 else 0

    # 夏普
    sharpe = (
        (returns.mean() / returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR))
        if len(returns) > 0 and returns.std() > 0
        else 0
    )

    # 索提诺比率（仅下行风险）+ 卡玛比率
    sortino = calc_sortino_ratio(returns) or 0
    calmar = calc_calmar_ratio(returns, equity_series) or 0

    # 最大回撤
    peak = equity_series.expanding().max()
    drawdown = (equity_series - peak) / peak * 100
    max_dd = drawdown.min()

    # 盈亏比
    avg_win = np.mean([t["pnl"] for t in trades if t.get("pnl", 0) > 0]) if win_trades > 0 else 0
    avg_loss = (
        abs(np.mean([t["pnl"] for t in trades if t.get("pnl", 0) < 0]))
        if (n_trades - win_trades) > 0
        else 1
    )
    profit_factor = avg_win / avg_loss if avg_loss > 0 else 0

    # 几何年化收益率
    years = max(len(df) / TRADING_DAYS_PER_YEAR, 0.5)
    ann_return = ((1 + total_return / 100) ** (1 / years) - 1) * 100

    metrics = {
        "总收益率%": round(total_return, 2),
        "年化收益率%": round(ann_return, 2),
        "夏普比率": round(sharpe, 2),
        "索提诺比率": round(sortino, 2),
        "卡玛比率": round(calmar, 2),
        "最大回撤%": round(max_dd, 2),
        "交易次数": n_trades,
        "胜率%": round(win_rate, 1),
        "盈亏比": round(profit_factor, 2),
        "最终资金": round(equity[-1], 2),
        "基准收益%": round(benchmark_return, 2),
        "超额收益%": round(total_return - benchmark_return, 2),
    }

    return {
        "trades": trades,
        "equity_curve": equity,
        "metrics": metrics,
        "summary": f"收益率{total_return:.1f}% | 夏普{sharpe:.2f} | "
        f"回撤{abs(max_dd):.1f}% | 胜率{win_rate:.0f}% | 交易{n_trades}次",
    }


def compare_strategies(
    df,
    strategies=None,
    initial_capital=100000,
    verbose=True,
    commission=0.0003,
    slippage=0.001,
    position_pct=1.0,
    stop_loss=None,
    take_profit=None,
    trailing_stop=None,
):
    """多策略对比回测"""
    if strategies is None:
        strategies = DEFAULT_COMPARE_STRATEGIES

    results = {}
    skipped = []
    for s_name in strategies:
        if s_name not in STRATEGIES:
            skipped.append(f"{s_name}(未知策略)")
            continue
        s_info = STRATEGIES[s_name]
        result = run_backtest(
            df,
            s_info["fn"],
            s_info["default"],
            initial_capital,
            commission,
            slippage,
            position_pct,
            stop_loss,
            take_profit,
            trailing_stop,
        )
        if result:
            results[s_name] = {
                "name": s_info["name"],
                "metrics": result["metrics"],
                "summary": result["summary"],
            }
        else:
            skipped.append(s_info["name"])

    if verbose and skipped:
        print(f"  [跳过] {', '.join(skipped)}: 信号不足")

    return results


def optimize_strategy(df, strategy_name, param_grid=None, test_pct=0.3):
    """策略参数网格优化（含样本外验证）

    参数:
        df: K线DataFrame
        strategy_name: 策略名
        param_grid: 参数搜索空间（默认用注册表）
        test_pct: 样本外比例（默认30%）
    """
    if strategy_name not in STRATEGIES:
        return None

    s_info = STRATEGIES[strategy_name]
    if param_grid is None:
        param_grid = s_info["params"]

    from itertools import product

    keys = list(param_grid.keys())
    values = list(param_grid.values())
    combinations = [dict(zip(keys, combo)) for combo in product(*values)]

    # 训练/测试分割
    split_idx = int(len(df) * (1 - test_pct))
    train_df = df.iloc[:split_idx]
    test_df = df.iloc[split_idx:]

    best = None
    best_sharpe = -999
    total = len(combinations)

    for idx, params in enumerate(combinations):
        result = run_backtest(train_df, s_info["fn"], params)
        if result and result["metrics"]["夏普比率"] > best_sharpe:
            best_sharpe = result["metrics"]["夏普比率"]
            best = {"params": params, "metrics": result["metrics"], "summary": result["summary"]}
        if total > 10 and (idx + 1) % max(1, total // 10) == 0:
            import sys

            sys.stderr.write(f"\r  优化进度: {idx + 1}/{total} ({100 * (idx + 1) // total}%)")
            sys.stderr.flush()

    if total > 10:
        import sys

        sys.stderr.write(f"\r  优化完成: 共测试{total}组参数\n")
        sys.stderr.flush()

    if best is None:
        return None

    # 样本外验证
    test_result = run_backtest(test_df, s_info["fn"], best["params"])
    if test_result:
        best["test_metrics"] = test_result["metrics"]
        best["test_summary"] = test_result["summary"]
        best["train_days"] = len(train_df)
        best["test_days"] = len(test_df)

    return best


def export_backtest_json(result, filepath):
    """导出回测结果为JSON文件"""
    import json

    data = {
        "metrics": result.get("metrics", {}),
        "trades": result.get("trades", []),
        "equity_curve": result.get("equity_curve", []),
        "summary": result.get("summary", ""),
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    return filepath
