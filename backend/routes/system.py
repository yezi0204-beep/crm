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
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT username, name, role FROM users ORDER BY name")

    rows = cursor.fetchall()
    users = []
    for row in rows:
        users.append(dict(row))

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

        hashed_pwd = hash_password(data.get('password'))
        cursor.execute("""
            INSERT INTO users (username, password_hash, name, role)
            VALUES (?, ?, ?, ?)
        """, (data.get('username'), hashed_pwd, data.get('name'), data.get('role')))
        db.commit()

        return jsonify({'code': 200, 'message': '用户创建成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@system_bp.route('/api/users/<username>', methods=['DELETE'])
@admin_required
def delete_user(username):
    db = get_db()
    cursor = db.cursor()

    try:
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
