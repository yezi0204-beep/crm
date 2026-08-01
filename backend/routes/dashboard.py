from datetime import datetime, timedelta
from flask import request, jsonify

from extensions import get_db, token_required

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

    if role == '主任' or role == '院长':
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

    return jsonify({'code': 200, 'message': 'success', 'data': result})


def register_routes(app):
    app.register_blueprint(dashboard_bp)
