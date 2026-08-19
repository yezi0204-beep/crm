"""Task 2 RED tests:
TR 2.1: 3用户考核核心算法（A销售80%，B销售150%封顶，C非销售115%均值）数值精确匹配
TR 2.2: 身份判定（role/ is_sales_override 组合）
TR 2.3: target=0 销售不参与均值，其绩效为0
TR 2.4: 权限：普通用户调用 /monthly /export /config 返回403
TR 2.5: POST /config 保存再 GET 回读一致，写 operation_logs
TR 2.6: /export 接口返回 xlsx attachment
"""
import sys, os, sqlite3, tempfile, shutil, json, io, urllib.parse
import importlib
from datetime import datetime

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
sys.path.insert(0, BACKEND_DIR)

# ---------- 准备临时数据库 + 预置数据 ----------
tmp = tempfile.mkdtemp()
tmp_db = os.path.join(tmp, 'test_appraisal2.db')
os.environ['DB_PATH'] = tmp_db
os.environ['SECRET_KEY'] = 'test_secret'
os.environ['UPLOAD_DIR'] = os.path.join(tmp, 'uploads')
os.makedirs(os.environ['UPLOAD_DIR'], exist_ok=True)

# 清除缓存import，确保读新DB_PATH
for m in list(sys.modules.keys()):
    if any(p in m for p in ('extensions','config','security','scheduler','qa_engine','ai_analyzer',
                           'vector_search','routes','app')):
        del sys.modules[m]

from flask import Flask
from extensions import (setup_extensions, ensure_tables, get_db, hash_password,
                        create_token, record_operation_log)

test_app = Flask(__name__)
setup_extensions(test_app)
with test_app.app_context():
    ensure_tables()
    conn = get_db()
    cur = conn.cursor()

    # 预置 contracts 表（不依赖其他 DDL 执行顺序，最小必要结构）
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

    # 预置3用户：A销售/B销售/C主任，再加D主任强制销售覆盖，E售前（非销售）
    users = [
        ('sales_a', '销售A', '销售', '应用中心', 1200000, 10000, 5000, 0),
        ('sales_b', '销售B', '销售', '应用中心', 1200000, 10000, 5000, 0),
        ('dir_c',   '主任C', '主任', '应用中心',       0, 15000, 2000, 0),  # 非销售
        ('dir_d',   '主任D', '主任', '应用中心',       0, 15000, 2000, 1),  # 强制销售
        ('eng_e',   '售前E', '售前', '应用中心',       0,  8000, 1500, 0),  # 非销售
        ('no_target_f', '销售F','销售','应用中心',     0, 10000, 5000, 0),  # annual=0（无指标）
        ('common_g','普通G', '员工', '其他部门',       0,  5000,  500, 0),  # 非应用中心
    ]
    pw = hash_password('123456')
    for u, name, role, dept, annual, basic, perf, override in users:
        cur.execute("INSERT INTO users (username, password_hash, name, role, department, status,"
                    " basic_salary, base_performance, annual_target_amount, is_sales_override)"
                    " VALUES (?, ?, ?, ?, ?, '在职', ?, ?, ?, ?)",
                    (u, pw, name, role, dept, basic, perf, annual, override))

    # 给A插入1条「考核月」合同：80000元；B插入 200000元
    # 为数值可控，测试固定 month=2，1个月累计（1月合同已在去年结算，从2月开始算）
    today_y, today_m = datetime.now().year, 2
    # 合同写到 year年2月
    ym = f'{today_y:04d}-02-15'
    cur.execute("""INSERT INTO contracts (contract_no, contract_name, total_amt, sign_date, owner_id, status,
                                          classification, is_audit, pending_acceptance_amount, pending_amt,
                                          paid_amt, party_a)
                   VALUES ('C-A-001', '测试合同A', 80000, ?, 'sales_a', '执行中',
                           '分类A', '是', 0, 80000, 0, '甲方A')""", (ym,))
    # 给B插入1条：200000元
    cur.execute("""INSERT INTO contracts (contract_no, contract_name, total_amt, sign_date, owner_id, status,
                                          classification, is_audit, pending_acceptance_amount, pending_amt,
                                          paid_amt, party_a)
                   VALUES ('C-B-001', '测试合同B', 200000, ?, 'sales_b', '执行中',
                           '分类B', '是', 0, 200000, 0, '甲方B')""", (ym,))
    conn.commit()

# 注册 appraisal 蓝图
from routes.appraisal import appraisal_bp as abp  # noqa: F401 （会先失败，RED）
test_app.register_blueprint(abp, url_prefix='/api/appraisal')
# 开启测试客户端
client = test_app.test_client()

