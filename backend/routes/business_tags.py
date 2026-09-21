"""业务标签管理（三级树）

标签体系完全由数据库驱动（business_tags 表），管理员可在后台：
  新增/修改/删除标签；配置同义词（匹配命中扩展）、关联词（备用弱信号）、排除词（过滤误报）。

路由（管理权限：intel.keywords）：
  GET    /api/business-tags          树形全量（含停用，管理视图）
  POST   /api/business-tags          新增标签
  PUT    /api/business-tags/<id>     修改标签
  DELETE /api/business-tags/<id>     删除标签（有子节点时拒绝）

匹配器（供情报采集使用）：
  load_tag_matcher(db) -> (tag_map, exclude_list)
    tag_map: {词(标签名/同义词, 小写): "一级/二级/三级"}，用于内容命中归入标签路径
    exclude_list: 全部标签排除词（小写），命中即丢弃
"""
import json

from flask import request, jsonify

from extensions import get_db, token_required, require_permission, record_operation_log

from . import business_tags_bp


# ==================== 工具 ====================

def _parse_list(text):
    """JSON 数组字段解析，兼容空值与脏数据。"""
    if not text:
        return []
    try:
        v = json.loads(text)
        return v if isinstance(v, list) else []
    except Exception:
        return []


def _tag_path(row, by_id):
    """根据 parent 链构建 '一级/二级/三级' 路径。"""
    names, node, depth = [], row, 0
    while node is not None and depth < 4:
        names.append(node['name'])
        pid = node['parent_id']
        node = by_id.get(pid) if pid else None
        depth += 1
    return '/'.join(reversed(names))


def load_tag_matcher(db):
    """构建标签匹配器（供 intelligence 采集过滤 + 能力匹配使用）。

    返回 (tag_map, exclude_list, has_tags, capabilities)：
    - tag_map: {词小写: 标签路径}，词 = 标签名 + 同义词 + related_words
    - exclude_list: 全部排除词小写
    - has_tags: 是否存在启用标签（False 时调用方回退旧关键词逻辑）
    - capabilities: 能力标签列表（capability_level 非空），供 capability_matcher 使用
    """
    rows = db.execute(
        "SELECT id, parent_id, name, synonyms, related_words, exclude_words, "
        "capability_level, capability_desc, products, solutions, cases "
        "FROM business_tags WHERE is_active=1"
    ).fetchall()
    if not rows:
        return {}, [], False, []
    by_id = {r['id']: r for r in rows}
    tag_map, exclude_list, capabilities = {}, [], []
    for r in rows:
        path = _tag_path(r, by_id)
        words = [r['name']] + _parse_list(r['synonyms']) + _parse_list(r['related_words'])
        for w in words:
            w = (w or '').strip()
            if w and w.lower() not in tag_map:
                tag_map[w.lower()] = path
        for w in _parse_list(r['exclude_words']):
            w = (w or '').strip()
            if w and w.lower() not in exclude_list:
                exclude_list.append(w.lower())
        if r['capability_level']:
            capabilities.append({
                'id': r['id'],
                'name': r['name'],
                'level': r['capability_level'],
                'description': r['capability_desc'] or '',
                'products': _parse_list(r['products']),
                'solutions': _parse_list(r['solutions']),
                'cases': _parse_list(r['cases']),
                'synonyms': _parse_list(r['synonyms']),
                'related_words': _parse_list(r['related_words']),
            })
    return tag_map, exclude_list, True, capabilities


# ==================== 接口 ====================

