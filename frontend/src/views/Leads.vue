<template>
  <div class="leads-container">
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">📡 智能线索管理</h2>
        <p class="page-desc">线索统一链路：采集/人工导入 → 原始情报库 → AI商机识别 → 转入CRM → 分配销售。人工导入的数据在"原始情报"标签页中查看</p>
      </div>
      <div class="header-right">
        <el-button @click="fetchData" :loading="loading"><span>🔄</span><span>刷新</span></el-button>
        <el-button type="primary" @click="openImportDialog"><span>📥</span><span>导入线索</span></el-button>
      </div>
    </div>

    <!-- 顶部统计卡片 -->
    <div class="stats-grid">
      <div class="stat-card stat-pending">
        <div class="stat-icon">⏳</div>
        <div class="stat-body">
          <div class="stat-label">待评估</div>
          <div class="stat-value">{{ stats.pending || 0 }}</div>
        </div>
      </div>
      <div class="stat-card stat-evaluated">
        <div class="stat-icon">🧠</div>
        <div class="stat-body">
          <div class="stat-label">已评估</div>
          <div class="stat-value">{{ stats.evaluated || 0 }}</div>
        </div>
      </div>
      <div class="stat-card stat-imported">
        <div class="stat-icon">✅</div>
        <div class="stat-body">
          <div class="stat-label">已分配</div>
          <div class="stat-value">{{ stats.imported || 0 }}</div>
        </div>
      </div>
      <div class="stat-card stat-avg">
        <div class="stat-icon">📊</div>
        <div class="stat-body">
          <div class="stat-label">平均意向分</div>
          <div class="stat-value">{{ avgScore }}</div>
        </div>
      </div>
      <div class="stat-card stat-sources">
        <div class="stat-icon">🔌</div>
        <div class="stat-body">
          <div class="stat-label">启用线索源</div>
          <div class="stat-value">{{ enabledSources }}</div>
        </div>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="content-tabs">
      <!-- ==================== 线索队列 ==================== -->
      <el-tab-pane label="线索队列" name="queue">
        <!-- 五大能力域类别筛选 -->
        <div class="category-bar">
          <div :class="['cat-chip', { active: !filterCategory }]" @click="setCategory('')">
            <span class="cat-icon">🗂️</span><span>全部</span>
            <span class="cat-count">{{ totalCount }}</span>
          </div>
          <div v-for="c in categories" :key="c.value"
               :class="['cat-chip', 'cat-' + c.value, { active: filterCategory === c.value }]"
               @click="setCategory(c.value)">
            <span class="cat-icon">{{ c.icon }}</span><span>{{ c.label }}</span>
            <span class="cat-count">{{ categoryStats[c.value] || 0 }}</span>
          </div>
        </div>

        <div class="filter-bar">
          <el-select v-model="filterStatus" placeholder="全部状态" clearable @change="fetchLeads" style="width:140px">
            <el-option label="待评估" value="pending" />
            <el-option label="已评估" value="evaluated" />
            <el-option label="已分配" value="imported" />
          </el-select>
          <el-select v-model="filterSource" placeholder="全部来源" clearable @change="fetchLeads" style="width:180px">
            <el-option label="🤖 AI商机识别" value="__ai__" />
            <el-option v-for="s in sources" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
          <el-input v-model="keyword" placeholder="搜索商机名称/公司/联系人/备注..." clearable @clear="fetchLeads" @keyup.enter="fetchLeads" style="width:280px">
            <template #append><el-button @click="fetchLeads">搜索</el-button></template>
          </el-input>
          <div class="action-group">
            <el-button v-if="isDirector" type="warning" @click="handleBatchEvaluate" :loading="evaluating" :disabled="!pendingCount">
              <span>🧠</span><span>批量AI评估</span>
            </el-button>
            <el-button type="success" v-if="isDirector" @click="openBatchAssignDialog" :disabled="!unassignedCount">
              <span>🧰</span><span>批量分配</span>
            </el-button>
            <el-button v-if="isDirector" @click="handleCleanup" type="info" plain><span>🧹</span><span>清理过期</span></el-button>
          </div>
        </div>

        <el-table :data="leads" v-loading="loading" stripe class="leads-table" max-height="70vh">
          <el-table-column type="index" label="#" width="50" />
          <el-table-column label="能力域" width="110">
            <template #default="{ row }">
              <span v-if="row.category" :class="['cat-badge', 'cb-' + categoryKey(row.category)]" :title="row.category">
                {{ categoryIcon(row.category) }} {{ row.category }}
              </span>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="商机名称 / 招标单位" min-width="200">
            <template #default="{ row }">
              <div class="opp-cell">
                <div class="opp-name">{{ row.opportunity_name || row.company || '—' }}</div>
                <div class="company-sub">🏢 {{ row.company }}<span v-if="row.contact_name"> · 👤 {{ row.contact_name }}</span><span v-if="row.phone"> · 📞 {{ row.phone }}</span></div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="行业/区域" width="110">
            <template #default="{ row }">
              <div>{{ row.industry || '—' }}</div>
              <div class="muted">{{ row.region || '—' }}</div>
            </template>
          </el-table-column>
          <el-table-column label="来源/链接" width="110">
            <template #default="{ row }">
              <div class="source-tag">{{ row.source || row.source_name || '—' }}</div>
              <a v-if="row.link" :href="row.link" target="_blank" rel="noopener" class="link-btn" title="打开招标详情链接">
                <span>🔗</span><span>详情链接</span>
              </a>
            </template>
          </el-table-column>
          <el-table-column label="招标详情" min-width="180">
            <template #default="{ row }">
              <div v-if="row.tender_no || row.publish_date || row.deadline || row.budget || row.agency" class="tender-detail">
                <div v-if="row.tender_no" class="tender-no">🔖 {{ row.tender_no }}</div>
                <div v-if="row.publish_date" class="tender-date muted">📅 {{ row.publish_date }}</div>
                <div v-if="row.deadline" :class="['tender-date', { 'proc-expired': isExpired(row.deadline) }]">⏰ {{ row.deadline }}</div>
                <div v-if="row.budget" class="tender-budget">💰 {{ row.budget }}</div>
                <div v-if="row.agency" class="tender-agency">📑 {{ row.agency }}<span v-if="row.agency_phone"> · ☎️ {{ row.agency_phone }}</span></div>
              </div>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="意向分" width="80" align="center">
            <template #default="{ row }">
              <span v-if="row.intent_score !== null && row.intent_score !== undefined"
                    :class="['score-badge', scoreClass(row.intent_score)]">{{ row.intent_score }}</span>
              <span v-else class="muted">未评估</span>
            </template>
          </el-table-column>
          <el-table-column label="评估理由" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.eval_reason" class="reason-text">{{ row.eval_reason }}</span>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="推荐分配" width="120">
            <template #default="{ row }">
              <div v-if="row.assigned_name" class="assignee-cell">
                <el-tooltip v-if="rowAssignReason(row)" placement="top" :show-after="300">
                  <template #content>
                    <div style="max-width:360px; line-height:1.6">
                      <div><b>综合评分：{{ rowAssignReason(row).score }} 分</b>（满分100）</div>
                      <div v-if="rowAssignReason(row).reason" style="margin-top:4px; color:#fff">{{ rowAssignReason(row).reason }}</div>
                    </div>
                  </template>
                  <span class="assignee">{{ row.assigned_name }}</span>
                  <span class="assign-score">{{ rowAssignReason(row).score }}分</span>
                </el-tooltip>
                <span v-else class="assignee">{{ row.assigned_name }}</span>
              </div>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <span :class="['status-badge', 'st-' + row.status]">{{ statusLabel(row.status) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button text size="small" @click="handleEvaluate(row)" v-if="isDirector && row.status === 'pending'">评估</el-button>
              <el-button text size="small" type="primary" @click="openAssignDialog(row)" v-if="isDirector && row.status === 'evaluated'">分配</el-button>
              <el-button text size="small" type="danger" @click="handleReject(row)" v-if="isDirector && ['pending','evaluated'].includes(row.status)">拒绝</el-button>
              <el-button text size="small" @click="openDetail(row)">详情</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="!leads.length && !loading" class="empty-state">
          <div class="empty-icon">📭</div>
          <div class="empty-text">暂无线索</div>
          <div class="empty-desc">真实线索来自五大能力域外网抓取（招投标/电商/企业客源/竞品/舆情），点击「抓取全部源」触发；或前往「线索源管理」配置更多渠道</div>
        </div>
      </el-tab-pane>

      <!-- ==================== 线索源管理（已迁移至系统管理→数据源管理） ==================== -->
      <el-tab-pane label="线索源管理" name="sources">
        <el-alert type="success" :closable="false" style="margin-bottom:12px"
                  title="线索源管理已统一至「系统管理 → 数据源管理」"
                  description="数据源 CRUD、采集器插件绑定、手动采集已收口至统一的数据源管理页面，支持插件式采集器、三级业务标签过滤、采集频率调度。" />
        <div class="source-redirect">
          <el-button type="primary" size="large" @click="$router.push('/data-sources')">
            📡 前往数据源管理
          </el-button>
          <span class="redirect-tip">或在左侧菜单「🔧 系统管理 → 📡 数据源管理」进入</span>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 分配对话框 -->
    <el-dialog v-model="assignVisible" title="分配线索" width="560px" :close-on-click-modal="false" :close-on-press-escape="false">
      <div v-if="currentLead" class="assign-content">
        <div class="assign-info">
          <div class="info-row opp-title" v-if="currentLead.opportunity_name"><span class="info-label">商机：</span>{{ currentLead.opportunity_name }}</div>
          <div class="info-row"><span class="info-label">公司：</span>{{ currentLead.company }}</div>
          <div class="info-row"><span class="info-label">意向分：</span>
            <span :class="['score-badge', scoreClass(currentLead.intent_score)]">{{ currentLead.intent_score }}</span>
          </div>
          <div class="info-row" v-if="currentLead.assigned_name">
            <span class="info-label">AI推荐：</span>
            <span class="assignee">{{ currentLead.assigned_name }}</span>
            <span v-if="currentAssignReason" class="assign-score">综合 {{ currentAssignReason.score }} 分</span>
          </div>
          <div class="info-row reason" v-if="currentLead.eval_reason"><span class="info-label">评估理由：</span>{{ currentLead.eval_reason }}</div>
          <div class="info-row reason" v-if="currentAssignReason?.reason">
            <span class="info-label">推荐依据：</span>{{ currentAssignReason.reason }}
          </div>
        </div>
        <el-form label-width="90px" style="margin-top:16px">
          <el-form-item label="分配给">
            <el-select v-model="assignForm.assigned_to" placeholder="选择销售人员" filterable style="width:100%">
              <el-option v-for="s in salespeople" :key="s.username" :label="`${s.name}（当前${s.biz_count}单）`" :value="s.username" />
            </el-select>
          </el-form-item>
        </el-form>
        <div class="assign-tip">分配后将自动创建客户 + 商机（引导需求阶段）并归属该销售，线索标记为已分配</div>
      </div>
      <template #footer>
        <el-button @click="assignVisible = false">取消</el-button>
        <el-button type="primary" @click="handleAssign" :loading="assigning">确认分配</el-button>
      </template>
    </el-dialog>

    <!-- 批量分配对话框（主任/院长专用） -->
    <el-dialog v-model="batchAssignVisible" title="批量分配线索（主任确认后执行）" width="1120px" top="6vh"
               :close-on-click-modal="false" :close-on-press-escape="false">
      <!-- 顶部控制区 -->
      <div class="batch-toolbar">
        <div class="bt-left">
          <el-select v-model="selectedSalesUsernames" multiple collapse-tags collapse-tags-tooltip
                     collapse-tags-tooltip-offset="0"
                     placeholder="选择参与分配的销售（默认全部）" style="min-width:300px;max-width:380px"
                     :loading="previewLoading" @change="handleSalesSelectionChanged">
            <template #header>
              <div style="padding:4px 12px 6px; display:flex; justify-content:space-between; align-items:center">
                <span style="color:#64748b;font-size:12px">共 {{ allSalesPool.length }} 位销售</span>
                <div>
                  <el-button link size="small" @click="selectAllSales">全选</el-button>
                  <el-button link size="small" @click="clearSalesSelection">清空</el-button>
                </div>
              </div>
            </template>
            <el-option-group v-for="(group, gi) in salesOptionGroups" :key="gi" :label="group.label">
              <el-option v-for="sp in group.items" :key="sp.username"
                         :label="`${sp.name}（商机${sp.biz_count}单）`" :value="sp.username" />
            </el-option-group>
          </el-select>
          <el-select v-model="batchScope" style="width:200px" @change="runPreview">
            <el-option label="仅已评估未分配" value="evaluated" />
            <el-option label="仅待评估（先评估再分配）" value="pending_eval" />
            <el-option label="全部未分配（推荐）" value="all_unassigned" />
          </el-select>
          <el-radio-group v-model="batchMode" @change="runPreview">
            <el-radio-button label="recommended">🧠 AI综合推荐</el-radio-button>
            <el-radio-button label="average">⚖️ 按数量平均分配</el-radio-button>
          </el-radio-group>
          <el-checkbox v-model="reEvaluate" @change="runPreview" :disabled="batchScope === 'pending_eval'">
            已评估线索重新评估
          </el-checkbox>
        </div>
        <div class="bt-right">
          <el-button :loading="previewLoading" @click="runPreview">🔄 重新生成草案</el-button>
          <el-tag type="info" effect="plain" v-if="previewSummary.total">共 {{ previewSummary.total }} 条</el-tag>
        </div>
      </div>

      <!-- 分配人数汇总条 -->
      <div class="distribution-bar" v-if="batchAllocations.length">
        <div v-for="sp in batchSalespeople" :key="sp.username" class="dist-card"
             :class="{ 'dist-full': sp.username === maxDistUser }">
          <div class="dist-name">{{ sp.name }}</div>
          <div class="dist-count">{{ distribution[sp.username] || 0 }}条</div>
          <div class="dist-extra">
            商机{{ sp.biz_count }}单
          </div>
        </div>
      </div>

      <!-- 分配表格 -->
      <div class="batch-table-wrap">
        <el-table :data="batchAllocations" stripe border size="small" max-height="52vh"
                  row-key="lead_id" :header-cell-style="{ background: '#f5f7fa' }">
          <el-table-column type="index" label="#" width="56" />
          <el-table-column label="招标单位/商机" min-width="230"
                           :class-name="({row}) => isInvalidRow(row) ? 'row-invalid' : ''">
            <template #default="{ row }">
              <div class="lead-title" v-if="row.opportunity_name" :title="row.opportunity_name"
                   :class="{ 'text-danger': isInvalidRow(row) }">
                📌 {{ row.opportunity_name }}
              </div>
              <div class="lead-company" :title="row.company" :class="{ 'text-danger': isInvalidRow(row) }">
                {{ row.company || '—' }}
                <el-tag v-if="isInvalidRow(row)" size="small" type="danger" effect="dark" style="margin-left:6px">
                  负责人不在候选集
                </el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="能力域/行业" width="170">
            <template #default="{ row }">
              <div><span v-if="row.category" class="muted">{{ row.category }}</span><span v-else class="muted">—</span></div>
              <div><span v-if="row.industry" class="muted">🏭 {{ row.industry }}</span><span v-else class="muted">—</span></div>
            </template>
          </el-table-column>
          <el-table-column label="意向分" width="90" align="center">
            <template #default="{ row }">
              <span v-if="row.intent_score != null"
                    :class="['score-badge', scoreClass(row.intent_score)]">{{ row.intent_score }}</span>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="预算" width="130">
            <template #default="{ row }">{{ row.budget || '—' }}</template>
          </el-table-column>
          <el-table-column label="截止时间" width="150">
            <template #default="{ row }">{{ row.deadline || '—' }}</template>
          </el-table-column>
          <el-table-column label="分配给（可调整）" width="230">
            <template #default="{ row }">
              <el-select v-model="row.assigned_to" size="small" filterable
                         :class="{ 'is-invalid': isInvalidRow(row) }"
                         style="width:100%" @change="onRowAssignChange(row)">
                <el-option v-for="s in batchSalespeople" :key="s.username"
                           :label="`${s.name}（已分${distribution[s.username]||0}条，商机${s.biz_count}单）`"
                           :value="s.username" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="分配依据" min-width="280" show-overflow-tooltip>
            <template #default="{ row }">
              <div v-if="row.assign_mode === 'average'" class="avg-tag">⚖️ {{ row.assign_reason }}</div>
              <div v-else>
                <span v-if="row.assign_score" :class="['score-badge', scoreClass(row.assign_score)]">{{ row.assign_score }}分</span>
                <span class="muted" v-if="row.assign_reason" style="margin-left:6px">{{ row.assign_reason }}</span>
                <span v-else class="muted">AI推荐</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" align="center">
            <template #default="{ $index }">
              <el-button-group>
                <el-button size="small" text @click="moveUp($index)" :disabled="$index===0" title="前移一条">↑</el-button>
                <el-button size="small" text @click="moveDown($index)" :disabled="$index===batchAllocations.length-1" title="后移一条">↓</el-button>
              </el-button-group>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="batch-footer">
        <div class="batch-tip" v-if="batchSalespeople.length">
          共 <b>{{ previewSummary.total }}</b> 条线索 · 在职销售 <b>{{ batchSalespeople.length }}</b> 人 ·
          平均每人 <b>{{ batchSalespeople.length ? Math.ceil(previewSummary.total / batchSalespeople.length) : 0 }}</b> 条
          <span v-if="invalidAllocationRows.length" class="done-err" style="margin-left:12px">
            ⚠️ {{ invalidAllocationRows.length }} 行负责人不在候选销售集
          </span>
          <span v-if="previewSummary.successCount" class="done-ok" style="margin-left:12px">
            本次已成功分配 {{ previewSummary.successCount }} 条
          </span>
          <span v-if="previewSummary.failCount" class="done-err" style="margin-left:12px">
            失败 {{ previewSummary.failCount }} 条
            <el-button link size="small" @click="showFailures = !showFailures">{{ showFailures ? '收起' : '查看详情' }}</el-button>
          </span>
        </div>
        <div>
          <el-button @click="batchAssignVisible = false">取消</el-button>
          <el-button type="primary"
                     :disabled="!batchAllocations.length || !!invalidAllocationRows.length"
                     :loading="confirmLoading" @click="confirmBatchAssign">
            <template v-if="invalidAllocationRows.length">请先修正 {{ invalidAllocationRows.length }} 行负责人</template>
            <template v-else>主任确认并执行分配（{{ validAllocationCount }} 条）</template>
          </el-button>
        </div>
      </div>

      <!-- 失败明细 -->
      <div v-if="showFailures && failList.length" class="fail-list">
        <div class="section-title" style="margin:8px 0">分配失败明细</div>
        <el-table :data="failList" size="small" border max-height="180">
          <el-table-column prop="lead_id" label="线索ID" width="90" />
          <el-table-column prop="message" label="原因" show-overflow-tooltip />
        </el-table>
      </div>
    </el-dialog>

    <!-- 线索详情对话框 -->
    <el-dialog v-model="detailVisible" title="线索详情" width="760px" :close-on-click-modal="false" :close-on-press-escape="false">
      <div v-if="currentLead" class="detail-content">
        <div class="detail-section">
          <div class="info-row opp-title" v-if="currentLead.opportunity_name"><span class="info-label">商机名称：</span>{{ currentLead.opportunity_name }}</div>
          <div class="info-row" v-if="currentLead.category">
            <span class="info-label">能力域：</span>
            <span :class="['cat-badge', 'cb-' + categoryKey(currentLead.category)]">{{ categoryIcon(currentLead.category) }} {{ currentLead.category }}</span>
          </div>
          <div class="info-row"><span class="info-label">公司：</span>{{ currentLead.company }}</div>
          <div class="info-row"><span class="info-label">联系人：</span>{{ currentLead.contact_name || '—' }}</div>
          <div class="info-row"><span class="info-label">电话：</span>{{ currentLead.phone || '—' }}</div>
          <div class="info-row"><span class="info-label">邮箱：</span>{{ currentLead.email || '—' }}</div>
          <div class="info-row"><span class="info-label">行业：</span>{{ currentLead.industry || '—' }}</div>
          <div class="info-row"><span class="info-label">区域：</span>{{ currentLead.region || '—' }}</div>
          <div class="info-row"><span class="info-label">来源：</span>{{ currentLead.source || currentLead.source_name || '—' }}</div>
          <div class="info-row"><span class="info-label">获取链接：</span>
            <a v-if="currentLead.link" :href="currentLead.link" target="_blank" rel="noopener" class="link-btn">{{ currentLead.link }}</a>
            <span v-else class="muted">—</span>
          </div>
          <!-- 招标信息专属字段 -->
          <div v-if="currentLead.tender_no" class="info-row"><span class="info-label">招标编号：</span>{{ currentLead.tender_no }}</div>
          <div v-if="currentLead.agency" class="info-row"><span class="info-label">招标代理机构：</span>{{ currentLead.agency }}</div>
          <div v-if="currentLead.agency_phone" class="info-row"><span class="info-label">代理机构电话：</span>{{ currentLead.agency_phone }}</div>
          <div v-if="currentLead.publish_date" class="info-row"><span class="info-label">发布时间：</span>{{ currentLead.publish_date }}</div>
          <div v-if="currentLead.deadline" class="info-row"><span class="info-label">投标截止时间：</span>{{ currentLead.deadline }}</div>
          <div v-if="currentLead.budget" class="info-row"><span class="info-label">招标估价：</span>{{ currentLead.budget }}</div>
          <!-- 能力域专属字段 -->
          <div v-if="currentLead.category === '电商商机' && currentRaw.rank" class="info-row">
            <span class="info-label">榜单排名：</span>#{{ currentRaw.rank }}
            <span v-if="currentRaw.price"> · 价格：{{ currentRaw.price }}</span>
            <span v-if="currentRaw.rating_count"> · 评价数：{{ currentRaw.rating_count }}</span>
          </div>
          <div v-if="currentLead.category === '舆情痛点' && currentRaw.pain_type" class="info-row">
            <span class="info-label">痛点类型：</span>{{ currentRaw.pain_type }}
            <span v-if="currentRaw.pain_count !== undefined"> · 痛点词：{{ currentRaw.pain_count }}</span>
            <span v-if="currentRaw.opp_count !== undefined"> · 商机词：{{ currentRaw.opp_count }}</span>
          </div>
          <div v-if="currentLead.category === '竞品情报' && currentRaw.competitor" class="info-row">
            <span class="info-label">竞品：</span>{{ currentRaw.competitor }}
            <span v-if="currentRaw.price"> · 价格：￥{{ currentRaw.price }}</span>
            <span v-if="currentRaw.promo"> · 促销：{{ currentRaw.promo }}</span>
          </div>
          <div v-if="currentLead.category === '企业客源' && currentRaw.legal_rep" class="info-row">
            <span class="info-label">法人：</span>{{ currentRaw.legal_rep }}
            <span v-if="currentRaw.reg_date"> · 成立：{{ currentRaw.reg_date }}</span>
          </div>
          <div class="info-row"><span class="info-label">备注：</span>{{ currentLead.remark || '—' }}</div>
        </div>
        <div class="detail-section">
          <div class="section-title">AI 评估结果</div>
          <div class="info-row"><span class="info-label">意向分：</span>
            <span v-if="currentLead.intent_score !== null && currentLead.intent_score !== undefined" :class="['score-badge', scoreClass(currentLead.intent_score)]">{{ currentLead.intent_score }}</span>
            <span v-else class="muted">未评估</span>
          </div>
          <div class="info-row reason" v-if="currentLead.eval_reason"><span class="info-label">评估理由：</span>{{ currentLead.eval_reason }}</div>
          <div class="info-row"><span class="info-label">推荐分配：</span>{{ currentLead.assigned_name || '—' }}</div>
          <div class="info-row" v-if="currentLead.business_id">
            <span class="info-label">已转商机：</span>
            <a class="link-btn" @click="goToBusiness(currentLead.business_id)">
              商机 #{{ currentLead.business_id }}（引导需求阶段）
            </a>
          </div>
          <div class="info-row"><span class="info-label">状态：</span>
            <span :class="['status-badge', 'st-' + currentLead.status]">{{ statusLabel(currentLead.status) }}</span>
          </div>
        </div>
        <!-- AI 推荐负责人分析：综合历史拜访案例、商机情况、合同签订情况的多维度科学推荐 -->
        <div class="detail-section" v-if="currentAssignReason">
          <div class="section-title">
            AI 推荐负责人分析
            <span class="section-hint">（基于销售历史拜访/商机/合同数据多维度评分）</span>
          </div>
          <div class="assign-analysis">
            <div class="analysis-summary">
              <div class="summary-score">
                <div class="score-num">{{ currentAssignReason.score }}</div>
                <div class="score-unit">分 / 满分100</div>
              </div>
              <div class="summary-reason">{{ currentAssignReason.reason }}</div>
            </div>
            <div class="analysis-dimensions" v-if="currentAssignReason.details">
              <div class="dim-title">维度得分明细</div>
              <div class="dim-bar" v-for="(val, key) in currentAssignReason.details" :key="key">
                <div class="dim-label">{{ dimensionLabels[key] || key }}</div>
                <div class="dim-track">
                  <div class="dim-fill" :style="{ width: dimPercent(val, key) + '%' }"></div>
                </div>
                <div class="dim-value">{{ val }}<span class="dim-max">/{{ dimMax(key) }}</span></div>
              </div>
            </div>
            <div class="analysis-candidates" v-if="currentAssignReason.all_candidates?.length">
              <div class="dim-title">Top5 候选人对比</div>
              <el-table :data="currentAssignReason.all_candidates" size="small" border>
                <el-table-column label="排名" type="index" width="55" align="center" />
                <el-table-column label="销售" width="100">
                  <template #default="{ row }">{{ row.name }}</template>
                </el-table-column>
                <el-table-column label="综合分" width="75" align="center">
                  <template #default="{ row }">
                    <span :class="['cand-score', row.username === currentLead.assigned_to ? 'cand-best' : '']">{{ row.score }}</span>
                  </template>
                </el-table-column>
                <el-table-column v-for="(label, key) in dimensionLabels" :key="key" :label="label" align="center" min-width="68">
                  <template #default="{ row }">{{ row.details?.[key] ?? '—' }}</template>
                </el-table-column>
              </el-table>
            </div>
          </div>
        </div>
        <div class="detail-section" v-if="currentLead.raw_data">
          <div class="section-title">原始数据</div>
          <pre class="raw-data">{{ formatRaw(currentLead.raw_data) }}</pre>
        </div>
      </div>
    </el-dialog>

    <!-- 导入线索对话框（JSON / 表格上传双模式） -->
    <el-dialog v-model="importVisible" title="导入线索" width="860px" :close-on-click-modal="false" :close-on-press-escape="false" top="6vh">
      <el-tabs v-model="importTab" class="import-tabs">
        <el-tab-pane label="📋 表格导入（Excel / CSV）" name="excel">
          <div class="excel-import">
            <div class="import-upload-area" @click="$refs.fileInput?.click()" @dragover.prevent @drop.prevent="handleDrop">
              <el-upload
                :show-file-list="false"
                :before-upload="beforeFileUpload"
                accept=".xlsx,.xls,.csv"
                :auto-upload="false"
                ref="fileInput"
              >
                <el-icon class="upload-icon" style="font-size: 48px; color: #3b82f6;"><Upload /></el-icon>
                <div class="upload-text">
                  <div class="upload-title">点击或拖拽 Excel / CSV 文件到此处</div>
                  <div class="upload-tip">
                    支持列头：标题 / 发布时间 / 招标编号 / 地区 / 投标截止时间 / 招标估价 / 招标单位 / 招标联系人 / 招标联系电话 / 招标代理机构 / 代理电话 / 详情链接，或通用公司/商机名等。
                  </div>
                </div>
              </el-upload>
            </div>
            <div v-if="currentFile" class="file-info-bar">
              <span>📄 {{ currentFile.name }}</span>
              <span class="size">{{ formatSize(currentFile.size) }}</span>
              <el-button text size="small" @click="clearUploaded">重新选择</el-button>
            </div>

            <div v-if="parseLoading" class="parse-loading">
              <el-icon class="is-loading" style="font-size: 22px;"><Loading /></el-icon>
              <span>正在解析表格结构...</span>
            </div>

            <div v-else-if="parseResult" class="parse-result">
              <div class="parse-summary">
                <el-tag type="success" effect="plain">
                  ✅ 自动识别模块：{{ parseResult.module_names?.[parseResult.sheets?.[0]?.detected_module] || parseResult.sheets?.[0]?.detected_module }}
                </el-tag>
                <el-tag v-if="parseResult.sheets?.[0]?.is_ambiguous" type="warning" effect="plain">
                  ⚠️ 匹配歧义，请在下方手动选择模块
                </el-tag>
                <span class="parse-stats">
                  共 {{ currentSheet.total_rows }} 行 · 有效 {{ currentSheet.valid_count }} · 无效 {{ currentSheet.invalid_count }}
                </span>
                <div v-if="parseResult.sheets?.[0]?.module_scores?.length" class="module-switcher">
                  <span>切换模块：</span>
                  <el-select v-model="activeModule" size="small" style="width: 160px" @change="switchModule">
                    <el-option
                      v-for="m in parseResult.sheets[0].module_scores"
                      :key="m.module"
                      :label="`${m.name}(${m.score})`"
                      :value="m.module"
                    />
                  </el-select>
                </div>
                <div v-if="activeModule === 'scraped_leads'" class="update-link-switcher">
                  <el-checkbox v-model="updateLinkMode">仅更新已有线索的链接（按招标单位+商机名称匹配，不新建）</el-checkbox>
                </div>
              </div>

              <div class="preview-title">
                数据预览（前 200 行）
                <el-checkbox v-model="showInvalidOnly" size="small" style="margin-left:12px">只看无效行</el-checkbox>
              </div>
              <el-table :data="filteredPreview" stripe border size="small" max-height="320" class="preview-table">
                <el-table-column label="行号" type="index" width="60" />
                <el-table-column label="状态" width="80">
                  <template #default="{ row }">
                    <el-tag v-if="row.__valid" size="small" type="success" effect="plain">有效</el-tag>
                    <el-tooltip v-else :content="(row.__errors || []).join('; ')" placement="top">
                      <el-tag size="small" type="danger" effect="dark">无效</el-tag>
                    </el-tooltip>
                  </template>
                </el-table-column>
                <el-table-column v-for="col in previewColumns" :key="col.key" :prop="col.key" :label="col.label" min-width="130" show-overflow-tooltip>
                  <template #default="{ row }">
                    <span :class="{ 'invalid-value': !row.__valid && !row._meta_ok }">{{ row[col.key] }}</span>
                  </template>
                </el-table-column>
              </el-table>

              <div v-if="parseResult.sheets?.[0]?.unmapped_columns?.length" class="unmapped-tip">
                ⚠️ 未自动匹配的列：{{ parseResult.sheets[0].unmapped_columns.map(c => c.header).join('、') }}
              </div>
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane label="🧾 JSON 文本导入" name="json">
          <div class="import-tip">
            请输入 JSON 数组，每条线索包含 company(必填)/contact_name/phone/email/industry/region/source/remark 字段。
          </div>
          <el-input v-model="importText" type="textarea" :rows="12" placeholder='[{"company":"示例科技","contact_name":"张总","phone":"13800000000","industry":"信息技术","region":"全国","source":"手动导入","remark":"有采购需求"}]' />
        </el-tab-pane>

        <el-tab-pane label="🖼️ 图片OCR导入" name="ocr">
          <div class="ocr-import">
            <div class="import-upload-area" @click="$refs.ocrFileInput?.click()" @dragover.prevent @drop.prevent="handleOcrDrop">
              <el-upload
                :show-file-list="false"
                :before-upload="() => false"
                accept="image/*"
                :auto-upload="false"
                ref="ocrFileInput"
                multiple
                :on-change="handleOcrFileChange"
              >
                <el-icon class="upload-icon" style="font-size: 48px; color: #3b82f6;"><Picture /></el-icon>
                <div class="upload-text">
                  <div class="upload-title">点击或拖拽图片到此处（支持批量上传）</div>
                  <div class="upload-tip">支持 PNG / JPG / JPEG / BMP / WEBP / TIFF。OCR 识别文字后由 AI 自动解析为线索字段，可编辑后确认导入。</div>
                </div>
              </el-upload>
            </div>

            <div v-if="ocrProcessing" class="parse-loading">
              <el-icon class="is-loading" style="font-size: 22px;"><Loading /></el-icon>
              <span>正在 OCR 识别并 AI 解析（{{ ocrProgress.current }}/{{ ocrProgress.total }}）...</span>
            </div>

            <div v-else-if="ocrResults.length" class="parse-result">
              <div class="parse-summary">
                <span class="parse-stats">共识别 {{ ocrResults.length }} 张图片</span>
                <el-tag v-if="ocrResults.filter(r => r.error).length" type="warning" effect="plain">
                  {{ ocrResults.filter(r => r.error).length }} 张识别失败
                </el-tag>
              </div>
              <div class="preview-title">线索预览（可编辑，公司为空的行将跳过）</div>
              <el-table :data="ocrEditableLeads" stripe border size="small" max-height="400" class="preview-table">
                <el-table-column label="图片" prop="image_name" width="120" show-overflow-tooltip />
                <el-table-column label="公司/招标单位" prop="company" min-width="140">
                  <template #default="{ row }"><el-input v-model="row.company" size="small" /></template>
                </el-table-column>
                <el-table-column label="商机名称" prop="opportunity_name" min-width="140">
                  <template #default="{ row }"><el-input v-model="row.opportunity_name" size="small" /></template>
                </el-table-column>
                <el-table-column label="联系人" prop="contact_name" width="90">
                  <template #default="{ row }"><el-input v-model="row.contact_name" size="small" /></template>
                </el-table-column>
                <el-table-column label="电话" prop="phone" width="120">
                  <template #default="{ row }"><el-input v-model="row.phone" size="small" /></template>
                </el-table-column>
                <el-table-column label="邮箱" prop="email" width="150">
                  <template #default="{ row }"><el-input v-model="row.email" size="small" /></template>
                </el-table-column>
                <el-table-column label="行业" prop="industry" width="90">
                  <template #default="{ row }"><el-input v-model="row.industry" size="small" /></template>
                </el-table-column>
                <el-table-column label="地区" prop="region" width="90">
                  <template #default="{ row }"><el-input v-model="row.region" size="small" /></template>
                </el-table-column>
                <el-table-column label="备注" prop="remark" min-width="130">
                  <template #default="{ row }"><el-input v-model="row.remark" size="small" /></template>
                </el-table-column>
                <el-table-column label="状态" width="70">
                  <template #default="{ row }">
                    <el-tag v-if="row._error" type="danger" size="small">失败</el-tag>
                    <el-tag v-else type="success" size="small">正常</el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>

      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button v-if="importTab === 'excel' && parseResult"
                   type="primary" @click="confirmExcelImport" :loading="excelExecuting">
          确认导入（{{ selectedCount }} 行）
        </el-button>
        <el-button v-if="importTab === 'json'" type="primary" @click="handleImport" :loading="importing">导入</el-button>
        <el-button v-if="importTab === 'ocr' && ocrResults.length" type="primary" @click="confirmOcrImport" :loading="ocrExecuting">
          确认导入（{{ ocrValidCount }} 条）
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload, Loading, Picture } from '@element-plus/icons-vue'
import { useRouter, useRoute } from 'vue-router'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()
const activeTab = ref('queue')
const loading = ref(false)
const evaluating = ref(false)
const assigning = ref(false)
const importing = ref(false)

// ==================== 导入：通用状态 ====================
const importVisible = ref(false)
const importTab = ref('excel')  // 'excel' | 'json'
const importText = ref('')
const updateLinkMode = ref(false)  // 仅更新已有线索链接（不新建）

// ==================== 导入：图片OCR ====================
const ocrProcessing = ref(false)
const ocrProgress = ref({ current: 0, total: 0 })
const ocrResults = ref([])
const ocrEditableLeads = ref([])
const ocrExecuting = ref(false)
const ocrFileInput = ref(null)

const ocrValidCount = computed(() => ocrEditableLeads.value.filter(r => (r.company || '').trim()).length)

const handleOcrFileChange = (file) => {
  // el-upload on-change 在 multiple 模式下逐个触发，收集后统一上传
  if (file && file.raw) {
    _ocrSelectedFiles = _ocrSelectedFiles.filter(f => f.uid !== file.uid)
    _ocrSelectedFiles.push(file)
    _ocrPendingTimer && clearTimeout(_ocrPendingTimer)
    _ocrPendingTimer = setTimeout(() => {
      uploadOcrImages(_ocrSelectedFiles.map(f => f.raw))
      _ocrSelectedFiles = []
    }, 500)
  }
}

let _ocrSelectedFiles = []
let _ocrPendingTimer = null

const handleOcrDrop = (e) => {
  const files = Array.from(e.dataTransfer?.files || []).filter(f => f.type.startsWith('image/'))
  if (files.length) uploadOcrImages(files)
}

const uploadOcrImages = async (files) => {
  if (!files || !files.length) return
  ocrProcessing.value = true
  ocrProgress.value = { current: 0, total: files.length }
  ocrResults.value = []
  ocrEditableLeads.value = []
  try {
    const formData = new FormData()
    files.forEach(f => formData.append('images', f))
    const res = await api.post('/leads/ocr-images', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000
    })
    if (res.code === 200) {
      ocrResults.value = res.data.results || []
      ocrEditableLeads.value = ocrResults.value.map(r => ({
        image_name: r.image_name || '',
        company: r.parsed?.company || '',
        opportunity_name: r.parsed?.opportunity_name || '',
        contact_name: r.parsed?.contact_name || '',
        phone: r.parsed?.phone || '',
        email: r.parsed?.email || '',
        industry: r.parsed?.industry || '',
        region: r.parsed?.region || '',
        link: r.parsed?.link || '',
        remark: r.parsed?.remark || '',
        tender_no: r.parsed?.tender_no || '',
        budget: r.parsed?.budget || '',
        deadline: r.parsed?.deadline || '',
        publish_date: r.parsed?.publish_date || '',
        agency: r.parsed?.agency || '',
        agency_phone: r.parsed?.agency_phone || '',
        _error: r.error || ''
      }))
      ocrProgress.value.current = files.length
    } else {
      ElMessage.error(res.message || 'OCR 识别失败')
    }
  } catch (error) {
    const msg = error.message || '网络错误'
    if (msg.includes('timeout') || msg.includes('Timeout')) {
      ElMessage.error('OCR 识别超时：图片过大或服务器繁忙，请重试')
    } else if (msg.includes('Network Error') || msg.includes('网络错误')) {
      ElMessage.error('网络错误：无法连接到服务器，请检查后端是否正常运行')
    } else {
      ElMessage.error('OCR 识别失败：' + msg)
    }
  } finally {
    ocrProcessing.value = false
  }
}

