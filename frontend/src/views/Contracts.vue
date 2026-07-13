<template>
  <div class="contracts">
    <div class="header-row">
      <el-button type="primary" @click="showAddModal = true" class="add-btn">
        <el-icon><Plus /></el-icon>
        新建合同
      </el-button>
      
      <el-dropdown @command="toggleColumn" class="column-selector">
        <el-button>
          ⚙️ 选择显示列
          <el-icon><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item v-for="col in allColumns" :key="col.prop" :command="col.prop">
              <el-checkbox :checked="visibleColumns.includes(col.prop)" />
              {{ col.label }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
    
    <el-table :data="contracts" stripe border class="data-table">
      <template v-for="col in visibleColumnConfigs" :key="col.prop">
        <el-table-column 
          v-if="col.prop === 'total_amt'" 
          :prop="col.prop" 
          :label="col.label" 
          :width="col.width" 
          sortable
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
          sortable
        >
          <template #default="scope">
            {{ formatAmount(scope.row.paid_amt) }}
          </template>
        </el-table-column>
        
        <el-table-column 
          v-else-if="col.prop === 'pending_amt'" 
          :label="col.label" 
          :width="col.width" 
          :sortable="true" 
          :sort-method="sortPendingAmount"
        >
          <template #default="scope">
            {{ formatAmount((scope.row.total_amt || 0) - (scope.row.paid_amt || 0)) }}
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
    
    <el-dialog v-model="showAddModal" title="新建合同" width="700px">
      <el-form :model="contractForm" :rules="rules" ref="formRef">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="合同名称" prop="contract_name">
              <el-input v-model="contractForm.contract_name" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="合同编号" prop="contract_no">
              <el-input v-model="contractForm.contract_no" />
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
                <el-option label="咨询服务" value="咨询服务" />
                <el-option label="技术开发" value="技术开发" />
                <el-option label="设备采购" value="设备采购" />
                <el-option label="工程建设" value="工程建设" />
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
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { Plus, ArrowDown } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const contracts = ref([])
const showAddModal = ref(false)
const showPreviewModal = ref(false)
const formRef = ref(null)

const allColumns = [
  { prop: 'contract_name', label: '合同名称', width: '', minWidth: 180 },
  { prop: 'contract_no', label: '合同编号', width: 150 },
  { prop: 'party_a', label: '甲方', width: '', minWidth: 180 },
  { prop: 'total_amt', label: '合同总额(万)', width: 130 },
  { prop: 'paid_amt', label: '已回款(万)', width: 130 },
  { prop: 'pending_amt', label: '待回款(万)', width: 130 },
  { prop: 'sign_date', label: '签约日期', width: 130 },
  { prop: 'business_type', label: '业态', width: 100 },
  { prop: 'classification', label: '密级', width: 100 },
  { prop: 'owner_name', label: '负责人', width: 100 },
  { prop: 'acceptance_nodes', label: '验收节点', width: 200 },
  { prop: 'payment_nodes', label: '回款节点', width: 200 },
  { prop: 'status', label: '状态', width: 100 }
]

const visibleColumns = ref([
  'contract_name', 'contract_no', 'party_a', 'total_amt', 
  'paid_amt', 'pending_amt', 'sign_date', 'business_type', 
  'classification', 'owner_name', 'status'
])

const visibleColumnConfigs = computed(() => {
  return allColumns.filter(col => visibleColumns.value.includes(col.prop))
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
const uploadHeaders = computed(() => ({
  Authorization: `Bearer ${authStore.token}`
}))

const rules = {
  contract_name: [{ required: true, message: '请输入合同名称', trigger: 'blur' }],
  contract_no: [{ required: true, message: '请输入合同编号', trigger: 'blur' }],
  total_amt: [{ required: true, message: '请输入合同总额', trigger: 'blur' }]
}

const formatAmount = (value) => {
  return ((value || 0) / 10000).toFixed(2)
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

const toggleColumn = (prop) => {
  const index = visibleColumns.value.indexOf(prop)
  if (index > -1) {
    visibleColumns.value.splice(index, 1)
  } else {
    visibleColumns.value.push(prop)
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
  const response = await api.get('/contracts')
  if (response.code === 200) {
    contracts.value = response.data
  }
}

const saveContract = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (valid) {
      contractForm.total_amt = (contractForm.total_amt || 0) * 10000
      contractForm.owner_id = authStore.username
      contractForm.status = '执行中'
      
      try {
        let response
        if (contractForm.id) {
          response = await api.put(`/contracts/${contractForm.id}`, contractForm)
        } else {
          response = await api.post('/contracts', contractForm)
        }
        
        if (response.code === 200) {
          ElMessage.success('保存成功')
          showAddModal.value = false
          fetchContracts()
        } else {
          ElMessage.error(response.message)
        }
      } catch (error) {
        ElMessage.error('保存失败')
      }
    }
  })
}

const editContract = (row) => {
  Object.assign(contractForm, row)
  contractForm.total_amt = (row.total_amt || 0) / 10000
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
}

.add-btn {
  align-self: flex-start;
}

.column-selector {
  margin-left: auto;
}

.data-table {
  width: 100%;
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
</style>