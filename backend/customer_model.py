"""AI 客户画像模型。

从 intelligence_leads 聚合客户数据，调用 LLM 生成 AI 客户画像，
并自动分级客户。

客户分级：
  战略客户 (strategic) - 采购≥5次 或 总预算≥500万 或 有合同
  重点客户 (key)       - 采购≥3次 或 总预算≥100万
  普通客户 (normal)    - 有采购记录
  潜在客户 (potential)  - 默认（情报中发现但尚未采购）
  AI发现客户 (ai_discovered) - AI从情报中发现的新客户，默认待人工确认

AI画像内容：
  - 客户基本信息
  - 历史采购 + 采购金额 + 采购频率
  - 采购方向
  - 重点供应商
  - 常见竞争对手
  - 最近项目 + 潜在项目
  - AI判断
"""
import json
import logging
import sqlite3
from datetime import datetime, date

logger = logging.getLogger(__name__)

# 客户分级
CUSTOMER_TIERS = {
    'strategic': {'label': '战略客户', 'color': 'danger', 'order': 0},
    'key': {'label': '重点客户', 'color': 'warning', 'order': 1},
    'normal': {'label': '普通客户', 'color': 'primary', 'order': 2},
    'potential': {'label': '潜在客户', 'color': 'info', 'order': 3},
    'ai_discovered': {'label': 'AI发现', 'color': 'success', 'order': 4},
}


def _parse_budget(budget_str):
    """从预算字符串提取金额（万元）。"""
    import re
    if not budget_str:
        return 0
    m = re.search(r'([\d.]+)\s*万', str(budget_str))
    if m:
        return float(m.group(1))
    m = re.search(r'([\d.]+)\s*元', str(budget_str))
    if m:
        return float(m.group(1)) / 10000
    m = re.search(r'([\d.]+)', str(budget_str))
    if m:
        val = float(m.group(1))
        return val if val < 100000 else val / 10000
    return 0


def classify_tier(profile, has_contract=False):
    """根据规则对客户分级。

    Args:
        profile: dict 含 total_procurements, total_budget, max_score
        has_contract: 是否有合同记录

    Returns:
        str: tier key (strategic/key/normal/potential)
    """
    total_proc = profile.get('total_procurements', 0) or 0
    total_budget = profile.get('total_budget', 0) or 0
    max_score = profile.get('max_score', 0) or 0

    # 战略客户
    if total_proc >= 5 or total_budget >= 500 or has_contract:
        return 'strategic'
    # 重点客户
    if total_proc >= 3 or total_budget >= 100 or max_score >= 80:
        return 'key'
    # 普通客户
    if total_proc >= 1:
        return 'normal'
    # 潜在客户
    return 'potential'


def calculate_frequency(timeline, total_proc):
    """计算采购频率描述。"""
    if not timeline or total_proc == 0:
        return '暂无记录'
    try:
        dates = [t.get('date', '') for t in timeline if t.get('date')]
        if len(dates) < 2:
            return '偶发（单次采购）'
        dates.sort()
        first = datetime.strptime(dates[0][:10], '%Y-%m-%d')
        last = datetime.strptime(dates[-1][:10], '%Y-%m-%d')
        months = (last - first).days / 30
        if months <= 0:
            return '集中采购'
        freq = total_proc / months
        if freq >= 2:
            return f'高频（{freq:.1f}次/月）'
        elif freq >= 0.5:
            return f'中频（{freq:.1f}次/月）'
        else:
            return f'低频（{freq:.1f}次/月）'
    except Exception:
        return '偶发'


