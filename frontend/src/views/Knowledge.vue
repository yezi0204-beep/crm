<template>
  <div class="knowledge-container">
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">📚 企业知识库</h2>
        <p class="page-desc">AI 拜访复盘、跟进洞察与销售经验沉淀的企业知识资产</p>
      </div>
      <div class="header-right">
        <el-button type="primary" @click="openCreateDialog">
          <span>✚</span><span>新建知识</span>
        </el-button>
      </div>
    </div>

    <div class="filter-bar">
      <el-select v-model="filterCategory" placeholder="全部分类" clearable @change="fetchList" style="width:160px">
        <el-option v-for="c in categories" :key="c.value" :label="c.label" :value="c.value" />
      </el-select>
      <el-input v-model="keyword" placeholder="搜索标题/摘要/标签..." clearable @clear="fetchList" @keyup.enter="fetchList" style="width:280px">
        <template #append><el-button @click="fetchList">搜索</el-button></template>
      </el-input>
      <div class="stat-info">共 {{ list.length }} 条知识</div>
    </div>

    <div class="knowledge-grid" v-loading="loading">
      <div v-if="!list.length && !loading" class="empty-state">
        <div class="empty-icon">📚</div>
        <div class="empty-text">暂无知识记录</div>
        <div class="empty-desc">完成拜访后可通过 AI 自动生成复盘，或手动新建知识</div>
      </div>

      <div v-for="item in list" :key="item.id" class="knowledge-card" @click="openDetail(item)">
        <div class="card-header">
          <span :class="['category-badge', 'cat-' + item.category]">{{ categoryLabel(item.category) }}</span>
          <span class="card-date">{{ formatDate(item.created_at) }}</span>
        </div>
        <div class="card-title">{{ item.title }}</div>
        <div class="card-summary">{{ item.summary || '暂无摘要' }}</div>
        <div class="card-footer">
          <span class="card-meta" v-if="item.customer_company">🏢 {{ item.customer_company }}</span>
          <span class="card-meta" v-if="item.owner_name">✍️ {{ item.owner_name }}</span>
          <div class="card-actions" @click.stop>
            <el-button text size="small" @click="openEditDialog(item)">编辑</el-button>
            <el-button text size="small" type="danger" @click="handleDelete(item)">删除</el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- 详情对话框 -->
    <el-dialog v-model="detailVisible" title="知识详情" width="700px" top="6vh">
      <div v-if="current" class="detail-content">
        <div class="detail-title">{{ current.title }}</div>
        <div class="detail-meta">
          <span :class="['category-badge', 'cat-' + current.category]">{{ categoryLabel(current.category) }}</span>
          <span v-if="current.customer_company">🏢 {{ current.customer_company }}</span>
          <span v-if="current.owner_name">✍️ {{ current.owner_name }}</span>
          <span>🕐 {{ formatDate(current.created_at) }}</span>
        </div>
        <div class="detail-summary" v-if="current.summary">{{ current.summary }}</div>
        <div class="detail-body" v-if="parsedContent">
          <template v-if="typeof parsedContent === 'object'">
            <div v-if="parsedContent.key_findings && parsedContent.key_findings.length" class="detail-section">
              <div class="section-title">🔍 关键发现</div>
              <ul><li v-for="(f, i) in parsedContent.key_findings" :key="i">{{ f }}</li></ul>
            </div>
            <div v-if="parsedContent.customer_needs && parsedContent.customer_needs.length" class="detail-section">
              <div class="section-title">💡 客户需求</div>
              <ul><li v-for="(f, i) in parsedContent.customer_needs" :key="i">{{ f }}</li></ul>
            </div>
            <div v-if="parsedContent.next_actions && parsedContent.next_actions.length" class="detail-section">
              <div class="section-title">📌 下一步行动</div>
              <ul><li v-for="(f, i) in parsedContent.next_actions" :key="i">{{ f }}</li></ul>
            </div>
            <div v-if="parsedContent.risk_warnings && parsedContent.risk_warnings.length" class="detail-section">
              <div class="section-title">⚠️ 风险提示</div>
              <ul><li v-for="(f, i) in parsedContent.risk_warnings" :key="i">{{ f }}</li></ul>
            </div>
            <div v-if="parsedContent.deal_signals" class="detail-section">
              <div class="section-title">🎯 成交信号</div>
              <div>{{ parsedContent.deal_signals }}</div>
            </div>
          </template>
          <template v-else>
            <div class="detail-text">{{ current.content }}</div>
          </template>
        </div>
      </div>
    </el-dialog>

    <!-- 新建/编辑对话框 -->
    <el-dialog v-model="formVisible" :title="form.id ? '编辑知识' : '新建知识'" width="600px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="标题" required>
          <el-input v-model="form.title" placeholder="请输入标题" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category" style="width:100%">
            <el-option v-for="c in categories" :key="c.value" :label="c.label" :value="c.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="摘要">
          <el-input v-model="form.summary" type="textarea" :rows="2" placeholder="一句话概括" />
        </el-form-item>
        <el-form-item label="内容" required>
          <el-input v-model="form.content" type="textarea" :rows="6" placeholder="详细内容" />
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="form.tags" placeholder="多个标签用逗号分隔" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const list = ref([])
const loading = ref(false)
const keyword = ref('')
const filterCategory = ref('')
const detailVisible = ref(false)
const formVisible = ref(false)
const current = ref(null)
const form = ref({ id: null, title: '', category: 'sales_skill', summary: '', content: '', tags: '' })

