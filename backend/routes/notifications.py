# -*- coding: utf-8 -*-
"""站内消息提示：聚合销售提醒、审批待办、业务到期、系统日志未读。

- 销售提醒 / 操作日志：已读状态直接落在源表（sales_alerts.status / operation_logs.is_read）
- 审批待办 / 业务到期：属实时推导的待办，已读状态记录在 notification_reads 表（按用户隔离）
"""
import logging
from datetime import date, datetime, timedelta

from flask import request, jsonify
from extensions import get_db, token_required, user_can
from . import notifications_bp

logger = logging.getLogger(__name__)

LIMIT_PER_TYPE = 100


def _today():
    return date.today()


def _fmt_time(val):
    if not val:
        return ''
    s = str(val)
    return s.replace('T', ' ')[:19]


def _get_user(cursor, username):
    cursor.execute("SELECT username, name, role, department FROM users WHERE username=?", (username,))
    return cursor.fetchone()


def _read_keys(cursor, username):
    cursor.execute("SELECT msg_key FROM notification_reads WHERE username=?", (username,))
    return {r['msg_key'] for r in cursor.fetchall()}


def _add(cursor, items, counts, msg, read_keys):
    """加推导类消息（审批/到期），已读的跳过。"""
    if msg['key'] in read_keys:
        return
    counts[msg['type']] = counts.get(msg['type'], 0) + 1
    if len([i for i in items if i['type'] == msg['type']]) < LIMIT_PER_TYPE:
        items.append(msg)


