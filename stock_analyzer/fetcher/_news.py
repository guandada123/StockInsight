"""fetcher _news 子模块 —— 原样搬移自 __init__.py（2026-10-17 拆分，逻辑零改动）。"""

import functools
import json
import os
import random
import re
import time
from datetime import datetime, timedelta
from enum import Enum

import numpy as np
import pandas as pd
import requests

from ..config import HEADERS
from ..env import get_env
from ..logging_config import get_logger
from ..sectors_fallback import SECTOR_STOCKS_FALLBACK


def get_stock_news(code):
    """获取个股新闻（东方财富，带重试）

    使用 akshare 获取最近 100 条个股新闻。
    返回 DataFrame，包含：标题、内容、时间、来源、关键词。
    失败时返回空 DataFrame。
    """
    import akshare as ak

    try:
        df = ak.stock_news_em(symbol=code)
    except Exception:
        return pd.DataFrame()
    if df is not None and not df.empty:
        # 新版akshare列名: 关键词/新闻标题/新闻内容/发布时间/文章来源
        col_map = {}
        if "新闻标题" in df.columns:
            col_map["新闻标题"] = "标题"
        if "新闻内容" in df.columns:
            col_map["新闻内容"] = "内容"
        elif "内容摘要" in df.columns:
            col_map["内容摘要"] = "内容"
        if "发布时间" in df.columns:
            col_map["发布时间"] = "时间"
        if "文章来源" in df.columns:
            col_map["文章来源"] = "来源"
        if "关键词" in df.columns:
            col_map["关键词"] = "关键词"
        df = df.rename(columns=col_map)
        keep_cols = [c for c in ["标题", "内容", "时间", "来源", "关键词"] if c in df.columns]
        return df[keep_cols]
    return pd.DataFrame()


def get_market_news():
    """获取全市场财经要闻（财新/东方财富，带重试）

    返回 DataFrame，包含：标签(市场动态/公司要闻等)、摘要、URL。
    可用于判断当日市场情绪和重大事件。
    """
    import akshare as ak

    df = ak.stock_news_main_cx()
    if df is not None and not df.empty:
        col_map = {}
        if "tag" in df.columns:
            col_map["tag"] = "标签"
        if "summary" in df.columns:
            col_map["summary"] = "摘要"
        if "url" in df.columns:
            col_map["url"] = "链接"
        return df.rename(columns=col_map)
    return pd.DataFrame()


def analyze_news_sentiment(news_df, stock_name=""):
    """分析新闻情感倾向

    基于关键词+情感词典，对新闻标题和内容进行情感评分。
    返回: {sentiment_score: 0-100, direction: 'positive'/'neutral'/'negative',
            key_events: [事件关键词列表], risk_alert: bool}
    """
    if news_df is None or news_df.empty:
        return {
            "sentiment_score": 50,
            "direction": "neutral",
            "key_events": [],
            "risk_alert": False,
        }

    title_col = (
        "标题"
        if "标题" in news_df.columns
        else ("新闻标题" if "新闻标题" in news_df.columns else None)
    )
    content_col = (
        "内容"
        if "内容" in news_df.columns
        else ("新闻内容" if "新闻内容" in news_df.columns else None)
    )

    # 情感词典
    positive_words = [
        "利好",
        "大涨",
        "突破",
        "增长",
        "盈利",
        "分红",
        "回购",
        "创新高",
        "买入",
        "增持",
        "涨停",
        "中标",
        "合同",
        "扭亏",
        "超预期",
        "扩产",
        "订单",
        "政策支持",
        "国产替代",
        "放量",
    ]
    negative_words = [
        "利空",
        "大跌",
        "亏损",
        "减持",
        "风险",
        "处罚",
        "诉讼",
        "退市",
        "下调",
        "跌停",
        "违约",
        "调查",
        "破产",
        "ST",
        "警示",
        "问责",
        "制裁",
        "关税",
        "限售",
        "暴雷",
    ]
    event_keywords = [
        "政策",
        "关税",
        "制裁",
        "重组",
        "并购",
        "定增",
        "业绩",
        "分红",
        "回购",
        "减持",
        "解禁",
        "立案",
        "停牌",
        "复牌",
        "涨停",
        "跌停",
        "龙虎榜",
        "大宗交易",
    ]

    all_text = ""
    if title_col:
        titles = news_df[title_col].head(20).tolist()
        all_text += " ".join(str(t) for t in titles)
    if content_col:
        contents = news_df[content_col].head(10).tolist()
        all_text += " " + " ".join(str(c)[:200] for c in contents)

    pos_count = sum(1 for w in positive_words if w in all_text)
    neg_count = sum(1 for w in negative_words if w in all_text)
    events_found = [w for w in event_keywords if w in all_text]

    if pos_count + neg_count == 0:
        score = 50
        direction = "neutral"
    else:
        ratio = pos_count / (pos_count + neg_count)
        score = 50 + (ratio - 0.5) * 80  # 10-90范围
        score = max(10, min(90, score))
        if ratio > 0.6:
            direction = "positive"
        elif ratio < 0.4:
            direction = "negative"
        else:
            direction = "neutral"

    return {
        "sentiment_score": round(score, 1),
        "direction": direction,
        "key_events": events_found[:5],
        "risk_alert": direction == "negative" and len(events_found) > 0,
        "positive_hits": pos_count,
        "negative_hits": neg_count,
    }


