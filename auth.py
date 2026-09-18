import bcrypt
import hashlib
import streamlit as st
from database import query_df, execute_sql
from utils import get_user_map, clear_user_cache

def hash_password(pwd: str) -> str:
    """使用 bcrypt 哈希密码（新用户或重置密码时使用）"""
    return bcrypt.hashpw(pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(pwd: str, hashed: str) -> bool:
    """
    验证密码，兼容旧版 SHA256 哈希（自动提示迁移）
    """
    # 如果是 bcrypt 哈希（以 $2b$ 开头）
    if hashed.startswith('$2b$'):
        try:
            return bcrypt.checkpw(pwd.encode('utf-8'), hashed.encode('utf-8'))
        except ValueError:
            return False
    else:
        # 旧版 SHA256 哈希（64位十六进制）
        old_hash = hashlib.sha256(pwd.encode()).hexdigest()
        if old_hash == hashed:
            # 密码正确但哈希格式旧，返回 True，但建议调用方提示用户修改密码
            # 这里可以通过全局变量或返回值额外告知需要迁移，但简单起见先返回 True
            # 注意：你可以在这里触发一个警告，提示用户重置密码
            return True
        return False
    if not pwd_hash.startswith('$2b$') and check_password(p, pwd_hash):
        # 更新为 bcrypt 哈希
        new_hash = hash_password(p)
        execute_sql("UPDATE users SET password_hash = ? WHERE username = ?", (new_hash, username))
        st.success("密码已升级为更安全的加密方式")

def login(username: str, password: str):
    """登录验证，返回用户信息或 None"""
    user = query_df("SELECT username, password_hash, name, role FROM users WHERE username = ?", (username,))
    if user.empty:
        return None
    if check_password(password, user.iloc[0]['password_hash']):
        return {
            "u_id": username,
            "name": user.iloc[0]['name'],
            "role": user.iloc[0]['role']
        }
    return None

def change_password(username: str, old_pwd: str, new_pwd: str) -> bool:
    """修改密码"""
    user = query_df("SELECT password_hash FROM users WHERE username = ?", (username,))
    if user.empty or not check_password(old_pwd, user.iloc[0]['password_hash']):
        return False
    if len(new_pwd) < 3:
        return False
    new_hash = hash_password(new_pwd)
    execute_sql("UPDATE users SET password_hash = ? WHERE username = ?", (new_hash, username))
    return True