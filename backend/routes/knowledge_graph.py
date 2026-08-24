"""知识图谱路由 - 实体提取、关系构建、图谱可视化。

核心功能：
1. 实体管理 - 提取、查询、删除实体
2. 关系管理 - 构建、查询、删除关系
3. 图谱构建 - 从文档批量构建知识图谱
4. 图谱可视化 - 获取图谱数据用于前端展示
"""
import json
import re
import sqlite3
import threading
import uuid
from datetime import datetime

from flask import request, jsonify, current_app

from extensions import get_db, token_required, record_operation_log, DB_PATH
from config import LLM_API_KEY, LLM_API_BASE, LLM_MODEL, USE_LLM

from . import knowledge_graph_bp


# 实体类型定义
ENTITY_TYPES = {
    'person': '人物',
    'organization': '组织/公司',
    'product': '产品/系统',
    'technology': '技术',
    'customer': '客户',
    'competitor': '竞争对手',
    'project': '项目',
    'contract': '合同',
    'business': '商机',
    'qualification': '资质',
    'location': '地点',
    'other': '其他'
}

# 关系类型定义
RELATION_TYPES = {
    'works_at': '任职于',
    'owns': '拥有',
    'produces': '生产',
    'uses': '使用',
    'competes_with': '竞争',
    'partner_of': '合作',
    'manages': '管理',
    'signs': '签署',
    'visits': '拜访',
    'follows_up': '跟进',
    'has_qualification': '具备资质',
    'located_at': '位于',
    'involves': '涉及',
    'related_to': '相关',
    'other': '其他关系'
}


# ============ LLM 实体提取提示词 ============
ENTITY_EXTRACTION_PROMPT = """你是一名CRM知识图谱专家。请从以下业务文档中提取实体和关系，以JSON格式返回。

【文档标题】{title}
【文档内容】
{content}

【实体类型说明】（仅限以下类型，必须准确分类）
- person: 具体的人名（如"张伟"、"李明主任"），不含代词
- organization: 公司/机构全称或简称（如"华为公司"、"中船701所"、"应用中心"），不含"该公司"等代词
- product: 具体产品/系统名称（如"XX雷达模拟器"、"数据管理平台"），不含单独的"系统""平台"等通用词
- technology: 具体技术名称（如"人工智能""大数据分析"），不含单独的"技术""方案"
- customer: 客户单位名称（如"海军装备部""某研究院"）
- competitor: 竞争对手公司名称
- project: 具体项目名称（如"XX型号研制项目"），不含单独的"项目"二字
- contract: 具体合同名称或编号（如"XX采购合同""合同编号HT-2024-001"）
- business: 具体商机名称（如"XX系统采购商机"）
- qualification: 具体资质名称（如"武器装备科研生产许可证""ISO9001认证"）
- location: 具体地点（如"北京""武汉光谷"）
- other: 以上无法覆盖的具体命名实体

【关系类型说明】（仅限以下类型）
- works_at: 任职于（人→组织）
- owns: 拥有（组织→产品/资质/项目）
- produces: 生产/研发（组织→产品）
- uses: 使用（组织/人→产品/技术）
- competes_with: 竞争（组织↔组织）
- partner_of: 合作（组织↔组织/人）
- manages: 管理（人→项目/组织）
- signs: 签署（组织/人→合同）
- visits: 拜访（人→组织/地点）
- follows_up: 跟进（人→商机/客户）
- has_qualification: 具备资质（组织→资质）
- located_at: 位于（组织/地点→地点）
- involves: 涉及（项目/合同→组织/产品）
- related_to: 相关（兜底关系）
- other: 其他关系

【提取规则】（必须严格遵守）
1. 只提取文档中**明确出现**的实体，绝不臆造或推测
2. 实体名称必须是文档中的**原始名称**，不要改写、缩写或扩展
3. **禁止提取**：代词（该公司、该系统、我们、他们）、通用名词（系统、平台、技术、项目、合同）、动词、形容词
4. 实体名称长度≥2个字符，且必须是具体专有名词
5. 同一实体只提取一次，使用文档中首次出现的完整名称
6. 关系必须有明确的源实体和目标实体，且两者都已提取
7. 关系描述要具体，说明关系的依据（如"张伟于2024年3月拜访了XX公司"）
8. 如果文档是拜访记录，重点提取人、客户组织、产品
9. 如果文档是合同，重点提取合同方、合同金额关联的产品/项目
10. 如果文档无任何可提取实体，返回空数组

【返回格式】（严格JSON，不要markdown代码块，不要额外文字）
{{
  "entities": [
    {{"name": "实体名称", "type": "实体类型", "description": "简短描述（含上下文依据）"}},
    {{"name": "张伟", "type": "person", "description": "文档中提到的销售人员"}}
  ],
  "relations": [
    {{"source": "张伟", "target": "XX公司", "type": "visits", "description": "张伟于3月拜访XX公司"}},
    {{"source": "XX公司", "target": "数据平台", "type": "uses", "description": "XX公司使用数据平台"}}
  ]
}}
"""


