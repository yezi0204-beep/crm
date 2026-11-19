<template>
  <div class="rd-page">
    <!-- 页头 -->
    <div class="page-header">
      <div class="header-title">
        <span class="title-icon">🧪</span>
        <div>
          <h2>自研项目</h2>
          <p>自主研发项目立项台账、里程碑跟踪与成果物登记（工时已打通）</p>
        </div>
      </div>
      <el-button v-if="canManage" type="primary" @click="openCreate">
        <span style="margin-right: 4px;">＋</span> 新建自研项目
      </el-button>
    </div>

    <!-- 统计 -->
    <div class="stat-row">
      <div class="stat-card">
        <div class="stat-label">项目总数</div>
        <div class="stat-value">{{ stats.total || 0 }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">进行中</div>
        <div class="stat-value running">{{ stats.running || 0 }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">筹备中</div>
        <div class="stat-value preparing">{{ stats.preparing || 0 }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">已结项</div>
        <div class="stat-value finished">{{ stats.finished || 0 }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">预算总额（元）</div>
        <div class="stat-value budget">{{ formatMoney(stats.budget_total) }}</div>
      </div>
    </div>

    <!-- 筛选 -->
    <div class="filter-card">
      <el-input v-model="filters.keyword" placeholder="项目名称 / 编号 / 负责人"
        clearable style="width: 260px" @keyup.enter="fetchList" @clear="fetchList" />
      <el-select v-model="filters.status" placeholder="全部状态" clearable style="width: 140px" @change="fetchList">
        <el-option v-for="s in statuses" :key="s" :label="s" :value="s" />
      </el-select>
      <el-checkbox v-model="filters.mine" @change="fetchList">只看我参与的</el-checkbox>
      <el-button type="primary" @click="fetchList">搜索</el-button>
      <el-button @click="resetFilters">重置</el-button>
    </div>

    <!-- 列表 -->
    <div class="table-card">
      <el-table :data="items" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="code" label="项目编号" width="130">
          <template #default="{ row }">{{ row.code || '—' }}</template>
        </el-table-column>
        <el-table-column prop="name" label="项目名称" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <a class="link" @click="openDetail(row.id)">{{ row.name }}</a>
          </template>
        </el-table-column>
        <el-table-column prop="owner_name" label="负责人" width="100" />
        <el-table-column prop="department" label="部门" width="110">
          <template #default="{ row }">{{ row.department || '—' }}</template>
        </el-table-column>
        <el-table-column label="起止时间" width="190">
          <template #default="{ row }">{{ row.start_date || '—' }} ~ {{ row.end_date || '—' }}</template>
        </el-table-column>
        <el-table-column label="预算（元）" width="130" align="right">
          <template #default="{ row }">{{ formatMoney(row.budget) }}</template>
        </el-table-column>
        <el-table-column label="进度" width="150">
          <template #default="{ row }">
            <el-progress :percentage="row.progress" :stroke-width="10"
              :status="row.progress >= 100 ? 'success' : undefined" />
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="成员" width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.member_names || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row.id)">详情</el-button>
            <template v-if="canEdit(row)">
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button link type="danger" @click="removeProject(row)">删除</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!loading && !items.length" class="empty-tip">暂无自研项目，点击右上角「新建自研项目」开始立项</div>
    </div>

    <!-- 新建 / 编辑 -->
    <el-dialog v-model="formVisible" :title="editId ? '编辑自研项目' : '新建自研项目'" width="720px">
      <el-form :model="form" :rules="rules" ref="formRef" label-width="90px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="项目名称" prop="name">
              <el-input v-model="form.name" placeholder="如：智能巡检机器人研发" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="项目编号">
              <el-input v-model="form.code" placeholder="如：RD-2026-001" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="项目分类">
              <el-input v-model="form.category" placeholder="如：产品研发 / 技术预研" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="负责人">
              <el-select v-model="form.owner_id" filterable style="width:100%" @change="onOwnerChange">
                <el-option v-for="u in users" :key="u.username"
                  :label="u.name + (u.department ? '（' + u.department + '）' : '')" :value="u.username" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="所属部门">
              <el-input v-model="form.department" placeholder="默认取负责人部门" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="预算（元）">
              <el-input-number v-model="form.budget" :min="0" :precision="2" :step="10000"
                controls-position="right" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="开始日期">
              <el-date-picker v-model="form.start_date" type="date" value-format="YYYY-MM-DD"
                placeholder="选择日期" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="结束日期">
              <el-date-picker v-model="form.end_date" type="date" value-format="YYYY-MM-DD"
                placeholder="选择日期" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="项目状态">
              <el-select v-model="form.status" style="width:100%">
                <el-option v-for="s in statuses" :key="s" :label="s" :value="s" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="项目进度">
              <el-slider v-model="form.progress" :max="100" show-input :disabled="hasMilestones"
                style="width:100%" />
              <div v-if="hasMilestones" class="hint">已配置里程碑，进度由里程碑完成比例自动计算</div>
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="项目成员">
              <el-select v-model="form.member_ids" multiple filterable collapse-tags
                collapse-tags-tooltip placeholder="选择参与成员" style="width:100%">
                <el-option v-for="u in users" :key="u.username"
                  :label="u.name + (u.department ? '（' + u.department + '）' : '')" :value="u.username" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="研发目标">
              <el-input v-model="form.objective" type="textarea" :rows="3" placeholder="项目目标、技术路线、预期成果" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="备注">
              <el-input v-model="form.remark" type="textarea" :rows="2" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveProject">保存</el-button>
      </template>
    </el-dialog>

    <!-- 详情 -->
    <el-drawer v-model="detailVisible" :title="detail.name || '自研项目详情'" size="52%">
      <div v-loading="detailLoading" class="detail-body">
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="项目编号">{{ detail.code || '—' }}</el-descriptions-item>
          <el-descriptions-item label="项目分类">{{ detail.category || '—' }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTagType(detail.status)" size="small">{{ detail.status }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="负责人">{{ detail.owner_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="部门">{{ detail.department || '—' }}</el-descriptions-item>
          <el-descriptions-item label="预算（元）">{{ formatMoney(detail.budget) }}</el-descriptions-item>
          <el-descriptions-item label="起止时间">
            {{ detail.start_date || '—' }} ~ {{ detail.end_date || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="项目进度" :span="2">
            <el-progress :percentage="detail.progress || 0" :stroke-width="12" style="max-width:320px" />
          </el-descriptions-item>
          <el-descriptions-item label="成员" :span="3">{{ detail.member_names || '—' }}</el-descriptions-item>
          <el-descriptions-item label="研发目标" :span="3">
            <div class="pre">{{ detail.objective || '—' }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="备注" :span="3">{{ detail.remark || '—' }}</el-descriptions-item>
        </el-descriptions>

        <!-- 工时汇总 -->
        <div class="section">
          <div class="section-title">⏱️ 研发工时</div>
          <div class="wh-summary">
            <span>记录 <b>{{ detail.workhours?.records || 0 }}</b> 条</span>
            <span>累计 <b>{{ detail.workhours?.hours || 0 }}</b> 小时</span>
            <span>已通过 <b class="ok">{{ detail.workhours?.hours_approved || 0 }}</b> 小时</span>
            <span>待审核 <b class="warn">{{ detail.workhours?.hours_pending || 0 }}</b> 小时</span>
          </div>
          <div v-if="detail.workhour_members && detail.workhour_members.length" class="wh-members">
            <el-tag v-for="m in detail.workhour_members" :key="m.user_id" size="small" type="info" class="wh-tag">
              {{ m.user_name }}：{{ m.hours }}h
            </el-tag>
          </div>
        </div>

        <!-- 里程碑 -->
        <div class="section">
          <div class="section-title">
            🎯 里程碑
            <span class="section-sub">完成比例自动折算项目进度</span>
          </div>
          <div v-if="detail.can_edit" class="inline-form">
            <el-input v-model="msForm.name" placeholder="里程碑名称" style="width:220px" />
            <el-date-picker v-model="msForm.plan_date" type="date" value-format="YYYY-MM-DD"
              placeholder="计划日期" style="width:150px" />
            <el-input v-model="msForm.owner" placeholder="责任人" style="width:120px" />
            <el-button type="primary" @click="addMilestone">添加</el-button>
          </div>
          <el-table :data="detail.milestones || []" size="small" border style="width:100%">
            <el-table-column label="完成" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox :model-value="row.status === 'done'"
                  :disabled="!detail.can_edit" @change="toggleMilestone(row)" />
              </template>
            </el-table-column>
            <el-table-column prop="name" label="里程碑" min-width="180" />
            <el-table-column prop="plan_date" label="计划日期" width="110" />
            <el-table-column prop="actual_date" label="实际完成" width="110">
              <template #default="{ row }">
                <el-date-picker v-if="detail.can_edit" v-model="row.actual_date" type="date"
                  value-format="YYYY-MM-DD" size="small" style="width:105px"
                  @change="updateMilestone(row)" />
                <span v-else>{{ row.actual_date || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="owner" label="责任人" width="100" />
            <el-table-column label="操作" width="70">
              <template #default="{ row }">
                <el-button v-if="detail.can_edit" link type="danger"
                  @click="deleteMilestone(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!(detail.milestones || []).length" class="empty-inline">暂无里程碑</div>
        </div>

        <!-- 成果物 -->
        <div class="section">
          <div class="section-title">📦 成果物</div>
          <div v-if="detail.can_edit" class="inline-form">
            <el-input v-model="dvForm.name" placeholder="成果物名称" style="width:240px" />
            <el-select v-model="dvForm.dtype" style="width:110px">
              <el-option v-for="t in deliverableTypes" :key="t" :label="t" :value="t" />
            </el-select>
            <el-date-picker v-model="dvForm.deliver_date" type="date" value-format="YYYY-MM-DD"
              placeholder="完成日期" style="width:150px" />
            <el-button type="primary" @click="addDeliverable">登记</el-button>
          </div>
          <el-table :data="detail.deliverables || []" size="small" border style="width:100%">
            <el-table-column prop="name" label="成果物名称" min-width="200" />
            <el-table-column prop="dtype" label="类型" width="90" />
            <el-table-column prop="deliver_date" label="完成日期" width="110" />
            <el-table-column label="操作" width="70">
              <template #default="{ row }">
                <el-button v-if="detail.can_edit" link type="danger"
                  @click="deleteDeliverable(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!(detail.deliverables || []).length" class="empty-inline">暂无成果物</div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()

const loading = ref(false)
const saving = ref(false)
const items = ref([])
const stats = ref({})
const canManage = ref(false)
const statuses = ref(['筹备中', '进行中', '已结项', '已终止'])
const deliverableTypes = ref(['文档', '专利', '软著', '样机', '其它'])
const users = ref([])

const filters = reactive({ keyword: '', status: '', mine: false })

const formVisible = ref(false)
const formRef = ref(null)
const editId = ref(null)
const hasMilestones = ref(false)
const form = ref(emptyForm())
const rules = {
  name: [{ required: true, message: '请填写项目名称', trigger: 'blur' }],
}

const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref({})
const msForm = reactive({ name: '', plan_date: '', owner: '' })
const dvForm = reactive({ name: '', dtype: '文档', deliver_date: '' })

function emptyForm() {
  return {
    code: '', name: '', category: '', objective: '',
    owner_id: '', owner_name: '', department: '',
    budget: 0, start_date: '', end_date: '',
    status: '筹备中', progress: 0, member_ids: [], remark: '',
  }
}

const formatMoney = (v) => Number(v || 0).toFixed(2)

const statusTagType = (s) => ({
  进行中: 'primary', 筹备中: 'info', 已结项: 'success', 已终止: 'danger',
}[s] || 'info')

const canEdit = (row) => canManage.value || row.owner_id === authStore.username

const fetchList = async () => {
  loading.value = true
  try {
    const res = await api.get('/rd-projects', {
      keyword: filters.keyword || undefined,
      status: filters.status || undefined,
      mine: filters.mine ? 1 : undefined,
    })
    if (res.code === 200) {
      items.value = res.data.items || []
      stats.value = res.data.stats || {}
      canManage.value = !!res.data.can_manage
    } else {
      ElMessage.error(res.message || '加载失败')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

const fetchMeta = async () => {
  try {
    const res = await api.get('/rd-projects/meta')
    if (res.code === 200) {
      statuses.value = res.data.statuses || statuses.value
      deliverableTypes.value = res.data.deliverable_types || deliverableTypes.value
      users.value = res.data.users || []
    }
  } catch (e) { /* ignore */ }
}

const resetFilters = () => {
  filters.keyword = ''
  filters.status = ''
  filters.mine = false
  fetchList()
}

const onOwnerChange = (val) => {
  const u = users.value.find(x => x.username === val)
  if (u) form.value.department = u.department || form.value.department
}

const openCreate = () => {
  editId.value = null
  hasMilestones.value = false
  form.value = emptyForm()
  formVisible.value = true
}

const openEdit = (row) => {
  editId.value = row.id
  hasMilestones.value = false
  form.value = {
    ...emptyForm(),
    ...row,
    member_ids: (row.members || []).map(m => m.username),
    budget: Number(row.budget || 0),
  }
  formVisible.value = true
  // 是否有里程碑会影响进度是否可编辑
  api.get(`/rd-projects/${row.id}`).then(res => {
    if (res.code === 200) hasMilestones.value = (res.data.milestones || []).length > 0
  }).catch(() => {})
}

const saveProject = async () => {
  await formRef.value.validate()
  saving.value = true
  try {
    const payload = { ...form.value }
    delete payload.owner_name
    delete payload.members
    delete payload.member_names
    let res
    if (editId.value) {
      res = await api.put(`/rd-projects/${editId.value}`, payload)
    } else {
      res = await api.post('/rd-projects', payload)
    }
    if (res.code === 200) {
      ElMessage.success(res.message || '已保存')
      formVisible.value = false
      fetchList()
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

const removeProject = (row) => {
  ElMessageBox.confirm(`确认删除自研项目「${row.name}」？该操作会同时删除里程碑与成果物记录。`, '提示',
    { type: 'warning' }).then(async () => {
    const res = await api.delete(`/rd-projects/${row.id}`)
    if (res.code === 200) {
      ElMessage.success('已删除')
      fetchList()
    } else {
      ElMessage.error(res.message || '删除失败')
    }
  }).catch(() => {})
}

const openDetail = async (pid) => {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = {}
  try {
    const res = await api.get(`/rd-projects/${pid}`)
    if (res.code === 200) detail.value = res.data
    else ElMessage.error(res.message || '加载失败')
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '加载失败')
  } finally {
    detailLoading.value = false
  }
}

const refreshDetail = async () => {
  if (!detail.value.id) return
  const res = await api.get(`/rd-projects/${detail.value.id}`)
  if (res.code === 200) detail.value = res.data
  fetchList()
}

const addMilestone = async () => {
  if (!msForm.name.trim()) return ElMessage.warning('请填写里程碑名称')
  const res = await api.post(`/rd-projects/${detail.value.id}/milestones`, { ...msForm })
  if (res.code === 200) {
    ElMessage.success('已添加')
    msForm.name = ''; msForm.plan_date = ''; msForm.owner = ''
    refreshDetail()
  } else {
    ElMessage.error(res.message || '添加失败')
  }
}

const toggleMilestone = async (row) => {
  const done = row.status !== 'done'
  const payload = { status: done ? 'done' : 'pending' }
  if (done && !row.actual_date) {
    payload.actual_date = new Date().toISOString().slice(0, 10)
  }
  const res = await api.put(`/rd-projects/milestones/${row.id}`, payload)
  if (res.code === 200) refreshDetail()
  else ElMessage.error(res.message || '更新失败')
}

const updateMilestone = async (row) => {
  const res = await api.put(`/rd-projects/milestones/${row.id}`, { actual_date: row.actual_date })
  if (res.code !== 200) ElMessage.error(res.message || '更新失败')
}

const deleteMilestone = (row) => {
  ElMessageBox.confirm(`确认删除里程碑「${row.name}」？`, '提示', { type: 'warning' })
    .then(async () => {
      const res = await api.delete(`/rd-projects/milestones/${row.id}`)
      if (res.code === 200) { ElMessage.success('已删除'); refreshDetail() }
      else ElMessage.error(res.message || '删除失败')
    }).catch(() => {})
}

const addDeliverable = async () => {
  if (!dvForm.name.trim()) return ElMessage.warning('请填写成果物名称')
  const res = await api.post(`/rd-projects/${detail.value.id}/deliverables`, { ...dvForm })
  if (res.code === 200) {
    ElMessage.success('已登记')
    dvForm.name = ''; dvForm.deliver_date = ''
    refreshDetail()
  } else {
    ElMessage.error(res.message || '登记失败')
  }
}

const deleteDeliverable = (row) => {
  ElMessageBox.confirm(`确认删除成果物「${row.name}」？`, '提示', { type: 'warning' })
    .then(async () => {
      const res = await api.delete(`/rd-projects/deliverables/${row.id}`)
      if (res.code === 200) { ElMessage.success('已删除'); refreshDetail() }
      else ElMessage.error(res.message || '删除失败')
    }).catch(() => {})
}

onMounted(() => {
  fetchMeta()
  fetchList()
})
</script>

<style scoped>
.rd-page { padding: 20px; background: #f5f7fa; min-height: 100vh; }

.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.header-title { display: flex; align-items: center; gap: 12px; }
.title-icon { font-size: 30px; }
.header-title h2 { margin: 0; font-size: 20px; color: #1f2d3d; }
.header-title p { margin: 4px 0 0; font-size: 12px; color: #909399; }

.stat-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 14px; }
.stat-card { background: #fff; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.stat-label { font-size: 12px; color: #909399; }
.stat-value { font-size: 22px; font-weight: 600; color: #1f2d3d; margin-top: 6px; }
.stat-value.running { color: #409eff; }
.stat-value.preparing { color: #909399; }
.stat-value.finished { color: #67c23a; }
.stat-value.budget { font-size: 18px; color: #e6a23c; }

.filter-card { background: #fff; border-radius: 8px; padding: 12px 16px; display: flex; gap: 10px; align-items: center; margin-bottom: 14px; }
.table-card { background: #fff; border-radius: 8px; padding: 12px; }
.empty-tip { text-align: center; color: #909399; font-size: 13px; padding: 24px 0; }
.empty-inline { text-align: center; color: #c0c4cc; font-size: 12px; padding: 10px 0; }
.link { color: #409eff; cursor: pointer; }
.link:hover { text-decoration: underline; }

.detail-body { padding: 0 4px 20px; }
.section { margin-top: 20px; }
.section-title { font-size: 14px; font-weight: 600; color: #1f2d3d; margin-bottom: 10px; }
.section-sub { font-size: 12px; color: #909399; font-weight: normal; margin-left: 8px; }
.inline-form { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.pre { white-space: pre-wrap; line-height: 1.6; }
.hint { font-size: 12px; color: #e6a23c; line-height: 1.4; margin-top: 2px; }

.wh-summary { display: flex; gap: 20px; font-size: 13px; color: #606266; margin-bottom: 8px; }
.wh-summary b { color: #303133; }
.wh-summary b.ok { color: #67c23a; }
.wh-summary b.warn { color: #e6a23c; }
.wh-members { display: flex; flex-wrap: wrap; gap: 6px; }
.wh-tag { margin: 0; }

@media (max-width: 1200px) {
  .stat-row { grid-template-columns: repeat(2, 1fr); }
}
</style>
