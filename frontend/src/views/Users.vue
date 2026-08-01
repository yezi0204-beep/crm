<template>
  <div class="users">
    <div class="header-row">
      <el-button type="primary" @click="openAddModal" class="add-btn">
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
          <el-table-column prop="department" label="部门" min-width="100" sortable>
            <template #default="scope">
              <span>{{ scope.row.department || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="角色" min-width="180" sortable>
            <template #default="scope">
              <el-tag
                v-for="r in (scope.row.roles || [scope.row.role])"
                :key="r"
                :type="getRoleType(r)"
                size="small"
                style="margin-right: 4px;"
              >
                {{ r }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" min-width="90" sortable>
            <template #default="scope">
              <el-tag :type="scope.row.status === '离职' ? 'danger' : 'success'" size="small">
                {{ scope.row.status || '在职' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" min-width="200" fixed="right">
            <template #default="scope">
              <el-button size="small" @click="editUser(scope.row)">编辑</el-button>
              <el-button
                v-if="(scope.row.status || '在职') === '在职'"
                size="small"
                type="warning"
                @click="toggleStatus(scope.row, '离职')"
              >
                标记离职
              </el-button>
              <el-button
                v-else
                size="small"
                type="success"
                @click="toggleStatus(scope.row, '在职')"
              >
                恢复在职
              </el-button>
              <el-button size="small" type="danger" @click="deleteUser(scope.row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <el-dialog v-model="showAddModal" :title="userForm.username && isEditing ? '编辑用户' : '添加用户'" width="450px">
      <el-form :model="userForm" :rules="rules" ref="formRef">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="userForm.username" :disabled="isEditing" />
        </el-form-item>
        <el-form-item label="姓名" prop="name">
          <el-input v-model="userForm.name" />
        </el-form-item>
        <el-form-item label="部门" prop="department">
          <el-select v-model="userForm.department" placeholder="请选择部门" style="width: 100%">
            <el-option label="综合部" value="综合部" />
            <el-option label="经营层" value="经营层" />
            <el-option label="应用中心" value="应用中心" />
            <el-option label="技术中心" value="技术中心" />
          </el-select>
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="userForm.password" type="password" :placeholder="isEditing ? '留空则不修改密码' : ''" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="userForm.roles" multiple placeholder="请选择角色" style="width: 100%">
            <el-option label="主任" value="主任" />
            <el-option label="院长" value="院长" />
            <el-option label="销售" value="销售" />
            <el-option label="售前" value="售前" />
            <el-option label="技术研发" value="技术研发" />
            <el-option label="采购" value="采购" />
            <el-option label="项目经理" value="项目经理" />
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
const isEditing = ref(false)

const filteredUsers = computed(() => {
  if (!searchKeyword.value) return users.value
  const keyword = searchKeyword.value.toLowerCase()
  return users.value.filter(u =>
    (u.username && u.username.toLowerCase().includes(keyword)) ||
    (u.name && u.name.toLowerCase().includes(keyword))
  )
})

const handleSearch = () => {}

const openAddModal = () => {
  resetForm()
  showAddModal.value = true
}

const getRoleType = (role) => {
  const types = {
    '主任': 'danger',
    '院长': 'warning',
    '销售': 'info',
    '售前': 'success',
    '技术研发': 'primary',
    '采购': '',
    '项目经理': 'info'
  }
  return types[role] || 'info'
}

const userForm = reactive({
  username: '',
  name: '',
  department: '',
  password: '',
  roles: ['销售']
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  department: [{ required: true, message: '请选择部门', trigger: 'change' }],
  password: [{
    validator: (rule, value, callback) => {
      if (!isEditing.value && !value) {
        callback(new Error('请输入密码'))
      } else {
        callback()
      }
    },
    trigger: 'blur'
  }]
}

const resetForm = () => {
  Object.assign(userForm, {
    username: '',
    name: '',
    department: '',
    password: '',
    roles: ['销售']
  })
  isEditing.value = false
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
      if (!userForm.roles || userForm.roles.length === 0) {
        ElMessage.error('请至少选择一个角色')
        return
      }
      try {
        let response
        if (isEditing.value) {
          const updateData = {
            name: userForm.name,
            department: userForm.department,
            roles: userForm.roles
          }
          if (userForm.password) {
            updateData.password = userForm.password
          }
          response = await api.put(`/users/${userForm.username}`, updateData)
        } else {
          response = await api.post('/users', userForm)
        }
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
  Object.assign(userForm, {
    username: row.username,
    name: row.name,
    department: row.department || '',
    password: '',
    roles: row.roles ? [...row.roles] : [row.role]
  })
  isEditing.value = true
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

const toggleStatus = async (row, newStatus) => {
  const action = newStatus === '离职' ? '标记离职' : '恢复在职'
  const hint = newStatus === '离职'
    ? `确定要将「${row.name}」标记为离职吗？离职后该用户将无法登录系统，且不再出现在排班下拉列表中。历史记录仍会保留。`
    : `确定要将「${row.name}」恢复为在职吗？`

  try {
    await ElMessageBox.confirm(hint, action, {
      confirmButtonText: action,
      cancelButtonText: '取消',
      type: newStatus === '离职' ? 'warning' : 'success'
    })

    const response = await api.put(`/users/${row.username}/status`, { status: newStatus })
    if (response.code === 200) {
      ElMessage.success(response.message)
      fetchUsers()
    } else {
      ElMessage.error(response.message)
    }
  } catch {
    ElMessage.info('已取消')
  }
}

onMounted(() => {
  fetchUsers()
})
</script>

<style scoped>
</style>