def _call_llm_for_graph(title, content):
    """调用LLM提取实体和关系。"""
    if not content or not content.strip():
        return None

    prompt = ENTITY_EXTRACTION_PROMPT.format(
        title=title or '未命名',
        content=content[:8000]
    )

    try:
        import requests
        headers = {
            'Authorization': f'Bearer {LLM_API_KEY}',
            'Content-Type': 'application/json'
        }
        payload = {
            'model': LLM_MODEL,
            'messages': [
                {'role': 'system', 'content': '你是CRM领域的知识图谱构建专家，擅长从销售拜访记录、合同、商机等业务文档中精准提取实体和关系。请严格按照JSON格式返回，不要添加任何额外文字，不要使用markdown代码块。'},
                {'role': 'user', 'content': prompt}
            ],
            'temperature': 0.1,
            'max_tokens': 180000
        }

        response = requests.post(
            f'{LLM_API_BASE}/chat/completions',
            headers=headers,
            json=payload,
            timeout=180
        )

        if response.status_code == 200:
            data = response.json()
            message = data['choices'][0]['message']
            raw_text = message.get('content')

            if not raw_text or not raw_text.strip():
                return None

            # 清理 markdown 代码块
            cleaned = raw_text.strip()
            if cleaned.startswith('```'):
                cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
                cleaned = re.sub(r'\s*```$', '', cleaned)

            # 解析 JSON
            try:
                result = json.loads(cleaned)
            except json.JSONDecodeError:
                # 尝试提取 JSON
                json_match = re.search(r'\{[\s\S]*\}', cleaned)
                if json_match:
                    try:
                        result = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        return None
                else:
                    return None

            # 后处理：清洗和过滤实体/关系
            return _postprocess_extraction(result)
        else:
            print(f"[KnowledgeGraph] LLM error: {response.status_code}, {response.text[:200]}")
            return None
    except Exception as e:
        print(f"[KnowledgeGraph] LLM call failed: {e}")
        return None


# ============ 实体后处理（清洗/过滤/归一化） ============

# 停用词：这些词不应作为实体名称
_STOPWORDS = {
    # 通用名词
    '系统', '平台', '软件', '产品', '设备', '装备', '技术', '方案', '架构',
    '项目', '工程', '计划', '合同', '协议', '契约', '商机', '机会',
    '公司', '集团', '部门', '中心', '单位', '机构', '组织',
    '客户', '用户', '对方', '甲方', '乙方', '丙方',
    # 代词
    '该公司', '该系统', '该平台', '该产品', '该技术', '该项目', '该合同',
    '我们', '他们', '你们', '其', '此', '该', '本',
    # 通用动词/形容词
    '管理', '使用', '拥有', '生产', '研发', '销售', '采购', '合作', '竞争',
    '位于', '涉及', '相关', '其他', '签署', '拜访', '跟进',
    # 通用后缀（单独出现时无意义）
    '有限', '股份',
}

# 实体类型有效值
_VALID_ENTITY_TYPES = set(ENTITY_TYPES.keys())
# 关系类型有效值
_VALID_RELATION_TYPES = set(RELATION_TYPES.keys())


def _is_valid_entity_name(name):
    """检查实体名称是否有效（非空、非停用词、长度>=2、非纯通用词）。"""
    if not name:
        return False
    name = name.strip()
    if len(name) < 2:
        return False
    if name in _STOPWORDS:
        return False
    # 纯数字或纯标点
    if re.match(r'^[\d\s\W]+$', name):
        return False
    # 以"该"开头的代词
    if name.startswith('该') or name.startswith('本') or name.startswith('其'):
        # 例外：本部、本公司等如果是组织名可以保留，但太短的不行
        if len(name) <= 2:
            return False
    return True


def _normalize_entity_name(name):
    """归一化实体名称：去除首尾空白、引号、括号。"""
    name = name.strip()
    # 去除首尾引号
    name = name.strip('"\'""''「」『』')
    # 去除首尾括号
    if name.startswith('(') and name.endswith(')'):
        name = name[1:-1].strip()
    if name.startswith('（') and name.endswith('）'):
        name = name[1:-1].strip()
    return name


