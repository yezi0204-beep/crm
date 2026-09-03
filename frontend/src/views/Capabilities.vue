<template>
  <div style="padding:16px">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;flex-wrap:wrap">
      <el-input v-model="search" placeholder="搜索能力名称/关键词" clearable style="width:240px"
                @keyup.enter="loadList" @clear="loadList" />
      <el-button @click="loadList">搜索</el-button>
      <el-button type="success" :loading="seeding" @click="seed">初始化默认能力</el-button>
      <el-button type="primary" v-if="isAdmin" @click="openEdit()">+ 新增能力</el-button>
      <div style="margin-left:auto">
        <el-input v-model="matchText" placeholder="输入项目需求，测试能力匹配" style="width:320px" @keyup.enter="doMatch" />
        <el-button type="warning" :loading="matching" @click="doMatch">匹配测试</el-button>
      </div>
    </div>

    <el-table :data="list" v-loading="loading" border>
      <el-table-column prop="name" label="能力名称" width="110" />
      <el-table-column label="能力等级" width="90" align="center">
        <template #default="{row}">
          <el-tag :type="levelType(row.level)" size="small">{{ levelLabel(row.level) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="160" show-overflow-tooltip />
      <el-table-column label="产品" min-width="140">
        <template #default="{row}">
          <el-tag v-for="p in row.products" :key="p" size="small" style="margin:2px" type="success">{{ p }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="历史案例" min-width="140">
        <template #default="{row}">
          <el-tag v-for="c in row.cases" :key="c" size="small" style="margin:2px" type="warning">{{ c }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="关键词" min-width="140">
        <template #default="{row}">
          <el-tag v-for="k in row.keywords" :key="k" size="small" style="margin:2px" type="info">{{ k }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="70" align="center">
        <template #default="{row}">
          <el-switch v-model="row.enabled" :disabled="!isAdmin" @change="toggleEnabled(row)" />
        </template>
      </el-table-column>
      <el-table-column v-if="isAdmin" label="操作" width="130">
        <template #default="{row}">
          <el-button size="small" type="primary" plain @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" text :loading="deletingId===row.id" @click="deleteOne(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 能力匹配测试结果 -->
    <el-dialog v-model="matchVisible" title="能力匹配测试" width="600px">
      <div v-if="matchResult">
        <el-alert :type="matchResult.capability_score >= 60 ? 'success' : 'warning'"
                  :title="`综合能力匹配分：${matchResult.capability_score}（命中${matchResult.coverage}/${matchResult.total_capabilities}项能力）`"
                  :closable="false" style="margin-bottom:12px" />
        <div v-for="m in matchResult.matched" :key="m.name" style="margin-bottom:10px;padding:8px;background:#f0f9eb;border-radius:6px">
          <div>
            <strong>{{ m.name }}</strong>
            <el-tag size="small" style="margin-left:8px">置信度 {{ m.confidence }}</el-tag>
            <el-tag v-for="t in m.hit_terms" :key="t" size="small" type="info" style="margin-left:4px">{{ t }}</el-tag>
          </div>
          <div v-if="m.products?.length" style="font-size:13px;color:#606266;margin-top:4px">产品：{{ m.products.join('、') }}</div>
          <div v-if="m.cases?.length" style="font-size:13px;color:#909399">案例：{{ m.cases.join('、') }}</div>
        </div>
        <el-empty v-if="!matchResult.matched?.length" description="未匹配到我方能力" :image-size="60" />
      </div>
    </el-dialog>

    <!-- 编辑弹窗 -->
    <el-dialog v-model="editVisible" :title="editForm.id ? '编辑能力' : '新增能力'" width="620px">
      <el-form :model="editForm" label-width="90px">
        <el-form-item label="能力名称" required>
          <el-input v-model="editForm.name" placeholder="例如：遥感" />
        </el-form-item>
        <el-form-item label="能力等级">
          <el-select v-model="editForm.level" style="width:160px">
            <el-option label="成熟" value="mature" />
            <el-option label="成长中" value="growing" />
            <el-option label="学习中" value="learning" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="产品">
          <el-select v-model="editForm.products" multiple filterable allow-create default-first-option placeholder="输入产品后回车" style="width:100%" />
        </el-form-item>
        <el-form-item label="解决方案">
          <el-select v-model="editForm.solutions" multiple filterable allow-create default-first-option placeholder="输入方案后回车" style="width:100%" />
        </el-form-item>
        <el-form-item label="历史案例">
          <el-select v-model="editForm.cases" multiple filterable allow-create default-first-option placeholder="输入案例后回车" style="width:100%" />
        </el-form-item>
        <el-form-item label="关键词">
          <el-select v-model="editForm.keywords" multiple filterable allow-create default-first-option placeholder="输入关键词后回车" style="width:100%" />
        </el-form-item>
        <el-form-item label="同义词">
          <el-select v-model="editForm.synonyms" multiple filterable allow-create default-first-option placeholder="输入同义词后回车" style="width:100%" />
        </el-form-item>
        <el-form-item label="关联行业">
          <el-select v-model="editForm.related_industries" multiple filterable allow-create default-first-option placeholder="输入行业后回车" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
      </template>
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
const loading = ref(false)
const search = ref('')
const seeding = ref(false)
const deletingId = ref(null)
const matchText = ref('')
const matchVisible = ref(false)
const matchResult = ref(null)
const matching = ref(false)
const editVisible = ref(false)
const editForm = ref({})
const saving = ref(false)

function levelType(level) {
  return { mature: 'success', growing: 'warning', learning: 'info' }[level] || 'info'
}

function levelLabel(level) {
  return { mature: '成熟', growing: '成长中', learning: '学习中' }[level] || level
}

async function loadList() {
  loading.value = true
  try {
    const res = await api.get('/capabilities', { search: search.value })
    list.value = res.data || []
  } catch (e) { ElMessage.error('加载失败') }
  finally { loading.value = false }
}

async function seed() {
  seeding.value = true
  try {
    const res = await api.post('/capabilities/seed')
    ElMessage.success(res.message || '初始化完成')
    loadList()
  } catch (e) { ElMessage.error('初始化失败') }
  finally { seeding.value = false }
}

async function doMatch() {
  if (!matchText.value.trim()) { ElMessage.warning('请输入项目需求'); return }
  matching.value = true
  matchVisible.value = true
  matchResult.value = null
  try {
    const res = await api.post('/capabilities/match', { text: matchText.value.trim() })
    matchResult.value = res.data
  } catch (e) { ElMessage.error('匹配失败') }
  finally { matching.value = false }
}

function openEdit(row = null) {
  editForm.value = row ? {
    id: row.id, name: row.name, level: row.level, description: row.description || '',
    products: row.products || [], solutions: row.solutions || [], cases: row.cases || [],
    keywords: row.keywords || [], synonyms: row.synonyms || [],
    related_industries: row.related_industries || [],
  } : {
    name: '', level: 'mature', description: '', products: [], solutions: [],
    cases: [], keywords: [], synonyms: [], related_industries: [],
  }
  editVisible.value = true
}

async function saveEdit() {
  const f = editForm.value
  if (!f.name?.trim()) { ElMessage.warning('能力名称必填'); return }
  saving.value = true
  try {
    if (f.id) {
      const res = await api.put(`/capabilities/${f.id}`, f)
      ElMessage.success(res.message || '已保存')
    } else {
      const res = await api.post('/capabilities', f)
      ElMessage.success(res.message || '已新增')
    }
    editVisible.value = false
    loadList()
  } catch (e) { ElMessage.error('保存失败：' + (e.response?.data?.message || e.message)) }
  finally { saving.value = false }
}

async function toggleEnabled(row) {
  try {
    await api.put(`/capabilities/${row.id}`, { enabled: row.enabled ? 1 : 0 })
  } catch (e) {
    row.enabled = !row.enabled
    ElMessage.error('更新失败')
  }
}

async function deleteOne(row) {
  try {
    await ElMessageBox.confirm(`确定删除能力「${row.name}」？`, '删除', { type: 'warning' })
  } catch { return }
  deletingId.value = row.id
  try {
    const res = await api.delete(`/capabilities/${row.id}`)
    ElMessage.success(res.message || '已删除')
    loadList()
  } catch (e) { ElMessage.error('删除失败') }
  finally { deletingId.value = null }
}

onMounted(() => loadList())
</script>
