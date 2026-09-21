# -*- coding: utf-8 -*-
"""MySQL 数据库适配层（sqlite3 兼容接口）。

目标：业务代码沿用 sqlite3 的使用习惯（? 占位符、Row 按名/按索引取值、
conn.execute 快捷方式、显式 commit），底层替换为 PyMySQL。

对外入口：
    get_db()   请求上下文内使用：连接缓存在 Flask g，请求结束由 close_db 关闭
    open_db()  请求上下文外使用（调度器/线程池）：全新连接，调用方自行 commit + close
"""
import os
import re
import datetime
import decimal
import pymysql

from flask import g

# MySQL 连接参数（.env 注入的环境变量）
MYSQL_HOST = os.environ.get('MYSQL_HOST', '127.0.0.1')
MYSQL_PORT = int(os.environ.get('MYSQL_PORT', '3306'))
MYSQL_USER = os.environ.get('MYSQL_USER', 'crm')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
MYSQL_DATABASE = os.environ.get('MYSQL_DATABASE', 'crm')

# CRM 应用专属 sql_mode：
# - 去掉 ONLY_FULL_GROUP_BY（SQLite 宽松 GROUP BY 语义）
# - 加 PIPES_AS_CONCAT（|| 作为字符串连接符，兼容 SQLite 写法）
CRM_SQL_MODE = 'STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION,PIPES_AS_CONCAT'

_INIT_COMMAND = f"SET SESSION sql_mode='{CRM_SQL_MODE}'"


class Row:
    """兼容 sqlite3.Row 的行对象：按列名/数字索引取值、len()、keys()、dict(row)。"""

    def __init__(self, keys, values):
        self._keys = list(keys)
        self._values = list(values)

    def __getitem__(self, key):
        if isinstance(key, (int,)):
            return self._values[key]
        if isinstance(key, str):
            try:
                idx = self._keys.index(key)
            except ValueError:
                raise KeyError(f'No item with that key: {key}')
            return self._values[idx]
        raise IndexError(f'Unsupported key type: {type(key)}')

    def __setitem__(self, key, value):
        if isinstance(key, str):
            try:
                idx = self._keys.index(key)
                self._values[idx] = value
                return
            except ValueError:
                raise KeyError(f'No item with that key: {key}')
        raise IndexError(f'Unsupported key type: {type(key)}')

    def __len__(self):
        return len(self._keys)

    def keys(self):
        return list(self._keys)

    def values(self):
        return list(self._values)

    def __iter__(self):
        return iter(self._values)

    def __contains__(self, key):
        return key in self._keys

    def __repr__(self):
        pairs = ', '.join(f'{k}={v!r}' for k, v in zip(self._keys, self._values))
        return f'<Row({pairs})>'

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default


def _normalize_value(v):
    """把 PyMySQL 返回值规范为原 SQLite 习惯的 Python 类型。

    - decimal.Decimal（SUM/AVG 等聚合的固有返回类型，即使列为 double/int）
      → float：避免与 float 直接运算抛 TypeError，同时 jsonify 可直接序列化
      （与 SQLite 中 REAL/INTEGER 聚合返回 float/int 的行为对齐）
    - datetime/date（DATETIME/DATE 列）→ 'YYYY-MM-DD HH:MM:SS' / 'YYYY-MM-DD'
      字符串：全库时间戳在 SQLite 时代即按文本存取，业务代码按字符串处理
    - bytes（BLOB）保持不变（sqlite3 同样返回 bytes）
    """
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, datetime.datetime):
        return v.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(v, datetime.date):
        return v.strftime('%Y-%m-%d')
    if isinstance(v, datetime.timedelta):
        return v.total_seconds()
    return v


def _wrap_row(description, row_tuple):
    if row_tuple is None or description is None:
        return row_tuple
    keys = [d[0] for d in description]
    values = [_normalize_value(v) for v in row_tuple]
    return Row(keys, values)


def translate_sql(sql, has_params):
    """SQLite SQL → MySQL SQL 翻译。

    1. `?` 占位符 → `%s`（仅替换单引号字面量之外的 `?`，'' 转义正确处理）
    2. 有参数时，所有 `%` → `%%`（PyMySQL 对 query 执行 % 格式化，
       SQL 字面量中的 LIKE '%x%'、DATE_FORMAT('%Y-%m') 必须转义）
    3. SQLite 类型名方言：`CAST(x AS INTEGER)` → `CAST(x AS SIGNED)`
       （MySQL 的 CAST 不接受 INTEGER，周计划滚动等语句依赖此转换）
    """
    if has_params and '%' in sql:
        sql = sql.replace('%', '%%')

    if re.search(r'CAST\s*\(.*AS\s+INTEGER\s*\)', sql, re.IGNORECASE | re.DOTALL):
        sql = re.sub(r'CAST\s*\((.*?)\s+AS\s+INTEGER\s*\)',
                     r'CAST(\1 AS SIGNED)', sql, flags=re.IGNORECASE | re.DOTALL)

    if '?' in sql:
        out = []
        in_str = False
        i = 0
        n = len(sql)
        while i < n:
            ch = sql[i]
            if ch == "'" and not in_str:
                in_str = True
                out.append(ch)
            elif ch == "'" and in_str:
                # '' 是字面量内的转义引号，仍是字符串内部
                if i + 1 < n and sql[i + 1] == "'":
                    out.append("''")
                    i += 1
                else:
                    in_str = False
                    out.append("'")
            elif ch == '?' and not in_str:
                out.append('%s')
            else:
                out.append(ch)
            i += 1
        sql = ''.join(out)
    return sql


