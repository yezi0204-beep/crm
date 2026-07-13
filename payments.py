# payments.py - 回款管理模块（独立）

import streamlit as st
import pandas as pd
from datetime import datetime, date
from database import query_df, execute_sql
from utils import get_user_map, clear_user_cache


def load_payments_data(uid: str, is_boss: bool):
    """加载回款数据（带缓存）"""
    if is_boss:
        sql = """
            SELECT pr.id, pr.contract_id, pr.payment_date, pr.amount, pr.note, pr.created_at,
                   c.contract_name, c.contract_no, c.party_a, c.owner_id,
                   c.total_amt, c.paid_amt
            FROM payment_records pr
            JOIN contracts c ON pr.contract_id = c.id
            ORDER BY pr.payment_date DESC
        """
        df = query_df(sql)
    else:
        sql = """
            SELECT pr.id, pr.contract_id, pr.payment_date, pr.amount, pr.note, pr.created_at,
                   c.contract_name, c.contract_no, c.party_a, c.owner_id,
                   c.total_amt, c.paid_amt
            FROM payment_records pr
            JOIN contracts c ON pr.contract_id = c.id
            WHERE c.owner_id = ?
            ORDER BY pr.payment_date DESC
        """
        df = query_df(sql, (uid,))
    return df


def load_contracts_list(uid: str, is_boss: bool):
    """加载合同列表用于选择（带缓存）"""
    if is_boss:
        df = query_df("SELECT id, contract_name, contract_no, party_a, owner_id FROM contracts ORDER BY contract_name")
    else:
        df = query_df("SELECT id, contract_name, contract_no, party_a, owner_id FROM contracts WHERE owner_id = ? ORDER BY contract_name", (uid,))
    return df


