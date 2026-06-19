"""HTML 报告生成 — 叙述文字生成函数

从 report_html.py 拆分而来，包含所有分析叙述文字的 HTML 生成函数。
"""


def _build_fundamental_narrative(detail: dict) -> str:
    """根据基本面数据生成中文叙述文字"""
    qs = detail.get("quant_score", {})
    fs = qs.get("factor_scores", {})
    fund_factor = fs.get("fundamental", {})
    fund_score = fund_factor.get("score")
    fund_details = fund_factor.get("details", {})

    parts = ['<div class="narrative-block">']
    parts.append('<div class="n-subtitle">基本面分析</div>')

    funda = detail.get("fundamentals")

    if isinstance(funda, dict) and funda.get("ROE") is not None:
        roe = funda.get("ROE", 0)
        if isinstance(roe, int | float):
            rev_growth = funda.get("营收增长", 0)
            net_growth = funda.get("净利润增长", 0)
            gross_margin = funda.get("毛利率", 0)
            net_margin = funda.get("净利率", 0)

            # ROE解读
            if roe > 15:
                roe_text = "优秀"
                roe_comment = "属于盈利能力很强的企业"
            elif roe > 8:
                roe_text = "良好"
                roe_comment = "盈利能力处于中等偏上水平"
            elif roe > 5:
                roe_text = "一般"
                roe_comment = "盈利能力处于中等水平"
            else:
                roe_text = "偏低"
                roe_comment = "盈利能力有待提升"

            sentences = [
                f"该股ROE（净资产收益率）为{roe:.1f}%，处于{roe_text}水平，{roe_comment}。"
                f"（A股参考：ROE>15%优秀，8-15%良好，5-8%一般，<5%偏低）"
            ]

            if isinstance(rev_growth, int | float):
                rev_pct = rev_growth * 100 if rev_growth < 1 else rev_growth
                if rev_pct > 30:
                    sentences.append(
                        f"营收增长{rev_pct:.1f}%，增速非常快，公司处于高速扩张期。（A股参考：营收增长>20%为较快，5-20%为稳定增长，<5%为增长乏力）"
                    )
                elif rev_pct > 20:
                    sentences.append(f"营收增长{rev_pct:.1f}%，增速较快，公司处于快速扩张阶段。")
                elif rev_pct > 5:
                    sentences.append(f"营收增长{rev_pct:.1f}%，业务保持稳定增长。")
                elif rev_pct > 0:
                    sentences.append(f"营收微增{rev_pct:.1f}%，增长动力偏弱。")
                else:
                    sentences.append(f"营收同比下降{abs(rev_pct):.1f}%，需关注业务下滑风险。")

            if isinstance(gross_margin, int | float):
                gm_pct = gross_margin * 100 if gross_margin < 1 else gross_margin
                if gm_pct > 70:
                    sentences.append(
                        f"毛利率{gm_pct:.1f}%，处于极高水平，产品或服务具有很强定价权和护城河。"
                    )
                elif gm_pct > 60:
                    sentences.append(
                        f"毛利率{gm_pct:.1f}%，处于较高水平，产品或服务具有较强定价权。（A股参考：毛利率>60%优秀，30-60%中等，<30%偏低）"
                    )
                elif gm_pct > 30:
                    sentences.append(f"毛利率{gm_pct:.1f}%，处于中等水平，盈利能力尚可。")
                else:
                    sentences.append(f"毛利率{gm_pct:.1f}%，相对偏低，产品或服务竞争较为激烈。")

            if isinstance(net_margin, int | float):
                nm_pct = net_margin * 100 if net_margin < 1 else net_margin
                if nm_pct > 20:
                    sentences.append(f"净利率{nm_pct:.1f}%，盈利质量很高，成本控制能力优秀。")
                elif nm_pct > 15:
                    sentences.append(f"净利率{nm_pct:.1f}%，盈利质量较高。")
                elif nm_pct > 5:
                    sentences.append(f"净利率{nm_pct:.1f}%，盈利质量处于中等水平。")

            if isinstance(net_growth, int | float):
                ng_pct = net_growth * 100 if net_growth < 1 else net_growth
                if ng_pct > 50:
                    sentences.append(f"净利润增长{ng_pct:.1f}%，爆发式增长，盈利能力大幅提升。")
                elif ng_pct > 30:
                    sentences.append(f"净利润增长{ng_pct:.1f}%，增长势头强劲。")

            parts.extend(f"<p>{s}</p>" for s in sentences)
    elif fund_score is not None:
        if fund_score >= 60:
            parts.append(
                f"<p>该股基本面评分为{fund_score:.0f}分，整体质地较好，财务健康度较高。</p>"
            )
        elif fund_score >= 40:
            parts.append(
                f"<p>该股基本面评分为{fund_score:.0f}分，处于中等水平，部分财务指标表现一般。</p>"
            )
        else:
            parts.append(
                f"<p>该股基本面评分为{fund_score:.0f}分，相对偏低，需关注公司经营状况的变化。</p>"
            )
    else:
        parts.append("<p>基本面数据暂缺，无法进行详细分析。</p>")

    parts.append("</div>")
    return "\n".join(parts)


