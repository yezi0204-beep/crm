<template>
  <div class="smart-import-page">
    <el-steps :active="stepIndex" finish-status="success" class="steps" align-center>
      <el-step title="上传文件" />
      <el-step title="预览与映射" />
      <el-step title="导入结果" />
    </el-steps>

    <!-- 步骤1: 上传 -->
    <el-card v-if="currentStep === 'upload'" class="upload-card">
      <el-upload
        drag
        :auto-upload="true"
        :show-file-list="false"
        accept=".xlsx,.xls,.csv"
        :http-request="handleUpload"
      >
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">拖拽文件到此处或<em>点击上传</em></div>
        <template #tip>
          <div class="el-upload__tip">支持 Excel (.xlsx/.xls) 和 CSV 文件，系统将自动识别数据归属模块</div>
        </template>
      </el-upload>
      <div v-if="uploading" class="upload-loading">
        <el-icon class="is-loading"><loading /></el-icon>
        正在解析文件并智能识别模块...
      </div>

      <el-divider />
      <div class="help-section">
        <h4>功能说明</h4>
        <ul>
          <li>系统会自动识别每个工作表属于哪个模块（客户/商机/合同/回款/拜访/线索）</li>
          <li>自动将 Excel 列头映射到对应字段，可手动调整</li>
          <li>多个工作表可一次性导入，按依赖顺序自动处理（客户→商机→合同→回款）</li>
          <li>金额默认按"万元"处理，可切换为"元"</li>
          <li>无法匹配的关联数据（如合同找不到客户）会自动创建</li>
          <li>存在歧义时会标注提示，由你决策</li>
        </ul>
      </div>
    </el-card>

    <!-- 步骤2: 预览 -->
    <div v-if="currentStep === 'preview'">
      <div class="preview-header">
        <span class="filename">📄 {{ filename }}</span>
        <div class="header-actions">
          <el-radio-group v-model="isWan" size="small">
            <el-radio-button :value="true">金额单位：万元</el-radio-button>
            <el-radio-button :value="false">金额单位：元</el-radio-button>
          </el-radio-group>
          <el-button @click="resetAll">重新上传</el-button>
          <el-button type="primary" :loading="importing" @click="executeImport">
            确认导入
          </el-button>
        </div>
      </div>

      <el-card v-for="(sheet, si) in sheets" :key="si" class="sheet-card" shadow="hover">
        <template #header>
          <div class="sheet-header">
            <span class="sheet-name">📋 {{ sheet.sheet_name }}</span>
            <el-tag v-if="sheet.is_ambiguous" type="warning" size="small">⚠ 模块存在歧义，请确认</el-tag>
            <el-tag type="success" size="small">{{ sheet.valid_count }} 有效</el-tag>
            <el-tag v-if="sheet.invalid_count" type="danger" size="small">{{ sheet.invalid_count }} 无效</el-tag>
            <span class="total">共 {{ sheet.total_rows }} 行</span>
          </div>
        </template>

        <!-- 模块选择 -->
        <div class="module-select-row">
          <span class="label">识别模块：</span>
          <el-select v-model="sheet.selectedModule" placeholder="选择模块" style="width:240px"
            @change="onModuleChange(sheet)">
            <el-option v-for="ms in sheet.module_scores" :key="ms.module"
              :label="`${ms.name} (匹配${ms.score}列)`" :value="ms.module" />
          </el-select>
          <span v-if="!sheet.selectedModule" class="ambiguous-hint">⚠ 无法自动识别，请手动选择模块</span>
        </div>

        <!-- 字段映射 -->
        <div v-if="sheet.selectedModule" class="field-map-section">
          <div class="section-title">字段映射（可调整）</div>
          <el-table :data="getFieldMapRows(sheet)" size="small" border max-height="300">
            <el-table-column label="Excel列头" prop="header" width="200" />
            <el-table-column label="映射到字段" width="220">
              <template #default="{ row }">
                <el-select v-model="row.field" size="small" clearable filterable
                  placeholder="不导入此列" @change="onFieldMapChange(sheet)">
                  <el-option v-for="f in getAvailableFields(sheet)" :key="f"
                    :label="f" :value="f" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="示例数据" prop="sample" show-overflow-tooltip />
          </el-table>
        </div>

        <!-- 数据预览 -->
        <div v-if="sheet.selectedModule" class="data-preview-section">
          <div class="section-title">数据预览（前20行）</div>
          <el-table :data="sheet.rows.slice(0, 20)" size="small" border max-height="400">
            <el-table-column label="#" type="index" width="50" />
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.valid ? 'success' : 'danger'" size="small">
                  {{ row.valid ? '有效' : '无效' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column v-for="(header, hi) in sheet.headers" :key="hi"
              :label="header" show-overflow-tooltip min-width="120">
              <template #default="{ row }">
                {{ row.raw[hi] || '' }}
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-card>
    </div>

    <!-- 步骤3: 结果 -->
    <el-card v-if="currentStep === 'result'" class="result-card">
      <el-result
        :icon="importResult.total_fail === 0 ? 'success' : 'warning'"
        :title="`导入完成`"
        :sub-title="`成功 ${importResult.total_success} 条，失败 ${importResult.total_fail} 条`">
      </el-result>
      <el-table :data="importResult.sheets" border size="small">
        <el-table-column label="工作表" prop="sheet_name" width="120" />
        <el-table-column label="模块" prop="module_name" width="80" />
        <el-table-column label="成功" prop="success_count" width="70">
          <template #default="{ row }">
            <span style="color:#67c23a">{{ row.success_count }}</span>
          </template>
        </el-table-column>
        <el-table-column label="失败" prop="fail_count" width="70">
          <template #default="{ row }">
            <span :style="{color: row.fail_count > 0 ? '#f56c6c' : '#999'}">{{ row.fail_count }}</span>
          </template>
        </el-table-column>
        <el-table-column label="失败详情">
          <template #default="{ row }">
            <div v-for="r in row.results.filter(x => !x.success)" :key="r.row_index" class="fail-detail">
              第{{ r.row_index }}行: {{ r.message }}
            </div>
            <span v-if="row.fail_count === 0" style="color:#999">全部成功</span>
          </template>
        </el-table-column>
      </el-table>
      <div style="margin-top: 16px; text-align: center;">
        <el-button @click="resetAll">再次导入</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, Loading } from '@element-plus/icons-vue'
import api from '../api'

const currentStep = ref('upload')
const uploading = ref(false)
const importing = ref(false)
const filename = ref('')
const sheets = ref([])
const isWan = ref(true)
const importResult = ref({})

const stepIndex = computed(() => {
  if (currentStep.value === 'upload') return 0
  if (currentStep.value === 'preview') return 1
  return 2
})

// 每个模块的可映射字段
const ALL_MODULE_FIELDS = {
  customers: ['company', 'name', 'phone', 'email', 'level', 'source', 'industry', 'region', 'owner_id'],
  business: ['title', 'amount', 'stage', 'predict_date', 'owner_id', 'probability', 'source', 'industry', 'region', 'note'],
  contracts: ['contract_no', 'contract_name', 'total_amt', 'sign_date', 'party_a', 'owner_id', 'status', 'classification', 'business_type', 'acceptance_date', 'expected_income_date', 'note'],
  payment_records: ['contract_no', 'contract_name', 'payment_date', 'amount', 'note'],
  visits: ['plan_date', 'plan_time', 'purpose', 'visitor_id', 'location', 'contact_person', 'result', 'notes', 'work_content', 'work_type'],
  scraped_leads: ['company', 'contact_name', 'phone', 'email', 'industry', 'region', 'source', 'opportunity_name', 'budget', 'deadline', 'publish_date', 'remark'],
  enterprises: ['name', 'established_date', 'location', 'personnel_size', 'brief', 'registered_capital', 'business_scope', 'main_qualifications', 'main_products', 'relationship_status', 'cooperation_opportunities', 'website', 'contact_person', 'contact_info'],
}

const REQUIRED_FIELDS = {
  customers: ['company'],
  business: ['title'],
  contracts: ['contract_no', 'contract_name', 'total_amt'],
  payment_records: ['contract_no', 'payment_date', 'amount'],
  visits: ['plan_date'],
  scraped_leads: ['company'],
  enterprises: ['name'],
}

// 上传文件
async function handleUpload(options) {
  uploading.value = true
  const formData = new FormData()
  formData.append('file', options.file)
  try {
    const res = await api.post('/smart-import/parse', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    })
    if (res.code === 200 && res.data) {
      filename.value = res.data.filename
      sheets.value = res.data.sheets.map(s => ({
        ...s,
        selectedModule: s.detected_module,
      }))
      currentStep.value = 'preview'
      ElMessage.success(`解析成功：${sheets.value.length} 个工作表`)
    } else {
      ElMessage.error(res.message || '解析失败')
    }
  } catch (e) {
    ElMessage.error('文件解析失败: ' + (e.response?.data?.message || e.message || ''))
  } finally {
    uploading.value = false
  }
}

