"""LLM Gateway：统一 LLM 接口层。

设计原则：业务代码不直接调用 LLM API，统一走本网关。
- 支持多 Provider：OpenAI Compatible / vLLM / Ollama（均为 OpenAI 兼容格式）
- 配置化：LLM_PROVIDER / LLM_BASE_URL / LLM_MODEL / EMBEDDING_MODEL / LLM_API_KEY
- 自动记录 AI 操作日志：model_name / prompt_version / token_usage / latency / error
- 更换模型无需修改业务代码

对外接口：
    gateway_chat(messages, ...)       -> str|None（对话补全）
    gateway_analyze(prompt, ...)      -> str|None（分析，带系统提示）
    gateway_embedding(texts)          -> list[list[float]]|None（向量）
"""
import json
import logging
import time
import requests

from config import (
    LLM_API_KEY, LLM_API_BASE, LLM_MODEL,
    LLM_PROVIDER, EMBEDDING_MODEL, USE_LLM,
)

logger = logging.getLogger(__name__)

PROMPT_VERSION = 'v1'


# ============================================================
# 核心调用
# ============================================================
def _base_url():
    """按 Provider 返回基础 URL。"""
    base = LLM_API_BASE.rstrip('/')
    if LLM_PROVIDER == 'ollama' and not base.endswith('/v1'):
        base = f'{base}/v1'
    return base


def _headers():
    return {
        'Authorization': f'Bearer {LLM_API_KEY}' if LLM_API_KEY else '',
        'Content-Type': 'application/json',
    }


