from datetime import datetime, timedelta
from flask import request, jsonify

from extensions import get_db, token_required, user_can

from . import dashboard_bp


def build_date_filter(time_range, year=None):
    if time_range not in ('all', 'month', 'quarter', 'year'):
        time_range = 'all'

    now = datetime.now()

    if time_range == 'month':
        start_date = now.strftime('%Y-%m-01')
        return ("AND created_at >= ?", "AND sign_date >= ?", "AND payment_date >= ?",
                [start_date], [start_date], [start_date])
    elif time_range == 'quarter':
        quarter = (now.month - 1) // 3 + 1
        start_month = (quarter - 1) * 3 + 1
        start_date = f"{now.year}-{start_month:02d}-01"
        return ("AND created_at >= ?", "AND sign_date >= ?", "AND payment_date >= ?",
                [start_date], [start_date], [start_date])
    elif time_range == 'year':
        year_str = str(year if year else now.year)
        return ("AND DATE_FORMAT(created_at, '%Y') = ?",
                "AND DATE_FORMAT(sign_date, '%Y') = ?",
                "AND DATE_FORMAT(payment_date, '%Y') = ?",
                [year_str], [year_str], [year_str])
    else:
        return ("", "", "", [], [], [])


@dashboard_bp.route('/api/dashboard', methods=['GET'])
@token_required
def get_dashboard():
    payload = request.current_user
    username = payload['username']
    role = payload['role']
    time_range = request.args.get('time_range', 'all')
    year = request.args.get('year', type=int)

    db = get_db()
    cursor = db.cursor()

    result = {}
    now = datetime.now()

    date_cond, contract_cond, payment_cond, date_params, contract_params, payment_params = build_date_filter(time_range, year)

    if user_can(username, 'data.view_all'):
        cursor.execute("SELECT COUNT(*) as total FROM customers WHERE 1=1 " + date_cond, date_params)
        result['total_customers'] = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) as total FROM business WHERE status = 'active' " + date_cond, date_params)
        result['total_business'] = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) as total FROM contracts WHERE 1=1 " + contract_cond, contract_params)
        result['total_contracts'] = cursor.fetchone()['total']

        cursor.execute("SELECT SUM(total_amt) as total FROM contracts WHERE 1=1 " + contract_cond, contract_params)
        total = cursor.fetchone()['total'] or 0
        result['contracts_amount'] = total

        cursor.execute("SELECT SUM(amount) as total FROM payment_records WHERE 1=1 " + payment_cond, payment_params)
        total = cursor.fetchone()['total'] or 0
        result['total_payments'] = total
    else:
        cursor.execute("SELECT COUNT(*) as total FROM customers WHERE owner_id = ? " + date_cond, [username] + date_params)
        result['total_customers'] = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) as total FROM business WHERE owner_id = ? AND status = 'active' " + date_cond, [username] + date_params)
        result['total_business'] = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) as total FROM contracts WHERE owner_id = ? " + contract_cond, [username] + contract_params)
        result['total_contracts'] = cursor.fetchone()['total']

        cursor.execute("SELECT SUM(total_amt) as total FROM contracts WHERE owner_id = ? " + contract_cond, [username] + contract_params)
        total = cursor.fetchone()['total'] or 0
        result['contracts_amount'] = total

        sql = (
            "SELECT SUM(pr.amount) as total "
            "FROM payment_records pr "
            "JOIN contracts c ON pr.contract_id = c.id "
            "WHERE c.owner_id = ? " + payment_cond
        )
        cursor.execute(sql, [username] + payment_params)
        total = cursor.fetchone()['total'] or 0
        result['total_payments'] = total

    if time_range == 'month':
        cursor.execute("""
            SELECT DATE_FORMAT(created_at, '%d') as day, COUNT(*) as count
            FROM customers
            WHERE DATE_FORMAT(created_at, '%Y-%m') = DATE_FORMAT(NOW(), '%Y-%m')
            GROUP BY DATE_FORMAT(created_at, '%d')
            ORDER BY day
        """)
        customer_monthly = {row['day']: row['count'] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT DATE_FORMAT(created_at, '%d') as day, COUNT(*) as count
            FROM business
            WHERE status = 'active' AND DATE_FORMAT(created_at, '%Y-%m') = DATE_FORMAT(NOW(), '%Y-%m')
            GROUP BY DATE_FORMAT(created_at, '%d')
            ORDER BY day
        """)
        business_monthly = {row['day']: row['count'] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT DATE_FORMAT(sign_date, '%d') as day, COUNT(*) as count
            FROM contracts
            WHERE DATE_FORMAT(sign_date, '%Y-%m') = DATE_FORMAT(NOW(), '%Y-%m')
            GROUP BY DATE_FORMAT(sign_date, '%d')
            ORDER BY day
        """)
        contract_monthly = {row['day']: row['count'] for row in cursor.fetchall()}

        days_in_month = (now.replace(month=now.month % 12 + 1, day=1) - timedelta(days=1)).day
        months = [f"{i}日" for i in range(1, days_in_month + 1)]
        customer_data = [customer_monthly.get(str(i), 0) for i in range(1, days_in_month + 1)]
        business_data = [business_monthly.get(str(i), 0) for i in range(1, days_in_month + 1)]
        contract_data = [contract_monthly.get(str(i), 0) for i in range(1, days_in_month + 1)]
    elif time_range == 'quarter':
        quarter = (now.month - 1) // 3 + 1
        start_month = (quarter - 1) * 3 + 1
        start_date = f"{now.year}-{str(start_month).zfill(2)}-01"

        cursor.execute("""
            SELECT DATE_FORMAT(created_at, '%Y-%m') as month, COUNT(*) as count
            FROM customers
            WHERE created_at >= ?
            GROUP BY DATE_FORMAT(created_at, '%Y-%m')
            ORDER BY month
        """, (start_date,))
        customer_monthly = {row['month']: row['count'] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT DATE_FORMAT(created_at, '%Y-%m') as month, COUNT(*) as count
            FROM business
            WHERE status = 'active' AND created_at >= ?
            GROUP BY DATE_FORMAT(created_at, '%Y-%m')
            ORDER BY month
        """, (start_date,))
        business_monthly = {row['month']: row['count'] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT DATE_FORMAT(sign_date, '%Y-%m') as month, COUNT(*) as count
            FROM contracts
            WHERE sign_date >= ?
            GROUP BY DATE_FORMAT(sign_date, '%Y-%m')
            ORDER BY month
        """, (start_date,))
        contract_monthly = {row['month']: row['count'] for row in cursor.fetchall()}

        months = []
        customer_data = []
        business_data = []
        contract_data = []
        for m in range(start_month, start_month + 3):
            month_str = f"{now.year}-{str(m).zfill(2)}"
            months.append(f"{m}月")
            customer_data.append(customer_monthly.get(month_str, 0))
            business_data.append(business_monthly.get(month_str, 0))
            contract_data.append(contract_monthly.get(month_str, 0))
    else:
        chart_year = year if year else now.year

        cursor.execute("""
            SELECT DATE_FORMAT(created_at, '%m') as month, COUNT(*) as count
            FROM customers
            WHERE DATE_FORMAT(created_at, '%Y') = ?
            GROUP BY DATE_FORMAT(created_at, '%m')
            ORDER BY month
        """, (str(chart_year),))
        customer_monthly = {row['month']: row['count'] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT DATE_FORMAT(created_at, '%m') as month, COUNT(*) as count
            FROM business
            WHERE status = 'active' AND DATE_FORMAT(created_at, '%Y') = ?
            GROUP BY DATE_FORMAT(created_at, '%m')
            ORDER BY month
        """, (str(chart_year),))
        business_monthly = {row['month']: row['count'] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT DATE_FORMAT(sign_date, '%m') as month, COUNT(*) as count
            FROM contracts
            WHERE DATE_FORMAT(sign_date, '%Y') = ?
            GROUP BY DATE_FORMAT(sign_date, '%m')
            ORDER BY month
        """, (str(chart_year),))
        contract_monthly = {row['month']: row['count'] for row in cursor.fetchall()}

        months = []
        customer_data = []
        business_data = []
        contract_data = []

        for m in range(1, 13):
            month_str = f"{m:02d}"
            months.append(f"{m}月")
            customer_data.append(customer_monthly.get(month_str, 0))
            business_data.append(business_monthly.get(month_str, 0))
            contract_data.append(contract_monthly.get(month_str, 0))

    result['chart_data'] = {
        'months': months,
        'customer_data': customer_data,
        'business_data': business_data,
        'contract_data': contract_data
    }

    cursor.execute("""
        SELECT u.name, u.role, COALESCE(SUM(c.total_amt), 0) as total_amount
        FROM users u
        LEFT JOIN contracts c ON u.username = c.owner_id
        GROUP BY u.username, u.name, u.role
        ORDER BY total_amount DESC
        LIMIT 5
    """)
    sales_ranking = []
    for row in cursor.fetchall():
        sales_ranking.append({
            'name': row['name'],
            'role': row['role'],
            'amount': row['total_amount']
        })
    result['sales_ranking'] = sales_ranking

    # 真实环比趋势：复用 reports.py 的 _compute_trend_comparison
    try:
        from .reports import _compute_trend_comparison
        trend_time_range = 'year' if time_range == 'year' else 'month'
        result['trends'] = _compute_trend_comparison(db, cursor, role, username, trend_time_range, year)
    except Exception as e:
        # 趋势计算失败不影响主流程
        result['trends'] = None

    return jsonify({'code': 200, 'message': 'success', 'data': result})


