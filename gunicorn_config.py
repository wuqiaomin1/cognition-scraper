"""Gunicorn 配置 —— Render 部署用"""
import os

# 如果没有通过 Render 环境变量设置 DATABASE_URL，在这里设置默认值
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://postgres:JhF4FwrVVXu8m9SB@db.pcsudvflktvoyljpajph.supabase.co:5432/postgres"

if not os.environ.get("ADMIN_PWD"):
    os.environ["ADMIN_PWD"] = "cognition2026"

bind = f"0.0.0.0:{os.environ.get('PORT', 10000)}"
workers = 2  # Render 免费 tier 512MB RAM
timeout = 120
worker_class = "sync"
loglevel = "info"
