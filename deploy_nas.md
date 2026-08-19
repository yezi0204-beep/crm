# 绿联 NAS DXP4800 部署指南

本指南针对绿联 DXP4800 / DXP4800 Plus / DXP4800 Pro（UGOS Pro 系统），支持完全图形化部署，无需敲命令。

## 一、环境要求

| 项目 | 要求 |
|------|------|
| NAS 型号 | DXP4800 / DXP4800 Plus / DXP4800 Pro（Intel CPU，支持 Docker） |
| 系统 | UGOS Pro（已内置 Docker，无需单独安装） |
| 内存 | 建议 8GB 以上（容器运行占用约 500MB） |
| 存储 | 预留 5GB 以上空间（数据库 + 上传文件） |
| 网络 | NAS 与电脑在同一局域网，能互访 |

## 二、部署前准备

### 1. 在电脑上准备部署文件

需要以下文件（项目根目录下）：
```
Dockerfile              # 后端镜像构建文件
Dockerfile-frontend     # 前端镜像构建文件
docker-compose.yml      # 容器编排配置
nginx.conf              # Nginx 配置
.env                    # 环境变量配置（从 .env.example 复制并修改）
backend/                # 后端源码目录（含 routes/、crypto_keys/ 等）
frontend/               # 前端源码目录
crm_app.db              # 数据库文件（含初始数据）
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，按需修改：

```bash
# 必改项：NAS 部署时填你的 NAS IP，否则前端无法访问后端 API
CORS_ALLOWED_ORIGINS=http://你的NAS_IP:8088

# 可选项：AI 问答功能（不填则 AI 功能不可用，其他功能正常）
LLM_API_KEY=sk-xxxxxxxxxxxxxxxx
LLM_API_BASE=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

## 三、部署步骤（图形化方式）

### 第一步：在 NAS 上创建存储目录

1. 浏览器登录 NAS 管理后台（`http://你的NAS_IP:9000`）
2. 打开 **文件管理** → **共享文件夹**
3. 找到或创建 `DockerData` 文件夹（绿联默认 Docker 数据目录）
4. 在 `DockerData` 下创建 `crm` 文件夹，再在 `crm` 下创建：
   - `data` 文件夹（存放数据库）
   - `uploads` 文件夹（存放上传的合同附件）

最终目录结构：
```
/share/DockerData/crm/
├── data/           # 数据库
└── uploads/        # 上传文件
```

### 第二步：上传项目文件到 NAS

1. 将整个项目文件夹打包为 `crm-deploy.zip`
2. 通过 NAS 文件管理器上传到 `/share/DockerData/crm/`
3. 右键解压到 `crm-deploy` 文件夹

或使用 WinSCP / scp 上传：
```bash
scp -r ./crm-deploy admin@你的NAS_IP:/share/DockerData/crm/
```

### 第三步：复制数据库到 data 目录

通过 NAS 文件管理器，将 `crm-deploy/crm_app.db` 复制到 `/share/DockerData/crm/data/` 目录。

### 第四步：安装并打开 Docker

1. 在 NAS 应用中心搜索 **Docker**，确认已安装（UGOS Pro 默认内置）
2. 打开 Docker 应用，进入容器管理界面
3. 点击 **设置 → 镜像加速**，添加国内加速源（可选但推荐）：
   - `https://registry.cn-hongkong.aliyuncs.com`
   - `https://docker.mirrors.ustc.edu.cn`

### 第五步：构建 Docker 镜像

#### 方式一：SSH 命令行构建（推荐）

1. 在 NAS 系统设置中开启 SSH（系统设置 → 网络 → SSH）
2. 电脑上用 SSH 连接 NAS：
   ```bash
   ssh admin@你的NAS_IP
   ```
3. 进入项目目录并构建镜像：
   ```bash
   cd /share/DockerData/crm/crm-deploy

   # 构建后端镜像（约 2-3 分钟）
   docker build -t crm-backend:latest -f Dockerfile .

   # 构建前端镜像（约 3-5 分钟，含 npm install）
   docker build -t crm-frontend:latest -f Dockerfile-frontend .
   ```

#### 方式二：绿联 Docker 图形化构建

1. 打开 Docker → **镜像管理** → **构建镜像**
2. 选择 Dockerfile 路径 `/share/DockerData/crm/crm-deploy/Dockerfile`
3. 镜像名填 `crm-backend:latest`，点击构建
4. 重复上述步骤构建 `crm-frontend:latest`（选择 `Dockerfile-frontend`）

### 第六步：启动容器（Docker Compose）

#### 方式一：SSH 命令行启动（推荐）

```bash
cd /share/DockerData/crm/crm-deploy
docker-compose up -d
```

