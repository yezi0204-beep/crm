"""商机多级去重模型。

4 级去重检测（由粗到细）：
  Level 1: URL Hash        - 精确匹配（raw_intelligence 已实现，此处检测同 URL）
  Level 2: 标题相似度       - difflib SequenceMatcher ≥ 0.85
  Level 3: 客户+项目+地区   - 组合模糊匹配 ≥ 0.80
  Level 4: Embedding相似度  - 余弦相似度 > 0.90

处理流程：
  疑似重复（不自动删除）→ AI判断 → 合并 / 保留

示例：
  "XX市自然资源综合监测平台建设" vs "XX市自然资源监测系统项目"
  → 标题相似度可能 < 0.85，但 Embedding 相似度 > 0.90 → 判为同一项目候选
"""
import json
import logging
import hashlib
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

# ============================================================
# 去重级别配置
# ============================================================
DEDUP_LEVELS = {
    1: {'name': 'URL Hash', 'threshold': 1.0, 'desc': 'URL完全相同'},
    2: {'name': '标题相似度', 'threshold': 0.85, 'desc': '标题文本相似度≥85%'},
    3: {'name': '客户+项目+地区', 'threshold': 0.80, 'desc': '采购单位+标题+地区组合匹配'},
    4: {'name': 'Embedding相似度', 'threshold': 0.90, 'desc': '语义向量相似度>90%'},
}

# 候选状态
CANDIDATE_STATUS = {
    'pending': '待处理',       # 疑似重复，待AI/人工判断
    'ai_same': 'AI判为同一',    # AI判断为同一项目
    'ai_diff': 'AI判为不同',    # AI判断为不同项目
    'merged': '已合并',         # 已执行合并
    'kept': '保留独立',         # 人工确认保留独立
}


# ============================================================
# Level 1: URL Hash
# ============================================================
def url_hash_match(url_a, url_b):
    """URL Hash 精确匹配。"""
    if not url_a or not url_b:
        return False, 0.0
    ha = hashlib.md5(str(url_a).encode()).hexdigest()
    hb = hashlib.md5(str(url_b).encode()).hexdigest()
    return ha == hb, 1.0 if ha == hb else 0.0


# ============================================================
# Level 2: 标题相似度
# ============================================================
def title_similarity(title_a, title_b):
    """标题文本相似度（difflib SequenceMatcher）。

    返回 0-1 的相似度。对中文标题先做清洗（去标点空格）。
    """
    if not title_a or not title_b:
        return 0.0
    import re
    def clean(t):
        # 去标点、空格、换行，保留中英文和数字
        return re.sub(r'[\s\u3000-\u303f\uff00-\uffef，。！？、；：""''（）()【】《》〈〉…—\-_/\\|]', '', str(t))
    a = clean(title_a)
    b = clean(title_b)
    if not a or not b:
        return 0.0
    # 完全相同
    if a == b:
        return 1.0
    # 一方包含另一方（短标题是长标题的子串）
    if a in b or b in a:
        return 0.95
    ratio = SequenceMatcher(None, a, b).ratio()
    return ratio


# ============================================================
# Level 3: 客户 + 项目名称 + 地区 组合匹配
# ============================================================
def combo_similarity(buyer_a, title_a, region_a, buyer_b, title_b, region_b):
    """采购单位 + 项目名称 + 地区 组合相似度。

    各维度独立打分后加权：客户40% + 项目名40% + 地区20%
    """
    def text_sim(a, b):
        if not a or not b:
            return 0.0
        a, b = str(a), str(b)
        if a == b:
            return 1.0
        if a in b or b in a:
            return 0.90
        return SequenceMatcher(None, a, b).ratio()

    buyer_sim = text_sim(buyer_a, buyer_b)
    title_sim = title_similarity(title_a, title_b)
    region_sim = text_sim(region_a, region_b)

    # 客户和项目名是核心，地区是辅助
    total = 0.40 * buyer_sim + 0.40 * title_sim + 0.20 * region_sim
    return total


