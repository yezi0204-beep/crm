"""多 Agent 协同商机分析模块。

将原单 Prompt 分析拆分为 7 个专职 Agent，各司其职、顺序协同：
  Agent 1 信息分类：商机/采购意向/招标/中标/新闻/客户动态/竞争对手动态/普通信息
  Agent 2 业务分类：遥感/农业/林业/自然资源/水利/生态环境/AI/软件/大数据/无人机/军品
  Agent 3 实体识别：项目/客户/企业/竞争对手/供应商/地区/金额/时间
  Agent 4 项目分析：采购内容/客户需求/预算/采购阶段/项目时间
  Agent 5 能力匹配：依据 CRM 产品库判断我们能不能做
  Agent 6 商机评分：业务匹配度/客户价值/预算金额/项目阶段/时间紧迫度/区域匹配度/竞争情况
  Agent 7 销售建议：为什么跟/何时跟/找谁/怎么切入/准备什么/可能竞争对手

每个 Agent 独立调用 LLM（max_tokens=2000, timeout=60, enable_thinking=False），
失败时降级为规则分析。结果聚合后写入 intelligence_agent_results 表。
"""
import json
import re
import logging
import sqlite3

logger = logging.getLogger(__name__)

# 业务分类标准列表（Agent 2 参考）
BUSINESS_DOMAINS = [
    '遥感', '农业', '林业', '自然资源', '水利',
    '生态环境', 'AI', '软件', '大数据', '无人机', '军品'
]

# 信息分类标准列表（Agent 1 参考）
INFO_CATEGORIES = [
    '商机', '采购意向', '招标', '中标',
    '新闻', '客户动态', '竞争对手动态', '普通信息'
]


def _extract_json(text):
    """从 LLM 输出文本中稳健提取 JSON 对象。"""
    if not text:
        return None
    # 去除 ```json ... ``` 包裹
    m = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    # 尝试直接解析
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    # 逐字符匹配最外层 {...}
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


def _call_llm_json(prompt, system_msg='你是一个严谨的数据分析助手，只返回JSON。', max_tokens=18000):
    """调用 LLM 并解析为 JSON，失败返回 None。"""
    from config import USE_LLM
    if not USE_LLM:
        return None
    try:
        from qa_engine import call_llm
        content = call_llm(
            [{'role': 'system', 'content': system_msg},
             {'role': 'user', 'content': prompt}],
            max_tokens=max_tokens, timeout=360, enable_thinking=False
        )
        if content:
            return _extract_json(content)
    except Exception as e:
        logger.warning(f'LLM 调用失败: {e}')
    return None


# ============================================================
# Agent 1：信息分类
# ============================================================
def agent1_classify(title, content):
    """判断信息类别：商机/采购意向/招标/中标/新闻/客户动态/竞争对手动态/普通信息。"""
    text = (title or '') + '\n' + (content or '')[:1500]
    prompt = f"""判断以下信息属于哪一类别，只能选一个。

类别选项：商机、采购意向、招标、中标、新闻、客户动态、竞争对手动态、普通信息

分类定义：
- 商机：明确的采购/招标项目，有预算和截止时间，我方可能参与
- 采购意向：仅表达采购计划或意向，尚未正式招标
- 招标：正式发布的招标公告/采购公告
- 中标：中标结果公告
- 新闻：行业资讯、政策动态、技术趋势等非项目信息
- 客户动态：我方现有/潜在客户的组织变动、项目进展等
- 竞争对手动态：竞争对手的产品发布、中标、合作等信息
- 普通信息：无法归入以上类别的信息

信息标题：{title}
信息正文（截取）：
{text[:1200]}

只返回 JSON：
{{"category": "类别名称", "confidence": 0到1的置信度, "reason": "一句话理由"}}"""
    result = _call_llm_json(prompt, '你是信息分类专家，只返回JSON。')
    if result and result.get('category') in INFO_CATEGORIES:
        return result
    # 规则降级
    return _rule_classify(title, content)


