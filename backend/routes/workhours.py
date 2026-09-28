"""研发工时填报与审批模块。

流程：
  研发人员登录系统 → 选择项目、填写工时与工作事项（提交，状态 pending）
  → 项目经理审核（通过 approved / 退回 rejected 并填写原因）
  → 通过的工时计入项目研发工时汇总。

数据复用现有 work_hours 表，字段：
  business_id / project_type / project_id / user_id / work_date / hours /
  description / status(pending|approved|rejected) / submit_time /
  approve_time / approver_id / reject_reason

审批权限（满足任一即可）：
  - 拥有 workhour.manage 权限（主任/院长/人力）
  - 拥有 workhour.approve 权限（项目经理角色）
  - 当前用户为该商机的 project_manager
"""
from datetime import datetime

from flask import request, jsonify
from extensions import (
    get_db, token_required, require_permission, record_operation_log,
    user_can,
)
from . import workhours_bp


def register_routes(app):
    app.register_blueprint(workhours_bp, url_prefix='/api/work-hours')


def _can_approve(username, business_id):
    """判断当前用户是否有权审批某商机的工时。"""
    if user_can(username, 'workhour.manage') or user_can(username, 'workhour.approve'):
        return True
    db = get_db()
    row = db.execute(
        "SELECT project_manager FROM business WHERE id=?", (business_id,)
    ).fetchone()
    if row and row['project_manager'] and row['project_manager'] == username:
        return True
    # 角色为项目经理的用户可审批全部
    u = db.execute("SELECT role FROM users WHERE username=?", (username,)).fetchone()
    if u and u['role'] == '项目经理':
        return True
    return False


def _user_can_access_project(username, business_id):
    """判断普通用户是否可见/可填报某项目工时。

    管理员（workhour.manage）恒为 True；
    普通用户需满足：被分配到该商机、或被分配到关联该商机的合同、
    或为商机负责人/项目经理。
    """
    if user_can(username, 'workhour.manage'):
        return True
    db = get_db()
    row = db.execute(
        "SELECT owner_id, project_manager FROM business WHERE id=?", (business_id,)
    ).fetchone()
    if not row:
        return False
    if row['owner_id'] == username or row['project_manager'] == username:
        return True
    # 直接分配到商机
    assigned_biz = db.execute(
        "SELECT id FROM project_assignments "
        "WHERE project_type='business' AND project_id=? AND user_id=? LIMIT 1",
        (business_id, username)
    ).fetchone()
    if assigned_biz:
        return True
    # 分配到关联该商机的合同
    assigned_ctr = db.execute(
        "SELECT pa.id FROM project_assignments pa "
        "JOIN contracts c ON pa.project_id = c.id "
        "WHERE pa.project_type='contract' AND c.b_id=? AND pa.user_id=? LIMIT 1",
        (business_id, username)
    ).fetchone()
    return assigned_ctr is not None


def _user_can_access_contract(username, contract_id):
    """判断普通用户是否可填报某合同的工时。

    管理员恒为 True；普通用户需被分配到该合同（project_type='contract'）。
    """
    if user_can(username, 'workhour.manage'):
        return True
    db = get_db()
    assigned = db.execute(
        "SELECT id FROM project_assignments "
        "WHERE project_type='contract' AND project_id=? AND user_id=? LIMIT 1",
        (contract_id, username)
    ).fetchone()
    return assigned is not None


def _row_to_dict(row):
    item = dict(row)
    # 统一日期字段命名
    if 'work_date' in item:
        item['date'] = item['work_date']
    return item


