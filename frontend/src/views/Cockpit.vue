<template>
  <div class="cockpit-page">
    <!-- AI 搜索栏 -->
    <el-card class="search-card">
      <div class="search-box">
        <el-input v-model="searchQuery" placeholder="🔍 AI搜索：输入关键词或问题，如'雷达相关商机'、'安徽省采购项目'"
                  size="large" clearable @keyup.enter="aiSearch" style="flex:1">
        </el-input>
        <el-button type="primary" size="large" :loading="searching" @click="aiSearch" style="margin-left:12px">
          AI搜索
        </el-button>
      </div>
      <div v-if="searchResult" class="search-result">
        <div class="ai-answer">{{ searchResult.answer }}</div>
        <div class="search-meta">
          <el-tag size="small">情报: {{ searchResult.raw_count }}</el-tag>
          <el-tag size="small" type="success">商机: {{ searchResult.lead_count }}</el-tag>
          <el-tag size="small" type="warning">CRM: {{ searchResult.crm_count }}</el-tag>
        </div>
        <div v-if="searchResult.lead_results?.length" class="search-leads">
          <div v-for="l in searchResult.lead_results.slice(0,3)" :key="l.id" class="search-lead-item">
            <el-tag :type="scoreType(l.score)" size="small">{{ l.score }}分</el-tag>
            <span class="lead-title">{{ l.title }}</span>
            <span class="lead-buyer">{{ l.buyer }}</span>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 指标卡片 -->
    <div class="metrics-row">
      <el-card class="metric-card" shadow="hover">
        <div class="metric-value" style="color:#409eff">{{ overview.today?.collected || 0 }}</div>
        <div class="metric-label">今日采集</div>
        <div class="metric-sub">总计 {{ overview.total?.intelligence || 0 }}</div>
      </el-card>
      <el-card class="metric-card" shadow="hover">
        <div class="metric-value" style="color:#67c23a">{{ overview.today?.analyzed || 0 }}</div>
        <div class="metric-label">今日AI分析</div>
        <div class="metric-sub">总计 {{ overview.total?.leads || 0 }}</div>
      </el-card>
      <el-card class="metric-card" shadow="hover">
        <div class="metric-value" style="color:#e6a23c">{{ overview.today?.converted || 0 }}</div>
        <div class="metric-label">今日转入CRM</div>
        <div class="metric-sub">总计 {{ overview.total?.converted || 0 }}</div>
      </el-card>
      <el-card class="metric-card" shadow="hover">
        <div class="metric-value" style="color:#f56c6c">{{ overview.total?.high_value || 0 }}</div>
        <div class="metric-label">高价值商机</div>
        <div class="metric-sub">≥60分</div>
      </el-card>
      <el-card class="metric-card" shadow="hover">
        <div class="metric-value" style="color:#909399">{{ overview.total?.pending || 0 }}</div>
        <div class="metric-label">待分析库存</div>
        <div class="metric-sub">待转入 {{ overview.total?.converted || 0 - overview.total?.converted || 0 }}</div>
      </el-card>
    </div>

    <!-- 销售提醒 -->
    <el-card v-if="alerts.length" shadow="hover" style="margin-bottom:16px">
      <template #header>
        <div style="display:flex;align-items:center;justify-content:space-between">
          <span>🔔 销售提醒 <el-badge :value="alertUnread" type="danger" /></span>
          <el-button size="small" text @click="markAllRead">全部已读</el-button>
        </div>
      </template>
      <div v-for="a in alerts.slice(0,5)" :key="a.id" class="alert-item">
        <el-tag :type="alertPriorityType(a.priority)" size="small">{{ alertPriorityLabel(a.priority) }}</el-tag>
        <span class="alert-title" :style="{fontWeight: a.status==='unread'?'bold':'normal'}">{{ a.title }}</span>
        <span class="alert-detail">{{ a.detail }}</span>
        <span class="alert-time">{{ a.created_at?.slice(5,16) }}</span>
      </div>
    </el-card>

    <!-- 图表行 -->
    <div class="chart-row">
      <el-card class="chart-card" shadow="hover">
        <template #header><span>📈 7天趋势</span></template>
        <div ref="trendChart" class="chart-box"></div>
      </el-card>
      <el-card class="chart-card" shadow="hover">
        <template #header><span>📊 评分分布</span></template>
        <div ref="scoreChart" class="chart-box"></div>
      </el-card>
    </div>

    <!-- 商机雷达 -->
    <el-card shadow="hover">
      <template #header>
        <div class="card-header">
          <span>🎯 商机雷达（评分 vs 紧迫性）</span>
          <el-select v-model="radarMinScore" placeholder="最低分" size="small" style="width:100px" @change="loadRadar">
            <el-option label="全部" :value="0" />
            <el-option label="≥40" :value="40" />
            <el-option label="≥60" :value="60" />
            <el-option label="≥80" :value="80" />
          </el-select>
        </div>
      </template>
      <div ref="radarChart" class="chart-box" style="height:400px"></div>
    </el-card>

    <!-- 分布图表 -->
    <div class="chart-row">
      <el-card class="chart-card" shadow="hover">
        <template #header><span>🗺️ 地区分布</span></template>
        <div ref="regionChart" class="chart-box"></div>
      </el-card>
      <el-card class="chart-card" shadow="hover">
        <template #header><span>📋 采购方式</span></template>
        <div ref="methodChart" class="chart-box"></div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import api from '../api'

