<template>
  <div style="padding:16px">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
      <el-input v-model="search" placeholder="搜索竞争对手名称" clearable style="width:300px" @keyup.enter="loadList" />
      <el-button type="primary" @click="loadList">搜索</el-button>
      <el-button type="success" :loading="analyzing" @click="analyzeAll">重新分析</el-button>
    </div>

    <el-table :data="list" v-loading="loading" border>
      <el-table-column prop="name" label="竞争对手" min-width="200" show-overflow-tooltip />
      <el-table-column prop="appearance_count" label="出现次数" width="100" sortable />
      <el-table-column label="客户列表" min-width="300">
        <template #default="{row}">
          <el-tag v-for="c in parseList(row.customer_list)" :key="c" size="small" style="margin:2px">{{ c }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="优势领域" min-width="200">
        <template #default="{row}">
          <el-tag v-for="a in parseList(row.advantage_areas)" :key="a" type="warning" size="small" style="margin:2px">{{ a }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="地区分布" min-width="150">
        <template #default="{row}">
          <el-tag v-for="r in parseList(row.regions)" :key="r" type="info" size="small" style="margin:2px">{{ r }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="first_seen" label="首次出现" width="110" />
      <el-table-column prop="last_seen" label="最近出现" width="110" />
    </el-table>

    <el-pagination v-if="total > 0" :total="total" :page-size="perPage" v-model:current-page="page"
                   layout="total, prev, pager, next" style="margin-top:12px" @current-change="loadList" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const list = ref([])
const total = ref(0)
const page = ref(1)
const perPage = ref(20)
const search = ref('')
const loading = ref(false)
const analyzing = ref(false)

function parseList(str) {
  if (!str) return []
  try { return JSON.parse(str) } catch { return [] }
}

async function loadList() {
  loading.value = true
  try {
    const res = await api.get('/cockpit/competitors', { page: page.value, per_page: perPage.value, search: search.value })
    list.value = res.data || []
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

onMounted(() => loadList())
</script>
