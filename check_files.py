import sqlite3
import os

conn = sqlite3.connect('crm_app.db')
cursor = conn.cursor()

cursor.execute("SELECT id, contract_name, contract_file_path, tech_agreement_file_path FROM contracts WHERE contract_file_path IS NOT NULL OR tech_agreement_file_path IS NOT NULL LIMIT 5")
rows = cursor.fetchall()

print("合同文件路径信息:")
for row in rows:
    print(f"\nID={row[0]}")
    print(f"  合同名称: {row[1]}")
    print(f"  合同文件路径: {row[2]}")
    print(f"  技术协议路径: {row[3]}")
    
    if row[2]:
        full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), row[2])
        print(f"  合同文件完整路径: {full_path}")
        print(f"  文件存在: {os.path.exists(full_path)}")
    
    if row[3]:
        full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), row[3])
        print(f"  技术协议完整路径: {full_path}")
        print(f"  文件存在: {os.path.exists(full_path)}")

conn.close()

print("\n上传目录内容:")
upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
if os.path.exists(upload_dir):
    for f in os.listdir(upload_dir):
        print(f"  {f}")
else:
    print(f"  上传目录不存在: {upload_dir}")
