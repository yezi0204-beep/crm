"""AI 文档分析引擎 - 为知识库文档提供智能分析。

核心功能：
1. 拜访纪要分析 - 提取关键发现、客户需求、下一步行动、风险提示
2. 合同分析 - 提取关键条款、履约风险、回款节点
3. 投标文件分析 - 提取资质要求、评分要点、竞争态势
4. 技术方案分析 - 提取技术亮点、方案要点、交付物
5. 通用分析 - 自动摘要、关键词提取、情感判断

支持两种模式：
- LLM 模式：调用大模型进行智能分析
- 规则模式：基于关键词和规则的结构化分析
"""
import json
import re
from datetime import datetime

from config import LLM_API_KEY, LLM_API_BASE, LLM_MODEL, USE_LLM


ANALYSIS_PROMPT = """你是一名资深的企业销售分析师。请分析以下{doc_type}的内容，提取关键信息并以JSON格式返回。

文档标题：{title}
文档内容：
{content}

请以JSON格式返回以下结构（如果某项没有内容请返回空数组或空字符串）：
{{
  "summary": "2-3句话的摘要",
  "key_findings": ["关键发现1", "关键发现2", "关键发现3"],
  "customer_needs": ["客户需求1", "客户需求2"],
  "next_actions": ["下一步行动1", "下一步行动2", "下一步行动3"],
  "risks": ["风险点1", "风险点2"],
  "opportunities": ["机会点1", "机会点2"],
  "sentiment": "positive/neutral/negative",
  "tags": ["自动标签1", "自动标签2", "自动标签3"]
}}

注意：
- key_findings是文档中最重要的发现或信息
- customer_needs是客户明确表达的需求
- next_actions是建议的下一步跟进动作（要具体可执行）
- risks是潜在风险或需要注意的问题
- opportunities是可利用的机会
- sentiment是对整体氛围的判断
- tags是3个能代表文档主题的关键词
"""


DOC_TYPE_CN = {
    'visit_summary': '拜访纪要',
    'contract': '合同',
    'bid_document': '投标文件',
    'technical_plan': '技术方案',
    'personnel_qualification': '人员资质',
    'company_qualification': '企业资质',
    'customer_info': '客户资料',
    'industry_report': '行业报告',
    'meeting_minutes': '会议纪要',
    'other': '文档'
}


def analyze_document_llm(title, content, doc_type='other'):
    """调用LLM分析文档内容。

    针对Qwen3等reasoning模型做了容错：
    - reasoning模型可能将token全部用于思考，导致content为None
    - 超时控制在120秒（2分钟），给reasoning模型充分思考时间
    - content为空时降级到规则模式
    """
    if not content or not content.strip():
        return None

    doc_type_cn = DOC_TYPE_CN.get(doc_type, '文档')
    prompt = ANALYSIS_PROMPT.format(
        doc_type=doc_type_cn,
        title=title or '未命名',
        content=content[:6000]
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
                {'role': 'system', 'content': '你是专业的企业销售分析师。请严格按照JSON格式返回分析结果，不要添加任何额外文字，不要输出思考过程。'},
                {'role': 'user', 'content': prompt}
            ],
            'temperature': 0.3,
            # Qwen reasoning模型会先消耗token做思考，需要更大的额度才能输出content
            'max_tokens': 4000
        }
        # 部分vLLM部署的Qwen3支持通过extra_body禁用thinking以加速响应
        try:
            payload['extra_body'] = {'chat_template_kwargs': {'enable_thinking': False}}
        except Exception:
            pass

        response = requests.post(
            f'{LLM_API_BASE}/chat/completions',
            headers=headers,
            json=payload,
            timeout=120
        )
        if response.status_code == 200:
            data = response.json()
            message = data['choices'][0]['message']
            raw_text = message.get('content')
            # Qwen reasoning模型：content可能为None（token全被reasoning占用）
            if not raw_text or not raw_text.strip():
                print(f"[AIAnalyzer] LLM returned empty content (reasoning model token exhausted), falling back to rules")
                return None
            # 提取JSON
            json_match = re.search(r'\{[\s\S]*\}', raw_text)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError as je:
                    print(f"[AIAnalyzer] LLM JSON parse failed: {je}")
            else:
                print(f"[AIAnalyzer] LLM response has no JSON block, raw: {raw_text[:200]}")
        else:
            print(f"[AIAnalyzer] LLM HTTP {response.status_code}: {response.text[:200]}")
    except Exception as e:
        print(f"[AIAnalyzer] LLM analysis failed: {e}")

    return None


