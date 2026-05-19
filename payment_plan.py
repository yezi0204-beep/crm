# payment_plan.py
import streamlit as st
from datetime import date, timedelta
from database import query_df, execute_sql
from utils import clear_user_cache

def show_payment_plans(uid: str, is_boss: bool):
    st.title("💰 下周付款计划")
    st.info("创建下周（未来7天内）的付款或资金使用计划，可关联项目（商机）或合同。")

    today = date.today()
    next_week_start = today + timedelta(days=1)
    next_week_end = today + timedelta(days=7)

    # 获取可关联的项目和合同（根据权限）
    if is_boss:
        businesses = query_df("SELECT id, title FROM business WHERE status != 'void' ORDER BY title")
        contracts = query_df("SELECT id, contract_name FROM contracts ORDER BY contract_name")
    else:
        businesses = query_df("SELECT id, title FROM business WHERE owner_id = ? AND status != 'void' ORDER BY title", (uid,))
        contracts = query_df("SELECT id, contract_name FROM contracts WHERE owner_id = ? ORDER BY contract_name", (uid,))

    # 在 session_state 中保存关联类型
    if "relate_type" not in st.session_state:
        st.session_state.relate_type = "项目（商机）"

    # 关联类型选择（放在表单外，以便立即触发 rerun）
    relate_type = st.radio("关联类型", ["无关联", "项目（商机）", "合同"], 
                           index=["无关联", "项目（商机）", "合同"].index(st.session_state.relate_type),
                           key="relate_type_radio")
    st.session_state.relate_type = relate_type

    with st.form("new_payment_plan"):
        plan_date = st.date_input("计划日期", value=next_week_start, min_value=next_week_start, max_value=next_week_end)
        amount = st.number_input("金额（元）", min_value=0.0, step=100.0, format="%.2f")
        description = st.text_area("用途说明")
        
        related_id = None
        if relate_type == "项目（商机）":
            if businesses.empty:
                st.warning("无可关联的项目")
            else:
                biz_options = {f"{row['id']} - {row['title']}": row['id'] for _, row in businesses.iterrows()}
                selected = st.selectbox("选择项目", list(biz_options.keys()))
                related_id = biz_options[selected]
        elif relate_type == "合同":
            if contracts.empty:
                st.warning("无可关联的合同")
            else:
                contract_options = {f"{row['id']} - {row['contract_name']}": row['id'] for _, row in contracts.iterrows()}
                selected = st.selectbox("选择合同", list(contract_options.keys()))
                related_id = contract_options[selected]

        submitted = st.form_submit_button("保存计划")
        if submitted:
            if amount <= 0:
                st.error("金额必须大于0")
            else:
                sql = """
                    INSERT INTO payment_plans (user_id, plan_date, amount, description, related_type, related_id, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'pending')
                """
                params = (uid, plan_date, amount, description, relate_type if relate_type != "无关联" else None, related_id)
                try:
                    execute_sql(sql, params)
                    st.success("付款计划已保存")
                    st.rerun()
                except Exception as e:
                    st.error(f"保存失败: {e}")

    st.divider()
    st.subheader("我的下周付款计划")
    plans = query_df("""
        SELECT id, plan_date, amount, description, related_type, related_id, status
        FROM payment_plans
        WHERE user_id = ? AND plan_date BETWEEN ? AND ?
        ORDER BY plan_date ASC
    """, (uid, next_week_start, next_week_end))
    if plans.empty:
        st.info("暂无下周付款计划")
    else:
        for _, row in plans.iterrows():
            with st.container():
                col1, col2, col3 = st.columns([2, 3, 1])
                with col1:
                    st.write(f"日期：{row['plan_date']}")
                    st.write(f"金额：￥{row['amount']:,.2f}")
                with col2:
                    st.write(f"说明：{row['description']}")
                    if row['related_type']:
                        rel_name = ""
                        if row['related_type'] == 'business':
                            biz = query_df("SELECT title FROM business WHERE id = ?", (row['related_id'],))
                            if not biz.empty:
                                rel_name = f"项目：{biz.iloc[0]['title']}"
                        elif row['related_type'] == 'contract':
                            con = query_df("SELECT contract_name FROM contracts WHERE id = ?", (row['related_id'],))
                            if not con.empty:
                                rel_name = f"合同：{con.iloc[0]['contract_name']}"
                        st.write(f"关联：{rel_name}")
                    st.write(f"状态：{row['status']}")
                with col3:
                    if row['status'] == 'pending':
                        if st.button("✅ 完成", key=f"complete_{row['id']}"):
                            execute_sql("UPDATE payment_plans SET status='completed' WHERE id=?", (row['id'],))
                            st.success("已标记完成")
                            st.rerun()
                        if st.button("🗑️ 删除", key=f"del_{row['id']}"):
                            execute_sql("DELETE FROM payment_plans WHERE id=?", (row['id'],))
                            st.success("已删除")
                            st.rerun()
                st.divider()

    with st.expander("历史完成计划"):
        history = query_df("""
            SELECT plan_date, amount, description
            FROM payment_plans
            WHERE user_id = ? AND status='completed' AND plan_date < ?
            ORDER BY plan_date DESC
            LIMIT 20
        """, (uid, next_week_start))
        if not history.empty:
            st.dataframe(history)
        else:
            st.info("暂无历史记录")