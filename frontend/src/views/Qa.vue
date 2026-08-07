<template>
  <div class="qa-container">
    <div class="qa-header">
      <div class="qa-title">
        <span class="qa-icon">🤖</span>
        <span>智能助手</span>
      </div>
      <div class="qa-desc">智能问答 / 对话录入 / 智能决策</div>
      <div class="mode-tabs">
        <div :class="['mode-tab', mode === 'qa' ? 'active' : '']" @click="switchMode('qa')">
          <span>💬</span><span>智能问答</span>
        </div>
        <div :class="['mode-tab', mode === 'agent' ? 'active' : '']" @click="switchMode('agent')">
          <span>✍️</span><span>对话录入</span>
        </div>
        <div :class="['mode-tab', mode === 'decision' ? 'active' : '']" @click="switchMode('decision')">
          <span>🎯</span><span>智能决策</span>
        </div>
      </div>
    </div>

    <!-- 智能问答 / 对话录入 模式 -->
    <div v-if="mode !== 'decision'" class="chat-container" ref="chatContainer">
      <div class="message-list">
        <div class="message-item system-message">
          <div class="message-avatar">🤖</div>
          <div class="message-content">
            <div class="message-text" v-if="mode === 'qa'">您好！我是 CRM 智能助手，可以查询客户、商机、合同、回款等数据，回答将逐字显示。</div>
            <div class="message-text" v-else>您好！请用自然语言或语音汇报您的跟进、拜访或商机进展，我会自动识别并录入 CRM。</div>
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

          <div v-if="msg.type === 'confirm'" class="confirm-card" :key="'c'+msg.id">
            <div class="confirm-header">
              <span class="confirm-icon">{{ intentIcon(msg.intent) }}</span>
              <span class="confirm-title">{{ intentLabel(msg.intent) }}</span>
              <span class="confirm-status pending">{{ msg.confirmData.status === 'pending' ? '待确认' : '已执行' }}</span>
            </div>
            <div class="confirm-body">
              <div class="confirm-reason" v-if="msg.confirmData.pending_reason">{{ msg.confirmData.pending_reason }}</div>
              <div class="confirm-field" v-if="msg.confirmData.matched_customers?.length">
                <label>选择客户</label>
                <el-select v-model="msg.editEntities.cust_id" placeholder="请选择目标客户" size="small" style="width:100%">
                  <el-option v-for="c in msg.confirmData.matched_customers" :key="c.id" :label="c.company || c.name" :value="c.id" />
                </el-select>
              </div>
              <div class="confirm-field" v-if="msg.confirmData.matched_business?.length">
                <label>选择商机</label>
                <el-select v-model="msg.editEntities.business_id" placeholder="请选择目标商机" size="small" style="width:100%">
                  <el-option v-for="b in msg.confirmData.matched_business" :key="b.id" :label="b.title" :value="b.id" />
                </el-select>
              </div>
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

    <!-- 智能决策模式 -->
    <div v-else class="decision-container">
      <el-tabs v-model="decisionTab" type="border-card" class="decision-tabs">
        <!-- 负责人推荐 -->
        <el-tab-pane label="👥 负责人推荐" name="owner">
          <div class="decision-form">
            <el-form :model="ownerForm" label-width="110px" size="small">
              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="商机标题">
                    <el-input v-model="ownerForm.business_title" placeholder="商机名称或项目标题" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="所属行业">
                    <el-select v-model="ownerForm.industry" placeholder="选择行业" clearable style="width:100%">
                      <el-option label="软件" value="软件" />
                      <el-option label="硬件" value="硬件" />
                      <el-option label="系统集成" value="系统集成" />
                      <el-option label="服务" value="服务" />
                      <el-option label="金融" value="金融" />
                      <el-option label="政府" value="政府" />
                    </el-select>
                  </el-form-item>
                </el-col>
              </el-row>
              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="商机金额(万)">
                    <el-input v-model="ownerForm.amount" type="number" placeholder="预估金额" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="特殊要求">
                    <el-input v-model="ownerForm.requirements" placeholder="资质、经验等要求" />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-form-item>
                <el-button type="primary" @click="handleRecommend" :loading="recommending">🎯 智能推荐</el-button>
                <el-button @click="resetOwnerForm">重置</el-button>
              </el-form-item>
            </el-form>
          </div>

          <div v-if="ownerResults.length" class="decision-result">
            <h4 class="result-title">🏆 推荐结果</h4>
            <div class="recommend-list">
              <div v-for="item in ownerResults" :key="item.username" class="recommend-card">
                <div class="rank-badge" :class="'rank-' + item.rank">{{ item.rank }}</div>
                <div class="recommend-info">
                  <div class="recommend-header">
                    <span class="recommend-name">{{ item.name }}</span>
                    <el-tag size="small" type="info">{{ item.role }}</el-tag>
                    <span class="score">{{ item.score }}分</span>
                  </div>
                  <div class="recommend-stats">
                    <span>📋 {{ item.total_business }}</span>
                    <span>✅ {{ item.success_rate }}%</span>
                    <span>💰 {{ item.total_amount }}万</span>
                  </div>
                  <div class="recommend-reasons" v-if="item.reasons?.length">
                    <span v-for="(r, i) in item.reasons" :key="i" class="reason-tag">{{ r }}</span>
                  </div>
                </div>
              </div>
            </div>
            <div v-if="ownerLLM" class="llm-analysis">
              <strong>🤖 AI分析：</strong>{{ ownerLLM.final_recommendation || ownerLLM.strategy_notes }}
            </div>
          </div>
        </el-tab-pane>

        <!-- 跟踪策略 -->
        <el-tab-pane label="📋 跟踪策略" name="strategy">
          <div class="decision-form">
            <el-form :model="strategyForm" label-width="110px" size="small">
              <el-form-item label="商机ID">
                <el-input v-model="strategyForm.business_id" type="number" placeholder="输入商机ID" style="width:200px" />
              </el-form-item>
              <el-form-item label="附加上下文">
                <el-input v-model="strategyForm.additional_context" type="textarea" :rows="2" placeholder="最新跟进情况" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="handleStrategy" :loading="strategizing">💡 生成策略</el-button>
              </el-form-item>
            </el-form>
          </div>

          <div v-if="strategyResult" class="decision-result">
            <div class="strategy-summary">
              <div class="summary-item"><span class="label">阶段：</span>{{ strategyResult.current_stage || '-' }}</div>
              <div class="summary-item"><span class="label">概率：</span>{{ strategyResult.current_probability || 0 }}%</div>
            </div>
            <div v-if="strategyResult.base_strategy" class="strategy-base">
              <div class="base-item"><span class="label">重点：</span>{{ strategyResult.base_strategy.focus }}</div>
              <div class="base-item"><span class="label">频率：</span>{{ strategyResult.base_strategy.frequency }}</div>
              <div class="base-item"><span class="label">方式：</span>{{ strategyResult.base_strategy.method }}</div>
            </div>
            <div v-if="strategyResult.action_items?.length" class="action-list">
              <h4>📌 行动计划</h4>
              <div v-for="(a, i) in strategyResult.action_items" :key="i" class="action-item">
                <span :class="['priority', 'p-' + a.priority]">{{ a.priority }}</span>
                <span class="action-text">{{ a.action }}</span>
                <span class="deadline">⏰ {{ a.deadline }}</span>
              </div>
            </div>
            <div v-if="strategyResult.llm_enhancement" class="llm-analysis">
              <strong>🤖 AI建议：</strong>{{ strategyResult.llm_enhancement.enhanced_strategy }}
            </div>
          </div>
        </el-tab-pane>

        <!-- 投标评估 -->
        <el-tab-pane label="📊 投标评估" name="bid">
          <div class="decision-form">
            <el-form :model="bidForm" label-width="110px" size="small">
              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="项目名称">
                    <el-input v-model="bidForm.project_name" placeholder="招标项目名称" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="项目类别">
                    <el-select v-model="bidForm.category" placeholder="选择类别" clearable style="width:100%">
                      <el-option label="软件" value="软件" />
                      <el-option label="硬件" value="硬件" />
                      <el-option label="系统集成" value="系统集成" />
                      <el-option label="服务" value="服务" />
                    </el-select>
                  </el-form-item>
                </el-col>
              </el-row>
              <el-form-item label="招标要求">
                <el-input v-model="bidForm.requirements" type="textarea" :rows="2" placeholder="关键技术要求、资质要求" />
              </el-form-item>
              <el-form-item label="投标内容">
                <el-input v-model="bidForm.bid_content" type="textarea" :rows="3" placeholder="投标文件核心内容摘要" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="handleBidEval" :loading="evaluating">📊 开始评估</el-button>
                <el-button @click="resetBidForm">重置</el-button>
              </el-form-item>
            </el-form>
          </div>

          <div v-if="bidResult" class="decision-result">
            <div class="score-summary">
              <div class="score-ring" :class="'level-' + bidResult.level">
                <div class="score-value">{{ bidResult.total_score }}</div>
                <div class="score-label">{{ bidResult.level }}</div>
              </div>
              <div class="score-info">
                <div class="recommendation">{{ bidResult.recommendation }}</div>
                <div class="dimensions">
                  <span v-for="(d, name) in bidResult.dimensions" :key="name" :class="['dim-tag', d.score >= 75 ? 'good' : d.score >= 60 ? 'mid' : 'low']">
                    {{ name }}: {{ d.score }}
                  </span>
                </div>
              </div>
            </div>
            <div v-if="bidResult.improvement_suggestions?.length" class="suggestions">
              <h4>📝 改进建议</h4>
              <div v-for="(s, i) in bidResult.improvement_suggestions.slice(0, 5)" :key="i" class="suggestion-item">{{ s }}</div>
            </div>
            <div v-if="bidResult.llm_review" class="llm-analysis">
              <strong>🤖 专家评审：</strong>{{ bidResult.llm_review.expert_opinion }}
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 底部输入区 -->
    <div v-if="mode !== 'decision'" class="input-container">
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
      <div v-if="speechSupported" :class="['voice-btn', { recording: isRecording }]" @click="toggleVoice">
        <span>{{ isRecording ? '⏹' : '🎤' }}</span>
      </div>
      <el-button type="primary" class="send-btn" @click="sendMessage" :disabled="isLoading || !inputText.trim()">
        <span>发送</span><span>➤</span>
      </el-button>
    </div>

    <div v-if="mode !== 'decision'" class="quick-questions">
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
import { ref, reactive, nextTick, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

// ========== 基础状态 ==========
const messages = ref([])
const inputText = ref('')
const isLoading = ref(false)
const chatContainer = ref(null)
const mode = ref('qa')
const isRecording = ref(false)
const speechSupported = ref(false)
let recognition = null

const stages = ['引导需求', '能力展示', '方案确定', '商务谈判', '合同签订', '销售实现']

// ========== 智能决策状态 ==========
const decisionTab = ref('owner')
const recommending = ref(false)
const strategizing = ref(false)
const evaluating = ref(false)

const ownerForm = reactive({
  business_title: '', industry: '', amount: '', requirements: ''
})
const ownerResults = ref([])
const ownerLLM = ref(null)

const strategyForm = reactive({ business_id: '', additional_context: '' })
const strategyResult = ref(null)

const bidForm = reactive({
  project_name: '', bid_content: '', requirements: '', category: ''
})
const bidResult = ref(null)

// ========== 快捷问题 ==========
const qaQuickQuestions = [
  '本月有哪些合同即将到期？',
  '待回款金额最高的客户是谁？',
  '最近一周有哪些商机需要跟进？',
  '我负责的客户有多少个？'
]
const agentQuickQuestions = [
  '今天拜访了江阴科技，客户对方案满意',
  '新增客户：航天信息科技，联系人张总',
  '银河航天商机概率提升到80%'
]
const currentQuickQuestions = computed(() => mode.value === 'qa' ? qaQuickQuestions : agentQuickQuestions)

// ========== 工具函数 ==========
const intentLabel = (intent) => ({ create_follow_log: '创建跟进', create_customer: '新增客户', update_business: '更新商机' }[intent] || '操作')
const intentIcon = (intent) => ({ create_follow_log: '📝', create_customer: '👥', update_business: '🎯' }[intent] || '⚡')
const formatTime = () => {
  const n = new Date()
  return `${n.getHours().toString().padStart(2, '0')}:${n.getMinutes().toString().padStart(2, '0')}`
}
const scrollToBottom = () => {
  nextTick(() => { if (chatContainer.value) chatContainer.value.scrollTop = chatContainer.value.scrollHeight })
}
const switchMode = (m) => { if (mode.value !== m) mode.value = m }

// ========== 语音输入 ==========
const initSpeech = () => {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition
  if (!SR) { speechSupported.value = false; return }
  speechSupported.value = true
  recognition = new SR()
  recognition.lang = 'zh-CN'
  recognition.continuous = false
  recognition.interimResults = false
  recognition.onresult = (e) => { inputText.value = (inputText.value ? inputText.value + ' ' : '') + e.results[0][0].transcript }
  recognition.onerror = () => { isRecording.value = false }
  recognition.onend = () => { isRecording.value = false }
}
const toggleVoice = () => {
  if (!recognition) return
  if (isRecording.value) { recognition.stop(); isRecording.value = false }
  else { try { recognition.start(); isRecording.value = true } catch (e) { ElMessage.error('启动录音失败') } }
}

// ========== 发送消息 ==========
const sendMessage = async () => {
  const text = inputText.value.trim()
  if (!text || isLoading.value) return
  messages.value.push({ id: Date.now(), role: 'user', type: 'text', content: text, time: formatTime() })
  inputText.value = ''
  isLoading.value = true
  scrollToBottom()
  if (mode.value === 'qa') await sendQA(text)
  else await sendAgent(text)
  isLoading.value = false
  scrollToBottom()
}

const sendQA = async (text) => {
  const assistantMsgId = Date.now() + 1
  messages.value.push({ id: assistantMsgId, role: 'assistant', type: 'text', content: '正在思考中...', time: formatTime() })
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
    let buffer = '', received = false
    let fullContent = ''
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
            if (idx !== -1) {
              if (data.type === 'status') {
                // 状态消息：显示为加载提示
                messages.value[idx].content = data.answer
              } else {
                // 实际回答内容：追加到完整内容
                fullContent += data.answer
                messages.value[idx].content = fullContent
              }
            }
            scrollToBottom()
          }
        } catch (e) { /* ignore */ }
      }
    }
    const idx = messages.value.findIndex(m => m.id === assistantMsgId)
    if (idx !== -1 && !received) messages.value[idx].content = '抱歉，查询失败，请稍后重试。'
  } catch (e) {
    const idx = messages.value.findIndex(m => m.id === assistantMsgId)
    if (idx !== -1) messages.value[idx].content = '网络连接异常，请稍后再试。'
  }
}

