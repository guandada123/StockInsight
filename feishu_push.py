#!/usr/bin/env python
r"""飞书每日推送调度脚本

用法:
  python feishu_push.py --mode daily     尾盘选股推送 (14:30)
  python feishu_push.py --mode morning   盘前大盘简报 (9:00)
  python feishu_push.py --mode alert     持仓异动预警
  python feishu_push.py --dry-run        仅输出不推送（测试用）

跨平台调度:
  macOS/Linux: 通过 WorkBuddy 自动化定时触发（推荐）
               或 crontab:
                30 14 * * 1-5 cd /path/to/stock-insight && python feishu_push.py --mode daily
                 0  9 * * 1-5 cd /path/to/stock-insight && python feishu_push.py --mode morning
                 */30 9-15 * * 1-5 cd /path/to/stock-insight && python feishu_push.py --mode alert
  Windows:     schtasks（见下方注释）
"""

import argparse
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_DIR)
sys.path.insert(0, PROJECT_DIR)


def push_daily(dry_run=False):
    """尾盘选股推送"""
    print(f"尾盘选股推送 [{_now()}]")
    if dry_run:
        print("[DRY RUN] 仅输出不发送\n")
        _print_market()
        return

    from stock_analyzer.feishu_bot import push_daily_picks

    result = push_daily_picks()
    if result.get("ok"):
        print("推送成功")
    else:
        print(f"推送失败: {result.get('error', '未知错误')}")


def push_morning(dry_run=False):
    """盘前大盘简报"""
    print(f"盘前大盘简报 [{_now()}]")

    from stock_analyzer.feishu_bot import send_market_brief
    from stock_analyzer.fetcher import get_market_overview

    market = get_market_overview()
    idx_map = {"000001": "上证", "399001": "深证", "399006": "创业板", "000688": "科创50"}

    print("大盘指数:")
    for code, name in idx_map.items():
        info = market.get(code, {})
        price = float(info.get("最新价", 0) or 0)
        prev = float(info.get("昨收", 0) or 0)
        chg_pct = round((price - prev) / prev * 100, 2) if prev else 0
        print(f"  {name}: {price:.2f} {chg_pct:+.2f}%")

    if dry_run:
        print("\n[DRY RUN] 未发送到飞书")
        return

    result = send_market_brief()
    if result.get("ok"):
        print("大盘简报推送成功")
    else:
        print(f"推送失败: {result.get('error', '')}")


def push_alert(dry_run=False):
    """持仓异动预警"""
    print(f"持仓异动预警 [{_now()}]")

    # 读取持仓
    import glob
    import json

    files = sorted(glob.glob("mainboard_owned_*.json"), reverse=True)
    if not files:
        print("未找到持仓文件")
        return

    with open(files[0], encoding="utf-8") as f:
        owned = json.load(f)
    if not owned:
        print("持仓为空")
        return

    from stock_analyzer.fetcher import sina_real_time

    codes = list(owned.keys())
    rt = sina_real_time(codes)

    alerts = []
    for code, pos in owned.items():
        info = rt.get(code, {})
        price = float(info.get("最新价", 0) or 0)
        cost = pos.get("cost", 0)
        if not cost or not price:
            continue
        profit_pct = round((price - cost) / cost * 100, 2)
        name = info.get("名称", code)

        # 预警条件
        if profit_pct <= -5:
            alerts.append(
                f"🔴 {name}({code}) 浮亏{profit_pct:.1f}% 现价{price:.2f} 成本{cost:.2f} 注意止损!"
            )
        elif profit_pct >= 8:
            alerts.append(f"🟢 {name}({code}) 浮盈{profit_pct:+.1f}% 现价{price:.2f} 可考虑止盈")

    if not alerts:
        print("无预警触发")
        if dry_run:
            print("[DRY RUN] 未发送")
        return

    for a in alerts:
        print(a)

    if dry_run:
        print("\n[DRY RUN] 未发送到飞书")
        return

    from stock_analyzer.feishu_bot import send_text

    content = "【持仓异动预警】\n" + "\n".join(alerts)
    result = send_text(content)
    if result.get("ok"):
        print("预警推送成功")
    else:
        print(f"推送失败: {result.get('error', '')}")


def _print_market():
    """控制台打印大盘信息"""
    from stock_analyzer.fetcher import get_market_overview, get_sectors

    print("═══ 大盘指数 ═══")
    market = get_market_overview()
    idx_map = {"000001": "上证", "399001": "深证", "399006": "创业板", "000688": "科创50"}
    for code, name in idx_map.items():
        info = market.get(code, {})
        price = float(info.get("最新价", 0) or 0)
        prev = float(info.get("昨收", 0) or 0)
        chg_pct = round((price - prev) / prev * 100, 2) if prev else 0
        print(f"  {name}: {price:.2f} {chg_pct:+.2f}%")

    print("\n═══ 板块 TOP5 ═══")
    sectors = get_sectors()
    if isinstance(sectors, dict) and sectors:
        ranked = sorted(
            sectors.items(), key=lambda x: float(x[1].get("涨跌幅", 0) or 0), reverse=True
        )
        for i, (nm, info) in enumerate(ranked[:5]):
            chg = float(info.get("涨跌幅", 0) or 0)
            ff = float(info.get("资金净流入", 0) or 0) / 1e8
            print(f"  {i + 1}. {nm} {chg:+.2f}% 资金{ff:+.1f}亿")


def _now():
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="飞书每日推送调度")
    parser.add_argument(
        "--mode",
        choices=["daily", "morning", "alert"],
        default="daily",
        help="推送模式: daily(尾盘选股) morning(盘前简报) alert(异动预警)",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅输出不推送（测试用）")
    args = parser.parse_args()

    if args.mode == "daily":
        push_daily(dry_run=args.dry_run)
    elif args.mode == "morning":
        push_morning(dry_run=args.dry_run)
    elif args.mode == "alert":
        push_alert(dry_run=args.dry_run)
