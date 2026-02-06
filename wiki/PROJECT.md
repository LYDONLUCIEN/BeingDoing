# 项目开发状态

## 总体进度

### ✅ 已完成阶段

1. **Phase 0: 项目初始化与基础设施** (100%)
   - ✅ 项目结构搭建
   - ✅ 数据库设计与初始化
   - ✅ 配置管理系统

2. **Phase 1: 核心AI服务** (100%)
   - ✅ LLM API接口（OpenAI Provider）
   - ✅ ASR API接口（OpenAI Whisper）
   - ✅ TTS API接口（OpenAI TTS）

3. **Phase 2: 数据层与知识库** (100%)
   - ✅ 知识库加载模块
   - ✅ 知识检索模块
   - ✅ 向量存储接口（保留）
   - ✅ 数据库操作层
   - ✅ 对话记录文件管理

4. **Phase 3: 智能体框架** (100%)
   - ✅ LangGraph基础框架
   - ✅ ReAct范式实现
   - ✅ 工具定义与实现
   - ✅ 上下文管理模块

5. **Phase 4: 业务逻辑层** (100%)
   - ✅ 用户认证服务
   - ✅ 用户信息收集服务
   - ✅ 问题服务
   - ✅ 回答服务
   - ✅ 进度管理服务
   - ✅ 引导服务
   - ✅ 导出服务

6. **Phase 5: API接口层** (100%)
   - ✅ 认证API
   - ✅ 用户信息API
   - ✅ 会话管理API
   - ✅ 问题API
   - ✅ 回答API
   - ✅ 对话API
   - ✅ 内容检索API
   - ✅ 语音API（可选）
   - ✅ 公式和流程API
   - ✅ 导出API
   - ✅ 配置查询API

7. **Phase 6: 前端基础** (100%)
   - ✅ 前端项目初始化
   - ✅ API服务层
   - ✅ 状态管理
   - ✅ 认证页面

8. **Phase 7: 前端核心功能** (80%)
   - ✅ 用户信息收集页面
   - ✅ 探索流程页面基础布局
   - ✅ 步骤引导组件
   - ✅ 问题展示组件
   - ✅ 回答输入组件
   - ✅ 对话助手组件
   - ✅ 进度展示组件
   - ⏳ 探索流程完整功能（待完善）
   - ⏳ 结果展示页面（待实现）

### ⏳ 进行中/待完成

- **Phase 8: 集成与优化** (0%)
  - ⏳ 前后端集成测试
  - ⏳ 性能优化
  - ⏳ Docker部署配置
  - ⏳ 文档完善

## 核心功能状态

| 功能模块 | 状态 | 完成度 |
|---------|------|--------|
| 用户认证 | ✅ | 100% |
| 用户信息收集 | ✅ | 100% |
| 探索流程 | ✅ | 90% |
| 智能引导 | ✅ | 90% |
| 对话系统 | ✅ | 90% |
| 知识库检索 | ✅ | 100% |
| 数据导出 | ✅ | 100% |
| 语音功能 | ⏳ | 接口完成，待测试 |
| 向量检索 | ⏳ | 接口保留，未实现 |

## 技术债务

1. **测试覆盖**
   - 后端单元测试：部分完成
   - 前端测试：未开始
   - E2E测试：未开始

2. **错误处理**
   - 需要更完善的错误处理机制
   - 需要用户友好的错误提示

3. **性能优化**
   - 对话历史加载优化
   - 知识库检索性能优化
   - 前端渲染优化

4. **安全性**
   - API限流（待实现）
   - 输入验证增强
   - SQL注入防护检查

## 下一步计划

1. 完善探索流程页面功能
2. 实现结果展示页面
3. 前后端集成测试
4. Docker部署配置完善
5. 性能优化和错误处理改进

## 已知问题

1. LangGraph状态图运行需要进一步测试
2. 对话文件管理器的异步方法需要验证
3. 前端状态持久化需要测试
4. API错误处理需要完善



# PROJECT：项目结构与组件关系

本页是 wiki 中关于 **项目结构 / 目录关系 / 主要组件** 的统一说明，用来满足 `wiki/CURSOR.md` 对 `PROJECT.md` 的要求。

- 如果你想知道「代码大概长什么样、在哪个目录改什么」——看这里。
- 更细的 API、架构设计等，请参考 `docs/` 目录下的专业文档。

---

## 一、顶层目录结构

项目根目录（只列与开发/使用紧密相关的部分）：

```text
BeingDoing/
├── src/                # 源代码（后端 + 前端）
├── test/               # 自动化测试
├── docs/               # 面向用户/开发者的正式文档
├── planning/           # 需求与架构设计稿
├── data/               # 运行时/知识库相关数据
├── *.csv               # 价值观/才能/热情等原始表格
├── note*.md            # 读书笔记（原始 + 整理）
├── question.md         # 自我探索问题清单
├── flowchart.md        # 找到“真正想做的事”的流程图
├── setup_env.sh / .ps1 # 环境配置脚本
├── run_tests.sh / .ps1 # 测试运行脚本
├── docker-compose.yml  # Docker 编排配置
└── wiki/               # 你现在正在看的这些 wiki 文档
```

**互相指向的大致关系：**

- `docs/`：更正式、较长的文档（API、架构、数据库等）
- `wiki/`：为自己用的「导航类」文档（ENV_SETUP / START / PROJECT）
- `planning/`：早期需求与设计记录，不一定与当前实现完全同步

---

