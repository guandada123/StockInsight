"""每日定时运行入口 & 计划任务注册

收盘后自动运行全市场扫描（仅排除ST/退市，不设价格成交量下限）。
用法:
  python run_daily.py              # 立即执行一次全市场扫描
  python run_daily.py --install    # 注册每日16:00定时任务 (需管理员权限)
  python run_daily.py --uninstall  # 删除定时任务

手动设置定时任务（如自动安装失败）：
  1. 按 Win+R, 输入 taskschd.msc
  2. 创建基本任务 -> 触发器: 每日 16:00（A股15:00收盘，等数据同步）
  3. 操作: 启动程序 -> python D:\CC\股票分析\run_daily.py
"""
import sys
import os
import json
import subprocess
import argparse
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def run_now():
    """立即执行全市场扫描，日志按日期归档"""
    os.chdir(PROJECT_DIR)
    sys.path.insert(0, PROJECT_DIR)

    # 每日日志归档
    date_str = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(PROJECT_DIR, "logs", f"full_scan_{date_str}.log")
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    print(f"每日全市场扫描启动 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
    print(f"日志将写入: {log_file}")

    # 调用 run_full_scan，输出重定向到日志文件
    import subprocess as sp
    with open(log_file, "w", encoding="utf-8") as f:
        proc = sp.run(
            [sys.executable, os.path.join(PROJECT_DIR, "run_full_scan.py")],
            stdout=f, stderr=sp.STDOUT, text=True, cwd=PROJECT_DIR,
        )

    if proc.returncode == 0:
        print(f"扫描完成，日志: {log_file}")
    else:
        print(f"扫描异常退出 (code={proc.returncode})，日志: {log_file}")

    # ── 自审计 ──
    print(f"\n自审计启动 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
    try:
        from stock_analyzer.self_audit import run_audit
        report = run_audit(auto_fix=True, verbose=True)
        audit_log = os.path.join(PROJECT_DIR, "logs", f"audit_{date_str}.json")
        with open(audit_log, "w", encoding="utf-8") as f:
            json.dump({
                "date": date_str,
                "issues": report.issues,
                "fixes": report.fixes,
                "warnings": report.warnings,
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  审计异常: {e}")
    return proc.returncode


def install_scheduler():
    """注册 Windows 计划任务，每日16:00运行（收盘后数据已同步）"""
    python_exe = sys.executable
    script = os.path.join(PROJECT_DIR, "run_daily.py")
    task_name = "StockFullScanDaily"

    cmd = (
        f'schtasks /Create /SC DAILY /TN "{task_name}" '
        f'/TR "{python_exe} {script}" /ST 16:00 '
        f"/F /RL HIGHEST"
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"计划任务已注册：每日 16:00 运行全市场扫描")
        print(f"任务名称: {task_name}")
        return True
    else:
        print(f"注册失败: {result.stderr}")
        return False


def uninstall_scheduler():
    """删除计划任务"""
    task_name = "StockFullScanDaily"
    cmd = f'schtasks /Delete /TN "{task_name}" /F'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"计划任务已删除: {task_name}")
        return True
    else:
        print(f"删除失败: {result.stderr}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="股票全市场扫描每日定时任务")
    parser.add_argument("--install", action="store_true", help="注册每日16:00定时任务")
    parser.add_argument("--uninstall", action="store_true", help="删除定时任务")
    args = parser.parse_args()

    if args.install:
        install_scheduler()
    elif args.uninstall:
        uninstall_scheduler()
    else:
        run_now()
