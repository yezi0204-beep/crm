<template>
  <div class="workhours-page">
    <div class="page-header">
      <h2>⏱️ 工时管理</h2>
      <div class="header-actions">
        <el-button type="primary" @click="handleAdd">新增工时</el-button>
        <el-button type="success" @click="handleExport">导出报表</el-button>
      </div>
    </div>
    
    <el-card class="stats-card">
      <div class="stats-grid">
        <div class="stat-item">
          <div class="stat-value">48.5</div>
          <div class="stat-label">本周工时(小时)</div>
        </div>
        <div class="stat-item">
          <div class="stat-value">168</div>
          <div class="stat-label">本月工时(小时)</div>
        </div>
        <div class="stat-item">
          <div class="stat-value">85%</div>
          <div class="stat-label">工时利用率</div>
        </div>
        <div class="stat-item">
          <div class="stat-value">12</div>
          <div class="stat-label">待审批工时</div>
        </div>
      </div>
    </el-card>
    
    <el-card>
      <template #header>
        <div class="table-header">
          <span>工时列表</span>
          <el-date-picker v-model="dateRange" type="daterange" range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期" />
        </div>
      </template>
      <el-table :data="workhoursData" stripe>
        <el-table-column prop="date" label="日期" sortable />
        <el-table-column prop="project_name" label="项目/合同名称" sortable />
        <el-table-column prop="user_name" label="填报人" sortable />
        <el-table-column prop="hours" label="工时(小时)" sortable />
        <el-table-column prop="overtime_hours" label="加班(小时)" sortable />
        <el-table-column prop="description" label="工作描述" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" sortable>
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status)">{{ getStatusText(scope.row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="submit_time" label="提交时间" sortable />
        <el-table-column label="操作">
          <template #default="scope">
            <el-button size="small" @click="handleEdit(scope.row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(scope.row)">删除</el-button>
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

const workhoursData = ref([])
const dateRange = ref('')

const fetchWorkhoursData = async () => {
  const response = await api.get('/workhours')
  if (response.code === 200) {
    workhoursData.value = response.data
  }
}

const handleAdd = () => {
  ElMessage.info('新增工时功能开发中')
}

const handleEdit = (row) => {
  ElMessage.info(`编辑工时: ${row.task_name}`)
}

const handleDelete = (row) => {
  ElMessage.warning(`删除工时: ${row.task_name}`)
}

const handleExport = () => {
  ElMessage.success('工时报表导出成功')
}

const getStatusType = (status) => {
  const types = {
    'pending': 'warning',
    'approved': 'success',
    'rejected': 'danger',
    '待审批': 'warning',
    '已审批': 'success',
    '已拒绝': 'danger'
  }
  return types[status] || 'info'
}

const getStatusText = (status) => {
  const texts = {
    'pending': '待审批',
    'approved': '已审批',
    'rejected': '已拒绝'
  }
  return texts[status] || status
}

onMounted(() => {
  fetchWorkhoursData()
})
</script>

<style scoped>
.workhours-page {
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

.stats-card {
  margin-bottom: 0;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 24px;
}

.stat-item {
  text-align: center;
  padding: 20px;
  background: linear-gradient(135deg, #f8f9fa 0%, #f1f3f4 100%);
  border-radius: 12px;
}

.stat-value {
  font-size: 28px;
  font-weight: bold;
  color: #4ecdc4;
}

.stat-label {
  font-size: 14px;
  color: #999;
  margin-top: 8px;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}
</style>