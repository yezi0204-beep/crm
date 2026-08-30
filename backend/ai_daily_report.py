"""AI 日报生成模块。

Phase5: 汇总当日数据（采集→AI识别→转入CRM→分配），用 LLM 生成
摘要和建议，存入 ai_daily_reports 表。

数据来源：
- raw_intelligence: 当日采集量
- intelligence_leads: 当日AI分析量、高价值商机
- scraped_leads: 当日转入CRM的线索、分配状态
- customers/business: 关联的业务数据

LLM 参数：max_tokens=4000, timeout=60, enable_thinking=False
"""
import json
import sqlite3
import logging
from datetime import datetime, date

logger = logging.getLogger(__name__)


def _collect_metrics(db, report_date):
    """收集当日关键指标。"""
    date_prefix = report_date  # YYYY-MM-DD

    # 1. 原始情报
    intel_stats = {}
    rows = db.execute("""
        SELECT status, COUNT(*) as cnt FROM raw_intelligence
        WHERE collected_at LIKE ? GROUP BY status
    """, (f'{date_prefix}%',)).fetchall()
    intel_stats = {r['status']: r['cnt'] for r in rows}

    intel_total = db.execute(
        "SELECT COUNT(*) as cnt FROM raw_intelligence WHERE collected_at LIKE ?",
        (f'{date_prefix}%',)
    ).fetchone()['cnt']

    # 2. AI商机分析
    leads_analyzed = db.execute(
        "SELECT COUNT(*) as cnt FROM intelligence_leads WHERE created_at LIKE ?",
        (f'{date_prefix}%',)
    ).fetchone()['cnt']

    leads_relevant = db.execute(
        "SELECT COUNT(*) as cnt FROM intelligence_leads WHERE is_relevant=1 AND created_at LIKE ?",
        (f'{date_prefix}%',)
    ).fetchone()['cnt']

    leads_converted = db.execute(
        "SELECT COUNT(*) as cnt FROM intelligence_leads WHERE status='converted' AND created_at LIKE ?",
        (f'{date_prefix}%',)
    ).fetchone()['cnt']

    # 5. 高价值商机（score >= 40）
    top_opportunities = db.execute("""
        SELECT il.title, il.buyer, il.budget, il.deadline, il.score,
               il.procurement_method, il.region, il.competitors,
               il.analysis_summary
        FROM intelligence_leads il
        WHERE il.score >= 40 AND il.created_at LIKE ?
        ORDER BY il.score DESC LIMIT 10
    """, (f'{date_prefix}%',)).fetchall()

    # 4. 转入CRM的线索
    crm_leads = db.execute("""
        SELECT company, opportunity_name, intent_score, status,
               assigned_to, region
        FROM scraped_leads
        WHERE source='AI商机识别' AND scraped_at LIKE ?
        ORDER BY intent_score DESC LIMIT 10
    """, (f'{date_prefix}%',)).fetchall()

    # 5. 待处理情报总量
    pending_total = db.execute(
        "SELECT COUNT(*) as cnt FROM raw_intelligence WHERE status='pending'"
    ).fetchone()['cnt']

    # 6. 分析未转入的商机总量
    analyzed_not_converted = db.execute(
        "SELECT COUNT(*) as cnt FROM intelligence_leads WHERE status='analyzed'"
    ).fetchone()['cnt']

    return {
        'intel_total': intel_total,
        'intel_stats': intel_stats,
        'leads_analyzed': leads_analyzed,
        'leads_relevant': leads_relevant,
        'leads_converted': leads_converted,
        'pending_intel': pending_total,
        'analyzed_not_converted': analyzed_not_converted,
        'top_opportunities': [dict(r) for r in top_opportunities],
        'crm_leads': [dict(r) for r in crm_leads],
    }


def _build_prompt(metrics, report_date):
    """构造 LLM 日报 prompt。"""
    top_ops = metrics.get('top_opportunities', [])
    ops_text = ''
    if top_ops:
        ops_lines = []
        for op in top_ops[:5]:
            comps = op.get('competitors', '')
            if isinstance(comps, str):
                try:
                    comps = ', '.join(json.loads(comps))
                except (json.JSONDecodeError, TypeError):
                    pass
            ops_lines.append(
                f"  - [{op['score']}分] {op['title'][:50]}\n"
                f"    采购:{op.get('buyer','')} 预算:{op.get('budget','')} "
                f"截止:{op.get('deadline','')} 地区:{op.get('region','')}\n"
                f"    竞争对手:{comps}"
            )
        ops_text = '\n'.join(ops_lines)

    crm_text = ''
    crm_leads = metrics.get('crm_leads', [])
    if crm_leads:
        crm_lines = [f"  - {l['company']} | {l['opportunity_name'][:40]} | "
                     f"分:{l.get('intent_score',0)} | 状态:{l.get('status','')}"
                     for l in crm_leads[:5]]
        crm_text = '\n'.join(crm_lines)

    prompt = f"""请基于以下数据生成今日AI销售情报日报。

日期：{report_date}

【今日关键指标】
- 采集原始情报：{metrics['intel_total']}条
- AI分析商机：{metrics['leads_analyzed']}条
- 相关商机：{metrics['leads_relevant']}条
- 转入CRM：{metrics['leads_converted']}条
- 待分析情报库存：{metrics['pending_intel']}条
- 已分析待转入：{metrics['analyzed_not_converted']}条

【今日高价值商机】
{ops_text or '  无'}

【今日转入CRM线索】
{crm_text or '  无'}

请返回JSON格式（不要其他文字）：
{{
  "title": "日报标题（如：AI销售情报日报 2026-08-27）",
  "summary": "200字以内的整体摘要，概括今日采集、识别、转入情况",
  "recommendations": ["建议1：...", "建议2：...", "建议3：..."]
}}

建议应包含：
1. 高价值商机的跟进建议
2. 待分析库存的处理建议
3. CRM线索分配建议
"""

    return prompt


