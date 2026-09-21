<template>
  <div class="business-tags">
    <div class="header-row">
      <el-button type="primary" @click="openForm(null, null)" class="add-btn">
        <el-icon><Plus /></el-icon>
        新增一级标签
      </el-button>
      <div class="tips">三级标签体系：同义词用于情报采集命中（扩大召回），排除词用于过滤误报，关联词为备用弱信号。能力等级非空时该标签同时作为能力模型参与商机匹配。</div>
    </div>

    <div class="table-container">
      <el-table
        :data="tree"
        row-key="id"
        border
        default-expand-all
        :tree-props="{ children: 'children' }"
        v-loading="loading"
        class="data-table"
      >
        <el-table-column label="标签" min-width="220">
          <template #default="{ row }">
            <el-tag :type="levelTagType(row.level)" size="small" class="lv-tag">{{ row.name }}</el-tag>
            <el-tag v-if="row.capability_level" :type="capTagType(row.capability_level)" size="small" effect="dark" class="cap-tag">{{ row.capability_level }}</el-tag>
            <el-tag v-if="!row.is_active" type="info" size="small">已停用</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="层级" width="80" align="center">
          <template #default="{ row }">{{ row.level }}级</template>
        </el-table-column>
        <el-table-column label="同义词" min-width="160">
          <template #default="{ row }">
            <el-tag v-for="s in row.synonyms" :key="s" size="small" type="success" effect="plain" class="w-tag">{{ s }}</el-tag>
            <span v-if="!row.synonyms.length" class="none">—</span>
          </template>
        </el-table-column>
        <el-table-column label="关联词" min-width="140">
          <template #default="{ row }">
            <el-tag v-for="s in row.related_words" :key="s" size="small" type="warning" effect="plain" class="w-tag">{{ s }}</el-tag>
            <span v-if="!row.related_words.length" class="none">—</span>
          </template>
        </el-table-column>
        <el-table-column label="排除词" min-width="140">
          <template #default="{ row }">
            <el-tag v-for="s in row.exclude_words" :key="s" size="small" type="danger" effect="plain" class="w-tag">{{ s }}</el-tag>
            <span v-if="!row.exclude_words.length" class="none">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="sort_order" label="排序" width="70" align="center" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" text :disabled="row.level >= 3" @click="openForm(null, row)">＋子标签</el-button>
            <el-button size="small" text @click="openForm(row, null)">编辑</el-button>
            <el-button size="small" type="danger" text @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="showForm" :title="form.id ? '编辑标签' : '新增标签'" width="640px" :close-on-click-modal="false">
      <el-form :model="form" label-width="90px">
        <el-form-item label="上级标签" v-if="form.parent_name">
          <el-tag type="primary">{{ form.parent_name }}</el-tag>
        </el-form-item>
        <el-form-item label="标签名称" required>
          <el-input v-model="form.name" placeholder="如：卫星遥感" maxlength="30" />
        </el-form-item>
        <el-form-item label="同义词">
          <el-select v-model="form.synonyms" multiple filterable allow-create default-first-option placeholder="输入后回车添加" style="width: 100%" />
          <div class="field-tip">内容命中标签名或任一同义词即归入该标签，如 SAR ← 合成孔径雷达</div>
        </el-form-item>
        <el-form-item label="关联词">
          <el-select v-model="form.related_words" multiple filterable allow-create default-first-option placeholder="输入后回车添加" style="width: 100%" />
          <div class="field-tip">弱相关信号，备用扩展</div>
        </el-form-item>
        <el-form-item label="排除词">
          <el-select v-model="form.exclude_words" multiple filterable allow-create default-first-option placeholder="输入后回车添加" style="width: 100%" />
          <div class="field-tip">内容含任一排除词即整条丢弃（误报过滤）</div>
        </el-form-item>

        <el-divider content-position="left">能力模型（可选）</el-divider>
        <el-form-item label="能力等级">
          <el-select v-model="form.capability_level" clearable placeholder="不设则该标签不参与能力匹配" style="width: 100%">
            <el-option label="成熟（mature）" value="mature" />
            <el-option label="成长中（growing）" value="growing" />
            <el-option label="学习中（learning）" value="learning" />
            <el-option label="普通（normal）" value="normal" />
          </el-select>
          <div class="field-tip">设置后该标签同时作为能力条目参与商机能力匹配评分</div>
        </el-form-item>
        <el-form-item label="能力描述" v-if="form.capability_level">
          <el-input v-model="form.capability_desc" type="textarea" :rows="2" placeholder="能力详细描述" />
        </el-form-item>
        <el-form-item label="产品" v-if="form.capability_level">
          <el-select v-model="form.products" multiple filterable allow-create default-first-option placeholder="输入后回车添加" style="width: 100%" />
        </el-form-item>
        <el-form-item label="方案" v-if="form.capability_level">
          <el-select v-model="form.solutions" multiple filterable allow-create default-first-option placeholder="输入后回车添加" style="width: 100%" />
        </el-form-item>
        <el-form-item label="案例" v-if="form.capability_level">
          <el-select v-model="form.cases" multiple filterable allow-create default-first-option placeholder="输入后回车添加" style="width: 100%" />
        </el-form-item>

        <el-divider />
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" :max="999" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showForm = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import api from '../api'

