"""自定义因子表达式引擎

支持用户通过受限表达式定义量化因子，如:
  close.pct_change(10)                          → 10日动量
  (close - close.rolling(20).mean()) / close.rolling(20).std() → 布林带位置
  vol / vol.rolling(20).mean()                  → 量比
  abs(close - open) / close                     → 日内振幅

安全机制:
  1. AST 白名单: 仅允许指定列名和函数
  2. 禁止双下划线方法 (__xxx__)
  3. 仅允许数值常量
  4. 防注入: 表达式必须是有效的 eval AST
"""

import ast
import operator
import os

# SQLite 因子存储
import sqlite3
import time
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "stock_cache.db")


class FactorExpressionEngine:
    """安全执行自定义因子表达式"""

    def __init__(self, allowed_columns: set | None = None):
        self.allowed_columns = allowed_columns or {
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "change_c",
            "pct_chg",
            "vol",
            "amount",
        }
        self.allowed_series_methods = {
            "pct_change",
            "shift",
            "diff",
            "rank",
            "rolling",
        }
        self.allowed_window_methods = {
            "mean",
            "std",
            "max",
            "min",
            "sum",
        }
        self.allowed_functions = {"abs": abs}
        self.bin_ops = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.Pow: operator.pow,
            ast.Mod: operator.mod,
        }
        self.unary_ops = {
            ast.UAdd: operator.pos,
            ast.USub: operator.neg,
        }

    def evaluate(self, expression: str, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=["factor_value"])
        if not expression or not str(expression).strip():
            raise ValueError("表达式为空")

        parsed = ast.parse(expression, mode="eval")
        value = self._eval_node(parsed.body, df)

        if np.isscalar(value):
            value = pd.Series([float(value)] * len(df), index=df.index)
        if not isinstance(value, pd.Series):
            raise ValueError("表达式结果必须是 pandas Series")

        result = df.copy()
        result["factor_value"] = pd.to_numeric(value, errors="coerce")
        return result

    def _eval_node(self, node: ast.AST, df: pd.DataFrame):
        if isinstance(node, ast.BinOp):
            left = self._eval_node(node.left, df)
            right = self._eval_node(node.right, df)
            op = self.bin_ops.get(type(node.op))
            if op is None:
                raise ValueError(f"不支持的运算符: {type(node.op).__name__}")
            return op(left, right)
        if isinstance(node, ast.UnaryOp):
            op = self.unary_ops.get(type(node.op))
            if op is None:
                raise ValueError(f"不支持的一元运算符: {type(node.op).__name__}")
            return op(self._eval_node(node.operand, df))
        if isinstance(node, ast.Name):
            if node.id.startswith("__"):
                raise ValueError("不安全的表达式")
            if node.id not in self.allowed_columns:
                raise ValueError(f"列名不允许: {node.id}")
            if node.id not in df.columns:
                raise ValueError(f"列不存在: {node.id}")
            return pd.to_numeric(df[node.id], errors="coerce")
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("仅允许数值常量")
        if isinstance(node, ast.Call):
            return self._eval_call(node, df)
        raise ValueError(f"不支持的节点类型: {type(node).__name__}")

    def _eval_call(self, node: ast.Call, df: pd.DataFrame):
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name not in self.allowed_functions:
                raise ValueError(f"函数不允许: {func_name}")
            args = [self._as_scalar(self._eval_node(arg, df), "arg") for arg in node.args]
            return self.allowed_functions[func_name](*args)

        if not isinstance(node.func, ast.Attribute):
            raise ValueError("不支持的调用方式")

        method_name = node.func.attr
        if method_name.startswith("__"):
            raise ValueError("不安全的方法")

        target = self._eval_node(node.func.value, df)
        raw_args = [self._eval_node(arg, df) for arg in node.args]

        if method_name == "rolling":
            if not isinstance(target, pd.Series):
                raise ValueError("rolling() 必须作用在 Series 上")
            window = int(self._as_scalar(raw_args[0], "window")) if raw_args else None
            if window is None or window <= 0:
                raise ValueError("rolling 窗口必须为正整数")
            return target.rolling(window=window)

        if isinstance(target, pd.Series):
            if method_name not in self.allowed_series_methods:
                raise ValueError(f"Series 方法不允许: {method_name}")
            args = [self._as_scalar(a, "arg") for a in raw_args]
            return getattr(target, method_name)(*args)

        if hasattr(target, method_name):
            if method_name not in self.allowed_window_methods:
                raise ValueError(f"窗口方法不允许: {method_name}")
            args = [self._as_scalar(a, "arg") for a in raw_args]
            return getattr(target, method_name)(*args)

        raise ValueError(f"不支持的方法: {method_name}")

    def _as_scalar(self, value: Any, name: str):
        if isinstance(value, (int, np.integer)):
            return int(value)
        if isinstance(value, (float, np.floating)):
            return float(value)
        raise ValueError(f"{name} 必须为数值标量")


