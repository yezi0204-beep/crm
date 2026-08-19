"""
身份安全 API（7.1.1 ~ 7.1.4 对应的 HTTP 接口）
=========================================
所有接口均要求登录（token_required），敏感接口需要管理员权限。

接口总览：
  7.1.1 机密性
    POST /api/security/aes/encrypt     —— AES 加密
    POST /api/security/aes/decrypt     —— AES 解密
    POST /api/security/rsa/encrypt     —— RSA 加密（公钥加密）
    POST /api/security/hybrid/encrypt  —— 混合加密
    POST /api/security/hybrid/decrypt  —— 混合解密

  7.1.2 完整性
    POST /api/security/digest/sha256   —— SHA-256 数字摘要
    POST /api/security/hmac/sign       —— HMAC 生成
    POST /api/security/hmac/verify     —— HMAC 校验
    POST /api/security/profile/check   —— 用户资料完整性校验

  7.1.3 真实性
    GET  /api/security/certificate     —— 获取服务端 X.509 证书
    GET  /api/security/certificate/info —— 证书详情
    POST /api/security/token/issue     —— 签发证书身份令牌（管理员）
    POST /api/security/token/verify    —— 验证证书身份令牌

  7.1.4 不可抵赖性
    POST /api/security/sign            —— RSA-PSS 数字签名
    POST /api/security/verify          —— RSA-PSS 签名验证
    POST /api/security/operation/log   —— 对一条操作记录进行签名存证
    GET  /api/security/operation/logs  —— 查询操作签名日志（含摘要/签名）
    POST /api/security/operation/verify —— 验证一条操作记录签名是否有效
"""

from flask import request, jsonify
from datetime import datetime

from extensions import get_db, token_required, admin_required, record_operation_log
from security import (
    get_confidentiality, get_integrity, get_authenticity, get_non_repudiation,
)
from . import security_bp


# ================================================================
# 7.1.1 机密性
# ================================================================

@security_bp.route('/api/security/aes/encrypt', methods=['POST'])
@token_required
def aes_encrypt():
    """AES-256-GCM 加密。Body: { "plaintext": "..." }"""
    data = request.get_json(silent=True) or {}
    plaintext = data.get('plaintext')
    if not isinstance(plaintext, str) and not isinstance(plaintext, bytes):
        return jsonify({'code': 400, 'message': '缺少 plaintext 字段', 'data': None})
    enc = get_confidentiality()
    try:
        ciphertext = enc.aes_encrypt(plaintext)
        return jsonify({'code': 200, 'message': 'success',
                        'data': {'ciphertext_b64': ciphertext, 'algorithm': 'AES-256-GCM'}})
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@security_bp.route('/api/security/aes/decrypt', methods=['POST'])
@token_required
def aes_decrypt():
    """AES-256-GCM 解密。Body: { "ciphertext_b64": "..." }"""
    data = request.get_json(silent=True) or {}
    ct = data.get('ciphertext_b64')
    if not isinstance(ct, str):
        return jsonify({'code': 400, 'message': '缺少 ciphertext_b64', 'data': None})
    enc = get_confidentiality()
    try:
        pt = enc.aes_decrypt(ct)
        return jsonify({'code': 200, 'message': 'success',
                        'data': {'plaintext': pt, 'algorithm': 'AES-256-GCM'}})
    except Exception:
        return jsonify({'code': 400, 'message': '解密失败（密文可能被篡改或密钥不匹配）', 'data': None})


@security_bp.route('/api/security/rsa/encrypt', methods=['POST'])
@token_required
def rsa_encrypt():
    """RSA-OAEP 公钥加密（短数据，如 AES 会话密钥）。"""
    data = request.get_json(silent=True) or {}
    plaintext = data.get('plaintext')
    if not isinstance(plaintext, str):
        return jsonify({'code': 400, 'message': '缺少 plaintext 字段', 'data': None})
    enc = get_confidentiality()
    try:
        ct = enc.rsa_encrypt(plaintext)
        return jsonify({'code': 200, 'message': 'success',
                        'data': {'ciphertext_b64': ct, 'algorithm': 'RSA-2048-OAEP-SHA256'}})
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@security_bp.route('/api/security/hybrid/encrypt', methods=['POST'])
@token_required
def hybrid_encrypt():
    """混合加密（RSA 封装 AES 密钥 + AES 加密数据）。"""
    data = request.get_json(silent=True) or {}
    plaintext = data.get('plaintext')
    if not isinstance(plaintext, str):
        return jsonify({'code': 400, 'message': '缺少 plaintext 字段', 'data': None})
    enc = get_confidentiality()
    try:
        payload = enc.hybrid_encrypt(plaintext)
        payload['algorithm'] = 'RSA-2048-OAEP + AES-256-GCM'
        return jsonify({'code': 200, 'message': 'success', 'data': payload})
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@security_bp.route('/api/security/hybrid/decrypt', methods=['POST'])
@token_required
def hybrid_decrypt():
    """混合解密。Body: { "enc_key": "...", "enc_data": "..." }"""
    data = request.get_json(silent=True) or {}
    if 'enc_key' not in data or 'enc_data' not in data:
        return jsonify({'code': 400, 'message': '缺少 enc_key 或 enc_data', 'data': None})
    enc = get_confidentiality()
    try:
        pt = enc.hybrid_decrypt(data)
        return jsonify({'code': 200, 'message': 'success',
                        'data': {'plaintext': pt, 'algorithm': 'RSA-2048-OAEP + AES-256-GCM'}})
    except Exception:
        return jsonify({'code': 400, 'message': '混合解密失败', 'data': None})