def _postprocess_extraction(result):
    """对LLM返回的提取结果进行后处理：清洗、过滤、去重、归一化。"""
    if not result or not isinstance(result, dict):
        return {'entities': [], 'relations': []}

    raw_entities = result.get('entities', []) or []
    raw_relations = result.get('relations', []) or []
    if not isinstance(raw_entities, list):
        raw_entities = []
    if not isinstance(raw_relations, list):
        raw_relations = []

    # === 实体清洗 ===
    seen_names = {}  # name(lower) -> entity dict，用于去重
    cleaned_entities = []
    for ent in raw_entities:
        if not isinstance(ent, dict):
            continue
        name = _normalize_entity_name(str(ent.get('name', '')))
        etype = str(ent.get('type', 'other')).strip().lower()
        desc = str(ent.get('description', '')).strip()

        # 类型校验，无效类型归为 other
        if etype not in _VALID_ENTITY_TYPES:
            etype = 'other'

        # 名称有效性校验
        if not _is_valid_entity_name(name):
            continue

        # 去重：同名称+同类型只保留第一个（description更长的优先）
        key = name.lower()
        if key in seen_names:
            existing = seen_names[key]
            # 如果新描述更长，替换
            if len(desc) > len(existing.get('description', '')):
                existing['description'] = desc
            # 如果已有类型更具体（非other），保留已有；否则用新类型
            if existing.get('type') == 'other' and etype != 'other':
                existing['type'] = etype
            continue

        new_ent = {'name': name, 'type': etype, 'description': desc}
        seen_names[key] = new_ent
        cleaned_entities.append(new_ent)

    # === 关系清洗 ===
    entity_name_set = {e['name'].lower() for e in cleaned_entities}
    name_to_canonical = {e['name'].lower(): e['name'] for e in cleaned_entities}
    cleaned_relations = []
    seen_rel_keys = set()
    for rel in raw_relations:
        if not isinstance(rel, dict):
            continue
        source = _normalize_entity_name(str(rel.get('source', '')))
        target = _normalize_entity_name(str(rel.get('target', '')))
        rtype = str(rel.get('type', 'related_to')).strip().lower()
        rdesc = str(rel.get('description', '')).strip()

        # 类型校验
        if rtype not in _VALID_RELATION_TYPES:
            rtype = 'related_to'

        # 源和目标必须都在已提取的实体中
        src_lower = source.lower()
        tgt_lower = target.lower()
        if src_lower not in entity_name_set or tgt_lower not in entity_name_set:
            continue
        # 自环排除
        if src_lower == tgt_lower:
            continue

        # 归一化为标准实体名
        source = name_to_canonical[src_lower]
        target = name_to_canonical[tgt_lower]

        # 关系去重（source+target+type）
        rel_key = (src_lower, tgt_lower, rtype)
        if rel_key in seen_rel_keys:
            continue
        seen_rel_keys.add(rel_key)

        cleaned_relations.append({
            'source': source, 'target': target,
            'type': rtype, 'description': rdesc
        })

    return {'entities': cleaned_entities, 'relations': cleaned_relations}


