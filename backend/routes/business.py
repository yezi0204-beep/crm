from flask import request, jsonify, g
from extensions import (
    get_db, verify_token, record_operation_log,
    token_required, admin_required,
)
from datetime import datetime
import logging

from . import business_bp

logger = logging.getLogger(__name__)


def auto_roll_over_plans(db):
    """自动滚动更新过期的商机周计划"""
    if getattr(g, '_plans_rolled_over', False):
        return
    
    today = datetime.now()
    current_week_num = int(today.strftime('%W'))
    current_week_str = today.strftime('%Y-W%W')
    
    cursor = db.cursor()
    
    try:
        # 1. 归档过期的 weekly_plan 到历史记录（仅当有 next_week_plan 即将替换时才归档）
        cursor.execute("""
            INSERT INTO business_plan_history (business_id, plan_type, week_label, content, created_at)
            SELECT id, 'weekly', plan_week, weekly_plan, CURRENT_TIMESTAMP
            FROM business
            WHERE status = 'active' AND plan_week IS NOT NULL AND plan_week != ''
                AND CAST(SUBSTR(plan_week, 7) AS INTEGER) <= ?
                AND weekly_plan IS NOT NULL AND weekly_plan != ''
                AND next_week_plan IS NOT NULL AND next_week_plan != ''
        """, (current_week_num,))

        # 2. 归档过期的 next_week_plan 到历史记录
        cursor.execute("""
            INSERT INTO business_plan_history (business_id, plan_type, week_label, content, created_at)
            SELECT id, 'next_week', plan_week, next_week_plan, CURRENT_TIMESTAMP
            FROM business
            WHERE status = 'active' AND plan_week IS NOT NULL AND plan_week != ''
                AND CAST(SUBSTR(plan_week, 7) AS INTEGER) <= ?
                AND next_week_plan IS NOT NULL AND next_week_plan != ''
        """, (current_week_num,))

        # 3. 有 next_week_plan 的记录：滚动 next_week_plan → weekly_plan
        cursor.execute("""
            UPDATE business SET
                weekly_plan = next_week_plan,
                next_week_plan = '',
                plan_week = ?
            WHERE status = 'active' AND plan_week IS NOT NULL AND plan_week != ''
                AND CAST(SUBSTR(plan_week, 7) AS INTEGER) <= ?
                AND next_week_plan IS NOT NULL AND next_week_plan != ''
        """, (current_week_str, current_week_num))

        # 4. 无 next_week_plan 的记录：仅更新 plan_week 到当前周，不清空 weekly_plan
        cursor.execute("""
            UPDATE business SET
                plan_week = ?
            WHERE status = 'active' AND plan_week IS NOT NULL AND plan_week != ''
                AND CAST(SUBSTR(plan_week, 7) AS INTEGER) <= ?
                AND (next_week_plan IS NULL OR next_week_plan = '')
        """, (current_week_str, current_week_num))
        
        db.commit()
        g._plans_rolled_over = True
        
        updated_count = cursor.rowcount
        if updated_count > 0:
            logger.info(f"自动滚动更新了 {updated_count} 个商机的周计划")
    except Exception as e:
        logger.error(f"自动滚动更新周计划失败: {e}")
        db.rollback()


@business_bp.route('/api/business/roll_over_plans', methods=['POST'])
@admin_required
def roll_over_business_plans():
    payload = request.current_user

    db = get_db()
    auto_roll_over_plans(db)

    record_operation_log(payload['username'], '执行', '商机', '滚动更新商机周计划')
    return jsonify({'code': 200, 'message': '周计划滚动更新成功', 'data': None})