def _build_technical_narrative(detail: dict) -> str:
    """根据技术指标数据生成中文叙述文字"""
    tech = detail.get("technical_summary", {})
    changes = detail.get("changes", {})

    parts = ['<div class="narrative-block">']
    parts.append('<div class="n-subtitle">技术面分析</div>')

    has_tech = bool(tech and isinstance(tech, dict))

    if has_tech:
        # MACD
        macd = tech.get("macd_signal", "")
        if macd in ("多头", "金叉"):
            if macd == "金叉":
                parts.append(
                    "<p><strong>MACD指标</strong>刚刚形成金叉信号（DIF线上穿DEA线），是趋势由弱转强的技术标志，短期看涨信号较强。"
                )
            else:
                parts.append(
                    "<p><strong>MACD指标</strong>处于多头区域，DIF线位于DEA线上方，表明短期内上涨动能占优，多头力量较强。"
                )
        elif macd in ("空头", "死叉"):
            if macd == "死叉":
                parts.append(
                    "<p><strong>MACD指标</strong>出现死叉信号（DIF线下穿DEA线），是趋势转弱的技术信号，短期需警惕进一步下行风险。"
                )
            else:
                parts.append(
                    "<p><strong>MACD指标</strong>处于空头区域，DIF线位于DEA线下方，短期趋势偏弱，空方力量占优。"
                )
        else:
            parts.append(
                "<p><strong>MACD指标</strong>处于多空交界状态，趋势方向尚不明确，需等待进一步确认。"
            )

        # RSI
        rsi_val = tech.get("rsi_value")
        rsi_sig = tech.get("rsi_signal", "")
        if rsi_val is not None:
            try:
                rv = float(rsi_val)
                if rv >= 80:
                    parts.append(
                        f"<p><strong>RSI指标</strong>为{rv:.0f}，处于严重超买区域（>80），说明近期涨幅较大，短期存在技术性回调压力，不宜追高。"
                    )
                elif rv > 70:
                    parts.append(
                        f"<p><strong>RSI指标</strong>为{rv:.0f}，处于超买区域（>70），短期可能存在回调需求，建议关注高位风险。"
                    )
                elif rv <= 20:
                    parts.append(
                        f"<p><strong>RSI指标</strong>为{rv:.0f}，处于严重超卖区域（<20），说明近期跌幅较大，可能存在超跌反弹机会。"
                    )
                elif rv < 30:
                    parts.append(
                        f"<p><strong>RSI指标</strong>为{rv:.0f}，处于超卖区域（<30），短期可能存在技术性反弹机会，可逢低关注。"
                    )
                else:
                    parts.append(
                        f"<p><strong>RSI指标</strong>为{rv:.0f}，处于中性区间（30-70），多空力量相对均衡，价格走势平稳。"
                    )
            except (TypeError, ValueError):
                parts.append("<p><strong>RSI指标</strong>数据异常，无法判断当前状态。")

        # KDJ
        kdj = tech.get("kdj_signal", "")
        if kdj == "金叉":
            parts.append(
                "<p><strong>KDJ指标</strong>出现金叉信号（K线上穿D线），是短期技术性买入信号，表明短期动能正在积聚。"
            )
        elif kdj == "死叉":
            parts.append(
                "<p><strong>KDJ指标</strong>出现死叉信号（K线下穿D线），是短期技术性卖出信号，预示短期调整或将开始。"
            )
        elif kdj == "超买":
            parts.append(
                "<p><strong>KDJ指标</strong>处于超买区域，K值和D值均偏高，短期存在回调需求。"
            )
        elif kdj == "超卖":
            parts.append(
                "<p><strong>KDJ指标</strong>处于超卖区域，K值和D值均偏低，短期可能存在反弹机会。"
            )

        # 均线排列
        ma_status = tech.get("ma_status", {})
        if ma_status:
            above = sum(1 for v in ma_status.values() if v.get("股价位置") == "上方")
            total_ma = len(ma_status)
            ma_keys = sorted(ma_status.keys())
            if above == total_ma:
                parts.append(
                    f"<p><strong>均线系统</strong>呈多头排列，股价位于全部主要均线（{'/'.join(ma_keys)}）之上，属于强势上涨格局，中期趋势向好。"
                )
            elif above >= total_ma / 2:
                up_list = [k for k, v in ma_status.items() if v.get("股价位置") == "上方"]
                down_list = [k for k, v in ma_status.items() if v.get("股价位置") != "上方"]
                parts.append(
                    f"<p>股价位于{','.join(up_list)}之上，但受到{','.join(down_list)}的压制，短期走势尚可但中期压力仍在。"
                )
            elif above > 0:
                up_list = [k for k, v in ma_status.items() if v.get("股价位置") == "上方"]
                down_list = [k for k, v in ma_status.items() if v.get("股价位置") != "上方"]
                parts.append(
                    f"<p>仅{','.join(up_list)}在股价之下，而{'、'.join(down_list)}均构成压力，整体趋势偏弱，需等待均线系统修复。"
                )
            else:
                parts.append(
                    "<p>股价位于全部主要均线之下，均线系统呈空头排列，整体处于弱势格局，建议等待企稳信号。"
                )

        # 近期涨跌幅
        ret5 = tech.get("近5日涨跌幅")
        ret20 = tech.get("近20日涨跌幅")
        if ret5 is not None and ret20 is not None:
            try:
                r5, r20 = float(ret5), float(ret20)
                if r5 > 5 and r20 > 10:
                    parts.append(
                        f"<p>近期表现强势，近5日上涨{r5:.1f}%，近20日上涨{r20:.1f}%，短中期均呈现上涨趋势，动量充足。"
                    )
                elif r5 < -5 and r20 < -10:
                    parts.append(
                        f"<p>近期表现承压，近5日下跌{abs(r5):.1f}%，近20日下跌{abs(r20):.1f}%，短中期趋势偏弱。"
                    )
                elif r20 > 5:
                    parts.append(f"<p>近期走势温和向上，近20日上涨{r20:.1f}%，中期趋势逐步改善。")
                elif r20 < -5:
                    parts.append(f"<p>中期趋势偏弱，近20日下跌{abs(r20):.1f}%，建议等待走势企稳。")
                else:
                    parts.append(
                        f"<p>近5日涨跌{r5:.1f}%，近20日涨跌{r20:.1f}%，走势相对平稳，无明显趋势性信号。"
                    )
            except (TypeError, ValueError):
                pass
    else:
        parts.append("<p>技术数据暂缺，无法进行技术面分析。</p>")

    parts.append("</div>")
    return "\n".join(parts)