const tree = ref([])
const loading = ref(false)
const showForm = ref(false)
const saving = ref(false)
const form = ref({})

const levelTagType = (level) => (level === 1 ? 'danger' : level === 2 ? 'primary' : 'success')
const capTagType = (level) => ({ mature: 'success', growing: 'warning', learning: 'info', normal: '' }[level] || '')

const fetchTree = async () => {
  loading.value = true
  try {
    const res = await api.get('/business-tags')
    if (res.code === 200) {
      tree.value = res.data || []
    } else {
      ElMessage.error(res.message || '加载失败')
    }
  } finally {
    loading.value = false
  }
}

const openForm = (row, parentRow) => {
  form.value = row
    ? {
        id: row.id, name: row.name, parent_id: row.parent_id,
        parent_name: '', synonyms: [...row.synonyms], related_words: [...row.related_words],
        exclude_words: [...row.exclude_words], sort_order: row.sort_order, is_active: row.is_active,
        capability_level: row.capability_level || '', capability_desc: row.capability_desc || '',
        products: [...(row.products || [])], solutions: [...(row.solutions || [])], cases: [...(row.cases || [])]
      }
    : {
        id: null, name: '', parent_id: parentRow ? parentRow.id : null,
        parent_name: parentRow ? `${parentRow.name}` : '', synonyms: [], related_words: [],
        exclude_words: [], sort_order: 0, is_active: true,
        capability_level: '', capability_desc: '', products: [], solutions: [], cases: []
      }
  showForm.value = true
}

const save = async () => {
  if (!form.value.name || !form.value.name.trim()) {
    ElMessage.warning('请输入标签名称')
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.value.name.trim(), parent_id: form.value.parent_id,
      synonyms: form.value.synonyms, related_words: form.value.related_words,
      exclude_words: form.value.exclude_words, sort_order: form.value.sort_order,
      is_active: form.value.is_active,
      capability_level: form.value.capability_level || null,
      capability_desc: form.value.capability_desc || '',
      products: form.value.products, solutions: form.value.solutions, cases: form.value.cases
    }
    const res = form.value.id
      ? await api.put(`/business-tags/${form.value.id}`, payload)
      : await api.post('/business-tags', payload)
    if (res.code === 200) {
      ElMessage.success('保存成功')
      showForm.value = false
      fetchTree()
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } finally {
    saving.value = false
  }
}

const remove = async (row) => {
  const confirmed = await ElMessageBox.confirm(
    `确认删除标签「${row.name}」？${row.children && row.children.length ? '（其子标签将一并失去上级，请先删除子标签）' : ''}`,
    '删除确认', { type: 'warning' })
  try {
    await confirmed
  } catch {
    return
  }
  const res = await api.delete(`/business-tags/${row.id}`)
  if (res.code === 200) {
    ElMessage.success('已删除')
    fetchTree()
  } else {
    ElMessage.error(res.message || '删除失败')
  }
}

onMounted(fetchTree)
</script>

<style scoped>
.business-tags {
  padding: 0;
}
.header-row {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 14px;
}
.tips {
  color: #909399;
  font-size: 12px;
  line-height: 1.5;
}
.lv-tag {
  margin-right: 6px;
  font-weight: 600;
}
.cap-tag {
  margin-right: 6px;
}
.w-tag {
  margin: 2px 4px 2px 0;
}
.none {
  color: #c0c4cc;
}
.field-tip {
  color: #909399;
  font-size: 12px;
  line-height: 1.4;
  margin-top: 4px;
}
</style>
