"""验证五大能力域线索源是否正确入库。"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'crm_app.db')
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute('SELECT id, name, source_type, category, enabled, url FROM lead_sources ORDER BY category, id')
rows = c.fetchall()
print('=== 线索源列表（按能力域分组）===')
cur_cat = ''
for r in rows:
    cat = r['category'] or '(无类别)'
    if cat != cur_cat:
        cur_cat = cat
        print('\n【' + cur_cat + '】')
    en = '启用' if r['enabled'] else '停用'
    print('  {:>3} | {:6} | {} | {}'.format(r['id'], r['source_type'], en, r['name']))
    print('       URL: ' + (r['url'] or '')[:75])
print('\n总计 {} 个线索源'.format(len(rows)))

# 统计类别分布
c.execute('SELECT COALESCE(category, "无") as cat, COUNT(*) as cnt FROM lead_sources GROUP BY category')
print('\n=== 能力域分布 ===')
for r in c.fetchall():
    print('  {}: {} 个源'.format(r['cat'], r['cnt']))

# 检查 scraped_leads 表 category 字段
c.execute('SELECT COALESCE(category, "无") as cat, COUNT(*) as cnt FROM scraped_leads GROUP BY category')
print('\n=== 线索类别分布 ===')
for r in c.fetchall():
    print('  {}: {} 条线索'.format(r['cat'], r['cnt']))

conn.close()
print('\n验证完成')