const overview = ref({})
const searchQuery = ref('')
const searchResult = ref(null)
const searching = ref(false)
const radarMinScore = ref(0)
const alerts = ref([])
const alertUnread = ref(0)

const trendChart = ref(null)
const scoreChart = ref(null)
const radarChart = ref(null)
const regionChart = ref(null)
const methodChart = ref(null)
const charts = []

function scoreType(s) {
  if (s >= 80) return 'danger'
  if (s >= 60) return 'warning'
  if (s >= 40) return ''
  return 'info'
}

async function loadOverview() {
  try {
    const res = await api.get('/cockpit/overview')
    overview.value = res.data || {}
  } catch (e) { /* ignore */ }
}

async function loadTrend() {
  try {
    const res = await api.get('/cockpit/trend?days=7')
    const data = res.data || []
    await nextTick()
    if (!trendChart.value) return
    const chart = echarts.init(trendChart.value)
    charts.push(chart)
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['采集', '分析', '转入CRM'] },
      grid: { left: 40, right: 20, top: 40, bottom: 30 },
      xAxis: { type: 'category', data: data.map(d => d.date.slice(5)) },
      yAxis: { type: 'value' },
      series: [
        { name: '采集', type: 'line', smooth: true, data: data.map(d => d.collected), itemStyle: { color: '#409eff' } },
        { name: '分析', type: 'line', smooth: true, data: data.map(d => d.analyzed), itemStyle: { color: '#67c23a' } },
        { name: '转入CRM', type: 'line', smooth: true, data: data.map(d => d.converted), itemStyle: { color: '#e6a23c' } },
      ]
    })
  } catch (e) { /* ignore */ }
}

async function loadDistribution() {
  try {
    const res = await api.get('/cockpit/distribution')
    const data = res.data || {}
    await nextTick()

    // 评分分布
    if (scoreChart.value) {
      const chart = echarts.init(scoreChart.value)
      charts.push(chart)
      const scores = data.score || []
      chart.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: 40, right: 20, top: 20, bottom: 30 },
        xAxis: { type: 'category', data: scores.map(s => s.range) },
        yAxis: { type: 'value' },
        series: [{ type: 'bar', data: scores.map(s => s.count), itemStyle: { color: '#409eff' } }]
      })
    }

    // 地区分布
    if (regionChart.value) {
      const chart = echarts.init(regionChart.value)
      charts.push(chart)
      const regions = data.region || []
      chart.setOption({
        tooltip: { trigger: 'item' },
        series: [{
          type: 'pie', radius: ['40%', '70%'],
          data: regions.map(r => ({ name: r.region, value: r.c })),
          label: { formatter: '{b}: {c}' }
        }]
      })
    }

    // 采购方式
    if (methodChart.value) {
      const chart = echarts.init(methodChart.value)
      charts.push(chart)
      const methods = data.method || []
      chart.setOption({
        tooltip: { trigger: 'item' },
        series: [{
          type: 'pie', radius: '60%',
          data: methods.map(m => ({ name: m.method, value: m.c })),
          label: { formatter: '{b}: {c} ({d}%)' }
        }]
      })
    }
  } catch (e) { /* ignore */ }
}

