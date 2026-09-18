<template>
  <div class="quarterly-assessment">
    <div class="page-header">
      <h2 class="page-title">应用中心季度考核</h2>
      <div class="header-actions">
        <el-select v-model="year" style="width: 110px; margin-right: 10px;" @change="loadAll">
          <el-option v-for="y in yearOptions" :key="y" :label="y + ' 年'" :value="y" />
        </el-select>
        <el-radio-group v-model="quarter" @change="loadAll">
          <el-radio-button :value="1">Q1（1-3月）</el-radio-button>
          <el-radio-button :value="2">Q2（4-6月）</el-radio-button>
          <el-radio-button :value="3">Q3（7-9月）</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <el-tabs v-model="activeTab">
      <!-- ===== Tab 1: 我的考核结果（只读） ===== -->
      <el-tab-pane label="我的考核结果" name="mine">
        <template v-if="mine.assessment">
          <el-alert
            v-if="mine.assessment.status === 'reviewed'"
            type="success" show-icon :closable="false" style="margin-bottom: 12px;"
            :title="`已核定：${mine.assessment.final_total} 分 / ${mine.assessment.grade} 级 / 系数 ${mine.assessment.coefficient}`"
            :description="mine.assessment.review_comment || ''"
          />
          <el-alert
            v-else
            type="info" show-icon :closable="false" style="margin-bottom: 12px;"
            title="考核表已导入，待绩效考核小组综合核定"
          />
          <div class="suggest-box">
            <div class="suggest-title">初步考核建议（大模型分析）</div>
            <div class="suggest-line">
              建议总分：<b>{{ mine.assessment.suggestion_total ?? '—' }}</b>　
              建议等级：<el-tag size="small" v-if="mine.assessment.suggestion_grade">{{ mine.assessment.suggestion_grade }}</el-tag>　
              建议系数：<b>{{ mine.assessment.suggestion_coefficient ?? '—' }}</b>
            </div>
            <div class="suggest-reason">{{ mine.assessment.suggestion_reason || '—' }}</div>
          </div>
          <el-table :data="mine.items" size="small" border style="margin-top: 12px;">
            <el-table-column label="维度" width="150">
              <template #default="{ row }">{{ dimNames[row.dimension] }}</template>
            </el-table-column>
            <el-table-column prop="task_name" label="任务名称" min-width="180" show-overflow-tooltip />
            <el-table-column prop="target" label="目标/交付物" min-width="140" show-overflow-tooltip />
            <el-table-column prop="difficulty" label="难度" width="70" align="center" />
            <el-table-column label="建议得分" width="90" align="center">
              <template #default="{ row }">{{ row.self_score }}</template>
            </el-table-column>
            <el-table-column prop="self_note" label="完成情况" min-width="180" show-overflow-tooltip />
            <el-table-column label="核定分" width="80" align="center">
              <template #default="{ row }">{{ row.final_score != null ? row.final_score : '—' }}</template>
            </el-table-column>
          </el-table>
        </template>
        <el-empty v-else description="本季度考核表尚未导入" />
      </el-tab-pane>

      <!-- ===== Tab 2: 考核总览与核定 ===== -->
      <el-tab-pane v-if="canReview" label="考核总览与核定" name="overview">
        <div class="header-actions" style="margin-bottom: 12px; flex-wrap: wrap; gap: 10px;">
          <el-upload
            :auto-upload="false"
            multiple
            :show-file-list="true"
            :file-list="fileList"
            :on-change="onFileChange"
            :on-remove="(f, fl) => fileList = fl"
            accept=".xlsx,.xlsm,.docx,.csv,.txt"
            :disabled="importing"
          >
            <el-button :icon="FolderOpened" :disabled="importing">选择考核表（可多选）</el-button>
          </el-upload>
          <el-button type="primary" :icon="Upload" :loading="importing"
            :disabled="!fileList.length" @click="batchImport">
            {{ importing ? `分析中 ${doneCount}/${fileList.length}...` : `开始导入分析（${fileList.length}个文件）` }}
          </el-button>
          <el-button type="primary" plain :icon="Download" @click="exportCsv">导出CSV</el-button>
          <el-button plain :icon="Aim" @click="openDeptTargets">部门年度指标</el-button>
          <el-button type="warning" plain :icon="RefreshRight" :loading="reanalyzing"
            :disabled="!hasImported" @click="confirmReanalyze">重新分析</el-button>
          <span class="import-tip">支持 xlsx / docx / csv；导入后大模型结合系统数据与部门指标生成初步考核建议</span>
        </div>
        <el-table :data="overviewRows" size="small" border>
          <el-table-column prop="name" label="姓名" width="90" />
          <el-table-column prop="role" label="角色" width="90" />
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag v-if="!row.a_status" type="info" size="small">未导入</el-tag>
              <el-tag v-else-if="row.a_status === 'draft'" type="warning" size="small">待核定</el-tag>
              <el-tag v-else type="success" size="small">已核定</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="建议总分" width="90" align="center">
            <template #default="{ row }">{{ row.suggestion_total != null ? row.suggestion_total : '—' }}</template>
          </el-table-column>
          <el-table-column label="建议等级" width="90" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.suggestion_grade" size="small">{{ row.suggestion_grade }}</el-tag>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="建议系数" width="90" align="center">
            <template #default="{ row }">{{ row.suggestion_coefficient != null ? row.suggestion_coefficient : '—' }}</template>
          </el-table-column>
          <el-table-column label="核定总分" width="90" align="center">
            <template #default="{ row }">{{ row.final_total != null ? row.final_total : '—' }}</template>
          </el-table-column>
          <el-table-column label="等级" width="70" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.grade" size="small">{{ row.grade }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="考核系数" width="90" align="center">
            <template #default="{ row }">{{ row.coefficient != null ? row.coefficient : '—' }}</template>
          </el-table-column>
          <el-table-column prop="review_comment" label="核定意见" min-width="140" show-overflow-tooltip />
          <el-table-column label="原表" width="70" align="center">
            <template #default="{ row }">
              <el-button v-if="row.import_file" link type="primary" size="small"
                @click="downloadFile(row)">下载</el-button>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="140" align="center">
            <template #default="{ row }">
              <el-button v-if="row.a_status === 'draft'" type="primary" size="small" @click="openReview(row)">核定</el-button>
              <el-button v-else-if="row.a_status === 'reviewed'" size="small" @click="openReview(row)">查看</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- ===== 部门年度指标弹窗 ===== -->
    <el-dialog v-model="deptDlg.visible" title="部门年度指标完成度" width="640px">
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px;"
        title="指标完成度将作为大模型评分的硬性校准依据：完成率显著偏低（<60%）时，销售类岗位总分原则上不超过85分、不得评S/A，系数≤1.0。" />
      <el-table :data="deptDlg.rows" size="small" border>
        <el-table-column label="指标名称" min-width="180">
          <template #default="{ row }"><el-input v-model="row.name" placeholder="如：新签合同额" /></template>
        </el-table-column>
        <el-table-column label="年度目标" width="150">
          <template #default="{ row }"><el-input-number v-model="row.target_value" :min="0" :controls="false" style="width:100%" /></template>
        </el-table-column>
        <el-table-column label="累计完成" width="150">
          <template #default="{ row }"><el-input-number v-model="row.actual_value" :min="0" :controls="false" style="width:100%" /></template>
        </el-table-column>
        <el-table-column label="完成率" width="90" align="center">
          <template #default="{ row }">
            <span :style="rateStyle(row)">{{ rateText(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="60" align="center">
          <template #default="{ $index }">
            <el-button link type="danger" size="small" @click="deptDlg.rows.splice($index, 1)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-button size="small" style="margin-top: 8px;" @click="deptDlg.rows.push({ name: '', target_value: null, actual_value: null })">+ 添加指标</el-button>
      <div class="sys-ref">系统参考：{{ sysRefText }}</div>
      <template #footer>
        <el-button @click="deptDlg.visible = false">取消</el-button>
        <el-button type="primary" :loading="deptDlg.saving" @click="saveDeptTargets">保存</el-button>
      </template>
    </el-dialog>

    <!-- ===== 导入结果弹窗 ===== -->
    <el-dialog v-model="resultDlg.visible" title="导入分析结果" width="760px">
      <div v-for="(fr, fi) in resultDlg.files" :key="fi" class="file-result">
        <div class="file-name">
          <el-icon><Document /></el-icon>
          {{ fr.filename }}
          <el-tag v-if="fr.ok" type="success" size="small" style="margin-left: 8px;">成功</el-tag>
          <el-tag v-else type="danger" size="small" style="margin-left: 8px;">失败</el-tag>
        </div>
        <div v-if="fr.ok" class="member-results">
          <div v-if="!fr.results.length" class="empty-line">该文件未匹配到应用中心成员</div>
          <div v-for="(m, mi) in fr.results" :key="mi" class="member-result">
            <div class="mr-head">
              <b>{{ m.name }}</b>
              <span>建议总分 <b class="mr-score">{{ m.total }}</b> 分</span>
              <el-tag size="small">{{ m.grade }} 级</el-tag>
              <span>建议系数 <b>{{ m.coefficient ?? '—' }}</b></span>
              <span class="mr-items">{{ m.items }} 项任务</span>
            </div>
            <div class="mr-sys">系统数据：{{ m.system_data }}</div>
            <div class="mr-reason">{{ m.reason }}</div>
          </div>
          <div v-if="fr.skipped.length" class="skip-line">
            未匹配到系统账号：{{ fr.skipped.join('、') }}
          </div>
        </div>
        <div v-else class="err-line">{{ fr.error }}</div>
      </div>
      <template #footer>
        <el-button type="primary" @click="resultDlg.visible = false">知道了</el-button>
      </template>
    </el-dialog>

    <!-- ===== 核定弹窗 ===== -->
    <el-dialog v-model="reviewDlg.visible" :title="`综合核定 — ${reviewDlg.name}（${year} 年 Q${quarter}）`" width="920px">
      <div v-if="reviewDlg.suggestion" class="suggest-box">
        <div class="suggest-title">大模型初步考核建议</div>
        <div class="suggest-line">
          建议总分：<b>{{ reviewDlg.suggestion.total ?? '—' }}</b>　
          建议等级：<b>{{ reviewDlg.suggestion.grade ?? '—' }}</b>　
          建议系数：<b>{{ reviewDlg.suggestion.coefficient ?? '—' }}</b>
        </div>
        <div class="suggest-reason">{{ reviewDlg.suggestion.reason || '—' }}</div>
      </div>

      <el-table :data="reviewDlg.items" size="small" border max-height="340" style="margin-top: 10px;">
        <el-table-column prop="dimension_label" label="维度" width="130" show-overflow-tooltip />
        <el-table-column prop="task_name" label="任务名称" min-width="160" show-overflow-tooltip />
        <el-table-column label="难度" width="60" align="center">
          <template #default="{ row }">{{ row.difficulty }}</template>
        </el-table-column>
        <el-table-column label="建议分" width="80" align="center">
          <template #default="{ row }">{{ row.self_score }}</template>
        </el-table-column>
        <el-table-column label="完成情况说明" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.self_note }}</template>
        </el-table-column>
        <el-table-column label="核定得分" width="130" align="center">
          <template #default="{ row }">
            <el-input-number v-model="row.final_score" :min="0" :max="dimMax[row.dimension]" :precision="2"
              size="small" style="width: 100%;" controls-position="right" />
          </template>
        </el-table-column>
      </el-table>

      <div class="review-summary">
        核定总分：<b>{{ finalTotal.toFixed(2) }}</b> / 100
        <el-tag v-if="finalGrade" size="small" style="margin-left: 8px;">{{ finalGrade }} 级</el-tag>
        <span v-if="finalGrade" class="coef-hint">系数区间 {{ gradeRules[finalGrade].coef_min }} ~ {{ gradeRules[finalGrade].coef_max }}</span>
      </div>

      <el-form label-width="180px" style="margin-top: 12px;">
        <el-form-item label="约束条件（影响系数）">
          <div class="flag-list">
            <el-checkbox v-model="reviewDlg.flags.urgent_task">承担急难险重任务、责任担当突出且业绩贡献特别显著</el-checkbox>
            <el-checkbox v-model="reviewDlg.flags.market_target_met">完成对应时间节点市场指标（系数≥1）</el-checkbox>
            <el-checkbox v-model="reviewDlg.flags.major_mistake">项目争取/管理/回款/方案编制出现低级错误或重大失误（≤0.5）</el-checkbox>
            <el-checkbox v-model="reviewDlg.flags.security_hidden">出现安全保密隐患（≤0.8）</el-checkbox>
            <el-checkbox v-model="reviewDlg.flags.security_accident">发生安全保密事故（≤0.5）</el-checkbox>
          </div>
        </el-form-item>
        <el-form-item label="考核系数">
          <el-input-number v-model="reviewDlg.coefficient" :min="0" :max="1.5" :step="0.1" :precision="2"
            controls-position="right" />
          <span class="coef-hint" style="margin-left: 8px;">0 ~ 1.5，须符合等级区间与约束上限</span>
        </el-form-item>
        <el-form-item label="综合核定意见">
          <el-input v-model="reviewDlg.review_comment" type="textarea" :rows="2" placeholder="综合评价、改进建议等（报人力备案）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reviewDlg.visible = false">关闭</el-button>
        <el-button v-if="reviewDlg.status === 'draft'" type="primary" :loading="reviewDlg.saving" @click="submitReview">确认核定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload, Download, FolderOpened, Document, Aim, RefreshRight } from '@element-plus/icons-vue'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const canReview = computed(() => authStore.has('appraisal.view'))

