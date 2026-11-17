<template>
  <div class="layout-container">
    <!-- 移动端遮罩层 -->
    <div v-if="isMobile && mobileSidebarOpen" class="mobile-overlay" @click="closeMobileSidebar"></div>

    <aside class="sidebar" :class="{ 'collapsed': isCollapsed, 'mobile-open': isMobile && mobileSidebarOpen, 'mobile-hidden': isMobile && !mobileSidebarOpen }">
      <div class="sidebar-header">
        <div class="logo-wrapper">
          <div class="logo">🚀</div>
        </div>
        <div class="title-section" v-show="!isCollapsed">
          <span class="title">{{ t('layout.systemName') }}</span>
          <span class="subtitle">{{ t('layout.subtitle') }}</span>
        </div>
      </div>

      <div class="user-info" v-show="!isCollapsed">
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
        @select="closeMobileSidebar"
      >
        <div class="menu-group" v-if="!isHrRole && !isRestrictedDirector">
          <div class="menu-group-title" v-show="!isCollapsed">📊 {{ t('menu.salesManagement') }}</div>
          <el-menu-item index="/dashboard">
            <span class="menu-icon">📊</span>
            <span>{{ t('menuItem.dashboard') }}</span>
          </el-menu-item>
          <el-menu-item index="/reports">
            <span class="menu-icon">📈</span>
            <span>{{ t('menuItem.reports') }}</span>
          </el-menu-item>
          <el-menu-item index="/customers">
            <span class="menu-icon">👥</span>
            <span>{{ t('menuItem.customers') }}</span>
          </el-menu-item>
          <el-menu-item index="/business">
            <span class="menu-icon">🎯</span>
            <span>{{ t('menuItem.business') }}</span>
          </el-menu-item>
          <el-menu-item index="/contracts">
            <span class="menu-icon">📜</span>
            <span>{{ t('menuItem.contracts') }}</span>
          </el-menu-item>
          <el-menu-item index="/acceptances">
            <span class="menu-icon">📋</span>
            <span>验收管理</span>
          </el-menu-item>
          <el-menu-item index="/quotes">
            <span class="menu-icon">💵</span>
            <span>{{ t('menuItem.quotes') }}</span>
          </el-menu-item>
          <el-menu-item index="/products">
            <span class="menu-icon">📦</span>
            <span>{{ t('menuItem.products') }}</span>
          </el-menu-item>
          <el-menu-item index="/payments">
            <span class="menu-icon">💰</span>
            <span>{{ t('menuItem.payments') }}</span>
          </el-menu-item>
          <el-menu-item index="/receivables">
            <span class="menu-icon">🧾</span>
            <span>两金明细表</span>
          </el-menu-item>
          <el-menu-item index="/visits">
            <span class="menu-icon">📅</span>
            <span>{{ t('menuItem.visits') }}</span>
          </el-menu-item>
          <el-menu-item index="/sandbox">
            <span class="menu-icon">🎖️</span>
            <span>{{ t('menuItem.sandbox') }}</span>
          </el-menu-item>
        </div>

        <div class="menu-group" v-if="!isHrRole && !isRestrictedDirector">
          <div class="menu-group-title" v-show="!isCollapsed">📢 {{ t('menu.marketingManagement') }}</div>
          <el-menu-item index="/marketing">
            <span class="menu-icon">📢</span>
            <span>{{ t('menuItem.marketing') }}</span>
          </el-menu-item>
        </div>

        <div class="menu-group" v-if="!isHrRole">
          <div class="menu-group-title" v-show="!isCollapsed">🛠️ {{ t('menu.afterSales') }}</div>
          <el-menu-item index="/service">
            <span class="menu-icon">🛠️</span>
            <span>{{ t('menuItem.service') }}</span>
          </el-menu-item>
        </div>

        <div class="menu-group" v-if="!isHrRole && !isRestrictedDirector">
          <div class="menu-group-title" v-show="!isCollapsed">📡 AI情报中心</div>
          <el-menu-item index="/cockpit" v-if="has('cockpit.view')">
            <span class="menu-icon">🚀</span>
            <span>AI驾驶舱</span>
          </el-menu-item>
          <el-menu-item index="/intelligence" v-if="has('intel.view') || has('intel.leads')">
            <span class="menu-icon">📡</span>
            <span>情报与线索</span>
          </el-menu-item>
          <el-menu-item index="/tender-analysis" v-if="has('intel.view') || has('intel.leads')">
            <span class="menu-icon">📑</span>
            <span>招标文件研判</span>
          </el-menu-item>
          <el-menu-item index="/customer-profiles" v-if="has('intel.profile')">
            <span class="menu-icon">🏢</span>
            <span>客户画像</span>
          </el-menu-item>
          <el-menu-item index="/competitor-analysis" v-if="has('intel.competitor')">
            <span class="menu-icon">⚔️</span>
            <span>竞争对手分析</span>
          </el-menu-item>
          <el-menu-item index="/task-monitor" v-if="has('system.admin')">
            <span class="menu-icon">🧵</span>
            <span>任务监控</span>
          </el-menu-item>
          <el-menu-item index="/daily-report" v-if="has('intel.report')">
            <span class="menu-icon">📰</span>
            <span>AI日报</span>
          </el-menu-item>
          <el-menu-item index="/business-tags" v-if="has('intel.keywords')">
            <span class="menu-icon">🧬</span>
            <span>标签与能力</span>
          </el-menu-item>
          <el-menu-item index="/enterprises">
            <span class="menu-icon">🗄️</span>
            <span>{{ t('menuItem.enterprises') }}</span>
          </el-menu-item>
        </div>

        <div class="menu-group" v-if="!isHrRole && !isRestrictedDirector">
          <div class="menu-group-title" v-show="!isCollapsed">🌊 {{ t('menu.resourceManagement') }}</div>
          <el-menu-item index="/pool">
            <span class="menu-icon">🌊</span>
            <span>{{ t('menuItem.pool') }}</span>
          </el-menu-item>
        </div>

        <div class="menu-group" v-if="!isHrRole">
          <div class="menu-group-title" v-show="!isCollapsed">⚡ {{ t('menu.projectManagement') }}</div>
          <el-menu-item index="/workhours">
            <span class="menu-icon">⏱️</span>
            <span>{{ t('menuItem.workhours') }}</span>
          </el-menu-item>
          <el-menu-item index="/projects">
            <span class="menu-icon">📋</span>
            <span>{{ t('menuItem.projects') }}</span>
          </el-menu-item>
          <el-menu-item index="/market-tasks">
            <span class="menu-icon">📨</span>
            <span>市场任务单</span>
          </el-menu-item>
          <el-menu-item index="/project-cost" v-if="!isRestrictedDirector && (has('workhour.view') || has('workhour.manage') || has('data.view_all') || has('cost.view') || has('cost.actual.manage'))">
            <span class="menu-icon">💰</span>
            <span>项目成本核算</span>
          </el-menu-item>
          <el-menu-item index="/opportunity-cost" v-if="!isRestrictedDirector">
            <span class="menu-icon">📐</span>
            <span>商机成本评估</span>
          </el-menu-item>
        </div>

        <div class="menu-group" v-if="!isRestrictedDirector">
          <div class="menu-group-title" v-show="!isCollapsed">🧾 {{ t('menu.hrManagement') }}</div>
          <el-menu-item index="/appraisal">
            <span class="menu-icon">🧾</span>
            <span>{{ t('menuItem.appraisal') }}</span>
          </el-menu-item>
          <el-menu-item index="/quarterly-assessment">
            <span class="menu-icon">📊</span>
            <span>季度考核</span>
          </el-menu-item>
          <el-menu-item index="/work-cost" v-if="has('workhour.view') || has('workhour.manage') || has('data.view_all')">
            <span class="menu-icon">⏱️</span>
            <span>工时分摊</span>
          </el-menu-item>
        </div>

        <div class="menu-group" v-if="!isHrRole && !isRestrictedDirector">
          <div class="menu-group-title" v-show="!isCollapsed">🔧 {{ t('menu.systemManagement') }}</div>
          <el-menu-item index="/users" v-if="has('system.admin')">
            <span class="menu-icon">👥</span>
            <span>{{ t('menuItem.users') }}</span>
          </el-menu-item>
          <el-menu-item index="/data-sources" v-if="has('system.admin') || has('data.view_all')">
            <span class="menu-icon">📡</span>
            <span>数据源管理</span>
          </el-menu-item>
          <el-menu-item index="/alerts">
            <span class="menu-icon">🔔</span>
            <span>{{ t('menuItem.alerts') }}</span>
            <el-badge v-if="alertCount > 0" :value="alertCount" class="menu-badge" />
          </el-menu-item>
          <el-menu-item index="/search">
            <span class="menu-icon">🔍</span>
            <span>{{ t('menuItem.search') }}</span>
          </el-menu-item>
          <el-menu-item index="/qa">
            <span class="menu-icon">🤖</span>
            <span>{{ t('menuItem.qa') }}</span>
          </el-menu-item>
          <el-menu-item index="/knowledge">
            <span class="menu-icon">📚</span>
            <span>{{ t('menuItem.knowledge') }}</span>
          </el-menu-item>
          <el-menu-item index="/qualifications">
            <span class="menu-icon">📜</span>
            <span>{{ t('menuItem.qualifications') }}</span>
          </el-menu-item>
          <el-menu-item index="/smart-import">
            <span class="menu-icon">📥</span>
            <span>{{ t('menuItem.smartImport') }}</span>
          </el-menu-item>
          <el-menu-item index="/operation-logs" v-if="has('system.logs')">
            <span class="menu-icon">📝</span>
            <span>{{ t('menuItem.operationLogs') }}</span>
          </el-menu-item>
        </div>
      </el-menu>

      <div class="sidebar-footer">
        <div class="collapse-btn" @click="toggleCollapse" v-show="!isMobile">
          <span>{{ isCollapsed ? '▶' : '◀' }}</span>
        </div>
        <el-button text @click="handleLogout" class="logout-btn">
          <span>🚪</span>
          <span v-show="!isCollapsed">{{ t('layout.logout') }}</span>
        </el-button>
      </div>
    </aside>

    <main class="main-content" :class="{ 'collapsed': isCollapsed, 'mobile': isMobile }">
      <header class="header">
        <div class="header-left">
          <button class="menu-toggle" @click="toggleCollapse">☰</button>
          <div class="breadcrumb">
            <span class="breadcrumb-item">{{ t('layout.home') }}</span>
            <span class="breadcrumb-separator">/</span>
            <span class="breadcrumb-item active">{{ pageTitle }}</span>
          </div>
        </div>
        <div class="header-right">
          <div class="search-box">
            <span class="search-icon">🔍</span>
            <input type="text" :placeholder="t('layout.globalSearch')" class="search-input" @keyup.enter="handleGlobalSearch">
          </div>
          <div class="lang-switcher" @click="openSettings" :title="t('layout.settings')">
            <span class="lang-flag">{{ settingsStore.currentLocale.flag }}</span>
            <span class="lang-label">{{ settingsStore.currentLocale.label }}</span>
          </div>
          <div class="settings-btn" @click="openSettings" :title="t('layout.settings')">
            <span>⚙️</span>
          </div>
          <el-popover v-model:visible="showNotifyPanel" placement="bottom-end" :width="400"
                      trigger="click" popper-class="notify-popover" @show="onNotifyPanelShow">
            <template #reference>
              <div class="notification-btn" :class="{ shaking: notifyShaking }">
                <span>🔔</span>
                <span class="badge" v-if="totalUnread > 0">{{ totalUnread > 99 ? '99+' : totalUnread }}</span>
              </div>
            </template>
            <div class="notify-panel">
              <div class="notify-head">
                <div class="notify-title">
                  消息中心
                  <span v-if="totalUnread > 0" class="notify-count">{{ totalUnread }} 条未读</span>
                </div>
                <el-button link type="primary" size="small" :disabled="totalUnread === 0"
                           @click="markAllRead(notifyFilter)">全部已读</el-button>
              </div>
              <div class="notify-tabs">
                <span v-for="tab in notifyTabs" :key="tab.type"
                      class="notify-tab" :class="{ active: notifyFilter === tab.type }"
                      @click="notifyFilter = tab.type">
                  {{ tab.label }}
                  <em v-if="notifyCounts[tab.type]">{{ notifyCounts[tab.type] }}</em>
                </span>
              </div>
              <div class="notify-body" v-loading="notifyLoading">
                <div v-for="msg in filteredNotifications" :key="msg.key" class="notify-item"
                     @click="openNotification(msg)">
                  <span class="notify-dot" :class="msg.priority"></span>
                  <div class="notify-main">
                    <div class="notify-item-title">
                      {{ msg.title }}
                      <em v-if="msg.count > 1" class="notify-group">×{{ msg.count }}</em>
                    </div>
                    <div class="notify-item-detail">{{ msg.detail }}</div>
                    <div class="notify-item-meta">
                      <span class="notify-type">{{ notifyTypeLabel(msg.type) }}</span>
                      <span v-if="msg.time" class="notify-time">{{ msg.time }}</span>
                    </div>
                  </div>
                  <span class="notify-read" title="标记已读" @click.stop="markOneRead(msg)">✓</span>
                </div>
                <div v-if="!filteredNotifications.length" class="notify-empty">
                  🔔 暂无新消息
                </div>
              </div>
              <div class="notify-foot" @click="goNotifyPage">查看全部消息 →</div>
            </div>
          </el-popover>
          <div class="header-user">
            <span>{{ authStore.name }}</span>
          </div>
        </div>
      </header>

      <div class="content-wrapper">
        <router-view />
      </div>
    </main>

    <!-- 设置抽屉 -->
    <el-drawer v-model="showSettingsDrawer" :title="t('settings.title')" direction="rtl" size="380px">
      <div class="settings-panel">
        <!-- 语言设置 -->
        <div class="setting-section">
          <div class="setting-label">{{ t('settings.language') }}</div>
          <div class="lang-options">
            <div
              v-for="locale in availableLocales"
              :key="locale.value"
              class="lang-option"
              :class="{ active: settingsForm.language === locale.value }"
              @click="onLanguageChange(locale.value)"
            >
              <span class="lang-flag">{{ locale.flag }}</span>
              <span>{{ locale.label }}</span>
              <span v-if="settingsForm.language === locale.value" class="check">✓</span>
            </div>
          </div>
        </div>

        <!-- 时区设置 -->
        <div class="setting-section">
          <div class="setting-label">{{ t('settings.timezone') }}</div>
          <el-select v-model="settingsForm.timezone" style="width: 100%;" @change="onTimezoneChange" filterable>
            <el-option
              v-for="tz in timezones"
              :key="tz.value"
              :label="tz.label"
              :value="tz.value"
            />
          </el-select>
          <div class="setting-hint">{{ t('settings.currentTimezone') }}: {{ settingsForm.timezone }}</div>
        </div>

        <!-- 主题设置 -->
        <div class="setting-section">
          <div class="setting-label">{{ t('settings.theme') }}</div>
          <el-radio-group v-model="settingsForm.theme" @change="onThemeChange">
            <el-radio-button label="light">☀️ {{ t('settings.light') }}</el-radio-button>
            <el-radio-button label="dark">🌙 {{ t('settings.dark') }}</el-radio-button>
          </el-radio-group>
        </div>

        <!-- 字号设置 -->
        <div class="setting-section">
          <div class="setting-label">{{ t('settings.fontSize') }}</div>
          <el-radio-group v-model="settingsForm.font_size" @change="onFontSizeChange">
            <el-radio-button label="small">{{ t('settings.small') }}</el-radio-button>
            <el-radio-button label="medium">{{ t('settings.medium') }}</el-radio-button>
            <el-radio-button label="large">{{ t('settings.large') }}</el-radio-button>
          </el-radio-group>
        </div>

        <!-- 预览 -->
        <div class="setting-section preview-section">
          <div class="setting-label">{{ t('settings.preview') }}</div>
          <div class="preview-box">
            <p>{{ t('common.confirm') }} · {{ t('common.cancel') }} · {{ t('common.save') }} · {{ t('common.delete') }}</p>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="showSettingsDrawer = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="savingSettings" @click="saveSettings">{{ t('common.save') }}</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useAuthStore } from '../stores/auth'
