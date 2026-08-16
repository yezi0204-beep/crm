import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './styles/table.css'
import './styles/responsive.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(ElementPlus)

// 应用启动时恢复用户偏好（语言、主题、字号）
const savedLang = localStorage.getItem('crm_language')
const savedTheme = localStorage.getItem('crm_theme')
const savedFontSize = localStorage.getItem('crm_font_size')
if (savedLang) document.documentElement.setAttribute('lang', savedLang)
if (savedTheme) document.documentElement.setAttribute('data-theme', savedTheme)
if (savedFontSize) document.documentElement.setAttribute('data-font-size', savedFontSize)

app.mount('#app')