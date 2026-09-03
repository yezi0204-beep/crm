"""数据源管理（插件式采集器）

lead_sources 表驱动：每个数据源绑定一个采集器插件（parser_type），
插件在 backend/collectors/*.py 中注册即可，业务代码无需改动。

路由（管理权限：system.admin 或 data.view_all）：
  GET    /api/data-sources              列表（搜索/筛选/分页）
  GET    /api/data-sources/<id>         详情
  POST   /api/data-sources              新增
  PUT    /api/data-sources/<id>         修改
  DELETE /api/data-sources/<id>         删除
  POST   /api/data-sources/<id>/toggle  启用/停用切换
  POST   /api/data-sources/<id>/collect 手动触发采集
  GET    /api/data-sources/meta/collectors  已注册采集器枚举
  GET    /api/data-sources/meta/options     数据源类型/采集方式/频率等枚举
"""
import json
from datetime import datetime, timedelta

from flask import request, jsonify

from extensions import get_db, token_required, user_can, record_operation_log

from . import data_sources_bp


# 数据源类型枚举
SOURCE_TYPES = [
    {'value': '政府采购', 'label': '政府采购'},
    {'value': '公共资源交易', 'label': '公共资源交易'},
    {'value': '采购意向', 'label': '采购意向'},
    {'value': '招标公告', 'label': '招标公告'},
    {'value': '中标公告', 'label': '中标公告'},
    {'value': '企业官网', 'label': '企业官网'},
    {'value': '行业网站', 'label': '行业网站'},
    {'value': '新闻', 'label': '新闻'},
    {'value': 'RSS', 'label': 'RSS'},
    {'value': 'API', 'label': 'API'},
]

# 采集方式（用户可见分类）
COLLECTION_METHODS = [
    {'value': '自动采集', 'label': '自动采集（定时）'},
    {'value': '手动采集', 'label': '手动采集（仅手动触发）'},
    {'value': 'RSS订阅', 'label': 'RSS 订阅'},
    {'value': 'API对接', 'label': 'API 对接'},
    {'value': 'AI搜索', 'label': 'AI 智能搜索'},
]

# 采集频率（对应 interval_hours，仅作为 UI 枚举）
FREQUENCIES = [
    {'value': '每小时', 'label': '每小时', 'hours': 1},
    {'value': '每4小时', 'label': '每 4 小时', 'hours': 4},
    {'value': '每6小时', 'label': '每 6 小时', 'hours': 6},
    {'value': '每8小时', 'label': '每 8 小时', 'hours': 8},
    {'value': '每12小时', 'label': '每 12 小时', 'hours': 12},
    {'value': '每日', 'label': '每日', 'hours': 24},
    {'value': '每周', 'label': '每周', 'hours': 24 * 7},
    {'value': '每月', 'label': '每月', 'hours': 24 * 30},
]

REGION_OPTIONS = ['全国', '华北', '华东', '华南', '华中', '西南', '西北', '东北', '北京', '上海', '广东', '江苏', '浙江', '四川', '山东', '河南', '陕西']
INDUSTRY_OPTIONS = ['信息技术', '军工装备', '航空航天', '农业农村', '水利气象', '生态环保', '政府政务', '教育科研', '医疗卫生', '交通运输', '能源电力', '金融', '制造', '综合']


# ==================== 工具函数 ====================

def _require_admin():
    """需要 system.admin 或 data.view_all 权限。"""
    username = request.current_user['username']
    return user_can(username, 'system.admin') or user_can(username, 'data.view_all')


def _frequency_to_hours(frequency):
    for f in FREQUENCIES:
        if f['value'] == frequency:
            return f['hours']
    return 24


def _calc_next_collect(interval_hours, method='自动采集'):
    if method == '手动采集':
        return ''
    try:
        return (datetime.now() + timedelta(hours=int(interval_hours or 24))).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return ''


