<template>
  <div class="contracts">
    <div class="header-row">
      <div class="header-left">
        <el-button type="primary" @click="addContract" class="add-btn">
          <el-icon><Plus /></el-icon>
          新建合同
        </el-button>
        
        <el-button @click="showImportModal = true" class="import-btn">
          <el-icon><Upload /></el-icon>
          导入合同
        </el-button>
        
        <el-button @click="exportContracts" class="export-btn">
          <el-icon><Download /></el-icon>
          导出合同
        </el-button>
      </div>
      
      <div class="header-right">
        <div class="search-wrapper">
          <el-input 
            v-model="searchKeyword" 
            placeholder="搜索合同名称、编号、甲方..." 
            class="search-input"
            clearable
            @keyup.enter="handleSearch"
          />
          <el-button @click="handleSearch" class="search-btn">搜索</el-button>
        </div>
        
        <el-popover 
          v-model:visible="showColumnSelector" 
          placement="bottom-end" 
          trigger="click"
          width="200"
        >
          <template #reference>
            <el-button>
              ⚙️ 选择显示列
              <el-icon><ArrowDown /></el-icon>
            </el-button>
          </template>
        <div class="column-selector-content">
          <div v-for="col in allColumns" :key="col.prop" class="column-item">
            <el-checkbox 
              :model-value="visibleColumns.includes(col.prop)" 
              @change="(val) => toggleColumn(col.prop, val)"
            />
            {{ col.label }}
          </div>
          <div class="column-selector-footer">
            <el-button size="small" @click="showColumnSelector = false">确定</el-button>
          </div>
        </div>
      </el-popover>
      </div>
    </div>
    
    <div class="table-wrapper">
      <el-table :data="filteredContracts" stripe border class="data-table" @sort-change="handleSortChange">
      <template v-for="col in visibleColumnConfigs" :key="col.prop">
        <el-table-column 
          v-if="col.prop === 'total_amt'" 
          :prop="col.prop" 
          :label="col.label" 
          :width="col.width" 
          sortable="custom"
          :sort-order="sortField === 'total_amt' ? sortOrder : undefined"
        >
          <template #default="scope">
            {{ formatAmount(scope.row.total_amt) }}
          </template>
        </el-table-column>
        
        <el-table-column 
          v-else-if="col.prop === 'paid_amt'" 
          :prop="col.prop" 
          :label="col.label" 
          :width="col.width" 
          sortable="custom"
          :sort-order="sortField === 'paid_amt' ? sortOrder : undefined"
        >
          <template #default="scope">
            {{ formatAmount(scope.row.paid_amt) }}
          </template>
        </el-table-column>
        
        <el-table-column 
          v-else-if="col.prop === 'pending_amt'" 
          :prop="col.prop" 
          :label="col.label" 
          :width="col.width" 
          sortable="custom"
          :sort-order="sortField === 'pending_amt' ? sortOrder : undefined"
        >
          <template #default="scope">
            <span :class="{ 'pending-highlight': getPendingAmt(scope.row) > 0.01 }">
              {{ formatAmount(getPendingAmt(scope.row)) }}
            </span>
          </template>
        </el-table-column>
        
        <el-table-column 
          v-else-if="col.prop === 'status'" 
          :prop="col.prop" 
          :label="col.label" 
          :width="col.width" 
          sortable
        >
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status)" size="small">{{ scope.row.status }}</el-tag>
          </template>
        </el-table-column>
        
        <el-table-column 
          v-else-if="col.prop === 'acceptance_nodes' || col.prop === 'payment_nodes'" 
          :prop="col.prop" 
          :label="col.label" 
          :width="col.width" 
          show-overflow-tooltip
        />
        
        <el-table-column 
          v-else-if="col.prop === 'owner_name'" 
          :prop="col.prop" 
          :label="col.label" 
          :width="col.width"
        >
          <template #default="scope">
            <template v-if="isAdminRole">
              <el-select 
                v-if="editingOwnerId === scope.row.id" 
                :value="scope.row.owner_id" 
                @change="(val) => saveOwnerChange(scope.row.id, val)"
                @visible-change="(visible) => { if (!visible) setTimeout(() => { if (!savingOwnerId) editingOwnerId = null }, 200) }"
                style="width: 120px;"
                filterable
              >
                <el-option 
                  v-for="user in users" 
                  :key="user.username" 
                  :label="user.name" 
                  :value="user.username" 
                />
              </el-select>
              <span 
                v-else 
                @click="startEditOwner(scope.row)"
                style="cursor: pointer; color: #4ecdc4;"
              >
                {{ scope.row.owner_name || '未分配' }}
              </span>
            </template>
            <span v-else>{{ scope.row.owner_name || '未分配' }}</span>
          </template>
        </el-table-column>
        
        <el-table-column 
          v-else 
          :prop="col.prop" 
          :label="col.label" 
          :width="col.width" 
          :min-width="col.minWidth" 
          :sortable="col.sortable !== false"
        />
      </template>
      
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="scope">
          <el-button size="small" @click="editContract(scope.row)">编辑</el-button>
          <el-button size="small" type="danger" @click="deleteContract(scope.row)">删除</el-button>
          <el-button size="small" @click="previewFiles(scope.row)">预览文件</el-button>
        </template>
      </el-table-column>
    </el-table>
    </div>
    
    <el-dialog v-model="showAddModal" :title="contractForm.id ? '编辑合同' : '新建合同'" width="700px">
      <el-form :model="contractForm" :rules="rules" ref="formRef">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="合同名称" prop="contract_name">
              <el-input v-model="contractForm.contract_name" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="合同编号" prop="contract_no">
              <el-input v-model="contractForm.contract_no" @blur="validateContractNo" />
              <span v-if="!contractForm.id" style="font-size: 12px; color: #999;">请输入合同编号，系统将检查是否重复</span>
            </el-form-item>
          </el-col>
        </el-row>
        
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="甲方">
              <el-input v-model="contractForm.party_a" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="项目令号">
              <el-input v-model="contractForm.project_order_no" />
            </el-form-item>
          </el-col>
        </el-row>
        
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="合同总额(万)" prop="total_amt">
              <el-input-number v-model="contractForm.total_amt" :min="0" :step="0.01" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="签约日期">
              <el-date-picker v-model="contractForm.sign_date" type="date" />
            </el-form-item>
          </el-col>
        </el-row>
        
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="业态">
              <el-select v-model="contractForm.business_type">
                <el-option label="J" value="J" />
                <el-option label="M" value="M" />
                <el-option label="K" value="K" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="项目密级">
              <el-select v-model="contractForm.classification">
                <el-option label="绝密" value="绝密" />
                <el-option label="机密" value="机密" />
                <el-option label="秘密" value="秘密" />
                <el-option label="内部" value="内部" />
                <el-option label="公开" value="公开" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="合同状态">
              <el-select v-model="contractForm.status">
                <el-option label="执行中" value="执行中" />
                <el-option label="已完成" value="已完成" />
                <el-option label="已终止" value="已终止" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="负责人">
              <el-select v-model="contractForm.owner_id">
                <el-option v-for="user in users" :key="user.username" :label="user.name" :value="user.username" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        
        <el-form-item label="合同约定验收节点">
          <el-input v-model="contractForm.acceptance_nodes" type="textarea" :rows="3" />
        </el-form-item>
        
        <el-form-item label="合同约定回款节点">
          <el-input v-model="contractForm.payment_nodes" type="textarea" :rows="3" />
        </el-form-item>
        
        <el-divider content-position="left">📎 文件上传</el-divider>
        
        <el-form-item label="合同文本">
          <el-upload
            :action="uploadUrl"
            :headers="uploadHeaders"
            :data="{ contract_id: contractForm.id || 0, file_type: 'contract' }"
            :on-success="handleUploadSuccess"
            :on-error="handleUploadError"
            :file-list="contractFileList"
            accept=".pdf,.docx,.txt,.md"
          >
            <el-button type="primary">点击上传</el-button>
          </el-upload>
        </el-form-item>
        
        <el-form-item label="技术协议文本">
          <el-upload
            :action="uploadUrl"
            :headers="uploadHeaders"
            :data="{ contract_id: contractForm.id || 0, file_type: 'tech' }"
            :on-success="handleUploadSuccess"
            :on-error="handleUploadError"
            :file-list="techFileList"
            accept=".pdf,.docx,.txt,.md"
          >
            <el-button type="primary">点击上传</el-button>
          </el-upload>
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="showAddModal = false">取消</el-button>
        <el-button type="primary" @click="saveContract">确定</el-button>
      </template>
    </el-dialog>
    
    <el-dialog v-model="showPreviewModal" title="文件预览" width="900px" height="70vh">
      <div v-if="previewContractFile" class="preview-section">
        <h4>📄 合同文本</h4>
        <div class="file-info">
          <a :href="previewContractFile" target="_blank" class="file-link">{{ previewContractFileName }}</a>
          <el-button size="small" @click="downloadFile(previewContractFile, previewContractFileName)" class="download-btn">下载</el-button>
        </div>
        <div v-if="isLoadingContract" class="loading-preview">
          <el-spin tip="加载中..." />
        </div>
        <div v-else-if="isPdfFile(previewContractFileName) && contractBlobUrl" class="pdf-preview">
          <embed :src="contractBlobUrl" type="application/pdf" class="pdf-frame" />
        </div>
        <div v-else class="text-preview">
          <pre>{{ previewTextContent || '暂无预览内容' }}</pre>
        </div>
      </div>
      <div v-else class="no-file">暂无合同文本文件</div>
      
      <el-divider />
      
      <div v-if="previewTechFile" class="preview-section">
        <h4>📋 技术协议文本</h4>
        <div class="file-info">
          <a :href="previewTechFile" target="_blank" class="file-link">{{ previewTechFileName }}</a>
          <el-button size="small" @click="downloadFile(previewTechFile, previewTechFileName)" class="download-btn">下载</el-button>
        </div>
        <div v-if="isLoadingTech" class="loading-preview">
          <el-spin tip="加载中..." />
        </div>
        <div v-else-if="isPdfFile(previewTechFileName) && techBlobUrl" class="pdf-preview">
          <embed :src="techBlobUrl" type="application/pdf" class="pdf-frame" />
        </div>
        <div v-else class="text-preview">
          <pre>{{ previewTechTextContent || '暂无预览内容' }}</pre>
        </div>
      </div>
      <div v-else class="no-file">暂无技术协议文件</div>
    </el-dialog>
    
    <el-dialog v-model="showImportModal" title="导入合同" width="900px">
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
          2. 必须包含以下列：合同编号、合同名称、合同总额(万)<br>
          3. 可选列：甲方、项目令号、签约日期、业态、密级、负责人、验收节点、回款节点<br>
          4. 合同编号必须唯一，重复编号将无法导入
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
            <el-table-column prop="row_index" label="行号" width="80" />
            <el-table-column prop="data.contract_no" label="合同编号" width="150" />
            <el-table-column prop="data.contract_name" label="合同名称" width="150" />
            <el-table-column prop="data.party_a" label="甲方" width="120" />
            <el-table-column prop="data.total_amt" label="合同总额(万)" width="120">
              <template #default="scope">
                {{ (scope.row.data.total_amt || 0) / 10000 }}
              </template>
            </el-table-column>
            <el-table-column prop="valid" label="状态" width="100">
              <template #default="scope">
                <el-tag :type="scope.row.valid ? 'success' : 'danger'" size="small">
                  {{ scope.row.valid ? '有效' : '无效' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="errors" label="错误信息" width="200">
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
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { Plus, ArrowDown, Download, Upload, CircleCheck } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { useAuthStore } from '../stores/auth'
import { useRoute } from 'vue-router'

const authStore = useAuthStore()
const route = useRoute()
const contracts = ref([])
const users = ref([])
const searchKeyword = ref('')
const showAddModal = ref(false)
const showPreviewModal = ref(false)
const showColumnSelector = ref(false)
const showImportModal = ref(false)
const formRef = ref(null)
const editingOwnerId = ref(null)
const savingOwnerId = ref(null)

const sortField = ref('sign_date')
const sortOrder = ref('desc')

const importStep = ref(1)
const isImporting = ref(false)
const importRows = ref([])
const importSummary = ref({ total: 0, valid_count: 0, invalid_count: 0 })
const importResult = ref({ total: 0, success_count: 0, fail_count: 0, results: [] })

const allColumns = [
  { prop: 'contract_name', label: '合同名称', width: '', minWidth: 120 },
  { prop: 'contract_no', label: '合同编号', width: 120 },
  { prop: 'party_a', label: '甲方', width: '', minWidth: 120 },
  { prop: 'total_amt', label: '合同总额(万)', width: 110 },
  { prop: 'paid_amt', label: '已回款(万)', width: 110 },
  { prop: 'pending_amt', label: '待回款(万)', width: 110 },
  { prop: 'sign_date', label: '签约日期', width: 110 },
  { prop: 'business_type', label: '业态', width: 90 },
  { prop: 'classification', label: '密级', width: 80 },
  { prop: 'owner_name', label: '负责人', width: 90 },
  { prop: 'acceptance_nodes', label: '验收节点', width: 120 },
  { prop: 'payment_nodes', label: '回款节点', width: 120 },
  { prop: 'status', label: '状态', width: 80 }
]

const visibleColumns = ref([
  'contract_name', 'contract_no', 'party_a', 'total_amt', 
  'paid_amt', 'pending_amt', 'sign_date', 'business_type', 
  'classification', 'owner_name', 'acceptance_nodes', 'payment_nodes', 'status'
])

const visibleColumnConfigs = computed(() => {
  return allColumns.filter(col => visibleColumns.value.includes(col.prop))
})

const filteredContracts = computed(() => {
  if (!searchKeyword.value) return contracts.value
  const keyword = searchKeyword.value.toLowerCase()
  return contracts.value.filter(record => 
    (record.contract_name && record.contract_name.toLowerCase().includes(keyword)) ||
    (record.contract_no && record.contract_no.toLowerCase().includes(keyword)) ||
    (record.party_a && record.party_a.toLowerCase().includes(keyword)) ||
    (record.owner_name && record.owner_name.toLowerCase().includes(keyword))
  )
})

const isAdminRole = computed(() => {
  return authStore.role === '主任' || authStore.role === '院长'
})

const contractForm = reactive({
  id: null,
  contract_name: '',
  contract_no: '',
  party_a: '',
  project_order_no: '',
  total_amt: 0,
  sign_date: '',
  business_type: '',
  classification: '',
  status: '执行中',
  owner_id: '',
  acceptance_nodes: '',
  payment_nodes: '',
  contract_file_path: '',
  tech_agreement_file_path: ''
})

const contractFileList = ref([])
const techFileList = ref([])

const previewContractFile = ref('')
const previewContractFileName = ref('')
const previewTechFile = ref('')
const previewTechFileName = ref('')
const previewTextContent = ref('')
const previewTechTextContent = ref('')
const contractBlobUrl = ref('')
const techBlobUrl = ref('')
const isLoadingContract = ref(false)
const isLoadingTech = ref(false)

const uploadUrl = computed(() => '/api/contracts/upload')
const importParseUrl = computed(() => '/api/contracts/import-parse')
const uploadHeaders = computed(() => ({
  Authorization: `Bearer ${authStore.token}`
}))

const validateContractNoRule = async (rule, value, callback) => {
  if (!value) {
    callback()
    return
  }
  
  try {
    const params = { contract_no: value }
    if (contractForm.id) {
      params.exclude_id = contractForm.id
    }
    const response = await api.get('/contracts/check-no', { params })
    if (response.code === 200 && response.data.exists) {
      callback(new Error('合同编号已存在，请重新输入'))
    } else {
      callback()
    }
  } catch (error) {
    console.error('验证合同编号失败:', error)
    callback()
  }
}

const validateContractNo = async () => {
  if (!contractForm.contract_no) return
  await validateContractNoRule({}, contractForm.contract_no, () => {})
}

const rules = {
  contract_name: [{ required: true, message: '请输入合同名称', trigger: 'blur' }],
  contract_no: [
    { required: true, message: '请输入合同编号', trigger: 'blur' },
    { validator: validateContractNoRule, trigger: 'blur' }
  ],
  total_amt: [{ required: true, message: '请输入合同总额', trigger: 'blur' }]
}

const formatAmount = (value) => {
  return ((value || 0) / 10000).toFixed(2)
}

const getPendingAmt = (row) => {
  const total = row.total_amt || 0
  const paid = row.paid_amt || 0
  return Math.max(0, total - paid)
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
    ElMessage.error(response.message)
  }
}

const handleImportError = (error) => {
  ElMessage.error('解析失败：' + (error.message || '未知错误'))
}

const executeImport = async () => {
  const validRows = importRows.value.filter(row => row.valid)
  if (validRows.length === 0) {
    ElMessage.warning('没有可导入的有效数据')
    return
  }
  
  isImporting.value = true
  try {
    const response = await api.post('/contracts/import-execute', validRows)
    if (response.code === 200) {
      importResult.value = response.data
      importStep.value = 3
      fetchContracts()
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
  importSummary.value = { total: 0, valid_count: 0, invalid_count: 0 }
  importResult.value = { total: 0, success_count: 0, fail_count: 0, results: [] }
}

const sortPendingAmount = (a, b) => {
  const pendingA = (a.total_amt || 0) - (a.paid_amt || 0)
  const pendingB = (b.total_amt || 0) - (b.paid_amt || 0)
  return pendingA - pendingB
}

const getStatusType = (status) => {
  const types = {
    '执行中': 'success',
    '已完成': 'primary',
    '已终止': 'danger'
  }
  return types[status] || 'info'
}

const toggleColumn = (prop, checked) => {
  const index = visibleColumns.value.indexOf(prop)
  if (checked !== undefined) {
    if (checked && index === -1) {
      visibleColumns.value.push(prop)
    } else if (!checked && index > -1) {
      visibleColumns.value.splice(index, 1)
    }
  } else {
    if (index > -1) {
      visibleColumns.value.splice(index, 1)
    } else {
      visibleColumns.value.push(prop)
    }
  }
}

const isPdfFile = (fileName) => {
  return fileName && fileName.toLowerCase().endsWith('.pdf')
}

const downloadFile = async (url, fileName) => {
  try {
    const response = await fetch(url, {
      headers: { Authorization: `Bearer ${authStore.token}` }
    })
    
    if (!response.ok) {
      ElMessage.error('下载失败：' + response.statusText)
      return
    }
    
    const blob = await response.blob()
    const blobUrl = window.URL.createObjectURL(blob)
    
    const link = document.createElement('a')
    link.href = blobUrl
    link.download = fileName || url.split('/').pop()
    link.click()
    
    window.URL.revokeObjectURL(blobUrl)
  } catch (error) {
    ElMessage.error('下载失败：' + error.message)
  }
}

const fetchContracts = async () => {
  const response = await api.get('/contracts', { 
    sort_field: sortField.value, 
    sort_order: sortOrder.value 
  })
  if (response.code === 200) {
    contracts.value = response.data
  }
}

const handleSortChange = (sort) => {
  sortField.value = sort.prop
  sortOrder.value = sort.order || 'asc'
  fetchContracts()
}

const handleSearch = () => {
}

const fetchUsers = async () => {
  const response = await api.get('/users')
  if (response.code === 200) {
    users.value = response.data
  }
}

const saveContract = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (valid) {
      const payload = {
        ...contractForm,
        total_amt: (contractForm.total_amt || 0) * 10000
      }
      
      if (!contractForm.id) {
        payload.owner_id = authStore.username
        payload.status = '执行中'
      }
      
      try {
        let response
        if (contractForm.id) {
          response = await api.put(`/contracts/${contractForm.id}`, payload)
        } else {
          console.log('Creating contract with payload:', JSON.stringify(payload))
          response = await api.post('/contracts', payload)
        }
        
        if (response.code === 200) {
          ElMessage.success('保存成功')
          showAddModal.value = false
          fetchContracts()
        } else {
          ElMessage.error(response.message)
        }
      } catch (error) {
        console.error('Save contract error:', error)
        ElMessage.error('保存失败')
      }
    }
  })
}

