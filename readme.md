# CRM 系统

天地信息网络研究院客户关系管理系统，采用前后端分离架构。

## 技术栈

- **前端**: Vue 3 + Element Plus + ECharts + Pinia + Vue Router
- **后端**: Flask + SQLite
- **构建工具**: Vite

## 项目结构

```
crm/
├── backend/                    # 后端服务
│   └── app.py                  # Flask 应用（API接口、数据库操作）
├── frontend/                   # 前端应用
│   ├── src/
│   │   ├── api/                # API 请求封装
│   │   │   └── index.js
│   │   ├── router/             # 路由配置
│   │   │   └── index.js
│   │   ├── stores/             # Pinia 状态管理
│   │   │   └── auth.js
│   │   ├── views/              # 页面组件
│   │   │   ├── Dashboard.vue   # 驾驶舱
│   │   │   ├── Customers.vue   # 客户管理
│   │   │   ├── Business.vue    # 商机管理
│   │   │   ├── Contracts.vue   # 合同管理
│   │   │   ├── Payments.vue    # 回款管理
│   │   │   ├── Pool.vue        # 公海池
│   │   │   ├── Projects.vue    # 项目管理
│   │   │   ├── WorkHours.vue   # 工时管理
│   │   │   ├── Users.vue       # 用户管理
│   │   │   ├── Search.vue      # 全局搜索
│   │   │   ├── Layout.vue      # 页面布局
│   │   │   └── Login.vue       # 登录页
│   │   ├── App.vue             # 根组件
│   │   └── main.js             # 入口文件
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
├── uploads/                    # 上传文件存储
│   └── contracts/              # 合同文件
├── crm_app.db                  # SQLite 数据库
├── .gitignore
└── readme.md
```

## 快速开始

### 后端

```bash
cd backend
python app.py
# 服务启动在 http://localhost:5000
```

### 前端

```bash
cd frontend
npm install
npm run dev
# 服务启动在 http://localhost:8080
```

## 功能模块

| 模块 | 说明 |
|------|------|
| 驾驶舱 | 数据统计与趋势分析，支持按月/季/年筛选 |
| 客户管理 | 客户信息CRUD，支持搜索、分级、来源管理 |
| 商机管理 | 商机跟踪，关联客户与干系人 |
| 合同管理 | 合同信息管理，支持导入导出、编号唯一校验、待回款排序 |
| 回款管理 | 回款记录管理，支持合同模糊搜索 |
| 公海池 | 30天未跟进客户自动释放 |
| 项目管理 | 项目成本与工时管理 |
| 工时管理 | 员工工时记录与审批 |
| 用户管理 | 用户账号与角色管理 |
| 全局搜索 | 跨模块模糊搜索 |
