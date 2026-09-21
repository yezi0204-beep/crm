# -*- coding: utf-8 -*-
"""一次性迁移脚本：SQLite (crm_app.db) → MySQL。

用法：
    python scripts/migrate_sqlite_to_mysql.py            # 全量迁移（目标表非空时拒绝）
    python scripts/migrate_sqlite_to_mysql.py --drop     # 先 DROP 再建，全量重迁
    python scripts/migrate_sqlite_to_mysql.py --truncate # 保 schema 清数据重拷
    python scripts/migrate_sqlite_to_mysql.py --verify-only  # 仅校验行数

流程：备份源库 → 读 schema → 生成 MySQL DDL → 建表 → 分批拷贝 →
     重置 AUTO_INCREMENT → 行数/max(id) 双边校验。
"""
import argparse
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from db import (MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT,  # noqa: E402
                MYSQL_USER, CRM_SQL_MODE)

import pymysql  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOURCE_DB = os.environ.get('DB_PATH', os.path.join(BASE_DIR, 'crm_app.db'))
BATCH = 500

# MySQL 8.0 保留字（与列名可能冲突的常用子集），用于迁移报告
MYSQL_RESERVED = {
    'ACCESSIBLE', 'ADD', 'ALL', 'ALTER', 'ANALYZE', 'AND', 'AS', 'ASC', 'ASENSITIVE',
    'BEFORE', 'BETWEEN', 'BIGINT', 'BINARY', 'BLOB', 'BOTH', 'BY', 'CALL', 'CASCADE',
    'CASE', 'CHANGE', 'CHAR', 'CHARACTER', 'CHECK', 'COLLATE', 'COLUMN', 'CONDITION',
    'CONSTRAINT', 'CONTINUE', 'CONVERT', 'CREATE', 'CROSS', 'CUBE', 'CUME_DIST',
    'CURRENT_DATE', 'CURRENT_TIME', 'CURRENT_TIMESTAMP', 'CURRENT_USER', 'CURSOR',
    'DATABASE', 'DATABASES', 'DAY_HOUR', 'DAY_MICROSECOND', 'DAY_MINUTE', 'DAY_SECOND',
    'DEC', 'DECIMAL', 'DECLARE', 'DEFAULT', 'DELAYED', 'DELETE', 'DENSE_RANK', 'DESC',
    'DESCRIBE', 'DETERMINISTIC', 'DISTINCT', 'DISTINCTROW', 'DIV', 'DOUBLE', 'DROP',
    'DUAL', 'EACH', 'ELSE', 'ELSEIF', 'EMPTY', 'ENCLOSED', 'ESCAPED', 'EXCEPT', 'EXISTS',
    'EXIT', 'EXPLAIN', 'FALSE', 'FETCH', 'FIRST_VALUE', 'FLOAT', 'FOR', 'FORCE',
    'FOREIGN', 'FROM', 'FULLTEXT', 'FUNCTION', 'GENERATED', 'GET', 'GRANT', 'GROUP',
    'GROUPING', 'GROUPS', 'HAVING', 'HIGH_PRIORITY', 'HOUR_MICROSECOND', 'HOUR_MINUTE',
    'HOUR_SECOND', 'IF', 'IGNORE', 'IN', 'INDEX', 'INFILE', 'INNER', 'INOUT',
    'INSENSITIVE', 'INSERT', 'INT', 'INTEGER', 'INTERSECT', 'INTERVAL', 'INTO',
    'IO_AFTER_GTIDS', 'IO_BEFORE_GTIDS', 'IS', 'ITERATE', 'JOIN', 'JSON_TABLE', 'KEY',
    'KEYS', 'KILL', 'LAG', 'LAST_VALUE', 'LATERAL', 'LEAD', 'LEADING', 'LEAVE', 'LEFT',
    'LIKE', 'LIMIT', 'LINEAR', 'LINES', 'LOAD', 'LOCALTIME', 'LOCALTIMESTAMP', 'LOCK',
    'LONG', 'LONGBLOB', 'LONGTEXT', 'LOOP', 'LOW_PRIORITY', 'MASTER_BIND',
    'MASTER_SSL_VERIFY_SERVER_CERT', 'MATCH', 'MAXVALUE', 'MEDIUMINT', 'MEDIUMBLOB',
    'MEDIUMTEXT', 'MIDDLEINT', 'MINUTE_MICROSECOND', 'MINUTE_SECOND', 'MOD', 'MODIFIES',
    'NATURAL', 'NOT', 'NO_WRITE_TO_BINLOG', 'NULL', 'NUMERIC', 'OF', 'ON', 'OPTIMIZE',
    'OPTIMIZER_COSTS', 'OPTION', 'OPTIONALLY', 'OR', 'ORDER', 'OUT', 'OUTER', 'OUTFILE',
    'OVER', 'PARTITION', 'PERCENT_RANK', 'PRECISION', 'PRIMARY', 'PROCEDURE', 'PURGE',
    'RANGE', 'RANK', 'READ', 'READS', 'READ_WRITE', 'REAL', 'RECURSIVE', 'REFERENCES',
    'REGEXP', 'RELEASE', 'RENAME', 'REPEAT', 'REPLACE', 'REQUIRE', 'RESIGNAL',
    'RESTRICT', 'RETURN', 'REVOKE', 'RIGHT', 'RLIKE', 'ROW', 'ROWS', 'ROW_NUMBER',
    'SCHEMA', 'SCHEMAS', 'SECOND_MICROSECOND', 'SELECT', 'SENSITIVE', 'SEPARATOR',
    'SET', 'SHOW', 'SIGNAL', 'SMALLINT', 'SPATIAL', 'SPECIFIC', 'SQL', 'SQLEXCEPTION',
    'SQLSTATE', 'SQLWARNING', 'SQL_BIG_RESULT', 'SQL_CALC_FOUND_ROWS', 'SQL_SMALL_RESULT',
    'SSL', 'STARTING', 'STORED', 'STRAIGHT_JOIN', 'SYSTEM', 'TABLE', 'TERMINATED', 'THEN',
    'TINYBLOB', 'TINYINT', 'TINYTEXT', 'TO', 'TRAILING', 'TRIGGER', 'TRUE', 'UNDO',
    'UNION', 'UNIQUE', 'UNLOCK', 'UNSIGNED', 'UPDATE', 'USAGE', 'USE', 'USING', 'UTC_DATE',
    'UTC_TIME', 'UTC_TIMESTAMP', 'VALUES', 'VARBINARY', 'VARCHAR', 'VARYING', 'VIRTUAL',
    'WHEN', 'WHERE', 'WHILE', 'WINDOW', 'WITH', 'WRITE', 'XOR', 'YEAR_MONTH', 'ZEROFILL',
}


