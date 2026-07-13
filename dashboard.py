# dashboard.py

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
from database import query_df, execute_sql
from utils import get_user_map, clear_user_cache
from config import STAGES
from settings import HIGH_SEAS_DAYS_THRESHOLD


def load_business_data(uid: str, is_boss: bool):
    """加载商机数据（带缓存）"""
    if is_boss:
        df = query_df("SELECT id, cust_id, title, amount, stage, predict_date, owner_id FROM business WHERE status = 'active'")
    else:
        df = query_df("SELECT id, cust_id, title, amount, stage, predict_date, owner_id FROM business WHERE owner_id = ? AND status = 'active'", (uid,))
    if not df.empty:
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
        if 'predict_date' in df.columns:
            df['predict_date'] = pd.to_datetime(df['predict_date'], errors='coerce')
    return df


def load_contracts_data(uid: str, is_boss: bool):
    """加载合同数据（带缓存）"""
    if is_boss:
        df = query_df("SELECT id, total_amt, paid_amt, sign_date, owner_id FROM contracts")
    else:
        df = query_df("SELECT id, total_amt, paid_amt, sign_date, owner_id FROM contracts WHERE owner_id = ?", (uid,))
    if not df.empty:
        df['paid_amt'] = pd.to_numeric(df['paid_amt'], errors='coerce').fillna(0)
        df['total_amt'] = pd.to_numeric(df['total_amt'], errors='coerce').fillna(0)
        if 'sign_date' in df.columns:
            df['sign_date'] = pd.to_datetime(df['sign_date'], errors='coerce')
    return df


def load_payments_data(uid: str, is_boss: bool):
    """加载回款数据（带缓存）"""
    if is_boss:
        df = query_df("SELECT payment_date, amount FROM payment_records")
    else:
        df = query_df("""
            SELECT pr.payment_date, pr.amount
            FROM payment_records pr
            JOIN contracts c ON pr.contract_id = c.id
            WHERE c.owner_id = ?
        """, (uid,))
    if not df.empty:
        df['payment_date'] = pd.to_datetime(df['payment_date'], errors='coerce')
    return df


def get_high_seas_data():
    """获取公海池数据（带缓存，短期TTL）"""
    sea_count = query_df("SELECT COUNT(*) as cnt FROM customers WHERE owner_id IS NULL").iloc[0, 0]
    customers_to_release = query_df(f"""
        SELECT id, name, company, owner_id, last_follow 
        FROM customers 
        WHERE owner_id IS NOT NULL 
        AND last_follow < date('now', '-{HIGH_SEAS_DAYS_THRESHOLD} days')
    """)
    return sea_count, customers_to_release


def get_follow_alerts(df_b, uid, is_boss):
    """获取跟进预警数据（带缓存）"""
    if df_b.empty:
        return []
    
    biz_ids = df_b['id'].tolist()
    if not biz_ids:
        return []
    
    # 更高效的查询方式
    placeholders = ','.join(['?']*len(biz_ids))
    biz_follow_sql = f"""
        SELECT ref_id as business_id, MAX(coalesce(log_time, created_at)) as last_follow_time
        FROM follow_logs
        WHERE ref_type='business' AND ref_id IN ({placeholders})
        GROUP BY ref_id
    """
    biz_follow_df = query_df(biz_follow_sql, biz_ids)
    biz_follow_dict = dict(zip(biz_follow_df['business_id'], pd.to_datetime(biz_follow_df['last_follow_time'])))
    
    # 只查询需要的客户
    cust_ids = df_b['cust_id'].dropna().unique().tolist()
    if cust_ids:
        cust_placeholders = ','.join(['?']*len(cust_ids))
        all_cust_follow = query_df(f"SELECT id, last_follow FROM customers WHERE id IN ({cust_placeholders})", cust_ids)
    else:
        all_cust_follow = pd.DataFrame(columns=['id', 'last_follow'])
    
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
    return alert_list


