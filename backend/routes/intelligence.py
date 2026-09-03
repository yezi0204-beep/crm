"""原始情报 API：统一采集池，所有数据源的原始数据。

Phase1: 列表 + 详情
Phase2: 手动采集触发 + 详情抓取 + 附件解析
"""
from flask import Blueprint, request, jsonify
from extensions import get_db, token_required, admin_required, app_center_or_admin_required, record_operation_log
import hashlib
import json
import logging

logger = logging.getLogger(__name__)
intelligence_bp = Blueprint('intelligence', __name__)


def register_routes(app):
    app.register_blueprint(intelligence_bp, url_prefix='/api/intelligence')


@intelligence_bp.route('', methods=['GET'])
@token_required
def list_intelligence():
    """原始情报列表，支持分页/状态/来源过滤。"""
    db = get_db()
    status = request.args.get('status', '')
    source_id = request.args.get('source_id', type=int)
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page

    sql = """
        SELECT ri.id, ri.source_id, ri.url, ri.title, ri.publish_date,
               ri.collected_at, ri.status, ri.error_message,
               ls.name as source_name,
               il.id as lead_id, il.score as lead_score, il.score_grade as lead_grade,
               ag.id as agent_result_id, ag.final_score as agent_score
        FROM raw_intelligence ri
        LEFT JOIN lead_sources ls ON ri.source_id = ls.id
        LEFT JOIN intelligence_leads il ON il.raw_intelligence_id = ri.id
        LEFT JOIN intelligence_agent_results ag ON ag.raw_intelligence_id = ri.id
        WHERE 1=1
    """
    params = []
    if status:
        sql += " AND ri.status = ?"
        params.append(status)
    if source_id:
        sql += " AND ri.source_id = ?"
        params.append(source_id)
    if search:
        sql += " AND (ri.title LIKE ? OR ri.content LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%'])

    total = db.execute(f"SELECT COUNT(*) as cnt FROM ({sql})", params).fetchone()['cnt']
    sql += " ORDER BY ri.collected_at DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    rows = db.execute(sql, params).fetchall()
    return jsonify({
        'code': 200,
        'data': [dict(r) for r in rows],
        'total': total,
        'page': page,
        'per_page': per_page
    })


@intelligence_bp.route('/<int:rid>', methods=['GET'])
@token_required
def get_intelligence(rid):
    """情报详情。"""
    db = get_db()
    row = db.execute("""
        SELECT ri.*, ls.name as source_name
        FROM raw_intelligence ri
        LEFT JOIN lead_sources ls ON ri.source_id = ls.id
        WHERE ri.id = ?
    """, (rid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '情报不存在'})
    return jsonify({'code': 200, 'data': dict(row)})


@intelligence_bp.route('/stats', methods=['GET'])
@token_required
def intelligence_stats():
    """情报统计（按状态分组）。"""
    db = get_db()
    rows = db.execute("""
        SELECT status, COUNT(*) as count
        FROM raw_intelligence
        GROUP BY status
    """).fetchall()
    stats = {r['status']: r['count'] for r in rows}
    # 补全状态
    for s in ['pending', 'processing', 'analyzed', 'invalid']:
        if s not in stats:
            stats[s] = 0
    return jsonify({'code': 200, 'data': stats})


@intelligence_bp.route('/<int:rid>', methods=['DELETE'])
@token_required
def delete_intelligence(rid):
    """删除情报。"""
    db = get_db()
    db.execute("DELETE FROM raw_intelligence WHERE id=?", (rid,))
    db.commit()
    record_operation_log(request.current_user, 'delete', 'raw_intelligence', f'删除情报:{rid}')
    return jsonify({'code': 200, 'message': '已删除'})


@intelligence_bp.route('/batch-delete', methods=['POST'])
@token_required
def batch_delete_intelligence():
    """批量删除情报。"""
    data = request.get_json(silent=True) or {}
    try:
        ids = [int(i) for i in (data.get('ids') or [])]
    except (TypeError, ValueError):
        ids = []
    ids = [i for i in ids if i > 0]
    if not ids:
        return jsonify({'code': 400, 'message': '请选择要删除的情报'})

    db = get_db()
    placeholders = ','.join('?' * len(ids))
    cur = db.execute(f"DELETE FROM raw_intelligence WHERE id IN ({placeholders})", ids)
    db.commit()
    record_operation_log(
        request.current_user, 'batch_delete', 'raw_intelligence',
        f'批量删除情报{cur.rowcount}条'
    )
    return jsonify({'code': 200, 'message': f'已删除{cur.rowcount}条', 'data': {'deleted': cur.rowcount}})


def _load_active_keywords(db):
    """读取关键词管理中启用的关键词。

    返回 (匹配词列表, 排除词列表)：匹配词 = 主词 + 同义词；排除词来自 exclude_words。
    """
    rows = db.execute(
        "SELECT keyword, synonyms, exclude_words FROM keywords WHERE enabled=1"
    ).fetchall()
    match_list, exclude_list = [], []
    for r in rows:
        kw = (r['keyword'] or '').strip()
        if kw and kw not in match_list:
            match_list.append(kw)
        if r['synonyms']:
            for s in r['synonyms'].split(','):
                s = s.strip()
                if s and s not in match_list:
                    match_list.append(s)
        if r['exclude_words']:
            for s in r['exclude_words'].split(','):
                s = s.strip()
                if s and s not in exclude_list:
                    exclude_list.append(s)
    return match_list, exclude_list


def _match_business_keywords(title, content, snippet, match_list, exclude_list):
    """按关键词管理配置判断内容是否与业务相关。

    规则：
    - 命中排除词 → 直接丢弃
    - 未配置启用关键词 → 全部保留（不做业务过滤）
    - 标题/摘要/正文命中任一业务关键词（或同义词）→ 保留
    返回 (是否保留, 命中的关键词列表)
    """
    text = f"{title or ''}\n{snippet or ''}\n{(content or '')[:3000]}"
    for ex in exclude_list:
        if ex in text:
            return False, []
    if not match_list:
        return True, []
    matched = [kw for kw in match_list if kw in text]
    return (bool(matched), matched)


def _load_content_matcher(db):
    """构建内容匹配器：业务标签（三级树）优先，无启用标签时回退旧关键词表。"""
    from .business_tags import load_tag_matcher
    tag_map, exclude_list, has_tags = load_tag_matcher(db)
    if has_tags:
        return {'mode': 'tags', 'tag_map': tag_map, 'exclude': exclude_list}
    match_list, exclude_list = _load_active_keywords(db)
    return {'mode': 'keywords', 'match_list': match_list, 'exclude': exclude_list}


def _match_content(title, content, snippet, matcher):
    """按匹配器判断内容是否与业务相关。

    规则（两种模式一致）：
    - 命中排除词 → 直接丢弃
    - tags 模式：文本命中任一标签名/同义词 → 保留，返回命中的标签路径（如 "遥感/SAR"）
    - keywords 模式：未配置启用关键词 → 全部保留；否则命中关键词（或同义词）→ 保留
    返回 (是否保留, 命中列表)
    """
    text = f"{title or ''}\n{snippet or ''}\n{(content or '')[:3000]}".lower()
    for ex in matcher.get('exclude', []):
        if ex.lower() in text:
            return False, []
    if matcher['mode'] == 'tags':
        seen, matched = set(), []
        for word, path in matcher['tag_map'].items():
            if word in text and path not in seen:
                seen.add(path)
                matched.append(path)
        return (bool(matched), matched)
    # keywords 模式
    match_list = matcher['match_list']
    if not match_list:
        return True, []
    matched = [kw for kw in match_list if kw.lower() in text]
    return (bool(matched), matched)


