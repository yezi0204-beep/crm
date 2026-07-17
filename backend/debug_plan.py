import sqlite3
import json

print("=== 1. 检查数据库中ID为63的商机 ===")
conn = sqlite3.connect('../crm_app.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute('SELECT * FROM business WHERE id=63')
row = cursor.fetchone()
if row:
    print(f"next_week_plan: '{row['next_week_plan']}'")
    print(f"weekly_plan: '{row['weekly_plan']}'")
    print(f"plan_week: '{row['plan_week']}'")
else:
    print("未找到ID为63的商机")

print("\n=== 2. 模拟GET /api/business返回的数据 ===")
cursor.execute("SELECT b.*, c.company as customer_name, c.name as customer_contact, u.name as owner_name FROM business b LEFT JOIN customers c ON b.cust_id = c.id LEFT JOIN users u ON b.owner_id = u.username WHERE b.status='active' AND b.id=63")
row = cursor.fetchone()
if row:
    data = dict(row)
    print(f"next_week_plan: '{data.get('next_week_plan')}'")
    print(f"weekly_plan: '{data.get('weekly_plan')}'")
    print(f"plan_week: '{data.get('plan_week')}'")
    
    print("\n完整数据:")
    for k, v in data.items():
        if k in ['weekly_plan', 'next_week_plan', 'plan_week']:
            print(f"  {k}: '{v}'")

conn.close()