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
_last_report_date = None  # 上次生成AI日报的日期
_last_analysis_date = None  # 上次执行客户/竞争对手分析的日期


def _open_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def collect_due_intelligence():
    """Phase2: 采集到期的原始情报（插件化采集器 → raw_intelligence）。

    三步短事务模式：
    1. 短连接读取到期源（parser_type 不为空的源才参与采集）
    2. 逐个网络采集（不持 DB 锁）：collect() + fetch_detail()
    3. 逐个短事务写入 raw_intelligence（URL Hash 去重，毫秒级锁）

    返回本次新增情报总数。
    """
    import hashlib
    from utils.cleaner import clean_title, is_junk_content

    # ---- 第1步：短连接读取到期源 ----
    now = datetime.now()
    due_sources = []
    conn = _open_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM lead_sources WHERE enabled=1 AND parser_type IS NOT NULL AND parser_type != ''")
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
        logger.error(f"读取情报源失败: {e}")
        return 0
    finally:
        conn.close()

    if not due_sources:
        return 0

    # ---- 第2步：逐个网络采集（不持任何 DB 锁）----
    collected_items = []  # [(source_id, item), ...]
    for source in due_sources:
        try:
            from collectors import get_collector
            import json as _json

            parser_type = source.get('parser_type', 'ccgp_gov')
            collector_cls = get_collector(parser_type)
            if not collector_cls:
                logger.warning(f"情报源「{source.get('name')}」采集器不存在: {parser_type}")
                continue

            config = {}
            if source.get('config'):
                try:
                    config = _json.loads(source['config'])
                except (ValueError, TypeError):
                    pass

            source_dict = {
                'id': source['id'], 'name': source['name'],
                'url': source.get('url') or '', 'keywords': source.get('keywords') or '',
            }
            collector = collector_cls(source_dict, config)
            items = collector.collect()

            # 抓取详情页（限前 max_detail 个，避免耗时过长）
            max_detail = config.get('max_detail', 10)
            for i, item in enumerate(items):
                if i < max_detail and item.url:
                    item = collector.fetch_detail(item)
                collected_items.append((source['id'], item))

            logger.info(f"情报源「{source.get('name')}」采集 {len(items)} 条")
        except Exception as e:
            logger.error(f"情报源「{source.get('name')}」采集失败: {e}")

    if not collected_items:
        return 0

    # ---- 第3步：逐个短事务写入（毫秒级锁）----
    total_new = 0
    wconn = _open_db()
    try:
        wcur = wconn.cursor()
        for source_id, item in collected_items:
            try:
                title = clean_title(item.title) if item.title else ''
                if is_junk_content(item.content, title):
                    continue

                url_hash = hashlib.md5(item.url.encode()).hexdigest() if item.url else None
                if url_hash:
                    existing = wcur.execute(
                        "SELECT id FROM raw_intelligence WHERE url_hash=?", (url_hash,)
                    ).fetchone()
                    if existing:
                        continue

                content_hash = hashlib.md5((item.content or '').encode()).hexdigest()[:16] if item.content else None
                att_path = ','.join(item.attachment_urls) if hasattr(item, 'attachment_urls') and item.attachment_urls else ''

                wcur.execute("""
                    INSERT INTO raw_intelligence (source_id, url, url_hash, title, content,
                                                  publish_date, content_hash, status, snippet, attachment_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """, (source_id, item.url, url_hash, title, item.content or '',
                      item.publish_date or '', content_hash,
                      getattr(item, 'snippet', '') or '', att_path))
                total_new += 1
            except Exception as e:
                logger.error(f"情报入库失败: {e}")

        # 更新源的最后采集时间
        source_ids = set(sid for sid, _ in collected_items)
        for sid in source_ids:
            wcur.execute("UPDATE lead_sources SET last_scraped_at=CURRENT_TIMESTAMP WHERE id=?", (sid,))

        wconn.commit()
        if total_new > 0:
            logger.info(f"情报采集完成：新增 {total_new} 条原始情报")
    except Exception as e:
        wconn.rollback()
        logger.error(f"情报批量入库失败: {e}")
    finally:
        wconn.close()

    return total_new


def run_scheduler():
    global scheduler_running, _last_cleanup
    logger.info("定时任务调度器已启动")

    # 调度循环：每 1 小时检查一次情报采集；客户清理每 24 小时一次
    check_interval = 3600
    while scheduler_running:
        try:
            now = datetime.now()

            # 1. 原始情报采集（唯一采集链路：插件化采集器 → 关键词过滤 → raw_intelligence，
            #    再由 AI商机识别分析后转入线索队列；不再直接抓取写入 scraped_leads）
            try:
                collected = collect_due_intelligence()
            except Exception as e:
                logger.error(f"情报采集任务错误: {e}")
                collected = 0

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

            # 2.5 AI日报生成（每天 18:00-19:00 自动生成一次）
            try:
                today_str = now.strftime('%Y-%m-%d')
                if now.hour >= 18 and _last_report_date != today_str:
                    from ai_daily_report import generate_daily_report
                    report = generate_daily_report(today_str)
                    if report:
                        logger.info(f"AI日报已生成: {today_str}")
                        _last_report_date = today_str
            except Exception as e:
                logger.error(f"AI日报生成失败: {e}")

            # 2.6 客户画像+竞争对手+销售提醒（每天 19:00-20:00 自动执行一次）
            try:
                today_str = now.strftime('%Y-%m-%d')
                if now.hour >= 19 and _last_analysis_date != today_str:
                    from ai_analysis import run_full_analysis
                    result = run_full_analysis()
                    logger.info(f"分析完成: 客户{result['customer_profiles']} 竞争对手{result['competitor_profiles']} 提醒{result['sales_alerts']}")
                    _last_analysis_date = today_str
            except Exception as e:
                logger.error(f"客户/竞争对手分析失败: {e}")

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
