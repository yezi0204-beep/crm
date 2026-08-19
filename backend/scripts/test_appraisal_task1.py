"""Task 1 Failing Tests：数据库迁移
TR 1.1: ensure_tables() 后 users 表含 4 个新列，monthly_targets 表存在，重复运行幂等
TR 1.2: monthly_targets (username,year,month) 唯一约束有效
"""
import sys, os, sqlite3, tempfile, shutil
import importlib

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
sys.path.insert(0, BACKEND_DIR)

tmp = tempfile.mkdtemp()
tmp_db = os.path.join(tmp, 'test_appraisal.db')
os.environ['DB_PATH'] = tmp_db
# 清理之前imported的extensions模块并重新import，以使用新DB_PATH
for m in list(sys.modules.keys()):
    if m in ('extensions', 'config', 'security', 'scheduler', 'qa_engine', 'ai_analyzer', 'vector_search'):
        del sys.modules[m]
from extensions import ensure_tables, DB_PATH as ext_db_path
assert ext_db_path == tmp_db, f'DB_PATH 未生效：期望{tmp_db}实际{ext_db_path}'

from flask import Flask
from extensions import setup_extensions
test_app = Flask(__name__)
setup_extensions(test_app)

with test_app.app_context():
    ensure_tables()

# 直接连临时DB验证
conn = sqlite3.connect(tmp_db)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# --- TR 1.1 ---
print('=== TR 1.1 ===')
cur.execute("PRAGMA table_info(users)")
cols = [r['name'] for r in cur.fetchall()]
print(f'  users 列: {cols}')
expected = ['basic_salary', 'base_performance', 'annual_target_amount', 'is_sales_override']
for c in expected:
    if c not in cols:
        raise AssertionError(f'TR1.1 FAIL: users 缺少列 {c}')
    print(f'  ✓ users.{c} 存在')

cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='monthly_targets'")
if not cur.fetchone():
    raise AssertionError('TR1.1 FAIL: monthly_targets 表不存在')
print('  ✓ monthly_targets 表存在')

# 幂等
try:
    ensure_tables()
    print('  ✓ 重复运行 ensure_tables 不报错（幂等）')
except Exception as e:
    raise AssertionError(f'TR1.1 FAIL: 重复运行报错: {e}')

# --- TR 1.2 ---
print('\n=== TR 1.2 ===')
cur.execute("""INSERT INTO monthly_targets (username, year, month, target_amount, updated_by, updated_at)
               VALUES ('testu', 2026, 8, 100000, 'admin', '2026-08-01')""")
conn.commit()
try:
    cur.execute("""INSERT INTO monthly_targets (username, year, month, target_amount, updated_by, updated_at)
                   VALUES ('testu', 2026, 8, 200000, 'admin', '2026-08-02')""")
    conn.commit()
    raise AssertionError('TR1.2 FAIL: 重复 (username,year,month) 应失败但成功')
except sqlite3.IntegrityError:
    print('  ✓ 唯一约束 (username,year,month) 生效')

conn.close()
shutil.rmtree(tmp, ignore_errors=True)
print('\n✅ Task 1 所有测试通过（Green）')