def generate_daily_report(report_date=None, db=None):
    """生成 AI 日报。

    Args:
        report_date: 报告日期 YYYY-MM-DD（默认今天）
        db: 数据库连接（可选）

    Returns:
        dict: 日报数据
    """
    if report_date is None:
        report_date = date.today().isoformat()

    from config import USE_LLM

    own_conn = False
    if db is None:
        from extensions import DB_PATH
        db = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
        db.row_factory = sqlite3.Row
        own_conn = True

    try:
        # 检查是否已生成
        existing = db.execute(
            "SELECT id FROM ai_daily_reports WHERE report_date=?", (report_date,)
        ).fetchone()
        if existing:
            # 已存在则更新（覆盖）
            db.execute("DELETE FROM ai_daily_reports WHERE report_date=?", (report_date,))
            db.commit()

        # 收集指标
        metrics = _collect_metrics(db, report_date)

        # 调用 LLM 生成摘要和建议
        summary = ''
        recommendations = []
        title = f'AI销售情报日报 {report_date}'

        if USE_LLM:
            try:
                from qa_engine import call_llm
                prompt = _build_prompt(metrics, report_date)
                messages = [
                    {'role': 'system', 'content': '你是一个专业的销售情报分析师，负责生成每日销售情报日报。只返回JSON。'},
                    {'role': 'user', 'content': prompt},
                ]
                content = call_llm(messages, max_tokens=4000, timeout=60, enable_thinking=False)
                if content:
                    result = _extract_json(content)
                    if result:
                        title = result.get('title', title)
                        summary = result.get('summary', '')
                        recommendations = result.get('recommendations', [])
            except Exception as e:
                logger.error(f'LLM日报生成失败: {e}')

        # 降级：无 LLM 时用模板生成
        if not summary:
            summary = _generate_summary_template(metrics, report_date)
        if not recommendations:
            recommendations = _generate_recommendations_template(metrics)

        # 构造商机数据
        opportunities = json.dumps(metrics.get('top_opportunities', []), ensure_ascii=False)
        metrics_json = json.dumps({
            'intel_total': metrics['intel_total'],
            'leads_analyzed': metrics['leads_analyzed'],
            'leads_relevant': metrics['leads_relevant'],
            'leads_converted': metrics['leads_converted'],
            'pending_intel': metrics['pending_intel'],
            'analyzed_not_converted': metrics['analyzed_not_converted'],
        }, ensure_ascii=False)

        cursor = db.execute("""
            INSERT INTO ai_daily_reports (
                report_date, title, summary, metrics, opportunities, recommendations, generated_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            report_date, title, summary, metrics_json, opportunities,
            json.dumps(recommendations, ensure_ascii=False),
            'auto' if USE_LLM else 'template',
        ))
        db.commit()
        return {
            'id': cursor.lastrowid,
            'report_date': report_date,
            'title': title,
            'summary': summary,
            'metrics': json.loads(metrics_json),
            'opportunities': metrics.get('top_opportunities', []),
            'recommendations': recommendations,
        }
    except Exception as e:
        logger.error(f'生成日报失败: {e}')
        return None
    finally:
        if own_conn:
            db.close()


def _extract_json(text):
    """从 LLM 输出中提取 JSON。"""
    import re
    if not text:
        return None
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    start = text.find('{')
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
    return None


def _generate_summary_template(metrics, report_date):
    """模板生成摘要（LLM 降级）。"""
    parts = [f'{report_date} AI销售情报日报：']
    if metrics['intel_total']:
        parts.append(f"今日采集{metrics['intel_total']}条原始情报")
    if metrics['leads_analyzed']:
        parts.append(f"AI分析{metrics['leads_analyzed']}条商机（相关{metrics['leads_relevant']}条）")
    if metrics['leads_converted']:
        parts.append(f"转入CRM {metrics['leads_converted']}条")
    parts.append(f"待分析库存{metrics['pending_intel']}条")

    summary = '，'.join(parts) + '。'
    if metrics.get('top_opportunities'):
        summary += f' 今日最高价值商机评分{metrics["top_opportunities"][0]["score"]}分。'
    return summary


def _generate_recommendations_template(metrics):
    """模板生成建议（LLM 降级）。"""
    recs = []
    if metrics['pending_intel'] > 20:
        recs.append(f'待分析情报库存{metrics["pending_intel"]}条，建议尽快执行批量AI分析')
    if metrics.get('top_opportunities'):
        top = metrics['top_opportunities'][0]
        recs.append(f'高价值商机"{top["title"][:30]}"评分{top["score"]}分，建议优先跟进')
    if metrics['analyzed_not_converted'] > 0:
        recs.append(f'已分析待转入CRM {metrics["analyzed_not_converted"]}条，建议批量转入')
    if metrics['leads_converted'] > 0:
        recs.append(f'今日转入CRM {metrics["leads_converted"]}条线索，建议及时分配给销售跟进')
    if not recs:
        recs.append('今日无新增数据，建议检查数据源采集状态')
    return recs