// 切换模块
function onModuleChange(sheet) {
  const fm = sheet.all_field_maps?.[sheet.selectedModule] || {}
  sheet.field_map = { ...fm }
  rebuildRowData(sheet)
}

// 字段映射调整
function onFieldMapChange(sheet) {
  // 从 getFieldMapRows 同步回 field_map
  const rows = getFieldMapRows(sheet)
  sheet.field_map = {}
  rows.forEach((row, idx) => {
    if (row.field) {
      sheet.field_map[String(idx)] = row.field
    }
  })
  rebuildRowData(sheet)
}

// 重新构建行数据和校验
function rebuildRowData(sheet) {
  const required = REQUIRED_FIELDS[sheet.selectedModule] || []
  for (const row of sheet.rows) {
    const data = {}
    for (const [colIdx, field] of Object.entries(sheet.field_map)) {
      if (field) {
        data[field] = row.raw[parseInt(colIdx)] || ''
      }
    }
    row.data = data
    const errors = required.filter(rf => !data[rf]).map(rf => `缺少必填字段: ${rf}`)
    row.valid = errors.length === 0
    row.errors = errors
  }
  // 重新统计
  sheet.valid_count = sheet.rows.filter(r => r.valid).length
  sheet.invalid_count = sheet.rows.filter(r => !r.valid).length
}

