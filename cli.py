#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A股量化分析平台 — 统一CLI入口

用法:
  python cli.py scan                    # 全市场扫描
  python cli.py scan --mode mainboard   # 仅主板扫描
  python cli.py analyze 601677 002119   # 个股深度分析
  python cli.py analyze --owned         # 分析已持仓股票
  python cli.py report --type screener  # 生成选股报告
  python cli.py report --type eod       # 生成收盘复盘报告
  python cli.py check                   # 检查持仓状态
  python cli.py check --alerts          # 检查预警触发
  python cli.py config show             # 查看配置
  python cli.py clean --archive         # 归档旧文件
"""
import sys
import os
import io
import argparse
import time
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 延迟导入重型模块（pandas/numpy仅在需要时加载，节省CLI --help等轻量操作启动时间）
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


# ── 解析器 ────────────────────────────────────────

def build_parser():
    p = argparse.ArgumentParser(
        description="A股量化分析平台",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python cli.py scan --mode mainboard --top-n 20
  python cli.py analyze 601677 002119 --days 365
  python cli.py report --type eod
  python cli.py check --owned
        """,
    )
    sub = p.add_subparsers(dest="command", help="子命令")

    # === scan ===
    sp = sub.add_parser("scan", help="全市场/主板扫描")
    sp.add_argument("--mode", choices=["full", "mainboard"], default="mainboard",
                    help="扫描模式: full=全A股, mainboard=仅主板")
    sp.add_argument("--top-n", type=int, default=50, help="保留前N只 (默认50)")
    sp.add_argument("--min-score", type=int, default=60, help="最低综合评分 (默认60)")
    sp.add_argument("--resume", action="store_true", help="从上次checkpoint续跑")
    sp.add_argument("--output", "-o", help="输出文件路径")
    sp.add_argument("--no-save", action="store_true", help="不保存结果到CSV/JSON")

    # === enhanced-scan (增强选股) ===
    esp = sub.add_parser("enhanced-scan", help="增强选股(板块+短线+ML+自定义因子)")
    esp.add_argument("--mode", choices=["mainboard", "full", "top_sectors"], default="mainboard",
                     help="mainboard=主板, full=全A股, top_sectors=仅前排板块")
    esp.add_argument("--top-n", type=int, default=30, help="返回前N只 (默认30)")
    esp.add_argument("--sector-top-n", type=int, default=5, help="板块排名取前N (默认5)")
    esp.add_argument("--min-price", type=float, default=10, help="最低价格 (默认10)")
    esp.add_argument("--max-price", type=float, default=80, help="最高价格 (默认80)")
    esp.add_argument("--min-amplitude", type=float, default=3, help="最低振幅(默认3, 短线需要波动)")
    esp.add_argument("--min-score", type=int, default=45, help="最低量化评分 (默认45)")
    esp.add_argument("--no-ml", action="store_true", help="禁用ML预测")
    esp.add_argument("--no-custom-factors", action="store_true", help="禁用自定义因子")
    esp.add_argument("--output", "-o", help="输出文件路径")

    # === overnight-scan (一夜持股法) ===
    osp = sub.add_parser("overnight-scan", help="一夜持股法：尾盘六步选股（2:30后运行）")
    osp.add_argument("--top-n", type=int, default=20, help="返回前N只 (默认20)")
    osp.add_argument("--min-vr", type=float, default=1.0, help="最低量比 (默认1.0)")
    osp.add_argument("--quiet", action="store_true", help="静默模式(仅输出结果表格)")

    # === overnight-sell (隔夜卖出检查) ===
    osell = sub.add_parser("overnight-sell", help="隔夜持仓早盘卖出检查（10:00前运行）")
    osell.add_argument("codes", nargs="+", help="持仓代码+成本，格式: 600066=33.20")

    # === analyze ===
    ap = sub.add_parser("analyze", help="个股/持仓深度分析")
    ap.add_argument("codes", nargs="*", help="股票代码（可多个，空格分隔）")
    ap.add_argument("--owned", action="store_true", help="分析当前持仓")
    ap.add_argument("--days", type=int, default=365, help="K线天数 (默认365)")
    ap.add_argument("--output", "-o", help="输出JSON路径")
    ap.add_argument("--full", action="store_true", help="一键全出：技术+量化+基本面+资金+回测+AI+宏观")
    ap.add_argument("--fast", action="store_true", help="快速模式：仅本地计算(L0-L3)，零网络等待，盘中秒出")
    ap.add_argument("--ultimate", action="store_true", help="终极分析：大盘→板块排名→资金流向→七层→预测价位→操作建议")

    # === report ===
    rp = sub.add_parser("report", help="生成报告")
    rp.add_argument("--type", choices=["screener", "eod", "sector", "portfolio"],
                    default="eod", help="报告类型 (默认eod)")
    rp.add_argument("--top-n", type=int, default=10, help="报告中Top N (默认10)")
    rp.add_argument("--output", "-o", help="输出路径")

    # === check ===
    cp = sub.add_parser("check", help="持仓/预警检查")
    cp.add_argument("--owned", action="store_true", help="显示持仓浮盈状态")
    cp.add_argument("--alerts", action="store_true", help="检查预警触发")
    cp.add_argument("--market", action="store_true", help="大盘指数概览（含消息摘要）")
    cp.add_argument("--limit", action="store_true", help="涨跌停统计")
    cp.add_argument("--rotation", action="store_true", help="板块轮动分析")
    cp.add_argument("--lhb", action="store_true", help="龙虎榜数据")
    cp.add_argument("--rs", nargs="?", const="all", help="相对强弱 (指定股票代码, 默认全部持仓)")
    cp.add_argument("--network", action="store_true", help="网络健康检测（测各数据源延迟）")
    cp.add_argument("--premarket", action="store_true", help="开盘前全面自检: 网络+数据库+数据源+API一键检测")
    cp.add_argument("--update-kline", action="store_true", help="增量更新持仓K线至最新交易日")

    # === config ===
    cfgp = sub.add_parser("config", help="配置管理")
    cfgp.add_argument("action", choices=["show", "init"], default="show",
                      help="show=查看配置, init=生成默认配置")

    # === history ===
    hp = sub.add_parser("history", help="历史评分查询")
    hp.add_argument("code", nargs="?", help="股票代码（查单只趋势）")
    hp.add_argument("--top", type=int, default=20, help="某日Top N (默认20)")
    hp.add_argument("--date", help="日期 YYYY-MM-DD (默认最新)")
    hp.add_argument("--summary", action="store_true", help="显示全市场评分分布")
    hp.add_argument("--dates", action="store_true", help="列出可用日期")

    # === clean ===
    clp = sub.add_parser("clean", help="清理/归档")
    clp.add_argument("--archive", action="store_true", help="归档旧JSON/CSV到archive/")
    clp.add_argument("--dry-run", action="store_true", help="仅列出将归档的文件，不实际移动")

    # === audit ===
    adp = sub.add_parser("audit", help="系统自审计(数据质量+API健康+内部一致性)")
    adp.add_argument("--no-fix", action="store_true", help="仅检测不自动修复")

    # === advanced ===
    avp = sub.add_parser("advanced", help="高级分析(龙虎榜/北向/两融/增减持/调研/财报/宏观)")
    avp.add_argument("--lhb", action="store_true", help="龙虎榜分析")
    avp.add_argument("--north", action="store_true", help="北向资金流向")
    avp.add_argument("--margin", action="store_true", help="融资融券汇总")
    avp.add_argument("--insider", type=str, nargs="?", const="all", help="高管增减持(指定代码或全部)")
    avp.add_argument("--visit", type=str, nargs="?", const="top", help="机构调研(指定代码或热门)")
    avp.add_argument("--financial", type=str, help="财报深度拆解(指定代码)")
    avp.add_argument("--macro", action="store_true", help="宏观指标+市场信号")
    avp.add_argument("--all", action="store_true", help="一键全部分析(含当前持仓)")

    # === backtest ===
    btp = sub.add_parser("backtest", help="策略回测")
    btp.add_argument("code", help="股票代码")
    btp.add_argument("--strategy", "-s", default="ma_cross",
                     choices=["ma_cross","macd_cross","rsi_reversal","bollinger","ma_trend","momentum_breakout","grid"],
                     help="策略名称（默认ma_cross）")
    btp.add_argument("--compare", action="store_true", help="多策略对比")
    btp.add_argument("--strategies", type=str, default=None,
                     help="对比策略列表，逗号分隔（如 ma_cross,macd_cross,rsi_reversal）")
    btp.add_argument("--optimize", action="store_true", help="参数优化")
    btp.add_argument("--days", type=int, default=365, help="回测天数")
    btp.add_argument("--capital", type=int, default=100000, help="初始资金")
    btp.add_argument("--commission", type=float, default=0.0003, help="手续费率（默认0.0003）")
    btp.add_argument("--slippage", type=float, default=0.001, help="滑点（默认0.001）")
    btp.add_argument("--position-pct", type=float, default=1.0, help="仓位比例（默认1.0）")
    btp.add_argument("--output", "-o", type=str, default=None, help="导出JSON文件路径")
    btp.add_argument("--stop-loss", type=float, default=None, metavar="PCT",
                     help="固定止损比例（如 0.08=8%%亏损止损）")
    btp.add_argument("--take-profit", type=float, default=None, metavar="PCT",
                     help="固定止盈比例（如 0.15=15%%盈利止盈）")
    btp.add_argument("--trailing-stop", type=float, default=None, metavar="PCT",
                     help="移动止损比例（如 0.05=从高点回撤5%%止损）")

    # === ml ===
    mlp = sub.add_parser("ml", help="机器学习预测")
    mlp.add_argument("code", help="股票代码")
    mlp.add_argument("--direction", action="store_true", help="涨跌方向预测")
    mlp.add_argument("--return", dest="predict_return", action="store_true", help="涨跌幅预测")
    mlp.add_argument("--enhance", action="store_true", help="ML增强评分")

    qp = sub.add_parser("quality", help="公司质地七问(商业模式+护城河+现金流+生命周期+估值+事件)")
    qp.add_argument("code", help="股票代码")
    qp.add_argument("--short", action="store_true", help="仅结论不展开")

    return p


