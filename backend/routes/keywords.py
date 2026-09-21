# -*- coding: utf-8 -*-
"""关键词管理 API（兼容层）。

三模块合并后关键词数据已迁入 business_tags 表。
本模块保留旧 API 路由兼容前端已有调用，内部代理到 business_tags。

GET    /api/keywords            列表（从 business_tags 读取，返回兼容格式）
POST   /api/keywords            新增（代理到 business_tags）
PUT    /api/keywords/<id>       编辑（代理到 business_tags）
DELETE /api/keywords/<id>       删除（代理到 business_tags）
GET    /api/keywords/groups     分组树（从 business_tags 树构建）
POST   /api/keywords/groups     新建分组（代理到 business_tags）
GET    /api/keywords/export     导出（从 business_tags 读取）
POST   /api/keywords/batch      批量导入（代理到 business_tags）
"""
from flask import Blueprint, request, jsonify
from extensions import get_db, token_required, admin_required, record_operation_log
from . import keywords_bp
import json

keywords_bp = Blueprint('keywords', __name__)


def register_routes(app):
    app.register_blueprint(keywords_bp, url_prefix='/api/keywords')


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


def _parse_str_field(val):
    """兼容旧 keywords 表的逗号分隔字符串字段。"""
    items = _parse(val)
    return ','.join(items) if items else ''


# ==================== 分组（树） ====================

@keywords_bp.route('/groups', methods=['GET'])
@token_required
def list_groups():
    """获取分组树（从 business_tags 树构建兼容格式）。"""
    db = get_db()
    rows = db.execute(
        "SELECT id, name, parent_id, level, sort_order, is_active "
        "FROM business_tags ORDER BY level, sort_order, id"
    ).fetchall()
    tree = _build_tree(rows)
    return jsonify({'code': 200, 'data': tree})


def _build_tree(rows):
    """构建树形结构。"""
    nodes = {r['id']: {
        'id': r['id'], 'name': r['name'], 'parent_id': r['parent_id'],
        'level': r['level'], 'sort_order': r['sort_order'], 'children': []
    } for r in rows}
    roots = []
    for r in rows:
        node = nodes[r['id']]
        if r['parent_id'] and r['parent_id'] in nodes:
            nodes[r['parent_id']]['children'].append(node)
        else:
            roots.append(node)
    return roots


@keywords_bp.route('/groups', methods=['POST'])
@admin_required
def create_group():
    """新建分组（代理到 business_tags）。"""
    data = request.get_json(force=True)
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '分组名称不能为空'})
    parent_id = data.get('parent_id')
    level = data.get('level', 2)
    sort_order = data.get('sort_order', 0)
    db = get_db()
    cursor = db.execute(
        "INSERT INTO business_tags (parent_id, name, level, synonyms, related_words, exclude_words, sort_order, is_active) "
        "VALUES (?, ?, ?, '[]', '[]', '[]', ?, 1)",
        (parent_id, name, level, sort_order)
    )
    db.commit()
    gid = cursor.lastrowid
    record_operation_log(request.current_user, 'create', 'keyword_groups', f'新建分组:{name}')
    return jsonify({'code': 200, 'data': {'id': gid, 'name': name}})


@keywords_bp.route('/groups/<int:gid>', methods=['PUT'])
@admin_required
def update_group(gid):
    """编辑关键词分组。"""
    data = request.get_json(force=True)
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '分组名称不能为空'})
    sort_order = data.get('sort_order', 0)
    parent_id = data.get('parent_id')
    db = get_db()
    db.execute(
        "UPDATE business_tags SET name=?, sort_order=?, parent_id=? WHERE id=?",
        (name, sort_order, parent_id, gid)
    )
    db.commit()
    record_operation_log(request.current_user, 'update', 'keyword_groups', f'编辑分组:{gid}')
    return jsonify({'code': 200, 'message': '已更新'})


@keywords_bp.route('/groups/<int:gid>', methods=['DELETE'])
@admin_required
def delete_group(gid):
    """删除分组（级联删除子节点）。"""
    db = get_db()
    all_ids = [gid]
    queue = [gid]
    while queue:
        current = queue.pop(0)
        children = db.execute("SELECT id FROM business_tags WHERE parent_id=?", (current,)).fetchall()
        for c in children:
            all_ids.append(c['id'])
            queue.append(c['id'])
    placeholders = ','.join('?' * len(all_ids))
    db.execute(f"DELETE FROM business_tags WHERE id IN ({placeholders})", all_ids)
    db.commit()
    record_operation_log(request.current_user, 'delete', 'keyword_groups', f'删除分组:{gid}')
    return jsonify({'code': 200, 'message': '已删除'})


# ==================== 关键词 ====================

@keywords_bp.route('', methods=['GET'])
@token_required
def list_keywords():
    """关键词列表（从 business_tags 读取，返回兼容格式）。"""
    db = get_db()
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    offset = (page - 1) * per_page

    sql = """
        SELECT t.id, t.parent_id as group_id, t.name as keyword, t.synonyms, t.related_words as related,
               t.exclude_words, '' as business_tag, t.is_active as enabled,
               p.name as group_name
        FROM business_tags t
        LEFT JOIN business_tags p ON t.parent_id = p.id
        WHERE t.capability_level IS NULL
    """
    params = []
    if search:
        sql += " AND (t.name LIKE ? OR t.synonyms LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%'])

    count_sql = f"SELECT COUNT(*) as cnt FROM ({sql}) AS sub"
    total = db.execute(count_sql, params).fetchone()['cnt']

    sql += " ORDER BY t.id DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    rows = db.execute(sql, params).fetchall()
    data = []
    for r in rows:
        d = dict(r)
        d['synonyms'] = _parse_str_field(r['synonyms'])
        d['related'] = _parse_str_field(r['related'])
        d['exclude_words'] = _parse_str_field(r['exclude_words'])
        d['enabled'] = bool(r['enabled'])
        data.append(d)
    return jsonify({
        'code': 200, 'data': data, 'total': total,
        'page': page, 'per_page': per_page
    })


