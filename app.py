"""认知作弊信息抓取系统 v6 —— 多用户版 + 云数据库 + 持久化存储"""
import os
import json
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, session
from apscheduler.schedulers.background import BackgroundScheduler

from scraper import (
    Kr36Scraper, HuxiuScraper, GeekparkScraper,
    PolicyScraper, CninfoScraper,
    ReportGeneratorV2, CATEGORIES,
    WeChatPusher, format_wechat_chat_message
)
from scraper.ai_assistant import AIAssistant
from models import (
    init_db, get_user_config, save_user_config, row_to_config_dict,
    kb_add, kb_batch_add, kb_search, kb_get_stats, kb_get_by_category, kb_export_all,
    get_user_kb_state, toggle_user_favorite, save_user_note, mark_user_read,
    save_daily_report, get_daily_report, get_report_history, USE_PG
)
from auth import auth_bp, login_required

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'cognition-scraper-v6-2026')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

app.register_blueprint(auth_bp)

# 初始化数据库
init_db()

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

scheduler = BackgroundScheduler()
scrape_status = {"running": False, "last_run": None, "progress": ""}

# AI助手
ai_assistant = AIAssistant(None)


# ==================== 用户配置管理 ====================

def get_current_config() -> dict:
    user_id = session.get('user_id')
    if user_id:
        try:
            row = get_user_config(user_id)
            return row_to_config_dict(row)
        except Exception:
            pass
    return load_config()


