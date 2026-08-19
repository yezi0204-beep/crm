"""验收级分成验证：框架合同每次验收可单独分配不同分成比例。
场景：
  合同 owner=sales_a, is_framework=1, total_amt=100万
  1月验收6万：分成 sales_a 70%, sales_b 30%
  2月验收8万：分成 sales_a 40%, sales_b 60%
  → sales_a 累计 = 6万×70% + 8万×40% = 4.2万 + 3.2万 = 7.4万
  → sales_b 累计 = 6万×30% + 8万×60% = 1.8万 + 4.8万 = 6.6万
  合同级分成（如有）应被验收级分成覆盖
"""
import sys, os, sqlite3, tempfile, shutil
from datetime import datetime

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
sys.path.insert(0, BACKEND_DIR)

tmp = tempfile.mkdtemp()
tmp_db = os.path.join(tmp, 'test_acc_comm.db')
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
from routes.contracts import contracts_bp
from routes.appraisal import appraisal_bp

test_app = Flask(__name__)
setup_extensions(test_app)
test_app.register_blueprint(contracts_bp)
test_app.register_blueprint(appraisal_bp, url_prefix='/api/appraisal')

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
                total_amt REAL DEFAULT 0, paid_amt REAL DEFAULT 0, pending_amt REAL DEFAULT 0,
                sign_date TEXT, owner_id TEXT, status TEXT DEFAULT '执行中',
                classification TEXT, is_audit TEXT,
                pending_acceptance_amount REAL DEFAULT 0,
                cost REAL, gross_profit REAL, acceptance_date TEXT,
                expected_income_date TEXT, expected_income_year TEXT,
                business_type TEXT, total_cost REAL DEFAULT 0,
                acceptance_nodes TEXT, payment_nodes TEXT, note TEXT,
                is_framework INTEGER DEFAULT 0
            )
        """)
    except Exception:
        pass
    pw = hash_password('123456')
    for u, name, role, dept, annual, basic, perf in [
        ('sales_a', '销售A', '销售', '应用中心', 1200000, 10000, 5000),
        ('sales_b', '销售B', '销售', '应用中心', 1200000, 10000, 5000),
        ('dir_c',   '主任C', '主任', '应用中心',       0, 15000, 2000),
    ]:
        cur.execute("INSERT INTO users (username, password_hash, name, role, department, status,"
                    " basic_salary, base_performance, annual_target_amount, is_sales_override)"
                    " VALUES (?, ?, ?, ?, ?, '在职', ?, ?, ?, 0)",
                    (u, pw, name, role, dept, basic, perf, annual))

    today_y = datetime.now().year
    # 框架合同 owner=sales_a
    cur.execute("""INSERT INTO contracts (contract_no, contract_name, total_amt, sign_date, owner_id, status,
                                          classification, is_audit, pending_acceptance_amount, pending_amt,
                                          paid_amt, party_a, is_framework)
                   VALUES ('C-FW-001', '框架合同A', 1000000, ?, 'sales_a', '执行中',
                           '分类A', '是', 0, 1000000, 0, '甲方A', 1)""", (f'{today_y}-01-01',))
    fw_contract_id = cur.lastrowid

    # 同时设一个合同级分成（sales_a 50%, sales_b 50%），验收级应覆盖它
    cur.execute("INSERT INTO contract_commissions (contract_id, username, ratio) VALUES (?, 'sales_a', 50)", (fw_contract_id,))
    cur.execute("INSERT INTO contract_commissions (contract_id, username, ratio) VALUES (?, 'sales_b', 50)", (fw_contract_id,))
    conn.commit()

client = test_app.test_client()
def hdr(user='dir_c', role='主任'):
    tk = create_token(user, user, role)
    return {'Authorization': f'Bearer {tk}'}

print('=== 1. 1月验收6万，分成 sales_a 70%, sales_b 30% ===')
with test_app.app_context():
    resp = client.post(f'/api/contracts/{fw_contract_id}/acceptances', headers=hdr(),
                       json={'acceptance_date': f'{today_y}-01-20', 'acceptance_amount': 60000,
                             'note': '1月验收',
                             'commissions': [{'username':'sales_a','ratio':70},{'username':'sales_b','ratio':30}]})
    assert resp.get_json()['code'] == 200, f'添加失败: {resp.get_json()}'
    print('  ✓ 1月验收6万 + 分成 70/30')

print('\n=== 2. 2月验收8万，分成 sales_a 40%, sales_b 60% ===')
with test_app.app_context():
    resp = client.post(f'/api/contracts/{fw_contract_id}/acceptances', headers=hdr(),
                       json={'acceptance_date': f'{today_y}-02-15', 'acceptance_amount': 80000,
                             'note': '2月验收',
                             'commissions': [{'username':'sales_a','ratio':40},{'username':'sales_b','ratio':60}]})
    assert resp.get_json()['code'] == 200
    print('  ✓ 2月验收8万 + 分成 40/60')

print('\n=== 3. GET 验收记录含分成分配 ===')
with test_app.app_context():
    resp = client.get(f'/api/contracts/{fw_contract_id}/acceptances', headers=hdr())
    data = resp.get_json()['data']
    assert len(data['acceptances']) == 2
    for a in data['acceptances']:
        assert len(a['commissions']) == 2, f"验收{a['id']}分成数={len(a['commissions'])}"
    print(f'  ✓ 2条验收记录各有2个分成')

print('\n=== 4. 1月考核：验收级分成覆盖合同级分成 ===')
with test_app.app_context():
    resp = client.get(f'/api/appraisal/monthly?year={today_y}&month=1', headers=hdr())
    rows = {r['username']: r for r in resp.get_json()['data']['rows']}
    a_actual = rows['sales_a']['cumulative_actual_amt']
    b_actual = rows['sales_b']['cumulative_actual_amt']
    # 1月验收6万，验收级分成 sales_a 70%=4.2万, sales_b 30%=1.8万
    # 合同级分成 50/50 应被覆盖
    print(f'  sales_a: actual={a_actual} (期望 42000 = 60000×70%)')
    print(f'  sales_b: actual={b_actual} (期望 18000 = 60000×30%)')
    assert abs(a_actual - 42000) < 0.5, f'sales_a 1月 actual={a_actual} 期望42000'
    assert abs(b_actual - 18000) < 0.5, f'sales_b 1月 actual={b_actual} 期望18000'
    print(f'  ✓ 验收级分成覆盖合同级分成')

print('\n=== 5. 2月累计：不同验收不同分成 ===')
with test_app.app_context():
    resp = client.get(f'/api/appraisal/monthly?year={today_y}&month=2', headers=hdr())
    rows = {r['username']: r for r in resp.get_json()['data']['rows']}
    a_actual = rows['sales_a']['cumulative_actual_amt']
    b_actual = rows['sales_b']['cumulative_actual_amt']
    # sales_a = 6万×70% + 8万×40% = 4.2万 + 3.2万 = 7.4万
    # sales_b = 6万×30% + 8万×60% = 1.8万 + 4.8万 = 6.6万
    print(f'  sales_a: actual={a_actual} (期望 74000 = 42000 + 32000)')
    print(f'  sales_b: actual={b_actual} (期望 66000 = 18000 + 48000)')
    assert abs(a_actual - 74000) < 0.5, f'sales_a 2月累计 actual={a_actual} 期望74000'
    assert abs(b_actual - 66000) < 0.5, f'sales_b 2月累计 actual={b_actual} 期望66000'
    print(f'  ✓ 每次验收独立分成，累计正确')

print('\n=== 6. 比例和≠100 → 400 拒绝 ===')
with test_app.app_context():
    resp = client.post(f'/api/contracts/{fw_contract_id}/acceptances', headers=hdr(),
                       json={'acceptance_date': f'{today_y}-03-10', 'acceptance_amount': 50000,
                             'commissions': [{'username':'sales_a','ratio':60},{'username':'sales_b','ratio':30}]})
    assert resp.get_json()['code'] == 400, f'应拒绝: {resp.get_json()}'
    print(f'  ✓ 90% 被拒绝: {resp.get_json()["message"]}')

conn.close()
shutil.rmtree(tmp, ignore_errors=True)
print('\n✅ 验收级分成功能所有测试通过')