def _rule_classify(title, content):
    """规则降级分类。"""
    text = (title or '') + (content or '')
    rules = [
        ('中标', '中标'),
        ('招标公告', '招标'), ('采购公告', '招标'), ('竞争性', '招标'),
        ('意向', '采购意向'), ('计划', '采购意向'),
    ]
    for kw, cat in rules:
        if kw in text:
            return {'category': cat, 'confidence': 0.6, 'reason': f'规则匹配关键词：{kw}'}
    return {'category': '普通信息', 'confidence': 0.5, 'reason': '未匹配明确分类规则'}


# ============================================================
# Agent 2：业务分类
# ============================================================
def agent2_business(title, content, db=None):
    """判断业务领域：遥感/农业/林业/自然资源/水利/生态环境/AI/软件/大数据/无人机/军品。"""
    text = (title or '') + '\n' + (content or '')[:1500]

    # 优先使用业务标签库（三级标签）
    tag_hints = ''
    if db is not None:
        try:
            rows = db.execute(
                "SELECT name, synonyms FROM business_tags WHERE is_active=1 ORDER BY level, sort_order"
            ).fetchall()
            if rows:
                tag_hints = '业务标签库：' + ', '.join(
                    f"{r['name']}({r['synonyms']})" if r['synonyms'] else r['name'] for r in rows[:40]
                )
        except Exception:
            pass

    prompt = f"""判断以下信息属于哪些业务领域，可多选。

业务领域选项：遥感、农业、林业、自然资源、水利、生态环境、AI、软件、大数据、无人机、军品

{tag_hints}

信息标题：{title}
信息正文（截取）：
{text[:1200]}

只返回 JSON：
{{"business_tags": ["领域1", "领域2"], "primary_business": "最主要领域", "confidence": 0到1, "reason": "一句话理由"}}"""
    result = _call_llm_json(prompt, '你是业务领域分类专家，只返回JSON。')
    if result and isinstance(result.get('business_tags'), list):
        valid = [b for b in result['business_tags'] if b in BUSINESS_DOMAINS]
        if valid:
            result['business_tags'] = valid
            return result
    return _rule_business(title, content)


def _rule_business(title, content):
    """规则降级业务分类。"""
    text = (title or '') + (content or '')
    mapping = {
        '遥感': ['遥感', '卫星', 'SAR', '光学', '雷达影像'],
        '农业': ['农业', '种植', '农作物', '智慧农业'],
        '林业': ['林业', '森林', '林木'],
        '自然资源': ['自然资源', '国土', '矿产', '土地'],
        '水利': ['水利', '水文', '水库', '河流'],
        '生态环境': ['生态', '环境', '环保', '监测站'],
        'AI': ['人工智能', 'AI', '大模型', '机器学习', '深度学习', '智能'],
        '软件': ['软件', '系统开发', '平台开发', '信息化'],
        '大数据': ['大数据', '数据中台', '数据治理'],
        '无人机': ['无人机', 'UAV', '航拍'],
        '军品': ['军', '装备', '国防', '武器'],
    }
    matched = []
    for domain, kws in mapping.items():
        if any(k in text for k in kws):
            matched.append(domain)
    if not matched:
        matched = ['普通信息']
    return {
        'business_tags': matched,
        'primary_business': matched[0],
        'confidence': 0.6,
        'reason': f'规则匹配：{",".join(matched)}'
    }


# ============================================================
# Agent 3：实体识别
# ============================================================
def agent3_entities(title, content):
    """提取实体：项目/客户/企业/竞争对手/供应商/地区/金额/时间。"""
    text = (title or '') + '\n' + (content or '')[:1800]
    prompt = f"""从以下信息中提取命名实体。

信息标题：{title}
信息正文（截取）：
{text[:1500]}

只返回 JSON，每个字段为字符串数组（无则空数组）：
{{"projects": [], "customers": [], "enterprises": [], "competitors": [], "suppliers": [], "regions": [], "amounts": [], "times": []}}

说明：
- projects: 项目名称
- customers: 采购单位/需求方
- enterprises: 涉及的企业/公司
- competitors: 可能的竞争对手
- suppliers: 供应商/中标方
- regions: 省/市/地区
- amounts: 金额（保留原文表述，如'100万元'）
- times: 时间表述（如'2026年12月'、'截止2026-10-15'）"""
    result = _call_llm_json(prompt, '你是命名实体识别专家，只返回JSON。')
    if result and isinstance(result, dict):
        return {k: result.get(k, []) if isinstance(result.get(k), list) else [] for k in
                ['projects', 'customers', 'enterprises', 'competitors', 'suppliers', 'regions', 'amounts', 'times']}
    return _rule_entities(title, content)


