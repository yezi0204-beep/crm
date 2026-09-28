# 万元口径统一改元实施方案

## Context（背景与目的）

CRM 系统当前金额口径混乱：
- **大部分字段**：DB 按"元"存储，前端 `/10000` 展示成"万元"，录入时 `*10000` 转元存 DB
- **少数字段 DB 直接按万元存储**：`competitor_profiles.win_amount`、`customer_profiles.total_budget/avg_budget`、`contract_monthly_forecast.expected_acceptance/expected_payment`
- **导入/导出模板**：合同导入、回款导入模板表头带"(万)"，解析时 `*10000`；业绩报表 Excel 导出表头带"(万元)"，数据 `/10000`
- **后端文本/JSON**：reports/misc/quarterly_assessment/system/enterprises/work_summary/dashboard 多处 `/10000` 或"万元"字样

用户要求"系统所有以万为单位的全部换成元"，并已确认：
1. DB 按万元存储的字段迁移成元存储（*10000，先备份）
2. 导入/导出模板同步改成元口径

目标：全系统金额口径统一为"元"，DB 存元、前端展示元（toFixed(2)）、录入元、导入导出元、文本"元"。

## 关键边界（已确认）

- `enterprises.py` L751/754 的 `/1000000` 是评分量级换算（每百万 5 分），**不是金额换算，保持不变**
- `competitor_model.py` L29-33、`customer_model.py` L49-53 的 `/10000` 是 DB 字段解析逻辑，DB 改元存储后**需去掉**
- `ai_analysis.py` L24/28、`scoring_model.py` L117/123、`intelligence.py` L721、`cockpit.py` L205/291/401、`smart_import.py` L274 的 `/10000` 或 `*10000` 是**非结构化文本归一化**（如把"5万"解析成 50000 元），**保留**
- 验收导入（contracts.py L1275-1413）：docstring/表头写"(万)"但 `_parse_amt` L1310 已按元处理，仅需改文档/表头

## 阶段一：数据迁移脚本

新建 `backend/migrations/wan_to_yuan.py`（MySQL 版，非 SQLite）：

迁移字段（全部 `UPDATE 表 SET 字段 = ROUND(字段 * 10000, 6) WHERE 字段 IS NOT NULL`）：
- `competitor_profiles.win_amount`
- `customer_profiles.total_budget`
- `customer_profiles.avg_budget`
- `contract_monthly_forecast.expected_acceptance`
- `contract_monthly_forecast.expected_payment`

脚本流程：
1. 先用 `mysqldump` 备份这 3 张表到 `crm_backup_wan_yuan_YYYYMMDD.sql`（Shell 执行，非 SQL 内）
2. 连接 MySQL，事务内执行 5 条 UPDATE
3. 打印各表受影响行数 + 抽样 SELECT 10 行人肉确认量级
4. COMMIT
5. 幂等保护：检查 `schema_migrations` 表是否有 `wan_to_yuan_v1` 记录，有则跳过；无则执行后插入

## 阶段二：后端改动

### 2.1 DB 解析/写入逻辑（去掉万元换算）

- `backend/models/competitor_model.py`：
  - L29-33：去掉 `/10000` 解析，直接 `return val`（DB 改元存储后返回元）
  - L219-233：注释"中标总金额(万)" → "(元)"
- `backend/models/customer_model.py`：
  - L49-53：去掉 `/10000` 解析
  - L208-257：返回逻辑去掉换算，标签"历史采购总金额(万)" → "(元)"
- `backend/routes/contracts.py`：
  - L843-844 docstring 示例改元
  - L872-874 注释"填报单位为万元" → "填报单位为元"
  - L937 表头"合同总额(万)" → "(元)"
  - L978-979 去掉 `value=float(value)*10000`
  - L1275-1413 验收导入：docstring L1279 + 表头"(万)" → "(元)"，`_parse_amt` 代码不变
- `backend/routes/finance.py`：
  - L184 表头"(万)" → "(元)"
  - L312 去掉 `value=float(value)*10000`
- `backend/routes/dashboard.py`：
  - L332-334、L453-455：去掉 `*10000`（forecast 改元存储后直接用 `row['acc']`），注释同步

### 2.2 导出/展示逻辑（去掉 /10000，文本"万元"→"元"）

- `backend/routes/reports.py`：
  - L633/659/684 表头"(万元)" → "(元)"
  - L651/654/678/730-733 数据去掉 `/10000`
  - JSON 接口 L264-265/332/411/413-415 去掉 `/10000`
  - 文本"万元" → "元"：L540/565/582/862/887/904
- `backend/routes/misc.py` L549/570/591/643/661/668：`/10000:.2f万元` → `:.2f元`
- `backend/routes/quarterly_assessment.py` L275-276/290-291/322：同上
- `backend/routes/system.py` L377/438：`amount=(total_amt-paid_amt)/10000` → `amount=(total_amt-paid_amt)`
- `backend/routes/enterprises.py`：
  - L751/754 **保持不变**（评分量级，非金额）
  - L783/785 `/10000:.1f万` → `:.2f元`
- `backend/routes/work_summary.py` L133：`amount_wan=round(.../10000,2)` → `amount=round(...,2)`（字段名同步改）

### 2.3 AI 抓取/解析层（保留，输入归一化）

以下**不改**，属于把非结构化文本归一化为元的逻辑：
- `backend/routes/ai_analysis.py` L24/L28
- `backend/models/scoring_model.py` L117/L123
- `backend/routes/intelligence.py` L721
- `backend/routes/cockpit.py` L205/291/401
- `backend/routes/smart_import.py` L274

