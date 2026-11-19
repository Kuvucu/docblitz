import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

DB = sqlite3.connect(os.getenv("DOCBLITZ_DB") or Path(__file__).parent / "bot.db", check_same_thread=False)
DB.executescript("""
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, seller TEXT, pro_until REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS docs(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT,
  number INTEGER, client TEXT, total REAL, created REAL);
CREATE TABLE IF NOT EXISTS payments(charge_id TEXT PRIMARY KEY, user_id INTEGER, stars INTEGER, created REAL);
""")


def _ensure(uid):
    DB.execute("INSERT OR IGNORE INTO users(id) VALUES(?)", (uid,))


def get_seller(uid):
    row = DB.execute("SELECT seller FROM users WHERE id=?", (uid,)).fetchone()
    return row[0] if row else None


def set_seller(uid, text):
    _ensure(uid)
    DB.execute("UPDATE users SET seller=? WHERE id=?", (text, uid))
    DB.commit()


def pro_until(uid):
    row = DB.execute("SELECT pro_until FROM users WHERE id=?", (uid,)).fetchone()
    return row[0] if row else 0


def is_pro(uid):
    return pro_until(uid) > time.time()


def add_pro(uid, days, charge_id, stars):
    _ensure(uid)
    start = max(pro_until(uid), time.time())
    DB.execute("UPDATE users SET pro_until=? WHERE id=?", (start + days * 86400, uid))
    DB.execute("INSERT OR IGNORE INTO payments VALUES(?,?,?,?)", (charge_id, uid, stars, time.time()))
    DB.commit()


def used_this_month(uid):
    first = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()
    return DB.execute("SELECT COUNT(*) FROM docs WHERE user_id=? AND created>=?", (uid, first)).fetchone()[0]


def next_number(uid, doc_type):
    n = DB.execute("SELECT MAX(number) FROM docs WHERE user_id=? AND type=?", (uid, doc_type)).fetchone()[0]
    return (n or 0) + 1


def save_doc(uid, doc_type, number, client, total):
    _ensure(uid)
    DB.execute("INSERT INTO docs(user_id,type,number,client,total,created) VALUES(?,?,?,?,?,?)",
               (uid, doc_type, number, client, total, time.time()))
    DB.commit()


def history(uid, limit=10):
    return DB.execute("SELECT type,number,client,total,created FROM docs WHERE user_id=? "
                      "ORDER BY id DESC LIMIT ?", (uid, limit)).fetchall()


def stats():
    q = lambda s: DB.execute(s).fetchone()[0]
    return {"users": q("SELECT COUNT(*) FROM users"), "docs": q("SELECT COUNT(*) FROM docs"),
            "pro": q(f"SELECT COUNT(*) FROM users WHERE pro_until>{time.time()}"),
            "stars": q("SELECT COALESCE(SUM(stars),0) FROM payments")}
