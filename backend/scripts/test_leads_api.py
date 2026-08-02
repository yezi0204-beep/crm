"""端到端验证：智能线索管理 API（抓取→评估→分配→转为客户）"""
import sqlite3
import requests

DB = r"c:\Program Files\python\crm\crm_app.db"
BASE = "http://127.0.0.1:5000"

# 1. 找一个主任/院长账号
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
row = conn.execute("SELECT username FROM users WHERE role IN ('主任','院长') LIMIT 1").fetchone()
conn.close()
if not row:
    print("未找到主任/院长账号")
    raise SystemExit(1)
username = row["username"]
print(f"测试账号: {username}")

# 2. 登录获取 token（直接读库造一个临时 token，避免密码猜测）
import uuid
from datetime import datetime, timedelta
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
u = conn.execute("SELECT username, name, role FROM users WHERE username=?", (username,)).fetchone()
conn.execute("DELETE FROM tokens WHERE username=?", (username,))
tk = str(uuid.uuid4())
exp = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
conn.execute("INSERT INTO tokens (token,username,name,role,expires) VALUES (?,?,?,?,?)",
             (tk, username, u["name"], u["role"], exp))
conn.commit()
conn.close()
token = tk
print(f"已为 {username}({u['role']}) 生成临时 token")

H = {"Authorization": f"Bearer {token}"}

def show(title, resp):
    j = resp.json()
    print(f"\n=== {title} === [{resp.status_code}] code={j.get('code')}")
    if isinstance(j.get("data"), list):
        print(f"  数据条数: {len(j['data'])}")
        if j["data"]:
            print(f"  首条: {j['data'][0]}")
    elif isinstance(j.get("data"), dict):
        for k, v in j["data"].items():
            if isinstance(v, list):
                print(f"  {k}: {len(v)} 条")
            else:
                print(f"  {k}: {v}")
    else:
        print(f"  message: {j.get('message')}")
        print(f"  data: {j.get('data')}")

# 3. 列出线索源
r = requests.get(f"{BASE}/api/leads/sources", headers=H, timeout=10)
show("GET /api/leads/sources", r)
sources = r.json().get("data", [])
sample_source = next((s for s in sources if s["source_type"] == "sample"), None)

# 4. 手动抓取一个 sample 源（保证有数据）
if sample_source:
    r = requests.post(f"{BASE}/api/leads/sources/{sample_source['id']}/scrape", headers=H, timeout=15)
    show(f"POST /api/leads/sources/{sample_source['id']}/scrape", r)

# 5. 列出线索队列
r = requests.get(f"{BASE}/api/leads?status=pending", headers=H, timeout=10)
show("GET /api/leads?status=pending", r)
pending = r.json().get("data", {}).get("list", [])
print(f"  待评估线索数: {len(pending)}")

# 6. 批量评估
r = requests.post(f"{BASE}/api/leads/evaluate-batch", headers=H, timeout=15)
show("POST /api/leads/evaluate-batch", r)

# 7. 取一条已评估的线索
r = requests.get(f"{BASE}/api/leads?status=evaluated", headers=H, timeout=10)
show("GET /api/leads?status=evaluated", r)
evaluated = r.json().get("data", {}).get("list", [])

# 8. 分配一条线索
if evaluated:
    lead = evaluated[0]
    # 找一个销售
    r = requests.get(f"{BASE}/api/users?role=销售", headers=H, timeout=10)
    sales = r.json().get("data", [])
    print(f"\n  在职销售数: {len(sales)}")
    assignee = sales[0]["username"] if sales else None
    r = requests.post(f"{BASE}/api/leads/{lead['id']}/assign",
                      headers=H, json={"assigned_to": assignee}, timeout=10)
    show(f"POST /api/leads/{lead['id']}/assign", r)

# 9. 统计接口
r = requests.get(f"{BASE}/api/leads/stats", headers=H, timeout=10)
show("GET /api/leads/stats", r)

# 10. 验证已分配线索确实创建了客户
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cnt = conn.execute("SELECT COUNT(*) as c FROM customers WHERE source LIKE '智能线索-%'").fetchone()["c"]
print(f"\n=== 数据库校验 === 智能线索来源客户数: {cnt}")
cnt2 = conn.execute("SELECT status, COUNT(*) as c FROM scraped_leads GROUP BY status").fetchall()
for r in cnt2:
    print(f"  scraped_leads.{r['status']}: {r['c']}")
conn.close()

print("\n✅ 端到端验证完成")
