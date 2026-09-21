from flask import Flask, g, request, jsonify
from functools import wraps
import json
import bcrypt
import os
import secrets
import uuid
import time
import threading
from datetime import datetime, timedelta
from collections import defaultdict

import db as _db
from db import open_db  # noqa: F401  请求上下文外（调度器/线程池）使用

# 优先取环境变量；未设置时使用进程内随机密钥（认证基于 DB token，不依赖此值，
# 因此重启失效不影响登录态）。切勿再回退到硬编码值。
SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
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
    """获取请求级数据库连接（MySQL，经 sqlite3 兼容适配层）。

    连接缓存在 g.db，请求结束由 close_db 关闭。表结构由迁移脚本
    scripts/migrate_sqlite_to_mysql.py 一次性建立，此处不做任何 DDL。
    """
    return _db.get_db()


def close_db(error=None):
    _db.close_db(error)


def auto_complete_if_paid_off(cursor, contract_id):
    """待回款归零的执行中合同自动标记为已完成。

    在回款新增/编辑/删除/导入及合同编辑（改合同额）后调用。
    仅处理 total_amt > 0 的合同（未填合同额的无法判断，不联动）。
    """
    try:
        cursor.execute("""
            UPDATE contracts SET status='已完成'
            WHERE id=? AND status='执行中'
              AND COALESCE(total_amt, 0) > 0
              AND COALESCE(total_amt, 0) - COALESCE(paid_amt, 0) <= 0
        """, (contract_id,))
    except Exception as e:
        print(f"[auto_complete] 合同 {contract_id} 回款完成状态联动失败: {e}")


# 迁移脚本建立的完整表清单（MySQL 硬切换后 schema 唯一来源是迁移脚本）
EXPECTED_TABLES = [
    'acceptance_commissions', 'ai_daily_reports', 'ai_operation_logs', 'ai_recommendations',
    'ai_tasks', 'bid_evaluations', 'business', 'business_plan_history', 'business_stage_logs',
    'business_tags', 'campaign_audiences', 'campaign_automations', 'campaign_metrics',
    'campaigns', 'capabilities', 'company_qualifications', 'competitor_profiles',
    'contract_acceptances', 'contract_commissions', 'contract_monthly_forecast',
    'contract_monthly_forecast_bak', 'contract_monthly_forecast_bak2', 'contracts', 'costs',
    'crm_sync_config', 'custom_fields', 'customer_profiles', 'customers',
    'dept_annual_targets', 'dept_hour_allocations', 'dept_month_costs', 'duplicate_candidates',
    'enterprise_visits', 'enterprises', 'erp_connections', 'erp_sync_logs', 'follow_logs',
    'intelligence_agent_results', 'intelligence_leads', 'inventory_records', 'keyword_groups',
    'keywords', 'knowledge_base', 'knowledge_documents', 'knowledge_entities',
    'knowledge_relations', 'knowledge_vectors', 'lead_sources', 'lifecycle_logs',
    'monthly_targets', 'operation_logs', 'payment_plans', 'payment_records', 'permissions',
    'personnel_qualifications', 'products', 'project_assignments', 'projects',
    'quarterly_assessment_items', 'quarterly_assessments', 'quote_items', 'quotes',
    'raw_intelligence', 'role_permissions', 'sales_alerts', 'scraped_leads',
    'ticket_messages', 'ticket_surveys', 'tickets', 'tokens', 'user_hourly_rate',
    'user_preferences', 'user_roles', 'users', 'visits', 'work_hours',
]


def ensure_tables():
    """启动时校验 MySQL 中全部表齐全（不再执行任何 DDL）。

    缺表说明尚未跑迁移脚本 scripts/migrate_sqlite_to_mysql.py，直接抛异常 fail-fast。
    """
    conn = _db.open_db()
    try:
        cur = conn.cursor()
        cur.execute(
            'SELECT TABLE_NAME FROM information_schema.TABLES '
            'WHERE TABLE_SCHEMA = DATABASE()')
        existing = {r[0] for r in cur.fetchall()}
        missing = [t for t in EXPECTED_TABLES if t not in existing]
        if missing:
            raise RuntimeError(
                f"MySQL 缺少 {len(missing)} 张表: {missing}。"
                f"请先执行: python backend/scripts/migrate_sqlite_to_mysql.py")
        print(f"[ensure_tables] MySQL 表结构校验通过（{len(EXPECTED_TABLES)} 张表齐全）")
    finally:
        conn.close()



