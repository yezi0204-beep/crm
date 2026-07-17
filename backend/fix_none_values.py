import sqlite3

conn = sqlite3.connect('../crm_app.db')
cursor = conn.cursor()

cursor.execute("UPDATE business SET weekly_plan = NULL WHERE weekly_plan = 'None'")
print(f"修复weekly_plan为'None'的记录: {cursor.rowcount} 条")

cursor.execute("UPDATE business SET next_week_plan = NULL WHERE next_week_plan = 'None'")
print(f"修复next_week_plan为'None'的记录: {cursor.rowcount} 条")

conn.commit()

cursor.execute('SELECT id, title, weekly_plan, next_week_plan, plan_week FROM business WHERE status="active" AND next_week_plan IS NOT NULL AND next_week_plan != ""')
rows = cursor.fetchall()

print("\n修复后有next_week_plan的商机:")
for r in rows:
    print(f"ID:{r[0]} | {r[1][:15]} | weekly_plan='{r[2]}' | next_week_plan='{r[3][:20]}' | plan_week='{r[4]}'")

conn.close()