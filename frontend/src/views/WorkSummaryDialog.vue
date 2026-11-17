<template>
  <el-dialog
    v-model="visible"
    title="📝 应用中心工作总结（AI 生成）"
    width="860px"
    top="4vh"
    :close-on-click-modal="false"
    @open="onOpen"
  >
    <!-- 顶部切换：新生成 / 历史总结 -->
    <div class="ws-top-tab">
      <el-radio-group v-model="mode" size="small">
        <el-radio-button value="generate">🤖 生成 / 编辑总结</el-radio-button>
        <el-radio-button value="history">📚 历史总结</el-radio-button>
      </el-radio-group>
    </div>

    <!-- ========== 模式一：生成 / 编辑 ========== -->
    <template v-if="mode === 'generate'">
      <div class="ws-toolbar">
        <el-radio-group v-model="periodType" :disabled="generating">
          <el-radio-button value="week">周总结</el-radio-button>
          <el-radio-button value="month">月总结</el-radio-button>
        </el-radio-group>
        <el-select v-model="offset" :disabled="generating" style="width: 130px">
          <template v-if="periodType === 'week'">
            <el-option label="本周" :value="0" />
            <el-option label="上周" :value="1" />
            <el-option label="上上周" :value="2" />
          </template>
          <template v-else>
            <el-option label="本月" :value="0" />
            <el-option label="上月" :value="1" />
            <el-option label="上上月" :value="2" />
          </template>
        </el-select>
        <el-button :loading="dataLoading" @click="fetchSummaryData">查看数据</el-button>
        <el-button
          type="primary"
          :loading="generating"
          @click="generate"
        >
          {{ generating ? 'AI 生成中…' : '🤖 生成总结' }}
        </el-button>
        <el-button
          type="success"
          :loading="exporting"
          :disabled="!content"
          @click="exportWord"
        >
          📄 导出 Word
        </el-button>
        <el-tag v-if="currentRecord" type="info" effect="plain">
          已保存 #{{ currentRecord.id }}
        </el-tag>
      </div>

      <!-- 数据概览 -->
      <el-collapse v-model="activeCollapse" class="ws-collapse">
        <el-collapse-item name="data" :title="`📊 周期数据预览${data ? `（${data.period_label}，共 ${data.visits_total} 次拜访）` : ''}`">
          <div v-if="data" class="ws-data">
            <div class="ws-stat-row">
              <el-tag type="primary" effect="plain">拜访 {{ data.visits_total }} 次</el-tag>
              <el-tag type="success" effect="plain">已完成 {{ data.visits_completed }}</el-tag>
              <el-tag type="warning" effect="plain">进行中 {{ data.visits_planned }}</el-tag>
              <el-tag type="info" effect="plain">覆盖客户 {{ data.customers_covered }} 家</el-tag>
              <el-tag type="info" effect="plain">新增客户 {{ data.customers_new }} 家</el-tag>
              <el-tag type="success" effect="plain">签约 {{ data.contracts_signed.count }} 份 / ¥{{ data.contracts_signed.amount_yuan }}</el-tag>
              <el-tag type="success" effect="plain">回款 {{ data.payments_received.count }} 笔 / ¥{{ data.payments_received.amount_yuan }}</el-tag>
              <el-tag type="primary" effect="plain">新增商机 {{ data.business_new.count }} 个</el-tag>
            </div>
            <el-table :data="data.visits_by_user" size="small" border max-height="220">
              <el-table-column prop="name" label="人员" width="90" />
              <el-table-column prop="role" label="角色" width="80" />
              <el-table-column prop="total" label="拜访数" width="80" align="center" />
              <el-table-column prop="completed" label="已完成" width="80" align="center" />
              <el-table-column prop="planned" label="进行中" width="80" align="center" />
              <el-table-column label="近期安排摘要" min-width="300">
                <template #default="{ row }">
                  <span class="ws-detail">{{ summarizeDetails(row.details) }}</span>
                </template>
              </el-table-column>
            </el-table>
            <el-input
              v-model="extraNote"
              type="textarea"
              :rows="2"
              placeholder="补充说明（可选）：如本期专项工作、临时任务等，将一并交给 AI 参考"
              class="ws-note"
            />
          </div>
          <el-empty v-else description="点击「查看数据」加载周期业务数据" :image-size="60" />
        </el-collapse-item>
      </el-collapse>

      <!-- 生成结果编辑 -->
      <div v-if="content || generating" class="ws-result">
        <div class="ws-result-header">
          <span>📋 总结内容（可编辑后导出）</span>
          <span v-if="generatedAt" class="ws-time">生成于 {{ generatedAt }}</span>
        </div>
        <el-input
          v-model="content"
          type="textarea"
          :rows="16"
          :disabled="generating"
          placeholder="点击「生成总结」，AI 将基于真实业务数据撰写多维度总结报告"
          class="ws-editor"
        />
      </div>
      <el-empty v-else-if="!generating" description="选择周期后点击「生成总结」" :image-size="80" />
    </template>

    <!-- ========== 模式二：历史总结 ========== -->
    <template v-else>
      <div class="ws-toolbar">
        <el-radio-group v-model="historyView">
          <el-radio-button value="any">🎯 指定周期分析</el-radio-button>
          <el-radio-button value="records">📚 历史记录</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 指定周期分析（无历史记录时也能用） -->
      <template v-if="historyView === 'any'">
        <div class="ws-toolbar" style="margin-bottom: 18px">
          <el-radio-group v-model="pickPeriodType">
            <el-radio-button value="week">周总结</el-radio-button>
            <el-radio-button value="month">月总结</el-radio-button>
          </el-radio-group>
          <!-- 周总结：daterange + 快捷项，规避 type="week" 的 value-format 不稳定问题 -->
          <el-date-picker
            v-if="pickPeriodType === 'week'"
            v-model="pickRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            :shortcuts="weekShortcuts"
            style="width: 300px"
          />
          <!-- 月总结：month 选择器的 value-format 稳定 -->
          <el-date-picker
            v-else
            v-model="pickMonth"
            type="month"
            placeholder="选择某月"
            value-format="YYYY-MM"
            style="width: 180px"
          />
          <el-button
            type="primary"
            :loading="generating"
            :disabled="!canRunSpecified"
            @click="generateSpecified"
          >🤖 直接分析此周期</el-button>
          <el-tag v-if="specifiedLabel" type="info" effect="plain">
            将分析 {{ specifiedLabel }}（{{ specifiedStart }} ~ {{ specifiedEnd }}）
          </el-tag>
        </div>

        <div class="ws-history-preview" style="border: 1px dashed #dcdfe6; border-radius: 6px; padding: 16px">
          <el-empty v-if="!specifiedResult" description="选择上方周期后点击「直接分析此周期」" :image-size="80" />
          <div v-else>
            <div class="ws-history-header">
              <span>📋 {{ specifiedResult.period_label }}</span>
              <div>
                <el-button size="small" type="success" :loading="exporting" @click="exportWord">📄 导出 Word</el-button>
              </div>
            </div>
            <el-input
              :model-value="specifiedResult.content"
              type="textarea"
              :rows="22"
              disabled
              class="ws-editor"
            />
          </div>
        </div>
      </template>

      <!-- 历史记录列表 -->
      <template v-else>
        <div class="ws-toolbar">
          <el-radio-group v-model="historyFilter">
            <el-radio-button value="all">全部</el-radio-button>
            <el-radio-button value="week">周总结</el-radio-button>
            <el-radio-button value="month">月总结</el-radio-button>
          </el-radio-group>
          <el-button :loading="historyLoading" @click="loadHistory">🔄 刷新</el-button>
        </div>

        <div class="ws-history" v-loading="historyLoading">
          <div class="ws-history-list">
            <div
              v-for="r in filteredHistory"
              :key="r.id"
              class="ws-history-item"
              :class="{ active: currentRecord && currentRecord.id === r.id }"
              @click="selectRecord(r)"
            >
              <div class="ws-history-title">
                <el-tag :type="r.period_type === 'week' ? 'primary' : 'success'" size="small" effect="plain">
                  {{ r.period_type === 'week' ? '周' : '月' }}
                </el-tag>
                <span class="ws-history-label">{{ r.period_label }}</span>
              </div>
              <div class="ws-history-meta">
                <span>{{ r.generated_name || r.generated_by || '—' }}</span>
                <span>{{ formatTime(r.created_at) }}</span>
              </div>
            </div>
            <el-empty
              v-if="!filteredHistory.length"
              description="暂无历史总结记录，可切到「🎯 指定周期分析」直接跑某一周"
              :image-size="60"
            />
          </div>
          <div class="ws-history-preview">
            <div v-if="currentRecord" class="ws-history-header">
              <span>📋 {{ currentRecord.period_label }}</span>
              <div>
                <el-button
                  size="small"
                  type="warning"
                  :loading="generating"
                  @click="reanalyzeCurrent"
                >🤖 重新分析</el-button>
                <el-button
                  size="small"
                  type="success"
                  :loading="exporting"
                  @click="exportWord"
                >📄 导出 Word</el-button>
                <el-button
                  size="small"
                  type="primary"
                  plain
                  @click="editCurrent"
                >✏️ 进入编辑</el-button>
              </div>
            </div>
            <el-input
              v-if="currentRecord"
              :model-value="currentRecord.content"
              type="textarea"
              :rows="22"
              disabled
              class="ws-editor"
            />
            <el-empty v-else description="选择左側历史记录查看" :image-size="80" />
          </div>
        </div>
      </template>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const visible = defineModel({ type: Boolean, default: false })

