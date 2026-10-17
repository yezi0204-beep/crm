<template>
  <div class="work-cost">
    <el-tabs v-model="activeTab">
      <!-- ============ Tab1 月度管理 ============ -->
      <el-tab-pane label="月度成本管理" name="months">
        <div class="toolbar">
          <el-select v-model="filterDept" placeholder="全部部门" clearable style="width: 140px" @change="loadMonths">
            <el-option v-for="d in DEPTS" :key="d" :label="d" :value="d" />
          </el-select>
          <el-date-picker v-model="filterYear" type="year" placeholder="全部年份" value-format="YYYY"
                          style="width: 130px" @change="loadMonths" :clearable="true" />
          <el-button type="primary" @click="openEdit()" v-if="canManage">＋ 录入月度成本</el-button>
        </div>

        <el-table :data="months" v-loading="loading" border show-summary :summary-method="monthsSummary">
          <el-table-column prop="dept" label="部门" width="110" align="center">
            <template #default="{ row }">
              <el-tag :type="row.dept === '应用中心' ? 'primary' : 'warning'">{{ row.dept }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="month" label="月份" width="100" align="center" />
          <el-table-column prop="total_hours" label="总工时" width="100" align="right">
            <template #default="{ row }">{{ fmt2(row.total_hours) }}</template>
          </el-table-column>
          <el-table-column prop="total_cost" label="人力成本合计(元)" width="150" align="right">
            <template #default="{ row }">{{ fmt2(row.total_cost) }}</template>
          </el-table-column>
          <el-table-column prop="unit_cost" label="单工时成本(元)" width="140" align="right">
            <template #default="{ row }">
              <span class="unit-cost">{{ row.unit_cost ? row.unit_cost.toFixed(2) : '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="已分配 / 剩余工时" width="160" align="center">
            <template #default="{ row }">
              <span :class="{ 'over-hours': row.remaining_hours < 0 }">
                {{ fmt2(row.allocated_hours) }} / {{ fmt2(row.remaining_hours) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="allocated_cost" label="已分摊成本(元)" width="140" align="right">
            <template #default="{ row }">{{ fmt2(row.allocated_cost) }}</template>
          </el-table-column>
          <el-table-column prop="note" label="备注" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.note || '-' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="230" align="center" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" size="small" @click="openAlloc(row)" v-if="canManage">分配工时</el-button>
              <el-button size="small" @click="openEdit(row)" v-if="canManage">编辑</el-button>
              <el-button type="danger" size="small" plain @click="removeMonth(row)" v-if="canManage">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="hint" v-if="!loading">
          流程：录入部门月度考勤总工时与人力成本 → 中心主任将工时分配到执行中的合同 → 系统按「单工时成本 = 月度总成本 ÷ 总工时」自动把总支出分摊到各项目。
        </div>
      </el-tab-pane>

      <!-- ============ Tab2 分摊汇总 ============ -->
      <el-tab-pane label="项目分摊汇总" name="summary">
        <div class="toolbar">
          <el-radio-group v-model="summaryMode" @change="loadSummary">
            <el-radio-button value="contract">按合同汇总</el-radio-button>
            <el-radio-button value="monthly">按月度明细</el-radio-button>
          </el-radio-group>
          <el-date-picker v-if="summaryMode === 'monthly'" v-model="summaryMonth" type="month"
                          placeholder="全部月份" value-format="YYYY-MM" style="width: 140px"
                          @change="loadSummary" :clearable="true" />
          <el-date-picker v-if="summaryMode === 'contract'" v-model="summaryYear" type="year"
                          placeholder="全部年份" value-format="YYYY" style="width: 130px"
                          @change="loadSummary" :clearable="true" />
          <el-select v-model="summaryDept" placeholder="全部部门" clearable style="width: 140px" @change="loadSummary">
            <el-option v-for="d in DEPTS" :key="d" :label="d" :value="d" />
          </el-select>
          <el-button type="success" @click="exportExcel">📥 导出Excel</el-button>
        </div>

        <!-- 按合同汇总 -->
        <el-table v-if="summaryMode === 'contract'" :data="summaryItems" v-loading="summaryLoading" border
                  show-summary :summary-method="summaryTotal">
          <el-table-column type="index" label="#" width="55" align="center" />
          <el-table-column prop="contract_name" label="合同名称" min-width="260" show-overflow-tooltip />
          <el-table-column prop="contract_no" label="合同编号" width="150" show-overflow-tooltip>
            <template #default="{ row }">{{ row.contract_no || '-' }}</template>
          </el-table-column>
          <el-table-column prop="customer_name" label="客户" width="180" show-overflow-tooltip>
            <template #default="{ row }">{{ row.customer_name || '-' }}</template>
          </el-table-column>
          <el-table-column prop="owner_name" label="负责人" width="90" align="center">
            <template #default="{ row }">{{ row.owner_name || '-' }}</template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="row.status === '执行中' ? 'success' : 'info'" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="total_hours" label="累计分配工时" width="130" align="right">
            <template #default="{ row }">{{ fmt2(row.total_hours) }}</template>
          </el-table-column>
          <el-table-column prop="total_cost" label="累计分摊成本(元)" width="160" align="right" sortable>
            <template #default="{ row }">
              <span class="cost">{{ fmt2(row.total_cost) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="month_count" label="涉及月份数" width="110" align="center" />
        </el-table>

        <!-- 按月度明细 -->
        <el-table v-else :data="detailItems" v-loading="summaryLoading" border show-summary
                  :summary-method="detailTotal">
          <el-table-column prop="month" label="月份" width="90" align="center" sortable />
          <el-table-column prop="dept" label="部门" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="row.dept === '应用中心' ? 'primary' : 'warning'" size="small">{{ row.dept }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="contract_name" label="合同名称" min-width="250" show-overflow-tooltip />
          <el-table-column prop="customer_name" label="客户" width="170" show-overflow-tooltip>
            <template #default="{ row }">{{ row.customer_name || '-' }}</template>
          </el-table-column>
          <el-table-column prop="hours" label="分配工时" width="110" align="right" sortable>
            <template #default="{ row }">{{ fmt2(row.hours) }}</template>
          </el-table-column>
          <el-table-column prop="unit_cost" label="单工时成本(元)" width="140" align="right">
            <template #default="{ row }">{{ row.unit_cost.toFixed(2) }}</template>
          </el-table-column>
          <el-table-column prop="alloc_cost" label="分摊金额(元)" width="150" align="right" sortable>
            <template #default="{ row }">
              <span class="cost">{{ fmt2(row.alloc_cost) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="note" label="备注" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.note || '-' }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ============ Tab3 数据挖掘分析 ============ -->
      <el-tab-pane label="数据挖掘分析" name="analysis">
        <div class="toolbar">
          <el-date-picker v-model="anaYear" type="year" placeholder="全部年份" value-format="YYYY"
                          style="width: 130px" @change="loadAnalysis" :clearable="true" />
          <el-select v-model="anaDept" placeholder="全部部门" clearable style="width: 140px" @change="loadAnalysis">
            <el-option v-for="d in DEPTS" :key="d" :label="d" :value="d" />
          </el-select>
          <el-button type="primary" plain @click="loadAnalysis">刷新分析</el-button>
          <span class="ana-hint">口径：成本分摊按「单工时成本 = 月度总成本 ÷ 总工时」；成本率 = 项目工时成本 ÷ 合同额</span>
        </div>

        <div v-loading="anaLoading">
          <!-- KPI -->
          <div class="kpi-row">
            <div class="kpi-card">
              <div class="kpi-label">月度人力成本合计</div>
              <div class="kpi-value">{{ fmt2(anaKpis.total_cost) }}<span class="kpi-unit">元</span></div>
              <div class="kpi-sub">{{ anaKpis.month_count }} 个月 · {{ anaKpis.dept_count }} 个部门</div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">考勤总工时</div>
              <div class="kpi-value">{{ fmt2(anaKpis.total_hours) }}<span class="kpi-unit">工时</span></div>
              <div class="kpi-sub">平均单工时成本 {{ fmt2(anaKpis.avg_unit_cost) }} 元</div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">已分摊到项目</div>
              <div class="kpi-value">{{ fmt2(anaKpis.allocated_cost) }}<span class="kpi-unit">元</span></div>
              <div class="kpi-sub">分摊率 {{ anaKpis.allocation_rate }}% ｜ 未分摊 {{ fmt2(anaKpis.unallocated_cost) }} 元</div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">项目工时成本</div>
              <div class="kpi-value">{{ fmt2(anaKpis.project_cost) }}<span class="kpi-unit">元</span></div>
              <div class="kpi-sub">{{ anaKpis.project_count }} 个项目 · {{ fmt2(anaKpis.project_hours) }} 工时</div>
            </div>
          </div>

          <!-- 洞察 -->
          <div class="insight-card">
            <div class="insight-title">数据洞察</div>
            <ul class="insight-list">
              <li v-for="(t, i) in anaInsights" :key="i">{{ t }}</li>
            </ul>
          </div>

          <!-- 图表 -->
          <div class="chart-row">
            <div class="chart-card">
              <div class="chart-title">各部门月度人力成本 &amp; 单工时成本</div>
              <div ref="anaCostChart" class="chart"></div>
            </div>
            <div class="chart-card">
              <div class="chart-title">人力成本构成占比</div>
              <div ref="anaPieChart" class="chart"></div>
            </div>
          </div>
          <div class="chart-card">
            <div class="chart-title">项目工时成本 Top 20</div>
            <div ref="anaProjChart" class="chart"></div>
          </div>

          <!-- 部门月度明细 -->
          <div class="table-title">部门月度人力成本明细</div>
          <el-table :data="anaDeptMonthly" border size="small" max-height="380"
                    show-summary :summary-method="anaMonthlySummary">
            <el-table-column prop="month" label="月份" width="95" align="center" sortable />
            <el-table-column prop="dept" label="部门" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="row.dept === '应用中心' ? 'primary' : 'warning'" size="small">{{ row.dept }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="total_hours" label="总工时" width="100" align="right">
              <template #default="{ row }">{{ fmt2(row.total_hours) }}</template>
            </el-table-column>
            <el-table-column prop="total_cost" label="人力成本(元)" width="140" align="right">
              <template #default="{ row }">{{ fmt2(row.total_cost) }}</template>
            </el-table-column>
            <el-table-column prop="unit_cost" label="单工时成本(元)" width="135" align="right">
              <template #default="{ row }"><span class="unit-cost">{{ fmt2(row.unit_cost) }}</span></template>
            </el-table-column>
            <el-table-column prop="allocated_hours" label="已分配工时" width="110" align="right">
              <template #default="{ row }">{{ fmt2(row.allocated_hours) }}</template>
            </el-table-column>
            <el-table-column prop="allocated_cost" label="已分摊成本(元)" width="140" align="right">
              <template #default="{ row }"><span class="cost">{{ fmt2(row.allocated_cost) }}</span></template>
            </el-table-column>
            <el-table-column prop="allocation_rate" label="分摊率" width="120" align="right">
              <template #default="{ row }">
                <el-progress :percentage="Math.min(Number(row.allocation_rate) || 0, 100)"
                             :stroke-width="6" :show-text="false"
                             style="width: 66px; display: inline-block; vertical-align: middle" />
                <span style="margin-left: 6px">{{ row.allocation_rate }}%</span>
              </template>
            </el-table-column>
            <el-table-column prop="unallocated_cost" label="未分摊成本(元)" width="140" align="right">
              <template #default="{ row }">{{ fmt2(row.unallocated_cost) }}</template>
            </el-table-column>
          </el-table>

          <!-- 项目工时成本明细 -->
          <div class="table-title">项目工时成本明细</div>
          <el-table :data="anaProjects" border size="small" max-height="420"
                    show-summary :summary-method="anaProjectSummary">
            <el-table-column type="index" label="#" width="50" align="center" />
            <el-table-column prop="contract_name" label="项目/合同名称" min-width="230" show-overflow-tooltip />
            <el-table-column prop="customer_name" label="客户" width="160" show-overflow-tooltip>
              <template #default="{ row }">{{ row.customer_name || '-' }}</template>
            </el-table-column>
            <el-table-column prop="owner_name" label="负责人" width="90" align="center">
              <template #default="{ row }">{{ row.owner_name || '-' }}</template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="90" align="center">
              <template #default="{ row }">
                <el-tag :type="row.status === '执行中' ? 'success' : 'info'" size="small">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="total_amt" label="合同额(元)" width="130" align="right" sortable>
              <template #default="{ row }">{{ fmt2(row.total_amt) }}</template>
            </el-table-column>
            <el-table-column prop="total_hours" label="累计工时" width="100" align="right" sortable>
              <template #default="{ row }">{{ fmt2(row.total_hours) }}</template>
            </el-table-column>
            <el-table-column prop="total_cost" label="工时成本(元)" width="140" align="right" sortable>
              <template #default="{ row }"><span class="cost">{{ fmt2(row.total_cost) }}</span></template>
            </el-table-column>
            <el-table-column prop="cost_rate" label="成本率" width="100" align="right" sortable>
              <template #default="{ row }">
                <span :class="{ 'over-hours': row.cost_rate >= 30 }">{{ row.cost_rate }}%</span>
              </template>
            </el-table-column>
            <el-table-column prop="estimated_hours" label="预计工时" width="100" align="right">
              <template #default="{ row }">{{ row.estimated_hours != null ? fmt2(row.estimated_hours) : '-' }}</template>
            </el-table-column>
            <el-table-column prop="hours_usage_rate" label="工时使用率" width="110" align="right">
              <template #default="{ row }">
                <span v-if="row.hours_usage_rate != null" :class="{ 'over-hours': row.hours_usage_rate > 100 }">
                  {{ row.hours_usage_rate }}%
                </span>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column prop="month_count" label="涉及月数" width="90" align="center" />
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- ============ 录入/编辑月度成本对话框 ============ -->
    <el-dialog v-model="editVisible" :title="editForm.id ? '编辑月度成本' : '录入月度成本'" width="560px">
      <el-form :model="editForm" label-width="130px">
        <el-form-item label="部门" required>
          <el-select v-model="editForm.dept" style="width: 100%" :disabled="!!editForm.id">
            <el-option v-for="d in DEPTS" :key="d" :label="d" :value="d" />
          </el-select>
        </el-form-item>
        <el-form-item label="月份" required>
          <el-date-picker v-model="editForm.month" type="month" value-format="YYYY-MM" style="width: 100%"
                          :disabled="!!editForm.id" placeholder="选择月份" />
        </el-form-item>
        <el-form-item label="考勤总工时" required>
          <el-input-number v-model="editForm.total_hours" :min="0.5" :precision="2" :step="8" style="width: 100%" />
        </el-form-item>
        <el-divider content-position="left">当月人力成本（元）</el-divider>
        <el-form-item v-for="f in COST_FIELDS" :key="f.key" :label="f.label">
          <el-input-number v-model="editForm[f.key]" :min="0" :precision="2" :step="1000" style="width: 100%"
                           placeholder="0.00" :controls="false" />
        </el-form-item>
        <el-form-item label="成本合计">
          <span class="cost-sum">{{ fmt2(editTotalCost) }} 元</span>
          <span class="unit-cost" v-if="editForm.total_hours > 0">
            （单工时成本 {{ (editTotalCost / editForm.total_hours).toFixed(2) }} 元）
          </span>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="editForm.note" type="textarea" :rows="2" placeholder="选填" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveMonth">保存</el-button>
      </template>
    </el-dialog>

    <!-- ============ 工时分配抽屉 ============ -->
    <el-drawer v-model="allocVisible" :title="`工时分配 — ${allocMonth.dept || ''} ${allocMonth.month || ''}`"
               size="78%">
      <div class="alloc-stats" v-if="allocMonth.id">
        <el-descriptions :column="5" border size="small">
          <el-descriptions-item label="总工时">{{ fmt2(allocMonth.total_hours) }}</el-descriptions-item>
          <el-descriptions-item label="人力成本合计">{{ fmt2(allocMonth.total_cost) }} 元</el-descriptions-item>
          <el-descriptions-item label="单工时成本">
            {{ allocMonth.unit_cost ? allocMonth.unit_cost.toFixed(2) : '-' }} 元
          </el-descriptions-item>
          <el-descriptions-item label="已分配工时">{{ fmt2(allocMonth.allocated_hours) }}</el-descriptions-item>
          <el-descriptions-item label="未分配工时">
            <span :class="{ 'over-hours': allocMonth.remaining_hours < 0 }">
              {{ fmt2(allocMonth.remaining_hours) }}
            </span>
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <div class="alloc-toolbar">
        <el-select v-model="allocStatusFilter" placeholder="全部状态" clearable style="width: 120px"
                   @change="onFilterChange">
          <el-option label="全部" value="" />
          <el-option label="执行中" value="执行中" />
          <el-option label="已完成" value="已完成" />
        </el-select>
        <el-input v-model="allocSearch" placeholder="搜索合同名称 / 编号 / 客户" clearable style="width: 260px"
                  :prefix-icon="Search" @input="onFilterChange" @clear="onFilterChange" />
        <span class="alloc-hint">默认展示所有执行中+已完成合同，可按状态筛选</span>
        <span class="alloc-sum">
          本次已填：{{ fmt2(allocSum) }} / {{ fmt2(allocMonth.total_hours) }} 工时
          <el-tag :type="allocOver ? 'danger' : 'success'" size="small" style="margin-left: 8px">
            {{ allocOver ? '超出总工时' : `剩余 ${fmt2(allocMonth.total_hours - allocSum)}` }}
          </el-tag>
          <span class="alloc-cost" v-if="allocMonth.unit_cost">
            ｜分摊金额：{{ fmt2(allocSum * allocMonth.unit_cost) }} 元
          </span>
        </span>
      </div>

      <el-table :data="filteredAllocContracts" v-loading="allocLoading" border max-height="520" size="small">
        <el-table-column type="index" label="#" width="50" align="center" />
        <el-table-column prop="contract_name" label="合同名称" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.contract_name }}
            <el-tag v-if="row.status === '已完成'" type="info" size="small" style="margin-left: 6px">已完成</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="contract_no" label="编号" width="130" show-overflow-tooltip>
          <template #default="{ row }">{{ row.contract_no || '-' }}</template>
        </el-table-column>
        <el-table-column prop="customer_name" label="客户" width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.customer_name || '-' }}</template>
        </el-table-column>
        <el-table-column prop="owner_name" label="负责人" width="85" align="center">
          <template #default="{ row }">{{ row.owner_name || '-' }}</template>
        </el-table-column>
        <el-table-column prop="total_amt" label="合同额(元)" width="120" align="right">
          <template #default="{ row }">{{ fmt2(row.total_amt) }}</template>
        </el-table-column>
        <el-table-column prop="estimated_hours" label="预计工时" width="100" align="center">
          <template #default="{ row }">{{ row.estimated_hours != null ? fmt2(row.estimated_hours) : '-' }}</template>
        </el-table-column>
        <el-table-column prop="total_allocated_hours" label="已分配工时" width="110" align="center">
          <template #default="{ row }">{{ fmt2(row.total_allocated_hours) }}</template>
        </el-table-column>
        <el-table-column label="剩余可分配" width="110" align="center">
          <template #default="{ row }">
            <span v-if="row.estimated_hours != null" :class="{ 'over-hours': row.estimated_hours - row.total_allocated_hours < 0 }">
              {{ fmt2(row.estimated_hours - row.total_allocated_hours) }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="本月分配工时" width="150" align="center">
          <template #default="{ row }">
            <el-input-number v-model="row.edit_hours" :min="0" :precision="2" :step="8" size="small"
                             :controls="false" style="width: 120px" />
          </template>
        </el-table-column>
        <el-table-column label="分摊金额(元)" width="120" align="right">
          <template #default="{ row }">
            {{ row.edit_hours > 0 && allocMonth.unit_cost ? fmt2(row.edit_hours * allocMonth.unit_cost) : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="160">
          <template #default="{ row }">
            <el-input v-model="row.edit_note" size="small" placeholder="选填" />
          </template>
        </el-table-column>
      </el-table>

      <div class="alloc-footer">
        <el-button @click="allocVisible = false">关闭</el-button>
        <el-button v-if="canManage" type="primary" :loading="allocSaving" :disabled="allocOver" @click="saveAlloc">
          保存分配
        </el-button>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { useAuthStore } from '../stores/auth'
import api from '../api'

const authStore = useAuthStore()
const canManage = computed(() => authStore.has('workhour.manage'))

const DEPTS = ['技术中心', '应用中心']
const COST_FIELDS = [
  { key: 'salary', label: '工资' },
  { key: 'pension', label: '社保-单位养老' },
  { key: 'medical', label: '社保-单位医疗' },
  { key: 'unemployment', label: '社保-单位失业' },
  { key: 'injury', label: '社保-单位工伤' },
  { key: 'annuity', label: '单位年金' },
  { key: 'housing_fund', label: '单位公积金' },
  { key: 'labor_fee', label: '劳务费' },
  { key: 'welfare', label: '福利费' },
  { key: 'supplement', label: '补充险' },
]

const activeTab = ref('months')
const loading = ref(false)
const months = ref([])
const filterDept = ref('')
const filterYear = ref('')

const summaryLoading = ref(false)
const summaryItems = ref([])
const summaryTotals = ref({ hours: 0, cost: 0 })
const summaryYear = ref('')
const summaryDept = ref('')
const summaryMode = ref('contract')
const summaryMonth = ref('')
const detailItems = ref([])
const detailTotals = ref({ hours: 0, cost: 0 })

const editVisible = ref(false)
const saving = ref(false)
const editForm = ref({})

const allocVisible = ref(false)
const allocLoading = ref(false)
const allocSaving = ref(false)
const allocMonth = ref({})
const allocContracts = ref([])
const allocSearch = ref('')
const allocStatusFilter = ref('')

// ---------- 数据挖掘分析 ----------
const anaLoading = ref(false)
const anaYear = ref('')
const anaDept = ref('')
const anaKpis = ref({
  total_cost: 0, total_hours: 0, avg_unit_cost: 0, allocated_cost: 0,
  allocation_rate: 0, unallocated_cost: 0, project_cost: 0, project_hours: 0,
  project_count: 0, month_count: 0, dept_count: 0,
})
const anaInsights = ref([])
const anaDeptMonthly = ref([])
const anaProjects = ref([])
const anaComposition = ref([])
const anaCostChart = ref(null)
const anaPieChart = ref(null)
const anaProjChart = ref(null)
let anaCostIns = null
let anaPieIns = null
let anaProjIns = null

const DEPT_COLORS = { '技术中心': '#409EFF', '应用中心': '#E6A23C' }
const LINE_COLORS = ['#5470c6', '#ee6666', '#91cc75']

function fmt2(v) {
  const n = Number(v) || 0
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ---------- 月度成本 ----------
async function loadMonths() {
  loading.value = true
  try {
    const params = {}
    if (filterDept.value) params.dept = filterDept.value
    if (filterYear.value) params.year = filterYear.value
    const res = await api.get('/work-cost/months', params)
    months.value = res.data || []
  } catch (e) {
    ElMessage.error('加载月度成本失败')
  } finally {
    loading.value = false
  }
}

const editTotalCost = computed(() =>
  COST_FIELDS.reduce((s, f) => s + (Number(editForm.value[f.key]) || 0), 0)
)

function openEdit(row) {
  if (row) {
    editForm.value = {
      id: row.id, dept: row.dept, month: row.month,
      total_hours: row.total_hours, note: row.note || '',
      ...Object.fromEntries(COST_FIELDS.map(f => [f.key, Number(row[f.key]) || 0])),
    }
  } else {
    const now = new Date()
    const m = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
    editForm.value = {
      id: null, dept: '应用中心', month: m, total_hours: null, note: '',
      ...Object.fromEntries(COST_FIELDS.map(f => [f.key, null])),
    }
  }
  editVisible.value = true
}

async function saveMonth() {
  const f = editForm.value
  if (!f.dept || !f.month) { ElMessage.warning('请选择部门和月份'); return }
  if (!f.total_hours || f.total_hours <= 0) { ElMessage.warning('请填写考勤总工时'); return }
  if (editTotalCost.value <= 0) { ElMessage.warning('至少填写一项人力成本'); return }
  saving.value = true
  try {
    const body = { dept: f.dept, month: f.month, total_hours: f.total_hours, note: f.note }
    for (const cf of COST_FIELDS) {
      if (f[cf.key] !== null && f[cf.key] !== undefined) body[cf.key] = f[cf.key]
    }
    const res = await api.post('/work-cost/months', body)
    if (res.code === 200) {
      ElMessage.success(res.message || '已保存')
      editVisible.value = false
      loadMonths()
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function removeMonth(row) {
  const ok = await ElMessageBox.confirm(
    `删除 ${row.dept} ${row.month} 的月度成本？该月的工时分配明细将一并删除，分摊汇总随之减少。`,
    '确认删除', { type: 'warning' }
  ).catch(() => null)
  if (!ok) return
  try {
    const res = await api.delete(`/work-cost/months/${row.id}`)
    if (res.code === 200) { ElMessage.success('已删除'); loadMonths() }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '删除失败')
  }
}

// ---------- 工时分配 ----------
async function openAlloc(row) {
  allocMonth.value = row
  allocVisible.value = true
  allocLoading.value = true
  allocSearch.value = ''
  allocStatusFilter.value = ''
  try {
    const res = await api.get(`/work-cost/months/${row.id}/contracts`)
    allocMonth.value = res.data.month_cost
    allocContracts.value = (res.data.contracts || []).map(c => ({
      ...c, edit_hours: Number(c.alloc_hours) || 0, edit_note: c.alloc_note || '',
    }))
  } catch (e) {
    ElMessage.error('加载合同列表失败')
  } finally {
    allocLoading.value = false
  }
}

function onFilterChange() {
  // 纯前端过滤，无需重新请求
}

const filteredAllocContracts = computed(() => {
  let list = allocContracts.value
  if (allocStatusFilter.value) {
    list = list.filter(c => c.status === allocStatusFilter.value)
  }
  const kw = (allocSearch.value || '').trim().toLowerCase()
  if (kw) {
    list = list.filter(c =>
      [c.contract_name, c.contract_no, c.customer_name].some(v => (v || '').toLowerCase().includes(kw)))
  }
  return list
})

const allocSum = computed(() =>
  Math.round(allocContracts.value.reduce((s, c) => s + (Number(c.edit_hours) || 0), 0) * 100) / 100
)
const allocOver = computed(() => allocSum.value > (Number(allocMonth.value.total_hours) || 0) + 0.009)

async function saveAlloc() {
  const items = allocContracts.value
    .filter(c => Number(c.edit_hours) > 0)
    .map(c => ({ contract_id: c.id, hours: c.edit_hours, note: c.edit_note }))
  if (allocOver.value) { ElMessage.error('分配工时合计超过本月总工时'); return }
  allocSaving.value = true
  try {
    const res = await api.post(`/work-cost/months/${allocMonth.value.id}/allocate`, { items })
    if (res.code === 200) {
      ElMessage.success(res.message || '已保存')
      allocVisible.value = false
      loadMonths()
      if (activeTab.value === 'summary') loadSummary()
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '保存失败')
  } finally {
    allocSaving.value = false
  }
}

// ---------- 分摊汇总 ----------
async function loadSummary() {
  summaryLoading.value = true
  try {
    if (summaryMode.value === 'monthly') {
      const params = {}
      if (summaryMonth.value) params.month = summaryMonth.value
      if (summaryDept.value) params.dept = summaryDept.value
      const res = await api.get('/work-cost/detail', params)
      detailItems.value = res.data?.items || []
      detailTotals.value = res.data?.totals || { hours: 0, cost: 0 }
    } else {
      const params = {}
      if (summaryYear.value) params.year = summaryYear.value
      if (summaryDept.value) params.dept = summaryDept.value
      const res = await api.get('/work-cost/summary', params)
      summaryItems.value = res.data?.items || []
      summaryTotals.value = res.data?.totals || { hours: 0, cost: 0 }
    }
  } catch (e) {
    ElMessage.error('加载分摊汇总失败')
  } finally {
    summaryLoading.value = false
  }
}

function detailTotal({ columns }) {
  return columns.map((col, i) => {
    if (i === 0) return '合计'
    if (col.property === 'hours') return fmt2(detailTotals.value.hours)
    if (col.property === 'alloc_cost') return fmt2(detailTotals.value.cost)
    return ''
  })
}

async function exportExcel() {
  try {
    const params = new URLSearchParams()
    if (summaryYear.value) params.set('year', summaryYear.value)
    if (summaryDept.value) params.set('dept', summaryDept.value)
    const qs = params.toString()
    const resp = await fetch(`/api/work-cost/summary/export${qs ? '?' + qs : ''}`, {
      headers: { Authorization: `Bearer ${localStorage.getItem('crm_token')}` },
    })
    if (!resp.ok) throw new Error('导出失败')
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = decodeURIComponent(resp.headers.get('content-disposition') || '').split("''").pop() || '工时成本分摊.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error('导出失败：' + e.message)
  }
}

// ---------- 数据挖掘分析 ----------
async function loadAnalysis() {
  anaLoading.value = true
  try {
    const params = {}
    if (anaYear.value) params.year = anaYear.value
    if (anaDept.value) params.dept = anaDept.value
    const res = await api.get('/work-cost/analysis', params)
    const d = res.data || {}
    anaKpis.value = d.kpis || anaKpis.value
    anaInsights.value = d.insights || []
    anaDeptMonthly.value = d.dept_monthly || []
    anaProjects.value = d.project_costs || []
    anaComposition.value = d.cost_composition || []
    if (activeTab.value === 'analysis') nextTick(renderAnalysisCharts)
  } catch (e) {
    ElMessage.error('加载数据分析失败')
  } finally {
    anaLoading.value = false
  }
}

function renderAnalysisCharts() {
  renderCostChart()
  renderPieChart()
  renderProjChart()
}

// 部门月度人力成本（柱）+ 单工时成本（折线，双Y轴）
function renderCostChart() {
  if (!anaCostChart.value) return
  if (!anaCostIns) anaCostIns = echarts.init(anaCostChart.value)
  const rows = anaDeptMonthly.value
  const months = [...new Set(rows.map(r => r.month))].sort()
  const depts = [...new Set(rows.map(r => r.dept))]
  const series = []
  depts.forEach(dep => {
    series.push({
      name: `${dep} 人力成本`, type: 'bar', yAxisIndex: 0, barMaxWidth: 26,
      itemStyle: { color: DEPT_COLORS[dep] || '#909399' },
      data: months.map(m => {
        const r = rows.find(x => x.month === m && x.dept === dep)
        return r ? r.total_cost : null
      }),
    })
  })
  depts.forEach((dep, i) => {
    series.push({
      name: `${dep} 单工时成本`, type: 'line', yAxisIndex: 1, smooth: true, symbolSize: 6,
      lineStyle: { type: 'dashed', width: 2 }, itemStyle: { color: LINE_COLORS[i % LINE_COLORS.length] },
      data: months.map(m => {
        const r = rows.find(x => x.month === m && x.dept === dep)
        return r ? r.unit_cost : null
      }),
    })
  })
  anaCostIns.setOption({
    tooltip: {
      trigger: 'axis',
      valueFormatter: v => (v == null ? '-' : Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })),
    },
    legend: { type: 'scroll', top: 0 },
    grid: { left: 70, right: 60, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: months },
    yAxis: [
      { type: 'value', name: '成本(元)', axisLabel: { formatter: v => Number(v).toLocaleString('zh-CN') } },
      { type: 'value', name: '单工时成本(元)' },
    ],
    series,
  }, true)
  anaCostIns.resize()
}

// 人力成本构成占比（饼图）
function renderPieChart() {
  if (!anaPieChart.value) return
  if (!anaPieIns) anaPieIns = echarts.init(anaPieChart.value)
  const data = anaComposition.value.map(c => ({ name: c.name, value: c.amount }))
  anaPieIns.setOption({
    tooltip: {
      trigger: 'item',
      formatter: p => `${p.name}<br/>${Number(p.value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} 元（${p.percent}%）`,
    },
    legend: { type: 'scroll', orient: 'vertical', right: 10, top: 20, bottom: 20 },
    series: [{
      type: 'pie', radius: ['42%', '68%'], center: ['38%', '52%'],
      avoidLabelOverlap: true,
      label: { formatter: '{b}\n{d}%', fontSize: 11 },
      data,
    }],
  }, true)
  anaPieIns.resize()
}

// 项目工时成本 Top20（横向柱状）
function renderProjChart() {
  if (!anaProjChart.value) return
  if (!anaProjIns) anaProjIns = echarts.init(anaProjChart.value)
  const top = [...anaProjects.value].sort((a, b) => b.total_cost - a.total_cost).slice(0, 20).reverse()
  const names = top.map(p => (p.contract_name || '').length > 16 ? p.contract_name.slice(0, 16) + '…' : p.contract_name)
  anaProjIns.setOption({
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      formatter: ps => {
        const p = top[ps[0].dataIndex]
        return `<b>${p.contract_name}</b><br/>工时成本：${fmt2(p.total_cost)} 元<br/>累计工时：${fmt2(p.total_hours)}<br/>合同额：${fmt2(p.total_amt)} 元<br/>成本率：${p.cost_rate}%`
      },
    },
    grid: { left: 140, right: 90, top: 20, bottom: 20 },
    xAxis: { type: 'value', name: '工时成本(元)', axisLabel: { formatter: v => Number(v).toLocaleString('zh-CN') } },
    yAxis: { type: 'category', data: names, axisLabel: { fontSize: 11 } },
    series: [{
      type: 'bar', barMaxWidth: 16,
      itemStyle: { color: '#409EFF' },
      label: { show: true, position: 'right', fontSize: 11, formatter: p => fmt2(p.value) },
      data: top.map(p => p.total_cost),
    }],
  }, true)
  anaProjIns.resize()
}

function anaMonthlySummary({ columns }) {
  return columns.map((col, i) => {
    if (i === 0) return '合计'
    const keys = ['total_hours', 'total_cost', 'allocated_hours', 'allocated_cost', 'unallocated_cost']
    if (keys.includes(col.property)) {
      const s = anaDeptMonthly.value.reduce((acc, r) => acc + (Number(r[col.property]) || 0), 0)
      return fmt2(s)
    }
    return ''
  })
}

function anaProjectSummary({ columns }) {
  return columns.map((col, i) => {
    if (i === 0) return '合计'
    if (col.property === 'total_amt') {
      return fmt2(anaProjects.value.reduce((s, r) => s + (Number(r.total_amt) || 0), 0))
    }
    if (col.property === 'total_hours') {
      return fmt2(anaProjects.value.reduce((s, r) => s + (Number(r.total_hours) || 0), 0))
    }
    if (col.property === 'total_cost') {
      return fmt2(anaProjects.value.reduce((s, r) => s + (Number(r.total_cost) || 0), 0))
    }
    return ''
  })
}

function onAnaResize() {
  [anaCostIns, anaPieIns, anaProjIns].forEach(c => c && c.resize())
}

watch(activeTab, val => {
  if (val === 'analysis') {
    if (!anaDeptMonthly.value.length) loadAnalysis()
    else nextTick(renderAnalysisCharts)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onAnaResize)
  ;[anaCostIns, anaPieIns, anaProjIns].forEach(c => { if (c) c.dispose() })
  anaCostIns = anaPieIns = anaProjIns = null
})

// ---------- 合计行 ----------
function monthsSummary({ columns }) {
  return columns.map((col, i) => {
    if (i === 0) return '合计'
    const keys = ['total_hours', 'total_cost', 'allocated_hours', 'allocated_cost']
    if (keys.includes(col.property)) {
      const s = months.value.reduce((acc, r) => acc + (Number(r[col.property]) || 0), 0)
      return fmt2(s)
    }
    return ''
  })
}

function summaryTotal({ columns }) {
  return columns.map((col, i) => {
    if (i === 0) return '合计'
    if (col.property === 'total_hours') return fmt2(summaryTotals.value.hours)
    if (col.property === 'total_cost') return fmt2(summaryTotals.value.cost)
    return ''
  })
}

onMounted(() => {
  loadMonths()
  loadSummary()
  loadAnalysis()
  window.addEventListener('resize', onAnaResize)
})
</script>

<style scoped>
.work-cost { padding: 8px 4px; }
.toolbar { display: flex; gap: 10px; align-items: center; margin-bottom: 14px; }
.hint { color: #909399; font-size: 12px; margin-top: 10px; line-height: 1.7; }
.unit-cost { color: #e6a23c; font-weight: 600; }
.cost { color: #f56c6c; font-weight: 600; }
.cost-sum { color: #f56c6c; font-weight: 700; font-size: 15px; }
.over-hours { color: #f56c6c; font-weight: 700; }
.alloc-stats { margin-bottom: 12px; }
.alloc-toolbar { display: flex; align-items: center; gap: 12px; margin: 4px 0 10px; flex-wrap: wrap; }
.alloc-sum { font-size: 13px; color: #606266; }
.alloc-hint { font-size: 12px; color: #909399; }
.alloc-cost { color: #f56c6c; font-weight: 600; }
.alloc-footer { margin-top: 14px; display: flex; justify-content: flex-end; gap: 10px; }

/* ---------- 数据挖掘分析 ---------- */
.ana-hint { font-size: 12px; color: #909399; }
.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 14px; }
.kpi-card {
  background: linear-gradient(135deg, #f7f9fc, #eef3fa);
  border: 1px solid #e4eaf2; border-radius: 8px; padding: 14px 16px;
}
.kpi-label { font-size: 13px; color: #606266; margin-bottom: 6px; }
.kpi-value { font-size: 22px; font-weight: 700; color: #1f4e79; line-height: 1.3; }
.kpi-unit { font-size: 12px; font-weight: 400; color: #909399; margin-left: 4px; }
.kpi-sub { font-size: 12px; color: #909399; margin-top: 6px; }
.insight-card {
  background: #fdf6ec; border: 1px solid #f5dab1; border-radius: 8px;
  padding: 12px 16px; margin-bottom: 14px;
}
.insight-title { font-weight: 700; color: #e6a23c; margin-bottom: 6px; }
.insight-list { margin: 0; padding-left: 20px; }
.insight-list li { font-size: 13px; color: #606266; line-height: 1.9; }
.chart-row { display: grid; grid-template-columns: 1.4fr 1fr; gap: 12px; }
.chart-card {
  background: #fff; border: 1px solid #ebeef5; border-radius: 8px;
  padding: 10px 12px; margin-bottom: 14px;
}
.chart-title { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 4px; }
.chart { width: 100%; height: 320px; }
.table-title { font-size: 13px; font-weight: 600; color: #303133; margin: 6px 0 8px; }
@media (max-width: 1200px) {
  .kpi-row { grid-template-columns: repeat(2, 1fr); }
  .chart-row { grid-template-columns: 1fr; }
}
</style>
