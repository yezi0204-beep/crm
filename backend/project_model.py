"""项目关联模型：多个公开公告关联到同一 Project。

采购项目生命周期（公告类型）：
  采购意向 → 招标公告 → 答疑公告 → 开标 → 中标公告 → 合同公告

同一项目在不同阶段会产生多个公开公告，每条公告作为独立 intelligence_lead
采集入库。本模块负责：
  1. 自动匹配：新公告按 买家+标题相似度+地区 关联到已有项目
  2. 项目创建：无匹配时自动创建新项目
  3. 阶段推进：新公告的 lifecycle_stage 更高时推进项目阶段
  4. 信息聚合：项目取最高评分、最新阶段、最新预算等

避免 CRM 重复商机：转入 CRM 时以 Project 为单位，而非单条公告。
"""
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# 项目关联匹配阈值：买家+标题+地区 组合相似度
PROJECT_MATCH_THRESHOLD = 0.75


def _get(obj, key, default=''):
    """兼容 dict / sqlite3.Row 的取值。"""
    if isinstance(obj, dict):
        return obj.get(key, default)
    try:
        return obj[key]
    except (KeyError, IndexError):
        return default


def _title_similarity(a, b):
    """标题相似度（复用 dedup_model 逻辑）。"""
    try:
        from dedup_model import title_similarity
        return title_similarity(a, b)
    except ImportError:
        from difflib import SequenceMatcher
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        return SequenceMatcher(None, str(a), str(b)).ratio()


def _combo_similarity(buyer_a, title_a, region_a, buyer_b, title_b, region_b):
    """买家+标题+地区 组合相似度（复用 dedup_model 逻辑）。"""
    try:
        from dedup_model import combo_similarity
        return combo_similarity(buyer_a, title_a, region_a, buyer_b, title_b, region_b)
    except ImportError:
        return _title_similarity(title_a, title_b)


def _normalize_project_name(title):
    """规范化项目名称：去常见后缀词。"""
    if not title:
        return ''
    import re
    # 去公告类型后缀词
    suffixes = [
        '采购意向公告', '采购意向', '招标公告', '招标', '答疑公告', '答疑',
        '开标公告', '开标', '中标公告', '中标结果公告', '中标结果', '中标',
        '合同公告', '合同公示', '成交公告', '成交结果公告', '成交结果', '成交',
        '公告', '公示', '项目', '采购',
    ]
    name = str(title).strip()
    for s in suffixes:
        if name.endswith(s) and len(name) > len(s):
            name = name[:-len(s)]
            break
    return name.strip() or str(title).strip()


def find_matching_project(lead, db):
    """为新公告查找匹配的已有项目。

    匹配策略（由精到粗）：
      1. 同买家 + 标题完全/高度相似 → 强匹配
      2. 同买家 + 标题组合相似度 ≥ 阈值 → 匹配
      3. 无买家但标题+地区高度相似 → 弱匹配

    Returns:
        dict|None: 匹配到的项目，无匹配返回 None
    """
    buyer = _get(lead, 'buyer', '').strip()
    title = _get(lead, 'title', '').strip()
    region = _get(lead, 'region', '').strip()

    if not title:
        return None

    # 取活跃项目列表（排除已关闭/已转入CRM的）
    projects = db.execute("""
        SELECT * FROM projects
        WHERE status = 'active'
        ORDER BY updated_at DESC
    """).fetchall()

    best_match = None
    best_score = 0.0

    for proj in projects:
        proj_buyer = _get(proj, 'buyer', '').strip()
        proj_name = _get(proj, 'name', '').strip()
        proj_region = _get(proj, 'region', '').strip()

        # 策略1：同买家 + 标题高度相似
        if buyer and proj_buyer and buyer == proj_buyer:
            title_sim = _title_similarity(title, proj_name)
            if title_sim >= 0.85:
                score = 0.40 + 0.50 * title_sim + 0.10 * (region == proj_region)
                if score > best_score:
                    best_score = score
                    best_match = proj
                    continue

        # 策略2：组合相似度
        combo = _combo_similarity(buyer, title, region, proj_buyer, proj_name, proj_region)
        if combo >= PROJECT_MATCH_THRESHOLD:
            if combo > best_score:
                best_score = combo
                best_match = proj

        # 策略3：无买家时，标题+地区匹配
        if not buyer and not proj_buyer:
            title_sim = _title_similarity(title, proj_name)
            if title_sim >= 0.80 and (region == proj_region or not region or not proj_region):
                score = title_sim * 0.8 + 0.2 * (region == proj_region)
                if score > best_score:
                    best_score = score
                    best_match = proj

    return best_match


def create_project(lead, db):
    """为新公告创建项目。"""
    title = _get(lead, 'title', '')
    buyer = _get(lead, 'buyer', '')
    region = _get(lead, 'region', '')
    budget = _get(lead, 'budget', '')
    score = _get(lead, 'score', 0) or 0
    score_grade = _get(lead, 'score_grade', '')
    lifecycle_stage = _get(lead, 'lifecycle_stage', 'intelligence') or 'intelligence'
    keywords = _get(lead, 'keywords_matched', '')

    name = _normalize_project_name(title)
    cursor = db.execute("""
        INSERT INTO projects
            (name, buyer, region, budget, lifecycle_stage, score, score_grade,
             status, announcement_count, keywords_matched)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 1, ?)
    """, (name, buyer, region, budget, lifecycle_stage, score, score_grade, keywords))
    return cursor.lastrowid