import { useSettingsStore } from '../stores/settings'
import { ElMessage, ElNotification } from 'element-plus'
import { availableLocales, translate } from '../locales'
import api from '../api'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const settingsStore = useSettingsStore()
const { language } = storeToRefs(settingsStore)
const t = (key, params = null) => translate(language.value, key, params)

// 权限驱动：RBAC 权限点判断
const has = (code) => authStore.has(code)

// 仅考核权限（如"人力"角色）：只能看到月度考核菜单
const isHrRole = computed(() =>
  authStore.permissions.length === 1 && authStore.permissions[0] === 'appraisal.view'
)

// 技术中心主任：仅保留项目管理（工时/项目列表）与售后服务，隐藏销售/营销/AI情报/资源/人事考核/系统管理及项目成本核算
const isRestrictedDirector = computed(() =>
  authStore.role === '主任' && authStore.department === '技术中心'
)

const isCollapsed = ref(false)
const isMobile = ref(false)
const mobileSidebarOpen = ref(false)
const unreadLogCount = ref(0)
const alertCount = ref(0)

// 设置抽屉
const showSettingsDrawer = ref(false)
const timezones = ref([])
const settingsForm = ref({
  language: 'zh-CN',
  timezone: 'Asia/Shanghai',
  theme: 'light',
  font_size: 'medium'
})
const savingSettings = ref(false)

