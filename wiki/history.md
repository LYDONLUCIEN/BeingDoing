# 变更历史（按时间倒序）

> 说明：根据 `wiki/CURSOR.md` 要求，这里记录每次较大的开发 / 文档调整的摘要，便于回溯。

---

## 2026-02-04 文档结构精简与 wiki 重构

**目标**：减少环境配置类文档重复，按 CURSOR 规范收敛为 `ENV_SETUP.md / START.md / PROJECT.md` 三个核心入口。

- **新增**
  - `ENV_SETUP.md`：统一环境与依赖安装文档，合并原来分散在 `DEPENDENCIES.md`、`MANUAL_SETUP.md`、`QUICK_SETUP.md` 里的安装步骤和 `.env` 配置说明。
  - `START.md`：统一起步指南，面向「体验用户」与「开发者」串联从克隆仓库到跑通基础测试和启动前后端的最小路径。
  - `PROJECT.md`：项目结构与组件关系说明，整理顶层目录、后端/前端结构、数据与知识库、测试与文档体系关系。

- **调整 / 精简**
  - `DEPENDENCIES.md`：改为**仅列依赖**的参考手册，移除所有安装步骤，统一指向 `ENV_SETUP.md` / `START.md`。
  - `MANUAL_SETUP.md`：改为说明「内容已合并至 `ENV_SETUP.md` / `START.md`」的占位页，避免旧链接失效。
  - `QUICK_SETUP.md`：改为重定向说明，明确快速手动配置已并入 `ENV_SETUP.md` 与 `START.md`。
  - `QUICK_START.md`：改为重定向说明，所有第一阶段测试的快速说明并入 `START.md`，详细测试说明指向 `docs/TESTING.md`。

- **保留但未动的 wiki 文档**
  - `CURSOR.md`：开发与文档规范。
  - `DEVELOPMENT.md`：开发流程与代码规范。
  - `DEPLOYMENT.md`：部署指南（本地 / Docker / 阿里云）。
  - `PROJECT_STATUS.md`：项目阶段与功能完成度。
  - `MERMAID_RENDERING.md`：Mermaid 流程图渲染帮助。

> 影响：之后新增环境/起步相关内容时，应优先修改 `ENV_SETUP.md` / `START.md` / `PROJECT.md`，避免再在多个文档中复制同一段说明。

