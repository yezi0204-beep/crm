# -*- coding: utf-8 -*-
"""一次性迁移：税额从合同级迁到验收记录级。
1. contract_acceptances 新增 tax_amount 列（默认 0）
2. 存量合同税额分摊：单条记录合同→该记录；多条记录合同→最新一条记录（保持 SUM 不变，含税收入不受影响）
"""
import sys
sys.path.insert(0, r'c:\Program Files\python\crm\backend')
from dotenv import load_dotenv
load_dotenv(r'c:\Program Files\python\crm\.env')
import db

c = db.open_db()
cur = c.cursor()

# 1) 新增列（已存在则跳过）
cur.execute("SHOW COLUMNS FROM contract_acceptances LIKE 'tax_amount'")
if not cur.fetchone():
    cur.execute("ALTER TABLE contract_acceptances ADD COLUMN tax_amount DOUBLE NOT NULL DEFAULT 0")
    print('列 tax_amount 已添加')
else:
    print('列 tax_amount 已存在，跳过')

# 2) 存量税额迁移：每合同税额写到最新一条验收记录
cur.execute("""
    SELECT c.id, c.tax_amount,
           (SELECT ca.id FROM contract_acceptances ca
            WHERE ca.contract_id = c.id
            ORDER BY ca.acceptance_date DESC, ca.id DESC LIMIT 1) AS latest_acc_id
    FROM contracts c
    WHERE COALESCE(c.tax_amount, 0) > 0
      AND EXISTS (SELECT 1 FROM contract_acceptances x WHERE x.contract_id = c.id)
""")
rows = cur.fetchall()
moved = 0
for r in rows:
    if r['latest_acc_id']:
        cur.execute("UPDATE contract_acceptances SET tax_amount=? WHERE id=?",
                    (float(r['tax_amount']), r['latest_acc_id']))
        moved += 1
c.commit()
print(f'已迁移 {moved} 个合同的税额到其最新验收记录')

# 3) 校验：迁移后 SUM(记录税额) 应等于原合同税额
cur.execute("""
    SELECT c.id, c.contract_name, c.tax_amount, COALESCE(SUM(ca.tax_amount),0) acc_tax_sum
    FROM contracts c LEFT JOIN contract_acceptances ca ON ca.contract_id=c.id
    GROUP BY c.id, c.contract_name, c.tax_amount
    HAVING ABS(COALESCE(c.tax_amount,0) - acc_tax_sum) > 0.01
       AND EXISTS (SELECT 1 FROM contract_acceptances x WHERE x.contract_id = c.id)
""")
diff = cur.fetchall()
print('迁移后口径不一致的合同数（应为0，除非该合同本无记录）:', len(diff))
for r in diff:
    print(dict(r))
c.close()
