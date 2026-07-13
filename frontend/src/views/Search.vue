<template>
  <div class="search-page">
    <div class="search-header">
      <div class="search-input-wrapper">
        <span class="search-icon">🔍</span>
        <input v-model="keyword" type="text" placeholder="搜索客户、商机、合同..." class="search-input" @keyup.enter="handleSearch">
        <button class="search-btn" @click="handleSearch">搜索</button>
      </div>
      <div class="search-filters">
        <el-tag v-for="filter in activeFilters" :key="filter" closable @close="removeFilter(filter)">{{ filter }}</el-tag>
      </div>
    </div>
    
    <div class="search-stats">
      <span>共找到 <strong>{{ totalResults }}</strong> 条结果</span>
    </div>
    
    <div class="search-tabs">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="全部" name="all"></el-tab-pane>
        <el-tab-pane label="客户" name="customers"></el-tab-pane>
        <el-tab-pane label="商机" name="business"></el-tab-pane>
        <el-tab-pane label="合同" name="contracts"></el-tab-pane>
      </el-tabs>
    </div>
    
    <div class="search-results">
      <div v-if="activeTab === 'customers' || activeTab === 'all'" class="result-section">
        <h3>👥 客户 ({{ customerResults.length }})</h3>
        <div v-if="customerResults.length > 0" class="result-list">
          <div v-for="item in customerResults" :key="item.id" class="result-item" @click="goToDetail('customers', item.id)">
            <div class="result-icon">👤</div>
            <div class="result-content">
              <div class="result-title">{{ item.name }}</div>
              <div class="result-subtitle">{{ item.company }} | {{ item.phone }} | {{ item.level }}</div>
            </div>
          </div>
        </div>
        <p v-else class="no-results">暂无客户结果</p>
      </div>
      
      <div v-if="activeTab === 'business' || activeTab === 'all'" class="result-section">
        <h3>🎯 商机 ({{ businessResults.length }})</h3>
        <div v-if="businessResults.length > 0" class="result-list">
          <div v-for="item in businessResults" :key="item.id" class="result-item" @click="goToDetail('business', item.id)">
            <div class="result-icon">🎯</div>
            <div class="result-content">
              <div class="result-title">{{ item.title }}</div>
              <div class="result-subtitle">{{ item.amount }}元 | {{ item.stage }} | {{ item.source }}</div>
            </div>
          </div>
        </div>
        <p v-else class="no-results">暂无商机结果</p>
      </div>
      
      <div v-if="activeTab === 'contracts' || activeTab === 'all'" class="result-section">
        <h3>📜 合同 ({{ contractResults.length }})</h3>
        <div v-if="contractResults.length > 0" class="result-list">
          <div v-for="item in contractResults" :key="item.id" class="result-item" @click="goToDetail('contracts', item.id)">
            <div class="result-icon">📄</div>
            <div class="result-content">
              <div class="result-title">{{ item.contract_name }}</div>
              <div class="result-subtitle">{{ item.contract_no }} | {{ item.total_amt }}元 | {{ item.sign_date }}</div>
            </div>
          </div>
        </div>
        <p v-else class="no-results">暂无合同结果</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import api from '../api'

const router = useRouter()
const route = useRoute()

const keyword = ref('')
const activeTab = ref('all')
const activeFilters = ref([])

const customerResults = ref([])
const businessResults = ref([])
const contractResults = ref([])

const totalResults = computed(() => {
  return customerResults.value.length + businessResults.value.length + contractResults.value.length
})

const handleSearch = async () => {
  if (!keyword.value.trim()) return
  
  const response = await api.get('/search', { params: { keyword: keyword.value } })
  if (response.code === 200) {
    customerResults.value = response.data.customers || []
    businessResults.value = response.data.business || []
    contractResults.value = response.data.contracts || []
  }
}

const removeFilter = (filter) => {
  const index = activeFilters.value.indexOf(filter)
  if (index > -1) {
    activeFilters.value.splice(index, 1)
  }
}

const goToDetail = (type, id) => {
  router.push(`/${type}/${id}`)
}

onMounted(() => {
  const params = new URLSearchParams(route.query)
  const kw = params.get('keyword')
  if (kw) {
    keyword.value = kw
    handleSearch()
  }
})
</script>

<style scoped>
.search-page {
  max-width: 900px;
  margin: 0 auto;
}

.search-header {
  margin-bottom: 24px;
}

.search-input-wrapper {
  display: flex;
  align-items: center;
  background: white;
  border-radius: 12px;
  padding: 16px 24px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.search-icon {
  font-size: 20px;
  margin-right: 12px;
  color: #999;
}

.search-input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 16px;
}

.search-btn {
  background: linear-gradient(135deg, #4ecdc4 0%, #44a08d 100%);
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}

.search-filters {
  display: flex;
  gap: 8px;
  margin-top: 16px;
}

.search-stats {
  font-size: 14px;
  color: #999;
  margin-bottom: 16px;
}

.search-tabs {
  margin-bottom: 24px;
}

.search-results {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.result-section h3 {
  font-size: 16px;
  color: #333;
  margin-bottom: 12px;
}

.result-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.result-item {
  display: flex;
  align-items: center;
  gap: 16px;
  background: white;
  padding: 16px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.result-item:hover {
  transform: translateX(4px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
}

.result-icon {
  font-size: 28px;
}

.result-content {
  flex: 1;
}

.result-title {
  font-size: 15px;
  font-weight: 600;
  color: #333;
}

.result-subtitle {
  font-size: 13px;
  color: #999;
  margin-top: 4px;
}

.no-results {
  color: #999;
  font-size: 14px;
  padding: 24px;
  text-align: center;
  background: rgba(0, 0, 0, 0.02);
  border-radius: 8px;
}
</style>