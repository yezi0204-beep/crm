<template>
  <div class="business">
    <el-button type="primary" @click="showAddModal = true" class="add-btn">
      <el-icon><Plus /></el-icon>
      添加商机
    </el-button>
    
    <el-table :data="businessList" stripe border class="data-table">
      <el-table-column prop="title" label="商机名称" min-width="180" sortable />
      <el-table-column prop="customer_name" label="客户" width="150" sortable />
      <el-table-column prop="stakeholder" label="干系人" width="120" sortable />
      <el-table-column prop="amount" label="金额(万)" width="120" sortable>
        <template #default="scope">
          {{ formatAmount(scope.row.amount) }}
        </template>
      </el-table-column>
      <el-table-column prop="stage" label="阶段" width="120" sortable>
        <template #default="scope">
          <el-tag :type="getStageType(scope.row.stage)" size="small">{{ scope.row.stage }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="predict_date" label="预计成交日期" width="150" sortable />
      <el-table-column prop="source" label="来源" width="120" sortable />
      <el-table-column prop="owner_name" label="负责人" width="100" sortable />
      <el-table-column prop="created_at" label="创建时间" width="150" sortable />
      <el-table-column label="操作" width="180">
        <template #default="scope">
          <el-button size="small" @click="editBusiness(scope.row)">编辑</el-button>
          <el-button size="small" type="warning" @click="showFollow(scope.row)">跟进</el-button>
          <el-button size="small" type="danger" @click="deleteBusiness(scope.row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    
    <el-dialog v-model="showAddModal" :title="businessForm.id ? '编辑商机' : '添加商机'" width="500px">
      <el-form :model="businessForm" :rules="rules" ref="formRef">
        <el-form-item label="商机名称" prop="title">
          <el-input v-model="businessForm.title" />
        </el-form-item>
        <el-form-item label="客户" prop="cust_id">
          <el-select v-model="businessForm.cust_id" placeholder="请选择客户" filterable remote :remote-method="searchCustomers">
            <el-option v-for="customer in customers" :key="customer.id" :label="customer.company || customer.name" :value="customer.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="干系人">
          <el-select v-model="businessForm.stakeholder" placeholder="请选择干系人" filterable allow-create>
            <el-option v-for="customer in customers" :key="customer.id" :label="customer.name" :value="customer.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="金额(万)" prop="amount">
          <el-input-number v-model="businessForm.amount" :min="0" :step="0.01" />
        </el-form-item>
        <el-form-item label="阶段">
          <el-select v-model="businessForm.stage">
            <el-option label="初步接触" value="初步接触" />
            <el-option label="需求确认" value="需求确认" />
            <el-option label="方案报价" value="方案报价" />
            <el-option label="商务谈判" value="商务谈判" />
            <el-option label="赢单成交" value="赢单成交" />
          </el-select>
        </el-form-item>
        <el-form-item label="预计成交日期">
          <el-date-picker v-model="businessForm.predict_date" type="date" />
        </el-form-item>
        <el-form-item label="来源">
          <el-input v-model="businessForm.source" />
        </el-form-item>
        <el-form-item label="行业">
          <el-input v-model="businessForm.industry" />
        </el-form-item>
        <el-form-item label="地区">
          <el-input v-model="businessForm.region" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddModal = false">取消</el-button>
        <el-button type="primary" @click="saveBusiness">确定</el-button>
      </template>
    </el-dialog>
    
    <el-dialog v-model="showFollowModal" :title="`商机跟进 - ${currentBusiness?.title}`" width="700px">
      <div class="follow-container">
        <div class="follow-history">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
            <h4>跟进记录</h4>
            <el-input 
              v-model="followSearchKeyword" 
              placeholder="搜索记录内容、主题、参与人..." 
              size="small" 
              style="width: 250px;"
              clearable
              @input="handleFollowSearch"
            />
          </div>
          <el-timeline v-if="followLogs.length > 0">
            <el-timeline-item 
              v-for="log in followLogs" 
              :key="log.id" 
              :timestamp="log.created_at"
              placement="top"
            >
              <el-card>
                <div class="log-header">
                  <span class="log-user">{{ log.user_name || log.user_id }}</span>
                  <span class="log-time">{{ log.log_time || log.created_at }}</span>
                </div>
                <div class="log-subject" v-if="log.subject">{{ log.subject }}</div>
                <div class="log-content">{{ log.content }}</div>
                <div class="log-meta" v-if="log.participants || log.location">
                  <span v-if="log.participants">参与人：{{ log.participants }}</span>
                  <span v-if="log.location">地点：{{ log.location }}</span>
                </div>
                <div class="log-next" v-if="log.next_plan">
                  <strong>下次计划：</strong>{{ log.next_plan }}
                </div>
                <el-button size="small" type="danger" @click="deleteFollowLog(log.id)" style="margin-top: 8px;">删除</el-button>
              </el-card>
            </el-timeline-item>
          </el-timeline>
          <div v-else class="empty-history">
            <el-empty description="暂无跟进记录" />
          </div>
        </div>
        
        <div class="follow-form">
          <h4>添加跟进记录</h4>
          <el-form :model="followForm" :rules="followRules" ref="followFormRef">
            <el-form-item label="主题" prop="subject">
              <el-input v-model="followForm.subject" placeholder="跟进主题" />
            </el-form-item>
            <el-form-item label="内容" prop="content">
              <el-input v-model="followForm.content" type="textarea" :rows="3" placeholder="跟进内容" />
            </el-form-item>
            <el-form-item label="跟进时间">
              <el-date-picker v-model="followForm.log_time" type="datetime" placeholder="选择跟进时间" />
            </el-form-item>
            <el-form-item label="参与人">
              <el-input v-model="followForm.participants" placeholder="参与人" />
            </el-form-item>
            <el-form-item label="地点">
              <el-input v-model="followForm.location" placeholder="跟进地点" />
            </el-form-item>
            <el-form-item label="下次计划">
              <el-input v-model="followForm.next_plan" type="textarea" :rows="2" placeholder="下次跟进计划" />
            </el-form-item>
          </el-form>
        </div>
      </div>
      
      <template #footer>
        <el-button @click="showFollowModal = false">取消</el-button>
        <el-button type="primary" @click="saveFollow">保存跟进</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const businessList = ref([])
const customers = ref([])
const showAddModal = ref(false)
const formRef = ref(null)

const showFollowModal = ref(false)
const followFormRef = ref(null)
const currentBusiness = ref(null)
const followLogs = ref([])

const followSearchKeyword = ref('')

const followForm = reactive({
  subject: '',
  content: '',
  log_time: '',
  participants: '',
  location: '',
  next_plan: ''
})

const followRules = {
  subject: [{ required: true, message: '请输入主题', trigger: 'blur' }],
  content: [{ required: true, message: '请输入跟进内容', trigger: 'blur' }]
}

const businessForm = reactive({
  id: null,
  title: '',
  cust_id: '',
  stakeholder: '',
  amount: 0,
  stage: '初步接触',
  predict_date: '',
  source: '',
  industry: '',
  region: '',
  owner_id: ''
})

const rules = {
  title: [{ required: true, message: '请输入商机名称', trigger: 'blur' }],
  amount: [{ required: true, message: '请输入金额', trigger: 'blur' }]
}

const formatAmount = (value) => {
  return ((value || 0) / 10000).toFixed(2)
}

const getStageType = (stage) => {
  const types = {
    '初步接触': 'info',
    '需求确认': 'primary',
    '方案报价': 'warning',
    '商务谈判': 'danger',
    '赢单成交': 'success',
    '需求确认中': 'primary',
    '方案报价中': 'warning',
    '合同签署': 'danger',
    '项目启动': 'success',
    '实施中': 'success',
    '已完成': 'success'
  }
  return types[stage] || 'info'
}

const fetchBusiness = async () => {
  const response = await api.get('/business')
  if (response.code === 200) {
    businessList.value = response.data
  }
}

const fetchCustomers = async (keyword = '') => {
  const response = await api.get('/customers', { params: { keyword } })
  if (response.code === 200) {
    customers.value = response.data
  }
}

const searchCustomers = async (keyword) => {
  await fetchCustomers(keyword)
}

const saveBusiness = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (valid) {
      businessForm.amount = (businessForm.amount || 0) * 10000
      
      if (!businessForm.id) {
        businessForm.owner_id = authStore.username
      }
      
      try {
        let response
        if (businessForm.id) {
          response = await api.put(`/business/${businessForm.id}`, businessForm)
        } else {
          response = await api.post('/business', businessForm)
        }
        if (response.code === 200) {
          ElMessage.success('保存成功')
          showAddModal.value = false
          fetchBusiness()
        } else {
          ElMessage.error(response.message)
        }
      } catch (error) {
        ElMessage.error('保存失败')
      }
    }
  })
}

