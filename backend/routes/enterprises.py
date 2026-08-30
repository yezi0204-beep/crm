from flask import request, jsonify
from extensions import get_db, record_operation_log, token_required, user_can
from datetime import datetime

from . import enterprises_bp


@enterprises_bp.route('/api/enterprises', methods=['GET'])
@token_required
def get_enterprises():
    """获取企业信息库列表。"""
    payload = request.current_user
    role = payload['role']

    keyword = request.args.get('keyword', '')
    relationship_status = request.args.get('relationship_status', '')
    owner_id = request.args.get('owner_id', '')

    db = get_db()
    cursor = db.cursor()

    conditions = []
    params = []

    if not user_can(payload['username'], 'data.view_all'):
        conditions.append("e.owner_id = ?")
        params.append(payload['username'])

    if keyword:
        conditions.append("(e.name LIKE ? OR e.contact_person LIKE ? OR e.brief LIKE ?)")
        params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])
    if relationship_status:
        conditions.append("e.relationship_status = ?")
        params.append(relationship_status)
    if owner_id:
        conditions.append("e.owner_id = ?")
        params.append(owner_id)

    where_clause = ' AND '.join(conditions) if conditions else '1=1'

    cursor.execute(f"""
        SELECT e.*, u.name as owner_name,
               (SELECT COUNT(*) FROM enterprise_visits ev WHERE ev.enterprise_id = e.id) as visit_count,
               (SELECT COUNT(*) FROM customers c WHERE c.company LIKE '%' || e.name || '%' OR c.company = e.name) as customer_count,
               (SELECT COUNT(*) FROM business b
                WHERE b.cust_id IN (SELECT c.id FROM customers c WHERE c.company LIKE '%' || e.name || '%' OR c.company = e.name)) as business_count,
               (SELECT COUNT(*) FROM contracts ct
                WHERE ct.cust_id IN (SELECT c.id FROM customers c WHERE c.company LIKE '%' || e.name || '%' OR c.company = e.name)) as contract_count
        FROM enterprises e
        LEFT JOIN users u ON e.owner_id = u.username
        WHERE {where_clause}
        ORDER BY e.updated_at DESC
    """, params)

    rows = cursor.fetchall()
    enterprises = [dict(row) for row in rows]

    return jsonify({'code': 200, 'message': 'success', 'data': enterprises})


