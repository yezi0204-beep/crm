"""合同销售分成功能验证：
1. POST /contracts/<id>/commissions 保存分成（2人 60/40），GET 回读一致
2. 比例之和≠100 → 400 拒绝
3. 有分成后，月度考核按比例计算实际额（sales_a 8万×60%=4.8万, sales_b 20万×40%=8万）
4. 清除分成后，恢复 owner 独享 100%
"""
import sys, os, sqlite3, tempfile, shutil
from datetime import datetime

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
sys.path.insert(0, BACKEND_DIR)

tmp = tempfile.mkdtemp()
tmp_db = os.path.join(tmp, 'test_commission.db')
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
    # 最小 contracts 表
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_no TEXT, contract_name TEXT, party_a TEXT,
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
    # 2个销售 + 1个主任
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
    # 合同：owner=sales_a，金额=10万，1月
    today_y = datetime.now().year
    ym = f'{today_y:04d}-01-15'
    cur.execute("""INSERT INTO contracts (contract_no, contract_name, total_amt, sign_date, owner_id, status,
                                          classification, is_audit, pending_acceptance_amount, pending_amt,
                                          paid_amt, party_a)
                   VALUES ('C-001', '分成测试合同', 100000, ?, 'sales_a', '执行中',
                           '分类A', '是', 0, 100000, 0, '甲方')""", (ym,))
    contract_id = cur.lastrowid
    conn.commit()

client = test_app.test_client()

def hdr(user='dir_c', role='主任'):
    tk = create_token(user, user, role)
    return {'Authorization': f'Bearer {tk}'}

print('=== 1. 保存分成（sales_a 60%, sales_b 40%）===')
with test_app.app_context():
    resp = client.post(f'/api/contracts/{contract_id}/commissions',
                       headers=hdr('dir_c','主任'),
                       json={'commissions': [{'username':'sales_a','ratio':60},{'username':'sales_b','ratio':40}]})
    print(f'  POST HTTP {resp.status_code}: {resp.get_json().get("message")}')
    assert resp.status_code == 200 and resp.get_json()['code'] == 200, f'保存失败: {resp.get_json()}'
    # GET 回读
    resp2 = client.get(f'/api/contracts/{contract_id}/commissions', headers=hdr('dir_c','主任'))
    data = resp2.get_json()['data']
    cms = {c['username']: c['ratio'] for c in data['commissions']}
    assert cms.get('sales_a') == 60 and cms.get('sales_b') == 40, f'回读不一致: {cms}'
    print(f'  ✓ GET 回读一致: sales_a=60%, sales_b=40%')

print('\n=== 2. 比例之和≠100 → 400 ===')
with test_app.app_context():
    resp = client.post(f'/api/contracts/{contract_id}/commissions',
                       headers=hdr('dir_c','主任'),
                       json={'commissions': [{'username':'sales_a','ratio':50},{'username':'sales_b','ratio':30}]})
    body = resp.get_json()
    assert body['code'] == 400, f'应拒绝但 code={body["code"]}'
    print(f'  ✓ 80% 被拒绝: {body["message"]}')

print('\n=== 3. 有分成后考核按比例计算 ===')
with test_app.app_context():
    resp = client.get(f'/api/appraisal/monthly?year={today_y}&month=1', headers=hdr('dir_c','主任'))
    data = resp.get_json()['data']
    rows = {r['username']: r for r in data['rows']}
    # sales_a: 合同10万 × 60% = 6万, target=10万/12×1=10万 → rate=60%
    # sales_b: 合同10万 × 40% = 4万, target=10万 → rate=40%
    a_actual = rows['sales_a']['cumulative_actual_amt']
    b_actual = rows['sales_b']['cumulative_actual_amt']
    a_rate = rows['sales_a']['rate_pct']
    b_rate = rows['sales_b']['rate_pct']
    print(f'  sales_a: actual={a_actual}, rate={a_rate}% (期望 60000, 60%)')
    print(f'  sales_b: actual={b_actual}, rate={b_rate}% (期望 40000, 40%)')
    assert abs(a_actual - 60000) < 0.5, f'sales_a actual={a_actual} 期望60000'
    assert abs(b_actual - 40000) < 0.5, f'sales_b actual={b_actual} 期望40000'
    assert abs(a_rate - 60.0) < 0.1, f'sales_a rate={a_rate} 期望60'
    assert abs(b_rate - 40.0) < 0.1, f'sales_b rate={b_rate} 期望40'
    print(f'  ✓ 分成后考核按比例计算正确')

print('\n=== 4. 清除分成 → 恢复 owner 独享 ===')
with test_app.app_context():
    resp = client.post(f'/api/contracts/{contract_id}/commissions',
                       headers=hdr('dir_c','主任'),
                       json={'commissions': []})
    assert resp.get_json()['code'] == 200
    # 考核恢复
    resp = client.get(f'/api/appraisal/monthly?year={today_y}&month=1', headers=hdr('dir_c','主任'))
    rows = {r['username']: r for r in resp.get_json()['data']['rows']}
    a_actual = rows['sales_a']['cumulative_actual_amt']
    b_actual = rows['sales_b']['cumulative_actual_amt']
    print(f'  sales_a: actual={a_actual} (期望 100000)')
    print(f'  sales_b: actual={b_actual} (期望 0)')
    assert abs(a_actual - 100000) < 0.5, f'清除分成后 sales_a actual={a_actual} 期望100000'
    assert abs(b_actual - 0) < 0.5, f'清除分成后 sales_b actual={b_actual} 期望0'
    print(f'  ✓ 清除分成后 owner 独享 100%')

conn.close()
shutil.rmtree(tmp, ignore_errors=True)
print('\n✅ 合同分成功能所有测试通过')