const editBusiness = (row) => {
  Object.assign(businessForm, row)
  businessForm.amount = (row.amount || 0) / 10000
  showAddModal.value = true
}

const deleteBusiness = async (row) => {
  try {
    await ElMessageBox.confirm('确定要删除这个商机吗？', '提示', {
      type: 'warning'
    })
    
    const response = await api.delete(`/business/${row.id}`)
    if (response.code === 200) {
      ElMessage.success('删除成功')
      fetchBusiness()
    } else {
      ElMessage.error(response.message)
    }
  } catch (error) {
    ElMessage.info('已取消删除')
  }
}

const showFollow = async (row) => {
  currentBusiness.value = row
  followLogs.value = []
  followSearchKeyword.value = ''
  showFollowModal.value = true
  await fetchFollowLogs(row.id)
}

const fetchFollowLogs = async (businessId) => {
  const params = { ref_type: 'business', ref_id: businessId }
  if (followSearchKeyword.value) {
    params.keyword = followSearchKeyword.value
  }
  const response = await api.get('/follow_logs', params)
  if (response.code === 200) {
    followLogs.value = response.data
  }
}

const handleFollowSearch = () => {
  if (currentBusiness.value) {
    fetchFollowLogs(currentBusiness.value.id)
  }
}

const saveFollow = async () => {
  if (!followFormRef.value || !currentBusiness.value) return
  
  await followFormRef.value.validate(async (valid) => {
    if (valid) {
      try {
        const response = await api.post('/follow_logs', {
          ref_type: 'business',
          ref_id: currentBusiness.value.id,
          ...followForm
        })
        if (response.code === 200) {
          ElMessage.success('跟进记录添加成功')
          await fetchFollowLogs(currentBusiness.value.id)
          Object.assign(followForm, { subject: '', content: '', log_time: '', participants: '', location: '', next_plan: '' })
        } else {
          ElMessage.error(response.message)
        }
      } catch (error) {
        ElMessage.error('保存失败')
      }
    }
  })
}

