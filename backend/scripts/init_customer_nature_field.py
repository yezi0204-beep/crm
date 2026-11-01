# -*- coding: utf-8 -*-
"""初始化客户性质（customer_nature）自定义字段。

两金明细表需要按客户性质分类（6 类）：
  国内地方客户-地方国企 / 国内地方客户-政府 / 国内地方客户-民企 /
  国内地方客户-其它事业单位 / 集团内 / 子集团内

通过 custom_fields 元数据驱动，前端 Customers.vue 已自动渲染 select 类型字段。

幂等：已存在则跳过。
"""
import json
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

OPTIONS = ['国内地方客户-地方国企', '国内地方客户-政府', '国内地方客户-民企',
           '国内地方客户-其它事业单位', '集团内', '子集团内']


def main():
    db = open_db()
    cur = db.cursor()
    cur.execute(
        "SELECT id FROM custom_fields WHERE object_type='customer' AND field_key='customer_nature'")
    row = cur.fetchone()
    if row:
        print(f'customer_nature 字段已存在 id={row[0]}，跳过')
    else:
        cur.execute("""
            INSERT INTO custom_fields (object_type, field_key, field_name, field_type,
                options, required, sort_order, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, ('customer', 'customer_nature', '客户性质（两金分类）', 'select',
              json.dumps(OPTIONS, ensure_ascii=False), 0, 90))
        db.commit()
        print(f'已插入 customer_nature 字段 id={cur.lastrowid}')
    db.close()


if __name__ == '__main__':
    main()