def _save_raw_intelligence(source_id, url, title, content, publish_date='', snippet='', attachment_path='', keywords_matched=''):
    """保存原始情报到统一采集池，URL Hash 去重。

    返回 (id, is_new)：is_new=True 表示新插入，False 表示已存在。
    """
    db = get_db()
    url_hash = hashlib.md5(url.encode()).hexdigest() if url else None
    # 检查是否已存在
    if url_hash:
        existing = db.execute(
            "SELECT id FROM raw_intelligence WHERE url_hash=?", (url_hash,)
        ).fetchone()
        if existing:
            return existing['id'], False
    content_hash = hashlib.md5((content or '').encode()).hexdigest()[:16] if content else None
    cursor = db.execute("""
        INSERT INTO raw_intelligence (source_id, url, url_hash, title, content, publish_date,
                                      content_hash, status, snippet, attachment_path, keywords_matched)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
    """, (source_id, url, url_hash, title, content, publish_date, content_hash,
          snippet, attachment_path, keywords_matched))
    db.commit()
    return cursor.lastrowid, True


# ==================== Phase2: 采集任务执行 ====================

@intelligence_bp.route('/collect/<int:source_id>', methods=['POST'])
@admin_required
def collect_from_source(source_id):
    """手动触发指定数据源的采集。

    流程：
    1. 读取 lead_source 配置（parser_type 决定采集器插件）
    2. 实例化采集器，执行 collect() 获取列表页
    3. 对每个 item 调用 fetch_detail() 抓取详情页正文 + 附件链接
    4. 通过 _save_raw_intelligence 写入统一采集池（URL Hash 去重）
    """
    db = get_db()
    source = db.execute("SELECT * FROM lead_sources WHERE id=?", (source_id,)).fetchone()
    if not source:
        return jsonify({'code': 404, 'message': '数据源不存在'})

    if not source['enabled']:
        return jsonify({'code': 400, 'message': '数据源已禁用'})

    parser_type = source['parser_type']
    if not parser_type:
        return jsonify({'code': 400, 'message': '该数据源未配置采集器(parser_type)，无法采集'})
    config = {}
    if source['config']:
        try:
            config = json.loads(source['config'])
        except (json.JSONDecodeError, TypeError):
            config = {}

    source_dict = {
        'id': source['id'],
        'name': source['name'],
        'url': source['url'] or '',
        'keywords': source['keywords'] or '',
        'category': source['category'] or '',
        'parser_type': parser_type,
    }

    try:
        from collectors import get_collector
        collector_cls = get_collector(parser_type)
        if not collector_cls:
            return jsonify({'code': 400, 'message': f'采集器插件不存在: {parser_type}'})

        collector = collector_cls(source_dict, config)
        items = collector.collect()
    except Exception as e:
        logger.error(f'采集失败 source={source_id}: {e}')
        return jsonify({'code': 500, 'message': f'采集失败: {e}'})

    # 抓取详情页 + 保存
    fetch_detail = request.args.get('fetch_detail', '1') != '0'
    matcher = _load_content_matcher(db)
    new_count = 0
    dup_count = 0
    filtered_count = 0
    errors = []
    saved_items = []

    for item in items:
        try:
            if fetch_detail and item.url:
                item = collector.fetch_detail(item)

            # 清洗标题
            from utils.cleaner import clean_title, is_junk_content
            title = clean_title(item.title) if item.title else ''

            # 业务标签/关键词联动：排除词过滤 + 标签（同义词）匹配（与业务无关的内容不入库）
            keep, matched = _match_content(title, item.content, item.snippet, matcher)
            if not keep:
                filtered_count += 1
                continue

            # 过滤垃圾内容
            if is_junk_content(item.content, title):
                dup_count += 1
                continue

            rid, is_new = _save_raw_intelligence(
                source_id=source_id,
                url=item.url,
                title=title,
                content=item.content or '',
                publish_date=item.publish_date or '',
                snippet=item.snippet or '',
                attachment_path=','.join(item.attachment_urls) if item.attachment_urls else '',
                keywords_matched=','.join(matched)
            )
            if is_new:
                new_count += 1
                saved_items.append({'id': rid, 'title': title, 'url': item.url})
            else:
                dup_count += 1
        except Exception as e:
            errors.append(str(e))

    # 更新 last_scraped_at
    db.execute("UPDATE lead_sources SET last_scraped_at=CURRENT_TIMESTAMP WHERE id=?", (source_id,))
    db.commit()

    record_operation_log(
        request.current_user, 'collect', 'raw_intelligence',
        f'采集数据源:{source["name"]} 新增{new_count}条 重复{dup_count}条 关键词过滤{filtered_count}条'
    )

    return jsonify({
        'code': 200,
        'data': {
            'collected': len(items),
            'new': new_count,
            'duplicate': dup_count,
            'filtered': filtered_count,
            'errors': errors[:5],
            'items': saved_items[:20],
        }
    })


@intelligence_bp.route('/collect-all', methods=['POST'])
@admin_required
def collect_all_sources():
    """批量触发所有启用的数据源采集。"""
    db = get_db()
    sources = db.execute(
        "SELECT id, name, parser_type, category FROM lead_sources WHERE enabled=1"
    ).fetchall()

    results = []
    for src in sources:
        try:
            # 复用单源采集逻辑
            from collectors import get_collector
            parser_type = src['parser_type']
            if not parser_type:
                results.append({'source': src['name'], 'error': '未配置采集器(parser_type)'})
                continue
            collector_cls = get_collector(parser_type)
            if not collector_cls:
                results.append({'source': src['name'], 'error': f'插件不存在:{parser_type}'})
                continue

            source_row = db.execute("SELECT * FROM lead_sources WHERE id=?", (src['id'],)).fetchone()
            config = {}
            if source_row['config']:
                try:
                    config = json.loads(source_row['config'])
                except (json.JSONDecodeError, TypeError):
                    pass

            source_dict = {
                'id': source_row['id'], 'name': source_row['name'],
                'url': source_row['url'] or '', 'keywords': source_row['keywords'] or '',
                'category': source_row['category'] or '', 'parser_type': parser_type,
            }
            collector = collector_cls(source_dict, config)
            items = collector.collect()

            matcher = _load_content_matcher(db)
            new_count = 0
            filtered_count = 0
            for item in items:
                item = collector.fetch_detail(item) if item.url else item
                from utils.cleaner import clean_title, is_junk_content
                title = clean_title(item.title) if item.title else ''
                # 业务标签/关键词联动：排除词过滤 + 标签（同义词）匹配
                keep, matched = _match_content(title, item.content, item.snippet, matcher)
                if not keep:
                    filtered_count += 1
                    continue
                if is_junk_content(item.content, title):
                    continue
                _, is_new = _save_raw_intelligence(
                    source_id=src['id'], url=item.url, title=title,
                    content=item.content or '', publish_date=item.publish_date or '',
                    snippet=item.snippet or '', keywords_matched=','.join(matched)
                )
                if is_new:
                    new_count += 1

            db.execute("UPDATE lead_sources SET last_scraped_at=CURRENT_TIMESTAMP WHERE id=?",
                       (src['id'],))
            db.commit()
            results.append({'source': src['name'], 'collected': len(items), 'new': new_count,
                            'filtered': filtered_count})
        except Exception as e:
            results.append({'source': src['name'], 'error': str(e)})

    record_operation_log(
        request.current_user, 'collect_all', 'raw_intelligence',
        f'批量采集{len(sources)}个数据源'
    )
    return jsonify({'code': 200, 'data': results})


