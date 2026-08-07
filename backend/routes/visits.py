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
    """完成拜访排班，同时创建跟进记录并同步到客户和商机。

    请求体可选字段（除了原有的 actual_date/actual_time/result，新增跟进信息）：
      - follow_content: 跟进详细内容
      - follow_type: 跟进方式（面谈/电话/邮件等）
      - next_action: 下一步行动
      - next_date: 下一步日期
      - business_ids: 关联的商机ID列表
    """
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT * FROM visits WHERE id=?", (visit_id,))
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

        # 仅对"客户拜访"类型创建跟进记录
        visit_dict = dict(visit)
        if visit_dict.get('work_type') == 'visit' and visit_dict.get('cust_id'):
            follow_content = data.get('follow_content') or data.get('result', '')
            follow_type = data.get('follow_type', '拜访')
            next_action = data.get('next_action', '')
            next_date = data.get('next_date', '')

            # 跟进内容格式：[跟进方式] + 跟进详情 + 拜访目的
            full_content = follow_content
            if follow_type:
                full_content = f"[{follow_type}] {follow_content}" if follow_content else f"[{follow_type}]"
            if visit_dict.get('purpose'):
                full_content += f"\n拜访目的：{visit_dict['purpose']}"

            # 1. 创建客户跟进记录
            cursor.execute("""
                INSERT INTO follow_logs (ref_type, ref_id, user_id, content, next_plan, log_time, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                'customer',
                visit_dict['cust_id'],
                username,
                full_content,
                next_action,
                now,
                now
            ))
            follow_id = cursor.lastrowid

            # 更新客户的最后跟进时间
            cursor.execute("UPDATE customers SET last_follow = ? WHERE id = ?", (now, visit_dict['cust_id']))

            # 2. 创建商机跟进记录（关联商机或自动关联客户活跃商机）
            business_ids = data.get('business_ids', [])
            if not business_ids:
                # 自动关联该客户的活跃商机
                cursor.execute("""
                    SELECT id FROM business
                    WHERE cust_id = ? AND status IN ('active', '跟进中')
                    ORDER BY id DESC LIMIT 5
                """, (visit_dict['cust_id'],))
                business_ids = [row['id'] for row in cursor.fetchall()]
            else:
                # 验证商机归属
                valid_ids = []
                for bid in business_ids:
                    cursor.execute("SELECT id FROM business WHERE id=? AND cust_id=?", (bid, visit_dict['cust_id']))
                    if cursor.fetchone():
                        valid_ids.append(bid)
                business_ids = valid_ids

            biz_follow_count = 0
            for bid in business_ids:
                cursor.execute("""
                    INSERT INTO follow_logs (ref_type, ref_id, user_id, content, next_plan, log_time, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    'business',
                    bid,
                    username,
                    f"[{follow_type or '拜访'}] {follow_content}",
                    next_action,
                    now,
                    now
                ))
                # 更新商机的最后跟进时间
                cursor.execute("UPDATE business SET last_follow = ? WHERE id = ?", (now, bid))
                biz_follow_count += 1

            record_operation_log(username, '完成', '拜访排班',
                f'完成拜访(ID:{visit_id})，创建客户跟进(ID:{follow_id})，关联{len(business_ids)}个商机跟进')

        db.commit()

        record_operation_log(username, '完成', '拜访排班', f'完成拜访计划 ID:{visit_id}')

        return jsonify({
            'code': 200,
            'message': '拜访已完成，跟进记录已同步',
            'data': {
                'visit_id': visit_id,
                'customer_follow_created': visit_dict.get('work_type') == 'visit' and visit_dict.get('cust_id') is not None,
                'business_follow_count': biz_follow_count if visit_dict.get('work_type') == 'visit' else 0
            }
        })
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@visits_bp.route('/api/visits/<int:visit_id>/update-complete', methods=['POST'])
@token_required
def update_complete_visit(visit_id):
    """修改已完成拜访的完成内容（不重复创建跟进记录）。

    请求体可选字段：
      - actual_date: 实际日期
      - actual_time: 实际时间
      - result: 完成结果/跟进内容
    """
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']
    role = payload['role']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT visitor_id, status, work_type, cust_id FROM visits WHERE id=?", (visit_id,))
    visit = cursor.fetchone()
    if not visit:
        return jsonify({'code': 404, 'message': '拜访记录不存在', 'data': None})

    if role not in ('主任', '院长') and visit['visitor_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    if visit['status'] != 'completed':
        return jsonify({'code': 400, 'message': '只能修改已完成的拜访', 'data': None})

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        cursor.execute("""
            UPDATE visits
            SET actual_date = ?,
                actual_time = ?,
                result = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            data.get('actual_date'),
            data.get('actual_time'),
            data.get('result'),
            now,
            visit_id
        ))
        db.commit()

        record_operation_log(username, '修改', '拜访排班',
                             f'修改已完成拜访(ID:{visit_id})的完成内容')

        return jsonify({
            'code': 200,
            'message': '完成记录已更新',
            'data': {'visit_id': visit_id}
        })
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
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


@visits_bp.route('/api/visits/customer-businesses/<int:cust_id>', methods=['GET'])
@token_required
def get_customer_businesses(cust_id):
    """获取客户的活跃商机列表，用于拜访完成时选择关联商机。"""
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT id, title as name, stage, probability, status
        FROM business
        WHERE cust_id = ? AND status IN ('active', '跟进中', '新建')
        ORDER BY CASE status 
            WHEN 'active' THEN 1 
            WHEN '跟进中' THEN 2 
            WHEN '新建' THEN 3 
        END, id DESC
    """, (cust_id,))

    rows = cursor.fetchall()
    businesses = [dict(row) for row in rows]

    return jsonify({'code': 200, 'message': 'success', 'data': businesses})


def register_routes(app):
    app.register_blueprint(visits_bp)
