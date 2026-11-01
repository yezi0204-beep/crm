# -*- coding: utf-8 -*-
"""两金明细表：新建 receivable_snapshots + receivable_overrides。

- receivable_snapshots：每季度末（3/31、6/30、9/30、12/31）由 scheduler 自动
  生成快照，也可由财务角色在页面上手动重新生成。应收账款/合同资产金额、账龄、
  自动风险评级均落库，便于历史季度回看。
- receivable_overrides：每季度每合同一条人工填报记录（客户风险/回款风险/
  更新回款计划），跨季度互不污染。

幂等：使用 CREATE TABLE IF NOT EXISTS，重复执行无副作用。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), '.env')
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
except ImportError:
    pass

from db import open_db

DDL = [
    """
    CREATE TABLE IF NOT EXISTS receivable_snapshots (
      id BIGINT PRIMARY KEY AUTO_INCREMENT,
      quarter VARCHAR(8) NOT NULL,
      snapshot_date VARCHAR(10) NOT NULL,
      contract_id BIGINT NOT NULL,
      cust_id BIGINT NOT NULL,
      customer_name MEDIUMTEXT,
      customer_nature MEDIUMTEXT,
      project_name MEDIUMTEXT,
      contract_no MEDIUMTEXT,
      receivable DOUBLE,
      contract_asset DOUBLE,
      ar_date VARCHAR(19),
      aging_bucket VARCHAR(16),
      auto_risk VARCHAR(4),
      created_at VARCHAR(19),
      UNIQUE KEY uk_quarter_contract (quarter, contract_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS receivable_overrides (
      id BIGINT PRIMARY KEY AUTO_INCREMENT,
      quarter VARCHAR(8) NOT NULL,
      contract_id BIGINT NOT NULL,
      customer_nature MEDIUMTEXT,
      cust_risk VARCHAR(4),
      payback_risk VARCHAR(4),
      payback_plan MEDIUMTEXT,
      updated_by MEDIUMTEXT,
      updated_at VARCHAR(19),
      UNIQUE KEY uk_quarter_contract (quarter, contract_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
]

# 已存在表需要补充的列（幂等：先查 information_schema）
ADD_COLUMNS = [
    ('receivable_overrides', 'customer_nature', 'MEDIUMTEXT'),
    ('receivable_snapshots', 'owner_id', 'MEDIUMTEXT'),
    ('receivable_snapshots', 'owner_name', 'MEDIUMTEXT'),
]


def _ensure_columns(cur):
    for table, column, col_type in ADD_COLUMNS:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? AND COLUMN_NAME = ?",
            (table, column))
        if not cur.fetchone()[0]:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            print(f'已补充列: {table}.{column}')


def main():
    db = open_db()
    cur = db.cursor()
    for stmt in DDL:
        cur.execute(stmt)
    _ensure_columns(cur)
    db.commit()
    # 校验
    cur.execute("SHOW TABLES LIKE 'receivable_%'")
    tables = [r[0] for r in cur.fetchall()]
    print('建表完成:', tables)
    db.close()


if __name__ == '__main__':
    main()