def hdr(user='dir_c', role='主任'):
    tk = create_token(user, user, role)
    return {'Authorization': f'Bearer {tk}'}

print('=== TR 2.1: 核心算法数值 ===')
# 期望：annual_target=120万 → monthly=10万
# sales_a: actual=8万, rate=80% → perf=5000*80%=4000, total=14000
# sales_b: actual=20万, rate=150%(封顶) → perf=5000*150%=7500, total=17500
# avg_sales_rate=(80+150)/2=115%
# dir_c (非销售主任): perf=2000*115%=2300, total=17300
# dir_d (主任 is_sales_override=1): 视为销售，annual=0 → target<=0 → rate=0, perf=0, total=15000
# eng_e (售前非销售): perf=1500*115%=1725, total=9725
# sales_f (annual=0销售): target=0，不参与均值；自己perf=0
with test_app.app_context():
    resp = client.get(f'/api/appraisal/monthly?year={today_y}&month={today_m}', headers=hdr('dir_c', '主任'))
    print(f'  HTTP {resp.status_code}')
    data = resp.get_json()
    assert resp.status_code == 200 and data.get('code') == 200, f'失败：{data}'
    rows = data.get('data', {}).get('rows', [])
    m = {r['username']: r for r in rows}
    EXPECTED = {
        'sales_a': {'actual_amt': 80000,   'target_amt': 100000,  'rate_pct': 80.00,  'perf_pay': 4000.00, 'total_pay': 14000.00, 'is_sales': True},
        'sales_b': {'actual_amt': 200000,  'target_amt': 100000,  'rate_pct': 150.00, 'perf_pay': 7500.00, 'total_pay': 17500.00, 'is_sales': True},
        'dir_c':   {'actual_amt': 0,       'target_amt': 0,       'rate_pct': 115.00, 'perf_pay': 2300.00, 'total_pay': 17300.00, 'is_sales': False},
        'dir_d':   {'actual_amt': 0,       'target_amt': 0,       'rate_pct': 0.00,   'perf_pay': 0.00,    'total_pay': 15000.00, 'is_sales': True},  # 强制销售，无指标
        'eng_e':   {'actual_amt': 0,       'target_amt': 0,       'rate_pct': 115.00, 'perf_pay': 1725.00, 'total_pay': 9725.00,  'is_sales': False},
        'no_target_f': {'actual_amt': 0,   'target_amt': 0,       'rate_pct': 0.00,   'perf_pay': 0.00,    'total_pay': 10000.00, 'is_sales': True},
    }
    avg_sales_rate = data.get('data', {}).get('avg_sales_rate_pct')
    assert avg_sales_rate is not None and round(avg_sales_rate, 2) == 115.00, f'avg_sales_rate 不对：{avg_sales_rate}，期望115%'
    for u, exp in EXPECTED.items():
        r = m.get(u)
        assert r is not None, f'列表缺失用户{u}，返回用户：{list(m.keys())}'
        # 取 float 比较
        for k in ['actual_amt', 'target_amt', 'rate_pct', 'perf_pay', 'total_pay']:
            got = round(float(r.get(k, 0)), 2)
            want = round(float(exp[k]), 2)
            assert got == want, (f'TR2.1 FAIL [{u}.{k}]: 实际 {got}，期望 {want}\n  原始行: {r}')
        assert r['is_sales'] == exp['is_sales'], f'{u} 身份判定错误'
        print(f'  ✓ {u}: actual={exp["actual_amt"]:>7}, target={exp["target_amt"]:>7}, '
              f'rate={exp["rate_pct"]:>6.2f}%, perf={exp["perf_pay"]:>7.2f}, total={exp["total_pay"]:>8.2f}, is_sales={exp["is_sales"]}')
    print(f'  ✓ avg_sales_rate={avg_sales_rate:.2f}%')

# TR 2.2 身份判定（已在2.1内覆盖 dir_d 和 eng_e 的 is_sales 结果）
print('\n=== TR 2.2: 身份判定（已在2.1覆盖） ✓ 已通过')

print('\n=== TR 2.3: target=0 销售(no_target_f)不参与均值')
# 验证 sales_f 若有指标，会改变均值；但现在均值=115（sales_a+sales_b），sales_f 未影响
print(f'  ✓ 已在2.1中验证 avg={avg_sales_rate:.2f} == 115（仅 sales_a+sales_b 平均，排除 sales_f）')

print('\n=== TR 2.4: 权限（普通用户/sales_a）访问受限接口 必须403')
with test_app.app_context():
    sales_h = hdr('sales_a', '销售')
