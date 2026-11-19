# CRM 系统 · 天地信息网络研究院

前后端分离的销售经营管理系统，面向应用中心销售与技术团队。集成 AI 情报采集、商机 7-Agent 评分、智能助手、周/月工作总结 LLM 生成等大模型能力。

## 技术栈

- **前端**：Vue 3 + Element Plus + ECharts + Pinia + Vue Router + Vite
- **后端**：Flask（单实例）+ MySQL 8.0 + PyMySQL
- **AI**：vLLM 推理服务（本地部署 Qwen3.5-122B）+ 双引擎情报筛选（关键词 + 语义）+ LLM Gateway
- **构建**：Vite 前端构建，Flask dev server，Nginx 反向代理（生产）

## 项目结构

```
crm/
├── backend/                        # Flask 后端（端口 5000）
│   ├── app.py                      # 应用入口 / 路由注册 / 调度器启动
│   ├── db.py                       # 数据库封装（SQL→MySQL 方言适配、Decimal/float 转换）
│   ├── extensions.py               # token_required / user_can / 操作日志等扩展
│   ├── scheduler.py                # 定时任务（情报采集 / 7-Agent 商机分析 / 自动导入）
│   ├── ai_agents.py                # 7-Agent LLM 商机分析
│   ├── qa_engine.py                # 智能助手（多轮上下文 + 函数调用 + SSE 流式）
│   ├── dual_engine.py              # 关键词 + 语义双引擎情报筛选
│   ├── llm_gateway.py              # /api/ai/* 统一 LLM 网关
│   ├── routes/                     # API 路由（40+ 蓝图）
│   │   ├── auth.py                 # 登录 / 权限
│   │   ├── customers.py            # 客户管理（多负责人 / 合并 / 公海）
│   │   ├── business.py             # 商机管理
│   │   ├── contracts.py            # 合同管理
│   │   ├── finance.py              # 回款 / 开票
│   │   ├── receivables.py          # 两金明细表 + 快照
│   │   ├── workhours.py            # 工时填报 / 审批
│   │   ├── work_summary.py         # AI 工作总结（周/月 + 历史 + 指定周期分析）
│   │   ├── sandbox.py              # 营销作战沙盘（ECharts 中国地图）
│   │   ├── cockpit.py              # AI 驾驶舱
│   │   ├── notifications.py        # 消息中心（销售提醒 / 审批 / 业务到期 / 操作日志）
│   │   ├── market_tasks.py         # 市场任务单
│   │   ├── business_cost.py        # 商机成本评估
│   │   ├── reports.py              # 业绩报表
│   │   ├── ...                     # 其余路由
│   │   └── __init__.py             # 蓝图注册顺序
│   ├── collectors/                 # 情报采集（ccgp.gov.cn / AI 搜索）
│   ├── scripts/                    # 一次性迁移 / 诊断脚本
│   ├── vendor/                     # 内嵌第三方依赖（ocr / docx / lxml 等）
│   └── requirements.txt
├── frontend/                       # Vue3 前端（dev 端口 8080）
│   ├── src/
│   │   ├── api/index.js            # axios 封装 + longPost（AI 长请求 600s 超时）
│   │   ├── router/index.js         # 路由 + 菜单权限
│   │   ├── stores/                 # Pinia（auth / settings）
│   │   ├── views/                  # 页面组件
│   │   │   ├── Layout.vue          # 主布局 + 顶部消息中心
│   │   │   ├── Dashboard.vue       # 驾驶舱（含当日/次日应用中心工作计划）
│   │   │   ├── Cockpit.vue         # AI 驾驶舱
│   │   │   ├── Sandbox.vue         # 营销作战沙盘
│   │   │   ├── Visits.vue          # 拜访排班 + 日历视图
│   │   │   ├── WorkSummaryDialog.vue # AI 工作总结对话框
│   │   │   ├── Qa.vue              # 智能助手（DeepSeek 风格）
│   │   │   ├── Receivables.vue     # 两金明细表
│   │   │   ├── ProjectCost.vue     # 项目成本核算（审批流）
│   │   │   ├── OpportunityCost.vue # 商机成本评估
│   │   │   ├── MarketTasks.vue     # 市场任务单
│   │   │   ├── ...
│   │   │   └── Login.vue
│   │   ├── utils/markdown.js       # 自研轻量 Markdown 渲染器（智能助手用）
│   │   ├── assets/china.json       # ECharts 中国地图 GeoJSON
│   │   └── locales/                # 中/英 i18n
│   ├── vite.config.js
│   └── package.json
├── .env.example                    # MYSQL_HOST / MYSQL_USER / MYSQL_PASSWORD 等
├── docker-compose.yml              # 生产部署（前端 Nginx + 后端 Flask）
└── readme.md
```

