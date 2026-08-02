<template>
  <div class="qa-container">
    <div class="qa-header">
      <div class="qa-title">
        <span class="qa-icon">🤖</span>
        <span>智能助手</span>
      </div>
      <div class="qa-desc">对话式交互：智能问答 / 语音汇报自动录入 CRM</div>
      <div class="mode-tabs">
        <div :class="['mode-tab', mode === 'qa' ? 'active' : '']" @click="switchMode('qa')">
          <span>💬</span><span>智能问答</span>
        </div>
        <div :class="['mode-tab', mode === 'agent' ? 'active' : '']" @click="switchMode('agent')">
          <span>✍️</span><span>对话录入</span>
        </div>
      </div>
    </div>

    <div class="chat-container" ref="chatContainer">
      <div class="message-list">
        <div class="message-item system-message">
          <div class="message-avatar">🤖</div>
          <div class="message-content">
            <div class="message-text" v-if="mode === 'qa'">您好！我是 CRM 智能助手，可以查询客户、商机、合同、回款等数据，回答将逐字显示。</div>
            <div class="message-text" v-else>您好！请用自然语言或语音汇报您的跟进、拜访或商机进展，我会自动识别并录入 CRM。例如：<i>"今天拜访了江阴科技，客户对方案满意，概率提升到60%"</i></div>
          </div>
        </div>

        <template v-for="msg in messages" :key="msg.id">
          <div :class="['message-item', msg.role === 'user' ? 'user-message' : 'assistant-message']">
            <div class="message-avatar">{{ msg.role === 'user' ? '👤' : '🤖' }}</div>
            <div class="message-content">
              <div class="message-text" v-html="msg.content"></div>
              <div class="message-time">{{ msg.time }}</div>
            </div>
          </div>

          <!-- 确认卡片：对话录入待确认时展示 -->
          <div v-if="msg.type === 'confirm'" class="confirm-card" :key="'c'+msg.id">
            <div class="confirm-header">
              <span class="confirm-icon">{{ intentIcon(msg.intent) }}</span>
              <span class="confirm-title">{{ intentLabel(msg.intent) }}</span>
              <span class="confirm-status pending">{{ msg.confirmData.status === 'pending' ? '待确认' : '已执行' }}</span>
            </div>
            <div class="confirm-body">
              <div class="confirm-reason" v-if="msg.confirmData.pending_reason">{{ msg.confirmData.pending_reason }}</div>

              <!-- 客户选择（匹配到多个） -->
              <div class="confirm-field" v-if="msg.confirmData.matched_customers && msg.confirmData.matched_customers.length">
                <label>选择客户</label>
                <el-select v-model="msg.editEntities.cust_id" placeholder="请选择目标客户" size="small" style="width:100%">
                  <el-option v-for="c in msg.confirmData.matched_customers" :key="c.id" :label="`${c.company || c.name}`" :value="c.id" />
                </el-select>
              </div>

              <!-- 商机选择（匹配到多个） -->
              <div class="confirm-field" v-if="msg.confirmData.matched_business && msg.confirmData.matched_business.length">
                <label>选择商机</label>
                <el-select v-model="msg.editEntities.business_id" placeholder="请选择目标商机" size="small" style="width:100%">
                  <el-option v-for="b in msg.confirmData.matched_business" :key="b.id" :label="b.title" :value="b.id" />
                </el-select>
              </div>

              <!-- 通用字段编辑 -->
              <div class="confirm-field" v-if="msg.editEntities.customer_name !== undefined && !msg.confirmData.matched_customers">
                <label>客户/公司名</label>
                <el-input v-model="msg.editEntities.customer_name" size="small" />
              </div>
              <div class="confirm-field" v-if="msg.editEntities.content !== undefined">
                <label>跟进内容</label>
                <el-input v-model="msg.editEntities.content" type="textarea" :rows="2" size="small" />
              </div>
              <div class="confirm-field" v-if="msg.editEntities.next_plan !== undefined">
                <label>下一步计划</label>
                <el-input v-model="msg.editEntities.next_plan" size="small" />
              </div>
              <div class="confirm-field" v-if="msg.editEntities.probability !== undefined">
                <label>概率（0-100）</label>
                <el-input-number v-model="msg.editEntities.probability" :min="0" :max="100" size="small" controls-position="right" style="width:100%" />
              </div>
              <div class="confirm-field" v-if="msg.editEntities.stage !== undefined">
                <label>阶段</label>
                <el-select v-model="msg.editEntities.stage" size="small" style="width:100%">
                  <el-option v-for="s in stages" :key="s" :label="s" :value="s" />
                </el-select>
              </div>
              <div class="confirm-field" v-if="msg.editEntities.contact_name !== undefined && msg.intent === 'create_customer'">
                <label>联系人</label>
                <el-input v-model="msg.editEntities.contact_name" size="small" />
              </div>
              <div class="confirm-field" v-if="msg.editEntities.phone !== undefined && msg.intent === 'create_customer'">
                <label>电话</label>
                <el-input v-model="msg.editEntities.phone" size="small" />
              </div>
            </div>
            <div class="confirm-actions" v-if="msg.confirmData.status === 'pending'">
              <el-button type="primary" size="small" @click="confirmExecute(msg)" :loading="msg.executing">确认执行</el-button>
              <el-button size="small" @click="cancelConfirm(msg)">取消</el-button>
            </div>
          </div>
        </template>

        <div v-if="isLoading" class="message-item assistant-message">
          <div class="message-avatar">🤖</div>
          <div class="message-content">
            <div class="typing-indicator">
              <span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="input-container">
      <el-input
        v-model="inputText"
        :placeholder="mode === 'qa' ? '输入您的问题...' : '汇报您的跟进/拜访/商机进展...'"
        class="qa-input"
        @keyup.enter="sendMessage"
        :disabled="isLoading"
        type="textarea"
        :autosize="{ minRows: 1, maxRows: 4 }"
        resize="none"
      />
      <div
        v-if="speechSupported"
        :class="['voice-btn', { recording: isRecording }]"
        @click="toggleVoice"
        :title="isRecording ? '停止录音' : '语音输入'"
      >
        <span>{{ isRecording ? '⏹' : '🎤' }}</span>
      </div>
      <el-button type="primary" class="send-btn" @click="sendMessage" :disabled="isLoading || !inputText.trim()">
        <span>发送</span><span>➤</span>
      </el-button>
    </div>

    <div class="quick-questions">
      <div class="quick-title">{{ mode === 'qa' ? '快速提问' : '汇报示例' }}</div>
      <div class="quick-list">
        <el-button v-for="q in currentQuickQuestions" :key="q" text class="quick-btn" @click="askQuickQuestion(q)">
          {{ q }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const messages = ref([])
const inputText = ref('')
const isLoading = ref(false)
const chatContainer = ref(null)
const mode = ref('qa') // 'qa' | 'agent'
const isRecording = ref(false)
const speechSupported = ref(false)
let recognition = null

const stages = ['引导需求', '能力展示', '方案确定', '商务谈判', '合同签订', '销售实现']

const qaQuickQuestions = [
  '本月有哪些合同即将到期？',
  '待回款金额最高的客户是谁？',
  '最近一周有哪些商机需要跟进？',
  '我负责的客户有多少个？',
  '合同总额最高的项目是哪个？'
]
const agentQuickQuestions = [
  '今天拜访了江阴科技，客户对方案满意，下周提供报价',
  '新增客户：航天信息科技，联系人张总，电话13800000000',
  '银河航天商机概率提升到80%，进入商务谈判阶段',
  '跟进了中国电科客户，对方要求下周提供详细报价单'
]
const currentQuickQuestions = computed(() => mode.value === 'qa' ? qaQuickQuestions : agentQuickQuestions)

const intentLabel = (intent) => ({
  create_follow_log: '创建跟进记录',
  create_customer: '新增客户',
  update_business: '更新商机'
}[intent] || '操作')
const intentIcon = (intent) => ({
  create_follow_log: '📝',
  create_customer: '👥',
  update_business: '🎯'
}[intent] || '⚡')

const formatTime = () => {
  const n = new Date()
  return `${n.getHours().toString().padStart(2, '0')}:${n.getMinutes().toString().padStart(2, '0')}`
}

const scrollToBottom = () => {
  nextTick(() => {
    if (chatContainer.value) chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  })
}

const switchMode = (m) => {
  if (mode.value === m) return
  mode.value = m
}

// ==================== 语音输入 ====================
const initSpeech = () => {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition
  if (!SR) { speechSupported.value = false; return }
  speechSupported.value = true
  recognition = new SR()
  recognition.lang = 'zh-CN'
  recognition.continuous = false
  recognition.interimResults = false
  recognition.onresult = (e) => {
    const text = e.results[0][0].transcript
    inputText.value = (inputText.value ? inputText.value + ' ' : '') + text
  }
  recognition.onerror = (e) => {
    ElMessage.error('语音识别失败：' + (e.error || '未知错误'))
    isRecording.value = false
  }
  recognition.onend = () => { isRecording.value = false }
}

const toggleVoice = () => {
  if (!recognition) return
  if (isRecording.value) {
    recognition.stop()
    isRecording.value = false
  } else {
    try {
      recognition.start()
      isRecording.value = true
      ElMessage.info('正在录音，请说话...')
    } catch (e) {
      ElMessage.error('启动录音失败')
    }
  }
}

// ==================== 发送消息 ====================
const sendMessage = async () => {
  const text = inputText.value.trim()
  if (!text || isLoading.value) return

  messages.value.push({ id: Date.now(), role: 'user', type: 'text', content: text, time: formatTime() })
  inputText.value = ''
  isLoading.value = true
  scrollToBottom()

  if (mode.value === 'qa') {
    await sendQA(text)
  } else {
    await sendAgent(text)
  }
  isLoading.value = false
  scrollToBottom()
}

// 智能问答：流式输出
const sendQA = async (text) => {
  const assistantMsgId = Date.now() + 1
  messages.value.push({ id: assistantMsgId, role: 'assistant', type: 'text', content: '', time: formatTime() })

  const token = localStorage.getItem('crm_token')
  try {
    const resp = await fetch('/api/ai/agent/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ text })
    })
    if (!resp.ok) throw new Error('网络错误')
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let received = false
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data:')) continue
        const payload = line.slice(5).trim()
        if (payload === '[DONE]') continue
        try {
          const data = JSON.parse(payload)
          if (data.answer) {
            received = true
            const idx = messages.value.findIndex(m => m.id === assistantMsgId)
            if (idx !== -1) messages.value[idx].content += data.answer
            scrollToBottom()
          }
        } catch (e) { /* ignore */ }
      }
    }
    const idx = messages.value.findIndex(m => m.id === assistantMsgId)
    if (idx !== -1 && !received) {
      messages.value[idx].content = '抱歉，暂未启用大语言模型或未能获取回答。'
    }
  } catch (e) {
    const idx = messages.value.findIndex(m => m.id === assistantMsgId)
    if (idx !== -1) messages.value[idx].content = '抱歉，网络连接异常，请稍后再试。'
  }
}

