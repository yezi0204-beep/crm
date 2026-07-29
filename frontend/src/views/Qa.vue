<template>
  <div class="qa-container">
    <div class="qa-header">
      <div class="qa-title">
        <span class="qa-icon">🤖</span>
        <span>智能助手</span>
      </div>
      <div class="qa-desc">基于您的CRM数据，为您提供智能问答服务</div>
    </div>
    
    <div class="chat-container" ref="chatContainer">
      <div class="message-list">
        <div class="message-item system-message">
          <div class="message-avatar">🤖</div>
          <div class="message-content">
            <div class="message-text">您好！我是您的CRM智能助手。我可以帮您查询客户信息、商机状态、合同数据等。请问有什么可以帮您的？</div>
          </div>
        </div>
        
        <div v-for="msg in messages" :key="msg.id" :class="['message-item', msg.role === 'user' ? 'user-message' : 'assistant-message']">
          <div class="message-avatar">{{ msg.role === 'user' ? '👤' : '🤖' }}</div>
          <div class="message-content">
            <div class="message-text" v-html="msg.content"></div>
            <div class="message-time">{{ msg.time }}</div>
          </div>
        </div>
        
        <div v-if="isLoading" class="message-item assistant-message">
          <div class="message-avatar">🤖</div>
          <div class="message-content">
            <div class="typing-indicator">
              <span class="typing-dot"></span>
              <span class="typing-dot"></span>
              <span class="typing-dot"></span>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <div class="input-container">
      <el-input 
        v-model="inputText" 
        placeholder="输入您的问题..." 
        class="qa-input"
        @keyup.enter="sendMessage"
        :disabled="isLoading"
      />
      <el-button 
        type="primary" 
        class="send-btn" 
        @click="sendMessage"
        :disabled="isLoading || !inputText.trim()"
      >
        <span>发送</span>
        <span>➤</span>
      </el-button>
    </div>
    
    <div class="quick-questions">
      <div class="quick-title">快速提问</div>
      <div class="quick-list">
        <el-button 
          v-for="q in quickQuestions" 
          :key="q" 
          text 
          class="quick-btn"
          @click="askQuickQuestion(q)"
        >
          {{ q }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const messages = ref([])
const inputText = ref('')
const isLoading = ref(false)
const chatContainer = ref(null)

const quickQuestions = [
  '本月有哪些合同即将到期？',
  '待回款金额最高的客户是谁？',
  '最近一周有哪些商机需要跟进？',
  '我负责的客户有多少个？',
  '合同总额最高的项目是哪个？'
]

const formatTime = () => {
  const now = new Date()
  return `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`
}

const scrollToBottom = () => {
  nextTick(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  })
}

const sendMessage = async () => {
  const text = inputText.value.trim()
  if (!text || isLoading.value) return
  
  messages.value.push({
    id: Date.now(),
    role: 'user',
    content: text,
    time: formatTime()
  })
  inputText.value = ''
  isLoading.value = true
  scrollToBottom()
  
  const assistantMsgId = Date.now() + 1
  messages.value.push({
    id: assistantMsgId,
    role: 'assistant',
    content: '',
    time: formatTime()
  })
  
  try {
    const response = await api.post('/qa', { question: text, stream: false }, { timeout: 30000 })
    const msgIndex = messages.value.findIndex(m => m.id === assistantMsgId)
    if (msgIndex !== -1) {
      if (response.code === 200 && response.data?.answer) {
        messages.value[msgIndex].content = response.data.answer
      } else {
        messages.value[msgIndex].content = `抱歉，我暂时无法回答这个问题。错误：${response.message || '未知错误'}`
      }
    }
  } catch (error) {
    const msgIndex = messages.value.findIndex(m => m.id === assistantMsgId)
    if (msgIndex !== -1) {
      messages.value[msgIndex].content = '抱歉，网络连接异常，请稍后再试。'
    }
  }
  
  isLoading.value = false
  scrollToBottom()
}

const askQuickQuestion = (question) => {
  inputText.value = question
  sendMessage()
}

onMounted(() => {
  scrollToBottom()
})
</script>

<style scoped>
.qa-container {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 180px);
  background: white;
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
  overflow: hidden;
}

.qa-header {
  padding: 24px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.qa-title {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 24px;
  font-weight: bold;
}

.qa-icon {
  font-size: 32px;
}

.qa-desc {
  margin-top: 8px;
  font-size: 14px;
  opacity: 0.8;
}

.chat-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  background: #f8fafc;
}

.message-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.message-item {
  display: flex;
  gap: 12px;
}

.system-message {
  justify-content: center;
}

.system-message .message-content {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-radius: 16px;
  padding: 12px 20px;
  max-width: 80%;
}

.system-message .message-text {
  font-size: 14px;
  line-height: 1.6;
}

.user-message {
  align-self: flex-end;
}

.user-message .message-content {
  background: linear-gradient(135deg, #4ecdc4 0%, #44a08d 100%);
  color: white;
  border-radius: 16px 16px 4px 16px;
}

.assistant-message .message-content {
  background: white;
  border-radius: 16px 16px 16px 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.message-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}

.message-content {
  padding: 12px 16px;
  max-width: 70%;
}

.message-text {
  font-size: 14px;
  line-height: 1.6;
  color: #334155;
}

.user-message .message-text {
  color: white;
}

.message-time {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 6px;
  text-align: right;
}

.user-message .message-time {
  color: rgba(255, 255, 255, 0.7);
}

.typing-indicator {
  display: flex;
  gap: 6px;
  padding: 12px 16px;
}

.typing-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #94a3b8;
  animation: typing 1.4s infinite ease-in-out;
}

.typing-dot:nth-child(1) { animation-delay: 0s; }
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
  0%, 80%, 100% { transform: scale(0.8); opacity: 0.5; }
  40% { transform: scale(1); opacity: 1; }
}

.input-container {
  display: flex;
  gap: 12px;
  padding: 16px 24px;
  background: white;
  border-top: 1px solid #e2e8f0;
}

.qa-input {
  flex: 1;
}

.send-btn {
  border-radius: 8px;
  padding: 0 24px;
}

.quick-questions {
  padding: 16px 24px;
  background: #f8fafc;
  border-top: 1px solid #e2e8f0;
}

.quick-title {
  font-size: 12px;
  color: #94a3b8;
  margin-bottom: 12px;
}

.quick-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.quick-btn {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 20px;
  padding: 6px 16px;
  font-size: 13px;
  color: #64748b;
}

.quick-btn:hover {
  background: #f1f5f9;
  border-color: #cbd5e1;
}

::-webkit-scrollbar {
  width: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}
</style>