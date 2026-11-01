<template>
  <div class="receivables-page">
    <div class="page-header">
      <h2>
        两金明细表
        <span v-if="snapshotDate" class="sub-date">（截至{{ snapshotDate.replace(/-/g, '.') }}）</span>
        <span class="unit">单位：元</span>
      </h2>
      <div class="header-actions">
        <el-select v-model="filterQuarter" placeholder="选择季度" style="width: 140px" @change="fetchData">
          <el-option v-for="q in quarters" :key="q" :label="q" :value="q" />
        </el-select>
        <el-button v-if="canManage" type="primary" :loading="snapshotLoading" @click="handleSnapshot">生成快照</el-button>
        <el-button v-if="canManage" :loading="importLoading" @click="importFileRef && importFileRef.click()">导入 Excel</el-button>
        <el-button type="success" @click="handleExport">导出 Excel</el-button>
        <input ref="importFileRef" type="file" accept=".xlsx" style="display: none" @change="onImportFile" />
      </div>
    </div>

    <!-- 汇总卡片 -->
    <div class="summary-cards">
      <el-card class="summary-card">
        <div class="summary-label">应收账款</div>
        <div class="summary-value">{{ formatMoney(summary.receivable) }}</div>
      </el-card>
      <el-card class="summary-card">
        <div class="summary-label">合同资产</div>
        <div class="summary-value">{{ formatMoney(summary.contract_asset) }}</div>
      </el-card>
      <el-card class="summary-card">
        <div class="summary-label">两金合计</div>
        <div class="summary-value highlight">{{ formatMoney(summary.total) }}</div>
      </el-card>
      <el-card class="summary-card">
        <div class="summary-label">显示条数</div>
        <div class="summary-value">{{ filteredItems.length }}</div>
      </el-card>
    </div>

    <!-- 明细表 -->
    <el-card class="detail-card">
      <el-table :data="filteredItems" v-loading="loading" border stripe size="small" height="100%" style="width: 100%">
        <el-table-column type="index" label="序号" width="70" align="center" :index="(i) => i + 1" />
        <el-table-column prop="customer_name" label="往来单位" min-width="180" show-overflow-tooltip />
        <el-table-column prop="customer_nature" label="客户性质" width="190"
          :filters="natureFilters" :filter-method="filterNatureMethod" column-key="customer_nature">
          <template #default="{ row }">
            <el-select :model-value="row.customer_nature || undefined" placeholder="未填报" size="small"
              style="width: 100%" :class="{ 'nature-unfilled': !row.customer_nature }"
              @change="(v) => saveOverride(row, 'customer_nature', v)">
              <el-option v-for="n in CUSTOMER_NATURES" :key="n" :label="n" :value="n" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="project_name" label="项目名称" min-width="180" show-overflow-tooltip />
        <el-table-column prop="owner_name" label="项目负责人" width="110" align="center" show-overflow-tooltip />
        <el-table-column prop="ar_date" label="应收账款日期" width="140" align="center" />
        <el-table-column prop="contract_asset" label="合同资产" width="130" align="right">
          <template #default="{ row }">{{ formatMoney(row.contract_asset) }}</template>
        </el-table-column>
        <el-table-column prop="receivable" label="应收账款" width="130" align="right">
          <template #default="{ row }">{{ formatMoney(row.receivable) }}</template>
        </el-table-column>
        <el-table-column label="可回收性分析" align="center">
          <el-table-column prop="aging_bucket" label="账龄" width="90" align="center" />
          <el-table-column label="客户风险" width="110" align="center">
            <template #default="{ row }">
              <el-select :model-value="row.cust_risk || ''" size="small" style="width: 100%"
                @change="(v) => saveOverride(row, 'cust_risk', v)">
                <el-option label="低" value="低" />
                <el-option label="中" value="中" />
                <el-option label="高" value="高" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="回款风险" width="110" align="center">
            <template #default="{ row }">
              <el-select :model-value="row.payback_risk || row.auto_risk || ''" size="small" style="width: 100%"
                @change="(v) => saveOverride(row, 'payback_risk', v)">
                <el-option label="低" value="低" />
                <el-option label="中" value="中" />
                <el-option label="高" value="高" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="回款计划" min-width="220">
            <template #default="{ row }">
              <div class="plan-cell" @click="editPlan(row)">
                <template v-if="planListOf(row).length">
                  <div v-for="(p, i) in planListOf(row)" :key="i" class="plan-item">
                    <span class="plan-date">{{ p.date || '—' }}</span>
                    <span class="plan-amt">{{ formatMoney(p.amt) }}</span>
                  </div>
                </template>
                <span v-else class="plan-empty">—</span>
              </div>
            </template>
          </el-table-column>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !items.length"
        :description="canManage ? '当前季度暂无数据，可点击右上角【生成快照】' : '当前季度暂无您负责项目的数据'" />
    </el-card>

    <!-- 导入比对弹窗 -->
    <el-dialog v-model="importDialog" title="导入比对" width="1100px" :close-on-click-modal="false">
      <div v-if="importData">
        <el-alert type="info" :closable="false" class="import-summary">
          共解析 {{ importData.total_rows }} 行：匹配 {{ importData.rows.length }} 行、
          未匹配 {{ importData.unmatched.length }} 行；
          将填入 <b>{{ fillCount }}</b> 项，需人工裁决 <b>{{ conflictCount }}</b> 项（默认保留系统现有值）
        </el-alert>

        <div v-if="importData.unmatched.length" class="unmatched-block">
          <div class="unmatched-title">未匹配行（不会写入）</div>
          <div v-for="u in importData.unmatched" :key="u.row_no" class="unmatched-item">
            第{{ u.row_no }}行 {{ u.customer_name || '—' }} / {{ u.project_name || '—' }}：{{ u.reason }}
          </div>
        </div>

        <el-table :data="importData.rows" size="small" border max-height="420">
          <el-table-column prop="customer_name" label="往来单位" width="150" show-overflow-tooltip />
          <el-table-column prop="project_name" label="项目名称" width="180" show-overflow-tooltip />
          <el-table-column prop="matched_by" label="匹配方式" width="110" align="center" />
          <el-table-column v-for="f in importFieldKeys" :key="f.key" :label="f.label" min-width="180">
            <template #default="{ row }">
              <template v-if="fieldOf(row, f.key).action === 'conflict'">
                <el-radio-group v-model="choices[row.contract_id][f.key]" size="small">
                  <el-radio value="import">导入: {{ short(fieldOf(row, f.key).imported) }}</el-radio>
                  <el-radio value="keep">保留: {{ short(fieldOf(row, f.key).existing) }}</el-radio>
                </el-radio-group>
              </template>
              <span v-else-if="fieldOf(row, f.key).action === 'fill'" class="fill-cell">
                将填入: {{ short(fieldOf(row, f.key).imported) }}
              </span>
              <span v-else-if="fieldOf(row, f.key).action === 'same'" class="same-cell">一致</span>
              <span v-else-if="fieldOf(row, f.key).action === 'invalid'" class="invalid-cell">
                {{ fieldOf(row, f.key).invalid_reason }}
              </span>
              <span v-else class="noop-cell">—</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <template #footer>
        <el-button @click="importDialog = false">取消</el-button>
        <el-button type="primary" :loading="applying" :disabled="!importData || !importData.rows.length"
          @click="applyImport">
          确认导入（{{ fillCount + chosenImportCount }} 项）
        </el-button>
      </template>
    </el-dialog>

    <!-- 快照差异确认弹窗 -->
    <el-dialog v-model="snapshotDialog" title="生成快照确认" width="880px" :close-on-click-modal="false">
      <div v-if="snapshotPreview">
        <el-alert type="warning" :closable="false" class="import-summary">
          按当前业务数据计算的快照与现有 <b>{{ snapshotPreview.quarter }}</b> 快照存在
          <b>{{ snapshotPreview.changes.length }}</b> 处差异
          （现有 {{ snapshotPreview.current_count }} 条 → 新 {{ snapshotPreview.new_count }} 条）。
          确认后将覆盖写入。
        </el-alert>
        <el-table :data="snapshotPreview.changes" size="small" border max-height="420">
          <el-table-column type="index" label="序号" width="60" align="center" :index="(i) => i + 1" />
          <el-table-column prop="customer_name" label="往来单位" width="180" show-overflow-tooltip />
          <el-table-column prop="project_name" label="项目名称" width="200" show-overflow-tooltip />
          <el-table-column label="变化类型" width="100" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.change_type === 'added'" type="success" size="small">新增</el-tag>
              <el-tag v-else-if="row.change_type === 'removed'" type="danger" size="small">减少</el-tag>
              <el-tag v-else type="warning" size="small">修改</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="差异明细" min-width="280">
            <template #default="{ row }">
              <div v-if="row.change_type === 'added'" class="diff-line">该合同将首次进入快照</div>
              <div v-else-if="row.change_type === 'removed'" class="diff-line">该合同将从快照中移除（数据已不符合口径）</div>
              <div v-else>
                <div v-for="(d, k) in row.diffs" :key="k" class="diff-line">
                  <span class="diff-label">{{ d.label }}：</span>
                  <span class="diff-old">{{ d.old || '—' }}</span>
                  <span class="diff-arrow">→</span>
                  <span class="diff-new">{{ d.new || '—' }}</span>
                </div>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <template #footer>
        <el-button @click="snapshotDialog = false">取消</el-button>
        <el-button type="primary" :loading="snapshotLoading" @click="doApplySnapshot">确认覆盖生成</el-button>
      </template>
    </el-dialog>

    <!-- 回款计划编辑弹窗 -->
    <el-dialog v-model="planDialog" title="更新回款计划" width="640px">
      <div v-if="editingRow" class="plan-header">
        <div><strong>{{ editingRow.customer_name }}</strong> · {{ editingRow.project_name }}</div>
        <div class="plan-sub">应收账款：{{ formatMoney(editingRow.receivable) }} 元</div>
      </div>
      <el-table :data="planList" size="small" border>
        <el-table-column label="回款节点" width="180">
          <template #default="{ row }">
            <el-input v-model="row.node" placeholder="如：尾款/进度款" size="small" />
          </template>
        </el-table-column>
        <el-table-column label="金额(元)" width="160">
          <template #default="{ row }">
            <el-input-number v-model="row.amt" :precision="2" :min="0" :controls="false" size="small" style="width: 140px" />
          </template>
        </el-table-column>
        <el-table-column label="预计日期" width="160">
          <template #default="{ row }">
            <el-date-picker v-model="row.date" type="date" value-format="YYYY-MM-DD" size="small" style="width: 140px" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ $index }">
            <el-button size="small" link type="danger" @click="planList.splice($index, 1)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="plan-actions">
        <el-button size="small" @click="planList.push({ node: '', amt: null, date: '' })">+ 添加节点</el-button>
      </div>
      <template #footer>
        <el-button @click="planDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingPlan" @click="savePlan">保存</el-button>
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
// 管理角色（财务/主任/院长/view_all）才可生成快照与导入填报；销售仅查看/填报自己负责的项目
const canManage = computed(() =>
  authStore.has('data.view_all') || authStore.has('contracts.view_all') ||
  ['主任', '院长', '财务'].includes(authStore.role)
)

