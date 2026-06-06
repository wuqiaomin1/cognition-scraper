"""Gunicorn 配置 —— Render 部署用"""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', 10000)}"
workers = 2  # Render 免费 tier 512MB RAM
timeout = 120
worker_class = "sync"
loglevel = "info"
