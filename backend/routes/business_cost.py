"""商机成本评估：销售发起 → 技术主任确认研发工时 → 销售提交生效

口径：
  人工成本 = 研发预估工时 ÷ 每月标准工时(174h) × 人月单价(2.5万)
  管理费   = (人工成本 + 外协成本 + 其他成本) × 15%
  成本合计 = 人工 + 外协 + 其他 + 管理费
"""
import json
from datetime import datetime

from flask import request, jsonify

from extensions import get_db, record_operation_log, token_required, user_can
from . import business_cost_bp

# 默认核算参数（创建评估单时快照，保证历史记录口径稳定）
DEFAULT_MONTH_HOURS = 174.0      # 21.75 天 × 8 小时
DEFAULT_MONTHLY_RATE = 25000.0   # 元/人月
DEFAULT_MANAGE_RATE = 0.15       # 管理费比例
TECH_DEPT = '技术中心'

LABOR_ROLES = ['项目经理', '需求分析', '架构设计', '开发', '测试', '实施', '运维', '其他']
STATUS_LABEL = {
    'draft': '待技术确认工时',
    'hours_confirmed': '待销售提交',
    'submitted': '已生效',
    'rejected': '技术已驳回',
}


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _f(v, default=0.0):
    try:
        return float(v if v is not None else default)
    except (TypeError, ValueError):
        return default


def _get_user(cursor, username):
    if not username:
        return None
    cursor.execute("SELECT username, name, role, department, status FROM users WHERE username=?", (username,))
    return cursor.fetchone()


def _is_tech_leader(cursor, username):
    """技术主任：技术中心 + 主任；院长可越级确认"""
    u = _get_user(cursor, username)
    if not u:
        return False
    if u.get('department') == TECH_DEPT and u.get('role') == '主任':
        return True
    return u.get('role') == '院长'


def _can_view(cursor, username, business_owner):
    """可见性：项目负责人 / 技术主任 / 院长 / 财务 / 全局数据权限"""
    if username == business_owner:
        return True
    if user_can(username, 'data.view_all') or user_can(username, 'contracts.view_all'):
        return True
    u = _get_user(cursor, username)
    if not u:
        return False
    if u.get('role') in ('院长', '财务', '主任'):
        return True
    return _is_tech_leader(cursor, username)


def _load_items(cursor, estimate_id):
    cursor.execute("""
        SELECT id, biz_type, role_name, item_name, hours, amount, note, sort_order
        FROM business_cost_items WHERE estimate_id=? ORDER BY sort_order, id
    """, (estimate_id,))
    rows = cursor.fetchall() or []
    labor, outsource, other = [], [], []
    for r in rows:
        d = dict(r)
        d['hours'] = _f(d.get('hours'))
        d['amount'] = _f(d.get('amount'))
        target = {'labor': labor, 'outsource': outsource, 'other': other}.get(d.get('biz_type'))
        if target is not None:
            target.append(d)
    return labor, outsource, other


def _recalc(cursor, estimate_id):
    """按明细重算金额并写回评估单"""
    cursor.execute("SELECT * FROM business_cost_estimates WHERE id=?", (estimate_id,))
    est = cursor.fetchone()
    if not est:
        return None
    month_hours = _f(est.get('month_hours'), DEFAULT_MONTH_HOURS) or DEFAULT_MONTH_HOURS
    monthly_rate = _f(est.get('monthly_rate'), DEFAULT_MONTHLY_RATE)
    manage_rate = _f(est.get('manage_rate'), DEFAULT_MANAGE_RATE)

    labor, outsource, other = _load_items(cursor, estimate_id)
    labor_hours = round(sum(_f(i['hours']) for i in labor), 2)
    labor_cost = round(labor_hours / month_hours * monthly_rate, 2)
    outsource_cost = round(sum(_f(i['amount']) for i in outsource), 2)
    other_cost = round(sum(_f(i['amount']) for i in other), 2)
    manage_cost = round((labor_cost + outsource_cost + other_cost) * manage_rate, 2)
    total_cost = round(labor_cost + outsource_cost + other_cost + manage_cost, 2)

    cursor.execute("""
        UPDATE business_cost_estimates SET
            labor_hours=?, labor_cost=?, outsource_cost=?, other_cost=?,
            manage_cost=?, total_cost=?, updated_at=?
        WHERE id=?
    """, (labor_hours, labor_cost, outsource_cost, other_cost,
          manage_cost, total_cost, _now(), estimate_id))
    cursor.execute("SELECT * FROM business_cost_estimates WHERE id=?", (estimate_id,))
    return cursor.fetchone()