def _build_risk_narrative(detail: dict) -> str:
    """根据风险指标数据生成中文叙述文字"""
    risk = detail.get("risk_metrics", {})
    stop = detail.get("stop_levels", {})

    parts = ['<div class="narrative-block">']
    parts.append('<div class="n-subtitle">风险评估</div>')

    has_risk = bool(risk and isinstance(risk, dict) and risk.get("sharpe_ratio") is not None)

    if has_risk:
        # 夏普比率
        sharpe = risk.get("sharpe_ratio")
        if sharpe is not None:
            try:
                s = float(sharpe)
                if s > 1:
                    parts.append(
                        f"<p><strong>风险调整后收益</strong>表现优秀。夏普比率为{s:.2f}（>1），每承担一单位风险获得了较高的超额回报，风险收益性价比较好。（A股参考：夏普比率>1优秀，0.5-1良好，0-0.5一般，<0需谨慎）"
                    )
                elif s > 0.5:
                    parts.append(
                        f"<p><strong>风险调整后收益</strong>处于中等偏上水平。夏普比率为{s:.2f}，收益基本能够覆盖风险，性价比较好。"
                    )
                elif s > 0:
                    parts.append(
                        f"<p><strong>风险调整后收益</strong>一般。夏普比率为{s:.2f}（>0），虽为正数但偏低，承担的风险未能充分转化为回报。"
                    )
                else:
                    parts.append(
                        f"<p><strong>风险调整后收益</strong>为负。夏普比率为{s:.2f}（<0），收益未能覆盖所承担的风险，当前风险收益特征不太理想。"
                    )
            except (TypeError, ValueError):
                pass

        # 最大回撤
        max_dd = risk.get("max_drawdown_pct")
        if max_dd is not None:
            try:
                dd = abs(float(max_dd))
                if dd < 10:
                    parts.append(
                        f"<p><strong>下行风险</strong>控制较好。历史最大回撤仅{dd:.1f}%，即使在极端行情下跌幅也相对有限，风险可控。（A股参考：最大回撤<10%优秀，10-20%良好，20-30%中等，>30%较大）"
                    )
                elif dd < 20:
                    parts.append(
                        f"<p><strong>下行风险</strong>控制尚可。历史最大回撤{dd:.1f}%，属于A股中较好水平，整体风险可控。"
                    )
                elif dd < 25:
                    parts.append(
                        f"<p><strong>下行风险</strong>处于中等水平。历史最大回撤{dd:.1f}%，属于A股正常波动范围，投资者仍需关注仓位管理。"
                    )
                elif dd < 35:
                    parts.append(
                        f"<p><strong>下行风险</strong>偏高。历史最大回撤{dd:.1f}%，该股历史上曾经历过较大幅度下跌，需注意极端行情风险。"
                    )
                else:
                    parts.append(
                        f"<p><strong>下行风险</strong>较大。历史最大回撤{dd:.1f}%，属于高波动品种，更适合风险承受能力较强的投资者。"
                    )
            except (TypeError, ValueError):
                pass

        # VaR
        var_val = risk.get("VaR_95_pct")
        if var_val is not None:
            try:
                var_abs = abs(float(var_val))
                if var_abs < 1.5:
                    parts.append(
                        f"<p><strong>尾部风险</strong>较低。在95%置信水平下，单日最大可能亏损不超过{var_abs:.1f}%，极端风险可控。（A股参考：VaR<2%较低，2-4%适中，>4%较高）"
                    )
                elif var_abs < 2:
                    parts.append(
                        f"<p><strong>尾部风险</strong>较低。在95%置信水平下，单日最大可能亏损不超过{var_abs:.1f}%，极端风险可控。"
                    )
                elif var_abs < 4:
                    parts.append(
                        f"<p><strong>尾部风险</strong>适中。单日VaR约{var_abs:.1f}%，极端行情下的潜在损失在可接受范围内。"
                    )
                else:
                    parts.append(
                        f"<p><strong>尾部风险</strong>较高。单日VaR达到{var_abs:.1f}%，极端行情下波动剧烈，需严格控制仓位。"
                    )
            except (TypeError, ValueError):
                pass

        # 波动率
        vol = risk.get("annualized_volatility_pct")
        if vol is not None:
            try:
                v = float(vol)
                if v < 20:
                    parts.append(
                        f"<p><strong>波动特征</strong>偏稳健。年化波动率{v:.1f}%，股价波动幅度较小，走势相对平稳。"
                    )
                elif v < 35:
                    parts.append(
                        f"<p><strong>波动特征</strong>中等。年化波动率{v:.1f}%，股价呈现正常波动。"
                    )
                else:
                    parts.append(
                        f"<p><strong>波动特征</strong>偏剧烈。年化波动率{v:.1f}%，价格波动频繁，交易时需注意仓位管理。"
                    )
            except (TypeError, ValueError):
                pass

        # 止损止盈参考
        sl = stop.get("止损参考价") if stop else None
        tp = stop.get("止盈参考价") if stop else None
        if sl and tp and isinstance(sl, int | float):
            sl_pct = stop.get("止损幅度%", "")
            tp_pct = stop.get("止盈幅度%", "")
            parts.append(
                f"<p><strong>交易区间参考</strong>：建议在{sl}设置止损（约{sl_pct}%），止盈目标参考{tp}（约{tp_pct}%），这是基于ATR波动率和支撑压力位计算的风险管理参考。"
            )
    else:
        parts.append("<p>风险数据暂缺，无法提供详细风险评估。</p>")

    parts.append("</div>")
    return "\n".join(parts)


