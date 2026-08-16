import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api'
import { translate, availableLocales } from '../locales'

export const useSettingsStore = defineStore('settings', () => {
  const language = ref(localStorage.getItem('crm_language') || 'zh-CN')
  const timezone = ref(localStorage.getItem('crm_timezone') || 'Asia/Shanghai')
  const theme = ref(localStorage.getItem('crm_theme') || 'light')
  const fontSize = ref(localStorage.getItem('crm_font_size') || 'medium')
  const loaded = ref(false)

  // 翻译函数
  const t = (key, params = null) => translate(language.value, key, params)

  // 当前语言信息
  const currentLocale = computed(() =>
    availableLocales.find(l => l.value === language.value) || availableLocales[0]
  )

  // 加载用户偏好
  const loadPreferences = async () => {
    try {
      const res = await api.get('/system/preferences')
      if (res.code === 200 && res.data) {
        const d = res.data
        setLanguage(d.language || 'zh-CN')
        setTimezone(d.timezone || 'Asia/Shanghai')
        setTheme(d.theme || 'light')
        setFontSize(d.font_size || 'medium')
        loaded.value = true
      }
    } catch (e) {
      console.error('加载偏好设置失败', e)
    }
  }

  // 保存偏好到后端
  const savePreferences = async (data = {}) => {
    try {
      const payload = {
        language: language.value,
        timezone: timezone.value,
        theme: theme.value,
        font_size: fontSize.value,
        ...data
      }
      const res = await api.put('/system/preferences', payload)
      return res
    } catch (e) {
      console.error('保存偏好设置失败', e)
      return { code: 500, message: '保存失败' }
    }
  }

  const setLanguage = (lang) => {
    language.value = lang
    localStorage.setItem('crm_language', lang)
    document.documentElement.setAttribute('lang', lang)
  }

  const setTimezone = (tz) => {
    timezone.value = tz
    localStorage.setItem('crm_timezone', tz)
  }

  const setTheme = (t) => {
    theme.value = t
    localStorage.setItem('crm_theme', t)
    document.documentElement.setAttribute('data-theme', t)
  }

  const setFontSize = (size) => {
    fontSize.value = size
    localStorage.setItem('crm_font_size', size)
    document.documentElement.setAttribute('data-font-size', size)
  }

  return {
    language,
    timezone,
    theme,
    fontSize,
    loaded,
    t,
    currentLocale,
    availableLocales,
    loadPreferences,
    savePreferences,
    setLanguage,
    setTimezone,
    setTheme,
    setFontSize
  }
})
