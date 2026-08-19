"""验证人力角色权限：
- 人力可以访问 /monthly（月度考核总览）
- 人力不能访问 /yearly（年度趋势）
- 人力不能访问 /config（配置指标）
- 人力不能访问 /export（导出）
- 人力可以访问 /mine（个人考核）
"""
import sys, os, tempfile, shutil
from datetime import datetime

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
sys.path.insert(0, BACKEND_DIR)

tmp = tempfile.mkdtemp()
tmp_db = os.path.join(tmp, 'test_hr_role.db')
os.environ['DB_PATH'] = tmp_db
os.environ['SECRET_KEY'] = 'test_secret'
os.environ['UPLOAD_DIR'] = os.path.join(tmp, 'uploads')
os.makedirs(os.environ['UPLOAD_DIR'], exist_ok=True)

for m in list(sys.modules.keys()):
    if any(p in m for p in ('extensions','config','security','scheduler','qa_engine','ai_analyzer',
                           'vector_search','routes','app')):
        del sys.modules[m]

from flask import Flask
from extensions import setup_extensions, ensure_tables, get_db, hash_password, create_token

test_app = Flask(__name__)
setup_extensions(test_app)
with test_app.app_context():
    ensure_tables()
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                b_id INTEGER, cust_id INTEGER,
                contract_no TEXT, contract_name TEXT,
                party_a TEXT, project_order_no TEXT,
                total_amt REAL DEFAULT 0, paid_amt REAL DEFAULT 0,
                pending_amt REAL DEFAULT 0,
                sign_date TEXT, owner_id TEXT, status TEXT DEFAULT '执行中',
                classification TEXT, is_audit TEXT,
                pending_acceptance_amount REAL DEFAULT 0,
                cost REAL, gross_profit REAL, acceptance_date TEXT,
                expected_income_date TEXT, expected_income_year TEXT,
                business_type TEXT, total_cost REAL DEFAULT 0,
                acceptance_nodes TEXT, payment_nodes TEXT,
                note TEXT,
                is_framework INTEGER DEFAULT 0
            )
        """)
    except Exception:
        pass

    # 主任 + 人力 + 销售
    users = [
        ('dir_x',   '主任X', '主任', '应用中心', 30000000, 15000, 5000, 1),
        ('hr_y',    '人力Y', '人力', '人力资源部', 0, 8000, 2000, 0),
        ('sales_a', '销售A', '销售', '应用中心', 9600000, 10000, 5000, 0),
    ]
    pw = hash_password('123456')
    for u, name, role, dept, annual, basic, perf, override in users:
        cur.execute("INSERT INTO users (username, password_hash, name, role, department, status,"
                    " basic_salary, base_performance, annual_target_amount, is_sales_override)"
                    " VALUES (?, ?, ?, ?, ?, '在职', ?, ?, ?, ?)",
                    (u, pw, name, role, dept, basic, perf, annual, override))

    today_y = datetime.now().year
    ym = f'{today_y:04d}-02-15'
    cur.execute("""INSERT INTO contracts (contract_no, contract_name, total_amt, sign_date, owner_id, status,
                                          classification, is_audit, pending_acceptance_amount, pending_amt,
                                          paid_amt, party_a)
                   VALUES ('C-A', '合同A', 640000, ?, 'sales_a', '执行中', '分类', '是', 0, 640000, 0, '甲方')""", (ym,))
    conn.commit()

from routes.appraisal import appraisal_bp as abp
test_app.register_blueprint(abp, url_prefix='/api/appraisal')
client = test_app.test_client()

def hdr(user, role):
    tk = create_token(user, user, role)
    return {'Authorization': f'Bearer {tk}'}

print('=== 人力角色权限验证 ===')

# 1. 人力可以访问 /monthly
with test_app.app_context():
    r = client.get(f'/api/appraisal/monthly?year={today_y}&month=2', headers=hdr('hr_y', '人力'))
    data = r.get_json()
    assert r.status_code == 200 and data.get('code') == 200, f'FAIL: 人力访问 /monthly 失败：{data}'
    rows = data['data']['rows']
    assert len(rows) > 0, 'FAIL: 人力应能看到考核数据'
    print(f'  ✓ 人力可以访问 /monthly（看到 {len(rows)} 行考核数据）')

# 2. 人力不能访问 /yearly
with test_app.app_context():
    r = client.get(f'/api/appraisal/yearly?year={today_y}', headers=hdr('hr_y', '人力'))
    data = r.get_json()
    assert data.get('code') == 403, f'FAIL: 人力不应能访问 /yearly：{data}'
    print(f'  ✓ 人力不能访问 /yearly（返回403）')

# 3. 人力不能访问 /config（GET）
with test_app.app_context():
    r = client.get(f'/api/appraisal/config/sales_a?year={today_y}', headers=hdr('hr_y', '人力'))
    data = r.get_json()
    assert data.get('code') == 403, f'FAIL: 人力不应能访问 /config GET：{data}'
    print(f'  ✓ 人力不能访问 /config GET（返回403）')

# 4. 人力不能访问 /config（POST）
with test_app.app_context():
    r = client.post('/api/appraisal/config', headers=hdr('hr_y', '人力'), json={
        'username': 'sales_a', 'year': today_y, 'basic_salary': 10000,
        'base_performance': 5000, 'annual_target_amount': 9600000, 'is_sales_override': 0,
        'monthly_overrides': {}
    })
    data = r.get_json()
    assert data.get('code') == 403, f'FAIL: 人力不应能访问 /config POST：{data}'
    print(f'  ✓ 人力不能访问 /config POST（返回403）')

# 5. 人力不能访问 /export
with test_app.app_context():
    r = client.get(f'/api/appraisal/export?year={today_y}&month=2', headers=hdr('hr_y', '人力'))
    try:
        data = r.get_json()
        code = data.get('code')
    except Exception:
        code = None
    assert code == 403, f'FAIL: 人力不应能访问 /export：code={code}'
    print(f'  ✓ 人力不能访问 /export（返回403）')

# 6. 人力可以访问 /mine（查看自己的考核）
with test_app.app_context():
    r = client.get(f'/api/appraisal/mine?year={today_y}&month=2', headers=hdr('hr_y', '人力'))
    data = r.get_json()
    assert r.status_code == 200 and data.get('code') == 200, f'FAIL: 人力访问 /mine 失败：{data}'
    print(f'  ✓ 人力可以访问 /mine（个人考核）')

# 7. 主任/院长仍可正常访问所有接口
with test_app.app_context():
    r = client.get(f'/api/appraisal/monthly?year={today_y}&month=2', headers=hdr('dir_x', '主任'))
    data = r.get_json()
    assert data.get('code') == 200, f'FAIL: 主任访问 /monthly 失败：{data}'
    r2 = client.get(f'/api/appraisal/yearly?year={today_y}', headers=hdr('dir_x', '主任'))
    data2 = r2.get_json()
    assert data2.get('code') == 200, f'FAIL: 主任访问 /yearly 失败：{data2}'
    print(f'  ✓ 主任仍可访问 /monthly 和 /yearly（权限无回归）')

# 8. 普通销售不能访问 /monthly
with test_app.app_context():
    r = client.get(f'/api/appraisal/monthly?year={today_y}&month=2', headers=hdr('sales_a', '销售'))
    data = r.get_json()
    assert data.get('code') == 403, f'FAIL: 销售不应能访问 /monthly：{data}'
    print(f'  ✓ 普通销售不能访问 /monthly（返回403）')

conn.close()
shutil.rmtree(tmp, ignore_errors=True)
print('\n✅ 人力角色权限验证通过')