const sendAgent = async (text) => {
  try {
    const resp = await api.post('/ai/agent', { text, confirm: false }, { timeout: 30000 })
    if (resp.code !== 200) {
      messages.value.push({ id: Date.now() + 2, role: 'assistant', type: 'text', content: `操作失败：${resp.message}`, time: formatTime() })
      return
    }
    const d = resp.data
    if (d.status === 'executed') {
      messages.value.push({ id: Date.now() + 2, role: 'assistant', type: 'text', content: d.reply || '操作已完成。', time: formatTime() })
    } else if (d.status === 'pending') {
      const editEntities = { ...d.entities }
      if (d.data?.matched_customers) editEntities.cust_id = null
      if (d.data?.matched_business) editEntities.business_id = null
      messages.value.push({
        id: Date.now() + 2, role: 'assistant', type: 'confirm',
        content: d.reply || '请确认：', time: formatTime(), intent: d.intent,
        confirmData: { status: 'pending', ...d.data }, editEntities, executing: false
      })
    } else {
      messages.value.push({ id: Date.now() + 2, role: 'assistant', type: 'text', content: d.reply || '未能识别意图。', time: formatTime() })
    }
  } catch (e) {
    messages.value.push({ id: Date.now() + 2, role: 'assistant', type: 'text', content: '请求异常。', time: formatTime() })
  }
}

