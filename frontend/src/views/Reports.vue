<template>
  <div class="reports-page">
    <!-- 顶部工具栏 -->
    <el-card class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <span class="toolbar-title">📊 业绩报表与业务洞察</span>
          <el-tag type="info" size="small">{{ authStore.role === '主任' || authStore.role === '院长' ? '全局视角' : '个人视角' }}</el-tag>
        </div>
        <div class="toolbar-right">
          <span class="year-label">年份：</span>
          <el-select v-model="selectedYear" size="small" style="width: 110px;" @change="onYearChange">
            <el-option v-for="y in availableYears" :key="y" :label="y + '年'" :value="y" />
          </el-select>
          <el-button type="primary" size="small" :loading="exporting" @click="handleExport">
            <span>📥 导出 Excel</span>
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 销售预测卡片 -->
    <el-card class="section-card">
      <template #header>
        <div class="card-header">
          <span>📈 销售预测（基于商机概率加权）</span>
          <span class="header-tip">加权预测 = Σ(商机金额 × 概率%)</span>
        </div>
      </template>
      <div class="forecast-summary">
        <div class="summary-item">
          <div class="summary-label">加权预测总额</div>
          <div class="summary-value primary">¥{{ forecastData.total_forecast || 0 }} <span class="unit">万</span></div>
        </div>
        <div class="summary-item">
          <div class="summary-label">已签约金额</div>
          <div class="summary-value success">¥{{ forecastData.total_signed || 0 }} <span class="unit">万</span></div>
        </div>
        <div class="summary-item">
          <div class="summary-label">预测准确率</div>
          <div class="summary-value warning">{{ forecastData.accuracy || 0 }}<span class="unit">%</span></div>
        </div>
      </div>
      <div ref="forecastChart" class="chart-lg"></div>
    </el-card>

    <!-- 阶段转化 + 自动洞察 双列 -->
    <el-row :gutter="20">
      <el-col :span="14">
        <el-card class="section-card">
          <template #header>
            <span>🎯 阶段转化漏斗</span>
          </template>
          <div ref="conversionChart" class="chart-md"></div>
          <el-table :data="conversionData.stages" stripe size="small" style="margin-top: 12px;">
            <el-table-column prop="name" label="阶段" width="100" />
            <el-table-column prop="count" label="商机数" width="80" align="center" />
            <el-table-column label="商机金额(万)" width="120" align="right">
              <template #default="scope">{{ scope.row.amount }}</template>
            </el-table-column>
            <el-table-column label="转化率" width="100" align="center">
              <template #default="scope">
                <el-tag :type="getConversionTagType(scope.row.conversion_rate)" size="small">
                  {{ scope.row.conversion_rate }}%
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="流失率" width="100" align="center">
              <template #default="scope">
                <span :class="{ 'drop-high': scope.row.drop_rate >= 50 }">{{ scope.row.drop_rate }}%</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card class="section-card insight-card">
          <template #header>
            <div class="card-header">
              <span>💡 自动业务洞察</span>
              <el-tag v-if="insightsData.total > 0" type="danger" size="small">{{ insightsData.total }} 条</el-tag>
            </div>
          </template>
          <div class="insight-list">
            <div v-for="(ins, idx) in insightsData.insights" :key="idx" class="insight-item" :class="'severity-' + ins.severity">
              <div class="insight-icon">{{ getInsightIcon(ins.type) }}</div>
              <div class="insight-content">
                <div class="insight-title">
                  <el-tag :type="getSeverityTagType(ins.severity)" size="small" effect="dark">{{ getSeverityLabel(ins.severity) }}</el-tag>
                  <span class="insight-name">{{ ins.title }}</span>
                </div>
                <div class="insight-detail">{{ ins.detail }}</div>
                <div class="insight-suggestion">💡 {{ ins.suggestion }}</div>
              </div>
            </div>
            <div v-if="insightsData.insights.length === 0" class="empty-insight">
              <span>✅ 暂无异常洞察，各项指标运行正常</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 团队业绩对比（仅主任/院长） -->
    <el-card v-if="isAdmin" class="section-card">
      <template #header>
        <div class="card-header">
          <span>👥 团队业绩对比</span>
          <span class="header-tip">按负责人统计商机/合同/回款/预测/胜率</span>
        </div>
      </template>
      <div ref="teamChart" class="chart-lg"></div>
      <el-table :data="teamData.members" stripe size="small" style="margin-top: 12px;">
        <el-table-column type="index" label="排名" width="60" align="center" />
        <el-table-column prop="name" label="负责人" width="100" />
        <el-table-column prop="role" label="角色" width="80" />
        <el-table-column prop="business_count" label="商机数" width="80" align="center" />
        <el-table-column label="商机金额(万)" width="120" align="right">
          <template #default="scope">{{ scope.row.business_amount }}</template>
        </el-table-column>
        <el-table-column prop="contract_count" label="合同数" width="80" align="center" />
        <el-table-column label="合同金额(万)" width="120" align="right">
          <template #default="scope">{{ scope.row.contract_amount }}</template>
        </el-table-column>
        <el-table-column label="回款金额(万)" width="120" align="right">
          <template #default="scope">{{ scope.row.payment_amount }}</template>
        </el-table-column>
        <el-table-column label="加权预测(万)" width="120" align="right">
          <template #default="scope">{{ scope.row.forecast_amount }}</template>
        </el-table-column>
        <el-table-column label="胜率" width="80" align="center">
          <template #default="scope">
            <el-tag :type="scope.row.win_rate >= 50 ? 'success' : (scope.row.win_rate >= 20 ? 'warning' : 'danger')" size="small">
              {{ scope.row.win_rate }}%
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 同比环比趋势 -->
    <el-card class="section-card">
      <template #header>
        <div class="card-header">
          <span>📊 同比环比趋势</span>
          <el-radio-group v-model="trendRange" size="small" @change="fetchTrendComparison">
            <el-radio-button label="month">本月 vs 上月</el-radio-button>
            <el-radio-button label="quarter">本季 vs 上季</el-radio-button>
            <el-radio-button label="year">本年 vs 去年</el-radio-button>
          </el-radio-group>
        </div>
      </template>
      <div class="trend-metrics">
        <div v-for="metric in trendMetrics" :key="metric.key" class="metric-card" :class="getMetricClass(metric)">
          <div class="metric-label">{{ metric.label }}</div>
          <div class="metric-values">
            <span class="metric-current">{{ metric.current }}</span>
            <span class="metric-previous">上期 {{ metric.previous }}</span>
          </div>
          <div class="metric-growth" :class="{ 'up': metric.growth_rate > 0, 'down': metric.growth_rate < 0 }">
            {{ metric.growth_rate > 0 ? '↑' : (metric.growth_rate < 0 ? '↓' : '—') }}
            {{ Math.abs(metric.growth_rate) }}%
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useAuthStore } from '../stores/auth'
import { ElMessage } from 'element-plus'
import api from '../api'
import * as echarts from 'echarts'

