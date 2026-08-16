<template>
  <div class="customers">
    <div class="header-row">
      <el-button type="primary" @click="showAddModal = true" class="add-btn">
        <el-icon><Plus /></el-icon>
        添加客户
      </el-button>
      <el-button type="success" @click="showAnalysis = true" class="add-btn">
        <el-icon><DataAnalysis /></el-icon>
        客户分析
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
        <el-select v-model="filterLevel" placeholder="等级" clearable style="width: 100px" @change="fetchCustomers">
          <el-option label="A(重点)" value="A" />
          <el-option label="B(普通)" value="B" />
          <el-option label="C(一般)" value="C" />
        </el-select>
        <el-select v-model="filterIndustry" placeholder="行业" clearable filterable style="width: 120px" @change="fetchCustomers">
          <el-option label="政府/军工" value="政府/军工" />
          <el-option label="教育" value="教育" />
          <el-option label="金融" value="金融" />
          <el-option label="制造" value="制造" />
          <el-option label="矿业" value="矿业" />
          <el-option label="通信" value="通信" />
          <el-option label="其它" value="其它" />
        </el-select>
        <el-select v-model="filterSource" placeholder="来源" clearable filterable allow-create style="width: 120px" @change="fetchCustomers">
          <el-option v-for="s in sourceOptions" :key="s" :label="s" :value="s" />
        </el-select>
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
          <el-table-column prop="address" label="地址" min-width="150" sortable show-overflow-tooltip />
          <el-table-column prop="owner_name" label="负责人" min-width="90" sortable />
          <el-table-column prop="created_at" label="创建时间" min-width="140" sortable />
          <el-table-column label="操作" min-width="260" fixed="right">
            <template #default="scope">
              <el-button size="small" @click="editCustomer(scope.row)">编辑</el-button>
              <el-button size="small" type="success" @click="showProfile(scope.row)">画像</el-button>
              <el-button size="small" type="primary" v-if="canEditOwner && scope.row.owner_id" @click="releaseToPool(scope.row)">释放</el-button>
              <el-button size="small" type="danger" @click="deleteCustomer(scope.row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
    
    <el-dialog v-model="showAddModal" :title="customerForm.id ? '编辑客户' : '添加客户'" width="500px" :close-on-click-modal="false" :close-on-press-escape="false">
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
        <el-form-item label="联系人姓名">
          <el-input v-model="customerForm.contact_name" placeholder="客户方对接人姓名" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="customerForm.email" placeholder="example@company.com" />
        </el-form-item>
        <el-form-item label="行业">
          <el-select v-model="customerForm.industry" placeholder="选择行业" filterable allow-create>
            <el-option label="政府/军工" value="政府/军工" />
            <el-option label="教育" value="教育" />
            <el-option label="金融" value="金融" />
            <el-option label="制造" value="制造" />
            <el-option label="矿业" value="矿业" />
            <el-option label="通信" value="通信" />
            <el-option label="其它" value="其它" />
          </el-select>
        </el-form-item>
        <el-form-item label="地区">
          <el-input v-model="customerForm.region" placeholder="如：北京/上海/四川" />
        </el-form-item>
        <el-form-item label="地址">
          <el-input v-model="customerForm.address" placeholder="详细地址" />
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
    
    <el-dialog v-model="showFollowModal" :title="`客户跟进 - ${currentCustomer?.company || currentCustomer?.name}`" width="700px" :close-on-click-modal="false" :close-on-press-escape="false">
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

    <el-drawer
      v-model="showProfileDrawer"
      :title="`客户3D画像 - ${profileData?.customer?.company || profileData?.customer?.name || ''}`"
      size="55%"
      direction="rtl"
      destroy-on-close
      :close-on-click-modal="false"
      :with-key="false"
    >
      <div v-loading="profileLoading" class="profile-container">
        <template v-if="profileData">
          <el-card class="profile-section">
            <template #header><span class="section-title">📋 基本信息</span></template>
            <el-descriptions :column="2" border>
              <el-descriptions-item label="联系人">{{ profileData.customer.name || '-' }}</el-descriptions-item>
              <el-descriptions-item label="公司">{{ profileData.customer.company || '-' }}</el-descriptions-item>
              <el-descriptions-item label="电话">{{ profileData.customer.phone || '-' }}</el-descriptions-item>
              <el-descriptions-item label="联系人姓名">{{ profileData.customer.contact_name || '-' }}</el-descriptions-item>
              <el-descriptions-item label="邮箱">{{ profileData.customer.email || '-' }}</el-descriptions-item>
              <el-descriptions-item label="行业">{{ profileData.customer.industry || '-' }}</el-descriptions-item>
              <el-descriptions-item label="地区">{{ profileData.customer.region || '-' }}</el-descriptions-item>
              <el-descriptions-item label="等级">
                <el-tag :type="getLevelType(profileData.customer.level)" size="small">{{ getLevelLabel(profileData.customer.level) }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="来源">{{ profileData.customer.source || '-' }}</el-descriptions-item>
              <el-descriptions-item label="负责人">{{ profileData.customer.owner_name || '-' }}</el-descriptions-item>
              <el-descriptions-item label="创建时间">{{ profileData.customer.created_at || '-' }}</el-descriptions-item>
              <el-descriptions-item label="最后跟进">{{ profileData.customer.last_follow || '-' }}</el-descriptions-item>
            </el-descriptions>
          </el-card>

          <div class="stats-row">
            <el-card class="stat-mini">
              <div class="stat-val">{{ profileData.stats.business_count }}</div>
              <div class="stat-lbl">商机数</div>
            </el-card>
            <el-card class="stat-mini">
              <div class="stat-val">¥{{ formatAmount(profileData.stats.contract_total_amt) }}</div>
              <div class="stat-lbl">合同总额(万)</div>
            </el-card>
            <el-card class="stat-mini">
              <div class="stat-val">{{ profileData.stats.visit_count }}</div>
              <div class="stat-lbl">拜访数</div>
            </el-card>
            <el-card class="stat-mini">
              <div class="stat-val">{{ profileData.stats.follow_count }}</div>
              <div class="stat-lbl">跟进数</div>
            </el-card>
          </div>

          <!-- 关联企业信息 -->
          <el-card class="profile-section" v-if="profileData.enterprise">
            <template #header>
              <span class="section-title">🏢 关联企业信息</span>
              <el-button text size="small" @click="goToEnterprise" style="float:right;">查看企业详情</el-button>
            </template>
            <el-descriptions :column="3" border size="small">
              <el-descriptions-item label="企业名称">{{ profileData.enterprise.name }}</el-descriptions-item>
              <el-descriptions-item label="成立时间">{{ profileData.enterprise.established_date || '-' }}</el-descriptions-item>
              <el-descriptions-item label="公司位置">{{ profileData.enterprise.location || '-' }}</el-descriptions-item>
              <el-descriptions-item label="人员规模">{{ profileData.enterprise.personnel_size || '-' }}</el-descriptions-item>
              <el-descriptions-item label="注册资本">{{ profileData.enterprise.registered_capital || '-' }}</el-descriptions-item>
              <el-descriptions-item label="单位网址">{{ profileData.enterprise.website || '-' }}</el-descriptions-item>
              <el-descriptions-item label="关系状态">
                <el-tag size="small">{{ profileData.enterprise.relationship_status || '未接触' }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="联系人">{{ profileData.enterprise.contact_person || '-' }}</el-descriptions-item>
              <el-descriptions-item label="联系方式">{{ profileData.enterprise.contact_info || '-' }}</el-descriptions-item>
              <el-descriptions-item label="单位简介" :span="3">{{ profileData.enterprise.brief || '-' }}</el-descriptions-item>
              <el-descriptions-item label="业务范围" :span="3">{{ profileData.enterprise.business_scope || '-' }}</el-descriptions-item>
              <el-descriptions-item label="主要资质" :span="3">{{ profileData.enterprise.main_qualifications || '-' }}</el-descriptions-item>
              <el-descriptions-item label="主要产品和方案" :span="3">{{ profileData.enterprise.main_products || '-' }}</el-descriptions-item>
              <el-descriptions-item label="合作机会点" :span="3">{{ profileData.enterprise.cooperation_opportunities || '-' }}</el-descriptions-item>
            </el-descriptions>
          </el-card>

          <el-card class="profile-section">
            <template #header><span class="section-title">🕒 全生命周期轨迹</span></template>
            <el-timeline v-if="timelineEvents.length > 0">
              <el-timeline-item
                v-for="(evt, idx) in timelineEvents"
                :key="idx"
                :timestamp="evt.time"
                placement="top"
                :type="evt.color"
                :hollow="evt.hollow"
              >
                <el-card shadow="hover" class="event-card">
                  <div class="event-header">
                    <el-tag :type="evt.color" size="small" effect="dark">{{ evt.typeLabel }}</el-tag>
                    <el-tag v-if="evt.badge" :type="evt.badge.type" size="small" effect="plain">{{ evt.badge.text }}</el-tag>
                    <span class="event-title">{{ evt.title }}</span>
                  </div>
                  <div class="event-desc" v-if="evt.desc">{{ evt.desc }}</div>
                  <div class="event-meta" v-if="evt.meta">{{ evt.meta }}</div>
                </el-card>
              </el-timeline-item>
            </el-timeline>
            <el-empty v-else description="暂无生命周期事件" />
          </el-card>
        </template>
      </div>
    </el-drawer>

    <!-- 客户分析对话框 -->
    <el-dialog
      v-model="showAnalysis"
      title="客户数据分析"
      width="90%"
      top="5vh"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <div v-loading="analysisLoading">
        <template v-if="analysisData">
          <div class="analysis-summary">
            <el-card class="summary-card">
              <div class="summary-val">{{ analysisData.total }}</div>
              <div class="summary-lbl">客户总数</div>
            </el-card>
            <el-card class="summary-card" v-for="(s, idx) in analysisData.conversion_funnel.slice(1)" :key="idx">
              <div class="summary-val">{{ s.count }}</div>
              <div class="summary-lbl">{{ s.stage }}</div>
            </el-card>
          </div>

          <el-row :gutter="16">
            <el-col :span="12">
              <el-card class="chart-card">
                <template #header><span class="chart-title">客户等级分布</span></template>
                <div ref="levelChartRef" class="chart-box"></div>
              </el-card>
            </el-col>
            <el-col :span="12">
              <el-card class="chart-card">
                <template #header><span class="chart-title">客户行业分布</span></template>
                <div ref="industryChartRef" class="chart-box"></div>
              </el-card>
            </el-col>
          </el-row>
          <el-row :gutter="16" style="margin-top: 16px;">
            <el-col :span="12">
              <el-card class="chart-card">
                <template #header><span class="chart-title">客户来源分布</span></template>
                <div ref="sourceChartRef" class="chart-box"></div>
              </el-card>
            </el-col>
            <el-col :span="12">
              <el-card class="chart-card">
                <template #header><span class="chart-title">客户地区分布 (Top 10)</span></template>
                <div ref="regionChartRef" class="chart-box"></div>
              </el-card>
            </el-col>
          </el-row>
          <el-row :gutter="16" style="margin-top: 16px;">
            <el-col :span="12">
              <el-card class="chart-card">
                <template #header><span class="chart-title">客户转化漏斗</span></template>
                <div ref="funnelChartRef" class="chart-box"></div>
              </el-card>
            </el-col>
            <el-col :span="12" v-if="isAdmin && analysisData.owner_ranking.length > 0">
              <el-card class="chart-card">
                <template #header><span class="chart-title">负责人业绩排行</span></template>
                <el-table :data="analysisData.owner_ranking" size="small" border height="320">
                  <el-table-column type="index" label="排名" width="60" />
                  <el-table-column prop="owner_name" label="负责人" min-width="90" />
                  <el-table-column prop="customer_count" label="客户数" width="70" sortable />
                  <el-table-column prop="business_count" label="商机数" width="70" sortable />
                  <el-table-column prop="contract_count" label="合同数" width="70" sortable />
                  <el-table-column label="合同总额(万)" width="110" sortable :sort-method="(a,b)=>(a.total_amount||0)-(b.total_amount||0)">
                    <template #default="{ row }">
                      ¥{{ ((row.total_amount || 0) / 10000).toFixed(2) }}
                    </template>
                  </el-table-column>
                </el-table>
              </el-card>
            </el-col>
          </el-row>
        </template>
      </div>
      <template #footer>
        <el-button @click="showAnalysis = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { Plus, DataAnalysis } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import api from '../api'
import { useAuthStore } from '../stores/auth'
import { useRouter } from 'vue-router'

const authStore = useAuthStore()
const router = useRouter()
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

// 筛选条件
const filterLevel = ref('')
const filterIndustry = ref('')
const filterSource = ref('')
const sourceOptions = ref(['主动开发', '客户介绍', '展会', '网络推广', '电话营销', '其它'])

// 客户分析
const showAnalysis = ref(false)
const analysisLoading = ref(false)
const analysisData = ref(null)

// 画像相关状态
const showProfileDrawer = ref(false)
const profileLoading = ref(false)
const profileData = ref(null)

const filteredCustomers = computed(() => {
  if (!searchKeyword.value) return customers.value
  const keyword = searchKeyword.value.toLowerCase()
  return customers.value.filter(c => 
    (c.name && c.name.toLowerCase().includes(keyword)) ||
    (c.company && c.company.toLowerCase().includes(keyword)) ||
    (c.phone && c.phone.toLowerCase().includes(keyword))
  )
})

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
  contact_name: '',
  email: '',
  industry: '',
  region: '',
  address: '',
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
  const params = {}
  if (searchKeyword.value) params.keyword = searchKeyword.value
  if (filterLevel.value) params.level = filterLevel.value
  if (filterIndustry.value) params.industry = filterIndustry.value
  if (filterSource.value) params.source = filterSource.value
  const response = await api.get('/customers', params)
  if (response.code === 200) {
    customers.value = response.data
  }
}

const handleSearch = () => {
  fetchCustomers()
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

// 金额格式化：元 → 万元，精确到分需保留4位小数（0.0001万元 = 0.01元）
const formatAmount = (value) => {
  return ((value || 0) / 10000).toFixed(4)
}

// 打开画像 Drawer
const showProfile = async (row) => {
  showProfileDrawer.value = true
  profileLoading.value = true
  profileData.value = null
  try {
    const response = await api.get(`/customers/${row.id}/profile`)
    if (response.code === 200) {
      profileData.value = response.data
    } else {
      ElMessage.error(response.message)
      showProfileDrawer.value = false
    }
  } catch (error) {
    ElMessage.error('加载画像失败')
    showProfileDrawer.value = false
  } finally {
    profileLoading.value = false
  }
}

// 跳转到企业信息库
const goToEnterprise = () => {
  if (profileData.value?.enterprise?.id) {
    showProfileDrawer.value = false
    router.push('/enterprises')
  } else {
    router.push('/enterprises')
  }
}

// 全生命周期时间轴事件合并
const timelineEvents = computed(() => {
  if (!profileData.value) return []
  const events = []
  const d = profileData.value

  // 跟进记录
  d.follow_logs.forEach(log => {
    events.push({
      time: log.log_time || log.created_at,
      typeLabel: '跟进',
      color: 'primary',
      hollow: false,
      title: log.subject || '(无主题)',
      desc: log.content,
      meta: [log.user_name && `跟进人: ${log.user_name}`,
             log.participants && `参与人: ${log.participants}`,
             log.location && `地点: ${log.location}`,
             log.next_plan && `下次计划: ${log.next_plan}`]
            .filter(Boolean).join('  |  ')
    })
  })

  // 商机（标注是否已签出合同，体现 商机→合同 关系链）
  d.business.forEach(b => {
    const linkedContracts = d.contracts.filter(c => c.b_id === b.id)
    const contractInfo = linkedContracts.length > 0
      ? `已签合同: ${linkedContracts.map(c => c.contract_name || c.contract_no).join('、')}`
      : ''
    events.push({
      time: b.created_at,
      typeLabel: '商机',
      color: 'warning',
      hollow: false,
      title: b.title,
      desc: `阶段: ${b.stage || '-'}  |  金额: ¥${formatAmount(b.amount)}万  |  概率: ${b.probability || 0}%`,
      meta: [b.owner_name && `负责人: ${b.owner_name}`,
             b.predict_date && `预计成交: ${b.predict_date}`,
             contractInfo,
             b.status === 'void' && '已作废']
            .filter(Boolean).join('  |  ')
    })
  })

  // 合同（linkage: precise=精确关联本客户；fuzzy=仅按公司名匹配，待精确关联；other=其它）
  d.contracts.forEach(c => {
    const linkage = c.linkage || 'other'
    const linkageLabel = linkage === 'fuzzy' ? '待精确关联' : (linkage === 'precise' ? '已关联客户' : '')
    events.push({
      time: c.sign_date,
      typeLabel: '合同',
      color: 'success',
      hollow: false,
      title: c.contract_name || c.contract_no,
      desc: `金额: ¥${formatAmount(c.total_amt)}万  |  状态: ${c.status || '-'}`,
      badge: linkage === 'fuzzy' ? { text: '待关联', type: 'warning' } : (linkage === 'precise' ? { text: '已关联', type: 'success' } : null),
      meta: [c.contract_no && `编号: ${c.contract_no}`,
             c.customer_name && `客户: ${c.customer_name}`,
             c.business_title && `源自商机: ${c.business_title}`,
             linkageLabel && `关联: ${linkageLabel}`,
             c.owner_name && `负责人: ${c.owner_name}`]
            .filter(Boolean).join('  |  ')
    })
  })

  // 拜访
  d.visits.forEach(v => {
    const visitTime = v.actual_date || v.plan_date
    events.push({
      time: visitTime + (v.actual_time || v.plan_time ? ' ' + (v.actual_time || v.plan_time) : ''),
      typeLabel: v.status === 'completed' ? '拜访(完成)' : (v.status === 'cancelled' ? '拜访(取消)' : '拜访(计划)'),
      color: v.status === 'completed' ? 'success' : (v.status === 'cancelled' ? 'info' : 'primary'),
      hollow: v.status !== 'completed',
      title: v.purpose || '(无拜访目的)',
      desc: v.result || v.notes || '',
      meta: [v.visitor_name && `拜访人: ${v.visitor_name}`,
             v.location && `地点: ${v.location}`,
             v.contact_person && `客户方: ${v.contact_person}`]
            .filter(Boolean).join('  |  ')
    })
  })

  // 按时间倒序
  events.sort((a, b) => {
    const ta = a.time || ''
    const tb = b.time || ''
    return tb.localeCompare(ta)
  })

  return events
})

// ===== 客户分析 =====
const levelChartRef = ref(null)
const industryChartRef = ref(null)
const sourceChartRef = ref(null)
const regionChartRef = ref(null)
const funnelChartRef = ref(null)
let levelChartInstance = null
let industryChartInstance = null
let sourceChartInstance = null
let regionChartInstance = null
let funnelChartInstance = null

const isAdmin = computed(() => authStore.role === '主任' || authStore.role === '院长')

const fetchAnalysis = async () => {
  analysisLoading.value = true
  analysisData.value = null
  try {
    const response = await api.get('/customers/analysis')
    if (response.code === 200) {
      analysisData.value = response.data
      await nextTick()
      initAnalysisCharts()
      updateAnalysisCharts()
    } else {
      ElMessage.error(response.message)
    }
  } catch (error) {
    ElMessage.error('加载客户分析失败')
  } finally {
    analysisLoading.value = false
  }
}

const initAnalysisCharts = () => {
  if (levelChartRef.value) levelChartInstance = echarts.init(levelChartRef.value)
  if (industryChartRef.value) industryChartInstance = echarts.init(industryChartRef.value)
  if (sourceChartRef.value) sourceChartInstance = echarts.init(sourceChartRef.value)
  if (regionChartRef.value) regionChartInstance = echarts.init(regionChartRef.value)
  if (funnelChartRef.value) funnelChartInstance = echarts.init(funnelChartRef.value)
}

const updateAnalysisCharts = () => {
  if (!analysisData.value) return
  const d = analysisData.value

  // 等级分布 - 饼图
  if (levelChartInstance) {
    levelChartInstance.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { bottom: 0 },
      series: [{
        name: '等级分布',
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['50%', '45%'],
        label: { formatter: '{b}\n{c}' },
        data: d.level_distribution.map(item => ({
          name: item.level,
          value: item.count,
          itemStyle: {
            color: item.level === 'A' ? '#ee6666' : (item.level === 'B' ? '#fac858' : '#91cc75')
          }
        }))
      }]
    })
  }

  // 行业分布 - 柱状图
  if (industryChartInstance) {
    industryChartInstance.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: d.industry_distribution.map(i => i.industry), axisLabel: { rotate: 30 } },
      yAxis: { type: 'value' },
      series: [{ type: 'bar', data: d.industry_distribution.map(i => i.count), itemStyle: { color: '#5470c6' } }]
    })
  }

  // 来源分布 - 饼图
  if (sourceChartInstance) {
    sourceChartInstance.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { bottom: 0 },
      series: [{
        name: '来源分布',
        type: 'pie',
        radius: '65%',
        center: ['50%', '45%'],
        label: { formatter: '{b}: {c}' },
        data: d.source_distribution.map(item => ({ name: item.source, value: item.count }))
      }]
    })
  }

  // 地区分布 - 柱状图
  if (regionChartInstance) {
    regionChartInstance.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: d.region_distribution.map(i => i.region), axisLabel: { rotate: 30 } },
      yAxis: { type: 'value' },
      series: [{ type: 'bar', data: d.region_distribution.map(i => i.count), itemStyle: { color: '#73c0de' } }]
    })
  }

  // 转化漏斗
  if (funnelChartInstance) {
    const stages = d.conversion_funnel
    const maxVal = stages.length > 0 ? Math.max(...stages.map(s => s.count)) : 100
    funnelChartInstance.setOption({
      tooltip: { trigger: 'item', formatter: (p) => {
        const stage = stages[p.dataIndex] || {}
        const rate = maxVal > 0 ? ((stage.count / stages[0].count) * 100).toFixed(1) : 0
        return `${stage.stage}<br/>数量: ${stage.count}<br/>相对首阶段: ${rate}%`
      }},
      series: [{
        name: '客户转化漏斗',
        type: 'funnel',
        left: '10%',
        top: 10,
        bottom: 10,
        width: '80%',
        min: 0,
        max: maxVal,
        minSize: '20%',
        maxSize: '100%',
        sort: 'descending',
        gap: 2,
        label: { show: true, position: 'inside', formatter: (p) => {
          const stage = stages[p.dataIndex] || {}
          return `${stage.stage}\n${stage.count}`
        }},
        itemStyle: { borderColor: '#fff', borderWidth: 1 },
        data: stages.map((s, i) => ({
          value: s.count,
          name: s.stage,
          itemStyle: { color: ['#5470c6', '#91cc75', '#fac858', '#ee6666'][i] || '#73c0de' }
        }))
      }]
    })
  }
}

