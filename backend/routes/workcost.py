"""工时成本分摊模块。

流程：人力/管理员按月录入各部门考勤总工时与10项人力成本（工资、社保五项、
年金、公积金、劳务费、福利费、补充险）→ 中心主任把总工时分配到执行中的合同
→ 系统按 单工时成本 = 月度总成本 / 月度总工时 把总支出分摊到各合同（项目）。

设计要点：
- 分摊金额实时计算（不落快照），月度成本修正后历史分摊自动重算；
- 金额一律保留两位小数；
- 管理操作需 workhour.manage 权限（默认授予 主任/院长/人力），查看/导出需
  workhour.view 或 workhour.manage（财务角色默认仅有 workhour.view 只读权限）。
"""
import io
from datetime import datetime

from flask import request, jsonify, send_file
from extensions import (
    get_db, token_required, require_permission, record_operation_log,
)
from . import workcost_bp

DEPARTMENTS = ['技术中心', '应用中心']

# 10 项人力成本字段：(字段名, 中文名)
COST_FIELDS = [
    ('salary', '工资'),
    ('pension', '社保-单位养老'),
    ('medical', '社保-单位医疗'),
    ('unemployment', '社保-单位失业'),
    ('injury', '社保-单位工伤'),
    ('annuity', '单位年金'),
    ('housing_fund', '单位公积金'),
    ('labor_fee', '劳务费'),
    ('welfare', '福利费'),
    ('supplement', '补充险'),
]

COST_SUM_SQL = ' + '.join(
    f"COALESCE(m.{f}, 0)" for f, _ in COST_FIELDS
)


def register_routes(app):
    app.register_blueprint(workcost_bp, url_prefix='/api/work-cost')


def _month_cost_with_stats(row, alloc_map):
    """月度记录 + 已分配统计 + 单工时成本。"""
    item = dict(row)
    total_cost = round(sum(float(item.get(f) or 0) for f, _ in COST_FIELDS), 2)
    total_hours = float(item.get('total_hours') or 0)
    unit_cost = round(total_cost / total_hours, 4) if total_hours > 0 else 0
    alloc = alloc_map.get(item['id'], {'hours': 0, 'cost': 0})
    allocated_hours = round(float(alloc['hours']), 2)
    return {
        **item,
        'total_cost': total_cost,
        'unit_cost': unit_cost,
        'allocated_hours': allocated_hours,
        'allocated_cost': round(float(alloc['cost']), 2),
        'remaining_hours': round(total_hours - allocated_hours, 2),
    }


def _alloc_map_by_cost(db, cost_ids=None):
    """{cost_id: {hours, cost}} — 已分配工时与分摊金额汇总。"""
    sql = f"""
        SELECT a.cost_id, COALESCE(SUM(a.hours),0) as hours,
               COALESCE(SUM(a.hours * ({COST_SUM_SQL}) / NULLIF(m.total_hours,0)),0) as cost
        FROM dept_hour_allocations a
        JOIN dept_month_costs m ON a.cost_id = m.id
    """
    params = []
    if cost_ids is not None:
        if not cost_ids:
            return {}
        ph = ','.join('?' * len(cost_ids))
        sql += f" WHERE a.cost_id IN ({ph})"
        params = cost_ids
    sql += " GROUP BY a.cost_id"
    return {
        r['cost_id']: {'hours': r['hours'], 'cost': r['cost']}
        for r in db.execute(sql, params).fetchall()
    }


# ============================================================
# 月度成本管理
# ============================================================
@workcost_bp.route('/months', methods=['GET'])
@require_permission(('workhour.view', 'workhour.manage'))
def list_months():
    """月度成本列表（含单工时成本、已分配统计）。可按 dept/year 筛选。"""
    db = get_db()
    dept = request.args.get('dept', '').strip()
    year = request.args.get('year', '').strip()

    sql = "SELECT * FROM dept_month_costs WHERE 1=1"
    params = []
    if dept:
        sql += " AND dept=?"
        params.append(dept)
    if year:
        sql += " AND month LIKE ?"
        params.append(f'{year}-%')
    sql += " ORDER BY month DESC, dept"
    rows = db.execute(sql, params).fetchall()
    alloc_map = _alloc_map_by_cost(db, [r['id'] for r in rows])
    data = [_month_cost_with_stats(r, alloc_map) for r in rows]
    return jsonify({'code': 200, 'message': 'success', 'data': data})


