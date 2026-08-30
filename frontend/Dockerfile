FROM node:18-alpine AS builder

WORKDIR /app
COPY frontend/package*.json ./
RUN npm install --registry https://registry.npmmirror.com
COPY frontend/ ./
RUN npm run build

# --- 运行阶段 ---
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
