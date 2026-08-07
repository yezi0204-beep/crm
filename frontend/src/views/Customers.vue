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
  contact_name: '',
  email: '',
  industry: '',
  region: '',
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
</style>