def q(name):
    """标识符加反引号。"""
    return '`' + name.replace('`', '``') + '`'


def sql_type_affinity(decl):
    """按 SQLite 亲和规则归类声明类型：integer/text/blob/real/numeric。"""
    d = (decl or '').upper()
    if 'INT' in d:
        return 'integer'
    if 'CHAR' in d or 'CLOB' in d or 'TEXT' in d:
        return 'text'
    # 日期时间类声明（DATE/DATETIME/TIMESTAMP/TIME）→ text 亲和，保持字符串存储最兼容
    if 'DATE' in d or 'TIME' in d:
        return 'text'
    if 'BLOB' in d or d == '':
        return 'blob'
    if 'REAL' in d or 'FLOA' in d or 'DOUB' in d:
        return 'real'
    return 'numeric'


def column_mysql_type(name, decl, notnull, dflt, is_rowid_pk, reserved_hits,
                      is_in_pk=False):
    """生成单列的 MySQL 类型片段。"""
    aff = sql_type_affinity(decl)
    du = decl.upper()
    # 布尔声明列 → TINYINT(1)（应用层写 0/1）
    if 'BOOL' in du:
        base = 'TINYINT(1)'
    elif is_rowid_pk:
        base = 'BIGINT'
    elif aff == 'integer':
        base = 'BIGINT'
    elif aff in ('real', 'numeric'):
        base = 'DOUBLE'
    elif aff == 'blob':
        base = 'MEDIUMBLOB'
    else:
        # text/日期类一律走文本路径（日期保持 TEXT 最兼容）
        # 参与 PRIMARY KEY 的 TEXT 列必须指定长度（MySQL 限制），用 VARCHAR(191)
        if is_in_pk:
            base = 'VARCHAR(191)'
        elif dflt is not None:
            base = 'VARCHAR(255)'
        else:
            base = 'MEDIUMTEXT'
    if name.upper() in MYSQL_RESERVED:
        reserved_hits.append(name)
    parts = [q(name), base]
    if notnull:
        parts.append('NOT NULL')
    if is_rowid_pk:
        # rowid 别名主键 → MySQL 必须声明 AUTO_INCREMENT，否则应用层不带 id 的 INSERT 会
        # 报 1364 "Field 'id' doesn't have a default value"
        parts.append('AUTO_INCREMENT')
    if dflt is not None and not is_rowid_pk:
        if aff == 'blob':
            print(f'  [警告] BLOB 列 {name} 带默认值，已忽略默认值')
        else:
            dv = str(dflt)
            # SQLite 动态函数默认值（CURRENT_DATE 等）：MySQL 不支持字面量形式，
            # 应用层用 Python strftime 生成时间戳，不依赖 DB 默认值，此处置空
            if dv.upper() in ('CURRENT_DATE', 'CURRENT_TIME', 'CURRENT_TIMESTAMP',
                              "CURRENT_DATE()", "CURRENT_TIME()", "CURRENT_TIMESTAMP()"):
                parts.append('DEFAULT NULL')
            elif dv.upper() == 'NULL':
                parts.append('DEFAULT NULL')
            elif dv.startswith("'"):
                inner = dv[1:-1] if len(dv) >= 2 else dv
                inner = inner.replace("''", "'")
                if len(inner) > 255:
                    print(f'  [警告] 列 {name} 默认值超 255 字符，已忽略默认值')
                else:
                    parts.append(f"DEFAULT '{inner}'")
            elif aff in ('text',) and not re.fullmatch(r'-?\d+(\.\d+)?', dv):
                parts.append(f"DEFAULT '{dv}'")
            else:
                # 数字默认值；文本列上补引号（MySQL 文本列默认值须为字符串）
                if aff == 'text' or base.startswith('VARCHAR'):
                    parts.append(f"DEFAULT '{dv}'")
                else:
                    parts.append(f'DEFAULT {dv}')
    return ' '.join(parts)


