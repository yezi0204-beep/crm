import os
import uuid
from io import BytesIO
from datetime import datetime
from flask import request, jsonify, send_from_directory
from extensions import (
    get_db, verify_token, record_operation_log,
    token_required, admin_required, UPLOAD_DIR,
)

from . import contracts_bp


@contracts_bp.route('/api/contracts', methods=['GET'])
@token_required
def get_contracts():
    payload = request.current_user
    username = payload['username']
    role = payload['role']
    sort_field = request.args.get('sort_field', 'sign_date')
    sort_order = request.args.get('sort_order', 'desc')

    db = get_db()
    cursor = db.cursor()

    valid_fields = ['sign_date', 'total_amt', 'paid_amt', 'contract_name', 'contract_no', 'pending_amt']
    if sort_field not in valid_fields:
        sort_field = 'sign_date'

    sort_direction = 'DESC' if sort_order.lower() in ['desc', 'descending'] else 'ASC'
    order_by_clause = sort_field + " " + sort_direction

    # 关联名：customer_name（客户公司名）、business_title（关联商机标题）
    if role == '主任' or role == '院长':
        if sort_field == 'pending_amt':
            cursor.execute(
                "SELECT c.*, u.name as owner_name, cu.company as customer_name, b.title as business_title, "
                "(COALESCE(c.total_amt, 0) - COALESCE(c.paid_amt, 0)) as pending_amt "
                "FROM contracts c "
                "LEFT JOIN users u ON c.owner_id = u.username "
                "LEFT JOIN customers cu ON c.cust_id = cu.id "
                "LEFT JOIN business b ON c.b_id = b.id "
                "ORDER BY pending_amt " + sort_direction
            )
        else:
            cursor.execute(
                "SELECT c.*, u.name as owner_name, cu.company as customer_name, b.title as business_title "
                "FROM contracts c "
                "LEFT JOIN users u ON c.owner_id = u.username "
                "LEFT JOIN customers cu ON c.cust_id = cu.id "
                "LEFT JOIN business b ON c.b_id = b.id "
                "ORDER BY c." + order_by_clause
            )
    else:
        if sort_field == 'pending_amt':
            cursor.execute(
                "SELECT c.*, u.name as owner_name, cu.company as customer_name, b.title as business_title, "
                "(COALESCE(c.total_amt, 0) - COALESCE(c.paid_amt, 0)) as pending_amt "
                "FROM contracts c "
                "LEFT JOIN users u ON c.owner_id = u.username "
                "LEFT JOIN customers cu ON c.cust_id = cu.id "
                "LEFT JOIN business b ON c.b_id = b.id "
                "WHERE c.owner_id = ? "
                "ORDER BY pending_amt " + sort_direction,
                (username,)
            )
        else:
            cursor.execute(
                "SELECT c.*, u.name as owner_name, cu.company as customer_name, b.title as business_title "
                "FROM contracts c "
                "LEFT JOIN users u ON c.owner_id = u.username "
                "LEFT JOIN customers cu ON c.cust_id = cu.id "
                "LEFT JOIN business b ON c.b_id = b.id "
                "WHERE c.owner_id = ? "
                "ORDER BY c." + order_by_clause,
                (username,)
            )

    rows = cursor.fetchall()
    contracts = []
    for row in rows:
        contracts.append(dict(row))

    return jsonify({'code': 200, 'message': 'success', 'data': contracts})


@contracts_bp.route('/api/contracts/check-no', methods=['GET'])
@token_required
def check_contract_no():
    contract_no = request.args.get('contract_no', '')
    exclude_id = request.args.get('exclude_id', type=int, default=None)

    db = get_db()
    cursor = db.cursor()

    if exclude_id:
        cursor.execute("SELECT COUNT(*) FROM contracts WHERE contract_no = ? AND id != ?", (contract_no, exclude_id))
    else:
        cursor.execute("SELECT COUNT(*) FROM contracts WHERE contract_no = ?", (contract_no,))

    count = cursor.fetchone()[0]

    return jsonify({'code': 200, 'message': 'success', 'data': {'exists': count > 0}})