def _rule_based_extraction(title, content):
    """规则模式实体提取（LLM不可用时的降级方案）。
    使用更精确的正则 + 前缀清洗，避免提取"系统""平台"等无意义通用词，
    并去除正则贪婪匹配导致的多余前缀（如"该系统由北京某研究所"→"北京某研究所"）。
    """
    entities = []
    relations = []

    if not content:
        return {'entities': entities, 'relations': relations}

    text = content
    seen_names = set()

    # 多字符分隔词：用 rfind 截取（不会误匹配实体名内部的字）
    _MULTI_SEPS = [
        '正在', '已经', '使用', '采购', '研发', '生产', '拥有', '具备', '位于',
        '涉及', '管理', '购买', '提供', '开发', '研制', '设计', '集成', '部署',
        '实施', '维护', '运营', '建设', '成立', '注册', '拜访', '访问', '计划',
        '负责', '属于', '来自', '称为', '叫做', '名为',
    ]
    # 单字符前缀词：只去除开头（避免误匹配实体名中间的字，如"华为有限"中的"有"）
    _SINGLE_SEPS = ['该', '本', '其', '某', '由', '在', '对', '向', '从', '给',
                    '和', '与', '及', '或', '的', '了', '是', '有', '将', '要',
                    '被', '把', '让', '使', '到', '去', '过', '着', '地']

    # 动词/介词字符集——实体名中间出现这些说明正则匹配越界了，应整条丢弃
    _BAD_VERBS = set('来回到去给带让使被把将要对会能可应需想要需且但而并以及或')

    def _trim_prefix(name):
        """去除名称开头的介词/动词前缀（循环去除，只处理开头不碰中间）。"""
        result = name
        all_seps = _MULTI_SEPS + _SINGLE_SEPS
        for _ in range(6):  # 最多迭代6次
            changed = False
            for sep in all_seps:
                if result.startswith(sep) and len(result) > len(sep) + 1:
                    result = result[len(sep):]
                    changed = True
                    break
            if not changed:
                break
        return result

    def _is_clean_entity(name):
        """检查实体名是否'干净'：不含动词/介词（说明正则没越界匹配句子）。"""
        if not name or len(name) < 2:
            return False
        # 实体名中间不应出现动词/介词
        bad_count = sum(1 for c in name if c in _BAD_VERBS)
        # 允许1个（如"研究院"的"院"不算），但超过1个说明是句子
        if bad_count > 1:
            return False
        return True

    def _add_entity(name, etype, desc):
        name = name.strip()
        # 清洗前缀
        name = _trim_prefix(name)
        if not name or name in seen_names:
            return
        if not _is_valid_entity_name(name):
            return
        # 规则提取专用：过滤不干净的实体（含多个动词/介词，说明越界了）
        if not _is_clean_entity(name):
            return
        seen_names.add(name)
        entities.append({'name': name, 'type': etype, 'description': desc})

    # 提取人名：前缀+2-4字中文名（要求前缀后有冒号/空格，或"经理/主任/总"后的人名+标点/动词）
    # 模式1：联系人：张伟
    name_pattern1 = r'(?:客户|联系人|负责人|对方|甲方|乙方)\s*[:：]\s*([\u4e00-\u9fa5]{2,4})(?:\s|[，。、,;；]|$)'
    for match in re.finditer(name_pattern1, text):
        _add_entity(match.group(1), 'person', f'从"{match.group(0).strip()}"提取')
    # 模式2：销售张伟、经理张伟 拜访/访问/到/，/。
    name_pattern2 = r'(?:销售|经理|主任|总|工程师|老师)\s*([\u4e00-\u9fa5]{2,3})(?=拜访|访问|去|到|，|。|、|,|;|；|$)'
    for match in re.finditer(name_pattern2, text):
        _add_entity(match.group(1), 'person', f'从"{match.group(0).strip()}"提取')

    # 提取公司名：要求带后缀，前缀2-8字（限制贪婪范围）
    org_pattern = r'([\u4e00-\u9fa5]{2,8}(?:有限公司|股份有限公司|科技有限公司|集团|研究所|研究院|设计院|部队|装备部))'
    for match in re.finditer(org_pattern, text):
        _add_entity(match.group(1), 'organization', '公司/机构名称')

    # 提取产品/系统：要求带具体名称前缀（≥2字），不能只是"系统""平台"等通用词
    product_pattern = r'([\u4e00-\u9fa5]{2,8}(?:系统|平台|软件|模拟器|雷达|终端|服务器))'
    for match in re.finditer(product_pattern, text):
        _add_entity(match.group(1), 'product', '产品/系统名称')

    # 提取技术：要求带具体前缀
    tech_pattern = r'((?:AI|人工智能|大模型|智能|数字化|信息化|云计算|大数据|物联网|区块链|5G|数字孪生)[\u4e00-\u9fa5]{0,6}(?:技术|架构)?)'
    for match in re.finditer(tech_pattern, text):
        tech = match.group(1)
        if len(tech) >= 3:
            _add_entity(tech, 'technology', '技术名称')

    # 提取地点：2-4字+市/省/区/县
    loc_pattern = r'([\u4e00-\u9fa5]{2,4}(?:市|省|区|县|开发区|高新区))'
    for match in re.finditer(loc_pattern, text):
        _add_entity(match.group(1), 'location', '地点')

    # 提取项目：要求带具体名称前缀
    project_pattern = r'([\u4e00-\u9fa5]{2,8}(?:项目|工程))'
    for match in re.finditer(project_pattern, text):
        _add_entity(match.group(1), 'project', '项目名称')

    # 提取合同：带编号或具体名称
    contract_pattern = r'((?:HT|ht|合同编号|合同)\s*[:：]?\s*[A-Za-z0-9\-]+)'
    for match in re.finditer(contract_pattern, text):
        _add_entity(match.group(1).strip(), 'contract', '合同编号')
    contract_name_pattern = r'([\u4e00-\u9fa5]{2,}(?:采购合同|服务合同|销售合同|技术合同|开发合同))'
    for match in re.finditer(contract_name_pattern, text):
        _add_entity(match.group(1), 'contract', '合同名称')

    # 提取资质
    qual_pattern = r'((?:武器装备科研生产许可证|ISO9001|ISO14001|武器装备质量管理体系认证|保密资格认证|高新技术企业|武器装备科研生产单位许可证)[\d\u4e00-\u9fa5]*)'
    for match in re.finditer(qual_pattern, text):
        _add_entity(match.group(1), 'qualification', '资质名称')

    # 简单关系构建：组织使用产品
    org_entities = [e for e in entities if e['type'] == 'organization']
    product_entities = [e for e in entities if e['type'] == 'product']
    person_entities = [e for e in entities if e['type'] == 'person']
    seen_rels = set()

    for org in org_entities:
        for product in product_entities:
            rel_key = (org['name'], product['name'], 'uses')
            if rel_key in seen_rels:
                continue
            seen_rels.add(rel_key)
            relations.append({
                'source': org['name'], 'target': product['name'],
                'type': 'uses', 'description': f'{org["name"]}使用{product["name"]}'
            })

    for person in person_entities:
        for org in org_entities:
            if person['name'] in org['name'] or org['name'] in person['name']:
                continue
            rel_key = (person['name'], org['name'], 'visits')
            if rel_key in seen_rels:
                continue
            seen_rels.add(rel_key)
            relations.append({
                'source': person['name'], 'target': org['name'],
                'type': 'visits', 'description': f'{person["name"]}拜访{org["name"]}'
            })

    return {'entities': entities, 'relations': relations}


# ============ 实体 API ============

@knowledge_graph_bp.route('/api/knowledge-graph/entities', methods=['GET'])
@token_required
def get_entities():
    """获取实体列表。"""
    entity_type = request.args.get('type', '')
    keyword = request.args.get('keyword', '')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    db = get_db()
    cursor = db.cursor()

    conditions = []
    params = []

    if entity_type:
        conditions.append("entity_type = ?")
        params.append(entity_type)
    if keyword:
        conditions.append("(name LIKE ? OR description LIKE ?)")
        kw = f'%{keyword}%'
        params.extend([kw, kw])

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    cursor.execute(f"SELECT COUNT(*) as total FROM knowledge_entities {where_clause}", params)
    total = cursor.fetchone()['total']

    offset = (page - 1) * per_page
    cursor.execute(f"""
        SELECT * FROM knowledge_entities {where_clause}
        ORDER BY importance DESC, updated_at DESC
        LIMIT ? OFFSET ?
    """, params + [per_page, offset])

    entities = [dict(row) for row in cursor.fetchall()]

    # 添加类型中文名
    for e in entities:
        e['entity_type_display'] = ENTITY_TYPES.get(e['entity_type'], e['entity_type'])

    return jsonify({
        'code': 200,
        'message': 'success',
        'data': {
            'entities': entities,
            'total': total,
            'page': page,
            'per_page': per_page,
            'entity_types': [{'value': k, 'label': v} for k, v in ENTITY_TYPES.items()]
        }
    })


