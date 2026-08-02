# AI 智能体功能集成（第一阶段）

## Context（背景）

用户要求为 CRM 系统添加 5 项 AI 能力：数据与 API 对接、场景流程嵌入、对话式交互录入、智能线索管理、自动化复盘总结。经确认采用**分阶段实施**，本次完成 3 项核心：

1. **数据与 API 对接**：智能体通过 API 直接读写客户档案、跟进记录、销售漏斗
2. **对话式交互录入**：销售通过语音/文字向智能体汇报，系统自动更新 CRM 状态
3. **自动化复盘与总结**：拜访结束后智能体生成结构化摘要，回流沉淀为企业知识资产

**后续阶段**（本次不做）：场景流程嵌入、外网线索抓取+AI 评估。

**现状**：系统已有 [qa_engine.py](file:///c:/Program%20Files/python/crm/backend/qa_engine.py) 提供 `call_llm`/`extract_query_function`/`generate_answer_stream` 等可复用函数，但仅支持 11 个只读查询；[Qa.vue](file:///c:/Program%20Files/python/crm/frontend/src/views/Qa.vue) 是对话界面，无语音、非流式。LLM 配置在 [config.py](file:///c:/Program%20Files/python/crm/backend/config.py)（DeepSeek API，环境变量 LLM_API_KEY）。

**技术选型**（用户确认）：
- 语音输入：浏览器原生 Web Speech API（无额外依赖）
- 复盘沉淀：跟进记录 + 知识库双写
- LLM 无 API Key 时降级为规则引擎（沿用现有 fallback 模式）

---

## 实施方案

### 一、后端：新增 `knowledge_base` 表

**文件**：`backend/extensions.py`（修改 `_init_tables`，新增 `_init_knowledge_base_table`）

```python
def _init_knowledge_base_table(cursor):
    try:
        cursor.execute("""
            CREATE TABLE knowledge_base (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'visit_summary',
                cust_id INTEGER,
                visit_id INTEGER,
                owner_id TEXT,
                tags TEXT,
                summary TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cust_id) REFERENCES customers(id),
                FOREIGN KEY (visit_id) REFERENCES visits(id)
            )
        """)
    except:
        pass
```

类别（category）：`visit_summary`（拜访复盘）/ `followup_insight`（跟进洞察）/ `sales_tip`（销售技巧）

### 二、后端：扩展 `qa_engine.py` 增加写操作意图识别

**文件**：`backend/qa_engine.py`（修改）

新增两个核心函数，复用现有 `call_llm`：

#### 2.1 `extract_write_intent(question, username, context=None)`
识别用户汇报中的写操作意图，返回结构化 JSON。LLM 使用 function call 模式输出：

```json
{
  "intent": "create_follow_log | create_customer | update_business | query | none",
  "entities": {
    "customer_name": "江阴科技",
    "content": "客户对方案满意，要求下周提供报价",
    "next_plan": "下周三前提供报价方案",
    "amount": 50,
    "probability": 60,
    "stage": "方案确定"
  },
  "confidence": 0.85
}
```

意图映射表（prompt 内置）：
- "刚拜访了XX客户"/"今天跟进了XX" → create_follow_log
- "新增客户XX"/"录入客户XX" → create_customer
- "XX商机概率提升到60%"/"XX商机进入方案阶段" → update_business
- 其他 → query（走现有只读流程）或 none

#### 2.2 `generate_visit_summary(visit_data, customer_data, business_data)`
基于拜访记录+客户信息+关联商机，生成结构化复盘摘要：

```json
{
  "title": "江阴科技拜访复盘-20260802",
  "summary": "客户对卫星通信方案整体满意，重点关注成本与交付周期",
  "key_findings": ["客户预算 50 万", "决策周期约 2 周", "竞品为华为"],
  "customer_needs": ["低成本方案", "3 个月内交付", "支持本地化部署"],
  "next_actions": ["下周三前提供报价", "安排技术方案演示", "联系售前评估可行性"],
  "risk_warnings": ["客户预算低于常规报价 20%", "竞品已有先发优势"],
  "deal_signals": "中等偏强，客户主动询问合同条款"
}
```

无 LLM 时降级为模板拼接（基于 visit.result + customer.company）。

### 三、后端：新增 `routes/ai_agent.py` Blueprint

**文件**：`backend/routes/ai_agent.py`（新建）
**注册**：`backend/routes/__init__.py` 添加 `ai_agent_bp`

#### 3.1 `POST /api/ai/agent` — 对话式录入主接口

入参：`{ text: "用户汇报文本", context?: "可选上下文" }`

处理流程：
1. 调用 `extract_write_intent(text, username)` 识别意图
2. 按 intent 执行对应写操作（**直接调用数据库，复用现有 CRUD 的字段约定**，不走 HTTP 转发）：
   - `create_follow_log`：先按 customer_name 模糊匹配 customers 表找 cust_id，找不到则提示用户补全客户信息；写入 follow_logs（ref_type='customer'），调用 `update_customer_last_follow`
   - `create_customer`：写入 customers 表，owner_id=current_user
   - `update_business`：按 title 模糊匹配 business 表，更新 probability/stage
   - `query`：走现有 `extract_query_function` + 数据查询流程
3. 记录 operation_log（模块='AI智能体'）
4. 返回：`{ intent, executed: true/false, data: {...}, reply: "自然语言回复" }`

**权限**：所有写操作以当前用户身份执行（@token_required），遵循现有权限隔离（如普通用户只能写自己的数据）

#### 3.2 `POST /api/ai/visit-summary` — 拜访复盘接口

入参：`{ visit_id: 123, extra_text?: "补充口述内容" }`

处理流程：
1. 查询 visit + 关联 customer + 关联 business
2. 调用 `generate_visit_summary(visit, customer, business)` 生成摘要
3. **双写**：
   - 写入 `follow_logs`：ref_type='customer', ref_id=cust_id, subject='[AI复盘]'+title, content=summary, next_plan=next_actions
   - 写入 `knowledge_base`：title, content(完整摘要JSON), category='visit_summary', cust_id, visit_id, owner_id, summary
4. 返回：`{ summary: {...}, follow_log_id, knowledge_id }`

#### 3.3 `POST /api/ai/agent/stream` — 流式对话接口（SSE）

复用现有 `generate_answer_stream`，支持录入结果的自然语言回复流式输出。

### 四、后端：新增 `routes/knowledge.py` Blueprint

**文件**：`backend/routes/knowledge.py`（新建）
**注册**：`backend/routes/__init__.py` 添加 `knowledge_bp`

接口：
- `GET /api/knowledge` — 列表查询（支持 keyword、category、cust_id 筛选，分页）
- `GET /api/knowledge/<id>` — 详情
- `DELETE /api/knowledge/<id>` — 删除（主任/院长或本人）
- `GET /api/knowledge/search?q=xxx` — 全文检索（title/content/tags/summary）

权限：主任/院长看全部，普通用户看自己创建的（owner_id 筛选）

### 五、前端：升级 `Qa.vue` 为 AI 智能体中心

**文件**：`frontend/src/views/Qa.vue`（重构）

#### 5.1 三种模式切换（顶部 Tab）
- **💬 智能问答**：现有功能，查询数据
- **📝 智能录入**：语音/文字汇报，AI 解析后展示确认卡片，确认后写入
- **🎯 拜访复盘**：选择拜访记录，AI 生成摘要

#### 5.2 语音输入（Web Speech API）
```javascript
const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)()
recognition.lang = 'zh-CN'
recognition.continuous = true
recognition.interimResults = true
recognition.onresult = (event) => {
  // 实时显示识别文本到输入框
}
```
- 输入框旁增加 🎤 麦克风按钮，点击开始/停止录音
- 录音中按钮显示波形动画
- 不支持 Web Speech API 的浏览器隐藏语音按钮

#### 5.3 录入模式交互流程
1. 用户语音/文字输入："今天拜访了江阴科技，客户对方案满意，要求下周提供报价，商机概率提升到60%"
2. 调用 `POST /api/ai/agent`
3. 后端返回意图+实体+执行结果
4. 前端展示**确认卡片**（el-card）：
   - 识别到客户：江阴科技 ✓
   - 跟进内容：客户对方案满意...
   - 下步计划：下周提供报价
   - 商机概率：60%
   - [确认写入] [修改] [取消] 按钮
5. 用户确认后，AI 回复"已为您记录本次跟进，并更新商机概率为60%"

#### 5.4 复盘模式交互
1. 下拉选择已完成的拜访记录（调用 /api/visits?status=completed）
2. 可补充口述内容
3. 点击"生成复盘"，调用 `POST /api/ai/visit-summary`
4. 展示结构化摘要（标题/关键发现/客户需求/下一步/风险/成交信号）
5. [保存到知识库] [保存并查看画像] 按钮

#### 5.5 流式输出
对智能问答模式启用 SSE 流式（调用 `/api/ai/agent/stream`），逐字显示回复。录入模式和复盘模式用非流式（需要完整 JSON 解析）。

### 六、前端：新增 `Knowledge.vue` 知识库页面

**文件**：`frontend/src/views/Knowledge.vue`（新建）

布局：
- 顶部搜索框 + 类别筛选（拜访复盘/跟进洞察/销售技巧）+ 关键词
- 左侧：知识列表（卡片式，显示 title/summary/category/created_at）
- 右侧：选中条目的详情（完整 content、关联客户、关联拜访、标签）
- 操作：删除（权限内）

### 七、前端：`Visits.vue` 嵌入"AI 复盘"按钮

**文件**：`frontend/src/views/Visits.vue`（修改）

- 在已完成拜访的操作列增加"🤖 AI 复盘"按钮
- 点击后弹窗（el-dialog）展示复盘界面（复用 Qa.vue 复盘模式的逻辑，或直接跳转 `/qa?mode=review&visit_id=xxx`）

### 八、路由与菜单集成

**文件**：`frontend/src/router/index.js`（修改）
- 添加 `/knowledge` 路由

**文件**：`frontend/src/views/Layout.vue`（修改）
- "智能助手"菜单项文案改为"AI 智能体"，图标 🤖
- 新增"📚 知识库"菜单项（在"系统管理"组或新增"💡 AI 能力"组）

---

## 关键文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/extensions.py` | 修改 | 新增 knowledge_base 表初始化 |
| `backend/qa_engine.py` | 修改 | 新增 extract_write_intent、generate_visit_summary |
| `backend/routes/ai_agent.py` | 新建 | 3 个接口：agent/visit-summary/stream |
| `backend/routes/knowledge.py` | 新建 | 4 个接口：list/detail/delete/search |
| `backend/routes/__init__.py` | 修改 | 注册 ai_agent_bp、knowledge_bp |
| `frontend/src/views/Qa.vue` | 重构 | 三模式+语音+流式+确认卡片 |
| `frontend/src/views/Knowledge.vue` | 新建 | 知识库页面 |
| `frontend/src/views/Visits.vue` | 修改 | 嵌入"AI 复盘"按钮 |
| `frontend/src/router/index.js` | 修改 | 添加 /knowledge 路由 |
| `frontend/src/views/Layout.vue` | 修改 | 菜单项升级+知识库菜单 |

## 复用的现有资产

- **call_llm**：[qa_engine.py:6](file:///c:/Program%20Files/python/crm/backend/qa_engine.py#L6) LLM 调用封装，写意图识别和复盘生成直接复用
- **extract_query_function**：[qa_engine.py:54](file:///c:/Program%20Files/python/crm/backend/qa_engine.py#L54) 现有只读意图识别，agent 接口中 query 分支复用
- **update_customer_last_follow**：[extensions.py](file:///c:/Program%20Files/python/crm/backend/extensions.py) 创建跟进记录后自动更新客户最后跟进时间
- **follow_logs 表结构**：[misc.py:91-99](file:///c:/Program%20Files/python/crm/backend/routes/misc.py#L91-L99) 字段约定（ref_type/ref_id/content/next_plan 等）
- **customers 表字段**：[customers.py:65-92](file:///c:/Program%20Files/python/crm/backend/routes/customers.py#L65-L92) name/company/phone/level/source/owner_id 等
- **business 表字段**：[business.py:156-164](file:///c:/Program%20Files/python/crm/backend/routes/business.py#L156-L164) title/amount/stage/probability/predict_date
- **visits 表字段**：[visits.py:108-124](file:///c:/Program%20Files/python/crm/backend/routes/visits.py#L108-L124) cust_id/purpose/result/work_type
- **token_required 装饰器**：所有新接口使用，AI 写操作以当前用户身份执行
- **record_operation_log**：记录 AI 智能体的写操作日志
- **Qa.vue 对话框架**：[Qa.vue](file:///c:/Program%20Files/python/crm/frontend/src/views/Qa.vue) 现有消息列表/输入框/快速提问可复用

## 权限与安全

- AI 写操作**以当前用户身份**执行，遵循现有权限隔离（普通用户只能写自己负责的数据）
- 客户名模糊匹配失败时，**不自动创建客户**，而是返回"未找到客户XX，是否创建？"让用户确认
- 商机更新需校验：当前用户是商机负责人或主任/院长
- 知识库删除：主任/院长可删任意，普通用户只能删自己创建的
- LLM 无 API Key 时：写意图识别降级为关键词规则匹配，复盘降级为模板拼接

## 降级策略

| 功能 | LLM 可用 | LLM 不可用 |
|------|---------|-----------|
| 写意图识别 | LLM function call | 关键词规则匹配（"拜访/跟进"→create_follow_log） |
| 复盘摘要生成 | LLM 结构化输出 | 模板拼接（visit.result + customer.company） |
| 自然语言回复 | LLM 生成 | 固定模板（"已为您记录本次跟进"） |
| 智能问答 | 现有流程 | 现有规则引擎 fallback |

## 验证方案

1. **后端接口验证**（curl/Postman）：
   - `POST /api/ai/agent` 传入"今天拜访了江阴科技，客户满意，下周报价"，验证返回意图 create_follow_log + 实体
   - `POST /api/ai/visit-summary` 传入 visit_id，验证返回结构化摘要 + 双写 follow_logs/knowledge_base
   - `GET /api/knowledge` 验证列表查询

2. **前端页面验证**：
   - 访问 `/qa`，确认三模式 Tab 切换正常
   - 录入模式：语音输入（Chrome）+ 文字输入，验证确认卡片展示和写入
   - 复盘模式：选择拜访记录，生成摘要，确认保存
   - 知识库页面：列表、搜索、详情、删除

3. **端到端流程验证**：
   - 销售口述："今天拜访了XX，客户要报价，商机到方案阶段"
   - AI 识别→确认卡片→写入跟进记录+更新商机
   - 客户画像时间轴显示新的跟进记录
   - 拜访记录页点击"AI 复盘"→生成摘要→知识库可检索

4. **降级验证**：临时清空 LLM_API_KEY，验证规则引擎 fallback 正常工作

5. **兼容性验证**：现有智能问答、客户/商机/拜访 CRUD 功能不受影响

## 实施顺序

1. 后端：knowledge_base 表迁移 + ai_agent.py + knowledge.py + 注册 Blueprint
2. 后端：qa_engine.py 扩展写意图识别 + 复盘生成函数
3. 前端：Qa.vue 重构（三模式+语音+流式+确认卡片）
4. 前端：Knowledge.vue 新建 + 路由 + 菜单
5. 前端：Visits.vue 嵌入"AI 复盘"按钮
6. 重启后端，端到端验证
7. 更新 project_memory.md 记录新约束

## 后续阶段（本次不做）

- **场景流程嵌入**：在客户/商机列表页嵌入"AI 分析"按钮，提供个性化建议
- **智能线索管理**：外网抓取多渠道线索 + AI 意向评估 + 精准分配（需独立设计爬虫合规方案）