const handleAnalysisResize = () => {
  levelChartInstance?.resize()
  industryChartInstance?.resize()
  sourceChartInstance?.resize()
  regionChartInstance?.resize()
  funnelChartInstance?.resize()
}

watch(showAnalysis, async (val) => {
  if (val) {
    await fetchAnalysis()
  } else {
    // 关闭时销毁图表实例，避免重复初始化
    levelChartInstance?.dispose(); levelChartInstance = null
    industryChartInstance?.dispose(); industryChartInstance = null
    sourceChartInstance?.dispose(); sourceChartInstance = null
    regionChartInstance?.dispose(); regionChartInstance = null
    funnelChartInstance?.dispose(); funnelChartInstance = null
  }
})

onMounted(() => {
  fetchCustomers()
  fetchUsers()
  window.addEventListener('resize', handleAnalysisResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleAnalysisResize)
  levelChartInstance?.dispose()
  industryChartInstance?.dispose()
  sourceChartInstance?.dispose()
  regionChartInstance?.dispose()
  funnelChartInstance?.dispose()
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

.profile-container {
  padding: 0 16px 16px;
}

.profile-section {
  margin-bottom: 16px;
}

.section-title {
  font-weight: 600;
  color: #334155;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.stat-mini {
  text-align: center;
}

.stat-val {
  font-size: 20px;
  font-weight: 700;
  color: #4ecdc4;
}

.stat-lbl {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 4px;
}

.event-card {
  margin-bottom: 0;
}

.event-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.event-title {
  font-weight: 600;
  color: #334155;
}

.event-desc {
  color: #64748b;
  font-size: 13px;
  margin-bottom: 4px;
}

.event-meta {
  font-size: 12px;
  color: #94a3b8;
}

.analysis-summary {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.summary-card {
  flex: 1;
  min-width: 120px;
  text-align: center;
}

.summary-val {
  font-size: 24px;
  font-weight: 700;
  color: #4ecdc4;
}

.summary-lbl {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 4px;
}

.chart-card {
  margin-bottom: 0;
}

.chart-title {
  font-weight: 600;
  color: #334155;
}

.chart-box {
  width: 100%;
  height: 320px;
}
</style>