const confirmOcrImport = async () => {
  const validLeads = ocrEditableLeads.value.filter(r => (r.company || '').trim())
  if (!validLeads.length) {
    ElMessage.warning('没有可导入的有效线索（公司名不能为空）')
    return
  }
  ocrExecuting.value = true
  try {
    const payload = validLeads.map(r => {
      const { _error, image_name, ...fields } = r
      return fields
    })
    const res = await api.post('/leads/ocr-images/execute', { leads: payload })
    if (res.code === 200) {
      ElMessage.success(`导入完成：成功 ${res.data.success_count} 条，失败 ${res.data.fail_count} 条`)
      importVisible.value = false
      ocrResults.value = []
      ocrEditableLeads.value = []
      fetchLeads()
      fetchStats()
    } else {
      ElMessage.error(res.message || '导入失败')
    }
  } catch (error) {
    ElMessage.error('导入失败：' + (error.message || '网络错误'))
  } finally {
    ocrExecuting.value = false
  }
}

// ==================== 导入：表格上传（smart-import） ====================
const currentFile = ref(null)
const parseLoading = ref(false)
const excelExecuting = ref(false)
const parseResult = ref(null)
const activeModule = ref('scraped_leads')

const currentSheet = computed(() => parseResult.value?.sheets?.[0] || { headers: [], rows: [], field_map: {} })

