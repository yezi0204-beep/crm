# business.py

import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from database import query_df, execute_sql
from utils import get_user_map, update_customer_last_follow, clear_user_cache
from config import STAGES

def show_business(uid: str, is_boss: bool):
    """商机全生命周期看板（表格视图）"""
    st.title("🎯 商机全生命周期看板")

    user_map = get_user_map()
    show_void = st.checkbox("显示已作废商机", value=False)

    # ---------- 新建商机（可折叠） ----------
    with st.expander("➕ 新建商机", expanded=False):
        if is_boss:
            cust_df = query_df("SELECT id, name, company FROM customers ORDER BY name")
        else:
            cust_df = query_df("SELECT id, name, company FROM customers WHERE owner_id = ? ORDER BY name", (uid,))
        cust_choices = {f"{row['id']} - {row['name']} ({row['company']})": row['id'] for _, row in cust_df.iterrows()}
        if not cust_choices:
            st.warning("请先录入客户")
            cust_id = None
        else:
            selected_cust = st.selectbox("关联客户", list(cust_choices.keys()))
            cust_id = cust_choices[selected_cust]

        with st.form("new_business"):
            title = st.text_input("项目名称（商机标题）*")
            amount = st.number_input("预计合同额（万元）", min_value=0.0, step=1.0, format="%.2f") * 10000
            probability = st.slider("落实概率（%）", 0, 100, 50)
            tax_rate = st.number_input("税率（%）", min_value=0.0, max_value=100.0, step=0.1, format="%.1f")
            expected_income = st.number_input("预计本年形成收入（万元）", min_value=0.0, step=1.0, format="%.2f") * 10000
            expected_cost = st.number_input("预计本年成本（万元）", min_value=0.0, step=1.0, format="%.2f") * 10000
            expected_month = st.text_input("预计收入形成时间（年月，如2025-03）", value=datetime.now().strftime("%Y-%m"))
            implementation = st.text_area("项目落实情况", placeholder="简要描述当前落实情况")
            stage = st.selectbox("当前阶段", STAGES)
            predict_date = st.date_input("预计签约日期", datetime.now().date() + timedelta(days=30))
            project_manager = None
            if is_boss:
                pm_candidates = query_df("""
                    SELECT u.username, u.name FROM users u
                    JOIN user_roles ur ON u.username = ur.username
                    WHERE ur.role = '项目经理'
                """)
                if not pm_candidates.empty:
                    pm_options = {f"{row['name']} ({row['username']})": row['username'] for _, row in pm_candidates.iterrows()}
                    selected_pm = st.selectbox("项目经理（可选）", ["无"] + list(pm_options.keys()))
                    if selected_pm != "无":
                        project_manager = pm_options[selected_pm]
            if st.form_submit_button("创建"):
                if title and cust_id:
                    sql = """
                        INSERT INTO business
                        (cust_id, title, amount, stage, predict_date, owner_id, probability, tax_rate,
                         expected_income_year, expected_cost_year, expected_income_month, implementation_status,
                         status, project_manager)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """
                    params = (cust_id, title, amount, stage, predict_date, uid, probability, tax_rate,
                              expected_income, expected_cost, expected_month, implementation,
                              'active', project_manager)
                    try:
                        execute_sql(sql, params)
                        if cust_id:
                            update_customer_last_follow(cust_id)
                        st.success("商机创建成功")
                        clear_user_cache()
                        st.rerun()
                    except Exception as e:
                        st.error(f"创建失败: {e}")
                else:
                    st.error("请填写项目名称并关联客户")

    # ---------- 加载商机数据 ----------
    if is_boss:
        if show_void:
            df_b = query_df("SELECT * FROM business ORDER BY created_at DESC")
        else:
            df_b = query_df("SELECT * FROM business WHERE status = 'active' ORDER BY created_at DESC")
    else:
        if show_void:
            df_b = query_df("SELECT * FROM business WHERE owner_id = ? ORDER BY created_at DESC", (uid,))
        else:
            df_b = query_df("SELECT * FROM business WHERE owner_id = ? AND status = 'active' ORDER BY created_at DESC", (uid,))

    if df_b.empty:
        st.info("暂无商机数据")
        return

    # 数值列转换
    numeric_cols = ['amount', 'expected_income_year', 'expected_cost_year']
    for col in numeric_cols:
        if col in df_b.columns:
            df_b[col] = pd.to_numeric(df_b[col], errors='coerce').fillna(0)

    cust_all = query_df("SELECT id, name, company FROM customers")
    cust_dict = dict(zip(cust_all['id'], cust_all['company']))
    cust_name_dict = dict(zip(cust_all['id'], cust_all['name']))

    # ---------- 表格视图（主视图） ----------
    st.subheader("📊 商机列表")
    
    # 筛选选项
    filter_col1, filter_col2, filter_col3 = st.columns(3)
    with filter_col1:
        selected_stage = st.selectbox("按阶段筛选", ["全部"] + list(STAGES))
    with filter_col2:
        if is_boss:
            owner_options = ["全部"] + list(user_map.values())
            owner_display = st.selectbox("按负责人筛选", owner_options)
            if owner_display != "全部":
                selected_owner = next(k for k, v in user_map.items() if v == owner_display)
            else:
                selected_owner = None
        else:
            selected_owner = None
    with filter_col3:
        search_keyword = st.text_input("搜索（项目名称/客户）", placeholder="输入关键词搜索")
    
    # 应用筛选
    filtered_df = df_b.copy()
    if selected_stage != "全部":
        filtered_df = filtered_df[filtered_df['stage'] == selected_stage]
    if selected_owner is not None:
        filtered_df = filtered_df[filtered_df['owner_id'] == selected_owner]
    if search_keyword.strip():
        keyword = search_keyword.strip().lower()
        filtered_df = filtered_df[
            filtered_df['title'].str.lower().str.contains(keyword, na=False) | 
            filtered_df['cust_id'].map(cust_name_dict).str.lower().str.contains(keyword, na=False)
        ]
    
    if filtered_df.empty:
        st.info("没有符合条件的商机")
        return
    
    # 显示表格
    table_df = filtered_df.copy()
    table_df['项目名称'] = table_df['title']
    table_df['客户'] = table_df['cust_id'].map(cust_name_dict).fillna('未知')
    table_df['金额(万元)'] = table_df['amount'] / 10000
    table_df['阶段'] = table_df['stage']
    table_df['负责人'] = table_df['owner_id'].map(user_map).fillna(table_df['owner_id'])
    table_df['预计签约日期'] = table_df['predict_date']
    
    # 概率显示
    def get_probability_color(prob):
        if prob >= 80:
            return "🟢"
        elif prob >= 50:
            return "🟠"
        else:
            return "🔴"
    table_df['概率'] = table_df['probability'].apply(
        lambda x: f"{get_probability_color(x)} {int(x)}%" if pd.notna(x) else "🟠 50%"
    )
    
    table_df['状态'] = table_df['status'].apply(lambda x: "作废" if x == "void" else "正常")
    
    display_cols = ['项目名称', '客户', '金额(万元)', '阶段', '负责人', '预计签约日期', '概率', '状态']
    
    # 使用st.dataframe展示表格
    st.dataframe(
        table_df[display_cols],
        column_config={
            '项目名称': st.column_config.TextColumn("项目名称"),
            '客户': st.column_config.TextColumn("客户"),
            '金额(万元)': st.column_config.NumberColumn("金额(万元)", format="%.2f"),
            '阶段': st.column_config.TextColumn("阶段"),
            '负责人': st.column_config.TextColumn("负责人"),
            '预计签约日期': st.column_config.DateColumn("预计签约日期"),
            '概率': st.column_config.TextColumn("概率"),
            '状态': st.column_config.TextColumn("状态")
        },
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    # ---------- 操作面板 ----------
    st.subheader("⚙️ 商机操作")
    # 按ID选择要操作的商机（使用原始的filtered_df，保留完整数据）
    active_df = filtered_df[filtered_df['status'] != 'void']
    void_df = filtered_df[filtered_df['status'] == 'void']
    
    if not active_df.empty or not void_df.empty:
        # 构建选择项
        select_options = []
        select_map = {}
        for _, row in active_df.iterrows():
            cust_name = cust_name_dict.get(row['cust_id'], '未知')
            label = f"[正常] {row['title']} - {cust_name}"
            select_options.append(label)
            select_map[label] = (row['id'], 'active')
        for _, row in void_df.iterrows():
            cust_name = cust_name_dict.get(row['cust_id'], '未知')
            label = f"[作废] {row['title']} - {cust_name}"
            select_options.append(label)
            select_map[label] = (row['id'], 'void')
        
        if select_options:
            selected_label = st.selectbox("选择要操作的商机", select_options)
            selected_id, selected_status = select_map[selected_label]
            
            # 找到原始数据
            original_row = df_b[df_b['id'] == selected_id].iloc[0]
            
            # ---------- 操作按钮组 ----------
            col1, col2, col3, col4, col5 = st.columns(5)
            
            if selected_status == 'active':
                with col1:
                    can_advance = (is_boss or original_row['owner_id'] == uid) and original_row['stage'] != '赢单成交'
                    if can_advance:
                        with st.popover("⏩ 推进阶段"):
                            st.warning("确定要推进到下一阶段吗？")
                            if st.button("确认推进", key=f"adv_{selected_id}"):
                                old_stage = original_row['stage']
                                new_stage = STAGES[STAGES.index(old_stage) + 1]
                                execute_sql("UPDATE business SET stage = ? WHERE id = ?", (new_stage, selected_id))
                                execute_sql(
                                    "INSERT INTO business_stage_logs (business_id, old_stage, new_stage, user_id) VALUES (?,?,?,?)",
                                    (selected_id, old_stage, new_stage, uid)
                                )
                                if original_row['cust_id']:
                                    update_customer_last_follow(original_row['cust_id'])
                                st.success(f"已推进到{new_stage}")
                                st.rerun()
                
                with col2:
                    can_edit = is_boss or original_row['owner_id'] == uid
                    if can_edit:
                        with st.popover("✏️ 编辑商机"):
                            with st.form(f"edit_form_{selected_id}"):
                                new_title = st.text_input("项目名称*", value=original_row['title'])
                                amount_wan = original_row['amount'] / 10000
                                new_amount = st.number_input("预计合同额（万元）", min_value=0.0, step=1.0, format="%.2f", value=float(amount_wan)) * 10000
                                new_prob = st.slider("落实概率（%）", 0, 100, value=int(original_row['probability']) if pd.notna(original_row['probability']) else 50)
                                new_tax = st.number_input("税率（%）", min_value=0.0, max_value=100.0, step=0.1, format="%.1f", value=float(original_row['tax_rate']) if pd.notna(original_row['tax_rate']) else 0.0)
                                income_wan = original_row['expected_income_year'] / 10000
                                new_income = st.number_input("预计本年形成收入（万元）", min_value=0.0, step=1.0, format="%.2f", value=float(income_wan)) * 10000
                                cost_wan = original_row['expected_cost_year'] / 10000
                                new_cost = st.number_input("预计本年成本（万元）", min_value=0.0, step=1.0, format="%.2f", value=float(cost_wan)) * 10000
                                new_month = st.text_input("预计收入形成时间（年月）", value=original_row['expected_income_month'] if pd.notna(original_row['expected_income_month']) else "")
                                new_impl = st.text_area("项目落实情况", value=original_row['implementation_status'] if pd.notna(original_row['implementation_status']) else "")
                                new_stage = st.selectbox("当前阶段", STAGES, index=STAGES.index(original_row['stage']) if original_row['stage'] in STAGES else 0)
                                new_predict = st.date_input("预计签约日期", value=pd.to_datetime(original_row['predict_date']).date() if pd.notna(original_row['predict_date']) else datetime.now().date())
                                
                                # 修改关联客户
                                if is_boss:
                                    all_cust = query_df("SELECT id, name, company FROM customers ORDER BY name")
                                else:
                                    all_cust = query_df("SELECT id, name, company FROM customers WHERE owner_id = ? ORDER BY name", (uid,))
                                cust_options = {f"{c['id']} - {c['name']} ({c['company']})": c['id'] for _, c in all_cust.iterrows()}
                                current_cust_label = next((label for label, cid in cust_options.items() if cid == original_row['cust_id']), None)
                                if current_cust_label is None:
                                    current_cust_label = f"{original_row['cust_id']} - 未知客户"
                                new_cust_label = st.selectbox("关联客户", list(cust_options.keys()), index=list(cust_options.keys()).index(current_cust_label) if current_cust_label in cust_options else 0)
                                new_cust_id = cust_options[new_cust_label]
                                sync_cust_owner = False
                                if new_cust_id != original_row['cust_id'] and is_boss:
                                    sync_cust_owner = st.checkbox("同时将新客户的负责人修改为当前商机负责人", value=False)
                                
                                # 负责人选择
                                old_owner = original_row['owner_id']
                                new_owner = old_owner
                                sync_owner = False
                                if is_boss:
                                    all_users = query_df("SELECT username, name FROM users ORDER BY name")
                                    user_options = {f"{u['username']} - {u['name']}": u['username'] for _, u in all_users.iterrows()}
                                    current_owner_label = next((label for label, un in user_options.items() if un == original_row['owner_id']), None)
                                    if current_owner_label is None:
                                        current_owner_label = f"{original_row['owner_id']} - {original_row['owner_id']}"
                                    selected_owner_label = st.selectbox("负责人", list(user_options.keys()),
                                                                       index=list(user_options.keys()).index(current_owner_label) if current_owner_label in user_options else 0)
                                    new_owner = user_options[selected_owner_label]
                                    if new_owner != old_owner:
                                        sync_owner = st.checkbox("同时将关联客户负责人修改为相同负责人", value=True)
                                
                                # 项目经理选择
                                new_pm = original_row.get('project_manager')
                                if is_boss:
                                    pm_candidates = query_df("""
                                        SELECT u.username, u.name FROM users u
                                        JOIN user_roles ur ON u.username = ur.username
                                        WHERE ur.role = '项目经理'
                                    """)
                                    if not pm_candidates.empty:
                                        pm_options = {f"{row['name']} ({row['username']})": row['username'] for _, row in pm_candidates.iterrows()}
                                        current_pm = original_row.get('project_manager')
                                        current_pm_label = next((label for label, un in pm_options.items() if un == current_pm), "无")
                                        selected_pm_label = st.selectbox("项目经理", ["无"] + list(pm_options.keys()),
                                                                        index=0 if current_pm_label == "无" else list(pm_options.keys()).index(current_pm_label) + 1)
                                        new_pm = pm_options[selected_pm_label] if selected_pm_label != "无" else None
                                
                                if st.form_submit_button("保存修改"):
                                    old_stage_val = original_row['stage']
                                    if new_stage != old_stage_val:
                                        execute_sql(
                                            "INSERT INTO business_stage_logs (business_id, old_stage, new_stage, user_id) VALUES (?,?,?,?)",
                                            (selected_id, old_stage_val, new_stage, uid)
                                        )
                                    update_sql = """
                                        UPDATE business SET
                                            title=?, amount=?, probability=?, tax_rate=?,
                                            expected_income_year=?, expected_cost_year=?,
                                            expected_income_month=?, implementation_status=?,
                                            stage=?, predict_date=?, owner_id=?, project_manager=?, cust_id=?
                                        WHERE id=?
                                    """
                                    params = (new_title, new_amount, new_prob, new_tax,
                                              new_income, new_cost, new_month, new_impl,
                                              new_stage, new_predict, new_owner, new_pm, new_cust_id, selected_id)
                                    try:
                                        execute_sql(update_sql, params)
                                        if sync_owner and new_owner != old_owner:
                                            execute_sql("UPDATE customers SET owner_id = ? WHERE id = ?", (new_owner, original_row['cust_id']))
                                            st.info(f"已同步更新原客户负责人为 {new_owner}")
                                        if sync_cust_owner and new_cust_id != original_row['cust_id']:
                                            execute_sql("UPDATE customers SET owner_id = ? WHERE id = ?", (new_owner, new_cust_id))
                                            st.info(f"已将新客户负责人更新为 {new_owner}")
                                        if original_row['cust_id']:
                                            update_customer_last_follow(original_row['cust_id'])
                                        if new_cust_id != original_row['cust_id']:
                                            update_customer_last_follow(new_cust_id)
                                        st.success("商机更新成功")
                                        clear_user_cache()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"更新失败: {e}")
                
                with col3:
                    can_void = (is_boss or original_row['owner_id'] == uid) and original_row['stage'] != '赢单成交'
                    if can_void:
                        with st.popover("❌ 作废"):
                            st.warning("作废后该商机将不再显示在看板中，但历史记录将保留。确定作废吗？")
                            if st.button("确认作废", key=f"void_{selected_id}"):
                                try:
                                    execute_sql("UPDATE business SET status = 'void' WHERE id = ?", (selected_id,))
                                    st.success("商机已作废")
                                    clear_user_cache()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"作废失败: {e}")
                
                with col4:
                    can_delete = is_boss or original_row['owner_id'] == uid
                    if can_delete:
                        with st.popover("🗑️ 删除"):
                            contract_check = query_df("SELECT id FROM contracts WHERE b_id=?", (selected_id,))
                            if not contract_check.empty:
                                st.error("该商机已关联合同，无法删除。请先删除合同。")
                            else:
                                st.warning("确定要删除此商机吗？此操作不可逆，且会删除所有相关跟进记录和阶段日志。")
                                if st.button("确认删除", key=f"delete_{selected_id}"):
                                    try:
                                        execute_sql("DELETE FROM follow_logs WHERE ref_type='business' AND ref_id=?", (selected_id,))
                                        execute_sql("DELETE FROM business_stage_logs WHERE business_id=?", (selected_id,))
                                        execute_sql("DELETE FROM business WHERE id=?", (selected_id,))
                                        st.success("商机已删除")
                                        clear_user_cache()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"删除失败: {e}")
                
                with col5:
                    can_follow = is_boss or original_row['owner_id'] == uid
                    if can_follow:
                        with st.popover("📝 记录跟进"):
                            with st.form(key=f"follow_form_{selected_id}"):
                                follow = st.text_area("跟进内容*", key=f"f_{selected_id}")
                                follow_subject = st.text_input("主题", key=f"sub_{selected_id}")
                                follow_participants = st.text_input("相关人员", key=f"par_{selected_id}")
                                follow_location = st.text_input("地点", key=f"loc_{selected_id}")
                                follow_next_plan = st.text_area("下一步工作计划", key=f"plan_{selected_id}")
                                col_date, col_time = st.columns(2)
                                with col_date:
                                    follow_date = st.date_input("日期", value=None, key=f"date_{selected_id}")
                                with col_time:
                                    follow_time = st.time_input("时间", value=None, step=60, key=f"time_{selected_id}")
                                if st.form_submit_button("记录跟进"):
                                    if follow.strip():
                                        actual_date = follow_date if follow_date else date.today()
                                        actual_time = follow_time if follow_time else datetime.min.time()
                                        combined = datetime.combine(actual_date, actual_time)
                                        time_str = combined.strftime("%Y-%m-%d %H:%M:%S")
                                        sql = """
                                            INSERT INTO follow_logs
                                            (ref_type, ref_id, user_id, content, subject, participants, location, next_plan, log_time)
                                            VALUES ('business', ?, ?, ?, ?, ?, ?, ?, ?)
                                        """
                                        try:
                                            execute_sql(sql, (selected_id, uid, follow.strip(), follow_subject,
                                                              follow_participants, follow_location, follow_next_plan, time_str))
                                            if original_row['cust_id']:
                                                update_customer_last_follow(original_row['cust_id'], combined)
                                            st.success("跟进已记录")
                                            clear_user_cache()
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"记录失败: {e}")
                                    else:
                                        st.error("跟进内容不能为空")
            
            else:
                with col1:
                    # 恢复按钮
                    can_restore = is_boss or original_row['owner_id'] == uid
                    if can_restore:
                        with st.popover("🔄 恢复"):
                            st.warning("确定要恢复此商机吗？恢复后将重新显示。")
                            if st.button("确认恢复", key=f"restore_{selected_id}"):
                                try:
                                    execute_sql("UPDATE business SET status = 'active' WHERE id = ?", (selected_id,))
                                    st.success("商机已恢复")
                                    clear_user_cache()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"恢复失败: {e}")
