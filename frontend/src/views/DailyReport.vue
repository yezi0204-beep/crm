<template>
  <div class="report-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>📰 AI销售情报日报</span>
          <div style="margin-left:auto">
            <el-button type="primary" :loading="generating" @click="generateToday">生成今日日报</el-button>
          </div>
        </div>
      </template>

      <div class="report-list" v-loading="loading">
        <el-timeline v-if="reports.length">
          <el-timeline-item v-for="r in reports" :key="r.id" :timestamp="r.report_date"
                           placement="top" :type="r.generated_by==='auto' ? 'success' : 'primary'">
            <el-card class="report-card" shadow="hover" @click="viewReport(r.report_date)" style="cursor:pointer">
              <div class="report-title">{{ r.title }}</div>
              <div class="report-summary">{{ r.summary }}</div>
              <div class="report-meta" v-if="r.metrics">
                <span v-for="(v, k) in parseMetrics(r.metrics)" :key="k" class="metric-tag">
                  {{ metricLabel(k) }}: {{ v }}
                </span>
              </div>
            </el-card>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="暂无日报，点击右上角生成" />
      </div>

      <el-pagination v-if="total > perPage" v-model:current-page="page" :page-size="perPage" :total="total"
                     layout="prev, pager, next" @current-change="loadList" style="margin-top:12px;justify-content:center" />
    </el-card>

    <el-dialog v-model="showDetail" title="日报详情" width="800px" top="5vh">
      <div v-if="detail" class="report-detail">
        <h2>{{ detail.title }}</h2>
        <div class="detail-date">{{ detail.report_date }} | 生成方式: {{ detail.generated_by }}</div>

        <div class="section" v-if="detail.metrics">
          <h3>📊 关键指标</h3>
          <div class="metrics-grid">
            <div class="metric-item" v-for="(v, k) in parseMetrics(detail.metrics)" :key="k">
              <div class="metric-value">{{ v }}</div>
              <div class="metric-label">{{ metricLabel(k) }}</div>
            </div>
          </div>
        </div>

        <div class="section">
          <h3>📝 摘要</h3>
          <p class="report-text">{{ detail.summary }}</p>
        </div>

        <div class="section" v-if="parseList(detail.opportunities).length">
          <h3>🎯 重点商机</h3>
          <el-table :data="parseList(detail.opportunities)" border size="small">
            <el-table-column label="评分" width="60" align="center">
              <template #default="{row}">
                <span :class="['score-badge', scoreClass(row.score)]">{{ row.score }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="buyer" label="采购单位" width="140" show-overflow-tooltip />
            <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
            <el-table-column prop="budget" label="预算" width="80" />
            <el-table-column prop="deadline" label="截止" width="90" />
          </el-table>
        </div>

        <div class="section" v-if="parseList(detail.recommendations).length">
          <h3>💡 AI建议</h3>
          <ul class="rec-list">
            <li v-for="(rec, i) in parseList(detail.recommendations)" :key="i">{{ rec }}</li>
          </ul>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const loading = ref(false)
const generating = ref(false)
const reports = ref([])
const total = ref(0)
const page = ref(1)
const perPage = ref(10)
const showDetail = ref(false)
const detail = ref(null)

const metricLabels = {
  intel_total: '采集情报',
  leads_analyzed: 'AI分析',
  leads_relevant: '相关商机',
  leads_converted: '转入CRM',
  pending_intel: '待分析库存',
  analyzed_not_converted: '待转入',
}

function metricLabel(k) { return metricLabels[k] || k }

function parseMetrics(val) {
  if (!val) return {}
  if (typeof val === 'object') return val
  try { return JSON.parse(val) || {} } catch { return {} }
}

function parseList(val) {
  if (!val) return []
  if (Array.isArray(val)) return val
  try { return JSON.parse(val) || [] } catch { return [] }
}

function scoreClass(s) {
  if (s >= 80) return 'score-high'
  if (s >= 60) return 'score-mid'
  if (s >= 40) return 'score-low'
  return 'score-vlow'
}

async function loadList() {
  loading.value = true
  try {
    const res = await api.get('/intelligence/daily-reports', { page: page.value, per_page: perPage.value })
    reports.value = res.data || []
    total.value = res.total || 0
  } catch (e) {
    ElMessage.error('加载日报列表失败')
  } finally {
    loading.value = false
  }
}

async function generateToday() {
  generating.value = true
  try {
    const res = await api.longPost('/intelligence/daily-report', {})
    ElMessage.success('日报已生成')
    loadList()
    if (res.data) {
      viewReport(res.data.report_date)
    }
  } catch (e) {
    ElMessage.error('生成失败：' + (e.response?.data?.message || e.message))
  } finally {
    generating.value = false
  }
}

async function viewReport(reportDate) {
  try {
    const res = await api.get(`/intelligence/daily-reports/${reportDate}`)
    detail.value = res.data
    showDetail.value = true
  } catch (e) {
    ElMessage.error('加载详情失败')
  }
}

onMounted(() => {
  loadList()
})
</script>

<style scoped>
.report-page { padding: 16px; }
.card-header { display: flex; align-items: center; }
.report-card { margin-bottom: 4px; }
.report-title { font-weight: bold; font-size: 15px; margin-bottom: 6px; }
.report-summary { color: #606266; font-size: 13px; line-height: 1.5; margin-bottom: 8px; }
.report-meta { display: flex; gap: 12px; flex-wrap: wrap; }
.metric-tag { background: #f0f2f5; padding: 2px 8px; border-radius: 4px; font-size: 12px; color: #606266; }
.report-detail h2 { margin: 0 0 4px; }
.detail-date { color: #909399; font-size: 13px; margin-bottom: 16px; }
.section { margin: 16px 0; }
.section h3 { margin: 0 0 8px; font-size: 15px; }
.report-text { line-height: 1.8; color: #303133; }
.metrics-grid { display: flex; gap: 12px; flex-wrap: wrap; }
.metric-item { text-align: center; min-width: 80px; padding: 8px; background: #f5f7fa; border-radius: 8px; }
.metric-value { font-size: 20px; font-weight: bold; color: #409eff; }
.metric-label { font-size: 12px; color: #909399; margin-top: 4px; }
.rec-list { padding-left: 20px; line-height: 1.8; }
.score-badge { display: inline-block; width: 28px; height: 28px; line-height: 28px; border-radius: 50%; text-align: center; font-weight: bold; color: #fff; font-size: 12px; }
.score-high { background: #f56c6c; }
.score-mid { background: #e6a23c; }
.score-low { background: #409eff; }
.score-vlow { background: #909399; }
</style>
