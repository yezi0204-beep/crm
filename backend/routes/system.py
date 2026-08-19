from flask import request, jsonify
from datetime import datetime, timedelta

from extensions import (
    get_db, verify_token, token_required, admin_required,
    record_operation_log, hash_password,
)

from . import system_bp


@system_bp.route('/api/users', methods=['GET'])
@token_required
def get_users():
    role_filter = request.args.get('role', '')

    db = get_db()
    cursor = db.cursor()

    if role_filter:
        cursor.execute("""
            SELECT u.username, u.name, u.role, u.status, u.department
            FROM users u
            INNER JOIN user_roles ur ON u.username = ur.username
            WHERE ur.role = ? AND (u.status IS NULL OR u.status != '离职')
            GROUP BY u.username, u.name, u.role, u.status, u.department
            ORDER BY u.name
        """, (role_filter,))
    else:
        cursor.execute("SELECT username, name, role, status, department FROM users ORDER BY name")

    rows = cursor.fetchall()
    users = []
    for row in rows:
        user = dict(row)
        user['status'] = user.get('status') or '在职'
        user['department'] = user.get('department') or ''
        cursor.execute("SELECT role FROM user_roles WHERE username = ?", (user['username'],))
        role_rows = cursor.fetchall()
        user['roles'] = [r['role'] for r in role_rows] if role_rows else [user['role']]
        users.append(user)

    return jsonify({'code': 200, 'message': 'success', 'data': users})


