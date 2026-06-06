"""认证模块 —— 登录/注册/登出 + 路由保护装饰器"""
from functools import wraps
from flask import Blueprint, request, jsonify, session, redirect, send_from_directory
from models import create_user, verify_user, get_user_by_id

auth_bp = Blueprint('auth', __name__)


def login_required(f):
    """装饰器：保护路由，未登录时 API 返回 401，页面请求重定向到登录页"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            # API 请求返回 JSON 错误
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({"ok": False, "message": "请先登录"}), 401
            # 页面请求重定向到登录页
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面 / 登录接口"""
    if request.method == 'GET':
        # 已登录用户直接跳转主页
        if 'user_id' in session:
            return redirect('/')
        return send_from_directory('static', 'login.html')

    # POST: 处理登录
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({"ok": False, "message": "请输入用户名和密码"}), 400

    user = verify_user(username, password)
    if user:
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['display_name'] = user.get('display_name', '') or user['username']
        session.permanent = True
        return jsonify({"ok": True, "message": "登录成功"})
    else:
        return jsonify({"ok": False, "message": "用户名或密码错误"}), 401


@auth_bp.route('/register', methods=['POST'])
def register():
    """注册接口"""
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({"ok": False, "message": "请输入用户名和密码"}), 400

    if len(username) < 2:
        return jsonify({"ok": False, "message": "用户名至少2个字符"}), 400

    if len(password) < 4:
        return jsonify({"ok": False, "message": "密码至少4个字符"}), 400

    ok, message = create_user(username, password)
    if ok:
        return jsonify({"ok": True, "message": message})
    else:
        return jsonify({"ok": False, "message": message}), 409


@auth_bp.route('/logout')
def logout():
    """退出登录"""
    session.clear()
    return redirect('/login')


@auth_bp.route('/api/user/info')
@login_required
def api_user_info():
    """获取当前用户信息"""
    user = get_user_by_id(session['user_id'])
    if user:
        return jsonify({
            "ok": True,
            "user": {
                "id": user['id'],
                "username": user['username'],
                "display_name": user.get('display_name', '') or user['username'],
            }
        })
    return jsonify({"ok": False, "message": "用户不存在"}), 404
