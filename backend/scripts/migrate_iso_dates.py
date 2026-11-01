# -*- coding: utf-8 -*-
"""存量 ISO 8601 时间串清洗迁移。

背景：前端 el-date-picker 未设置 value-format 时，Date 对象经 JSON 序列化
产生 UTC 时间串（如 2026-09-28T16:00:00.000Z，即北京时间 2026-09-29 零点），
被原样存入文本日期列并在页面显示。

本脚本将以下业务列的整值 ISO 时间串统一换算为北京时间并清洗为
'YYYY-MM-DD'（零点时刻）/'YYYY-MM-DD HH:MM:SS'（非零点）：

    business.predict_date
    contracts.sign_date
    follow_logs.log_time
    payment_records.payment_date

注意：operation_logs.timestamp_utc 为数字签名 payload 组成部分，
必须保持原始 UTC 串（验签依赖），不在清洗范围；其显示格式化在
security_api._fmt_utc_display 返回层处理。

幂等：已清洗值（YYYY-MM-DD / YYYY-MM-DD HH:MM:SS）不匹配 ISO 模式，
重复执行无副作用。
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

import pymysql

# 注意：必须用原生 PyMySQL 连接。db.py 包装层的读取转换会把 ISO 串在
# SELECT 时就转为干净格式，导致读不到原始值；此处需直接读写库内原值。
from db import _normalize_iso_string, MYSQL_HOST, MYSQL_PORT, MYSQL_USER, \
    MYSQL_PASSWORD, MYSQL_DATABASE

# (表, 列)：仅清洗以下业务日期列
TARGETS = [
    ('business', 'predict_date'),
    ('contracts', 'sign_date'),
    ('follow_logs', 'log_time'),
    ('payment_records', 'payment_date'),
]


def main():
    raw = pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER,
        password=MYSQL_PASSWORD, database=MYSQL_DATABASE,
        charset='utf8mb4', autocommit=False)
    cur = raw.cursor(pymysql.cursors.DictCursor)
    cur.execute("SET SESSION sql_mode='STRICT_TRANS_TABLES'")
    total = 0
    for table, column in TARGETS:
        cur.execute(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s", (table,))
        cols = [r['COLUMN_NAME'] for r in cur.fetchall()]
        if column not in cols:
            print(f'[skip] {table}.{column}: 列不存在')
            continue
        pk = 'id' if 'id' in cols else cols[0]
        cur.execute(
            f"SELECT `{pk}` AS _pk, `{column}` AS _v FROM `{table}` "
            f"WHERE `{column}` REGEXP '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}T'")
        rows = cur.fetchall()
        fixed = skipped = 0
        for r in rows:
            old = r['_v']
            new = _normalize_iso_string(old) if isinstance(old, str) else old
            if not isinstance(new, str) or new == old:
                skipped += 1
                continue
            cur.execute(
                f"UPDATE `{table}` SET `{column}`=%s "
                f"WHERE `{pk}`=%s AND `{column}`=%s",
                (new, r['_pk'], old))
            fixed += cur.rowcount
        print(f'{table}.{column}: 匹配 {len(rows)}，更新 {fixed}，跳过 {skipped}')
        total += fixed
    raw.commit()
    raw.close()
    print(f'完成，共更新 {total} 条')


if __name__ == '__main__':
    main()
