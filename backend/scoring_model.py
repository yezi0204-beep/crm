"""商机评分模型（第一版：规则评分 + LLM 评分混合）。

7 维度加权评分（每维度 0-100，总分 0-100）：
  business_match   业务匹配度   30%
  customer_value   客户价值     20%
  budget_amount    预算金额     15%
  project_stage   项目阶段     15%
  time_urgency    时间紧迫度   10%
  region_match    区域匹配度    5%
  competition     竞争情况      5%

等级：
  S 级：90-100
  A 级：80-89
  B 级：60-79
  C 级：0-59

融合策略：规则评分 50% + LLM 评分 50%（LLM 失败时降级为纯规则）。
"""
import json
import re
import logging
from datetime import datetime, date

logger = logging.getLogger(__name__)

# ============================================================
# 评分配置
# ============================================================
DIMENSION_WEIGHTS = {
    'business_match': 0.30,   # 业务匹配度
    'customer_value': 0.20,   # 客户价值
    'budget_amount': 0.15,    # 预算金额
    'project_stage': 0.15,    # 项目阶段
    'time_urgency': 0.10,     # 时间紧迫度
    'region_match': 0.05,     # 区域匹配度
    'competition': 0.05,      # 竞争情况
}

DIMENSION_LABELS = {
    'business_match': '业务匹配度',
    'customer_value': '客户价值',
    'budget_amount': '预算金额',
    'project_stage': '项目阶段',
    'time_urgency': '时间紧迫度',
    'region_match': '区域匹配度',
    'competition': '竞争情况',
}

# 等级阈值（从高到低）
GRADE_THRESHOLDS = [
    (90, 'S'),
    (80, 'A'),
    (60, 'B'),
    (0, 'C'),
]

# 规则 / LLM 融合权重
RULE_WEIGHT = 0.5
LLM_WEIGHT = 0.5

# 我方重点覆盖区域（可按业务调整）
TARGET_REGIONS = {
    '北京', '上海', '江苏', '浙江', '安徽', '山东',
    '南京', '苏州', '无锡', '杭州', '合肥', '济南',
}
# 邻近/业务辐射区域
ADJACENT_REGIONS = {
    '河南', '湖北', '湖南', '江西', '福建', '河北', '天津',
}

# 项目阶段得分映射（基于 procurement_method）
STAGE_SCORE_MAP = {
    '意向': 40, '需求': 40, '计划': 45,
    '挂网': 65, '预告': 65, '意向公开': 65,
    '询价': 75, '竞争性磋商': 85, '竞争性谈判': 85,
    '公开招标': 90, '邀请招标': 88, '招标': 90,
    '开标': 95, '评标': 92,
    '中标': 35, '成交': 35, '废标': 15,
    '执行': 25, '验收': 20, '履约': 25,
}


def grade_of(score):
    """根据总分返回等级 S/A/B/C。"""
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return 'C'


def _parse_list(val):
    """容错解析 JSON 数组/列表字符串。"""
    if not val:
        return []
    if isinstance(val, list):
        return val
    try:
        parsed = json.loads(val)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _parse_budget_amount(budget_str):
    """从预算字符串提取数值（万元）。"""
    if not budget_str:
        return None
    text = str(budget_str)
    # 优先匹配"XX万元"/"XX 万元"
    m = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*万', text)
    if m:
        return float(m.group(1))
    # 匹配"XX元"
    m = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*元', text)
    if m:
        return float(m.group(1)) / 10000.0
    # 匹配纯数字
    m = re.search(r'([0-9]+(?:\.[0-9]+)?)', text)
    if m:
        v = float(m.group(1))
        # 大于 1000 视为元
        return v / 10000.0 if v > 1000 else v
    return None


def _days_until(deadline_str):
    """计算距截止日期的天数，解析失败返回 None。"""
    if not deadline_str:
        return None
    text = str(deadline_str).strip()
    # 兼容 YYYY-MM-DD / YYYY/MM/DD / YYYY年MM月DD日
    m = re.search(r'(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})', text)
    if not m:
        # 兼容仅年月
        m2 = re.search(r'(20\d{2})[-/年](\d{1,2})', text)
        if m2:
            y, mo = int(m2.group(1)), int(m2.group(2))
            try:
                return (date(y, mo, 1) - date.today()).days
            except ValueError:
                return None
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return (date(y, mo, d) - date.today()).days
    except ValueError:
        return None


