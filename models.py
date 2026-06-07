"""数据库操作层 —— 支持 PostgreSQL (Supabase) + SQLite 双模式"""
import os
import json
import time
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# 检测数据库类型
DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_PG = False
_PG_AVAILABLE = False

def _try_pg_connect(url, retries=2, delay=2):
    """尝试连接 PostgreSQL，自动在直连(IPv6)和Pooler(IPv4)之间切换"""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    # 准备备选连接地址
    urls_to_try = [url]

    # 如果是直连地址(db.xxx.supabase.co)，自动生成 Pooler 地址作为备选
    # 因为 Render 等 PaaS 不支持 IPv6，直连 Supabase 会 Network unreachable
    if "db." in url and ".supabase.co" in url:
        try:
            # 从直连地址提取 project-ref 和密码
            # 直连格式: postgresql://postgres:PASSWORD@db.REF.supabase.co:5432/postgres
            at_split = url.split("@")
            user_pwd = at_split[0].split("://")[1]  # postgres:PASSWORD
            password = user_pwd.split(":", 1)[1]
            ref = at_split[1].split(".supabase.co")[0].replace("db.", "")
            # 生成多个区域的 Pooler 地址
            for region in ["aws-0-ap-southeast-1", "aws-0-us-east-1", "aws-0-us-west-1", "aws-0-eu-west-1"]:
                pooler_url = f"postgresql://postgres.{ref}:{password}@{region}.pooler.supabase.com:5432/postgres"
                urls_to_try.append(pooler_url)
        except Exception as e:
            print(f"  生成 Pooler 地址失败: {e}")

    # 如果是 Pooler 地址，也尝试直连作为备选
    if "pooler.supabase.com" in url:
        try:
            user_pwd_part = url.split("://")[1].split("@")[0]
            ref = user_pwd_part.split(".postgres.")[1] if ".postgres." in user_pwd_part else user_pwd_part.split(".", 1)[1] if "." in user_pwd_part else ""
            password = user_pwd_part.split(":", 1)[1] if ":" in user_pwd_part else ""
            if ref and password:
                direct_url = f"postgresql://postgres:{password}@db.{ref}.supabase.co:5432/postgres"
                urls_to_try.append(direct_url)
        except Exception as e:
            print(f"  生成直连地址失败: {e}")

    for try_url in urls_to_try:
        for attempt in range(retries):
            try:
                connect_url = try_url
                if "?" not in connect_url:
                    connect_url += "?sslmode=require"
                elif "sslmode" not in connect_url:
                    connect_url += "&sslmode=require"
                conn = psycopg2.connect(connect_url, cursor_factory=RealDictCursor, connect_timeout=8)
                conn.close()
                print(f"  ✅ 连接成功: {try_url.split('@')[1][:40] if '@' in try_url else try_url[:40]}")
                return True, try_url
            except Exception as e:
                short = try_url.split("@")[1][:30] if "@" in try_url else try_url[:30]
                print(f"  PG 尝试 {attempt+1}/{retries} ({short}): {str(e)[:60]}")
                if attempt < retries - 1:
                    time.sleep(delay)
    return False, url

if DATABASE_URL:
    success, DATABASE_URL = _try_pg_connect(DATABASE_URL)
    if success:
        _PG_AVAILABLE = True
        USE_PG = True
        print(f"✅ PostgreSQL 连接成功")
    else:
        print(f"⚠️ PostgreSQL 连接失败（已重试3次），降级到 SQLite")
        USE_PG = False

if USE_PG:
    def get_db():
        import psycopg2
        from psycopg2.extras import RealDictCursor
        connect_url = DATABASE_URL
        if "?" not in connect_url:
            connect_url += "?sslmode=require"
        elif "sslmode" not in connect_url:
            connect_url += "&sslmode=require"
        try:
            conn = psycopg2.connect(connect_url, cursor_factory=RealDictCursor, connect_timeout=10)
            conn.autocommit = False
            return conn
        except Exception as e:
            print(f"PG 连接失败，尝试重连: {e}")
            # 重试一次
            time.sleep(1)
            conn = psycopg2.connect(connect_url, cursor_factory=RealDictCursor, connect_timeout=10)
            conn.autocommit = False
            return conn

    PH = "%s"
else:
    import sqlite3
    from pathlib import Path
    DB_PATH = Path(__file__).parent / "data.db"

    def get_db():
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    PH = "?"


