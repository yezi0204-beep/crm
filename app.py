# app.py

import streamlit as st
from datetime import datetime, timedelta
from database import query_df, execute_sql, init_db
from auth import check_password, hash_password
from utils import get_user_map, clear_user_cache

# ========== 1. 页面配置 ==========
st.set_page_config(
    page_title="天地信息网络研究院CRM",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== 2. 数据库初始化 ==========
init_db()

# ========== 3. 登录状态管理 ==========
if "auth" not in st.session_state:
    # --- 1. 尝试从 LocalStorage 获取自动登录令牌 ---
    # 使用 st.query_params 辅助，但实际令牌存储在浏览器
    auto_token = st.query_params.get("auto_token")
    if auto_token:
        # 验证令牌（这里简化：令牌是用户名，生产环境应加密）
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
            # 清除URL参数，避免分享泄露
            st.query_params.clear()
            st.rerun()
        else:
            st.query_params.clear()
            st.rerun()
    else:
        # --- 2. 前端脚本：从 LocalStorage 读取并重定向 ---
        st.markdown("""
        <script>
        (function() {
            let token = localStorage.getItem('crm_token');
            if (token && !window.location.search.includes('auto_token')) {
                // 使用 replace 避免历史记录混乱
                const url = new URL(window.location.href);
                url.searchParams.set('auto_token', token);
                window.location.replace(url.toString());
            }
        })();
        </script>
        """, unsafe_allow_html=True)
        # 显示登录表单
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
                    # 存储到 localStorage
                    st.markdown(
                        f"<script>localStorage.setItem('crm_token', '{u}');</script>",
                        unsafe_allow_html=True
                    )
                    st.rerun()
                else:
                    st.error("账号或密码错误")
        st.stop()

# ========== 4. 获取当前用户信息 ==========
uid = st.session_state["u_id"]
user_name = st.session_state.u_info["name"]
user_role = st.session_state.u_info["role"]
is_boss = (user_role == "主任" or user_role == "院长")   # 院长也有全部数据权限
is_dean = (user_role == "院长")
is_admin = is_boss or is_dean

# 获取用户的所有角色
user_roles_df = query_df("SELECT role FROM user_roles WHERE username = ?", (uid,))
user_roles = user_roles_df['role'].tolist() if not user_roles_df.empty else [user_role]
st.session_state.user_roles = user_roles

# 获取用户映射
user_map = get_user_map()
if "user_map" not in st.session_state:
    st.session_state.user_map = user_map

# ========== 5. 侧边栏导航 ==========
st.sidebar.markdown(f"👋 {user_name} ({', '.join(user_roles)})")

menu_items = []
# 核心业务：主任或院长可见全部
if '主任' in user_roles or '院长' in user_roles:
    menu_items.extend(["📊 驾驶舱", "👥 客户管理", "🎯 商机看板", "📜 合同回款", "🌊 公海池", "📈 全周期日志", "📁 数据导出"])
# 其他角色（销售/售前/项目经理）添加相应菜单
if '销售' in user_roles or '售前' in user_roles or '项目经理' in user_roles:
    if "📊 驾驶舱" not in menu_items:
        menu_items.append("📊 驾驶舱")
    if "👥 客户管理" not in menu_items:
        menu_items.append("👥 客户管理")
    if "🎯 商机看板" not in menu_items:
        menu_items.append("🎯 商机看板")
    if "📜 合同回款" not in menu_items:
        menu_items.append("📜 合同回款")
    if "🌊 公海池" not in menu_items:
        menu_items.append("🌊 公海池")
    if "📈 全周期日志" not in menu_items:
        menu_items.append("📈 全周期日志")
    if "📁 数据导出" not in menu_items:
        menu_items.append("📁 数据导出")
# 技术研发：只看到工时管理
if '技术研发' in user_roles:
    menu_items = ["⏱️ 工时管理"]
# 工时管理：主任、院长、项目经理可见
if '主任' in user_roles or '院长' in user_roles or '项目经理' in user_roles:
    if "⏱️ 工时管理" not in menu_items:
        menu_items.append("⏱️ 工时管理")
# 项目分配：仅项目经理可见（也可根据需要开放给主任/院长，此处保持仅项目经理）
if '项目经理' in user_roles:
    menu_items.append("👥 项目分配")
# 用户管理：仅主任可见
if '主任' in user_roles:
    menu_items.append("👥 用户管理")
# 全局搜索：主任、院长、销售、售前、项目经理可见
if any(r in user_roles for r in ['主任', '院长', '销售', '售前', '项目经理']):
    if "🔍 全局搜索" not in menu_items:
        menu_items.append("🔍 全局搜索")

if '主任' in user_roles or '院长' in user_roles or '销售' in user_roles or '售前' in user_roles or '项目经理' in user_roles:
    menu_items.append("💰 付款计划")
    menu_items.append("📊 项目成本")

if '采购' in user_roles:
    if "📊 采购视图" not in menu_items:
        menu_items.append("📊 采购视图")

# 去重并保持顺序
menu_items = list(dict.fromkeys(menu_items))
menu = st.sidebar.radio("核心导航", menu_items)

# 修改密码
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

# 退出登录
if st.sidebar.button("安全退出"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.markdown("<script>sessionStorage.removeItem('crm_username');</script>", unsafe_allow_html=True)
    st.rerun()

# ========== 6. 路由到对应模块 ==========
if menu == "📊 驾驶舱":
    from dashboard import show_dashboard
    show_dashboard(uid, is_boss)
elif menu == "👥 客户管理":
    from customers import show_customers
    show_customers(uid, is_boss)
elif menu == "🎯 商机看板":
    from business import show_business
    show_business(uid, is_boss)
elif menu == "📜 合同回款":
    from contracts import show_contracts
    show_contracts(uid, is_boss)
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