def _log_ai_operation(operation_type, data_source, model_name, token_usage,
                      latency_ms, status, error_message='', result_summary='',
                      operator=None):
    """记录 AI 操作日志（独立连接，毫秒级提交）。"""
    try:
        from extensions import DB_PATH
        import sqlite3
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.execute("""
            INSERT INTO ai_operation_logs (
                operator_id, operator_name, operation_type, data_source,
                model_name, prompt_version, token_usage, latency, status,
                error_message, result_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            operator.get('id') if operator else None,
            operator.get('username') if operator else 'system',
            operation_type, data_source, model_name, PROMPT_VERSION,
            token_usage, latency_ms, status,
            (error_message or '')[:500], (result_summary or '')[:200],
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f'AI操作日志记录失败: {e}')


def gateway_chat(messages, max_tokens=4000, timeout=60, enable_thinking=False,
                 operation_type='chat', data_source='', prompt_version=PROMPT_VERSION,
                 operator=None):
    """统一对话补全接口。

    Returns:
        str|None: LLM 回复内容，失败返回 None（不抛异常，业务可降级）
    """
    if not USE_LLM or not LLM_API_KEY:
        return None

    payload = {
        'model': LLM_MODEL,
        'messages': messages,
        'temperature': 0.1,
        'stream': False,
        'max_tokens': max_tokens,
    }
    if not enable_thinking:
        payload['chat_template_kwargs'] = {'enable_thinking': False}

    start = time.time()
    status, error, content, token_usage = 'success', '', None, 0
    try:
        resp = requests.post(
            f'{_base_url()}/chat/completions',
            headers=_headers(), json=payload, timeout=timeout,
        )
        latency_ms = int((time.time() - start) * 1000)
        if resp.status_code == 200:
            data = resp.json()
            msg = data['choices'][0]['message']
            content = msg.get('content')
            if not content:
                reasoning = msg.get('reasoning', '')
                if reasoning:
                    content = _extract_json_from_text(reasoning)
            usage = data.get('usage', {})
            token_usage = usage.get('total_tokens', 0)
            if not content:
                status = 'failed'
                error = 'LLM返回内容为空'
        else:
            status = 'failed'
            error = f'HTTP {resp.status_code}: {resp.text[:200]}'
    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        status = 'failed'
        error = str(e)

    summary = (content[:150] if content else '')
    _log_ai_operation(operation_type, data_source, LLM_MODEL, token_usage,
                      latency_ms, status, error, summary, operator)
    return content


def _extract_json_from_text(text):
    """从思考文本中提取 JSON。"""
    if not text:
        return None
    import re
    m = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text[:2000]


def gateway_analyze(prompt, system_prompt=None, max_tokens=4000, timeout=60,
                    data_source='', operation_type='analyze', operator=None):
    """统一分析接口。"""
    messages = []
    if system_prompt:
        messages.append({'role': 'system', 'content': system_prompt})
    messages.append({'role': 'user', 'content': prompt})
    return gateway_chat(messages, max_tokens=max_tokens, timeout=timeout,
                        operation_type=operation_type, data_source=data_source,
                        operator=operator)


def gateway_embedding(texts, data_source='', operator=None):
    """统一向量接口。

    Args:
        texts: list[str] 或 str

    Returns:
        list[list[float]]|None
    """
    if isinstance(texts, str):
        texts = [texts]
    if not texts:
        return None

    start = time.time()
    status, error, result = 'success', '', None
    try:
        resp = requests.post(
            f'{_base_url()}/embeddings',
            headers=_headers(),
            json={'model': EMBEDDING_MODEL, 'input': texts},
            timeout=60,
        )
        latency_ms = int((time.time() - start) * 1000)
        if resp.status_code == 200:
            data = resp.json()
            result = [item['embedding'] for item in data['data']]
        else:
            status = 'failed'
            error = f'HTTP {resp.status_code}: {resp.text[:200]}'
    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        status = 'failed'
        error = str(e)

    _log_ai_operation('embedding', data_source, EMBEDDING_MODEL, 0,
                      latency_ms, status, error, f'{len(texts)}条向量', operator)
    return result


# ============================================================
# REST 接口
# ============================================================
def register_routes(app):
    from flask import Blueprint, request, jsonify
    from extensions import token_required

    ai_bp = Blueprint('ai_gateway', __name__)

    @ai_bp.route('/chat', methods=['POST'])
    @token_required
    def ai_chat():
        """POST /api/ai/chat {messages: [...], max_tokens?, timeout?}"""
        data = request.get_json(silent=True) or {}
        messages = data.get('messages')
        if not messages:
            return jsonify({'code': 400, 'message': '缺少 messages'})
        content = gateway_chat(
            messages,
            max_tokens=data.get('max_tokens', 4000),
            timeout=data.get('timeout', 60),
            operation_type='api_chat',
            data_source='api',
            operator=request.current_user,
        )
        return jsonify({'code': 200, 'data': {'content': content}})

    @ai_bp.route('/analyze', methods=['POST'])
    @token_required
    def ai_analyze():
        """POST /api/ai/analyze {prompt, system_prompt?, max_tokens?}"""
        data = request.get_json(silent=True) or {}
        prompt = (data.get('prompt') or '').strip()
        if not prompt:
            return jsonify({'code': 400, 'message': '缺少 prompt'})
        content = gateway_analyze(
            prompt,
            system_prompt=data.get('system_prompt'),
            max_tokens=data.get('max_tokens', 4000),
            timeout=data.get('timeout', 60),
            data_source='api',
            operation_type='api_analyze',
            operator=request.current_user,
        )
        return jsonify({'code': 200, 'data': {'content': content}})

    @ai_bp.route('/embedding', methods=['POST'])
    @token_required
    def ai_embedding():
        """POST /api/ai/embedding {texts: [...]}"""
        data = request.get_json(silent=True) or {}
        texts = data.get('texts')
        if not texts:
            return jsonify({'code': 400, 'message': '缺少 texts'})
        vectors = gateway_embedding(texts, data_source='api',
                                    operator=request.current_user)
        return jsonify({'code': 200, 'data': {'vectors': vectors}})

    app.register_blueprint(ai_bp, url_prefix='/api/ai')
