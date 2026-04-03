# BeingDoing 开发规范文档

> 本文档是 AI 编程助手（Claude Code / Claude Code / Copilot 等）在本项目中必须遵循的开发、测试、设计规范。
> 请将本文档路径配置到各工具的上下文加载机制中（见文末"如何让不同模型每次都调用"一节）。

---

## 一、项目语言约定

- **代码注释**：中文
- **Git commit message**：中文，格式：`<类型>: <简要描述>`
  - 类型：`功能` / `修复` / `优化` / `重构` / `文档` / `测试` / `部署`
  - 示例：`功能: 新增rumination反思对话流程`
- **变量/函数命名**：英文，Python 用 snake_case，TypeScript 用 camelCase
- **文件命名**：英文（知识库 CSV 文件除外，保留中文名）

---

## 二、代码规范

### Python 后端

| 项目 | 规范 |
|------|------|
| 格式化 | Black, line-length=100, target py310 |
| 导入排序 | isort, profile=black |
| 类型检查 | mypy (ignore_missing_imports=true) |
| 文档字符串 | Google 风格中文注释 |
| 异步 | 所有数据库操作和 LLM 调用必须 async/await |

**后端分层规则**（严格遵守，不可跨层调用）：
```
API 路由层 (api/v1/)        ← 只做参数校验和响应封装
    ↓ 调用
业务服务层 (services/)       ← 业务编排，不直接操作数据库
    ↓ 调用
核心服务层 (core/)           ← LLM、Agent、Knowledge、Database
领域层     (domain/)         ← 步骤定义、提示词模板、知识配置
```

**禁止事项**：
- 禁止在 `api/v1/` 中直接写业务逻辑或数据库查询
- 禁止在 `services/` 中直接构造 LLM prompt（应使用 `domain/prompts/`）
- 禁止硬编码 API key 或密钥，一律走 `app/config/settings.py` → `.env`

### TypeScript 前端

| 项目 | 规范 |
|------|------|
| Lint | ESLint (next lint) |
| 类型 | strict 模式，禁止 any（除第三方库适配） |
| 状态管理 | Zustand store 统一放 `stores/` |
| API 调用 | 统一通过 `lib/api/` 封装，不在组件中直接调 axios |
| 路由 | Next.js App Router, 页面组件在 `app/` 下 |

**组件规则**：
- 可复用组件放 `components/<功能域>/`
- 页面级组件放 `app/(main)/<页面>/` 内
- 所有 API 响应类型定义在 `lib/api/` 对应文件中

---

## 三、Git 工作流

### 分支规范
- `main` — 生产分支，必须通过测试
- `dev/<功能名>` — 功能开发分支
- `fix/<问题描述>` — 修复分支
- `refactor/<描述>` — 重构分支

### 提交前检查清单
1. Python: `black --check .` 和 `isort --check .`（在 `src/backend` 下）
2. TypeScript: `npm run lint`（在 `src/frontend` 下）
3. 后端测试: `pytest test/backend -v`（从项目根目录）
4. 前端构建: `npm run build`（确保无编译错误）

### 每次提交必须包含
- 清晰的 commit message（中文，带类型前缀）
- 如涉及 API 变更，同步更新 `docs/API_DOCUMENTATION.md`
- 如涉及数据库变更，创建 Alembic migration

---

## 四、测试规范

### 后端测试
- 测试文件位于 `test/backend/`，结构镜像 `src/backend/app/`
- 文件名: `test_<模块名>.py`
- 使用 pytest + asyncio_mode=auto
- 从项目根目录运行: `pytest test/backend -v`
- 单个测试: `pytest test/backend/core/agent/test_graph.py::test_xxx -v`

### 新增代码测试要求
- 新增 API 端点 → 必须写对应的路由测试
- 新增 service 方法 → 必须写单元测试
- 修改 Agent 节点/工具 → 必须验证 graph 流程测试通过
- Bug 修复 → 补充能复现该 bug 的测试用例

---

## 五、数据库变更规范

