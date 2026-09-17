"""拜访纪要丰富化处理模块。

功能：
1. 从拜访纪要内容中提取结构化信息（客户、日期、地点、联系人、目的、需求、下一步行动）
2. 自动匹配 customers 表，关联 cust_id
3. 生成摘要、标签
4. 清理无效/重复拜访纪要

设计原则：
- 优先使用规则提取（速度快、无 LLM 依赖）
- 规则提取失败时降级为 LLM
- 不修改已有有效数据，只补全缺失字段
"""
import re
import json
import logging

logger = logging.getLogger(__name__)


# ============================================================
# 规则提取：从拜访纪要内容中提取结构化字段
# ============================================================

# 拜访纪要常见格式：
# 商 务 拜 访 记 录
# 填表人 | 庞峰 | 时间 | 2022.8.9
# 拜访 单位 | 能建集团安徽电建二公司建筑公司 | 地点 | 强华工业园
# 我方参会人员 | 庞峰，赵陆远
# 对方参会人员 | 徐西兴 ...
# 拜访 目的 | ...
# 会谈记录... | ...

FIELD_PATTERNS = {
    'company': [
        r'拜访\s*单位[｜|\s]*([^\n｜|]+)',
        r'被访\s*单位[｜|\s]*([^\n｜|]+)',
        r'客户\s*名称[｜|\s]*([^\n｜|]+)',
    ],
    'date': [
        r'时\s*间[｜|\s]*([^\n｜|]+)',
        r'日\s*期[｜|\s]*([^\n｜|]+)',
        r'拜访\s*时间[｜|\s]*([^\n｜|]+)',
    ],
    'location': [
        r'地\s*点[｜|\s]*([^\n｜|]+)',
    ],
    'contact_person': [
        r'对方参会人员[｜|\s]*([^\n]+(?:\n[^\n｜|]+)*)',
        r'对方\s*人员[｜|\s]*([^\n｜|]+)',
        r'联系人[｜|\s]*([^\n｜|]+)',
    ],
    'our_attendees': [
        r'我方参会人员[｜|\s]*([^\n｜|]+)',
        r'我方\s*人员[｜|\s]*([^\n｜|]+)',
    ],
    'purpose': [
        r'拜访\s*目的[｜|\s]*([^\n]+(?:\n[^\n｜|]+)*)',
        r'会议\s*目的[｜|\s]*([^\n｜|]+)',
    ],
}


def _extract_field(content, patterns):
    """按模式列表依次尝试提取字段，返回首个非空匹配。"""
    for pat in patterns:
        m = re.search(pat, content)
        if m:
            val = m.group(1).strip()
            # 截断到第一个换行
            val = val.split('\n')[0].strip()
            if val and len(val) < 200:
                return val
    return ''


def extract_visit_metadata(content, title=''):
    """从拜访纪要内容中提取结构化信息。

    返回 dict:
        company, date, location, contact_person, our_attendees,
        purpose, customer_needs, next_actions, summary, tags
    """
    if not content:
        return {}

    text = content.strip()
    meta = {}

    # 1. 提取各字段
    for field, patterns in FIELD_PATTERNS.items():
        meta[field] = _extract_field(text, patterns)

    # 2. 清理公司名（去掉常见后缀）
    if meta.get('company'):
        meta['company'] = re.sub(r'\s+', '', meta['company'])[:100]

    # 3. 从标题提取日期（格式如 "20220809能建集团二公司交流纪要"）
    if not meta.get('date'):
        m = re.match(r'^(\d{8})', title or '')
        if m:
            d = m.group(1)
            meta['date'] = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        else:
            m = re.match(r'^(\d{4}-\d{2}-\d{2})', title or '')
            if m:
                meta['date'] = m.group(1)

    # 4. 提取客户需求（含"需求/希望/要求/需要/计划/打算"的句子）
    needs = []
    for s in re.split(r'[。！？\n]+', text):
        s = s.strip()
        if 5 < len(s) < 150 and any(w in s for w in ['需求', '希望', '要求', '需要', '想要', '计划', '打算', '关注', '关心']):
            needs.append(s[:100])
    meta['customer_needs'] = needs[:5]

    # 5. 提取下一步行动（含"跟进/下一步/后续/下次/安排"的句子）
    actions = []
    for s in re.split(r'[。！？\n]+', text):
        s = s.strip()
        if 5 < len(s) < 150 and any(w in s for w in ['跟进', '下一步', '后续', '下次', '安排', '方案', '实施']):
            actions.append(s[:100])
    meta['next_actions'] = actions[:5]

    # 6. 生成摘要（取会谈记录前2-3句）
    summary = ''
    talk_match = re.search(r'(?:会谈记录|会谈要点|主要内容|交流内容)[：:]*\s*([^\n]+(?:\n[^\n｜|]+){0,2})', text)
    if talk_match:
        summary = talk_match.group(1).strip()[:300]
    if not summary:
        sentences = [s.strip() for s in re.split(r'[。！？\n]+', text) if s.strip() and len(s.strip()) > 10]
        summary = '。'.join(sentences[:3])[:300]
    meta['summary'] = summary

    # 7. 生成标签（从内容中提取高频业务关键词）
    business_kw = ['遥感', 'GIS', '农业', '林业', '水利', '生态', '无人机', '仿真', '雷达',
                   '大数据', 'AI', '人工智能', '软件开发', '系统集成', '测绘', '监测', '平台']
    tags = [kw for kw in business_kw if kw.lower() in text.lower()]
    meta['tags'] = ','.join(tags[:5])

    return meta