@system_bp.route('/api/users', methods=['POST'])
@admin_required
def create_user():
    data = request.get_json(silent=True) or {}

    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("SELECT username FROM users WHERE username = ?", (data.get('username'),))
        if cursor.fetchone():
            return jsonify({'code': 400, 'message': '用户名已存在', 'data': None})

        roles = data.get('roles', [])
        if not roles and data.get('role'):
            roles = [data.get('role')]
        if not roles:
            roles = ['销售']

        primary_role = '主任' if '主任' in roles else ('院长' if '院长' in roles else roles[0])

        hashed_pwd = hash_password(data.get('password'))
        cursor.execute("""
            INSERT INTO users (username, password_hash, name, role, department)
            VALUES (?, ?, ?, ?, ?)
        """, (data.get('username'), hashed_pwd, data.get('name'), primary_role, data.get('department', '')))

        for r in roles:
            cursor.execute("INSERT OR IGNORE INTO user_roles (username, role) VALUES (?, ?)",
                           (data.get('username'), r))

        # ---- 7.1.2 完整性 + 7.1.4 不可抵赖性：写入摘要与签名 ----
        try:
            from security import get_integrity, get_non_repudiation
            integrity = get_integrity()
            non_rep = get_non_repudiation()
            status = '在职'
            dept = data.get('department', '') or ''
            profile_digest = integrity.compute_profile_digest(
                username=data.get('username'), name=data.get('name'),
                role=primary_role, department=dept, status=status,
            )
            signed = non_rep.sign_operation(
                username=request.current_user['username'],
                operation='创建用户',
                module='系统',
                detail=f'创建用户: {data.get("name")}',
                extra={'target_username': data.get('username'), 'role': primary_role,
                       'department': dept, 'status': status},
            )
            cursor.execute("""
                UPDATE users SET profile_digest = ?, profile_signature = ?
                WHERE username = ?
            """, (profile_digest, signed['signature'], data.get('username')))
        except Exception:
            pass

        db.commit()

        return jsonify({'code': 200, 'message': '用户创建成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@system_bp.route('/api/users/<username>', methods=['PUT'])
@admin_required
def update_user(username):
    data = request.get_json(silent=True) or {}

    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("SELECT username FROM users WHERE username = ?", (username,))
        if not cursor.fetchone():
            return jsonify({'code': 404, 'message': '用户不存在', 'data': None})

        if data.get('name'):
            cursor.execute("UPDATE users SET name = ? WHERE username = ?", (data.get('name'), username))

        if 'department' in data:
            cursor.execute("UPDATE users SET department = ? WHERE username = ?", (data.get('department', ''), username))

        roles = data.get('roles')
        if roles is not None:
            if not roles:
                roles = ['销售']
            primary_role = '主任' if '主任' in roles else ('院长' if '院长' in roles else roles[0])
            cursor.execute("UPDATE users SET role = ? WHERE username = ?", (primary_role, username))
            cursor.execute("DELETE FROM user_roles WHERE username = ?", (username,))
            for r in roles:
                cursor.execute("INSERT OR IGNORE INTO user_roles (username, role) VALUES (?, ?)",
                               (username, r))

        if data.get('password'):
            hashed_pwd = hash_password(data.get('password'))
            cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?", (hashed_pwd, username))

        # ---- 7.1.2 + 7.1.4：更新后重新计算完整性摘要与数字签名 ----
        try:
            from security import get_integrity, get_non_repudiation
            integrity = get_integrity()
            non_rep = get_non_repudiation()
            cursor.execute("SELECT name, role, department, status FROM users WHERE username = ?", (username,))
            r = cursor.fetchone()
            if r:
                name = r['name'] or ''
                role = r['role'] or ''
                dept = r['department'] or ''
                status = r['status'] or '在职'
                profile_digest = integrity.compute_profile_digest(
                    username=username, name=name, role=role,
                    department=dept, status=status,
                )
                signed = non_rep.sign_operation(
                    username=request.current_user['username'],
                    operation='更新用户',
                    module='系统',
                    detail=f'更新用户: {username}',
                    extra={'target_username': username, 'name': name, 'role': role,
                           'department': dept, 'status': status},
                )
                cursor.execute("""
                    UPDATE users SET profile_digest = ?, profile_signature = ?
                    WHERE username = ?
                """, (profile_digest, signed['signature'], username))
        except Exception:
            pass

        db.commit()

        return jsonify({'code': 200, 'message': '用户更新成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@system_bp.route('/api/users/<username>/status', methods=['PUT'])
@admin_required
def toggle_user_status(username):
    data = request.get_json(silent=True) or {}
    new_status = data.get('status')

    if new_status not in ('在职', '离职'):
        return jsonify({'code': 400, 'message': '无效的状态值', 'data': None})

    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("SELECT username FROM users WHERE username = ?", (username,))
        if not cursor.fetchone():
            return jsonify({'code': 404, 'message': '用户不存在', 'data': None})

        cursor.execute("UPDATE users SET status = ? WHERE username = ?", (new_status, username))

        # ---- 7.1.2 + 7.1.4：状态变更后重新计算完整性摘要与数字签名 ----
        try:
            from security import get_integrity, get_non_repudiation
            integrity = get_integrity()
            non_rep = get_non_repudiation()
            cursor.execute("SELECT name, role, department FROM users WHERE username = ?", (username,))
            r = cursor.fetchone()
            if r:
                profile_digest = integrity.compute_profile_digest(
                    username=username, name=r['name'] or '', role=r['role'] or '',
                    department=r['department'] or '', status=new_status,
                )
                signed = non_rep.sign_operation(
                    username=request.current_user['username'],
                    operation='用户状态变更',
                    module='用户管理',
                    detail=f'用户 {username} 状态变更为 {new_status}',
                    extra={'target_username': username, 'status': new_status},
                )
                cursor.execute("""
                    UPDATE users SET profile_digest = ?, profile_signature = ?
                    WHERE username = ?
                """, (profile_digest, signed['signature'], username))
        except Exception:
            pass

        db.commit()

        action = '标记离职' if new_status == '离职' else '恢复在职'
        record_operation_log(request.current_user['username'], '状态变更', '用户管理',
                             f'{action}：{username}')

        return jsonify({'code': 200, 'message': f'{action}成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@system_bp.route('/api/users/<username>', methods=['DELETE'])
@admin_required
def delete_user(username):
    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("DELETE FROM user_roles WHERE username = ?", (username,))
        cursor.execute("DELETE FROM users WHERE username = ?", (username,))
        db.commit()

        return jsonify({'code': 200, 'message': '用户删除成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@system_bp.route('/api/operation_logs', methods=['GET'])
@token_required
def get_operation_logs():
    payload = request.current_user
    role = payload.get('role', '')
    if role != '主任':
        return jsonify({'code': 403, 'message': '权限不足，仅主任可查看操作日志', 'data': None})

    db = get_db()
    cursor = db.cursor()

    keyword = request.args.get('keyword', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')

    conditions = []
    params = []

    if keyword:
        conditions.append("(username LIKE ? OR operation LIKE ? OR module LIKE ? OR detail LIKE ?)")
        params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])

    if start_date:
        conditions.append("created_at >= ?")
        params.append(start_date)

    if end_date:
        conditions.append("created_at <= ?")
        params.append(end_date + ' 23:59:59')

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    cursor.execute(f"""
        SELECT ol.*, u.name as user_name
        FROM operation_logs ol
        LEFT JOIN users u ON ol.username = u.username
        {where_clause}
        ORDER BY ol.created_at DESC
    """, params)

    rows = cursor.fetchall()
    logs = []
    for row in rows:
        logs.append(dict(row))

    return jsonify({'code': 200, 'message': 'success', 'data': logs})


@system_bp.route('/api/operation_logs/unread_count', methods=['GET'])
@token_required
def get_unread_log_count():
    payload = request.current_user
    role = payload.get('role', '')
    if role != '主任':
        return jsonify({'code': 200, 'message': 'success', 'data': {'unread_count': 0}})

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM operation_logs WHERE is_read = 0")
    count = cursor.fetchone()['count']

    return jsonify({'code': 200, 'message': 'success', 'data': {'unread_count': count}})


@system_bp.route('/api/operation_logs/read', methods=['POST'])
@token_required
def mark_logs_read():
    payload = request.current_user
    role = payload.get('role', '')
    if role != '主任':
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("UPDATE operation_logs SET is_read = 1 WHERE is_read = 0")
        db.commit()

        return jsonify({'code': 200, 'message': '已标记全部已读', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@system_bp.route('/api/alerts', methods=['GET'])
@token_required
def get_alerts():
    payload = request.current_user
    username = payload['username']
    role = payload['role']

    db = get_db()
    cursor = db.cursor()

    alerts = []

    today = datetime.now().strftime('%Y-%m-%d')
    seven_days_later = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
    # 商机预计成交日期为年月（YYYY-MM）精度，按本月及下月预警
    this_month = datetime.now().strftime('%Y-%m')
    next_month = (datetime.now() + timedelta(days=32)).strftime('%Y-%m')

    if role == '主任' or role == '院长':
        cursor.execute("""
            SELECT c.id, c.contract_name, c.expected_income_date, c.total_amt, c.paid_amt, c.owner_id, u.name as owner_name
            FROM contracts c
            LEFT JOIN users u ON c.owner_id = u.username
            WHERE c.status = '执行中' AND c.expected_income_date IS NOT NULL AND c.expected_income_date != ''
                AND c.expected_income_date >= ? AND c.expected_income_date <= ?
            ORDER BY expected_income_date ASC
        """, (today, seven_days_later))
        rows = cursor.fetchall()
        for row in rows:
            alerts.append({
                'type': 'payment',
                'title': '回款预警',
                'detail': f"合同「{row['contract_name']}」预计回款日期即将到期",
                'due_date': row['expected_income_date'],
                'amount': (row['total_amt'] - row['paid_amt']) / 10000 if row['total_amt'] else 0,
                'owner': row['owner_name'],
                'contract_id': row['id']
            })

        cursor.execute("""
            SELECT c.id, c.contract_name, c.acceptance_date, c.owner_id, u.name as owner_name
            FROM contracts c
            LEFT JOIN users u ON c.owner_id = u.username
            WHERE c.status = '执行中' AND c.acceptance_date IS NOT NULL AND c.acceptance_date != ''
                AND c.acceptance_date >= ? AND c.acceptance_date <= ?
            ORDER BY acceptance_date ASC
        """, (today, seven_days_later))
        rows = cursor.fetchall()
        for row in rows:
            alerts.append({
                'type': 'acceptance',
                'title': '验收预警',
                'detail': f"合同「{row['contract_name']}」验收日期即将到期",
                'due_date': row['acceptance_date'],
                'amount': 0,
                'owner': row['owner_name'],
                'contract_id': row['id']
            })

        cursor.execute("""
            SELECT b.id, b.title, b.predict_date, b.owner_id, u.name as owner_name
            FROM business b
            LEFT JOIN users u ON b.owner_id = u.username
            WHERE b.status = 'active' AND b.predict_date IS NOT NULL AND b.predict_date != ''
                AND substr(b.predict_date, 1, 7) IN (?, ?)
            ORDER BY predict_date ASC
        """, (this_month, next_month))
        rows = cursor.fetchall()
        for row in rows:
            alerts.append({
                'type': 'business',
                'title': '商机预警',
                'detail': f"商机「{row['title']}」预计成交日期即将到期",
                'due_date': row['predict_date'],
                'amount': 0,
                'owner': row['owner_name'],
                'business_id': row['id']
            })
    else:
        cursor.execute("""
            SELECT c.id, c.contract_name, c.expected_income_date, c.total_amt, c.paid_amt, c.owner_id, u.name as owner_name
            FROM contracts c
            LEFT JOIN users u ON c.owner_id = u.username
            WHERE c.status = '执行中' AND c.owner_id = ?
                AND c.expected_income_date IS NOT NULL AND c.expected_income_date != ''
                AND c.expected_income_date >= ? AND c.expected_income_date <= ?
            ORDER BY expected_income_date ASC
        """, (username, today, seven_days_later))
        rows = cursor.fetchall()
        for row in rows:
            alerts.append({
                'type': 'payment',
                'title': '回款预警',
                'detail': f"合同「{row['contract_name']}」预计回款日期即将到期",
                'due_date': row['expected_income_date'],
                'amount': (row['total_amt'] - row['paid_amt']) / 10000 if row['total_amt'] else 0,
                'owner': row['owner_name'],
                'contract_id': row['id']
            })

        cursor.execute("""
            SELECT c.id, c.contract_name, c.acceptance_date, c.owner_id, u.name as owner_name
            FROM contracts c
            LEFT JOIN users u ON c.owner_id = u.username
            WHERE c.status = '执行中' AND c.owner_id = ?
                AND c.acceptance_date IS NOT NULL AND c.acceptance_date != ''
                AND c.acceptance_date >= ? AND c.acceptance_date <= ?
            ORDER BY acceptance_date ASC
        """, (username, today, seven_days_later))
        rows = cursor.fetchall()
        for row in rows:
            alerts.append({
                'type': 'acceptance',
                'title': '验收预警',
                'detail': f"合同「{row['contract_name']}」验收日期即将到期",
                'due_date': row['acceptance_date'],
                'amount': 0,
                'owner': row['owner_name'],
                'contract_id': row['id']
            })

        cursor.execute("""
            SELECT b.id, b.title, b.predict_date, b.owner_id, u.name as owner_name
            FROM business b
            LEFT JOIN users u ON b.owner_id = u.username
            WHERE b.status = 'active' AND b.owner_id = ?
                AND b.predict_date IS NOT NULL AND b.predict_date != ''
                AND substr(b.predict_date, 1, 7) IN (?, ?)
            ORDER BY predict_date ASC
        """, (username, this_month, next_month))
        rows = cursor.fetchall()
        for row in rows:
            alerts.append({
                'type': 'business',
                'title': '商机预警',
                'detail': f"商机「{row['title']}」预计成交日期即将到期",
                'due_date': row['predict_date'],
                'amount': 0,
                'owner': row['owner_name'],
                'business_id': row['id']
            })

    alerts.sort(key=lambda x: x['due_date'])

    return jsonify({'code': 200, 'message': 'success', 'data': {'alerts': alerts, 'count': len(alerts)}})


# ==================== 用户偏好设置（5.6.1 多语言/多时区） ====================

def _ensure_preferences_table(cursor):
    """确保用户偏好表存在。"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            language TEXT DEFAULT 'zh-CN',
            timezone TEXT DEFAULT 'Asia/Shanghai',
            theme TEXT DEFAULT 'light',
            font_size TEXT DEFAULT 'medium',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)


@system_bp.route('/api/system/preferences', methods=['GET'])
@token_required
def get_preferences():
    """获取当前用户偏好设置（语言、时区等）。"""
    payload = request.current_user
    username = payload['username']

    db = get_db()
    cursor = db.cursor()
    _ensure_preferences_table(cursor)
    db.commit()

    cursor.execute("SELECT language, timezone, theme, font_size, updated_at FROM user_preferences WHERE username=?", (username,))
    row = cursor.fetchone()
    if not row:
        # 首次访问，返回默认值
        return jsonify({
            'code': 200,
            'message': 'success',
            'data': {
                'language': 'zh-CN',
                'timezone': 'Asia/Shanghai',
                'theme': 'light',
                'font_size': 'medium'
            }
        })

    return jsonify({'code': 200, 'message': 'success', 'data': dict(row)})


@system_bp.route('/api/system/preferences', methods=['PUT'])
@token_required
def update_preferences():
    """更新当前用户偏好设置。"""
    payload = request.current_user
    username = payload['username']

    data = request.get_json(silent=True) or {}
    # 白名单字段
    language = data.get('language')
    timezone = data.get('timezone')
    theme = data.get('theme')
    font_size = data.get('font_size')

    # 简单校验
    valid_languages = ('zh-CN', 'en-US')
    if language and language not in valid_languages:
        return jsonify({'code': 400, 'message': f'语言必须为 {valid_languages} 之一', 'data': None})

    valid_themes = ('light', 'dark')
    if theme and theme not in valid_themes:
        return jsonify({'code': 400, 'message': '主题必须为 light 或 dark', 'data': None})

    valid_font_sizes = ('small', 'medium', 'large')
    if font_size and font_size not in valid_font_sizes:
        return jsonify({'code': 400, 'message': '字号必须为 small/medium/large', 'data': None})

    db = get_db()
    cursor = db.cursor()
    _ensure_preferences_table(cursor)

    try:
        cursor.execute("""
            INSERT INTO user_preferences (username, language, timezone, theme, font_size, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(username) DO UPDATE SET
                language=COALESCE(excluded.language, language),
                timezone=COALESCE(excluded.timezone, timezone),
                theme=COALESCE(excluded.theme, theme),
                font_size=COALESCE(excluded.font_size, font_size),
                updated_at=CURRENT_TIMESTAMP
        """, (
            username,
            language or 'zh-CN',
            timezone or 'Asia/Shanghai',
            theme or 'light',
            font_size or 'medium'
        ))
        db.commit()
        return jsonify({'code': 200, 'message': '偏好设置已保存', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@system_bp.route('/api/system/timezones', methods=['GET'])
@token_required
def get_timezones():
    """返回常用时区列表，供前端选择。"""
    timezones = [
        {'value': 'Asia/Shanghai', 'label': '中国标准时间 (UTC+8)', 'offset': 8},
        {'value': 'Asia/Tokyo', 'label': '日本标准时间 (UTC+9)', 'offset': 9},
        {'value': 'Asia/Singapore', 'label': '新加坡时间 (UTC+8)', 'offset': 8},
        {'value': 'Asia/Hong_Kong', 'label': '香港时间 (UTC+8)', 'offset': 8},
        {'value': 'Asia/Seoul', 'label': '韩国标准时间 (UTC+9)', 'offset': 9},
        {'value': 'Asia/Dubai', 'label': '海湾标准时间 (UTC+4)', 'offset': 4},
        {'value': 'Europe/London', 'label': '格林尼治时间 (UTC+0)', 'offset': 0},
        {'value': 'Europe/Paris', 'label': '中欧时间 (UTC+1)', 'offset': 1},
        {'value': 'Europe/Moscow', 'label': '莫斯科时间 (UTC+3)', 'offset': 3},
        {'value': 'America/New_York', 'label': '美国东部时间 (UTC-5)', 'offset': -5},
        {'value': 'America/Chicago', 'label': '美国中部时间 (UTC-6)', 'offset': -6},
        {'value': 'America/Los_Angeles', 'label': '美国西部时间 (UTC-8)', 'offset': -8},
        {'value': 'UTC', 'label': '协调世界时 (UTC+0)', 'offset': 0},
    ]
    return jsonify({'code': 200, 'message': 'success', 'data': timezones})


def register_routes(app):
    app.register_blueprint(system_bp)
