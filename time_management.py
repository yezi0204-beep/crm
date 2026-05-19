# time_management.py

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, date, time, timedelta
from database import query_df, execute_sql
from utils import clear_user_cache

# ========== 主入口 ==========
def show_time_management(uid: str, is_boss: bool):
    """工时管理主入口"""
    st.title("⏱️ 项目工时管理")
    user_roles = st.session_state.get('user_roles', [])
    tab1, tab2, tab3, tab4 = st.tabs(["📝 工时填报", "✅ 工时审批", "📊 工时报表", "💰 项目成本"])
    with tab1:
        show_time_entry(uid, is_boss, user_roles)
    with tab2:
        show_time_approval(uid, is_boss, user_roles)
    with tab3:
        show_time_reports(uid, is_boss, user_roles)
    with tab4:
        show_project_cost(uid, is_boss, user_roles)

# ========== 辅助函数：获取用户可填报的项目 ==========
def get_user_projects(uid: str, is_boss: bool, user_roles: list):
    """根据用户角色获取可填报的项目列表（商机+合同）"""
    if '技术研发' in user_roles:
        projects = query_df("""
            SELECT pa.project_type, pa.project_id,
                   CASE WHEN pa.project_type = 'business' THEN b.title
                        ELSE c.contract_name END as title
            FROM project_assignments pa
            LEFT JOIN business b ON pa.project_type='business' AND pa.project_id = b.id
            LEFT JOIN contracts c ON pa.project_type='contract' AND pa.project_id = c.id
            WHERE pa.user_id = ? AND (b.status != 'void' OR c.id IS NOT NULL)
        """, (uid,))
    else:
        businesses = query_df("""
            SELECT 'business' as project_type, id as project_id, title
            FROM business
            WHERE (owner_id = ? OR project_manager = ?) AND status != 'void'
        """, (uid, uid))
        contracts = query_df("""
            SELECT 'contract' as project_type, id as project_id, contract_name as title
            FROM contracts
            WHERE owner_id = ?
        """, (uid,))
        projects = pd.concat([businesses, contracts], ignore_index=True)
    return projects

