"""验证 /api/appraisal/yearly 接口：1-12月部门完成率 + 各销售月度完成率。"""
import sys, os, tempfile, shutil
from datetime import datetime

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
sys.path.insert(0, BACKEND_DIR)

tmp = tempfile.mkdtemp()
tmp_db = os.path.join(tmp, 'test_yearly.db')
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

    # 主任(3000万) + 2销售(各960万，月度80万)
    users = [
        ('dir_x',   '主任X', '主任', '应用中心', 30000000, 15000, 5000, 1),
        ('sales_a', '销售A', '销售', '应用中心',  9600000, 10000, 5000, 0),
        ('sales_b', '销售B', '销售', '应用中心',  9600000, 10000, 5000, 0),
    ]
    pw = hash_password('123456')
    for u, name, role, dept, annual, basic, perf, override in users:
        cur.execute("INSERT INTO users (username, password_hash, name, role, department, status,"
                    " basic_salary, base_performance, annual_target_amount, is_sales_override)"
                    " VALUES (?, ?, ?, ?, ?, '在职', ?, ?, ?, ?)",
                    (u, pw, name, role, dept, basic, perf, annual, override))

    # 2月合同：A 64万（80%），B 160万（200%→150%封顶）
    today_y = datetime.now().year
    ym = f'{today_y:04d}-02-15'
    cur.execute("""INSERT INTO contracts (contract_no, contract_name, total_amt, sign_date, owner_id, status,
                                          classification, is_audit, pending_acceptance_amount, pending_amt,
                                          paid_amt, party_a)
                   VALUES ('C-A', '合同A', 640000, ?, 'sales_a', '执行中', '分类', '是', 0, 640000, 0, '甲方')""", (ym,))
    cur.execute("""INSERT INTO contracts (contract_no, contract_name, total_amt, sign_date, owner_id, status,
                                          classification, is_audit, pending_acceptance_amount, pending_amt,
                                          paid_amt, party_a)
                   VALUES ('C-B', '合同B', 1600000, ?, 'sales_b', '执行中', '分类', '是', 0, 1600000, 0, '甲方')""", (ym,))
    conn.commit()

from routes.appraisal import appraisal_bp as abp
test_app.register_blueprint(abp, url_prefix='/api/appraisal')
client = test_app.test_client()

def hdr(user='dir_x', role='主任'):
    tk = create_token(user, user, role)
    return {'Authorization': f'Bearer {tk}'}

print('=== /yearly 年度趋势接口验证 ===')
with test_app.app_context():
    resp = client.get(f'/api/appraisal/yearly?year={today_y}', headers=hdr('dir_x', '主任'))
    data = resp.get_json()
    assert resp.status_code == 200 and data.get('code') == 200, f'失败：{data}'
    d = data['data']
    dept_rates = d['dept_rates']
    sales_trend = d['sales_trend']

    # 1月：累计实际从2月起算 → 1月所有人为0，主任无累计实际 → dept_rate=0
    # 实际上1月 build_monthly_rows: 主任目标=250万，累计实际=0（部门销售1月无合同）→ 完成率0%
    r1 = dept_rates.get('1')
    assert r1 is not None, f'1月部门完成率缺失：{dept_rates}'
    print(f'  ✓ 1月部门完成率 = {r1}%（1月无累计实际，从2月起算）')

    # 2月：部门完成率 = 224万/250万 = 89.6%
    r2 = dept_rates.get('2')
    assert round(float(r2), 2) == 89.60, f'2月部门完成率错误：{r2}，期望 89.6%'
    print(f'  ✓ 2月部门完成率 = {r2}%（224万/250万 = 89.6%）')

    # 3-12月：累计实际仍=224万（只有2月合同），目标仍=250万 → 89.6%
    r3 = dept_rates.get('3')
    assert round(float(r3), 2) == 89.60, f'3月部门完成率错误：{r3}，期望 89.6%'
    print(f'  ✓ 3月部门完成率 = {r3}%（累计不变）')

    # 销售趋势
    sales_map = {s['username']: s for s in sales_trend}
    assert 'sales_a' in sales_map and 'sales_b' in sales_map
    # sales_a 2月完成率 = 80%
    a_r2 = sales_map['sales_a']['rates'].get('2')
    assert round(float(a_r2), 2) == 80.00, f'sales_a 2月完成率错误：{a_r2}，期望 80%'
    # sales_b 2月完成率 = 150%（封顶）
    b_r2 = sales_map['sales_b']['rates'].get('2')
    assert round(float(b_r2), 2) == 150.00, f'sales_b 2月完成率错误：{b_r2}，期望 150%'
    print(f'  ✓ sales_a 2月完成率 = {a_r2}%，sales_b 2月完成率 = {b_r2}%（封顶）')

    # 主任不作为个体销售出现在 sales_trend
    assert 'dir_x' not in sales_map, f'主任不应出现在销售趋势中：{sales_trend}'
    print(f'  ✓ 主任(dir_x)未出现在销售趋势（单独在 dept_rates）')

# 权限验证
print('\n=== 权限：普通销售访问 /yearly 必须403 ===')
with test_app.app_context():
    sales_h = {'Authorization': f'Bearer {create_token("sales_a","sales_a","销售")}'}
    r = client.get(f'/api/appraisal/yearly?year={today_y}', headers=sales_h)
    body_code = r.get_json().get('code') if r.is_json else None
    assert body_code == 403, f'FAIL: /yearly 业务 code={body_code} 期望 403'
    print(f'  ✓ GET /yearly → business_code={body_code} 权限正确')

conn.close()
shutil.rmtree(tmp, ignore_errors=True)
print('\n✅ /yearly 年度趋势接口验证通过')
