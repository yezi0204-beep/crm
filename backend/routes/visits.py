from flask import request, jsonify
from extensions import get_db, record_operation_log, token_required
from datetime import datetime

from . import visits_bp


@visits_bp.route('/api/visits', methods=['GET'])
@token_required
def get_visits():
    payload = request.current_user
    username = payload['username']
    role = payload['role']
    
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    visitor_id = request.args.get('visitor_id', '')
    cust_id = request.args.get('cust_id', '')
    status = request.args.get('status', '')
    keyword = request.args.get('keyword', '')

    db = get_db()
    cursor = db.cursor()

    conditions = []
    params = []

    if role not in ('主任', '院长'):
        conditions.append("v.visitor_id = ?")
        params.append(username)

    if start_date:
        conditions.append("v.plan_date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("v.plan_date <= ?")
        params.append(end_date)
    if visitor_id:
        conditions.append("v.visitor_id = ?")
        params.append(visitor_id)
    if cust_id:
        conditions.append("v.cust_id = ?")
        params.append(cust_id)
    if status:
        conditions.append("v.status = ?")
        params.append(status)
    if keyword:
        conditions.append("(c.name LIKE ? OR c.company LIKE ? OR v.purpose LIKE ?)")
        params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])

    where_clause = ' AND '.join(conditions) if conditions else '1=1'

    cursor.execute(f"""
        SELECT v.*, c.name as customer_name, c.company as customer_company,
               c.contact_name as contact_name, c.phone as customer_phone,
               u.name as visitor_name
        FROM visits v
        LEFT JOIN customers c ON v.cust_id = c.id
        LEFT JOIN users u ON v.visitor_id = u.username
        WHERE {where_clause}
        ORDER BY v.plan_date DESC, v.plan_time DESC
    """, params)

    rows = cursor.fetchall()
    visits = [dict(row) for row in rows]

    return jsonify({'code': 200, 'message': 'success', 'data': visits})