def _get_business(cursor, business_id):
    cursor.execute("""
        SELECT b.id, b.title, b.amount, b.stage, b.owner_id, b.predict_date,
               b.probability, b.status, b.total_cost,
               c.company AS customer_name, u.name AS owner_name, u.department AS owner_department
        FROM business b
        LEFT JOIN customers c ON b.cust_id = c.id
        LEFT JOIN users u ON b.owner_id = u.username
        WHERE b.id=?
    """, (business_id,))
    return cursor.fetchone()


def _get_estimate(cursor, business_id):
    cursor.execute("SELECT * FROM business_cost_estimates WHERE business_id=?", (business_id,))
    return cursor.fetchone()


def _payload(cursor, business, est, username):
    """组装前端所需完整数据"""
    if not est:
        return {
            'business': dict(business),
            'estimate': None,
            'labor_items': [], 'outsource_items': [], 'other_items': [],
            'summary': None,
            'permissions': {
                'can_create': username == business.get('owner_id'),
                'can_edit_labor': False,
                'can_edit_other': False,
                'can_confirm': False,
                'can_reject': False,
                'can_submit': False,
                'can_reopen': False,
            },
            'params': {
                'month_hours': DEFAULT_MONTH_HOURS,
                'monthly_rate': DEFAULT_MONTHLY_RATE,
                'manage_rate': DEFAULT_MANAGE_RATE,
            },
            'roles': LABOR_ROLES,
            'status_label': STATUS_LABEL,
        }

    labor, outsource, other = _load_items(cursor, est['id'])
    status = est.get('status') or 'draft'
    is_owner = username == business.get('owner_id')
    is_tech = _is_tech_leader(cursor, username)
    # 编辑窗口：draft / rejected
    editable = status in ('draft', 'rejected')

    amount = _f(business.get('amount'))
    total_cost = _f(est.get('total_cost'))
    gross_profit = round(amount - total_cost, 2)
    gross_rate = round(gross_profit / amount * 100, 2) if amount > 0 else None

    month_hours = _f(est.get('month_hours'), DEFAULT_MONTH_HOURS) or DEFAULT_MONTH_HOURS
    monthly_rate = _f(est.get('monthly_rate'), DEFAULT_MONTHLY_RATE)

    return {
        'business': dict(business),
        'estimate': dict(est),
        'labor_items': labor,
        'outsource_items': outsource,
        'other_items': other,
        'summary': {
            'labor_hours': _f(est.get('labor_hours')),
            'person_month': round(_f(est.get('labor_hours')) / month_hours, 2),
            'labor_cost': _f(est.get('labor_cost')),
            'outsource_cost': _f(est.get('outsource_cost')),
            'other_cost': _f(est.get('other_cost')),
            'manage_cost': _f(est.get('manage_cost')),
            'total_cost': total_cost,
            'amount': amount,
            'gross_profit': gross_profit,
            'gross_rate': gross_rate,
        },
        'permissions': {
            'can_create': is_owner and est is None,
            'can_edit_labor': is_tech and editable,
            'can_edit_other': is_owner and editable,
            'can_confirm': is_tech and editable,
            'can_reject': is_tech and status == 'draft',
            'can_submit': is_owner and status == 'hours_confirmed',
            'can_reopen': is_owner and status == 'submitted',
        },
        'params': {
            'month_hours': month_hours,
            'monthly_rate': monthly_rate,
            'manage_rate': _f(est.get('manage_rate'), DEFAULT_MANAGE_RATE),
        },
        'roles': LABOR_ROLES,
        'status_label': STATUS_LABEL,
    }


@business_cost_bp.route('/api/business/<int:business_id>/cost', methods=['GET'])
@token_required
def get_business_cost(business_id):
    payload_user = request.current_user
    username = payload_user['username']
    db = get_db()
    cursor = db.cursor()

    business = _get_business(cursor, business_id)
    if not business:
        return jsonify({'code': 404, 'message': '商机不存在', 'data': None})
    if not _can_view(cursor, username, business.get('owner_id')):
        return jsonify({'code': 403, 'message': '无权查看该商机成本', 'data': None})

    est = _get_estimate(cursor, business_id)
    return jsonify({'code': 200, 'message': 'success', 'data': _payload(cursor, business, est, username)})


