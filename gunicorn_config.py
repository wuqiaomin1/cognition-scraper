"""Gunicorn 配置 —— Render 部署用"""
import os

# 如果没有通过 Render 环境变量设置 DATABASE_URL，在这里设置默认值
# 使用 Supabase Session pooler（端口5432），直连可能被防火墙拦截
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://postgres.pcsudvflktvoyljpajph:JhF4FwrVVXu8m9SB@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres"

if not os.environ.get("ADMIN_PWD"):
    os.environ["ADMIN_PWD"] = "cognition2026"

bind = f"0.0.0.0:{os.environ.get('PORT', 10000)}"
workers = 2
timeout = 120
worker_class = "sync"
loglevel = "info"
