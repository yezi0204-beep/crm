<template>
  <div class="payments">
    <div class="header-row">
      <div class="header-left">
        <el-button type="primary" @click="showAddModal = true" class="add-btn">
          <el-icon><Plus /></el-icon>
          添加回款记录
        </el-button>
        
        <el-button @click="showImportModal = true" class="import-btn">
          <el-icon><Upload /></el-icon>
          导入回款记录
        </el-button>
      </div>
      
      <div class="search-wrapper">
        <el-input 
          v-model="searchKeyword" 
          placeholder="搜索合同名称、编号、甲方..." 
          class="search-input"
          clearable
          @keyup.enter="handleSearch"
        >
          <template #prefix>
            <span>🔍</span>
          </template>
        </el-input>
        <el-button @click="handleSearch" class="search-btn">搜索</el-button>
      </div>
    </div>
    
    <div class="table-container">
      <div class="table-wrapper">
        <el-table :data="paymentRecords" stripe border class="data-table">
          <el-table-column prop="contract_name" label="合同名称" min-width="160" sortable show-overflow-tooltip />
          <el-table-column prop="contract_no" label="合同编号" min-width="130" sortable />
          <el-table-column prop="payment_date" label="回款日期" min-width="120" sortable />
          <el-table-column prop="amount" label="金额(万)" min-width="110" sortable>
            <template #default="scope">
              {{ formatAmount(scope.row.amount) }}
            </template>
          </el-table-column>
          <el-table-column prop="owner_name" label="负责人" min-width="90" sortable />
          <el-table-column prop="note" label="备注" min-width="150" show-overflow-tooltip />
          <el-table-column prop="created_at" label="创建时间" min-width="140" sortable />
          <el-table-column label="操作" min-width="120" fixed="right">
            <template #default="scope">
              <el-button size="small" @click="editPayment(scope.row)">编辑</el-button>
              <el-button v-if="isAdmin" size="small" type="danger" @click="deletePayment(scope.row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
    
    <el-dialog v-model="showAddModal" title="添加回款记录" width="500px">
      <el-form :model="paymentForm" :rules="rules" ref="formRef">
        <el-form-item label="选择合同" prop="contract_id">
          <el-select 
            v-model="paymentForm.contract_id" 
            placeholder="请选择合同" 
            filterable
            style="width: 100%;"
          >
            <el-option 
              v-for="contract in contracts" 
              :key="contract.id" 
              :label="`${contract.contract_name} (${contract.contract_no}) - ${contract.party_a}`" 
              :value="contract.id" 
            />
          </el-select>
        </el-form-item>
        <el-form-item label="回款日期" prop="payment_date">
          <el-date-picker v-model="paymentForm.payment_date" type="date" />
        </el-form-item>
        <el-form-item label="金额(万)" prop="amount">
          <el-input-number v-model="paymentForm.amount" :min="0" :step="0.01" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="paymentForm.note" type="textarea" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddModal = false">取消</el-button>
        <el-button type="primary" @click="savePayment">确定</el-button>
      </template>
    </el-dialog>
    
    <el-dialog v-model="showImportModal" title="导入回款记录" width="900px">
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
          2. 必须包含以下列：合同编号、回款日期、金额(万)<br>
          3. 可选列：合同名称、备注<br>
          4. 合同编号必须在系统中存在<br>
          5. 如果与系统中回款信息重复，可选择保留哪一个
        </p>
      </div>
      
      <div v-else-if="importStep === 2" class="import-step-2">
        <div class="import-summary">
          <span class="summary-item">总数：{{ importSummary.total }}</span>
          <span class="summary-item valid">有效：{{ importSummary.valid_count }}</span>
          <span class="summary-item invalid">无效：{{ importSummary.invalid_count }}</span>
          <span class="summary-item duplicate">重复：{{ importSummary.duplicate_count }}</span>
        </div>
        
        <div v-if="importSummary.duplicate_count > 0" class="duplicate-action-bar">
          <span class="action-label">重复数据处理：</span>
          <el-radio-group v-model="duplicateAction" size="small">
            <el-radio label="keep_import">保留导入数据（覆盖系统）</el-radio>
            <el-radio label="keep_existing">保留系统数据（跳过导入）</el-radio>
          </el-radio-group>
          <el-button size="small" type="primary" @click="showDuplicateDialog = true">逐条选择</el-button>
        </div>
        
        <div class="import-table-wrapper">
          <el-table :data="importRows" stripe border max-height="400">
            <el-table-column prop="row_index" label="行号" width="80" />
            <el-table-column prop="data.contract_no" label="合同编号" width="150" />
            <el-table-column prop="data.contract_name" label="合同名称" width="150" />
            <el-table-column prop="data.payment_date" label="回款日期" width="130" />
            <el-table-column prop="data.amount" label="金额(万)" width="120">
              <template #default="scope">
                {{ (scope.row.data.amount || 0) / 10000 }}
              </template>
            </el-table-column>
            <el-table-column prop="data.note" label="备注" />
            <el-table-column prop="valid" label="状态" width="100">
              <template #default="scope">
                <el-tag :type="getRowStatusType(scope.row)" size="small">
                  {{ getRowStatusText(scope.row) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="errors" label="错误信息" width="200">
              <template #default="scope">
                <span v-if="scope.row.errors && scope.row.errors.length" class="error-text">
                  {{ scope.row.errors.join(', ') }}
                </span>
                <span v-else-if="scope.row.is_duplicate" class="duplicate-text">
                  与系统数据重复
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
              <li v-for="(result, idx) in importResult.results.filter(r => !r.success)" :key="idx">
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
    
    <el-dialog v-model="showDuplicateDialog" title="重复数据处理" width="800px">
      <div class="duplicate-dialog-content">
        <p class="dialog-tip">请为每条重复数据选择处理方式：</p>
        <div class="duplicate-table-wrapper">
          <el-table :data="duplicateRows" stripe border max-height="400">
            <el-table-column prop="row_index" label="行号" width="80" />
            <el-table-column prop="data.contract_no" label="合同编号" width="150" />
            <el-table-column prop="data.contract_name" label="合同名称" width="150" />
            <el-table-column prop="data.payment_date" label="回款日期" width="130" />
            <el-table-column label="金额对比(万)" width="180">
              <template #default="scope">
                <div class="compare-cell">
                  <span class="import-label">导入：{{ (scope.row.data.amount || 0) / 10000 }}</span>
                  <span class="system-label">系统：{{ (scope.row.existing_data?.amount || 0) / 10000 }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="备注对比" width="250">
              <template #default="scope">
                <div class="compare-cell">
                  <span class="import-label">导入：{{ scope.row.data.note || '-' }}</span>
                  <span class="system-label">系统：{{ scope.row.existing_data?.note || '-' }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="existing_data.created_at" label="系统创建时间" width="150" />
            <el-table-column label="处理方式" width="180">
              <template #default="scope">
                <el-radio-group v-model="scope.row.duplicate_action" size="small">
                  <el-radio label="keep_import">保留导入</el-radio>
                  <el-radio label="keep_existing">保留系统</el-radio>
                </el-radio-group>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
      <template #footer>
        <el-button @click="showDuplicateDialog = false">取消</el-button>
        <el-button type="primary" @click="saveDuplicateActions">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { Plus, Search, Upload, CircleCheck } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const isAdmin = computed(() => authStore.role === '主任' || authStore.role === '院长')
const allPaymentRecords = ref([])
const contracts = ref([])
const showAddModal = ref(false)
const showImportModal = ref(false)
const formRef = ref(null)
const searchKeyword = ref('')

const handleSearch = () => {}

const paymentForm = reactive({
  id: null,
  contract_id: '',
  payment_date: '',
  amount: 0,
  note: ''
})

const rules = {
  contract_id: [{ required: true, message: '请选择合同', trigger: 'blur' }],
  amount: [{ required: true, message: '请输入金额', trigger: 'blur' }]
}

const formatAmount = (value) => {
  return ((value || 0) / 10000).toFixed(2)
}

const paymentRecords = computed(() => {
  if (!searchKeyword.value) {
    return allPaymentRecords.value
  }
  
  const keyword = searchKeyword.value.toLowerCase()
  const filtered = allPaymentRecords.value.filter(record => {
    return (
      (record.contract_name && record.contract_name.toLowerCase().includes(keyword)) ||
      (record.contract_no && record.contract_no.toLowerCase().includes(keyword)) ||
      (record.party_a && record.party_a.toLowerCase().includes(keyword)) ||
      (record.owner_name && record.owner_name.toLowerCase().includes(keyword)) ||
      (record.note && record.note.toLowerCase().includes(keyword))
    )
  })
  return filtered
})

const fetchPayments = async () => {
  const response = await api.get('/payment_records')
  if (response.code === 200) {
    allPaymentRecords.value = response.data
  }
}

const fetchContracts = async () => {
  const response = await api.get('/contracts')
  if (response.code === 200) {
    contracts.value = response.data
  }
}

const savePayment = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (valid) {
      paymentForm.amount = (paymentForm.amount || 0) * 10000
      
      try {
        let response
        if (paymentForm.id) {
          response = await api.put(`/payment_records/${paymentForm.id}`, paymentForm)
        } else {
          response = await api.post('/payment_records', paymentForm)
        }
        
        if (response.code === 200) {
          ElMessage.success(paymentForm.id ? '更新成功' : '创建成功')
          showAddModal.value = false
          fetchPayments()
        } else {
          ElMessage.error(response.message)
        }
      } catch (error) {
        ElMessage.error('保存失败')
      }
    }
  })
}

const editPayment = (row) => {
  Object.assign(paymentForm, row)
  paymentForm.amount = (row.amount || 0) / 10000
  showAddModal.value = true
}

const deletePayment = async (row) => {
  try {
    await ElMessageBox.confirm('确定要删除这个回款记录吗？', '提示', {
      type: 'warning'
    })
    
    const response = await api.delete(`/payment_records/${row.id}`)
    if (response.code === 200) {
      ElMessage.success('删除成功')
      fetchPayments()
    } else {
      ElMessage.error(response.message)
    }
  } catch (error) {
    ElMessage.info('已取消删除')
  }
}

const importStep = ref(1)
const isImporting = ref(false)
const importRows = ref([])
const importSummary = ref({ total: 0, valid_count: 0, invalid_count: 0, duplicate_count: 0 })
const importResult = ref({ total: 0, success_count: 0, fail_count: 0, results: [] })
const showDuplicateDialog = ref(false)
const duplicateAction = ref('keep_import')

const importParseUrl = computed(() => '/api/payments/import-parse')
const uploadHeaders = computed(() => ({
  Authorization: `Bearer ${authStore.token}`
}))

const duplicateRows = computed(() => {
  return importRows.value.filter(row => row.is_duplicate && row.valid)
})

const getRowStatusType = (row) => {
  if (!row.valid) return 'danger'
  if (row.is_duplicate) return 'warning'
  return 'success'
}

const getRowStatusText = (row) => {
  if (!row.valid) return '无效'
  if (row.is_duplicate) return '重复'
  return '有效'
}

const handleImportParse = (response) => {
  if (response.code === 200) {
    importRows.value = response.data.rows.map(row => ({
      ...row,
      duplicate_action: 'keep_import',
      existing_data: row.data.existing_data || null
    }))
    importSummary.value = {
      total: response.data.total,
      valid_count: response.data.valid_count,
      invalid_count: response.data.invalid_count,
      duplicate_count: response.data.duplicate_count
    }
    importStep.value = 2
  } else {
    ElMessage.error(response.message)
  }
}

const handleImportError = (error) => {
  ElMessage.error('解析失败：' + (error.message || '未知错误'))
}

const saveDuplicateActions = () => {
  showDuplicateDialog.value = false
}

const executeImport = async () => {
  const validRows = importRows.value.filter(row => row.valid)
  if (validRows.length === 0) {
    ElMessage.warning('没有可导入的有效数据')
    return
  }
  
  const rowsToImport = validRows.map(row => ({
    ...row,
    duplicate_action: row.is_duplicate ? (row.duplicate_action || duplicateAction.value) : 'keep_import'
  }))
  
  isImporting.value = true
  try {
    const response = await api.post('/payments/import-execute', rowsToImport)
    if (response.code === 200) {
      importResult.value = response.data
      importStep.value = 3
      fetchPayments()
    } else {
      ElMessage.error(response.message)
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
  importSummary.value = { total: 0, valid_count: 0, invalid_count: 0, duplicate_count: 0 }
  importResult.value = { total: 0, success_count: 0, fail_count: 0, results: [] }
}

onMounted(() => {
  fetchPayments()
  fetchContracts()
})

watch(showImportModal, (newVal) => {
  if (!newVal) {
    importStep.value = 1
    importRows.value = []
    importSummary.value = { total: 0, valid_count: 0, invalid_count: 0, duplicate_count: 0 }
    importResult.value = { total: 0, success_count: 0, fail_count: 0, results: [] }
  }
})
</script>

<style scoped>
.import-step-1 {
  text-align: center;
  padding: 40px 0;
}

.import-tip {
  margin-top: 20px;
  text-align: left;
  font-size: 13px;
  color: #666;
  line-height: 1.8;
  background: #f5f7fa;
  padding: 16px;
  border-radius: 8px;
}

.import-summary {
  display: flex;
  gap: 24px;
  margin-bottom: 16px;
}

.summary-item {
  font-size: 14px;
  color: #666;
}

.summary-item.valid {
  color: #67c23a;
}

.summary-item.invalid {
  color: #f56c6c;
}

.summary-item.duplicate {
  color: #e6a23c;
}

.duplicate-action-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #fefce8;
  border-radius: 8px;
  margin-bottom: 16px;
}

.action-label {
  font-size: 14px;
  color: #d4a72c;
  font-weight: bold;
}

.import-table-wrapper {
  max-height: 400px;
  overflow-y: auto;
}

.error-text {
  color: #f56c6c;
  font-size: 12px;
}

.duplicate-text {
  color: #e6a23c;
  font-size: 12px;
}

.success-text {
  color: #67c23a;
  font-size: 12px;
}

.compare-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.import-label {
  font-size: 12px;
  color: #67c23a;
  background: #f0f9eb;
  padding: 2px 6px;
  border-radius: 4px;
}

.system-label {
  font-size: 12px;
  color: #e6a23c;
  background: #fdf6ec;
  padding: 2px 6px;
  border-radius: 4px;
}

.import-result {
  text-align: center;
  padding: 40px 0;
}

.result-icon {
  font-size: 64px;
  margin-bottom: 16px;
}

.result-icon.success {
  color: #67c23a;
}

.result-stats {
  font-size: 14px;
  color: #666;
}

.result-stats .success {
  color: #67c23a;
  font-weight: bold;
}

.result-stats .error {
  color: #f56c6c;
  font-weight: bold;
}

.fail-list {
  text-align: left;
  margin-top: 20px;
  padding: 16px;
  background: #fef0f0;
  border-radius: 8px;
  max-height: 200px;
  overflow-y: auto;
}

.fail-list h4 {
  margin-bottom: 12px;
  color: #f56c6c;
}

.fail-list ul {
  padding-left: 20px;
  margin: 0;
}

.fail-list li {
  font-size: 13px;
  color: #f56c6c;
  margin-bottom: 4px;
}

.duplicate-dialog-content {
  padding: 16px 0;
}

.dialog-tip {
  font-size: 14px;
  color: #666;
  margin-bottom: 16px;
}

.duplicate-table-wrapper {
  max-height: 400px;
  overflow-y: auto;
}
</style>