def _rule_entities(title, content):
    """规则降级实体识别。"""
    text = (title or '') + (content or '')
    entities = {k: [] for k in
                ['projects', 'customers', 'enterprises', 'competitors', 'suppliers', 'regions', 'amounts', 'times']}
    # 金额
    for m in re.finditer(r'([0-9]+(?:\.[0-9]+)?\s*(?:万|亿)?元)', text):
        entities['amounts'].append(m.group(1).strip())
    # 时间
    for m in re.finditer(r'(20\d{2}年\d{1,2}月(?:\d{1,2}日)?|20\d{2}[-/]\d{1,2}[-/]\d{1,2})', text):
        entities['times'].append(m.group(1))
    # 采购单位
    m = re.search(r'采购[单位人][:：\s]*([^\s,，。；；]{2,30})', text)
    if m:
        entities['customers'].append(m.group(1).strip())
    # 地区
    for prov in ['北京', '上海', '广东', '江苏', '浙江', '山东', '四川', '湖北', '湖南', '河南',
                 '河北', '福建', '安徽', '辽宁', '陕西', '云南', '广西', '新疆', '内蒙古', '黑龙江']:
        if prov in text:
            entities['regions'].append(prov)
    return entities


# ============================================================
# Agent 4：项目分析
# ============================================================
def agent4_project(title, content, entities=None):
    """分析：采购内容/客户需求/预算/采购阶段/项目时间。"""
    text = (title or '') + '\n' + (content or '')[:1800]
    ent_hint = ''
    if entities:
        ent_hint = f'\n已知实体：{json.dumps(entities, ensure_ascii=False)}'
    prompt = f"""分析以下信息的采购项目要素。

信息标题：{title}
信息正文（截取）：
{text[:1500]}{ent_hint}

只返回 JSON：
{{"procurement_content": "采购的具体内容/货物/服务", "customer_needs": "客户需求要点", "budget": "预算金额（原文表述，无则空）", "procurement_stage": "采购阶段（意向/挂网/招标/开标/中标/执行）", "project_timeline": "项目时间节点"}}"""
    result = _call_llm_json(prompt, '你是采购项目分析专家，只返回JSON。')
    if result and isinstance(result, dict):
        return result
    return _rule_project(title, content)


def _rule_project(title, content):
    """规则降级项目分析。"""
    text = (title or '') + (content or '')
    budget = ''
    m = re.search(r'预算[：:]*([0-9.]+\s*(?:万|亿)?元?)', text)
    if m:
        budget = m.group(0)
    stage = '挂网'
    if '中标' in text:
        stage = '中标'
    elif '招标' in text:
        stage = '招标'
    elif '意向' in text:
        stage = '意向'
    return {
        'procurement_content': title or '',
        'customer_needs': '',
        'budget': budget,
        'procurement_stage': stage,
        'project_timeline': '',
    }


# ============================================================
# Agent 5：能力匹配
# ============================================================
def agent5_capability(title, content, project, db=None):
    """依据 CRM 产品库判断我方能否承接。"""
    # 加载产品库摘要
    products_hint = ''
    if db is not None:
        try:
            rows = db.execute(
                "SELECT name, category, description FROM products ORDER BY id LIMIT 50"
            ).fetchall()
            if rows:
                products_hint = '我方产品库：\n' + '\n'.join(
                    f"- {r['name']}（{r['category'] or '未分类'}）：{(r['description'] or '')[:60]}" for r in rows
                )
        except Exception:
            pass

    text = (title or '') + '\n' + (content or '')[:1200]
    proj_hint = json.dumps(project, ensure_ascii=False) if project else ''
    prompt = f"""根据我方产品/能力，判断能否承接该项目。

{products_hint}

项目标题：{title}
项目正文（截取）：
{text[:1000]}
项目分析：{proj_hint}

只返回 JSON：
{{"can_do": true或false, "matched_products": ["匹配的产品名"], "capability_gap": "能力差距说明（无则空）", "confidence": 0到1, "reason": "一句话判断理由"}}"""
    result = _call_llm_json(prompt, '你是售前能力评估专家，只返回JSON。')
    if result and isinstance(result, dict) and 'can_do' in result:
        return result
    return _rule_capability(title, content, db)