@knowledge_graph_bp.route('/api/knowledge-graph/entities/<int:entity_id>', methods=['DELETE'])
@token_required
def delete_entity(entity_id):
    """删除实体及相关关系。"""
    data = request.current_user
    username = data.get('username', '')

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT id FROM knowledge_entities WHERE id = ?", (entity_id,))
    if not cursor.fetchone():
        return jsonify({'code': 404, 'message': '实体不存在', 'data': None})

    # 删除相关关系
    cursor.execute("DELETE FROM knowledge_relations WHERE source_id = ? OR target_id = ?",
                   (entity_id, entity_id))
    # 删除实体
    cursor.execute("DELETE FROM knowledge_entities WHERE id = ?", (entity_id,))
    db.commit()

    record_operation_log(username, '删除', '知识图谱', f'删除实体ID：{entity_id}')

    return jsonify({
        'code': 200,
        'message': '删除成功',
        'data': None
    })


# ============ 关系 API ============

@knowledge_graph_bp.route('/api/knowledge-graph/relations', methods=['GET'])
@token_required
def get_relations():
    """获取关系列表。"""
    relation_type = request.args.get('type', '')
    entity_id = request.args.get('entity_id', '', type=int)

    db = get_db()
    cursor = db.cursor()

    conditions = []
    params = []

    if relation_type:
        conditions.append("r.relation_type = ?")
        params.append(relation_type)
    if entity_id:
        conditions.append("(r.source_id = ? OR r.target_id = ?)")
        params.extend([entity_id, entity_id])

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    cursor.execute(f"""
        SELECT r.*, e1.name as source_name, e1.entity_type as source_type,
               e2.name as target_name, e2.entity_type as target_type
        FROM knowledge_relations r
        JOIN knowledge_entities e1 ON r.source_id = e1.id
        JOIN knowledge_entities e2 ON r.target_id = e2.id
        {where_clause}
        ORDER BY r.confidence DESC, r.created_at DESC
        LIMIT 200
    """, params)

    relations = []
    for row in cursor.fetchall():
        r = dict(row)
        r['source_type_display'] = ENTITY_TYPES.get(r['source_type'], r['source_type'])
        r['target_type_display'] = ENTITY_TYPES.get(r['target_type'], r['target_type'])
        r['relation_type_display'] = RELATION_TYPES.get(r['relation_type'], r['relation_type'])
        relations.append(r)

    return jsonify({
        'code': 200,
        'message': 'success',
        'data': {
            'relations': relations,
            'relation_types': [{'value': k, 'label': v} for k, v in RELATION_TYPES.items()]
        }
    })


# ============ 图谱构建 API ============

# 构建任务状态（进程内存储，重启丢失；够用于进度查询）
_build_tasks = {}

