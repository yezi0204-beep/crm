"""检查 AI 搜索线索的当前状态。"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'crm_app.db')
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# 总线索数
cur.execute('SELECT COUNT(*) FROM scraped_leads')
print('总线索数:', cur.fetchone()[0])

# 按能力域分类
cur.execute('SELECT COALESCE(category,"(空)"), COUNT(*) FROM scraped_leads GROUP BY category ORDER BY 2 DESC')
print('\n按能力域分类:')
for r in cur.fetchall():
    print('  ', r[0], '=', r[1])

# 按来源类型
cur.execute("""SELECT ls.source_type, COUNT(sl.id)
               FROM scraped_leads sl LEFT JOIN lead_sources ls ON sl.source_id=ls.id
               GROUP BY ls.source_type""")
print('\n按来源类型:')
for r in cur.fetchall():
    print('  ', r[0], '=', r[1])

# AI 搜索源状态
cur.execute("SELECT id,name,source_type,enabled,last_scraped_at FROM lead_sources WHERE source_type='ai_search'")
print('\nAI 搜索源状态:')
for r in cur.fetchall():
    print('  ', r)

# 最近 10 条线索
cur.execute("SELECT id, opportunity_name, category, link, scraped_at FROM scraped_leads ORDER BY id DESC LIMIT 10")
print('\n最近 10 条线索:')
for r in cur.fetchall():
    name = (r[1] or '')[:40]
    link = (r[3] or '')[:50]
    print(f"  #{r[0]} [{r[2]}] {name} | {link} | {r[4]}")

conn.close()