const now = new Date()
const year = ref(now.getFullYear())
const yearOptions = [now.getFullYear() - 1, now.getFullYear(), now.getFullYear() + 1]
const quarter = ref(now.getMonth() + 1 <= 3 ? 1 : (now.getMonth() + 1 <= 6 ? 2 : 3))
const activeTab = ref(canReview.value ? 'overview' : 'mine')

const DIM_MAX = { 1: 50, 2: 30, 3: 10, 4: 10 }
const DIM_NAMES = { 1: '重点任务完成情况', 2: '日常工作完成情况', 3: '责任担当与协同贡献', 4: '工作量与任务饱和度' }
const dimMax = DIM_MAX
const dimNames = DIM_NAMES
const gradeRules = {
  S: { coef_min: 1.0, coef_max: 1.5 },
  A: { coef_min: 1.0, coef_max: 1.0 },
  B: { coef_min: 0.8, coef_max: 1.0 },
  C: { coef_min: 0.6, coef_max: 0.8 },
  D: { coef_min: 0, coef_max: 0.6 }
}
const gradeOf = (s) => s >= 96 ? 'S' : s >= 86 ? 'A' : s >= 76 ? 'B' : s >= 60 ? 'C' : 'D'


// ---------- 我的考核结果 ----------
const mine = reactive({ assessment: null, items: [] })
const loadMine = async () => {
  const res = await api.get('/quarterly-assessment/mine', { year: year.value, quarter: quarter.value })
  mine.assessment = res.data.assessment
  mine.items = res.data.items || []
}