@workcost_bp.route('/months', methods=['POST'])
@require_permission('workhour.manage')
def save_month():
    """录入/更新月度成本（按 dept+month upsert）。"""
    payload = request.current_user
    body = request.get_json(silent=True) or {}
    dept = (body.get('dept') or '').strip()
    month = (body.get('month') or '').strip()
    total_hours = body.get('total_hours')

    if dept not in DEPARTMENTS:
        return jsonify({'code': 400, 'message': f'部门必须是 {"/".join(DEPARTMENTS)}', 'data': None})
    if not (len(month) == 7 and month[:4].isdigit() and month[5:7].isdigit()):
        return jsonify({'code': 400, 'message': '月份格式应为 YYYY-MM', 'data': None})
    try:
        total_hours = float(total_hours)
        if total_hours <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({'code': 400, 'message': '总工时必须大于 0', 'data': None})

    values = {'dept': dept, 'month': month, 'total_hours': total_hours}
    for f, _ in COST_FIELDS:
        try:
            v = float(body.get(f) or 0)
        except (TypeError, ValueError):
            v = 0
        if v < 0:
            return jsonify({'code': 400, 'message': '费用项不能为负数', 'data': None})
        values[f] = round(v, 2)

    total_cost = round(sum(values[f] for f, _ in COST_FIELDS), 2)
    if total_cost <= 0:
        return jsonify({'code': 400, 'message': '至少填写一项人力成本', 'data': None})

    db = get_db()
    now = datetime.now().isoformat(sep=' ', timespec='seconds')
    existing = db.execute(
        "SELECT id FROM dept_month_costs WHERE dept=? AND month=?", (dept, month)
    ).fetchone()
    if existing:
        # COALESCE 保护：编辑时未传的费用字段（None）不覆盖原值；total_hours 直接覆盖
        sets = ', '.join(
            f"{k}=COALESCE(?, {k})" if k != 'total_hours' else f"{k}=?"
            for k in values if k not in ('dept', 'month')
        )
        params = [values[k] if k == 'total_hours' else (values[k] if body.get(k) is not None else None)
                  for k in values if k not in ('dept', 'month')]
        params.append(now)
        params.append(existing['id'])
        db.execute(
            f"UPDATE dept_month_costs SET {sets}, updated_at=? WHERE id=?", params
        )
        cost_id = existing['id']
        action = '更新'
    else:
        cols = ', '.join(values)
        ph = ','.join('?' * len(values))
        db.execute(
            f"INSERT INTO dept_month_costs ({cols}, created_by, created_at) "
            f"VALUES ({ph}, ?, ?)",
            list(values.values()) + [payload['username'], now]
        )
        cost_id = db.execute("SELECT last_insert_rowid() as id").fetchone()['id']
        action = '录入'

    db.commit()
    record_operation_log(
        payload['username'], action, '工时分摊',
        f'{action} {dept} {month} 月度成本：总工时 {total_hours}，总成本 {total_cost}'
    )
    return jsonify({
        'code': 200,
        'message': f'{dept} {month} 成本已保存（总成本 {total_cost:.2f} 元）',
        'data': {'id': cost_id, 'total_cost': total_cost},
    })


@workcost_bp.route('/months/<int:cost_id>', methods=['DELETE'])
@require_permission('workhour.manage')
def delete_month(cost_id):
    """删除月度成本（连同其分配明细）。"""
    payload = request.current_user
    db = get_db()
    row = db.execute("SELECT * FROM dept_month_costs WHERE id=?", (cost_id,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '记录不存在', 'data': None})
    db.execute("DELETE FROM dept_hour_allocations WHERE cost_id=?", (cost_id,))
    db.execute("DELETE FROM dept_month_costs WHERE id=?", (cost_id,))
    db.commit()
    record_operation_log(
        payload['username'], '删除', '工时分摊',
        f'删除 {row["dept"]} {row["month"]} 月度成本及分配明细'
    )
    return jsonify({'code': 200, 'message': '已删除', 'data': None})


