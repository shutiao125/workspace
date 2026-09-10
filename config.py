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
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
LLM_API_KEY = os.getenv("LLM_API_KEY", "cf-enable")   # AI功能总开关: 非空即启用; 推理实际走Cloudflare(见下)
LLM_MODEL = os.getenv("LLM_MODEL", "glm-4-flash")

# ---------- Cloudflare Workers AI (AI分析/日报/年报的真实推理后端, 免费10k neurons/天) ----------
CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID", "ba4e567c939362ab8ef9be8dbd95d351")
CF_API_TOKEN  = os.getenv("CF_API_TOKEN", "")  # 敏感凭据, 勿提交git, 请用环境变量设置(见README/部署)
CF_MODEL      = os.getenv("CF_MODEL", "@cf/meta/llama-3.1-8b-instruct-fp8-fast")

# ---------- 其他 ----------
DB_PATH = os.getenv("LEDGER_DB", "ledger.db")                         # SQLite文件路径
PUSH_TOKEN = os.getenv("PUSH_TOKEN", "ggglll")                        # 手动触发每日推送的口令
RUN_SCHEDULER = os.getenv("RUN_SCHEDULER", "1") == "1"                # 内置定时推送开关(本机运行用)
PUSH_HOUR = int(os.getenv("PUSH_HOUR", "21"))                         # 每日推送时间: 点
PUSH_MINUTE = int(os.getenv("PUSH_MINUTE", "30"))                     # 每日推送时间: 分