def link_to_project(lead_id, project_id, db):
    """将公告关联到项目，并更新项目聚合信息。"""
    # 关联公告
    db.execute(
        "UPDATE intelligence_leads SET project_id=? WHERE id=?",
        (project_id, lead_id)
    )

    # 重新聚合项目信息：取最高分、最新阶段、最新预算、公告数
    leads = db.execute("""
        SELECT id, title, buyer, region, budget, score, score_grade,
               lifecycle_stage, keywords_matched, status
        FROM intelligence_leads
        WHERE project_id=? AND status NOT IN ('rejected', 'merged')
        ORDER BY id
    """, (project_id,)).fetchall()

    if not leads:
        return

    # 取最高分
    max_score = 0
    max_grade = ''
    best_lead = None
    for l in leads:
        s = _get(l, 'score', 0) or 0
        if s >= max_score:
            max_score = s
            max_grade = _get(l, 'score_grade', '')
            best_lead = l

    # 取最长的标题作为项目名（信息最全）
    best_name = _normalize_project_name(_get(best_lead, 'title', ''))
    for l in leads:
        t = _normalize_project_name(_get(l, 'title', ''))
        if len(t) > len(best_name):
            best_name = t

    # 取最新阶段（order 最大且非终态）
    from lifecycle_model import get_stage_order, is_terminal
    latest_stage = 'intelligence'
    latest_order = -1
    for l in leads:
        stage = _get(l, 'lifecycle_stage', 'intelligence') or 'intelligence'
        order = get_stage_order(stage)
        if order > latest_order:
            latest_order = order
            latest_stage = stage

    # 取最新预算（非空）
    latest_budget = ''
    for l in reversed(leads):
        b = _get(l, 'budget', '')
        if b:
            latest_budget = b
            break

    # 聚合买家和地区
    buyer = _get(best_lead, 'buyer', '')
    region = _get(best_lead, 'region', '')

    # 合并关键词
    all_keywords = set()
    for l in leads:
        kw = _get(l, 'keywords_matched', '')
        if kw:
            try:
                if isinstance(kw, str):
                    kw_list = json.loads(kw) if kw.startswith('[') else [k.strip() for k in kw.split(',') if k.strip()]
                    all_keywords.update(kw_list)
            except (json.JSONDecodeError, TypeError):
                pass

    db.execute("""
        UPDATE projects
        SET name=?, buyer=?, region=?, budget=?, lifecycle_stage=?,
            score=?, score_grade=?, announcement_count=?,
            keywords_matched=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (
        best_name, buyer, region, latest_budget, latest_stage,
        max_score, max_grade, len(leads),
        json.dumps(list(all_keywords), ensure_ascii=False) if all_keywords else '',
        project_id,
    ))


def auto_associate_project(lead_id, lead_data, db):
    """自动关联公告到项目（主入口）。

    在 ai_opportunity 分析完成后调用：
    1. 查找匹配项目
    2. 匹配则关联，推进项目阶段
    3. 无匹配则创建新项目

    Returns:
        dict: {'project_id': int, 'action': 'linked'|'created', 'project_name': str}
    """
    # 先检查该公告是否已关联项目
    existing = db.execute(
        "SELECT project_id FROM intelligence_leads WHERE id=?", (lead_id,)
    ).fetchone()
    if existing and existing['project_id']:
        return {
            'project_id': existing['project_id'],
            'action': 'already_linked',
            'project_name': '',
        }

    # 查找匹配项目
    match = find_matching_project(lead_data, db)
    if match:
        link_to_project(lead_id, match['id'], db)
        return {
            'project_id': match['id'],
            'action': 'linked',
            'project_name': _get(match, 'name', ''),
        }

    # 创建新项目
    project_id = create_project(lead_data, db)
    db.execute(
        "UPDATE intelligence_leads SET project_id=? WHERE id=?",
        (project_id, lead_id)
    )
    return {
        'project_id': project_id,
        'action': 'created',
        'project_name': _normalize_project_name(_get(lead_data, 'title', '')),
    }


def get_project_summary(project_id, db):
    """获取项目汇总：项目信息 + 关联公告列表 + 生命周期进度。"""
    from lifecycle_model import get_lifecycle_progress

    project = db.execute(
        "SELECT * FROM projects WHERE id=?", (project_id,)
    ).fetchone()
    if not project:
        return None

    leads = db.execute("""
        SELECT id, title, buyer, budget, deadline, procurement_method, region,
               score, score_grade, lifecycle_stage, status, created_at,
               analysis_summary, converted_lead_id
        FROM intelligence_leads
        WHERE project_id=?
        ORDER BY
            CASE lifecycle_stage
                WHEN 'procurement_intent' THEN 1
                WHEN 'project_preview' THEN 2
                WHEN 'bidding_announcement' THEN 3
                WHEN 'qa_announcement' THEN 4
                WHEN 'bid_opening' THEN 5
                WHEN 'won_bid' THEN 6
                WHEN 'contract_announcement' THEN 7
                WHEN 'deal_closed' THEN 8
                WHEN 'lost_bid' THEN 9
                ELSE 0
            END, id
    """, (project_id,)).fetchall()

    stage = _get(project, 'lifecycle_stage', 'intelligence') or 'intelligence'
    progress = get_lifecycle_progress(stage)

    return {
        'project': dict(project),
        'announcements': [dict(l) for l in leads],
        'announcement_count': len(leads),
        'progress': progress,
    }