@knowledge_graph_bp.route('/api/knowledge-graph/build', methods=['POST'])
@token_required
def build_graph():
    """从文档构建知识图谱（异步）。

    立即返回 task_id，构建在后台线程执行，**完全不占用 HTTP 线程**，
    前端通过 /api/knowledge-graph/build/status/<task_id> 轮询进度。
    这样 build 调大模型（可能耗时数分钟）也绝不会阻塞登录等短请求。

    后台三阶段分离，绝不在持有数据库写锁期间进行 LLM 调用：
      1. 读取阶段：独立连接读文档，读完立即关闭
      2. LLM 阶段：纯内存，不碰数据库（不持锁）
      3. 写入阶段：独立连接批量写入，每文档即 commit
    """
    data = request.current_user
    username = data.get('username', '')
    req_data = request.get_json(silent=True) or {}

    doc_ids = req_data.get('doc_ids', [])
    entity_types_filter = req_data.get('entity_types', [])
    use_llm = req_data.get('use_llm', True)

    task_id = uuid.uuid4().hex[:8]
    _build_tasks[task_id] = {
        'status': 'running',
        'progress': 0,
        'total_docs': 0,
        'processed_docs': 0,
        'total_entities': 0,
        'total_relations': 0,
        'errors': [],
        'message': '正在准备...',
        'username': username,
        'started_at': datetime.now().isoformat(),
    }

    # 捕获 app 实例，后台线程需要自己的应用上下文（record_operation_log 用 get_db）
    app_obj = current_app._get_current_object()

    def run_build():
        task = _build_tasks[task_id]
        with app_obj.app_context():
            try:
                # 阶段1：读取
                read_conn = sqlite3.connect(DB_PATH, timeout=10)
                read_conn.row_factory = sqlite3.Row
                read_conn.execute("PRAGMA journal_mode=WAL")
                read_cursor = read_conn.cursor()
                if doc_ids:
                    placeholders = ','.join(['?'] * len(doc_ids))
                    read_cursor.execute(f"""
                        SELECT id, title, content, doc_type FROM knowledge_documents
                        WHERE id IN ({placeholders}) AND content IS NOT NULL AND content != ''
                    """, doc_ids)
                else:
                    read_cursor.execute("""
                        SELECT id, title, content, doc_type FROM knowledge_documents
                        WHERE content IS NOT NULL AND content != ''
                    """)
                documents = [dict(r) for r in read_cursor.fetchall()]
                read_conn.close()

                task['total_docs'] = len(documents)
                if not documents:
                    task.update({'status': 'done', 'message': '没有可处理的文档', 'progress': 100})
                    return

                # 阶段2：LLM 提取（纯内存，不碰数据库）
                doc_results = []
                for idx, doc in enumerate(documents):
                    doc_id = doc['id']
                    title = doc['title']
                    content = doc['content']
                    try:
                        if use_llm and USE_LLM:
                            try:
                                result = _call_llm_for_graph(title, content)
                            except Exception as e:
                                print(f"[KnowledgeGraph] LLM超时或失败: {e}")
                                result = None
                        else:
                            result = None
                        if not result:
                            result = _rule_based_extraction(title, content)
                        if not result or (not result.get('entities') and not result.get('relations')):
                            continue
                        entities = result.get('entities', [])
                        relations = result.get('relations', [])
                        if entity_types_filter:
                            entities = [e for e in entities if e.get('type') in entity_types_filter]
                        doc_results.append({'doc_id': doc_id, 'entities': entities, 'relations': relations})
                    except Exception as e:
                        task['errors'].append(f"文档ID {doc_id} ({title}): {str(e)}")
                        print(f"[KnowledgeGraph] Error processing doc {doc_id}: {e}")
                    task['message'] = f'正在提取实体 {idx + 1}/{len(documents)}...'
                    task['progress'] = int((idx + 1) / len(documents) * 80)  # LLM 占 80% 进度

                # 阶段3：写入（每文档即 commit）
                write_conn = sqlite3.connect(DB_PATH, timeout=30)
                write_conn.row_factory = sqlite3.Row
                write_conn.execute("PRAGMA journal_mode=WAL")
                write_conn.execute("PRAGMA busy_timeout=30000")
                write_cursor = write_conn.cursor()
                try:
                    for item in doc_results:
                        doc_id = item['doc_id']
                        entities = item['entities']
                        relations = item['relations']
                        entity_id_map = {}
                        for entity in entities:
                            name = entity.get('name', '').strip()
                            entity_type = entity.get('type', 'other').strip()
                            description = entity.get('description', '')
                            if not name:
                                continue
                            write_cursor.execute(
                                "SELECT id FROM knowledge_entities WHERE name = ? AND entity_type = ?",
                                (name, entity_type))
                            existing = write_cursor.fetchone()
                            if existing:
                                entity_id_map[name] = existing['id']
                                write_cursor.execute("""
                                    UPDATE knowledge_entities
                                    SET description = ?, importance = importance + 0.1,
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE id = ?
                                """, (description, existing['id']))
                            else:
                                write_cursor.execute("""
                                    INSERT INTO knowledge_entities (name, entity_type, description, doc_ids, importance)
                                    VALUES (?, ?, ?, ?, 0.5)
                                """, (name, entity_type, description, str([doc_id])))
                                entity_id_map[name] = write_cursor.lastrowid
                        for relation in relations:
                            source_name = relation.get('source', '').strip()
                            target_name = relation.get('target', '').strip()
                            relation_type = relation.get('type', 'related_to').strip()
                            rel_desc = relation.get('description', '')
                            if source_name not in entity_id_map or target_name not in entity_id_map:
                                continue
                            source_id = entity_id_map[source_name]
                            target_id = entity_id_map[target_name]
                            if source_id == target_id:
                                continue
                            try:
                                write_cursor.execute("""
                                    INSERT OR IGNORE INTO knowledge_relations
                                    (source_id, target_id, relation_type, description, doc_id, confidence)
                                    VALUES (?, ?, ?, ?, ?, 0.8)
                                """, (source_id, target_id, relation_type, rel_desc, doc_id))
                            except Exception:
                                pass
                        task['processed_docs'] += 1
                        task['total_entities'] += len(entities)
                        task['total_relations'] += len(relations)
                        write_conn.commit()
                except Exception as e:
                    write_conn.rollback()
                    task['errors'].append(f"写入数据库失败: {str(e)}")
                    print(f"[KnowledgeGraph] Write error: {e}")
                finally:
                    write_conn.close()

                task.update({'status': 'done', 'message': '构建完成', 'progress': 100})
                try:
                    record_operation_log(username, '构建', '知识图谱',
                                         f"处理 {task['processed_docs']}/{task['total_docs']} 个文档，"
                                         f"提取 {task['total_entities']} 个实体，{task['total_relations']} 个关系")
                except Exception:
                    pass
            except Exception as e:
                task.update({'status': 'error', 'message': f'构建失败: {str(e)}',
                             'errors': [str(e)], 'progress': 100})
                print(f"[KnowledgeGraph] Build task error: {e}")

    threading.Thread(target=run_build, daemon=True).start()
    return jsonify({
        'code': 200,
        'message': '构建已开始',
        'data': {'task_id': task_id}
    })


