<template>
  <div class="acceptance-page">
    <div class="header-row">
      <div class="header-left">
        <el-button type="primary" @click="openAddModal" class="add-btn">
          <el-icon><Plus /></el-icon>
          新增验收记录
        </el-button>
        <el-button @click="showImportModal = true" class="import-btn">
          <el-icon><Upload /></el-icon>
          导入验收数据
        </el-button>
        <el-button @click="exportAcceptances" class="export-btn">
          <el-icon><Download /></el-icon>
          导出
        </el-button>
        <el-button @click="downloadTemplate" class="template-btn">
          <el-icon><Download /></el-icon>
          下载导入模板
        </el-button>
      </div>
      <div class="header-right">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索合同名称、编号、甲方..."
          class="search-input"
          clearable
          style="width: 280px;"
        />
      </div>
    </div>

    <div class="table-container">
      <el-table :data="filteredRows" stripe border style="width: 100%;" v-loading="loading" max-height="70vh">
        <el-table-column label="合同名称" prop="contract_name" min-width="160" show-overflow-tooltip />
        <el-table-column label="合同编号" prop="contract_no" width="140" />
        <el-table-column label="甲方" prop="party_a" min-width="140" show-overflow-tooltip />
        <el-table-column label="合同额(元)" prop="total_amt" width="120" sortable>
          <template #default="{ row }">{{ formatAmount(row.total_amt) }}</template>
        </el-table-column>
        <el-table-column label="收入(元)" prop="acceptance_amount" width="120" sortable>
          <template #default="{ row }">
            <strong :style="{ color: Number(row.acceptance_amount) < 0 ? '#f56c6c' : '#67c23a' }">
              {{ formatAmount(row.acceptance_amount) }}
            </strong>
          </template>
        </el-table-column>
        <el-table-column label="税额(元)" prop="tax_amount" width="110" sortable>
          <template #default="{ row }">{{ formatAmount(row.tax_amount) }}</template>
        </el-table-column>
        <el-table-column label="验收日期" prop="acceptance_date" width="120" sortable />
        <el-table-column label="验收情况" prop="note" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.note">{{ row.note }}</span>
            <span v-else style="color: #c0c4cc;">—</span>
          </template>
        </el-table-column>
        <el-table-column label="待验收合同额(元)" prop="pending_acceptance_amount" width="150" sortable>
          <template #default="{ row }">{{ formatAmount(row.pending_acceptance_amount) }}</template>
        </el-table-column>
        <el-table-column label="业务方向" prop="business_direction" width="130" show-overflow-tooltip />
        <el-table-column label="状态" prop="status" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === '已完成' ? 'success' : 'info'" size="small">
              {{ row.status || '执行中' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right" v-if="canDelete">
          <template #default="{ row }">
            <el-button type="danger" size="small" link @click="deleteAcceptance(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 新增验收记录弹窗 -->
    <el-dialog v-model="showAddModal" title="新增验收记录" width="640px" :close-on-click-modal="false">
      <el-form :model="addForm" label-width="110px" :rules="addRules" ref="addFormRef">
        <el-form-item label="合同" prop="contract_id">
          <el-select
            v-model="addForm.contract_id"
            filterable
            placeholder="搜索选择合同（按编号/名称）"
            style="width: 100%;"
            :loading="loadingContracts"
            @visible-change="onContractSelectOpen"
          >
            <el-option
              v-for="c in contractOptions"
              :key="c.id"
              :label="`${c.contract_no || ''} | ${c.contract_name || ''}`"
              :value="c.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="验收日期" prop="acceptance_date">
          <el-date-picker
            v-model="addForm.acceptance_date"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择验收日期"
            style="width: 100%;"
          />
        </el-form-item>
        <el-form-item label="收入(元)" prop="acceptance_amount">
          <el-input-number
            v-model="addForm.acceptance_amount"
            :precision="2"
            :step="100"
            controls-position="right"
            style="width: 100%;"
            placeholder="正数验收，负数核减"
          />
        </el-form-item>
        <el-form-item label="验收情况" prop="note">
          <el-input
            v-model="addForm.note"
            type="textarea"
            :rows="3"
            placeholder="选填，本次验收的说明"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddModal = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitAdd">确认新增</el-button>
      </template>
    </el-dialog>

    <!-- 导入弹窗 -->
    <el-dialog v-model="showImportModal" title="导入验收数据" width="1000px" :close-on-click-modal="false" :close-on-press-escape="false">
      <div v-if="importStep === 1" class="import-step-1">
        <el-upload
          :action="importParseUrl"
          :headers="uploadHeaders"
          :on-success="handleImportParse"
          :on-error="handleImportError"
          :show-file-list="false"
          accept=".xlsx,.xls"
          :disabled="isImporting"
        >
          <el-button type="primary" :loading="isImporting">
            <el-icon><Upload /></el-icon>
            {{ isImporting ? '解析中...' : '选择Excel文件' }}
          </el-button>
        </el-upload>
        <p class="import-tip">
          <strong>导入说明：</strong><br>
          1. 请使用Excel文件（.xlsx/.xls格式）<br>
          2. 必填列：合同编号、验收日期、收入<br>
          3. 可选列：合同名称、甲方、合同额、税额、验收情况、业务方向<br>
          4. 每行将创建一笔验收记录，收入即本次验收金额，金额单位为"元"<br>
          5. 系统会检测重复：同一合同+同一验收日期已存在则该行标红，导入时自动跳过<br>
          6. 文件内重复也会被检测（同一合同+日期出现多次）<br>
          7. 税额/业务方向为合同级字段，导入时会同步更新到合同
        </p>
      </div>

      <div v-else-if="importStep === 2" class="import-step-2">
        <div class="import-summary">
          <span class="summary-item">总数：{{ importSummary.total }}</span>
          <span class="summary-item valid">有效：{{ importSummary.valid_count }}</span>
          <span class="summary-item invalid">无效：{{ importSummary.invalid_count }}</span>
        </div>

        <div class="import-table-wrapper">
          <el-table :data="importRows" stripe border max-height="400">
            <el-table-column prop="row_index" label="行号" width="70" />
            <el-table-column prop="data.contract_no" label="合同编号" width="130" />
            <el-table-column prop="data.contract_name" label="合同名称" min-width="140" show-overflow-tooltip />
            <el-table-column prop="data.acceptance_date" label="验收日期" width="110" />
            <el-table-column prop="data.acceptance_amount" label="收入(元)" width="110" />
            <el-table-column prop="data.note" label="验收情况" min-width="130" show-overflow-tooltip />
            <el-table-column prop="data.business_direction" label="业务方向" width="110" show-overflow-tooltip />
            <el-table-column prop="valid" label="状态" width="80">
              <template #default="scope">
                <el-tag :type="scope.row.valid ? 'success' : 'danger'" size="small">
                  {{ scope.row.valid ? '有效' : '无效' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="errors" label="错误信息" min-width="180">
              <template #default="scope">
                <span v-if="scope.row.errors && scope.row.errors.length" class="error-text">
                  {{ scope.row.errors.join(', ') }}
                </span>
                <span v-else class="success-text">无</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>

      <div v-else-if="importStep === 3" class="import-step-3">
        <div class="import-result">
          <el-icon class="result-icon success"><CircleCheck /></el-icon>
          <h3>导入完成</h3>
          <p class="result-stats">
            总数：{{ importResult.total }} |
            <span class="success">成功：{{ importResult.success_count }}</span> |
            <span class="error">失败：{{ importResult.fail_count }}</span>
          </p>
          <div v-if="importResult.fail_count > 0" class="fail-list">
            <h4>失败记录：</h4>
            <ul>
              <li v-for="(result, idx) in (importResult.results || []).filter(r => !r.success)" :key="idx">
                第{{ result.row_index }}行：{{ result.message }}
              </li>
            </ul>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button v-if="importStep === 2" @click="importStep = 1">重新上传</el-button>
        <el-button v-if="importStep === 2" type="primary" :loading="isImporting" @click="executeImport">
          {{ isImporting ? '导入中...' : '确认导入' }}
        </el-button>
        <el-button v-if="importStep === 3" @click="closeImportModal">关闭</el-button>
        <el-button v-if="importStep === 1" @click="showImportModal = false">取消</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { Plus, Upload, Download, CircleCheck } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()

const rows = ref([])
const loading = ref(false)
const searchKeyword = ref('')

const canDelete = computed(() => authStore.has('data.view_all'))

// 新增验收记录
const showAddModal = ref(false)
const saving = ref(false)
const addFormRef = ref(null)
const contractOptions = ref([])
const loadingContracts = ref(false)
const contractsLoaded = ref(false)
const addForm = reactive({
  contract_id: null,
  acceptance_date: '',
  acceptance_amount: 0,
  note: ''
})
const addRules = {
  contract_id: [{ required: true, message: '请选择合同', trigger: 'change' }],
  acceptance_date: [{ required: true, message: '请选择验收日期', trigger: 'change' }],
  acceptance_amount: [{ required: true, message: '请输入收入', trigger: 'blur' }]
}

// 导入
const showImportModal = ref(false)
const importStep = ref(1)
const isImporting = ref(false)
const importRows = ref([])
const importSummary = ref({ total: 0, valid_count: 0, invalid_count: 0 })
const importResult = ref({ total: 0, success_count: 0, fail_count: 0, results: [] })

const importParseUrl = computed(() => '/api/acceptances/import-parse')
const uploadHeaders = computed(() => ({
  Authorization: `Bearer ${authStore.token}`
}))

const filteredRows = computed(() => {
  const kw = (searchKeyword.value || '').trim().toLowerCase()
  if (!kw) return rows.value
  return rows.value.filter(r => {
    return [r.contract_name, r.contract_no, r.party_a, r.business_direction, r.note]
      .some(v => v && String(v).toLowerCase().includes(kw))
  })
})

const formatAmount = (value) => {
  return (Number(value) || 0).toFixed(2)
}

const fetchAcceptances = async () => {
  loading.value = true
  try {
    const response = await api.get('/acceptances')
    if (response.code === 200) {
      rows.value = response.data || []
    } else {
      ElMessage.error(response.message || '获取验收数据失败')
    }
  } catch (error) {
    ElMessage.error('获取验收数据失败：' + (error.message || '网络错误'))
  } finally {
    loading.value = false
  }
}

const fetchContractOptions = async () => {
  if (contractsLoaded.value) return
  loadingContracts.value = true
  try {
    const res = await api.get('/contracts')
    if (res.code === 200) {
      contractOptions.value = (res.data || []).map(c => ({
        id: c.id,
        contract_no: c.contract_no,
        contract_name: c.contract_name,
        total_amt: c.total_amt
      }))
      contractsLoaded.value = true
    }
  } catch (e) {
    // 忽略
  } finally {
    loadingContracts.value = false
  }
}

const onContractSelectOpen = (visible) => {
  if (visible) fetchContractOptions()
}

const openAddModal = () => {
  addForm.contract_id = null
  addForm.acceptance_date = ''
  addForm.acceptance_amount = 0
  addForm.note = ''
  showAddModal.value = true
  fetchContractOptions()
}

const submitAdd = async () => {
  if (!addFormRef.value) return
  await addFormRef.value.validate(async (valid) => {
    if (!valid) return
    if (!addForm.acceptance_amount || Number(addForm.acceptance_amount) === 0) {
      ElMessage.warning('收入不能为0（正数验收，负数核减）')
      return
    }
    saving.value = true
    try {
      // 收入单位为元，直接传递
      const amountYuan = Number(addForm.acceptance_amount)
      const res = await api.post(`/contracts/${addForm.contract_id}/acceptances`, {
        acceptance_date: addForm.acceptance_date,
        acceptance_amount: amountYuan,
        note: addForm.note || '',
        commissions: []
      })
      if (res.code === 200) {
        ElMessage.success('验收记录添加成功')
        showAddModal.value = false
        fetchAcceptances()
      } else {
        ElMessage.error(res.message || '添加失败')
      }
    } catch (error) {
      ElMessage.error('添加失败：' + (error.message || '网络错误'))
    } finally {
      saving.value = false
    }
  })
}

const deleteAcceptance = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确认删除该验收记录？\n合同：${row.contract_name || row.contract_no}\n日期：${row.acceptance_date}\n收入：${formatAmount(row.acceptance_amount)} 万`,
      '删除确认',
      { type: 'warning' }
    )
  } catch {
    return
  }
  try {
    const res = await api.delete(`/contracts/acceptances/${row.acceptance_id}`)
    if (res.code === 200) {
      ElMessage.success('删除成功')
      fetchAcceptances()
    } else {
      ElMessage.error(res.message || '删除失败')
    }
  } catch (error) {
    ElMessage.error('删除失败：' + (error.message || '网络错误'))
  }
}

const handleImportParse = (response) => {
  if (response.code === 200) {
    importRows.value = response.data.rows
    importSummary.value = {
      total: response.data.total,
      valid_count: response.data.valid_count,
      invalid_count: response.data.invalid_count
    }
    importStep.value = 2
  } else {
    ElMessage.error(response.message || '解析失败')
  }
}

const handleImportError = (error) => {
  ElMessage.error('解析失败：' + (error.message || '未知错误'))
}

const executeImport = async () => {
  const validRows = importRows.value.filter(r => r.valid)
  if (validRows.length === 0) {
    ElMessage.warning('没有可导入的有效数据')
    return
  }

  isImporting.value = true
  try {
    const response = await api.post('/acceptances/import', validRows)
    if (response.code === 200) {
      importResult.value = response.data
      importStep.value = 3
      fetchAcceptances()
    } else {
      ElMessage.error(response.message || '导入失败')
    }
  } catch (error) {
    ElMessage.error('导入失败：' + (error.message || '网络错误'))
  } finally {
    isImporting.value = false
  }
}

const closeImportModal = () => {
  showImportModal.value = false
  importStep.value = 1
  importRows.value = []
  importSummary.value = { total: 0, valid_count: 0, invalid_count: 0 }
  importResult.value = { total: 0, success_count: 0, fail_count: 0, results: [] }
}

const exportAcceptances = () => {
  if (rows.value.length === 0) {
    ElMessage.info('暂无数据可导出')
    return
  }

  const exportColumns = [
    { prop: 'contract_name', label: '合同名称' },
    { prop: 'contract_no', label: '合同编号' },
    { prop: 'party_a', label: '甲方' },
    { prop: 'total_amt', label: '合同额(元)', isAmount: true },
    { prop: 'acceptance_amount', label: '收入(元)', isAmount: true },
    { prop: 'tax_amount', label: '税额(元)', isAmount: true },
    { prop: 'acceptance_date', label: '验收日期' },
    { prop: 'note', label: '验收情况' },
    { prop: 'pending_acceptance_amount', label: '待验收合同额(元)', isAmount: true },
    { prop: 'business_direction', label: '业务方向' },
    { prop: 'status', label: '状态' }
  ]

  const escapeCsvValue = (value) => {
    if (value === null || value === undefined) return ''
    let strValue = String(value)
    strValue = strValue.replace(/"/g, '""')
    return `"${strValue}"`
  }

  let csvContent = '\uFEFF' + exportColumns.map(col => escapeCsvValue(col.label)).join(',') + '\n'

  filteredRows.value.forEach(row => {
    const rowData = exportColumns.map(col => {
      let value = row[col.prop]
      if (col.isAmount) {
        value = formatAmount(value)
      }
      return escapeCsvValue(value)
    })
    csvContent += rowData.join(',') + '\n'
  })

  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  const url = URL.createObjectURL(blob)
  const timestamp = new Date().toISOString().slice(0, 10).replace(/-/g, '')
  link.setAttribute('href', url)
  link.setAttribute('download', `验收记录_${timestamp}.csv`)
  link.style.visibility = 'hidden'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)

  ElMessage.success('导出成功')
}

const downloadTemplate = () => {
  const headers = ['合同编号', '合同名称', '甲方', '合同额', '税额', '验收日期', '收入', '验收情况', '待验收合同额', '业务方向']
  let csvContent = '\uFEFF' + headers.join(',') + '\n'
  const sample = ['HT2024001', '示例合同', '示例甲方', '1000000.00', '130000.00', '2024-12-31', '300000.00', '首期验收', '700000.00', '数字化']
  csvContent += sample.join(',') + '\n'

  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  const url = URL.createObjectURL(blob)
  link.setAttribute('href', url)
  link.setAttribute('download', '验收数据导入模板.csv')
  link.style.visibility = 'hidden'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)

  ElMessage.success('模板已下载')
}

onMounted(() => {
  fetchAcceptances()
})

watch(showImportModal, (newVal) => {
  if (!newVal) {
    importStep.value = 1
    importRows.value = []
    importSummary.value = { total: 0, valid_count: 0, invalid_count: 0 }
    importResult.value = { total: 0, success_count: 0, fail_count: 0, results: [] }
  }
})
</script>

<style scoped>
.acceptance-page {
  padding: 20px;
}

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}

.header-left {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.add-btn,
.import-btn,
.export-btn,
.template-btn {
  display: flex;
  align-items: center;
  gap: 6px;
}

.table-container {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.import-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 6px;
  color: #606266;
  font-size: 13px;
  line-height: 1.8;
}

.import-summary {
  display: flex;
  gap: 24px;
  margin-bottom: 12px;
  padding: 10px 16px;
  background: #f5f7fa;
  border-radius: 6px;
  font-size: 14px;
}

.summary-item.valid {
  color: #67c23a;
}

.summary-item.invalid {
  color: #f56c6c;
}

.import-table-wrapper {
  margin-bottom: 8px;
}

.error-text {
  color: #f56c6c;
  font-size: 12px;
}

.success-text {
  color: #67c23a;
  font-size: 12px;
}

.import-result {
  text-align: center;
  padding: 24px;
}

.result-icon {
  font-size: 56px;
  margin-bottom: 12px;
}

.result-icon.success {
  color: #67c23a;
}

.result-stats {
  margin: 12px 0;
  font-size: 15px;
}

.result-stats .success {
  color: #67c23a;
  font-weight: 600;
}

.result-stats .error {
  color: #f56c6c;
  font-weight: 600;
}

.fail-list {
  margin-top: 16px;
  text-align: left;
  padding: 12px 16px;
  background: #fef0f0;
  border-radius: 6px;
  max-height: 200px;
  overflow-y: auto;
}

.fail-list h4 {
  margin: 0 0 8px 0;
  color: #f56c6c;
}

.fail-list ul {
  margin: 0;
  padding-left: 20px;
}

.fail-list li {
  color: #f56c6c;
  font-size: 13px;
  line-height: 1.8;
}
</style>