# ── 共享分析函数（替代各脚本中重复的 deep_analyze） ──

def deep_analyze(code, days=365, skip_nt=False):
    """个股深度分析（单次调用，返回完整dict）"""
    pd = _get_pd()
    np = _get_np()
    from stock_analyzer.cache import cached_kline, cached_fundamentals
    from stock_analyzer.analysis import (full_technical_analysis, get_technical_summary,
                                          calc_support_resistance, calc_stop_levels,
                                          score_fundamental)
    from stock_analyzer.quant import (composite_quant_score, calc_risk_metrics,
                                       generate_all_signals, consolidate_signals,
                                       evaluate_trading_style)

    kline = cached_kline(code, days=days)
    if len(kline) < 20:
        return None

    # 合并今日实时数据到K线（修复：之前只用昨日缓存，指标滞后1天）
    from stock_analyzer.fetcher import sina_real_time
    try:
        rt = sina_real_time([code])
        if rt and code in rt:
            r = rt[code]
            today_open = float(r.get('open', 0) or 0)
            today_high = float(r.get('high', 0) or 0)
            today_low = float(r.get('low', 0) or 0)
            today_price = float(r.get('price', 0) or 0)
            today_vol = float(r.get('volume', 0) or 0)
            if today_open > 0 and today_price > 0:
                last_date = str(kline['日期'].iloc[-1])[:10]
                today_str = pd.Timestamp.now().strftime('%Y-%m-%d')
                if today_str > last_date:
                    new_row = pd.DataFrame([{
                        '日期': pd.Timestamp(today_str),
                        '开盘': today_open,
                        '最高': today_high,
                        '最低': today_low,
                        '收盘': today_price,
                        '成交量': int(today_vol),
                        '成交额': 0,
                    }])
                    kline = pd.concat([kline, new_row], ignore_index=True)
    except Exception:
        pass  # 实时数据拉不到就用缓存，不阻塞分析

    kline = full_technical_analysis(kline)
    tech = get_technical_summary(kline)
    sr = calc_support_resistance(kline)

    price = float(kline.iloc[-1]['收盘'])
    atr = float(kline.iloc[-1].get('ATR', np.nan))
    if pd.isna(atr) or atr <= 0:
        atr = price * 0.03

    if not isinstance(sr, dict):
        sr = {'支撑位': [price * 0.9], '压力位': [price * 1.1]}
    sl = sr.get('支撑位', [price * 0.9])
    rl = sr.get('压力位', [price * 1.1])
    stop = calc_stop_levels(price, atr, float(sl[0]), float(rl[0]))

    risk = calc_risk_metrics(kline)
    sigs = consolidate_signals(generate_all_signals(kline))
    funds = cached_fundamentals(code)
    fsv, _ = score_fundamental(funds) if funds else (0, {})
    quant = composite_quant_score(kline, funds, sentiment_score=None)
    trading = evaluate_trading_style(kline, funds, risk)

    n5 = float((kline.iloc[-1]['收盘'] / kline.iloc[-6]['收盘'] - 1) * 100) if len(kline) > 5 else 0
    n20 = float((kline.iloc[-1]['收盘'] / kline.iloc[-21]['收盘'] - 1) * 100) if len(kline) > 20 else 0

    rsi = tech.get('rsi_value', 50) if isinstance(tech, dict) else 50
    macd_sig = tech.get('macd_signal', '') if isinstance(tech, dict) else ''
    kdj_sig = tech.get('kdj_signal', '') if isinstance(tech, dict) else ''

    qs = quant if isinstance(quant, dict) else {}
    fs = qs.get('factor_scores', {})

    def gf(k):
        v = fs.get(k, {})
        return float(v.get('score', 0)) if isinstance(v, dict) else 0

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
                has_nt = nt.get('has_national_team', False)
                nt_holders = nt.get('holders', [])
        except Exception:
            pass

    return {
        'code': code, 'price': price, 'atr': atr,
        'near_5d': round(n5, 2), 'near_20d': round(n20, 2),
        'rsi': round(rsi, 1),
        'macd_signal': macd_sig, 'kdj_signal': kdj_sig,
        'fund_score': round(fsv, 1),
        'roe': round(funds.get('ROE', 0), 2) if funds else 0,
        'sharpe': round(risk_d.get('sharpe_ratio', 0), 3),
        'max_dd': round(risk_d.get('max_drawdown_pct', 0), 2),
        'var95': round(risk_d.get('VaR_95_pct', 0), 2),
        'volatility': round(risk_d.get('annualized_volatility_pct', 0), 2),
        'signal_bias': sigs_d.get('bias', 'neutral'),
        'signal_score': sigs_d.get('score', 0),
        'short_score': round(ts_d.get('short_term_score', 0), 1),
        'long_score': round(ts_d.get('long_term_score', 0), 1),
        'style': ts_d.get('style', ''),
        'confidence': ts_d.get('style_confidence', ''),
        'short_basis': ts_d.get('short_term_basis', ''),
        'long_basis': ts_d.get('long_term_basis', ''),
        'qs_composite': round(float(qs.get('composite_score', 0)), 1),
        'qs_rating': str(qs.get('rating', '')),
        'mom_s': round(gf('momentum'), 1),
        'tech_s': round(gf('technical'), 1),
        'fund_s': round(gf('fundamental'), 1),
        'vol_s': round(gf('volume'), 1),
        'risk_s': round(gf('risk'), 1),
        'has_nt': has_nt, 'nt_holders': nt_holders,
        'support': [round(float(x), 2) for x in sl[:2]],
        'resistance': [round(float(x), 2) for x in rl[:2]],
        'stop_loss': round(stop_d.get('止损参考价', 0), 2),
        'stop_profit': round(stop_d.get('止盈参考价', 0), 2),
        '_kline': kline,
        # 完整对象（供HTML报告等需要详细数据的场景使用）
        'fundamentals': funds,
        'quant_score': quant, 'technical_summary': tech,
        'support_resistance': sr, 'stop_levels': stop,
        'risk_metrics': risk, 'signals': sigs,
        'trading_style': trading,
    }


def load_owned_stocks():
    """从 mainboard_owned 文件加载当前持仓（自动选最新）"""
    import glob
    files = sorted(glob.glob('mainboard_owned_*.json'), reverse=True)
    if not files:
        return {}
    with open(files[0], 'r', encoding='utf-8') as f:
        return json.load(f)


# ── 命令实现 ──────────────────────────────────────

