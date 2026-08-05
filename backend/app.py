import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, send_from_directory, jsonify, request
import logging

from config import SERVER_HOST, SERVER_PORT
from extensions import (
    SECRET_KEY, DB_PATH, BASE_DIR, UPLOAD_DIR,
    setup_extensions, get_db, record_operation_log, ensure_tables
)
from routes import register_blueprints
from scheduler import start_scheduler, stop_scheduler, run_cleanup_now

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
        from config import LLM_API_KEY
        USE_LLM = bool(LLM_API_KEY)
        logger.info(f"LLM support: {'enabled' if USE_LLM else 'disabled'}")
    except Exception as e:
        logger.warning(f"Failed to initialize LLM: {e}")
        USE_LLM = False

init_llm()

# 应用启动时预建所有表，确保调度器在请求上下文外运行时表已就绪
# （lead_sources/scraped_leads 等表在 get_db() 首次请求时才创建，调度器会先用到）
ensure_tables()

start_scheduler()

@app.route('/uploads/<path:filename>')
def serve_uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'ok',
        'database': os.path.exists(DB_PATH),
        'llm_enabled': USE_LLM,
        'scheduler': 'running'
    })

@app.route('/api/system/cleanup', methods=['POST'])
def trigger_cleanup():
    from extensions import verify_token
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
    
    role = payload.get('role', '')
    if role not in ('主任', '院长'):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    
    deleted_count = run_cleanup_now()
    
    record_operation_log(payload['username'], '手动清理', '客户', 
        f'手动清理了 {deleted_count} 个超过 100 天未跟进的客户')
    
    return jsonify({
        'code': 200, 
        'message': '清理完成', 
        'data': {'deleted_count': deleted_count}
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

    if args.no_scheduler:
        stop_scheduler()

    logger.info(f"Starting CRM server on {args.host}:{args.port}")
    logger.info(f"Database: {DB_PATH}")
    app.run(host=args.host, port=args.port, debug=args.debug)
