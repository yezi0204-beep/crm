<template>
  <div class="alerts-container">
    <div class="page-header">
      <h2>预警通知</h2>
      <p class="subtitle">查看即将到期的商机、合同验收和回款预警</p>
    </div>

    <div class="alert-stats">
      <div class="stat-card business">
        <div class="stat-icon">🎯</div>
        <div class="stat-info">
          <div class="stat-value">{{ businessCount }}</div>
          <div class="stat-label">商机预警</div>
        </div>
      </div>
      <div class="stat-card acceptance">
        <div class="stat-icon">✅</div>
        <div class="stat-info">
          <div class="stat-value">{{ acceptanceCount }}</div>
          <div class="stat-label">验收预警</div>
        </div>
      </div>
      <div class="stat-card payment">
        <div class="stat-icon">💰</div>
        <div class="stat-info">
          <div class="stat-value">{{ paymentCount }}</div>
          <div class="stat-label">回款预警</div>
        </div>
      </div>
    </div>

    <div class="alert-tabs">
      <el-tabs v-model="activeTab" class="alert-tabs-wrapper">
        <el-tab-pane label="全部" name="all">
          <div class="alert-list">
            <div 
              v-for="alert in allAlerts" 
              :key="alert.id" 
              class="alert-item"
              :class="alert.type"
            >
              <div class="alert-icon">{{ getAlertIcon(alert.type) }}</div>
              <div class="alert-content">
                <div class="alert-title">{{ alert.title }}</div>
                <div class="alert-detail">{{ alert.detail }}</div>
                <div class="alert-meta">
                  <span class="meta-item">负责人: {{ alert.owner }}</span>
                  <span class="meta-item">到期日期: {{ formatDueDate(alert.due_date) }}</span>
                  <span class="meta-item" v-if="alert.amount > 0">待回款: {{ alert.amount }}万</span>
                </div>
              </div>
              <div class="alert-days">
                <span :class="getDaysClass(alert.due_date)">{{ getDaysLeft(alert.due_date) }}</span>
              </div>
            </div>
          </div>
          <div class="empty-state" v-if="!loading && allAlerts.length === 0">
            <div class="empty-icon">🎉</div>
            <p>暂无预警通知</p>
          </div>
        </el-tab-pane>
        <el-tab-pane label="商机预警" name="business">
          <div class="alert-list">
            <div 
              v-for="alert in businessAlerts" 
              :key="alert.id" 
              class="alert-item business"
            >
              <div class="alert-icon">🎯</div>
              <div class="alert-content">
                <div class="alert-title">{{ alert.title }}</div>
                <div class="alert-detail">{{ alert.detail }}</div>
                <div class="alert-meta">
                  <span class="meta-item">负责人: {{ alert.owner }}</span>
                  <span class="meta-item">到期日期: {{ formatDueDate(alert.due_date) }}</span>
                </div>
              </div>
              <div class="alert-days">
                <span :class="getDaysClass(alert.due_date)">{{ getDaysLeft(alert.due_date) }}</span>
              </div>
            </div>
          </div>
          <div class="empty-state" v-if="!loading && businessAlerts.length === 0">
            <div class="empty-icon">🎉</div>
            <p>暂无商机预警</p>
          </div>
        </el-tab-pane>
        <el-tab-pane label="验收预警" name="acceptance">
          <div class="alert-list">
            <div 
              v-for="alert in acceptanceAlerts" 
              :key="alert.id" 
              class="alert-item acceptance"
            >
              <div class="alert-icon">✅</div>
              <div class="alert-content">
                <div class="alert-title">{{ alert.title }}</div>
                <div class="alert-detail">{{ alert.detail }}</div>
                <div class="alert-meta">
                  <span class="meta-item">负责人: {{ alert.owner }}</span>
                  <span class="meta-item">到期日期: {{ formatDueDate(alert.due_date) }}</span>
                </div>
              </div>
              <div class="alert-days">
                <span :class="getDaysClass(alert.due_date)">{{ getDaysLeft(alert.due_date) }}</span>
              </div>
            </div>
          </div>
          <div class="empty-state" v-if="!loading && acceptanceAlerts.length === 0">
            <div class="empty-icon">🎉</div>
            <p>暂无验收预警</p>
          </div>
        </el-tab-pane>
        <el-tab-pane label="回款预警" name="payment">
          <div class="alert-list">
            <div 
              v-for="alert in paymentAlerts" 
              :key="alert.id" 
              class="alert-item payment"
            >
              <div class="alert-icon">💰</div>
              <div class="alert-content">
                <div class="alert-title">{{ alert.title }}</div>
                <div class="alert-detail">{{ alert.detail }}</div>
                <div class="alert-meta">
                  <span class="meta-item">负责人: {{ alert.owner }}</span>
                  <span class="meta-item">到期日期: {{ formatDueDate(alert.due_date) }}</span>
                  <span class="meta-item">待回款: {{ alert.amount }}万</span>
                </div>
              </div>
              <div class="alert-days">
                <span :class="getDaysClass(alert.due_date)">{{ getDaysLeft(alert.due_date) }}</span>
              </div>
            </div>
          </div>
          <div class="empty-state" v-if="!loading && paymentAlerts.length === 0">
            <div class="empty-icon">🎉</div>
            <p>暂无回款预警</p>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import api from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const alerts = ref([])
