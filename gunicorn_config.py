"""Gunicorn 配置 —— Render 部署用"""
import os

# 强制使用 Supabase Pooler 地址（直连地址在项目暂停恢复后可能DNS不可达）
# Pooler 地址更稳定，支持跨区域连接
DATABASE_URL = "postgresql://postgres.pcsudvflktvoyljpajph:JhF4FwrVVXu8m9SB@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres"
os.environ["DATABASE_URL"] = DATABASE_URL

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