const confirmExecute = async (msg) => {
  msg.executing = true
  try {
    const resp = await api.post('/ai/agent', { text: msg.editEntities.content || msg.content, confirm: true, intent: msg.intent, entities: msg.editEntities }, { timeout: 30000 })
    if (resp.code === 200 && resp.data.status === 'executed') {
      msg.confirmData.status = 'executed'
      messages.value.push({ id: Date.now() + 3, role: 'assistant', type: 'text', content: resp.data.reply || '执行成功！', time: formatTime() })
    } else ElMessage.error(resp.message || '执行失败')
  } catch (e) { ElMessage.error('执行请求异常') }
  finally { msg.executing = false; scrollToBottom() }
}

const cancelConfirm = (msg) => {
  msg.confirmData.status = 'cancelled'
  messages.value.push({ id: Date.now() + 4, role: 'assistant', type: 'text', content: '已取消。', time: formatTime() })
  scrollToBottom()
}

const askQuickQuestion = (question) => { inputText.value = question; sendMessage() }

// ========== 智能决策功能 ==========
async function handleRecommend() {
  if (!ownerForm.business_title) { ElMessage.warning('请输入商机标题'); return }
  recommending.value = true
  try {
    const res = await api.post('/agent/recommend-owner', {
      business_title: ownerForm.business_title,
      industry: ownerForm.industry,
      amount: ownerForm.amount ? Number(ownerForm.amount) : 0,
      requirements: ownerForm.requirements
    })
    if (res.code === 200) { ownerResults.value = res.data.recommendations; ownerLLM.value = res.data.llm_analysis; ElMessage.success('推荐完成') }
    else ElMessage.error(res.message)
  } catch (e) { ElMessage.error('推荐失败') }
  finally { recommending.value = false }
}

