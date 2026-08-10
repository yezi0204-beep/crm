<template>
  <div class="knowledge-graph">
    <!-- 图谱控制栏 -->
    <div class="graph-controls">
      <div class="control-left">
        <el-select v-model="filterEntityType" placeholder="实体类型" clearable style="width:140px" @change="loadGraph">
          <el-option v-for="et in entityTypes" :key="et.value" :label="et.label" :value="et.value" />
        </el-select>
        <el-select v-model="filterDepth" placeholder="展开深度" style="width:120px" @change="loadGraph">
          <el-option :value="1" label="1 层" />
          <el-option :value="2" label="2 层" />
          <el-option :value="3" label="3 层" />
        </el-select>
        <el-input-number v-model="maxEntities" :min="20" :max="500" :step="20" placeholder="最大实体数" @change="loadGraph" />
        <el-button type="primary" @click="loadGraph" :loading="graphLoading">🔄 刷新图谱</el-button>
      </div>
      <div class="control-right">
        <el-button type="success" @click="showBuildDialog = true" :disabled="!canBuild">
          🧠 AI 构建图谱
        </el-button>
        <el-button @click="showEntityDialog = true">📋 实体管理</el-button>
        <el-button @click="showRelationDialog = true">🔗 关系管理</el-button>
      </div>
    </div>

    <!-- 图谱统计 -->
    <div class="graph-stats" v-if="stats">
      <div class="stat-item">
        <span class="stat-icon">🔵</span>
        <span class="stat-value">{{ stats.total_entities }}</span>
        <span class="stat-label">实体总数</span>
      </div>
      <div class="stat-item">
        <span class="stat-icon">🔗</span>
        <span class="stat-value">{{ stats.total_relations }}</span>
        <span class="stat-label">关系总数</span>
      </div>
      <div class="stat-item" v-for="item in stats.entity_type_distribution?.slice(0, 6)" :key="item.type">
        <span class="stat-icon" :style="{background: item.color}"></span>
        <span class="stat-value">{{ item.count }}</span>
        <span class="stat-label">{{ item.label }}</span>
      </div>
    </div>

    <!-- 图谱可视化 -->
    <div class="graph-container" v-loading="graphLoading">
      <div ref="chartRef" class="graph-chart"></div>
      <div v-if="!graphLoading && graphData.nodes.length === 0" class="graph-empty">
        <div class="empty-icon">🕸️</div>
        <div class="empty-text">知识图谱为空</div>
        <div class="empty-desc">点击"AI 构建图谱"按钮开始构建知识图谱</div>
      </div>
    </div>

    <!-- 选中实体详情 -->
    <el-dialog v-model="entityDetailVisible" :title="`实体详情 - ${selectedEntity?.name || ''}`" width="500px" :close-on-click-modal="false" :close-on-press-escape="false">
      <div v-if="selectedEntity" class="entity-detail">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="名称">{{ selectedEntity.name }}</el-descriptions-item>
          <el-descriptions-item label="类型">
            <el-tag :color="getEntityColor(selectedEntity.entity_type)" effect="dark">
              {{ getEntityTypeLabel(selectedEntity.entity_type) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="重要性">{{ (selectedEntity.importance || 0).toFixed(2) }}</el-descriptions-item>
          <el-descriptions-item label="描述" v-if="selectedEntity.description">{{ selectedEntity.description }}</el-descriptions-item>
          <el-descriptions-item label="关联文档" v-if="selectedEntity.doc_ids">{{ selectedEntity.doc_ids }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ selectedEntity.created_at }}</el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">关联关系</el-divider>
        <div v-if="selectedEntityRelations.length > 0" class="entity-relations">
          <div v-for="rel in selectedEntityRelations" :key="rel.id" class="relation-item">
            <el-tag size="small" :color="getRelationColor(rel.relation_type)" effect="plain">
              {{ getRelationTypeLabel(rel.relation_type) }}
            </el-tag>
            <span class="relation-direction">
              {{ rel.source_name === selectedEntity.name ? '→' : '←' }}
              {{ rel.source_name === selectedEntity.name ? rel.target_name : rel.source_name }}
            </span>
            <span v-if="rel.description" class="relation-desc">{{ rel.description }}</span>
          </div>
        </div>
        <div v-else class="no-relations">暂无关联关系</div>
      </div>
      <template #footer>
        <el-button v-if="selectedEntity" type="primary" @click="expandEntity">展开关联 ({{ selectedEntityRelations.length }})</el-button>
        <el-button @click="entityDetailVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 构建图谱对话框 -->
    <el-dialog v-model="showBuildDialog" title="AI 构建知识图谱" width="600px" :close-on-click-modal="false" :close-on-press-escape="false">
      <div class="build-dialog">
        <el-alert type="info" :closable="false" show-icon>
          选择要处理的文档，AI 将自动提取实体和关系，构建知识图谱。
        </el-alert>

        <el-form :model="buildForm" label-width="120px" style="margin-top: 16px">
          <el-form-item label="处理范围">
            <el-radio-group v-model="buildForm.scope">
              <el-radio value="all">所有文档</el-radio>
              <el-radio value="selected">选择文档</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="buildForm.scope === 'selected'" label="选择文档">
            <el-select
              v-model="buildForm.doc_ids"
              multiple
              filterable
              placeholder="选择要处理的文档"
              style="width: 100%"
            >
              <el-option v-for="doc in documentOptions" :key="doc.id" :label="doc.title" :value="doc.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="实体类型">
            <el-select v-model="buildForm.entity_types" multiple placeholder="选择要提取的实体类型（不选则全部）" style="width: 100%">
              <el-option v-for="et in entityTypes" :key="et.value" :label="et.label" :value="et.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="提取模式">
            <el-radio-group v-model="buildForm.use_llm">
              <el-radio :value="true">AI 智能提取（慢但精准）</el-radio>
              <el-radio :value="false">规则引擎提取（快）</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-form>

        <div v-if="building" class="build-progress">
          <el-divider />
          <el-progress :percentage="buildProgress" :status="buildProgress >= 100 ? 'success' : ''" />
          <div class="progress-msg">{{ buildStatusMsg }}</div>
          <div v-if="buildResult && buildResult.total_docs > 0" class="progress-stats">
            处理文档：{{ buildResult.processed_docs }} / {{ buildResult.total_docs }} ·
            已提取实体：{{ buildResult.total_entities }} · 关系：{{ buildResult.total_relations }}
          </div>
        </div>

        <div v-if="!building && buildResult" class="build-result">
          <el-divider />
          <el-result icon="success" :title="`构建完成！`">
            <template #extra>
              <div class="result-stats">
                <div>处理文档：{{ buildResult.processed_docs }} / {{ buildResult.total_docs }}</div>
                <div>提取实体：{{ buildResult.total_entities }}</div>
                <div>提取关系：{{ buildResult.total_relations }}</div>
              </div>
            </template>
          </el-result>
        </div>
      </div>
      <template #footer>
        <el-button @click="showBuildDialog = false">取消</el-button>
        <el-button type="primary" @click="handleBuild" :loading="building">
          {{ buildResult ? '重新构建' : '开始构建' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 实体管理对话框 -->
    <el-dialog v-model="showEntityDialog" title="实体管理" width="700px" :close-on-click-modal="false" :close-on-press-escape="false">
      <div class="entity-management">
        <div class="filter-bar">
          <el-select v-model="entityFilterType" placeholder="类型" clearable style="width:120px" @change="loadEntities">
            <el-option v-for="et in entityTypes" :key="et.value" :label="et.label" :value="et.value" />
          </el-select>
          <el-input v-model="entityKeyword" placeholder="搜索实体..." clearable @clear="loadEntities" style="width:200px">
            <template #append><el-button @click="loadEntities">搜索</el-button></template>
          </el-input>
        </div>

        <el-table :data="entityList" v-loading="entityLoading" stripe max-height="400px">
          <el-table-column prop="name" label="实体名称" min-width="120" />
          <el-table-column label="类型" width="100">
            <template #default="{ row }">
              <el-tag size="small" :color="getEntityColor(row.entity_type)">{{ getEntityTypeLabel(row.entity_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="importance" label="重要性" width="80">
            <template #default="{ row }">
              <el-progress :percentage="Math.round((row.importance || 0) * 100)" :stroke-width="8" />
            </template>
          </el-table-column>
          <el-table-column prop="description" label="描述" min-width="150" show-overflow-tooltip />
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button type="danger" size="small" text @click="handleDeleteEntity(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <template #footer>
        <el-button @click="showEntityDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 关系管理对话框 -->
    <el-dialog v-model="showRelationDialog" title="关系管理" width="700px" :close-on-click-modal="false" :close-on-press-escape="false">
      <div class="relation-management">
        <div class="filter-bar">
          <el-select v-model="relationFilterType" placeholder="关系类型" clearable style="width:140px" @change="loadRelations">
            <el-option v-for="rt in relationTypes" :key="rt.value" :label="rt.label" :value="rt.value" />
          </el-select>
        </div>

        <el-table :data="relationList" v-loading="relationLoading" stripe max-height="400px">
          <el-table-column prop="source_name" label="源实体" min-width="100">
            <template #default="{ row }">
              <el-tag size="small" :color="getEntityColor(row.source_type)">{{ row.source_name }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="关系" width="120">
            <template #default="{ row }">
              <el-tag size="small" :color="getRelationColor(row.relation_type)" effect="dark">{{ row.relation_type_display }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="target_name" label="目标实体" min-width="100">
            <template #default="{ row }">
              <el-tag size="small" :color="getEntityColor(row.target_type)">{{ row.target_name }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="描述" min-width="150" show-overflow-tooltip />
        </el-table>
      </div>
      <template #footer>
        <el-button @click="showRelationDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, nextTick, watch, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const token = ref(authStore.token || localStorage.getItem('token') || '')

// ========== 状态 ==========
const chartRef = ref(null)
let chartInstance = null
const graphMounted = ref(false)  // 是否已挂载用于Tab激活检测

const graphLoading = ref(false)
const graphData = reactive({ nodes: [], links: [], categories: [] })
const stats = ref(null)

const filterEntityType = ref('')
const filterDepth = ref(2)
const maxEntities = ref(100)

const entityTypes = ref([
  { value: 'person', label: '人物' },
  { value: 'organization', label: '组织/公司' },
  { value: 'product', label: '产品/系统' },
  { value: 'technology', label: '技术' },
  { value: 'customer', label: '客户' },
  { value: 'competitor', label: '竞争对手' },
  { value: 'project', label: '项目' },
  { value: 'contract', label: '合同' },
  { value: 'business', label: '商机' },
  { value: 'qualification', label: '资质' },
  { value: 'location', label: '地点' },
  { value: 'other', label: '其他' }
])

const relationTypes = ref([
  { value: 'works_at', label: '任职于' },
  { value: 'owns', label: '拥有' },
  { value: 'produces', label: '生产' },
  { value: 'uses', label: '使用' },
  { value: 'competes_with', label: '竞争' },
  { value: 'partner_of', label: '合作' },
  { value: 'manages', label: '管理' },
  { value: 'signs', label: '签署' },
  { value: 'visits', label: '拜访' },
  { value: 'follows_up', label: '跟进' },
  { value: 'has_qualification', label: '具备资质' },
  { value: 'located_at', label: '位于' },
  { value: 'involves', label: '涉及' },
  { value: 'related_to', label: '相关' },
  { value: 'other', label: '其他关系' }
])

// ========== 构建图谱 ==========
const showBuildDialog = ref(false)
const building = ref(false)
const buildForm = reactive({
  scope: 'all',
  doc_ids: [],
  entity_types: [],
  use_llm: false
})
const documentOptions = ref([])
const buildResult = ref(null)
const buildProgress = ref(0)
const buildStatusMsg = ref('')
let buildTimer = null

const canBuild = computed(() => documentOptions.value.length > 0)

// ========== 实体管理 ==========
const showEntityDialog = ref(false)
const entityLoading = ref(false)
const entityList = ref([])
const entityFilterType = ref('')
const entityKeyword = ref('')

// ========== 关系管理 ==========
const showRelationDialog = ref(false)
const relationLoading = ref(false)
const relationList = ref([])
const relationFilterType = ref('')

// ========== 实体详情 ==========
const entityDetailVisible = ref(false)
const selectedEntity = ref(null)
const selectedEntityRelations = ref([])

// ========== 颜色映射 ==========
const entityColors = {
  person: '#FF6B6B', organization: '#4ECDC4', product: '#45B7D1',
  technology: '#96CEB4', customer: '#FFEAA7', competitor: '#DDA0DD',
  project: '#98D8C8', contract: '#F7DC6F', business: '#BB8FCE',
  qualification: '#85C1E9', location: '#F8B500', other: '#BDC3C7'
}

const relationColors = {
  works_at: '#FF6B6B', owns: '#4ECDC4', produces: '#45B7D1',
  uses: '#96CEB4', competes_with: '#DDA0DD', partner_of: '#FFEAA7',
  manages: '#98D8C8', signs: '#F7DC6F', visits: '#BB8FCE',
  follows_up: '#85C1E9', has_qualification: '#F8B500', located_at: '#3498DB',
  involves: '#2ECC71', related_to: '#95A5A6', other: '#BDC3C7'
}

function getEntityColor(type) { return entityColors[type] || '#BDC3C7' }
function getRelationColor(type) { return relationColors[type] || '#BDC3C7' }
function getEntityTypeLabel(type) {
  const et = entityTypes.value.find(e => e.value === type)
  return et ? et.label : type
}
function getRelationTypeLabel(type) {
  const rt = relationTypes.value.find(r => r.value === type)
  return rt ? rt.label : type
}

// ========== 数据加载 ==========
async function loadGraph() {
  graphLoading.value = true
  try {
    const params = {
      max_entities: maxEntities.value,
      max_depth: filterDepth.value
    }
    if (filterEntityType.value) {
      params.entity_type = filterEntityType.value
    }
    const res = await api.get('/knowledge-graph/visualization', params)
    if (res.code === 200) {
      const data = res.data || {}
      graphData.nodes = data.nodes || []
      graphData.links = data.links || []
      graphData.categories = data.categories || []
      await nextTick()
      renderChart()
    }
  } catch (e) {
    ElMessage.error('加载图谱失败')
  } finally {
    graphLoading.value = false
  }
}

async function loadStats() {
  try {
    const res = await api.get('/knowledge-graph/stats')
    if (res.code === 200) {
      stats.value = res.data
    }
  } catch (e) { console.error(e) }
}

async function loadDocuments() {
  try {
    const res = await api.get('/knowledge/documents', { per_page: 200 })
    if (res.code === 200) {
      documentOptions.value = (res.data.items || []).map(doc => ({
        id: doc.id,
        title: doc.title
      }))
    }
  } catch (e) { console.error(e) }
}

async function loadEntities() {
  entityLoading.value = true
  try {
    const params = { per_page: 100 }
    if (entityFilterType.value) params.type = entityFilterType.value
    if (entityKeyword.value) params.keyword = entityKeyword.value
    const res = await api.get('/knowledge-graph/entities', params)
    if (res.code === 200) {
      entityList.value = res.data.entities
    }
  } catch (e) { ElMessage.error('加载实体失败') }
  finally { entityLoading.value = false }
}

async function loadRelations() {
  relationLoading.value = true
  try {
    const params = {}
    if (relationFilterType.value) params.type = relationFilterType.value
    const res = await api.get('/knowledge-graph/relations', params)
    if (res.code === 200) {
      relationList.value = res.data.relations
    }
  } catch (e) { ElMessage.error('加载关系失败') }
  finally { relationLoading.value = false }
}

// ========== 构建图谱（异步：立即返回 task_id，轮询进度，不阻塞后端 HTTP 线程） ==========
async function handleBuild() {
  if (buildForm.scope === 'selected' && buildForm.doc_ids.length === 0) {
    ElMessage.warning('请选择要处理的文档')
    return
  }

  // 清理上一次轮询定时器
  if (buildTimer) {
    clearTimeout(buildTimer)
    buildTimer = null
  }

  building.value = true
  buildResult.value = null
  buildProgress.value = 0
  buildStatusMsg.value = '正在启动构建...'

  try {
    const payload = {
      entity_types: buildForm.entity_types,
      use_llm: buildForm.use_llm
    }
    if (buildForm.scope === 'selected') {
      payload.doc_ids = buildForm.doc_ids
    }

    // 立即返回 task_id，后台线程构建，不阻塞 HTTP 线程
    const res = await api.post('/knowledge-graph/build', payload)
    if (res.code !== 200 || !res.data || !res.data.task_id) {
      ElMessage.error(res.message || '启动构建失败')
      building.value = false
      return
    }

    const taskId = res.data.task_id

    // 轮询进度
    const poll = async () => {
      try {
        const r = await api.get(`/knowledge-graph/build/status/${taskId}`)
        if (r.code === 200 && r.data) {
          const task = r.data
          buildProgress.value = task.progress || 0
          buildStatusMsg.value = task.message || ''
          buildResult.value = {
            processed_docs: task.processed_docs,
            total_docs: task.total_docs,
            total_entities: task.total_entities,
            total_relations: task.total_relations,
            errors: task.errors || []
          }

          if (task.status === 'running') {
            buildTimer = setTimeout(poll, 2000)
          } else if (task.status === 'done') {
            building.value = false
            buildTimer = null
            if (task.total_docs === 0) {
              ElMessage.warning('没有可处理的文档')
            } else {
              ElMessage.success(`构建完成！提取 ${task.total_entities} 个实体，${task.total_relations} 个关系`)
            }
            await loadGraph()
            await loadStats()
          } else if (task.status === 'error') {
            building.value = false
            buildTimer = null
            ElMessage.error(task.message || '构建失败')
          }
        } else {
          // 查询失败，稍后重试
          buildTimer = setTimeout(poll, 3000)
        }
      } catch (e) {
        buildTimer = setTimeout(poll, 3000)
      }
    }
    poll()
  } catch (e) {
    ElMessage.error('构建图谱失败')
    building.value = false
  }
}

// ========== 删除实体 ==========
async function handleDeleteEntity(row) {
  await ElMessageBox.confirm(`确定要删除实体「${row.name}」吗？相关关系也将一并删除。`, '确认删除', {
    type: 'warning'
  })

  try {
    const res = await api.delete(`/knowledge-graph/entities/${row.id}`)
    if (res.code === 200) {
      ElMessage.success('删除成功')
      await loadEntities()
      await loadGraph()
      await loadStats()
    } else {
      ElMessage.error(res.message || '删除失败')
    }
  } catch (e) { ElMessage.error('删除失败') }
}

// ========== 渲染图谱 ==========
function renderChart() {
  if (!chartRef.value) {
    if (chartInstance) {
      chartInstance.dispose()
      chartInstance = null
    }
    return
  }

  // 确保容器有尺寸（Tab激活后容器从display:none变为可见）
  const rect = chartRef.value.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) {
    // 容器还不可见，跳过渲染，等待refreshChart触发
    return
  }

  if (!graphData.nodes.length) {
    if (chartInstance) {
      chartInstance.dispose()
      chartInstance = null
    }
    return
  }

  // 关键修复：每次渲染前都 dispose 旧实例并重新 init
  // 避免容器尺寸曾经为0时初始化导致力导向布局参考系错乱（节点被甩到画布外）
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
  chartInstance = echarts.init(chartRef.value)

  const option = {
    tooltip: {
      formatter: (params) => {
        if (params.dataType === 'node') {
          const entity = params.data.entity
          if (!entity) return params.name
          return `
            <div style="font-weight:600;margin-bottom:4px">${entity.name}</div>
            <div style="color:#666;font-size:12px">类型: ${params.data.category}</div>
            ${entity.description ? `<div style="color:#666;font-size:12px">${entity.description}</div>` : ''}
            <div style="color:#999;font-size:11px;margin-top:4px">重要性: ${(entity.importance || 0).toFixed(2)}</div>
          `
        } else {
          const rel = params.data.relation
          if (!rel) return ''
          return `
            <div style="font-weight:600">${params.data.label?.formatter || ''}</div>
            ${rel.description ? `<div style="color:#666;font-size:12px">${rel.description}</div>` : ''}
          `
        }
      }
    },
    legend: [{
      data: graphData.categories.map(c => c.name),
      orient: 'vertical',
      right: 10,
      top: 20,
      textStyle: { fontSize: 12 }
    }],
    series: [{
      type: 'graph',
      layout: 'force',
      data: graphData.nodes,
      links: graphData.links,
      categories: graphData.categories,
      roam: true,
      draggable: true,
      label: {
        show: true,
        fontSize: 11,
        position: 'right'
      },
      force: {
        repulsion: 200,
        gravity: 0.2,
        edgeLength: [60, 150],
        layoutAnimation: true,
        friction: 0.6
      },
      // 强制节点初始位置在画布中心区域，避免被甩到画布外
      left: 'center',
      top: 'center',
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 3 }
      },
      lineStyle: {
        opacity: 0.6,
        curveness: 0.1
      },
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: 8
    }]
  }

  chartInstance.setOption(option, true)  // true = 不合并，完全替换，避免数据残留

  // 点击节点查看详情
  chartInstance.off('click')
  chartInstance.on('click', (params) => {
    if (params.dataType === 'node' && params.data.entity) {
      selectedEntity.value = params.data.entity
      // 获取关联关系
      selectedEntityRelations.value = graphData.links
        .filter(l => l.source === params.data.id || l.target === params.data.id)
        .map(l => l.relation)
        .filter(Boolean)
      entityDetailVisible.value = true
    }
  })

  // 关键修复：渲染后强制resize一次，确保布局正确
  setTimeout(() => {
    if (chartInstance) chartInstance.resize()
  }, 50)
  setTimeout(() => {
    if (chartInstance) chartInstance.resize()
  }, 300)
}

// ========== Tab激活时刷新图表（父组件切换到graph Tab时调用） ==========
async function refreshChart() {
  graphMounted.value = true
  // 如果容器没尺寸了（Tab切走再切回），先清理旧实例
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
  await nextTick()
  // 延迟等待DOM尺寸稳定
  await new Promise(r => setTimeout(r, 80))
  if (graphData.nodes.length === 0) {
    await loadGraph()
  } else {
    renderChart()
  }
  await nextTick()
  setTimeout(() => { if (chartInstance) chartInstance.resize() }, 100)
  setTimeout(() => { if (chartInstance) chartInstance.resize() }, 400)
}

// ========== 展开实体 ==========
async function expandEntity() {
  if (!selectedEntity.value) return

  graphLoading.value = true
  try {
    const res = await api.get('/knowledge-graph/visualization', {
      center_id: selectedEntity.value.id,
      max_depth: 2,
      max_entities: 50
    })
    if (res.code === 200) {
      const data = res.data || {}
      graphData.nodes = data.nodes || []
      graphData.links = data.links || []
      graphData.categories = data.categories || []
      entityDetailVisible.value = false
      await nextTick()
      renderChart()
      ElMessage.success('图谱已更新')
    }
  } catch (e) {
    ElMessage.error('展开失败')
  } finally {
    graphLoading.value = false
  }
}

// ========== 生命周期 ==========
function handleResize() {
  if (chartInstance) {
    chartInstance.resize()
  }
}

onMounted(async () => {
  await loadStats()
  await loadDocuments()
  // v-if 挂载后等待DOM尺寸稳定（避免第一次Tab激活时宽高还在计算）
  await nextTick()
  await new Promise(r => setTimeout(r, 300))
  // 双重确认容器尺寸真的稳定了，再加载图谱
  if (chartRef.value) {
    const rect = chartRef.value.getBoundingClientRect()
    if (rect.width < 100 || rect.height < 100) {
      // 还没稳定，再等一次
      await new Promise(r => setTimeout(r, 300))
    }
  }
  await loadGraph()
  // 渲染完后多次强制resize，强制ECharts重新计算布局
  setTimeout(() => { if (chartInstance) chartInstance.resize() }, 300)
  setTimeout(() => { if (chartInstance) chartInstance.resize() }, 800)
  setTimeout(() => { if (chartInstance) chartInstance.resize() }, 1500)
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
  if (buildTimer) {
    clearTimeout(buildTimer)
    buildTimer = null
  }
})

watch(filterEntityType, () => {
  loadGraph()
})

// 暴露给父组件，父组件Tab切换到graph时调用
defineExpose({
  refreshChart
})
</script>

<style scoped>
.knowledge-graph {
  padding: 0;
}

.graph-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #f8fafc;
  border-radius: 8px;
}

.control-left {
  display: flex;
  gap: 12px;
  align-items: center;
}

.control-right {
  display: flex;
  gap: 8px;
}

.graph-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: linear-gradient(135deg, #f6f9fc 0%, #eef4f8 100%);
  border-radius: 8px;
  flex-wrap: wrap;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stat-item .stat-icon {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  display: inline-block;
}

.stat-item .stat-value {
  font-size: 18px;
  font-weight: 600;
  color: #1e293b;
}

.stat-item .stat-label {
  font-size: 12px;
  color: #64748b;
}

.graph-container {
  position: relative;
  min-height: 500px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

.graph-chart {
  width: 100%;
  height: 560px;
}

.graph-empty {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  color: #94a3b8;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.empty-text {
  font-size: 16px;
  color: #64748b;
  margin-bottom: 8px;
}

.empty-desc {
  font-size: 13px;
}

.build-dialog .el-alert {
  margin-bottom: 16px;
}

.build-progress {
  margin-top: 16px;
}

.progress-msg {
  margin-top: 10px;
  text-align: center;
  color: #4a5568;
  font-size: 13px;
}

.progress-stats {
  margin-top: 8px;
  text-align: center;
  color: #718096;
  font-size: 12px;
}

.build-result {
  margin-top: 16px;
}

.result-stats {
  text-align: center;
  font-size: 14px;
  color: #4a5568;
  line-height: 2;
}

.entity-detail .el-descriptions {
  margin-bottom: 16px;
}

.entity-relations {
  max-height: 200px;
  overflow-y: auto;
}

.relation-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid #f0f4f8;
  font-size: 13px;
}

.relation-item:last-child {
  border-bottom: none;
}

.relation-direction {
  font-weight: 600;
  color: #2d3748;
}

.relation-desc {
  color: #718096;
  font-size: 12px;
}

.no-relations {
  text-align: center;
  color: #a0aec0;
  padding: 20px;
}

.entity-management .filter-bar,
.relation-management .filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
</style>
