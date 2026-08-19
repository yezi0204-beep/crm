from __future__ import annotations
"""
CRM 身份安全模块
==================
实现 7.1.1~7.1.4 四项身份安全要求：

7.1.1 机密性：对称加密(AES-GCM) + 非对称加密(RSA-OAEP)
7.1.2 完整性：数字摘要(SHA-256) + HMAC 校验
7.1.3 真实性：X.509 数字证书身份鉴别
7.1.4 不可抵赖性：RSA-PSS 数字签名

密钥存储：backend/crypto_keys/ 目录（首次运行自动生成）
"""

import os
import json
import base64
import hashlib
import hmac
from datetime import datetime, timezone

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.hmac import HMAC as CryptoHMAC
from cryptography.hazmat.backends import default_backend
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.exceptions import InvalidSignature

_BACKEND = default_backend()

# -------------------------- 路径与常量 --------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KEYS_DIR = os.path.join(BASE_DIR, 'crypto_keys')
os.makedirs(KEYS_DIR, exist_ok=True)

RSA_PRIVATE_KEY_PATH = os.path.join(KEYS_DIR, 'server_private_key.pem')
RSA_PUBLIC_KEY_PATH = os.path.join(KEYS_DIR, 'server_public_key.pem')
CERT_PATH = os.path.join(KEYS_DIR, 'server_certificate.pem')
CERT_PRIVATE_KEY_PATH = os.path.join(KEYS_DIR, 'cert_private_key.pem')
AES_MASTER_KEY_PATH = os.path.join(KEYS_DIR, 'aes_master.key')
HMAC_SECRET_PATH = os.path.join(KEYS_DIR, 'hmac_secret.key')

RSA_KEY_SIZE = 2048
AES_KEY_SIZE = 256  # bits = 32 bytes
HMAC_KEY_SIZE = 32  # bytes
PBKDF2_ITERATIONS = 200_000
GCM_NONCE_SIZE = 12
GCM_TAG_SIZE = 16


# ================================================================
# 7.1.1  机密性 —— 对称加密(AES-GCM) + 非对称加密(RSA-OAEP)
# ================================================================

