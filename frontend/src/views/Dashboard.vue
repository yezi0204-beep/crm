<template>
  <div class="dashboard">
    <div class="stats-row">
      <el-card class="stat-card">
        <div class="stat-icon blue">👥</div>
        <div class="stat-content">
          <div class="stat-value">{{ dashboardData.total_customers }}</div>
          <div class="stat-label">客户总数</div>
          <div class="stat-trend" :class="getTrendClass(dashboardData.trends?.total_customers)">
            {{ formatTrend(dashboardData.trends?.total_customers) }}
          </div>
        </div>
      </el-card>

      <el-card class="stat-card">
        <div class="stat-icon green">🎯</div>
        <div class="stat-content">
          <div class="stat-value">{{ dashboardData.total_business }}</div>
          <div class="stat-label">商机总数</div>
          <div class="stat-trend" :class="getTrendClass(dashboardData.trends?.total_business)">
            {{ formatTrend(dashboardData.trends?.total_business) }}
          </div>
        </div>
      </el-card>

      <el-card class="stat-card">
        <div class="stat-icon purple">📜</div>
        <div class="stat-content">
          <div class="stat-value">{{ dashboardData.total_contracts }}</div>
          <div class="stat-label">合同总数</div>
          <div class="stat-trend" :class="getTrendClass(dashboardData.trends?.total_contracts)">
            {{ formatTrend(dashboardData.trends?.total_contracts) }}
          </div>
        </div>
      </el-card>

      <el-card class="stat-card">
        <div class="stat-icon orange">💰</div>
        <div class="stat-content">
          <div class="stat-value">{{ formatAmount(dashboardData.contracts_amount) }}</div>
          <div class="stat-label">合同总额(万)</div>
          <div class="stat-trend" :class="getTrendClass(dashboardData.trends?.contracts_amount)">
            {{ formatTrend(dashboardData.trends?.contracts_amount) }}
          </div>
        </div>
      </el-card>

      <el-card class="stat-card">
        <div class="stat-icon red">💵</div>
        <div class="stat-content">
          <div class="stat-value">{{ formatAmount(dashboardData.total_payments) }}</div>
          <div class="stat-label">累计回款(万)</div>
          <div class="stat-trend" :class="getTrendClass(dashboardData.trends?.total_payments)">
            {{ formatTrend(dashboardData.trends?.total_payments) }}
          </div>
        </div>
      </el-card>
    </div>
    
    <!-- AI 商机驾驶舱 -->
    <el-card class="ai-cockpit-card">
      <template #header>
        <div class="card-header">
          <span>🚀 AI商机驾驶舱</span>
          <el-button size="small" type="primary" text @click="$router.push({path:'/intelligence', query:{tab:'ai-leads'}})">查看AI商机 →</el-button>
        </div>
      </template>
      <div class="ai-stats-row">
        <div v-for="c in aiCards" :key="c.label" class="ai-stat" :style="{ background: c.bg }">
          <div class="ai-stat-num">{{ c.value }}</div>
          <div class="ai-stat-label">{{ c.label }}</div>
        </div>
      </div>
      <el-row :gutter="16" style="margin-top:16px">
        <el-col :span="12">
          <div class="ai-chart-title">商机数量趋势</div>
          <el-radio-group v-model="aiTrendDays" size="small" style="margin-bottom:8px" @change="fetchAiTrend">
            <el-radio-button :label="7">近7天</el-radio-button>
            <el-radio-button :label="30">近30天</el-radio-button>
          </el-radio-group>
          <div ref="aiTrendChart" class="ai-chart" style="height:220px"></div>
        </el-col>
        <el-col :span="6">
          <div class="ai-chart-title">行业分布</div>
          <div ref="aiIndustryChart" class="ai-chart" style="height:260px"></div>
        </el-col>
        <el-col :span="6">
          <div class="ai-chart-title">金额分布</div>
          <div ref="aiAmountChart" class="ai-chart" style="height:260px"></div>
        </el-col>
      </el-row>
      <el-row :gutter="16" style="margin-top:8px">
        <el-col :span="12">
          <div class="ai-chart-title">地区分布 Top10</div>
          <div ref="aiRegionChart" class="ai-chart" style="height:220px"></div>
        </el-col>
        <el-col :span="12">
          <div class="ai-chart-title">竞争对手中标动态（近30天）</div>
          <div ref="aiCompChart" class="ai-chart" style="height:220px"></div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 月度验收/回款统计 -->
    <el-card class="chart-card">
      <template #header>
        <div class="card-header">
          <span>💰 财务看板（{{ financeYear }}年）</span>
          <el-select v-model="financeYear" size="small" style="width: 100px;" @change="fetchMonthlyFinance">
            <el-option v-for="y in availableYears" :key="y" :label="y + '年'" :value="y" />
          </el-select>
        </div>
      </template>

      <!-- 关键财务指标 -->
      <div class="finance-metrics">
        <div class="fm-item">
          <div class="fm-value">{{ formatWan(financeData.metrics?.total_contract_amt) }}</div>
          <div class="fm-label">合同总额(万)</div>
        </div>
        <div class="fm-item">
          <div class="fm-value blue">{{ formatWan(financeData.metrics?.cumulative_acceptance) }}</div>
          <div class="fm-label">累计验收(万)</div>
        </div>
        <div class="fm-item">
          <div class="fm-value orange">{{ formatWan(financeData.metrics?.pending_acceptance) }}</div>
          <div class="fm-label">待验收(万)</div>
        </div>
        <div class="fm-item">
          <div class="fm-value blue">{{ financeData.metrics?.acceptance_rate ?? 0 }}%</div>
          <div class="fm-label">验收率</div>
        </div>
        <div class="fm-item">
          <div class="fm-value green">{{ formatWan(financeData.metrics?.cumulative_payment) }}</div>
          <div class="fm-label">累计回款(万)</div>
        </div>
        <div class="fm-item">
          <div class="fm-value orange">{{ formatWan(financeData.metrics?.pending_payment) }}</div>
          <div class="fm-label">待回款(万)</div>
        </div>
        <div class="fm-item">
          <div class="fm-value green">{{ financeData.metrics?.payment_rate ?? 0 }}%</div>
          <div class="fm-label">回款率</div>
        </div>
      </div>

      <!-- 年度实际/预计汇总 -->
      <div class="finance-summary">
        <div class="finance-summary-item">
          <span class="finance-label">本年已验收（实际）</span>
          <span class="finance-value">{{ formatWan(financeData.summary?.actual_acceptance) }} 万</span>
        </div>
        <div class="finance-summary-item">
          <span class="finance-label">本年已回款（实际）</span>
          <span class="finance-value">{{ formatWan(financeData.summary?.actual_payment) }} 万</span>
        </div>
        <div class="finance-summary-item">
          <span class="finance-label">本年待验收（预计）</span>
          <span class="finance-value expected">{{ formatWan(financeData.summary?.expected_acceptance) }} 万</span>
        </div>
        <div class="finance-summary-item">
          <span class="finance-label">本年待回款（预计）</span>
          <span class="finance-value expected">{{ formatWan(financeData.summary?.expected_payment) }} 万</span>
        </div>
      </div>

      <!-- 月度 + 季度图表 -->
      <el-row :gutter="16">
        <el-col :span="15">
          <div class="finance-sub-title">月度验收与回款（深色=实际，浅色=预计）</div>
          <div ref="financeChart" class="finance-chart-box"></div>
        </el-col>
        <el-col :span="9">
          <div class="finance-sub-title">季度汇总</div>
          <div ref="quarterChart" class="finance-chart-box"></div>
        </el-col>
      </el-row>

      <!-- 负责人统计 + 月度填报明细 -->
      <el-row :gutter="16" style="margin-top: 16px;">
        <el-col :span="9">
          <div class="finance-sub-title">按负责人统计（全量合同）</div>
          <el-table :data="financeData.owners || []" border stripe size="small" max-height="320">
            <el-table-column prop="owner_name" label="负责人" min-width="80" />
            <el-table-column label="合同额(万)" align="right" width="90">
              <template #default="{ row }">{{ formatWan(row.contract_amt) }}</template>
            </el-table-column>
            <el-table-column label="已回款(万)" align="right" width="90">
              <template #default="{ row }">{{ formatWan(row.paid) }}</template>
            </el-table-column>
            <el-table-column label="待回款(万)" align="right" width="90">
              <template #default="{ row }">{{ formatWan(row.pending_pay) }}</template>
            </el-table-column>
            <el-table-column label="回款率" align="right" width="70">
              <template #default="{ row }">{{ row.contract_amt ? ((row.paid / row.contract_amt) * 100).toFixed(1) : 0 }}%</template>
            </el-table-column>
          </el-table>
        </el-col>
        <el-col :span="15">
          <div class="finance-sub-title">
            月度预计填报明细
            <el-button size="small" text type="primary" @click="exportForecastDetails" style="margin-left: 8px;">导出</el-button>
          </div>
          <el-table :data="financeData.details || []" border stripe size="small" max-height="320" empty-text="暂无填报数据，请到合同管理点击「月度预计」填报">
            <el-table-column label="月份" width="70" align="center">
              <template #default="{ row }">
                <el-tag :type="row.is_actual ? 'info' : 'warning'" size="small">{{ row.month_label }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="contract_name" label="合同名称" min-width="160" show-overflow-tooltip />
            <el-table-column prop="owner_name" label="负责人" width="80" />
            <el-table-column label="预计验收(万)" align="right" width="100">
              <template #default="{ row }">{{ formatWan(row.expected_acceptance) }}</template>
            </el-table-column>
            <el-table-column label="预计回款(万)" align="right" width="100">
              <template #default="{ row }">{{ formatWan(row.expected_payment) }}</template>
            </el-table-column>
          </el-table>
        </el-col>
      </el-row>
    </el-card>

    <div class="main-row">
      <div class="left-column">
        <el-card class="chart-card">
          <template #header>
            <div class="card-header">
              <span>📊 业务趋势分析</span>
              <div class="time-range">
                <el-radio-group v-model="timeRange">
                  <el-radio-button label="month">本月</el-radio-button>
                  <el-radio-button label="quarter">本季度</el-radio-button>
                  <el-radio-button label="year">本年</el-radio-button>
                </el-radio-group>
                <el-select v-model="selectedYear" size="small" style="width: 100px; margin-left: 12px;" @change="onYearChange">
                  <el-option v-for="y in availableYears" :key="y" :label="y + '年'" :value="y" />
                </el-select>
              </div>
            </div>
          </template>
          <div ref="trendChart" class="chart"></div>
        </el-card>
        
        <el-card class="chart-card">
          <template #header>
            <span>🎯 销售漏斗</span>
          </template>
          <div ref="funnelChart" class="chart"></div>
        </el-card>
      </div>
      
      <div class="right-column">
        <el-card class="ranking-card">
          <template #header>
            <span>🏆 销售排行榜</span>
          </template>
          <div class="ranking-list">
            <div v-for="(item, index) in salesRanking" :key="item.name" class="ranking-item">
              <div class="rank-badge" :class="'rank-' + (index + 1)">{{ index + 1 }}</div>
              <div class="rank-info">
                <div class="rank-name">{{ item.name }}</div>
                <div class="rank-role">{{ item.role }}</div>
              </div>
              <div class="rank-amount">¥{{ formatAmount(item.amount) }}万</div>
            </div>
          </div>
        </el-card>
        
        <el-card class="recent-card">
          <template #header>
            <span>📋 近期合同</span>
            <el-button size="small" type="text" @click="router.push('/contracts')">查看全部 →</el-button>
          </template>
          <el-table :data="recentContracts" stripe size="small">
            <el-table-column prop="contract_name" label="合同名称" min-width="150">
              <template #default="scope">
                <span class="contract-link" @click="router.push('/contracts')">{{ scope.row.contract_name }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="total_amt" label="金额(万)" width="100" :formatter="(row, column, cellValue) => formatAmount(cellValue)" />
            <el-table-column prop="sign_date" label="签约日期" width="110">
              <template #default="scope">
                {{ formatDate(scope.row.sign_date) }}
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="80">
              <template #default="scope">
                <el-tag :type="getStatusType(scope.row.status)" size="small">{{ scope.row.status }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
        
        <el-card class="alert-card">
          <template #header>
            <div class="card-header">
              <span>⚠️ 待办提醒</span>
              <el-button v-if="alerts.length > 0" size="small" type="text" @click="router.push('/alerts')">查看全部 →</el-button>
            </div>
          </template>
          <div class="alert-list">
            <div v-for="alert in alerts" :key="alert.id || alert.due_date + alert.title" class="alert-item">
              <span class="alert-icon">{{ getAlertIcon(alert.type) }}</span>
              <span class="alert-text">{{ alert.detail }}</span>
              <span class="alert-time">{{ formatDueDate(alert.due_date) }}</span>
            </div>
            <div v-if="alerts.length === 0" class="alert-empty">
              ✅ 暂无待办提醒
            </div>
          </div>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, computed, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'

const router = useRouter()

const dashboardData = ref({
  total_customers: 0,
  total_business: 0,
  total_contracts: 0,
  contracts_amount: 0,
  total_payments: 0
})

const recentContracts = ref([])
const salesRanking = ref([])

const alerts = ref([])

// 月度验收/回款统计
const financeData = ref({})
const financeYear = ref(new Date().getFullYear())
const financeChart = ref(null)
const quarterChart = ref(null)
let chartFinance = null
let chartQuarter = null

const timeRange = ref('month')
const currentYear = new Date().getFullYear()
const selectedYear = ref(currentYear)
const availableYears = computed(() => {
  const years = []
  for (let y = currentYear; y >= 2019; y--) {
    years.push(y)
  }
  return years
})

const trendChart = ref(null)
const funnelChart = ref(null)
// AI 商机驾驶舱图表 refs
const aiTrendChart = ref(null)
const aiIndustryChart = ref(null)
const aiAmountChart = ref(null)
const aiRegionChart = ref(null)
let chart1 = null
let chart2 = null

// 元 → 万元，精确到分：0.000001万元 = 0.01元，去尾零显示
const formatAmount = (value) => {
  return Number(((value || 0) / 10000).toFixed(6))
}

const formatWan = (value) => {
  return Number(((value || 0) / 10000).toFixed(6))
}

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  return dateStr.substring(0, 10)
}

const exportForecastDetails = () => {
  const details = financeData.value?.details || []
  if (!details.length) {
    ElMessage.info('暂无填报数据可导出')
    return
  }
  const escapeCsv = (v) => {
    if (v === null || v === undefined) return '""'
    return '"' + String(v).replace(/"/g, '""') + '"'
  }
  const cols = [
    { label: '月份', get: r => r.month_label || '' },
    { label: '合同名称', get: r => r.contract_name || '' },
    { label: '负责人', get: r => r.owner_name || '' },
    { label: '预计验收(万)', get: r => Number(((r.expected_acceptance || 0) / 10000).toFixed(6)) },
    { label: '预计回款(万)', get: r => Number(((r.expected_payment || 0) / 10000).toFixed(6)) }
  ]
  let csv = '\uFEFF' + cols.map(c => escapeCsv(c.label)).join(',') + '\n'
  details.forEach(r => {
    csv += cols.map(c => escapeCsv(c.get(r))).join(',') + '\n'
  })
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  const url = URL.createObjectURL(blob)
  link.setAttribute('href', url)
  link.setAttribute('download', `月度预计填报明细_${selectedYear.value}.csv`)
  link.style.visibility = 'hidden'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

// 真实趋势百分比：基于后端 trends 字段的 growth_rate
const formatTrend = (trend) => {
  if (!trend || trend.growth_rate === null || trend.growth_rate === undefined) return '— 环比'
  const rate = trend.growth_rate
  if (rate > 0) return `↑ ${rate}% 环比`
  if (rate < 0) return `↓ ${Math.abs(rate)}% 环比`
  return '持平 环比'
}

const getTrendClass = (trend) => {
  if (!trend || trend.growth_rate === null || trend.growth_rate === undefined) return 'flat'
  if (trend.growth_rate > 0) return 'up'
  if (trend.growth_rate < 0) return 'down'
  return 'flat'
}

// 预警图标映射
const getAlertIcon = (type) => {
  const map = { payment: '💸', acceptance: '✅', business: '📋' }
  return map[type] || '⚠️'
}

// 预警日期截断到 YYYY-MM-DD
const formatDueDate = (dateStr) => {
  if (!dateStr) return ''
  return dateStr.substring(0, 10)
}

// 真实预警：取前 5 条
const fetchAlerts = async () => {
  try {
    const response = await api.get('/alerts')
    if (response.code === 200 && response.data) {
      alerts.value = (response.data.alerts || []).slice(0, 5)
    }
  } catch (e) {
    console.error('获取预警失败', e)
  }
}

const onYearChange = () => {
  timeRange.value = 'year'
  fetchDashboardData()
}

const fetchDashboardData = async () => {
  const params = { time_range: timeRange.value }
  if (timeRange.value === 'year') {
    params.year = selectedYear.value
  }
  const response = await api.get('/dashboard', params)
  if (response.code === 200) {
    dashboardData.value = response.data
    salesRanking.value = response.data.sales_ranking || []
    updateTrendChart()
    updateFunnelChart()
  }
}

const fetchBusinessStats = async () => {
  try {
    const response = await api.get('/business', { status: 'active' })
    if (response.code === 200 && response.data) {
      const stats = {
        '引导需求阶段': 0,
        '能力展示阶段': 0,
        '方案确定阶段': 0,
        '商务谈判阶段': 0,
        '合同签订阶段': 0,
        '销售实现': 0
      }
      
      response.data.forEach(b => {
        const prob = b.probability || 0
        if (prob < 30) stats['引导需求阶段']++
        else if (prob < 60) stats['能力展示阶段']++
        else if (prob < 80) stats['方案确定阶段']++
        else if (prob < 90) stats['商务谈判阶段']++
        else if (prob < 100) stats['合同签订阶段']++
        else stats['销售实现']++
      })
      
      return stats
    }
  } catch (e) {
    console.error('获取商机统计失败', e)
  }
  return null
}

const updateFunnelChart = async () => {
  if (!chart2) return

  const stats = await fetchBusinessStats()
  if (!stats) return

  chart2.setOption({
    series: [{
      data: [
        { value: stats['引导需求阶段'], name: '引导需求阶段', itemStyle: { color: '#91cc75' } },
        { value: stats['能力展示阶段'], name: '能力展示阶段', itemStyle: { color: '#5470c6' } },
        { value: stats['方案确定阶段'], name: '方案确定阶段', itemStyle: { color: '#fac858' } },
        { value: stats['商务谈判阶段'], name: '商务谈判阶段', itemStyle: { color: '#ee6666' } },
        { value: stats['合同签订阶段'], name: '合同签订阶段', itemStyle: { color: '#73c0de' } },
        { value: stats['销售实现'], name: '销售实现', itemStyle: { color: '#9a60b4' } }
      ]
    }]
  })
}

const fetchRecentContracts = async () => {
  const response = await api.get('/contracts')
  if (response.code === 200) {
    recentContracts.value = response.data.slice(0, 5)
  }
}

const fetchMonthlyFinance = async () => {
  try {
    const res = await api.get('/dashboard/monthly-finance', { year: financeYear.value })
    if (res.code === 200) {
      financeData.value = res.data
      updateFinanceChart()
    }
  } catch (e) {
    console.error('获取月度财务统计失败', e)
  }
}

const updateFinanceChart = () => {
  const d = financeData.value
  if (!d || !d.months) return

  // 实际/预计分别拆为两条，用不同色区分
  const accActual = [], accExpected = [], payActual = [], payExpected = []
  d.months.forEach((_, i) => {
    const isAct = d.is_actual[i]
    accActual.push(isAct ? d.acceptance_data[i] : 0)
    accExpected.push(!isAct ? d.acceptance_data[i] : 0)
    payActual.push(isAct ? d.payment_data[i] : 0)
    payExpected.push(!isAct ? d.payment_data[i] : 0)
  })

  const tipFormatter = (params) => {
    let html = `${params[0].axisValue}<br/>`
    let total = 0
    params.forEach(p => {
      if (p.value > 0) {
        html += `${p.marker} ${p.seriesName}: ${Number((p.value / 10000).toFixed(6))} 万<br/>`
        total += p.value
      }
    })
    html += `<b>合计: ${Number((total / 10000).toFixed(6))} 万</b>`
    return html
  }
  const wanAxis = { type: 'value', axisLabel: { formatter: v => (v / 10000).toFixed(0) + '万' } }

  if (chartFinance) {
    chartFinance.setOption({
      tooltip: { trigger: 'axis', formatter: tipFormatter },
      legend: { data: ['实际验收', '预计验收', '实际回款', '预计回款'], bottom: 0, itemWidth: 12 },
      grid: { left: '3%', right: '4%', top: 20, bottom: '18%', containLabel: true },
      xAxis: { type: 'category', data: d.months },
      yAxis: wanAxis,
      series: [
        { name: '实际验收', type: 'bar', stack: 'acc', data: accActual, itemStyle: { color: '#5470c6' } },
        { name: '预计验收', type: 'bar', stack: 'acc', data: accExpected, itemStyle: { color: '#a8c5f0' } },
        { name: '实际回款', type: 'bar', stack: 'pay', data: payActual, itemStyle: { color: '#ee6666' } },
        { name: '预计回款', type: 'bar', stack: 'pay', data: payExpected, itemStyle: { color: '#f7b5b5' } },
      ]
    }, true)
  }

  // 季度汇总图
  if (chartQuarter && d.quarters) {
    chartQuarter.setOption({
      tooltip: { trigger: 'axis', formatter: tipFormatter },
      legend: { data: ['实际验收', '预计验收', '实际回款', '预计回款'], bottom: 0, itemWidth: 12 },
      grid: { left: '3%', right: '4%', top: 20, bottom: '18%', containLabel: true },
      xAxis: { type: 'category', data: d.quarters.map(q => q.label) },
      yAxis: wanAxis,
      series: [
        { name: '实际验收', type: 'bar', stack: 'acc', data: d.quarters.map(q => q.acceptance_actual), itemStyle: { color: '#5470c6' } },
        { name: '预计验收', type: 'bar', stack: 'acc', data: d.quarters.map(q => q.acceptance_expected), itemStyle: { color: '#a8c5f0' } },
        { name: '实际回款', type: 'bar', stack: 'pay', data: d.quarters.map(q => q.payment_actual), itemStyle: { color: '#ee6666' } },
        { name: '预计回款', type: 'bar', stack: 'pay', data: d.quarters.map(q => q.payment_expected), itemStyle: { color: '#f7b5b5' } },
      ]
    }, true)
  }
}

const getStatusType = (status) => {
  const types = {
    '已签署': 'success',
    '待审批': 'warning',
    '执行中': 'primary',
    '已完成': 'info'
  }
  return types[status] || 'info'
}

const initCharts = () => {
  if (trendChart.value) {
    chart1 = echarts.init(trendChart.value)
    updateTrendChart()
  }
  
  if (funnelChart.value) {
    chart2 = echarts.init(funnelChart.value)
    chart2.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: {c}个商机' },
      series: [{
        name: '商机漏斗',
        type: 'funnel',
        left: '10%',
        top: 20,
        bottom: 20,
        width: '80%',
        min: 0,
        max: 100,
        minSize: '0%',
        maxSize: '100%',
        sort: 'descending',
        gap: 2,
        label: { show: true, position: 'inside' },
        labelLine: { length: 10, lineStyle: { width: 1, type: 'solid' } },
        itemStyle: { borderColor: '#fff', borderWidth: 1 },
        emphasis: { label: { fontSize: 14 } },
        data: [
          { value: 100, name: '引导需求阶段', itemStyle: { color: '#91cc75' } },
          { value: 50, name: '能力展示阶段', itemStyle: { color: '#5470c6' } },
          { value: 35, name: '方案确定阶段', itemStyle: { color: '#fac858' } },
          { value: 20, name: '商务谈判阶段', itemStyle: { color: '#ee6666' } },
          { value: 10, name: '合同签订阶段', itemStyle: { color: '#73c0de' } },
          { value: 5, name: '销售实现', itemStyle: { color: '#9a60b4' } }
        ]
      }]
    })

    chart2.on('click', (params) => {
      const stageMap = {
        '引导需求阶段': { min: 0, max: 29 },
        '能力展示阶段': { min: 30, max: 59 },
        '方案确定阶段': { min: 60, max: 79 },
        '商务谈判阶段': { min: 80, max: 89 },
        '合同签订阶段': { min: 90, max: 99 },
        '销售实现': { min: 100, max: 100 }
      }
      const range = stageMap[params.name]
      if (range) {
        router.push({ path: '/business', query: { prob_min: range.min, prob_max: range.max } })
      }
    })
  }
}

const updateTrendChart = () => {
  if (!chart1) return
  
  const chartData = dashboardData.value.chart_data || {
    months: ['1月', '2月', '3月', '4月', '5月', '6月'],
    customer_data: [0, 0, 0, 0, 0, 0],
    business_data: [0, 0, 0, 0, 0, 0],
    contract_data: [0, 0, 0, 0, 0, 0]
  }
  
  chart1.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['客户数', '商机数', '合同数'], bottom: 0 },
    grid: { left: '3%', right: '4%', bottom: '15%', containLabel: true },
    xAxis: { type: 'category', data: chartData.months },
    yAxis: { type: 'value' },
    series: [
      { name: '客户数', type: 'line', data: chartData.customer_data, smooth: true, itemStyle: { color: '#5470c6' }, areaStyle: { opacity: 0.1 } },
      { name: '商机数', type: 'line', data: chartData.business_data, smooth: true, itemStyle: { color: '#91cc75' }, areaStyle: { opacity: 0.1 } },
      { name: '合同数', type: 'line', data: chartData.contract_data, smooth: true, itemStyle: { color: '#fac858' }, areaStyle: { opacity: 0.1 } }
    ]
  })
}

