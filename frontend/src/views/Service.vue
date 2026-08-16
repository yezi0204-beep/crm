<template>
  <div class="service">
    <el-tabs v-model="activeTab" class="content-tabs">
      <!-- ============ 工单管理 ============ -->
      <el-tab-pane label="服务工单" name="tickets">
        <!-- 统计卡片 -->
        <div class="stat-cards">
          <el-card class="stat-card" shadow="hover">
            <div class="stat-num">{{ stats.total }}</div>
            <div class="stat-label">工单总数</div>
          </el-card>
          <el-card class="stat-card status-new" shadow="hover">
            <div class="stat-num">{{ stats.by_status?.new || 0 }}</div>
            <div class="stat-label">待处理</div>
          </el-card>
          <el-card class="stat-card status-processing" shadow="hover">
            <div class="stat-num">{{ (stats.by_status?.processing || 0) + (stats.by_status?.pending || 0) + (stats.by_status?.reopened || 0) }}</div>
            <div class="stat-label">处理中</div>
          </el-card>
          <el-card class="stat-card status-resolved" shadow="hover">
            <div class="stat-num">{{ stats.by_status?.resolved || 0 }}</div>
            <div class="stat-label">已解决</div>
          </el-card>
          <el-card class="stat-card status-overdue" shadow="hover">
            <div class="stat-num">{{ stats.overdue || 0 }}</div>
            <div class="stat-label">超时未解决</div>
          </el-card>
        </div>

        <div class="header-row">
          <el-button type="primary" @click="openTicketModal()">
            <el-icon><Plus /></el-icon>
            新建工单
          </el-button>
          <div class="search-wrapper">
            <el-input v-model="searchKeyword" placeholder="搜索工单号、标题、描述..." class="search-input" clearable @keyup.enter="fetchTickets">
              <template #prefix><span>🔍</span></template>
            </el-input>
            <el-select v-model="filterType" placeholder="类型" clearable style="width: 130px" @change="fetchTickets">
              <el-option v-for="t in typeOptions" :key="t.value" :label="t.label" :value="t.value" />
            </el-select>
            <el-select v-model="filterStatus" placeholder="状态" clearable style="width: 130px" @change="fetchTickets">
              <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
            </el-select>
            <el-select v-model="filterPriority" placeholder="优先级" clearable style="width: 130px" @change="fetchTickets">
              <el-option v-for="p in priorityOptions" :key="p.value" :label="p.label" :value="p.value" />
            </el-select>
            <el-button @click="fetchTickets" class="search-btn">搜索</el-button>
          </div>
        </div>

        <div class="table-container">
          <div class="table-wrapper">
            <el-table :data="tickets" stripe border class="data-table">
              <el-table-column prop="ticket_no" label="工单号" min-width="150" sortable />
              <el-table-column prop="title" label="标题" min-width="180" sortable show-overflow-tooltip />
              <el-table-column label="类型" width="100">
                <template #default="{ row }">
                  <el-tag :type="typeTagType(row.type)" size="small">{{ typeLabel(row.type) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="优先级" width="90">
                <template #default="{ row }">
                  <el-tag :type="priorityTagType(row.priority)" size="small">{{ priorityLabel(row.priority) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="customer_name" label="客户" min-width="130" show-overflow-tooltip>
                <template #default="{ row }">{{ row.customer_name || row.contact_name || '-' }}</template>
              </el-table-column>
              <el-table-column prop="product_name" label="关联产品" min-width="110" show-overflow-tooltip>
                <template #default="{ row }">{{ row.product_name || '-' }}</template>
              </el-table-column>
              <el-table-column label="满意度" width="90">
                <template #default="{ row }">
                  <el-rate v-if="row.survey_score" disabled :model-value="row.survey_score" size="small" />
                  <span v-else>-</span>
                </template>
              </el-table-column>
              <el-table-column prop="owner_name" label="负责人" width="90" sortable />
              <el-table-column prop="due_date" label="期望完成" min-width="110" sortable>
                <template #default="{ row }">{{ row.due_date || '-' }}</template>
              </el-table-column>
              <el-table-column prop="updated_at" label="更新时间" min-width="140" sortable />
              <el-table-column label="操作" min-width="240" fixed="right">
                <template #default="{ row }">
                  <el-button size="small" @click="openTicketDetail(row)">详情</el-button>
                  <el-button size="small" type="primary" v-if="canEdit(row)" @click="openTicketModal(row)">编辑</el-button>
                  <el-button size="small" type="success" v-if="canChangeStatus(row)" @click="openStatusModal(row)">状态</el-button>
                  <el-button size="small" type="warning" v-if="row.status==='resolved' && !row.survey_score" @click="openSurveyModal(row)">评价</el-button>
                  <el-button size="small" type="danger" @click="deleteTicket(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </el-tab-pane>

      <!-- ============ 满意度调查 ============ -->
      <el-tab-pane label="满意度调查" name="surveys">
        <div class="survey-summary">
          <el-card class="summary-card" shadow="hover">
            <div class="survey-label">综合满意度</div>
            <div class="survey-value">{{ surveyStats.summary.satisfaction_rate || 0 }}%</div>
            <div class="survey-sub">基于 {{ surveyStats.summary.count || 0 }} 份评价</div>
          </el-card>
          <el-card class="summary-card" shadow="hover">
            <div class="survey-label">综合评分</div>
            <el-rate disabled :model-value="Math.round(surveyStats.summary.avg_overall || 0)" show-score />
            <div class="survey-sub">平均 {{ surveyStats.summary.avg_overall || 0 }} 星</div>
          </el-card>
          <el-card class="summary-card" shadow="hover">
            <div class="survey-label">响应速度</div>
            <el-rate disabled :model-value="Math.round(surveyStats.summary.avg_response || 0)" show-score />
          </el-card>
          <el-card class="summary-card" shadow="hover">
            <div class="survey-label">服务态度</div>
            <el-rate disabled :model-value="Math.round(surveyStats.summary.avg_attitude || 0)" show-score />
          </el-card>
          <el-card class="summary-card" shadow="hover">
            <div class="survey-label">解决质量</div>
            <el-rate disabled :model-value="Math.round(surveyStats.summary.avg_quality || 0)" show-score />
          </el-card>
        </div>

        <div class="table-container">
          <div class="table-wrapper">
            <el-table :data="surveyStats.surveys || []" stripe border class="data-table">
              <el-table-column prop="ticket_no" label="工单号" min-width="150" />
              <el-table-column prop="title" label="工单标题" min-width="160" show-overflow-tooltip />
              <el-table-column label="类型" width="90">
                <template #default="{ row }">{{ typeLabel(row.type) }}</template>
              </el-table-column>
              <el-table-column prop="owner_name" label="负责人" width="90" />
              <el-table-column label="综合评分" width="160">
                <template #default="{ row }">
                  <el-rate disabled :model-value="row.overall_score || 0" show-score size="small" />
                </template>
              </el-table-column>
              <el-table-column label="响应速度" width="160">
                <template #default="{ row }">
                  <el-rate disabled :model-value="row.response_speed || 0" show-score size="small" />
                </template>
              </el-table-column>
              <el-table-column label="服务态度" width="160">
                <template #default="{ row }">
                  <el-rate disabled :model-value="row.attitude_score || 0" show-score size="small" />
                </template>
              </el-table-column>
              <el-table-column label="解决质量" width="160">
                <template #default="{ row }">
                  <el-rate disabled :model-value="row.quality_score || 0" show-score size="small" />
                </template>
              </el-table-column>
              <el-table-column prop="comment" label="评价" min-width="180" show-overflow-tooltip />
              <el-table-column prop="suggestion" label="建议" min-width="180" show-overflow-tooltip />
              <el-table-column prop="submitted_at" label="提交时间" min-width="140" sortable />
            </el-table>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- ============ 新建/编辑工单 ============ -->
    <el-dialog v-model="showTicketModal" :title="ticketForm.id ? '编辑工单' : '新建工单'" width="780px" :close-on-click-modal="false" top="5vh">
      <el-form :model="ticketForm" :rules="ticketRules" ref="ticketFormRef" label-width="90px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="工单号">
              <el-input v-model="ticketForm.ticket_no" placeholder="留空自动生成" :disabled="!!ticketForm.id" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="标题" prop="title">
              <el-input v-model="ticketForm.title" placeholder="工单标题" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="工单类型">
              <el-select v-model="ticketForm.type" placeholder="选择类型" style="width: 100%">
                <el-option v-for="t in typeOptions" :key="t.value" :label="t.label" :value="t.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="优先级">
              <el-select v-model="ticketForm.priority" placeholder="选择优先级" style="width: 100%">
                <el-option v-for="p in priorityOptions" :key="p.value" :label="p.label" :value="p.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="来源">
              <el-select v-model="ticketForm.source" placeholder="选择来源" allow-create filterable style="width: 100%">
                <el-option v-for="s in sourceOptions" :key="s" :label="s" :value="s" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="联系人">
              <el-input v-model="ticketForm.contact_name" placeholder="客户联系人" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="联系方式">
              <el-input v-model="ticketForm.contact_info" placeholder="电话/邮箱/微信" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="关联客户">
              <el-select v-model="ticketForm.cust_id" placeholder="选择客户（可选）" clearable filterable style="width: 100%">
                <el-option v-for="c in customerList" :key="c.id" :label="c.company" :value="c.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="关联产品">
              <el-select v-model="ticketForm.product_id" placeholder="选择产品（可选）" clearable filterable style="width: 100%">
                <el-option v-for="p in productList" :key="p.id" :label="p.name" :value="p.id" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="期望完成">
          <el-date-picker v-model="ticketForm.due_date" type="date" value-format="YYYY-MM-DD" placeholder="期望完成日期" style="width: 50%" />
        </el-form-item>
        <el-form-item label="问题描述" prop="title">
          <el-input v-model="ticketForm.description" type="textarea" :rows="4" placeholder="详细描述客户问题、投诉或咨询内容" />
        </el-form-item>
        <el-form-item label="解决方案">
          <el-input v-model="ticketForm.resolution" type="textarea" :rows="3" placeholder="处理方案及结果" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="ticketForm.remark" type="textarea" :rows="2" placeholder="备注" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showTicketModal = false">取消</el-button>
        <el-button type="primary" @click="submitTicket">保存</el-button>
      </template>
    </el-dialog>

    <!-- ============ 工单详情 ============ -->
    <el-drawer v-model="showDetailDrawer" :title="`工单详情：${currentTicket?.ticket_no || ''}`" size="60%" direction="rtl">
      <div v-if="currentTicket" class="detail-content">
        <el-descriptions :column="2" border size="default">
          <el-descriptions-item label="标题" :span="2">{{ currentTicket.title }}</el-descriptions-item>
          <el-descriptions-item label="类型">
            <el-tag :type="typeTagType(currentTicket.type)" size="small">{{ typeLabel(currentTicket.type) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="优先级">
            <el-tag :type="priorityTagType(currentTicket.priority)" size="small">{{ priorityLabel(currentTicket.priority) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTagType(currentTicket.status)" size="small">{{ statusLabel(currentTicket.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="满意度">
            <el-rate v-if="currentTicket.survey?.overall_score" disabled :model-value="currentTicket.survey.overall_score" size="small" />
            <span v-else>未评价</span>
          </el-descriptions-item>
          <el-descriptions-item label="客户">{{ currentTicket.customer_name || currentTicket.contact_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="联系方式">{{ currentTicket.contact_info || '-' }}</el-descriptions-item>
          <el-descriptions-item label="关联产品">{{ currentTicket.product_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{ currentTicket.source || '-' }}</el-descriptions-item>
          <el-descriptions-item label="负责人">{{ currentTicket.owner_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建人">{{ currentTicket.creator_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="期望完成">{{ currentTicket.due_date || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ currentTicket.created_at }}</el-descriptions-item>
          <el-descriptions-item label="解决时间">{{ currentTicket.resolved_at || '-' }}</el-descriptions-item>
          <el-descriptions-item label="问题描述" :span="2">{{ currentTicket.description || '-' }}</el-descriptions-item>
          <el-descriptions-item label="解决方案" :span="2">{{ currentTicket.resolution || '-' }}</el-descriptions-item>
          <el-descriptions-item label="备注" :span="2">{{ currentTicket.remark || '-' }}</el-descriptions-item>
        </el-descriptions>

        <!-- 消息对话 -->
        <div class="detail-section">
          <div class="section-header">
            <h4>沟通记录</h4>
          </div>
          <div class="message-list">
            <div v-for="m in currentTicket.messages" :key="m.id"
              class="msg-item" :class="m.is_internal ? 'msg-internal' : 'msg-external'">
              <div class="msg-header">
                <span class="msg-sender">{{ m.sender_name }}（{{ m.sender_type === 'operator' ? '客服' : '客户' }}）</span>
                <el-tag v-if="m.is_internal" size="small" type="warning">内部</el-tag>
                <span class="msg-time">{{ m.created_at }}</span>
              </div>
              <div class="msg-body">{{ m.content }}</div>
            </div>
            <el-empty v-if="!currentTicket.messages?.length" description="暂无沟通记录" :image-size="80" />
          </div>
          <div class="msg-input-bar">
            <el-checkbox v-model="msgIsInternal" label="仅内部可见" />
            <el-input v-model="msgContent" type="textarea" :rows="2" placeholder="输入回复内容..." />
            <div style="margin-top: 8px; text-align: right;">
              <el-button type="primary" @click="sendMessage">发送回复</el-button>
            </div>
          </div>
        </div>

        <!-- 满意度调查 -->
        <div v-if="currentTicket.survey" class="detail-section">
          <div class="section-header"><h4>客户满意度评价</h4></div>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="综合评分">
              <el-rate disabled :model-value="currentTicket.survey.overall_score || 0" show-score />
            </el-descriptions-item>
            <el-descriptions-item label="响应速度">
              <el-rate disabled :model-value="currentTicket.survey.response_speed || 0" show-score />
            </el-descriptions-item>
            <el-descriptions-item label="服务态度">
              <el-rate disabled :model-value="currentTicket.survey.attitude_score || 0" show-score />
            </el-descriptions-item>
            <el-descriptions-item label="解决质量">
              <el-rate disabled :model-value="currentTicket.survey.quality_score || 0" show-score />
            </el-descriptions-item>
            <el-descriptions-item label="评价" :span="2">{{ currentTicket.survey.comment || '-' }}</el-descriptions-item>
            <el-descriptions-item label="建议" :span="2">{{ currentTicket.survey.suggestion || '-' }}</el-descriptions-item>
          </el-descriptions>
        </div>
      </div>
    </el-drawer>

    <!-- ============ 状态流转 ============ -->
    <el-dialog v-model="showStatusModal" title="更新工单状态" width="420px" :close-on-click-modal="false">
      <el-form label-width="80px">
        <el-form-item label="工单号">
          <span>{{ currentTicket?.ticket_no }}</span>
        </el-form-item>
        <el-form-item label="当前状态">
          <el-tag :type="statusTagType(currentTicket?.status)" size="small">{{ statusLabel(currentTicket?.status) }}</el-tag>
        </el-form-item>
        <el-form-item label="新状态">
          <el-select v-model="newTicketStatus" placeholder="选择新状态" style="width: 100%">
            <el-option v-for="s in nextStatusOptions" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="newTicketStatus === 'resolved'" label="解决方案">
          <el-input v-model="statusResolution" type="textarea" :rows="3" placeholder="请简要说明处理方案" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showStatusModal = false">取消</el-button>
        <el-button type="primary" @click="submitStatus">确认</el-button>
      </template>
    </el-dialog>

    <!-- ============ 满意度评价 ============ -->
    <el-dialog v-model="showSurveyModal" title="客户满意度评价" width="560px" :close-on-click-modal="false">
      <el-form :model="surveyForm" label-width="100px">
        <el-form-item label="综合评分">
          <el-rate v-model="surveyForm.overall_score" />
        </el-form-item>
        <el-form-item label="响应速度">
          <el-rate v-model="surveyForm.response_speed" />
        </el-form-item>
        <el-form-item label="服务态度">
          <el-rate v-model="surveyForm.attitude_score" />
        </el-form-item>
        <el-form-item label="解决质量">
          <el-rate v-model="surveyForm.quality_score" />
        </el-form-item>
        <el-form-item label="文字评价">
          <el-input v-model="surveyForm.comment" type="textarea" :rows="3" placeholder="您对我们的服务有什么评价？" />
        </el-form-item>
        <el-form-item label="改进建议">
          <el-input v-model="surveyForm.suggestion" type="textarea" :rows="3" placeholder="您希望我们如何改进服务？" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showSurveyModal = false">取消</el-button>
        <el-button type="primary" @click="submitSurvey">提交评价</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import api from '../api'

const activeTab = ref('tickets')

// ============ 枚举常量 ============
const typeOptions = [
  { label: '咨询', value: 'consult' },
  { label: '投诉', value: 'complaint' },
  { label: '建议', value: 'suggestion' },
  { label: '故障', value: 'fault' },
  { label: '其他', value: 'other' }
]
const statusOptions = [
  { label: '新工单', value: 'new' },
  { label: '处理中', value: 'processing' },
  { label: '待客户反馈', value: 'pending' },
  { label: '已解决', value: 'resolved' },
  { label: '已重开', value: 'reopened' },
  { label: '已关闭', value: 'closed' }
]
const priorityOptions = [
  { label: '低', value: 'low' },
  { label: '普通', value: 'normal' },
  { label: '高', value: 'high' },
  { label: '紧急', value: 'urgent' }
]
const sourceOptions = ['电话', '邮件', '微信', '在线客服', '现场', '其他']

const typeLabel = (v) => typeOptions.find(t => t.value === v)?.label || v || '-'
const statusLabel = (v) => statusOptions.find(s => s.value === v)?.label || v || '-'
const priorityLabel = (v) => priorityOptions.find(p => p.value === v)?.label || v || '-'
const typeTagType = (v) => ({
  consult: '', complaint: 'danger', suggestion: 'success',
  fault: 'warning', other: 'info'
}[v] || '')
const statusTagType = (s) => ({
  new: 'info', processing: 'primary', pending: 'warning',
  resolved: 'success', reopened: 'warning', closed: ''
}[s] || 'info')
const priorityTagType = (p) => ({
  low: 'info', normal: '', high: 'warning', urgent: 'danger'
}[p] || '')

// ============ 工单列表 ============
const searchKeyword = ref('')
const filterType = ref('')
const filterStatus = ref('')
const filterPriority = ref('')
const tickets = ref([])
const stats = ref({ by_status: {}, by_type: {}, by_priority: {}, total: 0, overdue: 0 })
const customerList = ref([])
const productList = ref([])

const fetchTickets = async () => {
  const params = {}
  if (searchKeyword.value) params.keyword = searchKeyword.value
  if (filterType.value) params.type = filterType.value
  if (filterStatus.value) params.status = filterStatus.value
  if (filterPriority.value) params.priority = filterPriority.value
  const res = await api.get('/tickets', params)
  if (res.code === 200) tickets.value = res.data || []
  else ElMessage.error(res.message || '获取工单失败')
}

const fetchStats = async () => {
  const res = await api.get('/tickets/statistics')
  if (res.code === 200) stats.value = res.data || stats.value
}

const fetchDicts = async () => {
  const [c, p] = await Promise.all([
    api.get('/customers', { keyword: '', page_size: 999 }),
    api.get('/products', { keyword: '', page_size: 999 })
  ])
  if (c.code === 200) customerList.value = c.data || []
  if (p.code === 200) productList.value = p.data || []
}

// ============ 工单表单 ============
const showTicketModal = ref(false)
const ticketFormRef = ref()
const ticketForm = reactive({
  id: null, ticket_no: '', title: '', type: 'consult', priority: 'normal', status: 'new',
  cust_id: null, contact_name: '', contact_info: '', source: '',
  product_id: null, description: '', resolution: '', due_date: '', remark: ''
})
const ticketRules = {
  title: [{ required: true, message: '请输入工单标题', trigger: 'blur' }]
}

const openTicketModal = (row) => {
  if (row) {
    Object.assign(ticketForm, {
      id: row.id, ticket_no: row.ticket_no, title: row.title, type: row.type,
      priority: row.priority, status: row.status, cust_id: row.cust_id,
      contact_name: row.contact_name, contact_info: row.contact_info,
      source: row.source, product_id: row.product_id, description: row.description,
      resolution: row.resolution, due_date: row.due_date, remark: row.remark
    })
  } else {
    Object.assign(ticketForm, {
      id: null, ticket_no: '', title: '', type: 'consult', priority: 'normal',
      status: 'new', cust_id: null, contact_name: '', contact_info: '',
      source: '', product_id: null, description: '', resolution: '', due_date: '', remark: ''
    })
  }
  showTicketModal.value = true
}

const submitTicket = async () => {
  if (!ticketFormRef.value) return
  await ticketFormRef.value.validate(async (valid) => {
    if (!valid) return
    const payload = { ...ticketForm }
    if (payload.id) {
      const res = await api.put(`/tickets/${payload.id}`, payload)
      if (res.code === 200) {
        ElMessage.success('工单更新成功')
        showTicketModal.value = false
        fetchTickets()
      } else {
        ElMessage.error(res.message || '更新失败')
      }
    } else {
      delete payload.id
      const res = await api.post('/tickets', payload)
      if (res.code === 200) {
        ElMessage.success('工单创建成功')
        showTicketModal.value = false
        fetchTickets()
        fetchStats()
      } else {
        ElMessage.error(res.message || '创建失败')
      }
    }
  })
}

const canEdit = (row) => row.status !== 'closed'
const canChangeStatus = (row) => row.status !== 'closed'

const deleteTicket = (row) => {
  ElMessageBox.confirm(`确认删除工单「${row.ticket_no}」？此操作不可恢复。`, '提示', {
    type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消'
  }).then(async () => {
    const res = await api.delete(`/tickets/${row.id}`)
    if (res.code === 200) {
      ElMessage.success('删除成功')
      fetchTickets()
      fetchStats()
    } else {
      ElMessage.error(res.message || '删除失败')
    }
  }).catch(() => {})
}

// ============ 工单详情 ============
const showDetailDrawer = ref(false)
const currentTicket = ref(null)
const msgContent = ref('')
const msgIsInternal = ref(false)

const openTicketDetail = async (row) => {
  const res = await api.get(`/tickets/${row.id}`)
  if (res.code === 200) {
    currentTicket.value = res.data
    msgContent.value = ''
    msgIsInternal.value = false
    showDetailDrawer.value = true
  } else {
    ElMessage.error(res.message || '获取详情失败')
  }
}

const sendMessage = async () => {
  if (!msgContent.value.trim()) {
    ElMessage.warning('请输入回复内容')
    return
  }
  const res = await api.post(`/tickets/${currentTicket.value.id}/messages`, {
    content: msgContent.value,
    is_internal: msgIsInternal.value ? 1 : 0,
    sender_type: 'operator'
  })
  if (res.code === 200) {
    ElMessage.success('回复成功')
    msgContent.value = ''
    // 刷新详情
    const detail = await api.get(`/tickets/${currentTicket.value.id}`)
    if (detail.code === 200) currentTicket.value = detail.data
    fetchTickets()
  } else {
    ElMessage.error(res.message || '回复失败')
  }
}

// ============ 状态流转 ============
const showStatusModal = ref(false)
const newTicketStatus = ref('')
const statusResolution = ref('')

const nextStatusOptions = computed(() => {
  if (!currentTicket.value) return statusOptions
  const s = currentTicket.value.status
  if (s === 'new') return statusOptions.filter(x => ['processing', 'closed'].includes(x.value))
  if (s === 'processing') return statusOptions.filter(x => ['pending', 'resolved', 'closed'].includes(x.value))
  if (s === 'pending') return statusOptions.filter(x => ['processing', 'resolved', 'closed'].includes(x.value))
  if (s === 'resolved') return statusOptions.filter(x => ['reopened', 'closed'].includes(x.value))
  if (s === 'reopened') return statusOptions.filter(x => ['processing', 'resolved', 'closed'].includes(x.value))
  return statusOptions
})

const openStatusModal = (row) => {
  currentTicket.value = row
  newTicketStatus.value = ''
  statusResolution.value = ''
  showStatusModal.value = true
}

const submitStatus = async () => {
  if (!newTicketStatus.value) {
    ElMessage.warning('请选择新状态')
    return
  }
  const payload = { status: newTicketStatus.value }
  if (newTicketStatus.value === 'resolved' && statusResolution.value) {
    payload.resolution = statusResolution.value
  }
  const res = await api.post(`/tickets/${currentTicket.value.id}/status`, payload)
  if (res.code === 200) {
    ElMessage.success('状态更新成功')
    showStatusModal.value = false
    fetchTickets()
    fetchStats()
  } else {
    ElMessage.error(res.message || '状态更新失败')
  }
}

// ============ 满意度评价 ============
const showSurveyModal = ref(false)
const surveyForm = reactive({
  overall_score: 5, response_speed: 5, attitude_score: 5, quality_score: 5,
  comment: '', suggestion: ''
})

const openSurveyModal = (row) => {
  currentTicket.value = row
  Object.assign(surveyForm, {
    overall_score: 5, response_speed: 5, attitude_score: 5, quality_score: 5,
    comment: '', suggestion: ''
  })
  showSurveyModal.value = true
}

const submitSurvey = async () => {
  if (!surveyForm.overall_score) {
    ElMessage.warning('请至少选择综合评分')
    return
  }
  const res = await api.post(`/tickets/${currentTicket.value.id}/survey`, surveyForm)
  if (res.code === 200) {
    ElMessage.success('评价提交成功')
    showSurveyModal.value = false
    fetchTickets()
    if (activeTab.value === 'surveys') fetchSurveys()
  } else {
    ElMessage.error(res.message || '提交失败')
  }
}

// ============ 满意度 Tab ============
const surveyStats = ref({ summary: {}, surveys: [] })
const fetchSurveys = async () => {
  const res = await api.get('/tickets/surveys')
  if (res.code === 200) surveyStats.value = res.data || surveyStats.value
}

// ============ Tab 切换 ============
watch(activeTab, (t) => {
  if (t === 'tickets') { fetchTickets(); fetchStats() }
  else if (t === 'surveys') fetchSurveys()
})

onMounted(async () => {
  await fetchDicts()
  fetchTickets()
  fetchStats()
})
</script>

<style scoped>
.service { padding: 0; }
.content-tabs { background: transparent; }

.stat-cards {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
.stat-card { padding: 8px 0; text-align: center; }
.stat-num { font-size: 24px; font-weight: 700; color: #303133; }
.stat-label { font-size: 13px; color: #909399; margin-top: 4px; }
.stat-card.status-new .stat-num { color: #909399; }
.stat-card.status-processing .stat-num { color: #409eff; }
.stat-card.status-resolved .stat-num { color: #67c23a; }
.stat-card.status-overdue .stat-num { color: #f56c6c; }

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}
.search-wrapper {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.search-input { width: 240px; }

.table-container {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.table-wrapper { overflow-x: auto; }

.survey-summary {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
.survey-summary .summary-card { text-align: center; padding: 12px; }
.survey-label { font-size: 13px; color: #909399; }
.survey-value { font-size: 28px; font-weight: 700; color: #67c23a; margin: 6px 0; }
.survey-sub { font-size: 12px; color: #c0c4cc; margin-top: 4px; }

.detail-content { padding: 0 8px; }
.detail-section { margin-top: 22px; }
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.section-header h4 { margin: 0; color: #303133; font-size: 15px; }

.message-list {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 6px;
  max-height: 360px;
  overflow-y: auto;
}
.msg-item {
  background: #fff;
  padding: 10px 12px;
  border-radius: 6px;
  margin-bottom: 10px;
  border: 1px solid #ebeef5;
}
.msg-item.msg-internal { background: #fdf6ec; border-color: #faecd8; }
.msg-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 12px;
  color: #909399;
}
.msg-sender { color: #606266; font-weight: 500; }
.msg-time { margin-left: auto; }
.msg-body { color: #303133; font-size: 14px; line-height: 1.6; white-space: pre-wrap; }

.msg-input-bar {
  margin-top: 14px;
  background: #fff;
  padding: 12px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}

@media (max-width: 1200px) {
  .stat-cards { grid-template-columns: repeat(3, 1fr); }
  .survey-summary { grid-template-columns: repeat(3, 1fr); }
}
</style>
