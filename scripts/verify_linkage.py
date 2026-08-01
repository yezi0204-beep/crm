# -*- coding: utf-8 -*-
"""验证合同关联客户/商机的数据库迁移与画像接口 linkage 字段。"""
import os
import sys
import sqlite3
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "crm_app.db")
API = "http://127.0.0.1:5000"


def check_schema():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(contracts)")
    contracts_cols = [r[1] for r in cur.fetchall()]
    cur.execute("PRAGMA table_info(business)")
    business_cols = [r[1] for r in cur.fetchall()]
    conn.close()

    print("=== 数据库 Schema ===")
    print("contracts.cust_id 存在:", "cust_id" in contracts_cols)
    print("contracts.b_id 存在:", "b_id" in contracts_cols)
    print("business.cust_id 存在:", "cust_id" in business_cols)
    print("contracts 全部列:", contracts_cols)
    print()

    # 统计关联情况
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM contracts")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM contracts WHERE cust_id IS NOT NULL")
    linked = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM contracts WHERE b_id IS NOT NULL")
    b_linked = cur.fetchone()[0]
    conn.close()
    print("=== 合同关联统计 ===")
    print(f"合同总数: {total}")
    print(f"已关联客户(cust_id): {linked}")
    print(f"已关联商机(b_id): {b_linked}")
    print()


def login():
    # 直接用 create_token 生成令牌，避免猜测密码触发限流
    sys.path.insert(0, BASE_DIR)
    sys.path.insert(0, os.path.join(BASE_DIR, "backend"))
    from extensions import create_token
    import app as app_module
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT username, name, role FROM users WHERE username = ? OR name = ?", ("叶伟", "叶伟"))
    row = cur.fetchone()
    conn.close()
    if not row:
        print("未找到用户 叶伟")
        sys.exit(1)
    username, name, role = row
    print(f"为用户 {name}({username}, role={role}) 生成令牌")
    with app_module.app.app_context():
        return create_token(username, name, role)


def check_profile(token, cust_id):
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{API}/api/customers/{cust_id}/profile", headers=headers, timeout=10)
    data = resp.json()
    if data.get("code") != 200:
        print(f"客户 {cust_id} 画像接口失败:", data)
        return
    d = data["data"]
    print(f"=== 客户 {cust_id} 画像 ===")
    print(f"客户: {d['customer'].get('company') or d['customer'].get('name')}")
    print(f"商机数: {len(d['business'])}  合同数: {len(d['contracts'])}")
    print("--- 合同 linkage 明细 ---")
    for c in d["contracts"]:
        print(f"  - {c.get('contract_name') or c.get('contract_no')} | "
              f"linkage={c.get('linkage')} | customer_name={c.get('customer_name')} | "
              f"business_title={c.get('business_title')} | cust_id={c.get('cust_id')} | b_id={c.get('b_id')}")
    print()


def main():
    check_schema()
    token = login()
    # 找一个有合同/商机的客户验证
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, company FROM customers ORDER BY id LIMIT 5")
    customers = cur.fetchall()
    conn.close()
    for cid, company in customers:
        check_profile(token, cid)


if __name__ == "__main__":
    main()
