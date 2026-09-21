# SQLite → MySQL 硬切换迁移计划

## Context

CRM 后端当前使用本地 SQLite（crm_app.db，77 表/12MB），全项目裸 SQL、无 ORM。用户要求迁移到 MySQL：本机 Windows 安装 MySQL 8，硬切换（迁完移除 SQLite 代码路径）。

**改造面**：`get_db()` 被 46 文件调用 360 处；~20 文件 31 处直接 `sqlite3.connect`；SQLite 专属语法（INSERT OR REPLACE/IGNORE、strftime、datetime('now')、PRAGMA、AUTOINCREMENT、`||`）约 467 处 / 30+ 文件。

**核心思路**：新增 sqlite3 兼容适配层 `backend/db.py`（PyMySQL 实现），`get_db()` 签名与行为不变 → 360 处调用零改动；只做三类改动：① 直连点换 `open_db()`；② SQL 方言改写；③ `ensure_tables()` 从建表降级为校验（schema 唯一来源 = 迁移脚本）。

## 实施步骤

### 1. MySQL 服务端（Windows 本机）
- `winget install Oracle.MySQL`（先 `winget search mysql` 确认包 ID）
- 建库建用户：
  ```sql
  CREATE DATABASE crm CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
  CREATE USER 'crm'@'localhost' IDENTIFIED BY '<强密码>';
  GRANT ALL PRIVILEGES ON crm.* TO 'crm'@'localhost';
  ```
- my.ini 持久化 sql_mode：`STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION,PIPES_AS_CONCAT`
  - 加 `PIPES_AS_CONCAT`：代码中 `||` 连接符免改写
  - 去掉 `ONLY_FULL_GROUP_BY`：SQLite 宽松 GROUP BY 直接可用

### 2. 依赖与配置
- requirements.txt 加 `PyMySQL==1.1.1`（cryptography 已有，caching_sha2_password 认证可用）
- .env/.env.example 新增 `MYSQL_HOST/PORT/USER/PASSWORD/DATABASE`；DB_PATH 后续移除

### 3. db.py 适配层（新增，核心）
- 连接：`pymysql.connect(charset='utf8mb4', autocommit=False)`，与 sqlite3 隐式事务 + 显式 `conn.commit()` 行为对齐；删全部 PRAGMA
- **Row 类**：支持 `row["col"]`、`row[0]` 数字索引（contracts.py L513 等在用）、`dict(row)`、`len()`
- **Cursor 类**：
  - `execute()` **必须返回 self**（PyMySQL 返回 rowcount int，extensions.py L113 链式取值会炸）
  - `?` → `%s` 翻译：逐字符扫描维护"单引号字面量内"状态（'' 转义），字面量外的 `%` → `%%`（PyMySQL 内部 `query % args` 格式化，`DATE_FORMAT('%Y-%m')` 类必须转义）；无参数时不传 args
  - lastrowid/rowcount/description 透传；fetchone/fetchall 返回值包装为 Row；executemany 透传
- **Connection 类**：提供 `.execute()/.executemany()` 快捷方式（extensions.py L46、L2490 在用），转发内部默认 cursor；cursor()/commit()/rollback()/close() 透传
- 对外入口：`get_db()`（Flask g.db 缓存，teardown 关闭，生命周期同现状）、`open_db()`（请求外用：调度器/线程池，调用方自己 commit+close）
- 连接策略：每请求直连不加池（本机建连 1-3ms，几十用户规模无压力）
- 附带单测：含 `?`、`%`、引号字面量的 SQL 翻译用例

### 4. 迁移脚本（新增 backend/scripts/migrate_sqlite_to_mysql.py）
- 流程：sqlite_master 读全部表 → PRAGMA table_info/index_list → 生成 MySQL DDL → 建表 → 分批 500 行 executemany 拷贝（保留主键 ID）→ `AUTO_INCREMENT = max(id)+1` → 行数 + max(id) 双边校验
- 类型映射：
  - `INTEGER PRIMARY KEY AUTOINCREMENT` → `BIGINT AUTO_INCREMENT PRIMARY KEY`；INTEGER→BIGINT；REAL→DOUBLE；BLOB→MEDIUMBLOB
  - TEXT 无默认值 → **MEDIUMTEXT**（防 LLM 长输出 strict 模式截断报错）
  - TEXT 带字面量默认值（全库大量 `DEFAULT 'x'`）→ `VARCHAR(255) DEFAULT 'x'`（MySQL TEXT 列不允许字面量默认值，关键坑）
  - 日期类 TEXT 列**保持 TEXT 不转 DATETIME**（应用层写的是 `strftime` 格式字符串，兼容最稳）
- TEXT 列上的索引 → 前缀索引 `col(191)`；标识符全部反引号 + MySQL 保留字列名检测报告
- 源库只读打开（`file:...?mode=ro`），第一步强制备份 `crm_app.db.bak_YYYYMMDD`
- 参数：`--drop`（全量重迁）/ `--truncate`；无参数时目标表非空拒绝执行
- 建表职责收口：迁移脚本是唯一 schema 来源；`ai_agents.py` L554 运行时惰性建表 `intelligence_agent_results` 并入脚本