const CUSTOMER_NATURES = [
  '国内地方客户-地方国企', '国内地方客户-政府', '国内地方客户-民企',
  '国内地方客户-其它事业单位', '集团内', '子集团内',
]

const natureFilters = [
  { text: '未填报', value: '__unfilled__' },
  ...CUSTOMER_NATURES.map(n => ({ text: n, value: n })),
]

const items = ref([])
const filteredItems = computed(() => items.value.filter(r => Number(r.receivable) !== 0))
const quarters = ref([])
const filterQuarter = ref('')
const snapshotDate = ref('')
const summary = ref({ receivable: 0, contract_asset: 0, total: 0, count: 0 })
const loading = ref(false)
const snapshotLoading = ref(false)
const snapshotDialog = ref(false)
const snapshotPreview = ref(null)

const importFileRef = ref(null)
const importLoading = ref(false)
const importDialog = ref(false)
const importData = ref(null)
const applying = ref(false)
const choices = ref({})  // { contract_id: { field_key: 'keep' | 'import' } }
const importFieldKeys = [
  { key: 'customer_nature', label: '客户性质' },
  { key: 'cust_risk', label: '客户风险' },
  { key: 'payback_risk', label: '回款风险' },
  { key: 'payback_plan', label: '更新回款计划' },
]

