"""市场任务单模块（纸质《市场任务单》线上化）。

业务流程：
  发起人填写任务单（任务名称/来源/任务要求/期望完成日期，选择接收部门与接收人）
  → 提交，待发起部门负责人审批
  → 发起部门负责人通过 / 驳回（填写意见）
  → 接收部门负责人同意接收（填写预计完成日期、预计投入工时/人日）/ 拒绝
  → 执行中 → 发起人或接收人标记完成。

状态机：
  draft（草稿）
  → pending_init（待发起部门审批）
  → pending_recv（待接收部门受理）
  → in_progress（执行中）
  → completed（已完成）
  任一审批环节驳回 / 拒绝 → rejected（发起人可修改后重新提交）。
"""
from datetime import datetime

from flask import request, jsonify
from extensions import (
    get_db, token_required, record_operation_log, user_can,
)
from . import market_tasks_bp


def register_routes(app):
    app.register_blueprint(market_tasks_bp, url_prefix='/api/market-tasks')


# ==================== 建表 ====================

def _ensure_tables():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS market_tasks (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            task_no VARCHAR(40) NOT NULL,
            task_date VARCHAR(20) DEFAULT '',
            title VARCHAR(255) NOT NULL,
            source VARCHAR(255) DEFAULT '',
            requirements TEXT,
            expected_completion VARCHAR(255) DEFAULT '',
            initiator VARCHAR(191),
            initiator_name VARCHAR(191),
            initiator_dept VARCHAR(191),
            init_opinion TEXT,
            init_approver VARCHAR(191),
            init_approved_at VARCHAR(32),
            init_result VARCHAR(20),
            receiver VARCHAR(191),
            receiver_name VARCHAR(191),
            receiver_dept VARCHAR(191),
            recv_opinion TEXT,
            recv_approver VARCHAR(191),
            recv_approved_at VARCHAR(32),
            recv_result VARCHAR(20),
            est_completion_date VARCHAR(32),
            est_work_days REAL,
            result_note TEXT,
            completed_at VARCHAR(32),
            status VARCHAR(30) NOT NULL DEFAULT 'draft',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)


# ==================== 辅助函数 ====================

def _now_str():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _generate_task_no(db):
    """任务编号：TDY-{年份}-{年内三位序号}，如 TDY-2025-001。"""
    year = datetime.now().strftime('%Y')
    prefix = f'TDY-{year}-'
    row = db.execute(
        "SELECT COUNT(*) AS c FROM market_tasks WHERE task_no LIKE ?",
        (f'{prefix}%',)
    ).fetchone()
    return f'{prefix}{(row["c"] + 1):03d}'


def _user_roles(db, username):
    """返回用户的角色集合（主角色 + user_roles 多角色）与部门。"""
    row = db.execute(
        "SELECT role, department FROM users WHERE username=?", (username,)
    ).fetchone()
    roles = set()
    dept = None
    if row:
        if row['role']:
            roles.add(row['role'])
        dept = row['department']
    for r in db.execute(
        "SELECT role FROM user_roles WHERE username=?", (username,)
    ).fetchall():
        roles.add(r['role'])
    return roles, dept


def _can_approve_init(db, username, task):
    """发起部门审批人：同部门主任，或院长（跨部门）。"""
    roles, dept = _user_roles(db, username)
    if '院长' in roles:
        return True
    return '主任' in roles and dept == task['initiator_dept']


def _can_approve_recv(db, username, task):
    """接收部门审批人：同部门主任，或院长（跨部门）。"""
    roles, dept = _user_roles(db, username)
    if '院长' in roles:
        return True
    return '主任' in roles and dept == task['receiver_dept']


def _get_user(db, username):
    return db.execute(
        "SELECT username, name, department FROM users "
        "WHERE username=? AND (status IS NULL OR status != '离职')",
        (username,)
    ).fetchone()


# ==================== 用户目录（接收人选择） ====================

@market_tasks_bp.route('/users', methods=['GET'])
@token_required
def list_users():
    """在职用户简要目录，供选择接收人。"""
    db = get_db()
    rows = db.execute("""
        SELECT username, name, department
        FROM users
        WHERE status IS NULL OR status != '离职'
        ORDER BY department, name
    """).fetchall()
    return jsonify({'code': 200, 'message': 'success', 'data': [dict(r) for r in rows]})


# ==================== 任务单 CRUD ====================

