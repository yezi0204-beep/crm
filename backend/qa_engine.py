import json
import re
import requests
from config import LLM_API_KEY, LLM_API_BASE, LLM_MODEL, USE_LLM, SYSTEM_PROMPT


def call_llm(messages, stream=False, max_tokens=18000, timeout=360, enable_thinking=False):
    """调用 LLM API。

    Args:
        enable_thinking: 是否开启思考模式。默认 False（关闭），大幅减少响应时间。
        max_tokens: 最大输出 token 数。关闭思考时 4000 足够。
        timeout: HTTP 超时秒数。关闭思考时 60-120 秒即可。
    """
    if not USE_LLM or not LLM_API_KEY:
        print(f"[LLM Debug] LLM not enabled. USE_LLM={USE_LLM}, API_KEY set={bool(LLM_API_KEY)}")
        return None

    headers = {
        'Authorization': f'Bearer {LLM_API_KEY}',
        'Content-Type': 'application/json'
    }

    payload = {
        'model': LLM_MODEL,
        'messages': messages,
        'temperature': 0.1,
        'stream': stream,
        'max_tokens': max_tokens,
    }
    # vLLM / Qwen3.5：通过 chat_template_kwargs 关闭思考模式
    if not enable_thinking:
        payload['chat_template_kwargs'] = {'enable_thinking': False}

    try:
        print(f"[LLM Debug] Calling API: {LLM_API_BASE}/chat/completions (max_tokens={max_tokens}, thinking={enable_thinking})")
        response = requests.post(
            f'{LLM_API_BASE}/chat/completions',
            headers=headers,
            json=payload,
            stream=stream,
            timeout=timeout
        )

        print(f"[LLM Debug] Response status: {response.status_code}")

        if response.status_code == 200:
            if stream:
                return response.iter_lines()
            else:
                data = response.json()
                msg = data['choices'][0]['message']
                content = msg.get('content')
                reasoning = msg.get('reasoning', '')
                if content:
                    pass  # 正常情况
                elif reasoning:
                    # 思考模型且 max_tokens 不够时 content 为 null
                    print(f"[LLM Debug] content is null, reasoning length={len(reasoning)}")
                    extracted = _extract_json_from_text(reasoning)
                    if extracted:
                        content = extracted
                    else:
                        print("[LLM Debug] Cannot extract JSON from reasoning, returning None for fallback")
                        return None
                else:
                    print("[LLM Debug] Both content and reasoning are empty/null")
                    return None
                print(f"[LLM Debug] Response ({len(content)} chars): {content[:200]}...")
                return content
        else:
            print(f"[LLM Debug] API Error: {response.status_code} - {response.text[:500]}")
            return None
    except Exception as e:
        print(f"[LLM Debug] API Exception: {e}")
        import traceback
        traceback.print_exc()
        return None


