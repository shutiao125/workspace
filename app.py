# -*- coding: utf-8 -*-
"""微信测试号回调服务入口: 消息回调 + 记账 + 每日推送
运行: python app.py  (开发时配合内网穿透暴露公网HTTPS)
"""
import re
import threading
from datetime import datetime, timedelta

from flask import Flask, request

from config import (WECHAT_TOKEN, ALLOWED_OPENIDS, PUSH_TOKEN,
                    RUN_SCHEDULER, PUSH_HOUR, PUSH_MINUTE)
import wechat
import db
from llm_parser import parse_record, ai_report
from report import build_daily_report, push_daily

app = Flask(__name__)
db.init_db()

# MsgId去重(微信5秒无响应会重试推送)
_seen_msgs = set()
_seen_lock = threading.Lock()

WELCOME = (
    "👋 欢迎使用语音记账本!\n"
    "直接发消息即可记账, 例如:\n"
    "  午饭花了35块\n"
    "  昨天打车去机场68元\n"
    "  发工资啦 12000\n"
    "也可以直接发语音, 我会自动转文字记账。\n\n"
    "命令: 【今日】【本月】【最近】【分析】【帮助】"
)
HELP = ("📈 记账命令:\n"
        "  今日 —— 查看今天收支\n"
        "  本月 —— 查看本月收支与分类\n"
        "  最近 —— 查看最近5笔记录\n"
        "  查9月5日 —— 查看某天的账单(可带年份,如查2025年9月5日)\n"
        "  补记9月5日午饭30块 —— 补账到指定日期(日期支持20250902写法)\n"
        "  删除9月7日 餐饮 35 —— 删除匹配的账单\n"
        "  直接发文字/语音 —— 记一笔账\n"
        "  修改某笔: 先删除, 再重发一条正确的\n"
        "  分析 —— 分析本月收支\n"
        "  帮助 —— 查看帮助")


def _allowed(openid: str) -> bool:
    return not ALLOWED_OPENIDS or openid in ALLOWED_OPENIDS


def _is_duplicate(msg_id: str) -> bool:
    """微信5秒收不到响应会重推, 按MsgId去重"""
    with _seen_lock:
        if msg_id in _seen_msgs:
            return True
        _seen_msgs.add(msg_id)
        if len(_seen_msgs) > 5000:          # 防止集合无限增长
            _seen_msgs.clear()
        return False


def _compact_ymd(digits: str):
    """紧凑日期解析: 20250902 / 2025920 / 202592 -> (年, 月, 日)"""
    if not digits.isdigit() or len(digits) < 6:
        raise ValueError("日期位数不足")
    y = int(digits[:4])
    rest = digits[4:]
    if len(rest) == 4:
        m, d = int(rest[:2]), int(rest[2:])
    elif len(rest) == 3:
        m, d = int(rest[0]), int(rest[1:])
    else:
        m, d = int(rest[0]), int(rest[1])
    datetime(y, m, d)                       # 校验日期合法性(如2月30日会抛错)
    return y, m, d


def _cat_disp(r):
    """显示用分类: 大分类·细分类"""
    return r["category"] + (f"·{r.get('subcategory')}" if r.get("subcategory") else "")


def handle_record(openid: str, text: str, source: str) -> str:
    """同步解析并入库, 返回确认文本(作为被动回复, 未认证订阅号无客服消息接口)"""
    r = parse_record(text)
    sub = r.get("subcategory", "")
    db.add_record(openid, r["date"], r["type"], r["category"],
                  r["amount"], r["note"], source, sub)
    icon = "💸" if r["type"] == "支出" else "💰"
    return (f"{icon} 已记账 {r['date']}\n"
            f"{_cat_disp(r)} ¥{r['amount']:.2f} | {r['note']}\n"
            f"发送【今日】查看汇总")


