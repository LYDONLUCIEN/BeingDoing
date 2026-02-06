# 根目录文件说明文档

本文档详细说明项目根目录下所有文件的作用和用途，特别是那些全大写的Markdown文档和启动脚本。

---

## 📋 目录结构概览

```
BeingDoing/
├── 📄 大写的Markdown文档（12个）
├── 🔧 启动脚本（4个）
├── ⚙️ 配置文件（2个）
├── 📚 项目文档（4个）
├── 📊 数据文件（3个CSV）
└── 📁 子目录（src/, test/, docs/, planning/等）
```

---

## 📄 大写的Markdown文档（12个）

### 1. **README.md** - 项目主文档
**作用**：项目的入口文档，提供项目概览和快速开始指南

**主要内容**：
- 项目简介：智能引导系统，帮助用户找到真正想做的事
- 核心公式：喜欢的事 × 擅长的事 × 重要的事 = 真正想做的事
- 项目结构说明
- 快速开始步骤（5分钟启动）
- 功能特性列表
- 技术栈介绍（后端FastAPI、前端Next.js）
- 文档索引（指向docs/目录下的详细文档）

**使用场景**：新用户了解项目、快速上手

---

### 2. **CURSOR.md** - Cursor开发规范
**作用**：定义使用Cursor AI进行开发的规范和流程

**主要内容**：
- 开发任务需要形成详细的todo list
- 完成开发后需要更新todo list的完成状态
- 代码自动在根目录下的test里生成单元测试用例
- 如果测试发现错误，需要更新todo list状态为debug中

**使用场景**：使用Cursor AI进行开发时的规范参考

---

### 3. **DEPENDENCIES.md** - 依赖清单与环境配置
**作用**：详细说明项目所需的所有依赖和系统要求

**主要内容**：
- 系统要求（Python 3.10+、Node.js 18+）
- Python依赖清单（Web框架、数据库、AI/智能体、测试等）
- Node.js依赖清单（前端框架、构建工具、代码质量工具）
- 环境配置步骤（Python环境、Node.js环境、环境变量）
- 依赖安装命令
- 注意事项和常见问题解决方案

**使用场景**：安装依赖、解决依赖问题、了解项目技术栈

---

### 4. **DEPLOYMENT.md** - 部署指南
**作用**：说明如何部署项目到不同环境

**主要内容**：
- 本地开发部署（后端、前端启动命令）
- Docker部署（docker-compose使用）
- 阿里云部署（ECS实例配置）
- 环境变量说明
- 注意事项（权限、数据库、安全等）

**使用场景**：部署项目到生产环境或本地开发环境

---

### 5. **DEVELOPMENT.md** - 开发指南
**作用**：开发环境设置和开发流程说明

**主要内容**：
- 环境设置（后端、前端）
- 运行测试（后端、前端测试命令）
- 代码规范（Python、TypeScript）
- 项目结构说明
- 开发流程（从todolist选择任务到提交代码）
- 注意事项

**使用场景**：日常开发参考、新开发者入门

---

### 6. **ENV_SETUP.md** - 环境变量配置说明
**作用**：详细说明环境变量配置方法

**主要内容**：
- .env.example文件说明
- .env文件说明（位置、作用、安全）
- 必须配置的变量（SECRET_KEY、OPENAI_API_KEY等）
- .ps1文件说明（PowerShell脚本）
- 快速开始步骤
- 常见问题解答

**使用场景**：配置环境变量、理解.ps1脚本

---

### 7. **MANUAL_SETUP.md** - 手动环境配置指南
**作用**：如果自动脚本无法运行，提供手动配置步骤

**主要内容**：
- 前置要求检查
- Python后端环境配置（Windows/Linux/Mac）
- Node.js前端环境配置
- 创建环境变量文件（3种方法）
- 验证安装步骤
- 启动服务命令
- 完整命令清单（可直接复制粘贴）
- 常见问题解决方案

**使用场景**：自动脚本失败时、需要手动配置时

---

### 8. **MERMAID_RENDERING.md** - Mermaid流程图渲染指南
**作用**：说明如何查看项目中的Mermaid流程图

**主要内容**：
- 问题说明（某些编辑器不支持Mermaid）
- 已修复的语法问题
- 如何让流程图正常渲染（3种方法）
- 支持的编辑器列表
- 在线工具推荐
- 测试流程图是否正常

**使用场景**：查看flowchart.md等包含流程图的文档时

---

### 9. **PROJECT_STATUS.md** - 项目开发状态
**作用**：记录项目的开发进度和当前状态

**主要内容**：
- 总体进度（已完成阶段、进行中阶段）
- 核心功能状态表（完成度）
- 技术债务列表
- 下一步计划
- 已知问题

**使用场景**：了解项目进度、规划开发任务

---

### 10. **QUICK_SETUP.md** - 快速手动配置指南
**作用**：5分钟快速配置环境的简化版指南