const activeMenu = computed(() => route.path)

const pageTitleMap = computed(() => ({
  '/dashboard': t('menuItem.dashboard'),
  '/reports': t('menuItem.reports'),
  '/customers': t('menuItem.customers'),
  '/business': t('menuItem.business'),
  '/contracts': t('menuItem.contracts'),
  '/payments': t('menuItem.payments'),
  '/visits': t('menuItem.visits'),
  '/pool': t('menuItem.pool'),
  '/leads': t('menuItem.leads'),
  '/workhours': t('menuItem.workhours'),
  '/work-cost': '工时分摊',
  '/project-cost': '项目成本核算',
  '/opportunity-cost': '商机成本评估',
  '/projects': t('menuItem.projects'),
  '/users': t('menuItem.users'),
  '/alerts': t('menuItem.alerts'),
  '/search': t('menuItem.search'),
  '/qa': t('menuItem.qa'),
  '/knowledge': t('menuItem.knowledge'),
  '/knowledge-docs': t('menuItem.knowledge'),
  '/qualifications': t('menuItem.qualifications'),
  '/smart-import': t('menuItem.smartImport'),
  '/operation-logs': t('menuItem.operationLogs'),
  '/products': t('menuItem.products'),
  '/quotes': t('menuItem.quotes'),
  '/marketing': t('menuItem.marketing'),
  '/service': t('menuItem.service'),
  '/enterprises': t('menuItem.enterprises')
}))

