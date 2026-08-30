"""关键词管理 API：三级分类（民品/军品 → 业务领域 → 具体关键词）。

支持关键词、同义词、关联词、排除词和业务标签，后台可配置。
"""
from flask import Blueprint, request, jsonify
from extensions import get_db, token_required, admin_required, record_operation_log
import json

keywords_bp = Blueprint('keywords', __name__)


def register_routes(app):
    app.register_blueprint(keywords_bp, url_prefix='/api/keywords')


@keywords_bp.route('/groups', methods=['GET'])
@token_required
def list_groups():
    """获取关键词分组树（三级分类）。"""
    db = get_db()
    rows = db.execute("""
        SELECT id, name, parent_id, level, sort_order
        FROM keyword_groups ORDER BY level, sort_order, id
    """).fetchall()
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
    """新建关键词分组。"""
    data = request.get_json(force=True)
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '分组名称不能为空'})
    parent_id = data.get('parent_id')
    level = data.get('level', 2)
    sort_order = data.get('sort_order', 0)
    db = get_db()
    cursor = db.execute(
        "INSERT INTO keyword_groups (name, parent_id, level, sort_order) VALUES (?, ?, ?, ?)",
        (name, parent_id, level, sort_order)
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
    db = get_db()
    db.execute("UPDATE keyword_groups SET name=? WHERE id=?", (name, gid))
    db.commit()
    record_operation_log(request.current_user, 'update', 'keyword_groups', f'编辑分组:{gid}')
    return jsonify({'code': 200, 'message': '已更新'})


@keywords_bp.route('/groups/<int:gid>', methods=['DELETE'])
@admin_required
def delete_group(gid):
    """删除关键词分组（级联删除子分组和关键词）。"""
    db = get_db()
    # 递归找所有子分组
    all_ids = {gid}
    changed = True
    while changed:
        changed = False
        rows = db.execute("SELECT id FROM keyword_groups WHERE parent_id IN ({})".format(
            ','.join('?' * len(all_ids))
        ), list(all_ids)).fetchall()
        for r in rows:
            if r['id'] not in all_ids:
                all_ids.add(r['id'])
                changed = True
    placeholders = ','.join('?' * len(all_ids))
    db.execute("DELETE FROM keywords WHERE group_id IN ({})".format(placeholders), list(all_ids))
    db.execute("DELETE FROM keyword_groups WHERE id IN ({})".format(placeholders), list(all_ids))
    db.commit()
    record_operation_log(request.current_user, 'delete', 'keyword_groups', f'删除分组:{gid}')
    return jsonify({'code': 200, 'message': '已删除'})


@keywords_bp.route('', methods=['GET'])
@token_required
def list_keywords():
    """关键词列表，支持按分组/搜索过滤。"""
    db = get_db()
    group_id = request.args.get('group_id', type=int)
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    offset = (page - 1) * per_page

    sql = """
        SELECT k.id, k.group_id, k.keyword, k.synonyms, k.related,
               k.exclude_words, k.business_tag, k.enabled,
               g.name as group_name, p.name as parent_name
        FROM keywords k
        LEFT JOIN keyword_groups g ON k.group_id = g.id
        LEFT JOIN keyword_groups p ON g.parent_id = p.id
        WHERE 1=1
    """
    params = []
    if group_id:
        sql += " AND k.group_id = ?"
        params.append(group_id)
    if search:
        sql += " AND (k.keyword LIKE ? OR k.synonyms LIKE ? OR k.business_tag LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])

    # 先取总数
    count_sql = f"SELECT COUNT(*) as cnt FROM ({sql})"
    total = db.execute(count_sql, params).fetchone()['cnt']

    sql += " ORDER BY k.id DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    rows = db.execute(sql, params).fetchall()
    return jsonify({
        'code': 200,
        'data': [dict(r) for r in rows],
        'total': total,
        'page': page,
        'per_page': per_page
    })


@keywords_bp.route('', methods=['POST'])
@admin_required
def create_keyword():
    """新建关键词。"""
    data = request.get_json(force=True)
    kw = (data.get('keyword') or '').strip()
    if not kw:
        return jsonify({'code': 400, 'message': '关键词不能为空'})
    db = get_db()
    cursor = db.execute("""
        INSERT INTO keywords (group_id, keyword, synonyms, related, exclude_words, business_tag, enabled)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get('group_id'), kw,
        data.get('synonyms', ''),
        data.get('related', ''),
        data.get('exclude_words', ''),
        data.get('business_tag', ''),
        1 if data.get('enabled', True) else 0
    ))
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
        UPDATE keywords SET group_id=?, keyword=?, synonyms=?, related=?, exclude_words=?, business_tag=?, enabled=?
        WHERE id=?
    """, (
        data.get('group_id'), kw,
        data.get('synonyms', ''),
        data.get('related', ''),
        data.get('exclude_words', ''),
        data.get('business_tag', ''),
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
    db.execute("DELETE FROM keywords WHERE id=?", (kid,))
    db.commit()
    record_operation_log(request.current_user, 'delete', 'keywords', f'删除关键词:{kid}')
    return jsonify({'code': 200, 'message': '已删除'})


@keywords_bp.route('/batch', methods=['POST'])
@admin_required
def batch_import():
    """批量导入关键词。格式: [{group_id, keyword, synonyms, related, exclude_words, business_tag}]"""
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
        db.execute("""
            INSERT INTO keywords (group_id, keyword, synonyms, related, exclude_words, business_tag, enabled)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (
            item.get('group_id'), kw,
            item.get('synonyms', ''),
            item.get('related', ''),
            item.get('exclude_words', ''),
            item.get('business_tag', '')
        ))
        count += 1
    db.commit()
    record_operation_log(request.current_user, 'import', 'keywords', f'批量导入{count}个关键词')
    return jsonify({'code': 200, 'message': f'已导入{count}个关键词'})


@keywords_bp.route('/export', methods=['GET'])
@token_required
def export_keywords():
    """导出所有关键词（用于前端生成搜索查询）。"""
    db = get_db()
    rows = db.execute("""
        SELECT k.keyword, k.synonyms, k.related, k.exclude_words, k.business_tag,
               g.name as group_name, p.name as category_name
        FROM keywords k
        LEFT JOIN keyword_groups g ON k.group_id = g.id
        LEFT JOIN keyword_groups p ON g.parent_id = p.id
        WHERE k.enabled = 1
    """).fetchall()
    result = []
    for r in rows:
        result.append({
            'keyword': r['keyword'],
            'synonyms': [s.strip() for s in (r['synonyms'] or '').split(',') if s.strip()],
            'related': [s.strip() for s in (r['related'] or '').split(',') if s.strip()],
            'exclude_words': [s.strip() for s in (r['exclude_words'] or '').split(',') if s.strip()],
            'business_tag': r['business_tag'],
            'group': r['group_name'],
            'category': r['category_name']
        })
    return jsonify({'code': 200, 'data': result})
