<template>
  <div class="keywords-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>🏷️ 关键词管理</span>
          <div>
            <el-button type="primary" @click="showAddDialog = true">新建关键词</el-button>
            <el-button @click="showBatchDialog = true">批量导入</el-button>
          </div>
        </div>
      </template>

      <el-row :gutter="16">
        <el-col :span="6">
          <el-card class="group-tree" body-style="padding:8px">
            <template #header><span>三级分类</span></template>
            <el-tree :data="groupTree" :props="{label:'name',children:'children'}" node-key="id"
                     highlight-current @node-click="onGroupClick" default-expand-all />
          </el-card>
        </el-col>

        <el-col :span="18">
          <div class="filter-bar">
            <el-input v-model="searchText" placeholder="搜索关键词/同义词/标签" clearable style="width:250px"
                      @keyup.enter="loadKeywords" @clear="loadKeywords" />
            <el-button @click="loadKeywords">搜索</el-button>
            <el-tag v-if="currentGroup">当前分组: {{ currentGroupName }}</el-tag>
          </div>

          <el-table :data="keywords" v-loading="loading" border style="margin-top:12px">
            <el-table-column prop="keyword" label="关键词" width="120" />
            <el-table-column prop="synonyms" label="同义词" show-overflow-tooltip />
            <el-table-column prop="related" label="关联词" show-overflow-tooltip />
            <el-table-column prop="exclude_words" label="排除词" show-overflow-tooltip />
            <el-table-column prop="business_tag" label="业务标签" width="100" />
            <el-table-column label="分类" width="120">
              <template #default="{row}">
                {{ row.parent_name }} / {{ row.group_name }}
              </template>
            </el-table-column>
            <el-table-column label="启用" width="60">
              <template #default="{row}">
                <el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '是' : '否' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120">
              <template #default="{row}">
                <el-button size="small" @click="editKeyword(row)">编辑</el-button>
                <el-button size="small" type="danger" @click="deleteKeyword(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-pagination v-model:current-page="page" :page-size="perPage" :total="total"
                         layout="total, prev, pager, next" @current-change="loadKeywords"
                         style="margin-top:12px;justify-content:center" />
        </el-col>
      </el-row>
    </el-card>

    <!-- 新建/编辑弹窗 -->
    <el-dialog v-model="showAddDialog" :title="editId ? '编辑关键词' : '新建关键词'" width="600px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="分组">
          <el-cascader v-model="form.group_id" :options="cascaderOptions"
                       :props="{value:'id',label:'name',children:'children',emitPath:false}"
                       placeholder="选择分类" style="width:100%" />
        </el-form-item>
        <el-form-item label="关键词" required>
          <el-input v-model="form.keyword" placeholder="主关键词" />
        </el-form-item>
        <el-form-item label="同义词">
          <el-input v-model="form.synonyms" placeholder="逗号分隔，如：遥感监测,遥感数据,遥感影像" />
        </el-form-item>
        <el-form-item label="关联词">
          <el-input v-model="form.related" placeholder="逗号分隔" />
        </el-form-item>
        <el-form-item label="排除词">
          <el-input v-model="form.exclude_words" placeholder="逗号分隔，如：百科,词典" />
        </el-form-item>
        <el-form-item label="业务标签">
          <el-input v-model="form.business_tag" placeholder="如：遥感" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="saveKeyword">保存</el-button>
      </template>
    </el-dialog>

    <!-- 批量导入弹窗 -->
    <el-dialog v-model="showBatchDialog" title="批量导入关键词" width="600px">
      <el-alert type="info" :closable="false" style="margin-bottom:12px">
        每行一个关键词，格式：关键词|同义词|关联词|排除词|业务标签
      </el-alert>
      <el-input v-model="batchText" type="textarea" :rows="10"
                placeholder="雷达|相控阵雷达,合成孔径雷达|雷达探测,雷达系统|百科,天气雷达|雷达" />
      <el-form-item label="分组" style="margin-top:12px">
        <el-cascader v-model="batchGroupId" :options="cascaderOptions"
                     :props="{value:'id',label:'name',children:'children',emitPath:false}"
                     placeholder="选择分类" style="width:100%" />
      </el-form-item>
      <template #footer>
        <el-button @click="showBatchDialog = false">取消</el-button>
        <el-button type="primary" @click="batchImport">导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const loading = ref(false)
