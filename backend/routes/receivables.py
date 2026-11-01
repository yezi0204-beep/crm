# -*- coding: utf-8 -*-
"""两金明细表（应收账款 + 合同资产）。

业务口径（已确认）：
  应收账款 = 含税收入（累计验收额 + 总税额） - 已回款金额
  合同资产 = 合同总额 - 含税收入（即待验收合同额）
  形成应收账款日期 = 该合同最早一条验收记录的 acceptance_date
  账龄分档（按快照日）：1年内 / 1-2年 / 2-3年 / 3年以上
  回款风险自动评级：1年内=低 / 1-2年=中 / >=2年=高（人工可改）

季度末（3/31、6/30、9/30、12/31）scheduler 自动落库 receivable_snapshots；
人工填报写 receivable_overrides（按 quarter+contract_id 隔离，跨季度不污染）。
"""
import json
import logging
from datetime import datetime, date
from io import BytesIO

from flask import request, jsonify, send_file

from extensions import (
    get_db, token_required, user_can, record_operation_log,
)
from .custom_fields import parse_ext
from . import receivables_bp

logger = logging.getLogger(__name__)

CUSTOMER_NATURES = [
    '国内地方客户-地方国企', '国内地方客户-政府', '国内地方客户-民企',
    '国内地方客户-其它事业单位', '集团内', '子集团内',
]
UNFILLED_LABEL = '未填报'  # 客户性质未人工填报时的展示文案
RISK_LEVELS = ['低', '中', '高']


def register_routes(app):
    app.register_blueprint(receivables_bp, url_prefix='/api/receivables')


# ============================================================
# 工具函数
# ============================================================
def _parse_date(s):
    if not s or not isinstance(s, str):
        return None
    s = s.strip()[:10]
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        return None


def _aging_bucket(first_date, snapshot_date):
    """账龄分档：按 snapshot_date - first_date 的年数。"""
    if not first_date or not snapshot_date:
        return ''
    days = (snapshot_date - first_date).days
    if days < 365:
        return '1年以内'
    if days < 365 * 2:
        return '1-2年'
    if days < 365 * 3:
        return '2-3年'
    return '3年以上'


def _auto_risk(aging_bucket):
    """自动回款风险评级：按账龄。"""
    return {'1年以内': '低', '1-2年': '中', '2-3年': '高', '3年以上': '高'}.get(aging_bucket, '低')


def _quarter_of(d):
    """'2026-09-30' → '2026Q3'"""
    return f'{d.year}Q{(d.month - 1) // 3 + 1}'


def _current_quarter():
    return _quarter_of(date.today())


def _fetch_contract_rows(cursor):
    """只从「合同管理 / 验收管理 / 回款管理」三处取数：

    - 合同总额、合同编号、项目名称、往来单位（party_a）→ contracts
    - 累计验收额、税额、形成应收账款日期 → contract_acceptances
    - 已回款金额 → payment_records

    不使用 contracts.paid_amt / contracts.income 等缓存汇总字段，避免与三个
    业务模块的实际明细不一致。
    """
    cursor.execute("""
        SELECT c.id, c.cust_id, c.contract_name, c.contract_no, c.party_a, c.total_amt,
               c.owner_id, u.name AS owner_name,
               COALESCE(a.acc_amt, 0) AS acc_amt,
               COALESCE(a.tax_amt, 0) AS tax_amt,
               a.first_acc_date,
               COALESCE(p.paid_amt, 0) AS paid_amt
        FROM contracts c
        LEFT JOIN users u ON c.owner_id = u.username
        LEFT JOIN (
          SELECT contract_id,
                 SUM(acceptance_amount) AS acc_amt,
                 SUM(tax_amount) AS tax_amt,
                 MIN(NULLIF(acceptance_date, '')) AS first_acc_date
          FROM contract_acceptances GROUP BY contract_id
        ) a ON a.contract_id = c.id
        LEFT JOIN (
          SELECT contract_id, SUM(amount) AS paid_amt
          FROM payment_records GROUP BY contract_id
        ) p ON p.contract_id = c.id
        WHERE c.status <> '作废'
          AND (a.first_acc_date IS NOT NULL OR p.paid_amt IS NOT NULL)
        ORDER BY c.id
    """)
    return [dict(r) for r in cursor.fetchall()]


