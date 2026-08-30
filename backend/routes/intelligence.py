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
               ls.name as source_name
        FROM raw_intelligence ri
        LEFT JOIN lead_sources ls ON ri.source_id = ls.id
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
    match_list, exclude_list = _load_active_keywords(db)
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

            # 关键词管理联动：排除词过滤 + 业务关键词匹配（与业务无关的内容不入库）
            keep, matched = _match_business_keywords(title, item.content, item.snippet, match_list, exclude_list)
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

            match_list, exclude_list = _load_active_keywords(db)
            new_count = 0
            filtered_count = 0
            for item in items:
                item = collector.fetch_detail(item) if item.url else item
                from utils.cleaner import clean_title, is_junk_content
                title = clean_title(item.title) if item.title else ''
                # 关键词管理联动：排除词过滤 + 业务关键词匹配
                keep, matched = _match_business_keywords(title, item.content, item.snippet, match_list, exclude_list)
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
