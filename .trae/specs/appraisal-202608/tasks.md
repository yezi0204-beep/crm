# 应用中心人员月度考核功能 - 实施计划 (tasks.md)

## Task 1: 数据库扩展（users 新字段 + 两张新表 + ensure_tables 幂等迁移）

**覆盖 AC**: AC1, AC2

- 优先级: high
- 状态: pending

**实现**: 在 `backend/extensions.py` 的 `ensure_tables` / `_init_other_tables` 区块追加：

1. users 表 ALTER TABLE 幂等新增 4 列：
   - `basic_salary REAL DEFAULT 0`（基本工资，元）
   - `base_performance REAL DEFAULT 0`（基础绩效工资，元）
   - `annual_target_amount REAL DEFAULT 0`（年度新签合同额指标，元/年）
   - `is_sales_override INTEGER DEFAULT 0`（是否强制按销售考核：1/0，身兼多职用）

2. 新建 `monthly_targets` 表（月度指标覆盖值）：
   | 列 | 类型 | 说明 |
   |---|---|---|
   | id | INTEGER PK | |
   | username | TEXT NOT NULL | 对应用户 |
   | year | INTEGER NOT NULL | 年度 |
   | month | INTEGER NOT NULL | 月份 1-12 |
   | target_amount | REAL NOT NULL DEFAULT 0 | 该月覆盖指标值，元。为 0 且 annual/12 != 0 时，代表未覆盖，读取默认值 |
   | updated_by | TEXT | 最后修改人 |
   | updated_at | TEXT | 最后修改时间 |
   - UNIQUE(username, year, month) 唯一键

3. 新建 `monthly_assessment_logs` 表（指标变更审计，可选但用于 AC5 操作日志可与 `operation_logs` 统一，如复用后者可省略本表）。但指标修改必须写 `operation_logs`（已有），所以这张表**非必需**，task 里改为只调用 `record_operation_log`。
- 因此 Task 1 的第 3 步改为：确认 extensions.py 的 `record_operation_log(username, operation, module, detail)` 可直接复用（module='月度考核'）。

**Test Requirements**:
- TR 1.1 (rule): python -c 检查 ensure_tables() 后 users 表包含以上 4 列，monthly_targets 表存在，重复运行 ensure_tables 不报错（幂等）
- TR 1.2 (rule): 对 monthly_targets 插入两条同 username+year+month 记录应失败（唯一约束）

**Completion Evidence**: DB migration 脚本执行日志

---

## Task 2: 后端考核接口 appraisal.py（3个读接口 + 1个写接口 + 1个导出）

**覆盖 AC**: AC3, AC4, AC5, AC6, AC7, AC8

- 优先级: high
- 依赖: Task 1 完成
- 状态: pending

**实现**: 新建 `backend/routes/appraisal.py`，注册在 `routes/__init__.py` 的 `register_blueprints`。
所有接口使用 `@token_required`，并在函数入口统一做权限 check（`_check_appraisal_access(payload, require_admin=False)`）。

**接口清单**:

| 方法 | 路径 | 角色 | 说明 |
|---|---|---|---|
| GET | `/api/appraisal/monthly` | 主任/院长 | 月度考核总览。query: year, month。返回列表，每人一行，字段见 AC3 清单 |
| GET | `/api/appraisal/mine` | 任意应用中心用户 | 我的本月考核 + 合同明细（AC7） |
| GET | `/api/appraisal/export` | 主任/院长 | 导出月度考核表 .xlsx（AC6，用 openpyxl） |
| POST | `/api/appraisal/config` | 主任/院长 | 保存单人配置（AC5：基本工资/基础绩效/年度指标/is_sales_override/12 月覆盖值），写 operation_logs |
| GET | `/api/appraisal/config/:username` | 主任/院长 | 读取单人配置（含 12 月覆盖值）用于配置表单回填 |

**核心算法（写在 appraisal.py 内部函数 `_compute_monthly_row(cursor, username, year, month, default_annual=0, basic=0, perf=0, override=None)`）**:

1. 查询该用户 `sign_date` 在 `YYYY-MM` 内的合同：
   ```sql
   SELECT COALESCE(SUM(total_amt), 0) as actual
   FROM contracts
   WHERE owner_id = ? AND strftime('%Y', sign_date) = ? AND strftime('%m', sign_date) = ?
   ```