def _extract_json_from_text(text):
    """从 LLM 输出文本中提取 JSON 数组（容错处理）。

    优先从文本末尾（LLM 实际输出位置）向前查找 JSON，避免在思考过程中误匹配。
    """
    if not text:
        return None
    text = text.strip()
    # 尝试找 ```json ... ```
    m = re.search(r'```json\s*\n?(.*?)```', text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # 从末尾向前找 [ ... ] 区间（优先找 LLM 最终输出的 JSON，而非思考过程中的片段）
    end = text.rfind(']')
    if end < 0:
        return None
    # 从 ] 向前最多搜索 2000 字符，找匹配的 [
    search_start = max(0, end - 2000)
    start = text.find('[', search_start, end)
    if start >= 0:
        return text[start:end + 1]
    # 兜底：全文搜索
    start = text.find('[')
    if start >= 0 and end > start:
        return text[start:end + 1]
    return None


def extract_query_function(question):
    if not USE_LLM:
        return None
    
    prompt = f"""
你是一个函数选择专家。请分析用户问题，从以下函数中选择最合适的一个：

函数映射表：
1. get_contracts_near_expiry → 合同到期、回款到期、快到期了、即将到期、哪个合同快到期
2. get_top_pending_customer → 待回款最多的客户、哪个客户待回款最高、客户回款排名
3. get_top_pending_contract → 待回款最多的合同、哪个合同待回款最高、合同回款排名
4. get_business_to_follow → 需要跟进的商机、商机跟进、跟进记录、待跟进
5. get_my_customer_count → 我有多少客户、我的客户数量、我负责的客户数
6. get_top_contract_by_amount → 合同金额最高、最大合同、哪个合同金额最大
7. get_business_count → 商机总数、有多少商机、商机数量
8. get_total_payments → 回款总额、累计回款、总共回款多少
9. get_total_pending → 待回款总额、所有待回款、总待回款
10. get_weekly_plan → 本周工作计划、本周工作安排、这周计划
11. get_next_week_plan → 下周工作计划、下周工作安排、下周计划

用户问题：{question}

请直接返回函数名称，不要包含任何其他文字。如果无法匹配，返回"none"。
"""
    
    messages = [
        {'role': 'system', 'content': '你是一个精确的函数选择器，必须从给定列表中选择一个函数名。'},
        {'role': 'user', 'content': prompt}
    ]
    
    result = call_llm(messages)
    if result:
        func_name = result.strip()
        valid_funcs = [
            'get_contracts_near_expiry', 'get_top_pending_customer', 
            'get_top_pending_contract', 'get_business_to_follow',
            'get_my_customer_count', 'get_top_contract_by_amount',
            'get_business_count', 'get_total_payments', 'get_total_pending',
            'get_weekly_plan', 'get_next_week_plan', 'none'
        ]
        for valid in valid_funcs:
            if valid in func_name:
                return valid
        return 'none'
    return None


def generate_answer(question, data_context, username):
    if not USE_LLM:
        return None
    
    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': f"""
用户问题：{question}

查询到的数据：
{data_context}

用户信息：{username}

请根据以上数据，用自然、友好的语言回答用户的问题。
"""}
    ]
    
    return call_llm(messages)


def generate_answer_stream(question, data_context, username):
    if not USE_LLM:
        return None

    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': f"""
用户问题：{question}

查询到的数据：
{data_context}

用户信息：{username}

请根据以上数据，用自然、友好的语言回答用户的问题。
"""}
    ]

    return call_llm(messages, stream=True)


# ==================== AI 智能体扩展：写操作意图识别 + 复盘生成 ====================

WRITE_INTENT_PROMPT = """你是一个 CRM 智能体的意图识别器。分析用户的汇报文本，识别写操作意图并提取实体。

意图类型（intent）：
1. create_follow_log - 用户汇报了客户拜访、跟进、沟通情况（关键词：拜访/跟进/沟通/见面/联系了/谈了/汇报）
2. create_customer - 用户要新增客户（关键词：新增客户/录入客户/添加客户/新建客户）
3. update_business - 用户要更新商机状态/概率/阶段（关键词：商机/概率/阶段/成交/签约/推进）
4. query - 用户在查询数据（关键词：多少/有哪些/查询/统计/列表/排名）
5. none - 无法识别

实体提取规则（entities 对象，仅提取文本中明确出现的字段，未提及的字段不要编造）：
- customer_name: 客户公司名（如"江阴科技"、"华为"）
- content: 跟进/拜访内容描述
- next_plan: 下一步计划
- subject: 跟进主题
- participants: 参与人员
- location: 地点
- amount: 商机金额（数字，单位万元）
- probability: 商机概率（0-100 整数）
- stage: 商机阶段（引导需求/能力展示/方案确定/商务谈判/合同签订/销售实现）
- predict_date: 预计成交日期（YYYY-MM 格式）
- business_title: 商机标题

输出严格的 JSON 格式（不要 markdown 代码块，不要多余文字）：
{"intent": "create_follow_log", "entities": {"customer_name": "江阴科技", "content": "客户对方案满意", "next_plan": "下周提供报价", "probability": 60, "stage": "方案确定"}, "confidence": 0.85}"""


def extract_write_intent(question, username=None):
    """识别用户汇报中的写操作意图，返回结构化 dict。

    LLM 可用时：使用 function call 模式输出 JSON
    LLM 不可用时：降级为关键词规则匹配
    """
    if not USE_LLM:
        return _extract_write_intent_rule(question)

    messages = [
        {'role': 'system', 'content': '你是一个精确的 CRM 意图识别器，必须输出严格 JSON。'},
        {'role': 'user', 'content': f"用户汇报：{question}\n\n{WRITE_INTENT_PROMPT}"}
    ]

    result = call_llm(messages)
    if not result:
        return _extract_write_intent_rule(question)

    try:
        # 清理可能的 markdown 代码块
        cleaned = result.strip()
        if cleaned.startswith('```'):
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
            cleaned = re.sub(r'\s*```$', '', cleaned)
        data = json.loads(cleaned)
        # 校验 intent 合法性
        valid_intents = ['create_follow_log', 'create_customer', 'update_business', 'query', 'none']
        if data.get('intent') not in valid_intents:
            data['intent'] = 'none'
        if 'entities' not in data:
            data['entities'] = {}
        if 'confidence' not in data:
            data['confidence'] = 0.5
        return data
    except (json.JSONDecodeError, KeyError) as e:
        print(f"[WriteIntent Debug] JSON parse failed: {e}, raw: {result[:200]}")
        return _extract_write_intent_rule(question)


def _extract_write_intent_rule(question):
    """无 LLM 时的降级规则匹配。"""
    q = question.lower()
    entities = {}

    # 提取客户名（启发式：xx公司/xx科技/xx集团）
    company_match = re.search(r'([\u4e00-\u9fa5]{2,8}(?:公司|科技|集团|有限|研究院|中心))', question)
    if company_match:
        entities['customer_name'] = company_match.group(1)

    # 提取概率
    prob_match = re.search(r'概率[^\d]*(\d{1,3})\s*%', question)
    if prob_match:
        entities['probability'] = int(prob_match.group(1))

    # 提取金额
    amt_match = re.search(r'(\d+(?:\.\d+)?)\s*万', question)
    if amt_match:
        entities['amount'] = float(amt_match.group(1))

    # 阶段
    stage_map = ['引导需求', '能力展示', '方案确定', '商务谈判', '合同签订', '销售实现']
    for s in stage_map:
        if s in question:
            entities['stage'] = s
            break

    # 意图判断
    if any(k in question for k in ['新增客户', '录入客户', '添加客户', '新建客户']):
        return {'intent': 'create_customer', 'entities': entities, 'confidence': 0.7}
    if any(k in question for k in ['商机', '概率', '阶段']) and any(k in question for k in ['提升', '更新', '进入', '推进', '改为', '调整']):
        return {'intent': 'update_business', 'entities': entities, 'confidence': 0.7}
    if any(k in question for k in ['拜访', '跟进', '沟通', '见面', '联系了', '谈了', '汇报']):
        entities['content'] = question
        return {'intent': 'create_follow_log', 'entities': entities, 'confidence': 0.7}
    if any(k in question for k in ['多少', '有哪些', '查询', '统计', '列表', '排名']):
        return {'intent': 'query', 'entities': {}, 'confidence': 0.6}

    return {'intent': 'none', 'entities': {}, 'confidence': 0.3}


VISIT_SUMMARY_PROMPT = """你是一个 CRM 销售复盘专家。基于拜访记录、客户信息和关联商机，生成结构化复盘摘要。

输出严格的 JSON 格式（不要 markdown 代码块）：
{
  "title": "客户公司名+拜访复盘+日期",
  "summary": "一句话概括本次拜访核心结论（30-50字）",
  "key_findings": ["关键发现1", "关键发现2", "关键发现3"],
  "customer_needs": ["客户需求1", "客户需求2"],
  "next_actions": ["下一步行动1", "下一步行动2"],
  "risk_warnings": ["风险提示1"],
  "deal_signals": "成交信号评估（强/中/弱/无，附简短理由）"
}

要求：
- 基于提供的数据客观分析，不要编造未提及的信息
- key_findings 提炼 2-4 条最有价值的发现
- next_actions 必须具体可执行（含时间节点、负责人暗示）
- 若数据不足以支撑某字段，返回空数组或"数据不足"
- 用中文输出"""


def generate_visit_summary(visit_data, customer_data=None, business_data=None, extra_text=None):
    """基于拜访记录+客户信息+关联商机生成结构化复盘摘要。

    LLM 可用时：调用 LLM 生成结构化 JSON
    LLM 不可用时：降级为模板拼接
    """
    # 拼接上下文
    context_parts = []
    if visit_data:
        context_parts.append(f"拜访记录：目的={visit_data.get('purpose', '-')}, 结果={visit_data.get('result', '-')}, 日期={visit_data.get('plan_date', '-')}, 地点={visit_data.get('location', '-')}, 联系人={visit_data.get('contact_person', '-')}")
    if customer_data:
        context_parts.append(f"客户信息：公司={customer_data.get('company', '-')}, 联系人={customer_data.get('name', '-')}, 行业={customer_data.get('industry', '-')}, 级别={customer_data.get('level', '-')}")
    if business_data:
        biz_list = business_data if isinstance(business_data, list) else [business_data]
        for b in biz_list[:3]:
            context_parts.append(f"关联商机：{b.get('title', '-')}, 金额={b.get('amount', 0)/10000:.1f}万, 概率={b.get('probability', 0)}%, 阶段={b.get('stage', '-')}")
    if extra_text:
        context_parts.append(f"补充口述：{extra_text}")

    context = "\n".join(context_parts)

    if not USE_LLM:
        return _generate_visit_summary_template(visit_data, customer_data, extra_text)

    messages = [
        {'role': 'system', 'content': '你是一个专业的销售复盘助手，必须输出严格 JSON。'},
        {'role': 'user', 'content': f"{context}\n\n{VISIT_SUMMARY_PROMPT}"}
    ]

    result = call_llm(messages)
    if not result:
        return _generate_visit_summary_template(visit_data, customer_data, extra_text)

    try:
        cleaned = result.strip()
        if cleaned.startswith('```'):
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
            cleaned = re.sub(r'\s*```$', '', cleaned)
        data = json.loads(cleaned)
        # 确保必要字段存在
        required = ['title', 'summary', 'key_findings', 'customer_needs', 'next_actions', 'risk_warnings', 'deal_signals']
        for k in required:
            if k not in data:
                data[k] = [] if k in ['key_findings', 'customer_needs', 'next_actions', 'risk_warnings'] else ''
        return data
    except (json.JSONDecodeError, KeyError) as e:
        print(f"[VisitSummary Debug] JSON parse failed: {e}, raw: {result[:200]}")
        return _generate_visit_summary_template(visit_data, customer_data, extra_text)


def _generate_visit_summary_template(visit_data, customer_data=None, extra_text=None):
    """无 LLM 时的降级模板拼接。"""
    company = (customer_data or {}).get('company', '客户')
    plan_date = (visit_data or {}).get('plan_date', '')
    purpose = (visit_data or {}).get('purpose', '')
    result = (visit_data or {}).get('result', '')
    date_str = plan_date.replace('-', '') if plan_date else ''

    title = f"{company}拜访复盘-{date_str}"
    summary = f"本次拜访{company}，目的：{purpose or '未明确'}；结果：{result or '未记录'}"
    if extra_text:
        summary += f"。补充：{extra_text}"

    key_findings = [f"拜访目的：{purpose}"] if purpose else []
    if result:
        key_findings.append(f"拜访结果：{result}")
    if extra_text:
        key_findings.append(f"补充说明：{extra_text}")

    return {
        'title': title,
        'summary': summary,
        'key_findings': key_findings,
        'customer_needs': [],
        'next_actions': [],
        'risk_warnings': [],
        'deal_signals': '数据不足，需补充更多信息',
        '_fallback': True  # 标记为降级模板
    }


def generate_agent_reply(intent, executed, data, error=None):
    """生成 AI 智能体的自然语言回复。

    LLM 可用时：基于执行结果生成友好回复
    LLM 不可用时：使用固定模板
    """
    if not USE_LLM:
        return _generate_agent_reply_template(intent, executed, data, error)

    status = "成功" if executed else "失败"
    context = f"意图：{intent}\n执行状态：{status}\n数据：{json.dumps(data, ensure_ascii=False, default=str)}"
    if error:
        context += f"\n错误：{error}"

    messages = [
        {'role': 'system', 'content': '你是 CRM 智能体，用简洁友好的中文回复用户（30-80字），告知操作结果。'},
        {'role': 'user', 'content': context}
    ]
    reply = call_llm(messages)
    return reply or _generate_agent_reply_template(intent, executed, data, error)


def _generate_agent_reply_template(intent, executed, data, error=None):
    """智能体回复模板（降级）。"""
    if not executed:
        return f"抱歉，操作未能完成：{error or '未知原因'}"

    if intent == 'create_follow_log':
        cust = data.get('customer_name', '客户')
        return f"已为您记录本次对「{cust}」的跟进，客户最后跟进时间已更新。"
    if intent == 'create_customer':
        cust = data.get('customer_name', data.get('company', '新客户'))
        return f"已成功创建客户「{cust}」，您可以在客户管理中查看。"
    if intent == 'update_business':
        title = data.get('business_title', '商机')
        prob = data.get('probability')
        stage = data.get('stage')
        parts = [f"已更新商机「{title}」"]
        if prob is not None:
            parts.append(f"概率调整为 {prob}%")
        if stage:
            parts.append(f"阶段调整为「{stage}」")
        return "，".join(parts) + "。"
    if intent == 'query':
        return "已为您查询相关数据。"
    return "操作已完成。"