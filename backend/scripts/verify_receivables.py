# -*- coding: utf-8 -*-
"""两金明细表端到端验证：登录 → 快照 → 列表 → 填报 → 口径 → 导出 → 导入比对/应用。"""
import sys
import io
import os
import json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import requests
import pymysql
import bcrypt
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

# 加载 .env 获取 MySQL 连接参数
for _line in (_BACKEND.parent / '.env').read_text(encoding='utf-8').splitlines():
    if '=' in _line and not _line.strip().startswith('#'):
        _k, _v = _line.split('=', 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from db import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE  # noqa: E402

BASE = 'http://127.0.0.1:5000'
TEST_USER = 'recv_verify_tmp'
TEST_PWD = 'Rv123456!'

# ---- 创建临时测试账号（财务角色，可手动快照/导入）----
conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER,
                       password=MYSQL_PASSWORD, database=MYSQL_DATABASE,
                       charset='utf8mb4', autocommit=False)
cur = conn.cursor()
pw_hash = bcrypt.hashpw(TEST_PWD.encode(), bcrypt.gensalt()).decode('utf-8')
cur.execute("DELETE FROM users WHERE username=%s", (TEST_USER,))
cur.execute(
    "INSERT INTO users (username, password_hash, name, role, department, status) VALUES (%s,%s,%s,%s,%s,%s)",
    (TEST_USER, pw_hash, '两金验证', '财务', '财务部', '在职'))
conn.commit()

_backups = {}  # {cid: row}

def _backup_override(quarter, cid):
    cur.execute(
        "SELECT customer_nature, cust_risk, payback_risk, payback_plan, updated_by, updated_at "
        "FROM receivable_overrides WHERE quarter=%s AND contract_id=%s", (quarter, cid))
    _backups[cid] = cur.fetchone()

def _restore_overrides():
    for cid, b in _backups.items():
        if b:
            cur.execute(
                "UPDATE receivable_overrides SET customer_nature=%s, cust_risk=%s, payback_risk=%s, "
                "payback_plan=%s, updated_by=%s, updated_at=%s WHERE quarter=%s AND contract_id=%s",
                (b[0], b[1], b[2], b[3], b[4], b[5], _QUARTER, cid))
        else:
            cur.execute("DELETE FROM receivable_overrides WHERE quarter=%s AND contract_id=%s",
                        (_QUARTER, cid))
    if _backups:
        conn.commit()
        print('== 已还原测试填报数据')

s = requests.Session()
login = s.post(f'{BASE}/api/auth/login', json={'username': TEST_USER, 'password': TEST_PWD}, timeout=10)
token = (login.json().get('data') or {}).get('token')
assert token, f'登录失败: {login.text}'
H = {'Authorization': f'Bearer {token}'}
print('[1] 登录成功')

# ---- 2. 触发快照 ----
snap = s.post(f'{BASE}/api/receivables/snapshot', json={}, headers=H, timeout=30)
print('[2] 快照:', snap.status_code, snap.text[:200])
assert snap.json().get('code') == 200, snap.text
snap_data = snap.json()['data']
print(f'    季度: {snap_data["quarter"]}, 写入 {snap_data["count"]} 条')

# ---- 3. 查询列表（未填报客户性质应为空串）----
lst = s.get(f'{BASE}/api/receivables', headers=H, timeout=10).json()
assert lst['code'] == 200, lst
data = lst['data']
_QUARTER = data['quarter']
print(f'[3] 列表: quarter={data["quarter"]}, items={len(data["items"])}, summary={data["summary"]}')
assert 'by_nature' not in data, 'by_nature 应已移除'
_unfilled = [i for i in data['items'] if not i.get('customer_nature')]
print(f'    未填报客户性质的行数: {len(_unfilled)}（前端展示为「未填报」）')

