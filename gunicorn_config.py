"""Gunicorn 配置 —— Render 部署用"""
import os

# 如果没有通过 Render 环境变量设置，在这里设置默认值
# 优先使用 Supabase Session pooler，备选直连地址
if not os.environ.get("DATABASE_URL"):
    # Supabase Session Mode Pooler (推荐，跨区域可用)
    os.environ["DATABASE_URL"] = "postgresql://postgres.pcsudvflktvoyljpajph:JhF4FwrVVXu8m9SB@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres"

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
