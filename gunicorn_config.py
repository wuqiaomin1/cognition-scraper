"""Gunicorn 配置 —— Render 部署用"""
import os

# Supabase 连接地址选择策略：
# - 直连 db.xxx.supabase.co 默认 IPv6，Render 不支持，会 Network unreachable
# - Pooler aws-0-xxx.pooler.supabase.com 走 IPv4，Render 可达
# - Pooler 用户名格式: postgres.[project-ref]（直连才是纯 postgres）
# - 项目恢复后 Pooler 才能识别 tenant
# Session mode pooler (port 5432) 支持 prepared statements，兼容 psycopg2
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
