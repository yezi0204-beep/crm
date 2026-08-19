import sqlite3
conn = sqlite3.connect('crm_app.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# 1. 检查 contracts 表是否有 is_framework 列
cur.execute("PRAGMA table_info(contracts)")
cols = [r['name'] for r in cur.fetchall()]
print('contracts 表列:', cols)
print('is_framework 存在:', 'is_framework' in cols)
print()

# 2. 查钱海明的合同
cur.execute("SELECT username FROM users WHERE name LIKE '%钱海明%'")
user_rows = cur.fetchall()
print('钱海明用户:', [dict(r) for r in user_rows])

if user_rows:
    usernames = [r['username'] for r in user_rows]
    placeholders = ','.join('?' * len(usernames))
    cur.execute(f"SELECT id, contract_name, total_amt, owner_id, is_framework, sign_date FROM contracts WHERE owner_id IN ({placeholders})", usernames)
    contracts = cur.fetchall()
    print(f'\n钱海明的合同 ({len(contracts)} 条):')
    for c in contracts:
        print(f'  ID={c["id"]} 名称={c["contract_name"]} 总额={c["total_amt"]} owner={c["owner_id"]} is_framework={c["is_framework"]} 签订={c["sign_date"]}')

# 3. 查所有 is_framework=1 的合同
print('\n所有框架合同:')
cur.execute("SELECT id, contract_name, total_amt, owner_id, is_framework FROM contracts WHERE is_framework=1")
fw_rows = cur.fetchall()
if fw_rows:
    for r in fw_rows:
        print(f'  ID={r["id"]} 名称={r["contract_name"]} 总额={r["total_amt"]} owner={r["owner_id"]}')
else:
    print('  （无框架合同标记）')

# 4. 查 contract_acceptances 表是否存在及有数据
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='contract_acceptances'")
if cur.fetchone():
    cur.execute("SELECT COUNT(*) as c FROM contract_acceptances")
    print(f'\n验收记录数: {cur.fetchone()["c"]}')
    cur.execute("SELECT * FROM contract_acceptances LIMIT 5")
    for r in cur.fetchall():
        print(f'  {dict(r)}')
else:
    print('\ncontract_acceptances 表不存在！')

conn.close()
