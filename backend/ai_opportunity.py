"""AI 商机识别模块。

Phase3: 对 raw_intelligence 进行 LLM 分析，识别商机、提取客户信息、
识别竞争对手、评分，结果存入 intelligence_leads 表。

LLM 参数：max_tokens=4000, timeout=60, enable_thinking=False（快速响应）
"""
import json
import re
import logging
import sqlite3

logger = logging.getLogger(__name__)


def _load_keywords(db):
    """从数据库加载启用的关键词列表（主词+同义词）。"""
    rows = db.execute("SELECT keyword, synonyms, business_tag FROM keywords WHERE enabled=1").fetchall()
    keywords = []
    for r in rows:
        kw = r['keyword']
        keywords.append(kw)
        if r['synonyms']:
            for s in r['synonyms'].split(','):
                s = s.strip()
                if s:
                    keywords.append(s)
    return keywords


def _build_prompt(title, content, keywords, snippet=''):
    """构造 LLM 分析 prompt。

    要求 LLM 返回 JSON，包含商机判断、客户信息、竞争对手、评分。
    """
    # 截取正文前 2000 字符，避免 token 过多
    text = (content or snippet or '')[:2000]

    kw_list = ', '.join(keywords[:50]) if keywords else '雷达,仿真,模拟训练,卫星,装备,数字孪生,无人机,通信,指控,导航'

    prompt = f"""分析以下采购公告，判断是否为与我司相关的商机，并提取关键信息。

我司业务关键词：{kw_list}

公告标题：{title}
公告正文（截取）：
{text}

重要判断规则：
- 若为"中标公告/成交公告/结果公告/结果公示"（即项目已定标），is_relevant 必须为 false——项目已名花有主，不再作为可跟进商机。但仍提取中标方（写入 competitors）供竞争对手分析使用。

请返回 JSON 格式（不要其他文字）：
{{
  "is_relevant": true/false,
  "buyer": "采购单位名称",
  "budget": "预算金额（如'100万元'，无则空）",
  "deadline": "截止日期（YYYY-MM-DD，无则空）",
  "project_type": "货物/工程/服务",
  "procurement_method": "公开招标/询价/竞争性谈判/竞争性磋商/单一来源/其他",
  "region": "地区（省/市）",
  "contact_person": "联系人",
  "contact_phone": "联系电话",
  "competitors": ["竞争对手1", "竞争对手2"],
  "keywords_matched": ["命中的关键词"],
  "score": 0-100的整数评分,
  "score_reason": "评分理由（一句话）",
  "analysis_summary": "一句话商机分析"
}}

评分标准：
- 关键词匹配度（30分）：命中我司业务关键词数量
- 预算规模（20分）：预算越大分越高
- 紧迫性（15分）：截止日期越近分越高
- 地区匹配（10分）：目标地区加分
- 项目类型匹配（15分）：我司能力范围内的项目类型
- 竞争程度（10分）：竞争对手越少分越高

只返回 JSON，不要其他文字。"""

    return prompt


