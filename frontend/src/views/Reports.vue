<template>
  <div class="reports-page">
    <!-- 顶部工具栏 -->
    <el-card class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <span class="toolbar-title">📊 业绩报表与业务洞察</span>
          <el-tag type="info" size="small">{{ authStore.has('data.view_all') ? '全局视角' : '个人视角' }}</el-tag>
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
              <template #default="scope">{{ formatAmount(scope.row.amount) }}</template>
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
          <template #default="scope">{{ formatAmount(scope.row.business_amount) }}</template>
        </el-table-column>
        <el-table-column prop="contract_count" label="合同数" width="80" align="center" />
        <el-table-column label="合同金额(万)" width="120" align="right">
          <template #default="scope">{{ formatAmount(scope.row.contract_amount) }}</template>
        </el-table-column>
        <el-table-column label="回款金额(万)" width="120" align="right">
          <template #default="scope">{{ formatAmount(scope.row.payment_amount) }}</template>
        </el-table-column>
        <el-table-column label="加权预测(万)" width="120" align="right">
          <template #default="scope">{{ formatAmount(scope.row.forecast_amount) }}</template>
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

    <!-- 客户满意度统计 -->
    <el-card class="section-card">
      <template #header>
        <div class="card-header">
          <span>😀 客户满意度统计</span>
          <span class="header-tip">基于售后服务工单的客户评价数据</span>
        </div>
      </template>
      <div class="satisfaction-summary">
        <div class="summary-item">
          <div class="summary-label">评价总数</div>
          <div class="summary-value primary">{{ satisfactionData.total || 0 }} <span class="unit">条</span></div>
        </div>
        <div class="summary-item">
          <div class="summary-label">满意度</div>
          <div class="summary-value success">{{ satisfactionData.satisfaction_rate || 0 }}<span class="unit">%</span></div>
        </div>
        <div class="summary-item">
          <div class="summary-label">总体评分</div>
          <div class="summary-value warning">{{ satisfactionData.avg_overall || 0 }}<span class="unit">分</span></div>
        </div>
        <div class="summary-item">
          <div class="summary-label">响应速度</div>
          <div class="summary-value">{{ satisfactionData.avg_response || 0 }}<span class="unit">分</span></div>
        </div>
        <div class="summary-item">
          <div class="summary-label">服务态度</div>
          <div class="summary-value">{{ satisfactionData.avg_attitude || 0 }}<span class="unit">分</span></div>
        </div>
        <div class="summary-item">
          <div class="summary-label">服务质量</div>
          <div class="summary-value">{{ satisfactionData.avg_quality || 0 }}<span class="unit">分</span></div>
        </div>
      </div>
      <div ref="satisfactionChart" class="chart-md"></div>
      <el-row :gutter="20" style="margin-top: 16px;">
        <el-col :span="12">
          <div class="sub-table-title">按工单类型</div>
          <el-table :data="satisfactionData.by_type" stripe size="small">
            <el-table-column prop="type_label" label="工单类型" width="100" />
            <el-table-column prop="count" label="评价数" width="80" align="center" />
            <el-table-column label="平均评分" align="center">
              <template #default="scope">
                <el-rate disabled :model-value="scope.row.avg_score" show-score size="small" />
              </template>
            </el-table-column>
          </el-table>
        </el-col>
        <el-col :span="12" v-if="isAdmin">
          <div class="sub-table-title">按负责人（团队视角）</div>
          <el-table :data="satisfactionData.by_owner" stripe size="small">
            <el-table-column prop="owner_name" label="负责人" width="100" />
            <el-table-column prop="count" label="评价数" width="80" align="center" />
            <el-table-column label="平均评分" align="center">
              <template #default="scope">
                <el-rate disabled :model-value="scope.row.avg_score" show-score size="small" />
              </template>
            </el-table-column>
          </el-table>
        </el-col>
      </el-row>
    </el-card>

    <!-- ERP 系统集成 -->
    <el-card v-if="isAdmin" class="section-card">
      <template #header>
        <div class="card-header">
          <span>🔄 ERP 系统集成</span>
          <el-button type="primary" size="small" @click="openERPConfigModal()">
            <el-icon><Plus /></el-icon> 新增连接
          </el-button>
        </div>
      </template>
      <el-table :data="erpConnections" stripe size="small">
        <el-table-column prop="name" label="连接名称" width="120" />
        <el-table-column prop="system_type" label="系统类型" width="100" />
        <el-table-column prop="base_url" label="服务地址" min-width="180" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template #default="scope">
            <el-tag :type="scope.row.status === 'active' ? 'success' : 'info'" size="small">
              {{ scope.row.status === 'active' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_sync_at" label="最后同步" min-width="140" />
        <el-table-column label="操作" min-width="280" fixed="right">
          <template #default="scope">
            <el-button size="small" @click="testERPConnection(scope.row)">测试</el-button>
            <el-button size="small" type="primary" @click="openSyncModal(scope.row)">同步</el-button>
            <el-button size="small" @click="openERPConfigModal(scope.row)">编辑</el-button>
            <el-button size="small" type="danger" @click="deleteERPConnection(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ERP 连接配置弹窗 -->
    <el-dialog v-model="showERPConfigModal" :title="erpConfigForm.id ? '编辑 ERP 连接' : '新增 ERP 连接'" width="560px">
      <el-form :model="erpConfigForm" label-width="100px" size="default">
        <el-form-item label="连接名称" required>
          <el-input v-model="erpConfigForm.name" placeholder="如：金蝶 ERP 生产环境" />
        </el-form-item>
        <el-form-item label="系统类型">
          <el-select v-model="erpConfigForm.system_type" style="width: 100%;">
            <el-option label="ERP 系统" value="erp" />
            <el-option label="财务系统" value="finance" />
            <el-option label="进销存系统" value="wms" />
            <el-option label="OA 系统" value="oa" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="服务地址">
          <el-input v-model="erpConfigForm.base_url" placeholder="https://erp.example.com/api" />
        </el-form-item>
        <el-form-item label="认证方式">
          <el-select v-model="erpConfigForm.auth_type" style="width: 100%;">
            <el-option label="API Key" value="api_key" />
            <el-option label="Basic Auth" value="basic" />
            <el-option label="OAuth2" value="oauth2" />
            <el-option label="无认证" value="none" />
          </el-select>
        </el-form-item>
        <el-form-item label="API Key" v-if="erpConfigForm.auth_type === 'api_key'">
          <el-input v-model="erpConfigForm.api_key" type="password" show-password
            :placeholder="erpConfigForm.id ? '留空则不修改' : '请输入 API Key'" />
        </el-form-item>
        <el-form-item label="启用状态">
          <el-switch v-model="erpConfigForm.status" active-value="active" inactive-value="inactive" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="erpConfigForm.remark" type="textarea" :rows="2" placeholder="连接用途、对接说明等" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showERPConfigModal = false">取消</el-button>
        <el-button type="primary" :loading="erpSaving" @click="saveERPConnection">保存</el-button>
      </template>
    </el-dialog>

    <!-- ERP 数据同步弹窗 -->
    <el-dialog v-model="showSyncModal" title="ERP 数据同步" width="480px">
      <div style="margin-bottom: 12px; color: #666;">
        连接：<b>{{ syncForm.connection_name }}</b>
      </div>
      <el-form :model="syncForm" label-width="90px" size="default">
        <el-form-item label="同步方向">
          <el-radio-group v-model="syncForm.direction">
            <el-radio-button label="export">导出 CRM → ERP</el-radio-button>
            <el-radio-button label="import">导入 ERP → CRM</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="数据模块">
          <el-select v-model="syncForm.module" style="width: 100%;">
            <el-option label="客户数据" value="customers" />
            <el-option label="产品数据" value="products" />
            <el-option label="合同数据" value="contracts" />
            <el-option label="商机数据" value="business" />
            <el-option label="回款数据" value="payments" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showSyncModal = false">取消</el-button>
        <el-button type="primary" :loading="syncing" @click="executeSync">开始同步</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useAuthStore } from '../stores/auth'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import api from '../api'
import * as echarts from 'echarts'

const authStore = useAuthStore()
const isAdmin = computed(() => authStore.has('data.view_all'))

// 金额格式化：元 → 万元，精确到分需保留4位小数（0.0001万元 = 0.01元）
const formatAmount = (value) => {
  return ((value || 0) / 10000).toFixed(4)
}

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

// 客户满意度数据
const satisfactionData = ref({
  total: 0,
  satisfied: 0,
  satisfaction_rate: 0,
  avg_overall: 0,
  avg_response: 0,
  avg_attitude: 0,
  avg_quality: 0,
  by_type: [],
  by_owner: [],
  monthly_trend: [],
  score_distribution: {}
})

// ERP 集成数据
const erpConnections = ref([])
const showERPConfigModal = ref(false)
const erpSaving = ref(false)
const erpConfigForm = ref({
  id: null,
  name: '',
  system_type: 'erp',
  base_url: '',
  api_key: '',
  auth_type: 'api_key',
  status: 'inactive',
  remark: ''
})
const showSyncModal = ref(false)
const syncing = ref(false)
const syncForm = ref({
  connection_id: null,
  connection_name: '',
  direction: 'export',
  module: 'customers'
})

// 图表 DOM 引用
const forecastChart = ref(null)
const conversionChart = ref(null)
const teamChart = ref(null)
const satisfactionChart = ref(null)
let forecastChartInstance = null
let conversionChartInstance = null
let teamChartInstance = null
let satisfactionChartInstance = null

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
          current: isAmount ? (val.current / 10000).toFixed(4) : val.current,
          previous: isAmount ? (val.previous / 10000).toFixed(4) : val.previous,
          growth_rate: val.growth_rate
        }
      })
    }
  } catch (e) { console.error('环比趋势获取失败', e) }
}