def _cmd_premarket_check():
    """开盘前全面自检：网络→数据库→数据源→API 一键检测"""
    import time, os, sqlite3
    from datetime import datetime

    W = 60
    print(f"\n{'='*W}")
    print(f"  StockInsight 开盘前自检 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*W}")

    results = {"pass": 0, "warn": 0, "fail": 0}

    def check(name, ok, detail=""):
        if ok:
            results["pass"] += 1
            print(f"  ✅ {name}: {detail}")
        else:
            results["fail"] += 1
            print(f"  ❌ {name}: {detail}")

    # 1. 网络健康
    print(f"\n── 1. 网络健康 ──")
    try:
        from stock_analyzer.network_health import check_all
        health = check_all()
        for src_name, label in [("sina","新浪"), ("tencent","腾讯"), ("eastmoney","东方财富")]:
            s = getattr(health, src_name, None)
            if s:
                avail = s.available
                lat = s.latency_ms
                if avail: check(label, True, f"{lat:.0f}ms")
                else: check(label, False, "不可达" if lat > 5000 else f"{lat:.0f}ms")
        # Baostock
        try:
            import baostock as bs; lg = bs.login()
            check("Baostock", lg.error_code == '0', "本地库可用" if lg.error_code == '0' else lg.error_msg)
            bs.logout()
        except Exception:
            check("Baostock", False, "未安装")
        # 模式
        print(f"  最优K线源: {health.best_kline_source}")
        print(f"  模式: {health.mode.upper()}")
    except Exception as e:
        check("网络健康检测", False, str(e))

    # 2. 数据库
    print(f"\n── 2. 数据库 ──")
    try:
        from stock_analyzer.config import DB_PATH
        if os.path.exists(DB_PATH):
            size_mb = os.path.getsize(DB_PATH) / (1024*1024)
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM kline_store")
            kc = cur.fetchone()[0]
            cur.execute("SELECT MAX(updated_at) FROM kline_store")
            ts = cur.fetchone()[0]
            age_h = (time.time() - ts) / 3600 if ts else 999
            cur.execute("SELECT MAX(date) FROM daily_scores")
            last_date = cur.fetchone()[0] or "无"
            conn.close()
            check("数据库文件", True, f"{size_mb:.0f}MB")
            check("K线缓存", kc > 4000, f"{kc}只 (距今{age_h:.0f}h)")
            check("评分数据", age_h < 48, f"最新{last_date}")
        else:
            check("数据库", False, "文件不存在")
    except Exception as e:
        check("数据库检查", False, str(e))

    # 3. 实时行情
    print(f"\n── 3. 实时行情 ──")
    try:
        t0 = time.time()
        from stock_analyzer.fetcher import sina_real_time
        rt = sina_real_time(["000001","399001"])
        lat = (time.time()-t0)*1000
        if rt and len(rt) >= 1:
            check("新浪实时行情", True, f"{lat:.0f}ms ({len(rt)}只)")
        else:
            check("新浪实时行情", False, "返回空")
    except Exception as e:
        check("新浪实时行情", False, str(e))

    # 4. 资金流向
    print(f"\n── 4. 资金流向 ──")
    try:
        t0 = time.time()
        from stock_analyzer.fetcher import get_fund_flow
        ff = get_fund_flow("000001", days=5)
        lat = (time.time()-t0)*1000
        if ff is not None and not ff.empty:
            check("东方财富资金流向", True, f"{lat:.0f}ms")
        else:
            now_h = datetime.now().hour
            if now_h < 15:
                print(f"  ⚠️ 东方财富资金流向: 盘中无数据，盘后T+1发布 (正常)")
            else:
                check("东方财富资金流向", False, "盘后仍无数据，可能API异常")
    except Exception as e:
        check("东方财富资金流向", False, str(e)[:60])

    # 5. 板块
    print(f"\n── 5. 板块数据 ──")
    try:
        from stock_analyzer.fetcher import get_sectors
        sectors = get_sectors()
        has_sectors = (isinstance(sectors, dict) and len(sectors) > 0) or \
                       (hasattr(sectors, 'empty') and not sectors.empty)
        if has_sectors:
            check("板块分类", True, f"{len(sectors)}个板块")
        else:
            check("板块分类", False, "返回空，将用静态兜底")
    except Exception as e:
        check("板块分类", False, str(e)[:60])

    # 总结
    print(f"\n{'='*W}")
    total = results["pass"] + results["warn"] + results["fail"]
    print(f"  自检完成: ✅{results['pass']} ⚠️{results['warn']} ❌{results['fail']} / {total}")
    if results["fail"] == 0:
        print(f"  结论: 🟢 系统就绪，可以正常使用")
    elif results["fail"] <= 2:
        print(f"  结论: 🟡 部分数据源不可用，基本功能正常")
    else:
        print(f"  结论: 🔴 多个数据源故障，建议等待恢复后重试")
    print(f"{'='*W}\n")