def _row_to_snapshot(r, snapshot_date):
    """从装配行计算快照字段。"""
    total_amt = float(r.get('total_amt') or 0)
    paid_amt = float(r.get('paid_amt') or 0)      # 来自回款管理
    acc_amt = float(r.get('acc_amt') or 0)        # 来自验收管理
    tax_amt = float(r.get('tax_amt') or 0)        # 来自验收管理
    income = acc_amt + tax_amt  # 含税收入

    receivable = round(income - paid_amt, 2)
    contract_asset = round(total_amt - income, 2)

    ar_date = r.get('first_acc_date')  # 'YYYY-MM-DD'
    first_d = _parse_date(ar_date)
    aging = _aging_bucket(first_d, snapshot_date)
    auto_risk = _auto_risk(aging)

    return {
        'contract_id': r['id'],
        'cust_id': r.get('cust_id') or 0,
        'customer_name': r.get('party_a') or '',
        # 客户性质由人工在表内填报（存 receivable_overrides），快照不预设
        'customer_nature': '',
        'project_name': r.get('contract_name') or '',
        'contract_no': r.get('contract_no') or '',
        'owner_id': r.get('owner_id') or '',
        'owner_name': r.get('owner_name') or '',
        'receivable': receivable,
        'contract_asset': contract_asset,
        'ar_date': ar_date,
        'aging_bucket': aging,
        'auto_risk': auto_risk,
    }


# ============================================================
# 快照生成（供 scheduler 与手动触发共用）
# ============================================================
def snapshot_quarter(snapshot_date_str, quarter=None, db_conn=None):
    """生成指定日期的季度快照，落库 receivable_snapshots。

    Args:
        snapshot_date_str: 'YYYY-MM-DD'
        quarter: 可选，默认按 snapshot_date 推导
        db_conn: 可选，复用外部连接；不传则新建并自行 commit/close
    Returns:
        写入条数
    """
    snapshot_date = _parse_date(snapshot_date_str)
    if not snapshot_date:
        raise ValueError(f'无效的快照日期: {snapshot_date_str}')
    quarter = quarter or _quarter_of(snapshot_date)

    own_conn = db_conn is None
    conn = db_conn or get_db()
    cur = conn.cursor()

    rows = _fetch_contract_rows(cur)
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    written = 0
    for r in rows:
        s = _row_to_snapshot(r, snapshot_date)
        cur.execute("""
            INSERT INTO receivable_snapshots
              (quarter, snapshot_date, contract_id, cust_id, customer_name,
               customer_nature, project_name, contract_no, owner_id, owner_name,
               receivable, contract_asset, ar_date, aging_bucket, auto_risk, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON DUPLICATE KEY UPDATE
              snapshot_date=VALUES(snapshot_date), cust_id=VALUES(cust_id),
              customer_name=VALUES(customer_name), customer_nature=VALUES(customer_nature),
              project_name=VALUES(project_name), contract_no=VALUES(contract_no),
              owner_id=VALUES(owner_id), owner_name=VALUES(owner_name),
              receivable=VALUES(receivable), contract_asset=VALUES(contract_asset),
              ar_date=VALUES(ar_date), aging_bucket=VALUES(aging_bucket),
              auto_risk=VALUES(auto_risk)
        """, (
            quarter, snapshot_date_str, s['contract_id'], s['cust_id'], s['customer_name'],
            s['customer_nature'], s['project_name'], s['contract_no'],
            s['owner_id'], s['owner_name'],
            s['receivable'], s['contract_asset'], s['ar_date'], s['aging_bucket'],
            s['auto_risk'], now_str,
        ))
        written += 1
    if own_conn:
        conn.commit()
    logger.info(f'[receivables] snapshot_quarter {quarter} @ {snapshot_date_str}: {written} 条')
    return written


# ============================================================
# 接口
# ============================================================
def _fetch_monthly_forecast_map(cur, contract_ids, snapshot_year=None, snapshot_quarter=None):
    """从合同管理月度预计回款表装配回款计划：
    按 季度快照 对应的 3 个月取数，金额单位为元（与合同管理填报口径一致），日期=该月最后一天。

    Returns: { contract_id: [{node, amt, date}, ...] }（仅包含非零月份，按月份排序）
    """
    if not contract_ids:
        return {}
    # 解析季度 → [起始月, 结束月]
    if snapshot_year and snapshot_quarter:
        try:
            year = int(snapshot_year)
            q = int(snapshot_quarter)
        except (TypeError, ValueError):
            return {}
    else:
        return {}
    months = {1: [1, 2, 3], 2: [4, 5, 6], 3: [7, 8, 9], 4: [10, 11, 12]}.get(q, [])
    if not months:
        return {}

    placeholders = ','.join(['?'] * len(contract_ids))
    m_ph = ','.join(['?'] * len(months))
    cur.execute(f"""
        SELECT contract_id, year, month, expected_payment
        FROM contract_monthly_forecast
        WHERE contract_id IN ({placeholders}) AND year = ? AND month IN ({m_ph})
        ORDER BY contract_id, month
    """, (*contract_ids, year, *months))

    import calendar
    result = {}
    for r in cur.fetchall():
        ep = float(r.get('expected_payment') or 0)
        if ep == 0:
            continue
        amt = round(ep, 2)  # 单位元（与合同管理月度预计回款填报口径一致）
        m = int(r['month'])
        last_day = calendar.monthrange(year, m)[1]
        date_str = f'{year}-{m:02d}-{last_day:02d}'
        result.setdefault(r['contract_id'], []).append({
            'node': f'{m}月预计回款',
            'amt': amt,
            'date': date_str,
        })
    return result


