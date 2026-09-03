<template>
  <div style="padding:16px">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;flex-wrap:wrap">
      <el-input v-model="search" placeholder="搜索客户名称/行业/地区" clearable style="width:240px"
                @keyup.enter="loadList" @clear="loadList" />
      <el-select v-model="filterTier" placeholder="客户分级" clearable style="width:120px" @change="loadList">
        <el-option label="战略客户" value="strategic" />
        <el-option label="重点客户" value="key" />
        <el-option label="普通客户" value="normal" />
        <el-option label="潜在客户" value="potential" />
        <el-option label="AI发现" value="ai_discovered" />
      </el-select>
      <el-select v-model="filterAiStatus" placeholder="AI状态" clearable style="width:110px" @change="loadList">
        <el-option label="待确认" value="pending" />
        <el-option label="已确认" value="confirmed" />
      </el-select>
      <el-button @click="loadList">搜索</el-button>
      <el-button type="success" :loading="analyzing" @click="analyzeAll">一键聚合</el-button>
      <el-button type="primary" :loading="aiGenerating" @click="generateAiAll">🤖 AI画像生成</el-button>
      <el-button type="danger" :loading="deleting" :disabled="!selection.length" @click="batchDelete">
        批量删除{{ selection.length ? `(${selection.length})` : '' }}
      </el-button>
    </div>

    <el-table :data="list" v-loading="loading" border @selection-change="rows => selection = rows">
      <el-table-column type="selection" width="45" />
      <el-table-column prop="buyer" label="采购单位" min-width="180" show-overflow-tooltip />
      <el-table-column label="分级" width="100" align="center">
        <template #default="{row}">
          <el-tag :type="tierType(row.customer_tier)" size="small" effect="dark">
            {{ tierLabel(row.customer_tier) }}
          </el-tag>
          <el-badge v-if="row.ai_status === 'pending'" is-dot type="warning" style="margin-left:6px">
            <el-icon style="color:#e6a23c;font-size:12px"><Warning /></el-icon>
          </el-badge>
        </template>
      </el-table-column>
      <el-table-column prop="region" label="地区" width="80" />
      <el-table-column prop="total_procurements" label="采购次数" width="80" sortable />
      <el-table-column label="总预算(万)" width="100" sortable :sort-by="'total_budget'">
        <template #default="{row}">{{ row.total_budget?.toFixed(2) || '0.00' }}</template>
      </el-table-column>
      <el-table-column prop="procurement_frequency" label="采购频率" width="120" show-overflow-tooltip />
      <el-table-column label="评分" width="80" align="center">
        <template #default="{row}">
          <span :class="['score-num', scoreClass(row.max_score)]">{{ row.max_score || 0 }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="latest_date" label="最近采购" width="100" />
      <el-table-column label="操作" width="240">
        <template #default="{row}">
          <el-button size="small" @click="viewDetail(row)">详情</el-button>
          <el-button size="small" type="primary" plain :loading="aiId===row.id" @click="generateAiOne(row)">AI画像</el-button>
          <el-button v-if="row.ai_status === 'pending'" size="small" type="success" plain
                     :loading="confirmId===row.id" @click="confirmCustomer(row)">确认</el-button>
          <el-button size="small" type="danger" text :loading="deletingId===row.id" @click="deleteOne(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination v-if="total > 0" :total="total" :page-size="perPage" v-model:current-page="page"
                   layout="total, prev, pager, next" style="margin-top:12px" @current-change="loadList" />

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" title="AI客户画像详情" width="850px" top="5vh">
      <div v-if="detail" style="line-height:2">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap">
          <h3 style="margin:0">{{ detail.buyer }}</h3>
          <el-tag :type="tierType(detail.customer_tier)" size="small" effect="dark">
            {{ tierLabel(detail.customer_tier) }}
          </el-tag>
          <el-tag v-if="detail.ai_status === 'pending'" type="warning" size="small">待人工确认</el-tag>
          <el-tag v-if="crmLink" type="success" size="small">已入CRM · 负责人：{{ crmLink.owner_name || '未分配' }}</el-tag>
          <el-tag v-else type="info" size="small">未入CRM</el-tag>
          <el-select v-model="detail.customer_tier" size="small" style="width:110px" @change="updateTier(detail)">
            <el-option label="战略客户" value="strategic" />
            <el-option label="重点客户" value="key" />
            <el-option label="普通客户" value="normal" />
            <el-option label="潜在客户" value="potential" />
            <el-option label="AI发现" value="ai_discovered" />
          </el-select>
          <el-button v-if="crmLink" size="small" type="primary" text @click="goToCrm">前往客户管理 →</el-button>
        </div>

        <!-- 基本信息 -->
        <el-descriptions :column="3" border>
          <el-descriptions-item label="地区">{{ detail.region || '-' }}</el-descriptions-item>
          <el-descriptions-item label="行业">{{ detail.industry || '-' }}</el-descriptions-item>
          <el-descriptions-item label="采购次数">{{ detail.total_procurements }}</el-descriptions-item>
          <el-descriptions-item label="总预算">{{ (detail.total_budget || 0).toFixed(2) }}万</el-descriptions-item>
          <el-descriptions-item label="平均预算">{{ (detail.avg_budget || 0).toFixed(2) }}万</el-descriptions-item>
          <el-descriptions-item label="采购频率">{{ detail.procurement_frequency || '-' }}</el-descriptions-item>
          <el-descriptions-item label="平均评分">{{ (detail.avg_score || 0).toFixed(1) }}</el-descriptions-item>
          <el-descriptions-item label="最高评分">{{ detail.max_score }}</el-descriptions-item>
          <el-descriptions-item label="最近采购">{{ detail.latest_date || '-' }}</el-descriptions-item>
        </el-descriptions>

        <!-- AI分析 -->
        <div v-if="detail.ai_analysis" style="margin-top:12px;padding:12px;background:#f0f9ff;border-radius:6px;border-left:4px solid #409eff">
          <strong>🤖 AI判断</strong>
          <p style="margin:6px 0 0 0;color:#303133;white-space:pre-wrap">{{ detail.ai_analysis }}</p>
          <div v-if="detail.ai_tier_suggestion" style="margin-top:6px;font-size:13px;color:#909399">
            AI建议分级：{{ tierLabel(detail.ai_tier_suggestion) }}
          </div>
        </div>

        <!-- 采购方向 + 潜在项目 -->
        <div v-if="detail.potential_projects?.length" style="margin-top:12px">
          <strong>潜在项目（AI预测）：</strong>
          <el-tag v-for="(p, i) in detail.potential_projects" :key="i" type="warning" style="margin:2px" size="small">{{ p }}</el-tag>
        </div>

        <!-- 重点供应商 -->
        <div v-if="detail.key_suppliers?.length" style="margin-top:8px">
          <strong>重点供应商：</strong>
          <el-tag v-for="(s, i) in detail.key_suppliers" :key="i" type="success" style="margin:2px" size="small">
            {{ s.project || s }} {{ s.amount ? `(${s.amount}万)` : '' }}
          </el-tag>
        </div>

        <!-- 竞争对手 -->
        <div v-if="detail.competitors?.length" style="margin-top:8px">
          <strong>常见竞争对手：</strong>
          <el-tag v-for="c in detail.competitors" :key="c" style="margin:2px" size="small" type="danger">{{ c }}</el-tag>
        </div>

        <!-- 采购方式 -->
        <div v-if="detail.procurement_methods?.length" style="margin-top:8px">
          <strong>采购方式：</strong>
          <el-tag v-for="m in detail.procurement_methods" :key="m" type="info" style="margin:2px" size="small">{{ m }}</el-tag>
        </div>

        <!-- 项目类型 -->
        <div v-if="detail.project_types?.length" style="margin-top:8px">
          <strong>项目类型：</strong>
          <el-tag v-for="t in detail.project_types" :key="t" type="success" style="margin:2px" size="small">{{ t }}</el-tag>
        </div>

        <!-- 采购时间线 -->
        <div v-if="detail.timeline?.length" style="margin-top:12px">
          <strong>历史采购时间线：</strong>
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
import { Warning } from '@element-plus/icons-vue'
import api from '../api'

const router = useRouter()
const crmLink = ref(null)

const list = ref([])
const total = ref(0)
const page = ref(1)
const perPage = ref(20)
const search = ref('')
const filterTier = ref('')
const filterAiStatus = ref('')
const loading = ref(false)
const analyzing = ref(false)
const aiGenerating = ref(false)
const aiId = ref(null)
const confirmId = ref(null)
const detailVisible = ref(false)
const detail = ref(null)
const selection = ref([])
const deleting = ref(false)
const deletingId = ref(null)

const TIER_MAP = {
  strategic: { label: '战略客户', type: 'danger' },
  key: { label: '重点客户', type: 'warning' },
  normal: { label: '普通客户', type: 'primary' },
  potential: { label: '潜在客户', type: 'info' },
  ai_discovered: { label: 'AI发现', type: 'success' },
}

function tierLabel(tier) {
  return TIER_MAP[tier]?.label || '未分级'
}

function tierType(tier) {
  return TIER_MAP[tier]?.type || 'info'
}

function scoreClass(score) {
  if (score >= 80) return 'score-s'
  if (score >= 60) return 'score-a'
  if (score >= 40) return 'score-b'
  return 'score-c'
}

function goToCrm() {
  if (crmLink.value?.company) {
    router.push({ path: '/customers', query: { keyword: crmLink.value.company } })
  }
}

async function loadList() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: perPage.value, search: search.value }
    if (filterTier.value) params.tier = filterTier.value
    if (filterAiStatus.value) params.ai_status = filterAiStatus.value
    const res = await api.get('/cockpit/customers', params)
    list.value = res.data || []
    total.value = res.total || 0
  } catch (e) { ElMessage.error('加载失败') }
  finally { loading.value = false }
}