# ---- 4. 人工填报（覆盖：客户性质/客户风险/回款风险/回款计划） ----
_test_cid = None
if data['items']:
    first = data['items'][0]
    cid = first['contract_id']
    _test_cid = cid
    _backup_override(data['quarter'], cid)
    print(f'    填报前 customer_nature={first.get("customer_nature")!r}, customer_name={first.get("customer_name")!r}')
    ov = s.put(f'{BASE}/api/receivables/override/{cid}', headers=H, json={
        'quarter': data['quarter'],
        'customer_nature': '集团内',
        'cust_risk': '中',
        'payback_risk': '高',
        'payback_plan': [
            {'node': '尾款', 'amt': 50000.00, 'date': '2026-11-15'},
            {'node': '质保金', 'amt': 20000.00, 'date': '2027-06-30'},
        ],
    }, timeout=10)
    print(f'[4] 覆盖保存: {ov.json()}')
    assert ov.json()['code'] == 200

    # 再查一次验证回填
    lst2 = s.get(f'{BASE}/api/receivables', headers=H, params={'quarter': data['quarter']}, timeout=10).json()
    match = [i for i in lst2['data']['items'] if i['contract_id'] == cid][0]
    print(f'    回填验证: nature={match.get("customer_nature")}, cust_risk={match.get("cust_risk")}, '
          f'payback_risk={match.get("payback_risk")}')
    assert match.get('customer_nature') == '集团内'
    assert match.get('cust_risk') == '中'
    assert match.get('payback_risk') == '高'

    # 单独改回款计划，不应清空已填的客户性质/风险（字段级隔离）
    ov2 = s.put(f'{BASE}/api/receivables/override/{cid}', headers=H, json={
        'quarter': data['quarter'],
        'payback_plan': [{'node': '一次性结清', 'amt': 1000.00, 'date': '2026-12-31'}],
    }, timeout=10)
    assert ov2.json()['code'] == 200
    lst3 = s.get(f'{BASE}/api/receivables', headers=H, params={'quarter': data['quarter']}, timeout=10).json()
    m3 = [i for i in lst3['data']['items'] if i['contract_id'] == cid][0]
    print(f'    单项更新后: nature={m3.get("customer_nature")}, cust_risk={m3.get("cust_risk")}, '
          f'payback_risk={m3.get("payback_risk")}（应保持不变）')
    assert m3.get('customer_nature') == '集团内' and m3.get('cust_risk') == '中'

# ---- 5. 金额口径校验：应收账款=含税收入-回款，合同资产=合同额-含税收入 ----
cur.execute("""
    SELECT c.id, c.total_amt, c.party_a,
           COALESCE((SELECT SUM(acceptance_amount) FROM contract_acceptances WHERE contract_id=c.id), 0) AS acc,
           COALESCE((SELECT SUM(tax_amount) FROM contract_acceptances WHERE contract_id=c.id), 0) AS tax,
           COALESCE((SELECT SUM(amount) FROM payment_records WHERE contract_id=c.id), 0) AS paid
    FROM contracts c WHERE c.status<>'作废'
      AND (EXISTS(SELECT 1 FROM contract_acceptances WHERE contract_id=c.id)
           OR EXISTS(SELECT 1 FROM payment_records WHERE contract_id=c.id))
    ORDER BY c.id LIMIT 5
""")
rows = cur.fetchall()
by_id = {i['contract_id']: i for i in data['items']}
print('[5] 口径校验（前5份合同）:')
for r in rows:
    cid, total, party, acc, tax, paid = r
    it = by_id.get(cid)
    if not it:
        print(f'    合同{cid} 不在快照中（异常）')
        continue
    exp_recv = round(float(acc) + float(tax) - float(paid), 2)
    exp_asset = round(float(total) - (float(acc) + float(tax)), 2)
    ok = abs(float(it['receivable']) - exp_recv) < 0.01 and abs(float(it['contract_asset']) - exp_asset) < 0.01
    print(f'    合同{cid} 应收={it["receivable"]} (期望{exp_recv}) 合同资产={it["contract_asset"]} '
          f'(期望{exp_asset}) 往来单位={it["customer_name"]!r} -> {"OK" if ok else "不一致"}')
    assert ok, f'合同{cid} 口径不一致'
    assert it['customer_name'] == (party or ''), f'合同{cid} 往来单位与合同管理不一致'

# ---- 6. 导出 ----
exp = s.get(f'{BASE}/api/receivables/export', headers=H, params={'quarter': data['quarter']}, timeout=30)
print(f'[6] 导出: status={exp.status_code}, content-type={exp.headers.get("Content-Type")}, size={len(exp.content)} bytes')
assert exp.status_code == 200 and len(exp.content) > 1000

# ---- 7. 导入比对（fill 路径）：构造 xlsx → preview → apply → 校验 ----
from openpyxl import Workbook as XWb

# 选一个未填报的合同作为导入目标
_test_cid2 = None
cur.execute("SELECT contract_id FROM receivable_overrides WHERE quarter=%s", (data['quarter'],))
_filled_ids = {r[0] for r in cur.fetchall()}
_target = next((i for i in data['items']
                if i['contract_id'] not in _filled_ids and i['contract_id'] != _test_cid), None)