def _row_to_dict(row):
    return {
        'id': row['id'],
        'name': row['name'],
        'source_type': row['source_type'] or '',
        'url': row['url'] or '',
        'industry': row['industry'] or '',
        'region': row['region'] or '',
        'parser_type': row['parser_type'] or '',
        'collection_method': row['collection_method'] or '自动采集',
        'frequency': row['frequency'] or '每日',
        'interval_hours': row['interval_hours'],
        'enabled': bool(row['enabled']),
        'last_scraped_at': row['last_scraped_at'] or '',
        'next_collect_at': row['next_collect_at'] or '',
        'notes': row['notes'] or '',
        'keywords': row['keywords'] or '',
        'config': None,  # 不直接透出 JSON 配置给列表
        'created_at': row['created_at'] or '',
    }


# ==================== 路由 ====================

@data_sources_bp.route('/api/data-sources/meta/options', methods=['GET'])
@token_required
def meta_options():
    return jsonify({
        'code': 200, 'message': 'success',
        'data': {
            'source_types': SOURCE_TYPES,
            'collection_methods': COLLECTION_METHODS,
            'frequencies': FREQUENCIES,
            'industries': INDUSTRY_OPTIONS,
            'regions': REGION_OPTIONS,
        }
    })


@data_sources_bp.route('/api/data-sources/meta/collectors', methods=['GET'])
@token_required
def meta_collectors():
    try:
        from collectors import list_collectors
        items = [{'value': k, 'label': v} for k, v in list_collectors().items()]
    except Exception as e:
        items = []
    return jsonify({'code': 200, 'message': 'success', 'data': items})


@data_sources_bp.route('/api/data-sources', methods=['GET'])
@token_required
def list_sources():
    if not _require_admin():
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    kw = (request.args.get('keyword') or '').strip()
    st = (request.args.get('source_type') or '').strip()
    ind = (request.args.get('industry') or '').strip()
    reg = (request.args.get('region') or '').strip()
    enabled_arg = request.args.get('enabled')
    try:
        page = max(1, int(request.args.get('page', 1) or 1))
        page_size = max(1, min(200, int(request.args.get('page_size', 20) or 20)))
    except ValueError:
        page, page_size = 1, 20

    db = get_db()
    where, args = [], []
    if kw:
        where.append("(name LIKE ? OR url LIKE ? OR notes LIKE ? OR keywords LIKE ?)")
        like = f'%{kw}%'
        args.extend([like, like, like, like])
    if st:
        where.append("source_type=?")
        args.append(st)
    if ind:
        where.append("industry=?")
        args.append(ind)
    if reg:
        where.append("region=?")
        args.append(reg)
    if enabled_arg in ('0', '1'):
        where.append("enabled=?")
        args.append(int(enabled_arg))
    where_sql = f"WHERE {' AND '.join(where)}" if where else ''

    total = db.execute(f"SELECT COUNT(*) as c FROM lead_sources {where_sql}", args).fetchone()['c']
    rows = db.execute(
        f"SELECT * FROM lead_sources {where_sql} ORDER BY enabled DESC, COALESCE(last_scraped_at,'') DESC, id DESC LIMIT ? OFFSET ?",
        [*args, page_size, (page - 1) * page_size]).fetchall()
    return jsonify({
        'code': 200, 'message': 'success',
        'data': [_row_to_dict(r) for r in rows],
        'total': total,
        'page': page, 'page_size': page_size
    })


@data_sources_bp.route('/api/data-sources/<int:sid>', methods=['GET'])
@token_required
def get_source(sid):
    if not _require_admin():
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    db = get_db()
    row = db.execute("SELECT * FROM lead_sources WHERE id=?", (sid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '数据源不存在', 'data': None})
    d = _row_to_dict(row)
    try:
        d['config'] = json.loads(row['config']) if row['config'] else {}
    except Exception:
        d['config'] = {}
    return jsonify({'code': 200, 'message': 'success', 'data': d})