const authStore = useAuthStore()
const isAdmin = computed(() => authStore.role === '主任' || authStore.role === '院长')

// 年份选择
const currentYear = new Date().getFullYear()
const selectedYear = ref(currentYear)
const availableYears = computed(() => {
  const years = []
  for (let y = currentYear; y >= 2019; y--) years.push(y)
  return years
})

// 数据
const forecastData = ref({ months: [], forecast_data: [], signed_data: [], total_forecast: 0, total_signed: 0, accuracy: 0 })
const conversionData = ref({ stages: [] })
const teamData = ref({ members: [] })
const insightsData = ref({ insights: [], total: 0 })
const trendMetrics = ref([])
const trendRange = ref('month')
const exporting = ref(false)

// 图表 DOM 引用
const forecastChart = ref(null)
const conversionChart = ref(null)
const teamChart = ref(null)
let forecastChartInstance = null
let conversionChartInstance = null
let teamChartInstance = null

// 数据获取
const fetchForecast = async () => {
  try {
    const res = await api.get('/reports/forecast', { year: selectedYear.value })
    if (res.code === 200) {
      forecastData.value = res.data
      updateForecastChart()
    }
  } catch (e) { console.error('销售预测获取失败', e) }
}

const fetchConversion = async () => {
  try {
    const res = await api.get('/reports/conversion')
    if (res.code === 200) {
      conversionData.value = res.data
      updateConversionChart()
    }
  } catch (e) { console.error('阶段转化获取失败', e) }
}

