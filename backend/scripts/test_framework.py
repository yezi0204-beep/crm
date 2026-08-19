"""框架合同验收记录功能验证：
1. GET/POST /contracts/<id>/acceptances 验收记录增查
2. 框架合同标记 is_framework=1
3. 考核按验收额计入（非按 total_amt）
4. 框架合同 + 分成组合：验收额 × ratio%
5. 普通合同不受框架合同验收记录影响
"""
import sys, os, sqlite3, tempfile, shutil
from datetime import datetime

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
sys.path.insert(0, BACKEND_DIR)

tmp = tempfile.mkdtemp()
tmp_db = os.path.join(tmp, 'test_framework.db')
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

    # 合同1：框架合同 owner=sales_a，total=100万（但考核按验收额计，不按100万）
    ym = f'{today_y:04d}-01-10'
    cur.execute("""INSERT INTO contracts (contract_no, contract_name, total_amt, sign_date, owner_id, status,
                                          classification, is_audit, pending_acceptance_amount, pending_amt,
                                          paid_amt, party_a, is_framework)
                   VALUES ('C-FW-001', '框架合同A', 1000000, ?, 'sales_a', '执行中',
                           '分类A', '是', 0, 1000000, 0, '甲方A', 1)""", (ym,))
    fw_contract_id = cur.lastrowid

    # 合同2：普通合同 owner=sales_b，total=20万（按 total_amt 计入）
    cur.execute("""INSERT INTO contracts (contract_no, contract_name, total_amt, sign_date, owner_id, status,
                                          classification, is_audit, pending_acceptance_amount, pending_amt,
                                          paid_amt, party_a, is_framework)
                   VALUES ('C-NM-001', '普通合同B', 200000, ?, 'sales_b', '执行中',
                           '分类B', '是', 0, 200000, 0, '甲方B', 0)""", (ym,))
    nm_contract_id = cur.lastrowid
    conn.commit()

client = test_app.test_client()
def hdr(user='dir_c', role='主任'):
    tk = create_token(user, user, role)
    return {'Authorization': f'Bearer {tk}'}

print('=== 1. 添加验收记录到框架合同 ===')
with test_app.app_context():
    # 1月验收 6万
    resp = client.post(f'/api/contracts/{fw_contract_id}/acceptances', headers=hdr(),
                       json={'acceptance_date': f'{today_y}-01-20', 'acceptance_amount': 60000, 'note': '1月验收'})
    assert resp.get_json()['code'] == 200, f'添加失败: {resp.get_json()}'
    # 2月验收 8万
    resp = client.post(f'/api/contracts/{fw_contract_id}/acceptances', headers=hdr(),
                       json={'acceptance_date': f'{today_y}-02-15', 'acceptance_amount': 80000, 'note': '2月验收'})
    assert resp.get_json()['code'] == 200
    # GET 回读
    resp = client.get(f'/api/contracts/{fw_contract_id}/acceptances', headers=hdr())
    data = resp.get_json()['data']
    assert data['is_framework'] == 1
    assert data['total_accepted'] == 140000, f"累计验收={data['total_accepted']} 期望140000"
    assert len(data['acceptances']) == 2
    print(f'  ✓ 添加2条验收记录，累计验收={data["total_accepted"]}（6万+8万=14万）')

print('\n=== 2. 1月考核：框架合同按验收额计（6万），非按 total_amt(100万) ===')
with test_app.app_context():
    resp = client.get(f'/api/appraisal/monthly?year={today_y}&month=1', headers=hdr())
    rows = {r['username']: r for r in resp.get_json()['data']['rows']}
    a_actual = rows['sales_a']['cumulative_actual_amt']
    b_actual = rows['sales_b']['cumulative_actual_amt']
    # sales_a: 框架合同1月验收6万 → actual=6万
    # sales_b: 普通合同 total=20万，sign_date=1月 → actual=20万
    print(f'  sales_a: actual={a_actual} (期望 60000)')
    print(f'  sales_b: actual={b_actual} (期望 200000)')
    assert abs(a_actual - 60000) < 0.5, f'框架合同1月 actual={a_actual} 期望60000（验收额），不是100万'
    assert abs(b_actual - 200000) < 0.5, f'普通合同 actual={b_actual} 期望200000'
    print(f'  ✓ 框架合同按验收额6万计入，非按total_amt100万')

print('\n=== 3. 2月考核：框架合同累计验收=14万（6万+8万） ===')
with test_app.app_context():
    resp = client.get(f'/api/appraisal/monthly?year={today_y}&month=2', headers=hdr())
    rows = {r['username']: r for r in resp.get_json()['data']['rows']}
    a_actual = rows['sales_a']['cumulative_actual_amt']
    print(f'  sales_a: actual={a_actual} (期望 140000)')
    assert abs(a_actual - 140000) < 0.5, f'框架合同2月累计 actual={a_actual} 期望140000'
    print(f'  ✓ 2月累计验收=14万（1月6万+2月8万）')

print('\n=== 4. 框架合同 + 分成组合（sales_a 60%, sales_b 40%）===')
with test_app.app_context():
    # 设置分成
    resp = client.post(f'/api/contracts/{fw_contract_id}/commissions', headers=hdr(),
                       json={'commissions': [{'username':'sales_a','ratio':60},{'username':'sales_b','ratio':40}]})
    assert resp.get_json()['code'] == 200
    # 1月考核：验收6万 × 60% = 3.6万（sales_a），× 40% = 2.4万（sales_b）
    resp = client.get(f'/api/appraisal/monthly?year={today_y}&month=1', headers=hdr())
    rows = {r['username']: r for r in resp.get_json()['data']['rows']}
    a_actual = rows['sales_a']['cumulative_actual_amt']
    b_from_fw = rows['sales_b']['cumulative_actual_amt']
    # sales_b 还有一个普通合同20万，所以 total = 20万 + 2.4万 = 22.4万
    print(f'  sales_a: actual={a_actual} (期望 36000 = 60000×60%)')
    print(f'  sales_b: actual={b_from_fw} (期望 224000 = 200000 + 60000×40%)')
    assert abs(a_actual - 36000) < 0.5, f'sales_a actual={a_actual} 期望36000'
    assert abs(b_from_fw - 224000) < 0.5, f'sales_b actual={b_from_fw} 期望224000'
    print(f'  ✓ 框架合同验收额 × 分成比例 正确')

print('\n=== 5. 删除验收记录后考核回退 ===')
with test_app.app_context():
    # 查验收记录id
    resp = client.get(f'/api/contracts/{fw_contract_id}/acceptances', headers=hdr())
    accs = resp.get_json()['data']['acceptances']
    # 删除2月的验收（8万那条）
    acc2 = [a for a in accs if '2月' in (a.get('note') or '')][0]
    resp = client.delete(f'/api/contracts/acceptances/{acc2["id"]}', headers=hdr())
    assert resp.get_json()['code'] == 200
    # 2月考核：框架合同只剩1月6万验收 → 2月累计=6万
    resp = client.get(f'/api/appraisal/monthly?year={today_y}&month=2', headers=hdr())
    rows = {r['username']: r for r in resp.get_json()['data']['rows']}
    a_actual = rows['sales_a']['cumulative_actual_amt']
    print(f'  sales_a 2月: actual={a_actual} (期望 36000 = 60000×60%)')
    assert abs(a_actual - 36000) < 0.5, f'删除2月验收后 actual={a_actual} 期望36000'
    print(f'  ✓ 删除验收记录后考核回退正确')

conn.close()
shutil.rmtree(tmp, ignore_errors=True)
print('\n✅ 框架合同验收功能所有测试通过')
