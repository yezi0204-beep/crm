<template>
  <div class="business">
    <div class="header-row">
      <div class="header-left">
        <el-button type="primary" @click="addBusiness" class="add-btn">
          <el-icon><Plus /></el-icon>
          添加商机
        </el-button>
        <el-button @click="exportBusiness" class="export-btn">
          <el-icon><Download /></el-icon>
          导出商机
        </el-button>
        <el-select v-model="statusFilter" @change="fetchBusiness" placeholder="状态筛选" class="status-filter">
          <el-option label="全部" value="all" />
          <el-option label="进行中" value="active" />
          <el-option label="已作废" value="deleted" />
        </el-select>
      </div>
      <div class="search-wrapper">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索商机名称、客户..."
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
        <el-table :data="filteredBusiness" stripe border class="data-table">
          <el-table-column prop="title" label="商机名称" min-width="130" sortable show-overflow-tooltip />
          <el-table-column prop="customer_name" label="客户" min-width="110" sortable show-overflow-tooltip />
          <el-table-column prop="stakeholder" label="干系人" min-width="90" sortable />
          <el-table-column prop="amount" label="预算(万)" min-width="100" sortable>
            <template #default="scope">
              {{ formatAmount(scope.row.amount) }}
            </template>
          </el-table-column>
          <el-table-column prop="customer_relation" label="客情关系" min-width="90" />
          <el-table-column prop="weekly_plan" label="本周安排" min-width="130" show-overflow-tooltip>
            <template #default="scope">
              {{ scope.row.weekly_plan || '暂无' }}
            </template>
          </el-table-column>
          <el-table-column prop="next_week_plan" label="下周计划" min-width="130" show-overflow-tooltip>
            <template #default="scope">
              {{ scope.row.next_week_plan || '暂无' }}
            </template>
          </el-table-column>
          <el-table-column prop="probability" label="项目落实概率" min-width="140" sortable>
            <template #default="scope">
              <div class="probability-cell">
                <el-tag :type="getProbabilityType(scope.row.probability)" size="small">
                  {{ getProbabilityLabel(scope.row.probability) }}
                </el-tag>
                <span class="probability-value">{{ scope.row.probability || 0 }}%</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="predict_date" label="预计成交" min-width="120" sortable :formatter="formatPredictDate" />
          <el-table-column prop="owner_name" label="负责人" min-width="80" sortable />
          <el-table-column prop="created_at" label="创建时间" min-width="130" sortable />
          <el-table-column label="操作" min-width="180" fixed="right">
            <template #default="scope">
              <template v-if="scope.row.status === 'active'">
                <el-button size="small" @click="editBusiness(scope.row)">编辑</el-button>
                <el-button size="small" type="warning" @click="showFollow(scope.row)">跟进</el-button>
                <el-button size="small" type="danger" @click="deleteBusiness(scope.row)">作废</el-button>
              </template>
              <template v-else>
                <el-button size="small" type="success" @click="restoreBusiness(scope.row)">恢复</el-button>
              </template>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
    
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
        <el-form-item label="项目落实概率">
          <el-select v-model="businessForm.probability" @change="onProbabilityChange">
            <el-option-group label="引导需求阶段 (0-30%)">
              <el-option label="0% - 定位目标客户" :value="0" />
              <el-option label="10% - 发现潜在客户" :value="10" />
              <el-option label="20% - 意向客户" :value="20" />
              <el-option label="30% - 引导客户立项" :value="30" />
            </el-option-group>
            <el-option-group label="能力展示阶段 (30-60%)">
              <el-option label="40% - 获得初步认可" :value="40" />
              <el-option label="50% - 方案交流" :value="50" />
              <el-option label="60% - 沟通技术方案" :value="60" />
            </el-option-group>
            <el-option-group label="方案确定阶段 (60-80%)">
              <el-option label="70% - 进入候选名单" :value="70" />
              <el-option label="80% - 投标" :value="80" />
            </el-option-group>
            <el-option-group label="商务谈判阶段 (80-90%)">
              <el-option label="85% - 成为候选人" :value="85" />
              <el-option label="90% - 进行商务谈判" :value="90" />
            </el-option-group>
            <el-option-group label="合同签订阶段 (90-100%)">
              <el-option label="95% - 办理合同签订手续" :value="95" />
            </el-option-group>
            <el-option-group label="销售实现 (100%)">
              <el-option label="100% - 完成合同签订" :value="100" />
            </el-option-group>
          </el-select>
        </el-form-item>
        <el-form-item label="预计成交日期">
          <el-date-picker v-model="businessForm.predict_date" type="month" value-format="YYYY-MM" placeholder="选择年月" />
        </el-form-item>
        <el-form-item label="行业">
          <el-input v-model="businessForm.industry" />
        </el-form-item>
        <el-form-item label="地区">
          <el-input v-model="businessForm.region" />
        </el-form-item>
        <el-form-item label="负责人">
          <el-select v-model="businessForm.owner_id" :disabled="!canEditOwner" placeholder="请选择负责人">
            <el-option v-for="user in users" :key="user.username" :label="user.name" :value="user.username" />
          </el-select>
        </el-form-item>
        <el-form-item label="客情关系">
          <el-select v-model="businessForm.customer_relation">
            <el-option label="初次接触" value="初次接触" />
            <el-option label="熟悉" value="熟悉" />
            <el-option label="良好" value="良好" />
            <el-option label="紧密" value="紧密" />
            <el-option label="战略合作" value="战略合作" />
          </el-select>
        </el-form-item>
        <el-form-item label="本周工作安排">
          <el-input v-model="businessForm.weekly_plan" type="textarea" :rows="3" placeholder="本周工作安排（每周自动更新）" />
        </el-form-item>
        <el-form-item label="下周工作计划">
          <el-input v-model="businessForm.next_week_plan" type="textarea" :rows="3" placeholder="下周工作计划（下周自动转为本周安排）" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="businessForm.note" type="textarea" :rows="3" placeholder="商机备注信息" />
        </el-form-item>
      </el-form>
      
      <div v-if="businessForm.id" class="plan-history-section">
        <el-divider content-position="left">历史工作计划</el-divider>
        <el-timeline v-if="planHistory.length > 0">
          <el-timeline-item 
            v-for="item in planHistory" 
            :key="item.id" 
            :timestamp="item.created_at"
            placement="top"
          >
            <el-card>
              <div class="plan-history-header">
                <span class="plan-type" :class="item.plan_type">{{ item.plan_type === 'weekly' ? '本周计划' : '下周计划' }}</span>
                <span class="plan-week">{{ item.week_label }}</span>
              </div>
              <div class="plan-content">{{ item.content }}</div>
            </el-card>
          </el-timeline-item>
        </el-timeline>
        <div v-else class="empty-history">
          暂无历史工作计划
        </div>
      </div>
      
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
import { ref, reactive, computed, onMounted } from 'vue'
import { Plus, Download } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const businessList = ref([])
const customers = ref([])
const users = ref([])
const showAddModal = ref(false)
const formRef = ref(null)

