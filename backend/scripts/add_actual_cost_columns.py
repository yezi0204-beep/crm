# -*- coding: utf-8 -*-
"""为 contracts 表新增实际成本列 + 为项目经理角色新增权限点。幂等，可重复执行。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dotenv import load_dotenv
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env')
load_dotenv(_env_path)

import pymysql

conn = pymysql.connect(
    host=os.environ.get('MYSQL_HOST', '127.0.0.1'),
    port=int(os.environ.get('MYSQL_PORT', '3306')),
    user=os.environ.get('MYSQL_USER', 'crm'),
    password=os.environ.get('MYSQL_PASSWORD', ''),
    database=os.environ.get('MYSQL_DATABASE', 'crm'),
    charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor, autocommit=True)
cur = conn.cursor()

# 1. 新增实际成本列
COLUMNS = [
    ('actual_cost_labor', 'REAL', 'DEFAULT 0'),
    ('actual_cost_travel', 'REAL', 'DEFAULT 0'),
    ('actual_cost_entertain', 'REAL', 'DEFAULT 0'),
    ('actual_cost_outsource', 'REAL', 'DEFAULT 0'),
    ('actual_cost_manage', 'REAL', 'DEFAULT 0'),
    ('actual_cost_tax', 'REAL', 'DEFAULT 0'),
    ('actual_cost_remark', 'TEXT', ''),
]
for col, dtype, extra in COLUMNS:
    try:
        sql = f"ALTER TABLE contracts ADD COLUMN {col} {dtype} {extra}".strip()
        cur.execute(sql)
        print(f'  + contracts.{col}')
    except pymysql.err.MySQLError as e:
        if e.args[0] == 1060:  # Duplicate column name
            print(f'  = contracts.{col} (already exists)')
        else:
            print(f'  ! contracts.{col} ERROR: {e}')
            raise

# 2. 新增权限点
PERMS = [
    ('项目经理', 'cost.view'),
    ('项目经理', 'cost.actual.manage'),
]
for role, perm in PERMS:
    try:
        cur.execute(
            "INSERT IGNORE INTO role_permissions (role_code, permission_code) VALUES (%s, %s)",
            (role, perm))
        if cur.rowcount > 0:
            print(f'  + {role} → {perm}')
        else:
            print(f'  = {role} → {perm} (already exists)')
    except pymysql.err.MySQLError as e:
        print(f'  ! {role} → {perm} ERROR: {e}')

conn.close()
print('done')