def init_db():
    """初始化数据库表结构（兼容 PG 和 SQLite）"""
    conn = get_db()
    try:
        if USE_PG:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    display_name TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_config (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER UNIQUE NOT NULL REFERENCES users(id),
                    email_enabled INTEGER DEFAULT 0,
                    smtp_host TEXT DEFAULT 'smtp.qq.com',
                    smtp_port INTEGER DEFAULT 587,
                    sender_email TEXT DEFAULT '',
                    email_password TEXT DEFAULT '',
                    recipients TEXT DEFAULT '',
                    wechat_enabled INTEGER DEFAULT 0,
                    wechat_webhook TEXT DEFAULT '',
                    schedule_enabled INTEGER DEFAULT 1,
                    schedule_hour INTEGER DEFAULT 8,
                    schedule_minute INTEGER DEFAULT 0,
                    sources TEXT DEFAULT '36氪,虎嗅,极客公园,国务院政策文件库,巨潮资讯网'
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kb_items (
                    id TEXT PRIMARY KEY,
                    title TEXT DEFAULT '',
                    url TEXT DEFAULT '',
                    source TEXT DEFAULT '',
                    category TEXT DEFAULT '',
                    ai_summary TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    priority TEXT DEFAULT 'normal',
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_kb_state (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    item_id TEXT NOT NULL REFERENCES kb_items(id),
                    favorite INTEGER DEFAULT 0,
                    notes TEXT DEFAULT '',
                    read_count INTEGER DEFAULT 0,
                    last_viewed TIMESTAMP DEFAULT NULL,
                    UNIQUE(user_id, item_id)
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_reports (
                    date TEXT PRIMARY KEY,
                    markdown TEXT DEFAULT '',
                    data_json TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
        else:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    display_name TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS user_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL,
                    email_enabled INTEGER DEFAULT 0,
                    smtp_host TEXT DEFAULT 'smtp.qq.com',
                    smtp_port INTEGER DEFAULT 587,
                    sender_email TEXT DEFAULT '',
                    email_password TEXT DEFAULT '',
                    recipients TEXT DEFAULT '',
                    wechat_enabled INTEGER DEFAULT 0,
                    wechat_webhook TEXT DEFAULT '',
                    schedule_enabled INTEGER DEFAULT 1,
                    schedule_hour INTEGER DEFAULT 8,
                    schedule_minute INTEGER DEFAULT 0,
                    sources TEXT DEFAULT '36氪,虎嗅,极客公园,国务院政策文件库,巨潮资讯网',
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS kb_items (
                    id TEXT PRIMARY KEY,
                    title TEXT DEFAULT '',
                    url TEXT DEFAULT '',
                    source TEXT DEFAULT '',
                    category TEXT DEFAULT '',
                    ai_summary TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    priority TEXT DEFAULT 'normal',
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS user_kb_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    item_id TEXT NOT NULL,
                    favorite INTEGER DEFAULT 0,
                    notes TEXT DEFAULT '',
                    read_count INTEGER DEFAULT 0,
                    last_viewed TIMESTAMP DEFAULT NULL,
                    UNIQUE(user_id, item_id)
                );
                CREATE TABLE IF NOT EXISTS daily_reports (
                    date TEXT PRIMARY KEY,
                    markdown TEXT DEFAULT '',
                    data_json TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
        conn.commit()
    finally:
        conn.close()


# ==================== 用户操作 ====================

def create_user(username: str, password: str) -> tuple[bool, str]:
    conn = get_db()
    try:
        password_hash = generate_password_hash(password)
        cursor = conn.execute(
            f"INSERT INTO users (username, password_hash) VALUES ({PH}, {PH})",
            (username, password_hash)
        )
        if USE_PG:
            user_id = cursor.fetchone()[0]
        else:
            user_id = cursor.lastrowid
        conn.execute(
            f"INSERT INTO user_config (user_id) VALUES ({PH})",
            (user_id,)
        )
        conn.commit()
        return True, f"注册成功，欢迎 {username}！"
    except Exception as e:
        conn.rollback()
        if "unique" in str(e).lower() or "IntegrityError" in type(e).__name__:
            return False, "用户名已存在，请换一个试试"
        return False, f"注册失败: {e}"
    finally:
        conn.close()


def verify_user(username: str, password: str) -> dict | None:
    conn = get_db()
    try:
        row = conn.execute(
            f"SELECT id, username, password_hash, display_name FROM users WHERE username = {PH}",
            (username,)
        ).fetchone()
        if row:
            row_dict = dict(row)
            if check_password_hash(row_dict["password_hash"], password):
                return row_dict
        return None
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_db()
    try:
        row = conn.execute(
            f"SELECT id, username, display_name, created_at FROM users WHERE id = {PH}",
            (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ==================== 用户配置 ====================

def get_user_config(user_id: int) -> dict:
    conn = get_db()
    try:
        row = conn.execute(
            f"SELECT * FROM user_config WHERE user_id = {PH}",
            (user_id,)
        ).fetchone()
        if not row:
            conn.execute(f"INSERT INTO user_config (user_id) VALUES ({PH})", (user_id,))
            conn.commit()
            row = conn.execute(
                f"SELECT * FROM user_config WHERE user_id = {PH}",
                (user_id,)
            ).fetchone()
        return dict(row)
    finally:
        conn.close()


def save_user_config(user_id: int, cfg: dict):
    conn = get_db()
    try:
        fields = {
            "email_enabled": 1 if cfg.get("email", {}).get("enabled") else 0,
            "smtp_host": cfg.get("email", {}).get("smtp_host", "smtp.qq.com"),
            "smtp_port": cfg.get("email", {}).get("smtp_port", 587),
            "sender_email": cfg.get("email", {}).get("sender", ""),
            "email_password": cfg.get("email", {}).get("password", ""),
            "recipients": ",".join(cfg.get("email", {}).get("recipients", [])),
            "wechat_enabled": 1 if cfg.get("wechat", {}).get("enabled") else 0,
            "wechat_webhook": cfg.get("wechat", {}).get("webhook_url", ""),
            "schedule_enabled": 1 if cfg.get("schedule", {}).get("enabled", True) else 0,
            "schedule_hour": cfg.get("schedule", {}).get("hour", 8),
            "schedule_minute": cfg.get("schedule", {}).get("minute", 0),
            "sources": ",".join(cfg.get("sources", [])),
        }
        set_clause = ", ".join(f"{k} = {PH}" for k in fields)
        values = list(fields.values()) + [user_id]
        conn.execute(
            f"UPDATE user_config SET {set_clause} WHERE user_id = {PH}",
            values
        )
        conn.commit()
    except:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_to_config_dict(row: dict) -> dict:
    return {
        "email": {
            "enabled": bool(row.get("email_enabled")),
            "smtp_host": row.get("smtp_host", "smtp.qq.com"),
            "smtp_port": row.get("smtp_port", 587),
            "sender": row.get("sender_email", ""),
            "password": row.get("email_password", ""),
            "recipients": [r.strip() for r in row.get("recipients", "").split(",") if r.strip()],
        },
        "schedule": {
            "enabled": bool(row.get("schedule_enabled", True)),
            "hour": row.get("schedule_hour", 8),
            "minute": row.get("schedule_minute", 0),
        },
        "sources": [s.strip() for s in row.get("sources", "").split(",") if s.strip()],
        "wechat": {
            "enabled": bool(row.get("wechat_enabled")),
            "webhook_url": row.get("wechat_webhook", ""),
        },
    }


# ==================== 知识库条目 (kb_items) ====================

import hashlib

def _make_id(title: str, url: str) -> str:
    return hashlib.md5(f"{title}{url}".encode()).hexdigest()[:12]


def kb_add(item: dict) -> str:
    """添加一条知识库条目，返回ID"""
    item_id = _make_id(item.get("title", ""), item.get("url", ""))
    conn = get_db()
    try:
        # 检查是否已存在
        existing = conn.execute(
            f"SELECT id FROM kb_items WHERE id = {PH}", (item_id,)
        ).fetchone()
        if existing:
            return item_id

        tags_json = json.dumps(item.get("tags", []), ensure_ascii=False)
        conn.execute(
            f"""INSERT INTO kb_items (id, title, url, source, category, ai_summary, tags, priority)
                VALUES ({PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH})""",
            (item_id, item.get("title", ""), item.get("url", ""), item.get("source", ""),
             item.get("category", ""), item.get("ai_summary", ""), tags_json, item.get("priority", "normal"))
        )
        conn.commit()
        return item_id
    except:
        conn.rollback()
        return item_id
    finally:
        conn.close()


def kb_batch_add(items: list[dict]) -> int:
    """批量添加，返回新增数量"""
    count = 0
    for item in items:
        item_id = _make_id(item.get("title", ""), item.get("url", ""))
        conn = get_db()
        try:
            existing = conn.execute(
                f"SELECT id FROM kb_items WHERE id = {PH}", (item_id,)
            ).fetchone()
            if not existing:
                tags_json = json.dumps(item.get("tags", []), ensure_ascii=False)
                conn.execute(
                    f"""INSERT INTO kb_items (id, title, url, source, category, ai_summary, tags, priority)
                        VALUES ({PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH})""",
                    (item_id, item.get("title", ""), item.get("url", ""), item.get("source", ""),
                     item.get("category", ""), item.get("ai_summary", ""), tags_json, item.get("priority", "normal"))
                )
                conn.commit()
                count += 1
        except:
            conn.rollback()
        finally:
            conn.close()
    return count


def kb_search(query: str = "", category: str = None, limit: int = 50) -> list[dict]:
    """搜索知识库条目"""
    conn = get_db()
    try:
        sql = f"SELECT * FROM kb_items WHERE 1=1"
        params = []
        if category:
            sql += f" AND category = {PH}"
            params.append(category)
        if query:
            sql += f" AND (title ILIKE {PH} OR ai_summary ILIKE {PH} OR tags ILIKE {PH})" if USE_PG else \
                f" AND (title LIKE {PH} OR ai_summary LIKE {PH} OR tags LIKE {PH})"
            q = f"%{query}%"
            params.extend([q, q, q])
        sql += " ORDER BY added_at DESC"
        if limit:
            sql += f" LIMIT {limit}" if USE_PG else f" LIMIT {limit}"
        rows = conn.execute(sql, params).fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["tags"] = json.loads(d.get("tags", "[]"))
            results.append(d)
        return results
    finally:
        conn.close()


def kb_get_by_category(category: str) -> list[dict]:
    return kb_search(category=category, limit=200)


def kb_get_stats() -> dict:
    conn = get_db()
    try:
        total = conn.execute("SELECT COUNT(*) as cnt FROM kb_items").fetchone()
        categories = {}
        rows = conn.execute("SELECT category, COUNT(*) as cnt FROM kb_items GROUP BY category").fetchall()
        for row in rows:
            categories[row["category"] if USE_PG else row[0]] = row["cnt"] if USE_PG else row[1]
        sources = {}
        rows = conn.execute("SELECT source, COUNT(*) as cnt FROM kb_items GROUP BY source").fetchall()
        for row in rows:
            sources[row["source"] if USE_PG else row[0]] = row["cnt"] if USE_PG else row[1]
        last = conn.execute("SELECT MAX(added_at) as la FROM kb_items").fetchone()
        return {
            "total": total["cnt"] if USE_PG else total[0],
            "favorites": 0,  # 由 user_kb_state 计算
            "with_notes": 0,
            "categories": categories,
            "sources": sources,
            "last_updated": str(last["la"] if USE_PG else last[0]) if (last["la"] if USE_PG else last[0]) else ""
        }
    finally:
        conn.close()


def kb_get_recent(limit: int = 50) -> list[dict]:
    return kb_search(limit=limit)


def kb_export_all() -> list[dict]:
    """导出所有条目"""
    return kb_search(limit=9999)


# ==================== 用户知识库状态 ====================

def get_user_kb_state(user_id: int) -> dict:
    """获取用户的知识库状态（收藏/笔记/已读）"""
    conn = get_db()
    try:
        rows = conn.execute(
            f"SELECT item_id, favorite, notes, read_count, last_viewed FROM user_kb_state WHERE user_id = {PH}",
            (user_id,)
        ).fetchall()
        state = {"favorites": {}, "notes": {}, "read": {}}
        for row in rows:
            d = dict(row)
            item_id = d["item_id"]
            if d.get("favorite"):
                state["favorites"][item_id] = True
            if d.get("notes"):
                state["notes"][item_id] = d["notes"]
            if d.get("read_count", 0) > 0:
                state["read"][item_id] = d.get("last_viewed", "")
        return state
    finally:
        conn.close()


def toggle_user_favorite(user_id: int, item_id: str) -> bool:
    """切换收藏状态，返回当前是否收藏"""
    conn = get_db()
    try:
        existing = conn.execute(
            f"SELECT favorite FROM user_kb_state WHERE user_id = {PH} AND item_id = {PH}",
            (user_id, item_id)
        ).fetchone()
        if existing:
            new_val = 0 if dict(existing)["favorite"] else 1
            conn.execute(
                f"UPDATE user_kb_state SET favorite = {PH} WHERE user_id = {PH} AND item_id = {PH}",
                (new_val, user_id, item_id)
            )
        else:
            conn.execute(
                f"INSERT INTO user_kb_state (user_id, item_id, favorite) VALUES ({PH}, {PH}, {PH})",
                (user_id, item_id, 1)
            )
            new_val = 1
        conn.commit()
        return bool(new_val)
    except:
        conn.rollback()
        return False
    finally:
        conn.close()


def save_user_note(user_id: int, item_id: str, note: str):
    """保存用户笔记"""
    conn = get_db()
    try:
        existing = conn.execute(
            f"SELECT id FROM user_kb_state WHERE user_id = {PH} AND item_id = {PH}",
            (user_id, item_id)
        ).fetchone()
        if existing:
            conn.execute(
                f"UPDATE user_kb_state SET notes = {PH} WHERE user_id = {PH} AND item_id = {PH}",
                (note, user_id, item_id)
            )
        else:
            conn.execute(
                f"INSERT INTO user_kb_state (user_id, item_id, notes) VALUES ({PH}, {PH}, {PH})",
                (user_id, item_id, note)
            )
        conn.commit()
    except:
        conn.rollback()
    finally:
        conn.close()


def mark_user_read(user_id: int, item_id: str):
    """标记用户已读"""
    conn = get_db()
    try:
        existing = conn.execute(
            f"SELECT read_count FROM user_kb_state WHERE user_id = {PH} AND item_id = {PH}",
            (user_id, item_id)
        ).fetchone()
        if existing:
            cnt = dict(existing)["read_count"] + 1
            conn.execute(
                f"UPDATE user_kb_state SET read_count = {PH}, last_viewed = CURRENT_TIMESTAMP WHERE user_id = {PH} AND item_id = {PH}",
                (cnt, user_id, item_id)
            )
        else:
            conn.execute(
                f"INSERT INTO user_kb_state (user_id, item_id, read_count, last_viewed) VALUES ({PH}, {PH}, 1, CURRENT_TIMESTAMP)",
                (user_id, item_id)
            )
        conn.commit()
    except:
        conn.rollback()
    finally:
        conn.close()


# ==================== 日报存储 ====================

def save_daily_report(date_str: str, markdown: str, data_json: dict):
    """保存日报到数据库"""
    conn = get_db()
    try:
        data_str = json.dumps(data_json, ensure_ascii=False)
        existing = conn.execute(
            f"SELECT date FROM daily_reports WHERE date = {PH}", (date_str,)
        ).fetchone()
        if existing:
            conn.execute(
                f"UPDATE daily_reports SET markdown = {PH}, data_json = {PH} WHERE date = {PH}",
                (markdown, data_str, date_str)
            )
        else:
            conn.execute(
                f"INSERT INTO daily_reports (date, markdown, data_json) VALUES ({PH}, {PH}, {PH})",
                (date_str, markdown, data_str)
            )
        conn.commit()
    except:
        conn.rollback()
    finally:
        conn.close()


def get_daily_report(date_str: str) -> dict | None:
    """获取日报"""
    conn = get_db()
    try:
        row = conn.execute(
            f"SELECT * FROM daily_reports WHERE date = {PH}", (date_str,)
        ).fetchone()
        if row:
            d = dict(row)
            if isinstance(d.get("data_json"), str):
                d["data_json"] = json.loads(d["data_json"])
            return d
        return None
    finally:
        conn.close()


def get_report_history(limit: int = 30) -> list[dict]:
    """获取报告历史"""
    conn = get_db()
    try:
        rows = conn.execute(
            f"SELECT date, created_at FROM daily_reports ORDER BY date DESC LIMIT {limit}"
        ).fetchall()
        return [{"date": dict(r)["date"], "created_at": str(dict(r).get("created_at", ""))} for r in rows]
    finally:
        conn.close()
