from flask import request, jsonify
from extensions import get_db, record_operation_log, token_required
from datetime import datetime

from . import quotes_bp

VALID_STATUSES = ('draft', 'sent', 'accepted', 'rejected', 'expired')


@quotes_bp.route('/api/quotes', methods=['GET'])
@token_required
def get_quotes():
    """报价单列表：支持关键字、状态、客户、商机筛选。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    keyword = request.args.get('keyword', '')
    status = request.args.get('status', '')
    cust_id = request.args.get('cust_id', '')
    b_id = request.args.get('b_id', '')

    db = get_db()
    cursor = db.cursor()

    conditions = []
    params = []

    if role not in ('主任', '院长'):
        conditions.append("q.owner_id = ?")
        params.append(username)

    if keyword:
        conditions.append("(q.quote_no LIKE ? OR q.title LIKE ?)")
        params.extend([f'%{keyword}%', f'%{keyword}%'])
    if status:
        conditions.append("q.status = ?")
        params.append(status)
    if cust_id:
        conditions.append("q.cust_id = ?")
        params.append(cust_id)
    if b_id:
        conditions.append("q.b_id = ?")
        params.append(b_id)

    where_clause = ' AND '.join(conditions) if conditions else '1=1'

    cursor.execute(f"""
        SELECT q.*, c.company as customer_name, c.name as customer_contact,
               b.title as business_title, u.name as owner_name
        FROM quotes q
        LEFT JOIN customers c ON q.cust_id = c.id
        LEFT JOIN business b ON q.b_id = b.id
        LEFT JOIN users u ON q.owner_id = u.username
        WHERE {where_clause}
        ORDER BY q.updated_at DESC
    """, params)

    rows = cursor.fetchall()
    data = [dict(r) for r in rows]
    return jsonify({'code': 200, 'message': 'success', 'data': data})


@quotes_bp.route('/api/quotes/<int:quote_id>', methods=['GET'])
@token_required
def get_quote_detail(quote_id):
    """报价单详情：含主表 + 明细列表。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    if role in ('主任', '院长'):
        cursor.execute("""
            SELECT q.*, c.company as customer_name, c.name as customer_contact,
                   b.title as business_title, u.name as owner_name
            FROM quotes q
            LEFT JOIN customers c ON q.cust_id = c.id
            LEFT JOIN business b ON q.b_id = b.id
            LEFT JOIN users u ON q.owner_id = u.username
            WHERE q.id = ?
        """, (quote_id,))
    else:
        cursor.execute("""
            SELECT q.*, c.company as customer_name, c.name as customer_contact,
                   b.title as business_title, u.name as owner_name
            FROM quotes q
            LEFT JOIN customers c ON q.cust_id = c.id
            LEFT JOIN business b ON q.b_id = b.id
            LEFT JOIN users u ON q.owner_id = u.username
            WHERE q.id = ? AND q.owner_id = ?
        """, (quote_id, username))

    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '报价单不存在', 'data': None})

    quote = dict(row)

    cursor.execute("""
        SELECT qi.*, p.name as product_name, p.unit as product_unit
        FROM quote_items qi
        LEFT JOIN products p ON qi.product_id = p.id
        WHERE qi.quote_id = ?
        ORDER BY qi.id ASC
    """, (quote_id,))
    quote['items'] = [dict(r) for r in cursor.fetchall()]

    return jsonify({'code': 200, 'message': 'success', 'data': quote})


def _generate_quote_no(cursor):
    """生成报价单号：Q + 年月日 + 当日序号"""
    today = datetime.now().strftime('%Y%m%d')
    prefix = f'Q{today}'
    cursor.execute("SELECT COUNT(*) as cnt FROM quotes WHERE quote_no LIKE ?", (f'{prefix}%',))
    cnt = cursor.fetchone()['cnt']
    return f'{prefix}{(cnt + 1):03d}'


def _calc_total(items):
    """根据明细计算总额"""
    total = 0.0
    for it in items:
        qty = float(it.get('qty') or 0)
        unit_price = float(it.get('unit_price') or 0)
        amount = qty * unit_price
        it['amount'] = round(amount, 2)
        total += amount
    return round(total, 2)