def analyze_document_rules(title, content, doc_type='other'):
    """基于规则的文档分析（LLM不可用时的降级方案）。"""
    if not content:
        return None

    text = content.strip()
    results = {
        'summary': '',
        'key_findings': [],
        'customer_needs': [],
        'next_actions': [],
        'risks': [],
        'opportunities': [],
        'sentiment': 'neutral',
        'tags': []
    }

    sentences = [s.strip() for s in re.split(r'[。！？\n]+', text) if s.strip()]

    # 摘要：取前3句
    results['summary'] = '。'.join(sentences[:3])[:200] if sentences else (title or '')

    # 关键词提取（简单词频）
    word_freq = {}
    stop_words = set('的了在是我有和就不人都一上也很到说要去你会着没有看好自己这那但还把被从与对为及等或如果因为所以我们你们他们它们这个那个一种一些什么怎么如何可以可能应该需要必须非常重要关键问题关注要求希望期望询问咨询讨论沟通反馈意见建议计划安排目标进展情况时间地点人物金额数量价格质量服务产品技术方案系统功能性能效果'.split())
    for sentence in sentences:
        for word in re.findall(r'[\u4e00-\u9fff]{2,4}', sentence):
            if word not in stop_words:
                word_freq[word] = word_freq.get(word, 0) + 1
    top_words = sorted(word_freq.items(), key=lambda x: -x[1])[:8]
    results['tags'] = [w for w, _ in top_words[:3]]

    # 规则分析
    if doc_type == 'visit_summary':
        # 拜访纪要分析
        for s in sentences:
            if any(w in s for w in ['客户', '公司', '对方', '领导', '负责人', '联系人']):
                if any(w in s for w in ['需求', '希望', '要求', '需要', '想要', '计划', '打算']):
                    results['customer_needs'].append(s[:80])
                elif any(w in s for w in ['关注', '关心', '在意', '重视', '提到', '谈到', '反馈']):
                    results['key_findings'].append(s[:80])

            if any(w in s for w in ['问题', '痛点', '困难', '挑战', '担心', '顾虑', '风险', '麻烦']):
                results['risks'].append(s[:80])

            if any(w in s for w in ['跟进', '下一步', '后续', '下次', '安排', '计划', '动作', '措施', '方案']):
                results['next_actions'].append(s[:80])

            if any(w in s for w in ['合作', '签约', '成交', '机会', '可能', '意向', '感兴趣', '考虑']):
                results['opportunities'].append(s[:80])

    elif doc_type == 'contract':
        for s in sentences:
            if any(w in s for w in ['金额', '价格', '费用', '款项', '总额', '合计']):
                results['key_findings'].append(s[:80])
            if any(w in s for w in ['违约', '风险', '赔偿', '责任', '限制']):
                results['risks'].append(s[:80])
            if any(w in s for w in ['交付', '验收', '付款', '回款', '结算']):
                results['next_actions'].append(s[:80])

    elif doc_type == 'bid_document':
        for s in sentences:
            if any(w in s for w in ['资质', '要求', '条件', '标准', '资格']):
                results['key_findings'].append(s[:80])
            if any(w in s for w in ['评分', '得分', '评标', '打分', '评审']):
                results['key_findings'].append(s[:80])
            if any(w in s for w in ['风险', '不利', '弱点', '缺失']):
                results['risks'].append(s[:80])

    elif doc_type == 'technical_plan':
        for s in sentences:
            if any(w in s for w in ['技术', '架构', '方案', '系统', '平台', '模块']):
                results['key_findings'].append(s[:80])
            if any(w in s for w in ['优势', '亮点', '创新', '特点', '特色']):
                results['opportunities'].append(s[:80])
            if any(w in s for w in ['实施', '部署', '交付', '计划', '进度']):
                results['next_actions'].append(s[:80])

    else:
        # 通用分析
        for s in sentences:
            if any(w in s for w in ['重要', '关键', '核心', '重点', '主要']):
                results['key_findings'].append(s[:80])
            if any(w in s for w in ['问题', '风险', '困难', '挑战']):
                results['risks'].append(s[:80])

    # 情感判断
    positive_words = ['好', '棒', '成功', '满意', '喜欢', '支持', '同意', '合作', '签约', '成交', '进展顺利']
    negative_words = ['差', '失败', '问题', '担心', '顾虑', '困难', '反对', '拒绝', '延迟', '超期', '风险']
    pos_count = sum(1 for s in sentences for w in positive_words if w in s)
    neg_count = sum(1 for s in sentences for w in negative_words if w in s)
    if pos_count > neg_count * 1.5:
        results['sentiment'] = 'positive'
    elif neg_count > pos_count * 1.5:
        results['sentiment'] = 'negative'
    else:
        results['sentiment'] = 'neutral'

    # 去重并限制数量
    for key in ['key_findings', 'customer_needs', 'next_actions', 'risks', 'opportunities']:
        seen = set()
        unique = []
        for item in results[key]:
            if item and item not in seen:
                seen.add(item)
                unique.append(item)
        results[key] = unique[:5]

    # 如果关键发现为空，用摘要前两句补充
    if not results['key_findings'] and sentences:
        results['key_findings'] = [s[:80] for s in sentences[:2]]

    return results


def analyze_document(title, content, doc_type='other'):
    """分析文档内容，优先使用LLM，失败时降级到规则模式。"""
    if not content or not content.strip():
        return None

    # 优先尝试LLM
    if USE_LLM and LLM_API_KEY:
        result = analyze_document_llm(title, content, doc_type)
        if result:
            result['analysis_method'] = 'llm'
            result['analyzed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            return result

    # 降级到规则模式
    result = analyze_document_rules(title, content, doc_type)
    if result:
        result['analysis_method'] = 'rules'
        result['analyzed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return result

    return None


def batch_analyze(documents):
    """批量分析文档列表。documents: [{id, title, content, doc_type}, ...]"""
    results = []
    for doc in documents:
        result = analyze_document(
            doc.get('title', ''),
            doc.get('content', ''),
            doc.get('doc_type', 'other')
        )
        results.append({
            'id': doc.get('id'),
            'analysis': result
        })
    return results
