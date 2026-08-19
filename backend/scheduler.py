import threading
import time
import logging
import sqlite3
from datetime import datetime, timedelta
from extensions import DB_PATH

logger = logging.getLogger(__name__)

scheduler_thread = None
scheduler_running = False
_last_cleanup = None  # 上次执行过期线索清理时间


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

    重要：网络抓取（_scrape_source）必须在数据库事务之外进行，
    否则 INSERT 开启的写锁会持续到 commit，期间任何并发写（如登录）
    都会因等待锁超时报 "database is locked"。
    """
    try:
        from routes.leads import _scrape_source, _persist_leads, _mark_scraped
    except Exception as e:
        logger.error(f"线索抓取模块加载失败: {e}")
        return 0

    now = datetime.now()

    # ---- 第1步：短连接读取到期源，立即释放锁 ----
    due_sources = []
    conn = _open_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM lead_sources WHERE enabled=1")
        sources = [dict(r) for r in cursor.fetchall()]
        for source in sources:
            due = True
            if source.get('last_scraped_at'):
                try:
                    last = datetime.strptime(source['last_scraped_at'], '%Y-%m-%d %H:%M:%S')
                    interval = timedelta(hours=int(source.get('interval_hours', 24) or 24))
                    due = (now - last) >= interval
                except Exception:
                    due = True
            if due:
                due_sources.append(source)
    except Exception as e:
        logger.error(f"读取线索源失败: {e}")
    finally:
        conn.close()

    # ---- 第2步：逐个网络抓取（不持任何 DB 锁）----
    scraped_results = []  # [(source, leads_data, err), ...]
    for source in due_sources:
        try:
            leads_data, err = _scrape_source(source)
            scraped_results.append((source, leads_data, err))
        except Exception as e:
            logger.error(f"线索源「{source.get('name')}」抓取失败: {e}")
            scraped_results.append((source, [], str(e)))

    # ---- 第3步：逐个短事务写入（写锁只持毫秒级）----
    total = 0
    for source, leads_data, err in scraped_results:
        wconn = _open_db()
        try:
            wcur = wconn.cursor()
            inserted = _persist_leads(wcur, leads_data, source['id'], source['name'])
            _mark_scraped(wcur, source['id'])
            wconn.commit()
            total += inserted
            if err:
                logger.warning(f"线索源「{source['name']}」抓取异常: {err}")
            elif inserted > 0:
                logger.info(f"线索源「{source['name']}」抓取 {inserted} 条线索")
        except Exception as e:
            wconn.rollback()
            logger.error(f"线索源「{source.get('name')}」入库失败: {e}")
        finally:
            wconn.close()

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

            # 2. 过期线索清理（每天一次：>30天的未分配线索 + 已过截止日期的军采线索）
            # 注：公海池客户"超过100天自动删除"功能已取消，不再自动清理客户数据
            if _last_cleanup is None or (now - _last_cleanup) >= timedelta(hours=24):
                logger.info(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] 检查是否需要执行每日清理任务...")
                try:
                    from routes.leads import _cleanup_expired_leads
                    lead_conn = _open_db()
                    lead_cursor = lead_conn.cursor()
                    lead_deleted = _cleanup_expired_leads(lead_cursor, days=30)
                    lead_conn.commit()
                    lead_conn.close()
                    if lead_deleted > 0:
                        logger.info(f"已清理 {lead_deleted} 条过期线索（>30天或已过截止日期）")
                except Exception as e:
                    logger.error(f"过期线索清理失败: {e}")
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
    """手动触发清理任务。

    公海池客户"超过100天自动删除"功能已取消，不再清理客户数据。
    保留函数签名以兼容 app.py 的 /api/system/cleanup 接口调用，但实际不执行任何删除操作。
    """
    logger.info("手动清理请求已忽略：公海池客户自动删除功能已停用")
    return 0


def run_scrape_now():
    """手动触发线索抓取。"""
    logger.info("手动触发线索抓取任务")
    return scrape_due_lead_sources()