# ============================================================
# 项目列表（供填报时选择）
# ============================================================
@workhours_bp.route('/projects', methods=['GET'])
@token_required
def list_projects():
    """返回可填报工时的项目列表（商机 + 合同）。

    权限规则（数据级隔离，在后端查询条件中实现）：
      - 管理员（workhour.manage）：可见全部活跃商机 + 执行中/已完成合同；
      - 普通用户（研发/售前等）：仅可见自己被分配到的商机或合同，
        或自己为商机负责人/项目经理的商机。
    返回字段含 ref_type（'business' | 'contract'）供前端区分。
    """
    payload = request.current_user
    db = get_db()
    keyword = request.args.get('keyword', '').strip()

    is_admin = user_can(payload['username'], 'workhour.manage')
    kw = f'%{keyword}%' if keyword else None

    # ---- 商机部分 ----
    biz_sql = """
        SELECT DISTINCT b.id AS ref_id, b.title AS name, b.stage AS stage,
               c.name AS customer_name, 'business' AS ref_type
        FROM business b
        LEFT JOIN customers c ON b.cust_id = c.id
    """
    biz_params = []
    if not is_admin:
        biz_sql += """
            LEFT JOIN project_assignments pa_biz
              ON pa_biz.project_type = 'business' AND pa_biz.project_id = b.id AND pa_biz.user_id = ?
            LEFT JOIN contracts ct ON ct.b_id = b.id
            LEFT JOIN project_assignments pa_ctr
              ON pa_ctr.project_type = 'contract' AND pa_ctr.project_id = ct.id AND pa_ctr.user_id = ?
        """
        biz_params.extend([payload['username'], payload['username']])

    biz_sql += " WHERE b.status = 'active'"
    if not is_admin:
        biz_sql += """ AND (
            pa_biz.id IS NOT NULL OR pa_ctr.id IS NOT NULL
            OR b.owner_id = ? OR b.project_manager = ?
        )"""
        biz_params.extend([payload['username'], payload['username']])
    if kw:
        biz_sql += " AND (b.title LIKE ? OR c.name LIKE ?)"
        biz_params.extend([kw, kw])
    biz_sql += " ORDER BY b.created_at DESC LIMIT 100"
    biz_rows = [dict(r) for r in db.execute(biz_sql, biz_params).fetchall()]

    # ---- 合同部分 ----
    ctr_sql = """
        SELECT DISTINCT c.id AS ref_id, c.contract_name AS name, c.status AS stage,
               cu.company AS customer_name, 'contract' AS ref_type
        FROM contracts c
        LEFT JOIN customers cu ON c.cust_id = cu.id
    """
    ctr_params = []
    if not is_admin:
        ctr_sql += """
            LEFT JOIN project_assignments pa_ctr2
              ON pa_ctr2.project_type = 'contract' AND pa_ctr2.project_id = c.id AND pa_ctr2.user_id = ?
        """
        ctr_params.append(payload['username'])

    ctr_sql += " WHERE c.status IN ('执行中', '已完成')"
    if not is_admin:
        ctr_sql += " AND pa_ctr2.id IS NOT NULL"
    else:
        # 管理员也仅看执行中/已完成的合同（已在 WHERE 中）
        pass
    if kw:
        ctr_sql += " AND (c.contract_name LIKE ? OR cu.company LIKE ?)"
        ctr_params.extend([kw, kw])
    ctr_sql += " ORDER BY c.sign_date DESC LIMIT 100"
    ctr_rows = [dict(r) for r in db.execute(ctr_sql, ctr_params).fetchall()]

    rows = biz_rows + ctr_rows
    return jsonify({'code': 200, 'message': 'success', 'data': rows})


