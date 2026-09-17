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

## 生产环境数据库迁移（Alembic）

> ⚠️ **迁移必须先于（或随）代码上线执行。** `start.sh` 不自动跑迁移；uvicorn `--reload`/重启会先加载新代码，若 DB 未迁移，接口会以 `no such column` 一类 500 报错（2026-09-15 实测事故，见 issue #93）。

### 何时需要

发布的代码中含 `src/backend/alembic/versions/` 新文件（模型加列/加表）时，**每次发布都要执行**。纯前端或无迁移的发布可跳过。

### 标准步骤（生产机）

```bash
cd <项目根>/src/backend

# 1. 备份数据库（命名带迁移版本与时间戳，便于回滚定位）
cp app.db ../../data/backups/app.db.bak-<新版本号>-$(date +%Y%m%d-%H%M%S)

# 2. 确认当前迁移版本
DATABASE_URL="sqlite+aiosqlite:///./app.db" alembic current

# 3. 执行迁移（用生产 conda base 环境的 alembic，./start.sh prod 同环境）
DATABASE_URL="sqlite+aiosqlite:///./app.db" alembic upgrade head

# 4. 验证：版本号已推进 + 新列/新表存在
DATABASE_URL="sqlite+aiosqlite:///./app.db" alembic current
sqlite3 app.db "PRAGMA table_info(<变动的表>);"

# 5. 重启服务
./start.sh restart backend   # 在项目根目录执行
```

### 回滚

```bash
# 代码回滚后，数据库按情况二选一：
DATABASE_URL="sqlite+aiosqlite:///./app.db" alembic downgrade -1   # 结构性回退
cp ../../data/backups/app.db.bak-<版本>-<时间戳> app.db            # 或直接恢复备份
```

### 注意事项

- `DATABASE_URL` 的 `./app.db` 是相对路径，**必须在 `src/backend` 目录下执行**（生产实际库以 `/etc/beingdoing.env` / `.env.prod` 为准，口径同上）。
- 迁移脚本中如需为存量数据回填默认值（如 020 的追溯补期），回填策略写死在迁移里，不要读运行时配置文件，保证确定性。
- 开发机验证新迁移：可先在临时库单跑目标迁移（`alembic stamp <上一版本>` + `alembic upgrade head`），并验证 downgrade 可逆。

## 环境变量说明

详见 `.env.example` 文件。

## 注意事项

1. 确保数据目录有写入权限
2. 生产环境使用PostgreSQL而非SQLite
3. 设置强密码和SECRET_KEY
4. 配置HTTPS（推荐）
5. 定期备份数据库和对话记录
