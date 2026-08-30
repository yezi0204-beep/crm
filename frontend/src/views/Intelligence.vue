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
        <el-table-column label="操作" width="180">
          <template #default="{row}">
            <el-button size="small" @click="viewDetail(row.id)">详情</el-button>
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
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

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
    const res = await api.get('/leads/sources', { per_page: 200 })
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
</style>
