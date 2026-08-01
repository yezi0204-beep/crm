import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('crm_token') || '')
  const username = ref('')
  const name = ref('')
  const role = ref('')
  const roles = ref([])
  const department = ref(localStorage.getItem('crm_department') || '')
  const isLoggedIn = ref(false)

  const login = async (usernameInput, password) => {
    try {
      const response = await api.post('/auth/login', {
        username: usernameInput,
        password
      })

      if (response.code === 200) {
        token.value = response.data.token
        username.value = response.data.username
        name.value = response.data.name
        role.value = response.data.role
        isLoggedIn.value = true

        localStorage.setItem('crm_token', token.value)
        localStorage.setItem('crm_username', username.value)
        localStorage.setItem('crm_name', name.value)
        localStorage.setItem('crm_role', role.value)

        await getUserInfo()

        return { success: true }
      }
      return { success: false, message: response.message || '登录失败' }
    } catch (error) {
      let message = '登录失败，请重试'
      if (error.response?.data?.message) {
        message = error.response.data.message
      } else if (error.message) {
        message = error.message
      }
      return { success: false, message }
    }
  }

  const getUserInfo = async () => {
    try {
      const response = await api.get('/auth/info')
      if (response.code === 200) {
        username.value = response.data.username
        name.value = response.data.name
        role.value = response.data.role
        roles.value = response.data.roles
        department.value = response.data.department || ''
        isLoggedIn.value = true
        localStorage.setItem('crm_department', department.value)
      }
    } catch (error) {
      logout()
    }
  }

  const checkLogin = async () => {
    const savedToken = localStorage.getItem('crm_token')
    if (savedToken) {
      token.value = savedToken
      username.value = localStorage.getItem('crm_username') || ''
      name.value = localStorage.getItem('crm_name') || ''
      role.value = localStorage.getItem('crm_role') || ''
      isLoggedIn.value = true
      try {
        await getUserInfo()
      } catch (error) {
        logout()
      }
    }
  }

  const logout = () => {
    token.value = ''
    username.value = ''
    name.value = ''
    role.value = ''
    roles.value = []
    department.value = ''
    isLoggedIn.value = false

    localStorage.removeItem('crm_token')
    localStorage.removeItem('crm_username')
    localStorage.removeItem('crm_name')
    localStorage.removeItem('crm_role')
    localStorage.removeItem('crm_department')
  }

  return {
    token,
    username,
    name,
    role,
    roles,
    department,
    isLoggedIn,
    login,
    getUserInfo,
    checkLogin,
    logout
  }
})