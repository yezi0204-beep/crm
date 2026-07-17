import json
import requests
from config import LLM_API_KEY, LLM_API_BASE, LLM_MODEL, USE_LLM, SYSTEM_PROMPT


def call_llm(messages, stream=False):
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
        'temperature': 0.3,
        'stream': stream
    }
    
    try:
        print(f"[LLM Debug] Calling API: {LLM_API_BASE}/chat/completions")
        print(f"[LLM Debug] Model: {LLM_MODEL}")
        response = requests.post(
            f'{LLM_API_BASE}/chat/completions',
            headers=headers,
            json=payload,
            stream=stream,
            timeout=30
        )
        
        print(f"[LLM Debug] Response status: {response.status_code}")
        
        if response.status_code == 200:
            if stream:
                return response.iter_lines()
            else:
                data = response.json()
                content = data['choices'][0]['message']['content']
                print(f"[LLM Debug] Response content: {content[:200]}...")
                return content
        else:
            print(f"[LLM Debug] API Error: {response.status_code} - {response.text[:500]}")
            return None
    except Exception as e:
        print(f"[LLM Debug] API Exception: {e}")
        import traceback
        traceback.print_exc()
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