from flask import request, jsonify, Response
from datetime import datetime, timedelta
import json

from extensions import (
    get_db, token_required, admin_required,
    record_operation_log, update_customer_last_follow,
)

from . import misc_bp


@misc_bp.route('/api/business_stage_logs', methods=['GET'])
@token_required
def get_stage_logs():
    business_id = request.args.get('business_id')

    db = get_db()
    cursor = db.cursor()

    if business_id:
        cursor.execute("SELECT * FROM business_stage_logs WHERE business_id = ? ORDER BY changed_at DESC", (business_id,))
    else:
        cursor.execute("SELECT * FROM business_stage_logs ORDER BY changed_at DESC")

    rows = cursor.fetchall()
    logs = []
    for row in rows:
        logs.append(dict(row))

    return jsonify({'code': 200, 'message': 'success', 'data': logs})


@misc_bp.route('/api/follow_logs', methods=['GET'])
@token_required
def get_follow_logs():
    ref_type = request.args.get('ref_type')
    ref_id = request.args.get('ref_id')
    keyword = request.args.get('keyword')

    db = get_db()
    cursor = db.cursor()

    conditions = []
    params = []

    if ref_type:
        conditions.append("fl.ref_type = ?")
        params.append(ref_type)

    if ref_id:
        conditions.append("fl.ref_id = ?")
        params.append(ref_id)

    if keyword:
        conditions.append("(fl.content LIKE ? OR fl.subject LIKE ? OR fl.participants LIKE ? OR u.name LIKE ?)")
        keyword_pattern = f'%{keyword}%'
        params.extend([keyword_pattern, keyword_pattern, keyword_pattern, keyword_pattern])

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    query = f"""
        SELECT fl.*, u.name as user_name
        FROM follow_logs fl
        LEFT JOIN users u ON fl.user_id = u.username
        {where_clause}
        ORDER BY fl.created_at DESC
    """

    cursor.execute(query, params)

    rows = cursor.fetchall()
    logs = []
    for row in rows:
        logs.append(dict(row))

    return jsonify({'code': 200, 'message': 'success', 'data': logs})


@misc_bp.route('/api/follow_logs', methods=['POST'])
@token_required
def create_follow_log():
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("""
            INSERT INTO follow_logs
            (ref_type, ref_id, user_id, content, log_time, subject, participants, location, next_plan)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get('ref_type'), data.get('ref_id'), username,
            data.get('content'), data.get('log_time'), data.get('subject'),
            data.get('participants'), data.get('location'), data.get('next_plan')
        ))
        db.commit()

        ref_type = data.get('ref_type')
        ref_id = data.get('ref_id')
        if ref_type == 'customer' and ref_id:
            update_customer_last_follow(ref_id)

        return jsonify({'code': 200, 'message': '跟进记录添加成功', 'data': {'id': cursor.lastrowid}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@misc_bp.route('/api/follow_logs/<int:log_id>', methods=['DELETE'])
@token_required
def delete_follow_log(log_id):
    payload = request.current_user
    role = payload.get('role', '')
    username = payload.get('username', '')

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT user_id FROM follow_logs WHERE id = ?", (log_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '跟进记录不存在', 'data': None})

    if role not in ('主任', '院长') and row['user_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足，只能删除自己的跟进记录', 'data': None})

    try:
        cursor.execute("DELETE FROM follow_logs WHERE id = ?", (log_id,))
        db.commit()

        return jsonify({'code': 200, 'message': '跟进记录删除成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@misc_bp.route('/api/pool', methods=['GET'])
@token_required
def get_pool():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT c.*, u.name as previous_owner_name
        FROM customers c
        LEFT JOIN users u ON c.previous_owner = u.username
        WHERE c.owner_id IS NULL OR c.owner_id = ''
        ORDER BY c.created_at DESC
    """)
    rows = cursor.fetchall()
    pool_data = []
    today = datetime.now().date()
    for row in rows:
        item = dict(row)
        item['quality_score'] = 65 + (item.get('id', 0) % 35)

        last_follow = item.get('last_follow')
        if last_follow:
            try:
                follow_date = datetime.strptime(str(last_follow), '%Y-%m-%d').date()
                days_unfollowed = (today - follow_date).days
            except:
                days_unfollowed = 0
        else:
            created_at = item.get('created_at')
            if created_at:
                try:
                    create_date = datetime.strptime(str(created_at), '%Y-%m-%d').date()
                    days_unfollowed = (today - create_date).days
                except:
                    days_unfollowed = 0
            else:
                days_unfollowed = 0
        item['days_unfollowed'] = days_unfollowed

        pool_data.append(item)

    return jsonify({'code': 200, 'message': 'success', 'data': pool_data})