def aggregate_buyer_data(buyer, db):
    """聚合单个采购单位的全部数据。"""
    rows = db.execute("""
        SELECT il.id, il.title, il.budget, il.procurement_method, il.region,
               il.score, il.deadline, il.created_at, il.competitors,
               il.analysis_summary, il.lifecycle_stage, il.status,
               il.project_type, il.keywords_matched
        FROM intelligence_leads il
        WHERE il.buyer = ? AND il.status NOT IN ('rejected', 'merged')
        ORDER BY il.created_at DESC
    """, (buyer,)).fetchall()

    if not rows:
        return None

    # 聚合
    total_budget = 0
    budgets = []
    methods = set()
    competitors = set()
    project_types = set()
    keywords = set()
    scores = []
    max_score = 0
    timeline = []

    for r in rows:
        budget = _parse_budget(r['budget'])
        if budget > 0:
            total_budget += budget
            budgets.append(budget)
        if r['procurement_method']:
            methods.add(r['procurement_method'])
        if r['project_type']:
            project_types.add(r['project_type'])
        if r['score']:
            scores.append(r['score'])
            max_score = max(max_score, r['score'])
        if r['competitors']:
            try:
                comps = json.loads(r['competitors'])
                if isinstance(comps, list):
                    competitors.update(c for c in comps if c)
            except (json.JSONDecodeError, TypeError):
                pass
        if r['keywords_matched']:
            try:
                kws = r['keywords_matched']
                if kws.startswith('['):
                    keywords.update(json.loads(kws))
                else:
                    keywords.update(k.strip() for k in kws.split(',') if k.strip())
            except (json.JSONDecodeError, TypeError):
                pass
        timeline.append({
            'title': r['title'][:50] if r['title'] else '',
            'date': r['created_at'][:10] if r['created_at'] else '',
            'deadline': r['deadline'] or '',
            'budget': r['budget'] or '',
            'score': r['score'] or 0,
            'stage': r['lifecycle_stage'] or '',
            'status': r['status'] or '',
        })

    # 检查CRM合同
    crm_customer = db.execute(
        "SELECT id FROM customers WHERE company=?", (buyer,)
    ).fetchone()
    has_contract = False
    if crm_customer:
        contract = db.execute(
            "SELECT id FROM contracts WHERE cust_id=?", (crm_customer['id'],)
        ).fetchone()
        has_contract = contract is not None

    # 重点供应商：从CRM合同中提取
    key_suppliers = []
    if crm_customer:
        contracts = db.execute("""
            SELECT ct.contract_name, ct.total_amt, ct.sign_date
            FROM contracts ct WHERE ct.cust_id=?
            ORDER BY ct.sign_date DESC LIMIT 5
        """, (crm_customer['id'],)).fetchall()
        for c in contracts:
            key_suppliers.append({
                'project': c['contract_name'] or '',
                'amount': c['total_amt'] or 0,
                'date': c['sign_date'][:10] if c['sign_date'] else '',
            })

    avg_budget = sum(budgets) / len(budgets) if budgets else 0
    avg_score = sum(scores) / len(scores) if scores else 0
    frequency = calculate_frequency(timeline, len(rows))

    profile = {
        'buyer': buyer,
        'region': rows[0]['region'] or '',
        'industry': ', '.join(list(project_types)[:3]) if project_types else '',
        'total_procurements': len(rows),
        'total_budget': round(total_budget, 2),
        'avg_budget': round(avg_budget, 2),
        'procurement_methods': json.dumps(list(methods), ensure_ascii=False),
        'competitors': json.dumps(list(competitors), ensure_ascii=False),
        'project_types': json.dumps(list(project_types), ensure_ascii=False),
        'keywords': json.dumps(list(keywords), ensure_ascii=False),
        'latest_date': max((r['created_at'][:10] for r in rows if r['created_at']), default=''),
        'avg_score': round(avg_score, 1),
        'max_score': max_score,
        'timeline': json.dumps(timeline[:15], ensure_ascii=False),
        'procurement_frequency': frequency,
        'key_suppliers': json.dumps(key_suppliers, ensure_ascii=False) if key_suppliers else '',
        'has_contract': has_contract,
        'crm_customer_id': crm_customer['id'] if crm_customer else None,
        'recent_projects': [t for t in timeline[:5]],
        'all_competitors': list(competitors),
    }
    return profile


