<template>
  <div style="padding:16px">
    <!-- 任务统计 -->
    <el-row :gutter="12" style="margin-bottom:14px">
      <el-col :span="4" v-for="s in statusCards" :key="s.key">
        <el-card shadow="never">
          <div class="stat-num" :style="{ color: s.color }">{{ stats.by_status?.[s.key] ?? 0 }}</div>
          <div class="stat-label">{{ s.label }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="stat-num">{{ stats.today_count ?? 0 }}</div>
          <div class="stat-label">今日处理</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="stat-num">{{ formatDuration(stats.avg_duration_ms) }}</div>
          <div class="stat-label">平均耗时</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 任务列表 -->
    <el-tabs v-model="activeTab">
      <el-tab-pane label="任务监控" name="tasks">
        <div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap">
          <el-select v-model="filterStatus" placeholder="状态" clearable style="width:120px" @change="loadTasks">
            <el-option v-for="s in ['PENDING','RUNNING','SUCCESS','FAILED','RETRYING','CANCELLED']" :key="s" :label="s" :value="s" />
          </el-select>
          <el-select v-model="filterType" placeholder="任务类型" clearable style="width:200px" @change="loadTasks">
            <el-option v-for="t in taskTypes" :key="t" :label="t" :value="t" />
          </el-select>
          <el-button v-if="isAdmin" type="primary" @click="submitDialog = true">+ 提交任务</el-button>
        </div>
        <el-table :data="tasks" v-loading="tasksLoading" border size="small">
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="task_type" label="任务类型" width="170" />
          <el-table-column label="状态" width="100" align="center">
            <template #default="{row}">
              <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="进度/结果" min-width="200" show-overflow-tooltip>
            <template #default="{row}">{{ row.progress || row.result || row.error_message || '-' }}</template>
          </el-table-column>
          <el-table-column prop="created_by" label="提交人" width="90" />
          <el-table-column label="耗时" width="90">
            <template #default="{row}">{{ row.duration_ms ? formatDuration(row.duration_ms) : '-' }}</template>
          </el-table-column>
          <el-table-column label="重试" width="60" align="center">
            <template #default="{row}">{{ row.retry_count }}/{{ row.max_retries }}</template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="150" />
          <el-table-column v-if="isAdmin" label="操作" width="140">
            <template #default="{row}">
              <el-button v-if="['FAILED','SUCCESS','CANCELLED','RETRYING'].includes(row.status)"
                         size="small" type="primary" plain :loading="actingId===row.id" @click="retryTask(row)">重跑</el-button>
              <el-button v-if="['PENDING','RUNNING','RETRYING'].includes(row.status)"
                         size="small" type="danger" text @click="cancelTask(row)">取消</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination v-if="taskTotal > 0" :total="taskTotal" :page-size="perPage" v-model:current-page="taskPage"
                       layout="total, prev, pager, next" style="margin-top:10px" @current-change="loadTasks" />
      </el-tab-pane>

      <el-tab-pane label="AI操作日志" name="aiLogs">
        <div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap">
          <el-select v-model="logStatus" placeholder="状态" clearable style="width:110px" @change="loadLogs">
            <el-option label="成功" value="success" />
            <el-option label="失败" value="failed" />
          </el-select>
          <el-button @click="loadLogs">刷新</el-button>
        </div>
        <el-table :data="logs" v-loading="logsLoading" border size="small">
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="operation_type" label="操作类型" width="150" />
          <el-table-column prop="operator_name" label="操作人" width="90" />
          <el-table-column prop="model_name" label="AI模型" min-width="180" show-overflow-tooltip />
          <el-table-column prop="prompt_version" label="Prompt版本" width="90" align="center" />
          <el-table-column prop="token_usage" label="Tokens" width="80" align="right" />
          <el-table-column label="耗时" width="90">
            <template #default="{row}">{{ row.latency ? formatDuration(row.latency) : '-' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{row}">
              <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="error_message" label="错误信息" min-width="160" show-overflow-tooltip />
          <el-table-column prop="created_at" label="时间" width="150" />
        </el-table>
        <el-pagination v-if="logTotal > 0" :total="logTotal" :page-size="perPage" v-model:current-page="logPage"
                       layout="total, prev, pager, next" style="margin-top:10px" @current-change="loadLogs" />
      </el-tab-pane>
    </el-tabs>

    <!-- 提交任务弹窗 -->
    <el-dialog v-model="submitDialog" title="手动提交任务" width="480px">
      <el-form label-width="90px">
        <el-form-item label="任务类型" required>
          <el-select v-model="submitType" style="width:100%">
            <el-option v-for="t in taskTypes" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="最大重试">
          <el-input-number v-model="submitRetries" :min="0" :max="10" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="submitDialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="doSubmit">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const isAdmin = computed(() => auth.user?.role === 'admin' || auth.has?.('system.admin'))

const activeTab = ref('tasks')
const stats = ref({})
const tasks = ref([])
const taskTotal = ref(0)
const taskPage = ref(1)
const perPage = ref(20)
const tasksLoading = ref(false)
const filterStatus = ref('')
const filterType = ref('')
const logs = ref([])
const logTotal = ref(0)
const logPage = ref(1)
const logsLoading = ref(false)
const logStatus = ref('')
const actingId = ref(null)
const submitDialog = ref(false)
const submitType = ref('update_customer_profile')
const submitRetries = ref(3)
const submitting = ref(false)
let timer = null

const taskTypes = [
  'crawl_source', 'parse_document', 'extract_attachment',
  'llm_classify', 'llm_extract_entity', 'llm_score',
  'deduplicate_project', 'update_customer_profile',
  'update_competitor_profile', 'generate_daily_report',
]

const statusCards = [
  { key: 'PENDING', label: '待执行', color: '#909399' },
  { key: 'RUNNING', label: '运行中', color: '#409eff' },
  { key: 'SUCCESS', label: '成功', color: '#67c23a' },
  { key: 'FAILED', label: '失败', color: '#f56c6c' },
  { key: 'RETRYING', label: '重试中', color: '#e6a23c' },
  { key: 'CANCELLED', label: '已取消', color: '#c0c4cc' },
]

function statusType(status) {
  return {
    PENDING: 'info', RUNNING: 'primary', SUCCESS: 'success',
    FAILED: 'danger', RETRYING: 'warning', CANCELLED: 'info',
  }[status] || 'info'
}

function formatDuration(ms) {
  if (!ms) return '-'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m${Math.round((ms % 60000) / 1000)}s`
}

async function loadStats() {
  try {
    const res = await api.get('/tasks/stats')
    stats.value = res.data || {}
  } catch { /* ignore */ }
}

async function loadTasks() {
  tasksLoading.value = true
  try {
    const params = { page: taskPage.value, per_page: perPage.value }
    if (filterStatus.value) params.status = filterStatus.value
    if (filterType.value) params.task_type = filterType.value
    const res = await api.get('/tasks', params)
    tasks.value = res.data || []
    taskTotal.value = res.total || 0
  } catch (e) { ElMessage.error('加载任务失败') }
  finally { tasksLoading.value = false }
}

async function loadLogs() {
  logsLoading.value = true
  try {
    const params = { page: logPage.value, per_page: perPage.value }
    if (logStatus.value) params.status = logStatus.value
    const res = await api.get('/ai-logs', params)
    logs.value = res.data || []
    logTotal.value = res.total || 0
  } catch (e) { ElMessage.error('加载日志失败') }
  finally { logsLoading.value = false }
}

async function retryTask(row) {
  actingId.value = row.id
  try {
    const res = await api.post(`/tasks/${row.id}/retry`)
    ElMessage.success(res.message || '已重新提交')
    loadTasks()
  } catch (e) { ElMessage.error('重跑失败：' + (e.response?.data?.message || e.message)) }
  finally { actingId.value = null }
}

async function cancelTask(row) {
  try {
    await ElMessageBox.confirm(`确定取消任务#${row.id}？`, '取消任务', { type: 'warning' })
  } catch { return }
  try {
    const res = await api.post(`/tasks/${row.id}/cancel`)
    ElMessage.success(res.message || '已取消')
    loadTasks()
  } catch (e) { ElMessage.error('取消失败') }
}

async function doSubmit() {
  submitting.value = true
  try {
    const res = await api.post('/tasks/submit', {
      task_type: submitType.value, max_retries: submitRetries.value,
    })
    ElMessage.success(res.message || '任务已提交')
    submitDialog.value = false
    loadTasks()
  } catch (e) { ElMessage.error('提交失败') }
  finally { submitting.value = false }
}

onMounted(() => {
  loadStats()
  loadTasks()
  loadLogs()
  timer = setInterval(() => {
    loadStats()
    if (activeTab.value === 'tasks') loadTasks()
  }, 10000)
})

onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.stat-num { font-size: 22px; font-weight: bold; }
.stat-label { font-size: 12px; color: #909399; }
</style>
