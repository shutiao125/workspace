# -*- coding: utf-8 -*-
"""全局配置: 全部支持环境变量覆盖, 也可直接改这里的默认值"""
import os

# ---------- 微信测试号配置 (申请地址: https://mp.weixin.qq.com/debug/cgi-bin/sandbox) ----------
WECHAT_TOKEN = os.getenv("WECHAT_TOKEN", "mytoken")          # 接口配置里的Token(自定义)
WECHAT_APPID = os.getenv("WECHAT_APPID", "wx2bc8c88a76b0cf50")               # 测试号信息的appID
WECHAT_SECRET = os.getenv("WECHAT_SECRET", "c9c708f06c57ebea87ce0ab1ce2267a9")            # 测试号信息的appsecret

# 每日推送用的测试号模板消息ID (测试号页面"模板消息接口"->新增测试模板后获得)
# 模板内容建议: 支出:{{expense.DATA}}  收入:{{income.DATA}}  {{remark.DATA}}
# 留空则退化为客服文本消息推送
DAILY_TEMPLATE_ID = os.getenv("DAILY_TEMPLATE_ID", "ifAqL7SDeoE8NIxKr4I9WZqMXrawdSHvJghNZbovito")

# 允许使用的openid白名单, 逗号分隔; 留空=不限制(测试号本来就只有你自己)
ALLOWED_OPENIDS = set(filter(None, os.getenv("ALLOWED_OPENIDS", "").split(",")))

# ---------- 大模型配置 (任意OpenAI兼容接口: 智谱/DeepSeek/通义/Kimi/SiliconFlow等) ----------
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")  # 智谱
LLM_API_KEY = os.getenv("LLM_API_KEY", "ac7679e620dc4ae88ec93ca915a180f8.MF3ZNUwR4eja7aMN")   # 有Key就填, 没有保持空串
LLM_MODEL = os.getenv("LLM_MODEL", "glm-4-flash")                     # flash模型免费额度充足

# ---------- 其他 ----------
DB_PATH = os.getenv("LEDGER_DB", "ledger.db")                         # SQLite文件路径
PUSH_TOKEN = os.getenv("PUSH_TOKEN", "ggglll")                        # 手动触发每日推送的口令
RUN_SCHEDULER = os.getenv("RUN_SCHEDULER", "1") == "1"                # 内置定时推送开关(本机运行用)
PUSH_HOUR = int(os.getenv("PUSH_HOUR", "21"))                         # 每日推送时间: 点
PUSH_MINUTE = int(os.getenv("PUSH_MINUTE", "30"))                     # 每日推送时间: 分