const planDialog = ref(false)
const editingRow = ref(null)
const planList = ref([])
const savingPlan = ref(false)

const formatMoney = (v) => {
  if (v === null || v === undefined || v === '') return '0.00'
  return Number(v).toFixed(2)
}

const filterNatureMethod = (value, row) => {
  if (value === '__unfilled__') return !row.customer_nature
  return row.customer_nature === value
}

const planCount = (row) => {
  if (!row.payback_plan) return 0
  try {
    const plans = typeof row.payback_plan === 'string' ? JSON.parse(row.payback_plan) : row.payback_plan
    return Array.isArray(plans) ? plans.length : 0
  } catch { return 0 }
}

const planListOf = (row) => {
  if (!row.payback_plan) return []
  try {
    const plans = typeof row.payback_plan === 'string' ? JSON.parse(row.payback_plan) : row.payback_plan
    return Array.isArray(plans) ? plans : []
  } catch { return [] }
}

const fieldOf = (row, key) => row.fields.find(f => f.key === key) || {}

const short = (s, n = 14) => {
  const str = String(s || '')
  return str.length > n ? str.slice(0, n) + '…' : str
}

const fillCount = computed(() => {
  if (!importData.value) return 0
  return importData.value.rows.reduce(
    (acc, r) => acc + r.fields.filter(f => f.action === 'fill').length, 0)
})
const conflictCount = computed(() => {
  if (!importData.value) return 0
  return importData.value.rows.reduce(
    (acc, r) => acc + r.fields.filter(f => f.action === 'conflict').length, 0)
})
const chosenImportCount = computed(() => {
  let n = 0
  for (const r of (importData.value?.rows || [])) {
    for (const f of r.fields) {
      if (f.action === 'conflict' && choices.value[r.contract_id]?.[f.key] === 'import') n++
    }
  }
  return n
})

