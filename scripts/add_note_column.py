import sqlite3

conn = sqlite3.connect('../crm_app.db')
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE contracts ADD COLUMN note TEXT")
    print("成功添加note字段到contracts表")
except sqlite3.OperationalError as e:
    print(f"字段可能已存在: {e}")

cursor.execute("PRAGMA table_info(contracts)")
cols = cursor.fetchall()
print("\ncontracts表结构:")
for c in cols:
    print(f"  {c[1]} ({c[2]})")

conn.commit()
conn.close()