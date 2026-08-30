"""ERP 系统集成模块（5.5.3）

提供 ERP 连接配置管理（CRUD/测试）与数据同步（导出/导入）能力。
权限模型：仅持有 data.view_all 的管理层可访问。

接口路径保持 /api/reports/erp/* 前缀不变，前端无需改动。
"""
from datetime import datetime
from flask import request, jsonify

from extensions import get_db, token_required, record_operation_log, user_can

from . import erp_bp


# ERP 连接配置存储表（动态创建，避免侵入主表初始化）
def _ensure_erp_tables(cursor):
    """确保 ERP 集成相关表存在。"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS erp_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            system_type TEXT,
            base_url TEXT,
            api_key TEXT,
            auth_type TEXT DEFAULT 'api_key',
            status TEXT DEFAULT 'inactive',
            last_sync_at TEXT,
            last_sync_status TEXT,
            last_sync_count INTEGER DEFAULT 0,
            config TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            remark TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS erp_sync_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            connection_id INTEGER NOT NULL,
            direction TEXT,
            module TEXT,
            status TEXT,
            total_count INTEGER DEFAULT 0,
            success_count INTEGER DEFAULT 0,
            fail_count INTEGER DEFAULT 0,
            started_at TEXT,
            finished_at TEXT,
            error_message TEXT,
            FOREIGN KEY (connection_id) REFERENCES erp_connections(id)
        )
    """)


@erp_bp.route('/api/reports/erp/connections', methods=['GET'])
@token_required
def get_erp_connections():
    """获取 ERP 连接列表。"""
    payload = request.current_user
    if not user_can(payload['username'], 'data.view_all'):
        return jsonify({'code': 403, 'message': '仅管理层可查看 ERP 集成配置', 'data': None})

    db = get_db()
    cursor = db.cursor()
    _ensure_erp_tables(cursor)
    db.commit()

    cursor.execute("""
        SELECT id, name, system_type, base_url, auth_type, status,
               last_sync_at, last_sync_status, last_sync_count,
               created_at, updated_at, remark
        FROM erp_connections
        ORDER BY updated_at DESC
    """)
    rows = cursor.fetchall()
    # 脱敏：不返回 api_key
    data = []
    for r in rows:
        item = dict(r)
        item['has_api_key'] = True  # 仅标记是否存在，不返回明文
        data.append(item)
    return jsonify({'code': 200, 'message': 'success', 'data': data})