const fetchData = async () => {
  loading.value = true
  try {
    const params = {}
    if (filterQuarter.value) params.quarter = filterQuarter.value
    const resp = await api.get('/receivables', { params })
    if (resp.code === 200) {
      items.value = resp.data.items || []
      quarters.value = resp.data.quarters || []
      if (!filterQuarter.value) filterQuarter.value = resp.data.quarter
      snapshotDate.value = items.value[0]?.snapshot_date || ''
      // 汇总金额按过滤后口径（应收账款≠0）重算，与明细表保持一致
      const filtered = items.value.filter(r => Number(r.receivable) !== 0)
      summary.value = {
        receivable: filtered.reduce((s, r) => s + Number(r.receivable || 0), 0),
        contract_asset: filtered.reduce((s, r) => s + Number(r.contract_asset || 0), 0),
        total: filtered.reduce((s, r) => s + Number(r.receivable || 0) + Number(r.contract_asset || 0), 0),
        count: filtered.length,
      }
    } else {
      ElMessage.error(resp.message || '加载失败')
    }
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.message || ''))
  } finally {
    loading.value = false
  }
}

const handleSnapshot = async () => {
  snapshotLoading.value = true
  try {
    // 先预览差异，与现有数据不一致时弹窗确认
    const pv = await api.post('/receivables/snapshot/preview', {})
    if (pv.code !== 200) {
      ElMessage.error(pv.message || '快照预览失败')
      return
    }
    if (!pv.data.identical) {
      snapshotPreview.value = pv.data
      snapshotDialog.value = true
      return
    }
    // 无差异：直接生成（幂等）
    await doApplySnapshot()
  } catch (e) {
    ElMessage.error('生成失败: ' + (e.message || ''))
  } finally {
    snapshotLoading.value = false
  }
}

const doApplySnapshot = async () => {
  snapshotLoading.value = true
  try {
    const resp = await api.post('/receivables/snapshot', {})
    if (resp.code === 200) {
      ElMessage.success(`已生成快照：${resp.data.quarter} 共 ${resp.data.count} 条`)
      filterQuarter.value = resp.data.quarter
      snapshotDialog.value = false
      fetchData()
    } else {
      ElMessage.error(resp.message || '生成失败')
    }
  } catch (e) {
    ElMessage.error('生成失败: ' + (e.message || ''))
  } finally {
    snapshotLoading.value = false
  }
}

