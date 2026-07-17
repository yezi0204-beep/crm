import requests
import json

session = requests.Session()
session.verify = False

login_data = {'username': 'yewei', 'password': '123456'}
try:
    r = session.post('http://localhost:5000/api/auth/login', json=login_data)
    result = r.json()
    
    if result.get('code') == 200:
        data = result.get('data', {})
        token = data.get('token', data.get('access_token'))
        
        headers = {'Authorization': f'Bearer {token}'}
        r = session.get('http://localhost:5000/api/business?status=active', headers=headers)
        
        data = r.json()
        if data.get('code') == 200:
            business_list = data.get('data', [])
            
            print("\n=== 检查有next_week_plan的商机 ===")
            for b in business_list:
                if b.get('next_week_plan'):
                    print(f"ID:{b['id']} | {b['title'][:15]} | next_week_plan='{b['next_week_plan']}'")
            
            print("\n=== 检查字段是否存在 ===")
            if business_list:
                first = business_list[0]
                print(f"所有字段: {list(first.keys())}")
                print(f"next_week_plan存在: {'next_week_plan' in first}")
                print(f"next_week_plan类型: {type(first.get('next_week_plan'))}")
                print(f"next_week_plan值: '{first.get('next_week_plan')}'")
except Exception as e:
    print(f"Error: {e}")