# ============================================================
# 工时分配
# ============================================================
@workcost_bp.route('/months/<int:cost_id>/contracts', methods=['GET'])
@require_permission(('workhour.view', 'workhour.manage'))
def alloc_contracts(cost_id):
    """分配工作台：月度信息 + 合同 + 已分配明细。

    默认返回所有执行中+已完成的合同，支持 status 参数筛选。
    """
    db = get_db()
    mc = db.execute("SELECT * FROM dept_month_costs WHERE id=?", (cost_id,)).fetchone()
    if not mc:
        return jsonify({'code': 404, 'message': '月度记录不存在', 'data': None})

    status_filter = (request.args.get('status') or '').strip()
    params = []
    where = "WHERE c.status IN ('执行中', '已完成')"
    if status_filter in ('执行中', '已完成'):
        where = "WHERE c.status = ?"
        params.append(status_filter)

    contracts = db.execute("""
        SELECT c.id, c.contract_name, c.contract_no, c.total_amt, c.status,
               c.sign_date, c.estimated_hours,
               u.name as owner_name, cu.company as customer_name,
               (SELECT COALESCE(SUM(a2.hours),0) FROM dept_hour_allocations a2 WHERE a2.contract_id=c.id) as total_allocated_hours
        FROM contracts c
        LEFT JOIN users u ON c.owner_id = u.username
        LEFT JOIN customers cu ON c.cust_id = cu.id
        """ + where + """
        ORDER BY (c.status='执行中') DESC, c.sign_date DESC
    """, params).fetchall()

    allocs = db.execute("""
        SELECT a.id, a.contract_id, a.hours, a.note
        FROM dept_hour_allocations a WHERE a.cost_id=?
    """, (cost_id,)).fetchall()
    alloc_by_contract = {a['contract_id']: dict(a) for a in allocs}

    data = []
    for c in contracts:
        item = dict(c)
        a = alloc_by_contract.get(c['id'])
        item['alloc_id'] = a['id'] if a else None
        item['alloc_hours'] = a['hours'] if a else 0
        item['alloc_note'] = a['note'] if a else ''
        data.append(item)

    alloc_map = _alloc_map_by_cost(db, [cost_id])
    return jsonify({
        'code': 200, 'message': 'success',
        'data': {
            'month_cost': _month_cost_with_stats(mc, alloc_map),
            'contracts': data,
        },
    })


@workcost_bp.route('/months/<int:cost_id>/allocate', methods=['POST'])
@require_permission('workhour.manage')
def allocate(cost_id):
    """保存分配明细（覆盖式：以本次提交为准）。

    body: {items: [{contract_id, hours, note}]}
    校验：合同必须是执行中；hours≥0；合计不得超过月度总工时。
    """
    payload = request.current_user
    body = request.get_json(silent=True) or {}
    items = body.get('items') or []

    db = get_db()
    mc = db.execute("SELECT * FROM dept_month_costs WHERE id=?", (cost_id,)).fetchone()
    if not mc:
        return jsonify({'code': 404, 'message': '月度记录不存在', 'data': None})

    total_hours = float(mc['total_hours'] or 0)
    valid_ids = {
        r['id'] for r in db.execute(
            "SELECT id FROM contracts WHERE status IN ('执行中', '已完成')"
        ).fetchall()
    }

    cleaned = []
    seen = set()
    for it in items:
        try:
            cid = int(it.get('contract_id'))
            h = float(it.get('hours') or 0)
        except (TypeError, ValueError):
            return jsonify({'code': 400, 'message': '分配数据格式错误', 'data': None})
        if cid in seen:
            return jsonify({'code': 400, 'message': '存在重复合同行', 'data': None})
        seen.add(cid)
        if h < 0:
            return jsonify({'code': 400, 'message': '分配工时不能为负数', 'data': None})
        if h == 0:
            continue  # 0 工时 = 清除该合同分配
        if cid not in valid_ids:
            return jsonify({'code': 400, 'message': '只能分配到执行中或已完成的合同', 'data': None})
        cleaned.append({'contract_id': cid, 'hours': round(h, 2),
                        'note': (it.get('note') or '').strip()})

    sum_hours = round(sum(x['hours'] for x in cleaned), 2)
    if sum_hours > total_hours + 0.009:
        return jsonify({
            'code': 400,
            'message': f'分配工时合计 {sum_hours} 超过本月总工时 {total_hours}',
            'data': None,
        })

    now = datetime.now().isoformat(sep=' ', timespec='seconds')
    db.execute("DELETE FROM dept_hour_allocations WHERE cost_id=?", (cost_id,))
    for x in cleaned:
        db.execute(
            "INSERT INTO dept_hour_allocations (cost_id, contract_id, hours, note, created_by, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (cost_id, x['contract_id'], x['hours'], x['note'], payload['username'], now)
        )
    db.commit()

    unit_cost = round(
        sum(float(mc[f] or 0) for f, _ in COST_FIELDS) / total_hours, 4
    ) if total_hours > 0 else 0
    record_operation_log(
        payload['username'], '分配', '工时分摊',
        f'{mc["dept"]} {mc["month"]}：分配 {len(cleaned)} 个合同共 {sum_hours} 工时'
        f'（单工时成本 {unit_cost} 元）'
    )
    return jsonify({
        'code': 200,
        'message': f'已保存分配：{len(cleaned)} 个合同 / {sum_hours} 工时',
        'data': {'sum_hours': sum_hours, 'unit_cost': unit_cost,
                 'allocated_cost': round(sum_hours * unit_cost, 2)},
    })


