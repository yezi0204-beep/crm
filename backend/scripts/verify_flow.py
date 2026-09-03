# -*- coding: utf-8 -*-
"""全流程验证：能力模型 / 任务系统 / AI日志 / 商机雷达 / 驾驶舱 / AI搜索"""
import sys
import io
import time
import json
import sqlite3
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = 'http://127.0.0.1:5000'
DB = r'c:\Program Files\python\crm\crm_app.db'
import bcrypt

conn = sqlite3.connect(DB)
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print('== 相关表:', [t for t in tables if t in ('capabilities', 'ai_operation_logs', 'ai_tasks')])

# 创建临时测试账号（主任角色=全权限），测完删除
TEST_USER = 'verify_test_tmp'
TEST_PWD = 'Vt123456!'
pw_hash = bcrypt.hashpw(TEST_PWD.encode(), bcrypt.gensalt()).decode()
conn.execute("DELETE FROM users WHERE username=?", (TEST_USER,))
conn.execute(
    "INSERT INTO users (username, password_hash, name, role, department, status) VALUES (?,?,?,?,?,?)",
    (TEST_USER, pw_hash, '流程验证', '主任', '验证部', '在职'))
conn.commit()
conn.close()
print('== 临时测试账号已创建:', TEST_USER)

USERNAME = TEST_USER

# ---------- 1. 登录 ----------
s = requests.Session()
login = s.post(f'{BASE}/api/auth/login', json={'username': USERNAME, 'password': TEST_PWD}, timeout=10)
print('\n[1] 登录:', login.status_code, login.text[:120])
if login.status_code != 200:
    sys.exit('登录失败，终止')

token = (login.json().get('data') or {}).get('token')
H = {'Authorization': f'Bearer {token}'}


def api(method, path, **kw):
    kw.setdefault('headers', H)
    kw.setdefault('timeout', 60)
    r = s.request(method, f'{BASE}{path}', **kw)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {'raw': r.text[:200]}


def show(label, code, data, keys=None):
    ok = code == 200 and (isinstance(data, dict) and data.get('code') in (200, None))
    d = data.get('data', data) if isinstance(data, dict) else data
    if isinstance(d, dict) and keys:
        d = {k: d.get(k) for k in keys}
    elif isinstance(d, list):
        d = f'[{len(d)} 条] 首条: ' + json.dumps(d[0], ensure_ascii=False)[:150] if d else '[]'
    print(f'[{label}] HTTP {code} {"OK" if ok else "FAIL"} ->', str(d)[:300])


# ---------- 2. 能力模型 ----------
code, data = api('POST', '/api/capabilities/seed')
show('2a 能力初始化', code, data)
code, data = api('GET', '/api/capabilities')
show('2b 能力列表', code, data)
code, data = api('POST', '/api/capabilities/match', json={'title': '海洋遥感监测系统采购', 'text': '需要遥感数据处理、GIS平台建设、AI智能识别，海洋生态环境监测'})
show('2c 能力匹配', code, data)

# ---------- 3. 任务系统 ----------
code, data = api('POST', '/api/tasks/submit', json={'task_type': 'update_customer_profile', 'payload': {}})
show('3a 提交任务', code, data)
task_id = None
if code == 200 and isinstance(data.get('data'), dict):
    task_id = data['data'].get('task_id') or data['data'].get('id')
time.sleep(3)
code, data = api('GET', '/api/tasks/stats')
show('3b 任务统计', code, data)
code, data = api('GET', '/api/tasks?page=1&page_size=5')
show('3c 任务列表', code, data)
if task_id:
    code, data = api('GET', f'/api/tasks/{task_id}')
    show('3d 任务详情', code, data)

# ---------- 4. AI操作日志 ----------
code, data = api('GET', '/api/ai-logs?page=1&page_size=5')
show('4 AI日志', code, data)

# ---------- 5. 驾驶舱 ----------
code, data = api('GET', '/api/cockpit/overview')
show('5a 驾驶舱总览', code, data)
code, data = api('GET', '/api/cockpit/trend?days=7')
show('5b 趋势(7天)', code, data)
code, data = api('GET', '/api/cockpit/distribution?type=industry')
show('5c 行业分布', code, data)

# ---------- 6. 商机雷达 ----------
code, data = api('GET', '/api/cockpit/radar-list?page=1&page_size=5')
show('6a 雷达列表', code, data)
code, data = api('GET', '/api/cockpit/radar-list?page=1&page_size=5&min_amount=1000000')
show('6b 雷达筛选(金额>=100万)', code, data)

# ---------- 7. AI搜索（可能较慢） ----------
t0 = time.time()
code, data = api('POST', '/api/cockpit/ai-search', json={'query': '最近三个月安徽有哪些500万以上的遥感项目？'}, timeout=300)
print(f'[7 AI搜索] HTTP {code} 耗时 {time.time()-t0:.1f}s ->', str(data)[:500])

print('\n== 全流程验证完成 ==')

# 清理临时测试账号
conn = sqlite3.connect(DB)
conn.execute("DELETE FROM users WHERE username=?", (TEST_USER,))
conn.commit()
conn.close()
print('== 临时测试账号已删除 ==')
