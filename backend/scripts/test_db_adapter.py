# -*- coding: utf-8 -*-
"""db.py 适配层单测：SQL 翻译器 + Row 行为（不依赖真实 MySQL）。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from db import translate_sql, Row


def test_placeholder():
    assert translate_sql("SELECT * FROM t WHERE id=? AND name=?", True) == \
        "SELECT * FROM t WHERE id=%s AND name=%s"
    assert translate_sql("SELECT * FROM t WHERE id=?", False) == \
        "SELECT * FROM t WHERE id=%s"


def test_question_mark_in_literal():
    # 字面量内的 ? 保留（是数据不是占位符）；字面量内 % 转义为 %%（PyMySQL 全串格式化）
    sql = "SELECT * FROM t WHERE remark LIKE '%?%' AND id=?"
    assert translate_sql(sql, True) == "SELECT * FROM t WHERE remark LIKE '%%?%%' AND id=%s"
    sql2 = "SELECT * FROM t WHERE remark LIKE '%?%'"
    assert translate_sql(sql2, False) == sql2  # 无参数时不转义，原样透传


def test_percent_escaping_with_params():
    sql = "SELECT * FROM t WHERE name LIKE ? AND DATE_FORMAT(d,'%Y-%m')=?"
    assert translate_sql(sql, True) == \
        "SELECT * FROM t WHERE name LIKE %s AND DATE_FORMAT(d,'%%Y-%%m')=%s"


def test_percent_escaping_without_params():
    # 无参数时 PyMySQL 不做 % 格式化，字面量 % 保持原样
    sql = "SELECT DATE_FORMAT(d,'%Y') FROM t"
    assert translate_sql(sql, False) == sql


def test_escaped_quote():
    sql = "UPDATE t SET a='it''s ?' WHERE id=?"
    assert translate_sql(sql, True) == "UPDATE t SET a='it''s ?' WHERE id=%s"


def test_concat_operator_untouched():
    sql = "SELECT a || '-' || b FROM t WHERE id=?"
    assert translate_sql(sql, True) == "SELECT a || '-' || b FROM t WHERE id=%s"


def test_row_semantics():
    row = Row(['id', 'name', 'total_amt'], [1, '测试', 12.5])
    assert row['id'] == 1
    assert row[0] == 1
    assert row[-1] == 12.5
    assert row['name'] == '测试'
    assert len(row) == 3
    assert list(row.keys()) == ['id', 'name', 'total_amt']
    d = dict(row)
    assert d == {'id': 1, 'name': '测试', 'total_amt': 12.5}
    assert list(row) == [1, '测试', 12.5]
    assert 'name' in row
    assert row.get('missing', 'x') == 'x'
    try:
        row['missing']
        assert False, '应抛 KeyError'
    except KeyError:
        pass
    # setitem
    row['name'] = '新值'
    assert row['name'] == '新值'


if __name__ == '__main__':
    for name, fn in sorted(list(globals().items())):
        if name.startswith('test_'):
            fn()
            print(f'PASS {name}')
    print('全部通过')