@intelligence_bp.route('/parse-attachment/<int:rid>', methods=['POST'])
@admin_required
def parse_attachment(rid):
    """解析情报附件，提取文本内容并回填。"""
    db = get_db()
    row = db.execute("SELECT * FROM raw_intelligence WHERE id=?", (rid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '情报不存在'})

    attachment_path = row['attachment_path'] or ''
    if not attachment_path:
        return jsonify({'code': 400, 'message': '无附件'})

    urls = [u.strip() for u in attachment_path.split(',') if u.strip()]
    from utils.attachment_parser import download_and_parse

    all_text = []
    parsed_files = []
    for url in urls:
        result = download_and_parse(url, source_name=row['title'] or '')
        if result and result.get('text'):
            all_text.append(result['text'])
            parsed_files.append(result.get('filename', url))

    combined_text = '\n\n'.join(all_text)
    if combined_text:
        # 回填到 content（追加到已有内容后）
        existing = row['content'] or ''
        new_content = existing + '\n\n--- 附件内容 ---\n' + combined_text if existing else combined_text
        db.execute("UPDATE raw_intelligence SET content=? WHERE id=?", (new_content, rid))
        db.commit()
        record_operation_log(
            request.current_user, 'parse_attachment', 'raw_intelligence',
            f'解析附件:{row["title"]} 文件数:{len(parsed_files)}'
        )

    return jsonify({
        'code': 200,
        'data': {
            'parsed_count': len(parsed_files),
            'files': parsed_files,
            'text_length': len(combined_text),
        }
    })


# ==================== Phase3: AI 商机识别 ====================

@intelligence_bp.route('/analyze/<int:rid>', methods=['POST'])
@admin_required
def analyze_intel(rid):
    """AI 分析单条原始情报 → 识别商机/客户/竞争对手/评分。"""
    from ai_opportunity import analyze_intelligence

    db = get_db()
    row = db.execute("SELECT id, title, status FROM raw_intelligence WHERE id=?", (rid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '情报不存在'})

    lead_id, err = analyze_intelligence(rid, db)
    if err:
        return jsonify({'code': 500, 'message': f'分析失败: {err}'})
    if lead_id is None:
        return jsonify({'code': 200, 'message': '已分析过，跳过'})

    lead = db.execute("SELECT * FROM intelligence_leads WHERE id=?", (lead_id,)).fetchone()
    record_operation_log(
        request.current_user, 'analyze', 'raw_intelligence',
        f'AI分析情报:{row["title"]} 评分:{lead["score"] if lead else "?"}'
    )
    return jsonify({'code': 200, 'data': dict(lead) if lead else {}})


@intelligence_bp.route('/analyze-batch', methods=['POST'])
@admin_required
def analyze_batch():
    """批量 AI 分析 pending 状态的原始情报。

    参数：
    - source_id: 限定数据源（可选）
    - limit: 最多分析条数（默认 20）
    """
    from ai_opportunity import batch_analyze

    source_id = request.args.get('source_id', type=int)
    limit = request.args.get('limit', 20, type=int)
    if limit > 100:
        limit = 100

    result = batch_analyze(source_id=source_id, limit=limit)
    record_operation_log(
        request.current_user, 'analyze_batch', 'raw_intelligence',
        f'批量分析{result["analyzed"]}条 成功{result["success"]} 失败{result["failed"]}'
    )
    return jsonify({'code': 200, 'data': result})


# ============================================================
# 多 Agent 协同分析（7 个专职 Agent 顺序协同）
# ============================================================
@intelligence_bp.route('/agent-analyze/<int:rid>', methods=['POST'])
@admin_required
def agent_analyze(rid):
    """7-Agent 协同分析单条情报。

    Agent1 信息分类 / Agent2 业务分类 / Agent3 实体识别 /
    Agent4 项目分析 / Agent5 能力匹配 / Agent6 商机评分 / Agent7 销售建议

    参数 ?force=true 强制重新分析（覆盖旧结果）；默认已分析过则直接返回已有结果。
    """
    from ai_agents import analyze_with_agents, get_agent_result

    db = get_db()
    row = db.execute("SELECT id, title, status FROM raw_intelligence WHERE id=?", (rid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '情报不存在'})

    force = request.args.get('force', '').lower() == 'true'
    result, err = analyze_with_agents(rid, db, force=force)
    if err:
        return jsonify({'code': 500, 'message': f'分析失败: {err}'})

    if result is None:
        # 已分析过（非强制）：直接返回已保存结果，前端可直接展示
        saved = get_agent_result(rid, db)
        return jsonify({'code': 200, 'data': saved, 'message': '已分析过，返回已有结果'})

    record_operation_log(
        request.current_user, 'agent_analyze', 'raw_intelligence',
        f'7-Agent分析:{row["title"]} 评分:{result.get("final_score", 0)}'
    )
    return jsonify({'code': 200, 'data': result})


@intelligence_bp.route('/agent-analyze-batch', methods=['POST'])
@admin_required
def agent_analyze_batch():
    """批量 7-Agent 协同分析 pending 状态情报。

    参数：
    - source_id: 限定数据源（可选）
    - limit: 最多分析条数（默认 10，上限 50，因单条需 7 次 LLM 调用）
    """
    from ai_agents import batch_analyze_with_agents

    source_id = request.args.get('source_id', type=int)
    limit = request.args.get('limit', 10, type=int)
    if limit > 50:
        limit = 50

    result = batch_analyze_with_agents(source_id=source_id, limit=limit)
    record_operation_log(
        request.current_user, 'agent_analyze_batch', 'raw_intelligence',
        f'7-Agent批量分析{result["analyzed"]}条 成功{result["success"]} 失败{result["failed"]}'
    )
    return jsonify({'code': 200, 'data': result})


@intelligence_bp.route('/agent-result/<int:rid>', methods=['GET'])
@token_required
def agent_result(rid):
    """获取已保存的 7-Agent 分析结果。"""
    from ai_agents import get_agent_result

    db = get_db()
    result = get_agent_result(rid, db)
    if not result:
        return jsonify({'code': 404, 'message': '尚未分析'})
    return jsonify({'code': 200, 'data': result})


@intelligence_bp.route('/leads', methods=['GET'])
@token_required
def list_leads():
    """商机列表（AI 分析结果），支持分页/筛选/排序。"""
    db = get_db()
    search = request.args.get('search', '').strip()
    min_score = request.args.get('min_score', 0, type=int)
    is_relevant = request.args.get('is_relevant', type=int)
    sort = request.args.get('sort', 'score')  # score / created_at
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page

    sql = """
        SELECT il.*, ri.url, ri.publish_date,
               ls.name as source_name
        FROM intelligence_leads il
        LEFT JOIN raw_intelligence ri ON il.raw_intelligence_id = ri.id
        LEFT JOIN lead_sources ls ON il.source_id = ls.id
        WHERE 1=1
    """
    params = []
    if search:
        sql += " AND (il.title LIKE ? OR il.buyer LIKE ? OR il.analysis_summary LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
    if min_score:
        sql += " AND il.score >= ?"
        params.append(min_score)
    if is_relevant is not None:
        sql += " AND il.is_relevant = ?"
        params.append(is_relevant)
    # 等级筛选：S/A/B/C
    grade = request.args.get('grade', '').strip().upper()
    if grade in ('S', 'A', 'B', 'C'):
        sql += " AND il.score_grade = ?"
        params.append(grade)
    # 生命周期阶段筛选
    lifecycle_stage = request.args.get('lifecycle_stage', '').strip()
    if lifecycle_stage:
        sql += " AND il.lifecycle_stage = ?"
        params.append(lifecycle_stage)
    # 去重状态筛选：clean/suspect/merged
    dedup_status = request.args.get('dedup_status', '').strip()
    if dedup_status:
        sql += " AND il.dedup_status = ?"
        params.append(dedup_status)

    total = db.execute(f"SELECT COUNT(*) as cnt FROM ({sql})", params).fetchone()['cnt']

    if sort == 'created_at':
        sql += " ORDER BY il.created_at DESC"
    else:
        sql += " ORDER BY il.score DESC, il.created_at DESC"
    sql += " LIMIT ? OFFSET ?"
    params.extend([per_page, offset])

    rows = db.execute(sql, params).fetchall()
    return jsonify({
        'code': 200,
        'data': [dict(r) for r in rows],
        'total': total,
        'page': page,
        'per_page': per_page
    })


