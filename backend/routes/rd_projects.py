"""自研项目（自主研发项目）管理。

功能范围：
  - 立项台账：项目基本信息、负责人、成员、预算、起止时间、状态
  - 里程碑计划与完成情况（完成比例自动折算项目进度）
  - 成果物登记（文档 / 专利 / 软著 / 样机等）
  - 工时联动：rd_projects 作为 work_hours.ref_type='rd' 的项目来源

权限：
  - 查看：所有登录用户
  - 新建 / 编辑 / 删除 / 里程碑 / 成果物：主任、院长、具备 data.view_all 或
    workhour.manage 权限的管理人员，以及该项目负责人本人
"""
from datetime import datetime

from flask import request, jsonify

from extensions import get_db, record_operation_log, token_required, user_can
from . import rd_projects_bp


STATUS_LIST = ['筹备中', '进行中', '已结项', '已终止']
DELIVERABLE_TYPES = ['文档', '专利', '软著', '样机', '其它']


# ------------------------------------------------------------
# 建表（幂等）
# ------------------------------------------------------------
DDL = [
    """
    CREATE TABLE IF NOT EXISTS rd_projects (
        id INT AUTO_INCREMENT PRIMARY KEY,
        code VARCHAR(64) DEFAULT '',
        name VARCHAR(255) NOT NULL,
        category VARCHAR(64) DEFAULT '',
        objective TEXT,
        owner_id VARCHAR(64) DEFAULT '',
        owner_name VARCHAR(64) DEFAULT '',
        department VARCHAR(64) DEFAULT '',
        budget DECIMAL(14,2) DEFAULT 0,
        start_date VARCHAR(20) DEFAULT '',
        end_date VARCHAR(20) DEFAULT '',
        status VARCHAR(20) DEFAULT '筹备中',
        progress INT DEFAULT 0,
        remark TEXT,
        created_by VARCHAR(64) DEFAULT '',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        KEY idx_rd_projects_status (status),
        KEY idx_rd_projects_owner (owner_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS rd_project_members (
        id INT AUTO_INCREMENT PRIMARY KEY,
        project_id INT NOT NULL,
        username VARCHAR(64) NOT NULL,
        UNIQUE KEY uk_rd_member (project_id, username),
        KEY idx_rd_member_user (username)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS rd_milestones (
        id INT AUTO_INCREMENT PRIMARY KEY,
        project_id INT NOT NULL,
        name VARCHAR(255) NOT NULL,
        plan_date VARCHAR(20) DEFAULT '',
        actual_date VARCHAR(20) DEFAULT '',
        owner VARCHAR(64) DEFAULT '',
        status VARCHAR(20) DEFAULT 'pending',
        remark TEXT,
        sort_no INT DEFAULT 0,
        KEY idx_rd_ms_project (project_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS rd_deliverables (
        id INT AUTO_INCREMENT PRIMARY KEY,
        project_id INT NOT NULL,
        name VARCHAR(255) NOT NULL,
        dtype VARCHAR(32) DEFAULT '文档',
        deliver_date VARCHAR(20) DEFAULT '',
        remark TEXT,
        KEY idx_rd_dv_project (project_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """,
]


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _is_manager(username):
    """是否具备自研项目的全局管理权限。"""
    if user_can(username, 'data.view_all') or user_can(username, 'workhour.manage'):
        return True
    db = get_db()
    row = db.execute("SELECT role FROM users WHERE username=?", (username,)).fetchone()
    return bool(row and row['role'] in ('主任', '院长'))


def _can_edit(username, project):
    if not project:
        return False
    if _is_manager(username):
        return True
    return bool(project.get('owner_id') and project['owner_id'] == username)


def _get_project(db, pid):
    row = db.execute("SELECT * FROM rd_projects WHERE id=?", (pid,)).fetchone()
    return dict(row) if row else None


def _recalc_progress(db, project_id):
    """按里程碑完成比例折算项目进度；无里程碑时保持手工进度。"""
    stat = db.execute(
        "SELECT COUNT(*) AS total, SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) AS done "
        "FROM rd_milestones WHERE project_id=?", (project_id,)
    ).fetchone()
    total = int(stat['total'] or 0) if stat else 0
    if total <= 0:
        return
    done = int(stat['done'] or 0)
    progress = int(round(done * 100.0 / total))
    db.execute("UPDATE rd_projects SET progress=? WHERE id=?", (progress, project_id))