@app.route("/wechat", methods=["GET", "POST"])
def wechat_callback():
    if request.method == "GET":
        # 测试号接口配置的URL验证
        if wechat.check_signature(WECHAT_TOKEN, request.args.get("signature", ""),
                                  request.args.get("timestamp", ""),
                                  request.args.get("nonce", "")):
            return request.args.get("echostr", "")
        return "签名校验失败", 403

    # ---------- POST: 消息处理 ----------
    if not wechat.check_signature(WECHAT_TOKEN, request.args.get("signature", ""),
                                  request.args.get("timestamp", ""),
                                  request.args.get("nonce", "")):
        return "success"
    msg = wechat.parse_xml(request.data)
    if not msg:
        return "success"

    openid = msg.get("FromUserName", "")
    msg_type = msg.get("MsgType", "")
    if not _allowed(openid):
        return "success"

    # 关注事件
    if msg_type == "event" and msg.get("Event") == "subscribe":
        return wechat.to_text_reply(msg.get("ToUserName", ""), openid, WELCOME)

    # 按MsgId去重
    if msg.get("MsgId") and _is_duplicate(msg["MsgId"]):
        return "success"

    # 提取文本: 文字消息 / 语音消息(优先微信自带识别)
    text, source = "", "text"
    if msg_type == "text":
        text = msg.get("Content", "").strip()
    elif msg_type == "voice":
        source = "voice"
        text = msg.get("Recognition", "").strip()
        if not text:
            # 微信未返回识别结果时的兜底提示(可在此接入腾讯云ASR)
            wechat.send_custom_text(
                openid, "🎤 未获取到语音识别结果, 请靠近点再说, "
                        "或直接打字发送~")
            return "success"
    else:
        return "success"

    if not text:
        return "success"

    # 紧凑日期规范化: 20250902/2025920 -> 2025年09月02日 (供查/补记/删除命令使用)
    m_c = re.match(r"^查\s*(\d{7,8})$", text)
    if m_c:
        try:
            y, mo, dy = _compact_ymd(m_c.group(1))
            text = f"查{y}年{mo}月{dy}日"
        except ValueError:
            return wechat.to_text_reply(msg.get("ToUserName", ""), openid,
                                        "❌ 日期无效, 示例: 查20250902 或 查9月5日")
    m_c = re.match(r"^(删除|补记)\s*(\d{7,8})\s+(.+)$", text)
    if m_c:
        try:
            y, mo, dy = _compact_ymd(m_c.group(2))
            text = f"{m_c.group(1)}{y}年{mo}月{dy}日 {m_c.group(3)}"
        except ValueError:
            return wechat.to_text_reply(msg.get("ToUserName", ""), openid,
                                        "❌ 日期无效, 示例: 补记20250902 午饭30块")

    # 快捷命令: 只查数据库, 同步回复(远快于5秒限制)
    today = datetime.now().strftime("%Y-%m-%d")
    if text in ("今日", "今天"):
        t = db.today_stats(openid, today)
        return wechat.to_text_reply(
            msg.get("ToUserName", ""), openid,
            f"📊 今日支出: ¥{t['支出']:.2f}\n📊 今日收入: ¥{t['收入']:.2f}")
    if text in ("本月", "月报"):
        month = datetime.now().strftime("%Y-%m")
        m = db.month_stats(openid, month)
        cats = db.month_by_category(openid, month)
        top = "、".join(f"{c} ¥{v}" for c, v in cats[:5]) if cats else "暂无"
        return wechat.to_text_reply(
            msg.get("ToUserName", ""), openid,
            f"📅 本月支出: ¥{m['支出']:.2f}\n📅 本月收入: ¥{m['收入']:.2f}\n"
            f"分类支出: {top}")
    if text in ("最近", "账单"):
        rows = db.recent_records(openid)
        if not rows:
            return wechat.to_text_reply(msg.get("ToUserName", ""), openid,
                                        "📭 还没有任何记账记录")
        lines = [f"{r['tx_date']} {_cat_disp(r)} ¥{r['amount']:.2f} "
                 f"{r['note']} [{r['type']}]"
                 for r in rows]
        return wechat.to_text_reply(
            msg.get("ToUserName", ""), openid,
            "📋 最近5笔:\n" + "\n".join(lines))
    # 查某天的账: 查9月5日(默认今年) / 查2025年9月5日
    m_q = re.match(r"^查\s*(?:(\d{4})年)?\s*(\d{1,2})月(\d{1,2})[日号]$", text)
    if m_q:
        year = int(m_q.group(1)) if m_q.group(1) else datetime.now().year
        try:
            day = f"{year}-{int(m_q.group(2)):02d}-{int(m_q.group(3)):02d}"
        except ValueError:
            return wechat.to_text_reply(msg.get("ToUserName", ""), openid,
                                        "❌ 日期无效, 示例: 查9月5日 或 查2025年9月5日")
        rows = db.day_records(openid, day)
        if not rows:
            return wechat.to_text_reply(msg.get("ToUserName", ""), openid,
                                        f"📭 {day} 没有账目记录")
        total = sum(r["amount"] for r in rows)
        lines = [f"{r['type']} {_cat_disp(r)} ¥{r['amount']:.2f} {r['note']}"
                 for r in rows]
        return wechat.to_text_reply(
            msg.get("ToUserName", ""), openid,
            f"📅 {day} 共{len(rows)}笔, 合计 ¥{total:.2f}:\n"
            + "\n".join(lines)
            + f"\n删除某条: 删除{day} 分类 金额")
    # 补记某天的账: 补记9月5日午饭30块(默认今年) / 补记2025年12月24日买礼物88元
    m_bu = re.match(r"^补记\s*(?:(\d{4})年)?\s*(\d{1,2})月(\d{1,2})[日号]\s*(.+)$", text) or \
           re.match(r"^补记\s*(?:(\d{4})-)?(\d{1,2})-(\d{1,2})\s+(.+)$", text)
    if m_bu:
        year = int(m_bu.group(1)) if m_bu.group(1) else datetime.now().year
        try:
            day = f"{year}-{int(m_bu.group(2)):02d}-{int(m_bu.group(3)):02d}"
        except ValueError:
            return wechat.to_text_reply(msg.get("ToUserName", ""), openid,
                                        "❌ 日期无效, 示例: 补记9月5日午饭30块")
        reply = handle_record(openid, m_bu.group(4).strip(), source, day)
        return wechat.to_text_reply(msg.get("ToUserName", ""), openid, reply)
    # 删除指定日期+分类+金额的账单 (较宽松): 删除9月7日 餐饮 35 / 删除9月7日餐饮35
    #   / 删除2026-09-07 餐饮 35 / 删除昨天 打车 20块 / 删除9月7日 餐饮:35
    m_del = re.match(
        r"^\s*删除\s*(?:"
        r"(?P<rel>今天|昨天)|"                         # 删除今天/昨天 …
        r"(?:(?P<y>\d{4})年)?\s*(?P<m>\d{1,2})月(?P<d>\d{1,2})[日号]|"  # 删除[YYYY年]M月D日 …
        r"(?P<y2>\d{4})[年/\-]?(?P<m2>\d{1,2})[月/\-]?(?P<d2>\d{1,2})[日号]?"  # 删除2026-09-07 / 2026/9/7 / 20260907
        r")"
        r"\s*[：:，,]?\s*"
        r"(?P<cat>\S+?)\s*[=：:，,\-]?\s*"
        r"(?P<amt>\d+(?:\.\d+)?)\s*[块元¥￥票]?\s*$",
        text)
    if m_del:
        if m_del.group("rel"):                       # 今天/昨天
            back = 1 if m_del.group("rel") == "昨天" else 0
            day_s = (datetime.now() - timedelta(days=back)).strftime("%Y-%m-%d")
        else:
            try:
                if m_del.group("m"):                 # M月D日 / YYYY年M月D日
                    year = int(m_del.group("y")) if m_del.group("y") else datetime.now().year
                    month, day = int(m_del.group("m")), int(m_del.group("d"))
                else:                                # YYYY-MM-DD / YYYY/MM/DD / YYYYMMDD
                    year = int(m_del.group("y2"))
                    month, day = int(m_del.group("m2")), int(m_del.group("d2"))
                day_s = f"{year}-{month:02d}-{day:02d}"
            except ValueError:
                return wechat.to_text_reply(msg.get("ToUserName", ""), openid,
                                            "❌ 日期无效, 示例: 删除9月7日 餐饮 35")
        category = m_del.group("cat")
        amount = round(float(m_del.group("amt")), 2)
        rec, more = db.delete_record_by_match(openid, day_s, category, amount)
        if rec is None:
            return wechat.to_text_reply(
                msg.get("ToUserName", ""), openid,
                f"❌ 没有找到匹配记录: {day_s} {category} ¥{amount:.2f}\n"
                f"可先发【查9月7日】核对该天的账目")
        reply = (f"🗑 已删除 {rec['tx_date']} {rec['category']} "
                 f"¥{rec['amount']:.2f} {rec['note']}")
        if more:
            reply += f"\n⚠️ 还有{more}条相同记录, 再次发送本命令可继续删除"
        return wechat.to_text_reply(msg.get("ToUserName", ""), openid, reply)
    if text in ("分析", "月度分析"):
        month = datetime.now().strftime("%Y-%m")
        m = db.month_stats(openid, month)
        cats = db.month_by_category(openid, month)
        if not cats:
            return wechat.to_text_reply(msg.get("ToUserName", ""), openid,
                                        "📭 本月暂无支出记录, 记账后再来分析~")
        data = {"月份": month, "总支出": m["支出"], "总收入": m["收入"],
                "分类支出": {c: v for c, v in cats}}
        analysis = ai_report("月度收支分析", data)
        if not analysis:
            return wechat.to_text_reply(msg.get("ToUserName", ""), openid,
                                        "🤖 AI分析暂不可用(未配置LLM Key或服务不可达)")
        return wechat.to_text_reply(msg.get("ToUserName", ""), openid,
                                    f"🤖 AI月度分析 {month}\n{analysis}")
    if text in ("帮助", "help", "指令"):
        return wechat.to_text_reply(msg.get("ToUserName", ""), openid, HELP)

    # 记账: 同步解析, 结果作为被动回复(未认证订阅号无客服消息接口)
    reply = handle_record(openid, text, source)
    return wechat.to_text_reply(msg.get("ToUserName", ""), openid, reply)


