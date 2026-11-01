<template>
  <div class="page">
    <div class="toolbar">
      <el-radio-group v-model="statusFilter" size="small" style="margin-right: 12px;">
        <el-radio-button v-for="s in statusOptions" :key="s.value" :value="s.value">
          {{ s.label }}
        </el-radio-button>
      </el-radio-group>

      <el-select
        v-model="businessId"
        filterable
        placeholder="请选择商机"
        style="width: 460px"
        @change="loadDetail"
      >
        <el-option
          v-for="r in filteredList"
          :key="r.business_id"
          :label="`${r.title}（${formatMoney(r.amount)}）`"
          :value="r.business_id"
        >
          <span>{{ r.title }}</span>
          <span style="float: right; color: #909399; font-size: 12px;">
            <el-tag :type="statusTagType(r.status)" size="small">{{ statusLabel(r.status) }}</el-tag>
            <span v-if="r.owner_name" style="margin-left: 6px;">· {{ r.owner_name }}</span>
          </span>
        </el-option>
      </el-select>

      <el-button type="primary" style="margin-left: 12px;" @click="openCreate">发起成本评估</el-button>
      <el-button style="margin-left: 6px;" :loading="loading" @click="refresh">刷新</el-button>
    </div>

    <div v-if="!businessId" class="empty-hint">
      请选择商机查看成本评估；商机负责人可点击「发起成本评估」新建核算单。
    </div>

    <div v-else class="sheet-wrap" v-loading="loading">
      <div class="sheet-title">商机成本评估表</div>
      <div class="sheet-unit">（单位：元）</div>

      <div class="biz-info">
        <span><b>商机：</b>{{ detail.business?.title || '—' }}</span>
        <span><b>客户：</b>{{ detail.business?.customer_name || '—' }}</span>
        <span><b>预算金额：</b>{{ formatMoney(detail.business?.amount) }}</span>
        <span><b>负责人：</b>{{ detail.business?.owner_name || detail.business?.owner_id || '—' }}</span>
        <span><b>预计成交：</b>{{ (detail.business?.predict_date || '—').toString().slice(0, 10) }}</span>
        <span>
          <b>状态：</b>
          <el-tag v-if="detail.estimate" :type="statusTagType(detail.estimate.status)" size="small">
            {{ statusLabel(detail.estimate.status) }}
          </el-tag>
          <span v-else>未发起</span>
        </span>
      </div>

      <div class="param-hint">
        核算口径：人月单价 {{ formatMoney(params.monthly_rate) }}/人月 · 每月标准工时 {{ params.month_hours }}h（21.75天×8h）
        · 管理费 {{ (params.manage_rate * 100).toFixed(0) }}%（按人工+外协+其他计提）
      </div>

      <div v-if="!detail.estimate" class="no-estimate">
        <el-empty description="该商机尚未发起成本评估" :image-size="90" />
        <div style="text-align:center;">
          <el-button type="primary" @click="createEstimate">发起成本评估</el-button>
        </div>
      </div>

      <template v-else>
        <div v-if="detail.estimate.tech_reject_reason" class="reject-banner">
          <b>技术驳回理由：</b>{{ detail.estimate.tech_reject_reason }}
        </div>

        <!-- 研发工时 -->
        <div class="section-title">
          一、人工成本（技术部门填报研发预估工时）
          <span class="section-tip">人月 = 工时 ÷ {{ params.month_hours }}h，人工费 = 人月 × {{ formatMoney(params.monthly_rate) }}</span>
        </div>
        <el-table :data="laborRows" size="small" border class="cost-table">
          <el-table-column label="角色" min-width="130">
            <template #default="{ row }">
              <el-select v-if="canEditLabor" v-model="row.role_name" size="small" placeholder="选择角色" style="width: 120px">
                <el-option v-for="r in roleOptions" :key="r" :label="r" :value="r" />
              </el-select>
              <span v-else>{{ row.role_name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="预估工时(h)" width="140" align="right">
            <template #default="{ row }">
              <el-input-number v-if="canEditLabor" v-model="row.hours" :min="0" :step="8" :precision="1" size="small" controls-position="right" style="width: 110px" />
              <span v-else>{{ formatNum(row.hours, 1) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="折人月" width="100" align="right">
            <template #default="{ row }">{{ formatNum(row.hours / params.month_hours, 2) }}</template>
          </el-table-column>
          <el-table-column label="人工费用" width="130" align="right">
            <template #default="{ row }">{{ formatMoney(row.hours / params.month_hours * params.monthly_rate) }}</template>
          </el-table-column>
          <el-table-column label="备注" min-width="160">
            <template #default="{ row }">
              <el-input v-if="canEditLabor" v-model="row.note" size="small" placeholder="人员/技能说明" />
              <span v-else>{{ row.note || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="canEditLabor" label="操作" width="70" align="center">
            <template #default="{ $index }">
              <el-button link type="danger" size="small" @click="laborRows.splice($index, 1)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="canEditLabor" class="row-actions">
          <el-button size="small" @click="addLaborRow">+ 添加角色工时</el-button>
        </div>
        <div class="subtotal">
          合计工时 <b>{{ formatNum(laborHours, 2) }}</b> h ·
          折合 <b>{{ formatNum(laborHours / params.month_hours, 2) }}</b> 人月 ·
          人工成本 <b>{{ formatMoney(laborCost) }}</b>
        </div>

        <!-- 外协成本 -->
        <div class="section-title">
          二、外协成本
          <el-popover v-if="canEditOther" placement="bottom" trigger="click" width="420">
            <template #reference>
              <el-button size="small" link type="primary">+ 添加</el-button>
            </template>
            <div style="display:flex; gap:8px;">
              <el-input v-model="newOutsource.item_name" size="small" placeholder="外协项目（如：算法外包）" />
              <el-input-number v-model="newOutsource.amount" :min="0" :step="1000" size="small" style="width: 140px" />
              <el-button size="small" type="primary" @click="addOtherRow('outsource')">添加</el-button>
            </div>
          </el-popover>
        </div>
        <el-table :data="outsourceRows" size="small" border class="cost-table" empty-text="暂无外协成本">
          <el-table-column label="外协项目" min-width="200">
            <template #default="{ row }">
              <el-input v-if="canEditOther" v-model="row.item_name" size="small" />
              <span v-else>{{ row.item_name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="金额" width="160" align="right">
            <template #default="{ row }">
              <el-input-number v-if="canEditOther" v-model="row.amount" :min="0" :step="1000" :precision="2" size="small" controls-position="right" style="width: 130px" />
              <span v-else>{{ formatMoney(row.amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="说明" min-width="170">
            <template #default="{ row }">
              <el-input v-if="canEditOther" v-model="row.note" size="small" placeholder="供应商/范围" />
              <span v-else>{{ row.note || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="canEditOther" label="操作" width="70" align="center">
            <template #default="{ $index }">
              <el-button link type="danger" size="small" @click="outsourceRows.splice($index, 1)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="subtotal">外协成本合计 <b>{{ formatMoney(outsourceCost) }}</b></div>

        <!-- 其他成本 -->
        <div class="section-title">
          三、其他成本
          <el-popover v-if="canEditOther" placement="bottom" trigger="click" width="420">
            <template #reference>
              <el-button size="small" link type="primary">+ 添加</el-button>
            </template>
            <div style="display:flex; gap:8px;">
              <el-input v-model="newOther.item_name" size="small" placeholder="成本项目（如：差旅、设备）" />
              <el-input-number v-model="newOther.amount" :min="0" :step="1000" size="small" style="width: 140px" />
              <el-button size="small" type="primary" @click="addOtherRow('other')">添加</el-button>
            </div>
          </el-popover>
        </div>
        <el-table :data="otherRows" size="small" border class="cost-table" empty-text="暂无其他成本">
          <el-table-column label="成本项目" min-width="200">
            <template #default="{ row }">
              <el-input v-if="canEditOther" v-model="row.item_name" size="small" />
              <span v-else>{{ row.item_name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="金额" width="160" align="right">
            <template #default="{ row }">
              <el-input-number v-if="canEditOther" v-model="row.amount" :min="0" :step="1000" :precision="2" size="small" controls-position="right" style="width: 130px" />
              <span v-else>{{ formatMoney(row.amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="说明" min-width="170">
            <template #default="{ row }">
              <el-input v-if="canEditOther" v-model="row.note" size="small" placeholder="用途/依据" />
              <span v-else>{{ row.note || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="canEditOther" label="操作" width="70" align="center">
            <template #default="{ $index }">
              <el-button link type="danger" size="small" @click="otherRows.splice($index, 1)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="subtotal">其他成本合计 <b>{{ formatMoney(otherCost) }}</b></div>

        <!-- 汇总 -->
        <div class="section-title">四、成本汇总</div>
        <el-table :data="summaryRows" size="small" border class="cost-table summary-table">
          <el-table-column prop="label" label="项目" min-width="150" />
          <el-table-column label="金额" width="170" align="right">
            <template #default="{ row }">
              <span :class="row.negative ? 'neg' : ''">{{ row.value }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="note" label="说明" min-width="260" />
        </el-table>

        <div class="sheet-hint">
          说明：人工成本 = 研发工时 ÷ {{ params.month_hours }}h × {{ formatMoney(params.monthly_rate) }} 元/人月；
          管理费 =（人工 + 外协 + 其他）× {{ (params.manage_rate * 100).toFixed(0) }}%；
          成本合计 = 人工 + 外协 + 其他 + 管理费；毛利率 =（商机预算 − 成本合计）÷ 商机预算。金额精确到分。
        </div>

        <!-- 流程轨迹 -->
        <div class="section-title">五、流程轨迹</div>
        <el-timeline class="flow-timeline">
          <el-timeline-item v-if="detail.estimate.created_at" :timestamp="formatTS(detail.estimate.created_at)" placement="top" color="#909399">
            销售发起成本评估：{{ detail.estimate.created_by || '—' }}
          </el-timeline-item>
          <el-timeline-item v-if="detail.estimate.tech_confirmed_by" :timestamp="formatTS(detail.estimate.tech_confirmed_at)" placement="top" color="#67c23a">
            技术部门确认研发工时：{{ detail.estimate.tech_confirmed_by }}
          </el-timeline-item>
          <el-timeline-item v-if="detail.estimate.tech_reject_reason" :timestamp="formatTS(detail.estimate.updated_at)" placement="top" color="#f56c6c">
            技术驳回：{{ detail.estimate.tech_reject_reason }}
          </el-timeline-item>
          <el-timeline-item v-if="detail.estimate.submitted_at" :timestamp="formatTS(detail.estimate.submitted_at)" placement="top" color="#409eff">
            销售提交生效：{{ detail.estimate.submitted_by }}
          </el-timeline-item>
        </el-timeline>

        <!-- 操作按钮 -->
        <div class="footer-actions">
          <el-button v-if="permissions.can_edit_labor" type="primary" :loading="saving" @click="saveLabor">保存研发工时</el-button>
          <el-button v-if="permissions.can_confirm" type="success" :loading="confirming" @click="confirmHours">技术确认工时</el-button>
          <el-button v-if="permissions.can_reject" type="danger" plain @click="rejectDialog = true">技术驳回</el-button>
          <el-button v-if="permissions.can_edit_other" type="primary" :loading="saving" @click="saveOther">保存外协/其他成本</el-button>
          <el-button v-if="permissions.can_submit" type="success" :loading="submitting" @click="submitCost">提交生效</el-button>
          <el-button v-if="permissions.can_reopen" plain @click="reopenCost">重新评估</el-button>
        </div>
      </template>
    </div>

    <!-- 发起成本评估 -->
    <el-dialog v-model="createDialog" title="发起商机成本评估" width="520px" :close-on-click-modal="false">
      <el-select v-model="createBusinessId" filterable placeholder="选择本人负责的商机" style="width: 100%">
        <el-option
          v-for="b in createCandidates"
          :key="b.id"
          :label="`${b.title}（${formatMoney(b.amount)}）`"
          :value="b.id"
        />
      </el-select>
      <div class="dialog-tip">发起后由技术部门负责人填报研发预估工时，系统自动按人月单价折算人工费用。</div>
      <template #footer>
        <el-button @click="createDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="createEstimate">确定发起</el-button>
      </template>
    </el-dialog>

    <!-- 驳回 -->
    <el-dialog v-model="rejectDialog" title="技术驳回成本评估" width="480px" :close-on-click-modal="false">
      <el-input v-model="rejectReason" type="textarea" :rows="4" placeholder="请填写驳回理由（必填）" />
      <template #footer>
        <el-button @click="rejectDialog = false">取消</el-button>
        <el-button type="danger" :loading="rejecting" @click="doReject">确定驳回</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()

const statusOptions = [
  { value: 'all', label: '全部' },
  { value: 'draft', label: '待技术确认工时' },
  { value: 'hours_confirmed', label: '待销售提交' },
  { value: 'submitted', label: '已生效' },
  { value: 'rejected', label: '技术已驳回' },
]

const STATUS_LABEL = {
  draft: '待技术确认工时',
  hours_confirmed: '待销售提交',
  submitted: '已生效',
  rejected: '技术已驳回',
}

const list = ref([])
const businessId = ref(null)
const statusFilter = ref('all')
const detail = ref({})
const loading = ref(false)
const saving = ref(false)
const confirming = ref(false)
const submitting = ref(false)
const rejecting = ref(false)
const creating = ref(false)

const laborRows = ref([])
const outsourceRows = ref([])
const otherRows = ref([])

const params = ref({ month_hours: 174, monthly_rate: 25000, manage_rate: 0.15 })
const roleOptions = ref(['项目经理', '需求分析', '架构设计', '开发', '测试', '实施', '运维', '其他'])
const permissions = ref({})

const createDialog = ref(false)
const createBusinessId = ref(null)
const createCandidates = ref([])

const rejectDialog = ref(false)
const rejectReason = ref('')

const newOutsource = ref({ item_name: '', amount: 0 })
const newOther = ref({ item_name: '', amount: 0 })

const filteredList = computed(() => {
  if (statusFilter.value === 'all') return list.value
  return list.value.filter(r => r.status === statusFilter.value)
})

const canEditLabor = computed(() => !!permissions.value.can_edit_labor)
const canEditOther = computed(() => !!permissions.value.can_edit_other)

const laborHours = computed(() => laborRows.value.reduce((s, r) => s + (Number(r.hours) || 0), 0))
const laborCost = computed(() => {
  const h = params.value.month_hours || 174
  return Math.round(laborHours.value / h * (params.value.monthly_rate || 0) * 100) / 100
})
const outsourceCost = computed(() => Math.round(outsourceRows.value.reduce((s, r) => s + (Number(r.amount) || 0), 0) * 100) / 100)
const otherCost = computed(() => Math.round(otherRows.value.reduce((s, r) => s + (Number(r.amount) || 0), 0) * 100) / 100)
const manageCost = computed(() => Math.round((laborCost.value + outsourceCost.value + otherCost.value) * (params.value.manage_rate || 0) * 100) / 100)
const totalCost = computed(() => Math.round((laborCost.value + outsourceCost.value + otherCost.value + manageCost.value) * 100) / 100)
const amount = computed(() => Number(detail.value.business?.amount) || 0)
const grossProfit = computed(() => Math.round((amount.value - totalCost.value) * 100) / 100)
const grossRate = computed(() => amount.value > 0 ? (grossProfit.value / amount.value * 100) : null)

const summaryRows = computed(() => [
  { label: '人工成本', value: formatMoney(laborCost.value), note: `${laborHours.value} 工时 = ${(laborHours.value / (params.value.month_hours || 174)).toFixed(2)} 人月` },
  { label: '外协成本', value: formatMoney(outsourceCost.value), note: '外协明细合计' },
  { label: '其他成本', value: formatMoney(otherCost.value), note: '差旅、设备等直接成本合计' },
  { label: `管理费（${((params.value.manage_rate || 0) * 100).toFixed(0)}%）`, value: formatMoney(manageCost.value), note: '（人工 + 外协 + 其他）× 管理费率' },
  { label: '成本合计', value: formatMoney(totalCost.value), note: '人工 + 外协 + 其他 + 管理费' },
  { label: '商机预算金额', value: formatMoney(amount.value), note: '取自商机预算' },
  { label: '预计毛利', value: formatMoney(grossProfit.value), note: '商机预算 − 成本合计', negative: grossProfit.value < 0 },
  { label: '毛利率', value: grossRate.value === null ? '—' : `${grossRate.value.toFixed(2)}%`, note: '预计毛利 ÷ 商机预算', negative: grossRate.value !== null && grossRate.value < 0 },
])

const formatMoney = (v) => {
  const n = Number(v) || 0
  return '¥' + n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
const formatNum = (v, d = 2) => (Number(v) || 0).toFixed(d)
const formatTS = (v) => (v ? String(v).slice(0, 16).replace('T', ' ') : '')
const statusLabel = (s) => STATUS_LABEL[s] || s || '未发起'
const statusTagType = (s) => ({ draft: 'info', hours_confirmed: 'warning', submitted: 'success', rejected: 'danger' }[s] || 'info')

const loadList = async () => {
  const res = await api.get('/business/cost/list')
  if (res.code === 200) list.value = res.data || []
}

const refresh = async () => {
  await loadList()
  if (businessId.value) await loadDetail()
}

const loadDetail = async () => {
  if (!businessId.value) return
  loading.value = true
  try {
    const res = await api.get(`/business/${businessId.value}/cost`)
    if (res.code !== 200) {
      ElMessage.error(res.message || '加载失败')
      return
    }
    detail.value = res.data
    params.value = res.data.params || params.value
    permissions.value = res.data.permissions || {}
    roleOptions.value = res.data.roles || roleOptions.value
    laborRows.value = (res.data.labor_items || []).map(i => ({
      role_name: i.role_name, hours: Number(i.hours) || 0, note: i.note || ''
    }))
    outsourceRows.value = (res.data.outsource_items || []).map(i => ({
      item_name: i.item_name, amount: Number(i.amount) || 0, note: i.note || ''
    }))
    otherRows.value = (res.data.other_items || []).map(i => ({
      item_name: i.item_name, amount: Number(i.amount) || 0, note: i.note || ''
    }))
    if (!laborRows.value.length && res.data.permissions?.can_edit_labor) addLaborRow()
  } finally {
    loading.value = false
  }
}

const addLaborRow = () => laborRows.value.push({ role_name: '开发', hours: 0, note: '' })
const addOtherRow = (type) => {
  if (type === 'outsource') {
    if (!newOutsource.value.item_name) return ElMessage.warning('请填写外协项目')
    outsourceRows.value.push({ item_name: newOutsource.value.item_name, amount: Number(newOutsource.value.amount) || 0, note: '' })
    newOutsource.value = { item_name: '', amount: 0 }
  } else {
    if (!newOther.value.item_name) return ElMessage.warning('请填写成本项目')
    otherRows.value.push({ item_name: newOther.value.item_name, amount: Number(newOther.value.amount) || 0, note: '' })
    newOther.value = { item_name: '', amount: 0 }
  }
}

const saveLabor = async () => {
  saving.value = true
  try {
    const res = await api.put(`/business/${businessId.value}/cost/labor`, { items: laborRows.value })
    if (res.code === 200) {
      ElMessage.success('研发工时已保存')
      await refresh()
    } else ElMessage.error(res.message || '保存失败')
  } finally {
    saving.value = false
  }
}

const saveOther = async () => {
  if (!laborRows.value.length && canEditOther.value) {
    // 允许销售在有工时后保存；此处不阻断
  }
  saving.value = true
  try {
    const res = await api.put(`/business/${businessId.value}/cost/other`, {
      outsource_items: outsourceRows.value,
      other_items: otherRows.value,
      note: detail.value.estimate?.note || '',
    })
    if (res.code === 200) {
      ElMessage.success('成本明细已保存')
      await refresh()
    } else ElMessage.error(res.message || '保存失败')
  } finally {
    saving.value = false
  }
}

const confirmHours = async () => {
  confirming.value = true
  try {
    const res = await api.post(`/business/${businessId.value}/cost/confirm`, {})
    if (res.code === 200) {
      ElMessage.success(res.message || '工时已确认')
      await refresh()
    } else ElMessage.error(res.message || '确认失败')
  } finally {
    confirming.value = false
  }
}

const doReject = async () => {
  if (!rejectReason.value.trim()) return ElMessage.warning('请填写驳回理由')
  rejecting.value = true
  try {
    const res = await api.post(`/business/${businessId.value}/cost/reject`, { reason: rejectReason.value.trim() })
    if (res.code === 200) {
      ElMessage.success('已驳回')
      rejectDialog.value = false
      rejectReason.value = ''
      await refresh()
    } else ElMessage.error(res.message || '驳回失败')
  } finally {
    rejecting.value = false
  }
}

const submitCost = async () => {
  submitting.value = true
  try {
    const res = await api.post(`/business/${businessId.value}/cost/submit`, {})
    if (res.code === 200) {
      ElMessage.success('成本评估已生效')
      await refresh()
    } else ElMessage.error(res.message || '提交失败')
  } finally {
    submitting.value = false
  }
}

const reopenCost = async () => {
  const res = await api.post(`/business/${businessId.value}/cost/reopen`, {})
  if (res.code === 200) {
    ElMessage.success(res.message || '已退回待技术确认')
    await refresh()
  } else ElMessage.error(res.message || '操作失败')
}

const openCreate = async () => {
  const res = await api.get('/business', { status: 'all' })
  const bizList = (res.code === 200 ? (res.data || []) : [])
  const existing = new Set(list.value.map(r => r.business_id))
  createCandidates.value = bizList.filter(b => !existing.has(b.id))
  createBusinessId.value = null
  createDialog.value = true
}

const createEstimate = async () => {
  const targetId = createBusinessId.value || businessId.value
  if (!targetId) {
    createDialog.value = true
    return
  }
  creating.value = true
  try {
    const res = await api.post(`/business/${targetId}/cost`, {})
    if (res.code === 200) {
      ElMessage.success(res.message || '成本评估单已创建')
      createDialog.value = false
      businessId.value = targetId
      await refresh()
      await loadDetail()
    } else ElMessage.error(res.message || '创建失败')
  } finally {
    creating.value = false
  }
}

onMounted(async () => {
  await loadList()
  if (list.value.length) {
    businessId.value = list.value[0].business_id
    await loadDetail()
  }
})
</script>

<style scoped>
.page { padding: 16px; }
.toolbar { display: flex; align-items: center; flex-wrap: wrap; margin-bottom: 14px; }
.empty-hint { padding: 60px; text-align: center; color: #909399; }
.sheet-wrap {
  background: #fff; border: 1px solid #ebeef5; border-radius: 6px;
  padding: 22px 26px; max-height: calc(100vh - 150px); overflow-y: auto;
}
.sheet-title { text-align: center; font-size: 20px; font-weight: 700; letter-spacing: 2px; }
.sheet-unit { text-align: center; color: #606266; font-size: 12px; margin: 4px 0 14px; }
.biz-info {
  display: flex; flex-wrap: wrap; gap: 8px 26px; font-size: 13px; color: #303133;
  padding: 10px 12px; background: #f5f7fa; border-radius: 4px; margin-bottom: 10px;
}
.param-hint { font-size: 12px; color: #909399; margin-bottom: 14px; }
.no-estimate { padding: 18px 0 26px; }
.reject-banner {
  background: #fef0f0; border: 1px solid #fbc4c4; color: #f56c6c;
  padding: 8px 12px; border-radius: 4px; margin-bottom: 12px; font-size: 13px;
}
.section-title { font-size: 14px; font-weight: 700; color: #303133; margin: 20px 0 8px; display: flex; align-items: center; gap: 10px; }
.section-tip { font-size: 12px; font-weight: 400; color: #909399; }
.cost-table { margin-bottom: 6px; }
.row-actions { margin-bottom: 4px; }
.subtotal { text-align: right; font-size: 13px; color: #606266; padding: 6px 4px; }
.summary-table :deep(.neg) { color: #f56c6c; font-weight: 700; }
.sheet-hint { font-size: 12px; color: #909399; margin-top: 12px; line-height: 1.7; }
.flow-timeline { padding-left: 4px; }
.footer-actions {
  margin-top: 18px; padding-top: 14px; border-top: 1px dashed #dcdfe6;
  display: flex; gap: 10px; flex-wrap: wrap; justify-content: flex-end;
}
.dialog-tip { margin-top: 10px; font-size: 12px; color: #909399; }
</style>