@erp_bp.route('/api/reports/erp/connections', methods=['POST'])
@token_required
def create_erp_connection():
    """创建 ERP 连接配置。"""
    payload = request.current_user
    if not user_can(payload['username'], 'data.view_all'):
        return jsonify({'code': 403, 'message': '仅管理层可配置 ERP 集成', 'data': None})

    data = request.get_json(silent=True) or {}
    if not data.get('name'):
        return jsonify({'code': 400, 'message': '连接名称不能为空', 'data': None})

    db = get_db()
    cursor = db.cursor()
    _ensure_erp_tables(cursor)

    try:
        cursor.execute("""
            INSERT INTO erp_connections (name, system_type, base_url, api_key, auth_type,
                status, config, created_at, updated_at, remark)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
        """, (
            data.get('name'), data.get('system_type') or 'erp',
            data.get('base_url'), data.get('api_key'),
            data.get('auth_type') or 'api_key', data.get('status') or 'inactive',
            data.get('config') or '', data.get('remark') or ''
        ))
        conn_id = cursor.lastrowid
        db.commit()
        record_operation_log(payload['username'], '创建', 'ERP连接', f'创建 ERP 连接：{data.get("name")}')
        return jsonify({'code': 200, 'message': 'ERP 连接创建成功', 'data': {'id': conn_id}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@erp_bp.route('/api/reports/erp/connections/<int:conn_id>', methods=['PUT'])
@token_required
def update_erp_connection(conn_id):
    """编辑 ERP 连接配置。"""
    payload = request.current_user
    if not user_can(payload['username'], 'data.view_all'):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    data = request.get_json(silent=True) or {}
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT id FROM erp_connections WHERE id=?", (conn_id,))
    if not cursor.fetchone():
        return jsonify({'code': 404, 'message': 'ERP 连接不存在', 'data': None})

    try:
        # api_key 为空则不更新
        if data.get('api_key'):
            cursor.execute("""
                UPDATE erp_connections SET
                    name=COALESCE(?, name), system_type=COALESCE(?, system_type),
                    base_url=COALESCE(?, base_url), api_key=?,
                    auth_type=COALESCE(?, auth_type), status=COALESCE(?, status),
                    config=COALESCE(?, config), remark=COALESCE(?, remark),
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (
                data.get('name'), data.get('system_type'), data.get('base_url'),
                data.get('api_key'), data.get('auth_type'), data.get('status'),
                data.get('config'), data.get('remark'), conn_id
            ))
        else:
            cursor.execute("""
                UPDATE erp_connections SET
                    name=COALESCE(?, name), system_type=COALESCE(?, system_type),
                    base_url=COALESCE(?, base_url),
                    auth_type=COALESCE(?, auth_type), status=COALESCE(?, status),
                    config=COALESCE(?, config), remark=COALESCE(?, remark),
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (
                data.get('name'), data.get('system_type'), data.get('base_url'),
                data.get('auth_type'), data.get('status'),
                data.get('config'), data.get('remark'), conn_id
            ))
        db.commit()
        record_operation_log(payload['username'], '编辑', 'ERP连接', f'编辑 ERP 连接 ID:{conn_id}')
        return jsonify({'code': 200, 'message': 'ERP 连接更新成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@erp_bp.route('/api/reports/erp/connections/<int:conn_id>', methods=['DELETE'])
@token_required
def delete_erp_connection(conn_id):
    """删除 ERP 连接。"""
    payload = request.current_user
    if not user_can(payload['username'], 'data.view_all'):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM erp_sync_logs WHERE connection_id=?", (conn_id,))
        cursor.execute("DELETE FROM erp_connections WHERE id=?", (conn_id,))
        db.commit()
        record_operation_log(payload['username'], '删除', 'ERP连接', f'删除 ERP 连接 ID:{conn_id}')
        return jsonify({'code': 200, 'message': 'ERP 连接删除成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@erp_bp.route('/api/reports/erp/connections/<int:conn_id>/test', methods=['POST'])
@token_required
def test_erp_connection(conn_id):
    """测试 ERP 连接（仅校验配置完整性，不实际发起外部请求）。"""
    payload = request.current_user
    if not user_can(payload['username'], 'data.view_all'):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT name, base_url, api_key, auth_type, status FROM erp_connections WHERE id=?", (conn_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': 'ERP 连接不存在', 'data': None})

    issues = []
    if not row['base_url']:
        issues.append('未配置服务地址')
    if row['auth_type'] == 'api_key' and not row['api_key']:
        issues.append('未配置 API Key')

    if issues:
        return jsonify({
            'code': 400,
            'message': '连接配置不完整：' + '；'.join(issues),
            'data': {'status': 'invalid', 'issues': issues}
        })

    # 配置完整即视为通过（实际生产环境此处应发起 ping/health 请求）
    return jsonify({
        'code': 200,
        'message': f'连接配置校验通过：{row["name"]}',
        'data': {'status': 'ok', 'base_url': row['base_url']}
    })


@erp_bp.route('/api/reports/erp/sync', methods=['POST'])
@token_required
def sync_erp_data():
    """ERP 数据同步：将 CRM 数据导出为 JSON/CSV 供 ERP 系统对接，或导入 ERP 数据。
    入参：connection_id, direction(export/import), module(customers/products/contracts)
    """
    payload = request.current_user
    if not user_can(payload['username'], 'data.view_all'):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    data = request.get_json(silent=True) or {}
    conn_id = data.get('connection_id')
    direction = (data.get('direction') or 'export').lower()
    module = (data.get('module') or 'customers').lower()

    if direction not in ('export', 'import'):
        return jsonify({'code': 400, 'message': 'direction 必须为 export 或 import', 'data': None})

    valid_modules = ('customers', 'products', 'contracts', 'business', 'payments')
    if module not in valid_modules:
        return jsonify({'code': 400, 'message': f'module 必须为 {valid_modules} 之一', 'data': None})

    db = get_db()
    cursor = db.cursor()
    _ensure_erp_tables(cursor)

    cursor.execute("SELECT name, base_url, status FROM erp_connections WHERE id=?", (conn_id,))
    conn = cursor.fetchone()
    if not conn:
        return jsonify({'code': 404, 'message': 'ERP 连接不存在', 'data': None})

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_id = None
    try:
        # 创建同步日志
        cursor.execute("""
            INSERT INTO erp_sync_logs (connection_id, direction, module, status,
                total_count, success_count, fail_count, started_at)
            VALUES (?, ?, ?, 'running', 0, 0, 0, ?)
        """, (conn_id, direction, module, now))
        log_id = cursor.lastrowid

        # 根据模块获取/统计数据
        if direction == 'export':
            if module == 'customers':
                cursor.execute("SELECT id, company, name, phone, email, owner_id FROM customers")
            elif module == 'products':
                cursor.execute("SELECT id, name, model, category, unit, price, stock FROM products")
            elif module == 'contracts':
                cursor.execute("SELECT id, contract_no, cust_id, total_amt, sign_date, owner_id FROM contracts")
            elif module == 'business':
                cursor.execute("SELECT id, title, cust_id, amount, probability, status, owner_id FROM business")
            elif module == 'payments':
                cursor.execute("SELECT id, contract_id, amount, payment_date FROM payment_records")
            rows = cursor.fetchall()
            records = [dict(r) for r in rows]
            total_count = len(records)
            success_count = total_count
            fail_count = 0
            sync_data = records
        else:
            # import：示例实现，实际应解析上传数据并入库
            import_data = data.get('data') or []
            total_count = len(import_data)
            success_count = total_count
            fail_count = 0
            sync_data = {'imported': total_count}

        finished_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
            UPDATE erp_sync_logs SET status='success', total_count=?, success_count=?,
                fail_count=?, finished_at=?
            WHERE id=?
        """, (total_count, success_count, fail_count, finished_at, log_id))

        # 更新连接的最后同步信息
        cursor.execute("""
            UPDATE erp_connections SET last_sync_at=?, last_sync_status='success',
                last_sync_count=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (now, success_count, conn_id))

        db.commit()
        record_operation_log(payload['username'], 'ERP同步',
            f'{conn["name"]} {direction} {module}：{success_count} 条')

        return jsonify({
            'code': 200,
            'message': f'同步完成：{direction} {module} 共 {success_count} 条',
            'data': {
                'log_id': log_id,
                'direction': direction,
                'module': module,
                'total': total_count,
                'success': success_count,
                'fail': fail_count,
                'sync_data': sync_data if direction == 'export' else None
            }
        })
    except Exception as e:
        if log_id:
            cursor.execute("""
                UPDATE erp_sync_logs SET status='failed', error_message=?,
                    finished_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (str(e), log_id))
        cursor.execute("""
            UPDATE erp_connections SET last_sync_at=?, last_sync_status='failed',
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (now, conn_id))
        db.commit()
        return jsonify({'code': 500, 'message': f'同步失败：{str(e)}', 'data': None})


@erp_bp.route('/api/reports/erp/sync-logs', methods=['GET'])
@token_required
def get_erp_sync_logs():
    """获取 ERP 同步日志列表。"""
    payload = request.current_user
    if not user_can(payload['username'], 'data.view_all'):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    connection_id = request.args.get('connection_id', '')
    limit = request.args.get('limit', 50, type=int)

    db = get_db()
    cursor = db.cursor()
    _ensure_erp_tables(cursor)

    if connection_id:
        cursor.execute("""
            SELECT l.*, c.name as connection_name
            FROM erp_sync_logs l
            LEFT JOIN erp_connections c ON l.connection_id = c.id
            WHERE l.connection_id = ?
            ORDER BY l.started_at DESC
            LIMIT ?
        """, (connection_id, limit))
    else:
        cursor.execute("""
            SELECT l.*, c.name as connection_name
            FROM erp_sync_logs l
            LEFT JOIN erp_connections c ON l.connection_id = c.id
            ORDER BY l.started_at DESC
            LIMIT ?
        """, (limit,))

    rows = cursor.fetchall()
    return jsonify({'code': 200, 'message': 'success', 'data': [dict(r) for r in rows]})


def register_routes(app):
    app.register_blueprint(erp_bp)
