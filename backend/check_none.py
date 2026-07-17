import sqlite3

conn = sqlite3.connect('../crm_app.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute('SELECT id, title, weekly_plan, typeof(weekly_plan), next_week_plan, typeof(next_week_plan) FROM business WHERE id=63')
row = cursor.fetchone()
if row:
    print(f"weekly_plan: value='{row['weekly_plan']}', type={type(row['weekly_plan'])}, sqlite_type={row['typeof(weekly_plan)']}")
    print(f"next_week_plan: value='{row['next_week_plan']}', type={type(row['next_week_plan'])}, sqlite_type={row['typeof(next_week_plan)']}")
    print(f"weekly_plan == 'None': {row['weekly_plan'] == 'None'}")
    print(f"weekly_plan is None: {row['weekly_plan'] is None}")
    print(f"weekly_plan == None: {row['weekly_plan'] == None}")

cursor.execute("SELECT COUNT(*) FROM business WHERE weekly_plan IS NULL")
print(f"\nweekly_plan IS NULL的记录数: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM business WHERE weekly_plan = 'None'")
print(f"weekly_plan = 'None'的记录数: {cursor.fetchone()[0]}")

conn.close()