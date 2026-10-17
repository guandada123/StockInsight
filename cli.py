#!/usr/bin/env python
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

import argparse
import sys


from cli_core import (  # noqa: F401 —— re-export 保 import cli 兼容
    _fail_on_skip_ratio,
    deep_analyze,
    load_owned_stocks,
)


from cli_commands import (  # noqa: F401 —— re-export 保 import cli 兼容
    _cmd_premarket_check,
    cmd_scan,
    cmd_enhanced_scan,
    cmd_overnight_scan,
    cmd_overnight_sell,
    cmd_analyze,
    cmd_report,
    cmd_check,
    cmd_config,
    cmd_history,
    cmd_audit,
    cmd_clean,
    cmd_advanced,
    cmd_backtest,
    cmd_ml,
    _print_ml_result,
    cmd_quality,
)


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
    sp.add_argument(
        "--mode",
        choices=["full", "mainboard"],
        default="mainboard",
        help="扫描模式: full=全A股, mainboard=主板+创业板(60/00/30，不含科创/北交所)",
    )
    sp.add_argument("--top-n", type=int, default=50, help="保留前N只 (默认50)")
    sp.add_argument("--min-score", type=int, default=60, help="最低综合评分 (默认60)")
    sp.add_argument("--resume", action="store_true", help="从上次checkpoint续跑")
    sp.add_argument("--output", "-o", help="输出文件路径")
    sp.add_argument("--no-save", action="store_true", help="不保存结果到CSV/JSON")

    # === enhanced-scan (增强选股) ===
    esp = sub.add_parser("enhanced-scan", help="增强选股(板块+短线+ML+自定义因子)")
    esp.add_argument(
        "--mode",
        choices=["mainboard", "full", "top_sectors"],
        default="mainboard",
        help="mainboard=主板+创业板, full=全A股, top_sectors=仅前排板块",
    )
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
    ap.add_argument(
        "--full", action="store_true", help="一键全出：技术+量化+基本面+资金+回测+AI+宏观"
    )
    ap.add_argument(
        "--fast", action="store_true", help="快速模式：仅本地计算(L0-L3)，零网络等待，盘中秒出"
    )
    ap.add_argument(
        "--ultimate",
        action="store_true",
        help="终极分析：大盘→板块排名→资金流向→七层→预测价位→操作建议",
    )

    # === report ===
    rp = sub.add_parser("report", help="生成报告")
    rp.add_argument(
        "--type",
        choices=["screener", "eod", "sector", "portfolio"],
        default="eod",
        help="报告类型 (默认eod)",
    )
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
    cp.add_argument(
        "--premarket", action="store_true", help="开盘前全面自检: 网络+数据库+数据源+API一键检测"
    )
    cp.add_argument("--update-kline", action="store_true", help="增量更新持仓K线至最新交易日")

    # === config ===
    cfgp = sub.add_parser("config", help="配置管理")
    cfgp.add_argument(
        "action", choices=["show", "init"], default="show", help="show=查看配置, init=生成默认配置"
    )

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
    avp.add_argument(
        "--insider", type=str, nargs="?", const="all", help="高管增减持(指定代码或全部)"
    )
    avp.add_argument("--visit", type=str, nargs="?", const="top", help="机构调研(指定代码或热门)")
    avp.add_argument("--financial", type=str, help="财报深度拆解(指定代码)")
    avp.add_argument("--macro", action="store_true", help="宏观指标+市场信号")
    avp.add_argument("--all", action="store_true", help="一键全部分析(含当前持仓)")

    # === backtest ===
    btp = sub.add_parser("backtest", help="策略回测")
    btp.add_argument("code", help="股票代码")
    btp.add_argument(
        "--strategy",
        "-s",
        default="ma_cross",
        choices=[
            "ma_cross",
            "macd_cross",
            "rsi_reversal",
            "bollinger",
            "ma_trend",
            "momentum_breakout",
            "grid",
        ],
        help="策略名称（默认ma_cross）",
    )
    btp.add_argument("--compare", action="store_true", help="多策略对比")
    btp.add_argument(
        "--strategies",
        type=str,
        default=None,
        help="对比策略列表，逗号分隔（如 ma_cross,macd_cross,rsi_reversal）",
    )
    btp.add_argument("--optimize", action="store_true", help="参数优化")
    btp.add_argument("--days", type=int, default=365, help="回测天数")
    btp.add_argument("--capital", type=int, default=100000, help="初始资金")
    btp.add_argument("--commission", type=float, default=0.0003, help="手续费率（默认0.0003）")
    btp.add_argument("--slippage", type=float, default=0.001, help="滑点（默认0.001）")
    btp.add_argument("--position-pct", type=float, default=1.0, help="仓位比例（默认1.0）")
    btp.add_argument("--output", "-o", type=str, default=None, help="导出JSON文件路径")
    btp.add_argument(
        "--stop-loss",
        type=float,
        default=None,
        metavar="PCT",
        help="固定止损比例（如 0.08=8%%亏损止损）",
    )
    btp.add_argument(
        "--take-profit",
        type=float,
        default=None,
        metavar="PCT",
        help="固定止盈比例（如 0.15=15%%盈利止盈）",
    )
    btp.add_argument(
        "--trailing-stop",
        type=float,
        default=None,
        metavar="PCT",
        help="移动止损比例（如 0.05=从高点回撤5%%止损）",
    )

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


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    dispatch = {
        "scan": cmd_scan,
        "enhanced-scan": cmd_enhanced_scan,
        "overnight-scan": cmd_overnight_scan,
        "overnight-sell": cmd_overnight_sell,
        "analyze": cmd_analyze,
        "report": cmd_report,
        "check": cmd_check,
        "config": cmd_config,
        "history": cmd_history,
        "clean": cmd_clean,
        "audit": cmd_audit,
        "advanced": cmd_advanced,
        "backtest": cmd_backtest,
        "ml": cmd_ml,
        "quality": cmd_quality,
    }
    # 修复(2026-10-16)：原为 `dispatch[args.command](args)`，**丢弃返回值**，
    # 进程恒以 0 退出 —— 于是调用方依赖的「退出码非 0 = 异常」判定永远不成立
    # （StockInsight 收盘选股扫描自动化的异常条件之一），cmd_audit 的
    # `1 if has_issues else 0` 也从未生效。改为把返回值交给 sys.exit：
    #   · 返回 None → sys.exit(None) → 退出码 0，与修复前行为一致
    #   · 返回 int → 真实传播（cmd_audit / cmd_scan 的失败码将真正可观测）
    sys.exit(dispatch[args.command](args))


if __name__ == "__main__":
    main()