@business_tags_bp.route('/api/business-tags', methods=['GET'])
@require_permission('intel.keywords')
def list_tags():
    db = get_db()
    rows = db.execute("""
        SELECT id, parent_id, name, level, synonyms, related_words, exclude_words,
               sort_order, is_active, created_at, updated_at,
               capability_level, capability_desc, products, solutions, cases
        FROM business_tags ORDER BY level, sort_order, id
    """).fetchall()
    by_id = {r['id']: r for r in rows}
    nodes = {}
    roots = []
    for r in rows:
        nodes[r['id']] = {
            'id': r['id'], 'parent_id': r['parent_id'], 'name': r['name'],
            'level': r['level'], 'synonyms': _parse_list(r['synonyms']),
            'related_words': _parse_list(r['related_words']),
            'exclude_words': _parse_list(r['exclude_words']),
            'sort_order': r['sort_order'], 'is_active': bool(r['is_active']),
            'path': _tag_path(r, by_id),
            'capability_level': r['capability_level'] or '',
            'capability_desc': r['capability_desc'] or '',
            'products': _parse_list(r['products']),
            'solutions': _parse_list(r['solutions']),
            'cases': _parse_list(r['cases']),
            'children': []
        }
    for r in rows:
        node = nodes[r['id']]
        if r['parent_id'] and r['parent_id'] in nodes:
            nodes[r['parent_id']]['children'].append(node)
        else:
            roots.append(node)
    return jsonify({'code': 200, 'message': 'success', 'data': roots})


@business_tags_bp.route('/api/business-tags', methods=['POST'])
@require_permission('intel.keywords')
def create_tag():
    payload = request.current_user
    body = request.get_json(silent=True) or {}
    name = (body.get('name') or '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '标签名称不能为空', 'data': None})
    parent_id = body.get('parent_id')
    synonyms = body.get('synonyms') or []
    related_words = body.get('related_words') or []
    exclude_words = body.get('exclude_words') or []
    sort_order = int(body.get('sort_order', 0) or 0)
    is_active = 1 if body.get('is_active', True) else 0
    capability_level = (body.get('capability_level') or '').strip() or None
    if capability_level and capability_level not in ('mature', 'growing', 'learning', 'normal'):
        return jsonify({'code': 400, 'message': '能力等级无效（mature/growing/learning/normal）', 'data': None})
    capability_desc = body.get('capability_desc') or ''
    products = body.get('products') or []
    solutions = body.get('solutions') or []
    cases = body.get('cases') or []

    db = get_db()
    level = 1
    if parent_id:
        parent = db.execute("SELECT id, level FROM business_tags WHERE id=?", (parent_id,)).fetchone()
        if not parent:
            return jsonify({'code': 400, 'message': '上级标签不存在', 'data': None})
        if parent['level'] >= 3:
            return jsonify({'code': 400, 'message': '最多支持三级标签', 'data': None})
        level = parent['level'] + 1
    dup = db.execute(
        "SELECT id FROM business_tags WHERE name=? AND COALESCE(parent_id,-1)=COALESCE(?,-1)",
        (name, parent_id)).fetchone()
    if dup:
        return jsonify({'code': 400, 'message': '同级下已存在同名标签', 'data': None})

    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO business_tags (parent_id, name, level, synonyms, related_words, exclude_words,
                                   sort_order, is_active, capability_level, capability_desc, products, solutions, cases)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (parent_id, name, level,
          json.dumps(synonyms, ensure_ascii=False),
          json.dumps(related_words, ensure_ascii=False),
          json.dumps(exclude_words, ensure_ascii=False),
          sort_order, is_active,
          capability_level, capability_desc,
          json.dumps(products, ensure_ascii=False),
          json.dumps(solutions, ensure_ascii=False),
          json.dumps(cases, ensure_ascii=False)))
    db.commit()
    record_operation_log(payload['username'], '新增', '业务标签', f'{name}')
    return jsonify({'code': 200, 'message': 'success', 'data': {'id': cursor.lastrowid}})


