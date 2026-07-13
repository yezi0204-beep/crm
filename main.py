# main.py

import streamlit as st

# ========== 1. 页面配置（必须是第一个Streamlit命令）==========
st.set_page_config(
    page_title="天地信息网络研究院CRM",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== 2. 导入其他模块（必须在set_page_config之后）==========
from datetime import datetime, timedelta
from database import query_df, execute_sql, init_db
from auth import check_password, hash_password
from utils import get_user_map, clear_user_cache

# ========== 3. 数据库初始化 ==========
init_db()

# ========== 4. 登录状态管理 ==========
if "auth" not in st.session_state:
    auto_token = st.query_params.get("auto_token")
    if auto_token:
        user_row = query_df("SELECT username, name, role FROM users WHERE username = ?", (auto_token,))
        if not user_row.empty:
            st.session_state.update({
                "auth": True,
                "u_id": auto_token,
                "u_info": {
                    "name": user_row.iloc[0]["name"],
                    "role": user_row.iloc[0]["role"]
                }
            })
            st.query_params.clear()
            st.rerun()
        else:
            st.query_params.clear()
            st.rerun()
    else:
        st.markdown("""
        <script>
        (function() {
            let token = localStorage.getItem('crm_token');
            if (token && !window.location.search.includes('auto_token')) {
                const url = new URL(window.location.href);
                url.searchParams.set('auto_token', token);
                window.location.replace(url.toString());
            }
        })();
        </script>
        """, unsafe_allow_html=True)
        st.title("🚀 天地信息网络研究院CRM")
        with st.form("login"):
            u = st.text_input("账号")
            p = st.text_input("密码", type="password")
            if st.form_submit_button("进入系统"):
                user_row = query_df(
                    "SELECT username, password_hash, name, role FROM users WHERE username = ?",
                    (u,)
                )
                if not user_row.empty and check_password(p, user_row.iloc[0]["password_hash"]):
                    pwd_hash = user_row.iloc[0]["password_hash"]
                    if not pwd_hash.startswith('$2b$'):
                        new_hash = hash_password(p)
                        execute_sql("UPDATE users SET password_hash = ? WHERE username = ?", (new_hash, u))
                        st.info("您的密码已升级为更安全的加密方式。")
                    st.session_state.update({
                        "auth": True,
                        "u_id": u,
                        "u_info": {
                            "name": user_row.iloc[0]["name"],
                            "role": user_row.iloc[0]["role"]
                        }
                    })
                    st.markdown(
                        f"<script>localStorage.setItem('crm_token', '{u}');</script>",
                        unsafe_allow_html=True
                    )
                    st.rerun()
                else:
                    st.error("账号或密码错误")
        st.stop()

# ========== 5. 获取当前用户信息 ==========
uid = st.session_state["u_id"]
user_name = st.session_state.u_info["name"]
user_role = st.session_state.u_info["role"]
is_boss = (user_role == "主任" or user_role == "院长")
is_dean = (user_role == "院长")
is_admin = is_boss or is_dean

user_roles_df = query_df("SELECT role FROM user_roles WHERE username = ?", (uid,))
user_roles = user_roles_df['role'].tolist() if not user_roles_df.empty else [user_role]
st.session_state.user_roles = user_roles

user_map = get_user_map()
if "user_map" not in st.session_state:
    st.session_state.user_map = user_map

# ========== 6. 侧边栏导航 ==========
st.sidebar.markdown(f"👋 {user_name} ({', '.join(user_roles)})")

menu_items = []
if '主任' in user_roles or '院长' in user_roles:
    menu_items.extend(["📊 驾驶舱", "👥 客户管理", "🎯 商机看板", "📜 合同管理", "💰 回款管理", "🌊 公海池", "📈 全周期日志", "📁 数据导出"])
if '销售' in user_roles or '售前' in user_roles or '项目经理' in user_roles:
    if "📊 驾驶舱" not in menu_items:
        menu_items.append("📊 驾驶舱")
    if "👥 客户管理" not in menu_items:
        menu_items.append("👥 客户管理")
    if "🎯 商机看板" not in menu_items:
        menu_items.append("🎯 商机看板")
    if "📜 合同管理" not in menu_items:
        menu_items.append("📜 合同管理")
    if "💰 回款管理" not in menu_items:
        menu_items.append("💰 回款管理")
    if "🌊 公海池" not in menu_items:
        menu_items.append("🌊 公海池")
    if "📈 全周期日志" not in menu_items:
        menu_items.append("📈 全周期日志")
    if "📁 数据导出" not in menu_items:
        menu_items.append("📁 数据导出")
if '技术研发' in user_roles:
    menu_items = ["⏱️ 工时管理"]
if '主任' in user_roles or '院长' in user_roles or '项目经理' in user_roles:
    if "⏱️ 工时管理" not in menu_items:
        menu_items.append("⏱️ 工时管理")
if '项目经理' in user_roles:
    menu_items.append("👥 项目分配")
if '主任' in user_roles:
    menu_items.append("👥 用户管理")
if any(r in user_roles for r in ['主任', '院长', '销售', '售前', '项目经理']):
    if "🔍 全局搜索" not in menu_items:
        menu_items.append("🔍 全局搜索")

if '主任' in user_roles or '院长' in user_roles or '销售' in user_roles or '售前' in user_roles or '项目经理' in user_roles:
    menu_items.append("💰 付款计划")
    menu_items.append("📊 项目成本")

if '采购' in user_roles:
    if "📊 采购视图" not in menu_items:
        menu_items.append("📊 采购视图")

menu_items = list(dict.fromkeys(menu_items))
menu = st.sidebar.radio("核心导航", menu_items)

with st.sidebar.expander("🔐 安全设置"):
    with st.form("change_pwd"):
        old_pwd = st.text_input("当前密码", type="password")
        new_pwd = st.text_input("新密码", type="password")
        confirm_pwd = st.text_input("确认新密码", type="password")
        if st.form_submit_button("修改密码"):
            user_row = query_df("SELECT password_hash FROM users WHERE username = ?", (uid,))
            if user_row.empty:
                st.error("用户不存在")
            elif not check_password(old_pwd, user_row.iloc[0]["password_hash"]):
                st.error("当前密码错误")
            elif new_pwd != confirm_pwd:
                st.error("两次输入的新密码不一致")
            elif len(new_pwd) < 3:
                st.error("密码至少3位")
            else:
                new_hash = hash_password(new_pwd)
                execute_sql("UPDATE users SET password_hash = ? WHERE username = ?", (new_hash, uid))
                st.success("密码修改成功")
                clear_user_cache()
                st.cache_data.clear()

if st.sidebar.button("安全退出"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.markdown("<script>sessionStorage.removeItem('crm_username');</script>", unsafe_allow_html=True)
    st.rerun()

# ========== 7. 路由到对应模块（延迟导入，确保在set_page_config之后）==========
def route_to_module(menu, uid, is_boss):
    if menu == "📊 驾驶舱":
        from dashboard import show_dashboard
        show_dashboard(uid, is_boss)
    elif menu == "👥 客户管理":
        from customers import show_customers
        show_customers(uid, is_boss)
    elif menu == "🎯 商机看板":
        from business import show_business
        show_business(uid, is_boss)
    elif menu == "📜 合同管理":
        from contracts import show_contracts
        show_contracts(uid, is_boss)
    elif menu == "💰 回款管理":
        from payments import show_payments
        show_payments(uid, is_boss)
    elif menu == "🌊 公海池":
        from highseas import show_highseas
        show_highseas(uid)
    elif menu == "📈 全周期日志":
        from timeline import show_timeline
        show_timeline(uid, is_boss)
    elif menu == "📁 数据导出":
        from export import show_export
        show_export(uid, is_boss)
    elif menu == "⏱️ 工时管理":
        from time_management import show_time_management
        show_time_management(uid, is_boss)
    elif menu == "👥 项目分配":
        from project_assignment import show_project_assignment
        show_project_assignment(uid)
    elif menu == "👥 用户管理":
        from users import show_users
        show_users()
    elif menu == "🔍 全局搜索":
        from search import show_search
        show_search(uid, is_boss)
    elif menu == "💰 付款计划":
        from payment_plan import show_payment_plans
        show_payment_plans(uid, is_boss)
    elif menu == "📊 项目成本":
        from project_cost import show_project_costs
        show_project_costs(uid, is_boss)
    elif menu == "📊 采购视图":
        from purchase_view import show_purchase_view
        show_purchase_view(uid)
    else:
        st.error("页面不存在")

route_to_module(menu, uid, is_boss)