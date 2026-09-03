<template>
  <div style="padding:16px">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;flex-wrap:wrap">
      <el-input v-model="search" placeholder="搜索企业名称/主营/行业" clearable style="width:240px"
                @keyup.enter="loadList" @clear="loadList" />
      <el-select v-model="filterRisk" placeholder="风险等级" clearable style="width:110px" @change="loadList">
        <el-option label="高" value="high" />
        <el-option label="中" value="medium" />
        <el-option label="低" value="low" />
      </el-select>
      <el-button @click="loadList">搜索</el-button>
      <el-button type="warning" :loading="autoUpdating" @click="autoUpdate">🔄 自动更新</el-button>
      <el-button type="success" :loading="analyzing" @click="analyzeAll">重新分析</el-button>
      <el-button type="primary" @click="openQuickAnalyze">📊 AI竞争分析</el-button>
      <el-button v-if="isAdmin" type="primary" plain @click="openEdit()">+ 新增竞争对手</el-button>
    </div>

    <el-table :data="list" v-loading="loading" border>
      <el-table-column label="风险" width="70" align="center">
        <template #default="{row}">
          <el-tag :type="riskType(row.risk_level)" size="small" effect="dark">
            {{ riskLabel(row.risk_level) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="企业名称" min-width="160" show-overflow-tooltip />
      <el-table-column label="别名" min-width="100">
        <template #default="{row}">
          <el-tag v-for="a in (row.aliases || [])" :key="a" size="small" style="margin:2px" type="info">{{ a }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="main_business" label="主营业务" min-width="140" show-overflow-tooltip />
      <el-table-column prop="industry" label="行业" width="100" show-overflow-tooltip />
      <el-table-column prop="appearance_count" label="出现次数" width="85" sortable />
      <el-table-column label="中标金额(万)" width="110" sortable :sort-by="'win_amount'">
        <template #default="{row}">{{ row.win_amount?.toFixed(2) || '0.00' }}</template>
      </el-table-column>
      <el-table-column label="主要客户" min-width="140">
        <template #default="{row}">
          <el-tag v-for="c in parseList(row.customer_list).slice(0,2)" :key="c" size="small" style="margin:2px">{{ c }}</el-tag>
          <span v-if="parseList(row.customer_list).length > 2" style="font-size:12px;color:#909399">等{{ parseList(row.customer_list).length }}家</span>
        </template>
      </el-table-column>
      <el-table-column prop="last_seen" label="最近出现" width="100" />
      <el-table-column label="操作" width="230">
        <template #default="{row}">
          <el-button size="small" type="success" plain :loading="analyzingId===row.id" @click="analyzeOne(row)">AI分析</el-button>
          <el-button size="small" @click="viewDetail(row)">详情</el-button>
          <el-button v-if="isAdmin" size="small" type="primary" plain @click="openEdit(row)">编辑</el-button>
          <el-button v-if="isAdmin" size="small" type="danger" text :loading="deletingId===row.id" @click="deleteOne(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination v-if="total > 0" :total="total" :page-size="perPage" v-model:current-page="page"
                   layout="total, prev, pager, next" style="margin-top:12px" @current-change="loadList" />

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" title="竞争对手详情" width="850px" top="5vh">
      <div v-if="detail" style="line-height:2">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap">
          <h3 style="margin:0">{{ detail.name }}</h3>
          <el-tag :type="riskType(detail.risk_level)" size="small" effect="dark">{{ riskLabel(detail.risk_level) }}风险</el-tag>
          <el-tag v-if="detail.website" size="small">
            <a :href="detail.website" target="_blank" style="color:#409eff;text-decoration:none">{{ detail.website }}</a>
          </el-tag>
        </div>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="主营业务">{{ detail.main_business || '-' }}</el-descriptions-item>
          <el-descriptions-item label="行业">{{ detail.industry || '-' }}</el-descriptions-item>
          <el-descriptions-item label="出现次数">{{ detail.appearance_count }}</el-descriptions-item>
          <el-descriptions-item label="涉及金额">{{ (detail.win_amount || 0).toFixed(2) }}万</el-descriptions-item>
          <el-descriptions-item label="首次出现">{{ detail.first_seen || '-' }}</el-descriptions-item>
          <el-descriptions-item label="最近出现">{{ detail.last_seen || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div v-if="detail.aliases?.length" style="margin-top:10px"><strong>别名：</strong>
          <el-tag v-for="a in detail.aliases" :key="a" size="small" style="margin:2px" type="info">{{ a }}</el-tag>
        </div>
        <div v-if="detail.products?.length" style="margin-top:8px"><strong>产品：</strong>
          <el-tag v-for="p in detail.products" :key="p" size="small" style="margin:2px" type="success">{{ p }}</el-tag>
        </div>
        <div v-if="detail.compete_fields?.length" style="margin-top:8px"><strong>竞争领域：</strong>
          <el-tag v-for="f in detail.compete_fields" :key="f" size="small" style="margin:2px" type="warning">{{ f }}</el-tag>
        </div>
        <div v-if="detail.customer_list?.length" style="margin-top:8px"><strong>客户：</strong>
          <el-tag v-for="c in detail.customer_list" :key="c" size="small" style="margin:2px">{{ c }}</el-tag>
        </div>
        <div v-if="detail.regions?.length" style="margin-top:8px"><strong>区域：</strong>
          <el-tag v-for="r in detail.regions" :key="r" size="small" style="margin:2px" type="info">{{ r }}</el-tag>
        </div>

        <div v-if="detail.strengths" style="margin-top:12px;padding:10px;background:#f0f9ff;border-radius:6px;border-left:4px solid #67c23a">
          <strong>💪 竞争对手优势</strong>
          <p style="margin:6px 0 0 0;white-space:pre-wrap">{{ detail.strengths }}</p>
        </div>
        <div v-if="detail.weaknesses" style="margin-top:8px;padding:10px;background:#fdf6ec;border-radius:6px;border-left:4px solid #e6a23c">
          <strong>⚠️ 竞争对手弱点</strong>
          <p style="margin:6px 0 0 0;white-space:pre-wrap">{{ detail.weaknesses }}</p>
        </div>
        <div v-if="detail.our_strategy" style="margin-top:8px;padding:10px;background:#f0f9ff;border-radius:6px;border-left:4px solid #409eff">
          <strong>🎯 我方竞争策略</strong>
          <p style="margin:6px 0 0 0;white-space:pre-wrap">{{ detail.our_strategy }}</p>
        </div>

        <div v-if="detail.recent_news?.length" style="margin-top:12px">
          <strong>最近动态：</strong>
          <el-timeline style="margin-top:8px">
            <el-timeline-item v-for="(n, i) in detail.recent_news" :key="i" :timestamp="n.date" placement="top">
              <div>{{ n.title }}</div>
              <div style="font-size:13px;color:#909399">客户:{{ n.buyer || '-' }} 预算:{{ n.budget || '-' }}</div>
            </el-timeline-item>
          </el-timeline>
        </div>
      </div>
    </el-dialog>

    <!-- 编辑弹窗 -->
    <el-dialog v-model="editVisible" :title="editForm.id ? '编辑竞争对手' : '新增竞争对手'" width="620px">
      <el-form :model="editForm" label-width="90px">
        <el-form-item label="企业名称" required>
          <el-input v-model="editForm.name" placeholder="企业名称" />
        </el-form-item>
        <el-form-item label="别名">
          <el-select v-model="editForm.aliases" multiple filterable allow-create default-first-option
                     placeholder="输入别名后回车" style="width:100%">
          </el-select>
        </el-form-item>
        <el-form-item label="官网">
          <el-input v-model="editForm.website" placeholder="https://" />
        </el-form-item>
        <el-form-item label="主营业务">
          <el-input v-model="editForm.main_business" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="产品">
          <el-select v-model="editForm.products" multiple filterable allow-create default-first-option
                     placeholder="输入产品后回车" style="width:100%">
          </el-select>
        </el-form-item>
        <el-form-item label="行业">
          <el-input v-model="editForm.industry" />
        </el-form-item>
        <el-form-item label="竞争领域">
          <el-select v-model="editForm.compete_fields" multiple filterable allow-create default-first-option
                     placeholder="输入竞争领域后回车" style="width:100%">
          </el-select>
        </el-form-item>
        <el-form-item label="客户">
          <el-select v-model="editForm.customer_list" multiple filterable allow-create default-first-option
                     placeholder="输入客户后回车" style="width:100%">
          </el-select>
        </el-form-item>
        <el-form-item label="风险等级">
          <el-select v-model="editForm.risk_level" style="width:140px">
            <el-option label="高" value="high" />
            <el-option label="中" value="medium" />
            <el-option label="低" value="low" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- AI分析弹窗 -->
    <el-dialog v-model="reportVisible" :title="`📊 ${reportName} 最近一年竞争分析`" width="850px" top="4vh">
      <div v-if="report" v-loading="reportLoading">
        <!-- 统计 -->
        <el-row :gutter="12" style="margin-bottom:14px">
          <el-col :span="6"><el-card shadow="never"><div class="stat-num">{{ report.stats.total_projects }}</div><div class="stat-label">涉及项目</div></el-card></el-col>
          <el-col :span="6"><el-card shadow="never"><div class="stat-num">{{ report.stats.win_count }}</div><div class="stat-label">中标项目</div></el-card></el-col>
          <el-col :span="6"><el-card shadow="never"><div class="stat-num">{{ report.stats.win_amount?.toFixed(2) }}</div><div class="stat-label">涉及金额(万)</div></el-card></el-col>
          <el-col :span="6"><el-card shadow="never"><div class="stat-num">{{ report.stats.growth_trend }}</div><div class="stat-label">增长趋势</div></el-card></el-col>
        </el-row>

        <!-- 月度趋势 -->
        <div style="margin-bottom:14px">
          <strong>月度活跃趋势：</strong>
          <div style="display:flex;align-items:flex-end;gap:4px;height:80px;margin-top:8px">
            <div v-for="t in report.stats.monthly_trend" :key="t.month" style="flex:1;text-align:center">
              <div style="background:#409eff;border-radius:3px 3px 0 0;margin:0 auto"
                   :style="{height: Math.max(t.count * 12, 2) + 'px', width: '70%'}"></div>
              <div style="font-size:10px;color:#909399">{{ t.month.slice(5) }}月</div>
            </div>
          </div>
        </div>

        <el-descriptions :column="2" border>
          <el-descriptions-item label="主要客户" :span="2">
            <el-tag v-for="[c, n] in report.stats.top_customers" :key="c" size="small" style="margin:2px">{{ c }}({{ n }}次)</el-tag>
            <span v-if="!report.stats.top_customers.length">暂无记录</span>
          </el-descriptions-item>
          <el-descriptions-item label="主要行业">
            <el-tag v-for="[i, n] in report.stats.top_industries" :key="i" size="small" type="success" style="margin:2px">{{ i }}({{ n }})</el-tag>
            <span v-if="!report.stats.top_industries.length">暂无记录</span>
          </el-descriptions-item>
          <el-descriptions-item label="主要区域">
            <el-tag v-for="[r, n] in report.stats.top_regions" :key="r" size="small" type="info" style="margin:2px">{{ r }}({{ n }})</el-tag>
            <span v-if="!report.stats.top_regions.length">暂无记录</span>
          </el-descriptions-item>
          <el-descriptions-item label="产品方向" :span="2">
            <el-tag v-for="p in report.stats.product_direction" :key="p" size="small" type="warning" style="margin:2px">{{ p }}</el-tag>
            <span v-if="!report.stats.product_direction.length">暂无记录</span>
          </el-descriptions-item>
          <el-descriptions-item label="竞争领域" :span="2">
            <el-tag v-for="f in report.stats.compete_fields" :key="f" size="small" type="danger" style="margin:2px">{{ f }}</el-tag>
            <span v-if="!report.stats.compete_fields.length">暂无记录</span>
          </el-descriptions-item>
        </el-descriptions>

        <!-- AI 分析结果 -->
        <div style="margin-top:14px">
          <el-tag :type="riskType(report.risk_level)" effect="dark" style="margin-bottom:10px">
            风险等级：{{ riskLabel(report.risk_level) }}
          </el-tag>
          <div style="padding:10px;background:#f0f9ff;border-radius:6px;border-left:4px solid #67c23a">
            <strong>💪 竞争对手优势</strong>
            <p style="margin:6px 0 0 0;white-space:pre-wrap">{{ report.strengths || '暂无（点击AI分析生成）' }}</p>
          </div>
          <div style="margin-top:8px;padding:10px;background:#fdf6ec;border-radius:6px;border-left:4px solid #e6a23c">
            <strong>⚠️ 竞争对手弱点</strong>
            <p style="margin:6px 0 0 0;white-space:pre-wrap">{{ report.weaknesses || '暂无（点击AI分析生成）' }}</p>
          </div>
          <div style="margin-top:8px;padding:10px;background:#f0f9ff;border-radius:6px;border-left:4px solid #409eff">
            <strong>🎯 我方竞争策略</strong>
            <p style="margin:6px 0 0 0;white-space:pre-wrap">{{ report.our_strategy || '暂无（点击AI分析生成）' }}</p>
          </div>
        </div>

        <!-- 最近项目 -->
        <div v-if="report.stats.recent_projects?.length" style="margin-top:14px">
          <strong>最近项目：</strong>
          <el-table :data="report.stats.recent_projects" size="small" border style="margin-top:8px">
            <el-table-column prop="title" label="项目" min-width="220" show-overflow-tooltip />
            <el-table-column prop="buyer" label="客户" min-width="140" show-overflow-tooltip />
            <el-table-column prop="budget" label="预算" width="90" />
            <el-table-column prop="date" label="日期" width="100" />
          </el-table>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const isAdmin = computed(() => auth.user?.role === 'admin' || auth.has?.('system.admin'))

const list = ref([])
const total = ref(0)
const page = ref(1)
const perPage = ref(20)
const search = ref('')
const filterRisk = ref('')
const loading = ref(false)
const analyzing = ref(false)
const analyzingId = ref(null)
const autoUpdating = ref(false)
const deletingId = ref(null)

// 详情
const detailVisible = ref(false)
const detail = ref(null)

// 编辑
const editVisible = ref(false)
const editForm = ref({})
const saving = ref(false)

// AI 分析报告
const reportVisible = ref(false)
const reportName = ref('')
const report = ref(null)
const reportLoading = ref(false)

function riskType(level) {
  return { high: 'danger', medium: 'warning', low: 'success' }[level] || 'info'
}

function riskLabel(level) {
  return { high: '高', medium: '中', low: '低' }[level] || '中'
}

function parseList(str) {
  if (!str) return []
  if (Array.isArray(str)) return str
  try { return JSON.parse(str) } catch { return [] }
}

async function loadList() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: perPage.value, search: search.value }
    if (filterRisk.value) params.risk_level = filterRisk.value
    const res = await api.get('/cockpit/competitors', params)
    list.value = (res.data || []).map(r => ({
      ...r,
      aliases: parseList(r.aliases),
    }))
    total.value = res.total || 0
  } catch (e) { ElMessage.error('加载失败') }
  finally { loading.value = false }
}

async function analyzeAll() {
  analyzing.value = true
  try {
    const res = await api.post('/cockpit/analyze-all', {})
    ElMessage.success(`分析完成: 竞争对手${res.data.competitor_profiles}条`)
    loadList()
  } catch (e) { ElMessage.error('分析失败') }
  finally { analyzing.value = false }
}

async function autoUpdate() {
  autoUpdating.value = true
  try {
    const res = await api.post('/cockpit/competitors/auto-update')
    ElMessage.success(res.message || '自动更新完成')
    loadList()
  } catch (e) { ElMessage.error('自动更新失败') }
  finally { autoUpdating.value = false }
}

async function viewDetail(row) {
  try {
    const res = await api.get(`/cockpit/competitors/${row.id}`)
    detail.value = res.data
    detailVisible.value = true
  } catch (e) { ElMessage.error('加载详情失败') }
}

async function analyzeOne(row) {
  analyzingId.value = row.id
  reportName.value = row.name
  reportVisible.value = true
  reportLoading.value = true
  report.value = null
  try {
    const res = await api.longPost(`/cockpit/competitors/${row.id}/analyze`)
    report.value = res.data
  } catch (e) { ElMessage.error('AI分析失败') }
  finally { reportLoading.value = false; analyzingId.value = null }
}

function openQuickAnalyze() {
  ElMessageBox.prompt('输入要分析的公司名称，AI将统计其最近一年竞争情况', 'AI竞争分析', {
    confirmButtonText: '分析',
    cancelButtonText: '取消',
    inputPlaceholder: '例如：XX信息技术有限公司',
  }).then(({ value }) => {
    if (!value || !value.trim()) return
    reportName.value = value.trim()
    reportVisible.value = true
    reportLoading.value = true
    report.value = null
    api.longPost('/cockpit/competitors/analyze', { name: value.trim() })
      .then(res => { report.value = res.data })
      .catch(() => ElMessage.error('AI分析失败'))
      .finally(() => { reportLoading.value = false })
  }).catch(() => {})
}

function openEdit(row = null) {
  editForm.value = row ? {
    id: row.id,
    name: row.name,
    aliases: parseList(row.aliases),
    website: row.website || '',
    main_business: row.main_business || '',
    products: parseList(row.products),
    industry: row.industry || '',
    compete_fields: parseList(row.compete_fields),
    customer_list: parseList(row.customer_list),
    risk_level: row.risk_level || 'medium',
  } : {
    name: '', aliases: [], website: '', main_business: '',
    products: [], industry: '', compete_fields: [],
    customer_list: [], risk_level: 'medium',
  }
  editVisible.value = true
}

async function saveEdit() {
  const f = editForm.value
  if (!f.name?.trim()) { ElMessage.warning('企业名称必填'); return }
  saving.value = true
  try {
    if (f.id) {
      const res = await api.put(`/cockpit/competitors/${f.id}`, f)
      ElMessage.success(res.message || '已保存')
    } else {
      const res = await api.post('/cockpit/competitors', f)
      ElMessage.success(res.message || '已新增')
    }
    editVisible.value = false
    loadList()
  } catch (e) { ElMessage.error('保存失败：' + (e.response?.data?.message || e.message)) }
  finally { saving.value = false }
}

async function deleteOne(row) {
  try {
    await ElMessageBox.confirm(`确定删除竞争对手「${row.name}」？`, '删除', { type: 'warning' })
  } catch { return }
  deletingId.value = row.id
  try {
    const res = await api.delete(`/cockpit/competitors/${row.id}`)
    ElMessage.success(res.message || '已删除')
    loadList()
  } catch (e) { ElMessage.error('删除失败') }
  finally { deletingId.value = null }
}

onMounted(() => loadList())
</script>

<style scoped>
.stat-num { font-size: 24px; font-weight: bold; color: #303133; }
.stat-label { font-size: 12px; color: #909399; }
</style>
