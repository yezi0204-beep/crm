"""AI 智能体模块

将智能体深度嵌入 CRM 业务流程，提供四项核心能力：
1. 对话式交互替代手动录入（POST /api/ai/agent）
   - 销售人员通过文字/语音直接汇报，智能体识别写操作意图并自动更新 CRM 状态
   - 支持创建跟进记录、新增客户、更新商机概率/阶段
   - 置信度不足或实体歧义时返回"待确认"卡片，由用户确认后二次执行
2. 自动化复盘与总结（POST /api/ai/visit-summary）
   - 拜访结束后基于拜访记录+客户信息+关联商机生成结构化复盘摘要
   - 摘要自动回流沉淀至 knowledge_base 企业知识资产
3. 流式对话（POST /api/ai/agent/stream）
   - SSE 流式输出，用于查询意图的自然语言回答逐字显示
4. 智能线索管理（POST /api/ai/leads/evaluate）
   - 结合历史成交数据由智能体评估线索意向分值
   - 复用 leads._assign_lead 多维度评分精准分配：综合销售人员的历史拜访案例、
     商机推进情况、合同签订业绩，按行业匹配/历史业绩/商机转化/拜访经验/工作量
     6个维度打分，科学推荐最匹配的负责人

数据与 API 对接：智能体通过本模块直接读写 customers/follow_logs/business 等表，
所有写操作复用既有约束（owner_id 隔离、update_customer_last_follow 等）。
"""
import json
import os
import sqlite3
from datetime import datetime
from flask import request, jsonify, Response

from extensions import (
    get_db, token_required, record_operation_log, update_customer_last_follow, user_can, DB_PATH,
)
from qa_engine import (
    extract_write_intent, generate_visit_summary, generate_agent_reply,
)

from . import ai_agent_bp


# ==================== 1. 对话式录入主接口 ====================

