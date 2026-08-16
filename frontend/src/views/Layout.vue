<template>
  <div class="layout-container">
    <aside class="sidebar">
      <div class="sidebar-header">
        <div class="logo-wrapper">
          <div class="logo">🚀</div>
        </div>
        <div class="title-section">
          <span class="title">CRM系统</span>
          <span class="subtitle">天地信息网络研究院</span>
        </div>
      </div>
      
      <div class="user-info">
        <div class="avatar-wrapper">
          <div class="avatar">👤</div>
          <div class="status-indicator online"></div>
        </div>
        <div class="user-detail">
          <div class="user-name">{{ authStore.name }}</div>
          <div class="user-role">{{ authStore.role }}</div>
        </div>
      </div>
      
      <el-menu 
        :default-active="activeMenu"
        class="sidebar-menu"
        background-color="transparent"
        text-color="#a0aec0"
        active-text-color="#4ecdc4"
        router
        :collapse="isCollapsed"
        @collapse="handleCollapse"
      >
        <div class="menu-group">
          <div class="menu-group-title">📊 销售管理</div>
          <el-menu-item index="/dashboard">
            <span class="menu-icon">📊</span>
            <span>驾驶舱</span>
          </el-menu-item>
          <el-menu-item index="/reports">
            <span class="menu-icon">📈</span>
            <span>业绩报表</span>
          </el-menu-item>
          <el-menu-item index="/customers">
            <span class="menu-icon">👥</span>
            <span>客户管理</span>
          </el-menu-item>
          <el-menu-item index="/business">
            <span class="menu-icon">🎯</span>
            <span>商机看板</span>
          </el-menu-item>
          <el-menu-item index="/contracts">
            <span class="menu-icon">📜</span>
            <span>合同管理</span>
          </el-menu-item>
          <el-menu-item index="/quotes">
            <span class="menu-icon">💵</span>
            <span>报价管理</span>
          </el-menu-item>
          <el-menu-item index="/products">
            <span class="menu-icon">📦</span>
            <span>产品库存</span>
          </el-menu-item>
          <el-menu-item index="/payments">
            <span class="menu-icon">💰</span>
            <span>回款管理</span>
          </el-menu-item>
          <el-menu-item index="/visits">
            <span class="menu-icon">📅</span>
            <span>拜访排班</span>
          </el-menu-item>
        </div>
        
        <div class="menu-group">
          <div class="menu-group-title">🌊 资源管理</div>
          <el-menu-item index="/pool">
            <span class="menu-icon">🌊</span>
            <span>公海池</span>
          </el-menu-item>
          <el-menu-item index="/leads" v-if="['主任','院长'].includes(authStore.role)">
            <span class="menu-icon">📡</span>
            <span>智能线索</span>
          </el-menu-item>
          <el-menu-item index="/enterprises">
            <span class="menu-icon">🏢</span>
            <span>企业信息库</span>
          </el-menu-item>
        </div>
        
        <div class="menu-group">
          <div class="menu-group-title">⚡ 项目管理</div>
          <el-menu-item index="/workhours">
            <span class="menu-icon">⏱️</span>
            <span>工时管理</span>
          </el-menu-item>
          <el-menu-item index="/projects">
            <span class="menu-icon">📋</span>
            <span>项目分配</span>
          </el-menu-item>
        </div>
        
        <div class="menu-group">
          <div class="menu-group-title">🔧 系统管理</div>
          <el-menu-item index="/users" v-if="authStore.department === '应用中心' && authStore.role === '主任'">
            <span class="menu-icon">👥</span>
            <span>用户管理</span>
          </el-menu-item>
          <el-menu-item index="/alerts">
            <span class="menu-icon">🔔</span>
            <span>预警通知</span>
            <el-badge v-if="alertCount > 0" :value="alertCount" class="menu-badge" />
          </el-menu-item>
          <el-menu-item index="/search">
            <span class="menu-icon">🔍</span>
            <span>全局搜索</span>
          </el-menu-item>
          <el-menu-item index="/qa">
            <span class="menu-icon">🤖</span>
            <span>智能助手</span>
          </el-menu-item>
          <el-menu-item index="/knowledge">
            <span class="menu-icon">📚</span>
            <span>知识库</span>
          </el-menu-item>
          <el-menu-item index="/qualifications">
            <span class="menu-icon">📜</span>
            <span>资质管理</span>
          </el-menu-item>
          <el-menu-item index="/smart-import">
            <span class="menu-icon">📥</span>
            <span>智能导入</span>
          </el-menu-item>
          <el-menu-item index="/operation-logs" v-if="authStore.role === '主任'">
            <span class="menu-icon">📝</span>
            <span>操作日志</span>
          </el-menu-item>
        </div>
      </el-menu>
      
      <div class="sidebar-footer">
        <div class="collapse-btn" @click="toggleCollapse">
          <span>{{ isCollapsed ? '▶' : '◀' }}</span>
        </div>
        <el-button text @click="handleLogout" class="logout-btn">
          <span>🚪</span>
          <span>退出</span>
        </el-button>
      </div>
    </aside>
    
    <main class="main-content" :class="{ 'collapsed': isCollapsed }">
      <header class="header">
        <div class="header-left">
          <button class="menu-toggle" @click="toggleCollapse">☰</button>
          <div class="breadcrumb">
            <span class="breadcrumb-item">首页</span>
            <span class="breadcrumb-separator">/</span>
            <span class="breadcrumb-item active">{{ pageTitle }}</span>
          </div>
        </div>
        <div class="header-right">
          <div class="search-box">
            <span class="search-icon">🔍</span>
            <input type="text" placeholder="全局搜索..." class="search-input" @keyup.enter="handleGlobalSearch">
          </div>
          <div class="notification-btn" @click="handleNotificationClick">
            <span>🔔</span>
            <span class="badge" v-if="totalUnread > 0">{{ totalUnread }}</span>
          </div>
          <div class="header-user">
            <span>{{ authStore.name }}</span>
          </div>
        </div>
      </header>
      
      <div class="content-wrapper">
        <router-view />
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { ElMessage } from 'element-plus'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const isCollapsed = ref(false)
const unreadLogCount = ref(0)
const alertCount = ref(0)