```bash
cd src/backend

# 1. 修改 models/ 中的模型定义
# 2. 生成迁移脚本
alembic revision --autogenerate -m "描述变更内容"

# 3. 检查生成的迁移脚本（在 alembic/versions/ 下）
# 4. 应用迁移
alembic upgrade head

# 5. 如需回滚
alembic downgrade -1
```

**注意**：SQLite 不支持部分 ALTER TABLE 操作，复杂迁移可能需要手动编写迁移脚本。

---

## 六、LLM / Agent 变更规范

- **提示词修改**：只改 `src/backend/app/domain/prompts/templates/*.yaml`，不要在代码中硬编码
- **Agent 节点修改**：改 `src/backend/app/core/agent/nodes/`
- **Agent 工具修改**：改 `src/backend/app/core/agent/tools/`
- **流程步骤修改**：改 `src/backend/app/domain/steps.py`
- **知识库配置**：改 `src/backend/app/domain/knowledge_config.py`

每次修改 prompt 模板后，务必在本地跑一次完整对话流程验证效果。

---

## 七、环境与部署

### 关键环境变量（.env）
- `ARCHITECTURE_MODE=simple` — 当前使用 simple 模式（SQLite + 内存缓存）
- `LLM_PROVIDER` — 可选: deepseek / openai / glm / kimi
- `AUDIO_MODE=False` — 语音功能默认关闭
- `FRONTEND_MODE` — dev / production，影响 start.sh 前端启动方式

### 服务管理
- 开发使用 `./start.sh start-dev`（tmux 管理后端+前端）
- 生产使用 `./start.sh start-run`（自动清理 .next 缓存并重新构建）
- systemd 服务配置在 `deploy/systemd/`

---

## 八、文件操作安全规则

**禁止 AI 修改的文件**：
- `.env` — 包含密钥和 API Key
- `app.db` — 生产数据库
- `data/` 下的用户数据（`data/user/`, `data/conversations/`）
- `deploy/` 下的生产部署配置（修改前必须人工确认）

**修改需谨慎的文件**：
- `src/backend/app/main.py` — 应用入口，中间件注册
- `src/backend/app/config/settings.py` — 全局配置
- `start.sh` — 服务编排脚本
- `docker-compose.yml` — 容器编排

---

## 九、版本维护与变更记录

### 每次有意义的功能变更后，必须更新以下文件：

1. **本文档** (`claude-开发文档.md`) — 如果规范本身需要调整
2. **AGENTS.md** — 如果架构、API路由、项目结构发生变化
3. **CLAUDE.md** — 如果构建命令或核心架构变化
4. **docs/API_DOCUMENTATION.md** — 如果 API 接口变化

### Git Tag 规范
- 每个可部署版本打 tag: `v<主版本>.<次版本>.<修订>`
- Tag message 记录本版本的关键变更

---

## 十、如何让不同 AI 编程工具每次都加载本文档

### Claude Code (claude.ai/code)
本文档已在项目根目录，Claude Code 会自动读取 `CLAUDE.md`。将本文档的关键规范合并到 `CLAUDE.md` 中，或者在 `CLAUDE.md` 头部加入引用：
```markdown
开发规范请严格遵循 [claude-开发文档.md](./claude-开发文档.md)。
```

### Cursor
在 `.cursor/rules/` 目录下创建规则文件（或使用 `.cursorrules` 文件），引用本文档：
```
# .Claude Coderules 或 .Claude Code/rules/dev-spec.mdc
请严格遵循项目根目录下 claude-开发文档.md 中的所有开发规范。
每次修改代码前先读取该文件确认规范要求。
```

### GitHub Copilot
在 `.github/copilot-instructions.md` 中引用：
```markdown
请遵循项目根目录 claude-开发文档.md 中定义的代码规范、分层架构、提交规范。
```

### 通用做法
- 在项目根目录维护本文档，AI 工具通常会自动扫描根目录 `.md` 文件
- 确保 `AGENTS.md`（已有）和本文档保持同步
- 每次 code review 时检查 AI 生成的代码是否符合本文档规范

### 保持文档自身的更新
- 每次新增重大功能或架构调整后，review 本文档是否需要更新
- 可以在 `start.sh` 或 CI 流程中加入提示：检查文档是否与代码一致
- 建议每月做一次文档-代码一致性审查
