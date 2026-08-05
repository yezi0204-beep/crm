"""智能体增强模块 - 基于知识库的智能推荐与评估

核心能力：
1. 商机负责人推荐 - 基于行业经验、历史业绩、客户关系的智能匹配
2. 商机跟踪策略 - 基于知识库的个性化跟进建议
3. 投标打分评估 - 多维度综合评分与竞争力分析
"""
import json
from datetime import datetime

from flask import request, jsonify

from extensions import get_db, token_required, record_operation_log
from vector_search import semantic_search, hybrid_search
from qa_engine import call_llm

from config import USE_LLM

from . import agent_agent_bp


@agent_agent_bp.route('/api/agent/recommend-owner', methods=['POST'])
@token_required
def recommend_owner():
    """商机负责人智能推荐。

    基于客户行业、商机特点、人员历史业绩和知识库匹配度，
    推荐最合适的商机负责人。

    请求体：
        customer_id: 客户ID
        business_id: 商机ID（可选）
        business_title: 商机标题
        industry: 行业
        amount: 金额
        requirements: 特殊要求（如资质、经验等）
    """
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload.get('username', '')

    customer_id = data.get('customer_id')
    business_id = data.get('business_id')
    business_title = data.get('business_title', '')
    industry = data.get('industry', '')
    amount = data.get('amount', 0)
    requirements = data.get('requirements', '')

    db = get_db()
    cursor = db.cursor()

    candidate_scores = {}

    cursor.execute("""
        SELECT u.username, u.name, u.role, u.department,
               COUNT(b.id) as total_business,
               SUM(CASE WHEN b.probability >= 60 THEN 1 ELSE 0 END) as successful_deals,
               COALESCE(SUM(b.amount), 0) as total_amount
        FROM users u
        LEFT JOIN business b ON b.owner_id = u.username AND b.status = 'active'
        WHERE u.status = '在职' AND u.role IN ('销售', '主任', '院长')
        GROUP BY u.username, u.name, u.role, u.department
        ORDER BY total_amount DESC
    """)
    sales_stats = {row['username']: dict(row) for row in cursor.fetchall()}

    cursor.execute("""
        SELECT p.username, GROUP_CONCAT(p.qualification_type || ':' || p.level, ', ') as qualifications
        FROM personnel_qualifications p
        WHERE p.status = '有效'
        GROUP BY p.username
    """)
    qualifications = {}
    for row in cursor.fetchall():
        qualifications[row['username']] = row['qualifications']

    cursor.execute("""
        SELECT username, industry, COUNT(*) as industry_count
        FROM business
        WHERE status = 'active' AND industry IS NOT NULL AND industry != ''
        GROUP BY username, industry
    """)
    industry_experience = {}
    for row in cursor.fetchall():
        user = row['username']
        if user not in industry_experience:
            industry_experience[user] = {}
        industry_experience[user][row['industry']] = row['industry_count']

    query_text = f"商机：{business_title}，行业：{industry}，金额：{amount}万，要求：{requirements}"
    knowledge_matches = semantic_search(query_text, doc_type='business', top_k=5)

    matched_owners = set()
    for match in knowledge_matches:
        doc_id = match.get('doc_id')
        cursor.execute("""
            SELECT owner_id FROM knowledge_documents WHERE id = ? AND owner_id IS NOT NULL
        """, (doc_id,))
        owner_row = cursor.fetchone()
        if owner_row:
            matched_owners.add(owner_row['owner_id'])

    for user, stats in sales_stats.items():
        score = 0.0
        reasons = []

        total_business = stats['total_business'] or 0
        if total_business > 0:
            success_rate = (stats['successful_deals'] or 0) / total_business * 100
            score += min(30, success_rate * 0.5)
            reasons.append(f"历史成交率{success_rate:.0f}%")

        total_amount = (stats['total_amount'] or 0) / 10000
        if total_amount > 0:
            score += min(20, total_amount / 10)
            reasons.append(f"累计业绩{total_amount:.1f}万")

        if industry and user in industry_experience:
            exp_count = industry_experience[user].get(industry, 0)
            if exp_count > 0:
                score += min(25, exp_count * 5)
                reasons.append(f"行业「{industry}」经验{exp_count}单")

        if user in matched_owners:
            score += 15
            reasons.append("知识库相关经历匹配")

        if requirements and user in qualifications:
            user_quals = qualifications.get(user, '')
            if any(req in user_quals for req in requirements.split(',')):
                score += 10
                reasons.append("资质匹配")

        workload_penalty = total_business * 2
        score = max(0, score - workload_penalty * 0.5)

        candidate_scores[user] = {
            'name': stats['name'],
            'role': stats['role'],
            'department': stats.get('department', ''),
            'score': round(score, 1),
            'total_business': total_business,
            'success_rate': round((stats['successful_deals'] or 0) / max(total_business, 1) * 100, 1),
            'total_amount': round(total_amount, 1),
            'reasons': reasons,
            'qualifications': qualifications.get(user, '')
        }

    if USE_LLM and candidate_scores:
        try:
            ranked = sorted(candidate_scores.items(), key=lambda x: x[1]['score'], reverse=True)[:3]
            top_candidates = [{'user': u, **v} for u, v in ranked]

            prompt = f"""你是CRM系统的销售分配专家。基于以下商机信息和候选人数据，
请分析每位候选人的优劣势，并给出最终推荐排序和理由。

商机信息：标题={business_title}，行业={industry}，金额={amount}万，要求={requirements}

候选人：
{json.dumps(top_candidates, ensure_ascii=False, indent=2)}

请输出JSON格式：
{{
  "recommendations": [
    {{"username": "...", "rank": 1, "reason": "...", "strengths": ["..."], "weaknesses": ["..."]}}
  ],
  "final_recommendation": "...",
  "strategy_notes": "..."
}}"""

            messages = [
                {'role': 'system', 'content': '你是专业的销售分配顾问，输出严格JSON格式。'},
                {'role': 'user', 'content': prompt}
            ]
            llm_result = call_llm(messages)

            if llm_result:
                try:
                    cleaned = llm_result.strip()
                    if cleaned.startswith('```'):
                        import re
                        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
                        cleaned = re.sub(r'\s*```$', '', cleaned)
                    llm_analysis = json.loads(cleaned)
                except Exception:
                    llm_analysis = None
            else:
                llm_analysis = None
        except Exception:
            llm_analysis = None
    else:
        llm_analysis = None

    sorted_candidates = sorted(candidate_scores.items(), key=lambda x: x[1]['score'], reverse=True)
    recommendations = []
    for rank, (user, data_item) in enumerate(sorted_candidates[:5], 1):
        data_item['username'] = user
        data_item['rank'] = rank
        recommendations.append(data_item)

    try:
        cursor.execute("""
            INSERT INTO ai_recommendations
            (recommendation_type, target_id, target_type, recommended_data, reason, score,
             created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            'owner_recommendation',
            business_id or customer_id,
            'business' if business_id else 'customer',
            json.dumps(recommendations[:3], ensure_ascii=False),
            llm_analysis.get('strategy_notes', '') if llm_analysis else '规则匹配推荐',
            recommendations[0]['score'] if recommendations else 0,
            username,
        ))
        db.commit()
    except Exception:
        pass

    record_operation_log(username, '智能推荐', '商机负责人',
                         f'推荐完成 {business_title} 推荐:{recommendations[0]["name"] if recommendations else "无"}')

    return jsonify({
        'code': 200,
        'message': 'success',
        'data': {
            'recommendations': recommendations,
            'llm_analysis': llm_analysis,
            'total_candidates': len(candidate_scores)
        }
    })


@agent_agent_bp.route('/api/agent/tracking-strategy', methods=['POST'])
@token_required
def generate_tracking_strategy():
    """基于知识库的商机跟踪策略生成。

    综合分析商机信息、历史跟进记录、知识库案例，
    生成个性化的跟踪策略和行动建议。

    请求体：
        business_id: 商机ID
        additional_context: 附加上下文（如最新跟进情况）
    """
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload.get('username', '')

    business_id = data.get('business_id')
    additional_context = data.get('additional_context', '')

    db = get_db()
    cursor = db.cursor()

    if business_id:
        cursor.execute("""
            SELECT b.*, c.company as customer_name, c.industry, c.level as customer_level,
                   c.region, u.name as owner_name
            FROM business b
            LEFT JOIN customers c ON b.cust_id = c.id
            LEFT JOIN users u ON b.owner_id = u.username
            WHERE b.id = ?
        """, (business_id,))
        business = dict(cursor.fetchone() or {})
    else:
        business = data

    if not business:
        return jsonify({'code': 400, 'message': '请提供商机信息', 'data': None})

    cursor.execute("""
        SELECT COUNT(*) as visit_count, MAX(v.plan_date) as last_visit
        FROM visits v
        WHERE v.cust_id = (SELECT cust_id FROM business WHERE id = ?)
    """, (business_id,))
    visit_data = cursor.fetchone()
    visit_count = visit_data['visit_count'] if visit_data else 0
    last_visit = visit_data['last_visit'] if visit_data else None

    cursor.execute("""
        SELECT COUNT(*) as log_count, MAX(log_time) as last_log
        FROM follow_logs
        WHERE ref_type = 'customer' AND ref_id = (SELECT cust_id FROM business WHERE id = ?)
    """, (business_id,))
    follow_data = cursor.fetchone()
    follow_count = follow_data['log_count'] if follow_data else 0
    last_follow = follow_data['last_log'] if follow_data else None

    industry = business.get('industry', '')
    customer_name = business.get('customer_name', '')
    stage = business.get('stage', '')
    probability = business.get('probability', 0)

    query_text = f"{customer_name} {industry} {stage} 商机跟进策略 案例"
    similar_cases = hybrid_search(query_text, top_k=5)

    knowledge_insights = []
    for case in similar_cases:
        if case['similarity'] > 0.3:
            knowledge_insights.append({
                'title': case['title'],
                'similarity': case['similarity'],
                'summary': case.get('summary', '')[:100],
                'source': case.get('source', '')
            })

    base_strategy = _generate_base_strategy(stage, probability, visit_count, follow_count, last_follow)

    risk_factors = _assess_risk_factors(business, visit_count, follow_count)

    action_items = _generate_action_items(stage, risk_factors, knowledge_insights)

    strategy = {
        'business_title': business.get('title', ''),
        'customer_name': customer_name,
        'current_stage': stage,
        'current_probability': probability,
        'visit_count': visit_count,
        'follow_count': follow_count,
        'last_visit': last_visit,
        'last_follow': last_follow,
        'base_strategy': base_strategy,
        'risk_factors': risk_factors,
        'action_items': action_items,
        'knowledge_references': knowledge_insights[:3],
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    if USE_LLM and (knowledge_insights or additional_context):
        try:
            prompt = f"""你是CRM销售策略专家。基于以下商机信息和知识库案例，
生成一份详细的跟进策略建议。

商机信息：
{json.dumps(strategy, ensure_ascii=False, indent=2)}

附加上下文：{additional_context}

请输出JSON格式的策略增强建议：
{{
  "enhanced_strategy": "详细的策略描述",
  "key_tactics": ["策略1", "策略2"],
  "communication_tips": ["沟通技巧1", "沟通技巧2"],
  "timeline_suggestion": "时间线建议",
  "resources_needed": ["需要的资源1", "需要的支持1"]
}}"""

            messages = [
                {'role': 'system', 'content': '你是专业的销售策略顾问。'},
                {'role': 'user', 'content': prompt}
            ]
            llm_result = call_llm(messages)
            if llm_result:
                try:
                    cleaned = llm_result.strip()
                    if cleaned.startswith('```'):
                        import re
                        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
                        cleaned = re.sub(r'\s*```$', '', cleaned)
                    llm_strategy = json.loads(cleaned)
                    strategy['llm_enhancement'] = llm_strategy
                except Exception:
                    pass
        except Exception:
            pass

    return jsonify({
        'code': 200,
        'message': 'success',
        'data': strategy
    })


def _generate_base_strategy(stage, probability, visit_count, follow_count, last_follow):
    """生成基础跟踪策略。"""
    if probability >= 80 or stage in ('商务谈判', '合同签订'):
        return {
            'focus': '促成签约',
            'frequency': '每周1-2次',
            'method': '面对面沟通为主',
            'content': '重点推进合同条款确认、商务谈判、高层对接'
        }
    elif probability >= 60 or stage == '方案确定':
        return {
            'focus': '方案确认',
            'frequency': '每3-5天1次',
            'method': '技术交流+方案演示',
            'content': '深化技术方案、确认需求细节、组织方案评审会'
        }
    elif probability >= 30 or stage == '能力展示':
        return {
            'focus': '能力展示',
            'frequency': '每5-7天1次',
            'method': '案例分享+产品演示',
            'content': '展示行业案例、组织产品演示、建立技术信任'
        }
    else:
        return {
            'focus': '需求挖掘',
            'frequency': '每7-10天1次',
            'method': '拜访+需求调研',
            'content': '深入了解客户需求、建立关系、挖掘痛点'
        }


def _assess_risk_factors(business, visit_count, follow_count):
    """评估商机风险因素。"""
    risks = []

    probability = business.get('probability', 0) or 0
    if probability < 30:
        risks.append({'level': '高', 'factor': '成交概率较低', 'suggestion': '加强需求挖掘，提高客户认可度'})
    elif probability < 50:
        risks.append({'level': '中', 'factor': '成交概率偏低', 'suggestion': '增加接触频次，推进关键决策人关系'})

    if visit_count == 0:
        risks.append({'level': '高', 'factor': '从未拜访客户', 'suggestion': '尽快安排首次拜访，建立面对面沟通'})
    elif visit_count < 2:
        risks.append({'level': '中', 'factor': '拜访次数偏少', 'suggestion': '增加拜访频次，加深客户关系'})

    if follow_count == 0:
        risks.append({'level': '高', 'factor': '无跟进记录', 'suggestion': '立即开展跟进活动，记录沟通内容'})

    amount = business.get('amount', 0) or 0
    if amount > 50000000:
        risks.append({'level': '中', 'factor': '大单项目（5000万+）', 'suggestion': '组织专项团队，高层参与跟进'})
    elif amount > 10000000:
        risks.append({'level': '低', 'factor': '中大项目（1000万+）', 'suggestion': '重点关注，保持定期沟通'})

    return risks


def _generate_action_items(stage, risk_factors, knowledge_insights):
    """生成具体行动项。"""
    actions = []

    if stage in ('引导需求', '能力展示'):
        actions.append({
            'priority': '高',
            'action': '安排客户需求调研会议',
            'deadline': '1周内',
            'details': '组织技术、商务团队进行需求摸底'
        })
        actions.append({
            'priority': '中',
            'action': '准备行业案例PPT',
            'deadline': '3天内',
            'details': '选择2-3个同行业成功案例进行展示'
        })
    elif stage in ('方案确定', '商务谈判'):
        actions.append({
            'priority': '高',
            'action': '组织方案评审会',
            'deadline': '5天内',
            'details': '与客户技术团队进行方案细节评审'
        })
        actions.append({
            'priority': '高',
            'action': '准备商务谈判材料',
            'deadline': '谈判前3天',
            'details': '包括报价单、谈判策略、让步底线'
        })
    elif stage in ('合同签订', '销售实现'):
        actions.append({
            'priority': '高',
            'action': '合同条款最终确认',
            'deadline': '3天内',
            'details': '法务、商务、技术三方审核合同'
        })
        actions.append({
            'priority': '中',
            'action': '项目启动会准备',
            'deadline': '合同签订后1周',
            'details': '组建项目团队，制定实施计划'
        })

    for risk in risk_factors:
        if risk['level'] == '高':
            actions.append({
                'priority': '高',
                'action': f"应对风险：{risk['factor']}",
                'deadline': '本周内',
                'details': risk['suggestion']
            })

    if knowledge_insights:
        top_case = knowledge_insights[0]
        actions.append({
            'priority': '中',
            'action': f"参考相似案例：{top_case['title']}",
            'deadline': '随时',
            'details': f"相似度{top_case['similarity']}，可借鉴其成功经验"
        })

    return actions


@agent_agent_bp.route('/api/agent/bid-evaluation', methods=['POST'])
@token_required
def evaluate_bid():
    """投标文件智能打分评估。

    基于投标文件内容、知识库案例、企业资质、人员资质，
    进行多维度综合评分和竞争力分析。

    请求体：
        project_name: 项目名称
        bid_content: 投标文件内容（文本）
        bid_id: 投标编号
        requirements: 招标要求
        category: 项目类别
    """
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload.get('username', '')

    project_name = data.get('project_name', '')
    bid_content = data.get('bid_content', '')
    bid_id = data.get('bid_id', '')
    requirements = data.get('requirements', '')
    category = data.get('category', '')

    if not project_name:
        return jsonify({'code': 400, 'message': '请提供项目名称', 'data': None})

    db = get_db()
    cursor = db.cursor()

    dimensions = {
        '技术方案': {'weight': 0.35, 'score': 0, 'max_score': 100, 'comments': []},
        '商务报价': {'weight': 0.25, 'score': 0, 'max_score': 100, 'comments': []},
        '企业资质': {'weight': 0.20, 'score': 0, 'max_score': 100, 'comments': []},
        '人员配置': {'weight': 0.15, 'score': 0, 'max_score': 100, 'comments': []},
        '项目经验': {'weight': 0.05, 'score': 0, 'max_score': 100, 'comments': []},
    }

    if bid_content:
        tech_score, tech_comments = _evaluate_technical(bid_content, requirements, category)
        dimensions['技术方案']['score'] = tech_score
        dimensions['技术方案']['comments'] = tech_comments

    if requirements:
        biz_score, biz_comments = _evaluate_business(bid_content, requirements)
        dimensions['商务报价']['score'] = biz_score
        dimensions['商务报价']['comments'] = biz_comments

    cursor.execute("SELECT * FROM company_qualifications WHERE status = '有效'")
    company_quals = [dict(r) for r in cursor.fetchall()]
    qual_score, qual_comments = _evaluate_company_qualifications(company_quals, requirements, category)
    dimensions['企业资质']['score'] = qual_score
    dimensions['企业资质']['comments'] = qual_comments

    cursor.execute("""
        SELECT p.*, u.name as user_name, u.role
        FROM personnel_qualifications p
        JOIN users u ON p.username = u.username
        WHERE p.status = '有效'
    """)
    personnel_quals = [dict(r) for r in cursor.fetchall()]
    staff_score, staff_comments = _evaluate_personnel(personnel_quals, requirements, category)
    dimensions['人员配置']['score'] = staff_score
    dimensions['人员配置']['comments'] = staff_comments

    cursor.execute("""
        SELECT c.*, u.name as owner_name
        FROM contracts c
        JOIN users u ON c.owner_id = u.username
        WHERE c.status IN ('执行中', '已完成')
        ORDER BY c.sign_date DESC
        LIMIT 20
    """)
    past_contracts = [dict(r) for r in cursor.fetchall()]
    exp_score, exp_comments = _evaluate_experience(past_contracts, category, requirements)
    dimensions['项目经验']['score'] = exp_score
    dimensions['项目经验']['comments'] = exp_comments

    total_score = sum(d['score'] * d['weight'] for d in dimensions.values())

    total_score = round(total_score, 1)

    if total_score >= 85:
        level = '优秀'
        recommendation = '建议参与投标，竞争力强'
    elif total_score >= 75:
        level = '良好'
        recommendation = '建议参与投标，具有一定竞争力'
    elif total_score >= 60:
        level = '合格'
        recommendation = '可参与投标，需加强薄弱环节'
    else:
        level = '风险'
        recommendation = '投标风险较大，建议谨慎评估'

    all_comments = []
    for dim_name, dim_data in dimensions.items():
        for comment in dim_data['comments']:
            all_comments.append(f"[{dim_name}] {comment}")

    evaluation = {
        'project_name': project_name,
        'bid_id': bid_id,
        'total_score': total_score,
        'level': level,
        'recommendation': recommendation,
        'dimensions': dimensions,
        'key_strengths': _get_strengths(dimensions),
        'key_weaknesses': _get_weaknesses(dimensions),
        'improvement_suggestions': all_comments[:5],
        'evaluated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'evaluator': username
    }

    if USE_LLM:
        try:
            prompt = f"""你是专业的投标评审专家。基于以下评估结果，
给出综合评审意见和改进建议。

评估结果：{json.dumps(evaluation, ensure_ascii=False, indent=2)}

招标要求：{requirements}
项目类别：{category}

请输出JSON格式的评审意见：
{{
  "expert_opinion": "综合评审意见",
  "strengths": ["优势1", "优势2"],
  "weaknesses": ["弱点1", "弱点2"],
  "improvement_actions": ["改进措施1", "改进措施2"],
  "confidence": 0.85
}}"""

            messages = [
                {'role': 'system', 'content': '你是专业的投标评审专家。'},
                {'role': 'user', 'content': prompt}
            ]
            llm_result = call_llm(messages)
            if llm_result:
                try:
                    cleaned = llm_result.strip()
                    if cleaned.startswith('```'):
                        import re
                        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
                        cleaned = re.sub(r'\s*```$', '', cleaned)
                    llm_eval = json.loads(cleaned)
                    evaluation['llm_review'] = llm_eval
                except Exception:
                    pass
        except Exception:
            pass

    try:
        cursor.execute("""
            INSERT INTO bid_evaluations
            (bid_id, project_name, evaluator, total_score, score_details,
             evaluation_result, recommendation, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (
            bid_id, project_name, username, total_score,
            json.dumps(dimensions, ensure_ascii=False),
            level, recommendation, '已完成'
        ))
        db.commit()
    except Exception:
        pass

    record_operation_log(username, '投标评估', '智能评估',
                         f'{project_name} 得分:{total_score} 等级:{level}')

    return jsonify({
        'code': 200,
        'message': '评估完成',
        'data': evaluation
    })


def _evaluate_technical(bid_content, requirements, category):
    """评估技术方案。"""
    score = 60.0
    comments = []

    keywords = requirements.split() if requirements else []
    if bid_content and keywords:
        matched = sum(1 for kw in keywords if kw in bid_content)
        coverage = matched / max(len(keywords), 1) * 100
        score = max(40, min(95, coverage * 0.8 + 30))
        comments.append(f"技术要点覆盖率：{coverage:.0f}%")

    category_tech = {
        '软件': ['架构设计', '技术栈', '安全性', '性能', '扩展性', '微服务'],
        '硬件': ['原理图', 'PCB设计', '元器件选型', 'EMC', '可靠性'],
        '系统集成': ['接口设计', '兼容性', '集成方案', '测试方案'],
        '服务': ['服务流程', '服务团队', '响应时间', 'SLA'],
    }

    if category and category in category_tech:
        tech_keywords = category_tech[category]
        found = [kw for kw in tech_keywords if kw in (bid_content or '')]
        if found:
            score += 5
            comments.append(f"包含关键技术要素：{', '.join(found[:3])}")
        else:
            comments.append("缺少该类别关键技术要素")
            score -= 10

    if '创新' in (bid_content or '') or '创新点' in (bid_content or ''):
        comments.append("包含创新点描述")
        score += 5

    return round(max(0, min(100, score)), 1), comments


def _evaluate_business(bid_content, requirements):
    """评估商务报价。"""
    score = 70.0
    comments = []

    if '报价' in (bid_content or '') or '价格' in (bid_content or ''):
        comments.append("报价信息完整")
        score += 5
    else:
        comments.append("缺少报价信息")
        score -= 10

    if '付款' in (bid_content or '') or '付款方式' in (bid_content or ''):
        comments.append("付款条款明确")
        score += 3

    if '质保' in (bid_content or '') or '售后服务' in (bid_content or ''):
        comments.append("售后服务有保障")
        score += 5

    return round(max(0, min(100, score)), 1), comments


def _evaluate_company_qualifications(quals, requirements, category):
    """评估企业资质。"""
    score = 50.0
    comments = []

    if not quals:
        comments.append("暂无企业资质记录")
        return score, comments

    total_quals = len(quals)
    valid_quals = sum(1 for q in quals if q.get('status') == '有效')
    score += min(20, valid_quals * 5)

    key_quals = ['ISO9001', 'ISO27001', 'CMMI', '高新技术企业', '软件企业']
    matched_quals = []
    for q in quals:
        qual_name = q.get('qualification_name', '') or ''
        qual_type = q.get('qualification_type', '') or ''
        for kq in key_quals:
            if kq in qual_name or kq in qual_type:
                matched_quals.append(qual_name or qual_type)

    if matched_quals:
        score += min(25, len(matched_quals) * 8)
        comments.append(f"持有资质：{', '.join(matched_quals[:3])}")

    if category:
        category_quals = {
            '软件': ['软件企业', 'CMMI', 'ISO27001'],
            '硬件': ['ISO9001', 'ISO14001'],
            '系统集成': ['系统集成资质', 'ISO9001'],
        }
        if category in category_quals:
            req_quals = category_quals[category]
            has_req = any(
                any(rq in (q.get('qualification_name', '') + q.get('qualification_type', '')) for rq in req_quals)
                for q in quals
            )
            if has_req:
                comments.append("具备行业必备资质")
                score += 10
            else:
                comments.append("缺少行业必备资质")
                score -= 10

    return round(max(0, min(100, score)), 1), comments


def _evaluate_personnel(personnel_quals, requirements, category):
    """评估人员配置。"""
    score = 55.0
    comments = []

    if not personnel_quals:
        comments.append("暂无人员资质记录")
        return score, comments

    total = len(personnel_quals)
    unique_users = len(set(q['username'] for q in personnel_quals))
    score += min(15, unique_users * 3)

    key_certs = ['PMP', '信息系统项目管理师', '系统架构设计师', '软件设计师', 'CISSP']
    has_key_certs = False
    for q in personnel_quals:
        qual_name = q.get('qualification_name', '') or ''
        cert_no = q.get('certificate_no', '') or ''
        for kc in key_certs:
            if kc in qual_name or kc in cert_no:
                has_key_certs = True
                break

    if has_key_certs:
        score += 20
        comments.append("核心人员持有重要证书")

    level_dist = {}
    for q in personnel_quals:
        level = q.get('level', '未知') or '未知'
        level_dist[level] = level_dist.get(level, 0) + 1
    if level_dist:
        level_desc = ', '.join([f"{k}:{v}人" for k, v in level_dist.items()])
        comments.append(f"人员结构：{level_desc}")
        score += min(10, len(level_dist) * 3)

    return round(max(0, min(100, score)), 1), comments


def _evaluate_experience(contracts, category, requirements):
    """评估项目经验。"""
    score = 50.0
    comments = []

    if not contracts:
        comments.append("暂无历史合同数据")
        return score, comments

    total_amount = sum(c.get('total_amt', 0) or 0 for c in contracts) / 10000
    total_count = len(contracts)

    score += min(20, total_count * 2)
    if total_amount > 1000:
        score += 10
        comments.append(f"累计合同额：{total_amount:.0f}万")
    if total_count > 10:
        comments.append(f"历史项目数量：{total_count}个")

    if category:
        matched = [c for c in contracts if category.lower() in (c.get('classification', '') or '').lower()]
        if matched:
            score += 15
            comments.append(f"同类项目经验：{len(matched)}个")

    return round(max(0, min(100, score)), 1), comments


def _get_strengths(dimensions):
    """获取优势维度。"""
    sorted_dims = sorted(dimensions.items(), key=lambda x: x[1]['score'], reverse=True)
    return [{'dimension': name, 'score': data['score']} for name, data in sorted_dims if data['score'] >= 75]


def _get_weaknesses(dimensions):
    """获取薄弱维度。"""
    sorted_dims = sorted(dimensions.items(), key=lambda x: x[1]['score'])
    return [{'dimension': name, 'score': data['score']} for name, data in sorted_dims if data['score'] < 65]


def register_routes(app):
    app.register_blueprint(agent_agent_bp)