def load_config() -> dict:
    CONFIG_FILE = Path(__file__).parent / "config.json"
    defaults = {
        "email": {"enabled": False, "smtp_host": "smtp.qq.com", "smtp_port": 587,
                  "sender": "", "password": "", "recipients": []},
        "schedule": {"enabled": True, "hour": 8, "minute": 0},
        "sources": ["36氪", "虎嗅", "极客公园", "国务院政策文件库", "巨潮资讯网"],
        "push_categories": ["🏛️ 政策/宏观", "🤖 AI/技术", "💼 商业/创业", "💰 投资/财报", "🛒 消费/市场"],
        "wechat": {"enabled": False, "webhook_url": "", "push_categories": []}
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            for k, v in defaults.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
        except:
            pass
    return defaults


def save_config(cfg: dict):
    CONFIG_FILE = Path(__file__).parent / "config.json"
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ==================== 抓取核心 ====================

def get_scrapers(sources: list[str] = None) -> dict:
    all_scrapers = {
        "36氪": Kr36Scraper(),
        "虎嗅": HuxiuScraper(),
        "极客公园": GeekparkScraper(),
        "国务院政策文件库": PolicyScraper(),
        "巨潮资讯网": CninfoScraper()
    }
    if sources:
        return {k: v for k, v in all_scrapers.items() if k in sources}
    return all_scrapers


def run_scrape(send_email: bool = False, user_id: int = None):
    global scrape_status
    scrape_status["running"] = True

    try:
        if user_id:
            try:
                row = get_user_config(user_id)
                cfg = row_to_config_dict(row)
            except:
                cfg = load_config()
        else:
            cfg = load_config()

        sources = cfg.get("sources", [])
        scrapers = get_scrapers(sources)

        # 1. 抓取
        all_results = {}
        for name, scraper in scrapers.items():
            scrape_status["progress"] = f"正在抓取 {name}..."
            try:
                items = scraper.fetch()
                all_results[name] = items
            except Exception as e:
                print(f"[{name}] 抓取异常: {e}")
                all_results[name] = []

        # 2. 生成分类日报
        scrape_status["progress"] = "正在AI摘要与分类..."
        generator = ReportGeneratorV2(str(OUTPUT_DIR))
        kb_stats = kb_get_stats()
        report_result = generator.generate(all_results, kb_stats)

        # 3. 入知识库（数据库持久化）
        scrape_status["progress"] = "正在更新知识库..."
        new_count = kb_batch_add(report_result["all_analyzed"])

        # 4. 保存日报到数据库
        today = datetime.now().strftime("%Y-%m-%d")
        save_daily_report(today, report_result["markdown"], report_result.get("data", {}))

        # 同时保存文件（兼容旧逻辑）
        try:
            md_path = OUTPUT_DIR / f"日报_{today}.md"
            md_path.write_text(report_result["markdown"], encoding='utf-8')
            data_path = OUTPUT_DIR / f"data_{today}.json"
            data_path.write_text(json.dumps(report_result.get("data", {}), ensure_ascii=False, indent=2), encoding='utf-8')
            latest_path = OUTPUT_DIR / "latest.md"
            latest_path.write_text(report_result["markdown"], encoding='utf-8')
        except Exception as e:
            print(f"保存文件失败(不影响运行): {e}")

        # 5. 发送邮件
        email_cfg = cfg.get("email", {})
        if send_email and email_cfg.get("enabled") and email_cfg.get("sender"):
            scrape_status["progress"] = "正在发送邮件..."
            send_report_email(report_result["markdown"], email_cfg)

        # 6. 微信推送
        wechat_cfg = cfg.get("wechat", {})
        if wechat_cfg.get("enabled") and wechat_cfg.get("webhook_url"):
            scrape_status["progress"] = "正在推送到微信..."
            try:
                pusher = WeChatPusher(wechat_cfg["webhook_url"])
                push_cats = wechat_cfg.get("push_categories", []) or None
                result = pusher.push_daily_report(report_result, push_cats)
                if result["ok"]:
                    scrape_status["progress"] = f"完成！新增{new_count}条知识，已推送到微信"
                else:
                    scrape_status["progress"] = f"完成！新增{new_count}条知识，微信推送部分失败"
            except Exception as e:
                print(f"微信推送失败: {e}")
        else:
            scrape_status["progress"] = f"完成！新增{new_count}条知识"

        scrape_status["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        scrape_status["progress"] = f"错误: {str(e)}"
        print(f"抓取任务失败: {e}")
    finally:
        scrape_status["running"] = False


def send_report_email(content: str, email_cfg: dict):
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"认知作弊情报日报 - {datetime.now().strftime('%Y-%m-%d')}"
        msg['From'] = email_cfg['sender']
        msg['To'] = ', '.join(email_cfg.get('recipients', []))

        html_content = content.replace('\n', '<br>')
        html_content = html_content.replace('## ', '<h2>').replace('<br><h2>', '<h2>')
        html_content = html_content.replace('### ', '<h3>').replace('<br><h3>', '<h3>')
        html_content = html_content.replace('# ', '<h1>').replace('<br><h1>', '<h1>')
        html_content = html_content.replace('**', '<strong>').replace('</strong><br><strong>', '')

        msg.attach(MIMEText(html_content, 'html', 'utf-8'))

        port = email_cfg['smtp_port']
        if port == 465:
            server = smtplib.SMTP_SSL(email_cfg['smtp_host'], port, timeout=30)
        else:
            server = smtplib.SMTP(email_cfg['smtp_host'], port, timeout=30)
            server.starttls()
        server.login(email_cfg['sender'], email_cfg['password'])
        server.send_message(msg)
        server.quit()
        print(f"邮件发送成功")
    except Exception as e:
        print(f"邮件发送失败: {e}")


# ==================== 页面路由 ====================

@app.route('/')
@login_required
def index():
    return send_from_directory('static', 'index.html')


@app.route('/chat')
@login_required
def chat_page():
    return send_from_directory('static', 'chat.html')


# ==================== API路由 ====================

@app.route('/api/status')
@login_required
def api_status():
    cfg = get_current_config()

    # 从数据库获取历史
    try:
        history = get_report_history(7)
    except:
        history = []

    # 知识库统计
    try:
        kb_stats = kb_get_stats()
    except:
        kb_stats = {"total": 0, "categories": {}, "sources": {}}

    # 获取最新日报
    latest_data = None
    if history:
        try:
            report = get_daily_report(history[0]["date"])
            if report and report.get("data_json"):
                latest_data = report["data_json"]
        except:
            pass

    return jsonify({
        "scrape_status": scrape_status,
        "schedule": cfg.get("schedule", {}),
        "email_enabled": cfg.get("email", {}).get("enabled", False),
        "sources": cfg.get("sources", []),
        "history": history[:7],
        "kb_stats": kb_stats,
        "latest_data": latest_data,
        "db_mode": "postgresql" if USE_PG else "sqlite"
    })


@app.route('/api/scrape', methods=['POST'])
@login_required
def api_scrape():
    if scrape_status["running"]:
        return jsonify({"ok": False, "message": "抓取任务正在进行中"}), 409

    send_email = request.json.get("send_email", False)
    user_id = session.get('user_id')
    thread = threading.Thread(target=run_scrape, args=(send_email, user_id), daemon=True)
    thread.start()
    return jsonify({"ok": True, "message": "抓取任务已启动"})


@app.route('/api/report/<date_str>')
@login_required
def api_report(date_str):
    # 先从数据库查
    try:
        report = get_daily_report(date_str)
        if report and report.get("markdown"):
            return jsonify({"ok": True, "content": report["markdown"]})
    except:
        pass
    # 回退到文件
    md_path = OUTPUT_DIR / f"日报_{date_str}.md"
    if md_path.exists():
        return jsonify({"ok": True, "content": md_path.read_text(encoding='utf-8')})
    return jsonify({"ok": False, "message": "日报不存在"}), 404


@app.route('/api/report/<date_str>/data')
@login_required
def api_report_data(date_str):
    try:
        report = get_daily_report(date_str)
        if report and report.get("data_json"):
            return jsonify({"ok": True, "data": report["data_json"]})
    except:
        pass
    data_path = OUTPUT_DIR / f"data_{date_str}.json"
    if data_path.exists():
        with open(data_path, 'r', encoding='utf-8') as f:
            return jsonify({"ok": True, "data": json.load(f)})
    return jsonify({"ok": False, "message": "数据不存在"}), 404


# ==================== 知识库API ====================

@app.route('/api/kb/search')
@login_required
def api_kb_search():
    query = request.args.get('q', '')
    category = request.args.get('category', '')
    favorite = request.args.get('favorite', '0') == '1'
    limit = int(request.args.get('limit', 50))
    user_id = session.get('user_id')

    try:
        results = kb_search(query=query, category=category or None, limit=limit)
    except:
        results = []

    # 合并用户状态
    if user_id and results:
        user_state = get_user_kb_state(user_id)
        for item in results:
            item_id = item.get("id", "")
            item["favorite"] = item_id in user_state.get("favorites", {})
            item["notes"] = user_state.get("notes", {}).get(item_id, "")

    if favorite:
        results = [r for r in results if r.get("favorite")]

    return jsonify({"ok": True, "items": results, "total": len(results)})


@app.route('/api/kb/stats')
@login_required
def api_kb_stats():
    user_id = session.get('user_id')
    try:
        global_stats = kb_get_stats()
    except:
        global_stats = {"total": 0, "categories": {}, "sources": {}}

    if user_id:
        try:
            user_state = get_user_kb_state(user_id)
            return jsonify({"ok": True, "stats": {
                "total": global_stats.get("total", 0),
                "favorites": len(user_state.get("favorites", {})),
                "with_notes": len([v for v in user_state.get("notes", {}).values() if v]),
                "categories": global_stats.get("categories", {}),
                "sources": global_stats.get("sources", {}),
                "last_updated": global_stats.get("last_updated", "")
            }})
        except:
            pass
    return jsonify({"ok": True, "stats": global_stats})


@app.route('/api/kb/favorite/<item_id>', methods=['POST'])
@login_required
def api_kb_favorite(item_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"ok": False, "message": "请先登录"}), 401
    try:
        is_fav = toggle_user_favorite(user_id, item_id)
        return jsonify({"ok": True, "favorite": is_fav})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500


@app.route('/api/kb/note/<item_id>', methods=['POST'])
@login_required
def api_kb_note(item_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"ok": False, "message": "请先登录"}), 401
    note = request.json.get('note', '')
    try:
        save_user_note(user_id, item_id, note)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500