class Cursor:
    """包装 PyMySQL cursor，提供 sqlite3.Cursor 兼容行为。"""

    def __init__(self, raw_cursor):
        self._cur = raw_cursor

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def description(self):
        return self._cur.description

    def execute(self, sql, args=None):
        translated = translate_sql(sql, args is not None)
        self._cur.execute(translated, args)
        return self

    def executemany(self, sql, seq_of_args):
        translated = translate_sql(sql, True)
        self._cur.executemany(translated, seq_of_args)
        return self

    def fetchone(self):
        return _wrap_row(self._cur.description, self._cur.fetchone())

    def fetchall(self):
        return [_wrap_row(self._cur.description, r) for r in self._cur.fetchall()]

    def fetchmany(self, size=None):
        if size is None:
            rows = self._cur.fetchmany()
        else:
            rows = self._cur.fetchmany(size)
        return [_wrap_row(self._cur.description, r) for r in rows]

    def __iter__(self):
        cur = self._cur
        while True:
            row = cur.fetchone()
            if row is None:
                break
            yield _wrap_row(cur.description, row)

    def close(self):
        try:
            self._cur.close()
        except Exception:
            pass

    def setinputsizes(self, *a):
        pass

    def setoutputsize(self, *a):
        pass


class Connection:
    """包装 PyMySQL connection，提供 sqlite3.Connection 兼容行为。"""

    def __init__(self, raw_conn):
        self._conn = raw_conn

    def cursor(self, *args, **kwargs):
        return Cursor(self._conn.cursor())

    def execute(self, sql, args=None):
        """sqlite3 快捷方式：执行并返回可取数的 cursor。"""
        cur = self.cursor()
        cur.execute(sql, args)
        return cur

    def executemany(self, sql, seq_of_args):
        cur = self.cursor()
        cur.executemany(sql, seq_of_args)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    def executescript(self, script):
        """兼容 sqlite3 executescript：按分号逐条执行（DDL/多语句脚本）。

        注意 MySQL DDL 会隐式提交；调用方须保证脚本不含 ? 参数。
        """
        cur = self.cursor()
        try:
            for statement in script.split(';'):
                stmt = statement.strip()
                if not stmt:
                    continue
                # 去掉 SQLite 方言残留，避免脚本级建表报错
                stmt = _strip_sqlite_dialect(stmt)
                cur.execute(stmt)
        finally:
            cur.close()

    # with conn: 成功提交 / 异常回滚（对齐 sqlite3.Connection 行为，不关闭连接）
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False

    def ping(self, reconnect=True):
        self._conn.ping(reconnect=reconnect)


def _strip_sqlite_dialect(stmt):
    """executescript 中的 SQLite 方言残留清理（大小写不敏感的前缀替换）。"""
    stmt = re.sub(r'AUTOINCREMENT', '', stmt, flags=re.IGNORECASE)
    return stmt


def _connect():
    """创建新的 MySQL 连接（内部函数）。"""
    raw = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset='utf8mb4',
        autocommit=False,
        init_command=_INIT_COMMAND,
        connect_timeout=10,
        read_timeout=120,
        write_timeout=120,
    )
    return Connection(raw)


def open_db():
    """请求上下文外获取新连接（调度器/线程池）。调用方自行 commit + close。"""
    return _connect()


def get_db():
    """请求上下文内获取连接：首次访问创建并缓存到 g.db。

    生命周期与原 sqlite3 版完全一致：teardown_appcontext(close_db) 关闭。
    """
    if 'db' not in g:
        g.db = _connect()
    return g.db


def close_db(error=None):
    if hasattr(g, 'db'):
        try:
            g.db.close()
        except Exception:
            pass


def table_columns(cursor, table):
    """兼容 PRAGMA table_info(t)：返回列名列表（按序）。

    cursor 可以是 Cursor 或 PyMySQL 原生 cursor。
    """
    cur = cursor._cur if isinstance(cursor, Cursor) else cursor
    cur.execute(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s "
        "ORDER BY ORDINAL_POSITION",
        (table,),
    )
    return [r[0] for r in cur.fetchall()]


def table_exists(cursor, table):
    cur = cursor._cur if isinstance(cursor, Cursor) else cursor
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
        (table,),
    )
    return cur.fetchone()[0] > 0
