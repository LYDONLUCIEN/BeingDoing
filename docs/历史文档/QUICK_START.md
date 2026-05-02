# 快速开始指南

## 🚀 5分钟快速启动

### 前置要求

- Python 3.10+
- Node.js 18+
- Git

### 步骤1: 克隆项目

```bash
git clone <repository-url>
cd 职业规划-找到喜欢的事
```

### 步骤2: 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，至少需要配置：
# - SECRET_KEY（随机字符串）
# - OPENAI_API_KEY（你的OpenAI API密钥）
```

### 步骤3: 启动后端

```bash
cd src/backend

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 初始化数据库
alembic upgrade head
python scripts/init_db.py

# 启动服务
uvicorn app.main:app --reload --port 8000
```

后端服务将在 http://localhost:8000 启动

### 步骤4: 启动前端

```bash
# 新开一个终端
cd src/frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端应用将在 http://localhost:3000 启动

### 步骤5: 访问应用

打开浏览器访问: http://localhost:3000

## 📝 首次使用

1. **注册账号**: 访问 `/auth/register` 注册新用户
2. **完善信息**: 注册后会自动跳转到 `/profile/setup` 完善个人信息
3. **开始探索**: 进入 `/explore` 开始探索流程

## 🔧 常见问题

### 后端启动失败

- 检查Python版本: `python --version` (需要3.10+)
- 检查依赖安装: `pip list`
- 检查环境变量: 确保`.env`文件存在且配置正确

### 前端启动失败

- 检查Node.js版本: `node --version` (需要18+)
- 清除缓存: `rm -rf node_modules .next && npm install`
- 检查端口占用: 确保3000端口未被占用

### 数据库错误

- 检查数据库文件: `data/app.db` 是否存在
- 重新初始化: `python scripts/init_db.py`

## 📚 更多信息

- 详细配置: 查看 `docs/ENV_SETUP.md`
- API文档: 启动后端后访问 http://localhost:8000/docs
- 完整文档: 查看 `docs/` 目录