const mode = ref('generate')        // generate / history
const periodType = ref('week')
const offset = ref(0)
const activeCollapse = ref([])
const data = ref(null)
const dataLoading = ref(false)
const generating = ref(false)
const exporting = ref(false)
const content = ref('')
const generatedAt = ref('')
const extraNote = ref('')
const currentRecord = ref(null)     // 当前编辑/查看的历史记录

// 历史
const historyView = ref('any')      // any / records
const pickPeriodType = ref('week')
const pickRange = ref([])            // [start, end]，格式 YYYY-MM-DD
const pickMonth = ref('')           // 如 2026-11
const specifiedResult = ref(null)
const historyFilter = ref('all')
const historyLoading = ref(false)
const historyRecords = ref([])

const filteredHistory = computed(() => {
  if (historyFilter.value === 'all') return historyRecords.value
  return historyRecords.value.filter(r => r.period_type === historyFilter.value)
})

// daterange 周快捷项：本周 / 上周 / 上上周 / 本月 / 上月
const weekShortcuts = [
  {
    text: '本周',
    value: () => {
      const now = new Date()
      const dow = (now.getDay() + 6) % 7          // 0=Mon, 6=Sun
      const mon = new Date(now.getTime() - dow * 86400000)
      const sun = new Date(mon.getTime() + 6 * 86400000)
      return [mon, sun]
    }
  },
  {
    text: '上周',
    value: () => {
      const now = new Date()
      const dow = (now.getDay() + 6) % 7
      const mon = new Date(now.getTime() - (dow + 7) * 86400000)
      const sun = new Date(mon.getTime() + 6 * 86400000)
      return [mon, sun]
    }
  },
  {
    text: '上上周',
    value: () => {
      const now = new Date()
      const dow = (now.getDay() + 6) % 7
      const mon = new Date(now.getTime() - (dow + 14) * 86400000)
      const sun = new Date(mon.getTime() + 6 * 86400000)
      return [mon, sun]
    }
  }
]