const fetchTeamPerformance = async () => {
  if (!isAdmin.value) return
  try {
    const res = await api.get('/reports/team-performance')
    if (res.code === 200) {
      teamData.value = res.data
      updateTeamChart()
    }
  } catch (e) { console.error('团队业绩获取失败', e) }
}

const fetchInsights = async () => {
  try {
    const res = await api.get('/reports/insights', { year: selectedYear.value })
    if (res.code === 200) {
      insightsData.value = res.data
    }
  } catch (e) { console.error('洞察获取失败', e) }
}

const fetchTrendComparison = async () => {
  try {
    const res = await api.get('/reports/trend-comparison', { time_range: trendRange.value, year: selectedYear.value })
    if (res.code === 200) {
      const labelMap = {
        total_customers: '新增客户数',
        total_business: '新增商机数',
        total_contracts: '新增合同数',
        contracts_amount: '合同总额(万)',
        total_payments: '回款总额(万)'
      }
      trendMetrics.value = Object.entries(res.data.metrics).map(([key, val]) => {
        const isAmount = key === 'contracts_amount' || key === 'total_payments'
        return {
          key,
          label: labelMap[key] || key,
          current: isAmount ? (val.current / 10000).toFixed(1) : val.current,
          previous: isAmount ? (val.previous / 10000).toFixed(1) : val.previous,
          growth_rate: val.growth_rate
        }
      })
    }
  } catch (e) { console.error('环比趋势获取失败', e) }
}

const onYearChange = () => {
  fetchForecast()
  fetchInsights()
  fetchTrendComparison()
}