const activeMenu = computed(() => route.path)

const pageTitleMap = {
  '/dashboard': '销售驾驶舱',
  '/reports': '业绩报表',
  '/customers': '客户管理',
  '/business': '商机看板',
  '/contracts': '合同管理',
  '/payments': '回款管理',
  '/visits': '拜访排班',
  '/pool': '公海池',
  '/leads': '智能线索',
  '/workhours': '工时管理',
  '/projects': '项目分配',
  '/users': '用户管理',
  '/alerts': '预警通知',
  '/search': '全局搜索',
  '/qa': '智能助手',
  '/knowledge': '企业知识库',
  '/knowledge-docs': '知识文档中心',
  '/qualifications': '资质信息管理',
  '/smart-import': '智能导入',
  '/operation-logs': '操作日志',
  '/products': '产品库存管理',
  '/quotes': '报价管理'
}

const pageTitle = computed(() => pageTitleMap[route.path] || '')

const totalUnread = computed(() => {
  return unreadLogCount.value + alertCount.value
})

const fetchUnreadCounts = async () => {
  try {
    const token = authStore.token
    if (!token) return
    
    const [logRes, alertRes] = await Promise.all([
      fetch('/api/operation_logs/unread_count', {
        headers: { 'Authorization': `Bearer ${token}` }
      }),
      fetch('/api/alerts', {
        headers: { 'Authorization': `Bearer ${token}` }
      })
    ])
    
    const logData = await logRes.json()
    if (logData.code === 200) {
      unreadLogCount.value = logData.data.unread_count || 0
    }
    
    const alertData = await alertRes.json()
    if (alertData.code === 200) {
      alertCount.value = alertData.data.count || 0
    }
  } catch (error) {
    console.error('Failed to fetch unread counts:', error)
  }
}

const handleLogout = () => {
  authStore.logout()
  ElMessage.success('已安全退出')
  router.push('/login')
}

const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
}

const handleCollapse = (val) => {
  isCollapsed.value = val
}

const handleGlobalSearch = (e) => {
  const keyword = e.target.value.trim()
  if (keyword) {
    router.push('/search?keyword=' + encodeURIComponent(keyword))
  }
}

const handleNotificationClick = () => {
  router.push('/alerts')
}

let refreshInterval = null

onMounted(() => {
  fetchUnreadCounts()
  refreshInterval = setInterval(fetchUnreadCounts, 30000)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})
</script>

<style scoped>
.layout-container {
  display: flex;
  min-height: 100vh;
  background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%);
}