async function analyzeAll() {
  analyzing.value = true
  try {
    const res = await api.post('/cockpit/analyze-all', {})
    ElMessage.success(`聚合完成: 客户${res.data.customer_profiles} 竞争对手${res.data.competitor_profiles} 提醒${res.data.sales_alerts}`)
    loadList()
  } catch (e) { ElMessage.error('聚合失败') }
  finally { analyzing.value = false }
}

async function generateAiAll() {
  try {
    await ElMessageBox.confirm('将为所有客户生成AI画像（含LLM分析、客户分级、AI发现新客户），可能需要几分钟。继续？', 'AI画像生成', { type: 'info' })
  } catch { return }
  aiGenerating.value = true
  try {
    const res = await api.longPost('/cockpit/customers/generate-ai', { run_ai: true })
    ElMessage.success(res.message || 'AI画像生成完成')
    loadList()
  } catch (e) { ElMessage.error('AI画像生成失败：' + (e.response?.data?.message || e.message)) }
  finally { aiGenerating.value = false }
}

async function generateAiOne(row) {
  aiId.value = row.id
  try {
    const res = await api.longPost(`/cockpit/customers/${row.id}/generate-ai`)
    ElMessage.success(res.message || 'AI画像已生成')
    loadList()
    // 如果详情打开则刷新
    if (detailVisible.value && detail.value?.id === row.id) {
      viewDetail(row)
    }
  } catch (e) { ElMessage.error('AI画像生成失败：' + (e.response?.data?.message || e.message)) }
  finally { aiId.value = null }
}

