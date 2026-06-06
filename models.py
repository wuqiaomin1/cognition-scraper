"""数据库操作层 —— SQLite 用户与配置管理"""
import sqlite3
import os
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = Path(__file__).parent / "data.db"


def get_db() -> sqlite3.Connection:
    """获取数据库连接（每次调用返回新连接，线程安全）"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # 提高并发性能
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表结构"""
    conn = get_db()
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
    """)
    conn.commit()
    conn.close()


def create_user(username: str, password: str) -> tuple[bool, str]:
    """创建用户，返回 (成功, 消息)"""
    conn = get_db()
    try:
        password_hash = generate_password_hash(password)
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash)
        )
        user_id = cursor.lastrowid
        # 自动创建默认配置
        conn.execute(
            "INSERT INTO user_config (user_id) VALUES (?)",
            (user_id,)
        )
        conn.commit()
        return True, f"注册成功，欢迎 {username}！"
    except sqlite3.IntegrityError:
        return False, "用户名已存在，请换一个试试"
    finally:
        conn.close()


def verify_user(username: str, password: str) -> dict | None:
    """验证用户登录，返回用户字典或 None"""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, username, password_hash, display_name FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            return dict(row)
        return None
    finally:
        conn.close()


def get_user_config(user_id: int) -> dict:
    """获取用户配置，返回字典"""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM user_config WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        if not row:
            # 创建默认配置
            conn.execute("INSERT INTO user_config (user_id) VALUES (?)", (user_id,))
            conn.commit()
            row = conn.execute(
                "SELECT * FROM user_config WHERE user_id = ?",
                (user_id,)
            ).fetchone()
        return dict(row)
    finally:
        conn.close()


def save_user_config(user_id: int, cfg: dict):
    """保存用户配置"""
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
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [user_id]
        conn.execute(
            f"UPDATE user_config SET {set_clause} WHERE user_id = ?",
            values
        )
        conn.commit()
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> dict | None:
    """根据 ID 获取用户"""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, username, display_name, created_at FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def row_to_config_dict(row: dict) -> dict:
    """将数据库行转换为配置字典格式（兼容前端）"""
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
