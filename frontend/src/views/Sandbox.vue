<template>
  <div class="sandbox-page">
    <!-- 顶部作战指标栏 -->
    <div class="sandbox-header">
      <div class="header-title">
        <span class="title-icon">🎖️</span>
        <span class="title-text">营销作战沙盘</span>
        <span class="title-sub">MAP · SITUATION AWARENESS</span>
      </div>
      <div class="header-stats">
        <div class="stat-chip">
          <div class="stat-num">{{ summary.customer_total || 0 }}</div>
          <div class="stat-label">客户总数</div>
        </div>
        <div class="stat-chip located">
          <div class="stat-num">{{ summary.located_total || 0 }}</div>
          <div class="stat-label">已定位</div>
        </div>
        <div class="stat-chip">
          <div class="stat-num">{{ summary.biz_total || 0 }}</div>
          <div class="stat-label">在途商机</div>
        </div>
        <div class="stat-chip amount">
          <div class="stat-num">¥{{ fmtAmount(summary.biz_amount) }}</div>
          <div class="stat-label">商机总额</div>
        </div>
        <div class="stat-chip visit">
          <div class="stat-num">{{ summary.week_visit_total || 0 }}</div>
          <div class="stat-label">本周拜访</div>
        </div>
        <div class="stat-chip">
          <div class="stat-num">{{ summary.salesman_total || 0 }}</div>
          <div class="stat-label">作战人员</div>
        </div>
      </div>
    </div>

    <!-- 主体：地图 + 右侧作战面板 -->
    <div class="sandbox-body">
      <div class="map-wrap">
        <div ref="chartRef" class="map-chart"></div>
        <div class="map-legend">
          <span class="lg-item"><i class="dot cyan"></i>客户阵地（大小=商机金额）</span>
          <span class="lg-item"><i class="dot pulse"></i>重点战区</span>
          <span class="lg-item"><i class="dot orange"></i>📍人员位置（最近拜访推断）</span>
        </div>
        <div class="map-tip" v-if="!selectedCity && !selectedCustomer">点击地图圆点查看城市客户 / 人员分布</div>
        <el-button v-if="selectedCity || selectedCustomer" class="back-btn" size="small" round @click="clearSelect">
          ← 返回全景
        </el-button>
      </div>

      <!-- 右侧作战面板 -->
      <div class="side-panel">
        <!-- 全景概览 -->
        <div v-if="!selectedCity && !selectedCustomer" class="panel-section">
          <div class="panel-title">📊 战区排行（TOP 10）</div>
          <div class="rank-list">
            <div v-for="(c, i) in topCities" :key="c.name" class="rank-item" @click="selectCity(c.name)">
              <span class="rank-no" :class="'no' + (i + 1)">{{ i + 1 }}</span>
              <span class="rank-city">{{ c.name }}</span>
              <span class="rank-meta">{{ c.custCount }}客户 · {{ c.bizCount }}商机</span>
              <span class="rank-amt">¥{{ fmtAmount(c.bizAmount) }}</span>
            </div>
            <div v-if="!topCities.length" class="empty-hint">暂无已定位客户，请在「未定位客户」中补录城市</div>
          </div>
          <div class="panel-title mt">⚔️ 人员战力</div>
          <div class="rank-list">
            <div v-for="s in salesmen" :key="s.username" class="rank-item man" @click="selectSalesman(s)">
              <span class="man-name">{{ s.name }}</span>
              <span class="man-pos">{{ s.position ? '📍' + s.position.city : '—' }}</span>
              <span class="rank-meta">{{ s.customer_count }}客户 · {{ s.biz_count }}商机</span>
              <span class="rank-amt">¥{{ fmtAmount(s.biz_amount) }}</span>
            </div>
          </div>
        </div>

        <!-- 城市客户列表 -->
        <div v-else-if="selectedCity && !selectedCustomer" class="panel-section">
          <div class="panel-title">🎯 {{ selectedCity }} · {{ cityCustomers.length }}个客户</div>
          <div class="cust-list">
            <div v-for="c in cityCustomers" :key="c.id" class="cust-item" @click="selectCustomer(c)">
              <div class="cust-head">
                <span class="cust-name">{{ c.name }}</span>
                <el-tag v-if="isKeyLevel(c.level)" type="danger" size="small" effect="dark">重点</el-tag>
                <span class="cust-amt">¥{{ fmtAmount(c.biz_amount) }}</span>
              </div>
              <div class="cust-meta">
                负责人 {{ c.owner_name }} · {{ c.biz_count }}商机 · {{ c.visit_count }}次拜访
                <span v-if="c.last_visit"> · 最近 {{ c.last_visit }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 客户作战详情 -->
        <div v-else class="panel-section">
          <div class="panel-title">
            <el-link class="back-link" :underline="false" @click="selectedCustomer = null">← </el-link>
            🏠 {{ selectedCustomer.name }}
          </div>
          <div class="cust-tags">
            <el-tag size="small" type="warning" effect="plain">{{ selectedCustomer.level || '未分级' }}</el-tag>
            <el-tag size="small" effect="plain">负责人：{{ selectedCustomer.owner_name }}</el-tag>
            <el-tag v-if="selectedCustomer.city" size="small" type="success" effect="plain">{{ selectedCustomer.city }}</el-tag>
          </div>

          <div class="detail-block">
            <div class="block-title">👥 干系人（{{ selectedCustomer.stakeholders.length }}）</div>
            <div class="stk-list">
              <el-tag v-for="(s, i) in selectedCustomer.stakeholders" :key="i" class="stk-tag"
                      :type="s.source === '客户联系人' ? 'danger' : (s.source === '商机干系人' ? 'warning' : 'info')"
                      effect="light">
                {{ s.name }} · {{ s.source }}
              </el-tag>
              <span v-if="!selectedCustomer.stakeholders.length" class="empty-hint">暂无干系人记录</span>
            </div>
          </div>

          <div class="detail-block">
            <div class="block-title">🎯 商机情况（{{ selectedCustomer.biz_list.length }}个在途）</div>
            <div class="biz-list">
              <div v-for="b in selectedCustomer.biz_list" :key="b.id" class="biz-item">
                <div class="biz-row">
                  <span class="biz-title">{{ b.title }}</span>
                  <span class="biz-amt">¥{{ fmtAmount(b.amount) }}</span>
                </div>
                <div class="biz-meta">
                  <el-tag size="small" effect="dark" type="primary">{{ b.stage || '未定阶段' }}</el-tag>
                  <span v-if="b.stakeholder">干系人：{{ b.stakeholder }}</span>
                </div>
              </div>
              <div v-if="!selectedCustomer.biz_list.length" class="empty-hint">暂无在途商机</div>
            </div>
          </div>

          <div class="detail-block">
            <div class="block-title">📅 拜访概要（最近{{ selectedCustomer.visits.length }}条）</div>
            <el-timeline class="visit-timeline">
              <el-timeline-item v-for="(v, i) in selectedCustomer.visits" :key="i"
                                :type="visitDotType(v.status)" :timestamp="v.plan_date" placement="top">
                <div class="visit-line">
                  <span class="visit-status" :class="v.status">{{ visitStatusText(v.status) }}</span>
                  <span class="visit-purpose">{{ v.purpose || '拜访沟通' }}</span>
                </div>
                <div class="visit-meta">{{ v.visitor_name }}<span v-if="v.contact_person"> · 会见 {{ v.contact_person }}</span></div>
              </el-timeline-item>
            </el-timeline>
            <div v-if="!selectedCustomer.visits.length" class="empty-hint">暂无拜访记录</div>
          </div>
        </div>

        <!-- 未定位客户管理 -->
        <div class="unlocated-bar" @click="unlocatedVisible = true">
          ⚠️ 未定位客户 {{ unlocated.length }} 个 → 前往补录
        </div>
      </div>
    </div>

    <!-- 未定位客户补录抽屉 -->
    <el-drawer v-model="unlocatedVisible" title="未定位客户补录" size="440px" class="unlocated-drawer">
      <div class="drawer-hint">为没有城市信息的客户选择所在城市，保存后立即上图。</div>
      <div v-for="c in unlocated" :key="c.id" class="unloc-item">
        <div class="unloc-info">
          <div class="unloc-name">{{ c.name }}</div>
          <div class="unloc-meta">负责人 {{ c.owner_name }} · {{ c.biz_count }}商机 · ¥{{ fmtAmount(c.biz_amount) }}</div>
        </div>
        <el-cascader v-model="c._cityPick" :options="cityOptions" :props="{ label: 'label', value: 'value' }"
                     placeholder="选择城市" filterable size="small" class="unloc-pick" @change="val => setCity(c, val)" />
      </div>
      <div v-if="!unlocated.length" class="empty-hint" style="text-align:center;padding:40px 0">
        🎉 全部客户已定位
      </div>
    </el-drawer>

    <!-- 人员详情抽屉 -->
    <el-drawer v-model="salesmanVisible" :title="'👤 ' + (activeSalesman?.name || '') + ' · 作战档案'" size="440px">
      <template v-if="activeSalesman">
        <div class="man-brief">
          <el-tag effect="plain">{{ activeSalesman.role }}</el-tag>
          <el-tag effect="plain" type="info">{{ activeSalesman.department }}</el-tag>
          <el-tag effect="plain" :type="activeSalesman.position ? 'success' : 'info'">
            📍 {{ activeSalesman.position ? activeSalesman.position.city + '（' + activeSalesman.position.visit_date + ' 拜访' + activeSalesman.position.from_customer + '）' : '暂无位置推断' }}
          </el-tag>
        </div>
        <div class="man-numbers">
          <div class="mn-item"><div class="mn-num">{{ activeSalesman.customer_count }}</div><div class="mn-label">名下客户</div></div>
          <div class="mn-item"><div class="mn-num">{{ activeSalesman.biz_count }}</div><div class="mn-label">在途商机</div></div>
          <div class="mn-item"><div class="mn-num mn-amt">¥{{ fmtAmount(activeSalesman.biz_amount) }}</div><div class="mn-label">商机总额</div></div>
        </div>
        <div class="panel-title mt">名下已定位客户</div>
        <div class="cust-list">
          <div v-for="c in salesmanCustomers" :key="c.id" class="cust-item" @click="openCustomerFromDrawer(c)">
            <div class="cust-head">
              <span class="cust-name">{{ c.name }} <el-tag v-if="c.city" size="small" type="success" effect="plain">{{ c.city }}</el-tag></span>
              <span class="cust-amt">¥{{ fmtAmount(c.biz_amount) }}</span>
            </div>
            <div class="cust-meta">{{ c.biz_count }}商机 · {{ c.visit_count }}次拜访</div>
          </div>
          <div v-if="!salesmanCustomers.length" class="empty-hint">暂无已定位客户</div>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import chinaJson from '../assets/china.json'
import api from '../api'

echarts.registerMap('china', chinaJson)

const chartRef = ref(null)
let chart = null

const summary = ref({})
const customers = ref([])   // 已定位客户
const unlocated = ref([])   // 未定位客户
const salesmen = ref([])
const cityOptions = ref([])

const selectedCity = ref(null)
const selectedCustomer = ref(null)
const unlocatedVisible = ref(false)
const salesmanVisible = ref(false)
const activeSalesman = ref(null)

const fmtAmount = (v) => {
  const n = Number(v || 0)
  if (n >= 100000000) return (n / 100000000).toFixed(2) + '亿'
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  return n.toFixed(2)
}

const isKeyLevel = (level) => (level || '').includes('A')

const visitStatusText = (s) => ({ planned: '计划', completed: '已完成', cancelled: '已取消', overdue: '已过期' }[s] || s)
const visitDotType = (s) => ({ planned: 'primary', completed: 'success', cancelled: 'info', overdue: 'danger' }[s] || 'primary')

// 城市聚合
const cityAgg = computed(() => {
  const map = {}
  for (const c of customers.value) {
    if (!c.city) continue
    if (!map[c.city]) map[c.city] = { name: c.city, lng: c.lng, lat: c.lat, custCount: 0, bizCount: 0, bizAmount: 0, customers: [] }
    map[c.city].custCount++
    map[c.city].bizCount += c.biz_count
    map[c.city].bizAmount += c.biz_amount
    map[c.city].customers.push(c)
  }
  return Object.values(map).sort((a, b) => b.bizAmount - a.bizAmount)
})
const topCities = computed(() => cityAgg.value.slice(0, 10))
const cityCustomers = computed(() => {
  const agg = cityAgg.value.find(x => x.name === selectedCity.value)
  return agg ? agg.customers : []
})
const salesmanCustomers = computed(() => {
  if (!activeSalesman.value) return []
  const uid = activeSalesman.value.username
  return customers.value.filter(c => c.owner_id === uid)
})

const loadData = async () => {
  try {
    const [dataRes, cityRes] = await Promise.all([
      api.get('/sandbox/data'),
      api.get('/sandbox/cities')
    ])
    summary.value = dataRes.data?.summary || {}
    customers.value = dataRes.data?.customers || []
    salesmen.value = dataRes.data?.salesmen || []
    unlocated.value = (dataRes.data?.unlocated || []).map(c => ({ ...c, _cityPick: null }))
    const groups = cityRes.data || {}
    cityOptions.value = Object.entries(groups).map(([prov, cities]) => ({
      label: prov,
      value: prov,
      children: cities.map(ct => ({ label: ct, value: ct }))
    }))
    renderChart()
  } catch (e) {
    ElMessage.error('沙盘数据加载失败：' + (e.response?.data?.message || e.message))
  }
}

const renderChart = () => {
  if (!chartRef.value) return
  if (!chart) chart = echarts.init(chartRef.value)
  const cityData = cityAgg.value.map(c => ({
    name: c.name,
    value: [c.lng, c.lat, c.custCount, c.bizCount, c.bizAmount]
  }))
  const topNames = cityAgg.value.slice(0, 5).map(c => c.name)
  const manData = salesmen.value.filter(s => s.position)
    .map(s => ({
      name: s.name,
      value: [s.position.lng, s.position.lat, s.position.city],
      username: s.username
    }))
  const maxAmt = Math.max(...cityAgg.value.map(c => c.bizAmount), 1)

  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(8,25,50,.92)',
      borderColor: '#1d5a8f',
      textStyle: { color: '#d8ecff', fontSize: 12 },
      formatter: (p) => {
        if (p.seriesType === 'cityScatter' || p.seriesName === '客户阵地') {
          return `<b>${p.name}</b><br/>客户 ${p.value[2]} 家 · 在途商机 ${p.value[3]} 个<br/>商机总额 ¥${fmtAmount(p.value[4])}<br/><span style="color:#5fa8e0">点击查看详情</span>`
        }
        if (p.seriesName === '人员位置') {
          return `<b>📍 ${p.name}</b><br/>当前推断位置：${p.value[2]}<br/>点击查看作战档案`
        }
        return p.name
      }
    },
    geo: {
      map: 'china',
      roam: true,
      zoom: 1.15,
      center: [104.5, 36.5],
      label: { show: false },
      itemStyle: {
        areaColor: '#0e2138',
        borderColor: '#2b567f',
        borderWidth: 1,
        shadowColor: 'rgba(0,80,160,.5)',
        shadowBlur: 12
      },
      emphasis: {
        label: { show: false },
        itemStyle: { areaColor: '#1a3a5f' }
      },
      select: { disabled: true }
    },
    series: [
      {
        name: '客户阵地',
        type: 'scatter',
        coordinateSystem: 'geo',
        data: cityData,
        symbolSize: (val) => 8 + Math.sqrt(val[4] / maxAmt) * 26,
        itemStyle: {
          color: '#27c2ff',
          shadowColor: 'rgba(39,194,255,.8)',
          shadowBlur: 10,
          borderColor: '#fff',
          borderWidth: 1
        },
        emphasis: { scale: 1.6 },
        zlevel: 2
      },
      {
        name: '重点战区',
        type: 'effectScatter',
        coordinateSystem: 'geo',
        data: cityData.filter(d => topNames.includes(d.name)),
        symbolSize: (val) => 10 + Math.sqrt(val[4] / maxAmt) * 24,
        rippleEffect: { brushType: 'stroke', scale: 3 },
        itemStyle: { color: '#ffd04b', shadowColor: 'rgba(255,208,75,.9)', shadowBlur: 12 },
        label: { show: true, formatter: '{b}', position: 'right', color: '#9fd6ff', fontSize: 11 },
        zlevel: 3
      },
      {
        name: '人员位置',
        type: 'scatter',
        coordinateSystem: 'geo',
        data: manData,
        symbol: 'pin',
        symbolSize: 20,
        itemStyle: { color: '#ff7a2f', shadowColor: 'rgba(255,122,47,.9)', shadowBlur: 10, borderColor: '#fff', borderWidth: 1 },
        label: { show: true, formatter: (p) => p.name, position: 'bottom', color: '#ffb27d', fontSize: 11 },
        zlevel: 4
      }
    ]
  })

  chart.off('click')
  chart.on('click', (p) => {
    if (p.seriesName === '人员位置') {
      const s = salesmen.value.find(x => x.name === p.name)
      if (s) selectSalesman(s)
    } else if (p.seriesName === '客户阵地' || p.seriesName === '重点战区') {
      selectCity(p.name)
    }
  })
}