# ============================================================
# 分摊汇总
# ============================================================
@workcost_bp.route('/summary', methods=['GET'])
@require_permission(('workhour.view', 'workhour.manage'))
def summary():
    """按合同汇总分摊：跨月累计分配工时与分摊成本。可按 year/dept 筛选。"""
    db = get_db()
    year = request.args.get('year', '').strip()
    dept = request.args.get('dept', '').strip()

    sql = f"""
        SELECT c.id as contract_id, c.contract_name, c.contract_no, c.status,
               cu.company as customer_name, u.name as owner_name,
               COALESCE(SUM(a.hours), 0) as total_hours,
               COALESCE(SUM(a.hours * ({COST_SUM_SQL}) / NULLIF(m.total_hours, 0)), 0) as total_cost,
               COUNT(DISTINCT m.month) as month_count
        FROM dept_hour_allocations a
        JOIN dept_month_costs m ON a.cost_id = m.id
        JOIN contracts c ON a.contract_id = c.id
        LEFT JOIN customers cu ON c.cust_id = cu.id
        LEFT JOIN users u ON c.owner_id = u.username
        WHERE 1=1
    """
    params = []
    if year:
        sql += " AND m.month LIKE ?"
        params.append(f'{year}-%')
    if dept:
        sql += " AND m.dept=?"
        params.append(dept)
    sql += " GROUP BY c.id ORDER BY total_cost DESC"

    rows = [dict(r) for r in db.execute(sql, params).fetchall()]
    for r in rows:
        r['total_hours'] = round(float(r['total_hours']), 2)
        r['total_cost'] = round(float(r['total_cost']), 2)

    totals = {
        'hours': round(sum(r['total_hours'] for r in rows), 2),
        'cost': round(sum(r['total_cost'] for r in rows), 2),
    }
    return jsonify({'code': 200, 'message': 'success',
                    'data': {'items': rows, 'totals': totals}})


@workcost_bp.route('/detail', methods=['GET'])
@require_permission(('workhour.view', 'workhour.manage'))
def detail():
    """月度分配明细：每行 = 某月某部门对某合同的分配（工时、单工时成本、分摊金额）。

    可按 year / month / dept 筛选，供前端"按月度明细"视图使用。
    """
    db = get_db()
    year = request.args.get('year', '').strip()
    month = request.args.get('month', '').strip()
    dept = request.args.get('dept', '').strip()

    sql = f"""
        SELECT m.id as cost_id, m.month, m.dept, m.total_hours,
               ({COST_SUM_SQL}) as month_total_cost,
               c.id as contract_id, c.contract_name, c.contract_no, c.status,
               cu.company as customer_name, u.name as owner_name,
               a.hours, a.note
        FROM dept_hour_allocations a
        JOIN dept_month_costs m ON a.cost_id = m.id
        JOIN contracts c ON a.contract_id = c.id
        LEFT JOIN customers cu ON c.cust_id = cu.id
        LEFT JOIN users u ON c.owner_id = u.username
        WHERE 1=1
    """
    params = []
    if month:
        sql += " AND m.month = ?"
        params.append(month)
    elif year:
        sql += " AND m.month LIKE ?"
        params.append(f'{year}-%')
    if dept:
        sql += " AND m.dept = ?"
        params.append(dept)
    sql += " ORDER BY m.month DESC, m.dept, (a.hours * (" + COST_SUM_SQL + ") / NULLIF(m.total_hours,0)) DESC"

    items = []
    for r in db.execute(sql, params).fetchall():
        d = dict(r)
        total_cost = round(float(d.pop('month_total_cost') or 0), 2)
        th = float(d['total_hours'] or 0)
        unit = round(total_cost / th, 4) if th > 0 else 0
        hours = float(d['hours'] or 0)
        d['month_total_cost'] = total_cost
        d['unit_cost'] = unit
        d['hours'] = round(hours, 2)
        d['alloc_cost'] = round(hours * unit, 2)
        items.append(d)

    totals = {
        'hours': round(sum(i['hours'] for i in items), 2),
        'cost': round(sum(i['alloc_cost'] for i in items), 2),
    }
    return jsonify({'code': 200, 'message': 'success', 'data': {'items': items, 'totals': totals}})


