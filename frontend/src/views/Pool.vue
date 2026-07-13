<template>
  <div class="pool-page">
    <div class="page-header">
      <h2>🌊 公海池</h2>
      <div class="header-actions">
        <el-button type="primary" icon="📥" @click="handleAllocate">分配线索</el-button>
        <el-button type="success" icon="✅" @click="handleClaim">认领线索</el-button>
      </div>
    </div>
    
    <el-card class="filter-card">
      <div class="filter-row">
        <el-select v-model="filters.industry" placeholder="行业" clearable>
          <el-option label="全部" value="" />
          <el-option label="信息技术" value="信息技术" />
          <el-option label="金融" value="金融" />
          <el-option label="制造业" value="制造业" />
          <el-option label="政府" value="政府" />
        </el-select>
        <el-select v-model="filters.level" placeholder="客户级别" clearable>
          <el-option label="全部" value="" />
          <el-option label="A级" value="A" />
          <el-option label="B级" value="B" />
          <el-option label="C级" value="C" />
        </el-select>
        <el-input v-model="filters.keyword" placeholder="搜索客户名称" clearable />
        <el-button type="primary" @click="fetchPoolData">搜索</el-button>
      </div>
    </el-card>
    
    <el-card>
      <el-table :data="poolData" stripe @selection-change="handleSelectionChange">
        <el-table-column type="selection" width="55" />
        <el-table-column prop="name" label="客户名称" sortable />
        <el-table-column prop="company" label="公司名称" sortable />
        <el-table-column prop="phone" label="电话" sortable />
        <el-table-column prop="level" label="级别" sortable />
        <el-table-column prop="source" label="来源" sortable />
        <el-table-column prop="created_at" label="入库时间" sortable />
        <el-table-column prop="quality_score" label="质量评分" sortable>
          <template #default="scope">
            <el-progress :percentage="scope.row.quality_score" :color="getScoreColor(scope.row.quality_score)" />
          </template>
        </el-table-column>
        <el-table-column label="操作">
          <template #default="scope">
            <el-button size="small" @click="handleClaimSingle(scope.row)">认领</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'
import { ElMessage } from 'element-plus'

const poolData = ref([])
const selectedRows = ref([])

const filters = ref({
  industry: '',
  level: '',
  keyword: ''
})

const fetchPoolData = async () => {
  const response = await api.get('/pool')
  if (response.code === 200) {
    poolData.value = response.data
  }
}

const handleSelectionChange = (val) => {
  selectedRows.value = val
}

const handleClaim = () => {
  if (selectedRows.value.length === 0) {
    ElMessage.warning('请选择要认领的线索')
    return
  }
  ElMessage.success(`成功认领 ${selectedRows.value.length} 条线索`)
}

const handleClaimSingle = (row) => {
  ElMessage.success(`成功认领线索: ${row.name}`)
}

const handleAllocate = () => {
  if (selectedRows.value.length === 0) {
    ElMessage.warning('请选择要分配的线索')
    return
  }
  ElMessage.info('分配功能开发中')
}

const getScoreColor = (score) => {
  if (score >= 80) return '#4ecdc4'
  if (score >= 60) return '#fac858'
  return '#ff6b6b'
}

onMounted(() => {
  fetchPoolData()
})
</script>

<style scoped>
.pool-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  color: #333;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.filter-card {
  margin-bottom: 0;
}

.filter-row {
  display: flex;
  gap: 16px;
  align-items: center;
}

:deep(.el-select) {
  width: 140px;
}

:deep(.el-input) {
  width: 200px;
}
</style>