const activeTab = ref('all')

const businessAlerts = computed(() => alerts.value.filter(a => a.type === 'business'))
const acceptanceAlerts = computed(() => alerts.value.filter(a => a.type === 'acceptance'))
const paymentAlerts = computed(() => alerts.value.filter(a => a.type === 'payment'))
const allAlerts = computed(() => alerts.value)

const businessCount = computed(() => businessAlerts.value.length)
const acceptanceCount = computed(() => acceptanceAlerts.value.length)
const paymentCount = computed(() => paymentAlerts.value.length)

const fetchAlerts = async () => {
  loading.value = true
  try {
    const response = await api.get('/alerts')
    if (response.code === 200) {
      alerts.value = response.data.alerts || []
    } else {
      ElMessage.error(response.message || '获取预警失败')
    }
  } catch (error) {
    ElMessage.error('获取预警失败，请重试')
  } finally {
    loading.value = false
  }
}

const getAlertIcon = (type) => {
  const icons = {
    'business': '🎯',
    'acceptance': '✅',
    'payment': '💰'
  }
  return icons[type] || '🔔'
}

const formatDueDate = (dueDate) => {
  if (!dueDate) return ''
  // 截取前10位，兼容 YYYY-MM-DD 与 ISO datetime（含时分秒/时区）格式
  return dueDate.length >= 10 ? dueDate.substring(0, 10) : dueDate
}

const getDaysLeft = (dueDate) => {
  const today = new Date()
  const due = new Date(dueDate)
  const diff = Math.ceil((due - today) / (1000 * 60 * 60 * 24))
  if (diff < 0) return '已过期'
  if (diff === 0) return '今天到期'
  if (diff === 1) return '明天到期'
  return `${diff}天后到期`
}

const getDaysClass = (dueDate) => {
  const today = new Date()
  const due = new Date(dueDate)
  const diff = Math.ceil((due - today) / (1000 * 60 * 60 * 24))
  if (diff < 0) return 'overdue'
  if (diff <= 2) return 'urgent'
  if (diff <= 5) return 'warning'
  return 'normal'
}

let refreshInterval = null

onMounted(() => {
  fetchAlerts()
  refreshInterval = setInterval(fetchAlerts, 30000)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})
</script>

<style scoped>
.page-header {
  margin-bottom: 16px;
}

.page-header h2 {
  font-size: 20px;
  font-weight: 600;
  color: #334155;
  margin: 0 0 8px 0;
}

.page-header .subtitle {
  font-size: 13px;
  color: #94a3b8;
  margin: 0;
}

.alert-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}

.stat-card {
  flex: 1;
  background: #fff;
  border-radius: 10px;
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  border-left: 4px solid;
}

.stat-card.business {
  border-left-color: #4ecdc4;
}

.stat-card.acceptance {
  border-left-color: #f59e0b;
}

.stat-card.payment {
  border-left-color: #ef4444;
}

.stat-icon {
  font-size: 28px;
}

.stat-info {
  flex: 1;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #334155;
}

.stat-label {
  font-size: 13px;
  color: #94a3b8;
  margin-top: 4px;
}

.alert-tabs-wrapper {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  overflow: hidden;
}

.alert-list {
  padding: 16px;
}

.alert-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px;
  margin-bottom: 10px;
  background: #f8fafc;
  border-radius: 8px;
  border-left: 4px solid;
  transition: all 0.2s ease;
}

.alert-item:hover {
  background: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.alert-item.business {
  border-left-color: #4ecdc4;
}

.alert-item.acceptance {
  border-left-color: #f59e0b;
}

.alert-item.payment {
  border-left-color: #ef4444;
}

.alert-icon {
  font-size: 22px;
  flex-shrink: 0;
}

.alert-content {
  flex: 1;
}

.alert-title {
  font-size: 14px;
  font-weight: 600;
  color: #334155;
  margin-bottom: 6px;
}

.alert-detail {
  font-size: 13px;
  color: #64748b;
  margin-bottom: 8px;
  line-height: 1.5;
}

.alert-meta {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.meta-item {
  font-size: 12px;
  color: #94a3b8;
}

.alert-days {
  flex-shrink: 0;
}

.alert-days span {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 12px;
  font-weight: 500;
}

.alert-days span.overdue {
  background: #fee2e2;
  color: #dc2626;
}

.alert-days span.urgent {
  background: #fed7aa;
  color: #ea580c;
}

.alert-days span.warning {
  background: #fef3c7;
  color: #d97706;
}

.alert-days span.normal {
  background: #d1fae5;
  color: #059669;
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.empty-state p {
  color: #94a3b8;
  font-size: 14px;
}
</style>
