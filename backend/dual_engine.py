"""关键词 + 语义双引擎

定位：轻量级筛选层，介于纯关键词过滤和完整 7-Agent 分析之间。

两个引擎协同：
  - 关键词引擎（毫秒级）：基于业务标签三级树，硬过滤（排除词丢弃）+ 匹配度评分
  - 语义引擎（秒级）：单次 LLM 调用，判断内容与业务的语义相关性
  - 双引擎综合：keyword_score * 0.5 + semantic_score * 0.5（与项目记忆一致：
    "首版商机评分采用规则 50% + LLM 50% 混合方案"）

应用位置：
  1. 采集初筛（scheduler.collect_due_intelligence）：关键词硬过滤 → 语义评分 → 入库
  2. 入库决策（scheduler.auto_convert_high_score_leads）：双引擎分数作为高分阈值参考
  3. 商机评分辅助（ai_agents.agent6_scoring）：注入 keyword_score 作 business_match 参考

性能取舍：
  - 关键词引擎：毫秒级，可对每条采集数据调用
  - 语义引擎：秒级（单次 LLM），只对关键词通过的数据调用
  - 完整 7-Agent：分钟级（7 次 LLM），每日定时批量分析
"""
import logging

logger = logging.getLogger(__name__)


# ============================================================
# 表结构校验
# ============================================================
def ensure_relevance_score_column(db=None):
    """确保 raw_intelligence 表有 relevance_score 列（存双引擎综合分数）。

    幂等：已存在则跳过。
    """
    close_after = False
    if db is None:
        from db import open_db
        db = open_db()
        close_after = True
    try:
        cur = db.cursor()
        cur.execute("SHOW COLUMNS FROM raw_intelligence LIKE 'relevance_score'")
        if not cur.fetchone():
            cur.execute(
                "ALTER TABLE raw_intelligence ADD COLUMN relevance_score INT DEFAULT 0 "
                "COMMENT '双引擎综合分数(0-100)'"
            )
            db.commit()
            logger.info("raw_intelligence 表已添加 relevance_score 列")
    except Exception as e:
        logger.warning(f"ensure_relevance_score_column 失败: {e}")
    finally:
        if close_after:
            db.close()


# ============================================================
# 关键词引擎（毫秒级）
# ============================================================
def keyword_evaluate(title, content, snippet, db=None):
    """关键词引擎：基于业务标签三级树，硬过滤 + 匹配度评分。

    规则：
      - 命中排除词 → score=0, excluded=True（直接丢弃）
      - tags 模式：命中标签数越多分数越高
      - keywords 模式：命中关键词数越多分数越高
      - 未配置启用关键词/标签 → score=50（中性，不阻塞后续语义引擎）

    Returns:
        {'score': 0-100, 'matched': [...], 'excluded': bool, 'mode': str}
    """
    from routes.intelligence import _load_content_matcher, _match_content

    close_after = False
    if db is None:
        from db import open_db
        db = open_db()
        close_after = True
    try:
        matcher = _load_content_matcher(db)
        keep, matched = _match_content(title, content, snippet, matcher)
        if not keep:
            # 命中排除词
            return {'score': 0, 'matched': [], 'excluded': True, 'mode': matcher['mode']}

        # 计算匹配度分数
        if not matched:
            # 未命中任何业务词（无配置时）
            return {'score': 50, 'matched': [], 'excluded': False, 'mode': matcher['mode']}

        # 命中数 → 分数映射：1个=60, 2个=75, 3个=85, 4+=95
        cnt = len(matched)
        score = min(60 + (cnt - 1) * 15, 95)
        return {'score': score, 'matched': matched, 'excluded': False, 'mode': matcher['mode']}
    except Exception as e:
        logger.warning(f"keyword_evaluate 失败: {e}")
        return {'score': 50, 'matched': [], 'excluded': False, 'mode': 'error'}
    finally:
        if close_after:
            db.close()


