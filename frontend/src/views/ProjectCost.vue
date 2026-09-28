<template>
  <div class="project-cost">
    <div class="page-header">
      <h2 class="page-title">项目成本核算</h2>
    </div>

    <div class="toolbar">
      <el-select
        v-model="contractId"
        filterable
        placeholder="请选择项目（合同）"
        style="width: 420px"
        @change="onSelectContract"
      >
        <el-option
          v-for="c in contracts"
          :key="c.id"
          :label="`${c.contract_name}（${c.contract_no || '无编号'}）`"
          :value="c.id"
        >
          <span>{{ c.contract_name }}</span>
          <span style="float: right; color: #909399; font-size: 12px;">
            {{ c.contract_no }}<span v-if="hasCost(c)" class="done-tag">已核算</span>
          </span>
        </el-option>
      </el-select>
      <el-button v-if="contractId && canSave" type="primary" :loading="saving" @click="save">保存核算</el-button>
      <div v-if="current" class="contract-meta">
        <span>编号：{{ current.contract_no || '—' }}</span>
        <span>客户：{{ current.party_a || '—' }}</span>
        <span>负责人：{{ current.owner_name || '—' }}</span>
        <span>状态：{{ current.status || '—' }}</span>
      </div>
    </div>

    <div v-if="!contractId" class="empty-tip">
      <el-empty description="请选择需要进行成本核算的项目（合同）" />
    </div>

    <div v-else class="sheet-wrap" v-loading="loading">
      <div class="sheet-title">软件系统研发任务成本核算</div>
      <div class="sheet-unit">（单位：元）</div>

      <table class="cost-sheet">
        <thead>
          <tr>
            <th class="th-factor" colspan="2">要素</th>
            <th class="th-total" colspan="2">总体情况</th>
            <th class="th-remark" rowspan="2">备注</th>
          </tr>
          <tr>
            <th class="th-sub">大类</th>
            <th class="th-sub">明细</th>
            <th class="th-sub">计划</th>
            <th class="th-sub">实际</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.key">
            <td class="td-cat" :rowspan="row.rowspan" v-if="row.catStart">{{ row.cat }}</td>
            <td class="td-name">{{ row.name }}</td>
            <td class="td-num">
              <el-input-number
                v-if="canEditPlan"
                v-model="form[row.key]"
                :min="0"
                :step="0.01"
                :precision="2"
                :controls="false"
                size="small"
                class="cell-input"
              />
              <span v-else>{{ fmt(form[row.key]) }}</span>
            </td>
            <td class="td-num td-actual">
              <el-input-number
                v-if="canEditActual"
                v-model="actualForm[row.actualKey]"
                :min="0"
                :step="0.01"
                :precision="2"
                :controls="false"
                size="small"
                class="cell-input"
              />
              <span v-else>{{ fmt(actualForm[row.actualKey]) }}</span>
            </td>
            <td class="td-remark">
              <el-input
                v-model="remarks[row.remarkKey]"
                :disabled="!canEditPlan"
                size="small"
                placeholder="—"
                :border="false"
              />
              <div v-if="canEditActual && row.key === 'cost_labor'" class="labor-hours-row">
                <el-input-number v-model="actualRemarks.labor.hours" :min="0" :precision="2" :controls="false" size="small" style="width: 90px" placeholder="工时" />
                <span class="labor-unit">工时</span>
                <el-input v-model="actualRemarks.labor.desc" size="small" placeholder="工时说明（如：前端80h+后端40.5h）" style="flex:1" />
              </div>
              <el-input
                v-else-if="canEditActual"
                v-model="actualRemarks[row.remarkKey].text"
                size="small"
                placeholder="实际备注"
                :border="false"
              />
            </td>
          </tr>
          <tr class="row-sum">
            <td colspan="2">成本合计</td>
            <td class="td-num strong">{{ fmt(totalCost) }}</td>
            <td class="td-num td-actual strong">{{ fmt(actualTotalCost) }}</td>
            <td></td>
          </tr>
          <tr>
            <td colspan="2">投资金额</td>
            <td class="td-num strong">{{ fmt(investment) }}</td>
            <td class="td-num td-actual">—</td>
            <td class="td-remark-light">取合同总额</td>
          </tr>
          <tr>
            <td colspan="2">税费</td>
            <td class="td-num">
              <el-input-number
                v-if="canEditPlan"
                v-model="form.cost_tax"
                :min="0"
                :step="0.01"
                :precision="2"
                :controls="false"
                size="small"
                class="cell-input"
              />
              <span v-else>{{ fmt(form.cost_tax) }}</span>
            </td>
            <td class="td-num td-actual">
              <el-input-number
                v-if="canEditActual"
                v-model="actualForm.actual_cost_tax"
                :min="0"
                :step="0.01"
                :precision="2"
                :controls="false"
                size="small"
                class="cell-input"
              />
              <span v-else>{{ fmt(actualForm.actual_cost_tax) }}</span>
            </td>
            <td class="td-remark">
              <el-input
                v-model="remarks.tax"
                :disabled="!canEditPlan"
                size="small"
                placeholder="如：6%税费"
                :border="false"
              />
            </td>
          </tr>
          <tr class="row-result">
            <td colspan="2">净利润</td>
            <td class="td-num strong" :class="{ neg: netProfit < 0 }">{{ fmt(netProfit) }}</td>
            <td class="td-num td-actual strong" :class="{ neg: actualNetProfit < 0 }">{{ fmt(actualNetProfit) }}</td>
            <td></td>
          </tr>
          <tr class="row-result">
            <td colspan="2">净利润率</td>
            <td class="td-num strong" :class="{ neg: netProfit < 0 }">{{ netMargin }}%</td>
            <td class="td-num td-actual strong" :class="{ neg: actualNetProfit < 0 }">{{ actualNetMargin }}%</td>
            <td></td>
          </tr>
        </tbody>
      </table>

      <div class="sign-row">
        <span>拟制：{{ drafter || '—' }}</span>
        <span>审核：</span>
      </div>
      <div class="sheet-hint">
        说明：成本合计 = 人工费 + 差旅费 + 业务招待费 + 外协费 + 管理费（不含税费）；
        净利润 = 投资金额 − 成本合计 − 税费；净利润率 = 净利润 ÷ 投资金额。金额单位元，精确到分（0.01元）。
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const canEditPlan = authStore.has('workhour.manage') || authStore.has('data.view_all')
const canEditActual = canEditPlan || authStore.has('cost.actual.manage')
const canSave = canEditPlan || canEditActual

