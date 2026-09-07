# -*- coding: utf-8 -*-
"""PythonAnywhere 定时任务专用: 每日推送收支日报到微信
用法(PA Scheduled Tasks, 每天 UTC 13:30 = 北京 21:30):
    python /home/你的用户名/wechat-ledger/daily_push.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
from report import push_daily


def main():
    with db._conn() as conn:
        openids = [r["openid"] for r in
                   conn.execute("SELECT DISTINCT openid FROM records")]
    if not openids:
        print("[daily_push] 数据库中暂无用户, 跳过")
        return
    for openid in openids:
        try:
            push_daily(openid)
            print(f"[daily_push] 已推送: {openid}")
        except Exception as e:
            print(f"[daily_push] 推送失败 {openid}: {e}")


if __name__ == "__main__":
    main()
