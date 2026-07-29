<template>
  <div class="login-container">
    <div class="bg-decoration">
      <div class="deco-circle c1"></div>
      <div class="deco-circle c2"></div>
      <div class="deco-circle c3"></div>
    </div>
    
    <div class="login-box">
      <div class="logo-section">
        <div class="logo-wrapper">
          <div class="logo">🚀</div>
        </div>
        <h1>天地信息网络研究院CRM</h1>
        <p>欢迎登录客户关系管理系统</p>
        <div class="features">
          <span class="feature-item">📊 数据驱动</span>
          <span class="feature-item">🔄 全流程</span>
          <span class="feature-item">👥 团队协作</span>
        </div>
      </div>
      
      <el-form :model="form" :rules="rules" ref="formRef" class="login-form">
        <el-form-item prop="username">
          <div class="input-wrapper">
            <span class="input-icon">👤</span>
            <el-input 
              v-model="form.username" 
              placeholder="请输入账号" 
              size="large"
              class="custom-input"
            />
          </div>
        </el-form-item>
        
        <el-form-item prop="password">
          <div class="input-wrapper">
            <span class="input-icon">🔒</span>
            <el-input 
              v-model="form.password" 
              type="password" 
              placeholder="请输入密码" 
              size="large"
              class="custom-input"
              show-password
            />
          </div>
        </el-form-item>
        
        <div class="form-options">
          <el-checkbox v-model="rememberMe">记住我</el-checkbox>
          <a href="#" class="forgot-link">忘记密码？</a>
        </div>
        
        <el-form-item>
          <el-button 
            type="primary" 
            size="large" 
            class="login-btn"
            :loading="loading"
            @click="handleLogin"
          >
            <span>进入系统</span>
            <span class="arrow">→</span>
          </el-button>
        </el-form-item>
      </el-form>
      
      <div class="footer">
        <span>© 2026 天地信息网络研究院 | 客户关系管理系统</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { ElMessage } from 'element-plus'

const router = useRouter()
const authStore = useAuthStore()
const loading = ref(false)
const rememberMe = ref(false)

const form = reactive({
  username: '',
  password: ''
})

const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

const handleLogin = async () => {
  loading.value = true
  
  try {
    const result = await authStore.login(form.username, form.password)
    
    if (result.success) {
      ElMessage.success('登录成功')
      router.push('/dashboard')
    } else {
      ElMessage.error(result.message || '账号或密码错误')
    }
  } catch (error) {
    ElMessage.error('登录失败，请重试')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
  position: relative;
  overflow: hidden;
}

.bg-decoration {
  position: absolute;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.deco-circle {
  position: absolute;
  border-radius: 50%;
  opacity: 0.15;
}

.c1 {
  width: 400px;
  height: 400px;
  background: linear-gradient(135deg, #4ecdc4 0%, #44a08d 100%);
  top: -100px;
  left: -100px;
  animation: float 6s ease-in-out infinite;
}

.c2 {
  width: 300px;
  height: 300px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  bottom: -50px;
  right: -50px;
  animation: float 8s ease-in-out infinite reverse;
}

.c3 {
  width: 200px;
  height: 200px;
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  animation: float 5s ease-in-out infinite;
}

@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-20px); }
}

.login-box {
  width: 440px;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(20px);
  border-radius: 24px;
  padding: 48px 44px;
  box-shadow: 0 25px 80px rgba(0, 0, 0, 0.4);
  position: relative;
  z-index: 1;
  animation: slideUp 0.6s ease-out;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.logo-section {
  text-align: center;
  margin-bottom: 36px;
}

.logo-wrapper {
  width: 80px;
  height: 80px;
  border-radius: 24px;
  background: linear-gradient(135deg, #4ecdc4 0%, #44a08d 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 20px;
  box-shadow: 0 8px 24px rgba(78, 205, 196, 0.4);
}

.logo {
  font-size: 40px;
}

.logo-section h1 {
  font-size: 24px;
  color: #1a1a2e;
  margin: 0 0 8px 0;
  font-weight: 700;
}

.logo-section p {
  font-size: 14px;
  color: #666;
  margin: 0 0 20px 0;
}

.features {
  display: flex;
  justify-content: center;
  gap: 16px;
}

.feature-item {
  font-size: 12px;
  color: #999;
  padding: 6px 12px;
  background: rgba(0, 0, 0, 0.04);
  border-radius: 12px;
}

.login-form {
  width: 100%;
}

.input-wrapper {
  display: flex;
  align-items: center;
  background: rgba(0, 0, 0, 0.03);
  border-radius: 12px;
  padding: 0 16px;
  border: 2px solid transparent;
  transition: all 0.3s ease;
}

.input-wrapper:focus-within {
  border-color: #4ecdc4;
  background: rgba(78, 205, 196, 0.05);
}

.input-icon {
  font-size: 18px;
  margin-right: 12px;
  color: #999;
}

.custom-input {
  flex: 1;
}

:deep(.el-input__wrapper) {
  background: transparent !important;
  box-shadow: none !important;
}

:deep(.el-input__inner) {
  font-size: 15px;
}

.form-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.forgot-link {
  font-size: 13px;
  color: #4ecdc4;
  text-decoration: none;
}

.forgot-link:hover {
  text-decoration: underline;
}

.login-btn {
  width: 100%;
  height: 52px;
  font-size: 16px;
  font-weight: 600;
  background: linear-gradient(135deg, #4ecdc4 0%, #44a08d 100%);
  border: none;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.3s ease;
}

.login-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(78, 205, 196, 0.4);
}

.arrow {
  transition: transform 0.3s ease;
}

.login-btn:hover:not(:disabled) .arrow {
  transform: translateX(4px);
}

.footer {
  text-align: center;
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}

.footer span {
  font-size: 12px;
  color: #999;
}
</style>