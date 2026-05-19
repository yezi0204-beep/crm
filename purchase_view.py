# purchase_view.py
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from database import query_df
from utils import get_user_map

def show_purchase_view(uid: str):
    st.title("📊 采购视图")
    st.info("查看本周资金使用情况和下周资金使用计划（仅汇总，不可编辑）")

    today = date.today()
    # 本周一至周日
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    # 下周
    next_week_start = start_of_week + timedelta(days=7)
    next_week_end = next_week_start + timedelta(days=6)

    # 1. 本周实际支出（已完成付款计划）
    completed_this_week = query_df("""
        SELECT amount, description, related_type, related_id, plan_date
        FROM payment_plans
        WHERE status = 'completed'
          AND plan_date BETWEEN ? AND ?
        ORDER BY plan_date ASC
    """, (start_of_week, end_of_week))

    st.subheader(f"本周已付款/资金使用（{start_of_week} 至 {end_of_week}）")
    if not completed_this_week.empty:
        total_this_week = completed_this_week['amount'].sum()
        st.metric("本周累计支出", f"￥{total_this_week:,.2f}")
        # 展示明细
        completed_this_week['金额(元)'] = completed_this_week['amount']
        st.dataframe(
            completed_this_week[['plan_date', '金额(元)', 'description', 'related_type', 'related_id']],
            column_config={
                "plan_date": "日期",
                "金额(元)": st.column_config.NumberColumn(format="¥%.2f"),
                "description": "用途说明",
                "related_type": "关联类型",
                "related_id": "关联ID"
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("本周暂无已完成付款记录")

    # 2. 下周资金使用计划（待执行）
    pending_next_week = query_df("""
        SELECT amount, description, related_type, related_id, plan_date
        FROM payment_plans
        WHERE status = 'pending'
          AND plan_date BETWEEN ? AND ?
        ORDER BY plan_date ASC
    """, (next_week_start, next_week_end))

    st.subheader(f"下周资金使用计划（{next_week_start} 至 {next_week_end}）")
    if not pending_next_week.empty:
        total_next_week = pending_next_week['amount'].sum()
        st.metric("下周计划支出", f"￥{total_next_week:,.2f}")
        pending_next_week['金额(元)'] = pending_next_week['amount']
        st.dataframe(
            pending_next_week[['plan_date', '金额(元)', 'description', 'related_type', 'related_id']],
            column_config={
                "plan_date": "计划日期",
                "金额(元)": st.column_config.NumberColumn(format="¥%.2f"),
                "description": "用途说明",
                "related_type": "关联类型",
                "related_id": "关联ID"
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("下周暂无计划")

    # 3. 按人员汇总（可选）
    st.subheader("按负责人汇总下周计划")
    by_user = query_df("""
        SELECT u.name, SUM(p.amount) as total_amount
        FROM payment_plans p
        JOIN users u ON p.user_id = u.username
        WHERE p.status = 'pending' AND p.plan_date BETWEEN ? AND ?
        GROUP BY p.user_id
        ORDER BY total_amount DESC
    """, (next_week_start, next_week_end))
    if not by_user.empty:
        st.dataframe(by_user, column_config={"total_amount": st.column_config.NumberColumn("金额(元)", format="¥%.2f")})
    else:
        st.info("无数据")