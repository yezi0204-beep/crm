<template>
  <div class="enterprises-page">
    <!-- 搜索栏 -->
    <el-card class="search-card" shadow="never">
      <div class="search-bar">
        <el-input v-model="keyword" placeholder="搜索企业名称/联系人/简介" clearable style="width:280px"
          @keyup.enter="fetchList" @clear="fetchList" />
        <el-select v-model="filterStatus" placeholder="关系状态" clearable style="width:140px" @change="fetchList">
          <el-option v-for="s in statusOptions" :key="s" :label="s" :value="s" />
        </el-select>
        <el-button type="primary" @click="fetchList">查询</el-button>
        <div class="search-bar-right">
          <el-button type="success" @click="openDialog()">+ 新建企业</el-button>
        </div>
      </div>
    </el-card>

    <!-- 列表 -->
    <el-card shadow="never" style="margin-top:12px;">
      <el-table :data="list" v-loading="loading" border stripe size="small">
        <el-table-column label="企业名称" prop="name" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" @click="openDetail(row)">{{ row.name }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="成立时间" prop="established_date" width="110" />
        <el-table-column label="公司位置" prop="location" min-width="140" show-overflow-tooltip />
        <el-table-column label="人员规模" prop="personnel_size" width="90" />
        <el-table-column label="关系状态" prop="relationship_status" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.relationship_status)" size="small">{{ row.relationship_status || '未接触' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="联系人" prop="contact_person" width="90" />
        <el-table-column label="联系方式" prop="contact_info" width="130" show-overflow-tooltip />
        <el-table-column label="客户" width="60" align="center">
          <template #default="{ row }">
            <el-badge :value="row.customer_count" :hidden="!row.customer_count" type="primary" />
          </template>
        </el-table-column>
        <el-table-column label="商机" width="60" align="center">
          <template #default="{ row }">
            <el-badge :value="row.business_count" :hidden="!row.business_count" type="warning" />
          </template>
        </el-table-column>
        <el-table-column label="合同" width="60" align="center">
          <template #default="{ row }">
            <el-badge :value="row.contract_count" :hidden="!row.contract_count" type="success" />
          </template>
        </el-table-column>
        <el-table-column label="拜访" width="60" align="center">
          <template #default="{ row }">
            <el-badge :value="row.visit_count" :hidden="!row.visit_count" type="primary" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" @click="openDialog(row)">编辑</el-button>
            <el-button text size="small" @click="openLinkVisit(row)">关联拜访</el-button>
            <el-button text size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-bar">
        <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total"
          layout="total, prev, pager, next" @current-change="fetchList" />
      </div>
    </el-card>

    <!-- 新建/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑企业信息' : '新建企业信息'" width="800px"
      :close-on-click-modal="false" :close-on-press-escape="false">
      <el-form :model="form" label-width="120px" size="default">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="企业名称" required>
              <el-input v-model="form.name" placeholder="请输入企业名称" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="成立时间">
              <el-date-picker v-model="form.established_date" type="date" value-format="YYYY-MM-DD"
                placeholder="选择日期" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="公司位置">
              <el-input v-model="form.location" placeholder="请输入公司位置" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="人员规模">
              <el-input v-model="form.personnel_size" placeholder="如: 100-500人" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="注册资本">
              <el-input v-model="form.registered_capital" placeholder="如: 5000万元" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="单位网址">
              <el-input v-model="form.website" placeholder="如: www.example.com" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="联系人">
              <el-input v-model="form.contact_person" placeholder="请输入联系人" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="联系方式">
              <el-input v-model="form.contact_info" placeholder="电话/邮箱" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="关系状态">
              <el-select v-model="form.relationship_status" placeholder="选择关系状态" style="width:100%">
                <el-option v-for="s in statusOptions" :key="s" :label="s" :value="s" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="负责人">
              <el-input v-model="form.owner_id" placeholder="留空则默认为当前用户" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="单位简介">
          <el-input v-model="form.brief" type="textarea" :rows="2" placeholder="请输入单位简介" />
        </el-form-item>
        <el-form-item label="业务范围">
          <el-input v-model="form.business_scope" type="textarea" :rows="2" placeholder="请输入业务范围" />
        </el-form-item>
        <el-form-item label="主要资质">
          <el-input v-model="form.main_qualifications" type="textarea" :rows="2" placeholder="请输入主要资质" />
        </el-form-item>
        <el-form-item label="主要产品和方案">
          <el-input v-model="form.main_products" type="textarea" :rows="2" placeholder="请输入主要产品和方案" />
        </el-form-item>
        <el-form-item label="合作机会点">
          <el-input v-model="form.cooperation_opportunities" type="textarea" :rows="2" placeholder="请输入合作机会点" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" :title="detail?.name || '企业详情'" width="1000px" top="5vh"
      :close-on-click-modal="false" :close-on-press-escape="false">
      <div v-if="detail" class="detail-content">
        <!-- 数据链条摘要 -->
        <div class="summary-cards" v-if="detail.summary">
          <div class="summary-card">
            <div class="summary-num">{{ detail.summary.customer_count }}</div>
            <div class="summary-label">关联客户</div>
          </div>
          <div class="summary-card">
            <div class="summary-num">{{ detail.summary.business_count }}</div>
            <div class="summary-label">商机数</div>
          </div>
          <div class="summary-card">
            <div class="summary-num">{{ detail.summary.contract_count }}</div>
            <div class="summary-label">合同数</div>
          </div>
          <div class="summary-card">
            <div class="summary-num">{{ detail.summary.visit_count }}</div>
            <div class="summary-label">拜访记录</div>
          </div>
          <div class="summary-card" v-if="detail.summary.business_total_amount > 0">
            <div class="summary-num">{{ (detail.summary.business_total_amount / 10000).toFixed(4) }}</div>
            <div class="summary-label">商机总额(万)</div>
          </div>
          <div class="summary-card" v-if="detail.summary.contract_total_amount > 0">
            <div class="summary-num">{{ (detail.summary.contract_total_amount / 10000).toFixed(4) }}</div>
            <div class="summary-label">合同总额(万)</div>
          </div>
        </div>

        <el-collapse v-model="activeCollapse">
          <el-collapse-item title="企业基本信息" name="info">
            <el-descriptions :column="3" border size="small">
              <el-descriptions-item label="企业名称">{{ detail.name }}</el-descriptions-item>
              <el-descriptions-item label="成立时间">{{ detail.established_date || '-' }}</el-descriptions-item>
              <el-descriptions-item label="公司位置">{{ detail.location || '-' }}</el-descriptions-item>
              <el-descriptions-item label="人员规模">{{ detail.personnel_size || '-' }}</el-descriptions-item>
              <el-descriptions-item label="注册资本">{{ detail.registered_capital || '-' }}</el-descriptions-item>
              <el-descriptions-item label="单位网址">
                <el-link v-if="detail.website" :href="'http://' + detail.website.replace(/^https?:\/\//,'')" target="_blank" type="primary">{{ detail.website }}</el-link>
                <span v-else>-</span>
              </el-descriptions-item>
              <el-descriptions-item label="联系人">{{ detail.contact_person || '-' }}</el-descriptions-item>
              <el-descriptions-item label="联系方式">{{ detail.contact_info || '-' }}</el-descriptions-item>
              <el-descriptions-item label="关系状态">
                <el-tag :type="statusTagType(detail.relationship_status)" size="small">{{ detail.relationship_status || '未接触' }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="负责人">{{ detail.owner_name || detail.owner_id || '-' }}</el-descriptions-item>
              <el-descriptions-item label="创建时间" :span="2">{{ detail.created_at }}</el-descriptions-item>
              <el-descriptions-item label="单位简介" :span="3">{{ detail.brief || '-' }}</el-descriptions-item>
              <el-descriptions-item label="业务范围" :span="3">{{ detail.business_scope || '-' }}</el-descriptions-item>
              <el-descriptions-item label="主要资质" :span="3">{{ detail.main_qualifications || '-' }}</el-descriptions-item>
              <el-descriptions-item label="主要产品和方案" :span="3">{{ detail.main_products || '-' }}</el-descriptions-item>
              <el-descriptions-item label="合作机会点" :span="3">{{ detail.cooperation_opportunities || '-' }}</el-descriptions-item>
            </el-descriptions>
          </el-collapse-item>

          <!-- 关联客户 -->
          <el-collapse-item :name="'customers'">
            <template #title>
              <span class="collapse-title">关联客户 ({{ detail.customers?.length || 0 }})</span>
            </template>
            <el-table v-if="detail.customers && detail.customers.length" :data="detail.customers" size="small" border max-height="250">
              <el-table-column label="客户名称" prop="company" min-width="160" show-overflow-tooltip />
              <el-table-column label="联系人" prop="name" width="90" />
              <el-table-column label="电话" prop="phone" width="130" />
              <el-table-column label="等级" prop="level" width="70" />
              <el-table-column label="负责人" prop="owner_id" width="90" />
              <el-table-column label="最后跟进" prop="last_follow" width="110" />
              <el-table-column label="操作" width="80">
                <template #default="{ row }">
                  <el-button text size="small" @click="goTo('/customers')">查看</el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-else description="暂无匹配的客户（系统按企业名称自动匹配客户公司名）" :image-size="50" />
          </el-collapse-item>

          <!-- 关联商机 -->
          <el-collapse-item :name="'business'">
            <template #title>
              <span class="collapse-title">关联商机 ({{ detail.business?.length || 0 }})</span>
            </template>
            <el-table v-if="detail.business && detail.business.length" :data="detail.business" size="small" border max-height="250">
              <el-table-column label="商机标题" prop="title" min-width="160" show-overflow-tooltip />
              <el-table-column label="客户" prop="customer_company" width="140" show-overflow-tooltip />
              <el-table-column label="金额(万)" width="110">
                <template #default="{ row }">{{ ((row.amount || 0) / 10000).toFixed(4) }}</template>
              </el-table-column>
              <el-table-column label="阶段" prop="stage" width="90" />
              <el-table-column label="状态" prop="status" width="80">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">{{ row.status === 'active' ? '进行中' : row.status }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="负责人" prop="owner_id" width="90" />
            </el-table>
            <el-empty v-else description="暂无关联商机（通过匹配客户自动关联）" :image-size="50" />
          </el-collapse-item>

          <!-- 关联合同 -->
          <el-collapse-item :name="'contracts'">
            <template #title>
              <span class="collapse-title">关联合同 ({{ detail.contracts?.length || 0 }})</span>
            </template>
            <el-table v-if="detail.contracts && detail.contracts.length" :data="detail.contracts" size="small" border max-height="250">
              <el-table-column label="合同编号" prop="contract_no" width="140" show-overflow-tooltip />
              <el-table-column label="合同名称" prop="contract_name" min-width="160" show-overflow-tooltip />
              <el-table-column label="客户" prop="customer_company" width="130" show-overflow-tooltip />
              <el-table-column label="合同总额(万)" width="120">
                <template #default="{ row }">{{ ((row.total_amt || 0) / 10000).toFixed(4) }}</template>
              </el-table-column>
              <el-table-column label="已回款(万)" width="110">
                <template #default="{ row }">{{ ((row.paid_amt || 0) / 10000).toFixed(4) }}</template>
              </el-table-column>
              <el-table-column label="状态" prop="status" width="80" />
            </el-table>
            <el-empty v-else description="暂无关联合同（通过匹配客户自动关联）" :image-size="50" />
          </el-collapse-item>

          <!-- 关联拜访记录 -->
          <el-collapse-item :name="'visits'">
            <template #title>
              <span class="collapse-title">关联拜访记录 ({{ detail.visits?.length || 0 }})</span>
              <el-button text size="small" @click.stop="openLinkVisit(detail)" style="margin-left:8px;">+ 手动关联</el-button>
            </template>
            <el-table v-if="detail.visits && detail.visits.length" :data="detail.visits" size="small" border max-height="300">
              <el-table-column label="日期" prop="plan_date" width="110" />
              <el-table-column label="时间" prop="plan_time" width="70" />
              <el-table-column label="拜访人" prop="visitor_name" width="90" />
              <el-table-column label="目的" prop="purpose" show-overflow-tooltip min-width="140" />
              <el-table-column label="状态" prop="status" width="80">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'completed' ? 'success' : 'warning'" size="small">
                    {{ row.status === 'completed' ? '已完成' : '计划中' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="来源" width="70">
                <template #default="{ row }">
                  <el-tag :type="row.link_type === 'manual' ? 'danger' : 'info'" size="small" effect="plain">
                    {{ row.link_type === 'manual' ? '手动' : '自动' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="结果" prop="result" show-overflow-tooltip min-width="140" />
              <el-table-column label="操作" width="80">
                <template #default="{ row }">
                  <el-button v-if="row.link_type === 'manual'" text size="small" type="danger" @click="unlinkVisit(row)">取消关联</el-button>
                  <span v-else>-</span>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-else description="暂无关联拜访记录" :image-size="50" />
          </el-collapse-item>
        </el-collapse>
      </div>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button type="primary" @click="openDialog(detail); detailVisible = false">编辑</el-button>
      </template>
    </el-dialog>

    <!-- 关联拜访记录弹窗 -->
    <el-dialog v-model="linkVisitVisible" title="关联拜访记录" width="700px"
      :close-on-click-modal="false" :close-on-press-escape="false">
      <div v-if="linkEnterprise">
        <p style="margin-bottom:12px;">为 <strong>{{ linkEnterprise.name }}</strong> 关联拜访记录：</p>
        <el-select v-model="selectedVisitId" filterable placeholder="搜索拜访日期/目的/拜访人" style="width:100%"
          :loading="visitLoading">
          <el-option v-for="v in visitOptions" :key="v.id"
            :label="`${v.plan_date} ${v.plan_time || ''} | ${v.visitor_name || v.visitor_id || ''} | ${v.purpose || ''}`"
            :value="v.id" />
        </el-select>
      </div>
      <template #footer>
        <el-button @click="linkVisitVisible = false">取消</el-button>
        <el-button type="primary" :loading="linking" @click="handleLinkVisit">确认关联</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()

const statusOptions = ['未接触', '初步接触', '深入沟通', '合作中', '已合作', '暂停']

const list = ref([])
const loading = ref(false)
const keyword = ref('')
const filterStatus = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

const dialogVisible = ref(false)
const editingId = ref(null)
const form = ref({})
const saving = ref(false)

const detailVisible = ref(false)
const detail = ref(null)
const activeCollapse = ref(['info', 'customers', 'business', 'contracts', 'visits'])

const linkVisitVisible = ref(false)
const linkEnterprise = ref(null)
const visitOptions = ref([])
const visitLoading = ref(false)
const selectedVisitId = ref(null)
const linking = ref(false)

onMounted(() => fetchList())

async function fetchList() {
  loading.value = true
  try {
    const res = await api.get('/enterprises', {
      keyword: keyword.value,
      relationship_status: filterStatus.value,
    })
    if (res.code === 200) {
      list.value = res.data || []
      total.value = list.value.length
    } else {
      ElMessage.error(res.message || '获取列表失败')
    }
  } catch (e) {
    ElMessage.error('获取列表失败')
  } finally {
    loading.value = false
  }
}

function goTo(path) {
  detailVisible.value = false
  router.push(path)
}

function statusTagType(status) {
  const map = {
    '未接触': 'info',
    '初步接触': 'warning',
    '深入沟通': '',
    '合作中': 'success',
    '已合作': 'success',
    '暂停': 'danger',
  }
  return map[status] || 'info'
}

function openDialog(row) {
  if (row) {
    editingId.value = row.id
    form.value = { ...row }
  } else {
    editingId.value = null
    form.value = {
      name: '', established_date: '', location: '', personnel_size: '', brief: '',
      registered_capital: '', business_scope: '', main_qualifications: '', main_products: '',
      relationship_status: '未接触', cooperation_opportunities: '', website: '',
      contact_person: '', contact_info: '', owner_id: '',
    }
  }
  dialogVisible.value = true
}

async function handleSave() {
  if (!form.value.name) {
    ElMessage.warning('请输入企业名称')
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      const res = await api.put(`/enterprises/${editingId.value}`, form.value)
      if (res.code === 200) {
        ElMessage.success('修改成功')
        dialogVisible.value = false
        fetchList()
      } else {
        ElMessage.error(res.message || '修改失败')
      }
    } else {
      const res = await api.post('/enterprises', form.value)
      if (res.code === 200) {
        ElMessage.success('创建成功')
        dialogVisible.value = false
        fetchList()
      } else {
        ElMessage.error(res.message || '创建失败')
      }
    }
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除企业「${row.name}」？`, '提示', { type: 'warning' })
    const res = await api.delete(`/enterprises/${row.id}`)
    if (res.code === 200) {
      ElMessage.success('删除成功')
      fetchList()
    } else {
      ElMessage.error(res.message || '删除失败')
    }
  } catch (e) {
    // cancelled
  }
}

async function openDetail(row) {
  detailVisible.value = true
  detail.value = null
  try {
    const res = await api.get(`/enterprises/${row.id}`)
    if (res.code === 200) {
      detail.value = res.data
    } else {
      ElMessage.error(res.message || '获取详情失败')
    }
  } catch (e) {
    ElMessage.error('获取详情失败')
  }
}

async function openLinkVisit(row) {
  linkEnterprise.value = row
  selectedVisitId.value = null
  linkVisitVisible.value = true
  visitLoading.value = true
  try {
    const res = await api.get('/visits', { page_size: 999 })
    if (res.code === 200) {
      visitOptions.value = res.data || []
    }
  } catch (e) {
    ElMessage.error('获取拜访记录失败')
  } finally {
    visitLoading.value = false
  }
}

async function handleLinkVisit() {
  if (!selectedVisitId.value) {
    ElMessage.warning('请选择拜访记录')
    return
  }
  linking.value = true
  try {
    const res = await api.post(`/enterprises/${linkEnterprise.value.id}/visits`, { visit_id: selectedVisitId.value })
    if (res.code === 200) {
      ElMessage.success('关联成功')
      linkVisitVisible.value = false
      if (detail.value && detail.value.id === linkEnterprise.value.id) {
        openDetail(detail.value)
      }
      fetchList()
    } else {
      ElMessage.error(res.message || '关联失败')
    }
  } catch (e) {
    ElMessage.error('关联失败')
  } finally {
    linking.value = false
  }
}

async function unlinkVisit(visit) {
  try {
    await ElMessageBox.confirm(`取消关联该拜访记录？`, '提示', { type: 'warning' })
    const res = await api.delete(`/enterprises/${detail.value.id}/visits/${visit.id}`)
    if (res.code === 200) {
      ElMessage.success('取消关联成功')
      openDetail(detail.value)
      fetchList()
    } else {
      ElMessage.error(res.message || '取消关联失败')
    }
  } catch (e) {
    // cancelled
  }
}
</script>

<style scoped>
.enterprises-page {
  padding: 16px;
}

.search-card {
  margin-bottom: 0;
}

.search-bar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.search-bar-right {
  margin-left: auto;
}

.pagination-bar {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

.detail-content {
  max-height: 72vh;
  overflow-y: auto;
}

.summary-cards {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.summary-card {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  border-radius: 8px;
  padding: 12px 20px;
  text-align: center;
  min-width: 100px;
}

.summary-num {
  font-size: 22px;
  font-weight: 700;
  line-height: 1.2;
}

.summary-label {
  font-size: 12px;
  opacity: 0.85;
  margin-top: 4px;
}

.collapse-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.visits-section {
  margin-top: 20px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}
</style>