## 阶段三：前端改动（14 个 .vue）

通用模式（用 Grep 驱动，逐文件核对）：

1. 金额展示：`/10000).toFixed(6)` → `).toFixed(2)`（DB 已是元）
2. 提交金额：`*10000` 提交 → 直接提交元值
3. `el-input-number` 的 `:precision="6"` → `:precision="2"`
4. 单位文本："万元"/"万" → "元"
5. 字段名：`amount_wan` → `amount`（对应后端字段名变更）

关键文件：
- [Contracts.vue](file:///c:/Program%20Files/python/crm/frontend/src/views/Contracts.vue)：L300-340 表单 precision、L527/L1187-1189/L1528/L1530 展示、L1372-1376/L1410-1414 提交回填、L1048-1063 均分提示
- [Business.vue](file:///c:/Program%20Files/python/crm/frontend/src/views/Business.vue)：L112-113/L635-636/L691/L762/L949
- [Payments.vue](file:///c:/Program%20Files/python/crm/frontend/src/views/Payments.vue)：L81-82/L145/L213-214/L278-279/L318/L376/L402
- [ProjectCost.vue](file:///c:/Program%20Files/python/crm/frontend/src/views/ProjectCost.vue)：L42/L68/L81/L130/L143/L181/L246-261/L288-311/L354-369
- [Dashboard.vue](file:///c:/Program%20Files/python/crm/frontend/src/views/Dashboard.vue)：L368-374/L396-397/L562/L566/L569（axisLabel formatter 改 `v.toFixed(0)+'元'`）
- [Customers.vue](file:///c:/Program%20Files/python/crm/frontend/src/views/Customers.vue)：L480/L874-876
- [Enterprises.vue](file:///c:/Program%20Files/python/crm/frontend/src/views/Enterprises.vue)：L191-195/L256-257/L279-283/L383-387（L111 placeholder "5000万元" 是注册资本示例文本，保持）
- [CompetitorAnalysis.vue](file:///c:/Program%20Files/python/crm/frontend/src/views/CompetitorAnalysis.vue)：L35-36/L72/L174（原 toFixed(6) 无 /10000 → toFixed(2)）
- [CustomerProfiles.vue](file:///c:/Program%20Files/python/crm/frontend/src/views/CustomerProfiles.vue)：L40-41/L90-91/L117
- [Reports.vue](file:///c:/Program%20Files/python/crm/frontend/src/views/Reports.vue)：L348-350/L476-477/L722/L737/L774
- [SmartImport.vue](file:///c:/Program%20Files/python/crm/frontend/src/views/SmartImport.vue)：L36/L49 单位切换文案
- Alerts.vue / IntelligenceLeads.vue / Qa.vue：无金额换算，无需改动

## 阶段四：更新 memory

编辑 `c:\Users\SJSYB-Yewei\.trae-cn\memory\projects\-c-Program-Files-python-crm--p2-5f269bcf4400fd863f3c\project_memory.md`：
- "合同管理中的金额单位（收入、待验收合同额）需统一换算为万元展示" → 删除或改为"统一以元展示，toFixed(2)"
- "万元口径需保留6位小数..." → 删除或改为"元口径 toFixed(2)，precision=2"
- "数据库存储单位保持不变（元）" → 保留，补充"所有金额字段统一按元存储"
- "合同管理的收入应为含税收入，计算公式为：含税收入 = 累计验收额 + 税额" → 保留
- "合同管理中的金额单位（收入、待验收合同额）需统一换算为万元展示" → 改元

## 阶段五：验证步骤

1. **语法检查**：`python -m py_compile backend/routes/*.py backend/models/*.py backend/migrations/wan_to_yuan.py`
2. **前端构建**：`npm run build`（在 frontend/ 目录下）
3. **执行迁移脚本**：先 mysqldump 备份 3 张表，再执行 5 条 UPDATE，确认受影响行数 + 抽样 SELECT 10 行量级正确
4. **重启服务**：单实例重启后端
5. **接口冒烟**：
   - `GET /api/competitors` → win_amount 元量级（如原 5.0 万 → 50000）
   - `GET /api/customers/profiles` → total_budget 元量级
   - `GET /api/dashboard` → forecast 数据元量级（不再 *10000）
   - `GET /api/contracts/{id}/forecast` → 填报返回元
   - `GET /api/reports/export` → Excel 表头"(元)"、数据元量级
   - `GET /api/enterprises/score` → 评分值不变，推荐理由文本"XX元"
6. **端到端**：导入一份元口径验收 Excel → 看板数据正确；填报月度预计（元）→ dashboard 展示正确

## 风险与回滚

- **风险1：迁移脚本重复执行导致 *10000 两次**。缓解：`schema_migrations` 记录 + 执行前查迁移表；已执行则跳过
- **风险2：备份覆盖但迁移失败**。缓解：事务内执行，失败 ROLLBACK；备份 SQL 文件保留 7 天
- **风险3：前端缓存旧构建**。缓解：构建产物文件名 hash 化，浏览器自动失效
- **风险4：work_summary 字段名变更导致前后端不匹配**。缓解：前后端同批改、同批验证
- **回滚策略**：
  - 代码层：`git revert` 本次改动
  - 数据层：`mysql -u crm -p crm < crm_backup_wan_yuan_YYYYMMDD.sql` 恢复 3 张表
  - 迁移记录：回滚后 `DELETE FROM schema_migrations WHERE name='wan_to_yuan_v1'` 以便重新执行
