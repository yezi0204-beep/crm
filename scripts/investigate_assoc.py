# -*- coding: utf-8 -*-
"""调查合同-商机-客户关联现状，为画像关联逻辑重构提供依据。"""
import sqlite3

DB_PATH = r'C:\Program Files\python\crm\crm_app.db'
db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row
c = db.cursor()

print('=== contracts 表结构 ===')
c.execute("PRAGMA table_info(contracts)")
for r in c.fetchall():
    print(f"  {r['name']:20s} {r['type']}")

print('\n=== business 表结构 ===')
c.execute("PRAGMA table_info(business)")
for r in c.fetchall():
    print(f"  {r['name']:20s} {r['type']}")

print('\n=== 客户73的商机 ===')
c.execute("SELECT id,title,cust_id,owner_id,amount FROM business WHERE cust_id=73")
for r in c.fetchall():
    print(' ', dict(r))

print('\n=== 客户73公司名的所有合同(含b_id) ===')
c.execute("""SELECT id, contract_no, contract_name, b_id, party_a, total_amt, sign_date
             FROM contracts
             WHERE party_a='中国电子科技集团公司第三十八研究所'
             ORDER BY sign_date DESC""")
rows = c.fetchall()
print(f'  共 {len(rows)} 条')
for r in rows:
    print(' ', dict(r))

print('\n=== 全库: 合同b_id关联的商机及其cust_id ===')
c.execute("""SELECT ct.id AS cid, ct.contract_no, ct.contract_name, ct.b_id,
                    b.title AS biz_title, b.cust_id AS biz_cust_id,
                    cust.name AS cust_name, cust.company AS cust_company
             FROM contracts ct
             LEFT JOIN business b ON ct.b_id = b.id
             LEFT JOIN customers cust ON b.cust_id = cust.id
             WHERE ct.b_id IS NOT NULL AND ct.b_id != 0""")
for r in c.fetchall():
    print(' ', dict(r))

print('\n=== 同公司多客户情况(38所) ===')
c.execute("""SELECT id, name, company, owner_id
             FROM customers
             WHERE company='中国电子科技集团公司第三十八研究所'
             ORDER BY id""")
rows = c.fetchall()
print(f'  该公司有 {len(rows)} 个客户联系人:')
for r in rows:
    print(' ', dict(r))

print('\n=== 合同是否有cust_id字段直接关联客户? ===')
c.execute("PRAGMA table_info(contracts)")
cols = [r['name'] for r in c.fetchall()]
print(f'  contracts表字段: {cols}')
print(f'  是否有cust_id字段: {"cust_id" in cols}')

db.close()