const editContract = (row) => {
  Object.assign(contractForm, row)
  contractForm.total_amt = (row.total_amt || 0) / 10000
  contractFileList.value = []
  techFileList.value = []
  if (row.contract_file_path) {
    contractFileList.value = [{ name: row.contract_file_path.split('/').pop(), url: row.contract_file_path }]
  }
  if (row.tech_agreement_file_path) {
    techFileList.value = [{ name: row.tech_agreement_file_path.split('/').pop(), url: row.tech_agreement_file_path }]
  }
  showAddModal.value = true
}

const startEditOwner = (row) => {
  editingOwnerId.value = row.id
}

const saveOwnerChange = async (contractId, newOwnerId) => {
  savingOwnerId.value = contractId
  try {
    console.log('saveOwnerChange called:', contractId, newOwnerId)
    const response = await api.post(`/contracts/${contractId}/owner`, {
      owner_id: newOwnerId
    })
    if (response.code === 200) {
      ElMessage.success('负责人修改成功')
      editingOwnerId.value = null
      fetchContracts()
    } else {
      ElMessage.error(response.message || '修改失败')
      editingOwnerId.value = null
    }
  } catch (error) {
    console.error('修改负责人失败:', error)
    ElMessage.error('网络错误，请重试')
    editingOwnerId.value = null
  } finally {
    savingOwnerId.value = null
  }
}

