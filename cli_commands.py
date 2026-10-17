"""CLI 命令实现层 —— 各子命令处理函数（原样搬移自 cli.py）

依赖：cli_core（deep_analyze/检查点/清理等共享件）；由 cli.py 薄入口 import。
"""

import json
import os
import time
from datetime import datetime
from cli_core import (
    _SCAN_DIR,
    _cleanup_old_logs,
    _clear_checkpoint,
    _fail_on_skip_ratio,
    _json_default,
    _load_checkpoint,
    _print_full_analysis,
    _print_stock_analysis,
    _save_checkpoint_single,
    deep_analyze,
    load_owned_stocks,
)


def _cmd_premarket_check():
    """开盘前全面自检：网络→数据库→数据源→API 一键检测"""
    import os
    import sqlite3
    import time
    from datetime import datetime

    W = 60
    print(f"\n{'=' * W}")
    print(f"  StockInsight 开盘前自检 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'=' * W}")

    results = {"pass": 0, "warn": 0, "fail": 0}

    def check(name, ok, detail=""):
        if ok:
            results["pass"] += 1
            print(f"  ✅ {name}: {detail}")
        else:
            results["fail"] += 1
            print(f"  ❌ {name}: {detail}")

    # 1. 网络健康
    print("\n── 1. 网络健康 ──")
    try:
        from stock_analyzer.network_health import check_all

        health = check_all()
        for src_name, label in [("sina", "新浪"), ("tencent", "腾讯"), ("eastmoney", "东方财富")]:
            s = getattr(health, src_name, None)
            if s:
                avail = s.available
                lat = s.latency_ms
                if avail:
                    check(label, True, f"{lat:.0f}ms")
                else:
                    check(label, False, "不可达" if lat > 5000 else f"{lat:.0f}ms")
        # Baostock
        try:
            import baostock as bs

            lg = bs.login()
            check(
                "Baostock",
                lg.error_code == "0",
                "本地库可用" if lg.error_code == "0" else lg.error_msg,
            )
            bs.logout()
        except Exception:
            check("Baostock", False, "未安装")
        # 模式
        print(f"  最优K线源: {health.best_kline_source}")
        print(f"  模式: {health.mode.upper()}")
    except Exception as e:
        check("网络健康检测", False, str(e))

    # 2. 数据库
    print("\n── 2. 数据库 ──")
    try:
        from stock_analyzer.config import DB_PATH

        if os.path.exists(DB_PATH):
            size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
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
    print("\n── 3. 实时行情 ──")
    try:
        t0 = time.time()
        from stock_analyzer.fetcher import sina_real_time

        rt = sina_real_time(["000001", "399001"])
        lat = (time.time() - t0) * 1000
        if rt and len(rt) >= 1:
            check("新浪实时行情", True, f"{lat:.0f}ms ({len(rt)}只)")
        else:
            check("新浪实时行情", False, "返回空")
    except Exception as e:
        check("新浪实时行情", False, str(e))

    # 4. 资金流向
    print("\n── 4. 资金流向 ──")
    try:
        t0 = time.time()
        from stock_analyzer.fetcher import get_fund_flow

        ff = get_fund_flow("000001", days=5)
        lat = (time.time() - t0) * 1000
        if ff is not None and not ff.empty:
            check("东方财富资金流向", True, f"{lat:.0f}ms")
        else:
            now_h = datetime.now().hour
            if now_h < 15:
                print("  ⚠️ 东方财富资金流向: 盘中无数据，盘后T+1发布 (正常)")
            else:
                check("东方财富资金流向", False, "盘后仍无数据，可能API异常")
    except Exception as e:
        check("东方财富资金流向", False, str(e)[:60])

    # 5. 板块
    print("\n── 5. 板块数据 ──")
    try:
        from stock_analyzer.fetcher import get_sectors

        sectors = get_sectors()
        has_sectors = (isinstance(sectors, dict) and len(sectors) > 0) or (
            hasattr(sectors, "empty") and not sectors.empty
        )
        if has_sectors:
            check("板块分类", True, f"{len(sectors)}个板块")
        else:
            check("板块分类", False, "返回空，将用静态兜底")
    except Exception as e:
        check("板块分类", False, str(e)[:60])

    # 总结
    print(f"\n{'=' * W}")
    total = results["pass"] + results["warn"] + results["fail"]
    print(f"  自检完成: ✅{results['pass']} ⚠️{results['warn']} ❌{results['fail']} / {total}")
    if results["fail"] == 0:
        print("  结论: 🟢 系统就绪，可以正常使用")
    elif results["fail"] <= 2:
        print("  结论: 🟡 部分数据源不可用，基本功能正常")
    else:
        print("  结论: 🔴 多个数据源故障，建议等待恢复后重试")
    print(f"{'=' * W}\n")