function resetOwnerForm() {
  Object.assign(ownerForm, { business_title: '', industry: '', amount: '', requirements: '' })
  ownerResults.value = []; ownerLLM.value = null
}

async function handleStrategy() {
  if (!strategyForm.business_id) { ElMessage.warning('请输入商机ID'); return }
  strategizing.value = true
  try {
    const res = await api.post('/agent/tracking-strategy', {
      business_id: Number(strategyForm.business_id),
      additional_context: strategyForm.additional_context
    })
    if (res.code === 200) { strategyResult.value = res.data; ElMessage.success('策略生成完成') }
    else ElMessage.error(res.message)
  } catch (e) { ElMessage.error('生成失败') }
  finally { strategizing.value = false }
}

async function handleBidEval() {
  if (!bidForm.project_name) { ElMessage.warning('请输入项目名称'); return }
  evaluating.value = true
  try {
    const res = await api.post('/agent/bid-evaluation', {
      project_name: bidForm.project_name,
      bid_content: bidForm.bid_content,
      requirements: bidForm.requirements,
      category: bidForm.category
    })
    if (res.code === 200) { bidResult.value = res.data; ElMessage.success('评估完成') }
    else ElMessage.error(res.message)
  } catch (e) { ElMessage.error('评估失败') }
  finally { evaluating.value = false }
}

