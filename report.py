# -*- coding: utf-8 -*-
"""每日收支汇总: 生成报告文本 + 微信模板消息/客服消息推送"""
import datetime

import db
from config import DAILY_TEMPLATE_ID
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


def push_daily(openid: str):
    """推送到微信: 配置了模板ID用模板消息, 否则用群发文本(个人订阅号每天1次)"""
    today = datetime.date.today()
    t = db.today_stats(openid, str(today))
    m = db.month_stats(openid, today.strftime("%Y-%m"))
    cats = db.month_by_category(openid, month:=today.strftime("%Y-%m"))
    text = build_daily_report(openid)

    # AI增强: 配置了LLM Key则生成解读版日报, 失败自动退化纯文本
    if LLM_API_KEY:
        data = {"今日": t, "本月": m, "分类支出": dict(cats)}
        ai_text = ai_report("今日收支日报", data)
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
