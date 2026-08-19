"""检查月度考核累计实际是否按分成金额计算"""
import sqlite3
from datetime import datetime

conn = sqlite3.connect('crm_app.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

today_y = datetime.now().year

# 1. 查所有有分成的合同
print('=== 有分成的合同 ===')
cur.execute("""
    SELECT c.id, c.contract_name, c.total_amt, c.owner_id, c.sign_date, c.is_framework,
           cc.username, cc.ratio
    FROM contracts c
    JOIN contract_commissions cc ON c.id = cc.contract_id
    WHERE c.sign_date LIKE ?
    ORDER BY c.id, cc.ratio DESC
""", (f'{today_y}-%',))
for r in cur.fetchall():
    share = float(r['total_amt'] or 0) * float(r['ratio'] or 0) / 100.0
    print(f'  合同ID={r["id"]} {r["contract_name"]} total={r["total_amt"]} owner={r["owner_id"]} sign={r["sign_date"]} fw={r["is_framework"]}')
    print(f'    → {r["username"]}: {r["ratio"]}% = {share:.2f}元')

# 2. 查框架合同验收级分成
print('\n=== 框架合同验收级分成 ===')
cur.execute("""
    SELECT ca.id as acc_id, ca.contract_id, ca.acceptance_date, ca.acceptance_amount,
           c.contract_name, c.owner_id,
           ac.username, ac.ratio
    FROM contract_acceptances ca
    JOIN contracts c ON ca.contract_id = c.id
    JOIN acceptance_commissions ac ON ca.id = ac.acceptance_id
    WHERE ca.acceptance_date LIKE ?
    ORDER BY ca.id, ac.ratio DESC
""", (f'{today_y}-%',))
for r in cur.fetchall():
    share = float(r['acceptance_amount'] or 0) * float(r['ratio'] or 0) / 100.0
    print(f'  验收ID={r["acc_id"]} 合同={r["contract_name"]} 验收额={r["acceptance_amount"]} 日期={r["acceptance_date"]}')
    print(f'    → {r["username"]}: {r["ratio"]}% = {share:.2f}元')

# 3. 查无分成的合同（owner独享100%）
print('\n=== 无分成的合同（owner独享100%）===')
cur.execute("""
    SELECT c.id, c.contract_name, c.total_amt, c.owner_id, c.sign_date, c.is_framework
    FROM contracts c
    WHERE c.sign_date LIKE ?
    AND c.id NOT IN (SELECT DISTINCT contract_id FROM contract_commissions)
    ORDER BY c.sign_date
""", (f'{today_y}-%',))
for r in cur.fetchall():
    print(f'  合同ID={r["id"]} {r["contract_name"]} total={r["total_amt"]} owner={r["owner_id"]} sign={r["sign_date"]} fw={r["is_framework"]}')

# 4. 按销售人员汇总累计实际
print('\n=== 按销售汇总累计实际（1~12月）===')
# 普通合同+合同级分成
cur.execute("""
    SELECT cc.username,
           SUM(c.total_amt * cc.ratio / 100.0) as share_amt
    FROM contracts c
    JOIN contract_commissions cc ON c.id = cc.contract_id
    WHERE c.sign_date >= ? AND c.sign_date <= ?
    AND COALESCE(c.is_framework, 0) = 0
    GROUP BY cc.username
""", (f'{today_y}-01-01', f'{today_y}-12-31'))
normal_share = {r['username']: float(r['share_amt'] or 0) for r in cur.fetchall()}

# 普通合同无分成
cur.execute("""
    SELECT c.owner_id as username, SUM(c.total_amt) as solo_amt
    FROM contracts c
    WHERE c.sign_date >= ? AND c.sign_date <= ?
    AND c.id NOT IN (SELECT DISTINCT contract_id FROM contract_commissions)
    AND COALESCE(c.is_framework, 0) = 0
    GROUP BY c.owner_id
""", (f'{today_y}-01-01', f'{today_y}-12-31'))
normal_solo = {r['username']: float(r['solo_amt'] or 0) for r in cur.fetchall()}

# 框架合同+验收级分成
cur.execute("""
    SELECT ac.username,
           SUM(ca.acceptance_amount * ac.ratio / 100.0) as acc_share_amt
    FROM contract_acceptances ca
    JOIN contracts c ON ca.contract_id = c.id
    JOIN acceptance_commissions ac ON ca.id = ac.acceptance_id
    WHERE ca.acceptance_date >= ? AND ca.acceptance_date <= ?
    AND COALESCE(c.is_framework, 0) = 1
    GROUP BY ac.username
""", (f'{today_y}-01-01', f'{today_y}-12-31'))
fw_acc_share = {r['username']: float(r['acc_share_amt'] or 0) for r in cur.fetchall()}

# 框架合同+合同级分成（无验收级分成）
cur.execute("""
    SELECT cc.username,
           SUM(ca.acceptance_amount * cc.ratio / 100.0) as fw_contract_share
    FROM contract_acceptances ca
    JOIN contracts c ON ca.contract_id = c.id
    JOIN contract_commissions cc ON c.id = cc.contract_id
    WHERE ca.acceptance_date >= ? AND ca.acceptance_date <= ?
    AND COALESCE(c.is_framework, 0) = 1
    AND ca.id NOT IN (SELECT DISTINCT acceptance_id FROM acceptance_commissions)
    GROUP BY cc.username
""", (f'{today_y}-01-01', f'{today_y}-12-31'))
fw_contract_share = {r['username']: float(r['fw_contract_share'] or 0) for r in cur.fetchall()}

# 框架合同无分成
cur.execute("""
    SELECT c.owner_id as username, SUM(ca.acceptance_amount) as fw_solo_amt
    FROM contract_acceptances ca
    JOIN contracts c ON ca.contract_id = c.id
    WHERE ca.acceptance_date >= ? AND ca.acceptance_date <= ?
    AND c.id NOT IN (SELECT DISTINCT contract_id FROM contract_commissions)
    AND ca.id NOT IN (SELECT DISTINCT acceptance_id FROM acceptance_commissions)
    AND COALESCE(c.is_framework, 0) = 1
    GROUP BY c.owner_id
""", (f'{today_y}-01-01', f'{today_y}-12-31'))
fw_solo = {r['username']: float(r['fw_solo_amt'] or 0) for r in cur.fetchall()}

# 汇总
all_users = set(list(normal_share.keys()) + list(normal_solo.keys()) + list(fw_acc_share.keys()) + list(fw_contract_share.keys()) + list(fw_solo.keys()))
for u in sorted(all_users):
    total = normal_share.get(u, 0) + normal_solo.get(u, 0) + fw_acc_share.get(u, 0) + fw_contract_share.get(u, 0) + fw_solo.get(u, 0)
    print(f'  {u}: 普通_分成={normal_share.get(u,0):.2f} + 普通_独享={normal_solo.get(u,0):.2f} + 框架_验收分成={fw_acc_share.get(u,0):.2f} + 框架_合同分成={fw_contract_share.get(u,0):.2f} + 框架_独享={fw_solo.get(u,0):.2f} = {total:.2f}')

conn.close()