def cmd_scan(args):
    """执行全市场/主板扫描"""
    from stock_analyzer.screener import (
        SCAN_BOARD_PREFIXES,
        load_all_a_shares,
        quick_filter,
    )
    from stock_analyzer.trade_day import is_trading_day

    # 非交易日短路（08-24 根因修复）：周末/法定节假日收盘扫描时全 K 线源普遍离线，
    # 每只 fetch_kline 阻塞至 300s 熔断冷却，聚合超时 600s 被外层 timeout 杀掉(exit 124)。
    # 接 tushare_loader 交易日表精确判断（表缺失时 fallback 内置 2026 休市 + 周末），
    # 非交易日直接跳过，避免无效 API 调用 + 误报告警。交易日仍走完整路径。
    _now = datetime.now()
    if not is_trading_day(_now.date()):
        print(f"{'=' * 60}")
        print(f"⏸️  非交易日跳过扫描（{_now.strftime('%Y-%m-%d')}）")
        print("    行情源休市期间普遍离线，跳过以避免无效抓取与超时误报。下一交易日自动恢复。")
        print(f"{'=' * 60}")
        return 0

    print(f"{'=' * 60}")
    print(
        f"扫描模式: {'全A股' if args.mode == 'full' else '主板+创业板(60/00/30)'} | "
        f"最低评分: {args.min_score} | Top: {args.top_n}"
    )
    print(f"{'=' * 60}")

    # 加载股票池
    all_codes = load_all_a_shares()
    if args.mode == "mainboard":
        # 主板(60/00) + 创业板(300/301)；科创688/北交所8/920 不在内（见 SCAN_BOARD_PREFIXES）
        codes = [c for c in all_codes if c.startswith(SCAN_BOARD_PREFIXES)]
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
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from concurrent.futures import TimeoutError as FutureTimeout
    from threading import Lock

    from stock_analyzer.config import SCAN_WORKERS

    results = []
    total = len(codes)
    t0 = time.time()
    skipped = 0
    completed = 0
    _lock = Lock()
    # 失败原因聚合（2026-10-16 新增）：原实现把 analyze_one 的异常文本直接丢弃，
    # 导致 2699 只标的静默跳过、事后无法归因。
    err_reasons: dict[str, int] = {}

    def analyze_one(code):
        """单只分析（供线程池调用）"""
        try:
            r = deep_analyze(code, days=120, skip_nt=True)
            return ("ok", code, r)
        except Exception as e:
            return ("err", code, f"{type(e).__name__}: {e}")

    # 修复(2026-10-16)：原 `future.result(timeout=45)` 是**死代码** ——
    #   `as_completed()` 只产出已完成 future，对其调用 result(timeout=...) 永不超时，
    #   所谓「单项 45s 超时护栏」从未生效（历史日志 0 次命中），
    #   个别卡死任务会一路拖到外层 timeout(exit 124) 才被杀。
    # 改为对整个扫描加**硬性总预算**：超预算即取消未开始任务并明确报告，不再静默。
    try:
        scan_budget = float(os.environ.get("SCAN_TOTAL_BUDGET_SEC", "5400"))
        if scan_budget <= 0:
            scan_budget = 5400.0
    except ValueError:
        # 环境变量被写坏不应导致整轮扫描启动即崩，回退默认值
        print("  ⚠️ SCAN_TOTAL_BUDGET_SEC 非数字，已回退默认 5400s")
        scan_budget = 5400.0
    budget_hit = False

    with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as executor:
        futures = {executor.submit(analyze_one, c): c for c in codes}

        try:
            for future in as_completed(futures, timeout=scan_budget):
                code = futures[future]
                try:
                    status, _code, r = future.result()
                except Exception as e:
                    # 原实现此处静默 `continue`（异常变量未使用），失败无迹可查
                    with _lock:
                        skipped += 1
                        completed += 1
                        key = f"future:{type(e).__name__}"
                        err_reasons[key] = err_reasons.get(key, 0) + 1
                    continue

                with _lock:
                    completed += 1
                    if status == "ok" and r and r["qs_composite"] >= args.min_score:
                        results.append(r)
                    elif status == "err":
                        skipped += 1
                        key = str(r).split(":", 1)[0].strip() or "unknown"
                        err_reasons[key] = err_reasons.get(key, 0) + 1

                    # 进度报告
                    if completed % 50 == 0 or completed == total:
                        elapsed = time.time() - t0
                        rate = completed / elapsed if elapsed > 0 else 0
                        eta = (total - completed) / rate if rate > 0 else 0
                        pct = completed / total * 100
                        print(
                            f"  [{completed}/{total}] {pct:.0f}%  速率 {rate:.1f}只/s  "
                            f"ETA {eta / 60:.0f}min  结果 {len(results)}  跳过 {skipped}"
                        )

                # 断点写盘移出锁外（2026-10-17）：
                # 原在 `with _lock` 内逐只执行 open+write+flush+fsync，
                # 8 个 worker 必须串行排队等 fsync，临界区被磁盘 I/O 占满。
                # 迁出后不牺牲崩溃保证（仍逐只落盘），仅缩短锁持有时间。
                # 并发安全性：checkpoint 是「集合」语义（_load_checkpoint 读成 set），
                # 行序无关；"a" 模式 = O_APPEND，单次 7 字节 write() 原子更新偏移，
                # 并发追加不会交错拆行。
                _save_checkpoint_single(code)
        except FutureTimeout:
            budget_hit = True
            for fut in futures:
                fut.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            print(
                f"  ⏰ 扫描总预算 {scan_budget:.0f}s 耗尽，已取消未开始任务 "
                f"({completed}/{total} 已完成)"
            )

    if err_reasons:
        top_err = sorted(err_reasons.items(), key=lambda kv: -kv[1])[:5]
        print("  失败原因 Top: " + "；".join(f"{k}×{v}" for k, v in top_err))
    if budget_hit:
        print(f"  ⚠️ 本轮为预算截断结果（{completed}/{total}），达标数偏低属预期，勿据此判定市场。")

    # 失败率护栏（2026-10-17，P1-b 收口）
    # 依据：「达标数为 0」既可能是真失败也可能是合法行情（大跌日），
    #       不能据它判失败（会造成误告警，违反「告警价值=症状准×药方对」）；
    #       但「绝大多数标的连分析都没完成」一定是失败。
    # 口径：skipped/total ≥ 阈值（默认 0.9）→ 返回 1，让自动化
    #       「退出码非 0 = 异常」判定真正可用（P0-1 修复后管道已通）。
    if _fail_on_skip_ratio(skipped, total):
        print(f"  ❌ 失败/跳过 {skipped}/{total}（达到阈值），按失败退出（exit 1）")
        return 1

    # 排序输出
    results.sort(key=lambda x: x["qs_composite"], reverse=True)
    top = results[: args.top_n]

    print(f"\n{'=' * 60}")
    print(
        f"扫描完成: {len(results)} 只达标  跳过/失败: {skipped}  耗时 {((time.time() - t0) / 60):.0f}min"
    )
    print(f"{'=' * 60}")
    print(
        f"{'#':<4} {'代码':<8} {'板块':<10} {'综合':<7} {'近20日':<9} {'RSI':<5} {'MACD':<6} {'基本面':<6}"
    )
    print("-" * 72)
    for i, r in enumerate(top):
        from stock_analyzer.sector_info import get_stock_sector_full

        sect = get_stock_sector_full(r["code"])[:10]
        print(
            f"{i + 1:<4} {r['code']:<8} {sect:<10} {r['qs_composite']:<7.1f} "
            f"{r['near_20d']:<+9.1f} {r['rsi']:<5.0f} {r['macd_signal']:<6} {r['fund_s']:<6.0f}"
        )

    if not args.no_save:
        out = args.output or os.path.join(
            _SCAN_DIR, f"scan_{args.mode}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        )
        with open(out, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "scan_time": datetime.now().isoformat(),
                    "mode": args.mode,
                    "total": len(results),
                    "results": top,
                },
                f,
                ensure_ascii=False,
                indent=2,
                default=_json_default,
            )
        print(f"\n结果已保存: {out}")

    # 保留期清理（2026-10-13）：scan_*.json 每次扫描一个（~2.4MB）、
    # error_*.log 每日一个，均无保留策略 → logs/ 曾积压 128MB。
    # 默认保留 14 天（与 backend/logging_config.py 的 LOG_BACKUP 一致），
    # 可用 SCAN_LOG_KEEP_DAYS 覆盖；只删保留期外的旧文件，绝不动当次产物。
    try:
        removed = _cleanup_old_logs()
        if removed:
            print(f"日志清理: 移除 {len(removed)} 个超过保留期的旧文件")
    except Exception as e:  # noqa: BLE001 — 清理失败不应让扫描失败
        print(f"日志清理跳过: {e}")

    # 写入 daily_scores 数据库
    try:
        import pandas as pd

        from stock_analyzer.history_db import append_daily_results

        df = pd.DataFrame(
            [
                {
                    "代码": r["code"],
                    "名称": r.get("name", ""),
                    "综合评分": r["qs_composite"],
                    "评级": r["qs_rating"],
                    "动量分": r.get("mom_s", 0),
                    "技术分": r.get("tech_s", 0),
                    "基本面分": r.get("fund_s", 0),
                    "量能分": r.get("vol_s", 0),
                    "风险分": r.get("risk_s", 0),
                }
                for r in results
            ]
        )
        if not df.empty:
            n = append_daily_results(df, datetime.now().strftime("%Y-%m-%d"))
            print(f"已写入 daily_scores: {n} 条")
    except Exception as e:
        print(f"写入 daily_scores 失败: {e}")

    _clear_checkpoint()
    # 显式返回成功码（RET503）：与函数开头「非交易日 return 0」保持同一契约，
    # 并让 main() 的 sys.exit(...) 有确定值。
    return 0


