from flask import request, jsonify
from extensions import get_db, record_operation_log, token_required
from datetime import datetime

from . import tickets_bp

# 工单状态状态机：
# new(新工单) → processing(处理中) → pending(待客户反馈) → resolved(已解决) → closed(已关闭)
# resolved → reopened(已重开) → processing
VALID_STATUSES = ('new', 'processing', 'pending', 'resolved', 'closed', 'reopened')
TERMINAL_STATUSES = ('closed',)  # closed 后不可再变更

# 工单类型
VALID_TYPES = ('consult', 'complaint', 'suggestion', 'fault', 'other')

# 优先级
VALID_PRIORITIES = ('low', 'normal', 'high', 'urgent')

# 工单来源
VALID_SOURCES = ('phone', 'email', 'wechat', 'online', 'onsite', 'other')


def _generate_ticket_no(cursor):
    """生成工单号：T + 年月日 + 当日序号"""
    today = datetime.now().strftime('%Y%m%d')
    prefix = f'T{today}'
    cursor.execute("SELECT COUNT(*) as cnt FROM tickets WHERE ticket_no LIKE ?", (f'{prefix}%',))
    cnt = cursor.fetchone()['cnt']
    return f'{prefix}{(cnt + 1):04d}'


# ==================== 工单 CRUD ====================

@tickets_bp.route('/api/tickets', methods=['GET'])
@token_required
def get_tickets():
    """工单列表：支持关键字、类型、状态、优先级、客户筛选。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    keyword = request.args.get('keyword', '')
    ticket_type = request.args.get('type', '')
    status = request.args.get('status', '')
    priority = request.args.get('priority', '')
    cust_id = request.args.get('cust_id', '')

    db = get_db()
    cursor = db.cursor()

    conditions = []
    params = []

    # 普通销售：可见自己负责的 + 自己创建的；管理层可见全部
    if role not in ('主任', '院长'):
        conditions.append("(t.owner_id = ? OR t.created_by = ?)")
        params.extend([username, username])

    if keyword:
        conditions.append("(t.ticket_no LIKE ? OR t.title LIKE ? OR t.description LIKE ? OR t.resolution LIKE ?)")
        kw = f'%{keyword}%'
        params.extend([kw, kw, kw, kw])
    if ticket_type:
        conditions.append("t.type = ?")
        params.append(ticket_type)
    if status:
        conditions.append("t.status = ?")
        params.append(status)
    if priority:
        conditions.append("t.priority = ?")
        params.append(priority)
    if cust_id:
        conditions.append("t.cust_id = ?")
        params.append(cust_id)

    where_clause = ' AND '.join(conditions) if conditions else '1=1'

    cursor.execute(f"""
        SELECT t.*, c.company as customer_name, c.name as customer_contact,
               p.name as product_name, u.name as owner_name,
               cu.name as creator_name, s.overall_score as survey_score
        FROM tickets t
        LEFT JOIN customers c ON t.cust_id = c.id
        LEFT JOIN products p ON t.product_id = p.id
        LEFT JOIN users u ON t.owner_id = u.username
        LEFT JOIN users cu ON t.created_by = cu.username
        LEFT JOIN ticket_surveys s ON t.id = s.ticket_id
        WHERE {where_clause}
        ORDER BY t.updated_at DESC
    """, params)

    rows = cursor.fetchall()
    data = [dict(r) for r in rows]
    return jsonify({'code': 200, 'message': 'success', 'data': data})


@tickets_bp.route('/api/tickets/<int:ticket_id>', methods=['GET'])
@token_required
def get_ticket_detail(ticket_id):
    """工单详情：含主表 + 消息记录 + 满意度调查。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    if role in ('主任', '院长'):
        cursor.execute("""
            SELECT t.*, c.company as customer_name, c.name as customer_contact,
                   p.name as product_name, u.name as owner_name,
                   cu.name as creator_name
            FROM tickets t
            LEFT JOIN customers c ON t.cust_id = c.id
            LEFT JOIN products p ON t.product_id = p.id
            LEFT JOIN users u ON t.owner_id = u.username
            LEFT JOIN users cu ON t.created_by = cu.username
            WHERE t.id = ?
        """, (ticket_id,))
    else:
        cursor.execute("""
            SELECT t.*, c.company as customer_name, c.name as customer_contact,
                   p.name as product_name, u.name as owner_name,
                   cu.name as creator_name
            FROM tickets t
            LEFT JOIN customers c ON t.cust_id = c.id
            LEFT JOIN products p ON t.product_id = p.id
            LEFT JOIN users u ON t.owner_id = u.username
            LEFT JOIN users cu ON t.created_by = cu.username
            WHERE t.id = ? AND (t.owner_id = ? OR t.created_by = ?)
        """, (ticket_id, username, username))

    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '工单不存在', 'data': None})

    ticket = dict(row)

    # 消息记录
    cursor.execute("""
        SELECT * FROM ticket_messages
        WHERE ticket_id = ?
        ORDER BY created_at ASC
    """, (ticket_id,))
    ticket['messages'] = [dict(r) for r in cursor.fetchall()]

    # 满意度调查
    cursor.execute("""
        SELECT * FROM ticket_surveys
        WHERE ticket_id = ?
    """, (ticket_id,))
    survey_row = cursor.fetchone()
    ticket['survey'] = dict(survey_row) if survey_row else None

    return jsonify({'code': 200, 'message': 'success', 'data': ticket})


