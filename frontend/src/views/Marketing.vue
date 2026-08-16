<template>
  <div class="marketing">
    <el-tabs v-model="activeTab" class="content-tabs">
      <!-- ============ 活动管理 ============ -->
      <el-tab-pane label="营销活动" name="campaigns">
        <div class="header-row">
          <el-button type="primary" @click="openCampaignModal()">
            <el-icon><Plus /></el-icon>
            新建活动
          </el-button>
          <div class="search-wrapper">
            <el-input v-model="searchKeyword" placeholder="搜索活动名称、目标..." class="search-input" clearable @keyup.enter="fetchCampaigns">
              <template #prefix><span>🔍</span></template>
            </el-input>
            <el-select v-model="filterType" placeholder="类型" clearable style="width: 130px" @change="fetchCampaigns">
              <el-option v-for="t in typeOptions" :key="t.value" :label="t.label" :value="t.value" />
            </el-select>
            <el-select v-model="filterStatus" placeholder="状态" clearable style="width: 130px" @change="fetchCampaigns">
              <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
            </el-select>
            <el-button @click="fetchCampaigns" class="search-btn">搜索</el-button>
          </div>
        </div>

        <div class="table-container">
          <div class="table-wrapper">
            <el-table :data="campaigns" stripe border class="data-table">
              <el-table-column prop="name" label="活动名称" min-width="160" sortable show-overflow-tooltip />
              <el-table-column label="类型" width="110">
                <template #default="{ row }">{{ typeLabel(row.type) }}</template>
              </el-table-column>
              <el-table-column prop="channel" label="渠道" width="100">
                <template #default="{ row }">{{ row.channel || '-' }}</template>
              </el-table-column>
              <el-table-column label="预算(元)" width="120" sortable :sort-method="(a,b)=>(a.budget||0)-(b.budget||0)">
                <template #default="{ row }">¥{{ formatMoney(row.budget) }}</template>
              </el-table-column>
              <el-table-column label="实际花费" width="120" sortable :sort-method="(a,b)=>(a.actual_cost||0)-(b.actual_cost||0)">
                <template #default="{ row }">¥{{ formatMoney(row.actual_cost) }}</template>
              </el-table-column>
              <el-table-column label="状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="活动周期" min-width="180">
                <template #default="{ row }">
                  <span v-if="row.start_date || row.end_date">{{ row.start_date || '?' }} ~ {{ row.end_date || '?' }}</span>
                  <span v-else>-</span>
                </template>
              </el-table-column>
              <el-table-column prop="owner_name" label="负责人" width="90" sortable />
              <el-table-column label="操作" min-width="280" fixed="right">
                <template #default="{ row }">
                  <el-button size="small" @click="viewCampaignDetail(row)">详情</el-button>
                  <el-button size="small" type="primary" v-if="canEdit(row)" @click="openCampaignModal(row)">编辑</el-button>
                  <el-button size="small" type="success" v-if="canChangeStatus(row)" @click="openStatusModal(row)">状态</el-button>
                  <el-button size="small" type="warning" v-if="canEdit(row)" @click="openAudienceModal(row)">受众</el-button>
                  <el-button size="small" type="danger" v-if="canEdit(row)" @click="deleteCampaign(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </el-tab-pane>

      <!-- ============ 效果分析 ============ -->
      <el-tab-pane label="效果分析" name="analytics">
        <div class="analytics-summary">
          <el-card class="summary-card" shadow="hover">
            <div class="summary-value">{{ analytics.summary?.total_campaigns || 0 }}</div>
            <div class="summary-label">活动总数</div>
          </el-card>
          <el-card class="summary-card" shadow="hover">
            <div class="summary-value">¥{{ formatMoney(analytics.summary?.total_budget || 0) }}</div>
            <div class="summary-label">总预算</div>
          </el-card>
          <el-card class="summary-card" shadow="hover">
            <div class="summary-value">¥{{ formatMoney(analytics.summary?.total_cost || 0) }}</div>
            <div class="summary-label">总花费</div>
          </el-card>
          <el-card class="summary-card" shadow="hover">
            <div class="summary-value">¥{{ formatMoney(analytics.summary?.total_revenue || 0) }}</div>
            <div class="summary-label">总营收</div>
          </el-card>
          <el-card class="summary-card" shadow="hover">
            <div class="summary-value">{{ analytics.summary?.total_leads || 0 }}</div>
            <div class="summary-label">总线索</div>
          </el-card>
          <el-card class="summary-card" shadow="hover">
            <div class="summary-value">{{ analytics.summary?.total_conversions || 0 }}</div>
            <div class="summary-label">总转化</div>
          </el-card>
        </div>

        <div class="table-container">
          <div class="table-wrapper">
            <el-table :data="analytics.campaigns || []" stripe border class="data-table">
              <el-table-column prop="name" label="活动名称" min-width="160" show-overflow-tooltip />
              <el-table-column label="类型" width="100">
                <template #default="{ row }">{{ typeLabel(row.type) }}</template>
              </el-table-column>
              <el-table-column label="曝光" width="90" sortable>
                <template #default="{ row }">{{ row.impressions || 0 }}</template>
              </el-table-column>
              <el-table-column label="点击" width="90" sortable>
                <template #default="{ row }">{{ row.clicks || 0 }}</template>
              </el-table-column>
              <el-table-column label="点击率" width="90">
                <template #default="{ row }">{{ row.ctr }}%</template>
              </el-table-column>
              <el-table-column label="线索" width="90" sortable>
                <template #default="{ row }">{{ row.leads || 0 }}</template>
              </el-table-column>
              <el-table-column label="转化" width="90" sortable>
                <template #default="{ row }">{{ row.conversions || 0 }}</template>
              </el-table-column>
              <el-table-column label="转化率" width="90">
                <template #default="{ row }">{{ row.conversion_rate }}%</template>
              </el-table-column>
              <el-table-column label="营收(元)" width="130" sortable>
                <template #default="{ row }">¥{{ formatMoney(row.revenue) }}</template>
              </el-table-column>
              <el-table-column label="ROI" width="100" sortable>
                <template #default="{ row }">
                  <el-tag :type="row.roi >= 0 ? 'success' : 'danger'" size="small">{{ row.roi }}%</el-tag>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </el-tab-pane>

      <!-- ============ 自动化规则 ============ -->
      <el-tab-pane label="自动化规则" name="automations">
        <div class="header-row">
          <el-button type="primary" @click="openAutomationModal()">
            <el-icon><Plus /></el-icon>
            新建规则
          </el-button>
          <div class="search-wrapper">
            <el-button @click="fetchAutomations" class="search-btn">刷新</el-button>
          </div>
        </div>

        <div class="table-container">
          <div class="table-wrapper">
            <el-table :data="automations" stripe border class="data-table">
              <el-table-column prop="name" label="规则名称" min-width="160" show-overflow-tooltip />
              <el-table-column label="触发条件" width="140">
                <template #default="{ row }">{{ triggerLabel(row.trigger_type) }}</template>
              </el-table-column>
              <el-table-column label="执行动作" width="120">
                <template #default="{ row }">{{ actionLabel(row.action_type) }}</template>
              </el-table-column>
              <el-table-column label="状态" width="90">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
                    {{ row.status === 'active' ? '启用' : '停用' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="run_count" label="执行次数" width="100" sortable />
              <el-table-column prop="last_run_at" label="上次执行" min-width="140" sortable>
                <template #default="{ row }">{{ row.last_run_at || '未执行' }}</template>
              </el-table-column>
              <el-table-column prop="owner_name" label="负责人" width="90" />
              <el-table-column label="操作" min-width="200" fixed="right">
                <template #default="{ row }">
                  <el-button size="small" type="success" v-if="row.status === 'active'" @click="runAutomation(row)">执行</el-button>
                  <el-button size="small" type="primary" @click="openAutomationModal(row)">编辑</el-button>
                  <el-button size="small" type="danger" @click="deleteAutomation(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- ============ 新建/编辑活动 ============ -->
    <el-dialog v-model="showCampaignModal" :title="campaignForm.id ? '编辑营销活动' : '新建营销活动'" width="780px" :close-on-click-modal="false" top="5vh">
      <el-form :model="campaignForm" :rules="campaignRules" ref="campaignFormRef" label-width="90px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="活动名称" prop="name">
              <el-input v-model="campaignForm.name" placeholder="活动名称" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="活动类型">
              <el-select v-model="campaignForm.type" placeholder="选择类型" style="width: 100%">
                <el-option v-for="t in typeOptions" :key="t.value" :label="t.label" :value="t.value" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="营销渠道">
              <el-select v-model="campaignForm.channel" placeholder="选择渠道" allow-create filterable style="width: 100%">
                <el-option v-for="c in channelOptions" :key="c" :label="c" :value="c" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="状态">
              <el-select v-model="campaignForm.status" placeholder="状态" style="width: 100%">
                <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="预算(元)">
              <el-input-number v-model="campaignForm.budget" :min="0" :precision="2" controls-position="right" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="实际花费">
              <el-input-number v-model="campaignForm.actual_cost" :min="0" :precision="2" controls-position="right" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="开始日期">
              <el-date-picker v-model="campaignForm.start_date" type="date" value-format="YYYY-MM-DD" placeholder="开始日期" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="结束日期">
              <el-date-picker v-model="campaignForm.end_date" type="date" value-format="YYYY-MM-DD" placeholder="结束日期" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="营销目标">
          <el-input v-model="campaignForm.goal" placeholder="本次活动的营销目标" />
        </el-form-item>
        <el-form-item label="目标受众">
          <el-input v-model="campaignForm.target_audience" type="textarea" :rows="2" placeholder="目标客户群体描述" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="campaignForm.remark" type="textarea" :rows="2" placeholder="备注" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCampaignModal = false">取消</el-button>
        <el-button type="primary" @click="submitCampaign">保存</el-button>
      </template>
    </el-dialog>

    <!-- ============ 状态流转 ============ -->
    <el-dialog v-model="showStatusModal" title="更新活动状态" width="420px" :close-on-click-modal="false">
      <el-form label-width="80px">
        <el-form-item label="活动名称">
          <span>{{ currentCampaign?.name }}</span>
        </el-form-item>
        <el-form-item label="当前状态">
          <el-tag :type="statusTagType(currentCampaign?.status)" size="small">{{ statusLabel(currentCampaign?.status) }}</el-tag>
        </el-form-item>
        <el-form-item label="新状态">
          <el-select v-model="newStatus" placeholder="选择新状态" style="width: 100%">
            <el-option v-for="s in nextStatusOptions" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showStatusModal = false">取消</el-button>
        <el-button type="primary" @click="submitStatus">确认</el-button>
      </template>
    </el-dialog>

    <!-- ============ 活动详情 ============ -->
    <el-drawer v-model="showDetailDrawer" :title="`活动详情：${currentCampaign?.name || ''}`" size="60%" direction="rtl">
      <div v-if="currentCampaign" class="detail-content">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="活动名称">{{ currentCampaign.name }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ typeLabel(currentCampaign.type) }}</el-descriptions-item>
          <el-descriptions-item label="渠道">{{ currentCampaign.channel || '-' }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTagType(currentCampaign.status)" size="small">{{ statusLabel(currentCampaign.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="预算">¥{{ formatMoney(currentCampaign.budget) }}</el-descriptions-item>
          <el-descriptions-item label="实际花费">¥{{ formatMoney(currentCampaign.actual_cost) }}</el-descriptions-item>
          <el-descriptions-item label="开始日期">{{ currentCampaign.start_date || '-' }}</el-descriptions-item>
          <el-descriptions-item label="结束日期">{{ currentCampaign.end_date || '-' }}</el-descriptions-item>
          <el-descriptions-item label="负责人">{{ currentCampaign.owner_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建人">{{ currentCampaign.creator_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="营销目标" :span="2">{{ currentCampaign.goal || '-' }}</el-descriptions-item>
          <el-descriptions-item label="目标受众" :span="2">{{ currentCampaign.target_audience || '-' }}</el-descriptions-item>
          <el-descriptions-item label="备注" :span="2">{{ currentCampaign.remark || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div class="detail-section">
          <div class="section-header">
            <h4>效果指标</h4>
            <el-button size="small" type="primary" @click="showMetricModal = true">录入指标</el-button>
          </div>
          <el-table :data="currentCampaign.metrics || []" stripe border size="small">
            <el-table-column label="指标" width="120">
              <template #default="{ row }">{{ metricLabel(row.metric_type) }}</template>
            </el-table-column>
            <el-table-column prop="metric_value" label="数值" width="120" />
            <el-table-column prop="recorded_at" label="记录时间" min-width="140" />
            <el-table-column prop="recorder_name" label="记录人" width="100" />
          </el-table>
        </div>

        <div class="detail-section">
          <div class="section-header">
            <h4>受众触达统计</h4>
          </div>
          <div class="audience-stats">
            <el-tag v-for="stat in (currentCampaign.audience_stats || [])" :key="stat.reach_status"
              :type="reachTagType(stat.reach_status)" size="large" class="stat-tag">
              {{ reachLabel(stat.reach_status) }}: {{ stat.cnt }}
            </el-tag>
          </div>
        </div>
      </div>
    </el-drawer>

    <!-- ============ 录入指标 ============ -->
    <el-dialog v-model="showMetricModal" title="录入效果指标" width="460px" :close-on-click-modal="false" append-to-body>
      <el-form :model="metricForm" label-width="80px">
        <el-form-item label="指标类型">
          <el-select v-model="metricForm.metric_type" placeholder="选择指标" style="width: 100%">
            <el-option v-for="m in metricOptions" :key="m.value" :label="m.label" :value="m.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="数值">
          <el-input-number v-model="metricForm.metric_value" :min="0" :precision="2" controls-position="right" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="metricForm.remark" placeholder="备注（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showMetricModal = false">取消</el-button>
        <el-button type="primary" @click="submitMetric">录入</el-button>
      </template>
    </el-dialog>

    <!-- ============ 受众管理 ============ -->
    <el-drawer v-model="showAudienceDrawer" :title="`受众管理：${currentCampaign?.name || ''}`" size="55%" direction="rtl">
      <div class="detail-content">
        <div class="section-header" style="margin-bottom: 12px;">
          <h4>触达受众</h4>
          <el-button size="small" type="primary" @click="openAudienceAddModal">添加受众</el-button>
        </div>
        <el-table :data="audiences" stripe border size="small">
          <el-table-column prop="contact_name" label="联系人" min-width="100">
            <template #default="{ row }">{{ row.contact_name || row.customer_name || '-' }}</template>
          </el-table-column>
          <el-table-column prop="contact_info" label="联系方式" min-width="120">
            <template #default="{ row }">{{ row.contact_info || '-' }}</template>
          </el-table-column>
          <el-table-column label="触达状态" width="110">
            <template #default="{ row }">
              <el-select v-model="row.reach_status" size="small" style="width: 100%" @change="updateAudienceStatus(row)">
                <el-option v-for="r in reachOptions" :key="r.value" :label="r.label" :value="r.value" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column prop="converted_amount" label="转化金额" width="110">
            <template #default="{ row }">¥{{ formatMoney(row.converted_amount) }}</template>
          </el-table-column>
          <el-table-column prop="reached_at" label="触达时间" min-width="140" />
          <el-table-column prop="feedback" label="反馈" min-width="120" show-overflow-tooltip />
          <el-table-column label="操作" width="80" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="danger" link @click="deleteAudience(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-drawer>

    <!-- ============ 添加受众 ============ -->
    <el-dialog v-model="showAudienceAddModal" title="添加触达受众" width="520px" :close-on-click-modal="false" append-to-body>
      <el-form :model="audienceForm" label-width="90px">
        <el-form-item label="联系人">
          <el-input v-model="audienceForm.contact_name" placeholder="联系人姓名" />
        </el-form-item>
        <el-form-item label="联系方式">
          <el-input v-model="audienceForm.contact_info" placeholder="电话/邮箱/微信" />
        </el-form-item>
        <el-form-item label="触达状态">
          <el-select v-model="audienceForm.reach_status" placeholder="选择状态" style="width: 100%">
            <el-option v-for="r in reachOptions" :key="r.value" :label="r.label" :value="r.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="转化金额">
          <el-input-number v-model="audienceForm.converted_amount" :min="0" :precision="2" controls-position="right" style="width: 100%" />
        </el-form-item>
        <el-form-item label="反馈">
          <el-input v-model="audienceForm.feedback" type="textarea" :rows="2" placeholder="受众反馈" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAudienceAddModal = false">取消</el-button>
        <el-button type="primary" @click="submitAudience">添加</el-button>
      </template>
    </el-dialog>

    <!-- ============ 新建/编辑自动化规则 ============ -->
    <el-dialog v-model="showAutomationModal" :title="automationForm.id ? '编辑自动化规则' : '新建自动化规则'" width="680px" :close-on-click-modal="false" top="5vh">
      <el-form :model="automationForm" :rules="automationRules" ref="automationFormRef" label-width="90px">
        <el-form-item label="规则名称" prop="name">
          <el-input v-model="automationForm.name" placeholder="规则名称" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="触发条件">
              <el-select v-model="automationForm.trigger_type" placeholder="选择触发条件" style="width: 100%">
                <el-option v-for="t in triggerOptions" :key="t.value" :label="t.label" :value="t.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="执行动作">
              <el-select v-model="automationForm.action_type" placeholder="选择执行动作" style="width: 100%">
                <el-option v-for="a in actionOptions" :key="a.value" :label="a.label" :value="a.value" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="触发配置">
          <el-input v-model="automationForm.trigger_config_str" type="textarea" :rows="3" placeholder='JSON格式，如：{"tag":"VIP客户"}' />
        </el-form-item>
        <el-form-item label="动作配置">
          <el-input v-model="automationForm.action_config_str" type="textarea" :rows="3" placeholder='JSON格式，如：{"template":"欢迎邮件模板"}' />
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="automationForm.status">
            <el-radio value="active">启用</el-radio>
            <el-radio value="inactive">停用</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="automationForm.remark" type="textarea" :rows="2" placeholder="备注" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAutomationModal = false">取消</el-button>
        <el-button type="primary" @click="submitAutomation">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import api from '../api'

// ============ Tab 切换 ============
const activeTab = ref('campaigns')

// ============ 活动管理 ============
const searchKeyword = ref('')
const filterType = ref('')
const filterStatus = ref('')
const campaigns = ref([])

const typeOptions = [
  { label: '市场推广', value: 'promotion' },
  { label: '广告活动', value: 'advertising' },
  { label: '线上营销', value: 'online' },
  { label: '线下活动', value: 'offline' },
  { label: '邮件营销', value: 'email' },
  { label: '社交媒体', value: 'social' }
]
const channelOptions = ['微信', '邮件', '短信', '电话', '线下', '搜索引擎', '抖音', '其他']
const statusOptions = [
  { label: '草稿', value: 'draft' },
  { label: '已计划', value: 'planned' },
  { label: '进行中', value: 'running' },
  { label: '已暂停', value: 'paused' },
  { label: '已完成', value: 'completed' },
  { label: '已取消', value: 'cancelled' }
]
const metricOptions = [
  { label: '曝光量', value: 'impressions' },
  { label: '点击量', value: 'clicks' },
  { label: '线索数', value: 'leads' },
  { label: '转化数', value: 'conversions' },
  { label: '营收(元)', value: 'revenue' },
  { label: '花费(元)', value: 'cost' }
]
const reachOptions = [
  { label: '待触达', value: 'pending' },
  { label: '已触达', value: 'reached' },
  { label: '有兴趣', value: 'interested' },
  { label: '已转化', value: 'converted' },
  { label: '已流失', value: 'lost' }
]
const triggerOptions = [
  { label: '新线索进入', value: 'new_lead' },
  { label: '客户打标签', value: 'customer_tag' },
  { label: '阶段变更', value: 'stage_change' },
  { label: '定时触发', value: 'schedule' },
  { label: '活动开始', value: 'campaign_start' },
  { label: '活动结束', value: 'campaign_end' }
]
const actionOptions = [
  { label: '发送邮件', value: 'email' },
  { label: '发送短信', value: 'sms' },
  { label: '微信推送', value: 'wechat' },
  { label: '创建任务', value: 'create_task' },
  { label: '创建线索', value: 'create_lead' },
  { label: '分配负责人', value: 'assign_owner' },
  { label: '添加标签', value: 'add_tag' }
]

const typeLabel = (v) => typeOptions.find(t => t.value === v)?.label || v || '-'
const statusLabel = (v) => statusOptions.find(s => s.value === v)?.label || v || '-'
const metricLabel = (v) => metricOptions.find(m => m.value === v)?.label || v || '-'
const reachLabel = (v) => reachOptions.find(r => r.value === v)?.label || v || '-'
const triggerLabel = (v) => triggerOptions.find(t => t.value === v)?.label || v || '-'
const actionLabel = (v) => actionOptions.find(a => a.value === v)?.label || v || '-'

const statusTagType = (s) => ({
  draft: 'info', planned: 'warning', running: 'success',
  paused: 'warning', completed: '', cancelled: 'danger'
}[s] || 'info')

const reachTagType = (s) => ({
  pending: 'info', reached: 'warning', interested: '',
  converted: 'success', lost: 'danger'
}[s] || 'info')

const formatMoney = (v) => Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const fetchCampaigns = async () => {
  const params = {}
  if (searchKeyword.value) params.keyword = searchKeyword.value
  if (filterType.value) params.type = filterType.value
  if (filterStatus.value) params.status = filterStatus.value
  const res = await api.get('/campaigns', params)
  if (res.code === 200) {
    campaigns.value = res.data || []
  } else {
    ElMessage.error(res.message || '获取活动列表失败')
  }
}

// ============ 活动表单 ============
const showCampaignModal = ref(false)
const campaignFormRef = ref()
const campaignForm = reactive({
  id: null, name: '', type: '', channel: '', budget: 0, actual_cost: 0,
  start_date: '', end_date: '', status: 'draft',
  target_audience: '', goal: '', owner_id: '', remark: ''
})
const campaignRules = {
  name: [{ required: true, message: '请输入活动名称', trigger: 'blur' }]
}

const openCampaignModal = (row) => {
  if (row) {
    Object.assign(campaignForm, {
      id: row.id, name: row.name, type: row.type, channel: row.channel,
      budget: row.budget, actual_cost: row.actual_cost,
      start_date: row.start_date, end_date: row.end_date, status: row.status,
      target_audience: row.target_audience, goal: row.goal,
      owner_id: row.owner_id, remark: row.remark
    })
  } else {
    Object.assign(campaignForm, {
      id: null, name: '', type: '', channel: '', budget: 0, actual_cost: 0,
      start_date: '', end_date: '', status: 'draft',
      target_audience: '', goal: '', owner_id: '', remark: ''
    })
  }
  showCampaignModal.value = true
}

const submitCampaign = async () => {
  if (!campaignFormRef.value) return
  await campaignFormRef.value.validate(async (valid) => {
    if (!valid) return
    const payload = { ...campaignForm }
    if (payload.id) {
      const res = await api.put(`/campaigns/${payload.id}`, payload)
      if (res.code === 200) {
        ElMessage.success('活动更新成功')
        showCampaignModal.value = false
        fetchCampaigns()
      } else {
        ElMessage.error(res.message || '更新失败')
      }
    } else {
      delete payload.id
      const res = await api.post('/campaigns', payload)
      if (res.code === 200) {
        ElMessage.success('活动创建成功')
        showCampaignModal.value = false
        fetchCampaigns()
      } else {
        ElMessage.error(res.message || '创建失败')
      }
    }
  })
}

const canEdit = (row) => !['completed', 'cancelled'].includes(row.status)
const canChangeStatus = (row) => !['completed', 'cancelled'].includes(row.status)

const deleteCampaign = (row) => {
  ElMessageBox.confirm(`确认删除活动「${row.name}」？删除后不可恢复。`, '提示', {
    type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消'
  }).then(async () => {
    const res = await api.delete(`/campaigns/${row.id}`)
    if (res.code === 200) {
      ElMessage.success('删除成功')
      fetchCampaigns()
    } else {
      ElMessage.error(res.message || '删除失败')
    }
  }).catch(() => {})
}

// ============ 状态流转 ============
const showStatusModal = ref(false)
const currentCampaign = ref(null)
const newStatus = ref('')

const nextStatusOptions = computed(() => {
  if (!currentCampaign.value) return statusOptions
  const s = currentCampaign.value.status
  if (s === 'draft') return statusOptions.filter(x => ['planned', 'running', 'cancelled'].includes(x.value))
  if (s === 'planned') return statusOptions.filter(x => ['running', 'cancelled'].includes(x.value))
  if (s === 'running') return statusOptions.filter(x => ['paused', 'completed', 'cancelled'].includes(x.value))
  if (s === 'paused') return statusOptions.filter(x => ['running', 'completed', 'cancelled'].includes(x.value))
  return statusOptions
})

const openStatusModal = (row) => {
  currentCampaign.value = row
  newStatus.value = ''
  showStatusModal.value = true
}

const submitStatus = async () => {
  if (!newStatus.value) {
    ElMessage.warning('请选择新状态')
    return
  }
  const res = await api.post(`/campaigns/${currentCampaign.value.id}/status`, { status: newStatus.value })
  if (res.code === 200) {
    ElMessage.success('状态更新成功')
    showStatusModal.value = false
    fetchCampaigns()
  } else {
    ElMessage.error(res.message || '状态更新失败')
  }
}

// ============ 活动详情 ============
const showDetailDrawer = ref(false)

const viewCampaignDetail = async (row) => {
  const res = await api.get(`/campaigns/${row.id}`)
  if (res.code === 200) {
    currentCampaign.value = res.data
    showDetailDrawer.value = true
  } else {
    ElMessage.error(res.message || '获取详情失败')
  }
}

// ============ 指标录入 ============
const showMetricModal = ref(false)
const metricForm = reactive({ metric_type: 'impressions', metric_value: 0, remark: '' })

const submitMetric = async () => {
  if (!metricForm.metric_type) {
    ElMessage.warning('请选择指标类型')
    return
  }
  const res = await api.post(`/campaigns/${currentCampaign.value.id}/metrics`, {
    metric_type: metricForm.metric_type,
    metric_value: metricForm.metric_value,
    remark: metricForm.remark
  })
  if (res.code === 200) {
    ElMessage.success('指标录入成功')
    showMetricModal.value = false
    metricForm.metric_value = 0
    metricForm.remark = ''
    // 刷新详情
    const detail = await api.get(`/campaigns/${currentCampaign.value.id}`)
    if (detail.code === 200) currentCampaign.value = detail.data
  } else {
    ElMessage.error(res.message || '录入失败')
  }
}

// ============ 受众管理 ============
const showAudienceDrawer = ref(false)
const audiences = ref([])

const openAudienceModal = async (row) => {
  currentCampaign.value = row
  await fetchAudiences(row.id)
  showAudienceDrawer.value = true
}

const fetchAudiences = async (campaignId) => {
  const res = await api.get(`/campaigns/${campaignId}/audiences`)
  if (res.code === 200) {
    audiences.value = res.data || []
  }
}

const showAudienceAddModal = ref(false)
const audienceForm = reactive({
  contact_name: '', contact_info: '', reach_status: 'pending',
  converted_amount: 0, feedback: ''
})

const openAudienceAddModal = () => {
  Object.assign(audienceForm, {
    contact_name: '', contact_info: '', reach_status: 'pending',
    converted_amount: 0, feedback: ''
  })
  showAudienceAddModal.value = true
}

const submitAudience = async () => {
  if (!audienceForm.contact_name) {
    ElMessage.warning('请输入联系人')
    return
  }
  const res = await api.post(`/campaigns/${currentCampaign.value.id}/audiences`, audienceForm)
  if (res.code === 200) {
    ElMessage.success('受众添加成功')
    showAudienceAddModal.value = false
    fetchAudiences(currentCampaign.value.id)
  } else {
    ElMessage.error(res.message || '添加失败')
  }
}

const updateAudienceStatus = async (row) => {
  const res = await api.put(`/campaigns/audiences/${row.id}`, {
    reach_status: row.reach_status,
    converted_amount: row.converted_amount
  })
  if (res.code !== 200) {
    ElMessage.error(res.message || '更新失败')
    fetchAudiences(currentCampaign.value.id)
  }
}

const deleteAudience = (row) => {
  ElMessageBox.confirm('确认删除该受众记录？', '提示', {
    type: 'warning', confirmButtonText: '确认', cancelButtonText: '取消'
  }).then(async () => {
    const res = await api.delete(`/campaigns/audiences/${row.id}`)
    if (res.code === 200) {
      ElMessage.success('删除成功')
      fetchAudiences(currentCampaign.value.id)
    } else {
      ElMessage.error(res.message || '删除失败')
    }
  }).catch(() => {})
}

// ============ 效果分析 ============
const analytics = ref({ campaigns: [], summary: {} })

const fetchAnalytics = async () => {
  const res = await api.get('/campaigns/analytics')
  if (res.code === 200) {
    analytics.value = res.data || { campaigns: [], summary: {} }
  } else {
    ElMessage.error(res.message || '获取分析数据失败')
  }
}

// ============ 自动化规则 ============
const automations = ref([])
const showAutomationModal = ref(false)
const automationFormRef = ref()
const automationForm = reactive({
  id: null, name: '', trigger_type: '', trigger_config_str: '',
  action_type: '', action_config_str: '', status: 'active', remark: ''
})
const automationRules = {
  name: [{ required: true, message: '请输入规则名称', trigger: 'blur' }]
}

const fetchAutomations = async () => {
  const res = await api.get('/campaigns/automations')
  if (res.code === 200) {
    automations.value = res.data || []
  } else {
    ElMessage.error(res.message || '获取规则列表失败')
  }
}

const openAutomationModal = (row) => {
  if (row) {
    const tc = typeof row.trigger_config === 'object' ? JSON.stringify(row.trigger_config, null, 2) : (row.trigger_config || '')
    const ac = typeof row.action_config === 'object' ? JSON.stringify(row.action_config, null, 2) : (row.action_config || '')
    Object.assign(automationForm, {
      id: row.id, name: row.name, trigger_type: row.trigger_type,
      trigger_config_str: tc, action_type: row.action_type,
      action_config_str: ac, status: row.status, remark: row.remark
    })
  } else {
    Object.assign(automationForm, {
      id: null, name: '', trigger_type: '', trigger_config_str: '',
      action_type: '', action_config_str: '', status: 'active', remark: ''
    })
  }
  showAutomationModal.value = true
}

const submitAutomation = async () => {
  if (!automationFormRef.value) return
  await automationFormRef.value.validate(async (valid) => {
    if (!valid) return
    // 解析 JSON 配置
    let triggerConfig = null
    let actionConfig = null
    try {
      if (automationForm.trigger_config_str.trim()) {
        triggerConfig = JSON.parse(automationForm.trigger_config_str)
      }
    } catch (e) {
      ElMessage.error('触发配置 JSON 格式错误')
      return
    }
    try {
      if (automationForm.action_config_str.trim()) {
        actionConfig = JSON.parse(automationForm.action_config_str)
      }
    } catch (e) {
      ElMessage.error('动作配置 JSON 格式错误')
      return
    }

    const payload = {
      name: automationForm.name,
      trigger_type: automationForm.trigger_type,
      trigger_config: triggerConfig,
      action_type: automationForm.action_type,
      action_config: actionConfig,
      status: automationForm.status,
      remark: automationForm.remark
    }

    if (automationForm.id) {
      const res = await api.put(`/campaigns/automations/${automationForm.id}`, payload)
      if (res.code === 200) {
        ElMessage.success('规则更新成功')
        showAutomationModal.value = false
        fetchAutomations()
      } else {
        ElMessage.error(res.message || '更新失败')
      }
    } else {
      const res = await api.post('/campaigns/automations', payload)
      if (res.code === 200) {
        ElMessage.success('规则创建成功')
        showAutomationModal.value = false
        fetchAutomations()
      } else {
        ElMessage.error(res.message || '创建失败')
      }
    }
  })
}

const deleteAutomation = (row) => {
  ElMessageBox.confirm(`确认删除规则「${row.name}」？`, '提示', {
    type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消'
  }).then(async () => {
    const res = await api.delete(`/campaigns/automations/${row.id}`)
    if (res.code === 200) {
      ElMessage.success('删除成功')
      fetchAutomations()
    } else {
      ElMessage.error(res.message || '删除失败')
    }
  }).catch(() => {})
}

const runAutomation = (row) => {
  ElMessageBox.confirm(`确认手动执行规则「${row.name}」？`, '提示', {
    type: 'info', confirmButtonText: '执行', cancelButtonText: '取消'
  }).then(async () => {
    const res = await api.post(`/campaigns/automations/${row.id}/run`)
    if (res.code === 200) {
      ElMessage.success('规则执行成功')
      fetchAutomations()
    } else {
      ElMessage.error(res.message || '执行失败')
    }
  }).catch(() => {})
}

// ============ Tab 切换时加载数据 ============
const handleTabChange = (tab) => {
  if (tab === 'campaigns') fetchCampaigns()
  else if (tab === 'analytics') fetchAnalytics()
  else if (tab === 'automations') fetchAutomations()
}

import { watch } from 'vue'
watch(activeTab, handleTabChange)

onMounted(() => {
  fetchCampaigns()
})
</script>

<style scoped>
.marketing { padding: 0; }
.content-tabs { background: transparent; }

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
.search-btn { margin-left: 4px; }

.table-container {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.table-wrapper { overflow-x: auto; }
.data-table { width: 100%; }

.analytics-summary {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
.summary-card {
  text-align: center;
  padding: 8px 0;
}
.summary-value {
  font-size: 22px;
  font-weight: 700;
  color: #409eff;
  margin-bottom: 4px;
}
.summary-label {
  font-size: 13px;
  color: #909399;
}

.detail-content { padding: 0 8px; }
.detail-section { margin-top: 20px; }
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.section-header h4 { margin: 0; color: #303133; }
.audience-stats { display: flex; gap: 10px; flex-wrap: wrap; }
.stat-tag { font-size: 14px; }

@media (max-width: 1200px) {
  .analytics-summary { grid-template-columns: repeat(3, 1fr); }
}
</style>
