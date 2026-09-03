<template>
  <div style="padding:16px">
    <!-- 筛选栏 -->
    <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">
      <el-input v-model="filters.search" placeholder="搜索项目名称/客户/摘要" clearable style="width:220px"
                @keyup.enter="loadList" @clear="loadList" />
      <el-input v-model="filters.industry" placeholder="行业" clearable style="width:110px" @keyup.enter="loadList" />
      <el-input v-model="filters.business" placeholder="业务" clearable style="width:110px" @keyup.enter="loadList" />
      <el-input v-model="filters.region" placeholder="地区" clearable style="width:110px" @keyup.enter="loadList" />
      <el-input v-model="filters.buyer" placeholder="客户" clearable style="width:130px" @keyup.enter="loadList" />
      <el-input v-model="filters.competitor" placeholder="竞争对手" clearable style="width:130px" @keyup.enter="loadList" />
      <el-input v-model="filters.budget_min" placeholder="最低预算(万)" clearable style="width:110px" />
      <el-input v-model="filters.budget_max" placeholder="最高预算(万)" clearable style="width:110px" />
      <el-date-picker v-model="dateRange" type="daterange" start-placeholder="开始日期" end-placeholder="结束日期"
                      value-format="YYYY-MM-DD" style="width:240px" @change="loadList" />
      <el-select v-model="filters.stage" placeholder="项目阶段" clearable style="width:120px" @change="loadList">
        <el-option v-for="(v, k) in STAGES" :key="k" :label="v" :value="k" />
      </el-select>
      <el-select v-model="filters.grade" placeholder="商机等级" clearable style="width:100px" @change="loadList">
        <el-option label="S级" value="S" />
        <el-option label="A级" value="A" />
        <el-option label="B级" value="B" />
        <el-option label="C级" value="C" />
      </el-select>
      <el-button type="primary" @click="loadList">筛选</el-button>
      <el-button @click="resetFilters">重置</el-button>
    </div>

    <el-table :data="list" v-loading="loading" border>
      <el-table-column label="项目名称" min-width="240" show-overflow-tooltip>
        <template #default="{row}">
          <el-link type="primary" @click="viewDetail(row)">{{ row.title }}</el-link>
        </template>
      </el-table-column>
      <el-table-column prop="buyer" label="客户" min-width="150" show-overflow-tooltip />
      <el-table-column prop="industry" label="行业" width="90" show-overflow-tooltip />
      <el-table-column prop="region" label="地区" width="80" show-overflow-tooltip />
      <el-table-column prop="budget" label="预算" width="100" show-overflow-tooltip />
      <el-table-column label="项目阶段" width="100" align="center">
        <template #default="{row}">
          <el-tag size="small" :type="stageType(row.stage)">{{ STAGES[row.stage] || row.stage || '-' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="等级" width="70" align="center">
        <template #default="{row}">
          <span :class="['grade-badge', gradeClass(row.grade)]">{{ row.grade }}</span>
        </template>
      </el-table-column>
      <el-table-column label="匹配度" width="80" align="center">
        <template #default="{row}">
          <span :class="['score-num', scoreClass(row.score)]">{{ row.score }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="发布时间" width="100" />
      <el-table-column prop="source" label="来源" width="110" show-overflow-tooltip />
      <el-table-column label="销售负责人" width="100">
        <template #default="{row}">{{ row.owner_name || '待分配' }}</template>
      </el-table-column>
    </el-table>

    <el-pagination v-if="total > 0" :total="total" :page-size="perPage" v-model:current-page="page"
                   layout="total, prev, pager, next" style="margin-top:12px" @current-change="loadList" />

    <!-- AI商机详情弹窗 -->
    <el-dialog v-model="detailVisible" title="AI商机详情" width="900px" top="3vh" destroy-on-close>
      <div v-loading="detailLoading" style="min-height:200px">
        <template v-if="detail">
          <h3 style="margin:0 0 8px 0">{{ detail.title }}</h3>
          <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">
            <el-tag :class="['grade-tag', gradeClass(detail.score_grade)]" effect="dark">
              {{ detail.score_grade || gradeOf(detail.score) }}级 {{ detail.score }}分
            </el-tag>
            <el-tag size="small">{{ STAGES[detail.lifecycle_stage] || detail.lifecycle_stage || '阶段未知' }}</el-tag>
            <el-tag size="small" type="info">来源：{{ detail.source_name || '-' }}</el-tag>
          </div>

          <el-descriptions :column="2" border>
            <el-descriptions-item label="客户">{{ detail.buyer || '-' }}</el-descriptions-item>
            <el-descriptions-item label="预算">{{ detail.budget || '-' }}</el-descriptions-item>
            <el-descriptions-item label="采购内容">{{ detail.procurement_method || '-' }}</el-descriptions-item>
            <el-descriptions-item label="地区">{{ detail.region || '-' }}</el-descriptions-item>
            <el-descriptions-item label="截止时间">{{ detail.deadline || '-' }}</el-descriptions-item>
            <el-descriptions-item label="发布时间">{{ detail.created_at?.slice(0,10) }}</el-descriptions-item>
          </el-descriptions>

          <!-- AI摘要 -->
          <div v-if="detail.analysis_summary" style="margin-top:12px;padding:10px;background:#f0f9ff;border-radius:6px;border-left:4px solid #409eff">
            <strong>🤖 AI摘要</strong>
            <p style="margin:6px 0 0 0;white-space:pre-wrap">{{ detail.analysis_summary }}</p>
          </div>

          <!-- AI判断 -->
          <div v-if="detail.score_reason" style="margin-top:8px;padding:10px;background:#fdf6ec;border-radius:6px;border-left:4px solid #e6a23c">
            <strong>⚖️ AI判断</strong>
            <p style="margin:6px 0 0 0;white-space:pre-wrap">{{ detail.score_reason }}</p>
          </div>

          <!-- 我方能力匹配 -->
          <div v-if="capResult" style="margin-top:8px;padding:10px;background:#f0f9eb;border-radius:6px;border-left:4px solid #67c23a">
            <strong>💪 我方能力匹配（{{ capResult.capability_score }}分）</strong>
            <div style="margin-top:6px">
              <el-tag v-for="m in capResult.matched" :key="m.name" size="small" style="margin:2px" type="success">
                {{ m.name }}({{ m.confidence }})
              </el-tag>
              <span v-if="!capResult.matched?.length" style="color:#909399;font-size:13px">未匹配到我方能力</span>
            </div>
          </div>

          <!-- 潜在竞争对手 -->
          <div v-if="parseComps(detail.competitors).length" style="margin-top:8px">
            <strong>🎯 潜在竞争对手：</strong>
            <el-tag v-for="c in parseComps(detail.competitors)" :key="c" type="danger" size="small" style="margin:2px">{{ c }}</el-tag>
          </div>

          <!-- 销售建议（AI） -->
          <div v-if="salesAdvice" style="margin-top:8px;padding:10px;background:#fafafa;border-radius:6px;border-left:4px solid #909399">
            <strong>📋 销售建议</strong>
            <p style="margin:6px 0 0 0;white-space:pre-wrap">{{ salesAdvice }}</p>
          </div>

          <!-- 历史关联项目 -->
          <div v-if="relatedProjects.length" style="margin-top:12px">
            <strong>📁 历史关联项目（{{ relatedProjects.length }}）：</strong>
            <el-table :data="relatedProjects" size="small" border style="margin-top:6px">
              <el-table-column prop="title" label="项目" min-width="220" show-overflow-tooltip />
              <el-table-column prop="buyer" label="客户" min-width="130" show-overflow-tooltip />
              <el-table-column prop="budget" label="预算" width="90" />
              <el-table-column prop="lifecycle_stage" label="阶段" width="90" />
            </el-table>
          </div>

          <!-- 相关情报 -->
          <div v-if="relatedIntel.length" style="margin-top:12px">
            <strong>📰 相关情报（{{ relatedIntel.length }}）：</strong>
            <div v-for="ri in relatedIntel" :key="ri.id" style="padding:6px 0;border-bottom:1px solid #f0f0f0">
              <div>{{ ri.title }}</div>
              <div style="font-size:12px;color:#909399">{{ ri.source_name || '' }} {{ ri.publish_date || '' }}</div>
            </div>
          </div>
        </template>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const STAGES = {
  intelligence: '情报', purchase_intent: '采购意向', project_forecast: '项目预告',
  tender_announcement: '招标公告', qa_announcement: '答疑公告', bid_opening: '开标',
  won_bid: '中标公告', contract_announcement: '合同公告', lost_bid: '落标', deal_closed: '成交',
}

const list = ref([])
const total = ref(0)
const page = ref(1)
const perPage = ref(20)
const loading = ref(false)
const dateRange = ref(null)
const filters = reactive({
  search: '', industry: '', business: '', region: '', buyer: '',
  competitor: '', budget_min: '', budget_max: '', stage: '', grade: '',
})

const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref(null)
const capResult = ref(null)
const salesAdvice = ref('')
const relatedProjects = ref([])
const relatedIntel = ref([])

function stageType(stage) {
  if (['won_bid', 'deal_closed'].includes(stage)) return 'success'
  if (stage === 'lost_bid') return 'danger'
  if (['tender_announcement', 'bid_opening', 'contract_announcement'].includes(stage)) return 'warning'
  return 'info'
}

function gradeClass(grade) {
  return { S: 'g-s', A: 'g-a', B: 'g-b', C: 'g-c' }[grade] || 'g-c'
}

function scoreClass(score) {
  if (score >= 80) return 's-s'
  if (score >= 60) return 's-a'
  if (score >= 40) return 's-b'
  return 's-c'
}

function gradeOf(score) {
  if (score >= 90) return 'S'
  if (score >= 80) return 'A'
  if (score >= 60) return 'B'
  return 'C'
}

function parseComps(raw) {
  try {
    const v = typeof raw === 'string' ? JSON.parse(raw) : (raw || [])
    return Array.isArray(v) ? v : []
  } catch { return [] }
}

function resetFilters() {
  Object.keys(filters).forEach(k => { filters[k] = '' })
  dateRange.value = null
  page.value = 1
  loadList()
}

async function loadList() {
  loading.value = true
  try {
    const params = {
      page: page.value, per_page: perPage.value,
      ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== '')),
    }
    if (dateRange.value?.length === 2) {
      params.date_from = dateRange.value[0]
      params.date_to = dateRange.value[1]
    }
    const res = await api.get('/cockpit/radar-list', params)
    list.value = res.data || []
    total.value = res.total || 0
  } catch (e) { ElMessage.error('加载失败') }
  finally { loading.value = false }
}

async function viewDetail(row) {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = null
  capResult.value = null
  salesAdvice.value = ''
  relatedProjects.value = []
  relatedIntel.value = []
  try {
    // 商机详情
    const res = await api.get(`/intelligence/leads/${row.id}`)
    detail.value = res.data
    // 我方能力匹配
    try {
      const capRes = await api.post('/capabilities/match', {
        title: detail.value.title, text: detail.value.analysis_summary || '',
      })
      capResult.value = capRes.data
    } catch { /* 能力匹配失败不阻塞 */ }
    // AI销售建议（LLM生成）
    try {
      const advRes = await api.longPost('/cockpit/ai-search', {
        query: `为商机「${detail.value.title}」（客户${detail.value.buyer || '未知'}，预算${detail.value.budget || '未知'}）给出销售建议：为什么值得跟、建议动作`,
      })
      salesAdvice.value = advRes.data?.answer || ''
    } catch { /* 建议失败不阻塞 */ }
    // 历史关联项目（同客户）
    try {
      const projRes = await api.get('/intelligence/leads', {
        buyer: detail.value.buyer || '', per_page: 5,
      })
      relatedProjects.value = (projRes.data || []).filter(p => p.id !== row.id).slice(0, 5)
    } catch { /* ignore */ }
    // 相关情报
    try {
      const intelRes = await api.get('/intelligence', { search: detail.value.title?.slice(0, 15), per_page: 5 })
      relatedIntel.value = intelRes.data || []
    } catch { /* ignore */ }
  } catch (e) {
    ElMessage.error('加载详情失败')
    detailVisible.value = false
  } finally { detailLoading.value = false }
}

onMounted(() => loadList())
</script>

<style scoped>
.grade-badge { font-weight: bold; }
.g-s { color: #f56c6c; }
.g-a { color: #e6a23c; }
.g-b { color: #409eff; }
.g-c { color: #909399; }
.score-num { font-weight: bold; }
.s-s { color: #f56c6c; }
.s-a { color: #e6a23c; }
.s-b { color: #409eff; }
.s-c { color: #909399; }
</style>
