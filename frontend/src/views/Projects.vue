<template>
  <div class="projects-page">
    <div class="page-header">
      <h2>📋 项目分配</h2>
      <div class="header-actions">
        <el-button type="primary" @click="handleAdd">新建项目</el-button>
        <el-button type="success" @click="handleAssign">分配资源</el-button>
      </div>
    </div>
    
    <div class="chart-row">
      <el-card class="chart-card">
        <template #header>
          <span>项目进度概览</span>
        </template>
        <div ref="progressChart" class="chart"></div>
      </el-card>
      
      <el-card class="chart-card">
        <template #header>
          <span>团队负载分布</span>
        </template>
        <div ref="loadChart" class="chart"></div>
      </el-card>
    </div>
    
    <el-card>
      <el-table :data="projectsData" stripe max-height="70vh">
        <el-table-column prop="project_name" label="项目名称" sortable />
        <el-table-column prop="customer_name" label="客户名称" sortable />
        <el-table-column prop="start_date" label="开始日期" sortable />
        <el-table-column prop="end_date" label="结束日期" sortable />
        <el-table-column prop="progress" label="进度" sortable>
          <template #default="scope">
            <el-progress :percentage="scope.row.progress" :color="getProgressColor(scope.row.progress)" />
          </template>
        </el-table-column>
        <el-table-column prop="manager" label="项目经理" sortable />
        <el-table-column prop="team_members" label="团队成员">
          <template #default="scope">
            <span v-for="(member, idx) in scope.row.team_members" :key="idx" class="member-tag">{{ member }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" sortable>
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status)">{{ scope.row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作">
          <template #default="scope">
            <el-button size="small" @click="handleView(scope.row)">查看详情</el-button>
            <el-button size="small" @click="handleEdit(scope.row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import api from '../api'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'

const projectsData = ref([])
const progressChart = ref(null)
const loadChart = ref(null)
let chart1 = null
let chart2 = null

const fetchProjectsData = async () => {
  const response = await api.get('/projects')
  if (response.code === 200) {
    projectsData.value = response.data
  }
}

const handleAdd = () => {
  ElMessage.info('新建项目功能开发中')
}

const handleAssign = () => {
  ElMessage.info('资源分配功能开发中')
}

const handleView = (row) => {
  ElMessage.info(`查看项目: ${row.project_name}`)
}

const handleEdit = (row) => {
  ElMessage.info(`编辑项目: ${row.project_name}`)
}

const getProgressColor = (progress) => {
  if (progress >= 80) return '#4ecdc4'
  if (progress >= 50) return '#fac858'
  return '#ff6b6b'
}

const getStatusType = (status) => {
  const types = {
    '进行中': 'success',
    '待启动': 'warning',
    '已完成': 'info',
    '已暂停': 'danger'
  }
  return types[status] || 'info'
}

const initCharts = () => {
  if (progressChart.value) {
    chart1 = echarts.init(progressChart.value)
    chart1.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['项目进度'] },
      xAxis: { type: 'category', data: ['Q1', 'Q2', 'Q3', 'Q4'] },
      yAxis: { type: 'value' },
      series: [{ name: '项目进度', type: 'line', data: [65, 78, 85, 92], smooth: true, itemStyle: { color: '#4ecdc4' } }]
    })
  }
  
  if (loadChart.value) {
    chart2 = echarts.init(loadChart.value)
    chart2.setOption({
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: ['张三', '李四', '王五', '赵六', '钱七'] },
      yAxis: { type: 'value' },
      series: [{ name: '负载率', type: 'bar', data: [85, 72, 90, 68, 75], itemStyle: { color: '#5470c6' } }]
    })
  }
}

const handleResize = () => {
  chart1?.resize()
  chart2?.resize()
}

onMounted(() => {
  fetchProjectsData()
  initCharts()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chart1?.dispose()
  chart2?.dispose()
})
</script>

<style scoped>
.projects-page {
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

.chart-row {
  display: flex;
  gap: 24px;
}

.chart-card {
  flex: 1;
}

.chart {
  height: 200px;
}

.member-tag {
  display: inline-block;
  background: rgba(78, 205, 196, 0.1);
  color: #4ecdc4;
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 12px;
  margin-right: 6px;
}
</style>