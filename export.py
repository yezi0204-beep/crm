# export.py

import streamlit as st
import pandas as pd
import io
from datetime import datetime
from database import query_df
from utils import clear_user_cache

def show_export(uid: str, is_boss: bool):
    """数据导出模块"""
    st.title("📁 一键导出报表")
    st.markdown("选择要导出的数据范围，支持 Excel 格式。")

    # 导出类型选择
    export_type = st.radio(
        "导出内容",
        ["客户数据", "商机数据", "合同数据", "所有数据"],
        horizontal=True
    )

    # 生成导出文件按钮
    if st.button("生成导出文件"):
        # 确保获取最新数据
        clear_user_cache()
        st.cache_data.clear()

        # 准备内存文件
        output = io.BytesIO()
        try:
            # 创建 Excel 写入器
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # 根据选择导出不同工作表
                if export_type == "所有数据" or export_type == "客户数据":
                    df_cust = _load_customers(uid, is_boss)
                    if not df_cust.empty:
                        df_cust.to_excel(writer, sheet_name='客户', index=False)
                        st.info(f"客户数据已导出 {len(df_cust)} 条")
                    else:
                        st.warning("客户数据为空")

                if export_type == "所有数据" or export_type == "商机数据":
                    df_biz = _load_business(uid, is_boss)
                    if not df_biz.empty:
                        df_biz.to_excel(writer, sheet_name='商机', index=False)
                        st.info(f"商机数据已导出 {len(df_biz)} 条")
                    else:
                        st.warning("商机数据为空")

                if export_type == "所有数据" or export_type == "合同数据":
                    df_contract = _load_contracts(uid, is_boss)
                    if not df_contract.empty:
                        df_contract.to_excel(writer, sheet_name='合同', index=False)
                        st.info(f"合同数据已导出 {len(df_contract)} 条")
                    else:
                        st.warning("合同数据为空")

            # 准备下载
            output.seek(0)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"天地信息网络研究院CRM_{timestamp}.xlsx"
            st.download_button(
                label="📥 下载 Excel 文件",
                data=output,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        except ImportError:
            st.error("导出需要安装 openpyxl，请执行：pip install openpyxl")
        except Exception as e:
            st.error(f"导出失败: {e}")


# ---------- 辅助函数：按权限加载数据 ----------
def _load_customers(uid: str, is_boss: bool) -> pd.DataFrame:
    """加载客户数据（根据权限）"""
    if is_boss:
        df = query_df("SELECT * FROM customers")
    else:
        df = query_df("SELECT * FROM customers WHERE owner_id = ?", (uid,))
    return df

def _load_business(uid: str, is_boss: bool) -> pd.DataFrame:
    """加载商机数据（根据权限）"""
    if is_boss:
        df = query_df("SELECT * FROM business")
    else:
        df = query_df("SELECT * FROM business WHERE owner_id = ?", (uid,))
    return df

def _load_contracts(uid: str, is_boss: bool) -> pd.DataFrame:
    """加载合同数据（根据权限）"""
    if is_boss:
        df = query_df("SELECT * FROM contracts")
    else:
        df = query_df("SELECT * FROM contracts WHERE owner_id = ?", (uid,))
    return df