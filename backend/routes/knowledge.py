"""基础知识库路由 - 管理知识条目CRUD。

提供知识条目的创建、查询、更新、删除接口，
支持按类别、客户、标签进行筛选。
"""
from flask import request, jsonify

from extensions import get_db, token_required, record_operation_log
from vector_search import semantic_search, index_document

from . import knowledge_bp


@knowledge_bp.route('/api/knowledge/entries', methods=['GET'])
@token_required
def get_knowledge_entries():
    """获取知识条目列表。"""
    data = request.current_user
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    category = request.args.get('category', '')
    cust_id = request.args.get('cust_id', type=int)
    owner_id = request.args.get('owner_id', '')
    keyword = request.args.get('keyword', '')

    db = get_db()
    cursor = db.cursor()

    conditions = []
    params = []

    if category:
        conditions.append("category = ?")
        params.append(category)
    if cust_id:
        conditions.append("cust_id = ?")
        params.append(cust_id)
    if owner_id:
        conditions.append("owner_id = ?")
        params.append(owner_id)
    if keyword:
        conditions.append("(title LIKE ? OR content LIKE ? OR tags LIKE ?)")
        kw = f'%{keyword}%'
        params.extend([kw, kw, kw])

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    cursor.execute(f"SELECT COUNT(*) as total FROM knowledge_base {where_clause}", params)
    total = cursor.fetchone()['total']

    offset = (page - 1) * per_page
    cursor.execute(f"""
        SELECT * FROM knowledge_base
        {where_clause}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """, params + [per_page, offset])

    entries = [dict(row) for row in cursor.fetchall()]

    return jsonify({
        'code': 200,
        'message': 'success',
        'data': {
            'items': entries,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': (total + per_page - 1) // per_page
        }
    })


@knowledge_bp.route('/api/knowledge/entries', methods=['POST'])
@token_required
def create_knowledge_entry():
    """创建知识条目。"""
    data = request.current_user
    username = data.get('username', '')
    req_data = request.get_json(silent=True) or {}

    title = req_data.get('title', '').strip()
    content = req_data.get('content', '').strip()
    category = req_data.get('category', 'visit_summary')
    cust_id = req_data.get('cust_id')
    visit_id = req_data.get('visit_id')
    tags = req_data.get('tags', '')
    summary = req_data.get('summary', '')

    if not title or not content:
        return jsonify({'code': 400, 'message': '标题和内容不能为空', 'data': None})

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        INSERT INTO knowledge_base (title, content, category, cust_id, visit_id, owner_id, tags, summary)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (title, content, category, cust_id, visit_id, username, tags, summary))
    db.commit()

    entry_id = cursor.lastrowid

    try:
        index_document(entry_id, f"{title}\n{content}")
    except Exception:
        pass

    record_operation_log(username, '创建', '知识库', f'创建知识条目：{title}')

    return jsonify({
        'code': 200,
        'message': '创建成功',
        'data': {'id': entry_id, 'title': title}
    })


@knowledge_bp.route('/api/knowledge/entries/<int:entry_id>', methods=['GET'])
@token_required
def get_knowledge_entry(entry_id):
    """获取单个知识条目详情。"""
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT * FROM knowledge_base WHERE id = ?", (entry_id,))
    entry = cursor.fetchone()
    if not entry:
        return jsonify({'code': 404, 'message': '知识条目不存在', 'data': None})

    return jsonify({
        'code': 200,
        'message': 'success',
        'data': dict(entry)
    })


@knowledge_bp.route('/api/knowledge/entries/<int:entry_id>', methods=['PUT'])
@token_required
def update_knowledge_entry(entry_id):
    """更新知识条目。"""
    data = request.current_user
    username = data.get('username', '')
    req_data = request.get_json(silent=True) or {}

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT id FROM knowledge_base WHERE id = ?", (entry_id,))
    if not cursor.fetchone():
        return jsonify({'code': 404, 'message': '知识条目不存在', 'data': None})

    fields = []
    params = []

    for field in ('title', 'content', 'category', 'cust_id', 'visit_id', 'tags', 'summary'):
        if field in req_data:
            fields.append(f"{field} = ?")
            params.append(req_data[field])

    if not fields:
        return jsonify({'code': 400, 'message': '无更新字段', 'data': None})

    params.append(entry_id)
    cursor.execute(f"UPDATE knowledge_base SET {', '.join(fields)} WHERE id = ?", params)
    db.commit()

    if 'content' in req_data or 'title' in req_data:
        try:
            title = req_data.get('title', '')
            content = req_data.get('content', '')
            cursor.execute("SELECT title, content FROM knowledge_base WHERE id = ?", (entry_id,))
            row = cursor.fetchone()
            index_document(entry_id, f"{row['title']}\n{row['content']}")
        except Exception:
            pass

    record_operation_log(username, '更新', '知识库', f'更新知识条目ID：{entry_id}')

    return jsonify({
        'code': 200,
        'message': '更新成功',
        'data': {'id': entry_id}
    })


@knowledge_bp.route('/api/knowledge/entries/<int:entry_id>', methods=['DELETE'])
@token_required
def delete_knowledge_entry(entry_id):
    """删除知识条目。"""
    data = request.current_user
    username = data.get('username', '')

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT id FROM knowledge_base WHERE id = ?", (entry_id,))
    if not cursor.fetchone():
        return jsonify({'code': 404, 'message': '知识条目不存在', 'data': None})

    cursor.execute("DELETE FROM knowledge_base WHERE id = ?", (entry_id,))
    db.commit()

    record_operation_log(username, '删除', '知识库', f'删除知识条目ID：{entry_id}')

    return jsonify({
        'code': 200,
        'message': '删除成功',
        'data': None
    })


@knowledge_bp.route('/api/knowledge/search', methods=['POST'])
@token_required
def search_knowledge():
    """语义搜索知识库。"""
    data = request.current_user
    req_data = request.get_json(silent=True) or {}

    query = req_data.get('query', '').strip()
    category = req_data.get('category')
    cust_id = req_data.get('cust_id')
    top_k = req_data.get('top_k', 10)

    if not query:
        return jsonify({'code': 400, 'message': '请提供搜索词', 'data': None})

    results = semantic_search(query, top_k=top_k)

    if category:
        results = [r for r in results if r.get('doc_type') == category]
    if cust_id:
        results = [r for r in results if r.get('cust_id') == cust_id]

    return jsonify({
        'code': 200,
        'message': 'success',
        'data': {
            'query': query,
            'results': results,
            'total': len(results)
        }
    })


@knowledge_bp.route('/api/knowledge/categories', methods=['GET'])
@token_required
def get_categories():
    """获取知识分类列表。"""
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT category, COUNT(*) as count
        FROM knowledge_base
        GROUP BY category
        ORDER BY count DESC
    """)

    categories = [dict(row) for row in cursor.fetchall()]

    return jsonify({
        'code': 200,
        'message': 'success',
        'data': categories
    })


def register_routes(app):
    app.register_blueprint(knowledge_bp)