const handleResize = () => {
  chart1?.resize()
  chart2?.resize()
  aiChart1?.resize()
  aiChart2?.resize()
  aiChart3?.resize()
  aiChart4?.resize()
  chartFinance?.resize()
  chartQuarter?.resize()
}

watch(timeRange, () => {
  fetchDashboardData()
})

// ============ AI 商机驾驶舱 ============
const aiData = ref({ today: {}, total: {} })
const aiTrendDays = ref(7)
const aiCards = computed(() => {
  const d = aiData.value
  return [
    { label: '今日新增情报', value: d.today?.collected ?? 0, bg: 'linear-gradient(135deg,#e8f4ff,#d6ecff)' },
    { label: '今日新增商机', value: d.today?.analyzed ?? 0, bg: 'linear-gradient(135deg,#f0f9eb,#e1f3d8)' },
    { label: 'S级商机', value: d.total?.grade_s ?? 0, bg: 'linear-gradient(135deg,#fef0f0,#fde2e2)' },
    { label: 'A级商机', value: d.total?.grade_a ?? 0, bg: 'linear-gradient(135deg,#fdf6ec,#faecd8)' },
    { label: '采购意向', value: d.total?.purchase_intent ?? 0, bg: 'linear-gradient(135deg,#ecf5ff,#d9ecff)' },
    { label: '招标项目', value: d.total?.tender_projects ?? 0, bg: 'linear-gradient(135deg,#f4f4f5,#e9e9eb)' },
    { label: '竞争对手动态', value: d.today?.competitor_moves ?? 0, bg: 'linear-gradient(135deg,#f0f9eb,#e1f3d8)' },
    { label: '客户动态', value: d.today?.customer_moves ?? 0, bg: 'linear-gradient(135deg,#fef0f0,#fde2e2)' },
  ]
})