# ============================================================
# 规则评分：7 维度（每维度 0-100）
# ============================================================
def rule_score_business_match(keywords, business_tags=None, products_matched=None,
                              title='', summary='', db=None):
    """业务匹配度：基于命中关键词 + 业务标签 + 产品匹配 + 我方能力模型。

    能力库非空时：能力匹配分 60% + 关键词/标签分 40%；
    能力库为空时：退化为原有关键词评分。
    """
    kw = _parse_list(keywords) if not isinstance(keywords, list) else keywords
    tags = _parse_list(business_tags) if not isinstance(business_tags, list) else (business_tags or [])
    kw_count = len(kw)
    if kw_count >= 5:
        s = 90
    elif kw_count >= 3:
        s = 75
    elif kw_count >= 1:
        s = 55
    else:
        s = 20
    # 业务标签命中加分
    if tags:
        s = min(s + 10, 100)
    # 产品库命中加分
    if products_matched:
        s = min(s + 10, 100)

    # 能力模型融合（db 提供时启用）
    if db is not None and (title or summary):
        try:
            from capability_matcher import match_project_capabilities
            cap_result = match_project_capabilities(title, summary, db)
            if cap_result.get('matched'):
                cap_score = cap_result['capability_score']
                return int(cap_score * 0.6 + s * 0.4)
        except Exception:
            pass
    return s


def rule_score_customer_value(buyer, keywords=None):
    """客户价值：依据采购单位性质评估战略价值。"""
    if not buyer:
        return 50
    text = str(buyer)
    # 军/国防/装备类客户战略价值最高
    if re.search(r'军|部队|国防|装备|战|火箭|联指|战区|武警|公安|安全', text):
        return 90
    # 部委/省级单位
    if re.search(r'部$|委员会|省|总局|局$|厅$|院$|中心$|管委会', text):
        return 75
    # 高校/研究院/医院
    if re.search(r'大学|学院|医院|研究院|研究所', text):
        return 65
    # 国企/集团
    if re.search(r'集团|公司|有限', text):
        return 55
    return 50


def rule_score_budget_amount(budget_str):
    """预算金额：预算规模越大分越高。"""
    amt = _parse_budget_amount(budget_str)
    if amt is None:
        return 50  # 未知预算，中性分
    if amt >= 1000:
        return 95
    if amt >= 200:
        return 85
    if amt >= 50:
        return 70
    if amt >= 10:
        return 55
    return 35


def rule_score_project_stage(procurement_method, status=None):
    """项目阶段：越接近招标阶段分越高，已中标/执行降级。"""
    if not procurement_method:
        # 若已转入 CRM（converted），说明项目已推进
        if status == 'converted':
            return 35
        return 50
    text = str(procurement_method)
    # 精确匹配优先
    if text in STAGE_SCORE_MAP:
        return STAGE_SCORE_MAP[text]
    # 模糊匹配
    for key, val in STAGE_SCORE_MAP.items():
        if key in text:
            return val
    return 50


def rule_score_time_urgency(deadline_str):
    """时间紧迫度：截止日期越近分越高，过期降级。"""
    days = _days_until(deadline_str)
    if days is None:
        return 50
    if days < 0:
        return 20  # 已过期
    if days <= 7:
        return 95
    if days <= 30:
        return 80
    if days <= 90:
        return 60
    return 40


def rule_score_region_match(region):
    """区域匹配度：与我方覆盖区域匹配度。"""
    if not region:
        return 50
    text = str(region)
    # 命中重点区域
    for r in TARGET_REGIONS:
        if r in text:
            return 90
    # 邻近区域
    for r in ADJACENT_REGIONS:
        if r in text:
            return 70
    return 40


def rule_score_competition(competitors):
    """竞争情况：竞争对手越少分越高。"""
    comps = _parse_list(competitors) if not isinstance(competitors, list) else competitors
    n = len(comps)
    if n == 0:
        return 60  # 未知竞争，中性偏乐观
    if n <= 2:
        return 75
    if n <= 5:
        return 55
    return 30


def rule_scores(lead, db=None):
    """对一条商机计算 7 维度规则评分。lead 为 dict 或 sqlite3.Row。

    db 提供时业务匹配度将融合我方能力模型（capability_matcher）。
    """
    def get(key, default=''):
        if isinstance(lead, dict):
            return lead.get(key, default)
        try:
            return lead[key]
        except (KeyError, IndexError):
            return default

    keywords = get('keywords_matched', '')
    buyer = get('buyer', '')
    budget = get('budget', '')
    method = get('procurement_method', '')
    deadline = get('deadline', '')
    region = get('region', '')
    competitors = get('competitors', '')
    status = get('status', '')
    title = get('title', '')
    summary = get('analysis_summary', '')

    return {
        'business_match': rule_score_business_match(
            keywords, title=title, summary=summary, db=db),
        'customer_value': rule_score_customer_value(buyer),
        'budget_amount': rule_score_budget_amount(budget),
        'project_stage': rule_score_project_stage(method, status),
        'time_urgency': rule_score_time_urgency(deadline),
        'region_match': rule_score_region_match(region),
        'competition': rule_score_competition(competitors),
    }