def cmd_enhanced_scan(args):
    """增强选股 — 板块过滤+短线信号+ML预测+自定义因子"""
    from stock_analyzer.enhanced_screener import enhanced_scan

    W = 60
    print(f"{'=' * W}")
    print(
        f"增强选股: mode={args.mode} top_n={args.top_n} "
        f"板块TOP{args.sector_top_n} 价格{args.min_price}-{args.max_price} 振幅>{args.min_amplitude}%"
    )
    print(f"{'=' * W}")

    df = enhanced_scan(
        top_n=args.top_n,
        mode=args.mode,
        sector_top_n=args.sector_top_n,
        min_price=args.min_price,
        max_price=args.max_price,
        min_amplitude=args.min_amplitude,
        use_ml=not args.no_ml,
        use_custom_factors=not args.no_custom_factors,
        min_score=args.min_score,
    )

    if df.empty:
        print("无符合条件的股票")
        return

    print(f"\n{'=' * W}")
    print(f"  选股结果 TOP{args.top_n}")
    print(f"{'=' * W}")
    cols = [
        "排名",
        "code",
        "name",
        "板块",
        "composite_score",
        "短线评分",
        "组合信号强度",
        "ml_direction",
        "ml_confidence",
        "price",
        "change_pct",
        "amplitude",
    ]
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
            positions.append({"代码": code, "成本": cost})

    if not positions:
        print("用法: python cli.py overnight-sell 600066=33.20 000001=24.50")
        return

    overnight_sell_check(positions)


