# -*- coding: utf-8 -*-
"""能力匹配器：基于业务标签中的能力标签（capability_level 非空）进行项目能力匹配。

合并后能力数据存储在 business_tags 表（capability_level/capability_desc/products/solutions/cases 列）。
- load_capabilities 从 load_tag_matcher 获取能力列表
- match_project_capabilities 对项目标题/需求文本进行匹配
- 商机评分模型的 business_match 维度引用本模块结果
"""
import logging

logger = logging.getLogger(__name__)

_cache = {'data': None, 'loaded_at': 0}
CACHE_TTL = 60  # 秒


def load_capabilities(db):
    """加载启用的能力条目（从 business_tags 表，带缓存）。"""
    import time
    now = time.time()
    if _cache['data'] is not None and now - _cache['loaded_at'] < CACHE_TTL:
        return _cache['data']

    try:
        from routes.business_tags import load_tag_matcher
        _, _, _, caps = load_tag_matcher(db)
    except Exception:
        caps = []

    _cache['data'] = caps
    _cache['loaded_at'] = now
    return caps


def invalidate_cache():
    """能力变更后调用，清空缓存。"""
    _cache['data'] = None


def match_project_capabilities(title, text, db):
    """匹配项目需求到我方能力。

    Args:
        title: 项目标题
        text: 需求/摘要文本
        db: 数据库连接

    Returns:
        dict: {
            'matched': [{name, level, confidence, hit_terms, evidence}],
            'capability_score': 0-100 综合能力匹配分,
            'coverage': 匹配能力数/总能力数
        }
    """
    caps = load_capabilities(db)
    if not caps:
        return {'matched': [], 'capability_score': 50, 'coverage': 0,
                'message': '能力模型为空，请先在业务标签中配置能力等级'}

    full_text = f'{title or ""} {text or ""}'
    matched = []

    for cap in caps:
        hit_terms = []
        # 匹配词集合：能力名 + 同义词 + related_words
        terms = [cap['name']] + cap.get('synonyms', []) + cap.get('related_words', [])
        for term in terms:
            if term and term.lower() in full_text.lower():
                hit_terms.append(term)

        if hit_terms:
            # 置信度：命中数/总词数，能力等级加权
            total_terms = max(len(terms), 1)
            base = min(len(hit_terms) / 3, 1.0)  # 命中3个即满分
            level_weight = {'mature': 1.0, 'growing': 0.85, 'learning': 0.7, 'normal': 0.9}.get(cap['level'], 0.9)
            confidence = round(min(base * level_weight * 100, 100))
            matched.append({
                'name': cap['name'],
                'level': cap['level'],
                'confidence': confidence,
                'hit_terms': hit_terms,
                'products': cap.get('products', [])[:3],
                'cases': cap.get('cases', [])[:2],
            })

    # 按置信度排序
    matched.sort(key=lambda x: -x['confidence'])

    # 综合能力分：最强能力 60% + 能力覆盖广度 40%
    if matched:
        top_score = matched[0]['confidence']
        breadth = min(len(matched) / 3, 1.0) * 100
        capability_score = int(top_score * 0.6 + breadth * 0.4)
    else:
        capability_score = 20  # 无匹配能力

    return {
        'matched': matched,
        'capability_score': capability_score,
        'coverage': len(matched),
        'total_capabilities': len(caps),
    }
