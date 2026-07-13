<template>
  <div class="business">
    <el-button type="primary" @click="showAddModal = true" class="add-btn">
      <el-icon><Plus /></el-icon>
      添加商机
    </el-button>
    
    <el-table :data="businessList" stripe border class="data-table">
      <el-table-column prop="title" label="商机名称" min-width="180" sortable />
      <el-table-column prop="customer_name" label="客户" width="150" sortable />
      <el-table-column prop="amount" label="金额(万)" width="120" sortable>
        <template #default="scope">
          {{ formatAmount(scope.row.amount) }}
        </template>
      </el-table-column>
      <el-table-column prop="stage" label="阶段" width="120" sortable>
        <template #default="scope">
          <el-tag :type="getStageType(scope.row.stage)" size="small">{{ scope.row.stage }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="predict_date" label="预计成交日期" width="150" sortable />
      <el-table-column prop="source" label="来源" width="120" sortable />
      <el-table-column prop="owner_name" label="负责人" width="100" sortable />
      <el-table-column prop="created_at" label="创建时间" width="150" sortable />
      <el-table-column label="操作" width="120">
        <template #default="scope">
          <el-button size="small" @click="editBusiness(scope.row)">编辑</el-button>
          <el-button size="small" type="danger" @click="deleteBusiness(scope.row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    
    <el-dialog v-model="showAddModal" title="添加商机" width="500px">
      <el-form :model="businessForm" :rules="rules" ref="formRef">
        <el-form-item label="商机名称" prop="title">
          <el-input v-model="businessForm.title" />
        </el-form-item>
        <el-form-item label="客户ID" prop="cust_id">
          <el-input v-model="businessForm.cust_id" />
        </el-form-item>
        <el-form-item label="金额(万)" prop="amount">
          <el-input-number v-model="businessForm.amount" :min="0" :step="0.01" />
        </el-form-item>
        <el-form-item label="阶段">
          <el-select v-model="businessForm.stage">
            <el-option label="初步接触" value="初步接触" />
            <el-option label="需求确认" value="需求确认" />
            <el-option label="方案报价" value="方案报价" />
            <el-option label="商务谈判" value="商务谈判" />
            <el-option label="赢单成交" value="赢单成交" />
          </el-select>
        </el-form-item>
        <el-form-item label="预计成交日期">
          <el-date-picker v-model="businessForm.predict_date" type="date" />
        </el-form-item>
        <el-form-item label="来源">
          <el-input v-model="businessForm.source" />
        </el-form-item>
        <el-form-item label="行业">
          <el-input v-model="businessForm.industry" />
        </el-form-item>
        <el-form-item label="地区">
          <el-input v-model="businessForm.region" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddModal = false">取消</el-button>
        <el-button type="primary" @click="saveBusiness">确定</el-button>
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
const businessList = ref([])
const showAddModal = ref(false)
const formRef = ref(null)

const businessForm = reactive({
  id: null,
  title: '',
  cust_id: '',
  amount: 0,
  stage: '初步接触',
  predict_date: '',
  source: '',
  industry: '',
  region: '',
  owner_id: ''
})

const rules = {
  title: [{ required: true, message: '请输入商机名称', trigger: 'blur' }],
  amount: [{ required: true, message: '请输入金额', trigger: 'blur' }]
}

const formatAmount = (value) => {
  return ((value || 0) / 10000).toFixed(2)
}

const getStageType = (stage) => {
  const types = {
    '初步接触': 'info',
    '需求确认': 'primary',
    '方案报价': 'warning',
    '商务谈判': 'danger',
    '赢单成交': 'success',
    '需求确认中': 'primary',
    '方案报价中': 'warning',
    '合同签署': 'danger',
    '项目启动': 'success',
    '实施中': 'success',
    '已完成': 'success'
  }
  return types[stage] || 'info'
}

const fetchBusiness = async () => {
  const response = await api.get('/business')
  if (response.code === 200) {
    businessList.value = response.data
  }
}

const saveBusiness = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (valid) {
      businessForm.amount = (businessForm.amount || 0) * 10000
      businessForm.owner_id = authStore.username
      
      try {
        const response = await api.post('/business', businessForm)
        if (response.code === 200) {
          ElMessage.success('保存成功')
          showAddModal.value = false
          fetchBusiness()
        } else {
          ElMessage.error(response.message)
        }
      } catch (error) {
        ElMessage.error('保存失败')
      }
    }
  })
}

const editBusiness = (row) => {
  Object.assign(businessForm, row)
  businessForm.amount = (row.amount || 0) / 10000
  showAddModal.value = true
}

const deleteBusiness = async (row) => {
  try {
    await ElMessageBox.confirm('确定要删除这个商机吗？', '提示', {
      type: 'warning'
    })
    
    const response = await api.delete(`/business/${row.id}`)
    if (response.code === 200) {
      ElMessage.success('删除成功')
      fetchBusiness()
    } else {
      ElMessage.error(response.message)
    }
  } catch (error) {
    ElMessage.info('已取消删除')
  }
}

onMounted(() => {
  fetchBusiness()
})
</script>

<style scoped>
.business {
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