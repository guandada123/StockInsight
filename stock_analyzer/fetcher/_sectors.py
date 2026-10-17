"""fetcher _sectors 子模块 —— 原样搬移自 __init__.py（2026-10-17 拆分，逻辑零改动）。"""

import functools
import json
import os
import random
import re
import time
from datetime import datetime, timedelta
from enum import Enum

import numpy as np
import pandas as pd
import requests

from ..config import HEADERS
from ..env import get_env
from ..logging_config import get_logger
from ..sectors_fallback import SECTOR_STOCKS_FALLBACK
from ._infra import _em_request
from ._quotes import get_market_overview, sina_real_time


def get_sectors():
    """获取行业板块列表"""
    data = _em_request(
        "/api/qt/clist/get",
        {
            "pn": 1,
            "pz": 200,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "m:90+t:2",
            "fields": "f2,f3,f4,f12,f14,f20,f104,f105,f128",
        },
        max_attempts=3,
        delay=1.0,
    )
    if data and data.get("data"):
        rows = []
        for item in data["data"].get("diff", []):
            rows.append(
                {
                    "板块代码": item.get("f12"),
                    "板块名称": item.get("f14"),
                    "涨跌幅": item.get("f3") or 0,
                    "上涨家数": item.get("f104") or 0,
                    "下跌家数": item.get("f105") or 0,
                    "总成交额": item.get("f20") or 0,
                }
            )
        df = pd.DataFrame(rows)
        return df[df["板块名称"].notna()].reset_index(drop=True)

    # 兜底：用静态板块列表（从Sina实时行情计算涨跌幅）
    return get_sectors_fallback()


def get_sectors_fallback():
    """兜底：静态板块映射 + 新浪实时行情"""
    rows = []
    for sec_name, info in SECTOR_STOCKS_FALLBACK.items():
        stocks = info["成分股"]
        rt = sina_real_time(stocks)
        changes = [rt[c]["涨跌幅"] for c in stocks if c in rt and rt[c]["涨跌幅"] is not None]
        if not changes:
            continue
        up = sum(1 for c in changes if c > 0)
        down = sum(1 for c in changes if c < 0)
        rows.append(
            {
                "板块代码": f"BK{abs(hash(sec_name)) % 10000:04d}",
                "板块名称": sec_name,
                "涨跌幅": round(float(np.mean(changes)), 2),
                "上涨家数": up,
                "下跌家数": down,
                "总成交额": sum(rt[c]["成交额"] for c in stocks if c in rt),
            }
        )
    if rows:
        df = pd.DataFrame(rows)
        return df.sort_values("涨跌幅", ascending=False).reset_index(drop=True)
    return pd.DataFrame()


def get_sector_stocks(sector_code):
    """获取板块成分股"""
    # 先试东方财富
    data = _em_request(
        "/api/qt/clist/get",
        {
            "pn": 1,
            "pz": 200,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": f"b:{sector_code}",
            "fields": "f2,f3,f12,f14,f20",
        },
        max_attempts=3,
        delay=1.0,
    )
    if data and data.get("data"):
        rows = []
        for item in data["data"].get("diff", []):
            name = item.get("f14", "")
            if "ST" in name or "退市" in name:
                continue
            rows.append({"代码": item.get("f12", ""), "名称": name, "涨跌幅": item.get("f3") or 0})
        if rows:
            return pd.DataFrame(rows)

    # 兜底：从静态映射找
    for sec_name_internal, info in SECTOR_STOCKS_FALLBACK.items():
        target = f"BK{abs(hash(sec_name_internal)) % 10000:04d}"
        if target == sector_code:
            stocks = info["成分股"]
            rt = sina_real_time(stocks)
            rows = []
            for c in stocks:
                if c in rt:
                    rows.append({"代码": c, "名称": rt[c]["名称"], "涨跌幅": rt[c]["涨跌幅"]})
            return pd.DataFrame(rows)

    return pd.DataFrame()