const contracts = ref([])
const contractId = ref(null)
const current = ref(null)
const loading = ref(false)
const saving = ref(false)
const drafter = ref(authStore.name || authStore.username || '')

const emptyForm = () => ({
  cost_labor: 0,
  cost_travel: 0,
  cost_entertain: 0,
  cost_outsource: 0,
  cost_manage: 0,
  cost_tax: 0
})
const form = reactive(emptyForm())
const remarks = ref({ labor: '', travel: '', entertain: '', outsource: '', manage: '', tax: '' })

// 实际成本表单
const emptyActualForm = () => ({
  actual_cost_labor: 0,
  actual_cost_travel: 0,
  actual_cost_entertain: 0,
  actual_cost_outsource: 0,
  actual_cost_manage: 0,
  actual_cost_tax: 0
})
const actualForm = reactive(emptyActualForm())
const emptyActualRemarks = () => ({
  labor: { hours: 0, desc: '', text: '' },
  travel: { text: '' },
  entertain: { text: '' },
  outsource: { text: '' },
  manage: { text: '' },
  tax: { text: '' }
})
const actualRemarks = ref(emptyActualRemarks())

// 表格行定义（税费/合计/投资/净利润在表中单独展示）
const rows = [
  { key: 'cost_labor', actualKey: 'actual_cost_labor', name: '人工成本', cat: '直接成本', catStart: true, rowspan: 4, remarkKey: 'labor' },
  { key: 'cost_travel', actualKey: 'actual_cost_travel', name: '差旅费', catStart: false, remarkKey: 'travel' },
  { key: 'cost_entertain', actualKey: 'actual_cost_entertain', name: '业务招待费', catStart: false, remarkKey: 'entertain' },
  { key: 'cost_outsource', actualKey: 'actual_cost_outsource', name: '外协费', catStart: false, remarkKey: 'outsource' },
  { key: 'cost_manage', actualKey: 'actual_cost_manage', name: '管理费', cat: '间接成本', catStart: true, rowspan: 1, remarkKey: 'manage' }
]

