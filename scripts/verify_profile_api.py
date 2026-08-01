# -*- coding: utf-8 -*-
"""验证客户3D画像接口 /api/customers/<id>/profile 的完整返回结构。
为 yewei(主任) 生成临时 token，调用接口并打印各数据段。
用完即删的验证脚本。
"""
import sqlite3
import uuid
import json
import urllib.request
import urllib.error
import sys
from datetime import datetime, timedelta

DB_PATH = r'C:\Program Files\python\crm\crm_app.db'
BASE = 'http://127.0.0.1:5000'
# 默认客户8，可通过命令行参数指定其它客户ID
TEST_CUST_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 8


def make_token(username, name, role):
    db = sqlite3.connect(DB_PATH)
    token = str(uuid.uuid4())
    expires = (datetime.now() + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
    db.execute(
        'INSERT INTO tokens (token, username, name, role, expires) VALUES (?,?,?,?,?)',
        (token, username, name, role, expires)
    )
    db.commit()
    db.close()
    return token


def cleanup_token(token):
    db = sqlite3.connect(DB_PATH)
    db.execute('DELETE FROM tokens WHERE token = ?', (token,))
    db.commit()
    db.close()


def call_profile(cust_id, token):
    url = f'{BASE}/api/customers/{cust_id}/profile'
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8'))


def main():
    token = make_token('yewei', '叶伟', '主任')
    print(f'生成临时 token: {token[:8]}...')
    try:
        status, body = call_profile(TEST_CUST_ID, token)
        print(f'\nHTTP状态: {status}')
        print(f'业务code: {body.get("code")}')
        print(f'消息: {body.get("message")}')

        data = body.get('data')
        if not data:
            print('!! 无 data 返回')
            return

        cust = data.get('customer', {})
        print('\n=== 客户基本信息 ===')
        for k in ('id', 'name', 'company', 'phone', 'contact_name', 'email',
                  'industry', 'region', 'level', 'source', 'owner_name',
                  'created_at', 'last_follow'):
            print(f'  {k}: {cust.get(k)}')

        stats = data.get('stats', {})
        print('\n=== 统计汇总 ===')
        for k, v in stats.items():
            print(f'  {k}: {v}')

        print('\n=== 各段数据条数 ===')
        print(f'  跟进记录 follow_logs: {len(data.get("follow_logs", []))} 条')
        print(f'  商机 business:        {len(data.get("business", []))} 条')
        print(f'  合同 contracts:       {len(data.get("contracts", []))} 条')
        print(f'  拜访 visits:          {len(data.get("visits", []))} 条')

        # 抽样展示
        contracts = data.get('contracts', [])
        if contracts:
            print('\n=== 合同样本(第1条) ===')
            c = contracts[0]
            for k in ('contract_no', 'contract_name', 'party_a', 'total_amt',
                      'sign_date', 'status', 'owner_name', 'business_title'):
                print(f'  {k}: {c.get(k)}')

        business = data.get('business', [])
        if business:
            print('\n=== 商机样本(第1条) ===')
            b = business[0]
            for k in ('id', 'title', 'stage', 'amount', 'probability',
                      'predict_date', 'owner_name', 'status'):
                print(f'  {k}: {b.get(k)}')

        visits = data.get('visits', [])
        if visits:
            print('\n=== 拜访样本(第1条) ===')
            v = visits[0]
            for k in ('id', 'plan_date', 'plan_time', 'purpose', 'status',
                      'visitor_name', 'work_type'):
                print(f'  {k}: {v.get(k)}')

        follow_logs = data.get('follow_logs', [])
        if follow_logs:
            print('\n=== 跟进样本(第1条) ===')
            f = follow_logs[0]
            for k in ('id', 'subject', 'content', 'log_time', 'user_name'):
                print(f'  {k}: {f.get(k)}')

        print('\n✅ 画像接口返回结构验证完成')
    finally:
        cleanup_token(token)
        print('\n临时 token 已清理')


if __name__ == '__main__':
    main()