const headerLabelCache = {
  opportunity_name: '商机名称/标题', tender_no: '招标编号', publish_date: '发布时间',
  deadline: '投标截止时间', budget: '招标估价', company: '招标单位',
  contact_name: '招标联系人', phone: '联系电话', email: '邮箱',
  region: '地区', agency: '代理机构', agency_phone: '代理电话',
  link: '详情链接', industry: '行业', source: '来源', remark: '备注',
}
const FIELD_LABEL = (f) => headerLabelCache[f] || f

const previewColumns = computed(() => {
  const fm = currentSheet.value.all_field_maps?.[activeModule.value] || currentSheet.value.field_map || {}
  const pairs = Object.entries(fm).sort((a, b) => (Number(a[0]) || 0) - (Number(b[0]) || 0))
  const headers = currentSheet.value.headers || []
  return pairs.map(([k, v]) => {
    const colIdx = Number(k)
    return { key: v, label: `${FIELD_LABEL(v)} · ${headers[colIdx] || ''}` || v }
  })
})

const mappedPreview = computed(() => {
  const rows = currentSheet.value.rows || []
  const fm = currentSheet.value.all_field_maps?.[activeModule.value] || currentSheet.value.field_map || {}
  return rows.slice(0, 200).map(r => {
    const data = r.data || {}
    const mapped = { __valid: r.valid, __errors: r.errors }
    Object.entries(fm).forEach(([colIdx, fieldName]) => {
      mapped[fieldName] = data[fieldName] != null ? data[fieldName]
        : (r.raw && r.raw[Number(colIdx)] != null ? r.raw[Number(colIdx)] : '—')
    })
    return mapped
  })
})