@visits_bp.route('/api/visits/<int:visit_id>', methods=['GET'])
@token_required
def get_visit(visit_id):
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT v.*, c.name as customer_name, c.company as customer_company,
               c.contact_name as contact_name, c.phone as customer_phone,
               u.name as visitor_name
        FROM visits v
        LEFT JOIN customers c ON v.cust_id = c.id
        LEFT JOIN users u ON v.visitor_id = u.username
        WHERE v.id = ?
    """, (visit_id,))
    
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '拜访记录不存在', 'data': None})
    
    return jsonify({'code': 200, 'message': 'success', 'data': dict(row)})


@visits_bp.route('/api/visits', methods=['POST'])
@token_required
def create_visit():
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    work_type = data.get('work_type', 'visit')
    cust_id = data.get('cust_id') if work_type == 'visit' else None
    work_content = data.get('work_content') if work_type == 'other' else None

    try:
        cursor.execute("""
            INSERT INTO visits (cust_id, visitor_id, plan_date, plan_time, 
                               purpose, location, contact_person, notes, status,
                               work_type, work_content)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'planned', ?, ?)
        """, (
            cust_id,
            data.get('visitor_id', username),
            data.get('plan_date'),
            data.get('plan_time'),
            data.get('purpose'),
            data.get('location'),
            data.get('contact_person'),
            data.get('notes'),
            work_type,
            work_content
        ))
        db.commit()

        work_desc = data.get("purpose", "") if work_type == 'visit' else data.get("work_content", "")
        record_operation_log(username, '创建', '拜访排班', 
            f'创建{("拜访" if work_type == "visit" else "其它工作")}计划：{data.get("plan_date")} - {work_desc}')

        return jsonify({'code': 200, 'message': '创建成功', 'data': {'id': cursor.lastrowid}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@visits_bp.route('/api/visits/<int:visit_id>', methods=['PUT'])
@token_required
def update_visit(visit_id):
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']
    role = payload['role']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT visitor_id, status FROM visits WHERE id=?", (visit_id,))
    visit = cursor.fetchone()
    if not visit:
        return jsonify({'code': 404, 'message': '拜访记录不存在', 'data': None})

    if role not in ('主任', '院长') and visit['visitor_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足，只能编辑自己的拜访记录', 'data': None})

    try:
        updates = []
        params = []
        
        work_type = data.get('work_type')
        if work_type == 'other':
            data['cust_id'] = None
        
        allowed_fields = ['cust_id', 'visitor_id', 'plan_date', 'plan_time', 
                          'purpose', 'location', 'contact_person', 'notes', 'status',
                          'actual_date', 'actual_time', 'result', 'work_type', 'work_content']
        
        for field in allowed_fields:
            if field in data:
                updates.append(f"{field} = ?")
                params.append(data[field])
        
        if updates:
            updates.append("updated_at = ?")
            params.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            params.append(visit_id)
            
            cursor.execute(f"""
                UPDATE visits SET {', '.join(updates)} WHERE id = ?
            """, params)
            db.commit()

            record_operation_log(username, '编辑', '拜访排班', 
                f'编辑排班计划 ID:{visit_id}')

        return jsonify({'code': 200, 'message': '更新成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@visits_bp.route('/api/visits/<int:visit_id>', methods=['DELETE'])
@token_required
def delete_visit(visit_id):
    payload = request.current_user
    username = payload['username']
    role = payload['role']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT visitor_id FROM visits WHERE id=?", (visit_id,))
    visit = cursor.fetchone()
    if not visit:
        return jsonify({'code': 404, 'message': '拜访记录不存在', 'data': None})

    if role not in ('主任', '院长') and visit['visitor_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    try:
        cursor.execute("DELETE FROM visits WHERE id=?", (visit_id,))
        db.commit()

        record_operation_log(username, '删除', '拜访排班', f'删除拜访计划 ID:{visit_id}')

        return jsonify({'code': 200, 'message': '拜访记录删除成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@visits_bp.route('/api/visits/<int:visit_id>/complete', methods=['POST'])
@token_required
def complete_visit(visit_id):
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT visitor_id FROM visits WHERE id=?", (visit_id,))
    visit = cursor.fetchone()
    if not visit:
        return jsonify({'code': 404, 'message': '拜访记录不存在', 'data': None})

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    today = datetime.now().strftime('%Y-%m-%d')
    current_time = datetime.now().strftime('%H:%M')

    try:
        cursor.execute("""
            UPDATE visits 
            SET status = 'completed',
                actual_date = ?,
                actual_time = ?,
                result = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            data.get('actual_date', today),
            data.get('actual_time', current_time),
            data.get('result'),
            now,
            visit_id
        ))
        db.commit()

        record_operation_log(username, '完成', '拜访排班', f'完成拜访计划 ID:{visit_id}')

        return jsonify({'code': 200, 'message': '拜访已完成', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@visits_bp.route('/api/visits/<int:visit_id>/cancel', methods=['POST'])
@token_required
def cancel_visit(visit_id):
    payload = request.current_user
    username = payload['username']
    role = payload['role']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT visitor_id FROM visits WHERE id=?", (visit_id,))
    visit = cursor.fetchone()
    if not visit:
        return jsonify({'code': 404, 'message': '拜访记录不存在', 'data': None})

    if role not in ('主任', '院长') and visit['visitor_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    try:
        cursor.execute("""
            UPDATE visits 
            SET status = 'cancelled',
                updated_at = ?
            WHERE id = ?
        """, (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), visit_id))
        db.commit()

        record_operation_log(username, '取消', '拜访排班', f'取消拜访计划 ID:{visit_id}')

        return jsonify({'code': 200, 'message': '拜访已取消', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@visits_bp.route('/api/visits/stats/summary', methods=['GET'])
@token_required
def get_visit_stats():
    payload = request.current_user
    username = payload['username']
    role = payload['role']
    
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))

    db = get_db()
    cursor = db.cursor()

    if role in ('主任', '院长'):
        base_where = "1=1"
        params = []
    else:
        base_where = "visitor_id = ?"
        params = [username]

    cursor.execute(f"""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'planned' THEN 1 ELSE 0 END) as planned,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled
        FROM visits
        WHERE {base_where} AND plan_date LIKE ?
    """, params + [f'{month}%'])

    row = cursor.fetchone()
    stats = dict(row)

    return jsonify({'code': 200, 'message': 'success', 'data': stats})


def register_routes(app):
    app.register_blueprint(visits_bp)
