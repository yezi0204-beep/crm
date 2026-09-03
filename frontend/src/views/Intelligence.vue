<template>
  <div class="intel-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>📡 原始情报库</span>
          <el-tag v-for="(v, k) in stats" :key="k" :type="statusType(k)" size="small" style="margin-left:8px">
            {{ statusLabel(k) }}: {{ v }}
          </el-tag>
        </div>
      </template>

      <div class="filter-bar">
        <el-input v-model="search" placeholder="搜索标题/正文" clearable style="width:260px"
                  @keyup.enter="loadData" @clear="loadData" />
        <el-select v-model="filterStatus" placeholder="状态" clearable style="width:110px" @change="loadData">
          <el-option label="待处理" value="pending" />
          <el-option label="处理中" value="processing" />
          <el-option label="已分析" value="analyzed" />
          <el-option label="无效" value="invalid" />
        </el-select>
        <el-button @click="loadData">搜索</el-button>
        <el-divider direction="vertical" />
        <el-select v-model="selectedSourceId" placeholder="选择数据源" style="width:220px" filterable>
          <el-option v-for="s in sources" :key="s.id" :label="s.name" :value="s.id" />
        </el-select>
        <el-button type="primary" :loading="collecting" @click="collectOne">采集</el-button>
        <el-button :loading="collectingAll" @click="collectAll">批量采集</el-button>
        <el-divider direction="vertical" />
        <el-button type="warning" :loading="batchAgentRunning" @click="agentAnalyzeAll">
          {{ batchAgentRunning
            ? `🤖 分析中(${batchAgentProgress.done}/${batchAgentProgress.total})`
            : '🤖 一键7-Agent分析' }}
        </el-button>
        <el-divider direction="vertical" />
        <el-button type="danger" :disabled="!selection.length" :loading="deleting"
                   @click="batchDelete">批量删除{{ selection.length ? `(${selection.length})` : '' }}</el-button>
      </div>

      <el-table :data="list" v-loading="loading" border style="margin-top:12px" @selection-change="onSelectionChange">
        <el-table-column type="selection" width="45" />
        <el-table-column prop="title" label="标题" min-width="260" show-overflow-tooltip />
        <el-table-column label="命中关键词" min-width="140">
          <template #default="{row}">
            <template v-if="parseMatched(row.keywords_matched).length">
              <el-tag v-for="kw in parseMatched(row.keywords_matched).slice(0, 3)" :key="kw" type="success" size="small"
                      style="margin-right:4px;margin-bottom:2px">{{ kw }}</el-tag>
              <el-tooltip v-if="parseMatched(row.keywords_matched).length > 3"
                          :content="parseMatched(row.keywords_matched).slice(3).join('、')" placement="top">
                <el-tag size="small" type="info">+{{ parseMatched(row.keywords_matched).length - 3 }}</el-tag>
              </el-tooltip>
            </template>
            <span v-else style="color:#c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="source_name" label="来源" width="140" show-overflow-tooltip />
        <el-table-column prop="publish_date" label="发布日期" width="100" />
        <el-table-column prop="collected_at" label="采集时间" width="150" />
        <el-table-column label="状态" width="80">
          <template #default="{row}">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="附件" width="50" align="center">
          <template #default="{row}">
            <el-tooltip v-if="row.attachment_path" content="有附件" placement="top">
              <span style="cursor:pointer">📎</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="340">
          <template #default="{row}">
            <el-button size="small" @click="viewDetail(row.id)">详情</el-button>
            <el-button v-if="row.lead_id" size="small" type="success" @click="viewLead(row)">
              查看商机{{ row.lead_score ? `(${row.lead_score}分)` : '' }}
            </el-button>
            <el-button v-if="row.agent_result_id" size="small" type="info"
                       :loading="agentLoading && currentAgentId===row.id"
                       @click="openAgentResult(row)">
              🤖 查看分析{{ row.agent_score ? `(${row.agent_score}分)` : '' }}
            </el-button>
            <el-button v-if="row.agent_result_id" size="small" type="warning"
                       :loading="agentAnalyzingId===row.id"
                       @click="agentAnalyze(row.id, true)">🔄 重新分析</el-button>
            <el-button v-else size="small" type="warning"
                       :loading="agentAnalyzingId===row.id"
                       @click="agentAnalyze(row.id)">🤖 7-Agent分析</el-button>
            <el-button v-if="row.attachment_path" size="small" type="success" :loading="parsingId===row.id"
                       @click="parseAttachment(row.id)">解析附件</el-button>
            <el-button size="small" type="danger" @click="deleteItem(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination v-model:current-page="page" :page-size="perPage" :total="total"
                     layout="total, prev, pager, next" @current-change="loadData"
                     style="margin-top:12px;justify-content:center" />
    </el-card>

    <el-dialog v-model="showDetail" title="情报详情" width="800px">
      <el-descriptions :column="1" border v-if="detail">
        <el-descriptions-item label="标题">{{ detail.title }}</el-descriptions-item>
        <el-descriptions-item label="来源">{{ detail.source_name }}</el-descriptions-item>
        <el-descriptions-item label="URL">
          <a :href="detail.url" target="_blank" style="color:#409eff">{{ detail.url }}</a>
        </el-descriptions-item>
        <el-descriptions-item label="发布日期">{{ detail.publish_date }}</el-descriptions-item>
        <el-descriptions-item label="采集时间">{{ detail.collected_at }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="statusType(detail.status)">{{ statusLabel(detail.status) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="命中关键词" v-if="parseMatched(detail.keywords_matched).length">
          <el-tag v-for="kw in parseMatched(detail.keywords_matched)" :key="kw" type="success" size="small"
                  style="margin-right:4px;margin-bottom:2px">{{ kw }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="附件" v-if="detail.attachment_path">
          <div v-for="(url, i) in detail.attachment_path.split(',')" :key="i" style="margin:2px 0">
            <a :href="url.trim()" target="_blank" style="color:#409eff">{{ url.trim() }}</a>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="摘要" v-if="detail.snippet">{{ detail.snippet }}</el-descriptions-item>
        <el-descriptions-item label="正文" v-if="detail.content">
          <div class="content-box">{{ detail.content }}</div>
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>

    <!-- 7-Agent 协同分析结果 -->
    <el-dialog v-model="showAgentResult" title="🤖 7-Agent 协同商机分析" width="900px" top="5vh">
      <div v-loading="agentLoading">
        <div v-if="agentData" class="agent-result">
          <div class="agent-score-bar">
            <span class="score-label">综合评分</span>
            <span class="score-value">{{ agentData.final_score || 0 }}</span>
            <span class="score-summary">{{ agentData.final_summary }}</span>
          </div>

          <el-row :gutter="12">
            <el-col :span="12">
              <el-card shadow="hover" class="agent-card">
                <template #header><span class="agent-title">1️⃣ 信息分类</span></template>
                <div v-if="agentData.agent1_classification">
                  <el-tag :type="categoryTagType(agentData.agent1_classification.category)" size="large">
                    {{ agentData.agent1_classification.category }}
                  </el-tag>
                  <div class="agent-reason">置信度：{{ (agentData.agent1_classification.confidence||0).toFixed(2) }} · {{ agentData.agent1_classification.reason }}</div>
                </div>
              </el-card>
            </el-col>
            <el-col :span="12">
              <el-card shadow="hover" class="agent-card">
                <template #header><span class="agent-title">2️⃣ 业务分类</span></template>
                <div v-if="agentData.agent2_business">
                  <div style="margin-bottom:6px">
                    <el-tag v-for="b in (agentData.agent2_business.business_tags||[])" :key="b" type="success" size="small"
                            style="margin-right:4px;margin-bottom:2px">{{ b }}</el-tag>
                  </div>
                  <div class="agent-reason">主业务：{{ agentData.agent2_business.primary_business }} · {{ agentData.agent2_business.reason }}</div>
                </div>
              </el-card>
            </el-col>
          </el-row>

          <el-card shadow="hover" class="agent-card" style="margin-top:12px">
            <template #header><span class="agent-title">3️⃣ 实体识别</span></template>
            <div v-if="agentData.agent3_entities" class="entity-grid">
              <div v-for="key in ['projects','customers','enterprises','competitors','suppliers','regions','amounts','times']" :key="key"
                   v-show="(agentData.agent3_entities[key]||[]).length">
                <span class="entity-label">{{ entityLabels[key] }}：</span>
                <el-tag v-for="(v,i) in agentData.agent3_entities[key]" :key="i" size="small" :type="entityTagType(key)"
                        style="margin:2px">{{ v }}</el-tag>
              </div>
            </div>
          </el-card>

          <el-card shadow="hover" class="agent-card" style="margin-top:12px">
            <template #header><span class="agent-title">4️⃣ 项目分析</span></template>
            <el-descriptions :column="1" border size="small" v-if="agentData.agent4_project">
              <el-descriptions-item label="采购内容">{{ agentData.agent4_project.procurement_content }}</el-descriptions-item>
              <el-descriptions-item label="客户需求">{{ agentData.agent4_project.customer_needs }}</el-descriptions-item>
              <el-descriptions-item label="预算">{{ agentData.agent4_project.budget }}</el-descriptions-item>
              <el-descriptions-item label="采购阶段">{{ agentData.agent4_project.procurement_stage }}</el-descriptions-item>
              <el-descriptions-item label="项目时间">{{ agentData.agent4_project.project_timeline }}</el-descriptions-item>
            </el-descriptions>
          </el-card>

          <el-card shadow="hover" class="agent-card" style="margin-top:12px">
            <template #header>
              <span class="agent-title">5️⃣ 我方能力匹配</span>
              <el-tag v-if="agentData.agent5_capability" :type="agentData.agent5_capability.can_do ? 'success' : 'danger'"
                      style="margin-left:8px">{{ agentData.agent5_capability.can_do ? '能做' : '不能做' }}</el-tag>
            </template>
            <div v-if="agentData.agent5_capability">
              <div v-if="(agentData.agent5_capability.matched_products||[]).length" style="margin-bottom:6px">
                <span class="entity-label">匹配产品：</span>
                <el-tag v-for="p in agentData.agent5_capability.matched_products" :key="p" type="primary" size="small"
                        style="margin:2px">{{ p }}</el-tag>
              </div>
              <div v-if="agentData.agent5_capability.capability_gap" class="agent-reason">能力差距：{{ agentData.agent5_capability.capability_gap }}</div>
              <div class="agent-reason">判断理由：{{ agentData.agent5_capability.reason }}</div>
            </div>
          </el-card>

          <el-card shadow="hover" class="agent-card" style="margin-top:12px">
            <template #header><span class="agent-title">6️⃣ 商机评分（7维度）</span></template>
            <div v-if="agentData.agent6_scoring" class="score-dims">
              <div v-for="(val, key) in (agentData.agent6_scoring.dimensions||{})" :key="key" class="score-dim-item">
                <div class="dim-label">{{ dimLabels[key] || key }}</div>
                <el-progress :percentage="val" :stroke-width="14" :color="scoreColor(val)" />
              </div>
              <div class="agent-reason" style="margin-top:8px">评分理由：{{ agentData.agent6_scoring.reason }}</div>
            </div>
          </el-card>

          <el-card shadow="hover" class="agent-card" style="margin-top:12px">
            <template #header><span class="agent-title">7️⃣ 销售建议</span></template>
            <el-descriptions :column="1" border size="small" v-if="agentData.agent7_suggestion">
              <el-descriptions-item label="为什么值得跟">{{ agentData.agent7_suggestion.why_follow }}</el-descriptions-item>
              <el-descriptions-item label="什么时候跟">{{ agentData.agent7_suggestion.when_to_follow }}</el-descriptions-item>
              <el-descriptions-item label="找谁">{{ agentData.agent7_suggestion.who_to_contact }}</el-descriptions-item>
              <el-descriptions-item label="怎么切入">{{ agentData.agent7_suggestion.how_to_enter }}</el-descriptions-item>
              <el-descriptions-item label="准备什么">{{ agentData.agent7_suggestion.what_to_prepare }}</el-descriptions-item>
              <el-descriptions-item label="可能竞争对手">
                <el-tag v-for="(c,i) in (agentData.agent7_suggestion.potential_competitors||[])" :key="i" type="danger" size="small"
                        style="margin-right:4px">{{ c }}</el-tag>
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </div>
        <el-empty v-else-if="!agentLoading" description="暂无分析结果" />
      </div>
      <template #footer>
        <el-button v-if="currentAgentId" type="warning" :loading="agentAnalyzingId===currentAgentId"
                   @click="agentAnalyze(currentAgentId, true)">🔄 重新分析</el-button>
        <el-button @click="showAgentResult=false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const router = useRouter()

const loading = ref(false)
const list = ref([])
const total = ref(0)
const page = ref(1)
const perPage = ref(20)
const search = ref('')
const filterStatus = ref('')
const stats = ref({})
const showDetail = ref(false)
const detail = ref(null)
const sources = ref([])
const selectedSourceId = ref('')
const collecting = ref(false)
const collectingAll = ref(false)
const parsingId = ref(null)
const selection = ref([])
const deleting = ref(false)
const agentAnalyzingId = ref(null)
const showAgentResult = ref(false)
const agentLoading = ref(false)
const agentData = ref(null)
const currentAgentId = ref(null)

const entityLabels = {
  projects: '项目', customers: '客户', enterprises: '企业',
  competitors: '竞争对手', suppliers: '供应商', regions: '地区',
  amounts: '金额', times: '时间'
}
const dimLabels = {
  business_match: '业务匹配度', customer_value: '客户价值', budget_amount: '预算金额',
  project_stage: '项目阶段', time_urgency: '时间紧迫度',
  region_match: '区域匹配度', competition: '竞争情况'
}
function categoryTagType(cat) {
  const m = { '商机': 'danger', '采购意向': 'warning', '招标': 'primary', '中标': 'success',
             '新闻': 'info', '客户动态': '', '竞争对手动态': 'info', '普通信息': 'info' }
  return m[cat] || 'info'
}
function entityTagType(key) {
  const m = { projects: 'primary', customers: 'success', enterprises: '',
             competitors: 'danger', suppliers: 'warning', regions: 'info',
             amounts: 'success', times: 'info' }
  return m[key] || ''
}
function scoreColor(val) {
  if (val >= 80) return '#67c23a'
  if (val >= 60) return '#409eff'
  if (val >= 40) return '#e6a23c'
  return '#f56c6c'
}

function onSelectionChange(rows) {
  selection.value = rows
}

async function batchDelete() {
  if (!selection.value.length) return
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selection.value.length} 条情报？`, '批量删除', { type: 'warning' })
  } catch { return }
  deleting.value = true
  try {
    const res = await api.post('/intelligence/batch-delete', { ids: selection.value.map(r => r.id) })
    if (res && res.code === 200) {
      ElMessage.success(res.message || '删除成功')
      selection.value = []
      loadData()
      loadStats()
    } else {
      ElMessage.error((res && res.message) || '删除失败')
    }
  } finally {
    deleting.value = false
  }
}

const statusLabels = { pending: '待处理', processing: '处理中', analyzed: '已分析', invalid: '无效' }
const statusTypes = { pending: 'warning', processing: 'primary', analyzed: 'success', invalid: 'info' }

function statusLabel(s) { return statusLabels[s] || s }
function statusType(s) { return statusTypes[s] || '' }

function parseMatched(val) {
  if (!val) return []
  return String(val).split(',').map(s => s.trim()).filter(Boolean)
}

async function loadData() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: perPage.value }
    if (search.value) params.search = search.value
    if (filterStatus.value) params.status = filterStatus.value
    const res = await api.get('/intelligence', params)
    list.value = res.data || []
    total.value = res.total || 0
  } catch (e) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    const res = await api.get('/intelligence/stats')
    stats.value = res.data || {}
  } catch (e) {
    // 忽略
  }
}

async function loadSources() {
  try {
    const res = await api.get('/data-sources', { page: 1, page_size: 200 })
    const allSources = res.data || []
    sources.value = allSources.filter(s => s.parser_type)
  } catch (e) {
    // 忽略
  }
}

async function collectOne() {
  if (!selectedSourceId.value) {
    ElMessage.warning('请先选择数据源')
    return
  }
  collecting.value = true
  try {
    const res = await api.longPost(`/intelligence/collect/${selectedSourceId.value}?fetch_detail=1`)
    const d = res.data || {}
    ElMessage.success(`采集完成：共${d.collected||0}条，新增${d.new||0}条，重复${d.duplicate||0}条${d.filtered ? `，关键词无关过滤${d.filtered}条` : ''}`)
    loadData()
    loadStats()
  } catch (e) {
    ElMessage.error('采集失败：' + (e.response?.data?.message || e.message))
  } finally {
    collecting.value = false
  }
}

async function collectAll() {
  collectingAll.value = true
  try {
    const res = await api.longPost('/intelligence/collect-all')
    const results = res.data || []
    const ok = results.filter(r => !r.error)
    const fail = results.filter(r => r.error)
    const filteredTotal = ok.reduce((s, r) => s + (r.filtered || 0), 0)
    let msg = `批量采集完成：${ok.length}个源成功`
    if (fail.length) msg += `，${fail.length}个失败`
    if (filteredTotal) msg += `，关键词无关过滤${filteredTotal}条`
    ElMessage.success(msg)
    loadData()
    loadStats()
  } catch (e) {
    ElMessage.error('批量采集失败：' + (e.response?.data?.message || e.message))
  } finally {
    collectingAll.value = false
  }
}

async function viewDetail(id) {
  try {
    const res = await api.get(`/intelligence/${id}`)
    detail.value = res.data
    showDetail.value = true
  } catch (e) {
    ElMessage.error('加载详情失败')
  }
}

function viewLead(row) {
  // 跳转到 AI商机识别 tab，并预填搜索标题快速定位
  router.push({ path: '/intelligence', query: { tab: 'ai-leads', search: row.title || '' } })
}

async function deleteItem(id) {
  try {
    await ElMessageBox.confirm('确认删除？', '提示')
    await api.delete(`/intelligence/${id}`)
    ElMessage.success('已删除')
    loadData()
    loadStats()
  } catch (e) {
    // 取消
  }
}

async function parseAttachment(id) {
  parsingId.value = id
  try {
    const res = await api.longPost(`/intelligence/parse-attachment/${id}`)
    const d = res.data || {}
    ElMessage.success(`附件解析完成：${d.parsed_count||0}个文件，提取${d.text_length||0}字符`)
    if (showDetail.value && detail.value?.id === id) {
      viewDetail(id)
    }
  } catch (e) {
    ElMessage.error('附件解析失败：' + (e.response?.data?.message || e.message))
  } finally {
    parsingId.value = null
  }
}

async function openAgentResult(row) {
  currentAgentId.value = row.id
  agentLoading.value = true
  showAgentResult.value = true
  agentData.value = null
  await loadAgentResult(row.id)
  agentLoading.value = false
}

async function agentAnalyze(id, force = false) {
  currentAgentId.value = id
  agentAnalyzingId.value = id
  agentLoading.value = true
  showAgentResult.value = true
  agentData.value = null
  try {
    const url = force ? `/intelligence/agent-analyze/${id}?force=true` : `/intelligence/agent-analyze/${id}`
    const res = await api.longPost(url)
    if (res && res.code === 200 && res.data) {
      agentData.value = res.data
      if (res.message && res.message.includes('已分析过')) {
        // 未传 force 时后端自动跳过已分析的，直接返回已有结果
        ElMessage.info('该情报已分析过，直接展示已有结果（点"🔄 重新分析"可强制重跑）')
      } else {
        ElMessage.success(`7-Agent分析${force ? '(重新)' : ''}完成，评分：${res.data.final_score || 0}`)
      }
      loadData()
      loadStats()
    } else if (res && res.message) {
      ElMessage.info(res.message)
      await loadAgentResult(id)
    } else {
      ElMessage.error('分析失败')
    }
  } catch (e) {
    ElMessage.error('7-Agent分析失败：' + (e.response?.data?.message || e.message))
  } finally {
    agentAnalyzingId.value = null
    agentLoading.value = false
  }
}

async function loadAgentResult(id) {
  try {
    const res = await api.get(`/intelligence/agent-result/${id}`)
    if (res && res.code === 200 && res.data) {
      agentData.value = res.data
    } else {
      ElMessage.warning('该情报尚无7-Agent分析结果，请先点击"🤖 7-Agent分析"')
    }
  } catch (e) {
    ElMessage.error('加载分析结果失败')
  }
}

// 一键7-Agent分析：逐条分析所有待处理情报（排除中标类），实时显示进度
const batchAgentRunning = ref(false)
const batchAgentProgress = ref({ done: 0, total: 0, success: 0, failed: 0 })
const WIN_KEYWORDS = ['中标', '成交结果', '结果公告', '结果公示']

async function agentAnalyzeAll() {
  if (batchAgentRunning.value) return
  // 取待分析列表（排除已中标公告）
  const res = await api.get('/intelligence', { status: 'pending', page: 1, per_page: 100 })
  const items = (res.data || []).filter(it => !WIN_KEYWORDS.some(kw => (it.title || '').includes(kw)))
  if (!items.length) {
    ElMessage.info('没有待分析的情报（中标结果公告已自动排除）')
    return
  }
  const confirmed = await ElMessageBox.confirm(
    `共 ${items.length} 条待分析情报，每条需 7 次 AI 调用（约 1-2 分钟/条），全程预计 ${Math.ceil(items.length * 1.5)} 分钟。期间请勿关闭页面。`,
    '一键7-Agent分析',
    { confirmButtonText: '开始分析', cancelButtonText: '取消', type: 'info' }
  ).catch(() => null)
  if (!confirmed) return

  batchAgentRunning.value = true
  batchAgentProgress.value = { done: 0, total: items.length, success: 0, failed: 0 }
  for (const it of items) {
    try {
      const r = await api.longPost(`/intelligence/agent-analyze/${it.id}`)
      if (r && r.code === 200) batchAgentProgress.value.success++
      else batchAgentProgress.value.failed++
    } catch (e) {
      batchAgentProgress.value.failed++
      console.warn(`情报#${it.id} 分析失败:`, e?.response?.data?.message || e.message)
    }
    batchAgentProgress.value.done++
    loadData()  // 每条完成刷新列表，状态实时可见
  }
  batchAgentRunning.value = false
  const p = batchAgentProgress.value
  ElMessage.success(`一键分析完成：成功 ${p.success} 条，失败 ${p.failed} 条`)
  loadStats()
}

onMounted(() => {
  loadData()
  loadStats()
  loadSources()
})
</script>

<style scoped>
.intel-page { padding: 16px; }
.card-header { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.filter-bar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.content-box { white-space: pre-wrap; max-height: 400px; overflow-y: auto; background: #f5f7fa; padding: 12px; border-radius: 4px; }
.agent-result { max-height: 75vh; overflow-y: auto; padding-right: 4px; }
.agent-score-bar { display: flex; align-items: center; gap: 12px; background: linear-gradient(135deg, #667eea, #764ba2); color: #fff; padding: 14px 18px; border-radius: 8px; margin-bottom: 12px; }
.score-label { font-size: 14px; opacity: 0.9; }
.score-value { font-size: 32px; font-weight: 700; }
.score-summary { flex: 1; font-size: 13px; opacity: 0.95; }
.agent-card { margin: 0; }
.agent-card :deep(.el-card__header) { padding: 10px 14px; background: #f0f5ff; }
.agent-title { font-weight: 600; color: #303133; }
.agent-reason { font-size: 12px; color: #909399; margin-top: 6px; line-height: 1.5; }
.entity-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; }
.entity-label { font-size: 12px; color: #606266; font-weight: 600; }
.score-dims { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 20px; }
.score-dim-item { display: flex; align-items: center; gap: 8px; }
.dim-label { width: 90px; font-size: 12px; color: #606266; flex-shrink: 0; }
.score-dim-item :deep(.el-progress) { flex: 1; }
</style>