// 客户满意度
const fetchCustomerSatisfaction = async () => {
  try {
    const res = await api.get('/reports/customer-satisfaction')
    if (res.code === 200) {
      satisfactionData.value = res.data
      updateSatisfactionChart()
    }
  } catch (e) { console.error('客户满意度数据获取失败', e) }
}

// 更新满意度图表
const updateSatisfactionChart = () => {
  if (!satisfactionChartInstance) return
  const scoreData = Object.entries(satisfactionData.value.score_distribution).map(([score, count]) => ({
    name: `${score}星`,
    value: count
  }))
  const trendData = satisfactionData.value.monthly_trend.map(m => ({
    month: m.month,
    avg_score: m.avg_score
  }))
  satisfactionChartInstance.setOption({
    title: [
      { text: '评分分布', left: '20%', top: 0, textAlign: 'center', textStyle: { fontSize: 13, fontWeight: 'normal', color: '#666' } },
      { text: '月度评分趋势', left: '70%', top: 0, textAlign: 'center', textStyle: { fontSize: 13, fontWeight: 'normal', color: '#666' } }
    ],
    tooltip: { trigger: 'item' },
    grid: { left: '55%', right: '3%', top: '15%', bottom: '12%', containLabel: true },
    xAxis: { type: 'category', data: trendData.map(d => d.month), axisLabel: { rotate: 35 } },
    yAxis: { type: 'value', name: '平均分', min: 0, max: 5 },
    series: [
      {
        name: '评分分布',
        type: 'pie',
        radius: ['35%', '60%'],
        center: ['22%', '55%'],
        data: scoreData,
        label: { formatter: '{b}: {c} ({d}%)', fontSize: 11 }
      },
      {
        name: '月度评分',
        type: 'line',
        data: trendData.map(d => d.avg_score),
        itemStyle: { color: '#5470c6' },
        markLine: { data: [{ type: 'average', name: '平均值' }] }
      }
    ]
  })
}