### 5. extensions.py 切换
- `get_db()` 内部换适配层（保留 g.db 缓存与 close_db teardown）；删 PRAGMA
- `ensure_tables()` 改为校验模式：information_schema 确认 77 表齐全，缺失 fail-fast 提示先跑迁移脚本（不再执行任何 CREATE/ALTER）
- `PRAGMA table_info` 封装 helper `table_columns(cursor, table)` 查 information_schema
- `update_customer_last_follow()`（L2490）改 `open_db()`

### 6. 直连文件改造（~22 文件）
- 统一模式：`conn = sqlite3.connect(DB_PATH, ...)` → `conn = open_db()`，生命周期不变（调用方 commit+close）
- 清单：scheduler.py L17-23（后台线程每 job 短连接，天然规避 wait_timeout 断连）、routes/quarterly_assessment.py L722-725（线程池 worker）、ai_agents.py、ai_analysis.py、ai_daily_report.py、ai_opportunity.py、llm_gateway.py、task_system.py、vector_search.py、routes/ai_agent.py、routes/knowledge_graph.py 等
- app.py：health check 的 `os.path.exists(DB_PATH)` 改 `SELECT 1` 探活；清理 DB_PATH import

### 7. SQL 方言改写（~30 文件，机械替换 + 人工复核）
| 类别 | 规则 | 复核 |
|---|---|---|
| 写入冲突（15 处/5 文件） | `INSERT OR REPLACE` → `REPLACE INTO`；`INSERT OR IGNORE` → `INSERT IGNORE` | REPLACE rowcount=2，依赖 rowcount 的分支过一遍 |
| 日期函数（100+ 处，dashboard 35/reports 22 为主） | `strftime('%Y',c)` → `YEAR(c)`；`strftime('%Y-%m',c)` → `DATE_FORMAT(c,'%Y-%m')` | YEAR() 返回 int 与字符串参数比较处核对 |
| 当前时间 | `datetime('now','localtime')` → `NOW()`；`datetime('now')`（UTC 语义）→ `UTC_TIMESTAMP()`；`date('now')` → `CURDATE()` | 带 `'+N days'` 修饰符的人工改 `DATE_ADD`（逐个 grep 变体） |
| PRAGMA | 改 helper（见步骤 5） | — |
| 兜底 grep | `RANDOM()` → `RAND()`、`julianday(` → `DATEDIFF`、`glob ` → LIKE | 逐个人工 |
- `ai_agents.py` L554 建表 DDL 手改 MySQL 方言
- LIKE 大小写：ci 排序规则下与 SQLite ASCII 行为一致，无需改

### 8. 正式迁移与验证
1. 备份 crm_app.db → 跑迁移脚本 → 行数/max(id) 校验
2. **基线快照回归**：切换前在 SQLite 上抓 `/api/dashboard/*`、`/api/reports/*` JSON 存基线；切后同参数重放 diff
3. 启动 `python app.py`：ensure_tables 校验通过、`GET /health` database:ok
4. 冒烟（先 GET 后写、写完 GET 复核）：
   - 登录（验证 ci 排序 + bcrypt）
   - 合同：列表/新建/编辑/新增回款（触发 auto_complete_if_paid_off + INSERT OR REPLACE 路径）/ 成本核算接口
   - 拜访新建 + 列表（visits.py 13 处 strftime）；工时录入汇总
   - 季度考核导入（线程池 open_db 异步写入）
   - 驾驶舱/报表与基线 diff；知识库上传+检索（BLOB 向量读写）
   - 调度器手动触发，日志无断连报错
5. 前端逐页点开，重点核对仪表盘/报表数字

### 9. 收尾
- grep 确认无 `sqlite3` 残留（vendor/、scripts/ 除外）；删 DB_PATH；更新 docker-commands.md（预留 Docker MySQL 环境变量说明）

## 回滚保障
- 数据：SQLite 源库全程只读 + 迁移前强制备份，无数据污染
- 代码：从当前分支切 `feature/mysql-migration` 实施；出问题切回 + 原 DB_PATH 即回滚，RTO≈30 秒；稳定 1-2 周后再清理 SQLite 残留

## 关键文件
- `backend/db.py`（新增适配层）
- `backend/scripts/migrate_sqlite_to_mysql.py`（新增迁移脚本）
- `backend/extensions.py`（get_db/ensure_tables/方言重灾区 72 处）
- `backend/scheduler.py`、`backend/app.py`（直连与 DB_PATH 清理）
- 方言改写重灾区：routes/dashboard.py(35)、routes/reports.py(22)、routes/knowledge_ext.py(16)、routes/visits.py(13)、routes/contracts.py(10)、routes/leads.py(9)、routes/system.py(7)、routes/cockpit.py、routes/business.py、routes/quarterly_assessment.py、ai_agents.py