def generate_ai_profile(buyer, db):
    """为单个客户生成AI画像（LLM分析）。

    Returns:
        dict: {
            'ai_analysis': str, 'ai_tier_suggestion': str,
            'potential_projects': str, 'procurement_direction': str,
        } or None if LLM unavailable
    """
    try:
        from config import USE_LLM
        if not USE_LLM:
            return None
        from qa_engine import call_llm
    except Exception as e:
        logger.warning(f'AI画像模块导入失败: {e}')
        return None

    profile = aggregate_buyer_data(buyer, db)
    if not profile:
        return None

    # 构造LLM输入
    summary = {
        '客户名称': buyer,
        '地区': profile['region'],
        '行业/项目类型': profile['industry'],
        '历史采购次数': profile['total_procurements'],
        '历史采购总金额(万)': profile['total_budget'],
        '平均预算(万)': profile['avg_budget'],
        '采购频率': profile['procurement_frequency'],
        '采购方式': json.loads(profile['procurement_methods']) if profile['procurement_methods'] else [],
        '常见竞争对手': profile['all_competitors'][:10],
        '关键词标签': json.loads(profile['keywords']) if profile['keywords'] else [],
        '平均评分': profile['avg_score'],
        '最高评分': profile['max_score'],
        '有合同记录': profile['has_contract'],
        '最近项目': profile['recent_projects'][:5],
    }

    prompt = f"""基于以下客户数据生成AI客户画像分析。

客户数据：
{json.dumps(summary, ensure_ascii=False, indent=2)}

请生成：
1. AI判断：客户价值评估、采购特点、合作潜力（200字内）
2. 采购方向：客户主要采购什么类型的产品/服务
3. 潜在项目：基于历史采购趋势，预测客户可能后续采购的项目
4. 建议分级：strategic(战略)/key(重点)/normal(普通)/potential(潜在)

只返回JSON：
{{
  "ai_analysis": "客户价值评估和分析",
  "procurement_direction": "采购方向描述",
  "potential_projects": ["潜在项目1", "潜在项目2"],
  "ai_tier_suggestion": "strategic|key|normal|potential"
}}"""

    try:
        messages = [
            {'role': 'system', 'content': '你是客户分析专家，基于采购数据生成客户画像。只返回JSON。'},
            {'role': 'user', 'content': prompt},
        ]
        content = call_llm(messages, max_tokens=2000, timeout=60, enable_thinking=False)
        if not content:
            return None
        parsed = _extract_json(content)
        if not isinstance(parsed, dict):
            return None
        return {
            'ai_analysis': str(parsed.get('ai_analysis', '')),
            'procurement_direction': str(parsed.get('procurement_direction', '')),
            'potential_projects': json.dumps(parsed.get('potential_projects', []),
                                             ensure_ascii=False) if parsed.get('potential_projects') else '',
            'ai_tier_suggestion': str(parsed.get('ai_tier_suggestion', '')),
        }
    except Exception as e:
        logger.warning(f'AI画像生成失败({buyer}): {e}')
        return None