## 二、后端结构（src/backend）

后端基于 **FastAPI + SQLAlchemy + LangGraph**，大致结构：

```text
src/backend/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── api/                 # API 路由（v1 分模块）
│   │   ├── v1/
│   │   │   ├── auth.py      # 认证接口
│   │   │   ├── users.py     # 用户信息
│   │   │   ├── sessions.py  # 会话管理
│   │   │   ├── questions.py # 问题列表
│   │   │   ├── answers.py   # 回答相关
│   │   │   ├── chat.py      # 对话接口
│   │   │   ├── search.py    # 内容/知识库检索
│   │   │   ├── audio.py     # 语音 ASR/TTS（可选）
│   │   │   ├── export.py    # 导出结果
│   │   │   └── formula.py   # 公式 / 流程相关
│   │   └── middleware.py    # 中间件（日志、请求上下文等）
│   │
│   ├── core/                # 核心能力（LLM / Agent / 知识 / 音频 / 数据库）
│   │   ├── llmapi/          # LLM 接入（OpenAI / 未来的 Provider）
│   │   ├── agent/           # LangGraph 智能体 + ReAct 流程
│   │   ├── knowledge/       # 知识库加载 + 检索 + 向量接口
│   │   ├── asr/             # 语音识别（Whisper 等）
│   │   ├── tts/             # 语音合成
│   │   └── database/        # 对话/用户等领域数据库操作层
│   │
│   ├── models/              # Pydantic/SQLAlchemy 模型
│   ├── services/            # 业务服务（用户/问题/回答/引导/导出等）
│   ├── utils/               # 工具函数（如对话文件管理）
│   └── config/              # 配置模块（settings / architecture / guide / audio）
│
├── scripts/                 # 运维 / 调试脚本
│   ├── init_db.py           # 初始化数据库
│   └── call_llm.py          # 命令行测试 LLM（含 DeepSeek 等）
└── alembic/                 # 数据库迁移
```

可以粗暴理解为三层：

- **API 层**：`app/api` 负责 HTTP 接口；
- **业务层**：`app/services` 负责「要做什么事」；
- **能力层**：`app/core` + `app/models` + `app/config` 负责「怎么做这件事」。

---

## 三、前端结构（src/frontend）

前端是基于 **Next.js + TypeScript + Zustand + Tailwind** 的应用（具体目录在 `src/frontend` 下，可结合 `docs/PROJECT_STRUCTURE.md` 或 `docs/ARCHITECTURE.md` 一起看）。

典型结构（示意）：

```text
src/frontend/
├── app/            # Next.js 页面与路由
├── components/     # 复用 UI 组件（步骤引导、问题卡片、对话区等）
├── lib/            # 前端工具库（API client、格式化工具等）
└── stores/         # Zustand 状态管理（用户信息、会话、进度等）
```

**与后端的关系：**

- 前端所有业务操作基本都通过 `NEXT_PUBLIC_API_URL` 指向的后端 API 完成；
- 会话、问题、回答、导出等页面，分别调用 `app/api/v1` 下对应路由；
- 进度条 / 引导组件，本质上基于后端的「阶段/步骤」接口和本地状态组合。

---

## 四、数据与知识库

项目中围绕「找到真正想做的事」有一套自己的知识与数据：

- `*.csv`：三张核心表
  - `重要的事_价值观.csv`
  - `擅长的事_才能.csv`
  - `喜欢的事_热情.csv`
- `note*.md`：对《如何找到想做的事》的读书笔记
- `question.md`：按照「价值观 / 才能 / 热情」分组的 90 个问题
- `flowchart.md`：从迷茫到找到“真正想做的事”的完整流程图（Mermaid）

后端的 `app/core/knowledge` 模块负责：

- 加载 CSV/Markdown 等知识源；
- 提供关键词/向量检索接口；
- 为智能体（`app/core/agent`）提供「资料库」能力。

---

## 五、测试与质量保障

- 测试代码：`test/backend`（对应后端模块），前端测试后续补充
- 测试配置：根目录 `pytest.ini` 已设置 `pythonpath = src/backend`
- 快速测试说明：
  - wiki 级：`wiki/START.md`（第一阶段测试）
  - 详细版：`docs/TESTING.md`

推荐实践（对应 `wiki/CURSOR.md` 的要求）：

1. 所有可测试模块，尽量在 `test/backend` 下有对应测试；
2. 每次在功能开发完成后跑一次测试；
3. 如测试不通过，需要在 todo 里把该项状态改为 “debug 中”。

---

## 六、文档体系关系（简版）

- **wiki/**
  - `ENV_SETUP.md`：唯一环境/依赖安装说明
  - `START.md`：如何开始使用和开发项目
  - `PROJECT.md`：你现在正在看的结构/组件说明
  - 其他：`PROJECT_STATUS.md`（进度）、`MERMAID_RENDERING.md`（流程图渲染）等
- **docs/**
  - 更正式、更细的说明：架构、数据库、API、用户指南等
- **planning/**
  - 需求/设计过程记录：需求分析、技术架构、API/数据库设计等

---

## 七、下一步怎么深入？

- 想知道「怎么装环境、怎么跑起来」 → `wiki/ENV_SETUP.md` + `wiki/START.md`
- 想从整体理解技术架构 → `docs/ARCHITECTURE.md` + `docs/PROJECT_STRUCTURE.md`
- 想看目前做到哪一步、还差什么 → `wiki/PROJECT_STATUS.md`