@app.route("/push/daily", methods=["POST", "GET"])
def push_daily_endpoint():
    """手动/外部定时触发每日推送: /push/daily?token=xxx"""
    if request.args.get("token") != PUSH_TOKEN:
        return "forbidden", 403
    with db._conn() as conn:
        openids = [r["openid"] for r in
                   conn.execute("SELECT DISTINCT openid FROM records")]
    results = {}
    for openid in openids or list(ALLOWED_OPENIDS):
        try:
            push_daily(openid)
            results[openid] = "ok"
        except Exception as e:
            results[openid] = str(e)
    return {"pushed": results}


def _start_scheduler():
    """内置定时推送(本机长期运行时启用: RUN_SCHEDULER=1)"""
    from apscheduler.schedulers.background import BackgroundScheduler
    sched = BackgroundScheduler(timezone="Asia/Shanghai")
    sched.add_job(push_daily_endpoint, "cron", hour=PUSH_HOUR, minute=PUSH_MINUTE)
    sched.start()
    print(f"[scheduler] 每日 {PUSH_HOUR:02d}:{PUSH_MINUTE:02d} 自动推送已启动")


if __name__ == "__main__":
    print(f"[config] 本次启动使用的Token: {WECHAT_TOKEN!r}  "
          f"(测试号页面填的Token必须与之一致)")
    if RUN_SCHEDULER:
        _start_scheduler()
    app.run(host="0.0.0.0", port=8000)
