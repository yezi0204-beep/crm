"""异步任务监控 API。

GET  /api/tasks           任务列表（状态/类型筛选）
GET  /api/tasks/stats     任务统计
POST /api/tasks/<id>/retry  人工重新执行
POST /api/tasks/<id>/cancel 取消任务
POST /api/tasks/submit    手动提交任务
GET  /api/ai-logs         AI操作日志
"""
from flask import Blueprint, request, jsonify
from extensions import get_db, token_required, admin_required, record_operation_log
import json
import logging

logger = logging.getLogger(__name__)
tasks_bp = Blueprint('tasks', __name__)


def register_routes(app):
    app.register_blueprint(tasks_bp, url_prefix='/api')


@tasks_bp.route('/tasks', methods=['GET'])
@token_required
def list_tasks():
    db = get_db()
    status = request.args.get('status', '').strip()
    task_type = request.args.get('task_type', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page

    sql = "SELECT * FROM ai_tasks WHERE 1=1"
    params = []
    if status:
        sql += " AND status=?"
        params.append(status)
    if task_type:
        sql += " AND task_type=?"
        params.append(task_type)

    total = db.execute(f"SELECT COUNT(*) as c FROM ({sql})", params).fetchone()['c']
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    rows = db.execute(sql, params).fetchall()
    return jsonify({'code': 200, 'data': [dict(r) for r in rows], 'total': total})


@tasks_bp.route('/tasks/stats', methods=['GET'])
@token_required
def task_stats():
    from task_system import get_task_stats
    return jsonify({'code': 200, 'data': get_task_stats()})


@tasks_bp.route('/tasks/<int:tid>', methods=['GET'])
@token_required
def task_detail(tid):
    db = get_db()
    row = db.execute("SELECT * FROM ai_tasks WHERE id=?", (tid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '任务不存在'})
    data = dict(row)
    for f in ('payload', 'result'):
        if data.get(f):
            try:
                data[f] = json.loads(data[f])
            except (json.JSONDecodeError, TypeError):
                pass
    return jsonify({'code': 200, 'data': data})


@tasks_bp.route('/tasks/<int:tid>/retry', methods=['POST'])
@admin_required
def retry_task(tid):
    """人工重新执行任务。"""
    from task_system import _run_task
    db = get_db()
    row = db.execute("SELECT status FROM ai_tasks WHERE id=?", (tid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '任务不存在'})
    if row['status'] == 'RUNNING':
        return jsonify({'code': 400, 'message': '任务正在运行中'})
    db.execute("""
        UPDATE ai_tasks SET status='PENDING', retry_count=0, error_message=NULL,
            finished_at=NULL, started_at=NULL WHERE id=?
    """, (tid,))
    db.commit()
    from extensions import DB_PATH
    import threading
    # 重新入队（借用 handler 已注册）
    from task_system import _executor
    _executor.submit(_run_task, tid)
    record_operation_log(request.current_user, 'retry', 'ai_task', f'重新执行任务#{tid}')
    return jsonify({'code': 200, 'message': f'任务#{tid} 已重新提交'})


@tasks_bp.route('/tasks/<int:tid>/cancel', methods=['POST'])
@admin_required
def cancel_task(tid):
    db = get_db()
    row = db.execute("SELECT status FROM ai_tasks WHERE id=?", (tid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '任务不存在'})
    if row['status'] in ('SUCCESS', 'FAILED', 'CANCELLED'):
        return jsonify({'code': 400, 'message': f'任务已结束（{row["status"]}）'})
    db.execute("UPDATE ai_tasks SET status='CANCELLED', finished_at=CURRENT_TIMESTAMP WHERE id=?", (tid,))
    db.commit()
    record_operation_log(request.current_user, 'cancel', 'ai_task', f'取消任务#{tid}')
    return jsonify({'code': 200, 'message': f'任务#{tid} 已取消'})


@tasks_bp.route('/tasks/submit', methods=['POST'])
@admin_required
def submit_task_api():
    """手动提交任务。

    Body: {"task_type": "update_customer_profile", "payload": {...}}
    """
    from task_system import submit_task, TASK_TYPES
    data = request.get_json(silent=True) or {}
    task_type = data.get('task_type', '')
    if task_type not in TASK_TYPES:
        return jsonify({'code': 400, 'message': f'无效任务类型，可选: {", ".join(TASK_TYPES)}'})

    task_id = submit_task(
        task_type, payload=data.get('payload'),
        created_by=request.current_user['username'],
        max_retries=data.get('max_retries', 3),
        timeout_seconds=data.get('timeout_seconds', 600),
    )
    record_operation_log(request.current_user, 'submit', 'ai_task', f'提交任务#{task_id}: {task_type}')
    return jsonify({'code': 200, 'message': f'任务#{task_id} 已提交', 'data': {'task_id': task_id}})


@tasks_bp.route('/ai-logs', methods=['GET'])
@token_required
def ai_logs():
    """AI操作日志列表。"""
    db = get_db()
    op_type = request.args.get('op_type', '').strip()
    status = request.args.get('status', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page

    sql = "SELECT * FROM ai_operation_logs WHERE 1=1"
    params = []
    if op_type:
        sql += " AND operation_type=?"
        params.append(op_type)
    if status:
        sql += " AND status=?"
        params.append(status)

    total = db.execute(f"SELECT COUNT(*) as c FROM ({sql})", params).fetchone()['c']
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    rows = db.execute(sql, params).fetchall()
    return jsonify({'code': 200, 'data': [dict(r) for r in rows], 'total': total})
