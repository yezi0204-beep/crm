# contracts.py

import streamlit as st
import pandas as pd
from datetime import datetime, date
from database import query_df, execute_sql, get_db_connection
from utils import get_user_map, clear_user_cache
from config import CONTRACT_CLASSIFICATIONS, BUSINESS_TYPES

def show_contracts(uid: str, is_boss: bool):
    """合同回款管理模块（含商机成本迁移）"""
    st.title("💰 合同与回款管理")

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
                                    (b_id, contract_no, total_amt, paid_amt, sign_date, owner_id, status,
                                     contract_name, classification, is_audit, pending_acceptance_amount,
                                     cost, gross_profit, acceptance_date, expected_income_date,
                                     expected_income_year, business_type, project_order_no, total_cost)
                                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)
                                """
                                params = (b_id, contract_no.strip(), total_amt, 0, sign_date, owner, '执行中',
                                          contract_name.strip(), classification, 1 if is_audit else 0, pending_acceptance,
                                          cost, gross_profit, acceptance_date, expected_income_date,
                                          expected_income_year, business_type, project_order_no)
                                cursor.execute(sql, params)
                                contract_id = cursor.lastrowid

                                # 如果关联了商机，将商机成本迁移到合同
                                if b_id:
                                    # 查询商机下的所有成本（使用统一的 costs 表）
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
                                        st.info(f"已自动迁移商机成本 {total_migrated:,.2f} 元到合同。")
                                conn.commit()
                                st.success("合同录入成功")
                                clear_user_cache()
                                st.cache_data.clear()
                                st.rerun()
                        except Exception as e:
                            st.error(f"保存失败：{e}")

    st.divider()

    # ---------- 加载合同数据 ----------
    if is_boss:
        df_con = query_df("SELECT * FROM contracts ORDER BY sign_date DESC")
    else:
        df_con = query_df("SELECT * FROM contracts WHERE owner_id = ? ORDER BY sign_date DESC", (uid,))

    if df_con.empty:
        st.info("暂无合同数据，请先创建合同")
        return

    # 数值列转换
    numeric_cols = ['total_amt', 'paid_amt', 'pending_acceptance_amount', 'cost', 'gross_profit', 'expected_income_year', 'total_cost']
    for col in numeric_cols:
        if col in df_con.columns:
            df_con[col] = pd.to_numeric(df_con[col], errors='coerce').fillna(0)

    df_con['pending_payment'] = df_con['total_amt'] - df_con['paid_amt']
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
            unaccepted_display = df_unaccepted[['contract_name', 'contract_no', 'total_amt', 'sign_date', 'owner_name']].copy()
            unaccepted_display['total_amt_wan'] = unaccepted_display['total_amt'] / 10000
            st.dataframe(
                unaccepted_display[['contract_name', 'contract_no', 'total_amt_wan', 'sign_date', 'owner_name']],
                column_config={
                    "contract_name": "合同名称",
                    "contract_no": "合同编号",
                    "total_amt_wan": st.column_config.NumberColumn("合同总额(万元)", format="%.2f"),
                    "sign_date": "签约日期",
                    "owner_name": "负责人"
                },
                use_container_width=True,
                hide_index=True
            )
            st.markdown("#### 快速验收")
            for _, row in df_unaccepted.iterrows():
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.write(f"**{row['contract_name']}** ({row['contract_no']})")
                with col2:
                    if st.button("✅ 设为已验收", key=f"quick_accept_{row['id']}"):
                        execute_sql("UPDATE contracts SET acceptance_date = ? WHERE id = ?", (today, row['id']))
                        st.success(f"合同 {row['contract_no']} 已标记为验收（验收日期：{today}）")
                        clear_user_cache()
                        st.cache_data.clear()
                        st.rerun()
                st.divider()
    else:
        st.success("🎉 所有合同均已验收！")

    st.subheader("📋 合同列表")
    show_unaccepted_only = st.checkbox("仅显示未验收合同", value=False)
    if show_unaccepted_only:
        df_con_display = df_con[~df_con['is_accepted']].copy()
    else:
        df_con_display = df_con.copy()

    # 展示列（含总成本）
    display_cols = ['contract_name', 'contract_no', 'project_order_no', 'total_amt', 'paid_amt', 'pending_payment',
                    '验收状态', 'classification', 'business_type', 'sign_date', 'acceptance_date',
                    'expected_income_date', 'expected_income_year', 'cost', 'gross_profit',
                    'is_audit', 'pending_acceptance_amount', 'status', 'owner_name', 'total_cost']
    display_cols = [c for c in display_cols if c in df_con_display.columns]
    df_display = df_con_display[display_cols].copy()

    wan_cols = ['total_amt', 'paid_amt', 'pending_payment', 'pending_acceptance_amount', 'cost', 'gross_profit', 'expected_income_year', 'total_cost']
    for col in wan_cols:
        if col in df_display.columns:
            df_display[col] = df_display[col] / 10000

    column_config = {
        "contract_name": "合同名称",
        "contract_no": "合同编号",
        "project_order_no": "项目令号",
        "total_amt": st.column_config.NumberColumn("合同总额(万元)", format="%.2f"),
        "paid_amt": st.column_config.NumberColumn("已回款(万元)", format="%.2f"),
        "pending_payment": st.column_config.NumberColumn("待回款(万元)", format="%.2f"),
        "验收状态": st.column_config.TextColumn("验收状态"),
        "classification": "密级",
        "business_type": "业态",
        "sign_date": st.column_config.DateColumn("签约日期"),
        "acceptance_date": st.column_config.DateColumn("验收日期"),
        "expected_income_date": st.column_config.DateColumn("预计收入日期"),
        "expected_income_year": st.column_config.NumberColumn("预计本年收入(万元)", format="%.2f"),
        "cost": st.column_config.NumberColumn("成本(万元)", format="%.2f"),
        "gross_profit": st.column_config.NumberColumn("毛利(万元)", format="%.2f"),
        "total_cost": st.column_config.NumberColumn("总成本(万元)", format="%.2f"),
        "is_audit": st.column_config.CheckboxColumn("是否审价"),
        "pending_acceptance_amount": st.column_config.NumberColumn("待验收(万元)", format="%.2f"),
        "status": "状态",
        "owner_name": "负责人"
    }

    st.dataframe(df_display, use_container_width=True, hide_index=True, column_config=column_config)

    # ---------- 合同详情操作 ----------
    st.subheader("✏️ 合同详情操作")
    for _, row in df_con.iterrows():
        can_edit = is_boss or row['owner_id'] == uid
        with st.expander(f"{row['contract_name']}（{row['contract_no']}）"):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**合同总额**：￥{row['total_amt']/10000:,.2f} 万元")
                st.markdown(f"**已回款**：￥{row['paid_amt']/10000:,.2f} 万元")
                st.markdown(f"**待回款**：￥{row['pending_payment']/10000:,.2f} 万元")
                st.markdown(f"**总成本**：￥{row['total_cost']/10000:,.2f} 万元")
                st.markdown(f"**密级**：{row['classification']} | **业态**：{row['business_type']}")
                st.markdown(f"**签约日期**：{row['sign_date']} | **验收日期**：{row['acceptance_date']}")
                st.markdown(f"**预计收入日期**：{row['expected_income_date']} | **预计本年收入**：{row['expected_income_year']/10000:,.2f} 万元")
                st.markdown(f"**成本**：{row['cost']/10000:,.2f} 万元 | **毛利**：{row['gross_profit']/10000:,.2f} 万元")
                st.markdown(f"**待验收金额**：{row['pending_acceptance_amount']/10000:,.2f} 万元 | **是否审价**：{'是' if row['is_audit'] else '否'}")
                st.markdown(f"**状态**：{row['status']} | **负责人**：{row['owner_name']}")

            with col2:
                if can_edit:
                    with st.popover("✏️ 编辑合同"):
                        with st.form(f"edit_contract_{row['id']}"):
                            new_contract_name = st.text_input("合同名称", value=row['contract_name'])
                            new_contract_no = st.text_input("合同编号", value=row['contract_no'])
                            new_project_order = st.text_input("项目令号", value=row['project_order_no'] if pd.notna(row['project_order_no']) else "")
                            new_total = st.number_input("合同总额(万元)", min_value=0.0, step=1.0, format="%.2f", value=row['total_amt']/10000) * 10000
                            new_sign_date = st.date_input("签约日期", value=pd.to_datetime(row['sign_date']).date() if pd.notna(row['sign_date']) else date.today())
                            new_classification = st.selectbox("项目密级", CONTRACT_CLASSIFICATIONS,
                                                               index=CONTRACT_CLASSIFICATIONS.index(row['classification']) if row['classification'] in CONTRACT_CLASSIFICATIONS else 0)
                            new_is_audit = st.checkbox("是否审价", value=bool(row['is_audit']))
                            new_pending_accept = st.number_input("待验收金额(万元)", min_value=0.0, step=1.0, format="%.2f", value=row['pending_acceptance_amount']/10000) * 10000
                            new_cost = st.number_input("成本(万元)", min_value=0.0, step=1.0, format="%.2f", value=row['cost']/10000) * 10000
                            new_gross = st.number_input("毛利(万元)", min_value=0.0, step=1.0, format="%.2f", value=row['gross_profit']/10000) * 10000
                            new_accept_date = st.date_input("合同验收日期", value=row['acceptance_date'] if pd.notna(row['acceptance_date']) else None)
                            new_exp_income_date = st.date_input("预计形成收入日期", value=pd.to_datetime(row['expected_income_date']).date() if pd.notna(row['expected_income_date']) else None)
                            new_exp_income_year = st.number_input("预计本年收入金额(万元)", min_value=0.0, step=1.0, format="%.2f", value=row['expected_income_year']/10000) * 10000
                            new_business_type = st.selectbox("业态", BUSINESS_TYPES,
                                                              index=BUSINESS_TYPES.index(row['business_type']) if row['business_type'] in BUSINESS_TYPES else 0)
                            new_status = st.text_input("执行状态", value=row['status'])

                            if is_boss:
                                all_users = query_df("SELECT username, name FROM users ORDER BY name")
                                user_options = {f"{u['name']} ({u['username']})": u['username'] for _, u in all_users.iterrows()}
                                current_owner_label = next((label for label, un in user_options.items() if un == row['owner_id']), None)
                                if current_owner_label is None:
                                    current_owner_label = f"{row['owner_id']} - {row['owner_id']}"
                                selected_owner_label = st.selectbox("负责人", list(user_options.keys()),
                                                                    index=list(user_options.keys()).index(current_owner_label) if current_owner_label in user_options else 0)
                                new_owner = user_options[selected_owner_label]
                            else:
                                new_owner = row['owner_id']

                            if st.form_submit_button("保存修改"):
                                sql_update = """
                                    UPDATE contracts SET
                                        contract_name=?, contract_no=?, project_order_no=?, total_amt=?, sign_date=?,
                                        classification=?, is_audit=?, pending_acceptance_amount=?,
                                        cost=?, gross_profit=?, acceptance_date=?, expected_income_date=?,
                                        expected_income_year=?, business_type=?, status=?, owner_id=?
                                    WHERE id=?
                                """
                                params = (new_contract_name, new_contract_no, new_project_order, new_total, new_sign_date,
                                          new_classification, 1 if new_is_audit else 0, new_pending_accept,
                                          new_cost, new_gross, new_accept_date, new_exp_income_date,
                                          new_exp_income_year, new_business_type, new_status, new_owner, row['id'])
                                try:
                                    execute_sql(sql_update, params)
                                    st.success("合同更新成功")
                                    clear_user_cache()
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"更新失败: {e}")

                    with st.popover("🗑️ 删除"):
                        st.warning("确定删除此合同？此操作不可逆。")
                        if st.button("确认删除", key=f"del_contract_{row['id']}"):
                            try:
                                execute_sql("DELETE FROM contracts WHERE id=?", (row['id'],))
                                st.success("合同已删除")
                                clear_user_cache()
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"删除失败: {e}")

            # ---------- 回款明细 ----------
            st.divider()
            st.markdown("#### 💰 回款明细")
            payment_df = query_df(
                "SELECT id, payment_date, amount, note FROM payment_records WHERE contract_id = ? ORDER BY payment_date DESC",
                (row['id'],)
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
                for _, pay_row in payment_df.iterrows():
                    cols = st.columns([2, 2, 4, 1, 1])
                    with cols[0]:
                        st.write(pd.to_datetime(pay_row['payment_date']).strftime('%Y-%m-%d'))
                    with cols[1]:
                        st.write(f"￥{pay_row['amount']/10000:,.2f} 万元")
                    with cols[2]:
                        st.write(pay_row['note'] if pay_row['note'] else "")
                    with cols[3]:
                        if can_edit:
                            with st.popover(f"✏️ 编辑 {pay_row['id']}"):
                                with st.form(f"edit_payment_{pay_row['id']}"):
                                    new_date = st.date_input("回款日期", value=pd.to_datetime(pay_row['payment_date']).date())
                                    new_amount = st.number_input("金额（万元）", min_value=0.0, step=0.01, format="%.2f", value=pay_row['amount']/10000) * 10000
                                    new_note = st.text_input("备注", value=pay_row['note'] if pay_row['note'] else "")
                                    if st.form_submit_button("保存"):
                                        delta = new_amount - pay_row['amount']
                                        try:
                                            execute_sql("UPDATE contracts SET paid_amt = paid_amt + ? WHERE id = ?", (delta, row['id']))
                                            execute_sql("UPDATE payment_records SET payment_date=?, amount=?, note=? WHERE id=?",
                                                        (new_date, new_amount, new_note, pay_row['id']))
                                            st.success("更新成功")
                                            clear_user_cache()
                                            st.cache_data.clear()
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"更新失败: {e}")
                    with cols[4]:
                        if can_edit:
                            with st.popover(f"🗑️ 删除 {pay_row['id']}"):
                                st.warning("确定删除此回款记录？")
                                if st.button("确认删除", key=f"del_payment_{pay_row['id']}"):
                                    try:
                                        execute_sql("UPDATE contracts SET paid_amt = paid_amt - ? WHERE id = ?", (pay_row['amount'], row['id']))
                                        execute_sql("DELETE FROM payment_records WHERE id = ?", (pay_row['id'],))
                                        st.success("删除成功")
                                        clear_user_cache()
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"删除失败: {e}")
            else:
                st.info("暂无回款记录")

            if can_edit:
                with st.form(key=f"new_payment_{row['id']}"):
                    st.markdown("**新增回款**")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        pay_date = st.date_input("回款日期", value=date.today())
                    with col2:
                        pay_amount = st.number_input("金额（万元）", min_value=0.0, step=0.01, format="%.2f") * 10000
                    with col3:
                        pay_note = st.text_input("备注")
                    if st.form_submit_button("添加回款"):
                        if pay_amount > 0:
                            try:
                                execute_sql(
                                    "INSERT INTO payment_records (contract_id, payment_date, amount, note) VALUES (?, ?, ?, ?)",
                                    (row['id'], pay_date, pay_amount, pay_note)
                                )
                                execute_sql("UPDATE contracts SET paid_amt = paid_amt + ? WHERE id = ?", (pay_amount, row['id']))
                                st.success("回款添加成功")
                                clear_user_cache()
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"添加失败: {e}")
                        else:
                            st.error("金额必须大于0")