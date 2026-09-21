# 能力模型 / 关键词管理 / 业务标签 三模块合并

## Context

系统中"能力模型"、"关键词管理"、"业务标签"三个功能存在数据结构和功能重叠：

| 模块 | 表 | 核心字段 | 用途 | 消费方 |
|---|---|---|---|---|
| 能力模型 | `capabilities` | name, level, keywords, synonyms, related_industries, products, solutions, cases | 项目能力匹配 | `capability_matcher.py` → `scoring_model.py` |
| 关键词管理 | `keywords` | keyword, synonyms, exclude_words, business_tag | 情报采集内容过滤 | `intelligence.py` `_load_active_keywords()` (fallback), `ai_opportunity.py` |
| 业务标签 | `business_tags` | parent_id, name, level, synonyms, related_words, exclude_words | 三级树业务分类+内容过滤 | `intelligence.py` `_load_content_matcher()` (优先), `ai_agents.py` |

三表都有 name/keyword + synonyms + exclude_words，`intelligence.py` 已有"标签优先、关键词回退"逻辑。合并目标：以 `business_tags` 三级树为统一骨架，吸收关键词表和能力模型表的字段，三前端页面合一。

## 实施步骤

### 1. 扩展 business_tags 表结构

[backend/routes/business_tags.py](file:///c:/Program/Files/python/crm/backend/routes/business_tags.py) 的 `_ensure_tables` 中 ALTER TABLE 增加：
- `capability_level VARCHAR(20)` — 成熟度（mature/growing/learning/null，null 表示非能力标签）
- `capability_desc TEXT` — 能力描述
- `products MEDIUMTEXT` — 产品（JSON 数组）
- `solutions MEDIUMTEXT` — 方案（JSON 数组）
- `cases MEDIUMTEXT` — 案例（JSON 数组）

### 2. 数据迁移脚本

新建 `backend/scripts/migrate_merge_tags.py`，幂等执行：

**A. keywords → business_tags**
- keywords 表每条记录：keyword → business_tags.name（三级树叶子），synonyms → business_tags.synonyms，exclude_words → business_tags.exclude_words
- keyword_groups 已有三级分类，若 keywords.group_id 关联了 keyword_groups，则映射为 business_tags 的 parent_id（先迁 keyword_groups 树结构，再挂 keywords 叶子）
- 迁完将 keywords 表标记 disabled（保留表不删，防回滚）

**B. capabilities → business_tags**
- capabilities 表每条：name → business_tags.name，keywords+synonyms → business_tags.synonyms（合并），level → capability_level，description → capability_desc，products/solutions/cases 对应迁入
- related_industries → 挂到对应行业标签作为子节点（或作为 related_words）
- 迁完 capabilities 表标记 disabled

### 3. 后端匹配器统一

**A. `business_tags.py` 扩展 `load_tag_matcher`**
- 返回结构增加 `capabilities` 列表（capability_level 非空的标签节点），供 capability_matcher 使用

**B. `capability_matcher.py` 改为从 business_tags 加载**
- `load_capabilities(db)` → 调 `load_tag_matcher` 获取 capability 字段
- `match_project_capabilities` 匹配逻辑不变（name + synonyms + related_words 组合为命中词集合）

**C. `intelligence.py` `_load_content_matcher` 简化**
- 移除 keywords fallback 分支，统一只走 business_tags
- `_load_active_keywords` 标记 deprecated 但保留函数签名

**D. `ai_opportunity.py` 改为从 business_tags 加载**
- L17 `SELECT keyword, synonyms, business_tag FROM keywords` → 从 business_tags 读取 name+synonyms

### 4. 后端 API 兼容

- `GET/POST/PUT/DELETE /api/capabilities` → 保留路由但内部代理到 business_tags（按 capability_level 非空过滤）
- `GET/POST/PUT/DELETE /api/keywords` → 保留路由但内部代理到 business_tags（返回旧格式兼容字段）
- `POST /api/capabilities/match` → 内部调 `capability_matcher.match_project_capabilities`（不变）
- `POST /api/capabilities/seed` → 迁移到 business_tags 的 seed 逻辑
- `GET /api/keywords/groups` → 从 business_tags 树构建兼容返回

### 5. 前端页面合并

**A. [BusinessTags.vue](file:///c:/Program/Files/python/crm/frontend/src/views/BusinessTags.vue) 扩展为统一管理页**
- 树形表格保留现有三级结构
- 每个标签节点的编辑弹窗增加可选字段：能力等级（下拉/空）、能力描述、产品、方案、案例
- 保留"同义词/关联词/排除词"现有字段

**B. 菜单调整 [Layout.vue](file:///c:/Program/Files/python/crm/frontend/src/views/Layout.vue#L116-L135)**
- 删除"能力模型"和"关键词管理"两个菜单项
- "业务标签"改名为"业务标签与能力"或"标签能力管理"

**C. 路由调整 [router/index.js](file:///c:/Program/Files/python/crm/frontend/src/router/index.js)**
- 删除 /capabilities 和 /keywords 路由（或保留重定向到 /business-tags）
- Capabilities.vue 和 Keywords.vue 文件删除

**D. 消费方更新**
- [IntelligenceLeads.vue](file:///c:/Program/Files/python/crm/frontend/src/views/IntelligenceLeads.vue) L935 `/capabilities/match` 调用不变（后端已兼容代理）

### 6. 验证

- 后端 `python -m py_compile` 全部修改文件
- 迁移脚本执行后检查 business_tags 数据量 = 原 tags + keywords + capabilities
- 冒烟测试：`/api/business-tags`（树含能力字段）、`/api/capabilities`（代理返回）、`/api/capabilities/match`（匹配正常）、`/api/keywords`（代理返回兼容格式）
- 前端 `npm run build` 通过
- 手动验证：情报采集过滤正常、商机评分能力匹配正常、AI 日报生成正常

## 关键文件

| 文件 | 改动 |
|---|---|
| backend/routes/business_tags.py | 扩展表结构 + load_tag_matcher 增加能力字段 |
| backend/capability_matcher.py | load_capabilities 改为从 business_tags 读取 |
| backend/ai_opportunity.py | L15-27 改为从 business_tags 读取关键词 |
| backend/routes/intelligence.py | _load_content_matcher 移除 keywords fallback |
| backend/routes/capabilities.py | 内部代理到 business_tags |
| backend/routes/keywords.py | 内部代理到 business_tags |
| backend/scripts/migrate_merge_tags.py | 新建迁移脚本 |
| frontend/src/views/BusinessTags.vue | 扩展编辑弹窗增加能力字段 |
| frontend/src/views/Layout.vue | 删除两个菜单项 |
| frontend/src/router/index.js | 删除/重定向两个路由 |
| frontend/src/views/Capabilities.vue | 删除 |
| frontend/src/views/Keywords.vue | 删除 |
