<template>
  <div class="leads-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>🎯 AI商机识别</span>
          <el-button v-if="isManager" type="primary" :loading="analyzing" @click="analyzeBatch" style="margin-left:auto">
            批量AI分析
          </el-button>
          <el-button type="warning" :loading="dedupDetecting" @click="openDuplicates">
            🔍 重复检测{{ dupPendingCount ? `(${dupPendingCount})` : '' }}
          </el-button>
          <el-button type="info" @click="openProjects">
            📋 项目视图{{ projectCount ? `(${projectCount})` : '' }}
          </el-button>
          <el-button v-if="isManager" type="primary" plain @click="autoAssociateProjects"
                     :loading="autoAssociating">
            自动关联
          </el-button>
          <el-button type="success" :loading="converting" @click="convertBatch">
            批量转入CRM
          </el-button>
          <el-button v-if="isManager" type="danger" :loading="deleting" :disabled="!selection.length" @click="batchDelete">
            批量删除{{ selection.length ? `(${selection.length})` : '' }}
          </el-button>
        </div>
      </template>

      <div class="filter-bar">
        <el-input v-model="search" placeholder="搜索标题/客户/摘要" clearable style="width:260px"
                  @keyup.enter="loadData" @clear="loadData" />
        <el-select v-model="filterRelevant" placeholder="相关性" clearable style="width:110px" @change="loadData">
          <el-option label="相关" :value="1" />
          <el-option label="不相关" :value="0" />
        </el-select>
        <el-select v-model="filterScore" placeholder="最低分" clearable style="width:100px" @change="loadData">
          <el-option label="≥80" :value="80" />
          <el-option label="≥60" :value="60" />
          <el-option label="≥40" :value="40" />
          <el-option label="≥20" :value="20" />
        </el-select>
        <el-select v-model="filterGrade" placeholder="等级" clearable style="width:90px" @change="loadData">
          <el-option label="S 级" value="S" />
          <el-option label="A 级" value="A" />
          <el-option label="B 级" value="B" />
          <el-option label="C 级" value="C" />
        </el-select>
        <el-select v-model="filterLifecycle" placeholder="生命周期" clearable style="width:120px" @change="loadData">
          <el-option v-for="s in INTEL_STAGES" :key="s.key" :label="s.label" :value="s.key" />
        </el-select>
        <el-select v-model="filterDedup" placeholder="去重状态" clearable style="width:110px" @change="loadData">
          <el-option label="正常" value="clean" />
          <el-option label="疑似重复" value="suspect" />
          <el-option label="已合并" value="merged" />
        </el-select>
        <el-radio-group v-model="sortBy" @change="loadData" style="margin-left:8px">
          <el-radio-button label="score">按评分</el-radio-button>
          <el-radio-button label="created_at">按时间</el-radio-button>
        </el-radio-group>
        <el-button @click="loadData">搜索</el-button>
      </div>

      <el-table :data="list" v-loading="loading" border style="margin-top:12px" @selection-change="onSelectionChange">
        <el-table-column v-if="isManager" type="selection" width="45" />
        <el-table-column label="评分" width="90" align="center">
          <template #default="{row}">
            <div class="score-cell">
              <span :class="['grade-badge', gradeClass(row.score_grade, row.score)]">{{ row.score_grade || gradeOf(row.score) }}</span>
              <span :class="['score-num', scoreClass(row.score)]">{{ row.score }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="生命周期" width="120" align="center">
          <template #default="{row}">
            <el-tag v-if="row.lifecycle_stage" :type="lifecycleTagType(row.lifecycle_stage)" size="small" effect="dark">
              {{ lifecycleLabel(row.lifecycle_stage) }}
            </el-tag>
            <span v-else style="color:#909399;font-size:12px">情报</span>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="280" show-overflow-tooltip />
        <el-table-column prop="buyer" label="采购单位" width="160" show-overflow-tooltip />
        <el-table-column prop="budget" label="预算" width="100" />
        <el-table-column prop="deadline" label="截止日期" width="100" />
        <el-table-column prop="procurement_method" label="采购方式" width="110" />
        <el-table-column label="竞争对手" width="120">
          <template #default="{row}">
            <span v-if="parseCompetitors(row.competitors).length">
              {{ parseCompetitors(row.competitors).slice(0,2).join(', ') }}
              <span v-if="parseCompetitors(row.competitors).length > 2">等{{ parseCompetitors(row.competitors).length }}家</span>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110" align="center">
          <template #default="{row}">
            <el-tag v-if="row.status === 'converted'" type="success" size="small">已入CRM</el-tag>
            <el-tag v-else-if="row.status === 'rejected'" type="danger" size="small">已作废</el-tag>
            <el-tag v-else-if="row.status === 'merged'" type="info" size="small">已合并</el-tag>
            <el-tag v-else :type="row.is_relevant ? 'primary' : 'info'" size="small">
              {{ row.is_relevant ? '相关' : '不相关' }}
            </el-tag>
            <el-badge v-if="row.dedup_status === 'suspect'" is-dot type="warning" style="margin-left:6px">
              <el-icon style="color:#e6a23c;font-size:14px"><Warning /></el-icon>
            </el-badge>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="340">
          <template #default="{row}">
            <el-button size="small" @click="viewDetail(row.id)">详情</el-button>
            <el-button v-if="isManager" size="small" type="warning" plain
                       :loading="dedupId===row.id" @click="detectDup(row)">去重</el-button>
            <el-button v-if="isManager" size="small" type="primary" plain
                       :loading="scoringId===row.id" @click="rescoreOne(row)">评分</el-button>
            <el-button v-if="row.status !== 'converted' && row.status !== 'rejected' && row.status !== 'merged'" size="small" type="success"
                       :loading="convertingId===row.id" @click="convertOne(row.id)">转入CRM</el-button>
            <el-button v-if="isManager && row.status !== 'converted' && row.status !== 'rejected' && row.status !== 'merged'" size="small" type="danger"
                       @click="openReject(row)">作废</el-button>
            <el-button v-if="isManager" size="small" type="danger" text
                       :loading="deletingId===row.id" @click="deleteOne(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination v-model:current-page="page" :page-size="perPage" :total="total"
                     layout="total, prev, pager, next" @current-change="loadData"
                     style="margin-top:12px;justify-content:center" />
    </el-card>

    <el-dialog v-model="showDetail" title="商机详情" width="850px" top="5vh">
      <el-descriptions :column="2" border v-if="detail">
        <el-descriptions-item label="标题" :span="2">{{ detail.title }}</el-descriptions-item>
        <el-descriptions-item label="评分">
          <span :class="['grade-badge', gradeClass(detail.score_grade, detail.score)]">{{ detail.score_grade || gradeOf(detail.score) }}</span>
          <span :class="['score-num', scoreClass(detail.score)]" style="margin-left:6px">{{ detail.score }}</span>
          <el-tag size="small" style="margin-left:8px" :type="detail.score_method === 'hybrid' ? 'success' : 'info'">
            {{ detail.score_method === 'hybrid' ? '混合评分' : '规则评分' }}
          </el-tag>
          <div style="margin-top:4px;color:#909399;font-size:12px">{{ detail.score_reason }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="相关性">
          <el-tag :type="detail.is_relevant ? 'success' : 'info'">
            {{ detail.is_relevant ? '相关商机' : '不相关' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="7 维度评分" :span="2">
          <div class="dim-grid">
            <div v-for="d in dimensionList(detail.score_dimensions)" :key="d.key" class="dim-row">
              <div class="dim-label">
                <span class="dim-name">{{ d.label }}</span>
                <span class="dim-weight">权重 {{ d.weight }}</span>
              </div>
              <div class="dim-bar">
                <div class="dim-fill" :class="scoreClass(d.value)" :style="{ width: d.value + '%' }"></div>
              </div>
              <div class="dim-value">{{ d.value }}</div>
            </div>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="生命周期" :span="2">
          <div class="lifecycle-box">
            <div class="lifecycle-header">
              <span class="lc-current">
                <el-tag :type="lifecycleTagType(detail.lifecycle_stage || 'intelligence')" effect="dark">
                  {{ lifecycleLabel(detail.lifecycle_stage || 'intelligence') }}
                </el-tag>
                <span class="lc-crm">→ CRM：{{ lifecycleCrmLabel(detail.lifecycle_stage || 'intelligence') }}</span>
              </span>
              <el-button size="small" type="primary" plain @click="openLifecycle(detail)"
                         style="margin-left:auto">流转阶段</el-button>
            </div>
            <el-steps :active="lifecycleOrder(detail.lifecycle_stage)" align-center finish-status="success"
                      :process-status="isTerminal(detail.lifecycle_stage) ? 'error' : 'process'"
                      style="margin-top:12px">
              <el-step v-for="s in INTEL_STAGES" :key="s.key" :title="s.label"
                       :description="s.crm_label" :status="lifecycleStepStatus(s.key, detail.lifecycle_stage)" />
            </el-steps>
            <div v-if="lifecycleLogs.length" class="lc-logs">
              <div class="lc-logs-title">流转记录</div>
              <el-timeline>
                <el-timeline-item v-for="log in lifecycleLogs" :key="log.id"
                                  :timestamp="log.created_at" placement="top"
                                  :type="log.to_stage === 'lost_bid' ? 'danger' : (log.to_stage === 'deal_closed' ? 'success' : 'primary')">
                  <span style="font-weight:bold">{{ lifecycleLabel(log.from_stage) }} → {{ lifecycleLabel(log.to_stage) }}</span>
                  <div style="color:#606266;font-size:12px">{{ log.reason }}</div>
                  <div style="color:#909399;font-size:11px">操作人：{{ log.operator || '-' }} | CRM：{{ log.crm_stage || '-' }}</div>
                </el-timeline-item>
              </el-timeline>
            </div>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="采购单位">{{ detail.buyer || '-' }}</el-descriptions-item>
        <el-descriptions-item label="预算金额">{{ detail.budget || '-' }}</el-descriptions-item>
        <el-descriptions-item label="截止日期">{{ detail.deadline || '-' }}</el-descriptions-item>
        <el-descriptions-item label="项目类型">{{ detail.project_type || '-' }}</el-descriptions-item>
        <el-descriptions-item label="采购方式">{{ detail.procurement_method || '-' }}</el-descriptions-item>
        <el-descriptions-item label="地区">{{ detail.region || '-' }}</el-descriptions-item>
        <el-descriptions-item label="联系人">{{ detail.contact_person || '-' }}</el-descriptions-item>
        <el-descriptions-item label="联系电话">{{ detail.contact_phone || '-' }}</el-descriptions-item>
        <el-descriptions-item label="来源">{{ detail.source_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="URL" :span="2">
          <a :href="detail.url" target="_blank" style="color:#409eff">{{ detail.url }}</a>
        </el-descriptions-item>
        <el-descriptions-item label="命中关键词" :span="2">
          <el-tag v-for="kw in parseList(detail.keywords_matched)" :key="kw" size="small" style="margin:2px">{{ kw }}</el-tag>
          <span v-if="!parseList(detail.keywords_matched).length">-</span>
        </el-descriptions-item>
        <el-descriptions-item label="竞争对手" :span="2">
          <el-tag v-for="c in parseCompetitors(detail.competitors)" :key="c" type="warning" size="small" style="margin:2px">{{ c }}</el-tag>
          <span v-if="!parseCompetitors(detail.competitors).length">-</span>
        </el-descriptions-item>
        <el-descriptions-item label="AI分析" :span="2">{{ detail.analysis_summary || '-' }}</el-descriptions-item>
        <el-descriptions-item label="原文正文" :span="2">
          <div class="content-box">{{ detail.raw_content || detail.snippet || '-' }}</div>
        </el-descriptions-item>
        <el-descriptions-item v-if="detail.status === 'rejected'" label="作废原因" :span="2">
          <span style="color:#f56c6c">{{ detail.reject_reason || '-' }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>

    <!-- 作废对话框 -->
    <el-dialog v-model="showReject" title="商机作废" width="500px">
      <div style="line-height:2">
        <p style="color:#606266">确定要作废以下商机吗？</p>
        <p style="font-weight:bold;background:#f5f7fa;padding:8px;border-radius:4px">{{ rejectRow?.title }}</p>
        <p style="color:#f56c6c;margin-top:12px">* 请填写作废原因（必填）：</p>
        <el-input v-model="rejectReason" type="textarea" :rows="3"
                  placeholder="例如：重复商机/信息有误/已过期/非目标客户等" />
      </div>
      <template #footer>
        <el-button @click="showReject = false">取消</el-button>
        <el-button type="danger" :loading="rejecting" @click="confirmReject">确认作废</el-button>
      </template>
    </el-dialog>

    <!-- 生命周期流转对话框 -->
    <el-dialog v-model="showLifecycle" title="生命周期流转" width="560px">
      <div v-if="lifecycleRow" style="line-height:1.8">
        <p style="color:#606266">商机：{{ lifecycleRow.title?.slice(0, 50) }}</p>
        <p>当前阶段：
          <el-tag :type="lifecycleTagType(lifecycleRow.lifecycle_stage || 'intelligence')" effect="dark">
            {{ lifecycleLabel(lifecycleRow.lifecycle_stage || 'intelligence') }}
          </el-tag>
          <span style="margin-left:8px;color:#909399;font-size:12px">
            → CRM：{{ lifecycleCrmLabel(lifecycleRow.lifecycle_stage || 'intelligence') }}
          </span>
        </p>
        <p style="color:#409eff;margin-top:12px">* 流转至新阶段：</p>
        <el-select v-model="lifecycleToStage" placeholder="选择目标阶段" style="width:100%">
          <el-option v-for="s in INTEL_STAGES.filter(x => x.key !== (lifecycleRow.lifecycle_stage || 'intelligence'))"
                     :key="s.key" :label="s.label + '（→ CRM：' + s.crm_label + '）'" :value="s.key">
            <span>{{ s.label }}</span>
            <span style="float:right;color:#909399;font-size:12px">{{ s.terminal ? '终态' : '' }}</span>
          </el-option>
        </el-select>
        <p style="color:#606266;margin-top:12px">流转说明（可选）：</p>
        <el-input v-model="lifecycleReason" type="textarea" :rows="2"
                  placeholder="例如：已开标/中标公示/客户确认成交等" />
        <el-alert v-if="lifecycleToStage && isTerminal(lifecycleToStage)" type="warning" :closable="false"
                  style="margin-top:8px">
          「{{ lifecycleLabel(lifecycleToStage) }}」为终态阶段，流转后不可再变更。
        </el-alert>
      </div>
      <template #footer>
        <el-button @click="showLifecycle = false">取消</el-button>
        <el-button type="primary" :loading="lifecycleLoading" @click="confirmLifecycle">确认流转</el-button>
      </template>
    </el-dialog>

    <!-- 疑似重复候选审查 -->
    <el-dialog v-model="showDuplicates" title="🔍 疑似重复候选审查" width="950px" top="5vh">
      <div style="margin-bottom:12px">
        <el-radio-group v-model="dupStatusFilter" @change="loadDuplicates(1)">
          <el-radio-button label="pending">待处理{{ dupPendingCount ? `(${dupPendingCount})` : '' }}</el-radio-button>
          <el-radio-button label="ai_same">AI判同一</el-radio-button>
          <el-radio-button label="ai_diff">AI判不同</el-radio-button>
          <el-radio-button label="merged">已合并</el-radio-button>
          <el-radio-button label="kept">保留独立</el-radio-button>
        </el-radio-group>
      </div>
      <el-table :data="dupList" v-loading="dupLoading" border size="small" style="max-height:520px">
        <el-table-column label="匹配级别" width="130">
          <template #default="{row}">
            <el-tag :type="dupLevelType(row.match_level)" size="small" effect="dark">
              L{{ row.match_level }} {{ row.match_level_name }}
            </el-tag>
            <div style="font-size:11px;color:#909399;margin-top:2px">相似度 {{ (row.similarity * 100).toFixed(0) }}%</div>
          </template>
        </el-table-column>
        <el-table-column label="商机A" min-width="200">
          <template #default="{row}">
            <div style="font-weight:bold">{{ row.a_title?.slice(0, 40) || `#${row.lead_a_id}` }}</div>
            <div style="font-size:12px;color:#606266">{{ row.a_buyer || '-' }} | 评分{{ row.a_score || '-' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="商机B" min-width="200">
          <template #default="{row}">
            <div style="font-weight:bold">{{ row.b_title?.slice(0, 40) || `#${row.lead_b_id}` }}</div>
            <div style="font-size:12px;color:#606266">{{ row.b_buyer || '-' }} | 评分{{ row.b_score || '-' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="匹配理由" min-width="180" show-overflow-tooltip>
          <template #default="{row}">
            <div style="font-size:12px">{{ row.match_reason }}</div>
            <div v-if="row.ai_reason" style="font-size:11px;color:#409eff;margin-top:2px">
              AI：{{ row.ai_is_same ? '同一' : '不同' }}({{ (row.ai_confidence * 100).toFixed(0) }}%) {{ row.ai_reason }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" align="center">
          <template #default="{row}">
            <template v-if="row.status === 'pending'">
              <el-button size="small" type="primary" plain :loading="dupActionId===row.id"
                         @click="aiJudgeDup(row)">AI判断</el-button>
              <el-button size="small" type="success" plain :loading="dupActionId===row.id"
                         @click="mergeDup(row, 'a')">合并A</el-button>
              <el-button size="small" type="info" plain :loading="dupActionId===row.id"
                         @click="keepDup(row)">保留</el-button>
            </template>
            <template v-else>
              <el-tag :type="dupStatusType(row.status)" size="small">{{ dupStatusLabel(row.status) }}</el-tag>
              <el-button v-if="row.status === 'ai_same'" size="small" type="success" plain style="margin-left:4px"
                         :loading="dupActionId===row.id" @click="mergeDup(row, 'a')">合并</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination v-model:current-page="dupPage" :page-size="10" :total="dupTotal"
                     layout="total, prev, pager, next" @current-change="loadDuplicates"
                     style="margin-top:12px;justify-content:center" />
      <div style="margin-top:8px;color:#909399;font-size:12px">
        提示：4级去重（URL Hash → 标题相似度 → 客户+项目+地区 → Embedding语义），疑似重复不自动删除，经AI判断或人工确认后合并/保留。
      </div>
    </el-dialog>

    <!-- 项目视图 -->
    <el-dialog v-model="showProjects" title="📋 项目视图（多公告关联）" width="950px" top="5vh">
      <div class="filter-bar" style="margin-bottom:12px">
        <el-input v-model="projectSearch" placeholder="搜索项目名/买家/地区" clearable style="width:240px"
                  @keyup.enter="loadProjects(1)" @clear="loadProjects(1)" />
        <el-select v-model="projectStageFilter" placeholder="生命周期" clearable style="width:120px" @change="loadProjects(1)">
          <el-option v-for="s in INTEL_STAGES" :key="s.key" :label="s.label" :value="s.key" />
        </el-select>
        <el-button @click="loadProjects(1)">搜索</el-button>
      </div>
      <el-table :data="projectList" v-loading="projectLoading" border size="small" style="max-height:480px"
                @row-click="viewProject">
        <el-table-column label="项目名称" min-width="240" show-overflow-tooltip>
          <template #default="{row}">
            <span style="font-weight:bold;color:#303133">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="buyer" label="采购单位" width="150" show-overflow-tooltip />
        <el-table-column label="阶段" width="100" align="center">
          <template #default="{row}">
            <el-tag :type="lifecycleTagType(row.lifecycle_stage)" size="small" effect="dark">
              {{ lifecycleLabel(row.lifecycle_stage) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="评分" width="80" align="center">
          <template #default="{row}">
            <span :class="['score-num', scoreClass(row.score)]">{{ row.score }}</span>
            <span v-if="row.score_grade" style="font-size:11px;color:#909399">({{ row.score_grade }})</span>
          </template>
        </el-table-column>
        <el-table-column prop="announcement_count" label="公告数" width="70" align="center" />
        <el-table-column prop="budget" label="预算" width="90" />
        <el-table-column prop="region" label="地区" width="80" />
      </el-table>
      <el-pagination v-model:current-page="projectPage" :page-size="15" :total="projectTotal"
                     layout="total, prev, pager, next" @current-change="loadProjects"
                     style="margin-top:12px;justify-content:center" />
    </el-dialog>

    <!-- 项目详情 -->
    <el-dialog v-model="showProjectDetail" title="项目详情" width="900px" top="5vh">
      <div v-if="projectDetail">
        <el-descriptions :column="3" border>
          <el-descriptions-item label="项目名称" :span="3">
            <span style="font-weight:bold;font-size:15px">{{ projectDetail.project.name }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="采购单位">{{ projectDetail.project.buyer || '-' }}</el-descriptions-item>
          <el-descriptions-item label="地区">{{ projectDetail.project.region || '-' }}</el-descriptions-item>
          <el-descriptions-item label="预算">{{ projectDetail.project.budget || '-' }}</el-descriptions-item>
          <el-descriptions-item label="当前阶段">
            <el-tag :type="lifecycleTagType(projectDetail.project.lifecycle_stage)" effect="dark">
              {{ lifecycleLabel(projectDetail.project.lifecycle_stage) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="评分">
            <span :class="['score-num', scoreClass(projectDetail.project.score)]">{{ projectDetail.project.score }}</span>
            ({{ projectDetail.project.score_grade || '-' }})
          </el-descriptions-item>
          <el-descriptions-item label="公告数">{{ projectDetail.announcement_count }} 条</el-descriptions-item>
        </el-descriptions>

        <!-- 生命周期进度 -->
        <div style="margin-top:16px">
          <div style="font-weight:bold;margin-bottom:8px;border-left:3px solid #409eff;padding-left:8px">
            项目生命周期进度
          </div>
          <el-steps :active="lifecycleOrder(projectDetail.project.lifecycle_stage)" align-center
                    finish-status="success"
                    :process-status="isTerminal(projectDetail.project.lifecycle_stage) ? 'error' : 'process'">
            <el-step v-for="s in INTEL_STAGES" :key="s.key" :title="s.label"
                     :description="s.crm_label"
                     :status="lifecycleStepStatus(s.key, projectDetail.project.lifecycle_stage)" />
          </el-steps>
        </div>

        <!-- 关联公告列表 -->
        <div style="margin-top:16px">
          <div style="font-weight:bold;margin-bottom:8px;border-left:3px solid #67c23a;padding-left:8px">
            关联公告（{{ projectDetail.announcement_count }} 条）
          </div>
          <el-table :data="projectDetail.announcements" border size="small">
            <el-table-column label="阶段" width="100">
              <template #default="{row}">
                <el-tag :type="lifecycleTagType(row.lifecycle_stage)" size="small">
                  {{ lifecycleLabel(row.lifecycle_stage) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="title" label="标题" min-width="250" show-overflow-tooltip />
            <el-table-column label="评分" width="70" align="center">
              <template #default="{row}">
                <span :class="['score-num', scoreClass(row.score)]">{{ row.score }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="budget" label="预算" width="80" />
            <el-table-column prop="deadline" label="截止" width="90" />
            <el-table-column label="状态" width="90" align="center">
              <template #default="{row}">
                <el-tag v-if="row.status === 'converted'" type="success" size="small">已入CRM</el-tag>
                <el-tag v-else-if="row.status === 'rejected'" type="danger" size="small">已作废</el-tag>
                <el-tag v-else-if="row.status === 'merged'" type="info" size="small">已合并</el-tag>
                <el-tag v-else type="primary" size="small">活跃</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80" align="center">
              <template #default="{row}">
                <el-button size="small" text type="primary" @click.stop="viewDetail(row.id)">详情</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Warning } from '@element-plus/icons-vue'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const authStore = useAuthStore()
// 权限点驱动：data.view_all 拥有全部权限；应用中心成员仅可查看+导入CRM（intel.import）
const isManager = computed(() => authStore.has('data.view_all'))

const loading = ref(false)
const analyzing = ref(false)
const converting = ref(false)
const convertingId = ref(null)
const restoringId = ref(null)
const showReject = ref(false)
const rejectRow = ref(null)
const rejectReason = ref('')
const rejecting = ref(false)
const list = ref([])
const total = ref(0)
const page = ref(1)
const perPage = ref(20)
const search = ref('')
const filterRelevant = ref(1)  // 默认只显示可跟进商机（中标/成交公告自动标记为不相关）
const filterScore = ref(null)
const filterGrade = ref('')
const filterLifecycle = ref('')
const filterDedup = ref('')
const sortBy = ref('score')
const showDetail = ref(false)
const detail = ref(null)
const scoringId = ref(null)

// 生命周期流转状态
const showLifecycle = ref(false)
const lifecycleRow = ref(null)
const lifecycleToStage = ref('')
const lifecycleReason = ref('')
const lifecycleLoading = ref(false)
const lifecycleLogs = ref([])

// 去重检测状态
const dedupId = ref(null)
const dedupDetecting = ref(false)
const dupPendingCount = ref(0)
const showDuplicates = ref(false)
const dupList = ref([])
const dupTotal = ref(0)
const dupPage = ref(1)
const dupStatusFilter = ref('pending')
const dupLoading = ref(false)
const dupActionId = ref(null)

// 项目视图状态
const showProjects = ref(false)
const projectList = ref([])
const projectTotal = ref(0)
const projectPage = ref(1)
const projectSearch = ref('')
const projectStageFilter = ref('')
const projectLoading = ref(false)
const projectCount = ref(0)
const showProjectDetail = ref(false)
const projectDetail = ref(null)
const autoAssociating = ref(false)

// 7 维度定义（与后端 scoring_model.DIMENSION_WEIGHTS / DIMENSION_LABELS 一致）
const DIMENSIONS = [
  { key: 'business_match', label: '业务匹配度', weight: '30%' },
  { key: 'customer_value', label: '客户价值', weight: '20%' },
  { key: 'budget_amount', label: '预算金额', weight: '15%' },
  { key: 'project_stage', label: '项目阶段', weight: '15%' },
  { key: 'time_urgency', label: '时间紧迫度', weight: '10%' },
  { key: 'region_match', label: '区域匹配度', weight: '5%' },
  { key: 'competition', label: '竞争情况', weight: '5%' }
]

// 情报生命周期 10 阶段（与后端 lifecycle_model.INTEL_STAGES 一致）
// 情报→采购意向→项目预告→招标公告→答疑公告→开标→中标公告→合同公告→落标/成交
const INTEL_STAGES = [
  { key: 'intelligence', label: '情报', crm_label: '线索采集', terminal: false, order: 0 },
  { key: 'procurement_intent', label: '采购意向', crm_label: '线索培育', terminal: false, order: 1 },
  { key: 'project_preview', label: '项目预告', crm_label: '线索跟进', terminal: false, order: 2 },
  { key: 'bidding_announcement', label: '招标公告', crm_label: '商机创建', terminal: false, order: 3 },
  { key: 'qa_announcement', label: '答疑公告', crm_label: '商机推进', terminal: false, order: 4 },
  { key: 'bid_opening', label: '开标', crm_label: '商机推进', terminal: false, order: 5 },
  { key: 'won_bid', label: '中标公告', crm_label: '合同签订', terminal: false, order: 6 },
  { key: 'contract_announcement', label: '合同公告', crm_label: '合同签订', terminal: false, order: 7 },
  { key: 'lost_bid', label: '落标', crm_label: '商机关闭', terminal: true, order: 8 },
  { key: 'deal_closed', label: '成交', crm_label: '合同+回款', terminal: true, order: 9 },
]

// CRM 生命周期 5 阶段（我方销售视角）：线索→商机→报价→合同→回款
const CRM_STAGE_LABELS = {
  lead: '线索', opportunity: '商机', quote: '报价',
  contract: '合同', payment: '回款', closed: '商机关闭',
}

// 情报阶段 → CRM 阶段映射
const INTEL_TO_CRM = {
  intelligence: 'lead', procurement_intent: 'lead', project_preview: 'lead',
  bidding_announcement: 'opportunity', qa_announcement: 'opportunity', bid_opening: 'opportunity',
  won_bid: 'contract', contract_announcement: 'contract',
  lost_bid: 'closed', deal_closed: 'payment',
}

function lifecycleLabel(key) {
  const s = INTEL_STAGES.find(x => x.key === key)
  return s ? s.label : '情报'
}

function lifecycleCrmLabel(key) {
  const crmKey = INTEL_TO_CRM[key] || 'lead'
  return CRM_STAGE_LABELS[crmKey] || '线索'
}

function lifecycleOrder(key) {
  const s = INTEL_STAGES.find(x => x.key === key)
  return s ? s.order : 0
}

function isTerminal(key) {
  const s = INTEL_STAGES.find(x => x.key === key)
  return s ? s.terminal : false
}

function lifecycleTagType(key) {
  // 终态：落标=danger，成交=success；中间阶段按进度渐变
  if (key === 'lost_bid') return 'danger'
  if (key === 'deal_closed') return 'success'
  if (key === 'won_bid') return 'success'
  const order = lifecycleOrder(key)
  if (order >= 3) return 'warning'  // 招标公告/投标
  if (order >= 1) return 'primary'  // 采购意向/项目预告
  return 'info'  // 情报
}

function lifecycleStepStatus(stepKey, currentKey) {
  const cur = lifecycleOrder(currentKey)
  const step = lifecycleOrder(stepKey)
  if (isTerminal(currentKey)) {
    // 落标/成交为终态
    if (step < cur) return 'success'
    if (step === cur) return currentKey === 'lost_bid' ? 'error' : 'success'
    return 'wait'
  }
  if (step < cur) return 'success'
  if (step === cur) return 'process'
  return 'wait'
}

function scoreClass(s) {
  if (s >= 80) return 'score-high'
  if (s >= 60) return 'score-mid'
  if (s >= 40) return 'score-low'
  return 'score-vlow'
}

// 等级计算（与后端一致）：S>=90, A>=80, B>=60, C<60
function gradeOf(score) {
  if (score == null) return 'C'
  if (score >= 90) return 'S'
  if (score >= 80) return 'A'
  if (score >= 60) return 'B'
  return 'C'
}

// 等级徽章样式
function gradeClass(grade, score) {
  const g = grade || gradeOf(score)
  return 'grade-' + g.toLowerCase()
}

// 解析 7 维度评分为数组（含标签与权重）
function dimensionList(dimensions) {
  let parsed = {}
  if (dimensions) {
    if (typeof dimensions === 'object') parsed = dimensions
    else {
      try { parsed = JSON.parse(dimensions) || {} } catch { parsed = {} }
    }
  }
  return DIMENSIONS.map(d => ({ ...d, value: parsed[d.key] != null ? Number(parsed[d.key]) : 0 }))
}

function parseList(val) {
  if (!val) return []
  if (Array.isArray(val)) return val
  try { return JSON.parse(val) || [] } catch { return [] }
}

function parseCompetitors(val) {
  return parseList(val)
}

async function loadData() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: perPage.value, sort: sortBy.value }
    if (search.value) params.search = search.value
    if (filterRelevant.value !== null && filterRelevant.value !== '') params.is_relevant = filterRelevant.value
    if (filterScore.value) params.min_score = filterScore.value
    if (filterGrade.value) params.grade = filterGrade.value
    if (filterLifecycle.value) params.lifecycle_stage = filterLifecycle.value
    if (filterDedup.value) params.dedup_status = filterDedup.value
    const res = await api.get('/intelligence/leads', params)
    list.value = res.data || []
    total.value = res.total || 0
  } catch (e) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function analyzeBatch() {
  analyzing.value = true
  try {
    const res = await api.longPost('/intelligence/analyze-batch?limit=20')
    const d = res.data || {}
    ElMessage.success(`分析完成：共${d.analyzed||0}条，成功${d.success||0}条，失败${d.failed||0}条`)
    loadData()
  } catch (e) {
    ElMessage.error('分析失败：' + (e.response?.data?.message || e.message))
  } finally {
    analyzing.value = false
  }
}

async function convertOne(id) {
  convertingId.value = id
  try {
    const res = await api.post(`/intelligence/leads/${id}/convert`)
    const d = res.data || {}
    if (d.duplicate) {
      ElMessage.info('该商机已在CRM中存在，已自动关联')
    } else {
      ElMessage.success(`已转入CRM：${d.company || ''}`)
    }
    loadData()
  } catch (e) {
    ElMessage.error('转入失败：' + (e.response?.data?.message || e.message))
  } finally {
    convertingId.value = null
  }
}

function openReject(row) {
  rejectRow.value = row
  rejectReason.value = ''
  showReject.value = true
}

async function confirmReject() {
  if (!rejectReason.value.trim()) {
    ElMessage.warning('请填写作废原因')
    return
  }
  rejecting.value = true
  try {
    await api.post(`/intelligence/leads/${rejectRow.value.id}/reject`, { reason: rejectReason.value.trim() })
    ElMessage.success('商机已作废')
    showReject.value = false
    loadData()
  } catch (e) {
    ElMessage.error('作废失败：' + (e.response?.data?.message || e.message))
  } finally {
    rejecting.value = false
  }
}

async function restoreOne(id) {
  restoringId.value = id
  try {
    await api.post(`/intelligence/leads/${id}/restore`)
    ElMessage.success('商机已恢复')
    loadData()
  } catch (e) {
    ElMessage.error('恢复失败：' + (e.response?.data?.message || e.message))
  } finally {
    restoringId.value = null
  }
}

// ==================== 删除 ====================
const selection = ref([])
const deleting = ref(false)
const deletingId = ref(null)

function onSelectionChange(rows) {
  selection.value = rows
}

async function deleteOne(row) {
  try {
    await ElMessageBox.confirm(`确定删除商机「${row.title?.slice(0, 40) || row.id}」？删除后不可恢复`, '删除商机', { type: 'warning' })
  } catch { return }
  deletingId.value = row.id
  try {
    const res = await api.delete(`/intelligence/leads/${row.id}`)
    if (res && res.code === 200) {
      ElMessage.success(res.message || '已删除')
      selection.value = []
      loadData()
    } else {
      ElMessage.error((res && res.message) || '删除失败')
    }
  } catch (e) {
    ElMessage.error('删除失败：' + (e.response?.data?.message || e.message))
  } finally {
    deletingId.value = null
  }
}

async function batchDelete() {
  if (!selection.value.length) return
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selection.value.length} 条商机？删除后不可恢复`, '批量删除', { type: 'warning' })
  } catch { return }
  deleting.value = true
  try {
    const res = await api.post('/intelligence/leads/batch-delete', { ids: selection.value.map(r => r.id) })
    if (res && res.code === 200) {
      ElMessage.success(res.message || '删除成功')
      selection.value = []
      loadData()
    } else {
      ElMessage.error((res && res.message) || '删除失败')
    }
  } catch (e) {
    ElMessage.error('批量删除失败：' + (e.response?.data?.message || e.message))
  } finally {
    deleting.value = false
  }
}

async function convertBatch() {
  converting.value = true
  try {
    const res = await api.post('/intelligence/leads/convert-batch', {
      only_relevant: true,
      min_score: filterScore.value || 0,
    })
    const d = res.data || {}
    ElMessage.success(`批量转入完成：新增${d.converted||0}条，跳过${d.skipped||0}条`)
    loadData()
  } catch (e) {
    ElMessage.error('批量转入失败：' + (e.response?.data?.message || e.message))
  } finally {
    converting.value = false
  }
}

async function viewDetail(id) {
  try {
    const res = await api.get(`/intelligence/leads/${id}`)
    detail.value = res.data
    showDetail.value = true
    // 加载生命周期日志
    loadLifecycleLogs(id)
  } catch (e) {
    ElMessage.error('加载详情失败')
  }
}

async function loadLifecycleLogs(id) {
  try {
    const res = await api.get(`/intelligence/leads/${id}/lifecycle`)
    lifecycleLogs.value = res.data?.logs || []
  } catch {
    lifecycleLogs.value = []
  }
}

function openLifecycle(row) {
  lifecycleRow.value = row
  lifecycleToStage.value = ''
  lifecycleReason.value = ''
  showLifecycle.value = true
}

async function confirmLifecycle() {
  if (!lifecycleToStage.value) {
    ElMessage.warning('请选择目标阶段')
    return
  }
  lifecycleLoading.value = true
  try {
    const res = await api.post(`/intelligence/leads/${lifecycleRow.value.id}/lifecycle`, {
      to_stage: lifecycleToStage.value,
      reason: lifecycleReason.value.trim(),
    })
    const d = res.data || {}
    ElMessage.success(res.message || `已流转至[${lifecycleLabel(d.to_stage)}]阶段`)
    showLifecycle.value = false
    // 局部刷新该行
    const idx = list.value.findIndex(r => r.id === lifecycleRow.value.id)
    if (idx >= 0) list.value[idx].lifecycle_stage = d.to_stage
    // 同步详情
    if (detail.value && detail.value.id === lifecycleRow.value.id) {
      detail.value = { ...detail.value, lifecycle_stage: d.to_stage }
      loadLifecycleLogs(lifecycleRow.value.id)
    }
  } catch (e) {
    ElMessage.error('流转失败：' + (e.response?.data?.message || e.message))
  } finally {
    lifecycleLoading.value = false
  }
}

// 商机评分模型：7 维度加权 + 规则/LLM 混合重评分
async function rescoreOne(row) {
  scoringId.value = row.id
  try {
    const res = await api.longPost(`/intelligence/leads/${row.id}/score`)
    const sc = res.scoring || {}
    ElMessage.success(`评分完成：${sc.score} 分（${sc.grade} 级，${sc.method === 'hybrid' ? '混合' : '规则'}）`)
    // 局部刷新该行
    const idx = list.value.findIndex(r => r.id === row.id)
    if (idx >= 0 && res.data) list.value[idx] = { ...list.value[idx], ...res.data }
    // 如详情打开同步刷新
    if (detail.value && detail.value.id === row.id && res.data) {
      detail.value = { ...detail.value, ...res.data }
    }
  } catch (e) {
    ElMessage.error('评分失败：' + (e.response?.data?.message || e.message))
  } finally {
    scoringId.value = null
  }
}

// ==================== 多级去重 ====================
function dupLevelType(level) {
  if (level <= 1) return 'danger'      // URL完全相同
  if (level === 2) return 'warning'    // 标题相似
  if (level === 3) return 'primary'   // 组合匹配
  return 'success'                     // Embedding语义
}

function dupStatusType(status) {
  const map = { pending: 'warning', ai_same: 'primary', ai_diff: 'info', merged: 'success', kept: '' }
  return map[status] || 'info'
}

function dupStatusLabel(status) {
  const map = { pending: '待处理', ai_same: 'AI判同一', ai_diff: 'AI判不同', merged: '已合并', kept: '保留独立' }
  return map[status] || status
}

async function detectDup(row) {
  dedupId.value = row.id
  try {
    const res = await api.longPost(`/intelligence/leads/${row.id}/dedup`)
    const d = res.data || {}
    if (d.candidates?.length) {
      ElMessage.success(`检测完成：发现${d.candidates.length}个疑似重复`)
      // 局部刷新该行
      const idx = list.value.findIndex(r => r.id === row.id)
      if (idx >= 0) list.value[idx].dedup_status = 'suspect'
      dupPendingCount.value += d.new_count
    } else {
      ElMessage.success('未发现疑似重复')
    }
  } catch (e) {
    ElMessage.error('去重检测失败：' + (e.response?.data?.message || e.message))
  } finally {
    dedupId.value = null
  }
}

async function openDuplicates() {
  showDuplicates.value = true
  await loadDuplicates(1)
  await loadDupPendingCount()
}

async function loadDupPendingCount() {
  try {
    const res = await api.get('/intelligence/duplicates', { status: 'pending', page: 1, per_page: 1 })
    dupPendingCount.value = res.total || 0
  } catch { /* ignore */ }
}

async function loadDuplicates(page) {
  if (page) dupPage.value = page
  dupLoading.value = true
  try {
    const res = await api.get('/intelligence/duplicates', {
      status: dupStatusFilter.value,
      page: dupPage.value,
      per_page: 10,
    })
    dupList.value = res.data || []
    dupTotal.value = res.total || 0
  } catch (e) {
    ElMessage.error('加载重复候选失败')
  } finally {
    dupLoading.value = false
  }
}

async function aiJudgeDup(row) {
  dupActionId.value = row.id
  try {
    const res = await api.longPost(`/intelligence/duplicates/${row.id}/ai-judge`)
    const d = res.data || {}
    if (d.is_same) {
      ElMessage.success(`AI判断为同一项目（置信度${(d.confidence * 100).toFixed(0)}%）`)
    } else {
      ElMessage.info(`AI判断为不同项目（置信度${(d.confidence * 100).toFixed(0)}%）`)
    }
    await loadDuplicates()
    await loadDupPendingCount()
  } catch (e) {
    ElMessage.error('AI判断失败：' + (e.response?.data?.message || e.message))
  } finally {
    dupActionId.value = null
  }
}

async function mergeDup(row, keep) {
  const aTitle = row.a_title?.slice(0, 30) || `#${row.lead_a_id}`
  const bTitle = row.b_title?.slice(0, 30) || `#${row.lead_b_id}`
  try {
    await ElMessageBox.confirm(
      `确认保留商机${keep === 'a' ? 'A' : 'B'}（${keep === 'a' ? aTitle : bTitle}），合并另一条？合并后不可恢复。`,
      '合并确认', { type: 'warning' }
    )
  } catch { return }
  dupActionId.value = row.id
  try {
    const res = await api.post(`/intelligence/duplicates/${row.id}/merge`, { keep })
    ElMessage.success(res.message || '已合并')
    await loadDuplicates()
    await loadDupPendingCount()
    loadData()
  } catch (e) {
    ElMessage.error('合并失败：' + (e.response?.data?.message || e.message))
  } finally {
    dupActionId.value = null
  }
}

async function keepDup(row) {
  dupActionId.value = row.id
  try {
    const res = await api.post(`/intelligence/duplicates/${row.id}/keep`)
    ElMessage.success(res.message || '已确认保留独立')
    await loadDuplicates()
    await loadDupPendingCount()
  } catch (e) {
    ElMessage.error('操作失败：' + (e.response?.data?.message || e.message))
  } finally {
    dupActionId.value = null
  }
}

// ==================== 项目关联 ====================
async function openProjects() {
  showProjects.value = true
  await loadProjects(1)
}

async function loadProjects(page) {
  if (page) projectPage.value = page
  projectLoading.value = true
  try {
    const params = { page: projectPage.value, per_page: 15, status: 'active' }
    if (projectSearch.value) params.search = projectSearch.value
    if (projectStageFilter.value) params.lifecycle_stage = projectStageFilter.value
    const res = await api.get('/intelligence/projects', params)
    projectList.value = res.data || []
    projectTotal.value = res.total || 0
    projectCount.value = res.total || 0
  } catch (e) {
    ElMessage.error('加载项目列表失败')
  } finally {
    projectLoading.value = false
  }
}

async function viewProject(row) {
  if (!row?.id) return
  try {
    const res = await api.get(`/intelligence/projects/${row.id}`)
    projectDetail.value = res.data
    showProjectDetail.value = true
  } catch (e) {
    ElMessage.error('加载项目详情失败')
  }
}

async function autoAssociateProjects() {
  autoAssociating.value = true
  try {
    const res = await api.longPost('/intelligence/projects/auto-associate')
    ElMessage.success(res.message || '自动关联完成')
    await loadProjects()
  } catch (e) {
    ElMessage.error('自动关联失败：' + (e.response?.data?.message || e.message))
  } finally {
    autoAssociating.value = false
  }
}

onMounted(() => {
  // 支持从原始情报页跳转过来时预填搜索
  const q = String(route.query.search || '').trim()
  if (q) search.value = q
  loadData()
  loadDupPendingCount()
  // 加载项目计数
  api.get('/intelligence/projects', { page: 1, per_page: 1 }).then(res => {
    projectCount.value = res.total || 0
  }).catch(() => {})
})
</script>

<style scoped>
.leads-page { padding: 16px; }
.card-header { display: flex; align-items: center; }
.filter-bar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.content-box { white-space: pre-wrap; max-height: 300px; overflow-y: auto; background: #f5f7fa; padding: 12px; border-radius: 4px; }

/* 评分单元格：等级徽章 + 分数 */
.score-cell { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.grade-badge { display: inline-block; min-width: 22px; padding: 0 6px; height: 18px; line-height: 18px; border-radius: 9px; font-size: 11px; font-weight: bold; color: #fff; text-align: center; }
.grade-s { background: #c0392b; }   /* S 级：深红，最高 */
.grade-a { background: #e67e22; }   /* A 级：橙 */
.grade-b { background: #2980b9; }   /* B 级：蓝 */
.grade-c { background: #95a5a6; }   /* C 级：灰 */
.score-num { font-weight: bold; font-size: 14px; }
.score-num.score-high { color: #c0392b; }
.score-num.score-mid { color: #e67e22; }
.score-num.score-low { color: #409eff; }
.score-num.score-vlow { color: #909399; }

/* 兼容旧版圆形徽章（详情页等处） */
.score-badge { display: inline-block; width: 32px; height: 32px; line-height: 32px; border-radius: 50%; text-align: center; font-weight: bold; color: #fff; }
.score-badge.score-high { background: #c0392b; }
.score-badge.score-mid { background: #e67e22; }
.score-badge.score-low { background: #409eff; }
.score-badge.score-vlow { background: #909399; }

/* 7 维度评分明细条 */
.dim-grid { display: flex; flex-direction: column; gap: 6px; width: 100%; }
.dim-row { display: flex; align-items: center; gap: 8px; }
.dim-label { width: 130px; display: flex; flex-direction: column; flex-shrink: 0; }
.dim-name { font-size: 13px; color: #303133; }
.dim-weight { font-size: 11px; color: #909399; }
.dim-bar { flex: 1; height: 14px; background: #f0f2f5; border-radius: 7px; overflow: hidden; }
.dim-fill { height: 100%; border-radius: 7px; transition: width .3s ease; }
.dim-fill.score-high { background: linear-gradient(90deg, #e74c3c, #c0392b); }
.dim-fill.score-mid { background: linear-gradient(90deg, #f39c12, #e67e22); }
.dim-fill.score-low { background: linear-gradient(90deg, #5dade2, #2e86c1); }
.dim-fill.score-vlow { background: linear-gradient(90deg, #bdc3c7, #95a5a6); }
.dim-value { width: 30px; text-align: right; font-weight: bold; font-size: 13px; color: #303133; }

/* 生命周期时间线 */
.lifecycle-box { width: 100%; }
.lifecycle-header { display: flex; align-items: center; gap: 8px; }
.lc-current { display: flex; align-items: center; gap: 8px; }
.lc-crm { color: #606266; font-size: 13px; }
.lc-logs { margin-top: 16px; }
.lc-logs-title { font-weight: bold; color: #303133; margin-bottom: 8px; border-left: 3px solid #409eff; padding-left: 8px; }
</style>