def get_schema(sqlite_conn):
    """读取全部表结构：{table: {'columns': [...], 'pk': [...], 'rowid_pk': col|None,
    'indexes': [{'name','unique','columns':[...]}]}}"""
    tables = [r[0] for r in sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        'ORDER BY name')]
    schema = {}
    for t in tables:
        cols = []
        pk_cols = []
        for cid, name, decl, notnull, dflt, pk in sqlite_conn.execute(
                f'PRAGMA table_info({q(t)})'):
            if pk:
                pk_cols.append((pk, name))
            cols.append({'name': name, 'decl': decl, 'notnull': notnull,
                         'dflt': dflt, 'pk': bool(pk)})
        pk_cols.sort()
        pk_names = [n for _, n in pk_cols]
        # rowid 别名主键：单列 INTEGER PK（含 AUTOINCREMENT）
        rowid_pk = None
        ddl, = sqlite_conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (t,)).fetchone()
        if len(pk_names) == 1:
            col = next(c for c in cols if c['name'] == pk_names[0])
            if sql_type_affinity(col['decl']) == 'integer':
                rowid_pk = pk_names[0]
        indexes = []
        for seq, iname, unique, origin, partial in sqlite_conn.execute(
                f'PRAGMA index_list({q(t)})'):
            if origin in ('pk',):  # 主键自动索引，DDL 已含
                continue
            icols = [r[2] for r in sqlite_conn.execute(f'PRAGMA index_info({q(iname)})')]
            indexes.append({'name': iname, 'unique': bool(unique), 'columns': icols})
        schema[t] = {'columns': cols, 'pk': pk_names, 'rowid_pk': rowid_pk,
                     'indexes': indexes, 'ddl': ddl or ''}
    return schema


