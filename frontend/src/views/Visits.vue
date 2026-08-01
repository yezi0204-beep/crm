<template>
  <div class="visits-container">
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">📅 客户拜访排班</h2>
      </div>
      <div class="header-right">
        <el-button-group>
          <el-button 
            :type="viewMode === 'calendar' ? 'primary' : ''" 
            @click="viewMode = 'calendar'"
          >
            📆 日历视图
          </el-button>
          <el-button 
            :type="viewMode === 'list' ? 'primary' : ''" 
            @click="viewMode = 'list'"
          >
            📋 列表视图
          </el-button>
          <el-button 
            :type="viewMode === 'personnel' ? 'primary' : ''" 
            @click="viewMode = 'personnel'"
          >
            👥 人员排班
          </el-button>
        </el-button-group>
        <el-button type="primary" @click="openAddDialog">+ 新增排班</el-button>
      </div>
    </div>

    <div class="stats-section">
      <div class="stat-card">
        <div class="stat-icon total">📅</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.total || 0 }}</div>
          <div class="stat-label">本月总拜访</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon planned">⏰</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.planned || 0 }}</div>
          <div class="stat-label">待拜访</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon completed">✅</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.completed || 0 }}</div>
          <div class="stat-label">已完成</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon cancelled">❌</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.cancelled || 0 }}</div>
          <div class="stat-label">已取消</div>
        </div>
      </div>
    </div>

    <div class="filter-section">
      <el-date-picker
        v-model="filterDateRange"
        type="daterange"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        @change="fetchVisits"
      />
      <el-select v-model="filterStatus" placeholder="状态" clearable @change="fetchVisits">
        <el-option label="待完成" value="planned" />
        <el-option label="已完成" value="completed" />
        <el-option label="已取消" value="cancelled" />
      </el-select>
      <el-select v-model="filterVisitorId" placeholder="人员" clearable @change="fetchVisits">
        <el-option 
          v-for="user in userList" 
          :key="user.username" 
          :label="user.name" 
          :value="user.username"
        />
      </el-select>
      <el-select v-model="filterWorkType" placeholder="类型" clearable @change="fetchVisits">
        <el-option label="客户拜访" value="visit" />
        <el-option label="其它工作" value="other" />
      </el-select>
      <el-input 
        v-model="searchKeyword" 
        placeholder="搜索客户/目的" 
        clearable
        @keyup.enter="fetchVisits"
        style="width: 200px;"
      />
      <el-button type="primary" @click="fetchVisits">搜索</el-button>
    </div>

    <div v-if="viewMode === 'calendar'" class="calendar-view">
      <el-calendar v-model="currentDate">
        <template #date-cell="{ data }">
          <div class="calendar-cell" :class="getCellClass(data)">
            <div class="date-number">{{ data.day.split('-').slice(-1)[0] }}</div>
            <div class="day-visits">
              <div 
                v-for="visit in getDayVisits(data.day)" 
                :key="visit.id" 
                class="visit-tag"
                :class="[visit.status, { 'other-work': visit.work_type === 'other' }]"
                @click="openDetailDialog(visit)"
              >
                {{ visit.plan_time }} {{ visit.work_type === 'other' ? (visit.work_content || '其它工作') : (visit.customer_name || visit.customer_company || visit.purpose) }}
              </div>
            </div>
          </div>
        </template>
      </el-calendar>
    </div>

    <div v-else-if="viewMode === 'list'" class="list-view">
      <div class="table-container">
        <div class="table-wrapper">
          <el-table :data="pagedVisits" stripe style="width: 100%">
            <el-table-column prop="plan_date" label="计划日期" min-width="100" sortable>
              <template #default="{ row }">
                {{ formatDate(row.plan_date) }}
              </template>
            </el-table-column>
            <el-table-column prop="plan_time" label="时间" min-width="70">
              <template #default="{ row }">
                {{ row.plan_time || '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="work_type" label="类型" min-width="90">
              <template #default="{ row }">
                <el-tag :type="row.work_type === 'visit' ? 'primary' : 'success'" effect="plain">
                  {{ row.work_type === 'visit' ? '客户拜访' : '其它工作' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="customer_name" label="客户名称" min-width="140" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.work_type === 'other' ? '-' : (row.customer_name || '-') }}
              </template>
            </el-table-column>
            <el-table-column prop="customer_company" label="公司" min-width="140" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.work_type === 'other' ? '-' : (row.customer_company || '-') }}
              </template>
            </el-table-column>
            <el-table-column prop="purpose" label="内容" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.work_type === 'other' ? (row.work_content || '-') : (row.purpose || '-') }}
              </template>
            </el-table-column>
            <el-table-column prop="visitor_name" label="执行人" min-width="90">
              <template #default="{ row }">
                {{ row.visitor_name || row.visitor_id }}
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" min-width="90">
              <template #default="{ row }">
                <el-tag :type="getStatusType(row.status)" effect="dark">
                  {{ getStatusText(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="240" fixed="right">
              <template #default="{ row }">
                <el-button 
                  v-if="row.status === 'planned'" 
                  type="success" 
                  size="small" 
                  @click="openCompleteDialog(row)"
                >
                  完成
                </el-button>
                <el-button type="primary" size="small" @click="openDetailDialog(row)">详情</el-button>
                <el-button 
                  v-if="row.status === 'planned'" 
                  size="small" 
                  @click="openEditDialog(row)"
                >
                  编辑
                </el-button>
                <el-button 
                  v-if="row.status === 'planned'" 
                  type="warning" 
                  size="small" 
                  @click="handleCancel(row)"
                >
                  取消
                </el-button>
                <el-button 
                  type="danger" 
                  size="small" 
                  @click="handleDelete(row)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <div class="pagination-wrapper">
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :page-sizes="[10, 20, 50]"
            :total="filteredVisits.length"
            layout="total, sizes, prev, pager, next, jumper"
            background
          />
        </div>
      </div>
    </div>

    <div v-else-if="viewMode === 'personnel'" class="personnel-view">
      <el-tabs v-model="activePersonnelTab" type="border-card">
        <el-tab-pane v-for="user in userList" :key="user.username" :label="user.name" :name="user.username">
          <div class="personnel-schedule">
            <el-table :data="getUserVisits(user.username)" stripe style="width: 100%">
              <el-table-column prop="plan_date" label="计划日期" min-width="100" sortable>
                <template #default="{ row }">
                  {{ formatDate(row.plan_date) }}
                </template>
              </el-table-column>
              <el-table-column prop="plan_time" label="时间" min-width="70">
                <template #default="{ row }">
                  {{ row.plan_time || '-' }}
                </template>
              </el-table-column>
              <el-table-column prop="work_type" label="类型" min-width="100">
                <template #default="{ row }">
                  <el-tag :type="row.work_type === 'visit' ? 'primary' : 'success'" effect="plain">
                    {{ row.work_type === 'visit' ? '客户拜访' : '其它工作' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="内容" min-width="200" show-overflow-tooltip>
                <template #default="{ row }">
                  <div v-if="row.work_type === 'visit'">
                    <div>{{ row.purpose || '-' }}</div>
                    <div class="sub-info" v-if="row.customer_name">{{ row.customer_name }} ({{ row.customer_company }})</div>
                  </div>
                  <div v-else>
                    {{ row.work_content || '-' }}
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="location" label="地点" min-width="100" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ row.location || '-' }}
                </template>
              </el-table-column>
              <el-table-column prop="status" label="状态" min-width="90">
                <template #default="{ row }">
                  <el-tag :type="getStatusType(row.status)" effect="dark">
                    {{ getStatusText(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="180" fixed="right">
                <template #default="{ row }">
                  <el-button 
                    v-if="row.status === 'planned'" 
                    type="success" 
                    size="small" 
                    @click="openCompleteDialog(row)"
                  >
                    完成
                  </el-button>
                  <el-button 
                    v-if="row.status === 'planned'" 
                    size="small" 
                    @click="openEditDialog(row)"
                  >
                    编辑
                  </el-button>
                  <el-button 
                    v-if="row.status === 'planned'" 
                    type="warning" 
                    size="small" 
                    @click="handleCancel(row)"
                  >
                    取消
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="getUserVisits(user.username).length === 0" description="暂无排班" />
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <el-dialog v-model="addDialogVisible" title="新增排班计划" width="600px">
      <el-form :model="visitForm" label-width="100px" ref="visitFormRef" :rules="formRules">
        <el-form-item label="类型" prop="work_type">
          <el-radio-group v-model="visitForm.work_type">
            <el-radio value="visit">客户拜访</el-radio>
            <el-radio value="other">其它工作</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="visitForm.work_type === 'visit'" label="客户" prop="cust_id">
          <el-select v-model="visitForm.cust_id" placeholder="选择客户" filterable>
            <el-option 
              v-for="customer in customerList" 
              :key="customer.id" 
              :label="`${customer.name} (${customer.company})`" 
              :value="customer.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-else label="工作内容" prop="work_content">
          <el-input v-model="visitForm.work_content" type="textarea" :rows="3" placeholder="请输入工作内容" />
        </el-form-item>
        <el-form-item label="执行人" prop="visitor_id">
          <el-select v-model="visitForm.visitor_id" placeholder="选择执行人">
            <el-option 
              v-for="user in userList" 
              :key="user.username" 
              :label="user.name" 
              :value="user.username"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="计划日期" prop="plan_date">
          <el-date-picker 
            v-model="visitForm.plan_date" 
            type="date" 
            placeholder="选择日期"
            value-format="YYYY-MM-DD"
          />
        </el-form-item>
        <el-form-item label="计划时间" prop="plan_time">
          <el-time-picker 
            v-model="visitForm.plan_time" 
            placeholder="选择时间"
            value-format="HH:mm"
          />
        </el-form-item>
        <el-form-item v-if="visitForm.work_type === 'visit'" label="拜访目的" prop="purpose">
          <el-input v-model="visitForm.purpose" placeholder="请输入拜访目的" />
        </el-form-item>
        <el-form-item label="地点">
          <el-input v-model="visitForm.location" :placeholder="visitForm.work_type === 'visit' ? '请输入拜访地点' : '请输入工作地点'" />
        </el-form-item>
        <el-form-item v-if="visitForm.work_type === 'visit'" label="联系人">
          <el-input v-model="visitForm.contact_person" placeholder="请输入联系人" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="visitForm.notes" type="textarea" :rows="2" placeholder="备注信息" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailDialogVisible" title="排班详情" width="600px">
      <el-descriptions :column="2" border v-if="currentVisit">
        <el-descriptions-item label="类型">
          <el-tag :type="currentVisit.work_type === 'visit' ? 'primary' : 'success'" effect="plain">
            {{ currentVisit.work_type === 'visit' ? '客户拜访' : '其它工作' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="执行人">
          {{ currentVisit.visitor_name || currentVisit.visitor_id }}
        </el-descriptions-item>
        <el-descriptions-item v-if="currentVisit.work_type === 'visit'" label="客户">
          {{ currentVisit.customer_name }} ({{ currentVisit.customer_company }})
        </el-descriptions-item>
        <el-descriptions-item label="计划日期">
          {{ formatDate(currentVisit.plan_date) }}
        </el-descriptions-item>
        <el-descriptions-item label="计划时间">
          {{ currentVisit.plan_time || '-' }}
        </el-descriptions-item>
        <el-descriptions-item v-if="currentVisit.work_type === 'visit'" label="拜访目的" :span="2">
          {{ currentVisit.purpose || '-' }}
        </el-descriptions-item>
        <el-descriptions-item v-else label="工作内容" :span="2">
          {{ currentVisit.work_content || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="地点">
          {{ currentVisit.location || '-' }}
        </el-descriptions-item>
        <el-descriptions-item v-if="currentVisit.work_type === 'visit'" label="联系人">
          {{ currentVisit.contact_person || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getStatusType(currentVisit.status)">
            {{ getStatusText(currentVisit.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="创建时间">
          {{ currentVisit.created_at }}
        </el-descriptions-item>
        <el-descriptions-item label="实际日期" v-if="currentVisit.actual_date">
          {{ formatDate(currentVisit.actual_date) }}
        </el-descriptions-item>
        <el-descriptions-item label="实际时间" v-if="currentVisit.actual_time">
          {{ currentVisit.actual_time }}
        </el-descriptions-item>
        <el-descriptions-item label="完成结果" v-if="currentVisit.result" :span="2">
          {{ currentVisit.result }}
        </el-descriptions-item>
        <el-descriptions-item label="备注" v-if="currentVisit.notes" :span="2">
          {{ currentVisit.notes }}
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button v-if="currentVisit?.status === 'planned'" type="success" @click="openCompleteDialog(currentVisit)">
          完成拜访
        </el-button>
        <el-button v-if="currentVisit?.status === 'planned'" @click="openEditDialog(currentVisit)">
          编辑
        </el-button>
        <el-button @click="detailDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="completeDialogVisible" title="完成排班" width="500px">
      <el-form :model="completeForm" label-width="100px">
        <el-form-item label="实际日期">
          <el-date-picker 
            v-model="completeForm.actual_date" 
            type="date" 
            placeholder="选择日期"
            value-format="YYYY-MM-DD"
          />
        </el-form-item>
        <el-form-item label="实际时间">
          <el-time-picker 
            v-model="completeForm.actual_time" 
            placeholder="选择时间"
            value-format="HH:mm"
          />
        </el-form-item>
        <el-form-item :label="currentVisit?.work_type === 'visit' ? '拜访结果' : '完成情况'">
          <el-input 
            v-model="completeForm.result" 
            type="textarea" 
            :rows="4" 
            :placeholder="currentVisit?.work_type === 'visit' ? '请输入拜访结果' : '请输入工作完成情况'"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="completeDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleComplete">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { useAuthStore } from '../stores/auth'
import { ElMessage, ElMessageBox } from 'element-plus'

const authStore = useAuthStore()
const token = computed(() => authStore.token)

const viewMode = ref('calendar')
const currentDate = ref(new Date())
const visits = ref([])
const stats = ref({})
const customerList = ref([])
const userList = ref([])

const filterDateRange = ref([])
const filterStatus = ref('')
const filterVisitorId = ref('')
const filterWorkType = ref('')
const searchKeyword = ref('')

const currentPage = ref(1)
const pageSize = ref(10)

const addDialogVisible = ref(false)
const detailDialogVisible = ref(false)
const completeDialogVisible = ref(false)
const visitFormRef = ref(null)

const activePersonnelTab = ref('')

const visitForm = reactive({
  id: null,
  work_type: 'visit',
  cust_id: null,
  work_content: '',
  visitor_id: authStore.username,
  plan_date: '',
  plan_time: '',
  purpose: '',
  location: '',
  contact_person: '',
  notes: ''
})

const completeForm = reactive({
  actual_date: new Date().toISOString().split('T')[0],
  actual_time: new Date().toTimeString().slice(0, 5),
  result: ''
})

const currentVisit = ref(null)

const validateCustId = (rule, value, callback) => {
  if (visitForm.work_type === 'visit' && !value) {
    callback(new Error('请选择客户'))
  } else {
    callback()
  }
}

const validateWorkContent = (rule, value, callback) => {
  if (visitForm.work_type === 'other' && !value) {
    callback(new Error('请输入工作内容'))
  } else {
    callback()
  }
}

const validatePurpose = (rule, value, callback) => {
  if (visitForm.work_type === 'visit' && !value) {
    callback(new Error('请输入拜访目的'))
  } else {
    callback()
  }
}

const formRules = {
  work_type: [{ required: true, message: '请选择类型', trigger: 'change' }],
  cust_id: [{ validator: validateCustId, trigger: 'change' }],
  work_content: [{ validator: validateWorkContent, trigger: 'blur' }],
  visitor_id: [{ required: true, message: '请选择执行人', trigger: 'change' }],
  plan_date: [{ required: true, message: '请选择计划日期', trigger: 'change' }],
  purpose: [{ validator: validatePurpose, trigger: 'blur' }]
}

const filteredVisits = computed(() => {
  let result = [...visits.value]
  
  if (filterStatus.value) {
    result = result.filter(v => v.status === filterStatus.value)
  }
  
  if (filterVisitorId.value) {
    result = result.filter(v => v.visitor_id === filterVisitorId.value)
  }
  
  if (filterWorkType.value) {
    result = result.filter(v => v.work_type === filterWorkType.value)
  }
  
  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase()
    result = result.filter(v => 
      (v.customer_name && v.customer_name.toLowerCase().includes(keyword)) ||
      (v.customer_company && v.customer_company.toLowerCase().includes(keyword)) ||
      (v.purpose && v.purpose.toLowerCase().includes(keyword)) ||
      (v.work_content && v.work_content.toLowerCase().includes(keyword))
    )
  }
  
  if (filterDateRange.value && filterDateRange.value.length === 2) {
    const [start, end] = filterDateRange.value
    result = result.filter(v => v.plan_date >= start && v.plan_date <= end)
  }
  
  return result
})

const getUserVisits = (username) => {
  return filteredVisits.value.filter(v => v.visitor_id === username)
}

const pagedVisits = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredVisits.value.slice(start, start + pageSize.value)
})

const getDayVisits = (day) => {
  return visits.value.filter(v => v.plan_date === day)
}

const getCellClass = (data) => {
  const hasVisit = visits.value.some(v => v.plan_date === data.day)
  return hasVisit ? 'has-visit' : ''
}

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return dateStr
}

const getStatusType = (status) => {
  const map = {
    'planned': 'warning',
    'completed': 'success',
    'cancelled': 'info'
  }
  return map[status] || ''
}

const getStatusText = (status) => {
  const map = {
    'planned': '待完成',
    'completed': '已完成',
    'cancelled': '已取消'
  }
  return map[status] || status
}

const fetchVisits = async () => {
  try {
    const params = new URLSearchParams()
    if (filterStatus.value) params.append('status', filterStatus.value)
    if (filterVisitorId.value) params.append('visitor_id', filterVisitorId.value)
    
    const res = await fetch(`/api/visits?${params.toString()}`, {
      headers: { 'Authorization': `Bearer ${token.value}` }
    })
    const data = await res.json()
    if (data.code === 200) {
      visits.value = data.data.map(v => ({
        ...v,
        work_type: v.work_type || 'visit',
        work_content: v.work_content || ''
      }))
    }
  } catch (error) {
    ElMessage.error('获取排班记录失败')
  }
}

const fetchStats = async () => {
  try {
    const res = await fetch('/api/visits/stats/summary', {
      headers: { 'Authorization': `Bearer ${token.value}` }
    })
    const data = await res.json()
    if (data.code === 200) {
      stats.value = data.data
    }
  } catch (error) {
    console.error('获取统计数据失败:', error)
  }
}

const fetchCustomers = async () => {
  try {
    const res = await fetch('/api/customers', {
      headers: { 'Authorization': `Bearer ${token.value}` }
    })
    const data = await res.json()
    if (data.code === 200) {
      customerList.value = data.data
    }
  } catch (error) {
    console.error('获取客户列表失败:', error)
  }
}

const fetchUsers = async () => {
  try {
    const res = await fetch('/api/users?role=销售', {
      headers: { 'Authorization': `Bearer ${token.value}` }
    })
    const data = await res.json()
    if (data.code === 200) {
      userList.value = data.data
    }
  } catch (error) {
    console.error('获取用户列表失败:', error)
  }
}

const openAddDialog = () => {
  Object.assign(visitForm, {
    id: null,
    work_type: 'visit',
    cust_id: null,
    work_content: '',
    visitor_id: authStore.username,
    plan_date: new Date().toISOString().split('T')[0],
    plan_time: '09:00',
    purpose: '',
    location: '',
    contact_person: '',
    notes: ''
  })
  addDialogVisible.value = true
}

const openDetailDialog = (visit) => {
  currentVisit.value = visit
  detailDialogVisible.value = true
}

const openEditDialog = (visit) => {
  Object.assign(visitForm, {
    id: visit.id,
    work_type: visit.work_type || 'visit',
    cust_id: visit.cust_id,
    work_content: visit.work_content || '',
    visitor_id: visit.visitor_id,
    plan_date: visit.plan_date,
    plan_time: visit.plan_time,
    purpose: visit.purpose,
    location: visit.location,
    contact_person: visit.contact_person,
    notes: visit.notes
  })
  addDialogVisible.value = true
  detailDialogVisible.value = false
}

const openCompleteDialog = (visit) => {
  currentVisit.value = visit
  completeForm.actual_date = new Date().toISOString().split('T')[0]
  completeForm.actual_time = new Date().toTimeString().slice(0, 5)
  completeForm.result = ''
  completeDialogVisible.value = true
}

const handleSave = async () => {
  if (!visitFormRef.value) return
  
  try {
    await visitFormRef.value.validate()
  } catch {
    return
  }
  
  try {
    const url = visitForm.id 
      ? `/api/visits/${visitForm.id}` 
      : '/api/visits'
    const method = visitForm.id ? 'PUT' : 'POST'
    
    const res = await fetch(url, {
      method,
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token.value}` 
      },
      body: JSON.stringify(visitForm)
    })
    const data = await res.json()
    if (data.code === 200) {
      ElMessage.success(data.message)
      addDialogVisible.value = false
      fetchVisits()
      fetchStats()
    } else {
      ElMessage.error(data.message)
    }
  } catch (error) {
    ElMessage.error('保存失败')
  }
}

const handleComplete = async () => {
  if (!currentVisit.value) return
  
  try {
    const res = await fetch(`/api/visits/${currentVisit.value.id}/complete`, {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token.value}` 
      },
      body: JSON.stringify(completeForm)
    })
    const data = await res.json()
    if (data.code === 200) {
      ElMessage.success('排班已完成')
      completeDialogVisible.value = false
      detailDialogVisible.value = false
      fetchVisits()
      fetchStats()
    } else {
      ElMessage.error(data.message)
    }
  } catch (error) {
    ElMessage.error('操作失败')
  }
}

const handleCancel = async (visit) => {
  try {
    await ElMessageBox.confirm('确定要取消这个排班计划吗？', '确认', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    
    const res = await fetch(`/api/visits/${visit.id}/cancel`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token.value}` }
    })
    const data = await res.json()
    if (data.code === 200) {
      ElMessage.success('排班已取消')
      fetchVisits()
      fetchStats()
    } else {
      ElMessage.error(data.message)
    }
  } catch {
    // 用户取消
  }
}

const handleDelete = async (visit) => {
  try {
    await ElMessageBox.confirm('确定要删除这个排班记录吗？', '确认', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    
    const res = await fetch(`/api/visits/${visit.id}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token.value}` }
    })
    const data = await res.json()
    if (data.code === 200) {
      ElMessage.success('删除成功')
      fetchVisits()
      fetchStats()
    } else {
      ElMessage.error(data.message)
    }
  } catch {
    // 用户取消
  }
}

onMounted(async () => {
  fetchVisits()
  fetchStats()
  fetchCustomers()
  await fetchUsers()
  if (userList.value.length > 0 && !activePersonnelTab.value) {
    activePersonnelTab.value = userList.value[0].username
  }
})
</script>

<style scoped>
.visits-container {
  max-width: 1400px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}

.page-title {
  margin: 0;
  color: #333;
}

.header-right {
  display: flex;
  gap: 12px;
  align-items: center;
}

.stats-section {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.stat-card {
  background: white;
  border-radius: 12px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
}

.stat-icon {
  width: 50px;
  height: 50px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
}

.stat-icon.total { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
.stat-icon.planned { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }
.stat-icon.completed { background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }
.stat-icon.cancelled { background: linear-gradient(135deg, #bdc3c7 0%, #2c3e50 100%); }

.stat-value {
  font-size: 28px;
  font-weight: bold;
  color: #333;
}

.stat-label {
  font-size: 14px;
  color: #999;
}

.filter-section {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.calendar-view {
  background: white;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.calendar-cell {
  min-height: 100px;
  padding: 4px;
  cursor: pointer;
}

.calendar-cell.has-visit {
  background: rgba(78, 205, 196, 0.05);
}

.date-number {
  font-size: 14px;
  color: #666;
  margin-bottom: 4px;
}

.day-visits {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.visit-tag {
  font-size: 11px;
  padding: 2px 4px;
  border-radius: 4px;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.visit-tag.planned {
  background: #fff7e6;
  color: #fa8c16;
}

.visit-tag.completed {
  background: #f6ffed;
  color: #52c41a;
}

.visit-tag.cancelled {
  background: #f5f5f5;
  color: #999;
}

.list-view {
  background: white;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.table-container {
  width: 100%;
}

.table-wrapper {
  overflow-x: auto;
}

.pagination-wrapper {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

:deep(.el-descriptions__label) {
  width: 100px;
  font-weight: 500;
  color: #666;
}

.personnel-view {
  background: white;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.personnel-schedule {
  padding: 16px 0;
}

.sub-info {
  font-size: 12px;
  color: #999;
  margin-top: 2px;
}

.stat-card .stat-icon.other {
  background: linear-gradient(135deg, #43cea2 0%, #185a9d 100%);
}

.visit-tag.other-work {
  background: #e6f7ff;
  color: #1890ff;
}
</style>
