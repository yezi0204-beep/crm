import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue')
  },
  {
    path: '/',
    name: 'Layout',
    component: () => import('../views/Layout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('../views/Dashboard.vue')
      },
      {
        path: 'reports',
        name: 'Reports',
        component: () => import('../views/Reports.vue')
      },
      {
        path: 'customers',
        name: 'Customers',
        component: () => import('../views/Customers.vue')
      },
      {
        path: 'business',
        name: 'Business',
        component: () => import('../views/Business.vue')
      },
      {
        path: 'contracts',
        name: 'Contracts',
        component: () => import('../views/Contracts.vue')
      },
      {
        path: 'acceptances',
        name: 'Acceptances',
        component: () => import('../views/Acceptance.vue')
      },
      {
        path: 'payments',
        name: 'Payments',
        component: () => import('../views/Payments.vue')
      },
      {
        path: 'receivables',
        name: 'Receivables',
        component: () => import('../views/Receivables.vue')
      },
      {
        path: 'users',
        name: 'Users',
        component: () => import('../views/Users.vue')
      },
      {
        path: 'data-sources',
        name: 'DataSources',
        component: () => import('../views/DataSources.vue')
      },
      {
        path: 'pool',
        name: 'Pool',
        component: () => import('../views/Pool.vue')
      },
      {
        path: 'workhours',
        name: 'WorkHours',
        component: () => import('../views/WorkHours.vue')
      },
      {
        path: 'work-cost',
        name: 'WorkCost',
        component: () => import('../views/WorkCost.vue')
      },
      {
        path: 'project-cost',
        name: 'ProjectCost',
        component: () => import('../views/ProjectCost.vue')
      },
      {
        path: 'opportunity-cost',
        name: 'OpportunityCost',
        component: () => import('../views/OpportunityCost.vue')
      },
      {
        path: 'quarterly-assessment',
        name: 'QuarterlyAssessment',
        component: () => import('../views/QuarterlyAssessment.vue')
      },
      {
        path: 'projects',
        name: 'Projects',
        component: () => import('../views/Projects.vue')
      },
      {
        path: 'search',
        name: 'Search',
        component: () => import('../views/Search.vue')
      },
      {
        path: 'qa',
        name: 'Qa',
        component: () => import('../views/Qa.vue')
      },
      {
        path: 'knowledge',
        name: 'Knowledge',
        component: () => import('../views/Knowledge.vue')
      },
      {
        path: 'leads',
        redirect: { path: '/intelligence', query: { tab: 'leads' } }
      },
      {
        path: 'alerts',
        name: 'Alerts',
        component: () => import('../views/Alerts.vue')
      },
      {
        path: 'visits',
        name: 'Visits',
        component: () => import('../views/Visits.vue')
      },
      {
        path: 'operation-logs',
        name: 'OperationLogs',
        component: () => import('../views/OperationLogs.vue')
      },
      {
        path: 'qualifications',
        name: 'Qualifications',
        component: () => import('../views/Qualifications.vue')
      },
      {
        path: 'smart-import',
        name: 'SmartImport',
        component: () => import('../views/SmartImport.vue')
      },
      {
        path: 'enterprises',
        name: 'Enterprises',
        component: () => import('../views/Enterprises.vue')
      },
      {
        path: 'products',
        name: 'Products',
        component: () => import('../views/Products.vue')
      },
      {
        path: 'quotes',
        name: 'Quotes',
        component: () => import('../views/Quotes.vue')
      },
      {
        path: 'marketing',
        name: 'Marketing',
        component: () => import('../views/Marketing.vue')
      },
      {
        path: 'service',
        name: 'Service',
        component: () => import('../views/Service.vue')
      },
      {
        path: 'appraisal',
        name: 'Appraisal',
        component: () => import('../views/Appraisal.vue')
      },
      {
        path: 'keywords',
        redirect: { path: '/business-tags' }
      },
      {
        path: 'business-tags',
        name: 'BusinessTags',
        component: () => import('../views/BusinessTags.vue')
      },
      {
        path: 'intelligence',
        name: 'Intelligence',
        component: () => import('../views/IntelligenceHub.vue')
      },
      {
        path: 'intel-leads',
        redirect: { path: '/intelligence', query: { tab: 'ai-leads' } }
      },
      {
        path: 'daily-report',
        name: 'DailyReport',
        component: () => import('../views/DailyReport.vue')
      },
      {
        path: 'cockpit',
        name: 'Cockpit',
        component: () => import('../views/Cockpit.vue')
      },
      {
        path: 'customer-profiles',
        name: 'CustomerProfiles',
        component: () => import('../views/CustomerProfiles.vue')
      },
      {
        path: 'competitor-analysis',
        name: 'CompetitorAnalysis',
        component: () => import('../views/CompetitorAnalysis.vue')
      },
      {
        path: 'opportunity-radar',
        redirect: { path: '/intelligence', query: { tab: 'ai-leads' } }
      },
      {
        path: 'capabilities',
        redirect: { path: '/business-tags' }
      },
      {
        path: 'task-monitor',
        name: 'TaskMonitor',
        component: () => import('../views/TaskMonitor.vue')
      },
      {
        path: 'market-tasks',
        name: 'MarketTasks',
        component: () => import('../views/MarketTasks.vue')
      },
      {
        path: 'tender-analysis',
        name: 'TenderAnalysis',
        component: () => import('../views/TenderAnalysis.vue')
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()
  
  if (to.path === '/login') {
    next()
    return
  }
  
  if (!authStore.isLoggedIn) {
    await authStore.checkLogin()
  }
  
  if (!authStore.isLoggedIn) {
    next('/login')
    return
  }
  
  // RBAC 权限点驱动路由守卫
  if (to.path === '/operation-logs' && !authStore.has('system.logs')) {
    next('/dashboard')
    return
  }

  if (to.path === '/users' && !authStore.has('system.admin')) {
    next('/dashboard')
    return
  }

  if (to.path === '/leads' && !authStore.has('leads.view_all')) {
    next('/dashboard')
    return
  }

  // 仅考核权限的用户（如"人力"角色）只能访问月度考核页面
  const appraisalOnly = authStore.permissions.length === 1 && authStore.permissions[0] === 'appraisal.view'
  if (appraisalOnly && to.path !== '/appraisal') {
    next('/appraisal')
    return
  }

  // 技术中心主任：仅允许工时管理/项目列表/售后服务，其余模块（销售/营销/AI情报/资源/人事考核/系统管理/项目成本核算）一律跳转工时管理
  const isRestrictedDirector = authStore.role === '主任' && authStore.department === '技术中心'
  if (isRestrictedDirector) {
    const blocked = [
      // 销售管理
      '/dashboard', '/reports', '/customers', '/business', '/contracts', '/acceptances',
      '/quotes', '/products', '/payments', '/visits', '/receivables',
      // 营销管理
      '/marketing',
      // AI情报中心
      '/cockpit', '/intelligence', '/tender-analysis', '/customer-profiles', '/competitor-analysis',
      '/task-monitor', '/daily-report', '/business-tags', '/enterprises',
      // 资源管理
      '/pool',
      // 项目管理-项目成本核算
      '/project-cost',
      // 人事考核
      '/appraisal', '/quarterly-assessment', '/work-cost',
      // 系统管理
      '/users', '/data-sources', '/alerts', '/search', '/qa', '/knowledge',
      '/qualifications', '/smart-import', '/operation-logs',
    ]
    if (blocked.includes(to.path)) {
      next('/workhours')
      return
    }
  }

  next()
})

export default router