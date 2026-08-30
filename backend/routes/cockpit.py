"""AI驾驶舱路由。

Phase6: 提供全局指标汇总、趋势分析、商机雷达数据、AI搜索。
"""
import json
import sqlite3
import logging
from datetime import date, timedelta

from flask import request, jsonify, g
from extensions import get_db, token_required, admin_required, record_operation_log
from . import cockpit_bp

logger = logging.getLogger(__name__)


def register_routes(app):
    app.register_blueprint(cockpit_bp, url_prefix='/api/cockpit')


@cockpit_bp.route('/overview', methods=['GET'])
@token_required
def overview():
    """驾驶舱总览：关键指标卡片。"""
    db = get_db()
    today = date.today().isoformat()

    # 今日指标
    today_intel = db.execute(
        "SELECT COUNT(*) as c FROM raw_intelligence WHERE collected_at LIKE ?", (f'{today}%',)
    ).fetchone()['c']
    today_analyzed = db.execute(
        "SELECT COUNT(*) as c FROM intelligence_leads WHERE created_at LIKE ?", (f'{today}%',)
    ).fetchone()['c']
    today_converted = db.execute(
        "SELECT COUNT(*) as c FROM intelligence_leads WHERE status='converted' AND created_at LIKE ?",
        (f'{today}%',)
    ).fetchone()['c']

    # 总量指标
    total_intel = db.execute("SELECT COUNT(*) as c FROM raw_intelligence").fetchone()['c']
    pending_intel = db.execute(
        "SELECT COUNT(*) as c FROM raw_intelligence WHERE status='pending'"
    ).fetchone()['c']
    total_leads = db.execute("SELECT COUNT(*) as c FROM intelligence_leads").fetchone()['c']
    total_converted = db.execute(
        "SELECT COUNT(*) as c FROM intelligence_leads WHERE status='converted'"
    ).fetchone()['c']
    high_value = db.execute(
        "SELECT COUNT(*) as c FROM intelligence_leads WHERE score >= 60"
    ).fetchone()['c']

    # 数据源数量
    total_sources = db.execute("SELECT COUNT(*) as c FROM lead_sources WHERE enabled=1").fetchone()['c']

    # CRM线索
    crm_ai_leads = db.execute(
        "SELECT COUNT(*) as c FROM scraped_leads WHERE source='AI商机识别'"
    ).fetchone()['c']

    return jsonify({
        'code': 200,
        'data': {
            'today': {
                'collected': today_intel,
                'analyzed': today_analyzed,
                'converted': today_converted,
            },
            'total': {
                'intelligence': total_intel,
                'pending': pending_intel,
                'leads': total_leads,
                'converted': total_converted,
                'high_value': high_value,
                'sources': total_sources,
                'crm_leads': crm_ai_leads,
            }
        }
    })


