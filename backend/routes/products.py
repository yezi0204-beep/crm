from flask import request, jsonify
from extensions import get_db, record_operation_log, token_required, user_can

from . import products_bp


@products_bp.route('/api/products', methods=['GET'])
@token_required
def get_products():
    """产品列表：支持关键字搜索、分类筛选、库存状态筛选。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    keyword = request.args.get('keyword', '')
    category = request.args.get('category', '')
    stock_status = request.args.get('stock_status', '')  # warning / normal / out

    db = get_db()
    cursor = db.cursor()

    conditions = []
    params = []

    # 普通销售仅可见自己负责的产品；管理层可见全部
    if not user_can(username, 'data.view_all'):
        conditions.append("p.owner_id = ?")
        params.append(username)

    if keyword:
        conditions.append("(p.name LIKE ? OR p.model LIKE ? OR p.description LIKE ?)")
        params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])
    if category:
        conditions.append("p.category = ?")
        params.append(category)

    where_clause = ' AND '.join(conditions) if conditions else '1=1'

    cursor.execute(f"""
        SELECT p.*, u.name as owner_name
        FROM products p
        LEFT JOIN users u ON p.owner_id = u.username
        WHERE {where_clause}
        ORDER BY p.updated_at DESC
    """, params)

    rows = cursor.fetchall()
    products = []
    for row in rows:
        item = dict(row)
        # 库存状态：out=缺货(stock<=0) warning=预警(0<stock<=warn_threshold) normal=正常
        stock = float(item.get('stock') or 0)
        threshold = float(item.get('warn_threshold') or 0)
        if stock <= 0:
            item['stock_status'] = 'out'
        elif threshold > 0 and stock <= threshold:
            item['stock_status'] = 'warning'
        else:
            item['stock_status'] = 'normal'
        products.append(item)

    # 二次按库存状态过滤
    if stock_status:
        products = [p for p in products if p['stock_status'] == stock_status]

    return jsonify({'code': 200, 'message': 'success', 'data': products})


@products_bp.route('/api/products/warnings', methods=['GET'])
@token_required
def get_product_warnings():
    """库存预警列表：缺货或低于预警阈值的产品。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    owner_filter = "" if user_can(username, 'data.view_all') else "AND p.owner_id = ?"
    owner_params = [] if user_can(username, 'data.view_all') else [username]

    cursor.execute(f"""
        SELECT p.*, u.name as owner_name
        FROM products p
        LEFT JOIN users u ON p.owner_id = u.username
        WHERE (p.stock <= 0 OR (p.warn_threshold > 0 AND p.stock <= p.warn_threshold))
        {owner_filter}
        ORDER BY CASE WHEN p.stock <= 0 THEN 0 ELSE 1 END, p.stock ASC
    """, owner_params)

    rows = cursor.fetchall()
    data = []
    for row in rows:
        item = dict(row)
        stock = float(item.get('stock') or 0)
        threshold = float(item.get('warn_threshold') or 0)
        item['stock_status'] = 'out' if stock <= 0 else 'warning'
        item['shortage'] = round(threshold - stock, 2) if stock <= threshold else 0
        data.append(item)

    return jsonify({'code': 200, 'message': 'success', 'data': data})


