from flask import request, jsonify, g
from extensions import (
    get_db, verify_token, create_token, check_password, hash_password,
    record_operation_log, token_required, admin_required,
    check_login_rate_limit, record_login_attempt,
    LOGIN_ATTEMPTS, LOGIN_MAX_ATTEMPTS,
)

from . import customers_bp


@customers_bp.route('/api/customers', methods=['GET'])
@token_required
def get_customers():
    payload = request.current_user
    username = payload['username']
    role = payload['role']
    keyword = request.args.get('keyword', '')

    db = get_db()
    cursor = db.cursor()

    if role == '主任' or role == '院长':
        if keyword:
            cursor.execute("""
                SELECT c.*, u.name as owner_name
                FROM customers c
                LEFT JOIN users u ON c.owner_id = u.username
                WHERE c.company LIKE ? OR c.name LIKE ? OR c.contact_name LIKE ?
                ORDER BY c.created_at DESC
            """, (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'))
        else:
            cursor.execute("""
                SELECT c.*, u.name as owner_name
                FROM customers c
                LEFT JOIN users u ON c.owner_id = u.username
                ORDER BY c.created_at DESC
            """)
    else:
        if keyword:
            cursor.execute("""
                SELECT c.*, u.name as owner_name
                FROM customers c
                LEFT JOIN users u ON c.owner_id = u.username
                WHERE c.owner_id = ? AND (c.company LIKE ? OR c.name LIKE ? OR c.contact_name LIKE ?)
                ORDER BY c.created_at DESC
            """, (username, f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'))
        else:
            cursor.execute("""
                SELECT c.*, u.name as owner_name
                FROM customers c
                LEFT JOIN users u ON c.owner_id = u.username
                WHERE c.owner_id = ?
                ORDER BY c.created_at DESC
            """, (username,))

    rows = cursor.fetchall()
    customers = []
    for row in rows:
        customers.append(dict(row))

    return jsonify({'code': 200, 'message': 'success', 'data': customers})


@customers_bp.route('/api/customers', methods=['POST'])
@token_required
def create_customer():
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("""
            INSERT INTO customers (name, company, phone, level, source, owner_id, contact_name, email, industry, region, created_at, last_follow)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (
            data.get('name'), data.get('company'), data.get('phone'),
            data.get('level'), data.get('source'), data.get('owner_id'),
            data.get('contact_name'), data.get('email'), data.get('industry'), data.get('region')
        ))
        db.commit()

        record_operation_log(username, '创建', '客户', f'创建客户：{data.get("name")}（{data.get("company")}）')

        return jsonify({'code': 200, 'message': '客户创建成功', 'data': {'id': cursor.lastrowid}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@customers_bp.route('/api/customers/<int:cust_id>', methods=['DELETE'])
@token_required
def delete_customer(cust_id):
    payload = request.current_user
    role = payload.get('role', '')
    username = payload.get('username', '')

    cursor = get_db().cursor()
    cursor.execute("SELECT owner_id FROM customers WHERE id=?", (cust_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '客户不存在', 'data': None})

    if role not in ('主任', '院长') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足，只能删除自己的客户', 'data': None})

    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("SELECT name, company FROM customers WHERE id=?", (cust_id,))
        row = cursor.fetchone()
        customer_info = f"{row['name']}（{row['company']}）" if row else f"ID:{cust_id}"

        cursor.execute("UPDATE business SET cust_id = NULL WHERE cust_id = ?", (cust_id,))
        cursor.execute("DELETE FROM customers WHERE id=?", (cust_id,))
        db.commit()

        record_operation_log(payload['username'], '删除', '客户', f'删除客户：{customer_info}')

        return jsonify({'code': 200, 'message': '客户删除成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@customers_bp.route('/api/customers/<int:cust_id>', methods=['PUT'])
@token_required
def update_customer(cust_id):
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    try:
        current_role = payload.get('role', '')
        can_change_owner = current_role == '主任' or current_role == '院长'

        if can_change_owner and 'owner_id' in data:
            cursor.execute("""
                UPDATE customers SET
                    name=?, company=?, phone=?, level=?, source=?,
                    contact_name=?, email=?, industry=?, region=?,
                    owner_id=?, previous_owner=owner_id
                WHERE id=?
            """, (
                data.get('name'), data.get('company'), data.get('phone'),
                data.get('level'), data.get('source'),
                data.get('contact_name'), data.get('email'),
                data.get('industry'), data.get('region'),
                data.get('owner_id'), cust_id
            ))
        else:
            cursor.execute("""
                UPDATE customers SET
                    name=?, company=?, phone=?, level=?, source=?,
                    contact_name=?, email=?, industry=?, region=?
                WHERE id=?
            """, (
                data.get('name'), data.get('company'), data.get('phone'),
                data.get('level'), data.get('source'),
                data.get('contact_name'), data.get('email'),
                data.get('industry'), data.get('region'), cust_id
            ))
        db.commit()

        record_operation_log(username, '编辑', '客户', f'编辑客户：{data.get("name")}（ID:{cust_id}）')

        return jsonify({'code': 200, 'message': '客户更新成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


def register_routes(app):
    app.register_blueprint(customers_bp)