@tickets_bp.route('/api/tickets', methods=['POST'])
@token_required
def create_ticket():
    """创建服务工单（问题、投诉、咨询等）。"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']

    if not data.get('title'):
        return jsonify({'code': 400, 'message': '工单标题不能为空', 'data': None})

    ticket_type = (data.get('type') or 'consult').lower()
    if ticket_type not in VALID_TYPES:
        return jsonify({'code': 400, 'message': f'type 必须为 {VALID_TYPES} 之一', 'data': None})

    priority = (data.get('priority') or 'normal').lower()
    if priority not in VALID_PRIORITIES:
        return jsonify({'code': 400, 'message': f'priority 必须为 {VALID_PRIORITIES} 之一', 'data': None})

    db = get_db()
    cursor = db.cursor()
    ticket_no = data.get('ticket_no') or _generate_ticket_no(cursor)

    try:
        cursor.execute("""
            INSERT INTO tickets (ticket_no, title, type, priority, status, cust_id,
                contact_name, contact_info, source, product_id, description,
                owner_id, created_by, created_at, updated_at, due_date, remark)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?, ?)
        """, (
            ticket_no, data.get('title'), ticket_type, priority, data.get('status') or 'new',
            data.get('cust_id'), data.get('contact_name'), data.get('contact_info'),
            data.get('source'), data.get('product_id'), data.get('description'),
            data.get('owner_id') or username, username, data.get('due_date'),
            data.get('remark') or ''
        ))
        ticket_id = cursor.lastrowid

        # 如果有初始描述，作为第一条消息记录
        if data.get('description'):
            cursor.execute("""
                INSERT INTO ticket_messages (ticket_id, sender_id, sender_name, sender_type,
                    content, is_internal, created_at)
                VALUES (?, ?, ?, 'operator', ?, 0, CURRENT_TIMESTAMP)
            """, (ticket_id, username, payload.get('name') or username, data['description']))

        db.commit()
        record_operation_log(username, '创建', '工单', f'创建工单 {ticket_no}：{data.get("title")}')
        return jsonify({'code': 200, 'message': '工单创建成功', 'data': {'id': ticket_id, 'ticket_no': ticket_no}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@tickets_bp.route('/api/tickets/<int:ticket_id>', methods=['PUT'])
@token_required
def update_ticket(ticket_id):
    """编辑工单基础信息。"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']
    role = payload['role']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id, created_by, title, status FROM tickets WHERE id=?", (ticket_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '工单不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username and row['created_by'] != username:
        return jsonify({'code': 403, 'message': '权限不足，只能操作自己的工单', 'data': None})

    # closed 状态不可编辑
    if row['status'] == 'closed':
        return jsonify({'code': 400, 'message': '工单已关闭，不可编辑', 'data': None})

    ticket_type = (data.get('type') or row['status'])
    if data.get('type') and ticket_type.lower() not in VALID_TYPES:
        return jsonify({'code': 400, 'message': f'type 必须为 {VALID_TYPES} 之一', 'data': None})

    priority = (data.get('priority') or 'normal').lower()
    if data.get('priority') and priority not in VALID_PRIORITIES:
        return jsonify({'code': 400, 'message': f'priority 必须为 {VALID_PRIORITIES} 之一', 'data': None})

    can_change_owner = role in ('主任', '院长')
    try:
        if can_change_owner and 'owner_id' in data:
            cursor.execute("""
                UPDATE tickets SET
                    title=?, type=?, priority=?, cust_id=?, contact_name=?, contact_info=?,
                    source=?, product_id=?, description=?, resolution=?, owner_id=?,
                    due_date=?, remark=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (
                data.get('title'), data.get('type') or None,
                data.get('priority') or None, data.get('cust_id'),
                data.get('contact_name'), data.get('contact_info'),
                data.get('source'), data.get('product_id'),
                data.get('description'), data.get('resolution'),
                data.get('owner_id'), data.get('due_date'),
                data.get('remark'), ticket_id
            ))
        else:
            cursor.execute("""
                UPDATE tickets SET
                    title=?, type=?, priority=?, cust_id=?, contact_name=?, contact_info=?,
                    source=?, product_id=?, description=?, resolution=?,
                    due_date=?, remark=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (
                data.get('title'), data.get('type') or None,
                data.get('priority') or None, data.get('cust_id'),
                data.get('contact_name'), data.get('contact_info'),
                data.get('source'), data.get('product_id'),
                data.get('description'), data.get('resolution'),
                data.get('due_date'), data.get('remark'), ticket_id
            ))
        db.commit()
        record_operation_log(username, '编辑', '工单', f'编辑工单：{data.get("title") or row["title"]}（ID:{ticket_id}）')
        return jsonify({'code': 200, 'message': '工单更新成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@tickets_bp.route('/api/tickets/<int:ticket_id>', methods=['DELETE'])
@token_required
def delete_ticket(ticket_id):
    """删除工单（级联删除消息和满意度）。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id, created_by, ticket_no, title FROM tickets WHERE id=?", (ticket_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '工单不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username and row['created_by'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    try:
        cursor.execute("DELETE FROM ticket_messages WHERE ticket_id=?", (ticket_id,))
        cursor.execute("DELETE FROM ticket_surveys WHERE ticket_id=?", (ticket_id,))
        cursor.execute("DELETE FROM tickets WHERE id=?", (ticket_id,))
        db.commit()
        record_operation_log(username, '删除', '工单', f'删除工单 {row["ticket_no"]}：{row["title"]}')
        return jsonify({'code': 200, 'message': '工单删除成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


# ==================== 工单状态流转 ====================

@tickets_bp.route('/api/tickets/<int:ticket_id>/status', methods=['POST'])
@token_required
def update_ticket_status(ticket_id):
    """更新工单状态：遵循状态机，支持设置解决方案（resolved时）。"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']
    role = payload['role']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id, created_by, ticket_no, title, status FROM tickets WHERE id=?", (ticket_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '工单不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username and row['created_by'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    new_status = (data.get('status') or '').lower()
    if new_status not in VALID_STATUSES:
        return jsonify({'code': 400, 'message': f'status 必须为 {VALID_STATUSES} 之一', 'data': None})

    old_status = row['status']
    # closed 不可再变更
    if old_status == 'closed':
        return jsonify({'code': 400, 'message': '工单已关闭，不可变更状态', 'data': None})

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    resolution = data.get('resolution')

    try:
        if new_status == 'resolved':
            # resolved 时写入 resolved_at 和 resolution
            cursor.execute("""
                UPDATE tickets SET status=?, resolved_at=COALESCE(?, resolved_at),
                    resolution=COALESCE(?, resolution), updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (new_status, now, resolution, ticket_id))
        elif new_status == 'closed':
            cursor.execute("""
                UPDATE tickets SET status=?, closed_at=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (new_status, now, ticket_id))
        else:
            cursor.execute("""
                UPDATE tickets SET status=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (new_status, ticket_id))

        # 状态变更自动追加一条内部消息记录
        action_msg = f'状态变更：{old_status} → {new_status}'
        if resolution:
            action_msg += f'，解决方案：{resolution}'
        cursor.execute("""
            INSERT INTO ticket_messages (ticket_id, sender_id, sender_name, sender_type,
                content, is_internal, created_at)
            VALUES (?, ?, ?, 'operator', ?, 1, CURRENT_TIMESTAMP)
        """, (ticket_id, username, payload.get('name') or username, action_msg))

        db.commit()
        record_operation_log(username, '状态变更', '工单',
            f'{row["ticket_no"]}：{old_status} → {new_status}')
        return jsonify({'code': 200, 'message': '状态更新成功', 'data': {'status': new_status}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


# ==================== 工单消息/处理记录 ====================

@tickets_bp.route('/api/tickets/<int:ticket_id>/messages', methods=['GET'])
@token_required
def get_ticket_messages(ticket_id):
    """获取工单消息记录。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id, created_by FROM tickets WHERE id=?", (ticket_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '工单不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username and row['created_by'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    # 管理层可见内部记录；普通用户仅可见非内部记录
    if role in ('主任', '院长') or row['owner_id'] == username or row['created_by'] == username:
        cursor.execute("""
            SELECT * FROM ticket_messages
            WHERE ticket_id = ?
            ORDER BY created_at ASC
        """, (ticket_id,))
    else:
        cursor.execute("""
            SELECT * FROM ticket_messages
            WHERE ticket_id = ? AND is_internal = 0
            ORDER BY created_at ASC
        """, (ticket_id,))

    rows = cursor.fetchall()
    return jsonify({'code': 200, 'message': 'success', 'data': [dict(r) for r in rows]})


@tickets_bp.route('/api/tickets/<int:ticket_id>/messages', methods=['POST'])
@token_required
def add_ticket_message(ticket_id):
    """添加工单回复消息。"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']
    role = payload['role']

    if not data.get('content'):
        return jsonify({'code': 400, 'message': '回复内容不能为空', 'data': None})

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id, created_by, ticket_no, status FROM tickets WHERE id=?", (ticket_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '工单不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username and row['created_by'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    is_internal = 1 if data.get('is_internal') else 0
    sender_type = data.get('sender_type') or 'operator'

    try:
        cursor.execute("""
            INSERT INTO ticket_messages (ticket_id, sender_id, sender_name, sender_type,
                content, is_internal, created_at, attachment)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
        """, (ticket_id, username, payload.get('name') or username,
              sender_type, data['content'], is_internal, data.get('attachment') or ''))

        # 有回复时若状态为 new/pending → 自动转为 processing
        if row['status'] in ('new', 'pending', 'reopened'):
            cursor.execute("UPDATE tickets SET status='processing', updated_at=CURRENT_TIMESTAMP WHERE id=?", (ticket_id,))
        else:
            cursor.execute("UPDATE tickets SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (ticket_id,))

        db.commit()
        record_operation_log(username, '回复', '工单', f'回复工单 {row["ticket_no"]}')
        return jsonify({'code': 200, 'message': '回复成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


# ==================== 满意度调查 ====================

@tickets_bp.route('/api/tickets/<int:ticket_id>/survey', methods=['POST'])
@token_required
def submit_survey(ticket_id):
    """提交满意度调查（工单 resolved 后）。"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']
    role = payload['role']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id, created_by, ticket_no, status FROM tickets WHERE id=?", (ticket_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '工单不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username and row['created_by'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    if row['status'] not in ('resolved', 'closed'):
        return jsonify({'code': 400, 'message': '工单未解决，暂不可提交满意度调查', 'data': None})

    # 校验各项评分 1-5 星
    for field in ('overall_score', 'response_speed', 'attitude_score', 'quality_score'):
        score = data.get(field)
        if score is not None:
            try:
                s = int(score)
                if s < 1 or s > 5:
                    return jsonify({'code': 400, 'message': f'{field} 评分范围 1-5 星', 'data': None})
            except (TypeError, ValueError):
                return jsonify({'code': 400, 'message': f'{field} 必须是整数', 'data': None})

    try:
        cursor.execute("""
            INSERT INTO ticket_surveys (ticket_id, overall_score, response_speed,
                attitude_score, quality_score, comment, suggestion, submitted_by, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(ticket_id) DO UPDATE SET
                overall_score=excluded.overall_score,
                response_speed=excluded.response_speed,
                attitude_score=excluded.attitude_score,
                quality_score=excluded.quality_score,
                comment=excluded.comment,
                suggestion=excluded.suggestion,
                submitted_by=excluded.submitted_by,
                submitted_at=CURRENT_TIMESTAMP
        """, (
            ticket_id,
            data.get('overall_score') or 0,
            data.get('response_speed') or 0,
            data.get('attitude_score') or 0,
            data.get('quality_score') or 0,
            data.get('comment') or '',
            data.get('suggestion') or '',
            username
        ))
        db.commit()
        record_operation_log(username, '提交', '满意度调查', f'工单 {row["ticket_no"]} 综合评分 {data.get("overall_score")}')
        return jsonify({'code': 200, 'message': '满意度调查提交成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@tickets_bp.route('/api/tickets/<int:ticket_id>/survey', methods=['GET'])
@token_required
def get_survey(ticket_id):
    """获取指定工单的满意度调查。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id, created_by FROM tickets WHERE id=?", (ticket_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '工单不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username and row['created_by'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    cursor.execute("SELECT * FROM ticket_surveys WHERE ticket_id=?", (ticket_id,))
    r = cursor.fetchone()
    return jsonify({'code': 200, 'message': 'success', 'data': dict(r) if r else None})


@tickets_bp.route('/api/tickets/surveys', methods=['GET'])
@token_required
def get_surveys_summary():
    """满意度调查汇总列表（分析视角）。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    owner_filter = ""
    params = []
    if role not in ('主任', '院长'):
        owner_filter = "AND (t.owner_id = ? OR t.created_by = ?)"
        params.extend([username, username])

    cursor.execute(f"""
        SELECT s.*, t.ticket_no, t.title, t.type, t.owner_id, u.name as owner_name
        FROM ticket_surveys s
        JOIN tickets t ON s.ticket_id = t.id
        LEFT JOIN users u ON t.owner_id = u.username
        WHERE 1=1 {owner_filter}
        ORDER BY s.submitted_at DESC
    """, params)

    rows = cursor.fetchall()
    surveys = [dict(r) for r in rows]

    # 汇总统计
    n = len(surveys)
    if n > 0:
        summary = {
            'count': n,
            'avg_overall': round(sum(s['overall_score'] for s in surveys if s['overall_score']) / n, 2),
            'avg_response': round(sum(s['response_speed'] for s in surveys if s['response_speed']) / n, 2),
            'avg_attitude': round(sum(s['attitude_score'] for s in surveys if s['attitude_score']) / n, 2),
            'avg_quality': round(sum(s['quality_score'] for s in surveys if s['quality_score']) / n, 2),
            'satisfaction_rate': round(sum(1 for s in surveys if s['overall_score'] and s['overall_score'] >= 4) / n * 100, 2)
        }
    else:
        summary = {'count': 0, 'avg_overall': 0, 'avg_response': 0, 'avg_attitude': 0, 'avg_quality': 0, 'satisfaction_rate': 0}

    return jsonify({'code': 200, 'message': 'success', 'data': {'surveys': surveys, 'summary': summary}})


# ==================== 服务统计 ====================

@tickets_bp.route('/api/tickets/statistics', methods=['GET'])
@token_required
def get_ticket_statistics():
    """服务统计：按状态/类型/优先级 聚合。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    owner_filter = ""
    params = []
    if role not in ('主任', '院长'):
        owner_filter = "WHERE (owner_id = ? OR created_by = ?)"
        params.extend([username, username])

    # 按状态统计
    cursor.execute(f"""
        SELECT status, COUNT(*) as cnt FROM tickets {owner_filter}
        GROUP BY status
    """, params)
    by_status = {r['status']: r['cnt'] for r in cursor.fetchall()}

    # 按类型统计
    cursor.execute(f"""
        SELECT type, COUNT(*) as cnt FROM tickets {owner_filter}
        GROUP BY type
    """, params)
    by_type = {r['type']: r['cnt'] for r in cursor.fetchall()}

    # 按优先级统计
    cursor.execute(f"""
        SELECT priority, COUNT(*) as cnt FROM tickets {owner_filter}
        GROUP BY priority
    """, params)
    by_priority = {r['priority']: r['cnt'] for r in cursor.fetchall()}

    # 总数 & 超时未解决（>7天未解决）
    owner_where2 = owner_filter.replace('WHERE', 'AND') if owner_filter else ''
    cursor.execute(f"""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN status NOT IN ('resolved','closed')
                    AND julianday('now') - julianday(created_at) > 7 THEN 1 ELSE 0 END) as overdue
        FROM tickets WHERE 1=1 {owner_where2}
    """, params)
    agg = cursor.fetchone()

    return jsonify({
        'code': 200, 'message': 'success',
        'data': {
            'total': agg['total'] or 0,
            'overdue': agg['overdue'] or 0,
            'by_status': by_status,
            'by_type': by_type,
            'by_priority': by_priority
        }
    })


def register_routes(app):
    app.register_blueprint(tickets_bp)
