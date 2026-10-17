"""CLI 共享核心 —— deep_analyze 与各命令共用件（2026-10-17 从 cli.py 拆出）

分层：cli.py(薄入口/build_parser/main) → cli_commands(命令实现) → cli_core(共享核心)
所有函数为原样搬移，逻辑零改动。
"""

import json
import os
import tempfile
import time

from stock_analyzer.logging_config import get_logger

logger = get_logger("cli")


_pd = None


_np = None


def _get_pd():
    global _pd
    if _pd is None:
        import pandas as _pd_mod

        _pd = _pd_mod
    return _pd


def _get_np():
    global _np
    if _np is None:
        import numpy as _np_mod

        _np = _np_mod
    return _np


def _scan_writable_dir():
    """扫描产物(断点/结果JSON)写入目录。

    容器以 `.:/app:ro` 只读挂载项目目录，/app 不可写；断点文件与结果JSON
    原写 cwd(/app) 会触发 OSError 致扫描崩溃(2026-08-25 复盘定位根因)。
    优先选项目自身 logs 目录(宿主侧/容器内均可写)，回退 /app/logs 与系统临时目录。
    """
    _proj_logs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    for cand in (_proj_logs, "/app/logs", tempfile.gettempdir()):
        try:
            os.makedirs(cand, exist_ok=True)
            probe = os.path.join(cand, f".wprobe_{os.getpid()}")
            with open(probe, "w") as _f:
                _f.write("ok")
            os.remove(probe)
            return cand
        except OSError:
            continue
    return tempfile.gettempdir()


def _cleanup_old_logs(days: int | None = None) -> list[str]:
    """清理 logs/ 下超过保留期的扫描产物与错误日志（2026-10-13 新增）。

    背景：`scan_<mode>_<ts>.json` 每次扫描写一个（实测 ~2.4MB/个）、
    `error_<date>.log` 每日一个，两者均无保留策略 —— 曾积压 128MB+。
    保留期默认 14 天（与 backend/logging_config.py 的 LOG_BACKUP 对齐），
    可用环境变量 SCAN_LOG_KEEP_DAYS 覆盖；只删保留期外的旧文件，
    当次产物（刚写入）绝不在删除范围。删除失败不抛出（由调用方兜底）。
    """
    if days is None:
        try:
            days = int(os.environ.get("SCAN_LOG_KEEP_DAYS", "14"))
        except ValueError:
            days = 14
    if days <= 0:
        return []
    cutoff = time.time() - days * 86400
    removed: list[str] = []
    try:
        names = os.listdir(_SCAN_DIR)
    except OSError:
        return []
    for name in names:
        is_scan = name.startswith("scan_") and name.endswith(".json")
        is_err = name.startswith("error_") and name.endswith(".log")
        if not (is_scan or is_err):
            continue
        path = os.path.join(_SCAN_DIR, name)
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed.append(name)
        except OSError:
            continue
    return removed


def _save_checkpoint_single(code):
    """追加一只股票到 checkpoint（立即刷盘，崩溃最多丢 1 只）。
    写入失败(如只读挂载)仅告警不中断扫描(2026-08-25 兜底)。"""
    try:
        with open(_CHECKPOINT_FILE, "a") as f:
            f.write(code + "\n")
            f.flush()
            os.fsync(f.fileno())
    except OSError as e:
        print(f"  ⚠️ 断点写入失败(已忽略): {e}")


def _load_checkpoint():
    """读取已完成股票集合"""
    if os.path.exists(_CHECKPOINT_FILE):
        with open(_CHECKPOINT_FILE) as f:
            return {line.strip() for line in f if line.strip()}
    return set()


def _clear_checkpoint():
    """扫描完成，清除断点文件"""
    if os.path.exists(_CHECKPOINT_FILE):
        os.remove(_CHECKPOINT_FILE)