function resetBidForm() {
  Object.assign(bidForm, { project_name: '', bid_content: '', requirements: '', category: '' })
  bidResult.value = null
}

onMounted(() => { initSpeech(); scrollToBottom() })
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
  padding: 16px 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.qa-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 4px;
}

.qa-icon { font-size: 24px; }

.qa-desc { font-size: 13px; opacity: 0.9; margin-bottom: 12px; }

.mode-tabs {
  display: flex;
  gap: 8px;
}

.mode-tab {
  padding: 8px 16px;
  border-radius: 20px;
  background: rgba(255,255,255,0.15);
  cursor: pointer;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 4px;
  transition: all 0.2s;
}

.mode-tab:hover { background: rgba(255,255,255,0.25); }
.mode-tab.active { background: white; color: #764ba2; font-weight: 500; }

.chat-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.message-list { display: flex; flex-direction: column; gap: 12px; }

.message-item {
  display: flex;
  gap: 10px;
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}

.user-message .message-avatar { background: #e2e8f0; }
.assistant-message .message-avatar { background: #c6f6d5; }
.system-message .message-avatar { background: #bee3f8; }

.message-content { flex: 1; max-width: 80%; }

.message-text {
  background: #f7fafc;
  padding: 12px 16px;
  border-radius: 12px;
  line-height: 1.6;
  word-break: break-word;
}

.user-message .message-text { background: #ebf8ff; }
.assistant-message .message-text { background: #f0fff4; }

.message-time { font-size: 11px; color: #a0aec0; margin-top: 4px; }

.typing-indicator { display: flex; gap: 4px; padding: 8px; }
.typing-dot {
  width: 8px; height: 8px;
  background: #a0aec0;
  border-radius: 50%;
  animation: typing 1.4s infinite;
}
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes typing { 0%, 60%, 100% { transform: translateY(0); } 30% { transform: translateY(-6px); } }

.confirm-card {
  background: #fffaf0;
  border: 1px solid #fbd38d;
  border-radius: 12px;
  padding: 14px;
  margin-left: 46px;
}

.confirm-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.confirm-icon { font-size: 18px; }
.confirm-title { font-weight: 600; color: #744210; }
.confirm-status { font-size: 12px; padding: 2px 8px; border-radius: 10px; background: #faf089; color: #744210; }
.confirm-status.executed { background: #9ae6b4; color: #22543d; }
.confirm-body { margin-bottom: 12px; }
.confirm-field { margin-bottom: 8px; }
.confirm-field label { display: block; font-size: 12px; color: #718096; margin-bottom: 4px; }
.confirm-reason { font-size: 13px; color: #744210; margin-bottom: 8px; }
.confirm-actions { display: flex; gap: 8px; }

.input-container {
  display: flex;
  gap: 10px;
  padding: 12px 16px;
  border-top: 1px solid #edf2f7;
  background: #fafafa;
}

.qa-input { flex: 1; }

.voice-btn {
  width: 40px; height: 40px;
  border-radius: 50%;
  background: #f0fff4;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  cursor: pointer;
  transition: all 0.2s;
}

.voice-btn:hover { background: #c6f6d5; }
.voice-btn.recording { background: #fc8181; color: white; animation: pulse 1s infinite; }
@keyframes pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.1); } }

.send-btn { padding: 0 20px; }

.quick-questions { padding: 8px 16px 16px; background: #fafafa; border-top: 1px solid #edf2f7; }
.quick-title { font-size: 12px; color: #a0aec0; margin-bottom: 8px; }
.quick-list { display: flex; flex-wrap: wrap; gap: 8px; }
.quick-btn { font-size: 12px; color: #667eea; }

/* 智能决策样式 */
.decision-container { flex: 1; overflow-y: auto; padding: 16px; }
.decision-tabs { border-radius: 10px; }
.decision-form { padding: 16px; background: #f7fafc; border-radius: 8px; margin-bottom: 16px; }

.decision-result { background: white; border-radius: 10px; padding: 16px; }
.result-title { font-size: 16px; color: #2d3748; margin: 0 0 12px 0; }

.recommend-list { display: flex; flex-direction: column; gap: 10px; }
.recommend-card {
  display: flex; gap: 12px;
  background: linear-gradient(135deg, #f8fafc 0%, #eef4f8 100%);
  border-radius: 10px; padding: 12px;
}
.rank-badge {
  width: 36px; height: 36px;
  border-radius: 50%;
  background: #cbd5e0;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; color: #2d3748; flex-shrink: 0;
}
.rank-1 { background: linear-gradient(135deg, #ffd700, #ffa500); color: white; }
.rank-2 { background: linear-gradient(135deg, #c0c0c0, #a0aec0); color: white; }
.rank-3 { background: linear-gradient(135deg, #cd7f32, #a0522d); color: white; }
.recommend-info { flex: 1; }
.recommend-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.recommend-name { font-weight: 600; color: #2d3748; }
.score { margin-left: auto; font-weight: 700; color: #4ecdc4; }
.recommend-stats { display: flex; gap: 12px; color: #718096; font-size: 12px; }
.recommend-reasons { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.reason-tag { background: #ebf8ff; color: #3182ce; padding: 2px 8px; border-radius: 10px; font-size: 11px; }

.llm-analysis { margin-top: 12px; padding: 12px; background: #faf5ff; border-radius: 8px; font-size: 13px; line-height: 1.6; }

.strategy-summary, .strategy-base { display: flex; gap: 16px; margin-bottom: 12px; }
.summary-item, .base-item { background: #f7fafc; padding: 8px 12px; border-radius: 6px; }
.summary-item .label, .base-item .label { color: #718096; font-size: 12px; }

.action-list h4 { margin: 12px 0 8px 0; font-size: 14px; }
.action-item { display: flex; align-items: center; gap: 8px; padding: 6px 0; font-size: 13px; }
.priority { padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; color: white; }
.p-高 { background: #e53e3e; }
.p-中 { background: #dd6b20; }
.p-低 { background: #38a169; }
.action-text { flex: 1; }
.deadline { color: #ed8936; font-size: 12px; }

.score-summary { display: flex; gap: 20px; align-items: center; margin-bottom: 16px; }
.score-ring {
  width: 100px; height: 100px;
  border-radius: 50%;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  flex-shrink: 0; border: 5px solid;
}
.level-优秀 { border-color: #48bb78; background: #f0fff4; }
.level-良好 { border-color: #4299e1; background: #ebf8ff; }
.level-合格 { border-color: #ecc94b; background: #fffff0; }
.level-风险 { border-color: #f56565; background: #fff5f5; }
.score-value { font-size: 28px; font-weight: 700; color: #2d3748; }
.score-label { font-size: 12px; color: #718096; }
.recommendation { color: #4ecdc4; font-weight: 500; margin-bottom: 8px; }
.dimensions { display: flex; flex-wrap: wrap; gap: 6px; }
.dim-tag { padding: 3px 10px; border-radius: 12px; font-size: 12px; }
.dim-tag.good { background: #c6f6d5; color: #22543d; }
.dim-tag.mid { background: #fef3c7; color: #92400e; }
.dim-tag.low { background: #fed7d7; color: #742a2a; }

.suggestions { margin-top: 12px; }
.suggestions h4 { margin: 0 0 8px 0; font-size: 14px; }
.suggestion-item { padding: 6px 0; font-size: 13px; color: #4a5568; border-bottom: 1px dashed #e2e8f0; }
.suggestion-item:last-child { border-bottom: none; }
</style>