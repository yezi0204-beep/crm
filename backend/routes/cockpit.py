"""AI驾驶舱路由。

Phase6: 提供全局指标汇总、趋势分析、商机雷达数据、AI搜索。
"""
import json
import sqlite3
import logging
from datetime import date, timedelta

from flask import request, jsonify, g
from extensions import (get_db, token_required, admin_required,
                        require_permission, record_operation_log)
from config import USE_LLM
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

    # 商机等级统计（S/A级）
    grade_s = db.execute(
        "SELECT COUNT(*) as c FROM intelligence_leads WHERE score_grade='S'"
    ).fetchone()['c']
    grade_a = db.execute(
        "SELECT COUNT(*) as c FROM intelligence_leads WHERE score_grade='A'"
    ).fetchone()['c']

    # 生命周期阶段统计（采购意向/招标项目）
    purchase_intent = db.execute("""
        SELECT COUNT(*) as c FROM intelligence_leads
        WHERE lifecycle_stage='purchase_intent' AND status NOT IN ('rejected', 'merged')
    """).fetchone()['c']
    tender_count = db.execute("""
        SELECT COUNT(*) as c FROM intelligence_leads
        WHERE lifecycle_stage IN ('tender_announcement', 'bid_opening')
          AND status NOT IN ('rejected', 'merged')
    """).fetchone()['c']

    # 今日竞争对手动态（今日情报中出现的竞争对手次数）
    today_comp = db.execute("""
        SELECT COUNT(*) as c FROM intelligence_leads
        WHERE competitors IS NOT NULL AND competitors != '[]'
          AND created_at LIKE ? AND status NOT IN ('rejected', 'merged')
    """, (f'{today}%',)).fetchone()['c']

    # 今日客户动态（今日有新采购信息的客户数）
    today_customer_moves = db.execute("""
        SELECT COUNT(DISTINCT buyer) as c FROM intelligence_leads
        WHERE created_at LIKE ? AND buyer != ''
          AND status NOT IN ('rejected', 'merged')
    """, (f'{today}%',)).fetchone()['c']

    return jsonify({
        'code': 200,
        'data': {
            'today': {
                'collected': today_intel,
                'analyzed': today_analyzed,
                'converted': today_converted,
                'competitor_moves': today_comp,
                'customer_moves': today_customer_moves,
            },
            'total': {
                'intelligence': total_intel,
                'pending': pending_intel,
                'leads': total_leads,
                'converted': total_converted,
                'high_value': high_value,
                'sources': total_sources,
                'crm_leads': crm_ai_leads,
                'grade_s': grade_s,
                'grade_a': grade_a,
                'purchase_intent': purchase_intent,
                'tender_projects': tender_count,
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

    # 金额分布（按预算解析为万元，分段统计）
    budget_rows = db.execute("""
        SELECT budget FROM intelligence_leads
        WHERE budget IS NOT NULL AND budget != ''
          AND status NOT IN ('rejected', 'merged')
    """).fetchall()
    import re as _re
    budget_ranges = [(0, 100, '<100万'), (100, 500, '100-500万'),
                     (500, 1000, '500-1000万'), (1000, 5000, '1000-5000万'),
                     (5000, 10**9, '≥5000万')]
    amount_dist = [{'range': label, 'count': 0, 'amount': 0.0} for _, __, label in budget_ranges]
    for br in budget_rows:
        m = _re.search(r'([\d.]+)\s*万', str(br['budget']))
        wan = float(m.group(1)) if m else 0
        if not wan:
            m2 = _re.search(r'([\d.]+)\s*元', str(br['budget']))
            if m2:
                wan = float(m2.group(1)) / 10000
        if wan <= 0:
            continue
        for i, (lo, hi, label) in enumerate(budget_ranges):
            if lo <= wan < hi:
                amount_dist[i]['count'] += 1
                amount_dist[i]['amount'] = round(amount_dist[i]['amount'] + wan, 2)
                break

    # 竞争对手中标动态（最近30天按竞争对手统计，Python端解析JSON，兼容SQLite 3.32）
    comp_rows = db.execute("""
        SELECT competitors, COUNT(*) as c
        FROM intelligence_leads
        WHERE status NOT IN ('rejected', 'merged')
          AND competitors IS NOT NULL AND competitors != ''
          AND created_at >= date('now', '-30 days')
        GROUP BY competitors
    """).fetchall()
    comp_counter = {}
    for cr in comp_rows:
        try:
            names = json.loads(cr['competitors'])
            if not isinstance(names, list):
                continue
        except (json.JSONDecodeError, TypeError):
            continue
        for name in names:
            if name:
                comp_counter[name] = comp_counter.get(name, 0) + cr['c']
    comp_dist = sorted(
        [{'name': k, 'c': v} for k, v in comp_counter.items()],
        key=lambda x: -x['c'])[:10]

    return jsonify({
        'code': 200,
        'data': {
            'score': [dict(r) for r in score_dist],
            'method': [dict(r) for r in method_dist],
            'region': [dict(r) for r in region_dist],
            'type': [dict(r) for r in type_dist],
            'relevant': [dict(r) for r in relevant_dist],
            'amount': amount_dist,
            'competitors': [dict(r) for r in comp_dist],
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


@cockpit_bp.route('/radar-list', methods=['GET'])
@token_required
def radar_list():
    """商机雷达列表：多条件筛选 + 分页。

    筛选：search(关键词)/industry(行业)/business(业务标签)/region(地区)/
         budget_min/budget_max(万元)/date_from/date_to(发布时间)/
         stage(项目阶段)/grade(商机等级)/buyer(客户)/competitor(竞争对手)
    """
    from scoring_model import grade_of
    db = get_db()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page

    search = request.args.get('search', '').strip()
    industry = request.args.get('industry', '').strip()
    business = request.args.get('business', '').strip()
    region = request.args.get('region', '').strip()
    budget_min = request.args.get('budget_min', type=float)
    budget_max = request.args.get('budget_max', type=float)
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    stage = request.args.get('stage', '').strip()
    grade = request.args.get('grade', '').strip()
    buyer = request.args.get('buyer', '').strip()
    competitor = request.args.get('competitor', '').strip()

    sql = """
        SELECT il.id, il.title, il.buyer, il.score, il.score_grade, il.budget,
               il.deadline, il.region, il.procurement_method, il.project_type,
               il.lifecycle_stage, il.created_at, il.source_id, il.status,
               il.analysis_summary, il.competitors, il.keywords_matched,
               ls.name as source_name, sl.assigned_to as owner_name
        FROM intelligence_leads il
        LEFT JOIN lead_sources ls ON il.source_id = ls.id
        LEFT JOIN scraped_leads sl ON il.converted_lead_id = sl.id
        WHERE il.status NOT IN ('rejected', 'merged')
    """
    params = []
    if search:
        sql += " AND (il.title LIKE ? OR il.analysis_summary LIKE ? OR il.buyer LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
    if industry:
        sql += " AND il.project_type LIKE ?"
        params.append(f'%{industry}%')
    if business:
        sql += " AND il.keywords_matched LIKE ?"
        params.append(f'%{business}%')
    if region:
        sql += " AND il.region LIKE ?"
        params.append(f'%{region}%')
    if stage:
        sql += " AND il.lifecycle_stage=?"
        params.append(stage)
    if grade:
        sql += " AND il.score_grade=?"
        params.append(grade)
    if buyer:
        sql += " AND il.buyer LIKE ?"
        params.append(f'%{buyer}%')
    if competitor:
        sql += " AND il.competitors LIKE ?"
        params.append(f'%{competitor}%')
    if date_from:
        sql += " AND date(il.created_at) >= date(?)"
        params.append(date_from)
    if date_to:
        sql += " AND date(il.created_at) <= date(?)"
        params.append(date_to)

    # 金额筛选：内存过滤（预算为文本格式）
    if budget_min is not None or budget_max is not None:
        rows = db.execute(sql, params).fetchall()
    else:
        total = db.execute(f"SELECT COUNT(*) as c FROM ({sql})", params).fetchone()['c']
        sql += " ORDER BY il.score DESC, il.created_at DESC LIMIT ? OFFSET ?"
        params2 = params + [per_page, offset]
        rows = db.execute(sql, params2).fetchall()

    # 解析预算
    import re as _re

    def parse_wan(budget_str):
        if not budget_str:
            return 0
        m = _re.search(r'([\d.]+)\s*万', str(budget_str))
        if m:
            return float(m.group(1))
        m2 = _re.search(r'([\d.]+)\s*元', str(budget_str))
        if m2:
            return float(m2.group(1)) / 10000
        return 0

    def parse_comps(raw):
        try:
            v = json.loads(raw) if raw else []
            return v if isinstance(v, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    if budget_min is not None or budget_max is not None:
        lo = budget_min if budget_min is not None else 0
        hi = budget_max if budget_max is not None else 10**9
        rows = [r for r in rows if lo <= parse_wan(r['budget']) < hi]

    total = len(rows) if (budget_min is not None or budget_max is not None) else total
    if budget_min is not None or budget_max is not None:
        rows = rows[offset:offset + per_page]

    items = []
    for r in rows:
        items.append({
            'id': r['id'],
            'title': r['title'],
            'buyer': r['buyer'],
            'industry': r['project_type'] or '',
            'region': r['region'] or '',
            'budget': r['budget'] or '',
            'budget_wan': parse_wan(r['budget']),
            'stage': r['lifecycle_stage'] or '',
            'score': r['score'] or 0,
            'grade': r['score_grade'] or grade_of(r['score'] or 0),
            'created_at': (r['created_at'][:10] if r['created_at'] else ''),
            'source': r['source_name'] or '',
            'owner_name': r['owner_name'] or '',
            'competitors': parse_comps(r['competitors']),
            'business_tags': r['keywords_matched'] or '',
            'summary': (r['analysis_summary'] or '')[:150],
        })

    return jsonify({'code': 200, 'data': items, 'total': total,
                    'page': page, 'per_page': per_page})


@cockpit_bp.route('/ai-search', methods=['POST'])
@token_required
def ai_search():
    """AI情报搜索：自然语言 → 结构化条件(SQL) + 关键词 + 向量 + LLM 混合检索。

    示例查询：
      "最近三个月安徽有哪些500万以上的遥感项目？"
      "有哪些客户最近准备采购AI？"
      "XX科技今年中标了哪些项目？"
    """
    from llm_gateway import gateway_analyze

    data = request.get_json(force=True)
    query = (data.get('query') or '').strip()
    if not query:
        return jsonify({'code': 400, 'message': '请输入搜索内容'})

    db = get_db()

    # ---------- 1. LLM 解析查询意图为结构化条件 ----------
    structured = {}
    if gateway_analyze:
        try:
            parse_prompt = f"""将用户的自然语言查询解析为结构化检索条件。

用户查询：{query}

只返回JSON（没有的条件设为null）：
{{"region": "地区关键词|null", "industry": "行业关键词|null",
  "budget_min_wan": 金额下限(万元数字)|null, "budget_max_wan": 金额上限|null,
  "days_back": 时间范围天数|null, "keywords": ["核心检索词1", "核心检索词2"],
  "company": "公司名|null", "intent": "查商机|查客户|查竞争对手|查项目|其他"}}"""
            parsed_raw = gateway_analyze(
                parse_prompt, system_prompt='你是查询解析器，只返回JSON。',
                max_tokens=500, timeout=30, operation_type='ai_search_parse',
                data_source='cockpit', operator=request.current_user)
            if parsed_raw:
                import re as _re2
                m = _re2.search(r'\{.*\}', parsed_raw, _re2.DOTALL)
                if m:
                    structured = json.loads(m.group())
        except Exception as e:
            logger.warning(f'AI搜索意图解析失败: {e}')

    # ---------- 2. 结构化 SQL 查询 ----------
    struct_results = []
    cond_parts = ["il.status NOT IN ('rejected', 'merged')"]
    sparams = []
    if structured.get('region'):
        cond_parts.append('il.region LIKE ?')
        sparams.append(f"%{structured['region']}%")
    if structured.get('industry'):
        cond_parts.append('(il.project_type LIKE ? OR il.keywords_matched LIKE ?)')
        sparams.extend([f"%{structured['industry']}%", f"%{structured['industry']}%"])
    if structured.get('company'):
        cond_parts.append('(il.buyer LIKE ? OR il.competitors LIKE ? OR il.title LIKE ?)')
        sparams.extend([f"%{structured['company']}%"] * 3)
    if structured.get('days_back'):
        cond_parts.append("date(il.created_at) >= date('now', ?)")
        sparams.append(f'-{int(structured["days_back"])} days')
    # 金额条件在内存中过滤（预算为文本）
    if len(cond_parts) > 1:
        try:
            srows = db.execute(f"""
                SELECT il.id, il.title, il.buyer, il.budget, il.score, il.score_grade,
                       il.region, il.project_type, il.created_at
                FROM intelligence_leads il WHERE {' AND '.join(cond_parts)}
                ORDER BY il.score DESC LIMIT 30
            """, sparams).fetchall()

            def _wan(v):
                m = re.search(r'([\d.]+)\s*万', str(v or ''))
                return float(m.group(1)) if m else 0

            bmin = structured.get('budget_min_wan')
            bmax = structured.get('budget_max_wan')
            for r in srows:
                wan = _wan(r['budget'])
                if bmin is not None and wan < float(bmin):
                    continue
                if bmax is not None and bmax and wan >= float(bmax):
                    continue
                struct_results.append(dict(r))
            struct_results = struct_results[:10]
        except Exception as e:
            logger.warning(f'AI搜索结构化查询失败: {e}')

    # ---------- 3. 关键词检索（原有逻辑） ----------
    keywords = structured.get('keywords') or query.split()
    keywords.append(query)  # 原句也搜
    raw_where = []
    raw_params = []
    for kw in dict.fromkeys(keywords):  # 去重保序
        raw_where.append("(ri.title LIKE ? OR ri.content LIKE ? OR ri.snippet LIKE ?)")
        raw_params.extend([f'%{kw}%', f'%{kw}%', f'%{kw}%'])
    raw_clause = ' AND '.join(raw_where) if raw_where else '1=1'

    raw_results = db.execute(f"""
        SELECT ri.id, ri.title, ri.url, ri.publish_date,
               SUBSTR(COALESCE(ri.content, ri.snippet, ''), 1, 200) as preview,
               ls.name as source_name
        FROM raw_intelligence ri
        LEFT JOIN lead_sources ls ON ri.source_id = ls.id
        WHERE {raw_clause}
        ORDER BY ri.collected_at DESC LIMIT 5
    """, raw_params).fetchall()

    lead_results = db.execute("""
        SELECT il.id, il.title, il.buyer, il.budget, il.deadline, il.score,
               il.procurement_method, il.region, il.analysis_summary, il.status
        FROM intelligence_leads il
        WHERE (il.title LIKE ? OR il.buyer LIKE ? OR il.analysis_summary LIKE ?)
        ORDER BY il.score DESC LIMIT 5
    """, [f'%{query}%', f'%{query}%', f'%{query}%']).fetchall()

    crm_results = db.execute("""
        SELECT id, company, opportunity_name, intent_score, status, assigned_to, region
        FROM scraped_leads
        WHERE (company LIKE ? OR opportunity_name LIKE ?)
        ORDER BY intent_score DESC LIMIT 5
    """, [f'%{query}%', f'%{query}%']).fetchall()

    # ---------- 4. 向量搜索（知识库语义检索） ----------
    vector_results = []
    try:
        # 复用 vector_search 的生成逻辑：远端 embedding 失败时自动降级为哈希向量
        from vector_search import generate_embedding
        qvec = generate_embedding(query)
        if qvec:
            import math
            kvecs = db.execute("""
                SELECT kv.document_id, kv.embedding, kd.title
                FROM knowledge_vectors kv
                JOIN knowledge_documents kd ON kv.document_id = kd.id
                LIMIT 500
            """).fetchall()
            scored = []
            for kv in kvecs:
                try:
                    vec = json.loads(kv['embedding'])
                    if isinstance(vec, list) and len(vec) == len(qvec):
                        dot = sum(a * b for a, b in zip(qvec, vec))
                        na = math.sqrt(sum(a * a for a in qvec)) or 1
                        nb = math.sqrt(sum(b * b for b in vec)) or 1
                        scored.append((dot / (na * nb), kv['document_id'], kv['title']))
                except (json.JSONDecodeError, TypeError):
                    continue
            scored.sort(key=lambda x: -x[0])
            vector_results = [
                {'document_id': d, 'title': t, 'similarity': round(s, 3)}
                for s, d, t in scored[:3] if s > 0.3
            ]
    except Exception as e:
        logger.warning(f'AI搜索向量检索失败: {e}')

    # ---------- 5. 组织上下文 → LLM 回答 ----------
    context_parts = []
    if struct_results:
        context_parts.append("【结构化查询命中商机】")
        for r in struct_results:
            context_parts.append(
                f"- [{r['score'] or 0}分] {r['title']}\n"
                f"  采购:{r['buyer']} 预算:{r['budget'] or '-'} 地区:{r['region'] or '-'} "
                f"日期:{r['created_at'][:10] if r['created_at'] else '-'}")
    if lead_results:
        context_parts.append("\n【相关商机】")
        for r in lead_results:
            context_parts.append(
                f"- [{r['score']}分] {r['title']}\n  采购:{r['buyer']} 预算:{r['budget'] or ''} 截止:{r['deadline'] or ''}")
    if raw_results:
        context_parts.append("\n【相关情报】")
        for r in raw_results:
            context_parts.append(f"- {r['title']}\n  {r['preview']}")
    if crm_results:
        context_parts.append("\n【CRM线索】")
        for r in crm_results:
            context_parts.append(f"- {r['company']} | {r['opportunity_name']} | 分:{r['intent_score']}")
    if vector_results:
        context_parts.append("\n【知识库语义匹配】")
        for r in vector_results:
            context_parts.append(f"- {r['title']} (相似度{r['similarity']})")

    context = '\n'.join(context_parts) if context_parts else '未找到相关数据'

    answer = ''
    if USE_LLM:
        try:
            from qa_engine import call_llm
            prompt = f"""用户搜索：{query}

根据以下数据库检索结果，回答用户问题：

{context}

要求：
1. 用中文回答
2. 基于数据回答，禁止编造；某维度无数据时明确说"暂无记录"
3. 如果有商机，列出评分最高的
4. 简洁明了，不超过300字"""
            messages = [
                {'role': 'system', 'content': '你是AI销售情报助手，基于数据库检索结果回答用户的自然语言查询。'},
                {'role': 'user', 'content': prompt},
            ]
            answer = call_llm(messages, max_tokens=4000, timeout=120, enable_thinking=False) or ''
        except Exception as e:
            logger.error(f'AI搜索LLM调用失败: {e}')

    # 降级：无 LLM 时用模板回答
    if not answer:
        total = len(struct_results) + len(raw_results) + len(lead_results) + len(crm_results)
        if total == 0:
            answer = f'未找到与"{query}"相关的信息。'
        else:
            answer = (f'搜索到{len(struct_results)}条结构化商机、{len(raw_results)}条情报、'
                      f'{len(lead_results)}条商机、{len(crm_results)}条CRM线索。')
            top_src = struct_results or lead_results
            if top_src:
                top = top_src[0]
                answer += f' 最高评分商机：{top["title"]}（{top["score"] or 0}分），采购单位：{top["buyer"]}。'

    return jsonify({
        'code': 200,
        'data': {
            'answer': answer,
            'structured': structured,
            'structured_count': len(struct_results),
            'raw_count': len(raw_results),
            'lead_count': len(lead_results),
            'crm_count': len(crm_results),
            'vector_count': len(vector_results),
            'structured_results': struct_results,
            'raw_results': [dict(r) for r in raw_results],
            'lead_results': [dict(r) for r in lead_results],
            'crm_results': [dict(r) for r in crm_results],
            'vector_results': vector_results,
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
    tier = request.args.get('tier', '').strip()
    if tier:
        sql += " AND customer_tier=?"
        params.append(tier)
    ai_status = request.args.get('ai_status', '').strip()
    if ai_status:
        sql += " AND ai_status=?"
        params.append(ai_status)

    total = db.execute(f"SELECT COUNT(*) as c FROM ({sql})", params).fetchone()['c']
    sql += " ORDER BY CASE customer_tier WHEN 'strategic' THEN 0 WHEN 'key' THEN 1 WHEN 'normal' THEN 2 WHEN 'potential' THEN 3 ELSE 4 END, total_procurements DESC, max_score DESC LIMIT ? OFFSET ?"
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
    for field in ('procurement_methods', 'competitors', 'project_types', 'timeline',
                  'key_suppliers', 'potential_projects'):
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


@cockpit_bp.route('/customers/generate-ai', methods=['POST'])
@admin_required
def generate_ai_profiles():
    """批量生成AI客户画像（含LLM分析+客户分级+AI发现新客户）。

    Body: {"run_ai": true} 是否调用LLM生成AI分析
    """
    from customer_model import generate_all_profiles
    data = request.get_json(silent=True) or {}
    run_ai = data.get('run_ai', True)

    db = get_db()
    result = generate_all_profiles(db, run_ai=run_ai)
    db.commit()

    record_operation_log(
        request.current_user, 'generate_ai', 'customer_profiles',
        f'AI画像生成：总计{result["total"]} 更新{result["updated"]} '
        f'新建{result["created"]} AI分析{result["ai_count"]}'
    )
    return jsonify({
        'code': 200,
        'message': f'生成完成：总计{result["total"]} 更新{result["updated"]} 新建{result["created"]} AI分析{result["ai_count"]}',
        'data': result,
    })


@cockpit_bp.route('/customers/<int:cid>/generate-ai', methods=['POST'])
@admin_required
def generate_single_ai_profile(cid):
    """为单个客户生成AI画像。"""
    from customer_model import upsert_customer_profile
    db = get_db()
    row = db.execute("SELECT buyer FROM customer_profiles WHERE id=?", (cid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '客户不存在'})

    result = upsert_customer_profile(row['buyer'], db, run_ai=True)
    db.commit()
    record_operation_log(
        request.current_user, 'generate_ai', 'customer_profiles',
        f'AI画像生成：{row["buyer"][:30]}'
    )
    return jsonify({
        'code': 200,
        'message': f'AI画像已生成：{row["buyer"][:30]}',
        'data': result,
    })


@cockpit_bp.route('/customers/<int:cid>/confirm', methods=['POST'])
@admin_required
def confirm_ai_customer(cid):
    """确认AI发现的客户（从pending变为confirmed）。"""
    db = get_db()
    row = db.execute(
        "SELECT buyer, ai_status FROM customer_profiles WHERE id=?", (cid,)
    ).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '客户不存在'})

    db.execute(
        "UPDATE customer_profiles SET ai_status='confirmed' WHERE id=?", (cid,)
    )
    db.commit()
    record_operation_log(
        request.current_user, 'confirm', 'customer_profiles',
        f'确认AI发现客户：{row["buyer"][:30]}'
    )
    return jsonify({'code': 200, 'message': '已确认'})


@cockpit_bp.route('/customers/<int:cid>/tier', methods=['PUT'])
@admin_required
def update_customer_tier(cid):
    """更新客户分级。

    Body: {"tier": "strategic|key|normal|potential|ai_discovered"}
    """
    data = request.get_json(silent=True) or {}
    tier = (data.get('tier') or '').strip()
    valid_tiers = {'strategic', 'key', 'normal', 'potential', 'ai_discovered'}
    if tier not in valid_tiers:
        return jsonify({'code': 400, 'message': '无效的客户分级'})

    db = get_db()
    row = db.execute("SELECT buyer FROM customer_profiles WHERE id=?", (cid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '客户不存在'})

    db.execute(
        "UPDATE customer_profiles SET customer_tier=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (tier, cid)
    )
    db.commit()
    tier_labels = {'strategic': '战略客户', 'key': '重点客户', 'normal': '普通客户',
                   'potential': '潜在客户', 'ai_discovered': 'AI发现客户'}
    record_operation_log(
        request.current_user, 'update_tier', 'customer_profiles',
        f'客户分级更新：{row["buyer"][:30]} -> {tier_labels.get(tier, tier)}'
    )
    return jsonify({'code': 200, 'message': f'已更新为{tier_labels.get(tier, tier)}'})


@cockpit_bp.route('/competitors', methods=['GET'])
@require_permission('intel.competitor')
def competitor_list():
    """竞争对手列表（敏感经营数据，需 intel.competitor 权限）。"""
    db = get_db()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    risk_level = request.args.get('risk_level', '').strip()
    offset = (page - 1) * per_page

    sql = "SELECT * FROM competitor_profiles WHERE 1=1"
    params = []
    if search:
        sql += " AND (name LIKE ? OR aliases LIKE ? OR main_business LIKE ? OR industry LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%', f'%{search}%'])
    if risk_level:
        sql += " AND risk_level=?"
        params.append(risk_level)

    total = db.execute(f"SELECT COUNT(*) as c FROM ({sql})", params).fetchone()['c']
    sql += " ORDER BY CASE risk_level WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, appearance_count DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    rows = db.execute(sql, params).fetchall()

    return jsonify({
        'code': 200,
        'data': [dict(r) for r in rows],
        'total': total,
    })


@cockpit_bp.route('/competitors/<int:cid>', methods=['GET'])
@require_permission('intel.competitor')
def competitor_detail(cid):
    """竞争对手详情（敏感经营数据）。"""
    db = get_db()
    row = db.execute("SELECT * FROM competitor_profiles WHERE id=?", (cid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '竞争对手不存在'})
    data = dict(row)
    for field in ('aliases', 'customer_list', 'project_types', 'regions',
                  'advantage_areas', 'products', 'compete_fields', 'recent_news'):
        if data.get(field):
            try:
                data[field] = json.loads(data[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return jsonify({'code': 200, 'data': data})


@cockpit_bp.route('/competitors', methods=['POST'])
@admin_required
def competitor_create():
    """新增竞争对手。"""
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '企业名称必填'})

    db = get_db()
    existing = db.execute("SELECT id FROM competitor_profiles WHERE name=?", (name,)).fetchone()
    if existing:
        return jsonify({'code': 400, 'message': f'竞争对手「{name}」已存在'})

    aliases = data.get('aliases') or []
    products = data.get('products') or []
    compete_fields = data.get('compete_fields') or []
    cursor = db.execute("""
        INSERT INTO competitor_profiles (
            name, aliases, website, main_business, products, industry,
            compete_fields, risk_level, customer_list
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        name,
        json.dumps(aliases, ensure_ascii=False) if aliases else None,
        data.get('website') or None,
        data.get('main_business') or None,
        json.dumps(products, ensure_ascii=False) if products else None,
        data.get('industry') or None,
        json.dumps(compete_fields, ensure_ascii=False) if compete_fields else None,
        data.get('risk_level') or 'medium',
        json.dumps(data.get('customer_list') or [], ensure_ascii=False) or None,
    ))
    db.commit()
    record_operation_log(request.current_user, 'create', 'competitor', f'新增竞争对手:{name}')
    return jsonify({'code': 200, 'message': '已新增', 'data': {'id': cursor.lastrowid}})


@cockpit_bp.route('/competitors/<int:cid>', methods=['PUT'])
@admin_required
def competitor_update(cid):
    """编辑竞争对手信息。"""
    data = request.get_json(silent=True) or {}
    db = get_db()
    row = db.execute("SELECT id FROM competitor_profiles WHERE id=?", (cid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '竞争对手不存在'})

    fields = ['website', 'main_business', 'industry', 'risk_level']
    updates, params = [], []
    for f in fields:
        if f in data:
            updates.append(f"{f}=?")
            params.append(data[f])
    # JSON 数组字段
    for f in ('aliases', 'products', 'compete_fields', 'customer_list'):
        if f in data:
            val = data[f]
            updates.append(f"{f}=?")
            params.append(json.dumps(val, ensure_ascii=False) if isinstance(val, list) else val)
    if 'name' in data and (data['name'] or '').strip():
        updates.append("name=?")
        params.append(data['name'].strip())
    if updates:
        updates.append("updated_at=CURRENT_TIMESTAMP")
        params.append(cid)
        db.execute(f"UPDATE competitor_profiles SET {', '.join(updates)} WHERE id=?", params)
        db.commit()
        record_operation_log(request.current_user, 'update', 'competitor', f'编辑竞争对手#{cid}')
    return jsonify({'code': 200, 'message': '已保存'})


@cockpit_bp.route('/competitors/<int:cid>', methods=['DELETE'])
@admin_required
def competitor_delete(cid):
    """删除竞争对手。"""
    db = get_db()
    row = db.execute("SELECT name FROM competitor_profiles WHERE id=?", (cid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '竞争对手不存在'})
    db.execute("DELETE FROM competitor_profiles WHERE id=?", (cid,))
    db.commit()
    record_operation_log(request.current_user, 'delete', 'competitor', f'删除竞争对手:{row["name"][:30]}')
    return jsonify({'code': 200, 'message': '已删除'})


@cockpit_bp.route('/competitors/auto-update', methods=['POST'])
@admin_required
def competitors_auto_update():
    """系统自动从公开信息（情报库）更新竞争对手数据。"""
    from competitor_model import auto_update_competitors
    db = get_db()
    result = auto_update_competitors(db)
    record_operation_log(
        request.current_user, 'auto_update', 'competitor',
        f'自动更新竞争对手：新增{result["new"]} 更新{result["updated"]}'
    )
    return jsonify({
        'code': 200,
        'message': f'自动更新完成：新增{result["new"]}个，更新{result["updated"]}个',
        'data': result,
    })


@cockpit_bp.route('/competitors/analyze', methods=['POST'])
@require_permission('intel.competitor')
def competitor_analyze():
    """AI分析XX公司最近一年竞争情况。

    Body: {"name": "XX公司"}
    """
    from competitor_model import ai_analyze_competitor
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '请输入公司名称'})

    db = get_db()
    result = ai_analyze_competitor(name, db)
    record_operation_log(
        request.current_user, 'analyze', 'competitor', f'AI分析竞争对手:{name[:30]}'
    )
    return jsonify({'code': 200, 'data': result})


@cockpit_bp.route('/competitors/<int:cid>/analyze', methods=['POST'])
@require_permission('intel.competitor')
def competitor_analyze_by_id(cid):
    """AI分析指定竞争对手（按ID）。"""
    from competitor_model import ai_analyze_competitor
    db = get_db()
    row = db.execute("SELECT name FROM competitor_profiles WHERE id=?", (cid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '竞争对手不存在'})
    result = ai_analyze_competitor(row['name'], db)
    record_operation_log(
        request.current_user, 'analyze', 'competitor', f'AI分析竞争对手:{row["name"][:30]}'
    )
    return jsonify({'code': 200, 'data': result})


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