@cockpit_bp.route('/trend', methods=['GET'])
@token_required
def trend():
    """最近7天趋势：采集/分析/转入。"""
    db = get_db()
    days = request.args.get('days', 7, type=int)
    if days > 30:
        days = 30

    result = []
    for i in range(days - 1, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        collected = db.execute(
            "SELECT COUNT(*) as c FROM raw_intelligence WHERE collected_at LIKE ?", (f'{d}%',)
        ).fetchone()['c']
        analyzed = db.execute(
            "SELECT COUNT(*) as c FROM intelligence_leads WHERE created_at LIKE ?", (f'{d}%',)
        ).fetchone()['c']
        converted = db.execute(
            "SELECT COUNT(*) as c FROM intelligence_leads WHERE status='converted' AND created_at LIKE ?",
            (f'{d}%',)
        ).fetchone()['c']
        result.append({'date': d, 'collected': collected, 'analyzed': analyzed, 'converted': converted})

    return jsonify({'code': 200, 'data': result})


@cockpit_bp.route('/distribution', methods=['GET'])
@token_required
def distribution():
    """分布统计：评分/采购方式/地区/项目类型。"""
    db = get_db()

    # 评分分布
    score_dist = []
    for rng in [(0, 20), (20, 40), (40, 60), (60, 80), (80, 101)]:
        cnt = db.execute(
            "SELECT COUNT(*) as c FROM intelligence_leads WHERE score >= ? AND score < ?",
            (rng[0], rng[1])
        ).fetchone()['c']
        score_dist.append({'range': f'{rng[0]}-{rng[1]-1}', 'count': cnt})

    # 采购方式分布
    method_dist = db.execute("""
        SELECT COALESCE(procurement_method, '未分类') as method, COUNT(*) as c
        FROM intelligence_leads GROUP BY procurement_method ORDER BY c DESC
    """).fetchall()

    # 地区分布
    region_dist = db.execute("""
        SELECT COALESCE(region, '未分类') as region, COUNT(*) as c
        FROM intelligence_leads WHERE region != ''
        GROUP BY region ORDER BY c DESC LIMIT 10
    """).fetchall()

    # 项目类型分布
    type_dist = db.execute("""
        SELECT COALESCE(project_type, '未分类') as ptype, COUNT(*) as c
        FROM intelligence_leads GROUP BY project_type ORDER BY c DESC
    """).fetchall()

    # 相关性分布
    relevant_dist = db.execute("""
        SELECT is_relevant, COUNT(*) as c FROM intelligence_leads GROUP BY is_relevant
    """).fetchall()

    return jsonify({
        'code': 200,
        'data': {
            'score': [dict(r) for r in score_dist],
            'method': [dict(r) for r in method_dist],
            'region': [dict(r) for r in region_dist],
            'type': [dict(r) for r in type_dist],
            'relevant': [dict(r) for r in relevant_dist],
        }
    })


@cockpit_bp.route('/radar', methods=['GET'])
@token_required
def radar():
    """商机雷达：散点图数据（评分 vs 紧迫性，气泡=预算）。"""
    db = get_db()
    min_score = request.args.get('min_score', 0, type=int)
    limit = request.args.get('limit', 50, type=int)

    rows = db.execute("""
        SELECT il.id, il.title, il.buyer, il.score, il.budget, il.deadline,
               il.region, il.procurement_method, il.is_relevant, il.status,
               il.analysis_summary
        FROM intelligence_leads il
        WHERE il.score >= ?
        ORDER BY il.score DESC LIMIT ?
    """, (min_score, limit)).fetchall()

    today = date.today()
    items = []
    for r in rows:
        # 计算紧迫性（距今天数，越小越紧迫）
        urgency = 30  # 默认30天
        if r['deadline']:
            try:
                dl = date.fromisoformat(r['deadline'][:10])
                urgency = max(0, (dl - today).days)
            except (ValueError, TypeError):
                pass

        # 解析预算金额
        budget_num = 0
        if r['budget']:
            import re
            m = re.search(r'([\d.]+)\s*万', r['budget'])
            if m:
                budget_num = float(m.group(1))
            else:
                m = re.search(r'([\d.]+)', r['budget'])
                if m:
                    budget_num = float(m.group(1)) / 10000  # 转为万元

        items.append({
            'id': r['id'],
            'title': r['title'],
            'buyer': r['buyer'],
            'score': r['score'],
            'urgency': urgency,
            'budget': budget_num,
            'region': r['region'],
            'method': r['procurement_method'],
            'relevant': r['is_relevant'],
            'status': r['status'],
            'summary': r['analysis_summary'],
        })

    return jsonify({'code': 200, 'data': items})


@cockpit_bp.route('/ai-search', methods=['POST'])
@token_required
def ai_search():
    """AI搜索：自然语言问答，跨库检索+LLM回答。"""
    from config import USE_LLM

    data = request.get_json(force=True)
    query = (data.get('query') or '').strip()
    if not query:
        return jsonify({'code': 400, 'message': '请输入搜索内容'})

    db = get_db()

    # 1. 关键词检索：在 raw_intelligence 和 intelligence_leads 中搜索
    keywords = query.split()
    # 原始情报搜索（title + content + snippet）
    raw_where = []
    raw_params = []
    for kw in keywords:
        raw_where.append("(ri.title LIKE ? OR ri.content LIKE ? OR ri.snippet LIKE ?)")
        raw_params.extend([f'%{kw}%', f'%{kw}%', f'%{kw}%'])
    raw_clause = ' AND '.join(raw_where) if raw_where else '1=1'

    # 搜索原始情报
    raw_results = db.execute(f"""
        SELECT ri.id, ri.title, ri.url, ri.publish_date,
               SUBSTR(COALESCE(ri.content, ri.snippet, ''), 1, 200) as preview,
               ls.name as source_name
        FROM raw_intelligence ri
        LEFT JOIN lead_sources ls ON ri.source_id = ls.id
        WHERE {raw_clause}
        ORDER BY ri.collected_at DESC LIMIT 5
    """, raw_params).fetchall()

    # 搜索商机
    lead_results = db.execute(f"""
        SELECT il.id, il.title, il.buyer, il.budget, il.deadline, il.score,
               il.procurement_method, il.region, il.analysis_summary, il.status
        FROM intelligence_leads il
        WHERE (il.title LIKE ? OR il.buyer LIKE ? OR il.analysis_summary LIKE ?)
        ORDER BY il.score DESC LIMIT 5
    """, [f'%{query}%', f'%{query}%', f'%{query}%']).fetchall()

    # 搜索CRM线索
    crm_results = db.execute("""
        SELECT id, company, opportunity_name, intent_score, status, assigned_to, region
        FROM scraped_leads
        WHERE (company LIKE ? OR opportunity_name LIKE ?)
        ORDER BY intent_score DESC LIMIT 5
    """, [f'%{query}%', f'%{query}%']).fetchall()

    # 2. 组织上下文
    context_parts = []
    if raw_results:
        context_parts.append("【相关情报】")
        for r in raw_results:
            context_parts.append(f"- {r['title']}\n  {r['preview']}")

    if lead_results:
        context_parts.append("\n【相关商机】")
        for r in lead_results:
            budget = r['budget'] if r['budget'] else ''
            deadline = r['deadline'] if r['deadline'] else ''
            context_parts.append(
                f"- [{r['score']}分] {r['title']}\n"
                f"  采购:{r['buyer']} 预算:{budget} 截止:{deadline}"
            )

    if crm_results:
        context_parts.append("\n【CRM线索】")
        for r in crm_results:
            context_parts.append(
                f"- {r['company']} | {r['opportunity_name']} | 分:{r['intent_score']}"
            )

    context = '\n'.join(context_parts) if context_parts else '未找到相关数据'

    # 3. LLM 生成回答
    answer = ''
    if USE_LLM:
        try:
            from qa_engine import call_llm
            prompt = f"""用户搜索：{query}

根据以下数据库检索结果，回答用户问题：

{context}

要求：
1. 用中文回答
2. 总结检索到的关键信息
3. 如果有商机，列出评分最高的
4. 简洁明了，不超过300字"""

            messages = [
                {'role': 'system', 'content': '你是AI销售情报助手，基于数据库检索结果回答用户的自然语言查询。'},
                {'role': 'user', 'content': prompt},
            ]
            answer = call_llm(messages, max_tokens=2000, timeout=60, enable_thinking=False) or ''
        except Exception as e:
            logger.error(f'AI搜索LLM调用失败: {e}')

    # 降级：无 LLM 时用模板回答
    if not answer:
        total = len(raw_results) + len(lead_results) + len(crm_results)
        if total == 0:
            answer = f'未找到与"{query}"相关的信息。'
        else:
            answer = f'搜索到{len(raw_results)}条情报、{len(lead_results)}条商机、{len(crm_results)}条CRM线索。'
            if lead_results:
                top = lead_results[0]
                answer += f' 最高评分商机：{top["title"]}（{top["score"]}分），采购单位：{top["buyer"]}。'

    return jsonify({
        'code': 200,
        'data': {
            'answer': answer,
            'raw_count': len(raw_results),
            'lead_count': len(lead_results),
            'crm_count': len(crm_results),
            'raw_results': [dict(r) for r in raw_results],
            'lead_results': [dict(r) for r in lead_results],
            'crm_results': [dict(r) for r in crm_results],
        }
    })


# ==================== Phase7: 日志+监控 ====================

@cockpit_bp.route('/logs', methods=['GET'])
@admin_required
def operation_logs():
    """操作日志查看器。"""
    db = get_db()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    action = request.args.get('action', '').strip()
    offset = (page - 1) * per_page

    sql = "SELECT * FROM operation_logs WHERE 1=1"
    params = []
    if search:
        sql += " AND (operator LIKE ? OR target LIKE ? OR detail LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
    if action:
        sql += " AND action = ?"
        params.append(action)

    total = db.execute(f"SELECT COUNT(*) as c FROM ({sql})", params).fetchone()['c']
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    rows = db.execute(sql, params).fetchall()

    return jsonify({
        'code': 200,
        'data': [dict(r) for r in rows],
        'total': total,
        'page': page,
    })


@cockpit_bp.route('/health', methods=['GET'])
@token_required
def health_check():
    """系统健康检查：数据库+LLM+调度器+磁盘。"""
    import os
    import shutil
    from config import USE_LLM, LLM_API_BASE, LLM_MODEL

    checks = {}

    # 1. 数据库
    try:
        db = get_db()
        db.execute("SELECT 1").fetchone()
        checks['database'] = {'status': 'ok', 'message': 'SQLite连接正常'}
    except Exception as e:
        checks['database'] = {'status': 'error', 'message': str(e)}

    # 2. LLM
    checks['llm'] = {
        'status': 'enabled' if USE_LLM else 'disabled',
        'api_base': LLM_API_BASE or 'not configured',
        'model': LLM_MODEL or 'not configured',
    }

    # 3. 调度器
    try:
        from scheduler import scheduler_running
        checks['scheduler'] = {
            'status': 'running' if scheduler_running else 'stopped',
        }
    except Exception:
        checks['scheduler'] = {'status': 'unknown'}

    # 4. 磁盘
    try:
        from extensions import DB_PATH
        db_dir = os.path.dirname(DB_PATH) or '.'
        usage = shutil.disk_usage(db_dir)
        checks['disk'] = {
            'total_gb': round(usage.total / 1024**3, 1),
            'used_gb': round(usage.used / 1024**3, 1),
            'free_gb': round(usage.free / 1024**3, 1),
            'usage_percent': round(usage.used / usage.total * 100, 1),
        }
    except Exception as e:
        checks['disk'] = {'status': 'error', 'message': str(e)}

    # 5. 数据量统计
    try:
        db = get_db()
        checks['data'] = {
            'raw_intelligence': db.execute("SELECT COUNT(*) as c FROM raw_intelligence").fetchone()['c'],
            'intelligence_leads': db.execute("SELECT COUNT(*) as c FROM intelligence_leads").fetchone()['c'],
            'scraped_leads': db.execute("SELECT COUNT(*) as c FROM scraped_leads").fetchone()['c'],
            'keywords': db.execute("SELECT COUNT(*) as c FROM keywords").fetchone()['c'],
            'daily_reports': db.execute("SELECT COUNT(*) as c FROM ai_daily_reports").fetchone()['c'],
        }
    except Exception:
        pass

    # 6. 最近错误日志
    try:
        recent_errors = db.execute("""
            SELECT * FROM operation_logs WHERE action='error' OR detail LIKE '%失败%'
            ORDER BY id DESC LIMIT 5
        """).fetchall()
        checks['recent_errors'] = [dict(r) for r in recent_errors]
    except Exception:
        checks['recent_errors'] = []

    all_ok = all(v.get('status') in ('ok', 'enabled', 'running') for v in checks.values() if isinstance(v, dict) and 'status' in v)
    return jsonify({
        'code': 200,
        'data': {
            'overall': 'healthy' if all_ok else 'warning',
            'checks': checks,
        }
    })


# ==================== Phase8: 客户画像+竞争对手+销售提醒 ====================

@cockpit_bp.route('/analyze-all', methods=['POST'])
@admin_required
def analyze_all():
    """一键执行全部分析：客户画像+竞争对手+销售提醒。"""
    from ai_analysis import run_full_analysis
    result = run_full_analysis()
    record_operation_log(
        request.current_user, 'analyze_all', 'ai_analysis',
        f'客户{result["customer_profiles"]} 竞争对手{result["competitor_profiles"]} 提醒{result["sales_alerts"]}'
    )
    return jsonify({'code': 200, 'data': result})


@cockpit_bp.route('/customers', methods=['GET'])
@token_required
def customer_list():
    """客户画像列表。"""
    db = get_db()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    offset = (page - 1) * per_page

    sql = "SELECT * FROM customer_profiles WHERE 1=1"
    params = []
    if search:
        sql += " AND (buyer LIKE ? OR industry LIKE ? OR region LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])

    total = db.execute(f"SELECT COUNT(*) as c FROM ({sql})", params).fetchone()['c']
    sql += " ORDER BY total_procurements DESC, max_score DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    rows = db.execute(sql, params).fetchall()

    return jsonify({
        'code': 200,
        'data': [dict(r) for r in rows],
        'total': total,
    })


@cockpit_bp.route('/customers/<int:cid>', methods=['GET'])
@token_required
def customer_detail(cid):
    """客户画像详情。"""
    db = get_db()
    row = db.execute("SELECT * FROM customer_profiles WHERE id=?", (cid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '客户不存在'})

    data = dict(row)
    for field in ('procurement_methods', 'competitors', 'project_types', 'timeline'):
        if data.get(field):
            try:
                data[field] = json.loads(data[field])
            except (json.JSONDecodeError, TypeError):
                pass

    # CRM 关联检查：该采购单位是否已建立客户档案（与销售管理的客户画像互补联动）
    crm_link = None
    buyer = data.get('buyer') or ''
    if buyer:
        crm_row = db.execute("""
            SELECT c.id, c.company, u.name as owner_name
            FROM customers c LEFT JOIN users u ON c.owner_id = u.username
            WHERE c.company = ? OR (? LIKE c.company || '%')
            LIMIT 1
        """, (buyer, buyer)).fetchone()
        if crm_row:
            crm_link = dict(crm_row)
    return jsonify({'code': 200, 'data': data, 'crm_link': crm_link})


@cockpit_bp.route('/customers/<int:cid>', methods=['DELETE'])
@admin_required
def customer_delete(cid):
    """删除单个客户画像（仅删除AI生成的画像记录，不影响客户主数据）。"""
    db = get_db()
    row = db.execute("SELECT buyer FROM customer_profiles WHERE id=?", (cid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '客户画像不存在'})

    db.execute("DELETE FROM customer_profiles WHERE id=?", (cid,))
    db.commit()
    record_operation_log(request.current_user, 'delete', 'customer_profile', f'删除客户画像:{row["buyer"][:30]}')
    return jsonify({'code': 200, 'message': '已删除'})


@cockpit_bp.route('/customers/batch-delete', methods=['POST'])
@admin_required
def customer_batch_delete():
    """批量删除客户画像。"""
    data = request.get_json(silent=True) or {}
    try:
        ids = [int(i) for i in (data.get('ids') or [])]
    except (TypeError, ValueError):
        ids = []
    ids = [i for i in ids if i > 0]
    if not ids:
        return jsonify({'code': 400, 'message': '请选择要删除的客户画像'})

    db = get_db()
    placeholders = ','.join('?' * len(ids))
    cur = db.execute(f"DELETE FROM customer_profiles WHERE id IN ({placeholders})", ids)
    db.commit()
    record_operation_log(request.current_user, 'batch_delete', 'customer_profile', f'批量删除客户画像{cur.rowcount}条')
    return jsonify({'code': 200, 'message': f'已删除{cur.rowcount}条', 'data': {'deleted': cur.rowcount}})


@cockpit_bp.route('/competitors', methods=['GET'])
@token_required
def competitor_list():
    """竞争对手画像列表。"""
    db = get_db()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    offset = (page - 1) * per_page

    sql = "SELECT * FROM competitor_profiles WHERE 1=1"
    params = []
    if search:
        sql += " AND name LIKE ?"
        params.append(f'%{search}%')

    total = db.execute(f"SELECT COUNT(*) as c FROM ({sql})", params).fetchone()['c']
    sql += " ORDER BY appearance_count DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    rows = db.execute(sql, params).fetchall()

    return jsonify({
        'code': 200,
        'data': [dict(r) for r in rows],
        'total': total,
    })


@cockpit_bp.route('/alerts', methods=['GET'])
@token_required
def alert_list():
    """销售提醒列表。"""
    db = get_db()
    status = request.args.get('status', 'unread')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page

    sql = "SELECT * FROM sales_alerts WHERE 1=1"
    params = []
    if status and status != 'all':
        sql += " AND status=?"
        params.append(status)

    total = db.execute(f"SELECT COUNT(*) as c FROM ({sql})", params).fetchone()['c']
    sql += " ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 ELSE 2 END, created_at DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    rows = db.execute(sql, params).fetchall()

    # 统计未读数
    unread = db.execute(
        "SELECT COUNT(*) as c FROM sales_alerts WHERE status='unread'"
    ).fetchone()['c']

    return jsonify({
        'code': 200,
        'data': [dict(r) for r in rows],
        'total': total,
        'unread': unread,
    })


@cockpit_bp.route('/alerts/<int:aid>/read', methods=['POST'])
@token_required
def mark_alert_read(aid):
    """标记提醒为已读。"""
    db = get_db()
    from datetime import datetime
    db.execute("UPDATE sales_alerts SET status='read', read_at=? WHERE id=?",
               (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), aid))
    db.commit()
    return jsonify({'code': 200, 'message': '已标记为已读'})


@cockpit_bp.route('/alerts/read-all', methods=['POST'])
@token_required
def mark_all_alerts_read():
    """全部标记为已读。"""
    db = get_db()
    from datetime import datetime
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.execute("UPDATE sales_alerts SET status='read', read_at=? WHERE status='unread'", (now,))
    db.commit()
    return jsonify({'code': 200, 'message': '全部已标记为已读'})
