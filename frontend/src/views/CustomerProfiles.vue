<template>
  <div style="padding:16px">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
      <el-input v-model="search" placeholder="搜索客户名称/行业/地区" clearable style="width:300px" @keyup.enter="loadList" />
      <el-button type="primary" @click="loadList">搜索</el-button>
      <el-button type="success" :loading="analyzing" @click="analyzeAll">一键分析</el-button>
      <el-button type="danger" :loading="deleting" :disabled="!selection.length" @click="batchDelete">
        批量删除{{ selection.length ? `(${selection.length})` : '' }}
      </el-button>
    </div>

    <el-table :data="list" v-loading="loading" border @selection-change="rows => selection = rows">
      <el-table-column type="selection" width="45" />
      <el-table-column prop="buyer" label="采购单位" min-width="200" show-overflow-tooltip />
      <el-table-column prop="region" label="地区" width="100" />
      <el-table-column prop="industry" label="行业/项目类型" min-width="150" show-overflow-tooltip />
      <el-table-column prop="total_procurements" label="采购次数" width="90" sortable />
      <el-table-column label="总预算(万)" width="110" sortable :sort-by="'total_budget'">
        <template #default="{row}">{{ row.total_budget?.toFixed(2) || '0.00' }}</template>
      </el-table-column>
      <el-table-column label="平均评分" width="100">
        <template #default="{row}">
          <el-tag :type="row.avg_score >= 50 ? 'warning' : 'info'" size="small">{{ row.avg_score?.toFixed(1) || 0 }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最高评分" width="100">
        <template #default="{row}">
          <el-tag :type="row.max_score >= 60 ? 'danger' : ''" size="small">{{ row.max_score || 0 }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="latest_date" label="最近采购" width="110" />
      <el-table-column label="操作" width="120">
        <template #default="{row}">
          <el-button size="small" @click="viewDetail(row)">详情</el-button>
          <el-button size="small" type="danger" text :loading="deletingId===row.id" @click="deleteOne(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination v-if="total > 0" :total="total" :page-size="perPage" v-model:current-page="page"
                   layout="total, prev, pager, next" style="margin-top:12px" @current-change="loadList" />

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" title="客户画像详情" width="800px" top="5vh">
      <div v-if="detail" style="line-height:2">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
          <h3 style="margin:0">{{ detail.buyer }}</h3>
          <el-tag v-if="crmLink" type="success" size="small">已入CRM · 负责人：{{ crmLink.owner_name || '未分配' }}</el-tag>
          <el-tag v-else type="info" size="small">潜在客户（未入CRM）</el-tag>
          <el-button v-if="crmLink" size="small" type="primary" text @click="goToCrm">前往客户管理 →</el-button>
        </div>
        <p style="margin:0 0 8px;color:#909399;font-size:13px">
          本画像基于情报库采购记录的AI分析；CRM客户档案的销售过程数据（跟进/商机/合同/拜访）请见客户管理页。
        </p>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="地区">{{ detail.region || '-' }}</el-descriptions-item>
          <el-descriptions-item label="行业">{{ detail.industry || '-' }}</el-descriptions-item>
          <el-descriptions-item label="采购次数">{{ detail.total_procurements }}</el-descriptions-item>
          <el-descriptions-item label="总预算">{{ (detail.total_budget || 0).toFixed(2) }}万</el-descriptions-item>
          <el-descriptions-item label="平均预算">{{ (detail.avg_budget || 0).toFixed(2) }}万</el-descriptions-item>
          <el-descriptions-item label="平均评分">{{ (detail.avg_score || 0).toFixed(1) }}</el-descriptions-item>
          <el-descriptions-item label="最高评分">{{ detail.max_score }}</el-descriptions-item>
          <el-descriptions-item label="最近采购">{{ detail.latest_date || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div v-if="detail.competitors?.length" style="margin-top:12px">
          <strong>竞争对手：</strong>
          <el-tag v-for="c in detail.competitors" :key="c" style="margin:2px" size="small">{{ c }}</el-tag>
        </div>

        <div v-if="detail.procurement_methods?.length" style="margin-top:8px">
          <strong>采购方式：</strong>
          <el-tag v-for="m in detail.procurement_methods" :key="m" type="info" style="margin:2px" size="small">{{ m }}</el-tag>
        </div>

        <div v-if="detail.project_types?.length" style="margin-top:8px">
          <strong>项目类型：</strong>
          <el-tag v-for="t in detail.project_types" :key="t" type="success" style="margin:2px" size="small">{{ t }}</el-tag>
        </div>

        <div v-if="detail.timeline?.length" style="margin-top:12px">
          <strong>采购时间线：</strong>
          <el-timeline style="margin-top:8px">
            <el-timeline-item v-for="(t, i) in detail.timeline" :key="i" :timestamp="t.date" placement="top">
              <div>
                <el-tag :type="t.score >= 60 ? 'danger' : t.score >= 40 ? 'warning' : 'info'" size="small">{{ t.score }}分</el-tag>
                {{ t.title }}
              </div>
              <div style="font-size:13px;color:#909399">预算:{{ t.budget }} 截止:{{ t.deadline }} 状态:{{ t.status }}</div>
            </el-timeline-item>
          </el-timeline>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const router = useRouter()
const crmLink = ref(null)

function goToCrm() {
  if (crmLink.value?.company) {
    router.push({ path: '/customers', query: { keyword: crmLink.value.company } })
  }
}

const list = ref([])
const total = ref(0)
const page = ref(1)
const perPage = ref(20)
const search = ref('')
const loading = ref(false)
const analyzing = ref(false)
const detailVisible = ref(false)
const detail = ref(null)
const selection = ref([])
const deleting = ref(false)
const deletingId = ref(null)

async function deleteOne(row) {
  try {
    await ElMessageBox.confirm(`确定删除客户「${row.buyer}」的画像？下次一键分析会重新生成`, '删除画像', { type: 'warning' })
  } catch { return }
  deletingId.value = row.id
  try {
    const res = await api.delete(`/cockpit/customers/${row.id}`)
    if (res && res.code === 200) {
      ElMessage.success(res.message || '已删除')
      selection.value = []
      loadList()
    } else {
      ElMessage.error((res && res.message) || '删除失败')
    }
  } catch (e) {
    ElMessage.error('删除失败：' + (e.response?.data?.message || e.message))
  } finally {
    deletingId.value = null
  }
}

async function batchDelete() {
  if (!selection.value.length) return
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selection.value.length} 条客户画像？下次一键分析会重新生成`, '批量删除', { type: 'warning' })
  } catch { return }
  deleting.value = true
  try {
    const res = await api.post('/cockpit/customers/batch-delete', { ids: selection.value.map(r => r.id) })
    if (res && res.code === 200) {
      ElMessage.success(res.message || '删除成功')
      selection.value = []
      loadList()
    } else {
      ElMessage.error((res && res.message) || '删除失败')
    }
  } catch (e) {
    ElMessage.error('批量删除失败：' + (e.response?.data?.message || e.message))
  } finally {
    deleting.value = false
  }
}

async function loadList() {
  loading.value = true
  try {
    const res = await api.get('/cockpit/customers', { page: page.value, per_page: perPage.value, search: search.value })
    list.value = res.data || []
    total.value = res.total || 0
  } catch (e) { ElMessage.error('加载失败') }
  finally { loading.value = false }
}

async function analyzeAll() {
  analyzing.value = true
  try {
    const res = await api.post('/cockpit/analyze-all', {})
    ElMessage.success(`分析完成: 客户${res.data.customer_profiles} 竞争对手${res.data.competitor_profiles} 提醒${res.data.sales_alerts}`)
    loadList()
  } catch (e) { ElMessage.error('分析失败') }
  finally { analyzing.value = false }
}

async function viewDetail(row) {
  try {
    const res = await api.get(`/cockpit/customers/${row.id}`)
    detail.value = res.data
    crmLink.value = res.crm_link || null
    detailVisible.value = true
  } catch (e) { ElMessage.error('加载详情失败') }
}

onMounted(() => loadList())
</script>