@business_bp.route('/api/business', methods=['GET'])
@token_required
def get_business():
    payload = request.current_user
    username = payload['username']
    role = payload['role']
    status = request.args.get('status', 'active')

    db = get_db()
    auto_roll_over_plans(db)
    cursor = db.cursor()

    if status == 'deleted':
        db_status = 'void'
    else:
        db_status = status

    if role == '主任' or role == '院长':
        if status == 'all':
            cursor.execute("""
                SELECT b.*, c.company as customer_name, c.name as customer_contact, u.name as owner_name
                FROM business b
                LEFT JOIN customers c ON b.cust_id = c.id
                LEFT JOIN users u ON b.owner_id = u.username
                ORDER BY b.created_at DESC
            """)
        else:
            cursor.execute("""
                SELECT b.*, c.company as customer_name, c.name as customer_contact, u.name as owner_name
                FROM business b
                LEFT JOIN customers c ON b.cust_id = c.id
                LEFT JOIN users u ON b.owner_id = u.username
                WHERE b.status = ?
                ORDER BY b.created_at DESC
            """, (db_status,))
    else:
        if status == 'all':
            cursor.execute("""
                SELECT b.*, c.company as customer_name, c.name as customer_contact, u.name as owner_name
                FROM business b
                LEFT JOIN customers c ON b.cust_id = c.id
                LEFT JOIN users u ON b.owner_id = u.username
                WHERE b.owner_id = ?
                ORDER BY b.created_at DESC
            """, (username,))
        else:
            cursor.execute("""
                SELECT b.*, c.company as customer_name, c.name as customer_contact, u.name as owner_name
                FROM business b
                LEFT JOIN customers c ON b.cust_id = c.id
                LEFT JOIN users u ON b.owner_id = u.username
                WHERE b.owner_id = ? AND b.status = ?
                ORDER BY b.created_at DESC
            """, (username, db_status))

    rows = cursor.fetchall()
    business = []
    for row in rows:
        business.append(dict(row))

    return jsonify({'code': 200, 'message': 'success', 'data': business})


