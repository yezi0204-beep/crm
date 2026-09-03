"""能力匹配器：基于我方能力模型（capabilities 表）进行项目能力匹配。

- 加载能力条目（名称+同义词+关键词）
- 对项目标题/需求文本进行匹配
- 输出匹配能力列表 + 综合匹配度
- 商机评分模型的 business_match 维度引用本模块结果
"""
import json
import logging

logger = logging.getLogger(__name__)

_cache = {'data': None, 'loaded_at': 0}
CACHE_TTL = 60  # 秒


def load_capabilities(db):
    """加载启用的能力条目（带缓存）。"""
    import time
    now = time.time()
    if _cache['data'] is not None and now - _cache['loaded_at'] < CACHE_TTL:
        return _cache['data']

    rows = db.execute("SELECT * FROM capabilities WHERE enabled=1").fetchall()
    caps = []
    for r in rows:
        def _parse(val):
            if not val:
                return []
            try:
                if val.startswith('['):
                    return json.loads(val)
                return [x.strip() for x in val.split(',') if x.strip()]
            except (json.JSONDecodeError, TypeError):
                return []

        caps.append({
            'id': r['id'],
            'name': r['name'],
            'level': r['level'] or 'mature',
            'description': r['description'] or '',
            'products': _parse(r['products']),
            'solutions': _parse(r['solutions']),
            'cases': _parse(r['cases']),
            'keywords': _parse(r['keywords']),
            'synonyms': _parse(r['synonyms']),
            'related_industries': _parse(r['related_industries']),
        })
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
                'message': '能力模型为空，请先初始化能力库'}

    full_text = f'{title or ""} {text or ""}'
    matched = []

    for cap in caps:
        hit_terms = []
        # 匹配词集合：能力名 + 同义词 + 关键词
        terms = [cap['name']] + cap['synonyms'] + cap['keywords']
        for term in terms:
            if term and term.lower() in full_text.lower():
                hit_terms.append(term)

        if hit_terms:
            # 置信度：命中数/总词数，能力等级加权（mature=1.0, growing=0.85, learning=0.7）
            total_terms = max(len(terms), 1)
            base = min(len(hit_terms) / 3, 1.0)  # 命中3个即满分
            level_weight = {'mature': 1.0, 'growing': 0.85, 'learning': 0.7}.get(cap['level'], 0.9)
            confidence = round(min(base * level_weight * 100, 100))
            matched.append({
                'name': cap['name'],
                'level': cap['level'],
                'confidence': confidence,
                'hit_terms': hit_terms,
                'products': cap['products'][:3],
                'cases': cap['cases'][:2],
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
