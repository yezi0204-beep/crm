<template>
  <div class="leads-container">
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">📡 智能线索管理</h2>
        <p class="page-desc">五大能力域（招投标监控/电商商机/企业客源/竞品情报/舆情痛点）多渠道自动抓取 → AI 评估意向 → 精准分配销售</p>
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
      <div class="stat-card stat-rejected">
        <div class="stat-icon">🚫</div>
        <div class="stat-body">
          <div class="stat-label">已拒绝</div>
          <div class="stat-value">{{ stats.rejected || 0 }}</div>
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
            <el-option label="已拒绝" value="rejected" />
          </el-select>
          <el-select v-model="filterSource" placeholder="全部来源" clearable @change="fetchLeads" style="width:180px">
            <el-option v-for="s in sources" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
          <el-input v-model="keyword" placeholder="搜索商机名称/公司/联系人/备注..." clearable @clear="fetchLeads" @keyup.enter="fetchLeads" style="width:280px">
            <template #append><el-button @click="fetchLeads">搜索</el-button></template>
          </el-input>
          <div class="action-group">
            <el-button type="warning" @click="handleBatchEvaluate" :loading="evaluating" :disabled="!pendingCount">
              <span>🧠</span><span>批量AI评估</span>
            </el-button>
            <el-button @click="scrapeAll" :loading="scraping"><span>🌐</span><span>抓取全部源</span></el-button>
          </div>
        </div>

        <el-table :data="leads" v-loading="loading" stripe class="leads-table">
          <el-table-column type="index" label="#" width="50" />
          <el-table-column label="能力域" width="120">
            <template #default="{ row }">
              <span v-if="row.category" :class="['cat-badge', 'cb-' + categoryKey(row.category)]" :title="row.category">
                {{ categoryIcon(row.category) }} {{ row.category }}
              </span>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="商机名称" min-width="220">
            <template #default="{ row }">
              <div class="opp-cell">
                <div class="opp-name">{{ row.opportunity_name || row.company || '—' }}</div>
                <div class="company-sub">🏢 {{ row.company }}<span v-if="row.contact_name"> · 👤 {{ row.contact_name }}</span></div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="行业/区域" width="130">
            <template #default="{ row }">
              <div>{{ row.industry || '—' }}</div>
              <div class="muted">{{ row.region || '—' }}</div>
            </template>
          </el-table-column>
          <el-table-column label="来源" width="110">
            <template #default="{ row }">
              <span class="source-tag">{{ row.source || row.source_name || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="获取链接" width="100" align="center">
            <template #default="{ row }">
              <a v-if="row.link" :href="row.link" target="_blank" rel="noopener" class="link-btn" title="打开获取链接">
                <span>🔗</span><span>查看</span>
              </a>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="意向分" width="100" align="center">
            <template #default="{ row }">
              <span v-if="row.intent_score !== null && row.intent_score !== undefined"
                    :class="['score-badge', scoreClass(row.intent_score)]">{{ row.intent_score }}</span>
              <span v-else class="muted">未评估</span>
            </template>
          </el-table-column>
          <el-table-column label="评估理由" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.eval_reason" class="reason-text">{{ row.eval_reason }}</span>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="推荐分配" width="110">
            <template #default="{ row }">
              <span v-if="row.assigned_name" class="assignee">{{ row.assigned_name }}</span>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <span :class="['status-badge', 'st-' + row.status]">{{ statusLabel(row.status) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="抓取时间" width="150">
            <template #default="{ row }">{{ formatDate(row.scraped_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="240" fixed="right">
            <template #default="{ row }">
              <el-button text size="small" @click="handleEvaluate(row)" v-if="row.status === 'pending'">评估</el-button>
              <el-button text size="small" type="primary" @click="openAssignDialog(row)" v-if="row.status === 'evaluated'">分配</el-button>
              <el-button text size="small" type="danger" @click="handleReject(row)" v-if="['pending','evaluated'].includes(row.status)">拒绝</el-button>
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

      <!-- ==================== 线索源管理 ==================== -->
      <el-tab-pane label="线索源管理" name="sources">
        <div class="filter-bar">
          <div class="source-tip">配置多渠道线索源，系统按「抓取间隔」自动抓取；也可手动触发单个源抓取</div>
          <el-button type="primary" @click="openSourceDialog()"><span>✚</span><span>新增线索源</span></el-button>
        </div>

        <el-table :data="sources" v-loading="loadingSources" stripe>
          <el-table-column label="名称" min-width="160">
            <template #default="{ row }"><span class="src-name">{{ row.name }}</span></template>
          </el-table-column>
          <el-table-column label="能力域" width="120">
            <template #default="{ row }">
              <span v-if="row.category" :class="['cat-badge', 'cb-' + categoryKey(row.category)]">
                {{ categoryIcon(row.category) }} {{ row.category }}
              </span>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="100" align="center">
            <template #default="{ row }">
              <span :class="['type-badge', 'tp-' + row.source_type]">{{ typeLabel(row.source_type) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="URL/配置" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <div v-if="row.url" class="mono">{{ row.url }}</div>
              <div v-else class="muted">（无URL，示例/手动）</div>
              <div class="muted mono" v-if="row.config">{{ row.config }}</div>
            </template>
          </el-table-column>
          <el-table-column label="关键词" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.keywords">{{ row.keywords }}</span><span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="行业/区域" width="140">
            <template #default="{ row }">
              <div>{{ row.industry || '—' }}</div><div class="muted">{{ row.region || '—' }}</div>
            </template>
          </el-table-column>
          <el-table-column label="间隔(h)" width="90" align="center" prop="interval_hours" />
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-switch :model-value="!!row.enabled" @change="(v) => toggleSource(row, v)" />
            </template>
          </el-table-column>
          <el-table-column label="已抓取" width="80" align="center" prop="lead_count" />
          <el-table-column label="上次抓取" width="150">
            <template #default="{ row }">{{ formatDate(row.last_scraped_at) || '从未' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="240" fixed="right">
            <template #default="{ row }">
              <el-button text size="small" type="success" @click="scrapeOne(row)" :loading="row._scraping">抓取</el-button>
              <el-button text size="small" @click="openSourceDialog(row)">编辑</el-button>
              <el-button text size="small" type="danger" @click="deleteSource(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 分配对话框 -->
    <el-dialog v-model="assignVisible" title="分配线索" width="500px">
      <div v-if="currentLead" class="assign-content">
        <div class="assign-info">
          <div class="info-row opp-title" v-if="currentLead.opportunity_name"><span class="info-label">商机：</span>{{ currentLead.opportunity_name }}</div>
          <div class="info-row"><span class="info-label">公司：</span>{{ currentLead.company }}</div>
          <div class="info-row"><span class="info-label">意向分：</span>
            <span :class="['score-badge', scoreClass(currentLead.intent_score)]">{{ currentLead.intent_score }}</span>
          </div>
          <div class="info-row" v-if="currentLead.assigned_name"><span class="info-label">AI推荐：</span>{{ currentLead.assigned_name }}</div>
          <div class="info-row reason" v-if="currentLead.eval_reason"><span class="info-label">评估理由：</span>{{ currentLead.eval_reason }}</div>
        </div>
        <el-form label-width="90px" style="margin-top:16px">
          <el-form-item label="分配给">
            <el-select v-model="assignForm.assigned_to" placeholder="选择销售人员" filterable style="width:100%">
              <el-option v-for="s in salespeople" :key="s.username" :label="`${s.name}（当前${s.biz_count}单）`" :value="s.username" />
            </el-select>
          </el-form-item>
        </el-form>
        <div class="assign-tip">分配后将自动创建客户并归属该销售，线索标记为已分配</div>
      </div>
      <template #footer>
        <el-button @click="assignVisible = false">取消</el-button>
        <el-button type="primary" @click="handleAssign" :loading="assigning">确认分配</el-button>
      </template>
    </el-dialog>

    <!-- 线索详情对话框 -->
    <el-dialog v-model="detailVisible" title="线索详情" width="600px">
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
          <div class="info-row"><span class="info-label">状态：</span>
            <span :class="['status-badge', 'st-' + currentLead.status]">{{ statusLabel(currentLead.status) }}</span>
          </div>
        </div>
        <div class="detail-section" v-if="currentLead.raw_data">
          <div class="section-title">原始数据</div>
          <pre class="raw-data">{{ formatRaw(currentLead.raw_data) }}</pre>
        </div>
      </div>
    </el-dialog>

    <!-- 线索源新建/编辑对话框 -->
    <el-dialog v-model="sourceVisible" :title="sourceForm.id ? '编辑线索源' : '新增线索源'" width="640px">
      <el-form :model="sourceForm" label-width="100px">
        <el-form-item label="名称" required>
          <el-input v-model="sourceForm.name" placeholder="如：政府采购招标信息" />
        </el-form-item>
        <el-form-item label="能力域" required>
          <el-select v-model="sourceForm.category" placeholder="选择能力域类别" style="width:100%">
            <el-option v-for="c in categories" :key="c.value" :label="c.icon + ' ' + c.label" :value="c.value" />
          </el-select>
          <div class="form-tip">{{ categoryDesc(sourceForm.category) }}</div>
        </el-form-item>
        <el-form-item label="抓取方式" required>
          <el-select v-model="sourceForm.source_type" style="width:100%">
            <el-option label="🤖 AI智能体搜索" value="ai_search" />
            <el-option label="RSS订阅" value="rss" />
            <el-option label="API接口" value="api" />
            <el-option label="HTML网页" value="html" />
            <el-option label="手动导入" value="manual" />
          </el-select>
          <div class="form-tip" v-if="sourceForm.source_type === 'ai_search'">
            🤖 AI 智能体搜索：通过 DuckDuckGo 搜索引擎主动搜集互联网数据，再用大语言模型（LLM）从搜索结果中提取结构化商机线索。无需配置 URL，仅需网络即可工作。LLM 不可用时降级为直接提取搜索结果（标题/链接/摘要）。
          </div>
          <div class="form-tip" v-else-if="sourceForm.source_type === 'html'">
            HTML 源按能力域分发抓取器：招投标监控解析公告、电商商机解析榜单、企业客源解析企业信息、竞品情报解析产品价格、舆情痛点解析帖子痛点。动态页面需在配置中设置 {"dynamic": true}（需安装 playwright）
          </div>
        </el-form-item>
        <el-form-item label="URL" v-if="['rss','api','html'].includes(sourceForm.source_type)">
          <el-input v-model="sourceForm.url" placeholder="RSS订阅地址 / API接口URL / 网页URL" />
        </el-form-item>
        <el-form-item label="配置JSON">
          <el-input v-model="sourceForm.config" type="textarea" :rows="2"
                    :placeholder='sourceForm.source_type === "ai_search" ? "{\"max_items\":15,\"max_queries\":3} max_items=每条查询最多结果数，max_queries=最多搜索查询数" : "{\"max_items\":20,\"dynamic\":true} 留空使用默认值；HTML动态页面需设置dynamic:true"' />
        </el-form-item>
        <el-form-item label="关键词">
          <el-input v-model="sourceForm.keywords" placeholder="多个关键词用逗号分隔，命中才入库" />
        </el-form-item>
        <el-form-item label="行业">
          <el-input v-model="sourceForm.industry" placeholder="如：信息技术,航天,通信" />
        </el-form-item>
        <el-form-item label="区域">
          <el-input v-model="sourceForm.region" placeholder="如：全国" />
        </el-form-item>
        <el-form-item label="抓取间隔">
          <el-input-number v-model="sourceForm.interval_hours" :min="1" :max="168" /> <span class="muted">小时</span>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="sourceForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="sourceVisible = false">取消</el-button>
        <el-button type="primary" @click="saveSource">保存</el-button>
      </template>
    </el-dialog>

    <!-- 手动导入对话框 -->
    <el-dialog v-model="importVisible" title="手动导入线索" width="640px">
      <div class="import-tip">
        请输入 JSON 数组，每条线索包含 company(必填)/contact_name/phone/email/industry/region/source/remark 字段。
      </div>
      <el-input v-model="importText" type="textarea" :rows="12" placeholder='[{"company":"示例科技","contact_name":"张总","phone":"13800000000","industry":"信息技术","region":"全国","source":"手动导入","remark":"有采购需求"}]' />
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" @click="handleImport" :loading="importing">导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const activeTab = ref('queue')
const loading = ref(false)
const loadingSources = ref(false)
const evaluating = ref(false)
const scraping = ref(false)
const assigning = ref(false)
const importing = ref(false)

const leads = ref([])
const sources = ref([])
const salespeople = ref([])
const stats = ref({})
const categoryStats = ref({})
const avgScore = ref(0)
const enabledSources = ref(0)

const filterStatus = ref('')
const filterSource = ref('')
const filterCategory = ref('')
const keyword = ref('')

// 五大能力域定义
const categories = [
  { value: '招投标监控', label: '招投标监控', icon: '📋', desc: '定时抓取全国/省市招投标网站，通过关键词筛选最新标讯，第一时间跟进投标' },
  { value: '电商商机', label: '电商商机', icon: '🛒', desc: '批量抓取亚马逊/TikTok Shop/淘宝等平台商品销量、评论增长率及热搜词，分析"高需求低竞争"潜在爆款' },
  { value: '企业客源', label: '企业客源', icon: '🏢', desc: '从企业信用公示系统、黄页网站批量提取特定行业新注册企业、联系方式及高管信息' },
  { value: '竞品情报', label: '竞品情报', icon: '🎯', desc: '监控竞品官网价格变动、新产品上线动态、促销活动，抓取社媒负面评价优化营销' },
  { value: '舆情痛点', label: '舆情痛点', icon: '💡', desc: '抓取知乎/小红书/贴吧等垂直论坛用户吐槽，挖掘未被满足的需求痛点作为新功能商机' },
]
const categoryKeyMap = {
  '招投标监控': 'bidding', '电商商机': 'ecommerce', '企业客源': 'b2b',
  '竞品情报': 'competitor', '舆情痛点': 'forum'
}
const categoryIconMap = {
  '招投标监控': '📋', '电商商机': '🛒', '企业客源': '🏢',
  '竞品情报': '🎯', '舆情痛点': '💡'
}

const categoryKey = (c) => categoryKeyMap[c] || 'other'
const categoryIcon = (c) => categoryIconMap[c] || '📌'
const categoryDesc = (c) => {
  const found = categories.find(x => x.value === c)
  return found ? found.desc : '请选择能力域类别，系统按类别分发到对应抓取器'
}

const pendingCount = computed(() => stats.value.pending || 0)
const totalCount = computed(() => Object.values(stats.value).reduce((a, b) => a + (b || 0), 0))
const currentRaw = computed(() => {
  if (!currentLead.value?.raw_data) return {}
  try { return JSON.parse(currentLead.value.raw_data) } catch (e) { return {} }
})

const assignVisible = ref(false)
const detailVisible = ref(false)
const sourceVisible = ref(false)
const importVisible = ref(false)
const currentLead = ref(null)
const assignForm = ref({ assigned_to: '' })
const sourceForm = ref(defaultSourceForm())
const importText = ref('')

function defaultSourceForm() {
  return { id: null, name: '', source_type: 'ai_search', url: '', config: '', keywords: '',
           industry: '信息技术', region: '全国', interval_hours: 24, enabled: true, category: '招投标监控' }
}

const statusLabel = (s) => ({ pending: '待评估', evaluated: '已评估', imported: '已分配', rejected: '已拒绝' }[s] || s)
const typeLabel = (t) => ({ rss: 'RSS', api: 'API', html: 'HTML', ai_search: 'AI搜索', sample: '示例', manual: '手动' }[t] || t)

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

const formatDate = (s) => {
  if (!s) return ''
  return String(s).replace('T', ' ').substring(0, 16)
}

const formatRaw = (raw) => {
  try { return JSON.stringify(JSON.parse(raw), null, 2) } catch (e) { return raw }
}

const fetchLeads = async () => {
  loading.value = true
  try {
    const params = {}
    if (filterStatus.value) params.status = filterStatus.value
    if (filterSource.value) params.source_id = filterSource.value
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

const fetchSources = async () => {
  loadingSources.value = true
  try {
    const resp = await api.get('/leads/sources')
    if (resp.code === 200) sources.value = resp.data || []
    else ElMessage.error(resp.message)
  } catch (e) { ElMessage.error('加载线索源失败') }
  finally { loadingSources.value = false }
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
  await Promise.all([fetchLeads(), fetchSources(), fetchStats()])
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
      ElMessage.success(resp.message)
      assignVisible.value = false
      fetchLeads(); fetchStats()
    } else ElMessage.error(resp.message)
  } catch (e) { ElMessage.error('分配失败') }
  finally { assigning.value = false }
}

const handleReject = async (row) => {
  try {
    await ElMessageBox.confirm(`确定拒绝线索「${row.company}」？`, '提示', { type: 'warning' })
    const resp = await api.post(`/leads/${row.id}/reject`)
    if (resp.code === 200) { ElMessage.success('已拒绝'); fetchLeads(); fetchStats() }
    else ElMessage.error(resp.message)
  } catch (e) { /* cancelled */ }
}

const openDetail = (row) => { currentLead.value = row; detailVisible.value = true }

// ==================== 抓取 ====================
const scrapeOne = async (row) => {
  row._scraping = true
  try {
    const resp = await api.post(`/leads/sources/${row.id}/scrape`)
    if (resp.code === 200) {
      ElMessage.success(resp.message)
      fetchSources(); fetchLeads(); fetchStats()
    } else ElMessage.error(resp.message)
  } catch (e) { ElMessage.error('抓取失败') }
  finally { row._scraping = false }
}

const scrapeAll = async () => {
  scraping.value = true
  try {
    const resp = await api.post('/leads/scrape-all')
    if (resp.code === 200) {
      ElMessage.success(resp.message)
      if (resp.data?.details) {
        const errs = resp.data.details.filter(d => d.error)
        if (errs.length) ElMessage.warning(`${errs.length} 个源抓取异常`)
      }
      fetchSources(); fetchLeads(); fetchStats()
    } else ElMessage.error(resp.message)
  } catch (e) { ElMessage.error('批量抓取失败') }
  finally { scraping.value = false }
}

// ==================== 线索源 CRUD ====================
const openSourceDialog = (row) => {
  if (row) {
    sourceForm.value = { id: row.id, name: row.name, source_type: row.source_type, url: row.url || '',
                         config: row.config || '', keywords: row.keywords || '', industry: row.industry || '',
                         region: row.region || '', interval_hours: row.interval_hours, enabled: !!row.enabled,
                         category: row.category || '' }
  } else {
    sourceForm.value = defaultSourceForm()
  }
  sourceVisible.value = true
}

const saveSource = async () => {
  if (!sourceForm.value.name) { ElMessage.warning('请输入名称'); return }
  try {
    const payload = { ...sourceForm.value, enabled: sourceForm.value.enabled ? 1 : 0 }
    let resp
    if (payload.id) resp = await api.put(`/leads/sources/${payload.id}`, payload)
    else resp = await api.post('/leads/sources', payload)
    if (resp.code === 200) { ElMessage.success('保存成功'); sourceVisible.value = false; fetchSources(); fetchStats() }
    else ElMessage.error(resp.message)
  } catch (e) { ElMessage.error('保存失败') }
}

const toggleSource = async (row, enabled) => {
  try {
    const resp = await api.put(`/leads/sources/${row.id}`, { enabled: enabled ? 1 : 0 })
    if (resp.code === 200) { ElMessage.success(enabled ? '已启用' : '已停用'); fetchSources(); fetchStats() }
    else ElMessage.error(resp.message)
  } catch (e) { ElMessage.error('操作失败') }
}

const deleteSource = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除线索源「${row.name}」？关联的线索也将一并删除`, '提示', { type: 'warning' })
    const resp = await api.delete(`/leads/sources/${row.id}`)
    if (resp.code === 200) { ElMessage.success('删除成功'); fetchSources(); fetchLeads(); fetchStats() }
    else ElMessage.error(resp.message)
  } catch (e) { /* cancelled */ }
}

// ==================== 导入 ====================
const openImportDialog = () => { importText.value = ''; importVisible.value = true }

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

onMounted(() => { fetchData() })
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
.stat-rejected .stat-icon { background: #fee2e2; } .stat-rejected .stat-value { color: #dc2626; }
.stat-avg .stat-icon { background: #ede9fe; } .stat-avg .stat-value { color: #7c3aed; }
.stat-sources .stat-icon { background: #e0f2fe; } .stat-sources .stat-value { color: #0284c7; }
.stat-body { display: flex; flex-direction: column; }
.stat-label { font-size: 12px; color: #64748b; }
.stat-value { font-size: 22px; font-weight: 700; line-height: 1.2; }

.content-tabs { background: white; border-radius: 12px; padding: 16px; border: 1px solid #e2e8f0; }

.filter-bar { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.action-group { margin-left: auto; display: flex; gap: 8px; }
.source-tip { color: #64748b; font-size: 13px; margin-right: auto; }

.leads-table { width: 100%; }
.company-cell .company-name { font-weight: 600; color: #1e293b; }
.company-sub { font-size: 12px; color: #94a3b8; margin-top: 2px; }
.opp-cell .opp-name { font-weight: 600; color: #1e293b; font-size: 14px; line-height: 1.4; }
.opp-cell .company-sub { margin-top: 3px; }
.opp-title { font-size: 15px; font-weight: 600; color: #1e293b; margin-bottom: 8px !important; }
.link-btn { display: inline-flex; align-items: center; gap: 4px; color: #2563eb; text-decoration: none; font-size: 12px; word-break: break-all; }
.link-btn:hover { color: #1d4ed8; text-decoration: underline; }
.muted { color: #94a3b8; font-size: 12px; }
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
.cat-chip.cat-电商商机.active { background: #f59e0b; }
.cat-chip.cat-企业客源.active { background: #10b981; }
.cat-chip.cat-竞品情报.active { background: #ef4444; }
.cat-chip.cat-舆情痛点.active { background: #8b5cf6; }

/* 能力域徽标 */
.cat-badge { font-size: 11px; padding: 2px 8px; border-radius: 8px; font-weight: 500; white-space: nowrap; }
.cb-bidding { background: #dbeafe; color: #2563eb; }
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
.st-rejected { background: #fee2e2; color: #dc2626; }

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
.raw-data { background: #f8fafc; padding: 12px; border-radius: 8px; font-size: 12px; color: #475569; max-height: 200px; overflow: auto; white-space: pre-wrap; word-break: break-all; }

.import-tip { background: #fffbeb; border: 1px solid #fde68a; color: #92400e; padding: 10px 14px; border-radius: 8px; font-size: 13px; margin-bottom: 12px; line-height: 1.5; }
</style>