# ═══════════════════════════════════════════
# 因子管理 (SQLite 持久化)
# ═══════════════════════════════════════════


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_factor_table():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS custom_factors (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            expression TEXT NOT NULL,
            factor_type TEXT DEFAULT 'custom',
            description TEXT DEFAULT '',
            created_at REAL,
            updated_at REAL
        )
    """)
    conn.commit()
    conn.close()


def list_factors() -> list:
    init_factor_table()
    conn = _get_conn()
    cur = conn.execute(
        "SELECT id, name, expression, factor_type, description, created_at FROM custom_factors ORDER BY created_at DESC"
    )
    rows = []
    for r in cur.fetchall():
        rows.append(
            {
                "id": r[0],
                "name": r[1],
                "expression": r[2],
                "type": r[3],
                "description": r[4],
                "created": time.strftime("%Y-%m-%d %H:%M", time.localtime(r[5])) if r[5] else "",
            }
        )
    conn.close()
    return rows


def create_factor(
    factor_id: str, name: str, expression: str, factor_type: str = "custom", description: str = ""
) -> dict:
    init_factor_table()
    # 验证表达式语法
    engine = FactorExpressionEngine()
    try:
        ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"表达式语法错误: {e}")
    conn = _get_conn()
    now = time.time()
    conn.execute(
        "INSERT OR REPLACE INTO custom_factors VALUES (?,?,?,?,?,?,?)",
        (factor_id, name, expression, factor_type, description, now, now),
    )
    conn.commit()
    conn.close()
    return {"id": factor_id, "name": name, "expression": expression}


def delete_factor(factor_id: str):
    conn = _get_conn()
    conn.execute("DELETE FROM custom_factors WHERE id=?", (factor_id,))
    conn.commit()
    conn.close()


def compute_factor(code: str, factor_id: str, df: pd.DataFrame | None = None) -> dict:
    """计算某只股票的自定义因子值"""
    init_factor_table()
    conn = _get_conn()
    cur = conn.execute("SELECT expression FROM custom_factors WHERE id=?", (factor_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise ValueError(f"因子不存在: {factor_id}")

    if df is None:
        from stock_analyzer.cache import cached_kline

        df = cached_kline(code, days=120)

    # 列名映射：中文→英文 (支持两种列名)
    col_map = {
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "vol",
        "成交额": "amount",
        "昨收": "pre_close",
        "涨跌幅": "pct_chg",
        "涨跌额": "change_c",
    }
    # 只重命名存在的列
    rename_dict = {k: v for k, v in col_map.items() if k in df.columns}
    mapped = df.rename(columns=rename_dict)

    expr = row[0]  # expression 是 SELECT 的第一个（也是唯一）字段
    engine = FactorExpressionEngine()
    result = engine.evaluate(expr, mapped)
    latest = float(result["factor_value"].dropna().iloc[-1]) if not result.empty else None
    return {
        "code": code,
        "factor_id": factor_id,
        "value": round(latest, 4) if latest is not None else None,
        "expression": expr,
    }


def compute_all_factors(code: str, df: pd.DataFrame | None = None) -> list:
    """计算该股票所有自定义因子"""
    factors = list_factors()
    results = []
    for f in factors:
        try:
            r = compute_factor(code, f["id"], df)
            results.append(r)
        except Exception as e:
            results.append({"code": code, "factor_id": f["id"], "value": None, "error": str(e)})
    return results