def _json_default(o):
    """JSON 序列化兜底：扫描结果偶发含 DataFrame/Series/numpy 类型(2026-08-25 复盘定位)。"""
    name = type(o).__name__
    if name == "DataFrame":
        try:
            return o.to_dict(orient="records")
        except Exception:
            return str(o)
    if name == "Series":
        try:
            return o.to_dict()
        except Exception:
            return str(o)
    if "ndarray" in name:
        try:
            return o.tolist()
        except Exception:
            return list(o)
    if "int" in name or "float" in name:  # numpy scalar (int64/float64 等)
        try:
            return o.item()
        except Exception:
            return str(o)
    if name in ("Timestamp", "datetime"):
        return str(o)
    return str(o)


def _fail_on_skip_ratio(skipped: int, total: int) -> bool:
    """失败率护栏（2026-10-17）：≥阈值比例的标的未完成分析 → 判失败。

    口径说明（详见 cmd_scan 内注释与 代码审查修复报告_20261017.md §8.2/§10）：
      · 不用「达标数=0」判失败 —— 那可能是合法行情（大跌日），会误告警；
      · 用「未完成比例」—— ≥90% 连分析都没完成只可能是系统性故障。
    配置：环境变量 SCAN_FAIL_RATIO，默认 0.9；设为 >1 显式禁用（回到旧恒 0 行为）。
    """
    try:
        threshold = float(os.environ.get("SCAN_FAIL_RATIO", "0.9"))
    except ValueError:
        threshold = 0.9
    if threshold > 1:  # 显式禁用开关
        return False
    return bool(total) and skipped >= total * threshold


def load_owned_stocks():
    """从 mainboard_owned 文件加载当前持仓（自动选最新）"""
    import glob

    files = sorted(glob.glob("mainboard_owned_*.json"), reverse=True)
    if not files:
        return {}
    with open(files[0], encoding="utf-8") as f:
        return json.load(f)