// 获取字段映射表行（用于 el-table 展示和编辑）
function getFieldMapRows(sheet) {
  return sheet.headers.map((header, idx) => ({
    header,
    field: sheet.field_map[String(idx)] || '',
    sample: sheet.rows[0]?.raw[idx] || '',
  }))
}

function getAvailableFields(sheet) {
  return ALL_MODULE_FIELDS[sheet.selectedModule] || []
}

// 执行导入
async function executeImport() {
  // 检查是否有可导入的数据
  const hasValid = sheets.value.some(s => s.selectedModule && s.rows.some(r => r.valid))
  if (!hasValid) {
    ElMessage.warning('没有可导入的有效数据')
    return
  }

  importing.value = true
  try {
    const payload = {
      is_wan: isWan.value,
      sheets: sheets.value.map(s => ({
        sheet_name: s.sheet_name,
        module: s.selectedModule,
        field_map: s.field_map,
        rows: s.rows.map(r => ({ ...r, selected: r.valid })),
      })),
    }
    const res = await api.post('/smart-import/execute', payload, { timeout: 120000 })
    if (res.code === 200) {
      importResult.value = res.data
      currentStep.value = 'result'
      ElMessage.success(res.message)
    } else {
      ElMessage.error(res.message || '导入失败')
    }
  } catch (e) {
    ElMessage.error('导入失败: ' + (e.response?.data?.message || e.message || ''))
  } finally {
    importing.value = false
  }
}

function resetAll() {
  currentStep.value = 'upload'
  sheets.value = []
  filename.value = ''
  importResult.value = {}
}
</script>

<style scoped>
.smart-import-page {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.steps {
  margin-bottom: 24px;
}

.upload-card {
  max-width: 600px;
  margin: 0 auto;
}

.upload-loading {
  text-align: center;
  margin-top: 16px;
  color: #4a5568;
  font-size: 14px;
}

.help-section {
  margin-top: 16px;
  color: #718096;
  font-size: 13px;
}

.help-section h4 {
  margin-bottom: 8px;
  color: #4a5568;
}

.help-section ul {
  padding-left: 20px;
  line-height: 1.8;
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #f7fafc;
  border-radius: 8px;
}

.filename {
  font-size: 15px;
  font-weight: 500;
  color: #2d3748;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.sheet-card {
  margin-bottom: 16px;
}

.sheet-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.sheet-name {
  font-weight: 600;
  font-size: 15px;
}

.total {
  color: #a0aec0;
  font-size: 13px;
  margin-left: auto;
}

.module-select-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.module-select-row .label {
  font-weight: 500;
  color: #4a5568;
}

.ambiguous-hint {
  color: #e6a23c;
  font-size: 13px;
}

.field-map-section,
.data-preview-section {
  margin-top: 16px;
}

.section-title {
  font-weight: 600;
  font-size: 14px;
  color: #4a5568;
  margin-bottom: 8px;
  padding-left: 8px;
  border-left: 3px solid #409eff;
}

.fail-detail {
  color: #f56c6c;
  font-size: 12px;
  line-height: 1.6;
}

.result-card {
  max-width: 900px;
  margin: 0 auto;
}
</style>
