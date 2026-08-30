<template>
  <div class="knowledge-container">
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">📚 企业知识库</h2>
        <p class="page-desc">为智能助手提供分析与决策支持的核心知识资产</p>
      </div>
      <div class="header-right">
        <el-button v-if="activeTab === 'documents'" type="primary" @click="showCreateDialog">
          <span>✚</span><span>新建文档</span>
        </el-button>
        <el-button v-if="activeTab === 'documents'" type="success" @click="showUploadDialog">
          <span>📤</span><span>批量导入</span>
        </el-button>
        <el-button v-if="activeTab === 'documents'" @click="handleSync" :loading="syncing">
          <span>🔄</span><span>同步CRM</span>
        </el-button>
        <el-button v-if="activeTab === 'documents'" @click="handleRebuild" :loading="rebuilding">
          <span>🧩</span><span>重建索引</span>
        </el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-bar" v-if="stats" style="margin-bottom:16px">
      <div class="stat-card">
        <div class="stat-icon">📄</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.total_documents }}</div>
          <div class="stat-label">文档总数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">✅</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.processed_documents }}</div>
          <div class="stat-label">已索引</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">🧠</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.total_vectors }}</div>
          <div class="stat-label">向量索引</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">✨</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.analyzed_documents || 0 }}</div>
          <div class="stat-label">AI已分析</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">📜</div>
        <div class="stat-info">
          <div class="stat-value">{{ (stats.personnel_qualifications || 0) + (stats.company_qualifications || 0) }}</div>
          <div class="stat-label">资质条目</div>
        </div>
      </div>
    </div>

    <el-tabs v-model="activeTab" type="border-card" class="kb-tabs">
      <!-- Tab 1: 知识文档（核心数据源） -->
      <el-tab-pane label="📂 知识文档" name="documents">
        <div class="tab-desc">为智能体提供知识支撑的核心文档库，支持批量导入、向量化索引和语义检索</div>

        <div class="filter-bar">
          <el-select v-model="filterDocType" placeholder="文档类型" clearable style="width:160px" @change="fetchDocuments">
            <el-option v-for="dt in docTypes" :key="dt.value" :label="dt.label" :value="dt.value" />
          </el-select>
          <el-input v-model="keyword" placeholder="搜索标题/内容/标签..." clearable @clear="fetchDocuments" @keyup.enter="fetchDocuments" style="width:280px">
            <template #append><el-button @click="fetchDocuments">搜索</el-button></template>
          </el-input>
          <el-button type="warning" size="small" @click="showSearchDialog">🔍 语义搜索</el-button>
          <el-button type="success" size="small" @click="handleBatchAnalyze" :loading="batchAnalyzing">🧠 批量AI分析</el-button>
        </div>

        <el-table :data="docList" v-loading="docLoading" stripe style="width:100%" @row-click="openDocDetail" max-height="70vh">
          <el-table-column type="index" width="50" />
          <el-table-column prop="title" label="标题" min-width="200">
            <template #default="{ row }">
              <div class="doc-title-cell">
                <span>{{ getDocIcon(row.doc_type) }}</span>
                <span>{{ row.title }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="doc_type_display" label="类型" width="120">
            <template #default="{ row }">
              <el-tag :type="getDocTagType(row.doc_type)" size="small">{{ row.doc_type_display }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="processed" label="索引状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.processed ? 'success' : 'warning'" size="small">
                {{ row.processed ? '✅ 已索引' : '⏳ 待处理' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="analysis_status" label="AI分析" width="150">
            <template #default="{ row }">
              <el-tag v-if="row.analysis_status === 'completed'" type="success" size="small" effect="dark">✨ 已分析</el-tag>
              <el-tag v-else-if="row.analysis_status === 'failed'" type="danger" size="small">❌ 失败</el-tag>
              <el-tag v-else type="info" size="small">⏳ 待分析</el-tag>
              <div v-if="row.analysis_summary" class="analysis-cell">{{ row.analysis_summary }}</div>
            </template>
          </el-table-column>
          <el-table-column prop="tags" label="标签" width="180">
            <template #default="{ row }">
              <span v-if="row.tags">{{ row.tags }}</span>
              <span v-else class="empty-cell">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="170">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="140" fixed="right" @click.stop>
            <template #default="{ row }">
              <el-button text size="small" @click="showEditDialog(row)">编辑</el-button>
              <el-button text size="small" type="danger" @click="handleDeleteDoc(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="pagination-bar">
          <el-pagination v-model:current-page="docPage" :page-size="20" :total="docTotal" layout="total, prev, pager, next" @current-change="fetchDocuments" />
        </div>
      </el-tab-pane>

      <!-- Tab 2: AI 洞察 -->
      <el-tab-pane label="🧠 AI洞察" name="insights">
        <div class="tab-desc">AI 自动生成的拜访复盘、跟进洞察与销售经验，同时聚合上传的拜访纪要，沉淀企业智慧</div>

        <div class="filter-bar">
          <el-select v-model="filterCategory" placeholder="全部分类" clearable @change="fetchInsights" style="width:160px">
            <el-option v-for="c in insightCategories" :key="c.value" :label="c.label" :value="c.value" />
          </el-select>
          <el-input v-model="insightKeyword" placeholder="搜索标题/摘要..." clearable @clear="fetchInsights" @keyup.enter="fetchInsights" style="width:280px">
            <template #append><el-button @click="fetchInsights">搜索</el-button></template>
          </el-input>
          <div class="stat-info">共 {{ insightTotal }} 条洞察</div>
        </div>

        <div class="knowledge-grid" v-loading="insightLoading">
          <div v-if="!insightList.length && !insightLoading" class="empty-state">
            <div class="empty-icon">🧠</div>
            <div class="empty-text">暂无 AI 洞察</div>
            <div class="empty-desc">完成拜访或商机跟进后，AI 会自动生成复盘洞察</div>
          </div>

          <div v-for="item in insightList" :key="(item._source || 'insight') + '_' + item.id" class="knowledge-card" @click="openInsightDetail(item)">
            <div class="card-header">
              <span :class="['category-badge', 'cat-' + item.category]">{{ insightCategoryLabel(item.category) }}</span>
              <el-tag v-if="item._source === 'document'" size="small" type="info" effect="plain">📎 上传</el-tag>
              <el-tag v-else size="small" type="success" effect="plain">🧠 AI</el-tag>
              <el-tag v-if="item.analysis_status === 'completed'" size="small" type="warning" effect="plain">✨ 已分析</el-tag>
              <span class="card-date">{{ formatDate(item.created_at) }}</span>
            </div>
            <div class="card-title">{{ item.title }}</div>
            <div class="card-summary">{{ item.analysis_summary || item.summary || '暂无摘要' }}</div>
            <div class="card-footer">
              <span class="card-meta" v-if="item.customer_company">🏢 {{ item.customer_company }}</span>
              <span class="card-meta" v-if="item.owner_name">✍️ {{ item.owner_name }}</span>
              <div class="card-actions" @click.stop>
                <el-button text size="small" @click="editInsight(item)">编辑</el-button>
                <el-button text size="small" type="danger" @click="deleteInsight(item)">删除</el-button>
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 3: 语义搜索 -->
      <el-tab-pane label="🔍 语义搜索" name="search">
        <div class="tab-desc">基于向量索引的智能语义检索，帮助智能体快速找到相关知识</div>

        <div class="search-panel">
          <el-form :model="searchForm" label-width="100px" inline>
            <el-form-item label="搜索词">
              <el-input v-model="searchForm.query" placeholder="输入自然语言搜索，如：医疗行业商机跟进策略" style="width:400px" @keyup.enter="doSemanticSearch" />
            </el-form-item>
            <el-form-item label="搜索方式">
              <el-radio-group v-model="searchForm.search_type">
                <el-radio label="hybrid">混合搜索</el-radio>
                <el-radio label="semantic">语义搜索</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="doSemanticSearch" :loading="searching">🔍 搜索</el-button>
            </el-form-item>
          </el-form>
        </div>

        <div v-if="searchResults.length" class="search-results">
          <div v-for="(r, i) in searchResults" :key="i" class="search-result-item">
            <div class="result-header">
              <span class="result-title">{{ r.title }}</span>
              <el-tag size="small" :type="getDocTagType(r.doc_type)">{{ r.doc_type_display }}</el-tag>
              <span class="similarity">相似度: {{ (r.similarity * 100).toFixed(1) }}%</span>
            </div>
            <div class="result-content" v-if="r.summary">{{ r.summary }}</div>
            <div class="result-meta" v-if="r.tags">
              <el-tag v-for="tag in r.tags.split(',').slice(0, 3)" :key="tag" size="small" class="meta-tag">{{ tag }}</el-tag>
            </div>
          </div>
        </div>

        <div v-else-if="searched && !searching" class="empty-state">
          <div class="empty-icon">🔍</div>
          <div class="empty-text">未找到相关结果</div>
          <div class="empty-desc">尝试调整搜索词或使用更通用的描述</div>
        </div>
      </el-tab-pane>

      <!-- Tab 4: 知识图谱 -->
      <!-- v-if="activeTab==='graph' 关键修复：切到Tab时才挂载，容器从一开始就有真实宽高，避免ECharts初始化width/height=0 -->
      <el-tab-pane label="🕸️ 知识图谱" name="graph">
        <div class="tab-desc">自动从文档中提取实体和关系，构建企业知识图谱，可视化展示知识关联</div>
        <KnowledgeGraph v-if="activeTab === 'graph'" ref="knowledgeGraphRef" />
      </el-tab-pane>
    </el-tabs>

    <!-- 文档详情对话框 -->
    <el-dialog v-model="detailVisible" title="文档详情" width="750px" top="5vh" :close-on-click-modal="false" :close-on-press-escape="false">
      <div v-if="currentDoc" class="detail-content">
        <div class="detail-header">
          <el-tag :type="getDocTagType(currentDoc.doc_type)">{{ currentDoc.doc_type_display }}</el-tag>
          <el-tag v-if="currentDoc.analysis_status === 'completed'" size="small" type="success" effect="dark">✨ AI已分析</el-tag>
          <el-tag v-else-if="currentDoc.analysis_status === 'failed'" size="small" type="danger" effect="plain">❌ 分析失败</el-tag>
          <el-tag v-else size="small" type="info" effect="plain">⏳ 待分析</el-tag>
          <span class="detail-time">{{ formatDate(currentDoc.created_at) }}</span>
          <el-button size="small" type="primary" plain @click="handleAnalyzeDoc" :loading="analyzing">
            {{ currentDoc.analysis_status === 'completed' ? '🔄 重新分析' : '✨ AI分析' }}
          </el-button>
        </div>
        <h3 class="detail-title">{{ currentDoc.title }}</h3>

        <!-- AI 分析结果 -->
        <div v-if="currentDoc.analysis" class="analysis-box">
          <div class="analysis-header">
            <span class="analysis-title">🧠 AI 智能分析</span>
            <span class="analysis-meta">
              <el-tag size="small" type="info">{{ currentDoc.analysis.analysis_method === 'llm' ? 'LLM大模型' : '规则引擎' }}</el-tag>
              <span v-if="currentDoc.analysis.analyzed_at" class="analyzed-at">{{ currentDoc.analysis.analyzed_at }}</span>
            </span>
          </div>

          <div v-if="currentDoc.analysis.summary" class="analysis-section">
            <div class="analysis-label">📌 AI摘要</div>
            <div class="analysis-text">{{ currentDoc.analysis.summary }}</div>
          </div>

          <div class="analysis-grid">
            <div v-if="currentDoc.analysis.key_findings?.length" class="analysis-card findings">
              <div class="analysis-card-title">🔍 关键发现</div>
              <ul><li v-for="(f, i) in currentDoc.analysis.key_findings" :key="i">{{ f }}</li></ul>
            </div>

            <div v-if="currentDoc.analysis.customer_needs?.length" class="analysis-card needs">
              <div class="analysis-card-title">💡 客户需求</div>
              <ul><li v-for="(f, i) in currentDoc.analysis.customer_needs" :key="i">{{ f }}</li></ul>
            </div>

            <div v-if="currentDoc.analysis.next_actions?.length" class="analysis-card actions">
              <div class="analysis-card-title">📌 下一步行动</div>
              <ul><li v-for="(f, i) in currentDoc.analysis.next_actions" :key="i">{{ f }}</li></ul>
            </div>

            <div v-if="currentDoc.analysis.risks?.length" class="analysis-card risks">
              <div class="analysis-card-title">⚠️ 风险提示</div>
              <ul><li v-for="(f, i) in currentDoc.analysis.risks" :key="i">{{ f }}</li></ul>
            </div>

            <div v-if="currentDoc.analysis.opportunities?.length" class="analysis-card opportunities">
              <div class="analysis-card-title">🎯 机会点</div>
              <ul><li v-for="(f, i) in currentDoc.analysis.opportunities" :key="i">{{ f }}</li></ul>
            </div>
          </div>

          <div v-if="currentDoc.analysis.tags?.length" class="analysis-tags">
            <span class="analysis-label">🏷️ AI关键词：</span>
            <el-tag v-for="t in currentDoc.analysis.tags" :key="t" size="small" class="analysis-tag">{{ t }}</el-tag>
          </div>

          <div class="analysis-sentiment">
            <span class="analysis-label">🎭 情感倾向：</span>
            <el-tag v-if="currentDoc.analysis.sentiment === 'positive'" type="success" size="small">积极正面</el-tag>
            <el-tag v-else-if="currentDoc.analysis.sentiment === 'negative'" type="danger" size="small">消极负面</el-tag>
            <el-tag v-else type="info" size="small">中性</el-tag>
          </div>
        </div>

        <div class="detail-meta" v-if="currentDoc.tags">
          <el-tag v-for="tag in currentDoc.tags.split(',')" :key="tag" size="small" class="meta-tag">{{ tag }}</el-tag>
        </div>
        <div class="detail-summary" v-if="currentDoc.summary && !currentDoc.analysis">
          <div class="section-label">📌 摘要</div>
          <div>{{ currentDoc.summary }}</div>
        </div>
        <div class="detail-body" v-if="currentDoc.content">
          <div class="section-label">📝 正文</div>
          <div class="content-box">{{ currentDoc.content }}</div>
        </div>
        <div class="detail-footer">
          <span v-if="currentDoc.file_name">📎 {{ currentDoc.file_name }}</span>
          <span v-if="currentDoc.owner_id">✍️ {{ currentDoc.owner_id }}</span>
        </div>
      </div>

      <div v-if="currentInsight" class="detail-content">
        <div class="detail-header">
          <span :class="['category-badge', 'cat-' + currentInsight.category]">{{ insightCategoryLabel(currentInsight.category) }}</span>
          <el-tag v-if="currentInsight._source === 'document'" size="small" type="info" effect="plain">📎 上传文档</el-tag>
          <el-tag v-else size="small" type="success" effect="plain">🧠 AI生成</el-tag>
          <span class="detail-time">{{ formatDate(currentInsight.created_at) }}</span>
        </div>
        <h3 class="detail-title">{{ currentInsight.title }}</h3>
        <div class="detail-meta">
          <span v-if="currentInsight.customer_company">🏢 {{ currentInsight.customer_company }}</span>
          <span v-if="currentInsight.owner_name">✍️ {{ currentInsight.owner_name }}</span>
          <span v-if="currentInsight.file_name">📎 {{ currentInsight.file_name }}</span>
          <span v-if="currentInsight.tags">🏷️ {{ currentInsight.tags }}</span>
        </div>

        <!-- AI 分析结果（上传文档且已分析时显示） -->
        <div v-if="currentInsight._source === 'document' && currentInsight.analysis" class="analysis-box">
          <div class="analysis-header">
            <span class="analysis-title">🧠 AI 智能分析</span>
            <span class="analysis-meta">
              <el-tag size="small" type="info">{{ currentInsight.analysis.analysis_method === 'llm' ? 'LLM大模型' : '规则引擎' }}</el-tag>
              <span v-if="currentInsight.analysis.analyzed_at" class="analyzed-at">{{ currentInsight.analysis.analyzed_at }}</span>
            </span>
          </div>
          <div v-if="currentInsight.analysis.summary" class="analysis-section">
            <div class="analysis-label">📌 AI摘要</div>
            <div class="analysis-text">{{ currentInsight.analysis.summary }}</div>
          </div>
          <div class="analysis-grid">
            <div v-if="currentInsight.analysis.key_findings?.length" class="analysis-card findings">
              <div class="analysis-card-title">🔍 关键发现</div>
              <ul><li v-for="(f, i) in currentInsight.analysis.key_findings" :key="i">{{ f }}</li></ul>
            </div>
            <div v-if="currentInsight.analysis.customer_needs?.length" class="analysis-card needs">
              <div class="analysis-card-title">💡 客户需求</div>
              <ul><li v-for="(f, i) in currentInsight.analysis.customer_needs" :key="i">{{ f }}</li></ul>
            </div>
            <div v-if="currentInsight.analysis.next_actions?.length" class="analysis-card actions">
              <div class="analysis-card-title">📌 下一步行动</div>
              <ul><li v-for="(f, i) in currentInsight.analysis.next_actions" :key="i">{{ f }}</li></ul>
            </div>
            <div v-if="currentInsight.analysis.risks?.length" class="analysis-card risks">
              <div class="analysis-card-title">⚠️ 风险提示</div>
              <ul><li v-for="(f, i) in currentInsight.analysis.risks" :key="i">{{ f }}</li></ul>
            </div>
            <div v-if="currentInsight.analysis.opportunities?.length" class="analysis-card opportunities">
              <div class="analysis-card-title">🎯 机会点</div>
              <ul><li v-for="(f, i) in currentInsight.analysis.opportunities" :key="i">{{ f }}</li></ul>
            </div>
          </div>
        </div>

        <div class="detail-summary" v-if="currentInsight.summary && !currentInsight.analysis">{{ currentInsight.summary }}</div>
        <div class="detail-body" v-if="insightParsedContent && !currentInsight.analysis">
          <template v-if="typeof insightParsedContent === 'object'">
            <div v-if="insightParsedContent.key_findings?.length" class="detail-section">
              <div class="section-title">🔍 关键发现</div>
              <ul><li v-for="(f, i) in insightParsedContent.key_findings" :key="i">{{ f }}</li></ul>
            </div>
            <div v-if="insightParsedContent.customer_needs?.length" class="detail-section">
              <div class="section-title">💡 客户需求</div>
              <ul><li v-for="(f, i) in insightParsedContent.customer_needs" :key="i">{{ f }}</li></ul>
            </div>
            <div v-if="insightParsedContent.next_actions?.length" class="detail-section">
              <div class="section-title">📌 下一步行动</div>
              <ul><li v-for="(f, i) in insightParsedContent.next_actions" :key="i">{{ f }}</li></ul>
            </div>
          </template>
          <template v-else>
            <div class="content-box">{{ currentInsight.content }}</div>
          </template>
        </div>
        <div v-else-if="currentInsight._source === 'document' && currentInsight.content" class="detail-body">
          <div class="section-label">📝 原文内容</div>
          <div class="content-box">{{ currentInsight.content }}</div>
        </div>
      </div>
    </el-dialog>

    <!-- 创建/编辑文档对话框 -->
    <el-dialog v-model="createVisible" :title="editingDoc ? '编辑文档' : '新建知识文档'" width="600px" :close-on-click-modal="false" :close-on-press-escape="false">
      <el-form :model="docForm" label-width="100px" ref="docFormRef">
        <el-form-item label="文档类型" required>
          <el-select v-model="docForm.doc_type" style="width:100%">
            <el-option v-for="dt in docTypes" :key="dt.value" :label="dt.label" :value="dt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="标题" required>
          <el-input v-model="docForm.title" placeholder="请输入文档标题" />
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="docForm.content" type="textarea" :rows="6" placeholder="请输入文档内容，将自动生成向量索引" />
        </el-form-item>
        <el-form-item label="关联客户">
          <el-select
            v-model="docForm.cust_id"
            filterable
            remote
            clearable
            reserve-keyword
            default-first-option
            placeholder="输入客户名称或ID搜索"
            :remote-method="searchCustomers"
            :loading="customerLoading"
            style="width:100%"
          >
            <el-option
              v-for="c in customerOptions"
              :key="c.id"
              :label="`[${c.id}] ${c.company || c.name || ''}`"
              :value="c.id"
            />
            <template #empty>
              <div style="padding:10px; text-align:center; color:#94a3b8">
                {{ customerLoading ? '搜索中...' : '输入关键词或ID搜索' }}
              </div>
            </template>
          </el-select>
        </el-form-item>
        <el-form-item label="关联商机">
          <el-select
            v-model="docForm.business_id"
            filterable
            remote
            clearable
            reserve-keyword
            default-first-option
            placeholder="输入商机名称或ID搜索"
            :remote-method="searchBusinessList"
            :loading="businessLoading"
            style="width:100%"
          >
            <el-option
              v-for="b in businessOptions"
              :key="b.id"
              :label="`[${b.id}] ${b.title || b.name || ''}${b.customer_name ? ' - ' + b.customer_name : ''}`"
              :value="b.id"
            />
            <template #empty>
              <div style="padding:10px; text-align:center; color:#94a3b8">
                {{ businessLoading ? '搜索中...' : '输入关键词或ID搜索' }}
              </div>
            </template>
          </el-select>
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="docForm.tags" placeholder="多个标签用逗号分隔" />
        </el-form-item>
        <el-form-item label="摘要">
          <el-input v-model="docForm.summary" type="textarea" :rows="2" placeholder="文档摘要，AI 会自动生成" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmitDoc" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>

    <!-- 上传对话框 -->
    <el-dialog v-model="uploadVisible" title="批量文件导入" width="500px" :close-on-click-modal="false" :close-on-press-escape="false">
      <div class="upload-tip">
        💡 上传的文档将自动解析并生成向量索引，供智能体使用
      </div>
      <el-form :model="uploadForm" label-width="100px">
        <el-form-item label="文档类型">
          <el-select v-model="uploadForm.doc_type" style="width:100%">
            <el-option v-for="dt in docTypes" :key="dt.value" :label="dt.label" :value="dt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联客户">
          <el-select
            v-model="uploadForm.cust_id"
            filterable
            remote
            clearable
            reserve-keyword
            placeholder="输入客户名称或ID搜索"
            :remote-method="searchCustomers"
            :loading="customerLoading"
            style="width:100%"
          >
            <el-option
              v-for="c in customerOptions"
              :key="c.id"
              :label="`[${c.id}] ${c.company || c.name || ''}`"
              :value="c.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="uploadForm.tags" placeholder="多个标签用逗号分隔" />
        </el-form-item>
        <el-form-item label="文件">
          <el-upload
            drag multiple :auto-upload="false"
            :on-change="handleFileChange"
            :file-list="uploadFiles"
            accept=".txt,.pdf,.doc,.docx,.xls,.xlsx,.md,.csv"
          >
            <div class="upload-icon">📁</div>
            <div class="el-upload__text">拖拽文件到此处，或<em>点击选择文件</em></div>
            <div class="el-upload__tip">支持 TXT/PDF/Word/Excel/Markdown，上传后自动索引</div>
          </el-upload>
        </el-form-item>
      </el-form>
      <!-- 进度条 -->
      <div v-if="uploadProgress >= 0" class="upload-progress">
        <el-progress :percentage="uploadProgress" :stroke-width="20" />
        <p class="progress-text">正在上传并处理... {{ uploadProgress }}%</p>
      </div>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" @click="handleUpload" :loading="uploading">开始上传</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import KnowledgeGraph from '../components/KnowledgeGraph.vue'

// ========== 基础状态 ==========
const activeTab = ref('documents')
const stats = ref(null)

// 知识图谱组件引用
const knowledgeGraphRef = ref(null)

// 监听Tab切换，激活知识图谱时触发图表重新渲染
watch(activeTab, async (newVal) => {
  if (newVal === 'graph' && knowledgeGraphRef.value?.refreshChart) {
    await nextTick()
    knowledgeGraphRef.value.refreshChart()
  }
})

// ========== Tab 1: 知识文档 ==========
const docTypes = [
  { value: 'visit_summary', label: '拜访纪要' },
  { value: 'contract', label: '合同' },
  { value: 'bid_document', label: '投标文件' },
  { value: 'technical_plan', label: '技术方案' },
  { value: 'customer_info', label: '客户资料' },
  { value: 'industry_report', label: '行业报告' },
  { value: 'meeting_minutes', label: '会议纪要' },
  { value: 'other', label: '其他' }
]

const docLoading = ref(false)
const docList = ref([])
const docTotal = ref(0)
const docPage = ref(1)
const keyword = ref('')
const filterDocType = ref('')
const currentDoc = ref(null)
const detailVisible = ref(false)
const createVisible = ref(false)
const editingDoc = ref(null)
const submitting = ref(false)
const analyzing = ref(false)
const batchAnalyzing = ref(false)
const docForm = reactive({
  doc_type: 'visit_summary', title: '', content: '',
  cust_id: '', business_id: '', tags: '', summary: ''
})

const uploadVisible = ref(false)
const uploading = ref(false)
const uploadProgress = ref(-1)
const uploadFiles = ref([])
const uploadForm = reactive({ doc_type: 'visit_summary', cust_id: '', tags: '' })
const syncing = ref(false)
const rebuilding = ref(false)

// ========== 客户/商机搜索 ==========
const customerOptions = ref([])
const customerLoading = ref(false)
const businessOptions = ref([])
const businessLoading = ref(false)
const initialCustomerLoaded = ref(false)
const initialBusinessLoaded = ref(false)

async function searchCustomers(query) {
  if (!query && initialCustomerLoaded.value) return
  customerLoading.value = true
  try {
    const params = { per_page: 30 }
    if (query) params.keyword = query
    const res = await api.get('/customers', params)
    if (res.code === 200) {
      let list = res.data || []
      // 如果用户输入纯数字ID且没找到，尝试直接按ID查
      if (query && /^\d+$/.test(query) && !list.find(c => String(c.id) === query)) {
        try {
          const detail = await api.get(`/customers/${query}`)
          if (detail.code === 200 && detail.data) {
            list = [detail.data, ...list]
          }
        } catch { /* ignore */ }
      }
      customerOptions.value = list
      if (!query) initialCustomerLoaded.value = true
    }
  } catch { /* ignore */ }
  customerLoading.value = false
}

async function searchBusinessList(query) {
  if (!query && initialBusinessLoaded.value) return
  businessLoading.value = true
  try {
    const params = { per_page: 30, status: 'all' }
    if (query) params.keyword = query
    const res = await api.get('/business', params)
    if (res.code === 200) {
      let list = res.data || []
      // 如果用户输入纯数字ID且没找到，尝试直接按ID查
      if (query && /^\d+$/.test(query) && !list.find(b => String(b.id) === query)) {
        try {
          const detail = await api.get(`/business/${query}`)
          if (detail.code === 200 && detail.data) {
            list = [detail.data, ...list]
          }
        } catch { /* ignore */ }
      }
      businessOptions.value = list
      if (!query) initialBusinessLoaded.value = true
    }
  } catch { /* ignore */ }
  businessLoading.value = false
}

async function handleAnalyzeDoc() {
  if (!currentDoc.value) return
  analyzing.value = true
  try {
    // AI分析可能涉及LLM调用（LLM超时2分钟+降级规则模式），需要较长超时
    const resp = await api.post(`/knowledge/documents/${currentDoc.value.id}/analyze`, {}, { timeout: 180000 })
    if (resp.code === 200) {
      ElMessage.success('✨ AI分析完成')
      currentDoc.value.analysis = resp.data
      currentDoc.value.analysis_status = 'completed'
      if (resp.data.summary && !currentDoc.value.summary) {
        currentDoc.value.summary = resp.data.summary
      }
      if (resp.data.tags?.length && !currentDoc.value.tags) {
        currentDoc.value.tags = resp.data.tags.join(',')
      }
      // 更新列表中对应记录
      const idx = docList.value.findIndex(d => d.id === currentDoc.value.id)
      if (idx >= 0) {
        docList.value[idx].analysis_status = 'completed'
        docList.value[idx].analysis_summary = resp.data.summary?.substring(0, 100) || ''
      }
    } else {
      ElMessage.error(resp.message || '分析失败')
    }
  } catch (e) {
    ElMessage.error('AI分析请求失败，请检查网络或稍后重试')
  } finally {
    analyzing.value = false
  }
}

async function handleBatchAnalyze() {
  batchAnalyzing.value = true
  try {
    // 批量分析耗时较长，设置5分钟超时
    const resp = await api.post('/knowledge/documents/batch-analyze', {}, { timeout: 300000 })
    if (resp.code === 200) {
      ElMessage.success(resp.message)
      fetchDocuments()
      fetchInsights()
    } else {
      ElMessage.error(resp.message || '批量分析失败')
    }
  } catch (e) {
    ElMessage.error('批量分析请求失败')
  } finally {
    batchAnalyzing.value = false
  }
}

function getDocIcon(type) {
  const icons = {
    visit_summary: '📅', contract: '📜', bid_document: '📋',
    technical_plan: '🔧', customer_info: '🏢', industry_report: '📊',
    meeting_minutes: '💬', other: '📄'
  }
  return icons[type] || '📄'
}

function getDocTagType(type) {
  const types = {
    visit_summary: '', contract: 'success', bid_document: 'warning',
    technical_plan: 'info', customer_info: 'danger', industry_report: 'success',
    meeting_minutes: 'warning', other: 'info'
  }
  return types[type] || ''
}

function formatDate(str) {
  if (!str) return '-'
  return str.replace('T', ' ').substring(0, 16)
}

async function fetchDocuments() {
  docLoading.value = true
  try {
    const params = { page: docPage.value, per_page: 20, keyword: keyword.value, doc_type: filterDocType.value }
    const res = await api.get('/knowledge/documents', params)
    if (res.code === 200) {
      docList.value = res.data.items
      docTotal.value = res.data.total
    }
  } catch (e) { ElMessage.error('获取文档列表失败') }
  finally { docLoading.value = false }
}

async function fetchStats() {
  try {
    const res = await api.get('/knowledge/stats')
    if (res.code === 200) stats.value = res.data
  } catch (e) { /* ignore */ }
}

async function openDocDetail(row) {
  detailVisible.value = true
  currentDoc.value = { ...row }
  // 加载完整详情（包含完整analysis数据）
  try {
    const resp = await api.get(`/knowledge/documents/${row.id}`)
    if (resp.code === 200) {
      currentDoc.value = resp.data
    }
  } catch { /* 保持列表数据 */ }
}

function showCreateDialog() {
  editingDoc.value = null
  Object.assign(docForm, { doc_type: 'visit_summary', title: '', content: '', cust_id: '', business_id: '', tags: '', summary: '' })
  createVisible.value = true
}

function showEditDialog(row) {
  editingDoc.value = row
  Object.assign(docForm, {
    doc_type: row.doc_type, title: row.title,
    content: row.content || '', cust_id: row.cust_id || '',
    business_id: row.business_id || '', tags: row.tags || '', summary: row.summary || ''
  })
  // 预加载当前选项，使select能回显已选值
  if (row.cust_id) searchCustomers(String(row.cust_id))
  if (row.business_id) searchBusinessList(String(row.business_id))
  createVisible.value = true
}

async function handleSubmitDoc() {
  if (!docForm.title) { ElMessage.warning('请输入标题'); return }
  submitting.value = true
  try {
    const payload = { ...docForm }
    if (payload.cust_id !== '' && payload.cust_id !== null && payload.cust_id !== undefined) payload.cust_id = Number(payload.cust_id)
    else delete payload.cust_id
    if (payload.business_id !== '' && payload.business_id !== null && payload.business_id !== undefined) payload.business_id = Number(payload.business_id)
    else delete payload.business_id
    const url = editingDoc.value ? `/knowledge/documents/${editingDoc.value.id}` : '/knowledge/documents'
    const fn = editingDoc.value ? api.put : api.post
    const res = await fn(url, payload)
    if (res.code === 200) {
      ElMessage.success(editingDoc.value ? '更新成功' : '创建成功')
      createVisible.value = false
      fetchDocuments(); fetchStats()
    } else ElMessage.error(res.message)
  } catch (e) { ElMessage.error('操作失败') }
  finally { submitting.value = false }
}

async function handleDeleteDoc(row) {
  try {
    await ElMessageBox.confirm(`确认删除「${row.title}」？`, '提示', { type: 'warning' })
    const res = await api.delete(`/knowledge/documents/${row.id}`)
    if (res.code === 200) { ElMessage.success('删除成功'); fetchDocuments(); fetchStats() }
    else ElMessage.error(res.message)
  } catch (e) { /* cancelled */ }
}

function showUploadDialog() {
  uploadFiles.value = []
  uploadProgress.value = -1
  Object.assign(uploadForm, { doc_type: 'visit_summary', cust_id: '', tags: '' })
  uploadVisible.value = true
}

function handleFileChange(file, fileList) { uploadFiles.value = fileList }

function handleUpload() {
  if (!uploadFiles.value.length) { ElMessage.warning('请选择文件'); return }
  uploading.value = true
  uploadProgress.value = 0

  const formData = new FormData()
  for (const f of uploadFiles.value) formData.append('files', f.raw)
  formData.append('doc_type', uploadForm.doc_type)
  if (uploadForm.cust_id) formData.append('cust_id', String(uploadForm.cust_id))
  if (uploadForm.tags) formData.append('tags', uploadForm.tags)

  const token = localStorage.getItem('crm_token')
  const xhr = new XMLHttpRequest()

  xhr.upload.addEventListener('progress', (e) => {
    if (e.lengthComputable) {
      const percent = Math.round((e.loaded / e.total) * 95)
      uploadProgress.value = percent
    }
  })

  xhr.addEventListener('load', () => {
    uploading.value = false
    if (xhr.status >= 200 && xhr.status < 300) {
      uploadProgress.value = 100
      try {
        const res = JSON.parse(xhr.responseText)
        if (res.code === 200) {
          ElMessage.success(res.message || '上传成功')
          setTimeout(() => { uploadVisible.value = false; uploadProgress.value = -1 }, 500)
          fetchDocuments()
          fetchStats()
        } else {
          ElMessage.error(res.message || '上传失败')
          uploadProgress.value = -1
        }
      } catch {
        ElMessage.error('服务器响应格式错误')
        uploadProgress.value = -1
      }
    } else {
      ElMessage.error(`上传失败：HTTP ${xhr.status}`)
      uploadProgress.value = -1
    }
  })

  xhr.addEventListener('error', () => {
    uploading.value = false
    uploadProgress.value = -1
    ElMessage.error('网络错误，请检查后端服务是否启动')
  })

  xhr.addEventListener('timeout', () => {
    uploading.value = false
    uploadProgress.value = -1
    ElMessage.error('上传超时，文件可能过大，请重试')
  })

  xhr.addEventListener('abort', () => {
    uploading.value = false
    uploadProgress.value = -1
  })

  xhr.open('POST', '/api/knowledge/documents/upload')
  xhr.setRequestHeader('Authorization', `Bearer ${token}`)
  xhr.timeout = 300000 // 5分钟超时
  xhr.send(formData)
}

async function handleSync() {
  syncing.value = true
  try {
    const res = await api.post('/knowledge/sync', { modules: ['customers', 'business', 'contracts', 'visits'] })
    if (res.code === 200) { ElMessage.success('CRM数据同步完成'); fetchDocuments(); fetchStats() }
    else ElMessage.error(res.message)
  } catch (e) { ElMessage.error('同步失败') }
  finally { syncing.value = false }
}

async function handleRebuild() {
  try {
    await ElMessageBox.confirm('重建向量索引会重新处理所有文档，是否继续？', '提示', { type: 'warning' })
    rebuilding.value = true
    const res = await api.post('/knowledge/rebuild-vectors')
    if (res.code === 200) { ElMessage.success('索引重建完成'); fetchStats() }
    else ElMessage.error(res.message)
  } catch (e) { /* cancelled */ }
  finally { rebuilding.value = false }
}

// ========== Tab 2: AI 洞察 ==========
const insightCategories = [
  { value: 'visit_summary', label: '拜访复盘' },
  { value: 'followup_insight', label: '跟进洞察' },
  { value: 'sales_skill', label: '销售技巧' },
  { value: 'customer_case', label: '客户案例' }
]
const insightCategoryLabel = (v) => insightCategories.find(c => c.value === v)?.label || v

const insightLoading = ref(false)
const insightList = ref([])
const insightTotal = ref(0)
const insightKeyword = ref('')
const filterCategory = ref('')
const currentInsight = ref(null)

const insightParsedContent = computed(() => {
  if (!currentInsight.value?.content) return null
  try { return JSON.parse(currentInsight.value.content) } catch (e) { return currentInsight.value.content }
})

async function fetchInsights() {
  insightLoading.value = true
  try {
    const params = {}
    if (filterCategory.value) params.category = filterCategory.value
    if (insightKeyword.value) params.keyword = insightKeyword.value

    // 1. 拉取 AI 生成的洞察（knowledge_base 表）
    const requests = [api.get('/knowledge/entries', params)]

    // 2. 拜访复盘分类或无分类时，同时拉取上传的拜访纪要文档
    const fetchVisitDocs = !filterCategory.value || filterCategory.value === 'visit_summary'
    if (fetchVisitDocs) {
      const docParams = { doc_type: 'visit_summary', per_page: 50 }
      if (insightKeyword.value) docParams.keyword = insightKeyword.value
      requests.push(api.get('/knowledge/documents', docParams))
    }

    const [resp, docResp] = await Promise.all(requests)

    let insights = []
    if (resp.code === 200) {
      insights = (resp.data.items || resp.data || []).map(item => ({ ...item, _source: 'insight' }))
    }

    // 合并上传的拜访纪要文档
    if (docResp && docResp.code === 200) {
      const docs = (docResp.data.items || []).map(item => ({
        ...item,
        category: 'visit_summary',
        _source: 'document',
        content: item.content || item.summary || ''
      }))
      insights = insights.concat(docs)
    }

    // 按创建时间倒序合并
    insights.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))

    insightList.value = insights
    insightTotal.value = insights.length
  } catch (e) { ElMessage.error('获取洞察失败') }
  finally { insightLoading.value = false }
}

async function openInsightDetail(item) {
  try {
    let data = item
    if (item._source === 'document') {
      // 上传文档：调用文档详情接口（包含analysis字段）
      const resp = await api.get(`/knowledge/documents/${item.id}`)
      if (resp.code === 200) {
        data = { ...resp.data, category: 'visit_summary', _source: 'document' }
      }
    } else {
      const resp = await api.get(`/knowledge/entries/${item.id}`)
      if (resp.code === 200) data = resp.data
    }
    currentInsight.value = data
    detailVisible.value = true
  } catch (e) { ElMessage.error('加载详情失败') }
}

function editInsight(item) {
  if (item._source === 'document') {
    // 上传的拜访纪要文档：走文档编辑流程
    api.get(`/knowledge/documents/${item.id}`).then(resp => {
      if (resp.code === 200) {
        showEditDialog(resp.data)
      }
    })
    return
  }
  api.get(`/knowledge/entries/${item.id}`).then(resp => {
    if (resp.code === 200) {
      const d = resp.data
      docForm.id = d.id
      docForm.title = d.title
      docForm.content = d.content
      docForm.doc_type = d.category || 'other'
      docForm.summary = d.summary || ''
      docForm.tags = d.tags || ''
      showEditDialog({ ...d, doc_type: d.category || 'other' })
    }
  })
}

async function deleteInsight(item) {
  try {
    await ElMessageBox.confirm(`确定删除「${item.title}」？`, '提示', { type: 'warning' })
    const url = item._source === 'document'
      ? `/knowledge/documents/${item.id}`
      : `/knowledge/entries/${item.id}`
    const resp = await api.delete(url)
    if (resp.code === 200) { ElMessage.success('删除成功'); fetchInsights() }
    else ElMessage.error(resp.message)
  } catch (e) { /* cancelled */ }
}

// ========== Tab 3: 语义搜索 ==========
const searchForm = reactive({ query: '', search_type: 'hybrid' })
const searchResults = ref([])
const searching = ref(false)
const searched = ref(false)

async function doSemanticSearch() {
  if (!searchForm.query) { ElMessage.warning('请输入搜索词'); return }
  searching.value = true; searched.value = true
  try {
    const res = await api.post('/knowledge/documents/search', {
      query: searchForm.query, search_type: searchForm.search_type, top_k: 15
    })
    if (res.code === 200) {
      searchResults.value = res.data.results
      ElMessage.success(`找到 ${res.data.total} 条结果`)
    }
  } catch (e) { ElMessage.error('搜索失败') }
  finally { searching.value = false }
}

onMounted(() => {
  fetchDocuments()
  fetchStats()
  fetchInsights()
})
</script>

<style scoped>
.knowledge-container { padding: 0; }

.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.page-title { font-size: 22px; font-weight: 600; color: #1e293b; margin: 0; }
.page-desc { font-size: 13px; color: #64748b; margin: 6px 0 0; }

.stats-bar { display: flex; gap: 16px; }
.stat-card { flex: 1; background: linear-gradient(135deg, #f6f9fc 0%, #eef4f8 100%); border-radius: 10px; padding: 14px; display: flex; align-items: center; gap: 14px; }
.stat-icon { font-size: 28px; }
.stat-value { font-size: 22px; font-weight: 700; color: #2d3748; }
.stat-label { font-size: 13px; color: #718096; }

.kb-tabs { border-radius: 10px; }
.tab-desc { color: #64748b; font-size: 13px; margin-bottom: 14px; padding: 8px 12px; background: #f0f4ff; border-radius: 6px; }

.filter-bar { display: flex; gap: 12px; align-items: center; margin-bottom: 14px; }
.stat-info { margin-left: auto; font-size: 13px; color: #94a3b8; }

.doc-title-cell { display: flex; align-items: center; gap: 8px; }
.analysis-cell { font-size: 12px; color: #64748b; margin-top: 4px; line-height: 1.4; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.empty-cell { color: #cbd5e0; }
.pagination-bar { display: flex; justify-content: flex-end; margin-top: 14px; }

.knowledge-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
.empty-state { grid-column: 1 / -1; text-align: center; padding: 60px 20px; color: #94a3b8; }
.empty-icon { font-size: 48px; margin-bottom: 12px; }
.empty-text { font-size: 16px; color: #64748b; margin-bottom: 6px; }
.empty-desc { font-size: 13px; }

.knowledge-card { background: white; border-radius: 12px; padding: 16px; cursor: pointer; border: 1px solid #e2e8f0; transition: all 0.25s ease; display: flex; flex-direction: column; gap: 10px; }
.knowledge-card:hover { box-shadow: 0 8px 24px rgba(0,0,0,0.08); transform: translateY(-2px); border-color: #c7d2fe; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.card-date { font-size: 12px; color: #94a3b8; }
.card-title { font-size: 15px; font-weight: 600; color: #1e293b; line-height: 1.4; }
.card-summary { font-size: 13px; color: #64748b; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.card-footer { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding-top: 6px; border-top: 1px dashed #e2e8f0; }
.card-meta { font-size: 12px; color: #94a3b8; }
.card-actions { margin-left: auto; }

.category-badge { font-size: 11px; padding: 3px 10px; border-radius: 10px; font-weight: 500; }
.cat-visit_summary { background: #dbeafe; color: #2563eb; }
.cat-followup_insight { background: #fef3c7; color: #d97706; }
.cat-sales_skill { background: #d1fae5; color: #059669; }
.cat-customer_case { background: #ede9fe; color: #7c3aed; }

.search-panel { padding: 20px; background: #f8fafc; border-radius: 10px; margin-bottom: 16px; }
.search-results { display: flex; flex-direction: column; gap: 12px; }
.search-result-item { padding: 14px; background: white; border: 1px solid #e2e8f0; border-radius: 10px; }
.result-header { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.result-title { font-weight: 600; color: #1e293b; }
.similarity { margin-left: auto; font-size: 13px; color: #4ecdc4; font-weight: 600; }
.result-content { color: #64748b; font-size: 13px; line-height: 1.5; margin-bottom: 8px; }
.result-meta { display: flex; gap: 6px; flex-wrap: wrap; }
.meta-tag { margin-right: 4px; }

.detail-content { padding: 0 10px; max-height: 70vh; overflow-y: auto; }
.detail-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.detail-time { color: #a0aec0; font-size: 13px; }
.detail-title { font-size: 18px; font-weight: 600; color: #1e293b; margin: 0 0 10px 0; }
.detail-meta { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
.detail-summary { background: #ebf8ff; padding: 10px 14px; border-radius: 8px; margin-bottom: 12px; }
.section-label { font-weight: 600; margin-bottom: 6px; color: #4a5568; }
.content-box { background: #f7fafc; padding: 14px; border-radius: 8px; white-space: pre-wrap; word-break: break-word; max-height: 400px; overflow-y: auto; }
.detail-footer { display: flex; gap: 16px; color: #a0aec0; font-size: 13px; margin-top: 12px; padding-top: 10px; border-top: 1px solid #edf2f7; }
.detail-section { margin-bottom: 12px; }
.detail-section ul { margin: 0; padding-left: 20px; }
.detail-section li { margin-bottom: 4px; }

.upload-tip { background: #f0fff4; padding: 10px 14px; border-radius: 8px; color: #22543d; font-size: 13px; margin-bottom: 14px; }
.upload-icon { font-size: 36px; margin-bottom: 8px; }
.upload-progress { margin: 16px 0; padding: 14px; background: #f7fafc; border-radius: 8px; }
.progress-text { text-align: center; margin: 8px 0 0; font-size: 14px; color: #4a5568; }

/* AI 分析样式 */
.analysis-box {
  background: linear-gradient(135deg, #f0f4ff 0%, #e8f4ff 100%);
  border: 1px solid #c3dafe;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 14px;
}
.analysis-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px dashed #c3dafe;
}
.analysis-title { font-size: 16px; font-weight: 600; color: #2d3748; }
.analysis-meta { display: flex; gap: 8px; align-items: center; }
.analyzed-at { font-size: 12px; color: #718096; }
.analysis-section { margin-bottom: 12px; }
.analysis-label { font-size: 13px; color: #4a5568; margin-bottom: 4px; font-weight: 500; }
.analysis-text {
  background: #fff;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.7;
  color: #2d3748;
  border-left: 3px solid #4299e1;
}
.analysis-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}
.analysis-card {
  background: #fff;
  border-radius: 8px;
  padding: 12px 14px;
  border-left: 3px solid #4299e1;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
.analysis-card.findings { border-left-color: #4299e1; }
.analysis-card.needs { border-left-color: #9f7aea; }
.analysis-card.actions { border-left-color: #48bb78; }
.analysis-card.risks { border-left-color: #f56565; }
.analysis-card.opportunities { border-left-color: #ed8936; }
.analysis-card-title { font-size: 13px; font-weight: 600; color: #2d3748; margin-bottom: 8px; }
.analysis-card ul { margin: 0; padding-left: 18px; }
.analysis-card li { font-size: 13px; color: #4a5568; line-height: 1.6; margin-bottom: 3px; }
.analysis-tags { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }
.analysis-tag { background: #e6f4ff; color: #2b6cb0; border: none; }
.analysis-sentiment { display: flex; align-items: center; gap: 8px; font-size: 13px; }
</style>