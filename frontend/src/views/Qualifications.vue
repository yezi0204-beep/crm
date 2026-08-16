<template>
  <div class="qualifications-container">
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">📜 资质信息管理</h2>
        <p class="page-desc">管理人员资质与企业资质，为投标评估提供数据支撑</p>
      </div>
    </div>

    <el-tabs v-model="activeTab" type="border-card">
      <!-- 人员资质 -->
      <el-tab-pane label="👤 人员资质" name="personnel">
        <div class="tab-toolbar">
          <div class="toolbar-left">
            <el-select v-model="personnelFilter.username" placeholder="筛选人员" clearable style="width:160px" @change="fetchPersonnel">
              <el-option v-for="u in userOptions" :key="u.username" :label="u.name" :value="u.username" />
            </el-select>
            <el-select v-model="personnelFilter.qualification_type" placeholder="资质类型" clearable style="width:160px" @change="fetchPersonnel">
              <el-option label="PMP" value="PMP" />
              <el-option label="信息系统项目管理师" value="信息系统项目管理师" />
              <el-option label="系统架构设计师" value="系统架构设计师" />
              <el-option label="软件设计师" value="软件设计师" />
              <el-option label="CISSP" value="CISSP" />
              <el-option label="其他" value="其他" />
            </el-select>
          </div>
          <el-button type="primary" @click="showPersonnelDialog()">
            <span>✚</span><span>新增资质</span>
          </el-button>
        </div>

        <el-table :data="personnelList" v-loading="personnelLoading" stripe>
          <el-table-column prop="name" label="姓名" width="100" />
          <el-table-column prop="username" label="账号" width="120" />
          <el-table-column prop="qualification_type" label="资质类型" width="160" />
          <el-table-column prop="qualification_name" label="资质名称" min-width="160" />
          <el-table-column prop="certificate_no" label="证书编号" width="140" />
          <el-table-column prop="level" label="级别" width="100">
            <template #default="{ row }">
              <el-tag v-if="row.level" size="small">{{ row.level }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="issue_date" label="颁发日期" width="120" />
          <el-table-column prop="expire_date" label="有效期至" width="120" />
          <el-table-column prop="status" label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.status === '有效' ? 'success' : 'info'" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <el-button text size="small" @click="showPersonnelDialog(row)">编辑</el-button>
              <el-button text size="small" type="danger" @click="handleDeletePersonnel(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="pagination-bar">
          <el-pagination v-model:current-page="personnelPage" :page-size="20" :total="personnelTotal" layout="total, prev, pager, next" @current-change="fetchPersonnel" />
        </div>
      </el-tab-pane>

      <!-- 企业资质 -->
      <el-tab-pane label="🏢 企业资质" name="company">
        <div class="tab-toolbar">
          <div class="toolbar-left">
            <el-select v-model="companyFilter.qualification_type" placeholder="资质类型" clearable style="width:160px" @change="fetchCompany">
              <el-option label="ISO9001质量管理体系" value="ISO9001" />
              <el-option label="ISO27001信息安全体系" value="ISO27001" />
              <el-option label="CMMI认证" value="CMMI" />
              <el-option label="高新技术企业" value="高新技术企业" />
              <el-option label="软件企业认证" value="软件企业" />
              <el-option label="系统集成资质" value="系统集成资质" />
              <el-option label="其他" value="其他" />
            </el-select>
          </div>
          <el-button type="primary" @click="showCompanyDialog()">
            <span>✚</span><span>新增资质</span>
          </el-button>
        </div>

        <el-table :data="companyList" v-loading="companyLoading" stripe>
          <el-table-column prop="qualification_type" label="资质类型" width="160" />
          <el-table-column prop="qualification_name" label="资质名称" min-width="180" />
          <el-table-column prop="certificate_no" label="证书编号" width="140" />
          <el-table-column prop="level" label="级别" width="100">
            <template #default="{ row }">
              <el-tag v-if="row.level" size="small" :type="row.level.includes('1') ? 'danger' : row.level.includes('2') ? 'warning' : 'info'">{{ row.level }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="issue_authority" label="颁发机构" width="140" />
          <el-table-column prop="issue_date" label="颁发日期" width="120" />
          <el-table-column prop="expire_date" label="有效期至" width="120" />
          <el-table-column prop="scope" label="范围" min-width="180" />
          <el-table-column prop="status" label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.status === '有效' ? 'success' : 'info'" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <el-button text size="small" @click="showCompanyDialog(row)">编辑</el-button>
              <el-button text size="small" type="danger" @click="handleDeleteCompany(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="pagination-bar">
          <el-pagination v-model:current-page="companyPage" :page-size="20" :total="companyTotal" layout="total, prev, pager, next" @current-change="fetchCompany" />
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 人员资质对话框 -->
    <el-dialog v-model="personnelDialogVisible" :title="editingPersonnel ? '编辑人员资质' : '新增人员资质'" width="550px" :close-on-click-modal="false" :close-on-press-escape="false">
      <el-form :model="personnelForm" label-width="110px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="账号" required>
              <el-select v-model="personnelForm.username" filterable placeholder="选择人员" style="width:100%">
                <el-option v-for="u in userOptions" :key="u.username" :label="u.name + ' (' + u.username + ')'" :value="u.username" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="姓名" required>
              <el-input v-model="personnelForm.name" placeholder="姓名" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="资质类型" required>
          <el-select v-model="personnelForm.qualification_type" style="width:100%">
            <el-option label="PMP" value="PMP" />
            <el-option label="信息系统项目管理师" value="信息系统项目管理师" />
            <el-option label="系统架构设计师" value="系统架构设计师" />
            <el-option label="软件设计师" value="软件设计师" />
            <el-option label="CISSP" value="CISSP" />
            <el-option label="其他" value="其他" />
          </el-select>
        </el-form-item>
        <el-form-item label="资质名称">
          <el-input v-model="personnelForm.qualification_name" placeholder="证书全称" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="证书编号">
              <el-input v-model="personnelForm.certificate_no" placeholder="证书编号" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="级别">
              <el-select v-model="personnelForm.level" placeholder="级别" clearable style="width:100%">
                <el-option label="高级" value="高级" />
                <el-option label="中级" value="中级" />
                <el-option label="初级" value="初级" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="颁发日期">
              <el-date-picker v-model="personnelForm.issue_date" type="date" placeholder="选择日期" value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="有效期至">
              <el-date-picker v-model="personnelForm.expire_date" type="date" placeholder="选择日期" value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="颁发机构">
          <el-input v-model="personnelForm.issue_authority" placeholder="颁发机构" />
        </el-form-item>
        <el-form-item label="专业领域">
          <el-input v-model="personnelForm.specialty" placeholder="如：软件开发、项目管理" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="personnelDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmitPersonnel" :loading="personnelSubmitting">确定</el-button>
      </template>
    </el-dialog>

    <!-- 企业资质对话框 -->
    <el-dialog v-model="companyDialogVisible" :title="editingCompany ? '编辑企业资质' : '新增企业资质'" width="550px" :close-on-click-modal="false" :close-on-press-escape="false">
      <el-form :model="companyForm" label-width="110px">
        <el-form-item label="资质类型" required>
          <el-select v-model="companyForm.qualification_type" style="width:100%">
            <el-option label="ISO9001质量管理体系" value="ISO9001" />
            <el-option label="ISO27001信息安全体系" value="ISO27001" />
            <el-option label="CMMI认证" value="CMMI" />
            <el-option label="高新技术企业" value="高新技术企业" />
            <el-option label="软件企业认证" value="软件企业" />
            <el-option label="系统集成资质" value="系统集成资质" />
            <el-option label="其他" value="其他" />
          </el-select>
        </el-form-item>
        <el-form-item label="资质名称">
          <el-input v-model="companyForm.qualification_name" placeholder="证书全称" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="证书编号">
              <el-input v-model="companyForm.certificate_no" placeholder="证书编号" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="级别">
              <el-select v-model="companyForm.level" placeholder="级别" clearable style="width:100%">
                <el-option label="一级" value="一级" />
                <el-option label="二级" value="二级" />
                <el-option label="三级" value="三级" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="颁发日期">
              <el-date-picker v-model="companyForm.issue_date" type="date" placeholder="选择日期" value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="有效期至">
              <el-date-picker v-model="companyForm.expire_date" type="date" placeholder="选择日期" value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="颁发机构">
          <el-input v-model="companyForm.issue_authority" placeholder="颁发机构" />
        </el-form-item>
        <el-form-item label="范围">
          <el-input v-model="companyForm.scope" type="textarea" :rows="2" placeholder="资质覆盖范围" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="companyDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmitCompany" :loading="companySubmitting">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const activeTab = ref('personnel')

// ===== 人员资质 =====
const personnelLoading = ref(false)
const personnelList = ref([])
const personnelTotal = ref(0)
const personnelPage = ref(1)
const personnelFilter = reactive({ username: '', qualification_type: '' })
const userOptions = ref([])

const personnelDialogVisible = ref(false)
const editingPersonnel = ref(null)
const personnelSubmitting = ref(false)
const personnelForm = reactive({
  username: '', name: '', qualification_type: 'PMP', qualification_name: '',
  certificate_no: '', level: '', issue_date: '', expire_date: '',
  issue_authority: '', specialty: ''
})

async function fetchPersonnel() {
  personnelLoading.value = true
  try {
    const params = {
      page: personnelPage.value,
      per_page: 20,
      username: personnelFilter.username,
      qualification_type: personnelFilter.qualification_type
    }
    const res = await api.get('/knowledge/personnel-qualifications', params)
    if (res.code === 200) {
      personnelList.value = res.data.items
      personnelTotal.value = res.data.total
    }
  } catch (e) {
    ElMessage.error('获取人员资质失败')
  } finally {
    personnelLoading.value = false
  }
}

async function fetchUserOptions() {
  try {
    const res = await api.get('/users')
    if (res.code === 200) {
      // 后端 /api/users 返回 { code:200, data: [用户数组] }，data 直接是数组
      const users = Array.isArray(res.data) ? res.data : (res.data?.users || [])
      userOptions.value = users.map(u => ({ username: u.username, name: u.name || u.username }))
    }
  } catch (e) { /* ignore */ }
}

function showPersonnelDialog(row) {
  editingPersonnel.value = row || null
  if (row) {
    Object.assign(personnelForm, {
      username: row.username, name: row.name,
      qualification_type: row.qualification_type,
      qualification_name: row.qualification_name || '',
      certificate_no: row.certificate_no || '',
      level: row.level || '',
      issue_date: row.issue_date || '',
      expire_date: row.expire_date || '',
      issue_authority: row.issue_authority || '',
      specialty: row.specialty || ''
    })
  } else {
    Object.assign(personnelForm, {
      username: '', name: '', qualification_type: 'PMP', qualification_name: '',
      certificate_no: '', level: '', issue_date: '', expire_date: '',
      issue_authority: '', specialty: ''
    })
  }
  personnelDialogVisible.value = true
}

async function handleSubmitPersonnel() {
  if (!personnelForm.username || !personnelForm.name) {
    ElMessage.warning('请填写完整信息')
    return
  }
  personnelSubmitting.value = true
  try {
    if (editingPersonnel.value) {
      const res = await api.put(`/knowledge/personnel-qualifications/${editingPersonnel.value.id}`, personnelForm)
      if (res.code === 200) { ElMessage.success('更新成功'); personnelDialogVisible.value = false; fetchPersonnel() }
      else ElMessage.error(res.message)
    } else {
      const res = await api.post('/knowledge/personnel-qualifications', personnelForm)
      if (res.code === 200) { ElMessage.success('创建成功'); personnelDialogVisible.value = false; fetchPersonnel() }
      else ElMessage.error(res.message)
    }
  } catch (e) { ElMessage.error('操作失败') }
  finally { personnelSubmitting.value = false }
}

async function handleDeletePersonnel(row) {
  try {
    await ElMessageBox.confirm(`确认删除 ${row.name} 的资质记录？`, '提示', { type: 'warning' })
    const res = await api.delete(`/knowledge/personnel-qualifications/${row.id}`)
    if (res.code === 200) { ElMessage.success('删除成功'); fetchPersonnel() }
    else ElMessage.error(res.message)
  } catch (e) { /* cancelled */ }
}

// ===== 企业资质 =====
const companyLoading = ref(false)
const companyList = ref([])
const companyTotal = ref(0)
const companyPage = ref(1)
const companyFilter = reactive({ qualification_type: '' })

const companyDialogVisible = ref(false)
const editingCompany = ref(null)
const companySubmitting = ref(false)
const companyForm = reactive({
  qualification_type: 'ISO9001', qualification_name: '', certificate_no: '',
  level: '', issue_date: '', expire_date: '', issue_authority: '', scope: ''
})

async function fetchCompany() {
  companyLoading.value = true
  try {
    const params = {
      page: companyPage.value,
      per_page: 20,
      qualification_type: companyFilter.qualification_type
    }
    const res = await api.get('/knowledge/company-qualifications', params)
    if (res.code === 200) {
      companyList.value = res.data.items
      companyTotal.value = res.data.total
    }
  } catch (e) {
    ElMessage.error('获取企业资质失败')
  } finally {
    companyLoading.value = false
  }
}

function showCompanyDialog(row) {
  editingCompany.value = row || null
  if (row) {
    Object.assign(companyForm, {
      qualification_type: row.qualification_type,
      qualification_name: row.qualification_name || '',
      certificate_no: row.certificate_no || '',
      level: row.level || '',
      issue_date: row.issue_date || '',
      expire_date: row.expire_date || '',
      issue_authority: row.issue_authority || '',
      scope: row.scope || ''
    })
  } else {
    Object.assign(companyForm, {
      qualification_type: 'ISO9001', qualification_name: '', certificate_no: '',
      level: '', issue_date: '', expire_date: '', issue_authority: '', scope: ''
    })
  }
  companyDialogVisible.value = true
}

async function handleSubmitCompany() {
  if (!companyForm.qualification_type) {
    ElMessage.warning('请选择资质类型')
    return
  }
  companySubmitting.value = true
  try {
    if (editingCompany.value) {
      const res = await api.put(`/knowledge/company-qualifications/${editingCompany.value.id}`, companyForm)
      if (res.code === 200) { ElMessage.success('更新成功'); companyDialogVisible.value = false; fetchCompany() }
      else ElMessage.error(res.message)
    } else {
      const res = await api.post('/knowledge/company-qualifications', companyForm)
      if (res.code === 200) { ElMessage.success('创建成功'); companyDialogVisible.value = false; fetchCompany() }
      else ElMessage.error(res.message)
    }
  } catch (e) { ElMessage.error('操作失败') }
  finally { companySubmitting.value = false }
}

async function handleDeleteCompany(row) {
  try {
    await ElMessageBox.confirm(`确认删除资质「${row.qualification_name || row.qualification_type}」？`, '提示', { type: 'warning' })
    const res = await api.delete(`/knowledge/company-qualifications/${row.id}`)
    if (res.code === 200) { ElMessage.success('删除成功'); fetchCompany() }
    else ElMessage.error(res.message)
  } catch (e) { /* cancelled */ }
}

onMounted(() => {
  fetchPersonnel()
  fetchCompany()
  fetchUserOptions()
})
</script>

<style scoped>
.qualifications-container {
  padding: 20px;
}

.page-header {
  margin-bottom: 20px;
}

.page-title {
  font-size: 22px;
  margin: 0 0 8px 0;
  color: #2d3748;
}

.page-desc {
  color: #718096;
  margin: 0;
}

.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.toolbar-left {
  display: flex;
  gap: 12px;
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>