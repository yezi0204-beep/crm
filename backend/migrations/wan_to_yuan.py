# -*- coding: utf-8 -*-
"""万元口径 → 元口径 数据迁移脚本。

将以下 DB 字段从"万元"存储迁移为"元"存储（*10000）：
  - competitor_profiles.win_amount
  - customer_profiles.total_budget
  - customer_profiles.avg_budget
  - contract_monthly_forecast.expected_acceptance
  - contract_monthly_forecast.expected_payment

执行方式：
  python backend/migrations/wan_to_yuan.py

幂等保护：通过 schema_migrations 表记录，已执行则跳过。
执行前务必先备份相关表（脚本会自动 mysqldump 备份）。
"""
import os
import sys
import subprocess
from datetime import datetime

# 让脚本能 import backend/db.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# 自动加载项目根目录的 .env（获取 MySQL 连接参数）
_env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
if os.path.exists(_env_path):
    with open(_env_path, encoding='utf-8') as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith('#') or '=' not in _line:
                continue
            _k, _v = _line.split('=', 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from db import open_db  # noqa: E402

# 需要迁移的字段：(表名, 字段名)
MIGRATION_FIELDS = [
    ('competitor_profiles', 'win_amount'),
    ('customer_profiles', 'total_budget'),
    ('customer_profiles', 'avg_budget'),
    ('contract_monthly_forecast', 'expected_acceptance'),
    ('contract_monthly_forecast', 'expected_payment'),
]

MIGRATION_NAME = 'wan_to_yuan_v1'


def backup_tables():
    """用 SQL 创建备份表，备份相关表数据（不依赖 mysqldump）。"""
    backup_suffix = '_backup_wan_yuan_v1'
    backup_names = []

    db = open_db()
    cursor = db.cursor()
    try:
        # 备份涉及的全部表（去重）
        tables = list(set(t for t, _ in MIGRATION_FIELDS))
        for table in tables:
            backup_name = f"{table}{backup_suffix}"
            cursor.execute(f"DROP TABLE IF EXISTS {backup_name}")
            cursor.execute(f"CREATE TABLE {backup_name} AS SELECT * FROM {table}")
            backup_names.append((table, backup_name))
        db.commit()
        print(f'[备份] 已创建备份表：{", ".join(b for _, b in backup_names)}')
        return backup_names
    except Exception as e:
        db.rollback()
        print(f'[备份] 失败：{e}')
        print('[备份] 迁移中止（无备份不迁移）')
        sys.exit(1)
    finally:
        cursor.close()
        db.close()


def ensure_migrations_table(cursor):
    """确保 schema_migrations 表存在。"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name VARCHAR(128) PRIMARY KEY,
            executed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def is_migrated(cursor):
    """检查迁移是否已执行。"""
    cursor.execute("SELECT name FROM schema_migrations WHERE name=?", (MIGRATION_NAME,))
    return cursor.fetchone() is not None


def mark_migrated(cursor):
    """记录迁移已执行。"""
    cursor.execute("INSERT INTO schema_migrations (name) VALUES (?)", (MIGRATION_NAME,))


def sample_before(cursor):
    """迁移前抽样，打印 10 行当前值，便于人肉核对。"""
    print('\n[迁移前抽样]')
    for table, field in MIGRATION_FIELDS:
        cursor.execute(f"SELECT {field} FROM {table} WHERE {field} IS NOT NULL ORDER BY id LIMIT 10")
        rows = cursor.fetchall()
        values = [r[field] for r in rows]
        print(f'  {table}.{field}: {values}')


def sample_after(cursor):
    """迁移后抽样，打印 10 行迁移后的值。"""
    print('\n[迁移后抽样]')
    for table, field in MIGRATION_FIELDS:
        cursor.execute(f"SELECT {field} FROM {table} WHERE {field} IS NOT NULL ORDER BY id LIMIT 10")
        rows = cursor.fetchall()
        values = [r[field] for r in rows]
        print(f'  {table}.{field}: {values}')


def run_migration():
    """执行迁移。"""
    backup_names = backup_tables()

    db = open_db()
    cursor = db.cursor()
    try:
        ensure_migrations_table(cursor)
        db.commit()

        if is_migrated(cursor):
            print(f'\n[跳过] 迁移 {MIGRATION_NAME} 已执行过，无需重复执行')
            print('[提示] 如需重新执行，请先 DELETE FROM schema_migrations WHERE name=%s' % MIGRATION_NAME)
            return

        sample_before(cursor)

        print('\n[迁移] 开始执行 UPDATE ...')
        affected_rows = []
        for table, field in MIGRATION_FIELDS:
            sql = f"UPDATE {table} SET {field} = ROUND({field} * 10000, 6) WHERE {field} IS NOT NULL"
            cursor.execute(sql)
            affected = cursor.rowcount
            affected_rows.append((table, field, affected))
            print(f'  {table}.{field}: 受影响 {affected} 行')

        mark_migrated(cursor)
        db.commit()

        print('\n[迁移] 提交完成')
        sample_after(cursor)

        print(f'\n[完成] 备份表：{", ".join(b for _, b in backup_names)}')
        print('[完成] 迁移记录已写入 schema_migrations 表')
        print('[回滚] 如需恢复，执行：')
        for orig, bak in backup_names:
            print(f'  DELETE FROM {orig}; INSERT INTO {orig} SELECT * FROM {bak};')

    except Exception as e:
        db.rollback()
        print(f'\n[错误] 迁移失败，已 ROLLBACK：{e}')
        print(f'[错误] 如需恢复，从备份表恢复：')
        for orig, bak in backup_names:
            print(f'  DELETE FROM {orig}; INSERT INTO {orig} SELECT * FROM {bak};')
        sys.exit(1)
    finally:
        cursor.close()
        db.close()


if __name__ == '__main__':
    run_migration()