@business_bp.route('/api/business', methods=['POST'])
@token_required
def create_business():
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    try:
        plan_week = data.get('plan_week')
        if plan_week == 'auto':
            today = datetime.now()
            current_week_num = int(today.strftime('%W'))
            plan_week = today.strftime('%Y-W') + str(current_week_num + 1).zfill(2)

        cursor.execute("""
            INSERT INTO business (title, cust_id, stakeholder, amount, stage, probability, predict_date, source, industry, region, owner_id, address, customer_relation, weekly_plan, next_week_plan, plan_week, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get('title'), data.get('cust_id'), data.get('stakeholder'), data.get('amount'), data.get('stage'),
            data.get('probability'), data.get('predict_date'), data.get('source'), data.get('industry'), data.get('region'), data.get('owner_id'),
            data.get('address'), data.get('customer_relation'), data.get('weekly_plan'), data.get('next_week_plan'), plan_week,
            data.get('note')
        ))
        db.commit()

        record_operation_log(username, '创建', '商机', f'创建商机：{data.get("title")}')

        return jsonify({'code': 200, 'message': '商机创建成功', 'data': {'id': cursor.lastrowid}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@business_bp.route('/api/business/<int:business_id>', methods=['DELETE'])
@token_required
def delete_business(business_id):
    payload = request.current_user
    role = payload.get('role', '')
    username = payload.get('username', '')

    cursor = get_db().cursor()
    cursor.execute("SELECT owner_id, title FROM business WHERE id=?", (business_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '商机不存在', 'data': None})

    if role not in ('主任', '院长') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足，只能作废自己的商机', 'data': None})

    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("UPDATE business SET status = 'void' WHERE id=?", (business_id,))
        db.commit()

        record_operation_log(username, '作废', '商机', f'作废商机：{row["title"]}')

        return jsonify({'code': 200, 'message': '商机作废成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@business_bp.route('/api/business/<int:business_id>/restore', methods=['PUT'])
@token_required
def restore_business(business_id):
    payload = request.current_user
    role = payload.get('role', '')
    username = payload.get('username', '')

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id, title FROM business WHERE id=?", (business_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '商机不存在', 'data': None})

    if role not in ('主任', '院长') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足，只能恢复自己的商机', 'data': None})

    try:
        cursor.execute("UPDATE business SET status = 'active' WHERE id=?", (business_id,))
        db.commit()

        record_operation_log(username, '恢复', '商机', f'恢复商机：{row["title"]}')

        return jsonify({'code': 200, 'message': '商机恢复成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@business_bp.route('/api/business/<int:business_id>', methods=['PUT'])
@token_required
def update_business(business_id):
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("SELECT weekly_plan, next_week_plan, plan_week FROM business WHERE id=?", (business_id,))
        old_data = cursor.fetchone()

        plan_week = data.get('plan_week')
        if plan_week == 'auto':
            today = datetime.now()
            current_week_num = int(today.strftime('%W'))
            plan_week = today.strftime('%Y-W') + str(current_week_num + 1).zfill(2)

        new_weekly_plan = data.get('weekly_plan', '')
        new_next_week_plan = data.get('next_week_plan', '')

        if old_data:
            old_weekly_plan = old_data['weekly_plan']
            old_next_week_plan = old_data['next_week_plan']
            old_plan_week = old_data['plan_week']

            if old_weekly_plan and old_weekly_plan != new_weekly_plan:
                cursor.execute("""
                    INSERT INTO business_plan_history (business_id, plan_type, week_label, content, created_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (business_id, 'weekly', old_plan_week or '', old_weekly_plan))

            if old_next_week_plan and old_next_week_plan != new_next_week_plan:
                cursor.execute("""
                    INSERT INTO business_plan_history (business_id, plan_type, week_label, content, created_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (business_id, 'next_week', plan_week or '', old_next_week_plan))

        current_role = payload.get('role', '')
        can_change_owner = current_role == '主任' or current_role == '院长'

        if can_change_owner and 'owner_id' in data:
            cursor.execute("""
                UPDATE business SET
                    title=?, cust_id=?, stakeholder=?, amount=?, stage=?, probability=?, predict_date=?,
                    source=?, industry=?, region=?, address=?, customer_relation=?,
                    weekly_plan=?, next_week_plan=?, plan_week=?, owner_id=?, note=?
                WHERE id=?
            """, (
                data.get('title'), data.get('cust_id'), data.get('stakeholder'),
                data.get('amount'), data.get('stage'), data.get('probability'), data.get('predict_date'),
                data.get('source'), data.get('industry'), data.get('region'),
                data.get('address'), data.get('customer_relation'),
                data.get('weekly_plan'), data.get('next_week_plan'), plan_week,
                data.get('owner_id'), data.get('note'), business_id
            ))
        else:
            cursor.execute("""
                UPDATE business SET
                    title=?, cust_id=?, stakeholder=?, amount=?, stage=?, probability=?, predict_date=?,
                    source=?, industry=?, region=?, address=?, customer_relation=?,
                    weekly_plan=?, next_week_plan=?, plan_week=?, note=?
                WHERE id=?
            """, (
                data.get('title'), data.get('cust_id'), data.get('stakeholder'),
                data.get('amount'), data.get('stage'), data.get('probability'), data.get('predict_date'),
                data.get('source'), data.get('industry'), data.get('region'),
                data.get('address'), data.get('customer_relation'),
                data.get('weekly_plan'), data.get('next_week_plan'), plan_week,
                data.get('note'), business_id
            ))
        db.commit()

        record_operation_log(username, '编辑', '商机', f'编辑商机：{data.get("title")}（ID:{business_id}）')

        return jsonify({'code': 200, 'message': '商机更新成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@business_bp.route('/api/business/<int:business_id>/plan_history', methods=['GET'])
@token_required
def get_business_plan_history(business_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT id, plan_type, week_label, content, created_at
        FROM business_plan_history
        WHERE business_id = ?
        ORDER BY created_at DESC
    """, (business_id,))

    rows = cursor.fetchall()
    history = []
    for row in rows:
        history.append({
            'id': row['id'],
            'plan_type': row['plan_type'],
            'week_label': row['week_label'],
            'content': row['content'],
            'created_at': row['created_at']
        })

    return jsonify({'code': 200, 'message': 'success', 'data': history})


def register_routes(app):
    app.register_blueprint(business_bp)