async function loadRadar() {
  try {
    const res = await api.get('/cockpit/radar', { min_score: radarMinScore.value, limit: 50 })
    const data = res.data || []
    await nextTick()
    if (!radarChart.value) return
    const chart = echarts.init(radarChart.value)
    charts.push(chart)
    chart.setOption({
      tooltip: {
        formatter: function(p) {
          const d = data[p.dataIndex]
          return `${d.title}<br/>评分:${d.score} | 紧迫:${d.urgency}天<br/>采购:${d.buyer || '-'}`
        }
      },
      grid: { left: 60, right: 30, top: 30, bottom: 50 },
      xAxis: { name: '评分', type: 'value', min: 0, max: 100 },
      yAxis: { name: '紧迫性(天)', type: 'value', inverse: true, min: 0, max: 60 },
      series: [{
        type: 'scatter',
        symbolSize: function(d) {
          return Math.max(10, Math.min(50, d.budget / 2))
        },
        data: data.map(d => [d.score, d.urgency, d]),
        itemStyle: {
          color: function(p) {
            const s = p.data[0]
            if (s >= 80) return '#f56c6c'
            if (s >= 60) return '#e6a23c'
            if (s >= 40) return '#409eff'
            return '#909399'
          }
        }
      }]
    })
  } catch (e) { /* ignore */ }
}

async function loadAlerts() {
  try {
    const res = await api.get('/cockpit/alerts', { status: 'all', per_page: 5 })
    alerts.value = res.data || []
    alertUnread.value = res.unread || 0
  } catch (e) { /* ignore */ }
}

function alertPriorityType(p) {
  if (p === 'urgent') return 'danger'
  if (p === 'high') return 'warning'
  return 'info'
}

function alertPriorityLabel(p) {
  if (p === 'urgent') return '紧急'
  if (p === 'high') return '高优先'
  return '通知'
}

async function markAllRead() {
  try {
    await api.post('/cockpit/alerts/read-all', {})
    loadAlerts()
  } catch (e) { /* ignore */ }
}

async function aiSearch() {
  if (!searchQuery.value.trim()) return
  searching.value = true
  try {
    const res = await api.longPost('/cockpit/ai-search', { query: searchQuery.value })
    if (res && res.code === 200) {
      searchResult.value = res.data
    } else {
      ElMessage.error('搜索失败：' + ((res && res.message) || '未知错误'))
    }
  } catch (e) {
    ElMessage.error('搜索失败：' + (e.response?.data?.message || e.message))
  } finally {
    searching.value = false
  }
}

onMounted(() => {
  loadOverview()
  loadTrend()
  loadDistribution()
  loadRadar()
  loadAlerts()
  window.addEventListener('resize', resizeCharts)
})

function resizeCharts() {
  charts.forEach(c => c.resize())
}

onBeforeUnmount(() => {
  charts.forEach(c => c.dispose())
  window.removeEventListener('resize', resizeCharts)
})
</script>

<style scoped>
.cockpit-page { padding: 16px; }
.search-card { margin-bottom: 16px; }
.search-box { display: flex; align-items: center; }
.search-result { margin-top: 12px; padding: 12px; background: #f5f7fa; border-radius: 8px; }
.ai-answer { line-height: 1.8; color: #303133; margin-bottom: 8px; }
.search-meta { display: flex; gap: 8px; margin-bottom: 8px; }
.search-leads { border-top: 1px solid #ebeef5; padding-top: 8px; }
.search-lead-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; }
.lead-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lead-buyer { color: #909399; font-size: 13px; }
.metrics-row { display: flex; gap: 12px; margin-bottom: 16px; }
.metric-card { flex: 1; text-align: center; }
.metric-value { font-size: 32px; font-weight: bold; }
.metric-label { color: #606266; font-size: 14px; margin-top: 4px; }
.metric-sub { color: #909399; font-size: 12px; margin-top: 2px; }
.chart-row { display: flex; gap: 12px; margin-bottom: 16px; }
.chart-card { flex: 1; }
.chart-box { height: 280px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.alert-item { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid #f0f0f0; }
.alert-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.alert-detail { color: #909399; font-size: 12px; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.alert-time { color: #c0c4cc; font-size: 12px; }
</style>
