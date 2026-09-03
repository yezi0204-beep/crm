"""商机生命周期模型：情报 8 阶段 + CRM 5 阶段关联。

情报生命周期（招标方视角，按项目推进顺序）：
  0. 情报          intelligence           → CRM: 线索采集
  1. 采购意向      procurement_intent     → CRM: 线索培育
  2. 项目预告      project_preview        → CRM: 线索跟进
  3. 招标公告      bidding_announcement   → CRM: 商机创建（决定投标）
  4. 投标          bidding                → CRM: 商机推进
  5. 中标          won_bid                → CRM: 合同签订
  6. 落标          lost_bid               → CRM: 商机关闭（终态/失败）
  7. 成交          deal_closed            → CRM: 合同+回款（终态/成功）

CRM 生命周期（我方销售视角）：
  线索 → 商机 → 报价 → 合同 → 回款

阶段流转规则：
  - 正向推进可跳转（如 情报→招标公告）
  - 落标/成交为终态，进入后不可再流转
  - 落标可由任意"投标前/投标中"阶段进入
"""
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ============================================================
# 情报生命周期阶段定义
# ============================================================
INTEL_STAGES = [
    {
        'key': 'intelligence',
        'label': '情报',
        'order': 0,
        'crm_stage': 'lead_collect',
        'crm_label': '线索采集',
        'terminal': False,
    },
    {
        'key': 'procurement_intent',
        'label': '采购意向',
        'order': 1,
        'crm_stage': 'lead_nurture',
        'crm_label': '线索培育',
        'terminal': False,
    },
    {
        'key': 'project_preview',
        'label': '项目预告',
        'order': 2,
        'crm_stage': 'lead_follow',
        'crm_label': '线索跟进',
        'terminal': False,
    },
    {
        'key': 'bidding_announcement',
        'label': '招标公告',
        'order': 3,
        'crm_stage': 'opportunity_create',
        'crm_label': '商机创建',
        'terminal': False,
    },
    {
        'key': 'qa_announcement',
        'label': '答疑公告',
        'order': 4,
        'crm_stage': 'opportunity_advance',
        'crm_label': '商机推进',
        'terminal': False,
    },
    {
        'key': 'bid_opening',
        'label': '开标',
        'order': 5,
        'crm_stage': 'opportunity_advance',
        'crm_label': '商机推进',
        'terminal': False,
    },
    {
        'key': 'won_bid',
        'label': '中标公告',
        'order': 6,
        'crm_stage': 'contract_sign',
        'crm_label': '合同签订',
        'terminal': False,
    },
    {
        'key': 'contract_announcement',
        'label': '合同公告',
        'order': 7,
        'crm_stage': 'contract_sign',
        'crm_label': '合同签订',
        'terminal': False,
    },
    {
        'key': 'lost_bid',
        'label': '落标',
        'order': 8,
        'crm_stage': 'opportunity_close',
        'crm_label': '商机关闭',
        'terminal': True,
    },
    {
        'key': 'deal_closed',
        'label': '成交',
        'order': 9,
        'crm_stage': 'payment_collect',
        'crm_label': '合同+回款',
        'terminal': True,
    },
]

# 快速索引
STAGE_BY_KEY = {s['key']: s for s in INTEL_STAGES}
STAGE_KEYS = [s['key'] for s in INTEL_STAGES]
TERMINAL_STAGES = {s['key'] for s in INTEL_STAGES if s['terminal']}

# CRM 生命周期阶段（我方销售视角）
CRM_STAGES = [
    {'key': 'lead', 'label': '线索', 'intel_from': 'intelligence', 'order': 0},
    {'key': 'opportunity', 'label': '商机', 'intel_from': 'bidding_announcement', 'order': 1},
    {'key': 'quote', 'label': '报价', 'intel_from': 'bid_opening', 'order': 2},
    {'key': 'contract', 'label': '合同', 'intel_from': 'won_bid', 'order': 3},
    {'key': 'payment', 'label': '回款', 'intel_from': 'deal_closed', 'order': 4},
]

# 采购方式 → 情报生命周期阶段 自动推断映射
# （与 scoring_model.STAGE_SCORE_MAP 保持业务语义一致）
PROCUREMENT_TO_STAGE = {
    # 采购意向阶段
    '意向': 'procurement_intent',
    '需求': 'procurement_intent',
    '计划': 'procurement_intent',
    # 项目预告阶段
    '挂网': 'project_preview',
    '预告': 'project_preview',
    '意向公开': 'project_preview',
    # 招标公告阶段
    '公开招标': 'bidding_announcement',
    '邀请招标': 'bidding_announcement',
    '询价': 'bidding_announcement',
    '竞争性磋商': 'bidding_announcement',
    '竞争性谈判': 'bidding_announcement',
    '招标': 'bidding_announcement',
    # 答疑公告阶段
    '答疑': 'qa_announcement',
    '澄清': 'qa_announcement',
    '补遗': 'qa_announcement',
    '变更': 'qa_announcement',
    # 开标阶段（开标/评标进行中）
    '开标': 'bid_opening',
    '评标': 'bid_opening',
    # 中标公告阶段
    '中标': 'won_bid',
    '成交公告': 'won_bid',
    # 合同公告阶段
    '合同公告': 'contract_announcement',
    '合同公示': 'contract_announcement',
    '签订合同': 'contract_announcement',
    # 落标/废标
    '废标': 'lost_bid',
    # 已执行（成交后）
    '成交': 'deal_closed',
    '执行': 'deal_closed',
    '验收': 'deal_closed',
    '履约': 'deal_closed',
}


