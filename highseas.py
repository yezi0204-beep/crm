# highseas.py

import streamlit as st
import pandas as pd
from datetime import date
from database import query_df, execute_sql
from utils import clear_user_cache

def show_highseas(uid: str):
    """公海池模块"""
    st.title("🌊 客户公海")
    st.info("规则：30天未跟进的客户自动掉入公海")

    # 1. 执行公海规则：将超过30天未跟进的客户释放到公海
    execute_sql("UPDATE customers SET owner_id = NULL WHERE last_follow < date('now', '-30 days')")
    clear_user_cache()  # 清除缓存，确保后续查询最新数据

    # 2. 查询公海客户列表
    df_sea = query_df("""
        SELECT id, name, company, level, last_follow
        FROM customers
        WHERE owner_id IS NULL
        ORDER BY last_follow DESC
    """)

    if df_sea.empty:
        st.write("公海暂无客户")
        return

    # 3. 展示公海客户表格
    st.dataframe(
        df_sea[['id', 'name', 'company', 'level', 'last_follow']],
        use_container_width=True,
        hide_index=True,
        column_config={
            "id": "客户ID",
            "name": "联系人",
            "company": "公司名称",
            "level": "客户等级",
            "last_follow": st.column_config.DateColumn("最后跟进时间", format="YYYY-MM-DD")
        }
    )

    # 4. 领取客户
    selected_id = st.selectbox("选择要领取的客户ID", df_sea['id'].tolist())
    if st.button("立即认领"):
        # 再次确认该客户仍在公海（防止并发）
        check = query_df("SELECT id FROM customers WHERE id = ? AND owner_id IS NULL", (selected_id,))
        if check.empty:
            st.error("该客户已被他人领取，请刷新页面重试")
            st.rerun()
        else:
            # 更新客户负责人为当前用户，并更新最后跟进日期为今天
            sql = "UPDATE customers SET owner_id = ?, last_follow = ? WHERE id = ?"
            try:
                rows = execute_sql(sql, (uid, date.today(), selected_id))
                if rows == 1:
                    st.success("领取成功！")
                    clear_user_cache()
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("领取失败，请重试")
            except Exception as e:
                st.error(f"领取失败: {e}")