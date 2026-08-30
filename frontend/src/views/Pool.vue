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
          <el-option label="J(咨询服务)" value="J" />
          <el-option label="M(技术开发)" value="M" />
        </el-select>
        <el-select v-model="filters.level" placeholder="客户级别" clearable>
          <el-option label="全部" value="" />
          <el-option label="A(重点)" value="A" />
          <el-option label="B(普通)" value="B" />
          <el-option label="C(一般)" value="C" />
        </el-select>
        <el-input v-model="filters.keyword" placeholder="搜索客户名称" clearable />
        <el-button type="primary" @click="fetchPoolData">搜索</el-button>
      </div>
    </el-card>
    
    <div class="table-container">
      <div class="table-wrapper">
        <el-table :data="filteredPoolData" stripe border @selection-change="handleSelectionChange" class="data-table" max-height="70vh">
          <el-table-column type="selection" width="55" />
          <el-table-column prop="name" label="联系人" min-width="100" sortable />
          <el-table-column prop="phone" label="手机号" min-width="120" sortable />
          <el-table-column prop="company" label="公司名称" min-width="160" sortable show-overflow-tooltip />
          <el-table-column prop="level" label="客户等级" min-width="100" sortable>
            <template #default="scope">
              <el-tag :type="getLevelType(scope.row.level)" size="small">{{ getLevelLabel(scope.row.level) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="source" label="来源" min-width="100" sortable />
          <el-table-column prop="previous_owner_name" label="前负责人" min-width="100" sortable />
          <el-table-column prop="days_unfollowed" label="未跟进天数" min-width="110" sortable>
            <template #default="scope">
              <span :class="{ 'unfollowed-highlight': scope.row.days_unfollowed > 7 }">{{ scope.row.days_unfollowed }}天</span>
            </template>
          </el-table-column>
          <el-table-column prop="industry" label="业态" min-width="90" sortable />
          <el-table-column prop="quality_score" label="质量评分" min-width="100" sortable>
            <template #default="scope">
              <span :class="{ 'score-high': scope.row.quality_score >= 80, 'score-medium': scope.row.quality_score >= 60 && scope.row.quality_score < 80, 'score-low': scope.row.quality_score < 60 }">{{ scope.row.quality_score }}分</span>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="入库时间" min-width="140" sortable />
          <el-table-column label="操作" min-width="100" fixed="right">
            <template #default="scope">
              <el-button size="small" @click="handleClaimSingle(scope.row)">认领</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api'
import { ElMessage } from 'element-plus'

const poolData = ref([])
const selectedRows = ref([])

const filters = ref({
  industry: '',
  level: '',
  keyword: ''
})

const filteredPoolData = computed(() => {
  let result = poolData.value
  if (filters.value.keyword) {
    const keyword = filters.value.keyword.toLowerCase()
    result = result.filter(c => 
      (c.name && c.name.toLowerCase().includes(keyword)) ||
      (c.company && c.company.toLowerCase().includes(keyword))
    )
  }
  if (filters.value.industry) {
    result = result.filter(c => c.industry === filters.value.industry)
  }
  if (filters.value.level) {
    result = result.filter(c => c.level && c.level.startsWith(filters.value.level))
  }
  return result
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

const handleClaim = async () => {
  if (selectedRows.value.length === 0) {
    ElMessage.warning('请选择要认领的线索')
    return
  }
  
  const customerIds = selectedRows.value.map(row => row.id)
  
  try {
    const response = await api.post('/pool/claim', { customer_ids: customerIds })
    if (response.code === 200) {
      ElMessage.success(response.message)
      selectedRows.value = []
      fetchPoolData()
    } else {
      ElMessage.error(response.message)
    }
  } catch (error) {
    ElMessage.error('认领失败，请稍后重试')
  }
}

const handleClaimSingle = async (row) => {
  try {
    const response = await api.post('/pool/claim', { customer_ids: [row.id] })
    if (response.code === 200) {
      ElMessage.success(`成功认领线索: ${row.name}`)
      fetchPoolData()
    } else {
      ElMessage.error(response.message)
    }
  } catch (error) {
    ElMessage.error('认领失败，请稍后重试')
  }
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

const getLevelType = (level) => {
  if (!level) return 'info'
  if (level.startsWith('A')) return 'danger'
  if (level.startsWith('B')) return 'warning'
  if (level.startsWith('C')) return 'info'
  return 'info'
}

const getLevelLabel = (level) => {
  if (!level) return ''
  if (level.startsWith('A')) return 'A(重点)'
  if (level.startsWith('B')) return 'B(普通)'
  if (level.startsWith('C')) return 'C(一般)'
  return level
}

onMounted(() => {
  fetchPoolData()
})
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  color: #334155;
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

.unfollowed-highlight {
  color: #f56c6c;
  font-weight: bold;
}

.score-high {
  color: #4ecdc4;
  font-weight: bold;
}

.score-medium {
  color: #fac858;
  font-weight: bold;
}

.score-low {
  color: #ff6b6b;
  font-weight: bold;
}
</style>