// 对话录入：识别意图 + 确认卡片 + 执行
const sendAgent = async (text) => {
  try {
    const resp = await api.post('/ai/agent', { text, confirm: false }, { timeout: 30000 })
    if (resp.code !== 200) {
      messages.value.push({ id: Date.now() + 2, role: 'assistant', type: 'text', content: `操作失败：${resp.message}`, time: formatTime() })
      return
    }
    const d = resp.data
    // 已直接执行或查询
    if (d.status === 'executed') {
      messages.value.push({ id: Date.now() + 2, role: 'assistant', type: 'text', content: d.reply || '操作已完成。', time: formatTime() })
      return
    }
    // 待确认：展示确认卡片
    if (d.status === 'pending') {
      const editEntities = { ...d.entities }
      // 若有候选客户/商机，预置选择字段
      if (d.data && d.data.matched_customers) editEntities.cust_id = null
      if (d.data && d.data.matched_business) editEntities.business_id = null
      messages.value.push({
        id: Date.now() + 2,
        role: 'assistant',
        type: 'confirm',
        content: d.reply || '请确认以下信息后执行：',
        time: formatTime(),
        intent: d.intent,
        confirmData: { status: 'pending', ...d.data, pending_reason: (d.data && d.data.pending_reason) || '' },
        editEntities,
        executing: false
      })
      return
    }
    // none / failed
    messages.value.push({ id: Date.now() + 2, role: 'assistant', type: 'text', content: d.reply || '未能识别您的操作意图。', time: formatTime() })
  } catch (e) {
    messages.value.push({ id: Date.now() + 2, role: 'assistant', type: 'text', content: '请求异常，请稍后再试。', time: formatTime() })
  }
}

