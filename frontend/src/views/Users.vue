<template>
  <div class="users">
    <div class="header-row">
      <el-button type="primary" @click="showAddModal = true" class="add-btn">
        <el-icon><Plus /></el-icon>
        添加用户
      </el-button>
      <div class="search-wrapper">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索用户名、姓名..."
          class="search-input"
          clearable
          @keyup.enter="handleSearch"
        >
          <template #prefix>
            <span>🔍</span>
          </template>
        </el-input>
        <el-button @click="handleSearch" class="search-btn">搜索</el-button>
      </div>
    </div>
    
    <div class="table-container">
      <div class="table-wrapper">
        <el-table :data="filteredUsers" stripe border class="data-table">
          <el-table-column prop="username" label="用户名" min-width="120" sortable />
          <el-table-column prop="name" label="姓名" min-width="100" sortable />
          <el-table-column prop="role" label="角色" min-width="100" sortable>
            <template #default="scope">
              <el-tag :type="getRoleType(scope.row.role)" size="small">{{ scope.row.role }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" min-width="120" fixed="right">
            <template #default="scope">
              <el-button size="small" @click="editUser(scope.row)">编辑</el-button>
              <el-button size="small" type="danger" @click="deleteUser(scope.row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
    
    <el-dialog v-model="showAddModal" title="添加用户" width="400px">
      <el-form :model="userForm" :rules="rules" ref="formRef">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="userForm.username" />
        </el-form-item>
        <el-form-item label="姓名" prop="name">
          <el-input v-model="userForm.name" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="userForm.password" type="password" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="userForm.role">
            <el-option label="主任" value="主任" />
            <el-option label="院长" value="院长" />
            <el-option label="销售人员" value="销售人员" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddModal = false">取消</el-button>
        <el-button type="primary" @click="saveUser">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const users = ref([])
const showAddModal = ref(false)
const formRef = ref(null)
const searchKeyword = ref('')

const filteredUsers = computed(() => {
  if (!searchKeyword.value) return users.value
  const keyword = searchKeyword.value.toLowerCase()
  return users.value.filter(u => 
    (u.username && u.username.toLowerCase().includes(keyword)) ||
    (u.name && u.name.toLowerCase().includes(keyword))
  )
})

const handleSearch = () => {}

const getRoleType = (role) => {
  const types = {
    '主任': 'danger',
    '院长': 'warning',
    '销售人员': 'info'
  }
  return types[role] || 'info'
}

const userForm = reactive({
  id: null,
  username: '',
  name: '',
  password: '',
  role: '销售人员'
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

const fetchUsers = async () => {
  const response = await api.get('/users')
  if (response.code === 200) {
    users.value = response.data
  }
}

const saveUser = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (valid) {
      try {
        const response = await api.post('/users', userForm)
        if (response.code === 200) {
          ElMessage.success('保存成功')
          showAddModal.value = false
          fetchUsers()
        } else {
          ElMessage.error(response.message)
        }
      } catch (error) {
        ElMessage.error('保存失败')
      }
    }
  })
}

const editUser = (row) => {
  Object.assign(userForm, row)
  userForm.password = ''
  showAddModal.value = true
}

const deleteUser = async (row) => {
  try {
    await ElMessageBox.confirm('确定要删除这个用户吗？', '提示', {
      type: 'warning'
    })
    
    const response = await api.delete(`/users/${row.username}`)
    if (response.code === 200) {
      ElMessage.success('删除成功')
      fetchUsers()
    } else {
      ElMessage.error(response.message)
    }
  } catch (error) {
    ElMessage.info('已取消删除')
  }
}

onMounted(() => {
  fetchUsers()
})
</script>

<style scoped>
</style>