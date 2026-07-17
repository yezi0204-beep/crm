from datetime import datetime

today = datetime.now()
current_week_num = int(today.strftime('%W'))
current_year = today.year
current_week_label = today.strftime('%Y-W%W')

print(f"当前日期: {today}")
print(f"当前年份: {current_year}")
print(f"当前周数: {current_week_num}")
print(f"当前周标签: {current_week_label}")

import sqlite3
conn = sqlite3.connect('../crm_app.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute('SELECT id, title, plan_week, next_week_plan FROM business WHERE next_week_plan IS NOT NULL AND next_week_plan != ""')
rows = cursor.fetchall()

print("\n有next_week_plan的商机:")
for r in rows:
    pw = r['plan_week'] or ''
    nwp = r['next_week_plan'] or ''
    title = r['title'][:15]
    
    if pw:
        try:
            plan_year = int(pw[:4])
            plan_week = int(pw[6:])
            print(f"ID:{r['id']} | {title} | plan_week={pw} | year={plan_year}, week={plan_week} | next_week_plan={nwp[:20]}")
            print(f"  比较: plan_week({plan_week}) <= current_week({current_week_num}) ? {plan_week <= current_week_num}")
        except:
            print(f"ID:{r['id']} | {title} | plan_week={pw} (格式错误) | next_week_plan={nwp[:20]}")
    else:
        print(f"ID:{r['id']} | {title} | plan_week=空 | next_week_plan={nwp[:20]}")

conn.close()