def deep_analyze(code, days=365, skip_nt=False):
    """个股深度分析（单次调用，返回完整dict）"""
    pd = _get_pd()
    np = _get_np()
    from stock_analyzer.analysis import (
        calc_stop_levels,
        calc_support_resistance,
        full_technical_analysis,
        get_technical_summary,
        score_fundamental,
    )
    from stock_analyzer.cache import cached_fundamentals, cached_kline
    from stock_analyzer.quant import (
        calc_risk_metrics,
        composite_quant_score,
        consolidate_signals,
        evaluate_trading_style,
        generate_all_signals,
    )

    kline = cached_kline(code, days=days)
    if len(kline) < 20:
        return None

    # 合并今日实时数据到K线（修复：之前只用昨日缓存，指标滞后1天）
    from stock_analyzer.fetcher import sina_real_time

    try:
        rt = sina_real_time([code])
        if rt and code in rt:
            r = rt[code]
            today_open = float(r.get("open", 0) or 0)
            today_high = float(r.get("high", 0) or 0)
            today_low = float(r.get("low", 0) or 0)
            today_price = float(r.get("price", 0) or 0)
            today_vol = float(r.get("volume", 0) or 0)
            if today_open > 0 and today_price > 0:
                last_date = str(kline["日期"].iloc[-1])[:10]
                today_str = pd.Timestamp.now().strftime("%Y-%m-%d")
                if today_str > last_date:
                    new_row = pd.DataFrame(
                        [
                            {
                                "日期": pd.Timestamp(today_str),
                                "开盘": today_open,
                                "最高": today_high,
                                "最低": today_low,
                                "收盘": today_price,
                                "成交量": int(today_vol),
                                "成交额": 0,
                            }
                        ]
                    )
                    kline = pd.concat([kline, new_row], ignore_index=True)
    except Exception as e:
        logger.warning("deep_analyze 失败 (%s: %s)", type(e).__name__, e)

    kline = full_technical_analysis(kline)
    tech = get_technical_summary(kline)
    sr = calc_support_resistance(kline)

    price = float(kline.iloc[-1]["收盘"])
    atr = float(kline.iloc[-1].get("ATR", np.nan))
    if pd.isna(atr) or atr <= 0:
        atr = price * 0.03

    if not isinstance(sr, dict):
        sr = {"支撑位": [price * 0.9], "压力位": [price * 1.1]}
    sl = sr.get("支撑位", [price * 0.9])
    rl = sr.get("压力位", [price * 1.1])
    stop = calc_stop_levels(price, atr, float(sl[0]), float(rl[0]))

    risk = calc_risk_metrics(kline)
    sigs = consolidate_signals(generate_all_signals(kline))
    funds = cached_fundamentals(code)
    fsv, _ = score_fundamental(funds) if funds else (0, {})
    quant = composite_quant_score(kline, funds, sentiment_score=None)
    trading = evaluate_trading_style(kline, funds, risk)

    n5 = float((kline.iloc[-1]["收盘"] / kline.iloc[-6]["收盘"] - 1) * 100) if len(kline) > 5 else 0
    n20 = (
        float((kline.iloc[-1]["收盘"] / kline.iloc[-21]["收盘"] - 1) * 100)
        if len(kline) > 20
        else 0
    )

    rsi = tech.get("rsi_value", 50) if isinstance(tech, dict) else 50
    macd_sig = tech.get("macd_signal", "") if isinstance(tech, dict) else ""
    kdj_sig = tech.get("kdj_signal", "") if isinstance(tech, dict) else ""

    qs = quant if isinstance(quant, dict) else {}
    fs = qs.get("factor_scores", {})

    def gf(k):
        v = fs.get(k, {})
        return float(v.get("score", 0)) if isinstance(v, dict) else 0

    risk_d = risk if isinstance(risk, dict) else {}
    sigs_d = sigs if isinstance(sigs, dict) else {}
    ts_d = trading if isinstance(trading, dict) else {}
    stop_d = stop if isinstance(stop, dict) else {}

    has_nt = False
    nt_holders = []
    if not skip_nt:
        try:
            from stock_analyzer.cache import cached_national_team_holdings

            nt = cached_national_team_holdings(code)
            if nt and isinstance(nt, dict):
                has_nt = nt.get("has_national_team", False)
                nt_holders = nt.get("holders", [])
        except Exception as e:
            logger.warning("deep_analyze 失败 (%s: %s)", type(e).__name__, e)

    return {
        "code": code,
        "price": price,
        "atr": atr,
        "near_5d": round(n5, 2),
        "near_20d": round(n20, 2),
        "rsi": round(rsi, 1),
        "macd_signal": macd_sig,
        "kdj_signal": kdj_sig,
        "fund_score": round(fsv, 1),
        "roe": round(funds.get("ROE", 0), 2) if funds else 0,
        "sharpe": round(risk_d.get("sharpe_ratio", 0), 3),
        "max_dd": round(risk_d.get("max_drawdown_pct", 0), 2),
        "var95": round(risk_d.get("VaR_95_pct", 0), 2),
        "volatility": round(risk_d.get("annualized_volatility_pct", 0), 2),
        "signal_bias": sigs_d.get("bias", "neutral"),
        "signal_score": sigs_d.get("score", 0),
        "short_score": round(ts_d.get("short_term_score", 0), 1),
        "long_score": round(ts_d.get("long_term_score", 0), 1),
        "style": ts_d.get("style", ""),
        "confidence": ts_d.get("style_confidence", ""),
        "short_basis": ts_d.get("short_term_basis", ""),
        "long_basis": ts_d.get("long_term_basis", ""),
        "qs_composite": round(float(qs.get("composite_score", 0)), 1),
        "qs_rating": str(qs.get("rating", "")),
        "mom_s": round(gf("momentum"), 1),
        "tech_s": round(gf("technical"), 1),
        "fund_s": round(gf("fundamental"), 1),
        "vol_s": round(gf("volume"), 1),
        "risk_s": round(gf("risk"), 1),
        "has_nt": has_nt,
        "nt_holders": nt_holders,
        "support": [round(float(x), 2) for x in sl[:2]],
        "resistance": [round(float(x), 2) for x in rl[:2]],
        "stop_loss": round(stop_d.get("止损参考价", 0), 2),
        "stop_profit": round(stop_d.get("止盈参考价", 0), 2),
        "_kline": kline,
        # 完整对象（供HTML报告等需要详细数据的场景使用）
        "fundamentals": funds,
        "quant_score": quant,
        "technical_summary": tech,
        "support_resistance": sr,
        "stop_levels": stop,
        "risk_metrics": risk,
        "signals": sigs,
        "trading_style": trading,
    }