@receivables_bp.route('', methods=['GET'])
@token_required
def list_receivables():
    """查询两金明细（默认最新季度）。

    Query:
        quarter: '2026Q3'，缺省返回最新季度
    """
    quarter = request.args.get('quarter', '').strip()

    payload = request.current_user
    vis_sql, vis_params = _visibility_clause(payload)

    db = get_db()
    cur = db.cursor()

    if not quarter:
        cur.execute(f"""
            SELECT DISTINCT s.quarter FROM receivable_snapshots s
            WHERE 1=1{vis_sql} ORDER BY s.quarter DESC LIMIT 1
        """, vis_params)
        row = cur.fetchone()
        quarter = row['quarter'] if row else _current_quarter()

    sql = f"""
        SELECT s.*, o.customer_nature AS override_nature,
               o.cust_risk, o.payback_risk, o.payback_plan,
               o.updated_by AS override_by, o.updated_at AS override_at
        FROM receivable_snapshots s
        LEFT JOIN receivable_overrides o
          ON o.quarter = s.quarter AND o.contract_id = s.contract_id
        WHERE s.quarter = ?{vis_sql}
        ORDER BY s.customer_name, s.contract_id
    """
    cur.execute(sql, [quarter, *vis_params])
    items = []
    for r in cur.fetchall():
        it = dict(r)
        # 客户性质：人工填报优先，未填报返回空串（前端展示「未填报」）
        it['customer_nature'] = it.pop('override_nature', None) or it.get('customer_nature') or ''
        items.append(it)

    # 装配月度预计回款：仅当该合同人工回款计划为空时，从合同管理按月计划自动生成
    # 季度格式 '2026Q4' → year=2026, q=4
    year_q, q_num = None, None
    if len(quarter) >= 6 and quarter[4].upper() == 'Q':
        year_q, q_num = quarter[:4], quarter[5]
    no_plan_cids = [i['contract_id'] for i in items if not i.get('payback_plan')]
    auto_plans = _fetch_monthly_forecast_map(cur, no_plan_cids, year_q, q_num)
    for it in items:
        if not it.get('payback_plan') and it['contract_id'] in auto_plans:
            it['payback_plan'] = json.dumps(auto_plans[it['contract_id']], ensure_ascii=False)
            it['plan_from_forecast'] = True  # 标记：来自合同管理月度预计回款，非人工填报

    # 汇总
    total_recv = round(sum(float(i.get('receivable') or 0) for i in items), 2)
    total_asset = round(sum(float(i.get('contract_asset') or 0) for i in items), 2)

    # 可用季度列表（按可见性过滤）
    cur.execute(f"""
        SELECT DISTINCT s.quarter FROM receivable_snapshots s
        WHERE 1=1{vis_sql} ORDER BY s.quarter DESC
    """, vis_params)
    quarters = [r['quarter'] for r in cur.fetchall()]

    return jsonify({'code': 200, 'message': 'success', 'data': {
        'quarter': quarter,
        'quarters': quarters,
        'items': items,
        'summary': {
            'receivable': total_recv,
            'contract_asset': total_asset,
            'total': round(total_recv + total_asset, 2),
            'count': len(items),
        },
    }})


@receivables_bp.route('/snapshot/preview', methods=['POST'])
@token_required
def preview_snapshot():
    """预览快照：对比当前库中快照与按当前业务数据算出的新快照差异，不写库。

    Returns:
        quarter, snapshot_date, current_count, new_count,
        changes: [{contract_id, customer_name, project_name, change_type, diffs: {field: {old, new}}}]
                 change_type: added / removed / modified
        identical: True 表示无任何差异
    """
    payload = request.current_user
    if not (user_can(payload['username'], 'data.view_all') or payload.get('role') in ('主任', '院长', '财务')):
        return jsonify({'code': 403, 'message': '仅财务/主任/院长可预览快照', 'data': None})

    body = request.get_json(silent=True) or {}
    date_str = (body.get('snapshot_date') or '').strip() or date.today().strftime('%Y-%m-%d')
    snapshot_date = _parse_date(date_str)
    if not snapshot_date:
        return jsonify({'code': 400, 'message': f'无效的快照日期: {date_str}', 'data': None})
    quarter = _quarter_of(snapshot_date)

    db = get_db()
    cur = db.cursor()

    # 当前库中该季度快照
    cur.execute("""
        SELECT contract_id, customer_name, project_name, contract_no,
               receivable, contract_asset, ar_date
        FROM receivable_snapshots WHERE quarter = ?
    """, (quarter,))
    existing = {r['contract_id']: dict(r) for r in cur.fetchall()}

    # 按当前业务数据重新计算
    rows = _fetch_contract_rows(cur)
    new_map = {}
    for r in rows:
        s = _row_to_snapshot(r, snapshot_date)
        new_map[s['contract_id']] = s

    # 比对
    cmp_fields = [('customer_name', '往来单位'), ('project_name', '项目名称'),
                  ('contract_no', '合同编号'), ('owner_name', '项目负责人'),
                  ('receivable', '应收账款'), ('contract_asset', '合同资产'),
                  ('ar_date', '形成应收账款日期')]

    changes = []
    # 新增 / 修改
    for cid, s in new_map.items():
        old = existing.get(cid)
        if not old:
            changes.append({
                'contract_id': cid,
                'customer_name': s['customer_name'],
                'project_name': s['project_name'],
                'change_type': 'added',
                'diffs': {},
            })
            continue
        diffs = {}
        for key, label in cmp_fields:
            ov = old.get(key)
            nv = s.get(key)
            if key in ('receivable', 'contract_asset'):
                if abs(float(ov or 0) - float(nv or 0)) > 0.005:
                    diffs[key] = {'label': label, 'old': round(float(ov or 0), 2), 'new': round(float(nv or 0), 2)}
            else:
                if (ov or '') != (nv or ''):
                    diffs[key] = {'label': label, 'old': ov or '', 'new': nv or ''}
        if diffs:
            changes.append({
                'contract_id': cid,
                'customer_name': s['customer_name'],
                'project_name': s['project_name'],
                'change_type': 'modified',
                'diffs': diffs,
            })
    # 减少
    for cid, old in existing.items():
        if cid not in new_map:
            changes.append({
                'contract_id': cid,
                'customer_name': old['customer_name'],
                'project_name': old['project_name'],
                'change_type': 'removed',
                'diffs': {},
            })

    return jsonify({'code': 200, 'message': 'success', 'data': {
        'quarter': quarter,
        'snapshot_date': date_str,
        'current_count': len(existing),
        'new_count': len(new_map),
        'identical': not changes,
        'changes': changes,
    }})


