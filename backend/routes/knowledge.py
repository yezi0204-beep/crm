"""企业知识库模块

存储并管理 AI 生成的企业知识资产：
- 拜访复盘摘要（visit_summary）：由 /api/ai/visit-summary 自动生成并沉淀
- 跟进洞察（followup_insight）：跟进记录的结构化洞察
- 销售技巧（sales_skill）：可手动录入的经验沉淀
- 客户案例（customer_case）：成交案例归档

权限模型：主任/院长可查看全部并管理；普通用户可查看全部、仅管理自己创建的知识。
"""
import json
from flask import request, jsonify

from extensions import get_db, token_required, record_operation_log

from . import knowledge_bp


@knowledge_bp.route('/api/knowledge', methods=['GET'])
@token_required
def list_knowledge():
    """知识库列表，支持按 category / cust_id / keyword 筛选。"""
    payload = request.current_user
    category = request.args.get('category', '')
    cust_id = request.args.get('cust_id', '')
    keyword = request.args.get('keyword', '')
    visit_id = request.args.get('visit_id', '')

    db = get_db()
    cursor = db.cursor()

    conditions = []
    params = []
    if category:
        conditions.append("k.category = ?")
        params.append(category)
    if cust_id:
        conditions.append("k.cust_id = ?")
        params.append(cust_id)
    if visit_id:
        conditions.append("k.visit_id = ?")
        params.append(visit_id)
    if keyword:
        conditions.append("(k.title LIKE ? OR k.summary LIKE ? OR k.tags LIKE ? OR k.content LIKE ?)")
        kw = f'%{keyword}%'
        params.extend([kw, kw, kw, kw])

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    cursor.execute(f"""
        SELECT k.id, k.title, k.summary, k.category, k.cust_id, k.visit_id,
               k.owner_id, k.tags, k.created_at,
               c.company as customer_company, u.name as owner_name
        FROM knowledge_base k
        LEFT JOIN customers c ON k.cust_id = c.id
        LEFT JOIN users u ON k.owner_id = u.username
        {where_clause}
        ORDER BY k.created_at DESC
    """, params)
    rows = [dict(r) for r in cursor.fetchall()]

    return jsonify({'code': 200, 'message': 'success', 'data': rows})


@knowledge_bp.route('/api/knowledge/<int:kb_id>', methods=['GET'])
@token_required
def get_knowledge(kb_id):
    """知识详情（含完整 content）。"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT k.*, c.company as customer_company, u.name as owner_name
        FROM knowledge_base k
        LEFT JOIN customers c ON k.cust_id = c.id
        LEFT JOIN users u ON k.owner_id = u.username
        WHERE k.id = ?
    """, (kb_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '知识记录不存在', 'data': None})
    return jsonify({'code': 200, 'message': 'success', 'data': dict(row)})


@knowledge_bp.route('/api/knowledge', methods=['POST'])
@token_required
def create_knowledge():
    """手动创建知识记录。

    请求体：title, content, category, cust_id, visit_id, tags, summary
    """
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload.get('username', '')

    title = (data.get('title') or '').strip()
    content = data.get('content') or ''
    if not title or not content:
        return jsonify({'code': 400, 'message': '标题和内容不能为空', 'data': None})

    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO knowledge_base (title, content, category, cust_id, visit_id,
                                        owner_id, tags, summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            title, content,
            data.get('category', 'sales_skill'),
            data.get('cust_id'), data.get('visit_id'),
            username, data.get('tags'), data.get('summary'),
        ))
        db.commit()
        record_operation_log(username, '创建', '知识库', f'创建知识：{title}')
        return jsonify({'code': 200, 'message': '创建成功', 'data': {'id': cursor.lastrowid}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@knowledge_bp.route('/api/knowledge/<int:kb_id>', methods=['PUT'])
@token_required
def update_knowledge(kb_id):
    """编辑知识记录（普通用户仅能编辑自己创建的）。"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload.get('username', '')
    role = payload.get('role', '')

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT owner_id FROM knowledge_base WHERE id=?", (kb_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '知识记录不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足，只能编辑自己创建的知识', 'data': None})

    try:
        updates, params = [], []
        for field in ['title', 'content', 'category', 'cust_id', 'visit_id', 'tags', 'summary']:
            if field in data:
                updates.append(f"{field}=?")
                params.append(data[field])
        if not updates:
            return jsonify({'code': 400, 'message': '没有需要更新的字段', 'data': None})
        params.append(kb_id)
        cursor.execute(f"UPDATE knowledge_base SET {', '.join(updates)} WHERE id=?", params)
        db.commit()
        record_operation_log(username, '编辑', '知识库', f'编辑知识 ID:{kb_id}')
        return jsonify({'code': 200, 'message': '更新成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@knowledge_bp.route('/api/knowledge/<int:kb_id>', methods=['DELETE'])
@token_required
def delete_knowledge(kb_id):
    """删除知识记录（普通用户仅能删除自己创建的）。"""
    payload = request.current_user
    username = payload.get('username', '')
    role = payload.get('role', '')

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT owner_id, title FROM knowledge_base WHERE id=?", (kb_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '知识记录不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足，只能删除自己创建的知识', 'data': None})

    try:
        cursor.execute("DELETE FROM knowledge_base WHERE id=?", (kb_id,))
        db.commit()
        record_operation_log(username, '删除', '知识库', f'删除知识：{row["title"]}')
        return jsonify({'code': 200, 'message': '删除成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


def register_routes(app):
    app.register_blueprint(knowledge_bp)