**主要内容**：
- 快速步骤（Python后端、Node.js前端、.env文件、测试）
- 每个步骤的简要命令
- 完成验证

**使用场景**：快速配置环境、不需要详细说明时

---

### 11. **QUICK_START.md** - 快速开始指南
**作用**：第一阶段测试的快速开始指南

**主要内容**：
- 已完成内容说明
- 快速测试方法（使用脚本或手动运行）
- 预期测试结果
- 项目结构说明
- 测试内容详情
- 下一步计划

**使用场景**：完成环境配置后，验证环境是否正确

---

### 12. **TESTING.md** - 测试指南
**作用**：详细的测试运行和编写指南

**主要内容**：
- 第一阶段测试内容
- 测试环境准备（安装依赖、设置环境变量）
- 运行测试的3种方法
- 测试内容说明（配置模块测试）
- 运行所有测试
- 测试输出示例
- 常见问题解决方案
- 测试最佳实践

**使用场景**：运行测试、编写测试、解决测试问题

---

## 🔧 启动脚本（4个）

### 1. **setup_env.sh** - Linux/Mac环境配置脚本
**作用**：自动配置开发环境（Bash脚本）

**功能**：
- 检查Python和Node.js是否安装
- 创建Python虚拟环境
- 安装Python依赖
- 安装Node.js依赖
- 创建.env文件（如果不存在）

**使用方法**：
```bash
chmod +x setup_env.sh
./setup_env.sh
```

**适用系统**：Linux、macOS

---

### 2. **setup_env.ps1** - Windows环境配置脚本
**作用**：自动配置开发环境（PowerShell脚本）

**功能**：
- 检查Python和Node.js是否安装
- 创建Python虚拟环境
- 安装Python依赖
- 安装Node.js依赖
- 创建.env文件（如果不存在）

**使用方法**：
```powershell
.\setup_env.ps1
```

**如果遇到执行策略限制**：
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.\setup_env.ps1
```

**适用系统**：Windows

---

### 3. **run_tests.sh** - Linux/Mac测试运行脚本
**作用**：自动运行第一阶段测试（Bash脚本）

**功能**：
- 设置PYTHONPATH环境变量
- 运行配置模块测试

**使用方法**：
```bash
chmod +x run_tests.sh
./run_tests.sh
```

**适用系统**：Linux、macOS

---

### 4. **run_tests.ps1** - Windows测试运行脚本
**作用**：自动运行第一阶段测试（PowerShell脚本）

**功能**：
- 设置PYTHONPATH环境变量
- 运行配置模块测试

**使用方法**：
```powershell
.\run_tests.ps1
```

**适用系统**：Windows

---

## ⚙️ 配置文件（2个）

### 1. **docker-compose.yml** - Docker部署配置
**作用**：定义Docker容器编排配置

**包含服务**：
- `backend`：后端服务（FastAPI）
- `frontend`：前端服务（Next.js）
- `db`：PostgreSQL数据库

**主要配置**：
- 端口映射（8000、3000、5432）
- 环境变量传递
- 数据卷挂载（数据文件、CSV文件）
- 服务依赖关系

**使用方法**：
```bash
docker-compose up -d
```

---

### 2. **pytest.ini** - pytest测试配置
**作用**：配置pytest测试框架

**主要配置**：
- `testpaths = test`：测试文件路径
- `pythonpath = src/backend`：Python路径
- `asyncio_mode = auto`：异步测试模式
- `addopts = -v --tb=short`：默认选项

**作用**：无需手动设置PYTHONPATH，pytest会自动使用配置的路径

---

## 📚 项目文档（4个）

### 1. **note.md** - 读书笔记
**作用**：从《如何找到想做的事》一书中提取的原始笔记

**内容**：131个笔记，包含：
- 核心公式
- 价值观、才能、兴趣的探索方法
- 常见误区
- 实践案例

**来源**：微信读书

---

### 2. **note_organized.md** - 整理后的读书笔记
**作用**：对note.md进行结构化整理

**内容分类**：
- 核心公式
- 核心结论类
- 误区类（5个常见误区）
- 方法类（自我认知法规则、探索方法）
- 说明类（本质、判断标准、工作选择）
- 举例类（作者案例、他人案例、生活状态）
- 流程图（Mermaid格式）
- 实践建议

**使用场景**：快速查找特定内容、理解核心概念

---

### 3. **question.md** - 问题清单
**作用**：包含90个自我探索问题

**内容结构**：
- **第一部分**：找到自己重要的事（价值观）- 30个问题
- **第二部分**：找到自己擅长的事（才能）- 30个问题
- **第三部分**：找到自己喜欢的事（热情）- 30个问题

**使用场景**：用户进行自我探索时回答这些问题

---

### 4. **flowchart.md** - 流程图文档
**作用**：可视化展示找到"真正想做的事"的完整流程

**内容**：
- 完整流程图（Mermaid格式）
- 简化版流程图
- 流程图关键节点说明
- 流程图使用指南
- 对应页码参考
- 问题清单对应关系
- 渲染说明和修复说明

**使用场景**：理解探索流程、指导用户进行自我探索

---

## 📊 数据文件（3个CSV）

### 1. **重要的事_价值观.csv**
**作用**：存储价值观相关的数据

**用途**：知识库数据，用于系统检索和引导

---

### 2. **擅长的事_才能.csv**
**作用**：存储才能相关的数据

**用途**：知识库数据，用于系统检索和引导

---

### 3. **喜欢的事_热情.csv**
**作用**：存储热情相关的数据

**用途**：知识库数据，用于系统检索和引导

---

## 📁 其他重要目录

### **src/** - 源代码目录
- `src/backend/`：后端代码（FastAPI + Python）
- `src/frontend/`：前端代码（Next.js + TypeScript）

### **test/** - 测试代码目录
- `test/backend/`：后端测试代码

### **docs/** - 详细文档目录
- 包含更详细的API文档、架构设计、数据库设计等

### **planning/** - 设计文档目录
- 包含需求分析、技术架构、API设计等规划文档

---

## 🚀 快速开始流程

### 对于新用户：

1. **阅读 README.md** - 了解项目
2. **阅读 DEPENDENCIES.md** - 了解依赖要求
3. **运行 setup_env.sh/setup_env.ps1** - 自动配置环境
   - 或参考 MANUAL_SETUP.md 手动配置
4. **配置 .env 文件** - 参考 ENV_SETUP.md
5. **运行 run_tests.sh/run_tests.ps1** - 验证环境
6. **阅读 QUICK_START.md** - 开始使用

### 对于开发者：

1. **阅读 DEVELOPMENT.md** - 了解开发流程
2. **阅读 CURSOR.md** - 了解开发规范
3. **查看 PROJECT_STATUS.md** - 了解项目进度
4. **参考 TESTING.md** - 运行和编写测试

### 对于部署人员：

1. **阅读 DEPLOYMENT.md** - 了解部署步骤
2. **使用 docker-compose.yml** - Docker部署
3. **配置环境变量** - 参考 ENV_SETUP.md

---

## 📝 文档关系图

```
README.md (入口)
    ├── 快速开始 → QUICK_START.md
    ├── 环境配置 → ENV_SETUP.md / MANUAL_SETUP.md / QUICK_SETUP.md
    ├── 依赖安装 → DEPENDENCIES.md
    ├── 开发指南 → DEVELOPMENT.md
    ├── 测试指南 → TESTING.md
    ├── 部署指南 → DEPLOYMENT.md
    └── 项目状态 → PROJECT_STATUS.md