def _extract_json(text):
    """从 LLM 输出中提取 JSON。"""
    import re
    if not text:
        return None
    m = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    start = text.find('{')
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def upsert_customer_profile(buyer, db, run_ai=False):
    """创建或更新客户画像。

    Args:
        buyer: 采购单位名称
        db: 数据库连接
        run_ai: 是否调用LLM生成AI画像

    Returns:
        dict: {'profile_id': int, 'action': 'created'|'updated'|'no_data', 'ai_run': bool}
    """
    profile = aggregate_buyer_data(buyer, db)
    if not profile:
        return {'profile_id': None, 'action': 'no_data', 'ai_run': False}

    # 规则分级
    tier = classify_tier(profile, profile['has_contract'])

    # AI画像
    ai_result = None
    if run_ai:
        ai_result = generate_ai_profile(buyer, db)

    existing = db.execute(
        "SELECT id, ai_generated FROM customer_profiles WHERE buyer=?", (buyer,)
    ).fetchone()

    # AI建议分级优先
    final_tier = tier
    ai_analysis = ''
    ai_tier_suggestion = ''
    potential_projects = ''
    procurement_frequency = profile['procurement_frequency']

    if ai_result:
        ai_analysis = ai_result.get('ai_analysis', '')
        ai_tier_suggestion = ai_result.get('ai_tier_suggestion', '')
        potential_projects = ai_result.get('potential_projects', '')
        # AI建议分级优先（如果有效）
        if ai_tier_suggestion in CUSTOMER_TIERS:
            final_tier = ai_tier_suggestion

    if existing:
        # 更新（保留 ai_generated 标记）
        ai_generated = existing['ai_generated'] or 0
        db.execute("""
            UPDATE customer_profiles SET
                industry=?, region=?, total_procurements=?, total_budget=?,
                avg_budget=?, procurement_methods=?, competitors=?, project_types=?,
                latest_date=?, avg_score=?, max_score=?, timeline=?,
                customer_tier=?, procurement_frequency=?, key_suppliers=?,
                potential_projects=?, ai_analysis=?, ai_tier_suggestion=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE buyer=?
        """, (
            profile['industry'], profile['region'], profile['total_procurements'],
            profile['total_budget'], profile['avg_budget'],
            profile['procurement_methods'], profile['competitors'],
            profile['project_types'], profile['latest_date'],
            profile['avg_score'], profile['max_score'], profile['timeline'],
            final_tier, procurement_frequency, profile['key_suppliers'],
            potential_projects, ai_analysis, ai_tier_suggestion,
            buyer,
        ))
        profile_id = existing['id']
        action = 'updated'
    else:
        # 新建
        cursor = db.execute("""
            INSERT INTO customer_profiles (
                buyer, industry, region, total_procurements, total_budget,
                avg_budget, procurement_methods, competitors, project_types,
                latest_date, avg_score, max_score, timeline,
                customer_tier, procurement_frequency, key_suppliers,
                potential_projects, ai_analysis, ai_tier_suggestion,
                ai_generated, ai_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            buyer, profile['industry'], profile['region'], profile['total_procurements'],
            profile['total_budget'], profile['avg_budget'],
            profile['procurement_methods'], profile['competitors'],
            profile['project_types'], profile['latest_date'],
            profile['avg_score'], profile['max_score'], profile['timeline'],
            final_tier, procurement_frequency, profile['key_suppliers'],
            potential_projects, ai_analysis, ai_tier_suggestion,
            0, 'confirmed',
        ))
        profile_id = cursor.lastrowid
        action = 'created'

    return {'profile_id': profile_id, 'action': action, 'ai_run': ai_result is not None}


def discover_new_customers(db):
    """从 intelligence_leads 中发现新客户（buyer 不在 customer_profiles 中）。

    AI发现的客户默认：待人工确认（ai_status='pending'）。

    Returns:
        list[dict]: 新发现的客户列表
    """
    # 找到 intelligence_leads 中有 buyer 但不在 customer_profiles 中的
    new_buyers = db.execute("""
        SELECT DISTINCT il.buyer
        FROM intelligence_leads il
        LEFT JOIN customer_profiles cp ON il.buyer = cp.buyer
        WHERE il.buyer IS NOT NULL AND il.buyer != '' AND cp.id IS NULL
    """).fetchall()

    discovered = []
    for r in new_buyers:
        buyer = r['buyer'].strip()
        if not buyer:
            continue
        # 聚合基础数据
        profile = aggregate_buyer_data(buyer, db)
        if not profile:
            continue
        tier = classify_tier(profile, profile['has_contract'])
        cursor = db.execute("""
            INSERT INTO customer_profiles (
                buyer, industry, region, total_procurements, total_budget,
                avg_budget, procurement_methods, competitors, project_types,
                latest_date, avg_score, max_score, timeline,
                customer_tier, procurement_frequency, key_suppliers,
                ai_generated, ai_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            buyer, profile['industry'], profile['region'], profile['total_procurements'],
            profile['total_budget'], profile['avg_budget'],
            profile['procurement_methods'], profile['competitors'],
            profile['project_types'], profile['latest_date'],
            profile['avg_score'], profile['max_score'], profile['timeline'],
            tier, profile['procurement_frequency'], profile['key_suppliers'],
            1, 'pending',
        ))
        discovered.append({
            'id': cursor.lastrowid,
            'buyer': buyer,
            'tier': tier,
            'total_procurements': profile['total_procurements'],
            'total_budget': profile['total_budget'],
        })

    return discovered


def generate_all_profiles(db, run_ai=False):
    """批量生成所有客户画像。

    Returns:
        dict: {'total': int, 'updated': int, 'created': int, 'ai_count': int}
    """
    # 先发现新客户
    new_customers = discover_new_customers(db)

    # 更新已有客户
    existing_buyers = db.execute("SELECT buyer FROM customer_profiles").fetchall()
    updated = 0
    created = len(new_customers)
    ai_count = 0

    for r in existing_buyers:
        result = upsert_customer_profile(r['buyer'], db, run_ai=run_ai)
        if result['action'] == 'updated':
            updated += 1
        if result['ai_run']:
            ai_count += 1

    db.commit()
    return {
        'total': len(existing_buyers) + created,
        'updated': updated,
        'created': created,
        'ai_count': ai_count,
    }