@app.route('/api/kb/read/<item_id>', methods=['POST'])
@login_required
def api_kb_read(item_id):
    user_id = session.get('user_id')
    if user_id:
        try:
            mark_user_read(user_id, item_id)
        except:
            pass
    return jsonify({"ok": True})


@app.route('/api/kb/save', methods=['POST'])
@login_required
def api_kb_save():
    user_id = session.get('user_id')
    item = {
        "title": request.json.get("title", ""),
        "ai_summary": request.json.get("ai_summary", ""),
        "url": request.json.get("url", ""),
        "source": request.json.get("source", ""),
        "category": request.json.get("category", "其他"),
        "tags": request.json.get("tags", []),
        "priority": request.json.get("priority", "normal")
    }
    item_id = kb_add(item)

    if user_id:
        toggle_user_favorite(user_id, item_id)

    return jsonify({"ok": True, "id": item_id})


@app.route('/api/kb/export', methods=['POST'])
@login_required
def api_kb_export():
    fmt = request.json.get('format', 'markdown')
    try:
        items = kb_export_all()
        if fmt == "json":
            filename = OUTPUT_DIR / f"knowledge_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filename.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
        else:
            lines = ["# 🧠 认知作弊知识库导出", f"> 导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}", f"> 共 {len(items)} 条知识", ""]
            for item in items:
                lines.append(f"### {item.get('title', '')}")
                lines.append(f"- **来源**: {item.get('source', '')}")
                lines.append(f"- **摘要**: {item.get('ai_summary', '')}")
                if item.get('tags'):
                    lines.append(f"- **标签**: {' '.join(['#' + t for t in item.get('tags', [])])}")
                if item.get('url'):
                    lines.append(f"- **链接**: {item.get('url')}")
                lines.append("")
            filename = OUTPUT_DIR / f"knowledge_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            filename.write_text("\n".join(lines), encoding='utf-8')
        return jsonify({"ok": True, "path": str(filename), "filename": filename.name})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500


