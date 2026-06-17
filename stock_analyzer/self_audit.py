"""自审计模块 — 每日自动检测数据质量+API健康+内部一致性

设计原则：
  - 审计不依赖任何外部权威"正确值"，只检查内部矛盾和异常模式
  - 能自动修复的自动修复，不能的明确报告
  - 零误报：宁可漏过也不干扰正常流程

使用：python cli.py audit
集成：每日16:00 run_daily.py 自动触发
"""

import time

# ── 审计结果收集 ──


class AuditReport:
    def __init__(self):
        self.issues = []
        self.fixes = []
        self.warnings = []
        self.passed = []

    def fail(self, category, detail, fix=None):
        self.issues.append({"category": category, "detail": detail, "fix": fix})

    def warn(self, category, detail):
        self.warnings.append({"category": category, "detail": detail})

    def ok(self, category, detail):
        self.passed.append({"category": category, "detail": detail})

    def fixed(self, category, detail):
        self.fixes.append({"category": category, "detail": detail})

    def has_issues(self):
        return len(self.issues) > 0

    def summary(self):
        lines = []
        lines.append(
            f"审计完成: {len(self.issues)}个问题 | {len(self.fixes)}个已修复 | {len(self.warnings)}个警告 | {len(self.passed)}个通过"
        )
        if self.issues:
            lines.append("\n⚠️ 需处理:")
            for i in self.issues:
                lines.append(f"  [{i['category']}] {i['detail']}")
                if i.get("fix"):
                    lines.append(f"    建议修复: {i['fix']}")
        if self.fixes:
            lines.append("\n✅ 已自动修复:")
            for f in self.fixes:
                lines.append(f"  [{f['category']}] {f['detail']}")
        if self.warnings:
            lines.append("\n🔶 警告:")
            for w in self.warnings:
                lines.append(f"  [{w['category']}] {w['detail']}")
        return "\n".join(lines)


# ── 审计规则 ──


def audit_api_data_consistency(report):
    """审计1: API返回数据内部一致性"""
    try:
        from .cache import cached_kline
        from .fetcher import get_market_overview, sina_real_time

        # 1a. 检验实时行情不为空
        test_codes = ["000001", "002156", "600719"]
        rt = sina_real_time(test_codes)
        ok_count = sum(1 for c in test_codes if c in rt and rt[c].get("最新价", 0) > 0)
        if ok_count == 0:
            report.fail("实时行情", "新浪实时行情全部返回空，可能API故障")
        elif ok_count < len(test_codes):
            report.warn("实时行情", f"新浪实时行情 {ok_count}/{len(test_codes)} 只有效")
        else:
            report.ok("实时行情", f"{ok_count}只测试股票数据正常")

        # 1b. 检验价格合理性
        for c in test_codes:
            if c in rt:
                price = rt[c].get("最新价", 0)
                if price <= 0:
                    report.fail("价格合理性", f"{c} 实时价为{price}，异常")
                elif price < 0.5 or price > 5000:
                    report.fail("价格合理性", f"{c} 实时价{price}超出正常范围")

        # 1c. 检验K线数据量
        for c in test_codes:
            kline = cached_kline(c)
            if kline is None or kline.empty:
                report.fail("K线数据", f"{c} K线数据为空")
            elif len(kline) < 100:
                report.warn("K线数据", f"{c} K线仅{len(kline)}条(<100)")
            else:
                report.ok("K线数据", f"{c} {len(kline)}条K线正常")

        # 1d. 检验大盘数据
        market = get_market_overview()
        if not market:
            report.fail("大盘数据", "get_market_overview 返回空")
        else:
            key_indices = ["000001", "399001", "399006"]
            missing = [i for i in key_indices if i not in market]
            if missing:
                report.warn("大盘数据", f"缺指数: {missing}")
            else:
                report.ok("大盘数据", f"{len(market)}个指数正常")

    except Exception as e:
        report.fail("审计1", f"数据一致性检查异常: {e}")