const pad2 = (n) => String(n).padStart(2, '0')

// 从 YYYY-MM-DD 字符串解析成 Date（本地时间）
const parseFmtDate = (s) => {
  if (!s) return null
  const [y, m, d] = s.split('-').map(Number)
  return new Date(y, m - 1, d)
}

const isoWeekNo = (date) => {
  const d = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  d.setHours(0, 0, 0, 0)
  d.setDate(d.getDate() + 4 - (d.getDay() || 7))
  const yearStart = new Date(d.getFullYear(), 0, 1)
  return Math.ceil((((d - yearStart) / 86400000) + 1) / 7)
}

// 从 pickRange 数组 [start, end] 生成 {start, end, label}
const parseWeekRange = (range) => {
  if (!Array.isArray(range) || range.length !== 2 || !range[0] || !range[1]) return null
  const start = String(range[0]).slice(0, 10)
  const end = String(range[1]).slice(0, 10)
  const date = parseFmtDate(start)
  if (!date) return null
  return {
    start, end,
    label: `${start} ~ ${end}（第${isoWeekNo(date)}周）`
  }
}

const parseMonthToRange = (ym) => {
  if (!ym) return null
  const [yearStr, monthStr] = ym.split('-')
  const year = parseInt(yearStr, 10)
  const month = parseInt(monthStr, 10)
  const start = `${ym}-01`
  const lastDay = new Date(year, month, 0).getDate()
  const end = `${ym}-${pad2(lastDay)}`
  const label = `${year}年${month}月`
  return { start, end, label }
}