def get_top_sector_stocks(sectors_df, top_n=3):
    """从TOP板块中精选个股"""
    from ..analysis import score_stocks_in_sector

    top3 = sectors_df.head(top_n)
    all_picks = []

    for _, sec_row in top3.iterrows():
        sec_code = sec_row["板块代码"]
        sec_name = sec_row["板块名称"]
        stocks = get_sector_stocks(sec_code)
        if stocks.empty:
            print(f"  {sec_name}: 无成分股数据")
            continue

        # 用新浪实时行情补充量比、振幅
        codes = stocks["代码"].tolist()
        rt = sina_real_time(codes)
        if rt:
            rt_df = pd.DataFrame.from_dict(rt, orient="index")
            stocks = stocks.merge(
                rt_df[["代码", "最新价", "成交额", "今开", "昨收", "最高", "最低"]],
                on="代码",
                how="left",
            )
        else:
            stocks["最新价"] = 0
            stocks["最高"] = 0
            stocks["最低"] = 0
            stocks["昨收"] = 0
            stocks["成交额"] = 0

        stocks = stocks[stocks["涨跌幅"].notna()].copy()
        if stocks.empty:
            continue

        stocks["振幅"] = (
            (stocks["最高"] - stocks["最低"]) / stocks["昨收"].replace(0, np.nan) * 100
        ).fillna(0)
        mean_amount = stocks["成交额"].mean()
        stocks["量比"] = (stocks["成交额"] / (mean_amount + 1)).fillna(1)

        scored = score_stocks_in_sector(stocks)
        for _, stk in scored.head(2).iterrows():
            all_picks.append(
                {
                    "代码": stk["代码"],
                    "名称": stk["名称"],
                    "板块": sec_name,
                    "最新价": stk.get("最新价", None),
                    "涨跌幅": stk["涨跌幅"],
                    "量比": stk.get("量比", 1),
                    "振幅": stk.get("振幅", 0),
                    "个股评分": stk["个股评分"],
                }
            )
        time.sleep(0.3)

    if all_picks:
        df = pd.DataFrame(all_picks)
        return df.drop_duplicates(subset=["代码"])
    return pd.DataFrame()


def calc_relative_strength(code, index_code="000001", days=60):
    """计算个股相对大盘的强弱（RS线）

    相对强弱 = (个股累计涨幅 - 大盘累计涨幅)，正值=跑赢大盘。

    Returns:
        dict: {rs_value: float, stock_return: float, index_return: float,
               trend: '跑赢大盘'/'跑输大盘'/'持平'}
    """
    try:
        # 延迟导入避免循环依赖（cache 会 import fetcher）
        from ..cache import cached_kline as _ck

        stock_kline = _ck(code, days=days)
        if stock_kline.empty or len(stock_kline) < days * 0.8:
            return {"rs_value": 0, "stock_return": 0, "index_return": 0, "trend": "数据不足"}

        stock_ret = (stock_kline.iloc[-1]["收盘"] / stock_kline.iloc[0]["收盘"] - 1) * 100

        # 用指数K线计算真实区间回报（不再用单日涨跌×倍数估算）
        try:
            prefix = "sh" if index_code.startswith(("0", "6")) else "sz"
            idx_kline = (
                _ck(f"{prefix}{index_code}", days=days)
                if index_code != "000688"
                else _ck("sh000688", days=days)
            )
        except Exception:
            idx_kline = pd.DataFrame()
        if not idx_kline.empty and len(idx_kline) >= days * 0.8:
            idx_ret = (idx_kline.iloc[-1]["收盘"] / idx_kline.iloc[0]["收盘"] - 1) * 100
        else:
            # K线不可用时用当日涨跌幅兜底
            index_data = get_market_overview()
            idx_info = index_data.get(index_code, {})
            idx_ret = idx_info.get("涨跌幅", 0)

        rs = stock_ret - idx_ret
        if rs > 5:
            trend = "跑赢大盘"
        elif rs < -5:
            trend = "跑输大盘"
        else:
            trend = "持平"

        return {
            "rs_value": round(rs, 1),
            "stock_return": round(stock_ret, 1),
            "index_return": round(idx_ret, 1),
            "trend": trend,
        }
    except Exception:
        return {"rs_value": 0, "stock_return": 0, "index_return": 0, "trend": "计算失败"}


def get_sector_rotation(days=5):
    """分析板块轮动：对比近N天板块排名变化

    从历史评分库中提取板块均分变化，识别走强和走弱的板块。

    Returns:
        dict: {strengthening: [{name, score_change}],
               weakening: [{name, score_change}],
               top5_now: [{name, avg_score}]}
    """
    try:
        import pandas as pd

        from ..history_db import get_market_summary
        from .sectors_fallback import get_sector_for_code

        # 从全市场扫描结果中统计板块均分
        if not os.path.exists("full_scan_results.csv"):
            return {
                "strengthening": [],
                "weakening": [],
                "top5_now": [],
                "message": "暂无全市场扫描数据",
            }

        df = pd.read_csv("full_scan_results.csv")
        df["code_str"] = df["代码"].astype(str).str.zfill(6)
        df["sector"] = df["code_str"].apply(get_sector_for_code)

        sector_scores = df.groupby("sector")["综合评分"].agg(["mean", "count"]).reset_index()
        sector_scores = sector_scores[sector_scores["count"] >= 3]  # 至少3只股票
        sector_scores = sector_scores.sort_values("mean", ascending=False)

        top5 = [
            {"name": r["sector"], "avg_score": round(r["mean"], 1)}
            for _, r in sector_scores.head(5).iterrows()
        ]

        return {
            "strengthening": [],  # 需要多天数据对比，初次运行只有一天
            "weakening": [],
            "top5_now": top5,
            "total_sectors": len(sector_scores),
            "message": f"共{len(sector_scores)}个板块，均分最高: {top5[0]['name'] if top5 else '无'}",
        }
    except Exception as e:
        return {
            "strengthening": [],
            "weakening": [],
            "top5_now": [],
            "message": f"板块分析失败: {e}",
        }
