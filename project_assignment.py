# project_assignment.py
import streamlit as st
from database import query_df, execute_sql
from utils import clear_user_cache

def show_project_assignment(uid: str):
    """项目分配管理（项目经理可见）"""
    st.title("👥 项目人员分配")

    # 获取项目经理负责的所有商机和合同
    # 商机：owner_id = uid 或 project_manager = uid
    businesses = query_df("""
        SELECT id, title, 'business' as type
        FROM business
        WHERE (owner_id = ? OR project_manager = ?) AND status != 'void'
    """, (uid, uid))
    # 合同：owner_id = uid（合同负责人）
    contracts = query_df("""
        SELECT id, contract_name as title, 'contract' as type
        FROM contracts
        WHERE owner_id = ?
    """, (uid,))

    if businesses.empty and contracts.empty:
        st.info("您还没有负责的项目（商机或合同），无法分配人员。")
        return

    # 合并项目列表
    projects = []
    for _, row in businesses.iterrows():
        projects.append({"id": row['id'], "title": row['title'], "type": "business"})
    for _, row in contracts.iterrows():
        projects.append({"id": row['id'], "title": row['title'], "type": "contract"})

    project_options = {f"{p['title']} ({'商机' if p['type']=='business' else '合同'})": (p['id'], p['type']) for p in projects}
    selected_label = st.selectbox("选择项目", list(project_options.keys()))
    project_id, project_type = project_options[selected_label]

    # 获取所有技术研发和售前角色的人员
    candidates = query_df("""
        SELECT DISTINCT u.username, u.name, GROUP_CONCAT(ur.role) as roles
        FROM users u
        JOIN user_roles ur ON u.username = ur.username
        WHERE ur.role IN ('技术研发', '售前')
        GROUP BY u.username
    """)
    if candidates.empty:
        st.warning("没有可分配的研发或售前人员")
        return

    # 当前已分配人员
    assigned = query_df("""
        SELECT user_id FROM project_assignments
        WHERE project_type = ? AND project_id = ?
    """, (project_type, project_id))
    assigned_users = assigned['user_id'].tolist() if not assigned.empty else []

    st.subheader("添加分配")
    available = candidates[~candidates['username'].isin(assigned_users)]
    if not available.empty:
        user_options = {f"{row['name']} ({row['username']}) - {row['roles']}": row['username'] for _, row in available.iterrows()}
        selected_user = st.selectbox("选择人员", list(user_options.keys()))
        if st.button("分配"):
            execute_sql("""
                INSERT INTO project_assignments (project_type, project_id, user_id, assigned_by)
                VALUES (?, ?, ?, ?)
            """, (project_type, project_id, user_options[selected_user], uid))
            st.success("分配成功")
            st.rerun()
    else:
        st.info("所有研发/售前人员已分配")

    st.subheader("已分配人员")
    if assigned_users:
        assigned_info = query_df(f"SELECT username, name FROM users WHERE username IN ({','.join(['?']*len(assigned_users))})", assigned_users)
        for _, row in assigned_info.iterrows():
            col1, col2 = st.columns([4,1])
            col1.write(f"{row['name']} ({row['username']})")
            if col2.button("移除", key=f"remove_{row['username']}_{project_type}_{project_id}"):
                execute_sql("""
                    DELETE FROM project_assignments
                    WHERE project_type = ? AND project_id = ? AND user_id = ?
                """, (project_type, project_id, row['username']))
                st.rerun()
    else:
        st.write("暂无分配")