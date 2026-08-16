"""测试：即使文件表头匹配度低，手动选择模块也有选项"""
import requests, openpyxl, io

BASE = "http://127.0.0.1:5000"

resp = requests.post(f"{BASE}/api/auth/login",
                    json={"username": "yewei", "password": "yewei123"}, timeout=10)
token = resp.json()["data"]["token"]
headers = {"Authorization": f"Bearer {token}"}

# 创建一个表头很泛的 Excel（几乎无法自动识别）
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "数据表"
ws.append(["名称", "金额", "日期", "备注"])
ws.append(["测试A", "100", "2026-08-01", "测试"])

excel_buffer = io.BytesIO()
wb.save(excel_buffer)
excel_buffer.seek(0)

files = {"file": ("vague.xlsx", excel_buffer, "application/vnd.openxmlformats-officedocument")}
r = requests.post(f"{BASE}/api/smart-import/parse", files=files, headers=headers, timeout=30)
result = r.json()

if result.get("code") == 200:
    s = result["data"]["sheets"][0]
    print(f"detected_module: {s['detected_module']}")
    print(f"module_scores count: {len(s['module_scores'])}")
    print(f"module_scores: {[(m['name'], m['score']) for m in s['module_scores']]}")
    print(f"all_field_maps keys: {list(s['all_field_maps'].keys())}")
    if len(s['module_scores']) == 6:
        print("\n[OK] 6个模块都在，手动选择有数据！")
    else:
        print(f"\n[FAIL] 只有 {len(s['module_scores'])} 个模块")
else:
    print(f"[FAIL] {result.get('message')}")
