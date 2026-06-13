"""终极分析 — 大盘→板块→七层全出→预测→操作建议

用法: python cli.py analyze <code> --ultimate
结合 --full 的七层细节 + 板块/资金/预测框架
"""

from datetime import datetime


def ultimate_analysis(code: str):
    W = 60

    # ═══════════════════════════════════
    # 一、大盘环境
    # ═══════════════════════════════════
    print(f"\n{'=' * W}")
    print(f"  StockInsight 终极分析 — {code}")
    print(f"  数据时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'=' * W}")

    print(f"\n{'─' * W}")
    print("  一、大盘环境")
    print(f"{'─' * W}")
    try:
        from stock_analyzer.fetcher import get_market_overview

        market = get_market_overview()
        for ci, cn in [
            ("000001", "上证指数"),
            ("399001", "深证成指"),
            ("399006", "创业板指"),
            ("000688", "科创50"),
        ]:
            info = market.get(ci, {})
            if info:
                p = float(info.get("最新价", 0) or 0)
                c = float(info.get("涨跌幅", 0) or 0)
                print(f"  {cn}: {p:.2f} ({c:+.2f}%)")
    except Exception:
        print("  大盘数据获取失败")

    # ═══════════════════════════════════
    # 二、板块分析
    # ═══════════════════════════════════
    print(f"\n{'─' * W}")
    print("  二、板块分析")
    print(f"{'─' * W}")

    sector_full = "未知"
    sector_rank = 0
    sector_score = 0
    sector_flow = 0
    ranked = []
    try:
        from .sector_info import get_stock_sector_full

        sector_full = get_stock_sector_full(code)
        sname = sector_full.split(" > ")[-1] if " > " in sector_full else sector_full

        from .fetcher import get_sectors

        sectors = get_sectors()
        if isinstance(sectors, dict) and sectors:
            ranked = sorted(
                sectors.items(), key=lambda x: float(x[1].get("涨跌幅", 0) or 0), reverse=True
            )
            print("  板块排名 TOP5:")
            for i, (nm, info) in enumerate(ranked[:5]):
                chg = float(info.get("涨跌幅", 0) or 0)
                ff = float(info.get("资金净流入", 0) or 0) / 1e8
                mk = " 👑" if i == 0 else ""
                print(f"    {i + 1}. {nm}: {chg:+.2f}%  资金{ff:+.1f}亿{mk}")
                if nm == sname or sname in nm or nm in sname:
                    sector_rank = i + 1
                    sector_score = round(chg, 2)
                    sector_flow = round(ff, 1)

        total = len(ranked) if ranked else 20
        rpct = (total - sector_rank) / total * 100 if sector_rank else 50
        label = "强势前排 ✅" if rpct > 66 else ("中游 ⚠️" if rpct > 33 else "弱势后排 🔴")
        print(f"\n  📌 {code} 所属: {sector_full}")
        if sector_rank:
            print(
                f"     排名: #{sector_rank}/{total} ({label})  涨跌:{sector_score:+.2f}%  资金:{sector_flow:+.1f}亿"
            )
        else:
            print(f"     排名: 东方财富数据不可用 ({label})")
        if rpct < 35:
            print("     🔴 板块弱势！个股逆势上涨难度大，建议降仓或观望")
    except Exception as e:
        print(f"  板块分析异常: {e}")

    # ═══════════════════════════════════
    # 三、七层深度分析 (复用 --full)
    # ═══════════════════════════════════
    print(f"\n{'─' * W}")
    print("  三、个股七层深度分析")
    print(f"{'─' * W}")

    # 加载数据用于后续预测
    from stock_analyzer.analysis import full_technical_analysis, get_technical_summary
    from stock_analyzer.cache import cached_fund_flow, cached_fundamentals, cached_kline
    from stock_analyzer.fetcher import sina_real_time
    from stock_analyzer.short_term import (
        calc_combo_signals,
        calc_multi_timeframe_resonance,
        short_term_score,
    )

    kline = cached_kline(code, days=365)
    if kline is None or kline.empty or len(kline) < 20:
        print(f"  {code}: K线数据不足")
        return
    funds = cached_fundamentals(code)
    kline = full_technical_analysis(kline)
    tech = get_technical_summary(kline)
    rt = sina_real_time([code])
    info = rt.get(code, {})
    price = float(info.get("最新价", 0) or kline["收盘"].iloc[-1])
    atr = float(kline.iloc[-1].get("ATR", price * 0.03))
    name = info.get("名称", code)

    # ── L0 短线专项 ──
    st = short_term_score(kline, code)
    combo = calc_combo_signals(kline)
    mr = calc_multi_timeframe_resonance(code)
    from .short_term import calc_consecutive_days, calc_tail_tendency, calc_turnover_signal

    to = calc_turnover_signal(kline)
    cd = calc_consecutive_days(kline)
    tl = calc_tail_tendency(kline)
    print("\n  ═══ L0 短线专项 ═══")
    turnover = to.get("换手率%", 0) or 0
    vol_ratio = to.get("量比", 0) or 0
    vol_sig = "放量" if vol_ratio > 1.5 else ("缩量" if vol_ratio < 0.7 else "正常")
    print(f"  换手率: {turnover:.1f}% | 量比: {vol_ratio:.1f} | {vol_sig}")
    cd_desc = cd.get("描述", "") if isinstance(cd, dict) else ""
    tl_rhythm = tl.get("节奏", "") if isinstance(tl, dict) else ""
    print(f"  {cd_desc} | 节奏: {tl_rhythm}")
    print(
        f"  短线评分: {st.get('短线评分', 0)} → {st.get('评级', '')} | ATR占比: {st.get('ATR占比%', 0):.1f}%"
    )
    print(
        f"  组合信号: {combo.get('信号', '')} (强度{combo.get('强度', 0)}) | {combo.get('详情', '')}"
    )
    print(f"  多周期共振: {mr.get('状态', '')} ({mr.get('共振强度', 0)})")
    if st.get("风险", []):
        print(f"  风险: {', '.join(st.get('风险', []))}")

    # 主力资金
    total_flow = 0
    flow_ok = False
    try:
        ff = cached_fund_flow(code, days=5)
        if ff is not None and not ff.empty and "主力净流入-净额" in ff.columns:
            total_flow = round(ff["主力净流入-净额"].sum() / 1e8, 2)
            flow_ok = True
    except Exception:
        pass
    print(
        f"  主力: {'近5日' + f'{total_flow:+.2f}亿' if flow_ok else '无数据'} | 今日: {'流入' if total_flow > 0 else '流出' if total_flow < 0 else '无数据'}"
    )

    # ── L1 技术面 ──
    from .analysis import calc_stop_levels, calc_support_resistance

    sr = calc_support_resistance(kline)
    sl = sr.get("支撑位", [price * 0.9])
    rl = sr.get("压力位", [price * 1.1])
    n5 = (
        round(float((kline["收盘"].iloc[-1] / kline["收盘"].iloc[-6] - 1) * 100), 2)
        if len(kline) > 5
        else 0
    )
    n20 = (
        round(float((kline["收盘"].iloc[-1] / kline["收盘"].iloc[-21] - 1) * 100), 2)
        if len(kline) > 20
        else 0
    )
    n60 = (
        round(float((kline["收盘"].iloc[-1] / kline["收盘"].iloc[-61] - 1) * 100), 2)
        if len(kline) > 60
        else 0
    )
    print("\n  ═══ L1 技术面 ═══")
    print(f"  现价: {price:.2f} | 近5日: {n5:+.1f}% | 近20日: {n20:+.1f}% | 近60日: {n60:+.1f}%")
    print(
        f"  MACD: {tech.get('macd_signal', '')} | RSI: {tech.get('rsi_value', 50):.0f} | KDJ: {tech.get('kdj_signal', '')}"
    )
    print(
        f"  支撑: {[round(float(x), 2) for x in sl[:2]]}  压力: {[round(float(x), 2) for x in rl[:2]]}"
    )
    stop = calc_stop_levels(price, atr, float(sl[0]), float(rl[0]))
    print(
        f"  止损: {stop.get('止损参考价', price * 0.93):.2f} | 止盈: {stop.get('止盈参考价', price * 1.07):.2f} | ATR: {atr:.2f}"
    )

    # ── L2 量化评分 ──
    from .quant import calc_risk_metrics, composite_quant_score, evaluate_trading_style

    quant = composite_quant_score(kline, funds)
    risk = calc_risk_metrics(kline)
    trading = evaluate_trading_style(kline, funds, risk)
    qs = quant.get("composite_score", 50) if isinstance(quant, dict) else 50
    qr = quant.get("rating", "") if isinstance(quant, dict) else ""
    fs = quant.get("factor_scores", {}) if isinstance(quant, dict) else {}

    def gf(k):
        v = fs.get(k, {})
        return round(float(v.get("score", 0)), 1) if isinstance(v, dict) else 0

    print("\n  ═══ L2 量化评分 ═══")
    print(
        f"  综合: {qs} → {qr} | 短线: {trading.get('short_term_score', 50)}分 | 长线: {trading.get('long_term_score', 50)}分 | 风格: {trading.get('style', '')}"
    )
    print(
        f"  动量: {gf('momentum')}  技术: {gf('technical')}  基本面: {gf('fundamental')}  量能: {gf('volume')}  风险: {gf('risk')}"
    )
    print(
        f"  夏普: {risk.get('sharpe_ratio', 0):.2f} | 回撤: {risk.get('max_drawdown_pct', 0):.1f}% | 波动率: {risk.get('annualized_volatility_pct', 0):.1f}%"
    )

    # ── L3 基本面 & 国家队 ──
    from .cache import cached_national_team_holdings

    roe = funds.get("ROE", 0) if isinstance(funds, dict) else 0
    nt_holders = []
    try:
        nt = cached_national_team_holdings(code)
        if isinstance(nt, dict):
            nt_holders = nt.get("holders", [])
    except:
        pass
    print("\n  ═══ L3 基本面 & 国家队 ═══")
    print(f"  ROE: {roe:.2f}% | 基本面评分: {gf('fundamental'):.0f}")
    if nt_holders:
        print(
            f"  国家队: {'🏛️ ' + ', '.join(nt_holders[:5])}{'...' if len(nt_holders) > 5 else ''} ({len(nt_holders)}家)"
        )
    else:
        print("  国家队: 无")

    # ── NL 多空辩论 ──
    from .nl_report import generate_bull_bear_debate

    try:
        from .ml_predict import predict_ensemble

        ai = predict_ensemble(kline, funds)
    except:
        ai = {"ensemble_direction": "?", "ensemble_confidence": 50}
    debate = generate_bull_bear_debate(
        {
            "quant_score": qs,
            "technical": {
                "macd_signal": tech.get("macd_signal", ""),
                "kdj_signal": tech.get("kdj_signal", ""),
                "rsi": tech.get("rsi_value", 50),
                "near5d": n5,
                "near20d": n20,
                "ma_status": tech.get("均线", ""),
                "resistance": rl,
                "price": price,
                "pe": 0,
            },
            "fund_flow": {"direction": "流入" if total_flow > 0 else "流出"},
            "ai_prediction": {
                "direction": ai.get("ensemble_direction", "看涨"),
                "confidence": ai.get("ensemble_confidence", 50),
            },
        }
    )
    print("\n  ═══ NL 多空辩论 ═══")
    print(f"  🐂 多头({debate['bull']['score']}分): {'; '.join(debate['bull']['points'][:3])}")
    print(
        f"  🐻 空头({debate['bear']['score']}分): {'; '.join(debate['bear']['points'][:3]) if debate['bear']['points'] else '无'}"
    )
    print(f"  📊 {debate['verdict']} → {debate['action']}")

    # ── L5 策略回测 ──
    print("\n  ═══ L5 策略回测 ═══")
    try:
        from .backtest import DEFAULT_COMPARE_STRATEGIES, compare_strategies

        bt = compare_strategies(kline, DEFAULT_COMPARE_STRATEGIES, 100000, verbose=False)
        if bt:
            bench = (float(kline["收盘"].iloc[-1]) / float(kline["收盘"].iloc[0]) - 1) * 100
            best = max(bt.items(), key=lambda x: x[1]["metrics"]["夏普比率"])
            print(f"  基准(买入持有): {bench:.1f}%")
            print(
                f"  最优: {bt[best[0]]['name']} (夏普{best[1]['metrics']['夏普比率']:.2f} 超额{best[1]['metrics']['超额收益%']:+.1f}%)"
            )
            for s, res in list(bt.items())[:5]:
                m = res["metrics"]
                bar = "█" * int(max(m["总收益率%"], 0) / 15)
                print(
                    f"  {res['name']:<12} {bar} {m['总收益率%']:.0f}%(超额{m['超额收益%']:+.0f}%) 夏普{m['夏普比率']:.2f} 回撤{m['最大回撤%']:.0f}%"
                )
    except Exception:
        print("  回测数据不足")

    # ── L6 AI预测 ──
    print("\n  ═══ L6 AI预测(三模型) ═══")
    try:
        ml = ai
        if ml.get("agreement", "?") == "高":
            emoji = "📈" if ml.get("ensemble_direction") == "看涨" else "📉"
            print(
                f"  {emoji} 三模型一致{ml.get('ensemble_direction', '?')} | 置信{ml.get('ensemble_confidence', 0):.0f}% | 一致性:高 ({ml.get('votes', '?')})"
            )
        else:
            print(
                f"  ⚠️ 分歧 | 投票: {ml.get('ensemble_direction', '?')} | 置信{ml.get('ensemble_confidence', 0):.0f}% | 一致性:{ml.get('agreement', '?')} ({ml.get('votes', '?')})"
            )
        for mk, label in [("xgb", "XGBoost"), ("rf", "RandomForest"), ("lgb", "LightGBM")]:
            m = ml.get("models", {}).get(mk, {})
            if "error" not in m and m.get("预测方向"):
                print(
                    f"  {label}: {m.get('预测方向', '')} 上涨{m.get('上涨概率', 0)}% | 准确率{m.get('准确率%', 0)}% | AUC:{m.get('AUC', 0):.3f}"
                )
                if m.get("重要特征"):
                    tops = [f"{f['特征']}({f['重要性']:.3f})" for f in m["重要特征"][:3]]
                    print(f"    关键因子: {', '.join(tops)}")
    except Exception:
        print("  ML预测暂不可用")

    # ── L7 宏观 ──
    print("\n  ═══ L7 宏观环境 ═══")
    try:
        from .advanced import macro_market_signal

        macro = macro_market_signal()
        if "error" not in macro:
            ind = macro.get("数据", {})
            pmi = ind.get("制造业PMI", "?") or "?"
            m2 = ind.get("M2同比%", "?") or "?"
            cpi = ind.get("CPI同比%", "?") or "?"
            print(f"  PMI: {pmi} | M2: {m2}% | CPI: {cpi}%")
            sigs = macro.get("信号", [])
            print(f"  信号: {'; '.join(sigs) if sigs else '无'}")
            print(f"  整体: {macro.get('整体', '')}")
    except Exception:
        print("  宏观数据暂不可用")

    # ═══════════════════════════════════
    # 四、综合预测 & 操作建议
    # ═══════════════════════════════════
    print(f"\n{'─' * W}")
    print("  四、综合预测 & 操作建议")
    print(f"{'─' * W}")

    # 复用 section 3 的计算结果
    st_score = st.get("短线评分", 50) if isinstance(st, dict) else 50
    combo_str = combo.get("强度", 0)
    mr_str = mr.get("共振强度", 0)
    ml_dir = ai.get("ensemble_direction", "?")
    ml_conf = ai.get("ensemble_confidence", 50)
    ml_agree = ai.get("agreement", "?")

    # 综合判断
    if ml_dir == "看涨" and combo_str >= 3:
        pred_dir = "看涨"
        pred_conf = ml_conf
    elif ml_dir == "看跌" and combo_str <= 0:
        pred_dir = "看跌"
        pred_conf = ml_conf
    elif combo_str >= 3:
        pred_dir = "看涨(技术面)"
        pred_conf = 60
    else:
        pred_dir = "震荡"
        pred_conf = 50

    # 预测天数&目标
    if combo_str >= 4:
        pred_days = "2-3天"
        target_pct = round(atr / price * 200, 1)
    elif combo_str >= 2:
        pred_days = "1-2天"
        target_pct = round(atr / price * 100, 1)
    else:
        pred_days = "观望"
        target_pct = 0

    target_price = round(price * (1 + target_pct / 100), 2)
    buy_low = round(price - atr * 0.5, 2)
    buy_high = round(price + atr * 0.3, 2)
    sl_price = round(max(price - 1.5 * atr, price * 0.93), 2)
    tp_price = round(min(price + 3 * atr, price * 1.12), 2)

    # 资金判断
    flow_str = f"{total_flow:+.2f}亿" if flow_ok else "无数据(东方财富挂)"
    flow_sig = "✅" if total_flow > 1 else ("⚠️" if total_flow < -1 else "—")

    roe = funds.get("ROE", 0) if isinstance(funds, dict) else 0

    print(f"  {name}({code})  {sector_full}")
    print(f"  现价 {price} | 近5日 {n5:+.1f}% | 近20日 {n20:+.1f}%")
    print("")
    print(f"  评分: {qs} {qr} | 短线: {st_score} | 组合信号: +{combo_str} | 共振: {mr_str}")
    print(
        f"  AI预测: {ml_dir} 置信{ml_conf:.0f}% 一致性:{ml_agree} | 主力5日: {flow_str} {flow_sig}"
    )
    print(f"  ROE: {roe:.2f}% | ATR: {atr:.2f}")
    print("")
    print(
        f"  预测方向: {pred_dir}({pred_conf:.0f}%) | 周期: {pred_days} | 目标涨幅: +{target_pct}% → {target_price}"
    )
    print("")
    print("  ┌────────────┬──────────┬──────────┬──────────┐")
    print("  │ 买入区间     │ 止损       │ 止盈       │ 持有天数   │")
    print("  ├────────────┼──────────┼──────────┼──────────┤")
    print(f"  │ {buy_low}-{buy_high:<7} │ {sl_price:<8} │ {tp_price:<8} │ {pred_days:<8} │")
    print("  └────────────┴──────────┴──────────┴──────────┘")

    # ═══════════════════════════════════
    # 六、风险提示
    # ═══════════════════════════════════
    print(f"\n{'─' * W}")
    print("  五、风险提示")
    print(f"{'─' * W}")

    risks = []
    if n5 > 12:
        risks.append(f"近5日涨{n5:.1f}%，短线追高风险")
    if n20 > 30:
        risks.append(f"近20日涨{n20:.1f}%，追高惩罚已触发")
    if tech.get("rsi_value", 50) > 72:
        risks.append(f"RSI={tech['rsi_value']:.0f}接近超买")
    if total_flow < -1:
        risks.append(f"主力5日流出{total_flow:.1f}亿")
    if sector_rank == 0:
        risks.append("板块排名数据不可用，无法评估板块联动风险")
    elif sector_rank > len(ranked) * 0.6 if ranked else False:
        risks.append(f"板块排名靠后(#{sector_rank})，板块拖累风险")
    if ml_dir == "看跌" and combo_str >= 3:
        risks.append("⚠️ AI看跌但技术面看涨，信号矛盾！建议轻仓或观望")
    if combo_str <= 1:
        risks.append("组合信号偏弱，短期方向不明")

    if not risks:
        risks.append("暂无明显风险信号")

    for risk in risks:
        print(f"  ⚠️ {risk}")

    print(f"\n{'=' * W}")
    print("  数据来源: 新浪财经(实时行情) | Baostock(行业分类) | 东方财富(板块/资金)")
    print("  免责声明: 以上分析仅供学习研究，不构成投资建议")
    print(f"{'=' * W}\n")