def cmd_analyze(args):
    """个股/持仓深度分析"""
    if args.owned:
        owned = load_owned_stocks()
        codes = list(owned.keys())
        costs = {c: d.get("cost", 0) for c, d in owned.items()}
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
                    r["cost"] = costs[code]
                    r["pnl"] = round((r["price"] / r["cost"] - 1) * 100, 2)
                results[code] = r
                _print_stock_analysis(r)

    if args.output and results:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n结果已保存: {args.output}")


def cmd_report(args):
    """生成报告"""
    if args.type == "eod":
        print("生成收盘复盘报告...")

        owned = load_owned_stocks()
        print(f"{'=' * 60}")
        print(f"{datetime.now().strftime('%Y-%m-%d')} 收盘复盘")
        print(f"{'=' * 60}")

        for code, info in owned.items():
            r = deep_analyze(code, days=365)
            if r:
                r["name"] = info.get("name", "")
                r["cost"] = info.get("cost", 0)
                pnl = (r["price"] / r["cost"] - 1) * 100
                status = "🟢" if pnl > 0 else "🔴"
                print(
                    f"  {status} {code} {r['name']}: 浮盈{pnl:+.2f}% | "
                    f"MACD:{r['macd_signal']} | RSI:{r['rsi']:.0f} | "
                    f"止损:{r['stop_loss']:.2f}"
                )

    elif args.type == "sector":
        print("生成板块分析报告...")
        from stock_analyzer.sector_report import generate_sector_report

        path = generate_sector_report()
        print(f"报告: {path}")

    elif args.type == "portfolio":
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
            print(f"  {info['名称']}: {info['最新价']:.2f} ({info['涨跌幅']:+.2f}%)")

        # 市场消息摘要
        print("\n今日市场消息:")
        try:
            from stock_analyzer.fetcher import get_market_news_digest

            digest = get_market_news_digest()
            print(f"  {digest['summary']}")
            if digest["hot_sectors"]:
                print(f"  热门板块: {'、'.join(digest['hot_sectors'])}")
            if digest["news_count"]:
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
                price = float(rtp.get("最新价", 0)) if rtp else 0
                if price:
                    pnl = (price / info.get("cost", price) - 1) * 100
                    name = rtp.get("名称", info.get("name", ""))
                    print(
                        f"  {code} {name}: "
                        f"成本{info.get('cost', 0):.2f} → 现价{price:.2f} "
                        f"浮盈{pnl:+.2f}%"
                    )
                else:
                    print(f"  {code} {info.get('name', '')}: 实时价获取失败")

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
            if lz["up"]:
                ups = [f"{s['name']}({s['change']:+.1f}%)" for s in lz["up"][:10]]
                print(f"  涨停示例: {'、'.join(ups)}")
            if lz["down"]:
                downs = [f"{s['name']}({s['change']:+.1f}%)" for s in lz["down"][:5]]
                print(f"  跌停示例: {'、'.join(downs)}")
        except Exception as e:
            print(f"  涨跌停数据获取失败: {e}")

    if args.rotation:
        print("\n板块轮动分析:")
        try:
            from stock_analyzer.fetcher import get_sector_rotation

            rot = get_sector_rotation()
            print(f"  {rot['message']}")
            if rot["top5_now"]:
                print("  板块排名 Top5:")
                for i, s in enumerate(rot["top5_now"]):
                    print(f"    {i + 1}. {s['name']}: {s['avg_score']}分")
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
            last = str(k["日期"].iloc[-1])[:10] if not k.empty else "?"
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
                print(
                    f"  {code}: 个股{rs['stock_return']:+.1f}%  大盘{rs['index_return']:+.1f}%  "
                    f"RS: {rs['rs_value']:+.1f}  {rs['trend']}"
                )
        except Exception as e:
            print(f"  相对强弱计算失败: {e}")


