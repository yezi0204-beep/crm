<template>
  <div class="appraisal-page">
    <div class="page-header">
      <h2 class="page-title">{{ t('appraisal.title') }}（应用中心）</h2>
      <div class="header-actions">
        <el-date-picker
          v-model="yearMonthPicker"
          type="month"
          format="YYYY 年 MM 月"
          value-format="YYYY-MM"
          :clearable="false"
          style="width: 180px; margin-right: 10px;"
          :disabled-date="disabledFuture"
          @change="loadOverview"
        />
        <el-button
          v-if="isAdmin"
          type="primary"
          :icon="Download"
          :loading="exporting"
          @click="handleExport"
        >{{ t('appraisal.export') }}</el-button>
      </div>
    </div>

    <!-- 角色提示：非应用中心且非管理/人力角色 -->
    <el-alert
      v-if="!isAppraisalDept && !canViewAppraisal"
      type="info"
      show-icon
      :closable="false"
      style="margin-bottom: 16px;"
      :title="t('appraisal.nonAppraisalDeptTip')"
    />

    <el-tabs v-model="activeTab" class="appraisal-tabs">
      <!-- Tab 1: 月度考核总览（主任/院长/人力可见，人力只读） -->
      <el-tab-pane
        :label="t('appraisal.tabOverview')"
        name="overview"
        v-if="canViewAppraisal"
      >
        <!-- 顶部指标卡片 -->
        <el-row :gutter="16" class="stat-row" style="margin-bottom: 16px;">
          <el-col :span="6">
            <el-card shadow="hover" class="stat-card card-primary">
              <div class="stat-label">部门当月指标</div>
              <div class="stat-value">{{ formatMoney(overview.dept_monthly_target) }}</div>
              <div style="color:#909399; font-size:12px; margin-top:4px;">
                {{ overview.year }}年{{ overview.month }}月
              </div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="hover" class="stat-card card-success">
              <div class="stat-label">部门累计新签</div>
              <div class="stat-value highlight">{{ formatMoney(overview.dept_cumulative_actual) }}</div>
              <div style="color:#909399; font-size:12px; margin-top:4px;">
                2月至{{ overview.month }}月累计
              </div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="hover" class="stat-card card-warning">
              <div class="stat-label">部门当月完成率</div>
              <div class="stat-value highlight">{{ formatPct(overview.dept_rate_pct) }}</div>
              <el-progress
                :percentage="clampRate(overview.dept_rate_pct)"
                :stroke-width="8"
                style="margin-top: 6px;"
                :status="rateStatus(overview.dept_rate_pct)"
              />
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="hover" class="stat-card card-info">
              <div class="stat-label">{{ t('appraisal.cardAvgSalesRate') }}</div>
              <div class="stat-value highlight">{{ formatPct(overview.avg_sales_rate_pct) }}</div>
              <el-progress
                :percentage="Number(overview.avg_sales_rate_pct || 0) > 150 ? 150 : Number(overview.avg_sales_rate_pct || 0)"
                :stroke-width="8"
                style="margin-top: 6px;"
                :status="rateStatus(overview.avg_sales_rate_pct)"
              />
            </el-card>
          </el-col>
        </el-row>

        <div class="table-card">
          <div class="table-toolbar">
            <div class="toolbar-left">
              <el-input
                v-model="overviewFilter"
                :placeholder="t('appraisal.searchPlaceholder')"
                clearable
                style="width: 260px;"
              >
                <template #prefix>🔍</template>
              </el-input>
            </div>
            <div class="toolbar-right">
              <el-tag type="danger" style="margin-right: 8px;">销售完成率封顶150%</el-tag>
              <el-tag type="info">非销售按销售均值计算</el-tag>
            </div>
          </div>

          <el-table
            :data="filteredOverviewRows"
            border
            stripe
            style="width: 100%;"
            v-loading="loadingOverview"
            row-key="username"
            empty-text="暂无数据（请确认年份和月份，或为用户配置指标）"
          >
            <el-table-column label="姓名" width="100" fixed>
              <template #default="{row}">
                <strong>{{ row.name }}</strong>
                <el-tag
                  size="small"
                  :type="row.is_director ? 'warning' : (row.is_sales ? 'danger' : 'info')"
                  style="margin-left:4px;"
                >{{ row.is_director ? '主任(部门)' : (row.is_sales ? '销售' : '非销售') }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="role" label="角色" width="80" />
            <el-table-column prop="status" label="状态" width="80">
              <template #default="{row}">
                <el-tag :type="row.status==='离职' ? 'info' : 'success'" size="small">{{ row.status || '在职' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="年度指标" width="110" align="right">
              <template #default="{row}">{{ formatMoney(row.annual_target_amount) }}</template>
            </el-table-column>
            <el-table-column label="当月指标" width="110" align="right">
              <template #default="{row}">{{ formatMoney(row.monthly_target_amt) }}</template>
            </el-table-column>
            <el-table-column label="累计实际" width="110" align="right">
              <template #default="{row}">{{ formatMoney(row.cumulative_actual_amt) }}</template>
            </el-table-column>
            <el-table-column label="完成率(%)" width="150" fixed="right">
              <template #default="{row}">
                <div style="display:flex; align-items:center; justify-content:space-between;">
                  <strong :style="{color: rateColor(row.rate_pct)}">{{ formatPct(row.rate_pct) }}</strong>
                  <span style="color:#999; font-size:12px;">
                    {{ row.is_sales ? '(个人)' : '(均值)' }}
                  </span>
                </div>
                <el-progress
                  :percentage="clampRate(row.rate_pct)"
                  :stroke-width="6"
                  :color="rateColor(row.rate_pct)"
                />
              </template>
            </el-table-column>
            <el-table-column label="基本工资" width="110" align="right" fixed="right">
              <template #default="{row}">{{ formatMoney(row.basic_salary) }}</template>
            </el-table-column>
            <el-table-column label="基础绩效" width="110" align="right" fixed="right">
              <template #default="{row}">{{ formatMoney(row.base_performance) }}</template>
            </el-table-column>
            <el-table-column label="绩效工资" width="110" align="right" fixed="right">
              <template #default="{row}">
                <span style="color:#e6a23c; font-weight:600;">{{ formatMoney(row.perf_pay) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="月应发合计" width="120" align="right" fixed="right">
              <template #default="{row}">
                <strong style="color:#409eff;">{{ formatMoney(row.total_pay) }}</strong>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="160" fixed="right" v-if="canViewAppraisal">
              <template #default="{row}">
                <el-button link type="primary" size="small" @click="openDetails(row)">
                  明细
                </el-button>
                <el-button v-if="isAdmin" link type="warning" size="small" @click="openConfig(row)">
                  {{ t('appraisal.configure') }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- Tab 2: 年度完成率趋势（主任/院长可见） -->
      <el-tab-pane
        label="年度完成率趋势"
        name="yearly"
        v-if="isAdmin"
      >
        <div class="table-card" v-loading="loadingYearly">
          <div class="table-toolbar">
            <div class="toolbar-left">
              <el-date-picker
                v-model="yearlyYearPicker"
                type="year"
                format="YYYY 年"
                value-format="YYYY"
                :clearable="false"
                style="width: 140px;"
                @change="loadYearly"
              />
              <el-tag type="warning" style="margin-left: 12px;">部门完成率 = 主任完成率（承担部门指标）</el-tag>
              <el-tag type="danger" style="margin-left: 8px;">销售完成率封顶150%</el-tag>
            </div>
            <div class="toolbar-right">
              <el-tag type="info">1月新签已在去年结算，累计实际从2月起算</el-tag>
            </div>
          </div>
          <el-table
            :data="yearlyTableRows"
            border
            stripe
            style="width: 100%;"
            row-key="rowKey"
            :cell-class-name="yearlyCellClass"
          >
            <el-table-column label="姓名" width="140" fixed>
              <template #default="{row}">
                <strong v-if="row.isDept" style="color:#e6a23c;">{{ row.name }}</strong>
                <span v-else>{{ row.name }}</span>
                <el-tag
                  v-if="row.isDept"
                  size="small"
                  type="warning"
                  style="margin-left:4px;"
                >部门</el-tag>
                <el-tag
                  v-else
                  size="small"
                  type="danger"
                  style="margin-left:4px;"
                >销售</el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-for="m in 12"
              :key="m"
              :label="`${m}月`"
              width="110"
              align="center"
            >
              <template #default="{row}">
                <span
                  v-if="row.rates[String(m)] !== null && row.rates[String(m)] !== undefined"
                  :style="{color: rateColor(row.rates[String(m)]), fontWeight: row.isDept ? 700 : 400}"
                >{{ formatPct(row.rates[String(m)]) }}</span>
                <span v-else style="color:#c0c4cc;">-</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- Tab 3: 指标配置（主任/院长可见） -->
      <el-tab-pane
        :label="t('appraisal.tabConfig')"
        name="config"
        v-if="isAdmin"
      >
        <el-row :gutter="16">
          <el-col :span="8">
            <el-card shadow="never">
              <template #header>
                <div style="display:flex; justify-content: space-between; align-items: center;">
                  <strong>{{ t('appraisal.selectUser') }}</strong>
                </div>
              </template>
              <el-input
                v-model="userFilter"
                :placeholder="t('appraisal.searchPlaceholder')"
                clearable
                style="margin-bottom: 12px;"
              >
                <template #prefix>🔍</template>
              </el-input>
              <div class="user-list">
                <div
                  v-for="u in filteredUserList"
                  :key="u.username"
                  class="user-item"
                  :class="{active: configUsername === u.username}"
                  @click="selectUser(u)"
                >
                  <div class="user-item-name">
                    {{ u.name || u.username }}
                    <el-tag
                      size="small"
                      :type="u.role==='主任' ? 'warning' : (u.role==='销售' ? 'danger' : 'info')"
                      style="margin-left:6px;"
                    >{{ u.role }}</el-tag>
                    <el-tag
                      v-if="u.is_sales_override"
                      size="small"
                      type="danger"
                      effect="plain"
                      style="margin-left:4px;"
                    >强销售</el-tag>
                  </div>
                  <div class="user-item-sub">{{ u.department || '-' }} · {{ u.username }}</div>
                </div>
              </div>
            </el-card>
          </el-col>
          <el-col :span="16">
            <el-card shadow="never" v-if="configUsername">
              <template #header>
                <div style="display:flex; justify-content: space-between; align-items: center;">
                  <strong>{{ t('appraisal.configTitle', {name: selectedUser?.name || configUsername, year: configYear}) }}</strong>
                  <el-date-picker
                    v-model="configYearPicker"
                    type="year"
                    format="YYYY 年"
                    value-format="YYYY"
                    :clearable="false"
                    style="width: 140px;"
                    @change="loadConfig"
                  />
                </div>
              </template>
              <el-form
                ref="configFormRef"
                :model="configForm"
                label-width="140px"
                v-loading="loadingConfig"
              >
                <el-divider>{{ t('appraisal.coreFields') }}</el-divider>
                <el-row :gutter="12">
                  <el-col :span="12">
                    <el-form-item :label="t('appraisal.basicSalary')">
                      <el-input-number v-model="configForm.basic_salary" :min="0" :precision="2" :step="100" style="width:100%" />
                    </el-form-item>
                  </el-col>
                  <el-col :span="12">
                    <el-form-item :label="t('appraisal.basePerformance')">
                      <el-input-number v-model="configForm.base_performance" :min="0" :precision="2" :step="100" style="width:100%" />
                    </el-form-item>
                  </el-col>
                  <el-col :span="12">
                    <el-form-item :label="t('appraisal.annualTarget')">
                      <el-input-number v-model="configForm.annual_target_amount" :min="0" :precision="2" :step="10000" style="width:100%" />
                    </el-form-item>
                  </el-col>
                  <el-col :span="12">
                    <el-form-item :label="t('appraisal.isSalesOverride')">
                      <el-switch
                        v-model="configForm.is_sales_override"
                        :active-value="1"
                        :inactive-value="0"
                        :active-text="t('appraisal.yes')"
                        :inactive-text="t('appraisal.no')"
                      />
                      <div style="color:#909399; font-size:12px; line-height:1.4; margin-top:4px;">
                        {{ t('appraisal.salesOverrideHelp') }}
                      </div>
                    </el-form-item>
                  </el-col>
                </el-row>

                <el-divider>{{ t('appraisal.monthlyBreakdown') }}</el-divider>
                <div class="monthly-grid">
                  <div v-for="m in 12" :key="m" class="monthly-cell">
                    <div class="monthly-cell-header">{{ m }}月</div>
                    <el-input-number
                      :model-value="monthlyForm[m]"
                      @update:model-value="v => setMonthly(m, v)"
                      :min="0"
                      :precision="2"
                      :step="10000"
                      size="small"
                      style="width: 100%;"
                      :controls="false"
                    />
                    <div
                      v-if="monthlyForm[m] != defaultMonthly[m]"
                      class="monthly-override-tag"
                    >● {{ t('appraisal.overrideTag') }}</div>
                    <div v-else class="monthly-default-tag">· {{ t('appraisal.defaultTag') }} ({{ formatMoney(defaultMonthly[m]) }})</div>
                  </div>
                </div>

                <el-divider />
                <el-form-item>
                  <el-button type="primary" :loading="savingConfig" @click="saveConfig">
                    {{ t('appraisal.saveConfig') }}
                  </el-button>
                  <el-button @click="resetMonthlyToDefault">
                    {{ t('appraisal.resetDefault') }}
                  </el-button>
                </el-form-item>
              </el-form>
            </el-card>
            <el-card shadow="never" v-else>
              <el-empty :description="t('appraisal.selectUserHint')" />
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- Tab 4: 个人考核详情（所有登录用户可见） -->
      <el-tab-pane :label="t('appraisal.tabMine')" name="mine">
        <div v-loading="loadingMine">
          <el-row :gutter="16" class="stat-row">
            <el-col :span="12">
              <el-card shadow="hover" class="stat-card card-primary">
                <div class="stat-label">{{ t('appraisal.mineLabel') }}</div>
                <div class="stat-value">{{ mine?.name || '-' }}
                  <el-tag
                    size="small"
                    style="margin-left:8px;"
                    :type="mine?.is_sales ? 'danger' : 'info'"
                  >{{ mine?.is_sales ? '按销售考核' : '按非销售考核' }}</el-tag>
                </div>
                <div style="color:#909399; font-size:13px; margin-top:6px;">
                  {{ mine?.department || '-' }} · {{ mine?.role || '-' }}
                </div>
              </el-card>
            </el-col>
            <el-col :span="12">
              <el-card shadow="hover" class="stat-card card-warning">
                <div class="stat-label">{{ t('appraisal.myRate') }}</div>
                <div class="stat-value highlight" style="font-size: 36px;">{{ formatPct(mine?.rate_pct) }}</div>
                <el-progress
                  :percentage="clampRate(mine?.rate_pct)"
                  :stroke-width="10"
                  style="margin-top: 8px;"
                  :status="rateStatus(mine?.rate_pct)"
                />
                <div style="color:#909399; font-size:12px; margin-top:6px;">
                  {{ t('appraisal.avgSalesRateHint') }}{{ formatPct(overview.avg_sales_rate_pct) }}
                </div>
              </el-card>
            </el-col>
          </el-row>

          <el-card shadow="never" style="margin-top:16px;">
            <template #header><strong>{{ t('appraisal.salaryDetail') }}</strong></template>
            <el-descriptions :column="2" border size="default">
              <el-descriptions-item :label="t('appraisal.monthlyTarget')">
                {{ formatMoney(mine?.monthly_target_amt) }}
                <el-tag v-if="mine?.is_sales" size="small" type="danger" style="margin-left:8px;">累计目标</el-tag>
              </el-descriptions-item>
              <el-descriptions-item :label="t('appraisal.cumActual')">
                {{ formatMoney(mine?.cumulative_actual_amt) }}
                <el-button link type="primary" size="small" style="margin-left:8px;"
                  @click="openDetails(mine)">查看明细</el-button>
              </el-descriptions-item>
              <el-descriptions-item :label="t('appraisal.basicSalary')">
                {{ formatMoney(mine?.basic_salary) }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('appraisal.basePerformance')">
                {{ formatMoney(mine?.base_performance) }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('appraisal.perfPay')">
                <span style="color:#e6a23c; font-weight:700; font-size:16px;">{{ formatMoney(mine?.perf_pay) }}</span>
                <div style="color:#909399; font-size:12px; margin-top:4px;">
                  {{ formatMoney(mine?.base_performance) }} × {{ formatPct(mine?.rate_pct) }}
                </div>
              </el-descriptions-item>
              <el-descriptions-item :label="t('appraisal.totalPay')">
                <span style="color:#409eff; font-weight:800; font-size:20px;">¥ {{ formatMoney(mine?.total_pay) }}</span>
                <div style="color:#909399; font-size:12px; margin-top:4px;">
                  = {{ formatMoney(mine?.basic_salary) }} + {{ formatMoney(mine?.perf_pay) }}
                </div>
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 明细抽屉 -->
    <el-drawer
      v-model="detailsDrawer"
      :title="detailsTitle"
      direction="rtl"
      size="70%"
      destroy-on-close
    >
      <div v-loading="loadingDetails">
        <!-- 公式说明 -->
        <el-card shadow="never" style="margin-bottom:16px;" v-if="detailsData?.formula_explain?.length">
          <template #header><strong>计算公式</strong></template>
          <div v-for="(f, i) in detailsData.formula_explain" :key="i"
               style="font-family: monospace; font-size: 13px; line-height: 2; color: #303133;">
            {{ f }}
          </div>
        </el-card>

        <!-- 汇总 -->
        <el-card shadow="never" style="margin-bottom:16px;">
          <el-descriptions :column="3" border size="small">
            <el-descriptions-item label="姓名">{{ detailsData?.name }}</el-descriptions-item>
            <el-descriptions-item label="角色">{{ detailsData?.role }}</el-descriptions-item>
            <el-descriptions-item label="身份">
              <el-tag size="small" :type="detailsData?.is_director ? 'warning' : (detailsData?.is_sales ? 'danger' : 'info')">
                {{ detailsData?.is_director ? '主任(部门)' : (detailsData?.is_sales ? '销售' : '非销售') }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="考核月份">{{ detailsData?.year }}年{{ detailsData?.month }}月</el-descriptions-item>
            <el-descriptions-item label="累计实际">
              <span style="color:#e6a23c; font-weight:700; font-size:16px;">{{ formatMoney(detailsData?.total) }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="明细笔数">{{ detailsData?.items?.length || 0 }} 笔</el-descriptions-item>
          </el-descriptions>
        </el-card>

        <!-- 主任：部门成员明细 -->
        <el-card v-if="detailsData?.is_director && detailsData?.dept_members?.length"
                 shadow="never" style="margin-bottom:16px;">
          <template #header><strong>部门成员累计实际</strong>（主任=部门所有销售之和）</template>
          <el-table :data="detailsData.dept_members" border size="small">
            <el-table-column prop="name" label="姓名" width="100" />
            <el-table-column label="累计实际" width="120" align="right">
              <template #default="{row}">
                <strong style="color:#e6a23c;">{{ formatMoney(row.total) }}</strong>
              </template>
            </el-table-column>
            <el-table-column label="明细笔数" width="80" align="center">
              <template #default="{row}">{{ row.items.length }} 笔</template>
            </el-table-column>
            <el-table-column prop="username" label="用户名" />
          </el-table>
        </el-card>

        <!-- 项目明细表 -->
        <el-card shadow="never">
          <template #header><strong>项目明细与分成</strong></template>
          <el-table :data="detailsData?.items" border stripe size="small" empty-text="暂无明细">
            <el-table-column label="类型" width="130">
              <template #default="{row}">
                <el-tag size="small" :type="row.is_framework ? 'warning' : 'primary'">{{ row.type_name }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="contract_no" label="合同编号" width="130" show-overflow-tooltip />
            <el-table-column prop="contract_name" label="合同名称" min-width="180" show-overflow-tooltip />
            <el-table-column prop="sign_date" label="签订/验收日期" width="120">
              <template #default="{row}">{{ (row.sign_date||'').slice(0,10) }}</template>
            </el-table-column>
            <el-table-column label="基数" width="100" align="right">
              <template #default="{row}">{{ formatMoney(row.base_amount) }}</template>
            </el-table-column>
            <el-table-column prop="base_label" label="基数类型" width="80" align="center" />
            <el-table-column label="分成比例" width="90" align="right">
              <template #default="{row}">{{ row.my_ratio }}%</template>
            </el-table-column>
            <el-table-column label="分成金额" width="120" align="right">
              <template #default="{row}">
                <strong style="color:#e6a23c;">{{ formatMoney(row.my_amount) }}</strong>
              </template>
            </el-table-column>
            <el-table-column prop="formula" label="计算公式" min-width="200">
              <template #default="{row}">
                <code style="font-size:12px; color:#606266;">{{ row.formula }}</code>
              </template>
            </el-table-column>
            <el-table-column label="分成方式" width="90" align="center">
              <template #default="{row}">
                <el-tag size="small" :type="row.commission_type==='none' ? 'info' : 'success'">
                  {{ row.commission_type==='contract' ? '合同级' : (row.commission_type==='acceptance' ? '验收级' : '独享') }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch, onBeforeUnmount } from 'vue'
import { storeToRefs } from 'pinia'
import { Download } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { translate } from '../locales'
import api from '../api'
import { useAuthStore } from '../stores/auth'
import { useSettingsStore } from '../stores/settings'

const authStore = useAuthStore()
const settingsStore = useSettingsStore()
const { language } = storeToRefs(settingsStore)
const t = (key, params = null) => translate(language.value, key, params)

// --- 权限 ---
const isAdmin = computed(() => ['主任', '院长'].includes(authStore.role))
// 月度考核总览查看权限：主任/院长/人力（人力只能看总览，不能配置/导出/看年度趋势）
const canViewAppraisal = computed(() => ['主任', '院长', '人力'].includes(authStore.role))
const isAppraisalDept = computed(() => authStore.department === '应用中心')

// --- 公共状态 ---
const activeTab = ref(canViewAppraisal.value ? 'overview' : 'mine')
const now = new Date()
const yearMonthPicker = ref(`${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}`)
const loadingOverview = ref(false)
const loadingMine = ref(false)
const exporting = ref(false)

const overview = reactive({
  year: now.getFullYear(), month: now.getMonth()+1,
  avg_sales_rate_pct: 0,
  dept_rate_pct: null,
  dept_monthly_target: 0,
  dept_cumulative_actual: 0,
  rows: []
})

const stats = computed(() => ({
  salesCount: overview.rows.filter(r => r.is_sales).length,
  deptCount: overview.rows.length,
}))

const overviewFilter = ref('')
const filteredOverviewRows = computed(() => {
  const kw = overviewFilter.value.trim().toLowerCase()
  if (!kw) return overview.rows
  return overview.rows.filter(r =>
    (r.name || '').toLowerCase().includes(kw) ||
    (r.username || '').toLowerCase().includes(kw) ||
    (r.role || '').toLowerCase().includes(kw)
  )
})

const disabledFuture = (d) => {
  return d && d.getTime() > (new Date().getTime() + 24 * 3600 * 1000)
}

// --- Tab2 Config ---
const userFilter = ref('')
const loadingConfig = ref(false)
const savingConfig = ref(false)
const configYearPicker = ref(String(now.getFullYear()))
const configYear = computed(() => parseInt(configYearPicker.value || now.getFullYear()))
const configUsername = ref('')
const selectedUser = ref(null)
const configFormRef = ref(null)
const configForm = reactive({
  username: '',
  basic_salary: 0,
  base_performance: 0,
  annual_target_amount: 0,
  is_sales_override: 0,
})
const defaultMonthly = reactive({})  // 1..12 default
const monthlyForm = reactive({})     // 1..12 current (editable)

// --- 拉取用户列表（供配置 Tab 选择） ---
const allUsers = ref([])
const filteredUserList = computed(() => {
  const kw = userFilter.value.trim().toLowerCase()
  // 应用中心排前，其他在后
  let list = allUsers.value
  if (kw) {
    list = list.filter(u =>
      (u.name || '').toLowerCase().includes(kw) ||
      (u.username || '').toLowerCase().includes(kw) ||
      (u.department || '').toLowerCase().includes(kw) ||
      (u.role || '').toLowerCase().includes(kw)
    )
  }
  return [...list].sort((a,b) => {
    if ((a.department === '应用中心') !== (b.department === '应用中心')) {
      return a.department === '应用中心' ? -1 : 1
    }
    return 0
  })
})

async function loadUsers() {
  try {
    const res = await api.get('/users')
    if (res && res.code === 200 && res.data) {
      allUsers.value = Array.isArray(res.data) ? res.data : (res.data.users || [])
    }
  } catch (e) { /* noop */ }
}

// --- Mine ---
const mine = ref(null)

// --- 方法 ---
const pickYM = (pickerVal) => {
  const [y, m] = String(pickerVal || '').split('-').map((s, i) => parseInt(s) || (i === 0 ? now.getFullYear() : now.getMonth()+1))
  return { year: y, month: m }
}

async function loadOverview() {
  if (!canViewAppraisal.value) return
  loadingOverview.value = true
  try {
    const { year, month } = pickYM(yearMonthPicker.value)
    const res = await api.get('/appraisal/monthly', { year, month })
    if (res && res.code === 200 && res.data) {
      overview.year = res.data.year
      overview.month = res.data.month
      overview.avg_sales_rate_pct = res.data.avg_sales_rate_pct || 0
      overview.dept_rate_pct = res.data.dept_rate_pct ?? null
      overview.dept_monthly_target = res.data.dept_monthly_target || 0
      overview.dept_cumulative_actual = res.data.dept_cumulative_actual || 0
      overview.rows = res.data.rows || []
    } else {
      ElMessage.error((res && res.message) || t('appraisal.loadFail'))
    }
  } finally {
    loadingOverview.value = false
  }
}

// --- 年度完成率趋势 ---
const loadingYearly = ref(false)

// --- 明细抽屉 ---
const detailsDrawer = ref(false)
const loadingDetails = ref(false)
const detailsData = ref(null)
const detailsTitle = computed(() => {
  if (!detailsData.value) return '考核明细'
  const d = detailsData.value
  return `${d.name} - ${d.year}年${d.month}月考核明细`
})

async function openDetails(row) {
  if (!row || !row.username) return
  detailsDrawer.value = true
  loadingDetails.value = true
  detailsData.value = null
  try {
    const { year, month } = pickYM(yearMonthPicker.value)
    const res = await api.get(`/appraisal/details/${encodeURIComponent(row.username)}`, { year, month })
    if (res && res.code === 200 && res.data) {
      detailsData.value = res.data
    } else {
      ElMessage.error((res && res.message) || '加载明细失败')
    }
  } catch (e) {
    ElMessage.error('加载明细失败')
  } finally {
    loadingDetails.value = false
  }
}

const yearlyYearPicker = ref(String(now.getFullYear()))
const yearlyData = ref({ dept_rates: {}, sales_trend: [] })

// 表格行：第一行为部门完成率，后续为各销售
const yearlyTableRows = computed(() => {
  const rows = []
  rows.push({
    rowKey: '__dept__',
    name: '部门完成率',
    isDept: true,
    rates: yearlyData.value.dept_rates || {},
  })
  for (const s of yearlyData.value.sales_trend || []) {
    rows.push({
      rowKey: s.username,
      name: s.name,
      isDept: false,
      rates: s.rates || {},
    })
  }
  return rows
})

function yearlyCellClass({ row, columnIndex }) {
  if (columnIndex === 0) return ''
  const m = columnIndex  // 1..12
  if (m < 1 || m > 12) return ''
  const v = row.rates ? row.rates[String(m)] : null
  if (v === null || v === undefined) return 'cell-empty'
  if (row.isDept) return 'cell-dept'
  return ''
}

async function loadYearly() {
  if (!isAdmin.value) return
  loadingYearly.value = true
  try {
    const year = parseInt(yearlyYearPicker.value) || now.getFullYear()
    const res = await api.get('/appraisal/yearly', { year })
    if (res && res.code === 200 && res.data) {
      yearlyData.value = {
        dept_rates: res.data.dept_rates || {},
        sales_trend: res.data.sales_trend || [],
      }
    } else {
      ElMessage.error((res && res.message) || t('appraisal.loadFail'))
    }
  } finally {
    loadingYearly.value = false
  }
}

async function loadMine() {
  loadingMine.value = true
  try {
    const { year, month } = pickYM(yearMonthPicker.value)
    const res = await api.get('/appraisal/mine', { year, month })
    if (res && res.code === 200 && res.data) {
      mine.value = res.data.myself
      if (!isAdmin.value) {
        // 非 admin 也用 avg_sales_rate 展示参考
        overview.avg_sales_rate_pct = res.data.avg_sales_rate_pct || 0
      }
    } else {
      ElMessage.error((res && res.message) || t('appraisal.loadFail'))
    }
  } finally {
    loadingMine.value = false
  }
}

async function handleExport() {
  exporting.value = true
  try {
    const { year, month } = pickYM(yearMonthPicker.value)
    const token = localStorage.getItem('crm_token') || ''
    const resp = await fetch(`/api/appraisal/export?year=${year}&month=${month}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const blob = await resp.blob()
    const cd = resp.headers.get('Content-Disposition') || ''
    let fname = `应用中心考核_${year}_${month}.xlsx`
    for (const part of cd.split(';')) {
      const p = part.trim()
      if (p.startsWith("filename*=") && p.includes("UTF-8''")) {
        fname = decodeURIComponent(p.split("UTF-8''")[1])
        break
      } else if (p.startsWith('filename=')) {
        fname = p.split('=',1)[1].replace(/"/g,'')
      }
    }
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = fname
    document.body.appendChild(a); a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 2000)
    ElMessage.success(t('appraisal.exportOk'))
  } catch (e) {
    ElMessage.error(t('appraisal.exportFail') + (e.message ? '：' + e.message : ''))
  } finally {
    exporting.value = false
  }
}

function openConfig(row) {
  selectUser({ username: row.username, name: row.name, department: row.department, role: row.role })
  activeTab.value = 'config'
}

function selectUser(u) {
  selectedUser.value = u
  configUsername.value = u.username
  loadConfig()
}

async function loadConfig() {
  if (!configUsername.value) return
  loadingConfig.value = true
  try {
    const res = await api.get(`/appraisal/config/${configUsername.value}`, { year: configYear.value })
    if (res && res.code === 200 && res.data) {
      const d = res.data
      configForm.username = d.username
      configForm.basic_salary = Number(d.basic_salary || 0)
      configForm.base_performance = Number(d.base_performance || 0)
      configForm.annual_target_amount = Number(d.annual_target_amount || 0)
      configForm.is_sales_override = Number(d.is_sales_override || 0)
      for (let m = 1; m <= 12; m++) {
        defaultMonthly[m] = Number(d.default_monthly?.[m] ?? 0)
        const ov = d.monthly_overrides
        // 兼容 str/int key
        const v = ov?.[m] ?? ov?.[String(m)]
        monthlyForm[m] = v !== undefined ? Number(v) : defaultMonthly[m]
      }
    } else {
      ElMessage.error((res && res.message) || t('appraisal.loadFail'))
    }
  } finally {
    loadingConfig.value = false
  }
}

function setMonthly(m, v) {
  monthlyForm[m] = Number(v || 0)
}

function resetMonthlyToDefault() {
  const annual = Number(configForm.annual_target_amount || 0)
  const def = annual > 0 ? annual / 12 : 0
  for (let m = 1; m <= 12; m++) {
    defaultMonthly[m] = def
    monthlyForm[m] = def
  }
}

// annual 改了，实时重算默认值（但覆盖值不动）
watch(
  () => configForm.annual_target_amount,
  (nv) => {
    const def = Number(nv || 0) > 0 ? Number(nv)/12 : 0
    for (let m = 1; m <= 12; m++) {
      defaultMonthly[m] = def
      // 如果当前等于旧 default，就跟随；否则保留（相当于覆盖）
      const oldDef = defaultMonthly[m]  // 就是新的 def
      // 这里简化：只有当 monthlyForm[m] 不是覆盖值时跟随。
      // 由于 oldDef===def，我们直接判断 monthlyForm[m] === 旧 defaultMonthly[m] 的前值有点麻烦；
      // 简单方案：若用户手动输入后存成覆盖就是覆盖，annual 改动时 defaultMonthly 同步更新，UI 标 overrideTag 显示差异
    }
  }
)

async function saveConfig() {
  savingConfig.value = true
  try {
    // 只传与 default 不同的 monthly_overrides
    const overrides = {}
    for (let m = 1; m <= 12; m++) {
      const cur = Number(monthlyForm[m] || 0)
      const def = Number(defaultMonthly[m] || 0)
      if (Math.abs(cur - def) > 0.009) {
        overrides[m] = cur
      }
    }
    const body = {
      username: configUsername.value,
      year: configYear.value,
      basic_salary: Number(configForm.basic_salary || 0),
      base_performance: Number(configForm.base_performance || 0),
      annual_target_amount: Number(configForm.annual_target_amount || 0),
      is_sales_override: Number(configForm.is_sales_override || 0),
      monthly_overrides: overrides,
    }
    const res = await api.post('/appraisal/config', body)
    if (res && res.code === 200) {
      ElMessage.success(t('appraisal.saveOk'))
      await loadConfig()
      if (activeTab.value === 'overview') {
        await loadOverview()
      }
    } else {
      ElMessage.error((res && res.message) || t('appraisal.saveFail'))
    }
  } finally {
    savingConfig.value = false
  }
}

// --- 工具函数 ---
function formatMoney(v) {
  const n = Number(v || 0)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function formatPct(v) {
  return (Number(v || 0)).toFixed(2) + '%'
}
function clampRate(v) {
  const n = Number(v || 0)
  if (n < 0) return 0
  if (n > 150) return 150
  return Math.round(n * 100) / 100
}
function rateColor(pct) {
  const n = Number(pct || 0)
  if (n < 60) return '#f56c6c'
  if (n < 100) return '#e6a23c'
  if (n >= 150) return '#409eff'
  return '#67c23a'
}
function rateStatus(pct) {
  const n = Number(pct || 0)
  if (n < 60) return 'exception'
  if (n < 100) return 'warning'
  return 'success'
}

// 切换 Tab 时刷新
watch(activeTab, (nv) => {
  if (nv === 'overview') loadOverview()
  if (nv === 'yearly') loadYearly()
  if (nv === 'mine') loadMine()
  if (nv === 'config' && allUsers.value.length === 0) loadUsers()
})

onMounted(async () => {
  if (canViewAppraisal.value) {
    // 人力只加载总览；主任/院长额外加载用户列表（配置Tab用）
    await Promise.all([loadOverview(), ...(isAdmin.value ? [loadUsers()] : [])])
  }
  await loadMine()
})
</script>

<style scoped>
.appraisal-page { padding: 4px; }
.page-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 16px;
}
.page-title { margin: 0; font-size: 20px; font-weight: 700; }
.header-actions { display: flex; align-items: center; }
.stat-row { margin-bottom: 8px; }
.stat-card { padding: 8px 6px; }
.stat-label { color: #909399; font-size: 13px; }
.stat-value { font-size: 22px; font-weight: 700; color: #303133; margin-top: 6px; }
.stat-value.highlight { color: #409eff; }
.card-primary :deep(.el-card__body) { border-top: 3px solid #409eff; }
.card-success :deep(.el-card__body) { border-top: 3px solid #67c23a; }
.card-warning :deep(.el-card__body) { border-top: 3px solid #e6a23c; }
.card-info :deep(.el-card__body) { border-top: 3px solid #909399; }

/* 年度趋势表格：部门行高亮、空值单元格 */
:deep(.cell-dept) {
  background: #fdf6ec !important;
  font-weight: 700;
}
:deep(.cell-empty) {
  color: #c0c4cc;
  background: #fafafa;
}

.table-card {
  background: #fff; border-radius: 8px; padding: 12px 14px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.table-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 10px; flex-wrap: wrap; gap: 8px;
}

.user-list {
  max-height: 65vh; overflow: auto; padding-right: 4px;
}
.user-item {
  padding: 10px 12px; border: 1px solid #ebeef5; border-radius: 6px;
  margin-bottom: 8px; cursor: pointer; transition: all 0.15s;
}
.user-item:hover { background: #f5f7fa; border-color: #b3d8ff; }
.user-item.active {
  background: #ecf5ff; border-color: #409eff;
  box-shadow: 0 0 0 1px #409eff inset;
}
.user-item-name { font-weight: 600; color: #303133; font-size: 14px; }
.user-item-sub { color: #909399; font-size: 12px; margin-top: 3px; }

.monthly-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}
.monthly-cell {
  border: 1px solid #ebeef5; border-radius: 6px; padding: 8px 10px 10px;
  background: #fafbfc;
}
.monthly-cell-header {
  font-weight: 700; color: #606266; margin-bottom: 6px; font-size: 13px;
}
.monthly-override-tag {
  color: #e6a23c; font-size: 11px; margin-top: 4px;
}
.monthly-default-tag {
  color: #909399; font-size: 11px; margin-top: 4px;
}
</style>