@ai_agent_bp.route('/api/ai/agent', methods=['POST'])
@token_required
def ai_agent():
    """对话式录入主接口。

    请求体：
        text: 用户汇报文本
        confirm: bool，是否为用户确认后的二次执行（默认 False）
        entities: dict，confirm=True 时由前端回传最终确认的实体（覆盖 LLM 抽取）
        intent: str，confirm=True 时由前端回传最终意图

    返回：
        {
          intent, entities, status: 'executed'|'pending'|'failed'|'none',
          data: {...}, reply: "自然语言回复", error: "..."
        }
    """
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload.get('username', '')
    role = payload.get('role', '')

    text = (data.get('text') or data.get('question') or '').strip()
    if not text:
        return jsonify({'code': 400, 'message': '请输入汇报内容', 'data': None})

    confirm = bool(data.get('confirm', False))

    # 意图识别：确认态用前端回传，首态用 LLM 抽取
    if confirm:
        intent = data.get('intent', 'none')
        entities = data.get('entities', {}) or {}
    else:
        intent_result = extract_write_intent(text, username)
        intent = intent_result.get('intent', 'none')
        entities = intent_result.get('entities', {}) or {}
        confidence = intent_result.get('confidence', 0)

    # 查询意图：复用 misc.py 的 LLM 问答流程（非流式）
    if intent == 'query':
        try:
            from .misc import process_question_llm
            db = get_db()
            cursor = db.cursor()
            answer = process_question_llm(text, cursor, username, stream=False)
            if not isinstance(answer, str):
                answer = '抱歉，暂时无法回答该问题。'
        except Exception as e:
            answer = f'查询失败：{e}'
        return jsonify({
            'code': 200, 'message': 'success',
            'data': {
                'intent': 'query', 'entities': entities,
                'status': 'executed', 'data': {'answer': answer},
                'reply': answer,
            }
        })

    if intent == 'none':
        reply = generate_agent_reply('none', False, {}, error='未能识别您的操作意图，请尝试描述具体的拜访、跟进或商机进展。')
        return jsonify({
            'code': 200, 'message': 'success',
            'data': {'intent': 'none', 'entities': entities, 'status': 'none', 'data': {}, 'reply': reply}
        })

    db = get_db()
    cursor = db.cursor()

    # 分发到具体执行器
    try:
        if intent == 'create_follow_log':
            result = _exec_create_follow_log(cursor, entities, username, role, text, confirm)
        elif intent == 'create_customer':
            result = _exec_create_customer(cursor, entities, username, text, confirm)
        elif intent == 'update_business':
            result = _exec_update_business(cursor, entities, username, role, text, confirm)
        else:
            result = {'status': 'none', 'data': {}, 'error': '不支持的意图'}

        executed = result.get('status') == 'executed'
        if executed:
            db.commit()
            record_operation_log(username, 'AI智能体', '对话录入',
                                 f'意图:{intent} 内容:{text[:80]}')
        else:
            db.rollback()

        reply = generate_agent_reply(intent, executed, result.get('data', {}),
                                     error=result.get('error'))
        result['reply'] = reply
        return jsonify({'code': 200, 'message': 'success',
                        'data': {'intent': intent, 'entities': entities, **result}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': f'智能体执行异常: {e}', 'data': None})


def _match_customer(cursor, customer_name, username, role):
    """按公司名/客户名模糊匹配客户，返回 (cust_id, status, matches)。

    status: 'unique' 唯一匹配 / 'ambiguous' 多个 / 'none' 未找到
    """
    if not customer_name:
        return None, 'none', []
    kw = f'%{customer_name}%'
    if user_can(username, 'data.view_all'):
        cursor.execute(
            "SELECT id, name, company FROM customers WHERE company LIKE ? OR name LIKE ? ORDER BY id",
            (kw, kw))
    else:
        cursor.execute(
            "SELECT id, name, company FROM customers WHERE owner_id = ? AND (company LIKE ? OR name LIKE ?) ORDER BY id",
            (username, kw, kw))
    rows = [dict(r) for r in cursor.fetchall()]
    if len(rows) == 1:
        return rows[0]['id'], 'unique', rows
    if len(rows) > 1:
        return None, 'ambiguous', rows
    return None, 'none', []


def _exec_create_follow_log(cursor, entities, username, role, text, confirm):
    """执行创建跟进记录。"""
    customer_name = entities.get('customer_name')
    cust_id = entities.get('cust_id')

    # 确认态：前端可能已选定 cust_id
    if not cust_id and customer_name:
        cust_id, status, matches = _match_customer(cursor, customer_name, username, role)
        if status != 'unique':
            return {
                'status': 'pending',
                'data': {'customer_name': customer_name, 'matched_customers': matches,
                         'pending_reason': '客户匹配不唯一，请选择目标客户'},
                'error': '客户匹配不唯一' if status == 'ambiguous' else '未找到匹配客户',
            }
    if not cust_id:
        return {
            'status': 'pending',
            'data': {'pending_reason': '未识别到客户信息，请补充客户名称'},
            'error': '缺少客户信息',
        }

    content = entities.get('content') or text
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
        INSERT INTO follow_logs (ref_type, ref_id, user_id, content, log_time,
                                 subject, participants, location, next_plan)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        'customer', cust_id, username, content, now,
        entities.get('subject'), entities.get('participants'),
        entities.get('location'), entities.get('next_plan'),
    ))
    new_id = cursor.lastrowid
    update_customer_last_follow(cust_id)

    # 取客户名用于回复
    cursor.execute("SELECT name, company FROM customers WHERE id=?", (cust_id,))
    c = cursor.fetchone()
    cust_label = (c['company'] or c['name']) if c else '客户'

    return {
        'status': 'executed',
        'data': {'id': new_id, 'cust_id': cust_id, 'customer_name': cust_label,
                 'content': content},
    }


