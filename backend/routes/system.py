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

    if role == '主任' or role == '院长':
        cursor.execute("""
            SELECT id, contract_name, expected_income_date, total_amt, paid_amt, owner_id, u.name as owner_name
            FROM contracts c
            LEFT JOIN users u ON c.owner_id = u.username
            WHERE status = '执行中' AND expected_income_date IS NOT NULL AND expected_income_date != ''
                AND expected_income_date >= ? AND expected_income_date <= ?
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
            SELECT id, contract_name, acceptance_date, owner_id, u.name as owner_name
            FROM contracts c
            LEFT JOIN users u ON c.owner_id = u.username
            WHERE status = '执行中' AND acceptance_date IS NOT NULL AND acceptance_date != ''
                AND acceptance_date >= ? AND acceptance_date <= ?
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
            SELECT id, title, predict_date, owner_id, u.name as owner_name
            FROM business b
            LEFT JOIN users u ON b.owner_id = u.username
            WHERE status = 'active' AND predict_date IS NOT NULL AND predict_date != ''
                AND predict_date >= ? AND predict_date <= ?
            ORDER BY predict_date ASC
        """, (today, seven_days_later))
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
            SELECT id, contract_name, expected_income_date, total_amt, paid_amt, owner_id, u.name as owner_name
            FROM contracts c
            LEFT JOIN users u ON c.owner_id = u.username
            WHERE status = '执行中' AND owner_id = ?
                AND expected_income_date IS NOT NULL AND expected_income_date != ''
                AND expected_income_date >= ? AND expected_income_date <= ?
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
            SELECT id, contract_name, acceptance_date, owner_id, u.name as owner_name
            FROM contracts c
            LEFT JOIN users u ON c.owner_id = u.username
            WHERE status = '执行中' AND owner_id = ?
                AND acceptance_date IS NOT NULL AND acceptance_date != ''
                AND acceptance_date >= ? AND acceptance_date <= ?
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
            SELECT id, title, predict_date, owner_id, u.name as owner_name
            FROM business b
            LEFT JOIN users u ON b.owner_id = u.username
            WHERE status = 'active' AND owner_id = ?
                AND predict_date IS NOT NULL AND predict_date != ''
                AND predict_date >= ? AND predict_date <= ?
            ORDER BY predict_date ASC
        """, (username, today, seven_days_later))
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


def register_routes(app):
    app.register_blueprint(system_bp)