@receivables_bp.route('/snapshot', methods=['POST'])
@token_required
def create_snapshot():
    """手动触发当前季度（或指定日期）快照。"""
    payload = request.current_user
    if not (user_can(payload['username'], 'data.view_all') or payload.get('role') in ('主任', '院长', '财务')):
        return jsonify({'code': 403, 'message': '仅财务/主任/院长可手动生成快照', 'data': None})

    body = request.get_json(silent=True) or {}
    date_str = (body.get('snapshot_date') or '').strip() or date.today().strftime('%Y-%m-%d')

    db = get_db()
    try:
        n = snapshot_quarter(date_str, db_conn=db)
        db.commit()
    except ValueError as e:
        return jsonify({'code': 400, 'message': str(e), 'data': None})
    except Exception as e:
        db.rollback()
        logger.exception('两金快照生成失败')
        return jsonify({'code': 500, 'message': f'快照生成失败: {e}', 'data': None})

    record_operation_log(payload['username'], '两金明细表', '生成快照',
                         f'季度 {_quarter_of(_parse_date(date_str))} 共 {n} 条')
    return jsonify({'code': 200, 'message': 'success',
                    'data': {'quarter': _quarter_of(_parse_date(date_str)),
                             'snapshot_date': date_str, 'count': n}})


@receivables_bp.route('/override/<int:contract_id>', methods=['PUT'])
@token_required
def save_override(contract_id):
    """保存人工填报：客户性质/客户风险/回款风险/更新回款计划。

    只更新请求体中出现的字段，未出现的字段保持原值。
    """
    payload = request.current_user
    username = payload['username']
    body = request.get_json(silent=True) or {}
    quarter = (body.get('quarter') or '').strip() or _current_quarter()

    cust_risk = body.get('cust_risk')
    payback_risk = body.get('payback_risk')
    payback_plan = body.get('payback_plan')
    customer_nature = body.get('customer_nature')

    if customer_nature is not None and customer_nature not in CUSTOMER_NATURES and customer_nature != '':
        return jsonify({'code': 400, 'message': '客户性质取值不合法', 'data': None})
    if cust_risk is not None and cust_risk not in RISK_LEVELS and cust_risk != '':
        return jsonify({'code': 400, 'message': f'客户风险必须是 {"|".join(RISK_LEVELS)}', 'data': None})
    if payback_risk is not None and payback_risk not in RISK_LEVELS and payback_risk != '':
        return jsonify({'code': 400, 'message': f'回款风险必须是 {"|".join(RISK_LEVELS)}', 'data': None})

    # payback_plan 接受 list 或 JSON 字符串
    plan_str = None
    if payback_plan is not None:
        if isinstance(payback_plan, list):
            plan_str = json.dumps(payback_plan, ensure_ascii=False)
        elif isinstance(payback_plan, str):
            plan_str = payback_plan
        else:
            return jsonify({'code': 400, 'message': 'payback_plan 格式错误', 'data': None})

    db = get_db()
    cur = db.cursor()

    # 可见性校验：非管理角色只能填报自己负责的合同
    if not _is_receivables_admin(payload):
        cur.execute("SELECT owner_id FROM contracts WHERE id = ?", (contract_id,))
        row = cur.fetchone()
        if not row or row['owner_id'] != username:
            return jsonify({'code': 403, 'message': '仅可填报自己负责的项目', 'data': None})

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        cur.execute("""
            INSERT INTO receivable_overrides
              (quarter, contract_id, customer_nature, cust_risk, payback_risk, payback_plan, updated_by, updated_at)
            VALUES (?,?,?,?,?,?,?,?)
            ON DUPLICATE KEY UPDATE
              customer_nature=COALESCE(VALUES(customer_nature), customer_nature),
              cust_risk=COALESCE(VALUES(cust_risk), cust_risk),
              payback_risk=COALESCE(VALUES(payback_risk), payback_risk),
              payback_plan=COALESCE(VALUES(payback_plan), payback_plan),
              updated_by=VALUES(updated_by), updated_at=VALUES(updated_at)
        """, (quarter, contract_id, customer_nature, cust_risk, payback_risk,
              plan_str, username, now_str))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception('两金人工填报保存失败')
        return jsonify({'code': 500, 'message': f'保存失败: {e}', 'data': None})

    record_operation_log(username, '两金明细表', '人工填报',
                         f'季度 {quarter} 合同 {contract_id}')
    return jsonify({'code': 200, 'message': 'success', 'data': {'quarter': quarter, 'contract_id': contract_id}})


