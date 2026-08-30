import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const instance = axios.create({
  baseURL: '/api',
  timeout: 30000
})

// 抓取类请求需要更长的超时（LLM 调用可能数分钟）
const longInstance = axios.create({
  baseURL: '/api',
  timeout: 600000
})

// 统一处理登录态失效：清除本地凭证并跳转登录页
function handleUnauthorized() {
  localStorage.removeItem('crm_token')
  localStorage.removeItem('crm_role')
  const auth = useAuthStore()
  if (auth && typeof auth.logout === 'function') {
    try { auth.logout() } catch (e) { /* ignore */ }
  }
  // 避免在登录页反复跳转
  if (!window.location.pathname.startsWith('/login')) {
    ElMessage.warning('登录已过期，请重新登录')
    window.location.href = '/login'
  }
}

// 统一响应错误处理（两个实例共用）
function handleResponseError(error) {
  if (error.response) {
    // HTTP 层 401：token 缺失/过期
    if (error.response.status === 401) {
      handleUnauthorized()
      return { code: 401, message: '登录已过期', data: null }
    }
    // 业务层 401（后端 token_required 返回 200 + code 401）
    if (error.response.data && error.response.data.code === 401) {
      handleUnauthorized()
      return error.response.data
    }
    if (error.response.data && error.response.data.code === 403) {
      ElMessage.error(error.response.data.message || '权限不足')
    }
    if (error.response.data) {
      return error.response.data
    }
    return { code: error.response.status, message: '请求失败', data: null }
  }
  return { code: 500, message: '网络错误', data: null }
}

longInstance.interceptors.request.use(
  config => {
    const token = localStorage.getItem('crm_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  error => Promise.reject(error)
)

longInstance.interceptors.response.use(
  response => response.data,
  error => handleResponseError(error)
)

instance.interceptors.request.use(
  config => {
    const token = localStorage.getItem('crm_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 成功响应中也可能携带业务层 code=401（后端部分接口 HTTP 200 + code 401）
function checkBusinessCode(data) {
  if (data && data.code === 401) {
    handleUnauthorized()
  }
  return data
}

instance.interceptors.response.use(
  response => checkBusinessCode(response.data),
  error => handleResponseError(error)
)

export default {
  get: (url, params, config) => instance.get(url, { params, ...config }),
  post: (url, data, config) => instance.post(url, data, config),
  put: (url, data, config) => instance.put(url, data, config),
  delete: (url, config) => instance.delete(url, config),
  // 长超时请求（用于抓取等耗时操作，10分钟超时）
  longPost: (url, data, config) => longInstance.post(url, data, config),
  longGet: (url, params, config) => longInstance.get(url, { params, ...config }),
}