@misc_bp.route('/api/pool/claim', methods=['POST'])
@token_required
def claim_pool():
    payload = request.current_user
    data = request.get_json()
    customer_ids = data.get('customer_ids', [])

    if not customer_ids:
        return jsonify({'code': 400, 'message': '请选择要认领的客户', 'data': None})

    db = get_db()
    cursor = db.cursor()

    username = payload.get('username', '')

    try:
        placeholders = ','.join('?' * len(customer_ids))
        cursor.execute(f"""
            UPDATE customers
            SET owner_id = ?, last_follow = ?
            WHERE id IN ({placeholders}) AND (owner_id IS NULL OR owner_id = '')
        """, (username, datetime.now().strftime('%Y-%m-%d'), *customer_ids))

        db.commit()
        record_operation_log(username, '认领', '公海池', f'认领客户，数量:{cursor.rowcount}，ID:{customer_ids}')
        return jsonify({'code': 200, 'message': f'成功认领 {cursor.rowcount} 条线索', 'data': {'claimed_count': cursor.rowcount}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': f'认领失败: {str(e)}', 'data': None})


@misc_bp.route('/api/pool/release', methods=['POST'])
@token_required
def release_pool():
    payload = request.current_user
    current_role = payload.get('role', '')
    if current_role != '主任' and current_role != '院长':
        return jsonify({'code': 403, 'message': '无权操作', 'data': None})

    data = request.get_json()
    customer_ids = data.get('customer_ids', [])

    if not customer_ids:
        return jsonify({'code': 400, 'message': '请选择要释放的客户', 'data': None})

    db = get_db()
    cursor = db.cursor()

    try:
        placeholders = ','.join('?' * len(customer_ids))
        cursor.execute(f"""
            UPDATE customers
            SET previous_owner = owner_id, owner_id = '', last_follow = NULL
            WHERE id IN ({placeholders}) AND owner_id IS NOT NULL AND owner_id != ''
        """, (*customer_ids,))

        db.commit()
        record_operation_log(payload['username'], '释放', '公海池', f'释放客户到公海池，数量:{cursor.rowcount}，ID:{customer_ids}')
        return jsonify({'code': 200, 'message': f'成功释放 {cursor.rowcount} 条客户到公海池', 'data': {'released_count': cursor.rowcount}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': f'释放失败: {str(e)}', 'data': None})


@misc_bp.route('/api/workhours', methods=['GET'])
@token_required
def get_workhours():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT wh.*, b.title as project_name, u.name as user_name
        FROM work_hours wh
        LEFT JOIN business b ON wh.business_id = b.id
        LEFT JOIN users u ON wh.user_id = u.username
        ORDER BY wh.work_date DESC
    """)
    rows = cursor.fetchall()
    workhours = []
    for row in rows:
        item = dict(row)
        item['date'] = item.pop('work_date')
        item['task_name'] = item.get('description', '')[:20]
        workhours.append(item)

    return jsonify({'code': 200, 'message': 'success', 'data': workhours})


@misc_bp.route('/api/projects', methods=['GET'])
@token_required
def get_projects():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT b.id, b.title as project_name, c.name as customer_name,
               b.created_at as start_date, b.predict_date as end_date,
               b.stage, b.status, b.project_manager as manager,
               b.owner_id, u.name as owner_name,
               b.amount, b.probability
        FROM business b
        LEFT JOIN customers c ON b.cust_id = c.id
        LEFT JOIN users u ON b.owner_id = u.username
        WHERE b.status = 'active'
        ORDER BY b.created_at DESC
    """)
    rows = cursor.fetchall()
    projects = []
    for row in rows:
        item = dict(row)
        stage_progress = {
            '需求确认': 20, '方案报价': 40, '商务谈判': 60,
            '合同签署': 80, '项目启动': 90, '实施中': 95, '已完成': 100
        }
        item['progress'] = stage_progress.get(item.get('stage'), 30)
        status_map = {'active': '进行中'}
        item['status'] = status_map.get(item.get('status'), item.get('status', '进行中'))

        cursor.execute("""
            SELECT u.name FROM project_assignments pa
            LEFT JOIN users u ON pa.user_id = u.username
            WHERE pa.project_type = 'business' AND pa.project_id = ?
        """, (item['id'],))
        members = cursor.fetchall()
        item['team_members'] = [m[0] for m in members]
        if not item['team_members'] and item['manager']:
            item['team_members'] = [item['manager']]

        projects.append(item)

    return jsonify({'code': 200, 'message': 'success', 'data': projects})


@misc_bp.route('/api/search', methods=['GET'])
@token_required
def search():
    payload = request.current_user
    username = payload['username']
    role = payload['role']
    keyword = request.args.get('keyword', '')

    db = get_db()
    cursor = db.cursor()
    kw = f'%{keyword}%'

    if role in ('主任', '院长'):
        cursor.execute("SELECT id, name, company, phone, level, source FROM customers WHERE name LIKE ? OR company LIKE ?", (kw, kw))
    else:
        cursor.execute("SELECT id, name, company, phone, level, source FROM customers WHERE (owner_id = ?) AND (name LIKE ? OR company LIKE ?)", (username, kw, kw))
    customers = [dict(row) for row in cursor.fetchall()]

    if role in ('主任', '院长'):
        cursor.execute("SELECT id, title, amount, stage, probability, owner_id FROM business WHERE title LIKE ? OR stage LIKE ?", (kw, kw))
    else:
        cursor.execute("SELECT id, title, amount, stage, probability, owner_id FROM business WHERE owner_id = ? AND (title LIKE ? OR stage LIKE ?)", (username, kw, kw))
    business = [dict(row) for row in cursor.fetchall()]

    if role in ('主任', '院长'):
        cursor.execute("SELECT id, contract_name, contract_no, total_amt, sign_date FROM contracts WHERE contract_name LIKE ? OR contract_no LIKE ?", (kw, kw))
    else:
        cursor.execute("SELECT id, contract_name, contract_no, total_amt, sign_date FROM contracts WHERE owner_id = ? AND (contract_name LIKE ? OR contract_no LIKE ?)", (username, kw, kw))
    contracts = [dict(row) for row in cursor.fetchall()]

    if role in ('主任', '院长'):
        cursor.execute("""
            SELECT fl.id, fl.ref_type, fl.ref_id, fl.content, fl.subject, fl.created_at, u.name as user_name
            FROM follow_logs fl
            LEFT JOIN users u ON fl.user_id = u.username
            WHERE fl.content LIKE ? OR fl.subject LIKE ? OR fl.participants LIKE ?
        """, (kw, kw, kw))
    else:
        cursor.execute("""
            SELECT fl.id, fl.ref_type, fl.ref_id, fl.content, fl.subject, fl.created_at, u.name as user_name
            FROM follow_logs fl
            LEFT JOIN users u ON fl.user_id = u.username
            WHERE fl.user_id = ? AND (fl.content LIKE ? OR fl.subject LIKE ? OR fl.participants LIKE ?)
        """, (username, kw, kw, kw))
    follow_logs = [dict(row) for row in cursor.fetchall()]

    return jsonify({'code': 200, 'message': 'success', 'data': {
        'customers': customers,
        'business': business,
        'contracts': contracts,
        'follow_logs': follow_logs
    }})


@misc_bp.route('/api/qa', methods=['POST'])
@token_required
def qa():
    payload = request.current_user
    data = request.get_json()
    question = data.get('question', '')
    stream = data.get('stream', False)

    db = get_db()
    cursor = db.cursor()
    username = payload.get('username', '')

    answer = process_question_llm(question, cursor, username, stream)
    if stream:
        return answer
    if answer:
        return jsonify({'code': 200, 'message': 'success', 'data': {'answer': answer}})

    answer = process_question_rule(question, cursor, payload)
    return jsonify({'code': 200, 'message': 'success', 'data': {'answer': answer}})


def process_question_llm_stream(question, cursor, username):
    """流式问答生成器：先查数据，再生成回答，全程有进度反馈。

    作为 generator，每条 yield 直接是一条 SSE 事件字符串。
    进度消息带 type: status，实际回答内容不带 type。
    """
    from qa_engine import _extract_query_function_rule, generate_answer_stream, generate_answer

    # 1. 快速函数选择（规则匹配，毫秒级）
    func_name = _extract_query_function_rule(question)

    if not func_name or func_name == 'none':
        # 规则匹配没命中，尝试 LLM 选择（可能较慢）
        yield f"data: {json.dumps({'answer': '正在分析意图...', 'type': 'status'}, ensure_ascii=False)}\n\n"
        from qa_engine import extract_query_function
        func_name = extract_query_function(question)
        if not func_name or func_name == 'none':
            answer = get_default_answer(question)
            yield f"data: {json.dumps({'answer': answer}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return

    # 2. 查询数据
    func_map = {
        'get_contracts_near_expiry': lambda: get_contracts_near_expiry_raw(cursor),
        'get_top_pending_customer': lambda: get_top_pending_customer_raw(cursor),
        'get_top_pending_contract': lambda: get_top_pending_contract_raw(cursor),
        'get_business_to_follow': lambda: get_business_to_follow_raw(cursor),
        'get_my_customer_count': lambda: get_my_customer_count_raw(cursor, username),
        'get_top_contract_by_amount': lambda: get_top_contract_by_amount_raw(cursor),
        'get_business_count': lambda: get_business_count_raw(cursor),
        'get_total_payments': lambda: get_total_payments_raw(cursor),
        'get_total_pending': lambda: get_total_pending_raw(cursor),
        'get_weekly_plan': lambda: get_weekly_plan_raw(cursor, username),
        'get_next_week_plan': lambda: get_next_week_plan_raw(cursor, username),
    }

    if func_name not in func_map:
        answer = get_default_answer(question)
        yield f"data: {json.dumps({'answer': answer}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        return

    yield f"data: {json.dumps({'answer': '正在查询数据...', 'type': 'status'}, ensure_ascii=False)}\n\n"
    data_context = func_map[func_name]()

    # 3. 尝试 LLM 流式生成回答
    yield f"data: {json.dumps({'answer': '正在生成回答...', 'type': 'status'}, ensure_ascii=False)}\n\n"
    lines = generate_answer_stream(question, data_context, username)

    if lines:
        received_content = False
        for line in lines:
            if line:
                line = line.decode('utf-8')
                if line.startswith('data:'):
                    try:
                        data = json.loads(line[5:])
                        if 'choices' in data and data['choices']:
                            delta = data['choices'][0].get('delta', {})
                            content = delta.get('content', '')
                            if content:
                                received_content = True
                                yield f"data: {json.dumps({'answer': content}, ensure_ascii=False)}\n\n"
                    except Exception:
                        pass
        if received_content:
            yield "data: [DONE]\n\n"
            return

    # LLM 流式生成失败，尝试非流式
    answer = generate_answer(question, data_context, username)
    if answer:
        yield f"data: {json.dumps({'answer': answer}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        return

    # LLM 完全失败，直接展示数据
    if data_context and not data_context.startswith('暂无'):
        fallback_answer = f'查询到以下数据：\n\n{data_context}'
        yield f"data: {json.dumps({'answer': fallback_answer}, ensure_ascii=False)}\n\n"
    else:
        yield f"data: {json.dumps({'answer': '抱歉，未能查询到相关数据。'}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


def _answer_with_data_context(question, data_context, stream=False):
    """当 LLM 生成失败时，直接用查询到的数据生成简单回答。"""
    if not data_context or data_context.strip() in ['', '暂无数据。', '暂无即将到期的合同。', '暂无待回款的客户。', '暂无待回款的合同。']:
        answer = '抱歉，未能查询到相关数据。您可以尝试换一种提问方式。'
    else:
        answer = f"根据查询结果：\n\n{data_context}"
    
    if stream:
        def generate():
            yield f"data: {json.dumps({'answer': answer})}\n\n"
            yield "data: [DONE]\n\n"
        return Response(generate(), content_type='text/event-stream')
    return answer


def process_question_rule(question, cursor, payload):
    question = question.lower().strip()
    username = payload.get('username', '')

    if '合同' in question and ('到期' in question or '即将到期' in question):
        return get_contracts_near_expiry(cursor)

    if '回款' in question and ('最高' in question or '最多' in question or '金额' in question):
        if '客户' in question:
            return get_top_pending_customer(cursor)
        return get_top_pending_contract(cursor)

    if '商机' in question and ('跟进' in question or '需要' in question):
        return get_business_to_follow(cursor)

    if '客户' in question and ('多少' in question or '数量' in question):
        return get_my_customer_count(cursor, username)

    if '合同' in question and ('总额' in question or '最高' in question):
        return get_top_contract_by_amount(cursor)

    if '商机' in question and ('多少' in question or '数量' in question):
        return get_business_count(cursor)

    if '回款' in question and ('总额' in question or '合计' in question):
        return get_total_payments(cursor)

    if '待回款' in question and ('总额' in question or '合计' in question):
        return get_total_pending(cursor)

    if '本周' in question and ('工作' in question or '计划' in question):
        return get_weekly_plan(cursor, username)

    if '下周' in question and ('工作' in question or '计划' in question):
        return get_next_week_plan(cursor, username)

    return get_default_answer(question)


def get_contracts_near_expiry(cursor):
    cursor.execute("""
        SELECT contract_name, expected_income_date, total_amt, (total_amt - paid_amt) as pending_amt
        FROM contracts
        WHERE status='执行中' AND expected_income_date IS NOT NULL AND expected_income_date != ''
        ORDER BY expected_income_date ASC LIMIT 5
    """)
    rows = cursor.fetchall()

    if not rows:
        return '暂无即将到期的合同。'

    result = '<strong>即将到期的合同：</strong><br><br>'
    for row in rows:
        result += f"• <strong>{row['contract_name']}</strong><br>"
        result += f"  预计回款日期：{row['expected_income_date']}<br>"
        result += f"  合同总额：{row['total_amt']/10000:.2f}万元，待回款：{row['pending_amt']/10000:.2f}万元<br><br>"

    return result


def get_top_pending_customer(cursor):
    cursor.execute("""
        SELECT c.company, SUM(ct.total_amt - ct.paid_amt) as total_pending
        FROM contracts ct
        JOIN customers c ON ct.party_a = c.company
        WHERE ct.status='执行中' AND (ct.total_amt - ct.paid_amt) > 0
        GROUP BY c.company
        ORDER BY total_pending DESC LIMIT 5
    """)
    rows = cursor.fetchall()

    if not rows:
        return '暂无待回款的客户。'

    result = '<strong>待回款金额最高的客户：</strong><br><br>'
    for i, row in enumerate(rows, 1):
        result += f"{i}. <strong>{row['company']}</strong>：待回款 {row['total_pending']/10000:.2f} 万元<br>"

    return result


def get_top_pending_contract(cursor):
    cursor.execute("""
        SELECT contract_name, party_a, (total_amt - paid_amt) as pending_amt, total_amt
        FROM contracts
        WHERE status='执行中' AND (total_amt - paid_amt) > 0
        ORDER BY pending_amt DESC LIMIT 5
    """)
    rows = cursor.fetchall()

    if not rows:
        return '暂无待回款的合同。'

    result = '<strong>待回款金额最高的合同：</strong><br><br>'
    for i, row in enumerate(rows, 1):
        result += f"{i}. <strong>{row['contract_name']}</strong><br>"
        result += f"  甲方：{row['party_a']}<br>"
        result += f"  待回款：{row['pending_amt']/10000:.2f} 万元（总额：{row['total_amt']/10000:.2f} 万元）<br><br>"

    return result


def get_business_to_follow(cursor):
    cursor.execute("""
        SELECT b.title, c.company, b.stage, b.next_week_plan, b.owner_id, u.name as owner_name
        FROM business b
        LEFT JOIN customers c ON b.cust_id = c.id
        LEFT JOIN users u ON b.owner_id = u.username
        WHERE b.status='active' AND (b.next_week_plan IS NOT NULL AND b.next_week_plan != '')
        ORDER BY b.id DESC LIMIT 5
    """)
    rows = cursor.fetchall()

    if not rows:
        return '暂无需要跟进的商机。'

    result = '<strong>需要跟进的商机：</strong><br><br>'
    for row in rows:
        result += f"• <strong>{row['title']}</strong><br>"
        result += f"  客户：{row['company'] or '未知'}<br>"
        result += f"  阶段：{row['stage']}<br>"
        result += f"  负责人：{row['owner_name'] or row['owner_id']}<br>"
        result += f"  下周计划：{row['next_week_plan']}<br><br>"

    return result


def get_my_customer_count(cursor, username):
    cursor.execute("""
        SELECT COUNT(*) as cnt FROM customers WHERE owner_id = ?
    """, (username,))
    row = cursor.fetchone()

    return f"您负责的客户数量为：<strong>{row['cnt']}</strong> 个。"


def get_top_contract_by_amount(cursor):
    cursor.execute("""
        SELECT contract_name, party_a, total_amt, sign_date
        FROM contracts
        ORDER BY total_amt DESC LIMIT 1
    """)
    row = cursor.fetchone()

    if not row:
        return '暂无合同数据。'

    return f"合同总额最高的项目是：<strong>{row['contract_name']}</strong><br>" \
           f"甲方：{row['party_a']}<br>" \
           f"合同金额：<strong>{row['total_amt']/10000:.2f} 万元</strong><br>" \
           f"签约日期：{row['sign_date']}"


def get_business_count(cursor):
    cursor.execute("SELECT COUNT(*) as cnt FROM business WHERE status='active'")
    active = cursor.fetchone()['cnt']

    cursor.execute("SELECT COUNT(*) as cnt FROM business WHERE status='void'")
    void = cursor.fetchone()['cnt']

    return f"当前商机总数：<strong>{active + void}</strong> 个，其中正常状态 <strong>{active}</strong> 个，已作废 <strong>{void}</strong> 个。"


def get_total_payments(cursor):
    cursor.execute("SELECT SUM(amount) as total FROM payment_records")
    total = cursor.fetchone()['total'] or 0

    return f"累计回款总额：<strong>{total/10000:.2f} 万元</strong>。"


def get_total_pending(cursor):
    cursor.execute("SELECT SUM(total_amt - paid_amt) as total FROM contracts WHERE status='执行中'")
    total = cursor.fetchone()['total'] or 0

    return f"所有执行中合同的待回款总额：<strong>{total/10000:.2f} 万元</strong>。"


def get_weekly_plan(cursor, username):
    cursor.execute("""
        SELECT b.title, b.weekly_plan
        FROM business b
        WHERE b.owner_id = ? AND b.status='active' AND b.weekly_plan IS NOT NULL AND b.weekly_plan != ''
    """, (username,))
    rows = cursor.fetchall()

    if not rows:
        return '您负责的商机暂无本周工作安排。'

    result = '<strong>您的本周工作安排：</strong><br><br>'
    for row in rows:
        result += f"• <strong>{row['title']}</strong><br>"
        result += f"  {row['weekly_plan']}<br><br>"

    return result


def get_next_week_plan(cursor, username):
    cursor.execute("""
        SELECT b.title, b.next_week_plan
        FROM business b
        WHERE b.owner_id = ? AND b.status='active' AND b.next_week_plan IS NOT NULL AND b.next_week_plan != ''
    """, (username,))
    rows = cursor.fetchall()

    if not rows:
        return '您负责的商机暂无下周工作计划。'

    result = '<strong>您的下周工作计划：</strong><br><br>'
    for row in rows:
        result += f"• <strong>{row['title']}</strong><br>"
        result += f"  {row['next_week_plan']}<br><br>"

    return result


def get_contracts_near_expiry_raw(cursor):
    cursor.execute("""
        SELECT contract_name, expected_income_date, total_amt, (total_amt - paid_amt) as pending_amt
        FROM contracts
        WHERE status='执行中' AND expected_income_date IS NOT NULL AND expected_income_date != ''
        ORDER BY expected_income_date ASC LIMIT 5
    """)
    rows = cursor.fetchall()
    return json.dumps([dict(row) for row in rows], ensure_ascii=False)


def get_top_pending_customer_raw(cursor):
    cursor.execute("""
        SELECT c.company, SUM(ct.total_amt - ct.paid_amt) as total_pending
        FROM contracts ct
        JOIN customers c ON ct.party_a = c.company
        WHERE ct.status='执行中' AND (ct.total_amt - ct.paid_amt) > 0
        GROUP BY c.company
        ORDER BY total_pending DESC LIMIT 5
    """)
    rows = cursor.fetchall()
    return json.dumps([dict(row) for row in rows], ensure_ascii=False)


def get_top_pending_contract_raw(cursor):
    cursor.execute("""
        SELECT contract_name, party_a, (total_amt - paid_amt) as pending_amt, total_amt
        FROM contracts
        WHERE status='执行中' AND (total_amt - paid_amt) > 0
        ORDER BY pending_amt DESC LIMIT 5
    """)
    rows = cursor.fetchall()
    return json.dumps([dict(row) for row in rows], ensure_ascii=False)


def get_business_to_follow_raw(cursor):
    cursor.execute("""
        SELECT b.title, c.company, b.stage, b.next_week_plan, b.owner_id, u.name as owner_name
        FROM business b
        LEFT JOIN customers c ON b.cust_id = c.id
        LEFT JOIN users u ON b.owner_id = u.username
        WHERE b.status='active' AND (b.next_week_plan IS NOT NULL AND b.next_week_plan != '')
        ORDER BY b.id DESC LIMIT 5
    """)
    rows = cursor.fetchall()
    return json.dumps([dict(row) for row in rows], ensure_ascii=False)


def get_my_customer_count_raw(cursor, username):
    cursor.execute("SELECT COUNT(*) as cnt FROM customers WHERE owner_id = ?", (username,))
    row = cursor.fetchone()
    return json.dumps({'count': row['cnt']}, ensure_ascii=False)


def get_top_contract_by_amount_raw(cursor):
    cursor.execute("""
        SELECT contract_name, party_a, total_amt, sign_date
        FROM contracts
        ORDER BY total_amt DESC LIMIT 1
    """)
    row = cursor.fetchone()
    if row:
        return json.dumps(dict(row), ensure_ascii=False)
    return json.dumps({}, ensure_ascii=False)


def get_business_count_raw(cursor):
    cursor.execute("SELECT COUNT(*) as cnt FROM business WHERE status='active'")
    active = cursor.fetchone()['cnt']
    cursor.execute("SELECT COUNT(*) as cnt FROM business WHERE status='void'")
    void = cursor.fetchone()['cnt']
    return json.dumps({'active': active, 'void': void, 'total': active + void}, ensure_ascii=False)


def get_total_payments_raw(cursor):
    cursor.execute("SELECT SUM(amount) as total FROM payment_records")
    total = cursor.fetchone()['total'] or 0
    return json.dumps({'total': total}, ensure_ascii=False)


def get_total_pending_raw(cursor):
    cursor.execute("SELECT SUM(total_amt - paid_amt) as total FROM contracts WHERE status='执行中'")
    total = cursor.fetchone()['total'] or 0
    return json.dumps({'total': total}, ensure_ascii=False)


def get_weekly_plan_raw(cursor, username):
    cursor.execute("""
        SELECT b.title, b.weekly_plan
        FROM business b
        WHERE b.owner_id = ? AND b.status='active' AND b.weekly_plan IS NOT NULL AND b.weekly_plan != ''
    """, (username,))
    rows = cursor.fetchall()
    return json.dumps([dict(row) for row in rows], ensure_ascii=False)


def get_next_week_plan_raw(cursor, username):
    cursor.execute("""
        SELECT b.title, b.next_week_plan
        FROM business b
        WHERE b.owner_id = ? AND b.status='active' AND b.next_week_plan IS NOT NULL AND b.next_week_plan != ''
    """, (username,))
    rows = cursor.fetchall()
    return json.dumps([dict(row) for row in rows], ensure_ascii=False)


def get_default_answer(question):
    help_text = """
我可以帮您查询以下信息：

<strong>合同相关：</strong>
• 本月有哪些合同即将到期？
• 合同总额最高的项目是哪个？

<strong>客户相关：</strong>
• 我负责的客户有多少个？
• 待回款金额最高的客户是谁？

<strong>商机相关：</strong>
• 最近一周有哪些商机需要跟进？
• 当前有多少个商机？

<strong>回款相关：</strong>
• 待回款金额最高的合同是哪个？
• 累计回款总额是多少？

<strong>工作计划：</strong>
• 我的本周工作安排
• 我的下周工作计划

请用自然语言提问，例如："待回款金额最高的客户是谁？"
"""
    return help_text


def register_routes(app):
    app.register_blueprint(misc_bp)