// 确认执行
const confirmExecute = async (msg) => {
  msg.executing = true
  try {
    const resp = await api.post('/ai/agent', {
      text: msg.editEntities.content || msg.content,
      confirm: true,
      intent: msg.intent,
      entities: msg.editEntities
    }, { timeout: 30000 })
    if (resp.code === 200 && resp.data.status === 'executed') {
      msg.confirmData.status = 'executed'
      messages.value.push({ id: Date.now() + 3, role: 'assistant', type: 'text', content: resp.data.reply || '执行成功！', time: formatTime() })
    } else {
      ElMessage.error(resp.data?.error || resp.message || '执行失败')
    }
  } catch (e) {
    ElMessage.error('执行请求异常')
  } finally {
    msg.executing = false
    scrollToBottom()
  }
}

const cancelConfirm = (msg) => {
  msg.confirmData.status = 'cancelled'
  messages.value.push({ id: Date.now() + 4, role: 'assistant', type: 'text', content: '已取消本次操作。', time: formatTime() })
  scrollToBottom()
}

const askQuickQuestion = (question) => {
  inputText.value = question
  sendMessage()
}

onMounted(() => {
  initSpeech()
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
  padding: 20px 24px 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.qa-title { display: flex; align-items: center; gap: 12px; font-size: 22px; font-weight: bold; }
.qa-icon { font-size: 28px; }
.qa-desc { margin-top: 6px; font-size: 13px; opacity: 0.85; }

.mode-tabs {
  display: flex;
  gap: 8px;
  margin-top: 14px;
}
.mode-tab {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 18px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.15);
  cursor: pointer;
  font-size: 13px;
  transition: all 0.25s ease;
}
.mode-tab:hover { background: rgba(255, 255, 255, 0.25); }
.mode-tab.active { background: white; color: #667eea; font-weight: 600; }

.chat-container { flex: 1; overflow-y: auto; padding: 24px; background: #f8fafc; }
.message-list { display: flex; flex-direction: column; gap: 16px; }

.message-item { display: flex; gap: 12px; }
.system-message { justify-content: center; }
.system-message .message-content {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white; border-radius: 16px; padding: 12px 20px; max-width: 80%;
}
.system-message .message-text { font-size: 14px; line-height: 1.6; }

.user-message { align-self: flex-end; }
.user-message .message-content {
  background: linear-gradient(135deg, #4ecdc4 0%, #44a08d 100%);
  color: white; border-radius: 16px 16px 4px 16px;
}
.assistant-message .message-content {
  background: white; border-radius: 16px 16px 16px 4px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}
.message-avatar {
  width: 40px; height: 40px; border-radius: 50%; background: #e2e8f0;
  display: flex; align-items: center; justify-content: center; font-size: 18px; flex-shrink: 0;
}
.message-content { padding: 12px 16px; max-width: 70%; }
.message-text { font-size: 14px; line-height: 1.6; color: #334155; }
.user-message .message-text { color: white; }
.message-time { font-size: 11px; color: #94a3b8; margin-top: 6px; text-align: right; }
.user-message .message-time { color: rgba(255, 255, 255, 0.7); }

/* 确认卡片 */
.confirm-card {
  margin-left: 52px;
  background: white;
  border: 1px solid #e2e8f0;
  border-left: 4px solid #667eea;
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.1);
}
.confirm-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.confirm-icon { font-size: 18px; }
.confirm-title { font-size: 15px; font-weight: 600; color: #334155; }
.confirm-status { margin-left: auto; font-size: 11px; padding: 3px 10px; border-radius: 10px; }
.confirm-status.pending { background: #fef3c7; color: #d97706; }
.confirm-status.executed { background: #d1fae5; color: #059669; }
.confirm-status.cancelled { background: #f1f5f9; color: #94a3b8; }
.confirm-reason { font-size: 12px; color: #d97706; background: #fffbeb; padding: 8px 12px; border-radius: 6px; margin-bottom: 12px; }
.confirm-body { display: flex; flex-direction: column; gap: 10px; }
.confirm-field { display: flex; flex-direction: column; gap: 4px; }
.confirm-field label { font-size: 12px; color: #64748b; font-weight: 500; }
.confirm-actions { display: flex; gap: 8px; margin-top: 14px; }

.typing-indicator { display: flex; gap: 6px; padding: 12px 16px; }
.typing-dot { width: 8px; height: 8px; border-radius: 50%; background: #94a3b8; animation: typing 1.4s infinite ease-in-out; }
.typing-dot:nth-child(1) { animation-delay: 0s; }
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes typing { 0%, 80%, 100% { transform: scale(0.8); opacity: 0.5; } 40% { transform: scale(1); opacity: 1; } }

.input-container { display: flex; gap: 10px; padding: 16px 24px; background: white; border-top: 1px solid #e2e8f0; align-items: flex-end; }
.qa-input { flex: 1; }
.voice-btn {
  width: 42px; height: 42px; border-radius: 10px; background: #f1f5f9;
  display: flex; align-items: center; justify-content: center; cursor: pointer; font-size: 20px;
  transition: all 0.25s ease; flex-shrink: 0;
}
.voice-btn:hover { background: #e2e8f0; }
.voice-btn.recording { background: #fee2e2; animation: pulse 1.2s infinite; }
@keyframes pulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); } 50% { box-shadow: 0 0 0 8px rgba(239, 68, 68, 0); } }
.send-btn { border-radius: 8px; padding: 0 22px; height: 42px; }

.quick-questions { padding: 14px 24px; background: #f8fafc; border-top: 1px solid #e2e8f0; }
.quick-title { font-size: 12px; color: #94a3b8; margin-bottom: 10px; }
.quick-list { display: flex; flex-wrap: wrap; gap: 8px; }
.quick-btn { background: white; border: 1px solid #e2e8f0; border-radius: 20px; padding: 6px 14px; font-size: 12px; color: #64748b; height: auto; }
.quick-btn:hover { background: #f1f5f9; border-color: #cbd5e1; }

::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
</style>
