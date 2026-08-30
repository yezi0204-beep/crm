"""自定义字段模块

支持为客户（customer）与商机（business）对象动态扩展字段：
- 字段元数据表 custom_fields（类型：text/number/date/select/multiselect）
- 业务表通过 ext_data JSON 列存储自定义值
- 写入时按元数据校验（类型/必填/选项），读取时解析为对象

权限：字段定义管理需 data.view_all；定义列表对所有登录用户开放（渲染表单用）。
"""
import json
from flask import request, jsonify

from extensions import get_db, token_required, record_operation_log, user_can

from . import custom_fields_bp

OBJECT_TYPES = ('customer', 'business')
FIELD_TYPES = ('text', 'number', 'date', 'select', 'multiselect')


def _parse_options(field):
    """options 存储 JSON 数组字符串，返回数组；兼容逗号分隔的旧格式。"""
    raw = field['options']
    if not raw:
        return []
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else []
    except (ValueError, TypeError):
        return [s.strip() for s in str(raw).split(',') if s.strip()]


def _field_dict(row):
    d = dict(row)
    d['options'] = _parse_options(d)
    d['required'] = bool(d['required'])
    d['is_active'] = bool(d['is_active'])
    return d


def get_active_fields(cursor, object_type):
    """查询对象类型的启用字段定义（按 sort_order, id 排序）。"""
    cursor.execute(
        "SELECT * FROM custom_fields WHERE object_type=? AND is_active=1 ORDER BY sort_order, id",
        (object_type,))
    return [_field_dict(r) for r in cursor.fetchall()]


def parse_ext(row_dict):
    """将查询结果中的 ext_data JSON 字符串解析为对象（原地修改）。"""
    raw = row_dict.get('ext_data')
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            parsed = {}
    elif isinstance(raw, dict):
        parsed = raw
    else:
        parsed = {}
    row_dict['ext_data'] = parsed
    return row_dict


def validate_ext(cursor, object_type, ext_data):
    """按字段元数据校验并清洗 ext_data。

    返回 (cleaned_dict, None) 或 (None, 错误消息)。
    必填校验独立于 ext_data 是否为空（空提交同样拦截）；
    未定义的 key 会被丢弃；空值字段不落库。
    """
    if ext_data is None:
        ext_data = {}
    if not isinstance(ext_data, dict):
        return None, 'ext_data 必须为对象'

    fields = get_active_fields(cursor, object_type)
    defined = {f['field_key']: f for f in fields}

    # 必填校验：不依赖提交内容，未填即拦截
    for f in fields:
        if f['required'] and ext_data.get(f['field_key']) in (None, '', []):
            return None, f"自定义字段「{f['field_name']}」为必填项"

    cleaned = {}
    for key, value in ext_data.items():
        field = defined.get(key)
        if not field:
            continue  # 丢弃未定义的 key，避免脏数据
        if value in (None, '', []):
            if field['required']:
                return None, f"自定义字段「{field['field_name']}」为必填项"
            continue

        ftype = field['field_type']
        try:
            if ftype == 'number':
                num = float(value)
                value = int(num) if num == int(num) else num
            elif ftype == 'date':
                if not isinstance(value, str) or len(value) < 8:
                    return None, f"自定义字段「{field['field_name']}」日期格式不正确"
            elif ftype == 'select':
                opts = field['options']
                if opts and str(value) not in opts:
                    return None, f"自定义字段「{field['field_name']}」的值不在可选项中"
                value = str(value)
            elif ftype == 'multiselect':
                if not isinstance(value, list):
                    return None, f"自定义字段「{field['field_name']}」必须为多选数组"
                opts = field['options']
                if opts:
                    bad = [v for v in value if str(v) not in opts]
                    if bad:
                        return None, f"自定义字段「{field['field_name']}」包含无效选项：{'、'.join(str(b) for b in bad)}"
                value = [str(v) for v in value]
            else:  # text
                value = str(value)
        except (ValueError, TypeError):
            return None, f"自定义字段「{field['field_name']}」的值类型不正确"
        cleaned[key] = value
    return cleaned, None


@custom_fields_bp.route('/api/custom-fields', methods=['GET'])
@token_required
def list_custom_fields():
    """字段定义列表（渲染表单/表格用）。is_active=0 的仅管理视图可见。"""
    object_type = request.args.get('object_type', 'customer')
    if object_type not in OBJECT_TYPES:
        return jsonify({'code': 400, 'message': f'object_type 必须为 {OBJECT_TYPES} 之一', 'data': None})
    include_inactive = request.args.get('include_inactive', '0') == '1'

    db = get_db()
    cursor = db.cursor()
    if include_inactive:
        cursor.execute(
            "SELECT * FROM custom_fields WHERE object_type=? ORDER BY sort_order, id", (object_type,))
    else:
        cursor.execute(
            "SELECT * FROM custom_fields WHERE object_type=? AND is_active=1 ORDER BY sort_order, id",
            (object_type,))
    return jsonify({'code': 200, 'message': 'success', 'data': [_field_dict(r) for r in cursor.fetchall()]})


