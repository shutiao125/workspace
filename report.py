# -*- coding: utf-8 -*-
"""每日收支汇总: 生成报告文本 + 微信模板消息/客服消息推送"""
import datetime

import db
from config import DAILY_TEMPLATE_ID, LLM_API_KEY
from llm_parser import ai_report
from wechat import send_custom_text, send_template, send_mass_text


def build_daily_report(openid: str) -> str:
    today = datetime.date.today()
    month = today.strftime("%Y-%m")

    t = db.today_stats(openid, str(today))
    m = db.month_stats(openid, month)
    cats = db.month_by_category(openid, month)

    top = "、".join(f"{c} ¥{v}" for c, v in cats[:3]) if cats else "暂无"
    lines = [
        f"📊 记账日报 {today}",
        f"────────────",
        f"今日支出: ¥{t['支出']:.2f}",
        f"今日收入: ¥{t['收入']:.2f}",
        f"────────────",
        f"本月支出: ¥{m['支出']:.2f}",
        f"本月收入: ¥{m['收入']:.2f}",
        f"本月支出Top3: {top}",
    ]
    return "\n".join(lines)


def _week_range(today: datetime.date = None):
    """返回本周(周一~周日)的 (起 YYYY-MM-DD, 止 YYYY-MM-DD)"""
    today = today or datetime.date.today()
    start = today - datetime.timedelta(days=today.weekday())   # 周一=0
    end = start + datetime.timedelta(days=6)
    return start, end


def build_weekly_report(openid: str) -> str:
    start, end = _week_range()
    s, e = start.isoformat(), end.isoformat()
    w = db.week_stats(openid, s, e)
    cats = db.week_by_category(openid, s, e)
    daily = db.week_daily(openid, s, e)
    top = "、".join(f"{c} ¥{v}" for c, v in cats[:3]) if cats else "暂无"
    lines = [
        f"📊 记账周报 {start} ~ {end}",
        f"────────────",
        f"本周支出: ¥{w['支出']:.2f}",
        f"本周收入: ¥{w['收入']:.2f}",
        f"本周结余: ¥{w['收入'] - w['支出']:.2f}",
        f"支出Top3: {top}",
    ]
    if daily:
        lines.append(f"────────────")
        for d in daily:
            lines.append(f"{d['date'][5:]} 支出¥{d['支出']:.2f}")
    return "\n".join(lines)


def push_weekly(openid: str):
    """推送周报: 配置了模板ID用模板消息, 否则用群发文本"""
    start, end = _week_range()
    s, e = start.isoformat(), end.isoformat()
    w = db.week_stats(openid, s, e)
    text = build_weekly_report(openid)
    if DAILY_TEMPLATE_ID:
        send_template(openid, DAILY_TEMPLATE_ID, data={
            "expense": {"value": f"本周支出 ¥{w['支出']:.2f}"},
            "income":  {"value": f"本周收入 ¥{w['收入']:.2f}"},
            "remark":  {"value": f"周报 {start}~{end} 结余 ¥{w['收入'] - w['支出']:.2f}"},
        })
    else:
        send_custom_text(openid, text)


def push_daily(openid: str):
    """推送到微信: 配置了模板ID用模板消息, 否则用群发文本(个人订阅号每天1次)"""
    today = datetime.date.today()
    t = db.today_stats(openid, str(today))
    m = db.month_stats(openid, today.strftime("%Y-%m"))
    cats = db.month_by_category(openid, month:=today.strftime("%Y-%m"))
    text = build_daily_report(openid)

    # AI增强: 配置了LLM Key则生成简洁解读版日报, 失败自动退化纯文本
    if LLM_API_KEY:
        bal = round(m["收入"] - m["支出"], 2)
        bal_str = f"+{bal:.2f}" if bal > 0 else f"{bal:.2f}"
        data = {"月份": today.strftime("%Y-%m"), "expense": m["支出"],
                "income": m["收入"], "balance": bal_str,
                "分类支出": dict(cats)}
        ai_text = ai_report("今日收支日报" + today.strftime("%Y-%m"), data)
        if ai_text:
            text = f"📊 AI记账日报 {today}\n{ai_text}"

    if DAILY_TEMPLATE_ID:
        send_template(openid, DAILY_TEMPLATE_ID, data={
            "expense": {"value": f"¥{t['支出']:.2f}"},
            "income":  {"value": f"¥{t['收入']:.2f}"},
            "remark":  {"value": f"本月支出 ¥{m['支出']:.2f} / 收入 ¥{m['收入']:.2f}"},
        })
    else:
        send_custom_text(openid, text)