@data_sources_bp.route('/api/data-sources', methods=['POST'])
@token_required
def create_source():
    payload = request.current_user
    if not _require_admin():
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    b = request.get_json(silent=True) or {}
    name = (b.get('name') or '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '数据源名称不能为空', 'data': None})
    parser_type = (b.get('parser_type') or '').strip()
    frequency = (b.get('frequency') or '每日')
    interval_hours = _frequency_to_hours(frequency)
    method = (b.get('collection_method') or '自动采集')
    config_obj = b.get('config') if isinstance(b.get('config'), dict) else {}
    if b.get('max_items') is not None:
        config_obj.setdefault('max_items', int(b['max_items']))
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO lead_sources (name, source_type, url, keywords, industry, region, enabled,
            parser_type, collection_method, frequency, interval_hours, next_collect_at, notes, config)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, b.get('source_type') or '', b.get('url') or '',
          b.get('keywords') or '', b.get('industry') or '', b.get('region') or '',
          1 if b.get('enabled', True) else 0,
          parser_type, method, frequency, interval_hours, _calc_next_collect(interval_hours, method),
          b.get('notes') or '', json.dumps(config_obj, ensure_ascii=False)))
    db.commit()
    record_operation_log(payload['username'], '新增', '数据源', name)
    return jsonify({'code': 200, 'message': 'success', 'data': {'id': cur.lastrowid}})