// ---------- 考核总览 ----------
const overviewRows = ref([])
const loadOverview = async () => {
  const res = await api.get('/quarterly-assessment/overview', { year: year.value, quarter: quarter.value })
  overviewRows.value = res.data.rows || []
}

const loadAll = () => {
  loadMine()
  if (canReview.value) loadOverview()
}

// ---------- 批量导入 ----------
const fileList = ref([])
const importing = ref(false)
const doneCount = ref(0)
const resultDlg = reactive({ visible: false, files: [] })

const onFileChange = (file, fl) => { fileList.value = fl }
const clearFiles = () => { fileList.value = [] }

const batchImport = async () => {
  const files = fileList.value.map(f => f.raw).filter(Boolean)
  if (!files.length) { ElMessage.warning('请先选择考核表文件'); return }
  importing.value = true
  doneCount.value = 0
  const jobs = files.map(f =>
    api.longPost('/quarterly-assessment/import', buildForm(f))
      .then(res => {
        doneCount.value++
        return res.code === 200
          ? { filename: f.name, ok: true, results: res.data?.results || [], skipped: res.data?.skipped || [] }
          : { filename: f.name, ok: false, error: res.message || '导入失败' }
      })
      .catch(e => {
        doneCount.value++
        return { filename: f.name, ok: false, error: e?.message || '导入失败（网络/服务异常）' }
      })
  )
  const results = await Promise.all(jobs)
  importing.value = false
  resultDlg.files = results
  resultDlg.visible = true
  clearFiles()
  await loadOverview()
}
const buildForm = (file) => {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('year', year.value)
  fd.append('quarter', quarter.value)
  return fd
}