@app.route('/api/kb/categories')
@login_required
def api_kb_categories():
    cats = []
    for name, info in CATEGORIES.items():
        try:
            count = len(kb_get_by_category(name))
        except:
            count = 0
        cats.append({"name": name, "desc": info.get("desc", ""), "count": count})
    return jsonify({"ok": True, "categories": cats})


@app.route('/api/debug')
def api_debug():
    """调试接口 - 检查环境变量（部署后删除）"""
    db_url = os.environ.get("DATABASE_URL", "")
    return jsonify({
        "db_mode": "postgresql" if USE_PG else "sqlite",
        "DATABASE_URL_set": bool(db_url),
        "DATABASE_URL_prefix": db_url[:30] + "..." if db_url else "NOT SET",
        "all_env_keys": [k for k in os.environ.keys() if not k.startswith("_")]
    })


# ==================== AI助手API ====================

@app.route('/api/ai/chat', methods=['POST'])
@login_required
def api_ai_chat():
    question = request.json.get('question', '')
    history = request.json.get('history', [])
    if not question.strip():
        return jsonify({"ok": False, "answer": "请输入你的问题"})
    try:
        # 构造一个兼容的知识库给 AI 助手
        from scraper.knowledge_base import KnowledgeBase
        tmp_kb = KnowledgeBase(str(OUTPUT_DIR / "tmp_kb.json"))
        items = kb_search(limit=200)
        for item in items:
            tmp_kb.add(item)
        ai_assistant.kb = tmp_kb
        answer = ai_assistant.chat(question, history)
        return jsonify({"ok": True, "answer": answer})
    except Exception as e:
        return jsonify({"ok": False, "answer": f"抱歉，出了点问题：{str(e)}"})


# ==================== 微信推送API ====================

@app.route('/api/wechat/push', methods=['POST'])
@login_required
def api_wechat_push():
    cfg = get_current_config()
    wechat_cfg = cfg.get("wechat", {})
    if not wechat_cfg.get("enabled") or not wechat_cfg.get("webhook_url"):
        return jsonify({"ok": False, "message": "请先在设置中配置企业微信Webhook地址并启用"}), 400
    try:
        history = get_report_history(1)
        if not history:
            return jsonify({"ok": False, "message": "还没有日报数据，请先执行一次抓取"}), 400
        report = get_daily_report(history[0]["date"])
        if not report or not report.get("data_json"):
            return jsonify({"ok": False, "message": "日报数据加载失败"}), 500
        pusher = WeChatPusher(wechat_cfg["webhook_url"])
        push_cats = wechat_cfg.get("push_categories", []) or None
        result = pusher.push_daily_report(report["data_json"], push_cats)
        return jsonify({"ok": result["ok"], "sent": result["sent"], "failed": result["failed"]})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500


@app.route('/api/wechat/test', methods=['POST'])
@login_required
def api_wechat_test():
    webhook_url = request.json.get('webhook_url', '')
    if not webhook_url:
        return jsonify({"ok": False, "message": "请输入Webhook地址"}), 400
    try:
        pusher = WeChatPusher(webhook_url)
        ok = pusher.send_text("认知作弊情报系统\n\n测试消息发送成功！")
        return jsonify({"ok": ok, "message": "测试消息已发送" if ok else "发送失败"})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500


