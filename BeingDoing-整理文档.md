# BeingDoing 项目目录整理文档

> 目的：梳理每个目录/文件的职责，标注哪些需要保留、哪些可以清理或转存。
> 审查日期：2026-04-02

---

## 一、目录总览与分级

### 🟢 核心保留（生产必需，长期 review）

| 路径 | 职责 | 说明 |
|------|------|------|
| `src/backend/` | Python 后端全部代码 | FastAPI + LangGraph，核心业务 |
| `src/frontend/` | TypeScript 前端全部代码 | Next.js 14 App Router |
| `.env` | 环境变量配置 | 密钥、LLM 配置、数据库连接（不入 Git） |
| `app.db` | SQLite 生产数据库 | 用户数据（不入 Git，需备份策略） |
| `start.sh` | tmux 服务管理脚本 | 开发和生产环境启动入口 |
| `data/` | 运行时数据目录 | 用户对话记录、知识库数据、备份 |
| `deploy/` | 部署配置 | systemd 服务文件、nginx 配置 |
| `test/` | 测试代码 | pytest 后端测试 |
| `report/` | PDF 导出工具 | Playwright 导出优势报告，独立 node 项目 |
| `docker-compose.yml` | 容器编排 | Docker 部署配置 |
| `pytest.ini` | 测试配置 | pytest 路径和选项 |
| `pyproject.toml` | Python 工具配置 | Black、isort、mypy 配置（在 src/backend 下） |

### 🟡 有价值但可精简（文档/参考类）

| 路径 | 职责 | 建议 |
|------|------|------|
| `CLAUDE.md` | Claude Code 上下文 | **保留**，保持更新 |
| `AGENTS.md` | AI 编程助手规范 | **保留**，是最完整的项目规范文档 |
| `claude-开发文档.md` | 开发测试规范 | **保留**，刚创建的规范文档 |
| `README.md` | 项目说明 | **保留**，精简冗余部分 |
| `docs/` | 项目文档集 | **精简**，见下方详细分析 |
| `*.csv`（3 个中文名 CSV） | 知识库源数据 | **保留**，Agent 运行时读取 |
| `question.md` | 问题库原始文本 | **保留**，业务内容 |

### 🔴 建议删除或转存