def audit_internal_key_consistency(report):
    """审计2: 模块间键名一致性"""
    try:
        # 2a. calc_risk_metrics 输出键 vs deep_analyze 读取键
        from .cache import cached_kline
        from .quant import calc_risk_metrics

        kline = cached_kline("002156")
        if kline is not None and not kline.empty:
            risk = calc_risk_metrics(kline)
            required_keys = [
                "VaR_95_pct",
                "CVaR_95_pct",
                "annualized_volatility_pct",
                "sharpe_ratio",
                "max_drawdown_pct",
                "annualized_return_pct",
            ]
            missing = [k for k in required_keys if k not in risk]
            if missing:
                report.fail(
                    "键名一致性",
                    f"calc_risk_metrics 缺少键: {missing}",
                    "检查 quant.py:calc_risk_metrics 返回字典",
                )
            else:
                report.ok("键名一致性", f"calc_risk_metrics {len(required_keys)}个必需键全部存在")

            # 2b. 检验值合理性
            null_keys = [k for k, v in risk.items() if v is None and k in required_keys]
            if null_keys:
                report.warn("键名一致性", f"calc_risk_metrics 键{null_keys}值为None")
            zero_keys = [
                k for k in ["VaR_95_pct", "annualized_volatility_pct"] if risk.get(k, -1) == 0
            ]
            if zero_keys:
                report.warn("键名一致性", f"键{zero_keys}值为0，可能是键名不匹配(历史bug已修复)")

        # 2b. 资金流向列名检查
        from .fetcher import get_fund_flow

        df = get_fund_flow("002156", days=5)
        if not df.empty:
            if "主力净流入-净额" not in df.columns:
                report.fail("资金流向", "DataFrame缺少'主力净流入-净额'列")
            else:
                report.ok("资金流向", "列名正确")
            if "主力净流入-净占比" in df.columns:
                # 确保净占比是百分比值(-100到100)
                pct_vals = df["主力净流入-净占比"].dropna()
                if len(pct_vals) > 0:
                    if abs(pct_vals).max() > 100:
                        report.warn("资金流向", f"净占比最大值{abs(pct_vals).max():.1f}%超100%")

    except Exception as e:
        report.fail("审计2", f"键名一致性检查异常: {e}")


def audit_cross_source_validation(report):
    """审计3: 多数据源交叉验证"""
    try:
        from .cache import cached_kline
        from .fetcher import sina_real_time

        # 3a. 实时价 vs K线昨收
        test_codes = ["000001", "002156"]
        rt = sina_real_time(test_codes)
        for c in test_codes:
            if c not in rt:
                continue
            rtp = rt[c]
            realtime_price = float(rtp.get("最新价", 0))
            yclose = float(rtp.get("昨收", 0))
            if realtime_price and yclose:
                chg = (realtime_price - yclose) / yclose * 100
                if abs(chg) > 11:  # A股涨跌停±10%，ST±5%
                    report.fail(
                        "交叉验证",
                        f"{c} 实时价{realtime_price} vs 昨收{yclose} = {chg:.1f}%，超过涨跌停限制",
                        "可能新浪数据错误或复权问题，交叉验证腾讯源",
                    )
                elif abs(chg) > 9.5 and abs(chg) <= 11:
                    report.ok("交叉验证", f"{c} 涨跌{chg:.1f}%（接近涨跌停）")
            else:
                report.warn("交叉验证", f"{c} 实时价或昨收为空")

        # 3b. K线最新收盘 vs 实时昨收
        for c in test_codes:
            kline = cached_kline(c)
            if kline is None or kline.empty:
                continue
            kline_close = float(kline.iloc[-1]["收盘"])
            if c in rt:
                sina_yclose = float(rt[c].get("昨收", 0))
                if sina_yclose and abs(kline_close - sina_yclose) / sina_yclose > 0.02:
                    report.warn(
                        "交叉验证",
                        f"{c} K线昨收{kline_close} vs 新浪昨收{sina_yclose} "
                        f"差异{abs(kline_close - sina_yclose) / sina_yclose * 100:.1f}%",
                    )

        report.ok("交叉验证", "多源对比完成")

    except Exception as e:
        report.fail("审计3", f"交叉验证异常: {e}")


