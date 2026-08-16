<template>
  <div class="visits-container">
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">📅 客户拜访排班</h2>
      </div>
      <div class="header-right">
        <el-button-group>
          <el-button 
            :type="viewMode === 'calendar' ? 'primary' : ''" 
            @click="viewMode = 'calendar'"
          >
            📆 日历视图
          </el-button>
          <el-button 
            :type="viewMode === 'list' ? 'primary' : ''" 
            @click="viewMode = 'list'"
          >
            📋 列表视图
          </el-button>
          <el-button 
            :type="viewMode === 'personnel' ? 'primary' : ''" 
            @click="viewMode = 'personnel'"
          >
            👥 人员排班
          </el-button>
        </el-button-group>
        <el-button type="primary" @click="openAddDialog">+ 新增排班</el-button>
        <el-button type="success" :loading="exporting" @click="exportWeeklyReport">
          📄 导出周报
        </el-button>
      </div>
    </div>

    <div class="stats-section">
      <div class="stat-card">
        <div class="stat-icon total">📅</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.total || 0 }}</div>
          <div class="stat-label">本月总拜访</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon planned">⏰</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.planned || 0 }}</div>
          <div class="stat-label">待拜访</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon completed">✅</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.completed || 0 }}</div>
          <div class="stat-label">已完成</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon cancelled">❌</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.cancelled || 0 }}</div>
          <div class="stat-label">已取消</div>
        </div>
      </div>
    </div>

    <div class="filter-section">
      <el-date-picker
        v-model="filterDateRange"
        type="daterange"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        @change="fetchVisits"
      />
      <el-select v-model="filterStatus" placeholder="状态" clearable @change="fetchVisits">
        <el-option label="待完成" value="planned" />
        <el-option label="已完成" value="completed" />
        <el-option label="已取消" value="cancelled" />
      </el-select>
      <el-select v-model="filterVisitorId" placeholder="人员" clearable @change="fetchVisits">
        <el-option 
          v-for="user in userList" 
          :key="user.username" 
          :label="user.name" 
          :value="user.username"
        />
      </el-select>
      <el-select v-model="filterWorkType" placeholder="类型" clearable @change="fetchVisits">
        <el-option label="客户拜访" value="visit" />
        <el-option label="其它工作" value="other" />
      </el-select>
      <el-input 
        v-model="searchKeyword" 
        placeholder="搜索客户/目的" 
        clearable
        @keyup.enter="fetchVisits"
        style="width: 200px;"
      />
      <el-button type="primary" @click="fetchVisits">搜索</el-button>
    </div>

    <div v-if="viewMode === 'calendar'" class="calendar-view">
      <el-calendar v-model="currentDate">
        <template #date-cell="{ data }">
          <div class="calendar-cell" :class="getCellClass(data)">
            <div class="date-number">{{ data.day.split('-').slice(-1)[0] }}</div>
            <div class="day-visits">
              <div
                v-for="visit in getDayVisitsLimited(data.day)"
                :key="visit.id"
                class="visit-tag"
                :class="[visit.status, { 'other-work': visit.work_type === 'other' }]"
                :title="`${visit.plan_time || ''} ${getVisitLabel(visit)}`"
                @click="openDetailDialog(visit)"
              >
                <span class="visit-time" v-if="visit.plan_time">{{ visit.plan_time }}</span>
                <span class="visit-text">{{ getVisitLabel(visit) }}</span>
              </div>
              <div
                v-if="getDayExtraCount(data.day) > 0"
                class="visit-more"
                @click="openDayListDialog(data.day)"
              >
                +{{ getDayExtraCount(data.day) }} 条
              </div>
            </div>
          </div>
        </template>
      </el-calendar>
    </div>

    <div v-else-if="viewMode === 'list'" class="list-view">
      <div class="table-container">
        <div class="table-wrapper">
          <el-table :data="pagedVisits" stripe style="width: 100%">
            <el-table-column prop="plan_date" label="计划日期" min-width="100" sortable>
              <template #default="{ row }">
                {{ formatDate(row.plan_date) }}
              </template>
            </el-table-column>
            <el-table-column prop="plan_time" label="时间" min-width="70">
              <template #default="{ row }">
                {{ row.plan_time || '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="work_type" label="类型" min-width="90">
              <template #default="{ row }">
                <el-tag :type="row.work_type === 'visit' ? 'primary' : 'success'" effect="plain">
                  {{ row.work_type === 'visit' ? '客户拜访' : '其它工作' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="customer_name" label="客户名称" min-width="140" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.work_type === 'other' ? '-' : (row.customer_name || '-') }}
              </template>
            </el-table-column>
            <el-table-column prop="customer_company" label="公司" min-width="140" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.work_type === 'other' ? '-' : (row.customer_company || '-') }}
              </template>
            </el-table-column>
            <el-table-column prop="enterprise_name" label="关联企业" min-width="140" show-overflow-tooltip>
              <template #default="{ row }">
                <el-link v-if="row.enterprise_id" type="primary" @click="$router.push('/enterprises')">{{ row.enterprise_name }}</el-link>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column prop="purpose" label="内容" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.work_type === 'other' ? (row.work_content || '-') : (row.purpose || '-') }}
              </template>
            </el-table-column>
            <el-table-column prop="visitor_name" label="执行人" min-width="90">
              <template #default="{ row }">
                {{ row.visitor_name || row.visitor_id }}
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" min-width="90">
              <template #default="{ row }">
                <el-tag :type="getStatusType(row.status)" effect="dark">
                  {{ getStatusText(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="300" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-if="row.status === 'completed' && row.work_type === 'visit'"
                  type="primary"
                  size="small"
                  @click="generateReview(row)"
                >
                  AI复盘
                </el-button>
                <el-button
                  v-if="row.status === 'planned'"
                  type="success"
                  size="small"
                  @click="openCompleteDialog(row)"
                >
                  完成
                </el-button>
                <el-button type="primary" size="small" @click="openDetailDialog(row)">详情</el-button>
                <el-button 
                  v-if="row.status === 'planned'" 
                  size="small" 
                  @click="openEditDialog(row)"
                >
                  编辑
                </el-button>
                <el-button 
                  v-if="row.status === 'planned'" 
                  type="warning" 
                  size="small" 
                  @click="handleCancel(row)"
                >
                  取消
                </el-button>
                <el-button 
                  type="danger" 
                  size="small" 
                  @click="handleDelete(row)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <div class="pagination-wrapper">
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :page-sizes="[10, 20, 50]"
            :total="filteredVisits.length"
            layout="total, sizes, prev, pager, next, jumper"
            background
          />
        </div>
      </div>
    </div>

    <div v-else-if="viewMode === 'personnel'" class="personnel-view">
      <el-tabs v-model="activePersonnelTab" type="border-card">
        <el-tab-pane v-for="user in userList" :key="user.username" :label="user.name" :name="user.username">
          <div class="personnel-schedule">
            <el-table :data="getUserVisits(user.username)" stripe style="width: 100%">
              <el-table-column prop="plan_date" label="计划日期" min-width="100" sortable>
                <template #default="{ row }">
                  {{ formatDate(row.plan_date) }}
                </template>
              </el-table-column>
              <el-table-column prop="plan_time" label="时间" min-width="70">
                <template #default="{ row }">
                  {{ row.plan_time || '-' }}
                </template>
              </el-table-column>
              <el-table-column prop="work_type" label="类型" min-width="100">
                <template #default="{ row }">
                  <el-tag :type="row.work_type === 'visit' ? 'primary' : 'success'" effect="plain">
                    {{ row.work_type === 'visit' ? '客户拜访' : '其它工作' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="内容" min-width="200" show-overflow-tooltip>
                <template #default="{ row }">
                  <div v-if="row.work_type === 'visit'">
                    <div>{{ row.purpose || '-' }}</div>
                    <div class="sub-info" v-if="row.customer_name">{{ row.customer_name }} ({{ row.customer_company }})</div>
                  </div>
                  <div v-else>
                    {{ row.work_content || '-' }}
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="location" label="地点" min-width="100" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ row.location || '-' }}
                </template>
              </el-table-column>
              <el-table-column prop="status" label="状态" min-width="90">
                <template #default="{ row }">
                  <el-tag :type="getStatusType(row.status)" effect="dark">
                    {{ getStatusText(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="180" fixed="right">
                <template #default="{ row }">
                  <el-button 
                    v-if="row.status === 'planned'" 
                    type="success" 
                    size="small" 
                    @click="openCompleteDialog(row)"
                  >
                    完成
                  </el-button>
                  <el-button 
                    v-if="row.status === 'planned'" 
                    size="small" 
                    @click="openEditDialog(row)"
                  >
                    编辑
                  </el-button>
                  <el-button 
                    v-if="row.status === 'planned'" 
                    type="warning" 
                    size="small" 
                    @click="handleCancel(row)"
                  >
                    取消
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="getUserVisits(user.username).length === 0" description="暂无排班" />
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <el-dialog v-model="addDialogVisible" title="新增排班计划" width="600px" :close-on-click-modal="false" :close-on-press-escape="false">
      <el-form :model="visitForm" label-width="100px" ref="visitFormRef" :rules="formRules">
        <el-form-item label="类型" prop="work_type">
          <el-radio-group v-model="visitForm.work_type">
            <el-radio value="visit">客户拜访</el-radio>
            <el-radio value="other">其它工作</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="visitForm.work_type === 'visit'" label="客户" prop="cust_id">
          <el-select v-model="visitForm.cust_id" placeholder="选择客户" filterable>
            <el-option
              v-for="customer in customerList"
              :key="customer.id"
              :label="`${customer.name} (${customer.company})`"
              :value="customer.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="visitForm.work_type === 'visit'" label="关联企业">
          <el-select v-model="visitForm.enterprise_id" placeholder="选择企业信息库（可选）" filterable clearable>
            <el-option
              v-for="ent in enterpriseList"
              :key="ent.id"
              :label="ent.name"
              :value="ent.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-else label="工作内容" prop="work_content">
          <el-input v-model="visitForm.work_content" type="textarea" :rows="3" placeholder="请输入工作内容" />
        </el-form-item>
        <el-form-item label="执行人" prop="visitor_id">
          <el-select v-model="visitForm.visitor_id" placeholder="选择执行人">
            <el-option 
              v-for="user in userList" 
              :key="user.username" 
              :label="user.name" 
              :value="user.username"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="计划日期" prop="plan_date">
          <el-date-picker 
            v-model="visitForm.plan_date" 
            type="date" 
            placeholder="选择日期"
            value-format="YYYY-MM-DD"
          />
        </el-form-item>
        <el-form-item label="计划时间" prop="plan_time">
          <el-time-picker 
            v-model="visitForm.plan_time" 
            placeholder="选择时间"
            value-format="HH:mm"
          />
        </el-form-item>
        <el-form-item v-if="visitForm.work_type === 'visit'" label="拜访目的" prop="purpose">
          <el-input v-model="visitForm.purpose" placeholder="请输入拜访目的" />
        </el-form-item>
        <el-form-item label="地点">
          <el-input v-model="visitForm.location" :placeholder="visitForm.work_type === 'visit' ? '请输入拜访地点' : '请输入工作地点'" />
        </el-form-item>
        <el-form-item v-if="visitForm.work_type === 'visit'" label="联系人">
          <el-input v-model="visitForm.contact_person" placeholder="请输入联系人" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="visitForm.notes" type="textarea" :rows="2" placeholder="备注信息" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailDialogVisible" title="排班详情" width="600px" :close-on-click-modal="false" :close-on-press-escape="false">
      <el-descriptions :column="2" border v-if="currentVisit">
        <el-descriptions-item label="类型">
          <el-tag :type="currentVisit.work_type === 'visit' ? 'primary' : 'success'" effect="plain">
            {{ currentVisit.work_type === 'visit' ? '客户拜访' : '其它工作' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="执行人">
          {{ currentVisit.visitor_name || currentVisit.visitor_id }}
        </el-descriptions-item>
        <el-descriptions-item v-if="currentVisit.work_type === 'visit'" label="客户">
          {{ currentVisit.customer_name }} ({{ currentVisit.customer_company }})
        </el-descriptions-item>
        <el-descriptions-item v-if="currentVisit.enterprise_id" label="关联企业">
          <el-link type="primary" @click="$router.push('/enterprises')">{{ currentVisit.enterprise_name }}</el-link>
        </el-descriptions-item>
        <el-descriptions-item label="计划日期">
          {{ formatDate(currentVisit.plan_date) }}
        </el-descriptions-item>
        <el-descriptions-item label="计划时间">
          {{ currentVisit.plan_time || '-' }}
        </el-descriptions-item>
        <el-descriptions-item v-if="currentVisit.work_type === 'visit'" label="拜访目的" :span="2">
          {{ currentVisit.purpose || '-' }}
        </el-descriptions-item>
        <el-descriptions-item v-else label="工作内容" :span="2">
          {{ currentVisit.work_content || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="地点">
          {{ currentVisit.location || '-' }}
        </el-descriptions-item>
        <el-descriptions-item v-if="currentVisit.work_type === 'visit'" label="联系人">
          {{ currentVisit.contact_person || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getStatusType(currentVisit.status)">
            {{ getStatusText(currentVisit.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="创建时间">
          {{ currentVisit.created_at }}
        </el-descriptions-item>
        <el-descriptions-item label="实际日期" v-if="currentVisit.actual_date">
          {{ formatDate(currentVisit.actual_date) }}
        </el-descriptions-item>
        <el-descriptions-item label="实际时间" v-if="currentVisit.actual_time">
          {{ currentVisit.actual_time }}
        </el-descriptions-item>
        <el-descriptions-item label="完成结果" v-if="currentVisit.result" :span="2">
          {{ currentVisit.result }}
        </el-descriptions-item>
        <el-descriptions-item label="备注" v-if="currentVisit.notes" :span="2">
          {{ currentVisit.notes }}
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button v-if="currentVisit?.status === 'planned'" type="success" @click="openCompleteDialog(currentVisit)">
          完成拜访
        </el-button>
        <el-button v-if="currentVisit?.status === 'planned'" @click="openEditDialog(currentVisit)">
          编辑
        </el-button>
        <el-button v-if="currentVisit?.status === 'completed'" type="warning" @click="openEditCompleteDialog(currentVisit)">
          修改完成记录
        </el-button>
        <el-button
          v-if="currentVisit?.status === 'completed' && currentVisit?.work_type === 'visit'"
          type="primary"
          @click="generateReview(currentVisit)"
        >
          🤖 AI 复盘
        </el-button>
        <el-button @click="detailDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="completeDialogVisible" :title="completeDialogTitle" width="680px" :close-on-click-modal="false" :close-on-press-escape="false">
      <el-form :model="completeForm" label-width="100px" :disabled="completing">
        <el-form-item label="实际日期">
          <el-date-picker 
            v-model="completeForm.actual_date" 
            type="date" 
            placeholder="选择日期"
            value-format="YYYY-MM-DD"
          />
        </el-form-item>
        <el-form-item label="实际时间">
          <el-time-picker 
            v-model="completeForm.actual_time" 
            placeholder="选择时间"
            value-format="HH:mm"
          />
        </el-form-item>
        <el-divider v-if="currentVisit?.work_type === 'visit' && completeMode === 'create'" content-position="left">📝 跟进信息（将同步到客户和商机）</el-divider>
        <!-- 修改模式：只显示完成结果输入框 -->
        <template v-if="completeMode === 'edit'">
          <el-form-item label="完成结果">
            <el-input
              v-model="completeForm.follow_content"
              type="textarea"
              :rows="5"
              placeholder="请输入完成结果/跟进内容"
            />
          </el-form-item>
        </template>
        <!-- 创建模式 + 客户拜访：显示跟进信息 -->
        <template v-else-if="currentVisit?.work_type === 'visit'">
          <el-form-item label="跟进方式">
            <el-select v-model="completeForm.follow_type" placeholder="选择跟进方式" style="width:100%">
              <el-option label="面谈" value="面谈" />
              <el-option label="电话" value="电话" />
              <el-option label="邮件" value="邮件" />
              <el-option label="微信" value="微信" />
              <el-option label="视频会议" value="视频会议" />
              <el-option label="其他" value="其他" />
            </el-select>
          </el-form-item>
          <el-form-item label="跟进内容" required>
            <el-input
              v-model="completeForm.follow_content"
              type="textarea"
              :rows="4"
              placeholder="请输入本次跟进的详细内容、客户反馈、讨论要点等"
            />
          </el-form-item>
          <el-form-item label="下一步计划">
            <el-input
              v-model="completeForm.next_action"
              placeholder="下一步要做什么（如：发送方案、安排 demo、准备报价等）"
            />
          </el-form-item>
          <el-form-item label="计划日期">
            <el-date-picker
              v-model="completeForm.next_date"
              type="date"
              placeholder="下一步行动日期"
              value-format="YYYY-MM-DD"
            />
          </el-form-item>
          <el-form-item v-if="customerBusinesses.length > 0" label="关联商机">
            <el-select
              v-model="completeForm.business_ids"
              multiple
              placeholder="选择关联的商机（不选则自动关联所有活跃商机）"
              style="width:100%"
            >
              <el-option
                v-for="biz in customerBusinesses"
                :key="biz.id"
                :label="`${biz.name}（${biz.stage}，概率${biz.probability}%）`"
                :value="biz.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item v-else label="关联商机">
            <span class="muted">该客户暂无活跃商机，完成后将自动创建客户跟进记录</span>
          </el-form-item>
        </template>
        <!-- 创建模式 + 其它工作：显示完成情况 -->
        <template v-else>
          <el-form-item label="完成情况">
            <el-input
              v-model="completeForm.result"
              type="textarea"
              :rows="4"
              placeholder="请输入工作完成情况"
            />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="completeDialogVisible = false" :disabled="completing">取消</el-button>
        <el-button v-if="completeMode === 'create'" type="primary" @click="handleComplete" :loading="completing">确定并同步跟进</el-button>
        <el-button v-else type="primary" @click="handleUpdateComplete" :loading="completing">保存修改</el-button>
      </template>
    </el-dialog>

    <!-- AI 复盘对话框 -->
    <el-dialog v-model="reviewDialogVisible" title="🤖 AI 拜访复盘" width="680px" top="6vh" :close-on-click-modal="false" :close-on-press-escape="false">
      <div v-loading="reviewLoading" element-loading-text="AI 正在生成结构化复盘摘要...">
        <div v-if="reviewData" class="review-content">
          <div class="review-title">{{ reviewData.title }}</div>
          <div class="review-summary">{{ reviewData.summary }}</div>
          <div class="review-section" v-if="reviewData.key_findings && reviewData.key_findings.length">
            <div class="review-section-title">🔍 关键发现</div>
            <ul><li v-for="(f, i) in reviewData.key_findings" :key="i">{{ f }}</li></ul>
          </div>
          <div class="review-section" v-if="reviewData.customer_needs && reviewData.customer_needs.length">
            <div class="review-section-title">💡 客户需求</div>
            <ul><li v-for="(f, i) in reviewData.customer_needs" :key="i">{{ f }}</li></ul>
          </div>
          <div class="review-section" v-if="reviewData.next_actions && reviewData.next_actions.length">
            <div class="review-section-title">📌 下一步行动</div>
            <ul><li v-for="(f, i) in reviewData.next_actions" :key="i">{{ f }}</li></ul>
          </div>
          <div class="review-section" v-if="reviewData.risk_warnings && reviewData.risk_warnings.length">
            <div class="review-section-title">⚠️ 风险提示</div>
            <ul><li v-for="(f, i) in reviewData.risk_warnings" :key="i">{{ f }}</li></ul>
          </div>
          <div class="review-section" v-if="reviewData.deal_signals">
            <div class="review-section-title">🎯 成交信号</div>
            <div class="review-deal">{{ reviewData.deal_signals }}</div>
          </div>
          <div class="review-tip" v-if="reviewData._fallback">
            <span>ℹ️ 当前未启用大语言模型，以上为基于拜访记录的模板摘要。配置 LLM_API_KEY 后可获得更深入的智能分析。</span>
          </div>
          <div class="review-saved" v-if="reviewKnowledgeId">
            ✅ 复盘摘要已自动沉淀至<a href="#/knowledge" target="_blank">企业知识库</a>（ID: {{ reviewKnowledgeId }}）
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="reviewDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 当天全部拜访列表 -->
    <el-dialog
      v-model="dayListDialogVisible"
      :title="`${dayListDate} 拜访列表（${dayListVisits.length} 条）`"
      width="640px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
    >
      <el-empty v-if="dayListVisits.length === 0" description="当天无排班" />
      <div v-else class="day-list">
        <div
          v-for="visit in dayListVisits"
          :key="visit.id"
          class="day-list-item"
          :class="visit.status"
          @click="openDetailDialog(visit); dayListDialogVisible = false"
        >
          <div class="day-list-time">{{ visit.plan_time || '全天' }}</div>
          <div class="day-list-content">
            <div class="day-list-title">{{ getVisitLabel(visit) }}</div>
            <div class="day-list-sub" v-if="visit.work_type === 'visit'">
              {{ visit.visitor_name || visit.visitor_id || '-' }}<span v-if="visit.location"> · {{ visit.location }}</span>
            </div>
          </div>
          <el-tag :type="getStatusType(visit.status)" size="small" effect="dark">
            {{ getStatusText(visit.status) }}
          </el-tag>
        </div>
      </div>
      <template #footer>
        <el-button @click="dayListDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { useAuthStore } from '../stores/auth'
import { ElMessage, ElMessageBox } from 'element-plus'

const authStore = useAuthStore()
const token = computed(() => authStore.token)

const viewMode = ref('calendar')
const currentDate = ref(new Date())
const visits = ref([])
const stats = ref({})
const customerList = ref([])
const userList = ref([])
const enterpriseList = ref([])

const filterDateRange = ref([])
const filterStatus = ref('')
const filterVisitorId = ref('')
const filterWorkType = ref('')
const searchKeyword = ref('')

const currentPage = ref(1)
const pageSize = ref(10)

const addDialogVisible = ref(false)
const detailDialogVisible = ref(false)
const completeDialogVisible = ref(false)
const visitFormRef = ref(null)

// AI 复盘相关状态
const reviewDialogVisible = ref(false)
const reviewLoading = ref(false)
const reviewData = ref(null)
const reviewKnowledgeId = ref(null)

const activePersonnelTab = ref('')

const visitForm = reactive({
  id: null,
  work_type: 'visit',
  cust_id: null,
  enterprise_id: null,
  work_content: '',
  visitor_id: authStore.username,
  plan_date: '',
  plan_time: '',
  purpose: '',
  location: '',
  contact_person: '',
  notes: ''
})

const completeForm = reactive({
  actual_date: new Date().toISOString().split('T')[0],
  actual_time: new Date().toTimeString().slice(0, 5),
  result: '',
  follow_type: '面谈',
  follow_content: '',
  next_action: '',
  next_date: '',
  business_ids: []
})

// 完成对话框模式：create=首次完成，edit=修改已完成记录
const completeMode = ref('create')
const completeDialogTitle = computed(() =>
  completeMode.value === 'create' ? '完成拜访并录入跟进信息' : '修改完成记录'
)

const currentVisit = ref(null)
const customerBusinesses = ref([])
const completing = ref(false)

const validateCustId = (rule, value, callback) => {
  if (visitForm.work_type === 'visit' && !value) {
    callback(new Error('请选择客户'))
  } else {
    callback()
  }
}

const validateWorkContent = (rule, value, callback) => {
  if (visitForm.work_type === 'other' && !value) {
    callback(new Error('请输入工作内容'))
  } else {
    callback()
  }
}

const validatePurpose = (rule, value, callback) => {
  if (visitForm.work_type === 'visit' && !value) {
    callback(new Error('请输入拜访目的'))
  } else {
    callback()
  }
}

const formRules = {
  work_type: [{ required: true, message: '请选择类型', trigger: 'change' }],
  cust_id: [{ validator: validateCustId, trigger: 'change' }],
  work_content: [{ validator: validateWorkContent, trigger: 'blur' }],
  visitor_id: [{ required: true, message: '请选择执行人', trigger: 'change' }],
  plan_date: [{ required: true, message: '请选择计划日期', trigger: 'change' }],
  purpose: [{ validator: validatePurpose, trigger: 'blur' }]
}

const filteredVisits = computed(() => {
  let result = [...visits.value]
  
  if (filterStatus.value) {
    result = result.filter(v => v.status === filterStatus.value)
  }
  
  if (filterVisitorId.value) {
    result = result.filter(v => v.visitor_id === filterVisitorId.value)
  }
  
  if (filterWorkType.value) {
    result = result.filter(v => v.work_type === filterWorkType.value)
  }
  
  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase()
    result = result.filter(v => 
      (v.customer_name && v.customer_name.toLowerCase().includes(keyword)) ||
      (v.customer_company && v.customer_company.toLowerCase().includes(keyword)) ||
      (v.purpose && v.purpose.toLowerCase().includes(keyword)) ||
      (v.work_content && v.work_content.toLowerCase().includes(keyword))
    )
  }
  
  if (filterDateRange.value && filterDateRange.value.length === 2) {
    const [start, end] = filterDateRange.value
    result = result.filter(v => v.plan_date >= start && v.plan_date <= end)
  }
  
  return result
})

const getUserVisits = (username) => {
  return filteredVisits.value.filter(v => v.visitor_id === username)
}

const pagedVisits = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredVisits.value.slice(start, start + pageSize.value)
})

const getDayVisits = (day) => {
  return visits.value.filter(v => v.plan_date === day)
}

// 日历单元格每天最多显示的条数，超出折叠为「+N 条」
const MAX_DAY_VISITS = 3

const getVisitLabel = (visit) => {
  if (!visit) return ''
  return visit.work_type === 'other'
    ? (visit.work_content || '其它工作')
    : (visit.customer_name || visit.customer_company || visit.purpose || '客户拜访')
}

// 当天拜访按时间升序排列，无时间的排到最后
const getDayVisitsSorted = (day) => {
  return visits.value
    .filter(v => v.plan_date === day)
    .slice()
    .sort((a, b) => {
      const ta = a.plan_time || '99:99'
      const tb = b.plan_time || '99:99'
      return ta.localeCompare(tb)
    })
}

const getDayVisitsLimited = (day) => {
  return getDayVisitsSorted(day).slice(0, MAX_DAY_VISITS)
}

const getDayExtraCount = (day) => {
  return Math.max(0, getDayVisitsSorted(day).length - MAX_DAY_VISITS)
}

// 当天全部拜访弹窗
const dayListDialogVisible = ref(false)
const dayListDate = ref('')
const dayListVisits = computed(() => getDayVisitsSorted(dayListDate.value))
const openDayListDialog = (day) => {
  dayListDate.value = day
  dayListDialogVisible.value = true
}

const getCellClass = (data) => {
  const hasVisit = visits.value.some(v => v.plan_date === data.day)
  return hasVisit ? 'has-visit' : ''
}

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return dateStr
}

const getStatusType = (status) => {
  const map = {
    'planned': 'warning',
    'completed': 'success',
    'cancelled': 'info'
  }
  return map[status] || ''
}

const getStatusText = (status) => {
  const map = {
    'planned': '待完成',
    'completed': '已完成',
    'cancelled': '已取消'
  }
  return map[status] || status
}

const fetchVisits = async () => {
  try {
    const params = new URLSearchParams()
    if (filterStatus.value) params.append('status', filterStatus.value)
    if (filterVisitorId.value) params.append('visitor_id', filterVisitorId.value)
    
    const res = await fetch(`/api/visits?${params.toString()}`, {
      headers: { 'Authorization': `Bearer ${token.value}` }
    })
    const data = await res.json()
    if (data.code === 200) {
      visits.value = data.data.map(v => ({
        ...v,
        work_type: v.work_type || 'visit',
        work_content: v.work_content || ''
      }))
    }
  } catch (error) {
    ElMessage.error('获取排班记录失败')
  }
}

const fetchStats = async () => {
  try {
    const res = await fetch('/api/visits/stats/summary', {
      headers: { 'Authorization': `Bearer ${token.value}` }
    })
    const data = await res.json()
    if (data.code === 200) {
      stats.value = data.data
    }
  } catch (error) {
    console.error('获取统计数据失败:', error)
  }
}

const fetchCustomers = async () => {
  try {
    const res = await fetch('/api/customers', {
      headers: { 'Authorization': `Bearer ${token.value}` }
    })
    const data = await res.json()
    if (data.code === 200) {
      customerList.value = data.data
    }
  } catch (error) {
    console.error('获取客户列表失败:', error)
  }
}

const fetchUsers = async () => {
  try {
    const res = await fetch('/api/users?role=销售', {
      headers: { 'Authorization': `Bearer ${token.value}` }
    })
    const data = await res.json()
    if (data.code === 200) {
      userList.value = data.data
    }
  } catch (error) {
    console.error('获取用户列表失败:', error)
  }
}

const fetchEnterprises = async () => {
  try {
    const res = await fetch('/api/enterprises', {
      headers: { 'Authorization': `Bearer ${token.value}` }
    })
    const data = await res.json()
    if (data.code === 200) {
      enterpriseList.value = data.data || []
    }
  } catch (error) {
    console.error('获取企业列表失败:', error)
  }
}

// 导出应用中心工作周报（Excel：每人本周工作 + 下周安排）
const exporting = ref(false)
const exportWeeklyReport = async () => {
  exporting.value = true
  try {
    const response = await fetch('/api/visits/export-weekly-report', {
      headers: { 'Authorization': `Bearer ${token.value}` }
    })
    if (!response.ok) {
      const errData = await response.json().catch(() => null)
      throw new Error(errData?.message || '导出失败')
    }
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    // 从响应头解析文件名，解析失败则用默认名
    let filename = '应用中心工作周报.xlsx'
    const disposition = response.headers.get('Content-Disposition')
    if (disposition) {
      const match = disposition.match(/filename\*?=([^;]+)/)
      if (match) {
        filename = decodeURIComponent(match[1].replace(/['"]/g, '').replace(/UTF-8''/i, ''))
      }
    }
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    ElMessage.success('周报导出成功')
  } catch (e) {
    ElMessage.error('周报导出失败：' + e.message)
  } finally {
    exporting.value = false
  }
}

const openAddDialog = () => {
  Object.assign(visitForm, {
    id: null,
    work_type: 'visit',
    cust_id: null,
    enterprise_id: null,
    work_content: '',
    visitor_id: authStore.username,
    plan_date: new Date().toISOString().split('T')[0],
    plan_time: '09:00',
    purpose: '',
    location: '',
    contact_person: '',
    notes: ''
  })
  addDialogVisible.value = true
}

const openDetailDialog = (visit) => {
  currentVisit.value = visit
  detailDialogVisible.value = true
}

const openEditDialog = (visit) => {
  Object.assign(visitForm, {
    id: visit.id,
    work_type: visit.work_type || 'visit',
    cust_id: visit.cust_id,
    enterprise_id: visit.enterprise_id || null,
    work_content: visit.work_content || '',
    visitor_id: visit.visitor_id,
    plan_date: visit.plan_date,
    plan_time: visit.plan_time,
    purpose: visit.purpose,
    location: visit.location,
    contact_person: visit.contact_person,
    notes: visit.notes
  })
  addDialogVisible.value = true
  detailDialogVisible.value = false
}

const openCompleteDialog = async (visit) => {
  currentVisit.value = visit
  completeMode.value = 'create'
  completeForm.actual_date = new Date().toISOString().split('T')[0]
  completeForm.actual_time = new Date().toTimeString().slice(0, 5)
  completeForm.result = ''
  completeForm.follow_type = '面谈'
  completeForm.follow_content = ''
  completeForm.next_action = ''
  completeForm.next_date = ''
  completeForm.business_ids = []
  customerBusinesses.value = []
  
  // 如果是客户拜访类型，加载该客户的活跃商机
  if (visit.work_type === 'visit' && visit.cust_id) {
    try {
      const res = await fetch(`/api/visits/customer-businesses/${visit.cust_id}`, {
        headers: { 'Authorization': `Bearer ${token.value}` }
      })
      const data = await res.json()
      if (data.code === 200) {
        customerBusinesses.value = data.data
      }
    } catch (error) {
      console.error('获取客户商机失败:', error)
    }
  }
  
  completeDialogVisible.value = true
}

// 打开"修改完成记录"对话框：填充已录入的完成内容
const openEditCompleteDialog = async (visit) => {
  currentVisit.value = visit
  completeMode.value = 'edit'
  // 用已有数据填充表单
  completeForm.actual_date = visit.actual_date || new Date().toISOString().split('T')[0]
  completeForm.actual_time = visit.actual_time || new Date().toTimeString().slice(0, 5)
  completeForm.result = visit.result || ''
  // 跟进相关字段在修改模式下不使用（后端 update-complete 不改跟进记录）
  completeForm.follow_type = '面谈'
  completeForm.follow_content = visit.result || ''
  completeForm.next_action = ''
  completeForm.next_date = ''
  completeForm.business_ids = []
  customerBusinesses.value = []

  detailDialogVisible.value = false
  completeDialogVisible.value = true
}

// 保存已完成拜访的修改（只更新 visits 表，不重复创建跟进记录）
const handleUpdateComplete = async () => {
  if (!currentVisit.value) return

  completing.value = true
  try {
    const res = await fetch(`/api/visits/${currentVisit.value.id}/update-complete`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token.value}`
      },
      body: JSON.stringify({
        actual_date: completeForm.actual_date,
        actual_time: completeForm.actual_time,
        result: completeForm.follow_content || completeForm.result
      })
    })
    const data = await res.json()
    if (data.code === 200) {
      ElMessage.success('完成记录已更新')
      completeDialogVisible.value = false
      fetchVisits()
      fetchStats()
    } else {
      ElMessage.error(data.message)
    }
  } catch (error) {
    ElMessage.error('操作失败')
  } finally {
    completing.value = false
  }
}

const handleSave = async () => {
  if (!visitFormRef.value) return
  
  try {
    await visitFormRef.value.validate()
  } catch {
    return
  }
  
  try {
    const url = visitForm.id 
      ? `/api/visits/${visitForm.id}` 
      : '/api/visits'
    const method = visitForm.id ? 'PUT' : 'POST'
    
    const res = await fetch(url, {
      method,
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token.value}` 
      },
      body: JSON.stringify(visitForm)
    })
    const data = await res.json()
    if (data.code === 200) {
      ElMessage.success(data.message)
      addDialogVisible.value = false
      fetchVisits()
      fetchStats()
    } else {
      ElMessage.error(data.message)
    }
  } catch (error) {
    ElMessage.error('保存失败')
  }
}

const handleComplete = async () => {
  if (!currentVisit.value) return

  // 验证：客户拜访类型必须有跟进内容
  if (currentVisit.value.work_type === 'visit' && !completeForm.follow_content.trim()) {
    ElMessage.warning('请填写跟进内容')
    return
  }

  completing.value = true
  try {
    const res = await fetch(`/api/visits/${currentVisit.value.id}/complete`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token.value}`
      },
      body: JSON.stringify({
        actual_date: completeForm.actual_date,
        actual_time: completeForm.actual_time,
        result: completeForm.follow_content || completeForm.result,
        follow_type: completeForm.follow_type,
        follow_content: completeForm.follow_content,
        next_action: completeForm.next_action,
        next_date: completeForm.next_date,
        business_ids: completeForm.business_ids
      })
    })
    const data = await res.json()
    if (data.code === 200) {
      let msg = '拜访已完成'
      if (data.data && data.data.business_follow_count > 0) {
        msg += `，已同步到 ${data.data.business_follow_count} 个商机`
      }
      if (data.data && data.data.customer_follow_created) {
        msg += '，客户跟进已创建'
      }
      ElMessage.success(msg)
      completeDialogVisible.value = false
      detailDialogVisible.value = false
      fetchVisits()
      fetchStats()
    } else {
      ElMessage.error(data.message)
    }
  } catch (error) {
    ElMessage.error('操作失败')
  } finally {
    completing.value = false
  }
}

// AI 复盘：调用智能体生成结构化拜访摘要并沉淀至知识库
const generateReview = async (visit) => {
  if (!visit || !visit.id) return
  reviewDialogVisible.value = true
  reviewLoading.value = true
  reviewData.value = null
  reviewKnowledgeId.value = null
  try {
    const res = await fetch('/api/ai/visit-summary', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token.value}`
      },
      body: JSON.stringify({ visit_id: visit.id, save_to_knowledge: true })
    })
    const data = await res.json()
    if (data.code === 200) {
      reviewData.value = data.data.summary
      reviewKnowledgeId.value = data.data.knowledge_id
    } else {
      ElMessage.error(data.message || '复盘生成失败')
      reviewDialogVisible.value = false
    }
  } catch (error) {
    ElMessage.error('请求失败，请稍后重试')
    reviewDialogVisible.value = false
  } finally {
    reviewLoading.value = false
  }
}

const handleCancel = async (visit) => {
  try {
    await ElMessageBox.confirm('确定要取消这个排班计划吗？', '确认', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    
    const res = await fetch(`/api/visits/${visit.id}/cancel`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token.value}` }
    })
    const data = await res.json()
    if (data.code === 200) {
      ElMessage.success('排班已取消')
      fetchVisits()
      fetchStats()
    } else {
      ElMessage.error(data.message)
    }
  } catch {
    // 用户取消
  }
}

const handleDelete = async (visit) => {
  try {
    await ElMessageBox.confirm('确定要删除这个排班记录吗？', '确认', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    
    const res = await fetch(`/api/visits/${visit.id}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token.value}` }
    })
    const data = await res.json()
    if (data.code === 200) {
      ElMessage.success('删除成功')
      fetchVisits()
      fetchStats()
    } else {
      ElMessage.error(data.message)
    }
  } catch {
    // 用户取消
  }
}

onMounted(async () => {
  fetchVisits()
  fetchStats()
  fetchCustomers()
  fetchEnterprises()
  await fetchUsers()
  if (userList.value.length > 0 && !activePersonnelTab.value) {
    activePersonnelTab.value = userList.value[0].username
  }
})
</script>

<style scoped>
.visits-container {
  max-width: 1400px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}

.page-title {
  margin: 0;
  color: #333;
}

.header-right {
  display: flex;
  gap: 12px;
  align-items: center;
}

.stats-section {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.stat-card {
  background: white;
  border-radius: 12px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
}

.stat-icon {
  width: 50px;
  height: 50px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
}

.stat-icon.total { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
.stat-icon.planned { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }
.stat-icon.completed { background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }
.stat-icon.cancelled { background: linear-gradient(135deg, #bdc3c7 0%, #2c3e50 100%); }

.stat-value {
  font-size: 28px;
  font-weight: bold;
  color: #333;
}

.stat-label {
  font-size: 14px;
  color: #999;
}

.filter-section {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.calendar-view {
  background: white;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

/* 固定 el-calendar 单元格高度，避免内容多时撑高整行导致布局错乱 */
:deep(.el-calendar-table .el-calendar-day) {
  min-height: 110px;
  max-height: 110px;
  height: 110px;
  padding: 0;
  overflow: hidden;
}

.calendar-cell {
  height: 100%;
  min-height: 110px;
  padding: 4px 6px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.calendar-cell.has-visit {
  background: rgba(78, 205, 196, 0.05);
}

.date-number {
  font-size: 13px;
  color: #666;
  margin-bottom: 4px;
  flex-shrink: 0;
}

.day-visits {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow: hidden;
}

.visit-tag {
  font-size: 11px;
  padding: 1px 5px;
  border-radius: 3px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 3px;
  overflow: hidden;
  line-height: 1.5;
}

.visit-tag .visit-time {
  flex-shrink: 0;
  font-weight: 600;
}

.visit-tag .visit-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.visit-more {
  font-size: 11px;
  color: #409eff;
  cursor: pointer;
  text-align: center;
  padding: 1px 0;
  flex-shrink: 0;
  margin-top: 1px;
}

.visit-more:hover {
  text-decoration: underline;
}

.visit-tag.planned {
  background: #fff7e6;
  color: #fa8c16;
}

.visit-tag.completed {
  background: #f6ffed;
  color: #52c41a;
}

.visit-tag.cancelled {
  background: #f5f5f5;
  color: #999;
}

/* 当天拜访列表弹窗 */
.day-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 60vh;
  overflow-y: auto;
}

.day-list-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
  border-left: 3px solid transparent;
}

.day-list-item:hover {
  background: #f5f7fa;
}

.day-list-item.planned { border-left-color: #fa8c16; }
.day-list-item.completed { border-left-color: #52c41a; }
.day-list-item.cancelled { border-left-color: #c0c4cc; }

.day-list-time {
  font-size: 13px;
  font-weight: 600;
  color: #409eff;
  flex-shrink: 0;
  width: 56px;
}

.day-list-content {
  flex: 1;
  min-width: 0;
}

.day-list-title {
  font-size: 14px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.day-list-sub {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}

.list-view {
  background: white;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.table-container {
  width: 100%;
}

.table-wrapper {
  overflow-x: auto;
}

.pagination-wrapper {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

:deep(.el-descriptions__label) {
  width: 100px;
  font-weight: 500;
  color: #666;
}

.personnel-view {
  background: white;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.personnel-schedule {
  padding: 16px 0;
}

.sub-info {
  font-size: 12px;
  color: #999;
  margin-top: 2px;
}

.stat-card .stat-icon.other {
  background: linear-gradient(135deg, #43cea2 0%, #185a9d 100%);
}

.visit-tag.other-work {
  background: #e6f7ff;
  color: #1890ff;
}

/* AI 复盘对话框 */
.review-content { padding: 0 8px; }
.review-title { font-size: 18px; font-weight: 600; color: #1e293b; margin-bottom: 12px; }
.review-summary {
  background: linear-gradient(135deg, #f0f4ff 0%, #ede9fe 100%);
  padding: 12px 16px; border-radius: 8px; font-size: 14px; color: #334155;
  line-height: 1.6; margin-bottom: 16px; border-left: 3px solid #667eea;
}
.review-section { margin-bottom: 16px; }
.review-section-title { font-size: 14px; font-weight: 600; color: #475569; margin-bottom: 8px; }
.review-section ul { margin: 0; padding-left: 20px; }
.review-section li { font-size: 13px; color: #475569; line-height: 1.7; margin-bottom: 4px; }
.review-deal { font-size: 13px; color: #475569; padding: 8px 12px; background: #f8fafc; border-radius: 6px; }
.review-tip { font-size: 12px; color: #94a3b8; margin-top: 16px; padding: 10px 12px; background: #fffbeb; border-radius: 6px; }
.review-saved { font-size: 13px; color: #059669; margin-top: 12px; padding: 10px 12px; background: #d1fae5; border-radius: 6px; }
.review-saved a { color: #059669; font-weight: 600; }
</style>