def cmd_scan(args):
    """执行全市场/主板扫描"""
    from stock_analyzer.screener import load_all_a_shares, quick_filter
    from stock_analyzer.cache import cached_kline, cached_fundamentals
    from stock_analyzer.analysis import full_technical_analysis
    from stock_analyzer.quant import composite_quant_score
    from stock_analyzer.fetcher import sina_real_time

    print(f"{'='*60}")
    print(f"扫描模式: {'全A股' if args.mode == 'full' else '仅主板'} | "
          f"最低评分: {args.min_score} | Top: {args.top_n}")
    print(f"{'='*60}")

    # 加载股票池
    all_codes = load_all_a_shares()
    if args.mode == 'mainboard':
        codes = [c for c in all_codes if c.startswith('60') or c.startswith('00')]
    else:
        codes = all_codes
    print(f"股票池: {len(codes)} 只")

    # 快速过滤
    codes = quick_filter(codes)
    if args.resume:
        done = _load_checkpoint()
        codes = [c for c in codes if c not in done]
        print(f"续跑模式: 跳过 {len(done)} 只已完成，剩余 {len(codes)} 只")

    # 并行分析（ThreadPoolExecutor，利用 I/O 等待时间）
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout, as_completed
    from threading import Lock
    from stock_analyzer.config import SCAN_WORKERS

    results = []
    total = len(codes)
    t0 = time.time()
    skipped = 0
    completed = 0
    _lock = Lock()
    _print_lock = Lock()

    def analyze_one(code):
        """单只分析（供线程池调用）"""
        try:
            r = deep_analyze(code, days=120, skip_nt=True)
            return ('ok', code, r)
        except Exception as e:
            return ('err', code, str(e))

    with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as executor:
        futures = {executor.submit(analyze_one, c): c for c in codes}

        for future in as_completed(futures):
            code = futures[future]
            try:
                status, code2, r = future.result(timeout=45)
            except FutureTimeout:
                with _lock:
                    skipped += 1
                    completed += 1
                print(f"  ⏰ [{code}] 超时，跳过")
                continue
            except Exception as e:
                with _lock:
                    skipped += 1
                    completed += 1
                continue

            with _lock:
                completed += 1
                if status == 'ok' and r and r['qs_composite'] >= args.min_score:
                    results.append(r)
                elif status == 'err':
                    skipped += 1

                _save_checkpoint_single(code)

                # 进度报告
                if completed % 50 == 0 or completed == total:
                    elapsed = time.time() - t0
                    rate = completed / elapsed if elapsed > 0 else 0
                    eta = (total - completed) / rate if rate > 0 else 0
                    pct = completed / total * 100
                    print(f"  [{completed}/{total}] {pct:.0f}%  速率 {rate:.1f}只/s  "
                          f"ETA {eta/60:.0f}min  结果 {len(results)}  跳过 {skipped}")

    # 排序输出
    results.sort(key=lambda x: x['qs_composite'], reverse=True)
    top = results[:args.top_n]

    print(f"\n{'='*60}")
    print(f"扫描完成: {len(results)} 只达标  跳过/失败: {skipped}  耗时 {((time.time()-t0)/60):.0f}min")
    print(f"{'='*60}")
    print(f"{'#':<4} {'代码':<8} {'板块':<10} {'综合':<7} {'近20日':<9} {'RSI':<5} {'MACD':<6} {'基本面':<6}")
    print("-" * 72)
    for i, r in enumerate(top):
        from stock_analyzer.sector_info import get_stock_sector
        sect = get_stock_sector(r['code'])[:10]
        print(f"{i+1:<4} {r['code']:<8} {sect:<10} {r['qs_composite']:<7.1f} "
              f"{r['near_20d']:<+9.1f} {r['rsi']:<5.0f} {r['macd_signal']:<6} {r['fund_s']:<6.0f}")

    if not args.no_save:
        out = args.output or f"scan_{args.mode}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        with open(out, 'w', encoding='utf-8') as f:
            json.dump({'scan_time': datetime.now().isoformat(),
                       'mode': args.mode, 'total': len(results),
                       'results': top}, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存: {out}")

    # 写入 daily_scores 数据库
    try:
        from stock_analyzer.history_db import append_daily_results
        import pandas as pd
        df = pd.DataFrame([{
            "代码": r["code"], "名称": r.get("name", ""),
            "综合评分": r["qs_composite"], "评级": r["qs_rating"],
            "动量分": r.get("mom_s", 0), "技术分": r.get("tech_s", 0),
            "基本面分": r.get("fund_s", 0), "量能分": r.get("vol_s", 0),
            "风险分": r.get("risk_s", 0),
        } for r in results])
        if not df.empty:
            n = append_daily_results(df, datetime.now().strftime("%Y-%m-%d"))
            print(f"已写入 daily_scores: {n} 条")
    except Exception as e:
        print(f"写入 daily_scores 失败: {e}")

    _clear_checkpoint()


def _print_full_analysis(code, days=365, fast=False):
    """一键全出：七层分析。复用 deep_analyze() 计算核心指标。
    fast=True 时仅 L0-L3（纯本地计算+跳过国家队查询），适合盘中快速决策。"""
    # 先跑核心分析（复用，fast模式跳过国家队API）
    r = deep_analyze(code, days=days, skip_nt=fast)
    if r is None:
        print(f"  {code}: K线数据不足")
        return

    kline = r['_kline']
    price = r['price']
    funds = r['fundamentals']

    # ── 输出 ──
    W = 60
    def sep(title):
        print(f"\n{'─'*W}")
        print(f"  {title}")
        print(f"{'─'*W}")

    print(f"\n{'='*W}")
    print(f"  {code} 全维度分析")
    print(f"{'='*W}")

    # 板块归属(行业 + 概念)
    from stock_analyzer.sector_info import get_stock_all_sectors
    si = get_stock_all_sectors(code)
    print(f"  行业: {si['industry']}")
    if si['concepts']:
        print(f"  概念: {', '.join(si['concepts'][:5])}")

    # L0r: 实时行情（fast/full 都拉新浪实时，0.06s）
    from stock_analyzer.fetcher import sina_real_time
    rt = sina_real_time([code])
    realtime_note = ""
    if code in rt:
        rtp = rt[code]
        rt_price = rtp.get('最新价', 0)
        rt_chg = rtp.get('涨跌幅', 0)
        rt_high = rtp.get('最高', 0)
        rt_low = rtp.get('最低', 0)
        rt_open = rtp.get('今开', 0)
        if rt_price and float(rt_price) != price:
            realtime_note = f" ⚠️缓存价{price:.2f}≠实时价{float(rt_price):.2f}"
            price = float(rt_price)
        tag = "(实时)" if fast else ""
        print(f"\n  实时行情: {rt_price} ({rt_chg}%) 今开{rt_open} 最高{rt_high} 最低{rt_low}{realtime_note} {tag}")

    # L0: 短线专项
    sep("L0 短线专项")
    try:
        from stock_analyzer.short_term import (
            calc_turnover_signal, calc_consecutive_days, calc_tail_tendency,
            calc_fund_flow_summary, calc_news_catalyst, short_term_score,
            calc_combo_signals, calc_multi_timeframe_resonance,
        )
        turnover = calc_turnover_signal(kline)
        consec = calc_consecutive_days(kline)
        tail = calc_tail_tendency(kline)
        st_score = short_term_score(kline, code)
        combo = calc_combo_signals(kline, code)
        if not fast:
            mr = calc_multi_timeframe_resonance(code)

        print(f"  换手率: {turnover.get('换手率%',0):.1f}% | 量比: {turnover.get('量比',1):.1f} | {turnover.get('信号','')}")
        print(f"  连{consec.get('方向','')}{consec.get('天数',0)}天 | {consec.get('信号','')} | 节奏: {tail.get('近5日涨跌节奏','')}")
        print(f"  尾盘: {tail.get('尾盘倾向','')} | 近10日阳线: {tail.get('近10日阳线占比%',50):.0f}%")
        print(f"  短线评分: {st_score.get('短线评分',0):.0f} → {st_score.get('评级','')} | ATR占比: {st_score.get('ATR占比%',0):.1f}%")
        # 组合信号
        print(f"  组合信号: {combo.get('信号','')} (强度{combo.get('强度',0):+d}) | {' '.join(combo.get('详情',[])[:4])}")
        if not fast:
            print(f"  多周期共振: {mr.get('状态','')} ({mr.get('共振强度',0):+d})")
        if st_score.get('风险'):
            print(f"  风险: {' | '.join(st_score['风险'])}")

        ff = calc_fund_flow_summary(code) if not fast else {"主力动向": "快速模式跳过", "近5日累计(万)": 0, "今日方向": ""}
        print(f"  主力: {ff.get('主力动向','')} | 近5日: {ff.get('近5日累计(万)',0)}万 | 今日: {ff.get('今日方向','')}")

        news = calc_news_catalyst(code) if not fast else {"消息催化": "快速模式跳过"}
        print(f"  消息: {news.get('消息催化','')}")
    except Exception:
        print("  短线数据获取失败")

    # L1: 技术面（复用 deep_analyze 结果）
    np = _get_np()
    n5 = r['near_5d']
    n20 = r['near_20d']
    n60 = float((kline.iloc[-1]['收盘']/kline.iloc[-61]['收盘']-1)*100) if len(kline)>60 else 0
    sep("L1 技术面")
    print(f"  现价: {price:.2f}  |  近5日: {n5:+.1f}%  |  近20日: {n20:+.1f}%  |  近60日: {n60:+.1f}%")
    print(f"  MACD: {r['macd_signal']}  |  RSI: {r['rsi']:.0f}  |  KDJ: {r['kdj_signal']}")
    print(f"  支撑: {r['support']}  压力: {r['resistance']}")
    print(f"  止损: {r['stop_loss']:.2f}  |  止盈: {r['stop_profit']:.2f}  |  ATR: {r['atr']:.2f}")

    # L2: 量化评分（复用）
    sep("L2 量化评分")
    print(f"  综合: {r['qs_composite']:.0f} → {r['qs_rating']}  |  短线: {r['short_score']:.0f}分  |  长线: {r['long_score']:.0f}分  |  风格: {r['style']}")
    print(f"  动量: {r['mom_s']:.0f}  技术: {r['tech_s']:.0f}  基本面: {r['fund_s']:.0f}")
    print(f"  量能: {r['vol_s']:.0f}  风险: {r['risk_s']:.0f}")
    print(f"  夏普: {r['sharpe']:.2f}  |  回撤: {r['max_dd']:.1f}%  |  波动率: {r['volatility']:.1f}%")

    # L3: 基本面（复用）
    sep("L3 基本面 & 国家队")
    print(f"  ROE: {r['roe']:.2f}%  |  基本面评分: {r['fund_score']:.0f}")
    if r['has_nt']:
        holders = r['nt_holders']
        print(f"  国家队: 🏛️ {', '.join(holders[:5])}{'...' if len(holders)>5 else ''} ({len(holders)}家)")

    # ── NL: 多空辩论自然语言报告 ──
    sep("NL 多空辩论")
    try:
        from stock_analyzer.nl_report import generate_bull_bear_debate

        debate_data = {
            "quant_score": r.get('qs_composite', 50),
            "technical": {
                "macd_signal": r.get('macd_signal', ''),
                "kdj_signal": r.get('kdj_signal', ''),
                "rsi": r.get('rsi', 50),
                "near5d": r.get('near_5d', 0),
                "near20d": r.get('near_20d', 0),
                "ma_status": '',
                "resistance": [],
                "price": r.get('price', 0),
                "pe": r.get('pe', 0),
            },
            "fund_flow": {"direction": r.get('fund_flow_direction', '')},
            "ai_prediction": {
                "direction": "看涨" if r.get('ml_up_prob', 50) > 50 else "看跌",
                "confidence": r.get('ml_up_prob', 50),
            },
        }
        debate = generate_bull_bear_debate(debate_data)

        print(f"  🐂 多头({debate['bull']['score']}分): {'; '.join(debate['bull']['points'][:3])}")
        print(f"  🐻 空头({debate['bear']['score']}分): {'; '.join(debate['bear']['points'][:3])}")
        print(f"  📊 结论: {debate['verdict']} → {debate['action']} (置信度:{debate['confidence']})")
    except Exception as e:
        print(f"  (多空辩论: {e})")

    # L4-L7: 仅全量模式（需网络API，盘中--fast跳过）
    if fast:
        print(f"\n  ⚡ 快速模式(L0-L3)，耗时 <1s")
        print(f"{'='*W}")
        return

    # L4: 资金面 & 消息
    sep("L4 资金面 & 消息")
    try:
        from stock_analyzer.advanced import insider_signal, get_institution_visits, north_flow_signal, get_margin_summary
        sig = insider_signal(code)
        print(f"  高管增减持: {sig.get('signal','无数据')} ({sig.get('records',0)}笔)")
        visits = get_institution_visits(code, days=60)
        print(f"  机构调研: {len(visits)}次(近60日)")
        nf = north_flow_signal()
        if 'error' not in nf:
            print(f"  北向资金: {'净流入' if any(v.get('净买额(亿)',0)>0 for v in nf.values()) else '净流出'}")
        mg = get_margin_summary()
        if mg:
            total_mg = sum(v.get('融资余额(亿)',0) for v in mg.values())
            print(f"  两市融资余额: {total_mg:.0f}亿")
    except Exception:
        pass

    # L5: 策略回测（复用 kline）
    sep("L5 策略回测")
    try:
        from stock_analyzer.backtest import compare_strategies, DEFAULT_COMPARE_STRATEGIES
        bt = compare_strategies(kline, DEFAULT_COMPARE_STRATEGIES, 100000, verbose=False)
        if bt:
            bench = (float(kline['收盘'].iloc[-1]) / float(kline['收盘'].iloc[0]) - 1) * 100
            best = max(bt.items(), key=lambda x: x[1]['metrics']['夏普比率'])
            print(f"  基准(买入持有): {bench:.1f}%")
            print(f"  最优策略: {bt[best[0]]['name']} (夏普{best[1]['metrics']['夏普比率']:.2f} 超额{best[1]['metrics']['超额收益%']:+.1f}%)")
            for s, res in list(bt.items())[:5]:
                m = res['metrics']
                bar = '█' * int(max(m['总收益率%'], 0) / 15)
                print(f"  {res['name']:<12} {bar} {m['总收益率%']:.0f}%(超额{m['超额收益%']:+.0f}%)  夏普{m['夏普比率']:.2f}  回撤{m['最大回撤%']:.0f}%")
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
            emoji = '📈' if direction == '看涨' else '📉'
            print(f"  {emoji} 三模型一致{direction}  |  置信度{confidence:.0f}%  |  一致性:{agreement} ({votes})")
        elif agreement == "中":
            print(f"  ⚠️ 模型有分歧  |  投票: {direction}  |  置信度{confidence:.0f}%  |  一致性:中 ({votes})")
        else:
            print(f"  模型预测方向: {direction}  |  置信度{confidence:.0f}%  |  一致性:低 ({votes})")

        # 展示各模型细节
        for name, label in [("xgb","XGBoost"), ("rf","RandomForest"), ("lgb","LightGBM")]:
            m = models.get(name, {})
            if 'error' not in m and m.get('预测方向'):
                print(f"  {label}: {m.get('预测方向','')} 上涨{m.get('上涨概率',0)}%  |  准确率{m.get('准确率%',0)}%  |  AUC:{m.get('AUC',0):.3f}")
                if m.get('重要特征'):
                    tops = [f"{f['特征']}({f['重要性']:.3f})" for f in m['重要特征'][:3]]
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
        if 'error' not in macro:
            ind = macro.get('数据', {})
            print(f"  PMI: {ind.get('制造业PMI','N/A')}  |  M2: {ind.get('M2同比%','N/A')}%")
            print(f"  信号: {' | '.join(macro.get('信号',[]))}")
            print(f"  整体: {macro.get('整体','N/A')}")
    except Exception:
        pass

    print(f"\n{'='*W}")


def cmd_enhanced_scan(args):
    """增强选股 — 板块过滤+短线信号+ML预测+自定义因子"""
    from stock_analyzer.enhanced_screener import enhanced_scan

    W = 60
    print(f"{'='*W}")
    print(f"增强选股: mode={args.mode} top_n={args.top_n} "
          f"板块TOP{args.sector_top_n} 价格{args.min_price}-{args.max_price} 振幅>{args.min_amplitude}%")
    print(f"{'='*W}")

    df = enhanced_scan(
        top_n=args.top_n, mode=args.mode,
        sector_top_n=args.sector_top_n,
        min_price=args.min_price, max_price=args.max_price,
        min_amplitude=args.min_amplitude,
        use_ml=not args.no_ml,
        use_custom_factors=not args.no_custom_factors,
        min_score=args.min_score,
    )

    if df.empty:
        print("无符合条件的股票")
        return

    print(f"\n{'='*W}")
    print(f"  选股结果 TOP{args.top_n}")
    print(f"{'='*W}")
    cols = ["排名", "code", "name", "板块", "composite_score", "短线评分", "组合信号强度",
            "ml_direction", "ml_confidence", "price", "change_pct", "amplitude"]
    show = [c for c in cols if c in df.columns]
    print(df[show].to_string(index=False))

    if args.output:
        df.to_csv(args.output, index=False, encoding="utf-8-sig")
        print(f"\n已保存: {args.output}")
    else:
        import os
        today = datetime.now().strftime("%Y%m%d_%H%M")
        path = os.path.join("reports", f"enhanced_scan_{today}.csv")
        os.makedirs("reports", exist_ok=True)
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"\n已保存: {path}")