const showInvalidOnly = ref(false)
const filteredPreview = computed(() => {
  if (!showInvalidOnly.value) return mappedPreview.value
  return mappedPreview.value.filter(r => !r.__valid)
})

const selectedCount = computed(() => {
  const rows = currentSheet.value.rows || []
  return rows.filter(r => r.selected !== false).length
})

const formatSize = (bytes) => {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let n = bytes
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++ }
  return `${n.toFixed(2)} ${units[i]}`
}

const beforeFileUpload = (file) => {
  if (!/\.(xlsx|xls|csv)$/i.test(file.name || '')) {
    ElMessage.error('只支持 .xlsx / .xls / .csv 文件')
    return false
  }
  currentFile.value = file
  runParse(file)
  return false  // 禁止 el-upload 自动上传
}

const handleDrop = (e) => {
  const files = e.dataTransfer?.files
  if (!files || !files.length) return
  const file = files[0]
  if (!/\.(xlsx|xls|csv)$/i.test(file.name || '')) {
    ElMessage.error('只支持 .xlsx / .xls / .csv 文件')
    return
  }
  currentFile.value = file
  runParse(file)
}

const clearUploaded = () => {
  currentFile.value = null
  parseResult.value = null
  activeModule.value = 'scraped_leads'
}

const runParse = async (file) => {
  parseLoading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file, file.name)
    const resp = await api.post('/smart-import/parse', fd, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    if (resp.code !== 200) throw new Error(resp.message || '解析失败')
    parseResult.value = resp.data
    // 自动选中线索模块（scraped_leads）作为默认；若识别到其他模块也回退到 scraped_leads
    const firstSheet = resp.data.sheets?.[0]
    const detected = firstSheet?.detected_module
    if (detected && ['scraped_leads', 'customers', 'business', 'enterprises'].includes(detected)) {
      activeModule.value = detected
    } else {
      activeModule.value = 'scraped_leads'
    }
  } catch (e) {
    ElMessage.error(e.message || '解析失败')
  } finally {
    parseLoading.value = false
  }
}

