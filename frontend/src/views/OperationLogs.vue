<template>
  <div class="operation-logs-container">
    <div class="page-header">
      <h2>操作日志</h2>
      <p class="subtitle">查看系统操作记录，仅主任可访问</p>
    </div>

    <div class="search-bar">
      <el-input
        v-model="keyword"
        placeholder="搜索用户名、姓名、详情"
        clearable
        class="search-input"
        @keyup.enter="onSearch"
      >
        <template #prefix>
          <span class="search-icon">🔍</span>
        </template>
      </el-input>

      <el-select v-model="moduleFilter" placeholder="模块" clearable filterable style="width: 150px">
        <el-option v-for="m in moduleOptions" :key="m" :label="m" :value="m" />
      </el-select>

      <el-select v-model="operationFilter" placeholder="操作类型" clearable filterable style="width: 140px">
        <el-option v-for="o in operationOptions" :key="o" :label="o" :value="o" />
      </el-select>

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

      <el-button type="primary" @click="onSearch" class="search-btn">
        查询
      </el-button>

      <el-button type="success" @click="markAllRead" class="mark-read-btn">
        全部标记为已读
      </el-button>
    </div>

    <div class="table-container">
      <div class="table-wrapper">
        <el-table :data="logs" border class="data-table" v-loading="loading" max-height="62vh">
          <el-table-column type="expand" width="40">
            <template #default="{ row }">
              <div class="detail-expand">
                <div class="detail-row"><span class="detail-label">完整详情：</span>{{ row.detail || '—' }}</div>
                <div class="detail-row">
                  <span class="detail-label">操作人：</span>{{ row.user_name || row.username }}
                  <template v-if="row.user_department">（{{ row.user_department }}）</template>
                  <span class="detail-label" style="margin-left:16px;">账号：</span>{{ row.username }}
                  <span class="detail-label" style="margin-left:16px;">IP：</span>{{ row.ip_address || '—' }}
                </div>
                <div class="detail-row"><span class="detail-label">日志ID：</span>{{ row.id }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="is_read" label="状态" width="70" align="center">
            <template #default="{ row }">
              <el-tag :type="row.is_read ? 'success' : 'warning'" size="small">
                {{ row.is_read ? '已读' : '未读' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="user_name" label="操作人" width="110" align="center">
            <template #default="{ row }">
              {{ row.user_name || row.username }}
            </template>
          </el-table-column>
          <el-table-column prop="operation" label="操作" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="getOperationTagType(row.operation)" size="small">
                {{ row.operation }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="module" label="模块" width="110" align="center">
            <template #default="{ row }">
              <el-tag type="info" size="small">
                {{ row.module }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="detail" label="操作详情" min-width="320" show-overflow-tooltip />
          <el-table-column prop="ip_address" label="IP地址" width="130" align="center" />
          <el-table-column prop="created_at" label="操作时间" width="165" align="center" />
        </el-table>
      </div>
    </div>

    <div class="pager-bar">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100, 200]"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="fetchLogs"
        @size-change="onSizeChange"
      />
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
const moduleFilter = ref('')
const operationFilter = ref('')
const moduleOptions = ref([])
const operationOptions = ref([])

const page = ref(1)
const pageSize = ref(50)
const total = ref(0)

const fetchLogs = async () => {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (keyword.value) params.keyword = keyword.value
    if (moduleFilter.value) params.module = moduleFilter.value
    if (operationFilter.value) params.operation = operationFilter.value
    if (dateRange.value && dateRange.value.length === 2) {
      params.start_date = dateRange.value[0]
      params.end_date = dateRange.value[1]
    }

    const response = await api.get('/operation_logs', params)
    if (response.code === 200) {
      const data = response.data || {}
      logs.value = data.list || []
      total.value = data.total || 0
      if (data.modules) moduleOptions.value = data.modules
      if (data.operations) operationOptions.value = data.operations
    } else if (response.code === 403) {
      ElMessage.error(response.message || '权限不足')
      logs.value = []
      total.value = 0
    } else {
      ElMessage.error(response.message || '获取日志失败')
    }
  } catch (error) {
    ElMessage.error('获取日志失败，请重试')
  } finally {
    loading.value = false
  }
}

const onSearch = () => {
  page.value = 1
  fetchLogs()
}

const onSizeChange = () => {
  page.value = 1
  fetchLogs()
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
    '新建': 'success',
    '编辑': 'warning',
    '修改': 'warning',
    '更新': 'warning',
    '删除': 'danger',
    '删除验收': 'danger',
    '作废': 'danger',
    '提交': 'primary',
    '审批通过': 'success',
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
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.search-input {
  width: 240px;
}

.date-picker {
  width: 260px;
}

.pager-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.detail-expand {
  padding: 8px 16px;
  background: #f8fafc;
  font-size: 13px;
  line-height: 1.9;
  color: #334155;
  word-break: break-all;
}

.detail-label {
  color: #94a3b8;
  font-weight: 600;
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
