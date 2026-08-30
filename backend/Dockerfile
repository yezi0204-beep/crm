FROM python:3.11-slim

WORKDIR /app

# 系统依赖（pypdf, python-docx, openpyxl 不需要额外系统库）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl && \
    rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码
COPY backend/ /app/

# 数据目录
RUN mkdir -p /app/data /app/uploads /app/logs

# 环境变量
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/app/data/crm.db
ENV UPLOAD_FOLDER=/app/uploads
ENV LOG_FOLDER=/app/logs
# 在应用进程内启动后台调度器（单 worker 前提下安全）
ENV CRM_START_SCHEDULER=1

# 暴露端口
EXPOSE 5000

# 健康检查
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:5000/api/cockpit/health || exit 1

# 启动：生产使用 gunicorn（必须 --workers 1，调度器在进程内运行）
CMD ["gunicorn", "--workers", "1", "--threads", "8", "--timeout", "300", "--bind", "0.0.0.0:5000", "app:app"]