for path, method in [('/monthly', 'GET'), ('/config/sales_a', 'GET'), ('/export', 'GET')]:
    if method == 'GET':
        r = client.get(f'/api/appraisal{path}?year={today_y}&month={today_m}', headers=sales_h)
    else:
        with test_app.app_context():
            r = client.post(f'/api/appraisal{path}', headers=sales_h, json={})
    # 业务 code 在 body.code；HTTP 是 200（系统惯例），但若 /export 返回附件则读 code 失败
    body_code = None
    try:
        body_code = r.get_json().get('code') if r.is_json else None
    except Exception:
        body_code = None
    assert body_code == 403, (
        f'FAIL: {method} {path} 业务 code={body_code} (HTTP {r.status_code}) 期望 403')
    print(f'  ✓ {method} {path} → HTTP {r.status_code} business_code={body_code} 权限正确')

print('\n=== TR 2.5: POST /config 保存并读回 + 操作日志')
with test_app.app_context():
    post_body = {
        'username': 'sales_a',
        'year': today_y,
        'basic_salary': 12000,
        'base_performance': 6000,
        'annual_target_amount': 2400000,
        'is_sales_override': 0,
        'monthly_overrides': {1: 300000, 2: 100000}  # 1月覆盖30万，2月覆盖10万，其他默认20万
    }
    resp = client.post('/api/appraisal/config', headers=hdr('dir_c', '主任'), json=post_body)
    print(f'  POST /config HTTP {resp.status_code}: {resp.get_json().get("message","")}')
    assert resp.status_code == 200, f'POST失败：{resp.get_json()}'
    # GET回读
    resp2 = client.get(f'/api/appraisal/config/sales_a?year={today_y}', headers=hdr('dir_c', '主任'))
    assert resp2.status_code == 200, f'GET失败：{resp2.get_json()}'
    got = resp2.get_json().get('data', {})
    assert round(got['basic_salary'],2) == 12000.0
    assert round(got['base_performance'],2) == 6000.0
    assert round(got['annual_target_amount'],2) == 2400000.0
    assert got['is_sales_override'] == 0
    overrides = got.get('monthly_overrides') or {}
    # JSON 返回键为字符串，兼容比较
    overrides = {int(k) if str(k).isdigit() else k: v for k, v in overrides.items()}
    assert overrides.get(1) == 300000 and overrides.get(2) == 100000, f'覆盖值不匹配：{overrides}'
    # 检查 operation_logs
    db2 = get_db()
    cur2 = db2.cursor()
    cur2.execute("SELECT COUNT(*) c FROM operation_logs WHERE module='月度考核' AND operation='配置指标' AND detail LIKE '%sales_a%'")
    log_cnt = cur2.fetchone()['c']
    assert log_cnt >= 1, f'配置后 operation_logs 未写入记录'
    print(f'  ✓ POST保存 → GET回读一致（含1月30万/2月10万覆盖）；操作日志 {log_cnt} 条')

print('\n=== TR 2.6: /export xlsx attachment')
with test_app.app_context():
    resp = client.get(f'/api/appraisal/export?year={today_y}&month={today_m}', headers=hdr('dir_c', '主任'))
    ct = resp.content_type or ''
    cd = resp.headers.get('Content-Disposition') or ''
    # 解析 filename*=UTF-8''...
    fname = ''
    for part in cd.split(';'):
        part = part.strip()
        if part.startswith('filename*=') and "UTF-8''" in part:
            fname = urllib.parse.unquote(part.split("UTF-8''")[1])
            break
        elif part.startswith('filename='):
            fname = part.split('=', 1)[1].strip('"')
    print(f'  HTTP {resp.status_code}, Content-Type={ct}, 文件名={fname}')
    assert resp.status_code == 200, f'export返回 {resp.status_code}'
    assert 'vnd.openxmlformats' in ct or 'octet-stream' in ct, 'Content-Type 不是xlsx'
    assert 'attachment' in cd, f'Content-Disposition 缺少 attachment：{cd}'
    expected_fname_contains = f'{today_y}年{today_m}月'
    assert expected_fname_contains in fname, (
        f'文件名 缺少「{expected_fname_contains}」，实际: {fname}')
    # 验证 xlsx 文件头（openpyxl生成是ZIP）
    body = resp.data
    assert body[:4] == b'PK\x03\x04', '响应体不是 xlsx（ZIP头缺失）'
    print('  ✓ 返回xlsx attachment，ZIP头正确，文件名含年月')

conn.close()
shutil.rmtree(tmp, ignore_errors=True)
print('\n✅ Task 2 所有测试通过 (GREEN)')