# ============================================================
# Level 4: Embedding 相似度
# ============================================================
def embedding_similarity(text_a, text_b):
    """Embedding 语义相似度（余弦相似度）。

    将标题+客户+摘要拼接为文本，计算语义向量相似度。
    LLM不可用时降级为标题相似度。
    """
    try:
        from vector_search import generate_embedding, cosine_similarity
    except Exception as e:
        logger.warning(f'导入 vector_search 失败，降级为标题相似度: {e}')
        return title_similarity(text_a, text_b)

    if not text_a or not text_b:
        return 0.0

    vec_a = generate_embedding(text_a)
    vec_b = generate_embedding(text_b)
    if not vec_a or not vec_b:
        # 降级
        return title_similarity(text_a, text_b)

    return cosine_similarity(vec_a, vec_b)


def build_embedding_text(lead):
    """构造用于 Embedding 的文本（标题+客户+摘要）。"""
    def get(key, default=''):
        if isinstance(lead, dict):
            return lead.get(key, default)
        try:
            return lead[key]
        except (KeyError, IndexError):
            return default
    parts = [
        get('title', ''),
        get('buyer', ''),
        get('analysis_summary', ''),
    ]
    return ' '.join(p for p in parts if p).strip()


# ============================================================
# 多级去重检测：对新商机与已有商机对比
# ============================================================
def detect_duplicates(lead, existing_leads, use_embedding=True):
    """对新商机执行多级去重检测。

    Args:
        lead: 新商机（dict/sqlite3.Row），含 id/title/buyer/region 等
        existing_leads: 已有商机列表
        use_embedding: 是否使用 Embedding（Level 4）

    Returns:
        list[dict]: 疑似重复候选列表，每项含 {lead_id, match_level, similarity, reason}
    """
    def get(obj, key, default=''):
        if isinstance(obj, dict):
            return obj.get(key, default)
        try:
            return obj[key]
        except (KeyError, IndexError):
            return default

    new_id = get(lead, 'id')
    new_url = get(lead, 'url', '')
    new_title = get(lead, 'title', '')
    new_buyer = get(lead, 'buyer', '')
    new_region = get(lead, 'region', '')
    new_emb_text = build_embedding_text(lead)

    candidates = []

    for existing in existing_leads:
        ex_id = get(existing, 'id')
        if ex_id == new_id:
            continue

        ex_url = get(existing, 'url', '')
        ex_title = get(existing, 'title', '')
        ex_buyer = get(existing, 'buyer', '')
        ex_region = get(existing, 'region', '')
        ex_emb_text = build_embedding_text(existing)

        match_level = 0
        similarity = 0.0
        reason = ''

        # Level 1: URL Hash
        matched, sim = url_hash_match(new_url, ex_url)
        if matched:
            match_level = 1
            similarity = sim
            reason = f'URL相同: {new_url}'
        else:
            # Level 2: 标题相似度
            sim = title_similarity(new_title, ex_title)
            if sim >= DEDUP_LEVELS[2]['threshold']:
                match_level = 2
                similarity = sim
                reason = f'标题相似度{sim:.2f}: "{new_title[:30]}" vs "{ex_title[:30]}"'
            else:
                # Level 3: 客户+项目+地区
                sim = combo_similarity(new_buyer, new_title, new_region,
                                       ex_buyer, ex_title, ex_region)
                if sim >= DEDUP_LEVELS[3]['threshold']:
                    match_level = 3
                    similarity = sim
                    reason = (f'组合匹配度{sim:.2f}: '
                              f'客户[{new_buyer}/{ex_buyer}] '
                              f'项目[{new_title[:20]}/{ex_title[:20]}] '
                              f'地区[{new_region}/{ex_region}]')
                elif use_embedding and new_emb_text and ex_emb_text:
                    # Level 4: Embedding 相似度（仅当前3级未命中时）
                    sim = embedding_similarity(new_emb_text, ex_emb_text)
                    if sim > DEDUP_LEVELS[4]['threshold']:
                        match_level = 4
                        similarity = sim
                        reason = (f'语义相似度{sim:.2f}>0.90: '
                                  f'"{new_title[:30]}" vs "{ex_title[:30]}"')

        if match_level > 0:
            candidates.append({
                'lead_id': ex_id,
                'match_level': match_level,
                'match_level_name': DEDUP_LEVELS[match_level]['name'],
                'similarity': round(similarity, 4),
                'reason': reason,
            })

    # 按匹配级别升序（Level 1 最强）、相似度降序排序
    candidates.sort(key=lambda x: (x['match_level'], -x['similarity']))
    return candidates