def cmd_overnight_scan(args):
    """一夜持股法：尾盘六步选股"""
    from stock_analyzer.overnight_holding import run_overnight_scan

    results = run_overnight_scan(top_n=args.top_n, verbose=not args.quiet)

    if not results:
        print("\n今日无一夜持股候选，建议空仓观望。")
        return

    # 保存结果
    import os
    today = datetime.now().strftime("%Y%m%d_%H%M")
    path = os.path.join("reports", f"overnight_{today}.csv")
    os.makedirs("reports", exist_ok=True)
    import pandas as pd
    df = pd.DataFrame(results)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"\n已保存: {path}")


def cmd_overnight_sell(args):
    """隔夜持仓早盘卖出检查"""
    from stock_analyzer.overnight_holding import overnight_sell_check

    positions = []
    for arg in args.codes:
        parts = arg.split("=")
        if len(parts) == 2:
            code = parts[0].strip()
            cost = float(parts[1])
            positions.append({'代码': code, '成本': cost})

    if not positions:
        print("用法: python cli.py overnight-sell 600066=33.20 000001=24.50")
        return

    overnight_sell_check(positions)


def cmd_analyze(args):
    """个股/持仓深度分析"""
    if args.owned:
        owned = load_owned_stocks()
        codes = list(owned.keys())
        costs = {c: d.get('cost', 0) for c, d in owned.items()}
    else:
        codes = args.codes
        costs = {}

    if not codes:
        print("请指定股票代码或使用 --owned")
        return

    results = {}
    for code in codes:
        if args.ultimate:
            from stock_analyzer.ultimate_report import ultimate_analysis
            ultimate_analysis(code)
        elif args.full:
            _print_full_analysis(code, args.days, fast=args.fast)
        elif args.fast:
            _print_full_analysis(code, args.days, fast=True)
        else:
            print(f"\n分析 {code}...")
            r = deep_analyze(code, days=args.days)
            if r:
                if code in costs:
                    r['cost'] = costs[code]
                    r['pnl'] = round((r['price'] / r['cost'] - 1) * 100, 2)
                results[code] = r
                _print_stock_analysis(r)

    if args.output and results:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n结果已保存: {args.output}")


def cmd_report(args):
    """生成报告"""
    if args.type == 'eod':
        print("生成收盘复盘报告...")
        from stock_analyzer.cache import cached_kline
        from stock_analyzer.analysis import full_technical_analysis
        from stock_analyzer.quant import composite_quant_score, calc_risk_metrics, \
            generate_all_signals, consolidate_signals, evaluate_trading_style

        owned = load_owned_stocks()
        print(f"{'='*60}")
        print(f"{datetime.now().strftime('%Y-%m-%d')} 收盘复盘")
        print(f"{'='*60}")

        for code, info in owned.items():
            r = deep_analyze(code, days=365)
            if r:
                r['name'] = info.get('name', '')
                r['cost'] = info.get('cost', 0)
                pnl = (r['price'] / r['cost'] - 1) * 100
                status = "🟢" if pnl > 0 else "🔴"
                print(f"  {status} {code} {r['name']}: 浮盈{pnl:+.2f}% | "
                      f"MACD:{r['macd_signal']} | RSI:{r['rsi']:.0f} | "
                      f"止损:{r['stop_loss']:.2f}")

    elif args.type == 'sector':
        print("生成板块分析报告...")
        from stock_analyzer.sector_report import generate_sector_report
        path = generate_sector_report()
        print(f"报告: {path}")

    elif args.type == 'portfolio':
        print("投资组合报告功能待实现")

    if args.output:
        print(f"输出: {args.output}")