#### 方式二：绿联 Docker 图形化启动

1. 打开 Docker → **项目** → **创建**
2. 项目名填 `crm`
3. 路径选择 `/share/DockerData/crm/crm-deploy`
4. 将 `docker-compose.yml` 内容粘贴到 compose 配置框
5. 点击 **立即部署**，勾选 **创建完成后立即运行**

### 第七步：验证部署

1. 查看容器状态：Docker → 容器管理，应看到 `crm-backend` 和 `crm-frontend` 均为运行中
2. 浏览器访问前端：`http://你的NAS_IP:8088`
3. 默认账号登录：`yewei` / `123456`（或你的实际账号）

## 四、常用管理命令

```bash
# 进入项目目录
cd /share/DockerData/crm/crm-deploy

# 查看容器状态
docker-compose ps

# 查看后端日志（排查问题用）
docker-compose logs -f backend

# 查看前端日志
docker-compose logs -f frontend

# 重启服务
docker-compose restart

# 停止服务
docker-compose down

# 更新代码后重新部署
docker-compose down
docker build -t crm-backend:latest -f Dockerfile .
docker build -t crm-frontend:latest -f Dockerfile-frontend .
docker-compose up -d
```

## 五、目录与端口说明

### 目录结构

| 路径 | 用途 |
|------|------|
| `/share/DockerData/crm/data/crm_app.db` | 数据库文件（核心数据，务必备份） |
| `/share/DockerData/crm/uploads/` | 上传的合同附件 |
| `/share/DockerData/crm/crm-deploy/` | 部署配置文件（Dockerfile 等） |

### 端口说明

| 端口 | 服务 | 说明 |
|------|------|------|
| 8088 | 前端页面 | 浏览器访问此端口使用系统 |
| 5000 | 后端 API | 容器内部通信，一般无需直接访问 |

如需修改端口，编辑 `docker-compose.yml` 中 `ports` 配置。

## 六、数据备份

定期备份数据库，避免数据丢失：

```bash
# 备份数据库（建议每天一次，可配合 NAS 计划任务）
cp /share/DockerData/crm/data/crm_app.db /share/DockerData/crm/data/crm_app.db.bak_$(date +%Y%m%d)

# 备份上传文件
cp -r /share/DockerData/crm/uploads /share/DockerData/crm/uploads_bak_$(date +%Y%m%d)
```

也可在 NAS 的 **备份与同步** 中设置自动备份 `crm` 文件夹到其他位置。

## 七、常见问题

### 1. 前端能打开但登录提示"网络错误"

**原因**：前端无法访问后端 API。

**解决**：
- 检查 `crm-backend` 容器是否正常运行
- 检查 `.env` 中 `CORS_ALLOWED_ORIGINS` 是否填了 `http://你的NAS_IP:8088`
- SSH 执行 `docker-compose logs backend` 查看后端报错

### 2. 镜像构建失败（pip install 超时）

**原因**：网络问题导致 Python 依赖下载失败。

**解决**：Dockerfile 已配置清华镜像源，若仍失败可尝试：
```bash
docker build --network=host -t crm-backend:latest -f Dockerfile .
```

### 3. 前端镜像构建失败（npm install 超时）

**解决**：修改 Dockerfile-frontend，在 `npm install` 前加淘宝镜像：
```dockerfile
RUN npm install --registry=https://registry.npmmirror.com
```

### 4. 数据库锁定错误（database is locked）

**原因**：SQLite 并发写入冲突。

**解决**：已通过 gunicorn 4 worker + WAL 模式缓解。若仍出现，减少并发或升级到 PostgreSQL。

### 5. 容器无法访问外网（AI 功能不可用）

**原因**：NAS 网络限制或 DNS 问题。

**解决**：
- 检查 NAS 网络设置，确保 DNS 正常（如 `8.8.8.8`）
- 若无需 AI 功能，`.env` 中 `LLM_API_KEY` 留空即可，系统其他功能正常

### 6. 端口被占用

**解决**：编辑 `docker-compose.yml`，将 `8088:80` 改为其他空闲端口，如 `9090:80`。

## 八、注意事项

1. **NAS 重启后容器自动启动**（`restart: unless-stopped` 策略）
2. **数据库持久化**：数据库在 NAS 本地存储，容器删除不会丢失数据
3. **升级时备份数据库**：更新代码前务必备份 `crm_app.db`
4. **HTTPS 配置**：如需 HTTPS，可在 NAS 中配置反向代理或使用 Caddy/Nginx Proxy Manager 容器
5. **防火墙**：若 NAS 开启了防火墙，需放行 8088 和 5000 端口
