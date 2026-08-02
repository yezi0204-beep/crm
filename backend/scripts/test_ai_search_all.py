"""测试五大能力域 AI 智能体搜索（真实互联网搜索）。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes.leads import _scrape_ai_search, _search_web, _build_search_queries

categories = [
    ('招投标监控', ['卫星遥感', '卫星通信', 'AI智能体']),
    ('电商商机', ['卫星通信终端', '智能体']),
    ('企业客源', ['卫星遥感', '通信科技']),
    ('竞品情报', ['卫星通信', '遥感软件']),
    ('舆情痛点', ['遥感数据', '卫星通信']),
]

for category, keywords in categories:
    print('\n' + '=' * 60)
    print('【{}】关键词: {}'.format(category, keywords))
    queries = _build_search_queries(keywords, category, max_queries=2)
    print('搜索查询: {}'.format(queries))
    source = {'name': '测试-' + category, 'region': '全国'}
    config = {'max_items': 8, 'max_queries': 2}
    leads = _scrape_ai_search(source, config, keywords, category)
    print('抓取到 {} 条线索'.format(len(leads)))
    for i, l in enumerate(leads[:5], 1):
        print('  {}. {}'.format(i, l['opportunity_name'][:55]))
        print('     链接: {}'.format(l['link'][:75]))
        print('     行业: {} | 备注: {}'.format(l['industry'], (l['remark'] or '')[:50]))

print('\n' + '=' * 60)
print('测试完成')