if _target:
    _test_cid2 = _target['contract_id']
    _backup_override(data['quarter'], _test_cid2)

    wb = XWb()
    ws = wb.active
    ws.append(['往来单位', '子集团内/集团内/集团外', '项目名称', '客户风险(高/中/低)', '回款风险(高/中/低)', '更新回款计划（节点+金额+日期）'])
    ws.append([_target['customer_name'], '子集团内', _target['project_name'], '低', '高', '尾款 30000元 2026-12-20'])
    ws.append(['不存在公司', '集团内', '不存在的项目XYZ', '低', '低', ''])  # 未匹配行
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    pv = s.post(f'{BASE}/api/receivables/import/preview', headers=H,
                files={'file': ('import_test.xlsx', buf, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},
                data={'quarter': data['quarter']}, timeout=30)
    pvd = pv.json()
    print(f'[7] 导入预览: code={pvd["code"]}, 匹配={len(pvd["data"]["rows"])}, 未匹配={len(pvd["data"]["unmatched"])}')
    assert pvd['code'] == 200
    assert len(pvd['data']['unmatched']) == 1, pvd['data']['unmatched']
    assert pvd['data']['unmatched'][0]['project_name'] == '不存在的项目XYZ'
    trow = next(r for r in pvd['data']['rows'] if r['contract_id'] == _test_cid2)
    fdict = {f['key']: f for f in trow['fields']}
    print(f'    动作: ' + ', '.join(f"{k}={v['action']}" for k, v in fdict.items()))
    assert fdict['customer_nature']['action'] == 'fill' and fdict['customer_nature']['imported'] == '子集团内'
    assert fdict['cust_risk']['action'] == 'fill' and fdict['cust_risk']['imported'] == '低'
    assert fdict['payback_risk']['action'] == 'fill' and fdict['payback_risk']['imported'] == '高'
    assert fdict['payback_plan']['action'] == 'fill'
    assert fdict['payback_plan']['imported_list'] == [{'node': '尾款', 'amt': 30000.0, 'date': '2026-12-20'}]

    ap = s.post(f'{BASE}/api/receivables/import/apply', headers=H, json={
        'quarter': data['quarter'],
        'rows': [{'contract_id': _test_cid2, 'fields': {
            'customer_nature': '子集团内', 'cust_risk': '低', 'payback_risk': '高',
            'payback_plan': fdict['payback_plan']['imported_list'],
        }}],
    }, timeout=10)
    apd = ap.json()
    print(f'    应用: {apd}')
    assert apd['code'] == 200 and apd['data']['applied'] == 1

    lst4 = s.get(f'{BASE}/api/receivables', headers=H, params={'quarter': data['quarter']}, timeout=10).json()
    m4 = [i for i in lst4['data']['items'] if i['contract_id'] == _test_cid2][0]
    plan = json.loads(m4['payback_plan'])
    print(f'    导入后: nature={m4["customer_nature"]}, cust_risk={m4["cust_risk"]}, '
          f'payback_risk={m4["payback_risk"]}, plan={plan}')
    assert m4['customer_nature'] == '子集团内' and m4['cust_risk'] == '低' and m4['payback_risk'] == '高'
    assert plan == [{'node': '尾款', 'amt': 30000.0, 'date': '2026-12-20'}]

    # ---- 8. 导入比对（conflict 路径）：已有值 vs 导入值，用户裁决 ----
    wb2 = XWb()
    ws2 = wb2.active
    ws2.append(['往来单位', '项目名称', '客户性质', '客户风险', '回款风险'])
    ws2.append([_target['customer_name'], _target['project_name'], '集团内', '中', '高'])
    buf2 = io.BytesIO()
    wb2.save(buf2)
    buf2.seek(0)
    pv2 = s.post(f'{BASE}/api/receivables/import/preview', headers=H,
                 files={'file': ('import_test2.xlsx', buf2, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},
                 data={'quarter': data['quarter']}, timeout=30).json()
    trow2 = next(r for r in pv2['data']['rows'] if r['contract_id'] == _test_cid2)
    fdict2 = {f['key']: f for f in trow2['fields']}
    print(f'[8] 冲突预览: ' + ', '.join(f"{k}={v['action']}" for k, v in fdict2.items()))
    assert fdict2['customer_nature']['action'] == 'conflict'   # 子集团内 vs 集团内
    assert fdict2['cust_risk']['action'] == 'conflict'         # 低 vs 中
    assert fdict2['payback_risk']['action'] == 'same'          # 高 vs 高
    assert fdict2['payback_plan']['action'] == 'no_import'     # 该列无数据
    # 裁决：客户性质用导入值，客户风险保留现有
    ap2 = s.post(f'{BASE}/api/receivables/import/apply', headers=H, json={
        'quarter': data['quarter'],
        'rows': [{'contract_id': _test_cid2, 'fields': {'customer_nature': '集团内'}}],
    }, timeout=10)
    assert ap2.json()['code'] == 200
    lst5 = s.get(f'{BASE}/api/receivables', headers=H, params={'quarter': data['quarter']}, timeout=10).json()
    m5 = [i for i in lst5['data']['items'] if i['contract_id'] == _test_cid2][0]
    print(f'    裁决后: nature={m5["customer_nature"]}（导入）, cust_risk={m5["cust_risk"]}（保留）')
    assert m5['customer_nature'] == '集团内' and m5['cust_risk'] == '低'
else:
    print('[7/8] 快照为空或无可选目标合同，跳过导入测试')

# ---- 还原测试期间写入的填报数据 + 清理临时账号 ----
_restore_overrides()
cur.execute("DELETE FROM users WHERE username=%s", (TEST_USER,))
conn.commit()
cur.close()
conn.close()
print('== 全部通过，临时账号已清理 ==')