@enterprises_bp.route('/api/enterprises/<int:enterprise_id>', methods=['GET'])
@token_required
def get_enterprise(enterprise_id):
    """获取单个企业详情，自动关联客户、商机、合同、拜访数据，打通数据链条。"""
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT e.*, u.name as owner_name
        FROM enterprises e
        LEFT JOIN users u ON e.owner_id = u.username
        WHERE e.id = ?
    """, (enterprise_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '企业不存在', 'data': None})

    enterprise = dict(row)
    ent_name = enterprise.get('name', '')

    # --- 1. 自动匹配客户：按企业名称匹配 customers.company ---
    matched_cust_ids = []
    if ent_name:
        cursor.execute("""
            SELECT id, name, company, phone, level, owner_id, last_follow, created_at
            FROM customers
            WHERE company LIKE ? OR company = ?
            ORDER BY last_follow DESC
        """, (f'%{ent_name}%', ent_name))
        customers = [dict(r) for r in cursor.fetchall()]
        enterprise['customers'] = customers
        matched_cust_ids = [c['id'] for c in customers]
    else:
        enterprise['customers'] = []

    # --- 2. 关联商机：通过匹配到的客户的 cust_id 查询 business ---
    if matched_cust_ids:
        placeholders = ','.join(['?'] * len(matched_cust_ids))
        cursor.execute(f"""
            SELECT b.*, c.company as customer_company, c.name as customer_name
            FROM business b
            LEFT JOIN customers c ON b.cust_id = c.id
            WHERE b.cust_id IN ({placeholders})
            ORDER BY b.created_at DESC
        """, matched_cust_ids)
        enterprise['business'] = [dict(r) for r in cursor.fetchall()]
    else:
        enterprise['business'] = []

    # --- 3. 关联合同：通过匹配到的客户的 cust_id 查询 contracts ---
    if matched_cust_ids:
        placeholders = ','.join(['?'] * len(matched_cust_ids))
        cursor.execute(f"""
            SELECT ct.*, c.company as customer_company
            FROM contracts ct
            LEFT JOIN customers c ON ct.cust_id = c.id
            WHERE ct.cust_id IN ({placeholders})
            ORDER BY ct.sign_date DESC
        """, matched_cust_ids)
        enterprise['contracts'] = [dict(r) for r in cursor.fetchall()]
    else:
        enterprise['contracts'] = []

    # --- 4. 关联拜访记录：手动关联(enterprise_visits) + 匹配客户的拜访记录 ---
    visit_ids_set = set()

    # 4a. enterprise_visits 关联表中的拜访
    cursor.execute("""
        SELECT v.*, u.name as visitor_name,
               c.company as customer_company
        FROM enterprise_visits ev
        JOIN visits v ON ev.visit_id = v.id
        LEFT JOIN users u ON v.visitor_id = u.username
        LEFT JOIN customers c ON v.cust_id = c.id
        WHERE ev.enterprise_id = ?
        ORDER BY v.plan_date DESC, v.plan_time DESC
    """, (enterprise_id,))
    manual_visits = [dict(r) for r in cursor.fetchall()]
    visit_ids_set.update(v['id'] for v in manual_visits)

    # 4b. 匹配客户的拜访记录（去重）
    auto_visits = []
    if matched_cust_ids:
        placeholders = ','.join(['?'] * len(matched_cust_ids))
        cursor.execute(f"""
            SELECT v.*, u.name as visitor_name,
                   c.company as customer_company
            FROM visits v
            LEFT JOIN users u ON v.visitor_id = u.username
            LEFT JOIN customers c ON v.cust_id = c.id
            WHERE v.cust_id IN ({placeholders})
            ORDER BY v.plan_date DESC, v.plan_time DESC
        """, matched_cust_ids)
        for r in cursor.fetchall():
            v = dict(r)
            if v['id'] not in visit_ids_set:
                auto_visits.append(v)
                visit_ids_set.add(v['id'])

    # 合并：手动关联标记 link_type='manual'，自动匹配标记 link_type='auto'
    for v in manual_visits:
        v['link_type'] = 'manual'
    for v in auto_visits:
        v['link_type'] = 'auto'
    enterprise['visits'] = manual_visits + auto_visits

    # 统计摘要
    enterprise['summary'] = {
        'customer_count': len(enterprise['customers']),
        'business_count': len(enterprise['business']),
        'contract_count': len(enterprise['contracts']),
        'visit_count': len(enterprise['visits']),
        'business_total_amount': sum(b.get('amount', 0) or 0 for b in enterprise['business']),
        'contract_total_amount': sum(c.get('total_amt', 0) or 0 for c in enterprise['contracts']),
        'contract_paid_amount': sum(c.get('paid_amt', 0) or 0 for c in enterprise['contracts']),
    }

    return jsonify({'code': 200, 'message': 'success', 'data': enterprise})


@enterprises_bp.route('/api/enterprises', methods=['POST'])
@token_required
def create_enterprise():
    """新建企业信息。"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}

    if not data.get('name'):
        return jsonify({'code': 400, 'message': '企业名称不能为空', 'data': None})

    db = get_db()
    cursor = db.cursor()

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
        INSERT INTO enterprises (name, established_date, location, personnel_size, brief,
            registered_capital, business_scope, main_qualifications, main_products,
            relationship_status, cooperation_opportunities, website, contact_person,
            contact_info, owner_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get('name', ''),
        data.get('established_date', ''),
        data.get('location', ''),
        data.get('personnel_size', ''),
        data.get('brief', ''),
        data.get('registered_capital', ''),
        data.get('business_scope', ''),
        data.get('main_qualifications', ''),
        data.get('main_products', ''),
        data.get('relationship_status', '未接触'),
        data.get('cooperation_opportunities', ''),
        data.get('website', ''),
        data.get('contact_person', ''),
        data.get('contact_info', ''),
        data.get('owner_id', '') or payload['username'],
        now, now,
    ))
    db.commit()
    enterprise_id = cursor.lastrowid

    record_operation_log(payload['username'], '新建', '企业信息库', f'新建企业: {data["name"]}')

    return jsonify({'code': 200, 'message': '创建成功', 'data': {'id': enterprise_id}})