const keywords = ref([])
const total = ref(0)
const page = ref(1)
const perPage = ref(50)
const searchText = ref('')
const currentGroup = ref(null)
const groupTree = ref([])
const showAddDialog = ref(false)
const showBatchDialog = ref(false)
const editId = ref(null)
const batchText = ref('')
const batchGroupId = ref(null)
const form = reactive({
  group_id: null, keyword: '', synonyms: '', related: '',
  exclude_words: '', business_tag: '', enabled: true
})

const currentGroupName = computed(() => {
  if (!currentGroup.value) return ''
  return currentGroup.value.name || ''
})

const cascaderOptions = computed(() => groupTree.value)

async function loadGroups() {
  try {
    const res = await api.get('/keywords/groups')
    groupTree.value = res.data || []
  } catch (e) {
    ElMessage.error('加载分组失败')
  }
}

async function loadKeywords() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: perPage.value }
    if (searchText.value) params.search = searchText.value
    if (currentGroup.value) params.group_id = currentGroup.value.id
    const res = await api.get('/keywords', params)
    keywords.value = res.data || []
    total.value = res.total || 0
  } catch (e) {
    ElMessage.error('加载关键词失败')
  } finally {
    loading.value = false
  }
}

function onGroupClick(node) {
  currentGroup.value = node
  page.value = 1
  loadKeywords()
}

function editKeyword(row) {
  editId.value = row.id
  Object.assign(form, {
    group_id: row.group_id, keyword: row.keyword, synonyms: row.synonyms || '',
    related: row.related || '', exclude_words: row.exclude_words || '',
    business_tag: row.business_tag || '', enabled: !!row.enabled
  })
  showAddDialog.value = true
}

async function saveKeyword() {
  if (!form.keyword.trim()) {
    ElMessage.warning('关键词不能为空')
    return
  }
  try {
    if (editId.value) {
      await api.put(`/keywords/${editId.value}`, form)
    } else {
      await api.post('/keywords', form)
    }
    ElMessage.success('保存成功')
    showAddDialog.value = false
    editId.value = null
    loadKeywords()
  } catch (e) {
    ElMessage.error('保存失败')
  }
}

async function deleteKeyword(id) {
  try {
    await ElMessageBox.confirm('确认删除？', '提示')
    await api.delete(`/keywords/${id}`)
    ElMessage.success('已删除')
    loadKeywords()
  } catch (e) {
    // 取消
  }
}

async function batchImport() {
  const lines = batchText.value.trim().split('\n').filter(l => l.trim())
  const items = lines.map(line => {
    const parts = line.split('|')
    return {
      group_id: batchGroupId.value,
      keyword: parts[0]?.trim() || '',
      synonyms: parts[1]?.trim() || '',
      related: parts[2]?.trim() || '',
      exclude_words: parts[3]?.trim() || '',
      business_tag: parts[4]?.trim() || ''
    }
  }).filter(item => item.keyword)
  if (!items.length) {
    ElMessage.warning('无有效数据')
    return
  }
  try {
    await api.post('/keywords/batch', { items })
    ElMessage.success(`已导入${items.length}个关键词`)
    showBatchDialog.value = false
    batchText.value = ''
    loadKeywords()
  } catch (e) {
    ElMessage.error('导入失败')
  }
}

onMounted(() => {
  loadGroups()
  loadKeywords()
})
</script>

<style scoped>
.keywords-page { padding: 16px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.filter-bar { display: flex; gap: 8px; align-items: center; }
.group-tree { max-height: 600px; overflow-y: auto; }
</style>