const pageTitle = computed(() => pageTitleMap.value[route.path] || '')

const totalUnread = computed(() => {
  return notifyTotal.value || (unreadLogCount.value + alertCount.value)
})

// 响应式：检测屏幕宽度
const checkResponsive = () => {
  const width = window.innerWidth
  isMobile.value = width < 768
  if (isMobile.value) {
    isCollapsed.value = false
    mobileSidebarOpen.value = false
  }
}

const handleLogout = () => {
  authStore.logout()
  ElMessage.success(t('layout.logout'))
  router.push('/login')
}

const toggleCollapse = () => {
  if (isMobile.value) {
    mobileSidebarOpen.value = !mobileSidebarOpen.value
  } else {
    isCollapsed.value = !isCollapsed.value
  }
}

const handleCollapse = (val) => {
  isCollapsed.value = val
}

const closeMobileSidebar = () => {
  mobileSidebarOpen.value = false
}

const handleGlobalSearch = (e) => {
  const keyword = e.target.value.trim()
  if (keyword) {
    router.push('/search?keyword=' + encodeURIComponent(keyword))
  }
}

/* ---------------- 消息中心 ---------------- */
const showNotifyPanel = ref(false)
const notifyLoading = ref(false)
const notifyItems = ref([])
const notifyCounts = ref({ alert: 0, approval: 0, expiry: 0, oplog: 0 })
const notifyFilter = ref('all')
const notifyShaking = ref(false)
const notifyTotal = ref(0)
let lastTotalUnread = -1