@dashboard_bp.route('/api/dashboard/monthly-finance', methods=['GET'])
@token_required
def get_monthly_finance():
    """财务看板：关键指标 + 月度/季度验收回款（过去实际、未来填报预计）
    + 负责人统计 + 月度填报明细。"""
    payload = request.current_user
    username = payload['username']
    year = request.args.get('year', type=int) or datetime.now().year

    db = get_db()
    cursor = db.cursor()
    now = datetime.now()
    current_month = now.month if year == now.year else 13  # 非当年则全部走"实际"

    can_view_all = (user_can(username, 'data.view_all')
                    or user_can(username, 'contracts.view_all')
                    or user_can(username, 'finance.view'))
    owner_param = [username] if not can_view_all else []

    months = []
    acceptance_data = []
    payment_data = []
    is_actual = []  # True=实际, False=预计

    for m in range(1, 13):
        month_str = f"{year}-{m:02d}"
        months.append(f"{m}月")

        if m < current_month:
            # —— 过去月份：实际记录 ——
            is_actual.append(True)

            if can_view_all:
                cursor.execute(
                    "SELECT COALESCE(SUM(acceptance_amount), 0) as total "
                    "FROM contract_acceptances "
                    "WHERE DATE_FORMAT(acceptance_date, '%Y-%m') = ?",
                    (month_str,)
                )
            else:
                cursor.execute(
                    "SELECT COALESCE(SUM(ca.acceptance_amount), 0) as total "
                    "FROM contract_acceptances ca "
                    "JOIN contracts c ON ca.contract_id = c.id "
                    "WHERE DATE_FORMAT(ca.acceptance_date, '%Y-%m') = ? AND c.owner_id = ?",
                    (month_str, username)
                )
            acceptance_data.append(cursor.fetchone()['total'] or 0)

            if can_view_all:
                cursor.execute(
                    "SELECT COALESCE(SUM(amount), 0) as total "
                    "FROM payment_records "
                    "WHERE DATE_FORMAT(payment_date, '%Y-%m') = ?",
                    (month_str,)
                )
            else:
                cursor.execute(
                    "SELECT COALESCE(SUM(pr.amount), 0) as total "
                    "FROM payment_records pr "
                    "JOIN contracts c ON pr.contract_id = c.id "
                    "WHERE DATE_FORMAT(pr.payment_date, '%Y-%m') = ? AND c.owner_id = ?",
                    (month_str, username)
                )
            payment_data.append(cursor.fetchone()['total'] or 0)
        else:
            # —— 当前月及之后：从月度填报表读预计数据 ——
            is_actual.append(False)

            if can_view_all:
                cursor.execute(
                    "SELECT COALESCE(SUM(expected_acceptance), 0) as acc, "
                    "COALESCE(SUM(expected_payment), 0) as pay "
                    "FROM contract_monthly_forecast WHERE year=? AND month=?",
                    (year, m)
                )
            else:
                cursor.execute(
                    "SELECT COALESCE(SUM(f.expected_acceptance), 0) as acc, "
                    "COALESCE(SUM(f.expected_payment), 0) as pay "
                    "FROM contract_monthly_forecast f "
                    "JOIN contracts c ON f.contract_id = c.id "
                    "WHERE f.year=? AND f.month=? AND c.owner_id=?",
                    (year, m, username)
                )
            row = cursor.fetchone()
            # contract_monthly_forecast 存储单位为万元，×10000 转元并精确到分（2位小数）
            acceptance_data.append(round((row['acc'] or 0) * 10000, 2))
            payment_data.append(round((row['pay'] or 0) * 10000, 2))

    # —— 年度汇总（实际/预计分开）——
    actual_acc = sum(a for a, act in zip(acceptance_data, is_actual) if act)
    actual_pay = sum(p for p, act in zip(payment_data, is_actual) if act)
    expected_acc = sum(a for a, act in zip(acceptance_data, is_actual) if not act)
    expected_pay = sum(p for p, act in zip(payment_data, is_actual) if not act)

    # —— 季度汇总 ——
    quarters = []
    for q in range(4):
        idx = [q * 3, q * 3 + 1, q * 3 + 2]
        all_actual = all(is_actual[i] for i in idx)
        all_expected = all(not is_actual[i] for i in idx)
        quarters.append({
            'label': f'Q{q+1}',
            'acceptance_actual': sum(acceptance_data[i] for i in idx if is_actual[i]),
            'acceptance_expected': sum(acceptance_data[i] for i in idx if not is_actual[i]),
            'payment_actual': sum(payment_data[i] for i in idx if is_actual[i]),
            'payment_expected': sum(payment_data[i] for i in idx if not is_actual[i]),
            'mixed': not (all_actual or all_expected),
        })

    # —— 关键财务指标（全部有效合同，排除已终止）——
    cursor.execute(
        "SELECT c.id, c.owner_id, u.name as owner_name, "
        "COALESCE(c.total_amt,0) as total_amt, COALESCE(c.tax_amount,0) as tax_amount, "
        "COALESCE(c.paid_amt,0) as paid_amt "
        "FROM contracts c LEFT JOIN users u ON c.owner_id = u.username "
        "WHERE c.status != '已终止'"
        + ("" if can_view_all else " AND c.owner_id = ?"),
        owner_param
    )
    contract_rows = cursor.fetchall()

    # 每合同累计验收额
    if contract_rows:
        cids = [r['id'] for r in contract_rows]
        placeholders = ','.join('?' * len(cids))
        cursor.execute(
            f"SELECT contract_id, COALESCE(SUM(acceptance_amount),0) as acc_sum "
            f"FROM contract_acceptances WHERE contract_id IN ({placeholders}) GROUP BY contract_id",
            cids
        )
        acc_map = {r['contract_id']: r['acc_sum'] for r in cursor.fetchall()}
    else:
        acc_map = {}

    total_contract_amt = 0.0
    cumulative_acceptance = 0.0
    pending_acceptance = 0.0
    cumulative_payment = 0.0
    pending_payment = 0.0
    owner_stats = {}

    for r in contract_rows:
        total_amt = float(r['total_amt'] or 0)
        paid_amt = float(r['paid_amt'] or 0)
        accepted = float(acc_map.get(r['id'], 0))
        # 待验收 = 合同额 - 累计验收额 - 税额（与合同列表口径一致）
        pending_acc = max(0.0, total_amt - accepted - float(r['tax_amount'] or 0))
        # 待回款 = 收入金额(累计验收额) + 税额 - 已回款金额 = 含税收入 - 已回款
        pending_pay = max(0.0, accepted + float(r['tax_amount'] or 0) - paid_amt)

        total_contract_amt += total_amt
        cumulative_acceptance += accepted
        pending_acceptance += pending_acc
        cumulative_payment += paid_amt
        pending_payment += pending_pay

        oid = r['owner_id'] or '未分配'
        oname = r['owner_name'] or oid
        st = owner_stats.setdefault(oid, {
            'owner_id': oid, 'owner_name': oname,
            'contract_amt': 0.0, 'accepted': 0.0, 'paid': 0.0, 'pending_pay': 0.0, 'count': 0
        })
        st['contract_amt'] += total_amt
        st['accepted'] += accepted
        st['paid'] += paid_amt
        st['pending_pay'] += pending_pay
        st['count'] += 1

    owner_list = sorted(owner_stats.values(), key=lambda x: x['contract_amt'], reverse=True)

    metrics = {
        'total_contract_amt': round(total_contract_amt, 2),
        'cumulative_acceptance': round(cumulative_acceptance, 2),
        'cumulative_payment': round(cumulative_payment, 2),
        'pending_acceptance': round(pending_acceptance, 2),
        'pending_payment': round(pending_payment, 2),
        'acceptance_rate': round(cumulative_acceptance / total_contract_amt * 100, 1) if total_contract_amt else 0,
        'payment_rate': round(cumulative_payment / total_contract_amt * 100, 1) if total_contract_amt else 0,
    }

    # —— 月度填报明细（有金额的行，附合同名/负责人）——
    cursor.execute(
        "SELECT f.month, COALESCE(f.expected_acceptance,0) as expected_acceptance, "
        "COALESCE(f.expected_payment,0) as expected_payment, "
        "c.id as contract_id, c.contract_name, c.contract_no, "
        "COALESCE(u.name, c.owner_id) as owner_name "
        "FROM contract_monthly_forecast f "
        "JOIN contracts c ON f.contract_id = c.id "
        "LEFT JOIN users u ON c.owner_id = u.username "
        "WHERE f.year = ? AND c.status != '已终止' "
        "AND (f.expected_acceptance > 0 OR f.expected_payment > 0) "
        + ("" if can_view_all else "AND c.owner_id = ? ")
        + "ORDER BY f.month, c.id",
        [year] + owner_param
    )
    detail_rows = []
    for r in cursor.fetchall():
        m = r['month']
        detail_rows.append({
            'month': m,
            'month_label': f'{m}月',
            'is_actual': m < current_month,
            'contract_id': r['contract_id'],
            'contract_name': r['contract_name'],
            'contract_no': r['contract_no'],
            'owner_name': r['owner_name'],
            # forecast 存元，直接返回
            'expected_acceptance': round((r['expected_acceptance'] or 0), 2),
            'expected_payment': round((r['expected_payment'] or 0), 2),
        })

    return jsonify({'code': 200, 'message': 'success', 'data': {
        'months': months,
        'acceptance_data': acceptance_data,
        'payment_data': payment_data,
        'is_actual': is_actual,
        'quarters': quarters,
        'metrics': metrics,
        'owners': owner_list,
        'details': detail_rows,
        'summary': {
            'actual_acceptance': actual_acc,
            'actual_payment': actual_pay,
            'expected_acceptance': expected_acc,
            'expected_payment': expected_pay,
        }
    }})