@intelligence_bp.route('/leads/<int:lid>', methods=['GET'])
@token_required
def get_lead(lid):
    """商机详情。"""
    db = get_db()
    row = db.execute("""
        SELECT il.*, ri.url, ri.publish_date, ri.content as raw_content,
               ri.snippet, ri.attachment_path,
               ls.name as source_name
        FROM intelligence_leads il
        LEFT JOIN raw_intelligence ri ON il.raw_intelligence_id = ri.id
        LEFT JOIN lead_sources ls ON il.source_id = ls.id
        WHERE il.id = ?
    """, (lid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '商机不存在'})
    return jsonify({'code': 200, 'data': dict(row)})


@intelligence_bp.route('/leads/<int:lid>/score', methods=['POST'])
@admin_required
def rescore_lead(lid):
    """商机评分模型重评分：7 维度加权 + 规则/LLM 混合。"""
    from scoring_model import score_lead

    db = get_db()
    row = db.execute("SELECT * FROM intelligence_leads WHERE id=?", (lid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '商机不存在'})

    result = score_lead(row, db=db)
    db.execute("""
        UPDATE intelligence_leads
        SET score=?, score_reason=?, score_dimensions=?, score_grade=?, score_method=?
        WHERE id=?
    """, (
        result['score'],
        result['reason'],
        json.dumps(result['dimensions'], ensure_ascii=False),
        result['grade'],
        result['method'],
        lid
    ))
    db.commit()
    record_operation_log(
        request.current_user, 'score', 'intelligence_leads',
        f'商机#{lid} 评分{result["score"]}({result["grade"]}级,{result["method"]})'
    )
    lead = db.execute("SELECT * FROM intelligence_leads WHERE id=?", (lid,)).fetchone()
    return jsonify({'code': 200, 'data': dict(lead), 'scoring': result})


# ==================== 商机生命周期 ====================

@intelligence_bp.route('/lifecycle/config', methods=['GET'])
@token_required
def lifecycle_config():
    """生命周期配置：情报 8 阶段 + CRM 5 阶段映射。"""
    from lifecycle_model import INTEL_STAGES, CRM_STAGES
    return jsonify({
        'code': 200,
        'data': {
            'intel_stages': INTEL_STAGES,
            'crm_stages': CRM_STAGES,
        }
    })


@intelligence_bp.route('/leads/<int:lid>/lifecycle', methods=['GET'])
@token_required
def get_lifecycle(lid):
    """获取商机生命周期进度与流转日志。"""
    from lifecycle_model import get_lifecycle_progress, STAGE_BY_KEY
    db = get_db()
    row = db.execute(
        "SELECT id, lifecycle_stage FROM intelligence_leads WHERE id=?", (lid,)
    ).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '商机不存在'})
    stage = row['lifecycle_stage'] or 'intelligence'
    progress = get_lifecycle_progress(stage)
    logs = db.execute("""
        SELECT id, from_stage, to_stage, reason, operator, crm_stage, created_at
        FROM lifecycle_logs
        WHERE lead_id=?
        ORDER BY created_at DESC
        LIMIT 50
    """, (lid,)).fetchall()
    return jsonify({
        'code': 200,
        'data': {
            'lead_id': lid,
            'current_stage': stage,
            'current_label': STAGE_BY_KEY.get(stage, {}).get('label', '情报'),
            'progress': progress,
            'logs': [dict(r) for r in logs],
        }
    })