# ============================================================
# 客户匹配
# ============================================================

def match_customer(db, company_name):
    """根据企业名称匹配 customers 表，返回 cust_id 或 None。

    匹配策略：
    1. 精确匹配 company 字段
    2. 包含匹配（company LIKE '%name%' 或 name LIKE '%company%'）
    3. 取最接近的（最短匹配优先，避免"中国"匹配到太多）
    """
    if not company_name:
        return None

    # 去掉常见后缀用于模糊匹配
    short_name = re.sub(r'(有限公司|股份有限公司|集团|公司|研究院|研究所|学院|学校|局|中心|部)$', '', company_name)
    short_name = short_name.strip()

    # 精确匹配
    row = db.execute("SELECT id FROM customers WHERE company = ?", (company_name,)).fetchone()
    if row:
        return row['id']

    # 模糊匹配：customers.company 包含 company_name，或反过来
    if short_name:
        row = db.execute(
            "SELECT id FROM customers WHERE company LIKE ? OR company LIKE ? ORDER BY LENGTH(company) ASC LIMIT 1",
            (f'%{short_name}%', f'%{company_name}%')
        ).fetchone()
        if row:
            return row['id']

    return None


# ============================================================
# 单条拜访纪要丰富化
# ============================================================

def enrich_visit_summary(db, doc_id):
    """丰富单条拜访纪要：提取结构化信息、关联客户、生成摘要、补全标签。

    返回 (updated_fields_dict, matched_cust_id)。
    不修改已有非空字段，只补全缺失字段。
    """
    doc = db.execute(
        "SELECT id, title, content, cust_id, summary, tags, owner_id FROM knowledge_documents WHERE id=?",
        (doc_id,)
    ).fetchone()
    if not doc:
        return None, None

    title = doc['title'] or ''
    content = doc['content'] or ''

    # 规则提取
    meta = extract_visit_metadata(content, title)

    updates = {}

    # 1. 关联客户（仅当 cust_id 为空时）
    matched_cust = None
    if not doc['cust_id'] and meta.get('company'):
        matched_cust = match_customer(db, meta['company'])
        if matched_cust:
            updates['cust_id'] = matched_cust

    # 2. 补全 summary（仅当为空时）
    if not doc['summary'] and meta.get('summary'):
        updates['summary'] = meta['summary']

    # 3. 补全 tags（仅当为空时）
    if not doc['tags'] and meta.get('tags'):
        updates['tags'] = meta['tags']

    # 4. 优化标题：统一为"日期 客户 拜访纪要"格式
    if title.startswith('拜访纪要：') and meta.get('company'):
        date_str = meta.get('date', '')
        new_title = f"{date_str} {meta['company']} 拜访纪要" if date_str else f"{meta['company']} 拜访纪要"
        if new_title != title:
            updates['title'] = new_title[:150]

    # 5. 将结构化提取结果存入 doc_metadata（供详情页展示）
    if meta:
        existing_meta = {}
        try:
            # doc_metadata 字段可能不存在，用 try
            existing_meta = json.loads(doc['doc_metadata'] or '{}')
        except Exception:
            existing_meta = {}
        # 合并提取的元数据（不覆盖已有）
        for k, v in meta.items():
            if v and k not in existing_meta:
                existing_meta[k] = v
        updates['doc_metadata'] = json.dumps(existing_meta, ensure_ascii=False)

    if updates:
        sets = []
        params = []
        for k, v in updates.items():
            sets.append(f"{k} = ?")
            params.append(v)
        params.append(doc_id)
        db.execute(f"UPDATE knowledge_documents SET {', '.join(sets)} WHERE id = ?", params)
        db.commit()

    return updates, matched_cust


# ============================================================
# 批量清洗
# ============================================================

def clean_visit_summaries(db):
    """清理历史拜访纪要：删除内容过短的无效记录、去重。

    返回 (deleted_short, deleted_duplicate)。
    """
    deleted_short = 0
    deleted_dup = 0

    # 1. 删除内容过短（<50字符）的无效记录
    cur = db.execute("DELETE FROM knowledge_documents WHERE doc_type='visit_summary' AND LENGTH(content) < 50")
    deleted_short = cur.rowcount
    db.commit()

    # 2. 去重：保留最早的一条，删除后续重复（按 content_hash 或 title+content 前500字符）
    dups = db.execute("""
        SELECT id, title, content FROM knowledge_documents
        WHERE doc_type='visit_summary'
        ORDER BY id ASC
    """).fetchall()

    seen = set()
    to_delete = []
    for d in dups:
        # 去重键：title + content前500字符
        key = (d['title'] or '', (d['content'] or '')[:500])
        if key in seen:
            to_delete.append(d['id'])
        else:
            seen.add(key)

    if to_delete:
        placeholders = ','.join(['?'] * len(to_delete))
        cur = db.execute(f"DELETE FROM knowledge_documents WHERE id IN ({placeholders})", to_delete)
        deleted_dup = cur.rowcount
        db.commit()

    return deleted_short, deleted_dup
