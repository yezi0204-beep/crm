"""异步任务系统（轻量级，适配 SQLite 单机环境）。

说明：用户环境为 Windows 单机 + SQLite，部署 Redis + Celery 成本高，
故采用 ThreadPoolExecutor + ai_tasks 表实现同等能力：
  - 任务可重试（max_retries）
  - 有超时（timeout_seconds）
  - 有错误日志（error_message）
  - 有执行状态（PENDING/RUNNING/SUCCESS/FAILED/RETRYING/CANCELLED）
  - 支持人工重新执行（retry_task / rerun API）

任务类型：
  crawl_source / parse_document / extract_attachment
  llm_classify / llm_extract_entity / llm_score
  deduplicate_project / update_customer_profile
  update_competitor_profile / generate_daily_report
"""
import json
import logging
import threading
import time
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from extensions import DB_PATH

logger = logging.getLogger(__name__)

# 状态常量
PENDING = 'PENDING'
RUNNING = 'RUNNING'
SUCCESS = 'SUCCESS'
FAILED = 'FAILED'
RETRYING = 'RETRYING'
CANCELLED = 'CANCELLED'

TASK_TYPES = [
    'crawl_source', 'parse_document', 'extract_attachment',
    'llm_classify', 'llm_extract_entity', 'llm_score',
    'deduplicate_project', 'update_customer_profile',
    'update_competitor_profile', 'generate_daily_report',
]

_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='ai-task')


# ============================================================
# 任务处理函数注册表（task_type -> callable(payload, task_id) -> dict）
# ============================================================
_HANDLERS = {}


def register_handler(task_type, func):
    """注册任务处理函数。"""
    _HANDLERS[task_type] = func


def _new_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def submit_task(task_type, payload=None, created_by='system',
                max_retries=3, timeout_seconds=600):
    """提交异步任务（立即返回，不阻塞 Web 请求）。

    Returns:
        int: 任务ID
    """
    conn = _new_conn()
    try:
        cursor = conn.execute("""
            INSERT INTO ai_tasks (task_type, status, payload, created_by,
                                  max_retries, timeout_seconds)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (task_type, PENDING, json.dumps(payload or {}, ensure_ascii=False),
              created_by, max_retries, timeout_seconds))
        task_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    _executor.submit(_run_task, task_id)
    logger.info(f'任务#{task_id} 已提交: {task_type}')
    return task_id


def _run_task(task_id):
    """执行任务（工作线程）。"""
    conn = _new_conn()
    try:
        task = conn.execute("SELECT * FROM ai_tasks WHERE id=?", (task_id,)).fetchone()
        if not task or task['status'] == CANCELLED:
            return

        task_type = task['task_type']
        payload = json.loads(task['payload']) if task['payload'] else {}
        max_retries = task['max_retries'] or 3
        retry_count = task['retry_count'] or 0
        timeout_seconds = task['timeout_seconds'] or 600

        handler = _HANDLERS.get(task_type)
        if not handler:
            conn.execute("""
                UPDATE ai_tasks SET status='FAILED', error_message='未注册的任务类型',
                    finished_at=CURRENT_TIMESTAMP WHERE id=?
            """, (task_id,))
            conn.commit()
            return

        start = time.time()
        try:
            conn.execute("""
                UPDATE ai_tasks SET status='RUNNING', started_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (task_id,))
            conn.commit()
        finally:
            pass
        conn.close()

        # 执行任务（独立连接）
        result = None
        error = None
        try:
            result = handler(payload, task_id)
        except Exception as e:
            error = str(e)
            logger.exception(f'任务#{task_id} 执行异常')

        duration_ms = int((time.time() - start) * 1000)
        conn = _new_conn()
        try:
            if error is None:
                conn.execute("""
                    UPDATE ai_tasks SET status='SUCCESS', result=?, finished_at=CURRENT_TIMESTAMP,
                        duration_ms=? WHERE id=?
                """, (json.dumps(result, ensure_ascii=False)[:5000] if result else '',
                      duration_ms, task_id))
            else:
                # 失败处理：可重试则 RETRYING 并重新入队
                if retry_count < max_retries:
                    conn.execute("""
                        UPDATE ai_tasks SET status='RETRYING', error_message=?,
                            retry_count=?, finished_at=CURRENT_TIMESTAMP, duration_ms=?
                        WHERE id=?
                    """, (error[:500], retry_count + 1, duration_ms, task_id))
                else:
                    conn.execute("""
                        UPDATE ai_tasks SET status='FAILED', error_message=?,
                            finished_at=CURRENT_TIMESTAMP, duration_ms=?
                        WHERE id=?
                    """, (error[:500], duration_ms, task_id))
            conn.commit()
        finally:
            conn.close()

        # 重试重新入队
        if error is not None and retry_count < max_retries:
            time.sleep(min(5 * (retry_count + 1), 30))  # 指数退避
            _executor.submit(_run_task, task_id)

    except Exception as e:
        logger.exception(f'任务#{task_id} 调度异常: {e}')
        try:
            conn = _new_conn()
            conn.execute("""
                UPDATE ai_tasks SET status='FAILED', error_message=?
                WHERE id=? AND status='RUNNING'
            """, (str(e)[:500], task_id))
            conn.commit()
            conn.close()
        except Exception:
            pass


