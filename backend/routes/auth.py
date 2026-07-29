from flask import request, jsonify, g
from extensions import (
    get_db, verify_token, create_token, check_password, hash_password,
    record_operation_log, token_required, admin_required,
    check_login_rate_limit, record_login_attempt, reset_login_rate_limit,
    LOGIN_ATTEMPTS, LOGIN_MAX_ATTEMPTS, LOGIN_WINDOW_SECONDS,
)

from . import auth_bp


@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    ip_address = request.remote_addr or 'unknown'

    allowed, wait_seconds = check_login_rate_limit(ip_address)
    if not allowed:
        minutes = wait_seconds // 60
        seconds = wait_seconds % 60
        return jsonify({
            'code': 429,
            'message': f'登录尝试过于频繁，请 {minutes}分{seconds}秒后再试',
            'data': {'wait_seconds': wait_seconds}
        })

    data = request.get_json(silent=True) or {}
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'code': 400, 'message': '请输入账号和密码', 'data': None})

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT username, password_hash, name, role FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()

    if row and check_password(password, row['password_hash']):
        LOGIN_ATTEMPTS.pop(ip_address, None)
        token = create_token(row['username'], row['name'], row['role'])
        record_operation_log(row['username'], '登录', '系统', f'用户 {row["name"]} 登录系统')
        return jsonify({
            'code': 200,
            'message': '登录成功',
            'data': {
                'token': token,
                'username': row['username'],
                'name': row['name'],
                'role': row['role']
            }
        })

    record_login_attempt(ip_address)
    remaining = LOGIN_MAX_ATTEMPTS - len(LOGIN_ATTEMPTS.get(ip_address, []))
    msg = '账号或密码错误'
    if remaining > 0:
        msg += f'，剩余 {remaining} 次尝试机会'
    else:
        msg += f'，已达最大尝试次数，请 {LOGIN_WINDOW_SECONDS // 60} 分钟后再试'
    return jsonify({'code': 401, 'message': msg, 'data': None})


@auth_bp.route('/api/auth/info', methods=['GET'])
@token_required
def get_user_info():
    payload = request.current_user

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT role FROM user_roles WHERE username = ?", (payload['username'],))
    rows = cursor.fetchall()
    roles = [r['role'] for r in rows] if rows else [payload['role']]

    return jsonify({
        'code': 200,
        'message': 'success',
        'data': {
            'username': payload['username'],
            'name': payload['name'],
            'role': payload['role'],
            'roles': roles
        }
    })


@auth_bp.route('/api/auth/logout', methods=['POST'])
@token_required
def logout():
    payload = request.current_user
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if token:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT username, name FROM tokens WHERE token = ?', (token,))
        row = cursor.fetchone()
        if row:
            record_operation_log(row['username'], '登出', '系统', f'用户 {row["name"]} 退出系统')
        cursor.execute('DELETE FROM tokens WHERE token = ?', (token,))
        db.commit()
    return jsonify({'code': 200, 'message': '退出成功', 'data': None})


@auth_bp.route('/api/auth/reset_rate_limit', methods=['POST'])
@admin_required
def reset_rate_limit():
    data = request.get_json(silent=True) or {}
    ip_address = data.get('ip_address')
    
    reset_login_rate_limit(ip_address)
    
    payload = request.current_user
    record_operation_log(payload['username'], '重置', '登录', 
        f'重置登录速率限制: {ip_address or "全部"}')
    
    return jsonify({
        'code': 200,
        'message': '速率限制已重置',
        'data': None
    })


def register_routes(app):
    app.register_blueprint(auth_bp)