const switchModule = (mod) => {
  activeModule.value = mod
}

const confirmExcelImport = async () => {
  const sheet = currentSheet.value
  if (!sheet || !sheet.rows?.length) { ElMessage.warning('无数据可导入'); return }
  if (!activeModule.value) { ElMessage.warning('请选择导入模块'); return }
  const fm = sheet.all_field_maps?.[activeModule.value] || sheet.field_map
  const sheetsPayload = [{
    sheet_name: sheet.sheet_name || 'Sheet1',
    module: activeModule.value,
    field_map: fm,
    rows: sheet.rows.map(r => ({
      row_index: r.row_index, data: r.data, selected: r.selected !== false
    }))
  }]
  excelExecuting.value = true
  try {
    const resp = await api.post('/smart-import/execute', {
      sheets: sheetsPayload, is_wan: false,
      mode: updateLinkMode.value ? 'update_link' : ''
    })
    if (resp.code === 200) {
      const { total_success, total_fail } = resp.data || {}
      ElMessage.success(`导入完成：成功 ${total_success} 条（已存入原始情报库），失败 ${total_fail} 条。请到"原始情报"标签页查看，经AI商机识别分析后转入CRM分配销售`)
      importVisible.value = false
      clearUploaded()
      fetchLeads()
      fetchStats()
    } else {
      ElMessage.error(resp.message || '导入失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '导入失败')
  } finally {
    excelExecuting.value = false
  }
}

// ==================== 导入：JSON 文本（旧功能保留） ====================
const handleImport = async () => {
  let leadsData
  try { leadsData = JSON.parse(importText.value) } catch (e) { ElMessage.error('JSON 格式错误'); return }
  if (!Array.isArray(leadsData)) { ElMessage.warning('请输入 JSON 数组'); return }
  importing.value = true
  try {
    const resp = await api.post('/leads/import', { leads: leadsData })
    if (resp.code === 200) { ElMessage.success(resp.message); importVisible.value = false; fetchLeads(); fetchStats() }
    else ElMessage.error(resp.message)
  } catch (e) { ElMessage.error('导入失败') }
  finally { importing.value = false }
}

const leads = ref([])
const salespeople = ref([])
const stats = ref({})
const categoryStats = ref({})
const avgScore = ref(0)
const enabledSources = ref(0)
// 线索源管理已迁移至 /data-sources，此处保留空数组仅用于来源筛选下拉占位
const sources = ref([])

// 五大能力域定义（用于能力域筛选条与表格分类标签）
const categories = [
  { value: '招标标志管控', label: '招标标志管控', icon: '📌' },
  { value: '军采监控', label: '军采监控', icon: '🎖️' },
  { value: '电商商机', label: '电商商机', icon: '📦' },
  { value: '企业客源', label: '企业客源', icon: '📇' },
  { value: '竞品情报', label: '竞品情报', icon: '📊' },
  { value: '舆情痛点', label: '舆情痛点', icon: '💗' }
]
const categoryKeyMap = {
  '招标标志管控': 'bidding', '军采监控': 'military', '电商商机': 'ecommerce', '企业客源': 'b2b',
  '竞品情报': 'competitor', '舆情痛点': 'forum'
}
const categoryIconMap = {
  '招标标志管控': '📌', '军采监控': '🎖️', '电商商机': '📦', '企业客源': '📇',
  '竞品情报': '📊', '舆情痛点': '💗'
}
const categoryKey = (c) => categoryKeyMap[c] || 'other'
const categoryIcon = (c) => categoryIconMap[c] || '📌'

const filterStatus = ref('')
const filterSource = ref('')
const filterCategory = ref('')
const keyword = ref('')

const pendingCount = computed(() => stats.value.pending || 0)
const totalCount = computed(() => Object.values(stats.value).reduce((a, b) => a + (b || 0), 0))
const unassignedCount = computed(() => (stats.value.pending || 0) + (stats.value.evaluated || 0))
const isDirector = computed(() => {
  // 与项目其他模块（Contracts/Appraisal/Reports/Business...）一致的主任/院长角色判断
  const r = authStore.role
  if (r === '主任' || r === '院长') return true
  // 多角色（roles 数组）兜底
  const rs = Array.isArray(authStore.roles) ? authStore.roles : []
  return rs.some(x => x === '主任' || x === '院长')
})
const currentRaw = computed(() => {
  if (!currentLead.value?.raw_data) return {}
  try { return JSON.parse(currentLead.value.raw_data) } catch (e) { return {} }
})

// 解析 AI 推荐负责人的科学依据（综合评分+6维度分数+Top5候选）
const currentAssignReason = computed(() => {
  if (!currentLead.value?.assign_reason) return null
  try { return JSON.parse(currentLead.value.assign_reason) } catch (e) { return null }
})

// 表格行内解析 assign_reason（用于"推荐分配"列显示综合评分）
const rowAssignReason = (row) => {
  if (!row?.assign_reason) return null
  try { return JSON.parse(row.assign_reason) } catch (e) { return null }
}

// 维度中文名映射
const dimensionLabels = {
  industry_match: '行业匹配',
  performance: '历史业绩',
  business_advance: '商机推进',
  visit_experience: '拜访经验',
  workload_balance: '工作量均衡',
  region_match: '区域匹配'
}
// 各维度满分（与后端 _assign_lead 权重对齐）
const dimensionMax = {
  industry_match: 30,
  performance: 25,
  business_advance: 15,
  visit_experience: 15,
  workload_balance: 10,
  region_match: 5
}
const dimMax = (key) => dimensionMax[key] || 100
const dimPercent = (val, key) => {
  const max = dimensionMax[key] || 100
  return Math.min(100, Math.round((val / max) * 100))
}

const assignVisible = ref(false)
const detailVisible = ref(false)
const currentLead = ref(null)
const assignForm = ref({ assigned_to: '' })

const statusLabel = (s) => ({ pending: '待评估', evaluated: '已评估', imported: '已分配' }[s] || s)

const setCategory = (cat) => {
  filterCategory.value = cat
  fetchLeads()
}

const scoreClass = (score) => {
  if (score >= 80) return 'sc-high'
  if (score >= 60) return 'sc-mid'
  if (score >= 40) return 'sc-low'
  return 'sc-vlow'
}

const formatRaw = (raw) => {
  try { return JSON.stringify(JSON.parse(raw), null, 2) } catch (e) { return raw }
}

const fetchLeads = async () => {
  loading.value = true
  try {
    const params = {}
    if (filterStatus.value) params.status = filterStatus.value
    if (filterSource.value === '__ai__') params.source = 'AI商机识别'
    else if (filterSource.value) params.source_id = filterSource.value
    if (filterCategory.value) params.category = filterCategory.value
    if (keyword.value) params.keyword = keyword.value
    const resp = await api.get('/leads', params)
    if (resp.code === 200) {
      leads.value = resp.data.list || []
      stats.value = resp.data.stats || {}
      categoryStats.value = resp.data.category_stats || {}
    } else { ElMessage.error(resp.message) }
  } catch (e) { ElMessage.error('加载线索失败') }
  finally { loading.value = false }
}

const fetchStats = async () => {
  try {
    const resp = await api.get('/leads/stats')
    if (resp.code === 200) {
      avgScore.value = resp.data.avg_score || 0
      enabledSources.value = resp.data.enabled_sources || 0
      // 若线索列表未加载（如首次），用 stats 接口的 category_stats 兜底
      if (!Object.keys(categoryStats.value).length && resp.data.category_stats) {
        categoryStats.value = resp.data.category_stats
      }
    }
  } catch (e) { /* ignore */ }
}

const fetchData = async () => {
  await Promise.all([fetchLeads(), fetchStats()])
}

const loadSalespeople = async () => {
  // 复用用户列表接口获取在职销售
  try {
    const resp = await api.get('/users', { role: '销售' })
    if (resp.code === 200) {
      // 后端返回结构兼容 {data:[...]} 或直接数组
      const arr = Array.isArray(resp.data) ? resp.data : (resp.data?.list || [])
      salespeople.value = arr.map(u => ({ username: u.username, name: u.name, biz_count: u.biz_count || 0 }))
    }
  } catch (e) { /* ignore */ }
}

// ==================== 线索操作 ====================
const handleEvaluate = async (row) => {
  try {
    const resp = await api.post(`/leads/${row.id}/evaluate`)
    if (resp.code === 200) {
      ElMessage.success('评估完成')
      fetchLeads(); fetchStats()
    } else ElMessage.error(resp.message)
  } catch (e) { ElMessage.error('评估失败') }
}

const handleBatchEvaluate = async () => {
  evaluating.value = true
  try {
    const resp = await api.post('/leads/evaluate-batch')
    if (resp.code === 200) {
      ElMessage.success(resp.message)
      fetchLeads(); fetchStats()
    } else ElMessage.error(resp.message)
  } catch (e) { ElMessage.error('批量评估失败') }
  finally { evaluating.value = false }
}

const isExpired = (deadline) => {
  if (!deadline) return false
  const today = new Date().toISOString().substring(0, 10)
  return deadline < today
}

const handleCleanup = async () => {
  try {
    await ElMessageBox.confirm(
      '将清理超过30天的未分配线索及已过截止日期的军采线索，已分配线索保留。是否继续？',
      '清理过期线索', { type: 'warning', confirmButtonText: '确认清理', cancelButtonText: '取消' }
    )
    const resp = await api.post('/leads/cleanup-expired', { days: 30 })
    if (resp.code === 200) {
      ElMessage.success(resp.message)
      fetchLeads(); fetchStats()
    } else ElMessage.error(resp.message)
  } catch (e) { /* 用户取消 */ }
}

const openAssignDialog = async (row) => {
  currentLead.value = row
  assignForm.value.assigned_to = row.assigned_to || ''
  await loadSalespeople()
  // 若未加载到销售列表，用 AI 推荐兜底
  if (!salespeople.value.length && row.assigned_to) {
    salespeople.value = [{ username: row.assigned_to, name: row.assigned_name || row.assigned_to, biz_count: 0 }]
  }
  assignVisible.value = true
}

const handleAssign = async () => {
  if (!assignForm.value.assigned_to) { ElMessage.warning('请选择销售人员'); return }
  assigning.value = true
  try {
    const resp = await api.post(`/leads/${currentLead.value.id}/assign`, { assigned_to: assignForm.value.assigned_to })
    if (resp.code === 200) {
      // 分配成功：已自动创建客户 + 商机，提示完整链路信息
      const d = resp.data || {}
      const parts = [resp.message]
      if (d.customer_id) parts.push(`客户#${d.customer_id}`)
      if (d.business_id) parts.push(`商机#${d.business_id}`)
      ElMessage.success(parts.join('，'))
      assignVisible.value = false
      fetchLeads(); fetchStats()
    } else ElMessage.error(resp.message)
  } catch (e) { ElMessage.error('分配失败') }
  finally { assigning.value = false }
}

// 跳转到商机详情页（线索转化的商机）
const goToBusiness = (bizId) => {
  detailVisible.value = false
  router.push({ path: '/business', query: { id: bizId } })
}

const handleReject = async (row) => {
  try {
    // 拒绝即删除：提示用户该操作不可恢复
    await ElMessageBox.confirm(`确定拒绝线索「${row.company}」？拒绝后将自动删除该线索，操作不可恢复。`, '拒绝并删除线索', { type: 'warning', confirmButtonText: '确认拒绝', cancelButtonText: '取消' })
    const resp = await api.post(`/leads/${row.id}/reject`)
    if (resp.code === 200) { ElMessage.success('已拒绝并删除'); fetchLeads(); fetchStats() }
    else ElMessage.error(resp.message)
  } catch (e) { /* cancelled */ }
}

const openDetail = (row) => { currentLead.value = row; detailVisible.value = true }

// ==================== 批量分配（主任/院长） ====================
const batchAssignVisible = ref(false)
const previewLoading = ref(false)
const confirmLoading = ref(false)
const batchScope = ref('all_unassigned')
const batchMode = ref('average')
const reEvaluate = ref(false)
const batchSalespeople = ref([])           // 本次已选候选销售（过滤后）
const allSalesPool = ref([])                // 全量销售列表（用于下拉多选 options，首次加载后缓存）
const selectedSalesUsernames = ref([])      // 主任当前勾选的销售 username 数组
const batchAllocations = ref([])
const distribution = ref({})
const failList = ref([])
const showFailures = ref(false)
const previewSummary = ref({ total: 0, successCount: 0, failCount: 0 })
// —— 防并发请求 & 防初始化触发多余请求的控制标志 ——
const _previewReqId = ref(0)                 // 请求序号：响应回来序号<最新则丢弃(过期响应)
const _suppressSelectionChange = ref(false)  // true 时，销售选择@change 不触发 runPreview

const handleSalesSelectionChanged = () => {
  // 由程序初始化触发的选择变更（例如首次打开后自动全选填充）→ 不发请求
  if (_suppressSelectionChange.value) return
  runPreview()
}

const salesOptionGroups = computed(() => {
  // 简化：单组"全部销售"；如需按部门分组可通过 allSalesPool[x].department 聚合
  if (!allSalesPool.value.length) return []
  const groups = {}
  allSalesPool.value.forEach(sp => {
    const dept = sp.department && sp.department.trim() ? sp.department : '默认部门'
    if (!groups[dept]) groups[dept] = []
    groups[dept].push(sp)
  })
  return Object.keys(groups).sort().map(dept => ({ label: dept, items: groups[dept] }))
})

const selectAllSales = () => {
  selectedSalesUsernames.value = allSalesPool.value.map(s => s.username)
}
const clearSalesSelection = () => { selectedSalesUsernames.value = [] }

const maxDistUser = computed(() => {
  if (!distribution.value || !batchSalespeople.value.length) return ''
  let best = '', bestN = -1
  batchSalespeople.value.forEach(sp => {
    const n = distribution.value[sp.username] || 0
    if (n > bestN) { bestN = n; best = sp.username }
  })
  return best
})

// —— 候选销售集合 & 无效行判定（主任没选中的人不应出现在分配行里）
const validUsernames = computed(() => new Set((batchSalespeople.value || []).map(s => s.username)))
const isInvalidRow = (row) => {
  if (!row) return false
  const u = row.assigned_to
  if (!u) return true
  return !validUsernames.value.has(u)
}
const invalidAllocationRows = computed(() => batchAllocations.value.filter(isInvalidRow))
const validAllocationCount = computed(() => batchAllocations.value.length - invalidAllocationRows.value.length)

const recalcDistribution = () => {
  const d = {}
  batchSalespeople.value.forEach(sp => { d[sp.username] = 0 })
  batchAllocations.value.forEach(row => {
    const u = row.assigned_to
    // 只统计落在候选销售集中的分配（主任删除的人不计入汇总，避免汇总卡显示非候选人也有数量）
    if (u && validUsernames.value.has(u)) d[u] = (d[u] || 0) + 1
  })
  distribution.value = d
}

const onRowAssignChange = (_row) => { recalcDistribution() }

const moveUp = (idx) => {
  if (idx <= 0) return
  const arr = batchAllocations.value
  ;[arr[idx - 1], arr[idx]] = [arr[idx], arr[idx - 1]]
}
const moveDown = (idx) => {
  const arr = batchAllocations.value
  if (idx < 0 || idx >= arr.length - 1) return
  ;[arr[idx + 1], arr[idx]] = [arr[idx], arr[idx + 1]]
}

const openBatchAssignDialog = async () => {
  if (!isDirector.value) { ElMessage.warning('仅主任/院长可执行批量分配'); return }
  previewSummary.value = { total: 0, successCount: 0, failCount: 0 }
  failList.value = []
  showFailures.value = false
  // 打开对话框时：如有销售缓存，选中的销售保持；否则默认空（表示"全体参与"），后端按全体返回后再全选
  batchAssignVisible.value = true
  await runPreview()
}

const runPreview = async () => {
  const reqId = ++_previewReqId.value
  previewLoading.value = true
  try {
    const payload = {
      mode: batchMode.value,
      scope: batchScope.value,
      re_evaluate: reEvaluate.value,
    }
    if (selectedSalesUsernames.value.length) payload.sales_usernames = selectedSalesUsernames.value
    const resp = await api.post('/leads/allocation-preview', payload)
    // —— 竞态保护：若此期间又发了新请求(reqId 已变),丢弃本响应 ——
    if (reqId !== _previewReqId.value) return
    if (resp.code === 200) {
      const d = resp.data || {}
      batchSalespeople.value = d.salespeople || []
      batchAllocations.value = d.allocations || []
      distribution.value = d.distribution || {}
      // 首次加载（没缓存销售列表）：把后端返回的销售存入全量池 + 初始化全选
      if (!allSalesPool.value.length && batchSalespeople.value.length) {
        allSalesPool.value = batchSalespeople.value.map(s => ({
          username: s.username, name: s.name, biz_count: s.biz_count || 0, department: s.department || '',
        }))
        if (!selectedSalesUsernames.value.length) {
          // 自动全选 → 打开 suppress 避免触发多余的 runPreview 请求（请求 1 已在进行中）
          try {
            _suppressSelectionChange.value = true
            selectedSalesUsernames.value = allSalesPool.value.map(s => s.username)
          } finally {
            _suppressSelectionChange.value = false
          }
        }
      }
      previewSummary.value.total = batchAllocations.value.length
      previewSummary.value.successCount = 0
      previewSummary.value.failCount = 0
      if (!batchAllocations.value.length) ElMessage.info(resp.message || '暂无可分配线索')
    } else ElMessage.error(resp.message)
  } catch (e) { ElMessage.error('生成分配草案失败') }
  finally {
    if (reqId === _previewReqId.value) previewLoading.value = false
  }
}

const confirmBatchAssign = async () => {
  if (!batchAllocations.value.length) { ElMessage.warning('暂无可分配线索'); return }
  try {
    await ElMessageBox.confirm(
      `将批量执行 ${batchAllocations.value.length} 条线索分配，每条线索会自动创建客户+商机。` +
      `此步骤由主任确认并执行，确定继续？`, '确认批量分配',
      { type: 'warning', confirmButtonText: '主任确认执行', cancelButtonText: '取消' }
    )
  } catch (e) { return }
  confirmLoading.value = true
  try {
    const payload = batchAllocations.value.map(r => ({ lead_id: r.lead_id, assigned_to: r.assigned_to }))
    const resp = await api.post('/leads/allocation-confirm', { allocations: payload })
    if (resp.code === 200) {
      const d = resp.data || {}
      previewSummary.value.successCount = d.success_count || 0
      previewSummary.value.failCount = d.fail_count || 0
      failList.value = d.failures || []
      // 从待分配列表中移除已成功的（失败的留在原列表方便主任处置）
      const successIds = new Set((d.imported || []).map(x => x.lead_id))
      batchAllocations.value = batchAllocations.value.filter(r => !successIds.has(r.lead_id))
      recalcDistribution()
      previewSummary.value.total = batchAllocations.value.length
      ElMessage.success(resp.message)
      fetchLeads(); fetchStats()
      if (!batchAllocations.value.length) {
        setTimeout(() => { batchAssignVisible.value = false }, 800)
      }
    } else ElMessage.error(resp.message)
  } catch (e) { ElMessage.error('执行批量分配失败') }
  finally { confirmLoading.value = false }
}

// ==================== 线索源管理已迁移至 /data-sources，此处不再维护 ====================

// ==================== 导入（旧文本模式合并至顶部统一实现，此处仅保留 openImportDialog） ====================
const openImportDialog = () => {
  importText.value = ''
  updateLinkMode.value = false
  clearUploaded()
  importTab.value = 'excel'
  importVisible.value = true
}

onMounted(() => {
  // 支持从原始情报页跳转过来时预填搜索
  const q = String(route.query.search || '').trim()
  if (q) keyword.value = q
  fetchData()
})
</script>

<style scoped>
.leads-container { padding: 0; }

.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.page-title { font-size: 22px; font-weight: 600; color: #1e293b; margin: 0; }
.page-desc { font-size: 13px; color: #64748b; margin: 6px 0 0; }
.header-right { display: flex; gap: 10px; }

/* 统计卡片 */
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; margin-bottom: 20px; }
.stat-card { background: white; border-radius: 12px; padding: 16px; display: flex; align-items: center; gap: 12px; border: 1px solid #e2e8f0; box-shadow: 0 2px 8px rgba(0,0,0,0.03); }
.stat-icon { width: 44px; height: 44px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 22px; }
.stat-pending .stat-icon { background: #fef3c7; } .stat-pending .stat-value { color: #d97706; }
.stat-evaluated .stat-icon { background: #dbeafe; } .stat-evaluated .stat-value { color: #2563eb; }
.stat-imported .stat-icon { background: #d1fae5; } .stat-imported .stat-value { color: #059669; }
.stat-avg .stat-icon { background: #ede9fe; } .stat-avg .stat-value { color: #7c3aed; }
.stat-sources .stat-icon { background: #e0f2fe; } .stat-sources .stat-value { color: #0284c7; }
.stat-body { display: flex; flex-direction: column; }
.stat-label { font-size: 12px; color: #64748b; }
.stat-value { font-size: 22px; font-weight: 700; line-height: 1.2; }

.content-tabs { background: white; border-radius: 12px; padding: 16px; border: 1px solid #e2e8f0; }

.filter-bar { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.action-group { margin-left: auto; display: flex; gap: 8px; }
.source-tip { color: #64748b; font-size: 13px; margin-right: auto; }
.source-redirect { display: flex; align-items: center; gap: 16px; padding: 30px 0; justify-content: center; }
.redirect-tip { color: #909399; font-size: 13px; }

.leads-table { width: 100%; }
.company-cell .company-name { font-weight: 600; color: #1e293b; }
.company-sub { font-size: 12px; color: #94a3b8; margin-top: 2px; }
.opp-cell .opp-name { font-weight: 600; color: #1e293b; font-size: 14px; line-height: 1.4; }
.opp-cell .company-sub { margin-top: 3px; }
.opp-title { font-size: 15px; font-weight: 600; color: #1e293b; margin-bottom: 8px !important; }
.link-btn { display: inline-flex; align-items: center; gap: 4px; color: #2563eb; text-decoration: none; font-size: 12px; word-break: break-all; }
.link-btn:hover { color: #1d4ed8; text-decoration: underline; }

/* 采购详情列（发布日期/截止日期/预算/采购方式） */
.proc-detail { line-height: 1.7; }
.proc-method { font-size: 12px; color: #1e40af; font-weight: 500; }
.proc-budget { font-size: 12px; color: #d97706; }
.proc-deadline { font-size: 12px; color: #059669; }
.proc-deadline.proc-expired { color: #dc2626; text-decoration: line-through; }
.proc-publish { font-size: 12px; }
.muted { color: #94a3b8; font-size: 12px; }

/* 联系信息（商机名称子行） */
.company-sub { font-size: 12px; color: #64748b; margin-top: 2px; word-break: break-all; }

/* 招标详情列（编号/发布/截止/估价/代理） */
.tender-detail { line-height: 1.7; }
.tender-no { font-size: 12px; color: #7c3aed; font-weight: 600; }
.tender-date { font-size: 12px; color: #059669; }
.tender-date.muted { color: #94a3b8; }
.tender-budget { font-size: 12px; color: #d97706; }
.tender-agency { font-size: 12px; color: #334155; }
.mono { font-family: monospace; font-size: 12px; }
.remark-text { font-size: 13px; color: #475569; }
.src-name { font-weight: 600; color: #1e293b; }
.assignee { color: #059669; font-weight: 600; font-size: 13px; }

.source-tag { font-size: 12px; padding: 2px 8px; border-radius: 8px; background: #f1f5f9; color: #475569; }

/* 五大能力域类别筛选条 */
.category-bar { display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
.cat-chip { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: 20px;
            background: #f8fafc; border: 1px solid #e2e8f0; cursor: pointer; font-size: 13px; color: #475569;
            transition: all 0.2s; user-select: none; }
.cat-chip:hover { border-color: #94a3b8; background: #f1f5f9; }
.cat-chip.active { color: white; border-color: transparent; font-weight: 600; }
.cat-chip .cat-icon { font-size: 15px; }
.cat-chip .cat-count { background: rgba(255,255,255,0.3); padding: 1px 7px; border-radius: 10px; font-size: 11px; }
.cat-chip:not(.active) .cat-count { background: #e2e8f0; color: #64748b; }
.cat-chip.cat-招投标监控.active { background: #3b82f6; }
.cat-chip.cat-军采监控.active { background: #1e40af; }
.cat-chip.cat-电商商机.active { background: #f59e0b; }
.cat-chip.cat-企业客源.active { background: #10b981; }
.cat-chip.cat-竞品情报.active { background: #ef4444; }
.cat-chip.cat-舆情痛点.active { background: #8b5cf6; }

/* 能力域徽标 */
.cat-badge { font-size: 11px; padding: 2px 8px; border-radius: 8px; font-weight: 500; white-space: nowrap; }
.cb-bidding { background: #dbeafe; color: #2563eb; }
.cb-military { background: #dbeafe; color: #1e40af; }
.cb-ecommerce { background: #fef3c7; color: #d97706; }
.cb-b2b { background: #d1fae5; color: #059669; }
.cb-competitor { background: #fee2e2; color: #dc2626; }
.cb-forum { background: #ede9fe; color: #7c3aed; }
.cb-other { background: #f1f5f9; color: #475569; }

.form-tip { font-size: 12px; color: #94a3b8; line-height: 1.5; margin-top: 4px; }

.score-badge { display: inline-block; min-width: 36px; padding: 3px 8px; border-radius: 12px; font-weight: 700; font-size: 13px; text-align: center; }
.sc-high { background: #d1fae5; color: #059669; }
.sc-mid { background: #dbeafe; color: #2563eb; }
.sc-low { background: #fef3c7; color: #d97706; }
.sc-vlow { background: #fee2e2; color: #dc2626; }

.status-badge { font-size: 11px; padding: 3px 10px; border-radius: 10px; font-weight: 500; }
.st-pending { background: #fef3c7; color: #d97706; }
.st-evaluated { background: #dbeafe; color: #2563eb; }
.st-imported { background: #d1fae5; color: #059669; }

.type-badge { font-size: 11px; padding: 2px 8px; border-radius: 8px; font-weight: 500; }
.tp-rss { background: #ede9fe; color: #7c3aed; }
.tp-api { background: #e0f2fe; color: #0284c7; }
.tp-html { background: #fce7f3; color: #db2777; }
.tp-ai_search { background: #ccfbf1; color: #0d9488; font-weight: 600; }
.tp-sample { background: #f1f5f9; color: #475569; }
.tp-manual { background: #fef3c7; color: #d97706; }

.empty-state { text-align: center; padding: 60px 20px; color: #94a3b8; }
.empty-icon { font-size: 48px; margin-bottom: 12px; }
.empty-text { font-size: 16px; color: #64748b; margin-bottom: 6px; }
.empty-desc { font-size: 13px; }

/* 对话框 */
.assign-content .assign-info { background: #f8fafc; padding: 14px 16px; border-radius: 8px; border-left: 3px solid #667eea; }
.info-row { font-size: 14px; color: #334155; margin-bottom: 6px; }
.info-row.reason { color: #64748b; font-size: 13px; line-height: 1.5; }
.info-label { color: #64748b; font-weight: 500; }
.assign-tip { margin-top: 12px; font-size: 12px; color: #94a3b8; }

.detail-content { padding: 0 10px; }
.detail-section { margin-bottom: 18px; padding-bottom: 14px; border-bottom: 1px dashed #e2e8f0; }
.detail-section:last-child { border-bottom: none; }
.section-title { font-size: 14px; font-weight: 600; color: #475569; margin-bottom: 10px; }
.section-hint { font-size: 12px; color: #94a3b8; font-weight: normal; }
.raw-data { background: #f8fafc; padding: 12px; border-radius: 8px; font-size: 12px; color: #475569; max-height: 200px; overflow: auto; white-space: pre-wrap; word-break: break-all; }

/* 表格"推荐分配"列：姓名 + 综合评分徽章 */
.assignee-cell { display: inline-flex; align-items: center; gap: 6px; }
.assign-score {
  display: inline-block; padding: 1px 6px; border-radius: 8px; font-size: 11px;
  font-weight: 600; color: #fff; background: #3b82f6;
}

/* 详情对话框：AI 推荐负责人分析区块 */
.assign-analysis { display: flex; flex-direction: column; gap: 16px; }
.analysis-summary {
  display: flex; gap: 16px; align-items: center; padding: 12px 14px;
  background: linear-gradient(135deg, #eff6ff 0%, #f0f9ff 100%);
  border-radius: 10px; border: 1px solid #dbeafe;
}
.summary-score {
  flex-shrink: 0; text-align: center; padding: 6px 14px;
  background: #fff; border-radius: 10px; border: 1px solid #bfdbfe;
}
.score-num { font-size: 26px; font-weight: 700; color: #2563eb; line-height: 1.1; }
.score-unit { font-size: 11px; color: #64748b; margin-top: 2px; }
.summary-reason { font-size: 13px; color: #1e293b; line-height: 1.6; flex: 1; }
.analysis-dimensions, .analysis-candidates { display: flex; flex-direction: column; gap: 8px; }
.dim-title { font-size: 13px; font-weight: 600; color: #475569; }
.dim-bar { display: flex; align-items: center; gap: 10px; font-size: 12px; }
.dim-label { width: 80px; color: #64748b; flex-shrink: 0; }
.dim-track {
  flex: 1; height: 8px; background: #f1f5f9; border-radius: 4px; overflow: hidden;
}
.dim-fill {
  height: 100%; background: linear-gradient(90deg, #60a5fa, #3b82f6);
  border-radius: 4px; transition: width 0.4s ease;
}
.dim-value { width: 56px; text-align: right; color: #1e293b; font-weight: 600; flex-shrink: 0; }
.dim-max { color: #94a3b8; font-weight: normal; font-size: 11px; }
.cand-score { font-weight: 600; color: #475569; }
.cand-best { color: #fff; background: #10b981; padding: 2px 8px; border-radius: 8px; }

.import-tip { background: #fffbeb; border: 1px solid #fde68a; color: #92400e; padding: 10px 14px; border-radius: 8px; font-size: 13px; margin-bottom: 12px; line-height: 1.5; }

/* 表格导入对话框 */
.import-tabs :deep(.el-tabs__content) { min-height: 320px; }
.excel-import { display: flex; flex-direction: column; gap: 14px; }
.import-upload-area {
  border: 2px dashed #cbd5e1; border-radius: 12px; padding: 28px 16px; cursor: pointer;
  background: #f8fafc; display: flex; justify-content: center; text-align: center; transition: all 0.2s;
}
.import-upload-area:hover { border-color: #3b82f6; background: #eff6ff; }
.upload-text { margin-left: 14px; }
.upload-title { font-size: 15px; font-weight: 600; color: #1e293b; margin-bottom: 6px; }
.upload-tip { font-size: 12px; color: #64748b; line-height: 1.6; }

.file-info-bar {
  display: flex; align-items: center; gap: 12px; padding: 10px 14px;
  border-radius: 8px; background: #f1f5f9; border: 1px solid #e2e8f0; font-size: 13px; color: #334155;
}
.file-info-bar .size { color: #64748b; margin-right: auto; }

.parse-loading { display: flex; align-items: center; justify-content: center; gap: 10px; padding: 32px; color: #64748b; }

.parse-result { display: flex; flex-direction: column; gap: 12px; }
.parse-summary { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.parse-stats { margin-left: auto; color: #64748b; font-size: 13px; }
.module-switcher { display: inline-flex; align-items: center; gap: 8px; margin-left: 4px; font-size: 13px; color: #475569; }

.preview-title { font-size: 13px; font-weight: 600; color: #334155; margin: 4px 0 0; }
.preview-table .invalid-value { color: #dc2626; background: #fee2e2; border-radius: 4px; padding: 2px 4px; }

.unmapped-tip {
  margin-top: 4px; font-size: 12px; color: #92400e; background: #fffbeb;
  padding: 8px 12px; border-radius: 6px; border: 1px solid #fde68a;
}

/* ===== 批量分配 ===== */
.batch-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 4px 14px; gap: 16px; flex-wrap: wrap;
}
.batch-toolbar .bt-left, .batch-toolbar .bt-right {
  display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
}
.distribution-bar {
  display: grid; grid-auto-flow: column; grid-auto-columns: minmax(120px, 1fr);
  gap: 10px; margin-bottom: 14px;
}
.dist-card {
  border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px 12px;
  background: #f8fafc; transition: all .15s ease-in;
}
.dist-card.dist-full { border-color: #fbbf24; background: linear-gradient(135deg,#fffbeb,#fef9c3); box-shadow: 0 1px 3px rgba(251,191,36,.2); }
.dist-name { font-weight: 600; color: #0f172a; font-size: 14px; }
.dist-count { font-size: 18px; font-weight: 700; color: #2563eb; margin-top: 2px; }
.dist-extra { font-size: 12px; color: #64748b; margin-top: 2px; }
.batch-table-wrap { border-radius: 8px; overflow: hidden; border: 1px solid #e2e8f0; }
.lead-title { font-weight: 600; color: #0f172a; margin-bottom: 2px; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lead-company { color: #475569; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.avg-tag { color: #b45309; font-weight: 500; }
.batch-footer {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 4px 0; border-top: 1px dashed #e2e8f0; margin-top: 12px; flex-wrap: wrap; gap: 10px;
}
.batch-tip { color: #475569; font-size: 13px; }
.batch-tip .done-ok { color: #15803d; font-weight: 600; }
.batch-tip .done-err { color: #b91c1c; font-weight: 600; }
.fail-list { margin-top: 10px; }
.muted { color: #94a3b8; font-size: 12px; }
.text-danger { color: #b91c1c !important; font-weight: 500; }
.row-invalid, .el-table .row-invalid td { background: #fef2f2 !important; }
.is-invalid .el-select__wrapper {
  border: 1px solid #f87171 !important;
  box-shadow: 0 0 0 2px rgba(248,113,113,.15);
  background: #fff5f5;
}
</style>
