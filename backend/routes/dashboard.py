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
        return ("AND strftime('%Y', created_at) = ?",
                "AND strftime('%Y', sign_date) = ?",
                "AND strftime('%Y', payment_date) = ?",
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
            SELECT strftime('%d', created_at) as day, COUNT(*) as count
            FROM customers
            WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
            GROUP BY strftime('%d', created_at)
            ORDER BY day
        """)
        customer_monthly = {row['day']: row['count'] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT strftime('%d', created_at) as day, COUNT(*) as count
            FROM business
            WHERE status = 'active' AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
            GROUP BY strftime('%d', created_at)
            ORDER BY day
        """)
        business_monthly = {row['day']: row['count'] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT strftime('%d', sign_date) as day, COUNT(*) as count
            FROM contracts
            WHERE strftime('%Y-%m', sign_date) = strftime('%Y-%m', 'now')
            GROUP BY strftime('%d', sign_date)
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
            SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count
            FROM customers
            WHERE created_at >= ?
            GROUP BY strftime('%Y-%m', created_at)
            ORDER BY month
        """, (start_date,))
        customer_monthly = {row['month']: row['count'] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count
            FROM business
            WHERE status = 'active' AND created_at >= ?
            GROUP BY strftime('%Y-%m', created_at)
            ORDER BY month
        """, (start_date,))
        business_monthly = {row['month']: row['count'] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT strftime('%Y-%m', sign_date) as month, COUNT(*) as count
            FROM contracts
            WHERE sign_date >= ?
            GROUP BY strftime('%Y-%m', sign_date)
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
            SELECT strftime('%m', created_at) as month, COUNT(*) as count
            FROM customers
            WHERE strftime('%Y', created_at) = ?
            GROUP BY strftime('%m', created_at)
            ORDER BY month
        """, (str(chart_year),))
        customer_monthly = {row['month']: row['count'] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT strftime('%m', created_at) as month, COUNT(*) as count
            FROM business
            WHERE status = 'active' AND strftime('%Y', created_at) = ?
            GROUP BY strftime('%m', created_at)
            ORDER BY month
        """, (str(chart_year),))
        business_monthly = {row['month']: row['count'] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT strftime('%m', sign_date) as month, COUNT(*) as count
            FROM contracts
            WHERE strftime('%Y', sign_date) = ?
            GROUP BY strftime('%m', sign_date)
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
                    "WHERE strftime('%Y-%m', acceptance_date) = ?",
                    (month_str,)
                )
            else:
                cursor.execute(
                    "SELECT COALESCE(SUM(ca.acceptance_amount), 0) as total "
                    "FROM contract_acceptances ca "
                    "JOIN contracts c ON ca.contract_id = c.id "
                    "WHERE strftime('%Y-%m', ca.acceptance_date) = ? AND c.owner_id = ?",
                    (month_str, username)
                )
            acceptance_data.append(cursor.fetchone()['total'] or 0)

            if can_view_all:
                cursor.execute(
                    "SELECT COALESCE(SUM(amount), 0) as total "
                    "FROM payment_records "
                    "WHERE strftime('%Y-%m', payment_date) = ?",
                    (month_str,)
                )
            else:
                cursor.execute(
                    "SELECT COALESCE(SUM(pr.amount), 0) as total "
                    "FROM payment_records pr "
                    "JOIN contracts c ON pr.contract_id = c.id "
                    "WHERE strftime('%Y-%m', pr.payment_date) = ? AND c.owner_id = ?",
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
        pending_pay = max(0.0, total_amt - paid_amt)

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
            # forecast 存万元，转元返回，前端 formatWan 统一显示
            'expected_acceptance': round((r['expected_acceptance'] or 0) * 10000, 2),
            'expected_payment': round((r['expected_payment'] or 0) * 10000, 2),
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


def register_routes(app):
    app.register_blueprint(dashboard_bp)
