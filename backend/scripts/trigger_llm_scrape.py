"""触发 LLM 提取的真实抓取，将结构化线索写入数据库。
直接用 sqlite3 操作数据库，不启动 Flask app / scheduler，避免数据库锁冲突。
"""
import os
import sys
import json
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('LLM_API_KEY', 'sk-51151dbb41e047029c02bd2bbfc61387')

from config import USE_LLM, LLM_MODEL
print('USE_LLM =', USE_LLM, '| LLM_MODEL =', LLM_MODEL)
print()

# 直接导入抓取函数（不导入 app，避免启动 scheduler）
from routes.leads import _scrape_source, _persist_leads

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'crm_app.db')
conn = sqlite3.connect(DB_PATH, timeout=10)
conn.execute('PRAGMA journal_mode=WAL')
conn.execute('PRAGMA busy_timeout=10000')
cur = conn.cursor()

# 1. 重置所有 ai_search 源的抓取时间戳
cur.execute("UPDATE lead_sources SET last_scraped_at=NULL WHERE source_type='ai_search'")
conn.commit()
print('已重置 AI 搜索源抓取时间戳')

# 2. 获取所有启用的 ai_search 源
cur.execute("""SELECT id, name, source_type, config, keywords, industry, region, category
               FROM lead_sources WHERE source_type='ai_search' AND enabled=1""")
sources = cur.fetchall()
print('找到 {} 个 AI 搜索源'.format(len(sources)))
print()

total_new = 0
for row in sources:
    source_id, name, stype, config_str, keywords_str, industry, region, category = row
    source = {
        'id': source_id, 'name': name, 'source_type': stype,
        'config': config_str, 'keywords': keywords_str,
        'industry': industry, 'region': region or '全国', 'category': category,
    }
    keywords = [k.strip() for k in (keywords_str or '').split(',') if k.strip()]

    print('=' * 55)
    print('抓取: {} [{}] keywords={}'.format(name, category, keywords[:3]))

    leads, error = _scrape_source(source)
    if error:
        print('  错误: {}'.format(error))
        continue
    if not leads:
        print('  无结果')
        continue

    # 3. 持久化到数据库
    new_count = _persist_leads(cur, leads, source_id, name, category)
    conn.commit()
    total_new += new_count
    print('  抓取 {} 条, 新增 {} 条'.format(len(leads), new_count))

    # 显示前 3 条 LLM 提取的结构化线索
    for i, lead in enumerate(leads[:3], 1):
        raw = json.loads(lead.get('raw_data', '{}')) if lead.get('raw_data') else {}
        llm_used = raw.get('llm_used', False)
        print('    {}. {} | {} | {} | 评分{} | LLM={}'.format(
            i,
            lead.get('opportunity_name', '')[:35],
            lead.get('company', '')[:20],
            lead.get('industry', ''),
            raw.get('intent_score', '-'),
            llm_used
        ))
    print()

# 4. 更新抓取时间戳
from datetime import datetime
now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
cur.execute("UPDATE lead_sources SET last_scraped_at=? WHERE source_type='ai_search'", (now,))
conn.commit()

print('=' * 55)
print('完成! 共新增 {} 条 LLM 结构化线索'.format(total_new))

# 5. 统计数据库中的 LLM 提取线索
cur.execute("SELECT COUNT(*) FROM scraped_leads")
total = cur.fetchone()[0]
cur.execute("""SELECT COUNT(*) FROM scraped_leads WHERE raw_data LIKE '%"llm_used": true%'""")
llm_count = cur.fetchone()[0]
print('数据库总线索: {} | 其中 LLM 提取: {}'.format(total, llm_count))

# 6. 显示 LLM 提取的线索样例
cur.execute("""SELECT id, opportunity_name, company, industry, region, contact_name, phone, raw_data
               FROM scraped_leads WHERE raw_data LIKE '%"llm_used": true%'
               ORDER BY id DESC LIMIT 5""")
print()
print('LLM 提取线索样例:')
for r in cur.fetchall():
    raw = json.loads(r[7]) if r[7] else {}
    print('  #{} {} | {} | {} | {} | 联系人={} | 评分={}'.format(
        r[0], (r[1] or '')[:30], (r[2] or '')[:15], r[3], r[4], r[5] or '-', raw.get('intent_score', '-')
    ))

conn.close()