let aiChart1 = null, aiChart2 = null, aiChart3 = null, aiChart4 = null

async function fetchAiOverview() {
  try {
    const res = await api.get('/cockpit/overview')
    aiData.value = res.data || {}
  } catch { /* ignore */ }
}

async function fetchAiTrend() {
  try {
    const res = await api.get('/cockpit/trend', { days: aiTrendDays.value })
    const rows = res.data || []
    const option = {
      tooltip: { trigger: 'axis' },
      legend: { data: ['新增情报', '新增商机', '转入CRM'], bottom: 0 },
      grid: { left: 40, right: 16, top: 20, bottom: 40 },
      xAxis: { type: 'category', data: rows.map(r => r.date.slice(5)) },
      yAxis: { type: 'value' },
      series: [
        { name: '新增情报', type: 'bar', data: rows.map(r => r.collected), itemStyle: { color: '#409eff' } },
        { name: '新增商机', type: 'bar', data: rows.map(r => r.analyzed), itemStyle: { color: '#67c23a' } },
        { name: '转入CRM', type: 'line', data: rows.map(r => r.converted), itemStyle: { color: '#e6a23c' } },
      ],
    }
    if (aiChart1) aiChart1.setOption(option, true)
  } catch { /* ignore */ }
}

function renderAiDistributions(dist) {
  const industry = (dist.type || []).filter(x => x.ptype && x.ptype !== '未分类').slice(0, 6)
  if (aiChart2) {
    aiChart2.setOption({
      tooltip: { trigger: 'item' },
      series: [{
        type: 'pie', radius: ['35%', '70%'],
        data: industry.map(x => ({ name: x.ptype, value: x.c })),
        label: { fontSize: 11 },
      }],
    }, true)
  }
  const amount = dist.amount || []
  if (aiChart3) {
    aiChart3.setOption({
      tooltip: { trigger: 'item' },
      series: [{
        type: 'pie', radius: ['35%', '70%'],
        data: amount.filter(x => x.count > 0).map(x => ({ name: x.range, value: x.count })),
        label: { fontSize: 11 },
      }],
    }, true)
  }
  const regions = (dist.region || []).slice(0, 10).reverse()
  if (aiChart4) {
    aiChart4.setOption({
      tooltip: {},
      grid: { left: 90, right: 20, top: 10, bottom: 20 },
      xAxis: { type: 'value' },
      yAxis: { type: 'category', data: regions.map(r => r.region) },
      series: [{ type: 'bar', data: regions.map(r => r.c), itemStyle: { color: '#409eff' } }],
    }, true)
  }
}

