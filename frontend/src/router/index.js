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
        name: 'Keywords',
        component: () => import('../views/Keywords.vue')
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
        name: 'OpportunityRadar',
        component: () => import('../views/OpportunityRadar.vue')
      },
      {
        path: 'capabilities',
        name: 'Capabilities',
        component: () => import('../views/Capabilities.vue')
      },
      {
        path: 'task-monitor',
        name: 'TaskMonitor',
        component: () => import('../views/TaskMonitor.vue')
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

  next()
})

export default router