# ============================================================
# 语义引擎（秒级，单次 LLM 调用）
# ============================================================
def semantic_evaluate(title, content, snippet, matched_keywords=None):
    """语义引擎：单次 LLM 调用，判断内容与我方业务的语义相关性。

    与完整 7-Agent 分析的区别：
      - 7-Agent：7 次 LLM 调用，深度结构化分析（分钟级）
      - 语义引擎：1 次 LLM 调用，只判断相关性 + 给分（秒级）

    用于采集初筛阶段的轻量级语义判断。

    Returns:
        {'score': 0-100, 'reason': str}
    """
    from config import USE_LLM
    if not USE_LLM:
        return {'score': 50, 'reason': 'LLM 未启用，使用中性分数'}

    # 构造输入文本（截断避免超长）
    text = f"标题：{title or ''}\n摘要：{snippet or ''}\n正文：{(content or '')[:1500]}"
    kw_hint = f"\n关键词引擎命中：{', '.join(matched_keywords)}" if matched_keywords else ""

    prompt = f"""判断以下内容与我方业务（军工装备、航空航天、信息技术、雷达/遥感/卫星、
嵌入式/仿真/指控系统、数据链/通信、智能制造）的语义相关性。

只返回 JSON：{{"score": 0到100的相关性分数, "reason": "一句话理由"}}
- 90+：高度相关，直接对应我方业务领域
- 60-89：相关，有部分业务契合点
- 30-59：弱相关，可能值得跟踪
- 0-29：不相关，丢弃

内容：
{text}{kw_hint}"""

    try:
        from qa_engine import call_llm
        resp = call_llm(
            [{'role': 'system', 'content': '你是业务相关性评估助手，只返回JSON。'},
             {'role': 'user', 'content': prompt}],
            max_tokens=4000, timeout=60, enable_thinking=False
        )
        if resp:
            from ai_agents import _extract_json
            result = _extract_json(resp)
            if result and isinstance(result, dict) and 'score' in result:
                score = int(result['score'])
                if 0 <= score <= 100:
                    return {'score': score, 'reason': result.get('reason', '')}
    except Exception as e:
        logger.warning(f"semantic_evaluate LLM 调用失败: {e}")

    # LLM 失败降级：用关键词匹配度作为语义分数的下限
    return {'score': 50, 'reason': 'LLM 调用失败，使用中性分数'}


# ============================================================
# 双引擎综合
# ============================================================
def hybrid_evaluate(title, content, snippet, db=None, skip_semantic=False):
    """双引擎综合评估：keyword_score * 0.5 + semantic_score * 0.5。

    流程：
      1. 关键词引擎：硬过滤（排除词丢弃）+ 匹配度评分
      2. 语义引擎：LLM 轻量语义判断
      3. 综合：两者各 50% 权重

    Args:
        skip_semantic: True 时跳过语义引擎（只走关键词，用于高频采集场景降本）

    Returns:
        {'score': 0-100, 'keyword_score': 0-100, 'semantic_score': 0-100,
         'matched': [...], 'excluded': bool, 'reason': str, 'should_collect': bool}
    """
    kw = keyword_evaluate(title, content, snippet, db)

    # 关键词硬过滤：命中排除词直接丢弃
    if kw['excluded']:
        return {
            'score': 0, 'keyword_score': 0, 'semantic_score': 0,
            'matched': [], 'excluded': True,
            'reason': '命中排除词，已丢弃', 'should_collect': False
        }

    if skip_semantic:
        sem_score = kw['score']
        sem_reason = '跳过语义引擎'
    else:
        sem = semantic_evaluate(title, content, snippet, kw.get('matched'))
        sem_score = sem['score']
        sem_reason = sem['reason']

    # 综合：50% + 50%
    hybrid_score = int(kw['score'] * 0.5 + sem_score * 0.5)
    reason = f"关键词{kw['score']}({','.join(kw['matched'][:3])}) + 语义{sem_score}({sem_reason[:30]})"

    return {
        'score': hybrid_score,
        'keyword_score': kw['score'],
        'semantic_score': sem_score,
        'matched': kw['matched'],
        'excluded': False,
        'reason': reason,
        'should_collect': hybrid_score >= 40  # 低于 40 分不采集入库
    }


def should_collect(title, content, snippet, db=None, threshold=40):
    """双引擎采集决策：综合分数 >= threshold 才采集入库。

    采集初筛调用此函数，避免低质量数据入库占用 LLM 分析配额。
    """
    result = hybrid_evaluate(title, content, snippet, db)
    result['should_collect'] = result['score'] >= threshold
    return result