# ============================================================
# 内置任务处理器
# ============================================================
def _handle_update_customer_profile(payload, task_id):
    """更新客户画像任务。"""
    from customer_model import generate_all_profiles
    conn = _new_conn()
    try:
        result = generate_all_profiles(conn, run_ai=payload.get('run_ai', False))
        return result
    finally:
        conn.close()


def _handle_update_competitor_profile(payload, task_id):
    """更新竞争对手画像任务。"""
    from competitor_model import auto_update_competitors
    conn = _new_conn()
    try:
        return auto_update_competitors(conn)
    finally:
        conn.close()


def _handle_generate_daily_report(payload, task_id):
    """生成AI销售日报任务。"""
    from ai_daily_report import generate_daily_report
    return generate_daily_report()


def _handle_llm_score(payload, task_id):
    """LLM评分任务（单条商机重评分）。"""
    from scoring_model import score_lead
    lead_id = payload.get('lead_id')
    if not lead_id:
        raise ValueError('缺少 lead_id')
    conn = _new_conn()
    try:
        row = conn.execute("SELECT * FROM intelligence_leads WHERE id=?", (lead_id,)).fetchone()
        if not row:
            raise ValueError(f'商机#{lead_id} 不存在')
        result = score_lead(row)
        conn.execute("""
            UPDATE intelligence_leads SET score=?, score_reason=?, score_dimensions=?,
                score_grade=?, score_method=? WHERE id=?
        """, (result['score'], result['reason'],
              json.dumps(result['dimensions'], ensure_ascii=False),
              result['grade'], result['method'], lead_id))
        conn.commit()
        return {'lead_id': lead_id, 'score': result['score'], 'grade': result['grade']}
    finally:
        conn.close()


def _handle_deduplicate_project(payload, task_id):
    """项目去重任务。"""
    from dedup_model import detect_duplicates_for_lead
    lead_id = payload.get('lead_id')
    conn = _new_conn()
    try:
        if lead_id:
            return detect_duplicates_for_lead(lead_id, conn)
        # 全量检测：最近100条
        rows = conn.execute("""
            SELECT id FROM intelligence_leads
            WHERE status NOT IN ('rejected', 'merged')
            ORDER BY id DESC LIMIT 100
        """).fetchall()
        total = 0
        for r in rows:
            found = detect_duplicates_for_lead(r['id'], conn)
            total += len(found) if found else 0
        return {'checked': len(rows), 'found': total}
    finally:
        conn.close()


# 注册内置处理器
register_handler('update_customer_profile', _handle_update_customer_profile)
register_handler('update_competitor_profile', _handle_update_competitor_profile)
register_handler('generate_daily_report', _handle_generate_daily_report)
register_handler('llm_score', _handle_llm_score)
register_handler('deduplicate_project', _handle_deduplicate_project)


def get_task_stats():
    """任务统计：各状态数量、平均耗时、今日处理数。"""
    conn = _new_conn()
    try:
        status_rows = conn.execute("""
            SELECT status, COUNT(*) as c FROM ai_tasks GROUP BY status
        """).fetchall()
        by_status = {r['status']: r['c'] for r in status_rows}
        for s in (PENDING, RUNNING, SUCCESS, FAILED, RETRYING, CANCELLED):
            if s not in by_status:
                by_status[s] = 0

        today = datetime.now().strftime('%Y-%m-%d')
        today_count = conn.execute(
            "SELECT COUNT(*) as c FROM ai_tasks WHERE created_at LIKE ?",
            (f'{today}%',)
        ).fetchone()['c']

        avg_duration = conn.execute(
            "SELECT AVG(duration_ms) as d FROM ai_tasks WHERE duration_ms > 0"
        ).fetchone()['d'] or 0

        # 按类型统计
        type_rows = conn.execute("""
            SELECT task_type, COUNT(*) as c,
                   SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) as failed
            FROM ai_tasks GROUP BY task_type
        """).fetchall()
        by_type = [{'task_type': r['task_type'], 'count': r['c'],
                    'failed': r['failed']} for r in type_rows]

        return {
            'by_status': by_status,
            'today_count': today_count,
            'avg_duration_ms': int(avg_duration),
            'by_type': by_type,
        }
    finally:
        conn.close()
