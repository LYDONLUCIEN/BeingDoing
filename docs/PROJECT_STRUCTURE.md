# 项目结构说明

## 📁 目录结构

```
.
├── src/                      # 源代码目录
│   ├── backend/             # 后端服务
│   │   ├── app/            # 应用代码
│   │   │   ├── api/        # API路由层
│   │   │   │   ├── v1/     # API v1版本
│   │   │   │   └── middleware.py  # 中间件
│   │   │   ├── core/       # 核心服务层
│   │   │   │   ├── agent/  # 智能体框架
│   │   │   │   ├── llmapi/ # LLM API
│   │   │   │   ├── asr/    # ASR API
│   │   │   │   ├── tts/    # TTS API
│   │   │   │   └── knowledge/  # 知识库
│   │   │   ├── models/     # 数据模型
│   │   │   ├── services/    # 业务逻辑服务
│   │   │   ├── utils/      # 工具函数
│   │   │   ├── config/     # 配置模块
│   │   │   └── main.py     # 应用入口
│   │   ├── alembic/        # 数据库迁移
│   │   ├── scripts/        # 脚本
│   │   ├── requirements.txt # Python依赖
│   │   └── Dockerfile      # Docker镜像
│   └── frontend/           # 前端应用
│       ├── app/            # Next.js App Router
│       │   ├── auth/       # 认证页面
│       │   ├── profile/    # 用户信息页面
│       │   ├── explore/   # 探索页面
│       │   ├── layout.tsx # 根布局
│       │   └── page.tsx    # 首页
│       ├── components/     # React组件
│       │   └── explore/    # 探索相关组件
│       ├── lib/            # 工具库
│       │   └── api/        # API客户端
│       ├── stores/         # Zustand状态管理
│       ├── package.json    # Node.js依赖
│       └── Dockerfile     # Docker镜像
│
├── docs/                    # 📚 项目文档目录
│   ├── INDEX.md            # 文档索引
│   ├── QUICK_START.md      # 快速开始
│   ├── DEVELOPMENT.md      # 开发指南
│   ├── TESTING.md          # 测试说明
│   ├── API_DOCUMENTATION.md # API文档
│   ├── ARCHITECTURE.md     # 架构设计
│   ├── DATABASE_SCHEMA.md  # 数据库设计
│   ├── DEPLOYMENT.md       # 部署指南
│   ├── DOCKER.md           # Docker使用
│   ├── USER_GUIDE.md       # 用户指南
│   ├── FAQ.md              # 常见问题
│   └── ...                 # 其他文档
│
├── planning/                # 设计文档目录
│   ├── README.md           # 设计文档索引
│   ├── 01_需求分析与澄清.md
│   ├── 02_技术架构设计.md
│   ├── 03_API接口设计.md
│   ├── 04_数据库设计.md
│   ├── 05_智能体设计.md
│   ├── 06_前端交互设计.md
│   ├── 07_系统流程图.md
│   ├── 08_架构切换与模块接口设计.md
│   └── todolist.md         # 开发任务清单
│
├── test/                    # 测试目录
│   ├── backend/            # 后端测试
│   │   ├── core/          # 核心服务测试
│   │   ├── api/           # API测试
│   │   └── services/       # 业务逻辑测试
│   └── frontend/          # 前端测试（待实现）
│
├── data/                    # 数据目录
│   ├── conversations/      # 对话记录（JSON文件）
│   └── app.db             # SQLite数据库（开发环境）
│
├── note.md                  # 用户原始笔记（保留）
├── question.md              # 用户原始问题（保留）
├── flowchart.md             # 用户原始流程图（保留）
├── note_organized.md       # 整理后的笔记（保留）
├── 重要的事_价值观.csv      # 知识库数据（保留）
├── 喜欢的事_热情.csv        # 知识库数据（保留）
├── 擅长的事_才能.csv        # 知识库数据（保留）
│
├── .env.example             # 环境变量模板
├── .env                     # 环境变量（不提交到Git）
├── .gitignore              # Git忽略文件
├── docker-compose.yml      # Docker编排
├── README.md               # 项目说明
└── setup_env.ps1           # 环境设置脚本（Windows）
```

## 📂 目录说明

### src/backend/
后端服务代码

- **app/api/**: API路由定义
- **app/core/**: 核心服务（AI服务、智能体、知识库）
- **app/models/**: 数据库模型
- **app/services/**: 业务逻辑服务
- **app/utils/**: 工具函数
- **alembic/**: 数据库迁移脚本

### src/frontend/
前端应用代码

- **app/**: Next.js页面和路由
- **components/**: React组件
- **lib/**: 工具库（API客户端等）
- **stores/**: Zustand状态管理

### docs/
项目文档目录

所有重要的说明文档都在这里，包括：
- 快速开始、开发指南、测试说明
- API文档、架构设计、数据库设计
- 部署指南、用户指南、FAQ等

### planning/
设计文档目录

包含所有设计文档：
- 需求分析、技术架构
- API设计、数据库设计
- 智能体设计、前端设计
- 开发任务清单等

### data/
数据存储目录

- **conversations/**: 对话记录JSON文件
- **app.db**: SQLite数据库文件（开发环境）

### 根目录文件

- **note.md, question.md, flowchart.md**: 用户原始文档（保留）
- **note_organized.md**: 整理后的笔记（保留）
- **重要的事_价值观.csv** 等: 知识库CSV文件（保留）
- **.env.example**: 环境变量模板
- **docker-compose.yml**: Docker编排文件
- **README.md**: 项目说明

## 🔍 文件查找指南

### 查找API接口
→ `src/backend/app/api/v1/`

### 查找业务逻辑
→ `src/backend/app/services/`

### 查找数据模型
→ `src/backend/app/models/`

### 查找前端组件
→ `src/frontend/components/`

### 查找文档
→ `docs/` 目录

### 查找设计文档
→ `planning/` 目录

## 📝 注意事项

1. **用户原始文档**: `note.md`, `question.md`, `flowchart.md` 等保留在根目录
2. **项目文档**: 所有生成的说明文档（全大写文件名）已整理到 `docs/` 目录
3. **设计文档**: `planning/` 目录包含所有设计文档
4. **数据文件**: CSV和Markdown知识库文件保留在根目录，便于访问
