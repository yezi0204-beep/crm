# dashboard.py

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
from database import query_df, execute_sql
from utils import get_user_map, clear_user_cache
from config import STAGES

def show_dashboard(uid: str, is_boss: bool):
    """销售驾驶舱（含年度回款、月度签约额）"""
    st.title("📈 销售驾驶舱")

    user_map = get_user_map()
    today = date.today()
    current_year = today.year

    # ---------- 1. 加载数据（带权限） ----------
    if is_boss:
        df_b = query_df("SELECT * FROM business WHERE status = 'active'")
        df_c = query_df("SELECT * FROM contracts")
        df_cust = query_df("SELECT * FROM customers")
    else:
        df_b = query_df("SELECT * FROM business WHERE owner_id = ? AND status = 'active'", (uid,))
        df_c = query_df("SELECT * FROM contracts WHERE owner_id = ?", (uid,))
        df_cust = query_df("SELECT * FROM customers WHERE owner_id = ?", (uid,))

    # 数值列转换
    if not df_b.empty:
        df_b['amount'] = pd.to_numeric(df_b['amount'], errors='coerce').fillna(0)
        if 'predict_date' in df_b.columns:
            df_b['predict_date'] = pd.to_datetime(df_b['predict_date'], errors='coerce')
    if not df_c.empty:
        df_c['paid_amt'] = pd.to_numeric(df_c['paid_amt'], errors='coerce').fillna(0)
        df_c['total_amt'] = pd.to_numeric(df_c['total_amt'], errors='coerce').fillna(0)
        if 'sign_date' in df_c.columns:
            df_c['sign_date'] = pd.to_datetime(df_c['sign_date'], errors='coerce')

    # ---------- 2. 顶部指标（原有4个 + 本年累计回款） ----------
    total_biz = df_b['amount'].sum() if not df_b.empty else 0
    total_signed = df_c['total_amt'].sum() if not df_c.empty else 0
    paid_v = df_c['paid_amt'].sum() if not df_c.empty else 0

    # 本月签约额
    current_month = datetime.now().strftime('%Y-%m')
    signed_this_month = 0
    if not df_c.empty and 'sign_date' in df_c.columns:
        month_mask = df_c['sign_date'].dt.strftime('%Y-%m') == current_month
        signed_this_month = df_c.loc[month_mask, 'total_amt'].sum()

    # 本年累计回款（基于 paid_amt，且签约日期在本年？回款日期没有记录，但回款金额是合同累计已回款，通常按合同签约年份？这里简单按合同签约年份的本年合同回款？更合理：使用 payment_records 表精确回款时间。但当前合同表只存储累计 paid_amt，没有回款时间明细。为了简化，我们展示所有合同的总回款额作为“累计回款”，另外增加“本年回款”需要基于 payment_records 表。
    # 由于 payment_records 表有 payment_date 和 amount，可以使用该表计算本年回款。
    # 因此新增查询 payment_records 表计算本年回款。
    if is_boss:
        payment_df = query_df("SELECT payment_date, amount FROM payment_records")
    else:
        payment_df = query_df("""
            SELECT pr.payment_date, pr.amount
            FROM payment_records pr
            JOIN contracts c ON pr.contract_id = c.id
            WHERE c.owner_id = ?
        """, (uid,))
    if not payment_df.empty:
        payment_df['payment_date'] = pd.to_datetime(payment_df['payment_date'], errors='coerce')
        this_year_payments = payment_df[payment_df['payment_date'].dt.year == current_year]
        paid_this_year = this_year_payments['amount'].sum() if not this_year_payments.empty else 0
    else:
        paid_this_year = 0

    # 公海更新
    execute_sql("UPDATE customers SET owner_id = NULL WHERE last_follow < date('now', '-30 days')")
    clear_user_cache()
    sea_count = query_df("SELECT COUNT(*) as cnt FROM customers WHERE owner_id IS NULL").iloc[0, 0]

    # 使用自定义布局展示5个指标
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("在手商机总额", f"￥{total_biz:,.0f}", delta="重点关注", delta_color="off")
    with col2:
        st.metric("本月签约额", f"￥{signed_this_month:,.0f}", delta="本月实绩")
    with col3:
        rate = (paid_v / total_signed * 100) if total_signed > 0 else 0
        st.metric("累计回款额", f"￥{paid_v:,.0f}", delta=f"整体回款率 {rate:.1f}%")
    with col4:
        st.metric("本年累计回款", f"￥{paid_this_year:,.0f}", delta="基于回款记录")
    with col5:
        st.metric("公海资源池", f"{sea_count} 位", delta="待分配", delta_color="inverse")

    st.divider()

    # ---------- 3. 原有左侧漏斗、右侧回款健康度 ----------
    col_l, col_r = st.columns([6, 4])
    with col_l:
        st.subheader("🔥 销售漏斗与转化路径")
        if not df_b.empty:
            funnel_data = df_b.groupby('stage')['amount'].sum().reindex(STAGES).reset_index().fillna(0)
            fig_funnel = px.funnel(funnel_data, x='amount', y='stage',
                                   color='stage', color_discrete_sequence=px.colors.sequential.Reds_r,
                                   labels={'amount': '商机金额'})
            fig_funnel.update_layout(showlegend=False, height=400)
            st.plotly_chart(fig_funnel, use_container_width=True)
        else:
            st.info("暂无商机分布数据")

    with col_r:
        st.subheader("📅 回款健康度 (总览)")
        if not df_c.empty:
            unpaid_v = total_signed - paid_v
            fig_pie = px.pie(values=[paid_v, unpaid_v], names=['已回款', '待回款'],
                             hole=0.6, color_discrete_sequence=['#2ECC71', '#E74C3C'])
            fig_pie.update_layout(height=350, margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("暂无合同回款数据")

    st.divider()

    # ---------- 4. 新增：每年回款金额（基于 payment_records） ----------
    st.subheader("💰 每年回款金额趋势")
    if not payment_df.empty and len(payment_df) > 0:
        payment_df['year'] = payment_df['payment_date'].dt.year
        yearly_payment = payment_df.groupby('year')['amount'].sum().reset_index()
        yearly_payment = yearly_payment.sort_values('year')
        fig_yearly = px.bar(yearly_payment, x='year', y='amount', title="各年度回款总额",
                            labels={'amount': '回款金额(元)', 'year': '年份'},
                            text_auto='.0f')
        fig_yearly.update_layout(height=400)
        st.plotly_chart(fig_yearly, use_container_width=True)
    else:
        st.info("暂无回款数据")

    st.divider()

    # ---------- 5. 新增：本年度每个月累计新签合同额 ----------
    st.subheader(f"📅 {current_year}年每月新签合同额")
    if not df_c.empty and 'sign_date' in df_c.columns:
        # 筛选本年度签约合同
        this_year_contracts = df_c[df_c['sign_date'].dt.year == current_year].copy()
        if not this_year_contracts.empty:
            this_year_contracts['month'] = this_year_contracts['sign_date'].dt.month
            monthly_signed = this_year_contracts.groupby('month')['total_amt'].sum().reset_index()
            # 补全缺失月份
            all_months = pd.DataFrame({'month': range(1, 13)})
            monthly_signed = all_months.merge(monthly_signed, on='month', how='left').fillna(0)
            monthly_signed['month_name'] = monthly_signed['month'].apply(lambda x: f"{x}月")
            fig_monthly = px.bar(monthly_signed, x='month_name', y='total_amt',
                                 title=f"{current_year}年每月新签合同额",
                                 labels={'total_amt': '签约金额(元)', 'month_name': '月份'},
                                 text_auto='.0f')
            fig_monthly.update_layout(height=400)
            st.plotly_chart(fig_monthly, use_container_width=True)
        else:
            st.info(f"{current_year}年暂无新签合同")
    else:
        st.info("暂无合同数据")

    st.divider()

    # ---------- 6. 原有底部：排行榜/个人预测 + 待办预警 ----------
    bot_l, bot_r = st.columns([5, 5])
    with bot_l:
        if is_boss:
            st.subheader("🏆 销售战绩排行榜")
            if not df_b.empty:
                rank = df_b.groupby('owner_id')['amount'].sum().reset_index()
                rank['amount_wan'] = rank['amount'] / 10000
                rank['owner_name'] = rank['owner_id'].map(user_map).fillna(rank['owner_id'])
                rank_sorted = rank.sort_values('amount_wan', ascending=True)
                fig_bar = px.bar(rank_sorted, y='owner_name', x='amount_wan', orientation='h',
                                 color='amount_wan', color_continuous_scale='GnBu',
                                 text_auto='.2f', title="各成员负责商机总额（万元）")
                fig_bar.update_layout(xaxis_title="商机总额（万元）", yaxis_title="负责人")
                st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info("暂无商机数据")
        else:
            st.subheader("🚀 个人成交预测 (按月)")
            if not df_b.empty and 'predict_date' in df_b.columns:
                personal_b = df_b[df_b['owner_id'] == uid].dropna(subset=['predict_date'])
                if not personal_b.empty:
                    personal_b['month'] = personal_b['predict_date'].dt.strftime('%Y-%m')
                    trend = personal_b.groupby('month')['amount'].sum().reset_index()
                    fig_trend = px.line(trend, x='month', y='amount', markers=True, title="预计成交额趋势")
                    st.plotly_chart(fig_trend, use_container_width=True)
                else:
                    st.info("暂无有效的预计签约日期")
            else:
                st.info("暂无商机数据")

    with bot_r:
        st.subheader("📋 待办预警看板")
        if not df_b.empty:
            biz_ids = df_b['id'].tolist()
            if biz_ids:
                biz_follow_sql = """
                    SELECT ref_id as business_id, MAX(coalesce(log_time, created_at)) as last_follow_time
                    FROM follow_logs
                    WHERE ref_type='business' AND ref_id IN ({})
                    GROUP BY ref_id
                """.format(','.join(['?']*len(biz_ids)))
                biz_follow_df = query_df(biz_follow_sql, biz_ids)
                biz_follow_dict = dict(zip(biz_follow_df['business_id'], pd.to_datetime(biz_follow_df['last_follow_time'])))
                all_cust_follow = query_df("SELECT id, last_follow FROM customers")
                cust_follow_dict = dict(zip(all_cust_follow['id'], pd.to_datetime(all_cust_follow['last_follow'], errors='coerce')))
                alert_list = []
                for _, row in df_b.iterrows():
                    biz_id = row['id']
                    cust_id = row['cust_id']
                    biz_last = biz_follow_dict.get(biz_id)
                    cust_last = cust_follow_dict.get(cust_id) if cust_id else None
                    valid_times = [t for t in [biz_last, cust_last] if pd.notna(t)]
                    if valid_times:
                        last_time = max(valid_times)
                        days_passed = (datetime.now() - last_time).days
                        if days_passed > 7:
                            alert_list.append({
                                'title': row['title'],
                                'amount': row['amount'],
                                'days_passed': days_passed
                            })
                if alert_list:
                    alert_df = pd.DataFrame(alert_list).sort_values('amount', ascending=False)
                    alert_df['amount'] = alert_df['amount'] / 10000
                    alert_df.columns = ['项目名称', '商机金额(万元)', '停滞天数']
                    st.warning(f"检测到 {len(alert_df)} 个项目超过7天未跟进：")
                    st.dataframe(alert_df[['项目名称', '商机金额(万元)', '停滞天数']],
                                 use_container_width=True, hide_index=True)
                else:
                    st.success("暂无停滞高风险项目，跟进非常及时！")
            else:
                st.info("暂无商机数据")
        else:
            st.info("暂无商机数据")