# ================================================================
# 7.1.2 完整性
# ================================================================

@security_bp.route('/api/security/digest/sha256', methods=['POST'])
@token_required
def sha256_digest():
    """SHA-256 数字摘要。Body: { "data": str|dict }"""
    data = request.get_json(silent=True) or {}
    payload = data.get('data')
    if payload is None:
        return jsonify({'code': 400, 'message': '缺少 data 字段', 'data': None})
    integrity = get_integrity()
    digest = integrity.sha256_digest(payload)
    return jsonify({'code': 200, 'message': 'success',
                    'data': {'digest': digest, 'algorithm': 'SHA-256'}})


@security_bp.route('/api/security/hmac/sign', methods=['POST'])
@token_required
def hmac_sign():
    """HMAC-SHA256 生成摘要标签。"""
    data = request.get_json(silent=True) or {}
    payload = data.get('data')
    if payload is None:
        return jsonify({'code': 400, 'message': '缺少 data 字段', 'data': None})
    integrity = get_integrity()
    sig = integrity.hmac_sign(payload)
    return jsonify({'code': 200, 'message': 'success',
                    'data': {'hmac': sig, 'algorithm': 'HMAC-SHA256'}})


@security_bp.route('/api/security/hmac/verify', methods=['POST'])
@token_required
def hmac_verify():
    """HMAC-SHA256 校验。Body: { "data":..., "signature": "<64 hex>" }"""
    data = request.get_json(silent=True) or {}
    payload = data.get('data')
    signature = data.get('signature')
    if payload is None or not isinstance(signature, str):
        return jsonify({'code': 400, 'message': '缺少 data 或 signature 字段', 'data': None})
    integrity = get_integrity()
    ok = integrity.hmac_verify(payload, signature)
    return jsonify({
        'code': 200, 'message': 'success',
        'data': {'valid': ok, 'algorithm': 'HMAC-SHA256'},
    })