const specifiedRange = computed(() => {
  if (pickPeriodType.value === 'week') return parseWeekRange(pickRange.value)
  return parseMonthToRange(pickMonth.value)
})
const specifiedStart = computed(() => specifiedRange.value?.start || '')
const specifiedEnd = computed(() => specifiedRange.value?.end || '')
const specifiedLabel = computed(() => specifiedRange.value?.label || '')
const canRunSpecified = computed(() => !!specifiedRange.value)

const generateSpecified = async () => {
  if (!specifiedRange.value) return
  generating.value = true
  currentRecord.value = null
  specifiedResult.value = null
  try {
    const response = await api.longPost('/work-summary/generate', {
      period_type: pickPeriodType.value,
      offset: 0,
      start_date: specifiedRange.value.start,
      end_date: specifiedRange.value.end,
      period_label: specifiedRange.value.label
    })
    if (response.code === 200) {
      specifiedResult.value = response.data
      ElMessage.success('指定周期总结生成成功')
      // 刷新历史列表
      await loadHistory()
      // 如果后端已按 start_date 匹配到已有记录，高亮它
      const fresh = historyRecords.value.find(h =>
        h.start_date === specifiedRange.value.start && h.period_type === pickPeriodType.value
      )
      if (fresh) currentRecord.value = fresh
    } else {
      ElMessage.error(response.message || '生成失败')
    }
  } finally {
    generating.value = false
  }
}

const summarizeDetails = (details) => {
  if (!details || !details.length) return '—'
  return details.slice(0, 4)
    .map(d => `${(d.date || '').slice(5)} ${d.customer || ''}${d.purpose ? '：' + d.purpose : ''}`)
    .join('；') + (details.length > 4 ? ` 等${details.length}项` : '')
}

const formatTime = (t) => {
  if (!t) return ''
  return String(t).replace('T', ' ').slice(0, 19)
}

const fetchSummaryData = async () => {
  dataLoading.value = true
  try {
    const response = await api.get('/work-summary/data', {
      period_type: periodType.value,
      offset: offset.value
    })
    if (response.code === 200) {
      data.value = response.data
    } else {
      ElMessage.error(response.message || '数据加载失败')
    }
  } finally {
    dataLoading.value = false
  }
}

const loadHistory = async () => {
  historyLoading.value = true
  try {
    const response = await api.get('/work-summary/records', { limit: 100 })
    if (response.code === 200) {
      historyRecords.value = response.data || []
    }
  } finally {
    historyLoading.value = false
  }
}

const selectRecord = async (r) => {
  try {
    const response = await api.get(`/work-summary/records/${r.id}`)
    if (response.code === 200) {
      currentRecord.value = response.data
    }
  } catch (e) {
    // 回退：列表里已有 content
    currentRecord.value = r
  }
}

const editCurrent = () => {
  if (!currentRecord.value) return
  content.value = currentRecord.value.content || ''
  periodType.value = currentRecord.value.period_type
  generatedAt.value = formatTime(currentRecord.value.created_at)
  mode.value = 'generate'
  ElMessage.success('已加载到编辑区，可继续修改或重新导出')
}

const reanalyzeCurrent = async () => {
  if (!currentRecord.value) return
  generating.value = true
  try {
    const r = currentRecord.value
    const response = await api.longPost('/work-summary/generate', {
      period_type: r.period_type,
      offset: 0,
      start_date: r.start_date,
      end_date: r.end_date,
      period_label: r.period_label
    })
    if (response.code === 200) {
      ElMessage.success('重新分析完成，已覆盖更新该记录')
      // 刷新当前记录
      if (response.data.record_id) {
        const id = response.data.record_id
        // 列表里找并定位
        await loadHistory()
        const fresh = historyRecords.value.find(h => h.id === id)
        if (fresh) {
          currentRecord.value = fresh
          await selectRecord(fresh)
        } else {
          // 兜底：按周期找
          await selectRecord(r)
        }
      } else {
        await loadHistory()
        await selectRecord(r)
      }
    } else {
      ElMessage.error(response.message || '重新分析失败')
    }
  } finally {
    generating.value = false
  }
}

const onOpen = () => {
  mode.value = 'generate'
  content.value = ''
  generatedAt.value = ''
  extraNote.value = ''
  currentRecord.value = null
  fetchSummaryData()
  loadHistory()
}