const downloadFile = async (row) => {
  const resp = await fetch(`/api/quarterly-assessment/file/${row.assessment_id}`, {
    headers: { Authorization: `Bearer ${authStore.token || localStorage.getItem('crm_token')}` },
  })
  if (!resp.ok) { ElMessage.error('下载失败'); return }
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = decodeURIComponent(row.import_file.split('/').pop())
  a.click()
  URL.revokeObjectURL(url)
}

// ---------- 部门年度指标 ----------
const deptDlg = reactive({ visible: false, rows: [], saving: false })
const hasImported = computed(() => overviewRows.value.some(r => r.a_status))

const sysRefText = computed(() => {
  const y = year.value
  const withTargets = overviewRows.value.filter(r => r.system_ref)
  return `${y} 年按系统月度目标口径；可结合实际情况填写完成值`
})

const openDeptTargets = async () => {
  const res = await api.get('/quarterly-assessment/dept-targets', { year: year.value })
  deptDlg.rows = (res.data.rows || []).map(r => ({
    name: r.name, target_value: r.target_value, actual_value: r.actual_value,
  }))
  deptDlg.visible = true
}

const rateText = (row) => {
  if (!row.target_value || row.actual_value == null) return '—'
  return `${(row.actual_value / row.target_value * 100).toFixed(1)}%`
}
const rateStyle = (row) => {
  if (!row.target_value || row.actual_value == null) return {}
  const rate = row.actual_value / row.target_value * 100
  return { color: rate < 60 ? '#f56c6c' : rate < 100 ? '#e6a23c' : '#67c23a', fontWeight: 600 }
}