def build_messages(username):
    db = get_db()
    cursor = db.cursor()
    user = _get_user(cursor, username) or {}
    role = user.get('role') or ''
    dept = user.get('department') or ''
    can_all = user_can(username, 'data.view_all')
    read_keys = _read_keys(cursor, username)
    today = _today()

    items = []
    counts = {'alert': 0, 'approval': 0, 'expiry': 0, 'oplog': 0}

    # ---------- 1. 销售提醒 ----------
    # 同标题的重复提醒合并为一条展示，点击已读时整组置为已读
    cursor.execute("""
        SELECT title, COUNT(*) AS cnt, MAX(id) AS last_id, MAX(created_at) AS last_time,
               MIN(CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 ELSE 2 END) AS prank
        FROM sales_alerts WHERE status='unread'
        GROUP BY title
        ORDER BY prank, last_id DESC
        LIMIT ?
    """, (LIMIT_PER_TYPE,))
    alert_rows = cursor.fetchall()
    cursor.execute("SELECT COUNT(*) AS c FROM sales_alerts WHERE status='unread'")
    counts['alert'] = cursor.fetchone()['c']
    for r in alert_rows:
        title = r['title'] or '销售提醒'
        cnt = r['cnt'] or 1
        items.append({
            'key': f"alertg:{title}",
            'type': 'alert',
            'title': title,
            'detail': f'共 {cnt} 条相同提醒' if cnt > 1 else '',
            'priority': {0: 'urgent', 1: 'high'}.get(r['prank'], 'normal'),
            'time': _fmt_time(r['last_time']),
            'count': cnt,
            'route': '/alerts',
        })

    # ---------- 2. 审批待办 ----------
    # 2.1 项目成本核算
    if role in ('财务', '院长') or can_all:
        cursor.execute("""
            SELECT c.id, c.contract_name, c.contract_no, c.cost_submitted_by
            FROM contracts c WHERE c.cost_status='pending_finance'
            ORDER BY c.cost_submitted_at DESC LIMIT ?
        """, (LIMIT_PER_TYPE,))
        for r in cursor.fetchall():
            _add(cursor, items, counts, {
                'key': f'approval:cost_finance:{r["id"]}',
                'type': 'approval',
                'title': f'财务待审：{r["contract_name"] or r["contract_no"]}',
                'detail': f'项目成本核算待财务终审，提交人 {r["cost_submitted_by"] or "-"}',
                'priority': 'high',
                'time': '',
                'route': '/project-cost',
            }, read_keys)
    if role == '主任' and dept:
        cursor.execute("""
            SELECT c.id, c.contract_name, c.contract_no, c.owner_id
            FROM contracts c
            JOIN users u ON u.username = c.owner_id
            WHERE c.cost_status='pending_dept' AND u.department=?
            ORDER BY c.cost_submitted_at DESC LIMIT ?
        """, (dept, LIMIT_PER_TYPE))
        for r in cursor.fetchall():
            _add(cursor, items, counts, {
                'key': f'approval:cost_dept:{r["id"]}',
                'type': 'approval',
                'title': f'部门待审：{r["contract_name"] or r["contract_no"]}',
                'detail': f'项目成本核算待本部门审核，负责人 {r["owner_id"] or "-"}',
                'priority': 'high',
                'time': '',
                'route': '/project-cost',
            }, read_keys)

    # 2.2 工时审批
    if user_can(username, 'workhour.manage'):
        cursor.execute("""
            SELECT w.id, w.user_id, w.work_date, w.hours, u.name AS user_name
            FROM work_hours w LEFT JOIN users u ON u.name = w.user_id
            WHERE w.status='pending' ORDER BY w.work_date DESC LIMIT ?
        """, (LIMIT_PER_TYPE,))
        wh_rows = cursor.fetchall()
    elif user_can(username, 'workhour.approve'):
        cursor.execute("""
            SELECT w.id, w.user_id, w.work_date, w.hours, u.name AS user_name
            FROM work_hours w
            LEFT JOIN users u ON u.name = w.user_id
            LEFT JOIN business b ON b.id = w.business_id
            LEFT JOIN contracts ct ON ct.id = w.project_id AND w.project_type='contract'
            WHERE w.status='pending'
              AND (b.project_manager = ? OR b.owner_id = ? OR ct.owner_id = ?)
            ORDER BY w.work_date DESC LIMIT ?
        """, (username, username, username, LIMIT_PER_TYPE))
        wh_rows = cursor.fetchall()
    else:
        wh_rows = []
    for r in wh_rows:
        _add(cursor, items, counts, {
            'key': f'approval:workhour:{r["id"]}',
            'type': 'approval',
            'title': f'工时待审：{r["user_name"] or r["user_id"]} {r["work_date"]}',
            'detail': f'{r["hours"]} 小时工时待审批',
            'priority': 'normal',
            'time': _fmt_time(r['work_date']),
            'route': '/workhours',
        }, read_keys)

    # 2.3 市场任务单
    cursor.execute("""
        SELECT id, task_no, title, initiator_name, receiver_name, initiator_dept, receiver_dept
        FROM market_tasks
        WHERE (status='pending_init' AND (init_approver=? OR (init_approver IS NULL AND initiator_dept=? AND ?='主任')))
           OR (status='pending_recv' AND (recv_approver=? OR (recv_approver IS NULL AND receiver_dept=? AND ?='主任')))
        ORDER BY id DESC LIMIT ?
    """, (username, dept, role, username, dept, role, LIMIT_PER_TYPE))
    for r in cursor.fetchall():
        _add(cursor, items, counts, {
            'key': f'approval:market_task:{r["id"]}',
            'type': 'approval',
            'title': f'市场任务单待审：{r["title"] or r["task_no"]}',
            'detail': f'{r["task_no"]} · 发起 {r["initiator_name"] or "-"} → 接收 {r["receiver_name"] or "-"}',
            'priority': 'normal',
            'time': '',
            'route': '/market-tasks',
        }, read_keys)

    # ---------- 3. 业务到期提醒 ----------
    owner_clause = '' if can_all else ' AND v.visitor_id = ?'
    owner_params = [] if can_all else [username]
    # 3.1 拜访计划已逾期
    cursor.execute(f"""
        SELECT v.id, v.cust_id, v.plan_date, v.purpose, v.work_content, c.name AS cust_name
        FROM visits v LEFT JOIN customers c ON c.id = v.cust_id
        WHERE v.status='planned' AND v.plan_date < ?{owner_clause}
        ORDER BY v.plan_date ASC LIMIT ?
    """, (today.isoformat(), *owner_params, LIMIT_PER_TYPE))
    for r in cursor.fetchall():
        _add(cursor, items, counts, {
            'key': f'expiry:visit:{r["id"]}',
            'type': 'expiry',
            'title': f'拜访计划已逾期：{r["cust_name"] or "客户"}',
            'detail': f'计划日期 {str(r["plan_date"])[:10]} · {r["purpose"] or r["work_content"] or "拜访"}',
            'priority': 'high',
            'time': _fmt_time(r['plan_date']),
            'route': '/visits',
        }, read_keys)

    # 3.2 商机长期未跟进（>30 天）
    stale = (today - timedelta(days=30)).isoformat()
    biz_owner = '' if can_all else ' AND b.owner_id = ?'
    biz_params = [] if can_all else [username]
    cursor.execute(f"""
        SELECT b.id, b.title, b.amount, b.last_follow, b.created_at
        FROM business b
        WHERE b.status='active' AND COALESCE(NULLIF(b.last_follow,''), b.created_at) < ?{biz_owner}
        ORDER BY COALESCE(NULLIF(b.last_follow,''), b.created_at) ASC LIMIT ?
    """, (stale, *biz_params, LIMIT_PER_TYPE))
    for r in cursor.fetchall():
        last = r['last_follow'] or r['created_at']
        _add(cursor, items, counts, {
            'key': f'expiry:business:{r["id"]}',
            'type': 'expiry',
            'title': f'商机超30天未跟进：{r["title"] or "-"}',
            'detail': f'最近跟进 {str(last)[:10] if last else "从未"} · 金额 ¥{float(r["amount"] or 0):,.2f}',
            'priority': 'normal',
            'time': _fmt_time(last),
            'route': '/business',
        }, read_keys)

    # 3.3 回款计划临近（7 天内）
    soon = (today + timedelta(days=7)).isoformat()
    plan_owner = '' if can_all else ' AND p.user_id = ?'
    plan_params = [] if can_all else [username]
    cursor.execute(f"""
        SELECT p.id, p.plan_date, p.amount, p.description
        FROM payment_plans p
        WHERE p.status='pending' AND p.plan_date <= ?{plan_owner}
        ORDER BY p.plan_date ASC LIMIT ?
    """, (soon, *plan_params, LIMIT_PER_TYPE))
    for r in cursor.fetchall():
        _add(cursor, items, counts, {
            'key': f'expiry:payment_plan:{r["id"]}',
            'type': 'expiry',
            'title': f'回款计划临近：{str(r["plan_date"])[:10]}',
            'detail': f'{r["description"] or "回款计划"} · ¥{float(r["amount"] or 0):,.2f}',
            'priority': 'high',
            'time': _fmt_time(r['plan_date']),
            'route': '/payments',
        }, read_keys)

    # ---------- 4. 系统 / 操作日志未读 ----------
    if user_can(username, 'system.logs'):
        cursor.execute("""
            SELECT module, operation, COUNT(*) AS cnt, MAX(id) AS last_id,
                   MAX(created_at) AS last_time
            FROM operation_logs WHERE is_read=0
            GROUP BY module, operation
            ORDER BY last_id DESC LIMIT ?
        """, (LIMIT_PER_TYPE,))
        for r in cursor.fetchall():
            module = r['module'] or '系统'
            operation = r['operation'] or '操作'
            cnt = r['cnt'] or 1
            items.append({
                'key': f"oplogg:{module}|{operation}",
                'type': 'oplog',
                'title': f"{operation} · {module}",
                'detail': f'共 {cnt} 条未读操作日志' if cnt > 1 else '',
                'priority': 'low',
                'time': _fmt_time(r['last_time']),
                'count': cnt,
                'route': '/operation-logs',
            })
        cursor.execute("SELECT COUNT(*) AS c FROM operation_logs WHERE is_read=0")
        counts['oplog'] = cursor.fetchone()['c']

    order = {'urgent': 0, 'high': 1, 'normal': 2, 'low': 3}
    items.sort(key=lambda x: (order.get(x['priority'], 9), x['time'] or ''), reverse=False)

    total = sum(counts.values())
    return {
        'total_unread': total,
        'counts': counts,
        'items': items,
    }


