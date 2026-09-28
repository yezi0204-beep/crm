<template>
  <div class="workhours-page">
    <div class="page-header">
      <h2>⏱️ 研发工时</h2>
      <div class="header-actions">
        <el-button type="primary" @click="openForm()">填报工时</el-button>
      </div>
    </div>

    <el-card class="stats-card">
      <div class="stats-grid">
        <div class="stat-item">
          <div class="stat-value">{{ stats.hours_approved }}</div>
          <div class="stat-label">已通过工时(小时)</div>
        </div>
        <div class="stat-item">
          <div class="stat-value">{{ stats.hours_pending }}</div>
          <div class="stat-label">待审核工时(小时)</div>
        </div>
        <div class="stat-item">
          <div class="stat-value">{{ stats.pending }}</div>
          <div class="stat-label">待审核条数</div>
        </div>
        <div class="stat-item">
          <div class="stat-value">{{ stats.approved }}</div>
          <div class="stat-label">已通过条数</div>
        </div>
      </div>
    </el-card>

    <el-tabs v-model="activeTab" class="main-tabs" @tab-change="handleTabChange">
      <el-tab-pane label="我的工时" name="mine">
        <el-card>
          <div class="toolbar">
            <el-select v-model="filterStatus" placeholder="状态" clearable style="width:140px" @change="fetchMine">
              <el-option label="待审核" value="pending" />
              <el-option label="已通过" value="approved" />
              <el-option label="已退回" value="rejected" />
            </el-select>
            <el-button @click="fetchMine">刷新</el-button>
          </div>
          <el-table :data="mineList" stripe max-height="60vh" v-loading="loadingMine">
            <el-table-column prop="date" label="日期" width="110" sortable />
            <el-table-column prop="project_name" label="项目" min-width="200" show-overflow-tooltip />
            <el-table-column prop="hours" label="工时" width="80" align="right">
              <template #default="scope">{{ scope.row.hours }}</template>
            </el-table-column>
            <el-table-column prop="description" label="工作事项" min-width="220" show-overflow-tooltip />
            <el-table-column prop="status" label="状态" width="90">
              <template #default="scope">
                <el-tag :type="statusType(scope.row.status)" size="small">{{ statusText(scope.row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="reject_reason" label="退回原因" min-width="140" show-overflow-tooltip />
            <el-table-column prop="approver_name" label="审批人" width="90" />
            <el-table-column label="操作" width="150" fixed="right">
              <template #default="scope">
                <el-button v-if="scope.row.status==='pending'" size="small" @click="openForm(scope.row)">编辑</el-button>
                <el-button v-if="scope.row.status==='pending'" size="small" type="danger" @click="handleDelete(scope.row)">删除</el-button>
                <el-button v-if="scope.row.status==='rejected'" size="small" @click="openForm(scope.row)">重新提交</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane v-if="isApprover" :label="'待我审批 (' + pendingCount + ')'" name="approve">
        <el-card>
          <el-table :data="pendingList" stripe max-height="60vh" v-loading="loadingPending">
            <el-table-column prop="user_name" label="填报人" width="90" />
            <el-table-column prop="date" label="日期" width="110" />
            <el-table-column prop="project_name" label="项目" min-width="200" show-overflow-tooltip />
            <el-table-column prop="hours" label="工时" width="80" align="right" />
            <el-table-column prop="description" label="工作事项" min-width="220" show-overflow-tooltip />
            <el-table-column prop="submit_time" label="提交时间" width="160" />
            <el-table-column label="操作" width="180" fixed="right">
              <template #default="scope">
                <el-button size="small" type="success" @click="handleApprove(scope.row)">通过</el-button>
                <el-button size="small" type="danger" @click="openReject(scope.row)">退回</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane v-if="isManager" label="全部工时" name="all">
        <el-card>
          <div class="toolbar">
            <el-select v-model="allFilter.user_id" placeholder="填报人" filterable clearable style="width:150px" @change="fetchAll">
              <el-option v-for="u in reporterOptions" :key="u.username" :label="u.name" :value="u.username" />
            </el-select>
            <el-select v-model="allFilter.business_id" placeholder="项目" filterable clearable style="width:220px" @change="fetchAll">
              <el-option v-for="p in allProjectOptions" :key="p.ref_id" :label="p.name" :value="p.ref_id">
                {{ p.name }}
                <el-tag size="small" style="margin-left:6px">{{ p.ref_type === 'contract' ? '合同' : '商机' }}</el-tag>
              </el-option>
            </el-select>
            <el-select v-model="allFilter.status" placeholder="状态" clearable style="width:130px" @change="fetchAll">
              <el-option label="待审核" value="pending" />
              <el-option label="已通过" value="approved" />
              <el-option label="已退回" value="rejected" />
            </el-select>
            <el-date-picker v-model="allFilter.dateRange" type="daterange" range-separator="至"
              start-placeholder="开始日期" end-placeholder="结束日期" value-format="YYYY-MM-DD"
              style="width:260px" @change="fetchAll" />
            <el-button @click="resetAllFilter">重置</el-button>
            <el-button type="primary" @click="fetchAll">查询</el-button>
          </div>

          <div class="all-stats">
            <div class="mini-stat approved">
              <span class="v">{{ allStats.hours_approved }}</span>
              <span class="l">已通过工时</span>
            </div>
            <div class="mini-stat pending">
              <span class="v">{{ allStats.hours_pending }}</span>
              <span class="l">待审核工时</span>
            </div>
            <div class="mini-stat rejected">
              <span class="v">{{ allStats.hours_rejected }}</span>
              <span class="l">已退回工时</span>
            </div>
            <div class="mini-stat total">
              <span class="v">{{ allStats.total }}</span>
              <span class="l">填报总条数</span>
            </div>
          </div>

          <el-table :data="allList" stripe max-height="55vh" v-loading="loadingAll">
            <el-table-column prop="user_name" label="填报人" width="90" sortable />
            <el-table-column prop="date" label="日期" width="110" sortable />
            <el-table-column prop="project_name" label="项目" min-width="200" show-overflow-tooltip />
            <el-table-column prop="hours" label="工时" width="80" align="right" sortable />
            <el-table-column prop="description" label="工作事项" min-width="200" show-overflow-tooltip />
            <el-table-column prop="status" label="状态" width="90">
              <template #default="scope">
                <el-tag :type="statusType(scope.row.status)" size="small">{{ statusText(scope.row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="reject_reason" label="退回原因" min-width="120" show-overflow-tooltip />
            <el-table-column prop="approver_name" label="审批人" width="90" />
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 填报/编辑 弹窗 -->
    <el-dialog v-model="formVisible" :title="editId ? '编辑工时' : '填报工时'" width="520px">
      <el-form :model="form" :rules="rules" ref="formRef" label-width="80px">
        <el-form-item label="项目" prop="ref_id">
          <el-select v-model="form.ref_id" filterable remote :remote-method="searchProjects"
            :loading="projectLoading" placeholder="搜索并选择项目" style="width:100%" @change="onProjectChange">
            <el-option v-for="p in projectOptions" :key="p.ref_id" :label="p.name" :value="p.ref_id">
              <span>{{ p.name }}</span>
              <el-tag size="small" style="margin-left:6px">{{ p.ref_type === 'contract' ? '合同' : '商机' }}</el-tag>
              <span style="float:right;color:#999;font-size:12px">{{ p.customer_name || '' }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="日期" prop="work_date">
          <el-date-picker v-model="form.work_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="工时" prop="hours">
          <el-input-number v-model="form.hours" :min="0.5" :max="24" :step="0.5" :precision="1" style="width:100%" />
        </el-form-item>
        <el-form-item label="加班工时">
          <el-input-number v-model="form.overtime_hours" :min="0" :max="12" :step="0.5" :precision="1" style="width:100%" />
        </el-form-item>
        <el-form-item label="工作事项" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="请简要描述完成的工作事项" maxlength="300" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible=false">取消</el-button>
        <el-button type="primary" @click="submitForm">提交</el-button>
      </template>
    </el-dialog>

    <!-- 退回原因弹窗 -->
    <el-dialog v-model="rejectVisible" title="退回工时" width="440px">
      <el-form label-width="80px">
        <el-form-item label="退回原因">
          <el-input v-model="rejectReason" type="textarea" :rows="3" placeholder="请填写退回原因" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rejectVisible=false">取消</el-button>
        <el-button type="danger" @click="confirmReject">确认退回</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api'
import { useAuthStore } from '../stores/auth'
import { ElMessage, ElMessageBox } from 'element-plus'

const auth = useAuthStore()
const isApprover = computed(() =>
  auth.role === '项目经理' || auth.has('workhour.manage') || auth.has('workhour.approve')
)
const isManager = computed(() => auth.has('workhour.manage'))

const activeTab = ref('mine')
const loadingMine = ref(false)
const loadingPending = ref(false)
const loadingAll = ref(false)
const mineList = ref([])
const pendingList = ref([])
const allList = ref([])
const pendingCount = ref(0)
const stats = ref({ hours_approved: 0, hours_pending: 0, pending: 0, approved: 0 })
const allStats = ref({ total: 0, approved: 0, pending: 0, rejected: 0, hours_approved: 0, hours_pending: 0, hours_rejected: 0 })
const allProjectSummary = ref([])
const filterStatus = ref('')

// 全部工时筛选条件
const allFilter = ref({ user_id: '', business_id: '', status: '', dateRange: [] })
const reporterOptions = ref([])
const allProjectOptions = ref([])

const formVisible = ref(false)
const editId = ref(null)
const formRef = ref(null)
const form = ref({ ref_id: null, ref_type: 'business', work_date: '', hours: 8, overtime_hours: 0, description: '' })
const rules = {
  ref_id: [{ required: true, message: '请选择项目', trigger: 'change' }],
  work_date: [{ required: true, message: '请选择日期', trigger: 'change' }],
  hours: [{ required: true, message: '请填写工时', trigger: 'blur' }],
  description: [{ required: true, message: '请填写工作事项', trigger: 'blur' }],
}

const projectOptions = ref([])
const projectLoading = ref(false)

const rejectVisible = ref(false)
const rejectRow = ref(null)
const rejectReason = ref('')

const statusType = (s) => ({ pending: 'warning', approved: 'success', rejected: 'danger' }[s] || 'info')
const statusText = (s) => ({ pending: '待审核', approved: '已通过', rejected: '已退回' }[s] || s)

const searchProjects = async (kw) => {
  projectLoading.value = true
  try {
    const res = await api.get('/work-hours/projects', { keyword: kw })
    projectOptions.value = res.code === 200 ? res.data : []
  } finally {
    projectLoading.value = false
  }
}

const fetchMine = async () => {
  loadingMine.value = true
  try {
    const params = {}
    if (filterStatus.value) params.status = filterStatus.value
    const res = await api.get('/work-hours/mine', params)
    if (res.code === 200) {
      mineList.value = res.data.items
      stats.value = res.data.stats
    }
  } finally {
    loadingMine.value = false
  }
}

const fetchPending = async () => {
  if (!isApprover.value) return
  loadingPending.value = true
  try {
    const res = await api.get('/work-hours/pending')
    if (res.code === 200) {
      pendingList.value = res.data.items
      pendingCount.value = res.data.count
    }
  } finally {
    loadingPending.value = false
  }
}

const fetchReporters = async () => {
  const res = await api.get('/work-hours/users')
  if (res.code === 200) reporterOptions.value = res.data
}

const fetchAllProjects = async () => {
  const res = await api.get('/work-hours/projects')
  if (res.code === 200) allProjectOptions.value = res.data
}

const fetchAll = async () => {
  if (!isManager.value) return
  loadingAll.value = true
  try {
    const params = {}
    if (allFilter.value.user_id) params.user_id = allFilter.value.user_id
    if (allFilter.value.business_id) params.business_id = allFilter.value.business_id
    if (allFilter.value.status) params.status = allFilter.value.status
    if (allFilter.value.dateRange && allFilter.value.dateRange.length === 2) {
      params.date_from = allFilter.value.dateRange[0]
      params.date_to = allFilter.value.dateRange[1]
    }
    const res = await api.get('/work-hours/all', params)
    if (res.code === 200) {
      allList.value = res.data.items
      allStats.value = res.data.stats
      allProjectSummary.value = res.data.project_summary
    }
  } finally {
    loadingAll.value = false
  }
}

const resetAllFilter = () => {
  allFilter.value = { user_id: '', business_id: '', status: '', dateRange: [] }
  fetchAll()
}

const openForm = (row) => {
  editId.value = row ? row.id : null
  if (row) {
    // 编辑：回填 ref_id（优先用 project_id）和 ref_type
    const refId = row.project_id || row.business_id
    form.value = {
      ref_id: refId,
      ref_type: row.project_type || 'business',
      work_date: row.date || row.work_date,
      hours: row.hours,
      overtime_hours: row.overtime_hours || 0,
      description: row.description || '',
    }
    // 预加载项目选项
    searchProjects('')
  } else {
    form.value = { ref_id: null, ref_type: 'business', work_date: '', hours: 8, overtime_hours: 0, description: '' }
    projectOptions.value = []
  }
  formVisible.value = true
}

// 选择项目时同步 ref_type
const onProjectChange = (val) => {
  const p = projectOptions.value.find(x => x.ref_id === val)
  if (p) form.value.ref_type = p.ref_type
}

const submitForm = async () => {
  await formRef.value.validate()
  const payload = { ...form.value }
  let res
  if (editId.value) {
    res = await api.put(`/work-hours/${editId.value}`, payload)
  } else {
    res = await api.post('/work-hours', payload)
  }
  if (res.code === 200) {
    ElMessage.success(res.message || '已提交')
    formVisible.value = false
    fetchMine()
  } else {
    ElMessage.error(res.message || '提交失败')
  }
}

const handleDelete = (row) => {
  ElMessageBox.confirm(`确认删除 ${row.date} 的工时记录？`, '提示', { type: 'warning' })
    .then(async () => {
      const res = await api.delete(`/work-hours/${row.id}`)
      if (res.code === 200) {
        ElMessage.success('已删除')
        fetchMine()
      } else {
        ElMessage.error(res.message || '删除失败')
      }
    }).catch(() => {})
}

const handleApprove = async (row) => {
  const res = await api.post(`/work-hours/${row.id}/approve`)
  if (res.code === 200) {
    ElMessage.success('已通过')
    fetchPending()
  } else {
    ElMessage.error(res.message || '操作失败')
  }
}

const openReject = (row) => {
  rejectRow.value = row
  rejectReason.value = ''
  rejectVisible.value = true
}

const confirmReject = async () => {
  if (!rejectReason.value.trim()) {
    ElMessage.warning('请填写退回原因')
    return
  }
  const res = await api.post(`/work-hours/${rejectRow.value.id}/reject`, { reason: rejectReason.value })
  if (res.code === 200) {
    ElMessage.success('已退回')
    rejectVisible.value = false
    fetchPending()
  } else {
    ElMessage.error(res.message || '操作失败')
  }
}

onMounted(() => {
  fetchMine()
  if (isApprover.value) fetchPending()
  if (isManager.value) {
    fetchReporters()
    fetchAllProjects()
  }
})

// 切换到全部工时标签时加载数据
const handleTabChange = (tab) => {
  if (tab === 'all' && isManager.value) fetchAll()
}
</script>

<style scoped>
.workhours-page { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; justify-content: space-between; align-items: center; }
.page-header h2 { margin: 0; font-size: 20px; color: #333; }
.header-actions { display: flex; gap: 12px; }
.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 24px; }
.stat-item { text-align: center; padding: 20px; background: linear-gradient(135deg, #f8f9fa 0%, #f1f3f4 100%); border-radius: 12px; }
.stat-value { font-size: 28px; font-weight: bold; color: #4ecdc4; }
.stat-label { font-size: 14px; color: #999; margin-top: 8px; }
.toolbar { display: flex; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; align-items: center; }
.main-tabs { margin-top: 0; }
.all-stats { display: flex; gap: 16px; margin-bottom: 16px; }
.mini-stat { flex: 1; text-align: center; padding: 14px 0; border-radius: 8px; background: #f5f7fa; }
.mini-stat .v { display: block; font-size: 24px; font-weight: bold; }
.mini-stat .l { font-size: 13px; color: #999; }
.mini-stat.approved .v { color: #67c23a; }
.mini-stat.pending .v { color: #e6a23c; }
.mini-stat.rejected .v { color: #f56c6c; }
.mini-stat.total .v { color: #409eff; }
</style>
