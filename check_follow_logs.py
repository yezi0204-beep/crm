import sqlite3

conn = sqlite3.connect('crm_app.db')
cursor = conn.cursor()

print("检查follow_logs表结构:")
cursor.execute("PRAGMA table_info(follow_logs)")
cols = cursor.fetchall()
for col in cols:
    print(f"  {col[1]}: {col[2]}")

print("\n检查follow_logs数据:")
cursor.execute("SELECT id, ref_type, ref_id, user_id, content, created_at FROM follow_logs LIMIT 10")
rows = cursor.fetchall()
if len(rows) == 0:
    print("  暂无跟进记录")
else:
    for row in rows:
        print(f"  ID={row[0]}, ref_type={row[1]}, ref_id={row[2]}, user_id={row[3]}, content={row[4][:30]}..., created_at={row[5]}")

print("\n检查business相关的跟进记录:")
cursor.execute("SELECT id, ref_type, ref_id, user_id, content, created_at FROM follow_logs WHERE ref_type = 'business' LIMIT 10")
rows = cursor.fetchall()
if len(rows) == 0:
    print("  暂无business类型的跟进记录")
else:
    for row in rows:
        print(f"  ID={row[0]}, ref_id={row[1]}, content={row[4][:30]}..., created_at={row[5]}")

conn.close()