| 路径 | 内容 | 建议 |
|------|------|------|
| `.bak_data/` | 旧数据备份 | **删除或转存到外部存储**，非代码仓库内容 |
| `.duplicate/` | 旧版 .env、start.sh 等副本 | **删除**，已有 Git 历史可追溯 |
| `kimi/` | Kimi AI 生成的 6 篇分析文档 | **转存到 docs/archive/**，参考价值但非必需 |
| `wiki/` | 早期 wiki 文档（环境配置、调试等） | **转存到 docs/archive/**，多数内容已过时或与 docs/ 重复 |
| `picture/` | 知识库参考图片（18 张 PNG） | **转存到外部存储或 data/static/**，不应在代码仓库根目录 |
| `uidesign/` | UI 设计稿、HTML 原型、参考代码 | **转存到外部存储**，设计阶段产物，代码已实现 |
| `planning/` | 早期规划文档（需求分析、架构设计等） | **转存到 docs/archive/**，已完成的规划，不再指导开发 |
| `logs/` | 空目录 | **删除** |
| `note.md` | 个人笔记（32KB） | **删除或转存**，个人参考内容 |
| `note_organized.md` | 整理版笔记（24KB） | **删除或转存** |
| `mydesign_note.md` | 设计笔记 | **删除或转存** |
| `flowchart.md` | 流程图描述 | **转存到 docs/**，如仍有参考价值 |
| `功能列表与页面列表.md` | 功能清单 | **删除或转存**，早期规划产物 |
| `TESTING.md` | 根目录测试说明 | **删除**，与 docs/TESTING.md 重复 |
| `setup_env.sh` / `setup_env.ps1` | 环境初始化脚本 | **考虑删除**，start.sh 已覆盖大部分功能 |
| `run_tests.sh` / `run_tests.ps1` | 测试运行脚本 | **考虑删除**，直接用 pytest 即可 |
| `debug.sh` | 调试脚本 | **删除**，临时调试用 |
| `.vscode/` | VS Code 配置 | **保留**（如团队统一配置），否则 gitignore |
| `.Claude Code/` | Cursor IDE 缓存/计划 | **保留**（IDE 工作文件），但 plans/ 下的旧计划可清理 |
| `.pytest_cache/` | pytest 缓存 | **已在 .gitignore**，无需处理 |

---

## 二、docs/ 目录详细分析

当前 docs/ 有 28 个文件，建议分三层：

### 保留（活跃文档，需持续更新）

| 文件 | 用途 |
|------|------|
| `API_DOCUMENTATION.md` | API 接口文档 |
| `ARCHITECTURE.md` | 系统架构 |
| `DATABASE_SCHEMA.md` | 数据库设计 |
| `DEVELOPMENT.md` | 开发指南 |
| `RUN_LOCALLY.md` | 本地运行指南 |
| `TESTING.md` | 测试说明 |
| `QUICK_START.md` | 快速开始 |
| `DEPLOYMENT.md` | 部署指南 |
| `DOCKER.md` | Docker 部署 |
| `DATA_STORAGE_SIMPLE.md` | Simple 模式数据存储说明 |
| `PROMPT_TUNING.md` | 提示词调优 |
| `ADMIN_SANDBOX_FORK.md` | 管理员沙箱功能 |
| `design_principle.md` | 设计原则 |
| `INDEX.md` | 文档索引 |
| `SYSTEMD_SERVICES.md` | systemd 部署 |

### 可转存到 docs/archive/（历史参考，不再更新）

| 文件 | 原因 |
|------|------|
| `architecture-guide.md` | 与 ARCHITECTURE.md 重复，18KB 更详细版 |
| `development-v2.4.md` | 旧版开发文档 |
| `TESTING_GUIDE_v2.4.md` | 旧版测试文档 |
| `REQUEST_FLOW.md` / `.html` | 请求流程图，93KB，参考用 |
| `FLOW_REFACTOR_PLAN.md` | 已完成的重构计划 |
| `PROGRESSIVE_GUIDANCE.md` | 渐进式引导设计文档 |
| `PROJECT_STRUCTURE.md` | 与 AGENTS.md 中的结构描述重复 |
| `USER_GUIDE.md` | 用户指南 |
| `BACKGROUND4_COLOR_ANALYSIS.md` | 背景色分析，设计阶段产物 |
| `DESIGN.md` | 早期设计文档 |
| `README.md` (docs 下的) | 文档目录说明，INDEX.md 已替代 |
| `design-sonnet` | 内容仅 27 字节 |

### 建议删除

| 文件 | 原因 |
|------|------|
| `ADMIN_403_TROUBLESHOOTING.md` | 特定问题排查，修复后无需保留 |

---

## 三、src/ 核心代码重点模块

### 后端重点（长期 review）

| 路径 | 重要度 | 说明 |
|------|--------|------|
| `app/core/agent/` | ⭐⭐⭐ | LangGraph 智能体，核心交互逻辑 |
| `app/core/llmapi/` | ⭐⭐⭐ | LLM 统一接口层 |
| `app/domain/` | ⭐⭐⭐ | 业务知识层（步骤、提示词、知识配置） |
| `app/api/v1/chat*.py` | ⭐⭐⭐ | 对话 API，核心用户交互 |
| `app/api/v1/auth.py` | ⭐⭐ | 认证安全 |
| `app/services/` | ⭐⭐ | 业务逻辑层 |
| `app/models/` | ⭐⭐ | 数据模型定义 |
| `app/config/settings.py` | ⭐⭐ | 全局配置 |
| `app/core/knowledge/` | ⭐⭐ | 知识库检索 |
| `app/utils/` | ⭐ | 工具函数 |
| `app/core/asr/`, `app/core/tts/` | ⭐ | 可选语音功能，非核心 |

### 前端重点（长期 review）

| 路径 | 重要度 | 说明 |
|------|--------|------|
| `app/(main)/explore/` | ⭐⭐⭐ | 探索流程页面，核心用户路径 |
| `components/explore/` | ⭐⭐⭐ | 探索相关组件 |
| `lib/api/` | ⭐⭐⭐ | API 调用封装层 |
| `stores/` | ⭐⭐ | Zustand 状态管理 |
| `app/auth/` | ⭐⭐ | 认证页面 |
| `app/(main)/dashboard/` | ⭐⭐ | 仪表盘 |
| `app/(main)/admin/` | ⭐⭐ | 管理后台 |
| `components/admin/` | ⭐ | 管理后台组件 |
| `components/layout/` | ⭐ | 布局组件 |

---

## 四、建议执行的清理操作

### 第一步：立即可做（低风险）

```bash
# 1. 删除空目录
rm -rf logs/

# 2. 删除明确的临时/重复文件
rm -f debug.sh
rm -f TESTING.md                      # 根目录的，docs/下有
rm -f docs/design-sonnet              # 仅27字节

# 3. 删除备份副本目录
rm -rf .duplicate/
```

### 第二步：创建归档目录并转存

```bash
# 创建归档目录
mkdir -p docs/archive
mkdir -p docs/archive/kimi-analysis
mkdir -p docs/archive/planning
mkdir -p docs/archive/wiki

# 转存 kimi 分析文档
mv kimi/* docs/archive/kimi-analysis/
rmdir kimi

# 转存早期规划
mv planning/* docs/archive/planning/
rmdir planning

# 转存 wiki
mv wiki/* docs/archive/wiki/
rmdir wiki

# 转存过时的 docs 文件
mv docs/architecture-guide.md docs/archive/
mv docs/development-v2.4.md docs/archive/
mv docs/TESTING_GUIDE_v2.4.md docs/archive/
mv docs/REQUEST_FLOW.md docs/archive/
mv docs/REQUEST_FLOW.html docs/archive/
mv docs/FLOW_REFACTOR_PLAN.md docs/archive/
mv docs/PROGRESSIVE_GUIDANCE.md docs/archive/
mv docs/PROJECT_STRUCTURE.md docs/archive/
mv docs/BACKGROUND4_COLOR_ANALYSIS.md docs/archive/
mv docs/DESIGN.md docs/archive/
mv docs/README.md docs/archive/
mv docs/ADMIN_403_TROUBLESHOOTING.md docs/archive/

# 转存根目录笔记
mv note.md docs/archive/
mv note_organized.md docs/archive/
mv mydesign_note.md docs/archive/
mv flowchart.md docs/archive/
mv 功能列表与页面列表.md docs/archive/
```

### 第三步：需确认后执行

| 操作 | 需要确认 |
|------|----------|
| 删除 `.bak_data/` | 确认这些旧备份不再需要 |
| 转存 `picture/` 到外部存储 | 确认知识库图片不被代码引用 |
| 转存 `uidesign/` 到外部存储 | 确认设计稿不再需要参考 |
| 删除 `setup_env.sh` / `setup_env.ps1` | 确认 start.sh 已完全替代 |
| 删除 `run_tests.sh` / `run_tests.ps1` | 确认团队直接使用 pytest |

### 第四步：更新 .gitignore

建议在 `.gitignore` 中补充：

```gitignore
# 归档文档（如果不想跟踪）
docs/archive/

# IDE 文件
.vscode/
.cursor/

# 备份
.bak_data/
.duplicate/
```

---

## 五、清理后的目标结构

```
BeingDoing/
├── src/
│   ├── backend/          # 后端代码（核心）
│   └── frontend/         # 前端代码（核心）
├── test/                 # 测试代码
├── data/                 # 运行时数据
├── deploy/               # 部署配置
├── report/               # PDF 导出工具
├── docs/                 # 活跃文档（~15个）
│   └── archive/          # 归档文档（历史参考）
├── .env                  # 环境变量
├── app.db                # 数据库
├── start.sh              # 服务管理
├── docker-compose.yml    # 容器编排
├── pytest.ini            # 测试配置
├── *.csv                 # 知识库数据（3个）
├── question.md           # 问题库
├── CLAUDE.md             # Claude Code 上下文
├── AGENTS.md             # AI 编程助手规范
├── claude-开发文档.md     # 开发规范
├── README.md             # 项目说明
└── .gitignore
```

根目录从 **30+ 个可见文件/目录** 精简到 **~17 个**，结构清晰，职责明确。