def _load_members(db, project_ids):
    if not project_ids:
        return {}
    ph = ','.join(['?'] * len(project_ids))
    rows = db.execute(
        f"SELECT m.project_id, m.username, u.name FROM rd_project_members m "
        f"LEFT JOIN users u ON u.username = m.username "
        f"WHERE m.project_id IN ({ph})", list(project_ids)
    ).fetchall()
    result = {}
    for r in rows:
        result.setdefault(r['project_id'], []).append({
            'username': r['username'], 'name': r['name'] or r['username'],
        })
    return result


# ------------------------------------------------------------
# 列表 / 详情
# ------------------------------------------------------------
@rd_projects_bp.route('/api/rd-projects', methods=['GET'])
@token_required
def list_projects():
    payload = request.current_user
    db = get_db()
    keyword = (request.args.get('keyword') or '').strip()
    status = (request.args.get('status') or '').strip()
    mine = request.args.get('mine') == '1'

    sql = "SELECT * FROM rd_projects WHERE 1=1"
    params = []
    if keyword:
        sql += " AND (name LIKE ? OR code LIKE ? OR owner_name LIKE ?)"
        params.extend([f'%{keyword}%'] * 3)
    if status and status in STATUS_LIST:
        sql += " AND status = ?"
        params.append(status)
    if mine:
        sql += " AND (owner_id = ? OR id IN (SELECT project_id FROM rd_project_members WHERE username = ?))"
        params.extend([payload['username'], payload['username']])
    sql += " ORDER BY CASE status WHEN '进行中' THEN 0 WHEN '筹备中' THEN 1 WHEN '已结项' THEN 2 ELSE 3 END, id DESC"

    rows = [dict(r) for r in db.execute(sql, params).fetchall()]
    members = _load_members(db, [r['id'] for r in rows])
    for r in rows:
        r['budget'] = float(r['budget'] or 0)
        r['progress'] = int(r['progress'] or 0)
        r['members'] = members.get(r['id'], [])
        r['member_names'] = '、'.join(m['name'] for m in r['members'])

    stats = {
        'total': len(rows),
        'running': len([r for r in rows if r['status'] == '进行中']),
        'preparing': len([r for r in rows if r['status'] == '筹备中']),
        'finished': len([r for r in rows if r['status'] == '已结项']),
        'budget_total': round(sum(r['budget'] for r in rows), 2),
    }
    return jsonify({'code': 200, 'message': 'success',
                    'data': {'items': rows, 'stats': stats, 'can_manage': _is_manager(payload['username'])}})


@rd_projects_bp.route('/api/rd-projects/<int:pid>', methods=['GET'])
@token_required
def project_detail(pid):
    payload = request.current_user
    db = get_db()
    project = _get_project(db, pid)
    if not project:
        return jsonify({'code': 404, 'message': '项目不存在', 'data': None})

    project['budget'] = float(project['budget'] or 0)
    project['progress'] = int(project['progress'] or 0)
    project['members'] = _load_members(db, [pid]).get(pid, [])
    project['member_names'] = '、'.join(m['name'] for m in project['members'])

    project['milestones'] = [dict(r) for r in db.execute(
        "SELECT * FROM rd_milestones WHERE project_id=? ORDER BY sort_no, id", (pid,)
    ).fetchall()]
    project['deliverables'] = [dict(r) for r in db.execute(
        "SELECT * FROM rd_deliverables WHERE project_id=? ORDER BY deliver_date, id", (pid,)
    ).fetchall()]

    # 工时汇总（work_hours.project_type='rd'）
    wh = db.execute("""
        SELECT COUNT(*) AS records, COALESCE(SUM(hours), 0) AS hours,
               COALESCE(SUM(CASE WHEN status='approved' THEN hours ELSE 0 END), 0) AS hours_approved,
               COALESCE(SUM(CASE WHEN status='pending' THEN hours ELSE 0 END), 0) AS hours_pending
        FROM work_hours WHERE project_type='rd' AND project_id=?
    """, (pid,)).fetchone()
    project['workhours'] = {
        'records': int(wh['records'] or 0),
        'hours': round(float(wh['hours'] or 0), 2),
        'hours_approved': round(float(wh['hours_approved'] or 0), 2),
        'hours_pending': round(float(wh['hours_pending'] or 0), 2),
    }
    project['workhour_members'] = [
        {'user_id': r['user_id'], 'user_name': r['user_name'],
         'hours': round(float(r['hours'] or 0), 2)}
        for r in db.execute("""
            SELECT wh.user_id, COALESCE(u.name, wh.user_id) AS user_name, SUM(wh.hours) AS hours
            FROM work_hours wh LEFT JOIN users u ON u.username = wh.user_id
            WHERE wh.project_type='rd' AND wh.project_id=? AND wh.status='approved'
            GROUP BY wh.user_id, u.name ORDER BY hours DESC
        """, (pid,)).fetchall()
    ]

    project['can_edit'] = _can_edit(payload['username'], project)
    return jsonify({'code': 200, 'message': 'success', 'data': project})


