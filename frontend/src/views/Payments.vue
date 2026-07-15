<template>
  <div class="payments">
    <div class="header-row">
      <el-button type="primary" @click="showAddModal = true" class="add-btn">
        <el-icon><Plus /></el-icon>
        添加回款记录
      </el-button>
      
      <div class="search-wrapper">
        <el-input 
          v-model="searchKeyword" 
          placeholder="搜索合同名称、编号、甲方..." 
          clearable
          style="width: 300px;"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
      </div>
    </div>
    
    <el-table :data="paymentRecords" stripe border class="data-table">
      <el-table-column prop="contract_name" label="合同名称" min-width="180" sortable />
      <el-table-column prop="contract_no" label="合同编号" width="150" sortable />
      <el-table-column prop="payment_date" label="回款日期" width="130" sortable />
      <el-table-column prop="amount" label="金额(万)" width="120" sortable>
        <template #default="scope">
          {{ formatAmount(scope.row.amount) }}
        </template>
      </el-table-column>
      <el-table-column prop="owner_name" label="负责人" width="100" sortable />
      <el-table-column prop="note" label="备注" />
      <el-table-column prop="created_at" label="创建时间" width="150" sortable />
      <el-table-column label="操作" width="120">
        <template #default="scope">
          <el-button size="small" @click="editPayment(scope.row)">编辑</el-button>
          <el-button size="small" type="danger" @click="deletePayment(scope.row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    
    <el-dialog v-model="showAddModal" title="添加回款记录" width="500px">
      <el-form :model="paymentForm" :rules="rules" ref="formRef">
        <el-form-item label="选择合同" prop="contract_id">
          <el-select 
            v-model="paymentForm.contract_id" 
            placeholder="请选择合同" 
            filterable
            style="width: 100%;"
          >
            <el-option 
              v-for="contract in contracts" 
              :key="contract.id" 
              :label="`${contract.contract_name} (${contract.contract_no}) - ${contract.party_a}`" 
              :value="contract.id" 
            />
          </el-select>
        </el-form-item>
        <el-form-item label="回款日期" prop="payment_date">
          <el-date-picker v-model="paymentForm.payment_date" type="date" />
        </el-form-item>
        <el-form-item label="金额(万)" prop="amount">
          <el-input-number v-model="paymentForm.amount" :min="0" :step="0.01" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="paymentForm.note" type="textarea" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddModal = false">取消</el-button>
        <el-button type="primary" @click="savePayment">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { Plus, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const allPaymentRecords = ref([])
const contracts = ref([])
const showAddModal = ref(false)
const formRef = ref(null)
const searchKeyword = ref('')

const paymentForm = reactive({
  id: null,
  contract_id: '',
  payment_date: '',
  amount: 0,
  note: ''
})

const rules = {
  contract_id: [{ required: true, message: '请选择合同', trigger: 'blur' }],
  amount: [{ required: true, message: '请输入金额', trigger: 'blur' }]
}

const formatAmount = (value) => {
  return ((value || 0) / 10000).toFixed(2)
}

const paymentRecords = computed(() => {
  console.log('searchKeyword:', searchKeyword.value, 'allRecords:', allPaymentRecords.value.length)
  
  if (!searchKeyword.value) {
    return allPaymentRecords.value
  }
  
  const keyword = searchKeyword.value.toLowerCase()
  const filtered = allPaymentRecords.value.filter(record => {
    return (
      (record.contract_name && record.contract_name.toLowerCase().includes(keyword)) ||
      (record.contract_no && record.contract_no.toLowerCase().includes(keyword)) ||
      (record.party_a && record.party_a.toLowerCase().includes(keyword)) ||
      (record.owner_name && record.owner_name.toLowerCase().includes(keyword)) ||
      (record.note && record.note.toLowerCase().includes(keyword))
    )
  })
  console.log('filtered count:', filtered.length)
  return filtered
})

const fetchPayments = async () => {
  const response = await api.get('/payment_records')
  if (response.code === 200) {
    allPaymentRecords.value = response.data
  }
}

const fetchContracts = async () => {
  const response = await api.get('/contracts')
  if (response.code === 200) {
    contracts.value = response.data
  }
}

const filterContracts = (query, item) => {
  if (!query) return true
  const q = query.toLowerCase()
  const contract = item
  return (
    (contract.contract_name && contract.contract_name.toLowerCase().includes(q)) ||
    (contract.contract_no && contract.contract_no.toLowerCase().includes(q)) ||
    (contract.party_a && contract.party_a.toLowerCase().includes(q))
  )
}

const savePayment = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (valid) {
      paymentForm.amount = (paymentForm.amount || 0) * 10000
      
      try {
        const response = await api.post('/payment_records', paymentForm)
        if (response.code === 200) {
          ElMessage.success('保存成功')
          showAddModal.value = false
          fetchPayments()
        } else {
          ElMessage.error(response.message)
        }
      } catch (error) {
        ElMessage.error('保存失败')
      }
    }
  })
}

const editPayment = (row) => {
  Object.assign(paymentForm, row)
  paymentForm.amount = (row.amount || 0) / 10000
  showAddModal.value = true
}

const deletePayment = async (row) => {
  try {
    await ElMessageBox.confirm('确定要删除这个回款记录吗？', '提示', {
      type: 'warning'
    })
    
    const response = await api.delete(`/payment_records/${row.id}`)
    if (response.code === 200) {
      ElMessage.success('删除成功')
      fetchPayments()
    } else {
      ElMessage.error(response.message)
    }
  } catch (error) {
    ElMessage.info('已取消删除')
  }
}

onMounted(() => {
  fetchPayments()
  fetchContracts()
})
</script>

<style scoped>
.payments {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.header-row {
  display: flex;
  align-items: center;
  gap: 16px;
}

.add-btn {
  align-self: flex-start;
}

.search-wrapper {
  margin-left: auto;
}

.data-table {
  width: 100%;
}
</style>