def _build_trading_suggestion(detail: dict) -> str:
    """根据交易风格和信号生成操作建议"""
    ts = detail.get("trading_style", {})
    signals = detail.get("signals", {})
    stop = detail.get("stop_levels", {})

    parts = ['<div class="narrative-block">']
    parts.append('<div class="n-subtitle">操作建议</div>')

    style = ts.get("style", "")
    confidence = ts.get("style_confidence", "")
    short_score = ts.get("short_term_score", 0)
    long_score = ts.get("long_term_score", 0)

    style_map = {
        "短线": (
            "短线交易为主",
            "该股短线信号较为明确，适合波段操作。建议密切关注量价变化，严格执行止损纪律。",
        ),
        "长线": (
            "长线持有为主",
            "该股基本面扎实，适合中长期持有。不必过于在意短期价格波动，建议以基本面变化作为持有依据。",
        ),
        "短线+长线": (
            "同时适合短线交易和长线持有",
            "这类标的是较为理想的操作对象，短线可博取波段收益，长线可享受价值增长，兼具进攻和防守特性。",
        ),
        "观望": (
            "暂时观望",
            "当前市场信号不够明朗，不确定性较高，建议等待更清晰的趋势信号后再做决策。",
        ),
    }

    if style in style_map:
        style_name, style_desc = style_map[style]
        conf_text = f"（置信度：{confidence}）" if confidence else ""
        parts.append(
            f"<p>根据量化模型评估，该股<strong>更适合{style_name}</strong>{conf_text}。{style_desc}"
        )

        # 显示评分
        parts.append(
            f"<p><strong>量化评分</strong>：短线适宜度{short_score:.0f}分 / 长线适宜度{long_score:.0f}分。"
        )
    else:
        parts.append("<p>数据不足，无法提供操作建议。</p>")

    # 多空信号
    sig_summary = signals.get("signal_summary", {})
    bull_cnt = sig_summary.get("bullish_count", 0)
    bear_cnt = sig_summary.get("bearish_count", 0)
    if bull_cnt or bear_cnt:
        if bull_cnt > bear_cnt:
            parts.append(
                f"<p><strong>信号汇总</strong>：当前持有<strong>{bull_cnt}个看多信号</strong>、{bear_cnt}个看空信号，整体偏乐观。"
            )
        elif bear_cnt > bull_cnt:
            parts.append(
                f"<p><strong>信号汇总</strong>：当前持有{bull_cnt}个看多信号、<strong>{bear_cnt}个看空信号</strong>，整体偏谨慎。"
            )
        else:
            parts.append(
                f"<p><strong>信号汇总</strong>：当前持有{bull_cnt}个看多信号、{bear_cnt}个看空信号，多空力量均衡。"
            )

    # 短线/长线依据（复用 evaluate_trading_style 已生成的文字）
    short_basis = ts.get("short_term_basis", "")
    long_basis = ts.get("long_term_basis", "")
    if style in ("短线", "短线+长线") and short_basis:
        parts.append(f"<p><strong>短线依据：</strong>{short_basis}</p>")
    if style in ("长线", "短线+长线") and long_basis:
        parts.append(f"<p><strong>长线依据：</strong>{long_basis}</p>")

    # 止损止盈操作建议
    sl = stop.get("止损参考价") if stop else None
    tp = stop.get("止盈参考价") if stop else None
    if sl and tp and isinstance(sl, int | float):
        sl_pct = stop.get("止损幅度%", "")
        tp_pct = stop.get("止盈幅度%", "")
        parts.append(
            f"<p><strong>操作参考</strong>：建议将止损设在{sl}（约{sl_pct}%），目标止盈参考{tp}（约{tp_pct}%），严格执行纪律以控制风险。</p>"
        )

    parts.append("</div>")
    return "\n".join(parts)