@security_bp.route('/api/security/profile/check', methods=['POST'])
@token_required
def profile_check():
    """校验指定用户资料完整性（是否被篡改）。管理员可查任意用户。"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    target_username = data.get('username') or payload['username']
    is_admin = payload.get('role') in ('主任', '院长')
    if not is_admin and target_username != payload['username']:
        return jsonify({'code': 403, 'message': '权限不足，仅管理员可校验他人资料', 'data': None})

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT username, name, role, department, status, profile_digest "
                   "FROM users WHERE username = ?", (target_username,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '用户不存在', 'data': None})

    integrity = get_integrity()
    stored_digest = row['profile_digest']
    if not stored_digest:
        return jsonify({
            'code': 200, 'message': 'success',
            'data': {'username': target_username, 'integrity': 'unknown',
                     'reason': '该用户尚未建立完整性摘要，请重新保存资料以生成'},
        })

    ok = integrity.verify_profile_digest(
        username=row['username'], name=row['name'] or '', role=row['role'] or '',
        department=row['department'] or '', status=row['status'] or '在职',
        signature=stored_digest,
    )
    return jsonify({
        'code': 200, 'message': 'success',
        'data': {
            'username': target_username,
            'integrity': 'valid' if ok else 'tampered',
            'algorithm': 'HMAC-SHA256',
            'profile_digest': stored_digest,
        },
    })


# ================================================================
# 7.1.3 真实性：数字证书鉴别
# ================================================================

@security_bp.route('/api/security/certificate', methods=['GET'])
def get_certificate():
    """获取服务端 X.509 公钥证书（任何人可下载）。"""
    auth = get_authenticity()
    return jsonify({
        'code': 200, 'message': 'success',
        'data': {
            'pem': auth.server_certificate_pem,
            'type': 'X.509 v3',
            'signature_algorithm': 'SHA-256 + RSA-PSS',
        },
    })


@security_bp.route('/api/security/certificate/info', methods=['GET'])
def get_certificate_info():
    """获取证书元数据（序列号、颁发者、有效期、指纹等）。"""
    auth = get_authenticity()
    return jsonify({'code': 200, 'message': 'success', 'data': auth.certificate_info})


@security_bp.route('/api/security/token/issue', methods=['POST'])
@admin_required
def issue_identity_token():
    """管理员为指定用户签发短期数字证书身份令牌。"""
    data = request.get_json(silent=True) or {}
    username = data.get('username')
    ttl = int(data.get('ttl_seconds') or 3600)
    if not username or ttl <= 0 or ttl > 86400 * 7:
        return jsonify({'code': 400, 'message': '无效的 username 或 ttl_seconds（1s~7d）', 'data': None})

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT name, role FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '用户不存在', 'data': None})

    auth = get_authenticity()
    token = auth.issue_user_token(
        username=username, name=row['name'] or '', role=row['role'] or '', ttl_seconds=ttl,
    )
    issuer = request.current_user['username']
    record_operation_log(issuer, '签发证书令牌', '安全',
                         f'为 {username} 签发证书身份令牌，有效期 {ttl} 秒')
    return jsonify({
        'code': 200, 'message': 'success',
        'data': {
            'header_b64': token['header_b64'],
            'payload_b64': token['payload_b64'],
            'signature_b64': token['signature_b64'],
            'payload': token['payload'],
            'issued_by': issuer,
        },
    })


@security_bp.route('/api/security/token/verify', methods=['POST'])
def verify_identity_token():
    """验证证书身份令牌（不要求登录，可用于信任链验证）。"""
    data = request.get_json(silent=True) or {}
    token = {
        'header_b64': data.get('header_b64'),
        'payload_b64': data.get('payload_b64'),
        'signature_b64': data.get('signature_b64'),
    }
    if not all(token.values()):
        return jsonify({'code': 400, 'message': '缺少 header/payload/signature', 'data': None})
    auth = get_authenticity()
    payload = auth.verify_user_token(token)
    if payload is None:
        return jsonify({
            'code': 200, 'message': 'success',
            'data': {'valid': False, 'reason': '签名无效或令牌已过期'},
        })
    return jsonify({
        'code': 200, 'message': 'success',
        'data': {
            'valid': True,
            'payload': payload,
            'verified_by': 'X.509 服务端证书公钥 RSA-PSS(SHA-256)',
        },
    })


# ================================================================
# 7.1.4 不可抵赖性：数字签名
# ================================================================

@security_bp.route('/api/security/sign', methods=['POST'])
@token_required
def sign_data():
    """对任意数据进行 RSA-PSS 数字签名。"""
    data = request.get_json(silent=True) or {}
    payload = data.get('data')
    if payload is None:
        return jsonify({'code': 400, 'message': '缺少 data 字段', 'data': None})
    nr = get_non_repudiation()
    try:
        signature = nr.sign(payload)
        return jsonify({
            'code': 200, 'message': 'success',
            'data': {'signature_b64': signature, 'algorithm': 'RSA-2048-PSS-SHA256'},
        })
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@security_bp.route('/api/security/verify', methods=['POST'])
def verify_signature():
    """验证 RSA-PSS 数字签名（公开接口，任何人可验）。"""
    data = request.get_json(silent=True) or {}
    payload = data.get('data')
    signature = data.get('signature_b64')
    if payload is None or not isinstance(signature, str):
        return jsonify({'code': 400, 'message': '缺少 data 或 signature_b64', 'data': None})
    nr = get_non_repudiation()
    ok = nr.verify(payload, signature)
    return jsonify({
        'code': 200, 'message': 'success',
        'data': {
            'valid': ok,
            'algorithm': 'RSA-2048-PSS-SHA256',
            'non_repudiable': ok,  # 签名有效即不可抵赖
        },
    })


@security_bp.route('/api/security/operation/log', methods=['POST'])
@token_required
def sign_operation_log():
    """对一条操作进行签名存证（写入带签名的操作日志）。"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    operation = data.get('operation', '自定义操作')
    module = data.get('module', '安全')
    detail = data.get('detail', '') or ''
    extra = data.get('extra') or None

    nr = get_non_repudiation()
    signed = nr.sign_operation(
        username=payload['username'], operation=operation,
        module=module, detail=detail, extra=extra,
    )
    # 写入数据库复用 record_operation_log（内部会自动再次签名，双重保险）
    record_operation_log(payload['username'], operation, module, detail)
    return jsonify({'code': 200, 'message': 'success',
                    'data': signed})


