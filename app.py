"""认知作弊信息抓取系统 v5 —— 多用户版 + 知识库隔离 + Flask Web应用"""
import os
import json
import re
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, render_template, jsonify, request, send_from_directory, session
from apscheduler.schedulers.background import BackgroundScheduler

from scraper import (
    Kr36Scraper, HuxiuScraper, GeekparkScraper,
    PolicyScraper, CninfoScraper,
    ReportGeneratorV2, KnowledgeBase, CATEGORIES,
    WeChatPusher, format_wechat_chat_message
)
from scraper.ai_assistant import AIAssistant
from models import init_db, get_user_config, save_user_config, row_to_config_dict
from auth import auth_bp, login_required

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'cognition-scraper-v5-2026')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

# 注册认证蓝图
app.register_blueprint(auth_bp)

CONFIG_FILE = Path(__file__).parent / "config.json"
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

scheduler = BackgroundScheduler()
scrape_status = {"running": False, "last_run": None, "progress": ""}

# 全局知识库（抓取结果存入这里，所有用户共享条目）
global_kb = KnowledgeBase(str(OUTPUT_DIR / "knowledge_base.json"))

# AI助手（不绑定特定知识库，运行时切换）
ai_assistant = AIAssistant(None)


# ==================== 用户配置管理 ====================

def get_current_config() -> dict:
    """获取当前用户的配置（已登录=用户配置，未登录=全局配置）"""
    user_id = session.get('user_id')
    if user_id:
        try:
            row = get_user_config(user_id)
            return row_to_config_dict(row)
        except Exception:
            pass
    return load_config()