@products_bp.route('/api/products/<int:product_id>', methods=['GET'])
@token_required
def get_product(product_id):
    """产品详情。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    if user_can(username, 'data.view_all'):
        cursor.execute("""
            SELECT p.*, u.name as owner_name
            FROM products p
            LEFT JOIN users u ON p.owner_id = u.username
            WHERE p.id = ?
        """, (product_id,))
    else:
        cursor.execute("""
            SELECT p.*, u.name as owner_name
            FROM products p
            LEFT JOIN users u ON p.owner_id = u.username
            WHERE p.id = ? AND p.owner_id = ?
        """, (product_id, username))

    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '产品不存在', 'data': None})

    return jsonify({'code': 200, 'message': 'success', 'data': dict(row)})


@products_bp.route('/api/products', methods=['POST'])
@token_required
def create_product():
    """创建产品。"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("""
            INSERT INTO products (name, model, category, unit, price, cost, stock, warn_threshold, description, owner_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (
            data.get('name'), data.get('model'), data.get('category'),
            data.get('unit'), data.get('price') or 0, data.get('cost') or 0,
            data.get('stock') or 0, data.get('warn_threshold') or 0,
            data.get('description'), data.get('owner_id') or username
        ))
        product_id = cursor.lastrowid

        # 初始库存记为入库流水
        init_stock = float(data.get('stock') or 0)
        if init_stock > 0:
            cursor.execute("""
                INSERT INTO inventory_records (product_id, type, quantity, reference, operator_id, remark, created_at)
                VALUES (?, 'in', ?, '初始入库', ?, '产品创建时初始库存', CURRENT_TIMESTAMP)
            """, (product_id, init_stock, username))

        db.commit()
        record_operation_log(username, '创建', '产品', f'创建产品：{data.get("name")}')
        return jsonify({'code': 200, 'message': '产品创建成功', 'data': {'id': product_id}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@products_bp.route('/api/products/<int:product_id>', methods=['PUT'])
@token_required
def update_product(product_id):
    """编辑产品基础信息（库存变动请使用出入库接口）。"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']
    role = payload['role']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id, name FROM products WHERE id=?", (product_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '产品不存在', 'data': None})
    if not user_can(username, 'data.view_all') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足，只能编辑自己的产品', 'data': None})

    can_change_owner = user_can(username, 'data.view_all')
    try:
        if can_change_owner and 'owner_id' in data:
            cursor.execute("""
                UPDATE products SET
                    name=?, model=?, category=?, unit=?, price=?, cost=?,
                    warn_threshold=?, description=?, owner_id=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (
                data.get('name'), data.get('model'), data.get('category'),
                data.get('unit'), data.get('price') or 0, data.get('cost') or 0,
                data.get('warn_threshold') or 0, data.get('description'),
                data.get('owner_id'), product_id
            ))
        else:
            cursor.execute("""
                UPDATE products SET
                    name=?, model=?, category=?, unit=?, price=?, cost=?,
                    warn_threshold=?, description=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (
                data.get('name'), data.get('model'), data.get('category'),
                data.get('unit'), data.get('price') or 0, data.get('cost') or 0,
                data.get('warn_threshold') or 0, data.get('description'),
                product_id
            ))
        db.commit()
        record_operation_log(username, '编辑', '产品', f'编辑产品：{data.get("name") or row["name"]}（ID:{product_id}）')
        return jsonify({'code': 200, 'message': '产品更新成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@products_bp.route('/api/products/<int:product_id>', methods=['DELETE'])
@token_required
def delete_product(product_id):
    """删除产品（同时删除出入库流水和关联报价明细中的引用置空）。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id, name FROM products WHERE id=?", (product_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '产品不存在', 'data': None})
    if not user_can(username, 'data.view_all') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足，只能删除自己的产品', 'data': None})

    try:
        cursor.execute("DELETE FROM inventory_records WHERE product_id=?", (product_id,))
        # 报价明细中引用本产品的记录：product_id 置空，保留明细文本信息
        cursor.execute("UPDATE quote_items SET product_id=NULL WHERE product_id=?", (product_id,))
        cursor.execute("DELETE FROM products WHERE id=?", (product_id,))
        db.commit()
        record_operation_log(username, '删除', '产品', f'删除产品：{row["name"]}（ID:{product_id}）')
        return jsonify({'code': 200, 'message': '产品删除成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@products_bp.route('/api/products/<int:product_id>/inventory', methods=['POST'])
@token_required
def record_inventory(product_id):
    """出入库操作：自动更新产品库存。
    入参：type(in/out), quantity(正数), reference(关联单据,可选), remark(可选)
    """
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']
    role = payload['role']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id, name, stock FROM products WHERE id=?", (product_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '产品不存在', 'data': None})
    if not user_can(username, 'data.view_all') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    inv_type = (data.get('type') or '').lower()
    if inv_type not in ('in', 'out'):
        return jsonify({'code': 400, 'message': 'type 必须为 in 或 out', 'data': None})

    try:
        quantity = float(data.get('quantity') or 0)
    except (TypeError, ValueError):
        return jsonify({'code': 400, 'message': 'quantity 必须为数字', 'data': None})
    if quantity <= 0:
        return jsonify({'code': 400, 'message': 'quantity 必须为正数', 'data': None})

    current_stock = float(row['stock'] or 0)
    if inv_type == 'in':
        new_stock = current_stock + quantity
    else:
        if quantity > current_stock:
            return jsonify({'code': 400, 'message': f'库存不足，当前库存 {current_stock}', 'data': None})
        new_stock = current_stock - quantity

    try:
        cursor.execute("""
            INSERT INTO inventory_records (product_id, type, quantity, reference, operator_id, remark, created_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (product_id, inv_type, quantity, data.get('reference') or '', username, data.get('remark') or ''))

        cursor.execute("UPDATE products SET stock=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (new_stock, product_id))
        db.commit()

        action = '入库' if inv_type == 'in' else '出库'
        record_operation_log(username, action, '产品', f'{action}：{row["name"]} ×{quantity}')
        return jsonify({'code': 200, 'message': f'{action}成功', 'data': {'stock': new_stock}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@products_bp.route('/api/products/<int:product_id>/inventory', methods=['GET'])
@token_required
def get_inventory_history(product_id):
    """产品出入库流水历史。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id FROM products WHERE id=?", (product_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '产品不存在', 'data': None})
    if not user_can(username, 'data.view_all') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    cursor.execute("""
        SELECT ir.*, u.name as operator_name
        FROM inventory_records ir
        LEFT JOIN users u ON ir.operator_id = u.username
        WHERE ir.product_id = ?
        ORDER BY ir.created_at DESC
    """, (product_id,))

    rows = cursor.fetchall()
    data = [dict(r) for r in rows]
    return jsonify({'code': 200, 'message': 'success', 'data': data})


def register_routes(app):
    app.register_blueprint(products_bp)