@enterprises_bp.route('/api/enterprises/<int:enterprise_id>', methods=['PUT'])
@token_required
def update_enterprise(enterprise_id):
    """修改企业信息。"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT id FROM enterprises WHERE id = ?", (enterprise_id,))
    if not cursor.fetchone():
        return jsonify({'code': 404, 'message': '企业不存在', 'data': None})

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    fields = ['name', 'established_date', 'location', 'personnel_size', 'brief',
              'registered_capital', 'business_scope', 'main_qualifications', 'main_products',
              'relationship_status', 'cooperation_opportunities', 'website', 'contact_person',
              'contact_info', 'owner_id']

    sets = []
    params = []
    for f in fields:
        if f in data:
            sets.append(f"{f} = ?")
            params.append(data[f])
    sets.append("updated_at = ?")
    params.append(now)
    params.append(enterprise_id)

    cursor.execute(f"UPDATE enterprises SET {', '.join(sets)} WHERE id = ?", params)
    db.commit()

    record_operation_log(payload['username'], '修改', '企业信息库', f'修改企业ID: {enterprise_id}')

    return jsonify({'code': 200, 'message': '修改成功', 'data': None})


@enterprises_bp.route('/api/enterprises/<int:enterprise_id>', methods=['DELETE'])
@token_required
def delete_enterprise(enterprise_id):
    """删除企业信息。"""
    payload = request.current_user

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT name FROM enterprises WHERE id = ?", (enterprise_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '企业不存在', 'data': None})

    name = row['name']
    cursor.execute("DELETE FROM enterprise_visits WHERE enterprise_id = ?", (enterprise_id,))
    cursor.execute("DELETE FROM enterprises WHERE id = ?", (enterprise_id,))
    db.commit()

    record_operation_log(payload['username'], '删除', '企业信息库', f'删除企业: {name}')

    return jsonify({'code': 200, 'message': '删除成功', 'data': None})


@enterprises_bp.route('/api/enterprises/<int:enterprise_id>/visits', methods=['POST'])
@token_required
def link_visit(enterprise_id):
    """关联拜访记录到企业。"""
    data = request.get_json(silent=True) or {}
    visit_id = data.get('visit_id')
    if not visit_id:
        return jsonify({'code': 400, 'message': '请选择拜访记录', 'data': None})

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT id FROM enterprises WHERE id = ?", (enterprise_id,))
    if not cursor.fetchone():
        return jsonify({'code': 404, 'message': '企业不存在', 'data': None})

    cursor.execute("SELECT id FROM visits WHERE id = ?", (visit_id,))
    if not cursor.fetchone():
        return jsonify({'code': 404, 'message': '拜访记录不存在', 'data': None})

    try:
        cursor.execute(
            "INSERT INTO enterprise_visits (enterprise_id, visit_id) VALUES (?, ?)",
            (enterprise_id, visit_id)
        )
        db.commit()
    except Exception:
        return jsonify({'code': 409, 'message': '该拜访记录已关联', 'data': None})

    return jsonify({'code': 200, 'message': '关联成功', 'data': None})


@enterprises_bp.route('/api/enterprises/<int:enterprise_id>/visits/<int:visit_id>', methods=['DELETE'])
@token_required
def unlink_visit(enterprise_id, visit_id):
    """取消关联拜访记录。"""
    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "DELETE FROM enterprise_visits WHERE enterprise_id = ? AND visit_id = ?",
        (enterprise_id, visit_id)
    )
    db.commit()

    return jsonify({'code': 200, 'message': '取消关联成功', 'data': None})


@enterprises_bp.route('/api/enterprises/import', methods=['POST'])
@token_required
def import_enterprises():
    """批量导入企业信息。"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    rows = data.get('rows', [])

    if not rows:
        return jsonify({'code': 400, 'message': '没有可导入的数据', 'data': None})

    db = get_db()
    cursor = db.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    success_count = 0
    fail_count = 0
    results = []

    for idx, row in enumerate(rows, 1):
        name = (row.get('name') or '').strip()
        if not name:
            fail_count += 1
            results.append({'row_index': idx, 'success': False, 'message': '企业名称不能为空'})
            continue

        try:
            cursor.execute("""
                INSERT INTO enterprises (name, established_date, location, personnel_size, brief,
                    registered_capital, business_scope, main_qualifications, main_products,
                    relationship_status, cooperation_opportunities, website, contact_person,
                    contact_info, owner_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name,
                row.get('established_date', ''),
                row.get('location', ''),
                row.get('personnel_size', ''),
                row.get('brief', ''),
                row.get('registered_capital', ''),
                row.get('business_scope', ''),
                row.get('main_qualifications', ''),
                row.get('main_products', ''),
                row.get('relationship_status', '未接触'),
                row.get('cooperation_opportunities', ''),
                row.get('website', ''),
                row.get('contact_person', ''),
                row.get('contact_info', ''),
                row.get('owner_id', '') or payload['username'],
                now, now,
            ))
            success_count += 1
            results.append({'row_index': idx, 'success': True, 'message': '成功'})
        except Exception as e:
            fail_count += 1
            results.append({'row_index': idx, 'success': False, 'message': str(e)})

    db.commit()

    record_operation_log(payload['username'], '导入', '企业信息库',
                         f'导入企业信息: 成功{success_count}条, 失败{fail_count}条')

    return jsonify({
        'code': 200,
        'message': f'导入完成: 成功{success_count}条, 失败{fail_count}条',
        'data': {
            'success_count': success_count,
            'fail_count': fail_count,
            'results': results,
        }
    })


def register_routes(app):
    app.register_blueprint(enterprises_bp)