const totalCost = computed(() =>
  Number((form.cost_labor + form.cost_travel + form.cost_entertain
    + form.cost_outsource + form.cost_manage).toFixed(2)))
const actualTotalCost = computed(() =>
  Number((actualForm.actual_cost_labor + actualForm.actual_cost_travel + actualForm.actual_cost_entertain
    + actualForm.actual_cost_outsource + actualForm.actual_cost_manage).toFixed(2)))
const investment = computed(() => Number(((current.value?.total_amt || 0)).toFixed(2)))
const netProfit = computed(() => Number((investment.value - totalCost.value - form.cost_tax).toFixed(2)))
const actualNetProfit = computed(() => Number((investment.value - actualTotalCost.value - actualForm.actual_cost_tax).toFixed(2)))
const netMargin = computed(() =>
  investment.value > 0 ? ((netProfit.value / investment.value) * 100).toFixed(2) : '0.00')
const actualNetMargin = computed(() =>
  investment.value > 0 ? ((actualNetProfit.value / investment.value) * 100).toFixed(2) : '0.00')

const fmt = (v) => {
  const n = Number(v || 0)
  return n.toFixed(2)
}

const hasCost = (c) =>
  (Number(c.cost_labor) || 0) + (Number(c.cost_travel) || 0) + (Number(c.cost_entertain) || 0)
  + (Number(c.cost_outsource) || 0) + (Number(c.cost_manage) || 0) + (Number(c.cost_tax) || 0) > 0

const loadContracts = async () => {
  const res = await api.get('/contracts', { page: 1, page_size: 1000 })
  if (res.code === 200) {
    const data = res.data
    let list = Array.isArray(data) ? data : (data.list || data.records || [])
    // 非全局查看权限的用户只看自己负责的项目
    if (!authStore.has('data.view_all')) {
      list = list.filter(c => c.owner_id === authStore.username)
    }
    contracts.value = list
  }
}

const onSelectContract = async (id) => {
  if (!id) return
  loading.value = true
  try {
    const res = await api.get(`/contracts/${id}`)
    if (res.code === 200 && res.data) {
      current.value = res.data
      // 计划成本（按元回填）
      Object.assign(form, {
        cost_labor: (Number(res.data.cost_labor) || 0),
        cost_travel: (Number(res.data.cost_travel) || 0),
        cost_entertain: (Number(res.data.cost_entertain) || 0),
        cost_outsource: (Number(res.data.cost_outsource) || 0),
        cost_manage: (Number(res.data.cost_manage) || 0),
        cost_tax: (Number(res.data.cost_tax) || 0)
      })
      let rk = {}
      try { rk = res.data.cost_remark ? JSON.parse(res.data.cost_remark) : {} } catch { rk = {} }
      remarks.value = {
        labor: rk.labor || '', travel: rk.travel || '', entertain: rk.entertain || '',
        outsource: rk.outsource || '', manage: rk.manage || '', tax: rk.tax || ''
      }
      // 实际成本（按元回填）
      Object.assign(actualForm, {
        actual_cost_labor: (Number(res.data.actual_cost_labor) || 0),
        actual_cost_travel: (Number(res.data.actual_cost_travel) || 0),
        actual_cost_entertain: (Number(res.data.actual_cost_entertain) || 0),
        actual_cost_outsource: (Number(res.data.actual_cost_outsource) || 0),
        actual_cost_manage: (Number(res.data.actual_cost_manage) || 0),
        actual_cost_tax: (Number(res.data.actual_cost_tax) || 0)
      })
      // 实际备注 JSON
      const ar = emptyActualRemarks()
      if (res.data.actual_cost_remark) {
        try {
          const rk2 = JSON.parse(res.data.actual_cost_remark)
          for (const k of Object.keys(ar)) {
            const v = rk2[k]
            if (k === 'labor') {
              if (typeof v === 'object' && v !== null) {
                ar.labor = { hours: Number(v.hours) || 0, desc: v.desc || '', text: v.text || '' }
              } else if (typeof v === 'string') {
                ar.labor = { hours: 0, desc: '', text: v }
              }
            } else {
              if (typeof v === 'string') {
                ar[k] = { text: v }
              } else if (typeof v === 'object' && v !== null) {
                ar[k] = { text: v.text || '' }
              }
            }
          }
        } catch { /* 旧格式忽略 */ }
      }
      actualRemarks.value = ar
    }
  } finally {
    loading.value = false
  }
}

