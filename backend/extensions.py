from flask import Flask, g, request, jsonify
from functools import wraps
import sqlite3
import bcrypt
import os
import uuid
import time
import threading
from datetime import datetime, timedelta
from collections import defaultdict

SECRET_KEY = os.environ.get('SECRET_KEY', "crm_secret_key_2026")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get('DB_PATH', os.path.join(BASE_DIR, "crm_app.db"))
UPLOAD_DIR = os.environ.get('UPLOAD_DIR', os.path.join(BASE_DIR, "uploads", "contracts"))

LOGIN_ATTEMPTS = defaultdict(list)
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300

ALLOWED_ORIGINS = [
    'http://localhost:5173',
    'http://localhost:3000',
    'http://127.0.0.1:5173',
]
_extra_origins = os.environ.get('CORS_ALLOWED_ORIGINS', '')
if _extra_origins:
    ALLOWED_ORIGINS.extend([o.strip() for o in _extra_origins.split(',') if o.strip()])


def get_db():
    if 'db' not in g:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        g.db = conn
        _init_tables(conn)
    return g.db


def close_db(error=None):
    if hasattr(g, 'db'):
        g.db.close()


def _init_tables(db):
    cursor = db.cursor()
    _init_business_table(cursor)
    _init_operation_logs_table(cursor)
    db.commit()


def _init_business_table(cursor):
    try:
        cursor.execute("ALTER TABLE business ADD COLUMN address TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE business ADD COLUMN customer_relation TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE business ADD COLUMN weekly_plan TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE business ADD COLUMN next_week_plan TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE business ADD COLUMN plan_week TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE business ADD COLUMN note TEXT")
    except:
        pass
    try:
        cursor.execute("""
            CREATE TABLE business_plan_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id INTEGER,
                plan_type TEXT,
                week_label TEXT,
                content TEXT,
                created_at TEXT,
                created_by TEXT,
                FOREIGN KEY (business_id) REFERENCES business(id)
            )
        """)
    except:
        pass


def _init_operation_logs_table(cursor):
    try:
        cursor.execute("""
            CREATE TABLE operation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                operation TEXT NOT NULL,
                module TEXT NOT NULL,
                detail TEXT,
                ip_address TEXT,
                created_at TEXT NOT NULL,
                is_read INTEGER DEFAULT 0
            )
        """)
    except:
        pass
    try:
        cursor.execute("ALTER TABLE operation_logs ADD COLUMN is_read INTEGER DEFAULT 0")
    except:
        pass


def record_operation_log(username, operation, module, detail=''):
    try:
        db = get_db()
        cursor = db.cursor()
        ip_address = request.remote_addr if request else ''
        cursor.execute("""
            INSERT INTO operation_logs (username, operation, module, detail, ip_address, created_at, is_read)
            VALUES (?, ?, ?, ?, ?, ?, 0)
        """, (username, operation, module, detail, ip_address, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        db.commit()
    except Exception as e:
        pass


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def check_password(password: str, hash_val: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hash_val.encode('utf-8'))


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


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        payload = verify_token(token)
        if not payload:
            return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
        request.current_user = payload
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    @token_required
    def decorated(*args, **kwargs):
        payload = request.current_user
        if payload['role'] not in ('主任', '院长'):
            return jsonify({'code': 403, 'message': '权限不足', 'data': None})
        return f(*args, **kwargs)
    return decorated


def check_login_rate_limit(ip_address):
    now = time.time()
    if ip_address in LOGIN_ATTEMPTS:
        LOGIN_ATTEMPTS[ip_address] = [t for t in LOGIN_ATTEMPTS[ip_address] if now - t < LOGIN_WINDOW_SECONDS]
        if len(LOGIN_ATTEMPTS[ip_address]) >= LOGIN_MAX_ATTEMPTS:
            return False
    return True


def record_login_attempt(ip_address):
    LOGIN_ATTEMPTS[ip_address].append(time.time())


INACTIVE_DAYS = 100


def cleanup_inactive_customers():
    from datetime import datetime, timedelta
    cutoff_date = (datetime.now() - timedelta(days=INACTIVE_DAYS)).strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT c.id, c.name, c.company, c.last_follow, c.created_at, c.owner_id
            FROM customers c
            WHERE (c.last_follow IS NOT NULL AND c.last_follow < ?)
               OR (c.last_follow IS NULL AND c.created_at < ?)
        """, (cutoff_date, cutoff_date))
        
        customers_to_delete = cursor.fetchall()
        
        deleted_count = 0
        for customer in customers_to_delete:
            cust_id = customer['id']
            try:
                cursor.execute("UPDATE business SET cust_id = NULL WHERE cust_id = ?", (cust_id,))
                cursor.execute("DELETE FROM customers WHERE id = ?", (cust_id,))
                deleted_count += 1
            except Exception:
                conn.rollback()
        
        if deleted_count > 0:
            conn.commit()
        else:
            conn.rollback()
        
        conn.close()
        return deleted_count
    except Exception:
        return 0


def update_customer_last_follow(customer_id):
    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE customers SET last_follow = ? WHERE id = ?",
            (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), customer_id)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def setup_extensions(app: Flask):
    app.teardown_appcontext(close_db)

    @app.after_request
    def after_request(response):
        origin = request.headers.get('Origin', '')
        if origin in ALLOWED_ORIGINS:
            response.headers.add('Access-Control-Allow-Origin', origin)
            response.headers.add('Access-Control-Allow-Credentials', 'true')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,PATCH,OPTIONS')
        return response

    @app.route('/api/', methods=['OPTIONS'])
    def options():
        return jsonify({'code': 200, 'message': 'OK', 'data': None})