## 快速开始

### 环境前置

- Python 3.8+（依赖 `backend/vendor/` 内嵌，无需额外 pip）
- Node.js 18+
- MySQL 8.0（远端实例 `10.200.100.108:3308`，`crm` 库，账号见 `.env`）
- （可选）vLLM 推理服务（`http://10.200.100.74:8000/v1`），开启 AI 能力

### 后端

```bash
cd backend
python app.py
# Flask dev server 监听 http://0.0.0.0:5000
# 首次启动自动建表（91 张）并启动 scheduler（情报采集 + LLM 商机分析）
```

### 前端

```bash
cd frontend
npm install
npm run dev
# Vite dev server 监听 http://localhost:8080
# Vite 直服务源码，改 .vue 无需重新 build，硬刷新即可
```

### 登录

- 默认管理员（应用中心主任）：`yewei / yewei123`

## 数据库配置

数据库已于 2026-11-17 迁移到远端 MySQL 实例，配置以项目根目录 `.env` 为准。

| 变量 | 当前值 |
|------|------|
| `MYSQL_HOST` | `10.200.100.108` |
| `MYSQL_PORT` | `3308` |
| `MYSQL_USER` | `crm`（仅 `crm` 库权限，无 GRANT OPTION） |
| `MYSQL_PASSWORD` | `Crm@MySql_2026` |
| `MYSQL_DATABASE` | `crm`（utf8mb4 / utf8mb4_0900_ai_ci） |

连接串：

```
mysql://crm:Crm%40MySql_2026@10.200.100.108:3308/crm?charset=utf8mb4
```

`backend/db.py` 的默认值已同步为远端地址（`10.200.100.108:3308`），本地库已停用；密码必须由 `.env` 提供，缺失时会直接连接失败而不会静默回退到本地。远端实例的 `root` 账号仅用于运维，业务进程一律使用 `crm` 账号。

迁移沿革：SQLite（`crm_app.db`）→ 本地 MySQL `127.0.0.1:3306`（2026-09）→ 远端 MySQL `10.200.100.108:3308`（2026-11-17）。旧 .db 备份保留在项目根目录（`crm_app.db.bak_*`）。

**数据备份**（远端实例，需 root）：

```bash
mysqldump -h 10.200.100.108 -P 3308 -u root -p \
  --single-transaction --set-gtid-purged=OFF --no-tablespaces \
  --default-character-set=utf8mb4 crm > crm_backup_YYYYMMDD.sql
```

**整库迁移/恢复**（`cmd /c` 重定向在部分环境被禁用，用 `source` 代替）：

```bash
mysql -h <host> -P <port> -u <user> -p --default-character-set=utf8mb4 crm \
  -e "source /path/to/crm_backup_YYYYMMDD.sql"
```

## 功能模块