# ========== 工时填报 ==========
def show_time_entry(uid: str, is_boss: bool, user_roles: list):
    st.subheader("工时填报")
    projects = get_user_projects(uid, is_boss, user_roles)
    if projects.empty:
        if '技术研发' in user_roles:
            st.warning("您尚未被分配到任何项目，请联系项目经理分配。")
        else:
            st.warning("没有可填报的项目，请先创建商机/合同或分配项目。")
        return

    project_options = {f"{row['title']} ({'商机' if row['project_type']=='business' else '合同'})": (row['project_id'], row['project_type']) for _, row in projects.iterrows()}
    selected_label = st.selectbox("选择项目", list(project_options.keys()))
    project_id, project_type = project_options[selected_label]

    with st.form("entry_form"):
        work_date = st.date_input("工作日期", value=date.today())
        
        # 默认正常工作时间 8:30 - 17:30
        default_start = time(8, 30)
        default_end = time(17, 30)
        st.markdown("**正常工作时间**")
        col1, col2 = st.columns(2)
        with col1:
            start_time = st.time_input("上班时间", value=default_start)
        with col2:
            end_time = st.time_input("下班时间", value=default_end)
        
        # 加班时间段
        st.markdown("**加班时间（可选）**")
        col3, col4 = st.columns(2)
        with col3:
            ot_start = st.time_input("加班开始时间", value=None)
        with col4:
            ot_end = st.time_input("加班结束时间", value=None)
        
        # 自动计算工时（扣除午休1小时，如果跨过12:00-13:00）
        def calc_hours(start, end, work_date):
            if start is None or end is None:
                return 0.0
            start_dt = datetime.combine(work_date, start)
            end_dt = datetime.combine(work_date, end)
            if end_dt < start_dt:
                end_dt += timedelta(days=1)
            total_seconds = (end_dt - start_dt).total_seconds()
            hours = total_seconds / 3600
            # 扣除午休1小时（如果工作时间覆盖12:00-13:00）
            lunch_start = time(12, 0)
            lunch_end = time(13, 0)
            if start <= lunch_start and end >= lunch_end:
                hours -= 1.0
            return hours
        
        normal_hours = calc_hours(start_time, end_time, work_date)
        overtime_hours = calc_hours(ot_start, ot_end, work_date)
        total_hours = normal_hours + overtime_hours
        
        st.info(f"自动计算总工时：{total_hours:.1f} 小时（正常 {normal_hours:.1f} 小时 + 加班 {overtime_hours:.1f} 小时）")
        manual_hours = st.number_input("如需手动修改总工时（小时）", min_value=0.0, max_value=24.0, step=0.5, value=total_hours, format="%.1f")
        description = st.text_area("工作内容描述", placeholder="请详细描述本次工作内容")
        
        if st.form_submit_button("提交工时"):
            if manual_hours <= 0:
                st.error("工时必须大于0")
            elif not description.strip():
                st.error("请填写工作内容描述")
            else:
                sql = """
                    INSERT INTO work_hours
                    (project_type, project_id, user_id, work_date, start_time, end_time,
                     overtime_start, overtime_end, overtime_hours, hours, description, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """
                params = (project_type, project_id, uid, work_date,
                          start_time.strftime("%H:%M:%S"), end_time.strftime("%H:%M:%S"),
                          ot_start.strftime("%H:%M:%S") if ot_start else None,
                          ot_end.strftime("%H:%M:%S") if ot_end else None,
                          overtime_hours, manual_hours, description.strip())
                try:
                    execute_sql(sql, params)
                    st.success("工时提交成功，等待审批")
                    clear_user_cache()
                    st.rerun()
                except Exception as e:
                    st.error(f"提交失败: {e}")
    
    # 显示当前用户的工时记录
    st.subheader("我的工时记录")
    my_hours = query_df("""
        SELECT wh.id,
               CASE WHEN wh.project_type = 'business' THEN b.title
                    ELSE c.contract_name END as project,
               wh.work_date, wh.start_time, wh.end_time, wh.overtime_start, wh.overtime_end,
               wh.overtime_hours, wh.hours, wh.description, wh.status,
               wh.submit_time, wh.reject_reason
        FROM work_hours wh
        LEFT JOIN business b ON wh.project_type='business' AND wh.project_id = b.id
        LEFT JOIN contracts c ON wh.project_type='contract' AND wh.project_id = c.id
        WHERE wh.user_id = ?
        ORDER BY wh.submit_time DESC
    """, (uid,))
    if not my_hours.empty:
        status_map = {'pending': '待审批', 'approved': '已批准', 'rejected': '已驳回'}
        my_hours['status_cn'] = my_hours['status'].map(status_map)
        # 格式化时间显示
        def format_time(t):
            if t and len(t) >= 5:
                return t[:5]
            return t or ''
        my_hours['上班'] = my_hours['start_time'].apply(format_time)
        my_hours['下班'] = my_hours['end_time'].apply(format_time)
        my_hours['加班时段'] = my_hours.apply(lambda row: f"{format_time(row['overtime_start'])}-{format_time(row['overtime_end'])}" if row['overtime_start'] and row['overtime_end'] else "", axis=1)
        display_df = my_hours[['project', 'work_date', '上班', '下班', '加班时段', 'hours', 'description', 'status_cn', 'reject_reason']]
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        pending_ids = my_hours[my_hours['status'] == 'pending']['id'].tolist()
        if pending_ids:
            with st.expander("编辑或删除待审批记录"):
                selected_id = st.selectbox("选择记录", pending_ids, format_func=lambda x: f"ID: {x}")
                record = my_hours[my_hours['id'] == selected_id].iloc[0]
                with st.form("edit_entry"):
                    new_hours = st.number_input("工时", value=float(record['hours']), step=0.5)
                    new_desc = st.text_area("描述", value=record['description'])
                    if st.form_submit_button("更新"):
                        execute_sql("UPDATE work_hours SET hours=?, description=? WHERE id=?", (new_hours, new_desc, selected_id))
                        st.success("更新成功")
                        st.rerun()
                if st.button("删除", key=f"del_{selected_id}"):
                    execute_sql("DELETE FROM work_hours WHERE id=?", (selected_id,))
                    st.success("删除成功")
                    st.rerun()
    else:
        st.info("暂无工时记录")