def _rule_capability(title, content, db=None):
    """规则降级能力匹配：基于产品名关键词命中。"""
    text = (title or '') + (content or '')
    matched = []
    if db is not None:
        try:
            rows = db.execute("SELECT name FROM products").fetchall()
            for r in rows:
                if r['name'] and r['name'] in text:
                    matched.append(r['name'])
        except Exception:
            pass
    return {
        'can_do': len(matched) > 0,
        'matched_products': matched[:5],
        'capability_gap': '' if matched else '未匹配到我方产品',
        'confidence': 0.6 if matched else 0.4,
        'reason': f'规则匹配{len(matched)}个产品'
    }


# ============================================================
# Agent 6：商机评分
# ============================================================
def agent6_scoring(context):
    """计算 7 维度评分：业务匹配度/客户价值/预算金额/项目阶段/时间紧迫度/区域匹配度/竞争情况。"""
    prompt = f"""基于以下分析结果，对商机进行 7 维度评分（每维度 0-100）。

分析上下文：
{json.dumps(context, ensure_ascii=False)[:2000]}

评分维度：
- business_match: 业务匹配度（与我方业务的契合程度）
- customer_value: 客户价值（客户重要性/战略价值）
- budget_amount: 预算金额（预算规模，越大越高）
- project_stage: 项目阶段（越接近招标越高分）
- time_urgency: 时间紧迫度（截止时间越近越高）
- region_match: 区域匹配度（目标区域与我方覆盖范围匹配度）
- competition: 竞争情况（竞争对手越少越高）

只返回 JSON：
{{"score": 0到100总分, "dimensions": {{"business_match": 0, "customer_value": 0, "budget_amount": 0, "project_stage": 0, "time_urgency": 0, "region_match": 0, "competition": 0}}, "reason": "评分理由（一句话）"}}"""
    result = _call_llm_json(prompt, '你是商机评分专家，只返回JSON。')
    if result and isinstance(result, dict) and 'score' in result:
        return result
    return _rule_scoring(context)


def _rule_scoring(context):
    """规则降级评分。"""
    dims = {
        'business_match': 50, 'customer_value': 50, 'budget_amount': 50,
        'project_stage': 50, 'time_urgency': 50, 'region_match': 50, 'competition': 50
    }
    # 业务匹配度
    biz = context.get('agent2', {})
    tags = biz.get('business_tags', [])
    if tags:
        dims['business_match'] = min(30 + len(tags) * 20, 100)
    # 能力匹配
    cap = context.get('agent5', {})
    if cap.get('can_do'):
        dims['business_match'] = min(dims['business_match'] + 20, 100)
    # 预算
    proj = context.get('agent4', {})
    budget = proj.get('budget', '')
    if budget:
        m = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*万', budget)
        if m:
            amt = float(m.group(1))
            dims['budget_amount'] = min(int(amt / 10), 100)
        else:
            dims['budget_amount'] = 60
    # 项目阶段
    stage = proj.get('procurement_stage', '')
    stage_map = {'意向': 40, '挂网': 60, '招标': 90, '开标': 95, '中标': 30, '执行': 20}
    dims['project_stage'] = stage_map.get(stage, 50)
    # 时间紧迫度
    ents = context.get('agent3', {})
    if ents.get('times'):
        dims['time_urgency'] = 70
    # 竞争
    comps = ents.get('competitors', [])
    dims['competition'] = max(80 - len(comps) * 20, 20)
    score = int(sum(dims.values()) / 7)
    return {'score': score, 'dimensions': dims, 'reason': '规则评分'}


