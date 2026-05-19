# search.py

import streamlit as st
import pandas as pd
from database import query_df
from utils import get_user_map

def show_search(uid: str, is_boss: bool):
    """全局搜索页面"""
    st.title("🔍 全局搜索")

    # 搜索关键词
    keyword = st.text_input("请输入搜索关键词（支持模糊匹配）", placeholder="客户名称、商机标题、合同编号等", key="global_search_input")
    if not keyword:
        st.info("输入关键词开始搜索")
        return

    keyword = keyword.strip()
    st.markdown(f"**搜索结果（关键词：{keyword}）**")

    # 获取用户权限
    user_roles = st.session_state.get('user_roles', [])
    is_pm = '项目经理' in user_roles

    # 1. 客户搜索
    if is_boss:
        cust_sql = """
            SELECT id, name, company, level, source, owner_id, last_follow
            FROM customers
            WHERE name LIKE ? OR company LIKE ? OR level LIKE ? OR source LIKE ?
        """
        cust_params = (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%')
    else:
        # 普通销售只能搜自己负责的客户，项目经理和售前类似
        cust_sql = """
            SELECT id, name, company, level, source, owner_id, last_follow
            FROM customers
            WHERE (owner_id = ?) AND (name LIKE ? OR company LIKE ? OR level LIKE ? OR source LIKE ?)
        """
        cust_params = (uid, f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%')
    cust_df = query_df(cust_sql, cust_params)
    if not cust_df.empty:
        st.subheader("👥 客户")
        user_map = get_user_map()
        cust_df['负责人'] = cust_df['owner_id'].map(user_map).fillna(cust_df['owner_id'])
        st.dataframe(
            cust_df[['name', 'company', 'level', 'source', '负责人', 'last_follow']],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("未找到相关客户")

    # 2. 商机搜索
    if is_boss:
        biz_sql = """
            SELECT b.id, b.title, b.amount, b.stage, b.predict_date, b.owner_id, c.name as customer_name
            FROM business b
            LEFT JOIN customers c ON b.cust_id = c.id
            WHERE b.title LIKE ? OR b.stage LIKE ? OR b.implementation_status LIKE ?
        """
        biz_params = (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%')
    else:
        biz_sql = """
            SELECT b.id, b.title, b.amount, b.stage, b.predict_date, b.owner_id, c.name as customer_name
            FROM business b
            LEFT JOIN customers c ON b.cust_id = c.id
            WHERE b.owner_id = ? AND (b.title LIKE ? OR b.stage LIKE ? OR b.implementation_status LIKE ?)
        """
        biz_params = (uid, f'%{keyword}%', f'%{keyword}%', f'%{keyword}%')
    biz_df = query_df(biz_sql, biz_params)
    if not biz_df.empty:
        st.subheader("🎯 商机")
        user_map = get_user_map()
        biz_df['负责人'] = biz_df['owner_id'].map(user_map).fillna(biz_df['owner_id'])
        biz_df['amount_wan'] = biz_df['amount'] / 10000
        st.dataframe(
            biz_df[['title', 'customer_name', 'amount_wan', 'stage', 'predict_date', '负责人']],
            column_config={
                "title": "商机名称",
                "customer_name": "客户",
                "amount_wan": st.column_config.NumberColumn("金额(万元)", format="%.2f"),
                "stage": "阶段",
                "predict_date": "预计签约日期",
                "负责人": "负责人"
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("未找到相关商机")

    # 3. 合同搜索
    if is_boss:
        contract_sql = """
            SELECT id, contract_name, contract_no, project_order_no, total_amt, sign_date, owner_id, classification, business_type, acceptance_date
            FROM contracts
            WHERE contract_name LIKE ? OR contract_no LIKE ? OR project_order_no LIKE ? OR classification LIKE ? OR business_type LIKE ?
        """
        contract_params = (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%')
    else:
        contract_sql = """
            SELECT id, contract_name, contract_no, project_order_no, total_amt, sign_date, owner_id, classification, business_type, acceptance_date
            FROM contracts
            WHERE owner_id = ? AND (contract_name LIKE ? OR contract_no LIKE ? OR project_order_no LIKE ? OR classification LIKE ? OR business_type LIKE ?)
        """
        contract_params = (uid, f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%')
    contract_df = query_df(contract_sql, contract_params)
    if not contract_df.empty:
        st.subheader("📜 合同")
        user_map = get_user_map()
        contract_df['负责人'] = contract_df['owner_id'].map(user_map).fillna(contract_df['owner_id'])
        contract_df['total_amt_wan'] = contract_df['total_amt'] / 10000
        st.dataframe(
            contract_df[['contract_name', 'contract_no', 'total_amt_wan', 'sign_date', 'classification', 'business_type', '负责人']],
            column_config={
                "contract_name": "合同名称",
                "contract_no": "合同编号",
                "total_amt_wan": st.column_config.NumberColumn("总额(万元)", format="%.2f"),
                "sign_date": "签约日期",
                "classification": "密级",
                "business_type": "业态",
                "负责人": "负责人"
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("未找到相关合同")

    # 4. 跟进记录搜索
    # 跟进记录需要关联权限：主任可看所有，其他人只能看自己创建的
    if is_boss:
        follow_sql = """
            SELECT fl.id, fl.ref_type, fl.ref_id, fl.content, fl.subject, fl.participants, fl.location, fl.next_plan, fl.log_time, fl.created_at,
                   u.name as user_name,
                   CASE WHEN fl.ref_type='business' THEN b.title
                        ELSE c.name END as ref_name
            FROM follow_logs fl
            LEFT JOIN users u ON fl.user_id = u.username
            LEFT JOIN business b ON fl.ref_type='business' AND fl.ref_id = b.id
            LEFT JOIN customers c ON fl.ref_type='customer' AND fl.ref_id = c.id
            WHERE fl.content LIKE ? OR fl.subject LIKE ? OR fl.participants LIKE ? OR fl.location LIKE ? OR fl.next_plan LIKE ?
        """
        follow_params = (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%')
    else:
        follow_sql = """
            SELECT fl.id, fl.ref_type, fl.ref_id, fl.content, fl.subject, fl.participants, fl.location, fl.next_plan, fl.log_time, fl.created_at,
                   u.name as user_name,
                   CASE WHEN fl.ref_type='business' THEN b.title
                        ELSE c.name END as ref_name
            FROM follow_logs fl
            LEFT JOIN users u ON fl.user_id = u.username
            LEFT JOIN business b ON fl.ref_type='business' AND fl.ref_id = b.id
            LEFT JOIN customers c ON fl.ref_type='customer' AND fl.ref_id = c.id
            WHERE fl.user_id = ? AND (fl.content LIKE ? OR fl.subject LIKE ? OR fl.participants LIKE ? OR fl.location LIKE ? OR fl.next_plan LIKE ?)
        """
        follow_params = (uid, f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%')
    follow_df = query_df(follow_sql, follow_params)
    if not follow_df.empty:
        st.subheader("📝 跟进记录")
        display = follow_df[['user_name', 'ref_name', 'subject', 'content', 'log_time']].copy()
        display['log_time'] = pd.to_datetime(display['log_time']).dt.strftime('%Y-%m-%d %H:%M')
        st.dataframe(
            display,
            column_config={
                "user_name": "跟进人",
                "ref_name": "关联对象",
                "subject": "主题",
                "content": "内容",
                "log_time": "时间"
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("未找到相关跟进记录")