const addContract = () => {
  Object.assign(contractForm, {
    id: null,
    contract_name: '',
    contract_no: '',
    party_a: '',
    project_order_no: '',
    total_amt: 0,
    sign_date: '',
    business_type: '',
    classification: '',
    status: '执行中',
    owner_id: '',
    acceptance_nodes: '',
    payment_nodes: '',
    contract_file_path: '',
    tech_agreement_file_path: ''
  })
  contractFileList.value = []
  techFileList.value = []
  showAddModal.value = true
}

const deleteContract = async (row) => {
  try {
    await ElMessageBox.confirm('确定要删除这个合同吗？', '提示', {
      type: 'warning'
    })
    
    const response = await api.delete(`/contracts/${row.id}`)
    if (response.code === 200) {
      ElMessage.success('删除成功')
      fetchContracts()
    } else {
      ElMessage.error(response.message)
    }
  } catch (error) {
    ElMessage.info('已取消删除')
  }
}

const exportContracts = () => {
  if (contracts.value.length === 0) {
    ElMessage.info('暂无数据可导出')
    return
  }
  
  const exportColumns = allColumns.filter(col => visibleColumns.value.includes(col.prop))
  
  const escapeCsvValue = (value) => {
    if (value === null || value === undefined) {
      return ''
    }
    let strValue = String(value)
    strValue = strValue.replace(/"/g, '""')
    return `"${strValue}"`
  }
  
  let csvContent = '\uFEFF' + exportColumns.map(col => escapeCsvValue(col.label)).join(',') + '\n'
  
  contracts.value.forEach(row => {
    const rowData = exportColumns.map(col => {
      let value = row[col.prop]
      if (col.prop === 'total_amt' || col.prop === 'paid_amt') {
        value = ((value || 0) / 10000).toFixed(2)
      } else if (col.prop === 'pending_amt') {
        value = (((row.total_amt || 0) - (row.paid_amt || 0)) / 10000).toFixed(2)
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
  link.setAttribute('download', `合同列表_${timestamp}.csv`)
  link.style.visibility = 'hidden'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  
  ElMessage.success('导出成功')
}

const previewFiles = async (row) => {
  previewTextContent.value = ''
  previewTechTextContent.value = ''
  isLoadingContract.value = false
  isLoadingTech.value = false
  
  if (contractBlobUrl.value) {
    window.URL.revokeObjectURL(contractBlobUrl.value)
    contractBlobUrl.value = ''
  }
  if (techBlobUrl.value) {
    window.URL.revokeObjectURL(techBlobUrl.value)
    techBlobUrl.value = ''
  }
  
  showPreviewModal.value = true
  
  if (row.contract_file_path) {
    const downloadUrl = `/api/contracts/download/${row.id}/contract`
    previewContractFile.value = downloadUrl
    previewContractFileName.value = row.contract_file_path.split('/').pop()
    
    isLoadingContract.value = true
    try {
      const response = await fetch(downloadUrl, {
        headers: { Authorization: `Bearer ${authStore.token}` }
      })
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      
      const contentType = response.headers.get('Content-Type')
      if (isPdfFile(previewContractFileName.value) || contentType?.includes('application/pdf')) {
        const blob = await response.blob()
        contractBlobUrl.value = window.URL.createObjectURL(blob)
      } else if (contentType?.includes('text/') || previewContractFileName.value.match(/\.(txt|md)$/i)) {
        previewTextContent.value = await response.text()
      } else {
        previewTextContent.value = '该文件类型暂不支持预览，请下载查看'
      }
    } catch (error) {
      console.error('预览合同文件失败:', error)
      previewTextContent.value = '无法预览文本内容: ' + error.message
    } finally {
      isLoadingContract.value = false
    }
  } else {
    previewContractFile.value = ''
    contractBlobUrl.value = ''
  }
  
  if (row.tech_agreement_file_path) {
    const downloadUrl = `/api/contracts/download/${row.id}/tech`
    previewTechFile.value = downloadUrl
    previewTechFileName.value = row.tech_agreement_file_path.split('/').pop()
    
    isLoadingTech.value = true
    try {
      const response = await fetch(downloadUrl, {
        headers: { Authorization: `Bearer ${authStore.token}` }
      })
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      
      const contentType = response.headers.get('Content-Type')
      if (isPdfFile(previewTechFileName.value) || contentType?.includes('application/pdf')) {
        const blob = await response.blob()
        techBlobUrl.value = window.URL.createObjectURL(blob)
      } else if (contentType?.includes('text/') || previewTechFileName.value.match(/\.(txt|md)$/i)) {
        previewTechTextContent.value = await response.text()
      } else {
        previewTechTextContent.value = '该文件类型暂不支持预览，请下载查看'
      }
    } catch (error) {
      console.error('预览技术协议文件失败:', error)
      previewTechTextContent.value = '无法预览文本内容: ' + error.message
    } finally {
      isLoadingTech.value = false
    }
  } else {
    previewTechFile.value = ''
    techBlobUrl.value = ''
  }
}

const handleUploadSuccess = () => {
  ElMessage.success('文件上传成功')
}

const handleUploadError = () => {
  ElMessage.error('文件上传失败')
}

onMounted(() => {
  fetchContracts()
  fetchUsers()
  const kw = route.query.keyword
  if (kw) {
    searchKeyword.value = kw
  }
})

watch(() => route.query.keyword, (newKeyword) => {
  if (newKeyword) {
    searchKeyword.value = newKeyword
  }
})

watch(showAddModal, (newVal) => {
  if (!newVal) {
    contractFileList.value = []
    techFileList.value = []
  } else {
    if (!contractForm.id) {
      Object.assign(contractForm, {
        id: null,
        contract_name: '',
        contract_no: '',
        party_a: '',
        project_order_no: '',
        total_amt: 0,
        sign_date: '',
        business_type: '',
        classification: '',
        status: '执行中',
        owner_id: '',
        is_audit: 0,
        pending_acceptance_amount: 0,
        cost: 0,
        gross_profit: 0,
        acceptance_date: '',
        expected_income_date: '',
        expected_income_year: '',
        total_cost: 0,
        acceptance_nodes: '',
        payment_nodes: '',
        b_id: ''
      })
    }
  }
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
.contracts {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.header-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-left: auto;
}

.search-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

.search-input {
  width: 200px;
}

.search-btn {
  height: 40px;
}

.add-btn {
  align-self: flex-start;
}

.export-btn {
}

.column-selector-content {
  padding: 8px 0;
}

.column-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  cursor: pointer;
}

.column-item:hover {
  background: #f5f7fa;
}

.column-selector-footer {
  display: flex;
  justify-content: flex-end;
  padding: 8px 16px;
  border-top: 1px solid #eee;
  margin-top: 8px;
}

.table-wrapper {
  overflow-x: auto;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.data-table {
  width: 100%;
  min-width: 100%;
}

.preview-section {
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
}

.file-info {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.file-link {
  color: #4ecdc4;
  text-decoration: none;
  font-weight: bold;
}

.download-btn {
  margin-left: auto;
}

.pdf-preview {
  height: 500px;
}

.pdf-frame {
  width: 100%;
  height: 100%;
  border-radius: 8px;
}

.loading-preview {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 400px;
}

.text-preview {
  max-height: 400px;
  overflow-y: auto;
  background: #fff;
  padding: 16px;
  border-radius: 8px;
  font-family: monospace;
  white-space: pre-wrap;
}

.no-file {
  padding: 16px;
  color: #999;
  background: #f5f7fa;
  border-radius: 8px;
  text-align: center;
}

.pending-highlight {
  color: #f56c6c;
  font-weight: bold;
}

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

.import-table-wrapper {
  max-height: 400px;
  overflow-y: auto;
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
</style>