@business_tags_bp.route('/api/business-tags/<int:tag_id>', methods=['PUT'])
@require_permission('intel.keywords')
def update_tag(tag_id):
    payload = request.current_user
    body = request.get_json(silent=True) or {}
    db = get_db()
    row = db.execute("SELECT * FROM business_tags WHERE id=?", (tag_id,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '标签不存在', 'data': None})

    name = (body.get('name') or row['name']).strip()
    if not name:
        return jsonify({'code': 400, 'message': '标签名称不能为空', 'data': None})
    # 禁止把自己挂到自己的子孙上（防环）
    parent_id = body.get('parent_id', row['parent_id'])
    if parent_id:
        pid = parent_id
        depth = 0
        while pid and depth < 4:
            if pid == tag_id:
                return jsonify({'code': 400, 'message': '上级标签不能是自己或自己的子级', 'data': None})
            prow = db.execute("SELECT parent_id FROM business_tags WHERE id=?", (pid,)).fetchone()
            pid = prow['parent_id'] if prow else None
            depth += 1
    level = 1
    if parent_id:
        parent = db.execute("SELECT level FROM business_tags WHERE id=?", (parent_id,)).fetchone()
        if not parent:
            return jsonify({'code': 400, 'message': '上级标签不存在', 'data': None})
        level = parent['level'] + 1

    cursor = db.cursor()
    cap_level = (body.get('capability_level') or '').strip() or None
    if cap_level and cap_level not in ('mature', 'growing', 'learning', 'normal'):
        return jsonify({'code': 400, 'message': '能力等级无效（mature/growing/learning/normal）', 'data': None})
    cursor.execute("""
        UPDATE business_tags SET name=?, parent_id=?, level=?, synonyms=?, related_words=?,
                                 exclude_words=?, sort_order=?, is_active=?,
                                 capability_level=?, capability_desc=?, products=?, solutions=?, cases=?,
                                 updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (name, parent_id, level,
          json.dumps(body.get('synonyms', _parse_list(row['synonyms'])), ensure_ascii=False),
          json.dumps(body.get('related_words', _parse_list(row['related_words'])), ensure_ascii=False),
          json.dumps(body.get('exclude_words', _parse_list(row['exclude_words'])), ensure_ascii=False),
          int(body.get('sort_order', row['sort_order']) or 0),
          1 if body.get('is_active', bool(row['is_active'])) else 0,
          cap_level,
          body.get('capability_desc', row['capability_desc'] or '') or '',
          json.dumps(body.get('products', _parse_list(row['products'])), ensure_ascii=False),
          json.dumps(body.get('solutions', _parse_list(row['solutions'])), ensure_ascii=False),
          json.dumps(body.get('cases', _parse_list(row['cases'])), ensure_ascii=False),
          tag_id))
    db.commit()
    record_operation_log(payload['username'], '修改', '业务标签', f'{name}')
    return jsonify({'code': 200, 'message': 'success', 'data': None})


@business_tags_bp.route('/api/business-tags/<int:tag_id>', methods=['DELETE'])
@require_permission('intel.keywords')
def delete_tag(tag_id):
    payload = request.current_user
    db = get_db()
    row = db.execute("SELECT name FROM business_tags WHERE id=?", (tag_id,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '标签不存在', 'data': None})
    child = db.execute("SELECT id FROM business_tags WHERE parent_id=? LIMIT 1", (tag_id,)).fetchone()
    if child:
        return jsonify({'code': 400, 'message': '该标签下存在子标签，请先删除子标签', 'data': None})
    cursor = db.cursor()
    cursor.execute("DELETE FROM business_tags WHERE id=?", (tag_id,))
    db.commit()
    record_operation_log(payload['username'], '删除', '业务标签', f"{row['name']}")
    return jsonify({'code': 200, 'message': 'success', 'data': None})


def register_routes(app):
    _ensure_columns()
    app.register_blueprint(business_tags_bp)


def _ensure_columns():
    """启动时确保 business_tags 表有能力模型合并新增的列（幂等 ALTER）。"""
    from db import open_db
    conn = None
    try:
        conn = open_db()
        cur = conn.cursor()
        cur.execute("SHOW COLUMNS FROM business_tags LIKE 'capability_level'")
        if not cur.fetchone():
            for stmt in [
                "ALTER TABLE business_tags ADD COLUMN capability_level VARCHAR(20) NULL",
                "ALTER TABLE business_tags ADD COLUMN capability_desc TEXT NULL",
                "ALTER TABLE business_tags ADD COLUMN products MEDIUMTEXT NULL",
                "ALTER TABLE business_tags ADD COLUMN solutions MEDIUMTEXT NULL",
                "ALTER TABLE business_tags ADD COLUMN cases MEDIUMTEXT NULL",
            ]:
                cur.execute(stmt)
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
