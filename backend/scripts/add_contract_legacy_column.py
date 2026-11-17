# -*- coding: utf-8 -*-
"""为 contracts 表新增 is_legacy（历史合同标记）列。幂等，可重复执行。

历史合同：负责人已离职或挂靠不合理的历史存量合同，
在合同列表单独筛选展示，且不计入个人业绩统计。
"""
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

try:
    cur.execute("ALTER TABLE contracts ADD COLUMN is_legacy TINYINT NOT NULL DEFAULT 0")
    print('  + contracts.is_legacy')
except pymysql.err.MySQLError as e:
    if e.args[0] == 1060:  # Duplicate column name
        print('  = contracts.is_legacy (already exists)')
    else:
        print(f'  ! contracts.is_legacy ERROR: {e}')
        raise

conn.close()
print('done')
