import sqlite3
conn = sqlite3.connect('crm_app.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()
# 查叶伟的 users 表 role 字段和 user_roles 表
cur.execute("SELECT username, name, role, department FROM users WHERE name LIKE '%叶伟%'")
for r in cur.fetchall():
    print(f'users表: {dict(r)}')
    cur.execute("SELECT role FROM user_roles WHERE username=?", (r['username'],))
    roles = [rr['role'] for rr in cur.fetchall()]
    print(f'user_roles表: {roles}')
    print()

# 看所有应用中心人员的 role 字段 vs user_roles
cur.execute("SELECT u.username, u.name, u.role, u.department FROM users u WHERE u.department = '应用中心' OR u.department LIKE '%应用%' ORDER BY u.name")
print('=== 应用中心人员 ===')
for r in cur.fetchall():
    cur.execute("SELECT role FROM user_roles WHERE username=?", (r['username'],))
    roles = [rr['role'] for rr in cur.fetchall()]
    print(f'  {r["name"]}({r["username"]}): users.role={r["role"]}, user_roles={roles}')
conn.close()
