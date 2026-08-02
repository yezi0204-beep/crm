import threading
import time
import logging
import sqlite3
from datetime import datetime, timedelta
from extensions import cleanup_inactive_customers, DB_PATH

logger = logging.getLogger(__name__)

scheduler_thread = None
scheduler_running = False
_last_cleanup = None  # 上次执行客户清理时间


def _open_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def scrape_due_lead_sources():
    """抓取所有到期的启用线索源（按 interval_hours 判断）。

    供调度器定时调用，也可被 run_scrape_now 手动触发。
    返回本次抓取的线索总数。
    """
    try:
        from routes.leads import _scrape_source, _persist_leads, _mark_scraped
    except Exception as e:
        logger.error(f"线索抓取模块加载失败: {e}")
        return 0

    conn = _open_db()
    cursor = conn.cursor()
    now = datetime.now()
    total = 0
    try:
        cursor.execute("SELECT * FROM lead_sources WHERE enabled=1")
        sources = [dict(r) for r in cursor.fetchall()]
        for source in sources:
            # 判断是否到期（last_scraped_at 为空或超过 interval_hours）
            due = True
            if source.get('last_scraped_at'):
                try:
                    last = datetime.strptime(source['last_scraped_at'], '%Y-%m-%d %H:%M:%S')
                    interval = timedelta(hours=int(source.get('interval_hours', 24) or 24))
                    due = (now - last) >= interval
                except Exception:
                    due = True
            if not due:
                continue
            try:
                leads_data, err = _scrape_source(source)
                inserted = _persist_leads(cursor, leads_data, source['id'], source['name'])
                _mark_scraped(cursor, source['id'])
                total += inserted
                if err:
                    logger.warning(f"线索源「{source['name']}」抓取异常: {err}")
                elif inserted > 0:
                    logger.info(f"线索源「{source['name']}」抓取 {inserted} 条线索")
            except Exception as e:
                logger.error(f"线索源「{source.get('name')}」抓取失败: {e}")
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"定时线索抓取错误: {e}")
    finally:
        conn.close()
    return total


def run_scheduler():
    global scheduler_running, _last_cleanup
    logger.info("定时任务调度器已启动")

    # 调度循环：每 1 小时检查一次线索抓取；客户清理每 24 小时一次
    check_interval = 3600
    while scheduler_running:
        try:
            now = datetime.now()

            # 1. 线索抓取（按各源 interval_hours 到期抓取）
            try:
                scraped = scrape_due_lead_sources()
            except Exception as e:
                logger.error(f"线索抓取任务错误: {e}")
                scraped = 0

            # 2. 客户清理（每 24 小时一次）
            if _last_cleanup is None or (now - _last_cleanup) >= timedelta(hours=24):
                logger.info(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] 检查是否需要执行每日清理任务...")
                deleted_count = cleanup_inactive_customers()
                if deleted_count > 0:
                    logger.info(f"已自动清理 {deleted_count} 个超过 100 天未跟进的客户")
                else:
                    logger.info("没有需要清理的客户")
                _last_cleanup = now

        except Exception as e:
            logger.error(f"定时任务执行错误: {e}")

        time.sleep(check_interval)


def start_scheduler():
    global scheduler_thread, scheduler_running
    if not scheduler_running:
        scheduler_running = True
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        logger.info("定时任务调度器已启动")


def stop_scheduler():
    global scheduler_running
    scheduler_running = False
    logger.info("定时任务调度器已停止")


def run_cleanup_now():
    logger.info("手动触发清理任务")
    deleted_count = cleanup_inactive_customers()
    return deleted_count


def run_scrape_now():
    """手动触发线索抓取。"""
    logger.info("手动触发线索抓取任务")
    return scrape_due_lead_sources()