# ============================================================
# Agent 7：销售建议
# ============================================================
def agent7_suggestion(context):
    """输出销售建议：为什么跟/何时跟/找谁/怎么切入/准备什么/可能竞争对手。"""
    prompt = f"""基于以下商机分析，给出销售行动建议。

分析上下文：
{json.dumps(context, ensure_ascii=False)[:2000]}

只返回 JSON：
{{"why_follow": "为什么值得跟（1-2句）", "when_to_follow": "最佳跟进时机", "who_to_contact": "建议联系对象", "how_to_enter": "切入策略", "what_to_prepare": "应准备的材料", "potential_competitors": ["可能竞争对手1", "可能竞争对手2"]}}"""
    result = _call_llm_json(prompt, '你是资深销售顾问，只返回JSON。')
    if result and isinstance(result, dict):
        return result
    return _rule_suggestion(context)


def _rule_suggestion(context):
    """规则降级销售建议。"""
    proj = context.get('agent4', {})
    ents = context.get('agent3', {})
    cap = context.get('agent5', {})
    scoring = context.get('agent6', {})
    can_do = cap.get('can_do', False)
    return {
        'why_follow': f'评分{scoring.get("score", 0)}分，{"我方能力匹配" if can_do else "需评估能力"}',
        'when_to_follow': '建议一周内联系',
        'who_to_contact': ents.get('customers', ['待确认'])[0] if ents.get('customers') else '待确认',
        'how_to_enter': '电话沟通需求 + 提供方案',
        'what_to_prepare': '公司介绍、相关案例、技术方案',
        'potential_competitors': ents.get('competitors', []),
    }


# ============================================================
# 协同调度：顺序执行 7 个 Agent
# ============================================================
def analyze_with_agents(raw_intel_id, db=None, force=False):
    """对单条原始情报执行 7-Agent 协同分析。

    Args:
        force: False 时若已有分析结果则直接跳过（返回 (None, None)），
               不重复消耗 LLM；True 时强制重新分析覆盖旧结果。

    Returns:
        (result_dict, error_message) — result_dict 含各 Agent 输出
    """
    own_conn = False
    if db is None:
        from extensions import DB_PATH
        db = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
        db.row_factory = sqlite3.Row
        own_conn = True

    try:
        row = db.execute(
            "SELECT * FROM raw_intelligence WHERE id=?", (raw_intel_id,)
        ).fetchone()
        if not row:
            return None, '情报不存在'

        # 防重：已有分析结果且非强制时，跳过不重跑（省 7 次 LLM 调用）
        if not force:
            existing = db.execute(
                "SELECT id FROM intelligence_agent_results WHERE raw_intelligence_id=?",
                (raw_intel_id,)
            ).fetchone()
            if existing:
                return None, None

        title = row['title'] or ''
        content = row['content'] or row['snippet'] or ''

        # 顺序执行 7 个 Agent，上下文逐步累积
        a1 = agent1_classify(title, content)
        a2 = agent2_business(title, content, db)
        a3 = agent3_entities(title, content)
        a4 = agent4_project(title, content, a3)
        a5 = agent5_capability(title, content, a4, db)

        context = {
            'title': title,
            'agent1': a1, 'agent2': a2, 'agent3': a3,
            'agent4': a4, 'agent5': a5,
        }
        a6 = agent6_scoring(context)
        context['agent6'] = a6
        a7 = agent7_suggestion(context)

        result = {
            'agent1_classification': a1,
            'agent2_business': a2,
            'agent3_entities': a3,
            'agent4_project': a4,
            'agent5_capability': a5,
            'agent6_scoring': a6,
            'agent7_suggestion': a7,
            'final_score': a6.get('score', 0),
            'final_summary': a7.get('why_follow', ''),
        }

        # 持久化到 intelligence_agent_results
        _save_agent_result(db, raw_intel_id, result)
        # 同步到 intelligence_leads 表，让 AI商机识别 tab 能看到
        _sync_to_intelligence_leads(db, raw_intel_id, row, result)
        # 同步原始情报状态
        db.execute("UPDATE raw_intelligence SET status='analyzed' WHERE id=?", (raw_intel_id,))
        db.commit()
        return result, None
    except Exception as e:
        logger.error(f'7-Agent 分析失败 {raw_intel_id}: {e}', exc_info=True)
        return None, str(e)
    finally:
        if own_conn:
            db.close()