def show_payments(uid: str, is_boss: bool):
    """回款管理模块（独立）"""
    st.title("💰 回款管理")

    user_map = get_user_map()

    # ---------- 新增回款 ----------
    with st.expander("➕ 新增回款记录", expanded=False):
        with st.form("new_payment"):
            contract_list = load_contracts_list(uid, is_boss)
            if contract_list.empty:
                st.warning("暂无合同数据，请先创建合同")
            else:
                contract_choices = {f"{row['id']} - {row['contract_name']} ({row['contract_no']})": row['id'] for _, row in contract_list.iterrows()}
                selected_contract = st.selectbox("选择合同 *", list(contract_choices.keys()))
                contract_id = contract_choices[selected_contract]

                col1, col2 = st.columns(2)
                with col1:
                    pay_date = st.date_input("回款日期 *", value=date.today())
                with col2:
                    pay_amount = st.number_input("回款金额（万元）*", min_value=0.0, step=0.01, format="%.2f") * 10000

                pay_note = st.text_input("备注")

                if st.form_submit_button("保存回款", type="primary"):
                    if pay_amount <= 0:
                        st.error("回款金额必须大于0")
                    else:
                        try:
                            execute_sql(
                                "INSERT INTO payment_records (contract_id, payment_date, amount, note) VALUES (?, ?, ?, ?)",
                                (contract_id, pay_date, pay_amount, pay_note)
                            )
                            execute_sql("UPDATE contracts SET paid_amt = paid_amt + ? WHERE id = ?", (pay_amount, contract_id))
                            st.success("回款记录添加成功")
                            clear_user_cache()
                            st.rerun()
                        except Exception as e:
                            st.error(f"添加失败: {e}")

    st.divider()

    # ---------- 筛选与搜索 ----------
    st.subheader("🔍 筛选条件")
    col1, col2, col3 = st.columns(3)
    with col1:
        search_term = st.text_input("搜索（合同名称/编号/甲方）", placeholder="输入关键词...")
    with col2:
        date_filter = st.selectbox("时间范围", ["全部", "本年", "本月", "本季度", "自定义"])
    with col3:
        sort_order = st.selectbox("排序方式", ["回款日期（从新到旧）", "回款日期（从旧到新）", "金额（从大到小）", "金额（从小到大）"])

    # 自定义日期范围
    start_date = None
    end_date = None
    if date_filter == "自定义":
        col4, col5 = st.columns(2)
        with col4:
            start_date = st.date_input("开始日期", value=None)
        with col5:
            end_date = st.date_input("结束日期", value=None)

    # ---------- 加载并处理数据 ----------
    df_pay = load_payments_data(uid, is_boss)

    if df_pay.empty:
        st.info("暂无回款记录")
        return

    # 数据处理
    df_pay['payment_date'] = pd.to_datetime(df_pay['payment_date']).dt.date
    df_pay['owner_name'] = df_pay['owner_id'].map(user_map).fillna(df_pay['owner_id'])
    df_pay['amount_wan'] = df_pay['amount'] / 10000
    df_pay['pending_payment'] = ((df_pay['total_amt'] - df_pay['paid_amt']).clip(lower=0)) / 10000

    # 筛选逻辑
    df_filtered = df_pay.copy()

    # 搜索筛选
    if search_term:
        search_term = search_term.lower()
        mask = (
            df_filtered['contract_name'].str.lower().str.contains(search_term, na=False) |
            df_filtered['contract_no'].str.lower().str.contains(search_term, na=False) |
            df_filtered['party_a'].str.lower().str.contains(search_term, na=False)
        )
        df_filtered = df_filtered[mask]

    # 时间筛选
    today = date.today()
    if date_filter == "本年":
        year_start = date(today.year, 1, 1)
        df_filtered = df_filtered[df_filtered['payment_date'] >= year_start]
    elif date_filter == "本月":
        month_start = date(today.year, today.month, 1)
        df_filtered = df_filtered[df_filtered['payment_date'] >= month_start]
    elif date_filter == "本季度":
        quarter = (today.month - 1) // 3
        quarter_start = date(today.year, quarter * 3 + 1, 1)
        df_filtered = df_filtered[df_filtered['payment_date'] >= quarter_start]
    elif date_filter == "自定义" and start_date and end_date:
        df_filtered = df_filtered[(df_filtered['payment_date'] >= start_date) & (df_filtered['payment_date'] <= end_date)]

    # 排序
    if sort_order == "回款日期（从新到旧）":
        df_filtered = df_filtered.sort_values('payment_date', ascending=False)
    elif sort_order == "回款日期（从旧到新）":
        df_filtered = df_filtered.sort_values('payment_date', ascending=True)
    elif sort_order == "金额（从大到小）":
        df_filtered = df_filtered.sort_values('amount', ascending=False)
    elif sort_order == "金额（从小到大）":
        df_filtered = df_filtered.sort_values('amount', ascending=True)

    # ---------- 统计概览 ----------
    total_amount = df_filtered['amount'].sum()
    total_count = len(df_filtered)
    avg_amount = df_filtered['amount'].mean() if total_count > 0 else 0

    stat_col1, stat_col2, stat_col3 = st.columns(3)
    with stat_col1:
        st.metric("总回款金额", f"￥{total_amount/10000:,.2f} 万元")
    with stat_col2:
        st.metric("回款笔数", f"{total_count} 笔")
    with stat_col3:
        st.metric("平均每笔回款", f"￥{avg_amount/10000:,.2f} 万元")

    st.divider()

    # ---------- 回款列表展示 ----------
    st.subheader(f"📋 回款记录列表（共 {total_count} 条）")

    if df_filtered.empty:
        st.info("没有符合条件的回款记录")
        return

    display_cols = [
        'payment_date', 'contract_name', 'contract_no', 'party_a',
        'amount_wan', 'pending_payment', 'note', 'owner_name'
    ]

    column_config = {
        "payment_date": st.column_config.DateColumn("回款日期", format="YYYY-MM-DD"),
        "contract_name": "合同名称",
        "contract_no": "合同编号",
        "party_a": "甲方",
        "amount_wan": st.column_config.NumberColumn("回款金额(万元)", format="%.2f"),
        "pending_payment": st.column_config.NumberColumn("待回款(万元)", format="%.2f"),
        "note": "备注",
        "owner_name": "负责人"
    }

    st.dataframe(
        df_filtered[display_cols],
        use_container_width=True,
        hide_index=True,
        column_config=column_config
    )

    st.divider()

    # ---------- 回款详情与编辑 ----------
    st.subheader("✏️ 回款详情操作")

    for _, row in df_filtered.iterrows():
        can_edit = is_boss or row['owner_id'] == uid
        with st.expander(f"📅 {row['payment_date']} - {row['contract_name']}（￥{row['amount_wan']:,.2f} 万元）"):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**合同名称**：{row['contract_name']}")
                st.markdown(f"**合同编号**：{row['contract_no']}")
                st.markdown(f"**甲方**：{row['party_a'] if row.get('party_a') else '未填写'}")
                st.markdown(f"**回款日期**：{row['payment_date']}")
                st.markdown(f"**回款金额**：￥{row['amount_wan']:,.2f} 万元")
                st.markdown(f"**备注**：{row['note'] if row.get('note') else '无'}")
                st.markdown(f"**负责人**：{row['owner_name']}")

            with col2:
                if can_edit:
                    with st.popover("✏️ 编辑"):
                        with st.form(f"edit_payment_{row['id']}"):
                            contract_list = load_contracts_list(uid, is_boss)
                            contract_choices = {f"{r['id']} - {r['contract_name']} ({r['contract_no']})": r['id'] for _, r in contract_list.iterrows()}
                            
                            current_contract_label = next((label for label, cid in contract_choices.items() if cid == row['contract_id']), None)
                            if current_contract_label is None:
                                current_contract_label = f"{row['contract_id']} - {row['contract_name']} ({row['contract_no']})"
                            
                            selected_contract = st.selectbox(
                                "选择合同 *",
                                list(contract_choices.keys()),
                                index=list(contract_choices.keys()).index(current_contract_label) if current_contract_label in contract_choices else 0
                            )
                            new_contract_id = contract_choices[selected_contract]
                            
                            new_date = st.date_input("回款日期", value=row['payment_date'])
                            new_amount = st.number_input(
                                "回款金额（万元）",
                                min_value=0.0, step=0.01, format="%.2f",
                                value=row['amount_wan']
                            ) * 10000
                            new_note = st.text_input("备注", value=row['note'] if pd.notna(row['note']) else "")

                            if st.form_submit_button("保存修改"):
                                delta = new_amount - row['amount']
                                contract_changed = new_contract_id != row['contract_id']
                                try:
                                    if contract_changed:
                                        execute_sql(
                                            "UPDATE contracts SET paid_amt = paid_amt - ? WHERE id = ?",
                                            (row['amount'], row['contract_id'])
                                        )
                                        execute_sql(
                                            "UPDATE contracts SET paid_amt = paid_amt + ? WHERE id = ?",
                                            (new_amount, new_contract_id)
                                        )
                                    else:
                                        execute_sql(
                                            "UPDATE contracts SET paid_amt = paid_amt + ? WHERE id = ?",
                                            (delta, row['contract_id'])
                                        )
                                    execute_sql(
                                        "UPDATE payment_records SET contract_id=?, payment_date=?, amount=?, note=? WHERE id=?",
                                        (new_contract_id, new_date, new_amount, new_note, row['id'])
                                    )
                                    st.success("回款记录更新成功")
                                    clear_user_cache()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"更新失败: {e}")

                    with st.popover("🗑️ 删除"):
                        st.warning("确定删除此回款记录？此操作不可逆。")
                        if st.button("确认删除", key=f"del_payment_{row['id']}", type="primary"):
                            try:
                                execute_sql(
                                    "UPDATE contracts SET paid_amt = paid_amt - ? WHERE id = ?",
                                    (row['amount'], row['contract_id'])
                                )
                                execute_sql("DELETE FROM payment_records WHERE id = ?", (row['id'],))
                                st.success("回款记录已删除")
                                clear_user_cache()
                                st.rerun()
                            except Exception as e:
                                st.error(f"删除失败: {e}")