@custom_fields_bp.route('/api/custom-fields', methods=['POST'])
@token_required
def create_custom_field():
    payload = request.current_user
    if not user_can(payload['username'], 'data.view_all'):
        return jsonify({'code': 403, 'message': '权限不足，仅管理层可管理自定义字段', 'data': None})

    data = request.get_json(silent=True) or {}
    object_type = data.get('object_type')
    field_name = (data.get('field_name') or '').strip()
    field_type = data.get('field_type') or 'text'

    if object_type not in OBJECT_TYPES:
        return jsonify({'code': 400, 'message': 'object_type 无效', 'data': None})
    if not field_name:
        return jsonify({'code': 400, 'message': '字段名称不能为空', 'data': None})
    if field_type not in FIELD_TYPES:
        return jsonify({'code': 400, 'message': f'field_type 必须为 {FIELD_TYPES} 之一', 'data': None})

    options = data.get('options') or []
    if field_type in ('select', 'multiselect') and not options:
        return jsonify({'code': 400, 'message': '选择型字段必须配置可选项', 'data': None})

    db = get_db()
    cursor = db.cursor()

    # field_key 自动生成，保证稳定且唯一
    import time
    field_key = f"cf_{object_type[:2]}_{int(time.time() * 1000) % 10_000_000_000}"
    try:
        cursor.execute("""
            INSERT INTO custom_fields (object_type, field_key, field_name, field_type,
                options, required, sort_order, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            object_type, field_key, field_name, field_type,
            json.dumps(options, ensure_ascii=False) if options else None,
            1 if data.get('required') else 0,
            int(data.get('sort_order') or 0)
        ))
        db.commit()
        record_operation_log(payload['username'], '创建', '自定义字段',
                             f'{object_type} 新增字段「{field_name}」（{field_type}）')
        return jsonify({'code': 200, 'message': '字段创建成功', 'data': {'id': cursor.lastrowid, 'field_key': field_key}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@custom_fields_bp.route('/api/custom-fields/<int:field_id>', methods=['PUT'])
@token_required
def update_custom_field(field_id):
    payload = request.current_user
    if not user_can(payload['username'], 'data.view_all'):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    data = request.get_json(silent=True) or {}
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT * FROM custom_fields WHERE id=?", (field_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '字段不存在', 'data': None})

    field_name = (data.get('field_name') or row['field_name']).strip()
    if not field_name:
        return jsonify({'code': 400, 'message': '字段名称不能为空', 'data': None})

    field_type = data.get('field_type') or row['field_type']
    if field_type not in FIELD_TYPES:
        return jsonify({'code': 400, 'message': 'field_type 无效', 'data': None})

    options = data.get('options')
    if options is None:
        options = _parse_options(row)
    if field_type in ('select', 'multiselect') and not options:
        return jsonify({'code': 400, 'message': '选择型字段必须配置可选项', 'data': None})

    try:
        cursor.execute("""
            UPDATE custom_fields SET
                field_name=?, field_type=?, options=?, required=?, sort_order=?, is_active=?
            WHERE id=?
        """, (
            field_name, field_type,
            json.dumps(options, ensure_ascii=False) if options else None,
            1 if data.get('required', bool(row['required'])) else 0,
            int(data.get('sort_order') or row['sort_order'] or 0),
            1 if data.get('is_active', bool(row['is_active'])) else 0,
            field_id
        ))
        db.commit()
        record_operation_log(payload['username'], '编辑', '自定义字段', f'编辑字段「{field_name}」ID:{field_id}')
        return jsonify({'code': 200, 'message': '字段更新成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@custom_fields_bp.route('/api/custom-fields/<int:field_id>', methods=['DELETE'])
@token_required
def delete_custom_field(field_id):
    """物理删除字段定义（ext_data 中历史值保留但不再展示/校验）。"""
    payload = request.current_user
    if not user_can(payload['username'], 'data.view_all'):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT field_name FROM custom_fields WHERE id=?", (field_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '字段不存在', 'data': None})

    try:
        cursor.execute("DELETE FROM custom_fields WHERE id=?", (field_id,))
        db.commit()
        record_operation_log(payload['username'], '删除', '自定义字段', f'删除字段「{row["field_name"]}」ID:{field_id}')
        return jsonify({'code': 200, 'message': '字段删除成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


def register_routes(app):
    app.register_blueprint(custom_fields_bp)
