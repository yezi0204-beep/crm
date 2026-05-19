# timeline.py

import streamlit as st
import pandas as pd
from datetime import datetime, date
from database import query_df, execute_sql
from utils import get_user_map, update_customer_last_follow, clear_user_cache

def show_timeline(uid: str, is_boss: bool):
    """商机全周期日志模块"""
    st.title("📈 商机全周期日志")

    # 获取用户映射（用于显示姓名）
    user_map = get_user_map()

    # 加载商机列表（根据权限）
    if is_boss:
        df_b = query_df("SELECT id, title, owner_id FROM business ORDER BY created_at DESC")
    else:
        df_b = query_df("SELECT id, title, owner_id FROM business WHERE owner_id = ? ORDER BY created_at DESC", (uid,))

    if df_b.empty:
        st.info("暂无商机")
        return

    # 构建选择框选项
    biz_options = {
        f"{row['id']} - {row['title']} (负责人: {user_map.get(row['owner_id'], row['owner_id'])})": row['id']
        for _, row in df_b.iterrows()
    }
    selected_biz = st.selectbox("选择商机查看全周期日志", list(biz_options.keys()))
    biz_id = biz_options[selected_biz]

    # 获取商机基本信息
    biz_info = query_df("SELECT title, stage, amount FROM business WHERE id = ?", (biz_id,)).iloc[0]
    st.markdown(f"**商机标题**：{biz_info['title']}  \n"
                f"**当前阶段**：{biz_info['stage']}  \n"
                f"**预计金额**：￥{biz_info['amount']:,.0f}")

    # 获取阶段变更日志
    stage_logs = query_df("""
        SELECT * FROM business_stage_logs
        WHERE business_id = ?
        ORDER BY changed_at ASC
    """, (biz_id,))

    # 获取跟进日志（关联商机）
    follow_logs = query_df("""
        SELECT *,
               coalesce(log_time, created_at) as display_time
        FROM follow_logs
        WHERE ref_type='business' AND ref_id = ?
        ORDER BY display_time ASC
    """, (biz_id,))

    st.subheader("⏳ 时间线")

    if stage_logs.empty and follow_logs.empty:
        st.info("暂无任何记录")
        return

    # 合并时间线
    timeline = []
    for _, row in stage_logs.iterrows():
        timeline.append({
            'time': pd.to_datetime(row['changed_at']),
            'type': '阶段变更',
            'content': f"阶段从 **{row['old_stage']}** 变更为 **{row['new_stage']}**",
            'user': row['user_id'],
            'data': row,
            'table': 'stage_log'
        })
    for _, row in follow_logs.iterrows():
        timeline.append({
            'time': pd.to_datetime(row['display_time']),
            'type': '跟进',
            'content': row['content'],
            'user': row['user_id'],
            'data': row,
            'table': 'follow_log'
        })
    timeline.sort(key=lambda x: x['time'])

    # 展示时间线
    for entry in timeline:
        with st.container():
            cols = st.columns([2, 1, 6])
            with cols[0]:
                st.caption(entry['time'].strftime('%Y-%m-%d %H:%M'))
            with cols[1]:
                st.markdown(f"`{entry['type']}`")
            with cols[2]:
                user_name = user_map.get(entry['user'], entry['user'])
                st.markdown(f"**{user_name}**：{entry['content']}")
                # 如果是跟进日志，展示额外字段
                if entry['type'] == '跟进':
                    data = entry['data']
                    if data['subject']:
                        st.markdown(f"**主题**：{data['subject']}")
                    if data['participants']:
                        st.markdown(f"**相关人员**：{data['participants']}")
                    if data['location']:
                        st.markdown(f"**地点**：{data['location']}")
                    if data['next_plan']:
                        st.markdown(f"**下一步计划**：{data['next_plan']}")

                # 编辑/删除按钮（仅主任或记录者本人）
                can_edit = is_boss or entry['user'] == uid
                if can_edit:
                    # 编辑按钮
                    with st.popover("✏️"):
                        if entry['type'] == '跟进':
                            with st.form(f"edit_follow_{entry['data']['id']}"):
                                edit_content = st.text_area("跟进内容 *", value=entry['data']['content'])
                                edit_subject = st.text_input("主题", value=entry['data']['subject'] if entry['data']['subject'] else "")
                                edit_participants = st.text_input("相关人员", value=entry['data']['participants'] if entry['data']['participants'] else "")
                                edit_location = st.text_input("地点", value=entry['data']['location'] if entry['data']['location'] else "")
                                edit_next_plan = st.text_area("下一步工作计划", value=entry['data']['next_plan'] if entry['data']['next_plan'] else "")
                                # 日期时间处理
                                default_time = pd.to_datetime(entry['data']['log_time']) if entry['data']['log_time'] else pd.to_datetime(entry['data']['created_at'])
                                edit_date = st.date_input("日期", value=default_time.date() if pd.notna(default_time) else date.today())
                                edit_time = st.time_input("时间", value=default_time.time() if pd.notna(default_time) else datetime.now().time())
                                if st.form_submit_button("保存修改"):
                                    combined = datetime.combine(edit_date, edit_time)
                                    time_str = combined.strftime('%Y-%m-%d %H:%M:%S')
                                    update_sql = """
                                        UPDATE follow_logs
                                        SET content=?, subject=?, participants=?, location=?, next_plan=?, log_time=?
                                        WHERE id=?
                                    """
                                    try:
                                        execute_sql(update_sql, (edit_content, edit_subject, edit_participants, edit_location, edit_next_plan, time_str, entry['data']['id']))
                                        # 更新关联客户的最后跟进日期
                                        cust_res = query_df("SELECT cust_id FROM business WHERE id = ?", (biz_id,))
                                        if not cust_res.empty:
                                            cust_id = cust_res.iloc[0]['cust_id']
                                            update_customer_last_follow(cust_id, combined)
                                        st.success("更新成功")
                                        clear_user_cache()
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"更新失败: {e}")
                        else:
                            # 阶段变更日志不可编辑
                            st.info("阶段变更日志不支持编辑")

                    # 删除按钮
                    with st.popover("🗑️"):
                        st.warning("确定删除此记录？")
                        if st.button("确认删除", key=f"del_{entry['type']}_{entry['data']['id']}"):
                            try:
                                if entry['type'] == '跟进':
                                    execute_sql("DELETE FROM follow_logs WHERE id = ?", (entry['data']['id'],))
                                else:
                                    execute_sql("DELETE FROM business_stage_logs WHERE id = ?", (entry['data']['id'],))
                                st.success("删除成功")
                                clear_user_cache()
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"删除失败: {e}")

            st.divider()