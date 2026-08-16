/**
 * i18n 国际化入口
 * 轻量级实现，无需 vue-i18n 依赖
 */
import zhCN from './zh-CN.js'
import enUS from './en-US.js'

const messages = {
  'zh-CN': zhCN,
  'en-US': enUS
}

/**
 * 根据 key 路径（如 'layout.systemName'）获取翻译文本
 * @param {string} locale - 语言代码 'zh-CN' / 'en-US'
 * @param {string} key - 点分路径，如 'menu.dashboard'
 * @param {object} params - 可选的插值参数
 * @returns {string}
 */
export function translate(locale, key, params = null) {
  const msg = messages[locale] || messages['zh-CN']
  const keys = key.split('.')
  let result = msg
  for (const k of keys) {
    if (result && typeof result === 'object' && k in result) {
      result = result[k]
    } else {
      // 找不到则回退到中文，再找不到返回 key 本身
      const fallback = messages['zh-CN']
      let fb = fallback
      for (const fk of keys) {
        if (fb && typeof fb === 'object' && fk in fb) {
          fb = fb[fk]
        } else {
          return key
        }
      }
      result = fb
      break
    }
  }
  if (typeof result !== 'string') return key
  // 简单插值：替换 {name}
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      result = result.replace(new RegExp(`\\{${k}\\}`, 'g'), v)
    })
  }
  return result
}

export const availableLocales = [
  { value: 'zh-CN', label: '中文', flag: '🇨🇳' },
  { value: 'en-US', label: 'English', flag: '🇺🇸' }
]

export default messages
