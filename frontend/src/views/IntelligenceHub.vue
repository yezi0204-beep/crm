<template>
  <div class="intel-hub">
    <el-tabs v-model="activeTab" class="hub-tabs">
      <el-tab-pane v-if="canViewIntel" label="📡 原始情报" name="intel">
        <Intelligence />
      </el-tab-pane>
      <el-tab-pane v-if="canViewLeads" label="🎯 AI商机识别" name="ai-leads">
        <IntelligenceLeads />
      </el-tab-pane>
      <el-tab-pane v-if="canViewLeads" label="📋 智能线索" name="leads">
        <Leads />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import Intelligence from './Intelligence.vue'
import IntelligenceLeads from './IntelligenceLeads.vue'
import Leads from './Leads.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const canViewIntel = computed(() => authStore.has('intel.view'))
const canViewLeads = computed(() => authStore.has('intel.leads'))

const activeTab = ref('')

// 按 URL query ?tab= 定位标签页，默认主任看情报、应用中心看线索
function resolveTab() {
  const q = String(route.query.tab || '')
  if (q === 'ai-leads' && canViewLeads.value) return 'ai-leads'
  if (q === 'leads' && canViewLeads.value) return 'leads'
  if (q === 'intel' && canViewIntel.value) return 'intel'
  return canViewIntel.value ? 'intel' : (canViewLeads.value ? 'ai-leads' : '')
}
activeTab.value = resolveTab()

watch(() => route.query.tab, () => {
  // 离开 intelligence 页面时不干预 tab，避免阻止路由跳转
  if (route.path !== '/intelligence') return
  const t = resolveTab()
  if (t) activeTab.value = t
})

// 切换标签页时同步 URL，便于分享/刷新定位
watch(activeTab, (t) => {
  if (!t) return
  // 仅在当前处于 intelligence 页面时同步 URL，避免离开时把路由拉回
  if (route.path !== '/intelligence') return
  if (t !== route.query.tab) {
    router.replace({ path: '/intelligence', query: { tab: t } })
  }
})
</script>

<style scoped>
.intel-hub :deep(.el-tabs__header) {
  margin-bottom: 12px;
}
.intel-hub :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
}
.intel-hub :deep(.el-tabs__item) {
  font-size: 15px;
  font-weight: 600;
}
</style>