const selectCity = (city) => {
  selectedCustomer.value = null
  selectedCity.value = city
  highlightCity(city)
}
const selectCustomer = (c) => { selectedCustomer.value = c }
const openCustomerFromDrawer = (c) => {
  salesmanVisible.value = false
  if (c.city) { selectedCity.value = c.city; highlightCity(c.city) }
  selectedCustomer.value = c
}
const clearSelect = () => {
  selectedCity.value = null
  selectedCustomer.value = null
  highlightCity(null)
}
const selectSalesman = (s) => {
  activeSalesman.value = s
  salesmanVisible.value = true
}
const highlightCity = (city) => {
  if (!chart) return
  chart.dispatchAction({ type: 'highlight', seriesName: '客户阵地', name: city })
}

const setCity = async (cust, val) => {
  if (!val || !val.length) return
  const city = val[val.length - 1]
  try {
    const res = await api.post('/sandbox/customer-city', { cust_id: cust.id, city })
    if (res.data?.ok) {
      ElMessage.success(`${cust.name} 已定位到 ${res.data.region}`)
      await loadData()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '保存失败')
  }
}

const resize = () => chart && chart.resize()

onMounted(async () => {
  await loadData()
  await nextTick()
  window.addEventListener('resize', resize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  if (chart) { chart.dispose(); chart = null }
})
</script>

<style scoped>
.sandbox-page {
  height: calc(100vh - 90px);
  display: flex;
  flex-direction: column;
  background: #071426;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid #12345c;
}
/* 顶栏 */
.sandbox-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background: linear-gradient(90deg, #0a2242 0%, #0d2c52 60%, #0a2242 100%);
  border-bottom: 1px solid #1d4a7a;
  flex-shrink: 0;
}
.header-title { display: flex; align-items: baseline; gap: 8px; }
.title-icon { font-size: 22px; }
.title-text { font-size: 18px; font-weight: 700; color: #e8f4ff; letter-spacing: 2px; }
.title-sub { font-size: 11px; color: #4d84bd; letter-spacing: 3px; }
.header-stats { display: flex; gap: 10px; }
.stat-chip {
  min-width: 86px; text-align: center; padding: 6px 12px;
  background: rgba(20, 60, 110, .45); border: 1px solid #1d4a7a; border-radius: 8px;
}
.stat-num { font-size: 17px; font-weight: 700; color: #52d0ff; font-family: Consolas, monospace; }
.stat-chip.amount .stat-num { color: #ffd04b; }
.stat-chip.visit .stat-num { color: #7dffb8; }
.stat-chip.located .stat-num { color: #ff9f5b; }
.stat-label { font-size: 11px; color: #6f9cc8; margin-top: 2px; }

/* 主体 */
.sandbox-body { flex: 1; display: flex; min-height: 0; }
.map-wrap { flex: 1; position: relative; min-width: 0; }
.map-chart { width: 100%; height: 100%; }
.map-legend {
  position: absolute; left: 16px; bottom: 12px; display: flex; gap: 16px;
  font-size: 11px; color: #7aa8d4; background: rgba(7,20,38,.7);
  padding: 6px 12px; border-radius: 6px; border: 1px solid #16406e;
}
.lg-item { display: flex; align-items: center; gap: 5px; }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot.cyan { background: #27c2ff; }
.dot.pulse { background: #ffd04b; }
.dot.orange { background: #ff7a2f; }
.map-tip {
  position: absolute; top: 14px; left: 16px; font-size: 12px; color: #6f9cc8;
  background: rgba(7,20,38,.7); padding: 5px 10px; border-radius: 6px; border: 1px dashed #2a5687;
}
.back-btn { position: absolute; top: 12px; right: 14px; }

/* 右侧面板 */
.side-panel {
  width: 400px; flex-shrink: 0; display: flex; flex-direction: column;
  background: #081a30; border-left: 1px solid #1d4a7a; position: relative; min-height: 0;
}
.panel-section { flex: 1; overflow-y: auto; padding: 14px; }
.panel-title { font-size: 14px; font-weight: 700; color: #8fc7ff; margin-bottom: 10px; display: flex; align-items: center; gap: 4px; }
.panel-title.mt { margin-top: 18px; }
.back-link { margin-right: 2px; }

.rank-list { display: flex; flex-direction: column; gap: 6px; }
.rank-item {
  display: flex; align-items: center; gap: 8px; padding: 8px 10px;
  background: rgba(18, 52, 92, .35); border: 1px solid #16406e; border-radius: 8px;
  cursor: pointer; transition: all .2s;
}
.rank-item:hover { background: rgba(28, 78, 132, .5); border-color: #2d6aa8; }
.rank-no { width: 20px; height: 20px; border-radius: 50%; background: #1d4a7a; color: #9fd6ff; font-size: 11px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.rank-no.no1 { background: #d4a017; color: #fff; }
.rank-no.no2 { background: #8c9bab; color: #fff; }
.rank-no.no3 { background: #a0622d; color: #fff; }
.rank-city { font-weight: 600; color: #d8ecff; font-size: 13px; }
.rank-meta { font-size: 11px; color: #6f9cc8; flex: 1; }
.rank-amt { font-size: 12px; color: #ffd04b; font-family: Consolas, monospace; }
.man-name { font-weight: 600; color: #d8ecff; font-size: 13px; width: 52px; }
.man-pos { font-size: 11px; color: #ff9f5b; width: 58px; }

/* 客户列表 */
.cust-list { display: flex; flex-direction: column; gap: 8px; }
.cust-item {
  padding: 10px 12px; background: rgba(18, 52, 92, .35);
  border: 1px solid #16406e; border-radius: 8px; cursor: pointer; transition: all .2s;
}
.cust-item:hover { background: rgba(28, 78, 132, .5); border-color: #2d6aa8; }
.cust-head { display: flex; align-items: center; gap: 6px; }
.cust-name { font-weight: 600; color: #e8f4ff; font-size: 13px; flex: 1; }
.cust-amt { color: #ffd04b; font-size: 12px; font-family: Consolas, monospace; }
.cust-meta { font-size: 11px; color: #6f9cc8; margin-top: 4px; }

/* 客户详情 */
.cust-tags { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
.detail-block { margin-bottom: 16px; }
.block-title { font-size: 12px; color: #8fc7ff; font-weight: 600; margin-bottom: 8px; }
.stk-list { display: flex; flex-wrap: wrap; gap: 6px; }
.stk-tag { font-size: 11px; }
.biz-list { display: flex; flex-direction: column; gap: 8px; }
.biz-item { padding: 8px 10px; background: rgba(18, 52, 92, .35); border: 1px solid #16406e; border-radius: 8px; }
.biz-row { display: flex; justify-content: space-between; gap: 8px; }
.biz-title { color: #e8f4ff; font-size: 12px; font-weight: 600; }
.biz-amt { color: #ffd04b; font-size: 12px; font-family: Consolas, monospace; flex-shrink: 0; }
.biz-meta { display: flex; align-items: center; gap: 8px; margin-top: 5px; font-size: 11px; color: #6f9cc8; }
.visit-timeline { padding-left: 4px; }
.visit-line { display: flex; gap: 6px; align-items: center; }
.visit-status { font-size: 11px; padding: 0 6px; border-radius: 4px; }
.visit-status.completed { background: rgba(80, 220, 140, .15); color: #7dffb8; }
.visit-status.planned { background: rgba(60, 150, 255, .15); color: #6cb8ff; }
.visit-status.cancelled, .visit-status.overdue { background: rgba(255, 90, 90, .15); color: #ff8f8f; }
.visit-purpose { font-size: 12px; color: #d8ecff; }
.visit-meta { font-size: 11px; color: #6f9cc8; margin-top: 2px; }
.empty-hint { font-size: 12px; color: #5a7ea6; padding: 8px 0; }

/* 未定位提示条 */
.unlocated-bar {
  flex-shrink: 0; padding: 9px 14px; font-size: 12px; color: #ffb27d;
  background: rgba(120, 60, 10, .25); border-top: 1px solid #6e4a1d;
  cursor: pointer; text-align: center; transition: background .2s;
}
.unlocated-bar:hover { background: rgba(150, 80, 15, .4); }

/* 抽屉内容 */
.drawer-hint { font-size: 12px; color: #909399; margin-bottom: 12px; }
.unloc-item {
  display: flex; align-items: center; gap: 10px; padding: 10px;
  border: 1px solid #e4e7ed; border-radius: 8px; margin-bottom: 8px;
}
.unloc-info { flex: 1; min-width: 0; }
.unloc-name { font-weight: 600; font-size: 13px; }
.unloc-meta { font-size: 11px; color: #909399; margin-top: 2px; }
.unloc-pick { width: 180px; flex-shrink: 0; }
.man-brief { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; }
.man-numbers { display: flex; gap: 10px; margin-bottom: 8px; }
.mn-item { flex: 1; text-align: center; padding: 10px; background: #f5f7fa; border-radius: 8px; }
.mn-num { font-size: 18px; font-weight: 700; color: #303133; font-family: Consolas, monospace; }
.mn-amt { font-size: 14px; color: #e6a23c; }
.mn-label { font-size: 11px; color: #909399; margin-top: 3px; }
</style>
