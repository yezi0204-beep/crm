# 客户拜访排班搜索功能增强

## Context

用户反馈"客户拜访排班添加搜索功能，可以查历史信息"。当前 Visits.vue 已有搜索输入框和日期筛选器，但 `fetchVisits` 函数只传了 `status` 和 `visitor_id` 两个参数到后端，日期范围、关键词、工作类型全靠前端 `filteredVisits` 计算属性本地过滤。导致搜索效率低，且用户可能感觉搜索不生效。

## 修改方案

### 1. 前端 `fetchVisits` 补传所有筛选参数（Visits.vue#L877-L897）

将 `filterDateRange`、`searchKeyword`、`filterWorkType` 全部传给后端：

```javascript
const fetchVisits = async () => {
  const params = new URLSearchParams()
  if (filterStatus.value) params.append('status', filterStatus.value)
  if (filterVisitorId.value) params.append('visitor_id', filterVisitorId.value)
  if (filterWorkType.value) params.append('work_type', filterWorkType.value)
  if (searchKeyword.value) params.append('keyword', searchKeyword.value)
  if (filterDateRange.value && filterDateRange.value.length === 2) {
    params.append('start_date', filterDateRange.value[0])
    params.append('end_date', filterDateRange.value[1])
  }
  // ...
}
```

### 2. 后端 `get_visits` 增加 work_type 筛选 + keyword 搜索扩展（visits.py#L8-L73）

- 增加 `work_type` 参数支持
- keyword 搜索增加 `v.work_content` 字段

### 3. 前端简化 `filteredVisits`（Visits.vue#L764-L795）

过滤逻辑已移至后端，`filteredVisits` 直接返回 `visits.value`，`pagedVisits` 做分页即可。

## 验证

- 打开拜访排班页，输入关键词搜索能查到历史拜访记录
- 选择历史日期范围能筛选出对应时段记录
- 工作类型筛选生效
- 分页正常
