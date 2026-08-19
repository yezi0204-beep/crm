# CRM 后端镜像：Python 3.10 slim 基础镜像（体积小，兼容绿联NAS Intel CPU）
FROM python:3.10-slim

# 设置时区为上海（日志时间和业务时间一致）
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# 优先复制依赖文件，利用 Docker 缓存层（依赖不变时跳过 pip install）
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制后端全部源码
COPY backend/app.py .
COPY backend/config.py .
COPY backend/extensions.py .
COPY backend/qa_engine.py .
COPY backend/ai_analyzer.py .
COPY backend/scheduler.py .
COPY backend/security.py .
COPY backend/vector_search.py .
COPY backend/routes/ ./routes/

# 复制加密密钥目录（证书、AES密钥、HMAC密钥等，用于数据加密/签名）
COPY backend/crypto_keys/ ./crypto_keys/

# 创建上传目录（合同附件等）
RUN mkdir -p /app/uploads/contracts

# 暴露 Flask 服务端口
EXPOSE 5000

# 使用 gunicorn 生产级 WSGI 启动（4 worker，120s 超时兼容 LLM 长请求）
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "--timeout", "120", "app:app"]
