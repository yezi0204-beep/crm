# 绿联NAS部署指南

## 环境要求
- 绿联NAS已安装Docker（在NAS应用中心搜索"Docker"安装）
- NAS已开启SSH服务（系统设置 -> 网络 -> SSH）
- 电脑可以访问NAS的IP地址

## 部署步骤

### 第一步：准备部署文件

将以下文件打包成 `crm-deploy.zip`：
- Dockerfile
- Dockerfile-frontend
- docker-compose.yml
- nginx.conf
- backend/app.py
- backend/requirements.txt
- crm_app.db

### 第二步：在NAS上创建目录

通过SSH连接NAS（密码为NAS管理员密码）：
```bash
ssh admin@你的NAS_IP
```

创建部署目录：
```bash
mkdir -p /share/CACHEDEV1_DATA/crm/{data,uploads,deploy}
```

### 第三步：上传文件到NAS

使用WinSCP或scp上传文件：
```bash
scp crm-deploy.zip admin@你的NAS_IP:/share/CACHEDEV1_DATA/crm/deploy/
```

解压文件：
```bash
cd /share/CACHEDEV1_DATA/crm/deploy
unzip crm-deploy.zip
```

复制数据库文件到数据目录：
```bash
cp crm_app.db /share/CACHEDEV1_DATA/crm/data/
```

### 第四步：构建Docker镜像

```bash
cd /share/CACHEDEV1_DATA/crm/deploy

# 构建后端镜像
docker build -t crm-backend:latest -f Dockerfile .

# 构建前端镜像
docker build -t crm-frontend:latest -f Dockerfile-frontend .
```

### 第五步：启动容器

```bash
docker-compose up -d
```

### 第六步：验证部署

访问以下地址验证：
- 前端页面：http://你的NAS_IP:8088
- 默认账号：yewei / 123456

## 管理命令

```bash
# 查看容器状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down

# 更新服务（修改代码后）
docker-compose down
docker build -t crm-backend:latest -f Dockerfile .
docker build -t crm-frontend:latest -f Dockerfile-frontend .
docker-compose up -d
```

## 目录说明

| 路径 | 用途 |
|------|------|
| /share/CACHEDEV1_DATA/crm/data/ | 数据库文件 |
| /share/CACHEDEV1_DATA/crm/uploads/ | 上传的合同文件 |
| /share/CACHEDEV1_DATA/crm/deploy/ | 部署配置文件 |

## 端口说明

| 端口 | 服务 |
|------|------|
| 8088 | 前端页面 |
| 5000 | 后端API（内部使用） |

## 注意事项

1. 如果NAS重启，容器会自动启动（restart: unless-stopped）
2. 数据库文件保存在NAS上，不会因容器删除而丢失
3. 如果需要修改端口，编辑docker-compose.yml中的ports配置
4. 如果NAS的存储卷名称不是CACHEDEV1_DATA，请根据实际情况修改路径