import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from pathlib import Path
for line in Path(os.path.join(os.path.dirname(__file__), '..', '.env')).read_text(encoding='utf-8').splitlines():
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
from db import open_db
db = open_db()
cur = db.cursor()
# 查这个合同
cur.execute("SELECT id, contract_name, contract_no, total_amt, paid_amt, income, tax_amount FROM contracts WHERE contract_name LIKE '%遥感数据处理与应用服务%'")
for r in cur.fetchall():
    print(f"contract id={r['id']} name={r['contract_name']} total={r['total_amt']} paid={r['paid_amt']} income={r['income']} tax={r['tax_amount']}")
    # 查它的验收记录
    cid = r['id']
    cur.execute("SELECT SUM(acceptance_amount) as acc_sum, COUNT(*) as cnt FROM contract_acceptances WHERE contract_id=?", (cid,))
    a = cur.fetchone()
    print(f"  acceptances: sum={a['acc_sum']} count={a['cnt']}")
    # 新逻辑 pending
    accepted = a['acc_sum'] or 0
    pending_new = max(0, accepted - (r['paid_amt'] or 0))
    print(f"  new pending (accepted-paid) = {pending_new}")
    # 旧逻辑 pending
    pending_old = max(0, (r['total_amt'] or 0) - (r['paid_amt'] or 0))
    print(f"  old pending (total-paid) = {pending_old}")
cur.close()
db.close()