# ========== 工时审批 ==========
def show_time_approval(uid: str, is_boss: bool, user_roles: list):
    st.subheader("待审批工时")
    is_pm = '项目经理' in user_roles
    if not (is_boss or is_pm):
        st.error("您无权访问工时审批功能")
        return

    if is_boss:
        pending = query_df("""
            SELECT wh.id, u.name as user_name,
                   CASE WHEN wh.project_type = 'business' THEN b.title
                        ELSE c.contract_name END as project,
                   wh.work_date, wh.start_time, wh.end_time, wh.overtime_start, wh.overtime_end, wh.overtime_hours, wh.hours,
                   wh.description, wh.submit_time
            FROM work_hours wh
            JOIN users u ON wh.user_id = u.username
            LEFT JOIN business b ON wh.project_type='business' AND wh.project_id = b.id
            LEFT JOIN contracts c ON wh.project_type='contract' AND wh.project_id = c.id
            WHERE wh.status = 'pending'
            ORDER BY wh.submit_time ASC
        """)
    else:
        pending = query_df("""
            SELECT wh.id, u.name as user_name,
                   CASE WHEN wh.project_type = 'business' THEN b.title
                        ELSE c.contract_name END as project,
                   wh.work_date, wh.start_time, wh.end_time, wh.overtime_start, wh.overtime_end, wh.overtime_hours, wh.hours,
                   wh.description, wh.submit_time
            FROM work_hours wh
            JOIN users u ON wh.user_id = u.username
            LEFT JOIN business b ON wh.project_type='business' AND wh.project_id = b.id
            LEFT JOIN contracts c ON wh.project_type='contract' AND wh.project_id = c.id
            WHERE wh.status = 'pending'
              AND (
                  (wh.project_type='business' AND (b.owner_id = ? OR b.project_manager = ?))
                  OR
                  (wh.project_type='contract' AND c.owner_id = ?)
              )
              AND wh.user_id != ?
            ORDER BY wh.submit_time ASC
        """, (uid, uid, uid, uid))

    if pending.empty:
        st.info("暂无待审批工时")
        return

    for _, row in pending.iterrows():
        with st.container():
            st.markdown(f"**{row['user_name']}** 在 **{row['project']}** 填报了 **{row['hours']}** 小时")
            
            # 统一时间格式化函数
            def fmt(t):
                if t and len(t) >= 5:
                    return t[:5]
                return t or '--:--'
            
            start_str = fmt(row['start_time'])
            # 根据是否有加班决定显示实际下班时间
            if row['overtime_end']:
                actual_end = fmt(row['overtime_end'])
                st.caption(f"📅 实际上班时间：**{start_str}**  |  实际下班时间：**{actual_end}**")
            else:
                end_str = fmt(row['end_time'])
                st.caption(f"📅 上班时间：**{start_str}**  |  下班时间：**{end_str}**")
            
            # 显示加班时段（如果存在）
            if row['overtime_start'] and row['overtime_end']:
                ot_start_str = fmt(row['overtime_start'])
                ot_end_str = fmt(row['overtime_end'])
                st.caption(f"⏰ 加班时段：**{ot_start_str} - {ot_end_str}**  (时长 {row['overtime_hours']} 小时)")
            elif row['overtime_hours'] > 0:
                # 兼容仅有加班时长但无具体时段的数据
                st.caption(f"⏰ 加班时长：{row['overtime_hours']} 小时")
            
            st.caption(f"📆 日期：{row['work_date']}  |  提交时间：{row['submit_time']}")
            st.markdown(f"📝 描述：{row['description']}")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ 批准", key=f"approve_{row['id']}"):
                    execute_sql("""
                        UPDATE work_hours
                        SET status='approved', approve_time=?, approver_id=?
                        WHERE id=?
                    """, (datetime.now(), uid, row['id']))
                    st.success("已批准")
                    st.rerun()
            with col2:
                with st.popover("❌ 驳回"):
                    reason = st.text_input("驳回原因", key=f"reason_{row['id']}")
                    if st.button("确认驳回", key=f"reject_{row['id']}"):
                        if not reason.strip():
                            st.error("请填写驳回原因")
                        else:
                            execute_sql("""
                                UPDATE work_hours
                                SET status='rejected', reject_reason=?, approver_id=?
                                WHERE id=?
                            """, (reason.strip(), uid, row['id']))
                            st.success("已驳回")
                            st.rerun()
            st.divider()

    # 已审批记录
    st.subheader("已审批工时记录")
    if is_boss:
        approved = query_df("""
            SELECT wh.id, u.name as user_name,
                   CASE WHEN wh.project_type = 'business' THEN b.title
                        ELSE c.contract_name END as project,
                   wh.work_date, wh.hours, wh.description, wh.status, wh.approve_time, wh.reject_reason
            FROM work_hours wh
            JOIN users u ON wh.user_id = u.username
            LEFT JOIN business b ON wh.project_type='business' AND wh.project_id = b.id
            LEFT JOIN contracts c ON wh.project_type='contract' AND wh.project_id = c.id
            WHERE wh.status IN ('approved', 'rejected')
            ORDER BY wh.approve_time DESC
        """)
    else:
        approved = query_df("""
            SELECT wh.id, u.name as user_name,
                   CASE WHEN wh.project_type = 'business' THEN b.title
                        ELSE c.contract_name END as project,
                   wh.work_date, wh.hours, wh.description, wh.status, wh.approve_time, wh.reject_reason
            FROM work_hours wh
            JOIN users u ON wh.user_id = u.username
            LEFT JOIN business b ON wh.project_type='business' AND wh.project_id = b.id
            LEFT JOIN contracts c ON wh.project_type='contract' AND wh.project_id = c.id
            WHERE wh.status IN ('approved', 'rejected')
              AND (
                  (wh.project_type='business' AND (b.owner_id = ? OR b.project_manager = ?))
                  OR
                  (wh.project_type='contract' AND c.owner_id = ?)
              )
              AND wh.user_id != ?
            ORDER BY wh.approve_time DESC
        """, (uid, uid, uid, uid))
    if not approved.empty:
        status_map = {'approved': '已批准', 'rejected': '已驳回'}
        approved['status_cn'] = approved['status'].map(status_map)
        st.dataframe(approved[['user_name', 'project', 'work_date', 'hours', 'description', 'status_cn', 'reject_reason']],
                     use_container_width=True, hide_index=True)
    else:
        st.info("暂无已审批记录")