const generate = async () => {
  generating.value = true
  currentRecord.value = null
  try {
    const response = await api.longPost('/work-summary/generate', {
      period_type: periodType.value,
      offset: offset.value,
      extra_note: extraNote.value
    })
    if (response.code === 200) {
      content.value = response.data.content
      generatedAt.value = new Date().toLocaleString('zh-CN', { hour12: false })
      if (response.data.record_id) {
        currentRecord.value = { id: response.data.record_id }
      }
      ElMessage.success('总结生成成功并已保存历史记录')
      loadHistory()
    } else {
      ElMessage.error(response.message || '生成失败')
    }
  } finally {
    generating.value = false
  }
}

const exportWord = async () => {
  // 根据当前视图取要导出的内容
  let body = null
  if (mode.value === 'generate' && content.value) {
    body = { content: content.value, period_label: currentRecord.value?.period_label || data.value?.period_label || '',
             period_type: periodType.value }
  } else if (historyView.value === 'any' && specifiedResult.value?.content) {
    body = { content: specifiedResult.value.content, period_label: specifiedResult.value.period_label,
             period_type: pickPeriodType.value }
  } else if (historyView.value === 'records' && currentRecord.value?.content) {
    body = { content: currentRecord.value.content, period_label: currentRecord.value.period_label,
             period_type: currentRecord.value.period_type }
  }
  if (!body) {
    ElMessage.warning('当前没有可导出的总结内容')
    return
  }
  exporting.value = true
  try {
    const stats = data.value ? [
      { label: '客户拜访', value: `${data.value.visits_total} 次` },
      { label: '已完成', value: `${data.value.visits_completed} 次` },
      { label: '覆盖客户', value: `${data.value.customers_covered} 家` },
      { label: '新增客户', value: `${data.value.customers_new} 家` },
      { label: '新增商机', value: `${data.value.business_new.count} 个` },
      { label: '签约合同', value: `${data.value.contracts_signed.count} 份 / ¥${data.value.contracts_signed.amount_yuan}` },
      { label: '回款', value: `${data.value.payments_received.count} 笔 / ¥${data.value.payments_received.amount_yuan}` }
    ] : []
    const periodText = body.period_type === 'week' ? '周' : '月'
    const res = await api.longPost('/work-summary/export-word', {
      title: `应用中心${periodText}工作总结`,
      subtitle: `${body.period_label}　导出时间：${new Date().toLocaleString('zh-CN', { hour12: false })}`,
      content: body.content,
      stats
    }, { responseType: 'blob' })
    if (res instanceof Blob && res.size > 0) {
      const url = URL.createObjectURL(res)
      const a = document.createElement('a')
      a.href = url
      a.download = `应用中心${periodText}工作总结.docx`
      a.click()
      URL.revokeObjectURL(url)
      ElMessage.success('Word 导出成功')
    } else {
      ElMessage.error('导出失败')
    }
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
.ws-top-tab {
  margin-bottom: 12px;
}
.ws-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.ws-collapse {
  margin-bottom: 14px;
}
.ws-stat-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}
.ws-detail {
  color: #606266;
  font-size: 12px;
}
.ws-note {
  margin-top: 10px;
}
.ws-result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  font-weight: 600;
  color: #303133;
}
.ws-time {
  font-weight: normal;
  color: #909399;
  font-size: 12px;
}
.ws-editor :deep(.el-textarea__inner) {
  font-family: 'Microsoft YaHei', sans-serif;
  font-size: 13px;
  line-height: 1.7;
}

/* 历史总结 */
.ws-history {
  display: flex;
  gap: 12px;
  height: 540px;
}
.ws-history-list {
  width: 280px;
  flex-shrink: 0;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  overflow-y: auto;
  background: #fafbfc;
}
.ws-history-item {
  padding: 10px 12px;
  border-bottom: 1px solid #ebeef5;
  cursor: pointer;
  transition: background 0.15s;
}
.ws-history-item:hover {
  background: #ecf5ff;
}
.ws-history-item.active {
  background: #d9ecff;
  border-left: 3px solid #409eff;
}
.ws-history-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.ws-history-label {
  font-size: 13px;
  color: #303133;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ws-history-meta {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #909399;
}
.ws-history-preview {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.ws-history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 4px;
  border-bottom: 1px solid #ebeef5;
  font-weight: 600;
  color: #303133;
  margin-bottom: 6px;
}
</style>