def get_user_permissions(username):
    """查询用户全部权限点（主角色 + user_roles 多角色 + 部门伪角色并集）。

    请求上下文内通过 g 缓存，每请求最多查询一次数据库。
    """
    from flask import has_request_context
    if has_request_context():
        cached = getattr(g, '_rbac_perms', None)
        if cached is not None:
            return cached
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT role FROM user_roles WHERE username = ?", (username,))
    roles = {r['role'] for r in cursor.fetchall()}
    cursor.execute("SELECT role, department FROM users WHERE username = ?", (username,))
    u = cursor.fetchone()
    if u:
        if u['role']:
            roles.add(u['role'])
        if u['department']:
            roles.add(f"dept:{u['department']}")
    perms = set()
    for role in roles:
        cursor.execute("SELECT permission_code FROM role_permissions WHERE role_code = ?", (role,))
        perms.update(r['permission_code'] for r in cursor.fetchall())
    perms = sorted(perms)
    if has_request_context():
        g._rbac_perms = perms
    return perms


def user_can(username, permission_code):
    """判断用户是否拥有指定权限点。"""
    return permission_code in get_user_permissions(username)


def require_permission(permission_code):
    """RBAC 权限装饰器：当前用户须持有指定权限点（传 list/tuple 时任一满足即可），否则 403。"""
    codes = [permission_code] if isinstance(permission_code, str) else list(permission_code)

    def decorator(f):
        @wraps(f)
        @token_required
        def decorated(*args, **kwargs):
            payload = request.current_user
            if not any(user_can(payload['username'], c) for c in codes):
                return jsonify({'code': 403, 'message': '权限不足', 'data': None})
            return f(*args, **kwargs)
        return decorated
    return decorator


def record_operation_log(username, operation, module, detail=''):
    try:
        db = get_db()
        cursor = db.cursor()
        ip_address = request.remote_addr if request else ''
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # ---- 7.1.4 不可抵赖性 + 7.1.2 完整性：操作签名 ----
        digest = ''
        signature = ''
        timestamp_utc = ''
        try:
            from security import get_integrity, get_non_repudiation
            integrity = get_integrity()
            non_rep = get_non_repudiation()
            signed = non_rep.sign_operation(
                username=username,
                operation=operation,
                module=module,
                detail=detail,
                extra={'ip': ip_address, 'created_at': created_at},
            )
            digest = signed['digest']
            signature = signed['signature']
            timestamp_utc = signed['timestamp']
        except Exception:
            pass

        cursor.execute("""
            INSERT INTO operation_logs (username, operation, module, detail, ip_address, created_at, is_read,
                                        digest, signature, timestamp_utc)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
        """, (username, operation, module, detail, ip_address, created_at,
              digest or None, signature or None, timestamp_utc or None))
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
    """管理类接口权限：等价于权限点 system.admin（默认授予 主任/院长，可改 role_permissions 表调整）。"""
    @wraps(f)
    @token_required
    def decorated(*args, **kwargs):
        payload = request.current_user
        if not user_can(payload['username'], 'system.admin'):
            return jsonify({'code': 403, 'message': '权限不足', 'data': None})
        return f(*args, **kwargs)
    return decorated


def appraisal_viewer_required(f):
    """月度考核查看权限：权限点 appraisal.view（默认 主任/院长/人力）。人力只能查看总览，不能配置/导出。"""
    @wraps(f)
    @token_required
    def decorated(*args, **kwargs):
        payload = request.current_user
        if not user_can(payload['username'], 'appraisal.view'):
            return jsonify({'code': 403, 'message': '权限不足', 'data': None})
        return f(*args, **kwargs)
    return decorated


def app_center_or_admin_required(f):
    """智能线索导入权限：权限点 intel.import（默认授予 主任/院长 及应用中心部门成员）。"""
    @wraps(f)
    @token_required
    def decorated(*args, **kwargs):
        payload = request.current_user
        if not user_can(payload['username'], 'intel.import'):
            return jsonify({'code': 403, 'message': '权限不足，仅应用中心成员可操作', 'data': None})
        return f(*args, **kwargs)
    return decorated


def check_login_rate_limit(ip_address):
    now = time.time()
    if ip_address in LOGIN_ATTEMPTS:
        LOGIN_ATTEMPTS[ip_address] = [t for t in LOGIN_ATTEMPTS[ip_address] if now - t < LOGIN_WINDOW_SECONDS]
        if len(LOGIN_ATTEMPTS[ip_address]) >= LOGIN_MAX_ATTEMPTS:
            oldest = LOGIN_ATTEMPTS[ip_address][0]
            wait_seconds = int(LOGIN_WINDOW_SECONDS - (now - oldest))
            return False, wait_seconds
    return True, 0


def record_login_attempt(ip_address):
    LOGIN_ATTEMPTS[ip_address].append(time.time())


def reset_login_rate_limit(ip_address=None):
    if ip_address:
        LOGIN_ATTEMPTS.pop(ip_address, None)
    else:
        LOGIN_ATTEMPTS.clear()


def update_customer_last_follow(customer_id):
    try:
        conn = open_db()
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
