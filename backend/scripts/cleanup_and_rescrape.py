"""清理数据库中的垃圾线索（百科/地图/导航等非商机页面），然后用修复后的代码重新抓取招投标监控。"""
import os
import sys
import json
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('LLM_API_KEY', 'sk-51151dbb41e047029c02bd2bbfc61387')

from config import USE_LLM, LLM_MODEL
print('USE_LLM =', USE_LLM, '| LLM_MODEL =', LLM_MODEL)

from routes.leads import _scrape_source, _persist_leads, _is_junk_url, _build_search_queries

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'crm_app.db')
conn = sqlite3.connect(DB_PATH, timeout=10)
conn.execute('PRAGMA journal_mode=WAL')
conn.execute('PRAGMA busy_timeout=10000')
cur = conn.cursor()

# 1. 清理已有的垃圾线索
print()
print('=' * 55)
print('步骤1: 清理数据库中的垃圾线索（百科/地图/导航等）')
cur.execute("SELECT id, opportunity_name, link FROM scraped_leads")
junk_ids = []
for row in cur.fetchall():
    lid, name, link = row
    if _is_junk_url(link):
        junk_ids.append(lid)
        print('  删除 #{}: {} | {}'.format(lid, (name or '')[:35], (link or '')[:50]))
if junk_ids:
    cur.executemany("DELETE FROM scraped_leads WHERE id=?", [(i,) for i in junk_ids])
    conn.commit()
    print('  已删除 {} 条垃圾线索'.format(len(junk_ids)))
else:
    print('  无垃圾线索')

# 2. 重置招投标监控源的抓取时间戳
cur.execute("UPDATE lead_sources SET last_scraped_at=NULL WHERE source_type='ai_search' AND category='招投标监控'")
conn.commit()
print()
print('已重置招投标监控源抓取时间戳')

# 3. 重新抓取招投标监控
cur.execute("""SELECT id, name, source_type, config, keywords, industry, region, category
               FROM lead_sources WHERE source_type='ai_search' AND category='招投标监控' AND enabled=1""")
sources = cur.fetchall()
print('找到 {} 个招投标监控源'.format(len(sources)))

from datetime import datetime
now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
total_new = 0

for row in sources:
    source_id, name, stype, config_str, keywords_str, industry, region, category = row
    source = {
        'id': source_id, 'name': name, 'source_type': stype,
        'config': config_str, 'keywords': keywords_str,
        'industry': industry, 'region': region or '全国', 'category': category,
    }
    keywords = [k.strip() for k in (keywords_str or '').split(',') if k.strip()]

    print()
    print('=' * 55)
    print('抓取: {} [{}]'.format(name, category))
    queries = _build_search_queries(keywords, category, max_queries=3)
    print('搜索查询:')
    for q in queries:
        print('  -', q)

    leads, error = _scrape_source(source)
    if error:
        print('  错误:', error)
        continue
    if not leads:
        print('  无结果（LLM 判定无有价值商机或搜索无结果）')
        continue

    new_count = _persist_leads(cur, leads, source_id, name, category)
    conn.commit()
    total_new += new_count
    print('  抓取 {} 条, 新增 {} 条'.format(len(leads), new_count))

    for i, lead in enumerate(leads[:5], 1):
        raw = json.loads(lead.get('raw_data', '{}')) if lead.get('raw_data') else {}
        llm_used = raw.get('llm_used', False)
        print('    {}. {} | {} | {} | 评分{} | LLM={}'.format(
            i, lead.get('opportunity_name', '')[:40],
            lead.get('company', '')[:20], lead.get('industry', ''),
            raw.get('intent_score', '-'), llm_used
        ))
        print('       链接: {}'.format(lead.get('link', '')[:65]))

# 4. 更新抓取时间戳
cur.execute("UPDATE lead_sources SET last_scraped_at=? WHERE source_type='ai_search' AND category='招投标监控'", (now,))
conn.commit()

print()
print('=' * 55)
print('完成! 新增 {} 条招投标线索'.format(total_new))

# 5. 最终统计
cur.execute("SELECT COUNT(*) FROM scraped_leads")
total = cur.fetchone()[0]
cur.execute("SELECT category, COUNT(*) FROM scraped_leads GROUP BY category ORDER BY 2 DESC")
print('数据库总线索: {}'.format(total))
print('按能力域:')
for r in cur.fetchall():
    print('  {} = {}'.format(r[0], r[1]))

conn.close()
