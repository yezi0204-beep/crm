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
  
  if (authStore.isLoggedIn) {
    next()
  } else {
    next('/login')
  }
})

export default router