def build_create_table(t, info, reserved_hits):
    defs = []
    for c in info['columns']:
        defs.append('  ' + column_mysql_type(
            c['name'], c['decl'], c['notnull'], c['dflt'],
            c['name'] == info['rowid_pk'], reserved_hits,
            is_in_pk=c['name'] in info['pk']))
    if info['pk']:
        defs.append('  PRIMARY KEY (' + ', '.join(q(n) for n in info['pk']) + ')')
    eng = 'ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci'
    return f"CREATE TABLE IF NOT EXISTS {q(t)} (\n" + ',\n'.join(defs) + f'\n) {eng}'


def build_indexes(t, info):
    stmts = []
    col_types = {c['name']: sql_type_affinity(c['decl']) for c in info['columns']}
    for idx in info['indexes']:
        parts = []
        for cn in idx['columns']:
            if col_types.get(cn) == 'blob':
                print(f'  [警告] 表 {t} 索引 {idx["name"]} 含 BLOB 列 {cn}，跳过')
                parts = None
                break
            if col_types.get(cn) in ('text', 'numeric'):
                parts.append(q(cn) + '(191)')
            else:
                parts.append(q(cn))
        if parts:
            u = 'UNIQUE ' if idx['unique'] else ''
            stmts.append(f'CREATE {u}INDEX {q(idx["name"])} ON {q(t)} (' + ', '.join(parts) + ')')
    return stmts


def mysql_connect(with_db=True):
    return pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE if with_db else None,
        charset='utf8mb4', autocommit=True,
        # 迁移用宽松 sql_mode：允许 SQLite 弱类型脏数据（空字符串→0 等）隐式转换，
        # 迁移后应用层用 db.py 的 CRM_SQL_MODE（STRICT）保证数据质量
        init_command="SET SESSION sql_mode=''")


def ensure_database():
    """库不存在则创建。"""
    try:
        mysql_connect().close()
        return
    except pymysql.err.OperationalError as e:
        if e.args[0] != 1049:  # Unknown database
            raise
    conn = mysql_connect(with_db=False)
    with conn.cursor() as cur:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS {q(MYSQL_DATABASE)} "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
    conn.close()
    print(f"已创建数据库 {MYSQL_DATABASE}")