@knowledge_graph_bp.route('/api/knowledge-graph/build/status/<task_id>', methods=['GET'])
@token_required
def build_status(task_id):
    """查询构建任务进度。"""
    task = _build_tasks.get(task_id)
    if not task:
        return jsonify({'code': 404, 'message': '任务不存在或已过期', 'data': None})
    return jsonify({'code': 200, 'message': 'success', 'data': task})


# ============ 图谱可视化 API ============

@knowledge_graph_bp.route('/api/knowledge-graph/visualization', methods=['GET'])
@token_required
def get_graph_visualization():
    """获取图谱可视化数据（ECharts 格式）。"""
    center_id = request.args.get('center_id', '', type=int)
    entity_type = request.args.get('entity_type', '')
    max_depth = request.args.get('max_depth', 2, type=int)
    max_entities = request.args.get('max_entities', 100, type=int)

    db = get_db()
    cursor = db.cursor()

    # 获取实体
    if center_id:
        # 以指定实体为中心，获取其周围的实体和关系
        cursor.execute("SELECT * FROM knowledge_entities WHERE id = ?", (center_id,))
        center_entity = cursor.fetchone()

        if not center_entity:
            return jsonify({'code': 404, 'message': '中心实体不存在', 'data': None})

        # 获取关联实体（限制深度）
        entity_ids = {center_id}
        all_entities = {center_id: dict(center_entity)}

        for depth in range(max_depth):
            new_ids = set()
            for eid in list(entity_ids):
                cursor.execute("""
                    SELECT target_id as id FROM knowledge_relations WHERE source_id = ?
                    UNION
                    SELECT source_id as id FROM knowledge_relations WHERE target_id = ?
                """, (eid, eid))
                for row in cursor.fetchall():
                    if row['id'] not in entity_ids:
                        new_ids.add(row['id'])

            if not new_ids:
                break

            entity_ids.update(new_ids)
            for eid in new_ids:
                if len(all_entities) >= max_entities:
                    break
                cursor.execute("SELECT * FROM knowledge_entities WHERE id = ?", (eid,))
                entity = cursor.fetchone()
                if entity:
                    all_entities[eid] = dict(entity)

        entities = list(all_entities.values())
        entity_ids = list(all_entities.keys())

        # 获取关系
        placeholders = ','.join(['?'] * len(entity_ids))
        cursor.execute(f"""
            SELECT * FROM knowledge_relations
            WHERE source_id IN ({placeholders}) AND target_id IN ({placeholders})
        """, entity_ids + entity_ids)
        relations = [dict(row) for row in cursor.fetchall()]

    else:
        # 获取所有实体（可按类型过滤）
        # 关键修复：优先选取"参与过关系"的实体，避免按 importance 取前 N 个时取到一堆孤立节点（0 条边）
        conditions = []
        params = []

        if entity_type:
            conditions.append("entity_type = ?")
            params.append(entity_type)

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        # 先取参与过关系的实体（按 importance 排序），再补足到 max_entities
        cursor.execute(f"""
            SELECT e.* FROM knowledge_entities e
            WHERE (
                e.id IN (SELECT DISTINCT source_id FROM knowledge_relations)
                OR e.id IN (SELECT DISTINCT target_id FROM knowledge_relations)
            )
            {('AND ' + ' AND '.join(conditions)) if conditions else ''}
            ORDER BY e.importance DESC
            LIMIT ?
        """, params + [max_entities])
        entities = [dict(row) for row in cursor.fetchall()]

        # 如果还不够 max_entities，再用孤立实体补足
        # 关键修复：正确构造 WHERE 子句，避免 where_clause 为空时拼出 "... AND id NOT IN ..." 这种缺 WHERE 的非法 SQL
        # 同时保证 conditions 与占位符一一对应，避免参数数量不匹配（之前漏掉 entity_type=? 占位符导致 500）
        if len(entities) < max_entities:
            existing_ids = [e['id'] for e in entities]

            # 统一收集 WHERE 条件与参数，确保占位符与参数严格对应
            where_parts = []
            where_params = []
            # 复用与主查询一致的过滤条件（如 entity_type = ?）
            if conditions:
                where_parts.extend(conditions)
                where_params.extend(params)
            # 排除已选实体，避免补足阶段重复
            if existing_ids:
                placeholders_excl = ','.join(['?'] * len(existing_ids))
                where_parts.append(f"id NOT IN ({placeholders_excl})")
                where_params.extend(existing_ids)

            solo_where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

            cursor.execute(f"""
                SELECT * FROM knowledge_entities
                {solo_where_clause}
                ORDER BY importance DESC
                LIMIT ?
            """, where_params + [max_entities - len(entities)])
            entities.extend(dict(row) for row in cursor.fetchall())

        entity_ids = [e['id'] for e in entities]

        # 获取关系
        if entity_ids:
            placeholders = ','.join(['?'] * len(entity_ids))
            cursor.execute(f"""
                SELECT * FROM knowledge_relations
                WHERE source_id IN ({placeholders}) AND target_id IN ({placeholders})
            """, entity_ids + entity_ids)
            relations = [dict(row) for row in cursor.fetchall()]
        else:
            relations = []

    # 构建 ECharts 格式数据
    nodes = []
    for entity in entities:
        entity['entity_type_display'] = ENTITY_TYPES.get(entity['entity_type'], entity['entity_type'])
        nodes.append({
            'id': str(entity['id']),
            'name': entity['name'],
            # 关键修复：category 必须与 categories 数组里的 name 完全匹配（这里用中文 display）
            'category': entity['entity_type_display'],
            'symbolSize': max(30, min(60, 20 + entity.get('importance', 0) * 40)),
            'value': entity.get('importance', 0),
            'itemStyle': {
                'color': _get_entity_color(entity['entity_type'])
            },
            'label': {
                'show': True,
                'fontSize': 12
            },
            'entity': entity  # 附加实体信息
        })

    links = []
    for relation in relations:
        relation['relation_type_display'] = RELATION_TYPES.get(
            relation['relation_type'], relation['relation_type'])
        links.append({
            'source': str(relation['source_id']),
            'target': str(relation['target_id']),
            'label': {
                'show': True,
                'formatter': relation['relation_type_display'],
                'fontSize': 10
            },
            'lineStyle': {
                'color': _get_relation_color(relation['relation_type']),
                'width': max(1, min(5, relation.get('confidence', 0.5) * 5))
            },
            'relation': relation  # 附加关系信息
        })

    # 分类数据
    categories = [{'name': v} for k, v in ENTITY_TYPES.items()]

    return jsonify({
        'code': 200,
        'message': 'success',
        'data': {
            'nodes': nodes,
            'links': links,
            'categories': categories,
            'entity_count': len(nodes),
            'relation_count': len(links),
            'entity_types': [{'value': k, 'label': v, 'color': _get_entity_color(k)}
                            for k, v in ENTITY_TYPES.items()],
            'relation_types': [{'value': k, 'label': v, 'color': _get_relation_color(k)}
                               for k, v in RELATION_TYPES.items()]
        }
    })