async function fetchAiDist() {
  try {
    const res = await api.get('/cockpit/distribution')
    renderAiDistributions(res.data || {})
  } catch { /* ignore */ }
}

function initAiCharts() {
  if (aiTrendChart.value && !aiChart1) {
    aiChart1 = echarts.init(aiTrendChart.value)
    aiChart1.setOption({ xAxis: { type: 'category', data: [] }, yAxis: { type: 'value' }, series: [] })
  }
  if (aiIndustryChart.value && !aiChart2) aiChart2 = echarts.init(aiIndustryChart.value)
  if (aiAmountChart.value && !aiChart3) aiChart3 = echarts.init(aiAmountChart.value)
  if (aiRegionChart.value && !aiChart4) aiChart4 = echarts.init(aiRegionChart.value)
}

onMounted(async () => {
  // 关键：必须先初始化 ECharts（chart2 = echarts.init），
  // 否则 fetchDashboardData 里的 updateFunnelChart() 会因 chart2==null 直接跳过，
  // 导致看板永远只显示 mock 数据（100,50,35...）而不是真实商机统计。
  initCharts()
  await nextTick()
  await fetchDashboardData()
  fetchRecentContracts()
  fetchAlerts()
  // AI 商机驾驶舱
  await nextTick()
  initAiCharts()
  fetchAiOverview()
  fetchAiTrend()
  fetchAiDist()
  // 月度验收/回款统计
  await nextTick()
  if (financeChart.value) chartFinance = echarts.init(financeChart.value)
  if (quarterChart.value) chartQuarter = echarts.init(quarterChart.value)
  fetchMonthlyFinance()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chart1?.dispose()
  chart2?.dispose()
  aiChart1?.dispose()
  aiChart2?.dispose()
  aiChart3?.dispose()
  aiChart4?.dispose()
  chartFinance?.dispose()
  chartQuarter?.dispose()
})
</script>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.stats-row {
  display: flex;
  gap: 16px;
}