const notifyTabs = [
  { type: 'all', label: '全部' },
  { type: 'alert', label: '销售提醒' },
  { type: 'approval', label: '审批待办' },
  { type: 'expiry', label: '业务到期' },
  { type: 'oplog', label: '系统日志' }
]

const notifyTypeLabel = (type) => ({
  alert: '销售提醒', approval: '审批待办', expiry: '业务到期', oplog: '系统日志'
}[type] || '消息')

const filteredNotifications = computed(() => {
  if (notifyFilter.value === 'all') return notifyItems.value
  return notifyItems.value.filter(i => i.type === notifyFilter.value)
})

const loadNotifications = async (silent = false) => {
  if (!authStore.token) return
  if (!silent) notifyLoading.value = true
  try {
    const res = await api.get('/notifications')
    if (res.code === 200 && res.data) {
      notifyItems.value = res.data.items || []
      notifyCounts.value = res.data.counts || { alert: 0, approval: 0, expiry: 0, oplog: 0 }
      unreadLogCount.value = notifyCounts.value.oplog || 0
      alertCount.value = notifyCounts.value.alert || 0
      const total = res.data.total_unread || 0
      notifyTotal.value = total
      // 新消息到达时弹出提示
      if (total > lastTotalUnread && lastTotalUnread >= 0) {
        const newest = notifyItems.value[0]
        ElNotification({
          title: `您有 ${total} 条未读消息`,
          message: newest ? newest.title : '点击右上角铃铛查看消息中心',
          type: 'info',
          duration: 4500,
          position: 'bottom-right',
          onClick: () => { showNotifyPanel.value = true }
        })
        notifyShaking.value = true
        setTimeout(() => { notifyShaking.value = false }, 900)
      }
      lastTotalUnread = total
    }
  } catch (e) {
    console.error('加载消息中心失败:', e)
  } finally {
    notifyLoading.value = false
  }
}