@workcost_bp.route('/summary/export', methods=['GET'])
@require_permission(('workhour.view', 'workhour.manage'))
def export_summary():
    """导出分摊汇总 Excel（按合同，含分部门明细 sheet）。"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    db = get_db()
    year = request.args.get('year', '').strip()
    dept = request.args.get('dept', '').strip()

    wb = Workbook()

    # Sheet1 按合同汇总
    ws = wb.active
    ws.title = '分摊汇总(按合同)'
    headers = ['合同名称', '合同编号', '客户', '负责人', '合同状态',
               '累计分配工时', '累计分摊成本(元)', '涉及月份数']
    ws.append(headers)
    head_fill = PatternFill('solid', fgColor='1F4E79')
    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = head_fill
        cell.alignment = Alignment(horizontal='center')

    sql = f"""
        SELECT c.contract_name, c.contract_no, cu.company as customer_name,
               u.name as owner_name, c.status,
               COALESCE(SUM(a.hours),0) as total_hours,
               COALESCE(SUM(a.hours * ({COST_SUM_SQL}) / NULLIF(m.total_hours,0)),0) as total_cost,
               COUNT(DISTINCT m.month) as month_count
        FROM dept_hour_allocations a
        JOIN dept_month_costs m ON a.cost_id = m.id
        JOIN contracts c ON a.contract_id = c.id
        LEFT JOIN customers cu ON c.cust_id = cu.id
        LEFT JOIN users u ON c.owner_id = u.username
        WHERE 1=1
    """
    params = []
    if year:
        sql += " AND m.month LIKE ?"
        params.append(f'{year}-%')
    if dept:
        sql += " AND m.dept=?"
        params.append(dept)
    sql += " GROUP BY c.id ORDER BY total_cost DESC"
    rows = db.execute(sql, params).fetchall()

    total_cost_all = 0.0
    for r in rows:
        cost = round(float(r['total_cost']), 2)
        total_cost_all += cost
        ws.append([r['contract_name'], r['contract_no'] or '', r['customer_name'] or '',
                   r['owner_name'] or '', r['status'] or '',
                   round(float(r['total_hours']), 2), cost, r['month_count']])
    # 合计行
    sum_row = ['合计', '', '', '', '', '', round(total_cost_all, 2), '']
    ws.append(sum_row)
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True)
    for i, width in enumerate([38, 18, 24, 10, 10, 14, 18, 12], 1):
        ws.column_dimensions[get_column_letter(i)].width = width

    # Sheet2 按部门月份明细
    ws2 = wb.create_sheet('月度分配明细')
    ws2.append(['部门', '月份', '总工时', '人力成本合计(元)', '单工时成本(元)',
                '分配合同', '分配工时', '分摊成本(元)', '备注'])
    for cell in ws2[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = head_fill
        cell.alignment = Alignment(horizontal='center')

    sql2 = f"""
        SELECT m.dept, m.month, m.total_hours, ({COST_SUM_SQL}) as total_cost,
               c.contract_name, a.hours, a.note
        FROM dept_hour_allocations a
        JOIN dept_month_costs m ON a.cost_id = m.id
        JOIN contracts c ON a.contract_id = c.id
        WHERE 1=1
    """
    params2 = []
    if year:
        sql2 += " AND m.month LIKE ?"
        params2.append(f'{year}-%')
    if dept:
        sql2 += " AND m.dept=?"
        params2.append(dept)
    sql2 += " ORDER BY m.month DESC, m.dept, a.hours DESC"
    for r in db.execute(sql2, params2).fetchall():
        total_cost = round(float(r['total_cost']), 2)
        th = float(r['total_hours'] or 0)
        unit = round(total_cost / th, 4) if th > 0 else 0
        ws2.append([
            r['dept'], r['month'], th, total_cost, unit,
            r['contract_name'], round(float(r['hours']), 2),
            round(float(r['hours']) * unit, 2), r['note'] or '',
        ])
    for i, width in enumerate([12, 10, 10, 16, 14, 38, 10, 14, 24], 1):
        ws2.column_dimensions[get_column_letter(i)].width = width

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    payload = request.current_user
    record_operation_log(payload['username'], '导出', '工时分摊', '导出工时成本分摊汇总Excel')
    fname = f'工时成本分摊_{year or "全部"}.xlsx'
    return send_file(
        buf, as_attachment=True, download_name=fname,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