# ========== 工时报表 ==========
def show_time_reports(uid: str, is_boss: bool, user_roles: list):
    st.subheader("工时数据分析")
    if is_boss:
        hours_data = query_df("""
            SELECT wh.*, u.name as user_name,
                   CASE WHEN wh.project_type = 'business' THEN b.title
                        ELSE c.contract_name END as project
            FROM work_hours wh
            JOIN users u ON wh.user_id = u.username
            LEFT JOIN business b ON wh.project_type='business' AND wh.project_id = b.id
            LEFT JOIN contracts c ON wh.project_type='contract' AND wh.project_id = c.id
            WHERE wh.status = 'approved'
        """)
    elif '技术研发' in user_roles:
        hours_data = query_df("""
            SELECT wh.*, u.name as user_name,
                   CASE WHEN wh.project_type = 'business' THEN b.title
                        ELSE c.contract_name END as project
            FROM work_hours wh
            JOIN users u ON wh.user_id = u.username
            LEFT JOIN business b ON wh.project_type='business' AND wh.project_id = b.id
            LEFT JOIN contracts c ON wh.project_type='contract' AND wh.project_id = c.id
            WHERE wh.user_id = ? AND wh.status = 'approved'
        """, (uid,))
    else:
        hours_data = query_df("""
            SELECT wh.*, u.name as user_name,
                   CASE WHEN wh.project_type = 'business' THEN b.title
                        ELSE c.contract_name END as project
            FROM work_hours wh
            JOIN users u ON wh.user_id = u.username
            LEFT JOIN business b ON wh.project_type='business' AND wh.project_id = b.id
            LEFT JOIN contracts c ON wh.project_type='contract' AND wh.project_id = c.id
            WHERE wh.status = 'approved'
              AND (
                  (wh.project_type='business' AND (b.owner_id = ? OR b.project_manager = ?))
                  OR
                  (wh.project_type='contract' AND c.owner_id = ?)
              )
        """, (uid, uid, uid))

    if hours_data.empty:
        st.info("暂无已批准的工时数据")
        return

    hours_data['work_date'] = pd.to_datetime(hours_data['work_date'])
    hours_data['month'] = hours_data['work_date'].dt.strftime('%Y-%m')

    monthly = hours_data.groupby('month')['hours'].sum().reset_index()
    fig1 = px.line(monthly, x='month', y='hours', markers=True, title="月度总工时趋势")
    st.plotly_chart(fig1, use_container_width=True)

    project_hours = hours_data.groupby('project')['hours'].sum().reset_index().sort_values('hours', ascending=False).head(10)
    fig2 = px.pie(project_hours, values='hours', names='project', title="项目工时分布（前10）")
    st.plotly_chart(fig2, use_container_width=True)

    user_hours = hours_data.groupby('user_name')['hours'].sum().reset_index().sort_values('hours', ascending=False)
    fig3 = px.bar(user_hours, x='user_name', y='hours', title="员工工时排行", color='hours', color_continuous_scale='Blues')
    st.plotly_chart(fig3, use_container_width=True)

    with st.expander("查看详细工时数据"):
        st.dataframe(hours_data[['user_name', 'project', 'work_date', 'hours', 'description']], use_container_width=True)