const categories = [
  { value: 'visit_summary', label: '拜访复盘' },
  { value: 'followup_insight', label: '跟进洞察' },
  { value: 'sales_skill', label: '销售技巧' },
  { value: 'customer_case', label: '客户案例' }
]
const categoryLabel = (v) => categories.find(c => c.value === v)?.label || v

const formatDate = (s) => {
  if (!s) return ''
  return s.replace('T', ' ').substring(0, 16)
}

const parsedContent = computed(() => {
  if (!current.value || !current.value.content) return null
  try { return JSON.parse(current.value.content) } catch (e) { return current.value.content }
})

const fetchList = async () => {
  loading.value = true
  try {
    const params = {}
    if (filterCategory.value) params.category = filterCategory.value
    if (keyword.value) params.keyword = keyword.value
    const resp = await api.get('/knowledge', params)
    if (resp.code === 200) list.value = resp.data
    else ElMessage.error(resp.message)
  } catch (e) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

const openDetail = async (item) => {
  try {
    const resp = await api.get(`/knowledge/${item.id}`)
    if (resp.code === 200) { current.value = resp.data; detailVisible.value = true }
  } catch (e) { ElMessage.error('加载详情失败') }
}

const openCreateDialog = () => {
  form.value = { id: null, title: '', category: 'sales_skill', summary: '', content: '', tags: '' }
  formVisible.value = true
}

const openEditDialog = (item) => {
  // 先取详情获取完整 content
  api.get(`/knowledge/${item.id}`).then(resp => {
    if (resp.code === 200) {
      const d = resp.data
      form.value = { id: d.id, title: d.title, category: d.category, summary: d.summary || '', content: d.content, tags: d.tags || '' }
      formVisible.value = true
    }
  })
}

const handleSave = async () => {
  if (!form.value.title || !form.value.content) { ElMessage.warning('标题和内容不能为空'); return }
  try {
    const payload = { ...form.value }
    if (payload.id) {
      const resp = await api.put(`/knowledge/${payload.id}`, payload)
      if (resp.code === 200) { ElMessage.success('更新成功'); formVisible.value = false; fetchList() }
      else ElMessage.error(resp.message)
    } else {
      const resp = await api.post('/knowledge', payload)
      if (resp.code === 200) { ElMessage.success('创建成功'); formVisible.value = false; fetchList() }
      else ElMessage.error(resp.message)
    }
  } catch (e) { ElMessage.error('保存失败') }
}

const handleDelete = async (item) => {
  try {
    await ElMessageBox.confirm(`确定删除「${item.title}」？`, '提示', { type: 'warning' })
    const resp = await api.delete(`/knowledge/${item.id}`)
    if (resp.code === 200) { ElMessage.success('删除成功'); fetchList() }
    else ElMessage.error(resp.message)
  } catch (e) { /* cancelled */ }
}

onMounted(() => { fetchList() })
</script>

<style scoped>
.knowledge-container { padding: 0; }

.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.page-title { font-size: 22px; font-weight: 600; color: #1e293b; margin: 0; }
.page-desc { font-size: 13px; color: #64748b; margin: 6px 0 0; }

.filter-bar { display: flex; gap: 12px; align-items: center; margin-bottom: 20px; }
.stat-info { margin-left: auto; font-size: 13px; color: #94a3b8; }

.knowledge-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }

.empty-state { grid-column: 1 / -1; text-align: center; padding: 60px 20px; color: #94a3b8; }
.empty-icon { font-size: 48px; margin-bottom: 12px; }
.empty-text { font-size: 16px; color: #64748b; margin-bottom: 6px; }
.empty-desc { font-size: 13px; }

.knowledge-card {
  background: white; border-radius: 12px; padding: 16px; cursor: pointer;
  border: 1px solid #e2e8f0; transition: all 0.25s ease;
  display: flex; flex-direction: column; gap: 10px;
}
.knowledge-card:hover { box-shadow: 0 8px 24px rgba(0,0,0,0.08); transform: translateY(-2px); border-color: #c7d2fe; }

.card-header { display: flex; justify-content: space-between; align-items: center; }
.card-date { font-size: 12px; color: #94a3b8; }
.card-title { font-size: 15px; font-weight: 600; color: #1e293b; line-height: 1.4; }
.card-summary { font-size: 13px; color: #64748b; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.card-footer { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding-top: 6px; border-top: 1px dashed #e2e8f0; }
.card-meta { font-size: 12px; color: #94a3b8; }
.card-actions { margin-left: auto; }

.category-badge { font-size: 11px; padding: 3px 10px; border-radius: 10px; font-weight: 500; }
.cat-visit_summary { background: #dbeafe; color: #2563eb; }
.cat-followup_insight { background: #fef3c7; color: #d97706; }
.cat-sales_skill { background: #d1fae5; color: #059669; }
.cat-customer_case { background: #ede9fe; color: #7c3aed; }

.detail-content { padding: 0 10px; }
.detail-title { font-size: 18px; font-weight: 600; color: #1e293b; margin-bottom: 12px; }
.detail-meta { display: flex; gap: 14px; align-items: center; font-size: 12px; color: #64748b; flex-wrap: wrap; margin-bottom: 16px; }
.detail-summary { background: #f8fafc; padding: 12px 16px; border-radius: 8px; font-size: 14px; color: #334155; line-height: 1.6; margin-bottom: 16px; border-left: 3px solid #667eea; }
.detail-body { font-size: 14px; line-height: 1.7; color: #334155; }
.detail-section { margin-bottom: 16px; }
.section-title { font-size: 14px; font-weight: 600; color: #475569; margin-bottom: 8px; }
.detail-section ul { margin: 0; padding-left: 20px; }
.detail-section li { margin-bottom: 4px; }
.detail-text { white-space: pre-wrap; }
</style>