# ============================================================
# LLM 评分：调用大模型对 7 维度分别打分
# ============================================================
def llm_scores(lead):
    """调用 LLM 对 7 维度评分，失败返回 None。"""
    from config import USE_LLM
    if not USE_LLM:
        return None
    try:
        from qa_engine import call_llm
    except Exception as e:
        logger.warning(f'LLM 模块导入失败: {e}')
        return None

    def get(key, default=''):
        if isinstance(lead, dict):
            return lead.get(key, default)
        try:
            return lead[key]
        except (KeyError, IndexError):
            return default

    # 先算规则分，作为 LLM 的参考锚点，避免幻觉
    rule = rule_scores(lead)

    context = {
        'title': get('title', ''),
        'buyer': get('buyer', ''),
        'budget': get('budget', ''),
        'deadline': get('deadline', ''),
        'procurement_method': get('procurement_method', ''),
        'region': get('region', ''),
        'competitors': _parse_list(get('competitors', '')),
        'keywords_matched': _parse_list(get('keywords_matched', '')),
        'analysis_summary': get('analysis_summary', ''),
    }

    prompt = f"""基于以下商机信息，对 7 个维度分别评分（每维度 0-100 整数）。

商机信息：
{json.dumps(context, ensure_ascii=False)[:1500]}

规则参考分（仅作锚点，可在此基础上 ±20 调整，但需给出依据）：
{json.dumps(rule, ensure_ascii=False)}

评分维度定义：
- business_match（业务匹配度 30%）：与我方业务（遥感/雷达/仿真/装备/数字孪生/无人机/通信/指控/导航）的契合度
- customer_value（客户价值 20%）：客户的战略重要性、采购规模潜力
- budget_amount（预算金额 15%）：预算规模，越大越高
- project_stage（项目阶段 15%）：越接近正式招标分越高，已中标/执行则降低
- time_urgency（时间紧迫度 10%）：截止日期越近越高，已过期大幅降低
- region_match（区域匹配度 5%）：与目标区域（北京/江苏/浙江/安徽/山东）匹配度
- competition（竞争情况 5%）：竞争对手越少越高

只返回 JSON：
{{"business_match": 0, "customer_value": 0, "budget_amount": 0, "project_stage": 0, "time_urgency": 0, "region_match": 0, "competition": 0, "reason": "一句话总评"}}"""

    try:
        messages = [
            {'role': 'system', 'content': '你是商机评分专家，严格按维度评分，只返回JSON。'},
            {'role': 'user', 'content': prompt},
        ]
        content = call_llm(messages, max_tokens=4000, timeout=60, enable_thinking=False)
        if not content:
            return None
        # 解析 JSON
        parsed = _extract_json(content)
        if not isinstance(parsed, dict):
            return None
        # 校验 7 维度齐全
        dims = {}
        for k in DIMENSION_WEIGHTS:
            v = parsed.get(k)
            if v is None or not isinstance(v, (int, float)):
                return None
            dims[k] = max(0, min(100, int(v)))
        return dims
    except Exception as e:
        logger.warning(f'LLM 评分失败: {e}')
        return None


def _extract_json(text):
    """从 LLM 输出文本中提取 JSON 对象。"""
    if not text:
        return None
    # 去 ```json``` 包裹
    m = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    # 逐字符匹配最外层 {...}
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
# 融合评分
# ============================================================
def score_lead(lead, db=None):
    """对一条商机执行规则 + LLM 混合评分。

    Args:
        lead: dict 或 sqlite3.Row，含 intelligence_leads 的字段
        db: 数据库连接（提供时业务匹配度融合我方能力模型）

    Returns:
        dict: {
            'score': 0-100 总分,
            'dimensions': {dim: score, ...},  # 7 维度最终分
            'rule_dimensions': {dim: score},  # 规则分明细
            'llm_dimensions': {dim: score} | None,  # LLM 维度分明细（无则 None）
            'grade': 'S'/'A'/'B'/'C',
            'method': 'hybrid'/'rule',  # 是否融合 LLM
            'reason': 评分说明
        }
    """
    rule = rule_scores(lead, db=db)
    llm = llm_scores(lead)

    if llm:
        # 融合：规则 50% + LLM 50%
        final = {k: round(RULE_WEIGHT * rule[k] + LLM_WEIGHT * llm.get(k, rule[k])) for k in DIMENSION_WEIGHTS}
        method = 'hybrid'
        llm_dims = llm
    else:
        final = dict(rule)
        method = 'rule'
        llm_dims = None

    # 加权总分
    total = round(sum(DIMENSION_WEIGHTS[k] * final[k] for k in DIMENSION_WEIGHTS))
    total = max(0, min(100, total))

    return {
        'score': total,
        'dimensions': final,
        'rule_dimensions': rule,
        'llm_dimensions': llm_dims,
        'grade': grade_of(total),
        'method': method,
        'reason': _build_reason(lead, final, method),
    }


def _build_reason(lead, dims, method):
    """生成一句话评分理由。"""
    parts = []
    # 找最强和最弱维度
    sorted_dims = sorted(dims.items(), key=lambda x: x[1], reverse=True)
    strongest = sorted_dims[0]
    weakest = sorted_dims[-1]
    parts.append(f"{DIMENSION_LABELS[strongest[0]]}最强({strongest[1]})")
    parts.append(f"{DIMENSION_LABELS[weakest[0]]}最弱({weakest[1]})")
    method_label = '混合' if method == 'hybrid' else '规则'
    return f"[{method_label}评分] " + "，".join(parts)