# ========== 项目成本分析 ==========
def show_project_cost(uid: str, is_boss: bool, user_roles: list):
    """项目成本与资源管理（基于人月成本）"""
    st.subheader("项目人力成本分析")

    from config import WORK_DAYS_PER_MONTH, WORK_HOURS_PER_DAY, COST_PER_MONTH

    # 获取项目列表（根据权限）
    if is_boss:
        businesses = query_df("SELECT id, title, amount, 'business' as type FROM business WHERE status != 'void'")
        contracts = query_df("SELECT id, contract_name as title, total_amt as amount, 'contract' as type FROM contracts")
        projects = pd.concat([businesses, contracts], ignore_index=True)
    elif '技术研发' in user_roles:
        projects = query_df("""
            SELECT pa.project_id as id,
                   CASE WHEN pa.project_type='business' THEN b.title
                        ELSE c.contract_name END as title,
                   CASE WHEN pa.project_type='business' THEN b.amount
                        ELSE c.total_amt END as amount,
                   pa.project_type as type
            FROM project_assignments pa
            LEFT JOIN business b ON pa.project_type='business' AND pa.project_id = b.id
            LEFT JOIN contracts c ON pa.project_type='contract' AND pa.project_id = c.id
            WHERE pa.user_id = ? AND (b.status != 'void' OR c.id IS NOT NULL)
        """, (uid,))
    else:
        businesses = query_df("""
            SELECT id, title, amount, 'business' as type
            FROM business
            WHERE (owner_id = ? OR project_manager = ?) AND status != 'void'
        """, (uid, uid))
        contracts = query_df("""
            SELECT id, contract_name as title, total_amt as amount, 'contract' as type
            FROM contracts
            WHERE owner_id = ?
        """, (uid,))
        projects = pd.concat([businesses, contracts], ignore_index=True)

    if projects.empty:
        st.info("无项目数据")
        return

    cost_data = []
    for _, proj in projects.iterrows():
        # 获取该项目下已批准的工时总和
        total_hours_df = query_df("""
            SELECT SUM(hours) as total_hours
            FROM work_hours
            WHERE project_type = ? AND project_id = ? AND status = 'approved'
        """, (proj['type'], proj['id']))
        # 处理可能的 NULL 值
        total_hours = total_hours_df.iloc[0]['total_hours'] if not total_hours_df.empty and total_hours_df.iloc[0]['total_hours'] is not None else 0.0

        # 计算人月数和成本
        total_person_months = total_hours / (WORK_DAYS_PER_MONTH * WORK_HOURS_PER_DAY)
        total_cost = total_person_months * COST_PER_MONTH

        budget = proj['amount'] if proj['amount'] else 0
        cost_data.append({
            '项目名称': proj['title'],
            '总工时': total_hours,
            '人月数': round(total_person_months, 2),
            '人力成本(元)': round(total_cost, 2),
            '预算(元)': budget,
            '成本占比': (total_cost / budget * 100) if budget > 0 else 0
        })

    df_cost = pd.DataFrame(cost_data)
    if not df_cost.empty:
        st.dataframe(df_cost, use_container_width=True, hide_index=True,
                     column_config={
                         "人月数": st.column_config.NumberColumn(format="%.2f"),
                         "人力成本(元)": st.column_config.NumberColumn(format="¥%.2f"),
                         "预算(元)": st.column_config.NumberColumn(format="¥%.2f"),
                         "成本占比": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100)
                     })
        fig = px.bar(df_cost, x='项目名称', y=['人力成本(元)', '预算(元)'], barmode='group', title="项目预算 vs 实际人力成本")
        st.plotly_chart(fig, use_container_width=True)
        over_budget = df_cost[df_cost['人力成本(元)'] > df_cost['预算(元)']]
        if not over_budget.empty:
            st.warning(f"⚠️ 以下项目人力成本已超出预算：{', '.join(over_budget['项目名称'].tolist())}")
    else:
        st.info("暂无成本数据")

    # 员工工时负荷（不变）
    st.subheader("员工工时负荷")
    if is_boss:
        user_load = query_df("""
            SELECT u.name, SUM(wh.hours) as total_hours
            FROM work_hours wh
            JOIN users u ON wh.user_id = u.username
            WHERE wh.status = 'approved'
            GROUP BY wh.user_id
            ORDER BY total_hours DESC
        """)
    elif '技术研发' in user_roles:
        user_load = query_df("""
            SELECT u.name, SUM(wh.hours) as total_hours
            FROM work_hours wh
            JOIN users u ON wh.user_id = u.username
            WHERE wh.user_id = ? AND wh.status = 'approved'
            GROUP BY wh.user_id
        """, (uid,))
    else:
        user_load = query_df("""
            SELECT u.name, SUM(wh.hours) as total_hours
            FROM work_hours wh
            JOIN users u ON wh.user_id = u.username
            LEFT JOIN business b ON wh.project_type='business' AND wh.project_id = b.id
            LEFT JOIN contracts c ON wh.project_type='contract' AND wh.project_id = c.id
            WHERE wh.status = 'approved'
              AND (
                  (wh.project_type='business' AND (b.owner_id = ? OR b.project_manager = ?))
                  OR
                  (wh.project_type='contract' AND c.owner_id = ?)
              )
            GROUP BY wh.user_id
            ORDER BY total_hours DESC
        """, (uid, uid, uid))
    if not user_load.empty:
        st.bar_chart(user_load.set_index('name'))
    else:
        st.info("暂无工时数据")