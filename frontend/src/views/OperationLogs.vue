<template>
  <div class="operation-logs-container">
    <div class="page-header">
      <h2>操作日志</h2>
      <p class="subtitle">查看系统操作记录，仅主任可访问</p>
    </div>

    <div class="search-bar">
      <el-input
        v-model="keyword"
        placeholder="搜索用户名、操作、模块、详情"
        clearable
        class="search-input"
        @keyup.enter="fetchLogs"
      >
        <template #prefix>
          <span class="search-icon">🔍</span>
        </template>
      </el-input>

      <el-date-picker
        v-model="dateRange"
        type="daterange"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        format="YYYY-MM-DD"
        value-format="YYYY-MM-DD"
        class="date-picker"
      />

      <el-button type="primary" @click="fetchLogs" class="search-btn">
        查询
      </el-button>

      <el-button type="success" @click="markAllRead" class="mark-read-btn">
        全部标记为已读
      </el-button>
    </div>

    <div class="table-container">
      <div class="table-wrapper">
        <el-table :data="logs" border class="data-table" v-loading="loading" max-height="70vh">
          <el-table-column prop="id" label="ID" min-width="60" align="center" />
          <el-table-column prop="is_read" label="状态" min-width="70" align="center">
            <template #default="{ row }">
              <el-tag :type="row.is_read ? 'success' : 'warning'" size="small">
                {{ row.is_read ? '已读' : '未读' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="user_name" label="操作人" min-width="90" align="center">
            <template #default="{ row }">
              {{ row.user_name || row.username }}
            </template>
          </el-table-column>
          <el-table-column prop="operation" label="操作" min-width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="getOperationTagType(row.operation)" size="small">
                {{ row.operation }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="module" label="模块" min-width="80" align="center">
            <template #default="{ row }">
              <el-tag type="info" size="small">
                {{ row.module }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="detail" label="操作详情" min-width="200" show-overflow-tooltip />
          <el-table-column prop="ip_address" label="IP地址" min-width="120" align="center" />
          <el-table-column prop="created_at" label="操作时间" min-width="160" align="center" />
        </el-table>
      </div>
    </div>

    <div class="empty-state" v-if="!loading && logs.length === 0">
      <div class="empty-icon">📋</div>
      <p>暂无操作日志记录</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'
import { ElMessage } from 'element-plus'

const logs = ref([])
const loading = ref(false)
const keyword = ref('')
const dateRange = ref([])

const fetchLogs = async () => {
  loading.value = true
  try {
    const params = {}
    if (keyword.value) {
      params.keyword = keyword.value
    }
    if (dateRange.value && dateRange.value.length === 2) {
      params.start_date = dateRange.value[0]
      params.end_date = dateRange.value[1]
    }

    const response = await api.get('/operation_logs', params)
    if (response.code === 200) {
      logs.value = response.data || []
    } else if (response.code === 403) {
      ElMessage.error(response.message || '权限不足')
      logs.value = []
    } else {
      ElMessage.error(response.message || '获取日志失败')
    }
  } catch (error) {
    ElMessage.error('获取日志失败，请重试')
  } finally {
    loading.value = false
  }
}

const markAllRead = async () => {
  try {
    const response = await api.post('/operation_logs/read')
    if (response.code === 200) {
      ElMessage.success(response.message || '已全部标记为已读')
      fetchLogs()
    } else {
      ElMessage.error(response.message || '操作失败')
    }
  } catch (error) {
    ElMessage.error('标记已读失败，请重试')
  }
}

const getOperationTagType = (operation) => {
  const typeMap = {
    '登录': 'success',
    '登出': 'info',
    '创建': 'success',
    '编辑': 'warning',
    '删除': 'danger',
    '作废': 'danger',
    '更新': 'warning',
    '认领': 'success',
    '释放': 'warning'
  }
  return typeMap[operation] || 'info'
}

onMounted(() => {
  fetchLogs()
})
</script>

<style scoped>
.page-header {
  margin-bottom: 16px;
}

.page-header h2 {
  font-size: 20px;
  font-weight: 600;
  color: #334155;
  margin: 0 0 8px 0;
}

.page-header .subtitle {
  font-size: 13px;
  color: #94a3b8;
  margin: 0;
}

.search-bar {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.search-input {
  width: 260px;
}

.date-picker {
  width: 280px;
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.empty-state p {
  color: #94a3b8;
  font-size: 14px;
}
</style>