def _print_full_analysis(code, days=365, fast=False):
    """一键全出：七层分析。复用 deep_analyze() 计算核心指标。
    fast=True 时仅 L0-L3（纯本地计算+跳过国家队查询），适合盘中快速决策。"""
    # 先跑核心分析（复用，fast模式跳过国家队API）
    r = deep_analyze(code, days=days, skip_nt=fast)
    if r is None:
        print(f"  {code}: K线数据不足")
        return

    kline = r["_kline"]
    price = r["price"]
    funds = r["fundamentals"]

    # ── 输出 ──
    W = 60

    def sep(title):
        print(f"\n{'─' * W}")
        print(f"  {title}")
        print(f"{'─' * W}")

    print(f"\n{'=' * W}")
    print(f"  {code} 全维度分析")
    print(f"{'=' * W}")

    # 板块归属(行业 + 概念)
    from stock_analyzer.sector_info import get_stock_all_sectors

    si = get_stock_all_sectors(code)
    print(f"  行业: {si['industry']}")
    if si["concepts"]:
        print(f"  概念: {', '.join(si['concepts'][:5])}")

    # L0r: 实时行情（fast/full 都拉新浪实时，0.06s）
    from stock_analyzer.fetcher import sina_real_time

    rt = sina_real_time([code])
    realtime_note = ""
    if code in rt:
        rtp = rt[code]
        rt_price = rtp.get("最新价", 0)
        rt_chg = rtp.get("涨跌幅", 0)
        rt_high = rtp.get("最高", 0)
        rt_low = rtp.get("最低", 0)
        rt_open = rtp.get("今开", 0)
        if rt_price and float(rt_price) != price:
            realtime_note = f" ⚠️缓存价{price:.2f}≠实时价{float(rt_price):.2f}"
            price = float(rt_price)
        tag = "(实时)" if fast else ""
        print(
            f"\n  实时行情: {rt_price} ({rt_chg}%) 今开{rt_open} 最高{rt_high} 最低{rt_low}{realtime_note} {tag}"
        )

    # L0: 短线专项
    sep("L0 短线专项")
    try:
        from stock_analyzer.short_term import (
            calc_combo_signals,
            calc_consecutive_days,
            calc_fund_flow_summary,
            calc_multi_timeframe_resonance,
            calc_news_catalyst,
            calc_tail_tendency,
            calc_turnover_signal,
            short_term_score,
        )

        turnover = calc_turnover_signal(kline)
        consec = calc_consecutive_days(kline)
        tail = calc_tail_tendency(kline)
        st_score = short_term_score(kline, code)
        combo = calc_combo_signals(kline, code)
        if not fast:
            mr = calc_multi_timeframe_resonance(code)

        print(
            f"  换手率: {turnover.get('换手率%', 0):.1f}% | 量比: {turnover.get('量比', 1):.1f} | {turnover.get('信号', '')}"
        )
        print(
            f"  连{consec.get('方向', '')}{consec.get('天数', 0)}天 | {consec.get('信号', '')} | 节奏: {tail.get('近5日涨跌节奏', '')}"
        )
        print(
            f"  尾盘: {tail.get('尾盘倾向', '')} | 近10日阳线: {tail.get('近10日阳线占比%', 50):.0f}%"
        )
        print(
            f"  短线评分: {st_score.get('短线评分', 0):.0f} → {st_score.get('评级', '')} | ATR占比: {st_score.get('ATR占比%', 0):.1f}%"
        )
        # 组合信号
        print(
            f"  组合信号: {combo.get('信号', '')} (强度{combo.get('强度', 0):+d}) | {' '.join(combo.get('详情', [])[:4])}"
        )
        if not fast:
            print(f"  多周期共振: {mr.get('状态', '')} ({mr.get('共振强度', 0):+d})")
        if st_score.get("风险"):
            print(f"  风险: {' | '.join(st_score['风险'])}")

        ff = (
            calc_fund_flow_summary(code)
            if not fast
            else {"主力动向": "快速模式跳过", "近5日累计(万)": 0, "今日方向": ""}
        )
        print(
            f"  主力: {ff.get('主力动向', '')} | 近5日: {ff.get('近5日累计(万)', 0)}万 | 今日: {ff.get('今日方向', '')}"
        )

        news = calc_news_catalyst(code) if not fast else {"消息催化": "快速模式跳过"}
        print(f"  消息: {news.get('消息催化', '')}")
    except Exception:
        print("  短线数据获取失败")

    # L1: 技术面（复用 deep_analyze 结果）
    np = _get_np()
    n5 = r["near_5d"]
    n20 = r["near_20d"]
    n60 = (
        float((kline.iloc[-1]["收盘"] / kline.iloc[-61]["收盘"] - 1) * 100)
        if len(kline) > 60
        else 0
    )
    sep("L1 技术面")
    print(
        f"  现价: {price:.2f}  |  近5日: {n5:+.1f}%  |  近20日: {n20:+.1f}%  |  近60日: {n60:+.1f}%"
    )
    print(f"  MACD: {r['macd_signal']}  |  RSI: {r['rsi']:.0f}  |  KDJ: {r['kdj_signal']}")
    print(f"  支撑: {r['support']}  压力: {r['resistance']}")
    print(f"  止损: {r['stop_loss']:.2f}  |  止盈: {r['stop_profit']:.2f}  |  ATR: {r['atr']:.2f}")

    # L2: 量化评分（复用）
    sep("L2 量化评分")
    print(
        f"  综合: {r['qs_composite']:.0f} → {r['qs_rating']}  |  短线: {r['short_score']:.0f}分  |  长线: {r['long_score']:.0f}分  |  风格: {r['style']}"
    )
    print(f"  动量: {r['mom_s']:.0f}  技术: {r['tech_s']:.0f}  基本面: {r['fund_s']:.0f}")
    print(f"  量能: {r['vol_s']:.0f}  风险: {r['risk_s']:.0f}")
    print(
        f"  夏普: {r['sharpe']:.2f}  |  回撤: {r['max_dd']:.1f}%  |  波动率: {r['volatility']:.1f}%"
    )

    # L3: 基本面（复用）
    sep("L3 基本面 & 国家队")
    print(f"  ROE: {r['roe']:.2f}%  |  基本面评分: {r['fund_score']:.0f}")
    if r["has_nt"]:
        holders = r["nt_holders"]
        print(
            f"  国家队: 🏛️ {', '.join(holders[:5])}{'...' if len(holders) > 5 else ''} ({len(holders)}家)"
        )

    # ── NL: 多空辩论自然语言报告 ──
    sep("NL 多空辩论")
    try:
        from stock_analyzer.nl_report import generate_bull_bear_debate

        debate_data = {
            "quant_score": r.get("qs_composite", 50),
            "technical": {
                "macd_signal": r.get("macd_signal", ""),
                "kdj_signal": r.get("kdj_signal", ""),
                "rsi": r.get("rsi", 50),
                "near5d": r.get("near_5d", 0),
                "near20d": r.get("near_20d", 0),
                "ma_status": "",
                "resistance": [],
                "price": r.get("price", 0),
                "pe": r.get("pe", 0),
            },
            "fund_flow": {"direction": r.get("fund_flow_direction", "")},
            "ai_prediction": {
                "direction": "看涨" if r.get("ml_up_prob", 50) > 50 else "看跌",
                "confidence": r.get("ml_up_prob", 50),
            },
        }
        debate = generate_bull_bear_debate(debate_data)

        print(f"  🐂 多头({debate['bull']['score']}分): {'; '.join(debate['bull']['points'][:3])}")
        print(f"  🐻 空头({debate['bear']['score']}分): {'; '.join(debate['bear']['points'][:3])}")
        print(
            f"  📊 结论: {debate['verdict']} → {debate['action']} (置信度:{debate['confidence']})"
        )
    except Exception as e:
        print(f"  (多空辩论: {e})")

    # L4-L7: 仅全量模式（需网络API，盘中--fast跳过）
    if fast:
        print("\n  ⚡ 快速模式(L0-L3)，耗时 <1s")
        print(f"{'=' * W}")
        return

    # L4: 资金面 & 消息
    sep("L4 资金面 & 消息")
    try:
        from stock_analyzer.advanced import (
            get_institution_visits,
            get_margin_summary,
            insider_signal,
            north_flow_signal,
        )

        sig = insider_signal(code)
        print(f"  高管增减持: {sig.get('signal', '无数据')} ({sig.get('records', 0)}笔)")
        visits = get_institution_visits(code, days=60)
        print(f"  机构调研: {len(visits)}次(近60日)")
        nf = north_flow_signal()
        if "error" not in nf:
            print(
                f"  北向资金: {'净流入' if any(v.get('净买额(亿)', 0) > 0 for v in nf.values()) else '净流出'}"
            )
        mg = get_margin_summary()
        if mg:
            total_mg = sum(v.get("融资余额(亿)", 0) for v in mg.values())
            print(f"  两市融资余额: {total_mg:.0f}亿")
    except Exception as e:
        logger.debug("_print_full_analysis 失败 (%s: %s)", type(e).__name__, e)

    # L5: 策略回测（复用 kline）
    sep("L5 策略回测")
    try:
        from stock_analyzer.backtest import DEFAULT_COMPARE_STRATEGIES, compare_strategies

        bt = compare_strategies(kline, DEFAULT_COMPARE_STRATEGIES, 100000, verbose=False)
        if bt:
            bench = (float(kline["收盘"].iloc[-1]) / float(kline["收盘"].iloc[0]) - 1) * 100
            best = max(bt.items(), key=lambda x: x[1]["metrics"]["夏普比率"])
            print(f"  基准(买入持有): {bench:.1f}%")
            print(
                f"  最优策略: {bt[best[0]]['name']} (夏普{best[1]['metrics']['夏普比率']:.2f} 超额{best[1]['metrics']['超额收益%']:+.1f}%)"
            )
            for s, res in list(bt.items())[:5]:
                m = res["metrics"]
                bar = "█" * int(max(m["总收益率%"], 0) / 15)
                print(
                    f"  {res['name']:<12} {bar} {m['总收益率%']:.0f}%(超额{m['超额收益%']:+.0f}%)  夏普{m['夏普比率']:.2f}  回撤{m['最大回撤%']:.0f}%"
                )
    except Exception:
        print("  回测数据不足")

    # L6: AI预测 (三模型集成: XGBoost + RandomForest + LightGBM)
    sep("L6 AI预测(三模型集成)")
    try:
        from stock_analyzer.ml_predict import predict_ensemble

        result = predict_ensemble(kline, funds)
        agreement = result.get("agreement", "未知")
        direction = result.get("ensemble_direction", "未知")
        confidence = result.get("ensemble_confidence", 0)
        votes = result.get("votes", "")
        models = result.get("models", {})

        if agreement == "数据不足":
            print("  数据不足，无法预测")
        elif agreement == "高":
            emoji = "📈" if direction == "看涨" else "📉"
            print(
                f"  {emoji} 三模型一致{direction}  |  置信度{confidence:.0f}%  |  一致性:{agreement} ({votes})"
            )
        elif agreement == "中":
            print(
                f"  ⚠️ 模型有分歧  |  投票: {direction}  |  置信度{confidence:.0f}%  |  一致性:中 ({votes})"
            )
        else:
            print(
                f"  模型预测方向: {direction}  |  置信度{confidence:.0f}%  |  一致性:低 ({votes})"
            )

        # 展示各模型细节
        for name, label in [("xgb", "XGBoost"), ("rf", "RandomForest"), ("lgb", "LightGBM")]:
            m = models.get(name, {})
            if "error" not in m and m.get("预测方向"):
                print(
                    f"  {label}: {m.get('预测方向', '')} 上涨{m.get('上涨概率', 0)}%  |  准确率{m.get('准确率%', 0)}%  |  AUC:{m.get('AUC', 0):.3f}"
                )
                if m.get("重要特征"):
                    tops = [f"{f['特征']}({f['重要性']:.3f})" for f in m["重要特征"][:3]]
                    print(f"    关键因子: {', '.join(tops)}")
    except ImportError:
        print("  ML预测暂不可用 (pip install scikit-learn xgboost lightgbm)")
    except Exception as e:
        print(f"  ML预测失败: {e}")

    # L7: 宏观
    sep("L7 宏观环境")
    try:
        from stock_analyzer.advanced import macro_market_signal

        macro = macro_market_signal()
        if "error" not in macro:
            ind = macro.get("数据", {})
            print(f"  PMI: {ind.get('制造业PMI', 'N/A')}  |  M2: {ind.get('M2同比%', 'N/A')}%")
            print(f"  信号: {' | '.join(macro.get('信号', []))}")
            print(f"  整体: {macro.get('整体', 'N/A')}")
    except Exception as e:
        logger.debug("_print_full_analysis 失败 (%s: %s)", type(e).__name__, e)

    print(f"\n{'=' * W}")