@business_cost_bp.route('/api/business/<int:business_id>/cost', methods=['POST'])
@token_required
def create_business_cost(business_id):
    username = request.current_user['username']
    db = get_db()
    cursor = db.cursor()

    business = _get_business(cursor, business_id)
    if not business:
        return jsonify({'code': 404, 'message': '商机不存在', 'data': None})
    if business.get('owner_id') != username:
        return jsonify({'code': 403, 'message': '仅商机负责人可发起成本评估', 'data': None})
    if _get_estimate(cursor, business_id):
        return jsonify({'code': 400, 'message': '该商机已有成本评估单', 'data': None})

    now = _now()
    cursor.execute("""
        INSERT INTO business_cost_estimates
            (business_id, status, month_hours, monthly_rate, manage_rate,
             labor_hours, labor_cost, outsource_cost, other_cost, manage_cost, total_cost,
             created_by, created_at, updated_at)
        VALUES (?, 'draft', ?, ?, ?, 0, 0, 0, 0, 0, 0, ?, ?, ?)
    """, (business_id, DEFAULT_MONTH_HOURS, DEFAULT_MONTHLY_RATE, DEFAULT_MANAGE_RATE,
          username, now, now))
    db.commit()
    cursor.execute("SELECT id FROM business_cost_estimates WHERE business_id=?", (business_id,))
    new_id = cursor.fetchone()['id']
    record_operation_log(username, 'create', 'business_cost', new_id,
                         f"发起商机成本评估：{business.get('title')}")
    return jsonify({'code': 200, 'message': '成本评估单已创建，等待技术部门填报研发工时', 'data': {'id': new_id}})