async function confirmCustomer(row) {
  confirmId.value = row.id
  try {
    const res = await api.post(`/cockpit/customers/${row.id}/confirm`)
    ElMessage.success(res.message || '已确认')
    loadList()
  } catch (e) { ElMessage.error('确认失败') }
  finally { confirmId.value = null }
}

async function updateTier(row) {
  try {
    const res = await api.put(`/cockpit/customers/${row.id}/tier`, { tier: row.customer_tier })
    ElMessage.success(res.message || '分级已更新')
  } catch (e) { ElMessage.error('分级更新失败') }
}

async function deleteOne(row) {
  try {
    await ElMessageBox.confirm(`确定删除客户「${row.buyer}」的画像？`, '删除画像', { type: 'warning' })
  } catch { return }
  deletingId.value = row.id
  try {
    const res = await api.delete(`/cockpit/customers/${row.id}`)
    if (res && res.code === 200) {
      ElMessage.success(res.message || '已删除')
      loadList()
    }
  } catch (e) { ElMessage.error('删除失败') }
  finally { deletingId.value = null }
}

async function batchDelete() {
  if (!selection.value.length) return
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selection.value.length} 条客户画像？`, '批量删除', { type: 'warning' })
  } catch { return }
  deleting.value = true
  try {
    const res = await api.post('/cockpit/customers/batch-delete', { ids: selection.value.map(r => r.id) })
    if (res && res.code === 200) {
      ElMessage.success(res.message || '删除成功')
      selection.value = []
      loadList()
    }
  } catch (e) { ElMessage.error('批量删除失败') }
  finally { deleting.value = false }
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

<style scoped>
.score-num { font-weight: bold; font-size: 14px; }
.score-s { color: #f56c6c; }
.score-a { color: #e6a23c; }
.score-b { color: #409eff; }
.score-c { color: #909399; }
</style>
