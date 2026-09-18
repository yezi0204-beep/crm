import streamlit as st
from database import query_df
from datetime import date, datetime

@st.cache_data(ttl=600)
def get_user_map():
    """获取用户名映射（缓存）"""
    users = query_df("SELECT username, name FROM users")
    return dict(zip(users['username'], users['name']))

def clear_user_cache():
    """清除用户映射缓存"""
    st.cache_data.clear()  # 简单全局清除，可优化为更细粒度

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
        st.warning(f"更新客户 {cust_id} 最后跟进日期失败")
        return False