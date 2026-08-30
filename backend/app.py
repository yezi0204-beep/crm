import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, send_from_directory, jsonify, request
import logging

from config import SERVER_HOST, SERVER_PORT
from extensions import (
    SECRET_KEY, DB_PATH, BASE_DIR, UPLOAD_DIR,
    setup_extensions, get_db, record_operation_log, ensure_tables, user_can
)
from routes import register_blueprints
from scheduler import start_scheduler, stop_scheduler, run_cleanup_now, scheduler_running

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY

setup_extensions(app)

register_blueprints(app)

USE_LLM = False

def init_llm():
    global USE_LLM
    try:
        from config import LLM_API_BASE
        USE_LLM = bool(LLM_API_BASE)
        logger.info(f"LLM support: {'enabled' if USE_LLM else 'disabled'}")
    except Exception as e:
        logger.warning(f"Failed to initialize LLM: {e}")
        USE_LLM = False

init_llm()

# 应用启动时预建所有表，确保调度器在请求上下文外运行时表已就绪
# （lead_sources/scraped_leads 等表在 get_db() 首次请求时才创建，调度器会先用到）
ensure_tables()

# 通过 gunicorn 等应用服务器启动时（非 python app.py 直跑），由环境变量
# CRM_START_SCHEDULER=1 控制是否在应用进程内启动后台调度器。
# 注意：必须单 worker 运行（--workers 1），否则调度器会重复执行。
if os.environ.get('CRM_START_SCHEDULER') == '1':
    start_scheduler()

@app.route('/uploads/<path:filename>')
def serve_uploads(filename):
    # 附件下载需携带有效 token（支持 Authorization 头或 ?token= 查询参数）
    from extensions import verify_token
    token = request.headers.get('Authorization', '').replace('Bearer ', '') or request.args.get('token', '')
    if not verify_token(token):
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None}), 401
    return send_from_directory(UPLOAD_DIR, filename)

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'ok',
        'database': os.path.exists(DB_PATH),
        'llm_enabled': USE_LLM,
        'scheduler': 'running' if scheduler_running else 'stopped'
    })

@app.route('/api/system/cleanup', methods=['POST'])
def trigger_cleanup():
    from extensions import verify_token
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})

    role = payload.get('role', '')
    if not user_can(payload['username'], 'data.view_all'):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    # 公海池客户"超过100天自动删除"功能已取消，不再清理客户数据
    run_cleanup_now()

    record_operation_log(payload['username'], '手动清理', '客户',
        '公海池客户自动删除功能已停用，未执行清理操作')

    return jsonify({
        'code': 200,
        'message': '公海池客户自动删除功能已停用，无需清理',
        'data': {'deleted_count': 0}
    })

import atexit
atexit.register(stop_scheduler)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CRM Backend Server')
    parser.add_argument('--host', default=SERVER_HOST, help='Server host (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=SERVER_PORT, help='Server port (default: 5000)')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--no-scheduler', action='store_true', help='Disable background scheduler')
    args = parser.parse_args()

    # 按 --no-scheduler 参数决定是否启动调度器
    # 调度器会执行耗时的网络请求（如 LLM 调用），可能长时间持有数据库锁
    if not args.no_scheduler:
        start_scheduler()

    logger.info(f"Starting CRM server on {args.host}:{args.port}")
    logger.info(f"Database: {DB_PATH}")
    # threaded=True：开发服务器多线程，确保即使有耗时的同步请求（如 LLM 调用）
    # 也不会阻塞登录等其他短请求
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