// ERP 连接管理
const fetchERPConnections = async () => {
  if (!isAdmin.value) return
  try {
    const res = await api.get('/reports/erp/connections')
    if (res.code === 200) {
      erpConnections.value = res.data || []
    }
  } catch (e) { console.error('ERP 连接列表获取失败', e) }
}

const openERPConfigModal = (row = null) => {
  if (row) {
    erpConfigForm.value = {
      id: row.id,
      name: row.name,
      system_type: row.system_type || 'erp',
      base_url: row.base_url || '',
      api_key: '',
      auth_type: row.auth_type || 'api_key',
      status: row.status || 'inactive',
      remark: row.remark || ''
    }
  } else {
    erpConfigForm.value = {
      id: null, name: '', system_type: 'erp', base_url: '',
      api_key: '', auth_type: 'api_key', status: 'inactive', remark: ''
    }
  }
  showERPConfigModal.value = true
}

const saveERPConnection = async () => {
  if (!erpConfigForm.value.name) {
    ElMessage.warning('请填写连接名称')
    return
  }
  erpSaving.value = true
  try {
    const payload = { ...erpConfigForm.value }
    // 新建时若未填 api_key，清空避免误存
    if (!payload.api_key) delete payload.api_key
    let res
    if (payload.id) {
      res = await api.put(`/reports/erp/connections/${payload.id}`, payload)
    } else {
      res = await api.post('/reports/erp/connections', payload)
    }
    if (res.code === 200) {
      ElMessage.success(res.message || '保存成功')
      showERPConfigModal.value = false
      fetchERPConnections()
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (e) {
    console.error('ERP 连接保存失败', e)
    ElMessage.error('保存失败：' + (e.message || ''))
  } finally {
    erpSaving.value = false
  }
}

const deleteERPConnection = async (row) => {
  try {
    await ElMessageBox.confirm(`确认删除连接「${row.name}」吗？相关同步日志将一并删除。`, '删除确认', {
      type: 'warning'
    })
  } catch {
    return
  }
  try {
    const res = await api.delete(`/reports/erp/connections/${row.id}`)
    if (res.code === 200) {
      ElMessage.success('删除成功')
      fetchERPConnections()
    } else {
      ElMessage.error(res.message || '删除失败')
    }
  } catch (e) {
    console.error('删除失败', e)
    ElMessage.error('删除失败：' + (e.message || ''))
  }
}

const testERPConnection = async (row) => {
  try {
    const res = await api.post(`/reports/erp/connections/${row.id}/test`)
    if (res.code === 200) {
      ElMessage.success(res.message || '连接测试通过')
    } else {
      ElMessage.warning(res.message || '连接测试未通过')
    }
  } catch (e) {
    console.error('测试失败', e)
    ElMessage.error('测试失败：' + (e.message || ''))
  }
}

const openSyncModal = (row) => {
  syncForm.value = {
    connection_id: row.id,
    connection_name: row.name,
    direction: 'export',
    module: 'customers'
  }
  showSyncModal.value = true
}

const executeSync = async () => {
  syncing.value = true
  try {
    const res = await api.post('/reports/erp/sync', {
      connection_id: syncForm.value.connection_id,
      direction: syncForm.value.direction,
      module: syncForm.value.module
    })
    if (res.code === 200) {
      const d = res.data || {}
      ElMessage.success(`同步完成：${d.direction} ${d.module} 共 ${d.success} 条`)
      showSyncModal.value = false
      fetchERPConnections()
    } else {
      ElMessage.error(res.message || '同步失败')
    }
  } catch (e) {
    console.error('同步失败', e)
    ElMessage.error('同步失败：' + (e.message || ''))
  } finally {
    syncing.value = false
  }
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
      return `${p.name}<br/>商机数: ${stage.count || 0} 个<br/>金额: ${((stage.amount || 0) / 10000).toFixed(4)} 万<br/>转化率: ${stage.conversion_rate || 0}%<br/>流失率: ${stage.drop_rate || 0}%`
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
  if (satisfactionChart.value) {
    satisfactionChartInstance = echarts.init(satisfactionChart.value)
  }
}

const handleResize = () => {
  forecastChartInstance?.resize()
  conversionChartInstance?.resize()
  teamChartInstance?.resize()
  satisfactionChartInstance?.resize()
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
  fetchCustomerSatisfaction()
  fetchERPConnections()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  forecastChartInstance?.dispose()
  conversionChartInstance?.dispose()
  teamChartInstance?.dispose()
  satisfactionChartInstance?.dispose()
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

.satisfaction-summary {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.satisfaction-summary .summary-value {
  font-size: 22px;
}

.sub-table-title {
  font-size: 13px;
  font-weight: 600;
  color: #333;
  margin-bottom: 8px;
  padding-left: 8px;
  border-left: 3px solid #5470c6;
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