@keywords_bp.route('', methods=['POST'])
@admin_required
def create_keyword():
    """新建关键词（代理到 business_tags 叶子节点）。"""
    data = request.get_json(force=True)
    kw = (data.get('keyword') or '').strip()
    if not kw:
        return jsonify({'code': 400, 'message': '关键词不能为空'})
    db = get_db()
    group_id = data.get('group_id')
    level = 1
    if group_id:
        parent = db.execute("SELECT level FROM business_tags WHERE id=?", (group_id,)).fetchone()
        level = (parent['level'] + 1) if parent else 1
    cursor = db.execute(
        "INSERT INTO business_tags (parent_id, name, level, synonyms, related_words, exclude_words, sort_order, is_active) "
        "VALUES (?, ?, ?, ?, ?, ?, 0, 1)",
        (group_id, kw, level,
         json.dumps(_parse(data.get('synonyms', '')), ensure_ascii=False),
         json.dumps(_parse(data.get('related', '')), ensure_ascii=False),
         json.dumps(_parse(data.get('exclude_words', '')), ensure_ascii=False))
    )
    db.commit()
    record_operation_log(request.current_user, 'create', 'keywords', f'新建关键词:{kw}')
    return jsonify({'code': 200, 'data': {'id': cursor.lastrowid}})


@keywords_bp.route('/<int:kid>', methods=['PUT'])
@admin_required
def update_keyword(kid):
    """编辑关键词。"""
    data = request.get_json(force=True)
    kw = (data.get('keyword') or '').strip()
    if not kw:
        return jsonify({'code': 400, 'message': '关键词不能为空'})
    db = get_db()
    db.execute("""
        UPDATE business_tags SET name=?, parent_id=?, synonyms=?, related_words=?, exclude_words=?, is_active=?
        WHERE id=?
    """, (
        kw, data.get('group_id'),
        json.dumps(_parse(data.get('synonyms', '')), ensure_ascii=False),
        json.dumps(_parse(data.get('related', '')), ensure_ascii=False),
        json.dumps(_parse(data.get('exclude_words', '')), ensure_ascii=False),
        1 if data.get('enabled', True) else 0,
        kid
    ))
    db.commit()
    record_operation_log(request.current_user, 'update', 'keywords', f'编辑关键词:{kid}')
    return jsonify({'code': 200, 'message': '已更新'})


@keywords_bp.route('/<int:kid>', methods=['DELETE'])
@admin_required
def delete_keyword(kid):
    """删除关键词。"""
    db = get_db()
    db.execute("DELETE FROM business_tags WHERE id=?", (kid,))
    db.commit()
    record_operation_log(request.current_user, 'delete', 'keywords', f'删除关键词:{kid}')
    return jsonify({'code': 200, 'message': '已删除'})


@keywords_bp.route('/batch', methods=['POST'])
@admin_required
def batch_import():
    """批量导入关键词。"""
    data = request.get_json(force=True)
    items = data.get('items', [])
    if not items:
        return jsonify({'code': 400, 'message': '无数据'})
    db = get_db()
    count = 0
    for item in items:
        kw = (item.get('keyword') or '').strip()
        if not kw:
            continue
        group_id = item.get('group_id')
        level = 1
        if group_id:
            parent = db.execute("SELECT level FROM business_tags WHERE id=?", (group_id,)).fetchone()
            level = (parent['level'] + 1) if parent else 1
        db.execute(
            "INSERT INTO business_tags (parent_id, name, level, synonyms, related_words, exclude_words, sort_order, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, 1)",
            (group_id, kw, level,
             json.dumps(_parse(item.get('synonyms', '')), ensure_ascii=False),
             json.dumps(_parse(item.get('related', '')), ensure_ascii=False),
             json.dumps(_parse(item.get('exclude_words', '')), ensure_ascii=False))
        )
        count += 1
    db.commit()
    record_operation_log(request.current_user, 'import', 'keywords', f'批量导入{count}个关键词')
    return jsonify({'code': 200, 'message': f'已导入{count}个关键词'})


@keywords_bp.route('/export', methods=['GET'])
@token_required
def export_keywords():
    """导出所有关键词（从 business_tags 读取）。"""
    db = get_db()
    rows = db.execute("""
        SELECT t.name as keyword, t.synonyms, t.related_words as related, t.exclude_words,
               p.name as group_name
        FROM business_tags t
        LEFT JOIN business_tags p ON t.parent_id = p.id
        WHERE t.capability_level IS NULL AND t.is_active = 1
    """).fetchall()
    result = []
    for r in rows:
        result.append({
            'keyword': r['keyword'],
            'synonyms': _parse(r['synonyms']),
            'related': _parse(r['related']),
            'exclude_words': _parse(r['exclude_words']),
            'business_tag': '',
            'group': r['group_name'],
            'category': ''
        })
    return jsonify({'code': 200, 'data': result})