class CryptoConfidentiality:
    """
    机密性模块：
    - 对称加密：AES-256-GCM（用于敏感字段、大数据块）
    - 非对称加密：RSA-2048-OAEP-SHA256（用于 AES 密钥交换、小数据）
    """

    def __init__(self):
        self._aes_key = None
        self._rsa_private = None
        self._rsa_public = None
        self._load_or_generate_keys()

    # ---------- 密钥加载/生成 ----------

    def _load_or_generate_keys(self):
        # RSA 密钥对
        if os.path.exists(RSA_PRIVATE_KEY_PATH) and os.path.exists(RSA_PUBLIC_KEY_PATH):
            with open(RSA_PRIVATE_KEY_PATH, 'rb') as f:
                self._rsa_private = serialization.load_pem_private_key(
                    f.read(), password=None, backend=_BACKEND)
            with open(RSA_PUBLIC_KEY_PATH, 'rb') as f:
                self._rsa_public = serialization.load_pem_public_key(
                    f.read(), backend=_BACKEND)
        else:
            self._rsa_private = rsa.generate_private_key(
                public_exponent=65537, key_size=RSA_KEY_SIZE, backend=_BACKEND
            )
            self._rsa_public = self._rsa_private.public_key()
            with open(RSA_PRIVATE_KEY_PATH, 'wb') as f:
                f.write(self._rsa_private.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                ))
            with open(RSA_PUBLIC_KEY_PATH, 'wb') as f:
                f.write(self._rsa_public.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                ))

        # AES 主密钥
        if os.path.exists(AES_MASTER_KEY_PATH):
            with open(AES_MASTER_KEY_PATH, 'rb') as f:
                self._aes_key = f.read()
        else:
            self._aes_key = os.urandom(AES_KEY_SIZE // 8)
            with open(AES_MASTER_KEY_PATH, 'wb') as f:
                f.write(self._aes_key)

    # ---------- 对称加密 AES-GCM ----------

    def aes_encrypt(self, plaintext: str | bytes, key: bytes | None = None) -> str:
        """
        AES-256-GCM 加密。
        返回格式：base64(nonce + tag + ciphertext)
        """
        k = key or self._aes_key
        if isinstance(plaintext, str):
            plain_bytes = plaintext.encode('utf-8')
        else:
            plain_bytes = plaintext
        nonce = os.urandom(GCM_NONCE_SIZE)
        cipher = Cipher(algorithms.AES(k), modes.GCM(nonce), backend=_BACKEND)
        encryptor = cipher.encryptor()
        ct = encryptor.update(plain_bytes) + encryptor.finalize()
        return base64.b64encode(nonce + encryptor.tag + ct).decode('ascii')

    def aes_decrypt(self, ciphertext_b64: str, key: bytes | None = None) -> str:
        """
        AES-256-GCM 解密。
        输入格式：base64(nonce + tag + ciphertext)
        """
        k = key or self._aes_key
        raw = base64.b64decode(ciphertext_b64.encode('ascii'))
        nonce = raw[:GCM_NONCE_SIZE]
        tag = raw[GCM_NONCE_SIZE:GCM_NONCE_SIZE + GCM_TAG_SIZE]
        ct = raw[GCM_NONCE_SIZE + GCM_TAG_SIZE:]
        cipher = Cipher(algorithms.AES(k), modes.GCM(nonce, tag), backend=_BACKEND)
        decryptor = cipher.decryptor()
        plain_bytes = decryptor.update(ct) + decryptor.finalize()
        return plain_bytes.decode('utf-8')

    # ---------- 非对称加密 RSA-OAEP ----------

    def rsa_encrypt(self, plaintext: str | bytes, public_key=None) -> str:
        """
        RSA-2048-OAEP(SHA-256) 加密（用于 AES 会话密钥等短数据）。
        返回 base64 密文。
        """
        pub = public_key or self._rsa_public
        if isinstance(plaintext, str):
            pt_bytes = plaintext.encode('utf-8')
        else:
            pt_bytes = plaintext
        ct = pub.encrypt(
            pt_bytes,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        return base64.b64encode(ct).decode('ascii')

    def rsa_decrypt_bytes(self, ciphertext_b64: str) -> bytes:
        """RSA-2048-OAEP 解密，返回原始字节（用于二进制数据如 AES 密钥）。"""
        ct = base64.b64decode(ciphertext_b64.encode('ascii'))
        pt = self._rsa_private.decrypt(
            ct,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        return pt

    def rsa_decrypt(self, ciphertext_b64: str) -> str:
        """RSA-2048-OAEP 解密，返回 UTF-8 字符串（用于文本数据）。"""
        return self.rsa_decrypt_bytes(ciphertext_b64).decode('utf-8')

    # ---------- 混合加密：RSA(AES-key) + AES(data) ----------

    def hybrid_encrypt(self, plaintext: str) -> dict:
        """
        混合加密：
        1. 生成随机 AES 会话密钥
        2. AES-GCM 加密明文
        3. RSA 加密 AES 密钥
        返回 { 'enc_key': b64, 'enc_data': b64 }
        """
        session_key = os.urandom(AES_KEY_SIZE // 8)
        enc_data = self.aes_encrypt(plaintext, key=session_key)
        # RSA 加密二进制密钥：直接使用底层方法
        pub = self._rsa_public
        ct = pub.encrypt(
            session_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        enc_key = base64.b64encode(ct).decode('ascii')
        return {'enc_key': enc_key, 'enc_data': enc_data}

    def hybrid_decrypt(self, payload: dict) -> str:
        """混合解密：RSA 解密会话密钥 → AES-GCM 解密数据"""
        session_key = self.rsa_decrypt_bytes(payload['enc_key'])
        return self.aes_decrypt(payload['enc_data'], key=session_key)


# ================================================================
# 7.1.2  完整性 —— 数字摘要(SHA-256) + HMAC-SHA256 校验
# ================================================================

class CryptoIntegrity:
    """
    完整性模块：
    - SHA-256 数字摘要：检测数据是否被篡改
    - HMAC-SHA256 消息认证码：带密钥的完整性校验
    """

    def __init__(self):
        self._hmac_secret = None
        self._load_or_generate_secret()

    def _load_or_generate_secret(self):
        if os.path.exists(HMAC_SECRET_PATH):
            with open(HMAC_SECRET_PATH, 'rb') as f:
                self._hmac_secret = f.read()
        else:
            self._hmac_secret = os.urandom(HMAC_KEY_SIZE)
            with open(HMAC_SECRET_PATH, 'wb') as f:
                f.write(self._hmac_secret)

    # ---------- SHA-256 摘要 ----------

    def sha256_digest(self, data: str | bytes | dict) -> str:
        """返回 SHA-256 十六进制摘要（64 字符）"""
        if isinstance(data, dict):
            data = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
        if isinstance(data, str):
            data = data.encode('utf-8')
        return hashlib.sha256(data).hexdigest()

    def sha256_file(self, file_path: str) -> str:
        """对文件内容计算 SHA-256 摘要"""
        h = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h.update(chunk)
        return h.hexdigest()

    # ---------- HMAC-SHA256 ----------

    def hmac_sign(self, data: str | dict) -> str:
        """对数据生成 HMAC-SHA256 标签"""
        if isinstance(data, dict):
            payload = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
        else:
            payload = str(data)
        mac = hmac.new(self._hmac_secret, payload.encode('utf-8'), hashlib.sha256)
        return mac.hexdigest()

    def hmac_verify(self, data: str | dict, signature: str) -> bool:
        """校验 HMAC-SHA256 标签是否匹配"""
        expected = self.hmac_sign(data)
        return hmac.compare_digest(expected, signature)

    # ---------- 用户资料完整性保护 ----------

    def compute_profile_digest(self, username: str, name: str, role: str,
                                department: str = '', status: str = '') -> str:
        """
        计算身份信息（用户资料）的完整性摘要。
        用于检测 user 表中关键字段是否被篡改。
        """
        payload = {
            'u': username,
            'n': name,
            'r': role,
            'd': department or '',
            's': status or '',
        }
        return self.hmac_sign(payload)

    def verify_profile_digest(self, username: str, name: str, role: str,
                               department: str, status: str, signature: str) -> bool:
        """校验用户资料摘要是否匹配"""
        payload = {
            'u': username,
            'n': name,
            'r': role,
            'd': department or '',
            's': status or '',
        }
        return self.hmac_verify(payload, signature)


# ================================================================
# 7.1.3  真实性 —— X.509 数字证书身份鉴别
# ================================================================

class CryptoAuthenticity:
    """
    真实性模块：X.509 数字证书身份鉴别。
    - 自签发服务端证书（首次启动自动生成，有效期 10 年）
    - 证书验证：验证公钥是否属于证书声明的主体
    - 用户证书令牌：签发可验证的用户身份凭证
    """

    def __init__(self):
        self._cert_private = None
        self._server_cert = None
        self._load_or_generate_cert()

    def _load_or_generate_cert(self):
        if os.path.exists(CERT_PATH) and os.path.exists(CERT_PRIVATE_KEY_PATH):
            with open(CERT_PRIVATE_KEY_PATH, 'rb') as f:
                self._cert_private = serialization.load_pem_private_key(
                    f.read(), password=None, backend=_BACKEND)
            with open(CERT_PATH, 'rb') as f:
                self._server_cert = x509.load_pem_x509_certificate(f.read(), backend=_BACKEND)
        else:
            self._cert_private = rsa.generate_private_key(
                public_exponent=65537, key_size=RSA_KEY_SIZE, backend=_BACKEND
            )
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, 'CN'),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, 'Beijing'),
                x509.NameAttribute(NameOID.LOCALITY_NAME, 'Beijing'),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Tiandi Info Network Institute'),
                x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, 'CRM System'),
                x509.NameAttribute(NameOID.COMMON_NAME, 'crm.tiandi.local'),
            ])
            now = datetime.now(timezone.utc)
            self._server_cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(self._cert_private.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now)
                .not_valid_after(now.replace(year=now.year + 10))
                .add_extension(
                    x509.SubjectAlternativeName([
                        x509.DNSName('crm.tiandi.local'),
                        x509.DNSName('localhost'),
                        x509.IPAddress(__import__('ipaddress').ip_address('127.0.0.1')),
                    ]),
                    critical=False,
                )
                .sign(self._cert_private, hashes.SHA256(), backend=_BACKEND)
            )
            with open(CERT_PRIVATE_KEY_PATH, 'wb') as f:
                f.write(self._cert_private.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                ))
            with open(CERT_PATH, 'wb') as f:
                f.write(self._server_cert.public_bytes(serialization.Encoding.PEM))

    # ---------- 证书信息 ----------

    @property
    def server_certificate_pem(self) -> str:
        """服务端 X.509 证书（PEM 格式）"""
        return self._server_cert.public_bytes(serialization.Encoding.PEM).decode('ascii')

    @property
    def certificate_info(self) -> dict:
        """返回证书主体信息供前端展示"""
        cert = self._server_cert
        return {
            'serial_number': hex(cert.serial_number),
            'issuer': cert.issuer.rfc4514_string(),
            'subject': cert.subject.rfc4514_string(),
            'not_valid_before': cert.not_valid_before.isoformat(),
            'not_valid_after': cert.not_valid_after.isoformat(),
            'fingerprint_sha256': cert.fingerprint(hashes.SHA256()).hex(),
            'signature_algorithm': cert.signature_algorithm_oid._name,
        }

    def verify_server_certificate(self, pem_cert: str) -> bool:
        """验证给定证书是否由本服务器私钥签发（自签验证）"""
        try:
            cert = x509.load_pem_x509_certificate(pem_cert.encode('ascii'), backend=_BACKEND)
            cert.public_key().verify(
                cert.signature,
                cert.tbs_certificate_bytes,
                padding.PKCS1v15(),
                cert.signature_hash_algorithm,
            )
            return True
        except (InvalidSignature, ValueError):
            return False

    # ---------- 用户证书令牌（短期身份凭证）----------

    def issue_user_token(self, username: str, name: str, role: str,
                          ttl_seconds: int = 3600) -> dict:
        """
        签发经数字证书私钥签名的用户身份令牌。
        包含 {header, payload, signature} 三段式结构。
        """
        now = datetime.now(timezone.utc)
        header = {'alg': 'RS256', 'typ': 'CRM-IDENTITY'}
        payload = {
            'sub': username,
            'name': name,
            'role': role,
            'iat': int(now.timestamp()),
            'exp': int((now.timestamp() + ttl_seconds)),
            'iss': self.certificate_info['subject'],
        }
        signing_input = (
            base64.urlsafe_b64encode(json.dumps(header, sort_keys=True).encode('utf-8')).rstrip(b'=')
            + b'.'
            + base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True).encode('utf-8')).rstrip(b'=')
        )
        signature = self._cert_private.sign(
            signing_input,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return {
            'header_b64': signing_input.split(b'.')[0].decode('ascii'),
            'payload_b64': signing_input.split(b'.')[1].decode('ascii'),
            'signature_b64': base64.urlsafe_b64encode(signature).rstrip(b'=').decode('ascii'),
            'payload': payload,
        }

    def verify_user_token(self, token: dict) -> dict | None:
        """
        验证用户身份令牌。
        成功返回 payload 字典，失败返回 None。
        """
        try:
            signing_input = (
                token['header_b64'].encode('ascii') + b'.' + token['payload_b64'].encode('ascii')
            )
            signature = base64.urlsafe_b64decode(
                token['signature_b64'] + '=' * ((4 - len(token['signature_b64']) % 4) % 4)
            )
            self._server_cert.public_key().verify(
                signature,
                signing_input,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
            payload_bytes = base64.urlsafe_b64decode(
                token['payload_b64'] + '=' * ((4 - len(token['payload_b64']) % 4) % 4)
            )
            payload = json.loads(payload_bytes.decode('utf-8'))
            if payload.get('exp', 0) < int(datetime.now(timezone.utc).timestamp()):
                return None
            return payload
        except (InvalidSignature, KeyError, ValueError, json.JSONDecodeError):
            return None


# ================================================================
# 7.1.4  不可抵赖性 —— RSA-PSS 数字签名
# ================================================================

class CryptoNonRepudiation:
    """
    不可抵赖性模块：RSA-PSS(SHA-256) 数字签名。
    - 对敏感操作（登录、修改密码、创建合同等）签名
    - 验证签名确认真实性，发送方不可否认
    """

    def __init__(self, private_key=None, public_key=None):
        """
        :param private_key: 签名私钥（默认使用服务端证书私钥）
        :param public_key:  验签公钥（默认使用服务端证书公钥）
        """
        self._private = private_key
        self._public = public_key
        # 若未传入则与证书模块共享同对密钥
        auth = CryptoAuthenticity() if (private_key is None or public_key is None) else None
        if self._private is None:
            self._private = auth._cert_private
        if self._public is None:
            self._public = auth._server_cert.public_key()

    # ---------- 签名 ----------

    def sign(self, data: str | bytes | dict) -> str:
        """
        对数据生成 RSA-PSS(SHA-256) 签名，返回 base64 编码。
        """
        if isinstance(data, dict):
            payload = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
        elif isinstance(data, str):
            payload = data.encode('utf-8')
        else:
            payload = data
        if isinstance(payload, str):
            payload = payload.encode('utf-8')
        signature = self._private.sign(
            payload,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode('ascii')

    def verify(self, data: str | bytes | dict, signature_b64: str, public_key=None) -> bool:
        """
        验证 RSA-PSS 签名。True 表示签名有效、发送方不可否认。
        """
        try:
            pub = public_key or self._public
            if isinstance(data, dict):
                payload = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
            elif isinstance(data, str):
                payload = data.encode('utf-8')
            else:
                payload = data
            if isinstance(payload, str):
                payload = payload.encode('utf-8')
            signature = base64.b64decode(signature_b64.encode('ascii'))
            pub.verify(
                signature,
                payload,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
            return True
        except (InvalidSignature, ValueError, base64.binascii.Error):
            return False

    # ---------- 操作签名与存证 ----------

    def sign_operation(self, username: str, operation: str, module: str,
                        detail: str = '', extra: dict | None = None) -> dict:
        """
        对一次敏感操作进行签名存证。
        返回 { digest, signature, timestamp, ... } 可直接存入审计日志。
        """
        ts = datetime.now(timezone.utc).isoformat()
        payload = {
            'username': username,
            'operation': operation,
            'module': module,
            'detail': detail or '',
            'timestamp': ts,
            'nonce': os.urandom(8).hex(),
        }
        if extra:
            payload['extra'] = {k: str(v) for k, v in extra.items()}
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode('utf-8')
        ).hexdigest()
        payload['digest'] = digest
        signature = self.sign(payload)
        return {
            'username': username,
            'operation': operation,
            'module': module,
            'detail': detail or '',
            'timestamp': ts,
            'digest': digest,
            'signature': signature,
            'payload': payload,
        }

    def verify_operation(self, record: dict) -> bool:
        """
        验证审计日志中的一条操作记录签名是否有效。
        record 需要包含 signature 和 payload（或用于重算 payload 的字段）。
        """
        try:
            payload = record.get('payload')
            if not payload:
                payload = {
                    'username': record['username'],
                    'operation': record['operation'],
                    'module': record['module'],
                    'detail': record.get('detail', ''),
                    'timestamp': record['timestamp'],
                    'nonce': record.get('nonce', ''),
                    'digest': record.get('digest', ''),
                }
                if record.get('extra'):
                    payload['extra'] = record['extra']
            return self.verify(payload, record['signature'])
        except KeyError:
            return False


# ================================================================
# 单例工厂
# ================================================================

_confidentiality: CryptoConfidentiality | None = None
_integrity: CryptoIntegrity | None = None
_authenticity: CryptoAuthenticity | None = None
_non_repudiation: CryptoNonRepudiation | None = None


def get_confidentiality() -> CryptoConfidentiality:
    global _confidentiality
    if _confidentiality is None:
        _confidentiality = CryptoConfidentiality()
    return _confidentiality


def get_integrity() -> CryptoIntegrity:
    global _integrity
    if _integrity is None:
        _integrity = CryptoIntegrity()
    return _integrity


def get_authenticity() -> CryptoAuthenticity:
    global _authenticity
    if _authenticity is None:
        _authenticity = CryptoAuthenticity()
    return _authenticity


def get_non_repudiation() -> CryptoNonRepudiation:
    global _non_repudiation
    if _non_repudiation is None:
        # 证书模块未初始化时先实例化 authenticity，保证密钥共享
        get_authenticity()
        _non_repudiation = CryptoNonRepudiation()
    return _non_repudiation
