# ML-filtered stock scan with two-tier fallback
import json, urllib.request, subprocess, sys, time, os
from datetime import datetime

s_codes = []  # cache

def run(mode, top_n):
    result = _tier(mode, top_n, False)
    if len(result) >= top_n:
        return result
    print(1, f"Tier1: {len(result)} only")
    result2 = _tier(mode, top_n, True)
    for r in result2:
        if r[0] not in [x[0] for x in result]:
            r[2] = "Tier2"
            result.append(r)
    return result

def _tier(mode, top_n, relaxed):
    for line in open(".env"):
        if line.startswith("TUSHARE_TOKEN="):
            os.environ["TUSHARE_TOKEN"] = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
    from stock_analyzer.tushare_loader import get_tushare_pro
    from stock_analyzer.cache import cached_kline
    from stock_analyzer.analysis import full_technical_analysis
    from stock_analyzer.ml_predict import _cached_predict_ensemble
    pro = get_tushare_pro()
    pool = pro.stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name,market")
    if mode == "mainboard":
        pool = pool[pool["market"] == "主板"]
    cmap = dict(zip(pool["symbol"], pool["name"]))
    today = datetime.now().strftime("%Y%m%d")
    cal = pro.trade_cal(start_date="20260501", end_date=today)
    if cal is not None and len(cal) > 0:
        od = cal[(cal["is_open"] == 1) & (cal["cal_date"] <= today)]["cal_date"]
        latest = od.iloc[0] if len(od) > 0 else "20260605"
    else:
        latest = "20260605"
    db = pro.daily_basic(trade_date=latest)
    if db is None or len(db) == 0:
        return []
    db["code"] = db["ts_code"].str.split(".").str[0]
    dp = db[db["code"].isin(list(cmap.keys()))]
    if relaxed:
        cond = (dp["close"] >= 5) & (dp["close"] <= 100) & (dp["pe"] > 0) & (dp["pe"] <= 100) & (dp["pb"] > 0) & (dp["pb"] <= 15) & (dp["volume_ratio"] >= 0.5) & (dp["turnover_rate"] <= 35)
    else:
        cond = (dp["close"] >= 5) & (dp["close"] <= 80) & (dp["pe"] > 0) & (dp["pe"] <= 60) & (dp["pb"] > 0) & (dp["pb"] <= 8) & (dp["volume_ratio"] >= 0.7) & (dp["turnover_rate"] <= 25)
    fd = dp[cond].copy()
    if len(fd) == 0:
        return []
    fd["score"] = fd["pe"].rank(pct=True, ascending=False) * 0.25 + fd["turnover_rate"].rank(pct=True) * 0.40 + fd["volume_ratio"].rank(pct=True) * 0.35
    top = fd.sort_values("score", ascending=False).head(top_n * 3)
    result = []
    for _, row in top.iterrows():
        code = row["code"]
        try:
            k = full_technical_analysis(cached_kline(code, 120))
            if len(k) >= 60:
                pred = _cached_predict_ensemble(k, None)
                if pred.get("ensemble_direction") != "看涨":
                    continue
        except:
            pass
        tier = "Tier1" if not relaxed else "Tier2"
        result.append([code, cmap.get(code, ""), tier])
        if len(result) >= top_n:
            break
    return result
