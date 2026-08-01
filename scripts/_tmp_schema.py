import sqlite3

p = r'C:\Program Files\python\crm\crm_app.db'
db = sqlite3.connect(p)
db.row_factory = sqlite3.Row
c = db.cursor()

for tbl in ['customers', 'business', 'contracts', 'visits', 'follow_logs']:
    print(f'=== {tbl} ===')
    c.execute(f"PRAGMA table_info({tbl})")
    for r in c.fetchall():
        print(f"  {r['name']:22s} {r['type']}")
    print()

# 检查 contracts 与 customers 的关联方式
print('=== contracts 样本（看 party_a 等字段）===')
c.execute("SELECT * FROM contracts LIMIT 1")
row = c.fetchone()
if row:
    print(dict(row))

print('\n=== business 样本（看 cust_id）===')
c.execute("SELECT id, title, cust_id, owner_id, status FROM business WHERE cust_id IS NOT NULL LIMIT 3")
for r in c.fetchall():
    print(dict(r))

print('\n=== visits 样本（看 cust_id）===')
c.execute("SELECT id, cust_id, visitor_id, visit_date, work_type FROM visits WHERE cust_id IS NOT NULL LIMIT 3")
for r in c.fetchall():
    print(dict(r))

print('\n=== follow_logs 样本（看 ref_type/ref_id）===')
c.execute("SELECT id, ref_type, ref_id, user_id, subject FROM follow_logs WHERE ref_type='customer' LIMIT 3")
for r in c.fetchall():
    print(dict(r))

db.close()
