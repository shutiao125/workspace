# -*- coding: utf-8 -*-
"""大模型解析记账文本: "午饭花了35块" -> {date, type, category, amount, note}
LLM未配置时自动退化为正则解析(只提取金额, 分类为其他)"""
import json
import re
import datetime

import requests

from config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL

CATEGORIES = "餐饮/交通/购物/娱乐/居住/医疗/教育/人情/工资/理财/其他"

PROMPT = """你是记账助手。从用户消息中解析出一笔记账, 只输出如下JSON, 不要任何其他内容:
{{"date":"YYYY-MM-DD","type":"支出|收入","category":"分类","amount":数字,"note":"简要备注"}}

规则:
1. "今天"是{today}, "昨天"是{yesterday}; 未提到日期默认今天
2. category 只能从 {cats} 中选择; 收入类(工资/红包/退款等)选工资或理财或其他
3. amount 为正数, 只保留数字部分; 未提到金额则amount填0
4. note 用不超过10个字概括消费内容
5. 收款/收到红包/到账 => type为收入; 其余默认支出"""

# 分类关键词兜底映射 (LLM不可用时使用)
KEYWORD_CATEGORY = [
    ("外卖|吃饭|午饭|晚饭|早饭|餐|奶茶|咖啡|食堂", "餐饮"),
    ("打车|地铁|公交|加油|停车|高铁|火车|机票|出租", "交通"),
    ("淘宝|京东|拼多多|购物|超市|买", "购物"),
    ("电影|游戏|KTV|旅游|会员", "娱乐"),
    ("房租|水电|燃气|物业", "居住"),
    ("医院|药|看病", "医疗"),
    ("书|课程|学费", "教育"),
    ("红包|礼金|随礼", "人情"),
    ("工资|到账|收入|进账|红包", "工资"),
]


def _llm_parse(text: str) -> dict | None:
    today = datetime.date.today()
    ctx = {"today": str(today), "yesterday": str(today - datetime.timedelta(days=1)),
           "cats": CATEGORIES}
    r = requests.post(f"{LLM_BASE_URL.rstrip('/')}/chat/completions",
                      headers={"Authorization": f"Bearer {LLM_API_KEY}"},
                      json={"model": LLM_MODEL, "temperature": 0,
                            "messages": [
                                {"role": "system", "content": PROMPT.format(**ctx)},
                                {"role": "user", "content": text},
                            ]},
                      timeout=3)   # 微信被动回复限时5秒, LLM超时自动退化正则
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"].strip()
    # 提取JSON(模型偶尔会带```json包裹)
    m = re.search(r"\{.*\}", content, re.S)
    data = json.loads(m.group())
    return {
        "date": data.get("date") or str(today),
        "type": data.get("type", "支出"),
        "category": data.get("category", "其他"),
        "amount": round(float(data.get("amount", 0)), 2),
        "note": data.get("note", text[:20]),
    }


def _regex_parse(text: str) -> dict:
    """无LLM时的兜底: 只保证金额和日期, 分类按关键词粗略匹配"""
    today = datetime.date.today()
    d = today - datetime.timedelta(days=1) if "昨天" in text else today
    m = re.search(r"(\d+(?:\.\d+)?)\s*[块元]", text) or re.search(r"[¥￥](\d+(?:\.\d+)?)", text) \
        or re.search(r"(\d+(?:\.\d+)?)", text)
    amount = round(float(m.group(1)), 2) if m else 0.0
    rtype = "收入" if any(k in text for k in ("工资", "到账", "收入", "进账", "收到红包")) else "支出"
    category, subcategory = "其他", ""
    for pattern, cat in KEYWORD_CATEGORY:
        if re.search(pattern, text):
            category = cat
            break
    return {"date": str(d), "type": rtype, "category": category,
            "subcategory": subcategory, "amount": amount, "note": text[:20]}


REPORT_PROMPT = """你是记账助手。以下是用户{month}月的收支统计(JSON):
{data}

请用中文简洁输出(60字以内)，只引用数据中的数字，不要新增数字，不要给任何建议，格式:
本月支出：¥{expense}
本月收入：¥{income}
结余：¥{balance}"""


def ai_report(kind: str, data: dict) -> str | None:
    """把数据库统计好的数据交给大模型生成解读报告; 失败/未配Key返回None"""
    if not LLM_API_KEY:
        return None
    try:
        fmt = dict(data) | {"month": kind.split("(")[0].replace("月度收支分析", ""), "data": json.dumps(data, ensure_ascii=False)}
        payload = {"model": LLM_MODEL, "temperature": 0.3,
                   "messages": [{"role": "system", "content": REPORT_PROMPT.format(
                       **fmt)},
                                {"role": "user", "content": "请生成报告"}]}
        r = requests.post(f"{LLM_BASE_URL.rstrip('/')}/chat/completions",
                          headers={"Authorization": f"Bearer {LLM_API_KEY}",
                                   "Content-Type": "application/json"},
                          data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                          timeout=15)   # 日报由定时任务触发, 无5秒限制, 用长超时
        if r.status_code != 200:
            print(f"[ai_report] HTTP {r.status_code}: {r.text[:300]}")
            return None
        return r.json()["choices"][0]["message"]["content"].strip() or None
    except Exception as e:
        print(f"[ai_report] 生成失败: {e}")
        return None


def parse_record(text: str) -> dict:
    """入口: 优先LLM解析, 失败/未配置则正则兜底"""
    if LLM_API_KEY:
        try:
            return _llm_parse(text)
        except Exception as e:
            print(f"[llm_parser] LLM解析失败, 使用正则兜底: {e}")
    return _regex_parse(text)
