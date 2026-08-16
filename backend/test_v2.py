import requests, json

BASE = "http://127.0.0.1:5000"

r = requests.post(f"{BASE}/api/auth/login",
                  json={"username": "yewei", "password": "yewei123"}, timeout=10)
token = r.json()["data"]["token"]
headers = {"Authorization": f"Bearer {token}"}
print("Login OK")

# 用 Python requests 的 files 参数上传
with open("vague.xlsx", "rb") as f:
    r2 = requests.post(f"{BASE}/api/smart-import/parse",
                       files={"file": ("vague.xlsx", f, "application/vnd.openxmlformats-officedocument")},
                       headers=headers, timeout=30)

result = r2.json()
if result.get("code") == 200:
    sheet = result["data"]["sheets"][0]
    print(f"detected_module: {sheet['detected_module']}")
    print(f"module_scores count: {len(sheet['module_scores'])}")
    for ms in sheet['module_scores']:
        print(f"  {ms['name']} score={ms['score']}")
    if len(sheet['module_scores']) == 6:
        print("\n[OK] 6 modules available for manual selection!")
    else:
        print(f"\n[FAIL] Only {len(sheet['module_scores'])} modules")
else:
    print(f"Error: {result.get('message')}")