# ============================================================
# AI 判断：两条商机是否为同一项目
# ============================================================
def ai_judge_duplicate(lead_a, lead_b):
    """调用 LLM 判断两条商机是否为同一项目。

    Returns:
        dict: {'is_same': bool, 'confidence': 0-1, 'reason': str}
              LLM 不可用时返回 None
    """
    try:
        from config import USE_LLM
        if not USE_LLM:
            return None
        from qa_engine import call_llm
    except Exception as e:
        logger.warning(f'AI判断模块导入失败: {e}')
        return None

    def get(obj, key, default=''):
        if isinstance(obj, dict):
            return obj.get(key, default)
        try:
            return obj[key]
        except (KeyError, IndexError):
            return default

    info_a = {
        '标题': get(lead_a, 'title', ''),
        '采购单位': get(lead_a, 'buyer', ''),
        '预算': get(lead_a, 'budget', ''),
        '截止日期': get(lead_a, 'deadline', ''),
        '采购方式': get(lead_a, 'procurement_method', ''),
        '地区': get(lead_a, 'region', ''),
        '摘要': get(lead_a, 'analysis_summary', '')[:200],
    }
    info_b = {
        '标题': get(lead_b, 'title', ''),
        '采购单位': get(lead_b, 'buyer', ''),
        '预算': get(lead_b, 'budget', ''),
        '截止日期': get(lead_b, 'deadline', ''),
        '采购方式': get(lead_b, 'procurement_method', ''),
        '地区': get(lead_b, 'region', ''),
        '摘要': get(lead_b, 'analysis_summary', '')[:200],
    }

    prompt = f"""判断以下两条商机是否为同一项目（考虑采购单位、项目名称语义、预算、地区等）。

商机A：
{json.dumps(info_a, ensure_ascii=False)}

商机B：
{json.dumps(info_b, ensure_ascii=False)}

判断要点：
- 项目名称虽用词不同但语义相同（如"监测平台建设"vs"监测系统项目"）→ 同一项目
- 采购单位相同 + 项目内容高度相似 → 同一项目
- 不同采购单位或不同地区 → 不同项目
- 预算/截止日期差异大 → 可能不同

只返回JSON：
{{"is_same": true/false, "confidence": 0.0-1.0, "reason": "一句话说明"}}"""

    try:
        messages = [
            {'role': 'system', 'content': '你是商机去重专家，严格判断是否为同一项目，只返回JSON。'},
            {'role': 'user', 'content': prompt},
        ]
        content = call_llm(messages, max_tokens=500, timeout=30, enable_thinking=False)
        if not content:
            return None
        parsed = _extract_json(content)
        if not isinstance(parsed, dict):
            return None
        return {
            'is_same': bool(parsed.get('is_same', False)),
            'confidence': float(parsed.get('confidence', 0.5)),
            'reason': str(parsed.get('reason', '')),
        }
    except Exception as e:
        logger.warning(f'AI去重判断失败: {e}')
        return None


def _extract_json(text):
    """从 LLM 输出中提取 JSON 对象。"""
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
# 合并策略
# ============================================================
def build_merge_summary(keep_lead, merge_lead):
    """构造合并说明：记录被合并商机的关键信息。"""
    def get(obj, key, default=''):
        if isinstance(obj, dict):
            return obj.get(key, default)
        try:
            return obj[key]
        except (KeyError, IndexError):
            return default

    parts = []
    parts.append(f'合并自商机#{get(merge_lead, "id", "")}')
    if get(merge_lead, 'title'):
        parts.append(f'标题:{get(merge_lead, "title", "")[:50]}')
    if get(merge_lead, 'buyer'):
        parts.append(f'客户:{get(merge_lead, "buyer", "")}')
    if get(merge_lead, 'score'):
        parts.append(f'评分:{get(merge_lead, "score", "")}')
    return ' | '.join(parts)