@knowledge_graph_bp.route('/api/knowledge-graph/stats', methods=['GET'])
@token_required
def get_graph_stats():
    """获取知识图谱统计信息。"""
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT COUNT(*) as total FROM knowledge_entities")
    total_entities = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) as total FROM knowledge_relations")
    total_relations = cursor.fetchone()['total']

    cursor.execute("SELECT entity_type, COUNT(*) as count FROM knowledge_entities GROUP BY entity_type")
    type_distribution = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT relation_type, COUNT(*) as count FROM knowledge_relations GROUP BY relation_type")
    rel_type_distribution = [dict(row) for row in cursor.fetchall()]

    return jsonify({
        'code': 200,
        'message': 'success',
        'data': {
            'total_entities': total_entities,
            'total_relations': total_relations,
            'entity_type_distribution': [
                {'type': item['entity_type'], 'count': item['count'],
                 'label': ENTITY_TYPES.get(item['entity_type'], item['entity_type']),
                 'color': _get_entity_color(item['entity_type'])}
                for item in type_distribution
            ],
            'relation_type_distribution': [
                {'type': item['relation_type'], 'count': item['count'],
                 'label': RELATION_TYPES.get(item['relation_type'], item['relation_type']),
                 'color': _get_relation_color(item['relation_type'])}
                for item in rel_type_distribution
            ]
        }
    })


# ============ 工具函数 ============

def _get_entity_color(entity_type):
    """获取实体类型对应的颜色。"""
    color_map = {
        'person': '#FF6B6B',
        'organization': '#4ECDC4',
        'product': '#45B7D1',
        'technology': '#96CEB4',
        'customer': '#FFEAA7',
        'competitor': '#DDA0DD',
        'project': '#98D8C8',
        'contract': '#F7DC6F',
        'business': '#BB8FCE',
        'qualification': '#85C1E9',
        'location': '#F8B500',
        'other': '#BDC3C7'
    }
    return color_map.get(entity_type, '#BDC3C7')


def _get_relation_color(relation_type):
    """获取关系类型对应的颜色。"""
    color_map = {
        'works_at': '#FF6B6B',
        'owns': '#4ECDC4',
        'produces': '#45B7D1',
        'uses': '#96CEB4',
        'competes_with': '#DDA0DD',
        'partner_of': '#FFEAA7',
        'manages': '#98D8C8',
        'signs': '#F7DC6F',
        'visits': '#BB8FCE',
        'follows_up': '#85C1E9',
        'has_qualification': '#F8B500',
        'located_at': '#3498DB',
        'involves': '#2ECC71',
        'related_to': '#95A5A6',
        'other': '#BDC3C7'
    }
    return color_map.get(relation_type, '#BDC3C7')


def register_routes(app):
    """注册知识图谱路由。"""
    app.register_blueprint(knowledge_graph_bp)