const saveDeptTargets = async () => {
  const rows = deptDlg.rows.filter(r => r.name && r.name.trim())
  if (!rows.length) { ElMessage.warning('请至少填写一项指标'); return }
  deptDlg.saving = true
  try {
    const res = await api.put('/quarterly-assessment/dept-targets', { year: year.value, rows })
    if (res.code === 200) {
      ElMessage.success('已保存，重新分析后将按新指标校准评分')
      deptDlg.visible = false
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } finally {
    deptDlg.saving = false
  }
}

// ---------- 重新分析 ----------
const reanalyzing = ref(false)
const confirmReanalyze = () => {
  ElMessageBox.confirm(
    '将用已导入的原始考核表按最新部门指标与校准规则重跑大模型分析，覆盖当前季度全部初步建议（已核定结果不受影响）。继续？',
    '重新分析', { confirmButtonText: '开始', cancelButtonText: '取消', type: 'warning' }
  ).then(runReanalyze).catch(() => {})
}
const runReanalyze = async () => {
  reanalyzing.value = true
  try {
    const res = await api.longPost('/quarterly-assessment/reanalyze', { year: year.value, quarter: quarter.value })
    if (res.code === 200) {
      const files = res.data?.files || []
      resultDlg.files = files.map(f => ({
        filename: `assessment #${f.assessment_id}`,
        ok: f.ok,
        results: f.results || [],
        skipped: f.skipped || [],
        error: f.error || '',
      }))
      resultDlg.visible = true
      await loadOverview()
    } else {
      ElMessage.error(res.message || '重新分析失败')
    }
  } catch (e) {
    ElMessage.error(e?.message || '重新分析失败（请求超时或服务异常）')
  } finally {
    reanalyzing.value = false
  }
}

// ---------- 核定 ----------
const reviewDlg = reactive({
  visible: false, username: '', name: '', status: '', saving: false,
  items: [], flags: {}, coefficient: 1.0, review_comment: '', suggestion: null
})
const finalTotal = computed(() => reviewDlg.items.reduce((s, r) => s + (Number(r.final_score) || 0), 0))
const finalGrade = computed(() => finalTotal.value > 0 ? gradeOf(finalTotal.value) : '')

const openReview = async (row) => {
  const res = await api.get(`/quarterly-assessment/detail/${row.username}`, { year: year.value, quarter: quarter.value })
  if (!res.data.assessment) { ElMessage.warning('该员工无此季度考核数据，请先导入'); return }
  const a = res.data.assessment
  reviewDlg.username = row.username
  reviewDlg.name = row.name
  reviewDlg.status = a.status
  reviewDlg.items = (res.data.items || []).map(i => ({
    ...i, dimension_label: DIM_NAMES[i.dimension], final_score: i.final_score ?? i.self_score
  }))
  reviewDlg.coefficient = a.coefficient ?? a.suggestion_coefficient ?? 1.0
  reviewDlg.review_comment = a.review_comment || ''
  reviewDlg.suggestion = {
    total: a.suggestion_total, grade: a.suggestion_grade,
    coefficient: a.suggestion_coefficient, reason: a.suggestion_reason
  }
  reviewDlg.flags = { urgent_task: false, market_target_met: false, major_mistake: false, security_hidden: false, security_accident: false }
  try { Object.assign(reviewDlg.flags, JSON.parse(a.constraint_flags || '{}')) } catch { /* ignore */ }
  reviewDlg.visible = true
}

const submitReview = async () => {
  if (reviewDlg.items.some(i => i.final_score == null)) { ElMessage.warning('请为每项任务填写核定得分'); return }
  for (const d of [1, 2, 3, 4]) {
    const s = reviewDlg.items.filter(i => i.dimension === d).reduce((a, r) => a + (Number(r.final_score) || 0), 0)
    if (s > DIM_MAX[d] + 1e-9) { ElMessage.warning(`「${DIM_NAMES[d]}」核定合计 ${s.toFixed(2)} 分，超过上限 ${DIM_MAX[d]} 分`); return }
  }
  reviewDlg.saving = true
  try {
    const res = await api.post('/quarterly-assessment/review', {
      username: reviewDlg.username, year: year.value, quarter: quarter.value,
      items: reviewDlg.items.map(i => ({ id: i.id, final_score: i.final_score })),
      constraint_flags: reviewDlg.flags,
      coefficient: reviewDlg.coefficient,
      review_comment: reviewDlg.review_comment
    })
    if (res.code === 200) {
      ElMessage.success(res.message || '核定完成')
      reviewDlg.visible = false
      await Promise.all([loadOverview(), loadMine()])
    } else {
      ElMessage.error(res.message || '核定失败')
    }
  } finally {
    reviewDlg.saving = false
  }
}

// ---------- 导出 ----------
const exportCsv = async () => {
  const params = new URLSearchParams({ year: year.value, quarter: quarter.value })
  const resp = await fetch(`/api/quarterly-assessment/export?${params.toString()}`, {
    headers: { Authorization: `Bearer ${authStore.token || localStorage.getItem('crm_token')}` },
  })
  if (!resp.ok) { ElMessage.error('导出失败'); return }
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `应用中心季度考核_${year.value}Q${quarter.value}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(loadAll)
</script>

<style scoped>
.quarterly-assessment { padding: 0 4px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.page-title { margin: 0; font-size: 20px; }
.header-actions { display: flex; align-items: center; }
.import-tip { margin-left: 12px; color: #909399; font-size: 12px; }
.suggest-box { background: #f4f8ff; border: 1px solid #d9e6ff; border-radius: 6px; padding: 10px 14px; }
.suggest-title { font-weight: 600; font-size: 13px; color: #3a6bd6; margin-bottom: 6px; }
.suggest-line { font-size: 14px; }
.suggest-reason { margin-top: 6px; font-size: 13px; color: #606266; white-space: pre-wrap; }
.review-summary { margin-top: 12px; font-size: 14px; }
.coef-hint { color: #909399; font-size: 12px; margin-left: 6px; }
.flag-list { display: flex; flex-direction: column; gap: 2px; }
.file-result { margin-bottom: 14px; border-bottom: 1px solid #eee; padding-bottom: 10px; }
.file-result:last-child { border-bottom: none; }
.file-name { font-weight: 600; font-size: 14px; display: flex; align-items: center; margin-bottom: 8px; }
.member-result { background: #f7f9fc; border-radius: 6px; padding: 8px 12px; margin-bottom: 8px; }
.mr-head { display: flex; align-items: center; gap: 12px; font-size: 14px; }
.mr-score { color: #e6a23c; font-size: 16px; }
.mr-items { color: #909399; font-size: 12px; margin-left: auto; }
.mr-sys { margin-top: 6px; font-size: 12px; color: #3a6bd6; }
.mr-reason { margin-top: 4px; font-size: 13px; color: #606266; white-space: pre-wrap; }
.skip-line { color: #e6a23c; font-size: 13px; margin-top: 4px; }
.err-line { color: #f56c6c; font-size: 13px; }
.empty-line { color: #909399; font-size: 13px; }
.sys-ref { margin-top: 10px; font-size: 12px; color: #909399; }
</style>
