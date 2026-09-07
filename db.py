# -*- coding: utf-8 -*-
"""记账存储: SQLite单文件, 线程安全"""
import sqlite3
import threading

from config import DB_PATH

_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS records(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            openid   TEXT NOT NULL,
            tx_date  TEXT NOT NULL,           -- YYYY-MM-DD
            type     TEXT NOT NULL,           -- 支出 / 收入
            category TEXT NOT NULL,           -- 分类
            subcategory TEXT DEFAULT '',      -- 细分类
            amount   REAL NOT NULL,
            note     TEXT DEFAULT '',
            source   TEXT DEFAULT 'text',     -- text / voice / manual
            created_at TEXT DEFAULT (datetime('now','localtime')))""")
        # 迁移: 老库补充 subcategory 列
        cols = [r[1] for r in conn.execute("PRAGMA table_info(records)")]
        if "subcategory" not in cols:
            conn.execute("ALTER TABLE records ADD COLUMN subcategory TEXT DEFAULT ''")


def add_record(openid: str, tx_date: str, rtype: str, category: str,
               amount: float, note: str = "", source: str = "text",
               subcategory: str = ""):
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT INTO records(openid,tx_date,type,category,subcategory,"
            "amount,note,source) VALUES(?,?,?,?,?,?,?,?)",
            (openid, tx_date, rtype, category, subcategory, amount, note, source))


def _sums(where: str, args: tuple, openid: str) -> dict:
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT type, SUM(amount) AS s FROM records "
            f"WHERE openid=? AND {where} GROUP BY type", (openid, *args)).fetchall()
    d = {"支出": 0.0, "收入": 0.0}
    for r in rows:
        d[r["type"]] = round(r["s"] or 0, 2)
    return d


def today_stats(openid: str, today: str) -> dict:
    return _sums("tx_date=?", (today,), openid)


def month_stats(openid: str, month: str) -> dict:
    return _sums("substr(tx_date,1,7)=?", (month,), openid)


def month_by_category(openid: str, month: str) -> list:
    """本月各分类支出, 按金额降序"""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT category, SUM(amount) AS s FROM records "
            "WHERE openid=? AND type='支出' AND substr(tx_date,1,7)=? "
            "GROUP BY category ORDER BY s DESC", (openid, month)).fetchall()
    return [(r["category"], round(r["s"], 2)) for r in rows]


def recent_records(openid: str, limit: int = 5) -> list:
    """最近几笔记录(新→旧), 含id供删除用"""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, tx_date, type, category, subcategory, amount, note FROM records "
            "WHERE openid=? ORDER BY id DESC LIMIT ?", (openid, limit)).fetchall()
    return [dict(r) for r in rows]


def delete_record_by_match(openid: str, tx_date: str, kind: str, amount: float):
    """按日期+分类(或细分类)+金额删除一条账目; 多个匹配时删除最早的一笔
    返回(被删记录dict, 剩余相同记录数); 无匹配返回(None, 0)"""
    with _lock, _conn() as conn:
        rows = conn.execute(
            "SELECT id, tx_date, type, category, subcategory, amount, note FROM records "
            "WHERE openid=? AND tx_date=? AND (category=? OR subcategory=?) "
            "AND ABS(amount-?)<0.005 "
            "ORDER BY id", (openid, tx_date, kind, kind, amount)).fetchall()
        if not rows:
            return None, 0
        row = rows[0]
        conn.execute("DELETE FROM records WHERE id=?", (row["id"],))
    return dict(row), len(rows) - 1


def day_records(openid: str, day: str) -> list:
    """某一天的全部记录(旧→新), 含id供删除用"""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, tx_date, type, category, subcategory, amount, note FROM records "
            "WHERE openid=? AND tx_date=? ORDER BY id", (openid, day)).fetchall()
    return [dict(r) for r in rows]