const handleExport = async () => {
  const params = {}
  if (filterQuarter.value) params.quarter = filterQuarter.value
  try {
    // 走 axios 携带 Authorization 头（后端 token_required 只认请求头，不支持 URL 传 token）
    const blob = await api.get('/receivables/export', params, { responseType: 'blob' })
    if (!(blob instanceof Blob)) {
      ElMessage.error(blob?.message || '导出失败')
      return
    }
    // 业务错误时后端返回 JSON（被包装为 blob），需解析提示
    if (blob.type && blob.type.includes('application/json')) {
      const err = JSON.parse(await blob.text())
      ElMessage.error(err.message || '导出失败')
      return
    }
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `两金明细表_${filterQuarter.value || ''}.xlsx`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (e) {
    ElMessage.error('导出失败: ' + (e.message || ''))
  }
}

// ---------- Excel 导入 ----------
const onImportFile = async (e) => {
  const file = e.target.files?.[0]
  e.target.value = ''  // 允许重复选择同一文件
  if (!file) return
  importLoading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    if (filterQuarter.value) fd.append('quarter', filterQuarter.value)
    const resp = await api.post('/receivables/import/preview', fd)
    if (resp.code === 200) {
      importData.value = resp.data
      // 冲突项默认「保留系统现有」
      const ch = {}
      for (const r of resp.data.rows) {
        ch[r.contract_id] = {}
        for (const f of r.fields) {
          if (f.action === 'conflict') ch[r.contract_id][f.key] = 'keep'
        }
      }
      choices.value = ch
      importDialog.value = true
    } else {
      ElMessage.error(resp.message || '解析失败')
    }
  } catch (err) {
    ElMessage.error('解析失败: ' + (err.message || ''))
  } finally {
    importLoading.value = false
  }
}

const applyImport = async () => {
  applying.value = true
  try {
    const payloadRows = []
    for (const r of importData.value.rows) {
      const fields = {}
      for (const f of r.fields) {
        if (f.action === 'fill') {
          fields[f.key] = f.key === 'payback_plan' ? f.imported_list : f.imported
        } else if (f.action === 'conflict' && choices.value[r.contract_id]?.[f.key] === 'import') {
          fields[f.key] = f.key === 'payback_plan' ? f.imported_list : f.imported
        }
      }
      if (Object.keys(fields).length) {
        payloadRows.push({ contract_id: r.contract_id, fields })
      }
    }
    if (!payloadRows.length) {
      ElMessage.info('没有需要写入的内容')
      importDialog.value = false
      return
    }
    const resp = await api.post('/receivables/import/apply', {
      quarter: importData.value.quarter,
      rows: payloadRows,
    })
    if (resp.code === 200) {
      ElMessage.success(`导入完成：写入 ${resp.data.applied} 行、填入 ${resp.data.filled} 项`)
      importDialog.value = false
      importData.value = null
      fetchData()
    } else {
      ElMessage.error(resp.message || '导入失败')
    }
  } catch (e) {
    ElMessage.error('导入失败: ' + (e.message || ''))
  } finally {
    applying.value = false
  }
}

// ---------- 手工单元格编辑 ----------
// 单元格编辑：随行携带客户性质/客户风险/回款风险，前一次填报不丢失
const saveOverride = async (row, field, value) => {
  const prev = row[field]
  row[field] = value
  try {
    const resp = await api.put(`/receivables/override/${row.contract_id}`, {
      quarter: filterQuarter.value,
      customer_nature: row.customer_nature || '',
      cust_risk: row.cust_risk || '',
      payback_risk: row.payback_risk || '',
    })
    if (resp.code === 200) {
      ElMessage.success('已保存')
    } else {
      row[field] = prev
      ElMessage.error(resp.message || '保存失败')
    }
  } catch (e) {
    row[field] = prev
    ElMessage.error('保存失败: ' + (e.message || ''))
  }
}

