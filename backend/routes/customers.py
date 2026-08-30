import json

from flask import request, jsonify, g
from extensions import (
    get_db, verify_token, create_token, check_password, hash_password,
    record_operation_log, token_required, admin_required, user_can,
    check_login_rate_limit, record_login_attempt,
    LOGIN_ATTEMPTS, LOGIN_MAX_ATTEMPTS,
)

from . import customers_bp
from .custom_fields import validate_ext, parse_ext


@customers_bp.route('/api/customers', methods=['GET'])
@token_required
def get_customers():
    payload = request.current_user
    username = payload['username']
    role = payload['role']
    keyword = request.args.get('keyword', '')
    level = request.args.get('level', '')
    industry = request.args.get('industry', '')
    source = request.args.get('source', '')

    db = get_db()
    cursor = db.cursor()

    conditions = []
    params = []

    if not user_can(username, 'data.view_all'):
        conditions.append("c.owner_id = ?")
        params.append(username)

    if keyword:
        conditions.append("(c.company LIKE ? OR c.name LIKE ? OR c.contact_name LIKE ? OR c.phone LIKE ?)")
        params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])
    if level:
        conditions.append("c.level = ?")
        params.append(level)
    if industry:
        conditions.append("c.industry = ?")
        params.append(industry)
    if source:
        conditions.append("c.source = ?")
        params.append(source)

    where_clause = ' AND '.join(conditions) if conditions else '1=1'

    cursor.execute(f"""
        SELECT c.*, u.name as owner_name
        FROM customers c
        LEFT JOIN users u ON c.owner_id = u.username
        WHERE {where_clause}
        ORDER BY c.created_at DESC
    """, params)

    rows = cursor.fetchall()
    customers = []
    for row in rows:
        customers.append(parse_ext(dict(row)))

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
        ext_cleaned, ext_err = validate_ext(cursor, 'customer', data.get('ext_data'))
        if ext_err:
            return jsonify({'code': 400, 'message': ext_err, 'data': None})

        cursor.execute("""
            INSERT INTO customers (name, company, phone, level, source, owner_id, contact_name, email, industry, region, address, ext_data, created_at, last_follow)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (
            data.get('name'), data.get('company'), data.get('phone'),
            data.get('level'), data.get('source'), data.get('owner_id'),
            data.get('contact_name'), data.get('email'), data.get('industry'),
            data.get('region'), data.get('address'),
            json.dumps(ext_cleaned, ensure_ascii=False) if ext_cleaned else None
        ))
        db.commit()

        record_operation_log(username, '创建', '客户', f'创建客户：{data.get("name")}（{data.get("company")}）')

        return jsonify({'code': 200, 'message': '客户创建成功', 'data': {'id': cursor.lastrowid}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@customers_bp.route('/api/customers/<int:cust_id>', methods=['GET'])
@token_required
def get_customer(cust_id):
    payload = request.current_user
    username = payload['username']
    role = payload['role']

    db = get_db()
    cursor = db.cursor()

    if user_can(username, 'data.view_all'):
        cursor.execute("""
            SELECT c.*, u.name as owner_name
            FROM customers c
            LEFT JOIN users u ON c.owner_id = u.username
            WHERE c.id = ?
        """, (cust_id,))
    else:
        cursor.execute("""
            SELECT c.*, u.name as owner_name
            FROM customers c
            LEFT JOIN users u ON c.owner_id = u.username
            WHERE c.id = ? AND c.owner_id = ?
        """, (cust_id, username))

    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '客户不存在', 'data': None})

    return jsonify({'code': 200, 'message': 'success', 'data': parse_ext(dict(row))})


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

    if not user_can(username, 'data.view_all') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足，只能删除自己的客户', 'data': None})

    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("SELECT name, company FROM customers WHERE id=?", (cust_id,))
        row = cursor.fetchone()
        customer_info = f"{row['name']}（{row['company']}）" if row else f"ID:{cust_id}"

        cursor.execute("UPDATE business SET cust_id = NULL WHERE cust_id = ?", (cust_id,))
        cursor.execute("UPDATE contracts SET cust_id = NULL WHERE cust_id = ?", (cust_id,))
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
        can_change_owner = user_can(username, 'data.view_all')

        # ext_data：传入才校验并覆盖，未传保留原值
        ext_clause = ""
        ext_param = None
        if 'ext_data' in data:
            ext_cleaned, ext_err = validate_ext(cursor, 'customer', data.get('ext_data'))
            if ext_err:
                return jsonify({'code': 400, 'message': ext_err, 'data': None})
            ext_clause = ", ext_data=?"
            ext_param = json.dumps(ext_cleaned, ensure_ascii=False) if ext_cleaned else None

        if can_change_owner and 'owner_id' in data:
            cursor.execute(f"""
                UPDATE customers SET
                    name=?, company=?, phone=?, level=?, source=?,
                    contact_name=?, email=?, industry=?, region=?,
                    address=?, owner_id=?, previous_owner=owner_id{ext_clause}
                WHERE id=?
            """, (
                data.get('name'), data.get('company'), data.get('phone'),
                data.get('level'), data.get('source'),
                data.get('contact_name'), data.get('email'),
                data.get('industry'), data.get('region'),
                data.get('address'), data.get('owner_id'),
                ext_param, cust_id
            ))
        else:
            cursor.execute(f"""
                UPDATE customers SET
                    name=?, company=?, phone=?, level=?, source=?,
                    contact_name=?, email=?, industry=?, region=?,
                    address=?{ext_clause}
                WHERE id=?
            """, (
                data.get('name'), data.get('company'), data.get('phone'),
                data.get('level'), data.get('source'),
                data.get('contact_name'), data.get('email'),
                data.get('industry'), data.get('region'),
                data.get('address'),
                ext_param, cust_id
            ))
        db.commit()

        record_operation_log(username, '编辑', '客户', f'编辑客户：{data.get("name")}（ID:{cust_id}）')

        return jsonify({'code': 200, 'message': '客户更新成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@customers_bp.route('/api/customers/<int:cust_id>/profile', methods=['GET'])
@token_required
def get_customer_profile(cust_id):
    """聚合返回客户 3D 画像：基本信息 + 跟进 + 商机 + 合同 + 拜访 + 统计汇总"""
    payload = request.current_user
    username = payload['username']
    role = payload['role']

    db = get_db()
    cursor = db.cursor()

    # 1. 查询客户基本信息并做 404 + 权限校验
    cursor.execute("""
        SELECT c.*, u.name as owner_name
        FROM customers c
        LEFT JOIN users u ON c.owner_id = u.username
        WHERE c.id = ?
    """, (cust_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '客户不存在', 'data': None})
    if not user_can(username, 'data.view_all') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足，只能查看自己的客户', 'data': None})

    customer = dict(row)
    customer_company = customer.get('company') or ''

    # 2. 跟进记录
    cursor.execute("""
        SELECT fl.*, u.name as user_name
        FROM follow_logs fl
        LEFT JOIN users u ON fl.user_id = u.username
        WHERE fl.ref_type = 'customer' AND fl.ref_id = ?
        ORDER BY fl.created_at DESC
    """, (cust_id,))
    follow_logs = [dict(r) for r in cursor.fetchall()]

    # 3. 商机
    cursor.execute("""
        SELECT b.*, u.name as owner_name
        FROM business b
        LEFT JOIN users u ON b.owner_id = u.username
        WHERE b.cust_id = ?
        ORDER BY b.created_at DESC
    """, (cust_id,))
    business = [dict(r) for r in cursor.fetchall()]

    # 4. 合同（cust_id 精确关联为主；历史无 cust_id 的按 party_a 模糊关联并标注 linkage）
    #    linkage: precise=精确关联本客户；fuzzy=按公司名模糊关联(待精确指定)；other=其它
    if customer_company:
        cursor.execute("""
            SELECT ct.*, u.name as owner_name, b.title as business_title,
                   cu.company as customer_name,
                   CASE
                       WHEN ct.cust_id = ? THEN 'precise'
                       WHEN ct.cust_id IS NULL AND ct.party_a = ? THEN 'fuzzy'
                       ELSE 'other'
                   END as linkage
            FROM contracts ct
            LEFT JOIN users u ON ct.owner_id = u.username
            LEFT JOIN business b ON ct.b_id = b.id
            LEFT JOIN customers cu ON ct.cust_id = cu.id
            WHERE ct.cust_id = ?
               OR (ct.cust_id IS NULL AND ct.party_a = ? AND ct.party_a != '')
            ORDER BY ct.sign_date DESC
        """, (cust_id, customer_company, cust_id, customer_company))
    else:
        cursor.execute("""
            SELECT ct.*, u.name as owner_name, b.title as business_title,
                   cu.company as customer_name,
                   CASE WHEN ct.cust_id = ? THEN 'precise' ELSE 'other' END as linkage
            FROM contracts ct
            LEFT JOIN users u ON ct.owner_id = u.username
            LEFT JOIN business b ON ct.b_id = b.id
            LEFT JOIN customers cu ON ct.cust_id = cu.id
            WHERE ct.cust_id = ?
            ORDER BY ct.sign_date DESC
        """, (cust_id, cust_id))
    contracts = [dict(r) for r in cursor.fetchall()]
    # 模糊关联(按公司名匹配)的合同无 cust_id，JOIN 得不到客户名，这里用画像客户公司名兜底，
    # 使前端时间轴能正确展示"客户→商机→合同"关系链
    for c in contracts:
        if not c.get('customer_name'):
            c['customer_name'] = customer_company

    # 5. 拜访记录
    cursor.execute("""
        SELECT v.*, u.name as visitor_name
        FROM visits v
        LEFT JOIN users u ON v.visitor_id = u.username
        WHERE v.cust_id = ?
        ORDER BY v.plan_date DESC, v.plan_time DESC
    """, (cust_id,))
    visits = [dict(r) for r in cursor.fetchall()]

    # 6. 统计汇总（total_amt 单位为元，前端再除 10000 转万元）
    stats = {
        'business_count': len(business),
        'contract_count': len(contracts),
        'contract_total_amt': sum(float(c.get('total_amt') or 0) for c in contracts),
        'visit_count': len(visits),
        'follow_count': len(follow_logs)
    }

    # 7. 关联企业信息（按客户公司名匹配企业信息库）
    enterprise = None
    if customer_company:
        cursor.execute("""
            SELECT e.id, e.name, e.established_date, e.location, e.personnel_size,
                   e.brief, e.registered_capital, e.business_scope, e.main_qualifications,
                   e.main_products, e.relationship_status, e.cooperation_opportunities,
                   e.website, e.contact_person, e.contact_info
            FROM enterprises e
            WHERE e.name = ? OR e.name LIKE ? OR ? LIKE '%' || e.name || '%'
            LIMIT 1
        """, (customer_company, f'%{customer_company}%', customer_company))
        ent_row = cursor.fetchone()
        if ent_row:
            enterprise = dict(ent_row)

    return jsonify({
        'code': 200,
        'message': 'success',
        'data': {
            'customer': customer,
            'follow_logs': follow_logs,
            'business': business,
            'contracts': contracts,
            'visits': visits,
            'stats': stats,
            'enterprise': enterprise
        }
    })


@customers_bp.route('/api/customers/analysis', methods=['GET'])
@token_required
def analyze_customers():
    """自动收集和分析客户数据：等级分布、行业分布、来源分布、地区分布、转化漏斗。"""
    payload = request.current_user
    username = payload['username']
    role = payload['role']

    db = get_db()
    cursor = db.cursor()

    # 权限过滤
    can_view_all = user_can(username, 'data.view_all')
    owner_filter = "" if can_view_all else "WHERE c.owner_id = ?"
    owner_params = [] if can_view_all else [username]

    # 1. 总数
    cursor.execute(f"SELECT COUNT(*) as total FROM customers c {owner_filter}", owner_params)
    total = cursor.fetchone()['total']

    # 2. 等级分布
    cursor.execute(f"""
        SELECT COALESCE(NULLIF(c.level, ''), '未分级') as level, COUNT(*) as count
        FROM customers c {owner_filter}
        GROUP BY c.level ORDER BY count DESC
    """, owner_params)
    level_dist = [dict(r) for r in cursor.fetchall()]

    # 3. 行业分布
    cursor.execute(f"""
        SELECT COALESCE(NULLIF(c.industry, ''), '未分类') as industry, COUNT(*) as count
        FROM customers c {owner_filter}
        GROUP BY c.industry ORDER BY count DESC
    """, owner_params)
    industry_dist = [dict(r) for r in cursor.fetchall()]

    # 4. 来源分布
    cursor.execute(f"""
        SELECT COALESCE(NULLIF(c.source, ''), '未知') as source, COUNT(*) as count
        FROM customers c {owner_filter}
        GROUP BY c.source ORDER BY count DESC
    """, owner_params)
    source_dist = [dict(r) for r in cursor.fetchall()]

    # 5. 地区分布
    cursor.execute(f"""
        SELECT COALESCE(NULLIF(c.region, ''), '未知') as region, COUNT(*) as count
        FROM customers c {owner_filter}
        GROUP BY c.region ORDER BY count DESC LIMIT 10
    """, owner_params)
    region_dist = [dict(r) for r in cursor.fetchall()]

    # 6. 转化漏斗：客户数 → 有商机数 → 有合同数 → 有回款数
    cust_cond = "c.owner_id = ?" if not can_view_all else "1=1"
    cust_params = [username] if not can_view_all else []

    cursor.execute(f"""
        SELECT COUNT(DISTINCT c.id) as total FROM customers c WHERE {cust_cond}
    """, cust_params)
    total_customers = cursor.fetchone()['total']

    cursor.execute(f"""
        SELECT COUNT(DISTINCT c.id) as total FROM customers c
        WHERE {cust_cond} AND EXISTS (SELECT 1 FROM business b WHERE b.cust_id = c.id)
    """, cust_params)
    has_business = cursor.fetchone()['total']

    cursor.execute(f"""
        SELECT COUNT(DISTINCT c.id) as total FROM customers c
        WHERE {cust_cond} AND EXISTS (SELECT 1 FROM contracts ct WHERE ct.cust_id = c.id)
    """, cust_params)
    has_contract = cursor.fetchone()['total']

    cursor.execute(f"""
        SELECT COUNT(DISTINCT c.id) as total FROM customers c
        WHERE {cust_cond} AND EXISTS (
            SELECT 1 FROM contracts ct WHERE ct.cust_id = c.id AND ct.paid_amt > 0
        )
    """, cust_params)
    has_payment = cursor.fetchone()['total']

    funnel = [
        {'stage': '客户总数', 'count': total_customers},
        {'stage': '有商机', 'count': has_business},
        {'stage': '有合同', 'count': has_contract},
        {'stage': '已回款', 'count': has_payment},
    ]

    # 7. 负责人业绩排行（仅管理层可见）
    owner_ranking = []
    if user_can(username, 'data.view_all'):
        cursor.execute("""
            SELECT u.name as owner_name, c.owner_id,
                   COUNT(DISTINCT c.id) as customer_count,
                   COUNT(DISTINCT b.id) as business_count,
                   COUNT(DISTINCT ct.id) as contract_count,
                   COALESCE(SUM(ct.total_amt), 0) as total_amount
            FROM customers c
            LEFT JOIN users u ON c.owner_id = u.username
            LEFT JOIN business b ON b.cust_id = c.id
            LEFT JOIN contracts ct ON ct.cust_id = c.id
            GROUP BY c.owner_id
            ORDER BY total_amount DESC
        """)
        owner_ranking = [dict(r) for r in cursor.fetchall()]

    return jsonify({
        'code': 200,
        'message': 'success',
        'data': {
            'total': total,
            'level_distribution': level_dist,
            'industry_distribution': industry_dist,
            'source_distribution': source_dist,
            'region_distribution': region_dist,
            'conversion_funnel': funnel,
            'owner_ranking': owner_ranking,
        }
    })


def register_routes(app):
    app.register_blueprint(customers_bp)