# ============================================================
# 我的工时
# ============================================================
@workhours_bp.route('/mine', methods=['GET'])
@token_required
def list_mine():
    """当前用户填报的工时列表，可按状态/日期筛选。"""
    payload = request.current_user
    db = get_db()
    status = request.args.get('status', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    sql = """
        SELECT wh.id, wh.business_id, wh.project_type, wh.project_id,
               wh.work_date, wh.hours, wh.overtime_hours,
               wh.description, wh.status, wh.submit_time, wh.approve_time,
               wh.approver_id, wh.reject_reason,
               COALESCE(b.title, c.contract_name) AS project_name,
               ua.name AS approver_name
        FROM work_hours wh
        LEFT JOIN business b ON wh.project_type='business' AND wh.project_id = b.id
        LEFT JOIN contracts c ON wh.project_type='contract' AND wh.project_id = c.id
        LEFT JOIN users ua ON wh.approver_id = ua.username
        WHERE wh.user_id = ?
    """
    params = [payload['username']]
    if status in ('pending', 'approved', 'rejected'):
        sql += " AND wh.status = ?"
        params.append(status)
    if date_from:
        sql += " AND wh.work_date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND wh.work_date <= ?"
        params.append(date_to)
    sql += " ORDER BY wh.work_date DESC, wh.id DESC"
    rows = [_row_to_dict(r) for r in db.execute(sql, params).fetchall()]

    # 统计
    stats = {'total': len(rows), 'pending': 0, 'approved': 0, 'rejected': 0,
             'hours_approved': 0.0, 'hours_pending': 0.0}
    for r in rows:
        stats[r['status']] = stats.get(r['status'], 0) + 1
        h = float(r.get('hours') or 0)
        if r['status'] == 'approved':
            stats['hours_approved'] += h
        elif r['status'] == 'pending':
            stats['hours_pending'] += h
    stats['hours_approved'] = round(stats['hours_approved'], 2)
    stats['hours_pending'] = round(stats['hours_pending'], 2)

    return jsonify({'code': 200, 'message': 'success',
                    'data': {'items': rows, 'stats': stats}})


# ============================================================
# 全部工时（主任/院长/人力等管理员可见）
# ============================================================
@workhours_bp.route('/all', methods=['GET'])
@require_permission('workhour.manage')
def list_all():
    """全公司工时明细（管理员视图），可按人员/项目/状态/日期筛选。"""
    db = get_db()
    user_id = request.args.get('user_id', '').strip()
    business_id = request.args.get('business_id', '').strip()
    status = request.args.get('status', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    sql = """
        SELECT wh.id, wh.business_id, wh.project_type, wh.project_id,
               wh.user_id, wh.work_date, wh.hours,
               wh.overtime_hours, wh.description, wh.status, wh.submit_time,
               wh.approve_time, wh.approver_id, wh.reject_reason,
               COALESCE(b.title, c.contract_name) AS project_name,
               uu.name AS user_name, ua.name AS approver_name
        FROM work_hours wh
        LEFT JOIN business b ON wh.project_type='business' AND wh.project_id = b.id
        LEFT JOIN contracts c ON wh.project_type='contract' AND wh.project_id = c.id
        LEFT JOIN users uu ON wh.user_id = uu.username
        LEFT JOIN users ua ON wh.approver_id = ua.username
        WHERE 1=1
    """
    params = []
    if user_id:
        sql += " AND wh.user_id = ?"
        params.append(user_id)
    if business_id:
        # 兼容商机/合同：按 project_id 过滤
        sql += " AND wh.project_id = ?"
        params.append(int(business_id))
    if status in ('pending', 'approved', 'rejected'):
        sql += " AND wh.status = ?"
        params.append(status)
    if date_from:
        sql += " AND wh.work_date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND wh.work_date <= ?"
        params.append(date_to)
    sql += " ORDER BY wh.work_date DESC, wh.id DESC LIMIT 1000"
    rows = [_row_to_dict(r) for r in db.execute(sql, params).fetchall()]

    # 汇总统计
    stats = {'total': len(rows), 'pending': 0, 'approved': 0, 'rejected': 0,
             'hours_approved': 0.0, 'hours_pending': 0.0, 'hours_rejected': 0.0}
    for r in rows:
        stats[r['status']] = stats.get(r['status'], 0) + 1
        h = float(r.get('hours') or 0)
        if r['status'] == 'approved':
            stats['hours_approved'] += h
        elif r['status'] == 'pending':
            stats['hours_pending'] += h
        elif r['status'] == 'rejected':
            stats['hours_rejected'] += h
    stats['hours_approved'] = round(stats['hours_approved'], 2)
    stats['hours_pending'] = round(stats['hours_pending'], 2)
    stats['hours_rejected'] = round(stats['hours_rejected'], 2)

    # 按项目汇总已通过工时
    proj_map = {}
    for r in rows:
        if r['status'] == 'approved':
            key = r['business_id']
            if key:
                proj_map.setdefault(key, {'business_id': key,
                                          'project_name': r['project_name'], 'hours': 0.0})
                proj_map[key]['hours'] += float(r['hours'] or 0)
    project_summary = sorted(
        [{'business_id': k, 'project_name': v['project_name'],
          'hours': round(v['hours'], 2)} for k, v in proj_map.items()],
        key=lambda x: x['hours'], reverse=True
    )

    return jsonify({'code': 200, 'message': 'success',
                    'data': {'items': rows, 'stats': stats,
                             'project_summary': project_summary}})


@workhours_bp.route('/users', methods=['GET'])
@token_required
def list_reporters():
    """有工时填报记录的人员列表（供筛选下拉，不返回敏感信息）。"""
    db = get_db()
    rows = db.execute("""
        SELECT DISTINCT wh.user_id, uu.name
        FROM work_hours wh
        LEFT JOIN users uu ON wh.user_id = uu.username
        ORDER BY uu.name
    """).fetchall()
    data = [{'username': r['user_id'], 'name': r['name'] or r['user_id']}
            for r in rows]
    return jsonify({'code': 200, 'message': 'success', 'data': data})


# ============================================================
# 填报 / 编辑 / 删除
# ============================================================
@workhours_bp.route('', methods=['POST'])
@token_required
def submit():
    """研发人员提交一条工时记录（状态 pending）。

    body.ref_type: 'business'（默认）或 'contract'
    body.ref_id: 商机ID 或 合同ID（兼容旧字段 business_id）
    """
    payload = request.current_user
    body = request.get_json(silent=True) or {}
    ref_type = (body.get('ref_type') or 'business').strip()
    ref_id = body.get('ref_id') or body.get('business_id')
    work_date = (body.get('work_date') or '').strip()
    hours = body.get('hours')
    description = (body.get('description') or '').strip()
    overtime_hours = body.get('overtime_hours') or 0

    try:
        ref_id = int(ref_id)
    except (TypeError, ValueError):
        return jsonify({'code': 400, 'message': '请选择项目', 'data': None})
    if ref_type not in ('business', 'contract'):
        return jsonify({'code': 400, 'message': '项目类型错误', 'data': None})
    if not work_date:
        return jsonify({'code': 400, 'message': '请选择工作日期', 'data': None})
    try:
        hours = float(hours)
        if hours <= 0 or hours > 24:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({'code': 400, 'message': '工时必须为 0~24 之间的数字', 'data': None})
    if not description:
        return jsonify({'code': 400, 'message': '请填写工作事项', 'data': None})

    try:
        overtime_hours = float(overtime_hours)
        if overtime_hours < 0:
            overtime_hours = 0
    except (TypeError, ValueError):
        overtime_hours = 0

    db = get_db()
    if ref_type == 'contract':
        ctr = db.execute(
            "SELECT id, b_id, contract_name FROM contracts WHERE id=? AND status IN ('执行中','已完成')",
            (ref_id,)
        ).fetchone()
        if not ctr:
            return jsonify({'code': 400, 'message': '所选合同不存在或未执行', 'data': None})
        if not _user_can_access_contract(payload['username'], ref_id):
            return jsonify({'code': 403, 'message': '您未被分配到该合同，无法填报工时', 'data': None})
        business_id = ctr['b_id'] or None
        project_id = ref_id
    else:
        biz = db.execute("SELECT id FROM business WHERE id=? AND status='active'",
                         (ref_id,)).fetchone()
        if not biz:
            return jsonify({'code': 400, 'message': '所选项目不存在或已关闭', 'data': None})
        if not _user_can_access_project(payload['username'], ref_id):
            return jsonify({'code': 403, 'message': '您未被分配到该项目，无法填报工时', 'data': None})
        business_id = ref_id
        project_id = ref_id

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cur = db.execute("""
        INSERT INTO work_hours
            (business_id, project_type, project_id, user_id, work_date,
             hours, overtime_hours, description, status, submit_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
    """, (business_id, ref_type, project_id, payload['username'], work_date,
          round(hours, 2), round(overtime_hours, 2), description, now))
    db.commit()
    ref_label = '合同' if ref_type == 'contract' else '商机'
    record_operation_log(
        payload['username'], '提交', '研发工时',
        f'提交 {work_date} 工时 {hours} 小时（{ref_label}ID {ref_id}）')
    return jsonify({'code': 200, 'message': '工时已提交，等待项目经理审核',
                    'data': {'id': cur.lastrowid}})


@workhours_bp.route('/<int:wh_id>', methods=['PUT'])
@token_required
def update(wh_id):
    """编辑本人 pending 状态的工时。"""
    payload = request.current_user
    body = request.get_json(silent=True) or {}
    db = get_db()
    row = db.execute("SELECT * FROM work_hours WHERE id=?", (wh_id,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '记录不存在', 'data': None})
    if row['user_id'] != payload['username']:
        return jsonify({'code': 403, 'message': '只能编辑本人的工时', 'data': None})
    if row['status'] != 'pending':
        return jsonify({'code': 400, 'message': '仅待审核状态可编辑', 'data': None})

    ref_type = (body.get('ref_type') or row['project_type'] or 'business').strip()
    ref_id = body.get('ref_id') or body.get('business_id', row['project_id'])
    work_date = (body.get('work_date') or row['work_date'] or '').strip()
    hours = body.get('hours', row['hours'])
    description = (body.get('description') or row['description'] or '').strip()
    overtime_hours = body.get('overtime_hours', row['overtime_hours'] or 0)

    try:
        ref_id = int(ref_id)
    except (TypeError, ValueError):
        return jsonify({'code': 400, 'message': '请选择项目', 'data': None})
    if ref_type not in ('business', 'contract'):
        return jsonify({'code': 400, 'message': '项目类型错误', 'data': None})
    if not work_date:
        return jsonify({'code': 400, 'message': '请选择工作日期', 'data': None})
    try:
        hours = float(hours)
        if hours <= 0 or hours > 24:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({'code': 400, 'message': '工时必须为 0~24 之间的数字', 'data': None})
    if not description:
        return jsonify({'code': 400, 'message': '请填写工作事项', 'data': None})
    try:
        overtime_hours = float(overtime_hours)
        if overtime_hours < 0:
            overtime_hours = 0
    except (TypeError, ValueError):
        overtime_hours = 0

    if ref_type == 'contract':
        ctr = db.execute(
            "SELECT id, b_id FROM contracts WHERE id=? AND status IN ('执行中','已完成')",
            (ref_id,)
        ).fetchone()
        if not ctr:
            return jsonify({'code': 400, 'message': '所选合同不存在或未执行', 'data': None})
        if not _user_can_access_contract(payload['username'], ref_id):
            return jsonify({'code': 403, 'message': '您未被分配到该合同，无法填报工时', 'data': None})
        business_id = ctr['b_id'] or None
        project_id = ref_id
    else:
        biz = db.execute("SELECT id FROM business WHERE id=? AND status='active'",
                         (ref_id,)).fetchone()
        if not biz:
            return jsonify({'code': 400, 'message': '所选项目不存在或已关闭', 'data': None})
        if not _user_can_access_project(payload['username'], ref_id):
            return jsonify({'code': 403, 'message': '您未被分配到该项目，无法填报工时', 'data': None})
        business_id = ref_id
        project_id = ref_id

    db.execute("""
        UPDATE work_hours SET business_id=?, project_type=?, project_id=?,
            work_date=?, hours=?, overtime_hours=?, description=?
        WHERE id=? AND status='pending'
    """, (business_id, ref_type, project_id, work_date, round(hours, 2),
          round(overtime_hours, 2), description, wh_id))
    db.commit()
    record_operation_log(payload['username'], '编辑', '研发工时', f'编辑工时 #{wh_id}')
    return jsonify({'code': 200, 'message': '已更新', 'data': None})


@workhours_bp.route('/<int:wh_id>', methods=['DELETE'])
@token_required
def delete(wh_id):
    """删除本人 pending 状态的工时。"""
    payload = request.current_user
    db = get_db()
    row = db.execute("SELECT * FROM work_hours WHERE id=?", (wh_id,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '记录不存在', 'data': None})
    if row['user_id'] != payload['username']:
        return jsonify({'code': 403, 'message': '只能删除本人的工时', 'data': None})
    if row['status'] != 'pending':
        return jsonify({'code': 400, 'message': '仅待审核状态可删除', 'data': None})
    db.execute("DELETE FROM work_hours WHERE id=?", (wh_id,))
    db.commit()
    record_operation_log(payload['username'], '删除', '研发工时', f'删除工时 #{wh_id}')
    return jsonify({'code': 200, 'message': '已删除', 'data': None})


# ============================================================
# 项目经理审批
# ============================================================
@workhours_bp.route('/pending', methods=['GET'])
@token_required
def list_pending():
    """待审批工时列表（项目经理 / 有审批权限者可见全部待审）。"""
    payload = request.current_user
    if not (user_can(payload['username'], 'workhour.manage') or
            user_can(payload['username'], 'workhour.approve')):
        u = get_db().execute(
            "SELECT role FROM users WHERE username=?", (payload['username'],)
        ).fetchone()
        if not (u and u['role'] == '项目经理'):
            return jsonify({'code': 403, 'message': '无审批权限', 'data': None})

    db = get_db()
    rows = db.execute("""
        SELECT wh.id, wh.business_id, wh.project_type, wh.project_id,
               wh.user_id, wh.work_date, wh.hours,
               wh.overtime_hours, wh.description, wh.status, wh.submit_time,
               COALESCE(b.title, c.contract_name) AS project_name,
               uu.name AS user_name
        FROM work_hours wh
        LEFT JOIN business b ON wh.project_type='business' AND wh.project_id = b.id
        LEFT JOIN contracts c ON wh.project_type='contract' AND wh.project_id = c.id
        LEFT JOIN users uu ON wh.user_id = uu.username
        WHERE wh.status = 'pending'
        ORDER BY wh.submit_time ASC
    """).fetchall()
    data = [_row_to_dict(r) for r in rows]
    return jsonify({'code': 200, 'message': 'success',
                    'data': {'items': data, 'count': len(data)}})


@workhours_bp.route('/<int:wh_id>/approve', methods=['POST'])
@token_required
def approve(wh_id):
    """审批通过。"""
    payload = request.current_user
    db = get_db()
    row = db.execute("SELECT * FROM work_hours WHERE id=?", (wh_id,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '记录不存在', 'data': None})
    if row['status'] != 'pending':
        return jsonify({'code': 400, 'message': '该记录非待审核状态', 'data': None})
    if not _can_approve(payload['username'], row['business_id']):
        return jsonify({'code': 403, 'message': '无权审批该项目工时', 'data': None})

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.execute("""
        UPDATE work_hours SET status='approved', approver_id=?, approve_time=?,
            reject_reason=NULL WHERE id=?
    """, (payload['username'], now, wh_id))
    db.commit()
    record_operation_log(
        payload['username'], '审批通过', '研发工时',
        f'通过工时 #{wh_id}（{row["work_date"]} {row["hours"]}小时）')
    return jsonify({'code': 200, 'message': '已通过', 'data': None})


@workhours_bp.route('/<int:wh_id>/reject', methods=['POST'])
@token_required
def reject(wh_id):
    """审批退回（需填写原因）。"""
    payload = request.current_user
    body = request.get_json(silent=True) or {}
    reason = (body.get('reason') or '').strip()
    if not reason:
        return jsonify({'code': 400, 'message': '请填写退回原因', 'data': None})

    db = get_db()
    row = db.execute("SELECT * FROM work_hours WHERE id=?", (wh_id,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '记录不存在', 'data': None})
    if row['status'] != 'pending':
        return jsonify({'code': 400, 'message': '该记录非待审核状态', 'data': None})
    if not _can_approve(payload['username'], row['business_id']):
        return jsonify({'code': 403, 'message': '无权审批该项目工时', 'data': None})

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.execute("""
        UPDATE work_hours SET status='rejected', approver_id=?, approve_time=?,
            reject_reason=? WHERE id=?
    """, (payload['username'], now, reason, wh_id))
    db.commit()
    record_operation_log(
        payload['username'], '审批退回', '研发工时',
        f'退回工时 #{wh_id}，原因：{reason}')
    return jsonify({'code': 200, 'message': '已退回', 'data': None})


# ============================================================
# 项目研发工时汇总
# ============================================================
@workhours_bp.route('/project/<int:business_id>', methods=['GET'])
@token_required
def project_detail(business_id):
    """某项目的研发工时明细与汇总（通过的工时计入项目研发工时）。"""
    db = get_db()
    biz = db.execute("""
        SELECT b.id, b.title, b.stage, b.project_manager,
               c.name AS customer_name
        FROM business b
        LEFT JOIN customers c ON b.cust_id = c.id
        WHERE b.id=?
    """, (business_id,)).fetchone()
    if not biz:
        return jsonify({'code': 404, 'message': '项目不存在', 'data': None})

    entries = db.execute("""
        SELECT wh.id, wh.user_id, wh.work_date, wh.hours, wh.overtime_hours,
               wh.description, wh.status, wh.submit_time, wh.approve_time,
               wh.approver_id, wh.reject_reason,
               uu.name AS user_name, ua.name AS approver_name
        FROM work_hours wh
        LEFT JOIN users uu ON wh.user_id = uu.username
        LEFT JOIN users ua ON wh.approver_id = ua.username
        WHERE wh.business_id=?
        ORDER BY wh.work_date DESC, wh.id DESC
    """, (business_id,)).fetchall()
    items = [_row_to_dict(r) for r in entries]

    total_approved = round(sum(float(i['hours'] or 0) for i in items if i['status'] == 'approved'), 2)
    total_pending = round(sum(float(i['hours'] or 0) for i in items if i['status'] == 'pending'), 2)
    total_rejected = round(sum(float(i['hours'] or 0) for i in items if i['status'] == 'rejected'), 2)

    # 按人员汇总已通过工时
    by_user = {}
    for i in items:
        if i['status'] == 'approved':
            key = i['user_id']
            by_user.setdefault(key, {'user_id': key, 'user_name': i['user_name'], 'hours': 0.0})
            by_user[key]['hours'] += float(i['hours'] or 0)
    user_summary = [
        {'user_id': k, 'user_name': v['user_name'], 'hours': round(v['hours'], 2)}
        for k, v in by_user.items()
    ]
    user_summary.sort(key=lambda x: x['hours'], reverse=True)

    return jsonify({'code': 200, 'message': 'success', 'data': {
        'project': dict(biz),
        'items': items,
        'summary': {
            'total_approved': total_approved,
            'total_pending': total_pending,
            'total_rejected': total_rejected,
            'entry_count': len(items),
        },
        'user_summary': user_summary,
    }})


@workhours_bp.route('/contract/<int:contract_id>', methods=['GET'])
@token_required
def contract_detail(contract_id):
    """某合同的研发工时明细与汇总。"""
    db = get_db()
    ctr = db.execute("""
        SELECT c.id, c.contract_name AS title, c.status, c.owner_id,
               cu.company AS customer_name
        FROM contracts c
        LEFT JOIN customers cu ON c.cust_id = cu.id
        WHERE c.id=?
    """, (contract_id,)).fetchone()
    if not ctr:
        return jsonify({'code': 404, 'message': '合同不存在', 'data': None})

    entries = db.execute("""
        SELECT wh.id, wh.user_id, wh.work_date, wh.hours, wh.overtime_hours,
               wh.description, wh.status, wh.submit_time, wh.approve_time,
               wh.approver_id, wh.reject_reason,
               uu.name AS user_name, ua.name AS approver_name
        FROM work_hours wh
        LEFT JOIN users uu ON wh.user_id = uu.username
        LEFT JOIN users ua ON wh.approver_id = ua.username
        WHERE wh.project_type='contract' AND wh.project_id=?
        ORDER BY wh.work_date DESC, wh.id DESC
    """, (contract_id,)).fetchall()
    items = [_row_to_dict(r) for r in entries]

    total_approved = round(sum(float(i['hours'] or 0) for i in items if i['status'] == 'approved'), 2)
    total_pending = round(sum(float(i['hours'] or 0) for i in items if i['status'] == 'pending'), 2)
    total_rejected = round(sum(float(i['hours'] or 0) for i in items if i['status'] == 'rejected'), 2)

    by_user = {}
    for i in items:
        if i['status'] == 'approved':
            key = i['user_id']
            by_user.setdefault(key, {'user_id': key, 'user_name': i['user_name'], 'hours': 0.0})
            by_user[key]['hours'] += float(i['hours'] or 0)
    user_summary = [
        {'user_id': k, 'user_name': v['user_name'], 'hours': round(v['hours'], 2)}
        for k, v in by_user.items()
    ]
    user_summary.sort(key=lambda x: x['hours'], reverse=True)

    return jsonify({'code': 200, 'message': 'success', 'data': {
        'project': dict(ctr),
        'items': items,
        'summary': {
            'total_approved': total_approved,
            'total_pending': total_pending,
            'total_rejected': total_rejected,
            'entry_count': len(items),
        },
        'user_summary': user_summary,
    }})


@workhours_bp.route('/projects-summary', methods=['GET'])
@token_required
def projects_summary():
    """所有活跃项目的研发工时汇总（供项目列表页展示研发工时列）。

    ref_type=business（默认）：商机；ref_type=contract：合同。
    """
    ref_type = request.args.get('ref_type', 'business').strip()
    db = get_db()
    if ref_type == 'contract':
        rows = db.execute("""
            SELECT c.id AS contract_id, c.contract_name AS title,
                   COALESCE(SUM(CASE WHEN wh.status='approved' THEN wh.hours ELSE 0 END), 0) AS approved_hours,
                   COALESCE(SUM(CASE WHEN wh.status='pending' THEN wh.hours ELSE 0 END), 0) AS pending_hours,
                   COUNT(wh.id) AS entry_count
            FROM contracts c
            LEFT JOIN work_hours wh ON wh.project_type='contract' AND wh.project_id = c.id
            WHERE c.status IN ('执行中', '已完成')
            GROUP BY c.id
        """).fetchall()
    else:
        rows = db.execute("""
            SELECT b.id AS business_id, b.title,
                   COALESCE(SUM(CASE WHEN wh.status='approved' THEN wh.hours ELSE 0 END), 0) AS approved_hours,
                   COALESCE(SUM(CASE WHEN wh.status='pending' THEN wh.hours ELSE 0 END), 0) AS pending_hours,
                   COUNT(wh.id) AS entry_count
            FROM business b
            LEFT JOIN work_hours wh ON wh.business_id = b.id
            WHERE b.status = 'active'
            GROUP BY b.id
        """).fetchall()
    data = []
    for r in rows:
        d = dict(r)
        d['approved_hours'] = round(float(d['approved_hours'] or 0), 2)
        d['pending_hours'] = round(float(d['pending_hours'] or 0), 2)
        data.append(d)
    return jsonify({'code': 200, 'message': 'success', 'data': data})


# ============================================================
# 项目成员分配管理
# ============================================================
def _can_manage_assignment(username, ref_type, ref_id):
    """判断用户是否可管理某项目的成员分配。

    管理员（workhour.manage）恒为 True；
    商机：负责人或项目经理可管理；
    合同：合同负责人（owner_id）可管理。
    """
    if user_can(username, 'workhour.manage'):
        return True
    db = get_db()
    if ref_type == 'contract':
        row = db.execute("SELECT owner_id FROM contracts WHERE id=?", (ref_id,)).fetchone()
        return row is not None and row['owner_id'] == username
    else:
        row = db.execute(
            "SELECT owner_id, project_manager FROM business WHERE id=?", (ref_id,)
        ).fetchone()
        if not row:
            return False
        return row['owner_id'] == username or row['project_manager'] == username


@workhours_bp.route('/projects/<int:ref_id>/assignments', methods=['GET'])
@token_required
def list_assignments(ref_id):
    """获取某项目（商机/合同）的已分配成员列表。"""
    ref_type = request.args.get('ref_type', 'business').strip()
    if ref_type not in ('business', 'contract'):
        return jsonify({'code': 400, 'message': 'ref_type 错误', 'data': None})
    db = get_db()
    rows = db.execute("""
        SELECT pa.id, pa.user_id, pa.assigned_by, pa.assigned_at,
               u.name AS user_name, u.role, u.department
        FROM project_assignments pa
        LEFT JOIN users u ON pa.user_id = u.username
        WHERE pa.project_type=? AND pa.project_id=?
        ORDER BY pa.assigned_at
    """, (ref_type, ref_id)).fetchall()
    data = [dict(r) for r in rows]
    return jsonify({'code': 200, 'message': 'success', 'data': data})


@workhours_bp.route('/projects/<int:ref_id>/assignments', methods=['POST'])
@token_required
def add_assignments(ref_id):
    """批量分配成员到项目（body: {ref_type, user_ids}，已存在则跳过）。"""
    payload = request.current_user
    body = request.get_json(silent=True) or {}
    ref_type = body.get('ref_type', 'business')
    user_ids = body.get('user_ids') or []
    if ref_type not in ('business', 'contract'):
        return jsonify({'code': 400, 'message': 'ref_type 错误', 'data': None})
    if not _can_manage_assignment(payload['username'], ref_type, ref_id):
        return jsonify({'code': 403, 'message': '无权分配该项目成员', 'data': None})

    db = get_db()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    added = 0
    for uid in user_ids:
        uid = str(uid).strip()
        if not uid:
            continue
        exists = db.execute(
            "SELECT id FROM project_assignments WHERE project_type=? AND project_id=? AND user_id=?",
            (ref_type, ref_id, uid)
        ).fetchone()
        if exists:
            continue
        db.execute(
            "INSERT INTO project_assignments (project_type, project_id, user_id, assigned_by, assigned_at) "
            "VALUES (?,?,?,?,?)",
            (ref_type, ref_id, uid, payload['username'], now)
        )
        added += 1
    db.commit()
    record_operation_log(
        payload['username'], '分配', '项目成员',
        f'向 {ref_type}#{ref_id} 分配 {added} 名成员')
    return jsonify({'code': 200, 'message': f'已分配 {added} 名成员', 'data': {'added': added}})


@workhours_bp.route('/projects/<int:ref_id>/assignments/<user_id>', methods=['DELETE'])
@token_required
def remove_assignment(ref_id, user_id):
    """移除项目中的某个成员。"""
    payload = request.current_user
    ref_type = request.args.get('ref_type', 'business').strip()
    if ref_type not in ('business', 'contract'):
        return jsonify({'code': 400, 'message': 'ref_type 错误', 'data': None})
    if not _can_manage_assignment(payload['username'], ref_type, ref_id):
        return jsonify({'code': 403, 'message': '无权操作', 'data': None})

    db = get_db()
    db.execute(
        "DELETE FROM project_assignments WHERE project_type=? AND project_id=? AND user_id=?",
        (ref_type, ref_id, user_id)
    )
    db.commit()
    record_operation_log(
        payload['username'], '移除', '项目成员',
        f'从 {ref_type}#{ref_id} 移除成员 {user_id}')
    return jsonify({'code': 200, 'message': '已移除', 'data': None})