def load_config() -> dict:
    """加载全局默认配置（模板）"""
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
    """保存全局默认配置"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ==================== 知识库用户隔离 ====================

def get_user_kb():
    """获取当前用户的知识库实例（全局条目 + 用户个人状态）"""
    user_id = session.get('user_id')
    if user_id:
        kb_path = OUTPUT_DIR / f"knowledge_base_{user_id}.json"
        return KnowledgeBase(str(kb_path))
    return global_kb


def get_user_kb_state_path(user_id: int) -> Path:
    """获取用户知识库状态文件路径"""
    return OUTPUT_DIR / f"user_kb_state_{user_id}.json"


def load_user_kb_state(user_id: int) -> dict:
    """加载用户的知识库状态（收藏/笔记/已读）"""
    path = get_user_kb_state_path(user_id)
    if path.exists():
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {"favorites": {}, "notes": {}, "read": {}}


def save_user_kb_state(user_id: int, state: dict):
    """保存用户的知识库状态"""
    path = get_user_kb_state_path(user_id)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def merge_user_state(items: list[dict], user_state: dict) -> list[dict]:
    """将用户状态合并到知识库条目列表中"""
    favorites = user_state.get("favorites", {})
    notes = user_state.get("notes", {})
    for item in items:
        item_id = item.get("id", "")
        item["favorite"] = favorites.get(item_id, False)
        item["notes"] = notes.get(item_id, "")
    return items


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
    """执行抓取 + 分类 + 入知识库"""
    global scrape_status
    scrape_status["running"] = True

    try:
        # 获取配置（指定用户或全局）
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
        kb_stats = global_kb.get_stats()
        report_result = generator.generate(all_results, kb_stats)

        # 3. 入全局知识库（抓取条目全局共享）
        scrape_status["progress"] = "正在更新知识库..."
        new_count = global_kb.batch_add(report_result["all_analyzed"])

        # 4. 发送邮件（给指定用户或全局配置）
        email_cfg = cfg.get("email", {})
        if send_email and email_cfg.get("enabled") and email_cfg.get("sender"):
            scrape_status["progress"] = "正在发送邮件..."
            send_report_email(report_result["markdown"], email_cfg)

        # 5. 微信推送
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
                scrape_status["progress"] = f"完成！新增{new_count}条知识，微信推送失败: {e}"
        else:
            scrape_status["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            scrape_status["progress"] = f"完成！新增{new_count}条知识"

        scrape_status["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not wechat_cfg.get("enabled"):
            scrape_status["progress"] = f"完成！新增{new_count}条知识"
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

        with smtplib.SMTP(email_cfg['smtp_host'], email_cfg['smtp_port'], timeout=30) as server:
            server.starttls()
            server.login(email_cfg['sender'], email_cfg['password'])
            server.send_message(msg)

        print(f"邮件发送成功")
    except Exception as e:
        print(f"邮件发送失败: {e}")


# ==================== API路由 ====================

@app.route('/')
@login_required
def index():
    return send_from_directory('static', 'index.html')


@app.route('/chat')
@login_required
def chat_page():
    """微信聊天风格页面"""
    return send_from_directory('static', 'chat.html')


@app.route('/api/status')
@login_required
def api_status():
    cfg = get_current_config()
    generator = ReportGeneratorV2(str(OUTPUT_DIR))
    history = generator.get_history(7)

    # 获取用户知识库统计（合并全局条目 + 用户状态）
    user_kb = get_user_kb()
    kb_stats = user_kb.get_stats()

    # 也展示全局知识库总量
    global_stats = global_kb.get_stats()
    kb_stats["global_total"] = global_stats.get("total", 0)

    latest_data = None
    if history:
        latest_data = generator.read_data(history[0]["date"])

    return jsonify({
        "scrape_status": scrape_status,
        "schedule": cfg.get("schedule", {}),
        "email_enabled": cfg.get("email", {}).get("enabled", False),
        "sources": cfg.get("sources", []),
        "history": history[:7],
        "kb_stats": kb_stats,
        "latest_data": latest_data
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
    generator = ReportGeneratorV2(str(OUTPUT_DIR))
    content = generator.read_report(date_str)
    if content:
        return jsonify({"ok": True, "content": content})
    return jsonify({"ok": False, "message": "日报不存在"}), 404


@app.route('/api/report/<date_str>/data')
@login_required
def api_report_data(date_str):
    generator = ReportGeneratorV2(str(OUTPUT_DIR))
    data = generator.read_data(date_str)
    if data:
        return jsonify({"ok": True, "data": data})
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

    # 从全局知识库搜索条目
    results = global_kb.search(query, category=category or None, favorite_only=False)

    # 合并用户状态
    if user_id:
        user_state = load_user_kb_state(user_id)
        results = merge_user_state(results, user_state)

    # 如果筛选仅收藏，过滤
    if favorite:
        results = [r for r in results if r.get("favorite")]

    return jsonify({"ok": True, "items": results[:limit], "total": len(results)})


@app.route('/api/kb/stats')
@login_required
def api_kb_stats():
    user_id = session.get('user_id')
    global_stats = global_kb.get_stats()

    if user_id:
        user_state = load_user_kb_state(user_id)
        favorites_count = len(user_state.get("favorites", {}))
        notes_count = len([v for v in user_state.get("notes", {}).values() if v])
        return jsonify({"ok": True, "stats": {
            "total": global_stats.get("total", 0),
            "favorites": favorites_count,
            "with_notes": notes_count,
            "categories": global_stats.get("categories", {}),
            "sources": global_stats.get("sources", {}),
            "last_updated": global_stats.get("last_updated", "")
        }})

    return jsonify({"ok": True, "stats": global_stats})


@app.route('/api/kb/favorite/<item_id>', methods=['POST'])
@login_required
def api_kb_favorite(item_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"ok": False, "message": "请先登录"}), 401

    user_state = load_user_kb_state(user_id)
    current = user_state["favorites"].get(item_id, False)
    user_state["favorites"][item_id] = not current
    save_user_kb_state(user_id, user_state)

    return jsonify({"ok": True, "favorite": not current})


@app.route('/api/kb/note/<item_id>', methods=['POST'])
@login_required
def api_kb_note(item_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"ok": False, "message": "请先登录"}), 401

    note = request.json.get('note', '')
    user_state = load_user_kb_state(user_id)
    user_state["notes"][item_id] = note
    save_user_kb_state(user_id, user_state)

    return jsonify({"ok": True})


@app.route('/api/kb/read/<item_id>', methods=['POST'])
@login_required
def api_kb_read(item_id):
    user_id = session.get('user_id')
    if not user_id:
        # 未登录也允许标记已读（存全局）
        global_kb.mark_read(item_id)
        return jsonify({"ok": True})

    user_state = load_user_kb_state(user_id)
    user_state["read"][item_id] = datetime.now().isoformat()
    save_user_kb_state(user_id, user_state)

    return jsonify({"ok": True})


@app.route('/api/kb/save', methods=['POST'])
@login_required
def api_kb_save():
    """从日报一键保存到知识库"""
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
    item_id = global_kb.add(item)

    # 自动收藏到用户
    if user_id:
        user_state = load_user_kb_state(user_id)
        user_state["favorites"][item_id] = True
        save_user_kb_state(user_id, user_state)

    return jsonify({"ok": True, "id": item_id})


@app.route('/api/kb/export', methods=['POST'])
@login_required
def api_kb_export():
    fmt = request.json.get('format', 'markdown')
    item_ids = request.json.get('item_ids', None)

    path = global_kb.export_file(fmt, item_ids)
    if path:
        return jsonify({"ok": True, "path": path, "filename": Path(path).name})
    return jsonify({"ok": False, "message": "导出失败"}), 500


@app.route('/api/kb/categories')
@login_required
def api_kb_categories():
    """获取所有分类定义"""
    cats = []
    for name, info in CATEGORIES.items():
        cats.append({
            "name": name,
            "desc": info.get("desc", ""),
            "count": len(global_kb.get_by_category(name))
        })
    return jsonify({"ok": True, "categories": cats})


# ==================== AI助手API ====================

@app.route('/api/ai/chat', methods=['POST'])
@login_required
def api_ai_chat():
    """AI答疑助手聊天接口"""
    question = request.json.get('question', '')
    history = request.json.get('history', [])

    if not question.strip():
        return jsonify({"ok": False, "answer": "请输入你的问题"})

    try:
        # 使用用户知识库进行检索
        user_kb = get_user_kb()
        ai_assistant.kb = user_kb
        answer = ai_assistant.chat(question, history)
        return jsonify({"ok": True, "answer": answer})
    except Exception as e:
        return jsonify({"ok": False, "answer": f"抱歉，出了点问题：{str(e)}"})


# ==================== 微信推送API ====================

@app.route('/api/wechat/push', methods=['POST'])
@login_required
def api_wechat_push():
    """手动触发微信推送"""
    cfg = get_current_config()
    wechat_cfg = cfg.get("wechat", {})

    if not wechat_cfg.get("enabled") or not wechat_cfg.get("webhook_url"):
        return jsonify({"ok": False, "message": "请先在设置中配置企业微信Webhook地址并启用"}), 400

    try:
        generator = ReportGeneratorV2(str(OUTPUT_DIR))
        history = generator.get_history(1)
        if not history:
            return jsonify({"ok": False, "message": "还没有日报数据，请先执行一次抓取"}), 400

        report_data = generator.read_data(history[0]["date"])
        if not report_data:
            return jsonify({"ok": False, "message": "日报数据加载失败"}), 500

        pusher = WeChatPusher(wechat_cfg["webhook_url"])
        push_cats = wechat_cfg.get("push_categories", []) or None
        result = pusher.push_daily_report(report_data, push_cats)

        return jsonify({"ok": result["ok"], "sent": result["sent"], "failed": result["failed"]})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500


@app.route('/api/wechat/test', methods=['POST'])
@login_required
def api_wechat_test():
    """测试微信推送"""
    webhook_url = request.json.get('webhook_url', '')
    if not webhook_url:
        return jsonify({"ok": False, "message": "请输入Webhook地址"}), 400

    try:
        pusher = WeChatPusher(webhook_url)
        ok = pusher.send_text("认知作弊情报系统\n\n测试消息发送成功！\n\n如果收到这条消息，说明Webhook配置正确。")
        return jsonify({"ok": ok, "message": "测试消息已发送" if ok else "发送失败，请检查Webhook地址"})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500


@app.route('/api/wechat/messages')
@login_required
def api_wechat_messages():
    """获取微信聊天风格的消息列表"""
    generator = ReportGeneratorV2(str(OUTPUT_DIR))
    history = generator.get_history(1)

    if not history:
        return jsonify({"ok": True, "messages": [{
            "role": "assistant", "type": "text",
            "content": "你好！我还没抓到今天的消息呢。\n\n点击「立即抓取」按钮来获取今日情报吧！"
        }]})

    report_data = generator.read_data(history[0]["date"])
    if not report_data:
        return jsonify({"ok": False, "messages": []}), 500

    messages = format_wechat_chat_message(report_data)
    return jsonify({"ok": True, "messages": messages, "date": history[0]["date"]})


# ==================== 配置API ====================

@app.route('/api/config', methods=['GET', 'POST'])
@login_required
def api_config():
    if request.method == 'GET':
        cfg = get_current_config()
        # 隐藏密码
        if cfg.get("email", {}).get("password"):
            cfg["email"]["password"] = "******"
        return jsonify(cfg)

    new_cfg = request.json
    if new_cfg:
        user_id = session.get('user_id')
        if user_id:
            # 处理密码占位符
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
    generator = ReportGeneratorV2(str(OUTPUT_DIR))
    history = generator.get_history(30)
    return jsonify({"ok": True, "history": history})


@app.route('/api/reports/<filename>')
@login_required
def api_report_file(filename):
    return send_from_directory(str(OUTPUT_DIR), filename)


# ==================== 定时任务 ====================

def update_scheduler_for_user(user_id: int, schedule_cfg: dict):
    """为特定用户更新定时任务"""
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


def update_scheduler(schedule_cfg: dict):
    """更新全局定时任务（向后兼容）"""
    update_scheduler_for_user(None, schedule_cfg)


def init_scheduler():
    """初始化定时任务：为所有开启调度的用户创建任务"""
    cfg = load_config()
    update_scheduler(cfg.get("schedule", {}))

    # 为所有启用了定时任务的用户创建调度
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
            schedule_cfg = {
                "enabled": bool(row["schedule_enabled"]),
                "hour": row["schedule_hour"],
                "minute": row["schedule_minute"]
            }
            update_scheduler_for_user(row["id"], schedule_cfg)
    except Exception as e:
        print(f"初始化用户定时任务失败: {e}")

    scheduler.start()


if __name__ == '__main__':
    init_db()
    print("=" * 50)
    print("认知作弊信息抓取系统 v5 多用户版")
    print("  用户系统 | 知识库隔离 | AI分类摘要 | 分类日报")
    print("=" * 50)
    init_scheduler()
    print(f"输出目录: {OUTPUT_DIR}")
    print(f"Web界面: http://localhost:5000")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=False)
