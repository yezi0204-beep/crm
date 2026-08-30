<template>
  <div class="leads-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>🎯 AI商机识别</span>
          <el-button v-if="isManager" type="primary" :loading="analyzing" @click="analyzeBatch" style="margin-left:auto">
            批量AI分析
          </el-button>
          <el-button type="success" :loading="converting" @click="convertBatch">
            批量转入CRM
          </el-button>
          <el-button v-if="isManager" type="danger" :loading="deleting" :disabled="!selection.length" @click="batchDelete">
            批量删除{{ selection.length ? `(${selection.length})` : '' }}
          </el-button>
        </div>
      </template>

      <div class="filter-bar">
        <el-input v-model="search" placeholder="搜索标题/客户/摘要" clearable style="width:260px"
                  @keyup.enter="loadData" @clear="loadData" />
        <el-select v-model="filterRelevant" placeholder="相关性" clearable style="width:110px" @change="loadData">
          <el-option label="相关" :value="1" />
          <el-option label="不相关" :value="0" />
        </el-select>
        <el-select v-model="filterScore" placeholder="最低分" clearable style="width:100px" @change="loadData">
          <el-option label="≥80" :value="80" />
          <el-option label="≥60" :value="60" />
          <el-option label="≥40" :value="40" />
          <el-option label="≥20" :value="20" />
        </el-select>
        <el-radio-group v-model="sortBy" @change="loadData" style="margin-left:8px">
          <el-radio-button label="score">按评分</el-radio-button>
          <el-radio-button label="created_at">按时间</el-radio-button>
        </el-radio-group>
        <el-button @click="loadData">搜索</el-button>
      </div>

      <el-table :data="list" v-loading="loading" border style="margin-top:12px" @selection-change="onSelectionChange">
        <el-table-column v-if="isManager" type="selection" width="45" />
        <el-table-column label="评分" width="70" align="center">
          <template #default="{row}">
            <div :class="['score-badge', scoreClass(row.score)]">{{ row.score }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="280" show-overflow-tooltip />
        <el-table-column prop="buyer" label="采购单位" width="160" show-overflow-tooltip />
        <el-table-column prop="budget" label="预算" width="100" />
        <el-table-column prop="deadline" label="截止日期" width="100" />
        <el-table-column prop="procurement_method" label="采购方式" width="110" />
        <el-table-column label="竞争对手" width="120">
          <template #default="{row}">
            <span v-if="parseCompetitors(row.competitors).length">
              {{ parseCompetitors(row.competitors).slice(0,2).join(', ') }}
              <span v-if="parseCompetitors(row.competitors).length > 2">等{{ parseCompetitors(row.competitors).length }}家</span>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{row}">
            <el-tag v-if="row.status === 'converted'" type="success" size="small">已入CRM</el-tag>
            <el-tag v-else-if="row.status === 'rejected'" type="danger" size="small">已作废</el-tag>
            <el-tag v-else :type="row.is_relevant ? 'primary' : 'info'" size="small">
              {{ row.is_relevant ? '相关' : '不相关' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260">
          <template #default="{row}">
            <el-button size="small" @click="viewDetail(row.id)">详情</el-button>
            <el-button v-if="row.status !== 'converted' && row.status !== 'rejected'" size="small" type="success"
                       :loading="convertingId===row.id" @click="convertOne(row.id)">转入CRM</el-button>
            <el-button v-if="isManager && row.status !== 'converted' && row.status !== 'rejected'" size="small" type="danger"
                       @click="openReject(row)">作废</el-button>
            <el-button v-if="isManager && row.status === 'rejected'" size="small" type="warning"
                       :loading="restoringId===row.id" @click="restoreOne(row.id)">恢复</el-button>
            <el-button v-if="isManager" size="small" type="danger" text
                       :loading="deletingId===row.id" @click="deleteOne(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination v-model:current-page="page" :page-size="perPage" :total="total"
                     layout="total, prev, pager, next" @current-change="loadData"
                     style="margin-top:12px;justify-content:center" />
    </el-card>

    <el-dialog v-model="showDetail" title="商机详情" width="850px" top="5vh">
      <el-descriptions :column="2" border v-if="detail">
        <el-descriptions-item label="标题" :span="2">{{ detail.title }}</el-descriptions-item>
        <el-descriptions-item label="评分">
          <span :class="['score-badge', scoreClass(detail.score)]">{{ detail.score }}</span>
          <span style="margin-left:8px;color:#909399">{{ detail.score_reason }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="相关性">
          <el-tag :type="detail.is_relevant ? 'success' : 'info'">
            {{ detail.is_relevant ? '相关商机' : '不相关' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="采购单位">{{ detail.buyer || '-' }}</el-descriptions-item>
        <el-descriptions-item label="预算金额">{{ detail.budget || '-' }}</el-descriptions-item>
        <el-descriptions-item label="截止日期">{{ detail.deadline || '-' }}</el-descriptions-item>
        <el-descriptions-item label="项目类型">{{ detail.project_type || '-' }}</el-descriptions-item>
        <el-descriptions-item label="采购方式">{{ detail.procurement_method || '-' }}</el-descriptions-item>
        <el-descriptions-item label="地区">{{ detail.region || '-' }}</el-descriptions-item>
        <el-descriptions-item label="联系人">{{ detail.contact_person || '-' }}</el-descriptions-item>
        <el-descriptions-item label="联系电话">{{ detail.contact_phone || '-' }}</el-descriptions-item>
        <el-descriptions-item label="来源">{{ detail.source_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="URL" :span="2">
          <a :href="detail.url" target="_blank" style="color:#409eff">{{ detail.url }}</a>
        </el-descriptions-item>
        <el-descriptions-item label="命中关键词" :span="2">
          <el-tag v-for="kw in parseList(detail.keywords_matched)" :key="kw" size="small" style="margin:2px">{{ kw }}</el-tag>
          <span v-if="!parseList(detail.keywords_matched).length">-</span>
        </el-descriptions-item>
        <el-descriptions-item label="竞争对手" :span="2">
          <el-tag v-for="c in parseCompetitors(detail.competitors)" :key="c" type="warning" size="small" style="margin:2px">{{ c }}</el-tag>
          <span v-if="!parseCompetitors(detail.competitors).length">-</span>
        </el-descriptions-item>
        <el-descriptions-item label="AI分析" :span="2">{{ detail.analysis_summary || '-' }}</el-descriptions-item>
        <el-descriptions-item label="原文正文" :span="2">
          <div class="content-box">{{ detail.raw_content || detail.snippet || '-' }}</div>
        </el-descriptions-item>
        <el-descriptions-item v-if="detail.status === 'rejected'" label="作废原因" :span="2">
          <span style="color:#f56c6c">{{ detail.reject_reason || '-' }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>

    <!-- 作废对话框 -->
    <el-dialog v-model="showReject" title="商机作废" width="500px">
      <div style="line-height:2">
        <p style="color:#606266">确定要作废以下商机吗？</p>
        <p style="font-weight:bold;background:#f5f7fa;padding:8px;border-radius:4px">{{ rejectRow?.title }}</p>
        <p style="color:#f56c6c;margin-top:12px">* 请填写作废原因（必填）：</p>
        <el-input v-model="rejectReason" type="textarea" :rows="3"
                  placeholder="例如：重复商机/信息有误/已过期/非目标客户等" />
      </div>
      <template #footer>
        <el-button @click="showReject = false">取消</el-button>
        <el-button type="danger" :loading="rejecting" @click="confirmReject">确认作废</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
// 权限点驱动：data.view_all 拥有全部权限；应用中心成员仅可查看+导入CRM（intel.import）
const isManager = computed(() => authStore.has('data.view_all'))

const loading = ref(false)
const analyzing = ref(false)
const converting = ref(false)
const convertingId = ref(null)
const restoringId = ref(null)
const showReject = ref(false)
const rejectRow = ref(null)
const rejectReason = ref('')
const rejecting = ref(false)
const list = ref([])
const total = ref(0)
const page = ref(1)
const perPage = ref(20)
const search = ref('')
const filterRelevant = ref(null)
const filterScore = ref(null)
const sortBy = ref('score')
const showDetail = ref(false)
const detail = ref(null)

function scoreClass(s) {
  if (s >= 80) return 'score-high'
  if (s >= 60) return 'score-mid'
  if (s >= 40) return 'score-low'
  return 'score-vlow'
}

function parseList(val) {
  if (!val) return []
  if (Array.isArray(val)) return val
  try { return JSON.parse(val) || [] } catch { return [] }
}

function parseCompetitors(val) {
  return parseList(val)
}

async function loadData() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: perPage.value, sort: sortBy.value }
    if (search.value) params.search = search.value
    if (filterRelevant.value !== null && filterRelevant.value !== '') params.is_relevant = filterRelevant.value
    if (filterScore.value) params.min_score = filterScore.value
    const res = await api.get('/intelligence/leads', params)
    list.value = res.data || []
    total.value = res.total || 0
  } catch (e) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function analyzeBatch() {
  analyzing.value = true
  try {
    const res = await api.longPost('/intelligence/analyze-batch?limit=20')
    const d = res.data || {}
    ElMessage.success(`分析完成：共${d.analyzed||0}条，成功${d.success||0}条，失败${d.failed||0}条`)
    loadData()
  } catch (e) {
    ElMessage.error('分析失败：' + (e.response?.data?.message || e.message))
  } finally {
    analyzing.value = false
  }
}

async function convertOne(id) {
  convertingId.value = id
  try {
    const res = await api.post(`/intelligence/leads/${id}/convert`)
    const d = res.data || {}
    if (d.duplicate) {
      ElMessage.info('该商机已在CRM中存在，已自动关联')
    } else {
      ElMessage.success(`已转入CRM：${d.company || ''}`)
    }
    loadData()
  } catch (e) {
    ElMessage.error('转入失败：' + (e.response?.data?.message || e.message))
  } finally {
    convertingId.value = null
  }
}

function openReject(row) {
  rejectRow.value = row
  rejectReason.value = ''
  showReject.value = true
}

async function confirmReject() {
  if (!rejectReason.value.trim()) {
    ElMessage.warning('请填写作废原因')
    return
  }
  rejecting.value = true
  try {
    await api.post(`/intelligence/leads/${rejectRow.value.id}/reject`, { reason: rejectReason.value.trim() })
    ElMessage.success('商机已作废')
    showReject.value = false
    loadData()
  } catch (e) {
    ElMessage.error('作废失败：' + (e.response?.data?.message || e.message))
  } finally {
    rejecting.value = false
  }
}

async function restoreOne(id) {
  restoringId.value = id
  try {
    await api.post(`/intelligence/leads/${id}/restore`)
    ElMessage.success('商机已恢复')
    loadData()
  } catch (e) {
    ElMessage.error('恢复失败：' + (e.response?.data?.message || e.message))
  } finally {
    restoringId.value = null
  }
}

// ==================== 删除 ====================
const selection = ref([])
const deleting = ref(false)
const deletingId = ref(null)

function onSelectionChange(rows) {
  selection.value = rows
}

async function deleteOne(row) {
  try {
    await ElMessageBox.confirm(`确定删除商机「${row.title?.slice(0, 40) || row.id}」？删除后不可恢复`, '删除商机', { type: 'warning' })
  } catch { return }
  deletingId.value = row.id
  try {
    const res = await api.delete(`/intelligence/leads/${row.id}`)
    if (res && res.code === 200) {
      ElMessage.success(res.message || '已删除')
      selection.value = []
      loadData()
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
    await ElMessageBox.confirm(`确认删除选中的 ${selection.value.length} 条商机？删除后不可恢复`, '批量删除', { type: 'warning' })
  } catch { return }
  deleting.value = true
  try {
    const res = await api.post('/intelligence/leads/batch-delete', { ids: selection.value.map(r => r.id) })
    if (res && res.code === 200) {
      ElMessage.success(res.message || '删除成功')
      selection.value = []
      loadData()
    } else {
      ElMessage.error((res && res.message) || '删除失败')
    }
  } catch (e) {
    ElMessage.error('批量删除失败：' + (e.response?.data?.message || e.message))
  } finally {
    deleting.value = false
  }
}

async function convertBatch() {
  converting.value = true
  try {
    const res = await api.post('/intelligence/leads/convert-batch', {
      only_relevant: true,
      min_score: filterScore.value || 0,
    })
    const d = res.data || {}
    ElMessage.success(`批量转入完成：新增${d.converted||0}条，跳过${d.skipped||0}条`)
    loadData()
  } catch (e) {
    ElMessage.error('批量转入失败：' + (e.response?.data?.message || e.message))
  } finally {
    converting.value = false
  }
}

async function viewDetail(id) {
  try {
    const res = await api.get(`/intelligence/leads/${id}`)
    detail.value = res.data
    showDetail.value = true
  } catch (e) {
    ElMessage.error('加载详情失败')
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.leads-page { padding: 16px; }
.card-header { display: flex; align-items: center; }
.filter-bar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.content-box { white-space: pre-wrap; max-height: 300px; overflow-y: auto; background: #f5f7fa; padding: 12px; border-radius: 4px; }
.score-badge { display: inline-block; width: 32px; height: 32px; line-height: 32px; border-radius: 50%; text-align: center; font-weight: bold; color: #fff; }
.score-high { background: #f56c6c; }
.score-mid { background: #e6a23c; }
.score-low { background: #409eff; }
.score-vlow { background: #909399; }
</style>