def audit_score_validity(report):
    """审计4: 评分有效性——检测全零字段等异常"""
    try:
        from pathlib import Path

        import pandas as pd

        csv_path = Path("full_scan_results.csv")
        if not csv_path.exists():
            report.warn("评分有效性", "full_scan_results.csv 不存在，跳过")
            return

        df = pd.read_csv(csv_path)
        if df.empty:
            report.warn("评分有效性", "full_scan_results.csv 为空")
            return

        # 4a. 检查各分数字段是否全零
        score_cols = ["综合评分", "动量分", "技术分", "基本面分", "量能分", "风险分"]
        for col in score_cols:
            if col not in df.columns:
                continue
            non_zero = (df[col] != 0).sum()
            total = len(df)
            if non_zero == 0:
                report.fail(
                    "评分有效性",
                    f"'{col}' 全部为0({total}行)，疑似计算模块故障",
                    "检查 quant.py 对应因子函数",
                )
            elif non_zero < total * 0.5:
                report.warn(
                    "评分有效性", f"'{col}' 仅{non_zero}/{total}({non_zero / total * 100:.0f}%)非零"
                )
            else:
                report.ok("评分有效性", f"'{col}' {non_zero}/{total}正常")

        # 4b. 综合评分范围检查
        if "综合评分" in df.columns:
            score_range = (df["综合评分"].min(), df["综合评分"].max())
            if score_range[1] > 100 or score_range[0] < 0:
                report.fail("评分有效性", f"综合评分范围{score_range}超出0-100")

        # 4c. 最新价范围
        if "最新价" in df.columns:
            valid_prices = df[df["最新价"] > 0]["最新价"]
            if len(valid_prices) < len(df) * 0.9:
                report.warn("评分有效性", f"{(len(df) - len(valid_prices))}只股票价格为0或负")

    except Exception as e:
        report.fail("审计4", f"评分有效性检查异常: {e}")


def audit_performance(report):
    """审计5: 性能监控"""
    try:
        from .cache import cached_fundamentals, cached_kline
        from .fetcher import sina_real_time

        # 5a. 实时行情响应时间
        t0 = time.time()
        rt = sina_real_time(["000001", "002156"])
        elapsed = time.time() - t0
        if elapsed > 1.0:
            report.fail("性能", f"sina_real_time 耗时{elapsed:.1f}s(>1s)，可能网络故障")
        elif elapsed > 0.5:
            report.warn("性能", f"sina_real_time 耗时{elapsed:.1f}s(>0.5s)")
        else:
            report.ok("性能", f"sina_real_time {elapsed:.3f}s")

        # 5b. K线缓存速度
        t0 = time.time()
        _ = cached_kline("002156")
        elapsed = time.time() - t0
        if elapsed > 0.1:
            report.warn("性能", f"cached_kline 耗时{elapsed:.3f}s(>0.1s)")

        # 5c. 基本面缓存速度
        t0 = time.time()
        _ = cached_fundamentals("002156")
        elapsed = time.time() - t0
        if elapsed > 2.0:
            report.warn("性能", f"cached_fundamentals 耗时{elapsed:.1f}s(>2s)")

    except Exception as e:
        report.fail("审计5", f"性能监控异常: {e}")


def audit_fund_flow_sign(report):
    """审计6: 资金流向方向性自检

    取3只代表性股票，用新旧两套逻辑交叉验证。
    如果方向相反 → 高度怀疑数据问题。
    """
    try:
        from .cache import cached_fund_flow
        from .fetcher import get_fund_flow

        test_codes = ["002156", "600719", "000001"]
        mismatches = 0
        for code in test_codes:
            df = get_fund_flow(code, days=5)
            if df.empty:
                continue
            total = df["主力净流入-净额"].sum()

            # 交叉检查缓存版本
            cached_df = cached_fund_flow(code, days=5)
            if not cached_df.empty:
                cached_total = cached_df["主力净流入-净额"].sum()
                if (
                    (total > 0) != (cached_total > 0)
                    and abs(total) > 1e7
                    and abs(cached_total) > 1e7
                ):
                    mismatches += 1
                    report.fail(
                        "资金流向",
                        f"{code} 实时API与缓存方向相反: {total / 1e8:.2f}亿 vs {cached_total / 1e8:.2f}亿",
                    )

        if mismatches == 0:
            report.ok("资金流向", f"{len(test_codes)}只方向一致")

    except Exception as e:
        report.fail("审计6", f"资金流向自检异常: {e}")


# ── 自动修复 ──

AUTO_FIX_LIST = [
    {
        "id": "cache_wipe_fund_flow",
        "desc": "清除过期资金流向缓存",
        "action": lambda: _clear_cache_pattern("fundflow:%"),
    },
    {
        "id": "reload_name_map",
        "desc": "预加载股票名称映射到缓存",
        "action": lambda: _preload_name_map(),
    },
]