@security_bp.route('/api/security/operation/logs', methods=['GET'])
@token_required
def get_signed_operation_logs():
    """获取最近 N 条带签名的操作日志。"""
    payload = request.current_user
    limit = int(request.args.get('limit', 50))
    limit = min(max(limit, 1), 500)

    db = get_db()
    cursor = db.cursor()
    if payload.get('role') in ('主任', '院长'):
        cursor.execute("""
            SELECT id, username, operation, module, detail, ip_address, created_at,
                   digest, signature, timestamp_utc
            FROM operation_logs
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
    else:
        cursor.execute("""
            SELECT id, username, operation, module, detail, ip_address, created_at,
                   digest, signature, timestamp_utc
            FROM operation_logs
            WHERE username = ?
            ORDER BY id DESC
            LIMIT ?
        """, (payload['username'], limit))
    rows = cursor.fetchall()
    return jsonify({'code': 200, 'message': 'success',
                    'data': [dict(r) for r in rows]})


@security_bp.route('/api/security/operation/verify', methods=['POST'])
@token_required
def verify_operation_log():
    """验证某条操作日志的签名是否有效（防篡改 + 不可抵赖）。"""
    data = request.get_json(silent=True) or {}
    log_id = data.get('id')
    if log_id is None:
        return jsonify({'code': 400, 'message': '缺少日志 id', 'data': None})

    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, username, operation, module, detail, ip_address, created_at,
               digest, signature, timestamp_utc
        FROM operation_logs WHERE id = ?
    """, (int(log_id),))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '日志不存在', 'data': None})

    # 1) 完整性：检查摘要是否匹配
    integrity = get_integrity()
    expected_digest = integrity.sha256_digest({
        'username': row['username'], 'operation': row['operation'],
        'module': row['module'], 'detail': row.get('detail') or '',
        'ip': row.get('ip_address') or '', 'created_at': row['created_at'],
    })
    integrity_ok = (not row['digest']) or row['digest'] == expected_digest

    # 2) 不可抵赖性：检查签名是否有效
    nr = get_non_repudiation()
    if row['signature']:
        # 按 sign_operation 逻辑重算 payload
        check_payload = {
            'username': row['username'], 'operation': row['operation'],
            'module': row['module'], 'detail': row.get('detail') or '',
            'timestamp': row.get('timestamp_utc') or row['created_at'],
            'digest': row.get('digest') or '',
        }
        signature_ok = nr.verify(check_payload, row['signature'])
    else:
        signature_ok = None  # 无签名无法验证

    return jsonify({
        'code': 200, 'message': 'success',
        'data': {
            'id': row['id'],
            'integrity_valid': integrity_ok,
            'signature_valid': signature_ok,
            'non_repudiable': bool(signature_ok),
            'digest_algorithm': 'SHA-256',
            'signature_algorithm': 'RSA-2048-PSS-SHA256',
            'log': dict(row),
        },
    })


# ================================================================
# 综合健康检查：四项安全能力一次性返回状态
# ================================================================

@security_bp.route('/api/security/status', methods=['GET'])
def security_status():
    """返回四项身份安全能力的启用状态。"""
    enc = get_confidentiality()
    integrity = get_integrity()
    auth = get_authenticity()
    nr = get_non_repudiation()

    # 做一次轻量自检测试
    aes_ok = False
    try:
        aes_ct = enc.aes_encrypt('self_test')
        aes_ok = enc.aes_decrypt(aes_ct) == 'self_test'
    except Exception:
        aes_ok = False

    hmac_ok = False
    try:
        s = integrity.hmac_sign({'self': 'test'})
        hmac_ok = integrity.hmac_verify({'self': 'test'}, s)
    except Exception:
        hmac_ok = False

    sign_ok = False
    try:
        s = nr.sign('non_repudiation_test')
        sign_ok = nr.verify('non_repudiation_test', s)
    except Exception:
        sign_ok = False

    token_ok = False
    try:
        t = auth.issue_user_token(username='_self_test', name='test', role='test', ttl_seconds=10)
        token_ok = auth.verify_user_token(t) is not None
    except Exception:
        token_ok = False

    return jsonify({
        'code': 200, 'message': 'success',
        'data': {
            '7.1.1_confidentiality': {
                'enabled': aes_ok,
                'algorithms': ['AES-256-GCM', 'RSA-2048-OAEP-SHA256', '混合加密'],
            },
            '7.1.2_integrity': {
                'enabled': hmac_ok,
                'algorithms': ['SHA-256', 'HMAC-SHA256'],
            },
            '7.1.3_authenticity': {
                'enabled': token_ok,
                'algorithms': ['X.509 v3 + RSA-PSS(SHA-256)'],
                'certificate': auth.certificate_info,
            },
            '7.1.4_non_repudiation': {
                'enabled': sign_ok,
                'algorithms': ['RSA-2048-PSS-SHA256'],
            },
            'server_time_utc': datetime.utcnow().isoformat() + 'Z',
        },
    })


def register_routes(app):
    app.register_blueprint(security_bp)