@quotes_bp.route('/api/quotes', methods=['POST'])
@token_required
def create_quote():
    """创建报价单（含明细）。"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    items = data.get('items') or []
    total_amount = _calc_total(items)

    quote_no = data.get('quote_no') or _generate_quote_no(cursor)

    try:
        cursor.execute("""
            INSERT INTO quotes (quote_no, cust_id, b_id, title, total_amount, status, valid_until, owner_id, created_at, updated_at, remark)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
        """, (
            quote_no, data.get('cust_id'), data.get('b_id'), data.get('title'),
            total_amount, data.get('status') or 'draft', data.get('valid_until'),
            data.get('owner_id') or username, data.get('remark') or ''
        ))
        quote_id = cursor.lastrowid

        for it in items:
            cursor.execute("""
                INSERT INTO quote_items (quote_id, product_id, name, model, qty, unit_price, amount, remark)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                quote_id, it.get('product_id'), it.get('name'), it.get('model'),
                it.get('qty') or 1, it.get('unit_price') or 0, it.get('amount') or 0, it.get('remark') or ''
            ))

        db.commit()
        record_operation_log(username, '创建', '报价单', f'创建报价单：{quote_no}')
        return jsonify({'code': 200, 'message': '报价单创建成功', 'data': {'id': quote_id, 'quote_no': quote_no, 'total_amount': total_amount}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@quotes_bp.route('/api/quotes/<int:quote_id>', methods=['PUT'])
@token_required
def update_quote(quote_id):
    """编辑报价单（含明细整体替换）。"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']
    role = payload['role']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id, quote_no, status FROM quotes WHERE id=?", (quote_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '报价单不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    # 已终态状态不允许编辑内容
    if row['status'] in ('accepted', 'rejected', 'expired'):
        return jsonify({'code': 400, 'message': f'报价单当前状态为 {row["status"]}，不可编辑', 'data': None})

    items = data.get('items') or []
    total_amount = _calc_total(items)

    can_change_owner = role in ('主任', '院长')
    try:
        if can_change_owner and 'owner_id' in data:
            cursor.execute("""
                UPDATE quotes SET
                    cust_id=?, b_id=?, title=?, total_amount=?,
                    valid_until=?, owner_id=?, remark=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (
                data.get('cust_id'), data.get('b_id'), data.get('title'),
                total_amount, data.get('valid_until'), data.get('owner_id'),
                data.get('remark') or '', quote_id
            ))
        else:
            cursor.execute("""
                UPDATE quotes SET
                    cust_id=?, b_id=?, title=?, total_amount=?,
                    valid_until=?, remark=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (
                data.get('cust_id'), data.get('b_id'), data.get('title'),
                total_amount, data.get('valid_until'), data.get('remark') or '', quote_id
            ))

        # 明细整体替换
        cursor.execute("DELETE FROM quote_items WHERE quote_id=?", (quote_id,))
        for it in items:
            cursor.execute("""
                INSERT INTO quote_items (quote_id, product_id, name, model, qty, unit_price, amount, remark)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                quote_id, it.get('product_id'), it.get('name'), it.get('model'),
                it.get('qty') or 1, it.get('unit_price') or 0, it.get('amount') or 0, it.get('remark') or ''
            ))

        db.commit()
        record_operation_log(username, '编辑', '报价单', f'编辑报价单：{row["quote_no"]}')
        return jsonify({'code': 200, 'message': '报价单更新成功', 'data': {'total_amount': total_amount}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@quotes_bp.route('/api/quotes/<int:quote_id>/status', methods=['POST'])
@token_required
def update_quote_status(quote_id):
    """更新报价单状态：draft→sent→accepted/rejected/expired"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']
    role = payload['role']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id, quote_no, status FROM quotes WHERE id=?", (quote_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '报价单不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    new_status = (data.get('status') or '').lower()
    if new_status not in VALID_STATUSES:
        return jsonify({'code': 400, 'message': f'status 必须为 {VALID_STATUSES} 之一', 'data': None})

    try:
        cursor.execute("UPDATE quotes SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (new_status, quote_id))
        db.commit()
        record_operation_log(username, '状态变更', '报价单', f'{row["quote_no"]}：{row["status"]} → {new_status}')
        return jsonify({'code': 200, 'message': '状态更新成功', 'data': {'status': new_status}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@quotes_bp.route('/api/quotes/<int:quote_id>', methods=['DELETE'])
@token_required
def delete_quote(quote_id):
    """删除报价单（含明细）。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id, quote_no FROM quotes WHERE id=?", (quote_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '报价单不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    try:
        cursor.execute("DELETE FROM quote_items WHERE quote_id=?", (quote_id,))
        cursor.execute("DELETE FROM quotes WHERE id=?", (quote_id,))
        db.commit()
        record_operation_log(username, '删除', '报价单', f'删除报价单：{row["quote_no"]}')
        return jsonify({'code': 200, 'message': '报价单删除成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


def register_routes(app):
    app.register_blueprint(quotes_bp)