# ============================================================
# AI 经营洞察（LLM 生成关键结论，带内存缓存避免频繁调用）
# ============================================================
_INSIGHTS_CACHE = {}
_INSIGHTS_CACHE_TTL = 300  # 5 分钟


def _collect_insight_metrics(db, cursor, username, can_view_all):
    """收集用于 LLM 洞察的核心指标（轻量、只读）。"""
    owner_filter = "" if can_view_all else "AND c.owner_id = ?"
    owner_params = [] if can_view_all else [username]
    now = datetime.now()
    month_start = now.strftime('%Y-%m-01')

    m = {}
    cursor.execute("SELECT COUNT(*) n FROM customers")
    m['total_customers'] = cursor.fetchone()['n']
    cursor.execute("SELECT COUNT(*) n FROM business WHERE status='active'")
    m['active_business'] = cursor.fetchone()['n']
    cursor.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(total_amt),0) amt FROM contracts c WHERE c.status != '已终止' " + owner_filter,
        owner_params)
    r = cursor.fetchone()
    m['total_contracts'] = r['n']
    m['contracts_amount'] = round(float(r['amt'] or 0), 2)

    cursor.execute(
        "SELECT COALESCE(SUM(amount),0) amt FROM payment_records "
        + ("" if can_view_all else "WHERE contract_id IN (SELECT id FROM contracts c WHERE c.owner_id = ?)"),
        owner_params)
    m['total_payments'] = round(float(cursor.fetchone()['amt'] or 0), 2)

    # 待回款 = 累计验收 + 税额 - 已回款（执行中合同）
    cursor.execute(
        "SELECT COALESCE(SUM(COALESCE(c.income,0) - COALESCE(c.paid_amt,0)),0) pending "
        "FROM contracts c WHERE c.status = '执行中' " + owner_filter,
        owner_params)
    m['pending_payment'] = round(float(cursor.fetchone()['pending'] or 0), 2)

    # 待验收合同额
    cursor.execute(
        "SELECT COALESCE(SUM(c.total_amt - COALESCE(c.income,0)),0) pending "
        "FROM contracts c WHERE c.status = '执行中' " + owner_filter,
        owner_params)
    m['pending_acceptance'] = round(float(cursor.fetchone()['pending'] or 0), 2)

    # 本月新增
    cursor.execute("SELECT COUNT(*) n FROM customers WHERE created_at >= ?", (month_start,))
    m['new_customers_month'] = cursor.fetchone()['n']
    cursor.execute("SELECT COUNT(*) n FROM business WHERE status='active' AND created_at >= ?", (month_start,))
    m['new_business_month'] = cursor.fetchone()['n']
    cursor.execute("SELECT COUNT(*) n, COALESCE(SUM(total_amt),0) amt FROM contracts WHERE sign_date >= ?", (month_start,))
    r = cursor.fetchone()
    m['new_contracts_month'] = r['n']
    m['new_contracts_amount_month'] = round(float(r['amt'] or 0), 2)
    cursor.execute("SELECT COALESCE(SUM(amount),0) amt FROM payment_records WHERE payment_date >= ?", (month_start,))
    m['payments_month'] = round(float(cursor.fetchone()['amt'] or 0), 2)

    # 待办
    try:
        cursor.execute("SELECT COUNT(*) n FROM work_hours WHERE status='pending'")
        m['pending_workhours'] = cursor.fetchone()['n']
    except Exception:
        m['pending_workhours'] = 0
    return m


