<template>
  <div class="market-tasks-page">
    <!-- 页头 -->
    <div class="page-header">
      <div class="header-title">
        <span class="title-icon">📨</span>
        <div>
          <h2>市场任务单</h2>
          <p>跨部门市场任务派发、审批与执行跟踪</p>
        </div>
      </div>
      <el-button type="primary" @click="openCreate">
        <span style="margin-right: 4px;">＋</span> 新建任务单
      </el-button>
    </div>

    <!-- 筛选区 -->
    <div class="filter-card">
      <div class="filter-row">
        <el-radio-group v-model="scope" size="default" @change="handleSearch">
          <el-radio-button label="related">与我相关</el-radio-button>
          <el-radio-button label="created">我发起的</el-radio-button>
          <el-radio-button label="received">我接收的</el-radio-button>
          <el-radio-button label="pending">待我审批</el-radio-button>
          <el-radio-button v-if="authStore.has('data.view_all')" label="all">全部</el-radio-button>
        </el-radio-group>
      </div>
      <div class="filter-row">
        <el-input
          v-model="keyword"
          placeholder="任务编号 / 任务名称 / 任务来源"
          clearable
          style="width: 280px;"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-select v-model="statusFilter" placeholder="全部状态" clearable style="width: 170px;" @change="handleSearch">
          <el-option v-for="(meta, key) in statusMeta" :key="key" :label="meta.label" :value="key" />
        </el-select>
        <el-button type="primary" @click="handleSearch">搜索</el-button>
        <el-button @click="handleReset">重置</el-button>
      </div>
    </div>

    <!-- 任务列表 -->
    <div class="table-card">
      <el-table :data="tasks" v-loading="loading" stripe style="width: 100%;">
        <el-table-column prop="task_no" label="任务编号" width="150" />
        <el-table-column prop="title" label="任务名称" min-width="220" show-overflow-tooltip />
        <el-table-column prop="source" label="任务来源" width="150" show-overflow-tooltip />
        <el-table-column label="发起" width="160">
          <template #default="{ row }">
            <div class="person-cell">
              <span>{{ row.initiator_name || row.initiator }}</span>
              <span class="dept-text">{{ row.initiator_dept }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="接收" width="160">
          <template #default="{ row }">
            <div class="person-cell">
              <span>{{ row.receiver_name || row.receiver || '-' }}</span>
              <span class="dept-text">{{ row.receiver_dept || '' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="expected_completion" label="期望完成" width="180" show-overflow-tooltip />
        <el-table-column label="状态" width="140">
          <template #default="{ row }">
            <el-tag :type="statusMeta[row.status]?.type || 'info'" size="small" effect="light">
              {{ statusMeta[row.status]?.label || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="perPage"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="fetchList"
          @size-change="handleSizeChange"
        />
      </div>
    </div>

    <!-- 新建/编辑弹窗 -->
    <el-dialog
      v-model="formDialogVisible"
      :title="editingId ? '编辑任务单' : '新建任务单'"
      width="680px"
      :close-on-click-modal="false"
    >
      <el-form :model="form" label-width="110px">
        <el-form-item label="日期">
          <el-date-picker v-model="form.task_date" type="date" value-format="YYYY-MM-DD" style="width: 200px;" />
        </el-form-item>
        <el-form-item label="任务名称" required>
          <el-input v-model="form.title" placeholder="如：合肥市土地整治智慧监测" maxlength="100" show-word-limit />
        </el-form-item>
        <el-form-item label="任务来源">
          <el-input v-model="form.source" placeholder="如：合肥市自规局" />
        </el-form-item>
        <el-form-item label="接收人" required>
          <el-select v-model="form.receiver" filterable placeholder="选择接收人" style="width: 100%;">
            <el-option-group
              v-for="group in groupedUsers"
              :key="group.department"
              :label="group.department"
            >
              <el-option
                v-for="opt in group.options"
                :key="opt.username"
                :label="opt.name"
                :value="opt.username"
              />
            </el-option-group>
          </el-select>
        </el-form-item>
        <el-form-item label="期望完成日期">
          <el-input v-model="form.expected_completion" placeholder="如：2025年3月11日（方案）、3月12日（会议）" />
        </el-form-item>
        <el-form-item label="任务要求">
          <el-input
            v-model="form.requirements"
            type="textarea"
            :rows="7"
            placeholder="请填写任务具体要求，可包含多条事项……"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formDialogVisible = false">取消</el-button>
        <el-button @click="handleSave(false)" :loading="saving">存草稿</el-button>
        <el-button type="primary" @click="handleSave(true)" :loading="saving">保存并提交</el-button>
      </template>
    </el-dialog>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" title="任务单详情" width="760px">
      <div v-if="detail" class="detail-wrap">
        <div class="detail-header">
          <span class="detail-no">{{ detail.task_no }}</span>
          <el-tag :type="statusMeta[detail.status]?.type" size="small">
            {{ statusMeta[detail.status]?.label }}
          </el-tag>
        </div>

        <el-descriptions :column="2" border size="small" class="detail-desc">
          <el-descriptions-item label="日期">{{ detail.task_date }}</el-descriptions-item>
          <el-descriptions-item label="任务来源">{{ detail.source || '-' }}</el-descriptions-item>
          <el-descriptions-item label="任务名称" :span="2">{{ detail.title }}</el-descriptions-item>
          <el-descriptions-item label="发起人">{{ detail.initiator_name }}（{{ detail.initiator_dept }}）</el-descriptions-item>
          <el-descriptions-item label="接收人">
            {{ detail.receiver ? `${detail.receiver_name}（${detail.receiver_dept}）` : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="期望完成日期" :span="2">{{ detail.expected_completion || '-' }}</el-descriptions-item>
          <el-descriptions-item label="任务要求" :span="2">
            <div class="pre-wrap">{{ detail.requirements || '-' }}</div>
          </el-descriptions-item>
        </el-descriptions>

        <!-- 发起部门审批 -->
        <div class="approval-block">
          <div class="approval-title">发起部门意见</div>
          <template v-if="detail.init_result">
            <div class="approval-record">
              <el-tag :type="detail.init_result === 'approved' ? 'success' : 'danger'" size="small">
                {{ detail.init_result === 'approved' ? '通过' : '驳回' }}
              </el-tag>
              <span class="pre-wrap opinion-text">{{ detail.init_opinion || '（无意见）' }}</span>
            </div>
            <div class="approval-meta">负责人：{{ detail.init_approver }} ｜ {{ detail.init_approved_at }}</div>
          </template>

          <template v-if="detail.status === 'pending_init' && canInitApprove(detail)">
            <el-input v-model="initForm.opinion" type="textarea" :rows="2"
                      placeholder="审批意见（通过时可留空，驳回时必填）" class="action-input" />
            <div class="action-btns">
              <el-button type="success" :loading="acting" @click="doInitApproval('approve')">通过</el-button>
              <el-button type="danger" :loading="acting" @click="doInitApproval('reject')">驳回</el-button>
            </div>
          </template>
          <div v-if="detail.status === 'pending_init' && !canInitApprove(detail)" class="waiting-text">
            等待发起部门负责人审批
          </div>
        </div>

        <!-- 接收部门受理 -->
        <div class="approval-block">
          <div class="approval-title">接收部门意见</div>
          <template v-if="detail.recv_result">
            <div class="approval-record">
              <el-tag :type="detail.recv_result === 'accepted' ? 'success' : 'danger'" size="small">
                {{ detail.recv_result === 'accepted' ? '同意接收' : '拒绝' }}
              </el-tag>
              <span class="pre-wrap opinion-text">{{ detail.recv_opinion || '（无意见）' }}</span>
            </div>
            <div class="approval-meta">
              负责人：{{ detail.recv_approver }} ｜ {{ detail.recv_approved_at }}
            </div>
            <div v-if="detail.recv_result === 'accepted'" class="approval-meta">
              预计完成日期：{{ detail.est_completion_date }} ｜ 预计投入工时：{{ detail.est_work_days }} 人日
            </div>
          </template>

          <template v-if="detail.status === 'pending_recv' && canRecvApprove(detail)">
            <div class="recv-form">
              <div class="recv-form-item">
                <span class="recv-label"><em>*</em> 预计完成日期</span>
                <el-date-picker v-model="recvForm.est_completion_date" type="date"
                                value-format="YYYY-MM-DD" style="width: 180px;" />
              </div>
              <div class="recv-form-item">
                <span class="recv-label"><em>*</em> 预计投入工时</span>
                <el-input-number v-model="recvForm.est_work_days" :min="0.5" :step="1" :precision="1" />
                <span class="unit-text">人日</span>
              </div>
            </div>
            <el-input v-model="recvForm.opinion" type="textarea" :rows="2"
                      placeholder="受理意见，如：同意接收任务（拒绝时必填）" class="action-input" />
            <div class="action-btns">
              <el-button type="success" :loading="acting" @click="doRecvApproval('accept')">同意接收</el-button>
              <el-button type="danger" :loading="acting" @click="doRecvApproval('reject')">拒绝</el-button>
            </div>
          </template>
          <div v-if="detail.status === 'pending_recv' && !canRecvApprove(detail)" class="waiting-text">
            等待接收部门负责人受理
          </div>
        </div>

        <!-- 完成区 -->
        <div class="approval-block">
          <div class="approval-title">执行结果</div>
          <template v-if="detail.status === 'in_progress' && canComplete(detail)">
            <el-input v-model="completeForm.note" type="textarea" :rows="2"
                      placeholder="完成说明（可选）" class="action-input" />
            <div class="action-btns">
              <el-button type="primary" :loading="acting" @click="doComplete">标记完成</el-button>
            </div>
          </template>
          <template v-else-if="detail.status === 'in_progress'">
            <div class="waiting-text">任务执行中……</div>
          </template>
          <template v-if="detail.status === 'completed'">
            <div class="approval-record">
              <el-tag type="success" size="small">已完成</el-tag>
              <span class="pre-wrap opinion-text">{{ detail.result_note || '（无说明）' }}</span>
            </div>
            <div class="approval-meta">完成时间：{{ detail.completed_at }}</div>
          </template>
        </div>

        <!-- 发起人的编辑入口 -->
        <div v-if="isInitiator(detail) && ['draft', 'rejected'].includes(detail.status)" class="detail-footer">
          <el-button type="primary" @click="openEdit(detail)">编辑任务单</el-button>
          <el-button type="success" @click="doSubmit(detail)">提交任务单</el-button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()

// ==================== 状态元数据 ====================

const statusMeta = {
  draft:        { label: '草稿',           type: 'info' },
  pending_init: { label: '待发起部门审批', type: 'warning' },
  pending_recv: { label: '待接收部门受理', type: 'warning' },
  in_progress:  { label: '执行中',         type: 'primary' },
  completed:    { label: '已完成',         type: 'success' },
  rejected:     { label: '已驳回',         type: 'danger' },
}

// ==================== 列表与筛选 ====================

const tasks = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const perPage = ref(20)

const scope = ref('related')
const keyword = ref('')
const statusFilter = ref('')

const fetchList = async () => {
  loading.value = true
  try {
    const res = await api.get('/market-tasks', {
      scope: scope.value,
      keyword: keyword.value,
      status: statusFilter.value,
      page: page.value,
      per_page: perPage.value,
    })
    if (res.code === 200) {
      tasks.value = res.data
      total.value = res.total
    }
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  page.value = 1
  fetchList()
}

const handleReset = () => {
  keyword.value = ''
  statusFilter.value = ''
  scope.value = 'related'
  page.value = 1
  fetchList()
}

const handleSizeChange = () => {
  page.value = 1
  fetchList()
}

// ==================== 权限判断（与后端同口径） ====================

const allRoles = computed(() =>
  new Set([authStore.role, ...(authStore.roles || [])].filter(Boolean))
)

const canInitApprove = (t) =>
  allRoles.value.has('院长') ||
  (allRoles.value.has('主任') && authStore.department === t.initiator_dept)

const canRecvApprove = (t) =>
  allRoles.value.has('院长') ||
  (allRoles.value.has('主任') && authStore.department === t.receiver_dept)

const canComplete = (t) =>
  [t.initiator, t.receiver].includes(authStore.username)

const isInitiator = (t) => t.initiator === authStore.username

// ==================== 用户目录 ====================

const userList = ref([])

const fetchUsers = async () => {
  const res = await api.get('/market-tasks/users')
  if (res.code === 200) userList.value = res.data
}

const groupedUsers = computed(() => {
  // 按部门分组供 el-option-group 使用
  const groups = []
  const map = new Map()
  for (const u of userList.value) {
    const dept = u.department || '其他'
    if (!map.has(dept)) {
      const g = { department: dept, options: [] }
      map.set(dept, g)
      groups.push(g)
    }
    map.get(dept).options.push({ name: u.name, username: u.username })
  }
  return groups
})

// ==================== 新建 / 编辑 ====================

const formDialogVisible = ref(false)
const saving = ref(false)
const editingId = ref(null)

const defaultForm = () => ({
  task_date: new Date().toISOString().slice(0, 10),
  title: '',
  source: '',
  receiver: '',
  expected_completion: '',
  requirements: '',
})

const form = reactive(defaultForm())

const resetForm = () => {
  Object.assign(form, defaultForm())
}

const openCreate = () => {
  editingId.value = null
  resetForm()
  formDialogVisible.value = true
}

const openEdit = (task) => {
  editingId.value = task.id
  Object.assign(form, {
    task_date: task.task_date,
    title: task.title,
    source: task.source,
    receiver: task.receiver,
    expected_completion: task.expected_completion,
    requirements: task.requirements,
  })
  detailVisible.value = false
  formDialogVisible.value = true
}

const handleSave = async (submit) => {
  if (!form.title.trim()) {
    ElMessage.warning('请填写任务名称')
    return
  }
  if (submit && !form.receiver) {
    ElMessage.warning('提交前请选择接收人')
    return
  }
  saving.value = true
  try {
    const payload = { ...form, submit }
    const res = editingId.value
      ? await api.put(`/market-tasks/${editingId.value}`, payload)
      : await api.post('/market-tasks', payload)
    if (res.code === 200) {
      ElMessage.success(res.message || '已保存')
      formDialogVisible.value = false
      fetchList()
    }
  } finally {
    saving.value = false
  }
}

const doSubmit = async (task) => {
  if (!task.receiver) {
    ElMessage.warning('请先编辑并选择接收人')
    return
  }
  const res = await api.post(`/market-tasks/${task.id}/submit`)
  if (res.code === 200) {
    ElMessage.success(res.message)
    detailVisible.value = false
    fetchList()
  }
}

// ==================== 详情 ====================

const detailVisible = ref(false)
const detail = ref(null)
const acting = ref(false)

const initForm = reactive({ opinion: '' })
const recvForm = reactive({
  est_completion_date: '',
  est_work_days: 1,
  opinion: '',
})
const completeForm = reactive({ note: '' })

const openDetail = async (row) => {
  const res = await api.get(`/market-tasks/${row.id}`)
  if (res.code === 200) {
    detail.value = res.data
    initForm.opinion = ''
    recvForm.est_completion_date = res.data.est_completion_date || ''
    recvForm.est_work_days = res.data.est_work_days || 1
    recvForm.opinion = ''
    completeForm.note = ''
    detailVisible.value = true
  }
}

const refreshDetail = async () => {
  const res = await api.get(`/market-tasks/${detail.value.id}`)
  if (res.code === 200) detail.value = res.data
}

// 发起部门审批
const doInitApproval = async (action) => {
  if (action === 'reject' && !initForm.opinion.trim()) {
    ElMessage.warning('驳回请填写意见')
    return
  }
  try {
    await ElMessageBox.confirm(
      action === 'approve' ? '确认通过该任务单？' : '确认驳回该任务单？',
      '审批确认', { type: 'warning', confirmButtonText: '确认', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  acting.value = true
  try {
    const res = await api.post(
      `/market-tasks/${detail.value.id}/init-approval`,
      { action, opinion: initForm.opinion }
    )
    if (res.code === 200) {
      ElMessage.success(res.message)
      await refreshDetail()
      fetchList()
    }
  } finally {
    acting.value = false
  }
}

// 接收部门受理
const doRecvApproval = async (action) => {
  if (action === 'reject' && !recvForm.opinion.trim()) {
    ElMessage.warning('拒绝请填写意见')
    return
  }
  if (action === 'accept') {
    if (!recvForm.est_completion_date) {
      ElMessage.warning('请选择预计完成日期')
      return
    }
    if (!recvForm.est_work_days || recvForm.est_work_days <= 0) {
      ElMessage.warning('请填写预计投入工时')
      return
    }
  }
  try {
    await ElMessageBox.confirm(
      action === 'accept' ? '确认接收该任务？' : '确认拒绝接收该任务？',
      '受理确认', { type: 'warning', confirmButtonText: '确认', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  acting.value = true
  try {
    const res = await api.post(
      `/market-tasks/${detail.value.id}/recv-approval`,
      {
        action,
        opinion: recvForm.opinion,
        est_completion_date: recvForm.est_completion_date,
        est_work_days: recvForm.est_work_days,
      }
    )
    if (res.code === 200) {
      ElMessage.success(res.message)
      await refreshDetail()
      fetchList()
    }
  } finally {
    acting.value = false
  }
}

// 标记完成
const doComplete = async () => {
  try {
    await ElMessageBox.confirm('确认该任务已完成？', '完成确认',
      { type: 'warning', confirmButtonText: '确认', cancelButtonText: '取消' })
  } catch {
    return
  }
  acting.value = true
  try {
    const res = await api.post(
      `/market-tasks/${detail.value.id}/complete`,
      { note: completeForm.note }
    )
    if (res.code === 200) {
      ElMessage.success(res.message)
      await refreshDetail()
      fetchList()
    }
  } finally {
    acting.value = false
  }
}

// ==================== 初始化 ====================

fetchUsers()
fetchList()
</script>

<style scoped>
.market-tasks-page {
  padding: 4px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #fff;
  border-radius: 10px;
  padding: 18px 22px;
  margin-bottom: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.header-title {
  display: flex;
  align-items: center;
  gap: 14px;
}

.title-icon {
  font-size: 34px;
}

.header-title h2 {
  margin: 0;
  font-size: 20px;
  color: #1f2937;
}

.header-title p {
  margin: 4px 0 0;
  font-size: 13px;
  color: #9ca3af;
}

.filter-card {
  background: #fff;
  border-radius: 10px;
  padding: 16px 20px;
  margin-bottom: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.filter-row + .filter-row {
  margin-top: 12px;
}

.table-card {
  background: #fff;
  border-radius: 10px;
  padding: 18px 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.person-cell {
  display: flex;
  flex-direction: column;
  line-height: 1.4;
}

.dept-text {
  font-size: 12px;
  color: #9ca3af;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

/* 详情 */
.detail-wrap {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.detail-no {
  font-size: 17px;
  font-weight: 600;
  color: #1f2937;
}

.pre-wrap {
  white-space: pre-wrap;
  word-break: break-word;
}

.approval-block {
  border: 1px solid #eef0f3;
  border-radius: 8px;
  padding: 14px 16px;
  background: #fafbfc;
}

.approval-title {
  font-weight: 600;
  font-size: 14px;
  color: #374151;
  margin-bottom: 10px;
}

.approval-record {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.opinion-text {
  flex: 1;
  font-size: 13px;
  color: #4b5563;
}

.approval-meta {
  margin-top: 8px;
  font-size: 12px;
  color: #9ca3af;
}

.action-input {
  margin-top: 10px;
}

.action-btns {
  display: flex;
  gap: 10px;
  margin-top: 12px;
}

.waiting-text {
  font-size: 13px;
  color: #9ca3af;
}

.recv-form {
  display: flex;
  gap: 28px;
  flex-wrap: wrap;
}

.recv-form-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.recv-label {
  font-size: 13px;
  color: #4b5563;
}

.recv-label em {
  color: #ef4444;
  font-style: normal;
}

.unit-text {
  font-size: 13px;
  color: #6b7280;
}

.detail-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