项目文档
    ├── note.md (原始笔记)
    ├── note_organized.md (整理笔记)
    ├── question.md (问题清单)
    └── flowchart.md (流程图)

启动脚本
    ├── setup_env.sh / setup_env.ps1 (环境配置)
    └── run_tests.sh / run_tests.ps1 (测试运行)
```

---

## 🔍 文件查找指南

### 想了解项目整体？
→ 阅读 **README.md**

### 想配置开发环境？
→ 运行 **setup_env.sh/setup_env.ps1** 或参考 **MANUAL_SETUP.md**

### 想了解依赖？
→ 阅读 **DEPENDENCIES.md**

### 想运行测试？
→ 运行 **run_tests.sh/run_tests.ps1** 或参考 **TESTING.md**

### 想了解开发流程？
→ 阅读 **DEVELOPMENT.md** 和 **CURSOR.md**

### 想部署项目？
→ 阅读 **DEPLOYMENT.md** 和使用 **docker-compose.yml**

### 想了解项目进度？
→ 阅读 **PROJECT_STATUS.md**

### 想理解核心概念？
→ 阅读 **note_organized.md** 和 **flowchart.md**

### 想查看问题清单？
→ 阅读 **question.md**

### 流程图无法显示？
→ 阅读 **MERMAID_RENDERING.md**

---

## ⚠️ 注意事项

1. **环境变量文件**：`.env` 文件不会被提交到Git（在.gitignore中），需要从`.env.example`复制创建

2. **脚本执行权限**：Linux/Mac系统需要给.sh脚本添加执行权限：
   ```bash
   chmod +x setup_env.sh run_tests.sh
   ```

3. **PowerShell执行策略**：Windows系统如果无法运行.ps1脚本，需要调整执行策略

4. **Python路径**：pytest.ini已配置pythonpath，从根目录运行pytest无需手动设置

5. **文档更新**：项目文档会随着开发进度更新，建议定期查看PROJECT_STATUS.md

---

## 📞 获取帮助

- 查看对应文档的"常见问题"部分
- 查看 **docs/FAQ.md**（如果存在）
- 查看项目的Issue和Pull Request

---

**最后更新**：请参考各文档的修改时间

**维护者**：项目开发团队