/* ============ AI 商机驾驶舱 ============ */
.ai-stats-row {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 10px;
}

.ai-stat {
  border-radius: 10px;
  padding: 12px 8px;
  text-align: center;
}

.ai-stat-num {
  font-size: 22px;
  font-weight: bold;
  color: #303133;
}

.ai-stat-label {
  font-size: 12px;
  color: #606266;
  margin-top: 2px;
}

.ai-chart-title {
  font-size: 13px;
  font-weight: bold;
  color: #303133;
  margin-bottom: 6px;
}


.stat-card {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 16px;
  background: white;
  border-radius: 16px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
  transition: all 0.3s ease;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.1);
}

.stat-icon {
  width: 64px;
  height: 64px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
}

.stat-icon.blue { background: linear-gradient(135deg, #5470c6 0%, #3563e9 100%); }
.stat-icon.green { background: linear-gradient(135deg, #91cc75 0%, #52c41a 100%); }
.stat-icon.purple { background: linear-gradient(135deg, #fac858 0%, #e6a23c 100%); }
.stat-icon.orange { background: linear-gradient(135deg, #ee6666 0%, #d93636 100%); }
.stat-icon.red { background: linear-gradient(135deg, #73c0de 0%, #389e0d 100%); }

.stat-content {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 32px;
  font-weight: bold;
  color: #1a1a2e;
}

.stat-label {
  font-size: 14px;
  color: #999;
}

.stat-trend {
  font-size: 12px;
  margin-top: 4px;
}

.stat-trend.up { color: #4ecdc4; }
.stat-trend.down { color: #ff6b6b; }
.stat-trend.flat { color: #999; }

.alert-empty {
  text-align: center;
  padding: 24px;
  color: #999;
  font-size: 13px;
}

.main-row {
  display: flex;
  gap: 24px;
}

.left-column {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.right-column {
  width: 420px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.chart-card {
  background: white;
  border-radius: 16px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.time-range {
  font-size: 12px;
}

.chart {
  height: 300px;
}

.finance-metrics {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 10px;
  margin-bottom: 16px;
}

.fm-item {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 12px 8px;
  text-align: center;
}

.fm-value {
  font-size: 20px;
  font-weight: bold;
  color: #303133;
}

.fm-value.blue { color: #409eff; }
.fm-value.green { color: #67c23a; }
.fm-value.orange { color: #e6a23c; }

.fm-label {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.finance-summary {
  display: flex;
  gap: 24px;
  margin-bottom: 16px;
  padding: 10px 16px;
  background: #fafafa;
  border-radius: 8px;
}

.finance-summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.finance-label {
  font-size: 13px;
  color: #909399;
}

.finance-value {
  font-size: 20px;
  font-weight: bold;
  color: #303133;
}

.finance-value.expected {
  color: #e6a23c;
}

.finance-sub-title {
  font-size: 13px;
  font-weight: bold;
  color: #303133;
  margin-bottom: 6px;
}

.finance-chart-box {
  height: 280px;
}

.ranking-card {
  background: white;
  border-radius: 16px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.ranking-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ranking-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: rgba(0, 0, 0, 0.02);
  border-radius: 10px;
}

.rank-badge {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: bold;
  background: #e0e0e0;
  color: #666;
}

.rank-1 { background: linear-gradient(135deg, #ffd700 0%, #ffaa00 100%); color: #fff; }
.rank-2 { background: linear-gradient(135deg, #c0c0c0 0%, #a0a0a0 100%); color: #fff; }
.rank-3 { background: linear-gradient(135deg, #cd7f32 0%, #b87333 100%); color: #fff; }

.rank-info {
  flex: 1;
}

.rank-name {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.rank-role {
  font-size: 12px;
  color: #999;
}

.rank-amount {
  font-size: 14px;
  font-weight: 600;
  color: #4ecdc4;
}

.recent-card {
  background: white;
  border-radius: 16px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.contract-link {
  color: #5470c6;
  cursor: pointer;
}

.contract-link:hover {
  text-decoration: underline;
}

.alert-card {
  background: white;
  border-radius: 16px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.alert-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.alert-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  background: rgba(255, 71, 71, 0.05);
  border-radius: 8px;
}

.alert-icon {
  font-size: 16px;
}

.alert-text {
  flex: 1;
  font-size: 13px;
  color: #333;
}

.alert-time {
  font-size: 12px;
  color: #ff6b6b;
}
</style>