@market_tasks_bp.route('', methods=['GET'])
@token_required
def list_tasks():
    """任务单列表。

    scope：
      related（默认）与我相关：我发起/我接收/待我审批；
      created 我发起的；received 我接收的；pending 待我审批的；
      all 全部（需 data.view_all）。
    支持 keyword（编号/名称/来源）、status 筛选与分页。
    """
    _ensure_tables()
    payload = request.current_user
    username = payload['username']
    scope = request.args.get('scope', 'related').strip()
    keyword = request.args.get('keyword', '').strip()
    status = request.args.get('status', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    db = get_db()

    if scope == 'all' and not user_can(username, 'data.view_all'):
        scope = 'related'

    where = []
    params = []
    pending_only = scope == 'pending'

    if scope == 'created':
        where.append('initiator = ?')
        params.append(username)
    elif scope == 'received':
        where.append('receiver = ?')
        params.append(username)

    if pending_only:
        where.append("status IN ('pending_init', 'pending_recv')")
    elif status:
        where.append('status = ?')
        params.append(status)

    if keyword:
        where.append('(task_no LIKE ? OR title LIKE ? OR source LIKE ?)')
        kw = f'%{keyword}%'
        params.extend([kw, kw, kw])

    sql = 'SELECT * FROM market_tasks'
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY id DESC'
    rows = [dict(r) for r in db.execute(sql, params).fetchall()]

    # 待审批过滤 / related 补充待我审批的任务
    if pending_only:
        rows = [
            t for t in rows
            if (t['status'] == 'pending_init' and _can_approve_init(db, username, t))
            or (t['status'] == 'pending_recv' and _can_approve_recv(db, username, t))
        ]
    elif scope == 'related':
        rows = [t for t in rows if t['initiator'] == username or t['receiver'] == username]
        pend_rows = db.execute(
            "SELECT * FROM market_tasks WHERE status IN ('pending_init', 'pending_recv')"
        ).fetchall()
        existing_ids = {t['id'] for t in rows}
        for r in pend_rows:
            t = dict(r)
            if t['id'] in existing_ids:
                continue
            if (t['status'] == 'pending_init' and _can_approve_init(db, username, t)) \
               or (t['status'] == 'pending_recv' and _can_approve_recv(db, username, t)):
                rows.append(t)
        rows.sort(key=lambda x: x['id'], reverse=True)

    total = len(rows)
    start = (page - 1) * per_page
    page_rows = rows[start:start + per_page]
    return jsonify({'code': 200, 'message': 'success',
                    'data': page_rows, 'total': total})


@market_tasks_bp.route('', methods=['POST'])
@token_required
def create_task():
    """新建任务单。body 含 title/source/requirements/expected_completion/receiver；
    submit=true 直接提交（pending_init），否则存为草稿。
    """
    _ensure_tables()
    payload = request.current_user
    username = payload['username']
    data = request.get_json(silent=True) or {}

    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'code': 400, 'message': '请填写任务名称', 'data': None})

    receiver_username = (data.get('receiver') or '').strip()
    receiver_row = None
    if receiver_username:
        receiver_row = _get_user(get_db(), receiver_username)
        if not receiver_row:
            return jsonify({'code': 400, 'message': '接收人不存在或已离职', 'data': None})

    submit = bool(data.get('submit'))
    now = _now_str()
    db = get_db()
    task_no = _generate_task_no(db)
    task_date = (data.get('task_date') or '').strip() or datetime.now().strftime('%Y-%m-%d')

    # token 载荷不含部门，发起人姓名/部门以 users 表为准
    initiator_row = _get_user(db, username)

    db.execute("""
        INSERT INTO market_tasks (
            task_no, task_date, title, source, requirements, expected_completion,
            initiator, initiator_name, initiator_dept,
            receiver, receiver_name, receiver_dept, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        task_no, task_date, title,
        (data.get('source') or '').strip(), data.get('requirements') or '',
        (data.get('expected_completion') or '').strip(),
        username,
        initiator_row['name'] if initiator_row else payload.get('name'),
        initiator_row['department'] if initiator_row else None,
        receiver_username,
        receiver_row['name'] if receiver_row else '',
        receiver_row['department'] if receiver_row else '',
        'pending_init' if submit else 'draft', now, now,
    ))
    db.commit()
    record_operation_log(
        username, '新建', '市场任务单',
        f'{task_no} {title}' + ('（已提交）' if submit else '（草稿）')
    )
    return jsonify({'code': 200, 'message': '任务单已创建',
                    'data': {'task_no': task_no}})


@market_tasks_bp.route('/<int:tid>', methods=['GET'])
@token_required
def get_task(tid):
    _ensure_tables()
    row = get_db().execute(
        "SELECT * FROM market_tasks WHERE id=?", (tid,)
    ).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '任务单不存在', 'data': None})
    return jsonify({'code': 200, 'message': 'success', 'data': dict(row)})


@market_tasks_bp.route('/<int:tid>', methods=['PUT'])
@token_required
def update_task(tid):
    """编辑任务单（仅 draft/rejected 且为发起人）。"""
    _ensure_tables()
    payload = request.current_user
    username = payload['username']
    db = get_db()
    task = db.execute("SELECT * FROM market_tasks WHERE id=?", (tid,)).fetchone()
    if not task:
        return jsonify({'code': 404, 'message': '任务单不存在', 'data': None})
    if task['initiator'] != username:
        return jsonify({'code': 403, 'message': '仅发起人可编辑', 'data': None})
    if task['status'] not in ('draft', 'rejected'):
        return jsonify({'code': 400, 'message': '当前状态不可编辑', 'data': None})

    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'code': 400, 'message': '请填写任务名称', 'data': None})

    receiver_username = (data.get('receiver') or '').strip()
    receiver_row = None
    if receiver_username:
        receiver_row = _get_user(db, receiver_username)
        if not receiver_row:
            return jsonify({'code': 400, 'message': '接收人不存在或已离职', 'data': None})

    db.execute("""
        UPDATE market_tasks
        SET task_date=?, title=?, source=?, requirements=?, expected_completion=?,
            receiver=?, receiver_name=?, receiver_dept=?, updated_at=?
        WHERE id=?
    """, (
        (data.get('task_date') or task['task_date']).strip(), title,
        (data.get('source') or '').strip(), data.get('requirements') or '',
        (data.get('expected_completion') or '').strip(),
        receiver_username,
        receiver_row['name'] if receiver_row else '',
        receiver_row['department'] if receiver_row else '',
        _now_str(), tid,
    ))
    db.commit()
    return jsonify({'code': 200, 'message': '已保存', 'data': None})


# ==================== 流程动作 ====================

@market_tasks_bp.route('/<int:tid>/submit', methods=['POST'])
@token_required
def submit_task(tid):
    """提交/重新提交任务单（draft/rejected → pending_init）。"""
    _ensure_tables()
    payload = request.current_user
    username = payload['username']
    db = get_db()
    task = db.execute("SELECT * FROM market_tasks WHERE id=?", (tid,)).fetchone()
    if not task:
        return jsonify({'code': 404, 'message': '任务单不存在', 'data': None})
    if task['initiator'] != username:
        return jsonify({'code': 403, 'message': '仅发起人可提交', 'data': None})
    if task['status'] not in ('draft', 'rejected'):
        return jsonify({'code': 400, 'message': '当前状态不可提交', 'data': None})
    if not task['receiver']:
        return jsonify({'code': 400, 'message': '请先选择接收人', 'data': None})

    # 重新提交时清空上一轮审批痕迹
    db.execute("""
        UPDATE market_tasks
        SET status='pending_init', init_opinion=NULL, init_approver=NULL,
            init_approved_at=NULL, init_result=NULL,
            recv_opinion=NULL, recv_approver=NULL, recv_approved_at=NULL,
            recv_result=NULL, est_completion_date=NULL, est_work_days=NULL,
            updated_at=?
        WHERE id=?
    """, (_now_str(), tid))
    db.commit()
    record_operation_log(username, '提交', '市场任务单', task['task_no'])
    return jsonify({'code': 200, 'message': '已提交，等待发起部门审批', 'data': None})


@market_tasks_bp.route('/<int:tid>/init-approval', methods=['POST'])
@token_required
def init_approval(tid):
    """发起部门负责人审批：action=approve|reject，opinion 为意见。"""
    _ensure_tables()
    payload = request.current_user
    username = payload['username']
    db = get_db()
    task = db.execute("SELECT * FROM market_tasks WHERE id=?", (tid,)).fetchone()
    if not task:
        return jsonify({'code': 404, 'message': '任务单不存在', 'data': None})
    if task['status'] != 'pending_init':
        return jsonify({'code': 400, 'message': '当前状态不可审批', 'data': None})
    if not _can_approve_init(db, username, dict(task)):
        return jsonify({'code': 403, 'message': '仅发起部门负责人可审批', 'data': None})

    body = request.get_json(silent=True) or {}
    action = body.get('action')
    opinion = (body.get('opinion') or '').strip()
    if action not in ('approve', 'reject'):
        return jsonify({'code': 400, 'message': 'action 错误', 'data': None})
    if action == 'reject' and not opinion:
        return jsonify({'code': 400, 'message': '驳回请填写意见', 'data': None})

    if action == 'approve':
        db.execute("""
            UPDATE market_tasks
            SET status='pending_recv', init_result='approved',
                init_opinion=?, init_approver=?, init_approved_at=?, updated_at=?
            WHERE id=?
        """, (opinion, username, _now_str(), _now_str(), tid))
        msg = '已通过，转接收部门受理'
    else:
        db.execute("""
            UPDATE market_tasks
            SET status='rejected', init_result='rejected',
                init_opinion=?, init_approver=?, init_approved_at=?, updated_at=?
            WHERE id=?
        """, (opinion, username, _now_str(), _now_str(), tid))
        msg = '已驳回'
    db.commit()
    record_operation_log(username, '审批', '市场任务单', f'{task["task_no"]} {msg}')
    return jsonify({'code': 200, 'message': msg, 'data': None})


@market_tasks_bp.route('/<int:tid>/recv-approval', methods=['POST'])
@token_required
def recv_approval(tid):
    """接收部门负责人受理：action=accept|reject；
    accept 时需 est_completion_date、est_work_days（人日）。
    """
    _ensure_tables()
    payload = request.current_user
    username = payload['username']
    db = get_db()
    task = db.execute("SELECT * FROM market_tasks WHERE id=?", (tid,)).fetchone()
    if not task:
        return jsonify({'code': 404, 'message': '任务单不存在', 'data': None})
    if task['status'] != 'pending_recv':
        return jsonify({'code': 400, 'message': '当前状态不可受理', 'data': None})
    if not _can_approve_recv(db, username, dict(task)):
        return jsonify({'code': 403, 'message': '仅接收部门负责人可受理', 'data': None})

    body = request.get_json(silent=True) or {}
    action = body.get('action')
    opinion = (body.get('opinion') or '').strip()
    if action not in ('accept', 'reject'):
        return jsonify({'code': 400, 'message': 'action 错误', 'data': None})
    if action == 'reject' and not opinion:
        return jsonify({'code': 400, 'message': '拒绝请填写意见', 'data': None})

    if action == 'accept':
        est_date = (body.get('est_completion_date') or '').strip()
        est_days_raw = body.get('est_work_days')
        if not est_date:
            return jsonify({'code': 400, 'message': '请填写预计完成日期', 'data': None})
        try:
            est_days = float(est_days_raw) if est_days_raw not in (None, '') else None
        except (TypeError, ValueError):
            return jsonify({'code': 400, 'message': '预计投入工时格式错误', 'data': None})
        if est_days is None or est_days <= 0:
            return jsonify({'code': 400, 'message': '请填写预计投入工时（人日）', 'data': None})

        db.execute("""
            UPDATE market_tasks
            SET status='in_progress', recv_result='accepted',
                recv_opinion=?, recv_approver=?, recv_approved_at=?,
                est_completion_date=?, est_work_days=?, updated_at=?
            WHERE id=?
        """, (opinion or '同意接收任务', username, _now_str(),
              est_date, est_days, _now_str(), tid))
        msg = '已接收任务'
    else:
        db.execute("""
            UPDATE market_tasks
            SET status='rejected', recv_result='rejected',
                recv_opinion=?, recv_approver=?, recv_approved_at=?, updated_at=?
            WHERE id=?
        """, (opinion, username, _now_str(), _now_str(), tid))
        msg = '已拒绝接收'
    db.commit()
    record_operation_log(username, '受理', '市场任务单', f'{task["task_no"]} {msg}')
    return jsonify({'code': 200, 'message': msg, 'data': None})


@market_tasks_bp.route('/<int:tid>/complete', methods=['POST'])
@token_required
def complete_task(tid):
    """标记完成（执行中，发起人或接收人均可）。"""
    _ensure_tables()
    payload = request.current_user
    username = payload['username']
    db = get_db()
    task = db.execute("SELECT * FROM market_tasks WHERE id=?", (tid,)).fetchone()
    if not task:
        return jsonify({'code': 404, 'message': '任务单不存在', 'data': None})
    if task['status'] != 'in_progress':
        return jsonify({'code': 400, 'message': '仅执行中的任务可完成', 'data': None})
    if username not in (task['initiator'], task['receiver']):
        return jsonify({'code': 403, 'message': '仅发起人或接收人可标记完成', 'data': None})

    body = request.get_json(silent=True) or {}
    now = _now_str()
    db.execute("""
        UPDATE market_tasks
        SET status='completed', result_note=?, completed_at=?, updated_at=?
        WHERE id=?
    """, ((body.get('note') or '').strip(), now, now, tid))
    db.commit()
    record_operation_log(username, '完成', '市场任务单', task['task_no'])
    return jsonify({'code': 200, 'message': '任务已完成', 'data': None})