def derive_stage(procurement_method, status=None):
    """根据采购方式自动推断情报生命周期阶段。

    Args:
        procurement_method: 采购方式文本
        status: intelligence_leads.status（converted 等可能覆盖推断结果）

    Returns:
        str: 生命周期阶段 key，默认 'intelligence'
    """
    if not procurement_method:
        return 'intelligence'
    text = str(procurement_method)
    # 精确匹配优先
    if text in PROCUREMENT_TO_STAGE:
        return PROCUREMENT_TO_STAGE[text]
    # 模糊匹配
    for key, stage in PROCUREMENT_TO_STAGE.items():
        if key in text:
            return stage
    return 'intelligence'


def get_stage_info(stage_key):
    """获取阶段详细信息。"""
    return STAGE_BY_KEY.get(stage_key, STAGE_BY_KEY['intelligence'])


def get_stage_order(stage_key):
    """获取阶段顺序号。"""
    info = STAGE_BY_KEY.get(stage_key)
    return info['order'] if info else 0


def is_terminal(stage_key):
    """是否终态阶段（落标/成交）。"""
    return stage_key in TERMINAL_STAGES


def can_transition(from_key, to_key):
    """校验阶段流转是否合法。

    规则：
    - 起点或终点不存在 → 非法
    - 起点为终态 → 不可流转
    - 正向推进（order 增大）→ 合法
    - 反向回退 → 允许（业务上可能识别错误需回退）
    - 落标可由任意非终态阶段进入
    """
    if from_key not in STAGE_BY_KEY or to_key not in STAGE_BY_KEY:
        return False, '阶段不存在'
    if is_terminal(from_key):
        return False, f'当前阶段[{get_stage_info(from_key)["label"]}]为终态，不可流转'
    return True, 'ok'


def get_lifecycle_progress(stage_key):
    """获取生命周期进度（当前阶段及前后阶段，用于前端时间线展示）。"""
    current_order = get_stage_order(stage_key)
    stages = []
    for s in INTEL_STAGES:
        stages.append({
            'key': s['key'],
            'label': s['label'],
            'crm_label': s['crm_label'],
            'order': s['order'],
            'terminal': s['terminal'],
            'status': 'done' if s['order'] < current_order else (
                'current' if s['order'] == current_order else 'pending'
            ),
        })
    return {
        'current_stage': stage_key,
        'current_label': get_stage_info(stage_key)['label'],
        'current_crm_label': get_stage_info(stage_key)['crm_label'],
        'progress_pct': round((current_order + 1) / len(INTEL_STAGES) * 100),
        'stages': stages,
    }


def map_to_crm_stage(stage_key):
    """情报阶段映射到 CRM 生命周期阶段。"""
    info = get_stage_info(stage_key)
    crm_stage_key = info['crm_stage']
    # 映射到 CRM 5 阶段
    crm_map = {
        'lead_collect': 'lead',
        'lead_nurture': 'lead',
        'lead_follow': 'lead',
        'opportunity_create': 'opportunity',
        'opportunity_advance': 'opportunity',
        'contract_sign': 'contract',
        'opportunity_close': 'closed',
        'payment_collect': 'payment',
    }
    return crm_map.get(crm_stage_key, 'lead')


def build_lifecycle_reason(from_key, to_key, note=''):
    """生成阶段流转说明。"""
    from_label = get_stage_info(from_key)['label']
    to_label = get_stage_info(to_key)['label']
    arrow = '→' if get_stage_order(to_key) > get_stage_order(from_key) else '⤴'
    reason = f'{from_label}{arrow}{to_label}'
    if note:
        reason += f'：{note}'
    return reason


def get_next_stages(stage_key):
    """获取可流转的下一阶段列表（用于前端下拉选择）。

    返回除当前阶段和已过终态外的所有阶段，由前端展示。
    """
    current_order = get_stage_order(stage_key)
    result = []
    for s in INTEL_STAGES:
        # 跳过当前阶段
        if s['key'] == stage_key:
            continue
        # 落标和成交都可从任意非终态进入
        result.append({
            'key': s['key'],
            'label': s['label'],
            'order': s['order'],
            'direction': 'forward' if s['order'] > current_order else 'backward',
            'terminal': s['terminal'],
        })
    return result