@receivables_bp.route('/export', methods=['GET'])
@token_required
def export_receivables():
    """导出 Excel。"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    quarter = request.args.get('quarter', '').strip()
    payload = request.current_user
    vis_sql, vis_params = _visibility_clause(payload)
    db = get_db()
    cur = db.cursor()
    if not quarter:
        cur.execute(f"""
            SELECT DISTINCT s.quarter FROM receivable_snapshots s
            WHERE 1=1{vis_sql} ORDER BY s.quarter DESC LIMIT 1
        """, vis_params)
        row = cur.fetchone()
        quarter = row['quarter'] if row else _current_quarter()

    cur.execute(f"""
        SELECT s.*, o.customer_nature AS override_nature,
               o.cust_risk, o.payback_risk, o.payback_plan
        FROM receivable_snapshots s
        LEFT JOIN receivable_overrides o
          ON o.quarter = s.quarter AND o.contract_id = s.contract_id
        WHERE s.quarter = ?{vis_sql}
        ORDER BY s.customer_name, s.contract_id
    """, (quarter, *vis_params))
    items = []
    for r in cur.fetchall():
        it = dict(r)
        it['customer_nature'] = it.pop('override_nature', None) or it.get('customer_nature') or UNFILLED_LABEL
        items.append(it)

    wb = Workbook()
    ws = wb.active
    ws.title = f'两金明细表_{quarter}'

    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
    header_align = Alignment(horizontal='center', vertical='center')
    title_align = Alignment(horizontal='center', vertical='center')

    snapshot_date = items[0].get('snapshot_date', '') if items else ''
    # 标题行：两金明细表（截至导出的快照日）
    ws.append([f'两金明细表（截至{snapshot_date.replace("-", ".")}）'])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=12)
    ws.cell(row=1, column=1).font = Font(bold=True, size=14)
    ws.cell(row=1, column=1).alignment = title_align
    # 单位行
    ws.append(['单位：元'])
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=12)
    ws.cell(row=2, column=1).alignment = Alignment(horizontal='right', vertical='center')

    headers = ['往来单位', '子集团内/集团内/集团外', '项目名称', '合同编号', '项目负责人', '形成应收账款日期',
               '合同资产(元)', '应收账款(元)', '账龄情况', '客户风险(高/中/低)',
               '回款风险(高/中/低)', '更新回款计划（节点+金额+日期）']
    ws.append(headers)
    for cell in ws[3]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align

    for it in items:
        # 回款计划：JSON 解析为易读文本
        plan_text = ''
        raw_plan = it.get('payback_plan')
        if raw_plan:
            try:
                plans = json.loads(raw_plan) if isinstance(raw_plan, str) else raw_plan
                if isinstance(plans, list):
                    plan_text = '; '.join(
                        f"{p.get('node','')} {p.get('amt','')}元 {p.get('date','')}" for p in plans)
            except (ValueError, TypeError):
                plan_text = str(raw_plan)
        ws.append([
            it.get('customer_name') or '',
            it.get('customer_nature') or '',
            it.get('project_name') or '',
            it.get('contract_no') or '',
            it.get('owner_name') or '',
            it.get('ar_date') or '',
            round(float(it.get('contract_asset') or 0), 2),
            round(float(it.get('receivable') or 0), 2),
            it.get('aging_bucket') or '',
            it.get('cust_risk') or '',
            it.get('payback_risk') or it.get('auto_risk') or '',
            plan_text,
        ])

    # 列宽
    for col_idx, width in enumerate([28, 22, 32, 18, 14, 18, 14, 14, 12, 10, 10, 40], start=1):
        ws.column_dimensions[chr(64 + col_idx)].width = width

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f'两金明细表_{quarter}_{snapshot_date}_{datetime.now().strftime("%Y%m%d%H%M%S")}.xlsx'
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename,
    )


# ============================================================
# Excel 导入（比对 + 填报）
# ============================================================
# 表头 → 字段映射（表头去掉括号说明后匹配）
_IMPORT_HEADER_MAP = {
    '往来单位': 'customer_name',
    '合同编号': 'contract_no',
    '项目名称': 'project_name',
    '子集团内/集团内/集团外': 'customer_nature',
    '客户性质': 'customer_nature',
    '客户风险': 'cust_risk',
    '回款风险': 'payback_risk',
    '更新回款计划': 'payback_plan',
}
_IMPORT_FIELDS = [
    ('customer_nature', '客户性质'),
    ('cust_risk', '客户风险'),
    ('payback_risk', '回款风险'),
    ('payback_plan', '更新回款计划'),
]


def _require_import_perm(payload):
    if not (user_can(payload['username'], 'data.view_all') or payload.get('role') in ('主任', '院长', '财务')):
        return jsonify({'code': 403, 'message': '仅财务/主任/院长可导入两金填报', 'data': None})
    return None


def _is_receivables_admin(payload):
    """两金管理角色：看全部数据 + 可生成快照/导入。"""
    return (user_can(payload['username'], 'data.view_all')
            or user_can(payload['username'], 'contracts.view_all')
            or payload.get('role') in ('主任', '院长', '财务'))


def _visibility_clause(payload):
    """两金数据可见性：管理角色（财务/主任/院长/view_all）→ 全部；
    其他用户（销售）→ 仅本人负责的合同（contracts.owner_id = 当前用户）。

    Returns: (sql_fragment, params)，sql_fragment 以 ' AND' 开头，主 SQL 需含 receivable_snapshots s 别名。
    """
    if _is_receivables_admin(payload):
        return '', []
    return " AND s.contract_id IN (SELECT id FROM contracts WHERE owner_id = ?)", [payload['username']]


def _norm_header(h):
    """表头标准化：去空白、去括号说明（如 客户风险(高/中/低) → 客户风险）。"""
    if h is None:
        return ''
    s = str(h).strip()
    for sep in ('（', '('):
        if sep in s:
            s = s.split(sep)[0]
    return ''.join(s.split())


def _cell_str(v):
    """单元格值统一为字符串；日期对象转 YYYY-MM-DD，浮点整数去掉 .0。"""
    if v is None:
        return ''
    if isinstance(v, datetime):
        return v.strftime('%Y-%m-%d')
    if isinstance(v, date):
        return v.strftime('%Y-%m-%d')
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _parse_plan_text(text):
    """把回款计划文本解析回 [{node, amt, date}]。

    支持导出格式「尾款 50000元 2026-11-15; 质保金 20000元 2027-06-30」，
    无法结构化的片段降级存为 {node: 原文}。
    """
    import re
    plans = []
    for seg in re.split(r'[;；\n]', str(text)):
        seg = seg.strip()
        if not seg:
            continue
        m = re.match(
            r'^(.*?)[\s]*([\d,]+(?:\.\d+)?)\s*元?\s*(\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)?$', seg)
        if m and (m.group(2) or m.group(3)):
            node = m.group(1).strip(' ：:') or '回款'
            amt = float(m.group(2).replace(',', '')) if m.group(2) else None
            d = (m.group(3) or '').replace('年', '-').replace('月', '-').replace('日', '')
            plans.append({'node': node, 'amt': amt, 'date': d})
        else:
            plans.append({'node': seg, 'amt': None, 'date': ''})
    return plans


def _format_plan(plans):
    """[{node, amt, date}] → 展示文本。"""
    if not plans:
        return ''
    if isinstance(plans, str):
        try:
            plans = json.loads(plans)
        except (ValueError, TypeError):
            return str(plans)
    if not isinstance(plans, list):
        return str(plans)
    parts = []
    for p in plans:
        if not isinstance(p, dict):
            continue
        amt = p.get('amt')
        amt_str = f'{float(amt):g}元' if amt not in (None, '') else ''
        parts.append(' '.join(x for x in [str(p.get('node') or ''), amt_str, str(p.get('date') or '')] if x))
    return '; '.join(parts)


def _norm_risk(v):
    """风险值标准化：从「高/中/低（默认）」等文本中提取等级，不合法返回 None。"""
    s = _cell_str(v)
    if not s:
        return ''
    for lv in RISK_LEVELS:
        if lv in s:
            return lv
    return None


@receivables_bp.route('/import/preview', methods=['POST'])
@token_required
def import_preview():
    """上传 Excel 解析并与当前季度填报数据比对。

    Form:
        file: xlsx 文件
        quarter: '2026Q3'，缺省最新季度
    Returns:
        rows: 每行匹配结果 + 4 个填报字段的比对动作
              action: fill(现有为空,将填入) / conflict(双方有值且不同,需选择)
                      / same(一致) / invalid(导入值不合法) / no_import(导入为空)
        unmatched: 未匹配到合同的行
    """
    from openpyxl import load_workbook

    payload = request.current_user
    perm_err = _require_import_perm(payload)
    if perm_err:
        return perm_err

    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'code': 400, 'message': '请选择要导入的 Excel 文件(.xlsx)', 'data': None})
    if not f.filename.lower().endswith('.xlsx'):
        return jsonify({'code': 400, 'message': '仅支持 .xlsx 格式', 'data': None})

    quarter = (request.form.get('quarter') or '').strip()
    db = get_db()
    cur = db.cursor()
    if not quarter:
        cur.execute("SELECT DISTINCT quarter FROM receivable_snapshots ORDER BY quarter DESC LIMIT 1")
        row = cur.fetchone()
        quarter = row['quarter'] if row else _current_quarter()

    # 该季度快照（匹配目标）
    cur.execute("""
        SELECT s.contract_id, s.customer_name, s.project_name, s.contract_no,
               o.customer_nature, o.cust_risk, o.payback_risk, o.payback_plan
        FROM receivable_snapshots s
        LEFT JOIN receivable_overrides o
          ON o.quarter = s.quarter AND o.contract_id = s.contract_id
        WHERE s.quarter = ?
    """, (quarter,))
    snaps = [dict(r) for r in cur.fetchall()]
    if not snaps:
        return jsonify({'code': 400, 'message': f'季度 {quarter} 暂无快照，请先生成快照', 'data': None})

    rows_by_no = {}
    rows_by_name = {}
    for s in snaps:
        no = (s.get('contract_no') or '').strip()
        if no:
            rows_by_no[no] = s
        name = (s.get('project_name') or '').strip()
        if name:
            rows_by_name.setdefault(name, []).append(s)

    # 解析 Excel
    try:
        wb = load_workbook(BytesIO(f.read()), data_only=True, read_only=True)
    except Exception as e:
        return jsonify({'code': 400, 'message': f'Excel 解析失败: {e}', 'data': None})
    ws = wb.active

    matrix = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()

    # 定位表头行（前 10 行内同时出现「往来单位」和「项目名称/合同编号」）
    header_idx, col_map = None, {}
    for i, row in enumerate(matrix[:10]):
        cells = {_norm_header(c): j for j, c in enumerate(row) if _norm_header(c)}
        if '往来单位' in cells and ('项目名称' in cells or '合同编号' in cells):
            header_idx = i
            for h, j in cells.items():
                key = _IMPORT_HEADER_MAP.get(h)
                if key and key not in col_map:
                    col_map[key] = j
            break
    if header_idx is None:
        return jsonify({'code': 400, 'message': '未识别到表头（需包含「往来单位」和「项目名称/合同编号」列）', 'data': None})

    def _get(row, key):
        j = col_map.get(key)
        return _cell_str(row[j]) if j is not None and j < len(row) else ''

    matched_rows, unmatched = [], []
    for ri in range(header_idx + 1, len(matrix)):
        row = matrix[ri]
        if not any(_cell_str(c) for c in row):
            continue  # 空行
        rec = {
            'row_no': ri + 1,
            'customer_name': _get(row, 'customer_name'),
            'contract_no': _get(row, 'contract_no'),
            'project_name': _get(row, 'project_name'),
        }

        # ---- 匹配合同：合同编号 → 项目名称(唯一) → 项目名称+往来单位 ----
        snap, matched_by = None, ''
        no = rec['contract_no']
        if no and no in rows_by_no:
            snap, matched_by = rows_by_no[no], '合同编号'
        else:
            name = rec['project_name']
            cands = rows_by_name.get(name, []) if name else []
            if len(cands) == 1:
                snap, matched_by = cands[0], '项目名称'
            elif len(cands) > 1:
                refined = [c for c in cands if (c.get('customer_name') or '').strip() == rec['customer_name']]
                if len(refined) == 1:
                    snap, matched_by = refined[0], '项目名称+往来单位'
                else:
                    unmatched.append({**rec, 'reason': f'项目名称匹配到 {len(cands)} 份合同，无法唯一确定'})
                    continue
            else:
                unmatched.append({**rec, 'reason': '未在当前季度快照中找到对应合同（项目名称/合同编号均未匹配）'})
                continue

        existing = {
            'customer_nature': (snap.get('customer_nature') or '').strip(),
            'cust_risk': (snap.get('cust_risk') or '').strip(),
            'payback_risk': (snap.get('payback_risk') or '').strip(),
            'payback_plan': _format_plan(snap.get('payback_plan')),
        }

        imported = {}
        imported['customer_nature'] = _get(row, 'customer_nature')
        imported['cust_risk'] = _norm_risk(_get(row, 'cust_risk')) if _get(row, 'cust_risk') else ''
        imported['payback_risk'] = _norm_risk(_get(row, 'payback_risk')) if _get(row, 'payback_risk') else ''
        plan_raw = _get(row, 'payback_plan')
        imported['payback_plan'] = _format_plan(_parse_plan_text(plan_raw)) if plan_raw else ''

        fields = []
        for key, label in _IMPORT_FIELDS:
            imp = imported.get(key) or ''
            # 不合法值（如客户风险「优」、客户性质不在 6 项内）
            invalid_reason = ''
            if key == 'customer_nature' and imp and imp not in CUSTOMER_NATURES:
                invalid_reason = f'客户性质「{imp}」不在可选范围内'
            if key in ('cust_risk', 'payback_risk') and imp == '' and _cell_str(_get(row, key)):
                invalid_reason = f'{label}「{_cell_str(_get(row, key))}」无法识别（仅支持 高/中/低）'
            ex = existing.get(key) or ''
            if invalid_reason:
                action = 'invalid'
            elif not imp:
                action = 'no_import'
            elif not ex:
                action = 'fill'
            elif ex == imp:
                action = 'same'
            else:
                action = 'conflict'
            fields.append({
                'key': key, 'label': label,
                'existing': ex, 'imported': imp,
                'action': action, 'invalid_reason': invalid_reason,
                # 回款计划附解析后的结构化列表，应用时原样回传
                'imported_list': (_parse_plan_text(plan_raw) if key == 'payback_plan' and plan_raw else None),
            })

        matched_rows.append({**rec, 'contract_id': snap['contract_id'],
                             'matched_by': matched_by, 'fields': fields})

    record_operation_log(payload['username'], '两金明细表', '导入预览',
                         f'季度 {quarter} 文件 {f.filename}：匹配 {len(matched_rows)} 行，未匹配 {len(unmatched)} 行')
    return jsonify({'code': 200, 'message': 'success', 'data': {
        'quarter': quarter,
        'total_rows': len(matched_rows) + len(unmatched),
        'rows': matched_rows,
        'unmatched': unmatched,
    }})


@receivables_bp.route('/import/apply', methods=['POST'])
@token_required
def import_apply():
    """按用户裁决结果写入填报。

    Body:
        quarter: '2026Q3'
        rows: [{contract_id, fields: {customer_nature?, cust_risk?, payback_risk?, payback_plan?}}]
              只传用户选择「使用导入值/将填入」的字段；payback_plan 传解析后的 list。
    """
    payload = request.current_user
    perm_err = _require_import_perm(payload)
    if perm_err:
        return perm_err

    body = request.get_json(silent=True) or {}
    quarter = (body.get('quarter') or '').strip() or _current_quarter()
    rows = body.get('rows') or []

    db = get_db()
    cur = db.cursor()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    applied = 0
    filled_count = 0
    try:
        for r in rows:
            cid = r.get('contract_id')
            fields = r.get('fields') or {}
            if not cid or not fields:
                continue

            customer_nature = fields.get('customer_nature')
            cust_risk = fields.get('cust_risk')
            payback_risk = fields.get('payback_risk')
            payback_plan = fields.get('payback_plan')

            # 校验（与手工填报同一套规则）
            if customer_nature is not None and customer_nature not in CUSTOMER_NATURES and customer_nature != '':
                return jsonify({'code': 400, 'message': f'合同{cid} 客户性质取值不合法', 'data': None})
            for name, val in (('客户风险', cust_risk), ('回款风险', payback_risk)):
                if val is not None and val not in RISK_LEVELS and val != '':
                    return jsonify({'code': 400, 'message': f'合同{cid} {name}必须是 {"|".join(RISK_LEVELS)}', 'data': None})
            plan_str = None
            if payback_plan is not None:
                if isinstance(payback_plan, list):
                    plan_str = json.dumps(payback_plan, ensure_ascii=False)
                elif isinstance(payback_plan, str):
                    plan_str = payback_plan
                else:
                    return jsonify({'code': 400, 'message': f'合同{cid} payback_plan 格式错误', 'data': None})

            for v in (customer_nature, cust_risk, payback_risk, plan_str):
                if v:
                    filled_count += 1
            cur.execute("""
                INSERT INTO receivable_overrides
                  (quarter, contract_id, customer_nature, cust_risk, payback_risk, payback_plan, updated_by, updated_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON DUPLICATE KEY UPDATE
                  customer_nature=COALESCE(VALUES(customer_nature), customer_nature),
                  cust_risk=COALESCE(VALUES(cust_risk), cust_risk),
                  payback_risk=COALESCE(VALUES(payback_risk), payback_risk),
                  payback_plan=COALESCE(VALUES(payback_plan), payback_plan),
                  updated_by=VALUES(updated_by), updated_at=VALUES(updated_at)
            """, (quarter, cid, customer_nature, cust_risk, payback_risk,
                  plan_str, payload['username'], now_str))
            applied += 1
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception('两金导入应用失败')
        return jsonify({'code': 500, 'message': f'导入失败: {e}', 'data': None})

    record_operation_log(payload['username'], '两金明细表', '导入应用',
                         f'季度 {quarter}：写入 {applied} 行，填入 {filled_count} 项')
    return jsonify({'code': 200, 'message': 'success', 'data': {
        'applied': applied, 'filled': filled_count,
    }})
