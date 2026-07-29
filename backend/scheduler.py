import threading
import time
import logging
from datetime import datetime
from extensions import cleanup_inactive_customers

logger = logging.getLogger(__name__)

scheduler_thread = None
scheduler_running = False

def run_scheduler():
    global scheduler_running
    logger.info("定时任务调度器已启动")
    
    while scheduler_running:
        try:
            now = datetime.now()
            logger.info(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] 检查是否需要执行每日清理任务...")
            
            deleted_count = cleanup_inactive_customers()
            if deleted_count > 0:
                logger.info(f"已自动清理 {deleted_count} 个超过 100 天未跟进的客户")
            else:
                logger.info("没有需要清理的客户")
            
        except Exception as e:
            logger.error(f"定时任务执行错误: {e}")
        
        time.sleep(86400)


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
