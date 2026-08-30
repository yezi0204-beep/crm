<template>
  <div class="contracts">
    <div class="header-row">
      <div class="header-left">
        <el-button type="primary" @click="addContract" class="add-btn">
          <el-icon><Plus /></el-icon>
          新建合同
        </el-button>
        
        <el-button @click="showImportModal = true" class="import-btn">
          <el-icon><Upload /></el-icon>
          导入合同
        </el-button>
        
        <el-button @click="exportContracts" class="export-btn">
          <el-icon><Download /></el-icon>
          导出合同
        </el-button>
      </div>
      
      <div class="header-right">
        <div class="search-wrapper">
          <el-input 
            v-model="searchKeyword" 
            placeholder="搜索合同名称、编号、项目令号、甲方..." 
            class="search-input"
            clearable
            @keyup.enter="handleSearch"
          />
          <el-button @click="handleSearch" class="search-btn">搜索</el-button>
        </div>
        
        <el-popover 
          v-model:visible="showColumnSelector" 
          placement="bottom-end" 
          trigger="click"
          width="200"
        >
          <template #reference>
            <el-button>
              ⚙️ 选择显示列
              <el-icon><ArrowDown /></el-icon>
            </el-button>
          </template>
        <div class="column-selector-content">
          <div v-for="col in allColumns" :key="col.prop" class="column-item">
            <el-checkbox 
              :model-value="visibleColumns.includes(col.prop)" 
              @change="(val) => toggleColumn(col.prop, val)"
            />
            {{ col.label }}
          </div>
          <div class="column-selector-footer">
            <el-button size="small" @click="showColumnSelector = false">确定</el-button>
          </div>
        </div>
      </el-popover>
      </div>
    </div>
    
    <div class="table-container">
      <div class="table-wrapper">
        <el-table :data="filteredContracts" stripe border class="data-table" @sort-change="handleSortChange" max-height="70vh">
          <template v-for="col in visibleColumnConfigs" :key="col.prop">
            <el-table-column 
              v-if="col.prop === 'total_amt'" 
              :prop="col.prop" 
              :label="col.label" 
              :min-width="col.width || 110" 
              align="right"
              sortable="custom"
              :sort-order="sortField === 'total_amt' ? sortOrder : undefined"
            >
              <template #default="scope">
                {{ formatAmount(scope.row.total_amt) }}
              </template>
            </el-table-column>
            
            <el-table-column 
              v-else-if="col.prop === 'paid_amt'" 
              :prop="col.prop" 
              :label="col.label" 
              :min-width="col.width || 110" 
              align="right"
              sortable="custom"
              :sort-order="sortField === 'paid_amt' ? sortOrder : undefined"
            >
              <template #default="scope">
                {{ formatAmount(scope.row.paid_amt) }}
              </template>
            </el-table-column>
            
            <el-table-column
              v-else-if="col.prop === 'pending_amt'"
              :prop="col.prop"
              :label="col.label"
              :min-width="col.width || 110"
              align="right"
              sortable="custom"
              :sort-order="sortField === 'pending_amt' ? sortOrder : undefined"
            >
              <template #default="scope">
                <span :class="{ 'pending-highlight': getPendingAmt(scope.row) > 0.01 }">
                  {{ formatAmount(getPendingAmt(scope.row)) }}
                </span>
              </template>
            </el-table-column>

            <el-table-column
              v-else-if="col.prop === 'income' || col.prop === 'pending_acceptance_amount'"
              :prop="col.prop"
              :label="col.label"
              :min-width="col.width || 110"
              align="right"
              sortable="custom"
            >
              <template #default="scope">
                {{ formatYuan(scope.row[col.prop]) }}
              </template>
            </el-table-column>

            <el-table-column
              v-else-if="col.prop === 'tax_amount'"
              :prop="col.prop"
              :label="col.label"
              :min-width="col.width || 110"
              align="right"
              sortable="custom"
            >
              <template #default="scope">
                {{ formatAmount(scope.row[col.prop]) }}
              </template>
            </el-table-column>
            
            <el-table-column 
              v-else-if="col.prop === 'status'" 
              :prop="col.prop" 
              :label="col.label" 
              :min-width="col.width || 80" 
              align="center"
              sortable
            >
              <template #default="scope">
                <el-tag :type="getStatusType(scope.row.status)" size="small">{{ scope.row.status }}</el-tag>
              </template>
            </el-table-column>
            
            <el-table-column 
              v-else-if="col.prop === 'acceptance_nodes' || col.prop === 'payment_nodes'" 
              :prop="col.prop" 
              :label="col.label" 
              :min-width="col.width || 120" 
              show-overflow-tooltip
            />
            
            <el-table-column 
              v-else-if="col.prop === 'owner_name'" 
              :prop="col.prop" 
              :label="col.label" 
              :min-width="col.width || 90"
            >
              <template #default="scope">
                <template v-if="isAdminRole">
                  <el-select 
                    v-if="editingOwnerId === scope.row.id" 
                    :value="scope.row.owner_id" 
                    @change="(val) => saveOwnerChange(scope.row.id, val)"
                    @visible-change="(visible) => { if (!visible) setTimeout(() => { if (!savingOwnerId) editingOwnerId = null }, 200) }"
                    style="width: 120px;"
                    filterable
                  >
                    <el-option 
                      v-for="user in users" 
                      :key="user.username" 
                      :label="user.name" 
                      :value="user.username" 
                    />
                  </el-select>
                  <span 
                    v-else 
                    @click="startEditOwner(scope.row)"
                    style="cursor: pointer; color: #4ecdc4;"
                  >
                    {{ scope.row.owner_name || '未分配' }}
                  </span>
                </template>
                <span v-else>{{ scope.row.owner_name || '未分配' }}</span>
              </template>
            </el-table-column>
            
            <el-table-column 
              v-else 
              :prop="col.prop" 
              :label="col.label" 
              :min-width="col.minWidth || (col.width || 100)" 
              :sortable="col.sortable !== false"
              show-overflow-tooltip
            />
          </template>
          
          <el-table-column label="操作" width="190" fixed="right">
            <template #default="scope">
              <el-button v-if="isAdmin" link type="primary" size="small" @click="editContract(scope.row)">编辑</el-button>
              <el-button v-if="isAdmin" link type="danger" size="small" @click="deleteContract(scope.row)">删除</el-button>
              <el-button v-if="isAdmin" link type="warning" size="small" @click="openCommission(scope.row)">分成</el-button>
              <el-button v-if="scope.row.is_framework" link type="success" size="small" @click="openAcceptance(scope.row)">验收</el-button>
              <el-button link type="info" size="small" @click="previewFiles(scope.row)">预览</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
    
    <el-dialog v-model="showAddModal" :title="contractForm.id ? '编辑合同' : '新建合同'" width="700px" :close-on-click-modal="false" :close-on-press-escape="false">
      <el-form :model="contractForm" :rules="rules" ref="formRef">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="合同名称" prop="contract_name">
              <el-input v-model="contractForm.contract_name" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="合同编号" prop="contract_no">
              <el-input v-model="contractForm.contract_no" @blur="validateContractNo" />
              <span v-if="!contractForm.id" style="font-size: 12px; color: #999;">请输入合同编号，系统将检查是否重复</span>
            </el-form-item>
          </el-col>
        </el-row>
        
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="甲方">
              <el-input v-model="contractForm.party_a" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="项目令号">
              <el-input v-model="contractForm.project_order_no" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="关联客户" prop="cust_id">
              <el-select
                v-model="contractForm.cust_id"
                placeholder="请选择客户（必填）"
                filterable
                clearable
                style="width: 100%;"
                @change="onCustomerChange"
              >
                <el-option
                  v-for="c in customers"
                  :key="c.id"
                  :label="c.company ? `${c.company}（${c.name || ''}）` : c.name"
                  :value="c.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="关联商机">
              <el-select
                v-model="contractForm.b_id"
                :placeholder="contractForm.cust_id ? '可选，选择该客户的商机' : '请先选择关联客户'"
                filterable
                clearable
                :disabled="!contractForm.cust_id"
                style="width: 100%;"
              >
                <el-option
                  v-for="b in filteredBusiness"
                  :key="b.id"
                  :label="b.title + (b.status === 'void' ? '（已作废）' : '')"
                  :value="b.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="合同总额(万)" prop="total_amt">
              <el-input-number v-model="contractForm.total_amt" :min="0" :step="0.01" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="签约日期">
              <el-date-picker v-model="contractForm.sign_date" type="date" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="8">
            <el-form-item label="收入(元)">
              <el-input-number v-model="contractForm.income" :min="0" :step="0.01" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="税额(万)">
              <el-input-number v-model="contractForm.tax_amount" :min="0" :step="0.01" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="待验收合同额(元)">
              <el-input-number v-model="contractForm.pending_acceptance_amount" :min="0" :step="0.01" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="业态">
              <el-select v-model="contractForm.business_type">
                <el-option label="J" value="J" />
                <el-option label="M" value="M" />
                <el-option label="K" value="K" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="业务方向">
              <el-input v-model="contractForm.business_direction" placeholder="如：智能制造、智慧城市..." />
            </el-form-item>
          </el-col>
        </el-row>
        
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="项目密级">
              <el-select v-model="contractForm.classification">
                <el-option label="绝密" value="绝密" />
                <el-option label="机密" value="机密" />
                <el-option label="秘密" value="秘密" />
                <el-option label="内部" value="内部" />
                <el-option label="公开" value="公开" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="合同状态">
              <el-select v-model="contractForm.status">
                <el-option label="执行中" value="执行中" />
                <el-option label="已完成" value="已完成" />
                <el-option label="已终止" value="已终止" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="负责人">
          <el-select v-model="contractForm.owner_id">
            <el-option v-for="user in users" :key="user.username" :label="user.name" :value="user.username" />
          </el-select>
        </el-form-item>

        <el-form-item label="框架合同">
          <el-switch v-model="contractForm.is_framework" :active-value="1" :inactive-value="0" />
          <span style="color: #909399; font-size: 12px; margin-left: 12px;">
            框架合同按每月验收实际金额计入考核，非框架合同按合同总额一次性计入
          </span>
        </el-form-item>

        <el-form-item label="合同约定验收节点">
          <el-input v-model="contractForm.acceptance_nodes" type="textarea" :rows="3" />
        </el-form-item>
        
        <el-form-item label="合同约定回款节点">
          <el-input v-model="contractForm.payment_nodes" type="textarea" :rows="3" />
        </el-form-item>
        
        <el-form-item label="备注">
          <el-input v-model="contractForm.note" type="textarea" :rows="3" placeholder="输入合同备注信息" />
        </el-form-item>
        
        <el-divider content-position="left">📎 文件上传</el-divider>
        
        <el-form-item label="合同文本">
          <el-upload
            :action="uploadUrl"
            :headers="uploadHeaders"
            :data="{ contract_id: contractForm.id || 0, file_type: 'contract' }"
            :on-success="handleUploadSuccess"
            :on-error="handleUploadError"
            :file-list="contractFileList"
            accept=".pdf,.docx,.txt,.md"
          >
            <el-button type="primary">点击上传</el-button>
          </el-upload>
        </el-form-item>
        
        <el-form-item label="技术协议文本">
          <el-upload
            :action="uploadUrl"
            :headers="uploadHeaders"
            :data="{ contract_id: contractForm.id || 0, file_type: 'tech' }"
            :on-success="handleUploadSuccess"
            :on-error="handleUploadError"
            :file-list="techFileList"
            accept=".pdf,.docx,.txt,.md"
          >
            <el-button type="primary">点击上传</el-button>
          </el-upload>
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="showAddModal = false">取消</el-button>
        <el-button type="primary" @click="saveContract">确定</el-button>
      </template>
    </el-dialog>
    
    <el-dialog v-model="showPreviewModal" title="文件预览" width="900px" height="70vh" :close-on-click-modal="false" :close-on-press-escape="false">
      <div v-if="previewContractFile" class="preview-section">
        <h4>📄 合同文本</h4>
        <div class="file-info">
          <a :href="previewContractFile" target="_blank" class="file-link">{{ previewContractFileName }}</a>
          <el-button size="small" @click="downloadFile(previewContractFile, previewContractFileName)" class="download-btn">下载</el-button>
        </div>
        <div v-if="isLoadingContract" class="loading-preview">
          <el-spin tip="加载中..." />
        </div>
        <div v-else-if="isPdfFile(previewContractFileName) && contractBlobUrl" class="pdf-preview">
          <embed :src="contractBlobUrl" type="application/pdf" class="pdf-frame" />
        </div>
        <div v-else class="text-preview">
          <pre>{{ previewTextContent || '暂无预览内容' }}</pre>
        </div>
      </div>
      <div v-else class="no-file">暂无合同文本文件</div>
      
      <el-divider />
      
      <div v-if="previewTechFile" class="preview-section">
        <h4>📋 技术协议文本</h4>
        <div class="file-info">
          <a :href="previewTechFile" target="_blank" class="file-link">{{ previewTechFileName }}</a>
          <el-button size="small" @click="downloadFile(previewTechFile, previewTechFileName)" class="download-btn">下载</el-button>
        </div>
        <div v-if="isLoadingTech" class="loading-preview">
          <el-spin tip="加载中..." />
        </div>
        <div v-else-if="isPdfFile(previewTechFileName) && techBlobUrl" class="pdf-preview">
          <embed :src="techBlobUrl" type="application/pdf" class="pdf-frame" />
        </div>
        <div v-else class="text-preview">
          <pre>{{ previewTechTextContent || '暂无预览内容' }}</pre>
        </div>
      </div>
      <div v-else class="no-file">暂无技术协议文件</div>
    </el-dialog>
    
    <el-dialog v-model="showImportModal" title="导入合同" width="900px" :close-on-click-modal="false" :close-on-press-escape="false">
      <div v-if="importStep === 1" class="import-step-1">
        <el-upload
          :action="importParseUrl"
          :headers="uploadHeaders"
          :on-success="handleImportParse"
          :on-error="handleImportError"
          :show-file-list="false"
          accept=".xlsx,.xls"
          :disabled="isImporting"
        >
          <el-button type="primary" :loading="isImporting">
            <el-icon><Upload /></el-icon>
            {{ isImporting ? '解析中...' : '选择Excel文件' }}
          </el-button>
        </el-upload>
        <p class="import-tip">
          <strong>导入说明：</strong><br>
          1. 请使用Excel文件（.xlsx/.xls格式）<br>
          2. 必须包含以下列：合同编号、合同名称、合同总额(万)<br>
          3. 可选列：甲方、项目令号、签约日期、业态、密级、负责人、验收节点、回款节点<br>
          4. 合同编号必须唯一，重复编号将无法导入
        </p>
      </div>
      
      <div v-else-if="importStep === 2" class="import-step-2">
        <div class="import-summary">
          <span class="summary-item">总数：{{ importSummary.total }}</span>
          <span class="summary-item valid">有效：{{ importSummary.valid_count }}</span>
          <span class="summary-item invalid">无效：{{ importSummary.invalid_count }}</span>
        </div>
        
        <div class="import-table-wrapper">
          <el-table :data="importRows" stripe border max-height="400">
            <el-table-column prop="row_index" label="行号" width="80" />
            <el-table-column prop="data.contract_no" label="合同编号" width="150" />
            <el-table-column prop="data.contract_name" label="合同名称" width="150" />
            <el-table-column prop="data.party_a" label="甲方" width="120" />
            <el-table-column prop="data.total_amt" label="合同总额(万)" width="120">
              <template #default="scope">
                {{ (scope.row.data.total_amt || 0) / 10000 }}
              </template>
            </el-table-column>
            <el-table-column prop="valid" label="状态" width="100">
              <template #default="scope">
                <el-tag :type="scope.row.valid ? 'success' : 'danger'" size="small">
                  {{ scope.row.valid ? '有效' : '无效' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="errors" label="错误信息" width="200">
              <template #default="scope">
                <span v-if="scope.row.errors && scope.row.errors.length" class="error-text">
                  {{ scope.row.errors.join(', ') }}
                </span>
                <span v-else class="success-text">无</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
      
      <div v-else-if="importStep === 3" class="import-step-3">
        <div class="import-result">
          <el-icon class="result-icon success"><CircleCheck /></el-icon>
          <h3>导入完成</h3>
          <p class="result-stats">
            总数：{{ importResult.total }} | 
            <span class="success">成功：{{ importResult.success_count }}</span> | 
            <span class="error">失败：{{ importResult.fail_count }}</span>
          </p>
          <div v-if="importResult.fail_count > 0" class="fail-list">
            <h4>失败记录：</h4>
            <ul>
              <li v-for="(result, idx) in importResult.results.filter(r => !r.success)" :key="idx">
                第{{ result.row_index }}行：{{ result.message }}
              </li>
            </ul>
          </div>
        </div>
      </div>
      
      <template #footer>
        <el-button v-if="importStep === 2" @click="importStep = 1">重新上传</el-button>
        <el-button v-if="importStep === 2" type="primary" :loading="isImporting" @click="executeImport">
          {{ isImporting ? '导入中...' : '确认导入' }}
        </el-button>
        <el-button v-if="importStep === 3" @click="closeImportModal">关闭</el-button>
        <el-button v-if="importStep === 1" @click="showImportModal = false">取消</el-button>
      </template>
    </el-dialog>

    <!-- 合同销售分成弹窗 -->
    <el-dialog v-model="showCommissionModal" title="合同销售分成" width="680px" :close-on-click-modal="false">
      <div v-if="commissionContract.name" style="margin-bottom: 16px; padding: 12px 16px; background: #f5f7fa; border-radius: 6px;">
        <div style="font-weight: 700; font-size: 15px;">{{ commissionContract.name }}</div>
        <div style="color: #909399; font-size: 13px; margin-top: 4px;">
          合同金额：<strong style="color: #e6a23c;">{{ formatYuan(commissionContract.totalAmt) }}</strong> 元
        </div>
      </div>

      <el-table :data="commissionRows" border stripe size="small" style="width: 100%;">
        <el-table-column label="销售人员" min-width="160">
          <template #default="{ row }">
            <el-select v-model="row.username" filterable placeholder="选择销售" style="width: 100%;">
              <el-option
                v-for="u in salesUsers"
                :key="u.username"
                :label="`${u.name} (${u.username})`"
                :value="u.username"
              />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="分成比例(%)" width="160">
          <template #default="{ row }">
            <el-input-number v-model="row.ratio" :min="0" :max="100" :precision="2" :step="5" size="small" style="width: 100%;" />
          </template>
        </el-table-column>
        <el-table-column label="分成金额(元)" width="140" align="right">
          <template #default="{ row }">
            <span style="color: #409eff; font-weight: 600;">
              {{ formatYuan(commissionContract.totalAmt * (row.ratio || 0) / 100) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ $index }">
            <el-button link type="danger" size="small" @click="commissionRows.splice($index, 1)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div style="margin-top: 12px; display: flex; justify-content: space-between; align-items: center;">
        <el-button size="small" @click="addCommissionRow">+ 添加销售</el-button>
        <div>
          <span>比例合计：</span>
          <strong :style="{ color: commissionTotalRatio === 100 ? '#67c23a' : '#f56c6c', fontSize: '16px' }">
            {{ commissionTotalRatio.toFixed(2) }}%
          </strong>
          <el-tag v-if="commissionTotalRatio === 100" type="success" size="small" style="margin-left: 8px;">✓ 合规</el-tag>
          <el-tag v-else type="danger" size="small" style="margin-left: 8px;">需等于 100%</el-tag>
        </div>
      </div>

      <template #footer>
        <el-button @click="showCommissionModal = false">取消</el-button>
        <el-button type="primary" :loading="savingCommission" @click="saveCommission">保存分成</el-button>
      </template>
    </el-dialog>

    <!-- 框架合同验收记录弹窗 -->
    <el-dialog v-model="showAcceptanceModal" title="框架合同验收记录" width="900px" :close-on-click-modal="false">
      <div v-if="acceptanceContract.name" style="margin-bottom: 16px; padding: 12px 16px; background: #f5f7fa; border-radius: 6px;">
        <div style="font-weight: 700; font-size: 15px;">
          {{ acceptanceContract.name }}
          <el-tag type="warning" size="small" style="margin-left: 8px;">框架合同</el-tag>
        </div>
        <div style="color: #909399; font-size: 13px; margin-top: 4px;">
          合同总额：<strong>{{ formatYuan(acceptanceContract.totalAmt) }}</strong> 元
          ｜ 累计验收：<strong style="color: #67c23a;">{{ formatYuan(acceptanceTotal) }}</strong> 元
          ｜ 剩余：<strong style="color: #e6a23c;">{{ formatYuan(acceptanceContract.totalAmt - acceptanceTotal) }}</strong> 元
        </div>
      </div>

      <!-- 新增验收记录表单 -->
      <div style="margin-bottom: 16px; padding: 12px; border: 1px solid #ebeef5; border-radius: 6px;">
        <div style="font-weight: 600; margin-bottom: 10px;">新增验收记录</div>
        <el-row :gutter="12">
          <el-col :span="6">
            <el-date-picker v-model="newAcceptance.date" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD"
              placeholder="验收日期" style="width: 100%;" />
          </el-col>
          <el-col :span="6">
            <el-input-number v-model="newAcceptance.amount" :min="0" :precision="2" :step="10000" placeholder="验收金额" style="width: 100%;" />
          </el-col>
          <el-col :span="8">
            <el-input v-model="newAcceptance.note" placeholder="备注（可选）" />
          </el-col>
          <el-col :span="4">
            <el-button type="primary" @click="addAcceptance" :loading="addingAcceptance">添加</el-button>
          </el-col>
        </el-row>
        <!-- 本次验收分成分配 -->
        <div style="margin-top: 12px; padding-top: 10px; border-top: 1px dashed #ebeef5;">
          <div style="display: flex; align-items: center; margin-bottom: 8px;">
            <span style="font-weight: 600; font-size: 13px;">本次验收分成分配</span>
            <el-button link type="primary" size="small" @click="addAccCommissionRow" style="margin-left: 12px;">+ 添加人员</el-button>
            <span style="margin-left: auto; font-size: 13px;">
              比例合计：<strong :style="{ color: newAcceptanceRatioSum === 100 ? '#67c23a' : '#f56c6c' }">{{ newAcceptanceRatioSum }}%</strong>
              <template v-if="newAcceptance.amount > 0 && newAcceptanceRatioSum === 100">
                ｜ 分配金额：<strong>{{ formatYuan(newAcceptance.amount) }}</strong> 元
              </template>
            </span>
          </div>
          <div v-for="(item, idx) in newAcceptance.commissions" :key="idx" style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
            <el-select v-model="item.username" placeholder="选择销售" filterable style="width: 180px;">
              <el-option v-for="u in salesUsers" :key="u.username" :label="u.name + ' (' + u.username + ')'" :value="u.username" />
            </el-select>
            <el-input-number v-model="item.ratio" :min="0" :max="100" :precision="1" :step="10" style="width: 120px;" />
            <span>%</span>
            <span v-if="newAcceptance.amount > 0 && item.ratio > 0" style="color: #909399; font-size: 12px;">
              = {{ formatYuan(newAcceptance.amount * item.ratio / 100) }} 元
            </span>
            <el-button link type="danger" size="small" @click="newAcceptance.commissions.splice(idx, 1)">移除</el-button>
          </div>
          <div v-if="!newAcceptance.commissions.length" style="color: #909399; font-size: 12px;">
            不分配分成则按合同负责人独享 100% 计入考核
          </div>
        </div>
      </div>

      <!-- 验收记录列表 -->
      <el-table :data="acceptanceRows" border stripe size="small" style="width: 100%;" empty-text="暂无验收记录">
        <el-table-column prop="acceptance_date" label="验收日期" width="120" />
        <el-table-column label="验收金额(元)" width="130" align="right">
          <template #default="{ row }">
            <strong style="color: #67c23a;">{{ formatYuan(row.acceptance_amount) }}</strong>
          </template>
        </el-table-column>
        <el-table-column label="分成分配" min-width="250">
          <template #default="{ row }">
            <template v-if="row.commissions && row.commissions.length">
              <el-tag v-for="c in row.commissions" :key="c.username" size="small" style="margin-right: 4px; margin-bottom: 2px;">
                {{ getUserName(c.username) }}: {{ c.ratio }}%
                <span v-if="row.acceptance_amount > 0" style="color: #909399;"> ({{ formatYuan(row.acceptance_amount * c.ratio / 100) }})</span>
              </el-tag>
            </template>
            <span v-else style="color: #909399; font-size: 12px;">负责人独享 100%</span>
          </template>
        </el-table-column>
        <el-table-column prop="note" label="备注" min-width="120" show-overflow-tooltip />
        <el-table-column prop="created_by" label="操作人" width="90" />
        <el-table-column label="操作" width="70" align="center" v-if="isAdmin">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="removeAcceptance(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <template #footer>
        <el-button @click="showAcceptanceModal = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { Plus, ArrowDown, Download, Upload, CircleCheck } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { useAuthStore } from '../stores/auth'
import { useRoute } from 'vue-router'

const authStore = useAuthStore()
const route = useRoute()
const contracts = ref([])
const isAdmin = computed(() => authStore.has('data.view_all'))
const users = ref([])
const customers = ref([])
const businessList = ref([])
const searchKeyword = ref('')
const showAddModal = ref(false)
const showPreviewModal = ref(false)
const showColumnSelector = ref(false)
const showImportModal = ref(false)
const formRef = ref(null)
const editingOwnerId = ref(null)
const savingOwnerId = ref(null)

const sortField = ref('sign_date')
const sortOrder = ref('desc')

const importStep = ref(1)
const isImporting = ref(false)
const importRows = ref([])
const importSummary = ref({ total: 0, valid_count: 0, invalid_count: 0 })
const importResult = ref({ total: 0, success_count: 0, fail_count: 0, results: [] })

const allColumns = [
  { prop: 'contract_name', label: '合同名称', width: '', minWidth: 160 },
  { prop: 'contract_no', label: '合同编号', width: 130 },
  { prop: 'project_order_no', label: '项目令号', width: 120 },
  { prop: 'party_a', label: '甲方', width: '', minWidth: 140 },
  { prop: 'total_amt', label: '合同总额(万)', width: 110 },
  { prop: 'income', label: '收入(元)', width: 110 },
  { prop: 'tax_amount', label: '税额(万)', width: 110 },
  { prop: 'pending_acceptance_amount', label: '待验收合同额(元)', width: 140 },
  { prop: 'paid_amt', label: '已回款(万)', width: 110 },
  { prop: 'pending_amt', label: '待回款(万)', width: 110 },
  { prop: 'sign_date', label: '签约日期', width: 110 },
  { prop: 'business_type', label: '业态', width: 90 },
  { prop: 'business_direction', label: '业务方向', width: 120 },
  { prop: 'classification', label: '密级', width: 80 },
  { prop: 'owner_name', label: '负责人', width: 90 },
  { prop: 'acceptance_nodes', label: '验收节点', width: 120 },
  { prop: 'payment_nodes', label: '回款节点', width: 120 },
  { prop: 'note', label: '备注', width: '', minWidth: 150 },
  { prop: 'status', label: '状态', width: 80 }
]

const visibleColumns = ref([
  'contract_name', 'contract_no', 'party_a', 'total_amt',
  'paid_amt', 'pending_amt', 'sign_date', 'owner_name', 'status'
])

const visibleColumnConfigs = computed(() => {
  return allColumns.filter(col => visibleColumns.value.includes(col.prop))
})

const filteredContracts = computed(() => {
  if (!searchKeyword.value) return contracts.value
  const keyword = searchKeyword.value.toLowerCase()
  return contracts.value.filter(record => 
    (record.contract_name && record.contract_name.toLowerCase().includes(keyword)) ||
    (record.contract_no && record.contract_no.toLowerCase().includes(keyword)) ||
    (record.project_order_no && record.project_order_no.toLowerCase().includes(keyword)) ||
    (record.party_a && record.party_a.toLowerCase().includes(keyword)) ||
    (record.owner_name && record.owner_name.toLowerCase().includes(keyword))
  )
})

const isAdminRole = computed(() => {
  return authStore.has('data.view_all')
})

// ==================== 合同销售分成 ====================
const showCommissionModal = ref(false)
const savingCommission = ref(false)
const commissionContract = reactive({ id: null, name: '', totalAmt: 0 })
const commissionRows = ref([])
const salesUsers = computed(() => {
  // 包含 role=销售 或 user_roles 里包含销售角色 或 is_sales_override 的用户
  return users.value.filter(u =>
    u.role === '销售' ||
    (u.roles && u.roles.includes('销售')) ||
    u.is_sales_override === 1 || u.is_sales_override === true
  )
})
const commissionTotalRatio = computed(() => {
  return commissionRows.value.reduce((sum, r) => sum + (Number(r.ratio) || 0), 0)
})

async function openCommission(row) {
  commissionContract.id = row.id
  commissionContract.name = row.contract_name || row.contract_no || `合同#${row.id}`
  commissionContract.totalAmt = Number(row.total_amt || 0)
  commissionRows.value = []
  showCommissionModal.value = true
  try {
    const res = await api.get(`/contracts/${row.id}/commissions`)
    if (res && res.code === 200 && res.data) {
      commissionRows.value = (res.data.commissions || []).map(c => ({
        username: c.username, ratio: Number(c.ratio) || 0
      }))
    }
  } catch (e) { /* noop */ }
}

function addCommissionRow() {
  commissionRows.value.push({ username: '', ratio: 0 })
}

async function saveCommission() {
  const items = commissionRows.value.filter(r => r.username)
  const total = items.reduce((s, r) => s + (Number(r.ratio) || 0), 0)
  if (items.length > 0 && Math.abs(total - 100) > 0.01) {
    ElMessage.warning(`比例合计 ${total.toFixed(2)}%，必须等于 100%`)
    return
  }
  savingCommission.value = true
  try {
    const res = await api.post(`/contracts/${commissionContract.id}/commissions`, {
      commissions: items.map(r => ({ username: r.username, ratio: Number(r.ratio) || 0 }))
    })
    if (res && res.code === 200) {
      ElMessage.success('分成保存成功')
      showCommissionModal.value = false
    } else {
      ElMessage.error((res && res.message) || '保存失败')
    }
  } finally {
    savingCommission.value = false
  }
}

// ==================== 框架合同验收记录 ====================
const showAcceptanceModal = ref(false)
const addingAcceptance = ref(false)
const acceptanceContract = reactive({ id: null, name: '', totalAmt: 0 })
const acceptanceRows = ref([])
const newAcceptance = reactive({ date: '', amount: 0, note: '', commissions: [] })
const acceptanceTotal = computed(() => acceptanceRows.value.reduce((s, r) => s + (Number(r.acceptance_amount) || 0), 0))
const newAcceptanceRatioSum = computed(() => newAcceptance.commissions.reduce((s, c) => s + (Number(c.ratio) || 0), 0))

function getUserName(username) {
  const u = users.value.find(x => x.username === username)
  return u ? u.name : username
}

function addAccCommissionRow() {
  newAcceptance.commissions.push({ username: '', ratio: 0 })
}

async function openAcceptance(row) {
  acceptanceContract.id = row.id
  acceptanceContract.name = row.contract_name || row.contract_no || `合同#${row.id}`
  acceptanceContract.totalAmt = Number(row.total_amt || 0)
  acceptanceRows.value = []
  newAcceptance.date = ''
  newAcceptance.amount = 0
  newAcceptance.note = ''
  newAcceptance.commissions = []
  showAcceptanceModal.value = true
  await loadAcceptances()
}

async function loadAcceptances() {
  try {
    const res = await api.get(`/contracts/${acceptanceContract.id}/acceptances`)
    if (res && res.code === 200 && res.data) {
      acceptanceRows.value = res.data.acceptances || []
    }
  } catch (e) { /* noop */ }
}

async function addAcceptance() {
  if (!newAcceptance.date) { ElMessage.warning('请选择验收日期'); return }
  if (!newAcceptance.amount || newAcceptance.amount <= 0) { ElMessage.warning('验收金额必须大于0'); return }
  const items = newAcceptance.commissions.filter(c => c.username)
  const totalRatio = items.reduce((s, c) => s + (Number(c.ratio) || 0), 0)
  if (items.length > 0 && Math.abs(totalRatio - 100) > 0.01) {
    ElMessage.warning(`分成比例合计 ${totalRatio.toFixed(1)}%，必须等于 100%`)
    return
  }
  addingAcceptance.value = true
  try {
    const res = await api.post(`/contracts/${acceptanceContract.id}/acceptances`, {
      acceptance_date: newAcceptance.date,
      acceptance_amount: newAcceptance.amount,
      note: newAcceptance.note,
      commissions: items.map(c => ({ username: c.username, ratio: Number(c.ratio) || 0 }))
    })
    if (res && res.code === 200) {
      ElMessage.success('验收记录添加成功')
      newAcceptance.date = ''
      newAcceptance.amount = 0
      newAcceptance.note = ''
      newAcceptance.commissions = []
      await loadAcceptances()
    } else {
      ElMessage.error((res && res.message) || '添加失败')
    }
  } finally {
    addingAcceptance.value = false
  }
}

async function removeAcceptance(accId) {
  try {
    await ElMessageBox.confirm('确认删除该验收记录？', '提示', { type: 'warning' })
  } catch { return }
  const res = await api.delete(`/contracts/acceptances/${accId}`)
  if (res && res.code === 200) {
    ElMessage.success('删除成功')
    await loadAcceptances()
  } else {
    ElMessage.error((res && res.message) || '删除失败')
  }
}

// 按已选客户联动过滤的商机列表
const filteredBusiness = computed(() => {
  if (!contractForm.cust_id) return []
  return businessList.value.filter(b => b.cust_id === contractForm.cust_id)
})

const contractForm = reactive({
  id: null,
  contract_name: '',
  contract_no: '',
  party_a: '',
  project_order_no: '',
  total_amt: 0,
  income: 0,
  tax_amount: 0,
  pending_acceptance_amount: 0,
  sign_date: '',
  business_type: '',
  business_direction: '',
  classification: '',
  status: '执行中',
  owner_id: '',
  cust_id: '',
  b_id: '',
  acceptance_nodes: '',
  payment_nodes: '',
  note: '',
  contract_file_path: '',
  tech_agreement_file_path: '',
  is_framework: 0
})

const contractFileList = ref([])
const techFileList = ref([])

const previewContractFile = ref('')
const previewContractFileName = ref('')
const previewTechFile = ref('')
const previewTechFileName = ref('')
const previewTextContent = ref('')
const previewTechTextContent = ref('')
const contractBlobUrl = ref('')
const techBlobUrl = ref('')
const isLoadingContract = ref(false)
const isLoadingTech = ref(false)

const uploadUrl = computed(() => '/api/contracts/upload')
const importParseUrl = computed(() => '/api/contracts/import-parse')
const uploadHeaders = computed(() => ({
  Authorization: `Bearer ${authStore.token}`
}))

const validateContractNoRule = async (rule, value, callback) => {
  if (!value) {
    callback()
    return
  }
  
  try {
    const params = { contract_no: value }
    if (contractForm.id) {
      params.exclude_id = contractForm.id
    }
    const response = await api.get('/contracts/check-no', params)
    if (response.code === 200 && response.data.exists) {
      callback(new Error('合同编号已存在，请重新输入'))
    } else {
      callback()
    }
  } catch (error) {
    console.error('验证合同编号失败:', error)
    callback()
  }
}

const validateContractNo = async () => {
  if (!contractForm.contract_no) return
  await validateContractNoRule({}, contractForm.contract_no, () => {})
}

const rules = {
  contract_name: [{ required: true, message: '请输入合同名称', trigger: 'blur' }],
  contract_no: [
    { required: true, message: '请输入合同编号', trigger: 'blur' },
    { validator: validateContractNoRule, trigger: 'blur' }
  ],
  total_amt: [{ required: true, message: '请输入合同总额', trigger: 'blur' }],
  cust_id: [{ required: true, message: '请选择关联客户', trigger: 'change' }]
}

const formatAmount = (value) => {
  return ((value || 0) / 10000).toFixed(4)
}

// 按元格式化（千分位），用于分成/验收弹窗
const formatYuan = (value) => {
  return (Number(value) || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const getPendingAmt = (row) => {
  const total = row.total_amt || 0
  const paid = row.paid_amt || 0
  return Math.max(0, total - paid)
}

const handleImportParse = (response) => {
  if (response.code === 200) {
    importRows.value = response.data.rows
    importSummary.value = {
      total: response.data.total,
      valid_count: response.data.valid_count,
      invalid_count: response.data.invalid_count
    }
    importStep.value = 2
  } else {
    ElMessage.error(response.message)
  }
}

const handleImportError = (error) => {
  ElMessage.error('解析失败：' + (error.message || '未知错误'))
}

const executeImport = async () => {
  const validRows = importRows.value.filter(row => row.valid)
  if (validRows.length === 0) {
    ElMessage.warning('没有可导入的有效数据')
    return
  }
  
  isImporting.value = true
  try {
    const response = await api.post('/contracts/import-execute', validRows)
    if (response.code === 200) {
      importResult.value = response.data
      importStep.value = 3
      fetchContracts()
    } else {
      ElMessage.error(response.message)
    }
  } catch (error) {
    ElMessage.error('导入失败：' + (error.message || '网络错误'))
  } finally {
    isImporting.value = false
  }
}

const closeImportModal = () => {
  showImportModal.value = false
  importStep.value = 1
  importRows.value = []
  importSummary.value = { total: 0, valid_count: 0, invalid_count: 0 }
  importResult.value = { total: 0, success_count: 0, fail_count: 0, results: [] }
}

const sortPendingAmount = (a, b) => {
  const pendingA = (a.total_amt || 0) - (a.paid_amt || 0)
  const pendingB = (b.total_amt || 0) - (b.paid_amt || 0)
  return pendingA - pendingB
}

const getStatusType = (status) => {
  const types = {
    '执行中': 'success',
    '已完成': 'primary',
    '已终止': 'danger'
  }
  return types[status] || 'info'
}

const toggleColumn = (prop, checked) => {
  const index = visibleColumns.value.indexOf(prop)
  if (checked !== undefined) {
    if (checked && index === -1) {
      visibleColumns.value.push(prop)
    } else if (!checked && index > -1) {
      visibleColumns.value.splice(index, 1)
    }
  } else {
    if (index > -1) {
      visibleColumns.value.splice(index, 1)
    } else {
      visibleColumns.value.push(prop)
    }
  }
}

const isPdfFile = (fileName) => {
  return fileName && fileName.toLowerCase().endsWith('.pdf')
}

const downloadFile = async (url, fileName) => {
  try {
    const response = await fetch(url, {
      headers: { Authorization: `Bearer ${authStore.token}` }
    })
    
    if (!response.ok) {
      ElMessage.error('下载失败：' + response.statusText)
      return
    }
    
    const blob = await response.blob()
    const blobUrl = window.URL.createObjectURL(blob)
    
    const link = document.createElement('a')
    link.href = blobUrl
    link.download = fileName || url.split('/').pop()
    link.click()
    
    window.URL.revokeObjectURL(blobUrl)
  } catch (error) {
    ElMessage.error('下载失败：' + error.message)
  }
}

const fetchContracts = async () => {
  const response = await api.get('/contracts', { 
    sort_field: sortField.value, 
    sort_order: sortOrder.value 
  })
  if (response.code === 200) {
    contracts.value = response.data
  }
}

const handleSortChange = (sort) => {
  sortField.value = sort.prop
  sortOrder.value = sort.order || 'asc'
  fetchContracts()
}

const handleSearch = () => {
}

const fetchUsers = async () => {
  const response = await api.get('/users')
  if (response.code === 200) {
    users.value = response.data
  }
}

const fetchCustomers = async () => {
  const response = await api.get('/customers')
  if (response.code === 200) {
    customers.value = response.data
  }
}

const fetchBusinessList = async () => {
  const response = await api.get('/business', { status: 'all' })
  if (response.code === 200) {
    businessList.value = response.data
  }
}

// 切换关联客户：清空不属于该客户的商机，甲方为空时自动带出客户公司名
const onCustomerChange = () => {
  if (contractForm.b_id && !filteredBusiness.value.some(b => b.id === contractForm.b_id)) {
    contractForm.b_id = ''
  }
  if (!contractForm.party_a) {
    const c = customers.value.find(x => x.id === contractForm.cust_id)
    if (c && c.company) contractForm.party_a = c.company
  }
}

const saveContract = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (valid) {
      const payload = {
        ...contractForm,
        total_amt: (contractForm.total_amt || 0) * 10000,
        income: contractForm.income || 0,
        tax_amount: (contractForm.tax_amount || 0) * 10000,
        pending_acceptance_amount: contractForm.pending_acceptance_amount || 0
      }
      
      if (!contractForm.id) {
        payload.owner_id = authStore.username
        payload.status = '执行中'
      }
      
      try {
        let response
        if (contractForm.id) {
          response = await api.put(`/contracts/${contractForm.id}`, payload)
        } else {
          response = await api.post('/contracts', payload)
        }
        
        if (response.code === 200) {
          ElMessage.success('保存成功')
          showAddModal.value = false
          fetchContracts()
        } else {
          ElMessage.error(response.message)
        }
      } catch (error) {
        console.error('Save contract error:', error)
        ElMessage.error('保存失败')
      }
    }
  })
}

const editContract = (row) => {
  Object.assign(contractForm, row)
  contractForm.total_amt = (row.total_amt || 0) / 10000
  contractForm.income = row.income || 0
  contractForm.tax_amount = (row.tax_amount || 0) / 10000
  contractForm.pending_acceptance_amount = row.pending_acceptance_amount || 0
  contractFileList.value = []
  techFileList.value = []
  if (row.contract_file_path) {
    contractFileList.value = [{ name: row.contract_file_path.split('/').pop(), url: row.contract_file_path }]
  }
  if (row.tech_agreement_file_path) {
    techFileList.value = [{ name: row.tech_agreement_file_path.split('/').pop(), url: row.tech_agreement_file_path }]
  }
  showAddModal.value = true
}

const startEditOwner = (row) => {
  editingOwnerId.value = row.id
}

const saveOwnerChange = async (contractId, newOwnerId) => {
  savingOwnerId.value = contractId
  try {
    const response = await api.post(`/contracts/${contractId}/owner`, {
      owner_id: newOwnerId
    })
    if (response.code === 200) {
      ElMessage.success('负责人修改成功')
      editingOwnerId.value = null
      fetchContracts()
    } else {
      ElMessage.error(response.message || '修改失败')
      editingOwnerId.value = null
    }
  } catch (error) {
    console.error('修改负责人失败:', error)
    ElMessage.error('网络错误，请重试')
    editingOwnerId.value = null
  } finally {
    savingOwnerId.value = null
  }
}

const addContract = () => {
  Object.assign(contractForm, {
    id: null,
    contract_name: '',
    contract_no: '',
    party_a: '',
    project_order_no: '',
    total_amt: 0,
    sign_date: '',
    business_type: '',
    classification: '',
    status: '执行中',
    owner_id: '',
    cust_id: '',
    b_id: '',
    acceptance_nodes: '',
    payment_nodes: '',
    contract_file_path: '',
    tech_agreement_file_path: '',
    is_framework: 0
  })
  contractFileList.value = []
  techFileList.value = []
  showAddModal.value = true
}

const deleteContract = async (row) => {
  try {
    await ElMessageBox.confirm('确定要删除这个合同吗？', '提示', {
      type: 'warning'
    })
    
    const response = await api.delete(`/contracts/${row.id}`)
    if (response.code === 200) {
      ElMessage.success('删除成功')
      fetchContracts()
    } else {
      ElMessage.error(response.message)
    }
  } catch (error) {
    ElMessage.info('已取消删除')
  }
}

const exportContracts = () => {
  if (contracts.value.length === 0) {
    ElMessage.info('暂无数据可导出')
    return
  }
  
  const exportColumns = allColumns.filter(col => visibleColumns.value.includes(col.prop))
  
  const escapeCsvValue = (value) => {
    if (value === null || value === undefined) {
      return ''
    }
    let strValue = String(value)
    strValue = strValue.replace(/"/g, '""')
    return `"${strValue}"`
  }
  
  let csvContent = '\uFEFF' + exportColumns.map(col => escapeCsvValue(col.label)).join(',') + '\n'
  
  contracts.value.forEach(row => {
    const rowData = exportColumns.map(col => {
      let value = row[col.prop]
      if (col.prop === 'total_amt' || col.prop === 'paid_amt') {
        value = ((value || 0) / 10000).toFixed(4)
      } else if (col.prop === 'pending_amt') {
        value = (((row.total_amt || 0) - (row.paid_amt || 0)) / 10000).toFixed(4)
      }
      return escapeCsvValue(value)
    })
    csvContent += rowData.join(',') + '\n'
  })
  
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  const url = URL.createObjectURL(blob)
  const timestamp = new Date().toISOString().slice(0, 10).replace(/-/g, '')
  link.setAttribute('href', url)
  link.setAttribute('download', `合同列表_${timestamp}.csv`)
  link.style.visibility = 'hidden'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  
  ElMessage.success('导出成功')
}

const previewFiles = async (row) => {
  previewTextContent.value = ''
  previewTechTextContent.value = ''
  isLoadingContract.value = false
  isLoadingTech.value = false
  
  if (contractBlobUrl.value) {
    window.URL.revokeObjectURL(contractBlobUrl.value)
    contractBlobUrl.value = ''
  }
  if (techBlobUrl.value) {
    window.URL.revokeObjectURL(techBlobUrl.value)
    techBlobUrl.value = ''
  }
  
  showPreviewModal.value = true
  
  if (row.contract_file_path) {
    const downloadUrl = `/api/download-contract?id=${row.id}&type=contract`
    previewContractFile.value = downloadUrl
    previewContractFileName.value = row.contract_file_path.split('/').pop()
    
    isLoadingContract.value = true
    try {
      const response = await fetch(downloadUrl, {
        headers: { Authorization: `Bearer ${authStore.token}` }
      })
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      
      const contentType = response.headers.get('Content-Type')
      if (isPdfFile(previewContractFileName.value) || contentType?.includes('application/pdf')) {
        const blob = await response.blob()
        contractBlobUrl.value = window.URL.createObjectURL(blob)
      } else if (contentType?.includes('text/') || previewContractFileName.value.match(/\.(txt|md)$/i)) {
        previewTextContent.value = await response.text()
      } else {
        previewTextContent.value = '该文件类型暂不支持预览，请下载查看'
      }
    } catch (error) {
      console.error('预览合同文件失败:', error)
      previewTextContent.value = '无法预览文本内容: ' + error.message
    } finally {
      isLoadingContract.value = false
    }
  } else {
    previewContractFile.value = ''
    contractBlobUrl.value = ''
  }
  
  if (row.tech_agreement_file_path) {
    const downloadUrl = `/api/download-contract?id=${row.id}&type=tech`
    previewTechFile.value = downloadUrl
    previewTechFileName.value = row.tech_agreement_file_path.split('/').pop()
    
    isLoadingTech.value = true
    try {
      const response = await fetch(downloadUrl, {
        headers: { Authorization: `Bearer ${authStore.token}` }
      })
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      
      const contentType = response.headers.get('Content-Type')
      if (isPdfFile(previewTechFileName.value) || contentType?.includes('application/pdf')) {
        const blob = await response.blob()
        techBlobUrl.value = window.URL.createObjectURL(blob)
      } else if (contentType?.includes('text/') || previewTechFileName.value.match(/\.(txt|md)$/i)) {
        previewTechTextContent.value = await response.text()
      } else {
        previewTechTextContent.value = '该文件类型暂不支持预览，请下载查看'
      }
    } catch (error) {
      console.error('预览技术协议文件失败:', error)
      previewTechTextContent.value = '无法预览文本内容: ' + error.message
    } finally {
      isLoadingTech.value = false
    }
  } else {
    previewTechFile.value = ''
    techBlobUrl.value = ''
  }
}

const handleUploadSuccess = () => {
  ElMessage.success('文件上传成功')
}

const handleUploadError = () => {
  ElMessage.error('文件上传失败')
}

onMounted(() => {
  fetchContracts()
  fetchUsers()
  fetchCustomers()
  fetchBusinessList()
  const kw = route.query.keyword
  if (kw) {
    searchKeyword.value = kw
  }
})

watch(() => route.query.keyword, (newKeyword) => {
  if (newKeyword) {
    searchKeyword.value = newKeyword
  }
})

watch(showAddModal, (newVal) => {
  if (!newVal) {
    contractFileList.value = []
    techFileList.value = []
  } else {
    if (!contractForm.id) {
      Object.assign(contractForm, {
        id: null,
        contract_name: '',
        contract_no: '',
        party_a: '',
        project_order_no: '',
        total_amt: 0,
        sign_date: '',
        business_type: '',
        classification: '',
        status: '执行中',
        owner_id: '',
        is_audit: 0,
        pending_acceptance_amount: 0,
        cost: 0,
        gross_profit: 0,
        acceptance_date: '',
        expected_income_date: '',
        expected_income_year: '',
        total_cost: 0,
        acceptance_nodes: '',
        payment_nodes: '',
        cust_id: '',
        b_id: ''
      })
    }
  }
})

watch(showImportModal, (newVal) => {
  if (!newVal) {
    importStep.value = 1
    importRows.value = []
    importSummary.value = { total: 0, valid_count: 0, invalid_count: 0 }
    importResult.value = { total: 0, success_count: 0, fail_count: 0, results: [] }
  }
})
</script>

<style scoped>
.contracts {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.header-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-left: auto;
}

.search-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

.search-input {
  width: 200px;
}

.search-btn {
  height: 40px;
}

.add-btn {
  align-self: flex-start;
}

.export-btn {
}

.column-selector-content {
  padding: 8px 0;
}

.column-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  cursor: pointer;
}

.column-item:hover {
  background: #f5f7fa;
}

.column-selector-footer {
  display: flex;
  justify-content: flex-end;
  padding: 8px 16px;
  border-top: 1px solid #eee;
  margin-top: 8px;
}

.table-wrapper {
  overflow-x: auto;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.data-table {
  width: 100%;
  min-width: 100%;
  --el-table-header-bg-color: #f5f7fa;
  --el-table-header-text-color: #303133;
  --el-table-row-hover-bg-color: #ecf5ff;
  --el-table-border-color: #ebeef5;
}

.data-table :deep(.el-table__header th.el-table__cell) {
  font-weight: 600;
  font-size: 13px;
  white-space: nowrap;
}

.data-table :deep(.el-table__body .cell) {
  font-size: 13px;
  line-height: 1.5;
}

.preview-section {
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
}

.file-info {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.file-link {
  color: #4ecdc4;
  text-decoration: none;
  font-weight: bold;
}

.download-btn {
  margin-left: auto;
}

.pdf-preview {
  height: 500px;
}

.pdf-frame {
  width: 100%;
  height: 100%;
  border-radius: 8px;
}

.loading-preview {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 400px;
}

.text-preview {
  max-height: 400px;
  overflow-y: auto;
  background: #fff;
  padding: 16px;
  border-radius: 8px;
  font-family: monospace;
  white-space: pre-wrap;
}

.no-file {
  padding: 16px;
  color: #999;
  background: #f5f7fa;
  border-radius: 8px;
  text-align: center;
}

.pending-highlight {
  color: #f56c6c;
  font-weight: bold;
}

.import-step-1 {
  text-align: center;
  padding: 40px 0;
}

.import-tip {
  margin-top: 20px;
  text-align: left;
  font-size: 13px;
  color: #666;
  line-height: 1.8;
  background: #f5f7fa;
  padding: 16px;
  border-radius: 8px;
}

.import-summary {
  display: flex;
  gap: 24px;
  margin-bottom: 16px;
}

.summary-item {
  font-size: 14px;
  color: #666;
}

.summary-item.valid {
  color: #67c23a;
}

.summary-item.invalid {
  color: #f56c6c;
}

.import-table-wrapper {
  max-height: 400px;
  overflow-y: auto;
}

.error-text {
  color: #f56c6c;
  font-size: 12px;
}

.success-text {
  color: #67c23a;
  font-size: 12px;
}

.import-result {
  text-align: center;
  padding: 40px 0;
}

.result-icon {
  font-size: 64px;
  margin-bottom: 16px;
}

.result-icon.success {
  color: #67c23a;
}

.result-stats {
  font-size: 14px;
  color: #666;
}

.result-stats .success {
  color: #67c23a;
  font-weight: bold;
}

.result-stats .error {
  color: #f56c6c;
  font-weight: bold;
}

.fail-list {
  text-align: left;
  margin-top: 20px;
  padding: 16px;
  background: #fef0f0;
  border-radius: 8px;
  max-height: 200px;
  overflow-y: auto;
}

.fail-list h4 {
  margin-bottom: 12px;
  color: #f56c6c;
}

.fail-list ul {
  padding-left: 20px;
  margin: 0;
}

.fail-list li {
  font-size: 13px;
  color: #f56c6c;
  margin-bottom: 4px;
}
</style>