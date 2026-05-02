# Docker使用说明

## 🐳 Docker部署

### 快速启动

```bash
# 配置环境变量
cp .env.example .env
# 编辑 .env 文件

# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

## 📦 服务说明

### backend
后端API服务

- **端口**: 8000
- **镜像**: 从 `src/backend/Dockerfile` 构建
- **数据卷**: 
  - `./data:/app/data` (数据目录)
  - CSV和Markdown文件

### frontend
前端应用

- **端口**: 3000
- **镜像**: 从 `src/frontend/Dockerfile` 构建
- **环境变量**: `NEXT_PUBLIC_API_URL=http://backend:8000`

### db
PostgreSQL数据库（可选）

- **端口**: 5432
- **数据卷**: `postgres_data` (持久化)

## 🔧 构建镜像

### 手动构建

```bash
# 构建后端镜像
cd src/backend
docker build -t career-guide-backend .

# 构建前端镜像
cd src/frontend
docker build -t career-guide-frontend .
```

### 使用docker-compose构建

```bash
docker-compose build
```

## 🚀 生产部署

### 1. 准备服务器

- 安装Docker和Docker Compose
- 配置防火墙规则
- 准备域名和SSL证书（可选）

### 2. 上传代码

```bash
git clone <repository>
cd <project-directory>
```

### 3. 配置环境

```bash
cp .env.example .env
# 编辑 .env，配置生产环境变量
```

### 4. 启动服务

```bash
docker-compose up -d
```

### 5. 查看状态

```bash
docker-compose ps
docker-compose logs
```

## 🔍 故障排查

### 查看日志

```bash
# 所有服务
docker-compose logs

# 特定服务
docker-compose logs backend
docker-compose logs frontend

# 实时日志
docker-compose logs -f
```

### 进入容器

```bash
# 进入后端容器
docker-compose exec backend bash

# 进入前端容器
docker-compose exec frontend sh
```

### 重启服务

```bash
# 重启所有服务
docker-compose restart

# 重启特定服务
docker-compose restart backend
```

## 📊 资源监控

### 查看资源使用

```bash
docker stats
```

### 清理资源

```bash
# 清理未使用的镜像
docker image prune

# 清理所有未使用的资源
docker system prune -a
```

## 🔒 安全建议

1. **环境变量**: 不要在Dockerfile中硬编码敏感信息
2. **网络**: 使用内部网络，不暴露数据库端口
3. **用户**: 容器内使用非root用户
4. **更新**: 定期更新基础镜像

## 🔗 相关文档

- 部署指南: 查看 `docs/DEPLOYMENT.md`
- 环境配置: 查看 `docs/ENV_SETUP.md`