@dashboard_bp.route('/api/dashboard/insights', methods=['GET'])
@token_required
def get_dashboard_insights():
    """AI 经营洞察：聚合核心指标，用 LLM 生成 3-5 条关键结论。
    缓存 5 分钟，LLM 不可用时返回规则生成的静态洞察。
    """
    payload = request.current_user
    username = payload['username']
    can_view_all = user_can(username, 'data.view_all')
    cache_key = f'{username}|{int(can_view_all)}'
    now_ts = datetime.now().timestamp()

    cached = _INSIGHTS_CACHE.get(cache_key)
    if cached and (now_ts - cached['ts']) < _INSIGHTS_CACHE_TTL:
        return jsonify({'code': 200, 'message': 'success',
                        'data': {**cached['data'], 'cached': True}})

    db = get_db()
    cursor = db.cursor()
    metrics = _collect_insight_metrics(db, cursor, username, can_view_all)

    insights = None
    source = 'llm'
    try:
        from llm_gateway import gateway_chat
        prompt = (
            "你是 CRM 经营分析助手。请根据以下数据给出 3-5 条简洁、可执行的关键经营洞察"
            "（每条不超过 35 字，用短句，不要客套话）。数据：\n"
            f"客户总数 {metrics['total_customers']}；活跃商机 {metrics['active_business']}；"
            f"有效合同 {metrics['total_contracts']} 个，总额 {metrics['contracts_amount']} 元；"
            f"累计回款 {metrics['total_payments']} 元；"
            f"待回款 {metrics['pending_payment']} 元；待验收 {metrics['pending_acceptance']} 元；"
            f"本月新增客户 {metrics['new_customers_month']}、新增商机 {metrics['new_business_month']}、"
            f"新签合同 {metrics['new_contracts_month']} 个（{metrics['new_contracts_amount_month']} 元）、"
            f"本月回款 {metrics['payments_month']} 元；待审工时 {metrics['pending_workhours']} 条。"
        )
        resp = gateway_chat(
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=600, timeout=30, enable_thinking=False,
            operation_type='dashboard_insights', data_source='dashboard', operator=username,
        )
        if resp:
            lines = [ln.strip('•-* 0123456789.、') for ln in resp.splitlines()]
            insights = [ln for ln in lines if len(ln) >= 6][:5] or None
    except Exception:
        insights = None

    if not insights:
        source = 'rule'
        insights = []
        if metrics['pending_payment'] > 0:
            insights.append(f"待回款 {metrics['pending_payment']:.2f} 元，建议优先跟进回款计划")
        if metrics['pending_acceptance'] > 0:
            insights.append(f"待验收 {metrics['pending_acceptance']:.2f} 元，可推动项目验收释放收入")
        if metrics['new_business_month'] > 0:
            insights.append(f"本月新增商机 {metrics['new_business_month']} 个，注意及时跟进转化")
        if metrics['pending_workhours'] > 0:
            insights.append(f"有 {metrics['pending_workhours']} 条工时待审批，可在工时页一键批量通过")
        if metrics['active_business'] > 0 and metrics['total_contracts'] > 0:
            rate = round(metrics['total_contracts'] / max(metrics['active_business'], 1) * 100, 1)
            insights.append(f"商机转合同比例约 {rate}%")
        if not insights:
            insights.append("暂无待处理事项，业务运行平稳")

    data = {
        'insights': insights,
        'metrics': metrics,
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'source': source,
    }
    _INSIGHTS_CACHE[cache_key] = {'ts': now_ts, 'data': data}
    return jsonify({'code': 200, 'message': 'success', 'data': {**data, 'cached': False}})


def register_routes(app):
    app.register_blueprint(dashboard_bp)
