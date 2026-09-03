<template>
  <div class="data-sources">
    <!-- 工具栏 -->
    <el-card class="toolbar-card" shadow="never">
      <div class="toolbar">
        <div class="left">
          <span class="title">📡 数据源管理</span>
          <span class="desc">插件式采集器驱动；新增数据源只需绑定一个采集器插件即可立即生效</span>
        </div>
        <div class="right">
          <el-button type="primary" @click="openForm()">
            <el-icon><Plus /></el-icon> 新增数据源
          </el-button>
        </div>
      </div>
      <div class="filters">
        <el-input v-model="keyword" size="default" placeholder="搜索名称/URL/关键词/备注" clearable style="width: 260px"
          @keyup.enter="fetch" @clear="fetch" />
        <el-select v-model="sourceType" size="default" placeholder="数据源类型" clearable style="width: 150px" @change="fetch">
          <el-option v-for="s in options.source_types" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-select v-model="industry" size="default" placeholder="行业" clearable style="width: 130px" filterable @change="fetch">
          <el-option v-for="s in options.industries" :key="s" :label="s" :value="s" />
        </el-select>
        <el-select v-model="region" size="default" placeholder="地区" clearable style="width: 130px" filterable @change="fetch">
          <el-option v-for="s in options.regions" :key="s" :label="s" :value="s" />
        </el-select>
        <el-select v-model="enabled" size="default" placeholder="启用状态" clearable style="width: 120px" @change="fetch">
          <el-option label="已启用" :value="1" />
          <el-option label="已停用" :value="0" />
        </el-select>
        <el-button size="default" @click="fetch">🔍 查询</el-button>
        <el-button size="default" @click="resetFilters">重置</el-button>
      </div>
    </el-card>

    <!-- 表格 -->
    <el-card class="table-card" shadow="never">
      <el-table :data="rows" border stripe v-loading="loading" class="data-table">
        <el-table-column label="名称" min-width="200" fixed="left">
          <template #default="{ row }">
            <el-icon-link v-if="row.url" :href="row.url" target="_blank" class="link-icon" />
            <span class="name">{{ row.name }}</span>
            <el-tag v-if="!row.enabled" type="info" size="small" style="margin-left:6px">停用</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="source_type" label="类型" width="110" align="center" />
        <el-table-column label="URL" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">
            <a v-if="row.url" :href="row.url" target="_blank" class="url">{{ row.url }}</a>
            <span v-else class="none">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="industry" label="行业" width="110" show-overflow-tooltip />
        <el-table-column prop="region" label="地区" width="90" align="center" />
        <el-table-column label="采集方式" width="120" align="center">
          <template #default="{ row }">{{ row.collection_method || '自动采集' }}</template>
        </el-table-column>
        <el-table-column label="采集频率" width="110" align="center">
          <template #default="{ row }">
            <el-tag size="small" type="primary" effect="plain">{{ row.frequency || '每日' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="采集器插件" min-width="170">
          <template #default="{ row }">
            <el-tag v-if="row.parser_type" size="small" type="success">
              {{ collectorLabel(row.parser_type) }}
            </el-tag>
            <el-tag v-else size="small" type="danger" effect="dark">未配置</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="80" align="center">
          <template #default="{ row }">
            <el-switch :model-value="row.enabled" @change="toggle(row)" />
          </template>
        </el-table-column>
        <el-table-column label="最后采集" width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="muted">{{ row.last_scraped_at || '从未' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="下次采集" width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="muted">{{ row.next_collect_at || (row.collection_method === '手动采集' ? '（手动）' : '—') }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="160" show-overflow-tooltip>
          <template #default="{ row }"><span class="muted">{{ row.notes || '—' }}</span></template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="success" text :disabled="!row.enabled || !row.parser_type" :loading="collectId===row.id" @click="collect(row)">
              手动采集
            </el-button>
            <el-button size="small" text @click="openForm(row)">编辑</el-button>
            <el-button size="small" type="danger" text @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager-wrap">
        <el-pagination layout="prev, pager, next, total, sizes"
          :current-page="page" :page-sizes="[20, 50, 100]" :page-size="pageSize" :total="total"
          @current-change="(p) => { page = p; fetch() }"
          @size-change="(s) => { pageSize = s; page = 1; fetch() }" />
      </div>
    </el-card>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="showForm" :title="editId ? '编辑数据源' : '新增数据源'" width="760px" :close-on-click-modal="false" top="4vh">
      <el-form :model="form" :rules="rules" ref="formRef" label-width="110px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="数据源名称" prop="name"><el-input v-model="form.name" maxlength="80" placeholder="如：中国政府采购网-招标公告" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="数据源类型" prop="source_type">
              <el-select v-model="form.source_type" filterable placeholder="请选择" style="width:100%">
                <el-option v-for="s in options.source_types" :key="s.value" :label="s.label" :value="s.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="URL" prop="url"><el-input v-model="form.url" placeholder="http(s)://..." /></el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="行业"><el-select v-model="form.industry" filterable allow-create placeholder="可选" style="width:100%">
              <el-option v-for="s in options.industries" :key="s" :label="s" :value="s" /></el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="地区"><el-select v-model="form.region" filterable allow-create placeholder="可选" style="width:100%">
              <el-option v-for="s in options.regions" :key="s" :label="s" :value="s" /></el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="启用状态"><el-switch v-model="form.enabled" /></el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="采集方式" prop="collection_method">
              <el-select v-model="form.collection_method" placeholder="请选择" style="width:100%">
                <el-option v-for="s in options.collection_methods" :key="s.value" :label="s.label" :value="s.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="采集频率" prop="frequency">
              <el-select v-model="form.frequency" placeholder="请选择" style="width:100%">
                <el-option v-for="s in options.frequencies" :key="s.value" :label="s.label" :value="s.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="采集器插件" prop="parser_type">
              <el-select v-model="form.parser_type" filterable placeholder="选择采集器插件" style="width:100%">
                <el-option v-for="c in collectors" :key="c.value" :label="c.label" :value="c.value" />
              </el-select>
              <div class="tip">采集器插件由 backend/collectors/*.py 注册；新插件放置后自动出现</div>
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="关键词">
              <el-input v-model="form.keywords" placeholder="用英文逗号分隔，如：雷达,卫星,仿真" />
              <div class="tip">用于采集器或 AI 搜索时的关键词定向（可选）</div>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="采集条数上限">
              <el-input-number v-model="form.max_items" :min="5" :max="500" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="备注"><el-input v-model="form.notes" type="textarea" :rows="2" maxlength="200" show-word-limit /></el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="showForm = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Link as LinkIcon } from '@element-plus/icons-vue'
import api from '../api'

const loading = ref(false)
const saving = ref(false)
const collectId = ref(null)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const keyword = ref('')
const sourceType = ref('')
const industry = ref('')
const region = ref('')
const enabled = ref(null)
const showForm = ref(false)
const editId = ref(null)
const formRef = ref(null)

const options = ref({ source_types: [], collection_methods: [], frequencies: [], industries: [], regions: [] })
const collectors = ref([])
const collectorLabel = (v) => (collectors.value.find(c => c.value === v) || {}).label || v

const defaultForm = () => ({
  name: '', source_type: '', url: '', industry: '', region: '',
  collection_method: '自动采集', frequency: '每日', parser_type: '',
  keywords: '', notes: '', enabled: true, max_items: 30,
})
const form = reactive(defaultForm())
const rules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  source_type: [{ required: true, message: '请选择类型', trigger: 'change' }],
  url: [{ required: true, message: '请输入 URL', trigger: 'blur' }],
  parser_type: [{ required: true, message: '请选择采集器插件', trigger: 'change' }],
}

const fetch = async () => {
  loading.value = true
  try {
    const res = await api.get('/data-sources', {
      keyword: keyword.value, source_type: sourceType.value,
      industry: industry.value, region: region.value,
      enabled: enabled.value !== null ? enabled.value : undefined,
      page: page.value, page_size: pageSize.value,
    })
    if (res.code === 200) {
      rows.value = res.data || []
      total.value = res.total || 0
    } else {
      ElMessage.error(res.message || '加载失败')
    }
  } finally { loading.value = false }
}

const fetchMeta = async () => {
  const [o, c] = await Promise.all([
    api.get('/data-sources/meta/options'),
    api.get('/data-sources/meta/collectors'),
  ])
  if (o.code === 200) options.value = o.data
  if (c.code === 200) collectors.value = c.data
}

const resetFilters = () => {
  keyword.value = ''; sourceType.value = ''; industry.value = ''
  region.value = ''; enabled.value = null; page.value = 1; fetch()
}

const openForm = async (row = null) => {
  Object.assign(form, defaultForm())
  if (row) {
    const res = await api.get(`/data-sources/${row.id}`)
    if (res.code !== 200) return ElMessage.error(res.message || '加载失败')
    const d = res.data
    Object.assign(form, {
      name: d.name, source_type: d.source_type, url: d.url,
      industry: d.industry, region: d.region,
      collection_method: d.collection_method || '自动采集',
      frequency: d.frequency || '每日',
      parser_type: d.parser_type, keywords: d.keywords,
      notes: d.notes, enabled: d.enabled,
      max_items: (d.config && d.config.max_items) ? d.config.max_items : 30,
    })
    editId.value = row.id
  } else {
    editId.value = null
  }
  showForm.value = true
}

const save = async () => {
  await formRef.value.validate()
  saving.value = true
  try {
    const payload = {
      name: form.name, source_type: form.source_type, url: form.url,
      industry: form.industry, region: form.region,
      collection_method: form.collection_method, frequency: form.frequency,
      parser_type: form.parser_type, keywords: form.keywords,
      notes: form.notes, enabled: form.enabled,
      config: { max_items: form.max_items },
    }
    const res = editId.value
      ? await api.put(`/data-sources/${editId.value}`, payload)
      : await api.post('/data-sources', payload)
    if (res.code === 200) {
      ElMessage.success('保存成功')
      showForm.value = false
      fetch()
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } finally { saving.value = false }
}

const toggle = async (row) => {
  const res = await api.post(`/data-sources/${row.id}/toggle`)
  if (res.code === 200) {
    row.enabled = res.data.enabled
    ElMessage.success(res.data.enabled ? '已启用' : '已停用')
  } else {
    ElMessage.error(res.message || '操作失败')
    row.enabled = !row.enabled
  }
}

const remove = async (row) => {
  await ElMessageBox.confirm(
    `确认删除数据源「${row.name}」？该源下已采集的原始情报不会被删除（来源信息置空）`,
    '删除确认', { type: 'warning' }
  ).catch(() => {})
  const r = await api.delete(`/data-sources/${row.id}`)
  if (r.code === 200) {
    ElMessage.success('已删除')
    fetch()
  } else {
    ElMessage.error(r.message || '删除失败')
  }
}

const collect = async (row) => {
  collectId.value = row.id
  try {
    const r = await api.longPost(`/data-sources/${row.id}/collect`, null, { timeout: 10 * 60 * 1000 })
    if (r.code === 200) {
      ElMessage.success(r.message)
      fetch()
    } else {
      ElMessage.error(r.message || '采集失败')
    }
  } finally { collectId.value = null }
}

onMounted(() => { fetchMeta(); fetch() })
</script>

<style scoped>
.data-sources { padding: 0; }
.toolbar-card, .table-card { margin-bottom: 14px; }
.toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 14px;
}
.title { font-size: 18px; font-weight: 700; color: #1f2d3d; margin-right: 14px; }
.desc { color: #909399; font-size: 12px; }
.filters { display: flex; gap: 10px; flex-wrap: wrap; }
.link-icon { margin-right: 6px; color: #409eff; vertical-align: middle; }
.name { font-weight: 600; color: #1f2d3d; }
.url { color: #409eff; }
.none, .muted { color: #909399; font-size: 12px; }
.tip { color: #909399; font-size: 12px; margin-top: 4px; line-height: 1.4; }
.pager-wrap { margin-top: 14px; display: flex; justify-content: flex-end; }
</style>