def _exec_create_customer(cursor, entities, username, text, confirm):
    """执行新增客户。"""
    company = entities.get('customer_name') or entities.get('company')
    if not company:
        return {'status': 'pending',
                'data': {'pending_reason': '请提供客户公司名称'},
                'error': '缺少客户公司名'}
    name = entities.get('contact_name') or company
    cursor.execute("""
        INSERT INTO customers (name, company, phone, level, source, owner_id,
                               contact_name, email, industry, region, created_at, last_follow)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (
        name, company, entities.get('phone'), entities.get('level', 'C'),
        entities.get('source', '智能体录入'), username,
        entities.get('contact_name'), entities.get('email'),
        entities.get('industry'), entities.get('region'),
    ))
    new_id = cursor.lastrowid
    return {'status': 'executed',
            'data': {'id': new_id, 'customer_name': company, 'company': company}}


def _exec_update_business(cursor, entities, username, role, text, confirm):
    """执行更新商机（概率/阶段）。"""
    b_id = entities.get('business_id')
    business_title = entities.get('business_title')
    probability = entities.get('probability')
    stage = entities.get('stage')

    # 未指定 b_id 时按标题或客户商机匹配
    if not b_id:
        if business_title:
            kw = f'%{business_title}%'
            if user_can(username, 'data.view_all'):
                cursor.execute("SELECT id, title FROM business WHERE title LIKE ? AND status='active'", (kw,))
            else:
                cursor.execute("SELECT id, title FROM business WHERE owner_id=? AND title LIKE ? AND status='active'", (username, kw))
            rows = [dict(r) for r in cursor.fetchall()]
        else:
            # 按客户名匹配其名下商机
            customer_name = entities.get('customer_name')
            if customer_name:
                cust_id, cstatus, _ = _match_customer(cursor, customer_name, username, role)
                if cstatus == 'unique':
                    cursor.execute("SELECT id, title FROM business WHERE cust_id=? AND status='active'", (cust_id,))
                    rows = [dict(r) for r in cursor.fetchall()]
                else:
                    rows = []
            else:
                rows = []

        if len(rows) == 1:
            b_id = rows[0]['id']
            business_title = rows[0]['title']
        elif len(rows) > 1:
            return {'status': 'pending',
                    'data': {'matched_business': rows, 'pending_reason': '匹配到多个商机，请选择目标商机'},
                    'error': '商机匹配不唯一'}
        else:
            return {'status': 'pending',
                    'data': {'pending_reason': '未找到对应商机，请补充商机标题或客户名'},
                    'error': '未匹配到商机'}

    if probability is None and not stage:
        return {'status': 'pending',
                'data': {'business_id': b_id, 'pending_reason': '请明确要更新的概率或阶段'},
                'error': '缺少更新字段'}

    updates, params = [], []
    if probability is not None:
        try:
            prob_int = int(probability)
        except (TypeError, ValueError):
            prob_int = None
        if prob_int is not None and 0 <= prob_int <= 100:
            updates.append("probability=?")
            params.append(prob_int)
            # 概率→阶段联动（与漏斗分段一致）
            if not stage:
                stage = _prob_to_stage(prob_int)
    if stage:
        updates.append("stage=?")
        params.append(stage)
    if not updates:
        return {'status': 'failed', 'data': {}, 'error': '概率值非法'}

    params.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    params.append(b_id)
    cursor.execute(f"UPDATE business SET {', '.join(updates)}, updated_at=? WHERE id=?", params)

    return {'status': 'executed',
            'data': {'business_id': b_id, 'business_title': business_title,
                     'probability': probability, 'stage': stage}}


def _prob_to_stage(prob):
    """概率→阶段映射（与 reports.py STAGE_RANGES 一致）。"""
    if prob >= 100:
        return '销售实现'
    if prob >= 90:
        return '合同签订'
    if prob >= 80:
        return '商务谈判'
    if prob >= 60:
        return '方案确定'
    if prob >= 30:
        return '能力展示'
    return '引导需求'


# ==================== 2. 拜访复盘接口 ====================

@ai_agent_bp.route('/api/ai/visit-summary', methods=['POST'])
@token_required
def ai_visit_summary():
    """拜访复盘：基于拜访记录+客户+商机生成结构化摘要并沉淀至知识库。

    请求体：
        visit_id: int（必填）
        extra_text: str（可选，销售口述补充）
        save_to_knowledge: bool（默认 True，自动写入 knowledge_base）
    """
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload.get('username', '')

    visit_id = data.get('visit_id')
    if not visit_id:
        return jsonify({'code': 400, 'message': '缺少 visit_id', 'data': None})

    extra_text = data.get('extra_text', '')
    save = data.get('save_to_knowledge', True)

    db = get_db()
    cursor = db.cursor()

    # 拉取拜访记录
    cursor.execute("""
        SELECT v.*, c.name as customer_name, c.company as customer_company,
               c.contact_name, c.phone, c.industry, c.level
        FROM visits v
        LEFT JOIN customers c ON v.cust_id = c.id
        WHERE v.id = ?
    """, (visit_id,))
    vrow = cursor.fetchone()
    if not vrow:
        return jsonify({'code': 404, 'message': '拜访记录不存在', 'data': None})
    visit_data = dict(vrow)

    customer_data = {
        'company': visit_data.get('customer_company') or visit_data.get('customer_name'),
        'name': visit_data.get('contact_name') or visit_data.get('customer_name'),
        'industry': visit_data.get('industry'),
        'level': visit_data.get('level'),
    } if visit_data.get('cust_id') else None

    # 拉取关联商机
    business_data = []
    if visit_data.get('cust_id'):
        cursor.execute("""
            SELECT id, title, amount, probability, stage, predict_date
            FROM business WHERE cust_id=? AND status='active'
            ORDER BY amount DESC LIMIT 3
        """, (visit_data['cust_id'],))
        business_data = [dict(r) for r in cursor.fetchall()]

    # 生成结构化复盘
    summary = generate_visit_summary(visit_data, customer_data, business_data, extra_text)

    # 沉淀至知识库
    kb_id = None
    if save:
        try:
            cursor.execute("""
                INSERT INTO knowledge_base (title, content, category, cust_id, visit_id,
                                            owner_id, tags, summary, created_at)
                VALUES (?, ?, 'visit_summary', ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                summary.get('title', f'拜访复盘-{visit_id}'),
                json.dumps(summary, ensure_ascii=False),
                visit_data.get('cust_id'),
                visit_id,
                username,
                '拜访复盘,结构化摘要',
                summary.get('summary', ''),
            ))
            db.commit()
            kb_id = cursor.lastrowid
            record_operation_log(username, 'AI复盘', '知识库',
                                 f'生成拜访复盘 visit_id={visit_id} kb_id={kb_id}')
        except Exception as e:
            db.rollback()

    return jsonify({
        'code': 200, 'message': 'success',
        'data': {'summary': summary, 'knowledge_id': kb_id, 'visit_id': visit_id},
    })


