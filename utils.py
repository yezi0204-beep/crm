from database import query_df, execute_sql
from datetime import date, datetime

def get_user_map():
    """获取用户名映射"""
    users = query_df("SELECT username, name FROM users")
    return dict(zip(users['username'], users['name']))

def clear_user_cache():
    """清除用户映射缓存"""
    try:
        import streamlit as st
        if 'user_map' in st.session_state:
            del st.session_state['user_map']
    except Exception:
        pass

def update_customer_last_follow(cust_id: int, follow_date=None):
    """更新客户最后跟进日期（复用）"""
    if not cust_id:
        return False
    if follow_date is None:
        follow_date = date.today()
    elif isinstance(follow_date, datetime):
        follow_date = follow_date.date()
    sql = "UPDATE customers SET last_follow = ? WHERE id = ?"
    try:
        execute_sql(sql, (follow_date, cust_id))
        return True
    except Exception:
        print(f"更新客户 {cust_id} 最后跟进日期失败")
        return False