2. 月度目标 = month_targets.override 若存在且>0；否则 `annual_target_amount / 12`，两位小数
3. 完成率 = `actual / target`。target <= 0 → 0。封顶 `min(actual/target, 1.5)`，保留 4 位小数
4. 身份判定：`role == '销售' OR is_sales_override == 1` → 销售
5. 汇总所有销售完成率 → `avg_sales_rate`（剔除 target<=0 的销售）
6. 绩效工资：销售用自己完成率，非销售用 avg_sales_rate。`perf_pay = base_performance * min(rate, 1.5)`，两位小数
7. 实发工资 = `round(basic_salary + perf_pay, 2)`
8. **金额统一用 round(..., 2)，百分比两位小数（87.35% 即 rate*100 后 round 2）**

**Test Requirements**:
- TR 2.1 (rule): 构造 3 用户测试集（A 销售 annual=120万 target=10万实际=8万→rate=80%；B 销售 actual=20万→rate=150%封顶；C 主任非销售 base_perf=2000）→ avg_sales_rate=(80%+150%)/2=115%；C 的绩效=2000*115%=2300。接口返回数值精确匹配
- TR 2.2 (rule): role='主任' + is_sales_override=1 时该人按销售公式，否则非销售（AC4）
- TR 2.3 (rule): target=0（未设指标）的销售不参与 avg 计算；该人自己的绩效=0（避免除以 0）
- TR 2.4 (rule): 普通用户调用 /monthly /export /config 接口都返回 403（AC8）
- TR 2.5 (rule): POST /config 后再次 GET /config/:username 能读回一模一样的值（含 12 月覆盖值）；operation_logs 新增一条记录
- TR 2.6 (rule): export 接口返回 Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet，Content-Disposition: attachment; filename=含年月

**Completion Evidence**: 单元测试脚本 assert 输出

---

## Task 3: 前端考核页 Appraisal.vue（总览+配置面板+我的考核+导出）

**覆盖 AC**: AC9, AC10, AC11

- 优先级: high
- 依赖: Task 2 接口就绪
- 状态: pending

**实现**: 新建 `frontend/src/views/Appraisal.vue`，包含三个 Tab（El-Tabs）：
- **Tab1 月度考核总览**（主任/院长可见，对普通用户隐藏）：
  - 行内筛选：年份下拉、月份下拉（默认当前）
  - El-Table 列：姓名、角色、身份标签、年度指标(元)、月度指标(元)、当月实际(元)、完成率（带 El-Progress 进度条 + 色阶 class）、基本工资、基础绩效、绩效工资、当月实发工资
  - 汇总行（summary-method）：合计 月度指标、当月实际、平均完成率、基本工资、基础绩效、绩效工资、实发工资
  - 右上角操作：[导出考核表] 按钮（点击直接 GET /api/appraisal/export?year=&month=，用 window.open 或 a.href 下载）、[指标配置] 按钮（打开右侧 Drawer）
  - 身份标签：销售=绿 tag，非销售=蓝 tag，强制销售覆盖=紫 tag
  - 色阶：完成率 >=100% 进度条 success 绿；60%~99% warning 黄；<60% danger 红（对应 AC10 rubric 色阶）

- **Tab2 指标配置**（主任/院长可见）：
  - 用户选择下拉（列出应用中心在职用户）
  - 表单：基本工资（number, step=0.01）、基础绩效工资（number, step=0.01）、年度新签合同额指标（number, step=0.01，单位元）、是否强制按销售考核 switch（is_sales_override）
  - 12 个月分解：用 El-Card 12 栅格展示 12 个输入框，输入框上方默认值"默认: annual/12"并显示灰色，输入值即覆盖值。下方提示"12 月之和 = X，年度指标 = Y，差值 = ±Z（应 ≤10 元）"，点击保存时校验差值，不通过则 ElMessage.error 不提交（对应 AC11 校验）
  - 保存按钮：POST `/api/appraisal/config`

- **Tab3 我的考核**（所有登录用户可见）：
  - 行内筛选年/月（默认当前），仅当前用户的数据
  - 卡片展示：月度指标、当月实际新签、完成率（大幅进度条）、基本工资、基础绩效、绩效工资、实发工资
  - 底部 El-Table：本月已签合同明细（合同号、合同名称、金额、签约日期）。0 条时 El-Empty 空状态

