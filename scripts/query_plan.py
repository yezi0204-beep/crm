import sqlite3

conn = sqlite3.connect('../crm_app.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(users)")
cols = cursor.fetchall()
print("Users table columns:")
for c in cols:
    print(f"  {c['name']}")

cursor.execute('SELECT * FROM users')
rows = cursor.fetchall()
print("\nUsers:")
for r in rows:
    print(f"  {dict(r)}")

conn.close()