def _clear_cache_pattern(pattern: str):
    """清除匹配模式的缓存条目"""
    try:
        from .cache import _get_conn

        conn = _get_conn()
        conn.execute("DELETE FROM cache WHERE key LIKE ?", (pattern,))
        conn.commit()
        return True
    except Exception:
        return False


def _preload_name_map():
    """预加载名称映射"""
    try:
        from .fetcher import _load_stock_name_map

        _load_stock_name_map()
        return True
    except Exception:
        return False


def audit_api_health(report):
    """审计7: API可用性评分（0-100）"""
    results = {}

    # 1. Sina 实时行情 (权重: 40%)
    try:
        from .fetcher import sina_real_time

        t0 = time.time()
        rt = sina_real_time(["000001"])
        elapsed = time.time() - t0
        ok = "000001" in rt and rt["000001"].get("最新价", 0) > 0
        results["sina"] = {"ok": ok, "latency_ms": round(elapsed * 1000), "weight": 40}
        if ok and elapsed < 0.5:
            report.ok("API健康", f"sina ✅ {elapsed * 1000:.0f}ms")
        elif ok:
            report.warn("API健康", f"sina ⚠️ {elapsed * 1000:.0f}ms(偏慢)")
        else:
            report.fail("API健康", "sina ❌ 实时行情不可用", "检查网络连接")
    except Exception as e:
        results["sina"] = {"ok": False, "latency_ms": 0, "weight": 40}
        report.fail("API健康", f"sina ❌ 异常: {e}")

    # 2. 东方财富 push2 (权重: 30%)
    try:
        from .fetcher import get_sectors

        t0 = time.time()
        df = get_sectors()
        elapsed = time.time() - t0
        ok = df is not None and not df.empty and len(df) > 5
        results["eastmoney"] = {"ok": ok, "latency_ms": round(elapsed * 1000), "weight": 30}
        if ok:
            report.ok("API健康", f"东方财富 ✅ {elapsed * 1000:.0f}ms ({len(df)}个板块)")
        elif len(df) <= 5 if not df.empty else True:
            report.warn("API健康", f"东方财富 ⚠️ 仅{len(df) if not df.empty else 0}个板块(降级)")
    except Exception as e:
        results["eastmoney"] = {"ok": False, "latency_ms": 0, "weight": 30}
        report.warn("API健康", f"东方财富 ⚠️ {e}")

    # 3. 资金流向 push2his (权重: 30%)
    try:
        from .fetcher import get_fund_flow

        t0 = time.time()
        df = get_fund_flow("002156", days=5)
        elapsed = time.time() - t0
        ok = df is not None and not df.empty
        results["fundflow"] = {"ok": ok, "latency_ms": round(elapsed * 1000), "weight": 30}
        if ok:
            report.ok("API健康", f"资金流向 ✅ {elapsed * 1000:.0f}ms")
        else:
            report.warn("API健康", "资金流向 ⚠️ 不可用(T+1正常，用缓存兜底)")
    except Exception as e:
        results["fundflow"] = {"ok": False, "latency_ms": 0, "weight": 30}
        report.warn("API健康", f"资金流向 ⚠️ {e}")

    # 综合健康分
    health_score = sum(r["weight"] for r in results.values() if r["ok"])
    report.ok("API健康", f"综合评分: {health_score}/100")