def cmd_check(args):
    """持仓/预警/大盘检查"""
    if args.market or (not args.owned and not args.alerts):
        print("大盘指数:")
        from stock_analyzer.fetcher import get_market_overview
        mkt = get_market_overview()
        for code, info in mkt.items():
            print(f"  {info['名称']}: {info['最新价']:.2f} "
                  f"({info['涨跌幅']:+.2f}%)")

        # 市场消息摘要
        print("\n今日市场消息:")
        try:
            from stock_analyzer.fetcher import get_market_news_digest
            digest = get_market_news_digest()
            print(f"  {digest['summary']}")
            if digest['hot_sectors']:
                print(f"  热门板块: {'、'.join(digest['hot_sectors'])}")
            if digest['news_count']:
                print(f"  要闻数量: {digest['news_count']} 条  情绪: {digest['sentiment']}")
        except Exception:
            print("  (消息获取失败)")

    if args.owned:
        print("\n持仓状态:")
        owned = load_owned_stocks()
        if owned:
            from stock_analyzer.fetcher import sina_real_time
            codes = list(owned.keys())
            rt = sina_real_time(codes)
            for code, info in owned.items():
                rtp = rt.get(code, {})
                price = float(rtp.get('最新价', 0)) if rtp else 0
                if price:
                    pnl = (price / info.get('cost', price) - 1) * 100
                    name = rtp.get('名称', info.get('name', ''))
                    print(f"  {code} {name}: "
                          f"成本{info.get('cost',0):.2f} → 现价{price:.2f} "
                          f"浮盈{pnl:+.2f}%")
                else:
                    print(f"  {code} {info.get('name','')}: 实时价获取失败")

    if args.alerts:
        print("\n预警检查:")
        try:
            from stock_analyzer.alert import run_all_alerts
            run_all_alerts()
        except Exception as e:
            print(f"  预警检查失败: {e}")

    if args.limit:
        print("\n涨跌停统计:")
        try:
            from stock_analyzer.fetcher import get_limit_up_down
            lz = get_limit_up_down()
            print(f"  涨停: {lz['up_count']} 只  跌停: {lz['down_count']} 只")
            if lz['up']:
                ups = [f"{s['name']}({s['change']:+.1f}%)" for s in lz['up'][:10]]
                print(f"  涨停示例: {'、'.join(ups)}")
            if lz['down']:
                downs = [f"{s['name']}({s['change']:+.1f}%)" for s in lz['down'][:5]]
                print(f"  跌停示例: {'、'.join(downs)}")
        except Exception as e:
            print(f"  涨跌停数据获取失败: {e}")

    if args.rotation:
        print("\n板块轮动分析:")
        try:
            from stock_analyzer.fetcher import get_sector_rotation
            rot = get_sector_rotation()
            print(f"  {rot['message']}")
            if rot['top5_now']:
                print("  板块排名 Top5:")
                for i, s in enumerate(rot['top5_now']):
                    print(f"    {i+1}. {s['name']}: {s['avg_score']}分")
        except Exception as e:
            print(f"  板块分析失败: {e}")

    if args.network:
        print("\n网络健康检测:")
        from stock_analyzer.network_health import print_health
        print_health()

    if args.premarket:
        _cmd_premarket_check()

    if args.update_kline:
        print("\n更新今日K线...")
        owned = load_owned_stocks()
        from stock_analyzer.cache import cached_kline
        for code in owned:
            k = cached_kline(code, days=5)
            last = str(k['日期'].iloc[-1])[:10] if not k.empty else '?'
            print(f"  {code}: {len(k)}天, 最新={last}")
        print("完成")

    if args.lhb:
        try:
            from stock_analyzer.fetcher import get_dragon_tiger_board
            df = get_dragon_tiger_board()
            if not df.empty:
                print(f"  上榜股票: {len(df)} 条记录")
            else:
                print("  无龙虎榜数据（可能非交易日）")
        except Exception as e:
            print(f"  龙虎榜获取失败: {e}")

    if args.rs:
        print("\n相对强弱分析:")
        try:
            from stock_analyzer.fetcher import calc_relative_strength
            if args.rs == "all":
                owned = load_owned_stocks()
                codes = list(owned.keys())
            else:
                codes = [args.rs]
            for code in codes:
                rs = calc_relative_strength(code)
                print(f"  {code}: 个股{rs['stock_return']:+.1f}%  大盘{rs['index_return']:+.1f}%  "
                      f"RS: {rs['rs_value']:+.1f}  {rs['trend']}")
        except Exception as e:
            print(f"  相对强弱计算失败: {e}")


def cmd_config(args):
    """配置管理"""
    if args.action == 'show':
        from stock_analyzer.config import (MA_WINDOWS, MACD_FAST, MACD_SLOW, MACD_SIGNAL,
                                            RSI_PERIOD, TRADING_DAYS_PER_YEAR, RISK_FREE_RATE,
                                            QUANT_FACTOR_WEIGHTS)
        print("当前配置:")
        print(f"  均线周期: {MA_WINDOWS}")
        print(f"  MACD: ({MACD_FAST}, {MACD_SLOW}, {MACD_SIGNAL})")
        print(f"  RSI周期: {RSI_PERIOD}")
        print(f"  年交易日: {TRADING_DAYS_PER_YEAR}")
        print(f"  无风险利率: {RISK_FREE_RATE}")
        print(f"  因子权重: {QUANT_FACTOR_WEIGHTS}")
    elif args.action == 'init':
        import json
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        default_config = {
            "TRADING_DAYS_PER_YEAR": 252,
            "RISK_FREE_RATE": 0.03,
            "QUANT_FACTOR_WEIGHTS": {
                "momentum": 0.21, "technical": 0.21, "fundamental": 0.17,
                "volume": 0.10, "risk": 0.11, "sentiment": 0.10, "fund_flow": 0.10,
            },
            "SHORT_TERM_WEIGHTS": {
                "momentum": 0.20, "volume": 0.15, "volatility": 0.15,
                "combo_signal": 0.25, "resonance": 0.15, "position": 0.10,
            },
            "ALERT": {"stop_loss_pct": -8, "take_profit_pct": 15, "review_days": 5},
            "SCAN": {"default_top_n": 30, "min_score": 50, "max_n20_chg": 30},
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)
        print(f"默认配置已生成: {config_path}")


def cmd_history(args):
    """历史评分查询"""
    from stock_analyzer.history_db import (
        get_stock_history, get_top_stocks, get_market_summary, get_available_dates
    )

    if args.dates:
        dates = get_available_dates()
        print(f"可用日期 ({len(dates)} 天):")
        for d in dates:
            print(f"  {d}")
        return

    if args.summary:
        s = get_market_summary(args.date)
        if s:
            print(f"\n{'='*50}")
            print(f"全市场评分分布 — {s['date']}")
            print(f"{'='*50}")
            print(f"总计: {s['total']} 只  均分: {s['avg_score']}")
            print(f"优秀(≥80): {s['excellent']} 只 ({s['excellent']/s['total']*100:.1f}%)" if s['total'] else "")
            print(f"良好(60-79): {s['good']} 只 ({s['good']/s['total']*100:.1f}%)" if s['total'] else "")
            print(f"中等(40-59): {s['medium']} 只 ({s['medium']/s['total']*100:.1f}%)" if s['total'] else "")
            print(f"偏低(<40): {s['low']} 只 ({s['low']/s['total']*100:.1f}%)" if s['total'] else "")
        else:
            print("暂无历史数据，请先运行一次全市场扫描")
        return

    if args.code:
        df = get_stock_history(args.code, days=30)
        if df.empty:
            print(f"未找到 {args.code} 的历史数据")
        else:
            print(f"\n{args.code} 近{len(df)}日评分趋势:")
            print(f"{'日期':<12} {'综合':<7} {'动量':<6} {'技术':<6} {'基本面':<6} {'量能':<6} {'风险':<6} {'价格':<8}")
            print("-" * 65)
            for _, r in df.iterrows():
                print(f"{r['date']:<12} {r['composite_score']:<7.1f} {r['momentum_score']:<6.0f} "
                      f"{r['technical_score']:<6.0f} {r['fundamental_score']:<6.0f} "
                      f"{r['volume_score']:<6.0f} {r['risk_score']:<6.0f} {r['price']:<8.2f}")
        return

    # 默认: 显示最新日期的Top N
    df = get_top_stocks(args.date, top_n=args.top)
    if df.empty:
        print("暂无历史数据")
    else:
        date = df['date'].iloc[0]
        print(f"\n{date} Top {len(df)}:")
        print(f"{'#':<4} {'代码':<8} {'名称':<8} {'综合':<7} {'动量':<6} {'技术':<6} {'基本面':<6} {'价格':<8}")
        print("-" * 65)
        for i, (_, r) in enumerate(df.iterrows()):
            print(f"{i+1:<4} {r['code']:<8} {r['name']:<8} {r['composite_score']:<7.1f} "
                  f"{r['momentum_score']:<6.0f} {r['technical_score']:<6.0f} "
                  f"{r['fundamental_score']:<6.0f} {r['price']:<8.2f}")


def cmd_audit(args):
    """系统自审计"""
    from stock_analyzer.self_audit import run_audit
    report = run_audit(auto_fix=not args.no_fix, verbose=True)
    return 1 if report.has_issues() else 0