// Excel 导出
const handleExport = async () => {
  exporting.value = true
  try {
    const token = authStore.token
    const response = await fetch(`/api/reports/export?year=${selectedYear.value}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
    if (!response.ok) {
      throw new Error('导出失败')
    }
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    // 从响应头获取文件名，兜底使用默认名
    const disposition = response.headers.get('Content-Disposition') || ''
    const match = disposition.match(/filename\*?=(?:UTF-8'')?([^;]+)/i)
    const filename = match ? decodeURIComponent(match[1].replace(/['"]/g, '')) : `销售业绩报表_${selectedYear.value}.xlsx`
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    ElMessage.success('报表导出成功')
  } catch (e) {
    console.error('导出失败', e)
    ElMessage.error('报表导出失败：' + e.message)
  } finally {
    exporting.value = false
  }
}

// 图表更新
const updateForecastChart = () => {
  if (!forecastChartInstance) return
  forecastChartInstance.setOption({
    tooltip: { trigger: 'axis', formatter: (params) => {
      let html = params[0].axisValue + '<br/>'
      params.forEach(p => {
        html += `${p.marker} ${p.seriesName}: ¥${p.value} 万<br/>`
      })
      return html
    }},
    legend: { data: ['加权预测', '已签约'], bottom: 0 },
    grid: { left: '3%', right: '4%', bottom: '12%', containLabel: true },
    xAxis: { type: 'category', data: forecastData.value.months },
    yAxis: { type: 'value', name: '万元' },
    series: [
      { name: '加权预测', type: 'bar', data: forecastData.value.forecast_data, itemStyle: { color: '#5470c6' } },
      { name: '已签约', type: 'bar', data: forecastData.value.signed_data, itemStyle: { color: '#91cc75' } }
    ]
  })
}

const updateConversionChart = () => {
  if (!conversionChartInstance) return
  const stages = conversionData.value.stages
  const colors = ['#91cc75', '#5470c6', '#fac858', '#ee6666', '#73c0de', '#9a60b4']
  conversionChartInstance.setOption({
    tooltip: { trigger: 'item', formatter: (p) => {
      const stage = stages[p.dataIndex] || {}
      return `${p.name}<br/>商机数: ${stage.count || 0} 个<br/>金额: ${stage.amount || 0} 万<br/>转化率: ${stage.conversion_rate || 0}%<br/>流失率: ${stage.drop_rate || 0}%`
    }},
    series: [{
      name: '阶段转化',
      type: 'funnel',
      left: '10%',
      top: 10,
      bottom: 10,
      width: '80%',
      min: 0,
      max: stages.length > 0 ? Math.max(...stages.map(s => s.count)) : 100,
      minSize: '20%',
      maxSize: '100%',
      sort: 'descending',
      gap: 2,
      label: { show: true, position: 'inside', formatter: (p) => {
        const stage = stages[p.dataIndex] || {}
        return `${p.name}\n${stage.count}个 (${stage.conversion_rate}%)`
      }},
      itemStyle: { borderColor: '#fff', borderWidth: 1 },
      data: stages.map((s, i) => ({
        value: s.count,
        name: s.name,
        itemStyle: { color: s.conversion_rate < 50 && i > 0 ? '#ee6666' : colors[i] }
      }))
    }]
  })
}

const updateTeamChart = () => {
  if (!teamChartInstance) return
  const members = teamData.value.members.slice(0, 10)  // 取前10避免拥挤
  teamChartInstance.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['商机金额', '合同金额', '回款金额'], bottom: 0 },
    grid: { left: '3%', right: '4%', bottom: '12%', containLabel: true },
    xAxis: { type: 'category', data: members.map(m => m.name), axisLabel: { rotate: 30 } },
    yAxis: { type: 'value', name: '万元' },
    series: [
      { name: '商机金额', type: 'bar', data: members.map(m => m.business_amount), itemStyle: { color: '#5470c6' } },
      { name: '合同金额', type: 'bar', data: members.map(m => m.contract_amount), itemStyle: { color: '#91cc75' } },
      { name: '回款金额', type: 'bar', data: members.map(m => m.payment_amount), itemStyle: { color: '#fac858' } }
    ]
  })
}

// 辅助函数
const getConversionTagType = (rate) => {
  if (rate >= 70) return 'success'
  if (rate >= 40) return 'warning'
  return 'danger'
}

const getInsightIcon = (type) => {
  const map = { bottleneck: '🚧', anomaly: '⚠️', top_performer: '🏆', risk_alert: '🚨', opportunity: '🎯' }
  return map[type] || '📌'
}

const getSeverityTagType = (sev) => ({ high: 'danger', medium: 'warning', info: 'info' }[sev] || 'info')
const getSeverityLabel = (sev) => ({ high: '高', medium: '中', info: '低' }[sev] || sev)

const getMetricClass = (metric) => {
  if (metric.growth_rate > 0) return 'metric-up'
  if (metric.growth_rate < 0) return 'metric-down'
  return 'metric-flat'
}

// 图表初始化
const initCharts = () => {
  if (forecastChart.value) {
    forecastChartInstance = echarts.init(forecastChart.value)
  }
  if (conversionChart.value) {
    conversionChartInstance = echarts.init(conversionChart.value)
  }
  if (teamChart.value && isAdmin.value) {
    teamChartInstance = echarts.init(teamChart.value)
  }
}

const handleResize = () => {
  forecastChartInstance?.resize()
  conversionChartInstance?.resize()
  teamChartInstance?.resize()
}

watch(selectedYear, () => {
  nextTick(() => {
    updateForecastChart()
    if (isAdmin.value) updateTeamChart()
  })
})

onMounted(async () => {
  await nextTick()
  initCharts()
  fetchForecast()
  fetchConversion()
  fetchTeamPerformance()
  fetchInsights()
  fetchTrendComparison()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  forecastChartInstance?.dispose()
  conversionChartInstance?.dispose()
  teamChartInstance?.dispose()
})
</script>

<style scoped>
.reports-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.toolbar-card {
  background: white;
  border-radius: 14px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toolbar-title {
  font-size: 18px;
  font-weight: 600;
  color: #1a1a2e;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.year-label {
  font-size: 13px;
  color: #666;
}

.section-card {
  background: white;
  border-radius: 14px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}

.header-tip {
  font-size: 12px;
  color: #999;
  font-weight: normal;
}

.forecast-summary {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}

.summary-item {
  flex: 1;
  padding: 16px;
  background: linear-gradient(135deg, rgba(78, 205, 196, 0.08) 0%, rgba(68, 160, 141, 0.05) 100%);
  border-radius: 10px;
  text-align: center;
}

.summary-label {
  font-size: 13px;
  color: #666;
  margin-bottom: 8px;
}

.summary-value {
  font-size: 28px;
  font-weight: bold;
}

.summary-value.primary { color: #5470c6; }
.summary-value.success { color: #91cc75; }
.summary-value.warning { color: #fac858; }

.unit {
  font-size: 14px;
  font-weight: normal;
  color: #999;
}

.chart-lg { height: 320px; }
.chart-md { height: 260px; }

.insight-card {
  height: 100%;
}

.insight-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 520px;
  overflow-y: auto;
}

.insight-item {
  display: flex;
  gap: 10px;
  padding: 12px;
  border-radius: 8px;
  border-left: 4px solid #ddd;
  background: #fafafa;
}

.insight-item.severity-high {
  border-left-color: #ee6666;
  background: rgba(238, 102, 102, 0.05);
}

.insight-item.severity-medium {
  border-left-color: #fac858;
  background: rgba(250, 200, 88, 0.05);
}

.insight-item.severity-info {
  border-left-color: #5470c6;
  background: rgba(84, 112, 198, 0.05);
}

.insight-icon {
  font-size: 20px;
}

.insight-content {
  flex: 1;
}

.insight-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.insight-name {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.insight-detail {
  font-size: 12px;
  color: #666;
  margin-bottom: 4px;
}

.insight-suggestion {
  font-size: 12px;
  color: #4ecdc4;
  font-style: italic;
}

.empty-insight {
  text-align: center;
  padding: 40px;
  color: #999;
  font-size: 14px;
}

.trend-metrics {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 16px;
}

.metric-card {
  padding: 16px;
  border-radius: 10px;
  background: #fafafa;
  border-top: 3px solid #ddd;
}

.metric-card.metric-up {
  border-top-color: #91cc75;
  background: rgba(145, 204, 117, 0.05);
}

.metric-card.metric-down {
  border-top-color: #ee6666;
  background: rgba(238, 102, 102, 0.05);
}

.metric-card.metric-flat {
  border-top-color: #fac858;
}

.metric-label {
  font-size: 13px;
  color: #666;
  margin-bottom: 8px;
}

.metric-values {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
}

.metric-current {
  font-size: 22px;
  font-weight: bold;
  color: #1a1a2e;
}

.metric-previous {
  font-size: 12px;
  color: #999;
}

.metric-growth {
  font-size: 14px;
  font-weight: 600;
}

.metric-growth.up { color: #91cc75; }
.metric-growth.down { color: #ee6666; }

.drop-high {
  color: #ee6666;
  font-weight: 600;
}

:deep(.el-card__header) {
  padding: 14px 18px;
}

:deep(.el-card__body) {
  padding: 18px;
}
</style>
