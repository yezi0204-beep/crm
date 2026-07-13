<template>
  <div class="dashboard">
    <div class="stats-row">
      <el-card class="stat-card">
        <div class="stat-icon blue">👥</div>
        <div class="stat-content">
          <div class="stat-value">{{ dashboardData.total_customers }}</div>
          <div class="stat-label">客户总数</div>
          <div class="stat-trend up">↑ 12% 本月</div>
        </div>
      </el-card>
      
      <el-card class="stat-card">
        <div class="stat-icon green">🎯</div>
        <div class="stat-content">
          <div class="stat-value">{{ dashboardData.total_business }}</div>
          <div class="stat-label">商机总数</div>
          <div class="stat-trend up">↑ 8% 本月</div>
        </div>
      </el-card>
      
      <el-card class="stat-card">
        <div class="stat-icon purple">📜</div>
        <div class="stat-content">
          <div class="stat-value">{{ dashboardData.total_contracts }}</div>
          <div class="stat-label">合同总数</div>
          <div class="stat-trend up">↑ 15% 本月</div>
        </div>
      </el-card>
      
      <el-card class="stat-card">
        <div class="stat-icon orange">💰</div>
        <div class="stat-content">
          <div class="stat-value">{{ formatAmount(dashboardData.contracts_amount) }}</div>
          <div class="stat-label">合同总额(万)</div>
          <div class="stat-trend up">↑ 23% 本月</div>
        </div>
      </el-card>
      
      <el-card class="stat-card">
        <div class="stat-icon red">💵</div>
        <div class="stat-content">
          <div class="stat-value">{{ formatAmount(dashboardData.total_payments) }}</div>
          <div class="stat-label">累计回款(万)</div>
          <div class="stat-trend down">↓ 3% 本月</div>
        </div>
      </el-card>
    </div>
    
    <div class="main-row">
      <div class="left-column">
        <el-card class="chart-card">
          <template #header>
            <div class="card-header">
              <span>📊 业务趋势分析</span>
              <div class="time-range">
                <el-radio-group v-model="timeRange">
                  <el-radio-button label="week">本周</el-radio-button>
                  <el-radio-button label="month">本月</el-radio-button>
                  <el-radio-button label="year">本年</el-radio-button>
                </el-radio-group>
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
            <el-button size="small" type="text">查看全部 →</el-button>
          </template>
          <el-table :data="recentContracts" stripe size="small">
            <el-table-column prop="contract_name" label="合同名称" min-width="150" />
            <el-table-column prop="total_amt" label="金额(万)" width="100" :formatter="formatAmount" />
            <el-table-column prop="sign_date" label="签约日期" width="100" />
            <el-table-column prop="status" label="状态" width="80">
              <template #default="scope">
                <el-tag :type="getStatusType(scope.row.status)" size="small">{{ scope.row.status }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
        
        <el-card class="alert-card">
          <template #header>
            <span>⚠️ 待办提醒</span>
          </template>
          <div class="alert-list">
            <div v-for="alert in alerts" :key="alert.id" class="alert-item">
              <span class="alert-icon">{{ alert.icon }}</span>
              <span class="alert-text">{{ alert.message }}</span>
              <span class="alert-time">{{ alert.time }}</span>
            </div>
          </div>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import api from '../api'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'

const dashboardData = ref({
  total_customers: 0,
  total_business: 0,
  total_contracts: 0,
  contracts_amount: 0,
  total_payments: 0
})

const recentContracts = ref([])
const salesRanking = ref([])

const alerts = ref([
  { id: 1, icon: '📅', message: '3份合同即将到期', time: '2天后' },
  { id: 2, icon: '💸', message: '5笔回款逾期未收', time: '已逾期' },
  { id: 3, icon: '📋', message: '8条商机待跟进', time: '本周' },
  { id: 4, icon: '✅', message: '2份合同待审批', time: '今日' }
])

const timeRange = ref('month')
const trendChart = ref(null)
const funnelChart = ref(null)
let chart1 = null
let chart2 = null

const formatAmount = (value) => {
  return ((value || 0) / 10000).toFixed(1)
}

const fetchDashboardData = async () => {
  const response = await api.get('/dashboard')
  if (response.code === 200) {
    dashboardData.value = response.data
    salesRanking.value = response.data.sales_ranking || []
    updateTrendChart()
  }
}

const fetchRecentContracts = async () => {
  const response = await api.get('/contracts')
  if (response.code === 200) {
    recentContracts.value = response.data.slice(0, 5)
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
      tooltip: { trigger: 'item', formatter: '{b}: {c}%' },
      series: [{
        name: '销售漏斗',
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
          { value: 100, name: '线索获取' },
          { value: 65, name: '需求确认' },
          { value: 45, name: '方案报价' },
          { value: 30, name: '商务谈判' },
          { value: 15, name: '合同签署' }
        ]
      }]
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
}

watch(timeRange, () => {
  updateTrendChart()
})

onMounted(() => {
  fetchDashboardData()
  fetchRecentContracts()
  initCharts()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chart1?.dispose()
  chart2?.dispose()
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