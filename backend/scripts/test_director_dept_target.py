"""验证「主任承担部门3000万指标，主任的月度分解就是部门月度指标任务」。
场景：
  - 主任 dir_x: role='主任', is_sales_override=1, annual=3000万 → 部门主任
  - 销售 sales_a: annual=960万(月度80万), 2月合同 64万 → 完成率80%
  - 销售 sales_b: annual=960万(月度80万), 2月合同 160万 → 完成率200%→封顶150%
期望（year=2026, month=2, 累计实际从2月开始算）：
  - 主任月度指标 = 3000万/12 = 250万（即为部门月度指标任务）
  - 主任累计实际 = sales_a(64万) + sales_b(160万) = 224万
  - 主任完成率 = 224万/250万 * 100 = 89.6%
  - 主任不参与销售均值
  - 销售均值 = (sales_a 80% + sales_b 150%封顶)/2 = 115%
  - 非销售按销售均值 115% 计算绩效
"""
import sys, os, sqlite3, tempfile, shutil, urllib.parse
from datetime import datetime

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
sys.path.insert(0, BACKEND_DIR)

# 准备临时数据库
tmp = tempfile.mkdtemp()
tmp_db = os.path.join(tmp, 'test_director.db')
os.environ['DB_PATH'] = tmp_db
os.environ['SECRET_KEY'] = 'test_secret'
os.environ['UPLOAD_DIR'] = os.path.join(tmp, 'uploads')
os.makedirs(os.environ['UPLOAD_DIR'], exist_ok=True)

# 清缓存
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

    # 预置 contracts 表最小结构
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

    # 用户：主任(3000万) + 2销售(各960万，月度80万) + 1非销售
    users = [
        ('dir_x',   '主任X', '主任', '应用中心', 30000000, 15000, 5000, 1),  # 部门主任，3000万指标
        ('sales_a', '销售A', '销售', '应用中心',  9600000, 10000, 5000, 0),  # 月度80万
        ('sales_b', '销售B', '销售', '应用中心',  9600000, 10000, 5000, 0),  # 月度80万
        ('eng_e',   '售前E', '售前', '应用中心',        0,  8000, 1500, 0),  # 非销售
    ]
    pw = hash_password('123456')
    for u, name, role, dept, annual, basic, perf, override in users:
        cur.execute("INSERT INTO users (username, password_hash, name, role, department, status,"
                    " basic_salary, base_performance, annual_target_amount, is_sales_override)"
                    " VALUES (?, ?, ?, ?, ?, '在职', ?, ?, ?, ?)",
                    (u, pw, name, role, dept, basic, perf, annual, override))

    # 2月合同：A 64万（完成率80%），B 160万（完成率200%→封顶150%）
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

print('=== 主任承担部门3000万指标 验证 ===')
with test_app.app_context():
    resp = client.get(f'/api/appraisal/monthly?year={today_y}&month=2', headers=hdr('dir_x', '主任'))
    data = resp.get_json()
    assert resp.status_code == 200 and data.get('code') == 200, f'失败：{data}'
    rows = data.get('data', {}).get('rows', [])
    m = {r['username']: r for r in rows}
    avg = data.get('data', {}).get('avg_sales_rate_pct')

    # 1. 主任月度指标 = 3000万/12 = 250万（部门月度指标任务）
    dir_row = m['dir_x']
    assert dir_row['is_director'] == True, f'主任应识别为部门主任：{dir_row}'
    assert round(dir_row['monthly_target_amt'], 2) == 2500000.00, (
        f'主任月度指标错误：{dir_row["monthly_target_amt"]}，期望 250万')
    assert round(dir_row['cumulative_target_amt'], 2) == 2500000.00, (
        f'主任累计目标错误：{dir_row["cumulative_target_amt"]}，期望 250万')
    print(f'  ✓ 主任月度指标 = 250万（3000万/12，部门月度指标任务）')

    # 2. 主任累计实际 = sales_a(64万) + sales_b(160万) = 224万
    assert round(dir_row['cumulative_actual_amt'], 2) == 2240000.00, (
        f'主任累计实际错误：{dir_row["cumulative_actual_amt"]}，期望 224万')
    print(f'  ✓ 主任累计实际 = 224万（部门所有销售累计实际之和：A 64万 + B 160万）')

    # 3. 主任完成率 = 224万/250万*100 = 89.6%
    assert round(dir_row['rate_pct'], 2) == 89.60, (
        f'主任完成率错误：{dir_row["rate_pct"]}，期望 89.6%')
    print(f'  ✓ 主任完成率 = 89.6%（224万/250万，未封顶150%）')

    # 4. 主任不参与销售均值
    # sales_a: 64万/80万 = 80%; sales_b: 160万/80万 = 200% → 封顶150%
    # 均值 = (80 + 150) / 2 = 115%（不含主任）
    assert round(avg, 2) == 115.00, f'销售均值错误：{avg}，期望 115%'
    print(f'  ✓ 销售均值 = 115%（不含主任，A 80% + B 150%封顶）/2')

    # 5. 非销售按销售均值
    eng_row = m['eng_e']
    assert round(eng_row['rate_pct'], 2) == 115.00, f'非销售完成率错误：{eng_row["rate_pct"]}'
    assert round(eng_row['perf_pay'], 2) == 1725.00, f'非销售绩效错误：{eng_row["perf_pay"]}'
    print(f'  ✓ 非销售(售前E) 完成率 = 115%（销售均值），绩效 = 1500*115% = 1725')

    # 6. 主任绩效 = 基础绩效 * 主任完成率 / 100 = 5000 * 89.6% = 4480
    assert round(dir_row['perf_pay'], 2) == 4480.00, (
        f'主任绩效错误：{dir_row["perf_pay"]}，期望 4480')
    assert round(dir_row['total_pay'], 2) == 19480.00, (
        f'主任应发合计错误：{dir_row["total_pay"]}，期望 19480')
    print(f'  ✓ 主任绩效 = 5000*89.6% = 4480，应发合计 = 15000+4480 = 19480')

    # 7. 各销售个人完成率
    assert round(m['sales_a']['rate_pct'], 2) == 80.00
    assert round(m['sales_b']['rate_pct'], 2) == 150.00  # 封顶
    print(f'  ✓ 销售A 80%（64万/80万），销售B 150%封顶（160万/80万=200%→封顶150%）')

conn.close()
shutil.rmtree(tmp, ignore_errors=True)
print('\n✅ 主任承担部门3000万指标 场景验证通过')