@contracts_bp.route('/api/contracts/<int:contract_id>', methods=['GET'])
@token_required
def get_contract(contract_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "SELECT ct.*, u.name as owner_name, cu.company as customer_name, b.title as business_title "
        "FROM contracts ct "
        "LEFT JOIN users u ON ct.owner_id = u.username "
        "LEFT JOIN customers cu ON ct.cust_id = cu.id "
        "LEFT JOIN business b ON ct.b_id = b.id "
        "WHERE ct.id = ?",
        (contract_id,)
    )
    row = cursor.fetchone()

    if row:
        return jsonify({'code': 200, 'message': 'success', 'data': dict(row)})
    return jsonify({'code': 404, 'message': '合同不存在', 'data': None})


@contracts_bp.route('/api/contracts', methods=['POST'])
@token_required
def create_contract():
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    try:
        contract_no = data.get('contract_no')
        if not contract_no or contract_no.strip() == '':
            cursor.execute("SELECT MAX(id) FROM contracts")
            max_id = cursor.fetchone()[0] or 0
            contract_no = f"HT{datetime.now().strftime('%Y%m%d%H%M%S')}{str(max_id + 1).zfill(3)}"

        cursor.execute("SELECT COUNT(*) FROM contracts WHERE contract_no = ?", (contract_no,))
        if cursor.fetchone()[0] > 0:
            contract_no = f"HT{datetime.now().strftime('%Y%m%d%H%M%S')}{str(max_id + 1).zfill(3)}{str(uuid.uuid4().hex[:3])}"

        # 关联客户/商机，并做一致性兜底：若传了 b_id，以商机的 cust_id 为准，防数据撕裂
        b_id = data.get('b_id')
        b_id = b_id if b_id else None  # 规范化空字符串为 None
        cust_id = data.get('cust_id')
        if b_id:
            cursor.execute("SELECT cust_id FROM business WHERE id = ?", (b_id,))
            brow = cursor.fetchone()
            if brow and brow['cust_id']:
                cust_id = brow['cust_id']

        cursor.execute("""
            INSERT INTO contracts
            (b_id, cust_id, contract_no, party_a, project_order_no, total_amt, paid_amt, sign_date, owner_id, status,
             contract_name, classification, is_audit, pending_acceptance_amount,
             cost, gross_profit, acceptance_date, expected_income_date,
             expected_income_year, business_type, total_cost, acceptance_nodes, payment_nodes, note, is_framework)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
        """, (
            b_id, cust_id, contract_no, data.get('party_a'), data.get('project_order_no'),
            data.get('total_amt'), 0, data.get('sign_date'), data.get('owner_id'), '执行中',
            data.get('contract_name'), data.get('classification'), data.get('is_audit'), data.get('pending_acceptance_amount'),
            data.get('cost'), data.get('gross_profit'), data.get('acceptance_date'), data.get('expected_income_date'),
            data.get('expected_income_year'), data.get('business_type'), data.get('acceptance_nodes'), data.get('payment_nodes'),
            data.get('note'), 1 if data.get('is_framework') else 0
        ))
        db.commit()
        contract_id = cursor.lastrowid

        record_operation_log(username, '创建', '合同', f'创建合同：{data.get("contract_name")}（{contract_no}）')

        return jsonify({'code': 200, 'message': '合同创建成功', 'data': {'id': contract_id, 'contract_no': contract_no}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@contracts_bp.route('/api/contracts/<int:contract_id>', methods=['PUT'])
@token_required
def update_contract(contract_id):
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    try:
        # 关联客户/商机，并做一致性兜底：若传了 b_id，以商机的 cust_id 为准，防数据撕裂
        b_id = data.get('b_id')
        b_id = b_id if b_id else None  # 规范化空字符串为 None
        cust_id = data.get('cust_id')
        if b_id:
            cursor.execute("SELECT cust_id FROM business WHERE id = ?", (b_id,))
            brow = cursor.fetchone()
            if brow and brow['cust_id']:
                cust_id = brow['cust_id']

        cursor.execute("""
            UPDATE contracts SET
                contract_name=?, contract_no=?, party_a=?, project_order_no=?, total_amt=?, sign_date=?,
                classification=?, is_audit=?, pending_acceptance_amount=?,
                cost=?, gross_profit=?, acceptance_date=?, expected_income_date=?,
                expected_income_year=?, business_type=?, status=?, owner_id=?,
                cust_id=?, b_id=?,
                acceptance_nodes=?, payment_nodes=?, note=?, is_framework=?
            WHERE id=?
        """, (
            data.get('contract_name'), data.get('contract_no'), data.get('party_a'), data.get('project_order_no'),
            data.get('total_amt'), data.get('sign_date'), data.get('classification'), data.get('is_audit'),
            data.get('pending_acceptance_amount'), data.get('cost'), data.get('gross_profit'),
            data.get('acceptance_date'), data.get('expected_income_date'), data.get('expected_income_year'),
            data.get('business_type'), data.get('status'), data.get('owner_id'),
            cust_id, b_id,
            data.get('acceptance_nodes'), data.get('payment_nodes'), data.get('note'),
            1 if data.get('is_framework') else 0, contract_id
        ))
        db.commit()

        record_operation_log(username, '编辑', '合同', f'编辑合同：{data.get("contract_name")}（ID:{contract_id}）')

        return jsonify({'code': 200, 'message': '合同更新成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@contracts_bp.route('/api/contracts/<int:contract_id>/owner', methods=['PATCH', 'POST'])
@token_required
def update_contract_owner(contract_id):
    payload = request.current_user

    if payload['role'] != '主任' and payload['role'] != '院长':
        return jsonify({'code': 403, 'message': '无权修改负责人', 'data': None})

    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'code': 400, 'message': '请求数据为空', 'data': None})

    owner_id = data.get('owner_id')

    if not owner_id:
        return jsonify({'code': 400, 'message': '请选择负责人', 'data': None})

    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("UPDATE contracts SET owner_id = ? WHERE id = ?", (owner_id, contract_id))
        db.commit()

        return jsonify({'code': 200, 'message': '负责人修改成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


# ==================== 合同销售分成 ====================

@contracts_bp.route('/api/contracts/<int:contract_id>/commissions', methods=['GET'])
@token_required
def get_contract_commissions(contract_id):
    """获取合同的销售分成列表。"""
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, total_amt, contract_name, owner_id FROM contracts WHERE id=?", (contract_id,))
    c = cur.fetchone()
    if not c:
        return jsonify({'code': 404, 'message': '合同不存在', 'data': None})
    cur.execute(
        "SELECT cc.username, cc.ratio, u.name "
        "FROM contract_commissions cc LEFT JOIN users u ON cc.username = u.username "
        "WHERE cc.contract_id=? ORDER BY cc.ratio DESC",
        (contract_id,)
    )
    rows = [{'username': r['username'], 'name': r['name'] or r['username'], 'ratio': float(r['ratio'])}
            for r in cur.fetchall()]
    return jsonify({
        'code': 200, 'message': 'OK',
        'data': {
            'contract_id': contract_id,
            'contract_name': c['contract_name'],
            'total_amt': float(c['total_amt'] or 0),
            'owner_id': c['owner_id'],
            'commissions': rows,
        }
    })


@contracts_bp.route('/api/contracts/<int:contract_id>/commissions', methods=['POST'])
@token_required
def save_contract_commissions(contract_id):
    """保存合同销售分成（整体替换）。仅主任/院长。
    body: {commissions: [{username, ratio}, ...]}  ratio之和必须=100
    """
    payload = request.current_user
    if payload['role'] != '主任' and payload['role'] != '院长':
        return jsonify({'code': 403, 'message': '无权设置分成', 'data': None})
    data = request.get_json(silent=True) or {}
    items = data.get('commissions') or []
    if not isinstance(items, list):
        return jsonify({'code': 400, 'message': 'commissions 必须是数组', 'data': None})
    # 校验
    total_ratio = 0
    seen = set()
    for item in items:
        u = (item.get('username') or '').strip()
        r = float(item.get('ratio') or 0)
        if not u:
            return jsonify({'code': 400, 'message': '分成人员用户名不能为空', 'data': None})
        if r < 0 or r > 100:
            return jsonify({'code': 400, 'message': f'比例 {r}% 超出范围(0-100)', 'data': None})
        if u in seen:
            return jsonify({'code': 400, 'message': f'人员 {u} 重复', 'data': None})
        seen.add(u)
        total_ratio += r
    if items and abs(total_ratio - 100.0) > 0.01:
        return jsonify({'code': 400, 'message': f'分成比例之和为 {total_ratio}%，必须等于 100%', 'data': None})

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT 1 FROM contracts WHERE id=?", (contract_id,))
    if not cur.fetchone():
        return jsonify({'code': 404, 'message': '合同不存在', 'data': None})

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    operator = payload['username']
    try:
        # 整体替换：先删后插
        cur.execute("DELETE FROM contract_commissions WHERE contract_id=?", (contract_id,))
        for item in items:
            u = (item.get('username') or '').strip()
            r = float(item.get('ratio') or 0)
            cur.execute(
                "INSERT INTO contract_commissions (contract_id, username, ratio, created_by, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (contract_id, u, r, operator, now)
            )
        db.commit()
        try:
            record_operation_log(operator, '设置分成', '合同管理',
                                 f'合同ID={contract_id} 设置销售分成：'
                                 + ', '.join(f"{it['username']}={it.get('ratio',0)}%" for it in items)
                                 if items else f'合同ID={contract_id} 清除分成')
        except Exception:
            pass
        return jsonify({'code': 200, 'message': '分成保存成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


# ==================== 框架合同验收记录 ====================

@contracts_bp.route('/api/contracts/<int:contract_id>/acceptances', methods=['GET'])
@token_required
def get_acceptances(contract_id):
    """获取框架合同的验收记录列表（含每次验收的分成分配）。"""
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, is_framework, total_amt, contract_name FROM contracts WHERE id=?", (contract_id,))
    c = cur.fetchone()
    if not c:
        return jsonify({'code': 404, 'message': '合同不存在', 'data': None})
    cur.execute(
        "SELECT id, acceptance_date, acceptance_amount, note, created_by, created_at "
        "FROM contract_acceptances WHERE contract_id=? ORDER BY acceptance_date DESC",
        (contract_id,)
    )
    rows = [dict(r) for r in cur.fetchall()]
    # 查每条验收的分成
    for r in rows:
        cur.execute(
            "SELECT username, ratio FROM acceptance_commissions WHERE acceptance_id=? ORDER BY ratio DESC",
            (r['id'],)
        )
        r['commissions'] = [{'username': cr['username'], 'ratio': float(cr['ratio'])} for cr in cur.fetchall()]
    total_accepted = sum(float(r['acceptance_amount'] or 0) for r in rows)
    return jsonify({
        'code': 200, 'message': 'OK',
        'data': {
            'contract_id': contract_id,
            'contract_name': c['contract_name'],
            'is_framework': int(c['is_framework'] or 0),
            'total_amt': float(c['total_amt'] or 0),
            'total_accepted': round(total_accepted, 2),
            'acceptances': rows,
        }
    })


@contracts_bp.route('/api/contracts/<int:contract_id>/acceptances', methods=['POST'])
@token_required
def add_acceptance(contract_id):
    """新增一条验收记录（可同时传入分成）。
    body: {acceptance_date, acceptance_amount, note, commissions: [{username, ratio}]}
    """
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    acc_date = (data.get('acceptance_date') or '').strip()
    acc_amt = float(data.get('acceptance_amount') or 0)
    if not acc_date:
        return jsonify({'code': 400, 'message': '验收日期不能为空', 'data': None})
    if acc_amt <= 0:
        return jsonify({'code': 400, 'message': '验收金额必须大于0', 'data': None})
    commissions = data.get('commissions') or []
    # 校验分成
    total_ratio = 0
    seen = set()
    for item in commissions:
        u = (item.get('username') or '').strip()
        r = float(item.get('ratio') or 0)
        if not u:
            return jsonify({'code': 400, 'message': '分成人员用户名不能为空', 'data': None})
        if u in seen:
            return jsonify({'code': 400, 'message': f'人员 {u} 重复', 'data': None})
        seen.add(u)
        total_ratio += r
    if commissions and abs(total_ratio - 100.0) > 0.01:
        return jsonify({'code': 400, 'message': f'分成比例之和为 {total_ratio}%，必须等于 100%', 'data': None})

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT 1 FROM contracts WHERE id=?", (contract_id,))
    if not cur.fetchone():
        return jsonify({'code': 404, 'message': '合同不存在', 'data': None})
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    operator = payload['username']
    try:
        cur.execute(
            "INSERT INTO contract_acceptances (contract_id, acceptance_date, acceptance_amount, note, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (contract_id, acc_date, acc_amt, data.get('note', ''), operator, now)
        )
        acc_id = cur.lastrowid
        # 写入验收级分成
        for item in commissions:
            u = (item.get('username') or '').strip()
            r = float(item.get('ratio') or 0)
            cur.execute(
                "INSERT INTO acceptance_commissions (acceptance_id, username, ratio, created_by, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (acc_id, u, r, operator, now)
            )
        db.commit()
        try:
            record_operation_log(operator, '新增验收', '合同管理',
                                 f'合同ID={contract_id} 验收日期={acc_date} 金额={acc_amt}'
                                 + (f' 分成={commissions}' if commissions else ''))
        except Exception:
            pass
        return jsonify({'code': 200, 'message': '验收记录添加成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@contracts_bp.route('/api/contracts/acceptances/<int:acc_id>', methods=['DELETE'])
@token_required
def delete_acceptance(acc_id):
    """删除一条验收记录（同时删除其分成）。"""
    payload = request.current_user
    if payload['role'] != '主任' and payload['role'] != '院长':
        return jsonify({'code': 403, 'message': '无权删除验收记录', 'data': None})
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT contract_id, acceptance_amount FROM contract_acceptances WHERE id=?", (acc_id,))
    row = cur.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '验收记录不存在', 'data': None})
    try:
        cur.execute("DELETE FROM acceptance_commissions WHERE acceptance_id=?", (acc_id,))
        cur.execute("DELETE FROM contract_acceptances WHERE id=?", (acc_id,))
        db.commit()
        try:
            record_operation_log(payload['username'], '删除验收', '合同管理',
                                 f'删除验收记录 ID={acc_id}（合同ID={row["contract_id"]} 金额={row["acceptance_amount"]}）')
        except Exception:
            pass
        return jsonify({'code': 200, 'message': '删除成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@contracts_bp.route('/api/contracts/import-parse', methods=['POST'])
@token_required
def import_parse_contracts():
    if 'file' not in request.files:
        return jsonify({'code': 400, 'message': '请选择文件', 'data': None})

    file = request.files['file']
    if file.filename == '':
        return jsonify({'code': 400, 'message': '请选择文件', 'data': None})

    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'code': 400, 'message': '仅支持Excel文件（.xlsx/.xls）', 'data': None})

    try:
        from openpyxl import load_workbook

        wb = load_workbook(BytesIO(file.read()), data_only=True)
        ws = wb.active

        headers = [cell.value for cell in ws[1]]
        col_map = {}
        for idx, header in enumerate(headers):
            header = str(header).strip() if header else ''
            if header == '合同编号':
                col_map['contract_no'] = idx
            elif header == '合同名称':
                col_map['contract_name'] = idx
            elif header == '甲方':
                col_map['party_a'] = idx
            elif header == '项目令号':
                col_map['project_order_no'] = idx
            elif header == '合同总额(万)':
                col_map['total_amt'] = idx
            elif header == '签约日期':
                col_map['sign_date'] = idx
            elif header == '业态':
                col_map['business_type'] = idx
            elif header == '密级':
                col_map['classification'] = idx
            elif header == '负责人':
                col_map['owner_name'] = idx
            elif header == '验收节点':
                col_map['acceptance_nodes'] = idx
            elif header == '回款节点':
                col_map['payment_nodes'] = idx

        required_cols = ['contract_no', 'contract_name', 'total_amt']
        for col in required_cols:
            if col not in col_map:
                return jsonify({'code': 400, 'message': f'缺少必要列：{col}', 'data': None})

        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT contract_no FROM contracts")
        existing_nos = set(row[0] for row in cursor.fetchall())

        rows = []
        batch_nos = set()
        valid_count = 0

        for row_idx in range(2, ws.max_row + 1):
            row_data = {}
            errors = []

            for key, idx in col_map.items():
                cell = ws.cell(row=row_idx, column=idx + 1)
                value = cell.value

                if key == 'total_amt':
                    if value is None:
                        errors.append('合同总额不能为空')
                    else:
                        try:
                            value = float(value) * 10000
                        except:
                            errors.append('合同总额格式错误')
                elif key == 'sign_date':
                    if value:
                        if isinstance(value, datetime):
                            value = value.strftime('%Y-%m-%d')
                        else:
                            value = str(value)[:10]

                row_data[key] = value

            contract_no = row_data.get('contract_no')
            if contract_no:
                contract_no = str(contract_no).strip()
                row_data['contract_no'] = contract_no

                if contract_no in existing_nos:
                    errors.append('合同编号已存在')
                if contract_no in batch_nos:
                    errors.append('批内合同编号重复')
                batch_nos.add(contract_no)

            contract_name = row_data.get('contract_name')
            if not contract_name:
                errors.append('合同名称不能为空')

            valid = len(errors) == 0
            if valid:
                valid_count += 1

            rows.append({
                'row_index': row_idx,
                'data': row_data,
                'valid': valid,
                'errors': errors
            })

        return jsonify({
            'code': 200,
            'message': '解析成功',
            'data': {
                'total': len(rows),
                'valid_count': valid_count,
                'invalid_count': len(rows) - valid_count,
                'rows': rows
            }
        })

    except Exception as e:
        return jsonify({'code': 500, 'message': f'解析失败：{str(e)}', 'data': None})


@contracts_bp.route('/api/contracts/import-execute', methods=['POST'])
@token_required
def import_execute_contracts():
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    if not data or not isinstance(data, list):
        return jsonify({'code': 400, 'message': '数据格式错误', 'data': None})

    db = get_db()
    cursor = db.cursor()

    success_count = 0
    fail_count = 0
    results = []

    cursor.execute("SELECT contract_no FROM contracts")
    existing_nos = set(row[0] for row in cursor.fetchall())

    for item in data:
        row_data = item.get('data', {})
        row_index = item.get('row_index', 0)

        contract_no = row_data.get('contract_no')
        if not contract_no or contract_no in existing_nos:
            results.append({
                'row_index': row_index,
                'success': False,
                'message': '合同编号已存在或为空'
            })
            fail_count += 1
            continue

        try:
            cursor.execute("""
                INSERT INTO contracts
                (contract_no, party_a, project_order_no, total_amt, paid_amt, sign_date, owner_id, status,
                 contract_name, classification, is_audit, pending_acceptance_amount,
                 cost, gross_profit, acceptance_date, expected_income_date,
                 expected_income_year, business_type, total_cost, acceptance_nodes, payment_nodes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """, (
                contract_no,
                row_data.get('party_a'),
                row_data.get('project_order_no'),
                row_data.get('total_amt', 0),
                0,
                row_data.get('sign_date'),
                payload['username'],
                '执行中',
                row_data.get('contract_name'),
                row_data.get('classification'),
                0,
                0,
                0,
                0,
                '',
                '',
                '',
                row_data.get('business_type'),
                row_data.get('acceptance_nodes'),
                row_data.get('payment_nodes')
            ))

            existing_nos.add(contract_no)
            success_count += 1
            results.append({
                'row_index': row_index,
                'success': True,
                'message': '导入成功'
            })
        except Exception as e:
            fail_count += 1
            results.append({
                'row_index': row_index,
                'success': False,
                'message': str(e)
            })

    db.commit()

    return jsonify({
        'code': 200,
        'message': '导入完成',
        'data': {
            'total': len(data),
            'success_count': success_count,
            'fail_count': fail_count,
            'results': results
        }
    })


@contracts_bp.route('/api/contracts/<int:contract_id>', methods=['DELETE'])
@token_required
def delete_contract(contract_id):
    payload = request.current_user
    role = payload.get('role', '')
    if role != '主任' and role != '院长':
        return jsonify({'code': 403, 'message': '权限不足，仅主任和院长可删除合同', 'data': None})

    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("SELECT contract_name, contract_no FROM contracts WHERE id=?", (contract_id,))
        row = cursor.fetchone()
        contract_info = f"{row['contract_name']}（{row['contract_no']}）" if row else f"ID:{contract_id}"

        cursor.execute("DELETE FROM payment_records WHERE contract_id = ?", (contract_id,))
        cursor.execute("DELETE FROM contracts WHERE id=?", (contract_id,))
        db.commit()

        record_operation_log(payload['username'], '删除', '合同', f'删除合同：{contract_info}')

        return jsonify({'code': 200, 'message': '合同删除成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@contracts_bp.route('/api/contracts/upload', methods=['POST'])
@token_required
def upload_contract_file():
    contract_id = request.form.get('contract_id', type=int)
    file_type = request.form.get('file_type')

    if 'file' not in request.files:
        return jsonify({'code': 400, 'message': '请选择文件', 'data': None})

    file = request.files['file']
    if file.filename == '':
        return jsonify({'code': 400, 'message': '请选择文件', 'data': None})

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _, ext = os.path.splitext(file.filename)
    filename = f"{contract_id}_{file_type}_{timestamp}{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)

    file.save(file_path)

    db = get_db()
    cursor = db.cursor()

    if file_type == 'contract':
        cursor.execute("UPDATE contracts SET contract_file_path = ? WHERE id = ?", (f"uploads/contracts/{filename}", contract_id))
    elif file_type == 'tech':
        cursor.execute("UPDATE contracts SET tech_agreement_file_path = ? WHERE id = ?", (f"uploads/contracts/{filename}", contract_id))

    db.commit()

    return jsonify({'code': 200, 'message': '文件上传成功', 'data': {'file_path': f"uploads/contracts/{filename}"}})


@contracts_bp.route('/api/contracts/test-download', methods=['GET'])
def test_download_route():
    return jsonify({'code': 200, 'message': '测试路由工作正常', 'data': None})


@contracts_bp.route('/api/download-contract', methods=['GET'])
def download_contract_file():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        token = request.args.get('token', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})

    contract_id = request.args.get('id', type=int)
    file_type = request.args.get('type')

    if not contract_id or not file_type:
        return jsonify({'code': 400, 'message': '参数错误', 'data': None})

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM contracts WHERE id = ?", (contract_id,))
    row = cursor.fetchone()

    if not row:
        return jsonify({'code': 404, 'message': '合同不存在', 'data': None})

    row_dict = dict(row)

    if file_type == 'contract':
        file_path = row_dict.get('contract_file_path')
    elif file_type == 'tech':
        file_path = row_dict.get('tech_agreement_file_path')
    else:
        return jsonify({'code': 400, 'message': '无效的文件类型', 'data': None})

    if not file_path:
        return jsonify({'code': 404, 'message': '文件不存在', 'data': None})

    filename = os.path.basename(file_path)
    full_path = os.path.join(UPLOAD_DIR, filename)

    if not os.path.exists(full_path):
        return jsonify({'code': 404, 'message': '文件不存在', 'data': None})

    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)


def register_routes(app):
    app.register_blueprint(contracts_bp)