# project_cost.py
import streamlit as st
import pandas as pd
from datetime import date
from database import query_df, execute_sql
from utils import clear_user_cache

def show_project_costs(uid: str, is_boss: bool):
    st.title("💰 项目成本管理")
    st.info("录入商机或合同的各项成本（历史、差旅、评审、招待等），自动汇总到对应项目的总成本。")

    # 选择项目类型
    project_type = st.radio("项目类型", ["商机", "合同"], horizontal=True)

    # 获取项目列表（根据权限）
    if project_type == "商机":
        if is_boss:
            projects = query_df("SELECT id, title, total_cost FROM business WHERE status != 'void' ORDER BY title")
        else:
            projects = query_df("SELECT id, title, total_cost FROM business WHERE owner_id = ? AND status != 'void' ORDER BY title", (uid,))
        id_col = "id"
        name_col = "title"
    else:
        if is_boss:
            projects = query_df("SELECT id, contract_name as title, total_cost FROM contracts ORDER BY contract_name")
        else:
            projects = query_df("SELECT id, contract_name as title, total_cost FROM contracts WHERE owner_id = ? ORDER BY contract_name", (uid,))
        id_col = "id"
        name_col = "title"

    if projects.empty:
        st.warning(f"没有可用的{project_type}项目")
        return

    project_options = {f"{row[id_col]} - {row[name_col]} (总成本: {row['total_cost']:,.2f})": row[id_col] for _, row in projects.iterrows()}
    selected_label = st.selectbox(f"选择{project_type}", list(project_options.keys()))
    selected_project_id = project_options[selected_label]
    selected_project = projects[projects[id_col] == selected_project_id].iloc[0]

    st.subheader(f"当前{project_type}总成本：￥{selected_project['total_cost']:,.2f}")

    # 新增成本明细
    with st.form("add_cost"):
        cost_type = st.selectbox("成本类型", ["历史成本", "差旅费", "评审费", "招待费", "其他"])
        amount = st.number_input("金额（元）", min_value=0.0, step=100.0, format="%.2f")
        cost_date = st.date_input("发生日期", value=date.today())
        description = st.text_area("说明")
        if st.form_submit_button("添加成本"):
            if amount <= 0:
                st.error("金额必须大于0")
            else:
                type_map = {"历史成本": "history", "差旅费": "travel", "评审费": "review", "招待费": "entertainment", "其他": "other"}
                db_type = type_map[cost_type]
                # 插入 costs 表
                sql = """
                    INSERT INTO costs (project_type, project_id, cost_type, amount, description, cost_date, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """
                db_project_type = "business" if project_type == "商机" else "contract"
                try:
                    execute_sql(sql, (db_project_type, selected_project_id, db_type, amount, description, cost_date, uid))
                    # 更新对应项目的总成本
                    if project_type == "商机":
                        execute_sql("UPDATE business SET total_cost = total_cost + ? WHERE id = ?", (amount, selected_project_id))
                    else:
                        execute_sql("UPDATE contracts SET total_cost = total_cost + ? WHERE id = ?", (amount, selected_project_id))
                    st.success("成本已添加")
                    clear_user_cache()
                    st.rerun()
                except Exception as e:
                    st.error(f"添加失败: {e}")

    st.divider()
    st.subheader("成本明细列表")
    db_project_type = "business" if project_type == "商机" else "contract"
    costs = query_df("""
        SELECT id, cost_type, amount, cost_date, description, created_by, created_at
        FROM costs
        WHERE project_type = ? AND project_id = ?
        ORDER BY cost_date DESC, created_at DESC
    """, (db_project_type, selected_project_id))
    if costs.empty:
        st.info("暂无成本记录")
    else:
        for _, row in costs.iterrows():
            with st.container():
                cols = st.columns([2, 2, 3, 1])
                with cols[0]:
                    st.write(f"**{row['cost_type']}**")
                    st.write(f"金额：￥{row['amount']:,.2f}")
                with cols[1]:
                    st.write(f"日期：{row['cost_date']}")
                    st.write(f"录入人：{row['created_by']}")
                with cols[2]:
                    st.write(f"说明：{row['description']}")
                with cols[3]:
                    if is_boss or row['created_by'] == uid:
                        if st.button("🗑️", key=f"del_cost_{row['id']}"):
                            # 删除成本并减去总成本
                            execute_sql("DELETE FROM costs WHERE id=?", (row['id'],))
                            if project_type == "商机":
                                execute_sql("UPDATE business SET total_cost = total_cost - ? WHERE id = ?", (row['amount'], selected_project_id))
                            else:
                                execute_sql("UPDATE contracts SET total_cost = total_cost - ? WHERE id = ?", (row['amount'], selected_project_id))
                            st.success("已删除")
                            st.rerun()
                st.divider()

        # 按类型统计
        total_by_type = costs.groupby('cost_type')['amount'].sum()
        st.subheader("成本按类型统计")
        st.dataframe(total_by_type.reset_index().rename(columns={'cost_type':'类型', 'amount':'金额(元)'}))

        # 每月趋势
        costs['month'] = pd.to_datetime(costs['cost_date']).dt.strftime('%Y-%m')
        monthly = costs.groupby('month')['amount'].sum().reset_index()
        if not monthly.empty:
            st.subheader("每月成本趋势")
            st.line_chart(monthly.set_index('month'))