# 部署指南

## 本地开发

### 后端
```bash
cd src/backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 前端
```bash
cd src/frontend
npm install
npm run dev
```

## Docker部署

### 构建和启动
```bash
docker-compose up -d
```

### 查看日志
```bash
docker-compose logs -f
```

### 停止服务
```bash
docker-compose down
```

## 阿里云部署

### 1. 准备服务器
- ECS实例（推荐2核4G以上）
- 安装Docker和Docker Compose

### 2. 上传代码
```bash
git clone <repository>
cd <project-directory>
```

### 3. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env 文件
```

### 4. 启动服务
```bash
docker-compose up -d
```

### 5. 配置Nginx（可选）
如果需要使用域名访问，配置Nginx反向代理。

## 环境变量说明

详见 `.env.example` 文件。

## 注意事项

1. 确保数据目录有写入权限
2. 生产环境使用PostgreSQL而非SQLite
3. 设置强密码和SECRET_KEY
4. 配置HTTPS（推荐）
5. 定期备份数据库和对话记录
