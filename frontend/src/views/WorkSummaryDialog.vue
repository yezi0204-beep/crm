<template>
  <el-dialog
    v-model="visible"
    title="📝 应用中心工作总结（AI 生成）"
    width="860px"
    top="4vh"
    :close-on-click-modal="false"
    @open="onOpen"
  >
    <!-- 周期选择 -->
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
      <el-button :loading="dataLoading" @click="fetchData">查看数据</el-button>
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
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const visible = defineModel({ type: Boolean, default: false })

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

const summarizeDetails = (details) => {
  if (!details || !details.length) return '—'
  return details.slice(0, 4)
    .map(d => `${(d.date || '').slice(5)} ${d.customer || ''}${d.purpose ? '：' + d.purpose : ''}`)
    .join('；') + (details.length > 4 ? ` 等${details.length}项` : '')
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

const onOpen = () => {
  content.value = ''
  generatedAt.value = ''
  extraNote.value = ''
  fetchSummaryData()
}

const generate = async () => {
  generating.value = true
  try {
    const response = await api.longPost('/work-summary/generate', {
      period_type: periodType.value,
      offset: offset.value,
      extra_note: extraNote.value
    })
    if (response.code === 200) {
      content.value = response.data.content
      generatedAt.value = new Date().toLocaleString('zh-CN', { hour12: false })
      ElMessage.success('总结生成成功')
    } else {
      ElMessage.error(response.message || '生成失败')
    }
  } finally {
    generating.value = false
  }
}

const exportWord = async () => {
  if (!content.value) return
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
    const res = await api.longPost('/work-summary/export-word', {
      title: `应用中心${periodType.value === 'week' ? '周' : '月'}工作总结`,
      subtitle: `${data.value ? data.value.period_label : ''}　生成时间：${new Date().toLocaleString('zh-CN', { hour12: false })}`,
      content: content.value,
      stats
    }, { responseType: 'blob' })
    if (res instanceof Blob && res.size > 0) {
      const url = URL.createObjectURL(res)
      const a = document.createElement('a')
      a.href = url
      a.download = `应用中心${periodType.value === 'week' ? '周' : '月'}工作总结.docx`
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
.ws-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
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
</style>