const editPlan = (row) => {
  editingRow.value = row
  try {
    const plans = row.payback_plan
      ? (typeof row.payback_plan === 'string' ? JSON.parse(row.payback_plan) : row.payback_plan)
      : []
    planList.value = Array.isArray(plans) ? plans.map(p => ({ ...p })) : []
  } catch {
    planList.value = []
  }
  if (!planList.value.length) {
    planList.value = [{ node: '', amt: null, date: '' }]
  }
  planDialog.value = true
}

const savePlan = async () => {
  savingPlan.value = true
  try {
    const cleaned = planList.value.filter(p => p.node || p.amt || p.date)
    const resp = await api.put(`/receivables/override/${editingRow.value.contract_id}`, {
      quarter: filterQuarter.value,
      payback_plan: cleaned,
    })
    if (resp.code === 200) {
      ElMessage.success('已保存')
      planDialog.value = false
      fetchData()
    } else {
      ElMessage.error(resp.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.message || ''))
  } finally {
    savingPlan.value = false
  }
}

onMounted(fetchData)
</script>

<style scoped>
.receivables-page {
  /* 占满内容区高度：header≈65px + content-wrapper padding 48px + 余量 */
  height: calc(100vh - 120px);
  width: 100%;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  padding: 0;
  box-sizing: border-box;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-bottom: 12px;
  flex: 0 0 auto;
}
.page-header h2 {
  margin: 0;
  font-size: 20px;
}
.sub-date {
  font-size: 15px;
  font-weight: normal;
  color: #606266;
}
.unit {
  font-size: 13px;
  font-weight: normal;
  color: #909399;
  margin-left: 12px;
}
.header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.summary-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 12px;
  flex: 0 0 auto;
}
.summary-card {
  text-align: center;
}
.summary-label {
  color: #909399;
  font-size: 13px;
  margin-bottom: 6px;
}
.summary-value {
  font-size: 22px;
  font-weight: 600;
  color: #303133;
}
.summary-value.highlight {
  color: #409eff;
}
/* 明细卡：flex:1 占据剩余高度，内部表格滚动 */
.detail-card {
  flex: 1;
  min-height: 0;
  min-width: 0;
  width: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.detail-card :deep(.el-card__body) {
  flex: 1;
  min-height: 0;
  min-width: 0;
  width: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.detail-card :deep(.el-table) {
  flex: 1;
  min-height: 0;
  min-width: 0;
  width: 100% !important;
  max-width: 100%;
}
/* 表格内部滚动（横/纵）由 el-table height="100%" 原生管理，勿手动覆盖 overflow */
.plan-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 4px 0;
  cursor: pointer;
  /* 单元格内计划条目过多时限高内部滚动，避免撑高整行 */
  max-height: 96px;
  overflow-y: auto;
}
.plan-cell:hover {
  background: #f5f7fa;
  border-radius: 4px;
}
.plan-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  line-height: 1.5;
}
.plan-date {
  color: #606266;
}
.plan-amt {
  color: #303133;
  font-weight: 500;
}
.plan-empty {
  color: #c0c4cc;
  font-size: 12px;
  text-align: center;
}
.diff-line {
  font-size: 13px;
  line-height: 1.8;
  color: #606266;
}
.diff-label {
  font-weight: 500;
}
.diff-old {
  color: #f56c6c;
  text-decoration: line-through;
}
.diff-arrow {
  margin: 0 6px;
  color: #909399;
}
.diff-new {
  color: #67c23a;
  font-weight: 500;
}
.plan-header {
  margin-bottom: 12px;
}
.plan-sub {
  color: #909399;
  font-size: 13px;
  margin-top: 4px;
}
.plan-actions {
  margin-top: 8px;
}
.nature-unfilled :deep(.el-select__placeholder) {
  color: #e6a23c;
  font-weight: 600;
}
.import-summary {
  margin-bottom: 12px;
}
.unmatched-block {
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #fdf6ec;
  border-radius: 4px;
}
.unmatched-title {
  font-weight: 600;
  color: #e6a23c;
  margin-bottom: 4px;
}
.unmatched-item {
  font-size: 12px;
  color: #909399;
  line-height: 1.8;
}
.fill-cell {
  color: #67c23a;
}
.same-cell {
  color: #909399;
}
.invalid-cell {
  color: #f56c6c;
  font-size: 12px;
}
.noop-cell {
  color: #c0c4cc;
}
</style>