def get_market_news_digest():
    """获取当日市场消息摘要（板块级+市场级）

    返回: {summary: 一句话总结, hot_sectors: [热门板块],
            key_events: [重大事件], sentiment: '偏多'/'偏空'/'中性'}
    """
    news = get_market_news()
    if news.empty:
        return {"summary": "暂无市场要闻", "hot_sectors": [], "key_events": [], "sentiment": "中性"}

    # 按标签分类
    tags = news["标签"].value_counts().head(5).to_dict() if "标签" in news.columns else {}

    # 提取板块关键词
    sector_keywords = [
        "半导体",
        "新能源",
        "医药",
        "消费",
        "金融",
        "地产",
        "汽车",
        "AI",
        "算力",
        "光伏",
        "锂电",
        "军工",
        "有色",
        "化工",
        "电力",
        "基建",
        "通信",
        "传媒",
        "农业",
    ]
    all_summaries = " ".join(news["摘要"].head(30).tolist()) if "摘要" in news.columns else ""
    hot_sectors = [s for s in sector_keywords if s in all_summaries]

    # 情感判断
    pos_words_in_news = ["上涨", "大涨", "利好", "突破", "增长", "政策支持", "回暖"]
    neg_words_in_news = ["下跌", "大跌", "利空", "风险", "制裁", "关税", "调整"]
    pos = sum(1 for w in pos_words_in_news if w in all_summaries)
    neg = sum(1 for w in neg_words_in_news if w in all_summaries)

    if pos > neg * 1.5:
        sentiment = "偏多"
    elif neg > pos * 1.5:
        sentiment = "偏空"
    else:
        sentiment = "中性"

    # 生成一句话总结
    tag_str = "、".join(list(tags.keys())[:3])
    sector_str = "、".join(hot_sectors[:4]) if hot_sectors else "无突出板块"
    summary = f"今日要闻聚焦{tag_str}；热门板块：{sector_str}；市场情绪{sentiment}"

    return {
        "summary": summary,
        "hot_sectors": hot_sectors[:5],
        "key_tags": tags,
        "sentiment": sentiment,
        "news_count": len(news),
    }


def get_weibo_sentiment():
    """获取微博舆情评分（金十数据，带重试）

    返回 DataFrame：股票名称 → 情绪评分（-1 到 +1，正数正面）。
    """
    import akshare as ak

    df = ak.stock_js_weibo_report(time_period="CNHOUR24")
    return df if df is not None and not df.empty else pd.DataFrame()


def get_stock_research(code):
    """获取券商研报与盈利预测（东方财富，带重试）"""
    import akshare as ak

    df = ak.stock_research_report_em(symbol=code)
    if df is not None and not df.empty:
        cols = {"研究报告标题": "研报标题", "评级": "评级", "机构": "券商", "行业": "行业"}
        for c in df.columns:
            if "盈利预测" in c:
                cols[c] = c
        return df[[c for c in cols if c in df.columns]].rename(columns=cols)
    return pd.DataFrame()