def reset_auto_increment(mysql_conn, t, info):
    if not info['rowid_pk']:
        return
    with mysql_conn.cursor() as cur:
        cur.execute(f'SELECT MAX({q(info["rowid_pk"])}) FROM {q(t)}')
        row = cur.fetchone()
        nxt = (row[0] or 0) + 1
        cur.execute(f'ALTER TABLE {q(t)} AUTO_INCREMENT = {nxt}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--drop', action='store_true', help='先 DROP 已存在的表再重建')
    ap.add_argument('--truncate', action='store_true', help='保留表结构，清空后重拷')
    ap.add_argument('--verify-only', action='store_true', help='仅校验行数')
    args = ap.parse_args()

    print(f'源库: {SOURCE_DB}')
    if not os.path.exists(SOURCE_DB):
        print('源库不存在'); sys.exit(1)

    # 1. 备份源库
    bak = SOURCE_DB + '.bak_' + datetime.now().strftime('%Y%m%d_%H%M%S')
    shutil.copy2(SOURCE_DB, bak)
    print(f'已备份源库 → {bak}')

    src = sqlite3.connect(f'file:{SOURCE_DB}?mode=ro', uri=True)

    # 视图/触发器检测
    for typ, name in src.execute(
            "SELECT type, name FROM sqlite_master WHERE type IN ('view','trigger')"):
        print(f'[报告] 存在 {typ}: {name}（需人工处理）')

    schema = get_schema(src)
    print(f'共 {len(schema)} 张表')
    ensure_database()
    mysql_conn = mysql_connect()

    if args.verify_only:
        verify(src, mysql_conn, schema)
        return

    reserved_hits = []
    with mysql_conn.cursor() as cur:
        for t, info in schema.items():
            cur.execute(
                'SELECT COUNT(*) FROM information_schema.TABLES '
                'WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s', (t,))
            exists = cur.fetchone()[0]
            if exists:
                if args.drop:
                    cur.execute(f'DROP TABLE {q(t)}')
                elif args.truncate:
                    cur.execute(f'SET FOREIGN_KEY_CHECKS=0')
                    cur.execute(f'TRUNCATE TABLE {q(t)}')
                    cur.execute(f'SET FOREIGN_KEY_CHECKS=1')
                else:
                    cur.execute(f'SELECT COUNT(*) FROM {q(t)}')
                    n = cur.fetchone()[0]
                    if n:
                        print(f'[跳过] {t} 已有 {n} 行（用 --drop 或 --truncate 覆盖）')
                        continue
            cur.execute(build_create_table(t, info, reserved_hits))
            for st in build_indexes(t, info):
                try:
                    cur.execute(st)
                except pymysql.err.OperationalError as e:
                    if e.args[0] == 1061:  # duplicate key name
                        pass
                    else:
                        raise

    if reserved_hits:
        print('\n[报告] MySQL 保留字列名（应用 SQL 需加反引号）:')
        for t, hits in _by_table(schema, reserved_hits).items():
            print(f'  {t}: {", ".join(sorted(set(hits)))}')

    # 数据拷贝
    for t, info in schema.items():
        colnames = [c['name'] for c in info['columns']]
        sel = ', '.join(q(c) for c in colnames)
        rows = src.execute(f'SELECT {sel} FROM {q(t)}').fetchall()
        if not rows:
            print(f'[数据] {t}: 0 行')
            continue
        ph = ', '.join(['%s'] * len(colnames))
        insert = f'INSERT INTO {q(t)} (' + ', '.join(q(c) for c in colnames) + f') VALUES ({ph})'
        with mysql_conn.cursor() as cur:
            for i in range(0, len(rows), BATCH):
                cur.executemany(insert, rows[i:i + BATCH])
            reset_auto_increment(mysql_conn, t, info)
        print(f'[数据] {t}: {len(rows)} 行')

    verify(src, mysql_conn, schema)
    mysql_conn.close()
    src.close()
    print('\n迁移完成')


def _by_table(schema, reserved_hits):
    out = {}
    hit_set = set(reserved_hits)
    for t, info in schema.items():
        hs = [c['name'] for c in info['columns'] if c['name'] in hit_set]
        if hs:
            out[t] = hs
    return out


def verify(src, mysql_conn, schema):
    print('\n=== 校验 ===')
    bad = 0
    with mysql_conn.cursor() as cur:
        for t, info in schema.items():
            n_src = src.execute(f'SELECT COUNT(*) FROM {q(t)}').fetchone()[0]
            cur.execute(f'SELECT COUNT(*) FROM {q(t)}')
            n_dst = cur.fetchone()[0]
            pkc = info['rowid_pk'] or (info['pk'][0] if info['pk'] else None)
            ok = n_src == n_dst
            max_ok = True
            if pkc and n_src:
                m_src = src.execute(f'SELECT MAX({q(pkc)}) FROM {q(t)}').fetchone()[0]
                cur.execute(f'SELECT MAX({q(pkc)}) FROM {q(t)}')
                m_dst = cur.fetchone()[0]
                max_ok = m_src == m_dst
            status = 'OK ' if (ok and max_ok) else 'FAIL'
            if not (ok and max_ok):
                bad += 1
            print(f'[{status}] {t}: src={n_src} dst={n_dst}')
    if bad:
        print(f'\n{bad} 张表校验失败'); sys.exit(1)
    print('全部表校验通过')


if __name__ == '__main__':
    main()
