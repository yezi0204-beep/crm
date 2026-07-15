<template>
  <div class="customers">
    <el-button type="primary" @click="showAddModal = true" class="add-btn">
      <el-icon><Plus /></el-icon>
      添加客户
    </el-button>
    
    <el-table :data="customers" stripe border class="data-table">
      <el-table-column prop="name" label="联系人" width="120" sortable />
      <el-table-column prop="phone" label="手机号" width="130" sortable />
      <el-table-column prop="company" label="公司名称" min-width="180" sortable />
      <el-table-column prop="level" label="客户等级" width="100" sortable>
        <template #default="scope">
          <el-tag :type="getLevelType(scope.row.level)" size="small">{{ scope.row.level }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="source" label="来源" width="120" sortable />
      <el-table-column prop="owner_name" label="负责人" width="100" sortable />
      <el-table-column prop="last_follow" label="最后跟进时间" width="150" sortable />
      <el-table-column prop="created_at" label="创建时间" width="150" sortable />
      <el-table-column label="操作" width="120">
        <template #default="scope">
          <el-button size="small" @click="editCustomer(scope.row)">编辑</el-button>
          <el-button size="small" type="danger" @click="deleteCustomer(scope.row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    
    <el-dialog v-model="showAddModal" :title="customerForm.id ? '编辑客户' : '添加客户'" width="500px">
      <el-form :model="customerForm" :rules="rules" ref="formRef">
        <el-form-item label="联系人" prop="name">
          <el-input v-model="customerForm.name" />
        </el-form-item>
        <el-form-item label="手机号" prop="phone">
          <el-input v-model="customerForm.phone" />
        </el-form-item>
        <el-form-item label="公司名称" prop="company">
          <el-input v-model="customerForm.company" />
        </el-form-item>
        <el-form-item label="客户等级">
          <el-select v-model="customerForm.level">
            <el-option label="A" value="A" />
            <el-option label="B" value="B" />
            <el-option label="C" value="C" />
          </el-select>
        </el-form-item>
        <el-form-item label="来源">
          <el-input v-model="customerForm.source" />
        </el-form-item>
        <el-form-item label="负责人">
          <el-input v-model="customerForm.owner_id" :disabled="true" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddModal = false">取消</el-button>
        <el-button type="primary" @click="saveCustomer">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const customers = ref([])
const showAddModal = ref(false)
const formRef = ref(null)

const customerForm = reactive({
  id: null,
  name: '',
  phone: '',
  company: '',
  level: 'B',
  source: '',
  owner_id: '',
  last_follow: '',
  created_at: ''
})

const rules = {
  name: [{ required: true, message: '请输入联系人', trigger: 'blur' }],
  phone: [{ required: true, message: '请输入手机号', trigger: 'blur' }],
  company: [{ required: true, message: '请输入公司名称', trigger: 'blur' }]
}

const getLevelType = (level) => {
  const types = {
    'A': 'danger',
    'B': 'warning',
    'C': 'info'
  }
  return types[level] || 'info'
}

const fetchCustomers = async () => {
  const response = await api.get('/customers')
  if (response.code === 200) {
    customers.value = response.data
  }
}

const saveCustomer = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (valid) {
      if (!customerForm.id) {
        customerForm.owner_id = authStore.username
      }
      
      try {
        let response
        if (customerForm.id) {
          response = await api.put(`/customers/${customerForm.id}`, customerForm)
        } else {
          response = await api.post('/customers', customerForm)
        }
        if (response.code === 200) {
          ElMessage.success('保存成功')
          showAddModal.value = false
          fetchCustomers()
        } else {
          ElMessage.error(response.message)
        }
      } catch (error) {
        ElMessage.error('保存失败')
      }
    }
  })
}

const editCustomer = (row) => {
  Object.assign(customerForm, row)
  showAddModal.value = true
}

const deleteCustomer = async (row) => {
  try {
    await ElMessageBox.confirm('确定要删除这个客户吗？', '提示', {
      type: 'warning'
    })
    
    const response = await api.delete(`/customers/${row.id}`)
    if (response.code === 200) {
      ElMessage.success('删除成功')
      fetchCustomers()
    } else {
      ElMessage.error(response.message)
    }
  } catch (error) {
    ElMessage.info('已取消删除')
  }
}

onMounted(() => {
  fetchCustomers()
})
</script>

<style scoped>
.customers {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.add-btn {
  align-self: flex-start;
}

.data-table {
  width: 100%;
}
</style>