def cmd_clean(args):
    """清理归档"""
    import glob
    patterns = [
        'deep_analysis_*.json', 'final_5_analysis*.json', 'short_term_*_analysis.json',
        'rational_*.json', 'sector_copper_result.json', 'candidate_pool_*.csv',
        'screener_*.csv', 'deep_dive_*.json',
    ]
    archive_dir = 'archive'
    files_to_move = []
    for pat in patterns:
        files_to_move.extend(glob.glob(pat))

    if args.dry_run:
        print(f"将归档 {len(files_to_move)} 个文件到 {archive_dir}/:")
        for f in sorted(files_to_move):
            print(f"  {f}")
    else:
        os.makedirs(archive_dir, exist_ok=True)
        for f in files_to_move:
            dst = os.path.join(archive_dir, f)
            os.rename(f, dst)
        print(f"已归档 {len(files_to_move)} 个文件到 {archive_dir}/")


# ── 辅助 ──────────────────────────────────────────

_CHECKPOINT_FILE = '.scan_progress'


def _save_checkpoint_single(code):
    """追加一只股票到 checkpoint（立即刷盘，崩溃最多丢 1 只）"""
    with open(_CHECKPOINT_FILE, 'a') as f:
        f.write(code + '\n')
        f.flush()
        os.fsync(f.fileno())


def _load_checkpoint():
    """读取已完成股票集合"""
    if os.path.exists(_CHECKPOINT_FILE):
        with open(_CHECKPOINT_FILE, 'r') as f:
            return {line.strip() for line in f if line.strip()}
    return set()


def _clear_checkpoint():
    """扫描完成，清除断点文件"""
    if os.path.exists(_CHECKPOINT_FILE):
        os.remove(_CHECKPOINT_FILE)


def _print_stock_analysis(r):
    """打印单只股票分析结果"""
    pnl_str = f" 浮盈: {r.get('pnl', 0):+.2f}%" if 'pnl' in r else ""
    print(f"  💰 价格: {r['price']:.2f}{pnl_str}")
    print(f"  📊 综合评分: {r['qs_composite']:.0f} ({r['qs_rating']})")
    print(f"  📈 近5日: {r['near_5d']:+.1f}% | 近20日: {r['near_20d']:+.1f}% | RSI: {r['rsi']:.0f}")
    print(f"  📉 MACD: {r['macd_signal']} | KDJ: {r['kdj_signal']}")
    print(f"  🎯 因子: 动量{r['mom_s']:.0f} 技术{r['tech_s']:.0f} 基本面{r['fund_s']:.0f} "
          f"量能{r['vol_s']:.0f} 风险{r['risk_s']:.0f}")
    print(f"  ⚡ 夏普: {r['sharpe']:.2f} | 回撤: {r['max_dd']:.1f}%")
    print(f"  🛡️ 止损: {r['stop_loss']:.2f} | 止盈: {r['stop_profit']:.2f}")
    nt = f"🏛️ {', '.join(r['nt_holders'][:2])}" if r['has_nt'] else "无"
    print(f"  🏛️ 国家队: {nt}")
    print(f"  🏷️ 风格: {r['style']} | 短线{r['short_score']:.0f}分 | 长线{r['long_score']:.0f}分")


# ── main ──────────────────────────────────────────

def cmd_advanced(args):
    """高级分析入口"""
    print("=" * 60)
    print("高级分析")
    print("=" * 60)

    if args.all:
        args.lhb = args.north = args.margin = args.macro = True

    # 龙虎榜
    if args.lhb:
        print("\n--- 龙虎榜 ---")
        from stock_analyzer.advanced import analyze_lhb_today
        result = analyze_lhb_today()
        if "error" in result:
            print(f"  {result['error']}")
        else:
            print(f"  上榜: {result['上榜数量']} 只")
            top = result.get("净买入TOP10", [])[:5]
            if top:
                print(f"  {'代码':<8} {'名称':<8} {'净买额(万)':<12} {'涨幅':<8}")
                for r in top:
                    print(f"  {r.get('代码',''):<8} {r.get('名称',''):<8} {r.get('净买额',0):<12.0f} {r.get('涨幅',0):<8}%")

    # 北向资金
    if args.north:
        print("\n--- 北向资金 ---")
        from stock_analyzer.advanced import north_flow_signal
        result = north_flow_signal()
        if "error" in result:
            print(f"  {result['error']}")
        else:
            for k, v in result.items():
                print(f"  {k}: 净买额 {v.get('净买额(亿)', 0):.1f}亿")

    # 融资融券
    if args.margin:
        print("\n--- 融资融券 ---")
        from stock_analyzer.advanced import get_margin_summary
        result = get_margin_summary()
        if result:
            for mkt, data in result.items():
                print(f"  {mkt}: 融资{data.get('融资余额(亿)',0):.0f}亿 融券{data.get('融券余额(亿)',0):.0f}亿")
        else:
            print("  数据获取失败")

    # 高管增减持
    if args.insider:
        print("\n--- 高管增减持 ---")
        from stock_analyzer.advanced import get_insider_trades, insider_signal
        code = None if args.insider == "all" else args.insider
        if code:
            sig = insider_signal(code)
            print(f"  {code}: {sig['signal']} ({sig['records']}笔)")
        else:
            df = get_insider_trades()
            if not df.empty:
                print(f"  近30日: {len(df)} 笔变动")
            else:
                print("  数据获取失败")

    # 机构调研
    if args.visit:
        print("\n--- 机构调研 ---")
        from stock_analyzer.advanced import get_institution_visits, most_visited_stocks
        code = None if args.visit in ("top", "all") else args.visit
        if code:
            df = get_institution_visits(code)
            print(f"  {code}: {len(df)} 次调研")
        else:
            top = most_visited_stocks()
            if not top.empty:
                print(f"  热门调研TOP10:")
                for _, r in top.head(10).iterrows():
                    code_val = r.get("证券代码", r.iloc[0])
                    count = r.get("调研次数", r.iloc[1]) if len(r) > 1 else "?"
                    print(f"    {code_val}  调研{count}次")
            else:
                print("  数据获取失败")

    # 财报
    if args.financial:
        print(f"\n--- 财报深度拆解: {args.financial} ---")
        from stock_analyzer.advanced import analyze_profit_quality
        result = analyze_profit_quality(args.financial)
        if "error" in result:
            print(f"  {result['error']}")
        else:
            for k, v in result.items():
                if k != "代码":
                    print(f"  {k}: {v}")

    # 宏观
    if args.macro:
        print("\n--- 宏观指标 ---")
        from stock_analyzer.advanced import macro_market_signal
        result = macro_market_signal()
        if "error" in result:
            print(f"  {result['error']}")
        else:
            ind = result.get("数据", {})
            print(f"  PMI: {ind.get('制造业PMI', 'N/A')} | CPI: {ind.get('CPI同比%', 'N/A')}%")
            print(f"  M2: {ind.get('M2同比%', 'N/A')}% | 社融: {ind.get('社融增量(亿)', 'N/A')}亿")
            sigs = result.get("信号", [])
            if sigs:
                print(f"  信号: {' | '.join(sigs)}")
            print(f"  整体: {result.get('整体', 'N/A')}")