const deleteFollowLog = async (logId) => {
  try {
    await ElMessageBox.confirm('确定要删除这条跟进记录吗？', '提示', {
      type: 'warning'
    })
    
    const response = await api.delete(`/follow_logs/${logId}`)
    if (response.code === 200) {
      ElMessage.success('删除成功')
      await fetchFollowLogs(currentBusiness.value.id)
    } else {
      ElMessage.error(response.message)
    }
  } catch (error) {
    ElMessage.info('已取消删除')
  }
}

onMounted(() => {
  fetchBusiness()
  fetchCustomers()
})
</script>

<style scoped>
.business {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.add-btn {
  align-self: flex-start;
}

.data-table {
  width: 100%;
}

.follow-container {
  max-height: 600px;
  overflow-y: auto;
}

.follow-history {
  margin-bottom: 24px;
}

.follow-history h4,
.follow-form h4 {
  margin-bottom: 16px;
  font-size: 14px;
  font-weight: bold;
  color: #303133;
}

.empty-history {
  padding: 40px 0;
}

.log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.log-user {
  font-weight: bold;
  color: #409eff;
}

.log-time {
  font-size: 12px;
  color: #909399;
}

.log-subject {
  font-weight: bold;
  margin-bottom: 8px;
  color: #303133;
}

.log-content {
  color: #606266;
  margin-bottom: 8px;
}

.log-meta {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}

.log-meta span {
  margin-right: 16px;
}

.log-next {
  font-size: 12px;
  color: #67c23a;
  background: #f0f9eb;
  padding: 8px;
  border-radius: 4px;
}

.follow-form {
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
}
</style>