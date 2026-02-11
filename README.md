# 找到想做的事 - 智能引导系统

一个沉浸式的智能引导系统，帮助用户通过探索价值观、才能和兴趣，找到真正想做的事。

## 核心公式

**喜欢的事 × 擅长的事 × 重要的事 = 真正想做的事**

## 项目结构

```
.
├── src/
│   ├── backend/          # 后端服务（FastAPI + Python）
│   │   ├── app/
│   │   │   ├── api/      # API路由
│   │   │   ├── core/     # 核心服务（LLM、ASR、TTS、Agent、Knowledge）
│   │   │   ├── models/   # 数据模型
│   │   │   ├── services/ # 业务逻辑服务
│   │   │   └── utils/    # 工具函数
│   │   └── alembic/      # 数据库迁移
│   └── frontend/         # 前端应用（Next.js + TypeScript）
│       ├── app/          # Next.js页面和路由
│       ├── components/   # React组件
│       ├── lib/          # 工具库（API客户端等）
│       └── stores/       # Zustand状态管理
├── planning/              # 设计文档
├── data/                  # 数据文件（CSV、Markdown、对话记录）
└── test/                  # 测试文件
```

## 快速开始

**本地完整跑起来**：请按 [本地运行指南](docs/RUN_LOCALLY.md) 一步步执行（环境、.env、数据库、后端、前端）。

### 快速启动（5分钟）

1. **配置环境变量**
```bash
cp .env.example .env
# 编辑 .env，至少配置 OPENAI_API_KEY 和 SECRET_KEY
```

2. **启动后端**
```bash
cd src/backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
python scripts/init_db.py
uvicorn app.main:app --reload
```

3. **启动前端**
```bash
cd src/frontend
npm install
npm run dev
```

4. **访问应用**: http://localhost:3000

## 功能特性

### 核心功能

✅ **用户认证** - 注册/登录、JWT Token认证  
✅ **用户信息收集** - 基本信息、工作履历、项目经历  
✅ **探索流程** - 价值观、才能、兴趣探索  
✅ **智能引导** - LangGraph智能体、ReAct范式  
✅ **对话系统** - 实时对话、历史管理  
✅ **知识库** - CSV/Markdown加载、关键词检索  
✅ **数据导出** - JSON/Markdown/PDF格式  

详细功能列表请查看 [项目状态文档](docs/PROJECT_STATUS.md)

## 技术栈

### 后端
- **框架**: FastAPI
- **数据库**: SQLAlchemy (SQLite/PostgreSQL)
- **智能体**: LangGraph
- **LLM**: OpenAI API
- **认证**: JWT (python-jose)
- **迁移**: Alembic

### 前端
- **框架**: Next.js 14 (App Router)
- **语言**: TypeScript
- **样式**: Tailwind CSS
- **状态管理**: Zustand
- **表单**: React Hook Form + Zod
- **动画**: Framer Motion

## 📚 文档

所有文档位于 `docs/` 目录：

- **[快速开始](docs/QUICK_START.md)** - 5分钟快速启动指南
- **[开发指南](docs/DEVELOPMENT.md)** - 开发环境设置和代码规范
- **[测试说明](docs/TESTING.md)** - 测试运行和编写指南
- **[API文档](docs/API_DOCUMENTATION.md)** - 完整的API接口文档
- **[架构设计](docs/ARCHITECTURE.md)** - 系统架构和技术栈
- **[数据库设计](docs/DATABASE_SCHEMA.md)** - 数据库表结构设计
- **[部署指南](docs/DEPLOYMENT.md)** - 部署说明
- **[Docker使用](docs/DOCKER.md)** - Docker部署指南
- **[用户指南](docs/USER_GUIDE.md)** - 用户使用说明
- **[常见问题](docs/FAQ.md)** - FAQ

## 🔧 配置

详细配置说明请查看 [环境配置文档](docs/ENV_SETUP.md)

主要配置项：
- `OPENAI_API_KEY` - OpenAI API密钥（必需）
- `SECRET_KEY` - JWT密钥（必需）
- `DATABASE_URL` - 数据库连接（默认SQLite）
- `ARCHITECTURE_MODE` - 架构模式（simple/full）
- `AUDIO_MODE` - 音频功能开关（False/True）

## 🧪 测试

```bash
# 后端测试
cd src/backend
pytest

# 查看测试覆盖率
pytest --cov=app --cov-report=html
```

详细测试说明请查看 [测试文档](docs/TESTING.md)

## 🚀 部署

### Docker部署

```bash
docker-compose up -d
```

详细部署说明请查看 [部署文档](docs/DEPLOYMENT.md) 和 [Docker文档](docs/DOCKER.md)

## 📊 API文档

启动后端后访问：
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

完整API文档请查看 [API文档](docs/API_DOCUMENTATION.md)

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request！
