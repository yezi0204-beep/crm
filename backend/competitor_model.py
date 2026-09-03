"""竞争对手分析模型。

功能：
  1. 自动更新：从情报库（intelligence_leads.competitors）自动更新竞争对手数据
     - 出现次数、客户列表、项目类型、地区分布、中标项目/金额统计
  2. AI分析："分析XX公司最近一年竞争情况"
     - 自动统计：中标项目、中标金额、主要客户、主要行业、主要区域、产品方向、增长趋势、竞争领域
     - LLM生成：竞争对手优势、竞争对手弱点、我方竞争策略
  3. 风险等级评估：基于出现频率、中标情况自动评估
"""
import json
import logging
from datetime import datetime, date, timedelta
from collections import Counter

logger = logging.getLogger(__name__)


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


# ============================================================
# 自动更新：从情报库更新竞争对手数据
# ============================================================
def auto_update_competitors(db):
    """从 intelligence_leads 的 competitors 字段自动更新竞争对手数据库。

    对每个竞争对手自动统计：
    - 出现次数、客户列表、项目类型、地区分布
    - 涉及项目总预算（作为中标金额参考）
    - 最近动态（最近出现的商机标题）
    - 风险等级（基于出现频率和涉及金额）

    Returns:
        dict: {'total': 更新总数, 'new': 新增数, 'updated': 更新数}
    """
    rows = db.execute("""
        SELECT buyer, competitors, project_type, region, procurement_method,
               score, budget, title, lifecycle_stage, created_at
        FROM intelligence_leads
        WHERE competitors IS NOT NULL AND competitors != '[]'
          AND status NOT IN ('rejected', 'merged')
    """).fetchall()

    profiles = {}
    for r in rows:
        try:
            comp_list = json.loads(r['competitors'])
            if not isinstance(comp_list, list):
                continue
        except (json.JSONDecodeError, TypeError):
            continue

        budget = _parse_budget(r['budget'])
        date_str = r['created_at'][:10] if r['created_at'] else ''

        for comp in comp_list:
            comp = (comp or '').strip()
            if not comp or len(comp) < 2:
                continue
            if comp not in profiles:
                profiles[comp] = {
                    'appearance_count': 0,
                    'customers': set(),
                    'project_types': set(),
                    'regions': set(),
                    'methods': set(),
                    'total_budget': 0.0,
                    'project_titles': [],
                    'first_seen': date_str,
                    'last_seen': date_str,
                    'monthly_counts': Counter(),
                }
            p = profiles[comp]
            p['appearance_count'] += 1
            if r['buyer']:
                p['customers'].add(r['buyer'])
            if r['project_type']:
                p['project_types'].add(r['project_type'])
            if r['region']:
                p['regions'].add(r['region'])
            if r['procurement_method']:
                p['methods'].add(r['procurement_method'])
            if budget > 0:
                p['total_budget'] += budget
            if r['title']:
                p['project_titles'].append({
                    'title': r['title'][:60],
                    'buyer': r['buyer'] or '',
                    'budget': r['budget'] or '',
                    'date': date_str,
                })
            if date_str:
                if not p['first_seen'] or date_str < p['first_seen']:
                    p['first_seen'] = date_str
                if not p['last_seen'] or date_str > p['last_seen']:
                    p['last_seen'] = date_str
                p['monthly_counts'][date_str[:7]] += 1

    new_count = 0
    updated_count = 0
    for comp, p in profiles.items():
        # 风险等级评估：近3个月出现≥5次或总金额≥500万为high，≥2次为medium
        recent_months = 0
        today = date.today()
        for i in range(3):
            m = (today - timedelta(days=30 * i)).strftime('%Y-%m')
            recent_months += p['monthly_counts'].get(m, 0)
        total_wan = round(p['total_budget'], 2)
        if recent_months >= 5 or total_wan >= 500:
            risk = 'high'
        elif recent_months >= 2 or total_wan >= 100:
            risk = 'medium'
        else:
            risk = 'low'

        # 最近动态：最近5条项目
        recent_news = json.dumps(p['project_titles'][:5], ensure_ascii=False)

        existing = db.execute(
            "SELECT id FROM competitor_profiles WHERE name=?", (comp,)
        ).fetchone()

        if existing:
            db.execute("""
                UPDATE competitor_profiles SET
                    appearance_count=?, customer_list=?, project_types=?,
                    regions=?, advantage_areas=?, win_amount=?, risk_level=?,
                    recent_news=?, first_seen=?, last_seen=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE name=?
            """, (
                p['appearance_count'],
                json.dumps(list(p['customers']), ensure_ascii=False),
                json.dumps(list(p['project_types']), ensure_ascii=False),
                json.dumps(list(p['regions']), ensure_ascii=False),
                json.dumps(list(p['project_types'])[:3], ensure_ascii=False),
                total_wan, risk, recent_news,
                p['first_seen'], p['last_seen'], comp,
            ))
            updated_count += 1
        else:
            db.execute("""
                INSERT INTO competitor_profiles (
                    name, appearance_count, customer_list, project_types,
                    regions, advantage_areas, win_amount, risk_level,
                    recent_news, first_seen, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                comp, p['appearance_count'],
                json.dumps(list(p['customers']), ensure_ascii=False),
                json.dumps(list(p['project_types']), ensure_ascii=False),
                json.dumps(list(p['regions']), ensure_ascii=False),
                json.dumps(list(p['project_types'])[:3], ensure_ascii=False),
                total_wan, risk, recent_news,
                p['first_seen'], p['last_seen'],
            ))
            new_count += 1

    db.commit()
    return {'total': len(profiles), 'new': new_count, 'updated': updated_count}


# ============================================================
# 单公司最近一年统计
# ============================================================
def get_company_stats(name, db, days=365):
    """统计XX公司最近一年（默认365天）的竞争情况。

    Returns:
        dict: {
            'win_projects': 中标项目列表,
            'win_count': 中标数量,
            'win_amount': 中标总金额(万),
            'top_customers': 主要客户,
            'top_industries': 主要行业,
            'top_regions': 主要区域,
            'product_direction': 产品方向,
            'growth_trend': 增长趋势,
            'compete_fields': 竞争领域,
            'monthly_trend': 月度趋势,
        }
    """
    start_date = (date.today() - timedelta(days=days)).isoformat()

    # 别名匹配
    aliases = [name]
    row = db.execute("SELECT aliases FROM competitor_profiles WHERE name=?", (name,)).fetchone()
    if row and row['aliases']:
        try:
            alias_list = json.loads(row['aliases'])
            if isinstance(alias_list, list):
                aliases.extend(alias_list)
        except (json.JSONDecodeError, TypeError):
            pass

    # 收集该公司出现的商机
    projects = []
    for alias in aliases:
        rows = db.execute("""
            SELECT title, buyer, budget, region, project_type, procurement_method,
                   lifecycle_stage, score, created_at, analysis_summary, competitors
            FROM intelligence_leads
            WHERE competitors LIKE ? AND status NOT IN ('rejected', 'merged')
              AND created_at >= ?
        """, (f'%{alias}%', start_date)).fetchall()
        for r in rows:
            try:
                comps = json.loads(r['competitors']) if r['competitors'] else []
                if alias in comps:
                    projects.append(dict(r))
            except (json.JSONDecodeError, TypeError):
                continue

    # 去重（同标题同buyer）
    seen = set()
    unique_projects = []
    for p in projects:
        key = (p['title'], p['buyer'])
        if key not in seen:
            seen.add(key)
            unique_projects.append(p)

    # 统计
    win_count = len(unique_projects)
    win_amount = sum(_parse_budget(p['budget']) for p in unique_projects)
    customer_counter = Counter(p['buyer'] for p in unique_projects if p['buyer'])
    industry_counter = Counter(p['project_type'] for p in unique_projects if p['project_type'])
    region_counter = Counter(p['region'] for p in unique_projects if p['region'])
    method_counter = Counter(p['procurement_method'] for p in unique_projects if p['procurement_method'])

    # 中标项目：lifecycle_stage 为 won_bid/contract_announcement/deal_closed 的
    win_stages = {'won_bid', 'contract_announcement', 'deal_closed'}
    won_projects = [p for p in unique_projects if p['lifecycle_stage'] in win_stages]

    # 月度趋势（近12个月）
    monthly = Counter()
    for p in unique_projects:
        if p['created_at']:
            monthly[p['created_at'][:7]] += 1
    trend_months = []
    today = date.today()
    for i in range(11, -1, -1):
        m = (today - timedelta(days=30 * i)).strftime('%Y-%m')
        trend_months.append({'month': m, 'count': monthly.get(m, 0)})

    # 增长趋势判断：近3月 vs 之前3月
    recent_3 = sum(t['count'] for t in trend_months[-3:])
    prev_3 = sum(t['count'] for t in trend_months[-6:-3])
    if recent_3 > prev_3 * 1.2:
        growth = '上升'
    elif recent_3 < prev_3 * 0.8:
        growth = '下降'
    else:
        growth = '平稳'

    return {
        'total_projects': win_count,
        'won_projects': [
            {'title': p['title'][:50], 'buyer': p['buyer'], 'budget': p['budget'],
             'date': p['created_at'][:10] if p['created_at'] else ''}
            for p in won_projects[:10]
        ],
        'win_count': len(won_projects),
        'win_amount': round(win_amount, 2),
        'top_customers': customer_counter.most_common(5),
        'top_industries': industry_counter.most_common(5),
        'top_regions': region_counter.most_common(5),
        'top_methods': method_counter.most_common(3),
        'product_direction': [k for k, _ in industry_counter.most_common(5)],
        'compete_fields': [k for k, _ in industry_counter.most_common(3)],
        'growth_trend': growth,
        'monthly_trend': trend_months,
        'recent_projects': [
            {'title': p['title'][:50], 'buyer': p['buyer'], 'budget': p['budget'],
             'date': p['created_at'][:10] if p['created_at'] else '', 'score': p['score']}
            for p in unique_projects[:10]
        ],
    }


# ============================================================
# AI 分析：优势/弱点/我方竞争策略
# ============================================================
def ai_analyze_competitor(name, db):
    """AI分析XX公司最近一年竞争情况，生成优势/弱点/我方策略。

    Returns:
        dict: {'stats': 统计, 'strengths': str, 'weaknesses': str,
               'our_strategy': str, 'risk_level': str}
              LLM 不可用时 stats 仍返回，AI字段为空
    """
    stats = get_company_stats(name, db)

    # 先更新基本信息
    profile = db.execute("SELECT * FROM competitor_profiles WHERE name=?", (name,)).fetchone()

    strengths = profile['strengths'] if profile else ''
    weaknesses = profile['weaknesses'] if profile else ''
    our_strategy = profile['our_strategy'] if profile else ''
    risk_level = profile['risk_level'] if profile else 'medium'

    try:
        from config import USE_LLM
        if USE_LLM:
            from qa_engine import call_llm

            summary = {
                '公司名称': name,
                '最近一年出现次数': stats['total_projects'],
                '中标项目数': stats['win_count'],
                '涉及总金额(万)': stats['win_amount'],
                '主要客户': [f'{c}({n}次)' for c, n in stats['top_customers']],
                '主要行业': [f'{i}({n}次)' for i, n in stats['top_industries']],
                '主要区域': [f'{r}({n}次)' for r, n in stats['top_regions']],
                '产品方向': stats['product_direction'],
                '竞争领域': stats['compete_fields'],
                '增长趋势': stats['growth_trend'],
                '月度活跃': {t['month']: t['count'] for t in stats['monthly_trend'][-6:]},
            }

            prompt = f"""基于以下竞争对手数据，分析该公司最近一年竞争情况。

数据：
{json.dumps(summary, ensure_ascii=False, indent=2)}

请生成：
1. 竞争对手优势：技术/价格/客户关系/地域等优势（150字内）
2. 竞争对手弱点：可能的短板和突破口（150字内）
3. 我方竞争策略：针对该公司我方应采取的差异化竞争策略（200字内）
4. 风险等级：high（活跃且金额大）/ medium / low

只返回JSON：
{{"strengths": "...", "weaknesses": "...", "our_strategy": "...", "risk_level": "high|medium|low"}}"""

            messages = [
                {'role': 'system', 'content': '你是竞争情报分析专家，基于数据生成竞争对手分析和策略建议。只返回JSON。'},
                {'role': 'user', 'content': prompt},
            ]
            content = call_llm(messages, max_tokens=1500, timeout=60, enable_thinking=False)
            if content:
                parsed = _extract_json(content)
                if isinstance(parsed, dict):
                    strengths = str(parsed.get('strengths', '')) or strengths
                    weaknesses = str(parsed.get('weaknesses', '')) or weaknesses
                    our_strategy = str(parsed.get('our_strategy', '')) or our_strategy
                    risk = parsed.get('risk_level', '')
                    if risk in ('high', 'medium', 'low'):
                        risk_level = risk
    except Exception as e:
        logger.warning(f'AI竞争对手分析失败({name}): {e}')

    # 写入数据库
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if profile:
        db.execute("""
            UPDATE competitor_profiles SET
                strengths=?, weaknesses=?, our_strategy=?, risk_level=?,
                win_amount=?, ai_analyzed_at=?, updated_at=CURRENT_TIMESTAMP
            WHERE name=?
        """, (strengths, weaknesses, our_strategy, risk_level,
              stats['win_amount'], now, name))
    else:
        db.execute("""
            INSERT INTO competitor_profiles (
                name, strengths, weaknesses, our_strategy, risk_level,
                win_amount, ai_analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, strengths, weaknesses, our_strategy, risk_level,
              stats['win_amount'], now))
    db.commit()

    return {
        'stats': stats,
        'strengths': strengths,
        'weaknesses': weaknesses,
        'our_strategy': our_strategy,
        'risk_level': risk_level,
    }
