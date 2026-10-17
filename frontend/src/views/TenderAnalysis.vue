<template>
  <div class="tender-page">
    <div class="page-header">
      <div class="header-title">
        <span class="title-icon">📑</span>
        <div>
          <h2>招标文件研判</h2>
          <p>上传竞争性磋商/招标文件，AI 结合研究院能力进行综合研判与风险识别</p>
        </div>
      </div>
      <el-upload
        :show-file-list="false"
        :http-request="doUpload"
        :accept="'.pdf,.docx,.doc,.xls,.xlsx,.txt'"
      >
        <el-button type="primary" :loading="uploading">
          <span style="margin-right: 4px;">⬆</span> 上传招标文件
        </el-button>
      </el-upload>
    </div>

    <div class="tips-card">
      支持格式：PDF（文字版）、Word、Excel、TXT，20MB 以内。上传后点击"AI研判"生成综合分析报告（含项目概况、资格符合性、能力匹配、评分策略、风险点、投标建议），研判约需 1-3 分钟。
    </div>

    <div class="table-card">
      <el-table :data="list" v-loading="loading" stripe>
        <el-table-column prop="filename" label="文件名" min-width="260" show-overflow-tooltip />
        <el-table-column label="大小" width="95">
          <template #default="{ row }">{{ fmtSize(row.filesize) }}</template>
        </el-table-column>
        <el-table-column label="文本长度" width="95" align="center">
          <template #default="{ row }">{{ row.text_len ? row.text_len.toLocaleString() : '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusMeta[row.status]?.type || 'info'" size="small" effect="light">
              {{ statusMeta[row.status]?.label || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_by_name" label="上传人" width="100" />
        <el-table-column prop="created_at" label="上传时间" width="165">
          <template #default="{ row }">{{ (row.created_at || '').slice(0, 16) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button
              link type="primary" :disabled="row.status === 'analyzing' || analyzingId === row.id"
              @click="doAnalyze(row)"
            >
              {{ analyzingId === row.id ? '研判中…' : (row.status === 'analyzed' ? '重新研判' : 'AI研判') }}
            </el-button>
            <el-button link type="success" v-if="row.status === 'analyzed'" @click="openReport(row)">查看报告</el-button>
            <el-button link type="danger" @click="doDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 研判报告弹窗 -->
    <el-dialog v-model="reportVisible" title="招标文件研判报告" width="860px" top="4vh" class="report-dialog">
      <div v-if="report" class="report">
        <!-- 结论横幅 -->
        <div class="conclusion-banner" :class="conclusionClass(report.conclusion?.recommendation)">
          <div class="c-left">
            <div class="c-label">综合研判结论</div>
            <div class="c-value">{{ report.conclusion?.recommendation || '-' }}</div>
          </div>
          <div class="c-score">
            <div class="c-label">可行性评分</div>
            <div class="c-value">{{ report.conclusion?.feasibility_score ?? '-' }}<span class="score-unit">/100</span></div>
          </div>
          <div class="c-reason">{{ report.conclusion?.reason }}</div>
        </div>

        <!-- 项目概况 -->
        <div class="report-block">
          <div class="block-title">📋 项目概况</div>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="项目名称" :span="2">{{ po.project_name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="采购人">{{ po.purchaser || '-' }}</el-descriptions-item>
            <el-descriptions-item label="采购方式">{{ po.procurement_method || '-' }}</el-descriptions-item>
            <el-descriptions-item label="预算金额">{{ po.budget || '未提供' }}</el-descriptions-item>
            <el-descriptions-item label="项目地点">{{ po.location || '-' }}</el-descriptions-item>
            <el-descriptions-item label="递交截止">{{ po.response_deadline || '-' }}</el-descriptions-item>
            <el-descriptions-item label="服务期/工期">{{ po.service_period || '-' }}</el-descriptions-item>
          </el-descriptions>
        </div>

        <!-- 资格要求 -->
        <div class="report-block">
          <div class="block-title">🧾 资格要求与符合性</div>
          <div v-if="report.qualification_check" class="check-note">{{ report.qualification_check }}</div>
          <ul class="plain-list">
            <li v-for="(q, i) in report.qualification_requirements || []" :key="'q'+i">{{ q }}</li>
          </ul>
          <div v-if="!(report.qualification_requirements || []).length" class="empty">未识别到资格要求</div>
        </div>

        <!-- 能力匹配 -->
        <div class="report-block">
          <div class="block-title">🎯 能力匹配</div>
          <div class="match-grid">
            <div class="match-col">
              <div class="match-head matched-head">我方可覆盖</div>
              <ul class="plain-list">
                <li v-for="(m, i) in report.capability_match?.matched || []" :key="'m'+i" class="ok">{{ m }}</li>
              </ul>
              <div v-if="!(report.capability_match?.matched || []).length" class="empty">无</div>
            </div>
            <div class="match-col">
              <div class="match-head missing-head">缺失/存疑</div>
              <ul class="plain-list">
                <li v-for="(m, i) in report.capability_match?.missing || []" :key="'x'+i" class="bad">{{ m }}</li>
              </ul>
              <div v-if="!(report.capability_match?.missing || []).length" class="empty">无</div>
            </div>
          </div>
          <div v-if="report.capability_match?.summary" class="match-summary">{{ report.capability_match.summary }}</div>
        </div>

        <!-- 评分要点 -->
        <div class="report-block" v-if="(report.scoring_highlights || []).length">
          <div class="block-title">🏅 评分要点与得分策略</div>
          <el-table :data="report.scoring_highlights" size="small" border>
            <el-table-column prop="item" label="评分项" min-width="160" />
            <el-table-column prop="weight" label="分值" width="90" />
            <el-table-column prop="strategy" label="得分策略" min-width="260" />
          </el-table>
        </div>

        <!-- 完整评分表 -->
        <div class="report-block" v-if="(report.scoring_detail || []).length">
          <div class="block-title">📋 完整评分表</div>
          <div v-for="(cat, ci) in report.scoring_detail" :key="'sd'+ci" class="scoring-cat">
            <div class="scoring-cat-head">
              <span class="scoring-cat-name">{{ cat.category }}</span>
              <span class="scoring-cat-score">{{ cat.max_score }} 分</span>
            </div>
            <el-table :data="cat.sub_items || []" size="small" border class="score-table">
              <el-table-column prop="name" label="子项" min-width="180" />
              <el-table-column prop="max_score" label="满分" width="70" align="center" />
              <el-table-column prop="criteria" label="评分细则" min-width="300" />
            </el-table>
          </div>
        </div>

        <!-- 得分失分分析 -->
        <div class="report-block" v-if="report.scoring_analysis">
          <div class="block-title">📊 得分失分预估</div>
          <!-- 得分总览 -->
          <div class="score-overview">
            <div class="score-bar-wrap">
              <div class="score-bar" :style="{ width: scorePercent + '%' }"></div>
            </div>
            <div class="score-numbers">
              <span class="score-est">{{ report.scoring_analysis.est_total_score || 0 }}</span>
              <span class="score-sep">/</span>
              <span class="score-max">{{ report.scoring_analysis.total_max_score || 0 }}</span>
              <span class="score-unit">分</span>
            </div>
          </div>
          <!-- 得分项 -->
          <div class="req-sub"><b>🟢 得分项</b></div>
          <el-table :data="report.scoring_analysis.score_items || []" size="small" border class="score-table">
            <el-table-column prop="item" label="评分项" min-width="150" />
            <el-table-column prop="max_score" label="满分" width="70" align="center" />
            <el-table-column prop="est_score" label="预估得分" width="90" align="center">
              <template #default="{ row }">
                <span :class="row.est_score >= row.max_score * 0.8 ? 'score-cell-good' : (row.est_score >= row.max_score * 0.5 ? 'score-cell-mid' : 'score-cell-bad')">
                  {{ row.est_score }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="confidence" label="把握" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="confType(row.confidence)" size="small" effect="plain">{{ confLabel(row.confidence) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="basis" label="得分依据" min-width="220" />
          </el-table>
          <!-- 失分项 -->
          <div class="req-sub" v-if="(report.scoring_analysis.loss_items || []).length"><b>🔴 失分项</b></div>
          <el-table v-if="(report.scoring_analysis.loss_items || []).length" :data="report.scoring_analysis.loss_items" size="small" border class="score-table">
            <el-table-column prop="item" label="失分项" min-width="150" />
            <el-table-column prop="est_loss" label="预估失分" width="90" align="center">
              <template #default="{ row }">
                <span class="score-cell-bad">-{{ row.est_loss }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="reason" label="失分原因" min-width="200" />
            <el-table-column prop="mitigation" label="减损措施" min-width="200" />
          </el-table>
          <div v-if="report.scoring_analysis.summary" class="match-summary">{{ report.scoring_analysis.summary }}</div>
        </div>

        <!-- 建议报价 -->
        <div class="report-block" v-if="report.recommended_price">
          <div class="block-title">💰 建议报价</div>
          <div class="price-main">
            <div class="price-amount">
              <span class="price-num">{{ formatPrice(report.recommended_price.price) }}</span>
              <span class="price-unit">元</span>
            </div>
            <div class="price-range" v-if="report.recommended_price.price_range_low">
              合理区间：{{ formatPrice(report.recommended_price.price_range_low) }} ~ {{ formatPrice(report.recommended_price.price_range_high) }} 元
            </div>
          </div>
          <el-descriptions :column="1" border size="small" class="price-desc">
            <el-descriptions-item label="报价依据">{{ report.recommended_price.basis }}</el-descriptions-item>
            <el-descriptions-item label="报价策略">{{ report.recommended_price.strategy }}</el-descriptions-item>
            <el-descriptions-item label="预估价格分">
              <span class="score-cell-good">{{ report.recommended_price.price_score_est || 0 }}</span>
              / {{ report.recommended_price.price_score_max || 0 }} 分
            </el-descriptions-item>
          </el-descriptions>
        </div>

        <!-- 关键需求 -->
        <div class="report-block">
          <div class="block-title">📌 关键要求</div>
          <div class="req-sub"><b>技术要求</b></div>
          <ul class="plain-list">
            <li v-for="(t, i) in report.key_requirements?.technical || []" :key="'t'+i">{{ t }}</li>
          </ul>
          <div class="req-sub"><b>商务要求</b></div>
          <ul class="plain-list">
            <li v-for="(c, i) in report.key_requirements?.commercial || []" :key="'c'+i">{{ c }}</li>
          </ul>
        </div>

        <!-- 风险点 -->
        <div class="report-block">
          <div class="block-title">⚠️ 风险点（{{ (report.risks || []).length }}）</div>
          <div v-for="(r, i) in report.risks || []" :key="'r'+i" class="risk-item" :class="'risk-' + r.severity">
            <div class="risk-head">
              <el-tag :type="riskType(r.severity)" size="small" effect="dark">{{ riskSeverity(r.severity) }}</el-tag>
              <el-tag size="small" effect="plain">{{ r.category }}</el-tag>
              <span class="risk-title">{{ r.description }}</span>
            </div>
            <div class="risk-suggest"><b>应对：</b>{{ r.suggestion }}</div>
          </div>
          <div v-if="!(report.risks || []).length" class="empty">未识别到风险</div>
        </div>

        <!-- 研判依据与数据来源 -->
        <div class="report-block" v-if="report._sources">
          <div class="block-title">📚 研判依据与数据来源（可追溯）</div>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="招标文件文本">{{ report._sources.text_mode }}</el-descriptions-item>
            <el-descriptions-item label="反馈修订轮次">{{ report._sources.feedback_rounds || 0 }} 轮</el-descriptions-item>
            <el-descriptions-item label="企业资质">注入 {{ report._sources.company_qual_count || 0 }} 项有效证书（资质管理模块）</el-descriptions-item>
            <el-descriptions-item label="人员资质">注入 {{ report._sources.personnel_qual_count || 0 }} 条有效人员资质（资质管理模块）</el-descriptions-item>
            <el-descriptions-item label="能力标签">注入 {{ report._sources.capability_count || 0 }} 个业务标签（标签与能力库）</el-descriptions-item>
            <el-descriptions-item label="规则命中能力">
              <template v-if="(report._sources.matched_capabilities || []).length">
                <el-tag v-for="m in report._sources.matched_capabilities" :key="m" size="small" type="success" effect="plain" class="src-tag">{{ m }}</el-tag>
              </template>
              <span v-else>无</span>
            </el-descriptions-item>
            <el-descriptions-item label="知识库命中" :span="2">
              <template v-if="(report._sources.kb_hits || []).length">
                <el-tag v-for="k in report._sources.kb_hits" :key="k" size="small" type="info" effect="plain" class="src-tag">《{{ k }}》</el-tag>
              </template>
              <span v-else>本次未命中相关知识库文档</span>
            </el-descriptions-item>
          </el-descriptions>
          <div class="src-note">报告中关键判断末尾的“（依据：…）”标注分别对应：招标文件原文 / 资质管理-证书 / 业务标签-能力 / 知识库-文档 / 综合推断。</div>
        </div>

        <!-- 对话式反馈 -->
        <div class="report-block chat-block">
          <div class="block-title">💬 反馈修订（补充信息后 AI 自动更新报告）</div>
          <div class="chat-history" v-if="feedbacks.length">
            <div v-for="f in feedbacks" :key="'fb'+f.id" class="chat-msg" :class="f.role">
              <div class="chat-meta">
                <b>{{ f.role === 'user' ? (f.created_by_name || '我方') : 'AI研判' }}</b>
                <span>{{ f.created_at }}</span>
              </div>
              <div class="chat-bubble">{{ f.content }}</div>
            </div>
          </div>
          <div v-else class="chat-empty">可输入补充信息，如“我们承担过霍山遥感监测项目”“报价不能超过130万”，AI 将据此更新上方报告</div>
          <div class="chat-input-row">
            <el-input
              v-model="feedbackText"
              type="textarea"
              :rows="2"
              maxlength="2000"
              show-word-limit
              placeholder="输入补充信息或修正意见，回车提交（Shift+回车换行）"
              :disabled="refining"
              @keydown.enter.exact.prevent="submitFeedback"
            />
            <el-button type="primary" :loading="refining" :disabled="!feedbackText.trim()" @click="submitFeedback">
              {{ refining ? '更新中…' : '提交' }}
            </el-button>
          </div>
          <div v-if="refining" class="chat-refining">AI 正在根据反馈更新研判报告，约需 1-2 分钟…</div>
        </div>

        <!-- 原文预览 -->
        <div class="report-block">
          <div class="block-title">📄 文本预览（前800字）</div>
          <div class="text-preview">{{ detail?.text_preview || '' }}…</div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const list = ref([])
const loading = ref(false)
const uploading = ref(false)
const analyzingId = ref(null)

const statusMeta = {
  uploaded:      { label: '待研判',   type: 'info' },
  analyzing:     { label: '研判中',   type: 'warning' },
  analyzed:      { label: '已研判',   type: 'success' },
  failed:        { label: '研判失败', type: 'danger' },
}

const fmtSize = (s) => {
  if (!s && s !== 0) return '-'
  if (s < 1024) return s + ' B'
  if (s < 1048576) return (s / 1024).toFixed(1) + ' KB'
  return (s / 1048576).toFixed(2) + ' MB'
}

const fetchList = async () => {
  loading.value = true
  try {
    const res = await api.get('/tender-analysis')
    if (res.code === 200) list.value = res.data || []
  } finally {
    loading.value = false
  }
}

// ==================== 上传 ====================

const doUpload = async (opts) => {
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', opts.file)
    const res = await api.post('/tender-analysis/upload', fd)
    if (res.code === 200) {
      ElMessage.success(res.message)
      fetchList()
    } else {
      ElMessage.error(res.message || '上传失败')
    }
  } finally {
    uploading.value = false
  }
}

// ==================== 研判 ====================

const doAnalyze = async (row) => {
  analyzingId.value = row.id
  ElMessage.info('AI 研判中，约需 1-3 分钟，请勿关闭页面…')
  try {
    const res = await api.longPost(`/tender-analysis/${row.id}/analyze`)
    if (res.code === 200) {
      ElMessage.success('研判完成')
      fetchList()
      openReport(row)
    } else {
      ElMessage.error(res.message || '研判失败')
      fetchList()
    }
  } finally {
    analyzingId.value = null
  }
}

const doDelete = async (row) => {
  try {
    await ElMessageBox.confirm(`确认删除「${row.filename}」？`, '删除确认', { type: 'warning' })
  } catch { return }
  const res = await api.delete(`/tender-analysis/${row.id}`)
  if (res.code === 200) {
    ElMessage.success('已删除')
    fetchList()
  }
}

// ==================== 报告展示 ====================

const reportVisible = ref(false)
const report = ref(null)
const detail = ref(null)

const po = computed(() => report.value?.project_overview || {})

const openReport = async (row) => {
  const res = await api.get(`/tender-analysis/${row.id}`)
  if (res.code === 200) {
    detail.value = res.data
    report.value = res.data.analysis
    if (!report.value) {
      ElMessage.warning('暂无研判结果')
      return
    }
    reportVisible.value = true
    fetchFeedbacks()
  }
}

// ==================== 对话式反馈 ====================

const feedbacks = ref([])
const feedbackText = ref('')
const refining = ref(false)

const fetchFeedbacks = async () => {
  if (!detail.value) return
  const res = await api.get(`/tender-analysis/${detail.value.id}/feedbacks`)
  if (res.code === 200) feedbacks.value = res.data || []
}

const submitFeedback = async () => {
  const text = feedbackText.value.trim()
  if (!text || refining.value || !detail.value) return
  refining.value = true
  try {
    const res = await api.longPost(`/tender-analysis/${detail.value.id}/refine`, { feedback: text })
    if (res.code === 200) {
      report.value = res.data
      feedbackText.value = ''
      ElMessage.success('研判报告已更新')
      fetchFeedbacks()
      fetchList()
    } else {
      ElMessage.error(res.message || '更新失败')
    }
  } finally {
    refining.value = false
  }
}

const riskType = (s) => ({ high: 'danger', medium: 'warning', low: 'info' }[s] || 'info')
const riskSeverity = (s) => ({ high: '高风险', medium: '中风险', low: '低风险' }[s] || s)

const scorePercent = computed(() => {
  const sa = report.value?.scoring_analysis
  if (!sa) return 0
  const max = sa.total_max_score || 0
  const est = sa.est_total_score || 0
  return max > 0 ? Math.min(100, Math.round(est / max * 100)) : 0
})
const confType = (c) => ({ high: 'success', medium: 'warning', low: 'info' }[c] || 'info')
const confLabel = (c) => ({ high: '高', medium: '中', low: '低' }[c] || c)
const formatPrice = (v) => {
  if (!v && v !== 0) return '—'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
const conclusionClass = (rec) => {
  if (rec && rec.includes('不建议')) return 'c-red'
  if (rec && rec.includes('谨慎')) return 'c-orange'
  return 'c-green'
}

fetchList()
</script>

<style scoped>
.tender-page {
  padding: 4px;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #fff;
  border-radius: 10px;
  padding: 18px 22px;
  margin-bottom: 14px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}
.header-title {
  display: flex;
  align-items: center;
  gap: 14px;
}
.title-icon { font-size: 32px; }
.header-title h2 { margin: 0; font-size: 20px; color: #1f2937; }
.header-title p { margin: 4px 0 0; font-size: 13px; color: #9ca3af; }
.tips-card {
  background: #ecf8f6;
  border: 1px solid #bfe8e0;
  color: #0f766e;
  font-size: 13px;
  border-radius: 8px;
  padding: 10px 16px;
  margin-bottom: 14px;
  line-height: 1.6;
}
.table-card {
  background: #fff;
  border-radius: 10px;
  padding: 18px 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

/* 报告 */
.report { display: flex; flex-direction: column; gap: 16px; }
.conclusion-banner {
  display: flex;
  align-items: center;
  gap: 22px;
  border-radius: 10px;
  padding: 14px 20px;
  color: #fff;
}
.c-green { background: linear-gradient(135deg, #0d9488, #10b981); }
.c-orange { background: linear-gradient(135deg, #d97706, #f59e0b); }
.c-red { background: linear-gradient(135deg, #dc2626, #ef4444); }
.c-label { font-size: 12px; opacity: 0.85; }
.c-value { font-size: 22px; font-weight: 700; margin-top: 2px; }
.score-unit { font-size: 13px; font-weight: 400; opacity: 0.85; margin-left: 2px; }
.c-reason {
  flex: 1;
  font-size: 13px;
  line-height: 1.7;
  background: rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  padding: 10px 14px;
}
.report-block {
  border: 1px solid #eef0f3;
  border-radius: 10px;
  padding: 14px 18px;
  background: #fafbfc;
}
.block-title { font-weight: 600; font-size: 14px; color: #374151; margin-bottom: 10px; }
.plain-list { margin: 0; padding-left: 20px; }
.plain-list li { font-size: 13px; color: #4b5563; line-height: 1.8; }
.plain-list li.ok { color: #0f766e; }
.plain-list li.bad { color: #b91c1c; }
.check-note {
  font-size: 13px;
  color: #1d4ed8;
  background: #eff6ff;
  border-radius: 6px;
  padding: 8px 12px;
  margin-bottom: 8px;
  line-height: 1.7;
}
.empty { font-size: 13px; color: #c0c4cc; }
.match-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.match-col {
  border: 1px solid #eef0f3;
  border-radius: 8px;
  padding: 10px 12px;
  background: #fff;
}
.match-head { font-size: 13px; font-weight: 600; padding-bottom: 6px; }
.matched-head { color: #0f766e; }
.missing-head { color: #b91c1c; }
.match-summary {
  margin-top: 10px;
  font-size: 13px;
  color: #4b5563;
  background: #fff;
  border: 1px dashed #d1d5db;
  border-radius: 6px;
  padding: 8px 12px;
  line-height: 1.7;
}
.req-sub { font-size: 13px; color: #6b7280; margin: 6px 0 4px; }

.score-overview { display: flex; align-items: center; gap: 16px; margin: 10px 0 16px; }
.score-bar-wrap { flex: 1; height: 22px; background: #e5e7eb; border-radius: 11px; overflow: hidden; }
.score-bar { height: 100%; background: linear-gradient(90deg, #10b981, #34d399); border-radius: 11px; transition: width 0.6s ease; }
.score-numbers { display: flex; align-items: baseline; gap: 2px; }
.score-est { font-size: 28px; font-weight: 700; color: #059669; }
.score-sep { font-size: 20px; color: #9ca3af; margin: 0 2px; }
.score-max { font-size: 20px; color: #6b7280; }
.score-unit { font-size: 14px; color: #6b7280; margin-left: 4px; }
.score-table { margin: 4px 0 10px; }
.score-cell-good { font-weight: 700; color: #059669; }
.score-cell-mid { font-weight: 700; color: #d97706; }
.score-cell-bad { font-weight: 700; color: #dc2626; }

.scoring-cat { margin-bottom: 14px; }
.scoring-cat-head { display: flex; align-items: center; justify-content: space-between; margin: 8px 0 6px; padding: 4px 10px; background: #f3f4f6; border-radius: 6px; }
.scoring-cat-name { font-weight: 600; font-size: 14px; color: #374151; }
.scoring-cat-score { font-weight: 700; color: #6b7280; font-size: 13px; }

.price-main { display: flex; align-items: baseline; gap: 20px; margin: 10px 0 14px; padding: 14px 20px; background: linear-gradient(135deg, #ecfdf5, #d1fae5); border-radius: 10px; }
.price-amount { display: flex; align-items: baseline; gap: 4px; }
.price-num { font-size: 32px; font-weight: 700; color: #059669; }
.price-unit { font-size: 16px; color: #059669; }
.price-range { font-size: 13px; color: #6b7280; }
.price-desc { margin-top: 4px; }

.chat-block { background: #f8fafc; border: 1px solid #e2e8f0; }
.chat-history { max-height: 300px; overflow-y: auto; margin-bottom: 10px; }
.chat-msg { margin-bottom: 10px; }
.chat-meta { font-size: 12px; color: #9ca3af; margin-bottom: 3px; display: flex; gap: 8px; }
.chat-msg.user .chat-meta { justify-content: flex-end; }
.chat-bubble { display: inline-block; max-width: 85%; padding: 8px 12px; border-radius: 10px; font-size: 13px; line-height: 1.6; white-space: pre-wrap; }
.chat-msg.user { text-align: right; }
.chat-msg.user .chat-bubble { background: #dbeafe; color: #1e40af; text-align: left; }
.chat-msg.assistant .chat-bubble { background: #ecfdf5; color: #065f46; }
.chat-empty { font-size: 12px; color: #9ca3af; padding: 8px 0; line-height: 1.8; }
.chat-input-row { display: flex; gap: 8px; align-items: flex-end; }
.chat-input-row .el-button { flex-shrink: 0; }
.chat-refining { font-size: 12px; color: #d97706; margin-top: 6px; }

.src-tag { margin: 2px 4px 2px 0; }
.src-note { font-size: 12px; color: #9ca3af; margin-top: 8px; line-height: 1.6; }

.risk-item {
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 8px;
  border-left: 4px solid #d1d5db;
  background: #fff;
}
.risk-high { border-left-color: #dc2626; background: #fef2f2; }
.risk-medium { border-left-color: #d97706; background: #fffbeb; }
.risk-low { border-left-color: #6b7280; background: #f9fafb; }
.risk-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.risk-title { font-size: 13px; color: #374151; line-height: 1.6; }
.risk-suggest { font-size: 13px; color: #6b7280; margin-top: 6px; line-height: 1.6; }
.text-preview {
  font-size: 12px;
  color: #6b7280;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 180px;
  overflow-y: auto;
  background: #fff;
  border: 1px solid #eef0f3;
  border-radius: 6px;
  padding: 10px 12px;
  line-height: 1.7;
}
</style>