def _print_stock_analysis(r):
    """打印单只股票分析结果"""
    pnl_str = f" 浮盈: {r.get('pnl', 0):+.2f}%" if "pnl" in r else ""
    print(f"  💰 价格: {r['price']:.2f}{pnl_str}")
    print(f"  📊 综合评分: {r['qs_composite']:.0f} ({r['qs_rating']})")
    print(f"  📈 近5日: {r['near_5d']:+.1f}% | 近20日: {r['near_20d']:+.1f}% | RSI: {r['rsi']:.0f}")
    print(f"  📉 MACD: {r['macd_signal']} | KDJ: {r['kdj_signal']}")
    print(
        f"  🎯 因子: 动量{r['mom_s']:.0f} 技术{r['tech_s']:.0f} 基本面{r['fund_s']:.0f} "
        f"量能{r['vol_s']:.0f} 风险{r['risk_s']:.0f}"
    )
    print(f"  ⚡ 夏普: {r['sharpe']:.2f} | 回撤: {r['max_dd']:.1f}%")
    print(f"  🛡️ 止损: {r['stop_loss']:.2f} | 止盈: {r['stop_profit']:.2f}")
    nt = f"🏛️ {', '.join(r['nt_holders'][:2])}" if r["has_nt"] else "无"
    print(f"  🏛️ 国家队: {nt}")
    print(f"  🏷️ 风格: {r['style']} | 短线{r['short_score']:.0f}分 | 长线{r['long_score']:.0f}分")


_SCAN_DIR = _scan_writable_dir()


_CHECKPOINT_FILE = os.path.join(_SCAN_DIR, ".scan_progress")
