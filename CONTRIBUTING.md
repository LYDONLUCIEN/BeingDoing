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
- Schema／业务文件格式变化同时审阅 `test_agent/snapshot/schema.json` 的导出字段与脱敏规则，并补充独立生产副本迁移用例；不能通过 `create_all`、`stamp head` 或忽略未知字段掩盖迁移缺口。配置与执行入口见 [生产副本自动验收](docs/SNAPSHOT_TESTING.md)。

## 业务决定与实现同步

- 讨论中的跨产品边界记录在 [PRODUCT_EVOLUTION](docs/PRODUCT_EVOLUTION.md)，尚未确认的词义不写入现行业务术语／字段字典。讨论术语与现行术语分区，暂停或尚未实施的规则不自动成为当前开发要求。决定状态、实现验证和部署状态分别记录。
- 改变已确认规则时，说明变更原因、替代关系及受影响模块／接口；同步业务规则、字段含义和行为验收。具有长期取舍的边界变化更新 ADR，普通规则修改不必另建 ADR。
- 同一规则由明确负责的模块实现，调用方通过接口使用；模块粒度根据独立生命周期、数据职责和实际变更范围调整。若规则判断不断复制到多个产品中，先复查职责，避免堆叠例外分支。
- 有存量影响的变更注明兼容期、迁移／回滚与退出条件；验证后清除被替代的运行路径和过期测试，保留历史解释及替代链接。不能仅更新文档而宣称代码迁移完成。

## 文档维护

文档职责：`docs/DEVELOPMENT.md` 维护现行开发方式，产品规则／字段字典维护当前契约，CHANGELOG／ADR 记录变更与取舍，`wiki/` 保留历史证据。更新规则时标明替代关系；旧记录不自动产生新待办。不要复制源码为 `current/` 或维护第二套环境指南，版本比较使用固定 Git 提交。移动资料时同步引用；删除重复材料前验证来源可追溯，保留唯一设计源和有存量用途的迁移依据。

根目录只放入口、必要配置／脚本和明确保留的原始输入；用途及例外见 [根目录索引](docs/ROOT_FILES.md)。新增评审按主题命名，不按 Claude、Cursor 等工具命名；区分“观察”“提案”“已决定”“已验证”，注明日期、基线与替代关系，历史记录不另充当现行规范。

## 提交前检查

每次功能或修复交付必须同时创建/更新 `test_agent/catalog/<id>.json` 与真实测试脚本，并在 `test_agent/changes/*.json` 登记实际变更。此工作由开发者/开发代理完成，不留给 admin 事后补写。定义必须分开记录测试目的、用户输入、断言标准、现行开发文档来源及执行入口；历史功能先核对最新有效规则。详见 [固定用例目录](test_agent/catalog/README.md)。admin 的核心/归档/人工修订由控制库保留，新版本只能提出差异建议。

全量后端验证从根目录执行 `PYTHONPATH=src/backend:. .venv/bin/python -m test_agent.center.verify_backend --output output/backend-<本次唯一名称>`，使用独立源码、数据库、文件根和禁止外部调用的环境；不得直接从共享工作区运行全量 pytest，旧测试未全部自带数据库隔离。证据目录必须是新目录，避免覆盖历史结果。前端执行 `npm run lint`、`npm run test:security`、`npm run build`。涉及渲染器时运行它的 `npm test` 并核对 dist。

在后端目录运行 Black/isort 全量只读检查；变更文件须符合格式。仓库现存格式债和失败测试不能通过大范围无关重排、删除测试或静默跳过隐藏。命令和本次基线对照见 [验证记录](docs/TESTING.md)。

缺陷修复应有能先失败后通过的行为用例；鉴权至少覆盖拒绝与合法访问，数据隔离至少覆盖两个用户。纯文档整理不新增镜像测试。
