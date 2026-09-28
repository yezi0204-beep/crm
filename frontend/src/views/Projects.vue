<template>
  <div class="projects-page">
    <div class="page-header">
      <h2>📋 项目分配</h2>
      <div class="header-actions">
        <el-button v-if="activeTab === 'business'" type="primary" @click="handleAdd">新建项目</el-button>
        <el-button type="success" @click="handleAssign()">分配资源</el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <el-tab-pane label="商机项目" name="business">
        <el-card>
          <el-table :data="projectsData" stripe max-height="70vh" v-loading="loading">
            <el-table-column prop="project_name" label="项目名称" sortable min-width="180" show-overflow-tooltip />
            <el-table-column prop="customer_name" label="客户名称" sortable width="140" show-overflow-tooltip />
            <el-table-column prop="stage" label="阶段" sortable width="100">
              <template #default="scope">
                <el-tag size="small" :type="getStageType(scope.row.stage)">{{ scope.row.stage || '-' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="amount" label="金额(元)" sortable width="120" align="right">
              <template #default="scope">
                {{ formatAmount(scope.row.amount) }}
              </template>
            </el-table-column>
            <el-table-column prop="progress" label="进度" sortable width="110">
              <template #default="scope">
                <el-progress :percentage="scope.row.progress" :color="getProgressColor(scope.row.progress)" />
              </template>
            </el-table-column>
            <el-table-column prop="owner_name" label="负责人" sortable width="90" />
            <el-table-column prop="manager" label="项目经理" sortable width="100" />
            <el-table-column label="团队成员" min-width="160" show-overflow-tooltip>
              <template #default="scope">
                <el-tag v-for="m in (scope.row.team_members || [])" :key="m" size="small" style="margin-right:4px;margin-bottom:2px">{{ m }}</el-tag>
                <span v-if="!scope.row.team_members || !scope.row.team_members.length" style="color:#bbb">-</span>
              </template>
            </el-table-column>
            <el-table-column prop="end_date" label="预计完成" sortable width="110" />
            <el-table-column prop="rd_hours" label="研发工时(小时)" width="140" align="right" sortable>
              <template #default="scope">
                <div>
                  <span style="color:#4ecdc4;font-weight:600">{{ scope.row.approved_hours }}</span>
                  <span v-if="scope.row.pending_hours > 0" style="color:#e6a23c;margin-left:6px">(待审{{ scope.row.pending_hours }})</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="280" fixed="right">
              <template #default="scope">
                <el-button size="small" @click="handleViewHours(scope.row)">工时明细</el-button>
                <el-button size="small" type="primary" @click="handleAssign(scope.row, 'business')">分配</el-button>
                <el-button size="small" @click="handleEdit(scope.row)">编辑</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="合同项目" name="contract">
        <el-card>
          <el-table :data="contractsData" stripe max-height="70vh" v-loading="contractLoading">
            <el-table-column prop="contract_name" label="合同名称" sortable min-width="200" show-overflow-tooltip />
            <el-table-column prop="customer_name" label="客户名称" sortable width="150" show-overflow-tooltip />
            <el-table-column prop="contract_no" label="合同编号" sortable width="140" show-overflow-tooltip />
            <el-table-column prop="total_amt" label="合同金额(元)" sortable width="130" align="right">
              <template #default="scope">
                {{ formatAmount(scope.row.total_amt) }}
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" sortable width="90">
              <template #default="scope">
                <el-tag size="small" :type="getContractStatusType(scope.row.status)">{{ scope.row.status || '-' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="owner_name" label="负责人" sortable width="90" />
            <el-table-column label="团队成员" min-width="160" show-overflow-tooltip>
              <template #default="scope">
                <el-tag v-for="m in (scope.row.team_members || [])" :key="m" size="small" style="margin-right:4px;margin-bottom:2px">{{ m }}</el-tag>
                <span v-if="!scope.row.team_members || !scope.row.team_members.length" style="color:#bbb">-</span>
              </template>
            </el-table-column>
            <el-table-column prop="sign_date" label="签订日期" sortable width="110" />
            <el-table-column label="研发工时(小时)" width="140" align="right" sortable>
              <template #default="scope">
                <div>
                  <span style="color:#4ecdc4;font-weight:600">{{ scope.row.approved_hours }}</span>
                  <span v-if="scope.row.pending_hours > 0" style="color:#e6a23c;margin-left:6px">(待审{{ scope.row.pending_hours }})</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="180" fixed="right">
              <template #default="scope">
                <el-button size="small" @click="handleViewHours(scope.row, 'contract')">工时明细</el-button>
                <el-button size="small" type="primary" @click="handleAssign(scope.row, 'contract')">分配</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!contractLoading && !contractsData.length" description="暂无合同数据" />
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 项目研发工时明细抽屉 -->
    <el-drawer v-model="drawerVisible" :title="'研发工时明细 - ' + (currentProject?.project_name || currentProject?.contract_name || '')" size="60%">
      <div v-if="currentProject" class="drawer-content" v-loading="detailLoading">
        <el-descriptions :column="3" border size="small" style="margin-bottom:16px">
          <el-descriptions-item label="客户">{{ currentProject.customer_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="项目经理">{{ currentProject.manager || '-' }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ currentProject.status }}</el-descriptions-item>
        </el-descriptions>

        <el-row :gutter="16" style="margin-bottom:16px">
          <el-col :span="6">
            <el-card shadow="never">
              <div class="sum-card approved">
                <div class="sum-val">{{ detail.summary.total_approved }}</div>
                <div class="sum-lbl">已通过工时</div>
              </div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="never">
              <div class="sum-card pending">
                <div class="sum-val">{{ detail.summary.total_pending }}</div>
                <div class="sum-lbl">待审核工时</div>
              </div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="never">
              <div class="sum-card rejected">
                <div class="sum-val">{{ detail.summary.total_rejected }}</div>
                <div class="sum-lbl">已退回工时</div>
              </div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="never">
              <div class="sum-card count">
                <div class="sum-val">{{ detail.summary.entry_count }}</div>
                <div class="sum-lbl">填报总条数</div>
              </div>
            </el-card>
          </el-col>
        </el-row>

        <el-card shadow="never" style="margin-bottom:16px">
          <template #header><span>按人员汇总（已通过）</span></template>
          <el-table :data="detail.user_summary" stripe size="small">
            <el-table-column prop="user_name" label="研发人员" />
            <el-table-column prop="hours" label="已通过工时(小时)" align="right" />
          </el-table>
          <el-empty v-if="!detail.user_summary.length" description="暂无研发工时数据" :image-size="60" />
        </el-card>

        <el-card shadow="never">
          <template #header><span>工时填报明细</span></template>
          <el-table :data="detail.items" stripe size="small" max-height="400">
            <el-table-column prop="user_name" label="填报人" width="90" />
            <el-table-column prop="date" label="日期" width="100" />
            <el-table-column prop="hours" label="工时" width="70" align="right" />
            <el-table-column prop="description" label="工作事项" min-width="180" show-overflow-tooltip />
            <el-table-column prop="status" label="状态" width="80">
              <template #default="scope">
                <el-tag :type="statusType(scope.row.status)" size="small">{{ statusText(scope.row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="reject_reason" label="退回原因" min-width="120" show-overflow-tooltip />
          </el-table>
          <el-empty v-if="!detail.items.length" description="暂无工时记录" :image-size="60" />
        </el-card>
      </div>
    </el-drawer>

    <!-- 项目成员分配对话框 -->
    <el-dialog v-model="assignVisible" title="项目成员分配" width="640px" @open="onAssignOpen">
      <el-form label-width="90px">
        <el-form-item label="项目类型">
          <el-radio-group v-model="assignRefType" :disabled="!!assignPreselectId" @change="onAssignTypeChange">
            <el-radio label="business">商机</el-radio>
            <el-radio label="contract">合同</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="项目">
          <el-select v-model="assignRefId" placeholder="选择项目" filterable style="width:100%" :disabled="!!assignPreselectId" @change="loadAssignments">
            <el-option v-for="p in assignProjectOptions" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>

        <el-form-item label="添加成员">
          <el-select v-model="newMemberIds" multiple filterable placeholder="从人员列表中选择（可多选）" style="width:100%">
            <el-option v-for="u in availableUsers" :key="u.username" :label="`${u.name}（${u.department || u.role || ''}）`" :value="u.username" />
          </el-select>
          <div style="margin-top:8px">
            <el-button type="primary" size="small" :disabled="!assignRefId || !newMemberIds.length" @click="addMembers">添加到项目</el-button>
          </div>
        </el-form-item>

        <el-form-item label="已分配成员">
          <el-table :data="assignedMembers" stripe size="small" style="width:100%" v-loading="assignLoading">
            <el-table-column prop="user_name" label="姓名" width="100" />
            <el-table-column prop="role" label="角色" width="100" />
            <el-table-column prop="department" label="部门" min-width="120" />
            <el-table-column label="操作" width="80" align="center">
              <template #default="scope">
                <el-button size="small" type="danger" link @click="removeMember(scope.row)">移除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!assignLoading && !assignedMembers.length" description="暂无分配成员" :image-size="60" />
        </el-form-item>
      </el-form>
    </el-dialog>

    <!-- 新建/编辑项目对话框 -->
    <el-dialog v-model="formVisible" :title="form.id ? '编辑项目' : '新建项目'" width="560px" @open="onFormOpen">
      <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
        <el-form-item label="项目名称" prop="title">
          <el-input v-model="form.title" placeholder="请输入项目名称" />
        </el-form-item>
        <el-form-item label="客户" prop="cust_id">
          <el-select v-model="form.cust_id" placeholder="选择客户" filterable style="width:100%">
            <el-option v-for="c in customerList" :key="c.id" :label="c.company || c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="金额(元)" prop="amount">
              <el-input-number v-model="form.amount" :min="0" :step="1000" :precision="2" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="落实概率">
              <el-select v-model="form.probability" placeholder="选择概率" style="width:100%">
                <el-option label="0%" :value="0" />
                <el-option label="20%" :value="20" />
                <el-option label="40%" :value="40" />
                <el-option label="60%" :value="60" />
                <el-option label="80%" :value="80" />
                <el-option label="90%" :value="90" />
                <el-option label="100%" :value="100" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="阶段" prop="stage">
              <el-select v-model="form.stage" placeholder="选择阶段" style="width:100%">
                <el-option v-for="s in stageOptions" :key="s" :label="s" :value="s" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="预计完成">
              <el-date-picker v-model="form.predict_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="负责人">
              <el-select v-model="form.owner_id" placeholder="选择负责人" filterable style="width:100%">
                <el-option v-for="u in userList" :key="u.username" :label="u.name" :value="u.username" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="项目经理">
              <el-select v-model="form.project_manager" placeholder="选择项目经理" filterable style="width:100%">
                <el-option v-for="u in userList" :key="u.username" :label="u.name" :value="u.username" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注">
          <el-input v-model="form.note" type="textarea" :rows="2" placeholder="项目备注" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted } from 'vue'
import api from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const projectsData = ref([])
const loading = ref(false)
const contractsData = ref([])
const contractLoading = ref(false)
const activeTab = ref('business')

const drawerVisible = ref(false)
const detailLoading = ref(false)
const currentProject = ref(null)
const detail = ref({ summary: {}, user_summary: [], items: [] })

// 项目成员分配
const assignVisible = ref(false)
const assignLoading = ref(false)
const assignRefId = ref(null)
const assignRefType = ref('business')
const assignPreselectId = ref(null)
const assignedMembers = ref([])
const allUsers = ref([])
const newMemberIds = ref([])

const availableUsers = computed(() => {
  const assigned = new Set(assignedMembers.value.map(m => m.user_id))
  return allUsers.value.filter(u => !assigned.has(u.username) && u.status === '在职')
})

const assignProjectOptions = computed(() => {
  if (assignRefType.value === 'contract') {
    return contractsData.value.map(c => ({ id: c.id, name: c.contract_name }))
  }
  return projectsData.value.map(p => ({ id: p.id, name: p.project_name }))
})

// 新建/编辑项目
const formVisible = ref(false)
const formRef = ref(null)
const form = reactive({
  id: null, title: '', cust_id: null, amount: 0, probability: 0,
  stage: '', predict_date: '', owner_id: '', project_manager: '', note: '',
})
const rules = {
  title: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
  cust_id: [{ required: true, message: '请选择客户', trigger: 'change' }],
  amount: [{ required: true, message: '请输入金额', trigger: 'blur' }],
  stage: [{ required: true, message: '请选择阶段', trigger: 'change' }],
}
const customerList = ref([])
const userList = ref([])
const stageOptions = ['需求确认', '方案报价', '商务谈判', '合同签署', '项目启动', '实施中', '已完成']

const fetchProjectsData = async () => {
  loading.value = true
  try {
    const [projRes, hoursRes] = await Promise.all([
      api.get('/projects'),
      api.get('/work-hours/projects-summary'),
    ])
    if (projRes.code === 200) {
      const hoursMap = {}
      if (hoursRes.code === 200) {
        hoursRes.data.forEach(h => { hoursMap[h.business_id] = h })
      }
      projectsData.value = projRes.data.map(p => {
        const h = hoursMap[p.id] || {}
        return { ...p, approved_hours: h.approved_hours || 0, pending_hours: h.pending_hours || 0 }
      })
    }
  } finally {
    loading.value = false
  }
}

const fetchContractsData = async () => {
  contractLoading.value = true
  try {
    const [ctrRes, hoursRes] = await Promise.all([
      api.get('/contracts'),
      api.get('/work-hours/projects-summary?ref_type=contract'),
    ])
    if (ctrRes.code === 200) {
      const hoursMap = {}
      if (hoursRes.code === 200) {
        hoursRes.data.forEach(h => { hoursMap[h.contract_id] = h })
      }
      contractsData.value = ctrRes.data.map(c => {
        const h = hoursMap[c.id] || {}
        return { ...c, approved_hours: h.approved_hours || 0, pending_hours: h.pending_hours || 0 }
      })
    }
  } finally {
    contractLoading.value = false
  }
}

const onTabChange = (name) => {
  if (name === 'contract' && !contractsData.value.length) {
    fetchContractsData()
  }
}

const resetForm = () => {
  Object.assign(form, {
    id: null, title: '', cust_id: null, amount: 0, probability: 0,
    stage: '', predict_date: '', owner_id: '', project_manager: '', note: '',
  })
}

const handleAdd = () => {
  resetForm()
  formVisible.value = true
}

const handleEdit = (row) => {
  Object.assign(form, {
    id: row.id,
    title: row.project_name,
    cust_id: row.cust_id || null,
    amount: row.amount || 0,
    probability: row.probability || 0,
    stage: row.stage || '',
    predict_date: row.end_date || '',
    owner_id: row.owner_id || '',
    project_manager: row.manager || '',
    note: row.note || '',
  })
  formVisible.value = true
}

const onFormOpen = async () => {
  if (!customerList.value.length) {
    const cRes = await api.get('/customers')
    if (cRes.code === 200) customerList.value = cRes.data || []
  }
  if (!userList.value.length) {
    const uRes = await api.get('/users')
    if (uRes.code === 200) userList.value = uRes.data || []
  }
}

const submitForm = async () => {
  await formRef.value.validate()
  const payload = {
    title: form.title,
    cust_id: form.cust_id,
    amount: form.amount,
    probability: form.probability,
    stage: form.stage,
    predict_date: form.predict_date,
    owner_id: form.owner_id,
    project_manager: form.project_manager,
    note: form.note,
  }
  let res
  if (form.id) {
    res = await api.put(`/business/${form.id}`, payload)
  } else {
    res = await api.post('/business', payload)
  }
  if (res.code === 200) {
    ElMessage.success(form.id ? '项目已更新' : '项目已创建')
    formVisible.value = false
    fetchProjectsData()
  } else {
    ElMessage.error(res.message || '保存失败')
  }
}

// 打开分配对话框：行按钮传入 row 和 ref_type，顶部按钮不传
const handleAssign = (row, refType) => {
  assignRefType.value = refType || activeTab.value
  assignPreselectId.value = row ? row.id : null
  assignRefId.value = row ? row.id : null
  assignedMembers.value = []
  newMemberIds.value = []
  assignVisible.value = true
}

const onAssignTypeChange = () => {
  assignRefId.value = null
  assignedMembers.value = []
  newMemberIds.value = []
}

const onAssignOpen = async () => {
  // 加载全量用户列表（用于下拉选择）
  if (!allUsers.value.length) {
    const res = await api.get('/users')
    if (res.code === 200) allUsers.value = res.data || []
  }
  // 若选了合同类型但合同列表未加载，先加载
  if (assignRefType.value === 'contract' && !contractsData.value.length) {
    await fetchContractsData()
  }
  if (assignRefId.value) loadAssignments()
}

const loadAssignments = async () => {
  if (!assignRefId.value) {
    assignedMembers.value = []
    return
  }
  assignLoading.value = true
  try {
    const res = await api.get(`/work-hours/projects/${assignRefId.value}/assignments?ref_type=${assignRefType.value}`)
    if (res.code === 200) assignedMembers.value = res.data || []
  } finally {
    assignLoading.value = false
  }
}

const addMembers = async () => {
  if (!assignRefId.value || !newMemberIds.value.length) return
  const res = await api.post(`/work-hours/projects/${assignRefId.value}/assignments`, {
    ref_type: assignRefType.value,
    user_ids: newMemberIds.value,
  })
  if (res.code === 200) {
    ElMessage.success(res.message || '分配成功')
    newMemberIds.value = []
    loadAssignments()
    // 刷新列表以更新团队成员展示
    if (assignRefType.value === 'contract') fetchContractsData()
    else fetchProjectsData()
  } else {
    ElMessage.error(res.message || '分配失败')
  }
}

const removeMember = (row) => {
  ElMessageBox.confirm(`确认将 ${row.user_name || row.user_id} 移出该项目？`, '提示', { type: 'warning' })
    .then(async () => {
      const res = await api.delete(`/work-hours/projects/${assignRefId.value}/assignments/${row.user_id}?ref_type=${assignRefType.value}`)
      if (res.code === 200) {
        ElMessage.success('已移除')
        loadAssignments()
        if (assignRefType.value === 'contract') fetchContractsData()
        else fetchProjectsData()
      } else {
        ElMessage.error(res.message || '移除失败')
      }
    })
    .catch(() => {})
}

const handleViewHours = async (row, refType) => {
  currentProject.value = row
  drawerVisible.value = true
  detailLoading.value = true
  try {
    const url = refType === 'contract'
      ? `/work-hours/contract/${row.id}`
      : `/work-hours/project/${row.id}`
    const res = await api.get(url)
    if (res.code === 200) {
      detail.value = res.data
    }
  } finally {
    detailLoading.value = false
  }
}

const getProgressColor = (progress) => {
  if (progress >= 80) return '#4ecdc4'
  if (progress >= 50) return '#fac858'
  return '#ff6b6b'
}
const getStageType = (stage) => {
  const types = { '已完成': 'success', '实施中': 'primary', '合同签署': 'success', '商务谈判': 'warning', '方案报价': 'info', '需求确认': 'info', '项目启动': 'primary' }
  return types[stage] || 'info'
}
const getContractStatusType = (status) => {
  const types = { '执行中': 'primary', '已完成': 'success', '已终止': 'danger', '待签订': 'warning', '已签订': 'info' }
  return types[status] || 'info'
}
const formatAmount = (amt) => {
  if (!amt && amt !== 0) return '-'
  return Number(amt).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
const getStatusType = (status) => {
  const types = { '进行中': 'success', '待启动': 'warning', '已完成': 'info', '已暂停': 'danger' }
  return types[status] || 'info'
}
const statusType = (s) => ({ pending: 'warning', approved: 'success', rejected: 'danger' }[s] || 'info')
const statusText = (s) => ({ pending: '待审核', approved: '已通过', rejected: '已退回' }[s] || s)

onMounted(() => fetchProjectsData())
</script>

<style scoped>
.projects-page { display: flex; flex-direction: column; gap: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; }
.page-header h2 { margin: 0; font-size: 20px; color: #333; }
.header-actions { display: flex; gap: 12px; }
.drawer-content { padding: 0 4px; }
.sum-card { text-align: center; padding: 12px 0; }
.sum-card .sum-val { font-size: 26px; font-weight: bold; }
.sum-card .sum-lbl { font-size: 13px; color: #999; margin-top: 4px; }
.sum-card.approved .sum-val { color: #67c23a; }
.sum-card.pending .sum-val { color: #e6a23c; }
.sum-card.rejected .sum-val { color: #f56c6c; }
.sum-card.count .sum-val { color: #409eff; }
</style>
