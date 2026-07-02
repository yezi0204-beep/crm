# contracts.py - 合同管理模块（专注于合同）

import streamlit as st
import pandas as pd
from datetime import datetime, date
from database import query_df, execute_sql, get_db_connection
from utils import get_user_map, clear_user_cache
from config import CONTRACT_CLASSIFICATIONS, BUSINESS_TYPES


@st.cache_data(ttl=300, show_spinner="正在加载合同数据...")
def load_contracts_data(uid: str, is_boss: bool):
    """加载合同数据（带缓存）"""
    if is_boss:
        df = query_df("SELECT * FROM contracts ORDER BY sign_date DESC")
    else:
        df = query_df("SELECT * FROM contracts WHERE owner_id = ? ORDER BY sign_date DESC", (uid,))
    return df


def show_contracts(uid: str, is_boss: bool):
    """合同管理模块（专注于合同）"""
    st.title("📜 合同管理")

    user_map = get_user_map()
    today = date.today()

    # ---------- 新建合同（可折叠） ----------
    with st.expander("➕ 新建合同", expanded=False):
        with st.form("new_contract"):
            link_business = st.checkbox("关联商机（如不勾选，则录入历史合同）", value=True)
            b_id = None
            owner = uid

            if link_business:
                biz_df = query_df("SELECT id, title, owner_id FROM business WHERE stage='赢单成交' ORDER BY title")
                if biz_df.empty:
                    st.warning("暂无赢单商机，请先推进商机至赢单成交，或取消勾选直接录入历史合同")
                    b_id = None
                else:
                    biz_choices = {f"{row['id']} - {row['title']}": row['id'] for _, row in biz_df.iterrows()}
                    selected_biz = st.selectbox("关联商机", list(biz_choices.keys()))
                    b_id = biz_choices[selected_biz]
                    owner = biz_df[biz_df['id'] == b_id].iloc[0]['owner_id']
                    if not is_boss and owner != uid:
                        st.error("您只能为自己负责的商机创建合同。")
                        st.stop()
            else:
                if is_boss:
                    owner = st.text_input("负责人工号", value=uid, help="输入负责人用户名")
                else:
                    owner = uid
                st.info("负责人默认为您自己")

            contract_name = st.text_input("合同名称 *")
            contract_no = st.text_input("合同编号 *")
            party_a = st.text_input("甲方", placeholder="填写甲方单位全称")
            project_order_no = st.text_input("项目令号")
            total_amt = st.number_input("合同总额（万元）", min_value=0.0, step=1.0, format="%.2f") * 10000
            sign_date = st.date_input("签约日期", datetime.now().date())
            classification = st.selectbox("项目密级", CONTRACT_CLASSIFICATIONS)
            is_audit = st.checkbox("是否审价")
            pending_acceptance = st.number_input("待验收金额（万元）", min_value=0.0, step=1.0, format="%.2f") * 10000
            cost = st.number_input("成本（万元）", min_value=0.0, step=1.0, format="%.2f") * 10000
            gross_profit = st.number_input("毛利（万元）", min_value=0.0, step=1.0, format="%.2f",
                                           value=(total_amt - cost) / 10000 if total_amt and cost else 0.0) * 10000
            acceptance_date = st.date_input("合同验收日期", value=None)
            expected_income_date = st.date_input("预计形成收入日期", value=None)
            expected_income_year = st.number_input("预计本年收入金额（万元）", min_value=0.0, step=1.0, format="%.2f") * 10000
            business_type = st.selectbox("业态", BUSINESS_TYPES)

            if st.form_submit_button("保存合同"):
                if not contract_name.strip() or not contract_no.strip():
                    st.error("合同名称和合同编号不能为空")
                else:
                    existing = query_df("SELECT contract_no FROM contracts WHERE contract_no = ?", (contract_no.strip(),))
                    if not existing.empty:
                        st.error(f"合同编号 {contract_no} 已存在，请使用唯一的编号。")
                    else:
                        try:
                            with get_db_connection() as conn:
                                cursor = conn.cursor()
                                sql = """
                                    INSERT INTO contracts
                                    (b_id, contract_no, party_a, project_order_no, total_amt, paid_amt, sign_date, owner_id, status,
                                     contract_name, classification, is_audit, pending_acceptance_amount,
                                     cost, gross_profit, acceptance_date, expected_income_date,
                                     expected_income_year, business_type, total_cost)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                                """
                                params = (b_id, contract_no.strip(), party_a.strip(), project_order_no,
                                          total_amt, 0, sign_date, owner, '执行中',
                                          contract_name.strip(), classification, 1 if is_audit else 0, pending_acceptance,
                                          cost, gross_profit, acceptance_date, expected_income_date,
                                          expected_income_year, business_type)
                                cursor.execute(sql, params)
                                contract_id = cursor.lastrowid

                                # 如果关联了商机，将商机成本迁移到合同
                                if b_id:
                                    costs = query_df("""
                                        SELECT cost_type, amount, description, cost_date, created_by
                                        FROM costs
                                        WHERE project_type='business' AND project_id = ?
                                    """, (b_id,))
                                    if not costs.empty:
                                        for _, cost_row in costs.iterrows():
                                            cursor.execute("""
                                                INSERT INTO costs (project_type, project_id, cost_type, amount, description, cost_date, created_by)
                                                VALUES ('contract', ?, ?, ?, ?, ?, ?)
                                            """, (contract_id, cost_row['cost_type'], cost_row['amount'],
                                                  cost_row['description'], cost_row['cost_date'], cost_row['created_by']))
                                        total_migrated = costs['amount'].sum()
                                        cursor.execute("UPDATE contracts SET total_cost = total_cost + ? WHERE id = ?", (total_migrated, contract_id))
                                        st.info(f"已自动迁移商机成本 {total_migrated/10000:,.2f} 万元到合同。")
                                conn.commit()
                                st.success("合同录入成功")
                                clear_user_cache()
                                load_contracts_data.clear()
                                st.rerun()
                        except Exception as e:
                            st.error(f"保存失败: {e}")

    st.divider()

    # ---------- 加载合同数据 ----------
    df_con = load_contracts_data(uid, is_boss)

    if df_con.empty:
        st.info("暂无合同数据，请先创建合同")
        return

    # 数据处理
    numeric_cols = ['total_amt', 'paid_amt', 'pending_acceptance_amount', 'cost', 'gross_profit', 'expected_income_year', 'total_cost']
    for col in numeric_cols:
        if col in df_con.columns:
            df_con[col] = pd.to_numeric(df_con[col], errors='coerce').fillna(0)

    df_con['pending_payment'] = (df_con['total_amt'] - df_con['paid_amt']).clip(lower=0)
    df_con['owner_name'] = df_con['owner_id'].map(user_map).fillna(df_con['owner_id'])
    # 验收状态
    if 'acceptance_date' in df_con.columns:
        df_con['acceptance_date'] = pd.to_datetime(df_con['acceptance_date'], errors='coerce').dt.date
    df_con['is_accepted'] = df_con['acceptance_date'].apply(lambda d: False if pd.isna(d) else d <= today)
    df_con['验收状态'] = df_con['is_accepted'].map({True: '✅ 已验收', False: '❌ 未验收'})

    # ---------- 未验收合同快速处理 ----------
    df_unaccepted = df_con[~df_con['is_accepted']]
    if not df_unaccepted.empty:
        with st.expander(f"📋 未验收合同（共 {len(df_unaccepted)} 份，点击展开快速处理）", expanded=False):
            unaccepted_display = df_unaccepted[['contract_name', 'contract_no', 'party_a', 'total_amt', 'sign_date', 'owner_name']].copy()
            unaccepted_display['total_amt_wan'] = unaccepted_display['total_amt'] / 10000
            st.dataframe(
                unaccepted_display[['contract_name', 'contract_no', 'party_a', 'total_amt_wan', 'sign_date', 'owner_name']],
                column_config={
                    "contract_name": "合同名称",
                    "contract_no": "合同编号",
                    "party_a": "甲方",
                    "total_amt_wan": st.column_config.NumberColumn("合同总额(万元)", format="%.2f"),
                    "sign_date": "签约日期",
                    "owner_name": "负责人"
                },
                use_container_width=True,
                hide_index=True
            )

    st.divider()

    # ---------- 合同列表（表格视图 + 筛选） ----------
    st.subheader("📋 合同列表")
    
    # 筛选选项
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        search_term = st.text_input("🔍 搜索（名称/编号/甲方）", placeholder="输入关键词...")
    with col2:
        show_unaccepted_only = st.checkbox("仅显示未验收合同", value=False)
    with col3:
        selected_classification = st.selectbox("密级", ["全部"] + list(CONTRACT_CLASSIFICATIONS))
    with col4:
        if is_boss:
            owner_options = ["全部"] + list(user_map.values())
            owner_display = st.selectbox("负责人", owner_options)
            if owner_display != "全部":
                selected_owner = next(k for k, v in user_map.items() if v == owner_display)
            else:
                selected_owner = None
        else:
            selected_owner = None
    
    # 应用筛选
    df_con_display = df_con.copy()
    
    # 1. 验收状态筛选
    if show_unaccepted_only:
        df_con_display = df_con_display[~df_con_display['is_accepted']]
    
    # 2. 密级筛选
    if selected_classification != "全部":
        df_con_display = df_con_display[df_con_display['classification'] == selected_classification]
    
    # 3. 负责人筛选
    if selected_owner is not None:
        df_con_display = df_con_display[df_con_display['owner_id'] == selected_owner]
    
    # 4. 搜索筛选
    if search_term:
        search_term = search_term.lower()
        mask = (
            df_con_display['contract_name'].str.lower().str.contains(search_term, na=False) |
            df_con_display['contract_no'].str.lower().str.contains(search_term, na=False) |
            df_con_display['party_a'].str.lower().str.contains(search_term, na=False)
        )
        df_con_display = df_con_display[mask]

    if df_con_display.empty:
        st.info("没有符合条件的合同")
    else:
        # 展示表格
        table_df = df_con_display.copy()
        table_df['合同名称'] = table_df['contract_name']
        table_df['合同编号'] = table_df['contract_no']
        table_df['甲方'] = table_df['party_a']
        table_df['合同总额(万元)'] = table_df['total_amt'] / 10000
        table_df['已回款(万元)'] = table_df['paid_amt'] / 10000
        table_df['待回款(万元)'] = table_df['pending_payment'] / 10000
        table_df['验收状态'] = table_df['验收状态']
        table_df['密级'] = table_df['classification']
        table_df['业态'] = table_df['business_type']
        table_df['签约日期'] = table_df['sign_date']
        table_df['负责人'] = table_df['owner_name']
        table_df['状态'] = table_df['status']

        display_cols = ['合同名称', '合同编号', '甲方', '合同总额(万元)', '已回款(万元)', '待回款(万元)',
                       '验收状态', '密级', '业态', '签约日期', '负责人', '状态']

        st.dataframe(
            table_df[display_cols],
            column_config={
                "合同名称": st.column_config.TextColumn("合同名称"),
                "合同编号": st.column_config.TextColumn("合同编号"),
                "甲方": st.column_config.TextColumn("甲方"),
                "合同总额(万元)": st.column_config.NumberColumn("合同总额(万元)", format="%.2f"),
                "已回款(万元)": st.column_config.NumberColumn("已回款(万元)", format="%.2f"),
                "待回款(万元)": st.column_config.NumberColumn("待回款(万元)", format="%.2f"),
                "验收状态": st.column_config.TextColumn("验收状态"),
                "密级": st.column_config.TextColumn("密级"),
                "业态": st.column_config.TextColumn("业态"),
                "签约日期": st.column_config.DateColumn("签约日期"),
                "负责人": st.column_config.TextColumn("负责人"),
                "状态": st.column_config.TextColumn("状态")
            },
            use_container_width=True,
            hide_index=True
        )

    st.divider()

    # ---------- 合同操作面板 ----------
    if not df_con_display.empty:
        st.subheader("⚙️ 合同操作")
        
        # 选择要操作的合同
        select_options = []
        select_map = {}
        for _, row in df_con_display.iterrows():
            label = f"{row['contract_name']} - {row['contract_no']}"
            select_options.append(label)
            select_map[label] = row['id']
        
        selected_label = st.selectbox("选择要操作的合同", select_options)
        selected_id = select_map[selected_label]
        original_row = df_con[df_con['id'] == selected_id].iloc[0]
        can_edit = is_boss or original_row['owner_id'] == uid
        
        # 操作按钮
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            # 快速验收
            if not original_row['is_accepted'] and can_edit:
                if st.button("✅ 设为已验收"):
                    execute_sql("UPDATE contracts SET acceptance_date = ? WHERE id = ?", (today, selected_id))
                    st.success(f"合同 {original_row['contract_no']} 已标记为验收")
                    clear_user_cache()
                    load_contracts_data.clear()
                    st.rerun()
        
        with col2:
            if can_edit:
                with st.popover("✏️ 编辑合同"):
                    with st.form(f"edit_contract_{selected_id}"):
                        new_contract_name = st.text_input("合同名称", value=original_row['contract_name'])
                        new_contract_no = st.text_input("合同编号", value=original_row['contract_no'])
                        new_party_a = st.text_input("甲方", value=original_row['party_a'] if original_row.get('party_a') else "")
                        new_project_order = st.text_input("项目令号", value=original_row['project_order_no'] if pd.notna(original_row['project_order_no']) else "")
                        new_total = st.number_input("合同总额(万元)", min_value=0.0, step=1.0, format="%.2f", value=original_row['total_amt']/10000) * 10000
                        new_sign_date = st.date_input("签约日期", value=pd.to_datetime(original_row['sign_date']).date() if pd.notna(original_row['sign_date']) else date.today())
                        new_classification = st.selectbox("项目密级", CONTRACT_CLASSIFICATIONS,
                                                           index=CONTRACT_CLASSIFICATIONS.index(original_row['classification']) if original_row['classification'] in CONTRACT_CLASSIFICATIONS else 0)
                        new_is_audit = st.checkbox("是否审价", value=bool(original_row['is_audit']))
                        new_pending_acceptance = st.number_input("待验收金额(万元)", min_value=0.0, step=1.0, format="%.2f", value=original_row['pending_acceptance_amount']/10000) * 10000
                        new_cost = st.number_input("成本(万元)", min_value=0.0, step=1.0, format="%.2f", value=original_row['cost']/10000) * 10000
                        new_gross = st.number_input("毛利(万元)", min_value=0.0, step=1.0, format="%.2f", value=original_row['gross_profit']/10000) * 10000
                        new_accept_date = st.date_input("合同验收日期", value=original_row['acceptance_date'] if pd.notna(original_row['acceptance_date']) else None)
                        new_exp_income_date = st.date_input("预计形成收入日期", value=pd.to_datetime(original_row['expected_income_date']).date() if pd.notna(original_row['expected_income_date']) else None)
                        new_exp_income_year = st.number_input("预计本年收入金额(万元)", min_value=0.0, step=1.0, format="%.2f", value=original_row['expected_income_year']/10000) * 10000
                        new_business_type = st.selectbox("业态", BUSINESS_TYPES,
                                                          index=BUSINESS_TYPES.index(original_row['business_type']) if original_row['business_type'] in BUSINESS_TYPES else 0)
                        new_status = st.text_input("执行状态", value=original_row['status'])

                        if is_boss:
                            all_users = query_df("SELECT username, name FROM users ORDER BY name")
                            user_options = {f"{u['name']} ({u['username']})": u['username'] for _, u in all_users.iterrows()}
                            current_owner_label = next((label for label, un in user_options.items() if un == original_row['owner_id']), None)
                            if current_owner_label is None:
                                current_owner_label = f"{original_row['owner_id']} - {original_row['owner_id']}"
                            selected_owner_label = st.selectbox("负责人", list(user_options.keys()),
                                                               index=list(user_options.keys()).index(current_owner_label) if current_owner_label in user_options else 0)
                            new_owner = user_options[selected_owner_label]
                        else:
                            new_owner = original_row['owner_id']

                        if st.form_submit_button("保存修改"):
                            sql_update = """
                                UPDATE contracts SET
                                    contract_name=?, contract_no=?, party_a=?, project_order_no=?, total_amt=?, sign_date=?,
                                    classification=?, is_audit=?, pending_acceptance_amount=?,
                                    cost=?, gross_profit=?, acceptance_date=?, expected_income_date=?,
                                    expected_income_year=?, business_type=?, status=?, owner_id=?
                                WHERE id=?
                            """
                            params = (new_contract_name, new_contract_no, new_party_a, new_project_order, new_total, new_sign_date,
                                      new_classification, 1 if new_is_audit else 0, new_pending_acceptance,
                                      new_cost, new_gross, new_accept_date, new_exp_income_date,
                                      new_exp_income_year, new_business_type, new_status, new_owner, selected_id)
                            try:
                                execute_sql(sql_update, params)
                                st.success("合同更新成功")
                                clear_user_cache()
                                load_contracts_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"更新失败: {e}")
        
        with col3:
            if can_edit:
                with st.popover("🗑️ 删除"):
                    st.warning("确定删除此合同？此操作不可逆。")
                    if st.button("确认删除", key=f"del_contract_{selected_id}", type="primary"):
                        try:
                            execute_sql("DELETE FROM contracts WHERE id=?", (selected_id,))
                            st.success("合同已删除")
                            clear_user_cache()
                            load_contracts_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"删除失败: {e}")
        
        with col4:
            # 查看回款摘要
            with st.popover("💰 回款摘要"):
                payment_df = query_df(
                    "SELECT id, payment_date, amount, note FROM payment_records WHERE contract_id = ? ORDER BY payment_date DESC",
                    (selected_id,)
                )
                if not payment_df.empty:
                    display_df = payment_df.copy()
                    display_df['amount'] = display_df['amount'] / 10000
                    display_df['payment_date'] = pd.to_datetime(display_df['payment_date']).dt.strftime('%Y-%m-%d')
                    st.dataframe(
                        display_df[['payment_date', 'amount', 'note']],
                        column_config={
                            "payment_date": "回款日期",
                            "amount": st.column_config.NumberColumn("金额(万元)", format="%.2f"),
                            "note": "备注"
                        },
                        use_container_width=True,
                        hide_index=True
                    )
                    total_paid = payment_df['amount'].sum()
                    st.info(f"**累计已回款**：￥{total_paid/10000:,.2f} 万元，共 {len(payment_df)} 笔")
                else:
                    st.info("暂无回款记录，请到「回款管理」添加")