def cmd_backtest(args):
    """策略回测"""
    from stock_analyzer.cache import cached_kline
    from stock_analyzer.backtest import (run_backtest, compare_strategies, optimize_strategy,
                                          STRATEGIES, DEFAULT_COMPARE_STRATEGIES, export_backtest_json)

    print(f"加载 {args.code} K线数据...")
    kline = cached_kline(args.code, days=args.days)
    if kline.empty or len(kline) < 60:
        print("K线数据不足（至少60天）")
        return

    print(f"数据: {len(kline)} 天  |  初始资金: {args.capital:,}  |  "
          f"手续费: {args.commission:.4f}  |  滑点: {args.slippage:.3f}")

    bt_kwargs = dict(initial_capital=args.capital, commission=args.commission,
                     slippage=args.slippage, position_pct=args.position_pct,
                     stop_loss=args.stop_loss, take_profit=args.take_profit,
                     trailing_stop=args.trailing_stop)

    if args.compare:
        strat_list = None
        if args.strategies:
            strat_list = [s.strip() for s in args.strategies.split(",")]
        print(f"\n{'='*70}")
        print(f"多策略对比回测 ({len(strat_list or DEFAULT_COMPARE_STRATEGIES)}个策略)")
        print(f"{'='*70}")
        results = compare_strategies(kline, strat_list, **bt_kwargs)
        if not results:
            print("所有策略均无有效信号")
            return
        # 基准收益
        bench = (float(kline['收盘'].iloc[-1]) / float(kline['收盘'].iloc[0]) - 1) * 100
        print(f"  基准(买入持有): {bench:.1f}%")
        header = f"{'策略':<16} {'收益率%':<10} {'超额%':<8} {'夏普':<8} {'索提诺':<8} {'卡玛':<8} {'回撤%':<8} {'交易':<6}"
        print(header)
        print("-" * len(header))
        for s_name, r in results.items():
            m = r['metrics']
            print(f"{r['name']:<16} {m['总收益率%']:<10.1f} {m['超额收益%']:<8.1f} "
                  f"{m['夏普比率']:<8.2f} {m['索提诺比率']:<8.2f} {m['卡玛比率']:<8.2f} "
                  f"{m['最大回撤%']:<8.1f} {m['交易次数']:<6}")
        best = max(results.items(), key=lambda x: x[1]['metrics']['夏普比率'])
        print(f"\n最优: {best[1]['name']} (夏普{best[1]['metrics']['夏普比率']:.2f})")

        if args.output:
            export_backtest_json({'metrics': {s: r['metrics'] for s, r in results.items()},
                                  'trades': [], 'equity_curve': [],
                                  'summary': f"{len(results)}个策略对比"},
                                 args.output)
            print(f"结果已导出: {args.output}")

    elif args.optimize:
        print(f"\n参数优化: {STRATEGIES[args.strategy]['name']}")
        best = optimize_strategy(kline, args.strategy)
        if best:
            print(f"最优参数: {best['params']}")
            m = best['metrics']
            print(f"  样本内({best.get('train_days','?')}天): "
                  f"收益率{m['总收益率%']:.1f}%  夏普{m['夏普比率']:.2f}  "
                  f"回撤{m['最大回撤%']:.1f}%")
            if 'test_metrics' in best:
                tm = best['test_metrics']
                print(f"  样本外({best.get('test_days','?')}天): "
                      f"收益率{tm['总收益率%']:.1f}%  夏普{tm['夏普比率']:.2f}  "
                      f"回撤{tm['最大回撤%']:.1f}%")
                oos_diff = tm['总收益率%'] - m['总收益率%']
                warn = " ⚠️过拟合" if abs(oos_diff) > 20 else ""
                print(f"  样本内外收益差: {oos_diff:+.1f}%{warn}")
        else:
            print("优化失败，无法生成有效信号")

    else:
        s_info = STRATEGIES[args.strategy]
        print(f"\n策略: {s_info['name']}  参数: {s_info['default']}")
        result = run_backtest(kline, s_info['fn'], s_info['default'], **bt_kwargs)
        if result:
            m = result['metrics']
            print(f"{'='*55}")
            print(f"收益率: {m['总收益率%']:.1f}%  年化: {m['年化收益率%']:.1f}%")
            print(f"夏普: {m['夏普比率']:.2f}  索提诺: {m['索提诺比率']:.2f}  卡玛: {m['卡玛比率']:.2f}")
            print(f"回撤: {m['最大回撤%']:.1f}%  胜率: {m['胜率%']:.0f}%  交易: {m['交易次数']}次  盈亏比: {m['盈亏比']:.2f}")
            print(f"基准(买入持有): {m['基准收益%']:.1f}%  超额收益: {m['超额收益%']:+.1f}%")
            print(f"最终资金: {m['最终资金']:,.0f}")
            if result['trades']:
                print(f"\n最近5笔交易:")
                for t in result['trades'][-5:]:
                    pnl = f" 盈亏{t['pnl']:+.0f}" if 'pnl' in t else ""
                    reason = f" [{t.get('exit_reason','')}]" if t.get('exit_reason') and t['action'] == 'SELL' else ""
                    print(f"  {t['date']} {t['action']} @{t['price']}{pnl}{reason}")

            if args.output:
                export_backtest_json(result, args.output)
                print(f"\n结果已导出: {args.output}")
        else:
            print("回测失败，无法生成有效信号")


def cmd_ml(args):
    """机器学习预测"""
    from stock_analyzer.cache import cached_kline, cached_fundamentals
    from stock_analyzer.ml_predict import predict_direction, predict_return, ml_enhanced_score

    print(f"加载 {args.code} 数据...")
    kline = cached_kline(args.code, days=365)
    if kline.empty or len(kline) < 60:
        print("K线数据不足（至少60天）")
        return

    funds = cached_fundamentals(args.code)

    if args.predict_return:
        print(f"\n{'='*50}")
        print(f"涨跌幅预测: {args.code}")
        print(f"{'='*50}")
        result = predict_return(kline, funds)
        _print_ml_result(result)

    elif args.enhance:
        print(f"\n{'='*50}")
        print(f"ML增强评分: {args.code}")
        print(f"{'='*50}")
        result = ml_enhanced_score(kline, funds)
        _print_ml_result(result)

    else:  # 默认方向预测
        print(f"\n{'='*50}")
        print(f"涨跌方向预测: {args.code}")
        print(f"{'='*50}")
        result = predict_direction(kline, funds)
        _print_ml_result(result)


def _print_ml_result(result):
    if "error" in result:
        print(f"  {result['error']}")
        return
    for k, v in result.items():
        if k == '重要特征':
            print(f"  {k}:")
            for f in v:
                print(f"    {f['特征']}: {f['重要性']:.4f}")
        else:
            print(f"  {k}: {v}")


def cmd_quality(args):
    """公司质地七问 — 商业模式+护城河+现金流+生命周期+估值+事件"""
    from stock_analyzer.business_quality import full_business_quality

    print(f"\n{'='*60}")
    print(f"  公司质地七问: {args.code}")
    print(f"{'='*60}")

    r = full_business_quality(args.code)

    print(f"\n{'─'*40}")
    print(f"  综合评分: {r['overall_score']} → {r['overall_level']}")
    print(f"{'─'*40}")

    # Q1
    p = r['company_profile']
    print(f"\n【Q1 公司靠什么赚钱】")
    if p.get('main_business'):
        print(f"  主营业务: {p['main_business'][:100]}")
    print(f"  行业: {p['industry']}")
    if p.get('listing_date'):
        print(f"  上市时间: {p['listing_date']}")

    # Q2
    m = r['moat']
    print(f"\n【Q2 护城河 — 凭什么别人抢不了】")
    print(f"  评分: {m['score']}/100 → {m['level']}")
    for s in m['signals']:
        print(f"  • {s}")
    print(f"  {m['assessment'][:120]}")

    # Q3
    cf = r['cash_flow']
    print(f"\n【Q3 现金流 — 到底赚的是真钱还是纸面利润】")
    print(f"  质量: {cf['quality']}")
    if cf['operating_cf_yi']:
        print(f"  经营CF: {cf['operating_cf_yi']}亿 | 投资CF: {cf['investing_cf_yi']}亿 | 融资CF: {cf['financing_cf_yi']}亿")
        print(f"  自由现金流: {cf['free_cf_yi']}亿")
    print(f"  {cf['assessment']}")

    # Q4
    lc = r['lifecycle']
    print(f"\n【Q4 生命周期 — 公司现在什么阶段】")
    print(f"  阶段: {lc['stage_cn']} (置信度{lc['confidence']}%)")
    for s in lc['signals']:
        print(f"  • {s}")
    if not args.short:
        print(f"  建议: {lc['suggestion']}")

    # Q5
    v = r['valuation']
    print(f"\n【Q5 估值 — 股价贵不贵】")
    print(f"  评分: {v['score']}/100 → {v['level']}")
    print(f"  PE={v['pe']} | PB={v['pb']} | PEG={v['peg']}")
    for s in v['signals'][:3]:
        print(f"  • {s}")

    # Q6 — 跳过，已有技术面
    print(f"\n【Q6 近期表现】→ 请使用 python cli.py analyze {args.code} --full 查看技术面分析")

    # Q7
    e = r['events']
    print(f"\n【Q7 近期大事】")
    if e['events']:
        for ev in e['events'][:5]:
            print(f"  [{ev['type']}] {ev['date']} {ev['title'][:60]}")
    else:
        print(f"  {e['assessment']}")

    print(f"\n{'─'*40}")
    print(f"  综合评估: {r['assessment_summary'][:150]}")
    print(f"{'─'*40}\n")


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    dispatch = {
        'scan': cmd_scan,
        'enhanced-scan': cmd_enhanced_scan,
        'overnight-scan': cmd_overnight_scan,
        'overnight-sell': cmd_overnight_sell,
        'analyze': cmd_analyze,
        'report': cmd_report,
        'check': cmd_check,
        'config': cmd_config,
        'history': cmd_history,
        'clean': cmd_clean,
        'audit': cmd_audit,
        'advanced': cmd_advanced,
        'backtest': cmd_backtest,
        'ml': cmd_ml,
        'quality': cmd_quality,
    }
    dispatch[args.command](args)


if __name__ == '__main__':
    main()
