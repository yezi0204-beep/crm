<template>
  <div class="customers">
    <div class="header-row">
      <el-button type="primary" @click="showAddModal = true" class="add-btn">
        <el-icon><Plus /></el-icon>
        添加客户
      </el-button>
      <div class="search-wrapper">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索客户名称、联系人、手机号..."
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
        <el-table :data="filteredCustomers" stripe border class="data-table">
          <el-table-column prop="name" label="联系人" min-width="100" sortable />
          <el-table-column prop="phone" label="手机号" min-width="120" sortable />
          <el-table-column prop="company" label="公司名称" min-width="160" sortable show-overflow-tooltip />
          <el-table-column prop="level" label="客户等级" min-width="100" sortable>
            <template #default="scope">
              <el-tag :type="getLevelType(scope.row.level)" size="small">{{ getLevelLabel(scope.row.level) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="source" label="来源" min-width="100" sortable />
          <el-table-column prop="owner_name" label="负责人" min-width="90" sortable />
          <el-table-column prop="last_follow" label="最后跟进" min-width="120" sortable />
          <el-table-column prop="created_at" label="创建时间" min-width="140" sortable />
          <el-table-column label="操作" min-width="200" fixed="right">
            <template #default="scope">
              <el-button size="small" @click="editCustomer(scope.row)">编辑</el-button>
              <el-button size="small" type="warning" @click="showFollow(scope.row)">跟进</el-button>
              <el-button size="small" type="primary" v-if="canEditOwner && scope.row.owner_id" @click="releaseToPool(scope.row)">释放</el-button>
              <el-button size="small" type="danger" @click="deleteCustomer(scope.row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
    
    <el-dialog v-model="showAddModal" :title="customerForm.id ? '编辑客户' : '添加客户'" width="500px">
      <el-form :model="customerForm" :rules="rules" ref="formRef">
        <el-form-item label="联系人" prop="name">
          <el-input v-model="customerForm.name" />
        </el-form-item>
        <el-form-item label="手机号" prop="phone">
          <el-input v-model="customerForm.phone" />
        </el-form-item>
        <el-form-item label="公司名称" prop="company">
          <el-input v-model="customerForm.company" />
        </el-form-item>
        <el-form-item label="客户等级">
          <el-select v-model="customerForm.level">
            <el-option label="A(重点)" value="A" />
            <el-option label="B(普通)" value="B" />
            <el-option label="C(一般)" value="C" />
          </el-select>
        </el-form-item>
        <el-form-item label="来源">
          <el-input v-model="customerForm.source" />
        </el-form-item>
        <el-form-item label="负责人">
          <el-select v-model="customerForm.owner_id" :disabled="!canEditOwner" placeholder="请选择负责人">
            <el-option v-for="user in users" :key="user.username" :label="user.name" :value="user.username" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddModal = false">取消</el-button>
        <el-button type="primary" @click="saveCustomer">确定</el-button>
      </template>
    </el-dialog>
    
    <el-dialog v-model="showFollowModal" :title="`客户跟进 - ${currentCustomer?.company || currentCustomer?.name}`" width="700px">
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
import { ref, reactive, computed, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const customers = ref([])
const showAddModal = ref(false)
const formRef = ref(null)
const users = ref([])

const showFollowModal = ref(false)
const followFormRef = ref(null)
const currentCustomer = ref(null)
const followLogs = ref([])

const followSearchKeyword = ref('')
const searchKeyword = ref('')

const filteredCustomers = computed(() => {
  if (!searchKeyword.value) return customers.value
  const keyword = searchKeyword.value.toLowerCase()
  return customers.value.filter(c => 
    (c.name && c.name.toLowerCase().includes(keyword)) ||
    (c.company && c.company.toLowerCase().includes(keyword)) ||
    (c.phone && c.phone.toLowerCase().includes(keyword))
  )
})

const handleSearch = () => {}

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

const customerForm = reactive({
  id: null,
  name: '',
  phone: '',
  company: '',
  level: 'B',
  source: '',
  owner_id: '',
  last_follow: '',
  created_at: ''
})

const rules = {
  name: [{ required: true, message: '请输入联系人', trigger: 'blur' }],
  phone: [{ required: true, message: '请输入手机号', trigger: 'blur' }],
  company: [{ required: true, message: '请输入公司名称', trigger: 'blur' }]
}

const canEditOwner = () => {
  return authStore.role === '主任' || authStore.role === '院长'
}

const fetchUsers = async () => {
  const response = await api.get('/users')
  if (response.code === 200) {
    users.value = response.data
  }
}

const getLevelType = (level) => {
  if (!level) return 'info'
  if (level.startsWith('A')) return 'danger'
  if (level.startsWith('B')) return 'warning'
  if (level.startsWith('C')) return 'info'
  return 'info'
}

const getLevelLabel = (level) => {
  if (!level) return ''
  if (level.startsWith('A')) return 'A(重点)'
  if (level.startsWith('B')) return 'B(普通)'
  if (level.startsWith('C')) return 'C(一般)'
  return level
}

const fetchCustomers = async () => {
  const response = await api.get('/customers')
  if (response.code === 200) {
    customers.value = response.data
  }
}

const saveCustomer = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (valid) {
      if (!customerForm.id) {
        customerForm.owner_id = authStore.username
      }
      
      try {
        let response
        if (customerForm.id) {
          response = await api.put(`/customers/${customerForm.id}`, customerForm)
        } else {
          response = await api.post('/customers', customerForm)
        }
        if (response.code === 200) {
          ElMessage.success('保存成功')
          showAddModal.value = false
          fetchCustomers()
        } else {
          ElMessage.error(response.message)
        }
      } catch (error) {
        ElMessage.error('保存失败')
      }
    }
  })
}