def _extract_json_from_text(text):
    """从文本中提取 JSON 对象（兼容 LLM 可能输出的额外文字）。"""
    if not text:
        return None
    # 尝试从末尾向前找 JSON 块
    for match in re.finditer(r'\{[^{}]*\}', text, re.DOTALL):
        pass  # 先找简单的
    # 尝试找完整的 JSON 对象（含嵌套）
    pattern = r'\{[\s\S]*\}'
    match = re.search(pattern, text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    # 尝试逐个字符解析
    start = text.find('{')
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
    return None


def analyze_intelligence(raw_intel_id, db=None):
    """分析单条原始情报，返回 intelligence_leads 记录 ID。

    Args:
        raw_intel_id: raw_intelligence.id
        db: 数据库连接（可选，不传则新建）

    Returns:
        (lead_id, error_message) — 成功时 error_message=None
    """
    from config import USE_LLM
    own_conn = False
    if db is None:
        from extensions import DB_PATH
        db = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
        db.row_factory = sqlite3.Row
        own_conn = True

    try:
        row = db.execute(
            "SELECT * FROM raw_intelligence WHERE id=?", (raw_intel_id,)
        ).fetchone()
        if not row:
            return None, '情报不存在'

        # 如果已经分析过，跳过
        existing = db.execute(
            "SELECT id FROM intelligence_leads WHERE raw_intelligence_id=?",
            (raw_intel_id,)
        ).fetchone()
        if existing:
            return existing['id'], None

        keywords = _load_keywords(db)
        snippet = row['snippet'] if 'snippet' in row.keys() else ''
        prompt = _build_prompt(row['title'], row['content'], keywords, snippet)

        # 调用 LLM
        result = None
        if USE_LLM:
            try:
                from qa_engine import call_llm
                messages = [
                    {'role': 'system', 'content': '你是一个专业的商机分析师，擅长从采购公告中识别商机并提取关键信息。只返回JSON。'},
                    {'role': 'user', 'content': prompt},
                ]
                content = call_llm(messages, max_tokens=18000, timeout=360, enable_thinking=False)
                if content:
                    result = _extract_json_from_text(content)
            except Exception as e:
                logger.error(f'LLM 调用失败: {e}')

        # 降级：无 LLM 或 LLM 失败时，用规则匹配
        if not result:
            result = _rule_based_analysis(row, keywords)

        # 商机评分模型：7 维度加权 + 规则/LLM 混合
        from scoring_model import score_lead
        lead_for_scoring = {
            'title': row['title'] or '',
            'buyer': result.get('buyer', ''),
            'budget': result.get('budget', ''),
            'deadline': result.get('deadline', ''),
            'procurement_method': result.get('procurement_method', ''),
            'region': result.get('region', ''),
            'competitors': result.get('competitors', []),
            'keywords_matched': result.get('keywords_matched', []),
            'analysis_summary': result.get('analysis_summary', ''),
            'status': 'analyzed',
        }
        scoring = score_lead(lead_for_scoring)

        # 商机生命周期：根据采购方式推断初始阶段
        from lifecycle_model import derive_stage
        lifecycle_stage = derive_stage(result.get('procurement_method', ''))

        # 保存结果
        cursor = db.execute("""
            INSERT INTO intelligence_leads (
                raw_intelligence_id, source_id, title, buyer, budget, deadline,
                project_type, procurement_method, region, contact_person, contact_phone,
                competitors, keywords_matched, score, score_reason, is_relevant,
                analysis_summary, status, score_dimensions, score_grade, score_method,
                lifecycle_stage
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'analyzed', ?, ?, ?, ?)
        """, (
            raw_intel_id,
            row['source_id'],
            row['title'],
            result.get('buyer', ''),
            result.get('budget', ''),
            result.get('deadline', ''),
            result.get('project_type', ''),
            result.get('procurement_method', ''),
            result.get('region', ''),
            result.get('contact_person', ''),
            result.get('contact_phone', ''),
            json.dumps(result.get('competitors', []), ensure_ascii=False),
            json.dumps(result.get('keywords_matched', []), ensure_ascii=False),
            scoring['score'],
            scoring['reason'],
            1 if result.get('is_relevant', True) else 0,
            result.get('analysis_summary', ''),
            json.dumps(scoring['dimensions'], ensure_ascii=False),
            scoring['grade'],
            scoring['method'],
            lifecycle_stage,
        ))
        db.commit()

        # 更新原始情报状态
        db.execute("UPDATE raw_intelligence SET status='analyzed' WHERE id=?", (raw_intel_id,))
        db.commit()

        # 项目关联：自动将新公告关联到已有项目或创建新项目
        try:
            from project_model import auto_associate_project
            new_lead = db.execute(
                "SELECT * FROM intelligence_leads WHERE id=?", (cursor.lastrowid,)
            ).fetchone()
            proj_result = auto_associate_project(cursor.lastrowid, new_lead, db)
            db.commit()
            if proj_result['action'] == 'created':
                logger.info(f'创建新项目 #{proj_result["project_id"]}: {proj_result["project_name"]}')
            elif proj_result['action'] == 'linked':
                logger.info(f'公告#{cursor.lastrowid} 关联到项目#{proj_result["project_id"]}')
        except Exception as e:
            logger.warning(f'项目关联失败（不影响分析结果）: {e}')

        return cursor.lastrowid, None
    except Exception as e:
        logger.error(f'分析情报失败 {raw_intel_id}: {e}')
        return None, str(e)
    finally:
        if own_conn:
            db.close()


def _rule_based_analysis(row, keywords):
    """无 LLM 时的规则降级分析。"""
    text = (row['title'] or '') + ' ' + (row['content'] or '')
    text_lower = text.lower()

    # 关键词匹配
    matched = []
    for kw in keywords:
        if kw and kw.lower() in text_lower:
            matched.append(kw)

    # 采购方式
    method = ''
    for m in ['公开招标', '询价', '竞争性谈判', '竞争性磋商', '单一来源', '邀请招标']:
        if m in text:
            method = m
            break

    # 项目类型
    ptype = ''
    for t in [('货物', '货物'), ('工程', '工程'), ('服务', '服务')]:
        if t[0] in text:
            ptype = t[1]
            break

    # 预算
    budget = ''
    budget_match = re.search(r'预算[：:]*([0-9.]+)\s*万?元?', text)
    if budget_match:
        budget = budget_match.group(0)

    # 截止日期
    deadline = ''
    date_match = re.search(r'(20\d{2}[-/年]\d{1,2}[-/月]\d{1,2})', text)
    if date_match:
        deadline = date_match.group(1).replace('年', '-').replace('月', '-').replace('/', '-')

    # 评分：关键词匹配 30 + 预算 10 + 紧迫性 10 = 最高 50
    score = min(len(matched) * 5, 30)
    if budget:
        score += 10
    if deadline:
        score += 10
    score = min(score, 50)

    # 中标/成交结果公告：项目已定标，不再作为可跟进商机
    title_lower = (row['title'] or '')
    is_win_result = any(kw in title_lower for kw in ('中标', '成交结果', '结果公告', '结果公示'))

    return {
        'is_relevant': len(matched) > 0 and not is_win_result,
        'buyer': _extract_buyer(text),
        'budget': budget,
        'deadline': deadline,
        'project_type': ptype,
        'procurement_method': method,
        'region': '',
        'contact_person': '',
        'contact_phone': '',
        'competitors': [],
        'keywords_matched': matched[:10],
        'score': score,
        'score_reason': f'规则匹配：命中{len(matched)}个关键词',
        'analysis_summary': f'规则分析：{"相关" if matched else "不相关"}商机',
    }


def _extract_buyer(text):
    """从文本中提取采购单位名称。"""
    patterns = [
        r'采购[单位人][:：\s]*([^\s,，。；；]{2,30})',
        r'招标[单位人][:：\s]*([^\s,，。；；]{2,30})',
        r'([^\s,，。；；]{4,20})采购中心',
        r'([^\s,，。；；]{4,20})(?:人民政府|管理局|中心|研究院|大学|医院)',
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(1).strip()
    return ''


def batch_analyze(source_id=None, limit=20, db=None):
    """批量分析 pending 状态的原始情报。

    Args:
        source_id: 限定数据源（可选）
        limit: 最多分析条数
        db: 数据库连接（可选）

    Returns:
        dict: {analyzed, success, failed, skipped}
    """
    own_conn = False
    if db is None:
        from extensions import DB_PATH
        db = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
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
        success = 0
        failed = 0
        skipped = 0

        for r in rows:
            lead_id, err = analyze_intelligence(r['id'], db)
            if err:
                failed += 1
                logger.warning(f'分析失败 {r["id"]}: {err}')
            elif lead_id is None:
                skipped += 1
            else:
                success += 1

        return {'analyzed': total, 'success': success, 'failed': failed, 'skipped': skipped}
    finally:
        if own_conn:
            db.close()