const save = async () => {
  if (!contractId.value) return
  // 前端工时校验：人工实际成本 > 0 时工时必须 > 0
  if (canEditActual && actualForm.actual_cost_labor > 0 && (actualRemarks.value.labor.hours || 0) <= 0) {
    ElMessage.warning('人工实际成本大于 0 时，请填写工时')
    return
  }
  saving.value = true
  try {
    const payload = {}
    // 计划列（仅有权限时提交）
    if (canEditPlan) {
      payload.cost_labor = Math.round(form.cost_labor * 100) / 100
      payload.cost_travel = Math.round(form.cost_travel * 100) / 100
      payload.cost_entertain = Math.round(form.cost_entertain * 100) / 100
      payload.cost_outsource = Math.round(form.cost_outsource * 100) / 100
      payload.cost_manage = Math.round(form.cost_manage * 100) / 100
      payload.cost_tax = Math.round(form.cost_tax * 100) / 100
      payload.cost_remark = JSON.stringify(remarks.value)
    }
    // 实际列
    if (canEditActual) {
      payload.actual_cost_labor = Math.round(actualForm.actual_cost_labor * 100) / 100
      payload.actual_cost_travel = Math.round(actualForm.actual_cost_travel * 100) / 100
      payload.actual_cost_entertain = Math.round(actualForm.actual_cost_entertain * 100) / 100
      payload.actual_cost_outsource = Math.round(actualForm.actual_cost_outsource * 100) / 100
      payload.actual_cost_manage = Math.round(actualForm.actual_cost_manage * 100) / 100
      payload.actual_cost_tax = Math.round(actualForm.actual_cost_tax * 100) / 100
      payload.actual_cost_remark = JSON.stringify(actualRemarks.value)
    }
    const res = await api.put(`/contracts/${contractId.value}/cost`, payload)
    if (res.code === 200) {
      ElMessage.success('成本核算保存成功')
      loadContracts()
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } finally {
    saving.value = false
  }
}

onMounted(loadContracts)
</script>

<style scoped>
.project-cost {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}

.contract-meta {
  display: flex;
  gap: 18px;
  color: #606266;
  font-size: 13px;
}

.empty-tip {
  margin-top: 60px;
}

.done-tag {
  margin-left: 6px;
  color: #67c23a;
}

.sheet-wrap {
  background: #fff;
  padding: 28px 36px 24px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}

.sheet-title {
  text-align: center;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 2px;
  color: #303133;
}

.sheet-unit {
  text-align: right;
  font-size: 14px;
  color: #606266;
  margin: 6px 0 10px;
}

.cost-sheet {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}

.cost-sheet th,
.cost-sheet td {
  border: 1px solid #909399;
  padding: 8px 10px;
  font-size: 14px;
  color: #303133;
}

.cost-sheet th {
  background: #f5f7fa;
  font-weight: 600;
  text-align: center;
  padding: 10px;
}

.th-factor { width: 10%; }
.th-total { width: 26%; }
.th-remark { width: 30%; }
.th-sub { width: 13%; font-weight: 500; }

.td-cat {
  text-align: center;
  background: #fafafa;
  font-weight: 500;
}

.td-name {
  text-align: center;
}

.td-num {
  text-align: right;
}

.td-actual {
  text-align: center;
  color: #c0c4cc;
}

.td-remark-light {
  color: #909399;
  font-size: 12px;
}

.td-remark :deep(.el-input__wrapper) {
  padding: 0;
  box-shadow: none !important;
}

.labor-hours-row {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
}
.labor-unit {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
}

.cell-input {
  width: 100%;
}

.cell-input :deep(.el-input__inner) {
  text-align: right;
}

.row-sum td {
  background: #fafafa;
}

.row-result td {
  background: #fdf6ec;
}

.strong {
  font-weight: 700;
}

.neg {
  color: #f56c6c;
}

.sign-row {
  display: flex;
  justify-content: space-between;
  margin-top: 22px;
  padding: 0 20px;
  font-size: 14px;
  color: #303133;
}

.sheet-hint {
  margin-top: 14px;
  font-size: 12px;
  color: #909399;
  line-height: 1.7;
}
</style>
