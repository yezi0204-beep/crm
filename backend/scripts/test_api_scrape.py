"""通过后端 API 测试 AI 搜索抓取（验证后端进程能否搜索）。"""
import requests

base = 'http://127.0.0.1:5000'

# 尝试登录
for user, pwd in [('yewei', '123456'), ('yewei', 'admin123'), ('yewei', 'yewei'),
                   ('admin', 'admin123'), ('admin', '123456')]:
    r = requests.post(base + '/api/auth/login', json={'username': user, 'password': pwd}, timeout=5)
    data = r.json()
    if data.get('code') == 200:
        token = data['data']['token']
        print('登录成功:', user)
        break
else:
    print('所有账号登录失败')
    # 尝试直接用 API key 或其他方式
    import sys
    sys.exit(1)

# 列出线索源
r2 = requests.get(base + '/api/leads/sources', headers={'Authorization': 'Bearer ' + token}, timeout=5)
sources = r2.json().get('data', [])
ai_sources = [s for s in sources if s.get('source_type') == 'ai_search']
print('\nAI搜索源共 {} 个:'.format(len(ai_sources)))
for s in ai_sources:
    print('  ID:{} {} ({}启用)'.format(s['id'], s['name'], '已' if s['enabled'] else '未'))

# 触发一个 AI 搜索源的抓取（选舆情痛点，之前没抓过）
if ai_sources:
    target = next((s for s in ai_sources if '舆情痛点' in s.get('name', '')), ai_sources[0])
    print('\n触发抓取: {} (ID:{})'.format(target['name'], target['id']))
    r3 = requests.post(base + '/api/leads/sources/{}/scrape'.format(target['id']),
                       headers={'Authorization': 'Bearer ' + token}, timeout=60)
    result = r3.json()
    print('抓取结果:', result.get('code'), result.get('message'))
    if result.get('data'):
        print('  新增线索数:', result['data'].get('scraped_count'))
        print('  错误:', result['data'].get('error'))

    # 查看最新线索
    r4 = requests.get(base + '/api/leads?category=' + target.get('category', ''),
                      headers={'Authorization': 'Bearer ' + token}, timeout=5)
    leads_data = r4.json().get('data', {})
    leads = leads_data.get('list', [])
    print('\n该类别最新线索:')
    for l in leads[:5]:
        print('  - {} | {}'.format(l.get('opportunity_name', '')[:50], l.get('link', '')[:60]))
