<template>
  <div class="products">
    <div class="header-row">
      <el-button type="primary" @click="openAddModal" class="add-btn">
        <el-icon><Plus /></el-icon>
        添加产品
      </el-button>
      <el-button type="warning" @click="openWarningsModal" class="add-btn">
        <el-icon><Warning /></el-icon>
        库存预警
        <el-badge v-if="warningCount > 0" :value="warningCount" class="warn-badge" />
      </el-button>
      <div class="search-wrapper">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索产品名称、型号..."
          class="search-input"
          clearable
          @keyup.enter="handleSearch"
        >
          <template #prefix><span>🔍</span></template>
        </el-input>
        <el-select v-model="filterCategory" placeholder="分类" clearable filterable allow-create style="width: 130px" @change="fetchProducts">
          <el-option v-for="c in categoryOptions" :key="c" :label="c" :value="c" />
        </el-select>
        <el-select v-model="filterStockStatus" placeholder="库存状态" clearable style="width: 120px" @change="fetchProducts">
          <el-option label="正常" value="normal" />
          <el-option label="预警" value="warning" />
          <el-option label="缺货" value="out" />
        </el-select>
        <el-button @click="handleSearch" class="search-btn">搜索</el-button>
      </div>
    </div>

    <div class="table-container">
      <div class="table-wrapper">
        <el-table :data="products" stripe border class="data-table" max-height="70vh">
          <el-table-column prop="name" label="产品名称" min-width="140" sortable show-overflow-tooltip />
          <el-table-column prop="model" label="型号" min-width="120" sortable show-overflow-tooltip />
          <el-table-column prop="category" label="分类" min-width="100" sortable />
          <el-table-column prop="unit" label="单位" width="70" />
          <el-table-column label="单价(元)" width="110" sortable :sort-method="(a,b)=>(a.price||0)-(b.price||0)">
            <template #default="{ row }">¥{{ formatNum(row.price) }}</template>
          </el-table-column>
          <el-table-column label="成本(元)" width="110" sortable :sort-method="(a,b)=>(a.cost||0)-(b.cost||0)">
            <template #default="{ row }">¥{{ formatNum(row.cost) }}</template>
          </el-table-column>
          <el-table-column label="库存" width="100" sortable :sort-method="(a,b)=>(a.stock||0)-(b.stock||0)">
            <template #default="{ row }">
              <span :class="stockClass(row)">{{ formatNum(row.stock) }} {{ row.unit }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="warn_threshold" label="预警阈值" width="90">
            <template #default="{ row }">{{ formatNum(row.warn_threshold) }}</template>
          </el-table-column>
          <el-table-column label="库存状态" width="90">
            <template #default="{ row }">
              <el-tag :type="stockTagType(row.stock_status)" size="small">{{ stockStatusLabel(row.stock_status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="owner_name" label="负责人" width="90" sortable />
          <el-table-column label="操作" min-width="240" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="editProduct(row)">编辑</el-button>
              <el-button size="small" type="success" @click="openInventoryModal(row)">出入库</el-button>
              <el-button size="small" type="primary" @click="openHistoryModal(row)">流水</el-button>
              <el-button size="small" type="danger" @click="deleteProduct(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- 添加/编辑产品 -->
    <el-dialog v-model="showFormModal" :title="productForm.id ? '编辑产品' : '添加产品'" width="560px" :close-on-click-modal="false">
      <el-form :model="productForm" :rules="rules" ref="formRef" label-width="90px">
        <el-form-item label="产品名称" prop="name">
          <el-input v-model="productForm.name" placeholder="产品名称" />
        </el-form-item>
        <el-form-item label="型号">
          <el-input v-model="productForm.model" placeholder="产品型号" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="productForm.category" placeholder="选择或输入分类" filterable allow-create style="width: 100%">
            <el-option v-for="c in categoryOptions" :key="c" :label="c" :value="c" />
          </el-select>
        </el-form-item>
        <el-form-item label="单位">
          <el-input v-model="productForm.unit" placeholder="如：套/台/件/个" style="width: 160px" />
        </el-form-item>
        <el-form-item label="单价(元)">
          <el-input-number v-model="productForm.price" :min="0" :precision="2" :step="100" style="width: 200px" />
        </el-form-item>
        <el-form-item label="成本(元)">
          <el-input-number v-model="productForm.cost" :min="0" :precision="2" :step="100" style="width: 200px" />
        </el-form-item>
        <el-form-item v-if="!productForm.id" label="初始库存">
          <el-input-number v-model="productForm.stock" :min="0" :precision="2" :step="10" style="width: 200px" />
          <span class="form-hint">创建后可通过出入库调整</span>
        </el-form-item>
        <el-form-item label="预警阈值">
          <el-input-number v-model="productForm.warn_threshold" :min="0" :precision="2" :step="10" style="width: 200px" />
          <span class="form-hint">库存低于此值触发预警</span>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="productForm.description" type="textarea" :rows="2" placeholder="产品描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showFormModal = false">取消</el-button>
        <el-button type="primary" @click="saveProduct">确定</el-button>
      </template>
    </el-dialog>

    <!-- 出入库 -->
    <el-dialog v-model="showInventoryModal" :title="`出入库 - ${currentProduct?.name || ''}`" width="480px" :close-on-click-modal="false">
      <el-form :model="inventoryForm" :rules="inventoryRules" ref="inventoryFormRef" label-width="90px">
        <el-form-item label="当前库存">
          <span class="current-stock">{{ formatNum(currentProduct?.stock) }} {{ currentProduct?.unit }}</span>
        </el-form-item>
        <el-form-item label="操作类型" prop="type">
          <el-radio-group v-model="inventoryForm.type">
            <el-radio value="in">入库 (+)</el-radio>
            <el-radio value="out">出库 (-)</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="数量" prop="quantity">
          <el-input-number v-model="inventoryForm.quantity" :min="0.01" :precision="2" :step="1" style="width: 200px" />
          <span class="form-hint">{{ inventoryForm.unit }}</span>
        </el-form-item>
        <el-form-item label="关联单据">
          <el-input v-model="inventoryForm.reference" placeholder="如：合同编号、采购单号（可选）" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="inventoryForm.remark" type="textarea" :rows="2" placeholder="备注" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showInventoryModal = false">取消</el-button>
        <el-button type="primary" @click="saveInventory">确定</el-button>
      </template>
    </el-dialog>

    <!-- 出入库流水 -->
    <el-dialog v-model="showHistoryModal" :title="`出入库流水 - ${currentProduct?.name || ''}`" width="760px">
      <el-table :data="inventoryHistory" stripe border size="small" max-height="420">
        <el-table-column prop="created_at" label="时间" min-width="140" sortable />
        <el-table-column label="类型" width="80">
          <template #default="{ row }">
            <el-tag :type="row.type === 'in' ? 'success' : 'warning'" size="small">{{ row.type === 'in' ? '入库' : '出库' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="数量" width="100">
          <template #default="{ row }">
            <span :style="{color: row.type === 'in' ? '#67c23a' : '#e6a23c'}">
              {{ row.type === 'in' ? '+' : '-' }}{{ formatNum(row.quantity) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="reference" label="关联单据" min-width="140" show-overflow-tooltip />
        <el-table-column prop="operator_name" label="操作人" width="90" />
        <el-table-column prop="remark" label="备注" min-width="140" show-overflow-tooltip />
      </el-table>
      <template #footer>
        <el-button @click="showHistoryModal = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 库存预警列表 -->
    <el-dialog v-model="showWarningsModal" title="库存预警" width="820px">
      <el-table :data="warningList" stripe border size="small" max-height="460">
        <el-table-column prop="name" label="产品名称" min-width="140" show-overflow-tooltip />
        <el-table-column prop="model" label="型号" min-width="110" show-overflow-tooltip />
        <el-table-column label="当前库存" width="100">
          <template #default="{ row }">{{ formatNum(row.stock) }} {{ row.unit }}</template>
        </el-table-column>
        <el-table-column label="预警阈值" width="100">
          <template #default="{ row }">{{ formatNum(row.warn_threshold) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.stock_status === 'out' ? 'danger' : 'warning'" size="small">
              {{ row.stock_status === 'out' ? '缺货' : '预警' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="缺口" width="90">
          <template #default="{ row }">{{ row.shortage > 0 ? formatNum(row.shortage) : '-' }}</template>
        </el-table-column>
        <el-table-column prop="owner_name" label="负责人" width="90" />
      </el-table>
      <template #footer>
        <el-button @click="showWarningsModal = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { Plus, Warning } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const products = ref([])
const searchKeyword = ref('')
const filterCategory = ref('')
const filterStockStatus = ref('')

const showFormModal = ref(false)
const formRef = ref(null)
const showInventoryModal = ref(false)
const inventoryFormRef = ref(null)
const currentProduct = ref(null)
const showHistoryModal = ref(false)
const inventoryHistory = ref([])
const showWarningsModal = ref(false)
const warningList = ref([])

const isAdmin = computed(() => authStore.has('data.view_all'))

const categoryOptions = ref(['硬件', '软件', '服务', '耗材', '其它'])

const warningCount = computed(() => warningList.value.length)

const productForm = reactive({
  id: null,
  name: '',
  model: '',
  category: '',
  unit: '套',
  price: 0,
  cost: 0,
  stock: 0,
  warn_threshold: 0,
  description: '',
  owner_id: ''
})

const rules = {
  name: [{ required: true, message: '请输入产品名称', trigger: 'blur' }]
}

const inventoryForm = reactive({
  type: 'in',
  quantity: 1,
  reference: '',
  remark: '',
  unit: ''
})

const inventoryRules = {
  type: [{ required: true, message: '请选择操作类型', trigger: 'change' }],
  quantity: [{ required: true, message: '请输入数量', trigger: 'blur' }]
}

const formatNum = (v) => {
  const n = Number(v || 0)
  return Number.isInteger(n) ? String(n) : n.toFixed(2)
}

const stockClass = (row) => {
  return {
    'stock-out': row.stock_status === 'out',
    'stock-warning': row.stock_status === 'warning'
  }
}

const stockTagType = (status) => {
  if (status === 'out') return 'danger'
  if (status === 'warning') return 'warning'
  return 'success'
}

const stockStatusLabel = (status) => {
  if (status === 'out') return '缺货'
  if (status === 'warning') return '预警'
  return '正常'
}

const fetchProducts = async () => {
  const params = {}
  if (searchKeyword.value) params.keyword = searchKeyword.value
  if (filterCategory.value) params.category = filterCategory.value
  if (filterStockStatus.value) params.stock_status = filterStockStatus.value
  const resp = await api.get('/products', params)
  if (resp.code === 200) {
    products.value = resp.data
  }
}

const fetchWarnings = async () => {
  const resp = await api.get('/products/warnings')
  if (resp.code === 200) {
    warningList.value = resp.data
  }
}

const handleSearch = () => fetchProducts()

const resetForm = () => {
  Object.assign(productForm, {
    id: null, name: '', model: '', category: '', unit: '套',
    price: 0, cost: 0, stock: 0, warn_threshold: 0, description: '', owner_id: ''
  })
}

const openAddModal = () => {
  resetForm()
  showFormModal.value = true
}

const editProduct = (row) => {
  Object.assign(productForm, {
    id: row.id, name: row.name, model: row.model, category: row.category,
    unit: row.unit || '套', price: row.price || 0, cost: row.cost || 0,
    stock: row.stock || 0, warn_threshold: row.warn_threshold || 0,
    description: row.description || '', owner_id: row.owner_id || ''
  })
  showFormModal.value = true
}

const saveProduct = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      let resp
      if (productForm.id) {
        resp = await api.put(`/products/${productForm.id}`, productForm)
      } else {
        resp = await api.post('/products', productForm)
      }
      if (resp.code === 200) {
        ElMessage.success('保存成功')
        showFormModal.value = false
        fetchProducts()
        fetchWarnings()
      } else {
        ElMessage.error(resp.message)
      }
    } catch (e) {
      ElMessage.error('保存失败')
    }
  })
}

const deleteProduct = async (row) => {
  try {
    await ElMessageBox.confirm(`确定要删除产品「${row.name}」吗？相关出入库流水也会一并删除。`, '提示', { type: 'warning' })
    const resp = await api.delete(`/products/${row.id}`)
    if (resp.code === 200) {
      ElMessage.success('删除成功')
      fetchProducts()
      fetchWarnings()
    } else {
      ElMessage.error(resp.message)
    }
  } catch (e) {
    if (e !== 'cancel') ElMessage.info('已取消删除')
  }
}

const openInventoryModal = (row) => {
  currentProduct.value = row
  Object.assign(inventoryForm, { type: 'in', quantity: 1, reference: '', remark: '', unit: row.unit || '' })
  showInventoryModal.value = true
}

const saveInventory = async () => {
  if (!inventoryFormRef.value || !currentProduct.value) return
  await inventoryFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      const resp = await api.post(`/products/${currentProduct.value.id}/inventory`, {
        type: inventoryForm.type,
        quantity: inventoryForm.quantity,
        reference: inventoryForm.reference,
        remark: inventoryForm.remark
      })
      if (resp.code === 200) {
        ElMessage.success(resp.message)
        showInventoryModal.value = false
        fetchProducts()
        fetchWarnings()
      } else {
        ElMessage.error(resp.message)
      }
    } catch (e) {
      ElMessage.error('操作失败')
    }
  })
}

const openHistoryModal = async (row) => {
  currentProduct.value = row
  showHistoryModal.value = true
  const resp = await api.get(`/products/${row.id}/inventory`)
  if (resp.code === 200) {
    inventoryHistory.value = resp.data
  }
}

const openWarningsModal = () => {
  showWarningsModal.value = true
  fetchWarnings()
}

onMounted(() => {
  fetchProducts()
  fetchWarnings()
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
.stock-out {
  color: #f56c6c;
  font-weight: 600;
}
.stock-warning {
  color: #e6a23c;
  font-weight: 600;
}
.form-hint {
  margin-left: 8px;
  color: #94a3b8;
  font-size: 12px;
}
.current-stock {
  font-weight: 600;
  color: #4ecdc4;
}
.warn-badge {
  margin-left: 4px;
}
</style>
