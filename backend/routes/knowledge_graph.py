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
ENTITY_EXTRACTION_PROMPT = """你是一名知识图谱专家。请从以下文档中提取实体和关系，并以JSON格式返回。

文档标题：{title}
文档内容：
{content}

请以JSON格式返回以下结构：
{{
  "entities": [
    {{"name": "实体名称", "type": "实体类型", "description": "简短描述"}},
    ...
  ],
  "relations": [
    {{"source": "源实体名称", "target": "目标实体名称", "type": "关系类型", "description": "关系描述"}},
    ...
  ]
}}

实体类型可选值：person(人物), organization(组织/公司), product(产品/系统), technology(技术), customer(客户), competitor(竞争对手), project(项目), contract(合同), business(商机), qualification(资质), location(地点), other(其他)

关系类型可选值：works_at(任职于), owns(拥有), produces(生产), uses(使用), competes_with(竞争), partner_of(合作), manages(管理), signs(签署), visits(拜访), follows_up(跟进), has_qualification(具备资质), located_at(位于), involves(涉及), related_to(相关), other(其他关系)

注意：
- 只提取文档中明确提到的实体和关系，不要臆造
- 实体名称要简洁明确
- 关系描述要具体
- 如果没有实体或关系，返回空数组
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
                {'role': 'system', 'content': '你是专业的知识图谱构建专家。请严格按照JSON格式返回实体和关系，不要添加任何额外文字，不要使用markdown代码块。'},
                {'role': 'user', 'content': prompt}
            ],
            'temperature': 0.3,
            'max_tokens': 260000
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
                return result
            except json.JSONDecodeError:
                # 尝试提取 JSON
                json_match = re.search(r'\{[\s\S]*\}', cleaned)
                if json_match:
                    result = json.loads(json_match.group())
                    return result
                return None
        else:
            print(f"[KnowledgeGraph] LLM error: {response.status_code}, {response.text[:200]}")
            return None
    except Exception as e:
        print(f"[KnowledgeGraph] LLM call failed: {e}")
        return None


def _rule_based_extraction(title, content):
    """规则模式实体提取（LLM不可用时的降级方案）。"""
    entities = []
    relations = []

    if not content:
        return {'entities': entities, 'relations': relations}

    text = content

    # 提取可能的人名（简单规则：2-4字的中文姓名模式）
    name_pattern = r'(?:客户|联系人|负责人|对方|甲方|乙方)\s*[:：]?\s*([\u4e00-\u9fa5]{2,4})'
    for match in re.finditer(name_pattern, text):
        name = match.group(1)
        if name not in [e['name'] for e in entities]:
            entities.append({'name': name, 'type': 'person', 'description': f'从"{match.group(0)}"提取'})

    # 提取公司名
    org_pattern = r'([\u4e00-\u9fa5]+(?:公司|集团|科技|有限公司|股份|有限))'
    for match in re.finditer(org_pattern, text):
        org = match.group(1)
        if org not in [e['name'] for e in entities]:
            entities.append({'name': org, 'type': 'organization', 'description': f'公司名称'})

    # 提取产品/系统
    product_pattern = r'((?:[\u4e00-\u9fa5]+)?(?:系统|平台|软件|产品|设备|装备|雷达|模拟器))'
    for match in re.finditer(product_pattern, text):
        product = match.group(1)
        if product not in [e['name'] for e in entities]:
            entities.append({'name': product, 'type': 'product', 'description': f'产品/系统'})

    # 提取技术
    tech_pattern = r'((?:AI|人工智能|大模型|智能|数字化|信息化|云|大数据|物联网)[\u4e00-\u9fa5]*(?:技术|方案|系统|架构)?)'
    for match in re.finditer(tech_pattern, text):
        tech = match.group(1)
        if tech not in [e['name'] for e in entities]:
            entities.append({'name': tech, 'type': 'technology', 'description': f'技术'})

    # 提取地点
    loc_pattern = r'((?:[\u4e00-\u9fa5]{2,4})(?:市|省|区|县|镇))'
    for match in re.finditer(loc_pattern, text):
        loc = match.group(1)
        if loc not in [e['name'] for e in entities]:
            entities.append({'name': loc, 'type': 'location', 'description': f'地点'})

    # 提取项目
    project_pattern = r'((?:[\u4e00-\u9fa5]+)?(?:项目|工程|计划|方案)[\u4e00-\u9fa5]*)'
    for match in re.finditer(project_pattern, text):
        project = match.group(0)
        if project not in [e['name'] for e in entities]:
            entities.append({'name': project, 'type': 'project', 'description': f'项目'})

    # 提取合同
    contract_pattern = r'((?:[\u4e00-\u9fa5]+)?(?:合同|协议|契约)[\u4e00-\u9fa5]*)'
    for match in re.finditer(contract_pattern, text):
        contract = match.group(0)
        if contract not in [e['name'] for e in entities]:
            entities.append({'name': contract, 'type': 'contract', 'description': f'合同'})

    # 简单关系构建：如果文档中有"XX公司"和"系统"，可能是使用关系
    org_entities = [e for e in entities if e['type'] == 'organization']
    product_entities = [e for e in entities if e['type'] == 'product']
    for org in org_entities:
        for product in product_entities:
            relations.append({
                'source': org['name'],
                'target': product['name'],
                'type': 'uses',
                'description': f'{org["name"]}使用{product["name"]}'
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
