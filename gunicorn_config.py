"""Gunicorn 配置 —— Render 部署用"""
import os

# 使用 Supabase 直连地址（Dashboard 获取的官方连接字符串）
# 直连用纯用户名 postgres，Pooler 才需要 postgres.xxx 格式
os.environ["DATABASE_URL"] = "postgresql://postgres:JhF4FwrVVXu8m9SB@db.pcsudvflktvoyljpajph.supabase.co:5432/postgres"

if not os.environ.get("ADMIN_PWD"):
    os.environ["ADMIN_PWD"] = "cognition2026"

bind = f"0.0.0.0:{os.environ.get('PORT', 10000)}"
workers = 2
timeout = 120
worker_class = "sync"
loglevel = "info"

# 打印连接信息方便调试
_db_url = os.environ.get("DATABASE_URL", "")
if _db_url:
    # 隐藏密码
    _safe = _db_url.split("@")[0].rsplit(":", 1)[0] + ":***@" + _db_url.split("@")[1] if "@" in _db_url else _db_url
    print(f"📊 DATABASE_URL = {_safe}")