# ------------------------------------------------------------
# 新建 / 编辑 / 删除
# ------------------------------------------------------------
def _save_members(db, pid, usernames):
    db.execute("DELETE FROM rd_project_members WHERE project_id=?", (pid,))
    for uname in usernames or []:
        uname = (uname or '').strip()
        if uname:
            db.execute(
                "INSERT IGNORE INTO rd_project_members (project_id, username) VALUES (?, ?)",
                (pid, uname)
            )


def _owner_name(db, username):
    if not username:
        return '', ''
    row = db.execute("SELECT name, department FROM users WHERE username=?", (username,)).fetchone()
    if not row:
        return username, ''
    return row['name'] or username, row['department'] or ''


@rd_projects_bp.route('/api/rd-projects', methods=['POST'])
@token_required
def create_project():
    payload = request.current_user
    if not _is_manager(payload['username']):
        return jsonify({'code': 403, 'message': '无权新建自研项目', 'data': None})
    body = request.get_json(silent=True) or {}
    name = (body.get('name') or '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '请填写项目名称', 'data': None})

    status = body.get('status') or '筹备中'
    if status not in STATUS_LIST:
        status = '筹备中'

    owner_id = (body.get('owner_id') or payload['username']).strip()
    owner_name, department = _owner_name(get_db(), owner_id)

    db = get_db()
    try:
        budget = float(body.get('budget') or 0)
    except (TypeError, ValueError):
        budget = 0.0

    cur = db.execute("""
        INSERT INTO rd_projects
            (code, name, category, objective, owner_id, owner_name, department,
             budget, start_date, end_date, status, progress, remark, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        (body.get('code') or '').strip(), name, (body.get('category') or '').strip(),
        (body.get('objective') or '').strip(), owner_id, owner_name,
        (body.get('department') or department or '').strip(), round(budget, 2),
        (body.get('start_date') or '').strip(), (body.get('end_date') or '').strip(),
        status, int(body.get('progress') or 0), (body.get('remark') or '').strip(),
        payload['username'],
    ))
    pid = cur.lastrowid
    _save_members(db, pid, body.get('member_ids') or [])
    _recalc_progress(db, pid)
    db.commit()

    record_operation_log(payload['username'], '新建', '自研项目', f'新建自研项目：{name}（ID {pid}）')
    return jsonify({'code': 200, 'message': '创建成功', 'data': {'id': pid}})


@rd_projects_bp.route('/api/rd-projects/<int:pid>', methods=['PUT'])
@token_required
def update_project(pid):
    payload = request.current_user
    db = get_db()
    project = _get_project(db, pid)
    if not project:
        return jsonify({'code': 404, 'message': '项目不存在', 'data': None})
    if not _can_edit(payload['username'], project):
        return jsonify({'code': 403, 'message': '无权编辑该项目', 'data': None})

    body = request.get_json(silent=True) or {}
    fields, params = [], []

    def add(col, key, transform=None):
        if key in body:
            val = body.get(key)
            if transform:
                val = transform(val)
            fields.append(f"{col}=?")
            params.append(val)

    add('code', 'code', lambda v: (v or '').strip())
    add('name', 'name', lambda v: (v or '').strip())
    add('category', 'category', lambda v: (v or '').strip())
    add('objective', 'objective', lambda v: (v or '').strip())
    add('budget', 'budget', lambda v: round(float(v or 0), 2))
    add('start_date', 'start_date', lambda v: (v or '').strip())
    add('end_date', 'end_date', lambda v: (v or '').strip())
    add('progress', 'progress', lambda v: max(0, min(100, int(v or 0))))
    add('remark', 'remark', lambda v: (v or '').strip())
    if 'status' in body and body['status'] in STATUS_LIST:
        fields.append('status=?')
        params.append(body['status'])
    if 'owner_id' in body:
        owner_id = (body.get('owner_id') or '').strip()
        owner_name, department = _owner_name(db, owner_id)
        fields.extend(['owner_id=?', 'owner_name=?'])
        params.extend([owner_id, owner_name])
        if department and 'department' not in body:
            fields.append('department=?')
            params.append(department)
    add('department', 'department', lambda v: (v or '').strip())

    # 名称必填校验
    if 'name' in body and not (body.get('name') or '').strip():
        return jsonify({'code': 400, 'message': '项目名称不能为空', 'data': None})

    try:
        if fields:
            params.append(pid)
            db.execute(f"UPDATE rd_projects SET {', '.join(fields)} WHERE id=?", params)
        if 'member_ids' in body:
            _save_members(db, pid, body.get('member_ids') or [])
        _recalc_progress(db, pid)
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})

    record_operation_log(payload['username'], '编辑', '自研项目',
                         f'编辑自研项目：{project["name"]}（ID {pid}）')
    return jsonify({'code': 200, 'message': '保存成功', 'data': None})


@rd_projects_bp.route('/api/rd-projects/<int:pid>', methods=['DELETE'])
@token_required
def delete_project(pid):
    payload = request.current_user
    db = get_db()
    project = _get_project(db, pid)
    if not project:
        return jsonify({'code': 404, 'message': '项目不存在', 'data': None})
    if not _can_edit(payload['username'], project):
        return jsonify({'code': 403, 'message': '无权删除该项目', 'data': None})

    used = db.execute(
        "SELECT COUNT(*) AS c FROM work_hours WHERE project_type='rd' AND project_id=?",
        (pid,)
    ).fetchone()
    if used and int(used['c'] or 0) > 0:
        return jsonify({'code': 400,
                        'message': f'该项目已关联 {used["c"]} 条工时记录，不能删除；可将状态改为「已终止」',
                        'data': None})

    db.execute("DELETE FROM rd_milestones WHERE project_id=?", (pid,))
    db.execute("DELETE FROM rd_deliverables WHERE project_id=?", (pid,))
    db.execute("DELETE FROM rd_project_members WHERE project_id=?", (pid,))
    db.execute("DELETE FROM rd_projects WHERE id=?", (pid,))
    db.commit()

    record_operation_log(payload['username'], '删除', '自研项目',
                         f'删除自研项目：{project["name"]}（ID {pid}）')
    return jsonify({'code': 200, 'message': '已删除', 'data': None})


# ------------------------------------------------------------
# 里程碑
# ------------------------------------------------------------
@rd_projects_bp.route('/api/rd-projects/<int:pid>/milestones', methods=['POST'])
@token_required
def add_milestone(pid):
    payload = request.current_user
    db = get_db()
    project = _get_project(db, pid)
    if not project:
        return jsonify({'code': 404, 'message': '项目不存在', 'data': None})
    if not _can_edit(payload['username'], project):
        return jsonify({'code': 403, 'message': '无权维护里程碑', 'data': None})

    body = request.get_json(silent=True) or {}
    name = (body.get('name') or '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '请填写里程碑名称', 'data': None})

    max_sort = db.execute(
        "SELECT COALESCE(MAX(sort_no), 0) AS m FROM rd_milestones WHERE project_id=?", (pid,)
    ).fetchone()
    cur = db.execute("""
        INSERT INTO rd_milestones
            (project_id, name, plan_date, actual_date, owner, status, remark, sort_no)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (pid, name, (body.get('plan_date') or '').strip(),
          (body.get('actual_date') or '').strip(), (body.get('owner') or '').strip(),
          'done' if body.get('status') == 'done' else 'pending',
          (body.get('remark') or '').strip(),
          int(body.get('sort_no') or (max_sort['m'] if max_sort else 0) + 1)))
    _recalc_progress(db, pid)
    db.commit()
    return jsonify({'code': 200, 'message': '已添加', 'data': {'id': cur.lastrowid}})


@rd_projects_bp.route('/api/rd-projects/milestones/<int:mid>', methods=['PUT'])
@token_required
def update_milestone(mid):
    payload = request.current_user
    db = get_db()
    row = db.execute("SELECT * FROM rd_milestones WHERE id=?", (mid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '里程碑不存在', 'data': None})
    ms = dict(row)
    project = _get_project(db, ms['project_id'])
    if not _can_edit(payload['username'], project):
        return jsonify({'code': 403, 'message': '无权维护里程碑', 'data': None})

    body = request.get_json(silent=True) or {}
    fields, params = [], []
    for col, key in (('name', 'name'), ('plan_date', 'plan_date'), ('actual_date', 'actual_date'),
                     ('owner', 'owner'), ('remark', 'remark')):
        if key in body:
            fields.append(f"{col}=?")
            params.append((body.get(key) or '').strip())
    if 'status' in body:
        fields.append('status=?')
        params.append('done' if body['status'] == 'done' else 'pending')
    if 'sort_no' in body:
        fields.append('sort_no=?')
        params.append(int(body['sort_no'] or 0))

    if fields:
        params.append(mid)
        db.execute(f"UPDATE rd_milestones SET {', '.join(fields)} WHERE id=?", params)
        _recalc_progress(db, ms['project_id'])
        db.commit()
    return jsonify({'code': 200, 'message': '已更新', 'data': None})


@rd_projects_bp.route('/api/rd-projects/milestones/<int:mid>', methods=['DELETE'])
@token_required
def delete_milestone(mid):
    payload = request.current_user
    db = get_db()
    row = db.execute("SELECT * FROM rd_milestones WHERE id=?", (mid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '里程碑不存在', 'data': None})
    ms = dict(row)
    project = _get_project(db, ms['project_id'])
    if not _can_edit(payload['username'], project):
        return jsonify({'code': 403, 'message': '无权维护里程碑', 'data': None})
    db.execute("DELETE FROM rd_milestones WHERE id=?", (mid,))
    _recalc_progress(db, ms['project_id'])
    db.commit()
    return jsonify({'code': 200, 'message': '已删除', 'data': None})


# ------------------------------------------------------------
# 成果物
# ------------------------------------------------------------
@rd_projects_bp.route('/api/rd-projects/<int:pid>/deliverables', methods=['POST'])
@token_required
def add_deliverable(pid):
    payload = request.current_user
    db = get_db()
    project = _get_project(db, pid)
    if not project:
        return jsonify({'code': 404, 'message': '项目不存在', 'data': None})
    if not _can_edit(payload['username'], project):
        return jsonify({'code': 403, 'message': '无权维护成果物', 'data': None})

    body = request.get_json(silent=True) or {}
    name = (body.get('name') or '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '请填写成果物名称', 'data': None})
    dtype = body.get('dtype') if body.get('dtype') in DELIVERABLE_TYPES else '文档'

    cur = db.execute("""
        INSERT INTO rd_deliverables (project_id, name, dtype, deliver_date, remark)
        VALUES (?, ?, ?, ?, ?)
    """, (pid, name, dtype, (body.get('deliver_date') or '').strip(),
          (body.get('remark') or '').strip()))
    db.commit()
    return jsonify({'code': 200, 'message': '已登记', 'data': {'id': cur.lastrowid}})


@rd_projects_bp.route('/api/rd-projects/deliverables/<int:did>', methods=['DELETE'])
@token_required
def delete_deliverable(did):
    payload = request.current_user
    db = get_db()
    row = db.execute("SELECT * FROM rd_deliverables WHERE id=?", (did,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '成果物不存在', 'data': None})
    dv = dict(row)
    project = _get_project(db, dv['project_id'])
    if not _can_edit(payload['username'], project):
        return jsonify({'code': 403, 'message': '无权维护成果物', 'data': None})
    db.execute("DELETE FROM rd_deliverables WHERE id=?", (did,))
    db.commit()
    return jsonify({'code': 200, 'message': '已删除', 'data': None})


# ------------------------------------------------------------
# 元数据（状态下拉 + 可选人员）
# ------------------------------------------------------------
@rd_projects_bp.route('/api/rd-projects/meta', methods=['GET'])
@token_required
def meta():
    db = get_db()
    users = [{'username': r['username'], 'name': r['name'], 'department': r['department'] or ''}
             for r in db.execute(
                 "SELECT username, name, department FROM users "
                 "WHERE status IS NULL OR status != '离职' ORDER BY name").fetchall()]
    return jsonify({'code': 200, 'message': 'success', 'data': {
        'statuses': STATUS_LIST, 'deliverable_types': DELIVERABLE_TYPES, 'users': users,
    }})


def register_routes(app):
    app.register_blueprint(rd_projects_bp)
    with app.app_context():
        db = get_db()
        for ddl in DDL:
            db.execute(ddl)
        db.commit()