def show_dashboard(uid: str, is_boss: bool):
    """销售驾驶舱（优化版本）"""
    st.title("📈 销售驾驶舱")
    
    # 使用容器和占位符优化渲染
    main_container = st.container()
    
    with main_container:
        # 并行加载数据（使用st.status显示进度）
        with st.status("正在加载数据...", expanded=False) as status:
            user_map = get_user_map()
            today = date.today()
            current_year = today.year
            
            status.update(label="加载商机数据...")
            df_b = load_business_data(uid, is_boss)
            
            status.update(label="加载合同数据...")
            df_c = load_contracts_data(uid, is_boss)
            
            status.update(label="加载回款数据...")
            payment_df = load_payments_data(uid, is_boss)
            
            status.update(label="加载公海池数据...")
            sea_count, customers_to_release = get_high_seas_data()
            
            status.update(label="数据加载完成！", state="complete")
        
        # ---------- 2. 顶部指标 ----------
        total_biz = df_b['amount'].sum() if not df_b.empty else 0
        total_signed = df_c['total_amt'].sum() if not df_c.empty else 0
        paid_v = df_c['paid_amt'].sum() if not df_c.empty else 0
        
        # 本月签约额
        current_month = datetime.now().strftime('%Y-%m')
        signed_this_month = 0
        if not df_c.empty and 'sign_date' in df_c.columns:
            month_mask = df_c['sign_date'].dt.strftime('%Y-%m') == current_month
            signed_this_month = df_c.loc[month_mask, 'total_amt'].sum()
        
        # 本年累计回款
        paid_this_year = 0
        if not payment_df.empty:
            this_year_payments = payment_df[payment_df['payment_date'].dt.year == current_year]
            paid_this_year = this_year_payments['amount'].sum() if not this_year_payments.empty else 0
        
        # 使用更美观的布局
        col1, col2, col3, col4, col5 = st.columns(5)
        metrics_data = [
            ("在手商机总额", f"￥{total_biz:,.0f}", "重点关注", "off"),
            ("本月签约额", f"￥{signed_this_month:,.0f}", "本月实绩", "normal"),
            ("累计回款额", f"￥{paid_v:,.0f}", f"整体回款率 {((paid_v / total_signed * 100) if total_signed > 0 else 0):.1f}%", "normal"),
            ("本年累计回款", f"￥{paid_this_year:,.0f}", "基于回款记录", "normal"),
            ("公海资源池", f"{sea_count} 位", "待分配", "inverse")
        ]
        
        for col, (label, value, delta, delta_color) in zip([col1, col2, col3, col4, col5], metrics_data):
            with col:
                st.metric(label, value, delta=delta, delta_color=delta_color)
        
        st.divider()
        
        # ---------- 3. 销售漏斗和回款健康度 ----------
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
        
        # ---------- 4. 每年回款金额趋势 ----------
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
        
        # ---------- 5. 本年度每月新签合同额 ----------
        st.subheader(f"📅 {current_year}年每月新签合同额")
        if not df_c.empty and 'sign_date' in df_c.columns:
            this_year_contracts = df_c[df_c['sign_date'].dt.year == current_year].copy()
            if not this_year_contracts.empty:
                this_year_contracts['month'] = this_year_contracts['sign_date'].dt.month
                monthly_signed = this_year_contracts.groupby('month')['total_amt'].sum().reset_index()
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
        
        # ---------- 6. 排行榜/个人预测 + 待办预警 ----------
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
            alert_list = get_follow_alerts(df_b, uid, is_boss)
            if alert_list:
                alert_df = pd.DataFrame(alert_list).sort_values('amount', ascending=False)
                alert_df['amount'] = alert_df['amount'] / 10000
                alert_df.columns = ['项目名称', '商机金额(万元)', '停滞天数']
                st.warning(f"检测到 {len(alert_df)} 个项目超过7天未跟进：")
                st.dataframe(alert_df[['项目名称', '商机金额(万元)', '停滞天数']],
                             use_container_width=True, hide_index=True)
            else:
                st.success("暂无停滞高风险项目，跟进非常及时！")
        
        st.divider()
        
        # ---------- 7. 即将进入公海的客户提醒 ----------
        st.subheader("⚠️ 即将进入公海的客户")
        if not customers_to_release.empty:
            st.warning(f"发现 {len(customers_to_release)} 个客户超过 {HIGH_SEAS_DAYS_THRESHOLD} 天未跟进，即将进入公海！")
            customers_to_release['owner_name'] = customers_to_release['owner_id'].map(user_map).fillna(customers_to_release['owner_id'])
            customers_to_release['last_follow'] = pd.to_datetime(customers_to_release['last_follow']).dt.date
            
            display_cols = ['name', 'company', 'owner_name', 'last_follow']
            st.dataframe(customers_to_release[display_cols],
                         use_container_width=True,
                         hide_index=True,
                         column_config={
                             "name": "客户姓名",
                             "company": "公司名称",
                             "owner_name": "负责人",
                             "last_follow": st.column_config.DateColumn("最后跟进日期")
                         })
            
            if is_boss:
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("📤 批量释放到公海", type="primary"):
                        with st.spinner("正在释放客户到公海..."):
                            for cust_id in customers_to_release['id']:
                                execute_sql("UPDATE customers SET owner_id = NULL WHERE id = ?", (cust_id,))
                            clear_user_cache()
                            st.success(f"已将 {len(customers_to_release)} 个客户释放到公海！")
                            st.rerun()
                with col2:
                    st.caption("提示：释放后客户将进入公海池，任何人都可以领取")
        else:
            st.success("所有客户跟进情况良好，没有即将进入公海的客户！")
