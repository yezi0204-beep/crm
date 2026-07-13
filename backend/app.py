from flask import Flask, jsonify, request, send_from_directory, g
import sqlite3
import bcrypt
import os
import hashlib
import uuid
from datetime import datetime, timedelta

app = Flask(__name__)

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response

@app.route('/api/', methods=['OPTIONS'])
def options():
    return jsonify({'code': 200, 'message': 'OK', 'data': None})

SECRET_KEY = "crm_secret_key_2026"
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "crm_app.db")
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "contracts")

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH, check_same_thread=False)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error):
    if hasattr(g, 'db'):
        g.db.close()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def check_password(password: str, hash: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hash.encode('utf-8'))


def create_token(username: str, name: str, role: str) -> str:
    token = str(uuid.uuid4())
    expires = datetime.now() + timedelta(hours=24)
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        INSERT INTO tokens (token, username, name, role, expires)
        VALUES (?, ?, ?, ?, ?)
    ''', (token, username, name, role, expires.strftime('%Y-%m-%d %H:%M:%S')))
    db.commit()
    
    return token


def verify_token(token: str):
    if not token:
        return None
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM tokens WHERE token = ?', (token,))
    row = cursor.fetchone()
    
    if not row:
        return None
    
    expires = datetime.strptime(row['expires'], '%Y-%m-%d %H:%M:%S')
    if datetime.now() > expires:
        cursor.execute('DELETE FROM tokens WHERE token = ?', (token,))
        db.commit()
        return None
    
    return {
        'username': row['username'],
        'name': row['name'],
        'role': row['role'],
        'expires': expires
    }


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT username, password_hash, name, role FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    
    if row and check_password(password, row['password_hash']):
        token = create_token(row['username'], row['name'], row['role'])
        return jsonify({
            'code': 200,
            'message': '登录成功',
            'data': {
                'token': token,
                'username': row['username'],
                'name': row['name'],
                'role': row['role']
            }
        })
    return jsonify({'code': 401, 'message': '账号或密码错误', 'data': None})


@app.route('/api/auth/info', methods=['GET'])
def get_user_info():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT role FROM user_roles WHERE username = ?", (payload['username'],))
    rows = cursor.fetchall()
    roles = [r['role'] for r in rows] if rows else [payload['role']]
    
    return jsonify({
        'code': 200,
        'message': 'success',
        'data': {
            'username': payload['username'],
            'name': payload['name'],
            'role': payload['role'],
            'roles': roles
        }
    })


@app.route('/api/auth/logout', methods=['POST'])
def logout():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if token:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('DELETE FROM tokens WHERE token = ?', (token,))
        db.commit()
    return jsonify({'code': 200, 'message': '退出成功', 'data': None})


@app.route('/api/contracts', methods=['GET'])
def get_contracts():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    username = payload['username']
    role = payload['role']
    
    db = get_db()
    cursor = db.cursor()
    
    if role == '主任' or role == '院长':
        cursor.execute("""
            SELECT c.*, u.name as owner_name 
            FROM contracts c 
            LEFT JOIN users u ON c.owner_id = u.username 
            ORDER BY c.sign_date DESC
        """)
    else:
        cursor.execute("""
            SELECT c.*, u.name as owner_name 
            FROM contracts c 
            LEFT JOIN users u ON c.owner_id = u.username 
            WHERE c.owner_id = ? 
            ORDER BY c.sign_date DESC
        """, (username,))
    
    rows = cursor.fetchall()
    contracts = []
    for row in rows:
        contracts.append(dict(row))
    
    return jsonify({'code': 200, 'message': 'success', 'data': contracts})


@app.route('/api/contracts/<int:contract_id>', methods=['GET'])
def get_contract(contract_id):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM contracts WHERE id = ?", (contract_id,))
    row = cursor.fetchone()
    
    if row:
        return jsonify({'code': 200, 'message': 'success', 'data': dict(row)})
    return jsonify({'code': 404, 'message': '合同不存在', 'data': None})


@app.route('/api/contracts', methods=['POST'])
def create_contract():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    data = request.json
    
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO contracts
            (b_id, contract_no, party_a, project_order_no, total_amt, paid_amt, sign_date, owner_id, status,
             contract_name, classification, is_audit, pending_acceptance_amount,
             cost, gross_profit, acceptance_date, expected_income_date,
             expected_income_year, business_type, total_cost, acceptance_nodes, payment_nodes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """, (
            data.get('b_id'), data.get('contract_no'), data.get('party_a'), data.get('project_order_no'),
            data.get('total_amt'), 0, data.get('sign_date'), data.get('owner_id'), '执行中',
            data.get('contract_name'), data.get('classification'), data.get('is_audit'), data.get('pending_acceptance_amount'),
            data.get('cost'), data.get('gross_profit'), data.get('acceptance_date'), data.get('expected_income_date'),
            data.get('expected_income_year'), data.get('business_type'), data.get('acceptance_nodes'), data.get('payment_nodes')
        ))
        db.commit()
        contract_id = cursor.lastrowid
        
        return jsonify({'code': 200, 'message': '合同创建成功', 'data': {'id': contract_id}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@app.route('/api/contracts/<int:contract_id>', methods=['PUT'])
def update_contract(contract_id):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    data = request.json
    
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            UPDATE contracts SET
                contract_name=?, contract_no=?, party_a=?, project_order_no=?, total_amt=?, sign_date=?,
                classification=?, is_audit=?, pending_acceptance_amount=?,
                cost=?, gross_profit=?, acceptance_date=?, expected_income_date=?,
                expected_income_year=?, business_type=?, status=?, owner_id=?,
                acceptance_nodes=?, payment_nodes=?
            WHERE id=?
        """, (
            data.get('contract_name'), data.get('contract_no'), data.get('party_a'), data.get('project_order_no'),
            data.get('total_amt'), data.get('sign_date'), data.get('classification'), data.get('is_audit'),
            data.get('pending_acceptance_amount'), data.get('cost'), data.get('gross_profit'),
            data.get('acceptance_date'), data.get('expected_income_date'), data.get('expected_income_year'),
            data.get('business_type'), data.get('status'), data.get('owner_id'),
            data.get('acceptance_nodes'), data.get('payment_nodes'), contract_id
        ))
        db.commit()
        
        return jsonify({'code': 200, 'message': '合同更新成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@app.route('/api/contracts/<int:contract_id>', methods=['DELETE'])
def delete_contract(contract_id):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("DELETE FROM contracts WHERE id=?", (contract_id,))
        db.commit()
        
        return jsonify({'code': 200, 'message': '合同删除成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@app.route('/api/customers', methods=['GET'])
def get_customers():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    username = payload['username']
    role = payload['role']
    
    db = get_db()
    cursor = db.cursor()
    
    if role == '主任' or role == '院长':
        cursor.execute("""
            SELECT c.*, u.name as owner_name 
            FROM customers c 
            LEFT JOIN users u ON c.owner_id = u.username 
            ORDER BY c.created_at DESC
        """)
    else:
        cursor.execute("""
            SELECT c.*, u.name as owner_name 
            FROM customers c 
            LEFT JOIN users u ON c.owner_id = u.username 
            WHERE c.owner_id = ? 
            ORDER BY c.created_at DESC
        """, (username,))
    
    rows = cursor.fetchall()
    customers = []
    for row in rows:
        customers.append(dict(row))
    
    return jsonify({'code': 200, 'message': 'success', 'data': customers})


@app.route('/api/customers', methods=['POST'])
def create_customer():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    data = request.json
    
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO customers (name, contact_name, phone, email, industry, region, level, owner_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get('name'), data.get('contact_name'), data.get('phone'), data.get('email'),
            data.get('industry'), data.get('region'), data.get('level'), data.get('owner_id')
        ))
        db.commit()
        
        return jsonify({'code': 200, 'message': '客户创建成功', 'data': {'id': cursor.lastrowid}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@app.route('/api/customers/<int:cust_id>', methods=['DELETE'])
def delete_customer(cust_id):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("DELETE FROM customers WHERE id=?", (cust_id,))
        db.commit()
        
        return jsonify({'code': 200, 'message': '客户删除成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@app.route('/api/business', methods=['GET'])
def get_business():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    username = payload['username']
    role = payload['role']
    
    db = get_db()
    cursor = db.cursor()
    
    if role == '主任' or role == '院长':
        cursor.execute("""
            SELECT b.*, c.name as customer_name, u.name as owner_name 
            FROM business b 
            LEFT JOIN customers c ON b.cust_id = c.id 
            LEFT JOIN users u ON b.owner_id = u.username 
            WHERE b.status = 'active' 
            ORDER BY b.created_at DESC
        """)
    else:
        cursor.execute("""
            SELECT b.*, c.name as customer_name, u.name as owner_name 
            FROM business b 
            LEFT JOIN customers c ON b.cust_id = c.id 
            LEFT JOIN users u ON b.owner_id = u.username 
            WHERE b.owner_id = ? AND b.status = 'active' 
            ORDER BY b.created_at DESC
        """, (username,))
    
    rows = cursor.fetchall()
    business = []
    for row in rows:
        business.append(dict(row))
    
    return jsonify({'code': 200, 'message': 'success', 'data': business})


@app.route('/api/business', methods=['POST'])
def create_business():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    data = request.json
    
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO business (title, cust_id, amount, stage, predict_date, source, industry, region, owner_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get('title'), data.get('cust_id'), data.get('amount'), data.get('stage'),
            data.get('predict_date'), data.get('source'), data.get('industry'), data.get('region'), data.get('owner_id')
        ))
        db.commit()
        
        return jsonify({'code': 200, 'message': '商机创建成功', 'data': {'id': cursor.lastrowid}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@app.route('/api/business/<int:business_id>', methods=['DELETE'])
def delete_business(business_id):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("DELETE FROM business WHERE id=?", (business_id,))
        db.commit()
        
        return jsonify({'code': 200, 'message': '商机删除成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@app.route('/api/dashboard', methods=['GET'])
def get_dashboard():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    username = payload['username']
    role = payload['role']
    
    db = get_db()
    cursor = db.cursor()
    
    result = {}
    
    if role == '主任' or role == '院长':
        cursor.execute("SELECT COUNT(*) as total FROM customers")
        result['total_customers'] = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(*) as total FROM business WHERE status = 'active'")
        result['total_business'] = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(*) as total FROM contracts")
        result['total_contracts'] = cursor.fetchone()['total']
        
        cursor.execute("SELECT SUM(total_amt) as total FROM contracts")
        total = cursor.fetchone()['total'] or 0
        result['contracts_amount'] = total
        
        cursor.execute("SELECT SUM(amount) as total FROM payment_records")
        total = cursor.fetchone()['total'] or 0
        result['total_payments'] = total
    else:
        cursor.execute("SELECT COUNT(*) as total FROM customers WHERE owner_id = ?", (username,))
        result['total_customers'] = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(*) as total FROM business WHERE owner_id = ? AND status = 'active'", (username,))
        result['total_business'] = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(*) as total FROM contracts WHERE owner_id = ?", (username,))
        result['total_contracts'] = cursor.fetchone()['total']
        
        cursor.execute("SELECT SUM(total_amt) as total FROM contracts WHERE owner_id = ?", (username,))
        total = cursor.fetchone()['total'] or 0
        result['contracts_amount'] = total
        
        cursor.execute("""
            SELECT SUM(pr.amount) as total 
            FROM payment_records pr 
            JOIN contracts c ON pr.contract_id = c.id 
            WHERE c.owner_id = ?
        """, (username,))
        total = cursor.fetchone()['total'] or 0
        result['total_payments'] = total
    
    cursor.execute("""
        SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count 
        FROM customers 
        WHERE created_at >= DATE('now', '-12 months') 
        GROUP BY strftime('%Y-%m', created_at) 
        ORDER BY month
    """)
    customer_monthly = {row['month']: row['count'] for row in cursor.fetchall()}
    
    cursor.execute("""
        SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count 
        FROM business 
        WHERE status = 'active' AND created_at >= DATE('now', '-12 months') 
        GROUP BY strftime('%Y-%m', created_at) 
        ORDER BY month
    """)
    business_monthly = {row['month']: row['count'] for row in cursor.fetchall()}
    
    cursor.execute("""
        SELECT strftime('%Y-%m', sign_date) as month, COUNT(*) as count 
        FROM contracts 
        WHERE sign_date >= DATE('now', '-12 months') 
        GROUP BY strftime('%Y-%m', sign_date) 
        ORDER BY month
    """)
    contract_monthly = {row['month']: row['count'] for row in cursor.fetchall()}
    
    months = []
    customer_data = []
    business_data = []
    contract_data = []
    
    for i in range(12):
        date = datetime.now() - timedelta(days=i*30)
        month_str = date.strftime('%Y-%m')
        months.insert(0, date.strftime('%m月'))
        customer_data.insert(0, customer_monthly.get(month_str, 0))
        business_data.insert(0, business_monthly.get(month_str, 0))
        contract_data.insert(0, contract_monthly.get(month_str, 0))
    
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


@app.route('/api/users', methods=['GET'])
def get_users():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    if payload['role'] != '主任' and payload['role'] != '院长':
        return jsonify({'code': 403, 'message': '无权访问', 'data': None})
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT username, name, role FROM users ORDER BY name")
    
    rows = cursor.fetchall()
    users = []
    for row in rows:
        users.append(dict(row))
    
    return jsonify({'code': 200, 'message': 'success', 'data': users})


@app.route('/api/users', methods=['POST'])
def create_user():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    if payload['role'] != '主任' and payload['role'] != '院长':
        return jsonify({'code': 403, 'message': '无权访问', 'data': None})
    
    data = request.json
    
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("SELECT username FROM users WHERE username = ?", (data.get('username'),))
        if cursor.fetchone():
            return jsonify({'code': 400, 'message': '用户名已存在', 'data': None})
        
        hashed_pwd = hash_password(data.get('password'))
        cursor.execute("""
            INSERT INTO users (username, password_hash, name, role)
            VALUES (?, ?, ?, ?)
        """, (data.get('username'), hashed_pwd, data.get('name'), data.get('role')))
        db.commit()
        
        return jsonify({'code': 200, 'message': '用户创建成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@app.route('/api/users/<username>', methods=['DELETE'])
def delete_user(username):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    if payload['role'] != '主任' and payload['role'] != '院长':
        return jsonify({'code': 403, 'message': '无权访问', 'data': None})
    
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("DELETE FROM users WHERE username = ?", (username,))
        db.commit()
        
        return jsonify({'code': 200, 'message': '用户删除成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@app.route('/api/payment_records', methods=['GET'])
def get_payment_records():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    contract_id = request.args.get('contract_id')
    username = payload['username']
    role = payload['role']
    
    db = get_db()
    cursor = db.cursor()
    
    if contract_id:
        cursor.execute("""
            SELECT pr.*, c.contract_name, c.contract_no, u.name as owner_name 
            FROM payment_records pr 
            LEFT JOIN contracts c ON pr.contract_id = c.id 
            LEFT JOIN users u ON c.owner_id = u.username 
            WHERE pr.contract_id = ? 
            ORDER BY pr.payment_date DESC
        """, (contract_id,))
    else:
        if role == '主任' or role == '院长':
            cursor.execute("""
                SELECT pr.*, c.contract_name, c.contract_no, u.name as owner_name 
                FROM payment_records pr 
                LEFT JOIN contracts c ON pr.contract_id = c.id 
                LEFT JOIN users u ON c.owner_id = u.username 
                ORDER BY pr.payment_date DESC
            """)
        else:
            cursor.execute("""
                SELECT pr.*, c.contract_name, c.contract_no, u.name as owner_name 
                FROM payment_records pr 
                LEFT JOIN contracts c ON pr.contract_id = c.id 
                LEFT JOIN users u ON c.owner_id = u.username 
                WHERE c.owner_id = ? 
                ORDER BY pr.payment_date DESC
            """, (username,))
    
    rows = cursor.fetchall()
    records = []
    for row in rows:
        records.append(dict(row))
    
    return jsonify({'code': 200, 'message': 'success', 'data': records})


@app.route('/api/payment_records', methods=['POST'])
def create_payment_record():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    data = request.json
    
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO payment_records (contract_id, payment_date, amount, note)
            VALUES (?, ?, ?, ?)
        """, (data.get('contract_id'), data.get('payment_date'), data.get('amount'), data.get('note')))
        db.commit()
        
        cursor.execute("SELECT SUM(amount) as total FROM payment_records WHERE contract_id = ?", (data.get('contract_id'),))
        total_paid = cursor.fetchone()['total'] or 0
        cursor.execute("UPDATE contracts SET paid_amt = ? WHERE id = ?", (total_paid, data.get('contract_id')))
        db.commit()
        
        return jsonify({'code': 200, 'message': '回款记录创建成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@app.route('/api/payment_records/<int:record_id>', methods=['DELETE'])
def delete_payment_record(record_id):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("SELECT contract_id FROM payment_records WHERE id = ?", (record_id,))
        row = cursor.fetchone()
        if row:
            contract_id = row['contract_id']
            
            cursor.execute("DELETE FROM payment_records WHERE id = ?", (record_id,))
            
            cursor.execute("SELECT SUM(amount) as total FROM payment_records WHERE contract_id = ?", (contract_id,))
            total_paid = cursor.fetchone()['total'] or 0
            cursor.execute("UPDATE contracts SET paid_amt = ? WHERE id = ?", (total_paid, contract_id))
        
        db.commit()
        
        return jsonify({'code': 200, 'message': '回款记录删除成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@app.route('/api/business_stage_logs', methods=['GET'])
def get_stage_logs():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    business_id = request.args.get('business_id')
    
    db = get_db()
    cursor = db.cursor()
    
    if business_id:
        cursor.execute("SELECT * FROM business_stage_logs WHERE business_id = ? ORDER BY changed_at DESC", (business_id,))
    else:
        cursor.execute("SELECT * FROM business_stage_logs ORDER BY changed_at DESC")
    
    rows = cursor.fetchall()
    logs = []
    for row in rows:
        logs.append(dict(row))
    
    return jsonify({'code': 200, 'message': 'success', 'data': logs})


@app.route('/api/pool', methods=['GET'])
def get_pool():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT * FROM customers WHERE owner_id IS NULL OR owner_id = '' ORDER BY created_at DESC")
    rows = cursor.fetchall()
    pool_data = []
    for row in rows:
        item = dict(row)
        item['quality_score'] = 65 + (item.get('id', 0) % 35)
        pool_data.append(item)
    
    return jsonify({'code': 200, 'message': 'success', 'data': pool_data})


@app.route('/api/workhours', methods=['GET'])
def get_workhours():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT wh.*, b.title as project_name, u.name as user_name
        FROM work_hours wh
        LEFT JOIN business b ON wh.business_id = b.id
        LEFT JOIN users u ON wh.user_id = u.username
        ORDER BY wh.work_date DESC
    """)
    rows = cursor.fetchall()
    workhours = []
    for row in rows:
        item = dict(row)
        item['date'] = item.pop('work_date')
        item['task_name'] = item.get('description', '')[:20]
        workhours.append(item)
    
    return jsonify({'code': 200, 'message': 'success', 'data': workhours})


@app.route('/api/projects', methods=['GET'])
def get_projects():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT b.id, b.title as project_name, c.name as customer_name,
               b.created_at as start_date, b.predict_date as end_date,
               b.stage, b.status, b.project_manager as manager, 
               b.owner_id, u.name as owner_name,
               b.amount, b.probability
        FROM business b
        LEFT JOIN customers c ON b.cust_id = c.id
        LEFT JOIN users u ON b.owner_id = u.username
        WHERE b.status = 'active'
        ORDER BY b.created_at DESC
    """)
    rows = cursor.fetchall()
    projects = []
    for row in rows:
        item = dict(row)
        stage_progress = {
            '需求确认': 20, '方案报价': 40, '商务谈判': 60, 
            '合同签署': 80, '项目启动': 90, '实施中': 95, '已完成': 100
        }
        item['progress'] = stage_progress.get(item.get('stage'), 30)
        status_map = {'active': '进行中'}
        item['status'] = status_map.get(item.get('status'), item.get('status', '进行中'))
        
        cursor.execute("""
            SELECT u.name FROM project_assignments pa
            LEFT JOIN users u ON pa.user_id = u.username
            WHERE pa.project_type = 'business' AND pa.project_id = ?
        """, (item['id'],))
        members = cursor.fetchall()
        item['team_members'] = [m[0] for m in members]
        if not item['team_members'] and item['manager']:
            item['team_members'] = [item['manager']]
        
        projects.append(item)
    
    return jsonify({'code': 200, 'message': 'success', 'data': projects})


@app.route('/api/search', methods=['GET'])
def search():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    keyword = request.args.get('keyword', '')
    
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT id, name, company, phone, level, source FROM customers WHERE name LIKE ? OR company LIKE ?", (f'%{keyword}%', f'%{keyword}%'))
    customers = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT id, title, amount, stage, probability, owner_id FROM business WHERE title LIKE ? OR stage LIKE ?", (f'%{keyword}%', f'%{keyword}%'))
    business = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT id, contract_name, contract_no, total_amt, sign_date FROM contracts WHERE contract_name LIKE ? OR contract_no LIKE ?", (f'%{keyword}%', f'%{keyword}%'))
    contracts = [dict(row) for row in cursor.fetchall()]
    
    return jsonify({'code': 200, 'message': 'success', 'data': {
        'customers': customers,
        'business': business,
        'contracts': contracts
    }})


@app.route('/api/contracts/upload', methods=['POST'])
def upload_contract_file():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    contract_id = request.form.get('contract_id', type=int)
    file_type = request.form.get('file_type')
    
    if 'file' not in request.files:
        return jsonify({'code': 400, 'message': '请选择文件', 'data': None})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'code': 400, 'message': '请选择文件', 'data': None})
    
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _, ext = os.path.splitext(file.filename)
    filename = f"{contract_id}_{file_type}_{timestamp}{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    
    file.save(file_path)
    
    db = get_db()
    cursor = db.cursor()
    
    if file_type == 'contract':
        cursor.execute("UPDATE contracts SET contract_file_path = ? WHERE id = ?", (f"uploads/contracts/{filename}", contract_id))
    elif file_type == 'tech':
        cursor.execute("UPDATE contracts SET tech_agreement_file_path = ? WHERE id = ?", (f"uploads/contracts/{filename}", contract_id))
    
    db.commit()
    
    return jsonify({'code': 200, 'message': '文件上传成功', 'data': {'file_path': f"uploads/contracts/{filename}"}})


@app.route('/api/contracts/download/<int:contract_id>/<file_type>', methods=['GET'])
def download_contract_file(contract_id, file_type):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        token = request.args.get('token', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM contracts WHERE id = ?", (contract_id,))
    row = cursor.fetchone()
    
    if not row:
        return jsonify({'code': 404, 'message': '合同不存在', 'data': None})
    
    row_dict = dict(row)
    
    if file_type == 'contract':
        file_path = row_dict.get('contract_file_path')
    elif file_type == 'tech':
        file_path = row_dict.get('tech_agreement_file_path')
    else:
        return jsonify({'code': 400, 'message': '无效的文件类型', 'data': None})
    
    if not file_path:
        return jsonify({'code': 404, 'message': '文件不存在', 'data': None})
    
    full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), file_path)
    
    if not os.path.exists(full_path):
        return jsonify({'code': 404, 'message': '文件不存在', 'data': None})
    
    return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path), as_attachment=False)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)