const editCustomer = (row) => {
  Object.assign(customerForm, row)
  showAddModal.value = true
}

const deleteCustomer = async (row) => {
  try {
    await ElMessageBox.confirm('确定要删除这个客户吗？', '提示', {
      type: 'warning'
    })
    
    const response = await api.delete(`/customers/${row.id}`)
    if (response.code === 200) {
      ElMessage.success('删除成功')
      fetchCustomers()
    } else {
      ElMessage.error(response.message)
    }
  } catch (error) {
    ElMessage.info('已取消删除')
  }
}

const showFollow = async (row) => {
  currentCustomer.value = row
  followLogs.value = []
  followSearchKeyword.value = ''
  showFollowModal.value = true
  await fetchFollowLogs(row.id)
}

const fetchFollowLogs = async (customerId) => {
  const params = { ref_type: 'customer', ref_id: customerId }
  if (followSearchKeyword.value) {
    params.keyword = followSearchKeyword.value
  }
  const response = await api.get('/follow_logs', params)
  if (response.code === 200) {
    followLogs.value = response.data
  }
}

const handleFollowSearch = () => {
  if (currentCustomer.value) {
    fetchFollowLogs(currentCustomer.value.id)
  }
}

const saveFollow = async () => {
  if (!followFormRef.value || !currentCustomer.value) return
  
  await followFormRef.value.validate(async (valid) => {
    if (valid) {
      try {
        const response = await api.post('/follow_logs', {
          ref_type: 'customer',
          ref_id: currentCustomer.value.id,
          ...followForm
        })
        if (response.code === 200) {
          ElMessage.success('跟进记录添加成功')
          await fetchFollowLogs(currentCustomer.value.id)
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
      await fetchFollowLogs(currentCustomer.value.id)
    } else {
      ElMessage.error(response.message)
    }
  } catch (error) {
    ElMessage.info('已取消删除')
  }
}

const releaseToPool = async (row) => {
  try {
    await ElMessageBox.confirm('确定要将该客户释放到公海池吗？', '提示', {
      type: 'warning'
    })
    
    const response = await api.post('/pool/release', { customer_ids: [row.id] })
    if (response.code === 200) {
      ElMessage.success(response.message)
      fetchCustomers()
    } else {
      ElMessage.error(response.message)
    }
  } catch (error) {
    ElMessage.info('已取消释放')
  }
}

onMounted(() => {
  fetchCustomers()
  fetchUsers()
})
</script>

<style scoped>
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
  font-weight: 600;
  color: #334155;
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
  font-weight: 600;
  color: #4ecdc4;
}

.log-time {
  font-size: 12px;
  color: #94a3b8;
}

.log-subject {
  font-weight: 600;
  margin-bottom: 8px;
  color: #334155;
}

.log-content {
  color: #64748b;
  margin-bottom: 8px;
}

.log-meta {
  font-size: 12px;
  color: #94a3b8;
  margin-bottom: 8px;
}

.log-meta span {
  margin-right: 16px;
}

.log-next {
  font-size: 12px;
  color: #10b981;
  background: #f0fdf4;
  padding: 8px;
  border-radius: 6px;
}

.follow-form {
  padding-top: 16px;
  border-top: 1px solid #e2e8f0;
}
</style>