@intelligence_bp.route('/leads/<int:lid>/lifecycle', methods=['POST'])
@token_required
def update_lifecycle(lid):
    """流转商机生命周期阶段。

    Body: {"to_stage": "bidding", "reason": "已开标"}
    规则：终态阶段不可流转；记录日志；同步映射到 CRM 阶段。
    """
    from lifecycle_model import (
        can_transition, get_stage_info, map_to_crm_stage,
        build_lifecycle_reason, STAGE_BY_KEY
    )
    data = request.get_json(silent=True) or {}
    to_stage = (data.get('to_stage') or '').strip()
    reason = (data.get('reason') or '').strip()

    if to_stage not in STAGE_BY_KEY:
        return jsonify({'code': 400, 'message': f'无效的生命周期阶段: {to_stage}'})

    db = get_db()
    row = db.execute(
        "SELECT id, lifecycle_stage, status FROM intelligence_leads WHERE id=?", (lid,)
    ).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '商机不存在'})

    from_stage = row['lifecycle_stage'] or 'intelligence'
    # 作废商机不允许流转
    if row['status'] == 'rejected':
        return jsonify({'code': 400, 'message': '已作废商机不可流转生命周期'})

    ok, msg = can_transition(from_stage, to_stage)
    if not ok:
        return jsonify({'code': 400, 'message': msg})

    crm_stage = map_to_crm_stage(to_stage)
    transition_reason = build_lifecycle_reason(from_stage, to_stage, reason)

    # 更新阶段 + 写日志
    db.execute(
        "UPDATE intelligence_leads SET lifecycle_stage=? WHERE id=?",
        (to_stage, lid)
    )
    db.execute("""
        INSERT INTO lifecycle_logs (lead_id, from_stage, to_stage, reason, operator, crm_stage)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        lid, from_stage, to_stage, transition_reason,
        request.current_user.get('username', ''), crm_stage
    ))
    db.commit()

    record_operation_log(
        request.current_user, 'lifecycle', 'intelligence_leads',
        f'商机#{lid} 生命周期流转: {transition_reason}'
    )

    from lifecycle_model import get_lifecycle_progress
    progress = get_lifecycle_progress(to_stage)
    return jsonify({
        'code': 200,
        'message': f'已流转至[{get_stage_info(to_stage)["label"]}]阶段',
        'data': {
            'lead_id': lid,
            'from_stage': from_stage,
            'to_stage': to_stage,
            'crm_stage': crm_stage,
            'reason': transition_reason,
            'progress': progress,
        }
    })


# ==================== 商机多级去重 ====================

@intelligence_bp.route('/leads/<int:lid>/dedup', methods=['POST'])
@token_required
def detect_duplicates_for_lead(lid):
    """对指定商机执行 4 级去重检测。

    Level 1: URL Hash
    Level 2: 标题相似度 ≥ 0.85
    Level 3: 客户+项目+地区 ≥ 0.80
    Level 4: Embedding 相似度 > 0.90

    检测结果写入 duplicate_candidates 表（status=pending），不自动删除。
    """
    from dedup_model import detect_duplicates, DEDUP_LEVELS
    db = get_db()
    lead = db.execute("SELECT * FROM intelligence_leads WHERE id=?", (lid,)).fetchone()
    if not lead:
        return jsonify({'code': 404, 'message': '商机不存在'})

    # 取其他活跃商机作为对比集（排除已作废/已合并）
    others = db.execute("""
        SELECT il.*, ri.url
        FROM intelligence_leads il
        LEFT JOIN raw_intelligence ri ON il.raw_intelligence_id = ri.id
        WHERE il.id != ? AND il.status NOT IN ('rejected', 'merged')
    """, (lid,)).fetchall()

    candidates = detect_duplicates(lead, others, use_embedding=True)

    # 写入候选表（去重：同对已存在 pending 候选则跳过）
    new_count = 0
    for c in candidates:
        existing = db.execute("""
            SELECT id FROM duplicate_candidates
            WHERE lead_a_id=? AND lead_b_id=? AND status='pending'
        """, (lid, c['lead_id'])).fetchone()
        if existing:
            continue
        db.execute("""
            INSERT INTO duplicate_candidates
                (lead_a_id, lead_b_id, match_level, match_level_name, similarity, match_reason, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """, (
            lid, c['lead_id'], c['match_level'], c['match_level_name'],
            c['similarity'], c['match_reason']
        ))
        new_count += 1

    # 更新商机去重状态
    if candidates:
        db.execute("UPDATE intelligence_leads SET dedup_status='suspect' WHERE id=?", (lid,))
        for c in candidates:
            db.execute("UPDATE intelligence_leads SET dedup_status='suspect' WHERE id=?", (c['lead_id'],))

    db.commit()
    record_operation_log(
        request.current_user, 'dedup', 'intelligence_leads',
        f'商机#{lid} 去重检测：发现{len(candidates)}个疑似重复，新增{new_count}条候选'
    )
    return jsonify({
        'code': 200,
        'message': f'检测完成：发现{len(candidates)}个疑似重复',
        'data': {'candidates': candidates, 'new_count': new_count}
    })


@intelligence_bp.route('/duplicates', methods=['GET'])
@token_required
def list_duplicates():
    """疑似重复候选列表。"""
    db = get_db()
    status = request.args.get('status', 'pending')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page

    sql = """
        SELECT dc.*,
               a.title as a_title, a.buyer as a_buyer, a.score as a_score,
               a.lifecycle_stage as a_stage, a.status as a_status,
               b.title as b_title, b.buyer as b_buyer, b.score as b_score,
               b.lifecycle_stage as b_stage, b.status as b_status
        FROM duplicate_candidates dc
        LEFT JOIN intelligence_leads a ON dc.lead_a_id = a.id
        LEFT JOIN intelligence_leads b ON dc.lead_b_id = b.id
        WHERE dc.status = ?
        ORDER BY dc.match_level ASC, dc.similarity DESC, dc.created_at DESC
        LIMIT ? OFFSET ?
    """
    rows = db.execute(sql, (status, per_page, offset)).fetchall()

    count_sql = "SELECT COUNT(*) as cnt FROM duplicate_candidates WHERE status = ?"
    total = db.execute(count_sql, (status,)).fetchone()['cnt']

    return jsonify({
        'code': 200,
        'data': [dict(r) for r in rows],
        'total': total,
        'page': page,
        'per_page': per_page,
    })


@intelligence_bp.route('/duplicates/<int:cid>/ai-judge', methods=['POST'])
@token_required
def ai_judge_duplicate_pair(cid):
    """AI 判断两条商机是否为同一项目。"""
    from dedup_model import ai_judge_duplicate
    db = get_db()
    cand = db.execute("SELECT * FROM duplicate_candidates WHERE id=?", (cid,)).fetchone()
    if not cand:
        return jsonify({'code': 404, 'message': '候选记录不存在'})

    lead_a = db.execute("SELECT * FROM intelligence_leads WHERE id=?", (cand['lead_a_id'],)).fetchone()
    lead_b = db.execute("SELECT * FROM intelligence_leads WHERE id=?", (cand['lead_b_id'],)).fetchone()
    if not lead_a or not lead_b:
        return jsonify({'code': 404, 'message': '商机不存在'})

    result = ai_judge_duplicate(lead_a, lead_b)
    if result is None:
        return jsonify({'code': 503, 'message': 'AI 判断不可用（LLM未启用或调用失败）'})

    db.execute("""
        UPDATE duplicate_candidates
        SET ai_is_same=?, ai_confidence=?, ai_reason=?,
            status=?, resolved_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (
        1 if result['is_same'] else 0,
        result['confidence'],
        result['reason'],
        'ai_same' if result['is_same'] else 'ai_diff',
        cid
    ))
    db.commit()
    record_operation_log(
        request.current_user, 'ai_judge', 'duplicate_candidates',
        f'候选#{cid} AI判断: {"同一项目" if result["is_same"] else "不同项目"} (置信度{result["confidence"]:.0%})'
    )
    return jsonify({
        'code': 200,
        'data': {
            'is_same': result['is_same'],
            'confidence': result['confidence'],
            'reason': result['reason'],
            'status': 'ai_same' if result['is_same'] else 'ai_diff',
        }
    })


@intelligence_bp.route('/duplicates/<int:cid>/merge', methods=['POST'])
@token_required
def merge_duplicate_pair(cid):
    """合并两条商机：保留 lead_a，将 lead_b 标记为已合并。

    Body: {"keep": "a"|"b"} 指定保留哪条，默认保留 a。
    """
    from dedup_model import build_merge_summary
    data = request.get_json(silent=True) or {}
    keep = (data.get('keep') or 'a').strip().lower()

    db = get_db()
    cand = db.execute("SELECT * FROM duplicate_candidates WHERE id=?", (cid,)).fetchone()
    if not cand:
        return jsonify({'code': 404, 'message': '候选记录不存在'})

    # 确定保留/合并方
    if keep == 'b':
        keep_id, merge_id = cand['lead_b_id'], cand['lead_a_id']
    else:
        keep_id, merge_id = cand['lead_a_id'], cand['lead_b_id']

    keep_lead = db.execute("SELECT * FROM intelligence_leads WHERE id=?", (keep_id,)).fetchone()
    merge_lead = db.execute("SELECT * FROM intelligence_leads WHERE id=?", (merge_id,)).fetchone()
    if not keep_lead or not merge_lead:
        return jsonify({'code': 404, 'message': '商机不存在'})
    if merge_lead['status'] == 'merged':
        return jsonify({'code': 400, 'message': '该商机已被合并'})

    merge_note = build_merge_summary(keep_lead, merge_lead)

    # 被合并方标记为 merged，状态更新
    db.execute("""
        UPDATE intelligence_leads
        SET status='merged', dedup_status='merged',
            reject_reason=COALESCE(reject_reason, '') || ' [' || ? || ']'
        WHERE id=?
    """, (merge_note, merge_id))

    # 候选记录标记为已合并
    db.execute("""
        UPDATE duplicate_candidates
        SET status='merged', operator=?, resolved_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (request.current_user.get('username', ''), cid))

    # 同时关闭涉及该合并方的其他 pending 候选
    db.execute("""
        UPDATE duplicate_candidates
        SET status='merged', operator=?, resolved_at=CURRENT_TIMESTAMP
        WHERE (lead_a_id=? OR lead_b_id=?) AND status='pending' AND id!=?
    """, (request.current_user.get('username', ''), merge_id, merge_id, cid))

    db.commit()
    record_operation_log(
        request.current_user, 'merge', 'intelligence_leads',
        f'合并商机：保留#{keep_id}，合并#{merge_id}（{merge_note[:60]}）'
    )
    return jsonify({
        'code': 200,
        'message': f'已合并：保留#{keep_id}，合并#{merge_id}',
        'data': {'keep_id': keep_id, 'merge_id': merge_id}
    })


@intelligence_bp.route('/duplicates/<int:cid>/keep', methods=['POST'])
@token_required
def keep_duplicate_pair(cid):
    """人工确认两条商机保留独立（不合并）。"""
    db = get_db()
    cand = db.execute("SELECT * FROM duplicate_candidates WHERE id=?", (cid,)).fetchone()
    if not cand:
        return jsonify({'code': 404, 'message': '候选记录不存在'})

    db.execute("""
        UPDATE duplicate_candidates
        SET status='kept', operator=?, resolved_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (request.current_user.get('username', ''), cid))

    # 恢复两条商机的去重状态为 clean（如果无其他 pending 候选）
    for lead_id in (cand['lead_a_id'], cand['lead_b_id']):
        other_pending = db.execute("""
            SELECT COUNT(*) as cnt FROM duplicate_candidates
            WHERE (lead_a_id=? OR lead_b_id=?) AND status='pending'
        """, (lead_id, lead_id)).fetchone()['cnt']
        if other_pending == 0:
            db.execute("UPDATE intelligence_leads SET dedup_status='clean' WHERE id=?", (lead_id,))

    db.commit()
    record_operation_log(
        request.current_user, 'keep', 'duplicate_candidates',
        f'候选#{cid} 确认保留独立'
    )
    return jsonify({'code': 200, 'message': '已确认保留独立'})


# ==================== 项目关联：多公告 → 一 Project ====================

@intelligence_bp.route('/projects', methods=['GET'])
@token_required
def list_projects():
    """项目列表：多个公告关联的统一项目视图。"""
    db = get_db()
    search = request.args.get('search', '').strip()
    lifecycle_stage = request.args.get('lifecycle_stage', '').strip()
    status = request.args.get('status', 'active')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page

    sql = "SELECT * FROM projects WHERE 1=1"
    params = []
    if status:
        sql += " AND status=?"
        params.append(status)
    if search:
        sql += " AND (name LIKE ? OR buyer LIKE ? OR region LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
    if lifecycle_stage:
        sql += " AND lifecycle_stage=?"
        params.append(lifecycle_stage)

    total = db.execute(f"SELECT COUNT(*) as cnt FROM ({sql})", params).fetchone()['cnt']
    sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    rows = db.execute(sql, params).fetchall()

    return jsonify({
        'code': 200,
        'data': [dict(r) for r in rows],
        'total': total,
        'page': page,
        'per_page': per_page,
    })


@intelligence_bp.route('/projects/<int:pid>', methods=['GET'])
@token_required
def get_project_detail(pid):
    """项目详情：项目信息 + 关联公告列表 + 生命周期进度。"""
    from project_model import get_project_summary
    db = get_db()
    summary = get_project_summary(pid, db)
    if not summary:
        return jsonify({'code': 404, 'message': '项目不存在'})
    return jsonify({'code': 200, 'data': summary})


@intelligence_bp.route('/projects/<int:pid>/link', methods=['POST'])
@token_required
def link_lead_to_project(pid):
    """手动将公告关联到项目。

    Body: {"lead_id": 123}
    """
    from project_model import link_to_project
    data = request.get_json(silent=True) or {}
    lead_id = data.get('lead_id')
    if not lead_id:
        return jsonify({'code': 400, 'message': '缺少 lead_id'})

    db = get_db()
    project = db.execute("SELECT id, name FROM projects WHERE id=?", (pid,)).fetchone()
    if not project:
        return jsonify({'code': 404, 'message': '项目不存在'})
    lead = db.execute(
        "SELECT id, title FROM intelligence_leads WHERE id=?", (lead_id,)
    ).fetchone()
    if not lead:
        return jsonify({'code': 404, 'message': '公告不存在'})

    link_to_project(lead_id, pid, db)
    db.commit()
    record_operation_log(
        request.current_user, 'link', 'projects',
        f'公告#{lead_id} 关联到项目#{pid}({project["name"][:30]})'
    )
    return jsonify({'code': 200, 'message': f'已关联到项目：{project["name"][:30]}'})


@intelligence_bp.route('/projects/<int:pid>/merge', methods=['POST'])
@token_required
def merge_projects(pid):
    """合并两个项目：保留当前项目，将另一项目的公告全部转移过来。

    Body: {"merge_project_id": 456}
    """
    data = request.get_json(silent=True) or {}
    merge_pid = data.get('merge_project_id')
    if not merge_pid:
        return jsonify({'code': 400, 'message': '缺少 merge_project_id'})

    db = get_db()
    keep = db.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    merge = db.execute("SELECT * FROM projects WHERE id=?", (merge_pid,)).fetchone()
    if not keep or not merge:
        return jsonify({'code': 404, 'message': '项目不存在'})

    # 转移公告
    db.execute(
        "UPDATE intelligence_leads SET project_id=? WHERE project_id=?",
        (pid, merge_pid)
    )
    # 标记被合并项目为 closed
    db.execute(
        "UPDATE projects SET status='closed' WHERE id=?", (merge_pid,)
    )
    # 重新聚合保留项目信息
    from project_model import link_to_project
    leads = db.execute(
        "SELECT id FROM intelligence_leads WHERE project_id=? LIMIT 1", (pid,)
    ).fetchone()
    if leads:
        link_to_project(leads['id'], pid, db)
    db.commit()
    record_operation_log(
        request.current_user, 'merge', 'projects',
        f'合并项目：保留#{pid}({keep["name"][:20]})，合并#{merge_pid}({merge["name"][:20]})'
    )
    return jsonify({
        'code': 200,
        'message': f'已合并：保留#{pid}，合并#{merge_pid}',
        'data': {'keep_id': pid, 'merge_id': merge_pid}
    })


@intelligence_bp.route('/leads/<int:lid>/project', methods=['GET'])
@token_required
def get_lead_project(lid):
    """获取公告所属项目信息。"""
    db = get_db()
    lead = db.execute(
        "SELECT id, project_id FROM intelligence_leads WHERE id=?", (lid,)
    ).fetchone()
    if not lead:
        return jsonify({'code': 404, 'message': '公告不存在'})
    if not lead['project_id']:
        return jsonify({'code': 200, 'data': None})
    from project_model import get_project_summary
    summary = get_project_summary(lead['project_id'], db)
    return jsonify({'code': 200, 'data': summary})


@intelligence_bp.route('/projects/auto-associate', methods=['POST'])
@token_required
def auto_associate_all():
    """批量自动关联所有未关联项目的公告。"""
    from project_model import auto_associate_project
    db = get_db()
    # 取所有未关联项目且已分析的公告
    leads = db.execute("""
        SELECT il.*, ri.url
        FROM intelligence_leads il
        LEFT JOIN raw_intelligence ri ON il.raw_intelligence_id = ri.id
        WHERE il.project_id IS NULL AND il.status NOT IN ('rejected', 'merged')
    """).fetchall()

    linked = 0
    created = 0
    for lead in leads:
        result = auto_associate_project(lead['id'], lead, db)
        if result['action'] == 'linked':
            linked += 1
        elif result['action'] == 'created':
            created += 1
    db.commit()

    record_operation_log(
        request.current_user, 'auto_associate', 'projects',
        f'批量关联：关联{linked}条，新建{created}个项目'
    )
    return jsonify({
        'code': 200,
        'message': f'关联{linked}条公告到已有项目，新建{created}个项目',
        'data': {'linked': linked, 'created': created, 'total': len(leads)}
    })


# ==================== Phase4: 商机转入CRM ====================

def _build_lead_from_intel(lead_row, raw_row):
    """将 intelligence_leads 记录映射为 scraped_leads 字段。"""
    remark_parts = []
    if lead_row['budget']:
        remark_parts.append(f'预算:{lead_row["budget"]}')
    if lead_row['deadline']:
        remark_parts.append(f'截止:{lead_row["deadline"]}')
    if lead_row['procurement_method']:
        remark_parts.append(f'采购方式:{lead_row["procurement_method"]}')
    if lead_row['analysis_summary']:
        remark_parts.append(f'AI分析:{lead_row["analysis_summary"]}')

    # 竞争对手信息
    competitors = lead_row['competitors'] or ''
    if competitors:
        try:
            comp_list = json.loads(competitors)
            if comp_list:
                remark_parts.append(f'竞争对手:{"、".join(comp_list)}')
        except (json.JSONDecodeError, TypeError):
            pass

    raw_data = json.dumps({
        'intelligence_lead_id': lead_row['id'],
        'score': lead_row['score'],
        'score_reason': lead_row['score_reason'],
        'keywords_matched': lead_row['keywords_matched'],
        'url': raw_row['url'] if raw_row else '',
        'publish_date': raw_row['publish_date'] if raw_row else '',
        'attachment_path': raw_row['attachment_path'] if raw_row else '',
    }, ensure_ascii=False)

    return {
        'company': lead_row['buyer'] or '',
        'opportunity_name': lead_row['title'] or '',
        'contact_name': lead_row['contact_person'] or '',
        'phone': lead_row['contact_phone'] or '',
        'email': '',
        'industry': lead_row['project_type'] or '',
        'region': lead_row['region'] or '',
        'source': 'AI商机识别',
        'link': raw_row['url'] if raw_row else '',
        'remark': ' | '.join(remark_parts),
        'raw_data': raw_data,
    }


@intelligence_bp.route('/leads/<int:lid>/convert', methods=['POST'])
@app_center_or_admin_required
def convert_lead(lid):
    """将 AI 识别的商机转入 CRM 线索库（scraped_leads）。

    字段映射：
    - buyer → company
    - title → opportunity_name
    - contact_person → contact_name
    - contact_phone → phone
    - url → link
    - score → intent_score + eval_reason
    - budget/deadline/procurement_method → remark
    """
    db = get_db()
    lead_row = db.execute("SELECT * FROM intelligence_leads WHERE id=?", (lid,)).fetchone()
    if not lead_row:
        return jsonify({'code': 404, 'message': '商机不存在'})

    if lead_row['status'] == 'converted':
        return jsonify({'code': 200, 'message': '已转入CRM',
                        'data': {'lead_id': lead_row['converted_lead_id']}})

    raw_row = None
    if lead_row['raw_intelligence_id']:
        raw_row = db.execute(
            "SELECT url, publish_date, content, snippet, attachment_path FROM raw_intelligence WHERE id=?",
            (lead_row['raw_intelligence_id'],)
        ).fetchone()

    # 去重检查：按 link 或 opportunity_name+company
    link = raw_row['url'] if raw_row else ''
    company = lead_row['buyer'] or ''
    opp_name = lead_row['title'] or ''

    if link:
        existing = db.execute("SELECT id FROM scraped_leads WHERE link=?", (link,)).fetchone()
        if existing:
            # 已存在，直接关联
            db.execute("UPDATE intelligence_leads SET status='converted', converted_lead_id=? WHERE id=?",
                       (existing['id'], lid))
            db.commit()
            return jsonify({'code': 200, 'message': '该商机已在CRM中存在，已自动关联',
                            'data': {'lead_id': existing['id'], 'duplicate': True}})

    if opp_name and company:
        existing = db.execute(
            "SELECT id FROM scraped_leads WHERE opportunity_name=? AND company=?",
            (opp_name, company)
        ).fetchone()
        if existing:
            db.execute("UPDATE intelligence_leads SET status='converted', converted_lead_id=? WHERE id=?",
                       (existing['id'], lid))
            db.commit()
            return jsonify({'code': 200, 'message': '该商机已在CRM中存在，已自动关联',
                            'data': {'lead_id': existing['id'], 'duplicate': True}})

    # 构造线索数据并插入
    lead_data = _build_lead_from_intel(lead_row, raw_row)
    if not lead_data['company']:
        return jsonify({'code': 400, 'message': '采购单位为空，无法转入CRM'})

    cursor = db.execute("""
        INSERT INTO scraped_leads (
            source_id, company, opportunity_name, contact_name, phone, email,
            industry, region, source, link, remark, raw_data,
            intent_score, eval_reason, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'evaluated')
    """, (
        lead_row['source_id'],
        lead_data['company'],
        lead_data['opportunity_name'],
        lead_data['contact_name'],
        lead_data['phone'],
        lead_data['email'],
        lead_data['industry'],
        lead_data['region'],
        lead_data['source'],
        lead_data['link'],
        lead_data['remark'],
        lead_data['raw_data'],
        lead_row['score'],
        lead_row['score_reason'],
    ))
    new_lead_id = cursor.lastrowid

    # 更新 intelligence_leads 状态
    db.execute("UPDATE intelligence_leads SET status='converted', converted_lead_id=? WHERE id=?",
               (new_lead_id, lid))

    # 记录生命周期流转：关联 CRM 线索（情报→线索）
    from lifecycle_model import map_to_crm_stage, get_stage_info
    current_stage = lead_row['lifecycle_stage'] or 'intelligence'
    crm_stage = map_to_crm_stage(current_stage)
    db.execute("""
        INSERT INTO lifecycle_logs (lead_id, from_stage, to_stage, reason, operator, crm_stage)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        lid, current_stage, current_stage,
        f'转入CRM线索#{new_lead_id}（CRM阶段：线索）',
        request.current_user.get('username', ''), 'lead'
    ))
    db.commit()

    record_operation_log(
        request.current_user, 'convert', 'intelligence_leads',
        f'转入CRM:{lead_data["company"]} - {lead_data["opportunity_name"][:30]}'
    )
    return jsonify({
        'code': 200,
        'message': '已转入CRM线索库',
        'data': {'lead_id': new_lead_id, 'company': lead_data['company']}
    })


@intelligence_bp.route('/leads/<int:lid>/reject', methods=['POST'])
@admin_required
def reject_lead(lid):
    """商机作废，需填写作废原因。"""
    data = request.get_json(force=True)
    reason = (data.get('reason') or '').strip()
    if not reason:
        return jsonify({'code': 400, 'message': '请填写作废原因'})

    db = get_db()
    lead = db.execute("SELECT id, status, title FROM intelligence_leads WHERE id=?", (lid,)).fetchone()
    if not lead:
        return jsonify({'code': 404, 'message': '商机不存在'})
    if lead['status'] == 'rejected':
        return jsonify({'code': 400, 'message': '该商机已作废'})

    db.execute("UPDATE intelligence_leads SET status='rejected', reject_reason=? WHERE id=?", (reason, lid))
    db.commit()
    record_operation_log(
        request.current_user, 'reject', 'intelligence_lead',
        f'商机作废:{lead["title"][:30]} 原因:{reason}'
    )
    return jsonify({'code': 200, 'message': '商机已作废', 'data': {'reason': reason}})


@intelligence_bp.route('/leads/<int:lid>/restore', methods=['POST'])
@admin_required
def restore_lead(lid):
    """恢复已作废的商机。"""
    db = get_db()
    lead = db.execute("SELECT id, status FROM intelligence_leads WHERE id=?", (lid,)).fetchone()
    if not lead:
        return jsonify({'code': 404, 'message': '商机不存在'})
    if lead['status'] != 'rejected':
        return jsonify({'code': 400, 'message': '该商机未作废，无需恢复'})

    db.execute("UPDATE intelligence_leads SET status='analyzed', reject_reason=NULL WHERE id=?", (lid,))
    db.commit()
    record_operation_log(request.current_user, 'restore', 'intelligence_lead', f'恢复作废商机:{lid}')
    return jsonify({'code': 200, 'message': '商机已恢复'})


def _delete_leads_by_ids(db, ids):
    """按ID列表删除商机，并清理关联的销售提醒。返回实际删除条数。"""
    placeholders = ','.join('?' * len(ids))
    cur = db.execute(f"DELETE FROM intelligence_leads WHERE id IN ({placeholders})", ids)
    # 清理指向已删商机的销售提醒，避免悬空引用
    db.execute(
        f"DELETE FROM sales_alerts WHERE related_type='intelligence_lead' AND related_id IN ({placeholders})",
        ids
    )
    db.commit()
    return cur.rowcount


@intelligence_bp.route('/leads/<int:lid>', methods=['DELETE'])
@admin_required
def delete_lead(lid):
    """删除单个商机。"""
    db = get_db()
    lead = db.execute("SELECT title FROM intelligence_leads WHERE id=?", (lid,)).fetchone()
    if not lead:
        return jsonify({'code': 404, 'message': '商机不存在'})

    deleted = _delete_leads_by_ids(db, [lid])
    record_operation_log(
        request.current_user, 'delete', 'intelligence_lead',
        f'删除商机:{lead["title"][:30]}'
    )
    return jsonify({'code': 200, 'message': '已删除', 'data': {'deleted': deleted}})


@intelligence_bp.route('/leads/batch-delete', methods=['POST'])
@admin_required
def batch_delete_leads():
    """批量删除商机。"""
    data = request.get_json(silent=True) or {}
    try:
        ids = [int(i) for i in (data.get('ids') or [])]
    except (TypeError, ValueError):
        ids = []
    ids = [i for i in ids if i > 0]
    if not ids:
        return jsonify({'code': 400, 'message': '请选择要删除的商机'})

    db = get_db()
    deleted = _delete_leads_by_ids(db, ids)
    record_operation_log(
        request.current_user, 'batch_delete', 'intelligence_lead',
        f'批量删除商机{deleted}条'
    )
    return jsonify({'code': 200, 'message': f'已删除{deleted}条', 'data': {'deleted': deleted}})


@intelligence_bp.route('/leads/convert-batch', methods=['POST'])
@app_center_or_admin_required
def convert_leads_batch():
    """批量转入 CRM。

    请求体：
    - lead_ids: [int] 商机ID列表
    - min_score: int (可选) 仅转入评分≥此值的商机
    - only_relevant: bool (可选) 仅转入相关商机
    """
    payload = request.current_user
    if payload.get('role') not in ('主任', '院长'):
        return jsonify({'code': 403, 'message': '权限不足'})

    data = request.get_json(silent=True) or {}
    lead_ids = data.get('lead_ids', [])
    min_score = data.get('min_score', 0)
    only_relevant = data.get('only_relevant', True)

    db = get_db()
    if not lead_ids:
        # 未指定ID时，按条件筛选
        sql = "SELECT id FROM intelligence_leads WHERE status='analyzed'"
        params = []
        if min_score:
            sql += " AND score >= ?"
            params.append(min_score)
        if only_relevant:
            sql += " AND is_relevant = 1"
        sql += " ORDER BY score DESC LIMIT 50"
        rows = db.execute(sql, params).fetchall()
        lead_ids = [r['id'] for r in rows]

    if not lead_ids:
        return jsonify({'code': 200, 'data': {'converted': 0, 'skipped': 0, 'message': '无可转入的商机'}})

    converted = 0
    skipped = 0
    errors = []

    for lid in lead_ids:
        lead_row = db.execute("SELECT * FROM intelligence_leads WHERE id=?", (lid,)).fetchone()
        if not lead_row:
            skipped += 1
            continue
        if lead_row['status'] == 'converted':
            skipped += 1
            continue

        try:
            raw_row = None
            if lead_row['raw_intelligence_id']:
                raw_row = db.execute(
                    "SELECT url, publish_date, content, snippet, attachment_path FROM raw_intelligence WHERE id=?",
                    (lead_row['raw_intelligence_id'],)
                ).fetchone()

            # 去重
            link = raw_row['url'] if raw_row else ''
            company = lead_row['buyer'] or ''
            opp_name = lead_row['title'] or ''
            dup_id = None

            if link:
                ex = db.execute("SELECT id FROM scraped_leads WHERE link=?", (link,)).fetchone()
                if ex:
                    dup_id = ex['id']
            if not dup_id and opp_name and company:
                ex = db.execute(
                    "SELECT id FROM scraped_leads WHERE opportunity_name=? AND company=?",
                    (opp_name, company)
                ).fetchone()
                if ex:
                    dup_id = ex['id']

            if dup_id:
                db.execute("UPDATE intelligence_leads SET status='converted', converted_lead_id=? WHERE id=?",
                           (dup_id, lid))
                db.commit()
                skipped += 1
                continue

            if not company:
                skipped += 1
                continue

            lead_data = _build_lead_from_intel(lead_row, raw_row)
            cursor = db.execute("""
                INSERT INTO scraped_leads (
                    source_id, company, opportunity_name, contact_name, phone, email,
                    industry, region, source, link, remark, raw_data,
                    intent_score, eval_reason, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'evaluated')
            """, (
                lead_row['source_id'],
                lead_data['company'],
                lead_data['opportunity_name'],
                lead_data['contact_name'],
                lead_data['phone'],
                lead_data['email'],
                lead_data['industry'],
                lead_data['region'],
                lead_data['source'],
                lead_data['link'],
                lead_data['remark'],
                lead_data['raw_data'],
                lead_row['score'],
                lead_row['score_reason'],
            ))
            new_id = cursor.lastrowid
            db.execute("UPDATE intelligence_leads SET status='converted', converted_lead_id=? WHERE id=?",
                       (new_id, lid))
            db.commit()
            converted += 1
        except Exception as e:
            errors.append(f'#{lid}: {e}')

    record_operation_log(
        payload['username'], 'convert_batch', 'intelligence_leads',
        f'批量转入CRM {converted}条 跳过{skipped}条'
    )
    return jsonify({
        'code': 200,
        'data': {'converted': converted, 'skipped': skipped, 'errors': errors[:5]}
    })


# ==================== Phase5: AI日报 ====================

@intelligence_bp.route('/daily-report', methods=['POST'])
@admin_required
def generate_daily_report():
    """生成 AI 日报（可指定日期，默认今天）。"""
    from ai_daily_report import generate_daily_report as gen_report

    data = request.get_json(silent=True) or {}
    report_date = data.get('date')  # YYYY-MM-DD，可选

    result = gen_report(report_date)
    if not result:
        return jsonify({'code': 500, 'message': '日报生成失败'})

    record_operation_log(
        request.current_user, 'generate_report', 'ai_daily_reports',
        f'生成日报:{result.get("report_date")}'
    )
    return jsonify({'code': 200, 'data': result})


@intelligence_bp.route('/daily-reports', methods=['GET'])
@token_required
def list_daily_reports():
    """日报列表。"""
    db = get_db()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    offset = (page - 1) * per_page

    total = db.execute("SELECT COUNT(*) as cnt FROM ai_daily_reports").fetchone()['cnt']
    rows = db.execute("""
        SELECT id, report_date, title, summary, metrics, generated_by, created_at
        FROM ai_daily_reports ORDER BY report_date DESC LIMIT ? OFFSET ?
    """, (per_page, offset)).fetchall()

    return jsonify({
        'code': 200,
        'data': [dict(r) for r in rows],
        'total': total,
    })


@intelligence_bp.route('/daily-reports/<report_date>', methods=['GET'])
@token_required
def get_daily_report(report_date):
    """日报详情（按日期）。"""
    db = get_db()
    row = db.execute("""
        SELECT * FROM ai_daily_reports WHERE report_date=?
    """, (report_date,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '日报不存在'})

    data = dict(row)
    # 解析 JSON 字段
    for field in ('metrics', 'opportunities', 'recommendations'):
        if data.get(field):
            try:
                data[field] = json.loads(data[field])
            except (json.JSONDecodeError, TypeError):
                pass

    return jsonify({'code': 200, 'data': data})
