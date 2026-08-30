<template>
  <div class="quotes">
    <div class="header-row">
      <el-button type="primary" @click="openAddModal" class="add-btn">
        <el-icon><Plus /></el-icon>
        新建报价单
      </el-button>
      <div class="search-wrapper">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索报价单号、标题..."
          class="search-input"
          clearable
          @keyup.enter="handleSearch"
        >
          <template #prefix><span>🔍</span></template>
        </el-input>
        <el-select v-model="filterStatus" placeholder="状态" clearable style="width: 130px" @change="fetchQuotes">
          <el-option label="草稿" value="draft" />
          <el-option label="已发送" value="sent" />
          <el-option label="已接受" value="accepted" />
          <el-option label="已拒绝" value="rejected" />
          <el-option label="已过期" value="expired" />
        </el-select>
        <el-button @click="handleSearch" class="search-btn">搜索</el-button>
      </div>
    </div>

    <div class="table-container">
      <div class="table-wrapper">
        <el-table :data="quotes" stripe border class="data-table" max-height="70vh">
          <el-table-column prop="quote_no" label="报价单号" min-width="160" sortable />
          <el-table-column prop="title" label="标题" min-width="160" sortable show-overflow-tooltip />
          <el-table-column prop="customer_name" label="客户" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.customer_name || '-' }}</template>
          </el-table-column>
          <el-table-column prop="business_title" label="关联商机" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.business_title || '-' }}</template>
          </el-table-column>
          <el-table-column label="总额(元)" width="130" sortable :sort-method="(a,b)=>(a.total_amount||0)-(b.total_amount||0)">
            <template #default="{ row }">¥{{ formatMoney(row.total_amount) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="valid_until" label="有效期至" min-width="110" sortable>
            <template #default="{ row }">{{ row.valid_until || '-' }}</template>
          </el-table-column>
          <el-table-column prop="owner_name" label="负责人" width="90" sortable />
          <el-table-column prop="created_at" label="创建时间" min-width="140" sortable />
          <el-table-column label="操作" min-width="280" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="viewDetail(row)">详情</el-button>
              <el-button size="small" type="primary" v-if="canEdit(row)" @click="editQuote(row)">编辑</el-button>
              <el-button size="small" type="success" v-if="canChangeStatus(row)" @click="openStatusModal(row)">状态</el-button>
              <el-button size="small" type="danger" v-if="canEdit(row)" @click="deleteQuote(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- 新建/编辑报价单 -->
    <el-dialog v-model="showFormModal" :title="quoteForm.id ? '编辑报价单' : '新建报价单'" width="900px" :close-on-click-modal="false" top="5vh">
      <el-form :model="quoteForm" :rules="rules" ref="formRef" label-width="90px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="报价单号">
              <el-input v-model="quoteForm.quote_no" placeholder="留空自动生成" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="标题" prop="title">
              <el-input v-model="quoteForm.title" placeholder="报价单标题" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="客户">
              <el-select v-model="quoteForm.cust_id" placeholder="选择客户（可选）" filterable clearable style="width: 100%">
                <el-option v-for="c in customers" :key="c.id" :label="`${c.company || c.name}`" :value="c.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="关联商机">
              <el-select v-model="quoteForm.b_id" placeholder="选择商机（可选）" filterable clearable style="width: 100%">
                <el-option v-for="b in businessOptions" :key="b.id" :label="b.title" :value="b.id" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="有效期至">
              <el-date-picker v-model="quoteForm.valid_until" type="date" value-format="YYYY-MM-DD" placeholder="有效期截止日" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="备注">
              <el-input v-model="quoteForm.remark" placeholder="备注" />
            </el-form-item>
          </el-col>
        </el-row>

        <div class="items-section">
          <div class="items-header">
            <span class="items-title">报价明细</span>
            <el-button size="small" type="primary" @click="addItem">+ 添加明细</el-button>
          </div>
          <el-table :data="quoteForm.items" border size="small" class="items-table">
            <el-table-column label="产品" min-width="200">
              <template #default="{ row, $index }">
                <el-select v-model="row.product_id" placeholder="选择产品（可选）" filterable clearable style="width: 100%" @change="(val) => onProductChange(val, $index)">
                  <el-option v-for="p in products" :key="p.id" :label="`${p.name}${p.model ? ' ('+p.model+')' : ''}`" :value="p.id" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="名称" min-width="150">
              <template #default="{ row }">
                <el-input v-model="row.name" placeholder="明细名称" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="型号" min-width="110">
              <template #default="{ row }">
                <el-input v-model="row.model" placeholder="型号" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="数量" width="110">
              <template #default="{ row }">
                <el-input-number v-model="row.qty" :min="0.01" :precision="2" :step="1" size="small" controls-position="right" @change="calcAmount(row)" />
              </template>
            </el-table-column>
            <el-table-column label="单价(元)" width="140">
              <template #default="{ row }">
                <el-input-number v-model="row.unit_price" :min="0" :precision="2" :step="100" size="small" controls-position="right" @change="calcAmount(row)" />
              </template>
            </el-table-column>
            <el-table-column label="金额(元)" width="120">
              <template #default="{ row }">
                <span class="amount-cell">¥{{ formatMoney(row.amount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80">
              <template #default="{ $index }">
                <el-button size="small" type="danger" link @click="removeItem($index)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="items-total">
            <span>合计：</span>
            <span class="total-amount">¥{{ formatMoney(totalAmount) }}</span>
          </div>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="showFormModal = false">取消</el-button>
        <el-button type="primary" @click="saveQuote">保存</el-button>
      </template>
    </el-dialog>

    <!-- 详情 -->
    <el-dialog v-model="showDetailModal" title="报价单详情" width="860px" top="5vh">
      <template v-if="detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="报价单号">{{ detail.quote_no }}</el-descriptions-item>
          <el-descriptions-item label="标题">{{ detail.title || '-' }}</el-descriptions-item>
          <el-descriptions-item label="客户">{{ detail.customer_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="关联商机">{{ detail.business_title || '-' }}</el-descriptions-item>
          <el-descriptions-item label="总额">¥{{ formatMoney(detail.total_amount) }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTagType(detail.status)" size="small">{{ statusLabel(detail.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="有效期至">{{ detail.valid_until || '-' }}</el-descriptions-item>
          <el-descriptions-item label="负责人">{{ detail.owner_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ detail.created_at || '-' }}</el-descriptions-item>
          <el-descriptions-item label="备注">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>
        <h4 class="detail-items-title">报价明细</h4>
        <el-table :data="detail.items" border size="small">
          <el-table-column type="index" label="#" width="50" />
          <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip />
          <el-table-column prop="model" label="型号" min-width="110" show-overflow-tooltip />
          <el-table-column label="数量" width="90">
            <template #default="{ row }">{{ formatMoney(row.qty) }}</template>
          </el-table-column>
          <el-table-column label="单价" width="110">
            <template #default="{ row }">¥{{ formatMoney(row.unit_price) }}</template>
          </el-table-column>
          <el-table-column label="金额" width="120">
            <template #default="{ row }">¥{{ formatMoney(row.amount) }}</template>
          </el-table-column>
          <el-table-column prop="remark" label="备注" min-width="120" show-overflow-tooltip />
        </el-table>
      </template>
      <template #footer>
        <el-button @click="showDetailModal = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 状态流转 -->
    <el-dialog v-model="showStatusModal" :title="`状态变更 - ${currentQuote?.quote_no || ''}`" width="420px">
      <el-form label-width="90px">
        <el-form-item label="当前状态">
          <el-tag :type="statusTagType(currentQuote?.status)" size="small">{{ statusLabel(currentQuote?.status) }}</el-tag>
        </el-form-item>
        <el-form-item label="新状态">
          <el-select v-model="newStatus" placeholder="选择新状态" style="width: 100%">
            <el-option label="草稿" value="draft" />
            <el-option label="已发送" value="sent" />
            <el-option label="已接受" value="accepted" />
            <el-option label="已拒绝" value="rejected" />
            <el-option label="已过期" value="expired" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showStatusModal = false">取消</el-button>
        <el-button type="primary" @click="saveStatus">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const isAdmin = computed(() => authStore.has('data.view_all'))

const quotes = ref([])
const customers = ref([])
const businessOptions = ref([])
const products = ref([])

const searchKeyword = ref('')
const filterStatus = ref('')

const showFormModal = ref(false)
const formRef = ref(null)
const showDetailModal = ref(false)
const detail = ref(null)
const showStatusModal = ref(false)
const currentQuote = ref(null)
const newStatus = ref('')

const quoteForm = reactive({
  id: null,
  quote_no: '',
  title: '',
  cust_id: null,
  b_id: null,
  valid_until: '',
  remark: '',
  owner_id: '',
  items: []
})

const rules = {
  title: [{ required: true, message: '请输入标题', trigger: 'blur' }]
}

const formatMoney = (v) => {
  const n = Number(v || 0)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const statusTagType = (s) => ({
  draft: 'info',
  sent: 'primary',
  accepted: 'success',
  rejected: 'danger',
  expired: 'warning'
}[s] || 'info')

const statusLabel = (s) => ({
  draft: '草稿',
  sent: '已发送',
  accepted: '已接受',
  rejected: '已拒绝',
  expired: '已过期'
}[s] || s)

const canEdit = (row) => {
  if (!row) return false
  if (row.status === 'accepted') return isAdmin.value
  if (row.status === 'rejected' || row.status === 'expired') return isAdmin.value
  return true
}

const canChangeStatus = (row) => {
  if (!row) return false
  return row.status !== 'accepted'
}

const totalAmount = computed(() => {
  return quoteForm.items.reduce((sum, it) => sum + (Number(it.amount) || 0), 0)
})

const fetchQuotes = async () => {
  const params = {}
  if (searchKeyword.value) params.keyword = searchKeyword.value
  if (filterStatus.value) params.status = filterStatus.value
  const resp = await api.get('/quotes', params)
  if (resp.code === 200) {
    quotes.value = resp.data
  }
}

const fetchCustomers = async () => {
  const resp = await api.get('/customers')
  if (resp.code === 200) {
    customers.value = resp.data
  }
}

const fetchBusiness = async () => {
  const resp = await api.get('/business', { status: 'all' })
  if (resp.code === 200) {
    businessOptions.value = resp.data
  }
}

const fetchProducts = async () => {
  const resp = await api.get('/products')
  if (resp.code === 200) {
    products.value = resp.data
  }
}

const handleSearch = () => fetchQuotes()

const resetForm = () => {
  Object.assign(quoteForm, {
    id: null, quote_no: '', title: '', cust_id: null, b_id: null,
    valid_until: '', remark: '', owner_id: '', items: []
  })
}

const openAddModal = () => {
  resetForm()
  quoteForm.items.push(newItem())
  showFormModal.value = true
}

const newItem = () => ({ product_id: null, name: '', model: '', qty: 1, unit_price: 0, amount: 0, remark: '' })

const addItem = () => {
  quoteForm.items.push(newItem())
}

const removeItem = (idx) => {
  quoteForm.items.splice(idx, 1)
}

const onProductChange = (productId, idx) => {
  const p = products.value.find(x => x.id === productId)
  if (!p) return
  const item = quoteForm.items[idx]
  item.name = p.name
  item.model = p.model
  if (!item.unit_price || item.unit_price === 0) {
    item.unit_price = p.price || 0
  }
  calcAmount(item)
}

const calcAmount = (row) => {
  row.amount = Number((Number(row.qty || 0) * Number(row.unit_price || 0)).toFixed(2))
}

const editQuote = async (row) => {
  const resp = await api.get(`/quotes/${row.id}`)
  if (resp.code !== 200) {
    ElMessage.error(resp.message)
    return
  }
  const d = resp.data
  Object.assign(quoteForm, {
    id: d.id,
    quote_no: d.quote_no,
    title: d.title || '',
    cust_id: d.cust_id,
    b_id: d.b_id,
    valid_until: d.valid_until || '',
    remark: d.remark || '',
    owner_id: d.owner_id || '',
    items: (d.items || []).map(it => ({
      product_id: it.product_id, name: it.name, model: it.model,
      qty: it.qty, unit_price: it.unit_price, amount: it.amount, remark: it.remark
    }))
  })
  showFormModal.value = true
}

const saveQuote = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    if (quoteForm.items.length === 0) {
      ElMessage.warning('请至少添加一条明细')
      return
    }
    // 保存前重新计算所有明细金额
    quoteForm.items.forEach(calcAmount)

    try {
      let resp
      if (quoteForm.id) {
        resp = await api.put(`/quotes/${quoteForm.id}`, quoteForm)
      } else {
        resp = await api.post('/quotes', quoteForm)
      }
      if (resp.code === 200) {
        ElMessage.success('保存成功')
        showFormModal.value = false
        fetchQuotes()
      } else {
        ElMessage.error(resp.message)
      }
    } catch (e) {
      ElMessage.error('保存失败')
    }
  })
}

const deleteQuote = async (row) => {
  try {
    await ElMessageBox.confirm(`确定要删除报价单「${row.quote_no}」吗？`, '提示', { type: 'warning' })
    const resp = await api.delete(`/quotes/${row.id}`)
    if (resp.code === 200) {
      ElMessage.success('删除成功')
      fetchQuotes()
    } else {
      ElMessage.error(resp.message)
    }
  } catch (e) {
    if (e !== 'cancel') ElMessage.info('已取消删除')
  }
}

const viewDetail = async (row) => {
  const resp = await api.get(`/quotes/${row.id}`)
  if (resp.code === 200) {
    detail.value = resp.data
    showDetailModal.value = true
  } else {
    ElMessage.error(resp.message)
  }
}

const openStatusModal = (row) => {
  currentQuote.value = row
  newStatus.value = row.status
  showStatusModal.value = true
}

const saveStatus = async () => {
  if (!currentQuote.value) return
  try {
    const resp = await api.post(`/quotes/${currentQuote.value.id}/status`, { status: newStatus.value })
    if (resp.code === 200) {
      ElMessage.success('状态更新成功')
      showStatusModal.value = false
      fetchQuotes()
    } else {
      ElMessage.error(resp.message)
    }
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

onMounted(() => {
  fetchQuotes()
  fetchCustomers()
  fetchBusiness()
  fetchProducts()
})
</script>

<style scoped>
.header-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.add-btn {
  display: flex;
  align-items: center;
  gap: 4px;
}
.search-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  flex-wrap: wrap;
}
.search-input {
  width: 240px;
}
.table-container {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
}
.items-section {
  margin-top: 16px;
  border-top: 1px solid #e2e8f0;
  padding-top: 16px;
}
.items-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.items-title {
  font-weight: 600;
  color: #334155;
}
.amount-cell {
  font-weight: 600;
  color: #4ecdc4;
}
.items-total {
  margin-top: 12px;
  text-align: right;
  font-size: 16px;
}
.total-amount {
  font-weight: 700;
  color: #ee6666;
  margin-left: 8px;
}
.detail-items-title {
  margin: 16px 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}
</style>