| 模块 | 菜单路径 | 说明 |
|------|----------|------|
| 驾驶舱 | 📊 销售管理 / Dashboard.vue | 数据统计、销售排行榜、今日/次日应用中心工作计划 |
| AI 驾驶舱 | 🚀 AI驾驶舱 / Cockpit.vue | 全局指标、7 天趋势、商机雷达、AI 搜索、销售提醒 |
| 客户管理 | 👥 销售管理 / Customers.vue | CRUD、分级、多负责人、合并、公海池、3D 画像 |
| 商机管理 | 🎯 销售管理 / Business.vue | 商机跟踪、干系人、7-Agent LLM 自动评分 |
| 合同管理 | 📜 销售管理 / Contracts.vue | 合同 CRUD、待回款、历史合同标记、编号唯一校验 |
| 验收管理 | 📋 销售管理 / Acceptance.vue | 验收记录（税额独立字段）、含税收入累计 |
| 回款管理 | 💰 销售管理 / Payments.vue | 回款记录、待回款自动计算 |
| 两金明细表 | 🧾 销售管理 / Receivables.vue | 应收账款/合同资产、季度快照、客户性质人工填报、风险评级 |
| 拜访排班 | 📅 销售管理 / Visits.vue | 日历/列表/人员三种视图、AI 计划分析、AI 复盘、事项完成自动沉淀知识库 |
| AI 工作总结 | 拜访排班对话框 | 周/月总结 LLM 生成、历史记录管理、指定任意周期重新分析、Word 导出 |
| 营销作战沙盘 | 🎖️ 销售管理 / Sandbox.vue | ECharts 中国地图、客户阵地散点、重点战区 effectScatter、人员位置推断、未定位客户补录 |
| 营销管理 | 📢 营销管理 / Marketing.vue | 市场活动 |
| 智能助手 | 🔧 系统管理 / Qa.vue | DeepSeek 风格、多轮上下文、函数调用、SSE 流式、停止生成、Markdown 自研渲染 |
| 项目管理 | 📋 项目管理 / Projects.vue | 商机项目 + 合同项目切换、成员分配 |
| 工时管理 | ⏱️ 项目管理 / WorkHours.vue | 填报、审批流（技术主任/项目经理/人力） |
| 项目成本核算 | 💰 项目管理 / ProjectCost.vue | 审批流（拟制→部门审→财务审→终审）、导出 Excel |
| 商机成本评估 | 📐 项目管理 / OpportunityCost.vue | 销售发起→技术主任工时确认→销售外协/其他→提交生效 |
| 市场任务单 | 📨 项目管理 / MarketTasks.vue | 跨部门审批流 |
| 工时分摊 | ⏱️ 人事考核 / WorkCost.vue | dept_month_costs + dept_hour_allocations |
| 季度考核 | 📊 人事考核 / QuarterlyAssessment.vue | S/A/B/C/D 五档、校准系数 |
| AI 情报中心 | 📡 AI情报中心 | 情报与线索、招标文件研判、客户画像、竞争对手分析、AI 日报、任务监控、标签与能力 |
| 知识库 | 📚 Knowledge.vue | 条目管理、向量搜索、批量上传不自动分析 |
| 消息中心 | 顶部 🔔 | 销售提醒 / 审批待办 / 业务到期 / 系统日志；新消息弹窗 + 铃铛抖动 + 60s 轮询 |
| 操作日志 | /operation-logs | 分页 + 模块/操作类型筛选 |

## AI 能力概览

- **7-Agent 商机分析**：采集 → 信息分类 → 业务分类（三级标签）→ 实体识别 → 项目分析 → 能力匹配 → 机会评分 → 销售建议（每日 20:00-21:00 定时）
- **双引擎情报筛选**：关键词硬过滤 + 语义 LLM 打分，入库前综合评分 ≥ 40
- **智能助手函数调用**：`qa_engine.is_contextual_followup` 识别指代追问，自动选择函数（如"那这个合同总额"→ `get_top_contract_by_amount` 而非关键词函数）
- **工作总结 LLM**：关键指标摘要注入 Prompt，强制逐项引用（回款笔数/金额等核心数字不遗漏）
- **拜访排班 AI**：自动推测拜访目标与资源需求（关联客户在途商机）

## 定时任务

| 时间 | 任务 |
|------|------|
| 每小时 | 原始情报采集（ccgp.gov.cn + AI 搜索）→ 关键词初筛 → 入库 raw_intelligence |
| 每日 20:00-21:00 | 7-Agent LLM 商机分析（pending raw_intelligence，limit=50） |
| 每日 21:00-23:00 | 高分线索（score≥60 且 is_relevant=1）自动导入 CRM scraped_leads |

## 重启后端

后端单实例模式，重启前需杀进程：

```powershell
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
cd backend
python app.py
```

## 已知坑

- PowerShell `Set-Content -Encoding UTF8` 给 .py 加 BOM 会导致 Python SyntaxError，写 Python 文件用 Write/Edit 工具或 `[System.IO.File]::WriteAllBytes`
- MySQL `SUM()` / `AVG()` 返回 Decimal（vs SQLite 的 int/float），`db.py` 已统一转 float
- MySQL 派生表 COUNT(*) 需要别名，否则报 error 1248
- Scheduler 必须在 `main()` 里启动，不能在模块顶层（LLM 长调用会阻塞数据库连接）
- 前端长请求（AI 抓取/总结）必须用 `api.longPost`，10 分钟超时
- vLLM 服务（`10.200.100.74:8000`）无 `/embeddings` 端点，向量检索走 `vector_search.generate_embedding`
- DuckerDuckGo 在国内不可用，统一走 Bing