@business_cost_bp.route('/api/business/<int:business_id>/cost/labor', methods=['PUT'])
@token_required
def save_labor_items(business_id):
    username = request.current_user['username']
    data = request.get_json(silent=True) or {}
    items = data.get('items') or []
    db = get_db()
    cursor = db.cursor()

    business = _get_business(cursor, business_id)
    if not business:
        return jsonify({'code': 404, 'message': '商机不存在', 'data': None})
    est = _get_estimate(cursor, business_id)
    if not est:
        return jsonify({'code': 400, 'message': '请先发起成本评估', 'data': None})
    if not _is_tech_leader(cursor, username):
        return jsonify({'code': 403, 'message': '仅技术部门负责人可填报研发工时', 'data': None})
    if (est.get('status') or 'draft') not in ('draft', 'rejected'):
        return jsonify({'code': 400, 'message': '当前状态不可修改工时', 'data': None})

    clean = []
    for idx, it in enumerate(items):
        hours = _f(it.get('hours'))
        if hours < 0:
            return jsonify({'code': 400, 'message': '工时不能为负数', 'data': None})
        role = (it.get('role_name') or '').strip()
        if not role and hours == 0:
            continue
        if not role:
            return jsonify({'code': 400, 'message': '请选择工时对应角色', 'data': None})
        clean.append((est['id'], 'labor', role, None, round(hours, 2), 0, it.get('note'), idx))

    cursor.execute("DELETE FROM business_cost_items WHERE estimate_id=? AND biz_type='labor'", (est['id'],))
    if clean:
        cursor.executemany("""
            INSERT INTO business_cost_items
                (estimate_id, biz_type, role_name, item_name, hours, amount, note, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, clean)
    # 技术重新填报后退回待确认，便于销售重新提交
    cursor.execute("UPDATE business_cost_estimates SET status='draft', updated_at=? WHERE id=?",
                   (_now(), est['id']))
    est2 = _recalc(cursor, est['id'])
    db.commit()
    record_operation_log(username, 'update', 'business_cost', est['id'],
                         f"填报研发工时：{est2.get('labor_hours')}h")
    return jsonify({'code': 200, 'message': '研发工时已保存', 'data': dict(est2)})


@business_cost_bp.route('/api/business/<int:business_id>/cost/other', methods=['PUT'])
@token_required
def save_other_items(business_id):
    username = request.current_user['username']
    data = request.get_json(silent=True) or {}
    outsource = data.get('outsource_items') or []
    other = data.get('other_items') or []
    note = (data.get('note') or '').strip()
    db = get_db()
    cursor = db.cursor()

    business = _get_business(cursor, business_id)
    if not business:
        return jsonify({'code': 404, 'message': '商机不存在', 'data': None})
    est = _get_estimate(cursor, business_id)
    if not est:
        return jsonify({'code': 400, 'message': '请先发起成本评估', 'data': None})
    if business.get('owner_id') != username:
        return jsonify({'code': 403, 'message': '仅商机负责人可维护外协/其他成本', 'data': None})
    if (est.get('status') or 'draft') not in ('draft', 'rejected'):
        return jsonify({'code': 400, 'message': '当前状态不可修改成本明细', 'data': None})

    clean = []
    for biz_type, rows in (('outsource', outsource), ('other', other)):
        for idx, it in enumerate(rows):
            name = (it.get('item_name') or '').strip()
            amount = _f(it.get('amount'))
            if not name and amount == 0:
                continue
            if not name:
                return jsonify({'code': 400, 'message': '请填写成本项目名称', 'data': None})
            if amount < 0:
                return jsonify({'code': 400, 'message': '金额不能为负数', 'data': None})
            clean.append((est['id'], biz_type, None, name, 0, round(amount, 2), it.get('note'), idx))

    cursor.execute("DELETE FROM business_cost_items WHERE estimate_id=? AND biz_type IN ('outsource','other')",
                   (est['id'],))
    if clean:
        cursor.executemany("""
            INSERT INTO business_cost_items
                (estimate_id, biz_type, role_name, item_name, hours, amount, note, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, clean)
    cursor.execute("UPDATE business_cost_estimates SET note=?, updated_at=? WHERE id=?",
                   (note, _now(), est['id']))
    est2 = _recalc(cursor, est['id'])
    db.commit()
    record_operation_log(username, 'update', 'business_cost', est['id'], '维护外协/其他成本')
    return jsonify({'code': 200, 'message': '成本明细已保存', 'data': dict(est2)})


@business_cost_bp.route('/api/business/<int:business_id>/cost/confirm', methods=['POST'])
@token_required
def confirm_labor(business_id):
    username = request.current_user['username']
    db = get_db()
    cursor = db.cursor()

    business = _get_business(cursor, business_id)
    est = _get_estimate(cursor, business_id)
    if not business or not est:
        return jsonify({'code': 404, 'message': '成本评估单不存在', 'data': None})
    if not _is_tech_leader(cursor, username):
        return jsonify({'code': 403, 'message': '仅技术部门负责人可确认工时', 'data': None})
    if (est.get('status') or 'draft') not in ('draft', 'rejected'):
        return jsonify({'code': 400, 'message': '当前状态不可确认工时', 'data': None})
    if _f(est.get('labor_hours')) <= 0:
        return jsonify({'code': 400, 'message': '请先填报研发预估工时', 'data': None})

    me = _get_user(cursor, username)
    cursor.execute("""
        UPDATE business_cost_estimates SET
            status='hours_confirmed', tech_confirmed_by=?, tech_confirmed_at=?,
            tech_reject_reason=NULL, updated_at=?
        WHERE id=?
    """, (me.get('name') or username, _now(), _now(), est['id']))
    db.commit()
    record_operation_log(username, 'approve', 'business_cost', est['id'], '技术部门确认研发工时')
    return jsonify({'code': 200, 'message': '工时已确认，等待销售提交', 'data': dict(est)})


@business_cost_bp.route('/api/business/<int:business_id>/cost/reject', methods=['POST'])
@token_required
def reject_labor(business_id):
    username = request.current_user['username']
    data = request.get_json(silent=True) or {}
    reason = (data.get('reason') or '').strip()
    if not reason:
        return jsonify({'code': 400, 'message': '请填写驳回理由', 'data': None})

    db = get_db()
    cursor = db.cursor()
    business = _get_business(cursor, business_id)
    est = _get_estimate(cursor, business_id)
    if not business or not est:
        return jsonify({'code': 404, 'message': '成本评估单不存在', 'data': None})
    if not _is_tech_leader(cursor, username):
        return jsonify({'code': 403, 'message': '仅技术部门负责人可驳回', 'data': None})
    if (est.get('status') or 'draft') != 'draft':
        return jsonify({'code': 400, 'message': '当前状态不可驳回', 'data': None})

    cursor.execute("""
        UPDATE business_cost_estimates SET status='rejected', tech_reject_reason=?, updated_at=? WHERE id=?
    """, (reason, _now(), est['id']))
    db.commit()
    record_operation_log(username, 'reject', 'business_cost', est['id'], f'技术驳回：{reason}')
    return jsonify({'code': 200, 'message': '已驳回，销售可修改后重新提交', 'data': None})


@business_cost_bp.route('/api/business/<int:business_id>/cost/submit', methods=['POST'])
@token_required
def submit_cost(business_id):
    username = request.current_user['username']
    db = get_db()
    cursor = db.cursor()

    business = _get_business(cursor, business_id)
    est = _get_estimate(cursor, business_id)
    if not business or not est:
        return jsonify({'code': 404, 'message': '成本评估单不存在', 'data': None})
    if business.get('owner_id') != username:
        return jsonify({'code': 403, 'message': '仅商机负责人可提交', 'data': None})
    if (est.get('status') or 'draft') != 'hours_confirmed':
        return jsonify({'code': 400, 'message': '技术部门尚未确认工时，暂不可提交', 'data': None})

    now = _now()
    cursor.execute("""
        UPDATE business_cost_estimates SET status='submitted', submitted_by=?, submitted_at=?, updated_at=?
        WHERE id=?
    """, (username, now, now, est['id']))
    # 回写商机成本总额，便于商机列表/报表直接引用
    cursor.execute("UPDATE business SET total_cost=? WHERE id=?", (_f(est.get('total_cost')), business_id))
    db.commit()
    record_operation_log(username, 'submit', 'business_cost', est['id'],
                         f"商机成本评估生效，成本合计 {_f(est.get('total_cost')):.2f} 元")
    return jsonify({'code': 200, 'message': '成本评估已生效', 'data': None})


@business_cost_bp.route('/api/business/<int:business_id>/cost/reopen', methods=['POST'])
@token_required
def reopen_cost(business_id):
    username = request.current_user['username']
    db = get_db()
    cursor = db.cursor()

    business = _get_business(cursor, business_id)
    est = _get_estimate(cursor, business_id)
    if not business or not est:
        return jsonify({'code': 404, 'message': '成本评估单不存在', 'data': None})
    if business.get('owner_id') != username:
        return jsonify({'code': 403, 'message': '仅商机负责人可重新评估', 'data': None})
    if (est.get('status') or 'draft') != 'submitted':
        return jsonify({'code': 400, 'message': '仅已生效的评估单可重新评估', 'data': None})

    cursor.execute("""
        UPDATE business_cost_estimates SET status='draft', tech_confirmed_by=NULL, tech_confirmed_at=NULL,
            submitted_by=NULL, submitted_at=NULL, updated_at=? WHERE id=?
    """, (_now(), est['id']))
    db.commit()
    record_operation_log(username, 'update', 'business_cost', est['id'], '重新评估商机成本')
    return jsonify({'code': 200, 'message': '已退回待技术确认工时', 'data': None})


@business_cost_bp.route('/api/business/cost/list', methods=['GET'])
@token_required
def list_business_costs():
    username = request.current_user['username']
    keyword = (request.args.get('keyword') or '').strip()
    db = get_db()
    cursor = db.cursor()

    sql = """
        SELECT e.id AS estimate_id, e.business_id, e.status, e.labor_hours, e.labor_cost,
               e.outsource_cost, e.other_cost, e.manage_cost, e.total_cost,
               e.tech_confirmed_by, e.tech_confirmed_at, e.submitted_by, e.submitted_at,
               e.tech_reject_reason, e.created_by, e.created_at,
               b.title, b.amount, b.stage, b.predict_date, b.owner_id,
               c.company AS customer_name, u.name AS owner_name, u.department AS owner_department
        FROM business_cost_estimates e
        JOIN business b ON e.business_id = b.id
        LEFT JOIN customers c ON b.cust_id = c.id
        LEFT JOIN users u ON b.owner_id = u.username
        WHERE 1=1
    """
    params = []
    if keyword:
        sql += " AND (b.title LIKE ? OR c.company LIKE ?)"
        params += [f'%{keyword}%', f'%{keyword}%']

    scope_all = (user_can(username, 'data.view_all') or user_can(username, 'contracts.view_all'))
    me = _get_user(cursor, username)
    if not scope_all and me:
        if me.get('role') in ('院长', '财务'):
            pass
        elif me.get('role') == '主任' and me.get('department') == TECH_DEPT:
            pass
        else:
            sql += " AND (b.owner_id = ? OR ? = 1)"
            params += [username, 1 if _is_tech_leader(cursor, username) else 0]

    sql += " ORDER BY e.updated_at DESC, e.id DESC"
    cursor.execute(sql, tuple(params))
    rows = [dict(r) for r in (cursor.fetchall() or [])]
    return jsonify({'code': 200, 'message': 'success', 'data': rows})


@business_cost_bp.route('/api/business/cost/params', methods=['GET'])
@token_required
def get_cost_params():
    return jsonify({'code': 200, 'message': 'success', 'data': {
        'month_hours': DEFAULT_MONTH_HOURS,
        'monthly_rate': DEFAULT_MONTHLY_RATE,
        'manage_rate': DEFAULT_MANAGE_RATE,
        'roles': LABOR_ROLES,
        'status_label': STATUS_LABEL,
    }})


def register_routes(app):
    app.register_blueprint(business_cost_bp)