def register_routes(app):
    app.register_blueprint(notifications_bp, url_prefix='/api/notifications')


@notifications_bp.route('', methods=['GET'])
@token_required
def list_notifications():
    username = request.current_user['username']
    msg_type = request.args.get('type', 'all')
    data = build_messages(username)
    if msg_type and msg_type != 'all':
        data['items'] = [i for i in data['items'] if i['type'] == msg_type]
    return jsonify({'code': 200, 'message': 'success', 'data': data})


@notifications_bp.route('/read', methods=['POST'])
@token_required
def mark_read():
    """标记单条消息已读。key 形如 alertg:标题 / oplogg:模块|操作 / approval:cost_dept:3"""
    username = request.current_user['username']
    data = request.get_json(silent=True) or {}
    key = (data.get('key') or '').strip()
    if not key:
        return jsonify({'code': 400, 'message': '缺少消息标识', 'data': None}), 400

    db = get_db()
    cursor = db.cursor()
    parts = key.split(':')
    if parts[0] == 'alertg':
        title = key[len('alertg:'):]
        cursor.execute("UPDATE sales_alerts SET status='read', read_at=? WHERE status='unread' AND title=?",
                       (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), title))
    elif parts[0] == 'oplogg':
        rest = key[len('oplogg:'):]
        module, _, operation = rest.partition('|')
        cursor.execute("UPDATE operation_logs SET is_read=1 WHERE is_read=0 AND module=? AND operation=?",
                       (module, operation))
    elif parts[0] == 'alert' and len(parts) == 2:
        cursor.execute("UPDATE sales_alerts SET status='read', read_at=? WHERE id=?",
                       (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), parts[1]))
    elif parts[0] == 'oplog' and len(parts) == 2:
        cursor.execute("UPDATE operation_logs SET is_read=1 WHERE id=?", (parts[1],))
    else:
        cursor.execute("INSERT IGNORE INTO notification_reads (username, msg_key, read_at) VALUES (?, ?, ?)",
                       (username, key, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    db.commit()
    return jsonify({'code': 200, 'message': '已标记为已读', 'data': None})


@notifications_bp.route('/read-all', methods=['POST'])
@token_required
def mark_all_read():
    """按类型全部已读；type=all 时清空全部。"""
    username = request.current_user['username']
    data = request.get_json(silent=True) or {}
    msg_type = data.get('type', 'all')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    db = get_db()
    cursor = db.cursor()
    snapshot = build_messages(username)
    keys = [i['key'] for i in snapshot['items']
            if msg_type == 'all' or i['type'] == msg_type]

    if msg_type in ('all', 'alert'):
        cursor.execute("UPDATE sales_alerts SET status='read', read_at=? WHERE status='unread'", (now,))
    if msg_type in ('all', 'oplog') and user_can(username, 'system.logs'):
        cursor.execute("UPDATE operation_logs SET is_read=1 WHERE is_read=0")
    derived = [k for k in keys if not k.startswith(('alert:', 'alertg:', 'oplog:', 'oplogg:'))]
    for k in derived:
        cursor.execute("INSERT IGNORE INTO notification_reads (username, msg_key, read_at) VALUES (?, ?, ?)",
                       (username, k, now))
    db.commit()
    return jsonify({'code': 200, 'message': '已全部标记为已读', 'data': {'count': len(keys)}})