@app.route('/api/wechat/messages')
@login_required
def api_wechat_messages():
    try:
        history = get_report_history(1)
        if not history:
            return jsonify({"ok": True, "messages": [{
                "role": "assistant", "type": "text",
                "content": "你好！我还没抓到今天的消息呢。\n\n点击「立即抓取」按钮来获取今日情报吧！"
            }]})
        report = get_daily_report(history[0]["date"])
        if not report or not report.get("data_json"):
            return jsonify({"ok": False, "messages": []}), 500
        messages = format_wechat_chat_message(report["data_json"])
        return jsonify({"ok": True, "messages": messages, "date": history[0]["date"]})
    except Exception as e:
        return jsonify({"ok": True, "messages": [{
            "role": "assistant", "type": "text",
            "content": "数据加载失败，请稍后再试"
        }]})


# ==================== 配置API ====================

@app.route('/api/config', methods=['GET', 'POST'])
@login_required
def api_config():
    if request.method == 'GET':
        cfg = get_current_config()
        if cfg.get("email", {}).get("password"):
            cfg["email"]["password"] = "******"
        return jsonify(cfg)

    new_cfg = request.json
    if new_cfg:
        user_id = session.get('user_id')
        if user_id:
            if new_cfg.get("email", {}).get("password") == "******":
                try:
                    row = get_user_config(user_id)
                    old_cfg = row_to_config_dict(row)
                    new_cfg["email"]["password"] = old_cfg.get("email", {}).get("password", "")
                except:
                    pass
            save_user_config(user_id, new_cfg)
        else:
            if new_cfg.get("email", {}).get("password") == "******":
                old_cfg = load_config()
                new_cfg["email"]["password"] = old_cfg.get("email", {}).get("password", "")
            save_config(new_cfg)
        update_scheduler_for_user(user_id, new_cfg.get("schedule", {}))
        return jsonify({"ok": True, "message": "配置已保存"})
    return jsonify({"ok": False}), 400


@app.route('/api/history')
@login_required
def api_history():
    try:
        history = get_report_history(30)
    except:
        history = []
    return jsonify({"ok": True, "history": history})


@app.route('/api/reports/<filename>')
@login_required
def api_report_file(filename):
    return send_from_directory(str(OUTPUT_DIR), filename)


# ==================== 定时任务 ====================

def update_scheduler_for_user(user_id: int, schedule_cfg: dict):
    job_id = f"daily_scrape_{user_id}" if user_id else "daily_scrape"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    if schedule_cfg.get("enabled", True):
        hour = schedule_cfg.get("hour", 8)
        minute = schedule_cfg.get("minute", 0)
        def job_func():
            return run_scrape(send_email=True, user_id=user_id)
        scheduler.add_job(
            job_func, 'cron', hour=hour, minute=minute,
            id=job_id, name=f'每日信息抓取(用户{user_id})'
        )


def init_scheduler():
    cfg = load_config()
    update_scheduler_for_user(None, cfg.get("schedule", {}))
    try:
        from models import get_db
        db = get_db()
        rows = db.execute(
            "SELECT u.id, uc.schedule_enabled, uc.schedule_hour, uc.schedule_minute "
            "FROM users u JOIN user_config uc ON u.id=uc.user_id "
            "WHERE uc.schedule_enabled=1"
        ).fetchall()
        db.close()
        for row in rows:
            d = dict(row)
            schedule_cfg = {"enabled": bool(d["schedule_enabled"]), "hour": d["schedule_hour"], "minute": d["schedule_minute"]}
            update_scheduler_for_user(d["id"], schedule_cfg)
    except Exception as e:
        print(f"初始化用户定时任务失败: {e}")
    scheduler.start()


if __name__ == '__main__':
    print("=" * 50)
    print("认知作弊信息抓取系统 v6 多用户版")
    print(f"  数据库: {'PostgreSQL' if USE_PG else 'SQLite'}")
    print("  用户系统 | 知识库隔离 | AI分类摘要 | 分类日报")
    print("=" * 50)
    init_scheduler()
    print(f"输出目录: {OUTPUT_DIR}")
    print(f"Web界面: http://localhost:5000")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=False)