# ==================== 3. 流式对话接口 ====================

@ai_agent_bp.route('/api/ai/agent/stream', methods=['POST'])
@token_required
def ai_agent_stream():
    """SSE 流式对话：用于查询意图的自然语言回答逐字输出。

    立即返回 SSE 连接，先发"思考中"消息，再异步处理查询。
    写操作意图快速识别后提示切换到对话录入模式。

    注意：SSE 流式响应会导致请求上下文在 generator 执行前被释放，
    因此需要创建独立的数据库连接（不依赖 Flask g 对象）。
    """
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload.get('username', '')
    text = (data.get('text') or data.get('question') or '').strip()
    if not text:
        return jsonify({'code': 400, 'message': '请输入内容', 'data': None})

    from config import USE_LLM

    def generate():
        # 创建独立的数据库连接（SSE 流式响应会释放请求上下文，不能用 get_db）
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        cursor = conn.cursor()

        try:
            # 先发一条"思考中"消息，让前端立即收到数据
            yield f"data: {json.dumps({'answer': '正在思考中...', 'type': 'status'}, ensure_ascii=False)}\n\n"

            # 1. 先用规则匹配快速识别写操作意图（不调 LLM，毫秒级响应）
            from qa_engine import _extract_write_intent_rule
            intent_result = _extract_write_intent_rule(text)
            intent = intent_result.get('intent', 'none')

            if intent in ('create_follow_log', 'create_customer', 'update_business'):
                action_label = {'create_follow_log': '跟进记录', 'create_customer': '新增客户',
                                'update_business': '商机更新'}[intent]
                hint = f'检测到您要进行「{action_label}」操作，已切换到对话录入模式，请在确认卡片中确认后执行。'
                yield f"data: {json.dumps({'answer': hint}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return

            # 2. 查询意图：处理问答
            if not USE_LLM:
                from .misc import process_question_rule
                answer = process_question_rule(text, cursor, payload)
                yield f"data: {json.dumps({'answer': answer}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return

            from .misc import process_question_llm_stream
            # process_question_llm_stream 是 generator，直接 yield 每一条 SSE 事件
            for event in process_question_llm_stream(text, cursor, username):
                yield event

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'answer': f'查询失败：{e}'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            # 确保关闭独立的数据库连接
            try:
                conn.close()
            except Exception:
                pass

    return Response(generate(), content_type='text/event-stream')