def cmd_config(args):
    """配置管理"""
    if args.action == "show":
        from stock_analyzer.config import (
            MA_WINDOWS,
            MACD_FAST,
            MACD_SIGNAL,
            MACD_SLOW,
            QUANT_FACTOR_WEIGHTS,
            RISK_FREE_RATE,
            RSI_PERIOD,
            TRADING_DAYS_PER_YEAR,
        )

        print("当前配置:")
        print(f"  均线周期: {MA_WINDOWS}")
        print(f"  MACD: ({MACD_FAST}, {MACD_SLOW}, {MACD_SIGNAL})")
        print(f"  RSI周期: {RSI_PERIOD}")
        print(f"  年交易日: {TRADING_DAYS_PER_YEAR}")
        print(f"  无风险利率: {RISK_FREE_RATE}")
        print(f"  因子权重: {QUANT_FACTOR_WEIGHTS}")
    elif args.action == "init":
        import json

        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        default_config = {
            "TRADING_DAYS_PER_YEAR": 252,
            "RISK_FREE_RATE": 0.03,
            "QUANT_FACTOR_WEIGHTS": {
                "momentum": 0.21,
                "technical": 0.21,
                "fundamental": 0.17,
                "volume": 0.10,
                "risk": 0.11,
                "sentiment": 0.10,
                "fund_flow": 0.10,
            },
            "SHORT_TERM_WEIGHTS": {
                "momentum": 0.20,
                "volume": 0.15,
                "volatility": 0.15,
                "combo_signal": 0.25,
                "resonance": 0.15,
                "position": 0.10,
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
        get_available_dates,
        get_market_summary,
        get_stock_history,
        get_top_stocks,
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
            print(f"\n{'=' * 50}")
            print(f"全市场评分分布 — {s['date']}")
            print(f"{'=' * 50}")
            print(f"总计: {s['total']} 只  均分: {s['avg_score']}")
            print(
                f"优秀(≥80): {s['excellent']} 只 ({s['excellent'] / s['total'] * 100:.1f}%)"
                if s["total"]
                else ""
            )
            print(
                f"良好(60-79): {s['good']} 只 ({s['good'] / s['total'] * 100:.1f}%)"
                if s["total"]
                else ""
            )
            print(
                f"中等(40-59): {s['medium']} 只 ({s['medium'] / s['total'] * 100:.1f}%)"
                if s["total"]
                else ""
            )
            print(
                f"偏低(<40): {s['low']} 只 ({s['low'] / s['total'] * 100:.1f}%)"
                if s["total"]
                else ""
            )
        else:
            print("暂无历史数据，请先运行一次全市场扫描")
        return

    if args.code:
        df = get_stock_history(args.code, days=30)
        if df.empty:
            print(f"未找到 {args.code} 的历史数据")
        else:
            print(f"\n{args.code} 近{len(df)}日评分趋势:")
            print(
                f"{'日期':<12} {'综合':<7} {'动量':<6} {'技术':<6} {'基本面':<6} {'量能':<6} {'风险':<6} {'价格':<8}"
            )
            print("-" * 65)
            for _, r in df.iterrows():
                print(
                    f"{r['date']:<12} {r['composite_score']:<7.1f} {r['momentum_score']:<6.0f} "
                    f"{r['technical_score']:<6.0f} {r['fundamental_score']:<6.0f} "
                    f"{r['volume_score']:<6.0f} {r['risk_score']:<6.0f} {r['price']:<8.2f}"
                )
        return

    # 默认: 显示最新日期的Top N
    df = get_top_stocks(args.date, top_n=args.top)
    if df.empty:
        print("暂无历史数据")
    else:
        date = df["date"].iloc[0]
        print(f"\n{date} Top {len(df)}:")
        print(
            f"{'#':<4} {'代码':<8} {'名称':<8} {'综合':<7} {'动量':<6} {'技术':<6} {'基本面':<6} {'价格':<8}"
        )
        print("-" * 65)
        for i, (_, r) in enumerate(df.iterrows()):
            print(
                f"{i + 1:<4} {r['code']:<8} {r['name']:<8} {r['composite_score']:<7.1f} "
                f"{r['momentum_score']:<6.0f} {r['technical_score']:<6.0f} "
                f"{r['fundamental_score']:<6.0f} {r['price']:<8.2f}"
            )


def cmd_audit(args):
    """系统自审计"""
    from stock_analyzer.self_audit import run_audit

    report = run_audit(auto_fix=not args.no_fix, verbose=True)
    return 1 if report.has_issues() else 0


def cmd_clean(args):
    """清理归档"""
    import glob

    patterns = [
        "deep_analysis_*.json",
        "final_5_analysis*.json",
        "short_term_*_analysis.json",
        "rational_*.json",
        "sector_copper_result.json",
        "candidate_pool_*.csv",
        "screener_*.csv",
        "deep_dive_*.json",
    ]
    archive_dir = "archive"
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
                    print(
                        f"  {r.get('代码', ''):<8} {r.get('名称', ''):<8} {r.get('净买额', 0):<12.0f} {r.get('涨幅', 0):<8}%"
                    )

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
                print(
                    f"  {mkt}: 融资{data.get('融资余额(亿)', 0):.0f}亿 融券{data.get('融券余额(亿)', 0):.0f}亿"
                )
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
                print("  热门调研TOP10:")
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
    from stock_analyzer.backtest import (
        DEFAULT_COMPARE_STRATEGIES,
        STRATEGIES,
        compare_strategies,
        export_backtest_json,
        optimize_strategy,
        run_backtest,
    )
    from stock_analyzer.cache import cached_kline

    print(f"加载 {args.code} K线数据...")
    kline = cached_kline(args.code, days=args.days)
    if kline.empty or len(kline) < 60:
        print("K线数据不足（至少60天）")
        return

    print(
        f"数据: {len(kline)} 天  |  初始资金: {args.capital:,}  |  "
        f"手续费: {args.commission:.4f}  |  滑点: {args.slippage:.3f}"
    )

    bt_kwargs = dict(
        initial_capital=args.capital,
        commission=args.commission,
        slippage=args.slippage,
        position_pct=args.position_pct,
        stop_loss=args.stop_loss,
        take_profit=args.take_profit,
        trailing_stop=args.trailing_stop,
    )

    if args.compare:
        strat_list = None
        if args.strategies:
            strat_list = [s.strip() for s in args.strategies.split(",")]
        print(f"\n{'=' * 70}")
        print(f"多策略对比回测 ({len(strat_list or DEFAULT_COMPARE_STRATEGIES)}个策略)")
        print(f"{'=' * 70}")
        results = compare_strategies(kline, strat_list, **bt_kwargs)
        if not results:
            print("所有策略均无有效信号")
            return
        # 基准收益
        bench = (float(kline["收盘"].iloc[-1]) / float(kline["收盘"].iloc[0]) - 1) * 100
        print(f"  基准(买入持有): {bench:.1f}%")
        header = f"{'策略':<16} {'收益率%':<10} {'超额%':<8} {'夏普':<8} {'索提诺':<8} {'卡玛':<8} {'回撤%':<8} {'交易':<6}"
        print(header)
        print("-" * len(header))
        for s_name, r in results.items():
            m = r["metrics"]
            print(
                f"{r['name']:<16} {m['总收益率%']:<10.1f} {m['超额收益%']:<8.1f} "
                f"{m['夏普比率']:<8.2f} {m['索提诺比率']:<8.2f} {m['卡玛比率']:<8.2f} "
                f"{m['最大回撤%']:<8.1f} {m['交易次数']:<6}"
            )
        best = max(results.items(), key=lambda x: x[1]["metrics"]["夏普比率"])
        print(f"\n最优: {best[1]['name']} (夏普{best[1]['metrics']['夏普比率']:.2f})")

        if args.output:
            export_backtest_json(
                {
                    "metrics": {s: r["metrics"] for s, r in results.items()},
                    "trades": [],
                    "equity_curve": [],
                    "summary": f"{len(results)}个策略对比",
                },
                args.output,
            )
            print(f"结果已导出: {args.output}")

    elif args.optimize:
        print(f"\n参数优化: {STRATEGIES[args.strategy]['name']}")
        best = optimize_strategy(kline, args.strategy)
        if best:
            print(f"最优参数: {best['params']}")
            m = best["metrics"]
            print(
                f"  样本内({best.get('train_days', '?')}天): "
                f"收益率{m['总收益率%']:.1f}%  夏普{m['夏普比率']:.2f}  "
                f"回撤{m['最大回撤%']:.1f}%"
            )
            if "test_metrics" in best:
                tm = best["test_metrics"]
                print(
                    f"  样本外({best.get('test_days', '?')}天): "
                    f"收益率{tm['总收益率%']:.1f}%  夏普{tm['夏普比率']:.2f}  "
                    f"回撤{tm['最大回撤%']:.1f}%"
                )
                oos_diff = tm["总收益率%"] - m["总收益率%"]
                warn = " ⚠️过拟合" if abs(oos_diff) > 20 else ""
                print(f"  样本内外收益差: {oos_diff:+.1f}%{warn}")
        else:
            print("优化失败，无法生成有效信号")

    else:
        s_info = STRATEGIES[args.strategy]
        print(f"\n策略: {s_info['name']}  参数: {s_info['default']}")
        result = run_backtest(kline, s_info["fn"], s_info["default"], **bt_kwargs)
        if result:
            m = result["metrics"]
            print(f"{'=' * 55}")
            print(f"收益率: {m['总收益率%']:.1f}%  年化: {m['年化收益率%']:.1f}%")
            print(
                f"夏普: {m['夏普比率']:.2f}  索提诺: {m['索提诺比率']:.2f}  卡玛: {m['卡玛比率']:.2f}"
            )
            print(
                f"回撤: {m['最大回撤%']:.1f}%  胜率: {m['胜率%']:.0f}%  交易: {m['交易次数']}次  盈亏比: {m['盈亏比']:.2f}"
            )
            print(f"基准(买入持有): {m['基准收益%']:.1f}%  超额收益: {m['超额收益%']:+.1f}%")
            print(f"最终资金: {m['最终资金']:,.0f}")
            if result["trades"]:
                print("\n最近5笔交易:")
                for t in result["trades"][-5:]:
                    pnl = f" 盈亏{t['pnl']:+.0f}" if "pnl" in t else ""
                    reason = (
                        f" [{t.get('exit_reason', '')}]"
                        if t.get("exit_reason") and t["action"] == "SELL"
                        else ""
                    )
                    print(f"  {t['date']} {t['action']} @{t['price']}{pnl}{reason}")

            if args.output:
                export_backtest_json(result, args.output)
                print(f"\n结果已导出: {args.output}")
        else:
            print("回测失败，无法生成有效信号")


def cmd_ml(args):
    """机器学习预测"""
    from stock_analyzer.cache import cached_fundamentals, cached_kline
    from stock_analyzer.ml_predict import ml_enhanced_score, predict_direction, predict_return

    print(f"加载 {args.code} 数据...")
    kline = cached_kline(args.code, days=365)
    if kline.empty or len(kline) < 60:
        print("K线数据不足（至少60天）")
        return

    funds = cached_fundamentals(args.code)

    if args.predict_return:
        print(f"\n{'=' * 50}")
        print(f"涨跌幅预测: {args.code}")
        print(f"{'=' * 50}")
        result = predict_return(kline, funds)
        _print_ml_result(result)

    elif args.enhance:
        print(f"\n{'=' * 50}")
        print(f"ML增强评分: {args.code}")
        print(f"{'=' * 50}")
        result = ml_enhanced_score(kline, funds)
        _print_ml_result(result)

    else:  # 默认方向预测
        print(f"\n{'=' * 50}")
        print(f"涨跌方向预测: {args.code}")
        print(f"{'=' * 50}")
        result = predict_direction(kline, funds)
        _print_ml_result(result)


def _print_ml_result(result):
    if "error" in result:
        print(f"  {result['error']}")
        return
    for k, v in result.items():
        if k == "重要特征":
            print(f"  {k}:")
            for f in v:
                print(f"    {f['特征']}: {f['重要性']:.4f}")
        else:
            print(f"  {k}: {v}")


def cmd_quality(args):
    """公司质地七问 — 商业模式+护城河+现金流+生命周期+估值+事件"""
    from stock_analyzer.business_quality import full_business_quality

    print(f"\n{'=' * 60}")
    print(f"  公司质地七问: {args.code}")
    print(f"{'=' * 60}")

    r = full_business_quality(args.code)

    print(f"\n{'─' * 40}")
    print(f"  综合评分: {r['overall_score']} → {r['overall_level']}")
    print(f"{'─' * 40}")

    # Q1
    p = r["company_profile"]
    print("\n【Q1 公司靠什么赚钱】")
    if p.get("main_business"):
        print(f"  主营业务: {p['main_business'][:100]}")
    print(f"  行业: {p['industry']}")
    if p.get("listing_date"):
        print(f"  上市时间: {p['listing_date']}")

    # Q2
    m = r["moat"]
    print("\n【Q2 护城河 — 凭什么别人抢不了】")
    print(f"  评分: {m['score']}/100 → {m['level']}")
    for s in m["signals"]:
        print(f"  • {s}")
    print(f"  {m['assessment'][:120]}")

    # Q3
    cf = r["cash_flow"]
    print("\n【Q3 现金流 — 到底赚的是真钱还是纸面利润】")
    print(f"  质量: {cf['quality']}")
    if cf["operating_cf_yi"]:
        print(
            f"  经营CF: {cf['operating_cf_yi']}亿 | 投资CF: {cf['investing_cf_yi']}亿 | 融资CF: {cf['financing_cf_yi']}亿"
        )
        print(f"  自由现金流: {cf['free_cf_yi']}亿")
    print(f"  {cf['assessment']}")

    # Q4
    lc = r["lifecycle"]
    print("\n【Q4 生命周期 — 公司现在什么阶段】")
    print(f"  阶段: {lc['stage_cn']} (置信度{lc['confidence']}%)")
    for s in lc["signals"]:
        print(f"  • {s}")
    if not args.short:
        print(f"  建议: {lc['suggestion']}")

    # Q5
    v = r["valuation"]
    print("\n【Q5 估值 — 股价贵不贵】")
    print(f"  评分: {v['score']}/100 → {v['level']}")
    print(f"  PE={v['pe']} | PB={v['pb']} | PEG={v['peg']}")
    for s in v["signals"][:3]:
        print(f"  • {s}")

    # Q6 — 跳过，已有技术面
    print(f"\n【Q6 近期表现】→ 请使用 python cli.py analyze {args.code} --full 查看技术面分析")

    # Q7
    e = r["events"]
    print("\n【Q7 近期大事】")
    if e["events"]:
        for ev in e["events"][:5]:
            print(f"  [{ev['type']}] {ev['date']} {ev['title'][:60]}")
    else:
        print(f"  {e['assessment']}")

    print(f"\n{'─' * 40}")
    print(f"  综合评估: {r['assessment_summary'][:150]}")
    print(f"{'─' * 40}\n")
