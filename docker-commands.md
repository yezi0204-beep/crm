# CRM 系统 Docker 打包与运行命令

## 一、前置准备

### 1. 确认文件结构

```
crm/
├── Dockerfile              # 后端镜像构建文件
├── docker-compose.yml      # 容器编排配置
├── .env                    # 环境变量（从 .env.example 复制并修改）
├── backend/                # 后端源码
│   ├── app.py
│   ├── extensions.py
│   ├── routes/
│   ├── crypto_keys/         # 加密密钥目录
│   ├── requirements.txt
│   └── ...
├── frontend/               # 前端源码
│   ├── src/
│   ├── package.json
│   └── ...
└── crm_app.db              # 数据库文件（含初始数据）
```

### 2. 配置环境变量

```bash
# 复制示例配置
cp .env.example .env

# 编辑 .env，按需修改：
# - SECRET_KEY：生产环境请改为随机字符串
# - LLM_API_KEY / LLM_API_BASE / LLM_MODEL：AI 功能配置（可留空）
# - CORS_ALLOWED_ORIGINS：填访问地址，如 http://NAS_IP:8088
```

---

## 二、单独构建镜像

### 后端镜像

```bash
# 在项目根目录执行
docker build -t crm-backend:latest -f Dockerfile .
```

### 前端镜像

```bash
# 在 frontend 目录执行（需先创建 Dockerfile-frontend）
docker build -t crm-frontend:latest -f frontend/Dockerfile-frontend .
```

---

## 三、Docker Compose 一键启动（推荐）

### 首次部署

```bash
# 构建镜像并启动容器
docker-compose up -d --build
```

### 查看容器状态

```bash
docker-compose ps
```

### 查看日志

```bash
# 后端日志
docker-compose logs -f backend

# 前端日志
docker-compose logs -f frontend

# 全部日志
docker-compose logs -f
```

### 停止与重启

```bash
# 停止
docker-compose down

# 重启
docker-compose restart

# 停止并删除容器（数据卷保留）
docker-compose down

# 停止并删除容器和数据卷（⚠️ 会删除所有数据）
docker-compose down -v
```

### 更新代码后重新部署

```bash
# 1. 停止旧容器
docker-compose down

# 2. 重新构建镜像
docker-compose build

# 3. 启动新容器
docker-compose up -d
```

---

## 四、单独运行容器（不使用 Compose）

### 后端容器

```bash
# 创建网络
docker network create crm-net

# 启动后端
docker run -d \
  --name crm-backend \
  --restart unless-stopped \
  -p 5000:5000 \
  -v crm-data:/app/data \
  -v crm-uploads:/app/uploads \
  -e SECRET_KEY=your_secret_key \
  -e DB_PATH=/app/data/crm_app.db \
  -e LLM_API_BASE=https://api.deepseek.com/v1 \
  -e LLM_API_KEY=your_api_key \
  -e LLM_MODEL=deepseek-chat \
  --network crm-net \
  crm-backend:latest
```

### 前端容器

```bash
docker run -d \
  --name crm-frontend \
  --restart unless-stopped \
  -p 80:80 \
  --network crm-net \
  --depends-on crm-backend \
  crm-frontend:latest
```

---

## 五、数据持久化

### 数据卷说明

| 卷名 | 容器路径 | 用途 |
|------|----------|------|
| crm-data | /app/data | 数据库文件 |
| crm-uploads | /app/uploads | 合同附件等上传文件 |
| crm-logs | /app/logs | 日志文件 |

### 手动备份数据库

```bash
# 将容器内数据库复制到宿主机
docker cp crm-backend:/app/data/crm_app.db ./crm_app.db.bak

# 或通过数据卷复制
docker run --rm -v crm-data:/data -v $(pwd):/backup alpine \
  cp /data/crm_app.db /backup/crm_app.db.bak
```

### 恢复数据库

```bash
# 将备份文件复制回容器
docker cp ./crm_app.db.bak crm-backend:/app/data/crm_app.db

# 重启容器使数据库生效
docker-compose restart backend
```

---

## 六、常用维护命令

```bash
# 进入后端容器
docker exec -it crm-backend bash

# 查看数据库
docker exec -it crm-backend python -c "
import sqlite3
conn = sqlite3.connect('/app/data/crm_app.db')
print(conn.execute('SELECT COUNT(*) FROM contracts').fetchone())
"

# 查看容器资源占用
docker stats crm-backend crm-frontend

# 清理无用镜像
docker image prune -f

# 查看所有容器
docker ps -a --filter "name=crm"
```

---

## 七、端口说明

| 端口 | 服务 | 说明 |
|------|------|------|
| 80 | 前端页面 | 浏览器访问此端口使用系统 |
| 5000 | 后端 API | 容器内部通信，一般无需直接访问 |

如需修改端口，编辑 `docker-compose.yml` 中 `ports` 配置：
```yaml
# 例如将前端端口改为 8088
ports:
  - "8088:80"
```

---

## 八、部署后验证

```bash
# 1. 检查容器运行状态
docker-compose ps

# 2. 测试后端 API
curl http://localhost:5000/api/health

# 3. 浏览器访问前端
# http://localhost（或映射的端口）
# 默认账号：yewei / 123456
```