**Test Requirements**:
- TR 3.1 (rule): 路由守卫 `to.path === '/appraisal'` 且非应用中心部门→ 404 或跳转 dashboard（前端路由校验）
- TR 3.2 (rule): 主任登录时总览 Tab+配置 Tab+我的考核 Tab 都展示；普通用户只显示我的考核 Tab（或总览/配置 Tab v-if 隐藏）
- TR 3.3 (rubric, AC10 对齐): 表格所有列展示 + 进度条色阶 + 汇总行正确。2=完美，1=可接受瑕疵，0=缺字段/色阶
- TR 3.4 (rubric, AC11 对齐): 配置表单 4 字段 + 12 月覆盖值可编辑，12 月之和偏离>10 元时拒绝提交并提示。2=完美，1=有校验但提示粗糙，0=无校验
- TR 3.5 (rule): 导出按钮点击后文件可下载，文件名含年月，打开 xlsx 表头中文正确（可与后端 TR 2.6 联动验证）

**Completion Evidence**: 页面手工操作截图证据（或前端无编译错误诊断通过）

---

## Task 4: 路由 + 菜单 + 国际化

**覆盖 AC**: AC9（部分）

- 优先级: medium
- 依赖: Task 3 文件就绪
- 状态: pending

**实现**:
1. `frontend/src/router/index.js` 的 Layout children 中新增路由：
   ```
   { path: 'appraisal', name: 'Appraisal', component: () => import('../views/Appraisal.vue') }
   ```
2. `frontend/src/views/Layout.vue` 侧边栏菜单中新增，放在销售管理组（或新的"人事管理"组，推荐在 users 旁边），icon 🏅，文字取 i18n `menuItem.appraisal`
3. `frontend/src/locales/zh-CN.js` 和 `en-US.js` 新增键：
   - `menuItem.appraisal = '月度考核' / 'Monthly Appraisal'`
   - `menu.humanResources = '人力资源'`（新增分组，月度考核、用户管理归入此组）

**Test Requirements**:
- TR 4.1 (rule): 刷新页面后 Layout 侧边栏可见新菜单项，点击跳转路由不报错
- TR 4.2 (rule): 前端 GetDiagnostics 无错误（Appraisal.vue + router.js + locales 三处）

---

## Task 5: 端到端验证（合同数据 → 考核联动）

**覆盖 AC**: AC12（rule）

- 优先级: high
- 依赖: Task 2 + Task 3 完成
- 状态: pending

**实现**: 编写 e2e 脚本或手工执行以下步骤并记录证据：

步骤：
1. 重置 A 销售（annual=1200000 元，月度默认10万，base_perf=5000，basic=10000）
2. 重置 B 销售（annual=1200000，base_perf=5000，basic=10000）
3. 重置 C 主任（非销售，base_perf=2000，basic=15000，is_sales_override=0）
4. 往 contracts 表 INSERT 一条 owner=A 当月 80000 元 当月签约合同
5. 往 contracts 表 INSERT 一条 owner=B 当月 200000 元 当月签约合同
6. GET /api/appraisal/monthly?year=2026&month=8 返回：
   - A: actual=8万, target=10万, rate=80%, perf_pay = 5000 * 80% = 4000, total = 14000
   - B: actual=20万, target=10万, rate=150%(封顶), perf_pay = 5000 * 150% = 7500, total = 17500
   - avg_sales_rate = (80+150)/2 = 115%
   - C: perf_pay = 2000 * 115% = 2300, total = 17300
7. 数值精确匹配即通过

**Test Requirements**:
- TR 5.1 (rule): AC12 断言全部通过（A/B/C 6个关键数值分别断言等于期望值，金额两位小数）

**Completion Evidence**: e2e 脚本 run 结果日志（stdout 打印每个字段期望值与实际值，全部 ok 则 pass）

---

## Task 6: Review 准备（文档 + 清理临时文件）

- 优先级: low
- 状态: pending
- 实现: 清除 scripts 临时调试文件，检查 .gitignore 未被修改，记录最终操作日志插入点证据。
- TR 6.1 (rule): 最终无遗留 debug 脚本，所有接口 URL 统一 /api/appraisal/* 前缀
