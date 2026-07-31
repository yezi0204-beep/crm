import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "crm_app.db")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

stage_to_probability = {
    '初步接触': (0, '引导需求阶段'),
    '初步洽谈': (10, '引导需求阶段'),
    '需求确认': (30, '引导需求阶段'),
    '需求确认中': (30, '引导需求阶段'),
    '方案报价': (50, '能力展示阶段'),
    '方案报价中': (50, '能力展示阶段'),
    '商务谈判': (85, '商务谈判阶段'),
    '合同签署': (95, '合同签订阶段'),
    '赢单成交': (100, '销售实现'),
    '项目启动': (100, '销售实现'),
    '实施中': (100, '销售实现'),
    '已完成': (100, '销售实现'),
}

cursor.execute("SELECT id, stage, probability FROM business WHERE status != 'void'")
rows = cursor.fetchall()

updated_count = 0
for row in rows:
    stage = row['stage']
    probability = row['probability']
    
    if stage and stage in stage_to_probability:
        new_prob, new_stage = stage_to_probability[stage]
        cursor.execute(
            "UPDATE business SET probability=?, stage=? WHERE id=?",
            (new_prob, new_stage, row['id'])
        )
        updated_count += 1
    elif stage and stage not in stage_to_probability:
        print(f"  未映射的阶段: ID={row['id']}, stage='{stage}', prob={probability}")
        if probability is None or probability == 0:
            cursor.execute(
                "UPDATE business SET probability=0, stage='引导需求阶段' WHERE id=?",
                (row['id'],)
            )
            updated_count += 1

conn.commit()

cursor.execute("SELECT id, stage, probability FROM business WHERE status != 'void' LIMIT 10")
updated_rows = cursor.fetchall()

print(f"\n更新了 {updated_count} 条商机数据")
print()
print("更新后的商机数据示例:")
for row in updated_rows:
    print(f"  ID:{row['id']} 阶段:{row['stage']} 概率:{row['probability']}%")

cursor.execute("SELECT COUNT(*) as cnt FROM business WHERE status != 'void' AND probability >= 100")
completed = cursor.fetchone()['cnt']
cursor.execute("SELECT COUNT(*) as cnt FROM business WHERE status != 'void' AND probability >= 90 AND probability < 100")
contract_signing = cursor.fetchone()['cnt']
cursor.execute("SELECT COUNT(*) as cnt FROM business WHERE status != 'void' AND probability >= 80 AND probability < 90")
negotiation = cursor.fetchone()['cnt']
cursor.execute("SELECT COUNT(*) as cnt FROM business WHERE status != 'void' AND probability >= 60 AND probability < 80")
solution = cursor.fetchone()['cnt']
cursor.execute("SELECT COUNT(*) as cnt FROM business WHERE status != 'void' AND probability >= 30 AND probability < 60")
capability = cursor.fetchone()['cnt']
cursor.execute("SELECT COUNT(*) as cnt FROM business WHERE status != 'void' AND probability < 30")
guidance = cursor.fetchone()['cnt']

print()
print("商机阶段分布:")
print(f"  引导需求阶段 (0-30%): {guidance} 个")
print(f"  能力展示阶段 (30-60%): {capability} 个")
print(f"  方案确定阶段 (60-80%): {solution} 个")
print(f"  商务谈判阶段 (80-90%): {negotiation} 个")
print(f"  合同签订阶段 (90-100%): {contract_signing} 个")
print(f"  销售实现 (100%): {completed} 个")

conn.close()