const showFollowModal = ref(false)
const followFormRef = ref(null)
const currentBusiness = ref(null)
const followLogs = ref([])

const followSearchKeyword = ref('')
const statusFilter = ref('active')
const searchKeyword = ref('')

const filteredBusiness = computed(() => {
  if (!searchKeyword.value) return businessList.value
  const keyword = searchKeyword.value.toLowerCase()
  return businessList.value.filter(b => 
    (b.title && b.title.toLowerCase().includes(keyword)) ||
    (b.customer_name && b.customer_name.toLowerCase().includes(keyword))
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

const PROBABILITY_STAGES = {
  0: { label: '引导需求', type: 'info', stage: '引导需求阶段' },
  10: { label: '引导需求', type: 'info', stage: '引导需求阶段' },
  20: { label: '引导需求', type: 'info', stage: '引导需求阶段' },
  30: { label: '引导需求', type: 'info', stage: '引导需求阶段' },
  40: { label: '能力展示', type: 'primary', stage: '能力展示阶段' },
  50: { label: '能力展示', type: 'primary', stage: '能力展示阶段' },
  60: { label: '方案确定', type: 'warning', stage: '方案确定阶段' },
  70: { label: '方案确定', type: 'warning', stage: '方案确定阶段' },
  80: { label: '方案确定', type: 'warning', stage: '方案确定阶段' },
  85: { label: '商务谈判', type: 'danger', stage: '商务谈判阶段' },
  90: { label: '商务谈判', type: 'danger', stage: '商务谈判阶段' },
  95: { label: '合同签订', type: 'success', stage: '合同签订阶段' },
  100: { label: '销售实现', type: 'success', stage: '销售实现' }
}

const businessForm = reactive({
  id: null,
  title: '',
  cust_id: '',
  stakeholder: '',
  amount: 0,
  probability: 0,
  stage: '引导需求阶段',
  predict_date: '',
  industry: '',
  region: '',
  customer_relation: '',
  weekly_plan: '',
  next_week_plan: '',
  plan_week: '',
  owner_id: '',
  note: ''
})

const planHistory = ref([])

const rules = {
  title: [{ required: true, message: '请输入商机名称', trigger: 'blur' }],
  amount: [{ required: true, message: '请输入金额', trigger: 'blur' }]
}

const canEditOwner = () => {
  return authStore.role === '主任' || authStore.role === '院长'
}

const formatPredictDate = (row) => {
  const date = row.predict_date
  if (!date) return ''
  return date.substring(0, 7)
}

const fetchUsers = async () => {
  const response = await api.get('/users')
  if (response.code === 200) {
    users.value = response.data
  }
}

const formatAmount = (value) => {
  return ((value || 0) / 10000).toFixed(2)
}

const getProbabilityType = (probability) => {
  const stage = PROBABILITY_STAGES[probability]
  return stage ? stage.type : 'info'
}

const getProbabilityLabel = (probability) => {
  const stage = PROBABILITY_STAGES[probability]
  return stage ? stage.label : '引导需求'
}

const onProbabilityChange = (probability) => {
  const stage = PROBABILITY_STAGES[probability]
  if (stage) {
    businessForm.stage = stage.stage
  }
}

const getStageType = (stage) => {
  const types = {
    '引导需求阶段': 'info',
    '能力展示阶段': 'primary',
    '方案确定阶段': 'warning',
    '商务谈判阶段': 'danger',
    '合同签订阶段': 'success',
    '销售实现': 'success'
  }
  return types[stage] || 'info'
}

const fetchBusiness = async () => {
  const response = await api.get('/business', { status: statusFilter.value })
  if (response.code === 200) {
    businessList.value = response.data
    if (businessList.value.length > 0) {
      const first = businessList.value[0]
      console.log('Business data sample:', {
        id: first.id,
        title: first.title,
        next_week_plan: first.next_week_plan,
        weekly_plan: first.weekly_plan,
        plan_week: first.plan_week
      })
    }
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
      
      if (businessForm.next_week_plan) {
        businessForm.plan_week = 'auto'
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

const addBusiness = () => {
  Object.assign(businessForm, {
    id: null,
    title: '',
    cust_id: '',
    stakeholder: '',
    amount: 0,
    probability: 0,
    stage: '引导需求阶段',
    predict_date: '',
    industry: '',
    region: '',
    customer_relation: '',
    weekly_plan: '',
    next_week_plan: '',
    plan_week: '',
    owner_id: '',
    note: ''
  })
  planHistory.value = []
  showAddModal.value = true
}

const fetchPlanHistory = async (businessId) => {
  const response = await api.get(`/business/${businessId}/plan_history`)
  if (response.code === 200) {
    planHistory.value = response.data
  }
}

const editBusiness = (row) => {
  const probability = row.probability || 0
  const stage = PROBABILITY_STAGES[probability]?.stage || '引导需求阶段'
  
  Object.assign(businessForm, {
    id: row.id,
    title: row.title || '',
    cust_id: row.cust_id || '',
    stakeholder: row.stakeholder || '',
    amount: (row.amount || 0) / 10000,
    probability: probability,
    stage: stage,
    predict_date: row.predict_date || '',
    industry: row.industry || '',
    region: row.region || '',
    customer_relation: row.customer_relation || '',
    weekly_plan: row.weekly_plan || '',
    next_week_plan: row.next_week_plan || '',
    plan_week: row.plan_week || '',
    owner_id: row.owner_id || '',
    note: row.note || ''
  })
  showAddModal.value = true
  fetchPlanHistory(row.id)
}

const deleteBusiness = async (row) => {
  try {
    await ElMessageBox.confirm('确定要作废这个商机吗？', '提示', {
      type: 'warning'
    })
    
    const response = await api.delete(`/business/${row.id}`)
    if (response.code === 200) {
      ElMessage.success('作废成功')
      fetchBusiness()
    } else {
      ElMessage.error(response.message)
    }
  } catch (error) {
    ElMessage.info('已取消作废')
  }
}

const restoreBusiness = async (row) => {
  try {
    await ElMessageBox.confirm('确定要恢复这个商机吗？', '提示', {
      type: 'warning'
    })
    
    const response = await api.put(`/business/${row.id}/restore`)
    if (response.code === 200) {
      ElMessage.success('恢复成功')
      fetchBusiness()
    } else {
      ElMessage.error(response.message)
    }
  } catch (error) {
    ElMessage.info('已取消恢复')
  }
}

const showFollow = async (row) => {
  console.log('showFollow called with row:', row)
  currentBusiness.value = row
  followLogs.value = []
  followSearchKeyword.value = ''
  showFollowModal.value = true
  await fetchFollowLogs(row.id)
}

const fetchFollowLogs = async (businessId) => {
  try {
    const params = { ref_type: 'business', ref_id: businessId }
    if (followSearchKeyword.value) {
      params.keyword = followSearchKeyword.value
    }
    console.log('fetchFollowLogs called with params:', params)
    const response = await api.get('/follow_logs', params)
    console.log('fetchFollowLogs response:', response)
    if (response.code === 200) {
      followLogs.value = response.data
      console.log('followLogs set to:', response.data)
    } else {
      ElMessage.error('获取跟进记录失败: ' + response.message)
    }
  } catch (error) {
    ElMessage.error('获取跟进记录失败，请稍后重试')
    console.error('fetchFollowLogs error:', error)
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

const exportBusiness = () => {
  const data = filteredBusiness.value
  if (data.length === 0) {
    ElMessage.info('暂无数据可导出')
    return
  }

  const exportColumns = [
    { prop: 'title', label: '商机名称' },
    { prop: 'customer_name', label: '客户' },
    { prop: 'stakeholder', label: '干系人' },
    { prop: 'amount', label: '预算(万)' },
    { prop: 'customer_relation', label: '客情关系' },
    { prop: 'weekly_plan', label: '本周安排' },
    { prop: 'next_week_plan', label: '下周计划' },
    { prop: 'probability', label: '项目落实概率(%)' },
    { prop: 'stage', label: '阶段' },
    { prop: 'predict_date', label: '预计成交日期' },
    { prop: 'owner_name', label: '负责人' },
    { prop: 'created_at', label: '创建时间' },
    { prop: 'note', label: '备注' }
  ]

  const escapeCsvValue = (value) => {
    if (value === null || value === undefined) {
      return ''
    }
    let strValue = String(value)
    strValue = strValue.replace(/"/g, '""')
    return `"${strValue}"`
  }

  let csvContent = '\uFEFF' + exportColumns.map(col => escapeCsvValue(col.label)).join(',') + '\n'

  data.forEach(row => {
    const rowData = exportColumns.map(col => {
      let value = row[col.prop]
      if (col.prop === 'amount') {
        value = ((value || 0) / 10000).toFixed(2)
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
  link.setAttribute('download', `商机列表_${timestamp}.csv`)
  link.style.visibility = 'hidden'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)

  ElMessage.success('导出成功')
}

onMounted(() => {
  fetchBusiness()
  fetchCustomers()
  fetchUsers()
})
</script>

<style scoped>
.status-filter {
  width: 150px;
}

.probability-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}

.probability-value {
  font-size: 12px;
  font-weight: 600;
  color: #334155;
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

.plan-history-section {
  margin-top: 16px;
}

.plan-history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.plan-type {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 6px;
}

.plan-type.weekly {
  background: #ecfeff;
  color: #06b6d4;
}

.plan-type.next_week {
  background: #f0fdf4;
  color: #10b981;
}

.plan-week {
  font-size: 12px;
  color: #94a3b8;
}

.plan-content {
  font-size: 14px;
  color: #334155;
  line-height: 1.6;
}
</style>