"""feishu_bot 补充测试（2026-10-18：覆盖率 21.93% -> 目标 80%+）

补齐三个未覆盖的大函数：
- send_market_brief（四大指数 + 涨跌停统计 + 异常兜底）
- send_stock_picks（板块/个股/风险提示段落，字段缺省与截断）
- push_daily_picks（全链路：大盘→板块→选股→逐股分析→推送，两条 fallback）

patch 约定：函数体内延迟 import → patch 源模块属性；
同模块调用（send_post/send_market_brief）→ patch stock_analyzer.feishu_bot.xxx。
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from stock_analyzer import feishu_bot

MARKET = {
    "000001": {"最新价": 3200.0, "昨收": 3180.0},
    "399001": {"最新价": 10500.0, "昨收": 10600.0},
    "399006": {"最新价": 2100.0, "昨收": 0},  # 昨收 0 → 除零保护
    # 000688 缺失 → 价格 0 分支
}

SECTORS = {
    "半导体": {"涨跌幅": 3.5, "资金净流入": 5.2e9},
    "银行": {"涨跌幅": -1.2, "资金净流入": -1.1e9},
}


def _pick(**over):
    base = {
        "code": "600036",
        "name": "招商银行",
        "price": 42.45,
        "change_pct": 1.2,
        "score": 68.0,
        "rating": "A",
        "level": "strong",
        "near_5d": 2.5,
        "near_20d": -1.0,
        "sector": "银行",
        "sector_rank": 12,
        "signal": "金叉",
        "ai_direction": "看涨",
        "ai_confidence": 62,
        "entry_low": 41.0,
        "entry_high": 43.0,
        "stop_loss": 39.5,
        "take_profit": 45.8,
    }
    base.update(over)
    return base


# ══════════════════════════════════════════
#  send_market_brief
# ══════════════════════════════════════════


class TestSendMarketBrief:
    def test_normal_with_limit_stats(self):
        zt = pd.DataFrame({"涨跌幅": [10.0, 9.9, -10.0, 5.0]})
        with (
            patch("stock_analyzer.fetcher.get_market_overview", return_value=MARKET),
            patch("akshare.stock_zt_pool_em", return_value=zt),
            patch.object(feishu_bot, "send_post", return_value={"ok": True}) as sp,
        ):
            r = feishu_bot.send_market_brief("https://hook.test")
        assert r == {"ok": True}
        title = sp.call_args.args[0]
        assert "大盘简报" in title
        body = sp.call_args.args[1][0][0]["text"]
        assert "上证 3200.00 +0.63%" in body
        assert "深证 10500.00 -0.94%" in body
        assert "创业板 2100.00 +0.00%" in body  # 昨收 0 → 0%
        assert "涨停 2 只 | 跌停 1 只" in body

    def test_empty_zt_pool(self):
        with (
            patch("stock_analyzer.fetcher.get_market_overview", return_value=MARKET),
            patch("akshare.stock_zt_pool_em", return_value=pd.DataFrame()),
            patch.object(feishu_bot, "send_post", return_value={"ok": True}) as sp,
        ):
            feishu_bot.send_market_brief("https://hook.test")
        assert "涨停 0 只 | 跌停 0 只" in sp.call_args.args[1][0][0]["text"]

    def test_akshare_failure_keeps_index_lines(self):
        with (
            patch("stock_analyzer.fetcher.get_market_overview", return_value=MARKET),
            patch("akshare.stock_zt_pool_em", side_effect=RuntimeError("net")),
            patch.object(feishu_bot, "send_post", return_value={"ok": True}) as sp,
        ):
            feishu_bot.send_market_brief("https://hook.test")
        body = sp.call_args.args[1][0][0]["text"]
        assert "上证" in body
        assert "涨停" not in body  # 统计行缺失但指数行保留

    def test_outer_exception_returns_error(self):
        with patch("stock_analyzer.fetcher.get_market_overview", side_effect=RuntimeError("boom")):
            r = feishu_bot.send_market_brief("https://hook.test")
        assert r["ok"] is False
        assert "boom" in r["error"]


# ══════════════════════════════════════════
#  send_stock_picks
# ══════════════════════════════════════════


class TestSendStockPicks:
    def test_no_webhook(self):
        with patch.object(feishu_bot, "_webhook_url", return_value=""):
            r = feishu_bot.send_stock_picks([_pick()], [])
        assert r["ok"] is False
        assert "FEISHU_WEBHOOK_URL" in r["error"]

    def test_full_fields(self):
        with patch.object(feishu_bot, "send_post", return_value={"ok": True}) as sp:
            r = feishu_bot.send_stock_picks(
                [_pick()],
                [{"name": "半导体", "change_pct": 3.5, "fund_flow_yi": 52.0}],
                market_summary="上证 +0.6%",
                webhook_url="https://hook.test",
            )
        assert r == {"ok": True}
        paragraphs = sp.call_args.args[1]
        texts = [p[0]["text"] for p in paragraphs]
        assert any("【大盘】上证 +0.6%" in t for t in texts)
        assert any("【强势板块】" in t and "半导体" in t for t in texts)
        assert any("招商银行(600036)" in t and "评分68" in t for t in texts)
        assert any("买入 41.00~43.00" in t for t in texts)
        assert any("不构成投资建议" in t for t in texts)

    def test_missing_optional_fields(self):
        pick = _pick(entry_low=None)
        for k in ("score", "rating", "price", "sector_rank", "sector", "ai_direction"):
            pick.pop(k, None)
        with patch.object(feishu_bot, "send_post", return_value={"ok": True}) as sp:
            feishu_bot.send_stock_picks([pick], [], webhook_url="https://hook.test")
        texts = [p[0]["text"] for p in sp.call_args.args[1]]
        stock_txt = next(t for t in texts if "招商银行" in t)
        assert "评分0" in stock_txt
        assert "买入" not in stock_txt  # entry_low 缺省 → 不输出买入行

    def test_truncates_to_eight(self):
        picks = [_pick(code=f"60000{i}", name=f"股{i}") for i in range(12)]
        with patch.object(feishu_bot, "send_post", return_value={"ok": True}) as sp:
            feishu_bot.send_stock_picks(picks, [], webhook_url="https://hook.test")
        texts = [p[0]["text"] for p in sp.call_args.args[1]]
        assert sum("股" in t and "评分" in t for t in texts) == 8

    def test_watch_level_icon(self):
        with patch.object(feishu_bot, "send_post", return_value={"ok": True}) as sp:
            feishu_bot.send_stock_picks([_pick(level="watch")], [], webhook_url="https://hook.test")
        texts = [p[0]["text"] for p in sp.call_args.args[1]]
        assert any("⚪" in t for t in texts)


# ══════════════════════════════════════════
#  push_daily_picks
# ══════════════════════════════════════════


class TestPushDailyPicks:
    def test_no_webhook_prints_hint(self, capsys):
        with patch.object(feishu_bot, "_webhook_url", return_value=""):
            r = feishu_bot.push_daily_picks()
        out = capsys.readouterr().out
        assert "未配置 FEISHU_WEBHOOK_URL" in out
        assert r["ok"] is False

    def test_full_chain(self):
        cand = pd.DataFrame({"code": [600036, 2], "name": ["招行", "平安"]})
        analyzed = {
            "_kline": pd.DataFrame({"收盘": [42.0, 42.4]}),
            "price": 42.45,
            "qs_composite": 68,
            "qs_rating": "A",
            "near_5d": 2.5,
            "near_20d": -1.0,
            "macd_signal": "金叉",
        }
        with (
            patch("stock_analyzer.fetcher.get_market_overview", return_value=MARKET),
            patch("stock_analyzer.fetcher.get_sectors", return_value=SECTORS),
            patch(
                "stock_analyzer.fetcher.sina_real_time",
                return_value={"000002": {"名称": "平安银行", "最新价": 11.5, "昨收": 11.2}},
            ),
            patch("stock_analyzer.sector_info.get_stock_sector_full", return_value="金融 > 银行"),
            patch("stock_analyzer.enhanced_screener.enhanced_scan", return_value=cand),
            patch("stock_analyzer.analyzer.deep_analyze", return_value=analyzed),
            patch(
                "stock_analyzer.ml_predict.predict_ensemble",
                return_value={"ensemble_direction": "看涨", "ensemble_confidence": 60},
            ),
            patch.object(feishu_bot, "send_stock_picks", return_value={"ok": True}) as ssp,
        ):
            r = feishu_bot.push_daily_picks("https://hook.test")
        assert r == {"ok": True}
        picks, ranking, summary, url = ssp.call_args.args
        assert len(picks) == 2
        assert picks[0]["code"] in {"600036", "000002"}
        assert picks[0]["sector"] == "银行"
        assert picks[0]["level"] in {"strong", "buy"}
        assert "上证" in summary
        assert ranking and ranking[0]["name"] == "半导体"

    def test_screener_empty_falls_back_to_brief(self):
        with (
            patch("stock_analyzer.fetcher.get_market_overview", return_value=MARKET),
            patch("stock_analyzer.fetcher.get_sectors", return_value={}),
            patch("stock_analyzer.enhanced_screener.enhanced_scan", return_value=pd.DataFrame()),
            patch.object(feishu_bot, "send_market_brief", return_value={"ok": True}) as smb,
        ):
            r = feishu_bot.push_daily_picks("https://hook.test")
        assert r["ok"] is True
        assert "fallback" in r
        smb.assert_called_once()

    def test_screener_exception_falls_back(self):
        with (
            patch("stock_analyzer.fetcher.get_market_overview", return_value=MARKET),
            patch("stock_analyzer.fetcher.get_sectors", return_value={}),
            patch("stock_analyzer.enhanced_screener.enhanced_scan", side_effect=RuntimeError("x")),
            patch.object(feishu_bot, "send_market_brief", return_value={"ok": True}),
        ):
            r = feishu_bot.push_daily_picks("https://hook.test")
        assert r["ok"] is True

    def test_all_analyze_fail_falls_back(self):
        cand = pd.DataFrame({"code": ["600036"]})
        with (
            patch("stock_analyzer.fetcher.get_market_overview", return_value=MARKET),
            patch("stock_analyzer.fetcher.get_sectors", return_value={}),
            patch("stock_analyzer.enhanced_screener.enhanced_scan", return_value=cand),
            patch("stock_analyzer.analyzer.deep_analyze", side_effect=RuntimeError("boom")),
            patch.object(feishu_bot, "send_market_brief", return_value={"ok": True}) as smb,
        ):
            r = feishu_bot.push_daily_picks("https://hook.test")
        assert r["fallback"] == "无有效候选"
        smb.assert_called_once()

    def test_deep_analyze_none_skipped(self):
        cand = pd.DataFrame({"code": ["600036"]})
        with (
            patch("stock_analyzer.fetcher.get_market_overview", return_value=MARKET),
            patch("stock_analyzer.fetcher.get_sectors", return_value={}),
            patch("stock_analyzer.enhanced_screener.enhanced_scan", return_value=cand),
            patch("stock_analyzer.analyzer.deep_analyze", return_value=None),
            patch.object(feishu_bot, "send_market_brief", return_value={"ok": True}),
        ):
            r = feishu_bot.push_daily_picks("https://hook.test")
        assert "fallback" in r

    def test_watch_level_filtered_out(self):
        cand = pd.DataFrame({"code": ["600036"]})
        analyzed = {
            "_kline": pd.DataFrame({"收盘": [42.0]}),
            "qs_composite": 40,  # < 50 → watch
            "qs_rating": "C",
        }
        with (
            patch("stock_analyzer.fetcher.get_market_overview", return_value=MARKET),
            patch("stock_analyzer.fetcher.get_sectors", return_value={}),
            patch("stock_analyzer.fetcher.sina_real_time", return_value={}),
            patch("stock_analyzer.sector_info.get_stock_sector_full", return_value="银行"),
            patch("stock_analyzer.enhanced_screener.enhanced_scan", return_value=cand),
            patch("stock_analyzer.analyzer.deep_analyze", return_value=analyzed),
            patch("stock_analyzer.ml_predict.predict_ensemble", return_value={}),
            patch.object(feishu_bot, "send_stock_picks", return_value={"ok": True}) as ssp,
        ):
            feishu_bot.push_daily_picks("https://hook.test")
        # watch 级被过滤 → 空列表仍调用（上游仅在 picks 为空时 fallback，此处已过 fallback 判断）
        assert ssp.call_args.args[0] == []