def audit_storage_benchmark(report):
    """审计8: 存储格式微基准 — 确保不再被错误性能数据误导

    每次审计时跑隔离微基准：纯pickle反序列化 vs 完整读取路径。
    检测格式退化 + 确认无parquet残留。
    """
    try:
        import os
        import pickle
        import sqlite3

        from .cache import _MEM_CACHE, DB_PATH, _load_kline_store

        # 8a. 格式纯度检查: 确认无parquet残留
        parquet_dir = os.path.join(os.path.dirname(DB_PATH), "kline_parquet")
        parquet_py = os.path.join(os.path.dirname(__file__), "kline_parquet.py")
        if os.path.exists(parquet_dir):
            report.fail(
                "存储格式",
                f"kline_parquet/ 目录仍存在({parquet_dir})，应已删除",
                "rm -rf kline_parquet/",
            )
        elif os.path.exists(parquet_py):
            report.fail(
                "存储格式",
                f"kline_parquet.py 文件仍存在({parquet_py})，应已删除",
                "rm stock_analyzer/kline_parquet.py",
            )
        else:
            report.ok("存储格式", "无parquet残留，格式干净")

        # 8b. pickle纯反序列化微基准 (排除SQLite/网络/冷启动干扰)
        try:
            conn = sqlite3.connect(DB_PATH)
            row = conn.execute("SELECT data FROM kline_store WHERE code='000001'").fetchone()
            conn.close()
            if row:
                blob = row[0]
                # 多轮循环，排除缓存干扰
                times = []
                for _ in range(50):
                    t0 = time.perf_counter()
                    _ = pickle.loads(blob)  # nosec - benchmark code, reading from local DB only
                    times.append(time.perf_counter() - t0)
                avg_ms = sum(times) / len(times) * 1000
                max_ms = max(times) * 1000

                if avg_ms > 5.0:
                    report.fail(
                        "存储格式",
                        f"pickle反序列化均{avg_ms:.1f}ms(>5ms阈值)，疑似格式退化",
                        "检查K线数据是否混入非pickle格式",
                    )
                elif avg_ms > 1.0:
                    report.warn("存储格式", f"pickle反序列化均{avg_ms:.1f}ms(>1ms)，偏慢")
                else:
                    report.ok(
                        "存储格式", f"pickle反序列化均{avg_ms:.2f}ms/次(50轮, max{max_ms:.1f}ms)"
                    )
        except Exception as e:
            report.fail("存储格式", f"pickle微基准异常: {e}")

        # 8c. _load_kline_store 完整读取路径
        try:
            _MEM_CACHE.clear()
            t0 = time.perf_counter()
            df = _load_kline_store("000001")
            elapsed = (time.perf_counter() - t0) * 1000
            if df is not None and not df.empty:
                if elapsed > 50:
                    report.warn("存储格式", f"_load_kline_store {elapsed:.0f}ms(>50ms)，读取偏慢")
                else:
                    report.ok("存储格式", f"_load_kline_store {elapsed:.1f}ms ({len(df)}行)")
            else:
                report.fail("存储格式", "_load_kline_store('000001') 返回空")
        except Exception as e:
            report.fail("存储格式", f"_load_kline_store 基准异常: {e}")

        # 8d. 确认cache.py无parquet引用
        try:
            cache_py = os.path.join(os.path.dirname(__file__), "cache.py")
            with open(cache_py, encoding="utf-8") as f:
                content = f.read()
            if "kline_parquet" in content:
                report.fail(
                    "存储格式",
                    "cache.py 仍引用 kline_parquet，双写未完全清除",
                    "检查 _load_kline_store / _save_kline_store 函数",
                )
            else:
                report.ok("存储格式", "cache.py 无parquet引用")
        except Exception:
            pass

    except Exception as e:
        report.fail("审计8", f"存储格式基准异常: {e}")


# ── 主入口 ──


def run_audit(auto_fix=True, verbose=True):
    """运行完整审计

    Args:
        auto_fix: 是否自动修复可修复的问题
        verbose: 是否输出详细信息

    Returns:
        AuditReport
    """
    # 先自动修复已知问题
    if auto_fix:
        for rule in AUTO_FIX_LIST:
            try:
                action = rule.get("action")
                if callable(action):
                    action()
            except Exception:
                pass

    report = AuditReport()
    t0 = time.time()

    checks = [
        ("数据一致性", audit_api_data_consistency),
        ("键名一致性", audit_internal_key_consistency),
        ("交叉验证", audit_cross_source_validation),
        ("评分有效性", audit_score_validity),
        ("性能监控", audit_performance),
        ("资金流向自检", audit_fund_flow_sign),
        ("API健康评分", audit_api_health),
        ("存储格式基准", audit_storage_benchmark),
    ]

    for name, check_fn in checks:
        try:
            check_fn(report)
        except Exception as e:
            report.fail(name, f"审计步骤异常: {e}")

    elapsed = time.time() - t0

    if verbose:
        print(f"\n{'=' * 50}")
        print(f"  自审计完成 ({elapsed:.1f}s)")
        print(f"{'=' * 50}")
        print(report.summary())

    return report


# ── CLI 集成 ──

if __name__ == "__main__":
    run_audit(auto_fix=True, verbose=True)