# ==================== 4. 智能线索评估与分配 ====================

@ai_agent_bp.route('/api/ai/leads/evaluate', methods=['POST'])
@token_required
def ai_leads_evaluate():
    """智能线索评估与精准分配。

    请求体：
        leads: list[{company, contact_name, phone, industry, region, source, remark}]
    返回：
        每条线索的意向分值（0-100）、评估理由、推荐分配销售
    """
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    if not user_can(payload['username'], 'data.view_all'):
        return jsonify({'code': 403, 'message': '仅主任/院长可使用线索评估', 'data': None})

    leads = data.get('leads', [])
    if not leads:
        return jsonify({'code': 400, 'message': '请提供线索数据', 'data': None})

    db = get_db()
    cursor = db.cursor()

    # 复用 leads 模块的销售画像加载与多维度分配逻辑
    # 综合考虑销售人员的历史拜访案例、商机情况、合同签订情况科学推荐负责人
    from .leads import _load_eval_context, _assign_lead
    industry_stats, salespeople = _load_eval_context(cursor)

    results = []
    for lead in leads:
        score, reason = _evaluate_lead_intent(lead, industry_stats)
        assignee = _assign_lead(lead, salespeople)
        results.append({
            'lead': lead,
            'intent_score': score,
            'reason': reason,
            'assigned_to': assignee,
        })

    record_operation_log(payload['username'], 'AI线索评估', '智能线索管理',
                         f'评估线索 {len(results)} 条')

    return jsonify({'code': 200, 'message': 'success', 'data': {'results': results}})


def _evaluate_lead_intent(lead, industry_stats):
    """结合历史数据评估线索意向分值（无 LLM 时使用规则评分）。"""
    score = 50
    reasons = []
    industry = (lead.get('industry') or '').strip()
    if industry and industry in industry_stats:
        score += min(20, industry_stats[industry] * 2)
        reasons.append(f'行业「{industry}」历史成交{industry_stats[industry]}单，意向较高')
    elif industry:
        reasons.append(f'行业「{industry}」历史成交较少，需进一步培育')
    # 来源信号
    source = (lead.get('source') or '').strip()
    source_bonus = {'主动咨询': 25, '老客户介绍': 20, '展会': 15, '官网': 10, '外部抓取': 5}
    if source in source_bonus:
        score += source_bonus[source]
        reasons.append(f'来源「{source}」为高价值渠道')
    # 备注关键词
    remark = (lead.get('remark') or '').strip()
    strong_kw = ['急需', '预算', '招标', '采购', '计划', '立项']
    if any(k in remark for k in strong_kw):
        score += 15
        reasons.append('备注含强意向关键词')
    score = max(0, min(100, score))
    if not reasons:
        reasons.append('信息有限，建议人工跟进核实')
    return score, '；'.join(reasons)


def _assign_salesperson(lead, salespeople):
    """[已废弃] 旧版仅按工作量分配；新逻辑请使用 leads._assign_lead。

    保留函数签名仅为向后兼容，实际逻辑已委托给 leads 模块的多维度评分推荐：
    综合销售人员的历史拜访案例、商机情况、合同签订情况科学推荐负责人。
    """
    if not salespeople:
        return None
    return {
        'username': salespeople[0]['username'],
        'name': salespeople[0]['name'],
        'reason': f'当前商机数最少（{salespeople[0].get("biz_count", 0)}单），工作量最均衡',
    }


def register_routes(app):
    app.register_blueprint(ai_agent_bp)