def _build_news_section(detail: dict) -> str:
    """生成新闻舆情 HTML 块"""
    headlines = detail.get("news_headlines", [])
    times = detail.get("news_times", [])
    sources = detail.get("news_sources", [])
    if not headlines:
        return ""

    items_html = []
    for i, title in enumerate(headlines[:3]):
        t = times[i] if i < len(times) else ""
        s = sources[i] if i < len(sources) else ""
        meta = f"{t} | {s}" if t and s else (t or s or "")
        items_html.append(
            f"""<div class="news-item"><div class="news-title">{title}</div><div class="news-meta">{meta}</div></div>"""
        )

    return f"""<div class="sd-section">
          <div class="sd-section-title">最新舆情</div>
          <div class="sd-news-list">{"".join(items_html)}</div>
        </div>"""


def _build_stock_narrative(detail: dict) -> str:
    """组合所有叙述文字为完整 HTML"""
    sections = [
        _build_fundamental_narrative(detail),
        _build_technical_narrative(detail),
        _build_risk_narrative(detail),
        _build_trading_suggestion(detail),
    ]
    return '<div class="sd-narrative">\n' + "\n".join(sections) + "\n</div>"


def _build_operation_advice(detail: dict) -> str:
    """根据多维度数据生成短线/长线操作建议"""
    ts = detail.get("trading_style", {})
    tech = detail.get("technical_summary", {})
    risk = detail.get("risk_metrics", {})
    quant_score = detail.get("quant_score", {})
    fund_flow = detail.get("fund_flow", {}) or {}
    nt = detail.get("national_team", {}) or {}
    signals = detail.get("signals", {})

    short_score = ts.get("short_term_score", 50)
    long_score = ts.get("long_term_score", 50)
    funda_score = detail.get("fundamental_score", 50)
    rsi_val = tech.get("rsi_value", 50)
    near_5d = detail.get("near_5d_pct", 0)
    near_20d = detail.get("near_20d_pct", 0)
    max_dd = risk.get("max_drawdown_pct", 0)
    bias = signals.get("bias", "neutral")
    main_ratio = fund_flow.get("主力净流入-净占比", 0)
    has_nt = nt.get("has_national_team", False)
    qs_total = quant_score.get("total", 50) if isinstance(quant_score, dict) else 50

    if isinstance(main_ratio, str):
        try:
            main_ratio = float(main_ratio.replace("%", ""))
        except (ValueError, TypeError):
            main_ratio = 0

    parts = []
    parts.append('<div class="sd-section">')
    parts.append('<div class="sd-section-title">操作建议</div>')

    try:
        rsi_val = float(rsi_val)
    except (TypeError, ValueError):
        rsi_val = 50
    try:
        near_20d = float(near_20d)
    except (TypeError, ValueError):
        near_20d = 0
    try:
        near_5d = float(near_5d)
    except (TypeError, ValueError):
        near_5d = 0

    # 量化综合评分
    score = qs_total
    try:
        score = float(score)
    except (TypeError, ValueError):
        score = 50

    # 综合判断
    bull_count = 0
    bear_count = 0
    signals_found = []

    if rsi_val > 60:
        bull_count += 1
        signals_found.append("RSI偏强")
    elif rsi_val < 40:
        bear_count += 1
        signals_found.append("RSI偏弱")

    if near_5d > 3:
        bull_count += 1
        signals_found.append("近5日涨幅>3%")
    elif near_5d < -3:
        bear_count += 1
        signals_found.append("近5日跌幅>3%")

    if near_20d > 8:
        bull_count += 1
        signals_found.append("中期趋势向好")
    elif near_20d < -8:
        bear_count += 1
        signals_found.append("中期趋势偏弱")

    if main_ratio and float(main_ratio) > 0:
        bull_count += 1
        signals_found.append(f"主力净流入{main_ratio}%")
    elif main_ratio and float(main_ratio) < 0:
        bear_count += 1
        signals_found.append(f"主力净流出{abs(main_ratio)}%")

    if has_nt:
        bull_count += 1
        signals_found.append("国家队持股背书")

    if score >= 60:
        bull_count += 1
        signals_found.append(f"综合评分{score:.0f}")
    elif score < 40:
        bear_count += 1
        signals_found.append(f"综合评分{score:.0f}")

    if bias == "bullish":
        bull_count += 2
        signals_found.append("多头信号")
    elif bias == "bearish":
        bear_count += 2
        signals_found.append("空头信号")

    # 生成建议
    short_advice = ""
    long_advice = ""
    if short_score >= 60:
        short_advice = "短线可适当关注"
    elif short_score >= 40:
        short_advice = "短线机会一般"
    else:
        short_advice = "短线不宜介入"

    if long_score >= 60:
        long_advice = "长线持有价值较高"
    elif long_score >= 40:
        long_advice = "长线持有需观察"
    else:
        long_advice = "长线暂不具备优势"

    # 多空决策
    if bull_count > bear_count + 1:
        conclusion = "综合来看，积极信号占优，倾向于乐观"
        conclusion_color = "#2e7d32"
    elif bear_count > bull_count + 1:
        conclusion = "综合来看，警示信号偏多，建议审慎"
        conclusion_color = "#c62828"
    else:
        conclusion = "综合来看，多空信号接近，建议保持中性"
        conclusion_color = "#f9a825"

    parts.append(f"""
      <div class="sd-op-grid">
        <div class="sd-op-card" style="border-left:4px solid #e65100">
          <div class="sd-op-title">短线策略</div>
          <div class="sd-op-score">适宜度 {short_score}/100</div>
          <div class="sd-op-text">{short_advice}</div>
        </div>
        <div class="sd-op-card" style="border-left:4px solid #1565c0">
          <div class="sd-op-title">长线策略</div>
          <div class="sd-op-score">适宜度 {long_score}/100</div>
          <div class="sd-op-text">{long_advice}</div>
        </div>
        <div class="sd-op-card" style="border-left:4px solid {conclusion_color}">
          <div class="sd-op-title">综合结论</div>
          <div class="sd-op-score" style="color:{conclusion_color}">{bull_count}看多 / {bear_count}看空</div>
          <div class="sd-op-text">{conclusion}</div>
        </div>
      </div>""")

    short_extra = ""
    if short_score >= 60:
        if rsi_val > 70:
            short_extra = "<p style='font-size:12px;line-height:1.5;margin:0;color:#d32f2f'>⚠️ RSI偏高（超买），短线追高风险较大</p>"
        elif rsi_val < 30:
            short_extra = "<p style='font-size:12px;line-height:1.5;margin:0;color:#2e7d32'>💡 RSI偏低（超卖），可能存在超跌反弹机会</p>"

    long_extra = ""
    if long_score >= 60 and has_nt:
        long_extra = "<p style='font-size:12px;line-height:1.5;margin:0;color:#1565c0'>🏛️ 国家队持股提振长线信心</p>"

    parts.append(f"""
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;font-size:12px;color:#666">
      <div>
        {short_extra}
      </div>
      <div>
        {long_extra}
      </div>
    </div>""")

    parts.append("</div>")
    parts.append("</div>")
    return "\n".join(parts)