def _save_agent_result(db, raw_intel_id, result):
    """保存/更新 7-Agent 分析结果到 intelligence_agent_results 表。"""
    # 建表（幂等）
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS intelligence_agent_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_intelligence_id INTEGER,
                agent1_classification TEXT,
                agent2_business TEXT,
                agent3_entities TEXT,
                agent4_project TEXT,
                agent5_capability TEXT,
                agent6_scoring TEXT,
                agent7_suggestion TEXT,
                final_score INTEGER DEFAULT 0,
                final_summary TEXT,
                analyzed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(raw_intelligence_id)
            )
        """)
    except Exception:
        pass

    fields = json.dumps(result, ensure_ascii=False)
    db.execute("""
        INSERT INTO intelligence_agent_results (
            raw_intelligence_id, agent1_classification, agent2_business,
            agent3_entities, agent4_project, agent5_capability,
            agent6_scoring, agent7_suggestion, final_score, final_summary
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(raw_intelligence_id) DO UPDATE SET
            agent1_classification=excluded.agent1_classification,
            agent2_business=excluded.agent2_business,
            agent3_entities=excluded.agent3_entities,
            agent4_project=excluded.agent4_project,
            agent5_capability=excluded.agent5_capability,
            agent6_scoring=excluded.agent6_scoring,
            agent7_suggestion=excluded.agent7_suggestion,
            final_score=excluded.final_score,
            final_summary=excluded.final_summary,
            analyzed_at=CURRENT_TIMESTAMP
    """, (
        raw_intel_id,
        json.dumps(result['agent1_classification'], ensure_ascii=False),
        json.dumps(result['agent2_business'], ensure_ascii=False),
        json.dumps(result['agent3_entities'], ensure_ascii=False),
        json.dumps(result['agent4_project'], ensure_ascii=False),
        json.dumps(result['agent5_capability'], ensure_ascii=False),
        json.dumps(result['agent6_scoring'], ensure_ascii=False),
        json.dumps(result['agent7_suggestion'], ensure_ascii=False),
        result['final_score'],
        result['final_summary'],
    ))


def _sync_to_intelligence_leads(db, raw_intel_id, raw_row, agent_result):
    """将 7-Agent 分析结果同步到 intelligence_leads 表。

    如果已有记录则更新，没有则插入。这样 AI商机识别 tab 能看到 7-Agent 分析过的情报。
    """
    a3 = agent_result.get('agent3_entities') or {}
    a4 = agent_result.get('agent4_project') or {}
    a6 = agent_result.get('agent6_scoring') or {}
    a7 = agent_result.get('agent7_suggestion') or {}

    # 从实体识别提取字段
    entities = a3 if isinstance(a3, dict) else {}
    buyers = entities.get('customers') or []
    competitors = entities.get('competitors') or []
    regions = entities.get('regions') or []
    amounts = entities.get('amounts') or []
    times = entities.get('times') or []

    # 从项目分析提取字段
    project = a4 if isinstance(a4, dict) else {}
    budget = project.get('budget') or (amounts[0] if amounts else '')
    deadline = times[0] if times else (project.get('project_timeline') or '')

    # 评分信息
    score = int(a6.get('score', 0)) if isinstance(a6, dict) else 0
    score_reason = (a6.get('reason') or '') if isinstance(a6, dict) else ''
    dimensions = (a6.get('dimensions') or {}) if isinstance(a6, dict) else {}

    # 评分等级
    if score >= 90:
        grade = 'S'
    elif score >= 80:
        grade = 'A'
    elif score >= 60:
        grade = 'B'
    else:
        grade = 'C'

    # 采购阶段 → 生命周期阶段
    stage = (project.get('procurement_stage') or '').strip()
    from lifecycle_model import derive_stage
    lifecycle_stage = derive_stage(stage)

    # AI摘要
    summary_parts = []
    if project.get('procurement_content'):
        summary_parts.append(f"采购内容：{project['procurement_content']}")
    if project.get('customer_needs'):
        summary_parts.append(f"客户需求：{project['customer_needs']}")
    if a7.get('why_follow'):
        summary_parts.append(f"建议：{a7['why_follow']}")
    analysis_summary = '；'.join(summary_parts)

    # 是否相关（普通信息/新闻/中标不相关——中标公告项目已定标，仅作竞争对手情报）
    a1 = agent_result.get('agent1_classification') or {}
    category = (a1.get('category') or '').strip() if isinstance(a1, dict) else ''
    win_kw = ('中标', '成交结果', '结果公告', '结果公示')
    title_is_win = any(kw in (raw_row['title'] or '') for kw in win_kw)
    is_relevant = 0 if (category in ('普通信息', '新闻', '中标') or title_is_win) else 1

    # 检查是否已有 intelligence_leads 记录
    existing = db.execute(
        "SELECT id FROM intelligence_leads WHERE raw_intelligence_id=?", (raw_intel_id,)
    ).fetchone()

    fields = {
        'title': raw_row['title'] or '',
        'buyer': buyers[0] if buyers else '',
        'budget': budget,
        'deadline': deadline,
        'project_type': '',
        'procurement_method': stage,
        'region': regions[0] if regions else '',
        'contact_person': '',
        'contact_phone': '',
        'competitors': json.dumps(competitors, ensure_ascii=False),
        'keywords_matched': raw_row['keywords_matched'] if 'keywords_matched' in raw_row.keys() else '',
        'score': score,
        'score_reason': score_reason,
        'is_relevant': is_relevant,
        'analysis_summary': analysis_summary,
        'score_dimensions': json.dumps(dimensions, ensure_ascii=False),
        'score_grade': grade,
        'score_method': '7-agent',
        'lifecycle_stage': lifecycle_stage,
    }

    if existing:
        set_clause = ', '.join(f"{k}=?" for k in fields)
        params = list(fields.values()) + [raw_intel_id]
        db.execute(
            f"UPDATE intelligence_leads SET {set_clause} WHERE raw_intelligence_id=?",
            params
        )
    else:
        cols = ['raw_intelligence_id', 'source_id'] + list(fields.keys())
        vals = [raw_intel_id, raw_row['source_id']] + list(fields.values())
        placeholders = ', '.join('?' for _ in vals)
        db.execute(
            f"INSERT INTO intelligence_leads ({', '.join(cols)}) VALUES ({placeholders})",
            vals
        )


def get_agent_result(raw_intel_id, db=None):
    """读取已保存的 7-Agent 分析结果。"""
    own_conn = False
    if db is None:
        from extensions import DB_PATH
        db = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
        db.row_factory = sqlite3.Row
        own_conn = True
    try:
        row = db.execute(
            "SELECT * FROM intelligence_agent_results WHERE raw_intelligence_id=?",
            (raw_intel_id,)
        ).fetchone()
        if not row:
            return None
        out = {}
        for key in ['agent1_classification', 'agent2_business', 'agent3_entities',
                    'agent4_project', 'agent5_capability', 'agent6_scoring', 'agent7_suggestion']:
            out[key] = json.loads(row[key]) if row[key] else {}
        out['final_score'] = row['final_score']
        out['final_summary'] = row['final_summary']
        out['analyzed_at'] = row['analyzed_at']
        return out
    finally:
        if own_conn:
            db.close()


def batch_analyze_with_agents(source_id=None, limit=20, db=None):
    """批量执行 7-Agent 分析。

    Returns:
        dict: {analyzed, success, failed, skipped}
    """
    own_conn = False
    if db is None:
        from extensions import DB_PATH
        db = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
        db.row_factory = sqlite3.Row
        own_conn = True
    try:
        sql = "SELECT id FROM raw_intelligence WHERE status='pending'"
        params = []
        if source_id:
            sql += " AND source_id=?"
            params.append(source_id)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = db.execute(sql, params).fetchall()

        total = len(rows)
        success = failed = skipped = 0
        for r in rows:
            res, err = analyze_with_agents(r['id'], db)
            if err:
                failed += 1
                logger.warning(f'7-Agent 分析失败 {r["id"]}: {err}')
            elif res is None:
                skipped += 1
            else:
                success += 1
        return {'analyzed': total, 'success': success, 'failed': failed, 'skipped': skipped}
    finally:
        if own_conn:
            db.close()
