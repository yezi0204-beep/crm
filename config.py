# config.py

# 数据库路径
DB_PATH = "crm_app.db"

# 商机阶段（顺序重要）
STAGES = ["初步洽谈", "方案报价", "商务谈判", "赢单成交"]

# 客户级别
CUSTOMER_LEVELS = ["A(重点)", "B(普通)", "C(一般)"]

# 客户来源
CUSTOMER_SOURCES = ["历史客户", "转介绍", "展会", "其它"]

# 合同密级
CONTRACT_CLASSIFICATIONS = ["非密", "内部", "秘密", "机密", "绝密"]

# 业态
BUSINESS_TYPES = ["J", "M", "K"]

# config.py 末尾添加
BUSINESS_STATUS = {
    "active": "正常",
    "void": "已作废"
}

# 人月成本配置
WORK_DAYS_PER_MONTH = 21.75      # 每月工作天数
WORK_HOURS_PER_DAY = 8           # 每天工作小时数
COST_PER_MONTH = 25000           # 每人月成本（元）