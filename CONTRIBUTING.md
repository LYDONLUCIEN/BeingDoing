# 贡献规范

## 语言与提交

注释、开发说明及提交信息用中文；变量/函数用英文。Python 使用 snake_case，TypeScript 使用 camelCase。提交格式：`修复: 描述`、`重构: 描述`、`文档: 描述`、`测试: 描述` 等。

`main` 保持发布基线；本次整理在 `clean`。一次提交围绕可审查的问题，禁止把用户数据或密钥放入差异。

## 代码边界

- Python 格式以 `src/backend/pyproject.toml` 为准：Black 100 列、isort black profile。新增/修改接口补充类型与中文说明。
- API 层负责参数、鉴权和响应；业务编排在 services，数据库通用操作在 core/database。现有部分服务直接使用 SQLAlchemy 是存量事实，新增跨接口通用操作应下沉；本次密码重置事务在 UserDB。
- 数据库和 LLM IO 使用 async/await。提示词放在 domain/prompts 或对应已确立的 prompt 模块，API 中不拼业务 prompt。当前 simple-chat 并非全部走 YAML；具体入口见架构文档。
- TypeScript strict；新增代码避免 any（第三方适配确需使用应说明）。API 类型与调用在 lib/api，状态在 stores，可复用界面放 components。
- 用户和模型内容经 SafeMarkdownPreview 渲染；普通字符串交给 React 转义。权限在后端校验，UI 隐藏仅负责交互。
- Schema 变化新增 Alembic migration，确认存量兼容及回滚；保留历史迁移。API 契约变化更新 docs/API_DOCUMENTATION.md，领域变化更新字典/规则，需要长期取舍时记录 ADR。

## 业务决定与实现同步

- 讨论中的跨产品边界记录在 [PRODUCT_EVOLUTION](docs/PRODUCT_EVOLUTION.md)，尚未确认的词义不写入现行业务术语／字段字典。讨论术语与现行术语分区，暂停或尚未实施的规则不自动成为当前开发要求。决定状态、实现验证和部署状态分别记录。
- 改变已确认规则时，说明变更原因、替代关系及受影响模块／接口；同步业务规则、字段含义和行为验收。具有长期取舍的边界变化更新 ADR，普通规则修改不必另建 ADR。
- 同一规则由明确负责的模块实现，调用方通过接口使用；模块粒度根据独立生命周期、数据职责和实际变更范围调整。若规则判断不断复制到多个产品中，先复查职责，避免堆叠例外分支。
- 有存量影响的变更注明兼容期、迁移／回滚与退出条件；验证后清除被替代的运行路径和过期测试，保留历史解释及替代链接。不能仅更新文档而宣称代码迁移完成。

## 提交前检查

从根目录执行后端测试 `python -m pytest test/backend`；前端执行 `npm run lint`、`npm run test:security`、`npm run build`。涉及渲染器时运行它的 `npm test` 并核对 dist。

在后端目录运行 Black/isort 全量只读检查；变更文件须符合格式。仓库现存格式债和失败测试不能通过大范围无关重排、删除测试或静默跳过隐藏。命令和本次基线对照见 [验证记录](docs/TESTING.md)。

缺陷修复应有能先失败后通过的行为用例；鉴权至少覆盖拒绝与合法访问，数据隔离至少覆盖两个用户。纯文档整理不新增镜像测试。
