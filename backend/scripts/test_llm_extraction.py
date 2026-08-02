"""测试 LLM 启用后的 AI 搜索结构化提取效果。
直接调用 _scrape_ai_search，对比 LLM 提取 vs 降级提取的字段丰富度。
"""
import os
import sys
import json

# 确保能导入 backend 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 设置环境变量（确保当前进程有 LLM_API_KEY）
os.environ.setdefault('LLM_API_KEY', 'sk-51151dbb41e047029c02bd2bbfc61387')

from config import USE_LLM, LLM_MODEL, LLM_API_BASE
print('USE_LLM =', USE_LLM)
print('LLM_MODEL =', LLM_MODEL)
print('LLM_API_BASE =', LLM_API_BASE)
print()

if not USE_LLM:
    print('ERROR: LLM 未启用，请检查 LLM_API_KEY 环境变量')
    sys.exit(1)

from routes.leads import _scrape_ai_search, _fallback_extract_leads, _search_web, _build_search_queries

# 选一个能力域测试：招投标监控（最容易看出结构化效果）
category = '招投标监控'
keywords = ['卫星遥感', '卫星通信', 'AI智能体']

source = {'name': '测试-' + category, 'region': '全国'}
config = {'max_items': 8, 'max_queries': 2}

queries = _build_search_queries(keywords, category, max_queries=2)
print('搜索查询:', queries)
print()

# 先搜索获取原始结果
print('=' * 60)
print('步骤1: 搜索引擎获取原始结果')
all_results = []
seen = set()
for q in queries:
    results = _search_web(q, max_results=8)
    for r in results:
        if r['url'] not in seen:
            seen.add(r['url'])
            all_results.append(r)
    if len(all_results) >= 8:
        break
    import time; time.sleep(2)

print('获取到 {} 条搜索结果'.format(len(all_results)))
for i, r in enumerate(all_results[:5], 1):
    print('  {}. {}'.format(i, r['title'][:60]))
    print('     link: {}'.format(r['url'][:70]))
print()

# 步骤2: LLM 结构化提取
print('=' * 60)
print('步骤2: LLM 结构化提取')
llm_leads = _scrape_ai_search(source, config, keywords, category)
print('LLM 提取到 {} 条线索'.format(len(llm_leads)))
print()
for i, lead in enumerate(llm_leads[:5], 1):
    print('  {}. 商机名: {}'.format(i, lead.get('opportunity_name', '')[:55]))
    print('     公司: {} | 行业: {} | 地区: {}'.format(lead.get('company', ''), lead.get('industry', ''), lead.get('region', '')))
    print('     联系人: {} | 电话: {}'.format(lead.get('contact_name', '-') or '-', lead.get('phone', '-') or '-'))
    raw = json.loads(lead.get('raw_data', '{}')) if lead.get('raw_data') else {}
    intent = raw.get('intent', '')
    score = raw.get('intent_score', '')
    llm_used = raw.get('llm_used', 'N/A')
    print('     意向: {} | 评分: {} | LLM提取: {}'.format(intent[:60] if intent else '-', score, llm_used))
    print('     链接: {}'.format(lead.get('link', '')[:70]))
    print()

# 步骤3: 对比降级提取
print('=' * 60)
print('步骤3: 降级提取对比（无LLM）')
fallback_leads = _fallback_extract_leads(all_results, source, keywords, category, 8)
print('降级提取到 {} 条线索'.format(len(fallback_leads)))
for i, lead in enumerate(fallback_leads[:3], 1):
    print('  {}. 商机名: {}'.format(i, lead.get('opportunity_name', '')[:55]))
    raw = json.loads(lead.get('raw_data', '{}')) if lead.get('raw_data') else {}
    print('     LLM提取: {} | 备注: {}'.format(raw.get('llm_used', 'N/A'), (lead.get('remark') or '')[:40]))

print()
print('=' * 60)
print('总结:')
print('  LLM 提取: {} 条，含 intent/intent_score/结构化行业字段'.format(len(llm_leads)))
print('  降级提取: {} 条，仅标题+摘要，无意向分析'.format(len(fallback_leads)))
