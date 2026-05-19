# users.py

import streamlit as st
from database import query_df, execute_sql
from utils import clear_user_cache
from auth import hash_password

def show_users():
    """用户管理模块（仅主任可访问）"""
    st.title("👥 用户管理")

    # 权限检查（双重保险）
    if st.session_state.get("u_info", {}).get("role") != "主任":
        st.error("您无权访问此页面")
        st.stop()

    tab_list, tab_add = st.tabs(["用户列表", "新增用户"])

    # ---------- 标签页1：用户列表 ----------
    with tab_list:
        df_users = query_df("SELECT username, name, role FROM users ORDER BY username")
        if df_users.empty:
            st.info("暂无用户数据")
        else:
            st.dataframe(df_users, use_container_width=True, hide_index=True)

            # 每个用户的详细信息及操作
            for _, row in df_users.iterrows():
                with st.expander(f"{row['name']} ({row['username']}) - {row['role']}"):
                    col1, col2 = st.columns(2)

                    # 重置密码
                    with col1:
                        with st.form(f"reset_pwd_{row['username']}"):
                            st.caption("重置密码")
                            new_pwd = st.text_input("新密码", type="password", key=f"new_pwd_{row['username']}")
                            confirm_pwd = st.text_input("确认密码", type="password", key=f"confirm_pwd_{row['username']}")
                            if st.form_submit_button("更新密码"):
                                if new_pwd != confirm_pwd:
                                    st.error("两次输入不一致")
                                elif len(new_pwd) < 3:
                                    st.error("密码至少3位")
                                else:
                                    new_hash = hash_password(new_pwd)
                                    execute_sql("UPDATE users SET password_hash = ? WHERE username = ?",
                                                (new_hash, row['username']))
                                    st.success("密码已重置")
                                    clear_user_cache()
                                    st.rerun()

                    # 删除用户（不能删除当前登录用户，且需检查是否有关联数据）
                    with col2:
                        current_user = st.session_state["u_id"]
                        if row['username'] == current_user:
                            st.info("不能删除当前登录用户")
                        else:
                            # 检查关联数据
                            check_sql = """
                                SELECT
                                    (SELECT COUNT(*) FROM customers WHERE owner_id = ?) as cust_cnt,
                                    (SELECT COUNT(*) FROM business WHERE owner_id = ?) as biz_cnt,
                                    (SELECT COUNT(*) FROM contracts WHERE owner_id = ?) as con_cnt,
                                    (SELECT COUNT(*) FROM follow_logs WHERE user_id = ?) as log_cnt
                            """
                            df_check = query_df(check_sql, (row['username'], row['username'], row['username'], row['username']))
                            cust_cnt = df_check.iloc[0]['cust_cnt']
                            biz_cnt = df_check.iloc[0]['biz_cnt']
                            con_cnt = df_check.iloc[0]['con_cnt']
                            log_cnt = df_check.iloc[0]['log_cnt']

                            if cust_cnt > 0 or biz_cnt > 0 or con_cnt > 0 or log_cnt > 0:
                                st.error(f"无法删除：该用户负责 {cust_cnt} 个客户、{biz_cnt} 个商机、{con_cnt} 个合同，并有 {log_cnt} 条跟进记录。请先转移或删除相关数据。")
                            else:
                                with st.popover("🗑️ 删除用户"):
                                    st.warning(f"确定删除用户 {row['username']} 吗？")
                                    if st.button("确认删除", key=f"del_user_{row['username']}"):
                                        # 先删除 user_roles 中的关联
                                        execute_sql("DELETE FROM user_roles WHERE username = ?", (row['username'],))
                                        # 再删除用户
                                        execute_sql("DELETE FROM users WHERE username = ?", (row['username'],))
                                        st.success("用户已删除")
                                        clear_user_cache()
                                        st.rerun()

                    # 角色管理（多选）
                    st.subheader("角色管理（可多选）")
                    # users.py 中的角色列表修改
                    all_roles = ['主任', '销售', '售前', '技术研发', '项目经理', '院长', '采购']
                    # 获取当前用户已有的角色
                    current_roles = query_df("SELECT role FROM user_roles WHERE username = ?", (row['username'],))['role'].tolist()
                    selected_roles = st.multiselect(
                        "分配角色",
                        all_roles,
                        default=current_roles,
                        key=f"roles_{row['username']}"
                    )
                    if st.button("更新角色", key=f"upd_roles_{row['username']}"):
                        # 删除原有角色
                        execute_sql("DELETE FROM user_roles WHERE username = ?", (row['username'],))
                        # 插入新角色
                        for role in selected_roles:
                            execute_sql("INSERT INTO user_roles (username, role) VALUES (?, ?)", (row['username'], role))
                        # 同步 users 表的 role 字段（用于旧逻辑兼容，取第一个角色作为主角色）
                        primary_role = selected_roles[0] if selected_roles else '销售'
                        execute_sql("UPDATE users SET role = ? WHERE username = ?", (primary_role, row['username']))
                        st.success("角色已更新")
                        clear_user_cache()
                        st.rerun()

    # ---------- 标签页2：新增用户 ----------
    with tab_add:
        with st.form("add_user"):
            new_username = st.text_input("账号 *")
            new_name = st.text_input("姓名 *")
            # 初始角色（可多选，但新建时建议先选一个默认角色）
            initial_roles = st.multiselect("初始角色", ['销售', '售前', '技术研发', '项目经理', '主任', '院长', '采购'], default=['销售'])
            new_password = st.text_input("初始密码 *", type="password")
            confirm_password = st.text_input("确认密码 *", type="password")

            if st.form_submit_button("创建用户"):
                if not new_username or not new_name or not new_password:
                    st.error("请填写所有必填项")
                elif new_password != confirm_password:
                    st.error("两次输入的密码不一致")
                elif len(new_password) < 3:
                    st.error("密码至少3位")
                elif not initial_roles:
                    st.error("请至少选择一个角色")
                else:
                    # 检查账号是否已存在
                    existing = query_df("SELECT username FROM users WHERE username = ?", (new_username,))
                    if not existing.empty:
                        st.error("账号已存在")
                    else:
                        pwd_hash = hash_password(new_password)
                        # 插入用户表（主角色取第一个）
                        primary_role = initial_roles[0]
                        execute_sql(
                            "INSERT INTO users (username, password_hash, name, role) VALUES (?, ?, ?, ?)",
                            (new_username, pwd_hash, new_name, primary_role)
                        )
                        # 插入角色关联表
                        for role in initial_roles:
                            execute_sql("INSERT INTO user_roles (username, role) VALUES (?, ?)", (new_username, role))
                        # 为用户初始化小时费率（默认200）
                        execute_sql("INSERT INTO user_hourly_rate (user_id, hourly_rate) VALUES (?, ?)", (new_username, 200.0))
                        st.success("用户创建成功")
                        clear_user_cache()
                        st.rerun()