@data_sources_bp.route('/api/data-sources/<int:sid>', methods=['PUT'])
@token_required
def update_source(sid):
    payload = request.current_user
    if not _require_admin():
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    db = get_db()
    row = db.execute("SELECT * FROM lead_sources WHERE id=?", (sid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '数据源不存在', 'data': None})
    b = request.get_json(silent=True) or {}
    name = (b.get('name', row['name']) or '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '数据源名称不能为空', 'data': None})
    frequency = b.get('frequency') if b.get('frequency') is not None else row['frequency'] or '每日'
    interval_hours = _frequency_to_hours(frequency)
    method = b.get('collection_method') if b.get('collection_method') is not None else (row['collection_method'] or '自动采集')
    parser_type = b.get('parser_type') if b.get('parser_type') is not None else (row['parser_type'] or '')
    config_obj = b.get('config') if isinstance(b.get('config'), dict) else None
    if config_obj is None:
        try:
            config_obj = json.loads(row['config']) if row['config'] else {}
        except Exception:
            config_obj = {}

    cur = db.cursor()
    cur.execute("""
        UPDATE lead_sources SET name=?, source_type=?, url=?, keywords=?, industry=?, region=?,
            enabled=?, parser_type=?, collection_method=?, frequency=?, interval_hours=?,
            next_collect_at=?, notes=?, config=?
        WHERE id=?
    """, (
        name, b.get('source_type', row['source_type'] or ''),
        b.get('url', row['url'] or ''),
        b.get('keywords', row['keywords'] or ''),
        b.get('industry', row['industry'] or ''),
        b.get('region', row['region'] or ''),
        1 if b.get('enabled', bool(row['enabled'])) else 0,
        parser_type, method, frequency, interval_hours,
        _calc_next_collect(interval_hours, method),
        b.get('notes', row['notes'] or ''),
        json.dumps(config_obj, ensure_ascii=False),
        sid
    ))
    db.commit()
    record_operation_log(payload['username'], '修改', '数据源', f'{name}(id={sid})')
    return jsonify({'code': 200, 'message': 'success', 'data': None})


@data_sources_bp.route('/api/data-sources/<int:sid>', methods=['DELETE'])
@token_required
def delete_source(sid):
    payload = request.current_user
    if not _require_admin():
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    db = get_db()
    row = db.execute("SELECT name FROM lead_sources WHERE id=?", (sid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '数据源不存在', 'data': None})
    cur = db.cursor()
    # raw_intelligence 保留（来源 id 置空），不 cascade 删除
    cur.execute("UPDATE raw_intelligence SET source_id=NULL WHERE source_id=?", (sid,))
    cur.execute("DELETE FROM lead_sources WHERE id=?", (sid,))
    db.commit()
    record_operation_log(payload['username'], '删除', '数据源', f"{row['name']}(id={sid})")
    return jsonify({'code': 200, 'message': 'success', 'data': None})


@data_sources_bp.route('/api/data-sources/<int:sid>/toggle', methods=['POST'])
@token_required
def toggle_source(sid):
    payload = request.current_user
    if not _require_admin():
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    db = get_db()
    row = db.execute("SELECT * FROM lead_sources WHERE id=?", (sid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '数据源不存在', 'data': None})
    new_enabled = 0 if row['enabled'] else 1
    cur = db.cursor()
    cur.execute("UPDATE lead_sources SET enabled=? WHERE id=?", (new_enabled, sid))
    db.commit()
    record_operation_log(payload['username'], '启用停用', '数据源',
                         f"{row['name']} -> {'启用' if new_enabled else '停用'}")
    return jsonify({'code': 200, 'message': 'success',
                    'data': {'id': sid, 'enabled': bool(new_enabled)}})


@data_sources_bp.route('/api/data-sources/<int:sid>/collect', methods=['POST'])
@token_required
def collect_source(sid):
    if not _require_admin():
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    # 直接转发复用 /intelligence/collect 逻辑（支持 fetch_detail 参数）
    from .intelligence import collect_source as do_collect
    try:
        from werkzeug.test import EnvironBuilder
        from flask import request as f_req
        # 构造子请求（复用请求上下文）
        original_path = f_req.path
        builder = EnvironBuilder(method='GET',
                                 query_string=f'source_id={sid}&fetch_detail=1',
                                 headers={k: v for k, v in f_req.headers.items()})
        # 直接调用现有路由函数需要 path 改变，简化处理：直接运行其内部逻辑
    except Exception:
        pass
    # 直接重写一个最小版本：读取 source -> 加载采集器 -> 走 intelligence 的 _load_content_matcher -> 保存
    try:
        db = get_db()
        source = db.execute("SELECT * FROM lead_sources WHERE id=?", (sid,)).fetchone()
        if not source:
            return jsonify({'code': 404, 'message': '数据源不存在', 'data': None})
        parser_type = source['parser_type']
        if not parser_type:
            return jsonify({'code': 400, 'message': '该数据源未配置采集器(parser_type)，无法采集', 'data': None})
        from collectors import get_collector
        collector_cls = get_collector(parser_type)
        if not collector_cls:
            return jsonify({'code': 400, 'message': f'采集器插件不存在: {parser_type}', 'data': None})
        try:
            import os, json as _json
            config = _json.loads(source['config']) if source.get('config') else {}
        except Exception:
            config = {}
        source_dict = {
            'id': source['id'], 'name': source['name'],
            'url': source['url'] or '', 'keywords': source['keywords'] or '',
            'category': source['category'] or '', 'parser_type': parser_type,
        }
        collector = collector_cls(source_dict, config)
        items = collector.collect() or []
        # 复用 intelligence 的匹配 + 保存
        from .intelligence import _load_content_matcher, _match_content, _save_raw_intelligence
        matcher = _load_content_matcher(db)
        new_count, filtered_count, error_count = 0, 0, 0
        for item in items:
            try:
                if item.url:
                    item = collector.fetch_detail(item)
                from utils.cleaner import clean_title, is_junk_content
                title = clean_title(item.title) if item.title else ''
                keep, matched = _match_content(title, item.content, item.snippet, matcher)
                if not keep:
                    filtered_count += 1
                    continue
                if is_junk_content(item.content, title):
                    continue
                _, is_new = _save_raw_intelligence(
                    source_id=sid, url=item.url, title=title,
                    content=item.content or '', publish_date=item.publish_date or '',
                    snippet=item.snippet or '',
                    attachment_path=','.join(item.attachment_urls) if item.attachment_urls else '',
                    keywords_matched=','.join(matched))
                if is_new:
                    new_count += 1
            except Exception as _e:
                error_count += 1
        # 更新最后采集时间 + 下次采集时间
        cur = db.cursor()
        frequency = source['frequency'] or '每日'
        interval_hours = _frequency_to_hours(frequency)
        method = source['collection_method'] or '自动采集'
        cur.execute("UPDATE lead_sources SET last_scraped_at=CURRENT_TIMESTAMP, next_collect_at=? WHERE id=?",
                    (_calc_next_collect(interval_hours, method), sid))
        db.commit()
        record_operation_log(request.current_user['username'], '手动采集', '数据源',
                             f"{source['name']} -> 入库{new_count}条，过滤{filtered_count}条，异常{error_count}条")
        return jsonify({
            'code': 200, 'message': f'采集完成，入库 {new_count} 条，过滤 {filtered_count} 条，异常 {error_count} 条',
            'data': {'new_count': new_count, 'filtered_count': filtered_count,
                     'error_count': error_count, 'collected': len(items)}
        })
    except Exception as e:
        return jsonify({'code': 500, 'message': f'采集失败: {e}', 'data': None})


def register_routes(app):
    app.register_blueprint(data_sources_bp)
