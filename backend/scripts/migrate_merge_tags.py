# -*- coding: utf-8 -*-
"""三模块合并迁移脚本：keywords + capabilities → business_tags

幂等执行：重复运行不会产生重复数据（按名称+parent_id 去重）。
迁完后将 keywords / capabilities 表中的记录 enabled=0 标记禁用（表保留不删）。
"""
import sys, os, json

_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_BASE, 'backend'))
from dotenv import load_dotenv
load_dotenv(os.path.join(_BASE, '.env'))
os.chdir(os.path.join(_BASE, 'backend'))

from db import open_db


def _parse(val):
    if not val:
        return []
    try:
        if isinstance(val, str) and val.startswith('['):
            return json.loads(val)
        if isinstance(val, str):
            return [x.strip() for x in val.split(',') if x.strip()]
        return list(val) if isinstance(val, (list, tuple)) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _find_or_create_tag(db, name, parent_id=None, level=1):
    """按 name+parent_id 查找已有标签，不存在则创建。返回 tag id。"""
    existing = db.execute(
        "SELECT id FROM business_tags WHERE name=? AND COALESCE(parent_id,-1)=COALESCE(?,-1)",
        (name, parent_id)
    ).fetchone()
    if existing:
        return existing['id']
    cur = db.execute(
        "INSERT INTO business_tags (parent_id, name, level, synonyms, related_words, exclude_words, sort_order, is_active) "
        "VALUES (?, ?, ?, '[]', '[]', '[]', 0, 1)",
        (parent_id, name, level)
    )
    return cur.lastrowid


def migrate_keywords(db):
    """keywords 表 → business_tags 叶子节点。"""
    # 1. 迁移 keyword_groups 三级树
    groups = db.execute("SELECT id, name, parent_id, level FROM keyword_groups ORDER BY level, id").fetchall()
    group_map = {}  # old group_id → new business_tag_id
    for g in groups:
        new_parent = group_map.get(g['parent_id']) if g['parent_id'] else None
        level = g['level'] if g['level'] else 1
        tid = _find_or_create_tag(db, g['name'], new_parent, level)
        group_map[g['id']] = tid

    # 2. 迁移 keywords 叶子
    kws = db.execute("SELECT id, group_id, keyword, synonyms, exclude_words, enabled FROM keywords").fetchall()
    migrated = 0
    for kw in kws:
        parent_id = group_map.get(kw['group_id']) if kw['group_id'] else None
        parent_level = 1
        if parent_id:
            prow = db.execute("SELECT level FROM business_tags WHERE id=?", (parent_id,)).fetchone()
            parent_level = prow['level'] if prow else 1
        name = (kw['keyword'] or '').strip()
        if not name:
            continue
        existing = db.execute(
            "SELECT id FROM business_tags WHERE name=? AND COALESCE(parent_id,-1)=COALESCE(?,-1)",
            (name, parent_id)
        ).fetchone()
        if existing:
            tid = existing['id']
        else:
            cur = db.execute(
                "INSERT INTO business_tags (parent_id, name, level, synonyms, related_words, exclude_words, sort_order, is_active) "
                "VALUES (?, ?, ?, ?, '[]', ?, 0, ?)",
                (parent_id, name, parent_level + 1,
                 json.dumps(_parse(kw['synonyms']), ensure_ascii=False),
                 json.dumps(_parse(kw['exclude_words']), ensure_ascii=False),
                 1 if kw['enabled'] else 0)
            )
            tid = cur.lastrowid
        migrated += 1

    # 3. 禁用 keywords 表
    db.execute("UPDATE keywords SET enabled=0 WHERE enabled=1")
    print(f"[migrate_keywords] 迁移 {migrated} 条关键词 → business_tags，已禁用 keywords 表")
    return migrated


def migrate_capabilities(db):
    """capabilities 表 → business_tags（带 capability_level 等字段）。"""
    caps = db.execute(
        "SELECT id, name, level, description, products, solutions, cases, "
        "keywords, synonyms, related_industries, enabled FROM capabilities"
    ).fetchall()
    migrated = 0
    for cap in caps:
        name = (cap['name'] or '').strip()
        if not name:
            continue
        existing = db.execute(
            "SELECT id FROM business_tags WHERE name=? AND parent_id IS NULL", (name,)
        ).fetchone()
        if existing:
            tid = existing['id']
        else:
            cur = db.execute(
                "INSERT INTO business_tags (parent_id, name, level, synonyms, related_words, exclude_words, sort_order, is_active) "
                "VALUES (NULL, ?, 1, ?, ?, '[]', 0, ?)",
                (name,
                 json.dumps(_parse(cap['keywords']) + _parse(cap['synonyms']), ensure_ascii=False),
                 json.dumps(_parse(cap['related_industries']), ensure_ascii=False),
                 1 if cap['enabled'] else 0)
            )
            tid = cur.lastrowid
        # 更新能力字段
        db.execute(
            "UPDATE business_tags SET capability_level=?, capability_desc=?, products=?, solutions=?, cases=? WHERE id=?",
            (cap['level'] or 'mature',
             cap['description'] or '',
             cap['products'] or '[]',
             cap['solutions'] or '[]',
             cap['cases'] or '[]',
             tid)
        )
        migrated += 1

    # 禁用 capabilities 表
    db.execute("UPDATE capabilities SET enabled=0 WHERE enabled=1")
    print(f"[migrate_capabilities] 迁移 {migrated} 条能力 → business_tags，已禁用 capabilities 表")
    return migrated


def main():
    db = open_db()
    try:
        n_kw = migrate_keywords(db)
        n_cap = migrate_capabilities(db)
        db.commit()
        total = db.execute("SELECT COUNT(*) as c FROM business_tags").fetchone()['c']
        print(f"\n[完成] business_tags 表现有 {total} 条记录（新增 keywords {n_kw} + capabilities {n_cap}）")
    except Exception as e:
        db.rollback()
        print(f"[失败] {e}")
        raise
    finally:
        db.close()


if __name__ == '__main__':
    main()