.sidebar {
  width: 260px;
  background: linear-gradient(180deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
  color: white;
  display: flex;
  flex-direction: column;
  position: fixed;
  left: 0;
  top: 0;
  bottom: 0;
  transition: width 0.3s ease;
  z-index: 1000;
  box-shadow: 2px 0 20px rgba(0, 0, 0, 0.15);
}

.sidebar.collapsed {
  width: 64px;
}

.sidebar-header {
  padding: 18px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
}

.logo-wrapper {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  background: linear-gradient(135deg, #4ecdc4 0%, #44a08d 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 15px rgba(78, 205, 196, 0.3);
}

.logo {
  font-size: 24px;
}

.title-section {
  display: flex;
  flex-direction: column;
}

.title {
  font-size: 18px;
  font-weight: bold;
  color: #ffffff;
}

.subtitle {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.5);
  margin-top: 2px;
}

.user-info {
  padding: 14px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.avatar-wrapper {
  position: relative;
}

.avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(78, 205, 196, 0.2) 0%, rgba(68, 160, 141, 0.2) 100%);
  border: 2px solid rgba(78, 205, 196, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}

.status-indicator {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  position: absolute;
  bottom: 0;
  right: 0;
  border: 2px solid #1a1a2e;
}

.status-indicator.online {
  background: #4ecdc4;
}

.user-detail {
  display: flex;
  flex-direction: column;
}

.user-name {
  font-size: 14px;
  font-weight: 600;
  color: #ffffff;
}

.user-role {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.5);
}

.sidebar-menu {
  flex: 1;
  border-right: none;
  padding: 12px 0;
  overflow-y: auto;
  overflow-x: hidden;
}

.sidebar-menu::-webkit-scrollbar {
  width: 4px;
}

.sidebar-menu::-webkit-scrollbar-track {
  background: transparent;
}

.sidebar-menu::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
  border-radius: 2px;
}

.sidebar-menu::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.3);
}

.menu-group {
  padding: 8px 12px;
}

.menu-group-title {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.35);
  padding: 8px 12px;
  text-transform: uppercase;
  letter-spacing: 1px;
}

:deep(.el-menu-item) {
  margin: 2px 8px;
  border-radius: 8px;
  padding: 10px 14px !important;
  transition: all 0.3s ease;
}

:deep(.el-menu-item:hover) {
  background: rgba(78, 205, 196, 0.15) !important;
}

:deep(.el-menu-item.is-active) {
  background: linear-gradient(135deg, rgba(78, 205, 196, 0.25) 0%, rgba(68, 160, 141, 0.2) 100%) !important;
  border-left: 3px solid #4ecdc4;
}

.menu-icon {
  margin-right: 10px;
  font-size: 16px;
}

:deep(.menu-badge) {
  margin-left: 4px;
}

.sidebar-footer {
  padding: 12px 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  display: flex;
  gap: 8px;
}

.collapse-btn {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s ease;
}

.collapse-btn:hover {
  background: rgba(255, 255, 255, 0.2);
}

.logout-btn {
  flex: 1;
  color: rgba(255, 107, 107, 0.8);
  justify-content: flex-start;
  padding: 0 12px !important;
  height: 36px;
}

.main-content {
  flex: 1;
  margin-left: 260px;
  display: flex;
  flex-direction: column;
  transition: margin-left 0.3s ease;
}

.main-content.collapsed {
  margin-left: 64px;
}

.header {
  background: white;
  padding: 14px 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.menu-toggle {
  width: 36px;
  height: 36px;
  border: none;
  background: rgba(78, 205, 196, 0.1);
  border-radius: 8px;
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s ease;
}

.menu-toggle:hover {
  background: rgba(78, 205, 196, 0.2);
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.breadcrumb-item {
  color: #666;
}

.breadcrumb-item.active {
  color: #4ecdc4;
  font-weight: 600;
}

.breadcrumb-separator {
  color: #ccc;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 20px;
}

.search-box {
  display: flex;
  align-items: center;
  background: rgba(0, 0, 0, 0.04);
  border-radius: 8px;
  padding: 8px 16px;
}

.search-icon {
  margin-right: 10px;
  font-size: 14px;
  color: #999;
}

.search-input {
  border: none;
  background: transparent;
  outline: none;
  font-size: 14px;
  width: 180px;
}

.notification-btn {
  position: relative;
  font-size: 20px;
  cursor: pointer;
  color: #666;
}

.badge {
  position: absolute;
  top: -4px;
  right: -8px;
  background: #ff4747;
  color: white;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 10px;
}

.header-user {
  font-size: 14px;
  color: #333;
  font-weight: 500;
}

.content-wrapper {
  flex: 1;
  padding: 24px;
}
</style>