const onNotifyPanelShow = () => {
  loadNotifications()
}

const markOneRead = async (msg) => {
  try {
    const res = await api.post('/notifications/read', { key: msg.key })
    if (res.code === 200) await loadNotifications(true)
  } catch (e) {
    ElMessage.error('标记已读失败')
  }
}

const markAllRead = async (type) => {
  try {
    const res = await api.post('/notifications/read-all', { type })
    if (res.code === 200) {
      ElMessage.success('已全部标记为已读')
      await loadNotifications(true)
    }
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

const openNotification = async (msg) => {
  await markOneRead(msg)
  showNotifyPanel.value = false
  if (msg.route) router.push(msg.route)
}

const goNotifyPage = () => {
  showNotifyPanel.value = false
  router.push('/alerts')
}

// 设置抽屉
const openSettings = () => {
  settingsForm.value = {
    language: settingsStore.language,
    timezone: settingsStore.timezone,
    theme: settingsStore.theme,
    font_size: settingsStore.fontSize
  }
  showSettingsDrawer.value = true
}

const fetchTimezones = async () => {
  try {
    const res = await api.get('/system/timezones')
    if (res.code === 200) {
      timezones.value = res.data || []
    }
  } catch (e) {
    console.error('时区列表获取失败', e)
  }
}

const onLanguageChange = (lang) => {
  settingsStore.setLanguage(lang)
  settingsForm.value.language = lang
}

const onTimezoneChange = (tz) => {
  settingsStore.setTimezone(tz)
  settingsForm.value.timezone = tz
}

const onThemeChange = (theme) => {
  settingsStore.setTheme(theme)
  settingsForm.value.theme = theme
}

const onFontSizeChange = (size) => {
  settingsStore.setFontSize(size)
  settingsForm.value.font_size = size
}

const saveSettings = async () => {
  savingSettings.value = true
  try {
    const res = await settingsStore.savePreferences(settingsForm.value)
    if (res.code === 200) {
      ElMessage.success(t('settings.saveSuccess'))
      showSettingsDrawer.value = false
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    savingSettings.value = false
  }
}

let refreshInterval = null

onMounted(async () => {
  checkResponsive()
  window.addEventListener('resize', checkResponsive)
  await settingsStore.loadPreferences()
  loadNotifications(true)
  fetchTimezones()
  refreshInterval = setInterval(() => loadNotifications(true), 60000)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkResponsive)
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
  min-height: 0;
  min-width: 0;
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

.notification-btn.shaking {
  animation: bell-shake 0.8s ease-in-out;
}

@keyframes bell-shake {
  0%, 100% { transform: rotate(0); }
  20% { transform: rotate(-16deg); }
  40% { transform: rotate(14deg); }
  60% { transform: rotate(-10deg); }
  80% { transform: rotate(8deg); }
}

:global(.notify-popover) {
  padding: 0 !important;
}

.notify-panel {
  display: flex;
  flex-direction: column;
  max-height: 520px;
}

.notify-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px 8px;
  border-bottom: 1px solid #f0f2f5;
}

.notify-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.notify-count {
  font-size: 12px;
  color: #f56c6c;
  font-weight: 500;
  margin-left: 6px;
}

.notify-tabs {
  display: flex;
  gap: 4px;
  padding: 8px 12px;
  border-bottom: 1px solid #f0f2f5;
  flex-wrap: wrap;
}

.notify-tab {
  font-size: 12px;
  color: #606266;
  padding: 3px 9px;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.notify-tab:hover {
  background: #f2f6fc;
}

.notify-tab.active {
  background: #ecf5ff;
  color: #409eff;
  font-weight: 600;
}

.notify-tab em {
  font-style: normal;
  font-size: 10px;
  background: #f56c6c;
  color: #fff;
  border-radius: 8px;
  padding: 0 5px;
  margin-left: 2px;
}

.notify-body {
  flex: 1;
  overflow-y: auto;
  min-height: 90px;
}

.notify-item {
  display: flex;
  gap: 9px;
  padding: 10px 14px;
  border-bottom: 1px solid #f7f8fa;
  cursor: pointer;
  transition: background 0.2s;
}

.notify-item:hover {
  background: #f7fafd;
}

.notify-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 5px;
  flex-shrink: 0;
  background: #909399;
}

.notify-dot.urgent { background: #f56c6c; }
.notify-dot.high { background: #e6a23c; }
.notify-dot.normal { background: #409eff; }
.notify-dot.low { background: #c0c4cc; }

.notify-main {
  flex: 1;
  min-width: 0;
}

.notify-item-title {
  font-size: 13px;
  color: #303133;
  font-weight: 500;
  line-height: 1.4;
}

.notify-group {
  font-style: normal;
  font-size: 11px;
  color: #f56c6c;
  background: #fef0f0;
  border-radius: 8px;
  padding: 0 6px;
  margin-left: 4px;
}

.notify-item-detail {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.notify-item-meta {
  display: flex;
  gap: 10px;
  margin-top: 4px;
  font-size: 11px;
  color: #b1b3b8;
}

.notify-type {
  color: #909399;
  background: #f4f4f5;
  border-radius: 3px;
  padding: 0 5px;
}

.notify-read {
  align-self: center;
  color: #c0c4cc;
  font-size: 14px;
  padding: 2px 4px;
}

.notify-read:hover {
  color: #67c23a;
}

.notify-empty {
  text-align: center;
  color: #b1b3b8;
  font-size: 13px;
  padding: 34px 0;
}

.notify-foot {
  text-align: center;
  font-size: 12px;
  color: #409eff;
  padding: 9px 0;
  border-top: 1px solid #f0f2f5;
  cursor: pointer;
}

.notify-foot:hover {
  background: #f7fafd;
}

.header-user {
  font-size: 14px;
  color: #333;
  font-weight: 500;
}

.content-wrapper {
  flex: 1;
  padding: 24px;
  min-height: 0;
  min-width: 0;
}

/* ==================== 语言切换器 ==================== */
.lang-switcher {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 6px 12px;
  border-radius: 8px;
  transition: all 0.3s ease;
  font-size: 13px;
  color: #666;
}

.lang-switcher:hover {
  background: rgba(78, 205, 196, 0.1);
}

.lang-flag {
  font-size: 16px;
}

.lang-label {
  font-weight: 500;
}

/* ==================== 设置按钮 ==================== */
.settings-btn {
  cursor: pointer;
  font-size: 20px;
  padding: 4px 8px;
  border-radius: 8px;
  transition: all 0.3s ease;
}

.settings-btn:hover {
  background: rgba(78, 205, 196, 0.1);
  transform: rotate(45deg);
}

/* ==================== 设置面板 ==================== */
.settings-panel {
  display: flex;
  flex-direction: column;
  gap: 28px;
}

.setting-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.setting-label {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.setting-hint {
  font-size: 12px;
  color: #999;
}

.lang-options {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.lang-option {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border: 2px solid #e4e8ec;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.3s ease;
  font-size: 14px;
}

.lang-option:hover {
  border-color: #4ecdc4;
  background: rgba(78, 205, 196, 0.05);
}

.lang-option.active {
  border-color: #4ecdc4;
  background: rgba(78, 205, 196, 0.1);
  color: #4ecdc4;
  font-weight: 600;
}

.lang-option .check {
  margin-left: auto;
  color: #4ecdc4;
  font-weight: bold;
}

.preview-section {
  margin-top: 8px;
}

.preview-box {
  padding: 16px;
  background: #f5f7fa;
  border-radius: 10px;
  text-align: center;
  color: #666;
  font-size: 14px;
}

/* ==================== 移动端遮罩 ==================== */
.mobile-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 999;
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

/* ==================== 响应式设计 ==================== */

/* 平板（768px - 1024px） */
@media (max-width: 1024px) {
  .sidebar {
    width: 220px;
  }

  .main-content {
    margin-left: 220px;
  }

  .main-content.collapsed {
    margin-left: 64px;
  }

  .content-wrapper {
    padding: 16px;
  }

  .search-input {
    width: 140px;
  }

  .header {
    padding: 12px 16px;
  }
}

/* 手机（< 768px） */
@media (max-width: 767px) {
  .sidebar {
    width: 260px;
    transform: translateX(-100%);
    transition: transform 0.3s ease;
  }

  .sidebar.mobile-open {
    transform: translateX(0);
  }

  .sidebar.mobile-hidden {
    transform: translateX(-100%);
  }

  .sidebar.collapsed {
    width: 260px;
  }

  .main-content {
    margin-left: 0 !important;
  }

  .main-content.mobile {
    margin-left: 0;
  }

  .header {
    padding: 10px 12px;
  }

  .header-right {
    gap: 10px;
  }

  .search-box {
    display: none;
  }

  .lang-label {
    display: none;
  }

  .header-user {
    display: none;
  }

  .content-wrapper {
    padding: 12px;
  }

  .breadcrumb {
    font-size: 13px;
  }
}

/* 超小屏幕（< 480px） */
@media (max-width: 479px) {
  .header-left {
    gap: 8px;
  }

  .breadcrumb-item {
    font-size: 12px;
  }

  .settings-btn {
    font-size: 18px;
  }

  .notification-btn {
    font-size: 18px;
  }
}
</style>